"""Spec 18 -- Curve & Market Structure. Roll-adjusted curve, spreads, convexity/regime,
Cushing-utilisation coupling, the GSCI/BCOM index-roll calendar, and physical
differentials.

Where a root has no price rows at all, every root-dependent card renders a real
st.info(...) no-data message instead of a chart, per specs/TRADING_LAYER_RUNBOOK.md's own
"render NO-DATA, never fabricate" rule. Cushing utilisation, the roll calendar table, and
"days to next roll" ARE real -- none of them depend on futures price data at all.

## Rank-derived visuals are windowed, and the window is stated on the page

Every exhibit built from f01..fn ranks (the curve strip, s12, cv123, the regime ribbon,
the roll-window heatmap, the Cushing scatter) is restricted to
`pipelines.derived.curve.valid_rank_window(expiries)` onward -- the SAME window that
module applies to the rank series it writes into the lake, so page and lake agree. The
IBKR capture behind this panel holds no contract that had already expired when it was
taken, so before that date `core.curve.nearby_panel` labels a deferred contract `f01`:
plotted unwindowed, `cl`'s own s12 showed 316 points of which 15 were real front-month
spreads and 301 were deferred-vs-deferred. Read that module's docstring before changing
anything here. The window is printed as a caption under each windowed exhibit rather than
applied quietly -- root CLAUDE.md's "a degenerate input fails loudly and visibly".

Contract-coded exhibits carry no rank claim and are NOT windowed (`dec_dec`, and
`fut.<root>.<contract>.*` itself); none is plotted on this page today, so if one is added,
leave it on its full history.

## The source caption states the metric actually plotted

`contract_panel_for(..., return_provenance=True)` returns the per-contract metric choice,
and the caption reports that mix. A settlement and a last trade are different quantities
(pipelines/futures/CLAUDE.md measures the difference), and the caption here once claimed
`fut.<root>.*.settle` for a panel that was entirely `.close`."""

from __future__ import annotations

from collections import Counter
from datetime import date

import core.theme  # noqa: F401
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.lake import read_ts_long
from components.section import page_header, section
from core.calendars import next_roll_window, roll_calendar
from core.curve import (
    REGIME_CODES,
    convexity,
    curve_regime,
    determined_regime_codes,
    nearby_panel,
    physical_bands,
    roll_window_offset_grid,
    rolling_quantile_bands,
    time_spreads,
    transition_matrix,
)
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
from pipelines.derived.curve import contract_panel_for, valid_rank_window
from pipelines.futures.client import ROOTS
from pipelines.futures.series_meta import read_series_meta
from pipelines.manual_physical.reader import read_physical_csvs

page_header("Curve & Market Structure")

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
contract_panel, expiries, metric_by_contract = contract_panel_for(
    root, meta, return_provenance=True
)
has_curve_data = not contract_panel.empty and len(expiries) >= 2


def _in_rank_window(frame: pd.DataFrame, window_start: pd.Timestamp) -> pd.DataFrame:
    """Rows from `window_start` onward -- the rank window, applied to a rank-labelled
    panel before anything is derived from it. Applied to the panel rather than to each
    derived series so the page's own rolling bands (s12's 252d stdev, cv123's
    percentiles) are built from in-window observations only; a band fitted to
    mislabelled rows is as wrong as plotting them."""
    return frame.loc[frame.index >= window_start]


rank_window_start = valid_rank_window(expiries) if has_curve_data else None
unadj = pd.DataFrame()
if has_curve_data and rank_window_start is not None:
    unadj = _in_rank_window(nearby_panel(contract_panel, expiries)[1], rank_window_start)
has_rank_data = not unadj.empty


def _no_futures_data_message() -> None:
    st.info(
        f"No price data yet for {root} -- the lake holds no fut.{root}.*.settle or "
        f"fut.{root}.*.close rows. Run `pipelines/futures/pull_daily.py` once "
        "FUTURES_SOURCE has real data, or ingest an IBKR capture with "
        "`pipelines/futures/pull_ibkr_curve.py` (see pipelines/futures/CLAUDE.md)."
    )


def _rank_data_message() -> None:
    """Why a rank-derived exhibit is empty: no panel at all, or a panel whose every date
    sits before the rank window. The two are different findings and must not read alike."""
    if not has_curve_data:
        _no_futures_data_message()
        return
    st.info(
        f"No trustworthy rank data for {root}: every date in its panel falls before "
        f"{rank_window_start.date() if rank_window_start else 'the rank window'}, so "
        "every f01 label on it would be a deferred contract. A capture with "
        "`include_expired=true` is the real fix -- see pipelines/derived/curve.py."
    )


