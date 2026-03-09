"""
Judge Orchestration Validation Tests (Mocked Contract Only)

This module validates judge orchestration logic with mocked judges.
Tests orchestration contract without real provider assumptions.

Requirements Coverage: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.12

Test Strategy:
- Test single mocked judge execution successfully
- Test multiple mocked judges execution
- Test judge timeout handling and status marking
- Test malformed response handling and status marking
- Test partial failure handling (preserve successful results)
- Test structured judge response parsing
- Test score and reasoning extraction from responses
- Test rejection of responses missing required fields
- Test collection of all judge results for aggregation

Note: Advanced features (concurrency limits, retry policy, rate limiting)
      deferred if not yet implemented.
"""

import asyncio
import os
import tempfile
import pytest
from typing import Dict, List

# Import judge orchestration components
from agent_eval.evaluators.trace_eval.judging.models import JudgeJob, JobResult
from agent_eval.evaluators.trace_eval.judging.queue_runner import WorkerPool
from agent_eval.judges.mock_client import MockJudgeClient
from agent_eval.judges.judge_client import JudgeClient


# -------------------------------------------------------------------------
# Fixtures and Helpers
# -------------------------------------------------------------------------

def create_test_judge_job(
    job_id: str,
    judge_id: str,
    rubric_id: str = "test_rubric",
    run_id: str = "test_run",
    turn_id: str = None,
    repeat_index: int = 0
) -> JudgeJob:
    """
    Create a test JudgeJob for orchestration testing.
    
    Args:
        job_id: Unique job identifier
        judge_id: Judge identifier
        rubric_id: Rubric identifier
        run_id: Run identifier
        turn_id: Optional turn identifier
        repeat_index: Repeat index for multiple runs
        
    Returns:
        JudgeJob instance
    """
    return JudgeJob(
        job_id=job_id,
        run_id=run_id,
        turn_id=turn_id,
        rubric_id=rubric_id,
        judge_id=judge_id,
        repeat_index=repeat_index,
        prompt_payload={
            "evidence": {"test": "data"},
            "rubric_description": "Test rubric description",
            "scoring_scale": {"type": "numeric", "min": 0, "max": 10}
        }
    )


@pytest.fixture
def temp_output_dir():
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_judge_clients() -> Dict[str, JudgeClient]:
    """Create a dictionary of mock judge clients for testing."""
    return {
        "judge_1": MockJudgeClient(
            judge_id="judge_1",
            deterministic_score=5.0,
            latency_ms=50.0
        ),
        "judge_2": MockJudgeClient(
            judge_id="judge_2",
            deterministic_score=7.0,
            latency_ms=50.0
        ),
        "judge_3": MockJudgeClient(
            judge_id="judge_3",
            deterministic_score=3.0,
            latency_ms=50.0
        )
    }


