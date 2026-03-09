# Implementation Plan: Generic JSON Adapter and Normalized Schema

## Overview

This plan implements Phase 1 of the agent-eval evaluation system: a turn-aware normalized schema, Generic JSON adapter with config-driven multi-stage pipeline (Normalize → Classify → Segment → Derive), confidence scoring, sample test fixtures, and a standalone CloudWatch export utility. The implementation follows a test-driven approach with both unit and property-based testing.

The adapter uses a production-ready configuration file (`adapter_config.yaml` v6) that defines field mappings, classification rules, segmentation strategies, and confidence scoring.

## Tasks

- [x] 1. Create turn-aware normalized schema definition
  - Create `agent_eval/schemas/normalized_run.schema.json` with turn-aware structure
  - Define run-level fields: run_id, metadata, adapter_stats, turns[]
  - Define turn-level fields: turn_id, user_query, final_answer, steps, confidence, normalized_latency_ms, runtime_reported_latency_ms
  - Define enhanced step fields: type, kind, name, status, start_ts, end_ts, latency_ms, span_id, parent_span_id, tool_run_id, attributes, raw, event_order, source_index
  - Add event_order (integer) and source_index (integer) to guarantee deterministic ordering
  - Set nullable fields for timestamps and latency values
  - Include adapter_stats with confidence_penalties array, raw_path, canonical_sources, orphan_tool_results[]
  - Set additionalProperties to false for strict output at root level
  - Allow additionalProperties: true for attributes and raw objects (flexible nested data)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12_

- [x] 2. Create base adapter interface
  - Create `agent_eval/adapters/base.py` with Adapter Protocol
  - Define `adapt(path: str, config_path: str = None) -> Dict[str, Any]` interface (renamed from load_and_normalize_trace for clarity)
  - Return typed structure with NormalizedRun data + AdapterStats to separate concerns
  - Use Python Protocol (PEP 544) for structural subtyping
  - Document interface for future adapters
  - _Requirements: 7.7_

- [x] 3. Verify adapter configuration (already created)
  - Confirm `agent_eval/adapters/generic_json/adapter_config.yaml` exists with v6 structure
  - Add config schema validation using Pydantic for fail-fast on invalid config
  - Verify multi-stage pipeline configuration: normalize, classify, segment, derive
  - Verify confidence scoring configuration
  - Verify comprehensive field aliases (50+ mappings)
  - Emit warnings for unknown config keys (config drift detection)
  - _Requirements: 2.2, 2.3_

- [x] 4. Set up testing infrastructure
  - Create `agent_eval/tests/` directory structure
  - Add `__init__.py` files for test modules
  - Configure pytest in `pyproject.toml`
  - Separate dependencies in pyproject.toml:
    - Runtime deps: jsonschema, pyyaml
    - Dev deps (optional group): pytest, pytest-cov, hypothesis
  - _Requirements: 7.5_

- [x] 5. Implement configuration loader
  - [x] 5.1 Create `agent_eval/adapters/generic_json/config_loader.py`
    - Implement `AdapterConfig` class to load and parse adapter_config.yaml
    - Add Pydantic schema validation for config structure
    - Compile all regex patterns at load time for fail-fast validation
    - Cache compiled regex patterns for performance
    - Pre-resolve alias accessors (dotpath getters) for speed optimization
    - Parse normalize section (event_paths, field_aliases, timestamp_parse, carry_fields)
    - Parse classify section (rules with regex matching, rule_order_policy)
    - Parse segment section (strategy_preference, turn_id_fields, anchor_events, tie_breaker_order)
    - Parse derive section (phases, prompt_context_strip, output_extraction, tool_linking, latency, attribution)
    - Parse confidence section (scoring penalties, emit_fields)
    - Parse stats section (emit_adapter_stats, max_error_examples)
    - Emit warnings for unknown config keys (config drift detection)
    - _Requirements: 2.2, 2.3_
  
  - [x]* 5.2 Write unit tests for config loader
    - Test YAML loading with valid config
    - Test Pydantic validation with invalid config
    - Test regex compilation and caching
    - Test field alias resolution with fallback chain
    - Test classification rule matching with regex
    - Test segmentation strategy selection
    - Test confidence penalty configuration
    - Test unknown key warnings
    - _Requirements: 2.3_

