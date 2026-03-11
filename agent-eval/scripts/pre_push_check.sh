#!/bin/bash
# Pre-push check script
# Run this before every push to ensure code quality

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "========================================="
echo "  Pre-Push Quality Gate"
echo "========================================="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Track failures
FAILED=0

# Function to run a check
run_check() {
    local name="$1"
    local command="$2"
    
    echo -e "${BLUE}▶${NC} $name"
    
    if eval "$command"; then
        echo -e "${GREEN}✅ PASS${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        echo ""
        FAILED=1
        return 1
    fi
}

# 1. Unit Tests
run_check "Unit Tests" "pytest agent_eval/tests/ -v --tb=short -x"

# 2. Smoke Tests (Raw Traces)
run_check "Smoke Tests (Raw Traces)" "$SCRIPT_DIR/smoke_test_raw_traces.sh"

# 3. Integration Test (Normalized Input)
run_check "Integration Test (Normalized)" \
    "python -m agent_eval.cli \
        --input test-fixtures/normalized_run_minimal.json \
        --judge-config test-fixtures/judges.mock.yaml \
        --rubrics test-fixtures/rubrics.test.yaml \
        --output-dir ./.pre-push-test-normalized && \
     test -f ./.pre-push-test-normalized/trace_eval.json && \
     test -f ./.pre-push-test-normalized/results.json && \
     rm -rf ./.pre-push-test-normalized"

# 4. Negative Path Test (Malformed Input)
run_check "Negative Path Test (Malformed)" \
    "! python -m agent_eval.cli \
        --input test-fixtures/malformed_raw_trace.json \
        --judge-config test-fixtures/judges.mock.yaml \
        --rubrics test-fixtures/rubrics.test.yaml \
        --output-dir ./.pre-push-test-malformed 2>/dev/null"

# 5. Import Check (No Import Errors)
run_check "Import Check" \
    "python -c 'import agent_eval; from agent_eval.adapters.generic_json import adapt; from agent_eval.pipeline import run_evaluation_pipeline'"

# 6. Schema Validation
run_check "Schema Validation" \
    "python -c 'import json; import jsonschema; \
     schema = json.load(open(\"agent_eval/schemas/normalized_run.schema.json\")); \
     data = json.load(open(\"test-fixtures/normalized_run_minimal.json\")); \
     jsonschema.validate(data, schema)'"

echo "========================================="
echo "  Summary"
echo "========================================="

if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ All checks PASSED${NC}"
    echo ""
    echo "Safe to push!"
    exit 0
else
    echo -e "${RED}❌ Some checks FAILED${NC}"
    echo ""
    echo "Fix failures before pushing."
    exit 1
fi
