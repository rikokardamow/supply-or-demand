# Mapping — `oil_demand.xlsx` onto this repo's connectors

**Date:** 2026-10-10
**Status:** analysis complete; routes confirmed live 2026-10-10 (see that section); plan in `docs/superpowers/plans/2026-10-10-oil-demand-elasticity.md`
**Source workbook:** `data/manual/bloomberg/oil_demand.xlsx` (was `~/Desktop/skill-pdfs/`) (Bloomberg Intelligence, 12 sheets)
**Related:** `specs/06_opec-supply.md`, `specs/33_frontend-nextjs.md` (33.01 is the Hormuz screen)

Read-only analysis. The workbook was not modified and must never be committed: it is
licensed BI content, and `data/manual/**` is git-ignored for that reason.

## What the model is, in its own words

From the workbook's `Methodology` sheet: a **top-down global oil balance on quarterly
observed data from the EIA, OPEC and IEA**, adjusted by analyst overlays on the supply side
(OPEC policy and capacity, US shale, Brazil, Guyana). On the demand side it adds *"a basic
OLS regression of changes in oil demand against changes in GDP for each major region … using
Bloomberg Economics GDP data"*, giving a region-specific GDP elasticity that translates BE's
GDP forecasts into demand projections. A **Hormuz overlay** applies reopening percentages by
quarter and country-specific recovery factors across Gulf producers.

So it is three things stacked: an observed balance, an elasticity, and a scenario overlay.
They have very different refreshability, and conflating them is the main risk in porting it.

## The regressions, as actually fitted

The fitted coefficients, R² values and p-values are BI's analytical output and are not
reproduced here. Open the workbook's four `OLS.*` sheets to read them. What follows is the
structural analysis, which is ours.

Four observations that matter before any of this is reproduced:

1. **The USA block is not in the same units as the other three.** Its slope coefficient is
   three orders of magnitude smaller, and the panel confirms why: `For_OLS` column E carries
   a GDP *level* change in US$bn while the other three carry a *percentage* change. Those are
   different quantities and must never be tabled side by side as if they were comparable
   elasticities.
2. **Three of the four blocks lost their regressor label** — cell A18 holds a number rather
   than a name, which is what Excel's regression tool produces when the "labels in first row"
   box is left unticked. The specification therefore has to be inferred from the panel rather
   than read off the output.
3. **China's fit is far weaker than the other three** — well under half their R². That
   single relationship is what converts a GDP forecast into a Chinese demand projection, and
   it explains only a minority of the variance. It is the weakest link in the model and
   belongs on the model card, not in a footnote.
4. **The panel spans 1Q 2013 onward, so it contains 2020.** Oil demand and GDP collapsed
   together that year, and a single extreme observation pair can carry most of an R² in a
   changes-on-changes regression. The repo already excludes 2020 from every seasonal
   construct for a related reason. Refitting with and without 2020 is one line and will show
   whether these elasticities are real or a COVID artefact.

These are pasted ToolPak outputs, not live formulas. Nothing recalculates.

## The workbook is already dead on this machine

The `Demand` sheet reads `#NAME?` in every data cell — Excel's error for an unresolvable
function. The Bloomberg add-in is not installed, so every `BDH`/`BDP` call fails. The
regressions still display numbers only because `For_OLS` holds pasted values.

This is not a problem to fix. It is the reason to port the model.

## Input map

Only **one** input is a price. yfinance and IBKR cannot supply the rest — they quote markets,
and this model runs on consumption volumes and macro aggregates.

| Workbook input | Was | Our replacement | State |
|---|---|---|---|
| `CO1 Comdty` (Brent front) | Bloomberg | yfinance `fut.lco.f01.close`; IBKR curve via the 2026-10-10 plan | **in the lake** |
| US oil consumption | Bloomberg | EIA `WRPUPUS2` (US total product supplied) | **in the lake**, 1,868 rows, 1990-11 → 2026-08, MBBL/D — weekly, needs quarterly aggregation |
| US GDP | Bloomberg / BE | FRED `fred.gdpc1` | **in the lake**, 318 rows, 1947 → 2026-04, chained 2017 $bn |
| Supply by producer, quarterly from 2013 | Bloomberg + analyst overlay | OPEC MOMR + EIA | **partial** — see below |
| Global / China / EU / RofW oil consumption, quarterly from 2013 | Bloomberg | — | **gap, and the real blocker** |
| China / EU / RofW GDP | Bloomberg Economics | OECD Quarterly National Accounts — **confirmed live**, see below. Not FRED: it carries no quarterly real China GDP at all | new keyless pipeline |
| GDP **forecasts** | Bloomberg Economics | — | **not a price; no connector supplies it** |
| IEA projection columns | IEA | — | paywalled; drop and label as absent |
| Hormuz % of normal flows, recovery factors | user assumption | user assumption | **no data needed** |

