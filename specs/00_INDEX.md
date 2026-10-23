# Energy Dashboard — spec index

**Owner:** Riko | **Start:** Fri 22 Aug 2026, ~21:00 Dublin | **Budget:** 3–4 h/day weekends, ≤1 h some weekdays

This pack contains one self-contained spec document per sub-project. Each document is written to be
dropped into the repo (under `specs/`) and worked through one session at a time, e.g.:

> "Read specs/01_eia-padd.md and DEVELOPMENT.md. Execute Session 2 exactly as written. Plan first, then implement."

## How to use this pack

1. **Before anything else:** rotate every API key that has ever been stored in plain-text notes
   (EIA, Ember, GIE, ENTSO-E, FRED, NewsAPI, WorldNews, ECMWF, tomorrow.io, Mapbox, IBKR password).
2. Keep `DEVELOPMENT.md` at the repo root. Copy the numbered specs into `specs/`.
3. Work through the specs in numeric order. Do not skip `00_project-setup.md` — every other
   spec assumes `core/` exists.
4. One sitting = one "Session" block inside a spec. Never start a session you cannot
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
| 29 | Self-hosted social sentiment (Reddit / Polymarket / StockTwits), scored in-repo and shown beside Adanos with the deviation | **Complete (Tasks 0–9).** `pipelines/social/` (Reddit RSS + Polymarket + StockTwits pulls), `core/sentiment.py` (VADER scoring, Adanos overlap/deviation/rolling correlation) and a new "Self-hosted social sentiment" section on page `10_macro.py` (comparison, deviation, Set B topic attention, Polymarket tag attention) are all live; full suite, ruff, mypy all green. **Polymarket has no keyword search**: live probes found `q`/`search` are silently ignored (HTTP 200, identical unfiltered listing regardless of value) — the only real filter is `tag_slug`, so it contributes one tag-level series ("energy"), not per-topic coverage across Set B's seventeen topics. **Reddit's unauthenticated RSS rate limit is ~1 request/60s**, so a full run costs 58 Reddit + 12 StockTwits + 1 Polymarket = 71 requests, wall-clock dominated by ~58 minutes of throttled Reddit calls. **Populated-page rendering verified 2026-09-06** against a real pull and a real screenshot, not just against unit tests — see below | **yes — Reddit RSS, Polymarket, StockTwits (all self-hosted, no vendor)**; new dep `vaderSentiment` confirmed (rule 7) | 17 |

Adds `pipelines/social/` and `core/sentiment.py`, extends page `10_macro.py`. Covers the
live-confirmed Adanos gap recorded in `pipelines/adanos/NOTES.md` (the five OPEC/OPEC+
exposure tickers resolve but return near-zero buzz) and adds commodity/geopolitical topic
queries a ticker basket cannot express. Adanos is retained, not replaced.

**Rendering verified 2026-09-06.** A full pull wrote 1574 `ts_long` rows and 945 events,
then exited 1 on `core.failures.PartialFailureError` after one Reddit 429 on the
`dubai_swap` topic — data was written before the failure surfaced, and the non-zero exit is
honest: that one subject of 29 wrote no rows at all rather than zeros. All 945 social events
came back severity 1, confirming the fix for a defect where the news tagger's
`extract_severity` had been scoring Reddit chatter up to severity 3, which would have
rendered on price charts through `event_overlay.py`'s `severity >= 2` filter. The pull-dated
snapshot series now exist (11 rows, all dated 2026-09-06), and `overlap()` returns
`overlap_days=1` for XOM, CVX, XLE and COP — up from 0 for 10 of 12 tickers before the axis
fix. The page was rendered in a real browser against this data: the comparison panel draws,
annotated "1 overlapping day · 1 dropped · 0% sign agreement", and topic attention shows
real post counts.

One overlapping day is not a finding: the deviation panel is mechanically correct but says
nothing yet, and needs several weekly pulls before vendor-versus-self-hosted disagreement can
be read at all. Separately, the dashboard caches lake reads
(`apps/dashboard/components/lake.py`), so a running app shows pre-write data until
restarted — this is why a first screenshot showed "no overlap yet" while the lake already
had the row.

