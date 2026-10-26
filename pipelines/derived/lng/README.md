# LNG — the committed model files

This repo's own Atlantic LNG model on public data: where US LNG goes (EIA), where Europe's LNG
comes from (Eurostat and DESNZ), and how far the two statistics agree. A Bloomberg Intelligence
global LNG calculator served as a layout example only.

    python -m pipelines.eia.pull_lng_exports
    python -m pipelines.eurostat_gas.pull
    python -m pipelines.desnz_gas.pull
    python -m pipelines.derived.lng

## `destinations.csv`

`destination, region, bloc, note`. Region groups EIA destinations for the chart, and bloc
(`eu` / `uk` / `other`) drives the mirror check. A destination EIA adds later lands in
`unmapped` on the page until it is added here. It is never dropped.

## What the 2026-10-26 run shows (public data)

- US LNG exports to Europe: 34.5 bcm (2021) → 106.7 bcm (2025), 68% of the US total.
- Europe (EU + UK) LNG from outside Europe, 2025: US 65.2, Algeria 24.0, Nigeria 14.7,
  Russia 12.7, Qatar 10.4 bcm, origin not specified 16.3 bcm.
- **Mirror**: EU statistics record 64–71% a year of what the US reports shipping to the EU.
  The UK and US agree within a few per cent. Both views are published; neither is corrected.

## Not built yet

Asian demand. JODI-Gas is the public route, but its bulk CSV
(`jodi_gas_csv_beta.zip`) stops in 2018-08, and its API needs a free jodidata.org account
(JWT from `POST /api/token` with username and password; `GET /api/gasdata`). Add
`JODI_USERNAME` / `JODI_PASSWORD` to `.env` to unblock it.
