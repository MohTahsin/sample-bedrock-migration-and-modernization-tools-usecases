# Agent Evaluation Framework

Evaluate agent behavior and response quality from recorded traces — without invoking the agent runtime.

This framework analyzes previously recorded agent execution traces and produces evaluation metrics for:

- **Orchestrator responses**: Decision-making patterns and reasoning quality
- **Tool/sub-agent usage**: Execution flow and tool selection accuracy
- **Latency and failures**: Performance metrics and error patterns
- **Correctness vs golden answers**: Output quality using judge models

It is designed for offline evaluation, making it suitable for:

- CI/CD pipelines
- Regression testing
- Batch trace analysis
- Production observability audits

## Core Idea

Instead of running the agent again, this framework evaluates recorded traces.

```
Agent runtime
      │
      │ produces traces
      ▼
Trace JSON
      │
      ▼
Agent Evaluation Framework
      │
      ▼
Metrics + evaluation results
```

**Supported trace sources:**
- Custom agent logs
- OpenTelemetry traces
- CloudWatch exports
- AgentCore traces (in progress)

## Quick Start (Recommended Path)

### Step 1 — Bring Your Raw Trace JSON

The easiest way to use the framework is to bring your own raw trace JSON file.

**Example raw trace:**
```json
{
  "events": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "event_type": "user_message",
      "text": "What is the refund policy?",
      "session_id": "session-123"
    },
    {
      "timestamp": "2024-01-15T10:30:01Z",
      "event_type": "llm_output",
      "text": "The refund policy allows returns within 30 days.",
      "session_id": "session-123"
    }
  ]
}
```

Save this as: `trace.json`

### Step 2 — Run the Evaluation Pipeline

```bash
python -m agent_eval.cli \
  --input trace.json \
  --judge-config test-fixtures/judges.mock.yaml \
  --rubrics test-fixtures/rubrics.test.yaml \
  --output-dir ./output
```

**Output files:**
```
output/
  ├── trace_eval.json
  ├── results.json
  └── judge_runs.jsonl
```

These contain:
- Deterministic metrics
- Rubric scores
- Judge model evaluations

## Input Types Supported

The pipeline accepts two types of inputs.

### 1️⃣ Raw Traces

Any JSON trace containing agent events.

**Example:** `raw_trace.json`

The framework automatically normalizes the trace using the Generic JSON Adapter.

### 2️⃣ Normalized Runs

If you already have normalized traces: `normalized_run.json`

You can run evaluation directly:

```bash
python -m agent_eval.cli \
  --input normalized_run.json \
  --judge-config judges.yaml \
  --rubrics rubrics.yaml \
  --output-dir ./output
```

## Evaluation Output

The framework generates multiple artifacts.

### `trace_eval.json`

Contains evaluation metadata and deterministic metrics.

**Example:**
```json
{
  "run_id": "abc123",
  "metrics": {
    "turns": 2,
    "tool_calls": 1,
    "latency_ms": 1320
  }
}
```

### `results.json`

Contains final rubric scores.

**Example:**
```json
{
  "rubric_scores": {
    "correctness": 0.9,
    "tool_usage": 0.8
  }
}
```

### `judge_runs.jsonl`

Raw judge model outputs. Used for debugging or auditing.

## Architecture

The system follows a three-stage architecture.

```
RAW TRACE
    │
    ▼
Extractor (optional)
    │
    ▼
Adapter
    │
    ▼
NormalizedRun
    │
    ▼
Evaluator
    │
    ▼
Metrics + Judge Scores
```

### Extractor

Collects traces from sources such as:
- CloudWatch
- AgentCore
- OpenTelemetry
- Log exports

### Adapter

Converts arbitrary traces into a standardized schema: **NormalizedRun**

### Evaluator

Runs evaluation logic:
- Deterministic metrics
- Rubric scoring
- LLM judges

## Generic JSON Adapter

The adapter converts arbitrary traces into a standardized schema.

**Supported formats:**
- OpenTelemetry
- CloudWatch
- Custom logs
- Generic JSON traces

**Example usage:**
```python
from agent_eval.adapters.generic_json import adapt

normalized = adapt("trace.json")

print(normalized["run_id"])
print(len(normalized["turns"]))
```

## CloudWatch Log Export (Optional)

You can export logs from CloudWatch and evaluate them.

```bash
python -m agent_eval.tools.cloudwatch_extractor \
  --log-group /aws/lambda/my-agent \
  --days 7 \
  --output-dir ./exports
```

This produces: `events.json`

Then evaluate:

```bash
python -m agent_eval.cli \
  --input exports/events.json \
  --judge-config judges.yaml \
  --rubrics rubrics.yaml \
  --output-dir ./output
```

## AgentCore Trace Extraction (In Progress)

The framework is adding direct AgentCore integration.

**Goal:**
```
AgentCore Runtime ARN
        │
        ▼
CloudWatch OTEL traces
        │
        ▼
NormalizedRun
        │
        ▼
Evaluation metrics
```

**Example:**
```bash
python -m agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn \
  --agent-runtime-arn arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME_ID \
  --region us-east-1 \
  --minutes 60 \
  --output-dir ./agentcore-output
```

**Generated files:**
```
agentcore-output/
  ├── discovery.json
  ├── 01_session_turns.json
  ├── 02_session_enriched_runtime.json
  └── 03_turns_merged_normalized.json
```

These can then be evaluated with the pipeline.

### AgentCore Log Architecture

AgentCore stores observability data in OpenTelemetry format.

```
/aws/bedrock-agentcore/runtimes/{runtime_id}-DEFAULT
    ├── [runtime-logs] streams
    └── otel-rt-logs stream
```

Only the **OTEL stream** contains structured trace data.

**Example OTEL event:**
```json
{
  "traceId": "69ab463d578ac35a3fd0daca2dba3f28",
  "spanId": "5513faadaa4c76e4",
  "timeUnixNano": 1772832322599135148,
  "attributes": {
    "session.id": "session-123"
  }
}
```

### Current Development Status

| Feature | Status |
|---------|--------|
| Generic JSON Adapter | ✅ Complete |
| Evaluation Pipeline | ✅ Complete |
| CloudWatch Exporter | ✅ Complete |
| AgentCore ARN Wrapper | ⚠️ In Progress |
| OTEL Trace Extraction | ⚠️ In Progress |

**Phase 1 Complete:**
- ✅ 1000 OTEL turns extracted successfully
- ✅ Timestamps, trace_id, span_id working correctly
- ✅ session_id extraction (7.5% of events, as expected)
- ⚠️ user_query extraction blocked by CloudWatch Insights limitations

**Next Steps:**
- Phase 2: Wire wrapper to OTEL mode by default
- Phase 3: Validate extraction quality
- Phase 4: End-to-end pipeline testing

See `guides/` directory for detailed validation results and progress tracking.

## Installation

```bash
cd agent-eval
pip install -e .
```

## Running Tests

Run the full test suite:

```bash
pytest agent_eval/tests/ -v
```

Run specific test suites:

```bash
# Adapter tests
pytest agent_eval/tests/test_adapter_integration.py -v

# Evaluation tests
pytest agent_eval/tests/test_trace_eval_integration.py -v

# AgentCore tests
pytest agent_eval/tests/test_run_from_agentcore_arn.py -v
```

### Pre-Push Quality Gate

Before pushing code, run the comprehensive quality gate:

```bash
make pre-push
```

This runs:
- Unit tests
- Smoke tests (weird traces)
- Integration tests
- Negative path tests
- Schema validation

See `guides/RELEASE_GATE.md` for details.

## Project Structure

```
agent-eval/
  ├── agent_eval/
  │   ├── adapters/          # Trace normalization
  │   ├── evaluators/        # Evaluation pipeline
  │   ├── judges/            # LLM judge clients
  │   ├── schemas/           # JSON schemas
  │   ├── tools/             # Extraction utilities
  │   │   ├── cloudwatch_extractor.py
  │   │   └── agentcore_pipeline/
  │   └── cli.py             # CLI interface
  ├── tests/                 # Test suite
  ├── test-fixtures/         # Sample data
  └── guides/                # Documentation
```

## Contributing

This module uses isolated dependencies.

**Install development environment:**
```bash
pip install -e ".[dev]"
```

**Run tests:**
```bash
pytest
```

## Summary

This framework enables offline evaluation of agent traces.

**Primary workflow:**
```
Bring trace JSON
        │
        ▼
Normalize trace
        │
        ▼
Run evaluation pipeline
        │
        ▼
Get metrics + rubric scores
```

**Future workflow:**
```
AgentCore Runtime
        │
        ▼
Automatic trace extraction
        │
        ▼
Evaluation metrics
```

---

For detailed documentation on specific components, see:
- **Generic JSON Adapter**: See "Generic JSON Adapter" section above
- **AgentCore Integration**: `agent_eval/tools/agentcore_pipeline/README.md`
- **Validation Results**: `guides/VALIDATION_RESULTS.md`
- **Progress Tracking**: `guides/FIX_PROGRESS.md`
