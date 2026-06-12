"""
Tests for SUNLIGHT Intelligence Alert System — API Endpoints.

Covers:
    GET /alerts/config:
        - Returns 200 with config structure
        - Does not expose secrets
        - Shows emitter types

    POST /alerts/test:
        - Fires synthetic alert through configured emitters
        - Returns emission results

    POST /alerts/triage:
        - Returns triage brief from alert input
        - Ranking, patterns, executive summary
        - Empty alerts list handled
        - Vendor clustering detected
        - Brief IDs populated
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient
from api import app


@pytest.fixture
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════
# GET /alerts/config TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertConfigEndpoint:
    def test_config_returns_200(self, client):
        response = client.get("/alerts/config")
        assert response.status_code == 200

    def test_config_structure(self, client):
        data = client.get("/alerts/config").json()
        expected_fields = [
            "enabled", "min_verdict", "min_confidence", "min_dimensions",
            "delivery_alerts_enabled", "batch_mode", "max_alerts_per_hour",
            "cooldown_seconds", "emitter_count", "emitter_types",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_config_no_secrets(self, client):
        data = client.get("/alerts/config").json()
        text = str(data).lower()
        assert "webhook_url" not in text
        assert "shared_secret" not in text

    def test_config_shows_emitter_types(self, client):
        data = client.get("/alerts/config").json()
        assert isinstance(data["emitter_types"], list)


# ═══════════════════════════════════════════════════════════
# POST /alerts/test TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertTestEndpoint:
    def test_test_returns_200(self, client):
        response = client.post("/alerts/test")
        assert response.status_code == 200

    def test_test_has_emissions(self, client):
        data = client.post("/alerts/test").json()
        assert "emissions" in data
        assert isinstance(data["emissions"], list)

    def test_test_has_success_field(self, client):
        data = client.post("/alerts/test").json()
        assert "success" in data
        assert isinstance(data["success"], bool)


# ═══════════════════════════════════════════════════════════
# POST /alerts/triage TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertTriageEndpoint:
    def test_triage_returns_200(self, client):
        payload = {
            "alerts": [
                {
                    "contract_id": "T001",
                    "verdict": "red",
                    "confidence": 0.85,
                    "priority": "high",
                    "dimensions_fired": 2,
                    "vendor": "TestCorp",
                    "rule_citations": [
                        {
                            "rule_id": "PROC-001",
                            "rule_name": "Test Rule",
                            "layer": "procurement",
                            "confidence": 0.90,
                        }
                    ],
                }
            ],
            "total_contracts": 100,
            "jurisdiction_profile": "us_federal",
        }
        response = client.post("/alerts/triage", json=payload)
        assert response.status_code == 200

    def test_triage_brief_structure(self, client):
        payload = {
            "alerts": [
                {
                    "contract_id": "T001",
                    "verdict": "red",
                    "confidence": 0.85,
                    "priority": "critical",
                    "dimensions_fired": 3,
                }
            ],
            "batch_id": "B001",
            "total_contracts": 50,
            "jurisdiction_profile": "us_federal",
        }
        data = client.post("/alerts/triage", json=payload).json()
        expected_fields = [
            "brief_id", "batch_id", "jurisdiction_profile",
            "total_contracts_analyzed", "total_alerts",
            "alerts_by_priority", "alerts_by_dimension",
            "patterns", "executive_summary",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_triage_empty_alerts(self, client):
        payload = {
            "alerts": [],
            "total_contracts": 50,
            "jurisdiction_profile": "us_federal",
        }
        data = client.post("/alerts/triage", json=payload).json()
        assert data["total_alerts"] == 0
        assert len(data["patterns"]) == 0

    def test_triage_vendor_clustering(self, client):
        """3+ alerts with same vendor → vendor_clustering pattern."""
        payload = {
            "alerts": [
                {
                    "contract_id": f"VC{i}",
                    "verdict": "red",
                    "confidence": 0.85,
                    "priority": "high",
                    "dimensions_fired": 2,
                    "vendor": "ShadyCorp",
                }
                for i in range(4)
            ],
            "total_contracts": 100,
            "jurisdiction_profile": "us_federal",
        }
        data = client.post("/alerts/triage", json=payload).json()
        vendor_patterns = [
            p for p in data["patterns"]
            if p["pattern_type"] == "vendor_clustering"
        ]
        assert len(vendor_patterns) == 1
        assert "ShadyCorp" in vendor_patterns[0]["description"]

    def test_triage_priority_distribution(self, client):
        payload = {
            "alerts": [
                {"contract_id": "P1", "verdict": "red", "confidence": 0.95, "priority": "critical", "dimensions_fired": 3},
                {"contract_id": "P2", "verdict": "red", "confidence": 0.80, "priority": "high", "dimensions_fired": 2},
                {"contract_id": "P3", "verdict": "yellow", "confidence": 0.65, "priority": "elevated", "dimensions_fired": 1},
            ],
            "total_contracts": 100,
            "jurisdiction_profile": "us_federal",
        }
        data = client.post("/alerts/triage", json=payload).json()
        assert data["alerts_by_priority"]["critical"] == 1
        assert data["alerts_by_priority"]["high"] == 1
        assert data["alerts_by_priority"]["elevated"] == 1

    def test_triage_executive_summary_populated(self, client):
        payload = {
            "alerts": [
                {"contract_id": "E1", "verdict": "red", "confidence": 0.85, "priority": "high", "dimensions_fired": 2},
            ],
            "batch_id": "SUMMARY-TEST",
            "total_contracts": 200,
            "jurisdiction_profile": "us_federal",
        }
        data = client.post("/alerts/triage", json=payload).json()
        assert len(data["executive_summary"]) > 0
        assert "SUMMARY-TEST" in data["executive_summary"]
        assert "us_federal" in data["executive_summary"]

    def test_triage_batch_id_passthrough(self, client):
        payload = {
            "alerts": [{"contract_id": "B1", "verdict": "red", "priority": "high"}],
            "batch_id": "MY-BATCH-123",
            "total_contracts": 10,
        }
        data = client.post("/alerts/triage", json=payload).json()
        assert data["batch_id"] == "MY-BATCH-123"

    def test_triage_does_not_affect_side1(self, client):
        """Alert triage endpoint does not affect Side 1 health."""
        payload = {
            "alerts": [{"contract_id": "X1", "verdict": "red", "priority": "critical"}],
            "total_contracts": 10,
        }
        client.post("/alerts/triage", json=payload)
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

    def test_triage_with_delivery_fields(self, client):
        """Alerts with delivery fields are handled correctly."""
        payload = {
            "alerts": [
                {
                    "contract_id": "D1",
                    "verdict": "red",
                    "confidence": 0.85,
                    "priority": "critical",
                    "dimensions_fired": 3,
                    "delivery_verdict": "red",
                    "delivery_dimensions_fired": 2,
                    "delivery_rule_citations": [
                        {
                            "rule_id": "DEL-MILE-001",
                            "rule_name": "Critical milestone delay",
                            "layer": "milestone",
                            "confidence": 0.85,
                        }
                    ],
                }
            ],
            "total_contracts": 50,
        }
        data = client.post("/alerts/triage", json=payload).json()
        assert data["total_alerts"] == 1
