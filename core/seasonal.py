"""Seasonal range/median maths. 2020 is excluded by default — never reimplement this elsewhere."""

from __future__ import annotations

import pandas as pd

_REFERENCE_YEAR = 2001  # non-leap year, used only to align day-of-year across leap/non-leap years


def _drop_leap_day(df: pd.DataFrame) -> pd.DataFrame:
    is_leap_day = (df["ts"].dt.month == 2) & (df["ts"].dt.day == 29)
    result: pd.DataFrame = df.loc[~is_leap_day]
    return result


def _normalised_doy(ts: pd.Series) -> pd.Series:
    result: pd.Series = ts.map(lambda d: d.replace(year=_REFERENCE_YEAR)).dt.dayofyear
    return result


def _daily_ffill_by_year(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Forward-fill each calendar year's series onto a dense daily grid.

    Source series here are weekly (EIA releases), and weekly release dates drift
    by a day or two year to year — pivoting on exact day-of-year would leave
    almost every day with data from at most one year, making cross-year
    lo/hi/median meaningless. Forward-filling within each year (the value holds
    until the next report) is the standard treatment for these storage/
    inventory seasonal charts and gives every day-of-year real overlap.
    """
    frames = []
    for year, year_df in df.groupby(df["ts"].dt.year):
        series = year_df.sort_values("ts").set_index("ts")[value_col]
        daily_index = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        daily_values = series.reindex(daily_index, method="ffill")
        frames.append(pd.DataFrame({"ts": daily_index, value_col: daily_values.to_numpy()}))
    return pd.concat(frames, ignore_index=True)


def seasonal_stats(
    df: pd.DataFrame,
    value_col: str,
    years: range = range(2018, 2026),
    exclude: tuple[int, ...] = (2020,),
) -> pd.DataFrame:
    daily = _daily_ffill_by_year(df, value_col)
    data = _drop_leap_day(daily).copy()
    data["year"] = data["ts"].dt.year
    data["doy"] = _normalised_doy(data["ts"])

    included_years = [y for y in years if y not in exclude]
    data = data[data["year"].isin(included_years)]

    pivot = data.pivot_table(index="doy", columns="year", values=value_col)

    stats = pd.DataFrame(index=pivot.index)
    stats["lo"] = pivot.min(axis=1)
    stats["hi"] = pivot.max(axis=1)
    stats["median"] = pivot.median(axis=1)
    for year in pivot.columns:
        stats[str(year)] = pivot[year]

    return stats.sort_index()


def yoy(df: pd.DataFrame, value_col: str = "value") -> pd.Series:
    daily = _daily_ffill_by_year(df, value_col)
    data = _drop_leap_day(daily).copy()
    data["year"] = data["ts"].dt.year
    data["doy"] = _normalised_doy(data["ts"])

    pivot = data.pivot_table(index="doy", columns="year", values=value_col)
    years_sorted = sorted(pivot.columns)
    if len(years_sorted) < 2:
        return pd.Series(dtype=float)

    current_year, previous_year = years_sorted[-1], years_sorted[-2]
    return (pivot[current_year] - pivot[previous_year]) / pivot[previous_year]
