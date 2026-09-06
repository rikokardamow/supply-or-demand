"""The real Spec-13 scheduled entrypoint -- CFTC COT is a weekly-only report (data as of
Tuesday, released Friday 15:30 ET per root CLAUDE.md's own release calendar), so this
re-pulls a trailing window of weeks rather than a daily one. Idempotent: write_ts_long's
own (series_id, ts) de-dup means re-running this after the same report has already landed
is a safe no-op."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
from core.failures import fails_loudly

from pipelines.cftc.pull import pull_all

TRAILING_WEEKS = 8


def trailing_window(today: date, trailing_weeks: int = TRAILING_WEEKS) -> date:
    return today - timedelta(weeks=trailing_weeks)


@fails_loudly("cftc.pull_weekly")
def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))
    start = trailing_window(ingested_at.date())
    total = pull_all(start=start, end=None, ingested_at=ingested_at)
    print(f"cftc weekly: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
