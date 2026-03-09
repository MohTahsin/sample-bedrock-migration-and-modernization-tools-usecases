"""
Preservation regression tests for adapter segmentation behavior.

These tests validate that the bugfix preserves existing correct behavior
for non-buggy segmentation as specified in the adapter-stage-bc-correctness spec.

IMPORTANT: Follow observation-first methodology.
These tests capture baseline behavior on UNFIXED code and should PASS.

Preservation Requirements:
3.3: ANCHOR segmentation strategy should work unchanged
3.4: Traces without turn_id fields should use fallback segmentation strategies
3.5: Other deterministic metrics (turn_count, step_count) should compute correctly
3.6: Tool linking logic should continue to work correctly
3.7: Traces that pass baseline tests should continue to produce correct outcomes

Test Strategy:
- Observe behavior on UNFIXED code for non-buggy segmentation
- Write regression tests capturing observed behavior patterns
- Run tests on UNFIXED code - they should PASS
- After fix, re-run tests to ensure no regressions
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


# -------------------------------------------------------------------------
# Preservation Tests - Segmentation Strategies (Requirement 3.3, 3.4)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestSegmentationStrategyPreservation:
    """
    Preservation tests for segmentation strategies.
    
    Requirement 3.3: ANCHOR segmentation strategy should work unchanged
    Requirement 3.4: Traces without turn_id fields should use fallback strategies
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_single_turn_direct_answer_segmentation(self, baseline_corpus_dir):
        """
        Test that single-turn traces without explicit turn_id segment correctly.
        
        Trace: good_001_direct_answer
        - Has turn_id fields in events (turn_id="turn-1")
        - Should create exactly 1 turn
        - TURN_ID strategy should be used
        
        Preservation Requirement 3.4:
        Traces without turn_id fields should use fallback segmentation strategies.
        (This trace HAS turn_id, so TURN_ID strategy should work)
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Verify turn count
        assert len(normalized_run["turns"]) == 1, (
            f"Expected 1 turn for single-turn trace, got {len(normalized_run['turns'])}"
        )
        
        # Verify segmentation strategy used (stored in adapter_stats)
        adapter_stats = normalized_run.get("adapter_stats", {})
        segmentation_strategy = adapter_stats.get("segmentation_strategy")
        assert segmentation_strategy in ["TURN_ID", "SESSION_PLUS_TRACE_THEN_ANCHOR_SPLIT"], (
            f"Expected TURN_ID or ANCHOR strategy, got '{segmentation_strategy}'"
        )
    
    def test_partial_answer_segmentation(self, baseline_corpus_dir):
        """
        Test that partial answer traces segment correctly.
        
        Trace: partial_001_incomplete_but_ok
        - Single turn trace
        - Should create exactly 1 turn
        - Should use appropriate segmentation strategy
        
        Preservation Requirement 3.4:
        Traces should use appropriate segmentation strategies based on available fields.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "partial_001_incomplete_but_ok"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Verify turn count
        assert len(normalized_run["turns"]) == 1, (
            f"Expected 1 turn for partial answer trace, got {len(normalized_run['turns'])}"
        )
        
        # Verify trace processed successfully
        assert "turns" in normalized_run, "Trace should be processed successfully"
        assert normalized_run["turns"][0].get("steps"), "Turn should have steps"


