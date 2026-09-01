from __future__ import annotations

import pandas as pd
from core.schemas import validate_events
from pipelines.news.events import (
    _event_id,
    articles_to_events,
    merge_cross_query_duplicates,
)


def _articles_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "url": ["https://example.com/a", "https://example.com/b"],
            "title": ["Refinery fire in Rotterdam", "OPEC weighs quota cut"],
            "seendate": pd.to_datetime(["2026-09-01T12:00:00", "2026-09-01T13:00:00"]),
            "domain": ["example.com", "example.com"],
            "language": ["English", "English"],
            "sourcecountry": ["Netherlands", "Saudi Arabia"],
        }
    )


def test_articles_to_events_is_schema_conformant_and_tags_from_event_type() -> None:
    df = articles_to_events(_articles_df(), commodity="crude", event_type="outage")

    validate_events(df)
    assert (df["commodity"] == "crude").all()
    assert (df["severity"] == 1).all()
    assert all(tags == ["outage"] for tags in df["tags"])
    assert df["event_id"].iloc[0] == _event_id("https://example.com/a")
    assert df["geo"].iloc[0] == "Netherlands"


def test_articles_to_events_empty_input_returns_empty_conformant_frame() -> None:
    empty = pd.DataFrame(
        columns=["url", "title", "seendate", "domain", "language", "sourcecountry"]
    )

    df = articles_to_events(empty, commodity="crude", event_type="outage")

    assert df.empty
    validate_events(df)


def test_event_id_is_stable_sha256_of_url() -> None:
    assert _event_id("https://example.com/a") == _event_id("https://example.com/a")
    assert _event_id("https://example.com/a") != _event_id("https://example.com/b")


def test_merge_cross_query_duplicates_unions_tags_for_same_event_id() -> None:
    same_url_two_matches = pd.concat(
        [
            articles_to_events(_articles_df().iloc[[1]], commodity="crude", event_type="opec"),
            articles_to_events(
                _articles_df().iloc[[1]], commodity="crude", event_type="sanctions"
            ),
        ],
        ignore_index=True,
    )

    merged = merge_cross_query_duplicates(same_url_two_matches)

    assert len(merged) == 1
    assert set(merged.iloc[0]["tags"]) == {"opec", "sanctions"}


def test_merge_cross_query_duplicates_leaves_distinct_events_untouched() -> None:
    events = articles_to_events(_articles_df(), commodity="crude", event_type="outage")

    merged = merge_cross_query_duplicates(events)

    assert len(merged) == 2
