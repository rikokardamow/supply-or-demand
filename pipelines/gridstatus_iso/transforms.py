"""Derived series for gridstatus ISO data -- computed at read time, not stored."""

from __future__ import annotations

import pandas as pd


def net_load(load: pd.Series, wind: pd.Series, solar: pd.Series) -> pd.Series:
    """Load minus wind minus solar -- what conventional (thermal/hydro/storage)
    capacity has to cover. Missing wind/solar at a timestamp is treated as 0, not
    dropped -- same reasoning as pipelines/entsoe/transforms.py::residual_load."""
    result: pd.Series = load - wind.reindex(load.index, fill_value=0.0) - solar.reindex(
        load.index, fill_value=0.0
    )
    return result
