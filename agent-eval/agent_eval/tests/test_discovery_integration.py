"""
Integration tests for log group discovery workflow.

Tests the complete end-to-end flow:
1. Script 1 discovers log groups and writes discovery.json
2. Wrapper reads discovery.json from raw/ directory
3. Wrapper includes discovery section in manifest.json
4. Run ID is stable (generated before discovery)
5. Backward compatibility (--log-group without discovery)
"""

import json
import pytest
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

# Import modules under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.agentcore_pipeline.export_agentcore_pipeline import (
    run_stage1,
    write_manifest,
    generate_run_id
)

# Import Script 1 using importlib (module name starts with number)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "script1",
    Path(__file__).parent.parent / "tools" / "agentcore_pipeline" / "01_export_turns_from_app_logs.py"
)
script1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script1)
discover_log_groups = script1.discover_log_groups


# Helper to create mock args that are JSON serializable
def create_mock_args(**overrides):
    """Create a mock args object with default values that can be JSON serialized."""
    class MockArgs:
        region = 'us-east-1'
        profile = None
        app_log_group = None
        app_log_group_prefix = None
        app_log_group_pattern = None
        trace_provider = 'xray'
        days = 30
        start_time = None
        end_time = None
        max_turns = None
        print_commands = False
    
    args = MockArgs()
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


class TestDiscoveryToManifestWorkflow:
    """Test end-to-end discovery workflow: discovery → discovery.json → wrapper → manifest."""
    
    def test_discovery_writes_json_wrapper_reads_includes_in_manifest(self, tmp_path):
        """Test complete workflow: discovery → write discovery.json → wrapper reads → manifest."""
        # Setup directories
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # Step 1: Script 1 discovers log groups and writes discovery.json
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/prod'},
                        {'logGroupName': '/aws/bedrock/agent/dev'},
                        {'logGroupName': '/aws/bedrock/agent/test'}
                    ]
                }
            ]
            
            discovery_result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=raw_dir
            )
        
        # Verify discovery.json was written
        discovery_path = raw_dir / 'discovery.json'
        assert discovery_path.exists()
        
        # Step 2: Wrapper reads discovery.json (simulated)
        with open(discovery_path, 'r') as f:
            loaded_discovery = json.load(f)
        
        assert loaded_discovery == discovery_result
        
        # Step 3: Wrapper writes manifest with discovery section
        manifest_path = tmp_path / 'manifest.json'
        
        mock_args = create_mock_args(app_log_group_prefix='/aws/bedrock/agent')
        
        write_manifest(
            manifest_path=manifest_path,
            run_id='test_run_123',
            args=mock_args,
            window={'start': '2024-01-01T00:00:00Z', 'end': '2024-01-31T23:59:59Z'},
            script_commands=[],
            output_files={'raw': [str(discovery_path)]},
            discovery_result=loaded_discovery
        )
        
        # Step 4: Verify manifest includes discovery section
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        assert 'discovery' in manifest
        assert manifest['discovery'] == discovery_result
        assert manifest['discovery']['search_criteria']['prefix'] == '/aws/bedrock/agent'
        assert manifest['discovery']['total_matched'] == 3
        assert manifest['discovery']['total_selected'] <= 3
    
    def test_manifest_includes_all_discovery_fields(self, tmp_path):
        """Verify manifest includes all required discovery fields."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # Create discovery result
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/agent1'},
                        {'logGroupName': '/aws/bedrock/agent/agent2'}
                    ]
                }
            ]
            
            discovery_result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=raw_dir
            )
        
        # Write manifest
        manifest_path = tmp_path / 'manifest.json'
        
        mock_args = create_mock_args(app_log_group_prefix='/aws/bedrock/agent')
        
        write_manifest(
            manifest_path=manifest_path,
            run_id='test_run_456',
            args=mock_args,
            window={'start': '2024-01-01T00:00:00Z', 'end': '2024-01-31T23:59:59Z'},
            script_commands=[],
            output_files={},
            discovery_result=discovery_result
        )
        
        # Verify all required fields in manifest discovery section
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        discovery = manifest['discovery']
        required_fields = [
            'search_criteria',
            'matched_groups',
            'selected_groups',
            'selection_reason',
            'total_matched',
            'total_selected'
        ]
        
        for field in required_fields:
            assert field in discovery, f"Missing required field: {field}"
        
        # Verify search_criteria structure
        assert 'prefix' in discovery['search_criteria']
        assert 'pattern' in discovery['search_criteria']
    
    def test_run_id_stable_generated_before_discovery(self, tmp_path):
        """Test that run_id is stable (generated before discovery)."""
        # Generate run_id with same inputs multiple times
        start_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 31, tzinfo=timezone.utc)
        
        app_inputs = {"log_group_prefix": "/aws/bedrock/agent"}
        trace_inputs = {"provider": "xray"}
        
        run_id_1 = generate_run_id(
            start_time=start_time,
            end_time=end_time,
            region='us-east-1',
            profile=None,
            app_inputs=app_inputs,
            trace_inputs=trace_inputs
        )
        
        run_id_2 = generate_run_id(
            start_time=start_time,
            end_time=end_time,
            region='us-east-1',
            profile=None,
            app_inputs=app_inputs,
            trace_inputs=trace_inputs
        )
        
        # Run IDs should be identical (deterministic)
        assert run_id_1 == run_id_2
        
        # Run ID should not contain discovery-specific information
        # (it's generated before discovery happens)
        assert 'discovery' not in run_id_1.lower()
        assert 'matched' not in run_id_1.lower()
        assert 'selected' not in run_id_1.lower()
    
    def test_backward_compatibility_log_group_without_discovery(self, tmp_path):
        """Test backward compatibility: --log-group without discovery."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # When using --log-group (not --log-group-prefix or --log-group-pattern),
        # no discovery.json should be written
        
        # Simulate wrapper behavior with --log-group
        manifest_path = tmp_path / 'manifest.json'
        
        mock_args = create_mock_args(app_log_group='/aws/bedrock/agent/specific-agent')
        
        # Write manifest without discovery_result
        write_manifest(
            manifest_path=manifest_path,
            run_id='test_run_backward_compat',
            args=mock_args,
            window={'start': '2024-01-01T00:00:00Z', 'end': '2024-01-31T23:59:59Z'},
            script_commands=[],
            output_files={},
            discovery_result=None  # No discovery
        )
        
        # Verify manifest does NOT include discovery section
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        assert 'discovery' not in manifest
        
        # Verify other fields are still present
        assert 'run_id' in manifest
        assert 'timestamp' in manifest
        assert 'cli_args' in manifest
        assert 'window' in manifest


