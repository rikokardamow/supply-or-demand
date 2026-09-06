"""Social posts -> the existing `events` schema (Spec 29 adds no new schema).

event_id is the same sha256-of-URL used by pipelines/news/events.py, so
write_events' dedup works unchanged and re-pulling the same post on a later run
maps to the same row. Tagging reuses pipelines/news/tagging.py rather than
introducing a second tagger with its own drift."""

from __future__ import annotations

import hashlib

import pandas as pd
from core.schemas import EVENTS_SCHEMA

from pipelines.news.tagging import extract_geo, extract_severity, extract_tags
from pipelines.social.client import Post

# Posts are chatter, not events with intensity. Severity is derived from the text
# where the news tagger recognises something, and floors at 1 otherwise.
_MIN_SEVERITY = 1


def _event_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _naive_ts(ts: pd.Timestamp) -> pd.Timestamp:
    """Strips tzinfo when present, leaves an already-naive timestamp unchanged.
    Reddit's RSS timestamps are tz-aware, but Polymarket's startDate/createdAt and
    StockTwits' created_at may parse naive -- pd.Timestamp.tz_localize(None) raises
    `TypeError: Already tz-naive` on those, so the two cases must be handled
    separately rather than calling tz_localize(None) unconditionally."""
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        return ts
    return ts.tz_localize(None)


def posts_to_events(posts: list[Post], commodity: str) -> pd.DataFrame:
    """`commodity` comes from the TopicQuery that produced these posts (Set B) or
    is "equity" for ticker queries (Set A)."""
    if not posts:
        # Building from the real pyarrow schema's own empty table gives correct
        # dtypes for free -- a bare DataFrame(columns=[...]) leaves every dtype
        # "object" and fails validate_events. Same trick pipelines/news/events.py
        # and core/storage.py's _read both use.
        empty: pd.DataFrame = EVENTS_SCHEMA.empty_table().to_pandas()
        return empty

    titles = [p["title"] for p in posts]
    return pd.DataFrame(
        {
            "event_id": [_event_id(p["url"]) for p in posts],
            "ts": [_naive_ts(p["ts"]) for p in posts],
            "headline": titles,
            "source": [p["platform"] for p in posts],
            "url": [p["url"] for p in posts],
            # The matching query travels with the row so a post's provenance is
            # readable straight from the lake.
            "tags": [sorted({p["query"], *extract_tags(p["title"])}) for p in posts],
            "geo": [extract_geo(title) for title in titles],
            "commodity": commodity,
            "severity": [max(extract_severity(title), _MIN_SEVERITY) for title in titles],
            "language": "en",
        }
    )