# -------------------------------------------------------------------------
# Preservation Tests - Deterministic Metrics (Requirement 3.5)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestDeterministicMetricsPreservation:
    """
    Preservation tests for deterministic metrics calculation.
    
    Requirement 3.5: Other deterministic metrics (turn_count, step_count) should
    compute correctly for non-buggy traces.
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_single_turn_metrics_good_001(self, baseline_corpus_dir):
        """
        Test that deterministic metrics compute correctly for single-turn trace.
        
        Trace: good_001_direct_answer
        - Expected: turn_count=1, tool_call_count=0
        - No tool calls, simple question-answer
        
        Preservation Requirement 3.5:
        Deterministic metrics should compute correctly for non-buggy traces.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute deterministic metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify turn count
        assert metrics.turn_count == 1, (
            f"Expected turn_count=1 for good_001, got {metrics.turn_count}"
        )
        
        # Verify tool call count
        assert metrics.tool_call_count == 0, (
            f"Expected tool_call_count=0 for good_001, got {metrics.tool_call_count}"
        )
        
        # Verify step count is positive
        assert metrics.step_count > 0, (
            f"Expected positive step count, got {metrics.step_count}"
        )
    
    def test_single_turn_metrics_partial_001(self, baseline_corpus_dir):
        """
        Test that deterministic metrics compute correctly for partial answer trace.
        
        Trace: partial_001_incomplete_but_ok
        - Expected: turn_count=1, tool_call_count=0
        - No tool calls, brief answer
        
        Preservation Requirement 3.5:
        Deterministic metrics should compute correctly for non-buggy traces.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "partial_001_incomplete_but_ok"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute deterministic metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify turn count
        assert metrics.turn_count == 1, (
            f"Expected turn_count=1 for partial_001, got {metrics.turn_count}"
        )
        
        # Verify tool call count
        assert metrics.tool_call_count == 0, (
            f"Expected tool_call_count=0 for partial_001, got {metrics.tool_call_count}"
        )
        
        # Verify step count is positive
        assert metrics.step_count > 0, (
            f"Expected positive step count, got {metrics.step_count}"
        )
    
    def test_step_count_consistency(self, baseline_corpus_dir):
        """
        Test that step counts are consistent across turns.
        
        Trace: good_001_direct_answer
        - Each turn should have positive step count
        - Total steps should equal sum of turn steps
        
        Preservation Requirement 3.5:
        Step counting logic should remain correct.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Verify each turn has steps
        for i, turn in enumerate(normalized_run["turns"]):
            assert "steps" in turn, f"Turn {i} should have steps field"
            assert len(turn["steps"]) > 0, f"Turn {i} should have at least one step"
        
        # Compute total steps
        total_steps = sum(len(turn["steps"]) for turn in normalized_run["turns"])
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify consistency
        assert metrics.step_count == total_steps, (
            f"Metrics step_count ({metrics.step_count}) should match "
            f"sum of turn steps ({total_steps})"
        )


# -------------------------------------------------------------------------
# Preservation Tests - Tool Linking (Requirement 3.6)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestToolLinkingPreservation:
    """
    Preservation tests for tool linking logic.
    
    Requirement 3.6: Tool linking logic that establishes linkage via tool_run_id
    should continue to work correctly.
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_orphan_tool_result_handled_gracefully(self, baseline_corpus_dir):
        """
        Test that orphan tool results are handled without crashing.
        
        Trace: weird_002_orphan_tool_result
        - Tool result has no matching tool call
        - Should process without crashing
        - Tool linking should handle gracefully
        
        Preservation Requirement 3.6:
        Tool linking logic should continue to work correctly, including
        graceful handling of orphan results.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "weird_002_orphan_tool_result"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace - should not crash
        normalized_run = adapt(trace_data)
        
        # Verify trace processed successfully
        assert "turns" in normalized_run, "Trace should be processed successfully"
        assert len(normalized_run["turns"]) == 1, "Should have 1 turn"
        
        # Verify orphan result is present
        turn = normalized_run["turns"][0]
        tool_result_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_RESULT"]
        
        assert len(tool_result_steps) == 1, (
            f"Expected 1 orphan tool result, got {len(tool_result_steps)}"
        )
        
        # Verify no matching tool call
        tool_call_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_call_steps) == 0, (
            f"Expected 0 tool calls (orphan result), got {len(tool_call_steps)}"
        )


