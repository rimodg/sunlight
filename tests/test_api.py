"""
Tests for the SUNLIGHT REST API.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient


@pytest.fixture
def api_client(populated_db, monkeypatch):
    """Create a test client with a populated temp database."""
    monkeypatch.setattr('api.DB_PATH', populated_db)
    # Need to re-import after patching
    import api
    api.DB_PATH = populated_db
    return TestClient(api.app)


class TestHealth:

    def test_health_returns_200(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'healthy'
        assert data['contract_count'] > 0

    def test_health_shows_version(self, api_client):
        resp = api_client.get("/health")
        assert 'version' in resp.json()


class TestContracts:

    def test_list_contracts(self, api_client):
        resp = api_client.get("/contracts")
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] > 0
        assert len(data['items']) > 0

    def test_list_contracts_with_agency_filter(self, api_client):
        resp = api_client.get("/contracts", params={"agency": "Defense"})
        assert resp.status_code == 200
        for item in resp.json()['items']:
            assert 'Defense' in item['agency_name']

    def test_list_contracts_with_amount_filter(self, api_client):
        resp = api_client.get("/contracts", params={"min_amount": 10_000_000})
        assert resp.status_code == 200
        for item in resp.json()['items']:
            assert item['award_amount'] >= 10_000_000

    def test_list_contracts_pagination(self, api_client):
        resp = api_client.get("/contracts", params={"limit": 3, "offset": 0})
        data = resp.json()
        assert len(data['items']) <= 3
        assert data['offset'] == 0
        assert data['limit'] == 3

    def test_get_contract_by_id(self, api_client):
        resp = api_client.get("/contracts/DOD-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data['contract_id'] == 'DOD-001'
        assert data['award_amount'] == 5_000_000

    def test_get_contract_not_found(self, api_client):
        resp = api_client.get("/contracts/NONEXISTENT")
        assert resp.status_code == 404

    def test_submit_new_contract(self, api_client):
        resp = api_client.post("/contracts", json={
            "contract_id": "NEW-001",
            "award_amount": 1_500_000,
            "vendor_name": "NEW_VENDOR",
            "agency_name": "Department of Energy",
            "description": "Test contract submission",
        })
        assert resp.status_code == 201
        assert resp.json()['contract_id'] == 'NEW-001'

    def test_submit_duplicate_contract(self, api_client):
        resp = api_client.post("/contracts", json={
            "contract_id": "DOD-001",
            "award_amount": 5_000_000,
            "vendor_name": "VENDOR_A",
            "agency_name": "Department of Defense",
        })
        assert resp.status_code == 409

    def test_submit_invalid_amount(self, api_client):
        resp = api_client.post("/contracts", json={
            "contract_id": "BAD-001",
            "award_amount": -100,
            "vendor_name": "VENDOR",
            "agency_name": "Agency",
        })
        assert resp.status_code == 422


class TestAnalysis:

    def test_analyze_single_with_comparables(self, api_client):
        resp = api_client.post("/analyze", json={
            "contract_id": "DOD-OUTLIER",
            "award_amount": 35_000_000,
            "vendor_name": "SUSPECT_VENDOR",
            "agency_name": "Department of Defense",
            "description": "Special project",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['fraud_tier'] in ('RED', 'YELLOW', 'GREEN', 'GRAY')
        assert data['comparable_count'] >= 3
        assert len(data['reasoning']) > 0
        assert data['methodology_version'] is not None

    def test_analyze_single_insufficient_data(self, api_client):
        resp = api_client.post("/analyze", json={
            "contract_id": "LONE-001",
            "award_amount": 5_000_000,
            "vendor_name": "LONE_VENDOR",
            "agency_name": "Nonexistent Agency",
            "description": "No comparables",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['fraud_tier'] == 'GRAY'
        assert data['comparable_count'] < 3

    def test_batch_analysis(self, api_client):
        resp = api_client.post("/analyze/batch", json={
            "run_seed": 99,
            "n_bootstrap": 100,
            "limit": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data['n_scored'] == 5
        assert data['n_errors'] == 0
        assert 'tier_counts' in data
        assert data['run_id'].startswith('run_')


class TestScores:

    def test_list_scores_after_batch(self, api_client):
        # First run a batch
        batch_resp = api_client.post("/analyze/batch", json={
            "run_seed": 77,
            "n_bootstrap": 100,
            "limit": 5,
        })
        run_id = batch_resp.json()['run_id']

        resp = api_client.get("/scores", params={"run_id": run_id})
        assert resp.status_code == 200
        assert resp.json()['total'] == 5

    def test_filter_by_tier(self, api_client):
        # Run batch first
        api_client.post("/analyze/batch", json={"run_seed": 88, "n_bootstrap": 100})

        resp = api_client.get("/scores", params={"tier": "GREEN"})
        assert resp.status_code == 200
        for item in resp.json()['items']:
            assert item['fraud_tier'] == 'GREEN'

    def test_get_scores_for_contract(self, api_client):
        # Run batch first
        api_client.post("/analyze/batch", json={"run_seed": 66, "n_bootstrap": 100, "limit": 16})

        resp = api_client.get("/scores/DOD-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data['contract_id'] == 'DOD-001'
        assert len(data['scores']) >= 1

    def test_scores_not_found(self, api_client):
        resp = api_client.get("/scores/NONEXISTENT")
        assert resp.status_code == 404


class TestReports:

    def test_evidence_package(self, api_client):
        resp = api_client.get("/reports/evidence/DOD-OUTLIER")
        assert resp.status_code == 200
        data = resp.json()
        assert data['contract_id'] == 'DOD-OUTLIER'
        assert data['sample_size'] > 0
        assert 'bootstrap_markup' in data
        assert 'bayesian_fraud_probability' in data
        assert len(data['reasoning']) > 0
        assert data['methodology_version'] is not None

    def test_evidence_not_found(self, api_client):
        resp = api_client.get("/reports/evidence/NONEXISTENT")
        assert resp.status_code == 404

    def test_triage_queue(self, api_client):
        # Run batch first
        api_client.post("/analyze/batch", json={"run_seed": 55, "n_bootstrap": 100})

        resp = api_client.get("/reports/triage")
        assert resp.status_code == 200
        data = resp.json()
        # All items should be RED or YELLOW
        for item in data['items']:
            assert item['fraud_tier'] in ('RED', 'YELLOW')


class TestRuns:

    def test_list_runs(self, api_client):
        api_client.post("/analyze/batch", json={"run_seed": 44, "n_bootstrap": 100, "limit": 5})
        resp = api_client.get("/runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_run_detail(self, api_client):
        batch_resp = api_client.post("/analyze/batch", json={"run_seed": 33, "n_bootstrap": 100, "limit": 5})
        run_id = batch_resp.json()['run_id']

        resp = api_client.get(f"/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data['run_id'] == run_id
        assert 'verification' in data

    def test_run_not_found(self, api_client):
        resp = api_client.get("/runs/nonexistent_run")
        assert resp.status_code == 404


class TestAudit:

    def test_audit_trail(self, api_client):
        # Generate some audit entries via batch
        api_client.post("/analyze/batch", json={"run_seed": 22, "n_bootstrap": 100, "limit": 5})

        resp = api_client.get("/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert data['chain_valid'] is True
        assert len(data['entries']) > 0


class TestMethodology:

    def test_methodology_endpoint(self, api_client):
        resp = api_client.get("/methodology")
        assert resp.status_code == 200
        data = resp.json()
        assert 'statistical_methods' in data
        assert 'thresholds' in data
        assert 'tier_definitions' in data
        assert 'legal_framework' in data
        assert 'transparency_commitment' in data

    def test_thresholds_match_engine(self, api_client):
        resp = api_client.get("/methodology")
        thresholds = resp.json()['thresholds']
        assert thresholds['extreme_markup_pct'] == 300
        assert thresholds['investigation_worthy_pct'] == 75


class TestOpenAPIDocs:

    def test_openapi_schema(self, api_client):
        resp = api_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema['info']['title'] == 'SUNLIGHT Fraud Detection API'
        assert '/health' in schema['paths']
        assert '/analyze' in schema['paths']
        assert '/analyze/batch' in schema['paths']
