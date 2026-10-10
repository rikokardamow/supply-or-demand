"""Contract metadata (expiry, tick_size, contract_unit, currency, roll_rule) -- a plain
Parquet manifest, not a new persisted DuckDB table. core/storage.py has no persisted-table
mechanism at all today (confirmed in specs/00_TRADING_CONVENTIONS.md's Verified core API
section) -- this follows pipelines/weather/anomaly_maps.py's manifest.parquet precedent
instead of introducing a first-of-its-kind architectural piece unilaterally."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from core import storage

SERIES_META_SUBDIR = "futures_meta"


def series_meta_dir() -> Path:
    """`core.storage.LAKE_ROOT / "futures_meta"`, resolved at call time -- deliberately a
    function, not a module constant.

    The directory was once the *relative* `Path("data/lake/futures_meta")`, independent of
    `LAKE_ROOT`, so only `monkeypatch.chdir` could isolate it: a test that patched
    `core.storage.LAKE_ROOT` (the ordinary lake isolation in this suite) and forgot the
    chdir wrote straight into the real manifest, which holds the only real contract
    expiries this project has. Reading `storage.LAKE_ROOT` through the module on every
    call -- rather than binding it at import, which `from core.storage import LAKE_ROOT`
    would do -- is what makes `monkeypatch.setattr(storage, "LAKE_ROOT", tmp_path)`
    sufficient on its own."""
    return storage.LAKE_ROOT / SERIES_META_SUBDIR


def series_meta_path() -> Path:
    return series_meta_dir() / "series_meta.parquet"


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

    path = series_meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, rows[_COLUMNS]], ignore_index=True)
    else:
        combined = rows[_COLUMNS]
    combined = combined.drop_duplicates(subset=["root", "contract"], keep="last")
    combined.to_parquet(path, index=False)


def read_series_meta() -> pd.DataFrame:
    path = series_meta_path()
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    return pd.read_parquet(path)
