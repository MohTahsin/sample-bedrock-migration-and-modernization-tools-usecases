"""
Rubric Resolution Validation Tests

This module validates rubric resolution logic including default rubrics loading,
user overrides, merging, disabled rubrics, and schema validation.

Requirements Coverage: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10

Test Strategy:
- Test default rubrics load correctly
- Test rubric overrides merge with defaults correctly
- Test disabled rubrics are skipped during evaluation
- Test required rubrics always included regardless of overrides
- Test invalid rubric configuration fails with descriptive error
- Test rubric schema validation before evaluation
- Test rubric metadata preservation (id, scope, scoring_scale)
- Test duplicate rubric ID rejection
- Test both turn-scoped and run-scoped rubric support
- Test evidence_selectors are valid JSONPath expressions
"""

import pytest
import yaml
import tempfile
from pathlib import Path
from typing import Dict, Any, List

from agent_eval.evaluators.trace_eval.rubric_loader import (
    RubricLoader,
    Rubric,
    RubricValidationError
)


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def rubric_loader() -> RubricLoader:
    """Create a fresh RubricLoader instance."""
    return RubricLoader()


@pytest.fixture
def temp_rubric_file(tmp_path: Path):
    """Create a temporary rubric file for testing."""
    def _create_file(content: Dict[str, Any]) -> Path:
        file_path = tmp_path / "test_rubrics.yaml"
        with open(file_path, 'w') as f:
            yaml.dump(content, f)
        return file_path
    return _create_file


