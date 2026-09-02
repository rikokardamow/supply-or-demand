"""Maps raw articles (GDELT or Guardian -- both share the same column shape, see
client.py/guardian_client.py) into events-schema rows. Session B's tagging engine
(pipelines/news/tagging.py) derives real tags/geo/severity from each article's own
headline text -- replacing Session A's placeholder (`tags=[event_type]`,
`severity=1` fixed)."""

from __future__ import annotations

import hashlib

import pandas as pd
from core.schemas import EVENTS_SCHEMA

from pipelines.news.tagging import extract_geo, extract_severity, extract_tags


def _event_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _merge_tags(event_type: str, headline_tags: list[str]) -> list[str]:
    """`event_type` (the query dictionary's own commodity x event_type match -- real
    evidence this article is relevant, even if the tagging engine's own keyword scan
    finds nothing in the headline itself) is always included, unioned with whatever
    `tagging.py::extract_tags` finds -- richer than either alone, and guarantees every
    row gets at least one tag even for an oblique headline."""
    merged = [event_type]
    for tag in headline_tags:
        if tag not in merged:
            merged.append(tag)
    return merged


def articles_to_events(
    articles: pd.DataFrame, commodity: str, event_type: str, source: str = "gdelt"
) -> pd.DataFrame:
    """`articles` is GDELTClient.search's/GuardianClient.search's own shared output
    shape (url, title, seendate, domain, language, sourcecountry). `event_id` is a
    stable sha256 of the URL, so re-pulling the same article on a later run maps to
    the same event_id -- write_events' dedup relies on this.

    `geo` prefers a place-name keyword found in the headline itself over GDELT's own
    `sourcecountry` -- `sourcecountry` is the *publisher's* country, not necessarily the
    event's location (see pipelines/news/tagging.py's own docstring)."""
    if articles.empty:
        # A bare pd.DataFrame(columns=[...]) would leave every column dtype "object"
        # (confirmed live: fails validate_events' own dtype check on "ts") -- building
        # from the real pyarrow schema's own empty table gives correct dtypes for free,
        # same trick core/storage.py's _read uses when a dataset has no files yet.
        empty: pd.DataFrame = EVENTS_SCHEMA.empty_table().to_pandas()
        return empty

    tags = [
        _merge_tags(event_type, extract_tags(title)) for title in articles["title"]
    ]
    geo = [
        extract_geo(title, fallback=fallback)
        for title, fallback in zip(articles["title"], articles["sourcecountry"], strict=True)
    ]
    severity = [extract_severity(title) for title in articles["title"]]

    return pd.DataFrame(
        {
            "event_id": articles["url"].map(_event_id),
            "ts": articles["seendate"],
            "headline": articles["title"],
            "source": source,
            "url": articles["url"],
            "tags": tags,
            "geo": geo,
            "commodity": commodity,
            "severity": severity,
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
