from __future__ import annotations

import pandas as pd
from pipelines.news.dedup import drop_fuzzy_duplicates


def _event(event_id: str, ts: str, headline: str) -> dict:
    return {
        "event_id": event_id,
        "ts": pd.Timestamp(ts),
        "headline": headline,
        "source": "gdelt",
        "url": f"https://example.com/{event_id}",
        "tags": ["outage"],
        "geo": "NL",
        "commodity": "crude",
        "severity": 2,
    }


def test_drop_fuzzy_duplicates_removes_similar_headline_within_window() -> None:
    events = pd.DataFrame(
        [
            _event("e1", "2026-09-01T08:00:00", "Refinery fire halts Rotterdam plant"),
            _event("e2", "2026-09-01T10:00:00", "Fire halts Rotterdam refinery plant"),
        ]
    )

    result = drop_fuzzy_duplicates(events)

    assert len(result) == 1
    assert result.iloc[0]["event_id"] == "e1"  # earliest report is kept


def test_drop_fuzzy_duplicates_keeps_dissimilar_headlines() -> None:
    events = pd.DataFrame(
        [
            _event("e1", "2026-09-01T08:00:00", "Refinery fire halts Rotterdam plant"),
            _event("e2", "2026-09-01T10:00:00", "OPEC weighs quota cut next month"),
        ]
    )

    result = drop_fuzzy_duplicates(events)

    assert len(result) == 2


def test_drop_fuzzy_duplicates_keeps_similar_headlines_outside_the_window() -> None:
    events = pd.DataFrame(
        [
            _event("e1", "2026-09-01T08:00:00", "Refinery fire halts Rotterdam plant"),
            _event("e2", "2026-09-04T08:00:01", "Fire halts Rotterdam refinery plant"),
        ]
    )

    result = drop_fuzzy_duplicates(events)

    assert len(result) == 2


def test_drop_fuzzy_duplicates_empty_input() -> None:
    empty = pd.DataFrame(columns=["event_id", "ts", "headline"])

    result = drop_fuzzy_duplicates(empty)

    assert result.empty
