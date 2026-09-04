"""One-off historical backfill -- the ONLY entrypoint this pipeline has. No pull_daily.py:
the source report is confirmed discontinued (EIA's own words, as of the March 2024 data),
so there is nothing to re-pull on a schedule. Not registered in infra/run_scheduled.py for
the same reason."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_ts_long

from pipelines.eia_storage_capacity.client import fetch_cushing_capacity

SERIES_ID = "eia.cushing_working_capacity"


def main() -> None:
    capacity = fetch_cushing_capacity()
    ingested_at = pd.Timestamp(datetime.now(UTC))

    df = pd.DataFrame(
        {
            "series_id": SERIES_ID,
            "source": "eia",
            "ts": capacity["ts"],
            "value": capacity["value"],
            "unit": "MBBL",
            "geo": "OK",
            "freq": "semi-annual",
            "revision_date": ingested_at,
        }
    )
    write_ts_long(df, source="eia")
    print(f"wrote {len(df)} rows ({df['ts'].min().date()} to {df['ts'].max().date()})", flush=True)


if __name__ == "__main__":
    main()
