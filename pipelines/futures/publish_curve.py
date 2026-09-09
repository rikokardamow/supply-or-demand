"""Publish the lake's futures curve into `serving.curve_settles` and `serving.spreads`.

Spec 32 Session 3. The lake stays the system of record; this writes a read-optimised
serving copy for the Next.js UI (Spec 33). Nothing is recomputed here that
`core/curve.py` already defines -- the spread sign convention below is
`core.curve.time_spreads`' own (front minus back, so positive is backwardation).

The lake's `fut.*` series come in two genuinely different shapes (see
`pipelines/futures/CLAUDE.md`), and the two serving tables are fed from one each:

* **Contract-coded** `fut.lco.<monthcode><year>.settle` (`source="manual"`, the
  Barchart-reconstructed Brent forward curve) -> `serving.curve_settles`, whose
  `contract` column wants a real contract code. `expiry` and `oi` stay NULL: that
  reconstruction carries neither, and inventing them would fabricate market data.
* **Rank-based** `fut.<root>.f01..f04.settle` (`source="eia"`, NYMEX ranks 1-4 to
  2024-04-05) -> `serving.spreads`, which is where the real daily history lives. A rank
  is not a contract, so these deliberately do *not* feed `curve_settles`.

Only ranks 1 to 4 exist, so only the five spreads those four ranks genuinely permit are
emitted. The spec's own `M1-M12` example is not computable from this lake and is never
published as a guess.

Run: `python -m pipelines.futures.publish_curve`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, time
from typing import Final

import pandas as pd
from core.publish import publish
from core.storage import read_ts_long

# The lake partitions `fut.*` across these two sources; `source=` narrows the DuckDB
# glob to a single partition directory, so reading each in turn is far cheaper than one
# unpartitioned scan of the whole lake.
FUTURES_SOURCES: Final = ("eia", "manual")

PIPELINE: Final = "curve"

# (legs label, front rank, back rank). Front minus back, matching
# `core.curve.time_spreads` (s12 = f01 - f02): positive means backwardation.
SPREAD_LEGS: Final[tuple[tuple[str, int, int], ...]] = (
    ("M1-M2", 1, 2),
    ("M1-M3", 1, 3),
    ("M1-M4", 1, 4),
    ("M2-M3", 2, 3),
    ("M3-M4", 3, 4),
)

# `fut.<root>.f01.settle` (a rank) versus `fut.<root>.x2026.settle` (a contract code:
# one of the standard futures month letters plus a four-digit year). The two are told
# apart by shape, not by root -- `f01` and `f2027` both begin with an "f".
_RANK_PATTERN: Final = re.compile(r"^fut\.(?P<root>[a-z0-9]+)\.f(?P<rank>\d{2})\.settle$")
_CONTRACT_PATTERN: Final = re.compile(
    r"^fut\.(?P<root>[a-z0-9]+)\.(?P<contract>[fghjkmnquvxz]\d{4})\.settle$"
)

CURVE_SETTLES_COLUMNS: Final = [
    "root",
    "trade_date",
    "contract",
    "expiry",
    "settle",
    "oi",
    "source",
]
SPREADS_COLUMNS: Final = ["root", "trade_date", "legs", "value"]


def read_futures_settles() -> pd.DataFrame:
    """Read every `fut.*` series out of the lake, both source partitions."""
    frames = [read_ts_long(source=source, series_prefix="fut.") for source in FUTURES_SOURCES]
    return pd.concat(frames, ignore_index=True)


def curve_settles_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Contract-coded settles as `serving.curve_settles` rows.

    Rank-based series are skipped: a rank is not a contract. `expiry` and `oi` are NULL
    because the lake genuinely holds neither for these rows.
    """
    parsed = df["series_id"].str.extract(_CONTRACT_PATTERN)
    matched = parsed["contract"].notna()
    rows = df[matched]

    out = pd.DataFrame(
        {
            "root": parsed.loc[matched, "root"].str.upper(),
            "trade_date": rows["ts"].dt.date,
            "contract": parsed.loc[matched, "contract"].str.upper(),
            "expiry": pd.Series(None, index=rows.index, dtype="object"),
            "settle": rows["value"].astype("float64"),
            "oi": pd.Series(None, index=rows.index, dtype="object"),
            "source": rows["source"],
        },
        columns=CURVE_SETTLES_COLUMNS,
    )
    return out.sort_values(["root", "trade_date", "contract"]).reset_index(drop=True)


