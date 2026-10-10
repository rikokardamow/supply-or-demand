from __future__ import annotations

import numpy as np
import pandas as pd
from core.theme import (
    NAVY,
    RED,
    crowding_quadrant_scatter,
    equity_drawdown_chart,
    fractionation_heatmap,
    reaction_curve_chart,
    signal_board_table,
)


def _index(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


# --- signal board -----------------------------------------------------------------


def test_signal_board_table_renders_a_row_per_strategy() -> None:
    board = pd.DataFrame(
        {
            "strategy": ["MOM_100", "CARRY_REACT"],
            "z": [1.2, -0.4],
            "position": [0.8, -0.3],
            "guardrail": ["none", "crowded long halved"],
        }
    )
    fig = signal_board_table(board)
    assert len(fig.data) == 1
    assert fig.data[0].type == "table"


def test_signal_board_colours_by_position_sign() -> None:
    """A board where you cannot see long from short at a glance is not a board. Assert
    the actual colours on the position column, not merely that some colouring exists."""
    board = pd.DataFrame(
        {"strategy": ["A", "B"], "z": [2.0, -2.0], "position": [1.0, -1.0], "guardrail": ["", ""]}
    )
    fig = signal_board_table(board)
    position_column = list(fig.data[0].cells.fill.color)[list(board.columns).index("position")]
    assert list(position_column) == [NAVY, RED]  # long navy, short red


# --- equity and drawdown ----------------------------------------------------------


def test_equity_drawdown_chart_has_both_panels() -> None:
    idx = _index(100)
    equity = pd.Series(np.linspace(0, 0.5, 100), index=idx)
    drawdown = pd.Series(np.minimum(0, np.linspace(0.1, -0.2, 100)), index=idx)
    fig = equity_drawdown_chart(equity, drawdown, "log return")
    assert len(fig.data) == 2


def test_equity_drawdown_chart_adds_a_benchmark_line_when_given_one() -> None:
    idx = _index(50)
    equity = pd.Series(np.linspace(0, 0.5, 50), index=idx)
    drawdown = pd.Series(0.0, index=idx)
    benchmark = pd.Series(np.linspace(0, 0.3, 50), index=idx)
    fig = equity_drawdown_chart(equity, drawdown, "u", benchmark=benchmark)
    assert len(fig.data) == 3
    assert any("enchmark" in (trace.name or "") for trace in fig.data)


def test_equity_drawdown_chart_works_on_a_datetime_axis() -> None:
    """Regression guard: model_monitor_chart crashed on exactly this, because plotly
    averages a shape's endpoints to place an annotation and cannot do that on datetimes.
    """
    idx = _index(80)
    fig = equity_drawdown_chart(
        pd.Series(np.linspace(0, 1, 80), index=idx),
        pd.Series(0.0, index=idx),
        "u",
    )
    # Built without raising on a datetime axis -- that is what this test guards.
    assert len(fig.data) >= 2
    # And since the 2026-09-06 restyle the section header owns the title, so the
    # figure must not paint one of its own (tests/test_theme_titles.py enforces this
    # across all the builders).
    assert fig.layout.title.text is None


# --- reaction curve ---------------------------------------------------------------


def test_reaction_curve_chart_draws_the_function_and_marks_the_live_z() -> None:
    fig = reaction_curve_chart(current_z=1.4)
    assert len(fig.data) >= 2  # the curve plus the marker
    marker = [t for t in fig.data if t.mode and "markers" in t.mode]
    assert marker, "the live z must be marked"
    assert marker[0].x[0] == 1.4


def test_reaction_curve_peaks_at_one() -> None:
    """The drawn curve must actually be R(z), whose maximum is exactly 1 at z=1."""
    fig = reaction_curve_chart(current_z=0.0)
    curve = fig.data[0]
    assert max(curve.y) == np.float64(1.0) or abs(max(curve.y) - 1.0) < 1e-6


def test_reaction_curve_handles_a_missing_live_z() -> None:
    fig = reaction_curve_chart(current_z=float("nan"))
    assert len(fig.data) >= 1


# --- fractionation ----------------------------------------------------------------


def test_fractionation_heatmap_pivots_condition_against_bin() -> None:
    table = pd.DataFrame(
        {
            "condition": ["regime", "regime", "month", "month"],
            "bin": ["0", "1", "1", "2"],
            "n": [10, 10, 10, 10],
            "mean": [0.1, -0.1, 0.2, -0.2],
            "sharpe": [0.5, -0.5, 1.0, -1.0],
            "share_of_total": [0.6, 0.4, 0.7, 0.3],
        }
    )
    fig = fractionation_heatmap(table, value="sharpe")
    assert len(fig.data) == 1
    assert fig.data[0].type == "heatmap"


def test_fractionation_heatmap_is_empty_safe() -> None:
    empty = pd.DataFrame(columns=["condition", "bin", "n", "mean", "sharpe", "share_of_total"])
    fig = fractionation_heatmap(empty, value="sharpe")
    assert len(fig.data) == 0


# --- crowding ---------------------------------------------------------------------


def test_crowding_quadrant_scatter_plots_cot_against_signal() -> None:
    idx = _index(200)
    rng = np.random.default_rng(0)
    cot = pd.Series(rng.uniform(0, 1, 200), index=idx)
    z = pd.Series(rng.normal(0, 1, 200), index=idx)
    fig = crowding_quadrant_scatter(cot, z)
    scatter = [t for t in fig.data if t.type == "scatter" or t.type == "scattergl"]
    assert scatter


def test_crowding_quadrant_shades_the_inflection_corners() -> None:
    """The point of the chart is the corners: crowded long with a long signal, and
    crowded short with a short signal."""
    idx = _index(50)
    fig = crowding_quadrant_scatter(pd.Series(0.5, index=idx), pd.Series(0.0, index=idx))
    assert len(fig.layout.shapes) >= 2
