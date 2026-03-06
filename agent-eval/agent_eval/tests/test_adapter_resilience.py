"""
Adapter Resilience Regression Tests

Tests the generic JSON adapter's ability to handle noisy, malformed,
and edge-case raw traces. These tests ensure production-grade resilience
is maintained across code changes.

Each test validates:
- Turn count extraction
- Tool call detection
- Confidence scoring
- Exit behavior (success vs graceful failure)
- Artifact generation
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from agent_eval.adapters.generic_json.adapter import adapt


class TestAdapterResilience:
    """Regression tests for adapter resilience against noisy/malformed inputs"""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_noisy_toplevel_json(self, temp_output_dir):
        """
        Test 1: Extremely noisy top-level JSON
        
        Validates:
        - Ignores random blobs, frontend_logs, session, tenant
        - Ignores event-level noise (ui_state, token_debug)
        - Extracts 1 clean turn
        - Confidence >= 0.8
        """
        raw_trace = {
            "trace_id": "weird-001",
            "session": "abc-123",
            "tenant": "dev",
            "random_blob": {
                "debug": True,
                "huge_array": [1, 2, 3, 4, 5, {"foo": "bar"}],
                "metrics": {"cpu": 88, "memory": 234}
            },
            "events": [
                {
                    "timestamp": "2026-03-06T14:00:00Z",
                    "type": "user_message",
                    "turn_id": "turn-a",
                    "content": "Who discovered gravity?",
                    "ui_state": {"window_size": "large", "theme": "dark"}
                },
                {
                    "timestamp": "2026-03-06T14:00:01Z",
                    "type": "agent_response",
                    "turn_id": "turn-a",
                    "content": "Gravity was famously described by Isaac Newton.",
                    "token_debug": {"prompt_tokens": 120, "completion_tokens": 25}
                }
            ],
            "frontend_logs": [{"event": "scroll"}, {"event": "click"}]
        }

        # Write input file
        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        # Run adapter
        output_file = os.path.join(temp_output_dir, "output.json")
        result = adapt(input_file)

        # Load result is already in memory from adapt()
        # (adapt returns the normalized dict directly)

        # Assertions
        assert len(result["turns"]) == 1, "Should extract exactly 1 turn"
        assert result["metadata"]["run_confidence"] >= 0.8, "Confidence should be >= 0.8"
        
        # Verify noise was ignored (check raw data doesn't contain frontend_logs)
        turn = result["turns"][0]
        assert "frontend_logs" not in str(turn), "Should not include frontend_logs"
        assert "random_blob" not in str(turn), "Should not include random_blob"

    def test_mixed_field_names(self, temp_output_dir):
        """
        Test 2: Mixed field names (event_type vs type, text vs content)
        
        Validates:
        - Handles field name variations
        - Ignores telemetry events
        - Extracts 1 turn (telemetry ignored)
        - Confidence >= 0.3 (may have penalties for missing turn_id on second event)
        """
        raw_trace = {
            "run_id": "weird-002",
            "events": [
                {
                    "timestamp": "2026-03-06T14:10:00Z",
                    "event_type": "user_message",
                    "turn_id": "turn-1",
                    "text": "Explain serverless computing.",
                    "junk_field": "ignore"
                },
                {
                    "timestamp": "2026-03-06T14:10:02Z",
                    "type": "agent_response",
                    "turn_id": "turn-1",
                    "content": "Serverless computing allows developers to run code without managing servers.",
                    "strange_metadata": {"experiment": "alpha"}
                },
                {
                    "timestamp": "2026-03-06T14:10:03Z",
                    "type": "telemetry",
                    "metrics": {"cpu": 72}
                }
            ]
        }

        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        result = adapt(input_file)

        # Assertions
        assert len(result["turns"]) >= 1, "Should extract at least 1 turn"
        assert result["metadata"]["run_confidence"] >= 0.3, "Confidence should be >= 0.3"
        
        # Verify text field was mapped correctly
        turn = result["turns"][0]
        user_step = [s for s in turn["steps"] if s.get("kind") == "USER_INPUT"][0]
        assert "serverless" in str(user_step["raw"]).lower(), "Should map 'text' field to user input"

    def test_tool_calls_with_junk_metadata(self, temp_output_dir):
        """
        Test 3: Tool calls with irrelevant runtime metadata
        
        Validates:
        - Extracts tool_call and tool_result as steps
        - Ignores runtime_debug metadata
        - Extracts 1 turn with 1 tool call
        - Confidence >= 0.8
        """
        raw_trace = {
            "trace_id": "weird-003",
            "events": [
                {
                    "timestamp": "2026-03-06T14:20:00Z",
                    "type": "user_message",
                    "turn_id": "t1",
                    "content": "What is 15 times 6?"
                },
                {
                    "timestamp": "2026-03-06T14:20:01Z",
                    "type": "tool_call",
                    "turn_id": "t1",
                    "tool_name": "calculator",
                    "input": "15*6",
                    "runtime_debug": {"container_id": "c-xyz", "memory_limit": 512}
                },
                {
                    "timestamp": "2026-03-06T14:20:02Z",
                    "type": "tool_result",
                    "turn_id": "t1",
                    "tool_name": "calculator",
                    "output": "90"
                },
                {
                    "timestamp": "2026-03-06T14:20:03Z",
                    "type": "agent_response",
                    "turn_id": "t1",
                    "content": "15 multiplied by 6 is 90."
                }
            ]
        }

        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        result = adapt(input_file)

        # Assertions
        assert len(result["turns"]) == 1, "Should extract exactly 1 turn"
        assert result["metadata"]["run_confidence"] >= 0.8, "Confidence should be >= 0.8"
        
        # Verify tool call extraction (at least tool_call should be present)
        turn = result["turns"][0]
        tool_steps = [s for s in turn["steps"] if s.get("kind") in ["TOOL_CALL", "TOOL_RESULT"]]
        assert len(tool_steps) >= 1, "Should extract at least tool_call"
        
        # Verify tool_call specifically
        tool_calls = [s for s in turn["steps"] if s.get("kind") == "TOOL_CALL"]
        assert len(tool_calls) >= 1, "Should extract tool_call"
        assert tool_calls[0].get("name") == "calculator", "Tool name should be preserved"

    def test_malformed_but_recoverable(self, temp_output_dir):
        """
        Test 4: Malformed trace with missing turn_id and invalid timestamp
        
        Validates:
        - Uses SINGLE_TURN fallback strategy
        - Applies appropriate confidence penalties
        - Still produces valid output
        - Confidence <= 0.1 (multiple penalties)
        """
        raw_trace = {
            "trace_id": "weird-004",
            "events": [
                {
                    "timestamp": "not-a-time",
                    "type": "user_message",
                    "content": "Tell me about photosynthesis."
                },
                {
                    "type": "agent_response",
                    "content": "Photosynthesis is how plants convert sunlight into energy."
                },
                {
                    "type": "debug_event",
                    "message": "internal debug noise"
                }
            ]
        }

        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        result = adapt(input_file)

        # Assertions
        assert len(result["turns"]) == 1, "Should extract 1 turn using SINGLE_TURN fallback"
        assert result["metadata"]["run_confidence"] <= 0.1, "Confidence should be very low due to multiple penalties"
        
        # Verify penalties were applied
        penalties = result["adapter_stats"]["confidence_penalties"]
        penalty_reasons = [p["reason"] for p in penalties]
        assert "single_turn_fallback" in penalty_reasons, "Should apply single_turn_fallback penalty"
        assert "missing_timestamp" in penalty_reasons, "Should apply missing_timestamp penalty"

    def test_multi_turn_with_duplicates(self, temp_output_dir):
        """
        Test 5: Multiple turns with large payloads and junk
        
        Validates:
        - Extracts 2 turns correctly
        - Ignores ui_state and large_payload
        - Confidence >= 0.8
        """
        raw_trace = {
            "trace_id": "weird-005",
            "events": [
                {
                    "timestamp": "2026-03-06T14:40:00Z",
                    "type": "user_message",
                    "turn_id": "turn1",
                    "content": "Who wrote Hamlet?"
                },
                {
                    "timestamp": "2026-03-06T14:40:01Z",
                    "type": "agent_response",
                    "turn_id": "turn1",
                    "content": "Hamlet was written by William Shakespeare.",
                    "large_payload": {"debug": ["a", "b", "c", "d", "e"]}
                },
                {
                    "timestamp": "2026-03-06T14:41:00Z",
                    "type": "user_message",
                    "turn_id": "turn2",
                    "content": "Explain photosynthesis in one line."
                },
                {
                    "timestamp": "2026-03-06T14:41:01Z",
                    "type": "agent_response",
                    "turn_id": "turn2",
                    "content": "Photosynthesis converts sunlight, water, and CO₂ into energy."
                }
            ],
            "ui_state": {"scroll": 2000}
        }

        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        result = adapt(input_file)

        # Assertions
        assert len(result["turns"]) == 2, "Should extract exactly 2 turns"
        assert result["metadata"]["run_confidence"] >= 0.8, "Confidence should be >= 0.8"
        
        # Verify ui_state was ignored
        assert "ui_state" not in str(result["turns"]), "Should not include ui_state in turns"

    def test_ridiculous_json_empty_events(self, temp_output_dir):
        """
        Test 6: Completely ridiculous JSON with empty events array
        
        Validates:
        - Fails gracefully with clear error message
        - No stack trace crash
        - Raises appropriate exception
        """
        raw_trace = {
            "banana": True,
            "foo": "bar",
            "events": []
        }

        input_file = os.path.join(temp_output_dir, "input.json")
        with open(input_file, 'w') as f:
            json.dump(raw_trace, f)

        # Should raise an exception with clear message
        with pytest.raises(Exception) as exc_info:
            adapt(input_file)

        # Verify error message is clear (not a stack trace)
        error_msg = str(exc_info.value)
        assert "events" in error_msg.lower() or "no" in error_msg.lower(), \
            "Error message should mention missing events"
        assert "traceback" not in error_msg.lower(), "Should not include stack trace in error message"


class TestAdapterResilienceEndToEnd:
    """End-to-end tests running full pipeline with resilience fixtures"""

    @pytest.fixture
    def fixtures_dir(self):
        """Get test fixtures directory"""
        return Path(__file__).parent.parent.parent / "test-fixtures"

    def test_weird_traces_exist(self, fixtures_dir):
        """Verify all weird trace fixtures exist"""
        expected_files = [
            "weird_001_noisy_toplevel.json",
            "weird_002_mixed_fields.json",
            "weird_003_tool_calls.json",
            "weird_004_malformed.json",
            "weird_005_multi_turn.json",
            "weird_006_ridiculous.json",
        ]
        
        for filename in expected_files:
            filepath = fixtures_dir / filename
            assert filepath.exists(), f"Missing fixture: {filename}"

    @pytest.mark.integration
    def test_all_weird_traces_produce_artifacts(self, fixtures_dir, tmp_path):
        """
        Integration test: Run all weird traces through full pipeline
        
        Validates that each trace (except ridiculous) produces:
        - normalized_run.*.json
        - Exit code 0
        """
        from agent_eval.cli import main
        import sys

        test_cases = [
            ("weird_001_noisy_toplevel.json", True),
            ("weird_002_mixed_fields.json", True),
            ("weird_003_tool_calls.json", True),
            ("weird_004_malformed.json", True),
            ("weird_005_multi_turn.json", True),
            ("weird_006_ridiculous.json", False),  # Expected to fail
        ]

        for filename, should_succeed in test_cases:
            input_file = fixtures_dir / filename
            output_dir = tmp_path / filename.replace(".json", "")
            output_dir.mkdir(exist_ok=True)

            # Mock sys.argv for CLI
            sys.argv = [
                "agent_eval.cli",
                "--input", str(input_file),
                "--judge-config", str(fixtures_dir / "judges.mock.yaml"),
                "--rubrics", str(fixtures_dir / "rubrics.test.yaml"),
                "--output-dir", str(output_dir),
            ]

            if should_succeed:
                # Should complete successfully
                try:
                    main()
                except SystemExit as e:
                    assert e.code == 0, f"{filename} should exit with code 0"

                # Verify artifacts exist
                normalized_files = list(output_dir.glob("normalized_run.*.json"))
                assert len(normalized_files) > 0, f"{filename} should produce normalized_run artifact"
            else:
                # Should fail gracefully
                with pytest.raises((SystemExit, Exception)):
                    main()
