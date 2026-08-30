"""EU Power — ENTSO-E day-ahead prices, generation mix, load, and cross-border flows,
plus the EirGrid Ireland panel. Price map + arrow map + generation-mix stack (Session B);
Ireland panel (Session C) per specs/04_entsoe-eu-power.md."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.power_maps import render_flow_map, render_price_map
from core.storage import read_flows, read_ts_long
from core.theme import (
    LIGHT_BLUE,
    NAVY,
    RED,
    dual_axis_chart,
    gauge_chart,
    generation_mix_chart,
    simple_time_series_chart,
)
from pipelines.eirgrid.transforms import snsp_proxy
from pipelines.entsoe.transforms import net_position, residual_load
from pipelines.entsoe.zones import BORDERS, ZONES

# Renewables first (bottom of the stack), thermal/other last (top) — per the spec's own
# "renewables greens/blues, thermal greys/navy" visual intent.
_GENERATION_ORDER = [
    "Solar",
    "Wind Onshore",
    "Wind Offshore",
    "Hydro Run-of-river and poundage",
    "Hydro Water Reservoir",
    "Hydro Pumped Storage",
    "Biomass",
    "Geothermal",
    "Other renewable",
    "Nuclear",
    "Fossil Gas",
    "Fossil Hard coal",
    "Fossil Brown coal/Lignite",
    "Fossil Oil",
    "Fossil Coal-derived gas",
    "Waste",
    "Other",
]


def _slug(psr_type: str) -> str:
    # Must match pipelines/entsoe/pull_actuals.py's own _slug exactly — this reverses it
    # to recover the PSR-type name from a series_id's final segment.
    return psr_type.lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


st.title("EU Power (ENTSO-E)")

st.subheader("Day-ahead price map")
render_price_map()

st.subheader("Cross-border flows")
render_flow_map()

st.subheader("Generation mix")
selected_zone = st.selectbox("Zone", options=ZONES, key="generation_zone")

psr_by_slug = {_slug(psr): psr for psr in _GENERATION_ORDER}
generation_series_ids = [
    f"entsoe.{selected_zone}.generation.{slug}" for slug in psr_by_slug
]
generation_long = read_ts_long(series_ids=generation_series_ids)
if generation_long.empty:
    st.info(f"No generation data yet for {selected_zone} — run `pipelines/entsoe/pull_actuals.py`.")
else:
    generation_long = generation_long.copy()
    generation_long["psr_type"] = generation_long["series_id"].str.split(".").str[-1].map(
        psr_by_slug
    )
    wide = generation_long.pivot_table(index="ts", columns="psr_type", values="value").fillna(0.0)
    ordered_cols = [c for c in _GENERATION_ORDER if c in wide.columns]
    fig = generation_mix_chart(
        wide[ordered_cols], title=f"{selected_zone} Generation Mix", unit="MW"
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Residual load")
load = _series_by_ts(f"entsoe.{selected_zone}.load")
wind_onshore = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Wind Onshore')}")
wind_offshore = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Wind Offshore')}")
solar = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Solar')}")
if load.empty:
    st.info(f"No load data yet for {selected_zone} — run `pipelines/entsoe/pull_actuals.py`.")
else:
    wind_total = wind_onshore.add(wind_offshore, fill_value=0.0)
    residual = residual_load(load, wind_total, solar)
    fig = simple_time_series_chart(residual, title=f"{selected_zone} Residual Load", unit="MW")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Net position (latest hour, ranked)")
flows_df = read_flows(source="entsoe")
power_df = flows_df[flows_df["mode"] == "power"]
if power_df.empty:
    st.info("No flow data yet — run `pipelines/entsoe/pull_flows.py`.")
else:
    net_df = net_position(power_df)
    latest_ts = net_df["ts"].max()
    latest_net = net_df[net_df["ts"] == latest_ts].sort_values("net_position", ascending=False)
    bar = go.Figure(
        go.Bar(
            x=latest_net["zone"],
            y=latest_net["net_position"],
            marker_color=[NAVY if v >= 0 else RED for v in latest_net["net_position"]],
        )
    )
    bar.update_layout(
        title=f"Net Export Position — {pd.Timestamp(latest_ts)}",
        yaxis_title="Net position (MW, +export / -import)",
    )
    st.plotly_chart(bar, use_container_width=True)

st.caption(f"{len(ZONES)} zones covered, {len(BORDERS)} borders flowing.")


def _eirgrid_series(field: str) -> pd.Series:
    df = read_ts_long(series_ids=[f"eirgrid.ROI.{field}"]).sort_values("ts")
    return df.set_index("ts")["value"]


st.subheader("Ireland panel (EirGrid)")
roi_demand = _eirgrid_series("demand")
roi_wind = _eirgrid_series("wind")

if roi_demand.empty or roi_wind.empty:
    st.info("No EirGrid data yet — run `pipelines/eirgrid/pull_ireland.py`.")
else:
    fig = dual_axis_chart(
        roi_demand,
        roi_wind,
        title="ROI Demand vs. Wind",
        left_label="Demand (MW)",
        right_label="Wind (MW)",
    )
    st.plotly_chart(fig, use_container_width=True)

    roi_net_import = _eirgrid_series("inter_net")
    snsp = snsp_proxy(roi_wind, roi_net_import, roi_demand).dropna()
    latest_snsp_pct = float(snsp.iloc[-1] * 100) if not snsp.empty else 0.0
    gauge = gauge_chart(latest_snsp_pct, title="SNSP Proxy — latest (%)")
    st.plotly_chart(gauge, use_container_width=True)

    roi_ewic = _eirgrid_series("inter_ewic")
    roi_greenlink = _eirgrid_series("inter_greenlink")
    inter_fig = go.Figure()
    inter_fig.add_trace(
        go.Scatter(x=roi_ewic.index, y=roi_ewic.values, name="EWIC", line={"color": NAVY})
    )
    inter_fig.add_trace(
        go.Scatter(
            x=roi_greenlink.index,
            y=roi_greenlink.values,
            name="Greenlink",
            line={"color": LIGHT_BLUE},
        )
    )
    inter_fig.update_layout(
        title="Ireland Interconnector Flows (+import / -export)", yaxis_title="MW"
    )
    st.plotly_chart(inter_fig, use_container_width=True)
