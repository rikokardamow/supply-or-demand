"""Pulls real GDP growth (y/y, seasonally adjusted) for the US, China and the euro area
from the OECD's Quarterly National Accounts into ts_long -- the GDP side of the oil-demand
elasticity (core/oil_demand.py).

One source for all three blocks on purpose: a single methodology, and the only free route
that carries quarterly real China GDP at all (FRED does not). The US series equals the
year-on-year change of `fred.gdpc1` already in the lake for every quarter since 2013.

Run by hand: `python -m pipelines.oecd.pull_gdp`. The response is small; re-running is
idempotent through write_ts_long's revision de-dup, and picks up OECD's own revisions.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.oecd.client import fetch_real_gdp_growth

# OECD REF_AREA -> the lake's geo code.
AREA_GEO = {"USA": "US", "CHN": "CN", "EA": "EA"}

START_PERIOD = "2012-Q1"


def to_ts_long(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame:
    geo = raw["REF_AREA"].map(AREA_GEO)
    quarter_start = pd.PeriodIndex(raw["TIME_PERIOD"], freq="Q").to_timestamp(how="start")
    return pd.DataFrame(
        {
            "series_id": "oecd.gdp_real_yoy." + geo.str.lower(),
            "source": "oecd",
            "ts": quarter_start,
            "value": raw["OBS_VALUE"].astype("float64").to_numpy(),
            "unit": "% y/y",
            "geo": geo,
            "freq": "Q",
            "revision_date": revision_date,
        }
    )


def main() -> None:
    raw = fetch_real_gdp_growth(list(AREA_GEO), start_period=START_PERIOD)
    df = to_ts_long(raw, datetime.now(UTC))
    write_ts_long(df, source="oecd")
    for series_id, group in df.groupby("series_id"):
        print(
            f"{series_id}: {len(group)} quarters, "
            f"{group['ts'].min().date()} -> {group['ts'].max().date()}",
            flush=True,
        )


if __name__ == "__main__":
    main()
