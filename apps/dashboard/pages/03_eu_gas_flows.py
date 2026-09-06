"""EU Gas Flows — ENTSOG pipeline flows. Sankey + corridor small multiples (Session B),
directional corridor map (Session C), physical-vs-nomination gap chart (Session D) —
per specs/03_entsog-eu-gas-flows.md."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.entsog_map import render_entsog_flow_map
from components.lake import read_flows
from core.theme import LIGHT_BLUE, NAVY, RED, current_vs_prior_year_chart, sankey_chart
from pipelines.entsog.corridors import CORRIDORS
from pipelines.entsog.transforms import (
    corridor_aggregate,
    latest_complete_date,
    pair_daily_totals,
    physical_vs_nomination_gap,
)

SANKEY_WINDOW_DAYS = 7
GAP_RANGE_DAYS = {"3M": 90, "6M": 182, "1Y": 365, "All": None}


def _corridor_filter_panel(corridor_totals: pd.DataFrame) -> list[str]:
    """Collapsible filter panel (accordion + checkboxes + live counts) -- see
    02_gas_storage.py's _country_filter_panel for the same convention."""
    for corridor_name in CORRIDORS:
        st.session_state.setdefault(f"eu_gas_flows_filter_{corridor_name}", True)
    selected_count = sum(
        st.session_state[f"eu_gas_flows_filter_{c}"] for c in CORRIDORS
    )

    with st.expander(f"Filter corridors ({selected_count} of {len(CORRIDORS)} shown)"):
        filter_cols = st.columns(2)
        for i, corridor_name in enumerate(CORRIDORS):
            corridor_df = corridor_totals[corridor_totals["corridor"] == corridor_name]
            latest = (
                corridor_df.sort_values("ts")["value"].iloc[-1] if not corridor_df.empty else None
            )
            label = corridor_name.replace("_", " ")
            checkbox_label = f"{label} — {latest:,.0f} GWh/d" if latest is not None else label
            with filter_cols[i % 2]:
                st.checkbox(checkbox_label, key=f"eu_gas_flows_filter_{corridor_name}")

    return [c for c in CORRIDORS if st.session_state[f"eu_gas_flows_filter_{c}"]]

st.title("EU Gas Flows (ENTSOG)")

flows_df = read_flows(source="entsog")
pipeline_df = flows_df[flows_df["mode"] == "pipeline"]

if pipeline_df.empty:
    st.info("No flow data yet — run `pipelines/entsog/pull_flows.py`.")
else:
    st.subheader("Sankey — latest 7-day average")
    daily_pairs = pair_daily_totals(pipeline_df)
    latest_ts = latest_complete_date(daily_pairs, ["from_node", "to_node"])
    window_start = latest_ts - pd.Timedelta(days=SANKEY_WINDOW_DAYS - 1)
    recent = daily_pairs[(daily_pairs["ts"] >= window_start) & (daily_pairs["ts"] <= latest_ts)]

    link_totals = recent.groupby(["from_node", "to_node"], as_index=False)["value"].mean()
    link_totals = link_totals[link_totals["value"] > 0]

    node_labels = sorted(set(link_totals["from_node"]) | set(link_totals["to_node"]))
    node_index = {label: i for i, label in enumerate(node_labels)}
    sources = link_totals["from_node"].map(node_index).tolist()
    targets = link_totals["to_node"].map(node_index).tolist()
    values = link_totals["value"].tolist()

    sankey_title = f"EU Gas Pipeline Flows — 7-day avg to {latest_ts.date()} (GWh/d)"
    fig = sankey_chart(node_labels, sources, targets, values, title=sankey_title)
    with card(sankey_title):
        st.plotly_chart(fig)

    st.subheader("Corridor map")
    with card("EU Gas Corridor Map"):
        render_entsog_flow_map()

    st.subheader("Corridor time series — current vs. prior year")
    corridor_totals = corridor_aggregate(pipeline_df, CORRIDORS, mode="pipeline")
    selected_corridors = _corridor_filter_panel(corridor_totals)

    if not selected_corridors:
        st.info("No corridors selected — check at least one above.")
    else:
        cols = st.columns(2)
        for i, corridor_name in enumerate(selected_corridors):
            corridor_df = corridor_totals[corridor_totals["corridor"] == corridor_name]
            with cols[i % 2]:
                if corridor_df.empty:
                    st.info(f"No data yet for {corridor_name}.")
                    continue
                corridor_title = corridor_name.replace("_", " ")
                fig = current_vs_prior_year_chart(corridor_df, title=corridor_title, unit="GWh/d")
                with card(corridor_title):
                    st.plotly_chart(fig)

    st.subheader("Physical vs. nomination gap")
    gap_corridor = st.selectbox("Corridor", options=list(CORRIDORS), key="gap_corridor")
    gap_df = physical_vs_nomination_gap(flows_df, CORRIDORS, gap_corridor).sort_values("ts")

    if gap_df.empty:
        st.info(f"No overlapping physical/nomination data yet for {gap_corridor}.")
    else:
        corridor_label = gap_corridor.replace("_", " ")

        gap_range = st.segmented_control(
            "Time range",
            options=list(GAP_RANGE_DAYS),
            default="6M",
            required=True,
            key="eu_gas_flows_gap_range",
        )
        gap_days = GAP_RANGE_DAYS[gap_range]
        if gap_days is not None:
            gap_cutoff = gap_df["ts"].max() - pd.Timedelta(days=gap_days)
            gap_df = gap_df[gap_df["ts"] >= gap_cutoff]

        lines = go.Figure()
        lines.add_trace(
            go.Scatter(
                x=gap_df["ts"],
                y=gap_df["physical"],
                name="Physical flow",
                line={"color": NAVY, "width": 2},
            )
        )
        lines.add_trace(
            go.Scatter(
                x=gap_df["ts"],
                y=gap_df["nomination"],
                name="Nomination",
                line={"color": LIGHT_BLUE, "width": 2},
            )
        )
        lines_title = f"{corridor_label} — Physical vs. Nomination"
        lines.update_layout(title=lines_title, yaxis_title="GWh/d")
        with card(lines_title):
            st.plotly_chart(lines)

        # A line, not a bar: with ~2 years of daily points, go.Bar's per-bar width
        # auto-calculation produces invalid negative widths in the browser (confirmed
        # live via console errors) — every other daily time series in this app already
        # uses a line for the same reason.
        gap_line = go.Figure(
            go.Scatter(
                x=gap_df["ts"],
                y=gap_df["gap"],
                line={"color": RED, "width": 1.5},
                fill="tozeroy",
                fillcolor="rgba(192,57,43,0.2)",
            )
        )
        gap_line.add_hline(y=0, line_color=NAVY, line_width=1)
        gap_title = f"{corridor_label} — Nomination minus Physical (under-delivery when positive)"
        gap_line.update_layout(title=gap_title, yaxis_title="GWh/d")
        with card(gap_title):
            st.plotly_chart(gap_line)
