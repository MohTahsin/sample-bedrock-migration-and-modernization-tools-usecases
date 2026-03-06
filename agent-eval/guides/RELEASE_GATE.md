# Release Gate System

This document describes the release gate system that ensures code quality before every push.

## Overview

The release gate system prevents regressions by validating that:
- All unit tests pass
- Smoke tests pass for weird/edge-case traces
- Integration tests work end-to-end
- Negative paths fail gracefully
- Output matches expected results

## Quick Start

Before every push, run:

```bash
make pre-push
```

Or directly:

```bash
./scripts/pre_push_check.sh
```

## Components

### 1. Golden Test Pack

Located in `test-fixtures/`, these are permanent weird traces that validate adapter resilience:

- `raw_trace_minimal.json` - Clean minimal trace
- `weird_001_noisy_toplevel.json` - Noisy top-level fields
- `weird_002_mixed_fields.json` - Mixed field names
- `weird_003_tool_calls.json` - Tool calls with junk metadata
- `weird_004_malformed.json` - Malformed but recoverable
- `malformed_raw_trace.json` - Negative case (should fail)

### 2. Expected Results

Located in `test-fixtures/expected-results/`, each trace has an expected outcome:

```json
{
  "expected_exit_code": 0,
  "min_turns": 1,
  "max_turns": 2,
  "expected_tool_calls": 1,
  "min_confidence": 0.5,
  "description": "Tool calls with junk metadata"
}
```

**Fields:**
- `expected_exit_code`: Expected CLI exit code (0 = success, 1 = failure)
- `min_turns`: Minimum number of turns expected
- `max_turns`: Maximum number of turns expected
- `expected_tool_calls`: Expected number of tool calls
- `min_confidence`: Minimum confidence score (0.0-1.0)
- `description`: Human-readable description

### 3. Smoke Test Script

`scripts/smoke_test_raw_traces.sh` runs all weird traces and validates:

- Exit code matches expected
- Output files exist (`trace_eval.json`, `results.json`)
- Output JSON is valid
- Turn count is within expected range
- Tool call count matches expected
- Confidence is above minimum threshold

**Usage:**
```bash
./scripts/smoke_test_raw_traces.sh
```

**Output:**
```
=========================================
  Raw Trace Smoke Test Suite
=========================================

Running smoke tests...

Testing raw_trace_minimal... PASS
Testing weird_001_noisy_toplevel... PASS
Testing weird_002_mixed_fields... PASS
Testing weird_003_tool_calls... PASS
Testing weird_004_malformed... PASS
Testing malformed_raw_trace... PASS (failed as expected)

=========================================
  Test Summary
=========================================
Total tests: 6
Passed: 6
Failed: 0

✅ All smoke tests PASSED
```

### 4. Pre-Push Check Script

`scripts/pre_push_check.sh` runs comprehensive quality checks:

1. **Unit Tests**: All pytest tests
2. **Smoke Tests**: Weird trace validation
3. **Integration Test**: Normalized input end-to-end
4. **Negative Path Test**: Malformed input fails gracefully
5. **Import Check**: No import errors
6. **Schema Validation**: Output conforms to schema

**Usage:**
```bash
./scripts/pre_push_check.sh
```

**Output:**
```
=========================================
  Pre-Push Quality Gate
=========================================

▶ Unit Tests
✅ PASS

▶ Smoke Tests (Raw Traces)
✅ PASS

▶ Integration Test (Normalized)
✅ PASS

▶ Negative Path Test (Malformed)
✅ PASS

▶ Import Check
✅ PASS

▶ Schema Validation
✅ PASS

=========================================
  Summary
=========================================
✅ All checks PASSED

Safe to push!
```

### 5. Makefile Targets

Convenient make targets for common tasks:

```bash
# Install dependencies
make install

# Run unit tests only
make test-unit

# Run smoke tests only
make test-smoke

# Run unit + smoke tests
make test-local

# Run full pre-push gate
make pre-push

# Alias for pre-push
make test

# Clean test artifacts
make clean
```

## Push Criteria

**DO NOT PUSH** if any of these fail:
- ❌ Unit tests
- ❌ Smoke tests
- ❌ Integration test
- ❌ Negative path test
- ❌ Import check
- ❌ Schema validation

**If behavior changed:**
- Update expected results in `test-fixtures/expected-results/`
- Document the change in commit message
- Ensure change is intentional, not a regression

## Adding New Test Cases

### 1. Add a new weird trace

Create `test-fixtures/weird_007_new_case.json`:

```json
{
  "events": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "weird_field": "unexpected_value",
      ...
    }
  ]
}
```

### 2. Add expected results

Create `test-fixtures/expected-results/weird_007_new_case.expected.json`:

```json
{
  "expected_exit_code": 0,
  "min_turns": 1,
  "max_turns": 1,
  "expected_tool_calls": 0,
  "min_confidence": 0.3,
  "description": "New edge case description"
}
```

### 3. Run smoke tests

```bash
make test-smoke
```

### 4. Verify output

Check `.smoke-test-output/weird_007_new_case/` for actual results.

### 5. Adjust expectations if needed

If actual results differ from expected, either:
- Fix the code (if it's a bug)
- Update expected results (if behavior is correct)

## Troubleshooting

### Smoke test fails

1. Check logs in `.smoke-test-output/<test_name>/`
2. Review `stdout.log` and `stderr.log`
3. Inspect `trace_eval.json` and `results.json`
4. Compare actual vs expected results

### Pre-push check fails

1. Run individual checks:
   ```bash
   make test-unit
   make test-smoke
   ```
2. Fix failures before pushing
3. Update expected results if behavior changed intentionally

### Expected results out of date

If you intentionally changed behavior:

1. Run smoke tests to see actual results
2. Update `test-fixtures/expected-results/*.expected.json`
3. Document change in commit message
4. Re-run pre-push check

## Best Practices

1. **Always run pre-push before pushing**
   ```bash
   make pre-push
   ```

2. **Add tests for new features**
   - Add weird trace if new adapter behavior
   - Add expected results
   - Verify smoke tests pass

3. **Update expected results intentionally**
   - Don't blindly update to make tests pass
   - Understand why results changed
   - Document in commit message

4. **Keep golden traces minimal**
   - Focus on edge cases and weird inputs
   - Don't add redundant traces
   - Each trace should test a specific scenario

5. **Review smoke test output**
   - Don't just check pass/fail
   - Review actual metrics occasionally
   - Ensure confidence scores are reasonable

## CI/CD Integration

To integrate with CI/CD:

```yaml
# Example GitHub Actions
- name: Run pre-push checks
  run: |
    cd agent-eval
    make pre-push
```

```yaml
# Example GitLab CI
test:
  script:
    - cd agent-eval
    - make pre-push
```

## Summary

The release gate system ensures:
- ✅ Code quality before every push
- ✅ No regressions in adapter behavior
- ✅ Consistent output for weird inputs
- ✅ Graceful failure for malformed inputs
- ✅ Schema compliance

**Remember:** Run `make pre-push` before every push!
