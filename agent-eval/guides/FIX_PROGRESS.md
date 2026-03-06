# AgentCore ARN Wrapper - Fix Progress

**Date:** March 6, 2026

## Completed Fixes

### ✅ Fix 1: GetAgentRuntime API Call (COMPLETE)
**Status:** Implemented and tested  
**Changes:**
- Updated `get_runtime_metadata()` to extract runtime ID from ARN
- Changed API call from `agentRuntimeArn=arn.raw_arn` to `agentRuntimeId=runtime_id`
- Updated documentation examples to use `runtime/...` instead of `agent/...`

**Test Result:**
```
✅ ARN parsed successfully
  Resource ID: runtime/customersupportagent-crGhIpFJYP
  Runtime ID (extracted): customersupportagent-crGhIpFJYP

✅ GetAgentRuntime API call succeeded!
  Agent Runtime ID: customersupportagent-crGhIpFJYP
  Status: READY
```

### ✅ Fix 2: Log Group Discovery (COMPLETE)
**Status:** Implemented and tested  
**Changes:**
- Updated `discover_log_groups()` to search for single log group with pattern `-DEFAULT`
- Returns same log group for both `runtime_logs` and `otel_logs` fields
- Prefers `-DEFAULT` suffix when multiple groups found
- Updated documentation to reflect actual AgentCore log structure

**Test Result:**
```
✅ Log group discovery succeeded!
  Runtime logs: /aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT
  OTEL logs: /aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT
  Discovery method: describe_log_groups with prefix
  Same group: True
```

### ✅ Fix 2.1: JSON Serialization (COMPLETE)
**Status:** Implemented and tested  
**Changes:**
- Added `default=str` to `json.dump()` call for discovery.json
- Handles datetime objects in AWS API responses

**Test Result:**
```
Exit Code: 0 (wrapper completes successfully)
```

## Remaining Work

### ⏳ Fix 3: Script 1 OTEL Mode (IN PROGRESS - Phase 1)
**Status:** Partially implemented - extraction works but user_query unavailable  
**Issue:** Script 1 needs to extract turns from OTEL stream instead of runtime logs

**Progress:**
- ✅ Added `--log-stream-kind otel` option to Script 1
- ✅ Fixed timestamp extraction (converts timeUnixNano to readable format)
- ✅ Fixed session_id extraction (uses `attributes.session.id`)
- ✅ Added filter for events with valid traceId
- ⚠️  user_query extraction not working (CloudWatch Insights limitation)

**Current Test Results:**
```bash
python -m agent_eval.tools.agentcore_pipeline.01_export_turns_from_app_logs \
  --log-group "/aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT" \
  --minutes 60 \
  --log-stream-kind otel \
  --region us-east-1
```

Output:
- ✅ 1000 turns extracted
- ✅ Timestamps correct: "2026-03-06 21:20:27.250"
- ✅ trace_id present: "69ab451a17d6821e6f4f54e10e52f2e2"
- ✅ span_id present: "ad78dea4cda80aa2"
- ⚠️  session_id: 75/1000 events have it (7.5%)
- ❌ user_query: 0/1000 events have it (CloudWatch Insights can't extract nested body.input)

**OTEL Log Schema Findings:**
```json
{
  "traceId": "69ab463d578ac35a3fd0daca2dba3f28",
  "spanId": "5513faadaa4c76e4",
  "timeUnixNano": 1772832322599135148,
  "attributes": {
    "session.id": "dd697fa7-76dc-4d04-a799-87e3ad34f059"
  },
  "body": {
    "input": {
      "messages": [
        {
          "role": "user",
          "content": {
            "content": "[{\"text\": \"user query here\"}]"
          }
        }
      ]
    }
  }
}
```

**CloudWatch Insights Limitations:**
- ✅ Can extract: `traceId`, `spanId`, `timeUnixNano`, `attributes.session.id`
- ❌ Cannot extract: `body.input` (too deeply nested)
- ❌ Cannot extract: `body` as JSON object (returns empty)

**Options for user_query Extraction:**

**Option A: Accept empty user_query for now**
- Script 1 extracts trace_id, span_id, session_id, timestamp
- Script 2 enriches with OTEL data (may have user query in different format)
- Script 3 adds X-Ray data
- Pros: Unblocks Phase 2-4, maintains turn tracking
- Cons: Missing user_query in Script 1 output

**Option B: Post-process with GetLogEvents API**
- Script 1 extracts basic fields from CloudWatch Insights
- Add post-processing step to fetch full @message for each event
- Parse body.input from full message
- Pros: Gets complete data
- Cons: Much slower (API call per event), complex implementation

**Option C: Use different OTEL event type**
- Investigate if other OTEL span types have simpler user_query field
- May need to query different event.name values
- Pros: Might find easier extraction path
- Cons: Uncertain if such events exist

**Recommendation: Option A for now**
- Proceed with Phase 2-4 using current extraction
- Validate that Script 2 OTEL enrichment provides user query
- Revisit user_query extraction if needed after full pipeline works

**Next Steps (Phase 2):**
1. Update wrapper to use `--log-stream-kind otel` by default
2. Test full 3-script pipeline with OTEL mode
3. Validate Script 2 can enrich with additional OTEL data
4. Check if user_query appears in Script 2 or Script 3 output

## Testing Status

### End-to-End Test (No Override Mode)
**Command:**
```bash
python -m agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn \
  --agent-runtime-arn "arn:aws:bedrock-agentcore:us-east-1:943677087104:runtime/customersupportagent-crGhIpFJYP" \
  --region us-east-1 \
  --minutes 60 \
  --output-dir ./test-no-override
```

**Result:**
- ✅ ARN parsing works
- ✅ GetAgentRuntime API call succeeds
- ✅ Log group discovery succeeds
- ✅ discovery.json created successfully
- ⚠️  Script 1 returns zero turns (expected - needs Fix 3)
- ✅ Pipeline completes without errors

## Summary

**Fixes 1 & 2 are production-ready.** The wrapper can now:
- Parse AgentCore runtime ARNs correctly
- Call GetAgentRuntime API successfully
- Discover log groups automatically
- Complete end-to-end without errors

**Fix 3 is the final blocker** for getting actual turn data. Once Script 1 is updated to query the OTEL stream, the wrapper will be fully functional.
