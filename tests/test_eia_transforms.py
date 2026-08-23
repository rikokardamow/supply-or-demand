from __future__ import annotations

import pandas as pd
import pytest
from pipelines.eia.transforms import days_of_cover, wpsr_summary


def test_days_of_cover_constant_product_supplied() -> None:
    dates = pd.date_range("2026-01-01", periods=6, freq="W")
    stocks = pd.Series([1000.0] * 6, index=dates)
    product_supplied = pd.Series([100.0] * 6, index=dates)

    result = days_of_cover(stocks, product_supplied)

    # rolling(4).mean() of a constant series equals the constant once warmed up
    assert result.iloc[-1] == 10.0


def test_days_of_cover_first_three_points_are_nan_before_4wk_window_fills() -> None:
    dates = pd.date_range("2026-01-01", periods=6, freq="W")
    stocks = pd.Series([1000.0] * 6, index=dates)
    product_supplied = pd.Series([100.0] * 6, index=dates)

    result = days_of_cover(stocks, product_supplied)

    assert result.iloc[:3].isna().all()


def test_wpsr_summary_computes_latest_prior_and_delta() -> None:
    df = pd.DataFrame(
        {
            "series_id": ["WCESTUS1", "WCESTUS1", "WPULEUS3", "WPULEUS3"],
            "ts": pd.to_datetime(
                ["2026-08-07", "2026-08-14", "2026-08-07", "2026-08-14"]
            ),
            "value": [400000.0, 420000.0, 96.2, 97.2],
        }
    )

    summary = wpsr_summary(df).set_index("series_id")

    assert summary.loc["WCESTUS1", "latest_value"] == 420000.0
    assert summary.loc["WCESTUS1", "prior_value"] == 400000.0
    assert summary.loc["WCESTUS1", "delta"] == 20000.0
    assert summary.loc["WPULEUS3", "delta"] == pytest.approx(1.0)
