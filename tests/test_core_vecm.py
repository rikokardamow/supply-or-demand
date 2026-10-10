from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core.vecm import (
    fit_vecm,
    forecast_eval,
    granger,
    johansen,
    model_card,
    select_lag_order,
    structural_break,
    to_monthly,
    unit_root_tests,
)


def _monthly_index(n: int, start: str = "1993-01-31") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="BME")


def _cointegrated(n: int = 300, beta: float = 0.16, seed: int = 0) -> pd.DataFrame:
    """y1 = beta*y2 + noise, y2 a random walk -- so y1 - beta*y2 is stationary and the
    pair is cointegrated with rank 1 by construction."""
    rng = np.random.default_rng(seed)
    y2 = np.cumsum(rng.normal(0, 1, n))
    y1 = beta * y2 + rng.normal(0, 0.05, n)
    return pd.DataFrame({"y1": y1, "y2": y2}, index=_monthly_index(n))


def _independent_random_walks(n: int = 300, seed: int = 7) -> pd.DataFrame:
    """Two unrelated I(1) series -- no cointegration, nothing for a VECM to exploit."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {"y1": np.cumsum(rng.normal(0, 1, n)), "y2": np.cumsum(rng.normal(0, 1, n))},
        index=_monthly_index(n),
    )


# --- monthly aggregation ----------------------------------------------------------


def test_to_monthly_takes_the_last_business_day_of_each_month() -> None:
    """The paper is monthly; Spec 20 fixes the aggregation as the last business day.

    January 2026 has exactly 22 business days, the last being Friday 30 January.
    """
    daily = pd.Series(range(1, 23), index=pd.bdate_range("2026-01-01", periods=22)).astype(float)
    monthly = to_monthly(daily)
    assert monthly.index[-1] == pd.Timestamp("2026-01-30")
    assert monthly.iloc[-1] == pytest.approx(22.0)


def test_to_monthly_drops_a_weekend_dated_observation() -> None:
    """31 Jan 2026 is a Saturday, so it is not a business-day print and must not become
    the January value. Left in, `resample("BME")` would push it past January's anchor
    and silently report it as a *February* observation."""
    daily = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-01-30", "2026-01-31"]))
    monthly = to_monthly(daily)
    assert monthly.index.tolist() == [pd.Timestamp("2026-01-30")]
    assert monthly.iloc[-1] == pytest.approx(1.0)


# --- unit roots -------------------------------------------------------------------


def test_unit_root_tests_call_a_random_walk_i1() -> None:
    rng = np.random.default_rng(3)
    y = pd.Series(np.cumsum(rng.normal(0, 1, 300)), index=_monthly_index(300))
    result = unit_root_tests(y)
    assert result["i1"] is True
    assert result["level"]["adf_p"] > 0.05  # cannot reject a unit root in the level
    assert result["diff"]["adf_p"] < 0.05  # can reject one in the difference


def test_unit_root_tests_do_not_call_white_noise_i1() -> None:
    rng = np.random.default_rng(4)
    y = pd.Series(rng.normal(0, 1, 300), index=_monthly_index(300))
    result = unit_root_tests(y)
    assert result["i1"] is False
    assert result["level"]["adf_p"] < 0.05


def test_unit_root_tests_report_all_three_tests() -> None:
    """ADF, Phillips-Perron and KPSS, per the spec -- PP is the reason `arch` is a
    dependency at all (statsmodels has no PP test)."""
    rng = np.random.default_rng(5)
    y = pd.Series(np.cumsum(rng.normal(0, 1, 200)), index=_monthly_index(200))
    level = unit_root_tests(y)["level"]
    for key in ("adf_stat", "adf_p", "adf_lags", "pp_stat", "pp_p", "kpss_stat", "kpss_p"):
        assert key in level


# --- lag order --------------------------------------------------------------------


def test_select_lag_order_stays_inside_the_specs_1_to_4_grid() -> None:
    chosen = select_lag_order(_cointegrated(), max_lags=4)
    assert 1 <= chosen["aic"] <= 4
    assert 1 <= chosen["sic"] <= 4
    assert chosen["chosen"] == chosen["aic"]


# --- structural break -------------------------------------------------------------


def test_structural_break_recovers_a_mean_shift_at_observation_120() -> None:
    """The spec's own acceptance test: a simulated shift at obs 120, recovered ±3."""
    rng = np.random.default_rng(1)
    n = 240
    signal = rng.normal(0, 1, n)
    signal[120:] += 5.0
    df = pd.DataFrame({"y": signal}, index=_monthly_index(n))
    result = structural_break(df)
    assert abs(result["break_index"] - 120) <= 3


def test_structural_break_reports_the_date_not_just_the_index() -> None:
    rng = np.random.default_rng(1)
    n = 240
    signal = rng.normal(0, 1, n)
    signal[120:] += 5.0
    index = _monthly_index(n)
    df = pd.DataFrame({"y": signal}, index=index)
    result = structural_break(df)
    assert result["break_date"] == index[result["break_index"]]


