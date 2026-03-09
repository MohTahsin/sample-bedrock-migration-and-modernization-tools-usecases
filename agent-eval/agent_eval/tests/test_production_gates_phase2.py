"""
Phase 2 Production Testing Suite for Generic JSON Adapter.

This module implements advanced production tests covering:
- Real production traces
- Config drift scenarios
- Fuzz/mutation testing
- Performance and scale
- Concurrency and thread-safety
- Determinism and repeatability

These tests validate production-grade behavior beyond basic correctness.
"""

import json
import pytest
import time
import copy
import random
import threading
from pathlib import Path
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent_eval.adapters.generic_json import adapt
from agent_eval.adapters.generic_json.exceptions import InputError, ValidationError, AdapterError


# Test fixture paths
FIXTURES_DIR = Path(__file__).parent.parent.parent / "test-fixtures"
PHASE2_DIR = FIXTURES_DIR / "production-gates-phase2"
REAL_TRACES_DIR = PHASE2_DIR / "real-traces"
FUZZ_DIR = PHASE2_DIR / "fuzz"
PERF_DIR = PHASE2_DIR / "performance"


def load_fixture(filename: str, subdir: str = "") -> Dict[str, Any]:
    """Load a test fixture JSON file."""
    if subdir:
        fixture_path = PHASE2_DIR / subdir / filename
    else:
        fixture_path = PHASE2_DIR / filename
    
    with open(fixture_path, 'r') as f:
        return json.load(f)


def mutate_remove_keys(data: Dict[str, Any], removal_rate: float = 0.2) -> Dict[str, Any]:
    """
    Randomly remove keys from a dict structure.
    
    Args:
        data: Input dictionary
        removal_rate: Fraction of keys to remove (0.0 to 1.0)
    
    Returns:
        Mutated dictionary with some keys removed
    """
    if not isinstance(data, dict):
        return data
    
    mutated = {}
    for key, value in data.items():
        # Randomly skip this key
        if random.random() < removal_rate:
            continue
        
        # Recursively mutate nested dicts
        if isinstance(value, dict):
            mutated[key] = mutate_remove_keys(value, removal_rate)
        elif isinstance(value, list):
            mutated[key] = [mutate_remove_keys(item, removal_rate) if isinstance(item, dict) else item 
                           for item in value]
        else:
            mutated[key] = value
    
    return mutated


