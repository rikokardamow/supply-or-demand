"""EirGrid-specific transforms."""

from __future__ import annotations

import pandas as pd


def snsp_proxy(wind: pd.Series, net_interconnection: pd.Series, demand: pd.Series) -> pd.Series:
    """System Non-Synchronous Penetration proxy = (wind + HVDC imports) / demand, per
    the spec's own simplified formula (wind + solar + HVDC imports) / demand — solar is
    omitted since EirGrid's public dashboard has no solar-specific area (confirmed live:
    "solaractual" returns "Invalid Area"). `net_interconnection` is INTER_NET_ROI
    (positive = importing into ROI, confirmed live by cross-checking generation + net
    import ≈ demand) — clipped to >=0 so an export period (net negative) contributes
    zero non-synchronous import, not a negative one."""
    imports = net_interconnection.reindex(demand.index, fill_value=0.0).clip(lower=0.0)
    wind_aligned = wind.reindex(demand.index, fill_value=0.0)
    result: pd.Series = (wind_aligned + imports) / demand
    return result
