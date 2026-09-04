"""Trailing 5-day re-pull -- the real Spec 13 orchestration entrypoint, distinct from
pull_history.py's one-off backfill. Idempotent via write_ts_long's own (series_id, ts)
de-dup (keep latest revision_date), same reasoning as every other pipeline's own
pull_daily.py in this project."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from core.storage import write_ts_long

from pipelines.futures.client import ROOTS, get_client
from pipelines.futures.pull_history import _series_meta_rows
from pipelines.futures.series_meta import write_series_meta
from pipelines.futures.to_ts_long import settles_to_ts_long

TRAILING_DAYS = 5


def main() -> None:
    from core.settings import settings

    client = get_client()
    ingested_at = pd.Timestamp(datetime.now())
    today = date.today()
    start = today - timedelta(days=TRAILING_DAYS)

    total_rows = 0
    for root in ROOTS:
        try:
            contracts = client.list_contracts(root)
            if not contracts:
                print(f"{root}: no contracts found", flush=True)
                continue

            write_series_meta(_series_meta_rows(contracts, settings.futures_source))

            settles = client.get_settles(root, [c.contract for c in contracts], start, today)
            if settles.empty:
                print(f"{root}: no settles rows pulled", flush=True)
                continue

            long_rows = settles_to_ts_long(settles, ingested_at)
            write_ts_long(long_rows, source="futures")
            total_rows += len(long_rows)
            print(f"{root}: wrote {len(long_rows)} rows", flush=True)
        except Exception as exc:
            print(f"{root}: FAILED ({type(exc).__name__}: {exc})", flush=True)

    print(f"pull_daily: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
