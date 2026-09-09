"""Raw AIS capture to the latest position per vessel, and on to the serving layer.

Spec 11 Session C in the shape this project actually needs first: the raw JSONL the
ingester writes is turned into one row per MMSI -- its most recent position -- and
published to `serving.vessel_latest`, which is what the map reads. The full
`vessel_positions` history table and the 5-minute downsample come later; a map needs the
latest fix, not the track.

**Ship class is a heuristic, and the spec says to treat it as one.** AIS type codes 80-89
are tankers, 70-79 cargo, and 84 is nominally an LNG carrier -- but the field is entered
by the crew and is wrong often enough that a class here means "reported as", never
"verified as". Anything downstream must carry that caveat.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pandas as pd
from core.publish import publish

from pipelines.ais.geofences import region_for
from pipelines.ais.ingester import RAW_ROOT

SERVING_VESSEL_COLUMNS: Final = [
    "mmsi",
    "ts",
    "geom",
    "sog",
    "cog",
    "nav_status",
    "ship_type",
    "draught",
    "name",
    "destination",
]


def classify(ship_type: int | None) -> str:
    """AIS type code to the four classes Spec 32's `vessel_latest.ship_type` allows.

    Reported by the vessel, not verified: the code is hand-entered and frequently wrong.
    'other' covers both a genuinely different vessel and a missing or nonsense code --
    they are indistinguishable here, and pretending otherwise would invent precision.
    """
    if ship_type is None:
        return "other"
    if ship_type == 84:
        return "lng"
    if 80 <= ship_type <= 89:
        return "crude"
    if 70 <= ship_type <= 79:
        return "products"
    return "other"


def read_raw(paths: list[Path]) -> Iterator[dict[str, Any]]:
    """Every JSON envelope in the given gzip JSONL files, bad lines skipped.

    A truncated final line is expected rather than exceptional: the ingester appends to
    an open file, so a capture interrupted mid-write leaves one partial record. Skipping
    it loses one position; refusing the file would lose the hour.
    """
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def latest_positions(messages: Iterator[dict[str, Any]]) -> pd.DataFrame:
    """One row per MMSI: its most recent position report, enriched with static data.

    Position and static data arrive as separate message types on different cadences, so
    a vessel's name and type are merged in from whichever `ShipStaticData` frame was
    seen -- often none, in a short capture, which is why those columns are nullable.
    """
    positions: dict[int, dict[str, Any]] = {}
    statics: dict[int, dict[str, Any]] = {}

    for message in messages:
        kind = message.get("MessageType")
        meta = message.get("MetaData") or {}
        mmsi = meta.get("MMSI")
        if not mmsi:
            continue
        mmsi = int(mmsi)

        if kind == "PositionReport":
            report = (message.get("Message") or {}).get("PositionReport") or {}
            lat = meta.get("latitude")
            lon = meta.get("longitude")
            if lat is None or lon is None:
                continue
            ts = meta.get("time_utc")
            previous = positions.get(mmsi)
            # Keep the newest fix. Frames can arrive out of order across a reconnect.
            if previous is not None and ts is not None and previous.get("raw_ts", "") > ts:
                continue
            positions[mmsi] = {
                "mmsi": mmsi,
                "raw_ts": ts,
                "lat": float(lat),
                "lon": float(lon),
                "sog": report.get("Sog"),
                "cog": report.get("Cog"),
                "nav_status": report.get("NavigationalStatus"),
            }
        elif kind == "ShipStaticData":
            static = (message.get("Message") or {}).get("ShipStaticData") or {}
            statics[mmsi] = {
                "name": (meta.get("ShipName") or static.get("Name") or "").strip() or None,
                "ship_type": classify(static.get("Type")),
                "draught": static.get("MaximumStaticDraught"),
                "destination": (static.get("Destination") or "").strip() or None,
            }

    rows: list[dict[str, Any]] = []
    for mmsi, position in positions.items():
        static = statics.get(mmsi, {})
        ts = _parse_ts(position["raw_ts"])
        if ts is None:
            continue
        rows.append(
            {
                "mmsi": mmsi,
                "ts": ts,
                # EWKT, which PostGIS parses straight into a geography column. Longitude
                # first: POINT is (x, y), and x is longitude -- the reverse of AIS's own
                # lat-first convention, and an easy way to put every ship in the sea off
                # Africa if got wrong.
                "geom": f"SRID=4326;POINT({position['lon']} {position['lat']})",
                "sog": position.get("sog"),
                "cog": position.get("cog"),
                "nav_status": _nav_status(position.get("nav_status")),
                "ship_type": static.get("ship_type", "other"),
                "draught": static.get("draught"),
                "name": static.get("name"),
                "destination": static.get("destination"),
            }
        )

    if not rows:
        return pd.DataFrame(columns=SERVING_VESSEL_COLUMNS)
    return pd.DataFrame(rows)[SERVING_VESSEL_COLUMNS]


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        # aisstream stamps e.g. "2026-09-09 14:12:03.123456789 +0000 UTC" -- not ISO, and
        # with nanoseconds Python's parser rejects.
        cleaned = str(value).replace(" +0000 UTC", "").split(".")[0]
        return datetime.fromisoformat(cleaned).replace(tzinfo=UTC)
    except ValueError:
        return None


def _nav_status(code: Any) -> str | None:
    """The handful of navigational statuses that matter for floating storage."""
    if code is None:
        return None
    known = {0: "under way", 1: "at anchor", 2: "not under command", 5: "moored"}
    return known.get(int(code), f"code {int(code)}")


def raw_files(root: Path = RAW_ROOT) -> list[Path]:
    return sorted(root.rglob("*.jsonl.gz"))


def main() -> None:
    paths = raw_files()
    if not paths:
        raise RuntimeError(
            f"no raw AIS capture under {RAW_ROOT} -- run pipelines.ais.ingester first"
        )

    vessels = latest_positions(read_raw(paths))
    if vessels.empty:
        raise RuntimeError("raw AIS capture contained no usable position reports")

    in_region = sum(
        1
        for _, row in vessels.iterrows()
        if region_for(
            float(row["geom"].split("(")[1].split()[1].rstrip(")")),
            float(row["geom"].split("(")[1].split()[0]),
        )
    )
    print(f"{len(vessels)} vessels from {len(paths)} raw file(s), {in_region} inside a region")

    published = publish(
        "vessel_latest",
        vessels,
        as_of=vessels["ts"].max().to_pydatetime(),
        source_note=(
            "aisstream.io terrestrial AIS, latest position per vessel. Coverage is good"
            " at coasts and chokepoints and patchy in open ocean; ship class is as"
            " reported by the vessel, not verified"
        ),
        key=["mmsi"],
        pipeline="ais",
    )
    print(f"published {published} vessel positions")


if __name__ == "__main__":
    main()
