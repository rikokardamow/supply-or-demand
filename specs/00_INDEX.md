# Energy Dashboard — Claude Code Spec Pack (Index)

**Owner:** Riko | **Start:** Fri 22 Aug 2026, ~21:00 Dublin | **Budget:** 3–4 h/day weekends, ≤1 h some weekdays

This pack contains one self-contained spec document per sub-project. Each document is written to be
dropped into the repo (under `specs/`) and referenced directly in a Claude Code session, e.g.:

> "Read specs/01_eia-padd.md and CLAUDE.md. Execute Session 2 exactly as written. Plan first, then implement."

## How to use this pack

1. **Before anything else:** rotate every API key that has ever been stored in plain-text notes
   (EIA, Ember, GIE, ENTSO-E, FRED, NewsAPI, WorldNews, ECMWF, tomorrow.io, Mapbox, IBKR password).
2. Copy `CLAUDE.md` to the repo root. Copy the numbered specs into `specs/`.
3. Work through the specs in numeric order. Do not skip `00_project-setup.md` — every other
   spec assumes `core/` exists.
4. One Claude Code session = one "Session" block inside a spec. Never start a session you cannot
   finish inside your time block. Always end green: tests pass, work committed.
5. Each spec ends with a **Definition of Done** — do not move to the next spec until it is met,
   or you have consciously descoped (write the descope decision into the spec file itself).

## Build order & dependency graph

```
00 setup (core/, theme, shell)          ── blocks everything
01 EIA PADD & WPSR                       ── first real page, quick win
02 GIE AGSI+/ALSI+ gas storage           ── quick win
03 ENTSOG EU gas flows                   ── needs core; slowest mapping work
04 ENTSO-E power + EirGrid               ── independent of 03
05 US gas & power (EIA + gridstatus)     ── reuses 01's EIA client
06 OPEC / JODI / Baker Hughes supply     ── independent
07 Refinery cracks (ib_async)            ── needs IB Gateway on your machine
08 Weather (Open-Meteo + ECMWF)          ── independent; GRIB learning curve
09 News & event tagging                  ── overlays onto all price/flow pages
10 Macro/FX normalisation                ── small; feeds all pages
11 AIS vessels                           ── hardest; do last
12 Flights (OpenSky)                     ── small; OAuth2
13 Orchestration, tests, CI              ── after pipelines exist
14 Analytics layer                       ── cross-spec, adds no new data sources of its own
                                             beyond §0.4 (EIA storage capacity, CFTC COT);
                                             run its lettered sessions (14-A..14-H) only once
                                             each session's "Depends on" specs are done
15 OFAC SDN sanctions                    ── independent; overlays onto 11 once AIS lands
16 NewsAPI supplement                    ── extends 09; manual-only, ToS-limited, never scheduled
17 Adanos sentiment overlay               ── independent; new pipeline, feeds page 10
```

## Calendar mapping (from the master plan)

| Weeks | Specs |
|---|---|
| 1–2 | 00, 01 |
| 3 | 02 |
| 4–5 | 03 |
| 6 | 04 |
| 7 | 05 |
| 8–9 | 06 |
| 10–11 | 07, 10 |
| 12–13 | 08 |
| 14 | 09 |
| 15 | 12 |
| 16–18 | 11 |
| 19–20 | 13 + polish |
| 21+ | 14 (analytics layer, one lettered session at a time) |
| 22 | 15 |
| 23 | 16, 17 |

## Non-negotiable house rules (repeated in every spec)

- Secrets only via `core.settings` from `.env`. Never printed, logged, or committed.
- Pipelines write the lake; dashboard pages read the lake. Pages never call external APIs.
- All scalar series → `ts_long` schema. All directional data → `flows` schema.
- Seasonal statistics always exclude 2020.
- Every chart uses `core.theme` (Kardamow house style). British English labels.
- Every pipeline gets a vcrpy cassette test. CI never hits live APIs.

## Trading analytics layer (Specs 18–27)

