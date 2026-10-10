# Mapping — the RIN model workbook onto this repo's connectors

**Date:** 2026-10-10
**Status:** analysis complete, no design yet
**Source workbook:** `~/Desktop/skill-pdfs/849726237.xlsx` (Bloomberg Intelligence, 22.7 MB, 26 sheets)
**Companion:** `docs/superpowers/specs/2026-10-10-oil-demand-model-mapping.md`

Read-only analysis. The workbook was not modified and must never be committed: licensed BI
content, and `data/manual/**` is git-ignored for that reason.

## The headline: nothing here is vendor-locked

Scanned every sheet for dead add-in formulas. **Zero `#NAME?` cells** across ~21,000
populated cells in 25 working sheets. This workbook has no live Bloomberg feeds at all — it
is hand-maintained public data with analysis built on top.

That makes it a fundamentally easier port than `oil_demand.xlsx`, where the Demand sheet is
`#NAME?` in every cell and the forward path depends on proprietary GDP forecasts. Here the
work is reading the method and re-sourcing public data, not finding substitutes for a feed
that no longer exists.

The workbook names its own sources, on its `Contents & Legend` and `Notes` sheets:

- **US EIA** — Short-Term Energy Outlook (STEO), State Energy Data System (SEDS), Annual
  Energy Outlook (AEO 2023; its own Notes record that the EIA did not publish a 2024 AEO).
- **US EPA** — the EPA Moderated Transaction System (EMTS), which is where RIN generation
  comes from.

Documented transformations: 1 barrel = 42 gallons, monthly periodicity.

## What the model does

Three parts, per the workbook's own `How-To Guide`:

1. **RIN Balance** — a fuel-demand baseline from EIA STEO, user-adjustable through a
   distillate-to-diesel reconciliation. The **implied mandate** is that baseline multiplied
   by the EPA's final percentage standards. RIN generation is then stacked by category:
   the conventional mandate (D6) is met with ethanol; excess conventional rolls into the
   non-cellulosic advanced mandate (D4+D5); whatever remains is compared against domestic
   renewable diesel.
2. **RIN Bank** — gross generation from the balance rolls in by category; the implied
   mandate feeds the reported RVO, and the total RVO plus available RINs follow from there.
3. **RD Project Tracker** — every publicly announced renewable-diesel project through 2027,
   with user-adjustable mix, utilisation and inclusion.

The same override convention as the other workbook: *"BI Baseline is default value and
overridden if user input is populated."* That pattern should survive the port as an explicit,
named assumption rather than a hidden cell.

## Input map

| Workbook input | Source | Our route | State |
|---|---|---|---|
| Fuel demand baseline | EIA STEO | EIA v2 API on the existing client | **absent** — 0 STEO series in the lake |
| RIN generation by category (D3–D7) | EPA EMTS | public EPA data, free, no key | **absent** — no EPA pipeline exists |
| EPA final volume targets, 2023–2027 | EPA rulemaking | hand-maintained reference CSV | **absent**; small — 7 categories × 5 years |
| EPA percentage standards, 2011– | EPA rulemaking | hand-maintained reference CSV | **absent**; on the `SREs` sheet today |
| Small refinery exemptions, petitions by year | EPA SRE dashboard | hand-maintained or scraped | **absent**; `SREs` is 451×34 |
| Small-refinery capacity list (~40 refineries, bpd) | EIA refinery capacity report | hand-maintained reference CSV | **absent**; the SRE-eligible universe |
| Ethanol production | EIA | `pipelines/eia/pull_ethanol_weekly.py` | **in the lake** — 6 series, US + all five PADDs, 3,588 rows, 2010-06 → 2026-08, MBBL/D |
| Biofuel capacity | EIA `pnp/capbio` | `pipelines/eia/pull_biofuels.py` | **in the lake** — 3 series (biodiesel, renewable diesel & other, fuel ethanol), MMGL |
| Biofuel feedstocks | EIA `pnp/feedbiofuel` | `pipelines/eia/pull_biofuels.py` | **in the lake** — 22 of 26 series, MMLB (4 report null for every period, confirmed live) |
| RD project pipeline | company announcements | judgement, not a feed | **not portable as data** |

**Never plot `capbio` and `feedbiofuel` on one axis**: MMGL is a volume, MMLB a mass.
`pipelines/eia/CLAUDE.md` records this.

## What the port actually needs

Two new pipelines and four reference files. No vendor, no key, nothing paywalled.

1. **`pipelines/eia/pull_steo.py`** — the fuel-demand baseline, the single biggest missing
   input. STEO is on the EIA v2 API, so it reuses the existing client and key. Confirm the
   route and its real series codes live before planning against them;
   `pipelines/eia/CLAUDE.md` is a long record of why guessing an EIA code fails.
2. **`pipelines/epa/`** — a new package for EMTS RIN generation. First of its kind here, so
   it needs its own `CLAUDE.md` and a cassette test, per the root guide.
3. **Reference CSVs**, committed beside their pipeline the way `quotas.csv` and
   `contract_specs.csv` are: EPA volume targets, EPA percentage standards, the SRE petition
   history, and the small-refinery capacity list. All small, all annual, all from published
   rulemakings — and all needing a `source` and `as_of` column so a figure can be traced.
4. **The RD project tracker** is not data. It is a dated, attributed assumption file, the
   same shape as the Hormuz levers.

## A real figure worth checking against the repo

The workbook's 2026 and 2027 volume targets are the EPA's **proposed** numbers, not final —
its How-To says so. Biomass-based diesel jumps from 5.356 billion RINs in 2025 to **8.856**
in 2026, a 65% step. Anything built on it must carry that it is a proposal, and the port
should re-check whether those figures have since been finalised or revised rather than
inheriting a 2025-vintage assumption as fact.

## Sequencing

1. Confirm the STEO route and its series codes live. Nothing else can be planned until the
   demand baseline is real.
2. Confirm what EPA EMTS actually publishes and in what shape.
3. Port the mandate arithmetic — implied mandate from baseline × percentage standards — with
   the reference CSVs. That is testable against the workbook's own `RVO Billion RINs` block
   the same way the Hormuz port was checked against its `Scenario` columns.
4. The RIN Bank and the RD tracker last; both depend on the balance.

The Hormuz port is the pattern to follow: pure arithmetic in `core/`, assumptions in dated
and attributed files, licensed inputs in the git-ignored drop, and the port checked cell by
cell against the workbook's own published outputs — which is what found the 1Q 2027 error
there.
