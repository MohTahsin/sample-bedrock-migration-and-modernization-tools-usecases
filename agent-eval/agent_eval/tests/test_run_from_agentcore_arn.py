"""
Unit tests for run_from_agentcore_arn module.

This test module covers the core functionality of the AgentCore ARN-based
trace extraction wrapper, including ARN parsing, runtime metadata resolution,
log group discovery, and pipeline execution.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from botocore.exceptions import ClientError, NoCredentialsError
from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import (
    LogGroupNotFoundError,
    RuntimeNotFoundError,
    parse_agentcore_arn,
    get_runtime_metadata,
    ParsedARN,
    RuntimeMetadata,
)


class TestLogGroupNotFoundError:
    """Tests for LogGroupNotFoundError exception class."""

    def test_exception_can_be_raised(self):
        """Test that LogGroupNotFoundError can be raised with a message."""
        with pytest.raises(LogGroupNotFoundError) as exc_info:
            raise LogGroupNotFoundError("Runtime logs not found with prefix: /aws/bedrock-agentcore/runtimes/abc-123-")
        
        assert "Runtime logs not found" in str(exc_info.value)
        assert "/aws/bedrock-agentcore/runtimes/abc-123-" in str(exc_info.value)

    def test_exception_inherits_from_exception(self):
        """Test that LogGroupNotFoundError inherits from Exception."""
        assert issubclass(LogGroupNotFoundError, Exception)

    def test_exception_can_be_caught_as_exception(self):
        """Test that LogGroupNotFoundError can be caught as a generic Exception."""
        with pytest.raises(Exception):
            raise LogGroupNotFoundError("Test error message")

    def test_exception_with_empty_message(self):
        """Test that LogGroupNotFoundError can be raised with an empty message."""
        with pytest.raises(LogGroupNotFoundError):
            raise LogGroupNotFoundError()

    def test_exception_message_formatting(self):
        """Test that LogGroupNotFoundError preserves message formatting."""
        error_msg = "OTEL logs not found with prefix: /aws/bedrock-agentcore/runtimes/xyz-456-\nVerify runtime has logging enabled"
        
        with pytest.raises(LogGroupNotFoundError) as exc_info:
            raise LogGroupNotFoundError(error_msg)
        
        assert str(exc_info.value) == error_msg


class TestParseAgentCoreARN:
    """Tests for parse_agentcore_arn function covering tasks 2.2.1 through 2.2.6."""

    def test_valid_arn_with_typical_values(self):
        """Task 2.2.1: Test valid ARN with typical values."""
        arn = "arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc-def-123:v1"

        result = parse_agentcore_arn(arn)

        assert isinstance(result, ParsedARN)
        assert result.raw_arn == arn
        assert result.region == "us-east-1"
        assert result.account_id == "123456789012"
        assert result.resource_id == "agent/abc-def-123:v1"

    def test_invalid_arn_prefix(self):
        """Task 2.2.2: Test invalid ARN prefix."""
        invalid_arns = [
            "arn:aws:bedrock:us-east-1:123456789012:agent/abc-def-123:v1",  # Wrong service
            "arn:aws:agentcore:us-east-1:123456789012:agent/abc-def-123:v1",  # Missing bedrock prefix
            "invalid-arn:us-east-1:123456789012:agent/abc-def-123:v1",  # Completely wrong prefix
            "aws:bedrock-agentcore:us-east-1:123456789012:agent/abc-def-123:v1",  # Missing arn prefix
        ]

        for invalid_arn in invalid_arns:
            with pytest.raises(ValueError) as exc_info:
                parse_agentcore_arn(invalid_arn)
            assert "Invalid ARN prefix" in str(exc_info.value)

    def test_arn_with_missing_components(self):
        """Task 2.2.3: Test ARN with missing components."""
        invalid_arns = [
            "arn:aws:bedrock-agentcore:",  # Only prefix
            "arn:aws:bedrock-agentcore:us-east-1",  # Missing account and resource
            "arn:aws:bedrock-agentcore:us-east-1:123456789012",  # Missing resource
            "arn:aws:bedrock-agentcore:us-east-1:123456789012:",  # Empty resource
        ]

        for invalid_arn in invalid_arns:
            with pytest.raises(ValueError) as exc_info:
                parse_agentcore_arn(invalid_arn)
            # Should raise error about insufficient components or empty resource
            assert "Invalid ARN format" in str(exc_info.value) or "component" in str(exc_info.value).lower()

    def test_arn_with_invalid_account_id_format(self):
        """Task 2.2.4: Test ARN with invalid account ID format (not 12 digits)."""
        invalid_arns = [
            "arn:aws:bedrock-agentcore:us-east-1:12345:agent/abc-def-123:v1",  # Too short
            "arn:aws:bedrock-agentcore:us-east-1:1234567890123:agent/abc-def-123:v1",  # Too long
            "arn:aws:bedrock-agentcore:us-east-1:abc123456789:agent/abc-def-123:v1",  # Contains letters
            "arn:aws:bedrock-agentcore:us-east-1:12345678901a:agent/abc-def-123:v1",  # Contains letter
            "arn:aws:bedrock-agentcore:us-east-1::agent/abc-def-123:v1",  # Empty account ID
        ]

        for invalid_arn in invalid_arns:
            with pytest.raises(ValueError) as exc_info:
                parse_agentcore_arn(invalid_arn)
            assert "account" in str(exc_info.value).lower()

    def test_empty_string_and_none_inputs(self):
        """Task 2.2.5: Test empty string and None inputs."""
        # Test empty string
        with pytest.raises(ValueError) as exc_info:
            parse_agentcore_arn("")
        assert "cannot be None or empty" in str(exc_info.value)

        # Test None
        with pytest.raises(ValueError) as exc_info:
            parse_agentcore_arn(None)
        assert "cannot be None or empty" in str(exc_info.value)

    def test_arn_with_extra_components_forward_compatibility(self):
        """Task 2.2.6: Test ARN with extra components (forward compatibility)."""
        # ARN with extra colons in resource ID should be preserved
        arn_with_extra = "arn:aws:bedrock-agentcore:us-west-2:987654321098:agent/xyz-789:v2:extra:components"

        result = parse_agentcore_arn(arn_with_extra)

        assert result.raw_arn == arn_with_extra
        assert result.region == "us-west-2"
        assert result.account_id == "987654321098"
        # Resource ID should preserve all components after the 5th colon
        assert result.resource_id == "agent/xyz-789:v2:extra:components"

    def test_arn_with_different_regions(self):
        """Additional test: Verify ARN parsing works with different AWS regions."""
        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]

        for region in regions:
            arn = f"arn:aws:bedrock-agentcore:{region}:123456789012:agent/test-id:v1"
            result = parse_agentcore_arn(arn)
            assert result.region == region

    def test_arn_preserves_raw_arn(self):
        """Additional test: Verify that raw_arn is always preserved exactly."""
        test_arns = [
            "arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/simple:v1",
            "arn:aws:bedrock-agentcore:eu-west-1:999888777666:agent/complex-id-123:v2",
            "arn:aws:bedrock-agentcore:ap-south-1:111222333444:agent/test:v1:extra",
        ]

        for arn in test_arns:
            result = parse_agentcore_arn(arn)
            assert result.raw_arn == arn



class TestGetRuntimeMetadata:
    """Tests for get_runtime_metadata function covering tasks 3.2.1 through 3.2.5."""

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_successful_api_response(self, mock_session):
        """Task 3.2.1: Test successful API response (mocked)."""
        # Setup mock
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        mock_response = {
            'agentRuntimeId': 'test-runtime-id-123',
            'status': 'ACTIVE',
            'agentId': 'agent-123',
            'agentVersion': 'v1',
            'otherField': 'some-value'
        }
        mock_client.get_agent_runtime.return_value = mock_response

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc:v1",
            region="us-east-1",
            account_id="123456789012",
            resource_id="agent/abc:v1"
        )

        # Call function
        result = get_runtime_metadata(arn, region="us-east-1", profile=None)

        # Verify result
        assert isinstance(result, RuntimeMetadata)
        assert result.agent_runtime_id == 'test-runtime-id-123'
        assert result.status == 'ACTIVE'
        assert result.raw_response == mock_response

        # Verify boto3 calls
        mock_session.assert_called_once_with(region_name="us-east-1", profile_name=None)
        mock_session.return_value.client.assert_called_once_with('bedrock-agentcore-control')
        mock_client.get_agent_runtime.assert_called_once_with(
            agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc:v1"
        )

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_successful_api_response_with_profile(self, mock_session):
        """Task 3.2.5: Test with different AWS profiles."""
        # Setup mock
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        mock_response = {
            'agentRuntimeId': 'runtime-with-profile',
            'status': 'ACTIVE'
        }
        mock_client.get_agent_runtime.return_value = mock_response

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-west-2:987654321098:agent/xyz:v2",
            region="us-west-2",
            account_id="987654321098",
            resource_id="agent/xyz:v2"
        )

        # Call function with profile
        result = get_runtime_metadata(arn, region="us-west-2", profile="myprofile")

        # Verify result
        assert result.agent_runtime_id == 'runtime-with-profile'
        assert result.status == 'ACTIVE'

        # Verify boto3 session was created with profile
        mock_session.assert_called_once_with(region_name="us-west-2", profile_name="myprofile")

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_resource_not_found_exception_handling(self, mock_session):
        """Task 3.2.2: Test ResourceNotFoundException handling."""
        # Setup mock to raise ResourceNotFoundException
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        error_response = {
            'Error': {
                'Code': 'ResourceNotFoundException',
                'Message': 'Runtime not found'
            }
        }
        mock_client.get_agent_runtime.side_effect = ClientError(error_response, 'GetAgentRuntime')

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/nonexistent:v1",
            region="us-east-1",
            account_id="123456789012",
            resource_id="agent/nonexistent:v1"
        )

        # Call function and expect RuntimeNotFoundError
        with pytest.raises(RuntimeNotFoundError) as exc_info:
            get_runtime_metadata(arn, region="us-east-1")

        # Verify error message contains helpful information
        error_msg = str(exc_info.value)
        assert "Runtime not found" in error_msg
        assert arn.raw_arn in error_msg
        assert "us-east-1" in error_msg
        assert "Troubleshooting" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_no_credentials_error_handling(self, mock_session):
        """Task 3.2.3: Test NoCredentialsError handling."""
        # Setup mock to raise NoCredentialsError
        mock_session.side_effect = NoCredentialsError()

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc:v1",
            region="us-east-1",
            account_id="123456789012",
            resource_id="agent/abc:v1"
        )

        # Call function and expect RuntimeError (wrapping NoCredentialsError)
        with pytest.raises(RuntimeError) as exc_info:
            get_runtime_metadata(arn, region="us-east-1")

        # Verify error message contains setup instructions
        error_msg = str(exc_info.value)
        assert "AWS credentials not found" in error_msg
        assert "aws configure" in error_msg
        assert "AWS_ACCESS_KEY_ID" in error_msg
        assert arn.raw_arn in error_msg
        
        # Verify the original exception is chained
        assert isinstance(exc_info.value.__cause__, NoCredentialsError)

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_network_error_handling(self, mock_session):
        """Task 3.2.4: Test network error handling (generic ClientError)."""
        # Setup mock to raise generic ClientError (network/permission error)
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        error_response = {
            'Error': {
                'Code': 'ServiceUnavailable',
                'Message': 'Service temporarily unavailable'
            }
        }
        mock_client.get_agent_runtime.side_effect = ClientError(error_response, 'GetAgentRuntime')

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:eu-west-1:111222333444:agent/test:v1",
            region="eu-west-1",
            account_id="111222333444",
            resource_id="agent/test:v1"
        )

        # Call function and expect ClientError
        with pytest.raises(ClientError) as exc_info:
            get_runtime_metadata(arn, region="eu-west-1")

        # Verify error message contains details
        error_msg = str(exc_info.value)
        assert "Failed to get runtime metadata" in error_msg or "ServiceUnavailable" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_missing_agent_runtime_id_in_response(self, mock_session):
        """Additional test: Handle malformed API response missing agentRuntimeId."""
        # Setup mock with incomplete response
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        # Response missing agentRuntimeId field
        mock_response = {
            'status': 'ACTIVE',
            'agentId': 'agent-123'
        }
        mock_client.get_agent_runtime.return_value = mock_response

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc:v1",
            region="us-east-1",
            account_id="123456789012",
            resource_id="agent/abc:v1"
        )

        # Call function and expect ValueError
        with pytest.raises(ValueError) as exc_info:
            get_runtime_metadata(arn, region="us-east-1")

        # Verify error message
        error_msg = str(exc_info.value)
        assert "agentRuntimeId" in error_msg
        assert "missing" in error_msg.lower()

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_status_defaults_to_unknown(self, mock_session):
        """Additional test: Verify status defaults to UNKNOWN if not in response."""
        # Setup mock
        mock_client = MagicMock()
        mock_session.return_value.client.return_value = mock_client
        
        # Response without status field
        mock_response = {
            'agentRuntimeId': 'test-runtime-id-456'
        }
        mock_client.get_agent_runtime.return_value = mock_response

        # Create test ARN
        arn = ParsedARN(
            raw_arn="arn:aws:bedrock-agentcore:us-east-1:123456789012:agent/abc:v1",
            region="us-east-1",
            account_id="123456789012",
            resource_id="agent/abc:v1"
        )

        # Call function
        result = get_runtime_metadata(arn, region="us-east-1")

        # Verify status defaults to UNKNOWN
        assert result.status == 'UNKNOWN'
        assert result.agent_runtime_id == 'test-runtime-id-456'



class TestDiscoverLogGroups:
    """Tests for discover_log_groups function covering tasks 5.2.1 through 5.2.7."""

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_both_log_groups_found(self, mock_session):
        """Task 5.2.1: Test both log groups found (mocked)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with both log groups
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups, DiscoveredLogGroups

        # Call function
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1",
            profile=None
        )

        # Verify result
        assert isinstance(result, DiscoveredLogGroups)
        assert result.runtime_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'
        assert result.otel_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'
        assert result.discovery_method == 'describe_log_groups with prefix'

        # Verify boto3 calls
        mock_session.assert_called_once_with(region_name="us-east-1", profile_name=None)
        mock_session.return_value.client.assert_called_once_with('logs')
        mock_logs_client.get_paginator.assert_called_once_with('describe_log_groups')
        mock_paginator.paginate.assert_called_once_with(
            logGroupNamePrefix='/aws/bedrock-agentcore/runtimes/test-runtime-id-'
        )

    def test_with_runtime_override_and_otel_override(self):
        """Task 5.2.2: Test with runtime_override and otel_override (bypass discovery)."""
        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function with both overrides (should bypass API calls entirely)
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1",
            runtime_override="/custom/runtime/logs",
            otel_override="/custom/otel/logs"
        )

        # Verify result uses overrides
        assert result.runtime_logs == '/custom/runtime/logs'
        assert result.otel_logs == '/custom/otel/logs'
        assert result.discovery_method == 'override'

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_only_runtime_logs_found(self, mock_session):
        """Task 5.2.3: Test only runtime logs found (should fail without override)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with only runtime logs
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function and expect LogGroupNotFoundError
        with pytest.raises(LogGroupNotFoundError) as exc_info:
            discover_log_groups(
                agent_runtime_id="test-runtime-id",
                region="us-east-1"
            )

        # Verify error message mentions OTEL logs
        error_msg = str(exc_info.value)
        assert "OTEL logs not found" in error_msg
        assert "/aws/bedrock-agentcore/runtimes/test-runtime-id-" in error_msg
        assert "otel-rt-logs" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_only_otel_logs_found(self, mock_session):
        """Task 5.2.4: Test only OTEL logs found (should fail without override)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with only OTEL logs
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function and expect LogGroupNotFoundError
        with pytest.raises(LogGroupNotFoundError) as exc_info:
            discover_log_groups(
                agent_runtime_id="test-runtime-id",
                region="us-east-1"
            )

        # Verify error message mentions runtime logs
        error_msg = str(exc_info.value)
        assert "Runtime logs not found" in error_msg
        assert "/aws/bedrock-agentcore/runtimes/test-runtime-id-" in error_msg
        assert "runtime-logs" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_no_log_groups_found(self, mock_session):
        """Task 5.2.5: Test no log groups found (should fail without override)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with no log groups
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': []
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function and expect LogGroupNotFoundError
        with pytest.raises(LogGroupNotFoundError) as exc_info:
            discover_log_groups(
                agent_runtime_id="nonexistent-runtime-id",
                region="us-east-1"
            )

        # Verify error message
        error_msg = str(exc_info.value)
        assert "Runtime logs not found" in error_msg
        assert "/aws/bedrock-agentcore/runtimes/nonexistent-runtime-id-" in error_msg

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_multiple_matching_log_groups(self, mock_session):
        """Task 5.2.6: Test multiple matching log groups (should select by suffix)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with multiple log groups
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint1/runtime-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint2/runtime-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint1/otel-rt-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint2/otel-rt-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-other/some-other-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1"
        )

        # Verify result selects first matching log group by suffix
        assert result.runtime_logs.endswith('/runtime-logs')
        assert result.otel_logs.endswith('/otel-rt-logs')
        # Should select the first one found
        assert result.runtime_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint1/runtime-logs'
        assert result.otel_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint1/otel-rt-logs'

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_pagination_handling(self, mock_session):
        """Task 5.2.7: Test pagination handling."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with multiple pages
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        # Simulate pagination: runtime logs on page 1, OTEL logs on page 2
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/other-logs'},
                ]
            },
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/more-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1"
        )

        # Verify result found both log groups across pages
        assert result.runtime_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'
        assert result.otel_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'
        assert result.discovery_method == 'describe_log_groups with prefix'

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_partial_override_runtime_only(self, mock_session):
        """Additional test: Test with only runtime_override (partial override)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with only OTEL logs
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function with runtime_override only
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1",
            runtime_override="/custom/runtime/logs"
        )

        # Verify result uses override for runtime, discovered for OTEL
        assert result.runtime_logs == '/custom/runtime/logs'
        assert result.otel_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'
        assert result.discovery_method == 'partial override'

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_partial_override_otel_only(self, mock_session):
        """Additional test: Test with only otel_override (partial override)."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response with only runtime logs
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function with otel_override only
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-east-1",
            otel_override="/custom/otel/logs"
        )

        # Verify result uses discovered for runtime, override for OTEL
        assert result.runtime_logs == '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'
        assert result.otel_logs == '/custom/otel/logs'
        assert result.discovery_method == 'partial override'

    @patch('agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn.boto3.Session')
    def test_with_aws_profile(self, mock_session):
        """Additional test: Test with AWS profile."""
        # Setup mock
        mock_logs_client = MagicMock()
        mock_session.return_value.client.return_value = mock_logs_client
        
        # Mock paginator response
        mock_paginator = MagicMock()
        mock_logs_client.get_paginator.return_value = mock_paginator
        
        mock_paginator.paginate.return_value = [
            {
                'logGroups': [
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/runtime-logs'},
                    {'logGroupName': '/aws/bedrock-agentcore/runtimes/test-runtime-id-endpoint/otel-rt-logs'},
                ]
            }
        ]

        # Import function
        from agent_eval.tools.agentcore_pipeline.run_from_agentcore_arn import discover_log_groups

        # Call function with profile
        result = discover_log_groups(
            agent_runtime_id="test-runtime-id",
            region="us-west-2",
            profile="myprofile"
        )

        # Verify boto3 session was created with profile
        mock_session.assert_called_once_with(region_name="us-west-2", profile_name="myprofile")
        
        # Verify result
        assert result.runtime_logs.endswith('/runtime-logs')
        assert result.otel_logs.endswith('/otel-rt-logs')
