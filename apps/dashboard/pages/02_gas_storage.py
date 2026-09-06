"""EU Gas Storage & LNG — GIE AGSI+/ALSI+. Four visuals per specs/02_gie-gas-storage.md:
EU fill-% worm (headline, with days-to-full/empty), small-multiples grid, dual-axis net
injection vs. LNG send-out, and a ranked country-deviation bar chart."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.event_overlay import add_event_markers
from components.kardamow_take import kardamow_take
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import (
    NAVY,
    RED,
    dual_axis_chart,
    fullness_comparison_bars,
    seasonal_minmaxmean_chart,
    seasonal_range_chart,
)
from pipelines.gie.transforms import (
    country_deviation,
    days_to_full_or_empty,
    nearest_value_at_offset,
    net_flow,
)

GEO_OPTIONS = ["EU", "DE", "NL", "FR", "IT", "AT", "PL"]

SMALL_MULTIPLES_COUNTRIES = ["DE", "NL", "FR", "IT", "AT", "PL"]

# Daily-cadence equivalent of a live-dashboard time-range pill row (e.g. 1h/6h/24h/
# All) -- our series are daily, not intraday, so the windows are months/years instead.
NET_FLOW_RANGE_DAYS = {"3M": 90, "6M": 182, "1Y": 365, "2Y": 730, "All": None}

_COUNTRY_TAKES = {
    "DE": (
        "Germany's the weakest link in European storage, a full 31 points under median — "
        "Europe's largest gas market heading into winter this far behind should worry TTF "
        "longs more than any headline."
    ),
    "NL": (
        "The Netherlands is even further behind Germany, 30.6 points under median — two of "
        "the bloc's biggest hubs running this short at the same time isn't coincidence, "
        "it's the same drawdown hitting the same geography."
    ),
    "FR": (
        "France is tracking almost exactly its own deviation from a year ago — 19 points "
        "under median both ways — which makes it the cleanest read on how much of this "
        "shortfall is structural versus last winter simply repeating."
    ),
    "IT": (
        "Italy's the outlier here, barely 6 points under median while its northern "
        "neighbours run 20-30 points short — the LNG-heavy import mix is buying Italy a "
        "winter the pipeline-dependent countries don't get."
    ),
    "AT": (
        "Austria sits 14.8 points under median — as the transit hub feeding Germany and "
        "Italy both, a shortfall here doesn't stay local, it's the corridor that decides "
        "how much of those two gaps actually get bridged."
    ),
    "PL": (
        "Poland's the only country here running above its own year-ago level and basically "
        "on median — the one storage chart in Europe that isn't part of the shortfall "
        "story, which tells you this winter's risk is concentrated, not continental."
    ),
}


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _latest_value(series_id: str) -> float | None:
    series = _series_by_ts(series_id)
    return float(series.iloc[-1]) if not series.empty else None


def _worm_chart(
    series_id: str, title: str, extra_annotation_line: str | None = None
) -> go.Figure | None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        return None

    stats = seasonal_stats(df, value_col="value")
    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    return seasonal_range_chart(
        stats,
        current_year_series,
        title=title,
        unit="%",
        extra_annotation_line=extra_annotation_line,
    )


def _net_flow_df(geo: str) -> pd.DataFrame:
    injection = _series_by_ts(f"agsi.{geo}.injection")
    withdrawal = _series_by_ts(f"agsi.{geo}.withdrawal")
    if injection.empty or withdrawal.empty:
        return pd.DataFrame(columns=["ts", "value"])
    return net_flow(injection, withdrawal).reset_index()


def _fullness_bars_section(geo: str) -> None:
    fill_series = _series_by_ts(f"agsi.{geo}.full_pct")
    twh_series = _series_by_ts(f"agsi.{geo}.gas_in_storage")
    if fill_series.empty or twh_series.empty:
        st.info(f"No data yet for {geo} — run `pipelines/gie/pull_agsi.py`.")
        return

    latest_ts = fill_series.index.max()
    rows = [("Current", float(fill_series.iloc[-1]), float(twh_series.iloc[-1]))]
    for label, days_back in [("M-1", 30), ("Y-1", 365)]:
        target = latest_ts - pd.Timedelta(days=days_back)
        pct = nearest_value_at_offset(fill_series, target)
        twh = nearest_value_at_offset(twh_series, target)
        if pct is not None and twh is not None:
            rows.append((label, pct, twh))

    fig = fullness_comparison_bars(
        rows,
        unit_abs="TWh",
        date_label=latest_ts.strftime("%d-%b-%Y"),
        title=f"{geo} Storage Fullness",
    )
    with card(f"{geo} Storage Fullness"):
        st.plotly_chart(fig)

        injection = _series_by_ts(f"agsi.{geo}.injection")
        withdrawal = _series_by_ts(f"agsi.{geo}.withdrawal")
        working_gas_volume = _latest_value(f"agsi.{geo}.working_gas_volume")
        if not injection.empty and not withdrawal.empty and working_gas_volume is not None:
            avg_rate = net_flow(injection, withdrawal).rolling(7).mean().iloc[-1]
            if pd.notna(avg_rate):
                days, direction = days_to_full_or_empty(
                    rows[0][1], working_gas_volume, float(avg_rate)
                )
                if days is not None:
                    st.caption(f"At the current 7-day pace: {days:.0f} days to {direction}.")


def _fullness_seasonal_section(geo: str) -> None:
    title = f"{geo} Storage Fullness — Seasonal"
    fig = _worm_chart_minmaxmean(f"agsi.{geo}.full_pct", title, "%")
    if fig is None:
        st.info(f"No data yet for {geo} — run `pipelines/gie/pull_agsi.py`.")
        return
    with card(title):
        st.plotly_chart(fig)
        if geo == "EU":
            kardamow_take(
                "Europe's storage is well behind its own median, and the current injection "
                "pace gets it full past 1 November — the date the market actually prices, "
                "which is why this chart is doing more for TTF than the flat price admits."
            )


def _net_flow_seasonal_section(geo: str) -> None:
    net_df = _net_flow_df(geo)
    if net_df.empty:
        st.info(f"No data yet for {geo} — run `pipelines/gie/pull_agsi.py`.")
        return

    stats = seasonal_stats(net_df, value_col="value")
    current_year = net_df["ts"].dt.year.max()
    current = net_df[net_df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    title = f"{geo} Net Daily Injection/Withdrawal — Seasonal"
    fig = seasonal_minmaxmean_chart(stats, current_year_series, title=title, unit="GWh/d")
    with card(title):
        st.plotly_chart(fig)


def _worm_chart_minmaxmean(series_id: str, title: str, unit: str) -> go.Figure | None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        return None

    stats = seasonal_stats(df, value_col="value")
    current_year = df["ts"].dt.year.max()
    current = df[df["ts"].dt.year == current_year].sort_values("ts")
    reference_doy = current["ts"].map(lambda d: d.replace(year=2001)).dt.dayofyear
    current_year_series = current.set_index(reference_doy)["value"]

    return seasonal_minmaxmean_chart(stats, current_year_series, title=title, unit=unit)


def _country_filter_panel() -> list[str]:
    """Collapsible filter panel (accordion + checkboxes + live counts), the pattern
    from warwatch.ch's Types/Parties filter groups -- each option shows that
    country's latest fill % rather than a bare label."""
    for country in SMALL_MULTIPLES_COUNTRIES:
        st.session_state.setdefault(f"gas_storage_filter_{country}", True)
    selected_count = sum(
        st.session_state[f"gas_storage_filter_{c}"] for c in SMALL_MULTIPLES_COUNTRIES
    )

    with st.expander(
        f"Filter countries ({selected_count} of {len(SMALL_MULTIPLES_COUNTRIES)} shown)"
    ):
        filter_cols = st.columns(3)
        for i, country in enumerate(SMALL_MULTIPLES_COUNTRIES):
            latest = _latest_value(f"agsi.{country}.full_pct")
            label = f"{country} — {latest:.0f}% full" if latest is not None else country
            with filter_cols[i % 3]:
                st.checkbox(label, key=f"gas_storage_filter_{country}")

    return [c for c in SMALL_MULTIPLES_COUNTRIES if st.session_state[f"gas_storage_filter_{c}"]]


