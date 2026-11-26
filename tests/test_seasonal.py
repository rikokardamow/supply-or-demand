from __future__ import annotations

import datetime

import pandas as pd
import pytest
from core.seasonal import FIRST_SEASONAL_YEAR, default_years, seasonal_stats


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


def test_default_years_excludes_the_current_year() -> None:
    years = default_years()

    assert years.start == FIRST_SEASONAL_YEAR
    assert datetime.date.today().year not in years
    assert datetime.date.today().year - 1 in years


def test_default_years_tracks_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: the window was the literal `range(2018, 2026)`, so it silently stopped
    widening once 2026 was no longer the current year. It must follow the calendar."""

    class _FakeDate(datetime.date):
        @classmethod
        def today(cls) -> datetime.date:
            return datetime.date(2031, 3, 1)

    monkeypatch.setattr("core.seasonal.date", _FakeDate)

    assert default_years() == range(FIRST_SEASONAL_YEAR, 2031)


def test_seasonal_stats_uses_the_default_window_when_years_is_none() -> None:
    last_complete_year = datetime.date.today().year - 1
    df = _build_synthetic_df(
        range(FIRST_SEASONAL_YEAR, last_complete_year + 1), outlier=(2020, 7, 1, 9999.0)
    )

    stats = seasonal_stats(df, value_col="value")
    year_cols = [c for c in stats.columns if c not in ("lo", "hi", "median")]

    assert str(last_complete_year) in year_cols
    assert "2020" not in year_cols


# --- the level carries over the new year (I-16) ----------------------------------------


def _weekly_by_year(start: str, end: str) -> pd.DataFrame:
    # W-FRI, every observation in year y valued y - 2000 (21 to 27 for 2021 to 2027).
    ts = pd.date_range(start, end, freq="W-FRI")
    return pd.DataFrame({"ts": ts, "value": (ts.year - 2000).astype(float)})


def test_the_last_december_report_holds_until_the_first_january_one() -> None:
    df = _weekly_by_year("2021-01-01", "2027-01-01")
    stats = seasonal_stats(df, "value", years=range(2022, 2027))
    # Day 1 of 2022..2026 carries 2021-12-31 (21), 2022-12-30 (22), 2023-12-29 (23),
    # 2024-12-27 (24) and 2025-12-26 (25): median 23, lo 21, hi 25.
    assert 1 in stats.index
    assert stats.loc[1, "median"] == 23.0
    assert stats.loc[1, "lo"] == 21.0
    assert stats.loc[1, "hi"] == 25.0
    assert [stats.loc[1, str(y)] for y in range(2022, 2027)] == [21.0, 22.0, 23.0, 24.0, 25.0]


def test_the_carry_does_not_move_any_value_after_a_years_first_report() -> None:
    df = _weekly_by_year("2021-01-01", "2027-01-01")
    stats = seasonal_stats(df, "value", years=range(2022, 2027))
    # 2022's first report is Jan 7 (day 7); from there every year is its own value.
    for y in range(2022, 2027):
        assert stats.loc[10, str(y)] == float(y - 2000)
        assert stats.loc[365, str(y)] == float(y - 2000)


def test_a_gap_longer_than_the_carry_is_not_bridged() -> None:
    # Last observation 2025-12-02 (30 days before 1 January), first of 2026 on 2026-01-15.
    ts = pd.to_datetime(["2024-01-05", "2024-12-27", "2025-01-03", "2025-12-02", "2026-01-15"])
    df = pd.DataFrame({"ts": ts, "value": [1.0, 2.0, 3.0, 4.0, 5.0]})
    stats = seasonal_stats(df, "value", years=range(2026, 2027))
    assert stats.loc[1:14, "2026"].isna().all()
    assert stats.loc[15, "2026"] == 5.0
