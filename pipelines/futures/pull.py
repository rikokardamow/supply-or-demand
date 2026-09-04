"""Shared per-root pull logic for pull_history.py (one-off backfill) and pull_daily.py
(trailing-window re-pull) -- previously duplicated near-identically in both, with
pull_daily.py reaching into pull_history.py's own private `_series_meta_rows` across
module boundaries. Factored here instead, matching pipelines/entsoe's own precedent
of exposing a shared pull_*() helper both its history and daily entrypoints call with
different date windows rather than duplicating the per-item resilience loop."""

from __future__ import annotations

from datetime import date

import pandas as pd
from core.settings import settings
from core.storage import write_ts_long

from pipelines.futures.client import ContractMeta, FuturesClient
from pipelines.futures.series_meta import ROLL_RULE, write_series_meta
from pipelines.futures.to_ts_long import settles_to_ts_long


def _series_meta_rows(contracts: list[ContractMeta], source: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "root": c.root,
                "contract": c.contract,
                "expiry": pd.Timestamp(c.expiry),
                "tick_size": c.tick_size,
                "contract_unit": c.contract_unit,
                "currency": c.currency,
                "roll_rule": ROLL_RULE,
                "source": source,
            }
            for c in contracts
        ]
    )


def pull_root(
    client: FuturesClient, root: str, start: date, end: date, ingested_at: pd.Timestamp
) -> int:
    """One root's full pull: list_contracts -> write_series_meta -> get_settles ->
    to_ts_long -> write_ts_long. Returns rows written (0 if nothing was found).
    Raises on a real failure -- callers wrap this per root in their own try/except
    for cross-root failure isolation, same as every other pipeline's own pull loop."""
    contracts = client.list_contracts(root)
    if not contracts:
        print(f"{root}: no contracts found", flush=True)
        return 0

    write_series_meta(_series_meta_rows(contracts, settings.futures_source))

    settles = client.get_settles(root, [c.contract for c in contracts], start, end)
    if settles.empty:
        print(f"{root}: no settles rows pulled", flush=True)
        return 0

    long_rows = settles_to_ts_long(settles, ingested_at, contracts, settings.futures_source)
    write_ts_long(long_rows, source=settings.futures_source)
    print(f"{root}: wrote {len(long_rows)} rows", flush=True)
    return len(long_rows)
