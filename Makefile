.PHONY: sync
sync:
	uv sync --all-extras --dev

.PHONY: test-env
test-env: sync
	uv run python -c "import litellm"
	uv run python -c "from agents.extensions.models.litellm_model import LitellmModel"

.PHONY: prime
prime:
	@echo "[prime] Context priming: building structure and reviewing diffs"
	@echo "Full file list:"
	@find src/ -name "*.py" | sort
	@echo "--------------------------------"
	@echo "Top 5 largest files:"
	@find src/ -name "*.py" | xargs wc -l | sort -nr | head -n 5
	@echo "--------------------------------"
	@echo "Full test list:"
	@find tests/ -name "*.py" | sort
	@echo "--------------------------------"
	@echo "Git status:"
	@git status --porcelain
	@echo "--------------------------------"
	@echo "Git diff (staged):"  # Only show staged changes
	@git diff --cached -- . ':(exclude)uv.lock' | cat
	@echo "--------------------------------"
	@echo "Git diff (unstaged):"
	@git diff -- . ':(exclude)uv.lock' | cat
	@echo "--------------------------------"

.PHONY: format
format:
	uv run ruff format --exclude docs
	uv run ruff check --fix --exclude docs

.PHONY: lint
lint:
	uv run ruff check --exclude docs

.PHONY: lint-unsafe
lint-unsafe:
	uv run ruff check --fix --unsafe-fixes --exclude docs

.PHONY: mypy
mypy:
	uv run mypy src

.PHONY: tests
tests: test-env
	uv run pytest

.PHONY: tests-fast
tests-fast: test-env
	uv run pytest -x --ff

.PHONY: tests-verbose
tests-verbose: test-env
	uv run pytest -v

.PHONY: coverage
coverage: test-env
	uv run coverage run -m pytest
	uv run coverage xml -o coverage.xml
	uv run coverage report -m --fail-under=89

.PHONY: coverage-html
coverage-html: test-env
	uv run coverage run -m pytest
	uv run coverage html
	@echo "Coverage report generated in htmlcov/index.html"

.PHONY: clean
clean:
	rm -rf .coverage coverage.xml htmlcov/ .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.PHONY: check
check: lint mypy

.PHONY: ci
ci: sync check coverage

.PHONY: serve-docs
serve-docs:
	cd docs && mintlify dev

.PHONY: build
build:
	@echo "Building package (pricing data will be auto-downloaded by build hook)..."
	uv build

.PHONY: help
help:
	@echo "Available commands:"
	@echo "  sync         - Install dependencies (all extras + dev)"
	@echo "  test-env     - Sync deps and verify LiteLLM test imports"
	@echo "  format       - Format code and apply safe fixes"
	@echo "  lint         - Run linting checks"
	@echo "  lint-unsafe  - Run linting with unsafe fixes"
	@echo "  mypy         - Run type checking"
	@echo "  tests        - Sync/verify test env and run all tests"
	@echo "  tests-fast   - Sync/verify test env and run tests with fail-fast and last-failed"
	@echo "  tests-verbose- Sync/verify test env and run tests with verbose output"
	@echo "  coverage     - Sync/verify test env and run tests with coverage reporting"
	@echo "  coverage-html- Sync/verify test env and generate HTML coverage report"
	@echo "  clean        - Clean cache files and artifacts"
	@echo "  check        - Run lint and mypy"
	@echo "  ci           - Run full CI pipeline (sync, check, coverage)"
	@echo "  serve-docs   - Serve documentation locally"
	@echo "  build        - Build the package"
	@echo "  help         - Show this help message"
