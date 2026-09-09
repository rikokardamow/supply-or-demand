from __future__ import annotations

import pandas as pd
import pytest
from core.indicators import MA_WINDOWS, moving_average


def test_moving_average_is_the_mean_of_the_window() -> None:
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    got = moving_average(values, 3)

    assert got.iloc[2] == pytest.approx(2.0)  # (1+2+3)/3
    assert got.iloc[4] == pytest.approx(4.0)  # (3+4+5)/3


def test_moving_average_emits_nothing_until_the_window_is_full() -> None:
    # The whole reason this function exists. Pandas' default (min_periods=1) would make a
    # 200-day average start on day one as a 1-day average and creep towards the real
    # thing -- a line that looks like a 200-day MA on a chart and is wrong for its first
    # 199 points. Better to start the line late than to draw a fabricated one.
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])

    got = moving_average(values, 3)

    assert got.iloc[:2].isna().all()
    assert got.iloc[2:].notna().all()


def test_moving_average_returns_all_nan_when_there_is_not_enough_history() -> None:
    # A young series has no 200-day average, and must not be given one.
    got = moving_average(pd.Series([1.0, 2.0, 3.0]), 200)

    assert got.isna().all()


def test_moving_average_keeps_the_original_index() -> None:
    index = pd.date_range("2026-01-01", periods=5, freq="D")
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=index)

    got = moving_average(values, 2)

    assert got.index.equals(index)


def test_moving_average_rejects_a_non_positive_window() -> None:
    with pytest.raises(ValueError, match="window must be positive"):
        moving_average(pd.Series([1.0]), 0)


def test_the_conventional_windows_are_the_ones_published() -> None:
    assert MA_WINDOWS == (50, 100, 200)
