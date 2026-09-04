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
