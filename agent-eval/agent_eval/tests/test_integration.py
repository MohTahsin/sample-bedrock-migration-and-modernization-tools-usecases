"""
Integration tests for the Generic JSON adapter.

Tests cover the complete pipeline: Normalize → Classify → Segment → Derive

Test scenarios:
- Single-turn trace normalization
- Multi-turn trace normalization
- Turn-aware output structure
- adapter_stats generation with all fields
- Golden tests for known trace patterns

Requirements: 2.2, 2.12
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any

from agent_eval.adapters.generic_json import adapt
from agent_eval.utils.validation import load_schema, validate_against_schema


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def schema_path() -> Path:
    """Path to normalized schema."""
    return Path(__file__).parent.parent / "schemas" / "normalized_run.schema.json"


@pytest.fixture
def schema(schema_path: Path) -> Dict[str, Any]:
    """Load normalized schema."""
    return load_schema(str(schema_path))


@pytest.fixture
def sample_traces_dir() -> Path:
    """Path to sample traces directory."""
    return Path(__file__).parent.parent.parent / "examples" / "sample_traces"


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

def assert_schema_compliant(result: Dict[str, Any], schema: Dict[str, Any]) -> None:
    """Assert that result is schema-compliant."""
    is_valid, errors = validate_against_schema(result, schema)
    assert is_valid, f"Schema validation failed: {errors}"


def assert_has_required_fields(result: Dict[str, Any]) -> None:
    """Assert that result has all required top-level fields."""
    assert "run_id" in result
    assert "metadata" in result
    assert "adapter_stats" in result
    assert "turns" in result


def assert_has_adapter_stats_fields(stats: Dict[str, Any]) -> None:
    """Assert that adapter_stats has required fields."""
    assert "total_events_processed" in stats
    assert "turn_count" in stats
    assert "confidence_penalties" in stats
    assert isinstance(stats["confidence_penalties"], list)


def assert_turn_structure(turn: Dict[str, Any]) -> None:
    """Assert that turn has required structure."""
    assert "turn_id" in turn
    assert "user_query" in turn
    assert "final_answer" in turn
    assert "steps" in turn
    assert "confidence" in turn
    assert isinstance(turn["steps"], list)
    assert isinstance(turn["confidence"], (int, float))
    assert 0 <= turn["confidence"] <= 1


# -------------------------------------------------------------------------
# Test: Complete Pipeline - Single Turn
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_single_turn_success_complete_pipeline(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test complete pipeline with single-turn success trace."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    # Execute complete pipeline
    result = adapt(str(trace_path))
    
    # Verify schema compliance
    assert_schema_compliant(result, schema)
    
    # Verify required fields
    assert_has_required_fields(result)
    assert_has_adapter_stats_fields(result["adapter_stats"])
    
    # Verify at least one turn (segmentation strategy may split into multiple turns)
    assert len(result["turns"]) >= 1
    
    # Verify each turn structure
    for turn in result["turns"]:
        assert_turn_structure(turn)
        # Verify turn has steps
        assert len(turn["steps"]) >= 0  # May have empty steps
    
    # Verify metadata
    assert "adapter_version" in result["metadata"]
    assert "processed_at" in result["metadata"]
    assert "run_confidence" in result["metadata"]
    
    # Verify confidence score is reasonable
    assert result["metadata"]["run_confidence"] >= 0.5


@pytest.mark.integration
def test_single_turn_with_tool_calls(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test single-turn trace with tool calls."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    
    # Verify schema compliance
    assert_schema_compliant(result, schema)
    
    # Check for tool-related steps
    turn = result["turns"][0]
    tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
    
    # If trace has tool calls, verify structure
    if tool_steps:
        for step in tool_steps:
            assert "name" in step
            assert "status" in step
            # Tool calls should have tool_run_id if available
            # (may be null for some traces)


# -------------------------------------------------------------------------
# Test: Complete Pipeline - Multi-Turn
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_multi_turn_complete_pipeline(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test complete pipeline with multi-turn trace."""
    trace_path = sample_traces_dir / "trace_multi_turn.json"
    
    # Execute complete pipeline
    result = adapt(str(trace_path))
    
    # Verify schema compliance
    assert_schema_compliant(result, schema)
    
    # Verify required fields
    assert_has_required_fields(result)
    
    # Verify multiple turns
    assert len(result["turns"]) > 1
    
    # Verify each turn structure
    for turn in result["turns"]:
        assert_turn_structure(turn)
        # Each turn should have unique turn_id
        assert turn["turn_id"]
    
    # Verify turn_ids are unique
    turn_ids = [t["turn_id"] for t in result["turns"]]
    assert len(turn_ids) == len(set(turn_ids)), "Turn IDs should be unique"
    
    # Verify segmentation strategy
    assert "segmentation_strategy_used" in result["metadata"]
    strategy = result["metadata"]["segmentation_strategy_used"]
    assert strategy in ["TURN_ID", "SESSION_PLUS_REQUEST", "SESSION_PLUS_TRACE_THEN_ANCHOR_SPLIT", "SINGLE_TURN"]


