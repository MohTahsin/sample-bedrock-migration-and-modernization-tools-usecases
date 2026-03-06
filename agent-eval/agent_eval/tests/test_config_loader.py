"""
Unit tests for config_loader.py

Tests cover:
- YAML loading with valid config
- Pydantic validation with invalid config
- Regex compilation and caching
- Field alias resolution with fallback chain
- Classification rule matching with regex
- Segmentation strategy selection
- Confidence penalty configuration
- Unknown key warnings
"""

import pytest
import tempfile
import re
from pathlib import Path
from typing import Dict, Any

from agent_eval.adapters.generic_json.config_loader import AdapterConfig


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def valid_config_yaml() -> str:
    """Minimal valid configuration YAML."""
    return """
version: 1
adapter_name: test-adapter

normalize:
  event_paths:
    - "events"
    - "trace.events"
  
  field_aliases:
    timestamp:
      - "timestamp"
      - "ts"
      - "attributes.timestamp"
    tool_name:
      - "tool_name"
      - "attributes.tool_name"
    event_type:
      - "event_type"
      - "type"
    role:
      - "role"
    tool_run_id:
      - "tool_run_id"
  
  timestamp_parse:
    epoch_units: ["ms", "s", "ns"]
    infer_epoch_unit_by_magnitude: true
    min_reasonable_year: 2000
    max_reasonable_year: 2100
    unix_nano_fields: ["startTimeUnixNano"]
    formats:
      - "%Y-%m-%d %H:%M:%S.%f"
  
  carry_fields:
    attributes_paths:
      - "attributes"
    keep_raw_event: true
    raw_event_max_bytes: 50000

classify:
  rule_order_policy: first_match_wins
  rules:
    - id: user_input_test
      kind: USER_INPUT
      any:
        - field: event_type
          regex: "(?i)user"
        - field: role
          equals: "user"
    
    - id: tool_call_test
      kind: TOOL_CALL
      all:
        - field: tool_name
          exists: true
      any:
        - field: tool_run_id
          exists: true
  
  default_kind: EVENT

segment:
  strategy_preference:
    - TURN_ID
    - SINGLE_TURN
  turn_id_fields: ["turn_id"]
  request_id_diagnosis:
    distinct_user_prompts_per_request_id_max: 1
    request_ids_per_user_prompt_max: 3
    sample_window_events: 5000
  anchor_events_in_order:
    - USER_INPUT
  tie_breaker_order:
    - USER_INPUT
    - EVENT
  emit_strategy_reason: true
  min_events_per_turn: 1

derive:
  phases:
    pre_tool: PRE_TOOL
    tool_call: TOOL_CALL
    post_tool: POST_TOOL
  
  prompt_context_strip:
    strip_kinds: ["PROMPT_CONTEXT"]
    strip_text_regex:
      - "(?is)<guidelines>.*?</guidelines>"
  
  output_extraction:
    top_level_path_syntax: "dot"
    top_level_dotpath_required: true
    top_level_fields:
      final_answer:
        - "final_answer"
      user_query:
        - "user_query"
      finish_reason:
        - "finish_reason"
    assistant_output_stream:
      include_kinds: ["LLM_OUTPUT_CHUNK"]
      exclude_if_text_matches_regex:
        - "(?is)<guidelines>.*?</guidelines>"
    join_with: ""
    max_chars: 200000
  
  tool_linking:
    tool_run_exists_only_if:
      kind_in: ["TOOL_CALL"]
      tool_name_required: true
    tool_run_id_fields: ["tool_run_id"]
    link_results_by:
      - TOOL_RUN_ID
    dedupe:
      enabled: true
      window_seconds: 2
      key_fields: ["tool_run_id"]
      prefer_richer_fields: ["tool_arguments"]
  
  latency:
    normalized_latency_ms:
      start_from_first_kind_in: ["USER_INPUT"]
      end_at_last_kind_in: ["EVENT"]
    keep_runtime_reported_latency_ms_fields:
      - "total_latency_ms"
    on_missing_timestamps: "null_and_penalize"
  
  attribution:
    verdicts:
      tool_used_if_has_kind: "TOOL_CALL"
      tool_output_only_if_text_matches_regex:
        - "(?is)\\\\bRetrieved\\\\s+\\\\d+\\\\s+results\\\\b"
    stitch_suspect:
      enabled: true
      question_line_regex: "(?m)^.{3,300}\\\\?$"
      distinct_question_count_suspect_at: 2

confidence:
  scoring:
    base: 1.0
    penalties:
      missing_timestamp: 0.4
      missing_grouping_ids: 0.3
  emit_fields:
    - "run_confidence"
    - "turn_confidence"

stats:
  emit_adapter_stats: true
  max_error_examples: 20
"""


