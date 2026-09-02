from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.macro.fred_series import SeriesMeta
from pipelines.macro.pull_macro import pull_esi, pull_fred, pull_fx


class _FakeFREDClient:
    def __init__(self, series: dict[str, pd.DataFrame | Exception]) -> None:
        self._series = series

    def get_series(self, series_id: str) -> pd.DataFrame:
        result = self._series[series_id]
        if isinstance(result, Exception):
            raise result
        return result


def _fake_series(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"ts": pd.to_datetime(["2026-01-01", "2026-02-01"][: len(values)]), "value": values}
    )


def test_pull_fred_maps_known_series_to_ts_long(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pipelines.macro.pull_macro.FRED_SERIES",
        {"CPIAUCSL": SeriesMeta("Index 1982-1984=100", "M", "US")},
    )
    client = _FakeFREDClient({"CPIAUCSL": _fake_series([300.0, 301.0])})

    df = pull_fred(client, pd.Timestamp("2026-09-01"))

    validate_ts_long(df)
    assert (df["series_id"] == "fred.cpiaucsl").all()
    assert (df["unit"] == "Index 1982-1984=100").all()
    assert (df["geo"] == "US").all()
    assert (df["freq"] == "M").all()
    assert df["value"].tolist() == [300.0, 301.0]


def test_pull_fred_one_failing_series_does_not_abort_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pipelines.macro.pull_macro.FRED_SERIES",
        {
            "GOODSERIES": SeriesMeta("Percent", "D", "US"),
            "BADSERIES": SeriesMeta("Percent", "D", "US"),
        },
    )
    client = _FakeFREDClient(
        {"GOODSERIES": _fake_series([1.0]), "BADSERIES": ValueError("Bad Request.")}
    )

    df = pull_fred(client, pd.Timestamp("2026-09-01"))

    assert list(df["series_id"]) == ["fred.goodseries"]


class _FakeFrankfurterClient:
    def __init__(self, rates: pd.DataFrame) -> None:
        self._rates = rates

    def get_rates(self, start: date, end: date, symbols: list[str]) -> pd.DataFrame:
        return self._rates


def test_pull_fx_maps_rates_to_ts_long_with_usd_base_naming() -> None:
    rates = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-09-01", "2026-09-01"]),
            "currency": ["EUR", "GBP"],
            "rate": [0.86, 0.74],
        }
    )
    client = _FakeFrankfurterClient(rates)

    df = pull_fx(client, pd.Timestamp("2026-09-01"))

    validate_ts_long(df)
    assert set(df["series_id"]) == {"fx.usd_eur", "fx.usd_gbp"}
    assert set(df["geo"]) == {"EUR", "GBP"}
    assert set(df["unit"]) == {"EUR per USD", "GBP per USD"}


class _FakeEurostatESIClient:
    def __init__(self, esi: pd.DataFrame) -> None:
        self._esi = esi

    def get_esi(self, geos: list[str] | None = None) -> pd.DataFrame:
        return self._esi


def test_pull_esi_maps_to_ts_long_with_estat_prefix() -> None:
    esi = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2026-08-01", "2026-08-01"]),
            "geo": ["EU", "DE"],
            "value": [98.2, 94.1],
        }
    )
    client = _FakeEurostatESIClient(esi)

    df = pull_esi(client, pd.Timestamp("2026-09-01"))

    validate_ts_long(df)
    assert set(df["series_id"]) == {"estat.esi.EU", "estat.esi.DE"}
    assert (df["freq"] == "M").all()
