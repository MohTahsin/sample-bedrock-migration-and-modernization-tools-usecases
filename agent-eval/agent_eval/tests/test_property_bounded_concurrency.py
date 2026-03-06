"""
Property Test: Bounded Concurrency Enforcement

Property 18: For any Worker_Pool execution, the number of concurrent jobs
must never exceed the configured concurrency limit.

Validates: Requirements 5.1

This test uses hypothesis to generate various job configurations and
verifies that the WorkerPool respects the max_concurrency limit by
tracking concurrent execution count.
"""

import asyncio
import pytest
import tempfile
import os
from typing import Dict, List
from unittest.mock import AsyncMock
from hypothesis import given, strategies as st, settings, assume

from agent_eval.evaluators.trace_eval.judging.models import JudgeJob, JobResult
from agent_eval.evaluators.trace_eval.judging.queue_runner import WorkerPool
from agent_eval.judges.judge_client import JudgeClient, JudgeResponse


class ConcurrencyTrackingJudgeClient(JudgeClient):
    """
    Mock judge client that tracks concurrent execution count.
    
    This client records the maximum concurrent execution count
    to verify bounded concurrency enforcement.
    """
    
    def __init__(
        self,
        judge_id: str,
        model_id: str = "mock-model",
        params: Dict = None,
        timeout_seconds: int = 30,
        execution_delay_ms: float = 10.0
    ):
        super().__init__(judge_id, model_id, params or {}, timeout_seconds)
        self.execution_delay_ms = execution_delay_ms
        
        # Shared state for tracking concurrency
        self.current_concurrent = 0
        self.max_concurrent_observed = 0
        self.lock = asyncio.Lock()
    
    async def execute_judge(
        self,
        prompt: str,
        rubric_id: str,
        scoring_scale: Dict
    ) -> JudgeResponse:
        """
        Execute with concurrency tracking.
        
        Increments counter on entry, decrements on exit,
        and tracks the maximum concurrent count observed.
        """
        async with self.lock:
            self.current_concurrent += 1
            if self.current_concurrent > self.max_concurrent_observed:
                self.max_concurrent_observed = self.current_concurrent
        
        try:
            # Simulate execution delay
            await asyncio.sleep(self.execution_delay_ms / 1000.0)
            
            # Return mock response
            return JudgeResponse(
                score=5,
                reasoning="Mock evaluation",
                raw_response={"score": 5, "reasoning": "Mock evaluation"},
                latency_ms=self.execution_delay_ms,
                metadata={}
            )
        finally:
            async with self.lock:
                self.current_concurrent -= 1
    
    async def validate_response(
        self,
        response: Dict,
        scoring_scale: Dict
    ) -> bool:
        """Mock validation always returns True."""
        return True


def create_test_job(
    job_index: int,
    run_id: str = "test-run",
    judge_id: str = "judge-1",
    rubric_id: str = "TEST_RUBRIC"
) -> JudgeJob:
    """Create a test JudgeJob with minimal payload."""
    return JudgeJob(
        job_id=f"job-{job_index}",
        run_id=run_id,
        turn_id=f"turn-{job_index % 3}",  # Cycle through 3 turns
        rubric_id=rubric_id,
        judge_id=judge_id,
        repeat_index=0,
        prompt_payload={
            "evidence": {"test": f"data-{job_index}"},
            "rubric_description": "Test rubric",
            "scoring_scale": {"type": "numeric", "min": 0, "max": 5}
        }
    )


