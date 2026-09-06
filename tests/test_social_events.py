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


def test_a_naive_post_timestamp_passes_through_unchanged_rather_than_erroring() -> None:
    """Polymarket's startDate/createdAt and StockTwits' created_at may parse to an
    already tz-naive pd.Timestamp, unlike Reddit's tz-aware RSS timestamps.
    pd.Timestamp.tz_localize(None) on an already-naive timestamp raises
    `TypeError: Already tz-naive` -- posts_to_events must not do that
    unconditionally."""
    naive_ts = pd.Timestamp("2026-09-01T10:00:00")
    assert naive_ts.tzinfo is None

    url = "https://polymarket.com/event/some-slug"
    events = posts_to_events(
        [_post("Some market event", url, ts=naive_ts)], commodity="crude"
    )

    validate_events(events)
    assert events.iloc[0]["ts"] == naive_ts
