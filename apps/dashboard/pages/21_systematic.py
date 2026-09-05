"""Spec 21 -- Systematic Strategies Engine.

What is real here, and what is not, checked live against the lake before writing this:

- **Six of eight registry strategies run.** `CARRY_1_13` needs nearby rank 13 and
  `FWD_SPREAD_MR` needs rank 7; EIA's discontinued NYMEX route publishes ranks 1-4 only.
  Both are shown as explicitly skipped with their missing ranks rather than omitted or,
  worse, silently rerun on a shorter spread.
- **The published anchors are all C(1,13)**, so they are *not* comparable to this repo's
  carry results, which run on C(1,3). The comparison card says so rather than printing a
  deviation that would imply otherwise. `SHORT_SPREAD_STATIC` is the one strategy that
  *is* directly comparable, and it misses badly.
- **Bouchouev's inventory-predictability finding does not reproduce** on this data. The
  page carries the repo's own numbers beside the book's claim, per the spec's own
  instruction to keep it as a permanent caption.
"""

from __future__ import annotations

import core.theme  # noqa: F401
import numpy as np
import pandas as pd
import streamlit as st
from components.card import card
from core.backtest import backtest, fractionate, inventory_predictability_test, spread_to_return
from core.storage import read_ts_long
from core.strategies import REGISTRY, missing_ranks
from core.systematic import log_price
from core.theme import (
    crowding_quadrant_scatter,
    equity_drawdown_chart,
    fractionation_heatmap,
    reaction_curve_chart,
    signal_board_table,
)
from pipelines.derived.curve_ranks import ADJUSTED_SUFFIX, RANK_ROOTS

CUSHING_STOCKS = "W_EPC0_SAX_YCUOK_MBBL"
BENCHMARK_STRATEGY = "SHORT_SPREAD_STATIC"
COST_BPS = 2.0

# Published anchors live on `Strategy.benchmark` in the registry, not here -- a second
# copy on the page would be a second source of truth and would drift.

st.title("Systematic Strategies Engine")
st.caption(
    "Bouchouev signals, reaction-function sizing and a vectorised backtester. "
    "Positions are lagged one day; costs are charged on trades, not holdings."
)


@st.cache_data(ttl=3600)
def _root_data(root: str) -> dict[str, pd.Series]:
    ids = [
        f"derived.curve.{root}.{ADJUSTED_SUFFIX}",
        f"fut.{root}.f01.settle",
        f"derived.spread.{root}.s12",
        f"derived.curve.{root}.regime",
        f"derived.cot.{root}.mm_pct_3y",
        "derived.cushing.util_decile",
    ]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return {}
    wide = df.pivot_table(index="ts", columns="series_id", values="value").sort_index()
    return {str(c).split(".")[-1] if "." in str(c) else str(c): wide[c] for c in wide.columns}


@st.cache_data(ttl=3600)
def _positions(root: str) -> pd.DataFrame:
    ids = [f"derived.pos.{name}.{root}" for name in REGISTRY]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="ts", columns="series_id", values="value").sort_index()
    wide.columns = [str(c).split(".")[2] for c in wide.columns]
    return wide


@st.cache_data(ttl=3600)
def _panel(root: str) -> pd.DataFrame:
    ids = [f"fut.{root}.f{r:02d}.settle" for r in (1, 2, 3, 4)]
    df = read_ts_long(series_ids=ids)
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="ts", columns="series_id", values="value").sort_index()
    wide.columns = [str(c).split(".")[2] for c in wide.columns]
    return wide


def _run(root: str, name: str) -> tuple[pd.Series, dict[str, float]] | None:
    positions = _positions(root)
    raw = read_ts_long(
        series_ids=[
            f"derived.curve.{root}.{ADJUSTED_SUFFIX}",
            f"fut.{root}.f01.settle",
            f"derived.spread.{root}.s12",
        ]
    )
    if positions.empty or name not in positions.columns or raw.empty:
        return None
    wide = raw.pivot_table(index="ts", columns="series_id", values="value").sort_index()
    adj = wide.get(f"derived.curve.{root}.{ADJUSTED_SUFFIX}")
    f01 = wide.get(f"fut.{root}.f01.settle")
    s12 = wide.get(f"derived.spread.{root}.s12")
    if adj is None or f01 is None:
        return None

    returns = log_price(adj).diff()
    spread = (
        spread_to_return(s12, f01)
        if REGISTRY[name].traded == "spread" and s12 is not None
        else None
    )
    result = backtest(positions[name], returns, spread_pnl=spread, cost_bps=COST_BPS)
    return result.pnl, result.stats


root = st.selectbox("Root", RANK_ROOTS, format_func=str.upper)
positions = _positions(root)
panel = _panel(root)

