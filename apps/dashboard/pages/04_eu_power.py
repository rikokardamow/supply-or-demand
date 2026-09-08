"""EU Power — ENTSO-E day-ahead prices, generation mix, load, and cross-border flows,
plus the EirGrid Ireland panel. Price map + arrow map + generation-mix stack (Session B);
Ireland panel (Session C) per specs/04_entsoe-eu-power.md."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.lake import read_flows, read_ts_long
from components.power_maps import render_flow_map, render_price_map
from components.section import empty_state, page_header, section
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


IRELAND_RANGE_DAYS = {"1M": 30, "3M": 90, "6M": 182, "1Y": 365, "All": None}


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _zone_filter_panel(latest_net: pd.DataFrame) -> list[str]:
    """Collapsible filter panel (accordion + checkboxes + live counts) -- see
    02_gas_storage.py's _country_filter_panel for the same convention."""
    for zone in ZONES:
        st.session_state.setdefault(f"eu_power_zone_filter_{zone}", True)
    selected_count = sum(st.session_state[f"eu_power_zone_filter_{z}"] for z in ZONES)

    with st.expander(f"Filter zones ({selected_count} of {len(ZONES)} shown)"):
        filter_cols = st.columns(3)
        zone_values = latest_net.set_index("zone")["net_position"]
        for i, zone in enumerate(ZONES):
            value = zone_values.get(zone)
            label = f"{zone} — {value:,.0f} MW" if value is not None else zone
            with filter_cols[i % 3]:
                st.checkbox(label, key=f"eu_power_zone_filter_{zone}")

    return [z for z in ZONES if st.session_state[f"eu_power_zone_filter_{z}"]]


page_header("EU Power (ENTSO-E)")

st.subheader("Day-ahead price map")
with section("EU Day-Ahead Price Map"):
    render_price_map()

st.subheader("Cross-border flows")
with section("EU Cross-Border Flow Map"):
    render_flow_map()

st.subheader("Generation mix")
selected_zone = st.selectbox("Zone", options=ZONES, key="generation_zone")

psr_by_slug = {_slug(psr): psr for psr in _GENERATION_ORDER}
generation_series_ids = [
    f"entsoe.{selected_zone}.generation.{slug}" for slug in psr_by_slug
]
generation_long = read_ts_long(series_ids=generation_series_ids)
if generation_long.empty:
    st.caption(f"Run `pipelines/entsoe/pull_actuals.py` to populate {selected_zone}.")
    empty_state("entsoe", "daily", None)
else:
    generation_long = generation_long.copy()
    generation_long["psr_type"] = generation_long["series_id"].str.split(".").str[-1].map(
        psr_by_slug
    )
    wide = generation_long.pivot_table(index="ts", columns="psr_type", values="value").fillna(0.0)
    ordered_cols = [c for c in _GENERATION_ORDER if c in wide.columns]
    mix_title = f"{selected_zone} Generation Mix"
    fig = generation_mix_chart(wide[ordered_cols], unit="MW")
    with section(mix_title):
        st.plotly_chart(fig)

st.subheader("Residual load")
load = _series_by_ts(f"entsoe.{selected_zone}.load")
wind_onshore = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Wind Onshore')}")
wind_offshore = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Wind Offshore')}")
solar = _series_by_ts(f"entsoe.{selected_zone}.forecast.{_slug('Solar')}")
if load.empty:
    st.caption(f"Run `pipelines/entsoe/pull_actuals.py` to populate {selected_zone}.")
    empty_state("entsoe", "daily", None)
else:
    wind_total = wind_onshore.add(wind_offshore, fill_value=0.0)
    residual = residual_load(load, wind_total, solar)
    residual_title = f"{selected_zone} Residual Load"
    fig = simple_time_series_chart(residual, unit="MW")
    with section(residual_title):
        st.plotly_chart(fig)

st.subheader("Net position (latest hour, ranked)")
flows_df = read_flows(source="entsoe")
power_df = flows_df[flows_df["mode"] == "power"]
if power_df.empty:
    st.caption("Run `pipelines/entsoe/pull_flows.py` to populate this.")
    empty_state("entsoe", "daily", None)
else:
    net_df = net_position(power_df)
    latest_ts = net_df["ts"].max()
    latest_net = net_df[net_df["ts"] == latest_ts].sort_values("net_position", ascending=False)

    selected_zones = _zone_filter_panel(latest_net)
    latest_net = latest_net[latest_net["zone"].isin(selected_zones)]

    if latest_net.empty:
        st.info("No zones selected — check at least one above.")
    else:
        bar = go.Figure(
            go.Bar(
                x=latest_net["zone"],
                y=latest_net["net_position"],
                marker_color=[NAVY if v >= 0 else RED for v in latest_net["net_position"]],
            )
        )
        net_position_title = f"Net Export Position — {pd.Timestamp(latest_ts)}"
        bar.update_layout(
            yaxis_title="Net position (MW, +export / -import)",
        )
        with section(net_position_title):
            st.plotly_chart(bar)

st.caption(f"{len(ZONES)} zones covered, {len(BORDERS)} borders flowing.")


def _eirgrid_series(field: str) -> pd.Series:
    df = read_ts_long(series_ids=[f"eirgrid.ROI.{field}"]).sort_values("ts")
    return df.set_index("ts")["value"]


st.subheader("Ireland panel (EirGrid)")
roi_demand = _eirgrid_series("demand")
roi_wind = _eirgrid_series("wind")

if roi_demand.empty or roi_wind.empty:
    st.caption("Run `pipelines/eirgrid/pull_ireland.py` to populate this.")
    empty_state("eirgrid", "daily", None)
else:
    ireland_range = st.segmented_control(
        "Time range",
        options=list(IRELAND_RANGE_DAYS),
        default="3M",
        required=True,
        key="eu_power_ireland_range",
    )
    ireland_days = IRELAND_RANGE_DAYS[ireland_range]
    if ireland_days is not None:
        ireland_cutoff = roi_demand.index.max() - pd.Timedelta(days=ireland_days)
        roi_demand = roi_demand[roi_demand.index >= ireland_cutoff]
        roi_wind = roi_wind[roi_wind.index >= ireland_cutoff]

    fig = dual_axis_chart(
        roi_demand,
        roi_wind,
        left_label="Demand (MW)",
        right_label="Wind (MW)",
    )
    with section("ROI Demand vs. Wind"):
        st.plotly_chart(fig)

    roi_net_import = _eirgrid_series("inter_net")
    snsp = snsp_proxy(roi_wind, roi_net_import, roi_demand).dropna()
    latest_snsp_pct = float(snsp.iloc[-1] * 100) if not snsp.empty else 0.0
    gauge = gauge_chart(latest_snsp_pct, title="SNSP Proxy — latest (%)")
    with section("SNSP Proxy — latest (%)"):
        st.plotly_chart(gauge)

    roi_ewic = _eirgrid_series("inter_ewic")
    roi_greenlink = _eirgrid_series("inter_greenlink")
    if ireland_days is not None:
        roi_ewic = roi_ewic[roi_ewic.index >= ireland_cutoff]
        roi_greenlink = roi_greenlink[roi_greenlink.index >= ireland_cutoff]
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
    inter_title = "Ireland Interconnector Flows (+import / -export)"
    inter_fig.update_layout(yaxis_title="MW")
    with section(inter_title):
        st.plotly_chart(inter_fig)
