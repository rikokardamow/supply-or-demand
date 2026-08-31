"""OPEC / Global Supply Monitoring (MOMR + JODI + Baker Hughes). Session B scope
(specs/06_opec-supply.md): DoC production-vs-quota grouped bars, and the MOMR
revision waterfall. JODI and Baker Hughes land in later sessions."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from core.storage import read_ts_long
from core.theme import production_vs_quota_chart, revision_waterfall_chart
from pipelines.opec_momr.transforms import load_quotas, production_vs_quota, revision_waterfall


def _production_vs_quota_section() -> None:
    quotas = load_quotas()
    countries = sorted(quotas["country"].unique())
    series_ids = [f"momr.doc_crude_secondary.{_slug(c)}.monthly" for c in countries]
    long_df = read_ts_long(series_ids=series_ids)
    if long_df.empty:
        st.info("No data yet — run `pipelines/opec_momr/pull_doc_crude.py <pdf path>`.")
        return

    slug_to_country = {_slug(c): c for c in countries}
    long_df = long_df.copy()
    long_df["country"] = long_df["series_id"].str.split(".").str[2].map(slug_to_country)
    latest_ts = long_df["ts"].max()
    latest = long_df[long_df["ts"] == latest_ts].set_index("country")["value"]

    result = production_vs_quota(latest, quotas)
    fig = production_vs_quota_chart(
        result, title=f"DoC Crude Production vs. Quota — {latest_ts:%B %Y}", unit="tb/d"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Quota is each country's most recently announced voluntary-adjustment target "
        "(not necessarily the same month as the actual shown) — see "
        "pipelines/opec_momr/NOTES.md."
    )


def _revision_waterfall_section() -> None:
    rev = read_ts_long(series_ids=None)
    rev = rev[rev["series_id"].str.startswith("momr.demand_balance_revision")]
    if rev.empty:
        st.info("No data yet — run `pipelines/opec_momr/pull_momr.py`.")
        return

    periods = sorted(rev["ts"].unique(), reverse=True)
    current_year_start = pd.Timestamp(f"{pd.Timestamp.today().year}-01-01")
    default_idx = next((i for i, p in enumerate(periods) if p == current_year_start), 0)
    period = st.selectbox(
        "Period", options=periods, index=default_idx, format_func=_format_period
    )

    result = revision_waterfall(rev, period)
    result = result[result["value"] != 0].head(15)
    if result.empty:
        st.info(f"No non-zero revisions for {period:%B %Y}.")
        return
    fig = revision_waterfall_chart(
        result, title=f"MOMR Revision Waterfall — {period:%B %Y}", unit="mb/d"
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "OPEC's own precomputed change-vs-last-month figures (Table 11-2) — not "
        "re-derived from consecutive vintages."
    )


def _slug(label: str) -> str:
    return label.lower().replace(" ", "_")


def _format_period(period: pd.Timestamp) -> str:
    if period.month == 1:
        return f"{period.year} (annual)"
    quarter = (period.month - 1) // 3 + 1
    return f"{quarter}Q{period.year % 100}"


st.title("OPEC / Global Supply Monitoring")

st.subheader("DoC production vs. quota")
_production_vs_quota_section()

st.subheader("MOMR revision waterfall")
_revision_waterfall_section()
