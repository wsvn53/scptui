.PHONY: build clean install dev-install test lint format help

help:
	@echo "📦 Available targets:"
	@echo "  build        - Build wheel package"
	@echo "  clean        - Remove build artifacts"
	@echo "  install      - Install the package"
	@echo "  dev-install  - Install package in development mode"
	@echo "  test         - Run tests"
	@echo "  lint         - Run linters"
	@echo "  format       - Format code with black"

build: clean
	@echo "🔨 Building wheel package..."
	pip wheel --no-deps -w dist .

clean:
	@echo "🧹 Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .eggs/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete

install:
	@echo "📥 Installing package..."
	pip install dist/*.whl

dev-install:
	@echo "🔧 Installing package in development mode..."
	pip install -e ".[dev]"

test:
	@echo "🧪 Running tests..."
	pytest

lint:
	@echo "🔍 Running linters..."
	ruff check .

format:
	@echo "✨ Formatting code..."
	black .
