"""Spec 20 -- Refining Economics & Crack Spreads.

Real data, and its real limits, checked live against the lake before writing this page:

- **Spot cracks are current** (`derived.crack.*.spot`, FRED legs, through yesterday), so
  the crack board, seasonal heatmap and percentile ranks are live.
- **Crack futures stop at 2024-04-05.** They come from EIA's `petroleum/pri/fut` route,
  which is discontinued (see `pipelines/futures/CLAUDE.md`). So the board's m1/m2/m6
  tenor columns are genuinely unavailable *today* and render as NaN rather than being
  filled with a two-year-old settlement dressed up as current -- and the forward strip is
  shown at its own as-of date, labelled, not as "today".
- **The model does not beat a random walk.** The monitor card shows that plainly, per
  `specs/00_TRADING_CONVENTIONS.md`: "a miss is a visible diagnostic, never a silent
  pass".
"""

from __future__ import annotations

import core.theme  # noqa: F401
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.section import empty_state, page_header, section
from core.cracks import crack_board, crack_seasonal_heatmap
from core.storage import read_ts_long
from core.theme import (
    GREY,
    LIGHT_BLUE,
    NAVY,
    RED,
    category_time_heatmap,
    cointegration_residual_chart,
    curve_strip_chart,
    irf_chart,
    model_monitor_chart,
    simple_time_series_chart,
)
from core.vecm import backtest_positions, ect_signal, fit_vecm, forecast_eval, irf_table
from pipelines.derived.vecm_refit import build_panel, read_legs, read_model_card
from pipelines.eia.pull_prices import LANDED_COST, LANDED_COST_GEO_MAP, RAC

SPOT_CRACKS = {
    "us321": "NYH 3:2:1",
    "us211": "NYH 2:1:1",
    "gulf321": "US Gulf 3:2:1",
    "nyh_gasoline": "NYH gasoline",
    "nyh_distillate": "NYH distillate",
}
FUT_TENORS = ("m1", "m2", "m3", "m4")
Z_ENTRY, Z_EXIT = 1.5, 0.5
REFIT_TRIGGER = 1.05

page_header("Refining Economics & Crack Spreads")
st.caption(
    "Crack boards, the Murat & Tokat (2009) crack VECM, and its error-correction signal. "
    "Spot cracks are current; crack futures end 2024-04-05 (EIA's futures route is "
    "discontinued)."
)


@st.cache_data(ttl=3600)
def _spot_panel() -> pd.DataFrame:
    ids = [f"derived.crack.{name}.spot" for name in SPOT_CRACKS]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="ts", columns="series_id", values="value")
    wide.columns = [str(c).split(".")[2] for c in wide.columns]
    return wide


@st.cache_data(ttl=3600)
def _futures_strip() -> pd.DataFrame:
    ids = [f"derived.crack.us321.{t}" for t in FUT_TENORS]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="ts", columns="series_id", values="value")
    wide.columns = [str(c).split(".")[3] for c in wide.columns]
    return wide[list(FUT_TENORS)].dropna(how="all")


@st.cache_data(ttl=3600)
def _model_panel() -> pd.DataFrame:
    legs = read_legs()
    return pd.DataFrame() if legs.empty else build_panel(legs)


# The VECM work below is genuinely expensive -- `forecast_eval` refits the model once per
# rolling origin (60 refits at the default test_size), and the page would otherwise fit it
# again for every card. Cached so a tab switch is instant rather than re-running the
# econometrics. Returned objects are plain frames/dicts, so st.cache_data can pickle them;
# the fitted VECMResults itself is deliberately not cached across reruns.
@st.cache_data(ttl=3600)
def _signal_frame() -> pd.DataFrame:
    panel = _model_panel()
    if panel.empty or len(panel) < 80:
        return pd.DataFrame()
    return ect_signal(fit_vecm(panel), panel, z_entry=Z_ENTRY, z_exit=Z_EXIT)


