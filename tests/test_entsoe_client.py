from __future__ import annotations

from datetime import date

import pytest
from pipelines.entsoe.client import ENTSOEClient


@pytest.mark.vcr
def test_get_day_ahead_prices_returns_raw_frame() -> None:
    client = ENTSOEClient()
    df = client.get_day_ahead_prices("DE_LU", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    assert set(df.columns) == {"ts", "value", "freq"}
    assert df["value"].dtype.kind == "f"
    # Real DE_LU day-ahead prices are plausible tens-to-low-hundreds EUR/MWh, not e.g.
    # accidentally left in some other unit or scale.
    assert 0 < df["value"].abs().median() < 1000
    # Confirmed live during planning: DE_LU is 15-minute resolution, not hourly.
    assert (df["freq"] == "15T").all()
    # ts must be tz-naive (entsoe-py returns a tz-aware, zone-local index — converted
    # to naive UTC before this point).
    assert df["ts"].dt.tz is None


@pytest.mark.vcr
def test_get_load_returns_raw_frame() -> None:
    client = ENTSOEClient()
    df = client.get_load("DE_LU", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    assert set(df.columns) == {"ts", "value", "freq"}
    # Real German load is tens of thousands of MW, not e.g. accidentally left in kW/GW.
    assert 10_000 < df["value"].median() < 200_000


@pytest.mark.vcr
def test_get_wind_and_solar_forecast_returns_long_frame_by_psr_type() -> None:
    client = ENTSOEClient()
    df = client.get_wind_and_solar_forecast("DE_LU", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    assert set(df.columns) == {"ts", "psr_type", "value", "freq"}
    # Confirmed live: DE_LU has all three PSR types.
    assert set(df["psr_type"]) == {"Solar", "Wind Onshore", "Wind Offshore"}


@pytest.mark.vcr
def test_get_generation_drops_actual_consumption_columns() -> None:
    client = ENTSOEClient()
    df = client.get_generation("DE_LU", date(2026, 8, 20), date(2026, 8, 22))

    assert not df.empty
    assert set(df.columns) == {"ts", "psr_type", "value", "freq"}
    # Hydro Pumped Storage has both "Actual Aggregated" (generation) and "Actual
    # Consumption" (charging demand) columns in the raw response — only the former
    # belongs in a generation mix. If get_generation ever regresses to keeping both,
    # this PSR type would appear duplicated with two different value series per ts.
    hydro_pumped = df[df["psr_type"] == "Hydro Pumped Storage"]
    assert hydro_pumped["ts"].is_unique


@pytest.mark.vcr
def test_get_crossborder_flow_returns_raw_frame() -> None:
    client = ENTSOEClient()
    df = client.get_crossborder_flow("DE_LU", "FR", date(2026, 8, 10), date(2026, 8, 12))

    assert not df.empty
    assert set(df.columns) == {"ts", "value", "freq"}
