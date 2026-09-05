# Spec 21 — Systematic Strategies Engine

> See `specs/00_TRADING_CONVENTIONS.md`'s **Verified core API** section for real function signatures, schema columns and series IDs before importing any name this spec guesses.

**Sources:** Bouchouev *Virtual Barrels* Ch. 5–6. Published anchors to display beside repo estimates: carry C(1,13) ≈ 20.3% annualised log-return, Sharpe 0.53, 1993–2022, unleveraged; carry–momentum blend ≈ 24.7%, Sharpe 0.64; static short front spread ≈ IR 0.50. Conventions: `specs/00_TRADING_CONVENTIONS.md`.

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
- DoD: [x] functions, [x] tests.

#### Session A verification (2026-09-05)
`core/systematic.py` with all 15 functions; 32 tests in `tests/test_core_systematic.py`, all passing, including every acceptance value the spec names: `reaction(1)=1`, `reaction(0)=0`, `reaction(2)=2e^-1.5=0.446`, monotone up on [0,1] and down on [1,3], carry sign +1 on a backwardated curve, and each guardrail cap. Vectorised pandas throughout, no per-date loops; convexity is imported from `core/curve.py`, not recomputed.

Smoke-checked on the real lake (39 years of WTI), not only synthetic data: carry(1,3) backwardated on 49.0% of days with mean −0.043; `carry_pct` mean +1.2% annualised (p5/p95 −29.6%/+38.5%); reaction positions bounded to [−1, 1] with |pos|>0.5 on 65.5% of days; momentum/value correlation **−0.40**, negative by construction as the overlay requires; guardrails altered 12.5% of positions, taking mean |position| from 0.643 to 0.579 — binding without dominating.

**Ambiguity resolved explicitly.** The spec's low-utilisation guardrail reads "cap long-backwardation/short-spread", naming the trade twice. It is implemented as the symmetric counterpart of the high-utilisation rule: top-decile utilisation already implies contango so **shorts** are capped, bottom-decile implies backwardation so **longs** are capped. Both cap the position the inventory state already favours, which is the crowding logic the rule exists for. Recorded in `apply_guardrails`'s own docstring.

#### C(1,13) is not reproducible from this data — a miss, recorded
The spec's headline anchors are all C(1,13): carry ≈ 20.3% annualised, Sharpe 0.53, 1993–2022, and the carry–momentum blend at ≈ 24.7% / 0.64. That spread needs **rank 13**. The lake's only futures source is EIA's discontinued NYMEX route, which publishes **contracts 1–4 only** — so `carry(near=1, far=13)` cannot be computed at all, and Session B's "CARRY_1_13 on real cl 1993–2022 within ±4 pp" test cannot pass on any data currently obtainable.

