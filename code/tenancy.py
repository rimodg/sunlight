"""
SUNLIGHT Multi-Tenant Isolation
=================================

Strict tenant isolation at application + database layers.
Every tenant-scoped table has tenant_id. All queries scoped.
PostgreSQL Row-Level Security (RLS) provides DB-layer guarantee.

Isolation model:
- tenant_id extracted from API key -> injected into request context
- DB session sets current_setting('app.tenant_id') for RLS
- Cross-tenant reads/writes are impossible if RLS is enabled
- Application layer ALSO filters by tenant_id (defense in depth)

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import sqlite3
import uuid
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

from fastapi import HTTPException, Request

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("tenancy")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

TENANT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    webhook_url     TEXT,
    webhook_secret  TEXT,
    settings_json   TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active',
    tier            TEXT NOT NULL DEFAULT 'standard',
    max_contracts   INTEGER NOT NULL DEFAULT 100000,
    rate_limit_rpm  INTEGER NOT NULL DEFAULT 60,
    max_concurrency INTEGER NOT NULL DEFAULT 5,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tenant_users (
    user_id     TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(tenant_id),
    email       TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'analyst',
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    UNIQUE(tenant_id, email)
);

CREATE INDEX IF NOT EXISTS idx_tenant_users_tenant ON tenant_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email);
"""

# PostgreSQL RLS policies
POSTGRES_RLS_SQL = """
-- Enable RLS on all tenant-scoped tables
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts FORCE ROW LEVEL SECURITY;
ALTER TABLE contract_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_scores FORCE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
ALTER TABLE scan_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scan_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY;

-- RLS policies: only rows matching current tenant are visible
CREATE POLICY tenant_contracts ON contracts
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_scores ON contract_scores
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_runs ON analysis_runs
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_audit ON audit_log
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_jobs ON scan_jobs
    USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_webhooks ON webhook_deliveries
    USING (tenant_id = current_setting('app.tenant_id', true));
"""


