"""US PADD — seasonal stocks, refining, inter-PADD flows, and the WPSR table."""

from __future__ import annotations

import numbers
from datetime import UTC, datetime

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.event_overlay import add_event_markers
from components.kardamow_take import kardamow_take
from components.lake import read_flows, read_ts_long
from components.padd_map import render_padd_flow_map
from components.section import empty_state, page_header, section, source_note
from core.calendars import next_release
from core.seasonal import current_track, seasonal_stats
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

REFINING_RANGE_DAYS = {"3M": 90, "6M": 182, "1Y": 365, "2Y": 730, "5Y": 1825, "All": None}

STOCKS_INFO = [
    (
        "W_EPC0_SAX_YCUOK_MBBL",
        "Cushing Crude Stocks",
        " mb",
        (
            "Cushing is sitting 7,512 mb under its five-year median — the delivery point "
            "for WTI running this thin is what keeps the front-month structure bid "
            "whenever a barrel goes missing anywhere upstream."
        ),
    ),
    (
        "WCESTUS1",
        "US Crude Stocks (ex-SPR)",
        " mb",
        (
            "US crude ex-SPR is basically sat on its own median, down just 1,863 mb — "
            "the rare series this cycle that isn't telling a scarcity story, which makes "
            "it the one chart the crude bulls can't point to."
        ),
    ),
    (
        "WGTSTUS1",
        "US Total Gasoline Stocks",
        " mb",
        (
            "Gasoline is 16,912 mb under normal into the tail of driving season — that's "
            "demand pulling barrels out faster than refiners can replace them, and it's "
            "the crack spread's real justification, not the headline print."
        ),
    ),
    (
        "WDISTUS1",
        "US Distillate Stocks",
        " mb",
        (
            "Distillate is short its median by 20,504 mb with winter still to build into "
            "— this is the stock chart that decides whether Europe's heating-oil "
            "arbitrage stays open or closes the moment the first cold snap hits."
        ),
    ),
]

# Plain red/green for this table's up/down convention, distinct from core.theme's chart
# palette — NOTES.md's "no ad-hoc colours" rule governs charts, not this kind of
# tabular conditional formatting.
_POSITIVE_COLOUR = "#2e7d32"
_NEGATIVE_COLOUR = RED


def _seasonal_section(series_id: str, unit: str, take: str | None = None) -> None:
    df = read_ts_long(series_ids=[series_id])
    if df.empty:
        empty_state("eia", "weekly", None)
        st.caption(f"Run `pipelines/eia/pull_wpsr.py` to populate {series_id}.")
        return

    stats = seasonal_stats(df, value_col="value")
    current_year_series = current_track(df)

    fig = seasonal_range_chart(stats, current_year_series, unit=unit)
    add_event_markers(fig, commodity="crude", x_axis="doy")
    st.plotly_chart(fig)
    source_note(f"Source: EIA WPSR — unit: {unit.strip()}")
    if take is not None:
        kardamow_take(take)


def _series_by_ts(series_id: str) -> pd.Series:
    df = read_ts_long(series_ids=[series_id]).sort_values("ts")
    return df.set_index("ts")["value"]


def _latest_value(series_id: str) -> float | None:
    series = _series_by_ts(series_id)
    return float(series.iloc[-1]) if not series.empty else None


def _stocks_filter_panel() -> list[tuple[str, str, str, str]]:
    """Collapsible filter panel (accordion + checkboxes + live latest-value counts),
    the pattern from warwatch.ch's filter groups -- see 02_gas_storage.py's
    _country_filter_panel for the same convention."""
    for series_id, _label, _unit, _take in STOCKS_INFO:
        st.session_state.setdefault(f"padd_stocks_filter_{series_id}", True)
    selected_count = sum(
        st.session_state[f"padd_stocks_filter_{sid}"] for sid, _, _, _ in STOCKS_INFO
    )

    with st.expander(f"Filter stock series ({selected_count} of {len(STOCKS_INFO)} shown)"):
        filter_cols = st.columns(2)
        for i, (series_id, label, unit, _take) in enumerate(STOCKS_INFO):
            latest = _latest_value(series_id)
            checkbox_label = f"{label} — {latest:,.0f}{unit}" if latest is not None else label
            with filter_cols[i % 2]:
                st.checkbox(checkbox_label, key=f"padd_stocks_filter_{series_id}")

    return [item for item in STOCKS_INFO if st.session_state[f"padd_stocks_filter_{item[0]}"]]


def _sign_colour(value: object) -> str:
    """`object`, not `float`: Styler.map applies this to every cell in the subset,
    and types the argument as the full scalar union pandas may hold rather than the
    float this particular column happens to carry. `numbers.Real`, not
    `(int, float)`: numpy registers its scalar types with the numbers ABCs, but
    `isinstance(np.int64(1), int)` is False, so an integer-typed column would
    silently lose its colouring."""
    if not isinstance(value, numbers.Real):
        return ""
    number = float(value)
    if pd.isna(number):
        return ""
    colour = _POSITIVE_COLOUR if number >= 0 else _NEGATIVE_COLOUR
    return f"color: {colour}; font-weight: 600"


