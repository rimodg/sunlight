"""
SUNLIGHT Live Container Integration Tests
==========================================

End-to-end verification of the containerized SUNLIGHT API deployment spun up
via docker-compose. These tests run against an actual HTTP server in a Docker
container, validating the complete deployment path from Dockerfile build through
API request handling.

Distinct from tests/test_api.py which uses FastAPI's TestClient for in-process
testing. This suite verifies:
- Container builds and starts successfully
- API responds to real HTTP traffic
- Profile propagation through containerized engines
- Calibration store persistence across HTTP calls
- Capacity threshold metadata correctness
- Response schema conformance under containerization

Requirements:
- Docker and docker-compose available on the host
- Port 8000 available for binding
- Ability to run `docker compose up/down` commands

All tests skip gracefully if Docker is not available.
"""

import subprocess
import time
import pytest
import httpx


# Detect Docker availability at module load time
# Check both that docker exists AND that the daemon is running
try:
    subprocess.run(
        ["docker", "info"],
        check=True,
        capture_output=True,
        timeout=5
    )
    DOCKER_AVAILABLE = True
except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
    DOCKER_AVAILABLE = False


# Skip entire module if Docker not available
pytestmark = pytest.mark.skipif(
    not DOCKER_AVAILABLE,
    reason="Docker not available"
)


@pytest.fixture(scope="session")
def sunlight_container():
    """
    Session-scoped fixture that spins up the SUNLIGHT API container via
    docker-compose, waits for health, yields the base URL, and tears down
    cleanly on exit.

    The teardown includes -v to remove the calibration volume so tests are
    hermetic across runs (each test session starts with a fresh calibration
    state).
    """
    import os

    # Change to repo root for docker-compose commands
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    base_url = "http://localhost:8000"

    # Spin up the container
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"docker compose up failed:\nstdout: {e.stdout}\nstderr: {e.stderr}"
        )

    # Wait for health check to pass
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=2.0)
            if r.status_code == 200 and r.json().get("status") == "ok":
                break
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    else:
        # Health check failed, capture logs before tearing down
        try:
            logs_result = subprocess.run(
                ["docker", "compose", "logs", "api"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=10
            )
            logs = logs_result.stdout
        except Exception:
            logs = "(failed to capture logs)"

        # Tear down the failed container
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=repo_root,
            capture_output=True
        )
        raise RuntimeError(
            f"sunlight-api did not become healthy within 60s\nLogs:\n{logs}"
        )

    # Yield base URL to tests
    yield base_url

    # Teardown: always run even if tests fail
    try:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            timeout=30
        )
    except subprocess.CalledProcessError as e:
        # Log teardown failure but don't fail the test run
        print(f"Warning: docker compose down failed: {e.stderr}")


# ============================================================================
# Test Cases
# ============================================================================


def test_health_returns_ok(sunlight_container):
    """Verify /health endpoint returns 200 with status=ok."""
    r = httpx.get(f"{sunlight_container}/health", timeout=5.0)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_profiles_lists_both_jurisdictions(sunlight_container):
    """Verify /profiles lists both us_federal and uk_central_government."""
    r = httpx.get(f"{sunlight_container}/profiles", timeout=5.0)
    assert r.status_code == 200
    data = r.json()
    profile_names = [p["name"] for p in data["profiles"]]
    assert "us_federal" in profile_names
    assert "uk_central_government" in profile_names


