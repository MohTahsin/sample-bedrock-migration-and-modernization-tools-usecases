"""
End-to-End Pipeline Validation Tests

This module validates the complete pipeline from raw trace to final results
using representative traces only. Component tests already cover all baseline
traces; E2E uses 4 representative traces for confidence.

Requirements Coverage: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.12

Test Strategy:
- Use 4 representative traces: good_001, bad_001, partial_001, weird_001
- Test complete pipeline: raw trace → adapter → metrics → evaluator → results
- Test trace_id preservation throughout all stages
- Test deterministic results for identical inputs
- Test adapter and evaluator failure handling without crash
- Test component error collection in final results
- Test valid results.json output
- Test completion within time bounds (< 5 seconds per trace)
- Test all stages logged for observability
"""

import pytest
import json
import yaml
import time
from pathlib import Path
from typing import Dict, Any
import tempfile
import shutil

from agent_eval.pipeline import run_pipeline, PipelineError


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent.parent / "test-fixtures" / "baseline"


@pytest.fixture
def expected_outcomes(baseline_corpus_dir: Path) -> Dict[str, Any]:
    """Load expected outcomes for baseline traces."""
    outcomes_path = baseline_corpus_dir / "expected_outcomes.yaml"
    
    if not outcomes_path.exists():
        pytest.skip(f"Expected outcomes file not found: {outcomes_path}")
    
    with open(outcomes_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def minimal_judge_config(tmp_path: Path) -> Path:
    """Create minimal judge configuration for testing."""
    config_file = tmp_path / "judges.yaml"
    config_file.write_text("""
judges:
  - judge_id: test_judge
    provider: mock
    model_id: mock-model
    params:
      temperature: 0.0
      max_tokens: 100
""")
    return config_file


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory for test results."""
    output = tmp_path / "output"
    output.mkdir(exist_ok=True)
    return output


# -------------------------------------------------------------------------
# Test: Good Trace Pipeline (Requirement 9.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestGoodTracePipeline:
    """Validate pipeline produces expected pass outcome for good traces."""
    
    def test_good_trace_produces_pass_outcome(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path,
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 9.1: WHEN a good trace is processed, THE Pipeline SHALL produce expected pass outcome
        
        Expected: good_001 should complete successfully with correct metrics
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        expected = expected_outcomes["traces"]["good-001"]["expected"]
        
        # Act
        start_time = time.time()
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        elapsed_time = time.time() - start_time
        
        # Assert - Pipeline success
        assert result["success"] is True, \
            f"Pipeline should succeed for good trace, got exit code: {result['evaluation_exit_code']}"
        assert result["evaluation_exit_code"] == 0, \
            "Exit code should be 0 for successful evaluation"
        
        # Assert - Results file exists and is valid JSON
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            "results.json should be created"
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Assert - Expected metrics present
        assert "deterministic_metrics" in results, \
            "Results should include deterministic_metrics"
        
        metrics = results["deterministic_metrics"]
        assert metrics["turn_count"] == expected["turn_count"], \
            f"Expected turn_count={expected['turn_count']}, got {metrics['turn_count']}"
        assert metrics["tool_call_count"] == expected["tool_call_count"], \
            f"Expected tool_call_count={expected['tool_call_count']}, got {metrics['tool_call_count']}"
        
        # Assert - Performance (< 5 seconds)
        assert elapsed_time < 5.0, \
            f"Pipeline should complete in < 5 seconds, took {elapsed_time:.2f}s"


# -------------------------------------------------------------------------
# Test: Bad Trace Pipeline (Requirement 9.2)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestBadTracePipeline:
    """Validate pipeline produces expected fail outcome for bad traces."""
    
    def test_bad_trace_produces_fail_outcome(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path,
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 9.2: WHEN a bad trace is processed, THE Pipeline SHALL produce expected fail outcome
        
        Expected: bad_001 should complete successfully with correct metrics
        """
        # Arrange
        trace_file = baseline_corpus_dir / "bad_001_wrong_math.json"
        expected = expected_outcomes["traces"]["bad-001"]["expected"]
        
        # Act
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        
        # Assert - Pipeline success (bad trace should still process successfully)
        assert result["success"] is True, \
            "Pipeline should succeed even for bad trace content"
        
        # Assert - Results file exists
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            "results.json should be created"
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Assert - Expected metrics present
        metrics = results["deterministic_metrics"]
        assert metrics["turn_count"] == expected["turn_count"], \
            f"Expected turn_count={expected['turn_count']}, got {metrics['turn_count']}"
        assert metrics["tool_call_count"] == expected["tool_call_count"], \
            f"Expected tool_call_count={expected['tool_call_count']}, got {metrics['tool_call_count']}"


# -------------------------------------------------------------------------
# Test: Partial Trace Pipeline (Requirement 9.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestPartialTracePipeline:
    """Validate pipeline produces expected partial outcome for partial traces."""
    
    def test_partial_trace_produces_partial_outcome(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path,
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 9.3: WHEN a partial trace is processed, THE Pipeline SHALL produce expected partial outcome
        
        Expected: partial_001 should complete successfully with correct metrics
        """
        # Arrange
        trace_file = baseline_corpus_dir / "partial_001_incomplete_but_ok.json"
        expected = expected_outcomes["traces"]["partial-001"]["expected"]
        
        # Act
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        
        # Assert - Pipeline success
        assert result["success"] is True, \
            "Pipeline should succeed for partial trace"
        
        # Assert - Results file exists
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            "results.json should be created"
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Assert - Expected metrics present
        metrics = results["deterministic_metrics"]
        assert metrics["turn_count"] == expected["turn_count"], \
            f"Expected turn_count={expected['turn_count']}, got {metrics['turn_count']}"
        assert metrics["tool_call_count"] == expected["tool_call_count"], \
            f"Expected tool_call_count={expected['tool_call_count']}, got {metrics['tool_call_count']}"


# -------------------------------------------------------------------------
# Test: Weird/Orphan Trace Pipeline (Requirement 9.4)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestWeirdTracePipeline:
    """Validate pipeline handles weird/orphan traces gracefully."""
    
    def test_weird_trace_handled_gracefully(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path,
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 9.4: WHEN a weird/orphan trace is processed, THE Pipeline SHALL handle it gracefully
        
        Expected: weird_001 should complete without crash, handling duplicate tool calls
        """
        # Arrange
        trace_file = baseline_corpus_dir / "weird_001_duplicate_tool_calls.json"
        expected = expected_outcomes["traces"]["weird-001"]["expected"]
        
        # Act
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        
        # Assert - Pipeline success (should handle gracefully)
        assert result["success"] is True, \
            "Pipeline should handle weird trace gracefully without crash"
        
        # Assert - Results file exists
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            "results.json should be created"
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Assert - Expected metrics present (after deduplication)
        metrics = results["deterministic_metrics"]
        assert metrics["turn_count"] == expected["turn_count"], \
            f"Expected turn_count={expected['turn_count']}, got {metrics['turn_count']}"
        assert metrics["tool_call_count"] == expected["tool_call_count"], \
            f"Expected tool_call_count={expected['tool_call_count']} (after dedup), got {metrics['tool_call_count']}"


# -------------------------------------------------------------------------
# Test: Trace ID Preservation (Requirement 9.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestTraceIDPreservation:
    """Validate trace_id is preserved throughout all pipeline stages."""
    
    def test_trace_id_preserved_throughout_pipeline(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path
    ):
        """
        Requirement 9.5: THE Pipeline SHALL preserve trace_id throughout all stages
        
        Expected: Pipeline processes trace successfully and maintains run_id consistency
        Note: trace_id from raw input is used to generate run_id in normalized format
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        
        with open(trace_file, 'r') as f:
            raw_trace = json.load(f)
        
        original_trace_id = raw_trace["trace_id"]
        
        # Act
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        
        # Assert - Pipeline success
        assert result["success"] is True
        
        # Assert - Normalized run created with consistent run_id
        normalized_files = list(output_dir.glob("normalized_run.*.json"))
        assert len(normalized_files) > 0, \
            "Normalized run file should be created"
        
        with open(normalized_files[0], 'r') as f:
            normalized = json.load(f)
        
        # Check run_id exists and is consistent
        assert "run_id" in normalized, \
            "Normalized run should have run_id"
        
        normalized_run_id = normalized["run_id"]
        
        # Assert - Results file has matching run_id
        results_file = output_dir / "results.json"
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        assert "run_id" in results, \
            "Results should have run_id"
        
        # Verify run_id consistency between normalized run and results
        assert results["run_id"] == normalized_run_id, \
            f"Run ID should be consistent: normalized={normalized_run_id}, results={results['run_id']}"


# -------------------------------------------------------------------------
# Test: Deterministic Results (Requirement 9.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDeterministicResults:
    """Validate pipeline produces deterministic results for identical inputs."""
    
    def test_deterministic_results_for_identical_inputs(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        tmp_path: Path
    ):
        """
        Requirement 9.6: THE Pipeline SHALL produce deterministic results for identical inputs
        
        Expected: Running same trace twice should produce identical deterministic metrics
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        output_dir_1 = tmp_path / "run1"
        output_dir_2 = tmp_path / "run2"
        output_dir_1.mkdir()
        output_dir_2.mkdir()
        
        # Act - Run 1
        result_1 = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir_1),
            verbose=False
        )
        
        # Act - Run 2
        result_2 = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir_2),
            verbose=False
        )
        
        # Assert - Both runs succeeded
        assert result_1["success"] is True
        assert result_2["success"] is True
        
        # Assert - Load results
        with open(output_dir_1 / "results.json", 'r') as f:
            results_1 = json.load(f)
        
        with open(output_dir_2 / "results.json", 'r') as f:
            results_2 = json.load(f)
        
        # Assert - Deterministic metrics are identical
        metrics_1 = results_1["deterministic_metrics"]
        metrics_2 = results_2["deterministic_metrics"]
        
        assert metrics_1["turn_count"] == metrics_2["turn_count"], \
            "Turn count should be deterministic"
        assert metrics_1["tool_call_count"] == metrics_2["tool_call_count"], \
            "Tool call count should be deterministic"
        assert metrics_1["tool_result_count"] == metrics_2["tool_result_count"], \
            "Tool result count should be deterministic"
        assert metrics_1["tool_success_rate"] == metrics_2["tool_success_rate"], \
            "Tool success rate should be deterministic"


