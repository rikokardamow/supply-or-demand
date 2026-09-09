from __future__ import annotations

from datetime import date

import pandas as pd
from core.publish import SEASONAL_COLUMNS, seasonal_rows


def _series(values_by_year: dict[int, float]) -> pd.DataFrame:
    """A daily ts_long-shaped frame, one constant value per year."""
    frames = []
    for year, value in values_by_year.items():
        end = date(year, 12, 31) if year < date.today().year else date.today()
        ts = pd.date_range(f"{year}-01-01", end, freq="D")
        frames.append(pd.DataFrame({"ts": ts, "value": [value] * len(ts)}))
    return pd.concat(frames, ignore_index=True)


def _band_years() -> list[int]:
    """Years core.seasonal's own default window covers, 2020 excluded."""
    return [y for y in range(2018, date.today().year) if y != 2020]


def test_seasonal_rows_returns_exactly_the_serving_seasonal_columns() -> None:
    df = _series({y: 100.0 for y in _band_years()})

    rows = seasonal_rows(df, series_id="agsi.DE.full_pct", unit="%")

    assert list(rows.columns) == list(SEASONAL_COLUMNS)
    assert set(rows["series_id"]) == {"agsi.DE.full_pct"}
    assert set(rows["unit"]) == {"%"}
    assert rows["doy"].between(1, 365).all()
    assert not rows["doy"].duplicated().any()  # doy is half the primary key


def test_seasonal_rows_excludes_2020_from_the_band() -> None:
    # Golden rule 4: seasonal maths ALWAYS exclude 2020. A 2020 outlier must not widen
    # the band -- if it leaked in, band_max would be 999 rather than 100.
    values = {y: 100.0 for y in _band_years()}
    values[2020] = 999.0
    df = _series(values)

    rows = seasonal_rows(df, series_id="agsi.DE.full_pct", unit="%")

    assert rows["band_max"].max() == 100.0
    assert rows["band_min"].min() == 100.0
    assert rows["median"].max() == 100.0


def test_seasonal_rows_keeps_the_current_year_out_of_the_band_but_reports_it_as_current() -> None:
    # The current year is the track being compared *against* the band, so folding it in
    # would let it move the very benchmark it is measured by (core.seasonal.default_years).
    this_year = date.today().year
    values = {y: 100.0 for y in _band_years()}
    values[this_year] = 50.0
    df = _series(values)

    rows = seasonal_rows(df, series_id="agsi.DE.full_pct", unit="%")

    assert rows["band_min"].min() == 100.0  # 50.0 must not widen the band downward
    current = rows.loc[rows["current"].notna(), "current"]
    assert not current.empty
    assert set(current) == {50.0}


def test_seasonal_rows_reports_the_prior_year_and_the_band_width_in_years() -> None:
    this_year = date.today().year
    values = {y: 100.0 for y in _band_years()}
    values[this_year - 1] = 77.0
    values[this_year] = 50.0
    df = _series(values)

    rows = seasonal_rows(df, series_id="agsi.DE.full_pct", unit="%")

    prior = rows.loc[rows["prior"].notna(), "prior"]
    assert set(prior) == {77.0}
    assert set(rows["years"]) == {len(_band_years())}


def test_seasonal_rows_is_empty_for_a_series_with_no_usable_history() -> None:
    # A series whose only data is the current year has no band to compare against.
    # Returning an empty frame (rather than rows of NaN) keeps serving.seasonal honest.
    df = _series({date.today().year: 42.0})

    rows = seasonal_rows(df, series_id="agsi.DE.full_pct", unit="%")

    assert rows.empty
    assert list(rows.columns) == list(SEASONAL_COLUMNS)


def test_seasonal_frame_stacks_every_series_and_carries_its_own_unit() -> None:
    from core.publish import seasonal_frame

    band = _series({y: 100.0 for y in _band_years()})
    a = band.assign(series_id="agsi.DE.full_pct", unit="%")
    b = band.assign(series_id="alsi.ES.lng_inventory", unit="1000 m3")

    frame = seasonal_frame(pd.concat([a, b], ignore_index=True))

    assert set(frame["series_id"]) == {"agsi.DE.full_pct", "alsi.ES.lng_inventory"}
    units = frame.drop_duplicates("series_id").set_index("series_id")["unit"].to_dict()
    assert units == {"agsi.DE.full_pct": "%", "alsi.ES.lng_inventory": "1000 m3"}
    assert list(frame.columns) == list(SEASONAL_COLUMNS)


def test_seasonal_frame_drops_series_with_no_usable_band_but_keeps_the_others() -> None:
    # A series that only exists in the current year contributes no band. It must be
    # skipped rather than emitting NaN rows or taking the whole publish down with it.
    from core.publish import seasonal_frame

    good = _series({y: 100.0 for y in _band_years()}).assign(series_id="good", unit="%")
    thin = _series({date.today().year: 42.0}).assign(series_id="thin", unit="%")

    frame = seasonal_frame(pd.concat([good, thin], ignore_index=True))

    assert set(frame["series_id"]) == {"good"}


def test_seasonal_rows_leaves_current_null_for_days_that_have_not_happened_yet() -> None:
    # core.seasonal forward-fills to daily within each year, which is right for a
    # complete year but fabricates the current one: it carries today's value flat to 31
    # December. serving.seasonal's own schema says `current` is "null if not yet", and a
    # flat forward-fill would draw a fake projection across the UI's seasonal chart.
    values = {y: 100.0 for y in _band_years()}
    values[date.today().year] = 50.0
    rows = seasonal_rows(_series(values), series_id="agsi.DE.full_pct", unit="%")

    today_doy = date.today().replace(year=2001).timetuple().tm_yday
    future = rows.loc[rows["doy"] > today_doy, "current"]
    past = rows.loc[rows["doy"] <= today_doy, "current"]

    assert future.isna().all(), "current must be null for days that have not happened yet"
    assert past.notna().any(), "current must still carry this year's real track"


def test_seasonal_rows_still_fills_the_prior_year_across_the_whole_curve() -> None:
    # The prior year is complete, so filling it is legitimate -- only the current year's
    # future is fabrication. Guards against over-correcting the fix above.
    values = {y: 100.0 for y in _band_years()}
    values[date.today().year - 1] = 77.0
    rows = seasonal_rows(_series(values), series_id="agsi.DE.full_pct", unit="%")

    today_doy = date.today().replace(year=2001).timetuple().tm_yday
    assert rows.loc[rows["doy"] > today_doy, "prior"].notna().any()


def test_seasonal_rows_tolerates_duplicate_timestamps_in_the_incoming_frame() -> None:
    # core.seasonal._daily_ffill_by_year reindexes a ts-indexed series onto a daily
    # grid, which requires unique timestamps -- a duplicate raises "cannot reindex on an
    # axis with duplicate labels". The lake never holds duplicates (write_ts_long dedups
    # on (series_id, ts)), but a caller passing a freshly *pulled* frame can: confirmed
    # live 2026-09-09, EIA's pagination returns a few boundary rows twice, which took
    # down the WPSR seasonal publish. Cleaning the input is the serving layer's job --
    # core.seasonal is shared by every dashboard page and is not changed for this.
    df = _series({y: 100.0 for y in _band_years()})
    with_dupes = pd.concat([df, df.iloc[[0, 5, 9]]], ignore_index=True)

    rows = seasonal_rows(with_dupes, series_id="agsi.DE.full_pct", unit="%")

    assert not rows.empty
    assert rows["band_max"].max() == 100.0
