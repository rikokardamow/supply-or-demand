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


def test_snapshot_rows_are_written_at_the_pull_date_not_post_dates() -> None:
    # Reddit's RSS feed can return posts spanning weeks or months in one call, so
    # the post-dated axis (post_count/sentiment_score, grouped by each post's own
    # date) and the pull-dated axis (snapshot_post_count/snapshot_sentiment_score,
    # grouped by the run's ingested_at) must land on genuinely different `ts`
    # values here -- that gap is the whole point of the fix.
    posts = [
        _post("old post", "2026-04-29T10:00Z"),
        _post("newer post", "2026-07-12T10:00Z"),
    ]
    ingested_at = pd.Timestamp("2026-09-06T12:00Z")

    rows = aggregate_to_ts_long(posts, subject="xom", ingested_at=ingested_at)

    validate_ts_long(rows)
    snapshot_count = rows[rows["series_id"] == "social.reddit.xom.snapshot_post_count"].iloc[0]
    snapshot_sentiment = rows[
        rows["series_id"] == "social.reddit.xom.snapshot_sentiment_score"
    ].iloc[0]

    assert snapshot_count["ts"] == pd.Timestamp("2026-09-06")
    assert snapshot_sentiment["ts"] == pd.Timestamp("2026-09-06")
    # Both source posts fall inside the one snapshot -- pull-dated grouping does
    # not split them by their own (very different) post dates.
    assert snapshot_count["value"] == 2.0
    assert snapshot_count["unit"] == "count"
    assert snapshot_sentiment["unit"] == "score_neg1_to_1"

    # The post-dated rows must still land on the posts' own days, not the pull day.
    post_dated_ts = set(
        rows[rows["series_id"] == "social.reddit.xom.post_count"]["ts"]
    )
    assert post_dated_ts == {pd.Timestamp("2026-04-29"), pd.Timestamp("2026-07-12")}
    assert pd.Timestamp("2026-09-06") not in post_dated_ts


def test_no_posts_produces_no_snapshot_rows_at_all() -> None:
    # The missing-not-zero rule applies to the snapshot axis too: a subject with
    # no posts this run must emit no snapshot rows, never a zero-valued one. This
    # would fail against a broken implementation that special-cased the snapshot
    # axis to always emit a zero-count row regardless of `posts`.
    ingested_at = pd.Timestamp("2026-09-06T12:00Z")
    rows = aggregate_to_ts_long([], subject="xom", ingested_at=ingested_at)
    assert rows.empty
    assert "social.reddit.xom.snapshot_post_count" not in set(rows.get("series_id", []))


def test_snapshot_rows_are_grouped_per_platform_not_across_platforms() -> None:
    # pull_ticker feeds Reddit + StockTwits posts into one aggregate_to_ts_long
    # call. A platform with zero posts this run must get no snapshot row -- the
    # same missing-not-zero rule, just triggered per-platform inside one call
    # rather than by an empty `posts` list.
    posts = [_post("reddit only", "2026-09-01T10:00Z")]
    posts[0]["platform"] = "reddit"
    ingested_at = pd.Timestamp("2026-09-06T12:00Z")

    rows = aggregate_to_ts_long(posts, subject="xom", ingested_at=ingested_at)

    ids = set(rows["series_id"])
    assert "social.reddit.xom.snapshot_post_count" in ids
    assert "social.stocktwits.xom.snapshot_post_count" not in ids
