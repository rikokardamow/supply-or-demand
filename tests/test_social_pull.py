from __future__ import annotations

import pandas as pd
import pytest
import requests
from core.failures import PartialFailureError
from pipelines.social import pull_social
from pipelines.social.client import Post


def _post(title: str, url: str, platform: str, query: str) -> Post:
    return Post(
        post_id=url,
        url=url,
        title=title,
        ts=pd.Timestamp("2026-09-01T10:00Z"),
        platform=platform,
        query=query,
        score=None,
        num_comments=None,
    )


def test_pull_ticker_one_platform_failing_never_aborts_the_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pattern pipelines/macro/pull_macro.py established and Spec 17 reused:
    # per-platform resilience, not just per-request retry. pull_ticker is the
    # only pull_* here that touches two platforms (Reddit + StockTwits) --
    # decision 1 makes pull_topic Reddit-only.
    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("stocktwits down")

    monkeypatch.setattr(
        pull_social,
        "fetch_reddit",
        lambda query, **kw: [_post("great news", "https://x.test/1", "reddit", query)],
    )
    monkeypatch.setattr(pull_social, "fetch_stocktwits", boom)

    rows, events = pull_social.pull_ticker("XOM", pd.Timestamp("2026-09-01T18:00Z"))

    assert not rows.empty, "reddit's rows must survive stocktwits failing"
    assert set(rows["source"]) == {"reddit"}
    assert len(events) == 1


def test_pull_topic_with_no_posts_writes_nothing_rather_than_zeros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pull_social, "fetch_reddit", lambda query, **kw: [])

    topic = {"slug": "pdvsa", "query": "PDVSA", "commodity": "crude", "theme": "opec_producers"}
    rows, events = pull_social.pull_topic(topic, pd.Timestamp("2026-09-01T18:00Z"))

    assert rows.empty
    assert events.empty


def test_pull_topic_survives_reddit_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Decision 1: pull_topic is Reddit-only, so Reddit failing is the ONLY
    # platform failure it can see. If the try/except here were removed, this
    # would raise instead of returning empty frames.
    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("reddit down")

    monkeypatch.setattr(pull_social, "fetch_reddit", boom)

    topic = {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"}
    rows, events = pull_social.pull_topic(topic, pd.Timestamp("2026-09-01T18:00Z"))

    assert rows.empty
    assert events.empty


def test_pull_polymarket_tag_uses_the_tag_slug_as_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pull_social,
        "fetch_polymarket",
        lambda tag_slug, **kw: [
            _post("Will there be a grid emergency?", "https://pm.test/1", "polymarket", tag_slug)
        ],
    )

    rows, events = pull_social.pull_polymarket_tag("energy", pd.Timestamp("2026-09-01T18:00Z"))

    assert not rows.empty
    assert set(rows["series_id"]) == {
        "social.polymarket.energy.post_count",
        "social.polymarket.energy.sentiment_score",
        "social.polymarket.energy.snapshot_post_count",
        "social.polymarket.energy.snapshot_sentiment_score",
    }
    assert len(events) == 1


def test_pull_polymarket_tag_survives_polymarket_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("polymarket down")

    monkeypatch.setattr(pull_social, "fetch_polymarket", boom)

    rows, events = pull_social.pull_polymarket_tag("energy", pd.Timestamp("2026-09-01T18:00Z"))

    assert rows.empty
    assert events.empty


