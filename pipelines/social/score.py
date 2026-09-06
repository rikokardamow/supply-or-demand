"""Deterministic lexicon scoring for Spec 29.

Deliberately not an LLM. The project's test story is vcrpy cassettes and
00_TRADING_CONVENTIONS requires a model card with window/refit/OOS for anything
estimated; a lexicon scorer is reproducible, offline and free, so the same text
always yields the same score and a regression is a real regression. LLM scoring is
deferred to its own spec, where it would land as a separately-named social_llm.*
series with a pinned model ID -- never as a silent upgrade to social.*.

Honest limitation, stated rather than hidden: VADER is calibrated on general
social-media English, not energy-trading jargon. "Crude tanking" is bearish price
language, not negative sentiment about crude. See this package's NOTES.md."""

from __future__ import annotations

import pandas as pd
from core.schemas import TS_LONG_SCHEMA
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from pipelines.social.client import Post

COUNT_UNIT = "count"
SENTIMENT_UNIT = "score_neg1_to_1"

_ANALYSER = SentimentIntensityAnalyzer()


def score_text(text: str) -> float:
    """VADER's compound score, already on -1..+1. Empty text scores exactly 0.0."""
    if not text.strip():
        return 0.0
    compound: float = _ANALYSER.polarity_scores(text)["compound"]
    return compound


def aggregate_to_ts_long(
    posts: list[Post], subject: str, ingested_at: pd.Timestamp
) -> pd.DataFrame:
    """Two axes, both grouped by platform, never blended:

    - **Post-dated**: one `post_count` row and one `sentiment_score` row per
      (platform, day), `day` being each post's own timestamp. This is real
      history -- Reddit's RSS feed returns whatever recent posts match the
      query, which can span weeks or months in one call, so this axis is not a
      pull-date snapshot and must never be read as one.
    - **Pull-dated snapshot**: one `snapshot_post_count` row and one
      `snapshot_sentiment_score` row per platform, at `ts = ingested_at`
      (normalised to midnight), over *every* post fetched this run regardless
      of the post's own date. This is the same kind of measurement Adanos
      makes (one row per pull date) and is what `core/sentiment.py::overlap`
      compares Adanos against -- comparing Adanos's pull-dated series against
      our post-dated one was Spec 29's original defect: Adanos writes one row
      per pull, we wrote one row per post date, and RSS's post dates almost
      never coincide with a pull date, so the two series were structurally
      never comparable no matter how much history accumulated.

    Returns an empty frame when there are no posts -- a zero-valued row on
    either axis would assert "we looked and found nothing" on a run we may not
    have looked at all, which is exactly the fabricated-zero failure Spec 17
    caught. A subject with no posts this run therefore gets no snapshot rows
    either, not a zero snapshot."""
    if not posts:
        empty: pd.DataFrame = TS_LONG_SCHEMA.empty_table().to_pandas()
        return empty

    frame = pd.DataFrame(
        {
            "platform": [p["platform"] for p in posts],
            "day": [pd.Timestamp(p["ts"]).tz_localize(None).normalize() for p in posts],
            "sentiment": [score_text(p["title"]) for p in posts],
        }
    )

    rows: list[dict[str, object]] = []
    for (platform, day), group in frame.groupby(["platform", "day"]):
        base = {
            "source": platform,
            "ts": day,
            "geo": "",
            "freq": "D",
            "revision_date": ingested_at,
        }
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.post_count",
                "value": float(len(group)),
                "unit": COUNT_UNIT,
            }
        )
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.sentiment_score",
                "value": float(group["sentiment"].mean()),
                "unit": SENTIMENT_UNIT,
            }
        )

    snapshot_ts = pd.Timestamp(ingested_at).tz_localize(None).normalize()
    for platform_key, group in frame.groupby("platform"):
        platform = str(platform_key)
        base = {
            "source": platform,
            "ts": snapshot_ts,
            "geo": "",
            "freq": "D",
            "revision_date": ingested_at,
        }
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.snapshot_post_count",
                "value": float(len(group)),
                "unit": COUNT_UNIT,
            }
        )
        rows.append(
            {
                **base,
                "series_id": f"social.{platform}.{subject}.snapshot_sentiment_score",
                "value": float(group["sentiment"].mean()),
                "unit": SENTIMENT_UNIT,
            }
        )
    return pd.DataFrame(rows)
