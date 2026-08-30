from __future__ import annotations

from datetime import date

import pytest
from pipelines.eirgrid.client import EirGridClient


@pytest.mark.vcr
def test_get_series_returns_raw_frame_for_demand() -> None:
    client = EirGridClient()
    df = client.get_series("demandactual", "ROI", date(2026, 8, 20), date(2026, 8, 21))

    assert not df.empty
    assert set(df.columns) == {"ts", "field_name", "value"}
    assert (df["field_name"] == "SYSTEM_DEMAND").all()
    # Real ROI demand is thousands of MW, not e.g. accidentally left in kW.
    assert 1000 < df["value"].median() < 10000
    assert df["ts"].dt.tz is None


@pytest.mark.vcr
def test_get_series_returns_multiple_fields_for_interconnection() -> None:
    client = EirGridClient()
    df = client.get_series("interconnection", "ROI", date(2026, 8, 20), date(2026, 8, 21))

    assert not df.empty
    assert set(df["field_name"]) == {"INTER_EWIC", "INTER_GRNLK", "INTER_NET_ROI"}


@pytest.mark.vcr
def test_get_series_raises_on_invalid_area() -> None:
    client = EirGridClient()
    with pytest.raises(ValueError, match="Invalid Area"):
        client.get_series("solaractual", "ROI", date(2026, 8, 20), date(2026, 8, 21))
