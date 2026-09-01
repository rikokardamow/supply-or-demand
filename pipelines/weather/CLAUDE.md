# pipelines/weather — Claude Code Guide

## Open-Meteo — no key, two endpoints, one shared response shape
`api.open-meteo.com/v1/forecast` (forecast, up to 16 days: `forecast_days=16` confirmed
live) and `archive-api.open-meteo.com/v1/archive` (ERA5-reanalysis history) return the
**identical** JSON shape per location: `{latitude, longitude, timezone, elevation,
daily_units: {...}, daily: {time: [...], <var>: [...]}}` — one parser (`client.py`'s
`_parse_daily_response`) handles both.

**The spec's own wind param name is stale**: it says `windspeed_10m_max`, the real live
param is `wind_speed_10m_max` (confirmed via a real request returning a clean 200 only
with the underscored name).

## Multi-city batching — confirmed live, a major simplification
Passing **comma-separated** `latitude`/`longitude` lists returns a JSON **array** of
per-location objects, in the same order as the input. One request covers every city in a
group instead of one request per city. Both endpoints support this identically.

## Rate limits — real, and *not* just per-minute
The free/no-key tier enforces both a per-minute quota (`"Minutely API request limit
exceeded"`) **and** a separate per-hour quota (`"Hourly API request limit exceeded"`),
confirmed live as two distinct error messages. A single large multi-year, multi-city
archive request (e.g. 2018-2026 × 9 cities) is "expensive" enough that issuing two such
requests back to back (EU group then US group) reliably trips the per-minute limit even
with a short exponential-backoff retry — `client.py`'s `_get` treats a 429 with a fixed
~65s wait (`RATE_LIMIT_WAIT_SECONDS`) rather than the short exponential backoff used for
5xx/network errors, and `pull_weather.py`/`climatology.py`'s own group loops add a
proactive `GROUP_PACING_SECONDS` (65s) sleep between groups rather than relying on
reactive retries alone. Hitting the *hourly* limit needs a genuine wait (not something a
retry loop should attempt) — this is why `climatology.py` avoids a second large archive
call entirely (see below).

## Climatology reuses the lake, doesn't re-fetch
An earlier version of `climatology.py` made its own separate 2010-2024 archive call per
city group. Confirmed live this reliably trips the rate limit on top of the call
`pull_weather.py`'s own history backfill already makes — two large archive pulls in the
same run is one too many. Fixed by having `build_climatology()` read the **already-
ingested lake data** (`core.storage.read_ts_long`, filtered to `source="open_meteo"` and
`series_id` starting `hdd.`/`cdd.`) and run **`core.seasonal.seasonal_stats`** on it — no
network call at all once the history backfill has run once. This also means the
climatology window is exactly `core.seasonal`'s own default years (2018-2026, 2020
excluded automatically by that function's default, never reimplemented per root
`CLAUDE.md` rule 4) rather than a separately-fetched, wider 2010-2024 range.

