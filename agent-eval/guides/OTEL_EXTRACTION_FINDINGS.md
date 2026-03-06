# OTEL Extraction Findings - Script 1

**Date:** March 6, 2026  
**Runtime ARN:** `arn:aws:bedrock-agentcore:us-east-1:943677087104:runtime/customersupportagent-crGhIpFJYP`

## Summary

Script 1 OTEL mode successfully extracts trace metadata (trace_id, span_id, timestamp) but cannot extract user_query due to CloudWatch Insights limitations on nested field extraction.

## Test Results

### Command
```bash
python -m agent_eval.tools.agentcore_pipeline.01_export_turns_from_app_logs \
  --log-group "/aws/bedrock-agentcore/runtimes/customersupportagent-crGhIpFJYP-DEFAULT" \
  --minutes 60 \
  --log-stream-kind otel \
  --region us-east-1 \
  --out test_otel_turns.json
```

### Output Statistics
- **Total turns extracted:** 1000
- **Turns with timestamp:** 1000 (100%)
- **Turns with trace_id:** 1000 (100%)
- **Turns with span_id:** 1000 (100%)
- **Turns with session_id:** 75 (7.5%)
- **Turns with user_query:** 0 (0%)

### Sample Output
```json
{
  "timestamp": "2026-03-06 21:20:27.250",
  "session_id": null,
  "trace_id": "69ab451a17d6821e6f4f54e10e52f2e2",
  "request_id": null,
  "span_id": "ad78dea4cda80aa2",
  "user_query": ""
}
```

## Issues Fixed

### ✅ Issue 1: Timestamp Conversion
**Problem:** Timestamps showing as "1970-01-01 00:00:00.000"

**Root Cause:** 
- Query was returning events without `timeUnixNano` field
- Events without `traceId` have `timeUnixNano: 0`

**Fix:**
- Added filter: `| filter ispresent(traceId) and traceId != ""`
- Also extract `@timestamp` as fallback
- Convert `timeUnixNano` from nanoseconds to ISO format

**Result:** ✅ All timestamps now correct

### ✅ Issue 2: session_id Extraction
**Problem:** session_id was null for all events

**Root Cause:**
- Query used wrong field path syntax: `attributes."session.id"` (with quotes)
- Correct syntax: `attributes.session.id` (no quotes)

**Fix:**
- Updated query to use `attributes.session.id`

**Result:** ✅ 75/1000 events now have session_id (7.5%)

**Note:** Most OTEL events don't have session_id - only specific span types include it. This is expected behavior.

### ❌ Issue 3: user_query Extraction
**Problem:** user_query is empty for all events

**Root Cause:** CloudWatch Insights cannot extract deeply nested fields

**OTEL Body Structure:**
```json
{
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
- ❌ Cannot extract: `body.input` (returns empty)
- ❌ Cannot extract: `body` as JSON object (returns empty)
- ❌ Cannot extract: nested paths like `body.input.messages[0].content.content`

**Attempted Solutions:**
1. ❌ `body.input as body_input` → Returns empty
2. ❌ `body.input.messages[0]` → Syntax error
3. ❌ `body` → Returns empty (too complex for Insights)

**Status:** Cannot extract user_query with CloudWatch Insights query alone

## CloudWatch Insights Query

### Final Working Query
```sql
fields
  @timestamp as ts,
  timeUnixNano as ts_nano,
  traceId as trace_id,
  spanId as span_id,
  attributes.session.id as session_id,
  body.input as body_input,
  body.output as body_output,
  body
| filter @logStream = "otel-rt-logs"
| filter ispresent(traceId) and traceId != ""
| sort @timestamp asc
```

### What Works
- ✅ Filters to OTEL stream only
- ✅ Filters to events with valid traceId
- ✅ Extracts timestamp (both formats)
- ✅ Extracts trace_id and span_id
- ✅ Extracts session_id when present
- ✅ Sorts chronologically

### What Doesn't Work
- ❌ Extracting user_query from body.input
- ❌ Extracting any nested body fields

## Options for user_query

### Option A: Accept Empty user_query (RECOMMENDED)
**Approach:** Proceed without user_query in Script 1 output

**Pros:**
- Unblocks Phase 2-4 immediately
- Maintains turn tracking with trace_id/span_id
- Script 2 may enrich with user query from OTEL
- Script 3 adds X-Ray data

**Cons:**
- Missing user_query in Script 1 output
- May need to extract from Script 2 or Script 3

**Next Steps:**
1. Update wrapper to use `--log-stream-kind otel`
2. Test full 3-script pipeline
3. Check if user_query appears in Script 2/3 output

### Option B: Post-Process with GetLogEvents API
**Approach:** Fetch full @message for each event and parse body.input

**Implementation:**
1. Script 1 extracts basic fields (trace_id, span_id, timestamp)
2. Add post-processing step:
   - For each event, call `logs.get_log_events()` with @ptr
   - Parse full @message JSON
   - Extract body.input.messages[0].content.content
3. Merge user_query back into turns

**Pros:**
- Gets complete data including user_query
- No CloudWatch Insights limitations

**Cons:**
- Much slower (1 API call per event)
- Complex implementation
- Rate limiting concerns for large datasets

### Option C: Query Different OTEL Event Types
**Approach:** Find OTEL events with simpler user_query field

**Investigation Needed:**
- Check if certain `event.name` values have user_query at top level
- Look for span types that include request payload
- May need to query multiple event types and merge

**Pros:**
- Might find easier extraction path
- Stays within CloudWatch Insights

**Cons:**
- Uncertain if such events exist
- May require multiple queries
- Complex merging logic

## Recommendation

**Proceed with Option A** for now:

1. Accept that Script 1 output has empty user_query
2. Update wrapper to use OTEL mode
3. Test full 3-script pipeline
4. Validate that downstream scripts (2 & 3) provide sufficient data
5. Revisit user_query extraction only if needed after full pipeline validation

**Rationale:**
- Unblocks immediate progress (Phase 2-4)
- Script 1's primary job is turn extraction (trace_id, timestamp, session_id)
- User query may be available in Script 2 OTEL enrichment or Script 3 X-Ray data
- Can always add post-processing later if needed

## Next Phase

**Phase 2: Wire Wrapper to OTEL Mode**

Update `run_from_agentcore_arn.py`:
1. Change default `log_stream_kind` from "runtime" to "otel"
2. Update documentation
3. Test full pipeline without overrides

**Expected Behavior:**
- Script 1 extracts 1000+ turns with trace_id, timestamp, session_id
- Script 2 enriches with OTEL data (may add user_query)
- Script 3 adds X-Ray steps and latency
- Final output has complete trace data

**Validation Criteria:**
- ✅ Script 1 returns >0 turns
- ✅ Timestamps are correct (not 1970)
- ✅ trace_id present for all turns
- ✅ session_id present for some turns (7-10%)
- ⚠️  user_query may be empty (acceptable for now)