@pytest.fixture
def temp_config_file(valid_config_yaml: str) -> Path:
    """Create a temporary config file with valid YAML."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(valid_config_yaml)
        return Path(f.name)


# -------------------------------------------------------------------------
# Test: YAML Loading
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_load_valid_yaml(temp_config_file: Path):
    """Test loading valid YAML configuration."""
    config = AdapterConfig(str(temp_config_file))
    
    assert config.get_version() == 1
    assert config.get_adapter_name() == "test-adapter"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_load_nonexistent_file():
    """Test loading non-existent config file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as exc_info:
        AdapterConfig("/nonexistent/path/config.yaml")
    
    assert "Configuration file not found" in str(exc_info.value)


@pytest.mark.unit
def test_load_empty_yaml():
    """Test loading empty YAML file raises ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("")  # Empty file
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            AdapterConfig(str(temp_path))
        
        assert "Configuration file is empty" in str(exc_info.value)
    finally:
        temp_path.unlink()


@pytest.mark.unit
def test_load_invalid_yaml():
    """Test loading invalid YAML raises ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid: yaml: content: [unclosed")
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            AdapterConfig(str(temp_path))
        
        assert "Failed to parse YAML" in str(exc_info.value)
    finally:
        temp_path.unlink()


# -------------------------------------------------------------------------
# Test: Pydantic Validation
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_pydantic_validation_missing_required_field():
    """Test Pydantic validation fails with missing required fields."""
    invalid_yaml = """
version: 1
# Missing adapter_name and other required sections
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_yaml)
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            AdapterConfig(str(temp_path))
        
        assert "Configuration validation failed" in str(exc_info.value)
    finally:
        temp_path.unlink()


@pytest.mark.unit
def test_pydantic_validation_invalid_type():
    """Test Pydantic validation fails with invalid field types."""
    invalid_yaml = """
version: "not_an_integer"
adapter_name: test
normalize:
  event_paths: "should_be_list"
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_yaml)
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            AdapterConfig(str(temp_path))
        
        assert "Configuration validation failed" in str(exc_info.value)
    finally:
        temp_path.unlink()


