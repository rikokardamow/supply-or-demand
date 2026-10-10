# pipelines/derived/oil_demand.py
"""Writes the observed oil-demand series and the assumption-driven scenario into the lake
as `derived.oil_demand.*`.

Reads `jodi.total_demand.*` and `oecd.gdp_real_yoy.*`, calls core.oil_demand's pure
functions, writes `ts_long` rows back -- the same shape as every other module here.

Three series per block:
- `.level`        quarterly mean demand, kb/d -- observed
- `.yoy`          its change on a year earlier, % -- observed
- `.yoy.scenario` demand growth implied by the owner's ASSUMED GDP growth, % -- a scenario

The fitted coefficients are not written. A slope belongs to a panel and a date, not to a
time axis; the page recomputes the model card from the observed series.

Not registered in infra/run_scheduled.py. Run it by hand after pull_demand, pull_gdp, or an
edit to gdp_assumptions.csv.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from core import oil_demand as od
from core.storage import read_ts_long, write_ts_long

ASSUMPTIONS_PATH = Path(__file__).parent / "oil_demand" / "gdp_assumptions.csv"

BLOCK_GEO = {"us": "US", "cn": "CN", "ea": "EA"}

UNIT_LEVEL = "kb/d"
UNIT_YOY = "% y/y"


def read_monthly_demand() -> pd.DataFrame:
    """Wide monthly demand from the lake: month-start index, one ISO-2 column per country."""
    long = read_ts_long(series_prefix="jodi.total_demand.", source="jodi")
    if long.empty:
        raise RuntimeError(
            "no jodi.total_demand.* series in the lake -- run "
            "`python -m pipelines.jodi.pull_demand` first"
        )
    return long.pivot_table(index="ts", columns="geo", values="value", aggfunc="last")


def read_gdp_yoy(block: str) -> pd.Series:
    series_id = f"oecd.gdp_real_yoy.{block}"
    long = read_ts_long(series_ids=[series_id], source="oecd")
    if long.empty:
        raise RuntimeError(
            f"no {series_id} in the lake -- run `python -m pipelines.oecd.pull_gdp` first"
        )
    return long.set_index("ts")["value"].sort_index()


def read_assumptions(path: Path) -> pd.DataFrame:
    """A blank `gdp_yoy_pct` reads as NaN -- no assumption -- never as 0.0, which would
    assert zero growth."""
    frame = pd.read_csv(path, dtype=str)
    frame["quarter"] = pd.to_datetime(frame["quarter"])
    frame["gdp_yoy_pct"] = pd.to_numeric(frame["gdp_yoy_pct"], errors="coerce")
    return frame[["block", "quarter", "gdp_yoy_pct", "author", "as_of"]]


def build_panel(block: str, monthly: pd.DataFrame, gdp_yoy: pd.Series) -> pd.DataFrame:
    """The regression panel for one block. Shared with the page so both fit the same rows."""
    quarterly = od.quarterly_demand(monthly, od.BLOCKS[block])
    return od.align(od.yoy_pct(quarterly), gdp_yoy)


def _rows(series: pd.Series, series_id: str, unit: str, geo: str) -> pd.DataFrame:
    observed = series.dropna()
    return pd.DataFrame(
        {
            "series_id": series_id,
            "ts": observed.index,
            "value": observed.to_numpy(dtype="float64"),
            "unit": unit,
            "geo": geo,
        }
    )


def build_rows(
    monthly: pd.DataFrame,
    gdp_by_block: dict[str, pd.Series],
    assumptions: pd.DataFrame,
    revision_date: pd.Timestamp | datetime,
) -> pd.DataFrame:
    unknown = sorted(set(assumptions["block"]) - set(od.BLOCKS))
    if unknown:
        raise ValueError(
            f"gdp_assumptions.csv names block(s) {unknown}; known blocks are {sorted(od.BLOCKS)}"
        )

    frames: list[pd.DataFrame] = []
    for block, members in od.BLOCKS.items():
        geo = BLOCK_GEO[block]
        level = od.quarterly_demand(monthly, members)
        yoy = od.yoy_pct(level)
        frames.append(_rows(level, f"derived.oil_demand.{block}.level", UNIT_LEVEL, geo))
        frames.append(_rows(yoy, f"derived.oil_demand.{block}.yoy", UNIT_YOY, geo))

        assumed = assumptions[(assumptions["block"] == block)].dropna(subset=["gdp_yoy_pct"])
        if assumed.empty:
            continue
        last_observed = yoy.dropna().index.max()
        inside = assumed[assumed["quarter"] <= last_observed]
        if not inside.empty:
            raise ValueError(
                f"gdp_assumptions.csv sets {block} growth for "
                f"{[q.date().isoformat() for q in inside['quarter']]}, already observed "
                f"(last observed quarter {last_observed.date()}). A scenario starts after it."
            )
        fit = od.fit_elasticity(od.align(yoy, gdp_by_block[block]))
        path = od.project_demand_yoy(
            fit, assumed.set_index("quarter")["gdp_yoy_pct"].sort_index()
        )
        frames.append(
            _rows(path, f"derived.oil_demand.{block}.yoy.scenario", UNIT_YOY, geo)
        )

    out = pd.concat(frames, ignore_index=True)
    out["source"] = "derived"
    out["freq"] = "Q"
    out["revision_date"] = pd.Timestamp(revision_date)
    return out[["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]]


def main() -> None:
    monthly = read_monthly_demand()
    gdp_by_block = {block: read_gdp_yoy(block) for block in od.BLOCKS}
    assumptions = read_assumptions(ASSUMPTIONS_PATH)
    rows = build_rows(monthly, gdp_by_block, assumptions, datetime.now(UTC))
    write_ts_long(rows, source="derived")
    for series_id, group in rows.groupby("series_id"):
        print(
            f"{series_id}: {len(group)} quarters, "
            f"{group['ts'].min().date()} -> {group['ts'].max().date()}",
            flush=True,
        )
    if not rows["series_id"].str.endswith(".scenario").any():
        print(
            "no scenario written: gdp_assumptions.csv holds no assumption. That is the "
            "shipped state, not an error.",
            flush=True,
        )


if __name__ == "__main__":
    main()
