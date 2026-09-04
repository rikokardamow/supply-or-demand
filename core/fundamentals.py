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


# --- Session B additions: quality mismatch, Carollo diagnostic, shale response,
# benchmark health, OSP signal. No scipy/statsmodels/scikit-learn dependency exists in
# this project (confirmed via pyproject.toml) -- closed-form simple linear regression
# needs none, so `_ols` is hand-rolled, matching Spec 18 Session C's own
# "no new dependency for basic stats" precedent (that session's t-test).


def _ols(x: pd.Series, y: pd.Series) -> dict[str, float]:
    """Closed-form simple linear regression of y on x (paired, NaN-dropped). Returns
    slope, intercept, r2, t_stat (slope / its own standard error), n. NaN fields
    (never a crash) when fewer than 2 paired points remain, x has zero variance, or the
    residual degrees of freedom is too small for a standard error."""
    paired = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(paired)
    nan_result = {
        "slope": np.nan,
        "intercept": np.nan,
        "r2": np.nan,
        "t_stat": np.nan,
        "n": float(n),
    }
    if n < 2:
        return nan_result

    x_arr = paired["x"].to_numpy(dtype=float)
    y_arr = paired["y"].to_numpy(dtype=float)
    x_mean, y_mean = x_arr.mean(), y_arr.mean()
    sxx = float(np.sum((x_arr - x_mean) ** 2))
    if sxx == 0:
        return nan_result

    sxy = float(np.sum((x_arr - x_mean) * (y_arr - y_mean)))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    y_pred = intercept + slope * x_arr
    residuals = y_arr - y_pred
    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((y_arr - y_mean) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan

    dof = n - 2
    if dof > 0 and ss_tot != 0:
        residual_std_err = np.sqrt(ss_res / dof)
        se_slope = residual_std_err / np.sqrt(sxx)
        t_stat = slope / se_slope if se_slope != 0 else np.nan
    else:
        t_stat = np.nan

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r2": float(r2),
        "t_stat": float(t_stat),
        "n": float(n),
    }


