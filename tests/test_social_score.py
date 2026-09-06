from __future__ import annotations

import pandas as pd
from core.schemas import validate_ts_long
from pipelines.social.client import Post
from pipelines.social.score import aggregate_to_ts_long, score_text


def _post(title: str, ts: str) -> Post:
    return Post(
        post_id=title, url=f"https://example.test/{title}", title=title,
        ts=pd.Timestamp(ts), platform="reddit", query="Henry Hub",
        score=None, num_comments=None,
    )


def test_score_text_is_deterministic_and_bounded() -> None:
    assert score_text("This is great news") == score_text("This is great news")
    assert -1.0 <= score_text("This is great news") <= 1.0
    assert score_text("This is great news") > 0
    assert score_text("terrible awful disaster") < 0
    assert score_text("") == 0.0


def test_score_text_is_deterministic_across_separate_analyser_uses() -> None:
    # score_text(x) == score_text(x) is trivially true for almost any implementation
    # (including a broken constant-returning one), so this pins the property that
    # actually matters: repeated, independent calls -- interleaved with other input
    # -- produce byte-identical results, and different inputs produce different
    # scores. A constant-returning scorer would pass the naive self-equality check
    # but fails the "differs by input" assertion below.
    first = score_text("This is great news")
    score_text("unrelated filler text")
    second = score_text("This is great news")
    assert first == second
    assert score_text("great") != score_text("terrible")


def test_aggregate_produces_valid_ts_long_with_post_count_and_sentiment() -> None:
    posts = [_post("great news", "2026-09-01T10:00Z"), _post("awful", "2026-09-01T12:00Z")]
    ingested_at = pd.Timestamp("2026-09-01T18:00Z")

    rows = aggregate_to_ts_long(posts, subject="henry_hub", ingested_at=ingested_at)

    validate_ts_long(rows)
    ids = set(rows["series_id"])
    assert "social.reddit.henry_hub.post_count" in ids
    assert "social.reddit.henry_hub.sentiment_score" in ids
    count_row = rows[rows["series_id"] == "social.reddit.henry_hub.post_count"].iloc[0]
    assert count_row["value"] == 2.0
    assert count_row["unit"] == "count"
    assert count_row["source"] == "reddit"
    assert count_row["freq"] == "D"


def test_aggregate_sentiment_score_is_the_mean_not_a_placeholder() -> None:
    # A broken aggregator could hard-code sentiment_score to 0.0 or to post_count
    # and still pass the previous test (it only checks the id and unit exist).
    # This pins the actual numeric relationship: the mean of the two posts'
    # individual scores, not any fixed value.
    posts = [_post("great news", "2026-09-01T10:00Z"), _post("awful", "2026-09-01T12:00Z")]
    expected_mean = (score_text("great news") + score_text("awful")) / 2
    ingested_at = pd.Timestamp("2026-09-01T18:00Z")

    rows = aggregate_to_ts_long(posts, subject="henry_hub", ingested_at=ingested_at)

    sentiment_row = rows[rows["series_id"] == "social.reddit.henry_hub.sentiment_score"].iloc[0]
    assert sentiment_row["value"] == expected_mean
    assert sentiment_row["unit"] == "score_neg1_to_1"


def test_aggregate_returns_empty_for_no_posts_never_a_zero_row() -> None:
    # A zero post_count row would assert "we looked and found nothing" on a day we
    # may simply not have looked. Absent means absent -- the Spec 17 lesson.
    ingested_at = pd.Timestamp("2026-09-01T18:00Z")
    rows = aggregate_to_ts_long([], subject="henry_hub", ingested_at=ingested_at)
    assert rows.empty
