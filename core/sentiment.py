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

import numpy as np
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

    `dropped_days` is the count of distinct days where one side reported a value
    and the other did not -- total distinct days across both series minus the
    days both reported."""
    subject = ticker.lower()
    adanos_id = f"adanos.{platform}.{subject}.sentiment_score"
    social_id = f"social.{platform}.{subject}.sentiment_score"

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


def agreement_rate(frame: pd.DataFrame) -> float:
    """Share of overlapping days where the two sources agree on the sign of
    sentiment. 0.0 for an empty frame -- no days, no agreement to report."""
    if frame.empty:
        return 0.0
    agree = np.sign(frame["adanos"].astype(float)) == np.sign(frame["social"].astype(float))
    return float(agree.mean())


def rolling_correlation(frame: pd.DataFrame, window: int = DEFAULT_CORRELATION_WINDOW) -> pd.Series:
    """Rolling correlation between the two sources over `window` overlapping days.
    Short frames yield NaNs rather than a fabricated single-point correlation."""
    if frame.empty:
        return pd.Series(dtype="float64")
    return frame["adanos"].astype(float).rolling(window).corr(frame["social"].astype(float))
