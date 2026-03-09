# Agent Evaluation Framework

Evaluate agent behavior and response quality from recorded execution traces without re-running the agent runtime. The framework uses deterministic metrics and configurable rubric-based judges (including LLM judges where configured).

## Why This Exists

Most agent evaluation systems require re-running the agent runtime. This framework evaluates previously recorded execution traces instead, making it suitable for offline analysis, CI pipelines, and regression testing.

## What This Framework Does

- Evaluates recorded agent execution traces
- Computes deterministic execution metrics (turn counts, tool usage, latency)
- Scores traces using configurable rubric-based judges
- Produces structured evaluation artifacts

## What This Framework Does Not Do

- It does not run the agent runtime
- It does not require access to the original agent infrastructure
- It does not depend on a specific agent framework

## Core Idea

The framework accepts JSON traces containing agent execution events. These traces are typically exported from custom runtimes, OpenTelemetry pipelines, CloudWatch logs, or AgentCore observability data.

Raw traces are normalized into a standard schema and then evaluated using deterministic metrics and optional judge-based scoring.

## Architecture

The system follows a three-stage pipeline with clear separation of concerns.

```
CLI
(agent_eval/cli.py)
      │
      ▼
Generic JSON Adapter
(agent_eval/adapters/generic_json/adapter.py)
      │
      ▼
NormalizedRun (standard schema)
(agent_eval/schemas/normalized_run.schema.json)
      │
      ▼
Trace Evaluator
(agent_eval/evaluators/trace_eval/runner.py)
   ├── Deterministic metrics (deterministic_metrics.py)
   └── Judge-based evaluation:
       │
       ├─ Evidence Extraction (judging/evidence.py)
       │
       ├─ Judge Job Queue (judging/queue_runner.py)
       │
       ├─ Parallel Judge Execution Workers
       │
       └─ Score Aggregation (judging/aggregator.py)
      │
      ▼
Evaluation Artifacts
   ├── results.json
   ├── trace_eval.json
   └── judge_runs.jsonl
```

### Two Types of Evaluation

The framework combines two evaluation approaches:

**Deterministic metrics**
- Turn counts
- Tool usage statistics
- Latency measurements
- Execution errors

**LLM judge evaluation**
- Correctness
- Groundedness
- Reasoning quality
- Tool usage quality

## Installation

Requires Python 3.11+

```bash
git clone https://github.com/<org>/agent-eval.git
cd agent-eval
pip install -e .
```

## Typical Workflow

1. Export trace logs from your agent system
2. Run the evaluation pipeline
3. Inspect results.json and trace_eval.json
4. Use outputs for regression testing or quality analysis

## 2-Minute Runnable Example

Get started immediately with a working example:

```bash
# Run evaluation on sample trace
python -m agent_eval.cli \
  --input test-fixtures/baseline/good_001_direct_answer.json \
  --judge-config test-fixtures/baseline/judges.mock.yaml \
  --rubrics test-fixtures/baseline/rubrics.test.yaml \
  --output-dir ./output
```

**Expected output:**
```
output/
  ├── results.json              # Final evaluation scores
  ├── trace_eval.json           # Detailed metrics and metadata
  ├── judge_runs.jsonl          # Raw judge outputs
  └── normalized_run.*.json     # Normalized trace artifact
```

### Artifacts Explained

- `results.json` → Final aggregated evaluation scores
- `trace_eval.json` → Detailed metrics and evidence
- `judge_runs.jsonl` → Raw judge model responses
- `normalized_run.*` → Adapter output for debugging

**Sample results.json:**
```json
{
  "run_id": "generated_3fa9d49d25a4a571",
  "deterministic_metrics": {
    "turn_count": 1,
    "tool_call_count": 0,
    "tool_result_count": 0,
    "tool_success_rate": null
  },
  "rubric_results": {
    "TRACE_COMPLETENESS": {
      "cross_judge_score": 3.0
    }
  }
}
```

## Judge Configuration

The framework supports two judge modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| **Mock Judges** | Deterministic responses for testing | CI/CD, testing, development |
| **Real Judges** | LLM-based scoring using Bedrock/OpenAI | Production evaluation, quality assessment |

The Quick Start uses mock judges so the evaluation pipeline can run without external APIs or credentials. Mock judges return deterministic placeholder scores for pipeline validation and do not measure actual semantic quality.

### Using Real LLM Judges

Judges are defined in a YAML configuration file passed to the CLI:

```yaml
judges:
  - judge_id: judge_1
    provider: bedrock
    model_id: anthropic.claude-3-sonnet-20240229-v1:0
    params:
      temperature: 0.0
      max_tokens: 1000
```

