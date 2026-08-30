from __future__ import annotations

import pandas as pd
import pytest
from pipelines.gie.transforms import (
    country_deviation,
    days_to_full_or_empty,
    nearest_value_at_offset,
    net_flow,
)


def test_net_flow_is_injection_minus_withdrawal() -> None:
    injection = pd.Series([100.0, 200.0])
    withdrawal = pd.Series([30.0, 50.0])

    result = net_flow(injection, withdrawal)

    assert result.tolist() == [70.0, 150.0]


def test_days_to_full_hand_checked() -> None:
    # 100 TWh = 100,000 GWh working volume, 50% full -> 50,000 GWh remaining;
    # at +1,000 GWh/d net injection -> exactly 50 days to full.
    days, direction = days_to_full_or_empty(
        fill_pct=50.0, working_gas_volume_twh=100.0, avg_net_injection_gwh_per_day=1000.0
    )

    assert direction == "full"
    assert days == pytest.approx(50.0)


def test_days_to_empty_hand_checked() -> None:
    # 100 TWh, 30% full -> 30,000 GWh remaining to withdraw;
    # at -500 GWh/d net injection (i.e. withdrawing) -> exactly 60 days to empty.
    days, direction = days_to_full_or_empty(
        fill_pct=30.0, working_gas_volume_twh=100.0, avg_net_injection_gwh_per_day=-500.0
    )

    assert direction == "empty"
    assert days == pytest.approx(60.0)


def test_days_to_full_or_empty_zero_rate_returns_none() -> None:
    days, direction = days_to_full_or_empty(
        fill_pct=50.0, working_gas_volume_twh=100.0, avg_net_injection_gwh_per_day=0.0
    )

    assert days is None
    assert direction is None


def test_nearest_value_at_offset_finds_the_closest_real_observation() -> None:
    series = pd.Series(
        [10.0, 20.0, 30.0],
        index=pd.to_datetime(["2024-01-01", "2024-01-05", "2024-01-10"]),
    )

    result = nearest_value_at_offset(series, pd.Timestamp("2024-01-06"), tolerance_days=5)

    assert result == 20.0


def test_nearest_value_at_offset_returns_none_beyond_tolerance() -> None:
    series = pd.Series([10.0], index=pd.to_datetime(["2024-01-01"]))

    result = nearest_value_at_offset(series, pd.Timestamp("2024-06-01"), tolerance_days=5)

    assert result is None


def test_nearest_value_at_offset_returns_none_for_empty_series() -> None:
    result = nearest_value_at_offset(pd.Series(dtype=float), pd.Timestamp("2024-01-01"))

    assert result is None


def test_country_deviation_ranks_by_deviation_descending() -> None:
    # Same June-15th value every year 2018-2024 (skipping 2020) except the latest
    # (2025) point for each country, which deliberately differs — matches the
    # pattern already hand-checked in tests/test_eia_transforms.py.
    years = [2018, 2019, 2021, 2022, 2023, 2024, 2025]

    def _make_df(latest_value: float) -> pd.DataFrame:
        values = [50.0] * 6 + [latest_value]
        return pd.DataFrame(
            {"ts": pd.to_datetime([f"{y}-06-15" for y in years]), "value": values}
        )

    fill_by_country = {
        "DE": _make_df(70.0),  # +20 vs median
        "FR": _make_df(30.0),  # -20 vs median
        "NL": _make_df(50.0),  # 0 vs median
    }

    result = country_deviation(fill_by_country)

    assert result["geo"].tolist() == ["DE", "NL", "FR"]
    assert result.loc[result["geo"] == "DE", "deviation"].iloc[0] == pytest.approx(20.0)
    assert result.loc[result["geo"] == "FR", "deviation"].iloc[0] == pytest.approx(-20.0)
