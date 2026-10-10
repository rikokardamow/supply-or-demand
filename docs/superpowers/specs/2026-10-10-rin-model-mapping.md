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

---

## Routes confirmed live, 2026-10-10

The Sequencing section above says nothing can be planned until the demand baseline is real.
It now is. Everything below was read from a live response, not inferred from a series name.

### EIA STEO — confirmed, and it carries the forward path for free

`GET /v2/steo` returns 200. **1,469 series codes**, frequencies annual/quarterly/monthly,
`startPeriod` 1974-01 and `endPeriod` **2027-12**. The route needs no new key: it is the
same `settings.eia_api_key` every other EIA pipeline uses.

The real codes, read off the `seriesId` facet by description. Three of the seven I guessed
from the workbook's own labels do not exist, which is the whole reason for this step:

| Code | Description | Confirmed range (monthly) |
|---|---|---|
| `MGTCPUSX` | Motor Gasoline Product Supplied | 456 obs, 1990-01 → 2027-12 |
| `DFTCPUS` | Distillate Fuel Oil Product Supplied | → 2027-12 |
| `JFTCPUS` | Jet Fuel Product Supplied | → 2027-12 |
| `EOTCPUS` | Fuel Ethanol Consumption | 419 obs, 1993-02 → 2027-12 |
| `BDTCPUS_PS` | Biodiesel Product Supplied | → 2027-12 |
| `RDTCPUS_PS` | Renewable Diesel Product Supplied | 216 obs, 2010-01 → 2027-12 |
| `PATCPUSX` | Total Petroleum and Other Liquids Product Supplied | → 2027-12 |

`MGTCPUS`, `JKTCPUS` and `COTCPUS` are **not published**. Units are
`million barrels per day` on every row.

**The find that changes the arithmetic.** STEO also publishes `MGTCPUSX_P`
("Petroleum-based Gasoline Consumption") and `DFTCPUS_P` ("Petroleum-based Distillate
Consumption"). The RFS percentage standards apply to *non-renewable* gasoline and diesel, so
these `_P` series are the correct denominator and the headline `MGTCPUSX`/`DFTCPUS` are not —
using the totals double-counts the renewable volume already blended in. This was not visible
from the workbook's labels and would have been an easy, invisible error.

### A projection is not an observation, and the API does not say which is which

STEO rows carry only `period`, `seriesId`, `seriesDescription`, `value`, `unit`. There is **no
per-row forecast flag**, no vintage field, and no `lastUpdated` on the route metadata — only
the route description's "Monthly short term (18 month) projections". So a naive ingest writes
EIA's 18-month model output into the lake wearing the same clothes as measured history.

The boundary is nonetheless groundable, and from an authoritative EIA route rather than an
assumption: `GET /v2/petroleum/sum/snd/data/` with `facets[series][]=MGFUPUS1` (US Product
Supplied of Finished Motor Gasoline, monthly, MBBL) returns actuals whose **last period is
2026-07**. That is where STEO's history ends; 2026-08 → 2027-12 is model output. The lake also
already holds the weekly cross-checks — `WGFUPUS2`, `WDIUPUS2`, `WKJUPUS2`, `WRPUPUS2`, all
running to 2026-10-02.

### The existing `get_series` cannot be reused for STEO

`EIAClient.get_series` builds `facets[series][]` and reads `row["series"]`, `row["units"]` and
`row["area-name"]`. STEO takes `facets[seriesId][]` and returns `seriesId`, `unit` (singular)
and `seriesDescription`, with **no `area-name` at all**. Pointing the existing method at the
route fails on the facet name and then on every field. The client already carries three fetch
variants (`_fetch_rows`, `_fetch_operational_rows`, `_fetch_facet_rows`) for exactly this
reason; STEO needs a fourth, not a widened third.

### EPA EMTS — live, but the shape is still unknown

The hub is `https://www.epa.gov/fuels-registration-reporting-and-compliance-help/public-data-renewable-fuel-standard`
(200). The two URLs this spec's own input map implied are both 404 — EPA has restructured. The
real sub-pages exist (`rins-generated-transactions`, `available-rins`,
`rin-trades-and-price-information`, `annual-compliance-data-obligated-parties-and`,
`spreadsheet-available-rins-date-renewable-fuel`) and all return 200, but **none exposes a
direct `.csv`/`.xlsx` link in its HTML** — the data is served through embedded tables or a
JS-driven viewer.

So EMTS is not plannable yet and is **out of the first plan**. It needs its own scoped
investigation of what those pages actually serve. This is a clean seam: EMTS supplies *actual*
RIN generation, while the mandate arithmetic needs only the STEO baseline and the EPA
rulemaking reference figures. The mandate half can be built, tested and checked against the
workbook with no EMTS at all; generation-versus-mandate is the half that waits.

### Consequence for sequencing

Steps 1 and 3 of the Sequencing section are unblocked and are the first plan. Step 2 becomes a
spike. Step 4 is unchanged — last, and dependent on the balance.
