"""
Unit tests for error handling and logging.

Tests ValidationError, JudgeExecutionError, and structured logging.
"""

import pytest
from agent_eval.judges.exceptions import (
    JudgeExecutionError,
    ValidationError,
    APIError,
    TimeoutError,
    ValidationResult
)
from agent_eval.evaluators.trace_eval.logging_config import (
    StructuredLogger,
    get_logger,
    get_job_logger,
    get_run_logger,
    setup_logging
)


class TestJudgeExecutionError:
    """Test JudgeExecutionError exception class."""
    
    def test_basic_error_creation(self):
        """Test creating basic JudgeExecutionError."""
        error = JudgeExecutionError(
            message="Test error",
            error_code="TEST_ERROR",
            retryable=True
        )
        
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.retryable is True
        assert str(error) == "TEST_ERROR: Test error"
    
    def test_error_with_context(self):
        """Test JudgeExecutionError with context."""
        error = JudgeExecutionError(
            message="Job failed",
            error_code="JOB_FAILED",
            context={
                'job_id': 'job-123',
                'judge_id': 'judge-1',
                'retry_count': 2
            }
        )
        
        assert error.job_id == 'job-123'
        assert error.judge_id == 'judge-1'
        assert error.retry_count == 2
    
    def test_from_job_factory_method(self):
        """Test creating error from job context."""
        error = JudgeExecutionError.from_job(
            message="API call failed",
            job_id="job-456",
            judge_id="judge-2",
            error="Connection timeout",
            retry_count=3,
            error_code="API_TIMEOUT",
            retryable=True
        )
        
        assert error.message == "API call failed"
        assert error.job_id == "job-456"
        assert error.judge_id == "judge-2"
        assert error.retry_count == 3
        assert error.error_code == "API_TIMEOUT"
        assert error.retryable is True
        assert error.context['error'] == "Connection timeout"


class TestValidationError:
    """Test ValidationError exception class."""
    
    def test_validation_error_with_details(self):
        """Test ValidationError with field details."""
        error = ValidationError(
            message="Invalid score value",
            error_code="INVALID_SCORE",
            field="score",
            expected="1-5",
            actual="10"
        )
        
        assert error.message == "Invalid score value"
        assert error.error_code == "INVALID_SCORE"
        assert error.field == "score"
        assert error.expected == "1-5"
        assert error.actual == "10"
        assert error.retryable is True  # Validation errors are retryable
        
        # Check context includes validation details
        assert error.context['field'] == "score"
        assert error.context['expected'] == "1-5"
        assert error.context['actual'] == "10"
    
    def test_validation_error_default_retryable(self):
        """Test that ValidationError is retryable by default."""
        error = ValidationError(message="Test validation error")
        assert error.retryable is True


class TestAPIError:
    """Test APIError exception class."""
    
    def test_api_error_with_status_code(self):
        """Test APIError with HTTP status code."""
        error = APIError(
            message="Service unavailable",
            error_code="API_UNAVAILABLE",
            status_code=503,
            retryable=True
        )
        
        assert error.message == "Service unavailable"
        assert error.error_code == "API_UNAVAILABLE"
        assert error.status_code == 503
        assert error.retryable is True
        assert error.context['status_code'] == 503


class TestTimeoutError:
    """Test TimeoutError exception class."""
    
    def test_timeout_error(self):
        """Test TimeoutError with timeout duration."""
        error = TimeoutError(
            message="Request timed out",
            timeout_seconds=30.0
        )
        
        assert error.message == "Request timed out"
        assert error.error_code == "TIMEOUT"
        assert error.timeout_seconds == 30.0
        assert error.retryable is True
        assert error.context['timeout_seconds'] == 30.0


