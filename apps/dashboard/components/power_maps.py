"""ENTSO-E power maps — price choropleth-style map and cross-border flow arrow map.
Same Scattermapbox + line/dot technique as padd_map.py/entsog_map.py — real
open-street-map tiles, no token needed, per the dashboard's institutional-look
redesign (root NOTES.md's chart house style). Direction markers are plain circles,
not rotated arrows -- see padd_map.py's comment on why."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.storage import read_flows, read_ts_long
from core.theme import NAVY, RED
from pipelines.entsoe.zones import ZONES

_ARROWHEAD_FRACTION = 0.85

# Real-world representative coordinates per zone — approximate, for visualisation only,
# same caveat as padd_map.py's PADD_CENTROIDS (not precise electrical hub locations).
ZONE_COORDS: dict[str, tuple[float, float]] = {
    "DE_LU": (50.11, 8.68),  # Frankfurt area (central for DE + LU)
    "FR": (48.85, 2.35),  # Paris
    "NL": (52.37, 4.90),  # Amsterdam
    "BE": (50.85, 4.35),  # Brussels
    "AT": (48.21, 16.37),  # Vienna
    "ES": (40.42, -3.70),  # Madrid
    "IT_NORD": (45.46, 9.19),  # Milan
    "PL": (52.23, 21.01),  # Warsaw
    "NO_2": (58.15, 8.00),  # Kristiansand (southern Norway, NO2's own area)
    "SE_4": (55.60, 13.00),  # Malmö (southernmost Sweden, SE4's own area)
    "DK_1": (56.15, 10.20),  # Aarhus (western Denmark, DK1's own area)
    "IE_SEM": (53.35, -6.26),  # Dublin
    "GB": (51.51, -0.13),  # London
}


def render_price_map() -> None:
    price_series_ids = [f"entsoe.{zone}.day_ahead_price" for zone in ZONES]
    prices = read_ts_long(series_ids=price_series_ids)
    if prices.empty:
        st.info("No price data yet — run `pipelines/entsoe/pull_prices.py`.")
        return

    latest = prices.sort_values("ts").groupby("geo").tail(1)
    lats, lons, texts, values = [], [], [], []
    for _, row in latest.iterrows():
        coord = ZONE_COORDS.get(row["geo"])
        if coord is None:
            continue
        lats.append(coord[0])
        lons.append(coord[1])
        values.append(row["value"])
        texts.append(f"{row['geo']}: {row['value']:,.1f} EUR/MWh")

    if not values:
        st.info("No mapped zones with price data yet.")
        return

    fig = go.Figure(
        go.Scattermapbox(
            lat=lats,
            lon=lons,
            text=[f"{v:,.0f}" for v in values],
            hovertext=texts,
            hoverinfo="text",
            mode="markers+text",
            textposition="top center",
            marker={
                "size": 22,
                "color": values,
                "colorscale": [[0, NAVY], [0.5, "#f5f5f5"], [1, RED]],
                "cmid": sum(values) / len(values),
                "colorbar": {"title": "EUR/MWh"},
                # No marker.line (outline) here -- unlike Scattergeo.Marker,
                # Scattermapbox.Marker doesn't support one at all (confirmed live:
                # a real ValueError, not silently dropped).
            },
            showlegend=False,
        )
    )
    fig.update_layout(
        mapbox={"style": "open-street-map", "center": {"lat": 50, "lon": 10}, "zoom": 3.3}
    )
    latest_ts = latest["ts"].max()
    fig.update_layout(title=f"Day-Ahead Price by Zone — {pd.Timestamp(latest_ts)}")
    st.plotly_chart(fig, use_container_width=True)


def render_flow_map() -> None:
    flows_df = read_flows(source="entsoe")
    power_df = flows_df[flows_df["mode"] == "power"]
    if power_df.empty:
        st.info("No flow data yet — run `pipelines/entsoe/pull_flows.py`.")
        return

    latest_ts = power_df["ts"].max()
    window_start = latest_ts - pd.Timedelta(hours=24)
    recent = power_df[power_df["ts"] >= window_start]
    link_totals = recent.groupby(["from_node", "to_node"], as_index=False)["value"].mean()
    link_totals = link_totals[link_totals["value"].abs() > 0]

    fig = go.Figure()
    fig.update_layout(
        mapbox={"style": "open-street-map", "center": {"lat": 50, "lon": 10}, "zoom": 3.3}
    )

    max_value = link_totals["value"].abs().max() if not link_totals.empty else 1.0
    for _, row in link_totals.iterrows():
        origin = ZONE_COORDS.get(row["from_node"])
        dest = ZONE_COORDS.get(row["to_node"])
        if origin is None or dest is None:
            continue
        orig_lat, orig_lon = origin
        dest_lat, dest_lon = dest
        width = 1 + 5 * (abs(row["value"]) / max_value) if max_value else 1

        fig.add_trace(
            go.Scattermapbox(
                lat=[orig_lat, dest_lat],
                lon=[orig_lon, dest_lon],
                mode="lines",
                line={"width": width, "color": NAVY},
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
                # A plain circle, not a rotated arrow -- see padd_map.py's comment:
                # the free raster styles ship no icon sprite, so marker.symbol
                # silently fails to render regardless of name.
                marker={"size": 10, "color": NAVY},
                showlegend=False,
                hovertext=(
                    f"{row['from_node']} → {row['to_node']}: {row['value']:,.0f} MW"
                ),
                hoverinfo="text",
            )
        )

    fig.update_layout(title=f"Cross-Border Power Flows — 24h avg to {latest_ts}")
    st.plotly_chart(fig, use_container_width=True)
