"""Kardamow Energy Dashboard — home page. Reads the lake, never calls APIs directly."""

from __future__ import annotations

import core.theme  # noqa: F401
import streamlit as st
from components.card import card
from core.freshness import staleness_report

st.set_page_config(page_title="Kardamow Energy Dashboard", layout="wide")
st.title("Kardamow Energy Dashboard")

_STATUS_ORDER = {"red": 0, "amber": 1, "green": 2}
_STATUS_ICON = {"red": "🔴", "amber": "🟡", "green": "🟢"}

report = staleness_report()
report = report.sort_values(
    by="status", key=lambda col: col.map(_STATUS_ORDER)
).reset_index(drop=True)
report["status"] = [f"{_STATUS_ICON[s]} {s}" for s in report["status"]]

with card("Lake status"):
    st.caption(
        "Every source across ts_long, flows, events and sanctions, checked against its "
        "own expected pull cadence (see core/freshness.py) — 🟢 within cadence, "
        "🟡 up to 2x cadence, 🔴 beyond that."
    )
    st.dataframe(report, use_container_width=True, hide_index=True)
