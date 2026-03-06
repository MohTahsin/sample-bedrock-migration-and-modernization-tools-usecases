"""
Import sanity tests for trace evaluation modules.

Tests that all required modules import cleanly and schema files exist.
"""

import json
import os
from pathlib import Path

import pytest


class TestModuleImports:
    """Test that all trace evaluation modules import cleanly."""
    
    def test_trace_eval_module_imports(self):
        """Test that trace_eval module imports without errors."""
        try:
            import agent_eval.evaluators.trace_eval
            assert agent_eval.evaluators.trace_eval is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent_eval.evaluators.trace_eval: {e}")
    
    def test_trace_eval_judging_module_imports(self):
        """Test that trace_eval.judging module imports without errors."""
        try:
            import agent_eval.evaluators.trace_eval.judging
            assert agent_eval.evaluators.trace_eval.judging is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent_eval.evaluators.trace_eval.judging: {e}")
    
    def test_judges_module_imports(self):
        """Test that judges module (shared primitives) imports without errors."""
        try:
            import agent_eval.judges
            assert agent_eval.judges is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent_eval.judges: {e}")
    
    def test_results_module_imports(self):
        """Test that results module imports without errors."""
        try:
            import agent_eval.evaluators.results
            assert agent_eval.evaluators.results is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent_eval.evaluators.results: {e}")
    
    def test_cli_module_imports(self):
        """Test that cli module imports without errors."""
        try:
            import agent_eval.cli
            assert agent_eval.cli is not None
        except ImportError as e:
            pytest.fail(f"Failed to import agent_eval.cli: {e}")


class TestCLIEntrypoint:
    """Test that CLI entrypoint resolves correctly."""
    
    def test_trace_eval_cli_exists(self):
        """Test that trace_eval_cli function exists in cli module."""
        from agent_eval.cli import trace_eval_cli
        assert callable(trace_eval_cli), "trace_eval_cli should be a callable function"
    
    def test_trace_eval_cli_signature(self):
        """Test that trace_eval_cli has correct signature."""
        from agent_eval.cli import trace_eval_cli
        import inspect
        
        sig = inspect.signature(trace_eval_cli)
        # Should accept no required arguments (uses argparse internally)
        assert len([p for p in sig.parameters.values() if p.default == inspect.Parameter.empty]) == 0


class TestSchemaFiles:
    """Test that all required schema files exist and are valid JSON."""
    
    @pytest.fixture
    def schema_dir(self):
        """Get path to schemas directory."""
        return Path(__file__).parent.parent / "schemas"
    
    def test_normalized_run_schema_exists(self, schema_dir):
        """Test that normalized_run.schema.json exists."""
        schema_path = schema_dir / "normalized_run.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_normalized_run_schema_valid_json(self, schema_dir):
        """Test that normalized_run.schema.json is valid JSON."""
        schema_path = schema_dir / "normalized_run.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
                assert "required" in schema, "Schema should have 'required' field"
                # Verify required fields from task specification
                required_fields = schema.get("required", [])
                assert "run_id" in required_fields
                assert "turns" in required_fields
                assert "adapter_stats" in required_fields
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in normalized_run.schema.json: {e}")
    
    def test_normalized_run_schema_has_adapter_stats_fields(self, schema_dir):
        """Test that adapter_stats has required fields."""
        schema_path = schema_dir / "normalized_run.schema.json"
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            adapter_stats = schema["properties"]["adapter_stats"]
            required_fields = adapter_stats.get("required", [])
            
            # Verify required fields from task specification
            assert "confidence_penalties" in required_fields
            assert "segmentation_strategy" in required_fields
            assert "mapping_coverage" in required_fields
            assert "orphan_tool_results" in required_fields
    
    def test_rubric_schema_exists(self, schema_dir):
        """Test that rubric.schema.json exists."""
        schema_path = schema_dir / "rubric.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_rubric_schema_valid_json(self, schema_dir):
        """Test that rubric.schema.json is valid JSON."""
        schema_path = schema_dir / "rubric.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in rubric.schema.json: {e}")
    
    def test_judge_config_schema_exists(self, schema_dir):
        """Test that judge_config.schema.json exists."""
        schema_path = schema_dir / "judge_config.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_judge_config_schema_valid_json(self, schema_dir):
        """Test that judge_config.schema.json is valid JSON."""
        schema_path = schema_dir / "judge_config.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in judge_config.schema.json: {e}")
    
    def test_judge_response_schema_exists(self, schema_dir):
        """Test that judge_response.schema.json exists."""
        schema_path = schema_dir / "judge_response.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_judge_response_schema_valid_json(self, schema_dir):
        """Test that judge_response.schema.json is valid JSON."""
        schema_path = schema_dir / "judge_response.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
                required_fields = schema.get("required", [])
                # Verify required fields from task specification
                assert "verdict" in required_fields
                assert "score" in required_fields
                assert "confidence" in required_fields
                assert "reasoning" in required_fields
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in judge_response.schema.json: {e}")
    
    def test_judge_run_record_schema_exists(self, schema_dir):
        """Test that judge_run_record.schema.json exists."""
        schema_path = schema_dir / "judge_run_record.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_judge_run_record_schema_valid_json(self, schema_dir):
        """Test that judge_run_record.schema.json is valid JSON."""
        schema_path = schema_dir / "judge_run_record.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
                required_fields = schema.get("required", [])
                # Verify required fields from task specification
                assert "job_id" in required_fields
                assert "run_id" in required_fields
                assert "rubric_id" in required_fields
                assert "judge_id" in required_fields
                assert "repeat_index" in required_fields
                assert "timestamp" in required_fields
                assert "status" in required_fields
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in judge_run_record.schema.json: {e}")
    
    def test_trace_eval_output_schema_exists(self, schema_dir):
        """Test that trace_eval_output.schema.json exists."""
        schema_path = schema_dir / "trace_eval_output.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_trace_eval_output_schema_valid_json(self, schema_dir):
        """Test that trace_eval_output.schema.json is valid JSON."""
        schema_path = schema_dir / "trace_eval_output.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in trace_eval_output.schema.json: {e}")
    
    def test_results_schema_exists(self, schema_dir):
        """Test that results.schema.json exists."""
        schema_path = schema_dir / "results.schema.json"
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
    
    def test_results_schema_valid_json(self, schema_dir):
        """Test that results.schema.json is valid JSON."""
        schema_path = schema_dir / "results.schema.json"
        with open(schema_path, 'r') as f:
            try:
                schema = json.load(f)
                assert isinstance(schema, dict), "Schema should be a JSON object"
                required_fields = schema.get("required", [])
                # Verify required fields from task specification
                assert "format_version" in required_fields
                assert "run_id" in required_fields
                assert "rubrics_hash" in required_fields
                assert "judge_config_hash" in required_fields
                assert "input_hash" in required_fields
                assert "deterministic_metrics" in required_fields
                assert "rubric_results" in required_fields
                assert "judge_disagreements" in required_fields
                assert "artifact_paths" in required_fields
                assert "execution_stats" in required_fields
            except json.JSONDecodeError as e:
                pytest.fail(f"Invalid JSON in results.schema.json: {e}")