# -------------------------------------------------------------------------
# Test: Default Rubrics Loading (Requirement 5.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDefaultRubricsLoading:
    """Validate default rubrics load correctly."""
    
    def test_default_rubrics_load_successfully(self, rubric_loader: RubricLoader):
        """
        Requirement 5.1: When no rubric overrides are provided,
        the Rubric_Resolver SHALL load default rubrics correctly
        
        Expected: 8 default rubrics loaded with all required fields
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        # Verify count
        assert len(rubrics) == 8, \
            f"Expected 8 default rubrics, got {len(rubrics)}"
        
        # Verify all rubrics are Rubric objects
        for rubric in rubrics:
            assert isinstance(rubric, Rubric), \
                f"Expected Rubric object, got {type(rubric)}"
        
        # Verify expected rubric IDs are present
        expected_ids = {
            "TOOL_GROUNDEDNESS",
            "TOOL_CONSISTENCY",
            "TOOL_CALL_QUALITY",
            "TOOL_CHAINING",
            "TRACE_COMPLETENESS",
            "SAFETY_PII",
            "LATENCY_REGRESSION_FLAG",
            "STITCHED_TRACE_SUSPECT"
        }
        
        actual_ids = {r.rubric_id for r in rubrics}
        assert actual_ids == expected_ids, \
            f"Rubric IDs mismatch. Expected: {expected_ids}, Got: {actual_ids}"
    
    def test_default_rubrics_have_required_fields(self, rubric_loader: RubricLoader):
        """
        Requirement 5.7: Rubric_Resolver SHALL preserve rubric metadata
        (id, scope, scoring_scale)
        
        Expected: All default rubrics have required fields populated
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            # Required fields
            assert rubric.rubric_id, \
                f"Rubric missing rubric_id"
            assert rubric.description, \
                f"Rubric {rubric.rubric_id} missing description"
            assert rubric.scope in ["turn", "run"], \
                f"Rubric {rubric.rubric_id} has invalid scope: {rubric.scope}"
            assert rubric.scoring_scale, \
                f"Rubric {rubric.rubric_id} missing scoring_scale"
            assert rubric.evidence_selectors, \
                f"Rubric {rubric.rubric_id} missing evidence_selectors"
            assert isinstance(rubric.enabled, bool), \
                f"Rubric {rubric.rubric_id} enabled must be bool"

    
    def test_default_evidence_budget_applied(self, rubric_loader: RubricLoader):
        """
        Requirement 5.1: Default evidence budget should be applied to rubrics
        
        Expected: All rubrics have evidence_budget set (from file or default)
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            assert rubric.evidence_budget > 0, \
                f"Rubric {rubric.rubric_id} has invalid evidence_budget: {rubric.evidence_budget}"
            assert isinstance(rubric.evidence_budget, int), \
                f"Rubric {rubric.rubric_id} evidence_budget must be int"


# -------------------------------------------------------------------------
# Test: Rubric Overrides and Merging (Requirement 5.2)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestRubricOverridesAndMerging:
    """Validate rubric overrides merge with defaults correctly."""
    
    def test_user_rubric_overrides_default(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.2: When rubric overrides are provided,
        the Rubric_Resolver SHALL merge them with defaults correctly
        
        Expected: User rubric with same ID overrides default
        """
        # Load defaults first
        defaults = rubric_loader.load_default_rubrics()
        
        # Create user override for TOOL_GROUNDEDNESS with different weight
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "TOOL_GROUNDEDNESS",
                    "description": "Custom groundedness evaluation",
                    "weight": 2.5,  # Different from default
                    "severity": "high",  # Different from default
                    "enabled": True,
                    "scoring_scale": {
                        "type": "numeric",
                        "min": 1,
                        "max": 5
                    },
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Custom instructions",
                    "evidence_selectors": ["$.turns[*].user_query"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        # Merge
        merged = rubric_loader.merge_rubrics(defaults, user_rubrics)
        
        # Find TOOL_GROUNDEDNESS in merged
        groundedness = next((r for r in merged if r.rubric_id == "TOOL_GROUNDEDNESS"), None)
        assert groundedness is not None, "TOOL_GROUNDEDNESS not found in merged rubrics"
        
        # Verify override applied
        assert groundedness.weight == 2.5, \
            f"Expected weight 2.5, got {groundedness.weight}"
        assert groundedness.severity == "high", \
            f"Expected severity 'high', got {groundedness.severity}"
        assert groundedness.description == "Custom groundedness evaluation", \
            "Description should be overridden"

    
    def test_user_adds_new_rubric(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.2: User can add new rubrics not in defaults
        
        Expected: New rubric appears in merged list
        """
        defaults = rubric_loader.load_default_rubrics()
        
        # Create user rubric with new ID
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "CUSTOM_METRIC",
                    "description": "Custom evaluation metric",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {
                        "type": "numeric",
                        "min": 1,
                        "max": 10
                    },
                    "aggregation_type": "mean",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Custom evaluation",
                    "evidence_selectors": ["$.turns[*].final_answer"],
                    "scope": "run",
                    "scope_behavior": "aggregate_all_turns"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        # Merge
        merged = rubric_loader.merge_rubrics(defaults, user_rubrics)
        
        # Verify new rubric added
        assert len(merged) == 9, \
            f"Expected 9 rubrics (8 defaults + 1 new), got {len(merged)}"
        
        custom = next((r for r in merged if r.rubric_id == "CUSTOM_METRIC"), None)
        assert custom is not None, "CUSTOM_METRIC not found in merged rubrics"
        assert custom.description == "Custom evaluation metric"
    
    def test_merge_preserves_stable_order(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.2: Merge should preserve stable order
        (defaults first, then new user rubrics)
        
        Expected: Default rubrics appear first in original order
        """
        defaults = rubric_loader.load_default_rubrics()
        default_ids = [r.rubric_id for r in defaults]
        
        # Create user rubric that adds new rubric
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "NEW_RUBRIC_1",
                    "description": "New rubric 1",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        merged = rubric_loader.merge_rubrics(defaults, user_rubrics)
        merged_ids = [r.rubric_id for r in merged]
        
        # Verify default IDs appear first in same order
        default_positions = [merged_ids.index(rid) for rid in default_ids if rid in merged_ids]
        assert default_positions == sorted(default_positions), \
            "Default rubrics should maintain their original order"



# -------------------------------------------------------------------------
# Test: Disabled Rubrics (Requirement 5.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDisabledRubrics:
    """Validate disabled rubrics are skipped during evaluation."""
    
    def test_disabled_rubric_excluded_from_merge(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.3: When a rubric is disabled,
        the Rubric_Resolver SHALL skip it during evaluation
        
        Expected: Disabled rubrics not included in merged result
        """
        defaults = rubric_loader.load_default_rubrics()
        
        # Create user rubric that disables TOOL_GROUNDEDNESS
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "TOOL_GROUNDEDNESS",
                    "description": "Disabled",
                    "enabled": False,  # Explicitly disabled
                    "weight": 1.0,
                    "severity": "medium",
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        # Merge
        merged = rubric_loader.merge_rubrics(defaults, user_rubrics)
        
        # Verify TOOL_GROUNDEDNESS not in merged
        groundedness = next((r for r in merged if r.rubric_id == "TOOL_GROUNDEDNESS"), None)
        assert groundedness is None, \
            "Disabled rubric TOOL_GROUNDEDNESS should not be in merged result"
        
        # Verify count reduced by 1
        assert len(merged) == 7, \
            f"Expected 7 rubrics (8 defaults - 1 disabled), got {len(merged)}"
    
    def test_only_enabled_rubrics_in_result(self, rubric_loader: RubricLoader):
        """
        Requirement 5.3: Only enabled rubrics should be in final result
        
        Expected: All rubrics in result have enabled=True
        """
        defaults = rubric_loader.load_default_rubrics()
        
        # All defaults should be enabled
        for rubric in defaults:
            assert rubric.enabled is True, \
                f"Default rubric {rubric.rubric_id} should be enabled"



# -------------------------------------------------------------------------
# Test: Invalid Rubric Configuration (Requirement 5.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestInvalidRubricConfiguration:
    """Validate invalid rubric configuration fails with descriptive error."""
    
    def test_missing_rubric_id_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Invalid rubric configuration SHALL fail
        with descriptive error
        
        Expected: Missing rubric_id raises RubricValidationError
        """
        rubric_data = {
            # Missing rubric_id
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have rubric_id"):
            rubric_loader.validate_rubric(rubric)
    
    def test_missing_description_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Missing description should fail validation
        
        Expected: Missing description raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            # Missing description
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have description"):
            rubric_loader.validate_rubric(rubric)
    
    def test_invalid_scope_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Invalid scope value should fail validation
        
        Expected: Scope not in ['turn', 'run'] raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "invalid_scope",  # Invalid
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="scope must be 'turn' or 'run'"):
            rubric_loader.validate_rubric(rubric)

    
    def test_invalid_scoring_scale_type_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Invalid scoring_scale type should fail
        
        Expected: scoring_scale type not in ['numeric', 'categorical'] fails
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "invalid_type"},  # Invalid
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="scoring_scale type must be"):
            rubric_loader.validate_rubric(rubric)
    
    def test_numeric_scale_missing_min_max_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Numeric scoring_scale must have min and max
        
        Expected: Missing min/max raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric"},  # Missing min/max
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have 'min' and 'max'"):
            rubric_loader.validate_rubric(rubric)
    
    def test_categorical_scale_missing_values_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Categorical scoring_scale must have values
        
        Expected: Missing values raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "categorical"},  # Missing values
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "majority_vote",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have 'values'"):
            rubric_loader.validate_rubric(rubric)
    
    def test_empty_evidence_selectors_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: evidence_selectors must not be empty
        
        Expected: Empty evidence_selectors raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": [],  # Empty
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have evidence_selectors"):
            rubric_loader.validate_rubric(rubric)



