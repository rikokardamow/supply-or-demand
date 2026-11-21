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

### I-03 README and docs: stop claiming what the code does not do

- **Problem.** `README.md:39` claims revisions become new rows (they overwrite, I-05). `README.md:91` claims terms were checked per pipeline and found free (18 NOTES files have no terms section; the owner's register disagrees on six sources). `README.md:69` demonstrates the API with a class-d series. `docs/README.md:9` says NOTES files record terms.
- **Proposal.** Four surgical edits: (a) line 39: "The lake is partitioned Parquet de-duplicated on series and date; a corrected number replaces the earlier one, and the write time is kept in `revision_date`. First prints are not retained yet (see PARKING.md)." (b) line 69: use `series_id=eq.WCESTUS1` (EIA, public domain). (c) line 91: split the row; keep EIA, CFTC, OFAC, Frankfurter, Eurostat, JODI with the wording they earn, and add a row "GIE AGSI+/ALSI+, ENTSO-E, ENTSOG, FRED, OPEC, Baker Hughes, gridstatus, EirGrid: terms read differently in the owner's register; see `RIGHTS.md`, published pending that decision". Add a row for Yahoo Finance: "Redistribution restricted; kept out of the serving layer since <date>". (d) `docs/README.md:9`: "`RIGHTS.md` records each source's terms and class; the per-pipeline `NOTES.md` record what was verified live." Also add `RIGHTS.md` to the Layout paragraph.
- **Desk-seat value.** A reader who checks one claim and finds it false stops reading.
- **Effort.** 1.5 h.
- **Risk.** `origin/docs/readme-and-notes` (unmerged, 47 files) also rewrites the README; the owner may need to resolve a small conflict. Keep edits to the four places above.
- **Acceptance test.** `tests/test_readme_claims.py`: `README.md` does not contain "a corrected number is a new row", does not contain `fut.cl.f01.close`, does contain `RIGHTS.md`; `docs/README.md` contains `RIGHTS.md`. Existing tests green.
- **Rights impact.** Honest public statement of what is published under which terms.
- **Implement in this run: yes.** Pure documentation of facts established above; depends on I-01 for `RIGHTS.md`.

### I-04 Compute the README band years from the data

- **Problem.** `apps/exhibits/readme_charts.py:36` `BAND_YEARS = range(2021, 2026)`; subtitles print `BAND_YEARS.start` and `BAND_YEARS.stop - 1`. On 1 January 2027 every README chart silently compares the new year against a band missing 2026. `core/seasonal.py:22-27` already explains why a frozen range is wrong.
- **Proposal.** Replace the constant with `band_years(df) -> range` = `range(last_year - 5, last_year)` where `last_year = df["ts"].max().year`, 2020 still excluded by `seasonal_stats`'s default. Call it in `seasonal_panel` and in each subtitle. Keep five years, as the artifacts design system does.
- **Desk-seat value.** A seasonal exhibit that is right every year without a hand edit; section 6 says 2020 stays out, section 7 says the band is "faint named prior years".
- **Effort.** 1 h.
- **Risk.** Byte-stability test: the PNGs must still be byte-identical for the current fixture, which they will be because the computed range for a series ending in 2026 is 2021..2025, the same as today.
- **Acceptance test.** In `tests/test_readme_charts.py`, `band_years` on the fixture `WCESTUS1` series ending `2026-10-02` returns `range(2021, 2026)` and the caption contains "2021 to 2025"; a second fixture ending `2027-03-05` returns `range(2022, 2027)` and the caption contains "2022 to 2026" and the band does not include 2020 (assert `"2020" not in stats.columns` from `seasonal_stats`). Existing byte-identity test unchanged and green.
- **Rights impact.** None.
- **Implement in this run: yes.**

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
