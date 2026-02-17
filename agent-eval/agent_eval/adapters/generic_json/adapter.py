"""
Generic JSON adapter implementation for trace normalization.

This module implements the core adapter logic for transforming Generic JSON
trace files into the normalized schema format. It uses a multi-stage pipeline:
1. Normalize: Event discovery, field mapping, timestamp parsing
2. Classify: Event kind classification (USER_INPUT, TOOL_CALL, etc.)
3. Segment: Turn segmentation for multi-turn conversations
4. Derive: Derived field calculation (latency, tool linking, etc.)

The adapter uses config-driven field mapping from adapter_config.yaml and
implements graceful degradation with confidence scoring for missing data.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import os

from .config_loader import AdapterConfig
from ...utils.validation import (
    parse_timestamp,
    sanitize_latency,
    calculate_confidence_score,
    load_schema,
    validate_against_schema
)

# Default configuration path
from . import DEFAULT_CONFIG_PATH

# Adapter version
ADAPTER_VERSION = "1.0.0"


def adapt(path: Union[str, os.PathLike], config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load a Generic JSON trace file and normalize it to the standard schema.
    
    This is the single public entry point for trace normalization.
    
    Args:
        path: Path to the Generic JSON trace file
        config_path: Optional path to adapter_config.yaml (defaults to DEFAULT_CONFIG_PATH)
        
    Returns:
        Dictionary conforming to normalized schema with:
        - run_id, metadata, adapter_stats, turns[]
        - Each turn has confidence score (0-1)
        - adapter_stats contains confidence_penalties
        
    Raises:
        FileNotFoundError: If the trace file doesn't exist
        ValueError: If the file contains invalid JSON or no events exist
        
    Behavior:
        - Graceful degradation: missing fields → null with confidence penalty
        - Config-driven field mapping from adapter_config.yaml
        - Dual latency tracking (normalized_latency_ms and runtime_reported_latency_ms)
        - Multi-turn conversation support with turn stitching
        - Orphan tool results handled with confidence penalties
        - Tool-looking text without markers not misclassified
    
    Example:
        >>> from agent_eval.adapters.generic_json import adapt
        >>> result = adapt("trace.json")
        >>> print(result["run_id"])
        'abc-123-def'
        >>> print(result["turns"][0]["confidence"])
        0.85
    """
    # Use default config if not provided
    if config_path is None:
        config_path = str(DEFAULT_CONFIG_PATH)
    
    # Load configuration
    config = AdapterConfig(config_path)
    
    # Create normalizer and process trace
    normalizer = _TraceNormalizer(config)
    return normalizer.normalize(path)