tab_board, tab_equity, tab_reaction, tab_fraction, tab_crowding = st.tabs(
    ["Signal Board", "Equity & Benchmarks", "Reaction Function", "Fractionation", "Crowding"]
)

# --- signal board -----------------------------------------------------------------

with tab_board:
    with card(f"Signal board -- {root.upper()}"):
        if positions.empty:
            st.info(
                "No positions in the lake. Run `python -m pipelines.derived.systematic`."
            )
        else:
            latest = positions.dropna(how="all").iloc[-1]
            board = pd.DataFrame(
                {
                    "strategy": latest.index,
                    "position": latest.to_numpy(dtype=float),
                    "traded": [REGISTRY[n].traded for n in latest.index],
                }
            ).sort_values("strategy")
            st.plotly_chart(
                signal_board_table(board, f"Latest positions ({positions.index.max():%d %b %Y})"),
                width="stretch",
            )
            disclosures = {n: REGISTRY[n].note for n in latest.index if REGISTRY[n].note}
            for name, note in disclosures.items():
                st.caption(f"**{name}** — {note}")

    with card("Strategies that cannot run on this data"):
        skipped = {
            name: missing_ranks(strategy, panel)
            for name, strategy in REGISTRY.items()
            if not panel.empty and missing_ranks(strategy, panel)
        }
        if not skipped:
            st.success("Every registry strategy has the ranks it needs.")
        else:
            for name, ranks in skipped.items():
                needed = ", ".join(f"f{r:02d}" for r in ranks)
                st.warning(f"**{name}** — needs {needed}. {REGISTRY[name].note}")
            st.caption(
                "Shown rather than hidden. A strategy with missing data is skipped, never "
                "written as a flat position — flat is a real trading decision, not an "
                "absence of one."
            )

# --- equity curves and the published comparison -----------------------------------

