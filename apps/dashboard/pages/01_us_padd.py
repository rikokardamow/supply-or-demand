"""Cushing crude stocks — seasonal range chart, read from the lake."""

from __future__ import annotations

import core.theme  # noqa: F401
import streamlit as st
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import seasonal_range_chart

SERIES_ID = "W_EPC0_SAX_YCUOK_MBBL"

st.title("US PADD — Cushing Crude Stocks")

df = read_ts_long(series_ids=[SERIES_ID])

if df.empty:
    st.info("No data yet — run `pipelines/eia/pull_crude_stocks.py` to populate the lake.")
else:
    stats = seasonal_stats(df, value_col="value")

    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    fig = seasonal_range_chart(
        stats,
        current_year_series,
        title="Cushing Crude Stocks — Seasonal Range",
        unit=" mb",
    )
    st.plotly_chart(fig, use_container_width=True)
