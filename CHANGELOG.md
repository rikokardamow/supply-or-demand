# Changelog

The build log, spec by spec. Moved out of `README.md` when the project was opened up:
it is a genuine record of what was verified live and what broke, but it is history
rather than orientation, and a newcomer needs the second thing first.

## Status

Live pages today: **US PADD** (crude/product stocks, refining, inter-PADD flows, WPSR
table), **US Oil Market Overview** (national balance supplementary charts), **EU Gas
Storage & LNG** (AGSI+/ALSI+ fill, injection vs. send-out, country deviation), **EU Gas
Flows** (ENTSOG corridor Sankey, directional map, time series, physical-vs-nomination gap),
**EU Power** (ENTSO-E day-ahead price map, cross-border flow map, generation mix, residual
load, net position). See `specs/00_INDEX.md` for the full roadmap (17 specs: gas storage,
gas flows, power markets, refinery cracks, weather, news, AIS vessels, flights, macro/FX,
orchestration, a cross-spec analytics layer, OFAC sanctions, a NewsAPI supplement, and an
Adanos sentiment overlay).

### Build log

Every finished session is checked off in its spec's Definition of Done
(`specs/0N_*.md`) with the verification actually performed — this section is the
higher-level summary, kept current after each spec closes.

#### v0.1 — Spec 00: project setup
Core library (`core/settings.py`, `schemas.py`, `storage.py`, `seasonal.py`, `theme.py`,
`calendars.py`) — the DuckDB + Parquet lake, the `ts_long`/`flows` schemas, exclude-2020
seasonal maths, and the Kardamow house chart template. Dashboard shell, release calendars,
`/new-pipeline` and `/new-page` scaffolding commands, GitHub Actions CI (ruff + mypy +
pytest, cassette-only). [PR #1](https://github.com/rikokardamow/energy-dashboard/pull/1),
[PR #2](https://github.com/rikokardamow/energy-dashboard/pull/2).

#### v0.2 — Spec 01: EIA PADD & WPSR
`pipelines/eia/` — weekly stocks/utilisation/product-supplied/imports pull (`pull_wpsr.py`),
inter-PADD crude movement corridors discovered live from the API's own series names
(`corridors.py`), days-of-cover and net-balance transforms. Page `01_us_padd.py`: four tabs
(Stocks, Refining, Flows, WPSR) — the Flows tab renders a US map with directional
pipeline/tanker/rail arrows sized by monthly volume (`components/padd_map.py`). Added a
supplementary page, `015_us_oil_overview.py`, with the 8 national-balance charts from a
reference chart pack that weren't already covered by page 01 (production, exports, SPR,
crack spreads, seasonal refinery demand/stocks, etc.). Cross-checked against the live EIA
API directly. [PR #3](https://github.com/rikokardamow/energy-dashboard/pull/3),
[PR #4](https://github.com/rikokardamow/energy-dashboard/pull/4).

#### v0.3 — Spec 02: GIE gas storage (AGSI+/ALSI+)
`pipelines/gie/` — authenticated client (`x-key` header, 60s cool-off backoff), EU +
19-country AGSI+ fill/injection/withdrawal history and EU + 13 LNG-terminal-country ALSI+
send-out history, both back to 2018. Daily incremental puller (`pull_daily.py`) re-pulls a
trailing 5-day window and de-dups by `revision_date` for idempotent re-runs (verified: two
consecutive runs produced zero duplicate rows). Page `02_gas_storage.py`: EU headline
fill-% seasonal worm with a days-to-full annotation, six-country small-multiples grid
(originally scoped to Germany only — widened to the top 5 biggest movers plus Poland after
a mid-session request), dual-axis net injection vs. ALSI send-out, and a ranked
country-deviation bar chart. Cross-checked EU and per-country fill % against GIE's own API
directly. [PR #5](https://github.com/rikokardamow/energy-dashboard/pull/5).

**Redesign**: the headline section was rebuilt around a country selector (EU + the 6
small-multiples countries) driving three AGSI-style panels — a Current/M-1/Y-1 fullness
bar comparison (`core.theme.fullness_comparison_bars`) and two seasonal charts with
explicit Min/Max/Median lines instead of a shaded band (`core.theme.seasonal_minmaxmean_chart`,
new), for both fill % and net daily injection/withdrawal. Kept the median-based house
seasonal maths (`core.seasonal`) rather than switching to a mean just to match the
reference's label. The small-multiples grid, dual-axis net-injection-vs-send-out chart,
and country-deviation bar chart are unchanged. Verified live, including switching the
selector between EU and individual countries.

#### v0.4 — Spec 03: ENTSOG EU gas flows
Session A merged: `pipelines/entsog/` — no-auth client against ENTSOG's Transparency
Platform (`limit=-1` pulls a full page in one call for both the point directory and
operational-data endpoints) and a Parquet-cached point directory.
[PR #6](https://github.com/rikokardamow/energy-dashboard/pull/6).

Session B done: `corridors.py` now maps **8 corridors** (Norwegian export points, TAP,
TurkStream, 3 interconnectors, RU→UA transit, and 8 LNG terminals across 6 countries) —
past the ≥8 minimum. `pull_flows.py` (supersedes Session A's `pull_no_exports.py`) pulled 2
years of daily physical flows (13,581 rows) and nominations (13,489 rows) for all 21 mapped
points. `transforms.py::corridor_aggregate` sums point-level rows into corridor-day totals.
Page `03_eu_gas_flows.py`: a Sankey (raw point-level flows, latest 7-day average) and
corridor small-multiples (`core.theme.current_vs_prior_year_chart`, new — ENTSOG only has
~2 years of history, not enough for the 5-year seasonal band `seasonal_range_chart` needs).
Norwegian export total cross-checked against an independent live API call (exact match:
2,535.03 GWh/d for 2026-08-28). Sankey-vs-time-series reconciliation verified exactly
(0.0 GWh/d difference across all 8 corridors) and covered by a regression test.

Two real gotchas fixed along the way: **timestamps** — `periodFrom`'s fixed local
gas-day time carries a UTC offset that shifts across DST, breaking `pd.to_datetime` over a
2-year range (fixed by taking the date substring, not resolving the timezone); **multiple
operators per point** — `ITP-00304` (VIP Pirineos) and `ITP-00008` (TAP)'s nominations are
reported by both sides of the border with different real values, silently doubling those
corridors' rows until pinned to the receiving-side operator via ENTSOG's `operatorKey`
filter. Full detail in `pipelines/entsog/NOTES.md`.

Session C done: `components/entsog_map.py` — a directional `Scattergeo` map of Europe
reusing `padd_map.py`'s line+rotated-triangle-arrow technique (now factored into a shared
`components/geo_utils.py` so neither map duplicates it), and Session B's "latest complete
7-day average" window logic, so the map and the Sankey always agree on which week they're
showing. Verified live: arrows render across every corridor (Norway into Germany, Belgium,
France and Great Britain; Turkey's coast into Bulgaria; France into Spain; LNG terminals as
sized markers across the Netherlands, Belgium, France, Spain, Poland, Italy and Portugal),
hover text correct, no exceptions.

Session D done: the physical-vs-nomination gap chart (`transforms.py::physical_vs_nomination_gap`
— nomination minus physical, per corridor per day; positive means under-delivery) and the
15-day revision window. `flows` has no `revision_date` column for `ts_long`-style
revision-aware de-dup, so a revised value for an already-stored day would otherwise sit
alongside the stale one rather than replacing it — fixed with a new `replace_window` param
on `core.storage.write_flows` that drops the affected window's existing rows before writing
the fresh ones. `pull_daily.py` re-pulls the trailing 15 gas-days on every run using this;
verified idempotent by running it twice in a row (26,815 rows both times). Spec 03 is now
fully done — [PR #7](https://github.com/rikokardamow/energy-dashboard/pull/7).

**Fix while writing the previous entry**: adding ENTSOG rows to the shared `flows` table
(rows use `from_node="NO"` etc.) broke the PADD page's Flows-tab map, which read the whole
table without filtering to its own `source="eia"` rows. Fixed by adding a `source` filter
parameter to `core.storage.read_flows()` itself, so every caller gets it for free — the same
bug had independently broken a second chart (the Flows tab's net-balance bar) too.

#### In progress — Spec 04: ENTSO-E European power (+ EirGrid)
Session A: `pipelines/entsoe/` wraps `entsoe-py`'s `EntsoePandasClient` (added as a new
dependency, approved — pulls in `beautifulsoup4` transitively) rather than a raw REST client
like `pipelines/entsog`'s, because the Transparency Platform is genuinely flaky — the
identical query returned `200` once and `503` minutes later during live testing.
`entsoe-py`'s own retry only covers connection-level errors, not HTTP status codes, so
`ENTSOEClient` adds its own 503/5xx backoff on top. Pulled 90 days of day-ahead prices for
DE_LU, FR, NL, IE_SEM into `ts_long` (28,060 rows) — resolution is genuinely per-zone, not
fixed (DE_LU/FR/NL are 15-minute, IE_SEM is hourly), confirmed live and read from each
response rather than assumed. Cross-checked yesterday's DE_LU price against an independent
fresh API call: exact match across all 89 points that day.

**Credential incident**: while live-testing the confirmed 503 flakiness during planning
(before any code existed), printed a raw `requests.HTTPError` to see what went wrong — its
default string representation embeds the full request URL, including ENTSO-E's
`securityToken` query-param auth, leaking the real API key into this transcript. Disclosed
immediately; the user was asked to rotate the key. `ENTSOEClient` now converts every HTTP
error to a bare status-code message before it can propagate — see
`pipelines/entsoe/NOTES.md` for the full rule.

Session B: extended price coverage to all **13 zones** (12 with real day-ahead prices; GB
has a confirmed, genuine data gap — no prices, load, generation, or wind/solar forecast via
ENTSO-E, matching the spec's own "GB (as available)" caveat, most likely a post-Brexit
reporting change, not a bug). Pulled generation mix, load, and wind/solar forecast for all
13 zones (14-day lookback — generation/wind-solar are per-PSR-type, so row counts multiply
fast across 13 zones) and cross-border physical flows for 12 real interconnector pairs (11
with data; `SE_4<->DK_1` is empty in both directions, confirmed live, not chased further
given 11 borders already clears the spec's ≥8 minimum). Page `04_eu_power.py`: a day-ahead
price map (diverging navy-to-red `Scattergeo`), a cross-border arrow map (same
line+triangle technique as `padd_map.py`/`entsog_map.py`), a selectable-zone generation-mix
stacked area (`core.theme.generation_mix_chart`, new — a documented PSR-type colour
exception to the house palette per the spec's own "renewables greens/blues, thermal
greys/navy" instruction), residual load, and a ranked net-position bar. Cross-checked a
DE_LU→FR flow value against an independent fresh API call: exact match across all 88
points that day.

Every pull script (`pull_prices.py`, `pull_actuals.py`, `pull_flows.py`) now catches a
failure **per zone/border/indicator individually** and continues rather than aborting the
whole run — the Transparency Platform's flakiness turned out to be sustained enough that a
13-item pull routinely has 1-3 items fail on any given run (a different random subset each
time, confirmed by re-running twice), so re-running to pick up whatever failed is the normal
workflow here, not an edge case. Also found and fixed a second entsoe-py gotcha:
`EntsoePandasClient` defaults to no request timeout at all (confirmed by reading
`EntsoeRawClient`'s source), which hung a pull indefinitely until killed by hand — fixed by
passing an explicit 45s timeout and retrying on connection-level errors too, not just HTTP
status codes.

Session C: `pipelines/eirgrid/` — a single-adapter-function client (`EirGridClient._fetch_rows`)
against EirGrid's public, undocumented, no-key JSON API, pulling 90 days of ROI demand,
generation, wind, CO2 intensity, and interconnector flows at 15-min resolution (60,487 rows
across 7 series). Found a genuine, confirmed ~30-day max range per call (not flakiness —
30 days succeeds, 45+ returns a real error body) — `get_series` now chunks transparently
into 30-day windows and dedupes the resulting boundary overlap. Two corrections to the
spec's own text, both confirmed live: there's no solar-specific area (so the SNSP proxy
formula omits the solar term entirely), and ROI's real interconnectors are **EWIC and
Greenlink**, not "EWIC/Celtic/Moyle" (Celtic isn't in this API; Moyle serves Northern
Ireland, a different region). Also confirmed live: timestamps are Ireland local time, not
UTC; future timestamps within a requested window return `Value: null`; and
`INTER_NET_ROI == INTER_EWIC + INTER_GRNLK` exactly, with positive meaning import into ROI.
Added the Ireland panel to `04_eu_power.py` — demand-vs-wind dual-axis chart, an SNSP proxy
gauge (`core.theme.gauge_chart`, new), and an EWIC/Greenlink flow chart. Acceptance
criterion met: the lake's latest ROI demand values matched a fresh, independent API call
exactly, zero diff.

Session D (final for this spec): `pull_daily.py` — day-ahead prices for a `[yesterday,
tomorrow+1)` window (ENTSO-E publishes ~12:45 CET) plus actuals (load, generation,
wind/solar forecast, cross-border flows) for the prior day only. `pull_prices.py`/
`pull_actuals.py`/`pull_flows.py` each now expose a reusable `pull_*()` helper so the daily
entrypoint shares their per-item resilience instead of duplicating it. Running it twice in a
row surfaced a genuine data-loss bug, not just a flaky-API annoyance: `write_flows`'s
`replace_window` was dropping every existing row in the re-pulled window regardless of which
border it belonged to, so a border that failed on one run (a routine occurrence — ENTSO-E's
confirmed flakiness) had its still-good prior data deleted with nothing to replace it.
Confirmed live: `DE_LU -> NL` had real data after run 1, then zero rows after run 2 once that
border's fetch failed. Fixed at the storage layer (`core.storage._write_partitioned`) to
scope the window deletion to only the pairs present in the fresh pull; added a regression
test. A third run confirmed the fix — `DE_LU -> NL` was cleanly restored and no other border
was lost. This also closes an identical latent risk in `pipelines/entsog`'s own daily
re-pull. Spec 04 is now feature-complete: page 04 (price map, arrow map, mix stack, Ireland
panel), 13 zones priced (12 with real data, GB's gap confirmed and expected), 12 borders
mapped (11 with real data), EirGrid adapter isolated in one function, all cross-checks done,
tests green.

#### In progress — Spec 05: US natural gas & power (EIA + gridstatus)
Session A: pulled weekly Lower-48 + regional natural gas working storage (8 series, 6,952
rows) via the existing `EIAClient`, confirmed live via `list_series()` — the spec only names
the Lower-48 code, the 7 regional codes (East, Midwest, Mountain, Pacific, South Central
aggregate + Salt + Nonsalt) were discovered, not guessed. Cross-checked live: Salt (248 BCF)
+ Nonsalt (813 BCF) = South Central aggregate (1061 BCF) exactly. Found a real client
gotcha: this route's `area-name` field is the literal string `"NA"` for every row regardless
of region (not a genuine missing-value case) — `EIAClient.get_series` gained an optional
`geo_map` parameter so a pull script can override `geo` per series_id when `area-name` isn't
usable, leaving every other route's existing area-name-based behaviour untouched. Page 05:
L48 headline worm chart + 7-region small multiples, reusing the exact
`seasonal_stats`/`seasonal_range_chart` pattern already built for `01_us_padd.py`/
`02_gas_storage.py`. Acceptance criterion met: the lake's latest L48 value (3,184 BCF,
2026-08-21) matched a fresh, independent API call exactly.

Session B: added `pipelines/gridstatus_iso/` for ISO real-time load, fuel mix, and
hub/zone-level LMP. The spec's own ERCOT+PJM pairing didn't survive contact with reality:
ERCOT's website is behind Incapsula bot-protection (every endpoint gridstatus needs returns
403), and PJM needs a free Data Miner 2 API key the user can't obtain (network membership
required). MISO was tried next but dropped too — its real-time load/fuel-mix API only
serves "today" for the current year, with no genuine historical path via gridstatus.
Landed on **CAISO + NYISO**, both confirmed to support a real 60-day range for all three
data types with no credentials needed. Also caught and fixed a real dependency conflict:
`gridstatus`'s latest release (0.36.0) hard-requires `plotly~=6.0`, clashing with this
project's `plotly<6.0` pin used by every existing chart — pinned `gridstatus==0.34.0`
instead (the newest release before that pin was introduced). Page 05 gained ISO tabs: a
fuel-mix stack, load-vs-net-load, and an hour×day LMP heatmap (`core.theme.hour_day_heatmap`,
new) per ISO. Verified live: CAISO load cross-checked against an independent fresh pull,
exact match.

Session C (final for this spec): monthly US dry natural gas production + LNG exports into
`ts_long`, dual-axis chart on page 05. Another spec-text correction, confirmed live: the
spec's named `natural-gas/move/poe2` route has no usable national LNG export total — its
per-destination-country series (17 of them) summed to only ~88,544 MMcf for the latest
month, a small fraction of reality. `natural-gas/sum/lsum` has the genuine pre-aggregated
total instead, cross-checked live (pipeline exports + LNG exports == that route's own
combined total, exact to EIA's own rounding) — ~502,812 MMcf/month (≈16.8 Bcf/d), a
plausible real figure. Feedgas confirmed to have no distinct EIA series at all across every
route checked — documented as out of scope rather than faked, with a caption on the page.
Both this session's and Session A's pull scripts are cheap full-history re-pulls (nowhere
near ENTSO-E/EirGrid's scale), so they already serve directly as Spec 13's weekly-storage/
monthly-production entrypoints — verified idempotent live (identical row counts across two
consecutive runs each). Spec 05 is now feature-complete: page 05 (storage worm + regionals,
production-vs-exports, 2 ISO tabs with 3 visuals each), feedgas documented as unavailable,
tests green.

#### In progress — Spec 06: OPEC / global supply monitoring (MOMR + JODI + Baker Hughes)
Session A: `pipelines/opec_momr/` downloads and parses OPEC's MOMR Excel appendix
(`opec.org/assets/assetdb/momr-appendix-{month}-{year}.xlsx`, confirmed live, no key). Per
explicit direction, captures **every labelled row across all 5 data sheets** (400+ series
from one issue) rather than a curated subset — full regional/country breakdowns for demand,
non-DoC production, OECD stocks, oil-on-water, and rig counts, all available for future
charts without a second pass. Found none of the 5 sheets is a long monthly history — each is
a snapshot/outlook table (a handful of years + trailing quarters + occasionally one or two
actual months) — which is exactly why `revision_date` = the MOMR's own publication month
matters; real history only builds up by pulling every month. Found Table 11-2 already *is*
OPEC's own precomputed revision-vs-last-month table, simplifying the spec's planned
waterfall transform considerably. Caught and fixed two real parsing bugs during development:
annual headers are real ints not strings, and the header row itself was being misread as a
data row before a fix. Also caught a genuine cross-vintage collision — an annual column and
a quarterly column both map to the same representative date, which silently collided under
`ts_long`'s de-dup key until every series_id was suffixed with its own granularity. New
precedents for this project: caching a raw downloaded file (not parsed data) under
`data/raw/opec/`, and a `tests/fixtures/` fixture-test convention (the real ~145 KB workbook
checked in directly). Confirmed gap matching the spec's own two-session split: no sheet has
per-country DoC crude production, only an OPEC-wide aggregate — exactly what Session B's
Camelot PDF fallback is for. Acceptance criterion met: parsed 2026 annual world demand
(105.74 mb/d) matches the real MOMR cell exactly.

Session B: tried Camelot first, as the spec calls for — the PDF's own download endpoint
(`momr.opec.org/pdf-download/`) returns a 403, and Camelot's lattice mode needs a system
Ghostscript install (a Windows UAC-gated installer this automated session couldn't approve
itself; the user ran it). With Ghostscript installed and a real user-provided PDF in hand,
the premise turned out to be moot: the MOMR PDF has a full, clean, digitally-native text
layer, not a scan — reading it directly with `pypdfium2` and a handful of regexes extracted
the one table missing from Excel (per-country DoC crude production, 22 countries) more
simply and reliably than image-based table detection would have. Verified independently:
summing every OPEC member country this parser found for July 2026 (23,633) matched the
PDF's own printed "Total OPEC" line (23,632) to within OPEC's own rounding disclaimer.
Per the spec's "if unstable, stop and document" allowance, Camelot itself was uninstalled
again once this was confirmed — it's not a project dependency. `quotas.csv` seeded from
OPEC's own 2 August 2026 press release (published as an embedded PNG image, not HTML or a
PDF table — read visually) — 7 of the "Voluntary 8" group's countries have current targets;
UAE already reached its separate ceiling and isn't part of the recurring table, and every
other DoC country has no quota seeded yet. Page 06 gained a production-vs-quota grouped-bar
chart and a revision-waterfall chart (both new `core.theme` primitives), verified live
in-browser with real data (e.g. Oman 110% compliance, Saudi Arabia 70%).

Session C: `pipelines/jodi/` bulk-downloads JODI-Oil's annual "primary" (crude oil) CSV and
filters to crude production/refinery intake/closing stocks for the top-15 producers. Found
a genuine reporting gap, confirmed live: Russia, Iraq, Iran, UAE, and Brazil — all major
real-world producers — have zero production data in JODI's primary table for all of 2026,
so "top 15" was computed from what JODI actually has (averaged across all available 2026
months, not just the latest, since a handful of otherwise-reporting countries have one-off
monthly gaps too) rather than assumed from other sources. Also found the two annual-CSV
filename patterns differ for the current (still-updating) year vs. closed years, and that
`OBS_VALUE` carries two distinct non-numeric markers (`"-"` not reported, `"x"` confidential/
inapplicable-unit) that both need dropping before conversion. Monthly entrypoint confirmed
idempotent live (identical row count across two consecutive runs). No page work this
session — pure data ingestion, per the spec.

Session D (final for this spec): `pipelines/baker_hughes/` scrapes the current weekly
North America rig count XLSX. Found there's no guessable URL, unlike OPEC's Excel
appendix — the file lives at a fresh random UUID (`rigcount.bakerhughes.com/static-files/
{uuid}`) each week, so the pipeline scrapes the landing page for the link labelled
"North America Rig Count Report - New Report" (a stable label distinguishing it from the
archived report link beside it). A HEAD request (confirmed live to return the same
`Content-Disposition` filename as a GET, with no body) resolves the report date and avoids
re-downloading the ~8 MB file on a cache hit. The `NAM Weekly` sheet is already a long
granular table (~188,000 rows, ~2.7 years of history) rather than a snapshot, so — unlike
MOMR — no vintage-tracking scheme was needed; ingestion time is used for `revision_date`,
matching `pipelines/eia`'s convention. Aggregated to three levels (country total, country×
drill-target, country×drill-target×state) rather than full per-county granularity, judged
excessive for now. Confirmed real values: US oil rigs = 447, US total = 588 (2026-08-28
report). Page 06 gained a single-series US oil rig count chart — a true dual-axis rigs-vs-
WTI chart waits for Spec 07 (Henry Hub/WTI), per the spec's own note. Pull confirmed
idempotent live (5,935 rows / 63 series, unchanged across two consecutive runs).

Close-out: pulled a second real MOMR vintage (July 2026, alongside August) to satisfy the
Definition of Done's "≥2 vintages stored" — confirmed live via the same URL pattern
Session A found, no synthetic data. Also added the oil-on-water navy-area chart (page 06's
Visualisation spec item 3, not assigned to any single session but the data was already
captured in Session A and otherwise unused) — a new `core.theme.time_series_area_chart`
primitive. With two vintages now stored, the revision waterfall shows genuine non-zero bars
and the oil-on-water series' quarterly range extended back to 2024.

Spec 06 is now feature-complete: page 06 (production-vs-quota, revision waterfall,
oil-on-water, US rig count), MOMR/JODI/Baker Hughes pipelines all green, ≥2 MOMR vintages
stored, tests passing.

#### Spec 07 (refinery cracks, IB Gateway) — deferred
Needs a locally-running IB Gateway/TWS with the API enabled per the spec's own manual-prep
step — confirmed live that none of the standard ports (7497/7496/4002/4001) are listening
on this machine. Skipped for now in favour of Spec 08, which has no such local-service
prerequisite; revisit once IB Gateway is set up.

#### In progress — Spec 08: Weather overlay (Open-Meteo + ECMWF)
Session A: `pipelines/weather/` pulls Open-Meteo HDD/CDD (no key) for 14 cities (9 EU,
5 US), population-weighted EU/US aggregates, and a climatology-vs-forecast page. Confirmed
live: both the forecast and archive endpoints accept **batched, comma-separated multi-city
requests**, returning a JSON array in input order — one request per EU/US group instead of
one per city. Also found the spec's own wind param name is stale (`windspeed_10m_max`
doesn't work; the real one is `wind_speed_10m_max`). Hit — and worked around — two distinct
real rate limits (per-minute and per-hour); redesigned the climatology builder to compute
directly from the lake's own already-backfilled history (`core.seasonal.seasonal_stats`,
2020 excluded automatically) rather than making a second expensive archive call, avoiding
the rate limit entirely for that step. Population weights sourced from a single consistent
source (macrotrends.net 2024 metro-area populations) for all 14 cities. Per user request,
extended beyond the spec's own visualisation spec: a US mirror of the EU HDD-vs-gas-storage
dual-axis chart (net-withdrawal derived as `-level.diff()` from Spec 05's EIA storage level,
since EIA has no injection/withdrawal split unlike GIE's AGSI), plus NYC/LA CDD-anomaly-vs-
ISO-load dual-axis charts joining Spec 05's gridstatus data. A real scale-mismatch bug was
caught and fixed live in-browser: joining a 90-day weather-anomaly window against a
multi-year gas-storage series on the same dual-axis chart stretched the shared x-axis to
the wider series' full range, squashing the weather trace to an invisible sliver — fixed by
trimming the other series to the same recent window before charting. Acceptance criterion
met: Dublin's real recorded temperatures give manual HDD values matching the lake's stored
figures exactly (within rounding).

Session B: ECMWF Open Data (`ecmwf-opendata`, no key, CC BY 4.0) IFS 2m-temperature
forecast at D+3/D+7, rendered as anomaly maps (`pipelines/weather/anomaly_maps.py`, via
`cartopy` — confirmed live to install and render cleanly on Windows via plain `pip
install`, no system GEOS/PROJ needed) against a coarse EU/CONUS climatology grid. The
spec's own "ERA5 2010-2024 climatology grid" was simplified to a 3-year (2022/2023/2024)
same-calendar-day normal computed from Open-Meteo's archive endpoint (confirmed live: no
multi-year-single-day batch mode exists, so this keeps the number of archive calls small
rather than pulling a full CDS-sourced ERA5 grid, which would need a separate Copernicus
account not otherwise used by this project). The spec's "DuckDB table `map_assets`" was
implemented as a Parquet manifest file instead — no precedent for a persisted (non-view)
DuckDB file exists elsewhere in this codebase. `Client.latest()` (metadata-only, no
download) confirmed live as a cheap way to cache-check against the real forecast run
datetime. Page 08 got a new region/D+3/D+7 map section, reading only the manifest — never
calling ECMWF/Open-Meteo directly from the page — verified live in-browser (switching
region and step correctly swaps the displayed map).

Session C: a 10m-wind-speed forecast index for DE/DK/IE (`pipelines/weather/wind.py`,
one representative point per country in a new small `wind_locations.csv`, reusing
`client.py`'s existing wind field) and `pull_daily.py` — the real scheduled entrypoint
(Spec 13), distinct from `pull_weather.py`'s one-off history backfill: refreshes the
16-day forecast (HDD/CDD + wind) and re-renders the 4 ECMWF anomaly maps daily. Also
added a stale-map badge (>24h since render) to page 08's anomaly-map section. A real,
confirmed-live gotcha found and documented rather than glossed over: the wind
cross-check chart's two series don't actually overlap in time —
`pipelines/entsoe/pull_daily.py` only ever ingests the *prior day's* ENTSO-E wind
forecast (a trailing window by that pipeline's own design), while Open-Meteo's wind
index looks 16 days forward — so the chart honestly shows a recent-observed-into-
forecast transition, not a same-day correlation check; flagged as a follow-up to widen
ENTSO-E's own forecast pull to a forward window instead. Spec 08 is now
feature-complete: HDD/CDD history+forecast+climatology, ≥2 anomaly maps auto-rendering
daily (4, confirmed via a real `pull_daily.py` run), the dual-axis weather-vs-gas
charts, and the wind cross-check are all live; tests green.

#### v0.8 — Dashboard redesign: institutional light theme, cards, real map tiles
Cross-cutting change, not tied to a spec — a visual redesign against reference screenshots
of professional energy/intelligence dashboards. Locks an explicit light theme
(`.streamlit/config.toml`: white canvas, dark-navy sidebar, Inter font) instead of silently
following the viewer's OS/browser dark-mode preference — this also fixed a real bug:
`seasonal_range_chart`'s annotation box and light-grey gridlines were nearly illegible
against a dark background that was never actually guaranteed. Every chart section across
all 7 existing pages now wraps in a new `apps.dashboard.components.card.card(title)`
bordered container instead of a bare `st.subheader`. Maps (`padd_map.py`, `power_maps.py`,
`entsog_map.py`) moved from Plotly's flat `Scattergeo` projection to `Scattermapbox` with
the free `open-street-map` tile style — real street tiles, no Mapbox token, no new
dependency. Found live that Scattermapbox's free raster styles ship no icon sprite at all,
so the existing rotated-triangle direction markers were silently failing to render; fixed
by switching to plain circle markers. Also rolled out two further patterns from the same
design survey (World Monitor, Conflict Dashboard, War Watch) to every page: a segmented-
control time-range pill row on each page's longest raw time series, and a collapsible
filter panel (checkboxes + live latest-value counts) on each page's biggest fixed list
(stock series, corridors, zones, regions, quota countries). Verified live in-browser on
every page, including forcing the browser to dark mode to confirm the theme lock holds.

#### v0.10 — Spec 09: News ingestion & event tagging (GDELT + event overlays)
New `events` lake schema/dataset (`core/schemas.py`, `core/storage.py`) — this
project's first list-typed column (`tags`). Session A: `pipelines/news/` — a GDELT
DOC 2.0 client (free, no key) against a curated (commodity × event_type) query
dictionary. Confirmed live: `api.gdeltproject.org` is severely flaky (connect
timeouts, resets, and even an HTTP-200-with-plain-text rate-limit body, not just
429s) — the client retries broadly and `pull_news.py` treats each curated query
independently, since two real full pulls saw only 2/6 and 5/6 queries succeed
respectively. Session B: a real headline-derived tagging engine
(`pipelines/news/tagging.py` — multi-tag extraction, severity 1-3 by keyword tier, geo
via a place-name dictionary that deliberately overrides the publisher-country field)
replacing Session A's placeholder tagging; fuzzy cross-source dedup (rapidfuzz,
≥90 similarity within 48h) catching near-duplicate articles from different outlets
that exact-URL dedup can't; a new page `09_events.py` (filterable event table +
events-per-week bar chart). Session C: a reusable
`apps/dashboard/components/event_overlay.py::add_event_markers`, drawing
severity-coloured vertical lines with hover headlines onto an existing chart —
wired onto pages 01 (crude), 02 (gas), and 06 (crude/supply, substituting for the
spec's named page 07, still deferred pending IB Gateway). A real bug caught live
before shipping broken: calling `fig.add_vline()` once per event hung the page
indefinitely with 960 real events in the lake — fixed by building shape dicts and
setting them via one `fig.update_layout(shapes=...)` call instead.

**Descoped**: a Guardian Open Platform client (`guardian_client.py`) was built behind
the same interface as GDELT's, but was never live-verified — `GUARDIAN_KEY` was never
set during this build. `pull_news.py` gracefully skips Guardian entirely when no key
is configured, so the pipeline is fully GDELT-only for now; add a real key and this
becomes a live second source with no further code changes needed. NewsAPI/WorldNews
were never used at all, matching the spec's own "not for scheduled pulls" guardrail.

#### v0.11 — Critical fix: DuckDB was silently truncating every series to whole numbers
Cross-cutting fix, not tied to a spec — found while verifying Spec 10's FX data.
`core/storage.py`'s read path globbed every source's parquet files together with a
bare `SELECT *`; Baker Hughes' rig-count files (Spec 06, genuinely whole numbers) were
physically `int64`-typed, while every other source used `double`. DuckDB's default
cross-file schema resolution silently coerced the **entire** `value` column to
`int64` for **every reader**, not just Baker Hughes' own rows — invisible for months
across large-magnitude series (losing a crude-stock figure's fraction doesn't show on
a chart), but catastrophic for Spec 10's FX rates: `fx.usd_eur` (always near 1.0) read
back as exactly `1.0` for every single date. Confirmed live that an outer `CAST`
doesn't fix it — the truncation happens at DuckDB's scan stage, before any SQL
expression sees the real value; the actual fix is `read_parquet(...,
union_by_name=true)`. Kept an explicit per-column `CAST` to each schema's canonical
type as defense in depth, plus a write-side `.astype({"value": "float64"})` so a
future int-only source can't reintroduce this. Existing Baker Hughes files repaired
in place. A new regression test reproduces the exact conditions (a hand-written
int64-typed parquet file for one source alongside a normal float source).

#### v0.12 — Spec 10: Macro/FX normalisation (FRED, Frankfurter, Eurostat)
Session A: `FREDClient` + `FrankfurterClient`. Per explicit, repeated user request
("add many more data points from FRED... broader picture... around Energy", then
"include much more around energy and inflation with micro and macro level"), goes
well beyond the spec's own 5-series list to **35 FRED series** — 18 macro (CPI, core
CPI, PCE, PPI, dual dollar indices, nominal + real 10Y yields, breakeven + survey
inflation expectations, GDP, unemployment, Fed funds, M2) + 17 energy-specific (WTI,
**Brent** — a genuine gap-fill, no Brent series existed anywhere else in this
project — Henry Hub, national + all 5 PADD-level gasoline prices, Gulf Coast diesel/
jet fuel, PPI crude/fuels, CPI energy, petroleum import price index, oil & gas
extraction employment, and the Dallas Fed Energy Survey as a unique energy-sector
sentiment gauge). Every series individually confirmed live before being added —
caught two real wrong guesses (a stale/wrong-type EA HICP series the spec itself
named, and a "petroleum" import-price ID that was actually Zinc). Session B:
`EurostatESIClient` (EU/DE/FR/IT/ES/IE economic sentiment — confirmed live that bare
`EU`/`EA`/`EA19` geo codes silently return nothing, no error; real codes are
`EU27_2020`/`EA20`) and `core/macro.py` (`deflate`, `to_currency`, `align_freq`,
`year_over_year`, `zscore`), hand-checked against toy series with manually-computed
expected values. Session C: page `10_macro.py` (dual-axis dollar-vs-WTI, real-vs-
nominal WTI indexed 2018=100, USD-vs-EUR energy small multiples, an ESI heat-strip)
plus a `deflate()` integration on `015_us_oil_overview.py`. Definition of Done fully
met — no descoping this time.

A naive test assertion broke against WTI's real 2020-04-20 negative print (-$36.98,
the COVID storage crisis) and again against Italy's real 1982 ESI low of 38.4 —
both fixed by checking only the latest value, not the full history, matching the
now-familiar lesson from earlier specs: full-history real data isn't guaranteed to
sit inside a "plausible-looking" range assumed without checking.

#### v0.13 — News page redesign: clickable world map, translation, Kardamow-take captions
Cross-cutting feature on an already-shipped, tagged spec (v0.10) — per explicit
request ("put world map that anyone can click and see the news with translate
option... as a small caption use kardamow... what exactly could this mean for energy
complex"), not tied to a new spec number. `events` schema gains a `language` column
(GDELT/Guardian already fetched it, just never persisted). `apps/dashboard/
components/geo_centroids.py` — a static country-centroid table (no live geocoding
API; `restcountries.com`'s free v3 confirmed dead, returning HTTP 200 with a
deprecation notice instead of an error) covering all 98 real distinct `geo` values in
the lake. `apps/dashboard/components/news_map.py` — a clickable map, one marker per
country, sized by event count, coloured by max severity. Page 09 redesigned: clicking
a marker scopes the existing commodity/tag/severity/date-filtered feed and table to
that country; each feed row gets a translate button (`pipelines/news/translate.py`,
MyMemory-based — confirmed live and free after `libretranslate.com`'s public instance
turned out to now require a paid key and Google's unofficial endpoint 429'd — cached
on disk keyed by event_id). Phase 2, `pipelines/news/kardamow_caption.py`: a
one-sentence "Kardamow take" on what a translated headline could mean for the energy
complex, via the Anthropic Messages API (`anthropic` SDK added as a dependency, an
explicit choice over raw `requests` since the added error-handling/retry niceties
were worth the new dependency here) — gracefully shows an explanatory message instead
of crashing until a real `ANTHROPIC_API_KEY` exists, matching the Guardian-key
precedent from Spec 09.

Four real bugs found and fixed via live verification, not just unit tests:
1. **`core/storage.py`**: `union_by_name=true` only NULL-fills a column present in at
   least one scanned parquet file — a column absent from *every* file (the whole
   `events` lake immediately after the `language` schema change) raised a DuckDB
   Binder Error instead of reading cleanly. A schema column not seen in the glob now
   gets selected as a typed NULL literal instead of referenced directly.
2. **`news_map.py` customdata**: a flat per-marker string array gets indexed like a
   list of characters by Plotly's click-event JSON round-trip — "United States" came
   back as just `"U"`. Fixed by wrapping each point's customdata in its own list.
3. **`go.Scattermapbox` never fired a Streamlit `on_select` event at all**, confirmed
   via direct Plotly JS listeners in-browser (zero `plotly_click`/`plotly_selected`
   from real clicks squarely on a marker). Switched to `go.Scattermap` (the newer
   MapLibre trace Plotly's own console already recommends migrating to) — fixed it.
   This project's other maps (`padd_map.py`/`entsog_map.py`/`power_maps.py`) still
   correctly use `go.Scattermapbox`, since none of them need click selection.
4. **"Clear selection" didn't stick** — the plotly widget remembers its own last
   selection across reruns independently of `st.session_state`, immediately
   re-overwriting a cleared value on the very next rerun. Fixed by versioning the
   widget's own `key` so clearing forces a genuinely fresh, selection-less instance.

Verified live end-to-end, including a real translation (not just the no-op path): a
fresh `pull_news.py` run populated real `language` values (Chinese, Spanish, Arabic,
and 9 others), and translating a real Chinese headline via the page's own button
produced a coherent English sentence. Phase 2 (the LLM caption) is code-complete but
still unverified live — no `ANTHROPIC_API_KEY` has been provided yet.

#### v0.14 — Spec 16: NewsAPI.org manual-search supplement
A manual, on-demand NewsAPI.org search added to `pipelines/news/` and page
`09_events.py` — deliberately kept out of any scheduled pull, since Spec 09 already
found and documented that NewsAPI's free Developer tier's ToS bans production/
scheduled use (100 req/day, 24h delay, dev/testing only). `newsapi_client.py`'s
response shape was confirmed live against a real key to match NewsAPI's own published
reference exactly — no surprises this time, unlike several other sources in this
project. The response carries no `language` or `sourcecountry` field at all, so
`language` is hard-set to `"unknown"` (the translate button correctly no-ops, same as
the pre-`language`-schema rows already in the lake) and `sourcecountry` is left blank
(geo resolves via headline keywords, the same fallback every other source already
relies on). A real regression test asserts `pull_news.py::main`'s own source code
never references NewsAPI — scoped to `main` specifically, since the whole module
legitimately imports the client for the new manual-search path. Verified live
end-to-end: a real manual search ("Strait of Hormuz tanker", crude) from the running
page wrote exactly 100 real event rows (matching the request's `pageSize=100`),
correctly tagged via the existing pipeline.

#### v0.15 — Spec 17: Adanos market-sentiment overlay
Reddit/X/News/Polymarket buzz and sentiment scores for a curated 57-ticker
energy-complex basket, added as a new section on page 10 (Macro & FX) — a separate,
independent data source sharing that page per the spec's own text. The ticker basket
spans every energy-complex segment (majors, E&P, refiners, midstream, oilfield
services, gas/LNG, coal, uranium, renewables) and broad geography (US, Canada, UK,
Netherlands, France, Norway, Italy, Brazil, Australia), plus 5 OPEC/OPEC+
geographic-exposure tickers added per explicit request — Libya, Nigeria, Iraq, and
Venezuela's own national oil companies are all wholly state-owned with no
publicly-traded shares at all, so real Iraq-Kurdistan pure-plays (`GENL`, `GKP`) and
Nigerian producers (`SEPLAT`, `OANDO`, `ARADEL`) stand in for genuine indirect
exposure instead; Libya and Venezuela have no standalone listed pure-play at all, so
their exposure stays indirect through majors already in the basket (`E`/`TTE` for
Libya JVs, `CVX` for its licensed Venezuela JV).

Every one of the 57 tickers was individually confirmed live against the real API
before being trusted — all 57 resolved, including all 5 OPEC/OPEC+ candidates. One
real wrong guess caught this way: Seplat Energy's actual Adanos ticker is `SEPLAT`,
not its LSE ticker `SEPL` (found via a live `/search` call). A more consequential
finding: **`/compare` never errors on an unrecognised ticker** — a deliberately fake
symbol still returns HTTP 200 with a zeroed row (`company_name: null`), identical in
shape to a genuinely-supported ticker with no qualifying data this period. That null
is the only real existence signal `pull_adanos.py` filters on — "the call succeeded"
proves nothing. `sentiment_score` is nullable too; a null value is skipped entirely
rather than written as a misleading `0.0` (`ts_long` needs a real float, and "no
data" isn't "neutral").

A real weekly pull used exactly the documented 25-call budget (6 ticker-batches × 4
platforms + 1 sector-trend call, ≈108 calls/month, 43% of the 250/month free-tier
cap) and wrote 372 real rows. One CI-only bug found after merge: `AdanosClient`
initially raised when `ADANOS_API_KEY` was unset, which broke every cassette-replay
test in CI (the real key only exists in the gitignored `.env`, never in CI's
environment) — fixed to default to an empty string instead, matching every other
optional-key client in this project, confirmed by faithfully reproducing CI's exact
environment locally before pushing the fix.

#### v0.16 — Spec 15: OFAC SDN sanctions tracking + events-lake bridge
Diffable tracking of the US Treasury's Specially Designated Nationals (SDN) list
(`pipelines/ofac/`), tagged for energy relevance, plus a deliberate bridge into the
*existing* news/events infrastructure (Spec 09) rather than a standalone silo — a
newly-listed energy-related sanction now automatically surfaces on page 09's map/
feed/table and as a severity-coloured line on pages 01/02/06's event overlay, via
the pre-existing `event_overlay.py` with zero changes needed there. New
`core/schemas.py::SANCTIONS_SCHEMA` and dedicated `core/storage.py` read/write — a
genuinely different current-state-table shape (first_seen/last_seen/status already
encode the diff history) than every other pipeline here, so it deliberately doesn't
reuse `_write_partitioned`.

A real correction of my own mistake, caught mid-session: an initial live check for
comma/semicolon delimiters in the `program` field found none and wrongly concluded
it was single-valued. Only while designing `program`→`geo` resolution for the events
bridge did a deeper check reveal the real delimiter, `"] ["` — 2,905 of 19,326 rows
(15%) are genuinely multi-program (243 distinct codes in total). `programs` is
`list[str]` after all, matching `events.tags`'s existing precedent — the spec's
original instinct was right; my own first-pass verification was wrong, corrected
before any code was written against it. Also confirmed live: pandas silently turns
a mapped `None` into a float `NaN` (and `NaN` is truthy in Python, so a bare
`if not value` guard silently fails to catch it) — every nullable check now uses
`pd.isna()` explicitly. IMO extraction covers 99% of real vessel rows (1,525 of
1,540), far better than the spec's own cautious framing suggested. A real
per-entity OFAC deep link (`sanctionssearch.ofac.treas.gov/Details.aspx?id=...`)
was confirmed live and used as the event `url`.

Verified live end-to-end: a real pull wrote 19,326 sanctions rows (entity_type
distribution matches live research exactly: 9,926 entities / 7,518 individuals /
1,540 vessels / 342 aircraft), 2,506 energy-related rows bridged into the events
lake (1,711 → 4,217 total). Page 15's four panels, page 09's map/feed, and a real
event-overlay marker on page 06's Oil-on-Water chart all confirmed live in-browser.

#### v1.0 — Spec 13: orchestration, testing hardening & CI/CD
Local Windows Task Scheduler orchestration, not GitHub Actions — this project runs
on the operator's own laptop, not a server, so `infra/run_scheduled.py` groups every
pipeline's real entrypoint by cadence (daily/WPSR/gas-storage/weekly-Friday/monthly)
with per-pipeline failure isolation, and `infra/register_tasks.ps1` registers the
real Task Scheduler entries; `ci.yml` stays exactly as it was, cassette-only.
`core/freshness.py::staleness_report()` classifies every source across all four
lake datasets (`ts_long`/`flows`/`events`/`sanctions`) as green/amber/red against its
own expected pull cadence, surfaced on the home page's extended "Lake status" table.
Two real bugs caught via a live run against the actual lake before landing: `ts_long`
freshness must use `revision_date` (ingestion time), not `ts`, since forward-dated
series (weather forecasts, MOMR vintages) produced impossible negative staleness
under `ts`; and a stale, wrongly-scheduled bare `"open_meteo"` source was excluded.
`tests/test_cassette_secrets.py` reuses README's own documented secret-scan regex as
a real CI gate; `tests/test_pages_smoke.py` drives every dashboard page headlessly
via `streamlit.testing.v1.AppTest` (the documented `from_file(app.py).switch_page(
...)` pattern — loading a page file directly raises `ModuleNotFoundError`, confirmed
live). README gained an "Orchestration & scheduling" section, a data-source
licences/attribution table, and a credential-handling/key-rotation policy written
into the repo itself. `CHANGELOG.md`'s stale content (it still described the
long-deleted pre-`specs/` Postgres/SQLAlchemy scaffold) was replaced with a real,
cross-checked Keep-a-Changelog summary of every tagged version. 17 tracking issues
opened on GitHub for every stretch-goal item skipped across Specs 00–17 plus the
fully unbuilt/deferred specs (07, 11, 12, 14). **"v1.0" means orchestration/CI/
freshness complete for every spec built so far, not full dashboard completion** —
Specs 11/12/14 remain unbuilt, Spec 07 stays deferred.

#### v1.1 — Weather module Phase 1: GFS as a second, independent NWP model
Cross-cutting addition on top of an already-shipped, tagged spec (v0.9), not a new
spec number — adapts a user-supplied `weather-module-spec.md` (written against
Railway/Postgres/Grafana) to this project's actual DuckDB+Parquet/Streamlit/Task
Scheduler stack. Confirmed scope with the user before writing code: reuse the
existing 3-year climatology grid (no `cdsapi`/Copernicus CDS account) and the
existing EU/US city-sample aggregates (no new region polygons) — zero new
dependencies, zero new accounts, zero new schemas. `pipelines/weather/gfs_client.py`
pulls a 2m-temperature GRIB2 subset per (region, forecast step) from NOMADS'
GRIB-filter service. Two real gotchas confirmed live before writing code against an
assumed shape: longitude convention is inconsistent across regions (a CONUS bbox
comes back 0..360, a EU bbox comes back already -180..180 — normalised
unconditionally on load) and a not-yet-published GFS cycle returns HTTP 403 with an
HTML body, not a 404 (handled with a one-cycle-back retry). `pipelines/weather/
gfs_degree_days.py` reuses `degree_days.py`/`aggregate.py` unchanged, tagged
`source="gfs"` — a real bug was caught before it ever ran: both of those functions
hardcode `source="open_meteo"` in the DataFrame they return, which would have
misclassified every GFS row as Open-Meteo's own on read-back; fixed by mirroring
`pull_daily.py`'s existing `_mark_as_forecast()` pattern. `anomaly_maps.py`'s
manifest and render function now carry an explicit `model` dimension end to end;
page 08 gained a model selector. A second, CI-only bug was caught the same way this
project has hit before: the new GFS test was the first in the whole codebase to
actually invoke the real `cfgrib` GRIB-decode backend, and CI's Linux runner has no
working `eccodes` install — fixed by monkeypatching `xr.open_dataset` (matching
every other weather test's own established convention) instead of adding a new CI
system dependency. Verified live: a real `pull_daily.py` run rendered 4 ECMWF + 2 GFS
anomaly maps and wrote 32 GFS HDD/CDD rows; the model selector confirmed live
in-browser swapping between ECMWF and GFS maps/captions correctly.


---

# Changelog

All notable changes to this project are documented here, in the style of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This file is a terse,
per-version summary; `README.md`'s own "Build log" section carries the full
narrative (real bugs found, corrections made mid-session, live-verification
detail) behind each entry.

**Where this project actually stands**: specs 00–06, 08–10, and 13 and 15–17 are
built and tagged below. Spec 07 (refinery cracks) is deferred, blocked on a
local IB Gateway install. Specs 11 (AIS vessels), 12 (flights), and 14
(cross-spec analytics layer) are not yet built — see the open tracking issues
on the GitHub repo for every one of these plus every stretch-goal item skipped
along the way.

## [Unreleased]
### Added
- **Terminal restyle (`design/terminal-ui-v2`) — `web/` (`data.kardamow.com`) rebuilt as
  a Bloomberg-style terminal.** `tokens.css` rewritten wholesale: black ground, one
  monospace family, amber `--accent` rationed to type on dark strips (never a fill), zero
  radius, no shadow, an 11px root with the whole rem scale re-derived against it, and
  `--measure` deleted outright so every page runs full-bleed. Inter survives only for
  running prose (`.prose`) — every label, heading, figure and table cell is monospace. A
  primitive layer (`.term-panel`, `.term-head`, `.term-grid`, `.term-cell`, `.term-key`,
  `.term-bar`, `.term-table`) replaces the previous product-UI kit (`card()`/`.card-link`,
  `nav-pill`, segmented controls, `.rise`) across all 14 routes; three files missed by the
  earlier component passes (`app/flows/page.tsx`, `app/oil-math/page.tsx`,
  `app/page.tsx`) still referenced the deleted `card`/`card-link` classes and were
  rendering unstyled — caught by grepping for the dead class names and fixed by moving
  them onto `.term-panel`. Every chart and the map now build their layout from
  `theme/plotly.ts`'s `baseLayout()`, so exactly one function paints a chart ground.
  - **Two tests guard the system.** `tokens.test.ts` (pre-existing) asserts every
    `var(--x)` referenced under `src/` resolves against `tokens.css` — it caught five
    dead-token references (`--rule`, `--heading-stack`, `--ink` and `--body-stack` among
    them) that had been rendering as nothing on the live site. `tokens.pins.test.ts`
    (new) pins every chrome and series token's literal value and enforces a 4.5:1
    contrast floor against every ground it actually paints on; `--navy-rgb`/`--red-rgb`
    are asserted as derived from their hex tokens rather than restated, so a retuned hex
    cannot silently drift from its rgba triple.
  - **The contrast floor caught two values that had been asserted by hand and were
    wrong.** `--faint` at `#6b7280` was 4.34:1 and is now `#7d8590` (5.63:1); `--down` at
    `#ea3943` was 4.4951:1 and is now `#ee4a56`.
  - **The WPSR heat wash was rebalanced.** Deficit tints carried chroma 18–41 against
    surplus's 5–9 at comparable contrast — navy greyed out at low alpha while red stayed
    a hue. Both tints now read with equal weight, verified by measuring the blended pixel
    against the panel ground rather than by eye.
  - **The cross-surface colour contract with `core/design.py` is now broken, and
    deliberately.** The two surfaces still agree on what each series *means* — navy is
    always the primary series, orange is always the seasonal median — but no longer on
    the *values*: navy at `#0f2a4a` is invisible on black, so every series here is
    re-derived at a luminance that survives a dark ground (`--navy: #4d9fff`,
    `--red: #ff5a4d`, etc). A chart drawn on `data.kardamow.com` and the same chart
    exported from the Streamlit app now tell the same story in different colours.
  - Local gate: `pnpm test` (38 passing), `pnpm lint` and `pnpm typecheck` all clean. The
    production build could not be run on this machine (Turbopack OOMs under 1.5GB free of
    7.79GB) — the production build is Vercel's. Branch not yet merged; per the plan's own
    notes, the merge call is the user's, not this session's.
- **UI restyle complete — masthead, section kit and Kardamow house type replace the
  bordered `card()` layout across all 16 pages (`2026-09-06-ui-design-system`).** Every
  page now opens with `page_header()` (a Lora `<h2>`, demoting the old bare `st.title()`)
  and wraps each chart or table in `section()` (`<h3>` + hairline rule) instead of
  `apps.dashboard.components.card.card()` — deleted here, along with its alias test.
  `core/theme.py`'s chart builders lost the `title` parameter on 30 of the 31 that took
  one: painting a chart's own title had already been made visually inert once the section
  header took over, but the dead parameter and its call-site argument were still threaded
  through every signature. `gauge_chart` kept it — its `title` labels the `go.Indicator`
  itself, real in-plot content, not a second `fig.update_layout` chart title.
  - **The doubled-title defect closes its last five sites: the shared map components.**
    `padd_map.py`, `news_map.py`, `power_maps.py` (two functions) and `entsog_map.py` each
    painted a second, dynamic title inside the plot area under a static `section()`
    heading that already said the same thing. None could be fixed mechanically — the
    dynamic part (a selected month, a snapshot timestamp, an averaging window) has no path
    back to the caller's static heading — so each got its own fix: the PADD month is
    already visible in its own slider, the news map's text was never a timestamp at all
    (an instructional caption, not provenance) and moved to `st.caption()`, and the three
    genuine freshness notes (day-ahead price snapshot, 24h cross-border flow average,
    7-day gas corridor average) moved to `source_note()` under the chart.
  - A live visual pass across all 16 pages, against a fresh dev server, caught a sixth
    stray title outside the map components: `01_us_padd.py`'s net inter-PADD balance bar
    chart was calling `fig.update_layout(title=...)` directly with the same text as its
    own `section()` heading. Removed.
- **Spec 21 complete — systematic strategies engine (Sessions A–C).** `core/systematic.py`
  (15 signal/sizing functions), `core/backtest.py` (backtester, `spread_to_return`,
  fractionation, inventory-predictability test), `core/strategies.py` (eight-entry
  registry), `pipelines/derived/systematic.py` writing **168,157 position rows**, five new
  theme primitives, and page `21_systematic.py` — verified in a real browser, not only by
  import. 95 new tests.
  - **Six of eight strategies run; two are skipped and say so.** `CARRY_1_13` needs nearby
    rank 13 and `FWD_SPREAD_MR` needs rank 7; EIA's discontinued route publishes 1–4.
    Both stay registered and `build_positions` raises rather than returning a flat series
    — a flat position is a real trading decision and must never stand in for missing data.
  - **The published anchors are not comparable, and the page says so.** Bouchouev's
    figures are all measured on C(1,13); these carry strategies run on C(1,3). A deviation
    is printed for `SHORT_SPREAD_STATIC` alone, the one directly comparable case — and it
    misses badly, **−0.01 against a published IR of 0.50**.
  - **Bouchouev's inventory-predictability finding does not reproduce.** On real Cushing
    stocks (n=1,165), inventories predict spreads slightly *more* than the reverse
    (r² 0.0104, t −3.50 vs r² 0.0061, t −2.67). Both weak. Rendered as an error on the
    page with the caveat that weekly stocks against a daily spread blunts the test.
  - **A real units trap, found by disbelieving the output.** Dividing a dollar spread
    change by the *spot* price to get return units explodes as price nears zero: it
    inflated calendar-spread annualised vol from **11.6% to 93.8%**, three days in April
    2020 doing all of it. `spread_to_return` uses a trailing median notional instead.
  - **Negative prices handled explicitly.** The 2020-04-20 −$37.63 settle made `np.log`
    warn and propagate a silent NaN through momentum and value; `log_price` now returns
    NaN cleanly, confining the gap to windows that touch the print.
- **Spec 20 Session C — ECT signal and page 20 (Spec 20 complete).** `core/vecm.py`
  gained `ect_signal` (β'y, rolling 60-month z-score, `-sign(z)` beyond entry and flat
  inside exit with hysteresis between, scaled by the crude leg's share of the adjustment
  speed and by inverse realised vol, flattened where it fights 3-month crack momentum),
  `backtest_positions` (turnaround-month fractionation) and `irf_table`. `core/theme.py`
  gained `cointegration_residual_chart`, `irf_chart` and `model_monitor_chart`. Page
  `apps/dashboard/pages/20_cracks.py` is live. 16 new tests.
  - **The DoD's own shift test caught a real look-ahead bug in the signal.** On its first
    run `ect`, `z`, `raw_position` and `momentum` all matched between a truncated and a
    full sample but `position` did not: `vol_scale` was normalised by the *full-sample*
    median, reading observations after *t* into every earlier position. Fixed to an
    expanding median. Left in, it would have silently inflated any backtest.
  - **Two documented stand-ins, surfaced in the UI rather than buried.** The spec calls
    for Spec 21's backtest engine and Spec 22's realised vol; neither `core/systematic.py`
    nor `core/risk.py` exists. The backtest is a minimal position × forward-move
    calculation with no costs, slippage or position limits, and the vol scaling is a plain
    rolling standard deviation. The page says so in a warning.
  - **Page renders its gaps honestly.** Board m1/m2/m6 tenors are empty because no
    *current* futures exist (EIA's route ends 2024-04-05, no IBKR feed) — a two-year-old
    settlement shown as a live tenor would be worse than a blank. The forward strip
    carries its own as-of date and a "not current" warning. The model card shows the
    random-walk failure as an error, per the conventions' "a miss is a visible
    diagnostic".
  - `model_monitor_chart` draws parity *and* the refit trigger, because a ratio of 1.02 is
    already losing to the benchmark while sitting inside a 1.05 trigger.
  - Crack futures extended to m3/m4 (EIA publishes ranks 1–4) so the forward strip has
    real shape. There is still no m6 from this source.
- **Spec 18 finally has real futures data** — 113,750 `fut.*` rows across 105 series,
  where before there were none at all. Three sources, each covering a different end of
  the problem, all writing the conventions' own series ids and partitioned by `source`.
  - **`pipelines/futures/eia_futures.py` — history.** EIA's `petroleum/pri/fut` route
    publishes real NYMEX settlements for contracts 1–4, free, through the API key Spec 01
    already uses: WTI from 1983, heating oil from 1980, RBOB from 2005, pre-2006 NYMEX
    unleaded 1985–2006. **113,661 rows.** The route is *discontinued* (verified against
    its own metadata: it stops at 2024-04-05 while `pri/spt` runs to the present), so it
    is history only and cannot drive a live board. It publishes ranks rather than contract
    codes, so it writes `fut.<root>.f01..f04.settle` directly and bypasses `nearby_panel`
    — `s12`/`s13`/`cv123` are computable, Dec–Dec and the roll calendar are not. RBOB
    (`rb`) and pre-2006 unleaded (`hu`) are kept as separate roots rather than spliced at
    ingestion, which is what `core.cracks.rbob_splice_flag` is for.
  - **`pipelines/futures/barchart_curve.py` — one date, the whole curve.** A Barchart
    spreads export carries no outright prices, but `SA` (strip average) and `SP` (spread)
    on the same pair pin both legs, and every other contract follows from a spread against
    an already-solved one. Rebuilds an **89-month Brent curve for 2026-09-04** (Nov-26
    96.28 → Mar-34 67.51). Validated against a real published quote: reconstructed from
    spread rows alone the front month comes out at **96.280** against Barchart's own
    **96.28s**, over-determined anchors agree to half a cent, and an implied QAZ6−QAF7 of
    3.17 matches the separately quoted 3.17 exactly. Without an `SA` anchor it raises
    rather than returning a curve wrong by a constant. `source="manual"` — these settles
    are reconstructed from a vendor export and must not pose as an exchange feed.
  - **IBKR made ready.** New `pipelines/futures/ibkr_preflight.py` probes all four Gateway
    ports without needing one running, flags a `settings.ibkr_port` pointing somewhere
    closed, and prints the next step — replacing the hand-run port check every prior
    session recorded. Current status: all four closed. Also **fixed a real latent bug**:
    `IBKRClient.get_settles` sent a single multi-decade `durationStr`, which IB rejects
    outright, so the very first `pull_history` run against a live Gateway would have
    failed. It now chunks via `duration_windows` (365-day windows sharing their boundary
    date, so the lake's own de-dup removes the duplicate bar rather than a gap losing a
    settlement).
  - **Fixed: manual data drops were never actually git-ignored.** `.gitignore` carried
    `manual_settlements/*.csv`, but the path the code uses is `data/manual/futures`
    (`client.py::MANUAL_FUTURES_DIR`), so nothing under `data/manual/` was ignored despite
    the conventions saying it is. A dropped CSV could have been committed.
- **Spec 20 Session B — crack VECM (Murat & Tokat 2009).** `core/vecm.py` (monthly
  aggregation, ADF/PP/KPSS unit roots, AIC/SIC lag choice over p=1..4, Bai-Perron +
  Andrews sup-F breaks, Johansen, VECM fit, Granger both ways, rolling-origin forecast
  evaluation with Theil U and a Newey-West Diebold-Mariano test, and a model card) plus
  `pipelines/derived/vecm_refit.py`, registered in the `monthly` cadence. 29 new tests.
  New dependencies, approved first per root NOTES.md rule 7: `statsmodels>=0.15`,
  `ruptures>=1.1`, `arch>=8.0` (`arch` supplies the Phillips-Perron test statsmodels
  lacks, and is what Spec 22's GARCH engine will need anyway).
  - **All three of the spec's synthetic acceptance tests pass**: Johansen recovers
    beta = 0.1611 against a 0.16±0.03 target, Bai-Perron finds the obs-120 mean shift at
    exactly 120, and the random-walk look-ahead guard holds.
  - **On real data the model fails, and that is the finding.** Theil U = 1.0725 — 7%
    *worse* than a random walk — DM +1.81 / p = 0.070, 32 exceptions in 60 forecasts,
    `oos_status = fail`. Cause identified rather than papered over: the spot 3:2:1 crack
    is **not I(1)**. ADF and Phillips-Perron disagree in every sample window and PP
    rejects the unit root decisively (p = 0.008 full sample, 0.000 on the paper's
    1993-2008 window), because a refining margin mean-reverts. Johansen returns rank 2 in
    a two-variable system — the standard signal that the system is already stationary and
    the cointegration framework does not apply. Granger also runs the opposite way to the
    paper (crack->spot p = 0.442; spot->crack p = 0.038).
  - **April 2003 not recovered.** Bai-Perron with one break finds 2005-03 (+23 months),
    Andrews sup-F 2004-08 (+16); the 2004-05 crude run-up is a much larger level shift and
    dominates. Two breaks surfaces 2003-01 — three months out, but obtained by relaxing
    the break count, so recorded as partial, not a replication.
  - All of the above traces to the **spot legs**: the paper models crack *futures*, and the
    lake still holds none. Session C is gated on this — see the spec.
- **Spec 20 Session A — refining economics / crack boards.** `core/cracks.py` (3:2:1,
  2:1:1, single-product gasoline and distillate, NWE gasoil, Singapore gasoil, the
  $/gal→$/bbl and $/tonne→$/bbl conversions, the crack board and the seasonal heatmap)
  plus `pipelines/derived/cracks.py`, which wrote **45,476 real rows** across five
  `derived.crack.<name>.spot` series. 29 new tests.
  - **Built on spot legs, not futures — a forced deviation.** Checked live before writing
    any code: the lake holds **zero `fut.*` rows**, because Spec 18's pipeline has never
    ingested a real settlement. Three FRED spot product legs were missing and were added
    to Spec 10's `fred_series.py` (`DGASNYH`, `DGASUSGULF`, `DHOILNYH` — each probed live
    against the FRED API, never guessed), giving real crack history back to **1986**. The
    board's `m1`/`m2`/`m6` tenor columns read `NaN`, never `0.0`, until futures land.
  - **Cross-checked exactly.** `derived.crack.us321.spot` vs a 3:2:1 computed
    independently from the EIA API (`petroleum/pri/spt`) — 60 overlapping days, **max
    absolute difference 0.0**. Annual means also reproduce known refining history without
    being fitted to it: 2015-19 ≈ $17–19, 2020 $10.60 (COVID), 2022 $41.11 (post-Ukraine
    margin blowout), 2025 $21.75.
  - **A wrong constant in the spec, corrected.** Spec 20's worked example
    `crack_321(70, 2.20, 2.40) = 28.53` is arithmetically impossible — the correct value
    is **25.20** (no gallons-per-barrel factor gives 28.53; it would need 43.47). Recorded
    in the spec file, the pipeline guide, and the test's own docstring, alongside the
    spec's existing "April 2003, not September" correction.
- `tests/test_pages_browser.py` — a real-headless-Chromium render check for every
  dashboard page, closing a gap `tests/test_pages_smoke.py` (Spec 13) can't: that test
  only proves the Python script didn't raise, not that the browser actually painted
  anything. Opt-in via a new `browser` pytest marker (`pytest -m browser`, excluded from
  the default run by `pyproject.toml`'s `addopts` — needs a one-off `playwright install
  chromium`). Two real bugs caught and fixed while getting it green: (1) the test's own
  page order, built from a naive `sorted(glob(...))`, disagreed with Streamlit's actual
  sidebar-nav order at 11 of 13 positions — confirmed live against Streamlit's own source
  (`source_util.py`'s `page_sort_key`, which sorts by `(float(leading_number), label)`,
  not lexically — `015_us_oil_overview.py` parses to `15.0` and ties with
  `15_sanctions.py`, landing nowhere near the front); fixed by selecting each sidebar
  link by its filename-derived `href` slug instead of by position, which also makes the
  test immune to future page renumbering. (2) the very first browser request after
  `/_stcore/health` reports ok can outrun a 45s render timeout, since that endpoint only
  proves the HTTP server is bound, not that the main script's own heavy import chain
  (cartopy, xarray, matplotlib, ecmwf-opendata, ib_async, gridstatus, …) has finished —
  fixed with one warm-up `requests.get` before the timed Playwright assertions start.
- Spec 18 Session A (trading analytics layer): `pipelines/futures/` — a futures/options
  settlements pipeline with two clients (`IBKRClient` via the actively-maintained
  `ib_async` fork, `ManualCSVClient`) behind one `FuturesClient` interface, selected by
  `FUTURES_SOURCE`; `pull_history.py`/`pull_daily.py`; a `series_meta` Parquet manifest for
  contract metadata (expiry/tick_size/contract_unit/currency/roll_rule). An 8-angle review
  pass afterwards caught and fixed 8 real bugs before merge (a duplicate-row check missing
  `root`, `source` hardcoded regardless of provider, a missing-lowercasing gap, a
  trailing-window off-by-one, duplicated pull loops, and more — see
  `pipelines/futures/NOTES.md`).
- Spec 18 Session B: `core/curve.py` — roll-adjusted nearby contract ranks (ratio
  back-adjustment), time spreads, convexity, and a six-state curve-regime classifier (plus
  a seventh, `"flat"`, for the `s12==0` case the spec's own six states don't cover);
  `pipelines/derived/curve.py` writes `derived.spread.*`/`derived.curve.*` back to the lake,
  registered in `infra/run_scheduled.py`'s daily cadence (which also picked up Session A's
  own `pipelines.futures.pull_daily` — never actually wired into the orchestrator until now).
  All 12 tests pass on hand-verified synthetic data, matching every worked example in the
  spec's own text exactly.
  **Not yet merged/tagged** — no live IBKR Gateway and no real settlement data exist yet, so
  every session's own verification is against synthetic data only; the live cross-check and
  real idempotency check are explicitly deferred (see `specs/18_curve-market-structure.md`).
  Spec 18 itself remains in progress (Sessions C–D still to come).
- Spec 18 Session C: `core/calendars.py` gains its first real business-day arithmetic
  (`roll_calendar`/`roll_window_flag`, GSCI business-days-5–9 / BCOM 6–10 index-roll
  windows); `core/curve.py` gains `roll_pressure_seasonal`, `cushing_utilisation`,
  `utilisation_decile`, `physical_bands`, `tas_window_flag`. New pipeline
  `pipelines/eia_storage_capacity/` ingests EIA's own now-**discontinued** "Working and Net
  Available Shell Storage Capacity" report (last data 2024-03-01) — a real, live-investigated
  finding: no such series exists anywhere in EIA's actual API, contrary to what this spec's
  own Data table assumed. `pipelines/derived/cushing.py` writes `derived.cushing.util`/
  `util_decile` back to the lake. `pipelines/manual_physical/` stub reader for Spec 18's own
  4 physical-differential series (Spec 19 owns the full scope).
  **More real verification than Sessions A/B, unusually**: `pull_history.py` run for real,
  wrote 23 genuine semi-annual Cushing capacity rows; `pipelines/derived/cushing.py` run for
  real against that plus the existing real weekly Cushing-stocks series already in the lake,
  wrote 803 real weekly utilisation rows; `cushing_utilisation()` cross-checked against EIA's
  own published Alternate Utilization Rate for 2024-03-01 (`0.4104759069028832`) to within
  `1e-4` — an independent real-data check, not a synthetic one. Real limitation, stated
  plainly: every utilisation value after 2024-03-01 divides by that same frozen capacity
  figure, forward-filled, since the source will never update again. See
  `pipelines/eia_storage_capacity/NOTES.md` and `specs/18_curve-market-structure.md`.
- Spec 18 Session D (final session): page `apps/dashboard/pages/18_curve.py` and four new
  `core/theme.py` primitives (`curve_strip_chart`, `regime_ribbon_chart`,
  `scatter_piecewise_fit_chart`, `bday_heatmap`). Real, confirmed-live constraint checked
  before planning: zero rows exist anywhere under `fut.*`/`derived.spread.*`/
  `derived.curve.*` (no real futures settlement data has ever been dropped) — every
  root-dependent card renders a real no-data message instead of a chart, verified live for
  all 7 roots with no exceptions. The cards that **do** have real data — "days to next
  index roll" (`core.calendars.next_roll_window`, new), the GSCI/BCOM roll-calendar table,
  and the Cushing Utilisation vs Decile Rank chart (Session C's own 803 real rows) — all
  rendered correctly in-browser. Spec 18's Sessions A–D are now all complete; its own
  overall Definition of Done stays open (needs a real settle cross-check against CME/ICE's
  bulletin and a two-run idempotency check on real data) — both deferred, not done, pending
  real futures settlement data.
- Spec 19 Session A (trading analytics layer): `core/fundamentals.py` —
  `inventory_deviation` (a thin wrapper over `core.seasonal.seasonal_stats`),
  `days_of_cover`, `spare_capacity`/`spare_cap_regime`, `cot_percentiles`. New
  pipeline `pipelines/cftc/` ingests real CFTC Commitments-of-Traders data (no such
  pipeline existed anywhere — this spec's own text assumed it did via "Spec 14",
  which was never built) via CFTC's own Public Reporting Environment API, a real,
  free, no-key Socrata dataset — run for real this session: 19,650 rows across all 4
  roots (`cl`/`rb`/`ho` back to 2006, `lco` back to 2011). One managed-money net
  position cross-checked directly against a fresh, independent query of the same
  CFTC source (`84,020` contracts long for `cl` on 2026-08-25) — an exact match.
  `pipelines/derived/fundamentals.py` writes `derived.inv.dev_z.uscrude`/
  `derived.cot.<root>.mm_pct_3y` back to the lake for real; `derived.spare_cap.regime`
  is correctly skipped (no real EIA STEO/IEA OMR spare-capacity data exists yet —
  Session B's own manual-drop extension). Also fixes a real, confirmed-live bug in
  `core/storage.py::_write_partitioned` (mixed tz-aware/tz-naive `revision_date`
  values crashed the write path the moment both landed in the same partition) — see
  `core/NOTES.md`'s new incident write-up.
- Spec 19 Session B: six more `core/fundamentals.py` functions — `quality_spreads`,
  `refining_constraint_index`, `carollo_scatter`, `shale_response`, `benchmark_health`,
  `osp_signal` — plus a hand-rolled `_ols` helper (no scipy/statsmodels dependency
  needed for closed-form simple linear regression). New `pipelines/manual_physical/`
  reader for this spec's own 17-series manual-drop list (spare capacity, quality
  differentials, Saudi OSPs, benchmark-health counts) — no real data exists yet for
  any of them. Real, live verification of `carollo_scatter` against the actual lake
  (157 real quarters of US crude stocks vs Brent): a genuinely near-zero relationship
  (`share_wrong_sign = 0.452`), consistent with Carollo's own point that the classical
  stock-change/price relationship is weak in practice. Documents a real merge
  consideration with Spec 18's own, independently-built, smaller `manual_physical`
  stub on the still-unmerged `feat/futures-settlements` branch.
- Spec 19 Session C (final session): page `apps/dashboard/pages/19_fundamentals.py` and
  three new `core/theme.py` primitives (`grouped_agency_bars`,
  `dual_axis_inverted_chart`, `sign_agreement_scatter`). Real cards verified live: the
  inventory seasonal-range + days-of-cover, the Carollo diagnostic (`R²=0.0023`,
  `45.2%` of quarters violate the classical model), refinery utilisation, and CFTC
  managed-money positioning. Every other card (S&D balance, spare capacity, refining
  constraint index, shale response, benchmark health, OSP) renders a real no-data
  message, verified by an actual on/off test (a synthetic manual CSV dropped in, the
  OSP card confirmed to render real data, then removed and confirmed reverted).
  Cross-checked one inventory figure against a fresh, independent live EIA API call
  (`WCESTUS1` matched exactly) alongside Session A's own COT cross-check, completing
  the spec's overall Definition of Done. Also fixes a real bug caught by this
  session's own verification: `sign_agreement_scatter` crashed comparing two
  independently-resampled series without first pairing them on a shared index. Spec
  19's Sessions A-C are now all complete.

## [1.1] - 2026-09-04
### Added
- Weather module Phase 1: GFS as a second, independent NWP model alongside the
  existing ECMWF Open Data pipeline (Spec 08). Adapts a user-supplied
  `weather-module-spec.md` (written against Railway/Postgres/Grafana) to this
  project's actual stack, with zero new dependencies/accounts/schemas —
  `pipelines/weather/gfs_client.py` (NOMADS GRIB-filter download),
  `gfs_degree_days.py` (reuses the existing degree-day/aggregate functions,
  tagged `source="gfs"`), a `model` dimension threaded through
  `anomaly_maps.py`'s manifest, and a model selector on page 08.
### Fixed
- A real bug caught before it ever ran: `degree_days.to_ts_long()`/
  `aggregate.population_weighted()` both hardcode `source="open_meteo"` in
  their own returned DataFrame — reusing them for GFS without overriding that
  column would have misclassified every GFS row as Open-Meteo's own on
  read-back.
- CI-only: the new GFS test was the first in the project to actually invoke
  the real `cfgrib` GRIB-decode backend, and CI's Linux runner has no working
  `eccodes` install — fixed by monkeypatching `xr.open_dataset` instead of
  adding a new CI system dependency.

## [1.0] - 2026-09-04
### Added
- Spec 13: orchestration, testing hardening & CI/CD. `infra/run_scheduled.py`
  — a single local orchestrator grouping every pipeline's real entrypoint by
  cadence (daily/WPSR/gas-storage/weekly-Friday/monthly), isolating one
  pipeline's failure from the rest; `infra/register_tasks.ps1` registers the
  real Windows Task Scheduler entries (this project runs on the operator's own
  laptop, not a server — GitHub Actions stays CI-only).
- `core/freshness.py::staleness_report()` — green/amber/red freshness
  classification per source, across all four lake datasets (`ts_long`,
  `flows`, `events`, `sanctions`), surfaced on the home page's "Lake status"
  table.
- `tests/test_cassette_secrets.py` — a real CI gate reusing README's own
  documented secret-scan regex against every committed cassette.
- `tests/test_pages_smoke.py` — every dashboard page driven headlessly via
  `streamlit.testing.v1.AppTest`, asserting no page raises.
- README gaps closed: an "Orchestration & scheduling" section, a data-source
  licences/attribution table, and a credential-handling/key-rotation policy
  written into the repo itself.
### Meaning of this tag
"v1.0" means orchestration/CI/freshness is complete for every spec built so
far — not that the dashboard itself is feature-complete. Specs 11 (AIS), 12
(flights), and 14 (analytics layer) remain unbuilt; Spec 07 (refinery cracks)
stays deferred pending a local IB Gateway install. See the open GitHub issues
for these plus every stretch-goal item skipped along the way.

## [0.16] - 2026-09-04
### Added
- Spec 15: OFAC SDN sanctions tracking (`pipelines/ofac/`), diffed against the
  prior pull (first_seen/last_seen/status), tagged for energy relevance, and
  bridged into the existing `events` lake (Spec 09) so a newly-listed
  energy-related sanction surfaces on page 09's map/feed/table and as an event
  overlay on pages 01/02/06 with no changes needed to `event_overlay.py`.
- `core/schemas.py::SANCTIONS_SCHEMA` and dedicated `core/storage.py`
  read/write (a current-state table, not `_write_partitioned`-shaped).
- Page `15_sanctions.py` — full table, newly-listed-this-week, vessel
  watchlist, delisted panels.

## [0.15] - 2026-09-04
### Added
- Spec 17: Adanos market-sentiment overlay for a 57-ticker energy-complex
  basket (Reddit/X/News/Polymarket buzz + sentiment) on page 10.
### Fixed
- `AdanosClient` no longer raises when `ADANOS_API_KEY` is unset (broke every
  cassette-replay test in CI, which has no real `.env`).

## [0.14] - 2026-09-03
### Added
- Spec 16: NewsAPI.org manual, on-demand search supplement on page 09 —
  deliberately excluded from any scheduled pull (NewsAPI free-tier ToS bans
  production/scheduled use).

## [0.13] - 2026-09-03
### Added
- News page redesign (cross-cutting, on top of Spec 09): a clickable world map
  scoping the event feed/table to a country, a translate button per headline
  (MyMemory-based), and an optional one-sentence "Kardamow take" caption via
  the Anthropic Messages API.
- `events` schema gains a `language` column.
### Fixed
- `core/storage.py`: a schema column absent from every scanned parquet file
  raised a DuckDB Binder Error instead of reading as a typed NULL.
- Map marker click customdata was being indexed like a character array by
  Plotly's click-event JSON round-trip.
- `go.Scattermapbox` never fires Streamlit's `on_select` — switched to
  `go.Scattermap` for the one map that needs click selection.
- A cleared map selection was immediately re-applied by the widget's own
  remembered state — fixed by versioning the widget key.

## [0.12] - 2026-09-02
### Added
- Spec 10: macro/FX normalisation — 35 FRED series, Frankfurter FX,
  Eurostat economic sentiment, `core/macro.py` (`deflate`, `to_currency`,
  `align_freq`, `year_over_year`, `zscore`), page `10_macro.py`.

## [0.11] - 2026-09-02
### Fixed
- Critical: `core/storage.py`'s cross-file parquet glob silently coerced the
  entire `value` column of `ts_long` to `int64` project-wide whenever any one
  source's files were physically int64-typed (Baker Hughes' rig counts) —
  invisible for large-magnitude series, but zeroed out FX rates entirely
  (`fx.usd_eur` read back as exactly `1.0` for every date). Fixed via
  `read_parquet(..., union_by_name=true)` plus an explicit per-column `CAST`
  and a write-side `float64` coercion.

## [0.10] - 2026-09-02
### Added
- Spec 09: news ingestion & event tagging — GDELT DOC 2.0 client, a
  headline-derived tagging engine (multi-tag, severity, geo), fuzzy
  cross-source dedup, `events` lake schema/dataset (this project's first
  list-typed column), page `09_events.py`, and a reusable
  `components/event_overlay.py` wired onto pages 01/02/06.
### Descoped
- A Guardian Open Platform client was built but never live-verified (no
  `GUARDIAN_KEY` set) — gracefully skipped when unconfigured.

## [0.9] - 2026-09-01
### Added
- Spec 08: weather overlay — Open-Meteo HDD/CDD history+forecast for 14
  cities, population-weighted EU/US aggregates, ECMWF Open Data anomaly maps
  (CC BY 4.0), a wind-speed forecast index for DE/DK/IE, `pull_daily.py`.

## [0.8] - 2026-09-01
### Changed
- Dashboard-wide redesign (cross-cutting): explicit locked light theme, every
  chart section wrapped in a bordered `card()` container, maps moved from
  `Scattergeo` to `Scattermapbox` with free OpenStreetMap tiles, a
  segmented-control time-range pill row and a collapsible filter panel added
  to every page.

## [0.7] - 2026-08-31
### Added
- Spec 06: OPEC/global supply monitoring — MOMR Excel + PDF-fallback parsing
  (400+ series, per-country DoC crude production), JODI-Oil top producers,
  Baker Hughes weekly North America rig count, page 06 (production-vs-quota,
  revision waterfall, oil-on-water, US rig count).

## [0.6] - 2026-08-31
### Added
- Spec 05: US natural gas & power — EIA weekly storage (Lower-48 + 7 regions),
  CAISO + NYISO real-time load/fuel-mix/LMP via `gridstatus`, monthly US dry
  gas production + LNG exports, page `05_us_gas_power.py`.

## [0.5] - 2026-08-30
### Added
- Spec 04: ENTSO-E European power + EirGrid — day-ahead prices, generation
  mix, cross-border flows for 13 zones, an Ireland panel (demand-vs-wind, SNSP
  proxy gauge, EWIC/Greenlink flows), `pull_daily.py`, page `04_eu_power.py`.
### Fixed
- `write_flows`'s `replace_window` was dropping every existing row in a
  re-pulled window regardless of which border it belonged to, silently
  deleting still-good data for any border whose fetch failed on a given run.

## [0.4] - 2026-08-30
### Added
- Spec 03: ENTSOG EU gas flows — 8 corridors, 2 years of daily physical
  flows + nominations, a Sankey + corridor small-multiples + directional map,
  the physical-vs-nomination gap chart, `pull_daily.py` with a 15-day revision
  window.

## [0.3] - 2026-08-29
### Added
- Spec 02: GIE AGSI+/ALSI+ EU gas storage — EU + per-country fill/injection/
  withdrawal and LNG send-out history back to 2018, page `02_gas_storage.py`,
  `pull_daily.py` trailing-5-day incremental re-pull.

## [0.2] - 2026-08-23
### Added
- Spec 01: EIA PADD & WPSR — weekly stocks/refining/imports pull, inter-PADD
  crude movement corridors, page `01_us_padd.py`, supplementary page
  `015_us_oil_overview.py`.

## [0.1] - 2026-08-23
### Added
- Spec 00: project setup — core library (`settings`, `schemas`, `storage`,
  `seasonal`, `theme`, `calendars`), the DuckDB + Parquet lake, the `ts_long`/
  `flows` schemas, exclude-2020 seasonal maths, the Kardamow house chart
  template, dashboard shell, `/new-pipeline`/`/new-page` scaffolding, GitHub
  Actions CI.
