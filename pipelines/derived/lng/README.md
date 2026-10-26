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

## Global view (JODI-Gas, built 2026-10-26)

`python -m pipelines.jodi_gas.pull` (needs `JODI_USERNAME` / `JODI_PASSWORD` in `.env`), then
`python -m pipelines.derived.lng`. LNG exports by exporter and imports by importer for
the 94 countries that report. A month is written only when its reporters cover 98% of typical
volume (`core.lng_balance.coverage`). Named gaps: Russia does not report exports. Taiwan files
zeros for imports, and those are treated as unreported. Thailand, Bangladesh, Pakistan and
Singapore do not report.

2025, bcm: exports US 165.2, Qatar 142.5, Australia 102.3, Malaysia 36.8; imports China 91.7,
Japan 87.2, South Korea 62.5, India 35.1, Europe (EU-27, UK, Türkiye) 176.9. World reported
exports 514, imports 484.

## Not built yet

A projection, and the liquefaction project list (it needs a source per plant capacity).