class TestRunStage1Integration:
    """Test run_stage1() function integration with discovery."""
    
    def test_run_stage1_reads_discovery_json(self, tmp_path):
        """Test that run_stage1() reads discovery.json from raw/ directory."""
        # Setup
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # Create mock discovery.json
        discovery_data = {
            "search_criteria": {"prefix": "/aws/bedrock/agent", "pattern": None},
            "matched_groups": [
                "/aws/bedrock/agent/prod",
                "/aws/bedrock/agent/dev"
            ],
            "selected_groups": ["/aws/bedrock/agent/prod"],
            "selection_reason": "Selected top 1 of 2 matched groups",
            "total_matched": 2,
            "total_selected": 1,
            "scoring_details": {"single_match": False}
        }
        
        discovery_path = raw_dir / "discovery.json"
        with open(discovery_path, 'w') as f:
            json.dump(discovery_data, f, indent=2)
        
        mock_args = create_mock_args(app_log_group_prefix='/aws/bedrock/agent')
        
        paths = {"raw": raw_dir}
        script_dir = Path(__file__).parent.parent / "tools" / "agentcore_pipeline"
        
        # Mock logger
        import logging
        logger = logging.getLogger("test")
        
        # Mock run_script to simulate successful Stage 1
        with patch('tools.agentcore_pipeline.export_agentcore_pipeline.run_script') as mock_run_script:
            mock_run_script.return_value = {
                "status": "success",
                "exit_code": 0,
                "command": "mock_command"
            }
            
            # Call run_stage1
            stage1_result, discovery_result = run_stage1(
                args=mock_args,
                paths=paths,
                script_dir=script_dir,
                logger=logger
            )
        
        # Verify discovery_result was loaded
        assert discovery_result is not None
        assert discovery_result['search_criteria']['prefix'] == '/aws/bedrock/agent'
        assert discovery_result['total_matched'] == 2
        assert discovery_result['total_selected'] == 1
        assert len(discovery_result['selected_groups']) == 1
    
    def test_run_stage1_handles_missing_discovery_json(self, tmp_path):
        """Test that run_stage1() handles missing discovery.json gracefully."""
        # Setup
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # No discovery.json created
        
        mock_args = create_mock_args(app_log_group='/aws/bedrock/agent/specific')
        
        paths = {"raw": raw_dir}
        script_dir = Path(__file__).parent.parent / "tools" / "agentcore_pipeline"
        
        import logging
        logger = logging.getLogger("test")
        
        with patch('tools.agentcore_pipeline.export_agentcore_pipeline.run_script') as mock_run_script:
            mock_run_script.return_value = {
                "status": "success",
                "exit_code": 0,
                "command": "mock_command"
            }
            
            stage1_result, discovery_result = run_stage1(
                args=mock_args,
                paths=paths,
                script_dir=script_dir,
                logger=logger
            )
        
        # Verify discovery_result is None (no discovery.json)
        assert discovery_result is None
    
    def test_run_stage1_validates_discovery_json_schema(self, tmp_path):
        """Test that run_stage1() validates discovery.json schema."""
        # Setup
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        
        # Create invalid discovery.json (missing required fields)
        invalid_discovery = {
            "search_criteria": {"prefix": "/aws/bedrock/agent"},
            "matched_groups": ["/aws/bedrock/agent/prod"]
            # Missing: selected_groups, selection_reason, total_matched, total_selected
        }
        
        discovery_path = raw_dir / "discovery.json"
        with open(discovery_path, 'w') as f:
            json.dump(invalid_discovery, f)
        
        mock_args = create_mock_args(app_log_group_prefix='/aws/bedrock/agent')
        
        paths = {"raw": raw_dir}
        script_dir = Path(__file__).parent.parent / "tools" / "agentcore_pipeline"
        
        import logging
        logger = logging.getLogger("test")
        
        with patch('tools.agentcore_pipeline.export_agentcore_pipeline.run_script') as mock_run_script:
            mock_run_script.return_value = {
                "status": "success",
                "exit_code": 0,
                "command": "mock_command"
            }
            
            stage1_result, discovery_result = run_stage1(
                args=mock_args,
                paths=paths,
                script_dir=script_dir,
                logger=logger
            )
        
        # Verify discovery_result is None (invalid schema)
        assert discovery_result is None


