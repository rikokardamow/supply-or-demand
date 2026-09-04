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
| 18 | Curve & market structure (futures pipeline, spreads, convexity, regime, index rolls, Cushing coupling) | not started | **yes — futures settlements (IBKR or manual CSV)** | 01, 14 |
| 19 | Fundamentals & physical (spare capacity, inventory bands, quality mismatch, COT percentiles, benchmark health, OSP) | Sessions A-C all done; page live in browser | **yes — CFTC COT (real, live Public Reporting Environment API)** + manual: Platts/Argus diffs, OSPs (`pipelines/manual_physical/` built, no real drops yet) | 01, 06, 10, 14, 18 |
| 20 | Refining economics & crack VECM (Murat & Tokat 2009) | not started | no | 18, 10 |
| 21 | Systematic strategies engine (Bouchouev: carry, momentum, value, convexity, reaction function, fractionation) | not started | no | 18, 19 |
| 22 | Risk engine (GARCH-MIDAS-EVT VaR, backtests, stress, margin) | not started | manual: book, margins | 18, 10, 21 |
| 23 | Macro & cross-asset signals (Yamarone signals, GFU regression) | not started | manual: GFU index, consensus calendar | 10, 18 |
| 24 | Volatility & options (surface, CSO/Bachelier, virtual storage, dealer gamma) | not started | options settlements (same pipeline as 18) | 18, 14, 21 |
| 25 | Freight & arbitrage (Adland & Alizadeh TC–FFA, landed-cost arbs) | not started | manual: Baltic/FFA/fixtures | 18, 19 |
| 26 | Gas analytics (netbacks, basis map, storage economics, indexation) | not started | manual: basis hubs, contract mix | 02, 05, 08, 10, 18 |
| 27 | Trade journal, playbook, Kardamow validation ledger | not started | no | 18, 21 |
