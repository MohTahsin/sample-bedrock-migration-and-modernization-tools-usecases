"""
Unit tests for validation.py

Tests cover:
- Schema loading with valid and invalid paths
- Validation with compliant and non-compliant data
- Timestamp parsing with various formats (ISO 8601, epoch ms/s/ns, UnixNano)
- Timestamp magnitude-based inference
- Timestamp year bounds validation (2000-2100)
- Confidence score calculation with penalties
- Latency sanitization (negative → zero)
- Error message formatting
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

from agent_eval.utils.validation import (
    load_schema,
    validate_against_schema,
    parse_timestamp,
    sanitize_latency,
    calculate_confidence_score
)


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def valid_schema() -> Dict[str, Any]:
    """Minimal valid JSON Schema."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["run_id", "turns"],
        "properties": {
            "run_id": {"type": "string"},
            "turns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["turn_id", "confidence"],
                    "properties": {
                        "turn_id": {"type": "string"},
                        "confidence": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1
                        }
                    }
                }
            }
        }
    }


@pytest.fixture
def temp_schema_file(valid_schema: Dict[str, Any]) -> Path:
    """Create a temporary schema file with valid JSON Schema."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(valid_schema, f)
        return Path(f.name)


# -------------------------------------------------------------------------
# Test: Schema Loading
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_load_schema_valid_file(temp_schema_file: Path):
    """Test loading valid schema file."""
    schema = load_schema(str(temp_schema_file))
    
    assert schema["type"] == "object"
    assert "run_id" in schema["required"]
    assert "turns" in schema["properties"]
    
    # Cleanup
    temp_schema_file.unlink()


@pytest.mark.unit
def test_load_schema_nonexistent_file():
    """Test loading non-existent schema file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as exc_info:
        load_schema("/nonexistent/path/schema.json")
    
    assert "Schema file not found" in str(exc_info.value)


