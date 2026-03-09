# Baseline Validation Tests

## Purpose

This directory contains deterministic baseline validation tests that ensure the non-LLM components of the evaluation system are stable and accurate before introducing real LLM judges.

## What We Test

- **Adapter correctness**: Parsing various trace formats
- **Deterministic metrics**: Turn counts, tool counts, latency calculations
- **Tool tracking**: Call/result pairing, deduplication, failure handling
- **Edge cases**: Noise filtering, orphan results, duplicate events

## Test Corpus

The tests use a fixed corpus of 10 traces located in `test-fixtures/baseline/`:

- 3 clearly good traces
- 3 clearly bad traces
- 2 partial/ambiguous traces
- 2 tool-path weird traces

Each trace has known expected outcomes defined in `expected_outcomes.yaml`.

## Running Tests

```bash
# Run all baseline tests
pytest agent-eval/tests/baseline/ -v

# Run with baseline marker
pytest agent-eval/tests/ -m baseline -v

# Run specific test class
pytest agent-eval/tests/baseline/test_baseline_corpus.py::TestGoodTraces -v
```

## Test Structure

```
baseline/
├── __init__.py                  # Package initialization
├── README.md                    # This file
└── test_baseline_corpus.py      # Main baseline validation tests
```

## Success Criteria

All tests must pass with:
- Exact matches for turn counts and tool counts
- Latency values within ±5% tolerance
- No adapter crashes or parsing errors
- Proper handling of all edge cases

## Documentation

See [Baseline Testing Guide](../../../guides/BASELINE_TESTING_GUIDE.md) for comprehensive documentation on:
- Test philosophy and strategy
- Detailed trace descriptions
- Expected outcomes reference
- Debugging guidance
- Maintenance procedures
