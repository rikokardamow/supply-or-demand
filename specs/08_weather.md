# Spec 08 — Weather Overlay (Open-Meteo + ECMWF Open Data)

**Weeks 12–13 · Est. 12–16 h (GRIB/cartopy learning curve) · Prereq: Spec 00.**

## Objective & alpha question
HDD/CDD drive gas/power demand; wind forecasts drive renewables supply and power prices; 2m-temp
anomaly maps front-run demand surprises. Question: *is upcoming weather bullish or bearish demand
vs normal, by region?*

## Data sources
1. **Open-Meteo** — free non-commercial, no key. Forecast + ERA5 archive endpoints:
   `api.open-meteo.com/v1/forecast` and `archive-api.open-meteo.com/v1/archive`
   (`daily=temperature_2m_mean,temperature_2m_min,temperature_2m_max,windspeed_10m_max`).
   City set (population-weight later): Dublin, London, Amsterdam, Frankfurt, Paris, Madrid, Milan,
   Warsaw, Vienna; US: NYC, Chicago, Houston, Atlanta, LA.
2. **ECMWF Open Data** — fully open (CC-BY-4.0) since 1 Oct 2025; `uv add ecmwf-opendata cfgrib xarray`
   plus `matplotlib cartopy`. `Client(source="ecmwf")` → IFS HRES GRIB2, param `2t`, steps out to
   ~240 h. Portal capped at 500 simultaneous connections; mirrors on AWS/Azure/GCP if slow.
3. **tomorrow.io** — optional free-tier point forecasts; skip unless time remains.

## Data model
- Daily city HDD/CDD + wind → `ts_long` (`hdd.dublin`, `cdd.houston.f65`, `geo`=city).
- Regional aggregates → `ts_long` (`hdd.eu.popw`).
- GRIB rasters stay as files in `data/raw/ecmwf/` + rendered PNG maps in `data/lake/maps/` (paths recorded in DuckDB table `map_assets`).

## Transformations
- **HDD = max(0, 18 °C − T_mean)`; `CDD = max(0, T_mean − 18 °C)`** (EU); **65 °F base for US series** — store both bases explicitly in the series_id.
- Population-weighted EU/US aggregates (weights CSV, hand-maintained).
- Forecast anomaly = forecast HDD − climatological HDD (ERA5 2010–2024 daily normals, computed once and cached).
- 2m-temp anomaly field = IFS forecast − ERA5 monthly climatology grid.

## Visualisation spec (page `08_weather.py`)
1. EU + US pop-weighted HDD: history (navy) + forecast (dashed) vs climatology (orange) with anomaly shading.
2. Dual-axis: EU HDD anomaly (navy) vs EU gas net-withdrawal from Spec 02 (light blue).
3. **Anomaly maps** (tropicaltidbits-style): cartopy Europe + CONUS 2m-temp anomaly at D+3/D+7,
   diverging blue-white-red, house fonts — rendered to PNG by the pipeline, displayed by the page.
4. Wind: forecast 10m wind index for DE/DK/IE vs ENTSO-E wind forecast (Spec 04 cross-check).

## Claude Code sessions

### Session A (weekend, 3 h) — Open-Meteo HDD/CDD
> Read CLAUDE.md, specs/08_weather.md. Scaffold `pipelines/weather/`: Open-Meteo client
> (archive + forecast), city list + weights CSV, HDD/CDD in both bases with hand-checked tests
> (T_mean 12 °C → HDD 6; 20 °C → 0), pop-weighted aggregates, climatology builder (cached Parquet).
> Page 08 with visuals 1–2. Acceptance: Dublin HDD for a known cold day matches manual calc.

### Session B (weekend, 3–4 h) — ECMWF maps
> Add `ecmwf-opendata` retrieval of IFS 2t at steps 72/168 → xarray; anomaly vs cached ERA5
> climatology grid (fetch climatology via Open-Meteo archive gridded sampling or ERA5 monthly
> means — choose the simplest that works); render cartopy anomaly PNGs (EU + CONUS) into
> data/lake/maps with a manifest row. Display on page 08 with a step selector. Timebox: if cartopy
> fights, ship matplotlib pcolormesh without coastlines first and iterate.

### Session C (weekday, 1 h) — wind + entrypoint
> Wind index for DE/DK/IE; `pull_daily.py` (forecast + map render); stale-map badge if >24 h old.

## Definition of Done
- HDD/CDD (both bases) for 14 cities + pop-weighted aggregates, forecast + history + climatology.
- ≥2 anomaly maps auto-rendering daily. Dual-axis weather-vs-gas chart live. Tests green.

## Stretch
- Degree-day-driven gas-demand nowcast regression (HDD → LDC demand) with out-of-sample error shown honestly.
- Ensemble spread (ENS) fan chart for EU HDD.
