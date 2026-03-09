"""
Score Aggregation Validation Tests

This module validates score aggregation logic using mocked judge results.
Tests within-judge and cross-judge aggregation for both numeric and categorical scores.

Requirements Coverage: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.11

Test Strategy:
- Test within-judge median computation from mock scores
- Test within-judge mean computation from mock scores
- Test within-judge variance computation from mock scores
- Test cross-judge weighted average from mock scores
- Test disagreement signal computation (0.0 to 1.0)
- Test high_risk_flag when disagreement exceeds threshold
- Test invalid score exclusion from aggregation
- Test all-judges-failed scenario (judge_count=0)
- Test deterministic aggregation for identical inputs
"""

import pytest
from typing import List, Optional

# Import aggregation components
from agent_eval.evaluators.trace_eval.judging.aggregator import (
    Aggregator,
    ScoringScale,
    WithinJudgeResult,
    CrossJudgeResult
)
from agent_eval.evaluators.trace_eval.judging.models import JobResult


# -------------------------------------------------------------------------
# Fixtures and Helpers
# -------------------------------------------------------------------------

def create_mock_job_result(
    job_id: str,
    judge_id: str,
    rubric_id: str,
    score: Optional[float],
    status: str = "success",
    turn_id: Optional[str] = None
) -> JobResult:
    """
    Create a mock JobResult for testing.
    
    Args:
        job_id: Unique job identifier
        judge_id: Judge identifier
        rubric_id: Rubric identifier
        score: Score value (numeric or categorical)
        status: Job status (default: "success")
        turn_id: Optional turn identifier
        
    Returns:
        JobResult instance
    """
    parsed_response = {"score": score} if score is not None else None
    
    return JobResult(
        job_id=job_id,
        run_id="test_run",
        turn_id=turn_id,
        rubric_id=rubric_id,
        judge_id=judge_id,
        repeat_index=0,
        timestamp="2024-01-01T00:00:00.000Z",
        status=status,
        parsed_response=parsed_response
    )


@pytest.fixture
def aggregator() -> Aggregator:
    """Create an Aggregator instance with default threshold."""
    return Aggregator(disagreement_threshold=0.3)


@pytest.fixture
def numeric_scoring_scale() -> ScoringScale:
    """Create a numeric scoring scale (0-10)."""
    return ScoringScale(type="numeric", min=0.0, max=10.0)


@pytest.fixture
def categorical_scoring_scale() -> ScoringScale:
    """Create a categorical scoring scale."""
    return ScoringScale(type="categorical", values=["pass", "fail", "partial"])


