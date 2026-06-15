"""
Tests for SUNLIGHT Side 4 — Recovery Intelligence API Endpoints.

Covers:
    POST /recovery/record — creates record with IDENTIFIED status
    POST /recovery/confirm — updates status to CONFIRMED
    POST /recovery/allocate — returns correct gap-weighted allocation
    POST /recovery/redirect — creates redirection record
    GET /recovery/status/{recovery_id} — full lifecycle with linked redirections
    GET /recovery/impact — complete report with executive summary
    GET /recovery/cycle/{source_contract_id} — traces one contract's full cycle
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient
import api


@pytest.fixture(autouse=True)
def reset_registries():
    """Reset module-level recovery state between tests."""
    api._recovery_ledger.reset()
    api._redirection_registry.reset()
    yield
    api._recovery_ledger.reset()
    api._redirection_registry.reset()


@pytest.fixture
def client():
    return TestClient(api.app)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _create_record(client, **overrides):
    """Create a recovery record and return the JSON response."""
    payload = {
        "source_contract_id": "C001",
        "recovery_amount": 500_000,
        "currency": "USD",
        "country_office": "Nigeria",
        "country_code": "NG",
        "original_pillar": "health",
        "source_verdict": "red",
        "source_confidence": 0.85,
    }
    payload.update(overrides)
    resp = client.post("/recovery/record", json=payload)
    assert resp.status_code == 200
    return resp.json()


def _cpd_profile_dict():
    """Minimal CPD profile dict for allocation tests."""
    return {
        "country_office": "Nigeria",
        "country_code": "NG",
        "programme_cycle": "2022-2026",
        "total_programme_budget": 50_000_000,
        "currency": "USD",
        "pillars": [
            {
                "pillar": "health",
                "sdg_targets": ["SDG 3"],
                "target_percentage": 0.30,
                "target_amount": 15_000_000,
                "actual_spend": 10_000_000,
                "actual_percentage": 0.20,
            },
            {
                "pillar": "education",
                "sdg_targets": ["SDG 4"],
                "target_percentage": 0.25,
                "target_amount": 12_500_000,
                "actual_spend": 12_000_000,
                "actual_percentage": 0.24,
            },
        ],
    }


# ═══════════════════════════════════════════════════════════
# POST /recovery/record
# ═══════════════════════════════════════════════════════════


class TestRecoveryRecordEndpoint:
    def test_creates_record_with_identified_status(self, client):
        data = _create_record(client)
        assert data["status"] == "identified"
        assert data["source_contract_id"] == "C001"
        assert data["recovery_amount"] == 500_000
        assert data["currency"] == "USD"
        assert data["country_office"] == "Nigeria"
        assert data["country_code"] == "NG"
        assert data["original_pillar"] == "health"
        assert "recovery_id" in data

    def test_creates_unique_ids(self, client):
        d1 = _create_record(client, source_contract_id="C001")
        d2 = _create_record(client, source_contract_id="C002")
        assert d1["recovery_id"] != d2["recovery_id"]


# ═══════════════════════════════════════════════════════════
# POST /recovery/confirm
# ═══════════════════════════════════════════════════════════


class TestRecoveryConfirmEndpoint:
    def test_confirms_recovery(self, client):
        created = _create_record(client)
        resp = client.post("/recovery/confirm", json={
            "recovery_id": created["recovery_id"],
            "confirmation_date": "2026-01-15",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["confirmation_date"] == "2026-01-15"

    def test_confirm_not_found(self, client):
        resp = client.post("/recovery/confirm", json={
            "recovery_id": "NONEXISTENT",
            "confirmation_date": "2026-01-15",
        })
        assert resp.status_code == 404

    def test_confirm_invalid_date(self, client):
        created = _create_record(client)
        resp = client.post("/recovery/confirm", json={
            "recovery_id": created["recovery_id"],
            "confirmation_date": "not-a-date",
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════
# POST /recovery/allocate
# ═══════════════════════════════════════════════════════════


class TestRecoveryAllocateEndpoint:
    def test_returns_gap_weighted_allocation(self, client):
        created = _create_record(client)
        resp = client.post("/recovery/allocate", json={
            "recovery_id": created["recovery_id"],
            "cpd_profile": _cpd_profile_dict(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["recovery_id"] == created["recovery_id"]
        assert data["recovery_amount"] == 500_000
        assert data["methodology"] == "gap_weighted"
        assert len(data["pillar_allocations"]) == 2

        # Allocations should sum to recovery amount
        total_allocated = sum(
            pa["allocation_amount"] for pa in data["pillar_allocations"]
        )
        assert abs(total_allocated - 500_000) < 1.0

        # Health has bigger gap (10% vs 1%) so should get more
        health = next(
            pa for pa in data["pillar_allocations"] if pa["pillar"] == "health"
        )
        education = next(
            pa for pa in data["pillar_allocations"] if pa["pillar"] == "education"
        )
        assert health["allocation_amount"] > education["allocation_amount"]

    def test_allocate_not_found(self, client):
        resp = client.post("/recovery/allocate", json={
            "recovery_id": "NONEXISTENT",
            "cpd_profile": _cpd_profile_dict(),
        })
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════
# POST /recovery/redirect
# ═══════════════════════════════════════════════════════════


class TestRecoveryRedirectEndpoint:
    def test_creates_redirection_record(self, client):
        created = _create_record(client)
        resp = client.post("/recovery/redirect", json={
            "recovery_id": created["recovery_id"],
            "target_contract_id": "NEW-001",
            "target_pillar": "health",
            "target_sdg": "SDG 3",
            "target_contract_value": 250_000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["recovery_id"] == created["recovery_id"]
        assert data["target_contract_id"] == "NEW-001"
        assert data["target_pillar"] == "health"
        assert data["target_sdg"] == "SDG 3"
        assert data["target_contract_value"] == 250_000
        assert "redirection_id" in data

    def test_redirect_not_found(self, client):
        resp = client.post("/recovery/redirect", json={
            "recovery_id": "NONEXISTENT",
            "target_contract_id": "NEW-001",
            "target_pillar": "health",
            "target_sdg": "SDG 3",
            "target_contract_value": 250_000,
        })
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════
# GET /recovery/status/{recovery_id}
# ═══════════════════════════════════════════════════════════


class TestRecoveryStatusEndpoint:
    def test_returns_full_lifecycle(self, client):
        created = _create_record(client)
        recovery_id = created["recovery_id"]

        # Add a redirection
        client.post("/recovery/redirect", json={
            "recovery_id": recovery_id,
            "target_contract_id": "NEW-001",
            "target_pillar": "health",
            "target_sdg": "SDG 3",
            "target_contract_value": 250_000,
        })

        resp = client.get(f"/recovery/status/{recovery_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["recovery_id"] == recovery_id
        assert data["source_contract_id"] == "C001"
        assert data["source_verdict"] == "red"
        assert data["status"] == "identified"
        assert data["recovery_amount"] == 500_000
        assert len(data["redirections"]) == 1
        assert data["redirections"][0]["target_contract_id"] == "NEW-001"

    def test_status_not_found(self, client):
        resp = client.get("/recovery/status/NONEXISTENT")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════
# GET /recovery/impact
# ═══════════════════════════════════════════════════════════


class TestRecoveryImpactEndpoint:
    def test_returns_complete_report(self, client):
        # Create a recovery and confirm it so it counts as recovered
        created = _create_record(client)
        recovery_id = created["recovery_id"]

        # Confirm
        client.post("/recovery/confirm", json={
            "recovery_id": recovery_id,
            "confirmation_date": "2026-01-15",
        })

        # Add a redirection
        client.post("/recovery/redirect", json={
            "recovery_id": recovery_id,
            "target_contract_id": "NEW-001",
            "target_pillar": "health",
            "target_sdg": "SDG 3",
            "target_contract_value": 250_000,
        })

        resp = client.get("/recovery/impact", params={
            "country_office": "Nigeria",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["country_office"] == "Nigeria"
        assert data["total_redirections"] == 1
        assert data["total_amount_redirected"] == 250_000
        assert len(data["executive_summary"]) > 0
        assert "report_id" in data

    def test_empty_report(self, client):
        resp = client.get("/recovery/impact", params={
            "country_office": "Nigeria",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_recoveries"] == 0
        assert data["total_redirections"] == 0

    def test_impact_invalid_date(self, client):
        resp = client.get("/recovery/impact", params={
            "country_office": "Nigeria",
            "period_start": "bad-date",
            "period_end": "2026-06-30",
        })
        assert resp.status_code == 400


# ═══════════════════════════════════════════════════════════
# GET /recovery/cycle/{source_contract_id}
# ═══════════════════════════════════════════════════════════


class TestRecoveryCycleEndpoint:
    def test_traces_full_cycle(self, client):
        created = _create_record(client, source_contract_id="C-TRACE-001")
        recovery_id = created["recovery_id"]

        # Redirect
        client.post("/recovery/redirect", json={
            "recovery_id": recovery_id,
            "target_contract_id": "NEW-T-001",
            "target_pillar": "education",
            "target_sdg": "SDG 4",
            "target_contract_value": 300_000,
        })

        resp = client.get("/recovery/cycle/C-TRACE-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source_contract_id"] == "C-TRACE-001"
        assert data["source_verdict"] == "red"
        assert data["recovery_amount"] == 500_000
        assert data["status"] == "identified"
        assert len(data["redirections"]) == 1
        rd = data["redirections"][0]
        assert rd["target_contract_id"] == "NEW-T-001"
        assert rd["target_pillar"] == "education"
        assert rd["target_sdg"] == "SDG 4"
        assert rd["full_cycle_complete"] is False

    def test_cycle_not_found(self, client):
        resp = client.get("/recovery/cycle/NONEXISTENT")
        assert resp.status_code == 404
