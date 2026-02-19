"""
SUNLIGHT Multi-Tenant Isolation Tests
=======================================

Tests that cross-tenant reads/writes are impossible.
Tests that every tenant-scoped table has tenant_id.
Tests tenant rate limiting and RBAC enforcement.
"""

import os
import sys
import json
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from tenancy import (
    init_tenant_schema, create_tenant, get_tenant, list_tenants,
    update_tenant, create_tenant_user, list_tenant_users,
    seed_demo_tenant, check_tenant_rate_limit,
    scoped_query, tenant_db_session,
)
from jobs import init_jobs_schema, create_job, get_job, list_jobs
from webhooks import init_webhooks_schema, create_webhook_event, get_delivery_logs
from rbac import (
    has_permission, require_permission, require_role,
    get_role_from_key, ROLE_PERMISSIONS,
)


@pytest.fixture
def db_path():
    """Create a temp database with all schemas."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE contracts (
            contract_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            award_amount REAL,
            vendor_name TEXT,
            agency_name TEXT,
            description TEXT DEFAULT '',
            raw_data_hash TEXT,
            created_at TEXT
        );
        CREATE TABLE contract_scores (
            score_id TEXT PRIMARY KEY,
            contract_id TEXT,
            tenant_id TEXT,
            run_id TEXT,
            tier TEXT,
            triage_priority INTEGER,
            markup_pct REAL,
            bayesian_posterior REAL,
            scored_at TEXT
        );
        CREATE TABLE analysis_runs (
            run_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            started_at TEXT,
            status TEXT DEFAULT 'RUNNING',
            run_seed INTEGER,
            config_json TEXT DEFAULT '{}',
            config_hash TEXT,
            dataset_hash TEXT,
            n_contracts INTEGER
        );
        CREATE TABLE audit_log (
            log_id TEXT PRIMARY KEY,
            tenant_id TEXT,
            sequence_number INTEGER,
            timestamp TEXT,
            action TEXT,
            run_id TEXT,
            details TEXT,
            previous_hash TEXT,
            entry_hash TEXT,
            action_type TEXT,
            entity_id TEXT,
            previous_log_hash TEXT,
            current_log_hash TEXT
        );
    """)
    conn.commit()
    conn.close()

    init_tenant_schema(path)
    init_jobs_schema(path)
    init_webhooks_schema(path)

    yield path
    os.unlink(path)


@pytest.fixture
def two_tenants(db_path):
    """Create two tenants for isolation testing."""
    t1 = create_tenant(db_path, "Tenant Alpha", "alpha")
    t2 = create_tenant(db_path, "Tenant Beta", "beta")
    return t1, t2


# ─── Tenant CRUD ─────────────────────────────────────────────────────────

class TestTenantCRUD:
    def test_create_tenant(self, db_path):
        t = create_tenant(db_path, "World Bank INT", "wb-int", tier="enterprise")
        assert t["name"] == "World Bank INT"
        assert t["slug"] == "wb-int"
        assert t["tier"] == "enterprise"
        assert t["tenant_id"].startswith("ten_")
        assert t["webhook_secret"].startswith("whsec_")

    def test_duplicate_slug_fails(self, db_path):
        create_tenant(db_path, "First", "unique-slug")
        with pytest.raises(ValueError, match="already exists"):
            create_tenant(db_path, "Second", "unique-slug")

    def test_get_tenant(self, db_path):
        created = create_tenant(db_path, "IMF", "imf")
        loaded = get_tenant(db_path, created["tenant_id"])
        assert loaded is not None
        assert loaded["name"] == "IMF"

    def test_list_tenants(self, db_path, two_tenants):
        tenants = list_tenants(db_path)
        names = {t["name"] for t in tenants}
        assert "Tenant Alpha" in names
        assert "Tenant Beta" in names

    def test_update_tenant(self, db_path, two_tenants):
        t1, _ = two_tenants
        updated = update_tenant(db_path, t1["tenant_id"], {"webhook_url": "https://example.com/hook"})
        assert updated is True
        t = get_tenant(db_path, t1["tenant_id"])
        assert t["webhook_url"] == "https://example.com/hook"

    def test_seed_demo_tenant(self, db_path):
        demo = seed_demo_tenant(db_path)
        assert demo["tenant_id"] == "ten_demo"
        # Idempotent
        demo2 = seed_demo_tenant(db_path)
        assert demo2["tenant_id"] == "ten_demo"


# ─── Cross-Tenant Isolation ──────────────────────────────────────────────

