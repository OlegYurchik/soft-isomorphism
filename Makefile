.PHONY: check format lint test

check: format lint test

format:
	uv run ruff format src/ tests/

lint:
	uv run ruff check src/ tests/

test:
	uv run pytest tests/ -v