def test_main_raises_when_every_fetch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # The fail-loudly test. Without the raise this proves, a totally-broken
    # run (every platform down) would print failures and return normally --
    # infra/run_scheduled.py would then print "social: OK" and Windows Task
    # Scheduler would show green for a run that ingested nothing. Now backed by
    # core.failures: every _safe_fetch failure is record_failure'd, and main's
    # failure_scope raises PartialFailureError once at the end if any were.
    monkeypatch.setattr(
        pull_social,
        "TOPIC_QUERIES",
        [
            {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
        ],
    )
    monkeypatch.setattr(pull_social, "TICKER_QUERIES", ["XOM"])
    monkeypatch.setattr(pull_social, "POLYMARKET_TAGS", ["energy"])

    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("everything down")

    monkeypatch.setattr(pull_social, "fetch_reddit", boom)
    monkeypatch.setattr(pull_social, "fetch_stocktwits", boom)
    monkeypatch.setattr(pull_social, "fetch_polymarket", boom)

    with pytest.raises(PartialFailureError, match=r"social\.pull_social.*item\(s\) failed"):
        pull_social.main()


def test_main_raises_on_any_failure_even_if_other_data_was_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # core.failures' established semantics (see pipelines/adanos/pull_adanos.py,
    # the closest sibling): ANY recorded failure fails the whole run, even one
    # where other, unrelated fetches succeeded and real data got written. This
    # is stricter than "raise only if nothing was written" -- and deliberately
    # so, matching every other adopted pipeline.
    monkeypatch.setattr(
        pull_social,
        "TOPIC_QUERIES",
        [
            {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
        ],
    )
    monkeypatch.setattr(pull_social, "TICKER_QUERIES", ["XOM"])
    monkeypatch.setattr(pull_social, "POLYMARKET_TAGS", [])

    def fake_reddit(query: str, **kw: object) -> list[Post]:
        if query == "Henry Hub":
            return [_post("Henry Hub spikes", "https://x.test/hh", "reddit", query)]
        return []  # XOM's reddit leg finds nothing, but does not fail

    monkeypatch.setattr(pull_social, "fetch_reddit", fake_reddit)

    def boom(*args: object, **kwargs: object) -> list[Post]:
        raise requests.exceptions.ConnectionError("stocktwits down")

    monkeypatch.setattr(pull_social, "fetch_stocktwits", boom)

    written_ts_long = []
    monkeypatch.setattr(
        pull_social,
        "write_ts_long",
        lambda df, source: written_ts_long.append((source, df)),
    )
    monkeypatch.setattr(pull_social, "write_events", lambda df, source: None)

    with pytest.raises(PartialFailureError):
        pull_social.main()

    # The failure must not have cost the Henry Hub topic's own real data.
    assert written_ts_long, "Henry Hub's rows should still have been written"


def test_main_does_not_raise_on_a_genuinely_quiet_run_with_no_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reddit's confirmed ~1-request/60s pace makes an all-empty-but-no-errors
    # run a real outcome (see pipelines/social/CLAUDE.md), not a bug -- this
    # must NOT be indistinguishable from a total failure by raising.
    monkeypatch.setattr(
        pull_social,
        "TOPIC_QUERIES",
        [
            {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
        ],
    )
    monkeypatch.setattr(pull_social, "TICKER_QUERIES", ["XOM"])
    monkeypatch.setattr(pull_social, "POLYMARKET_TAGS", ["energy"])

    monkeypatch.setattr(pull_social, "fetch_reddit", lambda query, **kw: [])
    monkeypatch.setattr(pull_social, "fetch_stocktwits", lambda symbol, **kw: [])
    monkeypatch.setattr(pull_social, "fetch_polymarket", lambda tag_slug, **kw: [])

    pull_social.main()  # must not raise


def test_main_writes_per_source_and_dedupes_events_when_posts_are_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pull_social,
        "TOPIC_QUERIES",
        [
            {"slug": "henry_hub", "query": "Henry Hub", "commodity": "gas", "theme": "gas_lng"},
        ],
    )
    monkeypatch.setattr(pull_social, "TICKER_QUERIES", ["XOM"])
    monkeypatch.setattr(pull_social, "POLYMARKET_TAGS", ["energy"])

    # Same URL from two different subjects -- proves cross-run event dedup by
    # event_id, since posts_to_events hashes the URL.
    shared_post = _post("Henry Hub spikes", "https://x.test/shared", "reddit", "Henry Hub")

    def fake_reddit(query: str, **kw: object) -> list[Post]:
        if query == "Henry Hub":
            return [shared_post]
        if query == "XOM":
            return [_post("XOM rallies", "https://x.test/shared", "reddit", "XOM")]
        return []

    monkeypatch.setattr(pull_social, "fetch_reddit", fake_reddit)
    monkeypatch.setattr(pull_social, "fetch_stocktwits", lambda symbol, **kw: [])
    monkeypatch.setattr(pull_social, "fetch_polymarket", lambda tag_slug, **kw: [])

    written_ts_long = []
    written_events = []
    monkeypatch.setattr(
        pull_social,
        "write_ts_long",
        lambda df, source: written_ts_long.append((source, df)),
    )
    monkeypatch.setattr(
        pull_social,
        "write_events",
        lambda df, source: written_events.append((source, df)),
    )

    pull_social.main()  # must not raise

    assert written_ts_long, "some rows must have been written"
    assert all(source == "reddit" for source, _ in written_ts_long)
    assert len(written_events) == 1
    _, events_df = written_events[0]
    # Both posts share a URL -> share an event_id -> dedup collapses them to 1.
    assert len(events_df) == 1
