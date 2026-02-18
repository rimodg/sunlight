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
    """Create a test client with a populated temp database (auth disabled)."""
    import api
    import auth
    import ingestion
    monkeypatch.setattr(api, 'DB_PATH', populated_db)
    monkeypatch.setattr(auth, 'AUTH_ENABLED', False)
    auth.init_auth_schema(populated_db)
    ingestion.init_ingestion_schema(populated_db)
    return TestClient(api.app)


@pytest.fixture
def auth_client(populated_db, monkeypatch):
    """Create a test client with auth ENABLED and a pre-generated key."""
    import api
    import auth
    monkeypatch.setattr(api, 'DB_PATH', populated_db)
    monkeypatch.setattr(auth, 'AUTH_ENABLED', True)
    auth.init_auth_schema(populated_db)
    # Generate a test key
    result = auth.generate_api_key(
        populated_db, "test_client",
        rate_limit=100, scopes="read,analyze,admin"
    )
    client = TestClient(api.app)
    return client, result['api_key']


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

    def test_detection_report_json(self, api_client):
        resp = api_client.get("/reports/detection/DOD-OUTLIER")
        assert resp.status_code == 200
        data = resp.json()
        assert data['report_type'] == 'SUNLIGHT Detection Report'
        assert data['contract']['contract_id'] == 'DOD-OUTLIER'
        assert data['assessment']['risk_level'] in ('RED', 'YELLOW', 'GREEN', 'GRAY')
        assert data['assessment']['risk_label'] != ''
        # Explainable evidence
        assert 'price_analysis' in data['evidence']
        assert 'finding' in data['evidence']['price_analysis']
        assert 'bayesian_analysis' in data['evidence']
        assert 'finding' in data['evidence']['bayesian_analysis']
        # Recommendations
        assert 'action' in data['recommendations']
        assert len(data['recommendations']['next_steps']) > 0
        # Methodology transparency
        assert 'methodology' in data
        assert data['methodology']['transparency_note'] is not None
        # Legal framework
        assert len(data['legal_framework']) >= 0  # May be empty for GREEN

    def test_detection_report_markdown(self, api_client):
        resp = api_client.get("/reports/detection/DOD-OUTLIER", params={"format": "markdown"})
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('text/markdown')
        text = resp.text
        assert '# SUNLIGHT Detection Report' in text
        assert 'DOD-OUTLIER' in text
        assert 'Evidence Summary' in text
        assert 'Recommended Action' in text

    def test_detection_report_not_found(self, api_client):
        resp = api_client.get("/reports/detection/NONEXISTENT")
        assert resp.status_code == 404

    def test_detection_report_green_contract(self, api_client):
        resp = api_client.get("/reports/detection/DOD-001")
        assert resp.status_code == 200
        data = resp.json()
        # DOD-001 is $5M (median range) — should be GREEN or YELLOW, not RED
        assert data['assessment']['risk_level'] in ('GREEN', 'YELLOW', 'GRAY')
        assert 'context' in data
        assert data['context']['total_comparables_in_agency'] > 0

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


