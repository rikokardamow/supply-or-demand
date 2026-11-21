# `make check` is the gate: run it locally before every merge. There is no CI and no
# GitHub Actions workflow. The tests replay recorded cassettes, but core.settings still needs
# the required API keys to be set (any placeholder value will do); see .env.example.
.PHONY: install lint typecheck test check dev clean

install:
	uv sync --all-extras

lint:
	uv run ruff check .

typecheck:
	uv run mypy core pipelines infra apps

test:
	uv run pytest

# The full green-session gate from golden rule 8, in the cheapest-first order of the
# NOTES.md code review procedure.
check: lint typecheck test

dev:
	uv run streamlit run apps/dashboard/app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
