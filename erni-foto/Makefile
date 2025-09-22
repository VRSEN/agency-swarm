# Makefile for Erni-Foto system

.PHONY: help install dev-install test lint format type-check clean build docker-build docker-run docker-stop docs ci coverage pre-commit cli-test compile-check

# Default target
help:
	@echo "Erni-Foto System - Available Commands:"
	@echo ""
	@echo "Development:"
	@echo "  install      Install production dependencies"
	@echo "  dev-install  Install development dependencies"
	@echo "  test         Run tests"
	@echo "  lint         Run linting checks"
	@echo "  format       Format code"
	@echo "  type-check   Run type checking"
	@echo "  clean        Clean build artifacts"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  build        Build distribution packages"
	@echo "  docker-build Build Docker image"
	@echo "  docker-run   Run with Docker Compose"
	@echo "  docker-stop  Stop Docker containers"
	@echo ""
	@echo "Usage:"
	@echo "  run          Run the system (requires configuration)"
	@echo "  validate     Validate configuration"
	@echo "  status       Check system status"
	@echo "  docs         Generate documentation"

# Development setup
install:
	pip install -e .

dev-install:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest tests/ -v --cov=src/erni_foto --cov-report=html --cov-report=term

test-fast:
	pytest tests/ -v -x --tb=short

# Code quality
lint:
	ruff check src/ tests/ examples/
	black --check src/ tests/ examples/

format:
	black src/ tests/ examples/
	ruff check --fix src/ tests/ examples/

type-check:
	mypy src/erni_foto

# Cleanup
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build
build: clean
	python -m build

# Docker
docker-build:
	docker build -t erni-foto:latest .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f erni-foto

# Usage commands
run:
	@echo "Usage examples:"
	@echo "  python -m erni_foto.main process --source-library SOURCE_ID --target-library TARGET_ID"
	@echo "  python -m erni_foto.main status"
	@echo "  python -m erni_foto.main validate-config"

validate:
	python -m erni_foto.main validate-config

status:
	python -m erni_foto.main status

# Documentation
docs:
	@echo "Generating documentation..."
	@echo "README.md contains comprehensive documentation"
	@echo "See examples/ directory for usage examples"

# Development workflow
dev-setup: dev-install
	@echo "Development environment set up successfully!"
	@echo "Run 'make validate' to check your configuration"

# CI/CD targets
ci: lint type-check test
	@echo "All CI checks passed!"

# Release preparation
pre-release: clean ci build
	@echo "Release preparation completed!"
	@echo "Distribution packages are in dist/"

# Quick development cycle
dev: format lint test-fast
	@echo "Development cycle completed!"

# Full quality check
quality: format lint type-check test
	@echo "Full quality check completed!"

# CI/CD Pipeline
ci: lint type-check compile-check test coverage cli-test
	@echo ""
	@echo "🎉 All CI checks passed!"
	@echo "✅ Ruff linting: PASSED"
	@echo "✅ MyPy type checking: PASSED"
	@echo "✅ Python compilation: PASSED"
	@echo "✅ Tests: PASSED"
	@echo "✅ Coverage ≥80%: PASSED"
	@echo "✅ CLI functionality: PASSED"

# Coverage with reporting
coverage:
	@echo "📊 Running tests with coverage..."
	python -m pytest tests/ -v --cov=src/erni_foto --cov-report=html --cov-report=term-missing --cov-fail-under=80

# Pre-commit hooks
pre-commit:
	@echo "🔗 Installing and running pre-commit hooks..."
	pre-commit install
	pre-commit run --all-files

# CLI testing
cli-test:
	@echo "🖥️  Testing CLI functionality..."
	python -m erni_foto.main --help
	python -m erni_foto.main validate-config --help

# Compilation check
compile-check:
	@echo "🔧 Running Python compilation check..."
	python -m py_compile src/erni_foto/__init__.py src/erni_foto/config.py src/erni_foto/main.py
	find src/erni_foto -name "*.py" -exec python -m py_compile {} \;