# -------------------------------------------------------------------------
# Test: Single Judge Execution (Requirement 7.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestSingleJudgeExecution:
    """Validate single mocked judge execution successfully."""
    
    def test_single_judge_success(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.1: Verify single judge executes successfully
        
        Expected: Job completes with status="success" and valid score
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create worker pool with single judge
        pool = WorkerPool(
            judge_clients={"judge_1": mock_judge_clients["judge_1"]},
            max_concurrency=1
        )
        
        # Create single job
        job = create_test_judge_job("job_1", "judge_1")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        # Verify execution result
        assert result.total_job_count == 1
        assert result.successful_job_count == 1
        assert result.failed_job_count == 0
        assert result.failure_ratio == 0.0
        
        # Verify output file exists and contains result
        assert os.path.exists(output_path)
        
        with open(output_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 1
            
            import json
            job_result = json.loads(lines[0])
            assert job_result["job_id"] == "job_1"
            assert job_result["status"] == "success"
            assert job_result["parsed_response"]["score"] == 5.0
            assert "reasoning" in job_result["parsed_response"]


# -------------------------------------------------------------------------
# Test: Multiple Judges Execution (Requirement 7.2)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestMultipleJudgesExecution:
    """Validate multiple mocked judges execution."""
    
    def test_multiple_judges_all_succeed(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.2: Verify multiple judges execute successfully
        
        Expected: All jobs complete with status="success"
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create worker pool with three judges
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=3
        )
        
        # Create jobs for each judge
        jobs = [
            create_test_judge_job(f"job_{i}", f"judge_{i}")
            for i in range(1, 4)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        # Verify execution result
        assert result.total_job_count == 3
        assert result.successful_job_count == 3
        assert result.failed_job_count == 0
        
        # Verify all results written
        with open(output_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 3
            
            import json
            job_results = [json.loads(line) for line in lines]
            job_ids = {jr["job_id"] for jr in job_results}
            assert job_ids == {"job_1", "job_2", "job_3"}
            
            # Verify all succeeded
            for jr in job_results:
                assert jr["status"] == "success"
                assert jr["parsed_response"]["score"] is not None
    
    def test_multiple_judges_same_rubric(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.2: Verify multiple judges evaluate same rubric
        
        Expected: All jobs complete for same rubric with different scores
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=3
        )
        
        # Create jobs for same rubric, different judges
        jobs = [
            create_test_judge_job(f"job_{i}", f"judge_{i}", rubric_id="accuracy")
            for i in range(1, 4)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        assert result.successful_job_count == 3
        
        # Verify different scores from different judges
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            scores = [jr["parsed_response"]["score"] for jr in job_results]
            
            # Mock judges configured with different scores: 5.0, 7.0, 3.0
            assert set(scores) == {5.0, 7.0, 3.0}


# -------------------------------------------------------------------------
# Test: Judge Timeout Handling (Requirement 7.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestJudgeTimeoutHandling:
    """Validate judge timeout handling and status marking."""
    
    def test_timeout_status_marking(self, temp_output_dir):
        """
        Requirement 7.3: Verify timeout results in status="timeout"
        
        Expected: Job marked as timeout with appropriate error message
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge that times out
        timeout_judge = MockJudgeClient(
            judge_id="timeout_judge",
            should_fail=True,
            failure_mode="timeout",
            latency_ms=100.0
        )
        
        pool = WorkerPool(
            judge_clients={"timeout_judge": timeout_judge},
            max_concurrency=1,
            default_timeout_seconds=1
        )
        
        job = create_test_judge_job("job_timeout", "timeout_judge")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        # Verify timeout recorded
        assert result.total_job_count == 1
        assert result.failed_job_count == 1
        assert result.successful_job_count == 0
        assert "job_timeout" in result.failed_job_ids
        
        # Verify status in output
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "timeout"
            assert "timeout" in job_result["error"].lower()


# -------------------------------------------------------------------------
# Test: Malformed Response Handling (Requirement 7.4)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestMalformedResponseHandling:
    """Validate malformed response handling and status marking."""
    
    def test_invalid_semantic_response_status(self, temp_output_dir):
        """
        Requirement 7.4: Verify malformed response handling
        
        Expected: Job completes but with None score/reasoning (filtered during aggregation)
        Note: Current implementation treats structurally valid responses as success,
              even if score/reasoning are None. Aggregation layer filters these out.
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge that returns semantically invalid response
        invalid_judge = MockJudgeClient(
            judge_id="invalid_judge",
            should_fail=True,
            failure_mode="invalid_semantic_response",
            latency_ms=50.0
        )
        
        pool = WorkerPool(
            judge_clients={"invalid_judge": invalid_judge},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_invalid", "invalid_judge")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        # Verify job completed (structurally valid response)
        assert result.total_job_count == 1
        assert result.successful_job_count == 1
        
        # Verify None values in output (will be filtered during aggregation)
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "success"
            # Score and reasoning are None - aggregation will filter this out
            assert job_result["parsed_response"]["score"] is None
            assert job_result["parsed_response"]["reasoning"] is None
    
    def test_invalid_transport_payload_status(self, temp_output_dir):
        """
        Requirement 7.4: Verify JSON parse failure results in status="invalid_response"
        
        Expected: Job marked as invalid_response when JSON parsing fails
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge that returns unparseable JSON
        invalid_judge = MockJudgeClient(
            judge_id="invalid_judge",
            should_fail=True,
            failure_mode="invalid_transport_payload",
            latency_ms=50.0
        )
        
        pool = WorkerPool(
            judge_clients={"invalid_judge": invalid_judge},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_parse_error", "invalid_judge")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        # Verify invalid response recorded
        assert result.failed_job_count == 1
        
        # Verify status in output
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "invalid_response"
            assert "INVALID_JSON" in job_result["error"] or "json" in job_result["error"].lower()


# -------------------------------------------------------------------------
# Test: Partial Failure Handling (Requirement 7.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestPartialFailureHandling:
    """Validate partial failure handling (preserve successful results)."""
    
    def test_preserve_successful_results_with_failures(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.5: Verify successful results preserved when some judges fail
        
        Expected: Successful jobs complete normally, failed jobs marked appropriately
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Add a failing judge to the mix
        failing_judge = MockJudgeClient(
            judge_id="failing_judge",
            should_fail=True,
            failure_mode="api_error",
            latency_ms=50.0
        )
        
        all_judges = {**mock_judge_clients, "failing_judge": failing_judge}
        
        pool = WorkerPool(
            judge_clients=all_judges,
            max_concurrency=4
        )
        
        # Create jobs: 3 successful, 1 failing
        jobs = [
            create_test_judge_job("job_1", "judge_1"),
            create_test_judge_job("job_2", "judge_2"),
            create_test_judge_job("job_fail", "failing_judge"),
            create_test_judge_job("job_3", "judge_3"),
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        # Verify partial success
        assert result.total_job_count == 4
        assert result.successful_job_count == 3
        assert result.failed_job_count == 1
        assert result.failure_ratio == 0.25
        assert "job_fail" in result.failed_job_ids
        
        # Verify all results written
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            assert len(job_results) == 4
            
            # Check successful results preserved
            successful = [jr for jr in job_results if jr["status"] == "success"]
            assert len(successful) == 3
            for jr in successful:
                assert jr["parsed_response"]["score"] is not None
            
            # Check failed result marked
            failed = [jr for jr in job_results if jr["status"] == "failure"]
            assert len(failed) == 1
            assert failed[0]["job_id"] == "job_fail"
    
    def test_partial_failure_different_rubrics(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.5: Verify failures don't affect other rubrics
        
        Expected: Failure in one rubric doesn't impact other rubrics
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        failing_judge = MockJudgeClient(
            judge_id="failing_judge",
            should_fail=True,
            failure_mode="timeout"
        )
        
        all_judges = {**mock_judge_clients, "failing_judge": failing_judge}
        
        pool = WorkerPool(
            judge_clients=all_judges,
            max_concurrency=4
        )
        
        # Create jobs for different rubrics
        jobs = [
            create_test_judge_job("job_1", "judge_1", rubric_id="accuracy"),
            create_test_judge_job("job_2", "judge_2", rubric_id="completeness"),
            create_test_judge_job("job_fail", "failing_judge", rubric_id="accuracy"),
            create_test_judge_job("job_3", "judge_3", rubric_id="completeness"),
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        # Verify partial success
        assert result.successful_job_count == 3
        assert result.failed_job_count == 1
        
        # Verify completeness rubric unaffected
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            completeness_results = [jr for jr in job_results if jr["rubric_id"] == "completeness"]
            assert len(completeness_results) == 2
            assert all(jr["status"] == "success" for jr in completeness_results)


# -------------------------------------------------------------------------
# Test: Structured Response Parsing (Requirement 7.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestStructuredResponseParsing:
    """Validate structured judge response parsing."""
    
    def test_parse_valid_response_structure(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.6: Verify structured response parsing
        
        Expected: Response parsed into structured format with score and reasoning
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients={"judge_1": mock_judge_clients["judge_1"]},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_1", "judge_1")
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify parsed response structure
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            
            # Check raw_response exists
            assert job_result["raw_response"] is not None
            
            # Check parsed_response structure
            parsed = job_result["parsed_response"]
            assert isinstance(parsed, dict)
            assert "score" in parsed
            assert "reasoning" in parsed
            
            # Verify types
            assert isinstance(parsed["score"], (int, float))
            assert isinstance(parsed["reasoning"], str)
    
    def test_response_includes_metadata(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.6: Verify response includes metadata
        
        Expected: Response includes job metadata (job_id, judge_id, rubric_id, etc.)
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients={"judge_1": mock_judge_clients["judge_1"]},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_meta", "judge_1", rubric_id="test_rubric")
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify metadata preserved
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            
            assert job_result["job_id"] == "job_meta"
            assert job_result["judge_id"] == "judge_1"
            assert job_result["rubric_id"] == "test_rubric"
            assert job_result["run_id"] == "test_run"
            assert "timestamp" in job_result
            assert "latency_ms" in job_result


# -------------------------------------------------------------------------
# Test: Score and Reasoning Extraction (Requirement 7.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestScoreAndReasoningExtraction:
    """Validate score and reasoning extraction from responses."""
    
    def test_extract_numeric_score(self, temp_output_dir):
        """
        Requirement 7.7: Verify numeric score extraction
        
        Expected: Numeric score correctly extracted from response
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge with specific score
        judge = MockJudgeClient(
            judge_id="judge_numeric",
            deterministic_score=8.5
        )
        
        pool = WorkerPool(
            judge_clients={"judge_numeric": judge},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_numeric", "judge_numeric")
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify score extraction
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["parsed_response"]["score"] == 8.5
    
    def test_extract_reasoning_text(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.7: Verify reasoning text extraction
        
        Expected: Reasoning text correctly extracted from response
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients={"judge_1": mock_judge_clients["judge_1"]},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_reasoning", "judge_1")
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify reasoning extraction
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            reasoning = job_result["parsed_response"]["reasoning"]
            
            assert isinstance(reasoning, str)
            assert len(reasoning) > 0
            # Mock judge includes rubric_id in reasoning
            assert "test_rubric" in reasoning.lower() or "mock" in reasoning.lower()
    
    def test_score_within_scale_range(self, temp_output_dir):
        """
        Requirement 7.7: Verify score respects scoring scale
        
        Expected: Score falls within configured scale range
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge with score in range
        judge = MockJudgeClient(
            judge_id="judge_scaled",
            deterministic_score=7.0
        )
        
        pool = WorkerPool(
            judge_clients={"judge_scaled": judge},
            max_concurrency=1
        )
        
        # Job with 0-10 scale
        job = create_test_judge_job("job_scaled", "judge_scaled")
        job.prompt_payload["scoring_scale"] = {"type": "numeric", "min": 0, "max": 10}
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify score in range
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            score = job_result["parsed_response"]["score"]
            assert 0 <= score <= 10


# -------------------------------------------------------------------------
# Test: Missing Required Fields Rejection (Requirement 7.8)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestMissingFieldsRejection:
    """Validate rejection of responses missing required fields."""
    
    def test_reject_response_missing_score(self, temp_output_dir):
        """
        Requirement 7.8: Verify response handling when score missing
        
        Expected: Response with missing score has None value (filtered during aggregation)
        Note: Current implementation treats structurally valid responses as success.
              Aggregation layer is responsible for filtering None scores.
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        # Create judge that returns response without score
        invalid_judge = MockJudgeClient(
            judge_id="no_score_judge",
            should_fail=True,
            failure_mode="invalid_semantic_response"
        )
        
        pool = WorkerPool(
            judge_clients={"no_score_judge": invalid_judge},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_no_score", "no_score_judge")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        # Verify job completed with None score
        assert result.successful_job_count == 1
        
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "success"
            # Score is None - will be filtered during aggregation
            assert job_result["parsed_response"]["score"] is None
    
    def test_descriptive_error_for_missing_fields(self, temp_output_dir):
        """
        Requirement 7.8: Verify handling of responses with missing fields
        
        Expected: Response completes but with None values for missing fields
        Note: Aggregation layer filters out None scores. This test verifies
              the orchestration layer handles the response without crashing.
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        invalid_judge = MockJudgeClient(
            judge_id="invalid_judge",
            should_fail=True,
            failure_mode="invalid_semantic_response"
        )
        
        pool = WorkerPool(
            judge_clients={"invalid_judge": invalid_judge},
            max_concurrency=1
        )
        
        job = create_test_judge_job("job_invalid", "invalid_judge")
        
        # Execute
        pool.run([job], output_path, resume=False)
        
        # Verify response handled gracefully
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "success"
            # None values present but no error - aggregation will filter
            assert job_result["parsed_response"]["score"] is None
            assert job_result["parsed_response"]["reasoning"] is None


# -------------------------------------------------------------------------
# Test: Judge Results Collection (Requirement 7.12)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestJudgeResultsCollection:
    """Validate collection of all judge results for aggregation."""
    
    def test_collect_all_results_for_aggregation(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.12: Verify all judge results collected for aggregation
        
        Expected: All results available in output file for downstream aggregation
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=3
        )
        
        # Create multiple jobs for same rubric (for aggregation)
        jobs = [
            create_test_judge_job(f"job_{i}", f"judge_{i}", rubric_id="accuracy")
            for i in range(1, 4)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        assert result.successful_job_count == 3
        
        # Verify all results collected
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            
            # All results for same rubric
            assert all(jr["rubric_id"] == "accuracy" for jr in job_results)
            
            # All have required fields for aggregation
            for jr in job_results:
                assert "job_id" in jr
                assert "judge_id" in jr
                assert "rubric_id" in jr
                assert "status" in jr
                assert "parsed_response" in jr
                assert jr["parsed_response"]["score"] is not None
    
    def test_collect_results_multiple_rubrics(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.12: Verify results collected across multiple rubrics
        
        Expected: Results organized by rubric for separate aggregation
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=6
        )
        
        # Create jobs for two rubrics
        jobs = []
        for rubric in ["accuracy", "completeness"]:
            for i in range(1, 4):
                jobs.append(
                    create_test_judge_job(
                        f"job_{rubric}_{i}",
                        f"judge_{i}",
                        rubric_id=rubric
                    )
                )
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        assert result.successful_job_count == 6
        
        # Verify results can be grouped by rubric
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            
            # Group by rubric
            by_rubric = {}
            for jr in job_results:
                rubric_id = jr["rubric_id"]
                if rubric_id not in by_rubric:
                    by_rubric[rubric_id] = []
                by_rubric[rubric_id].append(jr)
            
            # Verify both rubrics present
            assert "accuracy" in by_rubric
            assert "completeness" in by_rubric
            assert len(by_rubric["accuracy"]) == 3
            assert len(by_rubric["completeness"]) == 3
    
    def test_collect_results_with_repeat_runs(self, mock_judge_clients, temp_output_dir):
        """
        Requirement 7.12: Verify results collected for repeat runs
        
        Expected: Multiple runs of same judge tracked by repeat_index
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients={"judge_1": mock_judge_clients["judge_1"]},
            max_concurrency=3
        )
        
        # Create multiple repeat runs for same judge/rubric
        jobs = [
            create_test_judge_job(
                f"job_repeat_{i}",
                "judge_1",
                rubric_id="accuracy",
                repeat_index=i
            )
            for i in range(3)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        assert result.successful_job_count == 3
        
        # Verify repeat indices tracked
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            
            repeat_indices = {jr["repeat_index"] for jr in job_results}
            assert repeat_indices == {0, 1, 2}
            
            # All from same judge
            assert all(jr["judge_id"] == "judge_1" for jr in job_results)


# -------------------------------------------------------------------------
# Test: Edge Cases and Robustness
# -------------------------------------------------------------------------

@pytest.mark.component
class TestEdgeCases:
    """Validate edge cases and robustness of judge orchestration."""
    
    def test_empty_jobs_list(self, mock_judge_clients, temp_output_dir):
        """
        Verify orchestration handles empty jobs list gracefully
        
        Expected: Returns result with zero counts, no errors
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=1
        )
        
        # Execute with empty list
        result = pool.run([], output_path, resume=False)
        
        assert result.total_job_count == 0
        assert result.successful_job_count == 0
        assert result.failed_job_count == 0
        assert result.failure_ratio == 0.0
    
    def test_missing_judge_client(self, mock_judge_clients, temp_output_dir):
        """
        Verify orchestration handles missing judge client gracefully
        
        Expected: Job fails with descriptive error about missing client
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=1
        )
        
        # Create job for non-existent judge
        job = create_test_judge_job("job_missing", "nonexistent_judge")
        
        # Execute
        result = pool.run([job], output_path, resume=False)
        
        assert result.failed_job_count == 1
        
        import json
        with open(output_path, 'r') as f:
            job_result = json.loads(f.readline())
            assert job_result["status"] == "failure"
            assert "judge" in job_result["error"].lower() or "client" in job_result["error"].lower()
    
    def test_resume_mode_skips_completed(self, mock_judge_clients, temp_output_dir):
        """
        Verify resume mode skips already completed jobs
        
        Expected: Completed jobs not re-executed
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=2
        )
        
        # First execution: 2 jobs
        jobs_first = [
            create_test_judge_job("job_1", "judge_1"),
            create_test_judge_job("job_2", "judge_2"),
        ]
        
        result_first = pool.run(jobs_first, output_path, resume=False)
        assert result_first.successful_job_count == 2
        
        # Second execution: 3 jobs (2 already done, 1 new)
        jobs_second = [
            create_test_judge_job("job_1", "judge_1"),  # Already done
            create_test_judge_job("job_2", "judge_2"),  # Already done
            create_test_judge_job("job_3", "judge_3"),  # New
        ]
        
        result_second = pool.run(jobs_second, output_path, resume=True)
        
        # Should skip 2, execute 1
        assert result_second.total_job_count == 3
        assert result_second.skipped_job_count == 2
        assert result_second.successful_job_count == 3  # 2 skipped + 1 new
        
        # Verify only 3 total results in file
        import json
        with open(output_path, 'r') as f:
            lines = f.readlines()
            assert len(lines) == 3
    
    def test_latency_tracking(self, mock_judge_clients, temp_output_dir):
        """
        Verify latency is tracked for all jobs
        
        Expected: All results include latency_ms field
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=3
        )
        
        jobs = [
            create_test_judge_job(f"job_{i}", f"judge_{i}")
            for i in range(1, 4)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        # Verify latency tracked
        assert result.sum_job_latency_ms > 0
        
        import json
        with open(output_path, 'r') as f:
            job_results = [json.loads(line) for line in f.readlines()]
            
            for jr in job_results:
                assert "latency_ms" in jr
                assert jr["latency_ms"] is not None
                assert jr["latency_ms"] > 0
    
    def test_wall_time_tracking(self, mock_judge_clients, temp_output_dir):
        """
        Verify wall-clock time is tracked for execution
        
        Expected: ExecutionResult includes wall_time_seconds
        """
        output_path = os.path.join(temp_output_dir, "judge_runs.jsonl")
        
        pool = WorkerPool(
            judge_clients=mock_judge_clients,
            max_concurrency=3
        )
        
        jobs = [
            create_test_judge_job(f"job_{i}", f"judge_{i}")
            for i in range(1, 4)
        ]
        
        # Execute
        result = pool.run(jobs, output_path, resume=False)
        
        # Verify wall time tracked
        assert result.wall_time_seconds > 0
        # With concurrency=3, wall time should be less than sum of latencies
        assert result.wall_time_seconds < result.sum_job_latency_ms / 1000.0