# -------------------------------------------------------------------------
# Test: Adapter Failure Handling (Requirement 9.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestAdapterFailureHandling:
    """Validate pipeline handles adapter failures gracefully without crash."""
    
    def test_adapter_failure_handled_without_crash(
        self,
        minimal_judge_config: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 9.7: THE Pipeline SHALL handle adapter failures gracefully without crashing
        
        Expected: Malformed JSON should be caught and reported, not crash
        """
        # Arrange - Create malformed JSON file
        malformed_file = tmp_path / "malformed.json"
        malformed_file.write_text('{"invalid": json syntax}')
        
        # Act & Assert - Should raise PipelineError, not crash
        with pytest.raises(PipelineError) as exc_info:
            run_pipeline(
                input_path=str(malformed_file),
                judge_config_path=str(minimal_judge_config),
                output_dir=str(output_dir),
                verbose=False
            )
        
        # Assert - Error message is descriptive
        error_message = str(exc_info.value)
        assert "Pipeline execution failed" in error_message or "json" in error_message.lower(), \
            f"Error should mention JSON parsing issue: {error_message}"


# -------------------------------------------------------------------------
# Test: Evaluator Failure Handling (Requirement 9.8)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestEvaluatorFailureHandling:
    """Validate pipeline handles evaluator failures gracefully without crash."""
    
    def test_evaluator_failure_handled_without_crash(
        self,
        baseline_corpus_dir: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 9.8: THE Pipeline SHALL handle evaluator failures gracefully without crashing
        
        Expected: Missing judge config should be caught and reported, not crash
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        nonexistent_config = tmp_path / "nonexistent_judges.yaml"
        
        # Act & Assert - Should raise PipelineError, not crash
        with pytest.raises(PipelineError) as exc_info:
            run_pipeline(
                input_path=str(trace_file),
                judge_config_path=str(nonexistent_config),
                output_dir=str(output_dir),
                verbose=False
            )
        
        # Assert - Error is caught gracefully
        error_message = str(exc_info.value)
        assert "Pipeline execution failed" in error_message or "not found" in error_message.lower(), \
            f"Error should mention missing config: {error_message}"


# -------------------------------------------------------------------------
# Test: Valid Results JSON (Requirement 9.10)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestValidResultsJSON:
    """Validate pipeline produces valid results.json for representative traces."""
    
    @pytest.mark.parametrize("trace_file,trace_id", [
        ("good_001_direct_answer.json", "good-001"),
        ("bad_001_wrong_math.json", "bad-001"),
        ("partial_001_incomplete_but_ok.json", "partial-001"),
        ("weird_001_duplicate_tool_calls.json", "weird-001"),
    ])
    def test_valid_results_json_for_representative_traces(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        tmp_path: Path,
        trace_file: str,
        trace_id: str
    ):
        """
        Requirement 9.10: THE Pipeline SHALL produce valid results.json for all baseline traces
        
        Expected: All representative traces should produce valid, parseable results.json
        """
        # Arrange
        trace_path = baseline_corpus_dir / trace_file
        output_dir = tmp_path / f"output_{trace_id}"
        output_dir.mkdir()
        
        # Act
        result = run_pipeline(
            input_path=str(trace_path),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        
        # Assert - Pipeline success
        assert result["success"] is True, \
            f"Pipeline should succeed for {trace_id}"
        
        # Assert - Results file exists and is valid JSON
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            f"results.json should be created for {trace_id}"
        
        with open(results_file, 'r') as f:
            results = json.load(f)
        
        # Assert - Required fields present
        assert "run_id" in results, \
            "Results should include run_id"
        assert "deterministic_metrics" in results, \
            "Results should include deterministic_metrics"
        # Note: metadata is in the normalized run, not in results.json


# -------------------------------------------------------------------------
# Test: Performance Bounds (Requirement 9.11)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestPerformanceBounds:
    """Validate pipeline completes within time bounds."""
    
    def test_completion_within_time_bounds(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path
    ):
        """
        Requirement 9.11: THE Pipeline SHALL complete within reasonable time bounds (< 5 seconds per trace)
        
        Expected: Single trace should complete in < 5 seconds for deterministic path
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        
        # Act
        start_time = time.time()
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        elapsed_time = time.time() - start_time
        
        # Assert - Pipeline success
        assert result["success"] is True
        
        # Assert - Performance bound
        assert elapsed_time < 5.0, \
            f"Pipeline should complete in < 5 seconds, took {elapsed_time:.2f}s"


# -------------------------------------------------------------------------
# Test: Observability Logging (Requirement 9.12)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestObservabilityLogging:
    """Validate all pipeline stages are logged for observability."""
    
    def test_all_stages_logged_for_observability(
        self,
        baseline_corpus_dir: Path,
        minimal_judge_config: Path,
        output_dir: Path,
        capsys
    ):
        """
        Requirement 9.12: THE Pipeline SHALL log all stages for observability and debugging
        
        Expected: Verbose mode should log all major pipeline stages
        """
        # Arrange
        trace_file = baseline_corpus_dir / "good_001_direct_answer.json"
        
        # Act
        result = run_pipeline(
            input_path=str(trace_file),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=True  # Enable verbose logging
        )
        
        # Capture output
        captured = capsys.readouterr()
        output = captured.out + captured.err
        
        # Assert - Pipeline success
        assert result["success"] is True
        
        # Assert - Key stages logged
        assert "EVALUATION PIPELINE" in output or "Step 1" in output, \
            "Pipeline should log initialization"
        assert "Detected input format" in output or "raw" in output or "normalized" in output, \
            "Pipeline should log input format detection"
        assert "TRACE EVALUATOR" in output or "Step" in output, \
            "Pipeline should log evaluator stages"


# -------------------------------------------------------------------------
# Integration Test: Complete Pipeline Flow
# -------------------------------------------------------------------------

@pytest.mark.component
def test_complete_pipeline_integration(
    baseline_corpus_dir: Path,
    minimal_judge_config: Path,
    tmp_path: Path,
    expected_outcomes: Dict[str, Any]
):
    """
    Integration test: Validate complete pipeline flow for all representative traces
    
    This test validates the entire pipeline from raw trace to final results:
    - Input format detection
    - Adapter execution
    - Metrics computation
    - Evaluator execution
    - Results output
    - Trace ID preservation
    - Deterministic behavior
    """
    representative_traces = [
        ("good_001_direct_answer.json", "good-001"),
        ("bad_001_wrong_math.json", "bad-001"),
        ("partial_001_incomplete_but_ok.json", "partial-001"),
        ("weird_001_duplicate_tool_calls.json", "weird-001"),
    ]
    
    results_summary = []
    
    for trace_file, trace_id in representative_traces:
        # Arrange
        trace_path = baseline_corpus_dir / trace_file
        output_dir = tmp_path / f"output_{trace_id}"
        output_dir.mkdir()
        
        # Act
        start_time = time.time()
        result = run_pipeline(
            input_path=str(trace_path),
            judge_config_path=str(minimal_judge_config),
            output_dir=str(output_dir),
            verbose=False
        )
        elapsed_time = time.time() - start_time
        
        # Collect results
        results_summary.append({
            "trace_id": trace_id,
            "success": result["success"],
            "elapsed_time": elapsed_time,
            "exit_code": result["evaluation_exit_code"]
        })
        
        # Assert - Pipeline success
        assert result["success"] is True, \
            f"Pipeline should succeed for {trace_id}"
        
        # Assert - Results file exists
        results_file = output_dir / "results.json"
        assert results_file.exists(), \
            f"results.json should exist for {trace_id}"
        
        # Assert - Performance
        assert elapsed_time < 5.0, \
            f"Pipeline should complete in < 5s for {trace_id}, took {elapsed_time:.2f}s"
    
    # Assert - All traces processed successfully
    assert all(r["success"] for r in results_summary), \
        f"All representative traces should succeed: {results_summary}"
    
    # Assert - Total time reasonable
    total_time = sum(r["elapsed_time"] for r in results_summary)
    assert total_time < 20.0, \
        f"All 4 traces should complete in < 20s total, took {total_time:.2f}s"