# -------------------------------------------------------------------------
# Test: Rubric Schema Validation (Requirement 5.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestRubricSchemaValidation:
    """Validate rubric schema validation before evaluation."""
    
    def test_enabled_must_be_boolean(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: Rubric_Resolver SHALL validate rubric schema
        
        Expected: enabled field must be boolean
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": "true",  # String instead of bool
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="enabled must be a boolean"):
            rubric_loader.validate_rubric(rubric)
    
    def test_requires_llm_judge_must_be_boolean(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: requires_llm_judge must be boolean
        
        Expected: requires_llm_judge field must be boolean
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "requires_llm_judge": "false",  # String instead of bool
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="requires_llm_judge must be a boolean"):
            rubric_loader.validate_rubric(rubric)
    
    def test_weight_bounds_validation(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: weight must be within valid bounds (0.0 to 5.0)
        
        Expected: weight outside bounds raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "weight": 10.0,  # Exceeds max
            "severity": "medium",
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="weight must be between 0.0 and 5.0"):
            rubric_loader.validate_rubric(rubric)

    
    def test_severity_enum_validation(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: severity must be valid enum value
        
        Expected: Invalid severity raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "weight": 1.0,
            "severity": "invalid_severity",  # Invalid
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="severity must be one of"):
            rubric_loader.validate_rubric(rubric)
    
    def test_aggregation_type_validation(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: aggregation_type must be valid
        
        Expected: Invalid aggregation_type raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "invalid_type",  # Invalid
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="aggregation_type must be one of"):
            rubric_loader.validate_rubric(rubric)
    
    def test_deterministic_rubric_consistency(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: Deterministic rubrics must have consistent configuration
        
        Expected: requires_llm_judge=False must use aggregation_type='deterministic'
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "run",
            "scope_behavior": "aggregate_all_turns",
            "aggregation_type": "median",  # Should be deterministic
            "requires_llm_judge": False,
            "deterministic_source": "metrics.test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must use aggregation_type='deterministic'"):
            rubric_loader.validate_rubric(rubric)