def test_profile_propagation_differential(sunlight_container):
    """
    Verify that profile propagates through the container to the TCA engines
    by analyzing the same synthetic contract under two different profiles
    and confirming differential findings.

    Uses a construct designed to trigger different fiscal calendar rules
    under US vs UK profiles, similar to the 2.2.7a correction integration test.
    """
    # Synthetic contract: large value, limited competition, significant discount
    contract = {
        "ocid": "ocds-profile-differential-001",
        "buyer": {"id": "TEST-BUYER", "name": "Test Procurement Agency"},
        "tender": {
            "title": "Large Infrastructure Contract",
            "value": {"amount": 5000000, "currency": "USD"},
            "procurementMethod": "selective",
            "numberOfTenderers": 2
        },
        "awards": [{"value": {"amount": 4500000, "currency": "USD"}}]
    }

    # Analyze under US federal profile
    r_us = httpx.post(
        f"{sunlight_container}/analyze",
        json={"contract": contract, "profile": "us_federal"},
        timeout=10.0
    )
    assert r_us.status_code == 200
    result_us = r_us.json()

    # Analyze under UK central government profile
    r_uk = httpx.post(
        f"{sunlight_container}/analyze",
        json={"contract": contract, "profile": "uk_central_government"},
        timeout=10.0
    )
    assert r_uk.status_code == 200
    result_uk = r_uk.json()

    # Verify differential: either different verdicts, confidence, or contradictions
    us_verdict = result_us["structure"]["verdict"]
    uk_verdict = result_uk["structure"]["verdict"]
    us_confidence = result_us["structure"]["confidence"]
    uk_confidence = result_uk["structure"]["confidence"]
    us_contradictions = set(c["rule_id"] for c in result_us["structure"]["contradictions"])
    uk_contradictions = set(c["rule_id"] for c in result_uk["structure"]["contradictions"])

    differential = (
        us_verdict != uk_verdict or
        abs(us_confidence - uk_confidence) > 0.01 or
        us_contradictions != uk_contradictions
    )

    assert differential, (
        f"Expected differential findings across profiles, got identical: "
        f"US={us_verdict}/{us_confidence:.2f}, UK={uk_verdict}/{uk_confidence:.2f}"
    )


def test_batch_capacity_threshold_metadata(sunlight_container):
    """
    Verify /batch returns correct threshold_metadata when capacity_budget
    is provided, including all 5 documented keys and correct recommended_count.
    """
    # 3 contracts with capacity_budget=1 ensures capacity threshold binds
    batch = {
        "contracts": [
            {
                "ocid": "ocds-capacity-001",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": "Contract 1",
                    "value": {"amount": 200000, "currency": "USD"},
                    "procurementMethod": "open",
                    "numberOfTenderers": 4
                },
                "awards": [{"value": {"amount": 190000, "currency": "USD"}}]
            },
            {
                "ocid": "ocds-capacity-002",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": "Contract 2",
                    "value": {"amount": 300000, "currency": "USD"},
                    "procurementMethod": "selective",
                    "numberOfTenderers": 2
                },
                "awards": [{"value": {"amount": 280000, "currency": "USD"}}]
            },
            {
                "ocid": "ocds-capacity-003",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": "Contract 3",
                    "value": {"amount": 150000, "currency": "USD"},
                    "procurementMethod": "direct",
                    "numberOfTenderers": 1
                },
                "awards": [{"value": {"amount": 150000, "currency": "USD"}}]
            }
        ],
        "profile": "us_federal",
        "capacity_budget": 1
    }

    r = httpx.post(
        f"{sunlight_container}/batch",
        json=batch,
        timeout=15.0
    )
    assert r.status_code == 200
    data = r.json()

    # Verify threshold_metadata has all 5 required keys
    metadata = data["threshold_metadata"]
    assert "statistical_threshold" in metadata
    assert "capacity_budget" in metadata
    assert "capacity_threshold" in metadata
    assert "binding_threshold" in metadata
    assert "recommended_count" in metadata

    # Verify capacity constraint is respected
    assert metadata["capacity_budget"] == 1
    assert metadata["recommended_count"] <= 1


def test_calibration_monotonic_across_calls(sunlight_container):
    """
    Verify the calibration store's monotonic property across sequential batch
    calls: contract counts only grow, verdict counts only grow.
    """
    profile = "us_federal"

    # Get baseline
    r0 = httpx.get(f"{sunlight_container}/calibration/{profile}", timeout=5.0)
    assert r0.status_code == 200
    baseline = r0.json()
    n0 = baseline["total_contracts_analyzed"]
    verdict_baseline = baseline.get("verdict_counts", {})

    # First batch: 3 contracts
    batch1 = {
        "contracts": [
            {
                "ocid": f"ocds-monotonic-{i}",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": f"Monotonic Test {i}",
                    "value": {"amount": 100000 + i * 10000, "currency": "USD"},
                    "procurementMethod": "open",
                    "numberOfTenderers": 3
                },
                "awards": [{"value": {"amount": 95000 + i * 10000, "currency": "USD"}}]
            }
            for i in range(3)
        ],
        "profile": profile
    }

    r1 = httpx.post(f"{sunlight_container}/batch", json=batch1, timeout=15.0)
    assert r1.status_code == 200

    # Check count increased by 3
    r_after_1 = httpx.get(f"{sunlight_container}/calibration/{profile}", timeout=5.0)
    assert r_after_1.status_code == 200
    state_1 = r_after_1.json()
    assert state_1["total_contracts_analyzed"] == n0 + 3

    # Verify verdict counts are monotonic
    for verdict, count in state_1.get("verdict_counts", {}).items():
        baseline_count = verdict_baseline.get(verdict, 0)
        assert count >= baseline_count, f"Verdict {verdict} decreased: {baseline_count} -> {count}"

    # Second batch: 2 more contracts
    batch2 = {
        "contracts": [
            {
                "ocid": f"ocds-monotonic-{i}",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": f"Monotonic Test {i}",
                    "value": {"amount": 150000 + i * 10000, "currency": "USD"},
                    "procurementMethod": "open",
                    "numberOfTenderers": 5
                },
                "awards": [{"value": {"amount": 145000 + i * 10000, "currency": "USD"}}]
            }
            for i in range(10, 12)
        ],
        "profile": profile
    }

    r2 = httpx.post(f"{sunlight_container}/batch", json=batch2, timeout=15.0)
    assert r2.status_code == 200

    # Check final count
    r_final = httpx.get(f"{sunlight_container}/calibration/{profile}", timeout=5.0)
    assert r_final.status_code == 200
    state_final = r_final.json()
    assert state_final["total_contracts_analyzed"] == n0 + 5

    # Verify all verdict counts still monotonic relative to state_1
    for verdict, count in state_final.get("verdict_counts", {}).items():
        state_1_count = state_1.get("verdict_counts", {}).get(verdict, 0)
        assert count >= state_1_count, f"Verdict {verdict} decreased: {state_1_count} -> {count}"