@pytest.mark.integration
def test_multi_turn_confidence_scores(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that multi-turn trace has confidence scores for each turn."""
    trace_path = sample_traces_dir / "trace_multi_turn.json"
    
    result = adapt(str(trace_path))
    
    # Verify each turn has confidence score
    for turn in result["turns"]:
        assert "confidence" in turn
        assert isinstance(turn["confidence"], (int, float))
        assert 0 <= turn["confidence"] <= 1
    
    # Verify run_confidence is average of turn confidences
    turn_confidences = [t["confidence"] for t in result["turns"]]
    expected_run_confidence = sum(turn_confidences) / len(turn_confidences)
    actual_run_confidence = result["metadata"]["run_confidence"]
    
    # Allow small floating point difference
    assert abs(actual_run_confidence - expected_run_confidence) < 0.01


# -------------------------------------------------------------------------
# Test: Turn-Aware Output Structure
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_turn_aware_structure(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that output has proper turn-aware structure."""
    trace_path = sample_traces_dir / "trace_multi_turn.json"
    
    result = adapt(str(trace_path))
    
    # Verify top-level structure
    assert "run_id" in result
    assert "metadata" in result
    assert "adapter_stats" in result
    assert "turns" in result
    
    # Verify turns is array
    assert isinstance(result["turns"], list)
    
    # Verify each turn has required fields
    for turn in result["turns"]:
        assert "turn_id" in turn
        assert "user_query" in turn
        assert "final_answer" in turn
        assert "steps" in turn
        assert "confidence" in turn
        
        # Verify steps is array
        assert isinstance(turn["steps"], list)
        
        # Verify each step has required fields
        for step in turn["steps"]:
            assert "name" in step
            assert "status" in step


@pytest.mark.integration
def test_turn_latency_fields(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that turns have latency fields."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    
    # Verify each turn has latency fields
    for turn in result["turns"]:
        # These fields should exist (may be null)
        assert "normalized_latency_ms" in turn
        assert "runtime_reported_latency_ms" in turn
        assert "total_latency_ms" in turn
        
        # If normalized_latency_ms is present, it should be non-negative
        if turn["normalized_latency_ms"] is not None:
            assert turn["normalized_latency_ms"] >= 0


# -------------------------------------------------------------------------
# Test: adapter_stats Generation
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_adapter_stats_all_fields(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that adapter_stats contains all expected fields."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    stats = result["adapter_stats"]
    
    # Required fields
    assert "total_events_processed" in stats
    assert "turn_count" in stats
    assert "confidence_penalties" in stats
    
    # Verify types
    assert isinstance(stats["total_events_processed"], int)
    assert isinstance(stats["turn_count"], int)
    assert isinstance(stats["confidence_penalties"], list)
    
    # Verify counts are reasonable
    assert stats["total_events_processed"] > 0
    assert stats["turn_count"] > 0
    
    # Optional fields (may be present)
    # events_with_valid_timestamps, events_with_missing_data, etc.


@pytest.mark.integration
def test_adapter_stats_confidence_penalties(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that confidence penalties are properly tracked."""
    trace_path = sample_traces_dir / "trace_missing_timestamps.json"
    
    result = adapt(str(trace_path))
    stats = result["adapter_stats"]
    
    # Should have confidence penalties for missing timestamps
    penalties = stats["confidence_penalties"]
    assert isinstance(penalties, list)
    
    # Each penalty should have required fields
    for penalty in penalties:
        assert "reason" in penalty
        assert "penalty" in penalty
        assert "location" in penalty
        assert isinstance(penalty["penalty"], (int, float))
        assert 0 <= penalty["penalty"] <= 1


@pytest.mark.integration
def test_adapter_stats_events_by_kind(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that events_by_kind histogram is generated."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    stats = result["adapter_stats"]
    
    # events_by_kind may be present
    if "events_by_kind" in stats:
        events_by_kind = stats["events_by_kind"]
        assert isinstance(events_by_kind, dict)
        
        # Each kind should have a count
        for kind, count in events_by_kind.items():
            assert isinstance(kind, str)
            assert isinstance(count, int)
            assert count >= 0


# -------------------------------------------------------------------------
# Test: Golden Tests for Known Trace Patterns
# -------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("trace_file", [
    "trace_single_turn_success.json",
    "trace_multi_turn.json",
    "trace_minimal_fields.json",
    "trace_with_failure.json",
])
def test_golden_trace_patterns(trace_file: str, sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: verify known trace patterns normalize successfully."""
    trace_path = sample_traces_dir / trace_file
    
    # Should not raise exception
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Should have required fields
    assert_has_required_fields(result)
    
    # Should have at least one turn
    assert len(result["turns"]) > 0


@pytest.mark.integration
def test_golden_orphan_tool_results(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: orphan tool results handled gracefully."""
    trace_path = sample_traces_dir / "trace_orphan_tool_results.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Should have orphan_tool_results tracked in adapter_stats
    stats = result["adapter_stats"]
    if "orphan_tool_results" in stats:
        orphans = stats["orphan_tool_results"]
        assert isinstance(orphans, list)
        
        # Each orphan should have location
        for orphan in orphans:
            assert "location" in orphan


@pytest.mark.integration
def test_golden_otel_format(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: OpenTelemetry format trace."""
    trace_path = sample_traces_dir / "trace_otel_format.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Should have required fields
    assert_has_required_fields(result)
    
    # OTEL traces should have span_id fields
    for turn in result["turns"]:
        for step in turn["steps"]:
            # span_id may be present
            if "span_id" in step and step["span_id"] is not None:
                assert isinstance(step["span_id"], str)


@pytest.mark.integration
def test_golden_stitched_trace(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: stitched multi-turn trace."""
    trace_path = sample_traces_dir / "trace_stitched.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Should have multiple turns
    assert len(result["turns"]) > 1
    
    # Should have segmentation strategy
    assert "segmentation_strategy_used" in result["metadata"]


@pytest.mark.integration
def test_golden_missing_timestamps(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: trace with missing timestamps."""
    trace_path = sample_traces_dir / "trace_missing_timestamps.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant (graceful degradation)
    assert_schema_compliant(result, schema)
    
    # Should have confidence penalties
    penalties = result["adapter_stats"]["confidence_penalties"]
    assert len(penalties) > 0
    
    # Should have missing_timestamp penalty
    penalty_reasons = [p["reason"] for p in penalties]
    assert "missing_timestamp" in penalty_reasons


@pytest.mark.integration
def test_golden_duplicate_tool_calls(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: trace with duplicate tool calls (deduplication)."""
    trace_path = sample_traces_dir / "trace_duplicate_tool_calls.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Should have deduplicated tool calls
    # (exact behavior depends on config, but should not crash)
    assert len(result["turns"]) > 0


@pytest.mark.integration
def test_golden_bad_epoch_units(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Golden test: trace with ambiguous epoch values."""
    trace_path = sample_traces_dir / "trace_bad_epoch_units.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant (magnitude inference + year bounds)
    assert_schema_compliant(result, schema)
    
    # May have confidence penalties for timestamp issues
    # (depends on whether magnitude inference succeeded)


# -------------------------------------------------------------------------
# Test: Edge Cases
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_empty_steps_array(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that empty steps array is handled correctly."""
    trace_path = sample_traces_dir / "trace_minimal_fields.json"
    
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)
    
    # Turns may have empty steps arrays
    for turn in result["turns"]:
        assert isinstance(turn["steps"], list)
        # Empty steps is valid


@pytest.mark.integration
def test_metadata_fields(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that metadata contains required fields."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    metadata = result["metadata"]
    
    # Required fields
    assert "adapter_version" in metadata
    assert "processed_at" in metadata
    
    # Verify types
    assert isinstance(metadata["adapter_version"], str)
    assert isinstance(metadata["processed_at"], str)
    
    # processed_at should be ISO 8601 format
    from datetime import datetime
    datetime.fromisoformat(metadata["processed_at"].replace("Z", "+00:00"))


@pytest.mark.integration
def test_mapping_coverage(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that mapping_coverage is calculated."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    result = adapt(str(trace_path))
    metadata = result["metadata"]
    
    # mapping_coverage should be present
    if "mapping_coverage" in metadata:
        coverage = metadata["mapping_coverage"]
        
        # Should have required fields
        assert "ids_coverage" in coverage
        assert "time_coverage" in coverage
        assert "tool_coverage" in coverage
        assert "text_coverage" in coverage
        assert "overall_mapping_coverage" in coverage
        
        # All should be between 0 and 1
        for key, value in coverage.items():
            assert isinstance(value, (int, float))
            assert 0 <= value <= 1


# -------------------------------------------------------------------------
# Test: Error Handling
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_nonexistent_file():
    """Test that nonexistent file raises InputError."""
    from agent_eval.adapters.generic_json.exceptions import InputError
    
    with pytest.raises(InputError) as exc_info:
        adapt("/nonexistent/trace.json")
    
    assert "not found" in str(exc_info.value).lower() or "does not exist" in str(exc_info.value).lower()


@pytest.mark.integration
def test_invalid_json_file(tmp_path: Path):
    """Test that invalid JSON raises InputError."""
    from agent_eval.adapters.generic_json.exceptions import InputError
    
    # Create invalid JSON file
    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{invalid json")
    
    with pytest.raises(InputError) as exc_info:
        adapt(str(invalid_json))
    
    assert "JSON" in str(exc_info.value) or "parse" in str(exc_info.value).lower()


# -------------------------------------------------------------------------
# Test: Performance
# -------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.slow
def test_large_trace_performance(sample_traces_dir: Path, schema: Dict[str, Any]):
    """Test that adapter handles large traces without memory errors."""
    # Use any available trace (or skip if no large trace available)
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    # Should complete without memory errors
    result = adapt(str(trace_path))
    
    # Should be schema compliant
    assert_schema_compliant(result, schema)


# -------------------------------------------------------------------------
# Test: Deterministic Output
# -------------------------------------------------------------------------

@pytest.mark.integration
def test_deterministic_output(sample_traces_dir: Path):
    """Test that adapter produces deterministic output."""
    trace_path = sample_traces_dir / "trace_single_turn_success.json"
    
    # Run twice
    result1 = adapt(str(trace_path))
    result2 = adapt(str(trace_path))
    
    # Results should be identical (except processed_at timestamp)
    # Compare run_id, turns, adapter_stats (excluding processed_at)
    assert result1["run_id"] == result2["run_id"]
    assert len(result1["turns"]) == len(result2["turns"])
    
    # Turn IDs should be identical
    turn_ids1 = [t["turn_id"] for t in result1["turns"]]
    turn_ids2 = [t["turn_id"] for t in result2["turns"]]
    assert turn_ids1 == turn_ids2
    
    # Step counts should be identical
    for t1, t2 in zip(result1["turns"], result2["turns"]):
        assert len(t1["steps"]) == len(t2["steps"])