# -------------------------------------------------------------------------
# Test: Rubric Metadata Preservation (Requirement 5.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestRubricMetadataPreservation:
    """Validate rubric metadata preservation (id, scope, scoring_scale)."""
    
    def test_metadata_preserved_after_loading(self, rubric_loader: RubricLoader):
        """
        Requirement 5.7: Rubric_Resolver SHALL preserve rubric metadata
        (id, scope, scoring_scale)
        
        Expected: All metadata fields preserved correctly
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            # Verify metadata fields are preserved
            assert rubric.rubric_id, "rubric_id must be preserved"
            assert rubric.scope in ["turn", "run"], "scope must be preserved"
            assert rubric.scoring_scale, "scoring_scale must be preserved"
            assert "type" in rubric.scoring_scale, "scoring_scale.type must be preserved"
            
            # Verify scoring_scale structure based on type
            if rubric.scoring_scale["type"] == "numeric":
                assert "min" in rubric.scoring_scale, "numeric scale must have min"
                assert "max" in rubric.scoring_scale, "numeric scale must have max"
            elif rubric.scoring_scale["type"] == "categorical":
                assert "values" in rubric.scoring_scale, "categorical scale must have values"
    
    def test_metadata_preserved_after_merge(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.7: Metadata preserved after merge operation
        
        Expected: Merged rubrics retain all metadata
        """
        defaults = rubric_loader.load_default_rubrics()
        
        # Create user override
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "TOOL_GROUNDEDNESS",
                    "description": "Override",
                    "weight": 2.0,
                    "severity": "high",
                    "enabled": True,
                    "scoring_scale": {
                        "type": "numeric",
                        "min": 0,
                        "max": 10
                    },
                    "aggregation_type": "mean",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "run",
                    "scope_behavior": "aggregate_all_turns"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        merged = rubric_loader.merge_rubrics(defaults, user_rubrics)
        
        # Find overridden rubric
        groundedness = next((r for r in merged if r.rubric_id == "TOOL_GROUNDEDNESS"), None)
        assert groundedness is not None
        
        # Verify metadata preserved from override
        assert groundedness.rubric_id == "TOOL_GROUNDEDNESS"
        assert groundedness.scope == "run"
        assert groundedness.scoring_scale["type"] == "numeric"
        assert groundedness.scoring_scale["min"] == 0
        assert groundedness.scoring_scale["max"] == 10


