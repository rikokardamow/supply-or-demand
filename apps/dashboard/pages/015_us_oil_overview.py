"""US Oil Market Overview — national balance charts supplementary to page 01 (PADD detail).
Only charts not already shown on page 01 live here (no duplicate Crude/Gasoline/Distillate/
Cushing stock charts)."""

from __future__ import annotations

import core.theme  # noqa: F401
import streamlit as st
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import multi_year_overlay_chart, seasonal_range_chart, simple_time_series_chart


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


def _simple_section(series_id: str, title: str, unit: str) -> None:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    if df.empty:
        st.info(f"No data yet for {series_id} — run `pipelines/eia/pull_wpsr.py`.")
        return

    series = df.set_index("ts")["value"]
    fig = simple_time_series_chart(series, title=title, unit=unit)
    st.plotly_chart(fig, use_container_width=True)


def _four_week_avg_overlay(series_ids: list[str], title: str, unit: str) -> None:
    df = read_ts_long(series_ids=series_ids)
    if df.empty:
        st.info(f"No data yet for {series_ids} — run `pipelines/eia/pull_wpsr.py`.")
        return

    wide = df.pivot_table(index="ts", columns="series_id", values="value")
    combined = wide.sum(axis=1).rolling(4).mean().dropna()
    combined_df = combined.reset_index()
    combined_df.columns = ["ts", "value"]

    # seasonal_stats' default years window excludes the current (ongoing) year by
    # design for band/median purposes — this chart style wants it included, since
    # comparing the current year's partial line against recent years is the point.
    current_year = int(combined_df["ts"].dt.year.max())
    stats = seasonal_stats(combined_df, value_col="value", years=range(2018, current_year + 1))
    fig = multi_year_overlay_chart(stats, title=title, unit=unit)
    st.plotly_chart(fig, use_container_width=True)


st.title("US Oil Market Overview")

st.subheader("Refining & stocks")
_seasonal_section("WCRRIUS2", "Total US Refinery Demand — Seasonal Range", " Mbbl/d")
_seasonal_section("WTESTUS1", "US Total Commercial Oil and Product Stock — Seasonal Range", " Mbbl")

st.subheader("Production, exports & reserves")
_simple_section("WCRFPUS2", "US Crude Oil Production Estimate", "Mbbl/d")
_simple_section("WCREXUS2", "Total US Oil Exports", "Mbbl/d")
_simple_section("WCSSTUS1", "US Strategic Petroleum Reserves", "Mbbl")
_simple_section("WTTEXUS2", "Total US Oil and Fuel Export", "Mbbl/d")

st.subheader("Demand (4-week average, by year)")
_four_week_avg_overlay(["WGFUPUS2"], "Finished MOGAS Supplied (4-week avg.)", "Mbbl/d")
_four_week_avg_overlay(
    ["WGFUPUS2", "WDIUPUS2", "WKJUPUS2"],
    "US Implied Demand for Gasoline, Distillate & Jet Fuel (4-week avg.)",
    "Mbbl/d",
)