def test_calibration_per_profile_isolation(sunlight_container):
    """
    Verify calibration store maintains per-profile isolation at the container
    level: analyzing contracts under one profile does not affect the calibration
    state of a different profile.
    """
    # Get UK baseline
    r_uk_baseline = httpx.get(
        f"{sunlight_container}/calibration/uk_central_government",
        timeout=5.0
    )
    assert r_uk_baseline.status_code == 200
    uk_baseline_count = r_uk_baseline.json()["total_contracts_analyzed"]

    # Analyze under US federal
    batch_us = {
        "contracts": [
            {
                "ocid": "ocds-isolation-us-001",
                "buyer": {"id": "US-TEST", "name": "Test Agency"},
                "tender": {
                    "title": "US Isolation Test",
                    "value": {"amount": 200000, "currency": "USD"},
                    "procurementMethod": "open",
                    "numberOfTenderers": 4
                },
                "awards": [{"value": {"amount": 190000, "currency": "USD"}}]
            }
        ],
        "profile": "us_federal"
    }

    r_us = httpx.post(f"{sunlight_container}/batch", json=batch_us, timeout=15.0)
    assert r_us.status_code == 200

    # Verify UK count unchanged
    r_uk_after = httpx.get(
        f"{sunlight_container}/calibration/uk_central_government",
        timeout=5.0
    )
    assert r_uk_after.status_code == 200
    uk_after_count = r_uk_after.json()["total_contracts_analyzed"]

    assert uk_after_count == uk_baseline_count, (
        f"UK calibration was affected by US batch: {uk_baseline_count} -> {uk_after_count}"
    )


def test_analyze_response_schema(sunlight_container):
    """
    Verify /analyze returns a response with all required fields under
    containerization: ocid, structure with verdict/confidence/contradictions,
    processing_time_ms, recommended_for_investigation.
    """
    contract = {
        "ocid": "ocds-schema-test-001",
        "buyer": {"id": "US-DOD", "name": "Department of Defense"},
        "tender": {
            "title": "Schema Verification Contract",
            "value": {"amount": 500000, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": 6
        },
        "awards": [{"value": {"amount": 480000, "currency": "USD"}}]
    }

    r = httpx.post(
        f"{sunlight_container}/analyze",
        json={"contract": contract, "profile": "us_federal"},
        timeout=10.0
    )
    assert r.status_code == 200
    data = r.json()

    # Required top-level fields
    assert "ocid" in data
    assert data["ocid"] == "ocds-schema-test-001"
    assert "structure" in data
    assert "processing_time_ms" in data
    assert "recommended_for_investigation" in data

    # Required structure fields
    structure = data["structure"]
    assert "verdict" in structure
    assert "confidence" in structure
    assert "contradictions" in structure

    # Type checks
    assert isinstance(structure["verdict"], str)
    assert isinstance(structure["confidence"], (int, float))
    assert isinstance(structure["contradictions"], list)
    assert isinstance(data["processing_time_ms"], (int, float))
    assert isinstance(data["recommended_for_investigation"], bool)
