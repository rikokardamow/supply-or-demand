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

#### In progress — Spec 03: ENTSOG EU gas flows
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
hover text correct, no exceptions. Session D (physical-vs-nomination gap chart + 15-day
revision window) still to come.

**Fix while writing the previous entry**: adding ENTSOG rows to the shared `flows` table
(rows use `from_node="NO"` etc.) broke the PADD page's Flows-tab map, which read the whole
table without filtering to its own `source="eia"` rows. Fixed by adding a `source` filter
parameter to `core.storage.read_flows()` itself, so every caller gets it for free — the same
bug had independently broken a second chart (the Flows tab's net-balance bar) too.
