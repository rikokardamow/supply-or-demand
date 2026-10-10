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

| Region | n | R² | Intercept | β | p(β) | Regressor label present? |
|---|---|---|---|---|---|---|
| USA | 48 | 0.9006 | −1.0121 | **0.002284** | 1.1e−24 | yes — "Y/Y Change in GDP" |
| China | 47 | **0.3704** | −0.0191 | **1.0570** | 5.7e−06 | no — cell holds `0.07501…` |
| EU | 47 | 0.8213 | −0.0223 | **1.4989** | 1.9e−18 | no — cell holds `0.01638…` |
| RofW | 46 | 0.8618 | −0.0272 | **1.1876** | 1.6e−20 | no — cell holds `0.03598…` |

Four observations that matter before any of this is reproduced:

1. **The USA block is not in the same units as the other three.** Its β is 0.0023 against
   1.06–1.50 elsewhere, and the panel confirms why: `For_OLS` column E carries a GDP *level*
   change (291.57, i.e. US$bn) while the others carry a *percentage* change. A β of 0.0023
   and a β of 1.06 are different quantities and must never be tabled side by side as if they
   were comparable elasticities.
2. **Three of the four blocks lost their regressor label** — cell A18 holds a number rather
   than a name, which is what Excel's regression tool produces when the "labels in first row"
   box is left unticked. The specification therefore has to be inferred from the panel rather
   than read off the output.
3. **China's R² is 0.37.** That single relationship is what converts a GDP forecast into a
   Chinese demand projection, and it explains roughly a third of the variance. It is the
   weakest link in the model and belongs on the model card, not in a footnote.
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
