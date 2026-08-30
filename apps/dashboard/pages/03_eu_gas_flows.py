"""EU Gas Flows — ENTSOG pipeline flows. Sankey + corridor small multiples per Session B
of specs/03_entsog-eu-gas-flows.md; the directional corridor map (Session C) and the
physical-vs-nomination gap chart (Session D) come later."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from core.storage import read_flows
from core.theme import current_vs_prior_year_chart, sankey_chart
from pipelines.entsog.corridors import CORRIDORS
from pipelines.entsog.transforms import corridor_aggregate, latest_complete_date, pair_daily_totals

SANKEY_WINDOW_DAYS = 7

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

    fig = sankey_chart(
        node_labels,
        sources,
        targets,
        values,
        title=f"EU Gas Pipeline Flows — 7-day avg to {latest_ts.date()} (GWh/d)",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Corridor time series — current vs. prior year")
    corridor_totals = corridor_aggregate(pipeline_df, CORRIDORS, mode="pipeline")

    cols = st.columns(2)
    for i, corridor_name in enumerate(CORRIDORS):
        corridor_df = corridor_totals[corridor_totals["corridor"] == corridor_name]
        with cols[i % 2]:
            if corridor_df.empty:
                st.info(f"No data yet for {corridor_name}.")
                continue
            fig = current_vs_prior_year_chart(
                corridor_df, title=corridor_name.replace("_", " "), unit="GWh/d"
            )
            st.plotly_chart(fig, use_container_width=True)
