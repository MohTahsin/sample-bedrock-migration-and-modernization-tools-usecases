"""
Unit tests for judge configuration system.

Tests Requirements 13.1-13.7:
- Judge configuration loads successfully with 1-5 judges
- Rejects 0 judges with error "At least 1 judge required"
- Rejects 6+ judges with error "Maximum 5 judges allowed"
- Default repeats value of 3 is applied when not specified
- Required fields (judge_id, provider, model_id, params) are extracted correctly
- Optional fields (concurrency, rate_limit, retry_policy) are handled gracefully
"""

import pytest
import tempfile
import os
from pathlib import Path

from agent_eval.judges.judge_config_schema import (
    JudgeConfigLoader,
    JudgeConfig,
    Judge,
    ValidationError,
    ConfigurationError
)


class TestJudgeConfigLoader:
    """Test suite for JudgeConfigLoader class."""
    
    def test_load_single_judge(self, tmp_path):
        """Test loading configuration with 1 judge (Requirement 13.1)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: anthropic.claude-3-sonnet
    params:
      temperature: 0.7
      max_tokens: 1000
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert len(config.judges) == 1
        assert config.judges[0].judge_id == "judge1"
        assert config.judges[0].provider == "bedrock"
        assert config.judges[0].model_id == "anthropic.claude-3-sonnet"
        assert config.judges[0].params == {"temperature": 0.7, "max_tokens": 1000}
    
    def test_load_five_judges(self, tmp_path):
        """Test loading configuration with 5 judges (maximum) (Requirement 13.1)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
  - judge_id: judge2
    provider: openai
    model_id: model2
    params: {}
  - judge_id: judge3
    provider: anthropic
    model_id: model3
    params: {}
  - judge_id: judge4
    provider: bedrock
    model_id: model4
    params: {}
  - judge_id: judge5
    provider: openai
    model_id: model5
    params: {}
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert len(config.judges) == 5
        assert [j.judge_id for j in config.judges] == ["judge1", "judge2", "judge3", "judge4", "judge5"]
    
    def test_reject_zero_judges(self, tmp_path):
        """Test rejection of 0 judges with specific error (Requirement 13.2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges: []
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="At least 1 judge required"):
            loader.load(str(config_file))
    
    def test_reject_six_judges(self, tmp_path):
        """Test rejection of 6+ judges with specific error (Requirement 13.3)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
  - judge_id: judge2
    provider: bedrock
    model_id: model2
    params: {}
  - judge_id: judge3
    provider: bedrock
    model_id: model3
    params: {}
  - judge_id: judge4
    provider: bedrock
    model_id: model4
    params: {}
  - judge_id: judge5
    provider: bedrock
    model_id: model5
    params: {}
  - judge_id: judge6
    provider: bedrock
    model_id: model6
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Maximum 5 judges allowed"):
            loader.load(str(config_file))
    
    def test_default_repeats_applied(self, tmp_path):
        """Test default repeats=3 applied when omitted (Requirement 13.5)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert config.judges[0].repeats == 3
    
    def test_custom_repeats_respected(self, tmp_path):
        """Test custom repeats value is respected (Requirement 13.5)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    repeats: 5
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert config.judges[0].repeats == 5
    
    def test_required_fields_extracted(self, tmp_path):
        """Test required fields extracted correctly (Requirement 13.6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: test_judge
    provider: bedrock
    model_id: anthropic.claude-3-sonnet
    params:
      temperature: 0.5
      max_tokens: 2000
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        judge = config.judges[0]
        assert judge.judge_id == "test_judge"
        assert judge.provider == "bedrock"
        assert judge.model_id == "anthropic.claude-3-sonnet"
        assert judge.params == {"temperature": 0.5, "max_tokens": 2000}
    
    def test_optional_fields_handled_gracefully(self, tmp_path):
        """Test optional fields handled when present or absent (Requirement 13.7)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    concurrency: 5
    rate_limit: 10
    retry_policy:
      max_retries: 3
      backoff_multiplier: 2
    timeout_seconds: 60
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        judge = config.judges[0]
        assert judge.concurrency == 5
        assert judge.rate_limit == 10
        assert judge.retry_policy == {"max_retries": 3, "backoff_multiplier": 2}
        assert judge.timeout_seconds == 60
    
    def test_optional_fields_absent(self, tmp_path):
        """Test optional fields default to None when absent (Requirement 13.7)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        judge = config.judges[0]
        assert judge.concurrency is None
        assert judge.rate_limit is None
        assert judge.retry_policy is None
        assert judge.timeout_seconds == 30  # Default value
    
    def test_missing_judge_id_error(self, tmp_path):
        """Test error when judge_id is missing."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - provider: bedrock
    model_id: model1
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="judge_id is required"):
            loader.load(str(config_file))
    
    def test_missing_provider_error(self, tmp_path):
        """Test error when provider is missing."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    model_id: model1
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="provider is required"):
            loader.load(str(config_file))
    
    def test_missing_model_id_error(self, tmp_path):
        """Test error when model_id is missing."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="model_id must be a non-empty string"):
            loader.load(str(config_file))
    
    def test_empty_model_id_error(self, tmp_path):
        """Test error when model_id is empty string."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: ""
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="model_id must be a non-empty string"):
            loader.load(str(config_file))
    
    def test_whitespace_only_model_id_error(self, tmp_path):
        """Test error when model_id is whitespace only."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: "   "
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="model_id must be a non-empty string"):
            loader.load(str(config_file))
    
    def test_missing_params_error(self, tmp_path):
        """Test error when params is missing."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="params is required"):
            loader.load(str(config_file))
    
    def test_error_includes_judge_id(self, tmp_path):
        """Test that error messages include judge_id for better debugging."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: my_judge
    provider: bedrock
    model_id: model1
    params: {}
    repeats: "invalid"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="judge_id=my_judge"):
            loader.load(str(config_file))
    
    def test_file_not_found_error(self):
        """Test error when configuration file doesn't exist."""
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Judge configuration file not found"):
            loader.load("/nonexistent/path/judges.yaml")
    
    def test_invalid_yaml_error(self, tmp_path):
        """Test error when YAML is malformed."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {invalid yaml syntax
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            loader.load(str(config_file))
    
    def test_empty_file_error(self, tmp_path):
        """Test error when configuration file is empty."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Judge configuration file is empty"):
            loader.load(str(config_file))
    
    def test_missing_judges_key_error(self, tmp_path):
        """Test error when 'judges' key is missing."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
some_other_key: value
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Judge configuration must contain 'judges' key"):
            loader.load(str(config_file))
    
    def test_judges_not_list_error(self, tmp_path):
        """Test error when 'judges' is not a list."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges: "not a list"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="'judges' must be a list"):
            loader.load(str(config_file))
    
    def test_params_not_dict_error(self, tmp_path):
        """Test error when params is not a dictionary (Gap #1)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: "temp=0.2"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="params must be a dictionary"):
            loader.load(str(config_file))
    
    def test_params_list_error(self, tmp_path):
        """Test error when params is a list instead of dict (Gap #1)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: [1, 2, 3]
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="params must be a dictionary"):
            loader.load(str(config_file))
    
    def test_repeats_string_error(self, tmp_path):
        """Test error when repeats is a string (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    repeats: "3"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="repeats must be an integer"):
            loader.load(str(config_file))
    
    def test_repeats_float_error(self, tmp_path):
        """Test error when repeats is a float (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    repeats: 3.5
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="repeats must be an integer"):
            loader.load(str(config_file))
    
    def test_timeout_seconds_string_error(self, tmp_path):
        """Test error when timeout_seconds is a string (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    timeout_seconds: "30"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="timeout_seconds must be an integer"):
            loader.load(str(config_file))
    
    def test_concurrency_string_error(self, tmp_path):
        """Test error when concurrency is a string (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    concurrency: "5"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="concurrency must be an integer"):
            loader.load(str(config_file))
    
    def test_concurrency_negative_error(self, tmp_path):
        """Test error when concurrency is negative (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    concurrency: -1
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="concurrency must be >= 1"):
            loader.load(str(config_file))
    
    def test_rate_limit_string_error(self, tmp_path):
        """Test error when rate_limit is a string (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    rate_limit: "10"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="rate_limit must be an integer"):
            loader.load(str(config_file))
    
    def test_rate_limit_zero_error(self, tmp_path):
        """Test error when rate_limit is zero (Gap #2)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    rate_limit: 0
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="rate_limit must be >= 1"):
            loader.load(str(config_file))
    
    def test_duplicate_judge_id_error(self, tmp_path):
        """Test error when duplicate judge_id exists (Gap #3)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
  - judge_id: judge1
    provider: openai
    model_id: model2
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Duplicate judge_id: judge1"):
            loader.load(str(config_file))
    
    def test_duplicate_judge_id_three_judges_error(self, tmp_path):
        """Test error when duplicate judge_id exists among multiple judges (Gap #3)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
  - judge_id: judge2
    provider: openai
    model_id: model2
    params: {}
  - judge_id: judge1
    provider: anthropic
    model_id: model3
    params: {}
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="Duplicate judge_id: judge1"):
            loader.load(str(config_file))
    
    def test_retry_policy_not_dict_error(self, tmp_path):
        """Test error when retry_policy is not a dictionary (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy: "invalid"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="retry_policy must be a dictionary"):
            loader.load(str(config_file))
    
    def test_retry_policy_max_retries_string_error(self, tmp_path):
        """Test error when retry_policy.max_retries is a string (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      max_retries: "3"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="retry_policy.max_retries must be an integer"):
            loader.load(str(config_file))
    
    def test_retry_policy_max_retries_negative_error(self, tmp_path):
        """Test error when retry_policy.max_retries is negative (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      max_retries: -1
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="retry_policy.max_retries must be >= 0"):
            loader.load(str(config_file))
    
    def test_retry_policy_backoff_multiplier_string_error(self, tmp_path):
        """Test error when retry_policy.backoff_multiplier is a string (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      backoff_multiplier: "2"
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="retry_policy.backoff_multiplier must be a number"):
            loader.load(str(config_file))
    
    def test_retry_policy_backoff_multiplier_too_small_error(self, tmp_path):
        """Test error when retry_policy.backoff_multiplier < 1 (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      backoff_multiplier: 0.5
""")
        
        loader = JudgeConfigLoader()
        with pytest.raises(ConfigurationError, match="retry_policy.backoff_multiplier must be >= 1"):
            loader.load(str(config_file))
    
    def test_retry_policy_valid(self, tmp_path):
        """Test valid retry_policy is accepted (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      max_retries: 3
      backoff_multiplier: 2
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert config.judges[0].retry_policy == {"max_retries": 3, "backoff_multiplier": 2}
    
    def test_retry_policy_float_backoff_multiplier_valid(self, tmp_path):
        """Test valid retry_policy with float backoff_multiplier (Gap #6)."""
        config_file = tmp_path / "judges.yaml"
        config_file.write_text("""
judges:
  - judge_id: judge1
    provider: bedrock
    model_id: model1
    params: {}
    retry_policy:
      max_retries: 5
      backoff_multiplier: 1.5
""")
        
        loader = JudgeConfigLoader()
        config = loader.load(str(config_file))
        
        assert config.judges[0].retry_policy == {"max_retries": 5, "backoff_multiplier": 1.5}
    
    def test_validate_judge_count_method(self):
        """Test validate_judge_count method directly."""
        loader = JudgeConfigLoader()
        
        # Valid counts
        loader.validate_judge_count([1])
        loader.validate_judge_count([1, 2, 3])
        loader.validate_judge_count([1, 2, 3, 4, 5])
        
        # Invalid counts
        with pytest.raises(ValidationError, match="At least 1 judge required"):
            loader.validate_judge_count([])
        
        with pytest.raises(ValidationError, match="Maximum 5 judges allowed"):
            loader.validate_judge_count([1, 2, 3, 4, 5, 6])
    
    def test_apply_defaults_method(self):
        """Test apply_defaults method."""
        loader = JudgeConfigLoader()
        
        judge = Judge(
            judge_id="test",
            provider="bedrock",
            model_id="model1",
            params={},
            repeats=5,
            timeout_seconds=60
        )
        
        result = loader.apply_defaults(judge)
        assert result.repeats == 5
        assert result.timeout_seconds == 60


class TestJudgeDataclass:
    """Test suite for Judge dataclass validation."""
    
    def test_valid_judge_creation(self):
        """Test creating a valid Judge object."""
        judge = Judge(
            judge_id="test_judge",
            provider="bedrock",
            model_id="model1",
            params={"temperature": 0.7}
        )
        
        assert judge.judge_id == "test_judge"
        assert judge.provider == "bedrock"
        assert judge.model_id == "model1"
        assert judge.params == {"temperature": 0.7}
        assert judge.repeats == 3  # Default
        assert judge.timeout_seconds == 30  # Default
    
    def test_judge_missing_judge_id(self):
        """Test Judge validation fails when judge_id is empty."""
        with pytest.raises(ValidationError, match="judge_id is required"):
            Judge(
                judge_id="",
                provider="bedrock",
                model_id="model1",
                params={}
            )
    
    def test_judge_missing_provider(self):
        """Test Judge validation fails when provider is empty."""
        with pytest.raises(ValidationError, match="provider is required"):
            Judge(
                judge_id="test",
                provider="",
                model_id="model1",
                params={}
            )
    
    def test_judge_missing_model_id(self):
        """Test Judge validation fails when model_id is empty."""
        with pytest.raises(ValidationError, match="model_id is required"):
            Judge(
                judge_id="test",
                provider="bedrock",
                model_id="",
                params={}
            )
    
    def test_judge_none_params(self):
        """Test Judge validation fails when params is None."""
        with pytest.raises(ValidationError, match="params is required"):
            Judge(
                judge_id="test",
                provider="bedrock",
                model_id="model1",
                params=None
            )
    
    def test_judge_invalid_repeats(self):
        """Test Judge validation fails when repeats < 1."""
        with pytest.raises(ValidationError, match="repeats must be >= 1"):
            Judge(
                judge_id="test",
                provider="bedrock",
                model_id="model1",
                params={},
                repeats=0
            )
    
    def test_judge_invalid_timeout(self):
        """Test Judge validation fails when timeout_seconds < 1."""
        with pytest.raises(ValidationError, match="timeout_seconds must be >= 1"):
            Judge(
                judge_id="test",
                provider="bedrock",
                model_id="model1",
                params={},
                timeout_seconds=0
            )


class TestJudgeConfigDataclass:
    """Test suite for JudgeConfig dataclass validation."""
    
    def test_valid_judge_config(self):
        """Test creating a valid JudgeConfig."""
        judge = Judge(
            judge_id="test",
            provider="bedrock",
            model_id="model1",
            params={}
        )
        
        config = JudgeConfig(judges=[judge])
        assert len(config.judges) == 1
    
    def test_judge_config_empty_judges(self):
        """Test JudgeConfig validation fails with empty judges list."""
        with pytest.raises(ValidationError, match="At least 1 judge required"):
            JudgeConfig(judges=[])
    
    def test_judge_config_too_many_judges(self):
        """Test JudgeConfig validation fails with > 5 judges."""
        judges = [
            Judge(judge_id=f"judge{i}", provider="bedrock", model_id="model", params={})
            for i in range(6)
        ]
        
        with pytest.raises(ValidationError, match="Maximum 5 judges allowed"):
            JudgeConfig(judges=judges)
