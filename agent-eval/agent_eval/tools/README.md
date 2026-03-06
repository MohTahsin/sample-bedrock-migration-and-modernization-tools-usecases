# Agent Evaluation Tools

This directory contains evidence extraction pipelines for agent evaluation.

## Architecture Overview

```
tools/
├── agentcore_pipeline/              # AgentCore evidence reconstruction
│   ├── 01_export_turns_from_app_logs.py
│   ├── 02_build_session_trace_index.py
│   ├── 03_add_xray_steps_and_latency.py
│   ├── export_agentcore_pipeline.py  # Orchestrator
│   └── README.md
│
├── cloudwatch_logs_fixture_exporter.py  # Generic log fixture exporter
└── check_otel_structure.py              # Utility
```

## Two Extraction Approaches

### Option A: AgentCore Evidence Reconstruction Pipeline (Primary)

**Purpose**: Reconstruct complete AgentCore observability evidence from distributed sources.

**Mental Model**: This is NOT a "CloudWatch logs exporter" - it's an **evidence reconstruction pipeline**. CloudWatch is just the storage backend.

**What it does**:
- Extracts turns from CloudWatch app logs
- Builds session trace index
- Merges X-Ray spans for latency calculation
- Produces canonical JSON ready for adapter normalization

**When to use**:
- Evaluating AgentCore agents
- Need complete turn-level evidence with tool calls
- Need accurate latency from X-Ray spans
- Production observability analysis

**Usage**:
```bash
# Run full pipeline
python agentcore_pipeline/export_agentcore_pipeline.py \
    --log-group /aws/lambda/agentcore-app \
    --days 7 \
    --output-dir ./outputs/

# Custom time range
python agentcore_pipeline/export_agentcore_pipeline.py \
    --log-group /aws/lambda/agentcore-app \
    --start-time "2024-01-01T00:00:00Z" \
    --end-time "2024-01-31T23:59:59Z" \
    --output-dir ./outputs/
```

**Output Structure**:
```
outputs/
├── exported_traces/    # Intermediate: turns, trace index
└── normalized/         # Final: canonical JSON
```

**Coverage Summary**:
- Turns indexed
- Traces exported
- Joins by trace_id
- Joins by request_id
- Unmatched turns

---

### Option B: Generic Log Fixture Exporter (Supplementary)

**Purpose**: Export raw CloudWatch logs as Generic JSON fixtures for adapter development.

**Mental Model**: This is a **standalone fixture generator**, NOT part of the AgentCore pipeline.

**What it does**:
- Exports raw log events from any CloudWatch log group
- Basic OTEL field extraction (trace_id, span_id, session_id)
- No turn reconstruction or tool linking
- Outputs Generic JSON events only

**When to use**:
- Generating test fixtures for adapter development
- Exporting logs from non-AgentCore services
- Quick log enrichment data
- Testing adapter with various log formats

**Usage**:
```bash
# Export generic log fixtures
python cloudwatch_logs_fixture_exporter.py \
    --log-group /aws/lambda/my-service \
    --days 7 \
    --output-dir ./outputs/fixtures/

# With log group discovery
python cloudwatch_logs_fixture_exporter.py \
    --log-group-prefix /aws/lambda/ \
    --days 30 \
    --output-dir ./outputs/fixtures/
```

**Output Structure**:
```
outputs/
└── fixtures/           # Generic JSON event files
```

---

## Key Differences

| Feature | AgentCore Pipeline | Generic Exporter |
|---------|-------------------|------------------|
| **Purpose** | Evidence reconstruction | Fixture generation |
| **Turn segmentation** | ✅ Yes | ❌ No |
| **Tool linking** | ✅ Yes | ❌ No |
| **X-Ray spans** | ✅ Merged | ❌ Not included |
| **Latency calculation** | ✅ Accurate | ❌ Not calculated |
| **Output** | Canonical JSON | Generic JSON events |
| **Use case** | Production evaluation | Adapter testing |

---

## Architectural Principles

1. **Strict Separation**: Tools MUST NOT import adapter modules
2. **Evidence vs Storage**: AgentCore pipeline reconstructs evidence; CloudWatch is just storage
3. **Pipeline Independence**: Each tool can run standalone or orchestrated
4. **Output Contracts**: Clear intermediate and final output formats

---

## For More Details

- AgentCore Pipeline: See `agentcore_pipeline/README.md`
- Generic Exporter: See docstring in `cloudwatch_logs_fixture_exporter.py`
- Adapter Integration: See `../adapters/generic_json/README.md`
