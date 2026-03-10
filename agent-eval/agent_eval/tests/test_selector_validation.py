"""
Tests for Selector Validation

This module tests the selector validation logic that prevents run-level
selectors from being used in turn-scoped rubrics.
"""

import pytest
from agent_eval.evaluators.trace_eval.selector_validation import (
    validate_turn_scoped_selectors,
    SelectorValidationError
)


class TestInvalidTurnScopedSelectors:
    """Test cases that should be REJECTED - invalid selector configurations."""
    
    def test_reject_turns_wildcard_user_query(self):
        """
        Invalid Case 1: Turn-scoped rubric with $.turns[*].user_query
        
        This is the most common misconfiguration - using run-level path
        when context is narrowed to a single turn.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TEST_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].user_query"]
            )
        
        error_msg = str(exc_info.value)
        assert "TEST_RUBRIC" in error_msg
        assert "$.turns[*].user_query" in error_msg
        assert "turn-relative paths" in error_msg
    
    def test_reject_turns_wildcard_final_answer(self):
        """
        Invalid Case 2: Turn-scoped rubric with $.turns[*].final_answer
        
        Another common pattern - accessing final_answer through turns array.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TOOL_CONSISTENCY",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].final_answer"]
            )
        
        error_msg = str(exc_info.value)
        assert "TOOL_CONSISTENCY" in error_msg
        assert "$.turns[*].final_answer" in error_msg
    
    def test_reject_turns_wildcard_steps_tool_call(self):
        """
        Invalid Case 3: Turn-scoped rubric with $.turns[*].steps[?(@.kind=='TOOL_CALL')]
        
        Nested path through turns array - common in tool evaluation rubrics.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TOOL_GROUNDEDNESS",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].steps[?(@.kind=='TOOL_CALL')]"]
            )
        
        error_msg = str(exc_info.value)
        assert "TOOL_GROUNDEDNESS" in error_msg
        assert "$.turns[*].steps" in error_msg
    
    def test_reject_turns_wildcard_steps_tool_result(self):
        """
        Invalid Case 4: Turn-scoped rubric with $.turns[*].steps[?(@.kind=='TOOL_RESULT')]
        
        Another nested path pattern for tool results.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TOOL_CONSISTENCY",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].steps[?(@.kind=='TOOL_RESULT')]"]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns[*].steps" in error_msg
    
    def test_reject_turns_indexed_access(self):
        """
        Invalid Case 5: Turn-scoped rubric with $.turns[0].user_query (indexed access)
        
        Indexed access to turns array is also invalid in turn context.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TEST_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[0].user_query"]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns[0].user_query" in error_msg
    
    def test_reject_turns_wildcard_nested_attributes(self):
        """
        Invalid Case 6: Turn-scoped rubric with $.turns[*].steps[*].attributes
        
        Multiple levels of nesting through turns array.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TOOL_CALL_QUALITY",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].steps[*].attributes"]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns[*].steps[*].attributes" in error_msg
    
    def test_reject_mixed_valid_and_invalid_selectors(self):
        """
        Invalid Case 7: Turn-scoped rubric with multiple selectors, one invalid
        
        Even if some selectors are valid, any invalid selector should fail validation.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="MIXED_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=[
                    "$.user_query",  # Valid
                    "$.turns[*].final_answer"  # Invalid
                ]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns[*].final_answer" in error_msg
        # Should not mention the valid selector
        assert "$.user_query" not in error_msg or "Invalid selectors" in error_msg
    
    def test_reject_turns_nested_metadata(self):
        """
        Invalid Case 8: Turn-scoped rubric with nested turns reference: $.turns[*].metadata.turn_id
        
        Accessing metadata through turns array.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="METADATA_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].metadata.turn_id"]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns[*].metadata.turn_id" in error_msg
    
    def test_reject_turns_array_direct_access(self):
        """
        Invalid Case 9: Turn-scoped rubric with $.turns (accessing turns array directly)
        
        Direct access to turns array without further path.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="ARRAY_ACCESS_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns"]
            )
        
        error_msg = str(exc_info.value)
        assert "$.turns" in error_msg
    
    def test_reject_recursive_descent_turns(self):
        """
        Invalid Case 10: Turn-scoped rubric with $..turns[*].user_query (recursive descent)
        
        Recursive descent to turns array is also invalid.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="RECURSIVE_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$..turns[*].user_query"]
            )
        
        error_msg = str(exc_info.value)
        assert "$..turns[*].user_query" in error_msg


