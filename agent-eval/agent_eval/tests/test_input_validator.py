"""
Unit tests for InputValidator.

Tests validation of NormalizedRun files against schema and field extraction.
"""

import json
import pytest
from pathlib import Path

from agent_eval.evaluators.trace_eval.input_validator import (
    InputValidator,
    ValidationError,
    ExtractedFields
)


@pytest.fixture
def validator():
    """Create InputValidator instance."""
    # Use smaller limits for testing
    return InputValidator(
        max_file_size_mb=10,
        max_turns=100,
        max_steps_per_turn=100,
        max_total_steps=5000
    )


@pytest.fixture
def valid_normalized_run():
    """Create a valid minimal NormalizedRun."""
    return {
        "run_id": "test-run-123",
        "metadata": {
            "adapter_version": "1.0.0",
            "processed_at": "2024-01-01T00:00:00Z"
        },
        "adapter_stats": {
            "total_events_processed": 10,
            "turn_count": 1,
            "confidence_penalties": [],
            "segmentation_strategy": "TURN_ID",
            "mapping_coverage": 0.95,
            "orphan_tool_results": []
        },
        "turns": [
            {
                "turn_id": "turn-1",
                "user_query": "Hello",
                "final_answer": "Hi there!",
                "steps": [],
                "confidence": 1.0
            }
        ]
    }


class TestInputValidator:
    """Test InputValidator class."""
    
    def test_validate_valid_input(self, validator, valid_normalized_run):
        """Test validation passes for valid NormalizedRun."""
        result = validator.validate(valid_normalized_run)
        assert result == valid_normalized_run
    
    def test_validate_missing_run_id(self, validator, valid_normalized_run):
        """Test validation fails when run_id is missing."""
        del valid_normalized_run["run_id"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        assert "run_id" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_validate_missing_adapter_stats(self, validator, valid_normalized_run):
        """Test validation fails when adapter_stats is missing."""
        del valid_normalized_run["adapter_stats"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        assert "adapter_stats" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_validate_missing_confidence_penalties(self, validator, valid_normalized_run):
        """Test validation fails when confidence_penalties is missing."""
        del valid_normalized_run["adapter_stats"]["confidence_penalties"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        # Schema validation should catch this
        assert "confidence_penalties" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_validate_invalid_input_type(self, validator):
        """Test validation fails when input is not a dict."""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate([])  # List instead of dict
        
        assert "dict" in str(exc_info.value).lower() or "object" in str(exc_info.value).lower()
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate("string")  # String instead of dict
        
        assert "dict" in str(exc_info.value).lower() or "object" in str(exc_info.value).lower()
    
    def test_validate_missing_segmentation_strategy(self, validator, valid_normalized_run):
        """Test validation fails when segmentation_strategy is missing."""
        del valid_normalized_run["adapter_stats"]["segmentation_strategy"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        # Schema validation should catch this
        assert "segmentation_strategy" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_validate_missing_mapping_coverage(self, validator, valid_normalized_run):
        """Test validation fails when mapping_coverage is missing."""
        del valid_normalized_run["adapter_stats"]["mapping_coverage"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        # Schema validation should catch this
        assert "mapping_coverage" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_validate_missing_orphan_tool_results(self, validator, valid_normalized_run):
        """Test validation fails when orphan_tool_results is missing."""
        del valid_normalized_run["adapter_stats"]["orphan_tool_results"]
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(valid_normalized_run)
        
        # Schema validation should catch this
        assert "orphan_tool_results" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()
    
    def test_extract_fields_success(self, validator, valid_normalized_run):
        """Test successful field extraction."""
        validated = validator.validate(valid_normalized_run)
        fields = validator.extract_fields(validated)
        
        assert isinstance(fields, ExtractedFields)
        assert fields.run_id == "test-run-123"
        assert len(fields.turns) == 1
        assert fields.turns[0]["turn_id"] == "turn-1"
        assert "confidence_penalties" in fields.adapter_stats
        assert "segmentation_strategy" in fields.adapter_stats
        assert "mapping_coverage" in fields.adapter_stats
        assert "orphan_tool_results" in fields.adapter_stats
        assert fields.metadata["adapter_version"] == "1.0.0"
    
    def test_extract_fields_missing_field(self, validator):
        """Test field extraction fails when required field is missing."""
        incomplete_data = {
            "metadata": {},
            "adapter_stats": {},
            "turns": []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validator.extract_fields(incomplete_data)
        
        assert "missing" in str(exc_info.value).lower()
    
    def test_validate_file_not_found(self, validator):
        """Test validation fails when file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            validator.validate_file("/nonexistent/file.json")
    
    def test_validate_file_invalid_json(self, validator, tmp_path):
        """Test validation fails for invalid JSON."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("{ invalid json }")
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_file(str(invalid_file))
        
        assert "json" in str(exc_info.value).lower()
    
    def test_validate_file_success(self, validator, valid_normalized_run, tmp_path):
        """Test successful file validation."""
        valid_file = tmp_path / "valid.json"
        valid_file.write_text(json.dumps(valid_normalized_run))
        
        result = validator.validate_file(str(valid_file))
        assert result == valid_normalized_run
    
    def test_optional_fields_handled_gracefully(self, validator):
        """Test that optional fields are handled without errors."""
        minimal_run = {
            "run_id": "test-run-456",
            "metadata": {
                "adapter_version": "1.0.0",
                "processed_at": "2024-01-01T00:00:00Z"
            },
            "adapter_stats": {
                "total_events_processed": 5,
                "turn_count": 1,
                "confidence_penalties": [],
                "segmentation_strategy": "SINGLE_TURN_FALLBACK",
                "mapping_coverage": 0.5,
                "orphan_tool_results": []
            },
            "turns": [
                {
                    "turn_id": "turn-1",
                    "user_query": None,  # Optional field
                    "final_answer": None,  # Optional field
                    "steps": [],
                    "confidence": 0.8
                }
            ]
        }
        
        # Should not raise any errors
        result = validator.validate(minimal_run)
        assert result == minimal_run
        
        fields = validator.extract_fields(result)
        assert fields.run_id == "test-run-456"
        assert fields.turns[0]["user_query"] is None
        assert fields.turns[0]["final_answer"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
