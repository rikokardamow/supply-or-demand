"""US gas-storage net-withdrawal proxy for the page's HDD-vs-storage chart. Unlike GIE's
AGSI (pipelines/gie/transforms.py::net_flow, a direct injection-minus-withdrawal read),
EIA's weekly storage route (pipelines/eia/pull_gas_storage.py) publishes only a working-gas
*level*, no injection/withdrawal split -- net withdrawal has to be derived as the
week-over-week drop in that level."""

from __future__ import annotations

import pandas as pd


def net_withdrawal(level: pd.Series) -> pd.Series:
    """Positive when storage fell (net withdrawing), negative when it rose (net
    injecting) -- the opposite sign convention from the level itself, matching
    pipelines/gie/transforms.py::net_flow's "positive = net injecting" note inverted."""
    result: pd.Series = -level.diff()
    return result
