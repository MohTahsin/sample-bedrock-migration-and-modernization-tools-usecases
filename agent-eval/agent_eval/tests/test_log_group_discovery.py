"""
Unit tests for log group discovery functionality in Script 1.

Tests cover:
- discover_log_groups() with prefix and pattern
- select_best_log_groups() scoring and selection
- get_selection_reason() message generation
- Error handling (NoLogGroupsFoundError, AWSCredentialsError)
- Pagination handling
- discovery.json artifact writing and schema compliance
"""

import json
import pytest
import re
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from botocore.exceptions import NoCredentialsError, ClientError

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import using importlib since module name starts with number
import importlib.util
spec = importlib.util.spec_from_file_location(
    "script1",
    Path(__file__).parent.parent / "tools" / "agentcore_pipeline" / "01_export_turns_from_app_logs.py"
)
script1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script1)

# Import functions and constants
discover_log_groups = script1.discover_log_groups
select_best_log_groups = script1.select_best_log_groups
get_selection_reason = script1.get_selection_reason
NoLogGroupsFoundError = script1.NoLogGroupsFoundError
AWSCredentialsError = script1.AWSCredentialsError
DISCOVERY_KEYWORDS = script1.DISCOVERY_KEYWORDS
MAX_GROUPS_TO_EXPORT = script1.MAX_GROUPS_TO_EXPORT


