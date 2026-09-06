"""Trailing 5-day re-pull -- the real Spec 13 orchestration entrypoint, distinct from
pull_history.py's one-off backfill. Idempotent via write_ts_long's own (series_id, ts)
de-dup (keep latest revision_date), same reasoning as every other pipeline's own
pull_daily.py in this project."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from core.failures import fails_loudly, record_failure

from pipelines.futures.client import ROOTS, get_client
from pipelines.futures.pull import pull_root

TRAILING_DAYS = 5


def trailing_window(today: date, trailing_days: int = TRAILING_DAYS) -> date:
    """`trailing_days` calendar days INCLUDING `today` -- today's own date is the
    (N-1)th day back, not the Nth, or the window covers N+1 days (a real off-by-one
    confirmed live rather than assumed correct: TRAILING_DAYS=5 must mean 5 calendar
    days total, e.g. today through today-4, not today through today-5 (6 days))."""
    return today - timedelta(days=trailing_days - 1)


@fails_loudly("futures.pull_daily")
def main() -> None:
    client = get_client()
    ingested_at = pd.Timestamp(datetime.now())
    today = date.today()
    start = trailing_window(today)

    total_rows = 0
    for root in ROOTS:
        try:
            total_rows += pull_root(client, root, start, today, ingested_at)
        except Exception as exc:
            record_failure(f"{root}", exc)

    print(f"pull_daily: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
