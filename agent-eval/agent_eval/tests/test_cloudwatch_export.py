"""
Tests for CloudWatch Logs Fixture Exporter.

These tests verify:
1. Log group discovery (prefix and pattern)
2. Pagination handling
3. Retry logic with exponential backoff + jitter
4. Output contract (Generic JSON events only)
5. Isolation (no adapter imports)
6. Error handling (credentials, throttling, empty results)
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from botocore.stub import Stubber

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import cloudwatch_logs_fixture_exporter


class TestLogGroupDiscovery:
    """Test log group discovery with prefix and pattern."""
    
    def test_discover_by_prefix(self):
        """Test log group discovery using prefix."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # Mock paginator
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/lambda/agent-1'},
                        {'logGroupName': '/aws/lambda/agent-2'},
                        {'logGroupName': '/aws/lambda/other'}
                    ]
                }
            ]
            
            result = cloudwatch_logs_fixture_exporter.discover_log_groups(prefix='/aws/lambda/agent')
            
            assert len(result) == 3
            assert '/aws/lambda/agent-1' in result
            assert '/aws/lambda/agent-2' in result
            mock_client.get_paginator.assert_called_once_with('describe_log_groups')
    
    def test_discover_by_pattern(self):
        """Test log group discovery using regex pattern."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {
                    'logGroups': [
                        {'logGroupName': '/aws/lambda/my-agent'},
                        {'logGroupName': '/aws/lambda/other-service'},
                        {'logGroupName': '/aws/ecs/agent-task'}
                    ]
                }
            ]
            
            result = cloudwatch_logs_fixture_exporter.discover_log_groups(pattern='.*agent.*')
            
            assert len(result) == 2
            assert '/aws/lambda/my-agent' in result
            assert '/aws/ecs/agent-task' in result
            assert '/aws/lambda/other-service' not in result
    
    def test_no_log_groups_found(self):
        """Test handling when no log groups match."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [{'logGroups': []}]
            
            result = cloudwatch_logs_fixture_exporter.discover_log_groups(prefix='/nonexistent')
            
            assert result == []


class TestCredentialsHandling:
    """Test AWS credentials error handling."""
    
    def test_no_credentials_error(self):
        """Test handling of missing AWS credentials."""
        with patch('boto3.Session') as mock_session:
            mock_session.return_value.client.side_effect = NoCredentialsError()
            
            with pytest.raises(NoCredentialsError) as exc_info:
                cloudwatch_extractor.discover_log_groups(prefix='/aws/lambda')
            
            assert 'AWS credentials not found' in str(exc_info.value)
    
    def test_partial_credentials_error(self):
        """Test handling of incomplete AWS credentials."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            mock_client.get_paginator.side_effect = PartialCredentialsError(
                provider='env',
                cred_var='AWS_SECRET_ACCESS_KEY'
            )
            
            with pytest.raises(PartialCredentialsError):
                cloudwatch_extractor.discover_log_groups(prefix='/aws/lambda')
    
    def test_expired_token_error(self):
        """Test handling of expired AWS credentials."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            error_response = {
                'Error': {
                    'Code': 'ExpiredTokenException',
                    'Message': 'Token expired'
                }
            }
            mock_client.get_paginator.side_effect = ClientError(
                error_response,
                'DescribeLogGroups'
            )
            
            with pytest.raises(ClientError) as exc_info:
                cloudwatch_extractor.discover_log_groups(prefix='/aws/lambda')
            
            assert 'ExpiredTokenException' in str(exc_info.value)


