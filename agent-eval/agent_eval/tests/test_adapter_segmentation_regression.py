"""
Regression exploration test for adapter turn segmentation bug.

This test validates the turn segmentation bug identified in the
adapter-stage-bc-correctness bugfix spec.

CRITICAL: This test is EXPECTED TO FAIL on unfixed code.
Failure confirms the bug exists. DO NOT fix the test or code when it fails.

Bug Condition:
- Trace has events with turn_id="turn-1" and turn_id="turn-2"
- TURN_ID segmentation strategy is used
- System creates 3 turns instead of 2 (over-splitting bug)

Test Strategy:
- Load concrete failing trace from baseline corpus (good_003)
- Assert expected behavior (turn_count=2 for 2 unique turn_ids)
- Document counterexample when test fails
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
# Regression Exploration Test - Turn Segmentation
# -------------------------------------------------------------------------

@pytest.mark.regression
class TestTurnSegmentationRegression:
    """
    Regression exploration test for turn segmentation bug.
    
    EXPECTED OUTCOME: This test FAILS on unfixed code (this is correct).
    Failure confirms the bug exists and provides counterexample.
    """
    
    def test_good_003_turn_segmentation(self, baseline_corpus_dir):
        """
        Test good-003: Turn segmentation with explicit turn_id fields.
        
        Bug Condition:
        - Trace has events with turn_id="turn-1" and turn_id="turn-2"
        - TURN_ID segmentation strategy should be used
        - System should create exactly 2 turns (one per unique turn_id)
        
        Expected (correct behavior):
        - turn_count = 2 (one turn per unique turn_id)
        - Turn 1 contains all events with turn_id="turn-1"
        - Turn 2 contains all events with turn_id="turn-2"
        
        Actual (buggy behavior):
        - turn_count = 3 (over-splitting creates extra turn)
        - Possible causes:
          - "unknown" bucket created for events without turn_id
          - Anchor splitting applied after TURN_ID strategy
          - Field extraction inconsistent across events
        
        This test WILL FAIL on unfixed code - that's expected and correct.
        """
        trace_id = "good_003_two_turn_noise"
        trace_data = load_trace(baseline_corpus_dir, trace_id)
        
        # Adapt the trace
        normalized_run = adapt(trace_data)
        
        # Compute deterministic metrics
        metrics_calculator = DeterministicMetrics()
        metrics = metrics_calculator.compute(normalized_run)
        
        # EXPECTED: turn_count should be 2 (one per unique turn_id)
        # ACTUAL (buggy): turn_count is 3 (over-splitting bug)
        assert metrics.turn_count == 2, (
            f"good_003: Expected turn_count=2 (for turn_id='turn-1' and 'turn-2'), "
            f"got {metrics.turn_count}. "
            f"This indicates TURN_ID segmentation is over-splitting turns."
        )
        
        # Verify normalized run has exactly 2 turns
        assert len(normalized_run["turns"]) == 2, (
            f"good_003: Expected 2 turns in normalized_run, got {len(normalized_run['turns'])}. "
            f"TURN_ID segmentation should create one turn per unique turn_id."
        )
        
        # Verify segmentation strategy used
        adapter_stats = normalized_run.get("adapter_stats", {})
        segmentation_strategy = adapter_stats.get("segmentation_strategy")
        
        # Note: We expect TURN_ID strategy, but document what we observe
        print(f"Segmentation strategy used: {segmentation_strategy}")
        print(f"Turn count: {len(normalized_run['turns'])}")
        
        # Document turn structure for debugging
        for i, turn in enumerate(normalized_run["turns"]):
            step_count = len(turn.get("steps", []))
            print(f"Turn {i+1}: {step_count} steps")


# -------------------------------------------------------------------------
# Documentation of Expected Counterexample
# -------------------------------------------------------------------------

"""
EXPECTED COUNTEREXAMPLE (when test fails on unfixed code):

good_003_two_turn_noise:
- Expected: turn_count=2 (for turn_id="turn-1" and "turn-2")
- Actual: turn_count=3 (over-splitting creates extra turn)
- Root cause possibilities:
  1. "unknown" bucket: Events without turn_id create extra turn
  2. Anchor splitting: Applied after TURN_ID strategy succeeds
  3. Field extraction: turn_id not resolved consistently across events
  4. Segmentation logic: _segment_by_turn_id() incorrectly splitting groups

This counterexample confirms the bug exists and guides the fix implementation.

Next Steps (Task 4.2):
- Inspect good_003 normalized events BEFORE segmentation
- Verify resolved turn_id for each event
- Count events per turn_id value
- Identify root cause location
"""
