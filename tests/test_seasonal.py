from __future__ import annotations

import pandas as pd
from core.seasonal import seasonal_stats


def _value_for(date: pd.Timestamp) -> float:
    # Deterministic function of (month, day) only, so every year produces the
    # same value at the same calendar point unless we deliberately override it.
    return 100.0 + date.month * 10 + date.day


def _build_synthetic_df(years: range, outlier: tuple[int, int, int, float]) -> pd.DataFrame:
    outlier_year, outlier_month, outlier_day, outlier_value = outlier
    rows: list[dict[str, object]] = []

    for year in years:
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        for date in dates:
            value = _value_for(date)
            if year == outlier_year and date.month == outlier_month and date.day == outlier_day:
                value = outlier_value
            rows.append({"ts": date, "value": value})

    return pd.DataFrame(rows)


def test_2020_outlier_does_not_widen_band() -> None:
    df = _build_synthetic_df(range(2018, 2026), outlier=(2020, 7, 1, 9999.0))

    stats = seasonal_stats(df, value_col="value")

    expected = _value_for(pd.Timestamp("2001-07-01"))
    doy = pd.Timestamp("2001-07-01").dayofyear

    assert stats.loc[doy, "hi"] == expected
    assert stats.loc[doy, "lo"] == expected
    assert stats.loc[doy, "median"] == expected
    assert "2020" not in [c for c in stats.columns if c not in ("lo", "hi", "median")]


def test_leap_day_is_dropped() -> None:
    df = _build_synthetic_df(range(2018, 2026), outlier=(2020, 7, 1, 9999.0))

    stats = seasonal_stats(df, value_col="value")

    assert len(stats) == 365
    assert stats.index.max() == 365


def _build_weekly_df(years: range) -> pd.DataFrame:
    # Weekly release dates drift a few days year to year, same as real EIA
    # data — exact day-of-year rarely lines up across years without ffill.
    rows: list[dict[str, object]] = []
    for i, year in enumerate(years):
        start = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=i % 7)
        dates = pd.date_range(start, f"{year}-12-31", freq="7D")
        for date in dates:
            rows.append({"ts": date, "value": _value_for(date)})
    return pd.DataFrame(rows)


def test_weekly_data_is_ffilled_before_pivoting() -> None:
    # Regression: pivoting on exact day-of-year without ffill leaves almost
    # every day with at most one year's data, so lo/hi/median collapse to
    # that single point instead of a real cross-year band.
    df = _build_weekly_df(range(2018, 2026))

    stats = seasonal_stats(df, value_col="value")
    year_cols = [c for c in stats.columns if c not in ("lo", "hi", "median")]

    assert stats["median"].notna().sum() > 350
    overlap = (stats[year_cols].notna().sum(axis=1) > 1).sum()
    assert overlap > 350
