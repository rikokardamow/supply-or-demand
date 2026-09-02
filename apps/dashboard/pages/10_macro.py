"""Macro/FX Overlay (Spec 10, Session C): the four visuals from the spec's own
visualisation spec -- broad dollar vs. WTI, real-vs-nominal crude (indexed 2018=100),
energy-in-EUR-vs-USD small multiples, and an ESI heat-strip by country.

Visual 1 uses WTI directly from pipelines/macro (FRED) rather than a Spec-07-sourced
crude price -- Spec 07 (refinery cracks, needs a local IB Gateway) is still deferred,
and FRED's own WTI series (pulled since Session A) makes the spec's own "placeholder
until then" note moot: this is real data, not a placeholder."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from core.macro import deflate, index_to, to_currency
from core.storage import read_ts_long
from core.theme import LIGHT_BLUE, NAVY, category_time_heatmap, dual_axis_chart

INDEX_BASE_PERIOD = "2018-01-01"
RANGE_DAYS = {"1Y": 365, "3Y": 1095, "5Y": 1825, "10Y": 3650, "All": None}

ENERGY_SMALL_MULTIPLES = [
    ("fred.dcoilwtico", "WTI Crude", "$/bbl"),
    ("fred.dcoilbrenteu", "Brent Crude", "$/bbl"),
    ("fred.dhhngsp", "Henry Hub Gas", "$/MMBtu"),
]
ESI_GEOS = ["EU", "DE", "FR", "IT", "ES", "IE"]


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _trim_recent(series: pd.Series, days: int | None) -> pd.Series:
    if days is None or series.empty:
        return series
    cutoff = series.index.max() - pd.Timedelta(days=days)
    result: pd.Series = series[series.index >= cutoff]
    return result


def _dollar_vs_wti_section(days: int | None) -> None:
    dollar = _trim_recent(_series_by_ts("fred.dtwexbgs"), days)
    wti = _trim_recent(_series_by_ts("fred.dcoilwtico"), days)
    if dollar.empty or wti.empty:
        st.info("No data yet — run `pipelines/macro/pull_macro.py`.")
        return

    title = "Broad USD Index vs. WTI Crude"
    fig = dual_axis_chart(
        dollar,
        wti,
        title=title,
        left_label="Broad USD Index (Jan 2006=100)",
        right_label="WTI ($/bbl)",
    )
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        kardamow_take(
            "A stronger dollar is a headwind for dollar-priced crude almost "
            "mechanically — this is the chart that separates a real demand story "
            "from a currency one before either gets treated as the explanation."
        )


def _real_vs_nominal_section(days: int | None) -> None:
    wti = _series_by_ts("fred.dcoilwtico")
    cpi = _series_by_ts("fred.cpiaucsl")
    if wti.empty or cpi.empty:
        st.info("No data yet — run `pipelines/macro/pull_macro.py`.")
        return

    real_wti = deflate(wti, cpi, base_period=INDEX_BASE_PERIOD)
    nominal_indexed = _trim_recent(index_to(wti, base_period=INDEX_BASE_PERIOD), days)
    real_indexed = _trim_recent(index_to(real_wti, base_period=INDEX_BASE_PERIOD), days)

    title = "WTI Crude — Real vs. Nominal (2018=100)"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=nominal_indexed.index,
            y=nominal_indexed.values,
            name="Nominal",
            line={"color": NAVY, "width": 2},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=real_indexed.index,
            y=real_indexed.values,
            name="Real (CPI-adjusted)",
            line={"color": LIGHT_BLUE, "width": 2},
        )
    )
    fig.update_layout(title=title, yaxis_title="Index (2018=100)")
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        kardamow_take(
            "The gap between these two lines is pure inflation — whatever's left "
            "once it's closed is the actual real-terms move oil has made since 2018."
        )


def _energy_small_multiples_section(days: int | None) -> None:
    fx_eur = _series_by_ts("fx.usd_eur")
    if fx_eur.empty:
        st.info("No FX data yet — run `pipelines/macro/pull_macro.py`.")
        return

    cols = st.columns(len(ENERGY_SMALL_MULTIPLES))
    for i, (series_id, label, unit) in enumerate(ENERGY_SMALL_MULTIPLES):
        usd = _series_by_ts(series_id)
        if usd.empty:
            with cols[i]:
                st.info(f"No data yet for {label}.")
            continue

        eur = to_currency(usd, fx_eur, target="EUR")
        usd_trimmed = _trim_recent(usd, days)
        eur_trimmed = _trim_recent(eur, days)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=usd_trimmed.index,
                y=usd_trimmed.values,
                name="USD",
                line={"color": NAVY, "width": 1.5},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=eur_trimmed.index,
                y=eur_trimmed.values,
                name="EUR",
                line={"color": LIGHT_BLUE, "width": 1.5},
            )
        )
        fig.update_layout(title=f"{label} ({unit})", showlegend=True)
        with cols[i], card(label):
            st.plotly_chart(fig, use_container_width=True)


def _esi_heat_strip_section() -> None:
    frames = []
    for geo in ESI_GEOS:
        series = _series_by_ts(f"estat.esi.{geo}").tail(36)  # last 3 years, monthly
        if series.empty:
            continue
        frames.append(series.rename(geo))

    if not frames:
        st.info("No ESI data yet — run `pipelines/macro/pull_macro.py`.")
        return

    wide = pd.concat(frames, axis=1).T
    wide.columns = [pd.Timestamp(c).strftime("%Y-%m") for c in wide.columns]

    title = "Economic Sentiment Indicator — Heat-Strip"
    fig = category_time_heatmap(wide, title=title, unit="ESI (100=long-run avg)")
    with card(title):
        st.plotly_chart(fig, use_container_width=True)
        kardamow_take(
            "Sentiment leads hard data by a quarter or two more often than not — a "
            "country cooling off here is worth watching before it shows up in "
            "industrial production or demand numbers."
        )


st.title("Macro & FX")

range_label = st.segmented_control(
    "Time range", options=list(RANGE_DAYS), default="5Y", required=True, key="macro_range"
)
days = RANGE_DAYS[range_label]

st.subheader("Dollar vs. crude")
_dollar_vs_wti_section(days)

st.subheader("Real vs. nominal crude")
_real_vs_nominal_section(days)

st.subheader("Energy prices, USD vs. EUR")
_energy_small_multiples_section(days)

st.subheader("Economic sentiment by country")
_esi_heat_strip_section()