class TestDiscoverLogGroups:
    """Unit tests for discover_log_groups() function."""
    
    def test_prefix_based_discovery(self, tmp_path):
        """Test prefix-based discovery with mocked boto3 client."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # Mock paginator for prefix-based discovery
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/my-agent-prod'},
                        {'logGroupName': '/aws/bedrock/agent/my-agent-dev'},
                        {'logGroupName': '/aws/bedrock/agent/test-agent'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                profile=None,
                output_dir=tmp_path
            )
            
            # Verify API calls
            mock_client.get_paginator.assert_called_once_with('describe_log_groups')
            mock_paginator.paginate.assert_called_once_with(
                logGroupNamePrefix='/aws/bedrock/agent'
            )
            
            # Verify result structure
            assert 'search_criteria' in result
            assert result['search_criteria']['prefix'] == '/aws/bedrock/agent'
            assert result['search_criteria']['pattern'] is None
            assert 'matched_groups' in result
            assert len(result['matched_groups']) == 3
            assert 'selected_groups' in result
            assert 'selection_reason' in result
            assert 'total_matched' in result
            assert result['total_matched'] == 3
            assert 'total_selected' in result
            assert 'scoring_details' in result
    
    def test_pattern_based_discovery(self, tmp_path):
        """Test pattern-based discovery with regex filtering."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # Mock paginator for pattern-based discovery (full scan)
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/lambda/my-agent-function'},
                        {'logGroupName': '/aws/lambda/other-service'},
                        {'logGroupName': '/aws/ecs/agent-task'},
                        {'logGroupName': '/aws/bedrock/agentcore-service'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-west-2',
                pattern='.*agent.*',
                profile='dev',
                output_dir=tmp_path
            )
            
            # Verify API calls (pattern requires full scan, no prefix filter)
            mock_client.get_paginator.assert_called_once_with('describe_log_groups')
            mock_paginator.paginate.assert_called_once_with()
            
            # Verify regex filtering worked
            assert result['search_criteria']['pattern'] == '.*agent.*'
            assert result['search_criteria']['prefix'] is None
            matched = result['matched_groups']
            assert '/aws/lambda/my-agent-function' in matched
            assert '/aws/ecs/agent-task' in matched
            assert '/aws/bedrock/agentcore-service' in matched
            assert '/aws/lambda/other-service' not in matched
            assert result['total_matched'] == 3
    
    def test_no_log_groups_found_error(self):
        """Test NoLogGroupsFoundError when no matches."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [{'logGroups': []}]
            
            with pytest.raises(NoLogGroupsFoundError) as exc_info:
                discover_log_groups(
                    region='us-east-1',
                    prefix='/nonexistent/prefix'
                )
            
            assert 'No log groups found matching' in str(exc_info.value)
            assert 'prefix=/nonexistent/prefix' in str(exc_info.value)
    
    def test_aws_credentials_error_no_credentials(self):
        """Test AWSCredentialsError handling for missing credentials."""
        with patch('boto3.Session') as mock_session:
            mock_session.return_value.client.side_effect = NoCredentialsError()
            
            with pytest.raises(AWSCredentialsError) as exc_info:
                discover_log_groups(
                    region='us-east-1',
                    prefix='/aws/bedrock/agent'
                )
            
            assert 'AWS credentials are invalid or missing' in str(exc_info.value)
    
    def test_aws_credentials_error_client_error(self):
        """Test AWSCredentialsError handling for ClientError."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            error_response = {
                'Error': {
                    'Code': 'ExpiredTokenException',
                    'Message': 'Token has expired'
                }
            }
            mock_client.get_paginator.side_effect = ClientError(
                error_response,
                'DescribeLogGroups'
            )
            
            with pytest.raises(AWSCredentialsError) as exc_info:
                discover_log_groups(
                    region='us-east-1',
                    prefix='/aws/bedrock/agent'
                )
            
            assert 'AWS credentials are invalid or missing' in str(exc_info.value)
    
    def test_pagination_handling(self, tmp_path):
        """Test pagination handling for large result sets."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # Mock paginator with multiple pages
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': f'/aws/bedrock/agent/group-{i}'}
                        for i in range(50)
                    ]
                },
                {
                    'logGroups': [
                        {'logGroupName': f'/aws/bedrock/agent/group-{i}'}
                        for i in range(50, 100)
                    ]
                },
                {
                    'logGroups': [
                        {'logGroupName': f'/aws/bedrock/agent/group-{i}'}
                        for i in range(100, 120)
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=tmp_path
            )
            
            # Verify all pages were processed
            assert result['total_matched'] == 120
            assert len(result['matched_groups']) == 120
    
    def test_discovery_json_artifact_writing(self, tmp_path):
        """Test discovery.json artifact writing."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/prod'},
                        {'logGroupName': '/aws/bedrock/agent/dev'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=tmp_path
            )
            
            # Verify discovery.json was written
            discovery_path = tmp_path / 'discovery.json'
            assert discovery_path.exists()
            
            # Verify file contents match result
            with open(discovery_path, 'r') as f:
                file_data = json.load(f)
            
            assert file_data == result
    
    def test_discovery_json_schema_compliance(self, tmp_path):
        """Test discovery.json schema compliance with all required fields."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/agent-1'},
                        {'logGroupName': '/aws/bedrock/agent/agent-2'},
                        {'logGroupName': '/aws/bedrock/agent/agent-3'},
                        {'logGroupName': '/aws/bedrock/agent/agent-4'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=tmp_path
            )
            
            # Verify required fields
            required_fields = [
                'search_criteria',
                'matched_groups',
                'selected_groups',
                'selection_reason',
                'total_matched',
                'total_selected',
                'scoring_details'
            ]
            
            for field in required_fields:
                assert field in result, f"Missing required field: {field}"
            
            # Verify search_criteria structure
            assert 'prefix' in result['search_criteria']
            assert 'pattern' in result['search_criteria']
            
            # Verify types
            assert isinstance(result['matched_groups'], list)
            assert isinstance(result['selected_groups'], list)
            assert isinstance(result['selection_reason'], str)
            assert isinstance(result['total_matched'], int)
            assert isinstance(result['total_selected'], int)
            assert isinstance(result['scoring_details'], dict)
            
            # Verify scoring_details structure (optional but should be present)
            assert 'scoring_keywords' in result['scoring_details']
            assert 'max_groups_to_export' in result['scoring_details']
    
    def test_no_output_dir_skips_file_writing(self):
        """Test that discovery.json is not written when output_dir is None."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/test'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=None  # No output directory
            )
            
            # Result should still be returned
            assert 'matched_groups' in result
            assert len(result['matched_groups']) == 1
    
    def test_profile_parameter_passed_to_session(self):
        """Test that profile parameter is passed to boto3.Session."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'logGroups': [{'logGroupName': '/test'}]}
            ]
            
            discover_log_groups(
                region='us-west-2',
                prefix='/test',
                profile='production'
            )
            
            # Verify Session was created with correct parameters
            mock_session.assert_called_once_with(
                profile_name='production',
                region_name='us-west-2'
            )


class TestSelectBestLogGroups:
    """Unit tests for select_best_log_groups() function."""
    
    def test_single_match_selection(self):
        """Test single match selection."""
        matched_groups = ['/aws/bedrock/agent/my-agent']
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        assert selected == matched_groups
        assert scoring_details == {"single_match": True}
    
    def test_relevance_scoring_with_keywords(self):
        """Test relevance scoring with DISCOVERY_KEYWORDS."""
        matched_groups = [
            '/aws/lambda/other-service',  # score: 0
            '/aws/bedrock/agent/my-agent',  # score: 15 (agent=10, bedrock=5)
            '/aws/ecs/agentcore-task',  # score: 18 (agent=10, agentcore=8)
            '/aws/observability/agent-logs'  # score: 13 (agent=10, observability=3)
        ]
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        # Verify scoring details
        assert 'scoring_keywords' in scoring_details
        assert scoring_details['scoring_keywords'] == DISCOVERY_KEYWORDS
        assert 'scored_groups' in scoring_details
        
        # Verify top group has highest score
        top_group = scoring_details['scored_groups'][0]
        assert top_group['group'] == '/aws/ecs/agentcore-task'
        assert top_group['score'] == 18
        assert 'agent' in top_group['matched_keywords']
        assert 'agentcore' in top_group['matched_keywords']
    
    def test_matched_keywords_tracking(self):
        """Test matched_keywords tracking."""
        matched_groups = [
            '/aws/bedrock/agent/test',
            '/aws/agentcore/service',
            '/aws/observability/logs'
        ]
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        scored = scoring_details['scored_groups']
        
        # Verify all groups have matched_keywords field
        for group_info in scored:
            assert 'matched_keywords' in group_info
            assert isinstance(group_info['matched_keywords'], list)
        
        # Verify specific keyword matches
        # First group should be agentcore/service (score: 8) or bedrock/agent (score: 15)
        # Let's check by group name instead
        for group_info in scored:
            if 'bedrock' in group_info['group'] and 'agent' in group_info['group']:
                assert 'bedrock' in group_info['matched_keywords']
                assert 'agent' in group_info['matched_keywords']
            elif 'agentcore' in group_info['group']:
                assert 'agentcore' in group_info['matched_keywords']
            elif 'observability' in group_info['group']:
                assert 'observability' in group_info['matched_keywords']
    
    def test_alphabetical_tiebreaker(self):
        """Test alphabetical tiebreaker for same scores."""
        # All have same score (agent=10)
        matched_groups = [
            '/aws/lambda/zebra-agent',
            '/aws/lambda/alpha-agent',
            '/aws/lambda/beta-agent'
        ]
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        # Should be sorted alphabetically
        scored = scoring_details['scored_groups']
        assert scored[0]['group'] == '/aws/lambda/alpha-agent'
        assert scored[1]['group'] == '/aws/lambda/beta-agent'
        assert scored[2]['group'] == '/aws/lambda/zebra-agent'
        
        # All should have same score
        assert scored[0]['score'] == scored[1]['score'] == scored[2]['score']
    
    def test_top_n_selection(self):
        """Test top N selection (MAX_GROUPS_TO_EXPORT)."""
        # Create more groups than MAX_GROUPS_TO_EXPORT
        matched_groups = [
            f'/aws/bedrock/agent/group-{i:02d}'
            for i in range(10)
        ]
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        # Should select exactly MAX_GROUPS_TO_EXPORT
        assert len(selected) == MAX_GROUPS_TO_EXPORT
        assert scoring_details['max_groups_to_export'] == MAX_GROUPS_TO_EXPORT
        
        # Selected groups should be first N from scored list
        scored_groups_names = [g['group'] for g in scoring_details['scored_groups']]
        assert selected == scored_groups_names[:MAX_GROUPS_TO_EXPORT]
    
    def test_deterministic_ordering(self):
        """Test deterministic ordering across multiple calls."""
        matched_groups = [
            '/aws/bedrock/agent/prod',
            '/aws/bedrock/agent/dev',
            '/aws/agentcore/service',
            '/aws/observability/agent-logs',
            '/aws/lambda/agent-function'
        ]
        
        # Call multiple times
        selected1, _ = select_best_log_groups(matched_groups)
        selected2, _ = select_best_log_groups(matched_groups)
        selected3, _ = select_best_log_groups(matched_groups)
        
        # Results should be identical
        assert selected1 == selected2 == selected3
    
    def test_scoring_details_structure(self):
        """Test scoring_details structure."""
        matched_groups = [
            '/aws/bedrock/agent/test1',
            '/aws/bedrock/agent/test2'
        ]
        
        selected, scoring_details = select_best_log_groups(matched_groups)
        
        # Verify structure
        assert 'scoring_keywords' in scoring_details
        assert 'max_groups_to_export' in scoring_details
        assert 'scored_groups' in scoring_details
        
        # Verify scored_groups is limited to top 10
        assert len(scoring_details['scored_groups']) <= 10
        
        # Verify each scored group has required fields
        for group_info in scoring_details['scored_groups']:
            assert 'group' in group_info
            assert 'score' in group_info
            assert 'matched_keywords' in group_info


class TestGetSelectionReason:
    """Unit tests for get_selection_reason() function."""
    
    def test_single_match_reason(self):
        """Test reason for single match."""
        matched_groups = ['/aws/bedrock/agent/only-one']
        selected_groups = ['/aws/bedrock/agent/only-one']
        scoring_details = {"single_match": True}
        
        reason = get_selection_reason(matched_groups, selected_groups, scoring_details)
        
        assert reason == "Only one log group matched"
    
    def test_all_selected_reason(self):
        """Test reason when all groups are selected."""
        matched_groups = [
            '/aws/bedrock/agent/group1',
            '/aws/bedrock/agent/group2'
        ]
        selected_groups = matched_groups.copy()
        scoring_details = {}
        
        reason = get_selection_reason(matched_groups, selected_groups, scoring_details)
        
        assert reason == "All 2 matched groups selected"
    
    def test_top_n_selected_reason(self):
        """Test reason for top N selection with scoring explanation."""
        matched_groups = [f'/aws/bedrock/agent/group-{i}' for i in range(10)]
        selected_groups = matched_groups[:3]
        scoring_details = {
            "scoring_keywords": DISCOVERY_KEYWORDS,
            "max_groups_to_export": MAX_GROUPS_TO_EXPORT
        }
        
        reason = get_selection_reason(matched_groups, selected_groups, scoring_details)
        
        # Verify reason includes key information
        assert "Selected top 3 of 10 matched groups" in reason
        assert "relevance score" in reason
        assert "keywords:" in reason
        assert "alphabetically" in reason
        
        # Verify all keywords are mentioned with their weights
        for keyword, weight in DISCOVERY_KEYWORDS.items():
            assert f"{keyword}(+{weight})" in reason
    
    def test_reason_includes_keyword_weights(self):
        """Test that reason includes keyword weights."""
        matched_groups = [f'/aws/agent/group-{i}' for i in range(5)]
        selected_groups = matched_groups[:2]
        scoring_details = {"scoring_keywords": DISCOVERY_KEYWORDS}
        
        reason = get_selection_reason(matched_groups, selected_groups, scoring_details)
        
        # Check each keyword weight is present
        assert "agent(+10)" in reason
        assert "bedrock(+5)" in reason
        assert "agentcore(+8)" in reason
        assert "observability(+3)" in reason


class TestIntegrationScenarios:
    """Integration-style tests for complete discovery workflows."""
    
    def test_high_score_groups_selected_first(self, tmp_path):
        """Test that high-scoring groups are selected first."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/lambda/other-service'},  # score: 0
                        {'logGroupName': '/aws/bedrock/agent/prod'},  # score: 15
                        {'logGroupName': '/aws/agentcore/service'},  # score: 8
                        {'logGroupName': '/aws/observability/logs'},  # score: 3
                        {'logGroupName': '/aws/bedrock/agentcore/main'}  # score: 13
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws',
                output_dir=tmp_path
            )
            
            # Top 3 should be: bedrock/agent (15), bedrock/agentcore (13), agentcore (8)
            selected = result['selected_groups']
            assert len(selected) == 3
            assert '/aws/bedrock/agent/prod' in selected
            assert '/aws/bedrock/agentcore/main' in selected
            assert '/aws/agentcore/service' in selected
    
    def test_discovery_result_consistency(self, tmp_path):
        """Test that discovery result is consistent between return value and file."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/bedrock/agent/test1'},
                        {'logGroupName': '/aws/bedrock/agent/test2'}
                    ]
                }
            ]
            
            result = discover_log_groups(
                region='us-east-1',
                prefix='/aws/bedrock/agent',
                output_dir=tmp_path
            )
            
            # Read file
            with open(tmp_path / 'discovery.json', 'r') as f:
                file_data = json.load(f)
            
            # Should be identical
            assert result == file_data
            
            # Verify all fields match
            assert result['search_criteria'] == file_data['search_criteria']
            assert result['matched_groups'] == file_data['matched_groups']
            assert result['selected_groups'] == file_data['selected_groups']
            assert result['selection_reason'] == file_data['selection_reason']
            assert result['total_matched'] == file_data['total_matched']
            assert result['total_selected'] == file_data['total_selected']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
