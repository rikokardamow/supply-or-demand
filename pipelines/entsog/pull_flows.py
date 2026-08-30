"""Session B: full 2-year pull of physical flows (mode='pipeline') and nominations
(mode='nomination') for every corridor in corridors.py, at point level — per the spec's
data model, corridor aggregation is a read-time transform (transforms.py), not baked into
storage. Supersedes Session A's pull_no_exports.py; NO_EXPORTS is now one of many corridors
this script covers.

pull_all_points() is also used by pull_daily.py (Session D) for the trailing 15-gas-day
revision-window re-pull — same per-point iteration, different date range and write mode."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd
from core.storage import write_flows

from pipelines.entsog.client import ENTSOGClient
from pipelines.entsog.corridors import CORRIDORS, PointSpec, validate_corridors
from pipelines.entsog.directory import load_directory

KWH_TO_GWH = 1_000_000
LOOKBACK_DAYS = 365 * 2

GetIndicatorFn = Callable[[str, str, date, date, str | None], pd.DataFrame]


def pull_all_points(get_fn: GetIndicatorFn, start: date, end: date, mode: str) -> pd.DataFrame:
    all_points: list[tuple[str, PointSpec]] = [
        (corridor_name, point)
        for corridor_name, points in CORRIDORS.items()
        for point in points
    ]

    frames = []
    for i, (corridor_name, point) in enumerate(all_points, start=1):
        raw = get_fn(point.point_key, point.direction_key, start, end, point.operator_key)
        print(
            f"[{i}/{len(all_points)}] {mode} {corridor_name} {point.point_key}: "
            f"{len(raw)} rows",
            flush=True,
        )
        if raw.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "source": "entsog",
                    "from_node": point.from_node,
                    "to_node": point.to_node,
                    "value": raw["value_kwh_d"] / KWH_TO_GWH,
                    "unit": "GWh/d",
                    "ts": raw["ts"],
                    "mode": mode,
                }
            )
        )

    if not frames:
        columns = ["source", "from_node", "to_node", "value", "unit", "ts", "mode"]
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    directory = load_directory()
    validate_corridors(directory)

    client = ENTSOGClient()
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)

    physical = pull_all_points(client.get_physical_flow, start, end, "pipeline")
    write_flows(physical, source="entsog")
    print(f"wrote {len(physical)} physical-flow rows", flush=True)

    nominations = pull_all_points(client.get_nomination, start, end, "nomination")
    write_flows(nominations, source="entsog")
    print(f"wrote {len(nominations)} nomination rows", flush=True)


if __name__ == "__main__":
    main()