next_wpsr = next_release("wpsr", datetime.now(UTC))

page_header(
    "US PADD — Crude & Product Movements",
    as_of=f"NEXT WPSR {next_wpsr.strftime('%d %b %H:%M ET').upper()}",
)

tab_stocks, tab_refining, tab_flows, tab_wpsr = st.tabs(["Stocks", "Refining", "Flows", "WPSR"])

with tab_stocks:
    selected_stocks = _stocks_filter_panel()
    if not selected_stocks:
        st.info("No series selected — check at least one above.")
    else:
        stock_cols = st.columns(2)
        for i, (series_id, label, unit, take) in enumerate(selected_stocks):
            with stock_cols[i % 2], section(f"{label} — Seasonal Range"):
                _seasonal_section(series_id, unit, take=take)

with tab_refining:
    geo = st.selectbox("Region", options=list(GROSS_INPUTS_BY_GEO), index=0)

    gross_inputs = _series_by_ts(GROSS_INPUTS_BY_GEO[geo])
    utilisation = _series_by_ts(UTILISATION_BY_GEO[geo])

    if gross_inputs.empty or utilisation.empty:
        empty_state("eia", "weekly", None)
        st.caption(f"Run `pipelines/eia/pull_wpsr.py` to populate refining data for {geo}.")
    else:
        time_range = st.segmented_control(
            "Time range",
            options=list(REFINING_RANGE_DAYS),
            default="2Y",
            required=True,
            key="padd_refining_range",
        )
        days = REFINING_RANGE_DAYS[time_range]
        if days is not None:
            cutoff = gross_inputs.index.max() - pd.Timedelta(days=days)
            gross_inputs = gross_inputs[gross_inputs.index >= cutoff]
            utilisation = utilisation[utilisation.index >= cutoff]

        with section(f"{geo} Refinery Gross Inputs vs. Utilisation"):
            fig = dual_axis_chart(
                gross_inputs,
                utilisation,
                left_label="Gross inputs (Mbbl/d)",
                right_label="Utilisation (%)",
            )
            st.plotly_chart(fig)
            if geo == "US":
                kardamow_take(
                    "97.2% utilisation and gross inputs at 17,517 Mbbl/d — US refiners are "
                    "running flat out, which means the product-stock draws above aren't a "
                    "refining problem, they're a demand problem the system can't process "
                    "its way out of."
                )

with tab_flows:
    with section("Inter-PADD Crude Movements"):
        render_padd_flow_map()
        kardamow_take(
            "Pipeline moved 120,542 Mbbl of the latest month's inter-PADD barrel against a "
            "combined 16,000 for rail and barge — and 62,026 of that ran Midcontinent to "
            "the Gulf Coast alone, the corridor that decides whether PADD3 exports or "
            "PADD2 refines."
        )

    flows_df = read_flows(source="eia")
    if flows_df.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_padd_flows.py` to populate flow data.")
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
            yaxis_title="Net receipts (Mbbl, +receiver / -sender)",
        )
        with section(f"Net Inter-PADD Crude Balance — {pd.Timestamp(latest_month):%Y-%m}"):
            st.plotly_chart(bar)
            kardamow_take(
                "The Gulf Coast pulled in a net 39,370 Mbbl in the latest month while the "
                "Rockies and Midcontinent gave up 26,737 and 24,628 between them — PADD3's "
                "export machine is still being fed by barrels that have nowhere else useful "
                "to go."
            )

with tab_wpsr:
    countdown = next_wpsr - datetime.now(UTC)
    hours_left = int(countdown.total_seconds() // 3600)
    with section("Next WPSR release"):
        st.metric(
            "Next WPSR release",
            next_wpsr.strftime("%a %Y-%m-%d %H:%M %Z"),
            f"in {hours_left} h",
        )

    all_series = STOCKS + UTILISATION + GROSS_INPUTS + PRODUCT_SUPPLIED + WEEKLY_IMPORTS
    wpsr_df = read_ts_long(series_ids=all_series)

    if wpsr_df.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_wpsr.py` to populate this table.")
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
        with section("WPSR Summary"):
            st.dataframe(styled)

    stocks = _series_by_ts("WCESTUS1")
    product_supplied = _series_by_ts("WRPUPUS2")
    if stocks.empty or product_supplied.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_wpsr.py` to populate days-of-cover data.")
    else:
        cover = days_of_cover(stocks, product_supplied).dropna()
        if not cover.empty:
            with section("US Crude Days of Cover"):
                st.metric("US crude days of cover", f"{cover.iloc[-1]:.1f} days")