# -------------------------------------------------------------------------
# Test: Duplicate Rubric ID Rejection (Requirement 5.8)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDuplicateRubricIDRejection:
    """Validate duplicate rubric ID rejection."""
    
    def test_duplicate_ids_in_user_file_rejected(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.8: When duplicate rubric IDs are detected,
        the Rubric_Resolver SHALL reject the configuration
        
        Expected: Duplicate IDs in user file raise RubricValidationError
        """
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "DUPLICATE_ID",
                    "description": "First",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                },
                {
                    "rubric_id": "DUPLICATE_ID",  # Duplicate!
                    "description": "Second",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        
        with pytest.raises(RubricValidationError, match="Duplicate rubric_id"):
            rubric_loader.load_user_rubrics(str(user_file))



# -------------------------------------------------------------------------
# Test: Turn-Scoped and Run-Scoped Rubric Support (Requirement 5.9)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestScopeSupport:
    """Validate both turn-scoped and run-scoped rubric support."""
    
    def test_turn_scoped_rubrics_present(self, rubric_loader: RubricLoader):
        """
        Requirement 5.9: Rubric_Resolver SHALL support both turn-scoped
        and run-scoped rubrics
        
        Expected: Default rubrics include turn-scoped rubrics
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        turn_scoped = [r for r in rubrics if r.scope == "turn"]
        assert len(turn_scoped) > 0, \
            "Expected at least one turn-scoped rubric in defaults"
        
        # Verify turn-scoped rubrics have correct scope_behavior
        for rubric in turn_scoped:
            assert rubric.scope_behavior == "per_turn", \
                f"Turn-scoped rubric {rubric.rubric_id} must use scope_behavior='per_turn'"
    
    def test_run_scoped_rubrics_present(self, rubric_loader: RubricLoader):
        """
        Requirement 5.9: Run-scoped rubrics should be present
        
        Expected: Default rubrics include run-scoped rubrics
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        run_scoped = [r for r in rubrics if r.scope == "run"]
        assert len(run_scoped) > 0, \
            "Expected at least one run-scoped rubric in defaults"
        
        # Verify run-scoped rubrics have valid scope_behavior
        for rubric in run_scoped:
            assert rubric.scope_behavior in ["aggregate_all_turns", "sample_turns"], \
                f"Run-scoped rubric {rubric.rubric_id} must use valid scope_behavior"
    
    def test_scope_behavior_consistency(self, rubric_loader: RubricLoader):
        """
        Requirement 5.9: scope and scope_behavior must be consistent
        
        Expected: Turn scope uses per_turn, run scope uses aggregate_all_turns or sample_turns
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            if rubric.scope == "turn":
                assert rubric.scope_behavior == "per_turn", \
                    f"Rubric {rubric.rubric_id} with scope='turn' must use scope_behavior='per_turn'"
            elif rubric.scope == "run":
                assert rubric.scope_behavior in ["aggregate_all_turns", "sample_turns"], \
                    f"Rubric {rubric.rubric_id} with scope='run' must use valid run scope_behavior"
    
    def test_user_can_create_both_scopes(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.9: User can create rubrics with both scopes
        
        Expected: User rubrics with both scopes are accepted
        """
        user_rubrics_content = {
            "version": "1.0.0",
            "rubrics": [
                {
                    "rubric_id": "CUSTOM_TURN",
                    "description": "Turn-scoped custom",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                },
                {
                    "rubric_id": "CUSTOM_RUN",
                    "description": "Run-scoped custom",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "run",
                    "scope_behavior": "aggregate_all_turns"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        user_rubrics = rubric_loader.load_user_rubrics(str(user_file))
        
        assert len(user_rubrics) == 2
        
        turn_rubric = next((r for r in user_rubrics if r.rubric_id == "CUSTOM_TURN"), None)
        run_rubric = next((r for r in user_rubrics if r.rubric_id == "CUSTOM_RUN"), None)
        
        assert turn_rubric is not None and turn_rubric.scope == "turn"
        assert run_rubric is not None and run_rubric.scope == "run"



# -------------------------------------------------------------------------
# Test: Evidence Selectors Validation (Requirement 5.10)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestEvidenceSelectorsValidation:
    """Validate evidence_selectors are valid JSONPath expressions."""
    
    def test_evidence_selectors_are_strings(self, rubric_loader: RubricLoader):
        """
        Requirement 5.10: Rubric_Resolver SHALL validate evidence_selectors
        are valid JSONPath expressions
        
        Expected: All evidence_selectors are non-empty strings
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            assert isinstance(rubric.evidence_selectors, list), \
                f"Rubric {rubric.rubric_id} evidence_selectors must be a list"
            
            assert len(rubric.evidence_selectors) > 0, \
                f"Rubric {rubric.rubric_id} must have at least one evidence_selector"
            
            for i, selector in enumerate(rubric.evidence_selectors):
                assert isinstance(selector, str), \
                    f"Rubric {rubric.rubric_id} selector {i} must be a string"
                assert selector.strip(), \
                    f"Rubric {rubric.rubric_id} selector {i} must not be empty"
    
    def test_evidence_selectors_jsonpath_format(self, rubric_loader: RubricLoader):
        """
        Requirement 5.10: Evidence selectors should follow JSONPath format
        
        Expected: Selectors start with $ (JSONPath root)
        """
        rubrics = rubric_loader.load_default_rubrics()
        
        for rubric in rubrics:
            for selector in rubric.evidence_selectors:
                # JSONPath expressions typically start with $
                assert selector.startswith("$"), \
                    f"Rubric {rubric.rubric_id} selector '{selector}' should start with '$' (JSONPath root)"
    
    def test_empty_selector_rejected(self, rubric_loader: RubricLoader):
        """
        Requirement 5.10: Empty evidence selectors should be rejected
        
        Expected: Empty string selector raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": [""],  # Empty string
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must be a non-empty string"):
            rubric_loader.validate_rubric(rubric)
    
    def test_non_string_selector_rejected(self, rubric_loader: RubricLoader):
        """
        Requirement 5.10: Non-string selectors should be rejected
        
        Expected: Non-string selector raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": [123],  # Number instead of string
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must be a non-empty string"):
            rubric_loader.validate_rubric(rubric)


# -------------------------------------------------------------------------
# Test: Additional Edge Cases
# -------------------------------------------------------------------------

@pytest.mark.component
class TestAdditionalEdgeCases:
    """Additional edge case tests for rubric resolution."""
    
    def test_missing_version_in_user_file_fails(self, rubric_loader: RubricLoader, temp_rubric_file):
        """
        Requirement 5.5: User rubrics file must have version field
        
        Expected: Missing version raises RubricValidationError
        """
        user_rubrics_content = {
            # Missing version
            "rubrics": [
                {
                    "rubric_id": "TEST",
                    "description": "Test",
                    "weight": 1.0,
                    "severity": "medium",
                    "enabled": True,
                    "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
                    "aggregation_type": "median",
                    "run_aggregation_policy": "standard",
                    "requires_llm_judge": True,
                    "evaluation_instructions": "Test",
                    "evidence_selectors": ["$.test"],
                    "scope": "turn",
                    "scope_behavior": "per_turn"
                }
            ]
        }
        
        user_file = temp_rubric_file(user_rubrics_content)
        
        with pytest.raises(RubricValidationError, match="must contain 'version' field"):
            rubric_loader.load_user_rubrics(str(user_file))

    
    def test_llm_rubric_without_evaluation_instructions_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: LLM rubrics must have evaluation_instructions
        
        Expected: Missing evaluation_instructions for LLM rubric fails
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            # Missing evaluation_instructions
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must have evaluation_instructions"):
            rubric_loader.validate_rubric(rubric)
    
    def test_deterministic_rubric_without_source_fails(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: Deterministic rubrics must have deterministic_source
        
        Expected: Missing deterministic_source for deterministic rubric fails
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "run",
            "scope_behavior": "aggregate_all_turns",
            "aggregation_type": "deterministic",
            "requires_llm_judge": False,
            # Missing deterministic_source
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must specify deterministic_source"):
            rubric_loader.validate_rubric(rubric)
    
    def test_deterministic_source_format_validation(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: deterministic_source must be dotted path format
        
        Expected: deterministic_source without dot fails validation
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {"type": "numeric", "min": 1, "max": 5},
            "evidence_selectors": ["$.test"],
            "scope": "run",
            "scope_behavior": "aggregate_all_turns",
            "aggregation_type": "deterministic",
            "requires_llm_judge": False,
            "deterministic_source": "invalid_no_dot"  # No dot
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="must be a dotted path"):
            rubric_loader.validate_rubric(rubric)
    
    def test_numeric_scale_min_max_validation(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: Numeric scale min must be less than max
        
        Expected: min >= max raises RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {
                "type": "numeric",
                "min": 5,
                "max": 1  # min > max
            },
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "median",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="min must be less than max"):
            rubric_loader.validate_rubric(rubric)
    
    def test_categorical_values_uniqueness(self, rubric_loader: RubricLoader):
        """
        Requirement 5.6: Categorical values must be unique
        
        Expected: Duplicate values raise RubricValidationError
        """
        rubric_data = {
            "rubric_id": "TEST",
            "description": "Test",
            "enabled": True,
            "scoring_scale": {
                "type": "categorical",
                "values": ["good", "bad", "good"]  # Duplicate
            },
            "evidence_selectors": ["$.test"],
            "scope": "turn",
            "scope_behavior": "per_turn",
            "aggregation_type": "majority_vote",
            "requires_llm_judge": True,
            "evaluation_instructions": "Test"
        }
        
        rubric = Rubric(rubric_data)
        
        with pytest.raises(RubricValidationError, match="values must be unique"):
            rubric_loader.validate_rubric(rubric)
    
    def test_file_not_found_error(self, rubric_loader: RubricLoader):
        """
        Requirement 5.5: Non-existent file should raise FileNotFoundError
        
        Expected: Loading non-existent file raises FileNotFoundError
        """
        with pytest.raises(FileNotFoundError, match="not found"):
            rubric_loader.load_user_rubrics("/nonexistent/path/rubrics.yaml")