@pytest.mark.property
@given(
    max_concurrency=st.integers(min_value=1, max_value=20),
    num_jobs=st.integers(min_value=1, max_value=50),
    execution_delay_ms=st.floats(min_value=5.0, max_value=50.0)
)
@settings(max_examples=100, deadline=None)
def test_property_bounded_concurrency_enforcement(
    max_concurrency: int,
    num_jobs: int,
    execution_delay_ms: float
):
    """
    Property 18: Bounded Concurrency Enforcement
    
    For any Worker_Pool execution with max_concurrency=N, the number
    of concurrent jobs must never exceed N.
    
    Strategy:
    1. Create a WorkerPool with max_concurrency=N
    2. Create M jobs (where M may be > N)
    3. Use a tracking judge client that records concurrent execution count
    4. Execute all jobs
    5. Verify max_concurrent_observed <= max_concurrency
    
    Args:
        max_concurrency: Maximum concurrent jobs (1-20)
        num_jobs: Number of jobs to execute (1-50)
        execution_delay_ms: Simulated execution time per job (5-50ms)
    """
    # Skip trivial cases where num_jobs <= max_concurrency
    # (concurrency limit not tested)
    assume(num_jobs > max_concurrency)
    
    async def run_test():
        # Create tracking judge client
        judge_client = ConcurrencyTrackingJudgeClient(
            judge_id="test-judge",
            execution_delay_ms=execution_delay_ms
        )
        
        # Create WorkerPool with specified max_concurrency
        worker_pool = WorkerPool(
            judge_clients={"test-judge": judge_client},
            max_concurrency=max_concurrency,
            default_timeout_seconds=10
        )
        
        # Create test jobs
        jobs = [
            create_test_job(i, judge_id="test-judge")
            for i in range(num_jobs)
        ]
        
        # Create temporary output file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False
        ) as f:
            output_path = f.name
        
        try:
            # Execute jobs
            result = await worker_pool.execute(
                jobs=jobs,
                output_path=output_path,
                resume=False
            )
            
            # Property: max_concurrent_observed must never exceed max_concurrency
            assert judge_client.max_concurrent_observed <= max_concurrency, (
                f"Concurrency limit violated: observed {judge_client.max_concurrent_observed} "
                f"concurrent jobs, but max_concurrency={max_concurrency}"
            )
            
            # Additional invariants
            assert result.total_job_count == num_jobs
            assert result.successful_job_count == num_jobs
            assert result.failed_job_count == 0
            
            # Verify all jobs completed (no jobs left in flight)
            assert judge_client.current_concurrent == 0, (
                f"Jobs still in flight: {judge_client.current_concurrent}"
            )
            
        finally:
            # Cleanup
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    # Run the async test
    asyncio.run(run_test())


