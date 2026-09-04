"""Weather Overlay (Open-Meteo + ECMWF). Session A: population-weighted EU/US HDD
history+forecast vs. climatology (visual 1), and dual-axis HDD/CDD anomaly charts
linking weather to gas storage and power demand (visual 2 plus 3 more added per user
request -- see pipelines/weather/CLAUDE.md). Session B: cartopy anomaly maps (visual 3).
Session C: DE/DK/IE wind forecast cross-check vs. ENTSO-E (visual 4) and a stale-map
badge on the anomaly-map section."""

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
ANOMALY_MAP_MODELS = {"ecmwf": "ECMWF IFS", "gfs": "NOAA GFS"}
ANOMALY_MAP_ATTRIBUTION = {
    "ecmwf": "IFS HRES 2t (ECMWF Open Data, CC BY 4.0)",
    "gfs": "GFS 2t (NOAA/NCEP, public domain)",
}
STALE_MAP_THRESHOLD_HOURS = 24

US_STORAGE_SERIES_ID = "NW2_EPG0_SWO_R48_BCF"
ANOMALY_HISTORY_WINDOW_DAYS = 90

# User-adjustable version of the constant above, via the time-range pill row added to
# the page body -- kept as a separate dict so the pill's own default (90D) still lines
# up with the original fixed window.
ANOMALY_RANGE_DAYS = {"30D": 30, "90D": 90, "180D": 182, "1Y": 365}

CDD_LOAD_INFO = [("new_york", "NYISO"), ("los_angeles", "CAISO")]

# (country, ENTSO-E zone) -- pipelines/weather/wind_locations.csv's own country set,
# cross-checked against pipelines/entsoe/zones.py's ZONES (DE_LU/DK_1/IE_SEM all real
# covered zones there).
WIND_CROSSCHECK_INFO = [("DE", "DE_LU"), ("DK", "DK_1"), ("IE", "IE_SEM")]
WIND_PSR_TYPES = ("wind_onshore", "wind_offshore")


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


def _map_age_hours(rendered_at: pd.Timestamp, now: pd.Timestamp | None = None) -> float:
    """`now` is injectable so the >STALE_MAP_THRESHOLD_HOURS branch is testable without
    monkeypatching a clock -- defaults to the real current time for the page's own call."""
    if now is None:
        now = pd.Timestamp.now(tz="UTC")
    return (now - rendered_at).total_seconds() / 3600


def _anomaly_maps_section() -> None:
    """Reads pipelines/weather's own manifest.parquet (never calls ECMWF/Open-Meteo
    directly, per root CLAUDE.md's "pages read the lake, never call APIs" rule) and
    displays the map matching the region/step picked below, with a stale-map badge if
    the displayed map is more than STALE_MAP_THRESHOLD_HOURS old -- a sign
    `pipelines/weather/pull_daily.py` hasn't run recently."""
    manifest = read_manifest()
    if manifest.empty:
        st.info("No maps yet — run `pipelines/weather/pull_daily.py`.")
        return

    model_cols = st.columns(3)
    with model_cols[0]:
        model = st.selectbox(
            "Model",
            options=list(ANOMALY_MAP_MODELS),
            format_func=lambda m: ANOMALY_MAP_MODELS[m],
        )
    with model_cols[1]:
        region = st.selectbox(
            "Region",
            options=list(ANOMALY_MAP_REGIONS),
            format_func=lambda r: ANOMALY_MAP_REGIONS[r],
        )
    with model_cols[2]:
        step_label = st.segmented_control(
            "Forecast step",
            options=list(ANOMALY_MAP_STEPS),
            default="D+3",
            required=True,
            key="weather_anomaly_map_step",
        )
    step_hours = ANOMALY_MAP_STEPS[step_label]

    rows = manifest[
        (manifest["model"] == model)
        & (manifest["region"] == region)
        & (manifest["step_hours"] == step_hours)
    ]
    if rows.empty:
        st.info(
            f"No {ANOMALY_MAP_MODELS[model]} {ANOMALY_MAP_REGIONS[region]} "
            f"{step_label} map yet."
        )
        return

    latest = rows.sort_values("rendered_at").iloc[-1]
    rendered_at = pd.Timestamp(latest["rendered_at"])
    age_hours = _map_age_hours(rendered_at)

    card_title = (
        f"{ANOMALY_MAP_REGIONS[region]} 2m-Temp Anomaly — "
        f"{ANOMALY_MAP_MODELS[model]} — {step_label}"
    )
    with card(card_title):
        st.image(latest["path"])
        if age_hours > STALE_MAP_THRESHOLD_HOURS:
            st.warning(
                f"This map is {age_hours:.0f}h old — `pipelines/weather/pull_daily.py` "
                "may not have run recently."
            )
        st.caption(
            f"Valid {pd.Timestamp(latest['valid_time']):%Y-%m-%d} · rendered "
            f"{rendered_at:%Y-%m-%d %H:%M UTC} · "
            f"{ANOMALY_MAP_ATTRIBUTION[model]} vs a 3-year recent-normal grid "
            "— see pipelines/weather/CLAUDE.md for why 3 years, not a full ERA5 normal."
        )


