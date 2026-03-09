"""
Test utilities for production gate testing.

This module provides helper functions for:
- Comparing results excluding volatile fields
- Loading expected outcomes
- Counting tool calls/results
- Calculating confidence scores
- Environment-specific performance thresholds
"""

import copy
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional


# Volatile fields excluded from determinism checks
# These fields are expected to vary between runs
VOLATILE_FIELDS = [
    "metadata.processed_at",  # Timestamp of processing
]

# Optionally volatile fields (fixture-specific)
# Only exclude these for specific fixtures where they are non-deterministic
OPTIONALLY_VOLATILE_FIELDS = {
    "run_id": "only when generated from unstable input (e.g., random UUID)",
    "metadata.adapter_version": "only when using build-stamped versions in test runs",
}

# Note: By default, run_id and adapter_version should be deterministic and comparable.
# Only exclude them for specific fixtures where non-determinism is intentional.


def deep_copy_excluding_fields(data: Dict[str, Any], exclude_paths: List[str]) -> Dict[str, Any]:
    """
    Deep copy a dictionary excluding specified field paths.
    
    Args:
        data: Input dictionary
        exclude_paths: List of dot-notation paths to exclude (e.g., "metadata.processed_at")
    
    Returns:
        Deep copy with excluded fields removed
    """
    result = copy.deepcopy(data)
    
    for path in exclude_paths:
        parts = path.split(".")
        current = result
        
        # Navigate to parent
        for part in parts[:-1]:
            if part in current and isinstance(current[part], dict):
                current = current[part]
            else:
                break
        else:
            # Remove final key
            if parts[-1] in current:
                del current[parts[-1]]
    
    return result


def compare_results_excluding_volatile(result1: Dict[str, Any], result2: Dict[str, Any]) -> bool:
    """
    Compare two results excluding volatile fields.
    
    Args:
        result1: First result
        result2: Second result
    
    Returns:
        True if results are identical (excluding volatile fields)
    """
    r1 = deep_copy_excluding_fields(result1, VOLATILE_FIELDS)
    r2 = deep_copy_excluding_fields(result2, VOLATILE_FIELDS)
    return r1 == r2


def load_expected_outcomes(trace_id: str, manifest_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load expected outcomes for a real trace from manifest.
    
    Args:
        trace_id: Trace identifier (e.g., "cloudwatch_agentcore_001")
        manifest_path: Optional path to manifest.yaml
    
    Returns:
        Expected outcomes dictionary
    """
    if manifest_path is None:
        manifest_path = Path(__file__).parent.parent.parent / "test-fixtures" / "production-gates-phase2" / "real-traces" / "manifest.yaml"
    
    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)
    
    for trace in manifest["traces"]:
        if trace["trace_id"] == trace_id:
            return trace["expected_outcomes"]
    
    raise ValueError(f"Trace {trace_id} not found in manifest")


def count_tool_calls(result: Dict[str, Any]) -> int:
    """
    Count total tool calls across all turns.
    
    Args:
        result: Normalized adapter output
    
    Returns:
        Total number of tool calls
    """
    count = 0
    for turn in result.get("turns", []):
        for step in turn.get("steps", []):
            if step.get("kind") == "TOOL_CALL":
                count += 1
    return count


def count_tool_results(result: Dict[str, Any]) -> int:
    """
    Count total tool results across all turns.
    
    Args:
        result: Normalized adapter output
    
    Returns:
        Total number of tool results
    """
    count = 0
    for turn in result.get("turns", []):
        for step in turn.get("steps", []):
            if step.get("kind") == "TOOL_RESULT":
                count += 1
    return count


def calculate_avg_confidence(result: Dict[str, Any]) -> float:
    """
    Calculate average confidence score across all turns.
    
    Args:
        result: Normalized adapter output
    
    Returns:
        Average confidence score (0.0 to 1.0)
    """
    confidences = []
    for turn in result.get("turns", []):
        conf = turn.get("confidence")
        if conf is not None:
            confidences.append(conf)
    
    if not confidences:
        return 0.0
    
    return sum(confidences) / len(confidences)


def extract_confidences(result: Dict[str, Any]) -> List[float]:
    """
    Extract confidence scores from all turns.
    
    Args:
        result: Normalized adapter output
    
    Returns:
        List of confidence scores
    """
    return [turn.get("confidence") for turn in result.get("turns", [])]


def extract_step_order(result: Dict[str, Any]) -> List[List[str]]:
    """
    Extract step ordering from all turns.
    
    Args:
        result: Normalized adapter output
    
    Returns:
        List of step kind lists per turn
    """
    return [
        [step.get("kind") for step in turn.get("steps", [])]
        for turn in result.get("turns", [])
    ]


def all_identical(results: List[Dict[str, Any]]) -> bool:
    """
    Check if all results are identical (excluding volatile fields).
    
    Args:
        results: List of adapter outputs
    
    Returns:
        True if all results are identical
    """
    if len(results) < 2:
        return True
    
    first = results[0]
    for result in results[1:]:
        if not compare_results_excluding_volatile(first, result):
            return False
    
    return True


def all_valid_schema(results: List[Dict[str, Any]]) -> bool:
    """
    Check if all results have valid schema structure.
    
    Args:
        results: List of adapter outputs
    
    Returns:
        True if all have required fields
    """
    for result in results:
        if "turns" not in result:
            return False
        if "adapter_stats" not in result:
            return False
        if not isinstance(result["turns"], list):
            return False
    
    return True


# Performance threshold management

DEFAULT_THRESHOLDS = {
    "macos_m1": {
        "1k_events": 5.0,
        "10k_events": 30.0,
        "large_payloads_time": 10.0,
        "large_payloads_memory": 524288000,  # 500MB
    },
    "github_actions": {
        "1k_events": 10.0,
        "10k_events": 60.0,
        "large_payloads_time": 20.0,
        "large_payloads_memory": 1073741824,  # 1GB
    },
    "lambda": {
        "1k_events": 8.0,
        "10k_events": 45.0,
        "large_payloads_time": 15.0,
        "large_payloads_memory": 786432000,  # 750MB
    },
}


def get_performance_threshold(metric: str, default: float, environment: Optional[str] = None) -> float:
    """
    Get environment-specific performance threshold.
    
    Args:
        metric: Metric name (e.g., "1k_events", "10k_events")
        default: Default threshold if environment not found
        environment: Environment name (e.g., "macos_m1", "github_actions")
    
    Returns:
        Performance threshold for the metric
    """
    if environment is None:
        # Auto-detect environment
        import platform
        if platform.system() == "Darwin" and "arm" in platform.machine().lower():
            environment = "macos_m1"
        else:
            environment = "github_actions"
    
    thresholds = DEFAULT_THRESHOLDS.get(environment, {})
    return thresholds.get(metric, default)


def load_performance_thresholds(config_path: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """
    Load performance thresholds from configuration file.
    
    Args:
        config_path: Optional path to performance_thresholds.yaml
    
    Returns:
        Dictionary of environment-specific thresholds
    """
    if config_path is None:
        config_path = Path(__file__).parent.parent.parent / "test-fixtures" / "production-gates-phase2" / "performance_thresholds.yaml"
    
    if not config_path.exists():
        return DEFAULT_THRESHOLDS
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    return config.get("environments", DEFAULT_THRESHOLDS)