class TestValidationResult:
    """Test ValidationResult class."""
    
    def test_success_result(self):
        """Test creating successful validation result."""
        result = ValidationResult.success()
        
        assert result.is_valid is True
        assert result.error_code is None
        assert result.message is None
    
    def test_failure_result(self):
        """Test creating failed validation result."""
        result = ValidationResult.failure(
            error_code="MISSING_FIELD",
            message="Required field 'score' is missing",
            field="score",
            expected="numeric value",
            actual="null"
        )
        
        assert result.is_valid is False
        assert result.error_code == "MISSING_FIELD"
        assert result.message == "Required field 'score' is missing"
        assert result.field == "score"
        assert result.expected == "numeric value"
        assert result.actual == "null"
    
    def test_to_dict(self):
        """Test converting ValidationResult to dictionary."""
        result = ValidationResult.failure(
            error_code="INVALID_FORMAT",
            message="Invalid format"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['is_valid'] is False
        assert result_dict['error_code'] == "INVALID_FORMAT"
        assert result_dict['message'] == "Invalid format"
    
    def test_repr(self):
        """Test ValidationResult string representation."""
        success = ValidationResult.success()
        assert repr(success) == "ValidationResult(valid=True)"
        
        failure = ValidationResult.failure(
            error_code="TEST_ERROR",
            message="Test message"
        )
        assert "valid=False" in repr(failure)
        assert "TEST_ERROR" in repr(failure)


class TestStructuredLogger:
    """Test StructuredLogger class."""
    
    def test_logger_creation(self):
        """Test creating structured logger."""
        logger = StructuredLogger("test.logger")
        assert logger.logger.name == "test.logger"
        assert logger.context == {}
    
    def test_logger_with_context(self):
        """Test creating logger with default context."""
        logger = StructuredLogger(
            "test.logger",
            context={'run_id': 'run-123'}
        )
        
        assert logger.context['run_id'] == 'run-123'
    
    def test_with_context_method(self):
        """Test adding context to logger."""
        logger = StructuredLogger("test.logger", context={'run_id': 'run-123'})
        job_logger = logger.with_context(job_id='job-456')
        
        # Original logger unchanged
        assert 'job_id' not in logger.context
        
        # New logger has merged context
        assert job_logger.context['run_id'] == 'run-123'
        assert job_logger.context['job_id'] == 'job-456'
    
    def test_format_message(self):
        """Test message formatting with context."""
        logger = StructuredLogger(
            "test.logger",
            context={'run_id': 'run-123'}
        )
        
        formatted = logger._format_message(
            "Test message",
            extra_context={'job_id': 'job-456'}
        )
        
        assert "Test message" in formatted
        assert "run_id=run-123" in formatted
        assert "job_id=job-456" in formatted
        assert "timestamp=" in formatted


class TestLoggingHelpers:
    """Test logging helper functions."""
    
    def test_get_logger(self):
        """Test get_logger helper."""
        logger = get_logger("test.module", run_id="run-123")
        
        assert isinstance(logger, StructuredLogger)
        assert logger.context['run_id'] == "run-123"
    
    def test_get_job_logger(self):
        """Test get_job_logger helper."""
        logger = get_job_logger(run_id="run-123", job_id="job-456")
        
        assert isinstance(logger, StructuredLogger)
        assert logger.context['run_id'] == "run-123"
        assert logger.context['job_id'] == "job-456"
        assert logger.logger.name == "agent_eval.trace_eval.job"
    
    def test_get_run_logger(self):
        """Test get_run_logger helper."""
        logger = get_run_logger(run_id="run-123")
        
        assert isinstance(logger, StructuredLogger)
        assert logger.context['run_id'] == "run-123"
        assert logger.logger.name == "agent_eval.trace_eval.run"
    
    def test_setup_logging(self):
        """Test setup_logging configuration."""
        # Should not raise any exceptions
        setup_logging(level="INFO", format_style="simple")
        setup_logging(level="DEBUG", format_style="detailed")


class TestErrorHandlingIntegration:
    """Integration tests for error handling with logging."""
    
    def test_error_with_logging_context(self):
        """Test using errors with structured logging."""
        logger = get_job_logger(run_id="run-123", job_id="job-456")
        
        try:
            raise JudgeExecutionError.from_job(
                message="Test error",
                job_id="job-456",
                judge_id="judge-1",
                error="Connection failed",
                retry_count=2
            )
        except JudgeExecutionError as e:
            # Logger context matches error context
            assert logger.context['run_id'] == "run-123"
            assert logger.context['job_id'] == e.job_id
            assert e.retry_count == 2
    
    def test_validation_error_with_context(self):
        """Test ValidationError with job context."""
        error = ValidationError(
            message="Invalid response",
            error_code="INVALID_JSON",
            context={
                'job_id': 'job-789',
                'judge_id': 'judge-2',
                'retry_count': 1
            }
        )
        
        assert error.job_id == 'job-789'
        assert error.judge_id == 'judge-2'
        assert error.retry_count == 1
