"""Turn a ``views.sd.PageView`` into Dash components in the house style.

The Streamlit counterpart is ``apps/dashboard/views/render_streamlit.py``; both draw the same
view, so the two apps cannot drift apart in content.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from core.design import BODY_STACK, HEADING_STACK, MUTED, PAPER, RULE, TEXT
from dash import dash_table, dcc, html
from views.sd import Item, PageView, Section

# dash_table ships without type information for its components.
DataTable: Any = dash_table.DataTable  # type: ignore[attr-defined]

META: dict[str, Any] = {
    "fontSize": "0.72rem",
    "letterSpacing": "0.08em",
    "textTransform": "uppercase",
    "color": MUTED,
}
HAIRLINE: dict[str, Any] = {"border": "0", "borderTop": f"1px solid {RULE}"}


def _kpis(items: list[tuple[str, str, str | None]]) -> html.Div:
    cards = [
        html.Div(
            [
                html.Div(label, style={**META, "marginBottom": "0.3rem"}),
                html.Div(value, style={"fontSize": "1.6rem", "fontWeight": 600, "color": TEXT}),
                html.Div(delta or "", style={"fontSize": "0.8rem", "color": MUTED}),
            ],
            style={"flex": "1", "padding": "0.6rem 0.8rem", "border": f"1px solid {RULE}"},
        )
        for label, value, delta in items
    ]
    return html.Div(cards, style={"display": "flex", "gap": "0.8rem", "margin": "0.6rem 0"})


def _table(frame: pd.DataFrame) -> Any:
    data = frame.copy()
    data.index = [str(i) for i in data.index]
    data = data.reset_index().rename(columns={"index": ""})
    data.columns = [str(c) for c in data.columns]
    return DataTable(
        data=data.astype(object).where(data.notna(), None).to_dict("records"),
        columns=[{"name": c, "id": c, "type": "numeric" if c else "text"} for c in data.columns],
        sort_action="native",
        style_table={"overflowX": "auto"},
        style_cell={
            "fontFamily": BODY_STACK,
            "fontSize": "0.85rem",
            "padding": "4px 8px",
            "border": f"1px solid {RULE}",
            "textAlign": "right",
        },
        style_cell_conditional=[{"if": {"column_id": ""}, "textAlign": "left"}],
        style_header={"fontWeight": 600, "backgroundColor": PAPER},
    )


def _item(item: Item) -> Any:
    if item.kind == "figure":
        assert isinstance(item.value, go.Figure)
        return dcc.Graph(figure=item.value, config={"displaylogo": False})
    if item.kind == "table":
        assert isinstance(item.value, pd.DataFrame)
        return _table(item.value)
    if item.kind == "kpis":
        assert isinstance(item.value, list)
        return _kpis(item.value)
    if item.kind == "caption":
        return html.P(str(item.value), style={"fontSize": "0.85rem", "color": MUTED})
    if item.kind == "note":
        return html.P(str(item.value), style={**META, "marginTop": "-0.2rem"})
    return html.Div(
        str(item.value),
        style={
            "padding": "0.7rem 0.9rem",
            "borderLeft": "3px solid #5b9bd5",
            "background": "#eef4fb",
            "margin": "0.6rem 0",
            "color": TEXT,
        },
    )


def _section(part: Section) -> list[Any]:
    body = [_item(i) for i in part.items]
    if part.title is None:
        return body
    heading = html.H3(
        part.title,
        style={
            "fontFamily": HEADING_STACK,
            "fontSize": "1.05rem",
            "fontWeight": 600,
            "textAlign": "center",
            "margin": "1.6rem 0 0.15rem",
            "color": TEXT,
        },
    )
    return [heading, html.Hr(style={**HAIRLINE, "margin": "0 0 0.9rem"}), *body]


def render(view: PageView) -> html.Div:
    meta = " · ".join(p for p in (view.as_of, view.freshness) if p)
    children: list[Any] = [
        html.H2(
            view.title,
            style={
                "fontFamily": HEADING_STACK,
                "fontSize": "2.1rem",
                "fontWeight": 600,
                "textAlign": "center",
                "margin": "0.2rem 0 0.35rem",
                "color": TEXT,
            },
        ),
        html.Div(meta, style={**META, "textAlign": "center"}),
        html.Hr(style={**HAIRLINE, "margin": "0.8rem 0 1.4rem"}),
    ]
    if view.empty_source is not None:
        children.append(
            html.Div(
                f"No data · {view.empty_source} · expected {view.empty_cadence} · "
                "last seen not tracked",
                style={**META, "padding": "1.6rem 0"},
            )
        )
    for part in view.sections:
        children.extend(_section(part))
    return html.Div(children)
