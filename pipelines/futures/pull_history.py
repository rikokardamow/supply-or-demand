"""One-off backfill entrypoint. For IBKRClient: 1993-01-01 onward where the source allows.
For ManualCSVClient (this session's actual live path -- no IBKR Gateway running): reads
every settles_*.csv file already present under data/manual/futures/, whatever date range
that covers -- there is no API to backfill from, only whatever the operator has dropped in."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
from core.failures import fails_loudly, record_failure

from pipelines.futures.client import ROOTS, get_client
from pipelines.futures.pull import pull_root

HISTORY_START = date(1993, 1, 1)


@fails_loudly("futures.pull_history")
def main() -> None:
    client = get_client()
    ingested_at = pd.Timestamp(datetime.now())
    today = date.today()

    total_rows = 0
    for root in ROOTS:
        # Per-root failure isolation -- one root's own failure must never abort the
        # rest, same pattern pipelines/entsoe's own pull scripts use.
        try:
            total_rows += pull_root(client, root, HISTORY_START, today, ingested_at)
        except Exception as exc:
            record_failure(f"{root}", exc)

    print(f"pull_history: {total_rows} total rows written", flush=True)


if __name__ == "__main__":
    main()
