# Weather Module Spec — Energy Dashboard
**Module name:** `weather`
**Owner:** Riko
**Status:** Draft v1, 4 September 2026
**Fits into:** Python energy dashboard, Railway deployment, Grafana (phase 1) → React + Leaflet (phase 2)
---
## 1. Purpose
Reproduce the Tropical Tidbits class of model imagery (2 m temperature anomaly, ensemble spread, wind, tropical tracks) from the underlying public model data, and derive the numeric signals that natural gas markets actually trade on: population-weighted degree days, run-over-run changes, model divergence, freeze-off risk and Gulf infrastructure exposure.
The map is the visual layer. The alerts are the product. Every alert must be reproducible from stored numbers, not from an image.
**Non-goals (v1):** scraping Tropical Tidbits or any third-party rendered imagery; sub-daily nowcasting; Asian gas markets; any trading execution.
---
## 2. Markets and what drives them
| Market | Demand driver | Supply driver | Weather field |
|---|---|---|---|
| Henry Hub / US regional | HDD/CDD, power burn | Freeze-offs (Permian, Bakken, Appalachia), Gulf shut-ins, LNG feedgas | T2m anomaly, 10 m wind (ERCOT/SPP), NHC cone |
| TTF / NBP | HDD (DE, UK, FR, IT, NL), gas-for-power | Norwegian outages (not weather), LNG arrivals | T2m anomaly, North Sea 10 m wind, solar (later) |
---
## 3. Data sources
All free. Verify endpoints on first run; NOMADS in particular changes paths.
### 3.1 Deterministic models
| Model | Source | Resolution | Cadence | Horizon | Access |
|---|---|---|---|---|---|
| GFS | NOMADS GRIB filter (`filter_gfs_0p25.pl`) | 0.25° | 00/06/12/18z | 384 h | HTTP, subset by variable, level, bounding box |
| ECMWF IFS (open data) | `ecmwf-opendata` Python client | 0.25° | 00/12z (06/18z short) | 240 h (360 h for some) | Existing ECMWF key |
| ECMWF AIFS | same client, `model="aifs-single"` | 0.25° | 00/12z | 360 h | same |
### 3.2 Ensembles
| Model | Source | Members | Use |
|---|---|---|---|
| GEFS | NOMADS (`filter_gefs_atmos_0p50a.pl`), 0.5° | 31 | Spread on T2m; probability of anomaly thresholds |
| ECMWF ENS open data | `ecmwf-opendata`, `stream="enfo"` | 51 | Same, higher weight |
### 3.3 Climatology (anomaly baseline)
Pick one and stay with it; label it on every map.
- **Option A (recommended):** ERA5 daily T2m 1991–2020, from Copernicus CDS via `cdsapi`, pre-computed once into a 366-day × grid NetCDF, smoothed with a 31-day running mean. Uses existing ECMWF/CDS credentials.
- **Option B:** NOAA PSL CFSR or NCEP-NCAR reanalysis daily long-term means (matches the 1981–2010 baseline Tropical Tidbits uses).
Store as `data/climatology/t2m_daily_{source}_{period}.nc` on a 0.25° grid. Regrid models to this grid with `xesmf` or `xarray.interp`.
### 3.4 Tropical
- NHC GIS: forecast cone, track, wind radii, best track — shapefile/KMZ per advisory.
- NHC RSS/JSON for active storm list.
- Optional: HAFS/HWRF tracks via NOMADS for model consensus.
### 3.5 Degree-day reference data
- NOAA CPC population-weighted HDD/CDD (daily, by state and census region, with forecast weeks 1–2). Use as (a) the weighting scheme and (b) a validation series for our own calculation.
- Population weights: CPC state weights, or a 2020 gridded population raster (e.g. GPW/WorldPop at 0.25°) for grid-level weighting.
### 3.6 Static geography (`data/geo/`)
- US state and census-region polygons; EIA gas regions (East, Midwest, South Central, Mountain, Pacific).
- European country polygons.
- Gas production basins: Permian, Haynesville, Appalachia (Marcellus/Utica), Bakken, DJ, Anadarko, Eagle Ford (approximate polygons, hand-drawn GeoJSON is fine).
- Power markets: ERCOT, SPP, MISO, PJM, CAISO footprints.
- Gulf of Mexico federal offshore lease area polygon.
- Point assets — LNG export terminals (verify coordinates before use):
| Terminal | Lat | Lon | Capacity (Bcf/d, approx.) |
|---|---|---|---|
| Sabine Pass | 29.74 | −93.87 | 4.5 |
| Golden Pass | 29.76 | −93.92 | 2.4 (ramping) |
| Cameron | 29.98 | −93.31 | 2.0 |
| Calcasieu Pass | 29.77 | −93.33 | 1.6 |
| Plaquemines | 29.61 | −89.95 | 2.6 (ramping) |
| Freeport | 28.94 | −95.32 | 2.4 |
| Corpus Christi | 27.89 | −97.26 | 2.4+ |
| Elba Island | 32.09 | −81.06 | 0.35 |
| Cove Point | 38.39 | −76.39 | 0.8 |
Also: Henry Hub (29.98, −92.03), Waha (31.5, −103.5), and major Gulf processing (Sabine, Lake Charles). Store as `data/geo/assets.geojson` with `type`, `capacity_bcfd`, `market`.
---
## 4. Architecture
```
weather/
  ingest/
    gfs.py           # NOMADS filter download, subset, GRIB → xarray
    gefs.py
    ecmwf.py         # ecmwf-opendata (IFS, AIFS, ENS)
    nhc.py           # advisories, cone, track
    climatology.py   # one-off build + loader
  compute/
    anomaly.py       # model − climatology on common grid
    degree_days.py   # HDD/CDD, population-weighted, regional
    spread.py        # ensemble stats
    freeze.py        # freeze-off hours per basin
    exposure.py      # NHC cone ∩ asset polygons
    diff.py          # run-over-run, model-vs-model
  render/
    style.py         # Kardamow palette, fonts, layout
    maps.py          # cartopy PNGs
    charts.py        # degree-day strips, spread fans
  alerts/
    rules.py         # threshold definitions (YAML-driven)
    dispatch.py      # write to alerts table; webhook to orchestrator
  store/
    schema.sql
    io.py            # Postgres (Railway) + object storage for PNG/NetCDF
  jobs/
    run_cycle.py     # entry point: one model run end-to-end
    build_climo.py
  config.yaml
```
**Runtime:** Python 3.11+. Dependencies: `xarray`, `cfgrib` (needs `eccodes`), `netCDF4`, `numpy`, `pandas`, `geopandas`, `shapely`, `cartopy`, `matplotlib`, `ecmwf-opendata`, `cdsapi`, `requests`, `pyyaml`, `psycopg[binary]`, `xesmf` (optional).
**Scheduling:** Railway cron (or APScheduler in a worker) — see §9.
**Storage:**
- Raw GRIB: not retained beyond 48 h (disk cost).
- Processed NetCDF per run: T2m anomaly, wind, spread at daily resolution — retain 30 days.
- PNGs: object storage (Railway volume or S3-compatible), retain 90 days.
- Postgres: all derived numbers, indefinitely.
---
## 5. Computations
### 5.1 Common grid and time base
- Grid: 0.25°, two domains — `us` (20–55°N, 130–60°W) and `eu` (35–72°N, 15°W–35°E).
- Time: convert model valid times to **local-day means** (US: America/Chicago as the single gas-market day; EU: Europe/Berlin). Daily mean T2m = mean of 6-hourly values in that local day. Days with fewer than 3 samples are dropped.
### 5.2 Anomaly
`anom(day, grid) = T2m_model(day, grid) − climo(doy, grid)`
Same for ensemble mean. Output units °C. Also store `anom_f` for US display.
### 5.3 Degree days
Per grid cell, from daily mean T in °F:
- `HDD = max(0, 65 − T)`, `CDD = max(0, T − 65)`.
- Population-weighted regional value: `Σ (w_i × DD_i) / Σ w_i` over cells in the region polygon.
- Regions: L48 total, 9 census divisions, 5 EIA gas regions, ERCOT, and for EU: DE, UK, FR, IT, NL, and EU-5 weighted.
- Normals: from the climatology itself (30-year) and, where CPC provides it, the 10-year normal for cross-check.
- Cumulative windows: days 1–7, 8–15, 1–15; weeks 3–4 from CFSv2/ECMWF extended when added.
- Also compute **gas-weighted degree days (GWDD)** = HDD + `k × CDD` with `k ≈ 0.15–0.25` (calibrate against EIA weekly storage residuals later). Store `k` in config.
### 5.4 Ensemble spread
- Ensemble mean anomaly, standard deviation, and `P(anom < −3 °C)`, `P(anom > +3 °C)` per cell and per region.
- Regional degree-day distribution: p10 / p50 / p90 across members.
### 5.5 Run-over-run and model divergence
- `Δ_run = DD_15d(this run) − DD_15d(previous run, same model)`, per region.
- `Δ_model = DD_15d(ECMWF) − DD_15d(GFS)` at matched init times.
- Persist both; alert on thresholds (§7).
### 5.6 Freeze-off risk
- Per basin polygon: count of 6-hourly steps in the next 7 days with T2m < −5 °C (Permian, Haynesville, Anadarko, Eagle Ford), < −12 °C (Bakken, Appalachia, DJ — colder baselines, better winterisation).
- Areal fraction of basin below threshold at any step.
- Score = fraction × consecutive hours. Expose as 0–100.
### 5.7 Tropical exposure
For each active NHC advisory:
- Intersect the 5-day cone with (a) the Gulf offshore lease polygon and (b) a 100 km buffer around each LNG terminal.
- Output: list of assets in cone, earliest arrival day, summed `capacity_bcfd` at risk, and the NHC wind-radii probability where available.
- Also intersect with the Henry Hub 150 km buffer and the Haynesville polygon (onshore production and pipeline risk).
### 5.8 Wind (gas-for-power)
- Daily mean 10 m wind speed averaged over ERCOT, SPP footprints and a North Sea box (52–60°N, 0–8°E).
- Anomaly vs a simple 30-day trailing mean in v1 (climatology later).
- Low-wind flag: regional daily mean < 4 m/s.
---
## 6. Rendering
Produce Tropical-Tidbits-equivalent PNGs in the Kardamow exhibit style. Every image carries: model, init time, valid time/day, climatology label, "Kardamow" mark, and a colour bar.
### 6.1 Maps (`render/maps.py`)
| Product | Domains | Frames | Notes |
|---|---|---|---|
| `t2m_anom` | us, eu | daily, days 1–15 | Diverging palette, ±16 °C, white at 0. Replace the TT rainbow with a navy-to-white-to-red ramp so it sits with your other exhibits. |
| `t2m_anom_ensmean` | us, eu | daily 1–15 | GEFS and ENS |
| `t2m_spread` | us, eu | days 3, 5, 7, 10, 15 | Sequential light-blue → navy |
| `wind10m` | us, eu | daily 1–7 | With ERCOT/SPP/North Sea outlines |
| `freeze_hours` | us | single, 7-day | Basin polygons filled by score |
| `tropical_exposure` | gulf | per advisory | NHC cone + asset points sized by capacity |
Cartopy: `PlateCarree`, Lambert Conformal for the US domain if aesthetics matter. 1600×1000 px, 150 dpi. Overlay layers: state/country borders, basin polygons (thin), LNG points, Henry Hub.
Also produce a 15-frame animated GIF/WebP per product per run for the dashboard loop.
### 6.2 Charts (`render/charts.py`)
- Degree-day strip: bars of daily HDD/CDD vs normal for days 1–15, current run vs previous run overlaid (light blue vs navy).
- Model fan: cumulative GWDD by lead day, GFS, ECMWF, GEFS p10–p90 band, ENS p10–p90 band.
- Run history: 15-day cumulative GWDD as of each init over the last 10 days — the "how has the forecast trended" chart desks look at first.
### 6.3 Phase-1 UI (Grafana)
- Image panels pointing at object-storage URLs for the latest frame.
- Time-series panels reading Postgres for degree days, deltas, freeze score, wind.
- Table panel for active alerts.
### 6.4 Phase-2 UI (Leaflet)
Export anomaly fields as Cloud-Optimised GeoTIFF or PNG tiles (georeferenced) and load as an `ImageOverlay`/tile layer with the asset GeoJSON on top. Keep the rendering module's colour map identical so map and PNG match.
---
## 7. Alerts (`alerts/rules.yaml`)
Each rule: `id`, `metric`, `region`, `operator`, `threshold`, `severity`, `cooldown_hours`, `message_template`. Initial set:
| id | Condition | Severity |
|---|---|---|
| `dd_run_delta_l48` | |Δ_run GWDD 15d, L48| ≥ 15 | medium; ≥ 30 high |
| `dd_run_delta_eu5` | |Δ_run| ≥ 12 | medium |
| `model_divergence` | |Δ_model 15d| ≥ 25 | medium (implies uncertainty; note which model is warmer) |
| `model_convergence` | previous |Δ_model| ≥ 25 and now ≤ 8 | info ("move likely priced") |
| `cold_anomaly_prob` | ENS P(anom < −3 °C) ≥ 0.6 over ≥ 40 % of Midwest+Northeast for any day in 6–15 | high |
| `heat_anomaly_prob` | P(anom > +3 °C) ≥ 0.6 over ≥ 40 % of South Central+ERCOT, days 3–10 | medium |
| `freeze_off` | basin score ≥ 40 within 7 days | high (Permian/Haynesville), medium (others) |
| `tropical_gulf` | NHC cone intersects offshore lease polygon | high |
| `tropical_lng` | cone within 100 km of any terminal | high; message lists terminals and Bcf/d |
| `low_wind_ercot` | ERCOT daily mean wind < 4 m/s for ≥ 3 consecutive days with CDD above normal | medium |
| `low_wind_northsea` | North Sea box < 5 m/s for ≥ 3 days in heating season | medium |
Dispatch: insert into `alerts` table; POST JSON to the orchestrator webhook (`config.orchestrator_url`). Include the PNG URL and the numbers that fired the rule. Respect `cooldown_hours` per rule+region.
---
## 8. Schema (`store/schema.sql`)
```sql
model_runs(id, model, init_time, ingested_at, status, n_members)
region_daily(run_id, region, valid_day, t2m_mean_c, anom_c, hdd, cdd, gwdd,
             hdd_normal, cdd_normal, p10_gwdd, p50_gwdd, p90_gwdd)
region_windows(run_id, region, window, gwdd, gwdd_normal, delta_prev_run, delta_vs_gfs)
freeze_risk(run_id, basin, hours_below, areal_fraction, score)
wind_daily(run_id, region, valid_day, wind_ms, anom_ms, low_wind_flag)
tropical_exposure(advisory_id, storm, issued_at, asset, distance_km, in_cone, earliest_day, capacity_bcfd)
alerts(id, rule_id, region, fired_at, severity, value, threshold, message, image_url, run_id)
images(run_id, product, domain, frame, url, created_at)
```
Index `region_daily` on `(region, valid_day, run_id)`; `region_windows` on `(region, window, run_id)`.
---
## 9. Scheduling
| Job | When (UTC) | Notes |
|---|---|---|
| GFS 00z/12z | 03:45, 15:45 | data complete ~3.5 h after init |
| GFS 06z/18z | 09:45, 21:45 | lower priority; can skip in v1 |
| GEFS 00z/12z | 05:00, 17:00 | |
| ECMWF IFS/AIFS 00z/12z | 08:00, 20:00 | open data lag ~6–7 h |
| ECMWF ENS 00z/12z | 09:00, 21:00 | |
| NHC | every 30 min | cheap; only runs exposure when a new advisory appears |
| CPC degree days | daily 21:00 | validation |
Each job is idempotent on `(model, init_time)`; a re-run overwrites.
---
## 10. Phases
**Phase 1 — 1 week (weekend + evenings):**
GFS ingest → anomaly → US/EU `t2m_anom` PNGs → L48 and EU-5 degree days → Postgres → Grafana image + time-series panels. Climatology built once from ERA5.
**Phase 2 — week 2:**
ECMWF IFS, GEFS, ENS; spread maps; run-over-run and model-divergence tables; degree-day strip and model fan charts; first alert rules (`dd_run_delta`, `model_divergence`, `cold/heat_anomaly_prob`).
**Phase 3 — week 3:**
NHC ingest, asset GeoJSON, exposure computation and map, `tropical_*` alerts; freeze-off score; wind fields; webhook to the orchestrator.
**Phase 4 — later:**
CFSv2 / ECMWF extended weeks 3–4; GWDD `k` calibration against EIA storage residuals; Leaflet tiles; solar for EU; a `weather` sub-agent that reads the alerts table and drafts a one-liner in the Kardamow register.
---
## 11. Acceptance criteria
- A GFS 00z run produces 15 US and 15 EU anomaly PNGs and a populated `region_daily` within 20 minutes of data availability, on Railway, unattended, for 5 consecutive days.
- L48 population-weighted HDD for days 1–7 is within ±10 % of CPC's published forecast for the same period on 4 of 5 days checked.
- Δ_run and Δ_model computed and charted for every matched run.
- A synthetic NHC cone placed over Sabine Pass fires `tropical_lng` with the correct terminal list and Bcf/d sum.
- Every image carries model, init, valid, climatology and source attribution.
---
## 12. Open decisions
1. Climatology baseline: 1991–2020 ERA5 (recommended) or 1981–2010 CFSR (matches TT). Decide before Phase 1.
2. Grid-level population weights vs CPC state weights. Start with CPC state weights (simpler, validated), move to gridded later.
3. GWDD `k` initial value: 0.2.
4. Object storage: Railway volume (simplest) vs Cloudflare R2 (cheaper egress if images are ever public on Kardamow).
5. Whether 06z/18z GFS runs are worth the compute in v1. Suggest no.
---
## 13. Attribution
Models: NOAA/NCEP (GFS, GEFS, CFSv2), ECMWF (IFS, AIFS, ENS, open data licence CC-BY-4.0), Copernicus/ECMWF (ERA5), NOAA NHC, NOAA CPC. Print on every exhibit. Do not fetch or republish Tropical Tidbits imagery.