Conventions: `specs/00_TRADING_CONVENTIONS.md`. Dependency order: 18 → 19 → 21 → 22, then 20 / 24 / 25 / 26 in any order, 23 and 27 any time after 18. **Spec 18 Session A (futures settlements pipeline) blocks 18, 20, 21, 24.**

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 18 | Curve & market structure (futures pipeline, spreads, convexity, regime, index rolls, Cushing coupling) | Sessions A–D all done; page live in browser. **Real futures data landed 2026-09-05**: 113,750 `fut.*` rows from EIA (NYMEX ranks 1–4, 1980–2024, discontinued route) + a reconstructed 89-month Brent curve from a Barchart spreads export (2026-09-04), front month validated to the cent against the published settlement. IBKR preflight built and a real chunking bug in `get_settles` fixed; Gateway still not connected | **yes — EIA futures (history) + Barchart manual CSV (curve) + IBKR (live, pending)** | 01, 14 |
| 19 | Fundamentals & physical (spare capacity, inventory bands, quality mismatch, COT percentiles, benchmark health, OSP) | Sessions A-C all done; page live in browser | **yes — CFTC COT (real, live Public Reporting Environment API)** + manual: Platts/Argus diffs, OSPs (`pipelines/manual_physical/` built, no real drops yet) | 01, 06, 10, 14, 18 |
| 20 | Refining economics & crack VECM (Murat & Tokat 2009) | **Complete (A–C).** C: ECT signal + page 20 live; the shift test caught a real look-ahead bug (full-sample median in the vol scaling). Backtest engine and vol scaling are stand-ins until Specs 21/22 exist — flagged in the UI. Sessions A–B done. A: `core/cracks.py` boards, 5 crack series (45,476 rows), cross-check vs EIA API exact (max diff 0.0). B: `core/vecm.py` + monthly `vecm_refit` entrypoint; all synthetic acceptance tests pass, but on real data the model **fails out-of-sample** (Theil U 1.07, DM p=0.07 worse than RW) because the spot crack is **not I(1)** — a margin mean-reverts, so the cointegration framework doesn't transfer. April 2003 **not** recovered (finds 2005-03). Both are consequences of spot legs, not futures. **Session C should not proceed until Spec 18 has real futures, or must ship the failure on the model card** | **yes — 3 FRED spot product legs added to Spec 10's pipeline** (`dgasnyh`, `dgasusgulf`, `dhoilnyh`); new deps `statsmodels`/`ruptures`/`arch` | 18, 10 |
| 21 | Systematic strategies engine (Bouchouev: carry, momentum, value, convexity, reaction function, fractionation) | **Complete (A–C).** `core/systematic.py`, `core/backtest.py`, `core/strategies.py`, 168,157 position rows, page 21 live and browser-verified. 6 of 8 strategies run — `CARRY_1_13` (rank 13) and `FWD_SPREAD_MR` (rank 7) skipped, EIA publishes 1–4. Published C(1,13) anchors not comparable; `SHORT_SPREAD_STATIC` misses (−0.01 vs IR 0.50). Bouchouev's inventory-predictability claim **does not reproduce** | no | 18, 19 |
| 22 | Risk engine (GARCH-MIDAS-EVT VaR, backtests, stress, margin) | not started | manual: book, margins | 18, 10, 21 |
| 23 | Macro & cross-asset signals (Yamarone signals, GFU regression) | not started | manual: GFU index, consensus calendar | 10, 18 |
| 24 | Volatility & options (surface, CSO/Bachelier, virtual storage, dealer gamma) | not started | options settlements (same pipeline as 18) | 18, 14, 21 |
| 25 | Freight & arbitrage (Adland & Alizadeh TC–FFA, landed-cost arbs) | not started | manual: Baltic/FFA/fixtures | 18, 19 |
| 26 | Gas analytics (netbacks, basis map, storage economics, indexation) | not started | manual: basis hubs, contract mix | 02, 05, 08, 10, 18 |
| 27 | Trade journal, playbook, Kardamow validation ledger | not started | no | 18, 21 |

## Spec 28 — Geopolitical Risk Premium (GRP)

Specs 28.00–28.11 comprise the GRP module. This module is built against `specs/28_ADAPTATION.md`, not the Postgres / FastAPI / Grafana stack its own text assumes. Specs 11 (AIS vessels) and 12 (flights) remain unbuilt and block GRP's airspace and maritime components.

## Spec 29 — Self-hosted social sentiment

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 29 | Self-hosted social sentiment (Reddit / Polymarket / StockTwits), scored in-repo and shown beside Adanos with the deviation | **Complete (Tasks 0–9).** `pipelines/social/` (Reddit RSS + Polymarket + StockTwits pulls), `core/sentiment.py` (VADER scoring, Adanos overlap/deviation/rolling correlation) and a new "Self-hosted social sentiment" section on page `10_macro.py` (comparison, deviation, Set B topic attention, Polymarket tag attention) are all live; full suite, ruff, mypy all green. **Polymarket has no keyword search**: live probes found `q`/`search` are silently ignored (HTTP 200, identical unfiltered listing regardless of value) — the only real filter is `tag_slug`, so it contributes one tag-level series ("energy"), not per-topic coverage across Set B's seventeen topics. **Reddit's unauthenticated RSS rate limit is ~1 request/60s**, so a full run costs 58 Reddit + 12 StockTwits + 1 Polymarket = 71 requests, wall-clock dominated by ~58 minutes of throttled Reddit calls | **yes — Reddit RSS, Polymarket, StockTwits (all self-hosted, no vendor)**; new dep `vaderSentiment` confirmed (rule 7) | 17 |

Adds `pipelines/social/` and `core/sentiment.py`, extends page `10_macro.py`. Covers the
live-confirmed Adanos gap recorded in `pipelines/adanos/CLAUDE.md` (the five OPEC/OPEC+
exposure tickers resolve but return near-zero buzz) and adds commodity/geopolitical topic
queries a ticker basket cannot express. Adanos is retained, not replaced.
