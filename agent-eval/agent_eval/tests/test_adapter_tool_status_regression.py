"""
Regression exploration tests for adapter tool status bugs.

These tests validate the tool status inference and failed tool detection bugs
identified in the adapter-stage-bc-correctness bugfix spec.

CRITICAL: These tests are EXPECTED TO FAIL on unfixed code.
Failure confirms the bugs exist. DO NOT fix the test or code when it fails.

Bug Conditions:
1. Tool calls with linked successful results show status="unknown" instead of "success"
2. Tool calls with linked failed results show status="unknown" instead of "error"
3. tool_success_rate is calculated incorrectly (0.0 instead of 1.0 for successful tools)

Test Strategy:
- Load concrete failing traces from baseline corpus
- Assert expected behavior (status="success" for successful tools, status="error" for failed tools)
- Document counterexamples when tests fail
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any

from agent_eval.adapters.generic_json.adapter import adapt
from agent_eval.evaluators.trace_eval.deterministic_metrics import DeterministicMetrics


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent / "test-fixtures" / "baseline"


def load_trace(baseline_corpus_dir: Path, trace_id: str) -> Dict[str, Any]:
    """Load a trace JSON file from the baseline corpus."""
    trace_path = baseline_corpus_dir / f"{trace_id}.json"
    
    if not trace_path.exists():
        pytest.skip(f"Trace file not found: {trace_path}")
    
    with open(trace_path, 'r') as f:
        return json.load(f)


def adapt_and_compute_metrics(trace_data: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Adapt a trace and compute deterministic metrics.
    
    Args:
        trace_data: Raw trace data
        
    Returns:
        Tuple of (metrics_dict, normalized_run)
    """
    # Run adapter
    normalized_run = adapt(trace_data)
    
    # Compute deterministic metrics
    metrics_calculator = DeterministicMetrics()
    metrics_result = metrics_calculator.compute(normalized_run)
    
    return metrics_result.to_dict(), normalized_run


# -------------------------------------------------------------------------
# Regression Exploration Tests - Tool Status Inference
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestToolStatusInferenceRegression:
    """
    Regression exploration tests for tool status inference bugs.
    
    EXPECTED OUTCOME: These tests FAIL on unfixed code (this is correct).
    Failures confirm the bugs exist and provide counterexamples.
    """
    
    def test_good_002_tool_success_rate(self, baseline_corpus_dir):
        """
        Test good-002: Tool call with linked successful result.
        
        Bug Condition:
        - Tool call has tool_run_id="tool-001"
        - Tool result has tool_run_id="tool-001" with successful data
        - Tool call should infer status="success" from linked result
        
        Expected (correct behavior):
        - tool_success_rate = 1.0
        - Tool call step has status="success"
        
        Actual (buggy behavior):
        - tool_success_rate = 0.0
        - Tool call step has status="unknown"
        
        This test WILL FAIL on unfixed code - that's expected and correct.
        """
        trace_id = "good_002_tool_grounded"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt and compute metrics
        metrics, normalized_run = adapt_and_compute_metrics(trace_data)
        
        # EXPECTED: tool_success_rate should be 1.0 (100% success)
        # ACTUAL (buggy): tool_success_rate is 0.0 because status="unknown"
        assert metrics.get("tool_success_rate") == 1.0, (
            f"good_002: Expected tool_success_rate=1.0, got {metrics.get('tool_success_rate')}. "
            f"This indicates tool call status was not inferred from linked successful result."
        )
        
        # Verify tool call step has status="success"
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"Expected 1 tool call, got {len(tool_steps)}"
        
        tool_step = tool_steps[0]
        assert tool_step.get("status") == "success", (
            f"good_002: Expected tool call status='success', got '{tool_step.get('status')}'. "
            f"Tool call should infer status from linked successful result."
        )
    
    def test_bad_002_tool_success_rate(self, baseline_corpus_dir):
        """
        Test bad-002: Tool call with linked successful result (answer ignores result).
        
        Bug Condition:
        - Tool call has tool_run_id="tool-002"
        - Tool result has tool_run_id="tool-002" with successful data
        - Tool call should infer status="success" from linked result
        
        Expected (correct behavior):
        - tool_success_rate = 1.0 (tool succeeded, even though answer is wrong)
        - Tool call step has status="success"
        
        Actual (buggy behavior):
        - tool_success_rate = 0.0
        - Tool call step has status="unknown"
        
        This test WILL FAIL on unfixed code - that's expected and correct.
        """
        trace_id = "bad_002_ignores_tool"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt and compute metrics
        metrics, normalized_run = adapt_and_compute_metrics(trace_data)
        
        # EXPECTED: tool_success_rate should be 1.0 (tool succeeded)
        # ACTUAL (buggy): tool_success_rate is 0.0 because status="unknown"
        assert metrics.get("tool_success_rate") == 1.0, (
            f"bad_002: Expected tool_success_rate=1.0, got {metrics.get('tool_success_rate')}. "
            f"This indicates tool call status was not inferred from linked successful result."
        )
        
        # Verify tool call step has status="success"
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"Expected 1 tool call, got {len(tool_steps)}"
        
        tool_step = tool_steps[0]
        assert tool_step.get("status") == "success", (
            f"bad_002: Expected tool call status='success', got '{tool_step.get('status')}'. "
            f"Tool call should infer status from linked successful result."
        )
    
    def test_weird_001_tool_success_rate(self, baseline_corpus_dir):
        """
        Test weird-001: Duplicate tool calls with linked successful result.
        
        Bug Condition:
        - Tool calls have tool_run_id (after deduplication)
        - Tool result has matching tool_run_id with successful data
        - Tool call should infer status="success" from linked result
        
        Expected (correct behavior):
        - tool_success_rate = 1.0
        - Tool call step has status="success"
        
        Actual (buggy behavior):
        - tool_success_rate = 0.0
        - Tool call step has status="unknown"
        
        This test WILL FAIL on unfixed code - that's expected and correct.
        """
        trace_id = "weird_001_duplicate_tool_calls"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt and compute metrics
        metrics, normalized_run = adapt_and_compute_metrics(trace_data)
        
        # EXPECTED: tool_success_rate should be 1.0
        # ACTUAL (buggy): tool_success_rate is 0.0 because status="unknown"
        assert metrics.get("tool_success_rate") == 1.0, (
            f"weird_001: Expected tool_success_rate=1.0, got {metrics.get('tool_success_rate')}. "
            f"This indicates tool call status was not inferred from linked successful result."
        )
        
        # Verify tool call step has status="success"
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"Expected 1 tool call (after deduplication), got {len(tool_steps)}"
        
        tool_step = tool_steps[0]
        assert tool_step.get("status") == "success", (
            f"weird_001: Expected tool call status='success', got '{tool_step.get('status')}'. "
            f"Tool call should infer status from linked successful result."
        )