class TestCrossTenantIsolation:
    """
    CRITICAL: These tests verify that tenant A cannot see tenant B's data.
    If any of these fail, multi-tenancy is broken.
    """

    def test_jobs_isolated_between_tenants(self, db_path, two_tenants):
        t1, t2 = two_tenants
        # Create jobs for each tenant
        job1 = create_job(db_path, t1["tenant_id"], input_data={"test": "alpha"})
        job2 = create_job(db_path, t2["tenant_id"], input_data={"test": "beta"})

        # Tenant 1 should only see their jobs
        t1_jobs = list_jobs(db_path, t1["tenant_id"])
        t1_job_ids = {j["job_id"] for j in t1_jobs}
        assert job1["job_id"] in t1_job_ids
        assert job2["job_id"] not in t1_job_ids

        # Tenant 2 should only see their jobs
        t2_jobs = list_jobs(db_path, t2["tenant_id"])
        t2_job_ids = {j["job_id"] for j in t2_jobs}
        assert job2["job_id"] in t2_job_ids
        assert job1["job_id"] not in t2_job_ids

    def test_job_get_with_wrong_tenant_returns_none(self, db_path, two_tenants):
        t1, t2 = two_tenants
        job = create_job(db_path, t1["tenant_id"])

        # Correct tenant can see it
        assert get_job(db_path, job["job_id"], tenant_id=t1["tenant_id"]) is not None

        # Wrong tenant cannot
        assert get_job(db_path, job["job_id"], tenant_id=t2["tenant_id"]) is None

    def test_webhook_logs_isolated(self, db_path, two_tenants):
        t1, t2 = two_tenants
        create_webhook_event(db_path, t1["tenant_id"], "scan.completed",
                             {"job_id": "j1"}, "https://t1.example.com/hook")
        create_webhook_event(db_path, t2["tenant_id"], "scan.completed",
                             {"job_id": "j2"}, "https://t2.example.com/hook")

        t1_logs = get_delivery_logs(db_path, t1["tenant_id"])
        t2_logs = get_delivery_logs(db_path, t2["tenant_id"])

        assert len(t1_logs) == 1
        assert len(t2_logs) == 1
        assert t1_logs[0]["tenant_id"] != t2_logs[0]["tenant_id"]

    def test_scoped_query_adds_tenant_filter(self, db_path, two_tenants):
        t1, _ = two_tenants
        q, p = scoped_query("SELECT * FROM contracts", t1["tenant_id"])
        assert "tenant_id = ?" in q
        assert t1["tenant_id"] in p

    def test_scoped_query_with_existing_where(self, db_path, two_tenants):
        t1, _ = two_tenants
        q, p = scoped_query(
            "SELECT * FROM contracts WHERE tier = ?",
            t1["tenant_id"],
            ("RED",),
        )
        assert "AND tenant_id = ?" in q
        assert p == ("RED", t1["tenant_id"])

    def test_contracts_cross_tenant_read_fails(self, db_path, two_tenants):
        """Insert a contract for tenant A, verify tenant B can't read it via scoped query."""
        t1, t2 = two_tenants
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO contracts (contract_id, tenant_id, award_amount, vendor_name, agency_name) VALUES (?,?,?,?,?)",
            ("C001", t1["tenant_id"], 1000000, "Vendor A", "Agency A"),
        )
        conn.commit()

        # Tenant A sees it
        q, p = scoped_query("SELECT * FROM contracts", t1["tenant_id"])
        rows = conn.execute(q, p).fetchall()
        assert len(rows) == 1

        # Tenant B does NOT
        q, p = scoped_query("SELECT * FROM contracts", t2["tenant_id"])
        rows = conn.execute(q, p).fetchall()
        assert len(rows) == 0

        conn.close()

    def test_scores_cross_tenant_read_fails(self, db_path, two_tenants):
        """Insert scores for tenant A, verify tenant B can't read them."""
        t1, t2 = two_tenants
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO contract_scores (score_id, contract_id, tenant_id, run_id, tier) VALUES (?,?,?,?,?)",
            ("S001", "C001", t1["tenant_id"], "run_001", "RED"),
        )
        conn.commit()

        q, p = scoped_query("SELECT * FROM contract_scores", t2["tenant_id"])
        rows = conn.execute(q, p).fetchall()
        assert len(rows) == 0

        conn.close()


# ─── Tenant Users ─────────────────────────────────────────────────────────