@st.cache_data(ttl=3600)
def _irf_frame() -> pd.DataFrame:
    panel = _model_panel()
    if panel.empty or len(panel) < 80:
        return pd.DataFrame()
    return irf_table(fit_vecm(panel), periods=24)


@st.cache_data(ttl=3600)
def _rmse_ratio() -> pd.Series:
    """Rolling 12-month out-of-sample RMSE ratio against the random walk."""
    panel = _model_panel()
    if panel.empty or len(panel) < 140:
        return pd.Series(dtype=float)
    evaluation = forecast_eval(panel, test_size=60)
    origins = panel.index[-evaluation["n_forecasts"] :]
    vecm_rmse = pd.Series(evaluation["errors_vecm"] ** 2, index=origins).rolling(12).mean() ** 0.5
    rw_rmse = pd.Series(evaluation["errors_rw"] ** 2, index=origins).rolling(12).mean() ** 0.5
    return (vecm_rmse / rw_rmse).dropna()


# Spec 30: Crude acquisition cost -- what refiners actually paid, against what the
# benchmark printed, plus the retail-to-wholesale margin and the landed-cost sourcing mix.
#
# Fixed, non-cycled categorical hues (dataviz house rule): each headline series gets its
# own colour and the rest fold into one muted-grey group, rather than being handed a
# palette colour by index -- the old `_PRICE_PALETTE[i % len(_PRICE_PALETTE)]` cycling
# collided two series onto the same colour once either loop ran past the palette's 4
# entries (8 RAC series, 7 LANDED_COST series).
_ACQUISITION_HEADLINE = {
    "R0000____3": (NAVY, 2.5),  # US composite -- the headline series
    "R1200____3": (LIGHT_BLUE, 2.0),  # US domestic -- tracks WTI
    "R1300____3": (RED, 2.0),  # US imported -- tracks Brent
}
_LANDED_COST_HEADLINE = {
    "I000000208": NAVY,  # US-API-LE20, heaviest -- one end of the sourcing-mix spread
    "I000000998": RED,  # US-API-GT45, lightest -- the other end
}


def _acquisition_cost_section() -> None:
    """What refiners actually paid, against what the benchmark printed. Spec 19's
    quality-mismatch work and Spec 20's VECM both reason about crude grades; until
    Spec 30 the lake held no grade-differentiated price at all."""
    df = read_ts_long(series_ids=list(RAC))
    if df.empty:
        empty_state("eia", "weekly", None)
        st.caption("Run `pipelines/eia/pull_prices.py` to populate refiner acquisition cost.")
        return

    fig = go.Figure()
    padd_legend_shown = False
    for series_id in RAC:
        s = df[df["series_id"] == series_id].sort_values("ts")
        if s.empty:
            continue
        if series_id in _ACQUISITION_HEADLINE:
            colour, width = _ACQUISITION_HEADLINE[series_id]
            fig.add_trace(
                go.Scatter(x=s["ts"], y=s["value"], name=series_id, mode="lines",
                           line={"color": colour, "width": width})
            )
        else:
            # The 5 PADD composites -- regional detail, not identity the reader needs
            # to pick apart line-by-line. One undifferentiated muted-grey group, solid
            # (distinct from the dotted/dashed WTI/Brent reference lines below), one
            # shared legend entry rather than 5 rows all saying "PADD composite".
            fig.add_trace(
                go.Scatter(x=s["ts"], y=s["value"], name="PADD composite", mode="lines",
                           legendgroup="padd_composite", showlegend=not padd_legend_shown,
                           line={"color": GREY, "width": 1})
            )
            padd_legend_shown = True
    wti = read_ts_long(series_ids=["fred.dcoilwtico"]).sort_values("ts")
    if not wti.empty:
        fig.add_trace(
            go.Scatter(x=wti["ts"], y=wti["value"], name="WTI spot", mode="lines",
                       line={"color": GREY, "width": 1, "dash": "dot"})
        )
    # Domestic acquisition cost tracks WTI; imported tracks Brent -- both reference lines
    # are needed, or the imported line reads as persistently mispriced against WTI when it
    # is simply following a different benchmark (specs/30_eia-price-coverage.md line 116).
    brent = read_ts_long(series_ids=["fred.dcoilbrenteu"]).sort_values("ts")
    if not brent.empty:
        fig.add_trace(
            go.Scatter(x=brent["ts"], y=brent["value"], name="Brent spot", mode="lines",
                       line={"color": GREY, "width": 1, "dash": "dash"})
        )
    fig.update_layout(yaxis_title="$/bbl")
    with section("Refiner acquisition cost vs WTI and Brent spot"):
        st.plotly_chart(fig)
        st.caption(
            "Composite, domestic and imported acquisition cost is what refiners paid; "
            "the dotted and dashed lines are the WTI and Brent benchmark prints. Domestic "
            "cost tracks WTI, imported cost tracks Brent — the gap between either "
            "acquisition line and its own benchmark is the part a spot-only crack cannot "
            "see."
        )