class TestDiscoveryDeterminism:
    """Test deterministic behavior of discovery workflow."""
    
    def test_same_discovery_produces_same_manifest(self, tmp_path):
        """Test that same discovery inputs produce identical manifest discovery sections."""
        # Run discovery twice with same inputs
        results = []
        
        for i in range(2):
            raw_dir = tmp_path / f"raw_{i}"
            raw_dir.mkdir()
            
            with patch('boto3.Session') as mock_session:
                mock_client = Mock()
                mock_session.return_value.client.return_value = mock_client
                
                mock_paginator = Mock()
                mock_client.get_paginator.return_value = mock_paginator
                mock_paginator.paginate.return_value = [
                    {
                        'logGroups': [
                            {'logGroupName': '/aws/bedrock/agent/alpha'},
                            {'logGroupName': '/aws/bedrock/agent/beta'},
                            {'logGroupName': '/aws/bedrock/agent/gamma'}
                        ]
                    }
                ]
                
                discovery_result = discover_log_groups(
                    region='us-east-1',
                    prefix='/aws/bedrock/agent',
                    output_dir=raw_dir
                )
                
                results.append(discovery_result)
        
        # Results should be identical
        assert results[0] == results[1]
        
        # Selected groups should be in same order
        assert results[0]['selected_groups'] == results[1]['selected_groups']
        
        # Selection reason should be identical
        assert results[0]['selection_reason'] == results[1]['selection_reason']


class TestBackwardCompatibility:
    """Test backward compatibility with existing workflows."""
    
    def test_manifest_without_discovery_is_valid(self, tmp_path):
        """Test that manifest without discovery section is still valid."""
        manifest_path = tmp_path / 'manifest.json'
        
        mock_args = create_mock_args(app_log_group='/aws/bedrock/agent/specific')
        
        write_manifest(
            manifest_path=manifest_path,
            run_id='backward_compat_test',
            args=mock_args,
            window={'start': '2024-01-01T00:00:00Z', 'end': '2024-01-31T23:59:59Z'},
            script_commands=[],
            output_files={},
            discovery_result=None
        )
        
        # Verify manifest is valid JSON
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        # Verify required fields are present
        assert 'run_id' in manifest
        assert 'timestamp' in manifest
        assert 'cli_args' in manifest
        
        # Verify discovery is NOT present
        assert 'discovery' not in manifest
    
    def test_existing_workflows_unaffected(self, tmp_path):
        """Test that existing workflows without discovery continue to work."""
        # Simulate existing workflow: direct log group specification
        manifest_path = tmp_path / 'manifest.json'
        
        mock_args = create_mock_args(
            region='us-west-2',
            profile='production',
            app_log_group='/aws/lambda/my-agent-prod',
            days=7,
            max_turns=1000
        )
        
        write_manifest(
            manifest_path=manifest_path,
            run_id='existing_workflow_test',
            args=mock_args,
            window={'start': '2024-01-25T00:00:00Z', 'end': '2024-02-01T00:00:00Z'},
            script_commands=[
                {"stage": 1, "status": "success"},
                {"stage": 2, "status": "success"},
                {"stage": 3, "status": "success"}
            ],
            output_files={
                "raw": ["turns.json", "traces.json"],
                "merged": ["normalized_run.json"]
            },
            discovery_result=None
        )
        
        # Verify manifest structure matches existing format
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        assert manifest['run_id'] == 'existing_workflow_test'
        assert manifest['cli_args']['app_log_group'] == '/aws/lambda/my-agent-prod'
        assert 'discovery' not in manifest
        assert len(manifest['script_commands']) == 3
        assert 'raw' in manifest['output_files']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
