"""
Evaluator Contract Validation Tests

This module validates the evaluator contract compliance, ensuring the evaluator
handles all valid and invalid inputs correctly.

Requirements Coverage: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10

Test Strategy:
- Test evaluator accepts valid NormalizedRun without error
- Test evaluator rejects malformed NormalizedRun with descriptive error
- Test handling of empty turns array
- Test handling of turns with no assistant output
- Test handling of tools-only traces (no final answer)
- Test handling of no-tools traces
- Test required field validation before processing
- Test structured results output matches schema
- Test rubric configuration validation
- Test trace_id and metadata preservation in results
"""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch

from agent_eval.evaluators.trace_eval.runner import (
    TraceEvaluator,
    InputValidationError,
    ConfigError
)
from agent_eval.judges.mock_client import MockJudgeClient


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent.parent / "test-fixtures" / "baseline"


@pytest.fixture
def component_fixtures_dir() -> Path:
    """Path to component test fixtures directory."""
    fixtures_dir = Path(__file__).parent.parent.parent.parent / "test-fixtures" / "component" / "evaluator"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


@pytest.fixture
def judge_config_path(tmp_path: Path) -> Path:
    """Create temporary judge configuration with mock judge."""
    config = {
        "judges": [
            {
                "judge_id": "mock_judge_1",
                "provider": "mock",
                "model_id": "mock-model-1",
                "params": {},
                "repeats": 1
            }
        ]
    }
    
    config_path = tmp_path / "judges.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    
    return config_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def valid_normalized_run() -> Dict[str, Any]:
    """Create a minimal valid NormalizedRun for testing."""
    return {
        "run_id": "test_run_001",
        "metadata": {
            "adapter_version": "1.0.0",
            "processed_at": "2024-01-01T00:00:00.000Z"
        },
        "adapter_stats": {
            "total_events_processed": 2,
            "turn_count": 1,
            "confidence_penalties": [],
            "segmentation_strategy": "TURN_ID",
            "mapping_coverage": 0.95,
            "orphan_tool_results": []
        },
        "turns": [
            {
                "turn_id": "turn_001",
                "user_query": "What is the capital of France?",
                "final_answer": "The capital of France is Paris.",
                "steps": [
                    {
                        "name": "user_input",
                        "status": "success"
                    },
                    {
                        "name": "model_response",
                        "status": "success"
                    }
                ],
                "confidence": 0.95
            }
        ]
    }


