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
uv run python pipelines/eia/pull_crude_stocks.py   # populate the lake
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

- **v0.1** — core library, EIA client (`pipelines/eia/`), dashboard shell, seasonal-range
  charting, release calendars, pipeline/page scaffolding commands, CI.
- See `specs/00_INDEX.md` for the full roadmap (specs 01–13: EU gas storage, gas flows,
  power markets, refinery cracks, weather, news, AIS vessels, flights, macro/FX, and final
  orchestration).
