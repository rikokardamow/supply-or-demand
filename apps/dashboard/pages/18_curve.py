"""Spec 18 -- Curve & Market Structure. Roll-adjusted curve, spreads, convexity/regime,
Cushing-utilisation coupling, the GSCI/BCOM index-roll calendar, and physical
differentials.

Real, confirmed-live gap (Session D, checked via core.storage.read_ts_long() against the
actual lake): zero rows exist anywhere under fut.*/derived.spread.*/derived.curve.* -- no
real futures settlement data has ever been dropped (no IBKR Gateway running, no manual CSV
supplied yet). Every root-dependent card below renders a real st.info(...) no-data message
instead of a chart, per specs/TRADING_LAYER_RUNBOOK.md's own "render NO-DATA, never
fabricate" rule. Cushing utilisation, the roll calendar table, and "days to next roll" ARE
real -- none of them depend on futures settlement data at all."""

from __future__ import annotations

from datetime import date

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.card import card
from core.calendars import next_roll_window, roll_calendar
from core.curve import (
    REGIME_CODES,
    convexity,
    curve_regime,
    nearby_panel,
    physical_bands,
    roll_window_offset_grid,
    time_spreads,
    transition_matrix,
)
from core.storage import read_ts_long
from core.theme import (
    GREY,
    NAVY,
    RED,
    bday_heatmap,
    curve_strip_chart,
    dual_axis_chart,
    regime_ribbon_chart,
    scatter_piecewise_fit_chart,
)
from pipelines.derived.curve import contract_panel_for
from pipelines.futures.client import ROOTS
from pipelines.futures.series_meta import read_series_meta
from pipelines.manual_physical.reader import read_physical_csvs

st.title("Curve & Market Structure")

root = st.selectbox("Root", options=ROOTS)
as_of = st.date_input("As of", value=date.today())
storage_cost = st.number_input("Storage cost (M1-M2)", value=0.60, step=0.05)

today = date.today()
next_gsci = next_roll_window("gsci", today)
next_bcom = next_roll_window("bcom", today)
next_roll = min(next_gsci, next_bcom)
st.metric(
    "Days to next index roll (GSCI/BCOM)",
    (next_roll - today).days,
    help=f"GSCI: {next_gsci}, BCOM: {next_bcom}",
)

meta = read_series_meta()
contract_panel, expiries = contract_panel_for(root, meta)
has_curve_data = not contract_panel.empty and len(expiries) >= 2


def _no_futures_data_message() -> None:
    st.info(
        f"No settlement data yet for {root} -- run `pipelines/futures/pull_daily.py` once "
        "FUTURES_SOURCE has real data (see pipelines/futures/NOTES.md)."
    )


tab_curve, tab_spreads, tab_convexity, tab_storage, tab_roll_cal, tab_physical = st.tabs(
    ["Curve", "Spreads", "Convexity & Regime", "Storage", "Roll Calendar", "Physical"]
)

