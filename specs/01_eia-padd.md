# Spec 01 — US PADD Crude & Product Movements (EIA)

**Weeks 1–2 · Est. 10–12 h · Prereq: Spec 00.**

## Objective & alpha question
Track physical crude/product flows between PADDs, refinery utilisation by region, Cushing/US
stocks and WPSR weekly balances — to anticipate regional glut/tightness and crack-spread moves
before consensus. Ties directly to the refinery exhibits (dual-axis runs-vs-margins, utilisation
YoY, seasonal ranges, scatter-with-fit).

## Data source
EIA API v2, base `https://api.eia.gov/v2/`. Free key (`settings.eia_api_key`). Max 5,000 rows per
request (paginate with `offset`/`length`); no documented hourly cap. Discover exact series codes
via each route's `/facet/series` or the browser at eia.gov/opendata/browser/petroleum —
**verify terminal route names live before hard-coding** (EIA sometimes nests `/data` one level deeper).

Target routes/series:
- Weekly stocks `petroleum/stoc/wstk`: `WCESTUS1` (US crude ex-SPR), `W_EPC0_SAX_YCUOK_MBBL` (Cushing), `WCSSTUS1` (SPR), gasoline `WGTSTUS1`, distillate `WDISTUS1`.
- Refinery inputs & utilisation `petroleum/pnp/wiup`: `WPULEUS3` (US utilisation %), PADD utilisation `W_NA_YUP_R10_PER` … `R50_PER`, gross inputs by PADD.
- Product supplied (demand proxy) `petroleum/cons/wpsup`: total, gasoline, distillate, jet.
- Inter-PADD movements (monthly) `petroleum/move/ptb` (pipeline+tanker+barge+rail), plus `petroleum/move/pipe`, `petroleum/move/tb`, `petroleum/move/rail`; series pattern `PET_MOVE_PTB_DC_R{dest}0-R{orig}0_MBBL_M` for crude between PADDs.
- Imports/exports by PADD `petroleum/move/wkly` (weekly imports), `petroleum/move/exp`.

## Data model
- Scalars → `ts_long` (`series_id` = EIA series code, `geo` = US/PADD1..5, `freq` = W/M).
- Inter-PADD → `flows(source='eia', from_node='PADD3', to_node='PADD2', mode='pipeline'|'tanker_barge'|'rail', unit='Mbbl/m')`.

## Transformations (`core.seasonal` + new `pipelines/eia/transforms.py`)
- Seasonal median/range 2018–2025 **excluding 2020**; YoY deltas.
- Days-of-cover = stocks ÷ (4-week avg product supplied).
- Net inter-PADD balance per PADD per month; 12-month rolling share by mode.
- WPSR week: build a one-screen balance table (stocks Δ, runs, utilisation, product supplied, imports).

## Visualisation spec (page `01_us_padd.py`)
1. **Seasonal range charts** — Cushing, US crude, gasoline, distillate (grey band, orange median, navy current year, Latest/YoY/vs-median annotation).
2. **Dual-axis** — refinery gross inputs (navy, left) vs utilisation % (light blue, right), US + selectable PADD.
3. **PADD flow map** — Plotly `scattergeo` US map: PADD centroid nodes, directional arrows (annotations with `arrowhead`) sized by latest monthly flow, colour by mode; month slider.
4. **WPSR table** — latest week vs prior, vs 5-yr median, conditional red/green.

## Sessions

### Session A (weekend, 3 h) — stocks, utilisation, demand
> Read NOTES.md, specs/01_eia-padd.md. Extend `pipelines/eia/`:
> `pull_wpsr.py` pulling all weekly series listed in the spec (stocks, utilisation, product
> supplied, weekly imports) → `ts_long`. Add `transforms.py` with `days_of_cover()` and a
> `wpsr_summary()` returning the balance table. Cassette tests for one route of each shape.
> Page 01: seasonal charts for Cushing/US crude/gasoline/distillate + the dual-axis
> inputs-vs-utilisation chart with a PADD selector. Acceptance: page renders offline from the lake;
> pytest green.

### Session B (weekend, 3 h) — inter-PADD flows + map
> Pull monthly inter-PADD crude movements for all origin→destination pairs across
> ptb/pipe/tb/rail routes → `flows`. Build `apps/dashboard/components/padd_map.py` rendering the
> directional arrow map with month slider and mode filter. Add it to page 01 with the net-balance
> bar chart per PADD. Acceptance: arrows match a hand-checked PADD3→PADD2 value from the EIA
> browser; test validates flows schema.

### Session C (weekday, 1 h) — WPSR table + polish
> Add the WPSR one-screen table with conditional formatting and a "release countdown" using
> `core.calendars`. Tidy layout: charts in tabs (Stocks / Refining / Flows / WPSR).

### Session D (weekday, 1 h) — buffer
> Fix anything from A–C; record missing cassettes; update pipelines/eia/NOTES.md with every
> series code actually used and any route-name corrections discovered.

## Definition of Done
- Page 01 shows: 4 seasonal charts, dual-axis refining chart, PADD arrow map with slider, WPSR table.
- One hand-verified value against the EIA data browser for each of: a stock series, a utilisation series, an inter-PADD flow.
- All pulls idempotent (re-running does not duplicate rows). Tests + CI green.

## Stretch
- CFTC COT managed-money net length overlay on the crude stocks chart.
- WPSR surprise vs Bloomberg-consensus placeholder (manual input box) annotated on charts.
