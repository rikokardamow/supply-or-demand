"""PADD inter-region crude flow map — directional lines sized by monthly volume,
coloured by transport mode, with a month slider and mode filter.

Uses go.Scattermapbox with the free, no-token "open-street-map" style for real street
tiles (moved off go.Scattergeo's flat continent-outline projection as part of the
dashboard's institutional-look redesign — see root NOTES.md's chart house style).

Note: Plotly annotations only support geo-referenced *anchor* coordinates (xref/yref =
"geo"), not geo-referenced *arrow-tail* coordinates (axref/ayref only accept "pixel" or
a cartesian x/y-axis ref) — confirmed against the installed plotly version, so a
straightforward geo-to-geo annotation arrow isn't possible. Direction is shown instead
via a small rotated triangle marker placed most of the way along each corridor line."""

from __future__ import annotations

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
    fig.update_layout(
        mapbox={"style": "open-street-map", "center": {"lat": 39, "lon": -98}, "zoom": 3}
    )

    fig.add_trace(
        go.Scattermapbox(
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
            go.Scattermapbox(
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
        fig.add_trace(
            go.Scattermapbox(
                lat=[arrow_lat],
                lon=[arrow_lon],
                mode="markers",
                # A plain circle, not a rotated arrow -- confirmed live that
                # Scattermapbox's free raster styles ("open-street-map",
                # "carto-positron") ship no icon sprite at all, so ANY marker.symbol
                # silently fails to render ("Image ... could not be loaded" in the
                # console) regardless of name. Direction is still conveyed by this
                # dot's position near the destination end of its line.
                marker={"size": 10, "color": colour},
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