- [x] 6. Implement schema validation utility
  - [x] 6.1 Create `agent_eval/utils/validation.py`
    - Implement `load_schema(schema_path: str) -> dict` function
    - Implement `validate_against_schema(data: dict, schema: dict) -> tuple[bool, list[str]]` function
    - Implement `parse_timestamp(value: any, formats: list[str]) -> tuple[datetime | None, bool, str | None]` function
      - Returns (parsed_datetime, is_trusted, error_message)
      - Centralize all timestamp logic: ISO 8601, epoch (ms/s/ns), UnixNano
      - Support magnitude-based epoch unit inference
    - Implement `sanitize_latency(latency: any) -> float | None` function
    - Implement `calculate_confidence_score(penalties: list[dict], base_score: float) -> float` function
    - Handle schema loading errors gracefully
    - _Requirements: 6.1, 6.2_
  
  - [x]* 6.2 Write unit tests for validation utility
    - Test schema loading with valid and invalid paths
    - Test validation with compliant and non-compliant data
    - Test parse_timestamp with various formats (ISO 8601, epoch ms/s/ns, UnixNano)
    - Test parse_timestamp magnitude-based inference
    - Test parse_timestamp year bounds validation (2000-2100)
    - Test confidence score calculation with penalties
    - Test latency sanitization (negative → zero)
    - Test error message formatting
    - _Requirements: 6.1, 6.2_

- [x] 7. Create sample trace fixtures
  - [x] 7.1 Create `agent-eval/examples/sample_traces/` directory
    - Create `trace_single_turn_success.json`: Single turn with tool calls, all successful
    - Create `trace_multi_turn.json`: Multi-turn conversation with explicit turn_ids
    - Create `trace_stitched.json`: Stitched multi-turn trace (suspect detection test)
    - Create `trace_with_failure.json`: Trace with at least one failed step
    - Create `trace_minimal_fields.json`: Trace with only required fields, missing optionals
    - Create `trace_orphan_tool_results.json`: Trace with tool results without corresponding calls
    - Create `trace_otel_format.json`: OpenTelemetry format with spans and UnixNano timestamps
    - Create `trace_missing_timestamps.json`: Trace with missing/invalid timestamps
    - Create `trace_duplicate_tool_calls.json`: Trace with duplicate tool calls (dedupe test)
    - Create `trace_bad_epoch_units.json`: Trace with ambiguous epoch values (magnitude inference + year bounds test)
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

- [ ] 8. Implement Generic JSON adapter - Stage A: Normalize
  - [x] 8.1 Create `agent_eval/adapters/generic_json/__init__.py`
    - Export public API: `adapt` (renamed from load_and_normalize_trace)
    - Define DEFAULT_CONFIG_PATH constant: `Path(__file__).with_name("adapter_config.yaml")`
    - _Requirements: 2.1, 7.7_
  
  - [x] 8.2 Create `agent_eval/adapters/generic_json/adapter.py` with core structure
    - Implement `adapt(path: str, config_path: str = None) -> dict` public function
    - Use DEFAULT_CONFIG_PATH if config_path is None
    - Implement internal `_TraceNormalizer` class
    - Implement `_ConfidenceScorer` class for confidence calculation
    - Load configuration from adapter_config.yaml using AdapterConfig
    - _Requirements: 2.1, 2.2, 2.4, 7.7_
  
  - [x] 8.3 Implement event discovery and extraction
    - Extract events from configured event_paths (events, trace.events, spans, resourceSpans, etc.)
    - Support nested path traversal with wildcards (e.g., "resourceSpans.*.scopeSpans.*.spans")
    - Handle missing event paths gracefully
    - Persist raw_path (which event_path matched) in adapter_stats for debuggability
    - _Requirements: 2.3, 2.8_
  
  - [x] 8.4 Implement field alias resolution
    - Apply field_aliases with fallback chain (try each alias until found)
    - Support dotted-path field access (e.g., "attributes.timestamp")
    - Extract timestamps with multiple format support
    - Extract identifiers (session_id, trace_id, span_id, parent_span_id, request_id, turn_id)
    - Extract event typing fields (event_type, operation)
    - Extract tool fields (tool_name, tool_run_id, tool_result, tool_input, tool_arguments)
    - Extract model/message fields (role, span_kind, model_id, text)
    - Extract step fields (status, latency_ms)
    - Store canonical_sources (which alias matched per field) in adapter_stats for debuggability
    - _Requirements: 2.3, 2.8_
  
  - [x] 8.5 Implement timestamp parsing
    - Use centralized parse_timestamp() function from validation.py
    - Parse ISO 8601 formats with configured format strings
    - Parse epoch timestamps (ms, s, ns) with magnitude-based inference
    - Handle OTEL UnixNano fields explicitly (startTimeUnixNano, endTimeUnixNano)
    - Validate timestamps against min/max reasonable years (2000-2100)
    - Mark timestamps as trusted or untrusted based on parse success
    - _Requirements: 2.9, 2.11_
  
  - [x] 8.6 Implement raw data preservation
    - Extract attributes from configured attributes_paths
    - Preserve raw event data in step.raw (up to raw_event_max_bytes: 50000)
    - Include all extracted attributes in step.attributes
    - Add event_order (sequential integer) for deterministic ordering
    - Add source_index (original position) for events with invalid timestamps
    - _Requirements: 2.8_

