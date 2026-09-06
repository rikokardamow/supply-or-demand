"""US Natural Gas & Power (EIA + gridstatus). Session A scope (specs/05_us-gas-power.md):
Lower-48 storage worm chart + regional small multiples. Session B: CAISO/NYISO tabs
(mix stack, load/net-load, LMP heatmap). Session C: monthly dry production vs. LNG
exports dual-axis chart."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.lake import read_ts_long
from core.seasonal import seasonal_stats
from core.theme import dual_axis_chart, generation_mix_chart, hour_day_heatmap, seasonal_range_chart
from pipelines.eia.pull_gas_storage import STORAGE_GEO_MAP
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
    title = "Lower 48 Working Gas Storage — Seasonal"
    fig = _worm_chart(L48_SERIES_ID, title)
    if fig is None:
        st.info("No data yet — run `pipelines/eia/pull_gas_storage.py`.")
        return
    with card(title):
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
        fig = _worm_chart(series_id, title)
        with cols[i % 3]:
            if fig is None:
                st.info(f"No data yet for {label}.")
                continue
            fig.update_layout(height=320, showlegend=False)
            with card(title):
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
        st.info(f"No fuel-mix data yet for {iso} — run `pipelines/gridstatus_iso/pull_iso.py`.")
        return

    slug_to_fuel = {_slug(f): f for f in fuels}
    long_df = long_df.copy()
    long_df["fuel"] = long_df["series_id"].str.split(".").str[-1].map(slug_to_fuel)
    wide = long_df.pivot_table(index="ts", columns="fuel", values="value").fillna(0.0)
    ordered_cols = [f for f in fuels if f in wide.columns]
    title = f"{iso} Fuel Mix"
    fig = generation_mix_chart(wide[ordered_cols], title=title, unit="MW")
    with card(title):
        st.plotly_chart(fig)


def _iso_load_section(iso: str) -> None:
    load = _series_by_ts(f"gridstatus.{iso}.load")
    if load.empty:
        st.info(f"No load data yet for {iso} — run `pipelines/gridstatus_iso/pull_iso.py`.")
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
        load, net, title=title, left_label="Load (MW)", right_label="Net load (MW)"
    )
    with card(title):
        st.plotly_chart(fig)


def _iso_lmp_section(iso: str) -> None:
    hubs = HUBS[iso]
    hub = st.selectbox("Hub / zone", options=hubs, key=f"{iso}_hub")
    series = _series_by_ts(f"gridstatus.{iso}.lmp.{_slug(hub)}")
    if series.empty:
        st.info(f"No LMP data yet for {iso} {hub} — run `pipelines/gridstatus_iso/pull_iso.py`.")
        return
    title = f"{iso} {hub} LMP"
    fig = hour_day_heatmap(series.to_frame("value"), title=title, unit="USD/MWh")
    with card(title):
        st.plotly_chart(fig)


def _production_exports_section() -> None:
    production = _series_by_ts(PRODUCTION_SERIES[0])
    lng_exports = _series_by_ts(LNG_EXPORTS_SERIES[0])
    if production.empty or lng_exports.empty:
        st.info("No data yet — run `pipelines/eia/pull_production_exports.py`.")
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
        title=title,
        left_label="Dry production (MMcf)",
        right_label="LNG exports (MMcf)",
    )
    with card(title):
        st.plotly_chart(fig)
        st.caption(
            "LNG feedgas (gas consumed at liquefaction facilities before export) has no "
            "distinct EIA API series and is not shown — see pipelines/eia/CLAUDE.md."
        )


def _iso_tab(iso: str) -> None:
    st.subheader(f"{iso} fuel mix")
    _iso_mix_section(iso)
    st.subheader(f"{iso} load vs. net load")
    _iso_load_section(iso)
    st.subheader(f"{iso} LMP — hour x day")
    _iso_lmp_section(iso)


st.title("US Natural Gas & Power (EIA + gridstatus)")

st.subheader("Storage headline")
_headline_section()

st.subheader("Production vs. LNG exports")
_production_exports_section()

st.subheader("Regional small multiples")
_small_multiples_section()

st.subheader("ISO real-time signals")
_caiso_tab, _nyiso_tab = st.tabs(["CAISO", "NYISO"])
with _caiso_tab:
    _iso_tab("CAISO")
with _nyiso_tab:
    _iso_tab("NYISO")

st.caption(f"{len(STORAGE_GEO_MAP)} storage regions covered.")
