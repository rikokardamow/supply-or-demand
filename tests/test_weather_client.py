from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from pipelines.weather.client import fetch_archive, fetch_forecast

_CITIES = pd.DataFrame(
    {
        "city": ["dublin", "new_york"],
        "lat": [53.35, 40.71],
        "lon": [-6.26, -74.01],
        "base": ["c18", "f65"],
    }
)


@pytest.mark.vcr
def test_fetch_forecast_returns_one_row_per_city_per_day() -> None:
    df = fetch_forecast(_CITIES, days=3)

    assert set(df["city"]) == {"dublin", "new_york"}
    assert len(df) == 2 * 3
    assert {"ts", "temp_mean_c", "temp_min_c", "temp_max_c", "wind_max_kmh"}.issubset(df.columns)


@pytest.mark.vcr
def test_fetch_archive_returns_real_history_for_a_known_range_in_input_order() -> None:
    df = fetch_archive(_CITIES, date(2024, 1, 1), date(2024, 1, 5))

    assert len(df) == 2 * 5
    dublin = df[df["city"] == "dublin"].sort_values("ts")
    assert dublin["ts"].iloc[0] == pd.Timestamp("2024-01-01")
    assert dublin["ts"].iloc[-1] == pd.Timestamp("2024-01-05")
