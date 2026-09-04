"""Fundamentals & physical-market analytics: inventory seasonality, days-of-cover, spare
capacity, and CFTC COT positioning percentiles. Never touches DuckDB (root NOTES.md rule)
-- callers (pipelines/derived/fundamentals.py) read the lake, call these pure functions,
and write the results back."""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.seasonal import seasonal_stats


def inventory_deviation(
    df: pd.DataFrame, years: int = 5, exclude: tuple[int, ...] = (2020,)
) -> pd.DataFrame:
    """Thin wrapper over core.seasonal.seasonal_stats (root NOTES.md rule 4: never
    reimplement the day-of-year/exclude-2020 seasonal maths) -- `df` needs columns ts,
    value. Columns returned: value (the latest year's own track), mean/min/max (min/max are
    seasonal_stats' own lo/hi, renamed to match this project's own convention), dev
    (value-mean), dev_z (dev / the standard deviation across the included years, at that
    same day-of-year). NaN wherever std is 0 or too few years remain, never a crash."""
    current_year = int(df["ts"].dt.year.max())
    years_range = range(current_year - years, current_year + 1)
    stats = seasonal_stats(df, "value", years=years_range, exclude=exclude)

    year_cols = [c for c in stats.columns if c not in ("lo", "hi", "median")]
    year_values = stats[year_cols]
    mean = year_values.mean(axis=1)
    std = year_values.std(axis=1)

    latest_col = str(current_year)
    value = stats[latest_col] if latest_col in stats.columns else pd.Series(
        np.nan, index=stats.index
    )
    dev = value - mean
    dev_z = dev / std

    return pd.DataFrame(
        {
            "value": value,
            "mean": mean,
            "min": stats["lo"],
            "max": stats["hi"],
            "dev": dev,
            "dev_z": dev_z,
        },
        index=stats.index,
    )


def days_of_cover(stocks_kbbl: pd.Series, refinery_inputs_kbd: pd.Series) -> pd.Series:
    """stocks_kbbl / refinery_inputs_kbd -- plain division, matching this project's own
    real precedent (pipelines/eia/transforms.py::days_of_cover, used live on page
    01_us_padd.py, does the same plain division; any smoothing of `refinery_inputs_kbd`
    is the caller's own choice, not built in here)."""
    result: pd.Series = stocks_kbbl / refinery_inputs_kbd
    return result


def spare_capacity(eia: pd.Series, iea: pd.Series) -> pd.DataFrame:
    """Columns eia, iea, avg=(eia+iea)/2, disagreement=eia-iea -- both agencies' own real
    values are always kept alongside the average, per the spec's own "never average
    silently" instruction; no real data source exists yet for either input (Session B's
    manual_physical extension)."""
    combined_index = eia.index.union(iea.index)
    eia_r = eia.reindex(combined_index)
    iea_r = iea.reindex(combined_index)
    return pd.DataFrame(
        {"eia": eia_r, "iea": iea_r, "avg": (eia_r + iea_r) / 2, "disagreement": eia_r - iea_r}
    )


def spare_cap_regime(spare: pd.Series, thresholds: tuple[float, float] = (2.0, 4.0)) -> pd.Series:
    """'tight' below thresholds[0], 'ample' above thresholds[1], else 'balanced' --
    np.select, matching core.curve.curve_regime's own evaluated-in-order convention."""
    low, high = thresholds
    conditions = [spare < low, spare > high]
    choices = ["tight", "ample"]
    return pd.Series(np.select(conditions, choices, default="balanced"), index=spare.index)


def cot_percentiles(
    long: pd.Series, short: pd.Series, oi: pd.Series, window: int = 156
) -> pd.DataFrame:
    """net = long-short; net_pct_oi = net/oi; pct_rank_3y = today's net_pct_oi's own
    percentile rank within its own trailing `window`-week window (156 = 3yr of weekly COT
    reports), inclusive of today (same (w <= w.iloc[-1]).mean() technique
    core.curve.curve_regime's own slope_pct already uses); z = (net_pct_oi - rolling mean)
    / rolling std over the same window."""
    net = long - short
    net_pct_oi = net / oi
    pct_rank_3y = net_pct_oi.rolling(window).apply(
        lambda w: (w <= w.iloc[-1]).mean(), raw=False
    )
    rolling_mean = net_pct_oi.rolling(window).mean()
    rolling_std = net_pct_oi.rolling(window).std()
    z = (net_pct_oi - rolling_mean) / rolling_std

    return pd.DataFrame(
        {"net": net, "net_pct_oi": net_pct_oi, "pct_rank_3y": pct_rank_3y, "z": z}
    )
