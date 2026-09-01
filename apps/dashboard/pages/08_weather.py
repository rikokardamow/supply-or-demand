"""Weather Overlay (Open-Meteo). Session A scope (specs/08_weather.md): population-
weighted EU/US HDD history+forecast vs. climatology (visual 1), and dual-axis HDD/CDD
anomaly charts linking weather to gas storage and power demand (visual 2 plus 3 more
added per user request -- see pipelines/weather/CLAUDE.md). ECMWF anomaly maps and wind
land in later sessions."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import NAVY, dual_axis_chart, seasonal_range_chart
from pipelines.gie.transforms import net_flow
from pipelines.weather.anomaly_maps import read_manifest
from pipelines.weather.climatology import build_climatology
from pipelines.weather.gas_proxy import net_withdrawal

ANOMALY_MAP_REGIONS = {"eu": "Europe", "conus": "CONUS"}
ANOMALY_MAP_STEPS = {"D+3": 72, "D+7": 168}

US_STORAGE_SERIES_ID = "NW2_EPG0_SWO_R48_BCF"
ANOMALY_HISTORY_WINDOW_DAYS = 90

# User-adjustable version of the constant above, via the time-range pill row added to
# the page body -- kept as a separate dict so the pill's own default (90D) still lines
# up with the original fixed window.
ANOMALY_RANGE_DAYS = {"30D": 30, "90D": 90, "180D": 182, "1Y": 365}

CDD_LOAD_INFO = [("new_york", "NYISO"), ("los_angeles", "CAISO")]


def _series_by_ts(series_id: str, source: str | None = None) -> pd.Series:
    df = read_ts_long(series_ids=[series_id])
    if source is not None:
        df = df[df["source"] == source]
    return df.sort_values("ts").set_index("ts")["value"]


def _recent_cutoff(
    series_id: str, days: int = ANOMALY_HISTORY_WINDOW_DAYS
) -> pd.Timestamp | None:
    """The anomaly series below only plots a trailing window, not full history --
    other series joined onto the same dual-axis chart (e.g. gas storage, which has
    years of history) need trimming to the same recent window, or their much wider
    date range squashes the weather trace to an invisible sliver at the chart's edge."""
    history = _series_by_ts(series_id, source="open_meteo")
    if history.empty:
        return None
    cutoff: pd.Timestamp = history.index.max() - pd.Timedelta(days=days)
    return cutoff


def _trim_recent(series: pd.Series, cutoff: pd.Timestamp | None) -> pd.Series:
    if cutoff is None:
        return series
    return series[series.index >= cutoff]


def _anomaly_series(
    series_id: str,
    forecast_series_id: str | None = None,
    window_days: int = ANOMALY_HISTORY_WINDOW_DAYS,
) -> pd.Series:
    """Recent history (trailing window) plus the forecast horizon, each minus the
    climatological daily normal for that day-of-year -- built from the already-cached
    Parquet in pipelines/weather/climatology.py, not a live API call."""
    climatology = build_climatology()
    clim_lookup = climatology.loc[climatology["series_id"] == series_id].set_index("doy")[
        "climatology"
    ]
    if clim_lookup.empty:
        return pd.Series(dtype=float)

    parts = [_series_by_ts(series_id, source="open_meteo").tail(window_days)]
    if forecast_series_id is not None:
        parts.append(_series_by_ts(forecast_series_id, source="open_meteo_forecast"))
    combined = pd.concat(parts)
    if combined.empty:
        return pd.Series(dtype=float)

    doy = pd.Index([ts.replace(year=2001).dayofyear for ts in combined.index])
    baseline = clim_lookup.reindex(doy).to_numpy()
    return pd.Series(combined.to_numpy() - baseline, index=combined.index)


