from __future__ import annotations

import pytest
from pipelines.social import client
from pipelines.social.client import fetch_reddit


@pytest.fixture(autouse=True)
def _skip_real_pacing_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reddit's live rate limit paces requests ~60s apart (confirmed live, see
    pipelines/social/CLAUDE.md); that pacing is exercised for real by the live
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
