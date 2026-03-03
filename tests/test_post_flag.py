"""
Tests for the post-flag intelligence layer:
  - Vendor risk scoring (vendor_intelligence)
  - Case package generation (case_builder)
  - Priority queue ordering (priority_queue)
  - OCDS adapter field mapping (ocds_adapter)
  - API v2 routes (api_v2_routes) via FastAPI TestClient
"""

import os
import sys
import json
import pytest
import sqlite3
import tempfile
import hashlib

# Ensure code directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

# Disable auth for tests
os.environ['SUNLIGHT_AUTH_ENABLED'] = 'false'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def intel_db():
    """Create a temp DB with data suitable for vendor intelligence + case builder tests."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    c = conn.cursor()

    # Schema
    c.execute("""CREATE TABLE contracts (
        contract_id TEXT PRIMARY KEY,
        award_amount REAL,
        vendor_name TEXT,
        agency_name TEXT,
        description TEXT,
        start_date TEXT,
        location TEXT,
        raw_data TEXT,
        raw_data_hash TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE contracts_clean (
        contract_id TEXT PRIMARY KEY,
        award_amount REAL,
        vendor_name TEXT,
        agency_name TEXT,
        description TEXT,
        start_date TEXT,
        end_date TEXT,
        award_type TEXT,
        num_offers INTEGER,
        extent_competed TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE analysis_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT,
        completed_at TEXT,
        status TEXT,
        run_seed INTEGER,
        config_json TEXT,
        config_hash TEXT,
        dataset_hash TEXT,
        contracts_analyzed INTEGER,
        n_contracts INTEGER,
        n_scored INTEGER,
        n_errors INTEGER,
        code_commit_hash TEXT,
        environment_json TEXT,
        model_version TEXT,
        summary_json TEXT,
        fdr_n_tests INTEGER,
        fdr_n_significant INTEGER
    )""")

    c.execute("""CREATE TABLE contract_scores (
        score_id TEXT PRIMARY KEY,
        contract_id TEXT,
        run_id TEXT,
        fraud_tier TEXT,
        tier TEXT,
        triage_priority INTEGER,
        confidence_score INTEGER,
        raw_pvalue REAL,
        fdr_adjusted_pvalue REAL,
        survives_fdr INTEGER,
        markup_pct REAL,
        markup_ci_lower REAL,
        markup_ci_upper REAL,
        raw_zscore REAL,
        log_zscore REAL,
        bootstrap_percentile REAL,
        percentile_ci_lower REAL,
        percentile_ci_upper REAL,
        bayesian_prior REAL,
        bayesian_likelihood_ratio REAL,
        bayesian_posterior REAL,
        comparable_count INTEGER,
        insufficient_comparables INTEGER,
        selection_params_json TEXT,
        scored_at TEXT,
        analyzed_at TEXT,
        UNIQUE(contract_id, run_id)
    )""")

    c.execute("""CREATE TABLE political_donations (
        vendor_name TEXT,
        recipient_name TEXT,
        amount REAL,
        date TEXT,
        cycle TEXT,
        source TEXT
    )""")

    c.execute("""CREATE TABLE audit_log (
        log_id TEXT PRIMARY KEY,
        sequence_number INTEGER UNIQUE,
        timestamp TEXT,
        action_type TEXT,
        entity_id TEXT,
        previous_log_hash TEXT,
        current_log_hash TEXT,
        action TEXT,
        run_id TEXT,
        details TEXT,
        previous_hash TEXT,
        entry_hash TEXT
    )""")

    # Seed data
    run_id = "test-run-001"

    # Vendor ACME has 5 contracts at DOD, 2 at DOE — high concentration at DOD
    contracts = [
        ("C-001", 10_000_000, "ACME Corp", "Department of Defense", "Equipment", "2025-01-15"),
        ("C-002", 12_000_000, "ACME Corp", "Department of Defense", "Maintenance", "2025-02-20"),
        ("C-003", 15_000_000, "ACME Corp", "Department of Defense", "IT Services", "2025-03-10"),
        ("C-004", 8_000_000, "ACME Corp", "Department of Defense", "Logistics", "2025-04-05"),
        ("C-005", 9_000_000, "ACME Corp", "Department of Defense", "Consulting", "2025-05-01"),
        ("C-006", 3_000_000, "ACME Corp", "Department of Energy", "Solar", "2025-06-01"),
        ("C-007", 2_000_000, "ACME Corp", "Department of Energy", "Wind", "2025-07-01"),
        # Vendor BetaCo has 3 contracts at DOD
        ("C-008", 5_000_000, "BetaCo", "Department of Defense", "Parts", "2025-01-20"),
        ("C-009", 6_000_000, "BetaCo", "Department of Defense", "Repair", "2025-03-15"),
        ("C-010", 7_000_000, "BetaCo", "Department of Defense", "Training", "2025-05-10"),
        # Vendor GammaTech — single contract
        ("C-011", 20_000_000, "GammaTech", "Department of Defense", "Special project", "2025-02-01"),
        # Clean vendor
        ("C-012", 4_000_000, "CleanVendor", "Department of Energy", "Research", "2025-01-01"),
    ]

    for cid, amt, vendor, agency, desc, date in contracts:
        raw_hash = hashlib.sha256(f"{cid}:{amt}".encode()).hexdigest()
        c.execute(
            "INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cid, amt, vendor, agency, desc, date, None, None, raw_hash, "2025-01-01"),
        )

    # contracts_clean with extent_competed info
    c.execute(
        "INSERT INTO contracts_clean VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("C-001", 10_000_000, "ACME Corp", "Department of Defense", "Equipment",
         "2025-01-15", None, None, 3, "FULL AND OPEN COMPETITION", None),
    )
    c.execute(
        "INSERT INTO contracts_clean VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("C-002", 12_000_000, "ACME Corp", "Department of Defense", "Maintenance",
         "2025-02-20", None, None, 1, "NOT COMPETED", None),
    )
    c.execute(
        "INSERT INTO contracts_clean VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("C-003", 15_000_000, "ACME Corp", "Department of Defense", "IT Services",
         "2025-03-10", None, None, 1, "NOT COMPETED", None),
    )

    # Analysis run
    c.execute(
        """INSERT INTO analysis_runs (run_id, started_at, completed_at, status)
           VALUES (?, '2025-01-01', '2025-01-01', 'COMPLETED')""",
        (run_id,),
    )

    # Scores — ACME has RED and YELLOW flags
    scores = [
        ("s-001", "C-001", run_id, "RED", 15, 85, 0.001, 0.01, 1, 250.0, 230.0, 270.0,
         4.5, 3.8, 95.2, 92.0, 98.0, 0.03, 15.0, 0.72, 50, 0),
        ("s-002", "C-002", run_id, "YELLOW", 120, 60, 0.01, 0.05, 1, 80.0, 70.0, 90.0,
         2.5, 2.1, 82.5, 78.0, 87.0, 0.03, 5.0, 0.45, 50, 0),
        ("s-003", "C-003", run_id, "YELLOW", 130, 55, 0.02, 0.08, 0, 60.0, 50.0, 70.0,
         2.0, 1.8, 75.0, 70.0, 80.0, 0.03, 3.0, 0.40, 50, 0),
        ("s-008", "C-008", run_id, "GREEN", 5000, 10, 0.5, 0.8, 0, 5.0, -10.0, 20.0,
         0.3, 0.2, 30.0, 25.0, 35.0, 0.03, 1.0, 0.05, 50, 0),
        ("s-011", "C-011", run_id, "RED", 10, 92, 0.0001, 0.001, 1, 350.0, 320.0, 380.0,
         5.2, 4.5, 97.5, 95.0, 99.0, 0.03, 20.0, 0.85, 50, 0),
        ("s-012", "C-012", run_id, "GREEN", 5000, 5, 0.6, 0.9, 0, -10.0, -30.0, 10.0,
         -0.5, -0.3, 15.0, 10.0, 20.0, 0.03, 0.5, 0.02, 50, 0),
    ]

    for s in scores:
        c.execute(
            """INSERT INTO contract_scores
               (score_id, contract_id, run_id, fraud_tier, triage_priority, confidence_score,
                raw_pvalue, fdr_adjusted_pvalue, survives_fdr,
                markup_pct, markup_ci_lower, markup_ci_upper,
                raw_zscore, log_zscore,
                bootstrap_percentile, percentile_ci_lower, percentile_ci_upper,
                bayesian_prior, bayesian_likelihood_ratio, bayesian_posterior,
                comparable_count, insufficient_comparables)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            s,
        )

    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