# -------------------------------------------------------------------------
# Preservation Tests - Passing Baseline Tests (Requirement 3.7)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestPassingBaselinePreservation:
    """
    Preservation tests for traces that currently pass baseline tests.
    
    Requirement 3.7: Traces that pass baseline tests should continue to
    produce correct outcomes.
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_good_001_continues_to_pass(self, baseline_corpus_dir):
        """
        Test that good_001 continues to produce correct outcomes.
        
        Trace: good_001_direct_answer
        - Currently passes baseline tests
        - Should continue to pass after fix
        
        Preservation Requirement 3.7:
        Traces that pass baseline tests should continue to produce correct outcomes.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify expected outcomes from baseline
        assert metrics.turn_count == 1, f"Expected turn_count=1, got {metrics.turn_count}"
        assert metrics.tool_call_count == 0, f"Expected tool_call_count=0, got {metrics.tool_call_count}"
        # Note: tool_success_rate is 0.0 when there are no tool calls (observed behavior)
        assert metrics.tool_success_rate == 0.0, f"Expected tool_success_rate=0.0, got {metrics.tool_success_rate}"
    
    def test_partial_001_continues_to_pass(self, baseline_corpus_dir):
        """
        Test that partial_001 continues to produce correct outcomes.
        
        Trace: partial_001_incomplete_but_ok
        - Currently passes baseline tests
        - Should continue to pass after fix
        
        Preservation Requirement 3.7:
        Traces that pass baseline tests should continue to produce correct outcomes.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "partial_001_incomplete_but_ok"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify expected outcomes from baseline
        assert metrics.turn_count == 1, f"Expected turn_count=1, got {metrics.turn_count}"
        assert metrics.tool_call_count == 0, f"Expected tool_call_count=0, got {metrics.tool_call_count}"
        # Note: tool_success_rate is 0.0 when there are no tool calls (observed behavior)
        assert metrics.tool_success_rate == 0.0, f"Expected tool_success_rate=0.0, got {metrics.tool_success_rate}"
    
    def test_weird_002_continues_to_pass(self, baseline_corpus_dir):
        """
        Test that weird_002 continues to handle orphan results gracefully.
        
        Trace: weird_002_orphan_tool_result
        - Currently passes baseline tests (graceful degradation)
        - Should continue to pass after fix
        
        Preservation Requirement 3.7:
        Traces that pass baseline tests should continue to produce correct outcomes.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "weird_002_orphan_tool_result"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # Verify expected outcomes from baseline
        assert metrics.turn_count == 1, f"Expected turn_count=1, got {metrics.turn_count}"
        assert metrics.tool_call_count == 0, f"Expected tool_call_count=0 (orphan result), got {metrics.tool_call_count}"


# -------------------------------------------------------------------------
# Documentation of Expected Behavior
# -------------------------------------------------------------------------

"""
EXPECTED BEHAVIOR (tests should PASS on unfixed code):

1. Segmentation Strategy Preservation (Requirements 3.3, 3.4):
   - good_001: Single turn with turn_id segments correctly (1 turn, TURN_ID strategy)
   - partial_001: Single turn segments correctly (1 turn)
   - Appropriate segmentation strategies are used based on available fields

2. Deterministic Metrics Preservation (Requirement 3.5):
   - good_001: turn_count=1, tool_call_count=0, tool_success_rate=0.0, step_count>0
   - partial_001: turn_count=1, tool_call_count=0, tool_success_rate=0.0, step_count>0
   - Step counts are consistent across turns
   - Note: tool_success_rate=0.0 when there are no tool calls (observed behavior)

3. Tool Linking Preservation (Requirement 3.6):
   - weird_002: Orphan tool result handled gracefully without crash
   - Tool linking logic works correctly for edge cases

4. Passing Baseline Tests Preservation (Requirement 3.7):
   - good_001: Continues to produce correct outcomes
   - partial_001: Continues to produce correct outcomes
   - weird_002: Continues to handle orphan results gracefully

These tests capture baseline behavior that must be preserved after the fix.
All tests PASS on unfixed code, confirming baseline behavior to preserve.
"""