- [x] 9. Implement Generic JSON adapter - Stage A: Classify
  - [x] 9.1 Implement event classification engine
    - Apply classification rules with first_match_wins policy
    - Support condition types: field equals, field regex, field exists
    - Support condition combinators: all, any
    - Match events to kinds: USER_INPUT, MODEL_INVOKE, TOOL_CALL, TOOL_RESULT, LLM_OUTPUT_CHUNK, PROMPT_CONTEXT, EVENT
    - Apply default_kind (EVENT) for unmatched events
    - Emit kind_rule_id (which rule matched) on each canonical event for debuggability
    - Emit kind_reason (why classified as this kind) on each canonical event
    - _Requirements: 2.3_
  
  - [x] 9.2 Implement classification rules from config
    - Rule: user_input_by_type_or_role (event_type or role regex)
    - Rule: model_invoke_by_type_or_span_kind_or_model (event_type, span_kind, or model_id exists)
    - Rule: llm_output_chunk_by_type_or_role (event_type or role regex)
    - Rule: tool_call_strict (tool_name exists + tool_run_id/arguments/input exists or event_type/operation regex)
    - Rule: tool_result_by_type_or_payload (tool_result exists or event_type/operation regex)
    - Rule: prompt_context_scaffolding (text regex for guidelines, preferences, etc.)
    - Store rule_id and matching condition in event metadata
    - _Requirements: 2.3_

- [x] 10. Implement Generic JSON adapter - Stage B: Segment
  - [x] 10.1 Implement segmentation strategy selection
    - Try strategies in preference order: TURN_ID, SESSION_PLUS_REQUEST, SESSION_PLUS_TRACE_THEN_ANCHOR_SPLIT, SINGLE_TURN
    - Select first successful strategy
    - Emit segmentation_strategy_used in both metadata and adapter_stats
    - Add turn_confidence_penalty when SINGLE_TURN fallback is used (indicates low segmentation confidence)
    - _Requirements: 2.12_
  
  - [x] 10.2 Implement TURN_ID strategy
    - Look for explicit turn_id fields (turn_id, request_id)
    - Group events by turn_id
    - _Requirements: 2.12_
  
  - [x] 10.3 Implement SESSION_PLUS_REQUEST strategy
    - Detect session_id + request_id combinations
    - Group events by session + request
    - _Requirements: 2.12_
  
  - [x] 10.4 Implement SESSION_PLUS_TRACE_THEN_ANCHOR_SPLIT strategy
    - Group by session_id or trace_id
    - Split within groups using anchor events (USER_INPUT, MODEL_INVOKE)
    - Apply request_id_diagnosis for stitched trace detection
    - Check distinct_user_prompts_per_request_id_max (1)
    - Check request_ids_per_user_prompt_max (3)
    - Sample window_events (5000) for diagnosis
    - _Requirements: 2.12_
  
  - [x] 10.5 Implement SINGLE_TURN fallback strategy
    - Treat all events as single turn
    - Apply confidence penalty for using fallback strategy
    - _Requirements: 2.12_
  
  - [x] 10.6 Implement event ordering within turns
    - Apply tie_breaker_order for events with same/missing timestamps
    - Order: USER_INPUT, MODEL_INVOKE, TOOL_CALL, TOOL_RESULT, LLM_OUTPUT_CHUNK, EVENT
    - Maintain source_index for events with invalid timestamps
    - Assign event_order (sequential integer) for deterministic ordering
    - _Requirements: 2.11, 8.6_

