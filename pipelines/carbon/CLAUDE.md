# pipelines/carbon — Claude Code Guide

EU ETS public data, keyless. `python -m pipelines.carbon.pull` writes `source="eex"` (auctions)
and `source="eu_registry"` (installation totals). Consumer: `pipelines/derived/eu_carbon.py`.
Spec 39 Session A names this package. The registry half and the balance model come from
`docs/superpowers/specs/2026-10-26-eu-carbon-model-mapping.md`.

## EEX primary auctions (confirmed live 2026-10-26)

`https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-<year>-data.xlsx`
for 2020 to the current year. 2012–2019 return 404 at this pattern. One sheet, column A empty,
header row (`Date`, `Time`, `Auction Name`, `Contract`, `Status`, `Auction Price €/tCO2`, ...,
`Cover Ratio`, ..., `Total Revenue €`) found by searching for `Date`, never by position.

- One auction a day per contract: `T3PA` general allowances (→ `eua`), `EAA3` aviation
  (→ `euaa`; none after 2024).
- `cancelled` auctions exist (2020-03-17, two in 2022): no price, flagged in
  `eex.<product>.auction.cancelled`.
- **An auction clearing price is not a market price.** Every label says "auction".
- **Terms of use, reviewed 2026-10-26** (a reading, not legal advice). EEX `/en/disclaimer`
  allows "a single copy for exclusive personal, non-commercial use". "Any commercial use shall
  only be permitted with the express written approval of EEX AG." `/en/market-data/licensing-policies`
  says that passing data to third parties "in raw or in derived form" needs an External Usage
  Licence (Commercial: newsletters, portals; Media: public, raw form only). Kardamow is a paid
  publication, so **EEX-derived series stay in the private dashboard**.
  `core.publish.LICENCE_RESTRICTED_PREFIXES` drops `eex.*`, `derived.eu_carbon.price.*` and
  `derived.eu_carbon.balance.*` (its auction volumes are EEX-derived) from every serving-layer
  publish, including the `publish_series` sweep. Lift a prefix only once a licence is in place.

## Union Registry installation file (confirmed live 2026-10-26)

`verified_emissions_<year>_en.xlsx`, linked from the Union Registry page with a
`/document/download/<uuid>_en?filename=...` link that changes each release. The newest year
link is discovered from the page. Sheet `data`, header on row 3, one row per account:
stationary installations, aircraft operators and (from 2024) shipping companies.

- Columns per year: `ALLOCATION_<y>`, `ALLOCATION_RESERVE_<y>` (new entrant reserve, Art.
  10a(7)), `ALLOCATION_TRANSITIONAL_<y>` (Art. 10c), `VERIFIED_EMISSIONS_<y>`, Swiss `CH_*`
  (left out), and in 2025 `ALLOCATION_FEETS`, `ALLOCATION_BYICELAND`. Those last two are
  undocumented, kept apart and left out of supply. 2008 is spelled `ALLOCATION2008`.
- **`n/a` means nothing allocated or verified, which is not 0. `Excluded` means out of scope.**
  Neither gives a value.
- Pre-2013 data is not comparable (phase III scope change): the model starts at 2013.
- Registry `GB` holds UK history to 2020. The model leaves it out of every year.
- The file is extracted just after the reporting deadline (the 2025 file on 2026-04-01). Its
  latest year can therefore be incomplete. `core.carbon_balance.complete_years` tests only that year.
- Shipping emissions are reported **before** the phase-in. Demand applies
  `maritime_phase_in.csv` (40% for 2024, 70% for 2025, 100% from 2026; Directive (EU) 2023/959).

## `tnac.csv` — Total Number of Allowances in Circulation (2026-10-26)

Hand-maintained and annual. Each figure is quoted with its source. TNAC 2016–2025, and MSR intake
for the TNAC years 2020–2025 (each intake runs September of Y+1 to August of Y+2). Sources:
Commission PDFs (`c_2017_3228` … `c_2021_3266`) and Commission news releases on
climate.ec.europa.eu. **EUR-Lex answers scripted requests with HTTP 202 and an empty body (a
bot check), so the Official Journal versions were not fetched. Do not work around it.**
The 2023 TNAC comes from C(2025) 3120, where the PDF text reads "1 111 736 5353": the last 3 is a
footnote marker. 24% of 1,111,736,535 is exactly the published intake.
`core.carbon_balance.msr_intake` reproduces all six published intakes to within one allowance,
and a test pins this. Add a row each June when the Commission publishes the next TNAC.
