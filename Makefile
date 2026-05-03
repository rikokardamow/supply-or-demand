.PHONY: install lint typecheck test dev migrate clean

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy --strict src

test:
	uv run pytest

dev:
	uv run streamlit run src/kardamow/app/main.py

migrate:
	uv run alembic upgrade head

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