# -------------------------------------------------------------------------
# Test: Within-Judge Median Computation (Requirement 6.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestWithinJudgeMedian:
    """Validate within-judge median computation from mock scores."""
    
    def test_median_odd_number_of_scores(self, aggregator):
        """
        Requirement 6.1: Verify median computation with odd number of scores
        
        Expected: Median of [1.0, 2.0, 3.0, 4.0, 5.0] = 3.0
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.median == 3.0
        assert within_result.sample_size == 5
        assert within_result.scoring_type == "numeric"
    
    def test_median_even_number_of_scores(self, aggregator):
        """
        Requirement 6.1: Verify median computation with even number of scores
        
        Expected: Median of [1.0, 2.0, 3.0, 4.0] = 2.5
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0, 4.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.median == 2.5
        assert within_result.sample_size == 4
    
    def test_median_single_score(self, aggregator):
        """
        Requirement 6.1: Verify median computation with single score
        
        Expected: Median of [5.0] = 5.0
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 5.0)
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.median == 5.0
        assert within_result.sample_size == 1


# -------------------------------------------------------------------------
# Test: Within-Judge Mean Computation (Requirement 6.2)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestWithinJudgeMean:
    """Validate within-judge mean computation from mock scores."""
    
    def test_mean_computation(self, aggregator):
        """
        Requirement 6.2: Verify mean computation
        
        Expected: Mean of [1.0, 2.0, 3.0, 4.0, 5.0] = 3.0
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.mean == 3.0
    
    def test_mean_with_decimals(self, aggregator):
        """
        Requirement 6.2: Verify mean computation with decimal values
        
        Expected: Mean of [1.5, 2.5, 3.5] = 2.5
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.5, 2.5, 3.5])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.mean == 2.5


# -------------------------------------------------------------------------
# Test: Within-Judge Variance Computation (Requirement 6.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestWithinJudgeVariance:
    """Validate within-judge variance computation from mock scores."""
    
    def test_variance_identical_scores(self, aggregator):
        """
        Requirement 6.3: Verify variance with identical scores
        
        Expected: Variance of [5.0, 5.0, 5.0] = 0.0
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", 5.0)
            for i in range(3)
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.variance == 0.0
    
    def test_variance_with_spread(self, aggregator):
        """
        Requirement 6.3: Verify variance computation with spread
        
        Expected: Variance of [1.0, 2.0, 3.0] > 0
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.variance > 0.0
        # Population variance of [1, 2, 3] = 2/3 ≈ 0.6667
        assert abs(within_result.variance - 0.6667) < 0.001
    
    def test_variance_normalized_by_scale(self, aggregator, numeric_scoring_scale):
        """
        Requirement 6.3: Verify variance normalization by scoring scale
        
        Expected: Variance normalized by scale range (0-10)
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([2.0, 5.0, 8.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1", scoring_scale=numeric_scoring_scale
        )
        
        # Raw variance of [2, 5, 8] = 6.0
        # Normalized by (10-0)^2 = 100
        # Expected: 6.0 / 100 = 0.06
        assert within_result.variance > 0.0
        assert abs(within_result.variance - 0.06) < 0.001
    
    def test_variance_single_score_is_zero(self, aggregator):
        """
        Requirement 6.3: Verify variance is zero for single score
        
        Expected: Variance of [5.0] = 0.0
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 5.0)
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.variance == 0.0


# -------------------------------------------------------------------------
# Test: Cross-Judge Weighted Average (Requirement 6.4)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestCrossJudgeWeightedAverage:
    """Validate cross-judge weighted average computation from mock scores."""
    
    def test_weighted_average_equal_weights(self, aggregator):
        """
        Requirement 6.4: Verify weighted average with equal weights
        
        Expected: With equal sample_size and variance, weighted average = simple mean
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([2.0, 4.0, 6.0])
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # With equal weights, weighted average = (2 + 4 + 6) / 3 = 4.0
        assert cross_result.weighted_average == 4.0
        assert cross_result.judge_count == 3
    
    def test_weighted_average_different_sample_sizes(self, aggregator):
        """
        Requirement 6.4: Verify weighted average with different sample sizes
        
        Expected: Judges with larger sample_size get higher weight
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                median=2.0,
                mean=2.0,
                variance=0.0,
                sample_size=1,  # Low weight
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                median=8.0,
                mean=8.0,
                variance=0.0,
                sample_size=9,  # High weight
                scoring_type="numeric"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # Weight_1 = 1 / (1 + 0) = 1
        # Weight_2 = 9 / (1 + 0) = 9
        # Weighted avg = (2*1 + 8*9) / (1 + 9) = 74 / 10 = 7.4
        assert abs(cross_result.weighted_average - 7.4) < 0.001
    
    def test_weighted_average_different_variances(self, aggregator):
        """
        Requirement 6.4: Verify weighted average with different variances
        
        Expected: Judges with lower variance get higher weight
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                median=2.0,
                mean=2.0,
                variance=4.0,  # High variance, low weight
                sample_size=5,
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                median=8.0,
                mean=8.0,
                variance=0.1,  # Low variance, high weight
                sample_size=5,
                scoring_type="numeric"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # Weight_1 = 5 / (1 + 4.0) = 1.0
        # Weight_2 = 5 / (1 + 0.1) = 4.545...
        # Weighted avg should be closer to 8.0 than 2.0
        assert cross_result.weighted_average > 6.0
        assert cross_result.weighted_average < 8.0


# -------------------------------------------------------------------------
# Test: Disagreement Signal Computation (Requirement 6.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDisagreementSignal:
    """Validate disagreement signal computation (0.0 to 1.0)."""
    
    def test_disagreement_perfect_agreement(self, aggregator):
        """
        Requirement 6.5: Verify disagreement signal with perfect agreement
        
        Expected: Disagreement = 0.0 when all judges agree
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=5.0,
                mean=5.0,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i in range(3)
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        assert cross_result.disagreement_signal == 0.0
        assert cross_result.high_risk_flag is False
    
    def test_disagreement_with_spread(self, aggregator, numeric_scoring_scale):
        """
        Requirement 6.5: Verify disagreement signal with score spread
        
        Expected: Disagreement > 0.0 when judges disagree
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([2.0, 5.0, 8.0])
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1", scoring_scale=numeric_scoring_scale
        )
        
        assert cross_result.disagreement_signal > 0.0
        assert cross_result.disagreement_signal <= 1.0
    
    def test_disagreement_categorical_perfect_agreement(self, aggregator):
        """
        Requirement 6.5: Verify categorical disagreement with perfect agreement
        
        Expected: Disagreement = 0.0 when all judges vote the same
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="pass",
                variance=0.0,
                sample_size=3,
                scoring_type="categorical"
            )
            for i in range(3)
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        assert cross_result.disagreement_signal == 0.0
    
    def test_disagreement_categorical_with_split(self, aggregator):
        """
        Requirement 6.5: Verify categorical disagreement with vote split
        
        Expected: Disagreement > 0.0 when judges disagree
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="pass",
                variance=0.0,
                sample_size=3,
                scoring_type="categorical"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="fail",
                variance=0.0,
                sample_size=3,
                scoring_type="categorical"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        assert cross_result.disagreement_signal > 0.0
        assert cross_result.disagreement_signal <= 1.0


