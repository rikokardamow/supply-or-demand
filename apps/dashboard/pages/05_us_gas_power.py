"""US Natural Gas & Power (EIA + gridstatus). Session A scope (specs/05_us-gas-power.md):
Lower-48 storage worm chart + regional small multiples. Session B: CAISO/NYISO tabs
(mix stack, load/net-load, LMP heatmap). Session C: monthly dry production vs. LNG
exports dual-axis chart."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.lake import read_ts_long
from components.section import empty_state, page_header, section
from core.seasonal import current_track, seasonal_stats
from core.theme import (
    GREY,
    LIGHT_BLUE,
    NAVY,
    ORANGE,
    PAPER,
    RED,
    RULE,
    dual_axis_chart,
    generation_mix_chart,
    hour_day_heatmap,
    seasonal_range_chart,
)
from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP
from pipelines.eia.pull_prices import (
    GENERATOR_FUEL_COST_KEY,
    GENERATOR_FUEL_LOCATIONS,
    generator_fuel_series_id,
)
from pipelines.eia.pull_production_exports import LNG_EXPORTS_SERIES, PRODUCTION_SERIES
from pipelines.gridstatus_iso.hubs import HUBS
from pipelines.gridstatus_iso.transforms import net_load

# Renewables first, thermal last -- same stacking convention as 04_eu_power.py's
# generation mix. Fuel-type names are each ISO's own gridstatus column names,
# confirmed live (Spec 05 Session B) -- CAISO and NYISO don't share a naming scheme.
_ISO_FUEL_ORDER = {
    "CAISO": [
        "Solar",
        "Wind",
        "Geothermal",
        "Biomass",
        "Biogas",
        "Small Hydro",
        "Large Hydro",
        "Batteries",
        "Nuclear",
        "Natural Gas",
        "Coal",
        "Imports",
        "Other",
    ],
    "NYISO": [
        "Wind",
        "Hydro",
        "Other Renewables",
        "Nuclear",
        "Natural Gas",
        "Dual Fuel",
        "Other Fossil Fuels",
    ],
}

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

PRODUCTION_EXPORTS_RANGE_DAYS = {"1Y": 365, "2Y": 730, "5Y": 1825, "All": None}


def _worm_chart(series_id: str) -> go.Figure | None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        return None

    stats = seasonal_stats(df, value_col="value")
    current_year_series = current_track(df)

    return seasonal_range_chart(stats, current_year_series, unit="BCF")


def _headline_section() -> None:
    title = "Lower 48 Working Gas Storage — Seasonal"
    fig = _worm_chart(L48_SERIES_ID)
    if fig is None:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_gas_storage.py` to populate storage data.")
        return
    with section(title):
        st.plotly_chart(fig)


def _region_filter_panel() -> list[tuple[str, str]]:
    """Collapsible filter panel (accordion + checkboxes + live counts) -- see
    02_gas_storage.py's _country_filter_panel for the same convention."""
    for series_id, _label in _SMALL_MULTIPLE_SERIES:
        st.session_state.setdefault(f"gas_power_region_filter_{series_id}", True)
    selected_count = sum(
        st.session_state[f"gas_power_region_filter_{sid}"] for sid, _ in _SMALL_MULTIPLE_SERIES
    )

    with st.expander(
        f"Filter regions ({selected_count} of {len(_SMALL_MULTIPLE_SERIES)} shown)"
    ):
        filter_cols = st.columns(3)
        for i, (series_id, label) in enumerate(_SMALL_MULTIPLE_SERIES):
            latest = _series_by_ts(series_id)
            value = float(latest.iloc[-1]) if not latest.empty else None
            checkbox_label = f"{label} — {value:,.0f} BCF" if value is not None else label
            with filter_cols[i % 3]:
                st.checkbox(checkbox_label, key=f"gas_power_region_filter_{series_id}")

    return [
        item
        for item in _SMALL_MULTIPLE_SERIES
        if st.session_state[f"gas_power_region_filter_{item[0]}"]
    ]


