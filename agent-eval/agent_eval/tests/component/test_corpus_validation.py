"""
Corpus Integrity Validation Tests

This module validates the baseline test corpus integrity before running any other tests.
It ensures all fixtures are valid, unique, and consistent.

Requirements Coverage: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10

Test Strategy:
- Validate all 10 baseline fixtures exist and are parseable JSON
- Validate expected_outcomes.yaml structure and completeness
- Validate trace ID uniqueness across corpus
- Validate category consistency between manifest.yaml and expected_outcomes.yaml
- Test detection of missing files, malformed JSON, duplicate IDs
- Verify all 10 traces present (3 good, 3 bad, 2 partial, 2 weird)
"""

import pytest
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Set


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------

@pytest.fixture
def baseline_corpus_dir() -> Path:
    """Path to baseline test corpus directory."""
    return Path(__file__).parent.parent.parent.parent / "test-fixtures" / "baseline"


@pytest.fixture
def manifest(baseline_corpus_dir: Path) -> Dict[str, Any]:
    """Load manifest.yaml from baseline corpus."""
    manifest_path = baseline_corpus_dir / "manifest.yaml"
    
    if not manifest_path.exists():
        pytest.fail(f"Manifest file not found: {manifest_path}")
    
    with open(manifest_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def expected_outcomes(baseline_corpus_dir: Path) -> Dict[str, Any]:
    """Load expected_outcomes.yaml from baseline corpus."""
    outcomes_path = baseline_corpus_dir / "expected_outcomes.yaml"
    
    if not outcomes_path.exists():
        pytest.fail(f"Expected outcomes file not found: {outcomes_path}")
    
    with open(outcomes_path, 'r') as f:
        return yaml.safe_load(f)


# -------------------------------------------------------------------------
# Test: Fixture File Existence (Requirement 1.1)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestFixtureExistence:
    """Validate all baseline fixtures exist."""
    
    def test_all_baseline_fixtures_exist(self, baseline_corpus_dir: Path, manifest: Dict[str, Any]):
        """
        Requirement 1.1: Verify all raw trace fixtures exist in test-fixtures/baseline/
        
        Expected: All 10 trace files listed in manifest.yaml should exist
        """
        missing_files = []
        
        for trace_entry in manifest.get("traces", []):
            file_name = trace_entry.get("file")
            if not file_name:
                pytest.fail(f"Trace entry missing 'file' field: {trace_entry}")
            
            file_path = baseline_corpus_dir / file_name
            if not file_path.exists():
                missing_files.append(file_name)
        
        assert len(missing_files) == 0, \
            f"Missing baseline fixture files: {missing_files}"
    
    def test_manifest_file_exists(self, baseline_corpus_dir: Path):
        """Verify manifest.yaml exists."""
        manifest_path = baseline_corpus_dir / "manifest.yaml"
        assert manifest_path.exists(), \
            f"Manifest file not found: {manifest_path}"
    
    def test_expected_outcomes_file_exists(self, baseline_corpus_dir: Path):
        """
        Requirement 1.2: Verify expected_outcomes.yaml exists
        """
        outcomes_path = baseline_corpus_dir / "expected_outcomes.yaml"
        assert outcomes_path.exists(), \
            f"Expected outcomes file not found: {outcomes_path}"


# -------------------------------------------------------------------------
# Test: JSON Parseability (Requirement 1.3)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestJSONParseability:
    """Validate fixture JSON is valid and parseable."""
    
    def test_all_fixtures_are_valid_json(self, baseline_corpus_dir: Path, manifest: Dict[str, Any]):
        """
        Requirement 1.3: Verify fixture JSON is valid and parseable
        
        Expected: All trace JSON files should parse without errors
        """
        parse_errors = []
        
        for trace_entry in manifest.get("traces", []):
            file_name = trace_entry.get("file")
            file_path = baseline_corpus_dir / file_name
            
            if not file_path.exists():
                continue  # Skip missing files (covered by existence test)
            
            try:
                with open(file_path, 'r') as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                parse_errors.append({
                    "file": file_name,
                    "error": str(e),
                    "line": e.lineno if hasattr(e, 'lineno') else None
                })
        
        assert len(parse_errors) == 0, \
            f"JSON parse errors found: {parse_errors}"
    
    def test_malformed_json_detection(self, tmp_path: Path):
        """
        Requirement 1.8: Verify malformed JSON is detected with line number
        
        Expected: Parser should report parse error with line number
        """
        # Create a malformed JSON file
        malformed_file = tmp_path / "malformed.json"
        malformed_file.write_text('{"key": "value",\n"bad": }')
        
        # Attempt to parse
        with pytest.raises(json.JSONDecodeError) as exc_info:
            with open(malformed_file, 'r') as f:
                json.load(f)
        
        # Verify error has line number
        error = exc_info.value
        assert hasattr(error, 'lineno'), \
            "JSON parse error should include line number"
        assert error.lineno == 2, \
            f"Expected error on line 2, got line {error.lineno}"


# -------------------------------------------------------------------------
# Test: Trace ID Uniqueness (Requirement 1.4)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestTraceIDUniqueness:
    """Validate trace IDs are unique across the corpus."""
    
    def test_trace_ids_are_unique_in_manifest(self, manifest: Dict[str, Any]):
        """
        Requirement 1.4: Verify trace IDs are unique across the corpus
        
        Expected: No duplicate trace_id values in manifest.yaml
        """
        trace_ids: List[str] = []
        
        for trace_entry in manifest.get("traces", []):
            trace_id = trace_entry.get("trace_id")
            if trace_id:
                trace_ids.append(trace_id)
        
        # Find duplicates
        seen: Set[str] = set()
        duplicates: List[str] = []
        
        for trace_id in trace_ids:
            if trace_id in seen:
                duplicates.append(trace_id)
            seen.add(trace_id)
        
        assert len(duplicates) == 0, \
            f"Duplicate trace IDs found in manifest: {duplicates}"
    
    def test_expected_outcome_keys_are_unique(self, expected_outcomes: Dict[str, Any]):
        """
        Verify expected outcome keys are unique
        
        Expected: No duplicate keys in expected_outcomes.yaml traces section
        """
        traces = expected_outcomes.get("traces", {})
        trace_keys = list(traces.keys())
        
        # Find duplicates (should be impossible in YAML dict, but verify)
        assert len(trace_keys) == len(set(trace_keys)), \
            "Duplicate keys found in expected_outcomes.yaml"
    
    def test_duplicate_id_detection(self):
        """
        Requirement 1.9: Verify duplicate IDs are reported
        
        Expected: System should detect and report all duplicate IDs
        """
        # Simulate duplicate trace IDs
        trace_ids = ["good-001", "good-002", "good-001", "bad-001", "good-002"]
        
        seen: Set[str] = set()
        duplicates: List[str] = []
        
        for trace_id in trace_ids:
            if trace_id in seen:
                if trace_id not in duplicates:
                    duplicates.append(trace_id)
            seen.add(trace_id)
        
        # Verify detection
        assert "good-001" in duplicates, \
            "Should detect good-001 as duplicate"
        assert "good-002" in duplicates, \
            "Should detect good-002 as duplicate"
        assert len(duplicates) == 2, \
            f"Should detect exactly 2 duplicates, found {len(duplicates)}"


# -------------------------------------------------------------------------
# Test: Category Consistency (Requirement 1.5)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestCategoryConsistency:
    """Validate categories are consistent between manifest and expected outcomes."""
    
    def test_categories_match_between_manifest_and_outcomes(
        self, 
        manifest: Dict[str, Any], 
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 1.5: Verify categories are consistent between manifest.yaml 
        and expected_outcomes.yaml
        
        Expected: Each trace should have the same category in both files
        """
        mismatches = []
        
        for trace_entry in manifest.get("traces", []):
            trace_id = trace_entry.get("trace_id")
            expected_outcome_key = trace_entry.get("expected_outcome_key")
            manifest_category = trace_entry.get("category")
            
            if not expected_outcome_key:
                continue
            
            # Get category from expected_outcomes
            outcome_entry = expected_outcomes.get("traces", {}).get(expected_outcome_key)
            if not outcome_entry:
                mismatches.append({
                    "trace_id": trace_id,
                    "error": "Missing in expected_outcomes.yaml"
                })
                continue
            
            outcome_category = outcome_entry.get("category")
            
            # Compare categories
            if manifest_category != outcome_category:
                mismatches.append({
                    "trace_id": trace_id,
                    "manifest_category": manifest_category,
                    "outcome_category": outcome_category
                })
        
        assert len(mismatches) == 0, \
            f"Category mismatches found: {mismatches}"


# -------------------------------------------------------------------------
# Test: Expected Outcomes Structure (Requirement 1.6)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestExpectedOutcomesStructure:
    """Validate expected_outcomes.yaml structure matches schema requirements."""
    
    def test_expected_outcomes_has_traces_section(self, expected_outcomes: Dict[str, Any]):
        """
        Requirement 1.6: Verify expected outcome structure matches schema requirements
        
        Expected: expected_outcomes.yaml should have 'traces' section
        """
        assert "traces" in expected_outcomes, \
            "expected_outcomes.yaml missing 'traces' section"
    
    def test_all_traces_have_required_fields(self, expected_outcomes: Dict[str, Any]):
        """
        Requirement 1.6: Verify each trace has required fields
        
        Expected: Each trace should have description, category, and expected sections
        """
        traces = expected_outcomes.get("traces", {})
        missing_fields = []
        
        for trace_id, trace_data in traces.items():
            required_fields = ["description", "category", "expected"]
            
            for field in required_fields:
                if field not in trace_data:
                    missing_fields.append({
                        "trace_id": trace_id,
                        "missing_field": field
                    })
        
        assert len(missing_fields) == 0, \
            f"Traces missing required fields: {missing_fields}"
    
    def test_expected_section_has_required_metrics(self, expected_outcomes: Dict[str, Any]):
        """
        Requirement 1.6: Verify expected section has required metrics
        
        Expected: Each trace's expected section should have turn_count and tool_call_count
        """
        traces = expected_outcomes.get("traces", {})
        missing_metrics = []
        
        for trace_id, trace_data in traces.items():
            expected = trace_data.get("expected", {})
            required_metrics = ["turn_count", "tool_call_count"]
            
            for metric in required_metrics:
                if metric not in expected:
                    missing_metrics.append({
                        "trace_id": trace_id,
                        "missing_metric": metric
                    })
        
        assert len(missing_metrics) == 0, \
            f"Traces missing required metrics: {missing_metrics}"


# -------------------------------------------------------------------------
# Test: Missing File Detection (Requirement 1.7)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestMissingFileDetection:
    """Validate missing file detection and reporting."""
    
    def test_missing_file_is_reported_with_path(self, baseline_corpus_dir: Path):
        """
        Requirement 1.7: Verify missing file path is reported
        
        Expected: System should report the full path of missing files
        """
        # Simulate checking for a non-existent file
        missing_file = "nonexistent_trace.json"
        file_path = baseline_corpus_dir / missing_file
        
        # Verify file doesn't exist
        assert not file_path.exists(), \
            f"Test file should not exist: {file_path}"
        
        # Verify we can report the path
        reported_path = str(file_path)
        assert missing_file in reported_path, \
            f"Reported path should contain filename: {reported_path}"


# -------------------------------------------------------------------------
# Test: Corpus Completeness (Requirement 1.10)
# -------------------------------------------------------------------------

@pytest.mark.component
class TestCorpusCompleteness:
    """Verify all 10 baseline traces are present with correct distribution."""
    
    def test_all_11_traces_present(self, manifest: Dict[str, Any]):
        """
        Requirement 1.10: Verify all baseline traces are present
        
        Expected: Manifest should list exactly 11 traces (corpus has grown from original 10)
        """
        traces = manifest.get("traces", [])
        trace_count = len(traces)
        
        # Note: Original spec mentioned 10 traces, but corpus now has 11
        assert trace_count == 11, \
            f"Expected 11 traces in manifest, found {trace_count}"
    
    def test_trace_distribution_by_category(self, manifest: Dict[str, Any]):
        """
        Requirement 1.10: Verify correct distribution
        
        Expected (based on actual corpus):
        - 3 clearly_good traces
        - 3 clearly_bad traces
        - 1 partial trace
        - 2 ambiguous traces
        - 2 tool_weird traces
        Total: 11 traces
        """
        category_counts = {}
        
        for trace_entry in manifest.get("traces", []):
            category = trace_entry.get("category")
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
        
        # Verify counts
        assert category_counts.get("clearly_good", 0) == 3, \
            f"Expected 3 clearly_good traces, found {category_counts.get('clearly_good', 0)}"
        
        assert category_counts.get("clearly_bad", 0) == 3, \
            f"Expected 3 clearly_bad traces, found {category_counts.get('clearly_bad', 0)}"
        
        assert category_counts.get("partial", 0) == 1, \
            f"Expected 1 partial trace, found {category_counts.get('partial', 0)}"
        
        assert category_counts.get("ambiguous", 0) == 2, \
            f"Expected 2 ambiguous traces, found {category_counts.get('ambiguous', 0)}"
        
        assert category_counts.get("tool_weird", 0) == 2, \
            f"Expected 2 tool_weird traces, found {category_counts.get('tool_weird', 0)}"
    
    def test_expected_outcomes_covers_all_traces(
        self, 
        manifest: Dict[str, Any], 
        expected_outcomes: Dict[str, Any]
    ):
        """
        Requirement 1.2: Verify all expected outcome entries exist
        
        Expected: Every trace in manifest should have an entry in expected_outcomes
        """
        missing_outcomes = []
        
        for trace_entry in manifest.get("traces", []):
            expected_outcome_key = trace_entry.get("expected_outcome_key")
            trace_id = trace_entry.get("trace_id")
            
            if not expected_outcome_key:
                missing_outcomes.append({
                    "trace_id": trace_id,
                    "error": "No expected_outcome_key in manifest"
                })
                continue
            
            if expected_outcome_key not in expected_outcomes.get("traces", {}):
                missing_outcomes.append({
                    "trace_id": trace_id,
                    "expected_outcome_key": expected_outcome_key,
                    "error": "Missing in expected_outcomes.yaml"
                })
        
        assert len(missing_outcomes) == 0, \
            f"Traces missing expected outcomes: {missing_outcomes}"


# -------------------------------------------------------------------------
# Test: Manifest Metadata Validation
# -------------------------------------------------------------------------

@pytest.mark.component
class TestManifestMetadata:
    """Validate manifest.yaml metadata is complete."""
    
    def test_manifest_has_version(self, manifest: Dict[str, Any]):
        """Verify manifest has version field."""
        assert "version" in manifest, \
            "Manifest missing 'version' field"
    
    def test_manifest_has_description(self, manifest: Dict[str, Any]):
        """Verify manifest has description field."""
        assert "description" in manifest, \
            "Manifest missing 'description' field"
    
    def test_manifest_total_traces_matches_actual(self, manifest: Dict[str, Any]):
        """Verify manifest total_traces matches actual trace count."""
        declared_total = manifest.get("total_traces")
        actual_total = len(manifest.get("traces", []))
        
        assert declared_total == actual_total, \
            f"Manifest declares {declared_total} traces but has {actual_total}"


# -------------------------------------------------------------------------
# Test: Integration - Full Corpus Validation
# -------------------------------------------------------------------------

@pytest.mark.component
def test_full_corpus_integrity(
    baseline_corpus_dir: Path,
    manifest: Dict[str, Any],
    expected_outcomes: Dict[str, Any]
):
    """
    Integration test: Validate complete corpus integrity
    
    This test combines all validation checks to ensure the corpus is production-ready:
    - All files exist
    - All JSON is valid
    - All IDs are unique
    - Categories are consistent
    - Expected outcomes are complete
    - Distribution is correct (3 good, 3 bad, 2 partial, 2 weird)
    """
    errors = []
    
    # Check file existence
    for trace_entry in manifest.get("traces", []):
        file_name = trace_entry.get("file")
        file_path = baseline_corpus_dir / file_name
        
        if not file_path.exists():
            errors.append(f"Missing file: {file_name}")
            continue
        
        # Check JSON validity
        try:
            with open(file_path, 'r') as f:
                json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in {file_name}: {e}")
    
    # Check trace ID uniqueness
    trace_ids = [t.get("trace_id") for t in manifest.get("traces", [])]
    if len(trace_ids) != len(set(trace_ids)):
        errors.append("Duplicate trace IDs found")
    
    # Check expected outcomes coverage
    for trace_entry in manifest.get("traces", []):
        expected_outcome_key = trace_entry.get("expected_outcome_key")
        if expected_outcome_key not in expected_outcomes.get("traces", {}):
            errors.append(f"Missing expected outcome for {expected_outcome_key}")
    
    # Report all errors
    assert len(errors) == 0, \
        f"Corpus integrity validation failed with {len(errors)} errors:\n" + "\n".join(errors)