def _landed_cost_section() -> None:
    """Light versus heavy sourcing mix -- the series Spec 19's quality-mismatch work has
    been reasoning about without. petroleum/pri/land3 returns area-name as the literal
    string "NA" for every row, so series names come from LANDED_COST_GEO_MAP's own
    gravity-band labels rather than the API's geo field."""
    df = read_ts_long(series_ids=list(LANDED_COST))
    if df.empty:
        empty_state("eia", "weekly", None)
        st.caption(
            "Run `pipelines/eia/pull_prices.py` to populate landed cost by API "
            "gravity band."
        )
        return

    fig = go.Figure()
    middle_legend_shown = False
    for series_id in LANDED_COST:
        s = df[df["series_id"] == series_id].sort_values("ts")
        if s.empty:
            continue
        if series_id in _LANDED_COST_HEADLINE:
            fig.add_trace(
                go.Scatter(x=s["ts"], y=s["value"], name=LANDED_COST_GEO_MAP[series_id],
                           mode="lines",
                           line={"color": _LANDED_COST_HEADLINE[series_id], "width": 2})
            )
        else:
            # The middle 5 API-gravity bands -- the caption's contrast is between the
            # two extremes above; muted so the middle bands don't compete for attention.
            fig.add_trace(
                go.Scatter(x=s["ts"], y=s["value"], name="Middle API-gravity bands",
                           mode="lines", legendgroup="landed_cost_middle",
                           showlegend=not middle_legend_shown,
                           line={"color": GREY, "width": 1})
            )
            middle_legend_shown = True
    fig.update_layout(yaxis_title="$/bbl")
    with section("Landed cost of imported crude by API gravity band"):
        st.plotly_chart(fig)
        st.caption(
            "Lower API-gravity bands (US-API-LE20) are heavier crude; higher bands "
            "(US-API-GT45) are lighter. The spread between them is a sourcing-mix "
            "indicator, not just a price level."
        )


# US retail gasoline (all grades, all formulations) -- pipelines.eia.pull_prices.RETAIL[0],
# referenced here by its own EIA series id rather than by list index, per the same lesson
# Fix 1 (05_us_gas_power.py) drew: an index into a reorderable list is a silent-wrong-chart
# risk, not a loud one.
_US_RETAIL_GASOLINE = "EMM_EPM0_PTE_NUS_DPG"
# NY Harbor conventional gasoline, $/gal -- one of the wholesale legs Spec 20 added to the
# lake, and the benchmark the retail-to-wholesale margin below is measured against.
_WHOLESALE_GASOLINE_NYH = "fred.dgasnyh"


