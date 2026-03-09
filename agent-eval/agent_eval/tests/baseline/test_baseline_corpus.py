"""
Baseline validation tests against fixed 10-trace corpus.

These tests validate deterministic components (adapter, metrics, tool counting)
before introducing real LLM judges. Each trace has known expected outcomes.

Test corpus:
- 3 clearly good traces
- 3 clearly bad traces  
- 2 partial/ambiguous traces
- 2 tool-path weird traces
"""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, Any

# Import adapter and metrics
from agent_eval.adapters.generic_json.adapter import adapt
from agent_eval.evaluators.trace_eval.deterministic_metrics import DeterministicMetrics


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent.parent / "test-fixtures" / "baseline"


@pytest.fixture
def expected_outcomes(baseline_corpus_dir: Path) -> Dict[str, Any]:
    """Load expected outcomes for all baseline traces."""
    outcomes_path = baseline_corpus_dir / "expected_outcomes.yaml"
    
    if not outcomes_path.exists():
        pytest.skip(f"Expected outcomes file not found: {outcomes_path}")
    
    with open(outcomes_path, 'r') as f:
        return yaml.safe_load(f)


def load_trace(baseline_corpus_dir: Path, trace_id: str) -> Dict[str, Any]:
    """Load a trace JSON file from the baseline corpus."""
    trace_path = baseline_corpus_dir / f"{trace_id}.json"
    
    if not trace_path.exists():
        pytest.skip(f"Trace file not found: {trace_path}")
    
    with open(trace_path, 'r') as f:
        return json.load(f)


