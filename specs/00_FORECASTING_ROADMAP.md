# Forecasting Roadmap — Specs 34–41

**Owner:** Riko | **Drafted:** Thu 22 Oct 2026 | **Horizon:** Nov 2026 – Dec 2027

The lake is built. Specs 01–33 ingest crude, gas, power, weather, curves, positioning and news,
and serve them through Supabase. This roadmap adds the next two layers on top of it, in order:

1. **Forecasts** derived from the fundamentals already in the lake, each logged before the
   release and scored after it.
2. **Market expressions** of those forecasts (prediction markets, options), built only once
   the forecast underneath has a scored record.

Nothing in Layer 3 starts until the Layer 2 forecast it depends on has at least 8 scored weeks.

---

## 1. Assumptions

**Hours.** 12.5 hours a week, cut to 7 hours a week in the two MSc terms (assumed Jan–Mar and
Jul–Sep 2027, three Aberdeen modules each). Christmas (21 Dec – 3 Jan) is planned at zero.
Every phase carries a 20% buffer. If a term turns out heavier, the buffer goes first, then the
phase slips. Scope does not get squeezed in.

| Period | Weeks | Hours/week | Hours |
|---|---|---|---|
| 26 Oct – 20 Dec 2026 | 8 | 12.5 | 100 |
| 21 Dec – 3 Jan | 2 | 0 | 0 |
| 4 Jan – 28 Mar 2027 (MSc term) | 12 | 7 | 84 |
| 29 Mar – 27 Jun 2027 | 13 | 12.5 | 162 |
| 28 Jun – 26 Sep 2027 (MSc term) | 13 | 7 | 91 |
| 27 Sep – 19 Dec 2027 | 12 | 12.5 | 150 |
| **Total** | | | **587** |

**Running cost of live forecasts.** Each forecast that goes live costs about 0.5–1 hour a week
to watch, fix and publish, even fully scheduled. Five live forecasts is roughly 3–4 hours a
week, which is half the MSc-term budget. The plan accounts for this from Phase 2 onwards.

**Starting state, checked in the repo on 22 Oct 2026:**

- EIA weekly gas storage (L48 plus regions, Bcf) is pulled weekly
  (`pipelines/eia/pull_gas_storage.py`).
- Weather covers only **5 US cities**, population-weighted, with history from 2018
  (`pipelines/weather/cities.csv`). That is too thin for a gas-demand model and is the first
  real gap.
- EIA Grid Monitor gas-fired generation covers 8 balancing authorities, but only a 90-day
  trailing window. A power-burn model needs years of history.
- AIS (Spec 11) is unbuilt, so crude import and export tracking is not available.
- The IB Gateway is not connected (Spec 18), so there are no live TTF, JKM or options data.
- Scheduling is Windows Task Scheduler (`infra/register_tasks.ps1`) with the lake on the
  laptop. Moving to the Mac mini is real work, not a copy-paste.
- One known failing test: the GIE seasonal median on page 02.
- The last commit was 10 Oct 2026.

---

## 2. Calendar

| Phase | Dates | Hours | Work | Exit criterion |
|---|---|---|---|---|
| 0 | 26 Oct – 8 Nov | 25 | Mac mini migration and health check | All cadences run unattended for 3 consecutive days; full suite green |
| 1 | 9 Nov – 20 Dec | 75 | **Spec 34**: EIA gas storage predictor | Walk-forward backtest beats the best naive baseline; live ledger logging |
| — | 21 Dec – 3 Jan | 0 | Break; ledger keeps running | — |
| 2 | 4 Jan – 28 Mar | 84 | Spec 34 shadow scoring, then public; **Spec 35**: crude and product stocks nowcast | 8 scored storage weeks; Spec 35 backtest and model card |
| 3 | 29 Mar – 27 Jun | 162 | **Spec 36** EU storage fan chart; **Spec 37** hurricane shut-ins (live by 1 Jun); **Spec 38** prediction-market pipelines; **Spec 39** Kalshi temperature pricer | Hurricane estimator live before the season opens |
| 4 | 28 Jun – 26 Sep | 91 | Operations through hurricane season; IB Gateway on the Mac mini; **Spec 26 Session A** LNG netbacks | Gateway delivering TTF, JKM and NG curves daily |
| 5 | 27 Sep – 19 Dec | 150 | **Spec 40** options vs prediction-market scanner; **Spec 41** agent layer begins; 12-month review | One full year of scored gas storage forecasts (Nov 2027) |

Milestones worth naming publicly:

- **First scored forecast in the ledger:** Thu 17 Dec 2026, logged privately.
- **First public weekly storage call:** mid-Feb 2027, after 8 scored weeks.
- **Hurricane estimator live:** 1 Jun 2027.
- **One-year gas storage track record:** Nov 2027.