class TestValidTurnScopedSelectors:
    """Test cases that should be ACCEPTED - valid selector configurations."""
    
    def test_accept_turn_relative_user_query(self):
        """
        Valid Case 1: Turn-scoped rubric with $.user_query
        
        Correct turn-relative path for accessing user query.
        """
        # Should not raise any exception
        validate_turn_scoped_selectors(
            rubric_id="TOOL_GROUNDEDNESS",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.user_query"]
        )
    
    def test_accept_turn_relative_final_answer(self):
        """
        Valid Case 2: Turn-scoped rubric with $.final_answer
        
        Correct turn-relative path for accessing final answer.
        """
        validate_turn_scoped_selectors(
            rubric_id="TOOL_CONSISTENCY",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.final_answer"]
        )
    
    def test_accept_turn_relative_steps_tool_call(self):
        """
        Valid Case 3: Turn-scoped rubric with $.steps[?(@.kind=='TOOL_CALL')]
        
        Correct turn-relative path for accessing tool calls within a turn.
        """
        validate_turn_scoped_selectors(
            rubric_id="TOOL_GROUNDEDNESS",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.steps[?(@.kind=='TOOL_CALL')]"]
        )
    
    def test_accept_turn_relative_steps_tool_result(self):
        """
        Valid Case 4: Turn-scoped rubric with $.steps[?(@.kind=='TOOL_RESULT')]
        
        Correct turn-relative path for accessing tool results within a turn.
        """
        validate_turn_scoped_selectors(
            rubric_id="TOOL_CONSISTENCY",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.steps[?(@.kind=='TOOL_RESULT')]"]
        )
    
    def test_accept_turn_relative_steps_attributes(self):
        """
        Valid Case 5: Turn-scoped rubric with $.steps[*].attributes
        
        Correct turn-relative path for accessing step attributes.
        """
        validate_turn_scoped_selectors(
            rubric_id="TOOL_CALL_QUALITY",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.steps[*].attributes"]
        )
    
    def test_accept_turn_relative_turn_id(self):
        """
        Valid Case 6: Turn-scoped rubric with $.turn_id
        
        Correct turn-relative path for accessing turn identifier.
        """
        validate_turn_scoped_selectors(
            rubric_id="METADATA_RUBRIC",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.turn_id"]
        )
    
    def test_accept_turn_relative_metadata_confidence(self):
        """
        Valid Case 7: Turn-scoped rubric with $.metadata.confidence
        
        Correct turn-relative path for accessing turn metadata.
        """
        validate_turn_scoped_selectors(
            rubric_id="CONFIDENCE_RUBRIC",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.metadata.confidence"]
        )
    
    def test_accept_run_scoped_with_turns_wildcard(self):
        """
        Valid Case 8: Run-scoped rubric with $.turns[*].user_query (valid for run scope)
        
        Run-scoped rubrics CAN use $.turns[*] because they operate on full run context.
        """
        validate_turn_scoped_selectors(
            rubric_id="RUN_LEVEL_RUBRIC",
            scope="run",  # Run scope, not turn
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.turns[*].user_query"]
        )
    
    def test_accept_run_scoped_with_turns_final_answer(self):
        """
        Valid Case 9: Run-scoped rubric with $.turns[*].final_answer (valid for run scope)
        
        Run-scoped rubrics can access all turns.
        """
        validate_turn_scoped_selectors(
            rubric_id="TRACE_COMPLETENESS",
            scope="run",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.turns[*].final_answer"]
        )
    
    def test_accept_run_scoped_metadata(self):
        """
        Valid Case 10: Run-scoped rubric with $.metadata (run-level metadata)
        
        Run-scoped rubrics can access run-level metadata.
        """
        validate_turn_scoped_selectors(
            rubric_id="RUN_METADATA_RUBRIC",
            scope="run",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.metadata"]
        )


class TestValidationEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_full_context_mode_allows_turns_selectors(self):
        """
        When turn_selector_mode='full_context', turn-scoped rubrics
        receive the full run context, so $.turns[*] selectors are valid.
        """
        # Should not raise - full_context mode doesn't narrow context
        validate_turn_scoped_selectors(
            rubric_id="FULL_CONTEXT_RUBRIC",
            scope="turn",
            turn_selector_mode="full_context",  # Not narrow_to_turn
            evidence_selectors=["$.turns[*].user_query"]
        )
    
    def test_empty_selectors_list(self):
        """
        Empty selectors list should not raise validation error
        (will be caught by rubric validation instead).
        """
        validate_turn_scoped_selectors(
            rubric_id="EMPTY_RUBRIC",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=[]
        )
    
    def test_field_name_containing_turns(self):
        """
        Field names containing 'turns' (like 'turns_count') should be allowed
        as they don't reference the turns array.
        """
        validate_turn_scoped_selectors(
            rubric_id="TURNS_COUNT_RUBRIC",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=["$.turns_count", "$.metadata.total_turns"]
        )
    
    def test_multiple_invalid_selectors_all_reported(self):
        """
        When multiple selectors are invalid, all should be reported in error.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="MULTI_INVALID",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=[
                    "$.turns[*].user_query",
                    "$.turns[*].final_answer",
                    "$.turns[0].steps"
                ]
            )
        
        error_msg = str(exc_info.value)
        # All three invalid selectors should be mentioned
        assert "$.turns[*].user_query" in error_msg
        assert "$.turns[*].final_answer" in error_msg
        assert "$.turns[0].steps" in error_msg
    
    def test_error_message_includes_rubric_id(self):
        """
        Error messages should include the rubric_id for easy debugging.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="MY_CUSTOM_RUBRIC",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].data"]
            )
        
        error_msg = str(exc_info.value)
        assert "MY_CUSTOM_RUBRIC" in error_msg
    
    def test_error_message_includes_fix_instructions(self):
        """
        Error messages should include actionable fix instructions.
        """
        with pytest.raises(SelectorValidationError) as exc_info:
            validate_turn_scoped_selectors(
                rubric_id="TEST",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[*].user_query"]
            )
        
        error_msg = str(exc_info.value)
        assert "To fix this:" in error_msg
        assert "$.user_query" in error_msg  # Shows the corrected version
    
    def test_complex_jsonpath_with_turns_rejected(self):
        """
        Complex JSONPath expressions with turns array should be rejected.
        """
        with pytest.raises(SelectorValidationError):
            validate_turn_scoped_selectors(
                rubric_id="COMPLEX",
                scope="turn",
                turn_selector_mode="narrow_to_turn",
                evidence_selectors=["$.turns[?(@.turn_id=='turn_1')].steps"]
            )
    
    def test_multiple_valid_selectors_accepted(self):
        """
        Multiple valid turn-relative selectors should all be accepted.
        """
        validate_turn_scoped_selectors(
            rubric_id="MULTI_VALID",
            scope="turn",
            turn_selector_mode="narrow_to_turn",
            evidence_selectors=[
                "$.user_query",
                "$.final_answer",
                "$.steps[?(@.kind=='TOOL_CALL')]",
                "$.steps[?(@.kind=='TOOL_RESULT')]",
                "$.metadata.confidence"
            ]
        )
