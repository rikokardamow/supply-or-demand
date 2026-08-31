"""Derived series for OPEC MOMR data -- computed at read time, not stored."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

QUOTAS_PATH = Path("pipelines/opec_momr/quotas.csv")


def load_quotas() -> pd.DataFrame:
    """Hand-maintained CSV, per specs/06_opec-supply.md's data model. Confirmed
    live (Session B): the "Voluntary 8" group's targets change roughly monthly
    (OPEC's own press releases) -- this isn't a "set once" file, update it as
    new levels are announced. See pipelines/opec_momr/CLAUDE.md for the source
    and current coverage (7 of the group's countries; UAE already reached its
    ceiling and isn't part of the monthly incremental announcements)."""
    return pd.read_csv(QUOTAS_PATH, parse_dates=["effective_from"])


def production_vs_quota(
    actual_by_country: pd.Series, quotas: pd.DataFrame | None = None
) -> pd.DataFrame:
    """`actual_by_country`: index=country, value=latest actual production (same
    unit as quotas.csv, tb/d==kbd). Returns one row per country present in
    both, with a compliance % (actual / quota * 100) and the raw gap.

    Known simplification: uses each country's most recently effective quota
    row regardless of the actual production month it's compared against --
    OPEC+ announces each month's target about a month ahead of when it takes
    effect, so "latest actual" and "latest announced target" are usually a
    month or two apart in real time. A precise point-in-time comparison would
    need quotas.csv to carry a full history matched to each actual month;
    revisit if that becomes the sole open item."""
    if quotas is None:
        quotas = load_quotas()
    latest_quota = quotas.sort_values("effective_from").groupby("country").last()["quota_kbd"]

    countries = sorted(set(actual_by_country.index) & set(latest_quota.index))
    result = pd.DataFrame(
        {
            "country": countries,
            "actual_kbd": [actual_by_country[c] for c in countries],
            "quota_kbd": [latest_quota[c] for c in countries],
        }
    )
    result["compliance_pct"] = 100 * result["actual_kbd"] / result["quota_kbd"]
    result["gap_kbd"] = result["actual_kbd"] - result["quota_kbd"]
    return result.sort_values("quota_kbd", ascending=False).reset_index(drop=True)


def revision_waterfall(revision_df: pd.DataFrame, period_ts: pd.Timestamp) -> pd.DataFrame:
    """`revision_df`: a long ts_long-shaped frame read from the
    `demand_balance_revision` series (Table 11-2 -- OPEC's own precomputed
    current-vs-last-month deltas, confirmed live in Session A; this project
    doesn't diff two stored vintages itself). Returns the per-line-item deltas
    for one period, sorted by absolute size, ready for a waterfall chart."""
    period_rows = revision_df[revision_df["ts"] == period_ts].copy()
    label_parts = period_rows["series_id"].str.split(".")
    period_rows["label"] = label_parts.str[2:-1].str.join(".")
    result = period_rows[["label", "value"]]
    return result.sort_values("value", key=abs, ascending=False).reset_index(drop=True)