## The blocker, stated precisely

The regressions need roughly 48 quarters of regional oil consumption back to 2013. What the
lake holds for that today:

- `momr.demand_balance.world_demand.{china,europe,americas,asia_pacific,africa,…}` —
  real series, correct concept, but **12 quarterly rows (2025-01 → 2027-10)** and 6 annual
  rows. The MOMR appendix is a snapshot table, not deep history, and the lake holds only two
  vintages (July and August 2026). It cannot supply a 2013-onward panel.
- `jodi.crude_production.cn`, `jodi.refinery_intake.cn` — 18 rows each, 2025-01 → 2026-06.

Two routes out, both free and neither Bloomberg:

1. **JODI secondary table.** `pipelines/jodi/NOTES.md` records that the secondary table
   covers *refined products* with its own flow vocabulary including `TOTDEMO` (total demand),
   and that it was deliberately scoped out because the spec wanted crude. That is exactly the
   country-level consumption history this model needs, published back to 2002, no key.
   Separately, `CURRENT_YEAR_HISTORY_DEPTH = 2` caps even the primary pull at two years — a
   constant, raised deliberately.
2. **EIA international energy statistics**, country-level consumption, on the API client the
   repo already has.

Route 1 is now confirmed live — see "Routes confirmed live, 2026-10-10" below. Route 2 was not
needed and was not probed. Per this project's own standing rule, confirm the route
and the real series before planning against it — `pipelines/macro/NOTES.md` records two
plausible-looking FRED IDs that turned out to be a zinc index and a stale series.

## Routes confirmed live, 2026-10-10

Both halves of every regression — demand and GDP — now have a real, free, keyless route with
history covering the 1Q 2013 panel. Every figure below was read from a live response on this
date, not inferred.

### GDP — OECD Quarterly National Accounts, keyless SDMX

`https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/{key}?format=csvfile`
No key, CSV out (`application/vnd.sdmx.data+csv`). The key that returns seasonally adjusted
real GDP growth on a year earlier, quarterly, is:

`Q.Y.{REF_AREA}...B1GQ.....L.GY.`

`FREQ=Q`, `ADJUSTMENT=Y`, `TRANSACTION=B1GQ` (GDP), `PRICE_BASE=L` (chain-linked volume, so
**real**), `TRANSFORMATION=GY` (growth on the same quarter a year earlier), unit `PC`
(percent). Join several areas with `+`. Columns used: `REF_AREA`, `TIME_PERIOD` (`yyyy-Qn`),
`OBS_VALUE`, `OBS_STATUS`.

| `REF_AREA` | Range | Obs from 2013-Q1 | Gaps | Independent check |
|---|---|---|---|---|
| `CHN` | 1993-Q1 → 2026-Q2 | 54 | 0 | Equals China NBS's own index (preceding year = 100) for all six quarters DBnomics mirrors, 2024-Q3 → 2025-Q4 |
| `USA` | 1948-Q1 → 2026-Q2 | 54 | 0 | Equals the year-on-year change of `fred.gdpc1` already in the lake for all 54 quarters, max difference 0.000 pp |
| `EA` | 1996-Q1 → 2026-Q2 | 54 | 0 | not cross-checked — FRED's public CSV timed out on this date |
| `G20` | 1998-Q1 → 2026-Q2 | 54 | 0 | none |

The panel needs roughly 48 quarters; all four areas give 54. **This unblocks the China
elasticity**, which was blocked on GDP and not on demand.

Traps, each of which cost a probe to find:

- **The euro area is `EA` and the EU is `EU`.** `EA19`, `EA20` and `EU27_2020` — the codes
  Eurostat and FRED use — return nothing on this dataflow, silently. A first pass that
  guessed them concluded the euro area was not published here. It is.
- **China publishes growth rates, not a real level.** For `CHN` the dataflow carries only
  nominal levels (`PRICE_BASE` `V` and `Q`, national currency) and the two growth
  transformations (`G1`, `GY`). There is no chain-linked level, so a China regressor can only
  be a percentage change — which is what three of the workbook's four blocks use anyway.