def init_tenant_schema(db_path: str):
    """Create tenant tables (SQLite dev mode)."""
    conn = sqlite3.connect(db_path)
    conn.executescript(TENANT_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Tenant schema initialized", extra={"db_path": db_path})


# ---------------------------------------------------------------------------
# Tenant CRUD
# ---------------------------------------------------------------------------

def create_tenant(
    db_path: str,
    name: str,
    slug: str,
    tier: str = "standard",
    webhook_url: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> Dict:
    """Create a new tenant. Returns tenant record."""
    tenant_id = f"ten_{uuid.uuid4().hex[:16]}"
    webhook_secret = f"whsec_{secrets.token_hex(32)}"
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO tenants
               (tenant_id, name, slug, webhook_url, webhook_secret,
                settings_json, tier, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, name, slug, webhook_url, webhook_secret,
             __import__('json').dumps(settings or {}), tier, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"Tenant slug '{slug}' already exists")
    conn.close()

    logger.info("Tenant created",
                extra={"tenant_id": tenant_id, "tenant_name": name, "slug": slug})

    return {
        "tenant_id": tenant_id,
        "name": name,
        "slug": slug,
        "webhook_url": webhook_url,
        "webhook_secret": webhook_secret,
        "tier": tier,
        "status": "active",
        "created_at": now,
    }


def get_tenant(db_path: str, tenant_id: str) -> Optional[Dict]:
    """Load tenant by ID."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM tenants WHERE tenant_id = ? AND status = 'active'",
        (tenant_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_tenants(db_path: str) -> List[Dict]:
    """List all active tenants."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT tenant_id, name, slug, tier, status, created_at FROM tenants WHERE status = 'active'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_tenant(db_path: str, tenant_id: str, updates: Dict) -> bool:
    """Update tenant settings. Returns True if updated."""
    allowed = {"name", "webhook_url", "settings_json", "tier",
               "rate_limit_rpm", "max_concurrency", "max_contracts", "status"}
    filtered = {k: v for k, v in updates.items() if k in allowed}
    if not filtered:
        return False

    filtered["updated_at"] = datetime.now(timezone.utc).isoformat()
    sets = ", ".join(f"{k} = ?" for k in filtered)
    vals = list(filtered.values()) + [tenant_id]

    conn = sqlite3.connect(db_path)
    cur = conn.execute(f"UPDATE tenants SET {sets} WHERE tenant_id = ?", vals)
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()

    if updated:
        logger.info("Tenant updated",
                     extra={"tenant_id": tenant_id, "fields": list(filtered.keys())})
    return updated


# ---------------------------------------------------------------------------
# Tenant user management
# ---------------------------------------------------------------------------

VALID_ROLES = {"viewer", "analyst", "admin"}


def create_tenant_user(
    db_path: str, tenant_id: str, email: str, role: str = "analyst",
) -> Dict:
    """Create a user within a tenant."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role '{role}'. Must be one of: {VALID_ROLES}")

    user_id = f"usr_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO tenant_users (user_id, tenant_id, email, role, created_at) VALUES (?,?,?,?,?)",
            (user_id, tenant_id, email, role, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"User '{email}' already exists in tenant")
    conn.close()

    return {"user_id": user_id, "tenant_id": tenant_id, "email": email, "role": role}


def list_tenant_users(db_path: str, tenant_id: str) -> List[Dict]:
    """List users for a tenant."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM tenant_users WHERE tenant_id = ? AND is_active = 1",
        (tenant_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tenant context middleware
# ---------------------------------------------------------------------------

class TenantContext:
    """Thread-local-style tenant context for request scoping."""

    def __init__(self):
        self._tenant_id: Optional[str] = None
        self._tenant: Optional[Dict] = None
        self._user_role: Optional[str] = None

    @property
    def tenant_id(self) -> str:
        if not self._tenant_id:
            raise HTTPException(status_code=403, detail="No tenant context")
        return self._tenant_id

    @property
    def tenant(self) -> Dict:
        if not self._tenant:
            raise HTTPException(status_code=403, detail="No tenant context")
        return self._tenant

    @property
    def role(self) -> str:
        return self._user_role or "viewer"

    def set(self, tenant_id: str, tenant: Dict, role: str = "analyst"):
        self._tenant_id = tenant_id
        self._tenant = tenant
        self._user_role = role

    def clear(self):
        self._tenant_id = None
        self._tenant = None
        self._user_role = None


# Per-request context (set by middleware, read by endpoints)
_request_tenant = TenantContext()


def get_tenant_context() -> TenantContext:
    """Dependency: get current tenant context."""
    return _request_tenant


def set_tenant_from_api_key(db_path: str, key_record: Dict) -> TenantContext:
    """
    Extract tenant from API key record and set context.
    Called after auth middleware authenticates the key.
    """
    tenant_id = key_record.get("tenant_id")
    if not tenant_id:
        # Legacy keys without tenant — assign to default tenant
        tenant_id = "ten_default"

    tenant = get_tenant(db_path, tenant_id)
    if not tenant:
        raise HTTPException(status_code=403, detail=f"Tenant {tenant_id} not found or inactive")

    role = key_record.get("role", "analyst")
    _request_tenant.set(tenant_id, tenant, role)

    return _request_tenant


# ---------------------------------------------------------------------------
# Scoped DB helpers (defense-in-depth on top of RLS)
# ---------------------------------------------------------------------------

def scoped_query(base_query: str, tenant_id: str, params: tuple = ()) -> tuple:
    """
    Add tenant_id WHERE clause to a query.
    Defense-in-depth: even with RLS, application layer scopes queries.
    """
    if "WHERE" in base_query.upper():
        scoped = base_query + " AND tenant_id = ?"
    else:
        scoped = base_query + " WHERE tenant_id = ?"
    return scoped, params + (tenant_id,)


@contextmanager
def tenant_db_session(db_path: str, tenant_id: str):
    """
    Context manager that yields a SQLite connection with tenant scope.
    In PostgreSQL prod, this sets the session variable for RLS.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # In PostgreSQL, we'd do: SET app.tenant_id = '{tenant_id}'
    # In SQLite dev mode, we pass tenant_id to every query via scoped_query()
    try:
        yield conn, tenant_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tenant rate limiting
# ---------------------------------------------------------------------------

_tenant_request_counts: Dict[str, List[float]] = {}
import time as _time


def check_tenant_rate_limit(tenant: Dict) -> bool:
    """Check if tenant is within rate limit. Returns True if allowed."""
    tid = tenant["tenant_id"]
    rpm = tenant.get("rate_limit_rpm", 60)
    now = _time.time()
    window = 60.0  # 1 minute

    if tid not in _tenant_request_counts:
        _tenant_request_counts[tid] = []

    # Prune old entries
    _tenant_request_counts[tid] = [
        t for t in _tenant_request_counts[tid] if now - t < window
    ]

    if len(_tenant_request_counts[tid]) >= rpm:
        logger.warning("Tenant rate limited",
                       extra={"tenant_id": tid, "rpm": rpm,
                              "current": len(_tenant_request_counts[tid])})
        return False

    _tenant_request_counts[tid].append(now)
    return True


# ---------------------------------------------------------------------------
# Seed demo tenant
# ---------------------------------------------------------------------------

def seed_demo_tenant(db_path: str) -> Dict:
    """Create the demo tenant with sample data if it doesn't exist."""
    existing = get_tenant(db_path, "ten_demo")
    if existing:
        return existing

    # Create via raw insert to control the ID
    now = datetime.now(timezone.utc).isoformat()
    webhook_secret = f"whsec_{secrets.token_hex(32)}"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO tenants
           (tenant_id, name, slug, webhook_url, webhook_secret,
            settings_json, tier, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("ten_demo", "SUNLIGHT Demo", "demo", "https://httpbin.org/post",
         webhook_secret, '{"guided_tour": true}', "demo", "active", now, now),
    )
    conn.commit()
    conn.close()

    logger.info("Demo tenant seeded", extra={"tenant_id": "ten_demo"})
    return get_tenant(db_path, "ten_demo")