# -------------------------------------------------------------------------
# Test: Regex Compilation and Caching
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_regex_compilation_success(temp_config_file: Path):
    """Test regex patterns are compiled successfully at load time."""
    config = AdapterConfig(str(temp_config_file))
    
    # Verify compiled regexes exist
    assert len(config._compiled_regexes) > 0
    
    # Check specific patterns are compiled
    assert any("classify.rule" in key for key in config._compiled_regexes.keys())
    assert any("derive.prompt_context_strip" in key for key in config._compiled_regexes.keys())
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_regex_compilation_invalid_pattern():
    """Test invalid regex pattern raises ValueError at load time."""
    invalid_yaml = """
version: 1
adapter_name: test
normalize:
  event_paths: ["events"]
  field_aliases:
    timestamp: ["timestamp"]
  timestamp_parse:
    epoch_units: ["ms"]
    infer_epoch_unit_by_magnitude: true
    min_reasonable_year: 2000
    max_reasonable_year: 2100
    unix_nano_fields: []
    formats: []
  carry_fields:
    attributes_paths: []
    keep_raw_event: true
    raw_event_max_bytes: 50000
classify:
  rule_order_policy: first_match_wins
  rules:
    - id: bad_regex
      kind: TEST
      any:
        - field: test_field
          regex: "(?P<invalid"  # Invalid regex
  default_kind: EVENT
segment:
  strategy_preference: [SINGLE_TURN]
  turn_id_fields: []
  request_id_diagnosis:
    distinct_user_prompts_per_request_id_max: 1
    request_ids_per_user_prompt_max: 3
    sample_window_events: 5000
  anchor_events_in_order: []
  tie_breaker_order: []
  emit_strategy_reason: true
  min_events_per_turn: 1
derive:
  phases:
    pre_tool: PRE
    tool_call: TOOL
    post_tool: POST
  prompt_context_strip:
    strip_kinds: []
    strip_text_regex: []
  output_extraction:
    top_level_path_syntax: "dot"
    top_level_dotpath_required: true
    top_level_fields:
      final_answer: ["final_answer"]
      user_query: ["user_query"]
      finish_reason: ["finish_reason"]
    assistant_output_stream:
      include_kinds: []
      exclude_if_text_matches_regex: []
    join_with: ""
    max_chars: 200000
  tool_linking:
    tool_run_exists_only_if:
      kind_in: []
      tool_name_required: true
    tool_run_id_fields: []
    link_results_by: []
    dedupe:
      enabled: false
      window_seconds: 2
      key_fields: []
      prefer_richer_fields: []
  latency:
    normalized_latency_ms:
      start_from_first_kind_in: []
      end_at_last_kind_in: []
    keep_runtime_reported_latency_ms_fields: []
    on_missing_timestamps: "null_and_penalize"
  attribution:
    verdicts:
      tool_used_if_has_kind: "TOOL_CALL"
      tool_output_only_if_text_matches_regex: []
    stitch_suspect:
      enabled: false
      question_line_regex: "."
      distinct_question_count_suspect_at: 2
confidence:
  scoring:
    base: 1.0
    penalties: {}
  emit_fields: []
stats:
  emit_adapter_stats: true
  max_error_examples: 20
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(invalid_yaml)
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            AdapterConfig(str(temp_path))
        
        # Pydantic validates regex during schema validation, so error message differs
        assert "Invalid regex" in str(exc_info.value) or "Configuration validation failed" in str(exc_info.value)
        assert "test_field" in str(exc_info.value)
    finally:
        temp_path.unlink()


@pytest.mark.unit
def test_regex_caching(temp_config_file: Path):
    """Test regex patterns are cached for performance."""
    config = AdapterConfig(str(temp_config_file))
    
    # Get the same pattern twice
    key = list(config._compiled_regexes.keys())[0]
    pattern1 = config._compiled_regexes[key]
    pattern2 = config._compiled_regexes[key]
    
    # Should be the same object (cached)
    assert pattern1 is pattern2
    
    # Cleanup
    temp_config_file.unlink()


# -------------------------------------------------------------------------
# Test: Field Alias Resolution
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_field_alias_resolution_simple(temp_config_file: Path):
    """Test field alias resolution with simple field names."""
    config = AdapterConfig(str(temp_config_file))
    
    aliases = config.get_field_aliases("timestamp")
    assert aliases == ["timestamp", "ts", "attributes.timestamp"]
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_field_alias_resolution_nonexistent(temp_config_file: Path):
    """Test field alias resolution returns empty list for nonexistent field."""
    config = AdapterConfig(str(temp_config_file))
    
    aliases = config.get_field_aliases("nonexistent_field")
    assert aliases == []
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_field_value_with_fallback_first_match(temp_config_file: Path):
    """Test field value extraction uses first matching alias."""
    config = AdapterConfig(str(temp_config_file))
    
    # Data with first alias present
    data = {"timestamp": "2024-01-01T00:00:00Z"}
    value = config.get_field_value_with_fallback(data, "timestamp")
    assert value == "2024-01-01T00:00:00Z"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_field_value_with_fallback_second_match(temp_config_file: Path):
    """Test field value extraction falls back to second alias."""
    config = AdapterConfig(str(temp_config_file))
    
    # Data with second alias present
    data = {"ts": "2024-01-01T00:00:00Z"}
    value = config.get_field_value_with_fallback(data, "timestamp")
    assert value == "2024-01-01T00:00:00Z"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_field_value_with_fallback_nested(temp_config_file: Path):
    """Test field value extraction with nested dotted path."""
    config = AdapterConfig(str(temp_config_file))
    
    # Data with nested alias present
    data = {"attributes": {"timestamp": "2024-01-01T00:00:00Z"}}
    value = config.get_field_value_with_fallback(data, "timestamp")
    assert value == "2024-01-01T00:00:00Z"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_field_value_with_fallback_no_match(temp_config_file: Path):
    """Test field value extraction returns None when no alias matches."""
    config = AdapterConfig(str(temp_config_file))
    
    # Data without any matching alias
    data = {"other_field": "value"}
    value = config.get_field_value_with_fallback(data, "timestamp")
    assert value is None
    
    # Cleanup
    temp_config_file.unlink()


# -------------------------------------------------------------------------
# Test: Classification Rule Matching
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_classify_event_regex_match(temp_config_file: Path):
    """Test event classification with regex matching."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event matching user_input_test rule via regex
    event = {"event_type": "USER_MESSAGE"}
    kind, rule_id, reason = config.classify_event(event)
    
    assert kind == "USER_INPUT"
    assert rule_id == "user_input_test"
    assert "user_input_test" in reason
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_classify_event_equals_match(temp_config_file: Path):
    """Test event classification with equals matching."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event matching user_input_test rule via equals
    event = {"role": "user"}
    kind, rule_id, reason = config.classify_event(event)
    
    assert kind == "USER_INPUT"
    assert rule_id == "user_input_test"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_classify_event_exists_match(temp_config_file: Path):
    """Test event classification with exists matching."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event matching tool_call_test rule via exists
    event = {"tool_name": "my_tool", "tool_run_id": "123"}
    kind, rule_id, reason = config.classify_event(event)
    
    assert kind == "TOOL_CALL"
    assert rule_id == "tool_call_test"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_classify_event_all_conditions(temp_config_file: Path):
    """Test event classification with 'all' conditions (all must match)."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event with tool_name but no tool_run_id (should not match tool_call_test)
    event = {"tool_name": "my_tool"}
    kind, rule_id, reason = config.classify_event(event)
    
    # Should fall back to default kind
    assert kind == "EVENT"
    assert rule_id is None
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_classify_event_first_match_wins(temp_config_file: Path):
    """Test first_match_wins policy (first matching rule wins)."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event that could match multiple rules
    event = {"event_type": "USER_MESSAGE", "role": "user"}
    kind, rule_id, reason = config.classify_event(event)
    
    # Should match first rule (user_input_test)
    assert kind == "USER_INPUT"
    assert rule_id == "user_input_test"
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_classify_event_default_kind(temp_config_file: Path):
    """Test default kind is used when no rule matches."""
    config = AdapterConfig(str(temp_config_file))
    
    # Event that doesn't match any rule
    event = {"unknown_field": "value"}
    kind, rule_id, reason = config.classify_event(event)
    
    assert kind == "EVENT"
    assert rule_id is None
    assert "No classification rule matched" in reason
    
    # Cleanup
    temp_config_file.unlink()


