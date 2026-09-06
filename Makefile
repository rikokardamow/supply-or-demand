# Targets mirror .github/workflows/ci.yml and the root CLAUDE.md's own Commands section --
# keep the three checks below identical to what CI runs, or `make check` passing locally
# stops meaning anything.
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
# CLAUDE.md code review procedure.
check: lint typecheck test

dev:
	uv run streamlit run apps/dashboard/app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