- **2021-Q1 reads 18.9 % for China** — the base effect of 2020-Q1's −6.8 %. Excluding 2020
  alone leaves its echo in the panel. The with/without-2020 refit must drop the base-effect
  quarters too, or it does not test what it claims to.
- 57 areas are published. There is **no world aggregate**; `G20` is the widest. It is a
  proxy for world GDP, not world GDP, and must be labelled as such wherever it is used.
- The legacy IMF SDMX host is dead and DBnomics' NBS mirror keeps only a rolling six
  quarters. Neither is a route.

### Demand — JODI secondary table

`https://www.jodidata.org/_resources/files/downloads/oil-data/annual-csv/secondary/{year}.csv`
for closed years and `secondaryyear{year}.csv` for the current one — the same filename split
`pipelines/jodi/client.py` documents for the primary table, and the same seven columns. About
27 MB per closed year.

`FLOW_BREAKDOWN=TOTDEMO`, `ENERGY_PRODUCT=TOTPRODS`, `UNIT_MEASURE=KBD` is total oil product
demand per country per **month**. The only non-numeric marker seen in that slice is `-`.

Sampled across the panel (three files, this date):

| File | Months | US | China | Euro-area 20 members |
|---|---|---|---|---|
| `2013.csv` | 12 | 12/12, mean 19,118 kb/d | 12/12, mean 9,562 kb/d | 20/20 complete, sum 10,043 kb/d |
| `2020.csv` | 12 | 12/12, mean 18,051 kb/d | 12/12, mean 14,574 kb/d | 20/20 complete, sum 8,792 kb/d |
| `secondaryyear2026.csv` | 7 (→ 2026-07) | 7/7, mean 20,773 kb/d | 7/7, mean 14,780 kb/d | 17/20 complete — Croatia, Greece and Malta lag one month |

The eleven years between the samples were not opened here. An earlier session on this date
reported 2002 → 2025 with no missing year files, Russia reporting nothing at all and 55 of
118 countries fully complete; that is consistent with the above but was not re-measured.

Consequences for the model:

- **Three blocks are fittable on public data: USA, China, euro area.**
- **Rest of World is not.** Russia is absent from JODI and no world GDP series exists, so a
  residual cannot be summed honestly on either side. A G20 proxy is possible on the GDP side
  only. Leave it out and say so on the model card.
- **A euro-area quarter is only as complete as its slowest member.** The latest month is
  missing three members; summing the seventeen would understate demand and read as a fall.
  An aggregate with a missing member is no observation, not a smaller one.
- **The euro-area basket is nineteen members, without Malta.** Measured over the whole
  2012-2026 panel after the samples above: Malta is missing 2015-09 to 2016-01, 2017-05 and
  2026-07, and is 0.29 % of the twenty-member sum. With it, the completeness rule costs
  eight quarters of regression panel (46 of 54); without it, none.

First fit on the real panel, 2013-Q1 to 2026-Q2, year-on-year percentage change on both
sides. These are this repo's estimates on public data, not workbook figures.

| Block | n | Slope, full panel | R-squared | Slope, ex 2020-2021 | R-squared |
|---|---|---|---|---|---|
| US | 54 | 2.43 | 0.88 | 1.70 | 0.26 |
| China | 54 | 0.52 (p = 0.17) | 0.04 | 0.97 (p = 0.20) | 0.04 |
| Euro area ex Malta | 54 | 1.40 | 0.78 | 1.73 | 0.48 |

The spec's fourth observation is borne out: most of the US fit is the pandemic. And China
has no statistically significant elasticity on public data in either panel, which is
stronger than "the weakest link" and has to be said on the page.
- **The fitted coefficients will not equal the workbook's**, and are not meant to. Different
  demand source, different GDP source, and the workbook's USA block regresses on a level
  change in US$bn where this would use a percentage. Shown side by side they are a
  diagnostic; they are not a reconciliation target.

## BP Statistical Review (DataHub) — checked live 2026-10-10

`https://datahub.io/energy-and-commodities/bp-statistical-review-world-energy`, 14 CSV
resources, 1.35 MB. The `_r/-/` links 302-redirect to `r2.datahub.io`; fetch the redirect
target, do not assume the first URL serves bytes. Licence: "free to use with attribution" to
BP. Schema confirmed from the real `datapackage.json`, not from the listing page.

