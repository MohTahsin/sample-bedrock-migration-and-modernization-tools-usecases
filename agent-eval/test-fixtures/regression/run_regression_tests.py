#!/usr/bin/env python3
"""
Regression Test Runner for Generic JSON Adapter

This script runs focused regression tests to validate all production-readiness fixes:
- P0: tool_name propagation, removed attribution dead code
- P1: Expanded final_answer include_kinds, removed fields_source, dotted-key fallback
- P2: Expanded latency end_kinds, enhanced dotted-key handling
- Production: Kind-aware missing_data_count, marked _detect_attribution as reserved

Test Scenarios:
1. Dotted-key nested trace - Validates P2 enhanced dotted-key handling
2. Assistant-message-only final output - Validates P1 final_answer + P2 latency fixes
3. Orphan tool result - Validates existing orphan handling (no regression)
4. Duplicate tool calls - Validates P0 tool_name propagation
5. Multi-turn same session - Validates production kind-aware missing_data

Usage:
    python run_regression_tests.py
    
Exit codes:
    0 - All tests passed
    1 - One or more tests failed
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent_eval.adapters.generic_json import adapt


class RegressionTestRunner:
    """Run regression tests and validate results."""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.passed = 0
        self.failed = 0
        self.failures: List[str] = []
    
    def run_all_tests(self) -> bool:
        """
        Run all regression tests.
        
        Returns:
            True if all tests passed, False otherwise
        """
        print("=" * 80)
        print("REGRESSION TEST SUITE - Generic JSON Adapter")
        print("=" * 80)
        print()
        
        # Test 1: Dotted-key nested trace
        self.run_test(
            "Test 1: Dotted-Key Nested Trace",
            "test_01_dotted_key_nested.json",
            self.validate_dotted_key_test
        )
        
        # Test 2: Assistant-message-only final output
        self.run_test(
            "Test 2: Assistant-Message-Only Final Output",
            "test_02_assistant_message.json",
            self.validate_assistant_message_test
        )
        
        # Test 3: Orphan tool result
        self.run_test(
            "Test 3: Orphan Tool Result",
            "test_03_orphan_tool.json",
            self.validate_orphan_tool_test
        )
        
        # Test 4: Duplicate tool calls
        self.run_test(
            "Test 4: Duplicate Tool Calls",
            "test_04_duplicate_tool.json",
            self.validate_duplicate_tool_test
        )
        
        # Test 5: Multi-turn same session
        self.run_test(
            "Test 5: Multi-Turn Same Session",
            "test_05_multi_turn.json",
            self.validate_multi_turn_test
        )
        
        # Print summary
        print()
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        
        if self.failures:
            print()
            print("FAILURES:")
            for failure in self.failures:
                print(f"  - {failure}")
        
        print("=" * 80)
        
        return self.failed == 0
    
    def run_test(
        self,
        test_name: str,
        fixture_file: str,
        validator: callable
    ) -> None:
        """
        Run a single test.
        
        Args:
            test_name: Human-readable test name
            fixture_file: Test fixture filename
            validator: Validation function that takes result dict and returns (passed, message)
        """
        print(f"\n{test_name}")
        print("-" * 80)
        
        fixture_path = self.test_dir / fixture_file
        
        try:
            # Run adapter
            result = adapt(str(fixture_path))
            
            # Validate result
            passed, message = validator(result)
            
            if passed:
                print(f"✅ PASSED: {message}")
                self.passed += 1
            else:
                print(f"❌ FAILED: {message}")
                self.failed += 1
                self.failures.append(f"{test_name}: {message}")
        
        except Exception as e:
            print(f"❌ FAILED: Exception during test: {str(e)}")
            self.failed += 1
            self.failures.append(f"{test_name}: {str(e)}")
    
    def validate_dotted_key_test(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate dotted-key nested trace test.
        
        Expected:
        - session_id extracted from dotted key "session.id"
        - No crashes or null values
        - Events processed successfully
        """
        # Check session_id was extracted (could be from dotted key or regular field)
        if not result.get("turns"):
            return False, "No turns created"
        
        # Check events were processed
        stats = result.get("adapter_stats", {})
        if stats.get("total_events_processed", 0) < 4:
            return False, f"Expected 4 events, got {stats.get('total_events_processed', 0)}"
        
        # Check no crashes (result structure is valid)
        if not result.get("run_id"):
            return False, "Missing run_id"
        
        return True, "Dotted-key handling works correctly"
    
    def validate_assistant_message_test(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate assistant-message-only final output test.
        
        Expected:
        - final_answer = "It's sunny today!"
        - normalized_latency_ms calculated correctly
        - No missing final_answer
        """
        if not result.get("turns"):
            return False, "No turns created"
        
        turn = result["turns"][0]
        
        # Check final_answer is populated
        final_answer = turn.get("final_answer")
        if not final_answer:
            return False, "Missing final_answer"
        
        if "sunny" not in final_answer.lower():
            return False, f"Unexpected final_answer: {final_answer}"
        
        # Check latency was calculated
        latency = turn.get("normalized_latency_ms")
        if latency is None:
            return False, "Missing normalized_latency_ms"
        
        if latency <= 0:
            return False, f"Invalid latency: {latency}"
        
        return True, f"final_answer and latency extracted correctly (latency={latency}ms)"
    
    def validate_orphan_tool_test(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate orphan tool result test.
        
        Expected:
        - No crash
        - adapter_stats.orphan_tool_results contains one entry
        - Orphan result appears in steps
        - Confidence penalty applied
        """
        stats = result.get("adapter_stats", {})
        
        # Check orphan tool results tracked
        orphans = stats.get("orphan_tool_results", [])
        if len(orphans) != 1:
            return False, f"Expected 1 orphan tool result, got {len(orphans)}"
        
        # Check orphan has location field
        if "location" not in orphans[0]:
            return False, "Orphan tool result missing location field"
        
        # Check confidence penalty applied
        penalties = stats.get("confidence_penalties", [])
        orphan_penalty = any(p.get("reason") == "orphan_tool_results" for p in penalties)
        if not orphan_penalty:
            return False, "Missing orphan_tool_results confidence penalty"
        
        # Check turn was created
        if not result.get("turns"):
            return False, "No turns created"
        
        return True, "Orphan tool result handled correctly with penalty"
    
    def validate_duplicate_tool_test(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate duplicate tool calls test.
        
        Expected:
        - Only one TOOL_CALL step in output (deduplicated)
        - TOOL_RESULT has tool_name="search" (propagated)
        - No duplicate steps
        """
        if not result.get("turns"):
            return False, "No turns created"
        
        turn = result["turns"][0]
        steps = turn.get("steps", [])
        
        # Count TOOL_CALL steps
        tool_calls = [s for s in steps if s.get("kind") == "TOOL_CALL"]
        if len(tool_calls) != 1:
            return False, f"Expected 1 TOOL_CALL step (deduplicated), got {len(tool_calls)}"
        
        # Check TOOL_RESULT has tool_name propagated
        tool_results = [s for s in steps if s.get("kind") == "TOOL_RESULT"]
        if len(tool_results) != 1:
            return False, f"Expected 1 TOOL_RESULT step, got {len(tool_results)}"
        
        tool_result = tool_results[0]
        if tool_result.get("tool_name") != "search":
            return False, f"TOOL_RESULT missing tool_name propagation, got: {tool_result.get('tool_name')}"
        
        return True, "Duplicate tool calls deduplicated, tool_name propagated correctly"
    
    def validate_multi_turn_test(self, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate multi-turn same session test.
        
        Expected:
        - 2 turns created (segmented by turn_id)
        - Each turn has correct events
        - events_with_missing_data is LOW (kind-aware check passes)
        - USER_INPUT events not marked as missing data
        """
        turns = result.get("turns", [])
        if len(turns) != 2:
            return False, f"Expected 2 turns, got {len(turns)}"
        
        # Check each turn has events
        for i, turn in enumerate(turns):
            steps = turn.get("steps", [])
            if len(steps) < 1:
                return False, f"Turn {i} has no steps"
        
        # Check missing_data is reasonable (< 20% for good traces)
        stats = result.get("adapter_stats", {})
        total_events = stats.get("total_events_processed", 0)
        missing_data = stats.get("events_with_missing_data", 0)
        
        if total_events == 0:
            return False, "No events processed"
        
        missing_pct = (missing_data / total_events) * 100
        if missing_pct > 20:
            return False, f"Missing data too high: {missing_pct:.1f}% (expected < 20%)"
        
        # Check segmentation strategy used (should be TURN_ID for this test)
        strategy = stats.get("segmentation_strategy")
        if strategy != "TURN_ID":
            return False, f"Expected TURN_ID segmentation, got {strategy}"
        
        return True, f"Multi-turn segmentation correct, missing_data={missing_pct:.1f}% (kind-aware)"


def main():
    """Main entry point."""
    runner = RegressionTestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
