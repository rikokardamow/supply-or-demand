from __future__ import annotations

import numpy as np
import pandas as pd
from core.theme import cointegration_residual_chart, irf_chart, model_monitor_chart


def _ratio() -> pd.Series:
    index = pd.date_range("2015-01-31", periods=60, freq="BME")
    return pd.Series(np.linspace(0.9, 1.1, 60), index=index)


def test_model_monitor_chart_draws_a_break_line_on_a_datetime_axis() -> None:
    """Regression: `add_vline(annotation_text=...)` routes through plotly's own
    shapeannotation, which places the label with `float(sum(x)) / len(x)`. On a datetime
    axis that raises TypeError -- against a pandas Timestamp *and* against an ISO string.
    Page 20 crashed on exactly this, caught by tests/test_pages_smoke.py. The chart now
    adds the shape and the annotation separately.
    """
    fig = model_monitor_chart(_ratio(), 1.05, "t", break_date=pd.Timestamp("2018-06-29"))
    assert len(fig.layout.shapes) == 3  # parity, trigger, break
    assert any(a.text == "structural break" for a in fig.layout.annotations)


def test_model_monitor_chart_works_without_a_break_date() -> None:
    fig = model_monitor_chart(_ratio(), 1.05, "t")
    assert len(fig.layout.shapes) == 2  # parity and trigger only


def test_model_monitor_chart_draws_parity_as_well_as_the_trigger() -> None:
    """A ratio of 1.02 is already losing to the benchmark while sitting inside a 1.05
    trigger -- both lines are needed to keep that visible."""
    fig = model_monitor_chart(_ratio(), 1.05, "t")
    levels = sorted(s.y0 for s in fig.layout.shapes)
    assert levels == [1.0, 1.05]


def test_cointegration_residual_chart_builds_both_rows() -> None:
    index = pd.date_range("2015-01-31", periods=60, freq="BME")
    ect = pd.Series(np.random.default_rng(0).normal(0, 1, 60), index=index)
    fig = cointegration_residual_chart(ect, ect.rolling(12).mean().dropna(), "t", "$/bbl")
    assert len(fig.data) == 2


def test_irf_chart_draws_a_zero_line() -> None:
    irf = pd.DataFrame({"horizon": range(25), "crude_to_crack_shock": np.linspace(0, 0.2, 25)})
    fig = irf_chart(irf, "crude_to_crack_shock", "t", "u")
    assert len(fig.data) == 1
    assert any(s.y0 == 0.0 for s in fig.layout.shapes)
