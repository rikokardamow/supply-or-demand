# Mapping — the EU carbon calculator onto this repo's connectors

**Date:** 2026-10-26
**Status:** analysis complete, routes confirmed live (see that section), no design yet
**Source workbook:** `data/manual/bloomberg/904960927.xlsx` (Bloomberg Intelligence "Interactive
Calculator", European Carbon Allowances, `MOA Comdty`, last reviewed 14 May 2026, 3 sheets)
**Feeds:** `specs/39_carbon-eua.md` (EUA price and the fuel-switching price)
**Companions:** `2026-10-26-eu-uk-gas-model-mapping.md`, `2026-10-26-lng-model-mapping.md`

Read-only analysis. The workbook was not modified and must never be committed: it is licensed
BI content, kept in the git-ignored `data/manual/`. No figure from it appears below.

## The headline: the EU ETS supply-demand balance, from official registry data

The template is the same as the TTF and NBP calculators: annual, BI Baseline growth rates with
User Input overrides, and `S`-suffixed scenario columns. **Zero `#NAME?` cells**, and the only
formula function is `IF`. The sources are named on the sheet itself: **European Environment
Agency, European Commission and Bloomberg Intelligence**. Footnotes link the EEA ETS data
viewer ("verified for years 2013–2023 as of Oct. 14, 2024") and the Commission's annual Total
Number of Allowances in Circulation (TNAC) communication (`eur-lex.europa.eu/eli/C/2024/3415/oj`).

**Its verified history is stale.** The footnote dates the verified data to October 2024, ending
at 2023, and the sheet's columns switch to `S` (scenario) from 2024. Verified emissions for
2024 and 2025 are now published. A port is strictly fresher than this workbook on day one.

## What the model does

- **Price.** Annual EU carbon price history, and a consensus outlook pasted from Bloomberg CPFC.
- **Summary.** Surplus or deficit in million allowances, being allowances issued minus emissions.
- **Demand, as emissions.** Heat and power, industrial, aviation, and maritime (from 2024).
- **Supply.** Freely allocated allowances (stationary), auctioned allowances, aviation
  allowances, and other adjustments (policy).
- **Market Stability Reserve.** MSR injections (September–August), the injection rate, TNAC, the
  calendar-year impact on auction supply, and the auction pool before MSR.

## Input map

| Workbook row | Our route | State |
|---|---|---|
| Verified emissions by installation and sector | EU Union Registry `verified_emissions_<year>_en.xlsx` | **confirmed live**, 2025 file present, installation level |
| Free allocation | same file, `ALLOCATION_<year>` columns | **confirmed live** |
| Sector split (heat & power, industrial, aviation) | `MAIN_ACTIVITY_TYPE_CODE` in the same file, plus its `activity codes` sheet | **confirmed live**; a code-to-sector map is needed |
| Compliance status | Union Registry `compliance_<year>_code_en.xlsx` | **confirmed live** |
| Auctioned volume and clearing price | EEX primary auction report `emission-spot-primary-market-auction-report-<year>-data.xlsx` | **confirmed live**, daily to 2026-10-26 |
| TNAC, MSR intake | Commission's annual TNAC communication (Official Journal) | **reference file**: annual, hand-maintained, sourced per row |
| EUA continuous price | ICE EUA futures via IBKR (Spec 39 preference 1) | **unverified**: entitlement not checked |
| Consensus outlook | Bloomberg CPFC | **not portable** |

## Structural observations

1. **The auction price is not the market price.** EEX primary auctions clear once a day at a
   single price. They are free and official, but they are an auction print, not a continuous
   settlement. Spec 39 already says so. It must survive into every label: "EUA auction
   clearing price", never "EUA price".
2. **The MSR runs September to August; everything else runs on calendar years.** The workbook
   carries a "calendar-year impact" row precisely to bridge the two. The port must keep both
   periods explicit and convert in one tested function. Mixing them silently shifts supply by
   a third of a year.
3. **Maritime enters in 2024** at a phased surrender share. A series that starts in 2024 is not
   a series with zeros before it: no data is not zero (golden rule).
4. **Installation data needs aggregation with care.** One registry file holds stationary
   installations, aircraft operators (including Swiss-linked `CH_` columns) and, from 2024,
   maritime companies. The sector comes from `MAIN_ACTIVITY_TYPE_CODE`, mapped through the
   file's own `activity codes` sheet; the aircraft operators sampled carry code 10. A test must
   pin the code-to-sector map. The `Read Me` defines **`n/a` as "no allocation made / no emissions
   verified", which is distinct from `0`**, and treating `n/a` as zero is exactly the "no data is not zero" error.
   It also warns that data from 2013 on is **not comparable** with 2012 and before (the
   phase III scope change), so a long history must break at 2013.

## What the port needs

1. **`pipelines/carbon`** (Spec 39 Session A already names it):
   - EEX auction reports, one xlsx per year, giving `eex.eua.auction.price` and the volume
     series, as in Spec 39. Spec 39 also names `.cover_ratio`: check that it is published or
     derivable from the file's volume columns before relying on it.
   - The Union Registry verified-emissions and allocation files, annual, aggregated to EU by
     sector.
2. **A TNAC/MSR reference CSV** (`year, tnac_mt, msr_intake_mt, period, source, as_of`) from
   the Commission's communications.
3. **`core/carbon_balance.py`**: pure arithmetic for the surplus, the MSR period bridge and the
   sector aggregation.

## What cannot be ported, and should be said out loud

The BI Baseline growth rates for emissions and the consensus price are judgement and a paid
terminal function. EEX's terms may restrict redistribution of auction data. Spec 39 already
requires the terms recorded in `pipelines/carbon/NOTES.md`, and the series kept off the
public site if they forbid it.

## Routes confirmed live, 2026-10-26

- **EEX** `public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-2026-data.xlsx`:
  200, one sheet `EU ETS1`. Its column groups are References, Prices, Volumes, Participants and
  Revenue, and the first columns are Date, Time, Auction Name, Contract, Status, Auction Price €/tCO2,
  Minimum Bid and Maximum Bid. Latest row 2026-10-26. The
  2025 file is also 200. The auctions page itself carries no direct link; the file URL follows
  the year pattern.
- **European Commission**, Union Registry page: 200. It links `verified_emissions_2025_en.xlsx`
  (8.2 MB; sheets `Read Me`, `data`, `activity codes`, `CH adm. Aviation Operators`; extracted
  2026-04-01; history from 2008) and
  `compliance_2025_code_en.xlsx`, plus earlier years. Columns include `REGISTRY_CODE`,
  `INSTALLATION_NAME`, `MAIN_ACTIVITY_TYPE_CODE` and `ALLOCATION_2025`. Download links are
  `/document/download/<uuid>_en?filename=…` and change per release, so discover them from the
  page.
- **EEA** ETS data viewer and the Commission's MSR page: both 200 (HTML; no file link scraped).

## Sequencing

1. EEX auction reports. They are the price leg Spec 39 needs, confirmed, daily and keyless.
2. Union Registry verified emissions and allocation, aggregated by sector.
3. The TNAC/MSR reference CSV.
4. `core/carbon_balance.py`, checked against the workbook's 2013–2023 history columns in prose
   only, then a carbon section beside Spec 39's switching-price card.
