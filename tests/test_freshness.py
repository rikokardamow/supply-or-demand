from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from core.freshness import (
    EXPECTED_CADENCE_DAYS,
    SANCTIONS_FRESHNESS_KEY,
    _status,
    staleness_report,
)


def test_status_boundaries() -> None:
    assert _status(2.0, expected_days=2) == "green"
    assert _status(2.01, expected_days=2) == "amber"
    assert _status(4.0, expected_days=2) == "amber"
    assert _status(4.01, expected_days=2) == "red"


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["source", "ts", "revision_date"])


def test_staleness_report_uses_revision_date_not_ts_for_ts_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    # A forward-dated forecast row: `ts` is in the future (as real forecast data
    # legitimately is), but `revision_date` (actual ingestion time) is recent.
    ts_long = pd.DataFrame(
        {
            "source": ["open_meteo_forecast"],
            "ts": [now + timedelta(days=10)],
            "revision_date": [now - timedelta(hours=1)],
        }
    )
    monkeypatch.setattr("core.freshness.read_ts_long", lambda: ts_long)
    monkeypatch.setattr("core.freshness.read_flows", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_events", lambda: _empty_df())
    monkeypatch.setattr(
        "core.freshness.read_sanctions_current",
        lambda: pd.DataFrame(columns=["last_seen"]),
    )

    report = staleness_report()

    row = report.loc[report["source"] == "open_meteo_forecast"].iloc[0]
    assert row["days_stale"] >= 0  # would be strongly negative if `ts` were used
    assert row["status"] == "green"


def test_staleness_report_excludes_sources_with_no_expected_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    ts_long = pd.DataFrame(
        {
            "source": ["newsapi"],  # deliberately manual-only, never scheduled
            "ts": [now],
            "revision_date": [now],
        }
    )
    monkeypatch.setattr("core.freshness.read_ts_long", lambda: ts_long)
    monkeypatch.setattr("core.freshness.read_flows", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_events", lambda: _empty_df())
    monkeypatch.setattr(
        "core.freshness.read_sanctions_current",
        lambda: pd.DataFrame(columns=["last_seen"]),
    )

    report = staleness_report()

    assert "newsapi" not in EXPECTED_CADENCE_DAYS
    assert report.empty


def test_staleness_report_treats_sanctions_as_one_synthetic_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    monkeypatch.setattr("core.freshness.read_ts_long", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_flows", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_events", lambda: _empty_df())
    monkeypatch.setattr(
        "core.freshness.read_sanctions_current",
        lambda: pd.DataFrame({"last_seen": [now]}),
    )

    report = staleness_report()

    assert len(report) == 1
    row = report.iloc[0]
    assert row["dataset"] == "sanctions"
    assert row["source"] == SANCTIONS_FRESHNESS_KEY
    assert row["status"] == "green"


def test_staleness_report_returns_no_rows_when_the_lake_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.freshness.read_ts_long", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_flows", lambda: _empty_df())
    monkeypatch.setattr("core.freshness.read_events", lambda: _empty_df())
    monkeypatch.setattr(
        "core.freshness.read_sanctions_current",
        lambda: pd.DataFrame(columns=["last_seen"]),
    )

    report = staleness_report()

    assert report.empty
    assert list(report.columns) == ["dataset", "source", "last_seen", "days_stale", "status"]
