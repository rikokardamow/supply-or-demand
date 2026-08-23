# Spec 05 — US Natural Gas & Power (EIA + gridstatus)

**Week 7 · Est. 8–10 h · Prereq: Specs 00, 01 (reuses EIAClient).**

## Objective & alpha question
Weekly US gas storage vs seasonal corridor; production and LNG-export trend; ISO real-time
load/fuel-mix/LMP scarcity signals (ERCOT, PJM first). Question: *is the US gas balance tightening
faster than the curve implies, and where is power stress emerging?*

## Data sources
1. **EIA v2** (existing client): weekly working gas `natural-gas/stor/wkly` — Lower-48
   `NW2_EPG0_SWO_R48_BCF` + regional (East/Midwest/Mountain/Pacific/South Central incl. salt/non-salt);
   monthly dry production `natural-gas/prod/sum`; monthly LNG exports `natural-gas/move/poe2`.
   **Note:** EIA has no distinct "LNG feedgas" API series — only monthly export volumes; treat
   feedgas as out of scope or proxy it later from pipeline nominations (stretch).
2. **gridstatus** (open-source, free): `uv add gridstatus`. ISO classes for ERCOT, PJM (then MISO,
   CAISO): `get_load`, `get_fuel_mix`, `get_lmp` (real-time/day-ahead, zone/hub level). Some ISOs
   need free credentials — check the repo `.env.template`; add any to `core.settings` as optional.
   Keep pulls to hub/zone level (node-level LMP is huge).

## Data model
- Storage/production/exports → `ts_long` (`geo`='L48' or region).
- ISO load/mix/LMP → `ts_long` (`source`='gridstatus', `geo`='ERCOT.HB_HUBAVG' style ids, freq '5T'/'H' downsampled to hourly for the lake).

## Transformations
- Storage seasonal corridor (excl. 2020) + weekly injection/withdrawal vs 5-yr median for the same week.
- Storage surprise placeholder (manual consensus input) — annotate on chart.
- Production 7-day/30-day avgs; LNG exports YoY.
- ERCOT/PJM: daily peak load vs forecast; net load; LMP heatmap (hour × day) per hub.

## Visualisation spec (page `05_us_gas_power.py`)
1. L48 storage worm chart (headline annotations) + regional small multiples.
2. Dual-axis: dry production (navy) vs LNG exports (light blue).
3. ISO tab per ERCOT/PJM: fuel-mix stack, load vs net-load, LMP hour×day heatmap.

## Sessions

### Session A (weekday, 1 h) — gas storage
> Read NOTES.md, specs/05_us-gas-power.md. Using the existing EIAClient, pull weekly L48 +
> regional working gas history → ts_long. Storage worm chart + regional small multiples on a new
> page 05. Cassette test. Acceptance: latest L48 value matches EIA's weekly report.

### Session B (weekend, 3 h) — gridstatus ISOs
> Add `pipelines/gridstatus_iso/`: wrappers pulling ERCOT + PJM hourly load, fuel mix, and hub-level
> LMP for the trailing 60 days → ts_long (downsample to hourly). Handle any required free
> credentials via core.settings (optional fields). Build the ISO tabs: mix stack, load/net-load,
> LMP heatmap. Acceptance: page renders; one load value sanity-checked vs the ISO dashboard.

### Session C (weekday, 1 h) — production/exports + entrypoints
> Monthly dry production + LNG exports → ts_long; dual-axis chart; `pull_wpsr`-style weekly
> entrypoint scheduled for Thursdays (storage) in Spec 13. Idempotency + tests.

## Definition of Done
- Page 05: storage worm + regionals, production-vs-exports dual axis, 2 ISO tabs with 3 visuals each.
- Feedgas explicitly documented as unavailable via API (no fake series). Tests green.

## Stretch
- Henry Hub prompt (from Spec 07 IB pipeline) vs storage-deviation scatter with fitted curve.
- MISO + CAISO tabs.
