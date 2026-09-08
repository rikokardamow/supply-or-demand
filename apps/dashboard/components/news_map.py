"""Clickable world map for the news page redesign (Spec 09 amendment) -- one marker
per resolved country, sized by event count and coloured by that country's own max
severity.

Uses `go.Scattermap` (the newer MapLibre-based trace), NOT `go.Scattermapbox` like
this project's other maps (padd_map.py, entsog_map.py, power_maps.py) -- a deliberate,
confirmed-live deviation from that precedent. `go.Scattermapbox` markers never
produced a Streamlit `on_select` selection event no matter where a real click landed
(confirmed live: repeated clicks squarely on a rendered marker, verified against
screenshots, produced zero selection points) -- this matches a known, real gap
(third-party components like `streamlit-plotly-mapbox-events` exist specifically
because native `st.plotly_chart` selection support for Scattermapbox is unreliable).
Switching this one component to `go.Scattermap` (`layout.map` instead of
`layout.mapbox`; same free "open-street-map" style, no Mapbox token) fixed it --
confirmed live, click selection works correctly. Plotly itself already recommends
this migration (a console warning on every Scattermapbox render: "mapbox subplots and
traces are deprecated ... switching to `map` subplots and traces").

Returns a bare go.Figure -- the caller (09_events.py) renders it via
`st.plotly_chart(fig, on_select="rerun", selection_mode="points", key=...)` and reads
the click back out of the returned selection event; this module has no Streamlit
dependency of its own, matching the "components are pure figure builders" pattern
already used elsewhere in apps/dashboard/components."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from core.theme import NAVY

from components.event_overlay import SEVERITY_COLOURS
from components.geo_centroids import centroid_for

_MIN_MARKER_SIZE = 10
_MAX_MARKER_SIZE = 40


def _marker_size(count: int, max_count: int) -> float:
    if max_count <= 0:
        return _MIN_MARKER_SIZE
    return _MIN_MARKER_SIZE + (_MAX_MARKER_SIZE - _MIN_MARKER_SIZE) * (count / max_count)


def render_news_map(events_df: pd.DataFrame) -> go.Figure:
    """`events_df` is whatever `core.storage.read_events()` (optionally pre-filtered by
    the caller) returns. A `geo` value that doesn't resolve to a centroid (empty, or an
    as-yet-unmapped country) is excluded from the markers -- it stays reachable via the
    page's own "no location" catch-all in the text feed, per the approved plan; it is
    not silently dropped from the underlying data, only from this map's markers."""
    fig = go.Figure()
    fig.update_layout(
        map={"style": "open-street-map", "center": {"lat": 20, "lon": 10}, "zoom": 0.8},
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
    )

    if events_df.empty:
        return fig

    grouped = events_df.groupby("geo").agg(
        count=("event_id", "size"), max_severity=("severity", "max")
    )
    grouped = grouped.reset_index()
    grouped["centroid"] = grouped["geo"].map(centroid_for)
    grouped = grouped[grouped["centroid"].notna()]

    if grouped.empty:
        return fig

    max_count = int(grouped["count"].max())

    fig.add_trace(
        go.Scattermap(
            lat=[c[0] for c in grouped["centroid"]],
            lon=[c[1] for c in grouped["centroid"]],
            mode="markers",
            marker={
                "size": [_marker_size(int(c), max_count) for c in grouped["count"]],
                "color": [SEVERITY_COLOURS.get(int(s), NAVY) for s in grouped["max_severity"]],
            },
            # Each point's own customdata must itself be a list -- a bare flat array
            # of strings gets indexed like a list of characters by the click-event
            # JSON round-trip (confirmed live: "United States" came back as "U"),
            # matching Plotly Express's own convention of one customdata list per
            # point (see streamlit's plotly_chart docstring example: "customdata":
            # [2.5], not a bare 2.5).
            customdata=[[geo] for geo in grouped["geo"]],
            hovertext=[
                f"{geo}: {count} event(s), max severity {severity}"
                for geo, count, severity in zip(
                    grouped["geo"], grouped["count"], grouped["max_severity"], strict=True
                )
            ],
            hoverinfo="text",
        )
    )

    return fig
