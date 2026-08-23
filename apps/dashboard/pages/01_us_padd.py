"""US PADD — seasonal stocks charts + refining dual-axis chart, read from the lake."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import dual_axis_chart, seasonal_range_chart

GROSS_INPUTS_BY_GEO = {
    "US": "WGIRIUS2",
    "PADD1": "WGIRIP12",
    "PADD2": "WGIRIP22",
    "PADD3": "WGIRIP32",
    "PADD4": "WGIRIP42",
    "PADD5": "WGIRIP52",
}
UTILISATION_BY_GEO = {
    "US": "WPULEUS3",
    "PADD1": "W_NA_YUP_R10_PER",
    "PADD2": "W_NA_YUP_R20_PER",
    "PADD3": "W_NA_YUP_R30_PER",
    "PADD4": "W_NA_YUP_R40_PER",
    "PADD5": "W_NA_YUP_R50_PER",
}


def _seasonal_section(series_id: str, title: str, unit: str) -> None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        st.info(f"No data yet for {series_id} — run `pipelines/eia/pull_wpsr.py`.")
        return

    stats = seasonal_stats(df, value_col="value")
    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    fig = seasonal_range_chart(stats, current_year_series, title=title, unit=unit)
    st.plotly_chart(fig, use_container_width=True)


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


st.title("US PADD — Crude & Product Movements")

st.subheader("Seasonal ranges")
_seasonal_section("W_EPC0_SAX_YCUOK_MBBL", "Cushing Crude Stocks — Seasonal Range", " mb")
_seasonal_section("WCESTUS1", "US Crude Stocks (ex-SPR) — Seasonal Range", " mb")
_seasonal_section("WGTSTUS1", "US Total Gasoline Stocks — Seasonal Range", " mb")
_seasonal_section("WDISTUS1", "US Distillate Stocks — Seasonal Range", " mb")

st.subheader("Refining — gross inputs vs. utilisation")
geo = st.selectbox("Region", options=list(GROSS_INPUTS_BY_GEO), index=0)

gross_inputs = _series_by_ts(GROSS_INPUTS_BY_GEO[geo])
utilisation = _series_by_ts(UTILISATION_BY_GEO[geo])

if gross_inputs.empty or utilisation.empty:
    st.info(f"No refining data yet for {geo} — run `pipelines/eia/pull_wpsr.py`.")
else:
    fig = dual_axis_chart(
        gross_inputs,
        utilisation,
        title=f"{geo} Refinery Gross Inputs vs. Utilisation",
        left_label="Gross inputs (Mbbl/d)",
        right_label="Utilisation (%)",
    )
    st.plotly_chart(fig, use_container_width=True)
