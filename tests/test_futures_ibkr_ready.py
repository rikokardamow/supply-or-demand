from __future__ import annotations

from datetime import date
from itertools import pairwise

import pytest
from pipelines.futures.client import IB_MAX_DAYS_PER_REQUEST, duration_windows
from pipelines.futures.ibkr_preflight import GATEWAY_PORTS, preflight

# --- request chunking -------------------------------------------------------------


def test_a_short_span_is_a_single_request() -> None:
    windows = duration_windows(date(2026, 1, 1), date(2026, 3, 1))
    assert windows == [(date(2026, 1, 1), date(2026, 3, 1))]


def test_a_multi_decade_backfill_is_split_into_requests_ib_will_accept() -> None:
    """IB's historical API caps the duration of a single daily-bar request, so
    pull_history's own 1993-present span cannot go out as one call."""
    windows = duration_windows(date(1993, 1, 1), date(2026, 9, 1))
    assert len(windows) > 30
    for start, end in windows:
        assert (end - start).days <= IB_MAX_DAYS_PER_REQUEST


def test_the_windows_cover_the_whole_span_without_gaps_or_overlaps() -> None:
    start, end = date(2000, 1, 1), date(2010, 6, 15)
    windows = duration_windows(start, end)
    assert windows[0][0] == start
    assert windows[-1][1] == end
    for (_, previous_end), (next_start, _) in pairwise(windows):
        assert next_start == previous_end


def test_a_single_day_span_still_produces_one_window() -> None:
    day = date(2026, 5, 4)
    assert duration_windows(day, day) == [(day, day)]


def test_an_inverted_span_is_rejected_rather_than_silently_empty() -> None:
    with pytest.raises(ValueError, match="before"):
        duration_windows(date(2026, 5, 4), date(2026, 5, 1))


# --- preflight --------------------------------------------------------------------


def test_preflight_checks_every_documented_gateway_port() -> None:
    """7497/7496 are TWS paper/live, 4002/4001 are the Gateway's own pair."""
    assert GATEWAY_PORTS == (7497, 7496, 4002, 4001)


def test_preflight_reports_not_ready_when_no_port_is_listening() -> None:
    report = preflight(port_open=lambda host, port: False)
    assert report["ready"] is False
    assert report["open_ports"] == []
    assert "gateway" in report["blocker"].lower()


def test_preflight_reports_ready_when_the_gateway_is_listening() -> None:
    report = preflight(port_open=lambda host, port: port == 4002)
    assert report["ready"] is True
    assert report["open_ports"] == [4002]
    assert report["blocker"] is None


def test_preflight_names_the_configured_host_and_port() -> None:
    """A reachable port that isn't the one in settings is still a misconfiguration --
    the report has to show both so the mismatch is visible."""
    report = preflight(port_open=lambda host, port: port == 4002)
    assert "configured_port" in report
    assert "configured_host" in report


def test_preflight_flags_a_configured_port_that_is_not_listening() -> None:
    report = preflight(port_open=lambda host, port: port == 4002, configured_port=7497)
    assert report["configured_port_open"] is False
    assert report["ready"] is True  # something is listening, just not the configured one


def test_preflight_never_raises_when_the_probe_itself_fails() -> None:
    """A socket probe that throws must degrade to "closed", not abort the check."""

    def exploding(host: str, port: int) -> bool:
        raise OSError("network unreachable")

    report = preflight(port_open=exploding)
    assert report["ready"] is False
