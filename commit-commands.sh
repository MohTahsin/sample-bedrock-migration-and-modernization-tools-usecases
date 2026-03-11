#!/bin/bash
# Complete commit for agent-evaluation branch

# Stage .gitignore changes
git add .gitignore

# Stage all new agent-eval components
git add agent-eval/agent_eval/evaluators/
git add agent-eval/agent_eval/judges/
git add agent-eval/agent_eval/providers/
git add agent-eval/agent_eval/adapters/generic_json/exceptions.py
git add agent-eval/agent_eval/pipeline.py

# Stage new schemas
git add agent-eval/agent_eval/schemas/judge_config.schema.json
git add agent-eval/agent_eval/schemas/judge_response.schema.json
git add agent-eval/agent_eval/schemas/judge_run_record.schema.json
git add agent-eval/agent_eval/schemas/results.schema.json
git add agent-eval/agent_eval/schemas/rubric.schema.json
git add agent-eval/agent_eval/schemas/trace_eval_output.schema.json

# Stage all new tests
git add agent-eval/agent_eval/tests/test_01_export_turns.py
git add agent-eval/agent_eval/tests/test_adapter_integration.py
git add agent-eval/agent_eval/tests/test_adapter_resilience.py
git add agent-eval/agent_eval/tests/test_cloudwatch_export.py
git add agent-eval/agent_eval/tests/test_config_loader.py
git add agent-eval/agent_eval/tests/test_discovery_integration.py
git add agent-eval/agent_eval/tests/test_error_handling.py
git add agent-eval/agent_eval/tests/test_input_validator.py
git add agent-eval/agent_eval/tests/test_integration.py
git add agent-eval/agent_eval/tests/test_judge_config.py
git add agent-eval/agent_eval/tests/test_log_group_discovery.py
git add agent-eval/agent_eval/tests/test_module_imports.py
git add agent-eval/agent_eval/tests/test_property_bounded_concurrency.py
git add agent-eval/agent_eval/tests/test_run_from_agentcore_arn.py
git add agent-eval/agent_eval/tests/test_run_from_agentcore_arn_pipeline.py
git add agent-eval/agent_eval/tests/test_sample_traces.py
git add agent-eval/agent_eval/tests/test_trace_eval_integration.py
git add agent-eval/agent_eval/tests/test_validation.py

# Stage AgentCore pipeline tools
git add agent-eval/agent_eval/tools/

# Stage documentation (guides only, per gitignore)
git add agent-eval/guides/

# Stage validation scripts
git add agent-eval/validate_aws_access.py
git add agent-eval/validate_get_agent_runtime.py
git add agent-eval/validate_log_data.py

# Stage test utilities
git add agent-eval/test_rubric_loader.py
git add agent-eval/stich-all.text

# Stage egg-info (package metadata)
git add agent-eval/agentic_eval.egg-info/

# Stage modified files
git add agent-eval/agent_eval/adapters/generic_json/
git add agent-eval/agent_eval/cli.py
git add agent-eval/agent_eval/schemas/normalized_run.schema.json
git add agent-eval/agent_eval/tests/README.md
git add agent-eval/README.md
git add README.md

# Show what will be committed
echo "=== Files staged for commit ==="
git status --short | grep "^A"

echo ""
echo "=== Ready to commit with the following message ==="
cat << 'EOF'

feat(agent-eval): Complete trace evaluation system with AgentCore OTEL support

Major Features:
- Trace evaluation pipeline with LLM-as-judge
- Generic JSON adapter with resilience
- AgentCore pipeline with OTEL extraction
- Property-based testing framework

Components Added:

1. Trace Evaluation System (evaluators/)
   - Runner with bounded concurrency
   - Judge orchestration and aggregation
   - Rate limiting and retry policies
   - Deterministic metrics calculation
   - Output writer with streaming

2. Judge Integration (judges/)
   - Bedrock judge client
   - Mock client for testing
   - Judge config schema validation

3. Providers (providers/)
   - Bedrock client wrapper
   - Error handling and retries

4. Generic JSON Adapter (adapters/generic_json/)
   - Config-driven field mapping
   - Resilient parsing with fallbacks
   - Schema validation
   - Exception handling

5. AgentCore Pipeline (tools/agentcore_pipeline/)
   - Script 1: Export turns with OTEL support
   - Script 2: Build session trace index
   - Script 3: Add X-Ray steps and latency
   - ARN wrapper with auto-discovery
   - OTEL stream extraction (Phase 1)

6. Schemas (schemas/)
   - Judge config, response, run record
   - Results and rubric schemas
   - Trace eval output schema

7. Tests (tests/)
   - Integration tests for all components
   - Property-based tests for concurrency
   - Adapter resilience tests
   - CloudWatch export tests
   - End-to-end pipeline tests

8. Documentation (guides/)
   - Validation results (6-step validation)
   - Fix progress tracking
   - OTEL extraction findings

OTEL Implementation (Phase 1):
- ✅ Add --log-stream-kind otel to Script 1
- ✅ Fix timestamp conversion (nanoseconds)
- ✅ Fix session_id extraction
- ✅ Filter for valid traceId events
- ⚠️  user_query empty (CloudWatch Insights limitation)

Test Results:
- 45 tests passing (30 unit + 15 pipeline)
- 1000 OTEL turns extracted successfully
- Timestamps, trace_id, span_id working correctly
- 7.5% of events have session_id (expected)

Configuration:
- Updated .gitignore to exclude specs, steering, and temp files
- Excluded MD files outside guides/ directory

Next Steps:
- Phase 2: Wire wrapper to OTEL mode by default
- Phase 3: Validate extraction quality
- Phase 4: End-to-end pipeline test

EOF

echo ""
echo "=== To commit, run: ==="
echo 'git commit -F- << "COMMITMSG"'
echo '<paste the commit message above>'
echo 'COMMITMSG'
