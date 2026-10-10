"""Plotly figures for the exhibit specs -- the Python twin of `static/charts.js`.

The published pages draw each exhibit dict in the browser; this draws the same dict as a
`plotly.graph_objects.Figure` so the Streamlit app (or a notebook) shows the identical
chart. Colours come from `core.design` and the "kardamow" template from `core.theme`
(golden rule 5). No figure paints its own title: the caller's section heading owns it.
"""

from __future__ import annotations

import html
from typing import Any, Final

import core.theme  # noqa: F401  -- registers the "kardamow" template
import plotly.graph_objects as go
from core.design import BAND, GREY, GRID, LIGHT_BLUE, MUTED, NAVY, ORANGE, PAPER, TEXT

Exhibit = dict[str, Any]

HEIGHT: Final = 340
_LABEL_GROUND: Final = "rgba(255,255,255,0.9)"


def _esc(text: Any) -> str:
    """Plotly renders a subset of HTML in every string it draws; lake text is escaped."""
    return html.escape(str(text), quote=False)


def _fmt(digits: int) -> str:
    return f",.{digits}f"


def _axis_title(text: str, colour: str = MUTED) -> dict[str, Any]:
    return {"text": _esc(text), "font": {"size": 11.5, "color": colour}, "standoff": 6}


def _notes(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i, point in enumerate(points):
        latest = bool(point.get("latest"))
        low = str(point["text"]).startswith("Low")
        out.append(
            {
                "x": point["x"],
                "y": point["y"],
                "xref": "x",
                "yref": point.get("axis") or "y",
                "text": _esc(point["text"]),
                "showarrow": True,
                "arrowhead": 0,
                "arrowwidth": 1,
                "arrowcolor": NAVY if latest else MUTED,
                "ax": -70 if latest else (30 if i % 2 else -30),
                "ay": -34 if latest else (30 if low else -30),
                "font": {"size": 11, "color": NAVY if latest else TEXT},
                "bgcolor": _LABEL_GROUND,
                "borderpad": 2,
            }
        )
    return out


def _figure(data: list[Any], **layout: Any) -> go.Figure:
    fig = go.Figure(data=data)
    fig.update_layout(
        height=HEIGHT,
        margin={"l": 56, "r": 24, "t": 34, "b": 36},
        hovermode="x unified",
        hoverlabel={"bgcolor": PAPER, "bordercolor": GRID, "font": {"size": 12, "color": TEXT}},
        legend={"font": {"size": 11.5}},
    )
    fig.update_xaxes(linecolor=GRID, tickcolor=GRID)
    fig.update_yaxes(linecolor=GRID, automargin=True)
    fig.update_layout(**layout)
    return fig


def _seasonal(e: Exhibit) -> go.Figure:
    hover = f"%{{y:{_fmt(e['digits'])}}}"
    x = e["x"]
    data = [
        go.Scatter(
            x=x,
            y=e["band_min"],
            mode="lines",
            line={"width": 0},
            hoverinfo="skip",
            showlegend=False,
        ),
        go.Scatter(
            x=x,
            y=e["band_max"],
            mode="lines",
            line={"width": 0},
            fill="tonexty",
            fillcolor=BAND,
            name=_esc(e["band_label"]),
            hoverinfo="skip",
        ),
        go.Scatter(
            x=x,
            y=e["median"],
            mode="lines",
            name="Median",
            line={"color": ORANGE, "width": 1.5, "dash": "dot"},
            hovertemplate=hover,
        ),
        go.Scatter(
            x=x,
            y=e["prior"],
            mode="lines",
            name=str(e["year"] - 1),
            line={"color": LIGHT_BLUE, "width": 1.5},
            hovertemplate=hover,
        ),
        # Current year last, so it sits on top of everything it is measured against.
        go.Scatter(
            x=x,
            y=e["current"],
            mode="lines",
            name=str(e["year"]),
            line={"color": NAVY, "width": 2.5},
            hovertemplate=hover,
        ),
    ]
    # Weekly series arrive with a value only on report days; the line joins them.
    for trace in data:
        trace.connectgaps = True
    return _figure(
        data,
        xaxis={
            "type": "date",
            "tickformat": "%b",
            "dtick": "M1",
            "hoverformat": "%-d %b",
            "range": [x[0], x[-1]],
        },
        yaxis={"title": _axis_title(e["unit"]), "tickformat": _fmt(1 if e["digits"] > 1 else 0)},
        annotations=_notes(e["annotations"]),
    )


def _trace(s: dict[str, Any], colour: str, axis: str, width: float) -> go.Scatter:
    return go.Scatter(
        x=s["x"],
        y=s["y"],
        mode="lines+markers" if len(s["x"]) < 16 else "lines",
        name=_esc(s["name"]),
        yaxis=axis,
        line={"color": colour, "width": width},
        marker={"size": 6, "color": colour},
        hovertemplate=f"%{{y:{_fmt(s['digits'])}}} {_esc(s['unit'])}",
    )


def _dual(e: Exhibit) -> go.Figure:
    first = e["series"][0]
    data = [_trace(first, NAVY, "y", 2.2)]
    layout: dict[str, Any] = {
        "yaxis": {
            "title": _axis_title(f"{first['name']}, {first['unit']}", NAVY),
            "tickfont": {"color": NAVY},
        },
        "annotations": _notes(e["annotations"]),
        "margin": {"l": 56, "r": 56, "t": 34, "b": 36},
    }
    if len(e["series"]) > 1:
        second = e["series"][1]
        data.append(_trace(second, LIGHT_BLUE, "y2", 1.8))
        layout["yaxis2"] = {
            "title": _axis_title(f"{second['name']}, {second['unit']}", LIGHT_BLUE),
            "tickfont": {"color": LIGHT_BLUE},
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "zeroline": False,
            "automargin": True,
        }
    return _figure(data, **layout)


def _lines(e: Exhibit) -> go.Figure:
    colours = [NAVY, LIGHT_BLUE, GREY]
    data = [_trace(s, colours[i % 3], "y", 1.8 if i else 2.2) for i, s in enumerate(e["series"])]
    xaxis = {"title": _axis_title(e["x_title"])} if e.get("x_title") else {}
    return _figure(
        data,
        xaxis=xaxis,
        yaxis={
            "title": _axis_title(e["series"][0]["unit"]),
            "zeroline": True,
            "zerolinecolor": GRID,
        },
        showlegend=len(e["series"]) > 1,
        annotations=_notes(e["annotations"]),
    )


def _bars(e: Exhibit) -> go.Figure:
    # Plotly fills a horizontal bar chart from the bottom, so the ranking is reversed.
    cats = [_esc(c) for c in reversed(e["categories"])]
    hover = f"%{{x:{_fmt(e['digits'])}}} {_esc(e['unit'])}"
    data = [
        go.Bar(
            orientation="h",
            y=cats,
            x=e["compare"][::-1],
            name=_esc(e["compare_name"]),
            marker={"color": LIGHT_BLUE},
            hovertemplate=hover,
        ),
        go.Bar(
            orientation="h",
            y=cats,
            x=e["values"][::-1],
            name=_esc(e["value_name"]),
            marker={"color": NAVY},
            hovertemplate=hover,
        ),
    ]
    return _figure(
        data,
        height=max(320, 30 * len(cats) + 90),
        barmode="group",
        bargap=0.28,
        bargroupgap=0.08,
        hovermode="y unified",
        xaxis={"title": _axis_title(e["unit"]), "zeroline": True, "zerolinecolor": GRID},
        yaxis={"tickfont": {"size": 11.5}},
        legend={"traceorder": "reversed", "font": {"size": 11.5}},
        margin={"l": 56, "r": 24, "t": 34, "b": 44},
    )


_BUILDERS: Final = {"seasonal": _seasonal, "dual": _dual, "lines": _lines, "bars": _bars}


def figure(exhibit: Exhibit) -> go.Figure:
    """The chart for one exhibit dict from `exhibits.build`."""
    return _BUILDERS[exhibit["kind"]](exhibit)
