from __future__ import annotations

import hashlib

import pandas as pd
from core.schemas import validate_events
from pipelines.social.client import Post
from pipelines.social.events import posts_to_events


def _post(title: str, url: str, ts: pd.Timestamp | None = None) -> Post:
    return Post(
        post_id=url,
        url=url,
        title=title,
        ts=ts if ts is not None else pd.Timestamp("2026-09-01T10:00Z"),
        platform="reddit",
        query="Henry Hub",
        score=None,
        num_comments=None,
    )


def test_posts_to_events_uses_the_same_event_id_hash_as_the_news_pipeline() -> None:
    url = "https://reddit.com/r/energy/comments/abc"
    events = posts_to_events([_post("Henry Hub spikes", url)], commodity="gas")

    validate_events(events)
    assert events.iloc[0]["event_id"] == hashlib.sha256(url.encode("utf-8")).hexdigest()
    assert events.iloc[0]["source"] == "reddit"
    assert events.iloc[0]["commodity"] == "gas"
    assert "Henry Hub" in events.iloc[0]["tags"]


def test_empty_posts_return_a_correctly_typed_empty_frame() -> None:
    events = posts_to_events([], commodity="gas")
    assert events.empty
    validate_events(events)


def test_severity_is_always_fixed_at_1_never_derived_from_text() -> None:
    """Spec 29: `severity=1` fixed, deliberately, because these are posts, not events
    with intensity. A title like this one would score severity 3 (tag "outage") if
    posts_to_events ever went back to reusing pipelines/news/tagging.py's
    extract_severity -- and since Set B posts share the `events` table and carry a
    real `commodity`, that severity would render as a marker visually identical to a
    confirmed refinery explosion on apps/dashboard/components/event_overlay.py's
    severity>=2 filter, and would show up unfiltered on
    apps/dashboard/pages/09_events.py too. This test exists to fail loudly the moment
    that regression is reintroduced."""
    events = posts_to_events(
        [_post("XOM is on fire today", "https://reddit.com/r/energy/comments/fire")],
        commodity="crude",
    )
    assert events.iloc[0]["severity"] == 1


def test_mixed_aware_and_naive_post_timestamps_both_normalise_to_tz_naive() -> None:
    """Reddit's RSS timestamps are tz-aware; Polymarket's startDate/createdAt and
    StockTwits' created_at may parse tz-naive. A frame built from a mix of sources
    must come out with a single, consistently tz-naive ts column, or the Parquet
    write downstream would see mixed dtypes across rows."""
    aware_ts = pd.Timestamp("2026-09-01T10:00:00Z")
    naive_ts = pd.Timestamp("2026-09-01T11:00:00")
    assert aware_ts.tzinfo is not None
    assert naive_ts.tzinfo is None

    events = posts_to_events(
        [
            _post("Reddit post", "https://reddit.com/r/energy/comments/aware", ts=aware_ts),
            _post("Polymarket event", "https://polymarket.com/event/naive", ts=naive_ts),
        ],
        commodity="crude",
    )

    validate_events(events)
    assert events["ts"].dt.tz is None
    assert list(events["ts"]) == [
        pd.Timestamp("2026-09-01T10:00:00"),
        pd.Timestamp("2026-09-01T11:00:00"),
    ]
