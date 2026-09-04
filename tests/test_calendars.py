from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from core.calendars import next_release, roll_calendar, roll_window_flag

_UTC = ZoneInfo("UTC")


def test_wpsr_is_wednesday() -> None:
    now = datetime(2026, 8, 24, 0, 0, tzinfo=_UTC)  # a Monday
    result = next_release("wpsr", now)
    assert result.weekday() == 2  # Wednesday


def test_eia_gas_storage_is_thursday() -> None:
    now = datetime(2026, 8, 24, 0, 0, tzinfo=_UTC)
    result = next_release("eia_gas_storage", now)
    assert result.weekday() == 3  # Thursday


def test_baker_hughes_is_friday() -> None:
    now = datetime(2026, 8, 24, 0, 0, tzinfo=_UTC)
    result = next_release("baker_hughes", now)
    assert result.weekday() == 4  # Friday


def test_cftc_cot_is_friday() -> None:
    now = datetime(2026, 8, 24, 0, 0, tzinfo=_UTC)
    result = next_release("cftc_cot", now)
    assert result.weekday() == 4  # Friday


def test_weekly_release_rolls_to_next_week_once_time_has_passed() -> None:
    # Wednesday, but already past 10:30 ET (WPSR release time) -> next Wednesday, not today.
    now = datetime(2026, 8, 26, 20, 0, tzinfo=ZoneInfo("America/New_York"))
    result = next_release("wpsr", now)
    assert result.weekday() == 2
    assert result.date() != now.date()


def test_agsi_is_daily_at_1930_cet() -> None:
    now = datetime(2026, 8, 24, 10, 0, tzinfo=_UTC)
    result = next_release("agsi", now)
    assert result.hour == 19
    assert result.minute == 30
    assert result.tzinfo is not None


def test_opec_momr_anchors_mid_month() -> None:
    now = datetime(2026, 1, 1, tzinfo=_UTC)
    result = next_release("opec_momr", now)
    assert result.day == 12
    assert result.month == 1


def test_jodi_anchors_20th() -> None:
    now = datetime(2026, 1, 1, tzinfo=_UTC)
    result = next_release("jodi", now)
    assert result.day == 20
    assert result.month == 1


def test_monthly_release_rolls_to_next_month_once_day_has_passed() -> None:
    now = datetime(2026, 1, 25, tzinfo=_UTC)
    result = next_release("jodi", now)
    assert result.month == 2
    assert result.day == 20


# --- Session C: roll_calendar / roll_window_flag ---
# Real January 2026 business days (Mon-Fri, hand-verified: Jan 1 2026 is a Thursday):
# 1,2,5,6,7,8,9,12,13,14,15,16,19,20,21,22,23,26,27,28,29,30 -- so business days 5-9 are
# Jan 7/8/9/12/13, and business days 6-10 are Jan 8/9/12/13/14.


def test_gsci_roll_calendar_jan_2026_matches_hand_verified_business_days() -> None:
    cal = roll_calendar(2026, "gsci")
    jan = cal[cal["date"].dt.month == 1]
    assert list(jan["date"].dt.day) == [7, 8, 9, 12, 13]
    assert jan["fraction"].sum() == pytest.approx(1.0)


def test_bcom_roll_calendar_jan_2026_matches_hand_verified_business_days() -> None:
    cal = roll_calendar(2026, "bcom")
    jan = cal[cal["date"].dt.month == 1]
    assert list(jan["date"].dt.day) == [8, 9, 12, 13, 14]
    assert jan["fraction"].sum() == pytest.approx(1.0)


def test_roll_calendar_every_month_fractions_sum_to_one() -> None:
    for index in ("gsci", "bcom"):
        cal = roll_calendar(2026, index)
        for _month, group in cal.groupby(cal["date"].dt.month):
            assert group["fraction"].sum() == pytest.approx(1.0)


def test_roll_calendar_rejects_unknown_index() -> None:
    with pytest.raises(ValueError):
        roll_calendar(2026, "spgsci")


def test_roll_window_flag_true_only_inside_the_real_gsci_window() -> None:
    dates = pd.DatetimeIndex(["2026-01-07", "2026-01-08", "2026-01-06", "2026-01-14"])
    flag = roll_window_flag(dates, 2026, "gsci")
    assert flag.tolist() == [True, True, False, False]


def test_roll_window_flag_false_for_a_date_outside_the_given_year() -> None:
    dates = pd.DatetimeIndex(["2027-01-07"])
    flag = roll_window_flag(dates, 2026, "gsci")
    assert flag.tolist() == [False]
