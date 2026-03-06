"""
Unit tests for pipeline execution, artifact validation, and script orchestration.

This test module covers Phase 6-7 functionality including script execution helpers,
artifact validators, and pipeline execution.
"""
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import (
    execute_script1,
    execute_script2,
    execute_script3,
    validate_script1_output,
    validate_script2_output,
    validate_script3_output,
    execute_pipeline,
    ScriptExecutionError,
    ParsedARN,
    RuntimeMetadata,
    DiscoveredLogGroups,
    PipelineConfig,
    PipelineResult,
)


class TestScriptExecution:
    """Tests for script execution helper functions."""

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.subprocess.run')
    def test_execute_script1_success(self, mock_run):
        """Test successful Script 1 execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        result = execute_script1(
            log_group="/test/log/group",
            session_id="test-session-id",
            minutes=180,
            output="/tmp/output.json",
            region="us-east-1",
            profile="myprofile",
            output_dir="/tmp"
        )
        
        assert result == "/tmp/output.json"
        mock_run.assert_called_once()
        
        # Verify command includes all arguments
        cmd = mock_run.call_args[0][0]
        assert "--log-group" in cmd
        assert "/test/log/group" in cmd
        assert "--session-id" in cmd
        assert "test-session-id" in cmd
        assert "--minutes" in cmd
        assert "180" in cmd
        assert "--profile" in cmd
        assert "myprofile" in cmd
        assert "--out" in cmd
        assert "/tmp/output.json" in cmd

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.subprocess.run')
    def test_execute_script1_failure(self, mock_run):
        """Test Script 1 execution failure."""
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["python", "-m", "script1"],
            stderr="Error: Invalid log group"
        )
        
        with pytest.raises(ScriptExecutionError) as exc_info:
            execute_script1(
                log_group="/invalid/log/group",
                session_id=None,
                minutes=180,
                output="/tmp/output.json",
                region="us-east-1",
                profile=None,
                output_dir="/tmp"
            )
        
        error_msg = str(exc_info.value)
        assert "Script 1" in error_msg
        assert "01_export_turns_from_app_logs.py" in error_msg
        assert "return code 1" in error_msg
        assert "Invalid log group" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.subprocess.run')
    def test_execute_script2_success(self, mock_run):
        """Test successful Script 2 execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        result = execute_script2(
            turns="/tmp/turns.json",
            otel_log_group="/test/otel/logs",
            region="us-west-2",
            pad_seconds=7200,
            output="/tmp/enriched.json",
            profile="test-profile"
        )
        
        assert result == "/tmp/enriched.json"
        mock_run.assert_called_once()
        
        # Verify command includes all arguments
        cmd = mock_run.call_args[0][0]
        assert "--turns" in cmd
        assert "/tmp/turns.json" in cmd
        assert "--otel-log-group" in cmd
        assert "/test/otel/logs" in cmd
        assert "--pad-seconds" in cmd
        assert "7200" in cmd

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.subprocess.run')
    def test_execute_script3_success(self, mock_run):
        """Test successful Script 3 execution."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        result = execute_script3(
            index="/tmp/turns.json",
            detail="/tmp/enriched.json",
            output="/tmp/merged.json",
            debug=True
        )
        
        assert result == "/tmp/merged.json"
        mock_run.assert_called_once()
        
        # Verify command includes all arguments
        cmd = mock_run.call_args[0][0]
        assert "--index" in cmd
        assert "/tmp/turns.json" in cmd
        assert "--detail" in cmd
        assert "/tmp/enriched.json" in cmd
        assert "--out" in cmd  # Bug fix: Changed from --output to --out
        assert "/tmp/merged.json" in cmd
        assert "--debug" in cmd


class TestArtifactValidation:
    """Tests for artifact validation functions."""

    def test_validate_script1_output_valid(self):
        """Test Script 1 output validation with valid schema."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "run_id": "test-run-123",
                "window": {"start": "2024-01-01T00:00:00Z", "end": "2024-01-01T01:00:00Z"},
                "turns": [
                    {"turn_id": "turn-1", "data": "test"}
                ]
            }, f)
            temp_file = f.name
        
        try:
            result = validate_script1_output(temp_file)
            assert result is True
        finally:
            Path(temp_file).unlink()

    def test_validate_script1_output_missing_run_id(self):
        """Test Script 1 output validation with missing run_id."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "window": {"start": "2024-01-01T00:00:00Z"},
                "turns": [{"turn_id": "turn-1"}]
            }, f)
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                validate_script1_output(temp_file)
            assert "run_id" in str(exc_info.value)
            assert "missing" in str(exc_info.value).lower()
        finally:
            Path(temp_file).unlink()

    def test_validate_script1_output_empty_turns(self):
        """Test Script 1 output validation with empty turns list.
        
        Bug fix: Empty turns now raises a warning instead of ValueError,
        since zero turns may be valid (no data in time window).
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "run_id": "test-run-123",
                "window": {"start": "2024-01-01T00:00:00Z"},
                "turns": []
            }, f)
            temp_file = f.name
        
        try:
            # Bug fix: Should now return True and issue a warning instead of raising ValueError
            import warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validate_script1_output(temp_file)
                assert result is True
                assert len(w) == 1
                assert "empty" in str(w[0].message).lower()
                assert "turns" in str(w[0].message)
        finally:
            Path(temp_file).unlink()

    def test_validate_script2_output_valid(self):
        """Test Script 2 output validation with valid schema."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "sessions": [{"session_id": "session-1"}],
                "enrich_stats": {"total": 1, "enriched": 1}
            }, f)
            temp_file = f.name
        
        try:
            result = validate_script2_output(temp_file)
            assert result is True
        finally:
            Path(temp_file).unlink()

    def test_validate_script3_output_valid(self):
        """Test Script 3 output validation with valid schema."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "turns_merged_normalized": [{"turn_id": "turn-1"}],
                "merge_stats": {"total": 1, "merged": 1}
            }, f)
            temp_file = f.name
        
        try:
            result = validate_script3_output(temp_file)
            assert result is True
        finally:
            Path(temp_file).unlink()

    def test_validate_invalid_json(self):
        """Test validation with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json {")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError) as exc_info:
                validate_script1_output(temp_file)
            assert "not valid JSON" in str(exc_info.value)
        finally:
            Path(temp_file).unlink()

    def test_validate_file_not_found(self):
        """Test validation with non-existent file."""
        with pytest.raises(ValueError) as exc_info:
            validate_script1_output("/nonexistent/file.json")
        assert "not found" in str(exc_info.value)


class TestPipelineExecution:
    """Tests for execute_pipeline function."""

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script3')
    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script2')
    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script1')
    def test_successful_pipeline_execution(self, mock_script1, mock_script2, mock_script3):
        """Test successful pipeline execution with all scripts completing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup mocks
            script1_output = f"{tmpdir}/01_session_turns.json"
            script2_output = f"{tmpdir}/02_session_enriched_runtime.json"
            script3_output = f"{tmpdir}/03_turns_merged_normalized.json"
            
            mock_script1.return_value = script1_output
            mock_script2.return_value = script2_output
            mock_script3.return_value = script3_output
            
            # Create mock output files
            with open(script1_output, 'w') as f:
                json.dump({"run_id": "test", "window": {}, "turns": [{"id": "1"}]}, f)
            with open(script2_output, 'w') as f:
                json.dump({"sessions": [], "enrich_stats": {}}, f)
            with open(script3_output, 'w') as f:
                json.dump({"turns_merged_normalized": [], "merge_stats": {}}, f)
            
            # Create config
            config = PipelineConfig(
                arn=ParsedARN("arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/test:v1", "us-east-1", "123456789012", "agent/test:v1"),
                runtime=RuntimeMetadata("runtime-123", "ACTIVE", {}),
                log_groups=DiscoveredLogGroups("/runtime/logs", "/otel/logs", "discovered"),
                region="us-east-1",
                profile=None,
                session_id=None,
                minutes=180,
                output_dir=tmpdir,
                pad_seconds=7200,
                debug=False,
                
            )
            
            # Execute pipeline
            result = execute_pipeline(config)
            
            # Verify result
            assert result.success is True
            assert result.error is None
            assert result.discovery_file == f"{tmpdir}/discovery.json"
            assert result.script1_output == script1_output
            assert result.script2_output == script2_output
            assert result.script3_output == script3_output
            
            # Verify discovery.json was created
            assert Path(result.discovery_file).exists()
            with open(result.discovery_file) as f:
                discovery = json.load(f)
                assert "arn" in discovery
                assert "runtime_metadata" in discovery
                assert "log_groups" in discovery
                assert "timestamp" in discovery

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script1')
    def test_pipeline_script1_failure(self, mock_script1):
        """Test pipeline execution with Script 1 failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup mock to raise error
            mock_script1.side_effect = ScriptExecutionError("Script 1 failed")
            
            # Create config
            config = PipelineConfig(
                arn=ParsedARN("arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/test:v1", "us-east-1", "123456789012", "agent/test:v1"),
                runtime=RuntimeMetadata("runtime-123", "ACTIVE", {}),
                log_groups=DiscoveredLogGroups("/runtime/logs", "/otel/logs", "discovered"),
                region="us-east-1",
                profile=None,
                session_id=None,
                minutes=180,
                output_dir=tmpdir,
                pad_seconds=7200,
                debug=False,
                
            )
            
            # Execute pipeline
            result = execute_pipeline(config)
            
            # Verify result
            assert result.success is False
            assert "Script 1 failed" in result.error
            # Note: script1_output path is set even on failure (for debugging)
            assert result.script1_output != ""

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script2')
    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script1')
    def test_pipeline_script2_failure(self, mock_script1, mock_script2):
        """Test pipeline execution with Script 2 failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup mocks
            script1_output = f"{tmpdir}/01_session_turns.json"
            mock_script1.return_value = script1_output
            mock_script2.side_effect = ScriptExecutionError("Script 2 failed")
            
            # Create Script 1 output
            with open(script1_output, 'w') as f:
                json.dump({"run_id": "test", "window": {}, "turns": [{"id": "1"}]}, f)
            
            # Create config
            config = PipelineConfig(
                arn=ParsedARN("arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/test:v1", "us-east-1", "123456789012", "agent/test:v1"),
                runtime=RuntimeMetadata("runtime-123", "ACTIVE", {}),
                log_groups=DiscoveredLogGroups("/runtime/logs", "/otel/logs", "discovered"),
                region="us-east-1",
                profile=None,
                session_id=None,
                minutes=180,
                output_dir=tmpdir,
                pad_seconds=7200,
                debug=False,
                
            )
            
            # Execute pipeline
            result = execute_pipeline(config)
            
            # Verify result
            assert result.success is False
            assert "Script 2 failed" in result.error
            assert result.script1_output == script1_output
            # Note: script2_output path is set even on failure (for debugging)
            assert result.script2_output != ""

    def test_pipeline_output_directory_creation(self):
        """Test that pipeline creates output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = f"{tmpdir}/nested/output/dir"
            
            with patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.execute_script1') as mock_script1:
                mock_script1.side_effect = ScriptExecutionError("Stop after directory creation")
                
                config = PipelineConfig(
                    arn=ParsedARN("arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/test:v1", "us-east-1", "123456789012", "agent/test:v1"),
                    runtime=RuntimeMetadata("runtime-123", "ACTIVE", {}),
                    log_groups=DiscoveredLogGroups("/runtime/logs", "/otel/logs", "discovered"),
                    region="us-east-1",
                    profile=None,
                    session_id=None,
                    minutes=180,
                    output_dir=output_dir,
                    pad_seconds=7200,
                    debug=False,
                    
                )
                
                execute_pipeline(config)
                
                # Verify directory was created
                assert Path(output_dir).exists()
                assert Path(output_dir).is_dir()
