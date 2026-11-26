# IMPROVE.md: ideas run 01 for `supply-or-demand`

Written 2026-11-21 against origin/main at 98b479a, in the worktree `~/Projects/_improve/supply-or-demand` on `improve/run-01`. Nothing in this file changes code. The items marked "implement in this run: yes" are for the implementer session; everything else is an owner decision and is listed in `PARKING.md` as one line each.

The rules applied are `~/Projects/PROJECT-STARTER.md`: section 1 (the four desk-seat questions), section 3 (the stack), section 6 (data discipline and rights classes A to D) and section 7 (house style v4).

---

## 1. State

### 1.1 Checks run here (all local, cassette playback only)

| Check | Command | Result |
|---|---|---|
| Python deps | `env -u VIRTUAL_ENV uv sync --all-extras` | ok |
| Tests | `env -u VIRTUAL_ENV uv run pytest --record-mode=none` with the five placeholder keys from `.github/workflows/ci.yml` in the environment | **1205 passed, 17 deselected** (the `browser` marker, excluded by `addopts` in `pyproject.toml:199`), 22 warnings, 137.9 s |
| Lint | `env -u VIRTUAL_ENV uv run ruff check .` | All checks passed |
| Types | `env -u VIRTUAL_ENV uv run mypy core pipelines infra apps` | Success: no issues found in 226 source files |
| web deps | `pnpm install --frozen-lockfile` in `web/` | ok, 831 lockfile entries |
| web tests | `pnpm vitest run` | **6 files, 46 passed** |
| web types, lint | `pnpm typecheck`, `pnpm lint` | ok, ok |
| web build | `pnpm build` | **fails**: `Error occurred prerendering page "/api/headlines"`, `NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY must be set` (`web/src/data/supabase/server.ts:22`). With placeholder values it fails one step later, `overview query failed for fut.cl.f01.close: TypeError: fetch failed`, while generating 23 static pages. The build needs a live Postgres; it cannot pass offline. The README's contributor gate (`pnpm typecheck && pnpm lint && pnpm test`) does not include `build`, so this is consistent, but it means no local session can prove the data site builds. |
| site deps, tests | `pnpm install --frozen-lockfile`; `pnpm vitest run` in `site/` | ok, 457 entries; **1 file, 7 passed** |
| site types, lint, build | `pnpm typecheck`, `pnpm lint`, `pnpm build` | ok, ok, ok (2 static routes) |

The lake (`data/lake/`) is empty in this worktree (only `.gitkeep` is tracked), so the README charts cannot be redrawn here; `tests/test_readme_charts.py` draws them from a synthetic lake and passes.

### 1.2 What works

- A real open-data lake: 22 pipeline folders, four validated shapes (`core/schemas.py`), DuckDB over partitioned Parquet with atomic writes (`core/storage.py:190-200`), loud failures (`core/failures.py`), secrets by name only, a cassette secret scan (`tests/test_cassette_secrets.py`).
- Seasonal maths in one module with 2020 excluded by default (`core/seasonal.py:60-64`); no caller overrides `exclude`, and the web's `seasonal` table is computed by the same function at publish time (`core/publish.py` imports `seasonal_stats`). The rule holds.
- The README charts go through `core/paper_style.py` (house look v4), with captions in `.tex` files and a guard test. `STRICT_DESK` is off (`core/paper_style.py:99`), so the desk rules (no legend box, no twin axes, no red or green) are not enforced on them, though the four charts happen to comply.
- 1205 passing tests and a clean mypy on 226 files is a well-kept codebase.

### 1.3 What is stale or wrong

1. **The README's licence table (`README.md:91`) contradicts the owner's own later readings.** It lists GIE AGSI+/ALSI+, ENTSO-E and FRED under "no attribution requirement found in each provider's own documents". The owner's register in `~/Projects/_runs/desk-core/RIGHTS.md` (read 2026-11-01 and 2026-11-20) classes GIE as **d** ("website terms Art 4.2 bar redistribution without written consent"), ENTSO-E as **d** ("re-use only for data on the open re-use list; list not read"), FRED as **d** ("copyright differs per series and the pages are ambiguous"), OPEC MOMR **d**, and `oil-gas-desk/RIGHTS.md` classes Baker Hughes and ENTSOG **d** (terms not read). The README row also says "see each `pipelines/<source>/NOTES.md`", but only 4 of 22 NOTES files mention terms at all (`futures`, `manual_physical`, `social`, `weather`); `pipelines/gie/NOTES.md` has no terms section.
2. **Yahoo Finance closes are on the public API and the public front page.** `pipelines/futures/NOTES.md:330-333`: "Yahoo's terms also restrict redistribution, which is a live question for `data.kardamow.com` -- these rows are published into an anon-readable `serving.series_long`." The question was never answered. `fut.cl.f01.close`, `fut.lco.f01.close`, `fut.ng.f01.close` drive the front-page headline cards (`web/src/app/page.tsx:31-39,124`), `/prices` and `/curves`, and the README's API example (`README.md:69`). Under section 6, terms not read is class **d**: private only.
3. **The sweep publishes every lake source, with no rights filter.** `pipelines/derived/publish_series.py:31-62` walks `lake_sources()` and calls `publish("series_long", ...)` for each; `core/publish.py:36-49` only checks the table name. The "keep licence-restricted EEX series off the serving layer" fix (`2ba04f3` in `~/Projects/energy-dashboard`, squashed into `origin/feat/sd-models` as `5f8af1d`) **is not on origin/main**: `grep -rni eex core pipelines` finds nothing but an EIA process code in a cassette. It holds trivially (no EEX data is ingested on main) and is the only rights guard ever written for this repo.
4. **First prints are overwritten, and the README says the opposite.** `README.md:39`: "revision-aware de-duplication, so a corrected number is a new row". `core/storage.py:236-252` writes `ts_long` with `dedup_subset=["series_id","ts"]`, `sort_col="revision_date"`, then `drop_duplicates(..., keep="last")` at `core/storage.py:182-183`: a revision **replaces** the first print. The lake holds current vintages, which section 6 says cannot score a forecast.
5. **Units are free text.** `core/schemas.py:17` `unit: str`, no vocabulary. The lake and pages use `BCF` and `Bcf`, `mb`, `" mb"` (leading space, `apps/dashboard/pages/19_fundamentals.py:88`), `million barrels`, `MBBL` (thousand barrels, `pipelines/eia_storage_capacity/pull_history.py:28`), `thousand barrels`, `tb/d` (`pipelines/opec_momr/pdf_parser.py:184`), `USD` for a settle whose unit depends on the root (`pipelines/derived/curve.py:66`), `USD/MWh`, `EUR/MWh`, `% full`, `%`, `Posts`. Rule 8 of section 7.2 allows `kb, mb, kb/d, mb/d, Bcf, $/bbl, $/MMBtu, €/MWh, %` and so on.
6. **Dead hosting and CI configuration in a public repo.** `railway.toml:5` starts `streamlit run src/kardamow/app/main.py` and lines 15-28 schedule `scripts.run_ingestors`, `scripts.run_eia_weekly`, `scripts.run_alerts`, `scripts.run_saturday_drop`: none of these paths exist. `.github/workflows/ci.yml` is a live Actions workflow; the owner's global rule is that Actions stays off, and both merges on main carry `[skip ci]`. `infra/README.md:12` and `Makefile:1` describe ci.yml as the thing `make check` mirrors.
7. **House style.** The Streamlit and artifact layers follow their own design system (`DEVELOPMENT.md:66-121`): red `#c0392b` as a data accent (`core/design.py:31`, `core/theme.py:47` colourway), `STATUS_GREEN #1bc47d` (`core/design.py:24`), dual axes (`core/theme.py:188,691`), serif Lora headings, Plotly. Section 7.2 bans red and green, dual axes and serif titles, and section 3 says Plotly cannot match the house look. This is a whole-surface decision, not a fix.
8. **`BAND_YEARS = range(2021, 2026)`** is hard-coded in `apps/exhibits/readme_charts.py:36`. On 1 January 2027 the README charts will compare 2027 against a band that stops a year short, silently. `core/seasonal.py:22-27` documents exactly this failure mode for `default_years()`.
9. **The GIE README chart carries no licence line** (`docs/img/eu_gas_storage.tex`), the other three say "Public domain". Given item 1, there is nothing honest to write there yet.
10. `docs/README.md:9` points at `weather-module-spec.md` at the repo root; the move into `specs/` is committed on `origin/chore/move-weather-spec` and uncommitted in `~/Projects/energy-dashboard`.
11. `README.md:77`: "`infra/` scheduling and deployment" is Windows Task Scheduler (`infra/register_tasks.ps1`); the owner's rule is jobs by hand. Not wrong, but worth knowing the repo assumes a scheduler.