def test_structural_break_sup_f_finds_a_coefficient_break() -> None:
    """Andrews sup-F watches the *relationship* between the columns, which Bai-Perron's
    l2 cost on the levels does not -- here the slope flips halfway with no mean shift."""
    rng = np.random.default_rng(2)
    n = 240
    x = np.cumsum(rng.normal(0, 1, n))
    y = np.empty(n)
    y[:120] = 2.0 * x[:120] + rng.normal(0, 0.5, 120)
    y[120:] = 2.0 * x[119] - 2.0 * (x[120:] - x[119]) + rng.normal(0, 0.5, 120)
    df = pd.DataFrame({"y": y, "x": x}, index=_monthly_index(n))
    result = structural_break(df)
    assert abs(result["sup_f_index"] - 120) <= 12
    assert result["sup_f"] > 10.0


# --- Johansen ---------------------------------------------------------------------


def test_johansen_recovers_rank_one_and_beta_on_a_cointegrated_pair() -> None:
    """The spec's own acceptance test: simulated pair with beta=0.16 -> rank 1, ±0.03."""
    result = johansen(_cointegrated(beta=0.16))
    assert result["rank"] == 1
    assert result["beta_y2"] == pytest.approx(0.16, abs=0.03)


def test_johansen_finds_no_cointegration_between_independent_random_walks() -> None:
    assert johansen(_independent_random_walks())["rank"] == 0


def test_johansen_reports_both_statistics_against_their_5pct_critical_values() -> None:
    result = johansen(_cointegrated())
    assert len(result["trace_stat"]) == 2
    assert len(result["trace_cv_5pct"]) == 2
    assert len(result["max_eig_stat"]) == 2
    assert len(result["max_eig_cv_5pct"]) == 2
    assert result["trace_stat"][0] > result["trace_cv_5pct"][0]


# --- VECM fit ---------------------------------------------------------------------


def test_fit_vecm_recovers_the_cointegrating_vector() -> None:
    fitted = fit_vecm(_cointegrated(beta=0.16), rank=1, k_ar_diff=1)
    beta = fitted.beta[:, 0] / fitted.beta[0, 0]
    assert -beta[1] == pytest.approx(0.16, abs=0.03)


def test_fit_vecm_exposes_alpha_and_gamma() -> None:
    fitted = fit_vecm(_cointegrated(), rank=1, k_ar_diff=1)
    assert fitted.alpha.shape == (2, 1)
    assert fitted.gamma.shape[0] == 2


# --- Granger --------------------------------------------------------------------


def test_granger_reports_both_directions() -> None:
    result = granger(_cointegrated(), maxlag=2)
    assert set(result["direction"]) == {"y2->y1", "y1->y2"}
    assert result["p_value"].between(0.0, 1.0).all()


# --- forecast evaluation ----------------------------------------------------------


def test_forecast_eval_beats_a_random_walk_on_genuinely_cointegrated_data() -> None:
    """Where a real error-correction relationship exists, the VECM should exploit it --
    the positive control for the guard test below."""
    result = forecast_eval(_cointegrated(n=200), test_size=40, k_ar_diff=1)
    assert result["theil_u"] < 1.0
    assert result["n_forecasts"] == 40


def test_forecast_eval_does_not_beat_a_random_walk_on_pure_random_walks() -> None:
    """The spec's own look-ahead guard: with nothing to forecast, a VECM that appears to
    beat the random walk is evidence of leakage, not skill. dm_stat < 0 means the VECM
    has the lower loss, so a significantly negative stat here would be the red flag.
    """
    result = forecast_eval(_independent_random_walks(n=200), test_size=40, k_ar_diff=1)
    beats_rw_significantly = result["dm_stat"] < 0 and result["dm_p"] < 0.1
    assert not beats_rw_significantly


def test_forecast_eval_reports_theil_u_as_the_rmse_ratio() -> None:
    result = forecast_eval(_cointegrated(n=200), test_size=40, k_ar_diff=1)
    assert result["theil_u"] == pytest.approx(result["rmse_vecm"] / result["rmse_rw"])


def test_forecast_eval_never_fits_on_data_after_the_forecast_origin() -> None:
    """The concrete no-look-ahead check.

    Both runs start at origin 180; the second can additionally see rows 190-199. If any
    of those later rows leaked into a forecast made at origins 180-189, the overlapping
    prefix of the two error paths would differ. Comparing aggregate RMSE cannot show
    this, because the two runs cover different numbers of origins.
    """
    full = _cointegrated(n=200)
    short = forecast_eval(full.iloc[:190], test_size=10, k_ar_diff=1)
    long = forecast_eval(full, test_size=20, k_ar_diff=1)
    assert short["n_forecasts"] == 10
    assert long["n_forecasts"] == 20
    assert short["errors_vecm"] == pytest.approx(long["errors_vecm"][:10])


# --- model card -------------------------------------------------------------------


def test_model_card_carries_every_field_the_conventions_require() -> None:
    """00_TRADING_CONVENTIONS.md: estimation window, last refit, OOS status vs the named
    benchmark, exception count, structural-break date."""
    df = _cointegrated(n=200)
    card = model_card(df, test_size=40, k_ar_diff=1)
    for key in (
        "estimation_start",
        "estimation_end",
        "last_refit",
        "oos_status",
        "benchmark",
        "exceptions",
        "break_date",
        "theil_u",
        "rank",
    ):
        assert key in card, key
    assert card["benchmark"] == "random walk"
