"""ENTSOG-specific transforms. Point-level flows are what's stored (per the spec's data
model); corridor totals are computed here at read time, not pre-stored."""

from __future__ import annotations

import pandas as pd

from pipelines.entsog.corridors import PointSpec


def corridor_aggregate(
    flows_df: pd.DataFrame, corridors: dict[str, list[PointSpec]], mode: str = "pipeline"
) -> pd.DataFrame:
    """Sum point-level flow values into one row per (corridor, day). `flows_df` is the
    raw point-level `flows` table (no point/corridor identifier column of its own), so
    corridor membership is reconstructed from each point's (from_node, to_node) pair —
    safe because no two corridors in corridors.py share a pair. Returns columns
    ["corridor", "ts", "value"]; rows whose (from_node, to_node) isn't in any corridor
    are silently dropped (e.g. a point-level row from a corridor not in `corridors`)."""
    pair_to_corridor = {
        (point.from_node, point.to_node): corridor_name
        for corridor_name, points in corridors.items()
        for point in points
    }

    df = flows_df[flows_df["mode"] == mode].copy()
    df["corridor"] = list(zip(df["from_node"], df["to_node"], strict=False))
    df["corridor"] = df["corridor"].map(pair_to_corridor)
    df = df.dropna(subset=["corridor"])

    result: pd.DataFrame = df.groupby(["corridor", "ts"])["value"].sum().reset_index()
    return result


def pair_daily_totals(flows_df: pd.DataFrame, mode: str = "pipeline") -> pd.DataFrame:
    """Sum same-day values across points sharing a (from_node, to_node) pair (e.g.
    NO_EXPORTS has 2-3 active points landing at the same country) *before* any
    trailing-window average — skipping this silently divides a multi-point pair's sum
    by (days x points) instead of just days, understating it. Returns columns
    ["from_node", "to_node", "ts", "value"]."""
    df = flows_df[flows_df["mode"] == mode]
    result: pd.DataFrame = (
        df.groupby(["from_node", "to_node", "ts"])["value"].sum().reset_index()
    )
    return result


def physical_vs_nomination_gap(
    flows_df: pd.DataFrame, corridors: dict[str, list[PointSpec]], corridor_name: str
) -> pd.DataFrame:
    """Nomination minus physical flow, per day, for one corridor — positive means less
    gas physically flowed than was nominated (the under-delivery signal from the spec's
    alpha question). Both sides are built from corridor_aggregate so they're aggregated
    identically; an inner join drops any day where one side has no data, since a gap
    needs both real numbers, not a comparison against an implicit zero. Returns columns
    ["ts", "physical", "nomination", "gap"]."""
    physical = corridor_aggregate(flows_df, corridors, mode="pipeline")
    physical = physical[physical["corridor"] == corridor_name].rename(
        columns={"value": "physical"}
    )
    nomination = corridor_aggregate(flows_df, corridors, mode="nomination")
    nomination = nomination[nomination["corridor"] == corridor_name].rename(
        columns={"value": "nomination"}
    )

    merged = physical.merge(nomination, on="ts", how="inner")
    merged["gap"] = merged["nomination"] - merged["physical"]
    return merged[["ts", "physical", "nomination", "gap"]]


def latest_complete_date(daily_df: pd.DataFrame, group_cols: list[str]) -> pd.Timestamp:
    """The most recent date by which every group (e.g. every corridor pair) has already
    reported. ENTSOG points/operators publish on staggered schedules — confirmed live,
    up to 2 days' difference across this project's corridor points — so anchoring a
    trailing-window average to the raw global max date would silently include a
    partially-reported tail day for some groups but not others, breaking any
    cross-group total comparison (e.g. Sankey vs. corridor time series)."""
    per_group_max = daily_df.groupby(group_cols)["ts"].max()
    result: pd.Timestamp = per_group_max.min()
    return result