def _climatology_section(region: str) -> None:
    series_id = f"hdd.{region}.popw"
    history = _series_by_ts(series_id, source="open_meteo")
    if history.empty:
        st.info("No data yet — run `pipelines/weather/pull_weather.py`.")
        return

    history_df = history.reset_index()
    history_df.columns = ["ts", "value"]
    stats = seasonal_stats(history_df, value_col="value")
    current_year = history_df["ts"].dt.year.max()
    current = history_df[history_df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    title = f"{region.upper()} Population-Weighted HDD — Seasonal"
    fig = seasonal_range_chart(stats, current_year_series, title=title, unit="degree-days")

    forecast = _series_by_ts(f"{series_id}.forecast", source="open_meteo_forecast")
    if not forecast.empty:
        forecast_doy = [ts.replace(year=2001).dayofyear for ts in forecast.index]
        fig.add_trace(
            go.Scatter(
                x=forecast_doy,
                y=forecast.to_numpy(),
                mode="lines",
                name="Forecast",
                line={"color": NAVY, "width": 2, "dash": "dash"},
            )
        )

    with card(title):
        st.plotly_chart(fig, use_container_width=True)


def _eu_hdd_vs_gas_section(window_days: int) -> None:
    cutoff = _recent_cutoff("hdd.eu.popw", window_days)
    injection = _trim_recent(_series_by_ts("agsi.EU.injection"), cutoff)
    withdrawal = _trim_recent(_series_by_ts("agsi.EU.withdrawal"), cutoff)
    hdd_anomaly = _anomaly_series("hdd.eu.popw", "hdd.eu.popw.forecast", window_days)
    if injection.empty or withdrawal.empty or hdd_anomaly.empty:
        st.info("No data yet — run `pipelines/weather/pull_weather.py` and Spec 02's pulls.")
        return

    eu_net_withdrawal = net_flow(withdrawal, injection)
    title = "EU HDD Anomaly vs. Gas Net-Withdrawal"
    fig = dual_axis_chart(
        hdd_anomaly,
        eu_net_withdrawal,
        title=title,
        left_label="HDD anomaly (degree-days)",
        right_label="Net withdrawal (GWh/d)",
    )
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        kardamow_take(
            "Colder-than-normal EU weather shows up in storage draws within days, not "
            "weeks — this is the fastest-moving read on whether a cold snap is actually "
            "pulling gas out of the ground or just making headlines."
        )


def _us_hdd_vs_gas_section(window_days: int) -> None:
    level = _series_by_ts(US_STORAGE_SERIES_ID)
    hdd_anomaly = _anomaly_series("hdd.us.popw", "hdd.us.popw.forecast", window_days)
    if level.empty or hdd_anomaly.empty:
        st.info("No data yet — run `pipelines/weather/pull_weather.py` and Spec 05's pulls.")
        return

    # net_withdrawal needs the point before the trimmed window to diff against, so
    # compute it on the full series first and only trim the result afterwards.
    cutoff = _recent_cutoff("hdd.us.popw", window_days)
    us_net_withdrawal = _trim_recent(net_withdrawal(level), cutoff)
    title = "US HDD Anomaly vs. Gas Storage Net-Withdrawal"
    fig = dual_axis_chart(
        hdd_anomaly,
        us_net_withdrawal,
        title=title,
        left_label="HDD anomaly (degree-days)",
        right_label="Net withdrawal (BCF/week)",
    )
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "EIA's storage route publishes a weekly level, not a daily injection/"
            "withdrawal split like GIE's AGSI — net withdrawal here is the "
            "week-over-week drop, so this series is weekly while the HDD anomaly "
            "is daily."
        )


def _city_filter_panel() -> list[tuple[str, str]]:
    """Collapsible filter panel (accordion + checkboxes) -- see 02_gas_storage.py's
    _country_filter_panel for the same convention (no live counts here since a CDD
    anomaly doesn't have a single meaningful "latest" headline number)."""
    for city, _iso in CDD_LOAD_INFO:
        st.session_state.setdefault(f"weather_city_filter_{city}", True)
    selected_count = sum(st.session_state[f"weather_city_filter_{c}"] for c, _ in CDD_LOAD_INFO)

    with st.expander(f"Filter cities ({selected_count} of {len(CDD_LOAD_INFO)} shown)"):
        filter_cols = st.columns(2)
        for i, (city, iso) in enumerate(CDD_LOAD_INFO):
            label = f"{city.replace('_', ' ').title()} ({iso})"
            with filter_cols[i % 2]:
                st.checkbox(label, key=f"weather_city_filter_{city}")

    return [item for item in CDD_LOAD_INFO if st.session_state[f"weather_city_filter_{item[0]}"]]