class _ConfidenceScorer:
    """
    Calculate confidence scores based on data quality.
    
    This class tracks confidence penalties during trace normalization and
    calculates final confidence scores for turns and runs. Penalties are
    deduplicated by root cause to avoid double-counting the same issue.
    
    Penalty Types:
    - missing_timestamp: 0.4 (dedupe per turn)
    - missing_grouping_ids: 0.3 (dedupe per turn)
    - no_anchor_found: 0.3 (dedupe per turn)
    - no_llm_output: 0.2 (dedupe per turn)
    - missing_latency: 0.2 (dedupe per turn, only when timestamps exist)
    - single_turn_fallback: 0.25 (dedupe per run)
    """
    
    def __init__(self, config: AdapterConfig):
        """
        Initialize confidence scorer with configuration.
        
        Args:
            config: Adapter configuration with penalty weights
        """
        self.config = config
        self.penalties: List[Dict[str, Any]] = []
        self._penalty_config = config.get_confidence_scoring_config()
        
        # Track applied penalties per turn/run with (scope, reason) keys for proper deduplication
        self._applied_penalties_per_turn: Dict[str, set] = {}
        self._applied_penalties_per_run: set = set()  # Set of (scope, reason) tuples
        self._current_turn_id: Optional[str] = None
        
        # Track trusted timestamps for debugging
        self.trusted_timestamps: int = 0
        self.valid_timestamps: int = 0
    
    def set_current_turn(self, turn_id: str) -> None:
        """
        Set the current turn context for penalty tracking.
        
        Args:
            turn_id: Turn identifier for penalty deduplication
        """
        self._current_turn_id = turn_id
        if turn_id not in self._applied_penalties_per_turn:
            self._applied_penalties_per_turn[turn_id] = set()
    
    def add_penalty(self, reason: str, location: str, scope: str = "turn") -> None:
        """
        Record a confidence penalty with scope-aware deduplication.
        
        Penalties are deduplicated by (scope, reason) to avoid double-counting
        the same issue while allowing the same reason at different scopes.
        
        Args:
            reason: Penalty reason (e.g., "missing_timestamp")
            location: Where the penalty occurred (e.g., "turn_0.event_3")
            scope: Deduplication scope - "turn" or "run"
            
        Behavior:
            - Run-level penalties: applied once per run regardless of how many turns trigger them
            - Turn-level penalties: applied once per turn, can repeat across different turns
            - Example: missing_timestamp at run-level (all turns) vs turn-level (specific turns)
        """
        # Get penalty value from config
        penalty_value = self._penalty_config["penalties"].get(reason, 0.0)
        
        # Deduplicate penalties by (scope, reason) - FIX #1: scope is now part of the key
        dedupe_key = (scope, reason)
        
        if scope == "run":
            if dedupe_key in self._applied_penalties_per_run:
                return
            self._applied_penalties_per_run.add(dedupe_key)
        elif scope == "turn" and self._current_turn_id:
            if dedupe_key in self._applied_penalties_per_turn[self._current_turn_id]:
                return
            self._applied_penalties_per_turn[self._current_turn_id].add(dedupe_key)
        
        # Record penalty with scope
        self.penalties.append({
            "reason": reason,
            "penalty": penalty_value,
            "location": location,
            "scope": scope
        })
    
    def calculate_turn_confidence(self, turn_id: str) -> float:
        """
        Calculate final confidence score (0-1) for a turn.
        
        Includes both turn-specific and run-level penalties.
        
        Args:
            turn_id: Turn identifier (e.g., "turn_0")
            
        Returns:
            Confidence score between 0 and 1
        """
        # Get penalties for this turn
        # Include all run-scope penalties + turn-scope penalties for this turn
        turn_penalties = []
        for p in self.penalties:
            scope = p.get("scope", "turn")  # Default to turn for backward compat
            location = p["location"]
            
            if scope == "run" or (scope == "turn" and location.startswith(f"{turn_id}.")):
                turn_penalties.append(p)
        
        # Calculate confidence using utility function
        base_score = self._penalty_config["base"]
        return calculate_confidence_score(turn_penalties, base_score)
    
    def get_adapter_stats(
        self,
        total_events: int,
        missing_data: int,
        turn_count: int,
        raw_path: Optional[str] = None,
        canonical_sources: Optional[Dict[str, str]] = None,
        orphan_tool_results: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Generate adapter_stats object with timestamp debugging information.
        
        Uses internal counters for timestamp stats (valid_timestamps, trusted_timestamps).
        
        Args:
            total_events: Total number of events processed
            missing_data: Number of events with missing data
            turn_count: Total number of turns segmented
            raw_path: Which event_path matched in source
            canonical_sources: Which field aliases matched per field
            orphan_tool_results: Tool results without corresponding calls
            warnings: List of warning messages
            
        Returns:
            adapter_stats dictionary with both parsed and trusted timestamp counts
        """
        stats = {
            "total_events_processed": total_events,
            "events_with_valid_timestamps": self.valid_timestamps,  # Backward compat (deprecated)
            "events_with_parsed_timestamps": self.valid_timestamps,  # New preferred name
            "events_with_trusted_timestamps": self.trusted_timestamps,  # For debugging latency issues
            "events_with_missing_data": missing_data,
            "confidence_penalties": self.penalties,
            "turn_count": turn_count
        }
        
        if raw_path:
            stats["raw_path"] = raw_path
        
        if canonical_sources:
            stats["canonical_sources"] = canonical_sources
        
        if orphan_tool_results:
            stats["orphan_tool_results"] = orphan_tool_results
        
        if warnings:
            stats["warnings"] = warnings
        
        return stats


class _TraceNormalizer:
    """
    Internal class for trace normalization logic.
    
    This class implements the multi-stage normalization pipeline:
    1. Load and parse JSON
    2. Extract events from configured paths
    3. Normalize fields using alias fallback
    4. Parse timestamps with multiple format support
    5. Classify events into kinds
    6. Segment into turns
    7. Calculate derived fields
    8. Validate against schema
    """
    
    def __init__(self, config: AdapterConfig):
        """
        Initialize trace normalizer with configuration.
        
        Args:
            config: Adapter configuration
        """
        self.config = config
        self.scorer = _ConfidenceScorer(config)
        
        # Statistics tracking (scorer owns timestamp counters)
        self.total_events = 0
        self.missing_data_count = 0
        self.matched_event_path: Optional[str] = None
        self.canonical_sources: Dict[str, str] = {}
        self.orphan_tool_results: List[Dict[str, Any]] = []
        self.warnings: List[str] = []  # Collect warnings instead of spamming
        self._schema_warning_emitted = False  # Guard for schema warnings
    
    def _flatten_list(self, data: Any) -> List[Any]:
        """
        Recursively flatten nested lists, filtering out None values.
        
        Args:
            data: Data to flatten (can be list, dict, or scalar)
            
        Returns:
            Flattened list of non-list, non-None items
        """
        if not isinstance(data, list):
            return [data] if data is not None else []
        
        result = []
        for item in data:
            if item is None:
                continue
            if isinstance(item, list):
                # Recursively flatten nested lists
                result.extend(self._flatten_list(item))
            else:
                result.append(item)
        return result
    
    def normalize(self, path: Union[str, os.PathLike]) -> Dict[str, Any]:
        """
        Transform raw Generic JSON into normalized format.
        
        Args:
            path: Path to Generic JSON trace file
            
        Returns:
            Normalized dict with run_id, metadata, adapter_stats, turns[]
            
        Raises:
            FileNotFoundError: If trace file doesn't exist
            ValueError: If JSON is invalid or no events exist
        """
        # Load JSON file
        raw_data = self._load_json(path)
        
        # Extract events from configured paths
        events = self._extract_events(raw_data)
        
        # Validate that we have events
        if not events:
            raise ValueError(
                f"No events found in trace file {path}. "
                f"Checked event paths: {self.config.get_event_paths()}"
            )
        
        # Extract run-level fields
        run_id = self._extract_run_id(raw_data, events)
        metadata = self._extract_metadata(raw_data)
        
        # Normalize events (field mapping, timestamp parsing, classification)
        normalized_events = self._normalize_events(events)
        
        # Segment into turns (placeholder for now - will be implemented in Stage B)
        turns = self._create_single_turn(normalized_events, raw_data)
        
        # Validate against schema (before generating adapter_stats to capture warnings)
        self._validate_output_structure(normalized_events, turns, run_id, metadata)
        
        # Generate adapter_stats (scorer uses its own internal counters)
        adapter_stats = self.scorer.get_adapter_stats(
            total_events=self.total_events,
            missing_data=self.missing_data_count,
            turn_count=len(turns),
            raw_path=self.matched_event_path,
            canonical_sources=self.canonical_sources,
            orphan_tool_results=self.orphan_tool_results if self.orphan_tool_results else None,
            warnings=self.warnings if self.warnings else None
        )
        
        # Build normalized output
        normalized = {
            "run_id": run_id,
            "metadata": metadata,
            "adapter_stats": adapter_stats,
            "turns": turns
        }
        
        # Final schema validation
        self._validate_output(normalized)
        
        return normalized
    
    def _validate_output_structure(
        self,
        events: List[Dict[str, Any]],
        turns: List[Dict[str, Any]],
        run_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Perform cheap invariant checks before full schema validation.
        
        These are fast sanity checks that catch integration mistakes early
        without requiring jsonschema.
        
        Args:
            events: Normalized events
            turns: Turn list
            run_id: Run identifier
            metadata: Metadata dict
        """
        # Check run_id is non-empty string
        if not run_id or not isinstance(run_id, str):
            self.warnings.append(f"Invalid run_id: expected non-empty string, got {type(run_id).__name__}")
        
        # Check turns is a list
        if not isinstance(turns, list):
            self.warnings.append(f"Invalid turns: expected list, got {type(turns).__name__}")
            return
        
        # Check each turn has required fields
        for i, turn in enumerate(turns):
            if not isinstance(turn, dict):
                self.warnings.append(f"Turn {i}: expected dict, got {type(turn).__name__}")
                continue
            
            if "turn_id" not in turn:
                self.warnings.append(f"Turn {i}: missing turn_id")
            
            if "steps" in turn and not isinstance(turn["steps"], list):
                self.warnings.append(f"Turn {i}: steps should be list, got {type(turn['steps']).__name__}")
            
            if "confidence" in turn:
                conf = turn["confidence"]
                if conf is not None:
                    try:
                        conf_float = float(conf)
                        if not (0.0 <= conf_float <= 1.0):
                            self.warnings.append(f"Turn {i}: confidence should be 0..1, got {conf}")
                    except (TypeError, ValueError):
                        self.warnings.append(f"Turn {i}: confidence should be numeric, got {type(conf).__name__}")
    
    def _load_json(self, path: Union[str, os.PathLike]) -> Dict[str, Any]:
        """
        Load and parse JSON file.
        
        Args:
            path: Path to JSON file
            
        Returns:
            Parsed JSON dictionary
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid
        """
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise FileNotFoundError(
                f"Trace file not found: {path}. "
                f"Please ensure the file exists."
            )
        
        try:
            with open(path_obj, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse JSON from {path}: {e}. "
                f"Please ensure the file contains valid JSON."
            ) from e
        except OSError as e:
            raise ValueError(
                f"Failed to read file {path}: {e}. "
                f"Check file permissions."
            ) from e
        
        if data is None:
            raise ValueError(
                f"Trace file is empty: {path}. "
                f"Please ensure the file contains valid JSON data."
            )
        
        return data
    
    def _extract_events(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract events from configured event_paths.
        
        Supports:
        - Simple paths: "events", "trace.events"
        - Nested paths with wildcards: "resourceSpans.*.scopeSpans.*.spans"
        
        Warns if multiple paths match (helps debug config changes).
        
        Args:
            data: Source JSON dictionary
            
        Returns:
            List of event dictionaries
        """
        events = []
        event_paths = self.config.get_event_paths()
        matched_paths = []
        
        for path in event_paths:
            extracted = self._extract_from_path(data, path)
            
            # Use "is not None" to handle empty lists correctly
            if extracted is not None:
                # Handle empty list case
                if isinstance(extracted, list):
                    if len(extracted) == 0:
                        # Found but empty - continue to next path
                        continue
                    # Non-empty list found
                    if not events:
                        # First match - use it
                        events.extend(extracted)
                        self.matched_event_path = path
                    else:
                        # Additional match - warn about it
                        matched_paths.append((path, len(extracted)))
                else:
                    # Single item found
                    if not events:
                        events.append(extracted)
                        self.matched_event_path = path
                    else:
                        matched_paths.append((path, 1))
        
        # Warn if multiple paths matched (helps debug config drift)
        if matched_paths:
            alt_paths_str = ", ".join(f"{p} ({n} events)" for p, n in matched_paths)
            self.warnings.append(
                f"Multiple event paths matched. Using '{self.matched_event_path}' ({len(events)} events). "
                f"Alternatives: {alt_paths_str}"
            )
        
        return events
    
    def _extract_from_path(self, data: Any, path: str) -> Optional[Union[List, Dict]]:
        """
        Extract value from nested path with wildcard support.
        
        Handles nested wildcards with proper flattening at every step.
        
        Args:
            data: Source data
            path: Dotted path (e.g., "events" or "resourceSpans.*.scopeSpans.*.spans")
            
        Returns:
            Extracted value or None
        """
        parts = path.split('.')
        current = data
        
        for part in parts:
            if current is None:
                return None
            
            if part == '*':
                # Wildcard: traverse all items in list/dict
                if isinstance(current, list):
                    # Collect all non-None items
                    results = []
                    for item in current:
                        if item is not None:
                            results.append(item)
                    current = results if results else None
                elif isinstance(current, dict):
                    # Collect all non-None values
                    results = []
                    for value in current.values():
                        if value is not None:
                            results.append(value)
                    current = results if results else None
                else:
                    return None
                
                # Flatten after wildcard traversal
                if current is not None:
                    current = self._flatten_list(current)
                    if not current:  # Empty after flattening
                        current = None
            else:
                # Regular key access
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list):
                    # Apply key to all items in list
                    results = []
                    for item in current:
                        if isinstance(item, dict):
                            value = item.get(part)
                            if value is not None:
                                results.append(value)
                    current = results if results else None
                    
                    # Flatten after list key application
                    if current is not None:
                        current = self._flatten_list(current)
                        if not current:  # Empty after flattening
                            current = None
                else:
                    return None
        
        return current
    
    def _extract_run_id(self, data: Dict[str, Any], events: List[Dict[str, Any]]) -> str:
        """
        Extract run_id using config-driven field mapping.
        
        Uses deterministic generation based on trace content if no run_id found.
        
        Args:
            data: Source JSON dictionary
            events: List of events
            
        Returns:
            Run ID string
        """
        # Try direct access first (common case)
        run_id = data.get("run_id")
        
        # If not found, try config-driven field mapping
        if not run_id:
            run_id = self.config.get_field_value_with_fallback(data, "run_id")
        
        # If not found, try first event
        if not run_id and events:
            run_id = self.config.get_field_value_with_fallback(events[0], "run_id")
        
        # If still not found, generate deterministic ID from trace content
        if not run_id:
            # Build stable hash from trace_id/session_id/request_id + first timestamp + event_count + path
            hash_parts = []
            
            # Try to get stable identifiers
            for id_field in ["trace_id", "session_id", "request_id"]:
                value = self.config.get_field_value_with_fallback(data, id_field)
                if not value and events:
                    value = self.config.get_field_value_with_fallback(events[0], id_field)
                if value:
                    hash_parts.append(f"{id_field}:{value}")
            
            # Add first timestamp if available
            if events:
                first_ts = self.config.get_field_value_with_fallback(events[0], "timestamp")
                if first_ts:
                    hash_parts.append(f"ts:{first_ts}")
            
            # Always include event count and matched path to reduce collisions
            hash_parts.append(f"event_count:{len(events)}")
            if self.matched_event_path:
                hash_parts.append(f"matched_path:{self.matched_event_path}")
            
            # Generate deterministic hash
            if hash_parts:
                content = "|".join(hash_parts)
                hash_digest = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
                run_id = f"generated_{hash_digest}"
            else:
                # Last resort: hash bounded canonical subset
                # Use top-level keys + first 3 events + size cap
                canonical_subset = {
                    "keys": sorted(data.keys()),
                    "events_sample": events[:3] if events else [],
                    "event_count": len(events)
                }
                try:
                    content = json.dumps(canonical_subset, sort_keys=True, default=str)
                    # Cap at 10KB to avoid huge traces
                    if len(content) > 10000:
                        content = content[:10000]
                    hash_digest = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
                    run_id = f"generated_{hash_digest}"
                except (TypeError, ValueError):
                    # Fallback to simple hash of keys
                    content = "|".join(sorted(data.keys()))
                    hash_digest = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
                    run_id = f"generated_{hash_digest}"
            
            self.warnings.append(f"No run_id found in trace. Using generated ID: {run_id}")
        
        return str(run_id)
    
    def _extract_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract run-level metadata.
        
        Args:
            data: Source JSON dictionary
            
        Returns:
            Metadata dictionary
        """
        metadata = {
            "adapter_version": ADAPTER_VERSION,
            "runtime": {
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Extract optional source field
        source = self.config.get_field_value_with_fallback(data, "source")
        if source:
            metadata["source"] = str(source)
        
        return metadata
    
    def _normalize_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize events: field mapping, timestamp parsing, classification.
        
        Sorts events deterministically by: ts_trusted desc, start_ts_epoch_ms asc, source_index asc.
        
        Args:
            events: Raw event list
            
        Returns:
            List of normalized and sorted events with canonical fields
        """
        normalized = []
        
        for idx, event in enumerate(events):
            self.total_events += 1
            
            # Normalize single event
            normalized_event = self._normalize_event(event, idx)
            normalized.append(normalized_event)
        
        # Sort events deterministically using numeric epoch for reliable ordering
        def sort_key(evt):
            ts_trusted = evt.get("ts_trusted", False)
            start_ts_epoch_ms = evt.get("start_ts_epoch_ms")
            source_index = evt.get("source_index", 0)
            
            # Sort by: ts_trusted (desc), start_ts_epoch_ms (asc, None last), source_index (asc)
            return (
                not ts_trusted,  # False (trusted) sorts before True (untrusted)
                start_ts_epoch_ms if start_ts_epoch_ms is not None else float('inf'),  # None sorts last
                source_index
            )
        
        normalized.sort(key=sort_key)
        
        # Update event_order after sorting
        for order, event in enumerate(normalized):
            event["event_order"] = order
        
        return normalized
    
    def _normalize_event(self, event: Dict[str, Any], source_index: int) -> Dict[str, Any]:
        """
        Normalize a single event with field mapping and timestamp parsing.
        
        Args:
            event: Raw event dictionary
            source_index: Original position in event list
            
        Returns:
            Normalized event dictionary with metadata for penalty tracking
        """
        normalized = {
            "source_index": source_index,
            "event_order": source_index,  # Will be updated during segmentation
            "raw": {},
            "start_ts_epoch_ms": None,  # For numeric sorting
            "_has_trusted_ts": False,  # Metadata for penalty tracking
            "_has_grouping_id": False  # Metadata for penalty tracking
        }
        
        # Extract and parse timestamp
        timestamp_value = self.config.get_field_value_with_fallback(event, "timestamp")
        ts_config = self.config.get_timestamp_parse_config()
        
        # Check if this is a UnixNano field
        field_name = None
        matched_alias = None
        for unix_nano_field in ts_config["unix_nano_fields"]:
            if unix_nano_field in event:
                field_name = unix_nano_field
                timestamp_value = event[unix_nano_field]
                matched_alias = unix_nano_field
                break
        
        if timestamp_value is not None:
            dt, is_trusted, error = parse_timestamp(
                timestamp_value,
                formats=ts_config["formats"],
                epoch_units=ts_config["epoch_units"],
                infer_epoch_unit_by_magnitude=ts_config["infer_epoch_unit_by_magnitude"],
                min_reasonable_year=ts_config["min_reasonable_year"],
                max_reasonable_year=ts_config["max_reasonable_year"],
                unix_nano_fields=ts_config["unix_nano_fields"],
                field_name=field_name
            )
            
            if dt:
                # Ensure timezone-aware for epoch conversion
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                
                normalized["start_ts"] = dt.isoformat()
                normalized["start_ts_epoch_ms"] = int(dt.timestamp() * 1000)  # Integer for precision
                normalized["ts_trusted"] = is_trusted
                normalized["_has_trusted_ts"] = is_trusted
                
                # Update scorer counters (single source of truth)
                self.scorer.valid_timestamps += 1
                if is_trusted:
                    self.scorer.trusted_timestamps += 1
                
                # Track which alias matched
                if not matched_alias:
                    for alias in self.config.get_field_aliases("timestamp"):
                        if self._extract_from_path(event, alias) is not None:
                            matched_alias = alias
                            break
                if matched_alias and "timestamp" not in self.canonical_sources:
                    self.canonical_sources["timestamp"] = matched_alias
            else:
                normalized["start_ts"] = None
                normalized["ts_trusted"] = False
                self.missing_data_count += 1
                # Log parse error for debugging (bounded)
                if error and len(self.warnings) < 100:  # Limit warnings
                    self.warnings.append(f"Timestamp parse failed for event {source_index}: {error}")
        else:
            normalized["start_ts"] = None
            normalized["ts_trusted"] = False
            self.missing_data_count += 1
        
        # Extract identifiers with canonical source tracking
        for field in ["session_id", "trace_id", "span_id", "parent_span_id", "request_id", "turn_id"]:
            value = self.config.get_field_value_with_fallback(event, field)
            if value is not None:
                normalized[field] = str(value)
                if field in ["session_id", "trace_id", "request_id", "turn_id"]:
                    normalized["_has_grouping_id"] = True
                # Track which alias matched (first match only)
                if field not in self.canonical_sources:
                    for alias in self.config.get_field_aliases(field):
                        if self._extract_from_path(event, alias) is not None:
                            self.canonical_sources[field] = alias
                            break
        
        # Extract event typing fields
        for field in ["event_type", "operation"]:
            value = self.config.get_field_value_with_fallback(event, field)
            if value is not None:
                normalized[field] = str(value)
        
        # Extract tool fields
        for field in ["tool_name", "tool_run_id", "tool_result", "tool_input", "tool_arguments"]:
            value = self.config.get_field_value_with_fallback(event, field)
            if value is not None:
                normalized[field] = value
        
        # Extract model/message fields
        for field in ["role", "span_kind", "model_id", "text"]:
            value = self.config.get_field_value_with_fallback(event, field)
            if value is not None:
                normalized[field] = value
        
        # Extract step fields
        status = self.config.get_field_value_with_fallback(event, "status")
        if status:
            normalized["status"] = str(status)
        
        latency = self.config.get_field_value_with_fallback(event, "latency_ms")
        if latency is not None:
            sanitized = sanitize_latency(latency)
            if sanitized is not None:
                normalized["latency_ms"] = float(sanitized)
        
        # Classify event
        kind, rule_id = self.config.classify_event(event)
        normalized["kind"] = kind
        if rule_id:
            normalized["kind_rule_id"] = rule_id
        
        # Preserve raw data (byte-safe size check with safe serialization)
        carry_config = self.config.get_carry_fields_config()
        if carry_config["keep_raw_event"]:
            # Limit raw event size (byte-safe, handle non-serializable)
            try:
                raw_json = json.dumps(event, default=str)
                raw_bytes = raw_json.encode('utf-8')
                max_bytes = carry_config["raw_event_max_bytes"]
                if len(raw_bytes) <= max_bytes:
                    # Store serialized version for robustness
                    normalized["raw"] = json.loads(raw_json)
                else:
                    normalized["raw"] = {"truncated": True, "size_bytes": len(raw_bytes)}
            except (TypeError, ValueError) as e:
                normalized["raw"] = {"error": f"Serialization failed: {str(e)[:100]}"}
        
        # Extract attributes (check for None and dict type)
        attributes = {}
        for attr_path in carry_config["attributes_paths"]:
            attr_value = self._extract_from_path(event, attr_path)
            if attr_value is not None and isinstance(attr_value, dict):
                attributes.update(attr_value)
        
        if attributes:
            normalized["attributes"] = attributes
        
        return normalized
    
    def _create_single_turn(
        self,
        events: List[Dict[str, Any]],
        raw_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create a single turn from all events (placeholder for Stage B segmentation).
        
        This is a temporary implementation that treats all events as a single turn.
        Stage B (Segment) will implement proper multi-turn segmentation.
        
        Args:
            events: Normalized events
            raw_data: Original JSON data
            
        Returns:
            List containing single turn
        """
        turn_id = "turn_0"
        self.scorer.set_current_turn(turn_id)
        
        # Add run-level penalty for single-turn fallback
        self.scorer.add_penalty("single_turn_fallback", f"{turn_id}.segmentation", scope="run")
        
        # Check for missing trusted timestamps (once per turn)
        has_any_trusted_ts = any(evt.get("_has_trusted_ts") for evt in events)
        if not has_any_trusted_ts:
            self.scorer.add_penalty("missing_timestamp", f"{turn_id}.timestamps", scope="turn")
        else:
            # Check timestamp coverage: "trusted among parsed" ratio
            # Use per-turn counts (Stage B compatible)
            parsed_ts_count = sum(1 for evt in events if evt.get("start_ts") is not None)
            trusted_ts_count = sum(1 for evt in events if evt.get("_has_trusted_ts"))
            trusted_among_parsed = trusted_ts_count / max(1, parsed_ts_count)
            # Only apply low-coverage penalty if we have parsed timestamps but low trust ratio
            if parsed_ts_count > 0 and trusted_among_parsed < 0.2:
                self.scorer.add_penalty("missing_timestamp_low_coverage", f"{turn_id}.timestamps", scope="turn")
        
        # Check for missing grouping IDs (once per turn)
        # Use per-turn counts (Stage B compatible)
        has_any_grouping_id = any(evt.get("_has_grouping_id") for evt in events)
        grouping_id_count = sum(1 for evt in events if evt.get("_has_grouping_id"))
        
        if not has_any_grouping_id:
            self.scorer.add_penalty("missing_grouping_ids", f"{turn_id}.identifiers", scope="turn")
        else:
            # Check grouping ID coverage
            grouping_ratio = grouping_id_count / max(1, len(events))
            # Only apply low-coverage penalty if at least some grouping IDs were seen
            if grouping_id_count > 0 and grouping_ratio < 0.2:
                self.scorer.add_penalty("missing_grouping_ids_low_coverage", f"{turn_id}.identifiers", scope="turn")
        
        # Extract top-level fields - try direct access first
        user_query = raw_data.get("user_query")
        if not user_query:
            user_query = self.config.get_field_value_with_fallback(raw_data, "user_query")
        
        final_answer = raw_data.get("final_answer")
        if not final_answer:
            final_answer = self.config.get_field_value_with_fallback(raw_data, "final_answer")
        
        # Check for LLM output (stricter heuristic)
        has_llm_output = bool(final_answer) or any(
            evt.get("kind") in ["LLM_OUTPUT_CHUNK", "ASSISTANT_MESSAGE", "FINAL_RESPONSE"] 
            for evt in events
        )
        if not has_llm_output:
            self.scorer.add_penalty("no_llm_output", f"{turn_id}.output", scope="turn")
        
        # Convert events to steps
        steps = []
        for event in events:
            step = self._event_to_step(event)
            steps.append(step)
        
        # Calculate latency
        normalized_latency = self._calculate_normalized_latency(events)
        runtime_latency = self.config.get_field_value_with_fallback(raw_data, "total_latency_ms")
        if runtime_latency is not None:
            runtime_latency = sanitize_latency(runtime_latency)
            if runtime_latency is not None:
                runtime_latency = float(runtime_latency)
        
        # FIX #4: Check if we have at least 2 trusted timestamps but missing latency (invariant violation)
        trusted_ts_count = sum(1 for evt in events if evt.get("_has_trusted_ts"))
        if trusted_ts_count >= 2 and normalized_latency is None:
            # This should not happen - log warning and apply penalty
            self.warnings.append(f"{turn_id}: trusted timestamps present but latency could not be computed")
            self.scorer.add_penalty("missing_latency", f"{turn_id}.latency", scope="turn")
        
        # Calculate confidence
        confidence = self.scorer.calculate_turn_confidence(turn_id)
        
        turn = {
            "turn_id": turn_id,
            "user_query": str(user_query) if user_query else None,
            "final_answer": str(final_answer) if final_answer else None,
            "steps": steps,
            "confidence": confidence,
            "normalized_latency_ms": normalized_latency,
            "runtime_reported_latency_ms": runtime_latency
        }
        
        return [turn]
    
    def _strip_internal_fields(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip internal metadata fields (starting with _) from object.
        
        This prevents internal tracking fields from leaking into output.
        Used in Stage B/C when emitting enriched events.
        
        Args:
            obj: Dictionary potentially containing internal fields
            
        Returns:
            Dictionary with internal fields removed
        """
        return {k: v for k, v in obj.items() if not k.startswith("_")}
    
    def _json_safe(self, value: Any) -> Any:
        """
        Ensure value is JSON-serializable.
        
        Attempts to serialize and returns the value if successful,
        otherwise converts to string representation.
        
        Args:
            value: Value to make JSON-safe
            
        Returns:
            JSON-serializable value
        """
        if value is None:
            return None
        
        try:
            # Test if serializable
            json.dumps(value, default=str)
            return value
        except (TypeError, ValueError):
            # Fallback to string representation
            return str(value)
    
    def _event_to_step(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert normalized event to step format.
        
        Strips internal metadata fields (_has_*, _*) and ensures JSON-safe output.
        
        Args:
            event: Normalized event
            
        Returns:
            Step dictionary with JSON-safe fields
        """
        # Prefer tool_name, then event_type, then operation for better readability
        name = event.get("tool_name") or event.get("event_type") or event.get("operation") or "unknown"
        
        # Ensure attributes are JSON-safe (dict with primitive values)
        attributes = event.get("attributes")
        if attributes is not None:
            if isinstance(attributes, dict):
                # Make each attribute value JSON-safe
                attributes = {k: self._json_safe(v) for k, v in attributes.items()}
            else:
                # Not a dict - convert to safe representation
                attributes = None
        
        step = {
            "name": name,
            "status": event.get("status") or "success",
            "type": event.get("event_type"),
            "kind": event.get("kind"),
            "start_ts": event.get("start_ts"),
            "end_ts": None,  # Not populated in Stage A - will be added in later stages
            "latency_ms": event.get("latency_ms"),
            "span_id": event.get("span_id"),
            "parent_span_id": event.get("parent_span_id"),
            "tool_run_id": event.get("tool_run_id"),
            "attributes": attributes,  # JSON-safe dict or None
            "raw": None  # Don't duplicate raw in step - already in event
        }
        
        return step
    
    def _calculate_normalized_latency(self, events: List[Dict[str, Any]]) -> Optional[float]:
        """
        Calculate normalized latency from trusted timestamps using epoch ms.
        
        Uses min/max over all trusted timestamps for robustness.
        
        Args:
            events: List of normalized events (should be sorted)
            
        Returns:
            Latency in milliseconds or None
        """
        # Collect all trusted timestamps (use min/max for safety)
        trusted_timestamps = []
        
        for event in events:
            if event.get("ts_trusted") and event.get("start_ts_epoch_ms") is not None:
                trusted_timestamps.append(event["start_ts_epoch_ms"])
        
        if len(trusted_timestamps) >= 2:
            return max(trusted_timestamps) - min(trusted_timestamps)
        
        return None
    
    def _validate_output(self, normalized: Dict[str, Any]) -> None:
        """
        Validate output against normalized schema.
        
        Args:
            normalized: Normalized trace dictionary
            
        Raises:
            ValueError: If validation fails
        """
        # Try to load and validate against schema
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "normalized_run.schema.json"
        
        if not schema_path.exists():
            if not self._schema_warning_emitted:
                self.warnings.append("Schema file not found. Skipping validation.")
                self._schema_warning_emitted = True
            return
        
        try:
            schema = load_schema(str(schema_path))
            is_valid, errors = validate_against_schema(normalized, schema)
            
            if not is_valid:
                error_msg = "Schema validation failed:\n" + "\n".join(errors)
                raise ValueError(error_msg)
        except ImportError:
            if not self._schema_warning_emitted:
                self.warnings.append("jsonschema library not installed. Skipping validation.")
                self._schema_warning_emitted = True
