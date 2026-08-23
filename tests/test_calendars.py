from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from core.calendars import next_release

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