```bash
python -m agent_eval.cli \
  --input trace.json \
  --judge-config judges.yaml \
  --rubrics rubrics.yaml \
  --output-dir ./output
```

Typical setups use 1-5 judges for cross-model comparison and disagreement detection. The framework runs judges in parallel and aggregates scores with disagreement signals.

Additional providers can be added by implementing a judge client in `agent_eval/judges/`.

### Judge Execution Model

Judge evaluations are executed through a queue-based orchestration layer that enables parallel evaluation across judges and rubrics.

For each evaluation run:

```
Rubric × Judge combinations
        │
        ▼
Judge Job Queue (queue_runner.py)
        │
        ▼
Parallel judge execution
        │
        ▼
Score aggregation (aggregator.py)
```

Each judge evaluates the same extracted evidence independently. The framework then aggregates scores across judges to produce the final rubric result.

This design allows evaluation workloads to scale across multiple judges while keeping the pipeline deterministic and reproducible.

## Trace Input and Adapter

The adapter is the core innovation that makes this framework work with any trace format.

**Key capability:** Converts arbitrary JSON traces into a standardized schema automatically.

**Configuration:** Field mappings and segmentation strategies are defined in:
```
agent_eval/adapters/generic_json/adapter_config.yaml
```

Users can customize this file to extend mappings for their specific trace formats.

**How it works:**
1. Configurable field aliases map your trace fields to standard names
2. Turn segmentation strategies group events into conversation turns
3. Tool linking connects tool calls with their results
4. Confidence scoring tracks data quality

**Example usage:**
```python
from agent_eval.adapters.generic_json import adapt

normalized = adapt("trace.json")

print(normalized["run_id"])
print(len(normalized["turns"]))
```

### What You Need to Provide

For the built-in quick start, sample trace, judge config, and rubrics are already provided.

For your own data, you need:
- One raw trace JSON file
- One judge config YAML
- One rubric config YAML
- An output directory

### Minimal Trace Requirements

Raw traces should contain at minimum:

- **timestamp**: Event timing (ISO8601 or epoch)
- **event_type**: Event classification (e.g., "user_message", "llm_output")
- **text** or tool metadata: Content or tool execution data
- **session_id** or grouping identifier: To group related events

The Generic JSON Adapter maps these fields automatically using configurable aliases in `adapter_config.yaml`.

**Example minimal trace:**
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

## Debugging Adapter Behavior

If evaluation metrics look incorrect (wrong turn counts, missing tool calls, etc.), inspect the adapter pipeline:

```bash
python -m agent_eval.tools.inspect_adapter_stages trace.json
```

**Pipeline stages:**
- **Stage A**: Event normalization (field extraction, type classification)
- **Stage B**: Turn segmentation (grouping strategy, turn boundaries)
- **Stage C**: Tool linking (call/result pairing, status inference)
- **Stage D**: Confidence scoring (data quality penalties)

**Use when:**
- Debugging incorrect turn_count or tool_success_rate
- Diagnosing segmentation issues
- Verifying tool linking behavior
- Understanding how a specific trace is processed

## Evaluation Artifacts

- `results.json` → Final aggregated scores
- `trace_eval.json` → Detailed evaluation output
- `judge_runs.jsonl` → Raw judge responses
- `normalized_run.*.json` → Normalized trace used by evaluator

## Optional Integrations

### CloudWatch Log Export

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
| CloudWatch Exporter | ⚠️ Available, broader validation in progress |
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

## Running Tests

Recommended validated component suite:

```bash
pytest agent_eval/tests/component/ -v
```

Additional / in-progress test suites:

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

## Current Limitations

- **Quick start behavior**: The default sample configuration uses mock judges for deterministic pipeline validation, not semantic model-quality scoring. Real LLM judges require additional configuration.
- **AgentCore integration**: ARN-based extraction is still in progress.
- **OpenTelemetry fields**: Some fields (e.g., `user_query`) may not be available in CloudWatch exports due to Insights limitations.
- **Trace format assumptions**: While the adapter is flexible, it assumes event-based trace structure with timestamps.

## Contributing

This module uses isolated dependencies.

**Install development environment:**
```bash
pip install -e ".[dev]"
```

**Run tests:**
```bash
pytest agent_eval/tests/component/ -v
```

---

For detailed documentation on specific components, see:
- **AgentCore Integration**: `agent_eval/tools/agentcore_pipeline/README.md`
- **Validation Results**: `guides/VALIDATION_RESULTS.md`
- **Progress Tracking**: `guides/FIX_PROGRESS.md`
