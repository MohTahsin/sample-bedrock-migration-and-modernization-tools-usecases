# Testing Infrastructure

This directory contains the test suite for the agent_eval module, including unit tests, integration tests, and property-based tests.

## Test Structure

```
agent_eval/tests/
├── __init__.py                      # Test package initialization
├── README.md                        # This file
├── test_sanity.py                   # Infrastructure sanity tests
├── test_hypothesis_sanity.py        # Property-based testing sanity tests
├── test_log_group_discovery.py      # Log group discovery tests
├── test_discovery_integration.py    # Discovery workflow integration tests
└── test_cloudwatch_export.py        # CloudWatch export tests (pending implementation)
```

## Running Tests

### Run all tests
```bash
pytest agent_eval/tests/
```

### Run with verbose output
```bash
pytest agent_eval/tests/ -v
```

### Run specific test markers
```bash
# Unit tests only
pytest agent_eval/tests/ -m unit

# Integration tests only
pytest agent_eval/tests/ -m integration

# Property-based tests only
pytest agent_eval/tests/ -m property
```

### Run with coverage
```bash
pytest agent_eval/tests/ --cov=agent_eval --cov-report=html
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests for individual components
- `@pytest.mark.integration` - Integration tests for complete workflows
- `@pytest.mark.property` - Property-based tests using Hypothesis

## Dependencies

### Runtime Dependencies
- `jsonschema>=4.0.0` - JSON schema validation
- `pyyaml>=6.0.0` - YAML configuration parsing
- `pydantic>=2.0.0` - Data validation and settings management

### Development Dependencies (optional group)
- `pytest>=7.0.0` - Testing framework
- `pytest-cov>=4.0.0` - Coverage reporting
- `hypothesis>=6.0.0` - Property-based testing

Install development dependencies:
```bash
pip install -e ".[dev]"
```

## Configuration

Test configuration is defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["agent_eval/tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "--verbose",
    "--strict-markers",
    "--tb=short",
]
markers = [
    "unit: Unit tests for individual components",
    "integration: Integration tests for complete workflows",
    "property: Property-based tests using Hypothesis",
]
```

## Coverage Configuration

Coverage settings are also in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["agent_eval"]
omit = [
    "agent_eval/tests/*",
    "agent_eval/__pycache__/*",
    "*/__pycache__/*",
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
precision = 2
show_missing = true
```

## Writing Tests

### Unit Test Example
```python
import pytest

@pytest.mark.unit
def test_example():
    """Test description."""
    assert True
```

### Integration Test Example
```python
import pytest

@pytest.mark.integration
def test_workflow():
    """Test complete workflow."""
    # Setup
    # Execute
    # Assert
    pass
```

### Property-Based Test Example
```python
import pytest
from hypothesis import given, strategies as st

@pytest.mark.property
@given(st.integers())
def test_property(x):
    """Test property holds for all integers."""
    assert isinstance(x, int)
```

## Test Coverage Goals

- **Phase 1 (Current)**: Minimum 85% coverage for core adapter functionality
- **Future Phases**: Maintain or increase coverage as new features are added

## Continuous Integration

Tests are designed to run in CI environments:
- Fast execution (< 1 minute for unit tests)
- Deterministic results
- Clear failure messages
- No external dependencies for unit tests

## Troubleshooting

### Import Errors
Ensure the package is installed in development mode:
```bash
pip install -e .
```

### Missing Dependencies
Install all dependencies including dev group:
```bash
pip install -e ".[dev]"
```

### Hypothesis Configuration
Property-based tests use Hypothesis defaults. To customize:
```python
from hypothesis import settings

@settings(max_examples=1000)
@given(st.integers())
def test_with_more_examples(x):
    pass
```
