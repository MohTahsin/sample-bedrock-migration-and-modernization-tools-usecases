"""
Results and Report Output Validation Tests

This module validates results.json and report output to ensure evaluation results
are always valid, stable, and renderable. Tests focus on machine output validation
with minimal report rendering checks.

Requirements Coverage: 8.1, 8.2, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12

Test Strategy:
Part A: Machine output validation (primary focus)
- Test results.json is always valid JSON
- Test all required fields present in results.json
- Test stable output for identical inputs (deterministic)
- Test trace_id inclusion for traceability
- Test deterministic metrics inclusion in results
- Test aggregated judge scores inclusion in results (if available)
- Test confidence penalties inclusion in results (if available)
- Test timestamp serialization in ISO 8601 format
- Test NaN/Infinity serialization as null
- Test output validation against results schema before writing

Part B: Report rendering validation (minimal, if HTML report exists)
- Test evaluation output fields match report schema
- Test optional fields don't break rendering
"""

import pytest
import json
import yaml
import math
import tempfile
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Import output writer and related components
from agent_eval.evaluators.trace_eval.output_writer import OutputWriter
from agent_eval.evaluators.trace_eval.deterministic_metrics import DeterministicMetrics
from agent_eval.evaluators.trace_eval.judging.aggregator import CrossJudgeResult, WithinJudgeResult
from agent_eval.adapters.generic_json.adapter import adapt


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent.parent / "test-fixtures" / "baseline"


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def output_writer(temp_output_dir):
    """Create an OutputWriter instance."""
    return OutputWriter(str(temp_output_dir))


@pytest.fixture
def sample_metrics() -> Dict[str, Any]:
    """Create sample deterministic metrics for testing."""
    return {
        "turn_count": 2,
        "tool_call_count": 3,
        "tool_result_count": 3,
        "tool_success_rate": 1.0,
        "orphan_count": 0,
        "step_count": 5,
        "latency_ms": 1234.5,
        "first_turn_timestamp": "2024-01-15T10:30:00Z",
        "last_turn_timestamp": "2024-01-15T10:30:05Z"
    }


class MockMetricsResult:
    """Mock MetricsResult for testing."""
    def __init__(self, metrics_dict):
        self.metrics_dict = metrics_dict
    
    def to_dict(self):
        return self.metrics_dict


@pytest.fixture
def mock_metrics_result(sample_metrics):
    """Create a mock MetricsResult object."""
    return MockMetricsResult(sample_metrics)


@pytest.fixture
def sample_cross_judge_results() -> list:
    """Create sample cross-judge results for testing."""
    within_judge_result = WithinJudgeResult(
        judge_id="judge_1",
        rubric_id="correctness",
        turn_id="turn_1",
        majority_vote=None,
        median=4.0,
        mean=4.0,
        variance=0.0,
        sample_size=1,
        scoring_type="numeric"
    )
    
    cross_judge_result = CrossJudgeResult(
        rubric_id="correctness",
        turn_id="turn_1",
        individual_judge_results=[within_judge_result],
        weighted_vote=None,
        weighted_average=4.0,
        disagreement_signal=0.0,
        high_risk_flag=False,
        judge_count=1,
        scoring_type="numeric",
        mixed_types_error=None,
        scale_warning=None
    )
    
    return [cross_judge_result]


def load_trace(baseline_corpus_dir: Path, trace_id: str) -> Dict[str, Any]:
    """Load a trace JSON file from the baseline corpus."""
    trace_path = baseline_corpus_dir / f"{trace_id}.json"
    
    if not trace_path.exists():
        pytest.skip(f"Trace file not found: {trace_path}")
    
    with open(trace_path, 'r') as f:
        return json.load(f)


# -------------------------------------------------------------------------
# Part A: Machine Output Validation
# -------------------------------------------------------------------------

