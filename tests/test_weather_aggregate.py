from __future__ import annotations

import pandas as pd
import pytest
from pipelines.weather.aggregate import population_weighted


def test_population_weighted_matches_hand_computed_sum() -> None:
    long_df = pd.DataFrame(
        {
            "series_id": ["hdd.dublin.c18", "hdd.london.c18", "hdd.dublin.c18", "hdd.london.c18"],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"]),
            "value": [10.0, 20.0, 5.0, 15.0],
        }
    )
    cities_df = pd.DataFrame(
        {"city": ["dublin", "london"], "base": ["c18", "c18"], "population_weight": [0.3, 0.7]}
    )

    result = population_weighted(long_df, cities_df, "hdd", pd.Timestamp("2026-08-31"))

    assert set(result["series_id"]) == {"hdd.eu.popw"}
    day1 = result.loc[result["ts"] == pd.Timestamp("2024-01-01"), "value"].iloc[0]
    assert day1 == pytest.approx(10.0 * 0.3 + 20.0 * 0.7)


def test_population_weighted_separates_eu_and_us_regions() -> None:
    long_df = pd.DataFrame(
        {
            "series_id": ["hdd.dublin.c18", "hdd.new_york.f65"],
            "ts": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            "value": [10.0, 15.0],
        }
    )
    cities_df = pd.DataFrame(
        {"city": ["dublin", "new_york"], "base": ["c18", "f65"], "population_weight": [1.0, 1.0]}
    )

    result = population_weighted(long_df, cities_df, "hdd", pd.Timestamp("2026-08-31"))

    assert set(result["series_id"]) == {"hdd.eu.popw", "hdd.us.popw"}


def test_population_weighted_returns_empty_frame_for_missing_metric() -> None:
    long_df = pd.DataFrame(
        {"series_id": ["cdd.dublin.c18"], "ts": pd.to_datetime(["2024-01-01"]), "value": [1.0]}
    )
    cities_df = pd.DataFrame({"city": ["dublin"], "base": ["c18"], "population_weight": [1.0]})

    result = population_weighted(long_df, cities_df, "hdd", pd.Timestamp("2026-08-31"))

    assert result.empty
