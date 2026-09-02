"""Macro/FX normalisation helpers (Spec 10) -- shared by every page that needs to
separate a nominal price move from currency/inflation effects, so this logic isn't
duplicated per page. Pure transforms: take/return plain pd.Series indexed by ts
(matching every page's own _series_by_ts convention) -- no lake I/O here."""

from __future__ import annotations

from typing import cast

import pandas as pd


def deflate(series: pd.Series, cpi_series: pd.Series, base_period: str) -> pd.Series:
    """Converts a nominal `series` into real terms, indexed to `base_period`'s CPI
    level (e.g. base_period="2018-01-01" -> "2018 dollars"). `cpi_series` is
    forward-filled onto `series`'s own dates first -- CPI/HICP is monthly, `series`
    may be daily/weekly, same reasoning as to_currency's FX alignment below."""
    cpi_aligned = cpi_series.reindex(series.index, method="ffill")
    base_cpi = cast(float, cpi_series.asof(pd.Timestamp(base_period)))
    result: pd.Series = series * (base_cpi / cpi_aligned)
    return result


def to_currency(series: pd.Series, fx_series: pd.Series, target: str) -> pd.Series:
    """Converts a USD-denominated `series` into `target` currency using an
    `fx.usd_{ccy}`-style rate series (pipelines/macro/frankfurter_client.py's own
    convention: "how many `target` units you get for 1 USD" -- a plain
    multiply-to-convert factor, so no inversion arithmetic here). `fx_series` is
    forward-filled onto `series`'s own dates first -- FX is daily, `series` may be
    weekly/monthly. `target` isn't used in the calculation itself (the caller already
    picked the matching `fx.usd_{target.lower()}` series before calling this) -- kept
    only for signature parity with the spec's own `to_currency(series, fx_series,
    target)`."""
    fx_aligned = fx_series.reindex(series.index, method="ffill")
    result: pd.Series = series * fx_aligned
    return result


def _median_step(series: pd.Series) -> pd.Timedelta:
    diffs = series.index.to_series().diff().dropna()
    return pd.Timedelta(diffs.median())


def align_freq(a: pd.Series, b: pd.Series, how: str = "mean") -> tuple[pd.Series, pd.Series]:
    """Resamples the finer-grained of the two series down to the coarser one's own
    frequency (aggregating via `how` -- "mean"/"sum"/"last"/etc.), then returns both
    reindexed onto their shared dates. Frequency is inferred from each series' own
    median index spacing, not assumed -- a daily crude price against a monthly CPI
    print is the common real case this exists for."""
    step_a, step_b = _median_step(a), _median_step(b)
    if step_a >= step_b:
        coarse, fine, coarse_is_a = a, b, True
    else:
        coarse, fine, coarse_is_a = b, a, False

    # pd.infer_freq raises (not returns None) for fewer than 3 points -- confirmed
    # live by a failing test on a genuinely realistic 2-point toy series -- so the
    # day-count fallback below has to be reachable from a raise, not just a None.
    try:
        coarse_freq = pd.infer_freq(cast(pd.DatetimeIndex, coarse.index))
    except ValueError:
        coarse_freq = None
    if coarse_freq is None:
        coarse_freq = f"{max(int(_median_step(coarse) / pd.Timedelta(days=1)), 1)}D"
    fine_resampled = fine.resample(coarse_freq).agg(how)

    common_index = coarse.index.intersection(fine_resampled.index)
    coarse_aligned = coarse.reindex(common_index)
    fine_aligned = fine_resampled.reindex(common_index)

    return (coarse_aligned, fine_aligned) if coarse_is_a else (fine_aligned, coarse_aligned)


def year_over_year(series: pd.Series, periods: int = 12) -> pd.Series:
    """Percent change vs `periods` observations ago (default 12, matching a monthly
    series' own YoY convention -- pass a different `periods` for a non-monthly
    series, e.g. 4 for quarterly)."""
    result: pd.Series = (series / series.shift(periods) - 1) * 100
    return result


def zscore(series: pd.Series) -> pd.Series:
    """Full-sample z-score: (value - mean) / std, using the series' own history as
    its reference distribution."""
    result: pd.Series = (series - series.mean()) / series.std()
    return result


def index_to(series: pd.Series, base_period: str, base_value: float = 100.0) -> pd.Series:
    """Rescales `series` so its value at `base_period` equals `base_value` (e.g.
    base_period="2018-01-01" -> "2018=100"). Used for the spec's own "real vs nominal
    crude, indexed 2018=100" visual -- apply to both a nominal series and its
    `deflate()`-d real counterpart to make them visually comparable on one axis."""
    base = cast(float, series.asof(pd.Timestamp(base_period)))
    result: pd.Series = series / base * base_value
    return result