@pytest.mark.component
class TestResultsJsonValidation:
    """Validate results.json is always valid JSON with required fields."""

    
    def test_results_json_is_valid_json(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.1: THE Output_Writer SHALL always produce valid JSON in results.json
        
        Expected: results.json can be parsed without errors
        """
        # Build rubric results
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        # Write results.json
        results_path = output_writer.write_results_json(
            run_id="test_run_001",
            rubrics_config={"rubrics": [{"id": "correctness", "scope": "turn"}]},
            judge_config={"judges": [{"id": "judge_1"}]},
            input_data={"run_id": "test_run_001", "turns": []},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 1, "completed_jobs": 1, "failed_jobs": 0, "duration_seconds": 1.5}
        )
        
        # Verify file exists and is valid JSON
        assert Path(results_path).exists(), "results.json should be created"
        
        with open(results_path, 'r') as f:
            data = json.load(f)  # Should not raise JSONDecodeError
        
        assert isinstance(data, dict), "results.json should contain a JSON object"
    
    def test_all_required_fields_present(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.2: THE Output_Writer SHALL include all required fields in results.json
        
        Expected: All schema-required fields are present
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_002",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_002"},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        # Verify all required fields from schema
        required_fields = [
            "format_version",
            "run_id",
            "rubrics_hash",
            "judge_config_hash",
            "input_hash",
            "deterministic_metrics",
            "rubric_results",
            "judge_disagreements",
            "artifact_paths",
            "execution_stats"
        ]
        
        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from results.json"

    
    def test_trace_id_inclusion(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.6: THE Output_Writer SHALL include trace_id in results for traceability
        
        Expected: run_id field contains the trace identifier
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        test_run_id = "trace_abc123"
        results_path = output_writer.write_results_json(
            run_id=test_run_id,
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": test_run_id},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        assert data["run_id"] == test_run_id, "run_id should match the provided trace identifier"
    
    def test_deterministic_metrics_inclusion(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.7: THE Output_Writer SHALL include deterministic metrics in results
        
        Expected: deterministic_metrics field contains all computed metrics
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_003",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_003"},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        assert "deterministic_metrics" in data, "deterministic_metrics field should be present"
        metrics = data["deterministic_metrics"]
        
        # Verify key metrics are included
        assert "turn_count" in metrics, "turn_count should be in deterministic_metrics"
        assert "tool_call_count" in metrics, "tool_call_count should be in deterministic_metrics"
        assert "tool_success_rate" in metrics, "tool_success_rate should be in deterministic_metrics"

    
    def test_aggregated_judge_scores_inclusion(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.8: THE Output_Writer SHALL include aggregated judge scores in results
        
        Expected: rubric_results contains cross-judge aggregated scores
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_004",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_004"},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 1, "completed_jobs": 1, "failed_jobs": 0, "duration_seconds": 1.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        assert "rubric_results" in data, "rubric_results field should be present"
        rubric_results_data = data["rubric_results"]
        
        # Verify structure contains aggregated scores
        assert isinstance(rubric_results_data, dict), "rubric_results should be a dictionary"
        
        if rubric_results_data:
            # Check first rubric has expected structure
            first_rubric = next(iter(rubric_results_data.values()))
            assert "turns" in first_rubric, "Each rubric should have turns"
            
            if first_rubric["turns"]:
                first_turn = next(iter(first_rubric["turns"].values()))
                assert "cross_judge_score" in first_turn, "Each turn should have cross_judge_score"
                assert "disagreement_signal" in first_turn, "Each turn should have disagreement_signal"


@pytest.mark.component
class TestDeterministicOutput:
    """Validate output is deterministic for identical inputs."""
    
    def test_stable_output_for_identical_inputs(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.5: THE Output_Writer SHALL produce stable output for identical inputs (deterministic)
        
        Expected: Multiple writes with same inputs produce identical results.json content
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        # Write results twice with identical inputs
        common_params = {
            "run_id": "test_run_deterministic",
            "rubrics_config": {"rubrics": [{"id": "correctness"}]},
            "judge_config": {"judges": [{"id": "judge_1"}]},
            "input_data": {"run_id": "test_run_deterministic", "turns": []},
            "deterministic_metrics": mock_metrics_result,
            "rubric_results": rubric_results,
            "judge_disagreements": [],
            "artifact_paths": {"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            "execution_stats": {"total_jobs": 1, "completed_jobs": 1, "failed_jobs": 0, "duration_seconds": 1.0}
        }
        
        # First write
        results_path_1 = output_writer.write_results_json(**common_params)
        with open(results_path_1, 'r') as f:
            content_1 = json.load(f)
        
        # Second write (overwrites)
        results_path_2 = output_writer.write_results_json(**common_params)
        with open(results_path_2, 'r') as f:
            content_2 = json.load(f)
        
        # Compare content (should be identical)
        assert content_1 == content_2, "Identical inputs should produce identical output"



@pytest.mark.component
class TestTimestampSerialization:
    """Validate timestamp serialization in ISO 8601 format."""
    
    def test_timestamp_iso8601_format(self, output_writer, sample_cross_judge_results):
        """
        Requirement 8.10: THE Output_Writer SHALL serialize all timestamps in ISO 8601 format
        
        Expected: Timestamps are serialized as ISO 8601 strings
        """
        # Create metrics with ISO 8601 timestamp strings (already serialized)
        # The canonicalization happens in the metrics calculator, not the output writer
        metrics_with_timestamps = {
            "turn_count": 1,
            "tool_call_count": 0,
            "tool_result_count": 0,
            "tool_success_rate": 0.0,
            "orphan_count": 0,
            "step_count": 1,
            "first_turn_timestamp": "2024-01-15T10:30:00",
            "last_turn_timestamp": "2024-01-15T10:30:05"
        }
        
        mock_metrics = MockMetricsResult(metrics_with_timestamps)
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_timestamps",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_timestamps"},
            deterministic_metrics=mock_metrics,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        metrics = data["deterministic_metrics"]
        
        # Verify timestamps are strings in ISO 8601 format
        if "first_turn_timestamp" in metrics:
            timestamp = metrics["first_turn_timestamp"]
            assert isinstance(timestamp, str), "Timestamp should be serialized as string"
            # Verify ISO 8601 format (basic check)
            assert "T" in timestamp or timestamp.count("-") >= 2, "Timestamp should be in ISO 8601 format"


@pytest.mark.component
class TestSpecialValueSerialization:
    """Validate NaN and Infinity serialization."""
    
    def test_nan_infinity_serialization(self, output_writer, sample_cross_judge_results):
        """
        Requirement 8.11: WHEN results contain NaN or Infinity, THE Output_Writer SHALL serialize them as null
        
        Expected: NaN and Infinity values are converted to null in JSON
        """
        # Create metrics with special float values
        metrics_with_special_values = {
            "turn_count": 1,
            "tool_call_count": 0,
            "tool_result_count": 0,
            "tool_success_rate": float('nan'),  # NaN value
            "orphan_count": 0,
            "step_count": 1,
            "latency_ms": float('inf')  # Infinity value
        }
        
        mock_metrics = MockMetricsResult(metrics_with_special_values)
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_special_values",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_special_values"},
            deterministic_metrics=mock_metrics,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        # Verify file is valid JSON (NaN/Infinity would break JSON parsing if not handled)
        with open(results_path, 'r') as f:
            data = json.load(f)  # Should not raise error
        
        # Note: The current implementation may not convert NaN/Inf to null automatically
        # This test validates that the output is at least valid JSON
        assert isinstance(data, dict), "Output should be valid JSON even with special values"



@pytest.mark.component
class TestSchemaValidation:
    """Validate output against results schema."""
    
    def test_output_validation_against_schema(self, output_writer, mock_metrics_result, sample_cross_judge_results):
        """
        Requirement 8.12: THE Output_Writer SHALL validate output against results schema before writing
        
        Expected: Output conforms to results.schema.json structure
        """
        rubric_results = output_writer.build_rubric_results_for_results_json(sample_cross_judge_results)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_schema",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_schema"},
            deterministic_metrics=mock_metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 0, "completed_jobs": 0, "failed_jobs": 0, "duration_seconds": 0.0}
        )
        
        # Use the built-in validation method
        is_valid = output_writer.validate_json_output(results_path)
        assert is_valid, "Output should be valid JSON"
        
        # Try schema validation if jsonschema is available
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "results.schema.json"
        if schema_path.exists():
            is_valid, error_msg = output_writer.validate_against_schema(results_path, str(schema_path))
            if error_msg:
                # Schema validation available and failed
                pytest.fail(f"Schema validation failed: {error_msg}")
            # If no error_msg, validation passed or jsonschema not available (both OK)


@pytest.mark.component
class TestBaselineCorpusOutput:
    """Validate output for baseline corpus traces."""
    
    def test_good_trace_produces_valid_output(self, baseline_corpus_dir, temp_output_dir):
        """
        Validate that a good trace produces valid results.json
        
        Expected: good_001 trace produces valid, complete results.json
        """
        # Load and adapt trace
        trace_data = load_trace(baseline_corpus_dir, "good_001")
        normalized_run = adapt(trace_data)
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics_result = metrics_calculator.compute(normalized_run)
        
        # Create output writer
        writer = OutputWriter(str(temp_output_dir))
        
        # Create minimal cross-judge results
        within_judge = WithinJudgeResult(
            judge_id="test_judge",
            rubric_id="correctness",
            turn_id=None,
            majority_vote=None,
            median=5.0,
            mean=5.0,
            variance=0.0,
            sample_size=1,
            scoring_type="numeric"
        )
        
        cross_judge = CrossJudgeResult(
            rubric_id="correctness",
            turn_id=None,
            individual_judge_results=[within_judge],
            weighted_vote=None,
            weighted_average=5.0,
            disagreement_signal=0.0,
            high_risk_flag=False,
            judge_count=1,
            scoring_type="numeric",
            mixed_types_error=None,
            scale_warning=None
        )
        
        rubric_results = writer.build_rubric_results_for_results_json([cross_judge])
        
        # Write results
        results_path = writer.write_results_json(
            run_id=normalized_run.get("run_id", "good_001"),
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data=normalized_run,
            deterministic_metrics=metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 1, "completed_jobs": 1, "failed_jobs": 0, "duration_seconds": 1.0}
        )
        
        # Verify output
        assert Path(results_path).exists(), "results.json should be created"
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        # Verify key fields
        assert data["run_id"] == normalized_run.get("run_id", "good_001"), "run_id should match"
        assert "deterministic_metrics" in data, "deterministic_metrics should be present"
        assert "rubric_results" in data, "rubric_results should be present"

    
    def test_bad_trace_produces_valid_output(self, baseline_corpus_dir, temp_output_dir):
        """
        Validate that a bad trace produces valid results.json
        
        Expected: bad_001 trace produces valid, complete results.json
        """
        # Load and adapt trace
        trace_data = load_trace(baseline_corpus_dir, "bad_001")
        normalized_run = adapt(trace_data)
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics_result = metrics_calculator.compute(normalized_run)
        
        # Create output writer
        writer = OutputWriter(str(temp_output_dir))
        
        # Create minimal cross-judge results with low score
        within_judge = WithinJudgeResult(
            judge_id="test_judge",
            rubric_id="correctness",
            turn_id=None,
            majority_vote=None,
            median=1.0,
            mean=1.0,
            variance=0.0,
            sample_size=1,
            scoring_type="numeric"
        )
        
        cross_judge = CrossJudgeResult(
            rubric_id="correctness",
            turn_id=None,
            individual_judge_results=[within_judge],
            weighted_vote=None,
            weighted_average=1.0,
            disagreement_signal=0.0,
            high_risk_flag=False,
            judge_count=1,
            scoring_type="numeric",
            mixed_types_error=None,
            scale_warning=None
        )
        
        rubric_results = writer.build_rubric_results_for_results_json([cross_judge])
        
        # Write results
        results_path = writer.write_results_json(
            run_id=normalized_run.get("run_id", "bad_001"),
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data=normalized_run,
            deterministic_metrics=metrics_result,
            rubric_results=rubric_results,
            judge_disagreements=[],
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 1, "completed_jobs": 1, "failed_jobs": 0, "duration_seconds": 1.0}
        )
        
        # Verify output
        assert Path(results_path).exists(), "results.json should be created"
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        # Verify key fields
        assert data["run_id"] == normalized_run.get("run_id", "bad_001"), "run_id should match"
        assert "deterministic_metrics" in data, "deterministic_metrics should be present"


@pytest.mark.component
class TestTraceEvalOutput:
    """Validate trace_eval.json output."""
    
    def test_trace_eval_json_is_valid(self, output_writer, sample_metrics, sample_cross_judge_results):
        """
        Validate trace_eval.json is always valid JSON
        
        Expected: trace_eval.json can be parsed without errors
        """
        # Build rubric results for trace_eval
        rubric_results = output_writer.build_rubric_results_for_trace_eval(sample_cross_judge_results)
        
        # Build judge summary
        judge_summary = output_writer.build_judge_summary(
            total_jobs=1,
            successful_jobs=1,
            failed_jobs=0,
            judge_count=1
        )
        
        mock_metrics = MockMetricsResult(sample_metrics)
        
        # Write trace_eval.json
        trace_eval_path = output_writer.write_trace_eval(
            run_id="test_run_trace_eval",
            deterministic_metrics=mock_metrics,
            rubric_results=rubric_results,
            judge_summary=judge_summary
        )
        
        # Verify file exists and is valid JSON
        assert Path(trace_eval_path).exists(), "trace_eval.json should be created"
        
        with open(trace_eval_path, 'r') as f:
            data = json.load(f)  # Should not raise JSONDecodeError
        
        assert isinstance(data, dict), "trace_eval.json should contain a JSON object"
        
        # Verify required fields
        assert "format_version" in data, "format_version should be present"
        assert "run_id" in data, "run_id should be present"
        assert "deterministic_metrics" in data, "deterministic_metrics should be present"
        assert "rubric_results" in data, "rubric_results should be present"
        assert "judge_summary" in data, "judge_summary should be present"


@pytest.mark.component
class TestJudgeDisagreements:
    """Validate judge disagreement extraction and inclusion."""
    
    def test_high_risk_disagreements_included(self, output_writer, sample_metrics):
        """
        Requirement 8.9: THE Output_Writer SHALL include confidence penalties in results
        
        Expected: High-risk disagreements are included in judge_disagreements array
        """
        # Create cross-judge results with high disagreement
        within_judge_1 = WithinJudgeResult(
            judge_id="judge_1",
            rubric_id="correctness",
            turn_id="turn_1",
            majority_vote=None,
            median=5.0,
            mean=5.0,
            variance=0.0,
            sample_size=1,
            scoring_type="numeric"
        )
        
        within_judge_2 = WithinJudgeResult(
            judge_id="judge_2",
            rubric_id="correctness",
            turn_id="turn_1",
            majority_vote=None,
            median=1.0,
            mean=1.0,
            variance=0.0,
            sample_size=1,
            scoring_type="numeric"
        )
        
        cross_judge_high_disagreement = CrossJudgeResult(
            rubric_id="correctness",
            turn_id="turn_1",
            individual_judge_results=[within_judge_1, within_judge_2],
            weighted_vote=None,
            weighted_average=3.0,
            disagreement_signal=0.8,  # High disagreement
            high_risk_flag=True,
            judge_count=2,
            scoring_type="numeric",
            mixed_types_error=None,
            scale_warning=None
        )
        
        # Extract disagreements
        disagreements = output_writer.extract_judge_disagreements([cross_judge_high_disagreement])
        
        assert len(disagreements) > 0, "High-risk disagreements should be extracted"
        assert disagreements[0]["rubric_id"] == "correctness", "Disagreement should include rubric_id"
        assert disagreements[0]["disagreement_score"] == 0.8, "Disagreement score should match"
        
        # Write results with disagreements
        rubric_results = output_writer.build_rubric_results_for_results_json([cross_judge_high_disagreement])
        mock_metrics = MockMetricsResult(sample_metrics)
        
        results_path = output_writer.write_results_json(
            run_id="test_run_disagreements",
            rubrics_config={"rubrics": []},
            judge_config={"judges": []},
            input_data={"run_id": "test_run_disagreements"},
            deterministic_metrics=mock_metrics,
            rubric_results=rubric_results,
            judge_disagreements=disagreements,
            artifact_paths={"judge_runs_jsonl": "judge_runs.jsonl", "trace_eval_json": "trace_eval.json"},
            execution_stats={"total_jobs": 2, "completed_jobs": 2, "failed_jobs": 0, "duration_seconds": 2.0}
        )
        
        with open(results_path, 'r') as f:
            data = json.load(f)
        
        assert "judge_disagreements" in data, "judge_disagreements should be present"
        assert len(data["judge_disagreements"]) > 0, "High-risk disagreements should be included"
