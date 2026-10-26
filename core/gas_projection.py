"""Shared arithmetic for the gas supply-demand models: calendar years, projection and a
storage path. Pure functions, no I/O. Used by ``core/eu_gas_balance.py`` and
``core/uk_gas_balance.py``."""

from __future__ import annotations

import pandas as pd


def calendar_year(table: pd.DataFrame, complete_only: bool = True) -> pd.DataFrame:
    """Sum months to calendar years. With ``complete_only``, a column-year with fewer than
    twelve published months is NaN rather than a partial total."""
    grouped = table.groupby(pd.DatetimeIndex(table.index).year)
    totals = grouped.sum(min_count=1)
    if complete_only:
        totals = totals.where(grouped.count() == 12)
    return totals


def project(history: pd.DataFrame, assumptions: pd.DataFrame, end: pd.Timestamp) -> pd.DataFrame:
    """Month x line projection from the last observed month to ``end``.

    Each projected month is the same month a year earlier (observed or already projected)
    times ``1 + yoy_pct / 100``, which keeps the seasonal shape. ``assumptions`` has
    ``line``, ``year``, ``yoy_pct``. A line with no assumption for a year is NaN for that
    year: an unset assumption is not a zero-growth one.
    """
    if history.empty:
        return pd.DataFrame(columns=history.columns)
    last = pd.Timestamp(history.index.max())
    months = pd.date_range(last + pd.offsets.MonthBegin(1), end, freq="MS")
    rates = assumptions.set_index(["line", "year"])["yoy_pct"]
    if rates.index.duplicated().any():
        raise ValueError("assumptions: duplicate line/year")
    combined = history.copy()
    for month in months:
        base = (
            combined.loc[month - pd.DateOffset(years=1)]
            if (month - pd.DateOffset(years=1)) in combined.index
            else pd.Series(float("nan"), index=combined.columns)
        )
        growth = pd.Series(
            {col: rates.get((col, month.year), float("nan")) for col in combined.columns}
        )
        combined.loc[month] = base * (1 + growth / 100)
    return combined.loc[months]


def storage_path(start_twh: float, stock_build_twh: pd.Series) -> pd.Series:
    """Gas in storage after each projected month, from an observed starting level.
    Stops at the first month whose build is NaN: a gap cannot be carried forward."""
    level = start_twh + stock_build_twh.cumsum()
    gaps = stock_build_twh.index[stock_build_twh.isna()]
    return level if gaps.empty else level.loc[level.index < gaps[0]]