### 1.4 Unmerged work across the local copies (owner decision items)

- `~/supply-or-demand` on `readme-charts`: clean, **nothing local-only** (`git log origin/main..HEAD` empty; the branch is behind origin by 8).
- `~/Projects/energy-dashboard-rebuild` on `chore/move-weather-spec`: one commit `2ecc4a4`, identical to `origin/chore/move-weather-spec`. Already pushed.
- `~/Projects/energy-dashboard` on `feat/lng`: working tree has the **uncommitted move** `weather-module-spec.md` → `specs/weather-module-spec.md` (same change as the commit above). This clone's history was rewritten (the `reword/*` and `rebuild/*` branches; `git merge-base origin/main main` is empty), so `git log origin/main..<branch>` over-counts. Filtering by patch id, the genuinely new work is:
  - **`feat/lng` (also `origin/feat/lng`, 22 real commits, 26 Oct):** Specs 34-40 drafts; Eurostat EU-27 gas balance; DESNZ UK gas balance; EEX primary auctions and EU ETS balance; US LNG exports by destination; JODI-Gas client; LNG, carbon, EU and UK gas pages; the **EEX publish guard** `2ba04f3`. Squashed to 5 commits on `origin/feat/sd-models` (`5f8af1d` carries the guard).
  - `rebuild/oil-demand` = `origin/feat/oil-demand-rebuilt` (2 commits): GDP elasticity of oil demand, Hormuz scenario. `rebuild/rin-mandate` = `origin/feat/rin-mandate-rebuilt` (2 commits): implied RFS mandate. `feat/dash-app` = `origin/feat/dash-app` (6): a Plotly Dash app for the model pages (section 3 says no new UI frameworks).
  - **Local-only, never pushed:** `spec/ibkr-curve` (curve regime, Hormuz, RIN and demand notes; commits `e79b25b` "replace licensed workbook figures with synthetic fixtures" and `825a3eb` "close the licensed-figure leak" mean earlier commits on that branch hold licensed figures: **never push it**), `design/ui-restyle` and `feat/leaflet-maps` (UI restyle plan, Leaflet basemap on OpenStreetMap tiles, vendored Natural Earth boundaries), `docs/specs-34-40`, `feat/specs-36-40`, `backup/pre-reword-systematic`, `docs/spec31b-final-review-notes`, `skills/energy-analyst` (also on origin), seven `archive/pre-cleanup/*` and five `reword/*` branches.
- **Remote branches already public and not on main** (`git rev-list --count origin/main..<branch>`): `docs/readme-and-notes` (2 commits, 47 files, −483 lines: a README and notes tidy that also renames the old "Energy Dashboard" headings), `chore/development-notes` (1), `fix/entsoe-forward-wind-forecast` (1 commit from 2 Sept: pulls wind and solar forecasts on a forward window; a bug fix left behind), `docs/forecasting-roadmap` (1, adds `specs/00_FORECASTING_ROADMAP.md`), `docs/energy-analyst-notes` (1), `chore/move-weather-spec` (1), `feat/sd-models` (5), `feat/dash-app` (6), `feat/oil-demand-rebuilt` (2), `feat/rin-mandate-rebuilt` (2), `skills/energy-analyst` (5), and the rewritten-history branches `feat/lng`, `feat/eu-carbon`, `feat/eu-gas-balance`, `feat/uk-gas-balance`, `feat/oil-demand`, `feat/rin-mandate`, `docs/gas-lng-carbon-mapping` (355 to 384 "ahead" only because their history was rewritten; delete candidates once the squashed versions are merged or closed).

### 1.5 Overlap with the private desk repos (`~/Projects/_runs/`, read only)

`desk-core` owns P-01 pit-store (point-in-time store, that is first prints), P-02 rights-guard, P-06 energy-units, P-07 forecast-ledger, P-12 house-charts. `oil-gas-desk` owns P-04 agency-first-prints, release-day pages, curve and spread tools, balances, nowcasts. `earth-desk` owns the ECMWF anomaly maps. So three things this repo also does now have a private home: the weather anomaly maps (`pipelines/weather/anomaly_maps.py`), the trading analytics layer (specs 18-27: `core/backtest.py`, `strategies.py`, `systematic.py`, `vecm.py`, `curve.py`, pages 18-21) and any model that outputs a direction. What has no private twin and is this repo's reason to exist publicly: the **rights-clean open-data lake with provenance**. The ideas below are ranked on that: a desk person looks at this repo for data they can trust and cite, so rights, vintages and units come before any new page.

---

## 2. Ideas, ranked

### I-01 Rights register and a publish guard, so class-d data cannot reach the public serving layer

- **Problem.** `publish_series.py:31-62` pushes every lake source into anon-readable `serving.series_long`; `core/publish.py` checks the table name only. Yahoo closes are class d by this repo's own note (`pipelines/futures/NOTES.md:330-333`) and are on the public site and in the README API example. The one guard ever written (`2ba04f3`, EEX) never reached main. There is no `RIGHTS.md`.
- **Proposal.**
  1. `core/rights.py`: a frozen dict `SOURCE_CLASS: dict[str, str]` covering **every** lake source id (`eia, derived, gie, entsoe, entsog, opec_momr, open_meteo_forecast, gfs, ecmwf, manual, jodi, gridstatus, fred, frankfurter, eurostat, eirgrid, cftc, baker_hughes, adanos, yfinance, news, gdelt, ofac, ais, social, coal`; the implementer enumerates from `grep -rhoE "write_(ts_long|flows|events)\([^,]+, *(source=)?[\"'][a-z_]+[\"']" pipelines` and the `SOURCE` constants). Classes as this repo has read them: `eia b`, `cftc b`, `ecmwf b`, `gfs a`, `open_meteo_forecast c`, `yfinance d` (NOTES.md:330), `manual d` (`pipelines/manual_physical/NOTES.md:32`: paid commercial licences), `social d` (Reddit; terms not read here), `derived` inherits the class of its inputs via a per-prefix map (`derived.ma.* → yfinance`, `derived.cushing.* → eia`, `derived.curve.* → futures`). Every other source: the class the README table implies (`a`), with `owner_register` column recording the desk-core/oil-gas-desk reading where it differs (`gie d`, `entsoe d`, `fred d`, `opec_momr d`, `baker_hughes d`, `entsog d`). The guard uses the `class` column; the conflicts go to the owner (PARKING), not to the guard.
  2. `RESTRICTED_SERIES: tuple[re.Pattern, ...]` for series-level rules: `^fut\.[a-z]+\.f01\.close$` (Yahoo), `^derived\.ma\.` (Yahoo-derived), `^eex\.`, `^derived\.eu_carbon\.(price|balance)\.` (pre-seeded so `feat/sd-models` slots in).
  3. `core/publish.py::publish()`: after `_check_identifiers`, call `rights.drop_restricted(df, table, pipeline=pipeline)`. A row is dropped if its `source` (column, else the `pipeline` argument) is class `d`, or its `series_id` matches `RESTRICTED_SERIES`. Print one line per table with the count and up to three ids, in the repo's existing style. A source absent from `SOURCE_CLASS` raises `UnregisteredSourceError` **before any SQL**: unknown means unread means d, and the sweep must fail loud rather than publish. An all-dropped frame returns 0 and writes no `publish_log` row (reuse the existing "0 rows written" path).
  4. `RIGHTS.md` at the root, generated by hand from the same dict (a test asserts the table rows and the dict agree): `source | what is used | terms as read here (file:line) | class | owner register class | public surfaces reached (README chart, web, site, API) | credit line`.
  5. `tests/test_rights.py`: the registry covers every source id the pipelines write (collect them by import, not by grep, from the `SOURCE` constants and a list in the test); `RIGHTS.md` and the dict agree; no class-d source id appears in `README.md`, `docs/img/*.tex` or `site/src` (the `web/` references to `fut.*` are reads of the serving layer, not data in the repo, and are listed in PARKING).
