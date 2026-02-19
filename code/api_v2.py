"""
SUNLIGHT API v2 Extensions
============================

Extends the existing FastAPI application with:
- Multi-tenant middleware
- Async scan jobs (POST /scan -> job_id)
- Webhook management
- RBAC enforcement
- Prometheus /metrics endpoint
- Admin: tenants, users, DLQ, delivery logs
- Security headers middleware

Mounts alongside existing endpoints in api.py.

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import uuid
import json
import time
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict

from fastapi import APIRouter, HTTPException, Depends, Request, Response, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger
from tenancy import (
    init_tenant_schema, create_tenant, get_tenant, list_tenants,
    update_tenant, create_tenant_user, list_tenant_users,
    seed_demo_tenant, check_tenant_rate_limit,
    TenantContext, get_tenant_context,
)
from jobs import (
    init_jobs_schema, create_job, get_job, list_jobs,
    update_job_status, get_dlq_items, get_queue_metrics,
    ScanWorker, run_scan_pipeline,
)
from webhooks import (
    init_webhooks_schema, create_webhook_event, get_delivery_logs,
    get_webhook_metrics, verify_signature,
)
from rbac import (
    require_permission, require_role, has_permission,
    get_role_from_key, ROLE_PERMISSIONS,
)
from observability import metrics, update_system_gauges

logger = get_logger("api_v2")

DB_PATH = os.environ.get(
    "SUNLIGHT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "sunlight.db"),
)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    idempotency_key: Optional[str] = Field(None, description="Deduplicate scan submissions")
    config: Optional[Dict] = Field(default_factory=dict, description="Pipeline config overrides")
    limit: Optional[int] = Field(None, ge=1, le=100000, description="Max contracts to scan")
    seed: Optional[int] = Field(42, description="Random seed for reproducibility")
    webhook_url: Optional[str] = Field(None, description="Override webhook URL for this scan")


class ScanResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    progress_pct: int
    progress_msg: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    result: Optional[Dict] = None


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    tier: str = Field("standard", pattern=r"^(demo|standard|enterprise)$")
    webhook_url: Optional[str] = None


class TenantUserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    role: str = Field("analyst", pattern=r"^(viewer|analyst|admin)$")


class WebhookConfigUpdate(BaseModel):
    webhook_url: Optional[str] = None


class DispositionRequest(BaseModel):
    contract_id: str
    disposition: str = Field(..., pattern=r"^(confirmed_fraud|false_positive|needs_review|dismissed)$")
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Initialize schemas
# ---------------------------------------------------------------------------

def init_v2_schemas():
    """Initialize all v2 database schemas."""
    init_tenant_schema(DB_PATH)
    init_jobs_schema(DB_PATH)
    init_webhooks_schema(DB_PATH)
    seed_demo_tenant(DB_PATH)
    logger.info("V2 schemas initialized")


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    # Generate request ID
    request.state.request_id = str(uuid.uuid4())[:8]
    request.state.tenant_id = None

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-Id"] = request.state.request_id
    response.headers["X-Sunlight-Version"] = "2.0.0"

    return response


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/v2", tags=["SUNLIGHT v2"])


# ── Scan Jobs ─────────────────────────────────────────────────────────────

@router.post("/scan", response_model=ScanResponse, tags=["Scanning"])
async def submit_scan(req: ScanRequest, request: Request):
    """
    Submit an async scan job. Returns immediately with job_id.
    Poll GET /api/v2/jobs/{job_id} for status/progress.
    """
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")

    input_data = {
        "limit": req.limit,
        "seed": req.seed,
        "config": req.config or {},
    }

    job = create_job(
        db_path=DB_PATH,
        tenant_id=tenant_id,
        job_type="batch_scan",
        input_data=input_data,
        idempotency_key=req.idempotency_key,
    )

    return ScanResponse(
        job_id=job["job_id"],
        status=job["status"],
        message="Scan queued. Poll /api/v2/jobs/{job_id} for progress.",
    )


@router.get("/jobs", tags=["Jobs"])
async def list_scan_jobs(
    request: Request,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """List scan jobs for the current tenant."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    jobs = list_jobs(DB_PATH, tenant_id, status=status, limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}", response_model=JobResponse, tags=["Jobs"])
async def get_scan_job(job_id: str, request: Request):
    """Get job status, progress, and result."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    job = get_job(DB_PATH, job_id, tenant_id=tenant_id)
    if not job:
        raise HTTPException(404, "Job not found")

    result = None
    if job.get("result_json"):
        try:
            result = json.loads(job["result_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    return JobResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress_pct=job.get("progress_pct", 0),
        progress_msg=job.get("progress_msg"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
        result=result,
    )


@router.get("/jobs/{job_id}/result", tags=["Jobs"])
async def get_scan_result(job_id: str, request: Request):
    """Get full scan result for a completed job."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    job = get_job(DB_PATH, job_id, tenant_id=tenant_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] != "SUCCEEDED":
        raise HTTPException(400, f"Job status is {job['status']}, not SUCCEEDED")

    try:
        result = json.loads(job["result_json"]) if job.get("result_json") else {}
    except (json.JSONDecodeError, TypeError):
        result = {}

    return {"job_id": job_id, "result": result}


