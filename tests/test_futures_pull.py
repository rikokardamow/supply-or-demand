from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from core.storage import read_ts_long
from pipelines.futures.client import ContractMeta
from pipelines.futures.pull import pull_root
from pipelines.futures.pull_daily import trailing_window
from pipelines.futures.series_meta import read_series_meta


def test_trailing_window_covers_exactly_n_calendar_days_including_today() -> None:
    today = date(2026, 9, 4)
    start = trailing_window(today, trailing_days=5)

    assert start == date(2026, 8, 31)  # Aug 31 .. Sep 4 inclusive = 5 days, not 6

_CONTRACT = ContractMeta(
    root="cl", contract="z26", expiry=date(2026, 11, 20),
    tick_size=0.01, contract_unit="1000 bbl", currency="USD",
)


@pytest.fixture(autouse=True)
def _isolated_lake(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EIA_API_KEY", "placeholder")
    monkeypatch.setenv("EMBER_API_KEY", "placeholder")
    monkeypatch.setenv("GIE_API_KEY", "placeholder")
    monkeypatch.setenv("ENTSOE_API_KEY", "placeholder")
    monkeypatch.setenv("FRED_API_KEY", "placeholder")


class _FakeClient:
    def __init__(self, contracts: list[ContractMeta], settles: pd.DataFrame) -> None:
        self._contracts = contracts
        self._settles = settles

    def list_contracts(self, root: str) -> list[ContractMeta]:
        return [c for c in self._contracts if c.root == root]

    def get_settles(
        self, root: str, contracts: list[str], start: date, end: date
    ) -> pd.DataFrame:
        return self._settles[self._settles["root"] == root].reset_index(drop=True)


def test_pull_root_writes_series_meta_and_ts_long_tagged_with_the_real_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pipelines.futures.pull.settings.futures_source", "manual")
    settles = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-08-01"]),
            "root": ["cl"],
            "contract": ["z26"],
            "settle": [61.35],
            "oi": [125000],
            "volume": [180000],
        }
    )
    client = _FakeClient([_CONTRACT], settles)

    rows_written = pull_root(client, "cl", date(2026, 8, 1), date(2026, 8, 1), pd.Timestamp.now())

    assert rows_written == 3  # settle + oi + volume
    meta = read_series_meta()
    assert meta.iloc[0]["source"] == "manual"
    lake_rows = read_ts_long(series_ids=["fut.cl.z26.settle"])
    assert lake_rows.iloc[0]["source"] == "manual"
    assert lake_rows.iloc[0]["value"] == pytest.approx(61.35)


def test_pull_root_returns_zero_for_a_root_with_no_contracts() -> None:
    empty = pd.DataFrame(columns=["date", "root", "contract", "settle", "oi", "volume"])
    client = _FakeClient([], empty)

    assert pull_root(client, "cl", date(2026, 8, 1), date(2026, 8, 1), pd.Timestamp.now()) == 0
