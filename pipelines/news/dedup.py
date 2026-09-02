"""Fuzzy near-duplicate detection across DIFFERENT article URLs. Exact-URL dedup
(core.storage.write_events' event_id-based dedup, and events.py's own
merge_cross_query_duplicates for same-URL cross-query matches) can't catch two
different outlets' distinct URLs covering the same real-world event with a similar
headline. Per the spec: rapidfuzz title similarity >=90 within a 48h window counts as
the same event."""

from __future__ import annotations

from typing import cast

import pandas as pd
from rapidfuzz import fuzz

SIMILARITY_THRESHOLD = 90
DEDUP_WINDOW = pd.Timedelta(hours=48)


def drop_fuzzy_duplicates(events: pd.DataFrame) -> pd.DataFrame:
    """Rows are compared only against still-kept rows within a rolling 48h window (not
    globally N-by-N) -- events are processed in time order, and a later row whose
    headline fuzzy-matches (token_sort_ratio >= 90) an earlier still-kept row within
    that window is dropped, keeping the earliest report of each real-world event."""
    if events.empty:
        return events

    sorted_events = events.sort_values("ts").reset_index(drop=True)
    kept_indices: list[int] = []
    keep_mask = [True] * len(sorted_events)

    for i in range(len(sorted_events)):
        # pandas' .at[] returns an untyped scalar union (mypy strict flags every
        # downstream op on it) -- cast() narrows it to the concrete type this column
        # actually holds.
        row_ts = cast(pd.Timestamp, sorted_events.at[i, "ts"])
        row_headline = str(sorted_events.at[i, "headline"])

        is_duplicate = False
        for j in reversed(kept_indices):
            kept_ts = cast(pd.Timestamp, sorted_events.at[j, "ts"])
            if row_ts - kept_ts > DEDUP_WINDOW:
                # kept_indices is time-ordered, so nothing earlier than j can be
                # within the window either -- safe to stop scanning.
                break
            kept_headline = str(sorted_events.at[j, "headline"])
            # fuzz.token_sort_ratio is case-sensitive by default (confirmed live: two
            # otherwise-identical headlines differing only in capitalization scored
            # 68.6, not 100) -- different outlets rarely share the same capitalization
            # convention, so comparing raw headlines would systematically under-match.
            similarity = fuzz.token_sort_ratio(row_headline.lower(), kept_headline.lower())
            if similarity >= SIMILARITY_THRESHOLD:
                is_duplicate = True
                break

        if is_duplicate:
            keep_mask[i] = False
        else:
            kept_indices.append(i)

    return sorted_events[keep_mask].reset_index(drop=True)