- **Desk-seat value.** A public lake a desk can cite without a licence conversation; question 4 (can it be shown) answered for every series.
- **Effort.** 3.5 h.
- **Risk.** After the next `publish`, Yahoo rows stop refreshing and the front-page WTI, Brent and Henry Hub cards go to their empty state (the README promises that state). Rows already in Supabase stay until I-02 is run by the owner. `publish_series` will raise on any source missing from the dict, which is the intended fail-loud.
- **Acceptance test.** `tests/test_publish.py`, using the existing `_FakeConnection`: (a) a frame of 5 `ts_long` rows, 3 with `source="eia"`, `series_id="WCESTUS1"` and 2 with `source="yfinance"`, `series_id="fut.cl.f01.close"` → `publish("series_long", ...)` returns **3**, the COPY payload holds 3 lines, stdout contains `serving.series_long: 2 licence-restricted row(s) not published` and `fut.cl.f01.close`; (b) the 2 yfinance rows alone → returns **0**, no `INSERT INTO serving.publish_log` in the recorded SQL; (c) `source="mystery"` → `UnregisteredSourceError`, recorded SQL empty; (d) a `seasonal` frame with no `source` column and `series_id="fut.ng.f01.close"` → 0 rows; (e) `series_id="derived.ma.cl.50"` with `source="derived"` → dropped by prefix; `series_id="derived.cushing.stocks"` with `source="derived"` → kept. `tests/test_rights.py` as above. `make check` green.
- **Rights impact.** Removes class-d data from the publish path; records every source's class in one place.
- **Implement in this run: yes.** Under 4 h, local, no new source, follows section 6 directly; the only judgement (Yahoo is d) is the repo's own unanswered note.
- **Status: done, `76e5492`** (implementer run-01, 2026-11-21). pytest 1256 passed, 17 deselected; ruff and mypy clean on 227 files. Differences from the proposal above:
  - Terms were read at source on 2026-11-21 ("improve run-01", plain `curl`, pages kept in `.improve/terms/`, not committed). Class b: EIA, coal (EIA), CFTC, ECMWF, GDELT, EirGrid, GFS (read through the NWS disclaimer; NOMADS states no terms). Class c: Open-Meteo, Eurostat (DG ECFIN data may be non-commercial). Class d after reading: NewsAPI (development plan only), Guardian (personal non-commercial use, ads must be shown). Class d, terms not read: Frankfurter, GridStatus (HTTP 403), JODI and OFAC (no re-use statement found), Adanos, AIS, IBKR, manual, Reddit, Polymarket, StockTwits, Yahoo.
  - The six I-06 sources are held at class a (the README reading) with the owner's `d` in the "owner register" column and no read date. That is the one exception to "above d needs terms read"; `tests/test_rights.py` names it.
  - `curve_settles` is refused as well: it is the contract-coded Brent curve reconstructed from a vendor export (`source="manual"`, `pipelines/futures/NOTES.md:199`). `spreads` (EIA ranks) still publishes. The curve test was updated for that.
  - Frames with no `source` column need a `pipeline` label that names a source, or the guard raises; every caller in the repo passes one.
  - `RIGHTS.md` is rendered by `uv run python -m core.rights`, not typed by hand; a test compares the two byte for byte.

### I-02 A dry-run tool that removes already-published restricted rows from the serving layer

- **Problem.** I-01 stops new restricted rows; the 30,859 Yahoo rows already published (`pipelines/futures/NOTES.md:316`) stay anon-readable until deleted. Deleting needs the owner's pooler connection, so the tool must exist and be safe before the owner runs it.
- **Proposal.** `pipelines/derived/unpublish_restricted.py`: for each `RESTRICTED_SERIES` pattern and each class-d source in `core.rights`, count matching rows in `serving.series_long` and `serving.seasonal` (`series_id ~ %s`, `pipeline = %s` via `publish_log` where the table has no source column) and print them. `--apply` runs the `DELETE`s in one transaction and appends a `publish_log` row with `source_note="unpublished N licence-restricted rows"`. Default is dry run. Uses the same `psycopg` connection helper as `core/publish.py`.
- **Desk-seat value.** Completes I-01; the public API is clean, not just the next publish.
- **Effort.** 1.5 h.
- **Risk.** A wrong regex deletes real rows. Mitigation: patterns are shared with I-01 and tested there; `--apply` prints the counts first and refuses when any pattern matches more than one `source` in `publish_log`.
- **Acceptance test.** With `_FakeConnection`: dry run records only `SELECT count(*)` statements and prints `fut\.[a-z]+\.f01\.close: <n> rows in series_long`; `--apply` records one `DELETE FROM serving.series_long WHERE series_id ~ %s` per pattern plus the `publish_log` insert, inside one `commit()`.
- **Rights impact.** Removes class-d data already served.
- **Implement in this run: yes.** Nothing is run against a database here; the owner runs it by hand.
- **Status: done, `2bd2f20`** (implementer run-01). pytest 1269 passed, 17 deselected; ruff and mypy clean on 228 files. **Not executed against any database**; the tests use a fake connection and a small lake frame. Executing it is the owner's call: run the dry run first (`uv run python -m pipelines.derived.unpublish_restricted`, which connects to the pooler URL only to count), read the counts, then `--apply`. Differences from the proposal: it selects by the `source` column and by lake-derived series ids as well as by the series patterns, it also empties `curve_settles`, `vessel_latest` and `sanctions` whole (each is fed by one class d source), and its `publish_log` row reuses the table's latest `as_of` (a row stamped now would reset the staleness badge). The `--apply` safeguard is a per-delete count check with rollback, not the "more than one source in publish_log" test, which the log's schema cannot answer.

### I-03 README and docs: stop claiming what the code does not do

