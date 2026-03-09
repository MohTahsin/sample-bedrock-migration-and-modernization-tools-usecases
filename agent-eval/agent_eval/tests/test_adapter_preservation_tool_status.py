"""
Preservation regression tests for adapter tool status behavior.

These tests validate that the bugfix preserves existing correct behavior
for non-buggy inputs as specified in the adapter-stage-bc-correctness spec.

IMPORTANT: Follow observation-first methodology.
These tests capture baseline behavior on UNFIXED code and should PASS.

Preservation Requirements:
3.1: Tool calls with explicit status fields should keep their explicit status
3.2: Tool calls without linked results should remain status="unknown"

Test Strategy:
- Observe behavior on UNFIXED code for non-buggy inputs
- Write regression tests capturing observed behavior patterns
- Run tests on UNFIXED code - they should PASS
- After fix, re-run tests to ensure no regressions
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any

from agent_eval.adapters.generic_json.adapter import adapt


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
# Preservation Tests - Explicit Status Values (Requirement 3.1)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestExplicitStatusPreservation:
    """
    Preservation tests for explicit status values.
    
    Requirement 3.1: Tool calls with explicit status fields should keep their explicit status.
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_explicit_error_status_preserved(self, baseline_corpus_dir):
        """
        Test that tool result with explicit status="error" is preserved.
        
        Trace: bad_003_tool_failed_hallucinated
        - Tool result has explicit status="error" field
        - This explicit status should be preserved in the normalized output
        
        Preservation Requirement 3.1:
        Tool calls/results with explicit status fields must continue to use
        those explicit status values.
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "bad_003_tool_failed_hallucinated"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Find the tool result step
        turn = normalized_run["turns"][0]
        tool_result_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_RESULT"]
        
        assert len(tool_result_steps) == 1, (
            f"Expected 1 tool result step, got {len(tool_result_steps)}"
        )
        
        tool_result = tool_result_steps[0]
        
        # Verify explicit status="error" is preserved
        assert tool_result.get("status") == "error", (
            f"Expected tool result status='error' (explicit), got '{tool_result.get('status')}'. "
            f"Explicit status values must be preserved (Requirement 3.1)."
        )


# -------------------------------------------------------------------------
# Preservation Tests - Unlinked Tool Calls (Requirement 3.2)
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestUnlinkedToolCallPreservation:
    """
    Preservation tests for tool calls without linked results.
    
    Requirement 3.2: Tool calls without linked results should remain status="unknown".
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_orphan_tool_result_remains_unlinked(self, baseline_corpus_dir):
        """
        Test that orphan tool results (no matching tool call) are handled gracefully.
        
        Trace: weird_002_orphan_tool_result
        - Tool result has tool_run_id="orphan-1" but no matching tool call
        - This is an orphan result that cannot be linked
        - The adapter should process it without crashing
        
        Preservation Requirement 3.2:
        Tool calls without linked results must continue to show status="unknown".
        (In this case, the result is orphaned, so there's no tool call to link to)
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "weird_002_orphan_tool_result"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace - should not crash
        normalized_run = adapt(trace_data)
        
        # Verify the trace was processed successfully
        assert "turns" in normalized_run, "Trace should be processed successfully"
        assert len(normalized_run["turns"]) == 1, "Should have 1 turn"
        
        # Find the orphan tool result step
        turn = normalized_run["turns"][0]
        tool_result_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_RESULT"]
        
        assert len(tool_result_steps) == 1, (
            f"Expected 1 orphan tool result step, got {len(tool_result_steps)}"
        )
        
        # Verify no tool call steps exist (orphan result has no matching call)
        tool_call_steps = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_call_steps) == 0, (
            f"Expected 0 tool call steps (orphan result), got {len(tool_call_steps)}"
        )


# -------------------------------------------------------------------------
# Preservation Tests - Traces Without Tool Calls
# -------------------------------------------------------------------------

@pytest.mark.preservation
class TestTracesWithoutToolCalls:
    """
    Preservation tests for traces without tool calls.
    
    These traces should process correctly and be unaffected by tool status fixes.
    
    EXPECTED OUTCOME: These tests PASS on unfixed code (baseline behavior).
    After fix, they should continue to PASS (no regressions).
    """
    
    def test_direct_answer_no_tools(self, baseline_corpus_dir):
        """
        Test that traces without tool calls process correctly.
        
        Trace: good_001_direct_answer
        - Simple question-answer exchange
        - No tool calls or tool results
        - Should process cleanly
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "good_001_direct_answer"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Verify basic structure
        assert "turns" in normalized_run, "Trace should be processed successfully"
        assert len(normalized_run["turns"]) == 1, "Should have 1 turn"
        
        # Verify no tool calls or results
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] 
                     if s.get("kind") in ["TOOL_CALL", "TOOL_RESULT"]]
        
        assert len(tool_steps) == 0, (
            f"Expected 0 tool steps (no tools used), got {len(tool_steps)}"
        )
        
        # Verify turn has user input and model output
        user_steps = [s for s in turn["steps"] if s.get("kind") == "USER_INPUT"]
        model_steps = [s for s in turn["steps"] if s.get("kind") == "LLM_OUTPUT_CHUNK"]
        
        assert len(user_steps) == 1, f"Expected 1 user input, got {len(user_steps)}"
        assert len(model_steps) == 1, f"Expected 1 model output, got {len(model_steps)}"
    
    def test_partial_answer_no_tools(self, baseline_corpus_dir):
        """
        Test that partial answers without tools process correctly.
        
        Trace: partial_001_incomplete_but_ok
        - Partial but acceptable answer
        - No tool calls
        - Should process cleanly
        
        This test should PASS on unfixed code and continue to PASS after fix.
        """
        trace_id = "partial_001_incomplete_but_ok"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Verify basic structure
        assert "turns" in normalized_run, "Trace should be processed successfully"
        assert len(normalized_run["turns"]) == 1, "Should have 1 turn"
        
        # Verify no tool calls or results
        turn = normalized_run["turns"][0]
        tool_steps = [s for s in turn["steps"] 
                     if s.get("kind") in ["TOOL_CALL", "TOOL_RESULT"]]
        
        assert len(tool_steps) == 0, (
            f"Expected 0 tool steps (no tools used), got {len(tool_steps)}"
        )


# -------------------------------------------------------------------------
# Documentation of Expected Behavior
# -------------------------------------------------------------------------

"""
EXPECTED BEHAVIOR (tests should PASS on unfixed code):

1. Explicit Status Preservation (Requirement 3.1):
   - bad_003: Tool result with explicit status="error" keeps that status
   - Explicit status values are preserved in normalized output

2. Unlinked Tool Calls (Requirement 3.2):
   - weird_002: Orphan tool result (no matching call) processes without crash
   - No tool call steps exist for orphan results

3. Traces Without Tool Calls:
   - good_001: Direct answer without tools processes correctly
   - partial_001: Partial answer without tools processes correctly
   - No tool steps in output for traces without tools

These tests capture baseline behavior that must be preserved after the fix.
"""
