# pipelines/oecd — notes

## Keyless SDMX, CSV out
`https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/{key}?format=csvfile`
— the OECD's Quarterly National Accounts. No key. Confirmed live 2026-10-10.

## The one key this pipeline uses
`Q.Y.{areas}...B1GQ.....L.GY.` — quarterly, seasonally adjusted, GDP, chain-linked volume
(real), growth on the same quarter a year earlier, in percent. Join areas with `+`.

## An unknown area is omitted silently — the euro area is `EA`
Alone, an unknown `REF_AREA` returns HTTP 404 `NoRecordsFound`. Beside a valid one it
returns HTTP 200 and simply leaves that area out. `EA19`, `EA20` and `EU27_2020` are all
unknown on this dataflow. A first probe that guessed them concluded the euro area was not
published here. `client.fetch_real_gdp_growth` raises if any requested area is absent —
do not remove that check.

## China has growth rates only
For `CHN` the dataflow carries nominal levels (`PRICE_BASE` `V` and `Q`) and the growth
transformations `G1` and `GY`. There is no chain-linked level. Anything needing a real
China GDP *level* cannot come from here.

## No world aggregate
57 areas, of which `G20` is the widest. It is a proxy for world GDP, not world GDP.

## Verified
`CHN` equals China NBS's own index (preceding year = 100) for 2024-Q3 → 2025-Q4. `USA`
equals the year-on-year change of `fred.gdpc1` for all 54 quarters from 2013-Q1. `EA` was
not cross-checked. History: `CHN` from 1993-Q1, `EA` from 1996-Q1, `USA` from 1948-Q1.
