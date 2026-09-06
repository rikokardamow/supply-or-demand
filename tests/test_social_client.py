from __future__ import annotations

import io
import json
import logging
from email.message import Message
from urllib.error import HTTPError

import pytest
from pipelines.social import client
from pipelines.social.client import fetch_polymarket, fetch_reddit, fetch_stocktwits


@pytest.fixture(autouse=True)
def _skip_real_pacing_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reddit's live rate limit paces requests ~60s apart (confirmed live, see
    pipelines/social/NOTES.md); that pacing is exercised for real by the live
    probes recorded there, not by these cassette-replay tests. Patch the
    module's sleep hook to a no-op so replay stays fast."""
    monkeypatch.setattr(client, "_sleep", lambda seconds: None)


@pytest.mark.vcr
def test_fetch_reddit_returns_typed_posts_with_the_query_attached() -> None:
    posts = fetch_reddit("Henry Hub", subreddits=["energy"], limit=25)

    assert posts, "cassette should carry at least one entry"
    first = posts[0]
    assert set(first) == {
        "post_id", "url", "title", "ts", "platform", "query", "score", "num_comments"
    }
    assert first["platform"] == "reddit"
    assert first["query"] == "Henry Hub"
    assert first["url"].startswith("http")
    assert first["title"]


@pytest.mark.vcr
def test_reddit_rss_posts_carry_missing_metrics_never_zero() -> None:
    # The single most important constraint in Spec 29. RSS has no score and no
    # comment count; writing 0 would be indistinguishable from a real zero --
    # the same failure mode Spec 17 caught in Adanos's zeroed rows.
    posts = fetch_reddit("Henry Hub", subreddits=["energy"], limit=25)

    assert all(p["score"] is None for p in posts)
    assert all(p["num_comments"] is None for p in posts)


@pytest.mark.vcr
def test_fetch_polymarket_returns_typed_posts_for_tag_slug() -> None:
    # Polymarket has no keyword search (Task 0, confirmed live: `q` and `search`
    # are silently ignored). `tag_slug` is the only real filter, so the fetcher
    # takes a tag, not free text, and stamps `query` with the tag used.
    posts = fetch_polymarket("energy", limit=5)

    assert posts
    assert all(p["platform"] == "polymarket" for p in posts)
    assert all(p["query"] == "energy" for p in posts)
    assert all(isinstance(p["title"], str) and p["title"] for p in posts)
    assert all(isinstance(p["post_id"], str) for p in posts)
    assert all(p["url"].startswith("https://polymarket.com/event/") for p in posts)
    # Polymarket has no per-event score field -- must stay None, never a
    # fabricated 0.
    assert all(p["score"] is None for p in posts)
    # Unlike score, Polymarket DOES carry a genuine top-level `commentCount`
    # (confirmed live, Task 0) -- it must be used, not left None just because
    # the original brief guessed a different, wrong field name.
    assert any(isinstance(p["num_comments"], int) for p in posts)


@pytest.mark.vcr
def test_fetch_polymarket_tag_slug_actually_filters() -> None:
    # Polymarket is one of two platforms in this pipeline that return HTTP 200
    # with plausible rows while silently ignoring a filter parameter (Task 0:
    # q/search; Task 2: Reddit's site-wide search). tag_slug is the one
    # parameter Task 0 confirmed live actually filters -- prove it here by
    # checking two different tags return genuinely disjoint event sets, not the
    # same rows relabelled under a different `query`.
    energy_posts = fetch_polymarket("energy", limit=5)
    geopolitics_posts = fetch_polymarket("geopolitics", limit=5)

    energy_ids = {p["post_id"] for p in energy_posts}
    geopolitics_ids = {p["post_id"] for p in geopolitics_posts}

    assert energy_ids, "energy tag should return rows"
    assert geopolitics_ids, "geopolitics tag should return rows"
    assert energy_ids.isdisjoint(geopolitics_ids), (
        "different tag_slug values must not return identical events"
    )
    assert all(p["query"] == "energy" for p in energy_posts)
    assert all(p["query"] == "geopolitics" for p in geopolitics_posts)


@pytest.mark.vcr
def test_fetch_stocktwits_returns_typed_posts_with_real_metrics() -> None:
    posts = fetch_stocktwits("XOM", limit=5)

    assert posts
    assert all(p["platform"] == "stocktwits" for p in posts)
    assert all(p["query"] == "XOM" for p in posts)
    assert all(isinstance(p["post_id"], str) for p in posts)
    assert all(isinstance(p["title"], str) and p["title"] for p in posts)
    assert all(p["url"].startswith("https://stocktwits.com/") for p in posts)
    # StockTwits' JSON API exposes no numeric score and no comment count on a
    # message -- both must stay None, never a fabricated 0.
    assert all(p["score"] is None for p in posts)
    assert all(p["num_comments"] is None for p in posts)


class _FakeHTTPResponse:
    """Minimal context-manager stand-in for `http.client.HTTPResponse`."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _fake_403(url: str) -> HTTPError:
    return HTTPError(url, 403, "Forbidden", Message(), io.BytesIO(b""))


def test_fetch_stocktwits_retries_once_after_a_single_non_2xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 0 saw one unexplained HTTP 403 with an empty body sandwiched between
    clean 200s; five immediate retries afterwards all succeeded. A single
    transient failure must not be treated as StockTwits blocking us, and must
    not silently produce an empty list -- it must retry once and succeed."""
    payload = json.dumps(
        {
            "messages": [
                {
                    "id": 1,
                    "body": "hi",
                    "created_at": "2026-01-01T00:00:00Z",
                    "user": {"username": "trader1"},
                }
            ]
        }
    ).encode()
    calls = {"n": 0}

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeHTTPResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _fake_403(getattr(request, "full_url", "https://example.test"))
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    monkeypatch.setattr(client, "_sleep", lambda seconds: None)

    posts = fetch_stocktwits("XOM", limit=5)

    assert calls["n"] == 2, "must retry exactly once, not zero and not repeatedly"
    assert posts and posts[0]["post_id"] == "1"


def test_fetch_stocktwits_gives_up_and_logs_after_a_second_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """After the retry also fails, give up loudly: log the real status code and
    raise, rather than silently returning an empty list."""

    def fake_urlopen(request: object, timeout: float | None = None) -> _FakeHTTPResponse:
        raise _fake_403(getattr(request, "full_url", "https://example.test"))

    monkeypatch.setattr(client, "urlopen", fake_urlopen)
    monkeypatch.setattr(client, "_sleep", lambda seconds: None)

    with (
        caplog.at_level(logging.ERROR, logger="pipelines.social.client"),
        pytest.raises(HTTPError),
    ):
        fetch_stocktwits("XOM", limit=5)

    assert "403" in caplog.text
