# Files to Commit

## Core Code Changes (Modified)

### Pipeline & Adapter
- `agent_eval/pipeline.py` - Pipeline orchestration improvements
- `agent_eval/adapters/generic_json/adapter.py` - Adapter enhancements

### Evaluator
- `agent_eval/evaluators/trace_eval/deterministic_metrics.py` - Metrics calculation

### Schemas
- `agent_eval/schemas/normalized_run.schema.json` - Schema updates
- `agent_eval/schemas/results.schema.json` - Results schema

## New Test Files (Untracked - Add)

### Component Tests
- `agent_eval/tests/component/` - Full directory of component tests
  - `test_pipeline_e2e.py`
  - `test_output_validation.py`
  - `test_judge_orchestration.py`
  - `test_score_aggregation.py`
  - `test_rubric_resolution.py`
  - `test_evidence_selection.py`
  - `test_evaluator_contract.py`
  - `test_metrics_validation.py`
  - `test_corpus_validation.py`

### Baseline Tests
- `agent_eval/tests/baseline/` - Baseline corpus tests
  - `test_baseline_corpus.py`

### Preservation & Regression Tests
- `agent_eval/tests/test_adapter_preservation_segmentation.py`
- `agent_eval/tests/test_adapter_preservation_tool_status.py`
- `agent_eval/tests/test_adapter_segmentation_regression.py`
- `agent_eval/tests/test_adapter_tool_status_regression.py`

### Production Gate Tests
- `agent_eval/tests/test_production_gates.py`
- `agent_eval/tests/test_production_gates_phase2.py`
- `agent_eval/tests/test_production_gates_phase2_extended.py`

### Test Utilities
- `agent_eval/tests/test_utils.py`

## New Tools (Untracked - Add)
- `agent_eval/tools/inspect_adapter_stages.py` - Debugging tool

## Test Fixtures (Untracked - Add)

### Baseline Corpus
- `test-fixtures/baseline/` - Full directory
  - All trace files (good_*, bad_*, partial_*, weird_*, ambiguous_*)
  - `manifest.yaml`
  - `expected_outcomes.yaml`

### Production Gates Phase 2 (ONLY)
- `test-fixtures/production-gates-phase2/` - Full directory
  - Config drift cases
  - Fuzz mutation cases
  - Performance test cases
  - Real traces (if any)

### Expected Results
- `test-fixtures/expected-results/` - Full directory
  - Expected output files for validation

## Documentation & Guides

### Keep (Valuable)
- ✅ `guides/RELEASE_GATE.md` - Pre-push quality gate documentation
- ✅ `guides/OTEL_EXTRACTION_FINDINGS.md` - AgentCore OTEL findings

### Exclude (Temporary validation docs)
- ❌ `guides/PRE_COMMIT_VALIDATION.md` - Temporary validation doc
- ❌ `guides/FINAL_RUNTIME_CHECK.md` - Temporary validation doc
- ❌ `guides/CODE_CHANGES_SINCE_LAST_COMMIT.md` - Temporary tracking
- ❌ `guides/COMMIT_FILES_LIST.md` - This file (temporary)
- ❌ `guides/COMMIT_READY.md` - Temporary
- ❌ `guides/FILES_TO_COMMIT.md` - Temporary
- ❌ `guides/PRODUCTION_TESTING_COMPLETE_SUMMARY.md` - Temporary
- ❌ `guides/PRODUCTION_VALIDATION_RESULTS.md` - Temporary
- ❌ `guides/REGRESSION_TESTING_COMPLETE.md` - Temporary
- ❌ `guides/RUNNING_PRODUCTION_TESTS.md` - Temporary
- ❌ `guides/SCHEMA_GAPS_FIXED.md` - Temporary
- ❌ `guides/BASELINE_TESTING_SUMMARY.md` - Temporary
- ❌ `guides/BASELINE_TRACES_SUMMARY.md` - Temporary

## Files to EXCLUDE from Commit

### Test Fixtures (Remove)
- ❌ `test-fixtures/production-gates/` - Phase 1, superseded by phase2
- ❌ `test-fixtures/regression/` - Not needed for this commit
- ❌ `test-fixtures/validation/` - Temporary validation output

### Build Artifacts
- ❌ `agentic_eval.egg-info/` - Build artifact
- ❌ `test-weird-output/` - Test output directory

### Temporary Scripts
- ❌ `git-commit-commands.sh` - Temporary script
- ❌ `run_validation_traces.py` - Temporary validation script
- ❌ `../commit-commands.sh` - Temporary script

### Spec Files (Not part of code commit)
- ❌ `../.kiro/specs/generic-json-adapter/requirements.md`
- ❌ `../.kiro/specs/generic-json-adapter/tasks.md`
- ❌ `../README.md` (root README, not agent-eval)

## Deleted Files (Already staged for deletion)
- ✅ Old test fixtures (being replaced by baseline/)
- ✅ Old guide files (being replaced by new structure)

## Summary

**To commit:**
- 5 modified core files
- ~30 new test files
- 1 new tool
- ~30 test fixture files (baseline + phase2 + expected-results)
- 2 documentation updates (READMEs)
- 2 guide files (RELEASE_GATE.md, OTEL_EXTRACTION_FINDINGS.md)

**To exclude:**
- ~12 temporary validation/tracking docs in guides/
- production-gates/ (phase 1)
- regression/ fixtures
- validation/ output
- Build artifacts
- Temporary scripts
- Spec files
