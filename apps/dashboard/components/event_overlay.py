"""Reusable event-marker overlay (Spec 09 Session C): draws a severity-coloured
vertical line per matching event onto an existing Plotly figure, with the headline as
hover text. Reads `core.storage.read_events` directly, matching the page-reads-the-
lake convention every other component already follows.

Supports two x-axis conventions already in use across this dashboard's charts:
- `x_axis="date"` (default) -- a real calendar-timestamp x-axis
  (`core.theme.dual_axis_chart`/`time_series_area_chart`/etc.).
- `x_axis="doy"` -- a day-of-year x-axis (`core.theme.seasonal_range_chart` and every
  other `core.seasonal`-based chart), matching `core.seasonal.REFERENCE_YEAR`'s own
  non-leap-year alignment convention (ad-hoc-replicated the same way
  `apps/dashboard/pages/08_weather.py` already does inline, rather than importing
  `core.seasonal`'s private `_normalised_doy`)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from core.seasonal import REFERENCE_YEAR
from core.theme import GREY, ORANGE, RED

from components.lake import read_events

SEVERITY_COLOURS = {1: GREY, 2: ORANGE, 3: RED}

# Confirmed live: calling fig.add_vline() once per event hangs the page well before
# even 1,000 events (960 real crude-commodity rows in the lake as of writing) -- each
# call does non-trivial internal validation, so a per-event loop is O(n) Plotly-side
# work, not just O(n) Python-side. Building shape dicts and setting them via a single
# fig.update_layout(shapes=[...]) call is the documented efficient pattern.
MAX_MARKERS = 50

# A dedicated, hidden third axis (0-1, "paper"-like range) for the hover-marker trace
# -- keeps marker placement independent of whatever y-scale the underlying chart
# itself uses, and avoids colliding with charts that already use a real y2 (e.g.
# dual_axis_chart).
_MARKER_YAXIS = "y3"


def _doy(ts: pd.Timestamp) -> int | None:
    try:
        return int(ts.replace(year=REFERENCE_YEAR).dayofyear)
    except ValueError:
        return None  # Feb 29 events have no day-of-year in a non-leap reference year


def add_event_markers(
    fig: go.Figure,
    commodity: str,
    geo: str | None = None,
    x_axis: str = "date",
    min_severity: int = 2,
) -> go.Figure:
    """Mutates and returns `fig`. A no-op (returns `fig` unchanged) if there are no
    matching events, so callers can always call this unconditionally rather than
    checking emptiness themselves first.

    `min_severity` defaults to 2 (outage/strike-tier and up), not 1 -- tier-1 "general"
    headlines are the large majority of ingested events (confirmed live: 1423 of 1462
    total, vs. 39 at tier 2/3) and would bury a chart in low-signal noise as much as
    they'd bury it in unusable render time. `MAX_MARKERS` is a second, hard safety cap
    (keeping only the most recent events) independent of severity, since even a
    tier-2+-only set could still grow large over time."""
    events = read_events(commodity=commodity)
    if geo is not None:
        events = events[events["geo"] == geo]
    events = events[events["severity"] >= min_severity]
    if events.empty:
        return fig

    events = events.sort_values("ts").tail(MAX_MARKERS)

    if x_axis == "doy":
        x_values: list[object] = []
        headlines: list[str] = []
        severities: list[int] = []
        for _, row in events.iterrows():
            doy = _doy(pd.Timestamp(row["ts"]))
            if doy is None:
                continue
            x_values.append(doy)
            headlines.append(str(row["headline"]))
            severities.append(int(row["severity"]))
    else:
        x_values = list(events["ts"])
        headlines = [str(h) for h in events["headline"]]
        severities = [int(s) for s in events["severity"]]

    if not x_values:
        return fig

    colours = [SEVERITY_COLOURS.get(s, GREY) for s in severities]

    shapes: list[dict[str, Any]] = [
        {
            "type": "line",
            "x0": x,
            "x1": x,
            "y0": 0,
            "y1": 1,
            "xref": "x",
            "yref": "paper",
            "opacity": 0.5,
            "line": {"color": colour, "width": 1, "dash": "dot"},
        }
        for x, colour in zip(x_values, colours, strict=True)
    ]

    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=[1] * len(x_values),
            yaxis=_MARKER_YAXIS,
            mode="markers",
            marker={"color": colours, "size": 8, "symbol": "triangle-down"},
            hovertext=headlines,
            hoverinfo="text",
            showlegend=False,
            name="Events",
        )
    )
    fig.update_layout(
        shapes=list(fig.layout.shapes) + shapes,
        **{
            _MARKER_YAXIS.replace("y", "yaxis"): {
                "overlaying": "y",
                "range": [0, 1],
                "visible": False,
                "side": "right",
            }
        },
    )
    return fig