def _provenance_caption() -> str:
    """What was actually plotted, per contract -- never a guess at the metric."""
    mix = Counter(
        metric
        for contract, metric in metric_by_contract.items()
        if contract in contract_panel.columns
    )
    total = sum(mix.values())
    plotted = ", ".join(f"{count}/{total} .{metric}" for metric, count in sorted(mix.items()))
    return (
        f"Source: fut.{root}.<contract>.settle/.close (pipelines/futures) -- {plotted}, "
        "unadjusted ranks. A settlement and a last trade are different quantities."
    )


def _rank_window_caption() -> str:
    assert rank_window_start is not None  # only called where has_rank_data holds
    return (
        f"Rank window: dates from {rank_window_start.date()} onward only, the same window "
        f"pipelines/derived/curve.py applies to the rank series it writes. Before it the "
        f"{root} panel holds no already-expired contract, so f01 would be a deferred "
        "contract wearing a front-month label."
    )


tab_curve, tab_spreads, tab_convexity, tab_storage, tab_roll_cal, tab_physical = st.tabs(
    ["Curve", "Spreads", "Convexity & Regime", "Storage", "Roll Calendar", "Physical"]
)

with tab_curve, section(f"{root.upper()} Curve Strip"):
    if not has_rank_data:
        _rank_data_message()
    else:
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
        fig = curve_strip_chart(curves, spread_bars, unit="USD")
        st.plotly_chart(fig)
        st.caption(_provenance_caption())
        st.caption(_rank_window_caption())
        if len(curves) < len(offsets):
            st.caption(
                f"{len(curves)} of {len(offsets)} offsets drawn -- the rest need history "
                "from before the rank window, which is not trustworthy for ranks."
            )

with tab_spreads, section(f"{root.upper()} s12 (f01-f02)"):
    if not has_rank_data:
        _rank_data_message()
    else:
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
        fig.update_layout(yaxis_title="USD")
        st.plotly_chart(fig)
        st.caption(f"Source: derived.spread.{root}.s12 (pipelines/derived/curve.py).")
        st.caption(_rank_window_caption())

with tab_convexity:
    with section(f"{root.upper()} Convexity (cv123)"):
        if not has_rank_data:
            _rank_data_message()
        else:
            cv = convexity(unadj).dropna()
            bands = rolling_quantile_bands(cv, window=252, min_periods=20)
            p05, p95 = bands["p05"], bands["p95"]

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
            fig.update_layout(yaxis_title="USD")
            st.plotly_chart(fig)
            st.caption(f"Source: derived.curve.{root}.cv123.")
            st.caption(_rank_window_caption())

    with section(f"{root.upper()} Price & Regime"):
        if not has_rank_data:
            _rank_data_message()
        else:
            regime = curve_regime(unadj, storage_cost_m1m2=storage_cost)
            # The same mask pipelines/derived/curve.py applies before writing this series:
            # curve_regime's default is "flat", which a row also reaches when nothing could
            # be evaluated at all. Undetermined rows are dropped here rather than painted,
            # so the ribbon shows exactly the dates derived.curve.<root>.regime holds -- the
            # caption below cites that series, and a page claiming a state the lake
            # withholds is worse than a gap in the ribbon.
            state_codes = determined_regime_codes(regime, time_spreads(unadj)["s12"]).dropna()
            determined = regime.loc[state_codes.index]
            state_labels = {code: name for name, code in REGIME_CODES.items()}

            if state_codes.empty:
                st.info(
                    f"{root.upper()}'s regime is undetermined on every date in the rank "
                    "window: its state comes from s12, convexity and s1_12, and convexity "
                    "needs three ranks. The lake holds no "
                    f"derived.curve.{root}.regime row for this panel either."
                )
            else:
                fig = regime_ribbon_chart(
                    unadj.loc[state_codes.index, "f01"], state_codes, state_labels, unit="USD",
                )
                st.plotly_chart(fig)
                st.caption(
                    f"Source: derived.curve.{root}.regime (states: {', '.join(REGIME_CODES)})."
                )
                st.caption(_rank_window_caption())
                if len(state_codes) < len(regime):
                    st.caption(
                        f"{len(regime) - len(state_codes)} of {len(regime)} dates in the "
                        "window are omitted: their inputs determined no state, and "
                        "\"flat\" there would assert a structure nothing measured."
                    )

                st.dataframe(transition_matrix(determined["state"]))