**It does not solve this model's blocker.** Every resource is **annual**, and the latest year
is **2019** (BP Statistical Review 2020, 69th edition). The regressions need quarterly
observations through 2026. BP covers 2013–2019 of a 2013–2026 panel at the wrong frequency,
so it cannot fit them. Use it for long-run context and cross-checks, not for the panel.

Note also that BP discontinued this publication: the Energy Institute has published the
successor *Statistical Review of World Energy* since 2023, free, with more recent data. If
fresher annual coverage is wanted, that is the place to look — not confirmed live here.

**What it does close**, all annual and historical, all genuinely absent from this lake today:

| Resource | Why it matters here |
|---|---|
| `coal-prices.csv` — `northwest_europe_usd_tonne`, 1987–2019 | `pipelines/coal/NOTES.md` records API2/API4 as *"never published by EIA at all — a vendor gap, not a backlog item. No amount of EIA-side work closes it."* The NW Europe steam marker is the closest free proxy to API2, and the lake has nothing of the kind |
| `gas-prices.csv` — `netherlands_ttf_usd_mmbtu`, `uk_nbp_usd_mmbtu`, `jkm_usd_mmbtu`, `german_import_usd_mmbtu`, `lng_japan_cif_usd_mmbtu`, 1984–2019 | The lake holds exactly one gas price, `fred.dhhngsp` (Henry Hub). No TTF, no NBP, no JKM anywhere — while SKILL.md §9 and Spec 26 are built on precisely those hubs |
| `oil-spot-prices.csv` — `dubai_usd_bbl`, 1972–2019 | No Dubai series exists anywhere in this project. `manual_physical`'s `SERIES_META` declares Dubai M1/M3 and the Brent–Dubai EFS, all with no data |
| `oil-consumption.csv` — country and regional, kb/d, 1965–2019 | A long-run annual cross-check on MOMR and JODI levels, and a second, independent elasticity fit over six decades rather than twelve years |

**Binding caveats if any of it is ingested.** These are annual averages ending 2019. They are
historical context, never a current reading, and the freshness surface must say so rather
than showing them as stale. Never join an annual average to a daily or weekly series without
running SKILL.md §4's join checklist first — an annual mean and a spot assessment are not the
same quantity. Country naming uses BP's own conventions with regional aggregates
(`Total North America`, `Total CIS`, `USSR`) mixed in beside individual countries, so any
pull must filter aggregates out explicitly, the same discipline `GENERATOR_FUEL_LOCATIONS`
already applies for EIA. Whether China appears under that exact name was **not** confirmed —
the fetch returned a truncated view, so check before relying on it.

## The forward path needs a decision, not a connector

GDP *forecasts* are the model's engine, and no market connector supplies them. Three honest
options, in the order I would consider them:

1. **User-set assumptions.** The workbook already has a `User Input` column beside
   `BI Baseline (via Bloomberg Economics)`. Keeping that as the forward input is transparent,
   costs nothing, and makes the scenario machinery the point rather than a hidden default.
2. **IMF World Economic Outlook** — free, published twice a year, country-level GDP growth
   projections. Would need a small new pipeline.
3. **Drop the forward path**, fit and publish the elasticity only, and let the balance stay
   historical. Smallest build, and still answers "what has the GDP–demand relationship been".

The Hormuz overlay needs none of them: `% of Normal Hormuz Flows` by quarter (the workbook's
own path runs −, 0.15, 0.6, 0.8, 0.9, 1.0, 1.0 across 1Q26–3Q27) and per-country recovery
factors across Saudi Arabia, UAE, Iran, Iraq and Kuwait are **assumptions by construction**.
That part ports cleanly today and is what Spec 33.01's Hormuz screen wants.

## What I would build first

Sequenced so each step is useful alone:

1. **Confirm the consumption route live** — JODI secondary or EIA international. Nothing else
   can be planned until a real series with real history is in hand.
2. **Port the Hormuz overlay.** Pure assumption arithmetic over a supply baseline, no new
   data, and it feeds a screen the spec pack already names.
3. **Refit the four elasticities** on public data, with and without 2020, and show the repo's
   own estimates beside the workbook's with the deviation — the conventions require exactly
   that, and a miss is a visible diagnostic rather than something to tune away.
4. **Then** the balance itself, with the analyst overlay surfaced as a named, editable
   assumption rather than buried in a cell.

