# Spec 31 — EIA Coverage Extensions

**Est. 5–7 h across six independent items · Prereq: Spec 00, Spec 01, Spec 30 (built).
Extends `pipelines/eia/` and adds `pipelines/coal/`. No new schema. Sections on existing
pages; no new page.**

**Every item below is independent.** Each can be built, deferred or dropped on its own
without affecting the others, which is why these were split out of Spec 30 rather than
bundled into it. Spec 30 argued one claim — the lake held volumes and almost no prices.
This spec has no single claim; it is six separate wins.

## Objective

Close six specific coverage gaps, each of which either answers a question the lake cannot
answer today or removes a blind spot in data already ingested.

## The six items, in build order

Ranked by value against a crude/gas/power book, not by dataset size.

### 1. Natural gas storage capacity — `natural-gas/stor/cap`

The lake ingests weekly working gas in storage (Spec 02) but **not capacity**, so it can
report Bcf and cannot report **percent full**. Heading into winter the fullness ratio is
the number that matters; absolute Bcf without the denominator is far less informative.

State and region level, 1989–2026. Feeds a new panel on the existing gas storage page.

**Why first:** it makes data already in the lake more useful, which is the cheapest value
available here.

### 2. Grid Monitor — `electricity/rto/region-data`, `fuel-type-data`, `interchange-data`

**This is not a duplicate of `pipelines/gridstatus_iso/`, and the reason is specific.**
The `gridstatus` library reaches **CAISO and NYISO only** in this repo: **ERCOT is blocked
by Incapsula/Imperva bot protection (confirmed live 403)** and **PJM requires a Data Miner
2 key** the project does not hold. EIA's RTO routes cover all 65 Lower-48 balancing
authorities including both.

ERCOT and PJM are the two markets where gas-fired generation most moves the gas book, and
they are precisely the two the existing pipeline cannot see. `interchange-data` also maps
onto the `flows` schema and the `get_flows` corridor pattern `pipelines/eia/corridors.py`
already establishes.

**Scope discipline:** ingest demand, generation-by-fuel and interchange. **Do not** ingest
sub-regional demand for the 8 BAs that offer it — it is granular load research, not
gas-demand signal, and it multiplies row count for no gain here.

### 3. Natural gas consumption by sector — `natural-gas/cons/sum`

The gas pipeline carries supply (production, storage, exports) and **no demand**.
Residential, commercial, industrial and power-sector deliveries complete the balance.
State-level available; national is the minimum useful cut.

### 4. Coal, power sector only — `coal/consumption-and-quality`

**There is no `pipelines/coal/` today and no coal reference anywhere in `specs/00_INDEX.md`.**
This item creates the package.

Coal matters to this book through exactly one channel: **coal-to-gas switching in US power
generation**, which sets a floor and ceiling on gas demand. This route carries power-sector
coal receipts, consumption, stocks, **price ($/short ton) and heat content** together,
quarterly, national and state — everything a switching calculation needs, in one route.

**Deliberately excluded, with reasons that are findings in their own right:**

- **Coal Markets basin spot prices** (Powder River, Illinois, Appalachia) are **S&P Global
  proprietary**, per EIA's own notice. No bulk history exists anywhere; collection could
  only accumulate forward, so a chart built on it is empty for months.
- **API2 and API4** — the seaborne thermal benchmarks that actually matter for European gas
  substitution — **are never published by EIA at all.** That is a vendor gap; no amount of
  EIA work closes it. `coal/exports-imports-quantity-price` is the closest EIA-only proxy
  and is deferred to a later pass, not built here.
- **No weekly coal data exists on the API.** Weekly Coal Production would require scraping.
  Not worth it for a quarterly-cadence question.

### 5. Biofuels capacity and feedstocks — `petroleum/pnp/capbio`, `petroleum/pnp/feedbiofuel`

`capbio` is monthly national capacity for ethanol, biodiesel, and renewable diesel and
other biofuels — the signal for **renewable diesel capacity displacing petroleum diesel
demand**. `feedbiofuel` carries 26 monthly feedstock series (soybean oil, corn oil, used
cooking oil, tallow, canola), which is what quantifies **feedstock competition** rather
than merely asserting it.

### 6. Weekly ethanol production — `petroleum/pnp/wprode`

National and PADD1–4, **weekly — the same cadence as the WPSR series already in the lake**,
so it slots into an existing pull rhythm. The best trading-frequency proxy for ethanol
blending economics. Found while walking the route family during Spec 30's analysis; it was
not on the original source list.

## What Spec 30 learned that binds this spec