def spreads_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar spreads as `serving.spreads` rows, computed off the rank-based panel.

    A row is emitted only where both legs have a real value on that trade date -- an
    inner join, never a fill -- and only for the legs `SPREAD_LEGS` lists.
    """
    parsed = df["series_id"].str.extract(_RANK_PATTERN)
    matched = parsed["rank"].notna()
    if not bool(matched.any()):
        return pd.DataFrame(columns=SPREADS_COLUMNS)
    rows = df[matched]

    panel = pd.DataFrame(
        {
            "root": parsed.loc[matched, "root"].str.upper(),
            "trade_date": rows["ts"].dt.date,
            "rank": parsed.loc[matched, "rank"].astype(int),
            "value": rows["value"].astype("float64"),
        }
    )
    # A duplicate (root, trade_date, rank) would raise here rather than being silently
    # averaged away -- the lake dedups on (series_id, ts), so one is a real anomaly.
    wide = panel.pivot(index=["root", "trade_date"], columns="rank", values="value")

    parts: list[pd.DataFrame] = []
    for legs, front, back in SPREAD_LEGS:
        if front not in wide.columns or back not in wide.columns:
            continue
        diff = (wide[front] - wide[back]).dropna()
        if diff.empty:
            continue
        part = diff.rename("value").reset_index()
        part["legs"] = legs
        parts.append(part)

    if not parts:
        return pd.DataFrame(columns=SPREADS_COLUMNS)
    out = pd.concat(parts, ignore_index=True)[SPREADS_COLUMNS]
    return out.sort_values(["root", "trade_date", "legs"]).reset_index(drop=True)


def _as_of(frame: pd.DataFrame) -> datetime:
    """Data as-of: the latest trade date in the frame, at midnight UTC (Spec 32 §2)."""
    return datetime.combine(max(frame["trade_date"]), time.min, tzinfo=UTC)


def main() -> None:
    df = read_futures_settles()
    if df.empty:
        # An empty read is a defect, not a no-op -- see the same guard in
        # pipelines/gie/publish_gie.py. Returning quietly would hand run_scheduled.py an
        # "OK" for a run that published nothing where it published 132,546 rows the day
        # before, which is exactly the silent-success class pipelines/eia/CLAUDE.md
        # already documents.
        raise RuntimeError(
            f"read 0 fut.* rows across sources {FUTURES_SOURCES} -- the lake is empty or"
            " unreadable; refusing to report success."
        )
    settles = curve_settles_frame(df)
    spreads = spreads_frame(df)
    print(
        f"read {len(df)} fut.* rows -> {len(settles)} curve_settles row(s),"
        f" {len(spreads)} spreads row(s)"
    )

    # Publishing is deliberately not wrapped in try/except: the lake write happened in an
    # earlier pipeline run, so a publish failure loses no data, but it must still surface
    # as a non-zero exit rather than a quietly missing serving copy (core/failures.py).
    if settles.empty:
        print("serving.curve_settles: no contract-coded series in the lake, nothing to publish")
    else:
        publish(
            "curve_settles",
            settles,
            as_of=_as_of(settles),
            source_note=(
                "Contract-coded futures settles"
                f" ({', '.join(sorted(set(settles['root'])))});"
                " expiry and open interest not carried by the source"
            ),
            key=["root", "trade_date", "contract"],
            pipeline=PIPELINE,
        )

    if spreads.empty:
        print("serving.spreads: no rank-based series in the lake, nothing to publish")
    else:
        publish(
            "spreads",
            spreads,
            as_of=_as_of(spreads),
            source_note=(
                "Calendar spreads from the rank-based settle panel"
                f" ({', '.join(sorted(set(spreads['root'])))}), front minus back;"
                " ranks 1-4 only, so M1-M12 is not computable"
            ),
            key=["root", "trade_date", "legs"],
            pipeline=PIPELINE,
        )


if __name__ == "__main__":
    main()
