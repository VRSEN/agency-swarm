.PHONY: sync
sync:
	uv sync --all-extras --all-packages --group dev

.PHONY: format
format:
	uv run ruff format
	uv run ruff check --fix

.PHONY: lint
lint:
	uv run ruff check

.PHONY: mypy
mypy:
	uv run mypy src

.PHONY: tests
tests:
	uv run pytest

.PHONY: coverage
coverage:

	uv run coverage run -m pytest
	uv run coverage xml -o coverage.xml
	uv run coverage report -m --fail-under=95

.PHONY: serve-docs
serve-docs:
	cd docs && mintlify dev