def _retail_margin_section() -> None:
    """Spec 30 lines 126-127: retail belongs beside its wholesale leg, as a secondary line
    beneath the wholesale crack -- the point is the retail-to-wholesale margin, not the
    pump price alone. Plots US retail gasoline against the NY Harbor wholesale leg and the
    margin between them on its own axis, so the margin is a visible quantity rather than
    something implied by eyeballing two overlapping lines."""
    retail = read_ts_long(series_ids=[_US_RETAIL_GASOLINE]).sort_values("ts")
    wholesale = read_ts_long(series_ids=[_WHOLESALE_GASOLINE_NYH]).sort_values("ts")
    if retail.empty or wholesale.empty:
        empty_state("eia", "weekly", None)
        st.caption(
            "Run `pipelines/eia/pull_prices_weekly.py` and `pipelines/eia/pull_prices.py` "
            "to populate retail and wholesale gasoline prices."
        )
        return

    retail_by_ts = retail.set_index("ts")["value"]
    wholesale_by_ts = wholesale.set_index("ts")["value"]
    overlap = retail_by_ts.index.intersection(wholesale_by_ts.index)
    margin = (retail_by_ts.loc[overlap] - wholesale_by_ts.loc[overlap]).sort_index()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=retail_by_ts.index, y=retail_by_ts.to_numpy(), name="US retail gasoline",
                   mode="lines", line={"color": NAVY, "width": 2})
    )
    fig.add_trace(
        go.Scatter(x=wholesale_by_ts.index, y=wholesale_by_ts.to_numpy(),
                   name="NY Harbor wholesale gasoline", mode="lines",
                   line={"color": LIGHT_BLUE, "width": 2})
    )
    if not margin.empty:
        fig.add_trace(
            go.Scatter(x=margin.index, y=margin.to_numpy(), name="Retail-wholesale margin",
                       mode="lines", line={"color": RED, "width": 2}, yaxis="y2")
        )
        latest = margin.index.max()
        fig.add_annotation(
            x=latest,
            y=margin.loc[latest],
            yref="y2",
            text=f"Margin ${margin.loc[latest]:.2f}/gal",
            showarrow=True,
            arrowhead=2,
            ax=40,
            ay=-30,
        )
    fig.update_layout(
        yaxis_title="$/gal",
        yaxis2={"title": "Margin ($/gal)", "overlaying": "y", "side": "right"},
    )
    with section("Retail-to-wholesale margin"):
        st.plotly_chart(fig)
        st.caption(
            "The margin (red, right-hand axis) between the pump price and the NY Harbor "
            "wholesale leg is the interesting quantity here, not the pump price alone."
        )


tab_board, tab_seasonal, tab_curve, tab_model, tab_signal = st.tabs(
    ["Crack Board", "Seasonality", "Forward Strip", "Cointegration & Model", "ECT Signal"]
)

# --- crack board ------------------------------------------------------------------