def _zscore(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std()


_QUALITY_SPREAD_LEGS: dict[str, tuple[str, str]] = {
    "brent_dubai_efs": ("brent", "dubai"),
    "wti_wcs": ("wti", "wcs"),
    "lls_maya": ("lls", "maya"),
    "brent_urals": ("brent", "urals"),
}


def quality_spreads(prices: pd.DataFrame) -> pd.DataFrame:
    """`prices` columns: whatever subset of brent/dubai/wti/wcs/lls/maya/urals is
    available -- a spread missing either leg comes back NaN, never a KeyError.
    sweet_sour_index = the mean of the 4 spreads' own z-scores ("mean z" per the
    spec's own comment), not a mean of raw dollar spreads (which would conflate scale
    across genuinely different price levels)."""
    spreads: dict[str, pd.Series] = {}
    for name, (leg_a, leg_b) in _QUALITY_SPREAD_LEGS.items():
        if leg_a in prices.columns and leg_b in prices.columns:
            spreads[name] = prices[leg_a] - prices[leg_b]
        else:
            spreads[name] = pd.Series(np.nan, index=prices.index)

    result = pd.DataFrame(spreads, index=prices.index)
    z_scores = result[list(_QUALITY_SPREAD_LEGS)].apply(_zscore)
    result["sweet_sour_index"] = z_scores.mean(axis=1)
    return result


def refining_constraint_index(
    utilisation: pd.Series, complex_simple_margin_spread: pd.Series, light_heavy: pd.Series
) -> pd.Series:
    """Carollo's binding-constraint gauge: the mean of z(utilisation),
    z(-complex_simple_margin_spread) (a NARROW margin spread signals a binding
    constraint, so its z is inverted before averaging), z(light_heavy) -- all three
    push the same direction (high utilisation + narrow margin spread + wide
    light-heavy diff all mean the same thing: refining capacity is the binding
    constraint), so the composite rises exactly when Carollo's own story says it
    should."""
    combined_index = (
        utilisation.index.union(complex_simple_margin_spread.index).union(light_heavy.index)
    )
    u = utilisation.reindex(combined_index)
    margin = complex_simple_margin_spread.reindex(combined_index)
    lh = light_heavy.reindex(combined_index)
    result: pd.Series = (_zscore(u) + _zscore(-margin) + _zscore(lh)) / 3
    return result


def carollo_scatter(delta_stocks_q: pd.Series, delta_brent_q: pd.Series) -> dict[str, float]:
    """OLS of delta_brent_q on delta_stocks_q: slope, r2. share_wrong_sign = the
    fraction of quarters where sign(delta_stocks_q) == sign(delta_brent_q) -- the
    classical S&D model expects an INVERSE relationship (a stock build should coincide
    with a price fall), so a matching sign is the "wrong" one; on genuinely unrelated
    data this lands near 0.5 by chance (P(same sign) for two independent ~50/50-signed
    variables), matching the spec's own worked-example expectation."""
    paired = pd.DataFrame({"stocks": delta_stocks_q, "brent": delta_brent_q}).dropna()
    ols = _ols(paired["stocks"], paired["brent"])

    if paired.empty:
        share_wrong_sign = float("nan")
    else:
        same_sign = np.sign(paired["stocks"]) == np.sign(paired["brent"])
        share_wrong_sign = float(same_sign.mean())

    return {
        "slope": ols["slope"],
        "r2": ols["r2"],
        "share_wrong_sign": share_wrong_sign,
        "n": ols["n"],
    }


def shale_response(
    rigs: pd.Series, wti_f12: pd.Series, lags: tuple[int, ...] = (13, 26)
) -> pd.DataFrame:
    """One row per lag in `lags`: regresses delta_rigs = rigs.diff() (y) against
    delta_wti12 = wti_f12.diff(), shifted forward by that lag (x), via _ols -- columns
    lag, beta, t. A single per-lag OLS fit, not a walk-forward rolling-window
    regression -- the spec's own "rolling OLS" phrasing is ambiguous with no window
    size given alongside `lags` (a lag count, not a window length), and a single fit
    is what this session's own "recovers an injected beta" test needs."""
    delta_rigs = rigs.diff()
    delta_wti12 = wti_f12.diff()

    rows = []
    for lag in lags:
        shifted = delta_wti12.shift(lag)
        ols = _ols(shifted, delta_rigs)
        rows.append({"lag": lag, "beta": ols["slope"], "t": ols["t_stat"]})
    return pd.DataFrame(rows)


def benchmark_health(
    window_trades: pd.Series, partials: pd.Series, midland_share: pd.Series, window: int = 756
) -> pd.DataFrame:
    """z-scores of all three inputs over their own trailing `window` (default 756
    trading days ~= 3y, matching core.curve.physical_bands' own window=1260~=5y
    "trading-day window for an 'Ny' convention" precedent). 'thin' = window_trades
    below its own trailing-window 10th percentile -- never a fixed absolute cutoff,
    since a thin market's own baseline differs by benchmark."""

    def _rolling_z(s: pd.Series) -> pd.Series:
        mean = s.rolling(window, min_periods=20).mean()
        std = s.rolling(window, min_periods=20).std()
        result: pd.Series = (s - mean) / std
        return result

    p10 = window_trades.rolling(window, min_periods=20).quantile(0.10)
    thin = window_trades < p10

    return pd.DataFrame(
        {
            "window_trades_z": _rolling_z(window_trades),
            "partials_z": _rolling_z(partials),
            "midland_share_z": _rolling_z(midland_share),
            "thin": thin,
        }
    )


def osp_signal(osp_asia: pd.Series, dubai_m1_m3: pd.Series) -> pd.DataFrame:
    """divergence flag: osp_asia rising (diff > 0) while dubai_m1_m3 is falling
    (diff < 0, i.e. Dubai's own backwardation is weakening/flattening) -- an OSP hike
    not supported by the underlying Dubai structure."""
    combined_index = osp_asia.index.union(dubai_m1_m3.index)
    osp = osp_asia.reindex(combined_index)
    dubai = dubai_m1_m3.reindex(combined_index)
    divergence = (osp.diff() > 0) & (dubai.diff() < 0)
    return pd.DataFrame({"osp_asia": osp, "dubai_m1_m3": dubai, "divergence": divergence})
