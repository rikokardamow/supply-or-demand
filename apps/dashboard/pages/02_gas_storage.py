"""EU Gas Storage & LNG — GIE AGSI+/ALSI+. Four visuals per specs/02_gie-gas-storage.md:
EU fill-% worm (headline, with days-to-full/empty), small-multiples grid, dual-axis net
injection vs. LNG send-out, and a ranked country-deviation bar chart."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.kardamow_take import kardamow_take
from core.seasonal import seasonal_stats
from core.storage import read_ts_long
from core.theme import NAVY, RED, dual_axis_chart, seasonal_range_chart
from pipelines.gie.transforms import country_deviation, days_to_full_or_empty, net_flow

SMALL_MULTIPLES_COUNTRIES = ["DE", "NL", "FR", "IT", "AT", "PL"]

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


def _eu_headline_section() -> None:
    extra_line = None
    injection = _series_by_ts("agsi.EU.injection")
    withdrawal = _series_by_ts("agsi.EU.withdrawal")
    working_gas_volume = _latest_value("agsi.EU.working_gas_volume")
    latest_fill = _latest_value("agsi.EU.full_pct")

    have_inputs = (
        not injection.empty
        and not withdrawal.empty
        and working_gas_volume is not None
        and latest_fill is not None
    )
    if have_inputs:
        avg_rate = net_flow(injection, withdrawal).rolling(7).mean().iloc[-1]
        if pd.notna(avg_rate):
            days, direction = days_to_full_or_empty(
                latest_fill, working_gas_volume, float(avg_rate)
            )
            if days is not None:
                extra_line = f"Days to {direction}: {days:.0f}"

    fig = _worm_chart(
        "agsi.EU.full_pct", "EU Gas Storage Fill % — Seasonal Range", extra_line
    )
    if fig is None:
        st.info("No EU data yet — run `pipelines/gie/pull_agsi.py`.")
        return
    st.plotly_chart(fig, use_container_width=True)
    kardamow_take(
        "Europe's storage is well behind its own median, and the current injection pace "
        "gets it full past 1 November — the date the market actually prices, which is why "
        "this chart is doing more for TTF than the flat price admits."
    )


def _small_multiples_section() -> None:
    cols = st.columns(3)
    for i, country in enumerate(SMALL_MULTIPLES_COUNTRIES):
        fig = _worm_chart(f"agsi.{country}.full_pct", f"{country} Fill %")
        with cols[i % 3]:
            if fig is None:
                st.info(f"No data yet for {country}.")
                continue
            fig.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
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

    net_injection = net_flow(injection, withdrawal)
    fig = dual_axis_chart(
        net_injection,
        send_out,
        title="EU Net Injection vs. ALSI Send-Out",
        left_label="Net injection (GWh/d)",
        right_label="LNG send-out (GWh/d)",
    )
    st.plotly_chart(fig, use_container_width=True)
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
    st.plotly_chart(bar, use_container_width=True)
    kardamow_take(
        "Rank the six by deviation from median and the split is geographic, not random — "
        "Poland and Italy near normal, Germany and the Netherlands the worst by 20-plus "
        "points — the shortfall concentrates in the countries that lean hardest on "
        "pipeline gas that isn't coming back."
    )


st.title("EU Gas Storage & LNG (GIE AGSI+/ALSI+)")

st.subheader("EU headline")
_eu_headline_section()

st.subheader("Country small multiples")
_small_multiples_section()

st.subheader("Net injection vs. LNG send-out")
_net_injection_vs_sendout_section()

st.subheader("Country deviation vs. seasonal median")
_country_deviation_section()