with tab_storage:
    util_df = read_ts_long(series_ids=["derived.cushing.util", "derived.cushing.util_decile"])

    with section("Cushing Utilisation vs Decile Rank"):
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
                util, decile,
                left_label="Utilisation", right_label="Decile (1-10)",
            )
            st.plotly_chart(fig)
            st.caption(
                "Source: derived.cushing.util / util_decile (EIA Cushing weekly stocks + "
                "EIA's now-discontinued capacity report, forward-filled past 2024-03-01)."
            )

    with section("Cushing Utilisation vs WTI s12"):
        cl_panel, cl_expiries = contract_panel_for("cl", meta)
        has_cl_data = not cl_panel.empty and len(cl_expiries) >= 2
        cl_s12 = pd.Series(dtype="float64")
        cl_window_start = valid_rank_window(cl_expiries) if has_cl_data else None
        if has_cl_data and cl_window_start is not None:
            # cl's own window, not the selected root's -- a different panel, a different
            # earliest expiry, and this scatter is cl-only whatever the Root selector says.
            cl_unadj = _in_rank_window(
                nearby_panel(cl_panel, cl_expiries)[1], cl_window_start
            )
            cl_s12 = time_spreads(cl_unadj)["s12"]
        if util_df.empty or cl_s12.dropna().empty:
            st.info(
                "No scatter yet -- it needs derived.cushing.util (run "
                "`pipelines/derived/cushing.py`) and cl rank data inside cl's own valid "
                "rank window (run `pipelines/futures/pull_daily.py` with "
                "FUTURES_SOURCE=manual/ibkr, or ingest an IBKR capture; .settle or "
                ".close both qualify)."
            )
        else:
            util = (
                util_df[util_df["series_id"] == "derived.cushing.util"]
                .set_index("ts")["value"].sort_index()
            )
            merged = pd.DataFrame({"util": util, "s12": cl_s12}).dropna()

            # Not `annotations`: that name is already bound at module level by
            # `from __future__ import annotations`, and rebinding it here shadows it.
            fit_annotations: list[tuple[float, float, str]] = []
            april_2020 = merged[merged.index.to_series().between("2020-04-01", "2020-04-30")]
            if not april_2020.empty:
                row = april_2020.iloc[0]
                fit_annotations.append((float(row["util"]), float(row["s12"]), "Apr 2020"))

            fig = scatter_piecewise_fit_chart(
                merged["util"], merged["s12"], merged.index.to_series().dt.year,
                bins=[(0.0, 0.35), (0.35, 0.75), (0.75, 1.01)],
                x_label="Utilisation", y_label="s12 (USD)",
                annotations=fit_annotations or None,
            )
            st.plotly_chart(fig)
            st.caption(
                "Source: derived.cushing.util x derived.spread.cl.s12, cl rank dates from "
                f"{cl_window_start.date() if cl_window_start else '?'} onward only "
                "(pipelines/derived/curve.py's own rank window)."
            )

with tab_roll_cal:
    with section("GSCI / BCOM Roll Calendar"):
        gsci_cal = roll_calendar(as_of.year, "gsci").assign(index="GSCI")
        bcom_cal = roll_calendar(as_of.year, "bcom").assign(index="BCOM")
        combined = pd.concat([gsci_cal, bcom_cal]).sort_values("date").reset_index(drop=True)
        st.dataframe(combined)
        st.caption(
            "Source: core.calendars.roll_calendar -- real calendar arithmetic, no lake dependency."
        )

    with section(f"{root.upper()} Δs12 Around GSCI Roll Windows"):
        if not has_rank_data:
            _rank_data_message()
        else:
            delta_s12 = time_spreads(unadj)["s12"].diff().dropna()
            grid = roll_window_offset_grid(delta_s12, "gsci")
            fig = bday_heatmap(grid, unit="USD")
            st.plotly_chart(fig)
            st.caption(
                f"Source: derived.spread.{root}.s12 (day-over-day Δ), aligned to GSCI's own "
                "roll-calendar windows (core.calendars.roll_calendar)."
            )
            st.caption(_rank_window_caption())

with tab_physical, section("WTI Midland Differential"):
    physical_df = read_physical_csvs()
    if physical_df.empty:
        st.info(
            "No manual Platts/Argus drop yet -- add data/manual/physical/*.csv and run "
            "`pipelines/manual_physical/reader.py` (see pipelines/manual_physical/CLAUDE.md)."
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
        fig.update_layout(yaxis_title="USD/bbl")
        st.plotly_chart(fig)
        st.caption("Source: manual.argus.wti_midland_diff (pipelines/manual_physical).")