# ── Tenants ───────────────────────────────────────────────────────────────

@router.post("/tenants", tags=["Admin"])
async def create_new_tenant(req: TenantCreate, request: Request):
    """Create a new tenant (admin only)."""
    try:
        tenant = create_tenant(
            DB_PATH, name=req.name, slug=req.slug,
            tier=req.tier, webhook_url=req.webhook_url,
        )
        return tenant
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/tenants", tags=["Admin"])
async def list_all_tenants(request: Request):
    """List all tenants (admin only)."""
    tenants = list_tenants(DB_PATH)
    return {"tenants": tenants}


@router.get("/tenants/{tenant_id}", tags=["Admin"])
async def get_tenant_detail(tenant_id: str):
    """Get tenant details."""
    tenant = get_tenant(DB_PATH, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    # Redact webhook_secret
    tenant.pop("webhook_secret", None)
    return tenant


@router.patch("/tenants/{tenant_id}", tags=["Admin"])
async def update_tenant_settings(tenant_id: str, updates: Dict):
    """Update tenant settings."""
    updated = update_tenant(DB_PATH, tenant_id, updates)
    if not updated:
        raise HTTPException(404, "Tenant not found or no valid fields")
    return {"status": "updated", "tenant_id": tenant_id}


@router.patch("/tenants/{tenant_id}/webhook", tags=["Admin"])
async def set_webhook_url(tenant_id: str, config: WebhookConfigUpdate):
    """Set webhook URL for a tenant."""
    updated = update_tenant(DB_PATH, tenant_id, {"webhook_url": config.webhook_url})
    if not updated:
        raise HTTPException(404, "Tenant not found")
    return {"status": "updated", "webhook_url": config.webhook_url}


# ── Users ─────────────────────────────────────────────────────────────────

@router.post("/tenants/{tenant_id}/users", tags=["Admin"])
async def create_user(tenant_id: str, req: TenantUserCreate):
    """Create a user in a tenant."""
    try:
        user = create_tenant_user(DB_PATH, tenant_id, req.email, req.role)
        return user
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/tenants/{tenant_id}/users", tags=["Admin"])
async def list_users(tenant_id: str):
    """List users in a tenant."""
    users = list_tenant_users(DB_PATH, tenant_id)
    return {"users": users}


# ── Webhooks ──────────────────────────────────────────────────────────────

@router.get("/webhooks/deliveries", tags=["Webhooks"])
async def webhook_delivery_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
):
    """Get webhook delivery logs for current tenant."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    logs = get_delivery_logs(DB_PATH, tenant_id, limit=limit)
    return {"deliveries": logs, "count": len(logs)}


@router.get("/webhooks/metrics", tags=["Webhooks"])
async def webhook_metrics_endpoint():
    """Get webhook delivery health metrics."""
    return get_webhook_metrics(DB_PATH)


# ── DLQ ───────────────────────────────────────────────────────────────────

@router.get("/dlq", tags=["Admin"])
async def list_dlq(request: Request):
    """List dead-letter queue items."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    items = get_dlq_items(DB_PATH, tenant_id)
    return {"items": items, "count": len(items)}


# ── Queue Health ──────────────────────────────────────────────────────────

@router.get("/queue/health", tags=["Observability"])
async def queue_health():
    """Get job queue health metrics."""
    return get_queue_metrics(DB_PATH)


# ── Metrics ───────────────────────────────────────────────────────────────

@router.get("/metrics", tags=["Observability"], response_class=PlainTextResponse)
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    update_system_gauges(DB_PATH)
    return metrics.export_prometheus()


# ── Disposition ───────────────────────────────────────────────────────────