# -------------------------------------------------------------------------
# Test: Segmentation Strategy Selection
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_get_segmentation_strategies(temp_config_file: Path):
    """Test segmentation strategies are returned in preference order."""
    config = AdapterConfig(str(temp_config_file))
    
    strategies = config.get_segmentation_strategies()
    assert strategies == ["TURN_ID", "SINGLE_TURN"]
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_turn_id_fields(temp_config_file: Path):
    """Test turn ID fields are returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    fields = config.get_turn_id_fields()
    assert fields == ["turn_id"]
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_anchor_events(temp_config_file: Path):
    """Test anchor events are returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    anchors = config.get_anchor_events()
    assert anchors == ["USER_INPUT"]
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_tie_breaker_order(temp_config_file: Path):
    """Test tie-breaker order is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    order = config.get_tie_breaker_order()
    assert order == ["USER_INPUT", "EVENT"]
    
    # Cleanup
    temp_config_file.unlink()


# -------------------------------------------------------------------------
# Test: Confidence Penalty Configuration
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_get_confidence_scoring_config(temp_config_file: Path):
    """Test confidence scoring configuration is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    scoring = config.get_confidence_scoring_config()
    assert scoring["base"] == 1.0
    assert scoring["penalties"]["missing_timestamp"] == 0.4
    assert scoring["penalties"]["missing_grouping_ids"] == 0.3
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_confidence_emit_fields(temp_config_file: Path):
    """Test confidence emit fields are returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    fields = config.get_confidence_emit_fields()
    assert "run_confidence" in fields
    assert "turn_confidence" in fields
    
    # Cleanup
    temp_config_file.unlink()


# -------------------------------------------------------------------------
# Test: Unknown Key Warnings
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_unknown_key_warning():
    """Test warning is emitted for unknown configuration keys."""
    yaml_with_unknown_key = """
