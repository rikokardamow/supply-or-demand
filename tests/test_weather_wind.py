from __future__ import annotations

import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.weather.wind import wind_forecast_to_ts_long


def test_wind_forecast_to_ts_long_returns_ts_long_conformant_dataframe() -> None:
    daily_df = pd.DataFrame(
        {
            "city": ["berlin", "berlin", "copenhagen", "copenhagen"],
            "ts": pd.to_datetime(["2026-09-04", "2026-09-05"] * 2),
            "wind_max_kmh": [18.5, 22.0, 30.1, 28.4],
        }
    )
    locations_df = pd.DataFrame({"city": ["berlin", "copenhagen"], "country": ["DE", "DK"]})
    revision_date = pd.Timestamp("2026-09-01")

    df = wind_forecast_to_ts_long(daily_df, locations_df, revision_date)

    validate_ts_long(df)
    assert set(df["series_id"]) == {"wind.de.10m_max_kmh", "wind.dk.10m_max_kmh"}
    assert set(df["geo"]) == {"DE", "DK"}
    assert (df["unit"] == "km/h").all()

    de_values = df[df["series_id"] == "wind.de.10m_max_kmh"].sort_values("ts")["value"].tolist()
    assert de_values == [18.5, 22.0]


def test_wind_forecast_to_ts_long_raises_on_unknown_city() -> None:
    daily_df = pd.DataFrame(
        {"city": ["atlantis"], "ts": pd.to_datetime(["2026-09-04"]), "wind_max_kmh": [15.0]}
    )
    locations_df = pd.DataFrame({"city": ["berlin"], "country": ["DE"]})

    with pytest.raises(ValueError, match="atlantis"):
        wind_forecast_to_ts_long(daily_df, locations_df, pd.Timestamp("2026-09-01"))