---

## 3. Phase 0 — Mac mini migration and health check (25 hours)

| Task | Hours |
|---|---|
| Copy the lake (`data/`), `uv sync`, `.env` on the Mac mini; confirm `core.settings` loads | 3 |
| Run every cadence in `infra/run_scheduled.py` by hand; record and fix breakages | 8 |
| Replace Task Scheduler with `launchd` plists, keeping cadences and release-time offsets; `/security-review` (touches `infra/`) | 6 |
| Backups: re-check `infra/DISASTER_RECOVERY.md` against the new machine, and test one restore | 3 |
| CI green; fix or quarantine the GIE seasonal-median failure | 3 |
| Commit, update CHANGELOG | 2 |

**Exit:** three consecutive days of unattended daily and weekly runs on the Mac mini,
`ruff`, `mypy` and `pytest` all clean.

---

## 4. Layer 2 — Forecast specs

Every forecast spec shares three rules.

- **Ledger first.** A forecast is written to the ledger before the release time, with its
  inputs' `revision_date`s. It is never edited afterwards. The actual is scored against it
  when it lands.
- **Baselines always shown.** Every forecast is scored beside naive baselines: the 5-year
  average change for the week (ex-2020, via `core.seasonal`), the same week last year, and,
  where relevant, last week's change. A model that does not beat the best baseline is shown
  as a miss on its model card, as `00_TRADING_CONVENTIONS.md` requires.
- **No consensus feed.** There is no free analyst-consensus source. Consensus is either keyed
  in by hand each week from a news report (`data/manual/consensus/*.csv`, `source="manual"`)
  or left out. Decide in Spec 34 Session D; do not scrape it.

### Spec 34 — EIA weekly gas storage predictor (Phase 1, 75 hours including buffer)

**Why first:** it is the cleanest weekly test in the lake. Weather drives most of the winter
change, the report week has fully passed before release, and the season starts now.

| Session | Hours | Work |
|---|---|---|
| A | 14 | Weather expansion: about 20 US cities weighted by residential plus commercial gas consumption by state. Spec 31's consumption pull is national only (state-level was deferred), so add the state route to `pull_gas_consumption.py` first, then a hand-maintained weights CSV like `cities.csv`. Backfill history to 2010 with the existing 65-second group pacing. Build degree days aggregated to the EIA storage week (Friday to Thursday). |
| B | 8 | Power burn history: backfill EIA Grid Monitor gas-fired generation for the 8 balancing authorities from Jul 2018 (the route supports it; the current pull keeps only 90 days), aggregated to the storage week. |
| C | 15 | `core/gas_storage_model.py`: baselines plus a regression of the weekly change on degree days, power burn, season and lagged storage. Walk-forward backtest 2019–2026 with publication lag respected (`core/calendars.py`). Model card. |
| D | 10 | `core/forecast_ledger.py`, reusable by Specs 35, 36, 37 and 39: write forecast, score actual, rolling MAE and bias against each baseline. Stored in `ts_long` as `derived.forecast.*` and `derived.forecast_actual.*`, so no schema change. Scheduled run Wednesday 22:00 Dublin. |
| E | 10 | Page section (forecast vs actual vs baselines, error history), Supabase publish, and a Substack Note template that fills from the ledger. |
| Buffer | 18 | |

**DoD:** walk-forward mean absolute error at least 15% below the best naive baseline over
2023–2026 winters; ledger logging unattended; model card on the page.

**Kill criterion:** if the model cannot beat the best baseline after Session C, ship the model
card with the miss, keep the ledger running for regional forecasts only, and do not publish
weekly calls.

**Known limits:** dry gas production and LNG feedgas are not available weekly from free
sources. The model carries them as slow-moving trend terms. Say so on the model card.

### Spec 35 — EIA crude and product stocks nowcast (Phase 2, about 50 hours)

| Session | Hours | Work |
|---|---|---|
| A | 15 | Components from WPSR history: refinery runs (persistence plus seasonality), product supplied by product, yields. |
| B | 15 | Gasoline and distillate stock change from runs × yield − implied demand − exports (4-week averages). |
| C | 10 | Crude stock change: production + imports − exports − runs, with import and export terms as 4-week averages (no AIS). |
| D | 10 | Ledger wiring (reuses Spec 34), model card, page section. |

**Expectation, written down in advance:** product stocks should beat baselines; crude probably
will not without AIS, because weekly imports and exports swing by more than the whole signal.
**Kill criterion:** if crude fails, publish products only and log crude as a known miss. AIS
(Spec 11) becomes a separate decision afterwards, not part of this spec.

