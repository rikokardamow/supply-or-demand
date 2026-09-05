from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from pipelines.futures.client import ContractMeta, IBKRClient, ManualCSVClient

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "futures"


def test_manual_csv_client_reads_the_synthetic_fixture() -> None:
    """tests/fixtures/futures/settles_synthetic.csv is clearly-labelled synthetic data
    (see its own filename and pipelines/futures/NOTES.md) -- not real market settlements."""
    client = ManualCSVClient(data_dir=FIXTURE_DIR)

    contracts = client.list_contracts("cl")
    assert {c.contract for c in contracts} == {"z2026", "f2027"}
    z2026 = next(c for c in contracts if c.contract == "z2026")
    assert z2026.expiry == date(2026, 11, 20)
    assert z2026.tick_size == pytest.approx(0.01)
    assert z2026.contract_unit == "1000 bbl"
    assert z2026.currency == "USD"

    settles = client.get_settles(
        "cl", ["z2026", "f2027"], date(2026, 8, 1), date(2026, 8, 3)
    )
    assert len(settles) == 6
    assert set(settles.columns) == {"date", "root", "contract", "settle", "oi", "volume"}
    z2026_settles = settles[settles["contract"] == "z2026"].sort_values("date")
    assert z2026_settles["settle"].tolist() == [61.35, 61.72, 62.10]


def test_manual_csv_client_returns_empty_for_a_root_with_no_data() -> None:
    client = ManualCSVClient(data_dir=FIXTURE_DIR)
    assert client.list_contracts("ng") == []


def test_manual_csv_client_rejects_duplicate_date_root_contract_rows(tmp_path: Path) -> None:
    duplicate_csv = tmp_path / "settles_20260801.csv"
    duplicate_csv.write_text(
        "date,root,contract,settle,oi,volume,expiry\n"
        "2026-08-01,cl,z26,61.35,125000,180000,2026-11-20\n"
        "2026-08-01,cl,z26,61.40,125100,180500,2026-11-20\n"
    )
    client = ManualCSVClient(data_dir=tmp_path)

    with pytest.raises(ValueError, match="duplicate"):
        client.list_contracts("cl")


def test_manual_csv_client_allows_the_same_contract_code_across_different_roots(
    tmp_path: Path,
) -> None:
    """Real, confirmed-live gotcha: contract codes are month+year only (e.g. "z2026"),
    shared across every root trading that expiry cycle -- cl/z26 and ng/z26 on the
    same real date are both genuinely valid rows, not a duplicate. An earlier version
    of _validate keyed only on (date, contract) and would have wrongly rejected this."""
    csv = tmp_path / "settles_20260801.csv"
    csv.write_text(
        "date,root,contract,settle,oi,volume,expiry\n"
        "2026-08-01,cl,z26,61.35,125000,180000,2026-11-20\n"
        "2026-08-01,ng,z26,3.15,98000,60000,2026-11-24\n"
    )
    client = ManualCSVClient(data_dir=tmp_path)

    assert len(client.list_contracts("cl")) == 1
    assert len(client.list_contracts("ng")) == 1


def test_manual_csv_client_rejects_the_same_date_written_two_different_ways(
    tmp_path: Path,
) -> None:
    """Date parsing must happen BEFORE the duplicate check, not after -- otherwise two
    rows for the same real calendar day written as different strings across separate
    drops (a corrected re-drop, say) would slip past the string-level comparison."""
    csv = tmp_path / "settles_20260801.csv"
    csv.write_text(
        "date,root,contract,settle,oi,volume,expiry\n"
        "2026-08-01,cl,z26,61.35,125000,180000,2026-11-20\n"
        "2026-8-1,cl,z26,61.40,125100,180500,2026-11-20\n"
    )
    client = ManualCSVClient(data_dir=tmp_path)

    with pytest.raises(ValueError, match="duplicate"):
        client.list_contracts("cl")


def test_manual_csv_client_lowercases_contract_codes(tmp_path: Path) -> None:
    """An operator's hand-typed CSV isn't guaranteed to use lowercase contract codes
    the way IBKRClient.list_contracts already normalises -- ManualCSVClient must match,
    or a mixed-case code breaks the lake's lowercase-dotted series_id convention."""
    csv = tmp_path / "settles_20260801.csv"
    csv.write_text(
        "date,root,contract,settle,oi,volume,expiry\n"
        "2026-08-01,cl,Z26,61.35,125000,180000,2026-11-20\n"
    )
    client = ManualCSVClient(data_dir=tmp_path)

    contracts = client.list_contracts("cl")
    assert contracts[0].contract == "z26"

    settles = client.get_settles("cl", ["z26"], date(2026, 8, 1), date(2026, 8, 1))
    assert settles.iloc[0]["contract"] == "z26"


def test_manual_csv_client_rejects_non_numeric_settle(tmp_path: Path) -> None:
    bad_csv = tmp_path / "settles_20260801.csv"
    bad_csv.write_text(
        "date,root,contract,settle,oi,volume,expiry\n"
        "2026-08-01,cl,z26,not-a-number,125000,180000,2026-11-20\n"
    )
    client = ManualCSVClient(data_dir=tmp_path)

    with pytest.raises(ValueError, match="numeric"):
        client.list_contracts("cl")


class _FakeContractDetails:
    def __init__(self, local_symbol: str, expiry: str) -> None:
        self.contract = _FakeContract(local_symbol, expiry)


class _FakeContract:
    def __init__(self, local_symbol: str, expiry: str) -> None:
        self.localSymbol = local_symbol
        self.lastTradeDateOrContractMonth = expiry


class _FakeBar:
    def __init__(self, bar_date: date, close: float, volume: float) -> None:
        self.date = bar_date
        self.close = close
        self.volume = volume


class _FakeIB:
    """Mocks ib_async.IB entirely -- no live gateway needed or assumed, same established
    pattern as tests/test_weather_ecmwf_client.py's _FakeClient."""

    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False

    def connect(
        self, host: str, port: int, clientId: int, timeout: float  # noqa: N803
    ) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def reqContractDetails(  # noqa: N802 -- mirrors ib_async.IB's own real method name
        self, contract: object
    ) -> list[_FakeContractDetails]:
        return [_FakeContractDetails("Z26", "20261120")]

    def reqHistoricalData(  # noqa: N802 -- mirrors ib_async.IB's own real method name
        self, contract: object, **kwargs: object
    ) -> list[_FakeBar]:
        return [_FakeBar(date(2026, 8, 1), 61.35, 180000.0)]


def test_ibkr_client_against_a_mocked_interface(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ib = _FakeIB()
    monkeypatch.setattr("ib_async.IB", lambda: fake_ib)

    client = IBKRClient(host="127.0.0.1", port=7497, client_id=1)
    contracts = client.list_contracts("cl")

    assert fake_ib.connected
    assert fake_ib.disconnected
    assert len(contracts) == 1
    assert contracts[0] == ContractMeta(
        root="cl",
        contract="z26",
        expiry=date(2026, 11, 20),
        tick_size=0.01,
        contract_unit="1000 bbl",
        currency="USD",
    )

    fake_ib.connected = False
    fake_ib.disconnected = False
    settles = client.get_settles("cl", ["z26"], date(2026, 8, 1), date(2026, 8, 1))
    assert fake_ib.connected
    assert fake_ib.disconnected
    assert len(settles) == 1
    assert settles.iloc[0]["settle"] == 61.35
    assert pd.isna(settles.iloc[0]["oi"])  # reqHistoricalData bars carry no open interest
