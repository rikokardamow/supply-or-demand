"""Cached operator-point directory — refresh monthly per specs/03_entsog-eu-gas-flows.md,
not on every pull (it rarely changes and the full fetch is a single, sizeable call)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from pipelines.entsog.client import ENTSOGClient

CACHE_PATH = Path("data/raw/entsog/operatorpointdirections.parquet")


def fetch_and_cache_directory() -> pd.DataFrame:
    directory = ENTSOGClient().get_operator_point_directions()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    directory.to_parquet(CACHE_PATH, index=False)
    return directory


def load_directory(max_age_days: int = 30) -> pd.DataFrame:
    if CACHE_PATH.exists():
        age = datetime.now(UTC) - datetime.fromtimestamp(
            CACHE_PATH.stat().st_mtime, tz=UTC
        )
        if age <= timedelta(days=max_age_days):
            return pd.read_parquet(CACHE_PATH)

    return fetch_and_cache_directory()
