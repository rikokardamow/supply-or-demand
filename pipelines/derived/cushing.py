"""Reads the real weekly Cushing crude stocks series (W_EPC0_SAX_YCUOK_MBBL, source="eia",
pipelines/eia/pull_wpsr.py) plus the new eia.cushing_working_capacity series (source="eia",
semi-annual, pipelines/eia_storage_capacity/pull_history.py), calls
core.curve.cushing_utilisation/utilisation_decile, and writes derived.cushing.util /
derived.cushing.util_decile back. A separate step from pipelines/derived/curve.py -- Cushing
utilisation is a distinct concern (a different pair of real-data dependencies) from the
per-root curve/spread/regime writes. Registered in infra/run_scheduled.py's "wpsr" cadence
group (after eia_wpsr) since Cushing stocks are pulled by the Wed WPSR pull, not the daily
futures pull."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from core.curve import cushing_utilisation, utilisation_decile
from core.storage import read_ts_long, write_ts_long

STOCKS_SERIES_ID = "W_EPC0_SAX_YCUOK_MBBL"
CAPACITY_SERIES_ID = "eia.cushing_working_capacity"


def _write_derived(series_id_suffix: str, values: pd.Series, ingested_at: pd.Timestamp) -> int:
    values = values.dropna()
    if values.empty:
        return 0
    df = pd.DataFrame(
        {
            "series_id": f"derived.cushing.{series_id_suffix}",
            "source": "derived",
            "ts": values.index,
            "value": values.to_numpy(dtype=float),
            "unit": "ratio",
            "geo": "OK",
            "freq": "W",
            "revision_date": ingested_at,
        }
    )
    write_ts_long(df, source="derived")
    return len(df)


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now())

    stocks = read_ts_long(series_ids=[STOCKS_SERIES_ID])
    capacity = read_ts_long(series_ids=[CAPACITY_SERIES_ID])
    if stocks.empty or capacity.empty:
        print("cushing: missing stocks or capacity series -- nothing to compute", flush=True)
        return

    stocks_series = stocks.set_index("ts")["value"].sort_index()
    capacity_series = capacity.set_index("ts")["value"].sort_index()

    util = cushing_utilisation(stocks_series, capacity_series)
    decile = utilisation_decile(util)

    total = _write_derived("util", util, ingested_at)
    total += _write_derived("util_decile", decile, ingested_at)
    print(f"cushing: wrote {total} derived rows", flush=True)


if __name__ == "__main__":
    main()
