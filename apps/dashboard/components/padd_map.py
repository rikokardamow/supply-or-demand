"""PADD inter-region crude flow map — directional lines sized by monthly volume,
coloured by transport mode, with a month slider and mode filter.

Note: Plotly annotations only support geo-referenced *anchor* coordinates (xref/yref =
"geo"), not geo-referenced *arrow-tail* coordinates (axref/ayref only accept "pixel" or
a cartesian x/y-axis ref) — confirmed against the installed plotly version, so a
straightforward geo-to-geo annotation arrow isn't possible. Direction is shown instead
via a small rotated triangle marker placed most of the way along each corridor line."""

from __future__ import annotations

import math

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.storage import read_flows
from core.theme import LIGHT_BLUE, NAVY, RED

PADD_CENTROIDS: dict[str, tuple[float, float]] = {
    # Approximate regional centroids for visualisation only, not precise geographic centres.
    "PADD1": (40.0, -77.0),
    "PADD2": (41.5, -93.5),
    "PADD3": (29.5, -95.0),
    "PADD4": (43.5, -108.0),
    "PADD5": (37.0, -119.5),
}

MODE_COLOURS = {
    "pipeline": NAVY,
    "tanker_barge": LIGHT_BLUE,
    "rail": RED,
}

_ARROWHEAD_FRACTION = 0.85  # how far along the line the direction marker sits


def _bearing_degrees(orig_lat: float, orig_lon: float, dest_lat: float, dest_lon: float) -> float:
    # Flat-plane approximation (fine at US-domestic scale) matching Plotly's marker
    # angle convention: 0 = pointing up/north, increasing clockwise.
    dx = dest_lon - orig_lon
    dy = dest_lat - orig_lat
    return math.degrees(math.atan2(dx, dy))


def render_padd_flow_map() -> None:
    df = read_flows(source="eia")
    if df.empty:
        st.info("No flow data yet — run `pipelines/eia/pull_padd_flows.py`.")
        return

    months = sorted(df["ts"].unique())
    month_labels = {pd.Timestamp(m).strftime("%Y-%m"): m for m in months}
    selected_label = st.select_slider(
        "Month", options=list(month_labels), value=list(month_labels)[-1]
    )
    selected_month = month_labels[selected_label]

    selected_modes = st.multiselect("Mode", options=list(MODE_COLOURS), default=list(MODE_COLOURS))

    month_df = df[(df["ts"] == selected_month) & (df["mode"].isin(selected_modes))]

    fig = go.Figure()
    fig.update_geos(scope="usa")

    fig.add_trace(
        go.Scattergeo(
            lat=[lat for lat, _ in PADD_CENTROIDS.values()],
            lon=[lon for _, lon in PADD_CENTROIDS.values()],
            text=list(PADD_CENTROIDS),
            mode="markers+text",
            textposition="top center",
            marker={"size": 10, "color": NAVY},
            showlegend=False,
        )
    )

    max_value = month_df["value"].max() if not month_df.empty else 1.0
    for _, row in month_df.iterrows():
        orig_lat, orig_lon = PADD_CENTROIDS[row["from_node"]]
        dest_lat, dest_lon = PADD_CENTROIDS[row["to_node"]]
        colour = MODE_COLOURS.get(row["mode"], NAVY)
        width = 1 + 5 * (row["value"] / max_value) if max_value else 1

        fig.add_trace(
            go.Scattergeo(
                lat=[orig_lat, dest_lat],
                lon=[orig_lon, dest_lon],
                mode="lines",
                line={"width": width, "color": colour},
                opacity=0.7,
                showlegend=False,
                hoverinfo="skip",
            )
        )

        arrow_lat = orig_lat + _ARROWHEAD_FRACTION * (dest_lat - orig_lat)
        arrow_lon = orig_lon + _ARROWHEAD_FRACTION * (dest_lon - orig_lon)
        bearing = _bearing_degrees(orig_lat, orig_lon, dest_lat, dest_lon)
        fig.add_trace(
            go.Scattergeo(
                lat=[arrow_lat],
                lon=[arrow_lon],
                mode="markers",
                marker={"symbol": "triangle-up", "angle": bearing, "size": 10, "color": colour},
                showlegend=False,
                hovertext=(
                    f"{row['from_node']} → {row['to_node']} ({row['mode']}): "
                    f"{row['value']:,.0f} {row['unit']}"
                ),
                hoverinfo="text",
            )
        )

    fig.update_layout(title=f"Inter-PADD Crude Movements — {selected_label}")
    st.plotly_chart(fig, use_container_width=True)