def _small_multiples_section() -> None:
    selected = _region_filter_panel()
    if not selected:
        st.info("No regions selected — check at least one above.")
        return

    cols = st.columns(3)
    for i, (series_id, label) in enumerate(selected):
        title = f"{label} — Seasonal"
        fig = _worm_chart(series_id)
        with cols[i % 3], section(title):
            if fig is None:
                empty_state("eia", "weekly", None)
                continue
            fig.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig)


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _slug(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _iso_mix_section(iso: str) -> None:
    fuels = _ISO_FUEL_ORDER[iso]
    series_ids = [f"gridstatus.{iso}.fuel_mix.{_slug(fuel)}" for fuel in fuels]
    long_df = read_ts_long(series_ids=series_ids)
    if long_df.empty:
        empty_state("gridstatus", "daily", None)
        st.caption(f"Run `pipelines/gridstatus_iso/pull_iso.py` to populate {iso} fuel mix.")
        return

    slug_to_fuel = {_slug(f): f for f in fuels}
    long_df = long_df.copy()
    long_df["fuel"] = long_df["series_id"].str.split(".").str[-1].map(slug_to_fuel)
    wide = long_df.pivot_table(index="ts", columns="fuel", values="value").fillna(0.0)
    ordered_cols = [f for f in fuels if f in wide.columns]
    title = f"{iso} Fuel Mix"
    fig = generation_mix_chart(wide[ordered_cols], unit="MW")
    with section(title):
        st.plotly_chart(fig)


def _iso_load_section(iso: str) -> None:
    load = _series_by_ts(f"gridstatus.{iso}.load")
    if load.empty:
        empty_state("gridstatus", "daily", None)
        st.caption(f"Run `pipelines/gridstatus_iso/pull_iso.py` to populate {iso} load.")
        return

    fuels = _ISO_FUEL_ORDER[iso]
    empty = pd.Series(dtype=float)
    wind = _series_by_ts(f"gridstatus.{iso}.fuel_mix.{_slug('Wind')}") if "Wind" in fuels else empty
    solar = (
        _series_by_ts(f"gridstatus.{iso}.fuel_mix.{_slug('Solar')}") if "Solar" in fuels else empty
    )

    net = net_load(load, wind, solar)
    title = f"{iso} Load vs. Net Load"
    fig = dual_axis_chart(
        load, net, left_label="Load (MW)", right_label="Net load (MW)"
    )
    with section(title):
        st.plotly_chart(fig)


def _iso_lmp_section(iso: str) -> None:
    hubs = HUBS[iso]
    hub = st.selectbox("Hub / zone", options=hubs, key=f"{iso}_hub")
    series = _series_by_ts(f"gridstatus.{iso}.lmp.{_slug(hub)}")
    if series.empty:
        empty_state("gridstatus", "daily", None)
        st.caption(f"Run `pipelines/gridstatus_iso/pull_iso.py` to populate {iso} {hub} LMP.")
        return
    title = f"{iso} {hub} LMP"
    fig = hour_day_heatmap(series.to_frame("value"), unit="USD/MWh")
    with section(title):
        st.plotly_chart(fig)


def _production_exports_section() -> None:
    production = _series_by_ts(PRODUCTION_SERIES[0])
    lng_exports = _series_by_ts(LNG_EXPORTS_SERIES[0])
    if production.empty or lng_exports.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_production_exports.py` to populate this chart.")
        return

    time_range = st.segmented_control(
        "Time range",
        options=list(PRODUCTION_EXPORTS_RANGE_DAYS),
        default="2Y",
        required=True,
        key="gas_power_production_exports_range",
    )
    days = PRODUCTION_EXPORTS_RANGE_DAYS[time_range]
    if days is not None:
        cutoff = production.index.max() - pd.Timedelta(days=days)
        production = production[production.index >= cutoff]
        lng_exports = lng_exports[lng_exports.index >= cutoff]

    title = "US Dry Natural Gas Production vs. LNG Exports"
    fig = dual_axis_chart(
        production,
        lng_exports,
        left_label="Dry production (MMcf)",
        right_label="LNG exports (MMcf)",
    )
    with section(title):
        st.plotly_chart(fig)
        st.caption(
            "LNG feedgas (gas consumed at liquefaction facilities before export) has no "
            "distinct EIA API series and is not shown — see pipelines/eia/NOTES.md."
        )


# Excludes NAVY (reserved for the US national line) and GREY (reserved for the Henry Hub
# benchmark) so every colour on the chart carries one meaning. Cycled by index modulo its
# length rather than zipped against GENERATOR_FUEL_LOCATIONS, so a longer state list in
# future doesn't silently drop a series.
_STATE_PALETTE = (LIGHT_BLUE, RED, ORANGE)


def _delivered_fuel_cost_section() -> None:
    """The gas-to-power bridge: what generators pay above Henry Hub is where fuel
    switching economics actually bite. Spec 30 supplies the cost leg state by state --
    GENERATOR_FUEL_LOCATIONS holds US plus 9 states, and a single national average would
    wash out exactly the dispersion this chart exists to show. fred.dhhngsp was already
    in the lake as the benchmark."""
    ids = [
        generator_fuel_series_id(GENERATOR_FUEL_COST_KEY, loc) for loc in GENERATOR_FUEL_LOCATIONS
    ]
    df = read_ts_long(series_ids=ids)
    hh = read_ts_long(series_ids=["fred.dhhngsp"]).sort_values("ts")
    if df.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_prices.py` to populate generator fuel cost.")
        return

    fig = go.Figure()
    states = [loc for loc in GENERATOR_FUEL_LOCATIONS if loc != "US"]
    for i, location in enumerate(states):
        s = df[
            df["series_id"] == generator_fuel_series_id(GENERATOR_FUEL_COST_KEY, location)
        ].sort_values("ts")
        if s.empty:
            continue
        fig.add_trace(
            go.Scatter(x=s["ts"], y=s["value"], name=location, mode="lines",
                       line={"color": _STATE_PALETTE[i % len(_STATE_PALETTE)], "width": 1.5})
        )
    us = df[
        df["series_id"] == generator_fuel_series_id(GENERATOR_FUEL_COST_KEY, "US")
    ].sort_values("ts")
    if not us.empty:
        fig.add_trace(
            go.Scatter(x=us["ts"], y=us["value"], name="US (national)", mode="lines",
                       line={"color": NAVY, "width": 3})
        )
    if not hh.empty:
        fig.add_trace(
            go.Scatter(x=hh["ts"], y=hh["value"], name="Henry Hub spot", mode="lines",
                       line={"color": GREY, "width": 2, "dash": "dot"})
        )

    # Spec 30 line 124: the state-vs-Henry-Hub spread must be annotated, not just
    # described in a caption. Only the US national line's spread is annotated (one
    # annotation, not one per state -- ten would be noise) at the latest period the two
    # series actually share; skipped rather than raised if they never overlap.
    if not us.empty and not hh.empty:
        us_by_ts = us.set_index("ts")["value"]
        hh_by_ts = hh.set_index("ts")["value"]
        overlap = us_by_ts.index.intersection(hh_by_ts.index)
        if len(overlap):
            latest = overlap.max()
            spread = us_by_ts.loc[latest] - hh_by_ts.loc[latest]
            sign = "+" if spread >= 0 else "-"
            fig.add_annotation(
                x=latest,
                y=us_by_ts.loc[latest],
                text=f"US {sign}${abs(spread):.2f} vs Henry Hub",
                showarrow=True,
                arrowhead=2,
                ax=40,
                ay=-30,
                align="left",
                # House treatment (core/theme.py's seasonal_range_chart): opaque ground
                # and a hairline border so the box reads as a label rather than sitting
                # on top of the series.
                bgcolor=PAPER,
                bordercolor=RULE,
                borderwidth=1,
                borderpad=4,
                opacity=0.95,
            )

    fig.update_layout(yaxis_title="$/MMBtu")
    with section("State cost of natural gas delivered to generators vs Henry Hub"):
        st.plotly_chart(fig)
        st.caption(
            "Delivered cost sits above the benchmark by transport and contract terms; "
            "the spread across states is the dispersion in what generators actually "
            "pay, with the bold navy line the national average they are compared "
            "against. Widening spread raises the gas price generators actually face, "
            "which is what moves the coal-to-gas switching point — not the hub price "
            "alone."
        )


def _iso_tab(iso: str) -> None:
    st.subheader(f"{iso} fuel mix")
    _iso_mix_section(iso)
    st.subheader(f"{iso} load vs. net load")
    _iso_load_section(iso)
    st.subheader(f"{iso} LMP — hour x day")
    _iso_lmp_section(iso)


page_header("US Natural Gas & Power (EIA + gridstatus)")

st.subheader("Storage headline")
_headline_section()

st.subheader("Production vs. LNG exports")
_production_exports_section()

st.subheader("Delivered fuel cost")
_delivered_fuel_cost_section()

st.subheader("Regional small multiples")
_small_multiples_section()

st.subheader("ISO real-time signals")
_caiso_tab, _nyiso_tab = st.tabs(["CAISO", "NYISO"])
with _caiso_tab:
    _iso_tab("CAISO")
with _nyiso_tab:
    _iso_tab("NYISO")

st.caption(f"{len(STORAGE_GEO_MAP)} storage regions covered.")
