# tests/test_oecd_client.py
from __future__ import annotations

import pandas as pd
import pytest
from pipelines.oecd import client

_HEADER = (
    "DATAFLOW,FREQ,ADJUSTMENT,REF_AREA,SECTOR,COUNTERPART_SECTOR,TRANSACTION,INSTR_ASSET,"
    "ACTIVITY,EXPENDITURE,UNIT_MEASURE,PRICE_BASE,TRANSFORMATION,TABLE_IDENTIFIER,"
    "TIME_PERIOD,OBS_VALUE,REF_YEAR_PRICE,BASE_PER,CONF_STATUS,DECIMALS,OBS_STATUS,"
    "UNIT_MULT,CURRENCY\n"
)


def _line(area: str, period: str, value: str) -> str:
    return (
        f"OECD.SDD.NAD:DSD_NAMAIN1@DF_QNA(1.1),Q,Y,{area},S1,S1,B1GQ,_Z,_Z,_Z,PC,L,GY,"
        f"T0102,{period},{value},,,F,1,A,0,_Z\n"
    )


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise client.requests.HTTPError(f"{self.status_code}")


def test_the_key_asks_for_seasonally_adjusted_real_growth_on_a_year_earlier() -> None:
    """Q = quarterly, Y = seasonally adjusted, B1GQ = GDP, L = chain-linked volume (real),
    GY = growth on the same quarter a year earlier. Read off a live response 2026-10-10."""
    assert client.real_gdp_growth_key(["CHN", "USA", "EA"]) == "Q.Y.CHN+USA+EA...B1GQ.....L.GY."


def test_fetch_parses_the_sdmx_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_get(url: str, params: dict[str, str], timeout: int) -> _FakeResponse:
        seen["url"] = url
        seen["params"] = params
        return _FakeResponse(
            _HEADER + _line("CHN", "2026-Q1", "5") + _line("CHN", "2026-Q2", "4.3")
        )

    monkeypatch.setattr(client.requests, "get", fake_get)

    df = client.fetch_real_gdp_growth(["CHN"], start_period="2026-Q1")

    assert seen["url"] == f"{client.BASE_URL}/Q.Y.CHN...B1GQ.....L.GY."
    assert seen["params"] == {"startPeriod": "2026-Q1", "format": "csvfile"}
    assert list(df.columns) == ["REF_AREA", "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"]
    assert df["OBS_VALUE"].tolist() == [5.0, 4.3]
    assert pd.api.types.is_float_dtype(df["OBS_VALUE"])


def test_a_requested_area_missing_from_the_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EA19 beside CHN returns HTTP 200 and just leaves EA19 out -- confirmed live. Without
    this check the euro area vanishes from the lake and nothing fails."""
    monkeypatch.setattr(
        client.requests,
        "get",
        lambda url, params, timeout: _FakeResponse(_HEADER + _line("CHN", "2026-Q2", "4.3")),
    )

    with pytest.raises(ValueError, match="EA19"):
        client.fetch_real_gdp_growth(["CHN", "EA19"])


def test_a_response_that_is_not_the_expected_csv_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        client.requests, "get", lambda url, params, timeout: _FakeResponse("<html>busy</html>")
    )

    with pytest.raises(ValueError, match="REF_AREA"):
        client.fetch_real_gdp_growth(["CHN"])


@pytest.mark.vcr
def test_fetch_real_gdp_growth_live_shape() -> None:
    """Recorded once against the real service. Pins the three area codes the model uses --
    above all that the euro area is `EA`."""
    df = client.fetch_real_gdp_growth(["CHN", "USA", "EA"], start_period="2024-Q1")

    assert set(df["REF_AREA"]) == {"CHN", "USA", "EA"}
    assert df["TIME_PERIOD"].str.fullmatch(r"\d{4}-Q[1-4]").all()
    assert df["OBS_VALUE"].between(-30, 30).all(), "a growth rate, not a level"
    assert not df.duplicated(["REF_AREA", "TIME_PERIOD"]).any()
