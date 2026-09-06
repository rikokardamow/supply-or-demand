"""Kardamow Energy Dashboard — home page. Reads the lake, never calls APIs directly."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from components.card import card
from core.freshness import staleness_report

st.set_page_config(page_title="Kardamow Energy Dashboard", layout="wide")
st.title("Kardamow Energy Dashboard")

_STATUS_ORDER = {"red": 0, "amber": 1, "green": 2}
_STATUS_ICON = {"red": "🔴", "amber": "🟡", "green": "🟢"}

# Shorter than the ttl=3600 the analytics pages use. Those cache expensive model fits over
# data that only changes on a pull; this is a *status* panel, and one that keeps insisting
# a source is stale for an hour after the pull that fixed it is worse than useless. Five
# minutes still collapses the many reruns of a single browsing session into one query.
_STATUS_TTL_SECONDS = 300


@st.cache_data(ttl=_STATUS_TTL_SECONDS)
def _lake_status() -> pd.DataFrame:
    """Cached because Streamlit reruns this whole script on every interaction, and an
    uncached staleness_report() meant re-querying the lake each time."""
    return staleness_report()


report = _lake_status()
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
    st.dataframe(report, hide_index=True)
