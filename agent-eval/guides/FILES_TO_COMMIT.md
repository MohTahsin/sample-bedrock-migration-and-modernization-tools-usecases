# Files to Commit - Complete List

## Summary

This document lists ALL files and folders being committed to the `agent-evaluation` branch.

## Core Implementation (agent_eval/)

### 1. Adapters
```
agent_eval/adapters/
├── generic_json/
│   ├── __init__.py
│   ├── adapter.py              # Main adapter logic
│   ├── adapter_config.yaml     # Default configuration
│   ├── config_loader.py        # Config loading
│   ├── config_schema.py        # Config validation
│   └── exceptions.py           # Custom exceptions
└── base.py                     # Base adapter interface
```

### 2. Evaluators
```
agent_eval/evaluators/
├── trace_eval/
│   ├── __init__.py
│   ├── runner.py               # Main evaluation runner
│   ├── input_validator.py      # Schema validation
│   ├── output_writer.py        # Output file writing
│   ├── deterministic_metrics.py # Metrics calculation
│   ├── timestamp_policy.py     # Timestamp handling
│   ├── logging_config.py       # Logging setup
│   └── judging/
│       ├── __init__.py
│       ├── job_builder.py      # Judge job creation
│       ├── queue_runner.py     # Concurrent execution
│       ├── aggregator.py       # Result aggregation
│       ├── evidence.py         # Evidence extraction
│       ├── models.py           # Data models
│       ├── rate_limiter.py     # Rate limiting
│       └── retry_policy.py     # Retry logic
└── results/                    # (empty placeholder)
```

### 3. Judges
```
agent_eval/judges/
├── __init__.py
├── judge_client.py             # Base judge client
├── mock_client.py              # Mock judge for testing
├── client_factory.py           # Judge client factory
├── judge_config_schema.py      # Config validation
└── exceptions.py               # Judge exceptions
```

### 4. Providers
```
agent_eval/providers/
├── __init__.py
└── bedrock_client.py           # AWS Bedrock provider
```

### 5. Schemas
```
agent_eval/schemas/
├── normalized_run.schema.json      # NormalizedRun schema
├── judge_config.schema.json        # Judge config schema
├── judge_response.schema.json      # Judge response schema
├── judge_run_record.schema.json    # Judge run record schema
├── rubric.schema.json              # Rubric schema
├── results.schema.json             # Results schema
└── trace_eval_output.schema.json   # Trace eval output schema
```

### 6. Tools
```
agent_eval/tools/
├── __init__.py
├── README.md
├── check_otel_structure.py
├── cloudwatch_logs_fixture_exporter.py
└── agentcore_pipeline/
    ├── __init__.py
    ├── __main__.py
    ├── README.md
    ├── WRAPPER_README.md
    ├── 01_export_turns_from_app_logs.py    # OTEL extraction
    ├── 02_build_session_trace_index.py     # Session indexing
    ├── 03_add_xray_steps_and_latency.py    # X-Ray enrichment
    └── run_from_agentcore_arn.py           # ARN wrapper
```

### 7. Tests
```
agent_eval/tests/
├── __init__.py
├── README.md
├── test_adapter_integration.py
├── test_adapter_resilience.py
├── test_cloudwatch_export.py
├── test_config_loader.py
├── test_discovery_integration.py
├── test_error_handling.py
├── test_input_validator.py
├── test_integration.py
├── test_judge_config.py
├── test_log_group_discovery.py
├── test_module_imports.py
├── test_property_bounded_concurrency.py
├── test_run_from_agentcore_arn.py
├── test_run_from_agentcore_arn_pipeline.py
├── test_sample_traces.py
├── test_trace_eval_integration.py
├── test_01_export_turns.py
└── test_validation.py
```

### 8. CLI and Pipeline
```
agent_eval/
├── __init__.py
├── cli.py                      # CLI entry point
└── pipeline.py                 # Pipeline orchestrator
```

## Test Infrastructure

### 1. Test Fixtures
```
test-fixtures/
├── judges.mock.yaml            # Mock judge config
├── rubrics.test.yaml           # Test rubrics
├── raw_trace_minimal.json      # Minimal trace
├── normalized_run_minimal.json # Minimal normalized
├── malformed_raw_trace.json    # Negative test case
├── weird_001_noisy_toplevel.json
├── weird_002_mixed_fields.json
├── weird_003_tool_calls.json
├── weird_004_malformed.json
├── weird_005_multi_turn.json
├── weird_006_ridiculous.json
└── expected-results/
    ├── raw_trace_minimal.expected.json
    ├── malformed_raw_trace.expected.json
    ├── weird_001_noisy_toplevel.expected.json
    ├── weird_002_mixed_fields.expected.json
    ├── weird_003_tool_calls.expected.json
    └── weird_004_malformed.expected.json
```

### 2. Scripts
```
scripts/
├── smoke_test_raw_traces.sh    # Smoke test runner
└── pre_push_check.sh            # Pre-push quality gate
```

### 3. Makefile
```
Makefile                         # Test automation targets
```

## Documentation

```
README.md                        # Main user guide
guides/
├── COMMIT_READY.md             # Commit instructions
├── RELEASE_GATE.md             # Release gate documentation
├── VALIDATION_RESULTS.md       # AgentCore validation results
├── OTEL_EXTRACTION_FINDINGS.md # OTEL implementation details
├── FIX_PROGRESS.md             # Progress tracking
└── FILES_TO_COMMIT.md          # This file
```

## Configuration

```
.gitignore                       # Updated exclusions
```

## Helper Files (Not Committed to Git)

These files are in the working directory but excluded by .gitignore:

```
COMMIT_MESSAGE.txt               # Commit message (local helper)
git-commit-commands.sh           # Commit script (local helper)
validate_*.py                    # Validation scripts (temporary)
test_*.py (root level)           # Test scripts (temporary)
*_VALIDATION.md                  # Validation docs (temporary)
*_SUMMARY.md                     # Summary docs (temporary)
*_FIXES*.md                      # Fix tracking (temporary)
stich-all.text                   # Temporary file
```

## File Count Summary

- **Core Python modules**: ~50 files
- **Test files**: ~20 files
- **Schema files**: 7 files
- **Test fixtures**: ~20 files
- **Scripts**: 2 files
- **Documentation**: 6 files
- **Configuration**: 1 file

**Total**: ~106 production files

## What's NOT Being Committed

Excluded by .gitignore:
- `.kiro/specs/` - Development specs
- `.kiro/steering/` - Development steering
- `validate_*.py` - Temporary validation scripts
- `test_*.py` (root level) - Temporary test scripts
- `*_VALIDATION.md` - Temporary validation docs
- `*_SUMMARY.md` - Temporary summary docs
- Test outputs (`.smoke-test-output/`, `test-output/`, etc.)
- Python cache (`__pycache__/`, `*.pyc`)
- Virtual environments (`.venv/`)
- Coverage reports (`.coverage`, `htmlcov/`)

## Verification

To see exactly what will be committed:

```bash
cd agent-eval
git status --short
```

To verify file count:

```bash
git ls-files | wc -l
```