- **Problem.** `README.md:39` claims revisions become new rows (they overwrite, I-05). `README.md:91` claims terms were checked per pipeline and found free (18 NOTES files have no terms section; the owner's register disagrees on six sources). `README.md:69` demonstrates the API with a class-d series. `docs/README.md:9` says NOTES files record terms.
- **Proposal.** Four surgical edits: (a) line 39: "The lake is partitioned Parquet de-duplicated on series and date; a corrected number replaces the earlier one, and the write time is kept in `revision_date`. First prints are not retained yet (see PARKING.md)." (b) line 69: use `series_id=eq.WCESTUS1` (EIA, public domain). (c) line 91: split the row; keep EIA, CFTC, OFAC, Frankfurter, Eurostat, JODI with the wording they earn, and add a row "GIE AGSI+/ALSI+, ENTSO-E, ENTSOG, FRED, OPEC, Baker Hughes, gridstatus, EirGrid: terms read differently in the owner's register; see `RIGHTS.md`, published pending that decision". Add a row for Yahoo Finance: "Redistribution restricted; kept out of the serving layer since <date>". (d) `docs/README.md:9`: "`RIGHTS.md` records each source's terms and class; the per-pipeline `NOTES.md` record what was verified live." Also add `RIGHTS.md` to the Layout paragraph.
- **Desk-seat value.** A reader who checks one claim and finds it false stops reading.
- **Effort.** 1.5 h.
- **Risk.** `origin/docs/readme-and-notes` (unmerged, 47 files) also rewrites the README; the owner may need to resolve a small conflict. Keep edits to the four places above.
- **Acceptance test.** `tests/test_readme_claims.py`: `README.md` does not contain "a corrected number is a new row", does not contain `fut.cl.f01.close`, does contain `RIGHTS.md`; `docs/README.md` contains `RIGHTS.md`. Existing tests green.
- **Rights impact.** Honest public statement of what is published under which terms.
- **Implement in this run: yes.** Pure documentation of facts established above; depends on I-01 for `RIGHTS.md`.
- **Status: done, `e4137d8`** (implementer run-01). pytest 1290 passed, 17 deselected; ruff and mypy clean on 228 files. Edits match the proposal (a) to (d), plus three the new guard forced: the licence table was rewritten from `RIGHTS.md` (read dates, six disputed sources shown as "published pending that decision", Yahoo and the other class d sources listed), the `series_long` and `curve_settles` sentences in "The read API" now say what is actually published, and the contributing paragraph points at `core/rights.py`. `origin/docs/readme-and-notes` still rewrites the same README; expect a conflict there.

### I-04 Compute the README band years from the data

- **Problem.** `apps/exhibits/readme_charts.py:36` `BAND_YEARS = range(2021, 2026)`; subtitles print `BAND_YEARS.start` and `BAND_YEARS.stop - 1`. On 1 January 2027 every README chart silently compares the new year against a band missing 2026. `core/seasonal.py:22-27` already explains why a frozen range is wrong.
- **Proposal.** Replace the constant with `band_years(df) -> range` = `range(last_year - 5, last_year)` where `last_year = df["ts"].max().year`, 2020 still excluded by `seasonal_stats`'s default. Call it in `seasonal_panel` and in each subtitle. Keep five years, as the artifacts design system does.
- **Desk-seat value.** A seasonal exhibit that is right every year without a hand edit; section 6 says 2020 stays out, section 7 says the band is "faint named prior years".
- **Effort.** 1 h.
- **Risk.** Byte-stability test: the PNGs must still be byte-identical for the current fixture, which they will be because the computed range for a series ending in 2026 is 2021..2025, the same as today.
- **Acceptance test.** In `tests/test_readme_charts.py`, `band_years` on the fixture `WCESTUS1` series ending `2026-10-02` returns `range(2021, 2026)` and the caption contains "2021 to 2025"; a second fixture ending `2027-03-05` returns `range(2022, 2027)` and the caption contains "2022 to 2026" and the band does not include 2020 (assert `"2020" not in stats.columns` from `seasonal_stats`). Existing byte-identity test unchanged and green.
- **Rights impact.** None.
- **Implement in this run: yes.**
- **Status: done, `fce07ad`** (implementer run-01). pytest 1295 passed, 17 deselected; ruff and mypy clean on 228 files. `BAND_YEARS` is gone; `band_years(df)` and a five-year `BAND_SIZE` replace it, and the tests include the hand-worked 2027 case. `docs/img/*` were not redrawn (no lake here); the 2026 output is unchanged because the computed range is the same. One caveat left as is: a frame ending in 2025 or earlier has 2020 inside the five-year window, so its caption would read "2020 to ...", with 2020 left out of the maths by `seasonal_stats`.

### I-05 Keep first prints: a vintage-aware lake

- **Problem.** `core/storage.py:236-252` and `182-183`: a re-pull with a revised value replaces the row for `(series_id, ts)`. WPSR, EIA-930, OPEC secondary sources, JODI and CFTC all revise. Section 6: "A revised series can't score a forecast made before the revision." The README claims the opposite (I-03 corrects the words; this corrects the behaviour).
- **Proposal.** `write_ts_long` de-duplicates on `["series_id", "ts", "value"]` (an unchanged re-pull adds nothing; a changed value adds a row with its own `revision_date`). `read_ts_long(..., vintage="latest")` default selects one row per `(series_id, ts)` with `qualify row_number() over (partition by series_id, ts order by revision_date desc) = 1`; `vintage="first"` picks the earliest; `vintage="all"` returns everything; `as_of=<datetime>` picks the latest revision at or before that time. `publish()` keeps upserting the latest, so the serving layer is unchanged. A `tools/vintages_report.py` lists series with more than one vintage.
- **Desk-seat value.** The one property that makes a public lake useful to a desk: you can reconstruct what was known on a date. Question 3 (scored live) is impossible without it.
- **Effort.** 6 to 8 h (readers, publishers, 20 or so tests touch `read_ts_long`).
- **Risk.** Every reader assumes one row per `(series_id, ts)`; the default must stay "latest" to keep pages correct. The owner's existing lake has already lost past vintages; this only preserves future ones.
- **Acceptance test.** Write `(s, 2026-10-01, 100.0, rev 2026-10-02)`, then `(s, 2026-10-01, 101.0, rev 2026-10-09)`, then `(s, 2026-10-01, 101.0, rev 2026-10-16)`: `vintage="all"` has **2** rows; `latest` gives 101.0; `first` gives 100.0; `as_of=2026-10-05` gives 100.0.
- **Rights impact.** None.
- **Implement in this run: no.** Over 4 h, and `desk-core` P-01 pit-store is being built for the same job; the owner decides whether vintages live here, there, or both.

### I-06 Resolve the six sources whose terms the owner's register reads as class d

- **Problem.** GIE, ENTSO-E, ENTSOG, FRED, OPEC MOMR and Baker Hughes are on the public API, GIE is also in a README chart with no licence line (`docs/img/eu_gas_storage.tex`) and on the web front page (`web/src/app/page.tsx:40,125`). `desk-core/RIGHTS.md` reads GIE's Art 4.2 as barring redistribution without consent and notes the API manual was not read.
- **Proposal.** Per source, one of: read the API terms properly and record the reading in `RIGHTS.md` with a date (GIE's AGSI+ API documentation has its own terms page; ENTSO-E's open re-use list is a published document); ask GIE for written consent for a non-commercial, attributed, derived chart; or mark the source d in `core/rights.py`, which (with I-01 in place) takes it off the serving layer and out of the README at the next publish and redraw.
- **Desk-seat value.** Decides whether the EU gas storage exhibit, the project's best chart, can be public.
- **Effort.** 2 to 4 h of reading per source, plus any wait for consent.
- **Risk.** None technical.
- **Acceptance test.** `RIGHTS.md` row for each source has a "read on" date and the terms URL; `tests/test_rights.py` passes with the chosen class.
- **Rights impact.** The whole point.
- **Implement in this run: no.** Needs the owner to read licences and choose.

### I-07 Replace Yahoo on the public pages with EIA spot prices

- **Problem.** After I-01 the front-page cards and `/prices`, `/curves` for WTI, Brent and Henry Hub have no public-domain source. The lake holds no EIA daily spot (`pipelines/eia/pull_prices.py` pulls landed cost, citygate and generator fuel; `grep RWTC pipelines/eia` is empty). FRED's `dcoilwtico`, `dcoilbrenteu`, `dhhngsp` exist but FRED is d in the owner's register.
- **Proposal.** Add `petroleum/pri/spt` daily series `RWTC` (WTI Cushing), `RBRTE` (Brent), and `natural-gas/pri/fut` or the Henry Hub spot `RNGWHHD` to `pipelines/eia/pull_prices.py` as a `DAILY_GROUPS` entry with ids `eia.spot.wti`, `eia.spot.brent`, `eia.spot.hh`, record cassettes with the key read by name from `~/energy-forecasting/.env`, and switch `web/src/app/page.tsx`, `curves/page.tsx`, `prices/[root]/page.tsx`, `TickerPanels.tsx` from `fut.<root>.f01.close` to those ids. Label them "spot", not "front month".
- **Desk-seat value.** A public price panel that can be cited; spot against stocks is the balance chart a desk expects.
- **Effort.** 4 to 5 h including cassettes.
- **Risk.** Needs a live EIA key to record the cassettes; the route names must be verified live, never guessed (DEVELOPMENT.md rule).
- **Acceptance test.** Cassette test: three series, latest `ts` within 7 days of the recording date, units `$/bbl`, `$/bbl`, `$/MMBtu`. `grep -rn "fut\." web/src` returns nothing outside the curve pages that read `curve_settles`.
- **Rights impact.** Replaces class-d prices with public domain.
- **Implement in this run: no.** Needs a key and live route verification; spot versus front-month is also a presentation choice for the owner.

### I-08 One unit vocabulary, applied at ingest

- **Problem.** Item 5 in section 1.3: twelve spellings for five quantities, `MBBL` meaning thousand barrels, `USD` with no denominator, a leading space. Section 6: units are fixed at ingest; section 7.2 rule 8 lists the allowed spellings.
- **Proposal.** `core/units.py`: `ALLOWED = {"kb","mb","kb/d","mb/d","Bcf","Bcf/d","$/bbl","$/MMBtu","€/MWh","$/MWh","$/gal","%","days","contracts","index","°F","°C","HDD","CDD","TWh","GW","GWh","GWh/d","MW","percentile","weeks","rigs","posts","ratio"}` and `NORMALISE = {"BCF":"Bcf"," mb":"mb","million barrels":"mb","MBBL":"kb","thousand barrels":"kb","tb/d":"kb/d","USD/MWh":"$/MWh","EUR/MWh":"€/MWh","% full":"%","degree-days": None}` (None means the writer must choose HDD or CDD). `validate_ts_long` and `validate_flows` reject a unit outside `ALLOWED`; `write_ts_long` applies `NORMALISE` first. `pipelines/derived/curve.py:66` sets the unit per root (`cl, lco, ho, rb → $/bbl` after the products × 42 rule; `ng → $/MMBtu`). A one-off `tools/rewrite_units.py` rewrites the owner's existing lake partitions and `apps/exhibits/readme_charts.py:86`'s `unit = 'MBBL'` filter.
- **Desk-seat value.** A number without a fixed unit is not a number a desk can use.
- **Effort.** 5 to 6 h with the lake rewrite and page labels.
- **Risk.** The owner's lake has `MBBL` rows that readers filter on; the rewrite must run before the pages change. `desk-core` P-06 energy-units has a conversion module whose spellings this should match (`~/Projects/_runs/desk-core/research/src/desk_core/units.py`).
- **Acceptance test.** `validate_ts_long` on a frame with `unit="BCF"` raises after normalisation is skipped and passes with `Bcf` after `write_ts_long`; `convert`-free: `MBBL` → `kb`, `tb/d` → `kb/d`; `curve.py` emits `$/MMBtu` for `ng` and `$/bbl` for `ho`. A test that every literal `unit=` in `pipelines/` and `apps/` is in `ALLOWED`.
- **Rights impact.** None.
- **Implement in this run: no.** Over 4 h and rewrites the owner's lake; the repo's artifact design system also spells units out ("424.5 million barrels"), which the owner must reconcile with rule 8.

### I-09 Remove the dead hosting config and the Actions workflow

- **Problem.** `railway.toml` starts and schedules modules that do not exist (`src/kardamow/app/main.py`, `scripts.run_*`): a reader who tries it gets a crash, and it advertises hosted schedulers in a repo whose rules say local, by hand. `.github/workflows/ci.yml` is a live workflow in a public repo; the owner's global rule is that Actions stays off, and `[skip ci]` is already on every merge. `.gitignore:43-46` keeps a rule its own comment says never matched.
- **Proposal.** Delete `railway.toml` and `.github/workflows/ci.yml` (and the empty `.github/` dir). `Makefile:1-3` comment: "`make check` is the gate; run it before every merge." `infra/README.md:12-15`: replace the "stays exactly as it is" paragraph with "There is no CI; `make check` runs locally before every merge." `DEVELOPMENT.md` Commands section likewise. Drop `.gitignore:43-47` (`manual_settlements/*`) and the duplicate `*.log` line. Leave `CHANGELOG.md` alone (history).
- **Desk-seat value.** A repo that does what its rules say.
- **Effort.** 1 h.
- **Risk.** Low. The infra README decision paragraph is from the Windows-laptop era; the owner may prefer to keep a CI that never runs, but the global rule is explicit.
- **Acceptance test.** `git ls-files .github railway.toml` is empty; `grep -rn "ci.yml" Makefile DEVELOPMENT.md infra/README.md docs` is empty; `make check` green.
- **Rights impact.** None.
- **Implement in this run: yes.**
- **Status: done, `013e318`** (implementer run-01). pytest 1299 passed, 17 deselected; ruff and mypy clean on 228 files (`make check` green); web vitest 46 passed and site vitest 7 passed, typechecks clean. `railway.toml` and `.github/workflows/ci.yml` are deleted on the branch (nothing ran or triggered), `Makefile`, `infra/README.md`, `infra/run_scheduled.py` and `DEVELOPMENT.md` say there is no CI, and `.gitignore` lost the dead `manual_settlements` rule and the duplicate `*.log`. `tests/test_repo_hygiene.py` holds it. Historical specs and `CHANGELOG.md` still mention both files; they are history and were left alone. `make check` needs the five required keys set to any placeholder (the deleted workflow used to supply them), now said in the Makefile.

### I-10 Make the data site buildable without a database, or say that it cannot be

- **Problem.** `pnpm build` in `web/` cannot pass offline (section 1.1): 23 pages prerender from Supabase, and `/api/headlines` throws when the env is unset. Section 3 wants static export with Python writing JSON; this app is server-rendered against Postgres.
- **Proposal.** Either (a) owner keeps Supabase SSR and the README states that `pnpm build` needs `.env.local` and a reachable serving layer; or (b) move to section 3's shape: `pipelines/derived/export_web_json.py` writes `web/public/data/*.json` from the lake, `next.config.ts` gets `output: "export"`, the two API routes go, pages read JSON at build time. (b) also retires Supabase and the RLS migrations.
- **Desk-seat value.** (b) makes the whole stack run from one laptop with no hosted service, which is the owner's stated model; (a) is honest.
- **Effort.** (a) 0.5 h; (b) 12 to 20 h.
- **Risk.** (b) is a rewrite of `web/src/data/*`.
- **Acceptance test.** (a) README contributor paragraph names the requirement; (b) `pnpm build` passes offline and `web/out/` exists.
- **Rights impact.** (b) makes the publish guard (I-01) the only gate between lake and public, which is simpler to audit.
- **Implement in this run: no.** Owner choice.

### I-11 Bring the dashboards to house style v4, or declare the Streamlit layer legacy

- **Problem.** Red `#c0392b` as a data colour (`core/design.py:31`, `core/theme.py:47,215,559,723,854`), `STATUS_GREEN` (`core/design.py:24`), dual axes (`core/theme.py:188,691`), Lora serif headings, Plotly throughout. `DEVELOPMENT.md:66-121` makes these the rule. Section 7.2 bans each; section 3 says Plotly cannot match the house look.
- **Proposal.** Owner picks one: (a) `core/design.py` takes its values from a `house_style.json` (section 7.4), red and green go, `STATUS_*` become `state_hit/state_miss` used only on scored results, dual-axis builders become stacked panels, headings go sans; or (b) the Streamlit app and `apps/artifacts` are marked legacy in the README, and new exhibits go through `core/paper_style.py` only, with `STRICT_DESK = True` set in `apps/exhibits/readme_charts.py`.
- **Desk-seat value.** One look across the public repo and the private desks.
- **Effort.** (a) 10 to 15 h; (b) 1 h.
- **Risk.** (a) touches 17 pages and the artifact templates.
- **Acceptance test.** (a) `grep -rn "c0392b\|1bc47d\|yaxis2\|overlaying" core apps` is empty; `tests/test_design_tokens.py` reads `house_style.json`. (b) `ps.STRICT_DESK is True` inside `readme_charts.main()` and the four charts pass `ps.lint`.
- **Rights impact.** None.
- **Implement in this run: no.** Owner choice; the repo's own design system is documented and deliberate.

### I-12 Merge or close the unmerged branches

- **Problem.** Section 1.4: a bug fix from 2 September (`fix/entsoe-forward-wind-forecast`), a docs tidy that removes 483 lines of stale wording, the weather-spec move, a forecasting roadmap, the EEX guard and four data sources (`feat/sd-models`), two model pages, and seven rewritten-history branches, all public on origin and none on main. The `energy-dashboard` clone has no merge base with origin/main.
- **Proposal.** In this order: merge `fix/entsoe-forward-wind-forecast` (read the diff first, it changes `pull_daily.py`'s window), `chore/move-weather-spec` then fix `docs/README.md:9`, `docs/readme-and-notes` after I-03 (resolve the README conflict by hand), `docs/forecasting-roadmap`, `docs/energy-analyst-notes`. Decide on `feat/sd-models` (needs I-01's registry rows for `eurostat_gas`, `desnz_gas`, `eex`, `jodi_gas`), `feat/oil-demand-rebuilt`, `feat/rin-mandate-rebuilt` (models: candidates to move to the private desks), `feat/dash-app` (a second UI framework; section 3 says no). Delete the rewritten-history branches `feat/lng`, `feat/eu-carbon`, `feat/eu-gas-balance`, `feat/uk-gas-balance`, `feat/oil-demand`, `feat/rin-mandate`, `docs/gas-lng-carbon-mapping` once their squashed twins are decided. Never push `spec/ibkr-curve`. Commit or discard the uncommitted move in `~/Projects/energy-dashboard`, then treat that clone as an archive.
- **Desk-seat value.** The repo's main reflects its best state.
- **Effort.** 3 to 6 h of owner time.
- **Risk.** Conflicts; `[skip ci]` on every merge until I-09 lands.
- **Acceptance test.** `git branch -r | wc -l` falls from 26 to under 10; `git log origin/main..origin/fix/entsoe-forward-wind-forecast` empty.
- **Rights impact.** `feat/sd-models` brings EEX data; I-01's pre-seeded prefixes cover it.
- **Implement in this run: no.** Merging the owner's work is the owner's decision.

### I-13 Retire what the private desks now own

- **Problem.** Section 1.5: the trading analytics layer (specs 18-27, `core/backtest.py`, `strategies.py`, `systematic.py`, `vecm.py`, pages 18-21, `specs/TRADING_LAYER_RUNBOOK.md`), the GRP geopolitical module (specs 28.*), and the weather anomaly maps duplicate work in `oil-gas-desk`, `desk-core` and `earth-desk`. In a public repo, model code without a scored live record is also what section 6 warns against ("a baseline is never called alpha").
- **Proposal.** Owner lists what stays public (the lake, the publish layer, the README exhibits, the Streamlit explorer of raw series) and what moves or is deleted. Deleted specs become one line each in `CHANGELOG.md`.
- **Desk-seat value.** The public repo makes one claim, "trustworthy open data", and nothing it cannot back.
- **Effort.** 2 h to decide, 4 to 8 h to carry out.
- **Risk.** Losing tests that exercise `core/storage.py` indirectly; check coverage before deleting.
- **Acceptance test.** `ls specs | wc -l` and `ls apps/dashboard/pages | wc -l` fall to the agreed numbers; `make check` green.
- **Rights impact.** Fewer surfaces to audit.
- **Implement in this run: no.** Owner choice.

### I-14 Record release time, not only pull time

- **Problem.** `revision_date` is `pulled_at` (`pipelines/eia/client.py:179,291,375`), the wall clock of the pull. Section 6 wants every release recorded as issued with its timestamp; `core/calendars.py` already knows WPSR is Wednesday 10:30 ET. Without a release timestamp, "was this known at 10:31?" cannot be answered.
- **Proposal.** Add `released_at` (nullable) to `ts_long`; the EIA WPSR, gas storage and CFTC pulls fill it from `core/calendars.py`; other sources leave it null. Depends on I-05 for it to mean anything.
- **Desk-seat value.** Release-day scoring (oil-gas-desk Q-003, Q-004) needs this column from the public lake.
- **Effort.** 3 to 4 h after I-05.
- **Risk.** Schema change; DEVELOPMENT.md rule 7 says ask first.
- **Acceptance test.** A WPSR row for period 2026-10-02 has `released_at = 2026-10-07 14:30 UTC` (Wednesday 10:30 ET), computed by `calendars`, and a row for a holiday week uses the Thursday rule.
- **Rights impact.** None.
- **Implement in this run: no.** Schema change and depends on I-05.

---

## 3. Order for the implementer

Work on `improve/run-01` only; do not push. Run `make check` after each item; record the counts in the commit message.

1. **I-01** rights register and publish guard (`core/rights.py`, `RIGHTS.md`, `core/publish.py`, `tests/test_rights.py`, `tests/test_publish.py`). Enumerate every lake source before writing the dict; a missing source must fail the new test, not be guessed.
2. **I-02** `pipelines/derived/unpublish_restricted.py`, dry run by default. Do not run it.
3. **I-03** README and `docs/README.md` corrections, plus `tests/test_readme_claims.py`.
4. **I-04** `band_years()` in `apps/exhibits/readme_charts.py` and its tests. Do not redraw `docs/img/*` (no lake here).
5. **I-09** delete `railway.toml`, `.github/workflows/ci.yml`; fix the three comments; tidy `.gitignore`.

Expected end state: pytest count rises from 1205 by the new tests; ruff and mypy clean; web and site vitest unchanged (46 and 7). Commit identity: `git -c user.name=rikokardamow -c user.email=236246648+rikokardamow@users.noreply.github.com commit -m "..."`. Never `git add -A`; `.improve/`, `node_modules/` and `.next/` are not part of any commit.

Yes items: I-01, I-02, I-03, I-04, I-09 (five). Everything else is in `PARKING.md`.

---

## Round 2 (26 Nov 2026)

Written against `improve/run-01` at `3884a77` (round 1 plus its five implemented items). Checks run here: `EIA_API_KEY=x EMBER_API_KEY=x GIE_API_KEY=x ENTSOE_API_KEY=x FRED_API_KEY=x env -u VIRTUAL_ENV uv run pytest -q`: **1299 passed, 17 deselected**, 97 s, the same count round 1 ended on. Every failing input below was run in this worktree against the current code (throwaway scripts outside the repo); nothing in the repo was changed except this section.

### (a) Re-triage of round 1's "no" items

I-01, I-02, I-03, I-04 and I-09 are done and are not re-opened. I-02 is built but has not been run. Running it is the owner's job and is already in `PARKING.md`.

- **I-05 first prints:** still the owner's call. The owner must decide where vintages live: in this lake (`core/storage.py:182-183` changed to keep every changed value), in `desk-core` P-01 pit-store only, or in both.
- **I-06 the six disputed sources:** still the owner's call. For each of GIE, ENTSO-E, ENTSOG, FRED, OPEC MOMR and Baker Hughes, the owner must either read the terms and record a class, or mark it d in `core/rights.py`. GIE also decides whether the EU gas storage README chart stays up (I-15 below takes the screenshot down, but not this chart).
- **I-07 EIA spot in place of Yahoo:** partly doable now. The pipeline half can be done without the owner: add `RWTC`, `RBRTE` and `RNGWHHD` to `pipelines/eia/pull_prices.py` and record one cassette with a live EIA key read by name. That needs a live call, but no money and no decision. Switching the pages is still the owner's call: they must decide whether the front page shows EIA daily spot labelled "spot" in place of a front-month futures close.
- **I-08 unit vocabulary:** still the owner's call for the lake. The owner must approve rewriting the existing lake partitions (`MBBL` to `kb` and so on) and decide whether the artifact layer's spelled-out units ("million barrels") give way to rule 8. The README exhibits' units can be fixed now (I-21 below).
- **I-10 the web build:** the fact can be written down now. One README sentence can say that `pnpm build` in `web/` needs `web/.env.local` and a reachable serving layer, which round 1 measured. Choosing between keeping Supabase SSR and moving to a static export is still the owner's call.
- **I-11 house style on the dashboards:** still the owner's call: restyle, or mark as legacy. The decision now also has to cover `web/`, which uses `--red: #ff5a4d` for deficits (`web/src/components/tables/HeatTable.tsx:158`), red and green delta chips (visible in `docs/screenshots/data-overview.png`) and Plotly (`web/src/theme/plotly.ts:17`). Option (b)'s `STRICT_DESK` half no longer needs the owner: all four README charts pass `ps.lint(..., axis_labels=True)` with `STRICT_DESK = True` today (run here), so it is I-21 below.
- **I-12 unmerged branches:** still the owner's call. The owner must decide, in order: merge `fix/entsoe-forward-wind-forecast` (after reading its window change), `chore/move-weather-spec`, `docs/readme-and-notes` (README conflict with I-03), `docs/forecasting-roadmap` and `docs/energy-analyst-notes`. Then decide on `feat/sd-models`, the two `*-rebuilt` model branches and `feat/dash-app`, and delete the seven rewritten-history branches.
- **I-13 retire what the private desks own:** still the owner's call. The owner must list which of the trading layer (specs 18-27), the GRP module (specs 28.*) and the weather anomaly maps stay public.
- **I-14 `released_at`:** still the owner's call. It depends on I-05, and it is a schema change, which `DEVELOPMENT.md:16` (rule 7) says to ask about first.

### (b) New items, ranked by value

#### I-15 Take the dashboard screenshot out of the README: it shows Yahoo (class d) prices on the public front page

- **Why.** `README.md:35` embeds `docs/screenshots/data-overview.png`. The image shows the Yahoo front-month closes, which `core/rights.py:347-353` classes d and the README's own licence table says are "kept out of the serving layer". The headline cards read WTI 95.62, Brent 100.56 and Henry Hub 2.85, and a "Brent and WTI, front-month close" chart sits under them. The screenshot also carries red and green delta chips and sparklines (banned by PROJECT-STARTER 7.2 rule 4), the units `USD/bbl` and `MBBL` (rule 8), and a "PRIMARY SOURCES ONLY" badge that is false for Yahoo. Section 6 and rule 10: a chart drawn from class d data lives only under `.local/`. The guard from I-01 stops new rows reaching the serving layer, but this picture is the same data, committed and displayed on the repo's front page. The file is referenced nowhere else (`grep -rn data-overview` finds only `README.md:35`).
- **Exact change.** Delete the two README lines "The dashboard itself, as served:" and the image line (`README.md:33-35`). `git rm docs/screenshots/data-overview.png`; the copy in history stays, because pushed history is never rewritten. `docs/screenshots/site-landing.png` is referenced nowhere; leave it alone. In `tests/test_readme_claims.py`, add `test_the_readme_shows_no_screenshot_of_class_d_data`: `"data-overview.png" not in README` and `not (ROOT / "docs/screenshots/data-overview.png").exists()`. Add one line to `PARKING.md`: "Retake a dashboard screenshot for the README once I-07 (or another public-domain price) feeds the headline cards and I-11 settles the colours."
- **Acceptance.** `grep -n "screenshots/" README.md` returns nothing; `git ls-files docs/screenshots` lists only `site-landing.png`; the new test passes; pytest is at 1300 or more passed.
- **Risk.** The README loses its only picture of the web app. That is the honest state until I-07 lands.
- **Implement in this run: yes.** It applies section 6 and rule 10 directly, with no decision about any source's class: Yahoo is already d in this repo's own register.
- **Status: done in ce24921. `pytest -q`: 1300 passed, 17 deselected; `ruff check`: All checks passed. `git ls-files docs/screenshots` lists only `site-landing.png`; `grep -n "screenshots/" README.md` is empty. PARKING.md has the retake line.**

#### I-16 Seasonal bands have no value before each year's first report: the README crude chart raises `KeyError` on the 2027-01-01 report, and the January "median" comes from one year

- **Why.** `core/seasonal.py:51-56` (`_daily_ffill_by_year`) forward-fills inside each calendar year only. A weekly series is therefore NaN from 1 January until that year's first report, and `pivot_table` drops a day of the year that no band year covers. WPSR weeks end on Fridays. 2027-01-01 is a Friday, so the week ending 1 January 2027 (released 6 January 2027, about six weeks from now) is the first report of 2027. Its band years 2022 to 2026 first report on Jan 7, 6, 5, 3 and 2, so day 1 is missing from the band.
  - Run here on a W-FRI series from 2021-01-01 to 2027-01-01: `seasonal_stats(..., years=range(2022, 2027))` has a minimum day of 2, and `readme_charts.seasonal_panel` raises `KeyError: 1` at `apps/exhibits/readme_charts.py:156`. `uv run python -m apps.exhibits.readme_charts` would then fail on its first chart for that whole week.
  - The same gap reaches public numbers. `pipelines/eia/wpsr_lines.py:119-122` returns `vs_median_pct = None` when the day is missing. With the default 2018-2026 window, day 1 is covered only by 2021, whose first report fell on 1 January 2021, so the published "median" for that week is one year's value.
- **Exact change.** In `core/seasonal.py`, add `CARRY_DAYS = 14`. In `_daily_ffill_by_year`, find the last observation of the previous calendar year. If it lies no more than `CARRY_DAYS` before 1 January, include it as the seed of the reindex and forward-fill, then keep only this year's daily grid. The level then holds from the last December report until the first January one, which is how the module already treats every other gap between reports. Nothing changes after a year's first report, and nothing is bridged across a real gap longer than 14 days.
- **Acceptance.** All three use synthetic W-FRI data from 2021-01-01 to 2027-01-01, with every observation in year *y* valued `y - 2000` (21 to 27).
  - (a) `seasonal_stats(df, "value", years=range(2022, 2027))` has 1 in its index. The day-1 values for 2022 to 2026 are carried from 2021-12-31 (21), 2022-12-30 (22), 2023-12-29 (23), 2024-12-27 (24) and 2025-12-26 (25), so the day-1 median is **23.0**, `lo` is **21.0** and `hi` is **25.0**.
  - (b) `readme_charts.seasonal_panel` on the same frame returns **(27.0, 23.0)** instead of raising.
  - (c) A series with a 30-day gap over the new year (last obs 2025-12-02, first 2026-01-15) still has NaN for 2026 days 1 to 14.
  - The existing `tests/test_seasonal.py` and `tests/test_publish_seasonal.py` stay green. Re-run them first; any change to a non-January value is a bug in the change.
- **Risk.** `serving.seasonal` and `wpsr_lines` gain values on the first days of January where they had NaN or one year. No existing non-NaN value moves. For a series whose last December report falls in 2020, the 2021 grid starts from a 2020 level until 2021's first report. That is the level that held at the time, not a 2020 norm, but worth knowing.
- **Implement in this run: yes.** It fixes a crash that comes due on a known date, and no published number other than a missing one changes.

#### I-17 `inventory_deviation` puts the year it measures into its own benchmark: the published `derived.inv.dev_z.uscrude` is understated

- **Why.** At `core/fundamentals.py:24`, `years_range = range(current_year - years, current_year + 1)` includes the current year. Lines 27-30 then take `mean` and `std` over every year column, the current one among them, and `min`/`max` are `seasonal_stats`' `lo`/`hi`, which include it too. `core/seasonal.py:14-17` names exactly this error ("folding it into the band's own lo/hi/median would let it move the very benchmark it is measured by"), and `core/publish.py:seasonal_rows` avoids it with two calls.
  - The z-score is written to the lake as `derived.inv.dev_z.uscrude` (`pipelines/derived/fundamentals.py:62`). It traces to EIA, so it is class b and published to `serving.series_long` by the sweep. Page 19 shows it as "Latest deviation z-score (ex-2020)" (`apps/dashboard/pages/19_fundamentals.py:94`).
  - Run here on the repo's own test fixture (2022 to 2026 at 398, 402, 400, 401 and 405): it returns mean **401.2**, max **405.0** (the current value itself), dev 3.8 and dev_z **1.468**.
  - Excluding 2026 gives mean 400.25, std (ddof 1) √(8.75/3) = 1.7078, dev 4.75 and dev_z **2.781**. The published z is about half what it should be, and a record level can never sit above the band's max.
  - The existing test (`tests/test_core_fundamentals.py:40`) asserts `mean ≈ 401.2, abs=1.0`, so it passes either way. `pipelines/derived/fundamentals.py` has no test at all.
- **Exact change.** In `inventory_deviation`, compute the band from `seasonal_stats(df, "value", years=range(current_year - years, current_year), exclude=exclude)`. Take `mean`, `std`, `min` and `max` from those prior-year columns only. Read `value` (the current track) from a second call whose range is stretched to `current_year + 1`, the pattern `seasonal_rows` uses. Fix the docstring ("across the included years" becomes "across the `years` years before the latest, 2020 excluded"). Add `tests/test_derived_fundamentals.py`: write a synthetic `WCESTUS1` to a temp lake (the `tmp_lake` pattern in `tests/test_derived_cushing.py`), run `_pull_inventory_deviation`, and read `derived.inv.dev_z.uscrude` back.
- **Acceptance.** On the existing fixture, at `result.index[100]`: mean **400.25**, min **398.0**, max **402.0**, dev **4.75**, dev_z **2.781** (±0.001). Tighten the existing assertion from `401.2 abs=1.0` to `400.25 abs=1e-9`. The std-zero test still yields all-NaN dev_z. The new pipeline test reads back 2026 rows whose last value is 2.781 ± 0.001, unit `z-score`.
- **Risk.** The next `derived_fundamentals` run rewrites the current year's `derived.inv.dev_z.uscrude` rows with larger magnitudes, and the next sweep publishes them. It is not a frozen or pre-registered number; `specs/19_fundamentals-physical.md` records no score against it. Say so in the commit message.
- **Implement in this run: yes.**

#### I-18 Close the rights hole in derived curve series: class d settles would publish as class b

- **Why.** At `core/rights.py:384`, `^derived\.(spread|curve)\.` maps to `("eia",)` for every root. But `pipelines/derived/curve.py:30-40` builds `derived.spread.<root>.*` and `derived.curve.<root>.*` from `fut.<root>.<contract>.settle` read from every source partition. Contract-coded settles come only from `manual` (vendor export) or `ibkr`, both class d. `pipelines/derived/curve.py` is scheduled (`infra/run_scheduled.py:52`).
  - Run here: `series_class("derived", "derived.spread.lco.s12")` returns **"b"**, and `drop_restricted` keeps a `derived.spread.lco.s12` row.
  - It writes nothing today only because no `series_meta` rows exist (`pipelines/derived/curve_ranks.py:17-20` and the comment at `core/rights.py:382-383`). The first manual-CSV or IBKR pull (`pipelines/futures/pull.py:51` writes `series_meta`) would put a vendor-derived Brent curve on the public API with no warning.
- **Exact change.**
  1. Narrow the derived map to what the EIA ranks cover: `re.compile(r"^derived\.(spread|curve)\.(cl|rb|ho|hu)\.")` mapping to `("eia",)`. These are the roots in `curve_ranks.RANK_ROOTS`; a test asserts the two agree. Any other root then matches nothing and is class d by the existing rule.
  2. In `pipelines/derived/curve.py::pull_root`, after reading the panel, look up `core.rights.SOURCE_CLASS` for the `source` of the settle rows. If any is class d, write nothing for that root and print `<root>: settles come from class d source(s) [...]; derived curve rows not written (RIGHTS.md)`. This keeps class d inputs out of the shared `derived` partition, and also stops curve.py and curve_ranks.py from writing the same ids from different data, which `curve_ranks.py:17-20` warns about.
  3. Regenerate `RIGHTS.md` with `uv run python -m core.rights`.
- **Acceptance.**
  - `series_class("derived", "derived.spread.lco.s12") == "d"`, `series_class("derived", "derived.curve.lco.regime") == "d"` and `series_class("derived", "derived.spread.cl.s12") == "b"`.
  - A temp lake with `fut.lco.z2026.settle` and `fut.lco.f2027.settle` under `source=manual`, plus two `series_meta` rows: `curve.pull_root("lco", meta, ts)` returns **0** and nothing is written under `source=derived`.
  - With `SOURCE_CLASS` monkeypatched so `manual` is `"b"`, the same call returns more than 0.
  - `tests/test_rights.py` passes, comparing the regenerated `RIGHTS.md` byte for byte.
- **Risk.** None today, since no row changes. If the owner later wants a private Brent curve in the lake, that is a separate id namespace, and their call.
- **Implement in this run: yes.** It enforces the class the register already gives `manual` and `ibkr`.

#### I-19 Daily seasonal charts crash for all of 2028: 29 February reaches `replace(year=2001)`

- **Why.** At `apps/exhibits/readme_charts.py:121-122`, the current-year track is passed to `seasonal._normalised_doy`, which does `d.replace(year=2001)` (`core/seasonal.py:37`). `seasonal_stats` drops 29 February from the band, but nothing drops it from the track.
  - Run here on a daily series from 2022-01-01 to 2028-03-05: `seasonal_panel` raises `ValueError: day 29 must be in range 1..28 for month 2 in year 2001`. The EU gas storage README chart (daily AGSI+) therefore cannot be drawn from 29 February 2028 to 31 December 2028.
  - The same open-coded `replace(year=2001)` is in `apps/dashboard/pages/08_weather.py:99,116,124` (daily HDD, also a crash), `05_us_gas_power.py:93`, `015_us_oil_overview.py:80`, `01_us_padd.py:108`, `19_fundamentals.py:85` and `pipelines/derived/fundamentals.py:57`. The weekly series among these crash only when 29 February is a report date.
  - Three places already clamp it, each in its own way: `core/cracks.py:133-138`, `core/publish.py:_today_doy`, `apps/dashboard/components/event_overlay.py:41-45`. `DEVELOPMENT.md:12` (rule 4) says to use `core.seasonal` and never reimplement it.
- **Exact change.**
  - In `core/seasonal.py`, add the public `reference_doy(ts)`, which drops 29 February rows, and `current_track(df, value_col="value") -> pd.Series`: the latest calendar year's rows minus 29 February, indexed by reference day of year.
  - Use `current_track` in `readme_charts.seasonal_panel`, in the five dashboard pages above and in `pipelines/derived/fundamentals.py`. Replace the three private clamps with one `reference_doy_clamped(ts)` (29 February becomes 28 February) for single dates.
  - Add `tests/test_seasonal_calendar.py`, including a guard test: `grep` finds no `replace(year=2001)` or `replace(year=REFERENCE_YEAR)` outside `core/seasonal.py`.
- **Acceptance.**
  - Daily constant 50.0 from 2022-01-01 to 2028-03-05: `seasonal_panel` returns **(50.0, 50.0)**.
  - `current_track` has **64** rows (Jan 31 + Feb 29 + Mar 5 = 65, minus 29 February) and no duplicate index.
  - `reference_doy_clamped(pd.Timestamp("2028-02-29")) == 59`.
  - The guard test passes.
  - The `tests/test_pages_smoke.py` page smoke tests stay green.
- **Risk.** It touches six pages. Each change replaces one line with one call, and the smoke tests cover the pages.
- **Implement in this run: yes.**

#### I-20 The CFTC README chart's finding is wrong whenever managed money is net short

- **Why.** At `apps/exhibits/readme_charts.py:208-210`, the title is `f"net long {net:.0f} thousand contracts, {100*(1 - net/net.max()):.0f}% below its three-year high"` with no sign check. Run here: net −10 against a three-year high of +50 gives "Managed money is **net long -10** thousand contracts, **120%** below its three-year high". Net −10 against a high of −5 gives "**-100%** below". Managed money in WTI has been net short before (in other years). The title is sentence 1 of the caption, the finding (PROJECT-STARTER 7.1), and the README repeats it by hand (`README.md:23`).
- **Exact change.** Add `positioning_finding(net_last, net_max, peak) -> str` in `readme_charts.py`. Write "net long" or "net short" with the absolute value. Use the percentage form only when both `net_last` and `net_max` are positive. Otherwise say "N thousand below its three-year high of ±M thousand in <Month YYYY>" with a sign (rule 3). When `net_last == net_max`, say "at its three-year high". Add tests.
- **Acceptance.**
  - (54, 257, Oct 2023) gives "Managed money is net long 54 thousand contracts, 79% below its three-year high of October 2023", unchanged from today's caption.
  - (−10, 50, Oct 2023) gives "Managed money is net short 10 thousand contracts, 60 thousand below its three-year high of +50 thousand in October 2023".
  - (−10, −5, Mar 2025) gives "... net short 10 thousand contracts, 5 thousand below its three-year high of −5 thousand in March 2025".
  - (60, 60, Oct 2026) gives "... net long 60 thousand contracts, at its three-year high".
  - The byte-identity test for the fixture stays green, since the fixture is net long below its high.
- **Risk.** None.
- **Implement in this run: yes.**

#### I-21 Lock the README exhibits to the desk rules: `STRICT_DESK` on, and rule-8 unit spellings

- **Why.** `core/paper_style.py:99` sets `STRICT_DESK = False` and `:98` sets `UNITS = None`, so nothing stops a red line, a legend box, a twin axis or a free-text unit from reaching the README. Today's charts comply only by luck: all four pass `ps.lint(fig, axis_labels=True)` with `STRICT_DESK = True` (run here on the test fixture). They do write units that rule 8 does not allow: "million barrels" (`readme_charts.py:173`), "thousand contracts" (`:214`), "million barrels a day" (`:251`) and "% of working capacity" (`:274`). The committed captions (`docs/img/*.tex`) carry those spellings, and PROJECT-STARTER 7.1 asks for `Units: mb; weekly…` and axis labels like "Commercial crude stocks (mb)".
- **Exact change.**
  - In `build_all`, set `ps.STRICT_DESK = True` and `ps.UNITS = frozenset({"mb", "mb/d", "kb", "kb/d", "contracts", "%"})` inside a `try/finally` that restores the previous values, so other callers in the process are untouched.
  - Units become "mb", "contracts", "mb/d" and "%".
  - Axis labels become "Commercial crude stocks (mb)", "Managed-money positions (contracts; short below zero)", "Crude moved between PADDs (mb/d)" and "EU gas storage, share of working capacity (%)".
  - The CFTC panel plots contracts, not thousands, with a `{x:,.0f}` tick formatter; its title keeps "thousand contracts" as words.
  - Do not redraw `docs/img/*`; there is no lake here. The owner redraws with `uv run python -m apps.exhibits.readme_charts`, and that goes in `PARKING.md`.
- **Acceptance.**
  - On the fixture lake, `ps.field(fig, "units")` is "mb", "contracts", "mb/d" and "%" for the four charts.
  - Every chart passes `ps.lint(fig, axis_labels=True) == []` under `STRICT_DESK`.
  - A test that adds `ax.plot(..., color="#C0392B")` to the crude chart makes `ps.save` raise.
  - After `build_all` returns, `ps.STRICT_DESK is False` and `ps.UNITS is None`.
  - The byte-identity test is updated once, to the new expected bytes, and stays green between two runs.
- **Risk.** The committed PNGs and captions stay on the old spellings until the owner redraws. The I-04 and I-20 tests also read the caption text, so update them together.
- **Implement in this run: yes.**

#### I-22 A fifth README exhibit: this week's crude build or draw against the same week in the five prior years

- **Why.** This moves the repo toward the desk-seat questions. The number the market trades on a WPSR Wednesday is the week's change in commercial crude stocks set against what is normal for that week (question 2). The repo already publishes `wow` (`pipelines/eia/wpsr_lines.py:13-14`) and a seasonal level band, but not the change against its own seasonal norm, which is the named benchmark (seasonal naive) any later scoring would use (question 3). It is public-domain EIA data, so question 4 is answered: it can be shown. It is the "weekly balance" family of house exhibits.
- **Exact change.**
  - Add `crude_weekly_change(lake)` to `apps/exhibits/readme_charts.py`. It takes `WCESTUS1` in mb, computes `diff()`, and passes it through `seasonal.seasonal_stats(..., years=band_years(df))`; no new seasonal maths. It draws the latest 26 weeks of change as bars, with the prior five years' same-week range as a light band and their median as a dashed line.
  - The title states the finding with ▲/▼ and a sign. Units are "mb"; the caption source is the WPSR (WCESTUS1), public domain.
  - Register it in `CHARTS`. Do not add the README image line until the owner has drawn it from the lake; that goes in `PARKING.md` as one line.
- **Acceptance.** Use a synthetic W-FRI series where the change in the week ending on or before 2 October is +1.0 (2021), −1.0 (2022), +3.0 (2023), 0.0 (2024), +2.0 (2025) and **−2.0** (2026, the latest). The same-week median is **+1.0** and the range is **−1.0 to +3.0**. The title reads "US crude stocks ▼2.0 mb in the week to Oct 2, against a 2021 to 2025 median of ▲1.0 mb for the week". The chart passes lint under I-21's settings and is byte-identical between two runs.
- **Risk.** It shares I-16's January edge: build it after I-16, or the first week of 2027 breaks it as well.
- **Implement in this run: yes.** Code and tests only; drawing it needs the owner's lake.

### Order for the implementer (round 2)

Work on `improve/run-01`; do not push. Run the five-placeholder-key pytest after each item and put the count in the commit message.

1. **I-15**, the screenshot and its test.
2. **I-16**, the year-start carry, before anything else that touches seasonal charts.
3. **I-17**, `inventory_deviation` and `tests/test_derived_fundamentals.py`.
4. **I-18**, the derived curve rights hole and the `RIGHTS.md` regeneration.
5. **I-19**, `current_track` and `reference_doy_clamped`, then the six call sites.
6. **I-20**, the positioning finding.
7. **I-21**, the strict switches and units. Update the I-04 and I-20 caption assertions in the same commit.
8. **I-22**, the weekly change exhibit, code and tests only.

Yes items: I-15 to I-22 (eight). Add one line each to `PARKING.md` for what the owner must do afterwards: retake a screenshot (I-15), redraw `docs/img/*` from the lake (I-21, I-22), and add the I-22 image to the README.