# -------------------------------------------------------------------------
# Test: High Risk Flag (Requirement 6.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestHighRiskFlag:
    """Validate high_risk_flag when disagreement exceeds threshold."""
    
    def test_high_risk_flag_below_threshold(self, aggregator, numeric_scoring_scale):
        """
        Requirement 6.6: Verify high_risk_flag is False below threshold
        
        Expected: With threshold=0.3, low disagreement should not trigger flag
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([5.0, 5.1, 5.2])
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1", scoring_scale=numeric_scoring_scale
        )
        
        # Standard deviation of [5.0, 5.1, 5.2] ≈ 0.082
        # Normalized by range 10: 0.082 / 10 = 0.0082 < 0.3
        assert cross_result.disagreement_signal < 0.3
        assert cross_result.high_risk_flag is False
    
    def test_high_risk_flag_above_threshold(self, aggregator, numeric_scoring_scale):
        """
        Requirement 6.6: Verify high_risk_flag is True above threshold
        
        Expected: With threshold=0.3, high disagreement should trigger flag
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([0.0, 5.0, 10.0])
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1", scoring_scale=numeric_scoring_scale
        )
        
        # Standard deviation of [0, 5, 10] = 4.08
        # Normalized by range 10: 4.08 / 10 = 0.408 > 0.3
        assert cross_result.disagreement_signal > 0.3
        assert cross_result.high_risk_flag is True
    
    def test_high_risk_flag_custom_threshold(self):
        """
        Requirement 6.6: Verify high_risk_flag respects custom threshold
        
        Expected: Custom threshold should be used for flag determination
        """
        aggregator_strict = Aggregator(disagreement_threshold=0.1)
        
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([5.0, 5.5, 6.0])
        ]
        
        cross_result = aggregator_strict.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # With stricter threshold, even small disagreement should trigger flag
        if cross_result.disagreement_signal > 0.1:
            assert cross_result.high_risk_flag is True


# -------------------------------------------------------------------------
# Test: Invalid Score Exclusion (Requirement 6.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestInvalidScoreExclusion:
    """Validate invalid score exclusion from aggregation."""
    
    def test_exclude_failed_status(self, aggregator):
        """
        Requirement 6.7: Verify failed results are excluded from aggregation
        
        Expected: Only successful results should be included
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 5.0, status="success"),
            create_mock_job_result("job_1", "judge_1", "rubric_1", 1.0, status="failure"),
            create_mock_job_result("job_2", "judge_1", "rubric_1", 7.0, status="success"),
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        # Should only use scores from successful results: [5.0, 7.0]
        assert within_result.median == 6.0
        assert within_result.sample_size == 2
    
    def test_exclude_timeout_status(self, aggregator):
        """
        Requirement 6.7: Verify timeout results are excluded from aggregation
        
        Expected: Timeout results should not contribute to scores
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 5.0, status="success"),
            create_mock_job_result("job_1", "judge_1", "rubric_1", 1.0, status="timeout"),
            create_mock_job_result("job_2", "judge_1", "rubric_1", 5.0, status="success"),
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        # Should only use scores from successful results: [5.0, 5.0]
        assert within_result.median == 5.0
        assert within_result.sample_size == 2
    
    def test_exclude_invalid_response_status(self, aggregator):
        """
        Requirement 6.7: Verify invalid_response results are excluded
        
        Expected: Invalid response results should not contribute to scores
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 8.0, status="success"),
            create_mock_job_result("job_1", "judge_1", "rubric_1", 2.0, status="invalid_response"),
            create_mock_job_result("job_2", "judge_1", "rubric_1", 9.0, status="success"),
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        # Should only use scores from successful results: [8.0, 9.0]
        assert within_result.median == 8.5
        assert within_result.sample_size == 2
    
    def test_exclude_none_scores(self, aggregator):
        """
        Requirement 6.7: Verify None scores are excluded even with success status
        
        Expected: Results with None scores should not contribute
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", 5.0, status="success"),
            create_mock_job_result("job_1", "judge_1", "rubric_1", None, status="success"),
            create_mock_job_result("job_2", "judge_1", "rubric_1", 7.0, status="success"),
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        # Should only use non-None scores: [5.0, 7.0]
        assert within_result.median == 6.0
        # sample_size should reflect successful results (3), not just scored results
        assert within_result.sample_size == 3


