"""Pulls JODI-Oil crude production, refinery intake, and closing stocks for the
top-15 producers into ts_long. Confirmed live via the real flow-code -> concept
mapping documented in JODI's own "Item Names" guide (jodidata.org):
INDPROD="Production", REFINOBS="Refinery intake", CLOSTLV="Closing stocks" --
all three live in the "primary" (crude oil) table, not "secondary" (refined
products, out of scope here).

This is also the monthly entrypoint (per the spec) -- the current year's file
is always re-downloaded (see client.py), and write_ts_long's revision-based
de-dup makes re-running this idempotent."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.jodi.client import download_annual_csv

# Confirmed live (Session C): computed from the actual current-year primary
# CSV, ranked by mean CRUDEOIL/INDPROD/KBD across all months with real data
# (not just the latest month -- confirmed live that a handful of countries
# have real gaps in their latest 1-2 months, which would skew a
# single-month ranking). Notably excludes Russia, Iraq, Iran, UAE, and
# Brazil -- all major real-world producers, but all have *zero* INDPROD rows
# in JODI's primary table for all of 2026 (a genuine, confirmed reporting
# gap, not a bug -- these countries don't report crude production through
# this channel). This is the real, achievable "top 15" from JODI's own data,
# not an idealised list from other sources.
TOP_15_PRODUCERS = [
    "US", "SA", "CN", "CA", "NO", "MX", "KZ", "KW",
    "NG", "VE", "DZ", "GB", "IN", "ID", "MY",
]  # fmt: skip

# (FLOW_BREAKDOWN code, series slug, the one real unit that applies -- KBD for
# rate flows, KBBL for the stock *level* -- confirmed live: CLOSTLV under KBD
# comes back "x", not a real value).
_FLOWS = [
    ("INDPROD", "crude_production", "KBD", "kb/d"),
    ("REFINOBS", "refinery_intake", "KBD", "kb/d"),
    ("CLOSTLV", "closing_stocks", "KBBL", "kbbl"),
]

CURRENT_YEAR_HISTORY_DEPTH = 2  # current year + 1 prior closed year


def filter_and_transform(raw: pd.DataFrame, revision_date: datetime) -> pd.DataFrame:
    """Filters one year's raw primary-table CSV down to the 3 target flows for
    `TOP_15_PRODUCERS` and reshapes to ts_long. Pulled out of `main()` so the
    real filtering/reshaping logic is unit-testable against a small synthetic
    DataFrame, without needing the real multi-megabyte CSV as a fixture."""
    raw = raw[raw["REF_AREA"].isin(TOP_15_PRODUCERS) & (raw["ENERGY_PRODUCT"] == "CRUDEOIL")]

    frames = []
    for flow_code, slug, unit_measure, unit_label in _FLOWS:
        is_flow = raw["FLOW_BREAKDOWN"] == flow_code
        is_unit = raw["UNIT_MEASURE"] == unit_measure
        subset = raw[is_flow & is_unit]
        subset = subset[~subset["OBS_VALUE"].isin(["-", "x"])]
        if subset.empty:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "series_id": "jodi." + slug + "." + subset["REF_AREA"].str.lower(),
                    "source": "jodi",
                    "ts": pd.to_datetime(subset["TIME_PERIOD"], format="%Y-%m"),
                    "value": pd.to_numeric(subset["OBS_VALUE"]),
                    "unit": unit_label,
                    "geo": subset["REF_AREA"],
                    "freq": "M",
                    "revision_date": revision_date,
                }
            )
        )

    if not frames:
        return pd.DataFrame(
            columns=["series_id", "source", "ts", "value", "unit", "geo", "freq", "revision_date"]
        )
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    end_year = date.today().year
    years = range(end_year - CURRENT_YEAR_HISTORY_DEPTH + 1, end_year + 1)
    pulled_at = datetime.now(UTC)

    frames = []
    for year in years:
        raw = download_annual_csv(year, is_current_year=(year == end_year))
        transformed = filter_and_transform(raw, pulled_at)
        if not transformed.empty:
            frames.append(transformed)
        n_countries = raw[raw["REF_AREA"].isin(TOP_15_PRODUCERS)]["REF_AREA"].nunique()
        print(f"{year}: {len(transformed)} rows across {n_countries} countries", flush=True)

    if not frames:
        print("no rows pulled", flush=True)
        return
    df = pd.concat(frames, ignore_index=True)
    write_ts_long(df, source="jodi")
    print(f"wrote {len(df)} rows across {df['series_id'].nunique()} series", flush=True)


if __name__ == "__main__":
    main()
