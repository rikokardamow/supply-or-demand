# Trading Analytics Layer — Runbook for Claude Code (Specs 18–27)

This file is the entry point. Read it first in every session that touches Specs 18–27, then `CLAUDE.md`, then `specs/00_TRADING_CONVENTIONS.md`, then the one spec being worked on. Nothing else needs to be read up front.

---

## 1. What you are building

Specs 01–17 built a data lake (DuckDB + Parquet, `core/storage.py`) fed by per-source pipelines, and a Streamlit research dashboard on top of it. Specs 18–27 add a **desk-grade trading analytics layer** on the same lake for the same app: forward-curve structure, systematic signals and backtests, a risk engine, forecast models, options analytics, freight, gas analytics, and a trade journal that also scores the publication's own articles.

The layer introduces exactly one new scheduled upstream source — futures and options settlements (Spec 18) — plus a handful of manual CSV drops. Everything else is computed from data the lake already holds.

## 2. Where things go (there is no new package tree)

| You need to write… | Put it in | Copy the pattern from |
|---|---|---|
| An ingestor (API client or manual-CSV reader) | `pipelines/<source>/` via `/new-pipeline <source>` — client, `CLAUDE.md`, cassette or fixture test, `pull_*.py` entrypoints | `pipelines/eia/`, `pipelines/gie/`, `pipelines/entsoe/` |
| Pure analytics, models, signals, backtests | one flat module per spec in `core/` — `core/curve.py`, `core/fundamentals.py`, `core/cracks.py`, `core/vecm.py`, `core/systematic.py`, `core/backtest.py`, `core/strategies.py`, `core/risk.py`, `core/risk_desk.py`, `core/macro_signals.py`, `core/predictive.py`, `core/vol.py`, `core/cso.py`, `core/structures.py`, `core/freight.py`, `core/arb.py`, `core/gas_analytics.py`, `core/gas_strategies.py`, `core/journal.py`, `core/ledger.py` | `core/macro.py`, `core/seasonal.py` |
| A step that writes derived series back to the lake | `pipelines/derived/<topic>.py` — a thin script calling `core/` functions and `core.storage` writes; registered with Spec 13's orchestration | Spec 13 daily entrypoints |
| A chart primitive in house style | `core/theme.py` | `seasonal_range_chart`, `revision_waterfall`, `hour_day_heatmap` |
| A page-specific composite (map, board) | `apps/dashboard/components/` | `padd_map.py`, `news_map.py`, `event_overlay.py` |
| A page | `apps/dashboard/pages/NN_<name>.py` via `/new-page <name>`, every section inside `card(title)`, reads the lake only | pages 01–15 |
| Tests | `tests/test_<topic>.py`; pure-function tests on synthetic data with the numeric assertions from the spec; cassettes only for clients | existing suite |
| Manual data | `data/manual/<source>/*.csv` (git-ignored) read by `pipelines/manual_<source>/`, written with `source="manual"` and the file's as-of date as `revision_date` | `quotas.csv` (Spec 06) |

Rules that never bend: `core/` modules never touch DuckDB; pages never call an API; series IDs are lowercase dotted (`fut.cl.z26.settle`, `derived.spread.cl.s12`); values are written as float64 (v0.11 lesson); spreads are never computed from a back-adjusted series; a signal at date *t* uses only rows whose `date` **and** `release_date` are ≤ *t*.

## 3. How every session runs

1. **Open in plan mode.** Read this file, `CLAUDE.md`, `00_TRADING_CONVENTIONS.md`, and the one spec. Read the `core/` modules and lake series the spec says to import from — confirm they exist before planning; do not guess signatures or series IDs.
2. **Plan** the single session named in the prompt (A, B, C or D): files to create or modify, functions with signatures, tests, the live cross-check you will perform. Stop and show the plan.
3. **Implement** after approval. Vectorised pandas; no per-date Python loops except roll handling.
4. **Verify**: `uv run pytest`, `uv run ruff check .`, `uv run mypy core pipelines` green; run the page in the browser and check every new card renders with real data and a caption naming its source and any proxy; perform the spec's cross-check against an independent source and record the numbers.
5. **Close out**: tick the session's Definition-of-Done boxes in the spec *with the verification actually performed*; add the CHANGELOG entry; update the status column in `specs/00_INDEX.md` when a spec completes; commit with the `feat(<topic>): Spec NN Session X -- …` convention.
6. One session per sitting. The next session starts fresh.

