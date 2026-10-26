# pipelines/eurostat_gas — notes

EU-27 monthly natural gas from Eurostat's dissemination API: keyless, JSON-stat 2.0.
`python -m pipelines.eurostat_gas.pull` writes `source="eurostat_gas"`. Full history every run
(it takes seconds), because Eurostat revises recent months. Consumer: `pipelines/derived/eu_gas_balance.py`.

## Datasets, confirmed live 2026-10-26

| Dataset | What | Kept |
|---|---|---|
| `nrg_cb_gasm` | Monthly balance, 16 lines (`IPRD`, `IMP`, `EXP`, `STK_CHG_MG`, `IC_OBS`, `TI_EHG_MAP`, `FC_IND`, `FC_OTH`, `STATDIFF`…) | mcm for EU + 27 members; TJ GCV for EU |
| `nrg_ti_gasm` | Imports by partner, `G3000` (all gas) and `G3200` (LNG) | mcm, EU |
| `nrg_te_gasm` | Exports by partner, same split | mcm, EU |

Series ids: `estat.gas.balance.<line>.<geo>`, `estat.gas.balance_tj.<line>.eu`,
`estat.gas.<imports|exports>.<gas|lng>.<partner>.eu`, all Eurostat codes lower-cased.

## Traps, each found in the data

- **`EU27_2020`, not `EU`.** A bare `EU` is accepted and returns nothing
  (`pipelines/macro/NOTES.md` records the same trap for ESI).
- **An unknown filter code is a 200 with an empty dimension**, not an error (confirmed with
  `siec=NOT_A_CODE`). The client raises on any empty dimension. Never relax that check.
- **The EU-27 aggregate lists member states as partners**, and `TOTAL` includes them:
  intra-EU trade, which is about 10 bcm a month. Extra-EU flows are the non-member partners.
- **`G3000` includes `G3200`.** Pipeline = gas − LNG. Summing them double counts LNG.
- **Transit countries appear on both sides**: Albania (TAP), Serbia (TurkStream), Switzerland
  and Ukraine. Use net imports per partner. Gross imports overstate extra-EU supply.
- **The partner is often the last transit country**: Algerian gas arrives "from Tunisia",
  Azeri gas "from Albania" or "Türkiye".
- **EU-27 balance cells go blank whenever any member is missing**, even a member that produces
  nothing: EU production is blank for 2022-02 to 2022-12. Member rows are kept so the
  derived step can rebuild them (`core.eu_gas_balance.fill_from_members`).
- **A month's partner detail can lag its total**: in 2024-03 the import total was published
  with most partners still blank. `core.eu_gas_balance.complete_months` rejects any month whose
  partners do not add up to the total. All of 2020 is rejected the same way.
- **`STK_CHG_MG` is positive for injection** (gas into storage). Confirmed against GIE, where
  Eurostat's monthly stock change in TWh tracks GIE's month-end change with correlation 0.998.