class TestTenantUsers:
    def test_create_user(self, db_path, two_tenants):
        t1, _ = two_tenants
        user = create_tenant_user(db_path, t1["tenant_id"], "analyst@wb.org", "analyst")
        assert user["role"] == "analyst"
        assert user["user_id"].startswith("usr_")

    def test_duplicate_user_fails(self, db_path, two_tenants):
        t1, _ = two_tenants
        create_tenant_user(db_path, t1["tenant_id"], "test@wb.org")
        with pytest.raises(ValueError, match="already exists"):
            create_tenant_user(db_path, t1["tenant_id"], "test@wb.org")

    def test_invalid_role_fails(self, db_path, two_tenants):
        t1, _ = two_tenants
        with pytest.raises(ValueError, match="Invalid role"):
            create_tenant_user(db_path, t1["tenant_id"], "x@wb.org", "superadmin")

    def test_users_scoped_to_tenant(self, db_path, two_tenants):
        t1, t2 = two_tenants
        create_tenant_user(db_path, t1["tenant_id"], "a@t1.org")
        create_tenant_user(db_path, t2["tenant_id"], "b@t2.org")

        t1_users = list_tenant_users(db_path, t1["tenant_id"])
        t2_users = list_tenant_users(db_path, t2["tenant_id"])
        assert len(t1_users) == 1
        assert t1_users[0]["email"] == "a@t1.org"
        assert len(t2_users) == 1
        assert t2_users[0]["email"] == "b@t2.org"


# ─── RBAC ─────────────────────────────────────────────────────────────────

class TestRBAC:
    def test_viewer_permissions(self):
        assert has_permission("viewer", "scores:read")
        assert has_permission("viewer", "dashboard:read")
        assert not has_permission("viewer", "scan:submit")
        assert not has_permission("viewer", "users:manage")

    def test_analyst_permissions(self):
        assert has_permission("analyst", "scores:read")
        assert has_permission("analyst", "scan:submit")
        assert has_permission("analyst", "reports:export")
        assert not has_permission("analyst", "users:manage")
        assert not has_permission("analyst", "tenants:manage")

    def test_admin_has_all_permissions(self):
        assert has_permission("admin", "scores:read")
        assert has_permission("admin", "scan:submit")
        assert has_permission("admin", "users:manage")
        assert has_permission("admin", "tenants:manage")
        assert has_permission("admin", "settings:manage")

    def test_require_permission_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            require_permission("viewer", "scan:submit")
        assert exc.value.status_code == 403

    def test_require_role_hierarchy(self):
        from fastapi import HTTPException
        checker = require_role("admin")
        # Admin passes
        checker("admin")
        # Analyst fails
        with pytest.raises(HTTPException):
            checker("analyst")

    def test_role_from_key(self):
        assert get_role_from_key({"scopes": "read,analyze,admin"}) == "admin"
        assert get_role_from_key({"scopes": "read,analyze"}) == "analyst"
        assert get_role_from_key({"scopes": "read"}) == "viewer"


# ─── Rate Limiting ────────────────────────────────────────────────────────

class TestTenantRateLimiting:
    def test_rate_limit_allows_within_limit(self, db_path, two_tenants):
        t1, _ = two_tenants
        tenant = get_tenant(db_path, t1["tenant_id"])
        for _ in range(10):
            assert check_tenant_rate_limit(tenant) is True

    def test_rate_limit_blocks_over_limit(self, db_path):
        t = create_tenant(db_path, "Limited", "limited")
        update_tenant(db_path, t["tenant_id"], {"rate_limit_rpm": 3})
        tenant = get_tenant(db_path, t["tenant_id"])

        assert check_tenant_rate_limit(tenant) is True
        assert check_tenant_rate_limit(tenant) is True
        assert check_tenant_rate_limit(tenant) is True
        assert check_tenant_rate_limit(tenant) is False  # Over limit


# ─── Table Audit ──────────────────────────────────────────────────────────

class TestTenantIdPresence:
    """Regression: ensure every tenant-scoped table has tenant_id column."""

    TENANT_SCOPED_TABLES = [
        "scan_jobs",
        "dead_letter_queue",
        "webhook_deliveries",
    ]

    def test_all_tenant_tables_have_tenant_id(self, db_path):
        conn = sqlite3.connect(db_path)
        for table in self.TENANT_SCOPED_TABLES:
            cols = [
                row[1] for row in
                conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
            assert "tenant_id" in cols, \
                f"Table '{table}' missing tenant_id column"
        conn.close()
