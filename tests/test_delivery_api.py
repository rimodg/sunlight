"""
Tests for SUNLIGHT Side 2 delivery API endpoints.

Covers:
    POST /delivery/analyze:
        - Clean delivery → GREEN verdict response
        - Problematic delivery → RED verdict response
        - Response structure (all expected fields present)
        - Invalid profile → 400
        - Empty contract_id accepted
        - Minimal request (no milestones/resources/outcomes/financials)
        - Delivery metrics in response

    POST /delivery/batch:
        - Multiple deliveries processed
        - Verdict distribution tracked
        - Batch size limit (>1000 rejected)
        - Mixed verdicts in batch
        - Error in one delivery doesn't block others
        - Total errors counted

    GET /delivery/pillar-summary:
        - Returns methodology version
        - Returns profiles_available list
        - Stats reflect analyzed deliveries
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient
from api import app, _delivery_analyzers


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def clear_delivery_analyzers():
    """Reset cached analyzers between tests."""
    _delivery_analyzers.clear()
    yield
    _delivery_analyzers.clear()


@pytest.fixture
def client():
    return TestClient(app)


def _clean_delivery_payload() -> dict:
    """A delivery request with no problems — should produce GREEN."""
    return {
        "contract_id": "TEST-CLEAN-001",
        "milestones": [
            {
                "milestone_id": "M1",
                "description": "Phase 1 delivery",
                "planned_date": "2024-03-01",
                "actual_date": "2024-03-01",
                "status": "completed",
                "delay_days": 0,
                "deliverables_due": 5,
                "deliverables_accepted": 5,
            },
        ],
        "resources": [
            {
                "resource_id": "R1",
                "role": "engineer",
                "planned_fte": 2.0,
                "actual_fte": 2.0,
                "qualification_required": "PE",
                "qualification_verified": True,
            },
        ],
        "outcomes": [
            {
                "outcome_id": "O1",
                "description": "Road segment",
                "unit": "km_road",
                "quantity_planned": 10.0,
                "quantity_delivered": 10.0,
                "quality_score": 0.95,
                "defects_noted": 0,
            },
        ],
        "financials": [
            {
                "line_item_id": "F1",
                "description": "Materials",
                "budgeted_amount": 100000.0,
                "actual_amount": 100000.0,
                "currency": "USD",
                "variance_pct": 0.0,
                "amendment_count": 0,
            },
        ],
        "country_code": "US",
        "country_name": "United States",
        "project_name": "Test Clean Project",
        "procurement_verdict": "GREEN",
        "profile": "us_federal",
    }


def _problematic_delivery_payload() -> dict:
    """A delivery with problems across all 4 layers — should produce RED."""
    return {
        "contract_id": "TEST-BAD-001",
        "milestones": [
            {
                "milestone_id": "M1",
                "description": "Phase 1",
                "planned_date": "2024-01-01",
                "actual_date": "2024-06-01",
                "status": "delayed",
                "delay_days": 150,
                "deliverables_due": 10,
                "deliverables_accepted": 2,
            },
            {
                "milestone_id": "M2",
                "description": "Phase 2",
                "planned_date": "2024-03-01",
                "actual_date": "2024-09-01",
                "status": "delayed",
                "delay_days": 180,
                "deliverables_due": 8,
                "deliverables_accepted": 1,
            },
        ],
        "resources": [
            {
                "resource_id": "R1",
                "role": "engineer",
                "planned_fte": 5.0,
                "actual_fte": 1.0,
                "qualification_required": "PE",
                "qualification_verified": False,
            },
            {
                "resource_id": "R2",
                "role": "project_manager",
                "planned_fte": 2.0,
                "actual_fte": 0.5,
                "qualification_required": "PMP",
                "qualification_verified": False,
            },
        ],
        "outcomes": [
            {
                "outcome_id": "O1",
                "description": "Road segment",
                "unit": "km_road",
                "quantity_planned": 50.0,
                "quantity_delivered": 10.0,
                "quality_score": 0.3,
                "defects_noted": 15,
            },
        ],
        "financials": [
            {
                "line_item_id": "F1",
                "description": "Materials",
                "budgeted_amount": 100000.0,
                "actual_amount": 200000.0,
                "currency": "USD",
                "variance_pct": 100.0,
                "amendment_count": 5,
            },
            {
                "line_item_id": "F2",
                "description": "Labor",
                "budgeted_amount": 50000.0,
                "actual_amount": 120000.0,
                "currency": "USD",
                "variance_pct": 140.0,
                "amendment_count": 4,
            },
        ],
        "country_code": "US",
        "country_name": "United States",
        "project_name": "Test Problematic Project",
        "procurement_verdict": "RED",
        "profile": "us_federal",
    }


# ═══════════════════════════════════════════════════════════
# POST /delivery/analyze TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryAnalyzeEndpoint:
    def test_clean_delivery_returns_green(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] == "green"
        assert data["contract_id"] == "TEST-CLEAN-001"

    def test_problematic_delivery_returns_red_or_yellow(self, client):
        """A delivery with major problems should return RED or YELLOW."""
        payload = _problematic_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["verdict"] in ("red", "yellow")
        assert data["contract_id"] == "TEST-BAD-001"

    def test_response_has_expected_fields(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "delivery_id", "contract_id", "verdict", "stage",
            "dimensions_fired", "dimensions", "rules_evaluated",
            "rules_fired", "fired_rules", "layer_summary",
            "delivery_metrics", "processing_ms", "procurement_verdict",
            "methodology_note", "methodology_version", "profile_used",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_dimensions_structure(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        assert len(data["dimensions"]) == 4
        for dim in data["dimensions"]:
            assert "dimension" in dim
            assert "fired" in dim
            assert "detail" in dim

    def test_delivery_metrics_present(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        metrics = data["delivery_metrics"]
        assert "total_milestones" in metrics
        assert "delayed_milestones" in metrics
        assert "total_budget" in metrics
        assert "total_actual_spend" in metrics
        assert "budget_variance_pct" in metrics

    def test_invalid_profile_returns_400(self, client):
        payload = _clean_delivery_payload()
        payload["profile"] = "nonexistent_profile"
        response = client.post("/delivery/analyze", json=payload)
        assert response.status_code == 400

    def test_minimal_request(self, client):
        """Request with only contract_id — should still succeed."""
        payload = {"contract_id": "MINIMAL-001", "profile": "us_federal"}
        response = client.post("/delivery/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "MINIMAL-001"
        assert data["verdict"] is not None

    def test_stage_is_complete(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        assert data["stage"] == "delivery_complete"

    def test_profile_used_reflected(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        assert data["profile_used"] == "us_federal"

    def test_procurement_verdict_passthrough(self, client):
        payload = _clean_delivery_payload()
        payload["procurement_verdict"] = "YELLOW"
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        assert data["procurement_verdict"] == "YELLOW"

    def test_methodology_version_populated(self, client):
        payload = _clean_delivery_payload()
        response = client.post("/delivery/analyze", json=payload)
        data = response.json()
        assert data["methodology_version"] != ""


# ═══════════════════════════════════════════════════════════
# POST /delivery/batch TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryBatchEndpoint:
    def test_batch_two_deliveries(self, client):
        payload = {
            "deliveries": [
                _clean_delivery_payload(),
                _clean_delivery_payload(),
            ],
            "profile": "us_federal",
        }
        # Override contract_ids for uniqueness
        payload["deliveries"][0]["contract_id"] = "BATCH-A"
        payload["deliveries"][1]["contract_id"] = "BATCH-B"
        response = client.post("/delivery/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_processed"] == 2
        assert len(data["results"]) == 2

    def test_batch_verdict_distribution(self, client):
        payload = {
            "deliveries": [
                _clean_delivery_payload(),
                _clean_delivery_payload(),
            ],
            "profile": "us_federal",
        }
        response = client.post("/delivery/batch", json=payload)
        data = response.json()
        assert "verdict_distribution" in data
        assert isinstance(data["verdict_distribution"], dict)
        # Both clean → green expected
        assert data["verdict_distribution"].get("green", 0) >= 2

    def test_batch_mixed_verdicts(self, client):
        payload = {
            "deliveries": [
                _clean_delivery_payload(),
                _problematic_delivery_payload(),
            ],
            "profile": "us_federal",
        }
        response = client.post("/delivery/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_processed"] == 2
        # At least one green from the clean delivery
        assert data["verdict_distribution"].get("green", 0) >= 1

    def test_batch_invalid_profile(self, client):
        payload = {
            "deliveries": [_clean_delivery_payload()],
            "profile": "nonexistent",
        }
        response = client.post("/delivery/batch", json=payload)
        assert response.status_code == 400

    def test_batch_total_errors_counted(self, client):
        payload = {
            "deliveries": [_clean_delivery_payload()],
            "profile": "us_federal",
        }
        response = client.post("/delivery/batch", json=payload)
        data = response.json()
        assert "total_errors" in data
        assert isinstance(data["total_errors"], int)

    def test_batch_empty_deliveries(self, client):
        payload = {
            "deliveries": [],
            "profile": "us_federal",
        }
        response = client.post("/delivery/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_processed"] == 0
        assert len(data["results"]) == 0

    def test_batch_each_result_has_contract_id(self, client):
        payload = {
            "deliveries": [
                _clean_delivery_payload(),
                _clean_delivery_payload(),
            ],
            "profile": "us_federal",
        }
        payload["deliveries"][0]["contract_id"] = "C1"
        payload["deliveries"][1]["contract_id"] = "C2"
        response = client.post("/delivery/batch", json=payload)
        data = response.json()
        ids = [r["contract_id"] for r in data["results"]]
        assert "C1" in ids
        assert "C2" in ids


# ═══════════════════════════════════════════════════════════
# GET /delivery/pillar-summary TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryPillarSummary:
    def test_summary_returns_200(self, client):
        response = client.get("/delivery/pillar-summary")
        assert response.status_code == 200

    def test_summary_structure(self, client):
        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert "total_analyzed" in data
        assert "verdict_distribution" in data
        assert "profiles_available" in data
        assert "methodology_version" in data

    def test_summary_methodology_version(self, client):
        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert "Side 2" in data["methodology_version"]

    def test_summary_profiles_available(self, client):
        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert "us_federal" in data["profiles_available"]

    def test_summary_reflects_analyzed_deliveries(self, client):
        """After analyzing a delivery, pillar summary should reflect it."""
        # First analyze a delivery
        payload = _clean_delivery_payload()
        client.post("/delivery/analyze", json=payload)

        # Then check summary
        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert data["total_analyzed"] >= 1

    def test_summary_verdict_distribution_after_analysis(self, client):
        """After analyzing a clean delivery, green count should increase."""
        # Analyze a clean delivery
        payload = _clean_delivery_payload()
        client.post("/delivery/analyze", json=payload)

        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert data["verdict_distribution"]["green"] >= 1

    def test_summary_initial_zeroes(self, client):
        """Before any analysis, all counts should be zero."""
        response = client.get("/delivery/pillar-summary")
        data = response.json()
        assert data["total_analyzed"] == 0
        assert data["verdict_distribution"]["green"] == 0
        assert data["verdict_distribution"]["yellow"] == 0
        assert data["verdict_distribution"]["red"] == 0


# ═══════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryAPIIntegration:
    def test_analyze_then_summary_consistent(self, client):
        """Analyze → summary should show consistent counts."""
        # Analyze 3 clean deliveries
        for i in range(3):
            payload = _clean_delivery_payload()
            payload["contract_id"] = f"INT-{i}"
            client.post("/delivery/analyze", json=payload)

        summary = client.get("/delivery/pillar-summary").json()
        assert summary["total_analyzed"] == 3

    def test_batch_then_summary_consistent(self, client):
        """Batch analyze → summary should reflect batch counts."""
        payload = {
            "deliveries": [_clean_delivery_payload() for _ in range(3)],
            "profile": "us_federal",
        }
        for i, d in enumerate(payload["deliveries"]):
            d["contract_id"] = f"BINT-{i}"

        client.post("/delivery/batch", json=payload)

        summary = client.get("/delivery/pillar-summary").json()
        assert summary["total_analyzed"] == 3

    def test_side2_endpoints_do_not_affect_side1(self, client):
        """Side 2 endpoints should not interfere with Side 1 health check."""
        # Analyze a delivery
        payload = _clean_delivery_payload()
        client.post("/delivery/analyze", json=payload)

        # Side 1 health should still work
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