# ===================================================================
# 1. Vendor Intelligence Tests
# ===================================================================

class TestVendorIntelligence:

    def test_basic_profile(self, intel_db):
        """Build a vendor profile and verify fields."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "ACME Corp")
        assert profile.vendor_name == "ACME Corp"
        assert profile.contract_count == 7
        assert profile.total_awards == 59_000_000
        assert profile.average_value == pytest.approx(59_000_000 / 7, rel=0.01)

    def test_agency_concentration(self, intel_db):
        """ACME has 5/7 contracts at DOD — should show high concentration."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "ACME Corp")
        assert profile.top_agency == "Department of Defense"
        # DOD value = 10+12+15+8+9 = 54M out of 59M total
        expected_pct = 54_000_000 / 59_000_000
        assert profile.top_agency_pct == pytest.approx(expected_pct, rel=0.01)
        assert profile.concentration_score > 0.5  # High HHI

    def test_sole_source_rate(self, intel_db):
        """ACME has 2 NOT COMPETED, 1 FULL AND OPEN out of 3 in contracts_clean."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "ACME Corp")
        # 2 sole source / 3 total
        assert profile.sole_source_rate == pytest.approx(2 / 3, rel=0.01)

    def test_flag_history(self, intel_db):
        """ACME has 1 RED + 2 YELLOW flags."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "ACME Corp")
        assert profile.red_count == 1
        assert profile.yellow_count == 2
        assert profile.flagged_contract_count == 3

    def test_risk_score_range(self, intel_db):
        """Risk score should be between 0 and 100."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "ACME Corp")
        assert 0 <= profile.risk_score <= 100

    def test_clean_vendor_low_risk(self, intel_db):
        """A vendor with no flags should have a lower risk score."""
        from vendor_intelligence import build_vendor_profile

        acme = build_vendor_profile(intel_db, "ACME Corp")
        clean = build_vendor_profile(intel_db, "CleanVendor")
        assert clean.risk_score < acme.risk_score

    def test_nonexistent_vendor(self, intel_db):
        """A vendor with no contracts should return zero-ed profile."""
        from vendor_intelligence import build_vendor_profile

        profile = build_vendor_profile(intel_db, "NonExistent Inc")
        assert profile.contract_count == 0
        assert profile.risk_score == 0.0


# ===================================================================
# 2. Case Builder Tests
# ===================================================================

class TestCaseBuilder:

    def test_build_package(self, intel_db):
        """Build a case package for a RED-flagged contract."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        assert pkg.contract_id == "C-001"
        assert pkg.fraud_tier == "RED"
        assert pkg.confidence_score == 85
        assert pkg.generated_at != ""

    def test_signals_extracted(self, intel_db):
        """Should extract markup, bootstrap, Bayesian, z-score signals."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        signal_names = [s["signal_name"] for s in pkg.signals]
        assert "Price Markup Anomaly" in signal_names
        assert "Bayesian Fraud Posterior" in signal_names

    def test_peer_stats(self, intel_db):
        """Peer stats should be populated for the contract's agency."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        ps = pkg.peer_stats
        if isinstance(ps, dict):
            assert ps["peer_count"] > 0
            assert ps["agency"] == "Department of Defense"
        else:
            assert ps.peer_count > 0
            assert ps.agency == "Department of Defense"

    def test_vendor_summary(self, intel_db):
        """Vendor summary should be populated."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        assert pkg.vendor_summary["vendor_name"] == "ACME Corp"
        assert pkg.vendor_summary["contract_count"] == 7

    def test_markdown_export(self, intel_db):
        """Markdown rendering should include key sections."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        md = pkg.to_markdown()
        assert "# Case Package: C-001" in md
        assert "## Contract Details" in md
        assert "## Triggered Signals" in md
        assert "## Recommendation" in md
        assert "IMMEDIATE REVIEW" in md  # RED tier recommendation

    def test_json_export(self, intel_db):
        """JSON export should be valid JSON."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-001")
        j = pkg.to_json()
        parsed = json.loads(j)
        assert parsed["contract_id"] == "C-001"
        assert parsed["fraud_tier"] == "RED"

    def test_green_contract_recommendation(self, intel_db):
        """GREEN contracts should get 'no action' recommendation."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "C-012")
        assert "No immediate action" in pkg.recommendation

    def test_nonexistent_contract(self, intel_db):
        """Package for nonexistent contract should have empty metadata."""
        from case_builder import build_case_package

        pkg = build_case_package(intel_db, "NONEXISTENT")
        assert pkg.contract_metadata == {}


