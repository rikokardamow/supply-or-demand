# Mapping — the global LNG workbook onto this repo's connectors

**Date:** 2026-10-26
**Status:** analysis complete, routes partly confirmed live (see that section), no design yet
**Source workbook:** `data/manual/bloomberg/911324187.xlsx` (Bloomberg Intelligence "Interactive
Calculator", Global LNG Supply-Demand, 6 sheets, project list updated 19 May 2026)
**Feeds:** `specs/26_gas-analytics.md` (LNG netbacks, EU fill), `specs/25_freight-arbitrage.md`
**Companions:** `2026-10-26-eu-uk-gas-model-mapping.md`, `2026-10-26-eu-carbon-model-mapping.md`

Read-only analysis. The workbook was not modified and must never be committed: it is licensed BI
content, and `data/manual/**` is git-ignored for that reason. No figure from it appears below.

## The headline: an annual balance on hand-kept data, with two analyst engines underneath

Scanned every sheet. **Zero `#NAME?` cells.** No Bloomberg add-in formula is used; the only
functions are `SUM` and `IF`. The two price rows that say "Consensus Outlook via CPFC<GO>"
are pasted values from a terminal function, not live links. As with the RIN model, the work is
re-sourcing public data and carrying the analyst's assumptions as named, dated assumptions.
There is no dead feed to replace.

It is **annual, 2017 to 2027**. History runs through 2025; 2026 and 2027 are the analyst's
projection. Everything is in **million tonnes (Mt)**.

## What the model does

1. **`Summary`**: global supply (US, Qatar, Australia, Russia, rest of world) against global
   demand (Asia split into China, India, Japan/Korea/Taiwan and rest of Asia; Europe; Americas;
   rest of world). Surplus or deficit is supply minus demand. Beneath it sit annual Henry Hub,
   TTF and JKM rows, history plus a consensus outlook.
2. **`Supply`** and **`Demand`**: the same rows by year, each with the house override pattern.
   *BI Baseline* is a growth rate, and a *User Input* replaces it when filled.
3. **`SupplyProjection`**: a project-by-project export-capacity table, one row per
   liquefaction plant (Australia, Qatar, US, Africa and others), with owners and capacity by year.
   Summed by country, it drives the supply projection. This is the supply engine.
4. **`DemProjections`**: a country model for the main importers (China, India, Japan, South
   Korea, Taiwan, Thailand and others). Per country it takes GDP growth, a "GDP multiple for
   consumption", domestic production and its decline rate, pipeline imports, regasification
   capacity and utilisation, and solves for LNG as the residual. This is the demand engine. Its
   sheet cites IGU, GIIGNL, Clarksons, BP and BNEF.

## Structural observations

1. **The surplus is not a balance in the oil sense.** LNG supply equals LNG demand plus shipping
   losses and inventory in transit. An annual "surplus" is the analyst's projected capacity
   minus projected uptake. It must be presented as a **capacity overhang**, never as a stock
   build.
2. **The demand engine is the judgement.** "GDP multiple", "LNG % of consumption growth" and
   "production decline" are assumptions, not data. This is the same shape as the oil-demand
   elasticity, and the repo already has the pattern: fit what can be fitted on public data,
   and carry the rest as a dated assumptions file with an author.
3. **The supply engine is mostly public fact.** Plant names, owners, nameplate capacity and
   start dates are published by operators. Their *ramp profiles and delays* are the
   judgement. That splits cleanly into a committed reference file (facts, with a source per row)
   and an assumptions file (ramp, delay), the RD-project-tracker pattern.
4. **One unit label looks wrong.** The JKM consensus row is labelled `Euros per MWH`. JKM is
   quoted in US$ per MMBtu, and the TTF row above it is the one in €/MWh. Either the label was
   copied down or the values are a converted series. Treat the row as **unit-unknown**; never
   port it without resolving which.
5. **A `#DIV/0!` appears in `DemProjections`.** Whatever its cause, a port must not reproduce a
   division by a zero denominator: an undefined ratio is NaN with a reason, never an error
   string in a published cell.

## Input map

| Workbook input | Our route | State |
|---|---|---|
| US LNG exports | EIA v2 `natural-gas/move/expc`, `N9133US2` (MMcf, monthly) | **confirmed live**, last period 2026-07; not yet in the lake |
| Europe LNG send-out / inventory | GIE ALSI | **in the lake**: `alsi.<cc>.*`, 13 countries plus `EU`, 2018 → 2026-10 |
| EU LNG imports by origin (US, Qatar, Russia) | Eurostat `nrg_ti_gasm` (imports by partner, monthly) | **confirmed live** 2026-10-26 |
| Asian imports (China, Japan, Korea, India, Taiwan) | JODI-Gas world database | **unconfirmed**: the download page serves no direct file link |
| Global supply by exporter | Operator reports, GIIGNL annual report | **not a feed**: GIIGNL's report URL 404s; annual, hand-kept |
| Liquefaction project list | Operator announcements | **reference file**, hand-maintained with a source per row |
| Henry Hub | FRED `DHHNGSP` (daily), `PNGASUSUSDM` (monthly) | **confirmed live**; HH spot is planned via Spec 10 |
| TTF | FRED `PNGASEUUSDM` (IMF "Natural gas, EU", $/MMBtu, monthly) | **confirmed live**; monthly only, a proxy for TTF |
| JKM | none free; FRED `PNGASJPUSDM` is "LNG, Asia" (a Japan import price) | **gap**: that series is *not* JKM and must never be labelled as it |
| Consensus price outlook | Bloomberg CPFC | **not portable**: replace with a user assumption or drop |

## What the port needs

1. **`pipelines/eia`**: add `N9133US2` (and the by-destination `expc` series if wanted). It is
   the existing client and key, so a small change.
2. **Eurostat LNG by partner**: `nrg_ti_gasm` carries partner and LNG/pipeline splits. A
   general Eurostat gas pipeline serves this and the TTF balance (see the companion spec), so
   it should be built once.
3. **A liquefaction reference CSV** (`plant, country, owners, nameplate_mtpa, start_year,
   source, as_of`) and a separate **ramp/delay assumptions CSV** with an author and date.
4. **Asian demand**: a spike on JODI-Gas before anything is planned against it.

## What cannot be ported, and should be said out loud

The country demand elasticities and the consensus price outlook are judgement and a paid
terminal function. The global supply total for non-US exporters has no free monthly route; an
annual hand-kept figure from operator and GIIGNL publications is the honest substitute, and it
must be labelled annual and manual.

## Routes confirmed live, 2026-10-26

- **EIA** `GET /v2/natural-gas/move/expc/data/` with `facets[series][]=N9133US2`: 200, "Liquefied
  U.S. Natural Gas Exports", unit `MMCF`, latest period 2026-07.
- **FRED** (project key): `DHHNGSP` daily to 2026-10-20; `PNGASUSUSDM`, `PNGASEUUSDM` and
  `PNGASJPUSDM` monthly from 1992-01 to 2026-09, all in US$ per MMBtu. The keyless
  `fredgraph.csv` endpoint did not answer from this machine; use the API with the project key,
  as `pipelines/macro` does.
- **Eurostat** `nrg_ti_gasm` (natural gas imports, monthly): 200, JSON-stat, dataset updated
  2026-10-23.
- **JODI-Gas**: download page 200, but no direct `.zip`/`.csv` link in its HTML. Needs a spike.
- **GIIGNL** annual report category page: 404.

## Sequencing

1. EIA `N9133US2` and the Eurostat gas pipeline (shared with the TTF port). Both are confirmed.
2. The liquefaction reference CSV. It can be checked against the workbook's own
   `SupplyProjection` country sums, recorded in prose only.
3. The JODI-Gas spike, then Asian demand.
4. The demand engine last, as a fitted elasticity where data allows and named assumptions
   elsewhere.

## Update, 2026-10-26 (later): JODI-Gas and the Atlantic build

- **JODI-Gas bulk file is stale**: `…/gas-data/jodi_gas_csv_beta.zip` returns 200 but holds
  `jodi_gas_beta.csv` dated 2018-10-18, with data from 2009-01 to 2018-08.
- **JODI-Gas API is current but needs an account**: `POST https://www.jodidata.org/api/token`
  with the username (sign-up email) and password returns a JWT, valid for one hour, for
  `GET /api/gasdata`. The limit is 100 requests a minute. This is the route for Asian imports.
- **Built without it**: US exports by destination (EIA, 50 destinations, which add up to
  `N9133US2`), Europe's imports by origin, and the US–Europe mirror. Page `28_lng.py`.
- The liquefaction project list is still not built. Its capacities need a source per row,
  and none is in hand.