with tab_curve, card(f"{root.upper()} Curve Strip"):
    if not has_curve_data:
        _no_futures_data_message()
    else:
        _, unadj, _ = nearby_panel(contract_panel, expiries)
        offsets = {"Today": 0, "-5bd": 5, "-20bd": 20, "-252bd": 252}
        curves = {}
        for label, n in offsets.items():
            loc = len(unadj.index) - 1 - n
            if loc >= 0:
                curves[label] = unadj.iloc[loc].dropna()
        spreads_today = time_spreads(unadj).iloc[-1]
        spread_bars = {
            k: float(spreads_today[k])
            for k in ("s12", "s13", "s16", "s1_12")
            if pd.notna(spreads_today[k])
        }
        fig = curve_strip_chart(
            curves, spread_bars, title=f"{root.upper()} Curve Strip", unit="USD"
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Source: fut.{root}.*.settle (pipelines/futures), unadjusted ranks.")

with tab_spreads, card(f"{root.upper()} s12 Spread History"):
    if not has_curve_data:
        _no_futures_data_message()
    else:
        _, unadj, _ = nearby_panel(contract_panel, expiries)
        s12 = time_spreads(unadj)["s12"].dropna()
        mean = s12.rolling(252, min_periods=20).mean()
        std = s12.rolling(252, min_periods=20).std()

        fig = go.Figure()
        for band_mult, opacity in ((2, 0.15), (1, 0.25)):
            upper = mean + band_mult * std
            lower = mean - band_mult * std
            fig.add_trace(
                go.Scatter(
                    x=upper.index, y=upper.values, line={"width": 0}, showlegend=False,
                    hoverinfo="skip",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=lower.index, y=lower.values, line={"width": 0},
                    fill="tonexty", fillcolor=f"rgba(150,150,150,{opacity})",
                    name=f"+/-{band_mult} stdev (252d)", hoverinfo="skip",
                )
            )
        fig.add_trace(
            go.Scatter(x=s12.index, y=s12.values, line={"color": NAVY, "width": 2}, name="s12")
        )
        fig.add_hline(y=0, line_dash="dash", line_color=GREY)
        fig.update_layout(title=f"{root.upper()} s12 (f01-f02)", yaxis_title="USD")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Source: derived.spread.{root}.s12 (pipelines/derived/curve.py).")

with tab_convexity:
    with card(f"{root.upper()} Convexity"):
        if not has_curve_data:
            _no_futures_data_message()
        else:
            _, unadj, _ = nearby_panel(contract_panel, expiries)
            cv = convexity(unadj).dropna()
            p05 = cv.rolling(252, min_periods=20).quantile(0.05)
            p95 = cv.rolling(252, min_periods=20).quantile(0.95)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=cv.index, y=cv.values, line={"color": NAVY}, name="cv123"))
            fig.add_trace(
                go.Scatter(
                    x=p05.index, y=p05.values, line={"color": GREY, "dash": "dot"}, name="5th pct"
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=p95.index, y=p95.values, line={"color": GREY, "dash": "dot"}, name="95th pct"
                )
            )
            fig.add_hline(y=0, line_dash="dash", line_color=GREY)
            fig.update_layout(title=f"{root.upper()} Convexity (cv123)", yaxis_title="USD")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Source: derived.curve.{root}.cv123.")

    with card(f"{root.upper()} Regime"):
        if not has_curve_data:
            _no_futures_data_message()
        else:
            _, unadj, _ = nearby_panel(contract_panel, expiries)
            regime = curve_regime(unadj, storage_cost_m1m2=storage_cost)
            state_codes = regime["state"].map(REGIME_CODES)
            state_labels = {code: name for name, code in REGIME_CODES.items()}

            fig = regime_ribbon_chart(
                unadj["f01"], state_codes, state_labels,
                title=f"{root.upper()} Price & Regime", unit="USD",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Source: derived.curve.{root}.regime (states: {', '.join(REGIME_CODES)}).")

            st.dataframe(transition_matrix(regime["state"]), use_container_width=True)

with tab_storage:
    util_df = read_ts_long(series_ids=["derived.cushing.util", "derived.cushing.util_decile"])

    with card("Cushing Utilisation"):
        if util_df.empty:
            st.info("No data yet -- run `pipelines/derived/cushing.py`.")
        else:
            util = (
                util_df[util_df["series_id"] == "derived.cushing.util"]
                .set_index("ts")["value"].sort_index()
            )
            decile = (
                util_df[util_df["series_id"] == "derived.cushing.util_decile"]
                .set_index("ts")["value"].sort_index()
            )
            fig = dual_axis_chart(
                util, decile, title="Cushing Utilisation vs Decile Rank",
                left_label="Utilisation", right_label="Decile (1-10)",
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Source: derived.cushing.util / util_decile (EIA Cushing weekly stocks + "
                "EIA's now-discontinued capacity report, forward-filled past 2024-03-01)."
            )

    with card("Cushing Utilisation vs WTI s12"):
        cl_panel, cl_expiries = contract_panel_for("cl", meta)
        has_cl_data = not cl_panel.empty and len(cl_expiries) >= 2
        if util_df.empty or not has_cl_data:
            st.info(
                "No cl settlement data yet -- run `pipelines/futures/pull_daily.py` "
                "(FUTURES_SOURCE=manual/ibkr) to enable this scatter."
            )
        else:
            util = (
                util_df[util_df["series_id"] == "derived.cushing.util"]
                .set_index("ts")["value"].sort_index()
            )
            _, cl_unadj, _ = nearby_panel(cl_panel, cl_expiries)
            cl_s12 = time_spreads(cl_unadj)["s12"]
            merged = pd.DataFrame({"util": util, "s12": cl_s12}).dropna()

            annotations = []
            april_2020 = merged[merged.index.to_series().between("2020-04-01", "2020-04-30")]
            if not april_2020.empty:
                row = april_2020.iloc[0]
                annotations.append((float(row["util"]), float(row["s12"]), "Apr 2020"))

            fig = scatter_piecewise_fit_chart(
                merged["util"], merged["s12"], merged.index.year,
                bins=[(0.0, 0.35), (0.35, 0.75), (0.75, 1.01)],
                title="Cushing Utilisation vs WTI s12", x_label="Utilisation", y_label="s12 (USD)",
                annotations=annotations or None,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Source: derived.cushing.util x derived.spread.cl.s12.")

with tab_roll_cal:
    with card("GSCI / BCOM Roll Calendar"):
        gsci_cal = roll_calendar(as_of.year, "gsci").assign(index="GSCI")
        bcom_cal = roll_calendar(as_of.year, "bcom").assign(index="BCOM")
        combined = pd.concat([gsci_cal, bcom_cal]).sort_values("date").reset_index(drop=True)
        st.dataframe(combined, use_container_width=True)
        st.caption(
            "Source: core.calendars.roll_calendar -- real calendar arithmetic, no lake dependency."
        )

    with card(f"{root.upper()} Δs12 Around GSCI Roll Windows"):
        if not has_curve_data:
            _no_futures_data_message()
        else:
            _, unadj, _ = nearby_panel(contract_panel, expiries)
            delta_s12 = time_spreads(unadj)["s12"].diff().dropna()
            grid = roll_window_offset_grid(delta_s12, "gsci")
            fig = bday_heatmap(
                grid, title=f"{root.upper()} Δs12 around GSCI roll windows", unit="USD"
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                f"Source: derived.spread.{root}.s12 (day-over-day Δ), aligned to GSCI's own "
                "roll-calendar windows (core.calendars.roll_calendar)."
            )

with tab_physical, card("DFL / Midland Diff Bands"):
    physical_df = read_physical_csvs()
    if physical_df.empty:
        st.info(
            "No manual Platts/Argus drop yet -- add data/manual/physical/*.csv and run "
            "`pipelines/manual_physical/reader.py` (see pipelines/manual_physical/NOTES.md)."
        )
    else:
        midland = (
            physical_df[physical_df["series_id"] == "manual.argus.wti_midland_diff"]
            .set_index("date")["value"].sort_index()
        )
        bands = physical_bands(midland)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=bands.index, y=bands["p95"], line={"color": GREY, "dash": "dot"}, name="p95"
            )
        )
        fig.add_trace(
            go.Scatter(
                x=bands.index, y=bands["p05"], line={"color": GREY, "dash": "dot"}, name="p05"
            )
        )
        fig.add_trace(
            go.Scatter(
                x=bands.index, y=bands["value"], line={"color": NAVY, "width": 2},
                name="WTI Midland diff",
            )
        )
        fig.add_hline(y=5, line_dash="dash", line_color=RED, annotation_text="Newman +$5")
        fig.add_hline(y=-5, line_dash="dash", line_color=RED, annotation_text="Newman -$5")
        fig.update_layout(title="WTI Midland Differential", yaxis_title="USD/bbl")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Source: manual.argus.wti_midland_diff (pipelines/manual_physical).")
