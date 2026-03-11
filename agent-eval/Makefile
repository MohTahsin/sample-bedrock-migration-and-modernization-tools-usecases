.PHONY: test test-unit test-smoke test-local pre-push clean install

# Install dependencies
install:
	pip install -e ".[dev]"

# Run unit tests only
test-unit:
	pytest agent_eval/tests/ -v

# Run smoke tests only
test-smoke:
	./scripts/smoke_test_raw_traces.sh

# Run all local tests (unit + smoke)
test-local: test-unit test-smoke

# Pre-push quality gate (comprehensive)
pre-push:
	./scripts/pre_push_check.sh

# Alias for pre-push
test: pre-push

# Clean test artifacts
clean:
	rm -rf .smoke-test-output
	rm -rf .pre-push-test-*
	rm -rf .pytest_cache
	rm -rf agent_eval/__pycache__
	rm -rf agent_eval/**/__pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Help
help:
	@echo "Available targets:"
	@echo "  install     - Install package with dev dependencies"
	@echo "  test-unit   - Run unit tests only"
	@echo "  test-smoke  - Run smoke tests only"
	@echo "  test-local  - Run unit + smoke tests"
	@echo "  pre-push    - Run full quality gate (recommended before push)"
	@echo "  test        - Alias for pre-push"
	@echo "  clean       - Clean test artifacts"
	@echo "  help        - Show this help message"