## History backfill vs. forecast — distinct series_id and source, on purpose
`pull_weather.py` writes two kinds of rows:
- **History** (`source="open_meteo"`): a full 2018-present backfill via the archive
  endpoint — needed because `core.seasonal.seasonal_stats`' own default `years=
  range(2018, 2026)` requires real multi-year data in the lake for `seasonal_range_chart`'s
  band to mean anything; a short trailing window wouldn't be enough.
- **Forecast** (`source="open_meteo_forecast"`, `series_id` suffixed `.forecast`): the next
  16 days. Suffixing the series_id (not just changing `source`) means a forecast row and a
  later real observation for the same day never collide under `write_ts_long`'s
  `(series_id, ts)` de-dup key even though they're also already in separate `source=`
  partitions — belt and braces, and it lets the page read history and forecast as two
  explicitly separate series (solid vs. dashed trace) rather than needing to guess which
  rows are "real" once both exist for the same date.

## Population weights — hand-maintained, single-source (`cities.csv`)
Same precedent as `pipelines/opec_momr/quotas.csv`: a small reference CSV living in the
pipeline's own directory. Weights are each city's share of its own region's (EU or US)
total population among the 14 listed cities — **not** a share of the whole EU/US
population — sourced from macrotrends.net's 2024 metro-area population figures (a single
consistent source across all 14 cities, chosen over mixing sources of differing "metro
area" definitions). EU weights sum to ~1.0, US weights sum to ~1.0, separately. Needs a
manual refresh if this list of cities ever changes — not automated.

## `base` doubles as region — a deliberate simplification
Every EU city uses base `c18` (18°C), every US city `f65` (65°F) — `aggregate.py` derives
region ("eu"/"us") directly from `base` rather than a separate region column, since the two
coincide exactly in this dataset. Revisit if a non-EU/US city on one of these bases is ever
added.

## US gas storage net-withdrawal is a derived diff, not a direct read
Unlike GIE's AGSI (`pipelines/gie/transforms.py::net_flow`, a direct injection-minus-
withdrawal read), EIA's weekly storage route (`pipelines/eia/pull_gas_storage.py`,
`NW2_EPG0_SWO_R48_BCF` for Lower-48) publishes only a working-gas **level**, no
injection/withdrawal split. `gas_proxy.py::net_withdrawal` derives it as `-level.diff()`
(storage falling = net withdrawing). Because it's a diff, it must be computed on the full
series *before* trimming to a display window — trimming first would leave the window's
first point `NaN` (no prior point to diff against).

## Page charts: joining a trailing weather window onto full-history "other" series
`08_weather.py`'s HDD/CDD-anomaly dual-axis charts only plot a trailing window (`_series_
by_ts(...).tail(90)` plus the 16-day forecast) — but the gas-storage/injection series
they're joined against have **years** of history in the lake. Confirmed live: without
trimming the other series to the same window, `dual_axis_chart`'s shared x-axis stretches
to the wider series' full range and the weather trace becomes an invisible sliver at the
chart's right edge. `_recent_cutoff()`/`_trim_recent()` fix this by trimming the gas series
to the same window as the weather anomaly before charting. The NYISO/CAISO load series
didn't need this fix — `pipelines/gridstatus_iso`'s own trailing-60-day window already
sits inside the weather anomaly's ~106-day span.

## Verified (Session A)
Real pull: 101,792 history+forecast rows across 64 series (2018-08-31 through 2026-09-15
for city-level + population-weighted EU/US HDD/CDD), climatology cache built from that same
data (11,680 rows across 32 series). Acceptance criterion met: Dublin's real 2024-01-01
to -05 temperatures (7.1, 9.0, 7.6, 6.2, 4.8°C, cross-checked against the recorded test
cassette) give manual HDD-base-18 values of 10.9, 9.0, 10.4, 11.8, 13.2 — matching the
lake's stored `hdd.dublin.c18` values (11, 9, 10, 12, 13) exactly within rounding. Page 08
verified live in-browser: all 5 sections render with real data, forecast dashed line and
climatology band both visible, no console errors beyond pre-existing/unrelated dev-server
noise.

## Session B — ECMWF anomaly maps

**ECMWF Open Data (`ecmwf-opendata`), no key, CC BY 4.0.** `Client(source="ecmwf")`
defaults to `model="ifs"`, `resol="0p25"`; `Client.retrieve(type="fc", step=[...],
param=["2t"], target=...)` downloads a real GRIB2 (confirmed live: ~1.3MB for a 2-step
global 2t field). **`Client.latest(**request)` returns just the run datetime without
downloading the field** — `ecmwf_client.fetch_2t_forecast` uses this for a cheap
cache-hit check (cache key is the real forecast run datetime, not "today", since a run
can lag the calendar date). ECMWF's own terms require the CC BY 4.0 attribution line
printed on every download — carried onto page 08 as a caption under each map.

**GRIB2 structure via `xarray`+`cfgrib`** (confirmed live, not assumed): variable `t2m`
(Kelvin), dims `(step, latitude, longitude)`, `latitude` 90→-90, **`longitude` already
in -180..180** (not 0..360 — no wraparound conversion needed against the EU/CONUS
bounding boxes). `step` is `timedelta64[ns]`; `valid_time` is a per-step coordinate.

**Climatology grid is a deliberate simplification, not the spec's literal ERA5/CDS
grid.** The spec text says "ERA5 2010-2024 monthly climatology grid" — that needs a
separate Copernicus CDS account/key not otherwise used by this project. Per the spec's
own "choose the simplest that works" allowance, `climatology_grid.py` instead computes a
coarse (3° spacing) EU/CONUS grid from a **3-year same-calendar-day normal**
(2022/2023/2024) via Open-Meteo's archive endpoint. Confirmed live: a single archive call
happily batches 100+ locations (126-point EU grid, 189-point CONUS grid tested) for one
day — but there is **no multi-year-single-day batch mode**, so one archive call per
reference year is unavoidable; this is why the window is kept to 3 years rather than a
wider 5+ year normal (keeps runtime/API load small, distinct from the multi-year
rate-limit issue in `climatology.py` above, which this deliberately avoids repeating).

**`map_assets` is a Parquet file, not a real DuckDB table.** The spec's Data Model section
names "DuckDB table `map_assets`" — no precedent for a *persisted* (non-in-memory) DuckDB
file exists anywhere in this codebase (`core.storage.warehouse()` only registers views
over Parquet globs). `anomaly_maps.py` writes `data/lake/maps/manifest.parquet` instead —
same manifest-row semantics, swappable for a real DuckDB file later without changing any
caller, without introducing a first-of-its-kind architectural pattern unilaterally this
session.

**Cartopy installs cleanly on Windows via plain `pip install cartopy`** (v0.25.0 confirmed
live) — modern wheels (shapely 2.1.2, pyproj 3.7.2) bundle their own GEOS/PROJ binaries,
no system install needed. Renders real coastlines/borders via Natural Earth shapefiles
(downloaded from `naturalearth.s3.amazonaws.com` on first use, cached after). No
matplotlib-only fallback was needed.

Verified: 4 real anomaly maps rendered (EU/CONUS × D+3/D+7) with real coastlines and a
real diverging anomaly pattern (e.g. a cold pocket over Scandinavia, warm pocket over
southern Spain/Balkans for EU D+3). Page 08's region/step selector confirmed live in a
browser: switching region (Europe↔CONUS) and step (D+3↔D+7) correctly swaps the
displayed map and its date/title, reading only from the manifest — no direct API calls
from the page.
