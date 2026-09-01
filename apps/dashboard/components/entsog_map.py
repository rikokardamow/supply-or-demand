"""ENTSOG directional corridor map — Europe Scattermapbox (real open-street-map tiles,
no token needed, per the dashboard's institutional-look redesign), dots sized by the
latest complete 7-day average flow (same window logic as page 03's Sankey, via
pipelines.entsog.transforms). Styled after padd_map.py's convention: navy for
pipeline corridors, light blue for LNG (ship-borne, matching padd_map's
tanker_barge=light-blue colour semantics — "how did this gas travel"). Direction
markers are plain circles, not rotated arrows -- padd_map.py's comment explains why
(the free raster basemap styles ship no icon sprite).

The `flows` table stores no per-point identifier (see pipelines/entsog/NOTES.md), only
(from_node, to_node) pairs — same granularity the Sankey operates at — so this map draws
one arrow per pair, not per individual physical point. Where several real points share a
pair (e.g. NO_EXPORTS has 3 Germany-bound points), one representative site's coordinate
anchors that pair's marker; this is a visualisation simplification, not a data change."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.storage import read_flows
from core.theme import LIGHT_BLUE, NAVY
from pipelines.entsog.transforms import latest_complete_date, pair_daily_totals

_ARROWHEAD_FRACTION = 0.85
_WINDOW_DAYS = 7

# Real-world coordinates for the receiving-side entry point representing each
# (from_node, to_node) pair — approximate, for visualisation only, not precise site
# locations. Where a pair has multiple real points (NO->DE, NO->GB, LNG->FR), one
# representative site is picked; see the corridor table in pipelines/entsog/NOTES.md
# for every point actually pulled.
PAIR_DEST_COORDS: dict[tuple[str, str], tuple[float, float]] = {
    ("NO", "DE"): (53.37, 7.21),  # Emden EPT1 (also covers Dornum)
    ("NO", "BE"): (51.33, 3.20),  # Zeebrugge ZPT
    ("NO", "FR"): (51.05, 2.38),  # Dunkerque DKB
    ("NO", "GB"): (53.79, 0.10),  # Easington (also covers St Fergus)
    ("TAP", "IT"): (40.27, 18.35),  # Melendugno
    ("TURKSTREAM", "BG"): (41.95, 27.53),  # Strandzha 2 / Malkoclar
    ("FR", "ES"): (43.35, -1.75),  # VIP Pirineos
    ("BE", "GB"): (52.87, 1.45),  # Bacton (IUK)
    ("GB", "IE"): (55.33, -3.45),  # Moffat
    ("RU", "UA"): (51.20, 35.28),  # Sudzha
    ("LNG", "NL"): (51.95, 4.03),  # Gate Terminal
    ("LNG", "BE"): (51.33, 3.20),  # Zeebrugge LNG
    ("LNG", "FR"): (47.31, -2.15),  # Montoir de Bretagne (also covers Fos)
    ("LNG", "ES"): (41.35, 2.15),  # Barcelona
    ("LNG", "PL"): (53.92, 14.27),  # Świnoujście
    ("LNG", "IT"): (43.53, 10.28),  # OLT LNG / Livorno
    ("LNG", "PT"): (37.95, -8.87),  # Sines
}

# Representative upstream origin for a from_node that names a pipeline/exporter rather
# than a single real country (see corridors.py) — approximate, for visualisation only.
# LNG has no single origin (ship-borne from many countries) and isn't drawn as a line.
ORIGIN_COORDS: dict[str, tuple[float, float]] = {
    "NO": (59.3, 5.35),  # Norwegian west-coast gas hubs (Kårstø/Kollsnes area)
    "TAP": (40.5, 20.0),  # Greek/Albanian route into Melendugno
    "TURKSTREAM": (44.9, 37.3),  # Russian Black Sea coast (Anapa area)
    "RU": (51.5, 36.5),  # just inside Russia from Sudzha
}


def render_entsog_flow_map() -> None:
    flows_df = read_flows(source="entsog")
    pipeline_df = flows_df[flows_df["mode"] == "pipeline"]
    if pipeline_df.empty:
        st.info("No flow data yet — run `pipelines/entsog/pull_flows.py`.")
        return

    daily_pairs = pair_daily_totals(pipeline_df)
    latest_ts = latest_complete_date(daily_pairs, ["from_node", "to_node"])
    window_start = latest_ts - pd.Timedelta(days=_WINDOW_DAYS - 1)
    recent = daily_pairs[(daily_pairs["ts"] >= window_start) & (daily_pairs["ts"] <= latest_ts)]
    link_totals = recent.groupby(["from_node", "to_node"], as_index=False)["value"].mean()
    link_totals = link_totals[link_totals["value"] > 0]

    fig = go.Figure()
    fig.update_layout(
        mapbox={"style": "open-street-map", "center": {"lat": 50, "lon": 10}, "zoom": 3.3}
    )

    max_value = link_totals["value"].max() if not link_totals.empty else 1.0
    for _, row in link_totals.iterrows():
        pair = (row["from_node"], row["to_node"])
        dest = PAIR_DEST_COORDS.get(pair)
        if dest is None:
            continue
        dest_lat, dest_lon = dest
        colour = LIGHT_BLUE if row["from_node"] == "LNG" else NAVY
        width = 1 + 5 * (row["value"] / max_value) if max_value else 1

        origin = ORIGIN_COORDS.get(row["from_node"])
        if origin is not None:
            orig_lat, orig_lon = origin
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
                    # A plain circle, not a rotated arrow -- see padd_map.py's
                    # comment: the free raster styles ship no icon sprite, so
                    # marker.symbol silently fails to render regardless of name.
                    marker={"size": 10, "color": colour},
                    showlegend=False,
                    hovertext=(
                        f"{row['from_node']} → {row['to_node']}: "
                        f"{row['value']:,.0f} GWh/d"
                    ),
                    hoverinfo="text",
                )
            )
        else:
            # LNG: no single upstream origin — a sized marker at the terminal itself.
            fig.add_trace(
                go.Scattermapbox(
                    lat=[dest_lat],
                    lon=[dest_lon],
                    mode="markers",
                    marker={"size": 8 + 12 * (row["value"] / max_value), "color": colour},
                    showlegend=False,
                    hovertext=f"LNG → {row['to_node']}: {row['value']:,.0f} GWh/d",
                    hoverinfo="text",
                )
            )

    fig.update_layout(title=f"EU Gas Corridor Map — 7-day avg to {latest_ts.date()}")
    st.plotly_chart(fig, use_container_width=True)
