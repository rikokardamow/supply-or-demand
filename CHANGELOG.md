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
  `core/CLAUDE.md`'s new incident write-up.
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