class TestAuth:

    def test_missing_key_returns_401(self, auth_client):
        client, _ = auth_client
        resp = client.get("/health")
        assert resp.status_code == 401
        assert "Missing API key" in resp.json()['detail']

    def test_invalid_key_returns_401(self, auth_client):
        client, _ = auth_client
        resp = client.get("/health", headers={"X-API-Key": "sk_sunlight_bogus"})
        assert resp.status_code == 401
        assert "Invalid" in resp.json()['detail']

    def test_valid_key_succeeds(self, auth_client):
        client, key = auth_client
        resp = client.get("/health", headers={"X-API-Key": key})
        assert resp.status_code == 200
        assert resp.json()['status'] == 'healthy'

    def test_admin_generate_key(self, auth_client):
        client, key = auth_client
        resp = client.post("/admin/keys", json={
            "client_name": "new_client",
            "rate_limit": 50,
            "scopes": "read",
        }, headers={"X-API-Key": key})
        assert resp.status_code == 201
        data = resp.json()
        assert data['client_name'] == 'new_client'
        assert data['api_key'].startswith('sk_sunlight_')
        assert data['rate_limit'] == 50

    def test_admin_list_keys(self, auth_client):
        client, key = auth_client
        resp = client.get("/admin/keys", headers={"X-API-Key": key})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_admin_rotate_key(self, auth_client):
        client, key = auth_client
        # Get current key_id
        keys = client.get("/admin/keys", headers={"X-API-Key": key}).json()
        key_id = keys[0]['key_id']
        # Rotate
        resp = client.post("/admin/keys/rotate", json={"key_id": key_id},
                           headers={"X-API-Key": key})
        assert resp.status_code == 200
        data = resp.json()
        assert data['api_key'].startswith('sk_sunlight_')
        assert data['key_id'] != key_id

    def test_admin_revoke_key(self, auth_client):
        client, key = auth_client
        # Generate a key to revoke
        gen_resp = client.post("/admin/keys", json={"client_name": "disposable"},
                               headers={"X-API-Key": key})
        new_key_id = gen_resp.json()['key_id']
        new_api_key = gen_resp.json()['api_key']
        # Verify it works
        assert client.get("/health", headers={"X-API-Key": new_api_key}).status_code == 200
        # Revoke
        resp = client.delete(f"/admin/keys/{new_key_id}", headers={"X-API-Key": key})
        assert resp.status_code == 200
        # Verify revoked key is rejected
        resp = client.get("/health", headers={"X-API-Key": new_api_key})
        assert resp.status_code == 403

    def test_admin_key_usage(self, auth_client):
        client, key = auth_client
        # Make a few requests
        client.get("/health", headers={"X-API-Key": key})
        client.get("/contracts", headers={"X-API-Key": key})
        # Get usage
        keys = client.get("/admin/keys", headers={"X-API-Key": key}).json()
        key_id = keys[0]['key_id']
        resp = client.get(f"/admin/keys/{key_id}/usage", headers={"X-API-Key": key})
        assert resp.status_code == 200
        assert resp.json()['total_requests'] >= 2

    def test_non_admin_rejected(self, auth_client):
        client, admin_key = auth_client
        # Generate a non-admin key via admin endpoint
        gen_resp = client.post("/admin/keys", json={
            "client_name": "reader_only",
            "scopes": "read",
        }, headers={"X-API-Key": admin_key})
        reader_key = gen_resp.json()['api_key']
        # Try admin endpoint with reader key
        resp = client.get("/admin/keys", headers={"X-API-Key": reader_key})
        assert resp.status_code == 403

    def test_rate_limiting(self, populated_db, monkeypatch):
        import api
        import auth
        monkeypatch.setattr(api, 'DB_PATH', populated_db)
        monkeypatch.setattr(auth, 'AUTH_ENABLED', True)
        auth.init_auth_schema(populated_db)
        # Reset the module-level rate limiter
        auth._rate_limiter = auth.RateLimiter()
        # Create key with rate limit of 3
        result = auth.generate_api_key(
            populated_db, "rate_test", rate_limit=3, rate_window=3600,
            scopes="read,analyze,admin"
        )
        test_key = result['api_key']
        client = TestClient(api.app)
        # 3 requests should work
        for _ in range(3):
            resp = client.get("/health", headers={"X-API-Key": test_key})
            assert resp.status_code == 200
        # 4th should be rate limited
        resp = client.get("/health", headers={"X-API-Key": test_key})
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()['detail']


class TestIngestion:

    def test_ingest_json_single(self, api_client):
        import json
        contract = {
            "contract_id": "INGEST_TEST_001",
            "award_amount": 500000,
            "vendor_name": "Test Vendor Inc",
            "agency_name": "DEPARTMENT OF DEFENSE",
            "description": "Test contract for ingestion",
        }
        content = json.dumps(contract).encode()
        resp = api_client.post(
            "/ingest",
            files={"file": ("test.json", content, "application/json")},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data['status'] == 'PENDING'
        assert 'job_id' in data

        # Poll until complete (background task runs synchronously in test client)
        job_id = data['job_id']
        status_resp = api_client.get(f"/ingest/{job_id}")
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status['status'] in ('COMPLETED', 'PROCESSING', 'PENDING')

    def test_ingest_json_array(self, api_client):
        import json
        contracts = [
            {"contract_id": "INGEST_ARR_001", "award_amount": 100000,
             "vendor_name": "Vendor A", "agency_name": "DEPARTMENT OF DEFENSE"},
            {"contract_id": "INGEST_ARR_002", "award_amount": 200000,
             "vendor_name": "Vendor B", "agency_name": "DEPARTMENT OF DEFENSE"},
        ]
        content = json.dumps(contracts).encode()
        resp = api_client.post(
            "/ingest",
            files={"file": ("batch.json", content, "application/json")},
        )
        assert resp.status_code == 202
        job_id = resp.json()['job_id']
        status = api_client.get(f"/ingest/{job_id}").json()
        assert status['total_records'] == 2

    def test_ingest_csv(self, api_client):
        csv_content = (
            "contract_id,award_amount,vendor_name,agency_name,description\n"
            "CSV_TEST_001,750000,CSV Vendor,DEPARTMENT OF DEFENSE,CSV test\n"
            "CSV_TEST_002,350000,CSV Vendor 2,DEPARTMENT OF DEFENSE,CSV test 2\n"
        ).encode()
        resp = api_client.post(
            "/ingest",
            files={"file": ("contracts.csv", csv_content, "text/csv")},
        )
        assert resp.status_code == 202
        job_id = resp.json()['job_id']
        status = api_client.get(f"/ingest/{job_id}").json()
        assert status['source_format'] == 'csv'
        assert status['total_records'] == 2

    def test_ingest_unsupported_format(self, api_client):
        resp = api_client.post(
            "/ingest",
            files={"file": ("data.xyz", b"some data", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()['detail']

    def test_ingest_empty_file(self, api_client):
        resp = api_client.post(
            "/ingest",
            files={"file": ("empty.json", b"", "application/json")},
        )
        assert resp.status_code == 400
        assert "Empty" in resp.json()['detail']

    def test_ingest_job_not_found(self, api_client):
        resp = api_client.get("/ingest/nonexistent_job")
        assert resp.status_code == 404
