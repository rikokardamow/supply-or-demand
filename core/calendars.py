"""Release-calendar constants and next-release lookups. Times are approximate ("~")
for OPEC MOMR and JODI, which publish on a date range/estimate rather than a fixed
schedule — see CLAUDE.md's data release calendar for the source list."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")
_CT = ZoneInfo("America/Chicago")
_CET = ZoneInfo("Europe/Berlin")
_UTC = ZoneInfo("UTC")


@dataclass(frozen=True)
class ReleaseSchedule:
    kind: Literal["weekly", "daily", "monthly"]
    tz: ZoneInfo
    hour: int
    minute: int = 0
    weekday: int | None = None  # Monday=0 .. Sunday=6, weekly only
    day_of_month: int | None = None  # monthly only


RELEASES: dict[str, ReleaseSchedule] = {
    "wpsr": ReleaseSchedule(kind="weekly", tz=_ET, weekday=2, hour=10, minute=30),
    "eia_gas_storage": ReleaseSchedule(kind="weekly", tz=_ET, weekday=3, hour=10, minute=30),
    "agsi": ReleaseSchedule(kind="daily", tz=_CET, hour=19, minute=30),
    "baker_hughes": ReleaseSchedule(kind="weekly", tz=_CT, weekday=4, hour=12, minute=0),
    "cftc_cot": ReleaseSchedule(kind="weekly", tz=_ET, weekday=4, hour=15, minute=30),
    "opec_momr": ReleaseSchedule(kind="monthly", tz=_UTC, day_of_month=12, hour=0),
    "jodi": ReleaseSchedule(kind="monthly", tz=_UTC, day_of_month=20, hour=0),
}


def _next_weekly(now_local: datetime, schedule: ReleaseSchedule) -> datetime:
    assert schedule.weekday is not None
    candidate = now_local.replace(
        hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
    )
    days_ahead = (schedule.weekday - now_local.weekday()) % 7
    candidate += timedelta(days=days_ahead)
    if candidate <= now_local:
        candidate += timedelta(days=7)
    return candidate


def _next_daily(now_local: datetime, schedule: ReleaseSchedule) -> datetime:
    candidate = now_local.replace(
        hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
    )
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


def _next_monthly(now_local: datetime, schedule: ReleaseSchedule) -> datetime:
    assert schedule.day_of_month is not None
    candidate = now_local.replace(
        day=schedule.day_of_month,
        hour=schedule.hour,
        minute=schedule.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now_local:
        if candidate.month == 12:
            candidate = candidate.replace(year=candidate.year + 1, month=1)
        else:
            candidate = candidate.replace(month=candidate.month + 1)
    return candidate


def next_release(name: str, now: datetime) -> datetime:
    schedule = RELEASES[name]
    now_local = now.astimezone(schedule.tz)

    if schedule.kind == "weekly":
        return _next_weekly(now_local, schedule)
    if schedule.kind == "daily":
        return _next_daily(now_local, schedule)
    return _next_monthly(now_local, schedule)
