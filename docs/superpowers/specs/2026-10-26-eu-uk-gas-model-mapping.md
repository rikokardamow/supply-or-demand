# Mapping — the TTF and NBP gas calculators onto this repo's connectors

**Date:** 2026-10-26
**Status:** analysis complete, routes confirmed live (see that section), no design yet
**Source workbooks:** `data/manual/bloomberg/905516197.xlsx` (Dutch TTF, `TZT1 Comdty`, last
reviewed 15 May 2026) and `data/manual/bloomberg/904849657.xlsx` (UK NBP, `FN1 Comdty`, last
reviewed 14 May 2026). Both are Bloomberg Intelligence "Interactive Calculators", 4 sheets each.
**Feeds:** `specs/26_gas-analytics.md` (EU fill trajectory, hub board), `specs/02_gie-gas-storage.md`,
`specs/03_entsog-eu-gas-flows.md`
**Companions:** `2026-10-26-lng-model-mapping.md`, `2026-10-26-eu-carbon-model-mapping.md`

Read-only analysis. Neither workbook was modified, and neither may ever be committed: both are licensed BI
content, kept in the git-ignored `data/manual/`. No figure from either appears below.

## The headline: two copies of one template, both on public statistics

The two files are the **same calculator template** with different rows: identical front page,
identical `Summary` / `Supply` / `Demand` / `Balance` layout, identical formula vocabulary
(`IF`, `IFERROR`, `ISBLANK`, `FIND`, `NA`, which are the override plumbing). **Zero `#NAME?`
cells and no Bloomberg add-in formula in either.** Each names its sources on its front page:

- TTF: **"Eurostat, BBG Terminal"**
- NBP: **"UK Gov, BBG Terminal"** (DESNZ Energy Trends / DUKES)

They are **annual**, in **bcm**. The history runs 2018–2025 for TTF and 2016–2025 for NBP, and
each ends in two projected columns, `2026S` and `2027S` (S for scenario). Each driver row carries
a *BI Baseline* growth rate and an optional *User Input* that overrides it. The front page
documents a "Top-Down" mode (override the summary growth directly) and a "Bottom-Up" mode
(override the components). This is the same convention as the RIN and oil-demand workbooks, and
it ports the same way: as a dated, attributed assumptions file.

One spec covers both, because one port will.

## TTF: it is an EU balance, not a Dutch one

The ticker is Dutch, but the balance is the **EU-27**. Its own-production and gross-supply rows
are on the EU scale, and an order of magnitude too large for the Netherlands. Its
storage row is the EU aggregate fill on 31 December. TTF is in this calculator as the price of
the EU balance, not as the Dutch market. Anything built from it must say "EU-27".

**Rows.** Supply: imports by route, being Russia pipeline, Russian LNG, other LNG, Norway,
North Africa and TAP, the UK balance, other cross-border flows, plus own production. Demand: one
total-demand row with no sectoral split. Balance: storage change, ending storage, and storage
full at 31 December (%).

## NBP: a UK national balance, with a sectoral demand split

**Rows.** Supply: production, and net imports split into Norway, Europe (interconnectors) and
LNG, less exports. Demand: electricity generation, domestic, industrial, services, energy
industry, others. Balance: storage withdrawal or injection, transfers and others.

These rows are **exactly the lines of DESNZ Energy Trends table ET 4.1** (natural gas supply
and consumption), which publishes them quarterly and annually in GWh and million m³. The NBP
calculator is, in substance, ET 4.1 aggregated to years and converted to bcm.

## Input map

| Workbook row | Our route | State |
|---|---|---|
| EU production, imports, inland consumption | Eurostat `nrg_cb_gasm` (monthly balance), `nrg_cb_gas` (annual) | **confirmed live**; no Eurostat gas pipeline yet (`eurostat` in the lake is ESI sentiment only) |
| EU imports by partner and route (Russia, Norway, LNG…) | Eurostat `nrg_ti_gasm` | **confirmed live** |
| Daily pipeline flows (Norway, Russia, TAP, North Africa) | ENTSOG | **in the lake**: `flows` source `entsog`, 16 point pairs, 2024-09 → 2026-10; history is short |
| EU LNG send-out | GIE ALSI | **in the lake**, 2018 → 2026-10 |
| EU storage level, fill %, 31 Dec fill | GIE AGSI `agsi.EU.*` | **in the lake**, 2018 → 2026-10 |
| UK supply and demand by sector | DESNZ Energy Trends ET 4.1 (xlsx, quarterly/annual) | **confirmed live**: `ET_4.1_SEP_26.xlsx` |
| UK annual long history | DUKES chapter 4 (`DUKES_4.1`–`4.4`) | **confirmed live** |
| UK storage | GIE AGSI `agsi.GB` | **stops 2020-12-30** (Brexit); use ET 4.1's stock-change line instead |
| TTF price | FRED `PNGASEUUSDM` (IMF, monthly, $/MMBtu) as a proxy; futures via Spec 18/34 (IBKR, ICE Endex) | proxy **confirmed**; futures entitlement unverified |
| NBP price | none free; Spec 18/34 via IBKR | **gap** |

