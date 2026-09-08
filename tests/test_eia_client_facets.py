from __future__ import annotations

from typing import Any

import pytest
from core.schemas import validate_flows, validate_ts_long
from pipelines.eia.client import EIAClient


def _fake_rows() -> list[dict[str, Any]]:
    return [
        {"period": "2026-09-01T00", "respondent": "ERCO", "type": "D",
         "value": 45000, "value-units": "megawatthours"},
        {"period": "2026-09-01T01", "respondent": "ERCO", "type": "D",
         "value": None, "value-units": "megawatthours"},
        {"period": "2026-09-01T01", "respondent": "PJM", "type": "D",
         "value": 88000, "value-units": "megawatthours"},
    ]


def test_get_facet_series_builds_ts_long_and_drops_null_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = EIAClient(api_key="test")
    monkeypatch.setattr(EIAClient, "_fetch_facet_rows", lambda *a, **k: _fake_rows())

    df = client.get_facet_series(
        route="electricity/rto/region-data",
        data_key="value",
        facets={"respondent": ["ERCO", "PJM"], "type": ["D"]},
        frequency="hourly",
        series_id=lambda row: f"RTO.REGION.{row['respondent']}.{row['type']}.H",
        geo=lambda row: str(row["respondent"]),
    )

    validate_ts_long(df)
    # The null-value row must be dropped, not turned into NaN and not crash float().
    assert len(df) == 2
    assert list(df["series_id"]) == ["RTO.REGION.ERCO.D.H", "RTO.REGION.PJM.D.H"]
    assert set(df["geo"]) == {"ERCO", "PJM"}
    assert set(df["unit"]) == {"megawatthours"}
    assert set(df["source"]) == {"eia"}
    # A dropped row must be reported, never swallowed -- the convention every other
    # fetcher in this client follows.
    assert "dropped 1 row" in capsys.readouterr().out


def test_get_facet_flows_builds_flows_rows_from_fromba_toba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = EIAClient(api_key="test")
    monkeypatch.setattr(
        EIAClient,
        "_fetch_facet_rows",
        lambda *a, **k: [
            {"period": "2026-09-01T00", "fromba": "ERCO", "toba": "SWPP",
             "value": 120, "value-units": "megawatthours"},
            {"period": "2026-09-01T01", "fromba": "ERCO", "toba": "SWPP",
             "value": None, "value-units": "megawatthours"},
        ],
    )

    df = client.get_facet_flows(
        route="electricity/rto/interchange-data",
        data_key="value",
        facets={"fromba": ["ERCO"]},
        frequency="hourly",
        mode="grid_interchange",
    )

    validate_flows(df)
    assert len(df) == 1
    assert df["from_node"].iloc[0] == "ERCO"
    assert df["to_node"].iloc[0] == "SWPP"
    assert df["mode"].iloc[0] == "grid_interchange"


def test_fetch_facet_rows_sends_one_repeated_param_per_facet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The whole point of this method: an arbitrary facet dict becomes facets[<name>][]
    # params. get_operational_series hardcodes three facet names and cannot express
    # respondent+type or fromba+toba at all.
    captured: dict[str, Any] = {}

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"response": {"data": []}}

    def _fake_get(url: str, params: dict[str, Any], timeout: int) -> _Resp:
        captured.update(params)
        return _Resp()

    monkeypatch.setattr("pipelines.eia.client.requests.get", _fake_get)

    EIAClient(api_key="test")._fetch_facet_rows(
        route="electricity/rto/region-data",
        data_key="value",
        facets={"respondent": ["ERCO", "PJM"], "type": ["D"]},
        frequency="hourly",
        start="2026-09-01T00",
        end="2026-09-02T00",
    )

    assert captured["facets[respondent][]"] == ["ERCO", "PJM"]
    assert captured["facets[type][]"] == ["D"]
    assert captured["data[0]"] == "value"
    assert captured["start"] == "2026-09-01T00"
    assert captured["end"] == "2026-09-02T00"
