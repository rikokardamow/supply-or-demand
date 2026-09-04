"""Shared per-root pull logic -- both pull_history.py and pull_weekly.py call this with a
different date window, matching pipelines/opec_momr's own one-shared-pull-helper
precedent (avoids duplicating the same fetch -> convert -> write steps twice)."""

from __future__ import annotations

from datetime import date

import pandas as pd
from core.storage import write_ts_long

from pipelines.cftc.client import CONTRACT_CODES, CFTCClient
from pipelines.cftc.to_ts_long import disaggregated_to_ts_long


def pull_root(
    client: CFTCClient,
    root: str,
    start: date | None,
    end: date | None,
    ingested_at: pd.Timestamp,
) -> int:
    df = client.get_disaggregated(root, start=start, end=end)
    if df.empty:
        print(f"{root}: no rows returned", flush=True)
        return 0

    long_df = disaggregated_to_ts_long(df, root, ingested_at)
    write_ts_long(long_df, source="cftc")
    print(
        f"{root}: wrote {len(long_df)} rows "
        f"({df['date'].min().date()} to {df['date'].max().date()})",
        flush=True,
    )
    return len(long_df)


def pull_all(start: date | None, end: date | None, ingested_at: pd.Timestamp) -> int:
    client = CFTCClient()
    total = 0
    for root in CONTRACT_CODES:
        try:
            total += pull_root(client, root, start, end, ingested_at)
        except Exception as exc:
            print(f"{root}: FAILED ({type(exc).__name__}: {exc})", flush=True)
    return total
