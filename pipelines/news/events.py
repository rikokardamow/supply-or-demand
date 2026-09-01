"""Maps raw GDELT articles into events-schema rows. Session A's own tagging is
deliberately basic -- tags = [event_type] straight from the query dictionary
(pipelines/news/queries.py) that matched -- the fuller regex/severity/geo-dictionary
engine is Session B's job per the spec's own session split. severity defaults to 1
(lowest tier) as a Session A placeholder, refined 1-3 by that later engine."""

from __future__ import annotations

import hashlib

import pandas as pd
from core.schemas import EVENTS_SCHEMA

SESSION_A_SEVERITY_DEFAULT = 1


def _event_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def articles_to_events(
    articles: pd.DataFrame, commodity: str, event_type: str
) -> pd.DataFrame:
    """`articles` is GDELTClient.search's own output shape (url, title, seendate,
    domain, language, sourcecountry). `event_id` is a stable sha256 of the URL, so
    re-pulling the same article on a later run maps to the same event_id -- write_events'
    dedup relies on this."""
    if articles.empty:
        # A bare pd.DataFrame(columns=[...]) would leave every column dtype "object"
        # (confirmed live: fails validate_events' own dtype check on "ts") -- building
        # from the real pyarrow schema's own empty table gives correct dtypes for free,
        # same trick core/storage.py's _read uses when a dataset has no files yet.
        empty: pd.DataFrame = EVENTS_SCHEMA.empty_table().to_pandas()
        return empty

    return pd.DataFrame(
        {
            "event_id": articles["url"].map(_event_id),
            "ts": articles["seendate"],
            "headline": articles["title"],
            "source": "gdelt",
            "url": articles["url"],
            "tags": [[event_type]] * len(articles),
            "geo": articles["sourcecountry"],
            "commodity": commodity,
            "severity": SESSION_A_SEVERITY_DEFAULT,
        }
    )


def merge_cross_query_duplicates(events: pd.DataFrame) -> pd.DataFrame:
    """A single article can independently match more than one curated query in the same
    run (a real, expected case -- e.g. a headline mentioning both "OPEC" and
    "sanctions") -- each match produces its own single-tag row for the same event_id.
    write_events' own dedup keeps only the *last* full row per event_id, which would
    silently drop every match but one. This unions `tags` into a single row per
    event_id *before* write_events ever runs, keeping the first match's other fields
    (commodity/geo/etc. are otherwise identical across matches for the same URL)."""
    if events.empty:
        return events

    merged_rows = []
    for _event_id_value, group in events.groupby("event_id"):
        row = group.iloc[0].to_dict()
        merged_tags: list[str] = []
        for tags in group["tags"]:
            for tag in tags:
                if tag not in merged_tags:
                    merged_tags.append(tag)
        row["tags"] = merged_tags
        merged_rows.append(row)

    return pd.DataFrame(merged_rows, columns=events.columns)