version: 1
adapter_name: test
unknown_key: "this should trigger a warning"
normalize:
  event_paths: ["events"]
  field_aliases:
    timestamp: ["timestamp"]
  timestamp_parse:
    epoch_units: ["ms"]
    infer_epoch_unit_by_magnitude: true
    min_reasonable_year: 2000
    max_reasonable_year: 2100
    unix_nano_fields: []
    formats: []
  carry_fields:
    attributes_paths: []
    keep_raw_event: true
    raw_event_max_bytes: 50000
classify:
  rule_order_policy: first_match_wins
  rules:
    - id: test_rule
      kind: EVENT
      any:
        - field: test_field
          exists: true
  default_kind: EVENT
segment:
  strategy_preference: [SINGLE_TURN]
  turn_id_fields: []
  request_id_diagnosis:
    distinct_user_prompts_per_request_id_max: 1
    request_ids_per_user_prompt_max: 3
    sample_window_events: 5000
  anchor_events_in_order: []
  tie_breaker_order: []
  emit_strategy_reason: true
  min_events_per_turn: 1
derive:
  phases:
    pre_tool: PRE
    tool_call: TOOL
    post_tool: POST
  prompt_context_strip:
    strip_kinds: []
    strip_text_regex: []
  output_extraction:
    top_level_path_syntax: "dot"
    top_level_dotpath_required: true
    top_level_fields:
      final_answer: ["final_answer"]
      user_query: ["user_query"]
      finish_reason: ["finish_reason"]
    assistant_output_stream:
      include_kinds: []
      exclude_if_text_matches_regex: []
    join_with: ""
    max_chars: 200000
  tool_linking:
    tool_run_exists_only_if:
      kind_in: []
      tool_name_required: true
    tool_run_id_fields: []
    link_results_by: []
    dedupe:
      enabled: false
      window_seconds: 2
      key_fields: []
      prefer_richer_fields: []
  latency:
    normalized_latency_ms:
      start_from_first_kind_in: []
      end_at_last_kind_in: []
    keep_runtime_reported_latency_ms_fields: []
    on_missing_timestamps: "null_and_penalize"
  attribution:
    verdicts:
      tool_used_if_has_kind: "TOOL_CALL"
      tool_output_only_if_text_matches_regex: []
    stitch_suspect:
      enabled: false
      question_line_regex: "."
      distinct_question_count_suspect_at: 2
confidence:
  scoring:
    base: 1.0
    penalties: {}
  emit_fields: []
stats:
  emit_adapter_stats: true
  max_error_examples: 20
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(yaml_with_unknown_key)
        temp_path = Path(f.name)
    
    try:
        with pytest.warns(UserWarning, match="Unknown configuration keys"):
            config = AdapterConfig(str(temp_path))
            assert config is not None
    finally:
        temp_path.unlink()


# -------------------------------------------------------------------------
# Test: Additional Config Accessors
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_get_timestamp_parse_config(temp_config_file: Path):
    """Test timestamp parse configuration is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    ts_config = config.get_timestamp_parse_config()
    assert ts_config["epoch_units"] == ["ms", "s", "ns"]
    assert ts_config["infer_epoch_unit_by_magnitude"] is True
    assert ts_config["min_reasonable_year"] == 2000
    assert ts_config["max_reasonable_year"] == 2100
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_tool_linking_config(temp_config_file: Path):
    """Test tool linking configuration is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    tool_config = config.get_tool_linking_config()
    assert tool_config["tool_run_id_fields"] == ["tool_run_id"]
    assert tool_config["link_results_by"] == ["TOOL_RUN_ID"]
    assert tool_config["dedupe"]["enabled"] is True
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_should_emit_adapter_stats(temp_config_file: Path):
    """Test adapter stats emission flag is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    assert config.should_emit_adapter_stats() is True
    
    # Cleanup
    temp_config_file.unlink()


@pytest.mark.unit
def test_get_max_error_examples(temp_config_file: Path):
    """Test max error examples is returned correctly."""
    config = AdapterConfig(str(temp_config_file))
    
    assert config.get_max_error_examples() == 20
    
    # Cleanup
    temp_config_file.unlink()