If a data source turns out not to exist, is paywalled, or behaves differently from the spec (as happened in Specs 04–06), do what those specs did: confirm it live, document the correction in the spec and the pipeline `CLAUDE.md`, render the card in a visible NO-DATA state, and move on. Never fabricate data and never silently substitute a proxy.

## 4. Order of work and the one blocker

```
18A (futures pipeline)  ──►  18B → 18C → 18D
                             │
                             ├──► 19A → 19B → 19C
                             │        │
                             │        └──► 21A → 21B → 21C ──► 22A → 22B → 22C
                             │                    │
                             │                    ├──► 20A → 20B → 20C
                             │                    ├──► 24A → 24B → 24C
                             │                    ├──► 25A → 25B → 25C
                             │                    ├──► 26A → 26B → 26C
                             │                    └──► 27A → 27B → 27C → 27D
                             └──► 23A → 23B → 23C  (any time after 18)
```

**Spec 18 Session A is the gate.** Nothing in the lake holds the futures curve today, and Specs 18, 20, 21 and 24 cannot run without it. The pipeline ships two clients behind one interface — `IBKRClient` (ib_insync; the same local-gateway prerequisite as the deferred Spec 07) and `ManualCSVClient` (`data/manual/futures/settles_YYYYMMDD.csv`) — selected by `FUTURES_SOURCE` in `.env`. The session prompt will state which one is live on this machine; build both, verify the live one.

## 5. What each spec does and how to implement it

**Spec 18 — Curve & market structure.** Sessions: A futures/options settlements pipeline (both clients, history + idempotent daily pull, `series_meta` expiries, the float64 regression test). B `core/curve.py`: nearby ranks with a 5-business-day roll, ratio back-adjustment for returns only, spread strips, convexity `cv = F1 − 2F2 + F3`, the six-state regime classifier, derived series written by `pipelines/derived/curve.py`. C index-roll calendar (GSCI business days 5–9, BCOM 6–10, 20 %/day, in `core/calendars.py`), Cushing utilisation and decile, physical-differential bands. D page 18 with the curve-strip, regime-ribbon, Cushing scatter and roll-heatmap primitives added to `core/theme.py`. Exposes the curve API every later spec imports.

**Spec 19 — Fundamentals & physical.** Analytics over Specs 01/06/10/14 plus a `manual_physical` reader (agency spare capacity, grade differentials, OSPs, benchmark-health counts). A inventory bands (a wrapper over `core.seasonal`, 2020 excluded), days of cover, two-agency spare capacity with the disagreement shown, COT percentiles → guardrail series in the lake. B quality spreads, Carollo's stock-change scatter diagnostic, shale response, benchmark health, OSP signal. C page 19. This spec produces *conditioning variables*, never trade signals.

**Spec 20 — Cracks & VECM.** A crack boards (3-2-1, 2-1-1, RBOB, HO, NWE gasoil, Singapore) with unit conversions and derived series; supersedes the crude/product-crack part of the deferred Spec 07. B the Murat & Tokat pipeline in `core/vecm.py`: unit roots → structural break (must recover **April 2003** on 1993–2008) → Johansen → VECM → Granger → rolling-origin evaluation with Diebold–Mariano vs random walk; monthly refit entrypoint. C the error-correction signal backtested through Spec 21 and page 20 with the model-monitor card.

**Spec 21 — Systematic engine.** A `core/systematic.py`: momentum, carry C(1,13), value, convexity, momentum-on-carry, z-scores, the reaction function `R(z) = z·exp(0.5(1−z²))`, vol targeting, storage-boundary and crowding guardrails. B `core/backtest.py` (positions lagged one day, costs, full stat set, fractionation by regime / Cushing decile / COT quintile / roll window) and the strategy registry writing `derived.pos.*` daily; the benchmark card compares the repo's carry result with the published 20.3 % / 0.53 and prints a diagnostic on a miss rather than passing. C page 21. Every other spec's backtests reuse this engine.

**Spec 22 — Risk engine.** A GARCH-MIDAS-EVT in `core/risk.py` (scipy MLE, Beta lag weights, GPD tail at the lower decile, rolling ~2000-day window, Kupiec and Christoffersen backtests, the pass/fail matrix with historical simulation shown failing); refit entrypoint; exposes `realised_vol` to Spec 21. B desk risk: exposure trees, `scenarios.yaml` (2008, 20 Apr 2020, 7 Mar 2022, parallel/twist/flip/vol/basis shocks), margin path vs credit line, hedge effectiveness, liquidity/strike availability; manual book and margin readers. C page 22.

