"""Spec 19 -- Fundamentals & Physical Market. Inventory deviation, spare capacity,
quality mismatch, Carollo diagnostic, shale response, CFTC positioning, benchmark
health, OSP signal.

Real, confirmed-live gap (Session C, checked via core.storage.read_ts_long() against
the actual lake): most cards are genuinely un-renderable against real data today --
IEA/EIA S&D balance, spare capacity, quality differentials, Saudi OSPs and
benchmark-health counts are all manual-drop-only (pipelines/manual_physical, no real
CSV exists yet); shale_response needs a real futures curve (Spec 18 has none yet) and
no Spec 06 Drilling Productivity Report pipeline exists either. Every such card renders
a real st.info(...) no-data message instead of a chart, per
specs/TRADING_LAYER_RUNBOOK.md's own "render NO-DATA, never fabricate" rule. Real
cards: inventory deviation + days-of-cover (WCESTUS1/WGIRIUS2, Spec 01), the Carollo
scatter (WCESTUS1 vs fred.dcoilbrenteu, verified live in Session B), refinery
utilisation (WPULEUS3, Spec 01), and CFTC managed-money positioning
(derived.cot.<root>.mm_pct_3y, this spec's own Session A)."""

from __future__ import annotations

import core.theme  # noqa: F401
import pandas as pd
import streamlit as st
from components.card import card
from core.fundamentals import (
    carollo_scatter,
    days_of_cover,
    inventory_deviation,
    osp_signal,
)
from core.seasonal import REFERENCE_YEAR, seasonal_stats
from core.storage import read_ts_long
from core.theme import RED, seasonal_range_chart, sign_agreement_scatter, simple_time_series_chart
from pipelines.cftc.client import CONTRACT_CODES
from pipelines.manual_physical.reader import read_physical_csvs

US_CRUDE_STOCKS_SERIES_ID = "WCESTUS1"
US_REFINERY_INPUTS_SERIES_ID = "WGIRIUS2"
US_REFINERY_UTILISATION_SERIES_ID = "WPULEUS3"
BRENT_SERIES_ID = "fred.dcoilbrenteu"

st.title("Fundamentals & Physical Market")

tab_sd, tab_inventory, tab_quality, tab_shale_cot, tab_benchmark = st.tabs(
    ["S&D & Spare Capacity", "Inventory", "Quality & Refining", "Shale & COT", "Benchmark & OSP"]
)

with tab_sd, card("Supply & Demand Balance (IEA / EIA / OPEC)"):
    st.info(
        "No real IEA/EIA supply-demand balance data exists yet -- OPEC's own MOMR "
        "demand_balance series are real (Spec 06), but a 3-way agency comparison with "
        "2 of 3 agencies missing would misrepresent the point of this chart (agency "
        "disagreement), so it stays a clean no-data state rather than a lone OPEC bar."
    )
    st.caption(
        "Source: momr.demand_balance.* (real, Spec 06) + IEA OMR / EIA STEO S&D "
        "balance (missing -- distinct from their spare-capacity series below)."
    )

with tab_sd, card("Spare Capacity (inverted) vs Brent"):
    st.info(
        "No manual EIA STEO / IEA OMR spare-capacity drop yet -- add "
        "data/manual/physical/*.csv and run `pipelines/manual_physical/reader.py` "
        "(see pipelines/manual_physical/CLAUDE.md)."
    )
    st.caption(
        "Source: manual.eia_steo.spare_capacity / manual.iea_omr.spare_capacity (missing)."
    )

