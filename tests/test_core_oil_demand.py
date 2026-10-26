"""core/oil_demand.py -- the GDP elasticity of oil demand.

Every figure here is SYNTHETIC. The Bloomberg Intelligence workbook this module ports is
licensed, and none of its coefficients or panel values may appear in a tracked file.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core import oil_demand as od


def _monthly(start: str, periods: int, **columns: float) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="MS")
    return pd.DataFrame({name: float(value) for name, value in columns.items()}, index=index)


def _panel(n: int = 40, slope: float = 1.5, intercept: float = -2.0) -> pd.DataFrame:
    """An exact line through varying GDP growth: demand = intercept + slope * gdp."""
    index = pd.date_range("2013-01-01", periods=n, freq="QS")
    gdp = pd.Series(np.linspace(-1.0, 4.0, n), index=index)
    return pd.DataFrame({"demand_yoy": intercept + slope * gdp, "gdp_yoy": gdp})


# --- basket -----------------------------------------------------------------------


def test_the_euro_area_basket_is_nineteen_members_without_malta() -> None:
    """Malta has seven missing months and is 0.29 % of the sum. Kept in, the completeness
    rule discards eight quarters of panel; left out, none. Measured 2026-10-10."""
    assert len(od.EURO_AREA_BASKET) == 19
    assert "MT" not in od.EURO_AREA_BASKET
    assert od.BLOCKS == {"us": ("US",), "cn": ("CN",), "ea": od.EURO_AREA_BASKET}
    assert "ex Malta" in od.BLOCK_LABELS["ea"]


# --- quarterly aggregation --------------------------------------------------------


def test_quarterly_demand_is_the_mean_of_the_summed_members() -> None:
    monthly = _monthly("2025-01-01", 6, AA=100.0, BB=50.0)
    monthly.loc["2025-04-01":, "AA"] = [110.0, 120.0, 130.0]

    quarterly = od.quarterly_demand(monthly, ["AA", "BB"])

    assert quarterly.index.tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-04-01")]
    assert quarterly.iloc[0] == pytest.approx(150.0)
    assert quarterly.iloc[1] == pytest.approx(170.0)  # mean(160, 170, 180)


def test_a_quarter_with_any_member_missing_any_month_is_no_observation() -> None:
    """Summing the members that did report gives a smaller number that reads as a fall in
    demand. True of the live data today: the latest month lacks Croatia and Greece."""
    monthly = _monthly("2025-01-01", 6, AA=100.0, BB=50.0)
    monthly.loc["2025-05-01", "BB"] = np.nan

    quarterly = od.quarterly_demand(monthly, ["AA", "BB"])

    assert quarterly.loc["2025-01-01"] == pytest.approx(150.0)
    assert np.isnan(quarterly.loc["2025-04-01"])


def test_a_quarter_still_in_progress_is_no_observation() -> None:
    monthly = _monthly("2025-01-01", 4, AA=100.0)  # January to April: Q2 has one month

    quarterly = od.quarterly_demand(monthly, ["AA"])

    assert quarterly.loc["2025-01-01"] == pytest.approx(100.0)
    assert np.isnan(quarterly.loc["2025-04-01"])


def test_a_month_absent_from_the_index_altogether_counts_as_missing() -> None:
    monthly = _monthly("2025-01-01", 6, AA=100.0).drop(pd.Timestamp("2025-02-01"))

    quarterly = od.quarterly_demand(monthly, ["AA"])

    assert np.isnan(quarterly.loc["2025-01-01"])
    assert quarterly.loc["2025-04-01"] == pytest.approx(100.0)


def test_quarterly_demand_raises_for_a_member_with_no_series_at_all() -> None:
    with pytest.raises(ValueError, match="BB"):
        od.quarterly_demand(_monthly("2025-01-01", 3, AA=100.0), ["AA", "BB"])


def test_quarterly_demand_raises_on_an_empty_frame() -> None:
    with pytest.raises(ValueError, match="empty"):
        od.quarterly_demand(pd.DataFrame({"AA": []}, index=pd.DatetimeIndex([])), ["AA"])


# --- year-on-year -----------------------------------------------------------------


def test_yoy_pct_compares_with_the_same_quarter_a_year_earlier() -> None:
    index = pd.date_range("2024-01-01", periods=8, freq="QS")
    quarterly = pd.Series([100.0, 100.0, 100.0, 100.0, 110.0, 95.0, 100.0, 120.0], index=index)

    yoy = od.yoy_pct(quarterly)

    assert yoy.iloc[:4].isna().all()
    assert yoy.iloc[4:].tolist() == pytest.approx([10.0, -5.0, 0.0, 20.0])


def test_yoy_does_not_compare_across_a_missing_quarter() -> None:
    """With a quarter dropped from the index, a positional shift(4) would compare 2025-Q1
    with 2023-Q4. The gap must poison itself and the quarter a year later, nothing else."""
    index = pd.date_range("2023-01-01", periods=12, freq="QS")
    quarterly = pd.Series(100.0, index=index).drop(pd.Timestamp("2024-01-01"))

    yoy = od.yoy_pct(quarterly)

    assert np.isnan(yoy.loc["2024-01-01"])
    assert np.isnan(yoy.loc["2025-01-01"])
    assert yoy.loc["2025-04-01"] == pytest.approx(0.0)
    assert yoy.loc["2024-04-01"] == pytest.approx(0.0)


# --- the fit ----------------------------------------------------------------------


def test_fit_recovers_an_exact_line() -> None:
    fit = od.fit_elasticity(_panel(n=40, slope=1.5, intercept=-2.0))

    assert fit.slope == pytest.approx(1.5)
    assert fit.intercept == pytest.approx(-2.0)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.n == 40
    assert fit.start == pd.Timestamp("2013-01-01")
    assert fit.end == pd.Timestamp("2022-10-01")


def test_fit_refuses_a_short_panel() -> None:
    with pytest.raises(ValueError, match="19 overlapping quarters"):
        od.fit_elasticity(_panel(n=19))


def test_fit_refuses_a_regressor_with_no_variation() -> None:
    panel = _panel(n=30)
    panel["gdp_yoy"] = 2.0

    with pytest.raises(ValueError, match="does not vary"):
        od.fit_elasticity(panel)


def test_align_keeps_only_quarters_observed_on_both_sides() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="QS")
    demand = pd.Series([1.0, np.nan, 3.0, 4.0], index=index)
    gdp = pd.Series([2.0, 2.0, 2.0], index=index[:3])

    panel = od.align(demand, gdp)

    assert panel.index.tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-07-01")]
    assert list(panel.columns) == ["demand_yoy", "gdp_yoy"]


# --- the pandemic window ----------------------------------------------------------


def test_the_pandemic_window_covers_the_base_effect_year_too() -> None:
    assert (pd.Timestamp("2020-01-01"), pd.Timestamp("2021-10-01")) == od.PANDEMIC_WINDOW


def test_drop_window_removes_both_years_inclusive() -> None:
    panel = _panel(n=40)  # 2013-Q1 .. 2022-Q4

    kept = od.drop_window(panel, od.PANDEMIC_WINDOW)

    assert len(kept) == 32
    assert pd.Timestamp("2019-10-01") in kept.index
    assert pd.Timestamp("2020-01-01") not in kept.index
    assert pd.Timestamp("2021-10-01") not in kept.index
    assert pd.Timestamp("2022-01-01") in kept.index


def test_an_outlier_pair_inside_the_window_moves_the_full_fit_but_not_the_ex_pandemic_one() -> None:
    """The reason the second fit exists: one extreme pair can carry a slope."""
    panel = _panel(n=40, slope=1.0, intercept=0.0)
    panel.loc["2020-04-01"] = {"demand_yoy": -40.0, "gdp_yoy": -8.0}

    full = od.fit_elasticity(panel)
    ex = od.fit_elasticity(od.drop_window(panel, od.PANDEMIC_WINDOW))

    assert full.slope > 2.0
    assert ex.slope == pytest.approx(1.0)


# --- out of sample and the card ---------------------------------------------------


def test_out_of_sample_passes_when_the_relationship_holds_and_growth_moves() -> None:
    rng = np.random.default_rng(7)
    index = pd.date_range("2013-01-01", periods=48, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 48), index=index)
    panel = pd.DataFrame({"demand_yoy": 1.0 + 1.5 * gdp + rng.normal(0, 0.1, 48), "gdp_yoy": gdp})

    result = od.out_of_sample(panel, test_size=8)

    assert result["status"] == "pass"
    assert result["rmse_model"] < result["rmse_benchmark"]
    assert result["n_forecasts"] == 8
    assert 0 <= result["exceptions"] <= 8


def test_out_of_sample_fails_when_gdp_explains_nothing() -> None:
    """Demand that barely moves, against GDP that swings: "no change" beats the model."""
    rng = np.random.default_rng(11)
    index = pd.date_range("2013-01-01", periods=48, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 48), index=index)
    demand = pd.Series(np.linspace(0.0, 0.5, 48), index=index)
    demand.iloc[:30] += rng.normal(0, 6.0, 30)  # noisy history, calm test window
    panel = pd.DataFrame({"demand_yoy": demand, "gdp_yoy": gdp})

    assert od.out_of_sample(panel, test_size=8)["status"] == "fail"


def test_out_of_sample_refuses_when_it_cannot_hold_out_the_test_window() -> None:
    with pytest.raises(ValueError, match="hold out"):
        od.out_of_sample(_panel(n=27), test_size=8)


def test_model_card_carries_every_field_the_conventions_require() -> None:
    rng = np.random.default_rng(3)
    index = pd.date_range("2013-01-01", periods=54, freq="QS")
    gdp = pd.Series(rng.normal(2.0, 2.0, 54), index=index)
    panel = pd.DataFrame({"demand_yoy": 1.5 * gdp + rng.normal(0, 0.5, 54), "gdp_yoy": gdp})

    card = od.model_card(panel, as_of=pd.Timestamp("2026-10-10"))

    for field in (
        "estimation_start", "estimation_end", "last_refit", "oos_status", "benchmark",
        "exceptions", "break_date", "fit", "fit_ex_pandemic", "pandemic_window",
    ):  # fmt: skip
        assert field in card, field
    assert card["estimation_start"] == pd.Timestamp("2013-01-01")
    assert card["last_refit"] == pd.Timestamp("2026-10-10")
    assert card["benchmark"] == od.BENCHMARK
    assert card["fit"].n == 54
    assert card["fit_ex_pandemic"].n == 46


# --- the scenario -----------------------------------------------------------------


def test_project_demand_yoy_applies_the_fitted_line_to_assumed_growth() -> None:
    fit = od.fit_elasticity(_panel(n=40, slope=1.5, intercept=-2.0))
    assumed = pd.Series([0.0, 2.0], index=pd.to_datetime(["2027-01-01", "2027-04-01"]))

    projected = od.project_demand_yoy(fit, assumed)

    assert projected.tolist() == pytest.approx([-2.0, 1.0])
    assert projected.index.equals(assumed.index)
