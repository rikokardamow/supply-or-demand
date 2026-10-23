# pipelines/gridstatus_iso — notes

## Dependency pin — gridstatus==0.34.0, not the latest
`gridstatus>=0.35.0` hard-requires `plotly~=6.0`, which conflicts with this project's own
pinned `plotly>=5.22,<6.0` (every existing chart across every spec). A plain
`pip install gridstatus` pulled 0.36.0 and silently downgraded `pandas` 3.0.5→2.3.3 and
upgraded `plotly` 5.24.1→6.9.0 project-wide — confirmed live, caught via `pip check` showing
a real conflict, not assumed. `0.34.0` is the newest release with `plotly>=5.11.0`/
`pandas>=2.2.1` (no upper bounds), confirmed by checking each version's PyPI metadata
directly (`0.35.0` introduced the `~=6.0`/`~=2.2` pins; `0.34.0` and earlier don't have them).
Pinned exactly (`==0.34.0`, not a range) in `pyproject.toml` so a future bare install can't
silently regress this. `gridstatus.*` added to `pyproject.toml`'s mypy
`ignore_missing_imports` overrides (no type stubs exist).

**If `uv` isn't on PATH** (confirmed true for this project's shell this session), use
`.venv/Scripts/python.exe -m pip install "gridstatus==0.34.0"` directly rather than a bare
`pip install gridstatus` — the latter re-triggers the exact conflict above.

## ERCOT is blocked — confirmed live, not a code bug
Every `www.ercot.com` endpoint gridstatus's `Ercot` class hits (`get_load`, `get_fuel_mix`,
`get_lmp`) returns a `403` from **Incapsula/Imperva bot-protection** — a JS-challenge page,
not a simple auth wall, confirmed by inspecting the response body (`_Incapsula_Resource`
iframe, `visid_incap_*` cookie). No `User-Agent` header change fixes this. This may be
specific to this sandboxed environment's outbound IP rather than a universal block — worth
re-testing from a different network before concluding ERCOT is permanently unreachable this
way. ERCOT is out of scope for this pipeline until/unless that's resolved.

## PJM needs a free API key I can't currently get
`gridstatus.PJM(api_key=...)` requires a Data Miner 2 key from pjm.com, which needs network
membership I don't have. Out of scope for this pipeline — revisit only if that
changes.

## MISO was tried and dropped — its real-time load/fuel-mix has no genuine history
Confirmed live, in this order:
1. `MISO.get_load(date=day)`/`get_fuel_mix(date=day)` only accept a **single day**, not a
   range (`TypeError: unexpected keyword argument 'end'` for `get_load`).
2. Looping single days: `get_load` raises `gridstatus.base.NotSupported` for anything but
   "today"/"latest" (not even yesterday); `get_fuel_mix` supports "today" and "yesterday"
   only. Both source from MISO's live `RealTimeTotalLoad`/`FuelMix` cache APIs, which simply
   don't retain history.
3. `get_historical_zonal_load_hourly(year)` exists as a genuine historical path, but it
   downloads **one cumulative file per year, published only at year-end**
   (`{year}12_dfal_HIST_xls.zip`) — for the current, still-in-progress year this 404s
   (`NoDataFoundException`), so it can't serve a "trailing 60 days" window for "this year."
4. gridstatus's `MISO` class has **no historical fuel-mix method at all** (checked: no
   `get_*` method beyond the today/yesterday-limited `get_fuel_mix`).

MISO's `get_lmp` **does** support a real 60-day range, but only via `market="DAY_AHEAD_HOURLY"`
— `market="REAL_TIME_5_MIN"` raises `"Only today, yesterday, and latest are supported for
5 min LMPs"` (confirmed live). Since load and fuel-mix can't be pulled at all for a 60-day
window, MISO was dropped entirely rather than shipping a lopsided ISO tab (LMP only, no mix
or load) — swapped for NYISO instead, which supports all three cleanly. If MISO ever gains a
real historical load/fuel-mix path in a future gridstatus release, it's a reasonable
candidate to add back.

## The two ISOs actually used: CAISO and NYISO
Both confirmed live to support a genuine 60-day range for `get_load`, `get_fuel_mix`, and
`get_lmp` (CAISO via `market="REAL_TIME_5_MIN"`), with no credentials required.

**CAISO** fuel-mix columns (confirmed live): `Solar, Wind, Geothermal, Biomass, Biogas,
Small Hydro, Coal, Nuclear, Natural Gas, Large Hydro, Batteries, Imports, Other`.
Trading hubs for LMP — the 3 well-known generic aggregate points, not the thousands of
individual pricing nodes (`locations="ALL"` would return every node — the spec's own
"keep pulls to hub/zone level" caution): `TH_NP15_GEN-APND`, `TH_SP15_GEN-APND`,
`TH_ZP26_GEN-APND` (NP15/SP15/ZP26). CAISO's LMP pull is the slow part of a 60-day run
(~80-90s per ~30-day chunk against its OASIS endpoint) — budget for it, don't assume a hang.