`carry`'s `far=13` default is kept to match the spec, and raises a clear `KeyError` naming the missing rank rather than silently returning an empty series. Session B's registry must therefore either xfail that benchmark (as the spec's own text already anticipates: "xfail if history absent") or substitute a shorter, honestly-labelled spread such as C(1,3) — never relabel a C(1,3) result as the paper's C(1,13) anchor. Unblocking this needs a futures source with a deferred curve: IBKR (`python -m pipelines.futures.ibkr_preflight`) or a manual settlement CSV.

### Session B — `core/backtest.py` and strategy registry
```python
def backtest(pos, f01_adj_log_returns, spread_pnl=None, cost_bps=2.0) -> BacktestResult   # positions lagged one day; stats: ann log-return, ann vol, Sharpe (rf=0), max DD, Calmar, hit rate, turnover, worst-5, rolling 3y Sharpe
def fractionate(daily_pnl, conditioners: dict[str, Series], bins) -> DataFrame           # condition, bin, n, mean, sharpe, share_of_total
def inventory_predictability_test(s12, inventory) -> dict                                  # regress Δs12 on lagged inventory and inventory on lagged Δs12; page shows spreads predict inventories more than the reverse (Bouchouev) — guards against naive inventory→spread logic
```
Registry (`core/strategies.py`): CARRY_1_13 (sign carry, flat), CARRY_REACT (reaction of z(carry_pct), 10% vol target), MOM_100, CARRY_MOM (blend 0.5/0.5 → reaction), CONVEX_SPREAD (sign(cv123) on s12 + guardrails), SHORT_SPREAD_STATIC (−1 on s12, benchmark), FWD_SPREAD_MR (long S(k,k+1) below s12 / short above, k∈{3,6}), VALUE_OVERLAY (× (1+0.5·sign(value)) when |z|>1.5). Daily entrypoint `pipelines/derived/systematic.py` writes `derived.pos.<strategy>.<root>`.
- Tests: constant +1 position reproduces buy-and-hold log return exactly at zero cost; shifting returns by one day changes P&L (look-ahead guard); fractionation shares sum to 1±1e-6; CARRY_1_13 on real cl 1993–2022 within ±4 pp of 20.3% and Sharpe ±0.15 of 0.53 — **xfail if history absent, and on a miss the page prints the roll-rule/cost diagnostic rather than passing silently**.
- DoD: [x] backtester, [x] registry, [x] daily positions in lake, [~] benchmark comparison card — numbers below; the card itself is Session C's page.

#### Session B verification (2026-09-05)
`core/backtest.py` (backtest, spread_to_return, fractionate, inventory_predictability_test), `core/strategies.py` (all eight registry entries), `pipelines/derived/systematic.py` writing **168,157 position rows** across 6 strategies × 4 roots. 50 tests. Registered in `infra/run_scheduled.py`'s `weekly_fri` group after `derived_curve_ranks`.

Both of the spec's own acceptance guards pass: a constant +1 position reproduces buy-and-hold log return exactly at zero cost, and shifting the return series by one day changes the P&L. Fractionation shares sum to 1 ± 1e-6.

**Backtest on 39 years of real WTI, 2 bps costs:**

| Strategy | Ann log return | Vol | Sharpe | Max DD | Turnover | Published anchor |
|---|---|---|---|---|---|---|
| CARRY_REACT | 2.3% | 7.1% | **0.32** | −0.33 | 11.7 | 0.53 — but that anchor is C(1,13) |
| CARRY_MOM | 5.6% | 23.6% | 0.24 | −1.06 | 31.5 | 0.64 — also C(1,13) |
| MOM_100 | 2.2% | 23.7% | 0.09 | −1.44 | 32.5 | — |
| VALUE_OVERLAY | 2.1% | 23.5% | 0.09 | −1.22 | 31.5 | — |
| CONVEX_SPREAD | −10.2% | 24.4% | −0.42 | −4.20 | 50.9 | — |
| SHORT_SPREAD_STATIC | −0.2% | 24.4% | −0.01 | −1.10 | 0.0 | IR ≈ 0.50 |

The two carry entries run on **C(1,3)**, not the paper's C(1,13), so their Sharpes are not comparable to the published anchors and are not presented as if they were. `SHORT_SPREAD_STATIC` at −0.01 against a published IR of 0.50 is a genuine miss on a strategy that *is* directly comparable.

**Bouchouev's inventory-predictability claim does not reproduce.** On real Cushing stocks (`W_EPC0_SAX_YCUOK_MBBL`, n=1,165), inventories predict spreads slightly *more* than the reverse — the opposite of the book's finding:

| Direction | r² | t |
|---|---|---|
| spread → inventory | 0.0061 | −2.67 |
| inventory → spread | **0.0104** | **−3.50** |

Both relationships are weak. Caveat on record: Cushing stocks are weekly and the rank spread is daily, so the alignment (reindex + forward fill) blunts the test. This is displayed as a permanent caption on the page per the spec, showing the repo's own result beside the book's claim rather than asserting the book's.

**A real trap found and fixed: spread P&L units.** `backtest`'s `spread_pnl` must be in return units. Dividing a dollar spread change by the *spot* price is the obvious move and is wrong — it explodes as the price nears zero. Measured on the lake, that inflated calendar-spread annualised vol from **11.6% to 93.8%**, with three days in April 2020 doing all of it (WTI settled −$37.63 on the 20th, near $10 on the 21st). `spread_to_return` divides by a trailing median price instead: backward-looking, insensitive to one dislocation, never near zero.

**Also fixed: log signals on negative prices.** The same 2020-04-20 print made `np.log` emit a RuntimeWarning and propagate a silent NaN through momentum and value. `core.systematic.log_price` returns NaN cleanly for non-positive prices, confining the gap to windows that actually touch the print.

**Two strategies are skipped, never faked.** `CARRY_1_13` needs rank 13 and `FWD_SPREAD_MR` needs rank 7; EIA publishes 1–4. Both are registered, both report their missing ranks, and `build_positions` raises rather than returning a flat series — a flat position is a real trading decision and must never stand in for absent data.

### Session C — page `21_systematic.py`
Theme additions: `signal_board_table` (coloured z / position / guardrail state), `equity_drawdown_chart` (log equity + DD subplot, benchmark line), `reaction_curve_chart` (with current z marked), `fractionation_heatmap`, `crowding_quadrant_scatter`.
Visualisation spec: signal board per root; equity curves + rolling 3y Sharpe for every registry entry beside the published anchor; reaction function with live z; fractionation heatmap (strategy × regime / util decile / COT quintile / roll window / month) and share-of-total bars; crowding monitor (COT pct vs signal z, inflection quadrant shaded); the inventory-predictability test result as a permanent caption.
- DoD: [x] page live, [x] published-vs-repo deviation shown, [x] ruff/mypy/pytest green.

#### Session C verification (2026-09-05)
Five theme primitives (`signal_board_table`, `equity_drawdown_chart`, `reaction_curve_chart`, `fractionation_heatmap`, `crowding_quadrant_scatter`) with 12 tests, and page `apps/dashboard/pages/21_systematic.py` live across five tabs. Verified in a **real browser**, not only by import: `pytest -m browser -k systematic` passes, as does the page smoke test.

**Deviation is shown for one strategy only, deliberately.** The card prints a repo-vs-published deviation for `SHORT_SPREAD_STATIC` and withholds it everywhere else, with the reason on screen: every other anchor is measured on **C(1,13)** and this lake's carry strategies run on **C(1,3)**. Subtracting a C(1,3) Sharpe from a C(1,13) anchor would produce a number that looks like a result and is not one. `SHORT_SPREAD_STATIC` is the one directly comparable case and it misses badly — −0.01 against a published IR of 0.50, displayed rather than buried.

The two unavailable strategies get their own card naming the ranks they need, so a reader sees six of eight running and knows exactly why. The inventory-predictability test renders its non-reproduction as an `st.error` with the weekly-vs-daily caveat attached, per the spec's permanent-caption instruction.

`reaction_curve_chart` draws R(z) from the same formula the sizing uses, so the chart cannot drift from the behaviour it documents.

## Definition of Done (spec)
- [x] Sessions A–C. [x] Daily positions entrypoint registered with Spec 13 orchestration. [x] Index + CHANGELOG.

**Spec 21 is complete.** Carry forward: `CARRY_1_13` and `FWD_SPREAD_MR` remain registered but unrunnable until a futures source with a deferred curve exists (IBKR, or a manual settlement CSV) — at which point both should start working with no code change, since the registry already declares their rank requirements. Spec 22 replaces `core.systematic.vol_target`'s rolling standard deviation with real GARCH-MIDAS-EVT vol, and Specs 20/24/25/26/27 should now reuse `core/backtest.py` rather than building their own.

## Session A opener
> Read CLAUDE.md, specs/00_TRADING_CONVENTIONS.md, specs/21_systematic-engine.md. Plan Session A: `core/systematic.py` signals and sizing with tests, vectorised pandas only (no per-date loops). Read `core/curve.py` first and import from it rather than recomputing spreads.


## Verified against the source (2026-09-05)

The three published anchors were checked directly against Bouchouev, *Virtual Barrels*
(Springer, 2023). All three figures are correct as stated. Two surrounding claims were not.

| Anchor | Book | Page |
|---|---|---|
| Carry C(1,13): 20.3% annualised log-return, Sharpe 0.53 | confirmed verbatim | p.99, Fig 5.6 |
| Carry-momentum: 24.7% annualised, Sharpe 0.64 | confirmed verbatim | p.101 |
| Static short front spread: 0.50 | confirmed verbatim | p.112 |

"IR 0.50" is fine: footnote 6 (p.92) states the book uses information ratio and Sharpe
ratio interchangeably, both being return over volatility with a zero benchmark.

**Correction 1 — the sample period.** This spec said **1992–2022**. The book says
**1993–2022** throughout: Fig 5.1 and Fig 5.6 are both captioned "(1993–2022)", and the
static-spread result is "the thirty-year period starting from 1993". Corrected here and in
`core/strategies.py::_BOUCHOUEV`.

**Correction 2 — `CARRY_MOM` was not the strategy the 24.7%/0.64 anchor measures.** The
book defines carry-momentum as

> π_CM(F_t) = sign(C_t − MA_t(C_t; n))

— momentum applied to **carry**, on the annual carry C(1,13). This spec's registry line
instead specifies "CARRY_MOM (blend 0.5/0.5 → reaction)", a blend of carry and *price*
momentum. Those are different strategies, so the anchor was crediting our blend with a
result it never produced.

Resolved by adding a ninth registry entry, `DYNAMIC_CARRY`, implementing the book's
definition via `core.systematic.momentum_on_carry` (which existed from Session A and was
wired into nothing). The anchor moved to it; `CARRY_MOM` keeps the spec's blend and now
carries **no** published benchmark, with the reason in its `note`. Because the book uses
C(1,13), `DYNAMIC_CARRY` needs rank 13 and gates off on this lake exactly like
`CARRY_1_13` — the honest outcome, since the anchor now sits on a strategy that genuinely
cannot be run here rather than on one that can.
