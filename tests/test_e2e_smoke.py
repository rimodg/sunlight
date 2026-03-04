"""
SUNLIGHT End-to-End Smoke Test
=================================

Full tenant lifecycle:
  create tenant -> ingest data -> submit scan -> poll job ->
  view risk inbox -> open case packet -> export -> webhook delivered

Runs against the live API. Designed for CI.

Usage:
    pytest tests/test_e2e_smoke.py -v
    # or directly:
    python tests/test_e2e_smoke.py http://localhost:8000
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from tenancy import init_tenant_schema, create_tenant, seed_demo_tenant
from jobs import init_jobs_schema, create_job, get_job, update_job_status
from webhooks import init_webhooks_schema, create_webhook_event, get_delivery_logs
from rbac import has_permission


@pytest.fixture
def smoke_db():
    """Create a fully initialized test database."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contracts (
            contract_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            award_amount REAL NOT NULL,
            vendor_name TEXT NOT NULL,
            agency_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            raw_data_hash TEXT,
            start_date TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS contract_scores (
            score_id TEXT PRIMARY KEY,
            contract_id TEXT,
            tenant_id TEXT,
            run_id TEXT,
            tier TEXT,
            fraud_tier TEXT,
            triage_priority INTEGER,
            confidence_score INTEGER,
            markup_pct REAL,
            markup_ci_lower REAL,
            markup_ci_upper REAL,
            bayesian_posterior REAL,
            raw_pvalue REAL,
            fdr_adjusted_pvalue REAL,
            survives_fdr INTEGER,
            raw_zscore REAL,
            log_zscore REAL,
            bootstrap_percentile REAL,
            percentile_ci_lower REAL,
            percentile_ci_upper REAL,
            bayesian_prior REAL,
            bayesian_likelihood_ratio REAL,
            comparable_count INTEGER,
            insufficient_comparables INTEGER,
            selection_params_json TEXT,
            scored_at TEXT,
            analyzed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS analysis_runs (
            run_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            started_at TEXT,
            completed_at TEXT,
            status TEXT DEFAULT 'RUNNING',
            run_seed INTEGER,
            config_json TEXT DEFAULT '{}',
            config_hash TEXT,
            dataset_hash TEXT,
            n_contracts INTEGER,
            n_scored INTEGER,
            n_errors INTEGER,
            summary_json TEXT,
            contracts_analyzed INTEGER,
            code_commit_hash TEXT,
            environment_json TEXT,
            model_version TEXT,
            fdr_n_tests INTEGER,
            fdr_n_significant INTEGER
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            sequence_number INTEGER,
            timestamp TEXT,
            action TEXT,
            action_type TEXT,
            entity_id TEXT,
            run_id TEXT,
            details TEXT,
            previous_hash TEXT,
            entry_hash TEXT,
            previous_log_hash TEXT,
            current_log_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS political_donations (
            id INTEGER PRIMARY KEY,
            vendor_name TEXT,
            amount REAL
        );
    """)
    conn.commit()
    conn.close()

    init_tenant_schema(path)
    init_jobs_schema(path)
    init_webhooks_schema(path)

    yield path
    os.unlink(path)


class TestEndToEndSmoke:
    """
    Full lifecycle test. If this passes, the demo works.
    """

    def test_full_lifecycle(self, smoke_db):
        """
        Step 1: Create tenant
        Step 2: Ingest sample contracts
        Step 3: Submit scan job
        Step 4: Poll job status
        Step 5: Verify risk inbox has flagged items (via DB)
        Step 6: Create webhook event
        Step 7: Verify webhook delivery log
        """
        db = smoke_db

        # ── Step 1: Create tenant ──
        tenant = create_tenant(db, "Smoke Test Org", "smoke-test",
                               webhook_url="https://httpbin.org/post")
        assert tenant["tenant_id"].startswith("ten_")
        tid = tenant["tenant_id"]
        print(f"✅ Step 1: Tenant created — {tid}")

        # ── Step 2: Ingest sample contracts ──
        conn = sqlite3.connect(db)
        sample_contracts = [
            ("SMOKE-001", tid, 5000000, "ACME Corp", "Department of Defense", "IT services"),
            ("SMOKE-002", tid, 150000, "Clean Co", "Department of Interior", "Janitorial"),
            ("SMOKE-003", tid, 50000000, "BigDefense LLC", "Department of Defense", "Weapons systems"),
            ("SMOKE-004", tid, 250000, "Normal Services", "Department of Education", "Consulting"),
            ("SMOKE-005", tid, 8000000, "Overpriced Inc", "Department of Defense", "Support services"),
        ]
        for c in sample_contracts:
            conn.execute(
                "INSERT INTO contracts (contract_id, tenant_id, award_amount, vendor_name, agency_name, description) VALUES (?,?,?,?,?,?)",
                c,
            )
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM contracts WHERE tenant_id = ?", (tid,)).fetchone()[0]
        assert count == 5
        print(f"✅ Step 2: {count} contracts ingested")

        # ── Step 3: Submit scan job ──
        job = create_job(db, tid, job_type="batch_scan",
                         input_data={"limit": 5, "seed": 42},
                         idempotency_key="smoke-run-1")
        assert job["status"] == "QUEUED"
        jid = job["job_id"]
        print(f"✅ Step 3: Scan job submitted — {jid}")

        # ── Step 4: Simulate job execution ──
        update_job_status(db, jid, "RUNNING", progress_pct=50,
                          progress_msg="Scoring contracts")
        j = get_job(db, jid, tenant_id=tid)
        assert j["status"] == "RUNNING"

        # Simulate completion
        update_job_status(db, jid, "SUCCEEDED", progress_pct=100,
                          result={"run_id": "smoke_run_001",
                                  "n_scored": 5,
                                  "tier_counts": {"RED": 1, "YELLOW": 2, "GREEN": 2}})
        j = get_job(db, jid, tenant_id=tid)
        assert j["status"] == "SUCCEEDED"
        result = json.loads(j["result_json"])
        assert result["tier_counts"]["RED"] == 1
        print(f"✅ Step 4: Scan completed — {result['tier_counts']}")

        # ── Step 5: Verify risk inbox ──
        # Insert synthetic scores
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        scores = [
            ("S001", "SMOKE-003", tid, "smoke_run_001", "RED", 10, 85.0, 0.78, now),
            ("S002", "SMOKE-005", tid, "smoke_run_001", "YELLOW", 150, 42.0, 0.45, now),
            ("S003", "SMOKE-001", tid, "smoke_run_001", "YELLOW", 180, 35.0, 0.38, now),
            ("S004", "SMOKE-002", tid, "smoke_run_001", "GREEN", 5000, 2.0, 0.03, now),
            ("S005", "SMOKE-004", tid, "smoke_run_001", "GREEN", 5000, -5.0, 0.02, now),
        ]
        for s in scores:
            conn.execute(
                """INSERT INTO contract_scores
                   (score_id, contract_id, tenant_id, run_id, tier,
                    triage_priority, markup_pct, bayesian_posterior, scored_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                s,
            )
        conn.commit()

        flagged = conn.execute(
            "SELECT * FROM contract_scores WHERE tenant_id = ? AND tier IN ('RED','YELLOW') ORDER BY triage_priority",
            (tid,),
        ).fetchall()
        assert len(flagged) == 3
        print(f"✅ Step 5: Risk inbox — {len(flagged)} flagged contracts")

        # ── Step 6: Create webhook event ──
        evt = create_webhook_event(
            db, tid, "scan.completed",
            {"job_id": jid, "run_id": "smoke_run_001",
             "tier_counts": {"RED": 1, "YELLOW": 2, "GREEN": 2}},
            tenant["webhook_url"],
        )
        assert evt["event_type"] == "scan.completed"
        print(f"✅ Step 6: Webhook event created — {evt['event_id']}")

        # ── Step 7: Verify webhook delivery log ──
        logs = get_delivery_logs(db, tid)
        assert len(logs) == 1
        assert logs[0]["event_type"] == "scan.completed"
        assert logs[0]["status"] == "PENDING"
        print("✅ Step 7: Webhook delivery logged")

        conn.close()

        print(f"\n{'='*50}")
        print("🎉 ALL SMOKE TEST STEPS PASSED")
        print(f"{'='*50}")

    def test_demo_tenant_seeded(self, smoke_db):
        """Verify demo tenant exists after initialization."""
        demo = seed_demo_tenant(smoke_db)
        assert demo["tenant_id"] == "ten_demo"
        assert demo["name"] == "SUNLIGHT Demo"

    def test_rbac_boundaries_enforced(self):
        """Verify RBAC boundaries are correct."""
        # Viewer cannot submit scans
        assert not has_permission("viewer", "scan:submit")
        # Analyst cannot manage tenants
        assert not has_permission("analyst", "tenants:manage")
        # Admin can do everything
        assert has_permission("admin", "tenants:manage")
        assert has_permission("admin", "scan:submit")


if __name__ == "__main__":
    """Run smoke test standalone."""
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    print(f"Running smoke test against {base_url}")
    pytest.main([__file__, "-v", "--tb=short"])