## Structural observations

1. **The two balances don't close by construction.** EU supply − demand − storage change leaves
   a statistical difference. Eurostat publishes one, and ET 4.1 has "transfers and others".
   The port must carry that residual as its own named row, never fold it into demand.
2. **The UK appears in the TTF balance as a supply route ("UK Balance").** The two models
   therefore share a boundary flow. If both are ported, the UK's net exports to the continent
   must be one series read in both, never two estimates that can disagree.
3. **Annual is a choice, not a constraint.** Every public source above is monthly (Eurostat) or
   quarterly (ET 4.1). The port can publish monthly and aggregate, which is strictly more useful
   for Spec 26's fill-trajectory work. The annual view becomes a sum, not a separate model.
4. **Units.** Eurostat gas balances come in TJ (GCV) and million m³. ET 4.1 comes in GWh and
   million m³. The workbook reports bcm. Convert once, in `core/`, with the gross-calorific basis
   stated: a bcm on a GCV basis and a bcm on a NCV basis differ by about 10%.

## What the port needs

1. **`pipelines/eurostat` for gas**: `nrg_cb_gasm`, `nrg_ti_gasm`, `nrg_cb_gas`, keyless JSON-stat,
   EU-27 plus member states. Shared with the LNG port.
2. **`pipelines/desnz`**: ET 4.1 (quarterly) and DUKES 4.1 (annual). The workbook links
   change with each release (the media id is in the URL), so the pipeline must discover the
   link from the GOV.UK statistics page, not hard-code it. Record a fixture of the page.
3. **`core/gas_balance.py`**: pure arithmetic for the balance, the statistical difference and
   the unit conversions.
4. **An assumptions CSV per calculator** for the 2026–2027 growth drivers, with author and date.
   Leave it empty by default, and when it is empty the page shows history only.

## What cannot be ported, and should be said out loud

The BI Baseline growth rates for 2026 and 2027 are analyst judgement. The TTF and NBP *prices*
come from the BBG terminal, and there is no free daily route for either. The IMF monthly EU
price is a usable TTF proxy if it is labelled as such. NBP has no proxy and stays a gap until
Spec 18/34 confirms an IBKR entitlement.

## Routes confirmed live, 2026-10-26

- **Eurostat** dissemination API, JSON-stat 2.0, keyless:
  - `nrg_cb_gasm?geo=NL&siec=G3000&nrg_bal=IC_OBS&unit=MIO_M3`: 200, "Gas supply,
    transformation and consumption - monthly data", updated 2026-10-23.
  - `nrg_ti_gasm`: 200, "Natural gas imports - monthly data".
  - `nrg_cb_gas` (annual): 200.
- **GOV.UK** "Gas: section 4, Energy Trends": 200. It links `ET_4.1_SEP_26.xlsx` (sheets: Main
  Table, Quarter and Annual, each in GWh and in million m³), plus ET 4.2–4.5 and `Gas_SEP_26.ods`.
  "Natural gas: chapter 4, DUKES": 200, linking `DUKES_4.1`–`DUKES_4.4.xlsx`.
- **FRED** `PNGASEUUSDM`: 200, "Global price of Natural gas, EU", monthly, 1992-01 → 2026-09.

## Sequencing

1. Eurostat gas pipeline (EU-27 first), then DESNZ ET 4.1. Both are confirmed, keyless and
   monthly or quarterly.
2. `core/gas_balance.py`, checked year by year against both calculators' history columns in a
   throwaway script. The result is recorded in prose, never as figures, as was done for the RIN
   and oil-demand ports.
3. A page or a section on `02_gas_storage`: the balance by route, with storage from AGSI and
   the statistical difference shown.
4. Assumptions files and the 2026–2027 projection last, and only if wanted.
