from __future__ import annotations

import pandas as pd
from pipelines.eirgrid.transforms import snsp_proxy


def test_snsp_proxy_hand_checked() -> None:
    dates = pd.date_range("2026-01-01", periods=3, freq="h")
    wind = pd.Series([500.0, 600.0, 700.0], index=dates)
    net_import = pd.Series([200.0, -100.0, 300.0], index=dates)  # middle point exports
    demand = pd.Series([1000.0, 1000.0, 1000.0], index=dates)

    result = snsp_proxy(wind, net_import, demand)

    # (500+200)/1000, (600+0)/1000 [export clipped to 0], (700+300)/1000
    assert result.tolist() == [0.7, 0.6, 1.0]


def test_snsp_proxy_treats_missing_wind_as_zero() -> None:
    dates = pd.date_range("2026-01-01", periods=2, freq="h")
    wind = pd.Series(dtype=float)
    net_import = pd.Series([100.0, 100.0], index=dates)
    demand = pd.Series([1000.0, 1000.0], index=dates)

    result = snsp_proxy(wind, net_import, demand)

    assert result.tolist() == [0.1, 0.1]