# ===================================================================
# 3. Priority Queue Tests
# ===================================================================

class TestPriorityQueue:

    def test_triage_from_list_ordering(self):
        """Higher expected value contracts should rank higher."""
        from priority_queue import triage_from_list

        contracts = [
            {
                "contract_id": "LOW",
                "vendor_name": "V1",
                "agency_name": "DOD",
                "award_amount": 1_000_000,
                "fraud_tier": "YELLOW",
                "confidence_score": 50,
                "bayesian_posterior": 0.3,
                "comparable_count": 20,
                "markup_ci_lower": 50,
                "description": "Small contract",
                "start_date": "2025-01-01",
            },
            {
                "contract_id": "HIGH",
                "vendor_name": "V2",
                "agency_name": "DOD",
                "award_amount": 50_000_000,
                "fraud_tier": "RED",
                "confidence_score": 90,
                "bayesian_posterior": 0.8,
                "comparable_count": 50,
                "markup_ci_lower": 200,
                "description": "Large contract",
                "start_date": "2025-01-01",
            },
        ]

        result = triage_from_list(contracts)
        assert result[0].contract_id == "HIGH"
        assert result[0].rank == 1
        assert result[1].contract_id == "LOW"
        assert result[1].rank == 2

    def test_priority_score_positive(self):
        """All items should have positive priority scores."""
        from priority_queue import triage_from_list

        contracts = [
            {
                "contract_id": "C1",
                "award_amount": 5_000_000,
                "fraud_tier": "YELLOW",
                "bayesian_posterior": 0.4,
                "comparable_count": 15,
            },
        ]

        result = triage_from_list(contracts)
        assert result[0].priority_score > 0

    def test_recommended_actions(self):
        """RED and YELLOW tiers should get different recommended actions."""
        from priority_queue import triage_from_list

        contracts = [
            {"contract_id": "RED-1", "award_amount": 10_000_000,
             "fraud_tier": "RED", "bayesian_posterior": 0.7, "comparable_count": 20},
            {"contract_id": "YEL-1", "award_amount": 10_000_000,
             "fraud_tier": "YELLOW", "bayesian_posterior": 0.4, "comparable_count": 20},
        ]

        result = triage_from_list(contracts)
        red_item = next(r for r in result if r.contract_id == "RED-1")
        yellow_item = next(r for r in result if r.contract_id == "YEL-1")
        assert red_item.recommended_action != yellow_item.recommended_action

    def test_data_completeness(self):
        """Contracts with more data should have higher completeness."""
        from priority_queue import triage_from_list

        complete = {
            "contract_id": "COMPLETE",
            "vendor_name": "V1",
            "agency_name": "DOD",
            "award_amount": 5_000_000,
            "fraud_tier": "RED",
            "bayesian_posterior": 0.7,
            "comparable_count": 20,
            "markup_ci_lower": 100,
            "fdr_adjusted_pvalue": 0.01,
            "bootstrap_percentile": 95,
            "description": "Full data",
            "start_date": "2025-01-01",
        }
        sparse = {
            "contract_id": "SPARSE",
            "award_amount": 5_000_000,
            "fraud_tier": "RED",
            "bayesian_posterior": 0.7,
        }

        result = triage_from_list([complete, sparse])
        complete_item = next(r for r in result if r.contract_id == "COMPLETE")
        sparse_item = next(r for r in result if r.contract_id == "SPARSE")
        assert complete_item.data_completeness > sparse_item.data_completeness

    def test_complexity_estimate(self):
        """Large defense contracts should be high complexity."""
        from priority_queue import triage_from_list

        contracts = [
            {
                "contract_id": "BIG-DOD",
                "agency_name": "Department of Defense",
                "award_amount": 100_000_000,
                "fraud_tier": "RED",
                "bayesian_posterior": 0.8,
                "comparable_count": 20,
            },
        ]

        result = triage_from_list(contracts)
        assert result[0].complexity_estimate == "high"

    def test_build_triage_queue_from_db(self, intel_db):
        """Build queue from database — should return flagged contracts ordered."""
        from priority_queue import build_triage_queue

        queue = build_triage_queue(intel_db)
        assert len(queue) >= 2  # At least the RED and YELLOW contracts
        # First item should be highest priority
        assert queue[0].rank == 1
        # All items should be RED or YELLOW
        for item in queue:
            assert item.fraud_tier in ("RED", "YELLOW")