def _entsoe_wind_forecast(zone: str) -> pd.Series:
    """Daily-mean MW, summed across onshore + offshore (whichever exist for `zone` --
    a landlocked zone simply has no offshore series, read_ts_long just returns fewer
    rows for it, nothing to special-case). ENTSO-E's day-ahead forecast is sub-daily
    (15-min/hourly, per pipelines/entsoe/CLAUDE.md) -- resampled to a daily mean here
    so it lines up with Open-Meteo's own daily wind index for the cross-check chart."""
    series_ids = [f"entsoe.{zone}.forecast.{psr}" for psr in WIND_PSR_TYPES]
    df = read_ts_long(series_ids=series_ids)
    if df.empty:
        return pd.Series(dtype=float)

    totals = df.groupby("ts")["value"].sum()
    daily_mean = totals.groupby(pd.DatetimeIndex(totals.index).floor("D")).mean()
    return daily_mean


def _wind_filter_panel() -> list[tuple[str, str]]:
    """Same collapsible-panel convention as _city_filter_panel above."""
    for country, _zone in WIND_CROSSCHECK_INFO:
        st.session_state.setdefault(f"weather_wind_filter_{country}", True)
    selected_count = sum(
        st.session_state[f"weather_wind_filter_{c}"] for c, _ in WIND_CROSSCHECK_INFO
    )

    with st.expander(f"Filter countries ({selected_count} of {len(WIND_CROSSCHECK_INFO)} shown)"):
        filter_cols = st.columns(3)
        for i, (country, zone) in enumerate(WIND_CROSSCHECK_INFO):
            with filter_cols[i % 3]:
                st.checkbox(f"{country} ({zone})", key=f"weather_wind_filter_{country}")

    return [
        item
        for item in WIND_CROSSCHECK_INFO
        if st.session_state[f"weather_wind_filter_{item[0]}"]
    ]


def _wind_vs_entsoe_section(country: str, zone: str, window_days: int) -> None:
    wind_index = _series_by_ts(
        f"wind.{country.lower()}.10m_max_kmh.forecast", source="open_meteo_forecast"
    )
    entsoe_wind = _entsoe_wind_forecast(zone)
    if wind_index.empty or entsoe_wind.empty:
        st.info(
            f"No data yet for {country} — run `pipelines/weather/pull_daily.py` and "
            "Spec 04's ENTSO-E pulls."
        )
        return

    cutoff = wind_index.index.max() - pd.Timedelta(days=window_days)
    wind_index = _trim_recent(wind_index, cutoff)
    entsoe_wind = _trim_recent(entsoe_wind, cutoff)

    title = f"{country} Wind Forecast Cross-Check"
    fig = dual_axis_chart(
        wind_index,
        entsoe_wind,
        title=title,
        left_label="10m wind speed, daily max (km/h)",
        right_label=f"ENTSO-E {zone} wind forecast, daily mean (MW)",
    )
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Two independent sources, not a unit conversion, and not a same-day "
            "overlap — `pipelines/entsoe/pull_daily.py` only ever ingests the prior "
            "day's ENTSO-E wind forecast (a trailing window, by that pipeline's own "
            "design), while Open-Meteo's forecast looks ahead. This chart shows the "
            "ENTSO-E-observed wind pattern for the last ~2 weeks transitioning into "
            "Open-Meteo's own forward outlook, not a strict timing cross-check — see "
            "pipelines/weather/CLAUDE.md."
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

st.subheader("Wind forecast cross-check")
selected_wind_countries = _wind_filter_panel()
if not selected_wind_countries:
    st.info("No countries selected — check at least one above.")
else:
    for country, zone in selected_wind_countries:
        _wind_vs_entsoe_section(country, zone, anomaly_days)
