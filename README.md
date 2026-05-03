# Kardamow Pro (`kardamow-gas`)

European natural gas + US energy intelligence dashboard. Daily-refreshed Streamlit app, weekly Substack chart drop, alert layer over six free public APIs.

See `PROJECT_BRIEF.md` for the canonical spec.

## Stack

Python 3.12 · `uv` · Streamlit · Plotly · SQLAlchemy 2.0 (async) · Postgres + TimescaleDB · Alembic · Supabase Auth · Railway · Logfire.

## Quick start

```bash
uv sync --all-extras
cp .env.example .env   # fill in secrets
make migrate
make dev
```

## Make targets

| Target      | Action                                |
| ----------- | ------------------------------------- |
| `install`   | `uv sync --all-extras`                |
| `lint`      | `ruff check` + `ruff format --check`  |
| `typecheck` | `mypy --strict src`                   |
| `test`      | `pytest`                              |
| `dev`       | Run Streamlit on `app/main.py`        |
| `migrate`   | `alembic upgrade head`                |

## Layout

See §4 of `PROJECT_BRIEF.md`. Source under `src/kardamow/`, tests under `tests/`, cron entry points under `scripts/`.

## Deploy

Railway, configured via `railway.toml`. Five services: `web`, `ingestors-daily`, `ingestors-eia-weekly`, `alerts`, `saturday-drop`. Secrets live in Railway env vars (see `.env.example`).