def _cdd_vs_load_section(city: str, iso: str, window_days: int) -> None:
    cdd_anomaly = _anomaly_series(f"cdd.{city}.f65", f"cdd.{city}.f65.forecast", window_days)
    load = _series_by_ts(f"gridstatus.{iso}.load")
    if cdd_anomaly.empty or load.empty:
        st.info(
            f"No data yet for {iso} — run `pipelines/weather/pull_weather.py` "
            "and Spec 05's pulls."
        )
        return

    title = f"{city.replace('_', ' ').title()} CDD Anomaly vs. {iso} Load"
    fig = dual_axis_chart(
        cdd_anomaly,
        load,
        title=title,
        left_label="CDD anomaly (degree-days)",
        right_label="Load (MW)",
    )
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"{iso}'s load pull keeps a trailing 60-day window (see "
            "pipelines/gridstatus_iso/CLAUDE.md), so this chart covers a recent "
            "window, not deep seasonal history."
        )


def _anomaly_maps_section() -> None:
    """Reads pipelines/weather's own manifest.parquet (never calls ECMWF/Open-Meteo
    directly, per root CLAUDE.md's "pages read the lake, never call APIs" rule) and
    displays the map matching the region/step picked below. A stale-map badge (>24h
    old) is Session C's job, per the spec's own session split -- not added here."""
    manifest = read_manifest()
    if manifest.empty:
        st.info("No maps yet — run `pipelines/weather/pull_anomaly_maps.py`.")
        return

    region_cols = st.columns(2)
    with region_cols[0]:
        region = st.selectbox(
            "Region",
            options=list(ANOMALY_MAP_REGIONS),
            format_func=lambda r: ANOMALY_MAP_REGIONS[r],
        )
    with region_cols[1]:
        step_label = st.segmented_control(
            "Forecast step",
            options=list(ANOMALY_MAP_STEPS),
            default="D+3",
            required=True,
            key="weather_anomaly_map_step",
        )
    step_hours = ANOMALY_MAP_STEPS[step_label]

    rows = manifest[(manifest["region"] == region) & (manifest["step_hours"] == step_hours)]
    if rows.empty:
        st.info(f"No {ANOMALY_MAP_REGIONS[region]} {step_label} map yet.")
        return

    latest = rows.sort_values("rendered_at").iloc[-1]
    with card(f"{ANOMALY_MAP_REGIONS[region]} 2m-Temp Anomaly — {step_label}"):
        st.image(latest["path"])
        st.caption(
            f"Valid {pd.Timestamp(latest['valid_time']):%Y-%m-%d} · rendered "
            f"{pd.Timestamp(latest['rendered_at']):%Y-%m-%d %H:%M UTC} · "
            "IFS HRES 2t (ECMWF Open Data, CC BY 4.0) vs a 3-year recent-normal grid "
            "— see pipelines/weather/CLAUDE.md for why 3 years, not a full ERA5 normal."
        )


st.title("Weather Overlay")

st.subheader("Population-weighted HDD vs. climatology")
col_eu, col_us = st.columns(2)
with col_eu:
    _climatology_section("eu")
with col_us:
    _climatology_section("us")

st.subheader("2m-temperature anomaly maps")
_anomaly_maps_section()

anomaly_range = st.segmented_control(
    "Anomaly window",
    options=list(ANOMALY_RANGE_DAYS),
    default="90D",
    required=True,
    key="weather_anomaly_range",
)
anomaly_days = ANOMALY_RANGE_DAYS[anomaly_range]

st.subheader("EU weather vs. gas storage")
_eu_hdd_vs_gas_section(anomaly_days)

st.subheader("US weather vs. gas storage")
_us_hdd_vs_gas_section(anomaly_days)

st.subheader("Cooling demand vs. power load")
selected_cities = _city_filter_panel()
if not selected_cities:
    st.info("No cities selected — check at least one above.")
else:
    for city, iso in selected_cities:
        _cdd_vs_load_section(city, iso, anomaly_days)
