# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added — Week 1 / Prompt 1.1 (2026-05-03)
- Full repository scaffold per §4 of `PROJECT_BRIEF.md`
- `pyproject.toml` with all dependencies from §3 (Streamlit, Plotly, SQLAlchemy 2.0 async,
  Alembic, Pydantic-settings, httpx, tenacity, structlog, logfire, supabase, resend, pandas)
- Dev dependencies: ruff, mypy (strict), pytest, pytest-asyncio, vcrpy, hypothesis
- `.env.example` with every secret from §12
- `Makefile` — targets: install, lint, typecheck, test, dev, migrate, clean
- `alembic.ini` + `migrations/env.py` + `migrations/script.py.mako` (async-ready)
- `railway.toml` — five Railway services: web, ingestors-daily, ingestors-eia-weekly, alerts, saturday-drop
- `PROJECT_BRIEF.md` — canonical spec saved to repo
- Empty stub modules for: db/, analytics/, charts/, narrative/, alerts/, app/, app/pages/, app/components/
- `src/kardamow/ingestors/__init__.py` only (base.py and concrete ingestors deferred to prompts 1.3–1.4)
- Test directory structure: unit/, integration/, fixtures/ with empty cassette stubs
- `tests/conftest.py` skeleton
- `CHANGELOG.md` (this file)
