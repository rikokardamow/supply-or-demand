# pipelines/desnz_gas — Claude Code Guide

UK natural gas from DESNZ Energy Trends section 4: keyless, xlsx, released monthly.
`python -m pipelines.desnz_gas.pull` writes `source="desnz"`, geo `GB`. Full history every run.
Consumer: `pipelines/derived/uk_gas_balance.py`.

## Tables, confirmed live 2026-10-26 (September 2026 release)

| Table | Sheet | Content | Kept |
|---|---|---|---|
| ET 4.2 | `Month (mcm)` | Monthly supply and demand from 2008-01 | 19 lines → `desnz.gas.balance.<line>.gb` |
| ET 4.3 | `Data in flat format` | Imports and exports by type, country and pipeline, monthly from 2000-01 | `desnz.gas.<imports\|exports\|net>.<type>.<country>.<pipeline>.gb` |

ET 4.4 carries the same flat sheet as ET 4.3. ET 4.1 is quarterly, and its information is
already in 4.2.

## Traps, each found in the data

- **Links change every release** (a new media id each time). `discover_links` reads them
  from the GOV.UK page and raises unless it finds exactly one workbook per table.
- **`[x]` means not available.** Sector demand is `[x]` before January 2023, and gives no row.
- **The latest month's label is `"[provisional] July 2026"`.** The month comes from the
  sheet's trailing numeric `M` and `Y` columns, never from parsing the label. Provisional
  months are flagged in `desnz.gas.provisional.gb`.
- **`Stock change` is positive for a withdrawal**, the opposite of Eurostat's `STK_CHG_MG`.
- **Net supply = production + net imports + stock change + biomethane.** Synthetic coke
  oven gas is not in it: the published rows add up to the hundredth of an mcm without it.
- **The flat sheet carries totals** (`Total imports`, `Total LNG`, `Total Norwegian pipeline`,
  `Net imports`). They are kept to check the parts, and must never be added to them.
