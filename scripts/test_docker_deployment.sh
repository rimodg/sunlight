#!/usr/bin/env bash
# SUNLIGHT Docker Deployment Validation Script
# Tests that the containerized API works correctly

set -euo pipefail

echo "=== SUNLIGHT Docker Deployment Test ==="
echo

# Configuration
API_URL="${SUNLIGHT_API_URL:-http://localhost:8000}"
TIMEOUT=30

# Color output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
}

fail() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

# Wait for API to be ready
echo "Waiting for API to be ready at $API_URL..."
for i in $(seq 1 $TIMEOUT); do
    if curl -sf "$API_URL/health" >/dev/null 2>&1; then
        pass "API is responding"
        break
    fi
    if [ $i -eq $TIMEOUT ]; then
        fail "API did not become ready within ${TIMEOUT}s"
    fi
    sleep 1
done

# Test 1: Health endpoint
echo
echo "Test 1: Health endpoint"
HEALTH_RESPONSE=$(curl -sf "$API_URL/health")
if echo "$HEALTH_RESPONSE" | grep -q '"status":"ok"'; then
    pass "Health check passed"
else
    fail "Health check failed: $HEALTH_RESPONSE"
fi

# Test 2: Version endpoint
echo
echo "Test 2: Version endpoint"
VERSION_RESPONSE=$(curl -sf "$API_URL/version")
if echo "$VERSION_RESPONSE" | grep -q '"version"'; then
    VERSION=$(echo "$VERSION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['version'])")
    pass "Version endpoint returned: $VERSION"
else
    fail "Version endpoint failed: $VERSION_RESPONSE"
fi

# Test 3: Profiles endpoint
echo
echo "Test 3: Profiles endpoint"
PROFILES_RESPONSE=$(curl -sf "$API_URL/profiles")
if echo "$PROFILES_RESPONSE" | grep -q 'us_federal'; then
    pass "Profiles endpoint returned us_federal"
else
    fail "Profiles endpoint failed: $PROFILES_RESPONSE"
fi

# Test 4: Single contract analysis
echo
echo "Test 4: Single contract analysis"
ANALYZE_PAYLOAD='{
  "contract": {
    "ocid": "test-001",
    "buyer": {"id": "US-TEST", "name": "Test Agency"},
    "tender": {
      "title": "Test Contract",
      "value": {"amount": 100000, "currency": "USD"},
      "procurementMethod": "open",
      "numberOfTenderers": 3
    },
    "awards": [{"value": {"amount": 95000, "currency": "USD"}}]
  },
  "profile": "us_federal"
}'

ANALYZE_RESPONSE=$(curl -sf -X POST "$API_URL/analyze" \
    -H "Content-Type: application/json" \
    -d "$ANALYZE_PAYLOAD")

if echo "$ANALYZE_RESPONSE" | grep -q '"verdict"'; then
    VERDICT=$(echo "$ANALYZE_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['structure']['verdict'])")
    pass "Single analysis returned verdict: $VERDICT"
else
    fail "Single analysis failed: $ANALYZE_RESPONSE"
fi

# Test 5: Batch analysis
echo
echo "Test 5: Batch analysis with capacity threshold"
BATCH_PAYLOAD='{
  "contracts": [
    {
      "ocid": "batch-001",
      "buyer": {"id": "US-TEST", "name": "Test Agency"},
      "tender": {
        "title": "Batch Test 1",
        "value": {"amount": 100000, "currency": "USD"},
        "procurementMethod": "open",
        "numberOfTenderers": 3
      },
      "awards": [{"value": {"amount": 95000, "currency": "USD"}}]
    }
  ],
  "profile": "us_federal",
  "capacity_budget": 100
}'

BATCH_RESPONSE=$(curl -sf -X POST "$API_URL/batch" \
    -H "Content-Type: application/json" \
    -d "$BATCH_PAYLOAD")

if echo "$BATCH_RESPONSE" | grep -q '"results"'; then
    pass "Batch analysis succeeded"

    # Verify calibration store was updated
    echo
    echo "Test 6: Calibration store persistence"
    CALIBRATION_RESPONSE=$(curl -sf "$API_URL/calibration/us_federal")
    if echo "$CALIBRATION_RESPONSE" | grep -q '"total_contracts_analyzed"'; then
        COUNT=$(echo "$CALIBRATION_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['total_contracts_analyzed'])")
        pass "Calibration store has analyzed $COUNT contracts"
    else
        fail "Calibration endpoint failed: $CALIBRATION_RESPONSE"
    fi
else
    fail "Batch analysis failed: $BATCH_RESPONSE"
fi

echo
echo -e "${GREEN}=== All tests passed ===${NC}"
echo
echo "Deployment is working correctly!"
