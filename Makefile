.PHONY: sync
sync:
	uv sync --all-extras

.PHONY: format
format:
	uv run ruff format
	uv run ruff check --fix

.PHONY: lint
lint:
	uv run ruff check

.PHONY: lint-unsafe
lint-unsafe:
	uv run ruff check --fix --unsafe-fixes

.PHONY: mypy
mypy:
	uv run mypy src

.PHONY: tests
tests:
	uv run pytest

.PHONY: tests-fast
tests-fast:
	uv run pytest -x --ff

.PHONY: tests-verbose
tests-verbose:
	uv run pytest -v

.PHONY: coverage
coverage:
	uv run coverage run -m pytest
	uv run coverage xml -o coverage.xml
	uv run coverage report -m --fail-under=83

.PHONY: coverage-html
coverage-html:
	uv run coverage run -m pytest
	uv run coverage html
	@echo "Coverage report generated in htmlcov/index.html"

.PHONY: clean
clean:
	rm -rf .coverage coverage.xml htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.PHONY: check
check: lint mypy tests

.PHONY: ci
ci: sync check coverage

.PHONY: serve-docs
serve-docs:
	cd docs && mintlify dev

.PHONY: build
build:
	uv build

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  sync         - Install dependencies"
	@echo "  format       - Format code and apply safe fixes"
	@echo "  lint         - Run linting checks"
	@echo "  lint-unsafe  - Run linting with unsafe fixes"
	@echo "  mypy         - Run type checking"
	@echo "  tests        - Run all tests"
	@echo "  tests-fast   - Run tests with fail-fast and last-failed"
	@echo "  tests-verbose- Run tests with verbose output"
	@echo "  coverage     - Run tests with coverage reporting"
	@echo "  coverage-html- Generate HTML coverage report"
	@echo "  clean        - Clean cache files and artifacts"
	@echo "  check        - Run lint, mypy, and tests"
	@echo "  ci           - Run full CI pipeline (sync, check, coverage)"
	@echo "  serve-docs   - Serve documentation locally"
	@echo "  build        - Build the package"
	@echo "  help         - Show this help message"