# -------------------------------------------------------------------------
# Regression Exploration Tests - Failed Tool Detection
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestFailedToolDetectionRegression:
    """
    Regression exploration tests for failed tool detection bug.
    
    EXPECTED OUTCOME: These tests FAIL on unfixed code (this is correct).
    Failures confirm the bug exists and provide counterexamples.
    """
    
    def test_bad_003_failed_tool_status(self, baseline_corpus_dir):
        """
        Test bad-003: Tool call with linked failed result.
        
        Bug Condition:
        - Tool call has tool_run_id="tool-004"
        - Tool result has tool_run_id="tool-004" with status="error" and tool_error field
        - Tool call should infer status="error" from linked failed result
        
        Expected (correct behavior):
        - tool_success_rate = 0.0 (tool failed)
        - Tool call step has status="error"
        
        Actual (buggy behavior):
        - tool_success_rate = null (no successful or failed tools detected)
        - Tool call step has status="unknown"
        
        This test WILL FAIL on unfixed code - that's expected and correct.
        """
        trace_id = "bad_003_tool_failed_hallucinated"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt and compute metrics
        metrics, normalized_run = adapt_and_compute_metrics(trace_data)
        
        # EXPECTED: tool_success_rate should be 0.0 (tool failed)
        # ACTUAL (buggy): tool_success_rate is null because status="unknown"
        assert metrics.get("tool_success_rate") == 0.0, (
            f"bad_003: Expected tool_success_rate=0.0, got {metrics.get('tool_success_rate')}. "
            f"This indicates tool call status was not inferred from linked failed result."
        )
        
        # Verify tool call step has status="error"
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"Expected 1 tool call, got {len(tool_steps)}"
        
        tool_step = tool_steps[0]
        assert tool_step.get("status") == "error", (
            f"bad_003: Expected tool call status='error', got '{tool_step.get('status')}'. "
            f"Tool call should infer status from linked failed result."
        )


# -------------------------------------------------------------------------
# Documentation of Expected Counterexamples
# -------------------------------------------------------------------------

"""
EXPECTED COUNTEREXAMPLES (when tests fail on unfixed code):

1. good_002_tool_grounded:
   - Expected: tool_success_rate=1.0, status="success"
   - Actual: tool_success_rate=0.0, status="unknown"
   - Root cause: Tool call not inferring status from linked successful result

2. bad_002_ignores_tool:
   - Expected: tool_success_rate=1.0, status="success"
   - Actual: tool_success_rate=0.0, status="unknown"
   - Root cause: Tool call not inferring status from linked successful result

3. bad_003_tool_failed_hallucinated:
   - Expected: tool_success_rate=0.0, status="error"
   - Actual: tool_success_rate=null, status="unknown"
   - Root cause: Tool call not inferring status from linked failed result

4. weird_001_duplicate_tool_calls:
   - Expected: tool_success_rate=1.0, status="success"
   - Actual: tool_success_rate=0.0, status="unknown"
   - Root cause: Tool call not inferring status from linked successful result

These counterexamples confirm the bugs exist and guide the fix implementation.
"""
