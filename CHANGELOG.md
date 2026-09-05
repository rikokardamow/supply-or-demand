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
