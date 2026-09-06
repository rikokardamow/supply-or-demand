from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
from pipelines.entsog import directory as directory_module


def _frame(marker: str) -> pd.DataFrame:
    return pd.DataFrame({"pointKey": ["PT-1"], "operatorLabel": [marker]})


@pytest.fixture
def cache_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "operatorpointdirections.parquet"
    monkeypatch.setattr(directory_module, "CACHE_PATH", path)
    return path


def _stub_client(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    class _Client:
        def get_operator_point_directions(self) -> pd.DataFrame:
            calls.append("fetched")
            return _frame("from-api")

    monkeypatch.setattr(directory_module, "ENTSOGClient", _Client)


def test_a_fresh_cache_is_read_from_disk_without_calling_the_api(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of this module: the directory fetch is a single sizeable call and
    the data rarely changes, so a daily pull must not re-fetch it."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _frame("from-cache").to_parquet(cache_path, index=False)
    calls: list[str] = []
    _stub_client(monkeypatch, calls)

    result = directory_module.load_directory()

    assert calls == []
    assert result["operatorLabel"].tolist() == ["from-cache"]


def test_a_cache_older_than_max_age_is_refetched(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _frame("stale").to_parquet(cache_path, index=False)
    old = time.time() - timedelta(days=31).total_seconds()
    os.utime(cache_path, (old, old))
    calls: list[str] = []
    _stub_client(monkeypatch, calls)

    result = directory_module.load_directory(max_age_days=30)

    assert calls == ["fetched"]
    assert result["operatorLabel"].tolist() == ["from-api"]


def test_the_age_boundary_counts_as_fresh(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `age <= max_age_days` -- a cache exactly at the limit is still used. Pinned because
    # flipping this to `<` would silently re-fetch on every run at the boundary.
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _frame("boundary").to_parquet(cache_path, index=False)
    just_inside = time.time() - timedelta(days=30).total_seconds() + 60
    os.utime(cache_path, (just_inside, just_inside))
    calls: list[str] = []
    _stub_client(monkeypatch, calls)

    result = directory_module.load_directory(max_age_days=30)

    assert calls == []
    assert result["operatorLabel"].tolist() == ["boundary"]


def test_a_missing_cache_is_fetched_and_written(
    cache_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    _stub_client(monkeypatch, calls)
    assert not cache_path.exists()

    result = directory_module.load_directory()

    assert calls == ["fetched"]
    assert result["operatorLabel"].tolist() == ["from-api"]
    # Written for the next run, parent directory created on the way.
    assert cache_path.exists()
    assert pd.read_parquet(cache_path)["operatorLabel"].tolist() == ["from-api"]
