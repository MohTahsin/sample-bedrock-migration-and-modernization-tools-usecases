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

**Mental model:**
```
Raw trace logs
      ↓
Adapter normalizes trace
      ↓
NormalizedRun (standard schema)
      ↓
Evaluator computes:
  • deterministic metrics
  • rubric-based judge scores
      ↓
Structured evaluation artifacts
```

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

### Rubric-Driven and Scale-Aware Evaluation

Evaluation behavior is controlled by rubric configuration. Each rubric is an independent evaluation criterion (e.g., tool groundedness, safety/PII detection).

**Rubric system:**
- 8 default rubrics shipped with the system (6 LLM-based, 2 deterministic)
- User rubrics override defaults with matching IDs or add new criteria
- Final evaluation uses merged rubrics (user overrides + remaining defaults)
- Each LLM rubric runs 3 times by default (repeats=3) for consistency measurement

Each rubric is evaluated multiple times (default: 3) to measure score stability. Repeated runs allow the system to compute median, mean, and variance for each judge.

**Rubric configuration controls:**
- What quality dimensions are evaluated (correctness, groundedness, etc.)
- Whether evaluation is turn-scoped or run-scoped
- What evidence is extracted from the trace
- How judges score the trace (numeric scales vs categorical)
- How scores are aggregated across multiple judges
- How disagreement is normalized and computed

**Scale-aware aggregation:**
The framework uses rubric scoring scales (e.g., 1-5, 1-10, categorical) to drive:
- Numeric vs categorical score handling
- Disagreement computation (normalized by scale range)
- Variance-weighted aggregation across judges
- Cross-rubric comparability

Example:
```bash
python -m agent_eval.cli \
  --input trace.json \
  --judge-config judges.yaml \
  --rubrics rubrics.yaml \
  --output-dir ./output
```

Changing `rubrics.yaml` changes which evaluation criteria run and how evidence is selected, without changing application code. The scoring scale defined in each rubric automatically adjusts how scores are aggregated and how disagreement is measured.

## Rubric Scope and Evidence Selectors

Rubrics can evaluate either a single turn or the entire run. The scope determines what data is available to evidence selectors.

**Turn scope** (`scope: turn`)
- Evaluates each conversation turn independently
- Evidence extraction context is a single turn object
- Selectors must be turn-relative

Example turn object:
```json
{
  "turn_id": "turn_0",
  "user_query": "What is 2+2?",
  "steps": [...],
  "final_answer": "4"
}
```

Valid selectors for turn scope:
```
$.user_query
$.steps[?(@.kind=='TOOL_CALL')]
$.final_answer
```

**Run scope** (`scope: run`)
- Evaluates the entire conversation trace
- Evidence extraction context is the full NormalizedRun
- Selectors can reference all turns

Valid selectors for run scope:
```
$.turns[*].user_query
$.turns[*].steps
$.turns[*].final_answer
```

**Common mistake:**
Using `$.turns[*].user_query` with `scope: turn` will cause a validation error because the `turns[]` array is not present in the turn-level context.

**Quick guideline:**

| Scope | Selector style |
|-------|----------------|
| `turn` | `$.user_query` |
| `run` | `$.turns[*].user_query` |

**Typical use cases:**
- Turn scope: Correctness, groundedness, reasoning quality per turn
- Run scope: Safety/PII checks, trace completeness, conversation-level metrics

**Selector validation:**
The framework validates selector patterns at config load time to prevent mismatches between rubric scope and selector paths. See `guides/RUBRIC_SELECTOR_VALIDATION.md` for detailed validation rules and examples.

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

## Quick Start (2 Minutes)

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

**Artifacts explained:**

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

**Example output interpretation:**
```
TOOL_GROUNDEDNESS: 5
TOOL_CALL_QUALITY: 3
TRACE_COMPLETENESS: 4
SAFETY_PII: safe
```

Higher numeric scores indicate better performance. Categorical scores (e.g., safe/unsafe) represent classification judgments.

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

Typical setups use 1-5 judges for cross-model comparison and disagreement detection. Judge evaluations run in parallel across rubrics and judges, then aggregate scores with disagreement signals.

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

### Two-Stage Aggregation

**Stage 1 - Within-judge aggregation:**
Each judge runs multiple times (default: 3 repeats). The system computes the median of these repeated runs per judge.

**Stage 2 - Cross-judge aggregation:**
The system aggregates across different judges using variance-weighted averaging of their medians.

**Formulas:**
- **Within-judge**: median of N repeated runs
- **Cross-judge**: weighted average with weights = `sample_size / (1 + variance)`
- **Disagreement**: scale-aware normalized standard deviation

This two-stage approach measures both individual judge consistency and cross-judge agreement.

## Trace Input and Adapter

The adapter allows the framework to evaluate traces from many agent systems without requiring a specific runtime format.

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

## Common Issues

**No evidence extracted**
- Check rubric scope vs selector style
- Turn scope requires selectors like `$.user_query`
- Run scope allows selectors like `$.turns[*].user_query`

**All rubric scores are neutral**
- Evidence extraction may be empty
- Inspect `judge_runs.jsonl` to verify extracted evidence

**Unexpected metrics**
- Run `inspect_adapter_stages` to debug trace normalization
- Verify turn segmentation and tool linking behavior

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
- **Rubric selector rules**: Turn-scoped rubrics evaluate a single turn object. Evidence selectors must therefore be turn-relative (e.g., `$.user_query`) rather than run-level selectors (e.g., `$.turns[*].user_query`). Using run-level selectors with `scope: turn` will return no evidence because the extraction context is narrowed to the individual turn.

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
- **Rubric Selector Validation**: `guides/RUBRIC_SELECTOR_VALIDATION.md`
- **AgentCore Integration**: `agent_eval/tools/agentcore_pipeline/README.md`
- **Validation Results**: `guides/VALIDATION_RESULTS.md`
- **Progress Tracking**: `guides/FIX_PROGRESS.md`