with tab_inventory:
    stocks_df = read_ts_long(series_ids=[US_CRUDE_STOCKS_SERIES_ID])
    with card("US Crude Stocks -- Seasonal Range"):
        if stocks_df.empty:
            st.info(
                f"No data yet for {US_CRUDE_STOCKS_SERIES_ID} -- run pipelines/eia/pull_wpsr.py."
            )
        else:
            stats = seasonal_stats(stocks_df[["ts", "value"]], value_col="value")
            current_year = stocks_df["ts"].dt.year.max()
            current = stocks_df[stocks_df["ts"].dt.year == current_year].sort_values("ts")
            reference_doy = current["ts"].map(lambda d: d.replace(year=REFERENCE_YEAR)).dt.dayofyear
            current_year_series = current.set_index(reference_doy)["value"]

            fig = seasonal_range_chart(
                stats, current_year_series, title="US Crude Stocks (ex-SPR)", unit=" mb"
            )
            st.plotly_chart(fig)

            deviation = inventory_deviation(stocks_df[["ts", "value"]])
            latest_dev_z = deviation["dev_z"].dropna()
            if not latest_dev_z.empty:
                st.metric("Latest deviation z-score (ex-2020)", f"{latest_dev_z.iloc[-1]:+.2f}")
            st.caption(
                f"Source: {US_CRUDE_STOCKS_SERIES_ID} (Spec 01), "
                "2020 excluded from the seasonal band."
            )

    with card("Days of Cover"):
        inputs_df = read_ts_long(series_ids=[US_REFINERY_INPUTS_SERIES_ID])
        if stocks_df.empty or inputs_df.empty:
            st.info(
                f"No data yet for {US_CRUDE_STOCKS_SERIES_ID} or "
                f"{US_REFINERY_INPUTS_SERIES_ID} -- run pipelines/eia/pull_wpsr.py."
            )
        else:
            merged = pd.merge(
                stocks_df[["ts", "value"]],
                inputs_df[["ts", "value"]],
                on="ts",
                suffixes=("_stocks", "_inputs"),
            ).sort_values("ts")
            cover = days_of_cover(merged["value_stocks"], merged["value_inputs"]).dropna()
            if not cover.empty:
                st.metric("US crude days of cover", f"{cover.iloc[-1]:.1f} days")
            st.caption(
                f"Source: {US_CRUDE_STOCKS_SERIES_ID} / {US_REFINERY_INPUTS_SERIES_ID} (Spec 01)."
            )

with tab_quality:
    with card("Carollo Stock-Change vs Price-Change Diagnostic"):
        stocks = (
            read_ts_long(series_ids=[US_CRUDE_STOCKS_SERIES_ID])
            .set_index("ts")["value"].sort_index()
        )
        brent = read_ts_long(series_ids=[BRENT_SERIES_ID]).set_index("ts")["value"].sort_index()
        if stocks.empty or brent.empty:
            st.info(
                "No data yet -- run pipelines/eia/pull_wpsr.py and pipelines/macro (FRED Brent)."
            )
        else:
            delta_stocks_q = stocks.resample("QE").last().diff()
            delta_brent_q = brent.resample("QE").last().diff()
            result = carollo_scatter(delta_stocks_q, delta_brent_q)

            fig = sign_agreement_scatter(
                delta_stocks_q,
                delta_brent_q,
                title="US Crude Stock Changes vs Brent Price Changes (Quarterly)",
                x_label="Δ US crude stocks (quarterly)",
                y_label="Δ Brent (quarterly, USD)",
            )
            st.plotly_chart(fig)
            st.caption(
                f"Source: {US_CRUDE_STOCKS_SERIES_ID} x {BRENT_SERIES_ID}, quarterly changes. "
                f"R²={result['r2']:.4f}, {result['share_wrong_sign'] * 100:.1f}% of quarters "
                f"violate the classical model (n={int(result['n'])})."
            )

    with card("Refinery Utilisation"):
        util_df = read_ts_long(series_ids=[US_REFINERY_UTILISATION_SERIES_ID])
        if util_df.empty:
            st.info(
                f"No data yet for {US_REFINERY_UTILISATION_SERIES_ID} -- "
                "run pipelines/eia/pull_wpsr.py."
            )
        else:
            series = util_df.set_index("ts")["value"].sort_index()
            fig = simple_time_series_chart(series, title="US Refinery Utilisation", unit="%")
            st.plotly_chart(fig)
            st.caption(f"Source: {US_REFINERY_UTILISATION_SERIES_ID} (Spec 01).")

    with card("Refining Constraint Index"):
        st.info(
            "No manual complex-simple margin spread / light-heavy differential data yet -- "
            "both are required alongside utilisation for this index (see "
            "pipelines/manual_physical/CLAUDE.md)."
        )
        st.caption(
            f"Source: manual.argus.* differentials (missing) + "
            f"{US_REFINERY_UTILISATION_SERIES_ID} utilisation "
            "(real, unused without the other two legs)."
        )

