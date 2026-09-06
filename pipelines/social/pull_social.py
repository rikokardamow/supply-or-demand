"""Weekly entrypoint for Spec 29. Fetches Set A (ticker queries, for the Adanos
overlap), Set B (commodity/geopolitical topics, which Adanos cannot express) and
Polymarket's tag-level attention, scores all of it deterministically, and writes
ts_long aggregates plus the raw posts as events.

Task 6 brief correction (decision 1): the brief called `fetch_polymarket(query)`
per topic. Polymarket has no keyword search -- Task 0 proved `?q=`/`?search=` are
silently ignored and return the same default list for any input (see this
package's CLAUDE.md). `fetch_polymarket` therefore takes a tag slug, not a
per-topic query, so there are three pull functions here, not two: `pull_topic`
is Reddit-only (Set B -- the only platform here that genuinely filters by
keyword), `pull_ticker` is Reddit + StockTwits (Set A), and `pull_polymarket_tag`
pulls one Polymarket tag's attention as its own subject.

Per-platform resilience, not just per-request retry -- matches
pipelines/macro/pull_macro.py's established pattern and pipelines/adanos/
pull_adanos.py's reuse of it: one flaky platform must never abort the rest.

Registered in the weekly_fri group beside adanos deliberately, so the overlap
join in core/sentiment.py has matching dates rather than a systematic one-day
offset that would masquerade as deviation.

Decision 2 (fail loudly): `main` tracks fetch attempts/failures itself and
raises when every fetch failed, or when some failed and nothing at all got
written -- a silent `return` here would tell infra/run_scheduled.py the run
succeeded, so it would print OK and Windows Task Scheduler's "Last Run Result"
would show green for a run that ingested nothing. This is deliberately a small,
local `_RunStats`, NOT a use of `core/failures.py`: that module is being added
by a concurrent session on this branch and is currently untracked, so depending
on it risks building on work that may be reverted. Migrate `main` to
`core.failures` once that module lands -- until then this is the whole of the
fail-loudly story for pipelines/social."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from core.storage import write_events, write_ts_long

from pipelines.social.client import Post, fetch_polymarket, fetch_reddit, fetch_stocktwits
from pipelines.social.events import posts_to_events
from pipelines.social.queries import TICKER_QUERIES, TOPIC_QUERIES, TopicQuery
from pipelines.social.score import aggregate_to_ts_long

TICKER_COMMODITY = "equity"
# Polymarket has no keyword search (see this package's CLAUDE.md), so it
# contributes tag-level attention rather than a per-topic series. Only the one
# tag Task 3 actually probed and confirmed live is pulled -- widening this list
# is a separate decision, not a side effect of this pull.
POLYMARKET_TAGS: list[str] = ["energy"]
POLYMARKET_COMMODITY = "energy"


class _RunStats:
    """Local, file-scoped failure tracking -- see this module's docstring on
    why this is not `core/failures.py`."""

    def __init__(self) -> None:
        self.attempted = 0
        self.failed = 0

    def reset(self) -> None:
        self.attempted = 0
        self.failed = 0


_stats = _RunStats()


def _safe_fetch(label: str, fetch: object, *args: object) -> list[Post]:
    """Any one platform's failure is logged and skipped, never raised -- matches
    pipelines/macro/pull_macro.py's established per-platform resilience. Every
    call counts towards `_stats`, whether reached through pull_topic/pull_ticker/
    pull_polymarket_tag or directly, so `main` can tell a total failure apart
    from a genuinely quiet run at the end.

    Catches OSError, not `requests.exceptions.RequestException`: client.py is
    built on urllib, whose URLError/HTTPError are OSError subclasses, and
    requests' own RequestException also subclasses OSError -- one catch covers
    both without this module needing to import requests at all."""
    _stats.attempted += 1
    try:
        return list(fetch(*args))  # type: ignore[operator]
    except OSError as exc:
        _stats.failed += 1
        print(f"social {label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
        return []


def pull_topic(
    topic: TopicQuery, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Set B, Reddit only (decision 1 above) -- Polymarket cannot filter by
    keyword at all, so it is pulled separately, by tag, in
    `pull_polymarket_tag`. Returns (ts_long rows, events rows), both possibly
    empty -- an empty result for a topic is a real finding (recorded in this
    package's CLAUDE.md), not a bug to paper over with zeros."""
    query = topic["query"]
    posts = _safe_fetch(f"reddit {query}", fetch_reddit, query)
    print(f"social topic {topic['slug']}: {len(posts)} posts", flush=True)

    rows = aggregate_to_ts_long(posts, subject=topic["slug"], ingested_at=ingested_at)
    events = posts_to_events(posts, commodity=topic["commodity"])
    return rows, events


