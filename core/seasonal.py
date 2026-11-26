"""Seasonal range/median maths. 2020 is excluded by default — never reimplement this elsewhere."""

from __future__ import annotations

from datetime import date

import pandas as pd

REFERENCE_YEAR = 2001  # non-leap year, used only to align day-of-year across leap/non-leap years
FIRST_SEASONAL_YEAR = 2018  # earliest year with full coverage across this project's sources
CARRY_DAYS = 14
"""A year's level starts from the previous year's last observation when that lies no more
than this many days before 1 January. A weekly series has no report on 1 January itself, so
without the carry every day before the year's first report is empty."""


def default_years() -> range:
    """Reference window for a seasonal band: `FIRST_SEASONAL_YEAR` up to but *excluding*
    the current calendar year. The current year is left out deliberately -- it is the
    partial track being compared *against* the band, so folding it into the band's own
    lo/hi/median would let it move the very benchmark it is measured by. A caller that
    genuinely wants the current year included (e.g. a multi-year overlay chart, where
    plotting this year beside recent ones is the whole point) passes an explicit range --
    see apps/dashboard/pages/015_us_oil_overview.py.

    Computed per call rather than frozen in a default argument or module constant: this
    was previously the literal `range(2018, 2026)`, which was correct only for as long as
    2026 happened to be the current year and would have silently narrowed the band by a
    year every 1 January thereafter, with no error and no visible change beyond slightly
    different chart bands."""
    return range(FIRST_SEASONAL_YEAR, date.today().year)


def _drop_leap_day(df: pd.DataFrame) -> pd.DataFrame:
    is_leap_day = (df["ts"].dt.month == 2) & (df["ts"].dt.day == 29)
    result: pd.DataFrame = df.loc[~is_leap_day]
    return result


def _normalised_doy(ts: pd.Series) -> pd.Series:
    result: pd.Series = ts.map(lambda d: d.replace(year=REFERENCE_YEAR)).dt.dayofyear
    return result


def _is_leap_day(ts: pd.Series) -> pd.Series:
    result: pd.Series = (ts.dt.month == 2) & (ts.dt.day == 29)
    return result


def reference_doy(ts: pd.Series) -> pd.Series:
    """Day of year on the non-leap reference calendar, for a Series of timestamps, with
    29 February rows dropped (the calendar has no such day; `seasonal_stats` drops it from
    every band too). The result keeps the index of the rows it keeps.

    The one place a date is put on the reference calendar: an open-coded
    `ts.replace(year=2001)` raises on 29 February, which is how the daily charts broke
    for all of 2028."""
    ts = pd.to_datetime(ts)
    kept = ts[~_is_leap_day(ts)]
    after_feb_in_leap_year = kept.dt.is_leap_year & (kept.dt.month > 2)
    result: pd.Series = kept.dt.dayofyear - after_feb_in_leap_year.astype(int)
    return result


def reference_date_clamped(ts: pd.Timestamp) -> pd.Timestamp:
    """One date on the reference calendar. 29 February becomes 28 February (a single date
    must land somewhere; a Series goes through `reference_doy`, which drops it)."""
    day = 28 if (ts.month == 2 and ts.day == 29) else ts.day
    return pd.Timestamp(year=REFERENCE_YEAR, month=ts.month, day=day)


def reference_doy_clamped(ts: pd.Timestamp) -> int:
    """Day of year of one date on the reference calendar, 29 February taken as the 28th."""
    return int(reference_date_clamped(ts).dayofyear)


def current_year_rows(df: pd.DataFrame, value_col: str = "value") -> pd.DataFrame:
    """The latest calendar year's rows (ts, value_col), oldest first, 29 February dropped."""
    latest = df[df["ts"].dt.year == df["ts"].dt.year.max()].sort_values("ts")
    rows: pd.DataFrame = latest.loc[~_is_leap_day(latest["ts"]), ["ts", value_col]]
    return rows


def current_track(df: pd.DataFrame, value_col: str = "value") -> pd.Series:
    """The latest calendar year's values indexed by reference day of year, 29 February
    dropped: the track a seasonal chart draws against `seasonal_stats`' band."""
    rows = current_year_rows(df, value_col)
    return pd.Series(
        rows[value_col].to_numpy(),
        index=pd.Index(reference_doy(rows["ts"]).to_numpy(), name="doy"),
    )


def _daily_ffill_by_year(df: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Forward-fill each calendar year's series onto a dense daily grid.

    Source series here are weekly (EIA releases), and weekly release dates drift
    by a day or two year to year — pivoting on exact day-of-year would leave
    almost every day with data from at most one year, making cross-year
    lo/hi/median meaningless. Forward-filling (the value holds until the next
    report) is the standard treatment for these storage/inventory seasonal charts
    and gives every day-of-year real overlap. The fill starts from the previous
    year's last observation when it is at most `CARRY_DAYS` before 1 January, so
    the first days of January are not empty; a longer gap is left as NaN.
    """
    ordered = df.sort_values("ts")
    frames = []
    for year, year_df in ordered.groupby(ordered["ts"].dt.year):
        series = year_df.set_index("ts")[value_col]
        jan1 = pd.Timestamp(f"{year}-01-01")
        previous = ordered[ordered["ts"] < jan1]
        if not previous.empty and (jan1 - previous["ts"].iloc[-1]).days <= CARRY_DAYS:
            # The level that held at the turn of the year, until this year's first report.
            seed = previous.iloc[[-1]].set_index("ts")[value_col]
            series = pd.concat([seed, series])
        daily_index = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        daily_values = series.reindex(daily_index, method="ffill")
        frames.append(pd.DataFrame({"ts": daily_index, value_col: daily_values.to_numpy()}))
    return pd.concat(frames, ignore_index=True)


def seasonal_stats(
    df: pd.DataFrame,
    value_col: str,
    years: range | None = None,
    exclude: tuple[int, ...] = (2020,),
) -> pd.DataFrame:
    if years is None:
        years = default_years()
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