with tab_shale_cot:
    with card("Shale Rig Response to Forward WTI"):
        st.info(
            "No real 12-month-forward WTI price exists yet (Spec 18's futures pipeline has "
            "no real settlement data) and no Spec 06 Drilling Productivity Report pipeline "
            "exists for basin production -- both required for this card."
        )
        st.caption(
            "Source: bh.rigs.united_states.oil (real) x fut.cl.f12.settle (missing) + "
            "a Drilling Productivity Report pipeline (missing)."
        )

    with card("CFTC Managed-Money Positioning"):
        root = st.selectbox("Root", options=list(CONTRACT_CODES), key="fundamentals_cot_root")
        cot_df = read_ts_long(series_ids=[f"derived.cot.{root}.mm_pct_3y"])
        if cot_df.empty:
            st.info(
                f"No CFTC data yet for {root} -- run pipelines/cftc/pull_history.py and "
                "pipelines/derived/fundamentals.py."
            )
        else:
            series = cot_df.set_index("ts")["value"].sort_index()
            fig = simple_time_series_chart(
                series,
                title=f"{root.upper()} Managed-Money Net Length (% OI, 3y percentile rank)",
                unit="percentile",
            )
            fig.add_hline(y=0.95, line_dash="dash", line_color=RED)
            fig.add_hline(y=0.05, line_dash="dash", line_color=RED)
            st.plotly_chart(fig)
            st.caption(
                f"Source: derived.cot.{root}.mm_pct_3y (real, pipelines/cftc + "
                "pipelines/derived/fundamentals.py)."
            )

with tab_benchmark:
    physical_df = read_physical_csvs()

    with card("Benchmark Health (Window Trades / Partials / Midland Share)"):
        required = {
            "manual.platts.dated_brent_window_trades",
            "manual.platts.dubai_partials",
            "manual.argus.wti_midland_share_bfoet",
        }
        available = set(physical_df["series_id"]) if not physical_df.empty else set()
        if not required.issubset(available):
            st.info(
                "No manual Platts/Argus benchmark-health drop yet -- add "
                "data/manual/physical/*.csv and run `pipelines/manual_physical/reader.py`."
            )
        else:
            window_trades = (
                physical_df[physical_df["series_id"] == "manual.platts.dated_brent_window_trades"]
                .set_index("date")["value"].sort_index()
            )
            st.line_chart(window_trades)
            st.caption(
                "Source: manual.platts.dated_brent_window_trades / dubai_partials / "
                "manual.argus.wti_midland_share_bfoet (pipelines/manual_physical)."
            )

    with card("OSP vs Dubai M1-M3 Structure"):
        required = {
            "manual.saudi_aramco.osp_arab_light_asia",
            "manual.platts.dubai_m1",
            "manual.platts.dubai_m3",
        }
        available = set(physical_df["series_id"]) if not physical_df.empty else set()
        if not required.issubset(available):
            st.info(
                "No manual Saudi Aramco OSP / Platts Dubai structure drop yet -- add "
                "data/manual/physical/*.csv and run `pipelines/manual_physical/reader.py`."
            )
        else:
            osp_asia = (
                physical_df[physical_df["series_id"] == "manual.saudi_aramco.osp_arab_light_asia"]
                .set_index("date")["value"].sort_index()
            )
            dubai_m1 = (
                physical_df[physical_df["series_id"] == "manual.platts.dubai_m1"]
                .set_index("date")["value"].sort_index()
            )
            dubai_m3 = (
                physical_df[physical_df["series_id"] == "manual.platts.dubai_m3"]
                .set_index("date")["value"].sort_index()
            )
            dubai_structure = pd.DataFrame({"m1": dubai_m1, "m3": dubai_m3}).dropna()
            dubai_m1_m3 = dubai_structure["m1"] - dubai_structure["m3"]

            result = osp_signal(osp_asia, dubai_m1_m3)
            st.dataframe(result)
            divergence_count = int(result["divergence"].sum())
            st.metric("Divergence months (OSP up, Dubai structure weakening)", divergence_count)
            st.caption(
                "Source: manual.saudi_aramco.osp_arab_light_asia x manual.platts.dubai_m1/"
                "dubai_m3 (pipelines/manual_physical)."
            )