- [x] 11. Implement Generic JSON adapter - Stage C: Derive
  - [x] 11.1 Implement top-level field extraction
    - Extract final_answer using dotted-path syntax (final_answer, trace.final_answer, response.final_answer)
    - Extract user_query using dotted-path syntax (user_query, query, prompt, request.prompt)
    - Extract finish_reason using dotted-path syntax (finish_reason, stop_reason, response.finish_reason)
    - Implement dotted-path lookup on root JSON (required contract)
    - Precedence: top-level final_answer wins; stream join is fallback if top-level missing
    - _Requirements: 2.3_
  
  - [x] 11.2 Implement LLM output streaming
    - Join LLM_OUTPUT_CHUNK events into final_answer (fallback if top-level final_answer missing)
    - Exclude chunks matching prompt context regex patterns
    - Join with empty string (join_with: "")
    - Limit to max_chars (200000)
    - _Requirements: 2.3_
  
  - [x] 11.3 Implement prompt context stripping
    - Strip events with kind PROMPT_CONTEXT
    - Strip text matching regex patterns (guidelines, preferences, etc.)
    - _Requirements: 2.3_
  
  - [x] 11.4 Implement tool linking
    - Identify tool runs: kind=TOOL_CALL + tool_name required
    - Link tool calls with results via tool_run_id (TOOL_RUN_ID strategy)
    - Link tool calls with results via span hierarchy (SPAN_PARENT_CHILD strategy)
    - Deduplicate tool calls within time windows (window_seconds: 2)
    - Deduplicate by key_fields (tool_run_id, tool_name)
    - Prefer richer fields when deduplicating (tool_arguments, tool_input, attributes)
    - Handle orphan tool results gracefully with confidence penalty
    - Store orphan_tool_results[] explicitly in adapter_stats (not just penalty)
    - _Requirements: 2.3, 8.7_
  
  - [x] 11.5 Implement latency calculation
    - Calculate normalized_latency_ms from trusted timestamps
    - Start from first event with kind in: USER_INPUT, MODEL_INVOKE, LLM_OUTPUT_CHUNK, TOOL_CALL
    - End at last event with kind in: LLM_OUTPUT_CHUNK, TOOL_RESULT, EVENT
    - Extract runtime_reported_latency_ms from configured fields (total_latency_ms, attributes.latency_ms)
    - On missing timestamps: set to null and apply confidence penalty (on_missing_timestamps: "null_and_penalize")
    - _Requirements: 2.9, 2.10, 2.11_
  
  - [x] 11.6 Implement phase classification
    - Classify events into phases: PRE_TOOL_GENERATION, TOOL_CALL, FINAL_GENERATION
    - Based on tool usage patterns
    - _Requirements: 2.3_
  
  - [x] 11.7 Implement attribution and stitched trace detection
    - Detect tool usage: tool_used_if_has_kind=TOOL_CALL
    - Detect tool output by regex patterns (Retrieved results, statusCode/body JSON)
    - Detect stitched trace suspects: enabled=true, question_line_regex, distinct_question_count_suspect_at=2
    - _Requirements: 2.3_

