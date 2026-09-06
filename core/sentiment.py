"""Spec 29's two-source reconciliation -- the only place the adanos.* and social.*
namespaces meet.

The two are never blended. No weighted average, no "consensus" series: the two
numbers and the signed gap between them are the output. This is the same
convention the trading layer already applies to published benchmarks shown beside
repo estimates with the deviation, rather than merged into one.

Only the two sentiment_score series are comparable -- both are on -1..+1. Adanos's
buzz_score (0-100) and our post_count are different quantities and are deliberately
not compared."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.storage import read_ts_long

DEFAULT_CORRELATION_WINDOW = 14

_OVERLAP_COLUMNS = ["ts", "adanos", "social", "gap"]


@dataclass(frozen=True)
class Overlap:
    """`dropped_days` travels with the frame on purpose: a deviation computed over
    three overlapping days is not a finding, and the UI must be able to say so."""

    frame: pd.DataFrame
    overlap_days: int
    dropped_days: int


def overlap(ticker: str, platform: str = "reddit") -> Overlap:
    """Inner-join the vendor and self-hosted sentiment series for one ticker and
    platform. Columns: ts, adanos, social, gap (signed, social - adanos).

    Joins against `social.*.snapshot_sentiment_score`, not `social.*.sentiment_score`
    -- deliberately. Adanos writes one row per *pull* date; the plain
    `sentiment_score` series is grouped by each post's own date, which for
    Reddit's RSS feed can be weeks or months in the past and essentially never
    coincides with a pull date. Comparing the two was Spec 29's original defect:
    real evidence from the lake showed adanos.reddit.xom writing on 2026-09-03/06
    while social.reddit.xom.sentiment_score wrote on entirely different dates
    (2026-04-29, 05-04, 06-12, 07-12, 09-03), giving near-zero overlap regardless
    of how much history accumulated. `snapshot_sentiment_score` is written at
    `ts = ingested_at` (the pull date, see pipelines/social/score.py), so it is
    on the same axis as Adanos and is the only series this join may use.

    `dropped_days` is the count of distinct days where one side reported a value
    and the other did not -- total distinct days across both series minus the
    days both reported."""
    subject = ticker.lower()
    adanos_id = f"adanos.{platform}.{subject}.sentiment_score"
    social_id = f"social.{platform}.{subject}.snapshot_sentiment_score"

    raw = read_ts_long(series_ids=[adanos_id, social_id])
    if raw.empty:
        return Overlap(
            frame=pd.DataFrame(columns=_OVERLAP_COLUMNS),
            overlap_days=0,
            dropped_days=0,
        )

    wide = (
        raw.assign(day=pd.to_datetime(raw["ts"]).dt.normalize())
        .pivot_table(index="day", columns="series_id", values="value", aggfunc="mean")
        .rename(columns={adanos_id: "adanos", social_id: "social"})
    )
    for column in ("adanos", "social"):
        if column not in wide.columns:
            wide[column] = pd.NA

    total_days = len(wide)
    joined = wide.dropna(subset=["adanos", "social"]).reset_index(names="ts")
    joined["adanos"] = joined["adanos"].astype(float)
    joined["social"] = joined["social"].astype(float)
    joined["gap"] = joined["social"] - joined["adanos"]

    return Overlap(
        frame=joined[_OVERLAP_COLUMNS],
        overlap_days=len(joined),
        dropped_days=total_days - len(joined),
    )


def disagrees_on_sign(adanos: pd.Series, social: pd.Series) -> pd.Series:
    """The one definition of "disagree on sign" -- both `agreement_rate` below and
    apps/dashboard/pages/10_macro.py's deviation-bar colouring call this rather than
    each re-deriving their own rule, which previously let the two silently diverge
    (`np.sign(a) == np.sign(b)` here vs. `adanos * social < 0` on the page).

    Exact 0.0 is common, not an edge case: VADER returns exactly 0.0 for any title
    with no lexicon hit, and score.py returns 0.0 for empty text. Treating a 0.0 as
    "a sign" would flag a neutral, no-signal reading as disagreeing with a genuine
    nonzero value on the other side -- so 0.0 on either side is never a disagreement.
    Only a strictly negative value against a strictly positive one counts, which is
    exactly `adanos * social < 0`."""
    return (adanos.astype(float) * social.astype(float)) < 0


def agreement_rate(frame: pd.DataFrame) -> float | None:
    """Share of overlapping days where the two sources do not disagree on sign (see
    `disagrees_on_sign`). `None` for an empty frame -- no days, nothing to report,
    and 0.0 would read as "total disagreement" rather than "no data"."""
    if frame.empty:
        return None
    disagree = disagrees_on_sign(frame["adanos"], frame["social"])
    return float((~disagree).mean())


def rolling_correlation(frame: pd.DataFrame, window: int = DEFAULT_CORRELATION_WINDOW) -> pd.Series:
    """Rolling correlation between the two sources over `window` overlapping days.
    Short frames yield NaNs rather than a fabricated single-point correlation."""
    if frame.empty:
        return pd.Series(dtype="float64")
    return frame["adanos"].astype(float).rolling(window).corr(frame["social"].astype(float))