**NYISO** fuel-mix columns (confirmed live): `Dual Fuel, Hydro, Natural Gas, Nuclear,
Other Fossil Fuels, Other Renewables, Wind`. `get_load` conveniently returns a system-wide
`Load` column **plus every zone's own load** in one call — only the system-wide column is
used here. LMP "hub/zone" level is NYISO's own real load zones (already zone-level, not
thousands of nodes, confirmed via `locations="ALL"` returning only 15 total: 11 real zones
plus `H Q`/`NPX`/`O H`/`PJM` external interface ties, which are excluded from
`hubs.py::NYISO_ZONES`).

## Both ISOs' fuel-mix naming is genuinely different — no shared PSR-type scheme
Unlike ENTSO-E's fixed PSR-type vocabulary, CAISO and NYISO each use their own fuel-category
names with no overlap beyond a few common ones (`Wind`, `Solar`, `Nuclear`, `Natural Gas`).
`apps/dashboard/pages/05_us_gas_power.py`'s `_ISO_FUEL_ORDER` hardcodes each ISO's real
column names (confirmed live) rather than assuming a shared taxonomy — reusing
`core.theme.generation_mix_chart`/`PSR_COLOURS` (extended with these new names) rather than
building a second chart primitive.

## Timestamps
CAISO returns tz-aware `US/Pacific` (a real IANA zone, DST-aware); NYISO returns
`US/Eastern`. Both converted to naive UTC (`.tz_convert("UTC").tz_localize(None)`) before
downsampling, matching every other pipeline's `ts_long` convention.

## Downsampling to hourly
Per the spec's own data model note (`freq '5T'/'H' downsampled to hourly for the lake`),
`GridstatusISOClient._downsample_hourly` mean-resamples every raw 5-minute series (load,
fuel mix, LMP) to hourly after converting to naive UTC. Works uniformly for a single-column
(load) or multi-column (fuel mix, LMP pivoted wide by hub) frame since `.resample("h").mean()`
averages each column independently.

## Series id / geo convention
- Load: `series_id` = the raw EIA-style route code isn't applicable here (gridstatus has no
  such codes) — uses `gridstatus.{ISO}.load`, `geo={ISO}`.
- Fuel mix: `gridstatus.{ISO}.fuel_mix.{slug(fuel)}`, `geo={ISO}`.
- LMP: `gridstatus.{ISO}.lmp.{slug(hub)}`, `geo={ISO}.{hub}` — matches the spec's own
  literal `geo='ERCOT.HB_HUBAVG'`-style example for LMP specifically (load/fuel-mix stay
  ISO-only geo, since they're whole-system aggregates, not per-node).

## vcrpy gotcha: CAISO's cache-busting query param breaks cassette replay
CAISO's request URLs include a `_=<unix-ms-timestamp>` query parameter (a cache-buster,
confirmed live) that changes on every call — vcrpy's default query-string matching then
fails to replay a previously-recorded cassette (`_` differs between record and replay).
Added `"_"` to `tests/conftest.py`'s shared `vcr_config`'s `filter_query_parameters` (same
mechanism as EIA's `api_key`/ENTSO-E's `securityToken` — vcrpy strips the same param from
both the stored cassette and the live outgoing request before matching, so it isn't really
about secrecy here, just neutralising a volatile value). Every cassette recorded before this
fix had to be deleted and re-recorded.

## Verified (Session B)
60-day pull: CAISO 1,440 load rows / 18,720 fuel-mix rows / 4,320 LMP rows (all exact:
60×24, 60×24×13 fuels, 60×24×3 hubs). NYISO ~1,450 load / ~10,150 fuel-mix / ~15,950 LMP rows
(60×24×7 fuels, 60×24×11 zones, small variance from partial-day boundary effects). Page
`05_us_gas_power.py`: a `CAISO`/`NYISO` tab pair, each with a fuel-mix stack
(`core.theme.generation_mix_chart`), a load-vs-net-load dual-axis chart
(`pipelines/gridstatus_iso/transforms.py::net_load`, mirrors
`pipelines/entsoe/transforms.py::residual_load`'s exact reasoning), and an hour×day LMP
heatmap (`core.theme.hour_day_heatmap`, new — same navy-to-red diverging colourscale as
`components/power_maps.py`'s price map) with a hub/zone selectbox.
