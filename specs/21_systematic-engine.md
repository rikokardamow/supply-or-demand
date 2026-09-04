# Spec 21 — Systematic Strategies Engine

**Sources:** Bouchouev *Virtual Barrels* Ch. 5–6. Published anchors to display beside repo estimates: carry C(1,13) ≈ 20.3% annualised log-return, Sharpe 0.53, 1992–2022, unleveraged; carry–momentum blend ≈ 24.7%, Sharpe 0.64; static short front spread ≈ IR 0.50. Conventions: `specs/00_TRADING_CONVENTIONS.md`.

## Purpose
Signals, reaction-function sizing, vol targeting, a vectorised backtester reused by Specs 20/24/25/26/27, and fractionation analytics. Page `21_systematic.py`.

## Data
Spec 18 (adjusted f01 returns, unadjusted ranks, spreads, convexity, regime, Cushing decile). Spec 19 (`derived.cot.*.mm_pct_3y`). Spec 22 realised vol (until Spec 22 exists, a 63d realised-vol fallback lives here and is replaced later).

## Sessions

### Session A — `core/systematic.py` signals and sizing
```python
def momentum_ma(f01_adj, n=100) -> Series           # f01 - MA_n
def momentum_ret(f01_adj, n=252) -> Series
def carry(unadj, near=1, far=13) -> Series           # F_near - F_far
def carry_pct(unadj, near=1, far=13) -> Series       # annualised
def value(f01_adj, n=1260) -> Series                 # overlay only
def convexity_signal(unadj) -> Series                # sign(cv123) from core.curve
def momentum_on_carry(carry, n=60) -> Series
def zscore(x, window=252) -> Series
def reaction(z) -> Series                            # R(z) = z*exp(0.5*(1-z**2)), input clipped to [-3,3]
def reaction_piecewise(z, plateau=1.0, cutoff=2.5) -> Series
def vol_target(returns, target_ann=0.10, window=63) -> Series
def blend(signals: dict[str, Series], weights: dict[str, float]) -> Series
def position(blended_z, sizing="reaction") -> Series           # ∈ [-1, 1]
def apply_guardrails(pos, util_decile, cot_pct) -> Series      # util≥9: cap short-spread at 25%; util≤2: cap long-backwardation/short-spread; cot>0.95 halve longs; <0.05 halve shorts
```
- Tests: `reaction(1)=1`, `reaction(0)=0`, `reaction(2)=2e^{-1.5}≈0.446`, monotone up on [0,1] and down on [1,3]; carry sign +1 on a backwardated synthetic curve; guardrail caps applied.
- DoD: [ ] functions, [ ] tests.

### Session B — `core/backtest.py` and strategy registry
```python
def backtest(pos, f01_adj_log_returns, spread_pnl=None, cost_bps=2.0) -> BacktestResult   # positions lagged one day; stats: ann log-return, ann vol, Sharpe (rf=0), max DD, Calmar, hit rate, turnover, worst-5, rolling 3y Sharpe
def fractionate(daily_pnl, conditioners: dict[str, Series], bins) -> DataFrame           # condition, bin, n, mean, sharpe, share_of_total
def inventory_predictability_test(s12, inventory) -> dict                                  # regress Δs12 on lagged inventory and inventory on lagged Δs12; page shows spreads predict inventories more than the reverse (Bouchouev) — guards against naive inventory→spread logic
```
Registry (`core/strategies.py`): CARRY_1_13 (sign carry, flat), CARRY_REACT (reaction of z(carry_pct), 10% vol target), MOM_100, CARRY_MOM (blend 0.5/0.5 → reaction), CONVEX_SPREAD (sign(cv123) on s12 + guardrails), SHORT_SPREAD_STATIC (−1 on s12, benchmark), FWD_SPREAD_MR (long S(k,k+1) below s12 / short above, k∈{3,6}), VALUE_OVERLAY (× (1+0.5·sign(value)) when |z|>1.5). Daily entrypoint `pipelines/derived/systematic.py` writes `derived.pos.<strategy>.<root>`.
- Tests: constant +1 position reproduces buy-and-hold log return exactly at zero cost; shifting returns by one day changes P&L (look-ahead guard); fractionation shares sum to 1±1e-6; CARRY_1_13 on real cl 1993–2022 within ±4 pp of 20.3% and Sharpe ±0.15 of 0.53 — **xfail if history absent, and on a miss the page prints the roll-rule/cost diagnostic rather than passing silently**.
- DoD: [ ] backtester, [ ] registry, [ ] daily positions in lake, [ ] benchmark comparison card.

### Session C — page `21_systematic.py`
Theme additions: `signal_board_table` (coloured z / position / guardrail state), `equity_drawdown_chart` (log equity + DD subplot, benchmark line), `reaction_curve_chart` (with current z marked), `fractionation_heatmap`, `crowding_quadrant_scatter`.
Visualisation spec: signal board per root; equity curves + rolling 3y Sharpe for every registry entry beside the published anchor; reaction function with live z; fractionation heatmap (strategy × regime / util decile / COT quintile / roll window / month) and share-of-total bars; crowding monitor (COT pct vs signal z, inflection quadrant shaded); the inventory-predictability test result as a permanent caption.
- DoD: [ ] page live, [ ] published-vs-repo deviation shown, [ ] ruff/mypy/pytest green.

## Definition of Done (spec)
- [ ] Sessions A–C. [ ] Daily positions entrypoint registered with Spec 13 orchestration. [ ] Index + CHANGELOG.

## Session A opener
> Read NOTES.md, specs/00_TRADING_CONVENTIONS.md, specs/21_systematic-engine.md. Plan Session A: `core/systematic.py` signals and sizing with tests, vectorised pandas only (no per-date loops). Read `core/curve.py` first and import from it rather than recomputing spreads.
