"""Contract metadata (expiry, tick_size, contract_unit, currency, roll_rule) -- a plain
Parquet manifest, not a new persisted DuckDB table. core/storage.py has no persisted-table
mechanism at all today (confirmed in specs/00_TRADING_CONVENTIONS.md's Verified core API
section) -- this follows pipelines/weather/anomaly_maps.py's manifest.parquet precedent
instead of introducing a first-of-its-kind architectural piece unilaterally."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SERIES_META_DIR = Path("data/lake/futures_meta")
SERIES_META_PATH = SERIES_META_DIR / "series_meta.parquet"

ROLL_RULE = "5bd_before_expiry"

_COLUMNS = [
    "root",
    "contract",
    "expiry",
    "tick_size",
    "contract_unit",
    "currency",
    "roll_rule",
    "source",
]


def write_series_meta(rows: pd.DataFrame) -> None:
    """Append + drop_duplicates(subset=["root", "contract"], keep="last") -- same pattern
    as anomaly_maps.py's manifest, so a later, corrected contract spec simply overwrites
    the earlier one on the next write."""
    missing = set(_COLUMNS) - set(rows.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")

    SERIES_META_DIR.mkdir(parents=True, exist_ok=True)
    if SERIES_META_PATH.exists():
        existing = pd.read_parquet(SERIES_META_PATH)
        combined = pd.concat([existing, rows[_COLUMNS]], ignore_index=True)
    else:
        combined = rows[_COLUMNS]
    combined = combined.drop_duplicates(subset=["root", "contract"], keep="last")
    combined.to_parquet(SERIES_META_PATH, index=False)


def read_series_meta() -> pd.DataFrame:
    if not SERIES_META_PATH.exists():
        return pd.DataFrame(columns=_COLUMNS)
    return pd.read_parquet(SERIES_META_PATH)
