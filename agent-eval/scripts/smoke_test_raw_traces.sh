#!/bin/bash
# Smoke test for raw trace evaluation
# Tests all weird traces against expected outcomes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_FIXTURES="$PROJECT_ROOT/test-fixtures"
EXPECTED_RESULTS="$TEST_FIXTURES/expected-results"
OUTPUT_DIR="$PROJECT_ROOT/.smoke-test-output"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

echo "========================================="
echo "  Raw Trace Smoke Test Suite"
echo "========================================="
echo ""

# Clean output directory
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Function to run a single test
run_test() {
    local trace_file="$1"
    local expected_file="$2"
    local test_name=$(basename "$trace_file" .json)
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    echo -n "Testing $test_name... "
    
    # Read expected results
    if [ ! -f "$expected_file" ]; then
        echo -e "${YELLOW}SKIP${NC} (no expected results)"
        return
    fi
    
    local expected_exit_code=$(jq -r '.expected_exit_code' "$expected_file")
    local min_turns=$(jq -r '.min_turns' "$expected_file")
    local max_turns=$(jq -r '.max_turns' "$expected_file")
    local expected_tool_calls=$(jq -r '.expected_tool_calls' "$expected_file")
    local min_confidence=$(jq -r '.min_confidence' "$expected_file")
    
    # Create test output directory
    local test_output="$OUTPUT_DIR/$test_name"
    mkdir -p "$test_output"
    
    # Run evaluation pipeline
    set +e
    python -m agent_eval.cli \
        --input "$trace_file" \
        --judge-config "$TEST_FIXTURES/judges.mock.yaml" \
        --rubrics "$TEST_FIXTURES/rubrics.test.yaml" \
        --output-dir "$test_output" \
        > "$test_output/stdout.log" 2> "$test_output/stderr.log"
    
    local actual_exit_code=$?
    set -e
    
    # Validate exit code
    if [ "$actual_exit_code" -ne "$expected_exit_code" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  Expected exit code: $expected_exit_code"
        echo "  Actual exit code: $actual_exit_code"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    # If expected to fail, we're done
    if [ "$expected_exit_code" -ne 0 ]; then
        echo -e "${GREEN}PASS${NC} (failed as expected)"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return
    fi
    
    # Validate output files exist
    if [ ! -f "$test_output/trace_eval.json" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  Missing trace_eval.json"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    if [ ! -f "$test_output/results.json" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  Missing results.json"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    # Validate JSON is valid
    if ! jq empty "$test_output/trace_eval.json" 2>/dev/null; then
        echo -e "${RED}FAIL${NC}"
        echo "  Invalid JSON in trace_eval.json"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    if ! jq empty "$test_output/results.json" 2>/dev/null; then
        echo -e "${RED}FAIL${NC}"
        echo "  Invalid JSON in results.json"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    # Extract actual metrics
    local actual_turns=$(jq -r '.metrics.turns // 0' "$test_output/trace_eval.json")
    local actual_tool_calls=$(jq -r '.metrics.tool_calls // 0' "$test_output/trace_eval.json")
    local actual_confidence=$(jq -r '.metadata.run_confidence // 0' "$test_output/trace_eval.json")
    
    # Validate turn count
    if [ "$actual_turns" -lt "$min_turns" ] || [ "$actual_turns" -gt "$max_turns" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  Expected turns: $min_turns-$max_turns"
        echo "  Actual turns: $actual_turns"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    # Validate tool call count
    if [ "$actual_tool_calls" -ne "$expected_tool_calls" ]; then
        echo -e "${RED}FAIL${NC}"
        echo "  Expected tool calls: $expected_tool_calls"
        echo "  Actual tool calls: $actual_tool_calls"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    # Validate confidence
    if (( $(echo "$actual_confidence < $min_confidence" | bc -l) )); then
        echo -e "${RED}FAIL${NC}"
        echo "  Expected min confidence: $min_confidence"
        echo "  Actual confidence: $actual_confidence"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return
    fi
    
    echo -e "${GREEN}PASS${NC}"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

# Run tests for all traces with expected results
echo "Running smoke tests..."
echo ""

for expected_file in "$EXPECTED_RESULTS"/*.expected.json; do
    if [ -f "$expected_file" ]; then
        trace_name=$(basename "$expected_file" .expected.json)
        trace_file="$TEST_FIXTURES/${trace_name}.json"
        
        if [ -f "$trace_file" ]; then
            run_test "$trace_file" "$expected_file"
        else
            echo -e "${YELLOW}SKIP${NC} $trace_name (trace file not found)"
        fi
    fi
done

echo ""
echo "========================================="
echo "  Test Summary"
echo "========================================="
echo "Total tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"
echo ""

if [ "$FAILED_TESTS" -gt 0 ]; then
    echo -e "${RED}❌ Smoke tests FAILED${NC}"
    echo "Check logs in: $OUTPUT_DIR"
    exit 1
else
    echo -e "${GREEN}✅ All smoke tests PASSED${NC}"
    exit 0
fi
