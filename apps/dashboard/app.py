"""Kardamow Energy Dashboard — home page. Reads the lake, never calls APIs directly."""

from __future__ import annotations

import core.theme  # noqa: F401
import streamlit as st
from core.storage import warehouse

st.set_page_config(page_title="Kardamow Energy Dashboard", layout="wide")
st.title("Kardamow Energy Dashboard")

con = warehouse()
status = con.execute(
    "SELECT source, count(*) AS n_rows, max(ts) AS last_ts FROM ts_long GROUP BY source"
).df()

st.subheader("Lake status")
st.dataframe(status, use_container_width=True)
