# Testing Infrastructure

This directory contains the test suite for the agent_eval module, including unit tests, integration tests, and property-based tests.

## Test Structure

```
agent_eval/tests/
├── __init__.py                                    # Test package initialization
├── README.md                                      # This file
│
├── component/                                     # Component validation tests (200 tests)
│   ├── test_corpus_validation.py                 # Baseline corpus integrity (Req 1.x)
│   ├── test_metrics_validation.py                # Deterministic metrics (Req 2.x)
│   ├── test_evaluator_contract.py                # Evaluator I/O contract (Req 3.x)
│   ├── test_evidence_selection.py                # Evidence extraction (Req 4.x)
│   ├── test_rubric_resolution.py                 # Rubric loading (Req 5.x)
│   ├── test_score_aggregation.py                 # Score aggregation (Req 6.x)
│   ├── test_judge_orchestration.py               # Judge queue/rate limiting (Req 7.x)
│   ├── test_output_validation.py                 # Results output (Req 8.x)
│   └── test_pipeline_e2e.py                      # End-to-end pipeline (Req 9.x)
│
├── baseline/                                      # Baseline corpus validation
│   └── test_baseline_corpus.py                   # Tests against 11-trace corpus
│
├── test_production_gates.py                      # Production gate tests (Phase 1)
├── test_production_gates_phase2.py               # Production gate tests (Phase 2)
├── test_production_gates_phase2_extended.py      # Extended production tests
│
├── test_adapter_preservation_segmentation.py     # Turn segmentation preservation
├── test_adapter_preservation_tool_status.py      # Tool status preservation
├── test_adapter_segmentation_regression.py       # Segmentation regression tests
├── test_adapter_tool_status_regression.py        # Tool status regression tests
│
├── test_sanity.py                                # Infrastructure sanity tests
├── test_hypothesis_sanity.py                     # Property-based testing sanity
├── test_property_bounded_concurrency.py          # Concurrency property tests
├── test_log_group_discovery.py                   # Log group discovery tests
├── test_discovery_integration.py                 # Discovery workflow integration
├── test_cloudwatch_export.py                     # CloudWatch export tests
├── test_01_export_turns.py                       # Turn export tests
├── test_run_from_agentcore_arn.py                # AgentCore ARN integration
├── test_run_from_agentcore_arn_pipeline.py       # AgentCore pipeline integration
├── test_adapter_integration.py                   # Adapter integration tests
├── test_adapter_resilience.py                    # Adapter resilience tests
├── test_trace_eval_integration.py                # Trace evaluator integration
├── test_error_handling.py                        # Error handling tests
├── test_integration.py                           # General integration tests
├── test_sample_traces.py                         # Sample trace tests
├── test_validation.py                            # Validation tests
├── test_input_validator.py                       # Input validation tests
├── test_config_loader.py                         # Config loader tests
├── test_judge_config.py                          # Judge config tests
├── test_module_imports.py                        # Module import tests
└── test_utils.py                                 # Test utilities and helpers
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

### Run specific test suites
```bash
# Component tests only (200 tests)
pytest agent_eval/tests/component/ -v

# Baseline corpus validation (11 traces)
pytest agent_eval/tests/baseline/ -v

# Production gate tests
pytest agent_eval/tests/test_production_gates.py -v
pytest agent_eval/tests/test_production_gates_phase2.py -v

# Adapter regression tests
pytest agent_eval/tests/test_adapter_*_regression.py -v

# Property-based tests
pytest agent_eval/tests/test_property_*.py -v
```

### Run specific test markers
```bash
# Unit tests only
pytest agent_eval/tests/ -m unit

# Integration tests only
pytest agent_eval/tests/ -m integration

# Property-based tests only
pytest agent_eval/tests/ -m property

# Baseline validation tests only
pytest agent_eval/tests/ -m baseline

# Component tests only
pytest agent_eval/tests/ -m component
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
- `@pytest.mark.baseline` - Deterministic baseline validation tests
- `@pytest.mark.component` - Component validation tests (new comprehensive suite)

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
    "baseline: Deterministic baseline validation tests",
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

- **Phase 1 (Complete)**: Minimum 85% coverage for core adapter functionality ✓
- **Phase 2 (Complete)**: Deterministic baseline validation with 11-trace corpus ✓
- **Phase 3 (Complete)**: Component validation suite with 200 tests covering 9 requirement areas ✓
- **Phase 4 (Complete)**: Production gate tests with 14+ test cases ✓
- **Current Status**: ~280 total tests, all passing (200 passed, 2 skipped in component suite)
- **Future Phases**: Maintain or increase coverage as new features are added

## Baseline Validation Testing

