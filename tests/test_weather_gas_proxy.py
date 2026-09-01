from __future__ import annotations

import pandas as pd
from pipelines.weather.gas_proxy import net_withdrawal


def test_net_withdrawal_positive_on_drawdown_negative_on_build() -> None:
    level = pd.Series([100.0, 90.0, 95.0])

    result = net_withdrawal(level)

    assert result.iloc[1] == 10.0  # storage fell 10 -> net withdrawing
    assert result.iloc[2] == -5.0  # storage rose 5 -> net injecting