def compute_metrics_for_trace(trace_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapt a trace and compute deterministic metrics.
    
    Args:
        trace_data: Raw trace data
        
    Returns:
        Dictionary of computed metrics
    """
    # Run adapter
    normalized_run = adapt(trace_data)
    
    # Compute deterministic metrics
    metrics_calculator = DeterministicMetrics()
    metrics_result = metrics_calculator.compute(normalized_run)
    
    return metrics_result.to_dict(), normalized_run


def validate_deterministic_metrics(
    actual: Dict[str, Any],
    expected: Dict[str, Any],
    trace_id: str,
    tolerance: float = 0.05
):
    """
    Validate deterministic metrics against expected values.
    
    Args:
        actual: Actual metrics computed by the system
        expected: Expected metrics from expected_outcomes.yaml
        trace_id: Trace identifier for error messages
        tolerance: Tolerance for floating point comparisons (default 5%)
    """
    # Exact match required for counts
    assert actual.get("turn_count") == expected["turn_count"], \
        f"{trace_id}: turn_count mismatch - expected {expected['turn_count']}, got {actual.get('turn_count')}"
    
    assert actual.get("tool_call_count") == expected["tool_call_count"], \
        f"{trace_id}: tool_call_count mismatch - expected {expected['tool_call_count']}, got {actual.get('tool_call_count')}"
    
    # Latency presence check
    if expected.get("latency_present"):
        assert "total_latency_ms" in actual or "avg_turn_latency_ms" in actual, \
            f"{trace_id}: latency fields missing"
    
    # Tool success rate (if tools present)
    if expected["tool_call_count"] > 0 and "tool_success_rate" in expected:
        actual_rate = actual.get("tool_success_rate", 0.0)
        expected_rate = expected["tool_success_rate"]
        
        assert abs(actual_rate - expected_rate) <= tolerance, \
            f"{trace_id}: tool_success_rate mismatch - expected {expected_rate}, got {actual_rate}"


# -------------------------------------------------------------------------
# Test: Good Traces (3 traces)
# -------------------------------------------------------------------------

@pytest.mark.baseline
class TestGoodTraces:
    """Test clearly good traces with correct answers and proper tool usage."""
    
    def test_good_001_direct_answer(self, baseline_corpus_dir, expected_outcomes):
        """
        Test good-001: Direct answer, no tools needed.
        
        Expected:
        - 1 turn
        - 0 tool calls
        - High quality
        - Clean latency
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["good-001"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Additional checks
        assert normalized_run["turns"][0]["final_answer"] is not None, \
            f"{trace_id}: final_answer should be present"
    
    def test_good_002_tool_grounded(self, baseline_corpus_dir, expected_outcomes):
        """
        Test good-002: Tool used correctly, answer grounded.
        
        Expected:
        - 1 turn
        - 1 tool call
        - High quality
        - Tool latency captured
        """
        trace_id = "good_002_tool_grounded"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["good-002"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Additional checks
        turn = normalized_run["turns"][0]
        assert len(turn["steps"]) >= 1, f"{trace_id}: should have tool steps"
        
        # Check tool call/result pairing
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"{trace_id}: should have exactly 1 tool call"
    
    def test_good_003_two_turn_noise(self, baseline_corpus_dir, expected_outcomes):
        """
        Test good-003: Two-turn conversation with noise.
        
        Expected:
        - 2 turns
        - 1 tool call
        - High quality
        - Noise filtered correctly
        """
        trace_id = "good_003_two_turn_noise"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["good-003"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Additional checks
        assert len(normalized_run["turns"]) == 2, \
            f"{trace_id}: should have exactly 2 turns"


# -------------------------------------------------------------------------
# Test: Bad Traces (3 traces)
# -------------------------------------------------------------------------

@pytest.mark.baseline
class TestBadTraces:
    """Test clearly bad traces with wrong answers or ignored tools."""
    
    def test_bad_001_wrong_math(self, baseline_corpus_dir, expected_outcomes):
        """
        Test bad-001: Clearly wrong answer, no tools.
        
        Expected:
        - 1 turn
        - 0 tool calls
        - Low quality
        """
        trace_id = "bad_001_wrong_math"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["bad-001"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
    
    def test_bad_002_ignores_tool(self, baseline_corpus_dir, expected_outcomes):
        """
        Test bad-002: Tool used but result ignored.
        
        Expected:
        - 1 turn
        - 1 tool call
        - Low quality (groundedness issue)
        """
        trace_id = "bad_002_ignores_tool"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["bad-002"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Tool should be present
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"{trace_id}: should have 1 tool call"
    
    def test_bad_003_tool_failed_hallucinated(self, baseline_corpus_dir, expected_outcomes):
        """
        Test bad-003: Failed tool and hallucinated confident answer.
        
        Expected:
        - 1 turn
        - 1 tool call (failed)
        - Low quality
        - Failure captured
        """
        trace_id = "bad_003_tool_failed_hallucinated"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["bad-003"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Check tool failure captured
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, f"{trace_id}: should have 1 tool call"
        
        # Tool should have failed status
        assert tool_steps[0].get("status") in ["error", "failed"], \
            f"{trace_id}: tool should have failure status"


# -------------------------------------------------------------------------
# Test: Partial/Ambiguous Traces (2 traces)
# -------------------------------------------------------------------------

@pytest.mark.baseline
class TestPartialTraces:
    """Test partial or ambiguous traces."""
    
    def test_partial_001_incomplete_but_ok(self, baseline_corpus_dir, expected_outcomes):
        """
        Test partial-001: Incomplete but acceptable answer.
        
        Expected:
        - 1 turn
        - 0 tool calls
        - Medium quality
        """
        trace_id = "partial_001_incomplete_but_ok"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["partial-001"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)
    
    def test_partial_002_hedged_without_tool(self, baseline_corpus_dir, expected_outcomes):
        """
        Test partial-002: Answer hedged, tool missing.
        
        Expected:
        - 1 turn
        - 0 tool calls
        - Low-medium quality
        """
        trace_id = "partial_002_hedged_without_tool"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["partial-002"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate
        validate_deterministic_metrics(metrics, expected, trace_id)


# -------------------------------------------------------------------------
# Test: Weird Tool Path Traces (2 traces)
# -------------------------------------------------------------------------

@pytest.mark.baseline
class TestWeirdTraces:
    """Test weird tool path edge cases."""
    
    def test_weird_001_duplicate_tool_calls(self, baseline_corpus_dir, expected_outcomes):
        """
        Test weird-001: Duplicate tool call events.
        
        Expected:
        - 1 turn
        - 2 raw tool calls → 1 normalized
        - Medium-high quality if deduplicated
        """
        trace_id = "weird_001_duplicate_tool_calls"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["weird-001"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate (should be deduplicated to 1 tool call)
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Check deduplication worked
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_steps) == 1, \
            f"{trace_id}: duplicate tool calls should be deduplicated to 1"
    
    def test_weird_002_orphan_tool_result(self, baseline_corpus_dir, expected_outcomes):
        """
        Test weird-002: Orphan tool result, missing linkage.
        
        Expected:
        - 1 turn
        - 0 or 1 inferred tool call
        - Medium-low quality
        - Orphan handled gracefully
        """
        trace_id = "weird_002_orphan_tool_result"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        expected = expected_outcomes["traces"]["weird-002"]["expected"]
        
        # Compute metrics
        metrics, normalized_run = compute_metrics_for_trace(trace_data)
        
        # Validate (may infer tool call or count as 0)
        validate_deterministic_metrics(metrics, expected, trace_id)
        
        # Check orphan handling
        turn = normalized_run["turns"][0]
        # Adapter should handle gracefully without crashing
        assert turn is not None, f"{trace_id}: turn should be present"


# -------------------------------------------------------------------------
# Test: Corpus Completeness
# -------------------------------------------------------------------------

@pytest.mark.baseline
def test_corpus_completeness(baseline_corpus_dir, expected_outcomes):
    """
    Verify all 10 traces are present in the corpus.
    """
    expected_traces = [
        "good_001_direct_answer",
        "good_002_tool_grounded",
        "good_003_two_turn_noise",
        "bad_001_wrong_math",
        "bad_002_ignores_tool",
        "bad_003_tool_failed_hallucinated",
        "partial_001_incomplete_but_ok",
        "partial_002_hedged_without_tool",
        "weird_001_duplicate_tool_calls",
        "weird_002_orphan_tool_result",
    ]
    
    missing_traces = []
    for trace_id in expected_traces:
        trace_path = baseline_corpus_dir / f"{trace_id}.json"
        if not trace_path.exists():
            missing_traces.append(trace_id)
    
    assert len(missing_traces) == 0, \
        f"Missing baseline traces: {missing_traces}"


@pytest.mark.baseline
def test_expected_outcomes_structure(expected_outcomes):
    """
    Verify expected_outcomes.yaml has correct structure.
    """
    assert "traces" in expected_outcomes, \
        "expected_outcomes.yaml should have 'traces' key"
    
    required_trace_ids = [
        "good-001", "good-002", "good-003",
        "bad-001", "bad-002", "bad-003",
        "partial-001", "partial-002",
        "weird-001", "weird-002"
    ]
    
    for trace_id in required_trace_ids:
        assert trace_id in expected_outcomes["traces"], \
            f"Missing trace in expected_outcomes: {trace_id}"
        
        trace_config = expected_outcomes["traces"][trace_id]
        assert "expected" in trace_config, \
            f"Trace {trace_id} missing 'expected' section"
        
        expected = trace_config["expected"]
        assert "turn_count" in expected, \
            f"Trace {trace_id} missing 'turn_count'"
        assert "tool_call_count" in expected, \
            f"Trace {trace_id} missing 'tool_call_count'"
