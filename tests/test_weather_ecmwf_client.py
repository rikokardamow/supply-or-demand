from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from pipelines.weather import ecmwf_client


class _FakeResult:
    def __init__(self, run_datetime: datetime) -> None:
        self.datetime = run_datetime


class _FakeClient:
    def __init__(self, latest_datetime: datetime) -> None:
        self._latest_datetime = latest_datetime
        self.retrieve_calls = 0

    def latest(self, **kwargs: object) -> datetime:
        return self._latest_datetime

    def retrieve(self, target: str, **kwargs: object) -> _FakeResult:
        self.retrieve_calls += 1
        Path(target).write_bytes(b"fake grib bytes")
        return _FakeResult(self._latest_datetime)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ecmwf_client, "CACHE_DIR", tmp_path)


def test_fetch_2t_forecast_downloads_once_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeClient(datetime(2026, 9, 1, 0, 0))
    monkeypatch.setattr(ecmwf_client, "Client", lambda source: fake_client)

    path1 = ecmwf_client.fetch_2t_forecast()
    path2 = ecmwf_client.fetch_2t_forecast()

    assert path1 == path2
    assert path1.read_bytes() == b"fake grib bytes"
    # Second call should be a cache hit -- only one real retrieve.
    assert fake_client.retrieve_calls == 1


def test_fetch_2t_forecast_refetches_on_a_new_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeClient(datetime(2026, 9, 1, 0, 0))
    monkeypatch.setattr(ecmwf_client, "Client", lambda source: fake_client)
    ecmwf_client.fetch_2t_forecast()

    fake_client._latest_datetime = datetime(2026, 9, 1, 12, 0)
    path2 = ecmwf_client.fetch_2t_forecast()

    assert path2.name == "ifs-2t-20260901T1200.grib2"
    assert fake_client.retrieve_calls == 2
