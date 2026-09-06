"""Reads the lake, calls core.fundamentals's pure functions, writes
derived.inv.dev_z.uscrude / derived.cot.<root>.mm_pct_3y back. derived.spare_cap.regime is
deliberately NOT written this session -- see CLAUDE.md."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.failures import fails_loudly, record_failure
from core.fundamentals import cot_percentiles, inventory_deviation
from core.seasonal import REFERENCE_YEAR
from core.storage import read_ts_long, write_ts_long

from pipelines.cftc.client import CONTRACT_CODES

US_CRUDE_STOCKS_SERIES_ID = "WCESTUS1"


def _write_derived(
    series_id: str, values: pd.Series, unit: str, geo: str, ingested_at: pd.Timestamp
) -> int:
    values = values.dropna()
    if values.empty:
        return 0
    df = pd.DataFrame(
        {
            "series_id": series_id,
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype=float),
            "unit": unit,
            "geo": geo,
            "freq": "W",
            "revision_date": ingested_at,
        }
    )
    write_ts_long(df, source="derived")
    return len(df)


def _pull_inventory_deviation(ingested_at: pd.Timestamp) -> int:
    stocks = read_ts_long(series_ids=[US_CRUDE_STOCKS_SERIES_ID])
    if stocks.empty:
        print("inv.dev_z.uscrude: no US crude stocks data yet", flush=True)
        return 0

    result = inventory_deviation(stocks[["ts", "value"]])

    # inventory_deviation (like core.seasonal.seasonal_stats underneath it) is indexed
    # by day-of-year, not a real calendar date -- map the latest year's own real dates
    # back onto it (same reference_doy technique 01_us_padd.py's own _seasonal_section
    # already uses) before this can be written as a ts_long series.
    current = stocks.sort_values("ts")
    current_year = current["ts"].dt.year.max()
    current = current[current["ts"].dt.year == current_year]
    reference_doy = current["ts"].map(lambda d: d.replace(year=REFERENCE_YEAR)).dt.dayofyear
    dev_z_by_date = pd.Series(
        result["dev_z"].reindex(reference_doy).to_numpy(), index=current["ts"].to_numpy()
    )

    return _write_derived(
        "derived.inv.dev_z.uscrude", dev_z_by_date, "z-score", "US", ingested_at
    )


def _pull_cot(root: str, ingested_at: pd.Timestamp) -> int:
    long_df = read_ts_long(series_ids=[f"cftc.{root}.mm_long"])
    short_df = read_ts_long(series_ids=[f"cftc.{root}.mm_short"])
    oi_df = read_ts_long(series_ids=[f"cftc.{root}.oi"])
    if long_df.empty or short_df.empty or oi_df.empty:
        print(
            f"cot.{root}.mm_pct_3y: no CFTC data yet -- run pipelines/cftc/pull_history.py",
            flush=True,
        )
        return 0

    long = long_df.set_index("ts")["value"].sort_index()
    short = short_df.set_index("ts")["value"].sort_index()
    oi = oi_df.set_index("ts")["value"].sort_index()

    result = cot_percentiles(long, short, oi)
    return _write_derived(
        f"derived.cot.{root}.mm_pct_3y",
        result["pct_rank_3y"],
        "percentile",
        root.upper(),
        ingested_at,
    )


@fails_loudly("derived.fundamentals")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))
    total = 0

    try:
        total += _pull_inventory_deviation(ingested_at)
    except Exception as exc:
        record_failure("inv.dev_z.uscrude", exc)

    for root in CONTRACT_CODES:
        try:
            total += _pull_cot(root, ingested_at)
        except Exception as exc:
            record_failure(f"cot.{root}", exc)

    print(
        "spare_cap.regime: skipped -- no real EIA STEO/IEA OMR spare-capacity data yet "
        "(Session B's manual_physical extension)",
        flush=True,
    )
    print(f"derived.fundamentals: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