# -------------------------------------------------------------------------
# Test: All Judges Failed Scenario (Requirement 6.8)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestAllJudgesFailed:
    """Validate all-judges-failed scenario (judge_count=0)."""
    
    def test_all_judges_failed_within_judge(self, aggregator):
        """
        Requirement 6.8: Verify within-judge aggregation when all results failed
        
        Expected: sample_size=0, no scores computed
        """
        results = [
            create_mock_job_result("job_0", "judge_1", "rubric_1", None, status="failure"),
            create_mock_job_result("job_1", "judge_1", "rubric_1", None, status="timeout"),
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        assert within_result.sample_size == 0
        assert within_result.median is None
        assert within_result.mean is None
    
    def test_all_judges_failed_cross_judge(self, aggregator):
        """
        Requirement 6.8: Verify cross-judge aggregation when all judges failed
        
        Expected: judge_count=0, no weighted average computed
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                sample_size=0,  # All repeats failed
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                sample_size=0,  # All repeats failed
                scoring_type="numeric"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        assert cross_result.judge_count == 0
        assert cross_result.weighted_average is None
        assert cross_result.disagreement_signal == 0.0
    
    def test_partial_judges_failed(self, aggregator):
        """
        Requirement 6.8: Verify cross-judge aggregation with partial failures
        
        Expected: Only successful judges contribute to aggregation
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                median=5.0,
                mean=5.0,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                sample_size=0,  # All repeats failed
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_3",
                rubric_id="rubric_1",
                turn_id=None,
                median=7.0,
                mean=7.0,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # Only judge_1 and judge_3 should contribute
        assert cross_result.judge_count == 2
        assert cross_result.weighted_average == 6.0  # (5 + 7) / 2


# -------------------------------------------------------------------------
# Test: Deterministic Aggregation (Requirement 6.11)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestDeterministicAggregation:
    """Validate deterministic aggregation for identical inputs."""
    
    def test_deterministic_within_judge(self, aggregator):
        """
        Requirement 6.11: Verify within-judge aggregation is deterministic
        
        Expected: Same inputs produce identical outputs
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])
        ]
        
        # Run aggregation twice
        result_1 = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        result_2 = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        # Results should be identical
        assert result_1.median == result_2.median
        assert result_1.mean == result_2.mean
        assert result_1.variance == result_2.variance
        assert result_1.sample_size == result_2.sample_size
    
    def test_deterministic_cross_judge(self, aggregator):
        """
        Requirement 6.11: Verify cross-judge aggregation is deterministic
        
        Expected: Same inputs produce identical outputs
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                median=score,
                mean=score,
                variance=0.1,
                sample_size=3,
                scoring_type="numeric"
            )
            for i, score in enumerate([2.0, 5.0, 8.0])
        ]
        
        # Run aggregation twice
        result_1 = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        result_2 = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # Results should be identical
        assert result_1.weighted_average == result_2.weighted_average
        assert result_1.disagreement_signal == result_2.disagreement_signal
        assert result_1.high_risk_flag == result_2.high_risk_flag
        assert result_1.judge_count == result_2.judge_count
    
    def test_deterministic_categorical(self, aggregator):
        """
        Requirement 6.11: Verify categorical aggregation is deterministic
        
        Expected: Same inputs produce identical outputs
        """
        within_results = [
            WithinJudgeResult(
                judge_id=f"judge_{i}",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote=vote,
                variance=0.0,
                sample_size=3,
                scoring_type="categorical"
            )
            for i, vote in enumerate(["pass", "fail", "pass"])
        ]
        
        # Run aggregation twice
        result_1 = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        result_2 = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # Results should be identical
        assert result_1.weighted_vote == result_2.weighted_vote
        assert result_1.disagreement_signal == result_2.disagreement_signal
        assert result_1.high_risk_flag == result_2.high_risk_flag