def _small_multiples_section() -> None:
    selected = _country_filter_panel()
    if not selected:
        st.info("No countries selected — check at least one above.")
        return

    cols = st.columns(3)
    for i, country in enumerate(selected):
        fig = _worm_chart(f"agsi.{country}.full_pct", f"{country} Fill %")
        with cols[i % 3]:
            if fig is None:
                st.info(f"No data yet for {country}.")
                continue
            fig.update_layout(height=320, showlegend=False)
            with card(f"{country} Fill %"):
                st.plotly_chart(fig)
                take = _COUNTRY_TAKES.get(country)
                if take is not None:
                    kardamow_take(take)


def _net_injection_vs_sendout_section() -> None:
    injection = _series_by_ts("agsi.EU.injection")
    withdrawal = _series_by_ts("agsi.EU.withdrawal")
    send_out = _series_by_ts("alsi.EU.send_out")

    if injection.empty or withdrawal.empty or send_out.empty:
        st.info("No data yet — run `pipelines/gie/pull_agsi.py` and `pull_alsi.py`.")
        return

    time_range = st.segmented_control(
        "Time range",
        options=list(NET_FLOW_RANGE_DAYS),
        default="1Y",
        required=True,
        key="gas_storage_net_flow_range",
    )
    days = NET_FLOW_RANGE_DAYS[time_range]
    if days is not None:
        cutoff = injection.index.max() - pd.Timedelta(days=days)
        injection = injection[injection.index >= cutoff]
        withdrawal = withdrawal[withdrawal.index >= cutoff]
        send_out = send_out[send_out.index >= cutoff]

    net_injection = net_flow(injection, withdrawal)
    fig = dual_axis_chart(
        net_injection,
        send_out,
        title="EU Net Injection vs. ALSI Send-Out",
        left_label="Net injection (GWh/d)",
        right_label="LNG send-out (GWh/d)",
    )
    add_event_markers(fig, commodity="gas")
    with card("EU Net Injection vs. ALSI Send-Out"):
        st.plotly_chart(fig)
        kardamow_take(
            "LNG send-out is running slightly ahead of net storage injection — the import "
            "terminals are doing more of the day-to-day balancing than the storage system "
            "itself right now, with the fill deficit above still unclosed."
        )