class TestThrottlingAndRetry:
    """Test retry logic with exponential backoff."""
    
    def test_throttling_with_retry_success(self):
        """Test successful retry after throttling."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # First call throttles, second succeeds
            throttle_error = ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'StartQuery'
            )
            mock_client.start_query.side_effect = [
                throttle_error,
                {'queryId': 'test-query-id'}
            ]
            
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': []
            }
            
            with patch('time.sleep'):  # Mock sleep to speed up test
                result = cloudwatch_extractor._query_cloudwatch_with_retry(
                    mock_client,
                    '/aws/lambda/test',
                    datetime.utcnow() - timedelta(days=1),
                    datetime.utcnow(),
                    None
                )
            
            assert result == []
            assert mock_client.start_query.call_count == 2
    
    def test_max_retries_exceeded(self):
        """Test failure after max retries."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            throttle_error = ClientError(
                {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
                'StartQuery'
            )
            mock_client.start_query.side_effect = throttle_error
            
            with patch('time.sleep'):
                with pytest.raises(ClientError):
                    cloudwatch_extractor._query_cloudwatch_with_retry(
                        mock_client,
                        '/aws/lambda/test',
                        datetime.utcnow() - timedelta(days=1),
                        datetime.utcnow(),
                        None
                    )
            
            assert mock_client.start_query.call_count == cloudwatch_extractor.MAX_RETRIES
    
    def test_jitter_adds_randomness(self):
        """Test that jitter adds randomness to retry delays."""
        delays = [cloudwatch_extractor._add_jitter(10.0) for _ in range(100)]
        
        # Jitter should produce values between 5.0 and 15.0
        assert all(5.0 <= d <= 15.0 for d in delays)
        # Should have some variance (not all the same)
        assert len(set(delays)) > 10


class TestPaginationGuardrails:
    """Test pagination limits and guardrails."""
    
    def test_max_results_warning(self):
        """Test warning when query returns max results."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_client.start_query.return_value = {'queryId': 'test-id'}
            
            # Return exactly 10000 results (max)
            mock_results = [{'field': '@timestamp', 'value': '2024-01-01'}] * 10000
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': mock_results
            }
            
            with patch('builtins.print') as mock_print:
                result = cloudwatch_extractor._query_cloudwatch_with_retry(
                    mock_client,
                    '/aws/lambda/test',
                    datetime.utcnow() - timedelta(days=1),
                    datetime.utcnow(),
                    None
                )
            
            assert len(result) == 10000
            # Check that warning was printed
            warning_calls = [call for call in mock_print.call_args_list 
                           if 'truncated' in str(call).lower() or 'max results' in str(call).lower()]
            assert len(warning_calls) > 0


class TestOutputContract:
    """Test Generic JSON output format."""
    
    def test_output_has_required_fields(self, tmp_path):
        """Test that exported file has required Generic JSON structure."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            # Mock discovery
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'logGroups': [{'logGroupName': '/aws/lambda/test'}]}
            ]
            
            # Mock query
            mock_client.start_query.return_value = {'queryId': 'test-id'}
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': [
                    [
                        {'field': '@timestamp', 'value': '2024-01-01 00:00:00.000'},
                        {'field': '@message', 'value': 'test message'},
                        {'field': '@logStream', 'value': 'test-stream'}
                    ]
                ]
            }
            
            output_dir = str(tmp_path)
            files = cloudwatch_extractor.export_cloudwatch_logs(
                log_group_name='/aws/lambda/test',
                days=1,
                output_dir=output_dir
            )
            
            assert len(files) == 1
            
            # Load and verify output
            with open(files[0], 'r') as f:
                data = json.load(f)
            
            # Check required top-level fields
            assert 'export_id' in data
            assert 'source' in data
            assert data['source'] == 'cloudwatch'
            assert 'window' in data
            assert 'log_groups' in data
            assert 'events' in data
            
            # Check events structure
            assert isinstance(data['events'], list)
            if data['events']:
                event = data['events'][0]
                assert 'timestamp' in event
                assert 'event_type' in event
                assert 'attributes' in event
                assert isinstance(event['attributes'], dict)
    
    def test_event_has_minimum_fields(self, tmp_path):
        """Test that each event has minimum required fields."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'logGroups': [{'logGroupName': '/aws/lambda/test'}]}
            ]
            
            mock_client.start_query.return_value = {'queryId': 'test-id'}
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': [
                    [
                        {'field': '@timestamp', 'value': '2024-01-01 00:00:00.000'},
                        {'field': '@message', 'value': 'plain text log'},
                        {'field': '@logStream', 'value': 'stream-1'}
                    ]
                ]
            }
            
            output_dir = str(tmp_path)
            files = cloudwatch_extractor.export_cloudwatch_logs(
                log_group_name='/aws/lambda/test',
                days=1,
                output_dir=output_dir
            )
            
            with open(files[0], 'r') as f:
                data = json.load(f)
            
            event = data['events'][0]
            
            # Minimum required fields
            assert 'timestamp' in event
            assert 'event_type' in event
            assert 'attributes' in event
            assert isinstance(event['attributes'], dict)
            
            # CloudWatch metadata preserved
            assert 'log_group' in event['attributes']
            assert 'log_stream' in event['attributes']
    
    def test_otel_fields_extracted(self, tmp_path):
        """Test OTEL fields are extracted from JSON messages."""
        otel_message = json.dumps({
            'traceId': 'trace-123',
            'spanId': 'span-456',
            'parentSpanId': 'span-parent',
            'sessionId': 'session-789',
            'body': {'message': 'OTEL log entry'}
        })
        
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'logGroups': [{'logGroupName': '/aws/lambda/test'}]}
            ]
            
            mock_client.start_query.return_value = {'queryId': 'test-id'}
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': [
                    [
                        {'field': '@timestamp', 'value': '2024-01-01 00:00:00.000'},
                        {'field': '@message', 'value': otel_message},
                        {'field': '@logStream', 'value': 'stream-1'}
                    ]
                ]
            }
            
            output_dir = str(tmp_path)
            files = cloudwatch_extractor.export_cloudwatch_logs(
                log_group_name='/aws/lambda/test',
                days=1,
                output_dir=output_dir
            )
            
            with open(files[0], 'r') as f:
                data = json.load(f)
            
            event = data['events'][0]
            
            # OTEL fields should be extracted
            assert event.get('trace_id') == 'trace-123'
            assert event.get('span_id') == 'span-456'
            assert event.get('parent_span_id') == 'span-parent'
            assert event.get('session_id') == 'session-789'
            assert 'text' in event


class TestIsolation:
    """Test that exporter doesn't import adapter modules."""
    
    def test_no_adapter_imports(self):
        """Verify exporter doesn't import adapter modules."""
        import importlib.util
        
        # Load the module
        spec = importlib.util.spec_from_file_location(
            "cloudwatch_extractor",
            Path(__file__).parent.parent / "tools" / "cloudwatch_extractor.py"
        )
        module = importlib.util.module_from_spec(spec)
        
        # Check imports
        import_lines = []
        with open(spec.origin, 'r') as f:
            for line in f:
                if line.strip().startswith(('import ', 'from ')):
                    import_lines.append(line.strip())
        
        # Should NOT import adapter
        adapter_imports = [line for line in import_lines if 'adapter' in line.lower()]
        assert len(adapter_imports) == 0, f"Found adapter imports: {adapter_imports}"
        
        # Should NOT import boto3 adapter-related modules
        forbidden = ['adapters.', 'generic_json.adapter']
        for line in import_lines:
            for forbidden_import in forbidden:
                assert forbidden_import not in line, f"Found forbidden import: {line}"