## Spec 30 — EIA price coverage

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 30 | EIA price coverage (refiner acquisition cost by grade, retail pump prices, gas citygate/sectoral prices, generator delivered fuel cost) | **Done. Live-verified 2026-09-06**: 14,343 monthly + 20,628 weekly rows written from the real EIA API — refiner acquisition cost (rac2, 3,243 rows), retail pump prices (gnd, 20,628 rows), gas citygate/sectoral prices (pri/sum, 1,878 rows) and generator delivered fuel cost (electric-power-operational-data, 5,719 rows across a new `EIAClient.get_operational_series` method, since that route has no `series` facet at all). A fifth route, `petroleum/pri/land3` (gravity-banded landed cost of imported crude, 3,503 rows), was **not in the original plan** — found live by walking `GET /v2/petroleum/pri`'s category tree — and shipped because it is the only route that answers the spec's "landed cost by API gravity band" chart. Two of the spec's named candidates were **deliberately not ingested**: `natural-gas/pri/fut` duplicates `fred.dhhngsp` (Henry Hub spot, the lake's existing gas price) and Spec 18's own NYMEX futures ingestion (`RNGC1`..`RNGC4`) under a second convention — a Spec 18 job, not Spec 30's; `natural-gas/pri/rescom` carries no national-level series at all, and `pri/sum` already supplies the national residential/commercial/industrial rollups it was expected to provide. Fixed a real crash in the shared `EIAClient.get_series` (a literal EIA `null` value blew up `float(None)` on early-history rows of `pri/sum`) — the fix now skips null-value rows, changing behaviour for all eleven routes already using `get_series`, not just Spec 30's new ones. Revision behaviour (PMM/EPM restating prior months must replace, not duplicate) verified both by a new isolated unit test and by re-running the real monthly pull twice against the live lake — row counts held steady both times. One gap found during the final verification gate and closed the same task: `pull_prices_weekly.py` was missing the `if __name__ == "__main__":` guard every sibling weekly entrypoint has, so `python -m pipelines.eia.pull_prices_weekly` silently exited 0 having pulled nothing — it always ran correctly through `infra/run_scheduled.py`, which calls `.main()` directly, so the scheduled cadence was never affected. Fixed by adding the guard; re-verified live, the module now writes 20,628 rows when run standalone. Full suite green (723 passed), `ruff`/`mypy` clean | **no new vendor — five routes on the existing EIA API client (one, `land3`, discovered live)** | 01 |

The lake holds volumes almost everywhere and prices almost nowhere: one gas price
(`fred.dhhngsp`), no retail pump prices at all, and no grade-differentiated crude price beneath
Spec 19s quality-mismatch work or Spec 20s crack VECM. Spec 30 supplies those missing
denominators. Extends `pipelines/eia/`, adds no schema and no new pipeline package.

