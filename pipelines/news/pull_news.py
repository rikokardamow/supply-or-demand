"""Session A entrypoint: loops the curated query dictionary (queries.py), pulls each via
GDELTClient, maps to events rows, merges cross-query duplicates, writes to the lake.

Per-query resilience, not just per-request retry -- matches pipelines/entsoe/
pull_actuals.py's precedent: even with GDELTClient's own generous retry/backoff, a single
query can still exhaust its retry budget given GDELT's confirmed-live flakiness. One flaky
query must never abort an otherwise-successful multi-query pull; re-running this script
picks up whatever failed last time (write_events' dedup on event_id makes this
idempotent)."""

from __future__ import annotations

import pandas as pd
import requests
from core.storage import write_events

from pipelines.news.client import GDELTClient
from pipelines.news.events import articles_to_events, merge_cross_query_duplicates
from pipelines.news.queries import QUERIES


def pull_news(client: GDELTClient) -> pd.DataFrame:
    frames = []
    for spec in QUERIES:
        label = f"{spec['commodity']}/{spec['event_type']}"
        try:
            articles = client.search(spec["query"])
        except requests.exceptions.RequestException as exc:
            print(f"{label}: FAILED ({type(exc).__name__}) — skipping", flush=True)
            continue

        print(f"{label}: {len(articles)} articles", flush=True)
        if not articles.empty:
            frames.append(articles_to_events(articles, spec["commodity"], spec["event_type"]))

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    return merge_cross_query_duplicates(combined)


def main() -> None:
    events = pull_news(GDELTClient())
    if events.empty:
        print("no event rows pulled", flush=True)
        return

    write_events(events, source="gdelt")
    print(f"wrote {len(events)} event rows", flush=True)


if __name__ == "__main__":
    main()
