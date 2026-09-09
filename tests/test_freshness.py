from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from core.freshness import (
    EXPECTED_CADENCE_DAYS,
    SANCTIONS_FRESHNESS_KEY,
    _status,
    mass_data_loss_detected,
    missing_sources,
    staleness_report,
)


def test_status_boundaries() -> None:
    assert _status(2.0, expected_days=2) == "green"
    assert _status(2.01, expected_days=2) == "amber"
    assert _status(4.0, expected_days=2) == "amber"
    assert _status(4.01, expected_days=2) == "red"


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["source", "last_seen"])


def _patch_lake(
    monkeypatch: pytest.MonkeyPatch,
    per_dataset: dict[str, pd.DataFrame] | None = None,
    sanctions: pd.DataFrame | None = None,
) -> list[tuple[str, str]]:
    """Stub the lake at core.storage.last_ts_by_source's seam and record the
    (dataset, ts_col) pairs staleness_report actually asks for. Returns that call log."""
    calls: list[tuple[str, str]] = []
    frames = per_dataset or {}

    def _fake(dataset: str, ts_col: str) -> pd.DataFrame:
        calls.append((dataset, ts_col))
        return frames.get(dataset, _empty_df())

    monkeypatch.setattr("core.freshness.last_ts_by_source", _fake)
    monkeypatch.setattr(
        "core.freshness.read_sanctions_current",
        lambda: sanctions if sanctions is not None else pd.DataFrame(columns=["last_seen"]),
    )
    return calls


def test_staleness_report_asks_for_revision_date_not_ts_on_ts_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ts_long carries forward-dated forecast rows (a 16-day weather forecast's `ts` is
    # legitimately in the future), so its freshness must come from `revision_date` --
    # the real ingestion time. flows/events have no revision_date column at all.
    calls = _patch_lake(monkeypatch)

    staleness_report()

    assert calls == [("ts_long", "revision_date"), ("flows", "ts"), ("events", "ts")]


def test_staleness_report_scores_a_recently_ingested_source_green(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _patch_lake(
        monkeypatch,
        {
            "ts_long": pd.DataFrame(
                {
                    "source": ["open_meteo_forecast"],
                    "last_seen": [now - timedelta(hours=1)],
                }
            )
        },
    )

    report = staleness_report()

    row = report.loc[report["source"] == "open_meteo_forecast"].iloc[0]
    assert row["days_stale"] >= 0
    assert row["status"] == "green"


def test_staleness_report_excludes_sources_with_no_expected_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _patch_lake(
        monkeypatch,
        {
            # deliberately manual-only, never scheduled
            "ts_long": pd.DataFrame({"source": ["newsapi"], "last_seen": [now]})
        },
    )

    report = staleness_report()

    assert "newsapi" not in EXPECTED_CADENCE_DAYS
    assert report.empty


def test_staleness_report_treats_sanctions_as_one_synthetic_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    _patch_lake(monkeypatch, sanctions=pd.DataFrame({"last_seen": [now]}))

    report = staleness_report()

    assert len(report) == 1
    row = report.iloc[0]
    assert row["dataset"] == "sanctions"
    assert row["source"] == SANCTIONS_FRESHNESS_KEY
    assert row["status"] == "green"


def test_staleness_report_returns_no_rows_when_the_lake_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_lake(monkeypatch)

    report = staleness_report()

    assert report.empty
    assert list(report.columns) == ["dataset", "source", "last_seen", "days_stale", "status"]


def test_missing_sources_is_empty_when_every_expected_source_has_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    non_sanctions = list(set(EXPECTED_CADENCE_DAYS) - {SANCTIONS_FRESHNESS_KEY})
    ts_long = pd.DataFrame({"source": non_sanctions, "last_seen": [now] * len(non_sanctions)})
    _patch_lake(monkeypatch, {"ts_long": ts_long}, sanctions=pd.DataFrame({"last_seen": [now]}))

    assert missing_sources() == set()


def test_missing_sources_flags_a_source_with_zero_rows_anywhere_in_the_lake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A source absent from every dataset's last_ts_by_source result never appears in
    # staleness_report() at all -- indistinguishable from "never configured" unless
    # something explicitly diffs against the full expected roster.
    now = datetime.now(UTC).replace(tzinfo=None)
    _patch_lake(monkeypatch, {"ts_long": pd.DataFrame({"source": ["eia"], "last_seen": [now]})})

    missing = missing_sources()

    assert "gie" in missing
    assert "eia" not in missing


def test_mass_data_loss_detected_true_when_most_expected_sources_vanish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The real, confirmed-live signature of the 2026-09-08 data/lake wipe: every
    # source disappearing at once, not one pipeline going stale on its own schedule.
    now = datetime.now(UTC).replace(tzinfo=None)
    _patch_lake(monkeypatch, {"ts_long": pd.DataFrame({"source": ["eia"], "last_seen": [now]})})

    assert mass_data_loss_detected() is True


def test_mass_data_loss_detected_false_for_one_missing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A single missing source is normal -- a pipeline never yet run, or one genuinely
    # broken pipeline -- and must not trip the same alarm as a whole-lake wipe.
    now = datetime.now(UTC).replace(tzinfo=None)
    present = set(EXPECTED_CADENCE_DAYS) - {"gie", SANCTIONS_FRESHNESS_KEY}
    _patch_lake(
        monkeypatch,
        {"ts_long": pd.DataFrame({"source": list(present), "last_seen": [now] * len(present)})},
        sanctions=pd.DataFrame({"last_seen": [now]}),
    )

    assert mass_data_loss_detected() is False