### Spec 36 — EU gas storage fan chart (Phase 3, about 25 hours)

Analogue scenarios, not a new weather feed: replay each past winter's and summer's degree-day
path (2010 onwards, ex-2020) against today's GIE fill and LNG send-out run rate. Output P10,
P50 and P90 paths to the 1 Nov fill target and the 1 Feb and 1 Apr troughs. GIE and ENTSOG are
already in the lake, so there is no new source. Ledger scores the P50 monthly.

### Spec 37 — Gulf of Mexico hurricane shut-in estimator (Phase 3, about 35 hours, live by 1 Jun 2027)

| Session | Hours | Work |
|---|---|---|
| A | 10 | NHC forecast tracks and cones. Proposed dependency: `tropycal` (needs approval under golden rule 7). |
| B | 8 | Offshore platform locations and production from BOEM as a manual CSV drop; refinery locations from EIA. |
| C | 10 | Estimator: probability of wind thresholds over each platform, multiplied by production, giving expected barrels per day and Bcf per day shut in. |
| D | 7 | Validation against BSEE shut-in statistics for 2020–2024 storms; page section. |

### Spec 38 — Prediction-market pipelines (Phase 3, about 20 hours)

Kalshi as a new read-only pipeline (public market data, no trading keys). Extend the existing
Polymarket pull in `pipelines/social/` from tag-level attention to specific energy and weather
markets. Prices go into `ts_long`, market metadata into `events`. Confirm that Kalshi and
Polymarket will onboard an Irish resident before anything beyond reading data.

### Spec 39 — Kalshi temperature pricer (Phase 3, about 35 hours, shadow only)

Open-Meteo's ensemble endpoint (same client, new route) gives a probability for each
temperature band in the cities Kalshi lists. Settlement ground truth comes from the NWS Daily
Climate Report (a new source, with a cassette test). Ledger compares model probability, market
price and outcome daily. Shadow-scored through Phase 4; any real-money decision waits for the
12-month review.

---

## 5. Layer 3 — Market expressions (Phases 4–5)

| Item | Hours | Blocked by |
|---|---|---|
| IB Gateway on the Mac mini plus CME and ICE market-data subscriptions | 10 | Phase 0 |
| Spec 26 Session A: LNG netbacks and arbitrage signal (spec already written) | 20 | Gateway: TTF, JKM, NG curves |
| Spec 40: options-implied probabilities vs prediction-market odds for oil and gas | 40 | Gateway plus options data; Specs 34, 35 and 38 scored |
| Spec 41: agent layer (`TradingAgents` fork; "master Kardamow" narrates ledger output) | open-ended | everything above |

---

## 6. Driving Claude Code

Each new spec follows the existing house format (`specs/26_gas-analytics.md` is the template):
Purpose, Data, Sessions with function signatures and tests, Definition of Done, and a
**Session opener** prompt. One spec session is one Claude Code session, sized to fit one
evening or weekend block, and always ends green (golden rule 8).

Session opener pattern:

> Read `NOTES.md`, `specs/00_TRADING_CONVENTIONS.md`, `specs/00_FORECASTING_ROADMAP.md` and
> `specs/34_eia-gas-storage-predictor.md`. Execute Session A exactly as written. Plan first,
> then implement. Stop and ask before adding a dependency or changing a schema.

Write each spec just before its phase starts, not all at once: what Spec 34 teaches about the
ledger and the weather backfill will change Specs 35–39.

---

## 7. Risks and blockers

| Risk | Effect | Mitigation |
|---|---|---|
| MSc terms heavier than assumed | Phases 2 and 4 slip | Buffers absorb up to about 4 weeks; Spec 35 slides into Phase 3 before anything is cut |
| Open-Meteo hourly rate limit on the 2010 backfill | Session 34A takes several sittings | Run the backfill overnight in groups, as `climatology.py` already does |
| Running cost of live forecasts | Eats MSc-term hours | Cap live forecasts at 3 until Phase 5; everything else stays shadow-scored |
| No weekly production or LNG feedgas | Storage model error in shoulder seasons | Trend terms, stated on the model card |
| No consensus feed | Cannot claim "beat consensus" | Score against baselines; key consensus by hand only if it is worth 10 minutes a week |
| IB Gateway connection keeps failing | Phase 4–5 blocked | Barchart manual drops as a stopgap for Spec 26 netbacks |

---

## 8. Not in this plan

5-minute crypto contracts, perps analytics, liquidation alerts, builder-code front ends, Spec 28
(GRP), Spec 11 (AIS) and the Next.js front end (Spec 33). Each can come back after the
12-month review, if the forecasts underneath have earned it.
