# Spec 30 — EIA Price Coverage

**Est. 4–5 h (three sessions) · Prereq: Spec 00, Spec 01 (built). Independent — extends
`pipelines/eia/` with four new API routes, adds no new schema, no new pipeline package.
Adds a price section to page `20_cracks.py` and a delivered-cost panel to `05_us_gas_power.py`.**

## Objective & alpha question

The lake measures the energy complex in **volumes** and almost never in **prices**. This spec
closes that gap for the four price families the existing analytics already assume.

Question: *when a crack spread moves, was it the barrel or the product — and which grade of
barrel, delivered where?* Today the dashboard cannot answer that, because it holds product
volumes, refinery runs and crude movements, but not the prices those volumes cleared at.

## Why this exists — one claim, checked

Verified against the lake on 2026-09-06, not assumed:

- **Crude prices:** only FRED spot legs — `fred.dcoilwtico`, `fred.dcoilbrenteu`, plus three
  product legs added by Spec 20 (`dgasnyh`, `dgasusgulf`, `dhoilnyh`). No refiner acquisition
  cost, no first-purchase price, no landed cost by origin, nothing by grade.
- **Gas prices:** exactly one series — `fred.dhhngsp`, Henry Hub spot, 7,731 rows from 1997.
  No citygate, no wellhead, no state or sectoral delivered price. One national benchmark and
  nothing to locate it against, so basis is uncomputable.
- **Retail prices:** none at all. Zero pump-price series, despite Spec 20's crack analytics
  being built on the wholesale side of exactly that market.
- **Generator fuel cost:** none. The gas book and the power page share no price linkage.

Meanwhile Spec 19 does quality-mismatch work and Spec 20 runs a crack VECM — both reason about
crude *grades* while the lake holds no grade-differentiated price at all.

**This is not a coverage-breadth spec.** It adds no new commodity, no new region and no new
cadence. It supplies the missing denominator to analytics that already exist.

## What is confirmed, and what the first session must verify

**Confirmed** (live route walks, 2026-09-06):

| Family | Route | Notes |
|---|---|---|
| Refiner acquisition cost | `petroleum/pri/rac2` | `dnav` prefix `pet_pri_rac2`. By PADD, by crude stream, by API gravity. |
| Retail gasoline & diesel | `petroleum/pri/gnd` | Weekly. National, PADD, state, 9 selected cities. |
| Gas prices | `natural-gas/pri/sum`, `pri/rescom`, `pri/fut` | Citygate by state; residential/commercial/industrial delivered. |
| Generator fuel cost | `electricity/electric-power-operational-data` | EPM Tables 4.13 (avg cost of gas delivered to generators, $/MMBtu) and 2.4 (gas burn). **State-level**, not census division. |

**Not confirmed, and the mandatory first step of Session A** — the same discipline Spec 17
applied to its 57 tickers, which caught a real wrong ticker:

- The exact **series IDs** in each route. Discover them live via
  `GET /v2/{route}/facet/series`, per this repo's existing convention. **Do not guess a series
  ID from a `dnav` page URL.**
- Which `petroleum/pri/*` sub-route actually carries **domestic first-purchase price** and
  **imported landed cost by country** — the analysis identified the family but not the leaf.
- Whether `natural-gas/pri/fut` is genuinely useful here or duplicates futures data Spec 18
  already ingests. **If it duplicates, drop it and record that** rather than ingesting twice.

Record every real outcome — including routes that return nothing — in `pipelines/eia/CLAUDE.md`.

## Data model — no new schema

Everything is a scalar time series and fits `ts_long`. `core/schemas.py` is not touched.

**Series ID decision, stated explicitly because the repo is inconsistent here.** The existing
`pipelines/eia/` pulls store **EIA's own native series IDs** (`N9070US2`,
`NW2_EPG0_SNO_R33_BCF`), while Specs 17–29 use the lowercase dotted style
(`adanos.reddit.xom.buzz_score`). Root `CLAUDE.md`'s dotted-style rule is scoped to the trading
analytics layer, Specs 18–27.

**This spec follows the `pipelines/eia/` precedent and keeps EIA's native series IDs.** Reason:
all EIA data in the lake then answers to one convention, and a single `WHERE source='eia'` query
behaves predictably. Introducing dotted IDs for four new routes while eleven existing routes use
native IDs would make EIA the one source needing two lookup styles.

