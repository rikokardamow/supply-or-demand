# Mapping — `oil_demand.xlsx` onto this repo's connectors

**Date:** 2026-10-10
**Status:** analysis complete, no design yet
**Source workbook:** `~/Desktop/skill-pdfs/oil_demand.xlsx` (Bloomberg Intelligence, 12 sheets)
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
| China / EU / RofW GDP | Bloomberg Economics | FRED, IDs to be confirmed live | one-line addition to `FRED_SERIES` |
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

1. **JODI secondary table.** `pipelines/jodi/CLAUDE.md` records that the secondary table
   covers *refined products* with its own flow vocabulary including `TOTDEMO` (total demand),
   and that it was deliberately scoped out because the spec wanted crude. That is exactly the
   country-level consumption history this model needs, published back to 2002, no key.
   Separately, `CURRENT_YEAR_HISTORY_DEPTH = 2` caps even the primary pull at two years — a
   constant, raised deliberately.
2. **EIA international energy statistics**, country-level consumption, on the API client the
   repo already has.

Neither has been confirmed live yet. Per this project's own standing rule, confirm the route
and the real series before planning against it — `pipelines/macro/CLAUDE.md` records two
plausible-looking FRED IDs that turned out to be a zinc index and a stale series.

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
| `coal-prices.csv` — `northwest_europe_usd_tonne`, 1987–2019 | `pipelines/coal/CLAUDE.md` records API2/API4 as *"never published by EIA at all — a vendor gap, not a backlog item. No amount of EIA-side work closes it."* The NW Europe steam marker is the closest free proxy to API2, and the lake has nothing of the kind |
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