## Spec 31 — EIA coverage extensions

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 31 | EIA coverage extensions (gas storage capacity, Grid Monitor for ERCOT/PJM, gas consumption by sector, power-sector coal, biofuels capacity and feedstocks, weekly ethanol) | **Complete — all six items live-verified. Plan 31C (items 4, 5, 6) shipped 2026-09-09**, closing out plans 31A (items 1, 3) and 31B (item 2), both already merged to `main`. **Item 2**: hourly demand/generation-by-fuel/interchange for 8 of EIA's 65 Lower-48 balancing authorities (`ERCO`, `PJM`, `MISO`, `SWPP`, `CISO`, `NYIS`, `ISNE`, `US48`) — the large gas-burning markets `pipelines/gridstatus_iso/` cannot reach (ERCOT blocked by bot protection, PJM needs a Data Miner 2 key this project doesn't hold) plus the national aggregate. **Not** the other 57 BAs — hourly-only data with no daily/monthly rollup makes full 65-BA coverage load-research-scale volume, which the spec explicitly rules out. Real 90-day backfill, live against the EIA API: 68,075 demand/generation/forecast/interchange rows (`pull_rto_demand.py`), 118,072 fuel-mix rows (`pull_rto_fuel_mix.py`), 90,066 interchange rows across 45 corridors (`pull_rto_interchange.py`) — all three now scheduled daily in `infra/run_scheduled.py`. ERCOT and PJM gas-fired generation confirmed non-empty and spanning the full window (2,147 and 2,146 rows) — the entire justification for this item. The interchange double-count guard (`replace_window` derived from the pulled frame's own timestamps) was proved live: re-running the same 3-day pull twice left the lake's total `flows` row count unchanged both times (100,092 → 100,092 → 100,092), not growing by a window's worth. Minted series-id schemes `RTO.REGION.*`/`RTO.FUEL.*` are permanent once written; the `REGION`/`FUEL` segment exists specifically because `type=NG` (net generation) and `fueltype=NG` (natural gas) are the same code on two different facets and would otherwise collide. **Item 1/3 (31A)**: gas storage capacity and gas consumption by sector both live-verified 2026-09-06, scheduled monthly; the fullness ratio's page section is still not shipped, blocked on a concurrent session's permission for `apps/dashboard/**`. **Item 4 (coal), new `pipelines/coal/`**: 510 rows across 5 series (`COAL.RECEIPTS/CONSUMPTION/STOCKS/PRICE/HEAT_CONTENT.US-98.Q`), live-verified 2026-09-09 — `source="coal"` confirmed genuinely its own (`read_ts_long(source="coal")` returns exactly `{"coal"}`, never `"eia"`), the single most important check in the plan. `heat-content`'s unit label carries a real EIA-side bug (mislabelled as a sulfur percentage) — stored verbatim, documented, not silently fixed. Coal Markets basin spot prices, API2/API4 and weekly coal production are named exclusions, not silent gaps — no EIA route carries any of them. **Item 5 (biofuels)**: `petroleum/pnp/capbio` (198 rows, 3 codes) and `petroleum/pnp/feedbiofuel` (873 rows across 22 of 26 requested codes — 4 report a literal null for every period, confirmed live, and are absent from the lake by design, not a bug) both live-verified 2026-09-09; the 22 real feedstock series share one unit (`MMLB`), so they plot on one axis unconverted. **Item 6 (weekly ethanol)**: `petroleum/pnp/wprode`, 3,588 rows across national + all five PADDs, live-verified 2026-09-09 — **PADD5 (West Coast) confirmed present**, the specific under-ingestion risk plan 31A's Task 0 flagged for this item. Page sections for items 4-6 are deliberately not built here — `apps/dashboard/**` belongs to a concurrent restyle migration; the section designs are handed off in `pipelines/coal/NOTES.md` and `pipelines/eia/NOTES.md` for whoever owns that surface once it lands. Full suite after plan 31C: 773 passed, 1 failed, 16 deselected — the one failure is a known, already-being-addressed, out-of-scope GIE seasonal-median bug (`02_gas_storage.py`, unrelated to this spec, tracked separately); ruff and mypy both clean, mypy covering `pipelines/coal/` for the first time. | **yes — new `pipelines/coal/`; the rest are new routes on the existing EIA client** | 01, 02, 30 |

Six independent items, each buildable or droppable on its own — the reason they were split out
of Spec 30 rather than bundled into it. The Grid Monitor item is not a duplicate of
`pipelines/gridstatus_iso/`: that library reaches CAISO and NYISO only, because ERCOT is blocked
by bot protection (confirmed live 403) and PJM needs a Data Miner 2 key. Those are the two
markets where gas-fired generation most moves the gas book.

## Spec 32 — Serving layer (Supabase Postgres)

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 32 | Serving layer: a read-optimised `serving.*` Postgres schema on Supabase, published from the existing pipelines at the end of each run — the lake stays the system of record | **Sessions 1–2 done, live-verified 2026-09-09.** Project `kardamow-serving` (`uckqjixhqqlqyxzbpaso`, eu-central-1, free tier): 10 tables + 6 views + PostGIS, RLS anon-read-only on every table (security advisor clean), `serving` exposed on the Data API. `core/publish.py` (pandas, psycopg3, chunked COPY→staging + `ON CONFLICT DO UPDATE`, `publish_log` row per publish) wired into `pull_wpsr.py`. First real publish: **47,461 rows** in `serving.series_long`, 27 series, 1982–2026; **idempotency confirmed** (second run held the table flat at 47,461 while `publish_log` went 1→2); anon REST reads work and anon writes are refused (401). **Session 3 done, live-verified 2026-09-09**: GIE (416,357 rows + 51,830 seasonal bands), curve (`curve_settles` 89, `spreads` 132,546), `wpsr_lines` (15 at-a-glance lines), `flows` (122,386 rows, 81 corridors), and yfinance front-month closes. **Every serving table that can be populated now is.** GRP publishing skipped — Spec 28 has no implementation in this repo; AIS (`vessel_latest`) blocked on Spec 11. The spec's GitHub Actions workflows were replaced by local `run_scheduled` wiring (lake-on-laptop), and the revalidate hook waits on a Vercel deployment. Four schema/spec corrections applied from real data: a redundant 38 MB index dropped, `serving.flows`' primary key gained `mode` (~15% of rows were being silently discarded), `period` corrected to hourly/daily/monthly, and views set `security_invoker` | no — publishing layer only | 00, every pipeline spec |

Adds `core/publish.py`, `supabase/migrations/`. The DuckDB/Parquet lake is unaffected;
this is a serving copy for Spec 33's web UI. See `specs/32_serving-layer-supabase.md`.

## Spec 33 — Front-end (Next.js on Vercel)

| Spec | Title | Status | New source? | Depends on |
|---|---|---|---|---|
| 33 | Desk-grade web UI at `data.kardamow.com` (Next.js/Vercel/Supabase), matching the Streamlit app's masthead+top-nav chrome; public read-only now, paid desk tier later | not started | no | 32, 28 |

New top-level `web/` directory, coexists with `apps/dashboard/` (Streamlit is not being
replaced). See `specs/33_frontend-nextjs.md`. 33.01 (Hormuz) and 33.02 (Balances) are the
first two screens; 33.03 (Gas) and 33.04 (Curves) are stubbed for later.