# -------------------------------------------------------------------------
# Test: Edge Cases and Robustness
# -------------------------------------------------------------------------

@pytest.mark.component
class TestEdgeCases:
    """Validate edge cases and robustness of aggregation logic."""
    
    def test_empty_results_list(self, aggregator):
        """
        Verify aggregation handles empty results list gracefully
        
        Expected: Returns result with sample_size=0
        """
        within_result = aggregator.aggregate_within_judge(
            [], "judge_1", "rubric_1"
        )
        
        assert within_result.sample_size == 0
        assert within_result.median is None
    
    def test_empty_within_results_list(self, aggregator):
        """
        Verify cross-judge aggregation handles empty list gracefully
        
        Expected: Returns result with judge_count=0
        """
        cross_result = aggregator.aggregate_cross_judge(
            [], "rubric_1"
        )
        
        assert cross_result.judge_count == 0
        assert cross_result.weighted_average is None
    
    def test_mixed_scoring_types_error(self, aggregator):
        """
        Verify cross-judge aggregation detects mixed scoring types
        
        Expected: Sets mixed_types_error and high_risk_flag
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                median=5.0,
                mean=5.0,
                variance=0.0,
                sample_size=3,
                scoring_type="numeric"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="pass",
                variance=0.0,
                sample_size=3,
                scoring_type="categorical"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        assert cross_result.mixed_types_error is not None
        assert cross_result.high_risk_flag is True
        assert cross_result.disagreement_signal == 1.0
    
    def test_turn_id_preservation(self, aggregator):
        """
        Verify turn_id is preserved through aggregation
        
        Expected: turn_id should be maintained in results
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score, turn_id="turn_5")
            for i, score in enumerate([1.0, 2.0, 3.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1", turn_id="turn_5"
        )
        
        assert within_result.turn_id == "turn_5"
        
        cross_result = aggregator.aggregate_cross_judge(
            [within_result], "rubric_1", turn_id="turn_5"
        )
        
        assert cross_result.turn_id == "turn_5"
    
    def test_categorical_weighted_vote(self, aggregator):
        """
        Verify categorical weighted vote uses sample_size weighting
        
        Expected: Category with highest total weight wins
        """
        within_results = [
            WithinJudgeResult(
                judge_id="judge_1",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="pass",
                variance=0.0,
                sample_size=1,  # Low weight
                scoring_type="categorical"
            ),
            WithinJudgeResult(
                judge_id="judge_2",
                rubric_id="rubric_1",
                turn_id=None,
                majority_vote="fail",
                variance=0.0,
                sample_size=9,  # High weight
                scoring_type="categorical"
            )
        ]
        
        cross_result = aggregator.aggregate_cross_judge(
            within_results, "rubric_1"
        )
        
        # "fail" should win due to higher sample_size weight
        assert cross_result.weighted_vote == "fail"
        assert cross_result.judge_count == 2
    
    def test_serialization_to_dict(self, aggregator):
        """
        Verify results can be serialized to dict for JSON output
        
        Expected: to_dict() should produce valid dictionaries
        """
        results = [
            create_mock_job_result(f"job_{i}", "judge_1", "rubric_1", score)
            for i, score in enumerate([1.0, 2.0, 3.0])
        ]
        
        within_result = aggregator.aggregate_within_judge(
            results, "judge_1", "rubric_1"
        )
        
        within_dict = within_result.to_dict()
        assert isinstance(within_dict, dict)
        assert "judge_id" in within_dict
        assert "median" in within_dict
        assert "mean" in within_dict
        
        cross_result = aggregator.aggregate_cross_judge(
            [within_result], "rubric_1"
        )
        
        cross_dict = cross_result.to_dict()
        assert isinstance(cross_dict, dict)
        assert "rubric_id" in cross_dict
        assert "weighted_average" in cross_dict
        assert "disagreement_signal" in cross_dict
        assert "individual_judge_results" in cross_dict