These are not general good practice. Each one cost real time or nearly shipped a defect.

- **Never guess a series code.** Discover every one via `EIAClient.list_series(route)`
  (`facet/series`). Spec 30's discovery task found the gravity-band route its own plan had
  written off, and Spec 17 shipped a wrong ticker that only a live lookup caught.
- **Some routes have no `series` facet at all.** `electricity/electric-power-operational-data`
  returns 400 on `facet/series` and is queried by `fueltypeid`/`sectorid`/`location`/`data`
  instead. `EIAClient.get_operational_series` exists for that shape. **Verify which shape
  each `electricity/rto/*` route uses before writing pull code** — do not assume either.
- **A wrong `frequency` returns empty, not an error** on some routes. Confirm the accepted
  values live.
- **EIA publishes real `value: null` rows.** `get_series`, `get_operational_series` and
  `get_flows` now skip them and report the dropped count. Do not re-introduce an
  unconditional `float()`.
- **Units are stored exactly as published and never converted at ingest** — `Bcf`,
  `$/short ton`, `MMBtu`, `thousand gallons`. Conversion belongs in `core/`.
- **Series IDs stay in EIA's native form**, matching `pipelines/eia/`. Where a route
  supplies none, mint them deterministically and document the scheme — see
  `generator_fuel_series_id` in `pipelines/eia/pull_prices.py` for the precedent.
- **Never select a series by list index.** Spec 30 shipped `GENERATOR_FUEL[0]`, where
  reordering a constant would have plotted thousand Mcf on a `$/MMBtu` axis, raising
  nothing. Use named constants.
- **Never read the lake unbounded.** `read_ts_long` now takes `source` and `series_prefix`;
  `source` narrows the parquet glob itself. An unbounded read grew until it failed as a
  `pickle.dumps` error inside `st.cache_data`, pointing nowhere near the read.
- **Cycle a palette by index, never `zip(..., strict=False)`** against a fixed tuple — it
  silently drops series past the tuple's length.

## Data model — no new schema

`ts_long` for every scalar series. `flows` for Grid Monitor interchange, using the
`get_flows` corridor pattern. `core/schemas.py` is not touched.

`source="eia"` for items 1, 2, 3, 5, 6. **Item 4 uses `source="coal"`** — it is the first
member of a new `pipelines/coal/` package, and giving it its own source keeps
`read_ts_long(source="coal")` meaningful.

## Sessions

Each item is independently shippable. Suggested grouping, three sessions:

**Session A — gas completeness (items 1 and 3, ~2 h).** Both are `natural-gas/*` routes on
the existing client. Panel additions to the gas storage and US gas pages: storage as
percent of capacity, and a supply-versus-demand balance.

**Session B — Grid Monitor (item 2, ~2–3 h).** The largest item. Verify the query shape
first. Register at the cadence the data actually supports. Interchange goes to `flows`,
not `ts_long`.

**Session C — coal and biofuels (items 4, 5, 6, ~2 h).** Creates `pipelines/coal/` with its
own `NOTES.md`. Biofuels extend `pipelines/eia/`.

## Acceptance criteria

- Live route verification before any pull code; real outcomes, **including routes that
  return nothing**, recorded in the owning package's `NOTES.md`.
- Cassette tests for every route; a resilience test proving one route's failure does not
  abort the others.
- No series code guessed from a `dnav` URL.
- Units stored exactly as published, unconverted.
- Every new page read narrowed by `source` or `series_prefix`.
- `core/schemas.py` unchanged.
- Session ends green: `pytest`, `ruff check .`, `mypy core pipelines infra`.

## Out of scope, deliberately

Coal Markets spot prices (proprietary, no history). API2/API4 (not published by EIA;
a vendor decision). Weekly Coal Production (no API route; scraping). Coal reserves,
transportation rates and distribution (describe the coal industry rather than informing gas
demand). Monthly Energy Review (restates the fuel-specific reports; only its Section 11 CO2
tables are net-new, and those are one lightweight pull if ever wanted). Densified biomass
(peripheral to a crude/gas book). Plant-level annual capacity XLSX surveys (no API, low
value against parsing cost). Grid Monitor sub-regional demand (granular load research, not
gas-demand signal). EPA State Fuels — **not a pipeline at all**: it is regulatory reference
data (RVP limits, reformulated-gasoline zones, boutique-fuel states and seasonal transition
dates) and belongs as a static annotation lookup explaining PADD crack dislocations, not as
ingested rows.

Any trading signal derived from these series. The honesty rule of Specs 17, 29 and 30
carries over: these are observations, not recommendations.