with tab_board:
    spot = _spot_panel()
    with section("Crack board"):
        if spot.empty:
            st.info("No crack series in the lake. Run `python -m pipelines.derived.cracks`.")
        else:
            board = crack_board(spot)
            board["crack"] = board["crack"].map(SPOT_CRACKS).fillna(board["crack"])
            st.dataframe(
                board.style.format(
                    {
                        "spot": "{:.2f}",
                        "m1": "{:.2f}",
                        "m2": "{:.2f}",
                        "m6": "{:.2f}",
                        "seasonal_5y_mean": "{:.2f}",
                        "pct_rank_5y": "{:.0f}",
                    },
                    na_rep="—",
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption(
                f"$/bbl, as of {spot.index.max():%d %b %Y}. Seasonal mean excludes 2020 "
                "(core.seasonal). **m1/m2/m6 are empty because no current futures exist** "
                "— EIA's futures route ends 2024-04-05 and no IBKR feed is connected, so "
                "a forward tenor here would be a two-year-old settlement, not today's."
            )

    if not spot.empty:
        with section("Crack history"):
            choice = st.selectbox(
                "Crack", list(SPOT_CRACKS), format_func=lambda k: SPOT_CRACKS[k]
            )
            st.plotly_chart(
                simple_time_series_chart(spot[choice].dropna(), "$/bbl"),
                width="stretch",
            )

# --- seasonality ------------------------------------------------------------------

with tab_seasonal:
    spot = _spot_panel()
    with section("NYH 3:2:1 monthly mean by year"):
        if spot.empty:
            st.info("No crack series in the lake.")
        else:
            heat = crack_seasonal_heatmap(spot["us321"].dropna()).tail(15)
            heat.columns = [
                pd.Timestamp(year=2001, month=int(m), day=1).strftime("%b")
                for m in heat.columns
            ]
            st.plotly_chart(
                category_time_heatmap(heat.T, "$/bbl",
                                      center=float(np.nanmedian(heat.to_numpy()))),
                width="stretch",
            )
            st.caption(
                "2020 is deliberately **kept** here — the heatmap is a descriptive record "
                "of what happened, unlike the seasonal statistics, which exclude it."
            )

# --- forward strip ----------------------------------------------------------------

with tab_curve:
    strip = _futures_strip()
    with section("NYH 3:2:1 crack futures strip"):
        if strip.empty:
            st.info(
                "No crack futures in the lake. Run "
                "`python -m pipelines.futures.pull_eia_history` then "
                "`python -m pipelines.derived.cracks`."
            )
        else:
            as_of = strip.index.max()
            year_ago = strip.index[strip.index <= as_of - pd.DateOffset(years=1)]
            curves = {f"{as_of:%d %b %Y}": strip.loc[as_of]}
            if len(year_ago):
                curves[f"{year_ago[-1]:%d %b %Y}"] = strip.loc[year_ago[-1]]
            spreads = {
                "m1-m2": float(strip.loc[as_of, "m1"] - strip.loc[as_of, "m2"]),
                "m1-m4": float(strip.loc[as_of, "m1"] - strip.loc[as_of, "m4"]),
            }
            st.plotly_chart(
                curve_strip_chart(curves, spreads, "$/bbl"),
                width="stretch",
            )
            st.warning(
                f"**Not current.** This strip is as of {as_of:%d %B %Y}, the last day EIA "
                "published NYMEX futures before discontinuing the series. It is history, "
                "not a live curve."
            )
            st.caption("EIA publishes contracts 1-4 only, so there is no m6 here.")

# --- cointegration & model --------------------------------------------------------

with tab_model:
    panel = _model_panel()
    card_df = read_model_card()

    with section("Model card"):
        if card_df.empty:
            st.info("No model card yet. Run `python -m pipelines.derived.vecm_refit`.")
        else:
            latest = card_df.iloc[-1]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Theil U vs RW", f"{latest['theil_u']:.4f}")
            c2.metric("Johansen rank", int(latest["rank"]))
            c3.metric("β on crack", f"{latest['beta_crack']:.4f}")
            c4.metric("Exceptions", f"{int(latest['exceptions'])}/{int(latest['n_forecasts'])}")
            if latest["theil_u"] >= 1.0:
                st.error(
                    f"**This model does not beat a random walk.** Theil U "
                    f"{latest['theil_u']:.4f} (>1 means worse), Diebold-Mariano "
                    f"{latest['dm_stat']:+.2f}, p={latest['dm_p']:.3f}. Status: "
                    f"`{latest['oos_status']}`. Shown rather than hidden, per the "
                    "conventions — a miss is a visible diagnostic."
                )
            st.caption(
                f"Crack leg: **{latest['crack_source']}** · sample {latest['sample']} "
                f"({latest['estimation_start']:%b %Y} to {latest['estimation_end']:%b %Y}, "
                f"n={int(latest['n_obs'])}) · lags {int(latest['k_ar_diff'])} · "
                f"break {latest['break_date']:%b %Y} · last refit {latest['as_of']:%d %b %Y}. "
                f"{latest['deviation']}"
            )
            st.caption(
                "Benchmark is a random walk. Murat & Tokat's own RMSE/Theil figures are "
                "not in open sources, so the published comparison is qualitative: the "
                "paper reports both futures VECMs beating the random walk, which this "
                "does not reproduce."
            )

    with section("Cointegrating relation and error-correction term"):
        signal = _signal_frame()
        if signal.empty:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            st.plotly_chart(
                cointegration_residual_chart(
                    signal["ect"].dropna(),
                    signal["z"].dropna(),
                    "log $/bbl",
                    z_entry=Z_ENTRY,
                    z_exit=Z_EXIT,
                ),
                width="stretch",
            )

    with section("Response of log(WTI spot) to a 1 s.d. crack shock"):
        irf = _irf_frame()
        if irf.empty:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            st.plotly_chart(
                irf_chart(
                    irf,
                    "crude_to_crack_shock",
                    "log $/bbl",
                ),
                width="stretch",
            )

    with section("Rolling 12-month OOS RMSE ratio vs the random walk"):
        ratio = _rmse_ratio()
        if ratio.empty:
            st.info("Not enough history for a rolling out-of-sample evaluation.")
        else:
            st.plotly_chart(
                model_monitor_chart(
                    ratio,
                    REFIT_TRIGGER,
                    break_date=None if card_df.empty else card_df.iloc[-1]["break_date"],
                ),
                width="stretch",
            )
            st.caption(
                "Above the dotted parity line the model is losing to the random walk; "
                "above the dashed line it breaches the refit trigger."
            )

# --- ECT signal -------------------------------------------------------------------

with tab_signal:
    panel = _model_panel()
    with section("Error-correction signal"):
        signal = _signal_frame()
        if signal.empty:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            result = backtest_positions(signal["position"], panel["crack321"])
            summary = result["summary"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sharpe", f"{summary['sharpe']:.2f}")
            c2.metric("Hit rate", f"{summary['hit_rate']:.0%}")
            c3.metric("Max drawdown", f"{summary['max_drawdown']:.1f}")
            c4.metric("Trades", summary["n_trades"])

            st.plotly_chart(
                simple_time_series_chart(result["equity"], "$/bbl"),
                width="stretch",
            )

            turn, non_turn = summary["turnaround"], summary["non_turnaround"]
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Segment": "Turnaround (Mar-Apr, Sep-Oct)",
                            "Total P&L": turn["total_pnl"],
                            "Sharpe": turn["sharpe"],
                            "Months": turn["n_periods"],
                        },
                        {
                            "Segment": "Non-turnaround",
                            "Total P&L": non_turn["total_pnl"],
                            "Sharpe": non_turn["sharpe"],
                            "Months": non_turn["n_periods"],
                        },
                    ]
                ).style.format({"Total P&L": "{:.1f}", "Sharpe": "{:.2f}"}),
                width="stretch",
                hide_index=True,
            )
            st.warning(
                f"**Backtest caveat.** The engine is a `{summary['engine']}` — "
                "`core/systematic.py` (Spec 21) does not exist yet, so this is a minimal "
                "position-times-forward-move calculation, not the real systematic engine. "
                "The volatility scaling is likewise a plain rolling standard deviation "
                "standing in for Spec 22's GARCH-MIDAS-EVT vol. Costs, slippage and "
                "position limits are **not** modelled. Treat these numbers as a wiring "
                "check, not a strategy result — especially given the underlying model "
                "does not beat a random walk."
            )
            st.caption(
                f"Entry |z| ≥ {Z_ENTRY}, exit |z| ≤ {Z_EXIT}, held in between. Scaled by "
                "the crude leg's share of the adjustment speed and by inverse realised "
                "vol, and flattened wherever the position fights 3-month crack momentum. "
                "Positions are shifted one month before earning a return, so the signal "
                "never trades on information it did not have."
            )

# --- crude acquisition cost --------------------------------------------------------

st.subheader("Crude acquisition cost")
_acquisition_cost_section()
_landed_cost_section()
_retail_margin_section()