@pytest.mark.property
@given(
    max_concurrency=st.integers(min_value=1, max_value=10),
    num_judges=st.integers(min_value=1, max_value=5),
    jobs_per_judge=st.integers(min_value=2, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_property_bounded_concurrency_multi_judge(
    max_concurrency: int,
    num_judges: int,
    jobs_per_judge: int
):
    """
    Property 18 (Multi-Judge Variant): Bounded Concurrency with Multiple Judges
    
    For any Worker_Pool execution with max_concurrency=N and multiple judges,
    the total number of concurrent jobs across all judges must never exceed N.
    
    This tests that the concurrency limit is global, not per-judge.
    
    Args:
        max_concurrency: Maximum concurrent jobs (1-10)
        num_judges: Number of different judges (1-5)
        jobs_per_judge: Jobs per judge (2-10)
    """
    total_jobs = num_judges * jobs_per_judge
    
    # Skip if total jobs don't exceed concurrency (trivial case)
    assume(total_jobs > max_concurrency)
    
    async def run_test():
        # Create tracking judge clients (one per judge)
        judge_clients = {}
        shared_state = {
            'current_concurrent': 0,
            'max_concurrent_observed': 0,
            'lock': asyncio.Lock()
        }
        
        for judge_idx in range(num_judges):
            judge_id = f"judge-{judge_idx}"
            
            # Create client with shared concurrency tracking
            client = ConcurrencyTrackingJudgeClient(
                judge_id=judge_id,
                execution_delay_ms=10.0
            )
            
            # Override with shared state for global tracking
            client.current_concurrent = shared_state['current_concurrent']
            client.max_concurrent_observed = shared_state['max_concurrent_observed']
            client.lock = shared_state['lock']
            
            # Monkey-patch to update shared state
            original_execute = client.execute_judge
            
            async def execute_with_shared_tracking(
                prompt: str,
                rubric_id: str,
                scoring_scale: Dict,
                _client=client,
                _original=original_execute
            ):
                async with shared_state['lock']:
                    shared_state['current_concurrent'] += 1
                    if shared_state['current_concurrent'] > shared_state['max_concurrent_observed']:
                        shared_state['max_concurrent_observed'] = shared_state['current_concurrent']
                
                try:
                    return await _original(prompt, rubric_id, scoring_scale)
                finally:
                    async with shared_state['lock']:
                        shared_state['current_concurrent'] -= 1
            
            client.execute_judge = execute_with_shared_tracking
            judge_clients[judge_id] = client
        
        # Create WorkerPool
        worker_pool = WorkerPool(
            judge_clients=judge_clients,
            max_concurrency=max_concurrency,
            default_timeout_seconds=10
        )
        
        # Create jobs distributed across judges
        jobs = []
        job_id = 0
        for judge_idx in range(num_judges):
            judge_id = f"judge-{judge_idx}"
            for _ in range(jobs_per_judge):
                jobs.append(create_test_job(job_id, judge_id=judge_id))
                job_id += 1
        
        # Create temporary output file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False
        ) as f:
            output_path = f.name
        
        try:
            # Execute jobs
            result = await worker_pool.execute(
                jobs=jobs,
                output_path=output_path,
                resume=False
            )
            
            # Property: Global max_concurrent_observed must never exceed max_concurrency
            assert shared_state['max_concurrent_observed'] <= max_concurrency, (
                f"Global concurrency limit violated: observed "
                f"{shared_state['max_concurrent_observed']} concurrent jobs across "
                f"{num_judges} judges, but max_concurrency={max_concurrency}"
            )
            
            # Additional invariants
            assert result.total_job_count == total_jobs
            assert result.successful_job_count == total_jobs
            assert result.failed_job_count == 0
            
            # Verify all jobs completed
            assert shared_state['current_concurrent'] == 0
            
        finally:
            # Cleanup
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    # Run the async test
    asyncio.run(run_test())


@pytest.mark.property
def test_property_bounded_concurrency_edge_case_one():
    """
    Property 18 (Edge Case): max_concurrency=1 enforces sequential execution
    
    When max_concurrency=1, jobs must execute sequentially (one at a time).
    """
    async def run_test():
        judge_client = ConcurrencyTrackingJudgeClient(
            judge_id="test-judge",
            execution_delay_ms=20.0
        )
        
        worker_pool = WorkerPool(
            judge_clients={"test-judge": judge_client},
            max_concurrency=1,
            default_timeout_seconds=10
        )
        
        # Create 10 jobs
        jobs = [create_test_job(i, judge_id="test-judge") for i in range(10)]
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False
        ) as f:
            output_path = f.name
        
        try:
            result = await worker_pool.execute(
                jobs=jobs,
                output_path=output_path,
                resume=False
            )
            
            # Property: With max_concurrency=1, max_concurrent_observed must be exactly 1
            assert judge_client.max_concurrent_observed == 1, (
                f"Expected sequential execution (max_concurrent=1), but observed "
                f"{judge_client.max_concurrent_observed} concurrent jobs"
            )
            
            assert result.successful_job_count == 10
            
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    # Run the async test
    asyncio.run(run_test())


@pytest.mark.property
def test_property_bounded_concurrency_edge_case_high():
    """
    Property 18 (Edge Case): High max_concurrency with few jobs
    
    When max_concurrency > num_jobs, all jobs can run concurrently.
    """
    async def run_test():
        num_jobs = 5
        max_concurrency = 20
        
        judge_client = ConcurrencyTrackingJudgeClient(
            judge_id="test-judge",
            execution_delay_ms=50.0  # Longer delay to ensure overlap
        )
        
        worker_pool = WorkerPool(
            judge_clients={"test-judge": judge_client},
            max_concurrency=max_concurrency,
            default_timeout_seconds=10
        )
        
        jobs = [create_test_job(i, judge_id="test-judge") for i in range(num_jobs)]
        
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.jsonl',
            delete=False
        ) as f:
            output_path = f.name
        
        try:
            result = await worker_pool.execute(
                jobs=jobs,
                output_path=output_path,
                resume=False
            )
            
            # Property: max_concurrent_observed should equal num_jobs (all ran concurrently)
            # or be close to it (due to timing)
            assert judge_client.max_concurrent_observed >= num_jobs - 1, (
                f"Expected ~{num_jobs} concurrent jobs with high max_concurrency, "
                f"but observed {judge_client.max_concurrent_observed}"
            )
            
            # Still must not exceed max_concurrency
            assert judge_client.max_concurrent_observed <= max_concurrency
            
            assert result.successful_job_count == num_jobs
            
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    # Run the async test
    asyncio.run(run_test())