def _country_deviation_section() -> None:
    fill_by_country = {}
    for country in SMALL_MULTIPLES_COUNTRIES:
        df = read_ts_long(series_ids=[f"agsi.{country}.full_pct"])
        if not df.empty:
            fill_by_country[country] = df

    if not fill_by_country:
        st.info("No data yet — run `pipelines/gie/pull_agsi.py`.")
        return

    deviation_df = country_deviation(fill_by_country)
    bar = go.Figure(
        go.Bar(
            x=deviation_df["geo"],
            y=deviation_df["deviation"],
            marker_color=[NAVY if v >= 0 else RED for v in deviation_df["deviation"]],
        )
    )
    bar.update_layout(
        title="Country Fill % vs. Seasonal Median (ranked)",
        yaxis_title="Deviation (percentage points)",
    )
    with card("Country Fill % vs. Seasonal Median (ranked)"):
        st.plotly_chart(bar)
        kardamow_take(
            "Rank the six by deviation from median and the split is geographic, not "
            "random — Poland and Italy near normal, Germany and the Netherlands the "
            "worst by 20-plus points — the shortfall concentrates in the countries that "
            "lean hardest on pipeline gas that isn't coming back."
        )


st.title("EU Gas Storage & LNG (GIE AGSI+/ALSI+)")

st.subheader("Storage headline")
selected_geo = st.selectbox("Country", options=GEO_OPTIONS, index=0)
_fullness_bars_section(selected_geo)
_fullness_seasonal_section(selected_geo)
_net_flow_seasonal_section(selected_geo)

st.subheader("Country small multiples")
_small_multiples_section()

st.subheader("Net injection vs. LNG send-out")
_net_injection_vs_sendout_section()

st.subheader("Country deviation vs. seasonal median")
_country_deviation_section()
