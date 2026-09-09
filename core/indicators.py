"""Price indicators. Small, testable, and computed here rather than in the UI.

Spec 32 §1: every derived number the UI shows is computed in Python and published as
rows. A moving average is a derived number, so it belongs here and in a `derived.*`
series, not in a browser.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

# The conventional trio. 50/100/200 sessions, not calendar days -- a moving average is
# defined over observations, and futures do not trade at weekends.
MA_WINDOWS: Final[tuple[int, ...]] = (50, 100, 200)


def moving_average(values: pd.Series, window: int) -> pd.Series:
    """`window`-observation simple moving average, aligned to `values`' own index.

    `min_periods=window` is the point of this function. Pandas defaults to emitting a
    partial average as soon as there is one observation, so a 200-day MA would begin on
    day one as a 1-day average and creep towards the real thing -- indistinguishable on a
    chart from a genuine 200-day line, and wrong for its first 199 points. Here the
    series is NaN until the window is genuinely full, and the chart simply starts later.
    """
    if window <= 0:
        raise ValueError(f"window must be positive, got {window}")
    return values.rolling(window=window, min_periods=window).mean()