@router.post("/disposition", tags=["Risk Inbox"])
async def set_disposition(req: DispositionRequest, request: Request):
    """Set analyst disposition on a flagged contract."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(DB_PATH)
    # Verify contract exists and is flagged
    row = conn.execute(
        "SELECT tier FROM contract_scores WHERE contract_id = ? ORDER BY scored_at DESC LIMIT 1",
        (req.contract_id,),
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(404, "Contract score not found")

    # Log disposition in audit
    from institutional_pipeline import append_audit_entry
    append_audit_entry(DB_PATH, "DISPOSITION", {
        "contract_id": req.contract_id,
        "disposition": req.disposition,
        "notes": req.notes,
        "tenant_id": tenant_id,
        "tier": row[0],
    })
    conn.close()

    return {"status": "recorded", "contract_id": req.contract_id,
            "disposition": req.disposition}


# ── Risk Inbox ────────────────────────────────────────────────────────────

@router.get("/risk-inbox", tags=["Risk Inbox"])
async def risk_inbox(
    request: Request,
    tier: Optional[str] = Query(None, pattern=r"^(RED|YELLOW)$"),
    sort_by: str = Query("triage_priority", pattern=r"^(triage_priority|markup_pct|bayesian_posterior|award_amount)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Risk inbox: flagged contracts sorted by priority.
    Shows workload metrics: flags/1k, estimated analyst minutes.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get latest run
    run = conn.execute(
        "SELECT run_id FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    if not run:
        conn.close()
        return {"items": [], "workload": {}, "count": 0}

    run_id = run["run_id"]

    # Build query
    q = """SELECT cs.*, c.vendor_name, c.agency_name, c.award_amount, c.description
           FROM contract_scores cs
           JOIN contracts c ON cs.contract_id = c.contract_id
           WHERE cs.run_id = ? AND cs.tier IN ('RED', 'YELLOW')"""
    params: list = [run_id]

    if tier:
        q += " AND cs.tier = ?"
        params.append(tier)

    q += f" ORDER BY cs.{sort_by} ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(q, params).fetchall()
    items = [dict(r) for r in rows]

    # Workload metrics
    total_flagged = conn.execute(
        "SELECT COUNT(*) FROM contract_scores WHERE run_id = ? AND tier IN ('RED','YELLOW')",
        (run_id,),
    ).fetchone()[0]

    total_scored = conn.execute(
        "SELECT COUNT(*) FROM contract_scores WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]

    conn.close()

    flags_per_1k = round(total_flagged / total_scored * 1000, 1) if total_scored else 0
    analyst_minutes = total_flagged * 45  # 45 min per flag

    return {
        "items": items,
        "count": total_flagged,
        "workload": {
            "flags_per_1k": flags_per_1k,
            "total_flagged": total_flagged,
            "total_scored": total_scored,
            "estimated_analyst_minutes": analyst_minutes,
            "estimated_analyst_hours": round(analyst_minutes / 60, 1),
        },
    }


# ── Portfolio View ────────────────────────────────────────────────────────

@router.get("/portfolio", tags=["Portfolio"])
async def portfolio_view(request: Request):
    """Portfolio overview: tier distribution, top typologies, repeat entities."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    run = conn.execute(
        "SELECT run_id FROM analysis_runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()

    if not run:
        conn.close()
        return {"tiers": {}, "top_vendors": [], "top_agencies": []}

    run_id = run["run_id"]

    # Tier distribution
    tiers = {}
    for row in conn.execute(
        "SELECT tier, COUNT(*) as cnt, SUM(CASE WHEN markup_pct IS NOT NULL THEN markup_pct ELSE 0 END) as total_markup FROM contract_scores WHERE run_id = ? GROUP BY tier",
        (run_id,),
    ).fetchall():
        tiers[row["tier"]] = {"count": row["cnt"], "total_markup_pct": round(row["total_markup"] or 0, 1)}

    # Top flagged vendors (repeat entities)
    top_vendors = [dict(r) for r in conn.execute(
        """SELECT c.vendor_name, COUNT(*) as flag_count,
                  SUM(c.award_amount) as total_value, cs.tier
           FROM contract_scores cs
           JOIN contracts c ON cs.contract_id = c.contract_id
           WHERE cs.run_id = ? AND cs.tier IN ('RED','YELLOW')
           GROUP BY c.vendor_name
           ORDER BY flag_count DESC LIMIT 20""",
        (run_id,),
    ).fetchall()]

    # Top flagged agencies
    top_agencies = [dict(r) for r in conn.execute(
        """SELECT c.agency_name, COUNT(*) as flag_count,
                  SUM(c.award_amount) as total_value
           FROM contract_scores cs
           JOIN contracts c ON cs.contract_id = c.contract_id
           WHERE cs.run_id = ? AND cs.tier IN ('RED','YELLOW')
           GROUP BY c.agency_name
           ORDER BY flag_count DESC LIMIT 20""",
        (run_id,),
    ).fetchall()]

    conn.close()

    return {
        "run_id": run_id,
        "tiers": tiers,
        "top_flagged_vendors": top_vendors,
        "top_flagged_agencies": top_agencies,
    }


# ── Demo / Onboarding ────────────────────────────────────────────────────

@router.get("/onboarding/status", tags=["Onboarding"])
async def onboarding_status(request: Request):
    """Check onboarding progress for current tenant."""
    tenant_id = getattr(request.state, "tenant_id", "ten_demo")
    conn = sqlite3.connect(DB_PATH)

    has_contracts = conn.execute(
        "SELECT COUNT(*) FROM contracts LIMIT 1"
    ).fetchone()[0] > 0

    has_scores = conn.execute(
        "SELECT COUNT(*) FROM contract_scores LIMIT 1"
    ).fetchone()[0] > 0

    has_run = conn.execute(
        "SELECT COUNT(*) FROM analysis_runs LIMIT 1"
    ).fetchone()[0] > 0

    conn.close()

    steps = {
        "tenant_created": True,
        "data_ingested": has_contracts,
        "first_scan_complete": has_run and has_scores,
        "risk_inbox_available": has_scores,
    }

    return {
        "tenant_id": tenant_id,
        "steps": steps,
        "complete": all(steps.values()),
        "next_step": next((k for k, v in steps.items() if not v), "done"),
    }


# ---------------------------------------------------------------------------
# Schema init on import
# ---------------------------------------------------------------------------

try:
    if os.path.exists(DB_PATH):
        init_v2_schemas()
except Exception as e:
    logger.warning("V2 schema init deferred", extra={"error": str(e)})
