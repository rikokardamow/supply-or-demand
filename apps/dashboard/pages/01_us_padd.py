"""US PADD — seasonal stocks, refining, inter-PADD flows, and the WPSR table."""

from __future__ import annotations

from datetime import UTC, datetime

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from components.kardamow_take import kardamow_take
from components.padd_map import render_padd_flow_map
from core.calendars import next_release
from core.seasonal import seasonal_stats
from core.storage import read_flows, read_ts_long
from core.theme import NAVY, RED, dual_axis_chart, seasonal_range_chart
from pipelines.eia.pull_wpsr import (
    GROSS_INPUTS,
    PRODUCT_SUPPLIED,
    STOCKS,
    UTILISATION,
    WEEKLY_IMPORTS,
)
from pipelines.eia.transforms import days_of_cover, net_balance, wpsr_summary

GROSS_INPUTS_BY_GEO = {
    "US": "WGIRIUS2",
    "PADD1": "WGIRIP12",
    "PADD2": "WGIRIP22",
    "PADD3": "WGIRIP32",
    "PADD4": "WGIRIP42",
    "PADD5": "WGIRIP52",
}
UTILISATION_BY_GEO = {
    "US": "WPULEUS3",
    "PADD1": "W_NA_YUP_R10_PER",
    "PADD2": "W_NA_YUP_R20_PER",
    "PADD3": "W_NA_YUP_R30_PER",
    "PADD4": "W_NA_YUP_R40_PER",
    "PADD5": "W_NA_YUP_R50_PER",
}

# Plain red/green for this table's up/down convention, distinct from core.theme's chart
# palette — CLAUDE.md's "no ad-hoc colours" rule governs charts, not this kind of
# tabular conditional formatting.
_POSITIVE_COLOUR = "#2e7d32"
_NEGATIVE_COLOUR = RED


def _seasonal_section(series_id: str, title: str, unit: str, take: str | None = None) -> None:
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
    if take is not None:
        kardamow_take(take)


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _sign_colour(value: float) -> str:
    if pd.isna(value):
        return ""
    colour = _POSITIVE_COLOUR if value >= 0 else _NEGATIVE_COLOUR
    return f"color: {colour}; font-weight: 600"


st.title("US PADD — Crude & Product Movements")

tab_stocks, tab_refining, tab_flows, tab_wpsr = st.tabs(["Stocks", "Refining", "Flows", "WPSR"])

with tab_stocks:
    with card("Cushing Crude Stocks"):
        _seasonal_section(
            "W_EPC0_SAX_YCUOK_MBBL",
            "Cushing Crude Stocks — Seasonal Range",
            " mb",
            take=(
                "Cushing is sitting 7,512 mb under its five-year median — the delivery point "
                "for WTI running this thin is what keeps the front-month structure bid "
                "whenever a barrel goes missing anywhere upstream."
            ),
        )
    with card("US Crude Stocks (ex-SPR)"):
        _seasonal_section(
            "WCESTUS1",
            "US Crude Stocks (ex-SPR) — Seasonal Range",
            " mb",
            take=(
                "US crude ex-SPR is basically sat on its own median, down just 1,863 mb — "
                "the rare series this cycle that isn't telling a scarcity story, which makes "
                "it the one chart the crude bulls can't point to."
            ),
        )
    with card("US Total Gasoline Stocks"):
        _seasonal_section(
            "WGTSTUS1",
            "US Total Gasoline Stocks — Seasonal Range",
            " mb",
            take=(
                "Gasoline is 16,912 mb under normal into the tail of driving season — that's "
                "demand pulling barrels out faster than refiners can replace them, and it's "
                "the crack spread's real justification, not the headline print."
            ),
        )
    with card("US Distillate Stocks"):
        _seasonal_section(
            "WDISTUS1",
            "US Distillate Stocks — Seasonal Range",
            " mb",
            take=(
                "Distillate is short its median by 20,504 mb with winter still to build into "
                "— this is the stock chart that decides whether Europe's heating-oil "
                "arbitrage stays open or closes the moment the first cold snap hits."
            ),
        )

