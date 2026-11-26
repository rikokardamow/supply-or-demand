"""GIE-specific transforms. Seasonal maths belongs in core.seasonal, not here."""

from __future__ import annotations

import pandas as pd
from core.seasonal import reference_doy_clamped, seasonal_stats


def net_flow(injection: pd.Series, withdrawal: pd.Series) -> pd.Series:
    """Net flow = injection - withdrawal. Positive = net injecting, negative = net
    withdrawing."""
    result: pd.Series = injection - withdrawal
    return result


def days_to_full_or_empty(
    fill_pct: float,
    working_gas_volume_twh: float,
    avg_net_injection_gwh_per_day: float,
) -> tuple[float | None, str | None]:
    """Days to reach 100% full (if net injecting) or 0% empty (if net withdrawing) at
    the given average net-injection rate. working_gas_volume is in TWh, injection rate
    in GWh/d — converted to matching units (x1000) before dividing. Returns (None, None)
    if the rate is exactly zero (no meaningful trajectory)."""
    working_gas_volume_gwh = working_gas_volume_twh * 1000

    if avg_net_injection_gwh_per_day > 0:
        remaining_gwh = working_gas_volume_gwh * (100 - fill_pct) / 100
        return remaining_gwh / avg_net_injection_gwh_per_day, "full"
    if avg_net_injection_gwh_per_day < 0:
        remaining_gwh = working_gas_volume_gwh * fill_pct / 100
        return remaining_gwh / abs(avg_net_injection_gwh_per_day), "empty"
    return None, None


def nearest_value_at_offset(
    series: pd.Series, target_ts: pd.Timestamp, tolerance_days: int = 5
) -> float | None:
    """The series value nearest `target_ts` (e.g. "30 days ago", "365 days ago") — GIE's
    daily data won't always land exactly on the target date, so this finds the closest
    real observation instead of requiring an exact match. Returns None if the nearest
    point is further than `tolerance_days` away (no meaningful M-1/Y-1 comparison)."""
    if series.empty:
        return None
    index_series = series.index.to_series()
    diffs = (index_series - target_ts).abs()
    nearest_ts = diffs.idxmin()
    if diffs.loc[nearest_ts] > pd.Timedelta(days=tolerance_days):
        return None
    return float(series.loc[nearest_ts])


def country_deviation(fill_by_country: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """For each country's fill-% history (columns: ts, value), the latest value vs.
    the seasonal median at the same day-of-year, ranked descending (biggest surplus
    first). `fill_by_country` maps a country/geo code to its ts_long-shaped subset."""
    rows = []
    for geo, df in fill_by_country.items():
        if df.empty:
            continue
        stats = seasonal_stats(df, value_col="value")
        latest = df.sort_values("ts").iloc[-1]
        latest_doy = reference_doy_clamped(pd.Timestamp(latest["ts"]))
        median = stats["median"].get(latest_doy)
        if median is None:
            continue
        rows.append(
            {
                "geo": geo,
                "latest_fill_pct": latest["value"],
                "median_fill_pct": median,
                "deviation": latest["value"] - median,
            }
        )

    return pd.DataFrame(rows).sort_values("deviation", ascending=False).reset_index(drop=True)