# ===================================================================
# 4. OCDS Adapter Tests
# ===================================================================

class TestOCDSAdapter:

    def test_award_release(self):
        """Transform an OCDS award release into SUNLIGHT contracts."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-abc-001",
            "tag": ["award"],
            "buyer": {"name": "Ministry of Transport"},
            "awards": [
                {
                    "id": "award-1",
                    "value": {"amount": 5000000, "currency": "USD"},
                    "suppliers": [{"name": "Constructor SA"}],
                    "description": "Road construction project",
                    "date": "2025-06-15",
                }
            ],
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        c = contracts[0]
        assert c.vendor_name == "Constructor SA"
        assert c.agency_name == "Ministry of Transport"
        assert c.award_amount == 5_000_000
        assert c.ocds_tag == "award"
        assert c.start_date == "2025-06-15"

    def test_tender_release(self):
        """Transform an OCDS tender release."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-abc-002",
            "tag": ["tender"],
            "buyer": {"name": "Department of Health"},
            "tender": {
                "value": {"amount": 2000000, "currency": "EUR"},
                "description": "Medical equipment supply",
                "procurementMethod": "open",
                "numberOfTenderers": 5,
                "tenderPeriod": {
                    "startDate": "2025-01-01",
                    "endDate": "2025-02-15",
                },
            },
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        c = contracts[0]
        assert c.agency_name == "Department of Health"
        assert c.award_amount == 2_000_000
        assert c.num_offers == 5
        assert c.extent_competed == "FULL AND OPEN COMPETITION"
        assert c.procurement_method == "open"

    def test_contract_release_with_amendments(self):
        """Transform a contract release with amendments."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-abc-003",
            "tag": ["contract"],
            "buyer": {"name": "City Council"},
            "awards": [
                {
                    "id": "a1",
                    "suppliers": [{"name": "Builder LLC"}],
                }
            ],
            "contracts": [
                {
                    "id": "c1",
                    "awardID": "a1",
                    "value": {"amount": 10000000, "currency": "USD"},
                    "description": "Bridge construction",
                    "period": {"startDate": "2025-03-01", "endDate": "2026-03-01"},
                    "amendments": [
                        {
                            "date": "2025-06-01",
                            "description": "Scope change",
                            "value": {"amount": 500000},
                        }
                    ],
                }
            ],
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        c = contracts[0]
        assert c.vendor_name == "Builder LLC"
        assert c.award_amount == 10_000_000
        assert c.start_date == "2025-03-01"
        assert c.end_date == "2026-03-01"
        assert len(c.amendments) == 1

    def test_planning_release(self):
        """Planning releases produce contracts with warnings."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-abc-004",
            "tag": ["planning"],
            "buyer": {"name": "Treasury"},
            "planning": {
                "budget": {
                    "amount": {"amount": 1000000, "currency": "USD"},
                    "description": "Annual office supplies budget",
                },
            },
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        c = contracts[0]
        assert c.ocds_tag == "planning"
        assert any("Planning" in w for w in c.validation_warnings)

    def test_multiple_releases(self):
        """transform_releases handles a batch with validation."""
        from ocds_adapter import transform_releases

        releases = [
            {
                "ocid": "ocds-1",
                "tag": ["award"],
                "buyer": {"name": "Agency A"},
                "awards": [
                    {"id": "a1", "value": {"amount": 100000}, "suppliers": [{"name": "V1"}]},
                ],
            },
            {
                "ocid": "ocds-2",
                "tag": ["award"],
                "buyer": {"name": "Agency B"},
                "awards": [
                    {"id": "a2", "value": {"amount": 0}, "suppliers": [{"name": "V2"}]},
                ],
            },
        ]

        # With validation — should filter out zero-amount
        valid = transform_releases(releases, validate=True)
        assert len(valid) == 1
        assert valid[0].vendor_name == "V1"

        # Without validation — keep all
        all_contracts = transform_releases(releases, validate=False)
        assert len(all_contracts) == 2

    def test_missing_fields_graceful(self):
        """Adapter should handle missing fields without crashing."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-empty",
            "tag": ["award"],
            "awards": [
                {
                    "id": "a1",
                    "value": {"amount": 500000},
                    # no suppliers, no buyer, no description
                }
            ],
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        c = contracts[0]
        assert c.vendor_name == ""  # Missing but not crashing
        assert c.agency_name == ""
        assert c.award_amount == 500_000

    def test_implementation_release(self):
        """Implementation releases extract transaction totals."""
        from ocds_adapter import transform_release

        release = {
            "ocid": "ocds-impl",
            "tag": ["implementation"],
            "buyer": {"name": "Agency X"},
            "contracts": [
                {
                    "id": "c1",
                    "value": {"amount": 1000000},
                    "implementation": {
                        "transactions": [
                            {"value": {"amount": 300000}},
                            {"value": {"amount": 400000}},
                        ]
                    },
                }
            ],
        }

        contracts = transform_release(release)
        assert len(contracts) == 1
        assert contracts[0].award_amount == 1_000_000  # Uses contract value

    def test_record_transformation(self):
        """Transform an OCDS record (compiled release)."""
        from ocds_adapter import transform_record

        record = {
            "compiledRelease": {
                "ocid": "ocds-rec-1",
                "tag": ["award"],
                "buyer": {"name": "National Agency"},
                "awards": [
                    {"id": "a1", "value": {"amount": 750000}, "suppliers": [{"name": "CompanyX"}]},
                ],
            }
        }

        contracts = transform_record(record)
        assert len(contracts) == 1
        assert contracts[0].vendor_name == "CompanyX"


# ===================================================================
# 5. API v2 Routes Tests
# ===================================================================

class TestAPIV2Routes:

    @pytest.fixture
    def api_client(self, intel_db, monkeypatch):
        """Create a TestClient for the v2 routes."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import api_v2_routes

        monkeypatch.setattr(api_v2_routes, 'DB_PATH', intel_db)

        app = FastAPI()
        app.include_router(api_v2_routes.router)
        return TestClient(app)

    def test_analyze_endpoint(self, api_client):
        """POST /v2/analyze should accept contracts and return job_id."""
        response = api_client.post(
            "/v2/analyze",
            json={
                "contracts": [
                    {
                        "contract_id": "NEW-001",
                        "award_amount": 5000000,
                        "vendor_name": "TestVendor",
                        "agency_name": "TestAgency",
                        "description": "Test contract",
                    }
                ],
                "calibration_profile": "doj_federal",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["contract_count"] == 1

    def test_results_endpoint_not_found(self, api_client):
        """GET /v2/results/{job_id} should 404 for nonexistent jobs."""
        response = api_client.get("/v2/results/nonexistent-job")
        assert response.status_code == 404

    def test_results_endpoint_existing_job(self, api_client):
        """GET /v2/results/{job_id} should return status for existing runs."""
        response = api_client.get("/v2/results/test-run-001")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "COMPLETED"
        assert data["result"] is not None

    def test_vendor_profile_endpoint(self, api_client):
        """GET /v2/vendor/{vendor_id}/profile should return vendor profile."""
        response = api_client.get("/v2/vendor/ACME Corp/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["vendor_name"] == "ACME Corp"
        assert data["contract_count"] == 7
        assert 0 <= data["risk_score"] <= 100

    def test_vendor_profile_not_found(self, api_client):
        """GET /v2/vendor/{vendor_id}/profile should 404 for unknown vendors."""
        response = api_client.get("/v2/vendor/NonExistent/profile")
        assert response.status_code == 404

    def test_case_package_endpoint(self, api_client):
        """GET /v2/case/{contract_id}/package should return evidence package."""
        response = api_client.get("/v2/case/C-001/package")
        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "C-001"
        assert data["fraud_tier"] == "RED"
        assert len(data["signals"]) > 0
        assert "markdown" in data
        assert "# Case Package: C-001" in data["markdown"]

    def test_case_package_not_found(self, api_client):
        """GET /v2/case/{contract_id}/package should 404 for unknown contracts."""
        response = api_client.get("/v2/case/NONEXISTENT/package")
        assert response.status_code == 404

    def test_triage_endpoint(self, api_client):
        """POST /v2/triage should return prioritized list."""
        response = api_client.post(
            "/v2/triage",
            json={
                "contracts": [
                    {
                        "contract_id": "T-001",
                        "vendor_name": "V1",
                        "agency_name": "DOD",
                        "award_amount": 50000000,
                        "fraud_tier": "RED",
                        "confidence_score": 90,
                        "bayesian_posterior": 0.8,
                        "comparable_count": 30,
                    },
                    {
                        "contract_id": "T-002",
                        "vendor_name": "V2",
                        "agency_name": "DOE",
                        "award_amount": 1000000,
                        "fraud_tier": "YELLOW",
                        "confidence_score": 50,
                        "bayesian_posterior": 0.3,
                        "comparable_count": 20,
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert data["items"][0]["rank"] == 1
        # Higher value RED contract should rank first
        assert data["items"][0]["contract_id"] == "T-001"

    def test_triage_validation(self, api_client):
        """POST /v2/triage should reject empty contract list."""
        response = api_client.post("/v2/triage", json={"contracts": []})
        assert response.status_code == 422  # Pydantic validation error

    def test_analyze_batch(self, api_client):
        """POST /v2/analyze should handle multiple contracts."""
        contracts = [
            {
                "contract_id": f"BATCH-{i:03d}",
                "award_amount": 1_000_000 * (i + 1),
                "vendor_name": f"Vendor_{i}",
                "agency_name": "TestAgency",
            }
            for i in range(5)
        ]
        response = api_client.post(
            "/v2/analyze",
            json={"contracts": contracts},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["contract_count"] == 5


# ===================================================================
# 6. Process Indicators Tests (bonus — covers process_indicators.py)
# ===================================================================

class TestProcessIndicators:

    def test_compressed_timeline(self):
        """Short bidding window should trigger red flag."""
        from process_indicators import check_compressed_timeline

        flag = check_compressed_timeline("2025-01-01", "2025-01-05", "goods")
        assert flag is not None
        assert flag.indicator == "compressed_timeline"
        assert flag.severity in ("high", "critical")

    def test_normal_timeline(self):
        """Adequate bidding window should not trigger."""
        from process_indicators import check_compressed_timeline

        flag = check_compressed_timeline("2025-01-01", "2025-02-15", "goods")
        assert flag is None

    def test_invalid_timeline(self):
        """Deadline before announcement should trigger critical flag."""
        from process_indicators import check_compressed_timeline

        flag = check_compressed_timeline("2025-02-01", "2025-01-01")
        assert flag is not None
        assert flag.indicator == "invalid_timeline"
        assert flag.severity == "critical"

    def test_declining_bidders(self):
        """Downward trend in bidder counts should trigger."""
        from process_indicators import check_bidder_trend

        counts = [("Q1", 10), ("Q2", 8), ("Q3", 5), ("Q4", 3)]
        flag = check_bidder_trend(counts)
        assert flag is not None
        assert flag.indicator == "declining_bidders"

    def test_stable_bidders(self):
        """Stable bidder counts should not trigger."""
        from process_indicators import check_bidder_trend

        counts = [("Q1", 10), ("Q2", 11), ("Q3", 10), ("Q4", 12)]
        flag = check_bidder_trend(counts)
        assert flag is None

    def test_excessive_amendments(self):
        """Many amendments with large value change should trigger."""
        from process_indicators import check_amendment_frequency

        amendments = [
            {"amount_change": 500_000, "date": "2025-03-01", "description": "Change 1"},
            {"amount_change": 800_000, "date": "2025-04-01", "description": "Change 2"},
            {"amount_change": 300_000, "date": "2025-05-01", "description": "Change 3"},
            {"amount_change": 400_000, "date": "2025-06-01", "description": "Change 4"},
        ]
        flag = check_amendment_frequency(5_000_000, amendments)
        assert flag is not None
        assert flag.indicator == "excessive_amendments"

    def test_tailored_specs(self):
        """Specs with vendor-specific language should trigger."""
        from process_indicators import check_tailored_specs

        spec = (
            "System must be compatible only with AcmeCorp model XR-9000. "
            "Only AcmeCorp produces this proprietary technology. "
            "Part number ACM-2025-SPEC required."
        )
        flag = check_tailored_specs(spec, vendor_name="AcmeCorp")
        assert flag is not None
        assert flag.indicator == "tailored_specifications"
        assert flag.score > 0

    def test_generic_specs(self):
        """Generic specs should not trigger."""
        from process_indicators import check_tailored_specs

        spec = "The system shall provide secure file storage with 99.9% uptime."
        flag = check_tailored_specs(spec)
        assert flag is None

    def test_composite_analysis(self):
        """Full process analysis should aggregate multiple flags."""
        from process_indicators import analyze_process

        result = analyze_process(
            contract_id="TEST-001",
            announcement_date="2025-01-01",
            deadline_date="2025-01-03",
            procurement_type="services",
            specification_text="Must use proprietary PatentCorp model Z-100 only.",
            vendor_name="PatentCorp",
        )
        assert result.flag_count >= 1  # At least compressed timeline
        assert result.composite_score > 0