The baseline validation tests ensure the non-LLM components (adapter, deterministic metrics, tool counting) are stable before introducing real LLM judges. See [Baseline Testing Guide](../../guides/BASELINE_TESTING_GUIDE.md) for detailed information.

Key aspects:
- Fixed corpus of 11 traces (3 good, 3 bad, 2 partial/ambiguous, 2 weird, 1 ambiguous)
- Known expected outcomes for each trace
- Validates deterministic metrics, tool counts, latency fields, turn counts
- Tests failure handling and edge cases

## Test Fixtures

Test fixtures are organized in `test-fixtures/` directory:

### Baseline Corpus (`test-fixtures/baseline/`)
11 production-representative traces for deterministic validation:
- `good_001_direct_answer.json` - Single turn, no tools
- `good_002_tool_grounded.json` - Tool used correctly
- `good_003_two_turn_noise.json` - Multi-turn with noise filtering
- `bad_001_wrong_math.json` - Factually incorrect answer
- `bad_002_ignores_tool.json` - Tool result ignored
- `bad_003_tool_failed_hallucinated.json` - Failed tool + hallucination
- `partial_001_incomplete_but_ok.json` - Brief but correct
- `partial_002_hedged_without_tool.json` - Hedged answer
- `ambiguous_001_hedged_without_tool.json` - Uncertain response
- `weird_001_duplicate_tool_calls.json` - Duplicate tool events
- `weird_002_orphan_tool_result.json` - Orphan tool result

Metadata files:
- `manifest.yaml` - Trace catalog with validation types
- `expected_outcomes.yaml` - Expected metrics for each trace

### Production Gates (`test-fixtures/production-gates/`)
14 test cases for production readiness validation:
- `case_01_single_turn_clean.json` - Clean single turn
- `case_02_multi_turn_clean.json` - Clean multi-turn
- `case_05_missing_event_path.json` - Missing event paths
- `case_06_malformed_events.json` - Malformed event structures
- `case_07_dirty_timestamps.json` - Inconsistent timestamps
- `case_08_missing_grouping_ids.json` - Missing IDs
- `case_09_turn_segmentation_noise.json` - Noisy turn boundaries
- `case_10_tool_success_inference.json` - Tool success detection
- `case_11_tool_failure_inference.json` - Tool failure detection
- `case_12_span_parent_linking.json` - Span hierarchy
- `case_14_prompt_contamination.json` - Prompt in output
- And more...

### Production Gates Phase 2 (`test-fixtures/production-gates-phase2/`)
Extended production validation with real traces:
- `real-traces/` - Real production trace samples
- `manifest.yaml` - Phase 2 trace catalog

### Regression Tests (`test-fixtures/regression/`)
Regression test cases for adapter fixes:
- Tool status preservation tests
- Turn segmentation tests
- `run_regression_tests.py` - Regression test runner

### Validation Traces (`test-fixtures/validation/`)
Additional validation traces for specific scenarios

### Minimal/Noisy Traces (root level)
- `raw_trace_minimal.json` - Minimal valid trace
- `normalized_run_minimal.json` - Minimal normalized format
- `raw_trace_noisy_001.json` through `raw_trace_noisy_005.json` - Noisy traces
- `weird_001_noisy_toplevel.json` through `weird_006_ridiculous.json` - Edge cases
- `malformed_raw_trace.json` - Invalid JSON structure

### Configuration Files
- `judges.mock.yaml` - Mock judge configuration for testing
- `rubrics.test.yaml` - Test rubric definitions

### Expected Results (`test-fixtures/expected-results/`)
Expected normalized outputs for validation:
- `raw_trace_minimal.expected.json`
- `malformed_raw_trace.expected.json`
- `weird_001_noisy_toplevel.expected.json`
- `weird_002_mixed_fields.expected.json`
- `weird_003_tool_calls.expected.json`
- `weird_004_malformed.expected.json`

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

### Baseline Test Failures
If baseline tests fail:
1. Check that test fixtures exist in `test-fixtures/baseline/`
2. Verify `expected_outcomes.yaml` is present and valid
3. Review adapter logs for parsing errors
4. Compare actual vs expected metrics
5. See [Baseline Testing Guide](../../guides/BASELINE_TESTING_GUIDE.md) for detailed debugging

## Quick Start: Baseline Testing

To get started with baseline validation testing:

1. **Ensure test corpus exists**:
   ```bash
   ls agent-eval/test-fixtures/baseline/
   ```

2. **Run baseline tests**:
   ```bash
   pytest agent-eval/tests/baseline/ -v
   ```

3. **Review results**: All 10 traces should pass with exact metric matches

4. **See detailed guide**: [Baseline Testing Guide](../../guides/BASELINE_TESTING_GUIDE.md)
