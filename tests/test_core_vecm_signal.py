from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from core.vecm import backtest_positions, ect_signal, fit_vecm, irf_table


def _panel(n: int = 240, seed: int = 0) -> pd.DataFrame:
    """Cointegrated pair on a monthly index: y1 = 0.16*y2 + stationary noise."""
    rng = np.random.default_rng(seed)
    y2 = np.cumsum(rng.normal(0, 1, n))
    y1 = 0.16 * y2 + rng.normal(0, 0.5, n)
    return pd.DataFrame(
        {"log_wti": y1, "crack321": y2},
        index=pd.date_range("2000-01-31", periods=n, freq="BME"),
    )


def _signal(df: pd.DataFrame | None = None, **kwargs) -> pd.DataFrame:
    data = _panel() if df is None else df
    return ect_signal(fit_vecm(data), data, **kwargs)


# --- error-correction term --------------------------------------------------------


def test_ect_is_the_cointegrating_combination_of_the_two_series() -> None:
    """ect = beta'y, with beta normalised so the crude leg carries a coefficient of 1."""
    df = _panel()
    fitted = fit_vecm(df)
    out = ect_signal(fitted, df)
    beta = fitted.beta[:, 0] / fitted.beta[0, 0]
    expected = df["log_wti"] + beta[1] * df["crack321"]
    assert out["ect"].to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-9)


def test_z_score_uses_a_rolling_window_not_the_whole_sample() -> None:
    """A full-sample z would be computed with data from the future."""
    out = _signal(z_window=60)
    assert out["z"].iloc[:59].isna().all()
    assert out["z"].iloc[60:].notna().any()


# --- entry / exit hysteresis ------------------------------------------------------


def test_position_is_opposite_the_z_score_beyond_the_entry_band() -> None:
    """A rich error-correction term is faded, not chased."""
    out = _signal(z_entry=1.5, z_exit=0.5)
    entered = out[out["z"].abs() >= 1.5]
    assert len(entered) > 0
    assert (np.sign(entered["raw_position"]) == -np.sign(entered["z"])).all()


def test_position_is_flat_inside_the_exit_band() -> None:
    out = _signal(z_entry=1.5, z_exit=0.5)
    inside = out[out["z"].abs() <= 0.5]
    assert len(inside) > 0
    assert (inside["raw_position"] == 0).all()


def test_position_is_held_between_the_exit_and_entry_bands() -> None:
    """Hysteresis: between the bands the previous position persists rather than
    flip-flopping on every small move."""
    out = _signal(z_entry=1.5, z_exit=0.5).dropna(subset=["z"])
    between = (out["z"].abs() > 0.5) & (out["z"].abs() < 1.5)
    held = out[between & (out["raw_position"] != 0)]
    assert len(held) > 0


# --- scaling and gating -----------------------------------------------------------


def test_alpha_scale_is_the_crude_legs_share_of_the_adjustment() -> None:
    """|alpha_crude| normalised -- bounded 0..1, so it scales rather than explodes."""
    out = _signal()
    assert out["alpha_scale"].between(0.0, 1.0).all()
    assert out["alpha_scale"].nunique() == 1  # one fitted model, one alpha


def test_vol_scale_is_inverse_realised_volatility() -> None:
    out = _signal()
    scale = out["vol_scale"].dropna()
    assert (scale > 0).all()
    assert np.isfinite(scale).all()


def test_momentum_gate_flattens_positions_that_fight_3m_crack_momentum() -> None:
    """The spec trades the error-correction signal only in the direction of 3-month
    crack momentum."""
    out = _signal().dropna(subset=["position"])
    fighting = out[
        (out["raw_position"] != 0)
        & (np.sign(out["raw_position"]) != np.sign(out["momentum"]))
    ]
    assert (fighting["position"] == 0).all()


def test_position_is_zero_wherever_the_raw_signal_is_zero() -> None:
    out = _signal()
    assert (out.loc[out["raw_position"] == 0, "position"] == 0).all()


# --- the no-look-ahead guard (Session C's own DoD) --------------------------------


def test_signal_never_uses_a_future_observation() -> None:
    """Spec 20 Session C DoD: "signal never uses y_{t+1} (shift test)".

    Truncating the panel must leave every signal value up to the truncation point
    unchanged. If any rolling statistic, z-score or gate were centred or forward-looking,
    the two runs would disagree on the overlap.
    """
    full = _panel(240)
    cut = 200
    fitted = fit_vecm(full.iloc[:cut])

    long_run = ect_signal(fitted, full)
    short_run = ect_signal(fitted, full.iloc[:cut])

    overlap = short_run.index
    for column in ("ect", "z", "raw_position", "position", "momentum"):
        a = long_run.loc[overlap, column].to_numpy(dtype=float)
        b = short_run[column].to_numpy(dtype=float)
        assert np.allclose(a, b, equal_nan=True), column


def test_backtest_applies_yesterdays_position_to_todays_return() -> None:
    """A position formed at t earns the return from t to t+1. Applying it to the return
    *into* t would be trading on information the signal did not have."""
    index = pd.date_range("2020-01-31", periods=4, freq="BME")
    crack = pd.Series([10.0, 11.0, 12.0, 13.0], index=index)
    positions = pd.Series([0.0, 1.0, 0.0, 0.0], index=index)
    result = backtest_positions(positions, crack)
    # Only the position held at index 1 earns anything: 12.0 - 11.0 = 1.0
    assert result["pnl"].sum() == pytest.approx(1.0)
    assert result["pnl"].iloc[0] == pytest.approx(0.0)


# --- backtest card ----------------------------------------------------------------


def test_backtest_reports_the_card_fields_the_conventions_require() -> None:
    out = _signal()
    crack = _panel()["crack321"]
    result = backtest_positions(out["position"], crack)
    for key in ("pnl", "summary"):
        assert key in result
    for field in ("sharpe", "hit_rate", "max_drawdown", "n_trades", "total_pnl"):
        assert field in result["summary"], field


def test_backtest_fractionates_by_refinery_turnaround_months() -> None:
    """Spec 20 Session C: fractionate by turnaround months (Mar-Apr, Sep-Oct)."""
    out = _signal()
    result = backtest_positions(out["position"], _panel()["crack321"])
    assert "turnaround" in result["summary"]
    assert "non_turnaround" in result["summary"]


def test_backtest_hit_rate_is_a_proportion() -> None:
    out = _signal()
    result = backtest_positions(out["position"], _panel()["crack321"])
    assert 0.0 <= result["summary"]["hit_rate"] <= 1.0


# --- impulse responses ------------------------------------------------------------


def test_irf_table_gives_the_crude_response_to_a_crack_shock() -> None:
    """The spec's page shows crude's response to a crack shock over 24 months."""
    table = irf_table(fit_vecm(_panel()), periods=24)
    assert len(table) == 25  # horizon 0 through 24
    assert "crude_to_crack_shock" in table.columns
    assert table["horizon"].iloc[0] == 0


def test_irf_table_starts_at_zero_response_for_the_cross_shock() -> None:
    table = irf_table(fit_vecm(_panel()), periods=12)
    assert table["crude_to_crack_shock"].iloc[0] == pytest.approx(0.0, abs=1e-9)
