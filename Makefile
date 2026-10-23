# Targets mirror .github/workflows/ci.yml and the Commands section of DEVELOPMENT.md --
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

# The full gate from rule 8 in DEVELOPMENT.md, cheapest check first.
check: lint typecheck test

dev:
	uv run streamlit run apps/dashboard/app.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