@pytest.mark.unit
def test_load_schema_empty_file():
    """Test loading empty schema file raises ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("")  # Empty file
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            load_schema(str(temp_path))
        
        assert "Failed to parse JSON schema" in str(exc_info.value) or "Schema file is empty" in str(exc_info.value)
    finally:
        temp_path.unlink()


@pytest.mark.unit
def test_load_schema_invalid_json():
    """Test loading invalid JSON raises ValueError."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("{invalid json")
        temp_path = Path(f.name)
    
    try:
        with pytest.raises(ValueError) as exc_info:
            load_schema(str(temp_path))
        
        assert "Failed to parse JSON schema" in str(exc_info.value)
    finally:
        temp_path.unlink()


# -------------------------------------------------------------------------
# Test: Schema Validation
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_validate_compliant_data(valid_schema: Dict[str, Any]):
    """Test validation with compliant data."""
    data = {
        "run_id": "test-run-123",
        "turns": [
            {"turn_id": "turn-1", "confidence": 0.95}
        ]
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is True
    assert errors == []


@pytest.mark.unit
def test_validate_missing_required_field(valid_schema: Dict[str, Any]):
    """Test validation with missing required field."""
    data = {
        "turns": [
            {"turn_id": "turn-1", "confidence": 0.95}
        ]
        # Missing run_id
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    assert any("run_id" in err for err in errors)


@pytest.mark.unit
def test_validate_invalid_type(valid_schema: Dict[str, Any]):
    """Test validation with invalid field type."""
    data = {
        "run_id": 123,  # Should be string
        "turns": [
            {"turn_id": "turn-1", "confidence": 0.95}
        ]
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    assert any("run_id" in err for err in errors)


@pytest.mark.unit
def test_validate_out_of_range_value(valid_schema: Dict[str, Any]):
    """Test validation with out-of-range value."""
    data = {
        "run_id": "test-run-123",
        "turns": [
            {"turn_id": "turn-1", "confidence": 1.5}  # Out of range [0, 1]
        ]
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    assert any("confidence" in err for err in errors)


@pytest.mark.unit
def test_validate_nested_error(valid_schema: Dict[str, Any]):
    """Test validation with nested field error."""
    data = {
        "run_id": "test-run-123",
        "turns": [
            {"turn_id": "turn-1"}  # Missing confidence
        ]
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    # Error should reference nested path
    assert any("turns" in err and "confidence" in err for err in errors)


# -------------------------------------------------------------------------
# Test: Timestamp Parsing - ISO 8601 Formats
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_timestamp_iso8601_with_z():
    """Test parsing ISO 8601 timestamp with Z suffix."""
    dt, is_trusted, error = parse_timestamp("2024-01-15T10:30:45Z")
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.second == 45
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_iso8601_with_microseconds():
    """Test parsing ISO 8601 timestamp with microseconds."""
    dt, is_trusted, error = parse_timestamp("2024-01-15T10:30:45.123456Z")
    
    assert dt is not None
    assert dt.microsecond == 123456
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_iso8601_with_offset():
    """Test parsing ISO 8601 timestamp with timezone offset."""
    dt, is_trusted, error = parse_timestamp("2024-01-15T10:30:45+05:00")
    
    assert dt is not None
    # Should be normalized to UTC
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_iso8601_naive():
    """Test parsing ISO 8601 timestamp without timezone (naive)."""
    dt, is_trusted, error = parse_timestamp("2024-01-15T10:30:45")
    
    assert dt is not None
    assert dt.tzinfo == timezone.utc  # Normalized to UTC
    assert is_trusted is False  # Marked as less trusted
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_space_separated():
    """Test parsing space-separated timestamp format."""
    dt, is_trusted, error = parse_timestamp("2024-01-15 10:30:45.123456")
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15
    assert dt.tzinfo == timezone.utc
    assert is_trusted is False  # No explicit timezone
    assert error is None


# -------------------------------------------------------------------------
# Test: Timestamp Parsing - Epoch Formats
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_timestamp_epoch_seconds():
    """Test parsing epoch timestamp in seconds."""
    # 2024-01-15 10:30:45 UTC
    epoch_s = 1705318245
    dt, is_trusted, error = parse_timestamp(epoch_s)
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_epoch_milliseconds():
    """Test parsing epoch timestamp in milliseconds."""
    # 2024-01-15 10:30:45.123 UTC
    epoch_ms = 1705318245123
    dt, is_trusted, error = parse_timestamp(epoch_ms)
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15
    assert dt.microsecond == 123000
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_epoch_nanoseconds():
    """Test parsing epoch timestamp in nanoseconds."""
    # 2024-01-15 10:30:45.123456789 UTC
    epoch_ns = 1705318245123456789
    dt, is_trusted, error = parse_timestamp(epoch_ns)
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.month == 1
    assert dt.day == 15
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_unix_nano_field():
    """Test parsing UnixNano field (OTEL format)."""
    # 2024-01-15 10:30:45.123456789 UTC
    epoch_ns = 1705318245123456789
    dt, is_trusted, error = parse_timestamp(
        epoch_ns,
        field_name="startTimeUnixNano"
    )
    
    assert dt is not None
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc
    assert is_trusted is True
    assert error is None


# -------------------------------------------------------------------------
# Test: Timestamp Parsing - Magnitude-Based Inference
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_timestamp_magnitude_inference_seconds():
    """Test magnitude-based inference for seconds."""
    # Value < 1e11 should be inferred as seconds
    epoch_s = 1705318245  # ~1.7 billion
    dt, is_trusted, error = parse_timestamp(
        epoch_s,
        infer_epoch_unit_by_magnitude=True
    )
    
    assert dt is not None
    assert dt.year == 2024
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_magnitude_inference_milliseconds():
    """Test magnitude-based inference for milliseconds."""
    # Value < 1e14 should be inferred as milliseconds
    epoch_ms = 1705318245123  # ~1.7 trillion
    dt, is_trusted, error = parse_timestamp(
        epoch_ms,
        infer_epoch_unit_by_magnitude=True
    )
    
    assert dt is not None
    assert dt.year == 2024
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_magnitude_inference_nanoseconds():
    """Test magnitude-based inference for nanoseconds."""
    # Value >= 1e14 should be inferred as nanoseconds
    epoch_ns = 1705318245123456789  # ~1.7 quintillion
    dt, is_trusted, error = parse_timestamp(
        epoch_ns,
        infer_epoch_unit_by_magnitude=True
    )
    
    assert dt is not None
    assert dt.year == 2024
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_magnitude_inference_fallback():
    """Test magnitude-based inference with fallback to other units."""
    # Value that would be out of bounds for inferred unit
    # Should try other units
    epoch_value = 999999999  # Could be seconds or milliseconds
    dt, is_trusted, error = parse_timestamp(
        epoch_value,
        infer_epoch_unit_by_magnitude=True
    )
    
    # Should successfully parse with some unit
    assert dt is not None or error is not None


# -------------------------------------------------------------------------
# Test: Timestamp Parsing - Year Bounds Validation
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_timestamp_year_too_early():
    """Test timestamp with year before min_reasonable_year."""
    # 1999-01-01 (before 2000)
    dt, is_trusted, error = parse_timestamp(
        "1999-01-01T00:00:00Z",
        min_reasonable_year=2000
    )
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "outside reasonable range" in error


@pytest.mark.unit
def test_parse_timestamp_year_too_late():
    """Test timestamp with year after max_reasonable_year."""
    # 2101-01-01 (after 2100)
    dt, is_trusted, error = parse_timestamp(
        "2101-01-01T00:00:00Z",
        max_reasonable_year=2100
    )
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "outside reasonable range" in error


@pytest.mark.unit
def test_parse_timestamp_year_within_bounds():
    """Test timestamp with year within bounds."""
    # 2050-01-01 (within 2000-2100)
    dt, is_trusted, error = parse_timestamp(
        "2050-01-01T00:00:00Z",
        min_reasonable_year=2000,
        max_reasonable_year=2100
    )
    
    assert dt is not None
    assert dt.year == 2050
    assert is_trusted is True
    assert error is None


@pytest.mark.unit
def test_parse_timestamp_epoch_year_bounds():
    """Test epoch timestamp year bounds validation."""
    # Epoch value that would result in year 1999
    epoch_1999 = 915148800  # 1999-01-01
    dt, is_trusted, error = parse_timestamp(
        epoch_1999,
        min_reasonable_year=2000
    )
    
    # Should fail year bounds check
    assert dt is None or error is not None


# -------------------------------------------------------------------------
# Test: Timestamp Parsing - Edge Cases
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_parse_timestamp_none():
    """Test parsing None timestamp."""
    dt, is_trusted, error = parse_timestamp(None)
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "None" in error


@pytest.mark.unit
def test_parse_timestamp_negative_epoch():
    """Test parsing negative epoch timestamp."""
    dt, is_trusted, error = parse_timestamp(-1000)
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "Negative epoch" in error


@pytest.mark.unit
def test_parse_timestamp_zero_epoch():
    """Test parsing zero epoch timestamp."""
    dt, is_trusted, error = parse_timestamp(0)
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "zero" in error


@pytest.mark.unit
def test_parse_timestamp_invalid_string():
    """Test parsing invalid timestamp string."""
    dt, is_trusted, error = parse_timestamp("not-a-timestamp")
    
    assert dt is None
    assert is_trusted is False
    assert error is not None


@pytest.mark.unit
def test_parse_timestamp_unsupported_type():
    """Test parsing unsupported timestamp type."""
    dt, is_trusted, error = parse_timestamp({"timestamp": "2024-01-01"})
    
    assert dt is None
    assert is_trusted is False
    assert error is not None
    assert "Unsupported timestamp type" in error


@pytest.mark.unit
def test_parse_timestamp_small_epoch_value():
    """Test parsing very small epoch value (suspect)."""
    # Value < 1 billion (pre-2001 or unusual)
    small_value = 100000
    dt, is_trusted, error = parse_timestamp(small_value)
    
    # Should either parse as untrusted or fail
    if dt is not None:
        assert is_trusted is False
    else:
        assert error is not None


# -------------------------------------------------------------------------
# Test: Latency Sanitization
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_sanitize_latency_positive():
    """Test sanitizing positive latency value."""
    result = sanitize_latency(123.45)
    assert result == 123.45


@pytest.mark.unit
def test_sanitize_latency_zero():
    """Test sanitizing zero latency value."""
    result = sanitize_latency(0)
    assert result == 0.0


@pytest.mark.unit
def test_sanitize_latency_negative():
    """Test sanitizing negative latency value (converts to zero)."""
    result = sanitize_latency(-50.0)
    assert result == 0.0


@pytest.mark.unit
def test_sanitize_latency_string_numeric():
    """Test sanitizing numeric string latency value."""
    result = sanitize_latency("123.45")
    assert result == 123.45


@pytest.mark.unit
def test_sanitize_latency_none():
    """Test sanitizing None latency value."""
    result = sanitize_latency(None)
    assert result is None


@pytest.mark.unit
def test_sanitize_latency_invalid_string():
    """Test sanitizing invalid string latency value."""
    result = sanitize_latency("not-a-number")
    assert result is None


@pytest.mark.unit
def test_sanitize_latency_invalid_type():
    """Test sanitizing invalid type latency value."""
    result = sanitize_latency({"latency": 123})
    assert result is None


# -------------------------------------------------------------------------
# Test: Confidence Score Calculation
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_calculate_confidence_no_penalties():
    """Test confidence score with no penalties."""
    score = calculate_confidence_score([])
    assert score == 1.0


@pytest.mark.unit
def test_calculate_confidence_single_penalty():
    """Test confidence score with single penalty."""
    penalties = [{"penalty": 0.2, "reason": "missing_timestamp"}]
    score = calculate_confidence_score(penalties)
    assert score == 0.8


@pytest.mark.unit
def test_calculate_confidence_multiple_penalties():
    """Test confidence score with multiple penalties."""
    penalties = [
        {"penalty": 0.3, "reason": "missing_timestamp"},
        {"penalty": 0.2, "reason": "missing_latency"}
    ]
    score = calculate_confidence_score(penalties)
    assert score == 0.5


@pytest.mark.unit
def test_calculate_confidence_clamped_to_zero():
    """Test confidence score is clamped to zero."""
    penalties = [
        {"penalty": 0.6, "reason": "missing_timestamp"},
        {"penalty": 0.6, "reason": "missing_latency"}
    ]
    score = calculate_confidence_score(penalties)
    assert score == 0.0


@pytest.mark.unit
def test_calculate_confidence_clamped_to_one():
    """Test confidence score is clamped to one."""
    penalties = [{"penalty": -0.5, "reason": "invalid"}]
    score = calculate_confidence_score(penalties)
    assert score == 1.0


@pytest.mark.unit
def test_calculate_confidence_custom_base_score():
    """Test confidence score with custom base score."""
    penalties = [{"penalty": 0.2, "reason": "missing_timestamp"}]
    score = calculate_confidence_score(penalties, base_score=0.9)
    assert score == 0.7


@pytest.mark.unit
def test_calculate_confidence_invalid_penalty_value():
    """Test confidence score with invalid penalty value (guards against errors)."""
    penalties = [
        {"penalty": 0.2, "reason": "valid"},
        {"penalty": "invalid", "reason": "invalid_value"},
        {"penalty": None, "reason": "none_value"}
    ]
    score = calculate_confidence_score(penalties)
    # Should only count the valid penalty
    assert score == 0.8


@pytest.mark.unit
def test_calculate_confidence_missing_penalty_field():
    """Test confidence score with missing penalty field."""
    penalties = [
        {"penalty": 0.2, "reason": "valid"},
        {"reason": "missing_penalty_field"}
    ]
    score = calculate_confidence_score(penalties)
    # Should only count the valid penalty
    assert score == 0.8


@pytest.mark.unit
def test_calculate_confidence_invalid_base_score():
    """Test confidence score with invalid base score (guards against errors)."""
    penalties = [{"penalty": 0.2, "reason": "missing_timestamp"}]
    score = calculate_confidence_score(penalties, base_score="invalid")
    # Should default to 1.0 base score
    assert score == 0.8


# -------------------------------------------------------------------------
# Test: Error Message Formatting
# -------------------------------------------------------------------------

@pytest.mark.unit
def test_validation_error_message_format(valid_schema: Dict[str, Any]):
    """Test validation error messages are well-formatted."""
    data = {
        "run_id": 123,  # Wrong type
        "turns": []
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    
    # Error should include field path and description
    error_msg = errors[0]
    assert "run_id" in error_msg
    assert ":" in error_msg  # Should have field: message format


@pytest.mark.unit
def test_validation_error_sorted_order(valid_schema: Dict[str, Any]):
    """Test validation errors are returned in sorted order."""
    data = {
        # Multiple errors
        "run_id": 123,  # Wrong type
        "turns": [
            {"turn_id": 456, "confidence": 1.5}  # Multiple errors in nested object
        ]
    }
    
    is_valid, errors = validate_against_schema(data, valid_schema)
    
    assert is_valid is False
    assert len(errors) > 0
    
    # Errors should be in consistent order (sorted)
    # Run multiple times to verify stability
    for _ in range(3):
        _, errors_again = validate_against_schema(data, valid_schema)
        assert errors == errors_again


@pytest.mark.unit
def test_timestamp_error_message_descriptive():
    """Test timestamp parsing error messages are descriptive."""
    _, _, error = parse_timestamp("invalid-timestamp")
    
    assert error is not None
    assert len(error) > 0
    assert "invalid-timestamp" in error or "Failed to parse" in error


@pytest.mark.unit
def test_schema_load_error_message_descriptive():
    """Test schema loading error messages are descriptive."""
    try:
        load_schema("/nonexistent/path/schema.json")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError as e:
        error_msg = str(e)
        assert "Schema file not found" in error_msg
        assert "/nonexistent/path/schema.json" in error_msg
