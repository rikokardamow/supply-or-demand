from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pipelines.weather import climatology_grid as climatology_grid_module


def test_build_region_grid_bounds_and_spacing() -> None:
    grid = climatology_grid_module.build_region_grid("eu", spacing_deg=10.0)

    assert set(grid.columns) == {"lat", "lon"}
    assert grid["lat"].min() == 35.0
    assert grid["lat"].max() == pytest.approx(55.0)  # last step <= 60 at spacing 10
    assert grid["lon"].min() == -10.0
    assert grid["lon"].max() == pytest.approx(30.0)


def test_build_region_grid_unknown_region_raises() -> None:
    with pytest.raises(KeyError):
        climatology_grid_module.build_region_grid("mars")


def test_climatology_grid_averages_across_years(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each grid point gets a fixed per-year temperature (year - 2000, e.g. 22.0 for
    2022) via a fake fetch_archive -- the mean across (2022, 2023, 2024) must be 23.0
    at every point, regardless of how many grid points there are."""
    monkeypatch.setattr(
        climatology_grid_module, "build_region_grid", lambda region: pd.DataFrame(
            [{"lat": 50.0, "lon": 10.0}, {"lat": 53.0, "lon": 13.0}]
        )
    )

    def _fake_fetch_archive(cities: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        year = start.year
        return pd.DataFrame({"city": cities["city"], "temp_mean_c": float(year - 2000)})

    monkeypatch.setattr(climatology_grid_module, "fetch_archive", _fake_fetch_archive)

    result = climatology_grid_module.climatology_grid("eu", date(2026, 9, 4))

    assert set(result.columns) == {"lat", "lon", "climatology_c"}
    assert len(result) == 2
    assert (result["climatology_c"] == 23.0).all()