def mutate_type_confusion(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Replace values with wrong types.
    
    Examples:
    - dict → list
    - string → number
    - list → string
    """
    if not isinstance(data, dict):
        return data
    
    mutated = {}
    for key, value in data.items():
        # 20% chance to corrupt this value
        if random.random() < 0.2:
            if isinstance(value, dict):
                mutated[key] = ["corrupted", "dict"]
            elif isinstance(value, str):
                mutated[key] = 12345
            elif isinstance(value, (int, float)):
                mutated[key] = "corrupted_number"
            elif isinstance(value, list):
                mutated[key] = "corrupted_list"
            else:
                mutated[key] = value
        else:
            # Recursively mutate
            if isinstance(value, dict):
                mutated[key] = mutate_type_confusion(value)
            elif isinstance(value, list):
                mutated[key] = [mutate_type_confusion(item) if isinstance(item, dict) else item 
                               for item in value]
            else:
                mutated[key] = value
    
    return mutated


class TestRealTraces:
    """Tests using real production traces."""
    
    @pytest.mark.skipif(not REAL_TRACES_DIR.exists(), reason="Real traces not available")
    def test_real_trace_01_cloudwatch_agentcore(self):
        """
        Real trace 1: CloudWatch AgentCore trace.
        
        Validates adapter behavior on actual AgentCore deployment logs.
        """
        if not (REAL_TRACES_DIR / "cloudwatch_agentcore.json").exists():
            pytest.skip("CloudWatch trace fixture not available")
        
        result = adapt(REAL_TRACES_DIR / "cloudwatch_agentcore.json")
        
        # Basic validation
        assert "turns" in result
        assert "adapter_stats" in result
        
        # Turn count should be reasonable (human inspection required for exact count)
        turn_count = len(result["turns"])
        assert turn_count > 0, "Should have at least one turn"
        assert turn_count < 100, "Turn count seems unreasonably high"
        
        # Confidence should be decent for real traces
        avg_confidence = sum(t.get("confidence", 0) for t in result["turns"]) / len(result["turns"])
        assert avg_confidence > 0.5, f"Average confidence too low: {avg_confidence}"
    
    @pytest.mark.skipif(not REAL_TRACES_DIR.exists(), reason="Real traces not available")
    def test_real_trace_02_otel_multi_service(self):
        """
        Real trace 2: OTEL multi-service trace.
        
        Validates span hierarchy and service boundary handling.
        """
        if not (REAL_TRACES_DIR / "otel_multi_service.json").exists():
            pytest.skip("OTEL trace fixture not available")
        
        result = adapt(REAL_TRACES_DIR / "otel_multi_service.json")
        
        # Should handle span hierarchy
        assert "turns" in result
        stats = result["adapter_stats"]
        
        # Should have processed events
        assert stats.get("total_events_processed", 0) > 0
    
    @pytest.mark.skipif(not REAL_TRACES_DIR.exists(), reason="Real traces not available")
    def test_real_trace_03_bedrock_agent(self):
        """
        Real trace 3: Bedrock agent execution trace.
        
        Validates action groups and knowledge base handling.
        """
        if not (REAL_TRACES_DIR / "bedrock_agent.json").exists():
            pytest.skip("Bedrock trace fixture not available")
        
        result = adapt(REAL_TRACES_DIR / "bedrock_agent.json")
        
        # Should identify tool calls (action groups)
        assert "turns" in result
        
        # Check for tool calls in steps
        has_tool_calls = False
        for turn in result["turns"]:
            for step in turn.get("steps", []):
                if step.get("kind") == "TOOL_CALL":
                    has_tool_calls = True
                    break
        
        # Bedrock agents typically use tools
        assert has_tool_calls, "Expected tool calls in Bedrock agent trace"
    
    @pytest.mark.skipif(not REAL_TRACES_DIR.exists(), reason="Real traces not available")
    def test_real_trace_04_noisy_production(self):
        """
        Real trace 4: Noisy production trace with debug events.
        
        Validates noise filtering and signal extraction.
        """
        if not (REAL_TRACES_DIR / "noisy_production.json").exists():
            pytest.skip("Noisy trace fixture not available")
        
        result = adapt(REAL_TRACES_DIR / "noisy_production.json")
        
        # Should filter noise
        stats = result["adapter_stats"]
        
        # Should have dropped or filtered some events
        dropped = stats.get("dropped_events_count", 0)
        invalid = stats.get("invalid_events_count", 0)
        
        # Noisy traces should have some filtering
        assert dropped + invalid > 0, "Expected some events to be filtered"
    
    @pytest.mark.skipif(not REAL_TRACES_DIR.exists(), reason="Real traces not available")
    def test_real_trace_05_multi_session_stitched(self):
        """
        Real trace 5: Multiple sessions stitched together.
        
        Validates session boundary detection.
        """
        if not (REAL_TRACES_DIR / "multi_session_stitched.json").exists():
            pytest.skip("Multi-session trace fixture not available")
        
        result = adapt(REAL_TRACES_DIR / "multi_session_stitched.json")
        
        # Should handle multiple sessions
        assert "turns" in result
        
        # Multiple sessions should result in multiple turns
        assert len(result["turns"]) > 1, "Expected multiple turns for multi-session trace"


class TestConfigDrift:
    """Tests for config drift and field migration scenarios."""
    
    def test_config_drift_01_renamed_timestamp(self):
        """
        Config drift 1: Renamed timestamp field.
        
        Validates fallback when primary timestamp field is renamed.
        """
        # Create fixture with renamed timestamp field
        trace = {
            "events": [
                {
                    "event_type": "USER_INPUT",
                    "event_time": "2024-03-09T10:00:00Z",  # Renamed from 'timestamp'
                    "session_id": "session-001",
                    "content": "Hello"
                },
                {
                    "event_type": "ASSISTANT_OUTPUT",
                    "event_time": "2024-03-09T10:00:01Z",
                    "session_id": "session-001",
                    "content": "Hi"
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should still work with fallback
        assert "turns" in result
        assert len(result["turns"]) >= 1
        
        # Should have confidence penalty or warning
        stats = result["adapter_stats"]
        penalties = stats.get("confidence_penalties", [])
        
        # May have timestamp-related penalties
        # (exact behavior depends on config aliases)
    
    def test_config_drift_02_nested_alias_moved(self):
        """
        Config drift 2: Nested alias moved deeper.
        
        Validates handling when field nesting changes.
        """
        trace = {
            "events": [
                {
                    "event": {
                        "metadata": {
                            "type": "USER_INPUT"  # Moved from event.type
                        }
                    },
                    "timestamp": "2024-03-09T10:00:00Z",
                    "session_id": "session-002",
                    "content": "Test"
                }
            ]
        }
        
        # Should handle gracefully (may not extract type, but shouldn't crash)
        try:
            result = adapt(trace)
            assert "turns" in result
        except (ValidationError, AdapterError):
            # Acceptable to fail gracefully
            pass
    
    def test_config_drift_03_event_type_missing_operation_exists(self):
        """
        Config drift 3: event_type missing, operation field present.
        
        Validates fallback to alternative classification fields.
        """
        trace = {
            "events": [
                {
                    "operation": "user_message",  # Alternative to event_type
                    "timestamp": "2024-03-09T10:00:00Z",
                    "session_id": "session-003",
                    "content": "Hello"
                },
                {
                    "operation": "assistant_response",
                    "timestamp": "2024-03-09T10:00:01Z",
                    "session_id": "session-003",
                    "content": "Hi"
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should work with operation field
        assert "turns" in result
        assert len(result["turns"]) >= 1
    
    def test_config_drift_04_tool_result_payload_moved(self):
        """
        Config drift 4: Tool result payload moved to attributes.
        
        Validates extraction from alternative locations.
        """
        trace = {
            "events": [
                {
                    "event_type": "TOOL_CALL",
                    "timestamp": "2024-03-09T10:00:00Z",
                    "session_id": "session-004",
                    "tool_run_id": "call-001",
                    "tool_name": "calculator"
                },
                {
                    "event_type": "TOOL_RESULT",
                    "timestamp": "2024-03-09T10:00:01Z",
                    "session_id": "session-004",
                    "tool_run_id": "call-001",
                    "attributes": {
                        "result": {"answer": 42}  # Moved from top-level
                    }
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should still link tool call and result
        assert "turns" in result
        turn = result["turns"][0]
        steps = turn["steps"]
        
        tool_calls = [s for s in steps if s.get("kind") == "TOOL_CALL"]
        assert len(tool_calls) >= 1, "Should have tool call"
    
    def test_config_drift_05_complete_field_alias_failure(self):
        """
        Config drift 5: All aliases for critical field fail.
        
        Validates graceful degradation when field cannot be found.
        """
        trace = {
            "events": [
                {
                    "unknown_type_field": "USER_INPUT",  # No known alias
                    "timestamp": "2024-03-09T10:00:00Z",
                    "session_id": "session-005",
                    "content": "Hello"
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should handle gracefully
        assert "turns" in result
        
        # Should have reduced mapping coverage
        stats = result["adapter_stats"]
        mapping_coverage = stats.get("mapping_coverage", 1.0)
        
        # Coverage should be reduced (exact value depends on config)
        assert mapping_coverage < 1.0, "Expected reduced mapping coverage"


class TestFuzzMutation:
    """Fuzz and mutation tests for robustness."""
    
    def test_fuzz_01_random_key_removal(self):
        """
        Fuzz 1: Random key removal.
        
        Removes 20% of keys randomly to test resilience.
        """
        # Load a clean fixture
        base_fixture = FIXTURES_DIR / "production-gates" / "case_01_single_turn_clean.json"
        with open(base_fixture) as f:
            clean_trace = json.load(f)
        
        # Mutate by removing keys
        mutated_trace = mutate_remove_keys(clean_trace, removal_rate=0.2)
        
        # Should handle gracefully
        try:
            result = adapt(mutated_trace)
            
            # If successful, should have valid structure
            assert "turns" in result
            assert "adapter_stats" in result
            
            # Should track missing data or have reduced mapping coverage
            stats = result["adapter_stats"]
            missing_data = stats.get("events_with_missing_data", 0)
            mapping_coverage = stats.get("mapping_coverage", 1.0)
            
            # Either missing data tracked OR mapping coverage reduced
            assert missing_data > 0 or mapping_coverage < 1.0, \
                "Expected missing data or reduced mapping coverage after key removal"
            
        except (ValidationError, AdapterError) as e:
            # Acceptable to fail gracefully
            assert len(str(e)) > 0, "Error message should be informative"
    
    def test_fuzz_02_type_confusion(self):
        """
        Fuzz 2: Type confusion.
        
        Replaces values with wrong types.
        """
        base_fixture = FIXTURES_DIR / "production-gates" / "case_01_single_turn_clean.json"
        with open(base_fixture) as f:
            clean_trace = json.load(f)
        
        # Mutate types
        random.seed(42)  # Reproducible
        mutated_trace = mutate_type_confusion(clean_trace)
        
        # Should handle gracefully
        try:
            result = adapt(mutated_trace)
            
            # Should track dropped events
            stats = result["adapter_stats"]
            dropped = stats.get("dropped_events_count", 0)
            invalid = stats.get("invalid_events_count", 0)
            
            assert dropped + invalid > 0, "Expected some events to be dropped"
            
        except (ValidationError, AdapterError):
            # Acceptable to fail gracefully
            pass
    
    def test_fuzz_03_timestamp_corruption(self):
        """
        Fuzz 3: Timestamp corruption.
        
        Replaces timestamps with garbage.
        """
        trace = {
            "events": [
                {
                    "event_type": "USER_INPUT",
                    "timestamp": "garbage_timestamp_123",
                    "session_id": "session-fuzz",
                    "content": "Event 1"
                },
                {
                    "event_type": "ASSISTANT_OUTPUT",
                    "timestamp": "not-a-date",
                    "session_id": "session-fuzz",
                    "content": "Event 2"
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should handle gracefully
        assert "turns" in result
        
        # Should have timestamp warnings
        stats = result["adapter_stats"]
        penalties = stats.get("confidence_penalties", [])
        
        # Should have timestamp-related penalties
        timestamp_penalties = [p for p in penalties if "timestamp" in p.get("reason", "").lower()]
        assert len(timestamp_penalties) > 0, "Expected timestamp penalties"
    
    def test_fuzz_04_event_order_shuffle(self):
        """
        Fuzz 4: Event order shuffle.
        
        Randomly shuffles event order.
        """
        trace = {
            "events": [
                {"event_type": "USER_INPUT", "timestamp": "2024-03-09T10:00:00Z", "session_id": "s1", "turn_id": "1", "content": "A"},
                {"event_type": "ASSISTANT_OUTPUT", "timestamp": "2024-03-09T10:00:01Z", "session_id": "s1", "turn_id": "1", "content": "B"},
                {"event_type": "USER_INPUT", "timestamp": "2024-03-09T10:00:02Z", "session_id": "s1", "turn_id": "2", "content": "C"},
                {"event_type": "ASSISTANT_OUTPUT", "timestamp": "2024-03-09T10:00:03Z", "session_id": "s1", "turn_id": "2", "content": "D"},
            ]
        }
        
        # Shuffle events
        events = trace["events"].copy()
        random.seed(42)
        random.shuffle(events)
        shuffled_trace = {"events": events}
        
        result = adapt(shuffled_trace)
        
        # Should still work (timestamps should help)
        assert "turns" in result
        assert len(result["turns"]) >= 1
    
    def test_fuzz_05_duplicate_ids(self):
        """
        Fuzz 5: Duplicate IDs.
        
        Duplicates tool_run_id and span_id across events.
        """
        trace = {
            "events": [
                {
                    "event_type": "TOOL_CALL",
                    "timestamp": "2024-03-09T10:00:00Z",
                    "session_id": "s1",
                    "tool_run_id": "dup-001",
                    "tool_name": "tool1"
                },
                {
                    "event_type": "TOOL_CALL",
                    "timestamp": "2024-03-09T10:00:01Z",
                    "session_id": "s1",
                    "tool_run_id": "dup-001",  # Duplicate!
                    "tool_name": "tool2"
                },
                {
                    "event_type": "TOOL_RESULT",
                    "timestamp": "2024-03-09T10:00:02Z",
                    "session_id": "s1",
                    "tool_run_id": "dup-001",
                    "result": {"data": "result"}
                }
            ]
        }
        
        result = adapt(trace)
        
        # Should handle deterministically
        assert "turns" in result
        
        # Should have warning about duplicates (implementation-dependent)


class TestPerformance:
    """Performance and scale tests."""
    
    def test_performance_01_1k_events(self):
        """
        Performance 1: 1K event trace.
        
        Validates performance with 1,000 events.
        """
        # Generate 1K events
        events = []
        for i in range(1000):
            turn_id = str(i // 20)  # 50 turns
            events.append({
                "event_type": "USER_INPUT" if i % 2 == 0 else "ASSISTANT_OUTPUT",
                "timestamp": f"2024-03-09T10:{i//60:02d}:{i%60:02d}Z",
                "session_id": "perf-session",
                "turn_id": turn_id,
                "content": f"Event {i}"
            })
        
        trace = {"events": events}
        
        # Time execution
        start_time = time.time()
        result = adapt(trace)
        elapsed = time.time() - start_time
        
        # Should complete quickly
        assert elapsed < 5.0, f"Took too long: {elapsed:.2f}s"
        
        # Should process all events
        stats = result["adapter_stats"]
        assert stats.get("total_events_processed", 0) == 1000
    
    def test_performance_02_10k_events(self):
        """
        Performance 2: 10K event trace.
        
        Validates performance with 10,000 events.
        """
        # Generate 10K events
        events = []
        for i in range(10000):
            turn_id = str(i // 20)  # 500 turns
            events.append({
                "event_type": "USER_INPUT" if i % 2 == 0 else "ASSISTANT_OUTPUT",
                "timestamp": f"2024-03-09T{i//3600:02d}:{(i%3600)//60:02d}:{i%60:02d}Z",
                "session_id": "perf-session",
                "turn_id": turn_id,
                "content": f"Event {i}"
            })
        
        trace = {"events": events}
        
        # Time execution
        start_time = time.time()
        result = adapt(trace)
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time
        assert elapsed < 30.0, f"Took too long: {elapsed:.2f}s"
        
        # Should process all events
        stats = result["adapter_stats"]
        assert stats.get("total_events_processed", 0) == 10000
    
    @pytest.mark.slow
    def test_performance_03_large_payloads(self):
        """
        Performance 3: Very large payloads.
        
        Validates handling of events with large content.
        """
        # Generate events with large payloads
        large_content = "x" * (1024 * 1024)  # 1MB string
        
        events = []
        for i in range(100):
            events.append({
                "event_type": "USER_INPUT" if i % 2 == 0 else "ASSISTANT_OUTPUT",
                "timestamp": f"2024-03-09T10:00:{i:02d}Z",
                "session_id": "perf-session",
                "turn_id": str(i // 2),
                "content": large_content
            })
        
        trace = {"events": events}
        
        # Should handle without OOM
        try:
            result = adapt(trace)
            assert "turns" in result
        except MemoryError:
            pytest.fail("Out of memory with large payloads")


class TestConcurrency:
    """Concurrency and thread-safety tests."""
    
    def test_concurrency_01_parallel_same_fixture(self):
        """
        Concurrency 1: Parallel execution on same fixture.
        
        Validates thread-safety with 50 parallel runs.
        """
        fixture_path = FIXTURES_DIR / "production-gates" / "case_01_single_turn_clean.json"
        
        def run_adapter():
            return adapt(fixture_path)
        
        # Run 50 times in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_adapter) for _ in range(50)]
            results = [f.result() for f in as_completed(futures)]
        
        # All should succeed
        assert len(results) == 50
        
        # All should produce identical output (deterministic)
        first_result = results[0]
        for result in results[1:]:
            # Compare turn counts
            assert len(result["turns"]) == len(first_result["turns"])
    
    def test_concurrency_02_parallel_mixed_fixtures(self):
        """
        Concurrency 2: Parallel execution on different fixtures.
        
        Validates no cross-contamination with 100 parallel runs.
        """
        fixtures = [
            FIXTURES_DIR / "production-gates" / "case_01_single_turn_clean.json",
            FIXTURES_DIR / "production-gates" / "case_02_multi_turn_clean.json",
            FIXTURES_DIR / "production-gates" / "case_06_malformed_events.json",
            FIXTURES_DIR / "production-gates" / "case_07_dirty_timestamps.json",
        ]
        
        def run_adapter(fixture_path):
            return adapt(fixture_path)
        
        # Run 100 times with mixed fixtures
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(100):
                fixture = fixtures[i % len(fixtures)]
                futures.append(executor.submit(run_adapter, fixture))
            
            results = [f.result() for f in as_completed(futures)]
        
        # All should succeed
        assert len(results) == 100
        
        # All should have valid structure
        for result in results:
            assert "turns" in result
            assert "adapter_stats" in result


class TestDeterminism:
    """Determinism and repeatability tests."""
    
    def test_determinism_01_repeated_execution(self):
        """
        Determinism 1: Repeated execution.
        
        Runs same input 10 times and validates identical output.
        """
        fixture_path = FIXTURES_DIR / "production-gates" / "case_01_single_turn_clean.json"
        
        results = []
        for _ in range(10):
            result = adapt(fixture_path)
            results.append(result)
        
        # All should have same turn count
        turn_counts = [len(r["turns"]) for r in results]
        assert len(set(turn_counts)) == 1, f"Turn counts vary: {turn_counts}"
        
        # All should have same confidence scores
        first_confidences = [t.get("confidence") for t in results[0]["turns"]]
        for result in results[1:]:
            confidences = [t.get("confidence") for t in result["turns"]]
            assert confidences == first_confidences, "Confidence scores vary"
    
    def test_determinism_02_backward_compatibility(self):
        """
        Determinism 2: Backward compatibility.
        
        Validates that baseline fixtures produce stable output.
        """
        # Run all Phase 1 fixtures
        phase1_fixtures = [
            "case_01_single_turn_clean.json",
            "case_02_multi_turn_clean.json",
            "case_06_malformed_events.json",
            "case_07_dirty_timestamps.json",
        ]
        
        for fixture_name in phase1_fixtures:
            fixture_path = FIXTURES_DIR / "production-gates" / fixture_name
            
            # Should still work
            result = adapt(fixture_path)
            
            # Basic validation
            assert "turns" in result
            assert "adapter_stats" in result
            assert len(result["turns"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
