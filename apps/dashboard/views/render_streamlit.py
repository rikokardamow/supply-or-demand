"""Draw a ``views.sd.PageView`` with Streamlit and the house components."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, kpi_row, page_header, section, source_note

from views.sd import Item, PageView, Section


def _item(item: Item) -> None:
    if item.kind == "figure":
        assert isinstance(item.value, go.Figure)
        st.plotly_chart(item.value)
    elif item.kind == "table":
        assert isinstance(item.value, pd.DataFrame)
        st.dataframe(item.value, width="stretch")
    elif item.kind == "kpis":
        assert isinstance(item.value, list)
        kpi_row(item.value)
    elif item.kind == "caption":
        st.caption(str(item.value))
    elif item.kind == "note":
        source_note(str(item.value))
    elif item.kind == "info":
        st.info(str(item.value))


def _section(part: Section) -> None:
    if part.title is None:
        for item in part.items:
            _item(item)
        return
    with section(part.title):
        for item in part.items:
            _item(item)


def render(view: PageView) -> None:
    page_header(view.title, as_of=view.as_of, freshness=view.freshness)
    if view.empty_source is not None:
        empty_state(view.empty_source, view.empty_cadence or "", None)
    for part in view.sections:
        _section(part)
