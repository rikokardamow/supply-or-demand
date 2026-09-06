"""OPEC / Global Supply Monitoring (MOMR + JODI + Baker Hughes). Session B:
DoC production-vs-quota grouped bars, MOMR revision waterfall. Session D: US
oil rig count. Rigs vs. WTI stays a single series until Spec 07 (Henry
Hub/WTI) exists, per the spec's own "until then rigs only" note."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from components.card import card
from components.event_overlay import add_event_markers
from components.lake import read_ts_long
from core.theme import (
    production_vs_quota_chart,
    revision_waterfall_chart,
    simple_time_series_chart,
    time_series_area_chart,
)
from pipelines.opec_momr.transforms import load_quotas, production_vs_quota, revision_waterfall

RIG_COUNT_RANGE_DAYS = {"6M": 182, "1Y": 365, "2Y": 730, "All": None}


def _country_filter_panel(countries: list[str], latest: pd.Series) -> list[str]:
    """Collapsible filter panel (accordion + checkboxes + live counts) -- see
    02_gas_storage.py's _country_filter_panel for the same convention."""
    for country in countries:
        st.session_state.setdefault(f"supply_quota_filter_{country}", True)
    selected_count = sum(st.session_state[f"supply_quota_filter_{c}"] for c in countries)

    with st.expander(f"Filter countries ({selected_count} of {len(countries)} shown)"):
        filter_cols = st.columns(3)
        for i, country in enumerate(countries):
            value = latest.get(country)
            label = f"{country} — {value:,.0f} tb/d" if value is not None else country
            with filter_cols[i % 3]:
                st.checkbox(label, key=f"supply_quota_filter_{country}")

    return [c for c in countries if st.session_state[f"supply_quota_filter_{c}"]]


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

    selected_countries = _country_filter_panel(countries, latest)
    if not selected_countries:
        st.info("No countries selected — check at least one above.")
        return

    result = production_vs_quota(latest, quotas)
    result = result[result["country"].isin(selected_countries)]
    title = f"DoC Crude Production vs. Quota — {latest_ts:%B %Y}"
    fig = production_vs_quota_chart(result, title=title, unit="tb/d")
    with card(title):
        st.plotly_chart(fig)
        st.caption(
            "Quota is each country's most recently announced voluntary-adjustment target "
            "(not necessarily the same month as the actual shown) — see "
            "pipelines/opec_momr/CLAUDE.md."
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
    title = f"MOMR Revision Waterfall — {period:%B %Y}"
    fig = revision_waterfall_chart(result, title=title, unit="mb/d")
    with card(title):
        st.plotly_chart(fig)
        st.caption(
            "OPEC's own precomputed change-vs-last-month figures (Table 11-2) — not "
            "re-derived from consecutive vintages."
        )


def _oil_on_water_section() -> None:
    long_df = read_ts_long(
        series_ids=["momr.oecd_stocks.closing_stock_levels_mb.oilonwater.quarterly"]
    )
    if long_df.empty:
        st.info("No data yet — run `pipelines/opec_momr/pull_momr.py`.")
        return

    series = long_df.sort_values("ts").set_index("ts")["value"]
    title = "Oil-on-Water (OECD)"
    fig = time_series_area_chart(series, title=title, unit="mb")
    add_event_markers(fig, commodity="crude")
    with card(title):
        st.plotly_chart(fig)
        st.caption(
            "OPEC's own MOMR appendix (Table 11-3) trailing-quarters view, combined "
            "across stored vintages — not a continuous monthly series. Floating "
            "storage joins in Spec 11."
        )


def _rig_count_section() -> None:
    long_df = read_ts_long(series_ids=["bh.rigs.united_states.oil"])
    if long_df.empty:
        st.info("No data yet — run `pipelines/baker_hughes/pull_rigs.py`.")
        return

    series = long_df.sort_values("ts").set_index("ts")["value"]

    time_range = st.segmented_control(
        "Time range",
        options=list(RIG_COUNT_RANGE_DAYS),
        default="2Y",
        required=True,
        key="supply_rig_count_range",
    )
    days = RIG_COUNT_RANGE_DAYS[time_range]
    if days is not None:
        cutoff = series.index.max() - pd.Timedelta(days=days)
        series = series[series.index >= cutoff]

    title = "US Oil Rig Count"
    fig = simple_time_series_chart(series, title=title, unit="rigs")
    with card(title):
        st.plotly_chart(fig)
        st.caption(
            "Rig count vs. WTI stays a single series (navy) until Spec 07 (Henry "
            "Hub/WTI) exists — see pipelines/baker_hughes/CLAUDE.md."
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

st.subheader("Oil-on-water")
_oil_on_water_section()

st.subheader("US rig count")
_rig_count_section()