with tab_equity:
    with card("Repo estimate vs published anchor"):
        rows = []
        for name in REGISTRY:
            run = _run(root, name)
            if run is None:
                continue
            _, stats = run
            anchor = REGISTRY[name].benchmark
            anchor_sharpe = anchor.sharpe if anchor else float("nan")
            basis = anchor.source if anchor else ""
            comparable = name == BENCHMARK_STRATEGY
            rows.append(
                {
                    "strategy": name,
                    "ann return": stats["ann_log_return"],
                    "Sharpe": stats["sharpe"],
                    "published Sharpe": anchor_sharpe,
                    "deviation": (stats["sharpe"] - anchor_sharpe) if comparable else np.nan,
                    "basis": basis or "-",
                    # The registry's own disclosure text, surfaced rather than hidden --
                    # this is where "C(1,3), not the paper's C(1,13)" reaches the reader.
                    "note": REGISTRY[name].note or "-",
                }
            )
        if not rows:
            st.info("No backtestable positions in the lake yet.")
        else:
            st.dataframe(
                pd.DataFrame(rows).style.format(
                    {
                        "ann return": "{:.1%}",
                        "Sharpe": "{:.2f}",
                        "published Sharpe": "{:.2f}",
                        "deviation": "{:+.2f}",
                    },
                    na_rep="-",
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "**Costing convention**, inherited by Specs 20 and 24-27: cost is charged "
                "on `pos.diff()`, the day the *signal* changes, which is one day before "
                "the new position starts earning. No look-ahead either way, but it is a "
                "real convention choice rather than an inevitability."
            )
            st.warning(
                "**Deviation is shown only for SHORT_SPREAD_STATIC.** Every other "
                "published anchor is measured on **C(1,13)** — rank 1 against rank 13 — "
                "and this lake's only futures source publishes ranks 1-4, so the carry "
                "strategies here run on C(1,3). Subtracting a C(1,3) Sharpe from a "
                "C(1,13) anchor would produce a number that looks like a result and is "
                "not one."
            )

    with card("Equity and drawdown"):
        runnable = [n for n in REGISTRY if _run(root, n) is not None]
        if not runnable:
            st.info("Nothing to plot yet.")
        else:
            choice = st.selectbox("Strategy", runnable)
            pnl, stats = _run(root, choice)
            benchmark = _run(root, BENCHMARK_STRATEGY)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Ann. log return", f"{stats['ann_log_return']:.1%}")
            c2.metric("Sharpe", f"{stats['sharpe']:.2f}")
            c3.metric("Max drawdown", f"{stats['max_drawdown']:.2f}")
            c4.metric("Turnover", f"{stats['turnover']:.1f}x")
            st.plotly_chart(
                equity_drawdown_chart(
                    pnl.cumsum(),
                    pnl.cumsum() - pnl.cumsum().cummax(),
                    f"{choice} — cumulative log P&L",
                    "log return",
                    benchmark=benchmark[0].cumsum() if benchmark else None,
                ),
                width="stretch",
            )
            st.caption(
                f"Costs {COST_BPS:.0f} bps on traded notional. Positions lagged one day. "
                "The benchmark line is SHORT_SPREAD_STATIC."
            )

# --- reaction function ------------------------------------------------------------

with tab_reaction, card("Reaction function with today's z"):
    data = _root_data(root)
    s12 = data.get("s12")
    live_z = float("nan")
    if s12 is not None and len(s12.dropna()) > 252:
        rolled = s12.rolling(252)
        z = (s12 - rolled.mean()) / rolled.std()
        live_z = float(z.dropna().iloc[-1])
    st.plotly_chart(
        reaction_curve_chart(live_z, "R(z) = z*exp(0.5*(1-z^2))"), width="stretch"
    )
    st.caption(
        "Conviction peaks at z=1 and *falls* beyond it: an unusually extreme reading "
        "is treated as a regime the model does not understand, not a bigger "
        "opportunity. Input is clipped to +/-3."
    )

# --- fractionation ----------------------------------------------------------------

with tab_fraction, card("Where the P&L came from"):
    runnable = [n for n in REGISTRY if _run(root, n) is not None]
    if not runnable:
        st.info("Nothing to attribute yet.")
    else:
        choice = st.selectbox("Strategy ", runnable, key="fraction_strategy")
        pnl, _ = _run(root, choice)
        data = _root_data(root)
        conditioners = {}
        if "regime" in data:
            conditioners["curve regime"] = data["regime"]
        if "util_decile" in data:
            conditioners["Cushing decile"] = data["util_decile"]
        if "mm_pct_3y" in data:
            conditioners["COT percentile"] = data["mm_pct_3y"]
        conditioners["month"] = pd.Series(pnl.index.month, index=pnl.index)

        table = fractionate(pnl, conditioners, bins=5)
        if table.empty:
            st.info("No conditioners available for this root.")
        else:
            st.plotly_chart(
                fractionation_heatmap(table, f"{choice} — Sharpe by bucket", value="sharpe"),
                width="stretch",
            )
            st.dataframe(
                table.style.format(
                    {"mean": "{:.5f}", "sharpe": "{:.2f}", "share_of_total": "{:.1%}"}
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption("Shares of total P&L sum to 1 within each condition.")

# --- crowding ---------------------------------------------------------------------

with tab_crowding:
    with card("Crowding monitor"):
        data = _root_data(root)
        cot = data.get("mm_pct_3y")
        s12 = data.get("s12")
        if cot is None or s12 is None:
            st.info("No CFTC positioning for this root.")
        else:
            rolled = s12.rolling(252)
            z = (s12 - rolled.mean()) / rolled.std()
            st.plotly_chart(
                crowding_quadrant_scatter(cot, z.reindex(cot.index), "Positioning vs signal"),
                width="stretch",
            )
            st.caption(
                "Shaded corners are the inflection quadrants: a long signal while managed "
                "money is already crowded long, and the mirror image. The guardrails halve "
                "positions there."
            )

    with card("Do spreads predict inventories, or the reverse?"):
        stocks = read_ts_long(series_ids=[CUSHING_STOCKS])
        data = _root_data(root)
        s12 = data.get("s12")
        if stocks.empty or s12 is None:
            st.info("Cushing stocks or the front spread are unavailable.")
        else:
            series = stocks.set_index("ts")["value"].sort_index()
            try:
                test = inventory_predictability_test(s12.reindex(series.index).ffill(), series)
            except ValueError as exc:
                st.info(f"Not enough overlapping history: {exc}")
            else:
                left, right = st.columns(2)
                left.metric(
                    "spread → inventory",
                    f"r²={test['r2_spread_to_inventory']:.4f}",
                    f"t={test['t_spread_to_inventory']:+.2f}",
                )
                right.metric(
                    "inventory → spread",
                    f"r²={test['r2_inventory_to_spread']:.4f}",
                    f"t={test['t_inventory_to_spread']:+.2f}",
                )
                if test["spread_leads_inventory"]:
                    st.success(
                        "Spreads lead inventories here, matching Bouchouev's finding."
                    )
                else:
                    st.error(
                        "**This does not reproduce Bouchouev's finding.** He argues "
                        "spreads predict inventories more than the reverse; on this data "
                        "the reverse is (weakly) stronger. Both relationships are small. "
                        "Caveat: Cushing stocks are weekly and the rank spread is daily, "
                        "so the forward-filled alignment blunts the test."
                    )
                st.caption(
                    f"n={test['n_obs']} overlapping observations. Regressed on changes, "
                    "not levels — two trending levels would give a high r² in either "
                    "direction and say nothing about lead-lag."
                )
