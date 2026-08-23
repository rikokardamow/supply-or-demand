# Spec 00 — Project Setup, Core Library & Dashboard Shell

**When:** Session 1 = Fri 22 Aug 2026, ~21:00 Dublin, ~2 h. Sessions 2–3 finish Week 1.
**Prereqs:** All keys rotated. Python 3.12 + `uv` installed. Git configured. Nothing else.
**Blocks:** every other spec.

## Objective
A running, themed, multipage Streamlit dashboard backed by a DuckDB + Parquet lake, with the
shared `core/` library (settings, storage, schemas, seasonal maths, theme) and one real EIA
chart rendering — proving the whole pipeline end-to-end on day one.

## Pre-session manual steps (do these yourself, not in Claude Code)
1. Rotate keys: EIA, Ember, GIE, ENTSO-E, FRED, NewsAPI, WorldNews, ECMWF, tomorrow.io, Mapbox. Change the IBKR password.
2. Create the GitHub repo `energy-dashboard` (private).
3. Bootstrap locally:
   ```bash
   mkdir energy-dashboard && cd energy-dashboard && git init
   uv init --python 3.12
   uv add pandas duckdb plotly streamlit pydantic pydantic-settings requests pyarrow
   uv add --dev pytest ruff mypy vcrpy pytest-recording
   printf ".env\ndata/\n*.duckdb\n__pycache__/\n.venv/\n" > .gitignore
   mkdir -p core pipelines apps/dashboard/pages tests/cassettes specs data
   ```
4. Copy `CLAUDE.md` (root) and this spec pack into place. Create `.env` from `.env.example` with rotated keys.

## Target structure after this spec
```
energy-dashboard/
├── CLAUDE.md            ├── specs/*.md
├── pyproject.toml       ├── .env.example (names only)
├── core/{__init__,settings,schemas,storage,seasonal,theme,calendars}.py
├── pipelines/eia/{__init__,client}.py + CLAUDE.md
├── apps/dashboard/app.py + pages/01_us_padd.py
├── tests/{test_storage,test_seasonal,test_eia_client}.py + cassettes/
└── data/{raw,lake}/     (git-ignored)
```

## Session 1 (Fri 22 Aug, ~2 h) — copy-paste prompt for Claude Code

> Read CLAUDE.md and specs/00_project-setup.md. Plan first, then implement:
> 1. `core/settings.py` — pydantic-settings `Settings` loading from `.env`: `eia_api_key`,
>    `ember_api_key`, `gie_api_key`, `entsoe_api_key`, `fred_api_key`, plus optional
>    `newsapi_key`, `worldnews_key`, `aisstream_key`, `opensky_client_id`,
>    `opensky_client_secret`, `mapbox_token`, `tomorrow_io_key`, `guardian_key`. Export a
>    module-level `settings`. Also write `.env.example` with names and blank values.
> 2. `core/schemas.py` — pydantic models + pyarrow schemas for `ts_long` and `flows`
>    exactly as defined in CLAUDE.md. Include a `validate_ts_long(df)` helper that raises on
>    missing columns/dtypes.
> 3. `core/storage.py` — `write_ts_long(df, source)` appending Parquet to
>    `data/lake/ts_long/source=<source>/year=<yyyy>/part-*.parquet` with de-duplication on
>    `(series_id, ts)` keeping the latest `revision_date`; `read_ts_long(series_ids, start=None, end=None)`
>    reading via DuckDB over the Parquet glob; `warehouse()` returning a DuckDB connection with a
>    `ts_long` view registered. Mirror `write_flows`/`read_flows`.
> 4. `core/seasonal.py` — `seasonal_stats(df, value_col, years=range(2018, 2026), exclude=(2020,))`
>    returning day-of-year indexed `lo`, `hi`, `median` plus each year's track; `yoy(df)`;
>    leap-day handling (drop 29 Feb). 2020 must be excluded by default and this must be tested.
> 5. `core/theme.py` — register Plotly template `"kardamow"` per the house style in CLAUDE.md
>    and set it as default. Add helpers: `seasonal_range_chart(stats_df, current_year_series, title, unit)`
>    (grey band, orange median, navy current year, "Latest / YoY / vs median" annotation at the last
>    point) and `dual_axis_chart(left_series, right_series, ...)` (navy left, light-blue right).
> 6. `pipelines/eia/client.py` — `EIAClient` with `get_series(route: str, series: list[str], frequency: str)`
>    building `https://api.eia.gov/v2/{route}/data/` requests with `data[0]=value`,
>    `facets[series][]`, sort desc, `length=5000`, offset pagination until exhausted; returns a
>    `ts_long`-conformant DataFrame. Add `pipelines/eia/CLAUDE.md` documenting the route/facet pattern
>    and the 5,000-row page limit.
> 7. Script `pipelines/eia/pull_crude_stocks.py` — pulls weekly series `WCESTUS1` (US crude ex-SPR)
>    and `W_EPC0_SAX_YCUOK_MBBL` (Cushing) full history → `write_ts_long(source="eia")`.
> 8. `apps/dashboard/app.py` — Streamlit multipage home: title "Kardamow Energy Dashboard",
>    lake status table (datasets, row counts, last ts) from DuckDB.
>    `apps/dashboard/pages/01_us_padd.py` — renders the Cushing seasonal-range chart from the lake.
> 9. Tests: `test_seasonal.py` (synthetic 2018–2026 data: band = min/max, 2020 excluded — assert a
>    2020 outlier does NOT widen the band; leap-day dropped); `test_storage.py` (round-trip +
>    de-dup on revision); `test_eia_client.py` with a vcrpy cassette (record once live, filter the
>    `api_key` query param out of the cassette).
> 10. Configure ruff + mypy + pytest in `pyproject.toml`. Everything green.
>
> Acceptance: `uv run python pipelines/eia/pull_crude_stocks.py` populates the lake;
> `streamlit run apps/dashboard/app.py` shows the themed Cushing seasonal chart;
> `pytest`, `ruff check .`, `mypy core pipelines` all pass; no key value appears in any tracked file
> (verify with `git grep -iE "api_key.*=.*[A-Za-z0-9]{20}" -- ':!*.example'` returning nothing).

Commit as `feat: core library, EIA client, dashboard shell (v0.1)` and tag `v0.1`.

## Session 2 (weekday, 1 h)
> Read specs/00_project-setup.md. Add `core/calendars.py`: release-calendar constants
> (EIA WPSR Wed 10:30 ET; EIA NG storage Thu 10:30 ET; AGSI+ ~19:30 CET; Baker Hughes Fri;
> OPEC MOMR 11th–14th; JODI ~20th; CFTC COT Fri) with `next_release(name, now)` helpers and tests.
> Add `.claude/commands/new-pipeline.md` and `.claude/commands/new-page.md` slash-command
> templates that scaffold a pipeline (client + CLAUDE.md + cassette test) and a dashboard page.

## Session 3 (weekday, 1 h)
> Wire GitHub Actions `ci.yml`: on push/PR run ruff, mypy, pytest (cassettes only, no live calls,
> no secrets needed). Protect `main`. Confirm CI green on a trivial PR.

## Definition of Done
- Dashboard shell runs with one real, themed EIA chart read from the lake.
- `core/` complete and tested (settings, schemas, storage, seasonal excl-2020, theme, calendars).
- CI green; `v0.1` tagged; zero secrets in git history.

## Stretch (only if ahead of schedule)
- `gitleaks` pre-commit hook. — `core/theme.py` scatter-with-fitted-log-curve helper (needed by Spec 07).
