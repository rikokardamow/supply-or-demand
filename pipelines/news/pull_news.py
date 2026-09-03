"""Loops the curated query dictionary (queries.py) against both GDELT (always, no key)
and Guardian (only if GUARDIAN_KEY is configured -- gracefully skipped otherwise, see
CLAUDE.md), maps articles to events rows, merges cross-query duplicates, drops
cross-source fuzzy duplicates (Session B's dedup.py -- GDELT and Guardian covering the
same real-world event always have different URLs, so exact event_id dedup alone can't
catch it), then writes to the lake, one source-partition at a time.

Per-query resilience, not just per-request retry -- matches pipelines/entsoe/
pull_actuals.py's precedent: even with each client's own retry/backoff, a single query
can still exhaust its retry budget (confirmed live for GDELT). One flaky query/source
must never abort an otherwise-successful multi-query pull; re-running this script picks
up whatever failed last time (write_events' dedup on event_id makes this idempotent for
exact repeats; fuzzy dedup only ever removes rows within one run's own combined batch,
so it doesn't affect idempotency across separate runs).

`manual_newsapi_search` (bottom of this file) is deliberately NEVER called from
`main()` -- see specs/16_newsapi-supplement.md and pipelines/news/CLAUDE.md for why
NewsAPI stays manual/on-demand only (its free tier's own ToS bans production/
scheduled use). It exists purely for page 09's manual-search control to import."""

from __future__ import annotations

import pandas as pd
import requests
from core.settings import settings
from core.storage import write_events

from pipelines.news.client import GDELTClient
from pipelines.news.dedup import drop_fuzzy_duplicates
from pipelines.news.events import articles_to_events, merge_cross_query_duplicates
from pipelines.news.guardian_client import GuardianClient
from pipelines.news.newsapi_client import NewsAPIClient
from pipelines.news.queries import QUERIES


def pull_news(
    gdelt_client: GDELTClient, guardian_client: GuardianClient | None = None
) -> pd.DataFrame:
    frames = []
    for spec in QUERIES:
        label = f"{spec['commodity']}/{spec['event_type']}"

        try:
            articles = gdelt_client.search(spec["query"])
        except requests.exceptions.RequestException as exc:
            print(f"gdelt {label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
        else:
            print(f"gdelt {label}: {len(articles)} articles", flush=True)
            if not articles.empty:
                frames.append(
                    articles_to_events(
                        articles, spec["commodity"], spec["event_type"], source="gdelt"
                    )
                )

        if guardian_client is not None:
            try:
                g_articles = guardian_client.search(spec["query"])
            except requests.exceptions.RequestException as exc:
                print(f"guardian {label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
            else:
                print(f"guardian {label}: {len(g_articles)} articles", flush=True)
                if not g_articles.empty:
                    frames.append(
                        articles_to_events(
                            g_articles, spec["commodity"], spec["event_type"], source="guardian"
                        )
                    )

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    merged = merge_cross_query_duplicates(combined)
    return drop_fuzzy_duplicates(merged)


def main() -> None:
    guardian_client = GuardianClient() if settings.guardian_key else None
    if guardian_client is None:
        print("guardian: no GUARDIAN_KEY configured — skipping", flush=True)

    events = pull_news(GDELTClient(), guardian_client)
    if events.empty:
        print("no event rows pulled", flush=True)
        return

    for source, group in events.groupby("source"):
        write_events(group, source=str(source))
        print(f"wrote {len(group)} {source} event rows", flush=True)


def manual_newsapi_search(
    client: NewsAPIClient, query: str, commodity: str
) -> pd.DataFrame:
    """One-off, page-triggered NewsAPI search -- NOT part of `main()` and never
    called from it (see this module's own docstring). The caller (page
    09_events.py's manual-search control) is responsible for writing the result via
    `core.storage.write_events`."""
    articles = client.search(query)
    if articles.empty:
        return articles
    return articles_to_events(articles, commodity, event_type="manual_search", source="newsapi")


if __name__ == "__main__":
    main()
