"""US Natural Gas & Power (EIA + gridstatus). Session A scope (specs/05_us-gas-power.md):
Lower-48 storage worm chart + regional small multiples. ISO tabs and production/exports
land in later sessions."""

from __future__ import annotations

import core.theme  # noqa: F401
import plotly.graph_objects as go
import streamlit as st
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import seasonal_range_chart
from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP

L48_SERIES_ID = "NW2_EPG0_SWO_R48_BCF"

# Small multiples exclude L48 (it's the headline chart above) and order the remaining
# 7 regions geographically rather than STORAGE_GEO_MAP's dict order.
_SMALL_MULTIPLE_SERIES = [
    ("NW2_EPG0_SWO_R31_BCF", "East"),
    ("NW2_EPG0_SWO_R32_BCF", "Midwest"),
    ("NW2_EPG0_SWO_R34_BCF", "Mountain"),
    ("NW2_EPG0_SWO_R35_BCF", "Pacific"),
    ("NW2_EPG0_SWO_R33_BCF", "South Central"),
    ("NW2_EPG0_SSO_R33_BCF", "South Central — Salt"),
    ("NW2_EPG0_SNO_R33_BCF", "South Central — Nonsalt"),
]


def _worm_chart(series_id: str, title: str) -> go.Figure | None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        return None

    stats = seasonal_stats(df, value_col="value")
    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    return seasonal_range_chart(stats, current_year_series, title=title, unit="BCF")


def _headline_section() -> None:
    fig = _worm_chart(L48_SERIES_ID, "Lower 48 Working Gas Storage — Seasonal")
    if fig is None:
        st.info("No data yet — run `pipelines/eia/pull_gas_storage.py`.")
        return
    st.plotly_chart(fig, use_container_width=True)


def _small_multiples_section() -> None:
    cols = st.columns(3)
    for i, (series_id, label) in enumerate(_SMALL_MULTIPLE_SERIES):
        fig = _worm_chart(series_id, f"{label} — Seasonal")
        with cols[i % 3]:
            if fig is None:
                st.info(f"No data yet for {label}.")
                continue
            fig.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)


st.title("US Natural Gas & Power (EIA + gridstatus)")

st.subheader("Storage headline")
_headline_section()

st.subheader("Regional small multiples")
_small_multiples_section()

st.caption(f"{len(STORAGE_GEO_MAP)} storage regions covered.")
