# AgentCore ARN Wrapper - Validation Results

**Date:** March 6, 2026  
**Runtime ARN:** `arn:aws:bedrock-agentcore:us-east-1:943677087104:runtime/customersupportagent-crGhIpFJYP`

## Executive Summary

Completed all 6 validation steps. Found 2 critical bugs and 1 architectural mismatch that prevent the wrapper from working with real AgentCore runtimes.

## Validation Steps

### ✅ Step 1: 3-Script Pipeline (Override Mode)
**Status:** PASS  
**Result:** Pipeline orchestration works correctly when using manual log group overrides

- All 3 scripts execute successfully
- Output files created correctly
- Error handling works as expected

### ✅ Step 2: CloudWatch Data Availability
**Status:** PASS  
**Result:** Fresh log data confirmed in runtime log group

- Log group: `/aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT`
- Latest event: March 6, 2026 (today)
- Multiple fresh log streams available

### ✅ Step 3: Log Schema Validation
**Status:** PASS with FINDINGS  
**Result:** OTEL logs have correct schema, but location differs from expectations

**OTEL logs (`otel-rt-logs` stream):**
- ✅ Valid JSON format
- ✅ Contains `traceId` and `spanId`
- ✅ OTEL format with resource, scope, attributes
- ✅ Fresh data available

**Runtime logs (`[runtime-logs]` streams):**
- ⚠️  Plain text Python logs (not JSON)
- ⚠️  Cannot be used for turn extraction

**APPLICATION_LOGS group:**
- ⚠️  Legacy/deprecated (last data: Feb 20, 2026)
- ✅ Has correct JSON schema when active
- ⚠️  Not receiving new data

### ✅ Step 4: AWS Identity and Region Consistency
**Status:** PASS  
**Result:** All AWS access validated

- ✅ AWS identity confirmed (Account: 943677087104)
- ✅ Region consistency verified (us-east-1)
- ✅ CloudWatch Logs access confirmed
- ✅ Bedrock AgentCore client created successfully

### ❌ Step 5: GetAgentRuntime API Call
**Status:** FAIL - Critical Bug Found  
**Result:** API call uses wrong parameter name

**Bug Location:** `run_from_agentcore_arn.py:480`

```python
# ❌ CURRENT (WRONG)
response = client.get_agent_runtime(agentRuntimeArn=arn.raw_arn)

# ✅ SHOULD BE
response = client.get_agent_runtime(agentRuntimeId=runtime_id)
```

**Details:**
- API expects `agentRuntimeId` (just the ID part)
- Code passes `agentRuntimeArn` (full ARN)
- Runtime ID must be extracted from ARN: `customersupportagent-crGhIpFJYP`

**API Response (when called correctly):**
```json
{
  "agentRuntimeId": "customersupportagent-crGhIpFJYP",
  "agentRuntimeName": "customersupportagent",
  "status": "READY",
  "agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:943677087104:runtime/customersupportagent-crGhIpFJYP",
  ...
}
```

### ❌ Step 6: Log Group Naming Assumptions
**Status:** FAIL - Architectural Mismatch  
**Result:** Discovery logic expects wrong log group structure

**Expected (by wrapper):**
```
/aws/bedrock-agentcore/runtimes/{agentRuntimeId}-{endpoint}/runtime-logs
/aws/bedrock-agentcore/runtimes/{agentRuntimeId}-{endpoint}/otel-rt-logs
```

**Actual (in AWS):**
```
/aws/bedrock-agentcore/runtimes/{agentRuntimeId}-DEFAULT
  ├── [runtime-logs] streams (plain text)
  └── otel-rt-logs stream (JSON OTEL data)
```

**Key Differences:**
1. **Single log group** (not two separate groups)
2. **Log group ends with `-DEFAULT`** (not `/runtime-logs` or `/otel-rt-logs`)
3. **OTEL data is a stream** within the runtime log group (not a separate group)
4. **Runtime logs are plain text** (not JSON, cannot be used for turn extraction)

## Critical Bugs Summary

### Bug 1: GetAgentRuntime API Parameter (Line 480)
**Severity:** HIGH  
**Impact:** Wrapper cannot fetch runtime metadata from AWS API

**Fix Required:**
```python
# Extract runtime ID from ARN
resource_id = arn.resource_id  # "runtime/customersupportagent-crGhIpFJYP"
runtime_id = resource_id.split('/')[-1]  # "customersupportagent-crGhIpFJYP"

# Call API with correct parameter
response = client.get_agent_runtime(agentRuntimeId=runtime_id)
```

### Bug 2: Log Group Discovery Logic (Lines 655-720)
**Severity:** HIGH  
**Impact:** Wrapper cannot discover log groups automatically

**Current Logic Issues:**
1. Searches for TWO separate log groups
2. Expects groups ending with `/runtime-logs` and `/otel-rt-logs`
3. Doesn't handle single log group with multiple streams

**Fix Required:**
1. Search for single log group ending with `-DEFAULT`
2. Use that group for BOTH runtime and OTEL data
3. Script 2 should query the `otel-rt-logs` stream within that group

## Recommended Fixes

### Priority 1: Fix GetAgentRuntime API Call
Update `get_runtime_metadata()` function to extract runtime ID from ARN before calling API.

### Priority 2: Fix Log Group Discovery
Update `discover_log_groups()` function to:
1. Search for log group with pattern: `/aws/bedrock-agentcore/runtimes/{runtime_id}-*`
2. Return the same log group for both runtime_logs and otel_logs
3. Update Script 2 to query the `otel-rt-logs` stream specifically

### Priority 3: Update Documentation
- Document actual log group structure
- Update examples to reflect single log group pattern
- Add note about APPLICATION_LOGS being legacy

## Testing Recommendations

1. **Unit tests** for ARN parsing and runtime ID extraction
2. **Integration test** with real AgentCore runtime
3. **End-to-end test** without override mode (full discovery)
4. **Validation** that Script 2 can read from `otel-rt-logs` stream

## Workaround (Current)

Until bugs are fixed, use override mode:

```bash
python -m agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn \
  --agent-runtime-arn "arn:aws:bedrock-agentcore:us-east-1:943677087104:runtime/customersupportagent-crGhIpFJYP" \
  --runtime-log-group "/aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT" \
  --otel-log-group "/aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT" \
  --region us-east-1 \
  --log-stream-kind runtime \
  --output-dir ./output
```

**Note:** This bypasses both bugs by providing log groups manually.
