from __future__ import annotations

import pandas as pd
import pytest
import xarray as xr
from pipelines.weather import gfs_degree_days


def _fake_ds(temp_k: float) -> xr.Dataset:
    t2m = xr.DataArray(
        data=[[temp_k]],
        dims=("latitude", "longitude"),
        coords={"latitude": [53.35], "longitude": [-6.26]},
    )
    return xr.Dataset(
        {"t2m": t2m},
        coords={"valid_time": pd.Timestamp("2026-09-07T00:00:00")},
    )


def test_sample_cities_extracts_temp_and_valid_time_for_the_requested_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cities_df = pd.DataFrame(
        {
            "city": ["dublin", "new_york"],
            "lat": [53.35, 40.71],
            "lon": [-6.26, -74.01],
            "base": ["c18", "f65"],
        }
    )
    calls: list[str] = []

    def fake_fetch(region: str, step_hours: int = 72) -> tuple[str, object]:
        calls.append(region)
        return "fake-path", object()

    monkeypatch.setattr(gfs_degree_days, "fetch_2t_forecast", fake_fetch)
    monkeypatch.setattr(gfs_degree_days, "load_2t_dataset", lambda path: _fake_ds(293.15))

    result = gfs_degree_days.sample_cities(cities_df, base="c18")

    assert calls == ["eu"]  # c18 (EU base) maps to gfs_client's "eu" region, not "conus"
    assert list(result["city"]) == ["dublin"]
    assert result["ts"].iloc[0] == pd.Timestamp("2026-09-07T00:00:00")
    assert result["temp_mean_c"].iloc[0] == pytest.approx(20.0)  # 293.15K -> 20.0C


def test_sample_cities_maps_us_base_to_conus_region(monkeypatch: pytest.MonkeyPatch) -> None:
    cities_df = pd.DataFrame(
        {"city": ["new_york"], "lat": [40.71], "lon": [-74.01], "base": ["f65"]}
    )
    calls: list[str] = []

    def fake_fetch(region: str, step_hours: int = 72) -> tuple[str, object]:
        calls.append(region)
        return "fake-path", object()

    monkeypatch.setattr(gfs_degree_days, "fetch_2t_forecast", fake_fetch)
    monkeypatch.setattr(gfs_degree_days, "load_2t_dataset", lambda path: _fake_ds(283.15))

    gfs_degree_days.sample_cities(cities_df, base="f65")

    assert calls == ["conus"]
