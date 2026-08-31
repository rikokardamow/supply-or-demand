from __future__ import annotations

import pandas as pd
import pytest
from core.schemas import validate_ts_long
from pipelines.weather.degree_days import cdd, celsius_to_fahrenheit, hdd, to_ts_long


def test_hdd_matches_spec_worked_example() -> None:
    assert hdd(12.0, 18.0) == 6.0
    assert hdd(20.0, 18.0) == 0.0


def test_cdd_base_case() -> None:
    assert cdd(20.0, 18.0) == 2.0
    assert cdd(12.0, 18.0) == 0.0


def test_hdd_fahrenheit_base_case() -> None:
    assert hdd(50.0, 65.0) == 15.0  # 50F mean, base 65F -> HDD 15


def test_celsius_to_fahrenheit() -> None:
    assert celsius_to_fahrenheit(0.0) == 32.0
    assert celsius_to_fahrenheit(100.0) == 212.0


def test_to_ts_long_returns_ts_long_conformant_dataframe_both_bases() -> None:
    daily_df = pd.DataFrame(
        {
            "city": ["dublin", "dublin", "new_york", "new_york"],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-02"] * 2),
            "temp_mean_c": [12.0, 20.0, 10.0, 10.0],
        }
    )
    cities_df = pd.DataFrame({"city": ["dublin", "new_york"], "base": ["c18", "f65"]})
    revision_date = pd.Timestamp("2026-08-31")

    df = to_ts_long(daily_df, cities_df, revision_date)

    validate_ts_long(df)
    assert set(df["series_id"]) == {
        "hdd.dublin.c18",
        "cdd.dublin.c18",
        "hdd.new_york.f65",
        "cdd.new_york.f65",
    }

    dublin_hdd = df[df["series_id"] == "hdd.dublin.c18"].sort_values("ts")["value"].tolist()
    assert dublin_hdd == [6.0, 0.0]

    # 10C -> 50F, base 65F -> HDD 15 both days
    ny_hdd = df[df["series_id"] == "hdd.new_york.f65"].sort_values("ts")["value"].tolist()
    assert ny_hdd == [15.0, 15.0]


def test_to_ts_long_raises_on_unknown_city() -> None:
    daily_df = pd.DataFrame(
        {"city": ["atlantis"], "ts": pd.to_datetime(["2024-01-01"]), "temp_mean_c": [15.0]}
    )
    cities_df = pd.DataFrame({"city": ["dublin"], "base": ["c18"]})

    with pytest.raises(ValueError, match="atlantis"):
        to_ts_long(daily_df, cities_df, pd.Timestamp("2026-08-31"))