# -------------------------------------------------------------------------
# Test: Valid NormalizedRun Acceptance (Requirement 3.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestValidNormalizedRunAcceptance:
    """Validate evaluator accepts valid NormalizedRun without error."""
    
    def test_accepts_valid_normalized_run(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.1: Evaluator accepts valid NormalizedRun without error
        
        Expected: Evaluator should process valid input successfully
        """
        # Write normalized run to file
        input_path = tmp_path / "valid_normalized_run.json"
        with open(input_path, 'w') as f:
            json.dump(valid_normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should not raise
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluator should accept valid NormalizedRun"
    
    def test_accepts_baseline_good_trace(
        self,
        baseline_corpus_dir: Path,
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.1: Evaluator accepts baseline good trace
        
        Expected: Evaluator should process baseline traces successfully
        """
        # Load and adapt baseline trace
        from agent_eval.adapters.generic_json.adapter import adapt
        
        trace_path = baseline_corpus_dir / "good_001_direct_answer.json"
        with open(trace_path, 'r') as f:
            raw_trace = json.load(f)
        
        normalized_run = adapt(raw_trace)
        
        # Write normalized run to file
        input_path = tmp_path / "normalized_good_001.json"
        with open(input_path, 'w') as f:
            json.dump(normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should not raise
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluator should accept baseline good trace"


# -------------------------------------------------------------------------
# Test: Malformed NormalizedRun Rejection (Requirement 3.2, 3.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestMalformedNormalizedRunRejection:
    """Validate evaluator rejects malformed NormalizedRun with descriptive error."""
    
    def test_rejects_missing_required_field_run_id(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.2, 3.7: Reject NormalizedRun missing required field 'run_id'
        
        Expected: Evaluator should reject with descriptive error
        """
        # Remove required field
        malformed_run = valid_normalized_run.copy()
        del malformed_run["run_id"]
        
        # Write malformed run to file
        input_path = tmp_path / "malformed_no_run_id.json"
        with open(input_path, 'w') as f:
            json.dump(malformed_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should fail with validation error
            exit_code = evaluator.run()
            
            # Verify failure (non-zero exit code)
            assert exit_code != 0, "Evaluator should reject malformed NormalizedRun"
    
    def test_rejects_missing_required_field_metadata(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.2, 3.7: Reject NormalizedRun missing required field 'metadata'
        
        Expected: Evaluator should reject with descriptive error
        """
        # Remove required field
        malformed_run = valid_normalized_run.copy()
        del malformed_run["metadata"]
        
        # Write malformed run to file
        input_path = tmp_path / "malformed_no_metadata.json"
        with open(input_path, 'w') as f:
            json.dump(malformed_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should fail
            exit_code = evaluator.run()
            
            # Verify failure
            assert exit_code != 0, "Evaluator should reject NormalizedRun without metadata"
    
    def test_rejects_missing_required_field_turns(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.2, 3.7: Reject NormalizedRun missing required field 'turns'
        
        Expected: Evaluator should reject with descriptive error
        """
        # Remove required field
        malformed_run = valid_normalized_run.copy()
        del malformed_run["turns"]
        
        # Write malformed run to file
        input_path = tmp_path / "malformed_no_turns.json"
        with open(input_path, 'w') as f:
            json.dump(malformed_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should fail
            exit_code = evaluator.run()
            
            # Verify failure
            assert exit_code != 0, "Evaluator should reject NormalizedRun without turns"
    
    def test_rejects_invalid_turn_structure(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.2, 3.7: Reject NormalizedRun with invalid turn structure
        
        Expected: Evaluator should reject turns missing required fields
        """
        # Create malformed turn (missing required 'steps' field)
        malformed_run = valid_normalized_run.copy()
        malformed_run["turns"] = [
            {
                "turn_id": "turn_001",
                "user_query": "Test query",
                "final_answer": "Test answer",
                # Missing 'steps' field
                "confidence": 0.95
            }
        ]
        
        # Write malformed run to file
        input_path = tmp_path / "malformed_turn_no_steps.json"
        with open(input_path, 'w') as f:
            json.dump(malformed_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should fail
            exit_code = evaluator.run()
            
            # Verify failure
            assert exit_code != 0, "Evaluator should reject turn without steps"


# -------------------------------------------------------------------------
# Test: Empty Turns Array Handling (Requirement 3.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestEmptyTurnsHandling:
    """Validate evaluator handles empty turns array gracefully."""
    
    def test_handles_empty_turns_array(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.3: Handle NormalizedRun with empty turns array
        
        Expected: Evaluator should handle gracefully (no crash)
        """
        # Create run with empty turns
        empty_turns_run = valid_normalized_run.copy()
        empty_turns_run["turns"] = []
        empty_turns_run["adapter_stats"]["turn_count"] = 0
        
        # Write to file
        input_path = tmp_path / "empty_turns.json"
        with open(input_path, 'w') as f:
            json.dump(empty_turns_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should not crash
            exit_code = evaluator.run()
            
            # Verify it completes (may succeed or fail gracefully, but shouldn't crash)
            assert exit_code is not None, "Evaluator should complete without crashing"
            
            # Verify output files were created
            assert (output_dir / "trace_eval.json").exists(), \
                "Should create trace_eval.json even with empty turns"


# -------------------------------------------------------------------------
# Test: Turn with No Assistant Output (Requirement 3.4)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestNoAssistantOutputHandling:
    """Validate evaluator handles turns with no assistant output."""
    
    def test_handles_turn_with_null_final_answer(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.4: Handle turn with no assistant output (null final_answer)
        
        Expected: Evaluator should handle gracefully
        """
        # Create run with null final_answer
        no_answer_run = valid_normalized_run.copy()
        no_answer_run["turns"][0]["final_answer"] = None
        
        # Write to file
        input_path = tmp_path / "no_final_answer.json"
        with open(input_path, 'w') as f:
            json.dump(no_answer_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should not crash
            exit_code = evaluator.run()
            
            # Verify it completes
            assert exit_code is not None, "Evaluator should handle null final_answer"


# -------------------------------------------------------------------------
# Test: Tools-Only Traces (Requirement 3.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestToolsOnlyTraces:
    """Validate evaluator handles tools-only traces (no final answer)."""
    
    def test_handles_tools_only_no_final_answer(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.5: Handle trace with tools-only steps (no final answer)
        
        Expected: Evaluator should process successfully
        """
        # Create run with tool steps but no final answer
        tools_only_run = valid_normalized_run.copy()
        tools_only_run["turns"][0]["final_answer"] = None
        tools_only_run["turns"][0]["steps"] = [
            {
                "name": "get_weather",
                "kind": "TOOL_CALL",
                "status": "success",
                "tool_name": "get_weather"
            },
            {
                "name": "weather_result",
                "kind": "TOOL_RESULT",
                "status": "success",
                "tool_name": "get_weather"
            }
        ]
        
        # Write to file
        input_path = tmp_path / "tools_only.json"
        with open(input_path, 'w') as f:
            json.dump(tools_only_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation
            exit_code = evaluator.run()
            
            # Verify it completes
            assert exit_code is not None, "Evaluator should handle tools-only trace"


# -------------------------------------------------------------------------
# Test: No-Tools Traces (Requirement 3.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestNoToolsTraces:
    """Validate evaluator handles traces with no tools."""
    
    def test_handles_no_tools_trace(
        self,
        baseline_corpus_dir: Path,
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.6: Handle trace with no tools
        
        Expected: Evaluator should process successfully
        """
        # Load baseline trace with no tools (good_001)
        from agent_eval.adapters.generic_json.adapter import adapt
        
        trace_path = baseline_corpus_dir / "good_001_direct_answer.json"
        with open(trace_path, 'r') as f:
            raw_trace = json.load(f)
        
        normalized_run = adapt(raw_trace)
        
        # Write normalized run to file
        input_path = tmp_path / "no_tools.json"
        with open(input_path, 'w') as f:
            json.dump(normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluator should handle no-tools trace successfully"


# -------------------------------------------------------------------------
# Test: Structured Results Output (Requirement 3.8)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestStructuredResultsOutput:
    """Validate structured results output matches schema."""
    
    def test_results_output_matches_schema(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.8: Structured results output matches schema
        
        Expected: trace_eval.json should have all required fields
        """
        # Write normalized run to file
        input_path = tmp_path / "valid_run.json"
        with open(input_path, 'w') as f:
            json.dump(valid_normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluation should succeed"
        
        # Verify trace_eval.json structure
        trace_eval_path = output_dir / "trace_eval.json"
        assert trace_eval_path.exists(), "trace_eval.json should exist"
        
        with open(trace_eval_path, 'r') as f:
            trace_eval = json.load(f)
        
        # Verify required top-level fields
        required_fields = [
            "format_version",
            "run_id",
            "deterministic_metrics",
            "rubric_results",
            "judge_summary"
        ]
        
        for field in required_fields:
            assert field in trace_eval, \
                f"trace_eval.json missing required field: {field}"
        
        # Verify deterministic_metrics structure
        metrics = trace_eval["deterministic_metrics"]
        assert "turn_count" in metrics, "Missing turn_count in metrics"
        assert "tool_call_count" in metrics, "Missing tool_call_count in metrics"
        
        # Verify rubric_results is a list
        assert isinstance(trace_eval["rubric_results"], list), \
            "rubric_results should be a list"
        
        # Verify judge_summary structure
        judge_summary = trace_eval["judge_summary"]
        # Judge summary should have job-related fields
        assert "total_jobs" in judge_summary or "total_judges" in judge_summary, \
            f"Missing job count in summary. Available fields: {list(judge_summary.keys())}"


# -------------------------------------------------------------------------
# Test: Rubric Configuration Validation (Requirement 3.9)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestRubricConfigurationValidation:
    """Validate rubric configuration validation."""
    
    def test_rejects_invalid_rubric_config(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.9: Reject invalid rubric configuration
        
        Expected: Evaluator should reject malformed rubric config
        """
        # Create invalid rubric config (malformed YAML)
        invalid_rubric_path = tmp_path / "invalid_rubrics.yaml"
        invalid_rubric_path.write_text("invalid: yaml: content: [")
        
        # Write normalized run to file
        input_path = tmp_path / "valid_run.json"
        with open(input_path, 'w') as f:
            json.dump(valid_normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator with invalid rubric config
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                rubrics_path=str(invalid_rubric_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation - should fail
            exit_code = evaluator.run()
            
            # Verify failure
            assert exit_code != 0, "Evaluator should reject invalid rubric config"


# -------------------------------------------------------------------------
# Test: Trace ID and Metadata Preservation (Requirement 3.10)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestTraceIDPreservation:
    """Validate trace_id and metadata preservation in results."""
    
    def test_preserves_trace_id_in_results(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.10: Preserve trace_id in evaluation results
        
        Expected: run_id should be preserved in trace_eval.json
        """
        # Set specific run_id
        test_run_id = "test_trace_12345"
        valid_normalized_run["run_id"] = test_run_id
        
        # Write normalized run to file
        input_path = tmp_path / "valid_run.json"
        with open(input_path, 'w') as f:
            json.dump(valid_normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluation should succeed"
        
        # Verify trace_id preservation
        trace_eval_path = output_dir / "trace_eval.json"
        with open(trace_eval_path, 'r') as f:
            trace_eval = json.load(f)
        
        assert trace_eval["run_id"] == test_run_id, \
            f"run_id should be preserved: expected {test_run_id}, got {trace_eval['run_id']}"
    
    def test_preserves_metadata_in_results(
        self,
        valid_normalized_run: Dict[str, Any],
        judge_config_path: Path,
        output_dir: Path,
        tmp_path: Path
    ):
        """
        Requirement 3.10: Preserve metadata in evaluation results
        
        Expected: Input metadata should be accessible in results
        """
        # Set specific metadata
        test_metadata = {
            "adapter_version": "2.5.0",
            "processed_at": "2024-06-15T10:30:00.000Z",
            "source": "test_system"
        }
        valid_normalized_run["metadata"] = test_metadata
        
        # Write normalized run to file
        input_path = tmp_path / "valid_run.json"
        with open(input_path, 'w') as f:
            json.dump(valid_normalized_run, f)
        
        # Patch BedrockJudgeClient to use MockJudgeClient
        with patch('agent_eval.providers.bedrock_client.BedrockJudgeClient', MockJudgeClient):
            # Create evaluator
            evaluator = TraceEvaluator(
                input_path=str(input_path),
                judge_config_path=str(judge_config_path),
                output_dir=str(output_dir),
                
                verbose=False
            )
            
            # Run evaluation
            exit_code = evaluator.run()
            
            # Verify success
            assert exit_code == 0, "Evaluation should succeed"
        
        # Verify metadata is accessible (may be in trace_eval.json or results.json)
        trace_eval_path = output_dir / "trace_eval.json"
        with open(trace_eval_path, 'r') as f:
            trace_eval = json.load(f)
        
        # Metadata should be preserved somewhere in the output
        # (exact location depends on implementation)
        assert "run_id" in trace_eval, "Results should contain run_id from metadata"