class TestEmptyResults:
    """Test handling of empty result sets."""
    
    def test_empty_results_creates_file(self, tmp_path):
        """Test that empty results still create an export file."""
        with patch('boto3.Session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client
            
            mock_paginator = Mock()
            mock_client.get_paginator.return_value = mock_paginator
            mock_paginator.paginate.return_value = [
                {'logGroups': [{'logGroupName': '/aws/lambda/test'}]}
            ]
            
            mock_client.start_query.return_value = {'queryId': 'test-id'}
            mock_client.get_query_results.return_value = {
                'status': 'Complete',
                'results': []  # Empty results
            }
            
            output_dir = str(tmp_path)
            files = cloudwatch_extractor.export_cloudwatch_logs(
                log_group_name='/aws/lambda/test',
                days=1,
                output_dir=output_dir
            )
            
            assert len(files) == 1
            
            with open(files[0], 'r') as f:
                data = json.load(f)
            
            assert data['total_events'] == 0
            assert data['events'] == []


class TestDeterministicExportId:
    """Test deterministic export ID generation."""
    
    def test_same_params_same_id(self):
        """Test that same parameters produce same export ID."""
        log_groups = ['/aws/lambda/test']
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        filter_pattern = 'ERROR'
        
        id1 = cloudwatch_extractor._generate_export_id(log_groups, start, end, filter_pattern)
        id2 = cloudwatch_extractor._generate_export_id(log_groups, start, end, filter_pattern)
        
        assert id1 == id2
    
    def test_different_params_different_id(self):
        """Test that different parameters produce different export IDs."""
        log_groups = ['/aws/lambda/test']
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 31)
        
        id1 = cloudwatch_extractor._generate_export_id(log_groups, start, end, None)
        id2 = cloudwatch_extractor._generate_export_id(log_groups, start, end, 'ERROR')
        
        assert id1 != id2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