def pull_ticker(
    ticker: str, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Set A -- Reddit + StockTwits, exists solely to give core/sentiment.py an
    apples-to-apples series against Adanos for the same ticker, platform and
    day."""
    posts = [
        *_safe_fetch(f"reddit {ticker}", fetch_reddit, ticker),
        *_safe_fetch(f"stocktwits {ticker}", fetch_stocktwits, ticker),
    ]
    print(f"social ticker {ticker}: {len(posts)} posts", flush=True)

    rows = aggregate_to_ts_long(posts, subject=ticker.lower(), ingested_at=ingested_at)
    events = posts_to_events(posts, commodity=TICKER_COMMODITY)
    return rows, events


def pull_polymarket_tag(
    tag_slug: str, ingested_at: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Polymarket tag-level attention (decision 1 above) -- the subject is the
    tag slug itself (`social.polymarket.<tag_slug>.*`), not any single topic or
    ticker, because Polymarket cannot be filtered any more finely than that."""
    posts = _safe_fetch(f"polymarket {tag_slug}", fetch_polymarket, tag_slug)
    print(f"social polymarket tag {tag_slug}: {len(posts)} posts", flush=True)

    rows = aggregate_to_ts_long(posts, subject=tag_slug, ingested_at=ingested_at)
    events = posts_to_events(posts, commodity=POLYMARKET_COMMODITY)
    return rows, events


def main() -> None:
    """Decision 2: this must not swallow a total failure and exit 0. Reddit's
    confirmed ~1-request/60s unauthenticated pace (see this package's
    CLAUDE.md) makes a run that legitimately fetches zero posts across every
    subject a real, not theoretical, possibility, so a total failure and a
    genuinely quiet run must be told apart, not conflated: only the former (or
    a partial failure that still leaves nothing written) raises."""
    _stats.reset()
    ingested_at = pd.Timestamp(datetime.now(UTC))

    row_frames: list[pd.DataFrame] = []
    event_frames: list[pd.DataFrame] = []
    for topic in TOPIC_QUERIES:
        rows, events = pull_topic(topic, ingested_at)
        row_frames.append(rows)
        event_frames.append(events)
    for ticker in TICKER_QUERIES:
        rows, events = pull_ticker(ticker, ingested_at)
        row_frames.append(rows)
        event_frames.append(events)
    for tag_slug in POLYMARKET_TAGS:
        rows, events = pull_polymarket_tag(tag_slug, ingested_at)
        row_frames.append(rows)
        event_frames.append(events)

    rows_all = [f for f in row_frames if not f.empty]
    combined = pd.concat(rows_all, ignore_index=True) if rows_all else pd.DataFrame()
    if not combined.empty:
        for source, group in combined.groupby("source"):
            write_ts_long(group.reset_index(drop=True), source=str(source))
        print(f"wrote {len(combined)} social rows", flush=True)

    events_all = [f for f in event_frames if not f.empty]
    combined_events = pd.concat(events_all, ignore_index=True) if events_all else pd.DataFrame()
    if not combined_events.empty:
        # Drop within-run duplicates first: the same post can match several
        # queries and subreddits, and shares an event_id by construction.
        combined_events = combined_events.drop_duplicates(subset="event_id", keep="first")
        for source, group in combined_events.groupby("source"):
            write_events(group.reset_index(drop=True), source=str(source))
        print(f"wrote {len(combined_events)} social events", flush=True)

    wrote_nothing = combined.empty and combined_events.empty
    if _stats.attempted == 0:
        # TOPIC_QUERIES/TICKER_QUERIES/POLYMARKET_TAGS are all non-empty in
        # normal operation, but if every one were emptied there is nothing to
        # judge either way.
        return
    if _stats.failed == _stats.attempted:
        raise RuntimeError(
            f"social pull: all {_stats.attempted} fetches failed -- see logs above. "
            "TODO: migrate to core.failures once that module lands."
        )
    if wrote_nothing and _stats.failed > 0:
        raise RuntimeError(
            f"social pull: {_stats.failed}/{_stats.attempted} fetches failed and "
            "nothing was written -- see logs above. TODO: migrate to "
            "core.failures once that module lands."
        )
    if wrote_nothing:
        # Genuinely quiet: every fetch succeeded but found nothing. This must
        # never look identical to "wrote N social rows" above, without raising
        # for an outcome that was not a failure.
        print(
            f"social pull: 0 rows and 0 events across {_stats.attempted} fetches, "
            "0 failures -- genuinely nothing found this run",
            flush=True,
        )


if __name__ == "__main__":
    main()
