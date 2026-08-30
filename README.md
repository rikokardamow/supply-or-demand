# Kardamow Energy Dashboard

Solo-analyst energy/macro research dashboard (publication: Kardamow). Ingest pipelines pull
per-source data into a DuckDB + Parquet lake; a Streamlit multipage app reads the lake and
renders it in a shared house chart style. See `NOTES.md` for the conventions every part of
this repo follows, and `specs/` for the full spec-driven build plan.

## Stack

Python 3.12 · `uv` · pandas · duckdb · pyarrow · plotly · streamlit · pydantic +
pydantic-settings · requests. Lint: ruff. Types: mypy. Tests: pytest + vcrpy cassettes.

## Quick start

```bash
uv sync --all-extras
cp .env.example .env   # fill in real API keys — this file is git-ignored, never commit it
uv run python pipelines/eia/pull_wpsr.py   # populate the lake
uv run streamlit run apps/dashboard/app.py
```

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy core pipelines
```

Before any commit, confirm no secret ever landed in a tracked file:

```bash
git grep -iE "api_key.*=.*[A-Za-z0-9]{20}" -- ':!*.example'   # must return nothing
```

## Layout

```
core/                 shared library: settings, schemas, storage (the lake), seasonal
                       maths, theme, release calendars
pipelines/<source>/   per-source ingestor (client + NOTES.md + cassette test)
apps/dashboard/       Streamlit app — reads the lake only, never calls APIs directly
specs/                spec-driven build plan, one file per data source
data/                 git-ignored lake (raw/ + lake/); only .gitkeep is tracked
tests/                pytest suite, including vcrpy cassettes in tests/cassettes/
```

## Adding a new pipeline or page

Use the scaffolding slash commands — `/new-pipeline <source>` and `/new-page <name>` (see
`.claude/commands/`) — to keep new pipelines and pages consistent with the existing ones.

## CI

`.github/workflows/ci.yml` runs ruff, mypy, and pytest on every push/PR to `main`. Tests run
against recorded cassettes only (`--record-mode=none`) — no live API calls and no real
secrets are needed in CI.

## Status

Live pages today: **US PADD** (crude/product stocks, refining, inter-PADD flows, WPSR
table), **US Oil Market Overview** (national balance supplementary charts), **EU Gas
Storage & LNG** (AGSI+/ALSI+ fill, injection vs. send-out, country deviation). See
`specs/00_INDEX.md` for the full roadmap (13 specs: gas storage, gas flows, power markets,
refinery cracks, weather, news, AIS vessels, flights, macro/FX, and final orchestration).

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

#### In progress — Spec 03: ENTSOG EU gas flows
Session A merged: `pipelines/entsog/` — no-auth client against ENTSOG's Transparency
Platform (`limit=-1` pulls a full page in one call for both the point directory and
operational-data endpoints), a Parquet-cached point directory, and `corridors.py` mapping
6 real corridors (Norwegian export points, TAP, TurkStream, and 3 interconnectors) to
validated `pointKey`/`directionKey` pairs. `pull_no_exports.py` pulls Norwegian pipeline
exports into the shared `flows` table. [PR #6](https://github.com/rikokardamow/energy-dashboard/pull/6).
Sessions B–D (full multi-corridor pulls, Sankey chart, directional map,
physical-vs-nomination gap chart) still to come — no page yet for this spec.

**Fix while writing this changelog**: adding ENTSOG rows to the shared `flows` table (rows
use `from_node="NO"` etc.) broke the PADD page's Flows-tab map, which read the whole table
without filtering to its own `source="eia"` rows. Fixed in `components/padd_map.py` by
filtering `read_flows()` to `source == "eia"` before plotting — confirmed live (the tab
crashed with `KeyError: 'NO'` before the fix, renders correctly after).