with tab_refining:
    geo = st.selectbox("Region", options=list(GROSS_INPUTS_BY_GEO), index=0)

    gross_inputs = _series_by_ts(GROSS_INPUTS_BY_GEO[geo])
    utilisation = _series_by_ts(UTILISATION_BY_GEO[geo])

    if gross_inputs.empty or utilisation.empty:
        st.info(f"No refining data yet for {geo} — run `pipelines/eia/pull_wpsr.py`.")
    else:
        with card(f"{geo} Refinery Gross Inputs vs. Utilisation"):
            fig = dual_axis_chart(
                gross_inputs,
                utilisation,
                title=f"{geo} Refinery Gross Inputs vs. Utilisation",
                left_label="Gross inputs (Mbbl/d)",
                right_label="Utilisation (%)",
            )
            st.plotly_chart(fig, use_container_width=True)
            if geo == "US":
                kardamow_take(
                    "97.2% utilisation and gross inputs at 17,517 Mbbl/d — US refiners are "
                    "running flat out, which means the product-stock draws above aren't a "
                    "refining problem, they're a demand problem the system can't process "
                    "its way out of."
                )

with tab_flows:
    with card("Inter-PADD Crude Movements"):
        render_padd_flow_map()
        kardamow_take(
            "Pipeline moved 120,542 Mbbl of the latest month's inter-PADD barrel against a "
            "combined 16,000 for rail and barge — and 62,026 of that ran Midcontinent to "
            "the Gulf Coast alone, the corridor that decides whether PADD3 exports or "
            "PADD2 refines."
        )

    flows_df = read_flows(source="eia")
    if flows_df.empty:
        st.info("No flow data yet — run `pipelines/eia/pull_padd_flows.py`.")
    else:
        balance = net_balance(flows_df)
        latest_month = balance["ts"].max()
        latest_balance = balance[balance["ts"] == latest_month].sort_values("padd")

        bar = go.Figure(
            go.Bar(
                x=latest_balance["padd"],
                y=latest_balance["net_balance"],
                marker_color=[NAVY if v >= 0 else RED for v in latest_balance["net_balance"]],
            )
        )
        bar.update_layout(
            title=f"Net Inter-PADD Crude Balance — {pd.Timestamp(latest_month).strftime('%Y-%m')}",
            yaxis_title="Net receipts (Mbbl, +receiver / -sender)",
        )
        with card(f"Net Inter-PADD Crude Balance — {pd.Timestamp(latest_month):%Y-%m}"):
            st.plotly_chart(bar, use_container_width=True)
            kardamow_take(
                "The Gulf Coast pulled in a net 39,370 Mbbl in the latest month while the "
                "Rockies and Midcontinent gave up 26,737 and 24,628 between them — PADD3's "
                "export machine is still being fed by barrels that have nowhere else useful "
                "to go."
            )

with tab_wpsr:
    next_wpsr = next_release("wpsr", datetime.now(UTC))
    countdown = next_wpsr - datetime.now(UTC)
    hours_left = int(countdown.total_seconds() // 3600)
    with card("Next WPSR release"):
        st.metric(
            "Next WPSR release",
            next_wpsr.strftime("%a %Y-%m-%d %H:%M %Z"),
            f"in {hours_left} h",
        )

    all_series = STOCKS + UTILISATION + GROSS_INPUTS + PRODUCT_SUPPLIED + WEEKLY_IMPORTS
    wpsr_df = read_ts_long(series_ids=all_series)

    if wpsr_df.empty:
        st.info("No data yet — run `pipelines/eia/pull_wpsr.py`.")
    else:
        summary = wpsr_summary(wpsr_df).sort_values("series_id").reset_index(drop=True)
        styled = summary.style.map(_sign_colour, subset=["delta", "vs_median"]).format(
            {
                "latest_value": "{:,.1f}",
                "prior_value": "{:,.1f}",
                "delta": "{:+,.1f}",
                "vs_median": "{:+,.1f}",
            }
        )
        with card("WPSR Summary"):
            st.dataframe(styled, use_container_width=True)

    stocks = _series_by_ts("WCESTUS1")
    product_supplied = _series_by_ts("WRPUPUS2")
    if stocks.empty or product_supplied.empty:
        st.info("No data yet for days-of-cover — run `pipelines/eia/pull_wpsr.py`.")
    else:
        cover = days_of_cover(stocks, product_supplied).dropna()
        if not cover.empty:
            with card("US Crude Days of Cover"):
                st.metric("US crude days of cover", f"{cover.iloc[-1]:.1f} days")