**Spec 23 — Macro signals.** Extends Spec 10 rather than replacing it. A Yamarone board in `core/macro_signals.py` (ISM new-orders-minus-inventories, NO−P with the −20 threshold, the three-negative-payrolls rule, ISM prices vs WTI, surprise z, persistence diagnostics) after confirming each new FRED ID live. B `core/predictive.py`: the GFU predictive regression with Newey–West and wild bootstrap, expanding-window OOS, Campbell–Thompson R², Clark–West, a ~23-predictor horse race, economic value, and the monthly `derived.tilt.gfu` consumed by Spec 21; both published R² figures shown beside the repo's. C page 23.

**Spec 24 — Volatility & options.** A extend both Spec 18 clients to option chains and CSOs; Black-76 and Bachelier pricers, implied vols, per-expiry smile fit, skew metrics, vol cone. B dealer negative-gamma profile, CSO implied normal vols, local-vol term structure with the no-arbitrage flag, the virtual-storage strategy (long-dated CSO, Bachelier delta hedge weekly, exit 45 days before expiry) backtested through Spec 21. C hedge-structure pricers and page 24.

**Spec 25 — Freight & arbitrage.** All inputs are manual drops (Baltic indices are on the do-not-schedule list). A `core/freight.py`: TC vs FFA-equivalent differential, cointegration, ARMA-X with the published Adland & Alizadeh coefficients displayed beside the estimates, hedge-ratio adjustment, differential signal. B landed-cost arbs (WS conversion, transatlantic, east–west, TC2/TC5/TC14, persistence). C page 25; the differential backtest is captioned as statistical, not riskless, arbitrage.

**Spec 26 — Gas analytics.** Analytics over Specs 02/05/08/10 and Spec 18's ng/tfm/nbp/jkm curves; pages 02 and 05 stay untouched. A conversions, hub board, US LNG netbacks with the cancellation floor, basis map with constraint flags, EU fill trajectory, degree-day anomaly, storage-spread economics, oil-indexation tracker; `manual_gas` reader. B storage-spread, widow-maker, basis-constraint and JKM–HH convergence strategies registered in Spec 21, plus the HH-proxy basis-risk card. C page 26.

**Spec 27 — Journal, playbook, Kardamow ledger.** A four state tables (`journal`, `playbook`, `kardamow_ledger`, `ledger_audit`) following the Spec 15 `SANCTIONS_SCHEMA` precedent; the playbook seed of Johnson's 40 chapters plus six supplementary cards — titles, contributors, categories and page references only, no book text. B journal logic: `log_signal_trade` snapshots regime state at the trade's `as_of`, `close_trade` splits P&L into directional / carry / vol / slippage; wired to Spec 21's daily positions so a strategy flip logs a trade. C the ledger: parse an article's falsifiable close into trigger / outcome / channel / level / horizon, snapshot marks, resolve, score on four 0–25 axes (right outcome via the wrong channel caps the channel score at 10), hit rate excluding untested gauges, calibration, thesis drift, follow-up stubs. D page 27 with forms; the first ten archive pieces are parsed by hand.

## 6. Prompt templates

**Registration (run once, before 18A):**
> Read specs/TRADING_LAYER_RUNBOOK.md, CLAUDE.md and specs/00_TRADING_CONVENTIONS.md. Append specs/INDEX_ADDITION.md to specs/00_INDEX.md and specs/CLAUDE_MD_ADDITION.md to CLAUDE.md, then delete both. Read core/schemas.py, core/storage.py, core/seasonal.py, core/theme.py, core/calendars.py and add a "Verified core API" section to the end of specs/00_TRADING_CONVENTIONS.md listing the exact ts_long read/write signatures, the seasonal_stats signature, the existing theme primitives, and which Spec 14 CFTC and Cushing-capacity series IDs exist in the lake. No other changes. Commit "docs: register Specs 18–27 trading layer".

**Any build session:**
> Read specs/TRADING_LAYER_RUNBOOK.md, CLAUDE.md, specs/00_TRADING_CONVENTIONS.md and specs/NN_<name>.md. Plan **Session X** only, per the runbook's §3. [For 18A add: Futures source live on this machine: IBKR gateway on port 7497 / manual CSV at data/manual/futures/settles_YYYYMMDD.csv.] Show the plan before implementing.

**Close-out reminder (if it forgets):**
> Tick Session X's DoD boxes in specs/NN_<name>.md with the verification you actually ran, add the CHANGELOG entry, and commit.