Consequence, accepted: these series will not read like `social.*` or `adanos.*`. That is the
lesser inconsistency.

`source="eia"` throughout. `unit` as published — `$/bbl`, `$/gal`, `$/Mcf`, `$/MMBtu` — and
**never converted at ingest**; unit conversion belongs in `core/`, not the pipeline.
`geo` carries the PADD, state or city code. `freq` as published (`W`, `M`).

## Revision behaviour — load-bearing

PMM and EPM both **revise prior months**, and EPM's early months are routinely restated. The
lake's `revision_date` column exists for this. Each pull writes `revision_date = ingested_at`,
and `write_ts_long`'s dedup on `(series_id, ts)` sorted by `revision_date` keeps the latest.

**Do not treat a changed historical value as a bug.** Record in `pipelines/eia/CLAUDE.md` what
was actually observed about revision depth for each product, once real pulls have run twice.

## Sessions

### Session A — verify and build the petroleum price pulls (~2 h)

> Read `CLAUDE.md`, `specs/30_eia-price-coverage.md`, `pipelines/eia/CLAUDE.md`. Walk
> `petroleum/pri/rac2` and `petroleum/pri/gnd` live via `facet/series`; record the real series
> IDs and any route that returns nothing. Identify the leaf routes for domestic first-purchase
> price and imported landed cost by country. Build `pipelines/eia/pull_prices.py` reusing the
> existing `EIAClient` — no new client. Per-route `requests.exceptions.RequestException`
> resilience via `core.failures`, matching `pull_wpsr.py`. Cassette tests for each route.

### Session B — gas and generator-fuel prices (~1.5 h)

> Walk `natural-gas/pri/sum`, `pri/rescom`, and `electricity/electric-power-operational-data`
> live. **Decide and record whether `natural-gas/pri/fut` duplicates Spec 18's futures data**;
> if it does, do not ingest it. Extend `pull_prices.py`. Add EPM Table 4.13 (state $/MMBtu
> delivered to generators) and Table 2.4 (gas burn). Cassette tests. Register in
> `infra/run_scheduled.py` — monthly cadence for PMM/EPM, weekly for `gnd`.

### Session C — visualisation (~1.5 h)

Three additions, all `card(...)`-wrapped, `core.theme` colours, British English.

**On `20_cracks.py`** — a "Crude acquisition cost" subheader:
1. **Refiner acquisition cost by PADD**, composite vs imported vs domestic, against the WTI and
   Brent legs already in the lake. The first chart in this repo able to show what refiners
   *actually paid* rather than what the benchmark printed.
2. **Landed cost by API gravity band** — light versus heavy, as a sourcing-mix indicator. This
   is the series Spec 19's quality-mismatch work has been reasoning about without.

**On `05_us_gas_power.py`** — a "Delivered fuel cost" subheader:
3. **State delivered gas cost to generators vs Henry Hub** (`fred.dhhngsp`), with the spread
   annotated. The gas↔power bridge: it shows what generators pay above the benchmark, which is
   where switching economics actually bite.

Retail pump prices go on `20_cracks.py` as a secondary line beneath the wholesale crack, not
their own page — the point is the retail-to-wholesale margin, not the pump price alone.

## Acceptance criteria

- Live route verification done **before** any pull code; real outcomes, including empty routes,
  recorded in `pipelines/eia/CLAUDE.md`.
- Cassette tests for every route; a resilience test proving one route's `RequestException` does
  not abort the others.
- No series ID guessed from a `dnav` URL — every one discovered via `facet/series`.
- Units stored exactly as published, unconverted.
- A test proving a revised historical value replaces its predecessor rather than duplicating it.
- `core/schemas.py` unchanged; no new pipeline package created.
- Session ends green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

## Out of scope, deliberately

Heating Oil & Propane (`petroleum/pri/wfr`) — seasonal, PADD1-centric, low priority until
propane basis becomes a focus. Spot prices (`petroleum/pri/spt`) — a useful cross-check but
duplicative of the FRED legs already held. Everything in Spec 31 (storage capacity, Grid
Monitor, gas consumption, coal, biofuels). Any trading signal derived from these prices: this
spec supplies inputs, and the honesty rule of Specs 17 and 29 carries over — these are
observations, not recommendations.