- [x] 12. Implement confidence scoring
  - [x] 12.1 Implement ConfidenceScorer class
    - Track confidence penalties with reason, penalty, location
    - Calculate turn-level confidence scores (base: 1.0, subtract penalties)
    - Clamp confidence to [0, 1] range
    - Deduplicate penalties per root cause (e.g., missing_timestamp counted once per turn)
    - _Requirements: 2.5, 2.6_
  
  - [x] 12.2 Apply confidence penalties (additive with deduplication)
    - missing_timestamp: 0.4 (dedupe per turn - apply once even if multiple events missing timestamps)
    - missing_grouping_ids: 0.3 (dedupe per turn)
    - no_anchor_found: 0.3 (dedupe per turn)
    - no_llm_output: 0.2 (dedupe per turn)
    - missing_latency: 0.2 (dedupe per turn - only when timestamps exist but latency can't be computed; avoid double-penalizing with missing_timestamp)
    - single_turn_fallback: 0.25 (dedupe per run - penalty for using SINGLE_TURN segmentation strategy)
    - Ensure penalties are additive but deduplicated by root cause per turn
    - Don't apply same penalty repeatedly within a turn
    - _Requirements: 2.5, 2.6, 2.11_
  
  - [x] 12.3 Emit confidence fields
    - Emit run_confidence (aggregation rule: average of valid turn confidences, clamping to [0,1], ignoring empty/invalid turns)
    - Emit turn_confidence for each turn
    - Emit segmentation_strategy_used
    - Emit mapping_coverage with breakdown:
      - Per field group: ids_coverage, time_coverage, tool_coverage, text_coverage
      - Overall: overall_mapping_coverage (percentage)
    - Document aggregation rule explicitly: run_confidence = avg(valid_turn_confidences) with empty/invalid turns excluded
    - _Requirements: 2.5_

- [x] 13. Implement adapter_stats generation
  - [x] 13.1 Track processing statistics
    - Track total_events_processed
    - Track events_with_valid_timestamps
    - Track events_with_missing_data
    - Track dropped_events_count (events that couldn't be processed)
    - Track invalid_events_count (events that failed validation)
    - Track events_by_kind histogram (count per kind: USER_INPUT, MODEL_INVOKE, TOOL_CALL, etc.)
    - Track turn_count (total number of turns segmented)
    - _Requirements: 2.5_
  
  - [x] 13.2 Collect confidence penalties and metadata
    - Store all confidence_penalties with reason, penalty, location
    - Limit error examples to max_error_examples (20)
    - Store segmentation_strategy_reason (why this strategy was selected)
    - Store canonical_sources summary: top 10 missing fields with which aliases were tried
    - _Requirements: 2.5_
  
  - [x] 13.3 Generate adapter_stats object
    - Include all tracked statistics
    - Include confidence_penalties array
    - Include events_by_kind histogram
    - Include segmentation_strategy_used and segmentation_strategy_reason
    - Include turn_count
    - Include canonical_sources summary for debugging
    - Include metadata (adapter_version, processed_at)
    - _Requirements: 2.5_

- [x] 14. Implement schema validation and error handling
  - [x] 14.1 Define exception taxonomy
    - InputError: File not found, invalid JSON, unreadable input
    - ValidationError: Schema validation failure, schema file can't load, no events exist
    - AdaptationError: Internal adapter logic errors
    - Ensure JSONDecodeError is wrapped with file path context
    - _Requirements: 2.5, 2.6, 2.7, 3.1, 6.1, 6.2_
  
  - [x] 14.2 Integrate schema validation
    - Validate output against normalized schema before returning
    - Raise ValidationError if schema file can't be loaded
    - Raise ValidationError if no events exist in input
    - Raise ValidationError if input is completely unreadable
    - Raise descriptive errors on validation failure with field details
    - _Requirements: 2.5, 2.6, 2.7, 6.1, 6.2_
  
  - [x] 14.3 Implement graceful degradation
    - Missing optional fields → null with confidence penalty (not hard error)
    - Invalid timestamps → mark ts_trusted=false, order by source_index, reduce confidence
    - Orphan tool results → handle gracefully with confidence penalty
    - Tool-looking text without markers → don't misclassify
    - _Requirements: 2.6, 2.11, 8.6, 8.7_
  
  - [x] 14.4 Implement file operation error handling
    - Handle FileNotFoundError with clear message (InputError)
    - Handle JSONDecodeError with file path in error (InputError with context)
    - Ensure consistent error wrapping with file path context
    - _Requirements: 3.1_
  
  - [x] 14.5 Implement edge case handling
    - Negative latency → set to zero with warning
    - Duplicate run_id → process independently
    - Large step arrays (>10,000) → process without memory errors
    - Unicode characters → preserve correctly
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 15. Write unit tests for adapter
  - [ ]* 15.1 Create `agent_eval/tests/test_normalize_stage.py`
    - Test event discovery from various event_paths
    - Test field alias resolution with fallback chain
    - Test timestamp parsing (ISO 8601, epoch ms/s/ns, UnixNano)
    - Test infer_epoch_unit_by_magnitude behavior (ms vs s vs ns)
    - Test min_reasonable_year and max_reasonable_year bounds (2000-2100)
    - Test raw data preservation in step.raw and step.attributes
    - _Requirements: 2.3, 2.8, 2.9_
  
  - [ ]* 15.2 Create `agent_eval/tests/test_classify_stage.py`
    - Test event classification with regex rules
    - Test first_match_wins policy
    - Test all classification kinds (USER_INPUT, MODEL_INVOKE, TOOL_CALL, TOOL_RESULT, LLM_OUTPUT_CHUNK, PROMPT_CONTEXT, EVENT)
    - Test default_kind fallback
    - Test TOOL_CALL false positives: tool_name present but no evidence (tool_run_id/arguments/input missing + no matching event_type) → NOT TOOL_CALL
    - Test kind_rule_id and kind_reason emission
    - _Requirements: 2.3_
  
  - [ ]* 15.3 Create `agent_eval/tests/test_segment_stage.py`
    - Test TURN_ID strategy
    - Test SESSION_PLUS_REQUEST strategy
    - Test SESSION_PLUS_TRACE_THEN_ANCHOR_SPLIT strategy with anchor events
    - Test SINGLE_TURN fallback strategy with confidence penalty
    - Test request_id_diagnosis for stitched traces
    - Test tie_breaker_order for event ordering
    - _Requirements: 2.12_
  
  - [ ]* 15.4 Create `agent_eval/tests/test_derive_stage.py`
    - Test top-level field extraction with dotted paths
    - Test top_level_dotpath_required=true behavior (fail if dotpath lookup not implemented)
    - Test precedence: top-level final_answer wins over stream join
    - Test LLM output streaming and joining (fallback)
    - Test prompt context stripping
    - Test tool linking via tool_run_id
    - Test tool linking via span hierarchy
    - Test tool deduplication
    - Test latency calculation (normalized and runtime-reported)
    - Test phase classification
    - Test attribution and stitched trace detection
    - _Requirements: 2.3, 2.9, 2.10, 2.11_
  
  - [ ]* 15.5 Create `agent_eval/tests/test_confidence_scoring.py`
    - Test confidence penalty application with deduplication
    - Test missing_latency only triggers when timestamps exist but latency can't be computed
    - Test single_turn_fallback penalty
    - Test confidence score calculation
    - Test adapter_stats with confidence_penalties
    - Test graceful degradation with messy traces
    - Test run_confidence and turn_confidence aggregation
    - Test mapping_coverage breakdown (ids/time/tool/text + overall)
    - _Requirements: 2.5, 2.6, 9.3_
  
  - [x]* 15.6 Create `agent_eval/tests/test_integration.py`
    - Test complete pipeline: Normalize → Classify → Segment → Derive
    - Test single-turn trace normalization
    - Test multi-turn trace normalization
    - Test turn-aware output structure
    - Test adapter_stats generation with all fields
    - Add golden tests for known trace patterns
    - _Requirements: 2.2, 2.12_
  
  - [ ]* 15.7 Create `agent_eval/tests/test_error_handling.py`
    - Test InputError for file not found
    - Test InputError for invalid JSON with file path context
    - Test ValidationError for no events
    - Test ValidationError for schema load failure
    - Test AdaptationError for internal errors
    - Test missing optional fields don't raise errors
    - Test orphan tool results handled gracefully
    - Test invalid timestamps handled gracefully
    - Test negative latency handling
    - _Requirements: 2.6, 2.7, 2.11, 3.1, 8.1, 8.6, 8.7_
  
  - [x]* 15.8 Create `agent_eval/tests/test_sample_traces.py`
    - Load each sample from examples/sample_traces/
    - Normalize each sample using adapt()
    - Validate output conforms to schema
    - Verify edge cases handled correctly (orphan results, stitched traces, OTEL format, missing timestamps, duplicate tool calls, bad epoch units)
    - _Requirements: 9.1, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

- [x] 16. Checkpoint - Ensure all tests pass
  - Run all unit tests: `pytest -q agent_eval/tests/`
  - Verify coverage threshold: minimum 85% for Phase 1 code
  - Machine-checkable gate: tests must pass + coverage >= 85%
  - Fix any failing tests before proceeding

- [ ]* 17. Write property-based tests
  - [ ]* 17.1 Create `agent_eval/tests/test_properties.py`
    - **Property 1: Schema Compliance** - For any valid Generic JSON trace, transformation produces schema-compliant output with turn-aware structure
    - **Validates: Requirements 1.1-1.12, 2.2, 2.5, 6.1**
  
  - [ ]* 17.2 Add latency property tests
    - **Property 2: Dual Latency Tracking** - For any trace, output includes both normalized_latency_ms (from timestamps) and runtime_reported_latency_ms (if provided)
    - **Validates: Requirements 1.9, 1.10, 2.9, 2.10**
  
  - [ ]* 17.3 Add graceful degradation property test
    - **Property 3: Graceful Degradation** - For any trace with missing optional fields, adapter produces output with confidence penalties instead of failing
    - **Validates: Requirements 2.5, 2.6, 2.11, 9.3**
  
  - [ ]* 17.4 Add multi-turn property test
    - **Property 4: Multi-Turn Support** - For any trace with multiple turns, adapter segments correctly and produces turns[] array
    - **Validates: Requirements 1.5, 1.6, 2.12**
  
  - [ ]* 17.5 Add config-driven mapping property test
    - **Property 5: Config-Driven Mapping** - For any trace, field extraction follows adapter_config.yaml mappings with fallback chain
    - **Validates: Requirements 2.2, 2.3**
  
  - [ ]* 17.6 Add confidence scoring property test
    - **Property 6: Confidence Scoring** - For any trace, confidence scores are between 0 and 1, with penalties tracked in adapter_stats
    - **Validates: Requirements 2.5, 2.6**
  
  - [ ]* 17.7 Add adapter independence property test
    - **Property 7: Adapter Independence** - For any execution, adapter completes without importing boto3 or AWS modules
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**
  
  - [ ]* 17.8 Add orphan tool results property test
    - **Property 8: Orphan Tool Results** - For any trace with orphan tool results, adapter handles gracefully with confidence penalty
    - **Validates: Requirements 8.7**
  
  - [ ]* 17.9 Add sample trace validation property test
    - **Property 9: Sample Trace Validation** - For any sample trace in examples/sample_traces/, adapter normalizes successfully
    - **Validates: Requirements 9.1, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10**
  
  - [ ]* 17.10 Add invariant tests
    - **Invariant 1: No Fabricated Tool Runs** - For any trace, TOOL_CALL kind must exist in source events (not fabricated)
    - **Invariant 2: Stable Event Ordering** - For any trace, event ordering is deterministic and stable across multiple runs
    - Set iterations configurable via environment variable (e.g., HYPOTHESIS_ITERATIONS=100, CI-friendly)

- [x] 18. Implement CloudWatch export utility
  - [x] 18.1 Create `agent_eval/tools/cloudwatch_extractor.py`
    - **A standalone CloudWatch exporter that emits Generic JSON events only**
    - **This module is adapter-independent and MUST NOT import any adapter modules**
    - **Note:** The 3 existing scripts + README in tools/ are AgentCore Observability reference utilities (OTEL/app-log reconstruction pipeline). They demonstrate how AgentCore traces are structured. They are NOT the Generic JSON exporter. Reuse their trace understanding logic where applicable, but do not reuse their turn reconstruction logic.
    - Implement CLI argument parsing:
      - `--log-group`
      - `--log-group-prefix`
      - `--log-group-pattern`
      - `--days`
      - `--start-time`
      - `--end-time`
      - `--output-dir`
      - `--filter`
      - `--region`
      - `--profile`
    - Implement `discover_log_groups(prefix, pattern)` function
    - Implement `export_cloudwatch_logs()` function
    - Use boto3 to query CloudWatch Logs (filter_log_events or Logs Insights as appropriate)
    - Default to 90 days lookback (configurable via --days)
    - Support log group discovery via --log-group-prefix or --log-group-pattern
    - Emit explicit failure message if no log groups found
    - Handle pagination for large result sets with guardrails (max pages / max events safety limit)
    - Implement rate-limiting and exponential backoff for API calls
    - **When exporting AgentCore Observability logs:**
      - Preserve OTEL span structure (trace_id, span_id, parent_span_id)
      - Preserve tool-related fields if present in logs
      - Do NOT reconstruct turns (leave to adapter)
    - **Output Generic JSON events only:**
      - No turn segmentation
      - No final_answer extraction
      - No tool linking
      - No latency derivation
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 5.4, 5.6_
  
  - [x] 18.2 Implement log parsing logic
    - Parse CloudWatch log entries into Generic JSON event structure
    - **For AgentCore Observability traces:**
      - Parse OTEL-style JSON payloads
      - Extract:
        - timestamp (normalized ISO 8601 or epoch)
        - trace_id
        - span_id
        - parent_span_id
        - session_id (if present)
        - request_id (if present)
        - event_type
        - operation
        - status
        - latency_ms (if present in span)
        - attributes (flattened key/value pairs)
        - text (if message content exists)
    - **For non-AgentCore logs:**
      - Attempt best-effort JSON parsing
      - If plain text, store under `text` field
    - **Preserve raw CloudWatch metadata:**
      - log_group
      - log_stream
      - ingestion_time
    - **Do NOT:**
      - Attempt turn segmentation
      - Extract final_answer
      - Perform tool call/result linking
      - Perform phase classification
      - Derive normalized_latency_ms
    - Save events as Generic JSON array in individual files
    - Output to configured output_dir with:
      - export-id-based filename, OR
      - deterministic hash-based ID derived from (log_group + time window + first trace_id)
    - Ensure exported files can be processed directly by `adapt()`
    - _Requirements: 4.3, 5.3_
  
  - [x] 18.3 Add error handling for CloudWatch operations
    - Handle missing AWS credentials with helpful authentication error message
    - Handle expired credentials separately with remediation hint
    - Handle CloudWatch API errors gracefully with retry logic
    - Implement exponential backoff with jitter for:
      - ThrottlingException
      - RateExceededException
    - Guard against infinite pagination loops
    - Handle empty result set (no logs found) without error
      - Emit warning
      - Return empty export file OR no file
    - Handle log group discovery failure with explicit message and non-zero exit code
    - Ensure all AWS interactions remain inside exporter module (adapter independence)
    - _Requirements: 4.5, 4.8, 4.10, 5.1, 5.2_

**🔎 How the 3 Existing Scripts Fit:**

The 3 scripts in tools/:
- Are AgentCore-specific reconstruction utilities
- Extract turns and final answers
- Parse OTEL spans and merge runtime logs
- Perform segmentation and enrichment

In Task 18:
- They serve as **reference** for understanding AgentCore trace structure
- They are **NOT** the canonical export utility
- They should **NOT** be called by cloudwatch_extractor.py
- They remain useful for:
  - Manual debugging
  - Cross-validation against adapter normalization
  - Comparing reconstructed vs normalized output

- [ ]* 19. Write tests for CloudWatch export utility
  - [x]* 19.1 Create `agent_eval/tests/test_cloudwatch_export.py`
    - Use botocore.stub.Stubber (or moto) for mocking boto3 calls
    - Assert no adapter module imports inside exporter (verify isolation)
    - Test log group discovery with prefix
    - Test log group discovery with regex pattern
    - Test Generic JSON event output format (events only, no turns/final_answer)
    - Test authentication error handling
    - Test rate limiting and backoff behavior
    - Test pagination handling
    - Test empty result handling
    - Test explicit failure message when no log groups found
    - Verify exported files can be normalized by adapter
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 4.10_
  
  - [ ]* 19.2 Add integration test for export script
    - **Property 10: Export Script Isolation** - For any Generic JSON file from export script, it's processable by adapt()
    - Verify exporter doesn't import adapter modules (prevents coupling)
    - **Validates: Requirements 5.4, 4.6**
  
  - [ ]* 19.3 Add CloudWatch export validation test
    - **Property 11: CloudWatch Export Validation** - For any traces exported from CloudWatch, adapter achieves 100% schema compliance for clean inputs
    - **Validates: Requirements 9.2, 9.3**

- [x] 20. Add logging and documentation
  - [x] 20.1 Add logging to adapter
    - Add INFO logging for successful normalizations
    - Add INFO logging for segmentation strategy selected
    - Add WARNING logging when applying defaults and confidence penalties
    - Add WARNING logging for orphan tool results
    - Add WARNING logging for stitched trace suspects
    - Add ERROR logging for validation failures
    - Add --debug flag support to print adapter_stats and segmentation_strategy_reason
    - _Requirements: 2.3, 3.5_
  
  - [x] 20.2 Add comprehensive docstrings
    - Document `adapt()` with examples (renamed from load_and_normalize_trace)
    - Document DEFAULT_CONFIG_PATH constant
    - Document all internal classes and methods
    - Include type hints throughout
    - Document adapter_config.yaml structure and stages
    - Document each stage: Normalize, Classify, Segment, Derive
    - Document exception taxonomy (InputError, ValidationError, AdaptationError)
    - _Requirements: 2.1_
  
  - [x] 20.3 Update agent-eval README
    - Add Phase 1 usage examples with adapt() function
    - Document turn-aware schema structure
    - Document adapter_config.yaml stages (Normalize → Classify → Segment → Derive)
    - Document sample trace structure
    - Document CloudWatch export script usage with log group discovery
    - Document confidence scoring system
    - Document supported source formats (Generic JSON, OTEL, CloudWatch)
    - Add "Known Limitations" section
    - Add "How to Add New Mappings" section (config-only, no code changes)
    - Document --debug flag for troubleshooting
    - _Requirements: 7.7_

- [x] 21. Final checkpoint - Validate Phase 1 completion
  - Run all tests (unit + property-based): `pytest -q agent_eval/tests/`
  - Verify coverage threshold: minimum 85% for Phase 1 code
  - Verify all sample traces normalize successfully
  - Verify schema compliance for all outputs
  - Verify confidence scoring works correctly
  - Verify multi-turn segmentation works correctly
  - Machine-checkable gate: all tests pass + coverage >= 85%
  - Review adapter_stats output for completeness
  - Review documentation completeness (README, docstrings, known limitations)

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (minimum 100 iterations each)
- Unit tests validate specific examples and edge cases
- CloudWatch export script is standalone (not imported by adapter)
- All code isolated under agent-eval/ directory
- Adapter uses multi-stage pipeline: Normalize → Classify → Segment → Derive
- Configuration file (adapter_config.yaml v6) is production-ready and already created
- DEFAULT_CONFIG_PATH constant ensures config loads regardless of CWD
- Implementation follows config-driven architecture for maximum flexibility
