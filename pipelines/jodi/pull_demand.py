# pipelines/jodi/pull_demand.py
"""Pulls JODI-Oil total product demand for the US, China and the euro-area members into
ts_long -- the consumption side of the oil-demand elasticity (core/oil_demand.py).

Reads the SECONDARY table (refined products), not the primary one pull_jodi.py reads.
`FLOW_BREAKDOWN=TOTDEMO` + `ENERGY_PRODUCT=TOTPRODS` + `UNIT_MEASURE=KBD` is total oil
product demand per country per month, in thousand barrels a day -- confirmed live
2026-10-10, complete for the US, China and all twenty euro-area members in 2013 and 2020.

All twenty members are ingested, including Malta, whose reporting has gaps. Which members
form the model's basket is the model's decision (core.oil_demand.EURO_AREA_BASKET), not
the ingest's: the lake holds what JODI published.

Run by hand: `python -m pipelines.jodi.pull_demand`. Not registered in
infra/run_scheduled.py -- closed years are about 27 MB each and are cached after the first
run, which downloads roughly 380 MB.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.jodi.client import download_annual_csv

EURO_AREA_20 = [
    "AT", "BE", "HR", "CY", "EE", "FI", "FR", "DE", "GR", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PT", "SK", "SI", "ES",
]  # fmt: skip

DEMAND_COUNTRIES = ["US", "CN", *EURO_AREA_20]

# The regression panel opens 1Q 2013 and is in year-on-year changes, so levels are needed
# from a year earlier.
START_YEAR = 2012

_TS_LONG_COLUMNS = [
    "series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"
]  # fmt: skip


def filter_and_transform(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame:
    """One year's raw secondary-table CSV -> ts_long rows of total product demand.

    `-` (not reported) and `x` (confidential / not applicable) are dropped, never zeroed:
    a zero would read as a country consuming no oil that month. A blank cell is dropped too.
    """
    keep = (
        raw["REF_AREA"].isin(DEMAND_COUNTRIES)
        & (raw["FLOW_BREAKDOWN"] == "TOTDEMO")
        & (raw["ENERGY_PRODUCT"] == "TOTPRODS")
        & (raw["UNIT_MEASURE"] == "KBD")
        & ~raw["OBS_VALUE"].isin(["-", "x"])
        & raw["OBS_VALUE"].notna()
    )
    subset = raw[keep]
    if subset.empty:
        return pd.DataFrame(columns=_TS_LONG_COLUMNS)
    return pd.DataFrame(
        {
            "series_id": "jodi.total_demand." + subset["REF_AREA"].str.lower(),
            "source": "jodi",
            "ts": pd.to_datetime(subset["TIME_PERIOD"], format="%Y-%m"),
            "value": pd.to_numeric(subset["OBS_VALUE"]),
            "unit": "kb/d",
            "geo": subset["REF_AREA"],
            "freq": "M",
            "revision_date": revision_date,
        }
    ).reset_index(drop=True)


def main() -> None:
    end_year = date.today().year
    pulled_at = datetime.now(UTC)

    frames = []
    for year in range(START_YEAR, end_year + 1):
        raw = download_annual_csv(year, is_current_year=(year == end_year), table="secondary")
        transformed = filter_and_transform(raw, pulled_at)
        print(
            f"{year}: {len(transformed)} rows across "
            f"{transformed['geo'].nunique() if not transformed.empty else 0} countries",
            flush=True,
        )
        if not transformed.empty:
            frames.append(transformed)

    if not frames:
        raise RuntimeError(
            "JODI secondary returned no total-demand rows for any year -- the flow, product "
            "or unit code has changed. Check the columns of the downloaded file."
        )
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="jodi")
    print(f"wrote {len(df)} rows across {df['series_id'].nunique()} series", flush=True)


if __name__ == "__main__":
    main()
