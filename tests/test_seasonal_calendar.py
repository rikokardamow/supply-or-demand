"""29 February on the seasonal reference calendar (I-19).

`core.seasonal` aligns years on the non-leap 2001 calendar and drops 29 February from every
band. The current year's own track and single dates must be put on the same calendar without
`Timestamp.replace(year=2001)`, which raises on 29 February.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
from apps.exhibits import readme_charts
from core import seasonal

ROOT = Path(__file__).resolve().parent.parent


def _daily_constant(start: str, end: str, value: float = 50.0) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"ts": ts, "value": value})


def test_the_daily_panel_is_drawn_through_29_february() -> None:
    # Daily constant 50.0 from 2022-01-01 to 2028-03-05; 2028-02-29 is in the track. The
    # panel used to raise "day 29 must be in range 1..28 for month 2 in year 2001".
    df = _daily_constant("2022-01-01", "2028-03-05")
    _, ax = readme_charts.new_figure()
    latest, median = readme_charts.seasonal_panel(ax, df, lambda v, t: (f"{v:.0f}", f"{t:%b %-d}"))
    assert (latest, median) == (50.0, 50.0)


def test_the_current_track_drops_29_february_and_has_no_duplicate_day() -> None:
    track = seasonal.current_track(_daily_constant("2022-01-01", "2028-03-05"))
    # Jan 31 + Feb 29 + Mar 5 = 65 days, minus 29 February.
    assert len(track) == 64
    assert track.index.is_unique
    assert track.index[0] == 1
    assert track.index[-1] == 64  # 5 March on the 2001 calendar: 31 + 28 + 5


def test_the_current_track_on_a_non_leap_year_is_the_plain_day_of_year() -> None:
    track = seasonal.current_track(_daily_constant("2025-01-01", "2026-03-05"))
    assert len(track) == 64 and list(track.index[:3]) == [1, 2, 3]


def test_the_current_track_of_a_weekly_series_keeps_only_the_latest_year() -> None:
    ts = pd.to_datetime(["2027-12-31", "2028-01-07", "2028-02-29", "2028-03-07"])
    df = pd.DataFrame({"ts": ts, "value": [1.0, 2.0, 3.0, 4.0]})
    track = seasonal.current_track(df)
    assert list(track.index) == [7, 66]  # Jan 7, and Mar 7 = 31 + 28 + 7
    assert list(track) == [2.0, 4.0]


def test_reference_doy_drops_29_february_rows_and_keeps_the_others_aligned() -> None:
    ts = pd.Series(pd.to_datetime(["2028-02-28", "2028-02-29", "2028-03-01", "2028-12-31"]))
    doy = seasonal.reference_doy(ts)
    assert list(doy) == [59, 60, 365]
    # Whatever the year, the same calendar date has the same reference day.
    assert seasonal.reference_doy(pd.Series(pd.to_datetime(["2027-03-01"]))).iloc[0] == 60


def test_reference_doy_of_nothing_is_nothing() -> None:
    assert seasonal.reference_doy(pd.Series([], dtype="datetime64[ns]")).empty


def test_a_single_date_on_29_february_takes_the_28th() -> None:
    assert seasonal.reference_doy_clamped(pd.Timestamp("2028-02-29")) == 59
    assert seasonal.reference_doy_clamped(pd.Timestamp("2028-02-28")) == 59
    assert seasonal.reference_doy_clamped(pd.Timestamp("2028-03-01")) == 60
    assert seasonal.reference_doy_clamped(pd.Timestamp("2027-07-04")) == 185
    assert seasonal.reference_date_clamped(pd.Timestamp("2028-02-29")) == pd.Timestamp(
        "2001-02-28"
    )


def test_no_module_outside_core_seasonal_puts_a_date_on_the_reference_year_itself() -> None:
    # DEVELOPMENT.md rule 4: seasonal maths lives in core.seasonal. An open-coded
    # `replace(year=2001)` raises on 29 February (I-19).
    pattern = re.compile(r"replace\(\s*year\s*=\s*(2001|REFERENCE_YEAR)\b")
    offenders = []
    for folder in ("apps", "core", "pipelines", "infra", "tools"):
        for path in (ROOT / folder).rglob("*.py"):
            if path == ROOT / "core" / "seasonal.py" or ".venv" in path.parts:
                continue
            if pattern.search(path.read_text()):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_the_inventory_pipeline_survives_a_report_dated_29_february(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.storage import read_ts_long, write_ts_long
    from pipelines.derived import fundamentals

    monkeypatch.chdir(tmp_path)
    ts = pd.date_range("2022-01-04", "2028-03-07", freq="W-TUE")  # 2028-02-29 is a Tuesday
    assert pd.Timestamp("2028-02-29") in ts
    levels = {y: 400.0 + 2 * (y % 5) for y in range(2022, 2029)}
    write_ts_long(
        pd.DataFrame(
            {
                "series_id": fundamentals.US_CRUDE_STOCKS_SERIES_ID,
                "source": "eia",
                "ts": ts,
                "value": [levels[t.year] + 0.1 * t.month for t in ts],
                "unit": "mb",
                "geo": "US",
                "freq": "W",
                "revision_date": pd.Timestamp("2028-03-08"),
            }
        ),
        source="eia",
    )

    written = fundamentals._pull_inventory_deviation(pd.Timestamp("2028-03-08"))

    rows = read_ts_long(series_ids=["derived.inv.dev_z.uscrude"])
    assert written == len(rows) > 0
    # The 29 February report has no day on the reference calendar, so it is the one row
    # not written; the 2028-03-07 report is.
    assert pd.Timestamp("2028-02-29") not in set(rows["ts"])
    assert pd.Timestamp("2028-03-07") in set(rows["ts"])
