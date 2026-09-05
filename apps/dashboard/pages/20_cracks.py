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
import streamlit as st
from components.card import card
from core.cracks import crack_board, crack_seasonal_heatmap
from core.storage import read_ts_long
from core.theme import (
    category_time_heatmap,
    cointegration_residual_chart,
    curve_strip_chart,
    irf_chart,
    model_monitor_chart,
    simple_time_series_chart,
)
from core.vecm import backtest_positions, ect_signal, fit_vecm, forecast_eval, irf_table
from pipelines.derived.vecm_refit import build_panel, read_legs, read_model_card

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

st.title("Refining Economics & Crack Spreads")
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


tab_board, tab_seasonal, tab_curve, tab_model, tab_signal = st.tabs(
    ["Crack Board", "Seasonality", "Forward Strip", "Cointegration & Model", "ECT Signal"]
)

# --- crack board ------------------------------------------------------------------

with tab_board:
    spot = _spot_panel()
    with card("Crack board"):
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
        with card("Crack history"):
            choice = st.selectbox(
                "Crack", list(SPOT_CRACKS), format_func=lambda k: SPOT_CRACKS[k]
            )
            st.plotly_chart(
                simple_time_series_chart(
                    spot[choice].dropna(), f"{SPOT_CRACKS[choice]} (spot)", "$/bbl"
                ),
                width="stretch",
            )

# --- seasonality ------------------------------------------------------------------

with tab_seasonal:
    spot = _spot_panel()
    with card("Crack seasonality (monthly mean by year)"):
        if spot.empty:
            st.info("No crack series in the lake.")
        else:
            heat = crack_seasonal_heatmap(spot["us321"].dropna()).tail(15)
            heat.columns = [pd.Timestamp(2001, m, 1).strftime("%b") for m in heat.columns]
            st.plotly_chart(
                category_time_heatmap(heat.T, "NYH 3:2:1 monthly mean by year", "$/bbl",
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
    with card("Crack forward strip vs a year earlier"):
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
                curve_strip_chart(curves, spreads, "NYH 3:2:1 crack futures strip", "$/bbl"),
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

    with card("Model card"):
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

    with card("Cointegrating relation and error-correction term"):
        if panel.empty or len(panel) < 80:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            fitted = fit_vecm(panel)
            signal = ect_signal(fitted, panel, z_entry=Z_ENTRY, z_exit=Z_EXIT)
            st.plotly_chart(
                cointegration_residual_chart(
                    signal["ect"].dropna(),
                    signal["z"].dropna(),
                    "log(WTI spot) - beta*crack: fitted relation and z-score",
                    "log $/bbl",
                    z_entry=Z_ENTRY,
                    z_exit=Z_EXIT,
                ),
                width="stretch",
            )

    with card("Impulse response — crude's reaction to a crack shock"):
        if panel.empty or len(panel) < 80:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            st.plotly_chart(
                irf_chart(
                    irf_table(fit_vecm(panel), periods=24),
                    "crude_to_crack_shock",
                    "Response of log(WTI spot) to a 1 s.d. crack shock",
                    "log $/bbl",
                ),
                width="stretch",
            )

    with card("Model monitor — rolling out-of-sample RMSE ratio"):
        if panel.empty or len(panel) < 140:
            st.info("Not enough history for a rolling out-of-sample evaluation.")
        else:
            evaluation = forecast_eval(panel, test_size=60)
            origins = panel.index[-evaluation["n_forecasts"] :]
            ratio = (
                pd.Series(evaluation["errors_vecm"] ** 2, index=origins).rolling(12).mean() ** 0.5
                / pd.Series(evaluation["errors_rw"] ** 2, index=origins).rolling(12).mean() ** 0.5
            )
            st.plotly_chart(
                model_monitor_chart(
                    ratio.dropna(),
                    REFIT_TRIGGER,
                    "Rolling 12-month OOS RMSE ratio vs the random walk",
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
    with card("Error-correction signal"):
        if panel.empty or len(panel) < 80:
            st.info("Not enough monthly observations to fit the VECM.")
        else:
            fitted = fit_vecm(panel)
            signal = ect_signal(fitted, panel, z_entry=Z_ENTRY, z_exit=Z_EXIT)
            result = backtest_positions(signal["position"], panel["crack321"])
            summary = result["summary"]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sharpe", f"{summary['sharpe']:.2f}")
            c2.metric("Hit rate", f"{summary['hit_rate']:.0%}")
            c3.metric("Max drawdown", f"{summary['max_drawdown']:.1f}")
            c4.metric("Trades", summary["n_trades"])

            st.plotly_chart(
                simple_time_series_chart(
                    result["equity"], "Cumulative P&L ($/bbl per unit position)", "$/bbl"
                ),
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
