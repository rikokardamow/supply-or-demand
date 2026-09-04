"""One-off historical backfill -- the Disaggregated Futures-Only report goes back to
2006 (confirmed live); this pulls everything available for every root in one go."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from pipelines.cftc.pull import pull_all


def main() -> None:
    ingested_at = pd.Timestamp(datetime.now(UTC))
    total = pull_all(start=None, end=None, ingested_at=ingested_at)
    print(f"cftc history: {total} total rows written", flush=True)


if __name__ == "__main__":
    main()