## What cannot be ported, and should be said out loud

The supply side's *"analyst-driven overlays … based on market intelligence and company-level
coverage"* are human judgement, not data. No connector reproduces them. Porting the model
means either carrying them as explicit, dated, editable assumptions with an author, or
dropping them and accepting a different balance. Silently inheriting BI's overlays as if they
were observations would put someone else's judgement into this repo wearing the costume of
measured data — which is the failure mode `00_TRADING_CONVENTIONS.md` keeps naming.

## Port compared with the workbook, 2026-10-26

Read against the workbook's `OLS.*` and `For_OLS` sheets. Recorded in structure and direction
only: no coefficient, R², p-value, observation count or panel value from the workbook appears
here, and nothing here is a ratio or difference from which one could be recovered given the
repo's own figures, which are public on the Oil Demand page.

### What the workbook actually regressed

- **USA:** year-on-year change in US oil consumption in mb/d, regressed on the year-on-year
  change in US GDP in US$bn. Level change on level change. Not an elasticity.
- **China, Europe, Rest of World:** year-on-year growth on both sides, carried as fractions
  rather than percentages. The slope is unit-free, so it is the same quantity as the repo's
  slope and can be compared directly.
- **Europe is OECD Europe**, not the euro area. Its regressor is Europe GDP growth from
  Bloomberg Economics.
- **Rest of World** is regressed on global GDP growth. The repo does not fit it (see the plan's
  out-of-scope list).
- **The panel** runs from 1Q 2013 levels, so the first year-on-year observation is 2014, and the
  last observed quarter is 4Q 2025. It **contains 2020 and 2021**. The workbook has no
  ex-pandemic fit.
- **Every intercept is negative**: demand growth below zero at zero GDP growth, the
  efficiency drift. The repo's specification also carries an intercept, so the two are alike on
  this point.

### Direction and rank, block by block

- **USA: not comparable at all.** The workbook's slope is in mb/d per US$bn, the repo's is
  percentage points per percentage point. No row of one may sit beside the other. On fit
  quality alone, both full-panel fits explain most of the variance. The repo's ex-pandemic R²
  collapses, which says the workbook's US
  fit is also likely carried by 2020–2021. The workbook cannot show this, because it has no
  ex-pandemic run.
- **China: same sign, smaller slope here, and a different verdict.** The workbook's China slope
  is positive and statistically significant. The repo's full-panel and ex-pandemic slopes are
  both positive and both smaller than the workbook's, and neither is significant at 5 %. Both
  sources rank China the weakest block on R², and the repo's R² is far below the workbook's.
- **Europe / euro area: same sign, similar size, lower fit here.** The repo's slopes in both
  panels are of the same order as the workbook's. The repo's R² is lower than the workbook's in
  both panels. Different geography (see below), so read this as the same
  relationship measured on a neighbouring basket, not as a replication.

### Why differences are expected, largest first

1. **Specification.** For the USA the two are different regressions. For China and Europe both
   are year-on-year growth on growth, so specification is *not* the cause there.
2. **Demand source.** The repo uses JODI's secondary table, total products, which is national
   reporting. The workbook uses EIA/IEA-style consumption estimates in mb/d. China's JODI demand
   is noisier quarter to quarter than an agency estimate smoothed for stock changes, and noise in
   the dependent variable lowers R². That alone could explain much of China's lost significance.
3. **GDP source.** The repo uses OECD Quarterly National Accounts (seasonally adjusted,
   chain-linked volume). The workbook uses Bloomberg Economics series in local currency (CNY bn,
   EUR mn).
4. **Basket.** OECD Europe there, euro area ex Malta here. OECD Europe adds the UK, Norway,
   Switzerland and Türkiye, among others. Türkiye's demand growth is fast and only loosely tied to
   euro-area GDP, which would pull the workbook's Europe slope away from a pure euro-area one.
5. **Panel end.** The repo's panel runs past 4Q 2025 into 2026, adding a few post-pandemic
   quarters. A minor effect next to the four above.

### Verdict

The port reproduces the workbook's ordering for the two comparable blocks: Europe is a strong,
significant relationship and China is the weak one. It does **not** reproduce China's
significance. The repo's reading is that, on public national data, the China elasticity cannot
be distinguished from zero. The page states this, in words, beside the number. The USA block
is a different model in each source and is never compared as a figure.
