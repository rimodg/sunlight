"""
SUNLIGHT REST API — Institutional-Grade Fraud Detection
=======================================================

FastAPI application exposing the SUNLIGHT detection engine
for institutional integration (World Bank, IMF, Fortune 500).

Endpoints:
    GET  /health                     — Service health check
    GET  /contracts                  — List contracts with filters
    GET  /contracts/{contract_id}    — Single contract detail
    POST /contracts                  — Submit new contract for analysis
    POST /analyze                    — Score a single contract
    POST /analyze/batch              — Run batch analysis pipeline
    GET  /scores                     — Query scored contracts
    GET  /scores/{contract_id}       — Scores for a specific contract
    GET  /reports/evidence/{contract_id} — Full evidence package
    GET  /reports/triage             — Triage queue (RED/YELLOW first)
    GET  /runs                       — List analysis runs
    GET  /runs/{run_id}              — Run detail with verification
    GET  /audit                      — Audit trail
    POST /ingest                     — Upload document for async ingestion
    GET  /ingest/{job_id}            — Check ingestion job status
    GET  /admin/dashboard/health     — System health overview
    GET  /admin/dashboard/detections — Detection stats over time
    GET  /admin/dashboard/api-usage  — API usage per client
    GET  /admin/dashboard/flagged    — Flagged contracts queue
"""

import os
import sys
import sqlite3
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional, List
from enum import Enum

from fastapi import FastAPI, HTTPException, Query, Path, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add code directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
from institutional_statistical_rigor import (
    BootstrapAnalyzer, BayesianFraudPrior, MultipleTestingCorrection,
    ProsecutorEvidencePackage, DOJProsecutionThresholds, FraudTier,
)
from institutional_pipeline import (
    InstitutionalPipeline, InstitutionalVerification,
    verify_audit_chain,
)
from sunlight_logging import get_logger
from detection_report import generate_detection_report, render_markdown
from api_v2 import router as v2_router
from auth import (
    create_auth_dependency, require_api_key_dynamic,
    generate_api_key, rotate_api_key,
    revoke_api_key, list_api_keys, get_key_usage, init_auth_schema,
)
from ingestion import (
    init_ingestion_schema, create_job, get_job, process_ingestion,
)
from dashboard import (
    get_system_health, get_detection_stats, get_api_usage, get_flagged_queue,
)

logger = get_logger("api")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get(
    "SUNLIGHT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "sunlight.db"),
)

API_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class TierEnum(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    GRAY = "GRAY"


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    contract_count: int
    scored_count: int
    audit_chain_valid: bool


class ContractIn(BaseModel):
    contract_id: str = Field(..., min_length=1, max_length=100, description="Unique contract identifier")
    award_amount: float = Field(..., gt=0, le=1e15, description="Award amount in USD")
    vendor_name: str = Field(..., min_length=1, max_length=500)
    agency_name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000, description="Contract description")
    start_date: Optional[str] = Field(default=None, max_length=30)


class ContractOut(BaseModel):
    contract_id: str
    award_amount: float
    vendor_name: str
    agency_name: str
    description: Optional[str]
    start_date: Optional[str]


class ScoreOut(BaseModel):
    score_id: str
    contract_id: str
    run_id: str
    fraud_tier: str
    confidence_score: int
    markup_pct: Optional[float]
    markup_ci_lower: Optional[float]
    markup_ci_upper: Optional[float]
    raw_zscore: Optional[float]
    log_zscore: Optional[float]
    bayesian_prior: Optional[float]
    bayesian_posterior: Optional[float]
    bayesian_likelihood_ratio: Optional[float]
    bootstrap_percentile: Optional[float]
    raw_pvalue: Optional[float]
    fdr_adjusted_pvalue: Optional[float]
    survives_fdr: bool
    comparable_count: int
    insufficient_comparables: bool


class AnalyzeSingleRequest(BaseModel):
    contract_id: str = Field(..., min_length=1, max_length=100)
    award_amount: float = Field(..., gt=0, le=1e15)
    vendor_name: str = Field(..., min_length=1, max_length=500)
    agency_name: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)
    is_sole_source: bool = False
    has_political_donations: bool = False


class AnalyzeSingleResponse(BaseModel):
    contract_id: str
    fraud_tier: str
    confidence_score: int
    markup_pct: Optional[float]
    markup_ci_lower: Optional[float]
    markup_ci_upper: Optional[float]
    bayesian_posterior: Optional[float]
    comparable_count: int
    reasoning: List[str]
    legal_citations: List[str]
    methodology_version: str


class BatchRequest(BaseModel):
    run_seed: int = Field(default=42, description="Seed for reproducibility")
    n_bootstrap: int = Field(default=1000, ge=100, le=50000)
    fdr_alpha: float = Field(default=0.10, gt=0, lt=1)
    min_amount: float = Field(default=0, ge=0)
    limit: Optional[int] = Field(default=None, ge=1)


class BatchResponse(BaseModel):
    run_id: str
    run_seed: int
    config_hash: str
    dataset_hash: str
    n_contracts: int
    n_scored: int
    n_errors: int
    tier_counts: dict
    pass1_time: float


class EvidenceOut(BaseModel):
    contract_id: str
    contract_amount: float
    sample_size: int
    raw_zscore: float
    log_zscore: float
    raw_markup_pct: float
    bootstrap_markup: dict
    bootstrap_percentile: dict
    bayesian_fraud_probability: dict
    fdr_adjusted_pvalue: float
    survives_fdr: bool
    tier: str
    confidence_score: int
    reasoning: List[str]
    legal_citations: List[str]
    methodology_version: str


class RunOut(BaseModel):
    run_id: str
    started_at: str
    completed_at: Optional[str]
    status: str
    run_seed: int
    n_contracts: Optional[int]
    n_scored: Optional[int]
    n_errors: Optional[int]
    config_hash: Optional[str]
    dataset_hash: Optional[str]


class AuditEntry(BaseModel):
    sequence_number: int
    timestamp: str
    action: str
    run_id: Optional[str]
    entry_hash: str


class PaginatedResponse(BaseModel):
    total: int
    offset: int
    limit: int
    items: list


class ErrorResponse(BaseModel):
    error: str
    detail: str


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    """Get a database connection with row factory."""
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail=f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

MAX_REQUEST_SIZE = 50 * 1024 * 1024  # 50 MB

app = FastAPI(
    title="SUNLIGHT Fraud Detection API",
    description=(
        "Institutional-grade fraud detection for government procurement contracts. "
        "Bootstrap/Bayesian/FDR statistical engine with DOJ-calibrated thresholds. "
        "Every detection is explainable and prosecution-ready."
    ),
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — configurable via environment
CORS_ORIGINS = os.environ.get("SUNLIGHT_CORS_ORIGINS", "").split(",")
CORS_ORIGINS = [o.strip() for o in CORS_ORIGINS if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-API-Key", "X-Tenant-ID", "Content-Type"],
    max_age=3600,
)

# Mount v2 API router (multi-tenant, async jobs, webhooks, RBAC, metrics)
app.include_router(v2_router)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Reject requests exceeding MAX_REQUEST_SIZE."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_SIZE:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body too large. Maximum size: {MAX_REQUEST_SIZE // (1024*1024)} MB"},
        )
    return await call_next(request)


# Static files and templates
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_REPO_ROOT, "static")
_TEMPLATE_DIR = os.path.join(_REPO_ROOT, "templates")

if os.path.isdir(_STATIC_DIR):
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

# Initialize auth and ingestion schemas
init_auth_schema(DB_PATH)
init_ingestion_schema(DB_PATH)
require_api_key = require_api_key_dynamic


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Service health check with database status (unauthenticated)."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM contracts")
        contract_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM contract_scores")
        scored_count = c.fetchone()[0]
        conn.close()
        valid, _ = verify_audit_chain(DB_PATH)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        database=os.path.basename(DB_PATH),
        contract_count=contract_count,
        scored_count=scored_count,
        audit_chain_valid=valid,
    )


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

@app.get("/contracts", response_model=PaginatedResponse, tags=["Contracts"])
def list_contracts(
    agency: Optional[str] = Query(None, description="Filter by agency name (substring match)"),
    vendor: Optional[str] = Query(None, description="Filter by vendor name (substring match)"),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    client: dict = Depends(require_api_key),
):
    """List contracts with optional filters and pagination."""
    conn = get_db()
    c = conn.cursor()

    where_clauses = []
    params = []

    if agency:
        where_clauses.append("agency_name LIKE ?")
        params.append(f"%{agency}%")
    if vendor:
        where_clauses.append("vendor_name LIKE ?")
        params.append(f"%{vendor}%")
    if min_amount is not None:
        where_clauses.append("award_amount >= ?")
        params.append(min_amount)
    if max_amount is not None:
        where_clauses.append("award_amount <= ?")
        params.append(max_amount)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    c.execute(f"SELECT COUNT(*) FROM contracts WHERE {where_sql}", params)
    total = c.fetchone()[0]

    c.execute(
        f"SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date "
        f"FROM contracts WHERE {where_sql} ORDER BY award_amount DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    return PaginatedResponse(total=total, offset=offset, limit=limit, items=rows)


@app.get("/contracts/{contract_id}", response_model=ContractOut, tags=["Contracts"])
def get_contract(contract_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Get a single contract by ID."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date "
        "FROM contracts WHERE contract_id = ?",
        (contract_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    return ContractOut(**dict(row))


@app.post("/contracts", response_model=ContractOut, status_code=201, tags=["Contracts"])
def submit_contract(contract: ContractIn, client: dict = Depends(require_api_key)):
    """Submit a new contract for future analysis."""
    conn = get_db()
    c = conn.cursor()

    # Check for duplicate
    c.execute("SELECT 1 FROM contracts WHERE contract_id = ?", (contract.contract_id,))
    if c.fetchone():
        conn.close()
        logger.warning("Duplicate contract submission",
            extra={"contract_id": contract.contract_id})
        raise HTTPException(status_code=409, detail=f"Contract {contract.contract_id} already exists")

    raw_hash = hashlib.sha256(
        f"{contract.contract_id}:{contract.award_amount}:{contract.vendor_name}".encode()
    ).hexdigest()

    c.execute(
        "INSERT INTO contracts (contract_id, award_amount, vendor_name, agency_name, "
        "description, start_date, raw_data_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            contract.contract_id,
            contract.award_amount,
            contract.vendor_name,
            contract.agency_name,
            contract.description,
            contract.start_date,
            raw_hash,
        ),
    )
    conn.commit()
    conn.close()

    logger.info("Contract submitted",
        extra={"contract_id": contract.contract_id, "award_amount": contract.award_amount,
               "vendor": contract.vendor_name, "agency": contract.agency_name})

    return ContractOut(
        contract_id=contract.contract_id,
        award_amount=contract.award_amount,
        vendor_name=contract.vendor_name,
        agency_name=contract.agency_name,
        description=contract.description,
        start_date=contract.start_date,
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=AnalyzeSingleResponse, tags=["Analysis"])
def analyze_single(request: AnalyzeSingleRequest, client: dict = Depends(require_api_key)):
    """
    Score a single contract against the database of comparables.

    Returns fraud tier, confidence score, statistical evidence, and legal citations.
    Every field is explainable — no black-box scores.
    """
    conn = get_db()
    c = conn.cursor()

    # Get comparables from same agency
    c.execute(
        "SELECT award_amount FROM contracts WHERE agency_name = ? AND contract_id != ? AND award_amount > 0",
        (request.agency_name, request.contract_id),
    )
    comparables = [row[0] for row in c.fetchall()]
    conn.close()

    # Filter to similar size
    if comparables:
        import numpy as np
        target_bin = int(np.log10(request.award_amount)) if request.award_amount > 0 else 0
        similar = [a for a in comparables if abs(int(np.log10(a)) if a > 0 else 0 - target_bin) <= 1]
        if len(similar) < 5:
            similar = [a for a in comparables if 0.1 * request.award_amount <= a <= 10 * request.award_amount]
        comparables = similar

    if len(comparables) < 3:
        logger.info("Single analysis: insufficient comparables",
            extra={"contract_id": request.contract_id, "comparable_count": len(comparables),
                   "decision": "GRAY"})
        return AnalyzeSingleResponse(
            contract_id=request.contract_id,
            fraud_tier="GRAY",
            confidence_score=0,
            markup_pct=None,
            markup_ci_lower=None,
            markup_ci_upper=None,
            bayesian_posterior=None,
            comparable_count=len(comparables),
            reasoning=["INSUFFICIENT DATA: Fewer than 3 comparable contracts in database"],
            legal_citations=[],
            methodology_version=API_VERSION,
        )

    # Run the evidence generator
    pkg = ProsecutorEvidencePackage(DB_PATH)
    evidence = pkg.generate_evidence({
        'id': request.contract_id,
        'amount': request.award_amount,
        'vendor': request.vendor_name,
        'agency': request.agency_name,
        'desc': request.description,
        'has_donations': request.has_political_donations,
        'is_sole_source': request.is_sole_source,
    })

    logger.info("Single analysis complete",
        extra={"contract_id": evidence.contract_id, "decision": evidence.tier.value,
               "confidence": evidence.confidence_score, "markup_pct": evidence.raw_markup_pct,
               "comparable_count": evidence.sample_size,
               "bayesian_posterior": round(evidence.bayesian_fraud_probability.posterior_probability, 4)})

    return AnalyzeSingleResponse(
        contract_id=evidence.contract_id,
        fraud_tier=evidence.tier.value,
        confidence_score=evidence.confidence_score,
        markup_pct=evidence.raw_markup_pct,
        markup_ci_lower=evidence.bootstrap_markup.ci_lower,
        markup_ci_upper=evidence.bootstrap_markup.ci_upper,
        bayesian_posterior=evidence.bayesian_fraud_probability.posterior_probability,
        comparable_count=evidence.sample_size,
        reasoning=evidence.reasoning,
        legal_citations=evidence.legal_citations,
        methodology_version=evidence.methodology_version,
    )


@app.post("/analyze/batch", response_model=BatchResponse, tags=["Analysis"])
def analyze_batch(request: BatchRequest, client: dict = Depends(require_api_key)):
    """
    Run the full two-pass institutional pipeline on all contracts.

    Pass 1: Score each contract (bootstrap CIs, Bayesian posteriors)
    Pass 2: Apply FDR correction across all scored contracts

    Results are persisted to the database with a unique run_id.
    The run is fully reproducible given the same seed and data.
    """
    logger.info("Batch analysis requested",
        extra={"run_seed": request.run_seed, "n_bootstrap": request.n_bootstrap,
               "fdr_alpha": request.fdr_alpha, "limit": request.limit})

    pipeline = InstitutionalPipeline(DB_PATH)
    try:
        result = pipeline.run(
            run_seed=request.run_seed,
            config={
                'n_bootstrap': request.n_bootstrap,
                'fdr_alpha': request.fdr_alpha,
                'min_amount': request.min_amount,
            },
            limit=request.limit,
            verbose=False,
        )
    except Exception as e:
        logger.error("Batch analysis failed", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

    return BatchResponse(**result)


# ---------------------------------------------------------------------------
# Scores
# ---------------------------------------------------------------------------

@app.get("/scores", response_model=PaginatedResponse, tags=["Scores"])
def list_scores(
    run_id: Optional[str] = Query(None, description="Filter by analysis run"),
    tier: Optional[TierEnum] = Query(None, description="Filter by fraud tier"),
    min_confidence: Optional[int] = Query(None, ge=0, le=100),
    survives_fdr: Optional[bool] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    client: dict = Depends(require_api_key),
):
    """Query scored contracts with filters."""
    conn = get_db()
    c = conn.cursor()

    where_clauses = []
    params = []

    if run_id:
        where_clauses.append("cs.run_id = ?")
        params.append(run_id)
    if tier:
        where_clauses.append("cs.fraud_tier = ?")
        params.append(tier.value)
    if min_confidence is not None:
        where_clauses.append("cs.confidence_score >= ?")
        params.append(min_confidence)
    if survives_fdr is not None:
        where_clauses.append("cs.survives_fdr = ?")
        params.append(1 if survives_fdr else 0)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    c.execute(f"SELECT COUNT(*) FROM contract_scores cs WHERE {where_sql}", params)
    total = c.fetchone()[0]

    c.execute(
        f"SELECT cs.score_id, cs.contract_id, cs.run_id, cs.fraud_tier, cs.confidence_score, "
        f"cs.markup_pct, cs.markup_ci_lower, cs.markup_ci_upper, cs.raw_zscore, cs.log_zscore, "
        f"cs.bayesian_prior, cs.bayesian_posterior, cs.bayesian_likelihood_ratio, "
        f"cs.bootstrap_percentile, cs.raw_pvalue, cs.fdr_adjusted_pvalue, cs.survives_fdr, "
        f"cs.comparable_count, cs.insufficient_comparables "
        f"FROM contract_scores cs WHERE {where_sql} "
        f"ORDER BY cs.triage_priority ASC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = [dict(r) for r in c.fetchall()]
    # Normalize booleans
    for row in rows:
        row['survives_fdr'] = bool(row.get('survives_fdr'))
        row['insufficient_comparables'] = bool(row.get('insufficient_comparables'))
    conn.close()

    return PaginatedResponse(total=total, offset=offset, limit=limit, items=rows)


@app.get("/scores/{contract_id}", tags=["Scores"])
def get_contract_scores(contract_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Get all scores for a specific contract across all runs."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT score_id, contract_id, run_id, fraud_tier, confidence_score, "
        "markup_pct, markup_ci_lower, markup_ci_upper, raw_zscore, log_zscore, "
        "bayesian_prior, bayesian_posterior, bayesian_likelihood_ratio, "
        "bootstrap_percentile, raw_pvalue, fdr_adjusted_pvalue, survives_fdr, "
        "comparable_count, insufficient_comparables "
        "FROM contract_scores WHERE contract_id = ? ORDER BY run_id DESC",
        (contract_id,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No scores found for contract {contract_id}")

    items = []
    for r in rows:
        d = dict(r)
        d['survives_fdr'] = bool(d.get('survives_fdr'))
        d['insufficient_comparables'] = bool(d.get('insufficient_comparables'))
        items.append(d)

    return {"contract_id": contract_id, "scores": items}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@app.get("/reports/evidence/{contract_id}", response_model=EvidenceOut, tags=["Reports"])
def get_evidence_package(contract_id: str = Path(...), client: dict = Depends(require_api_key)):
    """
    Generate a full prosecutor-grade evidence package for a contract.

    Includes bootstrap CIs, Bayesian analysis, legal citations,
    and human-readable reasoning. Suitable for court presentation.
    """
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT contract_id, award_amount, vendor_name, agency_name, description "
        "FROM contracts WHERE contract_id = ?",
        (contract_id,),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")

    contract = dict(row)

    # Check political donations
    c.execute(
        "SELECT SUM(amount) FROM political_donations WHERE vendor_name = ?",
        (contract['vendor_name'],),
    )
    donation_row = c.fetchone()
    has_donations = donation_row[0] is not None and donation_row[0] > 0
    conn.close()

    pkg = ProsecutorEvidencePackage(DB_PATH)
    evidence = pkg.generate_evidence({
        'id': contract['contract_id'],
        'amount': contract['award_amount'],
        'vendor': contract['vendor_name'],
        'agency': contract['agency_name'],
        'desc': contract['description'] or '',
        'has_donations': has_donations,
    })

    def _sanitize(obj):
        """Convert numpy types to Python natives for JSON serialization."""
        import numpy as np
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return obj

    return EvidenceOut(
        contract_id=evidence.contract_id,
        contract_amount=float(evidence.contract_amount),
        sample_size=int(evidence.sample_size),
        raw_zscore=float(evidence.raw_zscore),
        log_zscore=float(evidence.log_zscore),
        raw_markup_pct=float(evidence.raw_markup_pct),
        bootstrap_markup=_sanitize(evidence.bootstrap_markup.to_dict()),
        bootstrap_percentile=_sanitize(evidence.bootstrap_percentile.to_dict()),
        bayesian_fraud_probability=_sanitize(evidence.bayesian_fraud_probability.to_dict()),
        fdr_adjusted_pvalue=float(evidence.fdr_adjusted_pvalue),
        survives_fdr=bool(evidence.survives_fdr),
        tier=evidence.tier.value,
        confidence_score=int(evidence.confidence_score),
        reasoning=list(evidence.reasoning),
        legal_citations=list(evidence.legal_citations),
        methodology_version=evidence.methodology_version,
    )


@app.get("/reports/triage", response_model=PaginatedResponse, tags=["Reports"])
def triage_queue(
    run_id: Optional[str] = Query(None, description="Limit to a specific run"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    client: dict = Depends(require_api_key),
):
    """
    Get the triage queue ordered by priority (RED first, then YELLOW).

    This is the primary interface for fraud investigators.
    """
    conn = get_db()
    c = conn.cursor()

    where_clauses = ["cs.fraud_tier IN ('RED', 'YELLOW')"]
    params = []

    if run_id:
        where_clauses.append("cs.run_id = ?")
        params.append(run_id)

    where_sql = " AND ".join(where_clauses)

    c.execute(f"SELECT COUNT(*) FROM contract_scores cs WHERE {where_sql}", params)
    total = c.fetchone()[0]

    c.execute(
        f"SELECT cs.score_id, cs.contract_id, cs.run_id, cs.fraud_tier, cs.confidence_score, "
        f"cs.markup_pct, cs.markup_ci_lower, cs.markup_ci_upper, cs.bayesian_posterior, "
        f"cs.comparable_count, cs.survives_fdr, co.vendor_name, co.agency_name, co.award_amount "
        f"FROM contract_scores cs "
        f"JOIN contracts co ON cs.contract_id = co.contract_id "
        f"WHERE {where_sql} "
        f"ORDER BY cs.triage_priority ASC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = [dict(r) for r in c.fetchall()]
    for row in rows:
        row['survives_fdr'] = bool(row.get('survives_fdr'))
    conn.close()

    return PaginatedResponse(total=total, offset=offset, limit=limit, items=rows)


@app.get("/reports/detection/{contract_id}", tags=["Reports"])
def get_detection_report(
    contract_id: str = Path(...),
    run_id: Optional[str] = Query(None, description="Specific run to report on"),
    format: Optional[str] = Query("json", description="'json' or 'markdown'"),
    client: dict = Depends(require_api_key),
):
    """
    Generate a client-facing detection report with explainable reasoning.

    Returns structured JSON or human-readable markdown explaining WHY each
    flag was raised. Designed for World Bank and institutional reviewers.
    """
    report = generate_detection_report(DB_PATH, contract_id, run_id=run_id)

    if 'error' in report:
        raise HTTPException(status_code=404, detail=report['error'])

    if format == "markdown":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(
            content=render_markdown(report),
            media_type="text/markdown",
        )

    return report


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@app.get("/runs", response_model=List[RunOut], tags=["Runs"])
def list_runs(client: dict = Depends(require_api_key)):
    """List all analysis runs."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT run_id, started_at, completed_at, status, run_seed, "
        "n_contracts, n_scored, n_errors, config_hash, dataset_hash "
        "FROM analysis_runs ORDER BY started_at DESC"
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return [RunOut(**row) for row in rows]


@app.get("/runs/{run_id}", tags=["Runs"])
def get_run(run_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Get run detail with verification status."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT run_id, started_at, completed_at, status, run_seed, "
        "n_contracts, n_scored, n_errors, config_hash, dataset_hash, "
        "config_json, summary_json "
        "FROM analysis_runs WHERE run_id = ?",
        (run_id,),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    run_data = dict(row)

    # Parse JSON fields
    config = json.loads(run_data.pop('config_json', '{}') or '{}')
    summary = json.loads(run_data.pop('summary_json', '{}') or '{}')

    # Run verification
    verifier = InstitutionalVerification(DB_PATH)
    verification = verifier.verify_run(run_id, verbose=False)

    return {
        **run_data,
        "config": config,
        "summary": summary,
        "verification": verification,
    }


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@app.get("/audit", tags=["Audit"])
def get_audit_trail(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    client: dict = Depends(require_api_key),
):
    """
    Get the cryptographic audit trail.

    Each entry is hash-chained to the previous, providing tamper-evident
    logging suitable for institutional compliance requirements.
    """
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM audit_log")
    total = c.fetchone()[0]

    # Handle both column naming conventions
    try:
        c.execute(
            "SELECT sequence_number, timestamp, action, run_id, entry_hash "
            "FROM audit_log ORDER BY sequence_number ASC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    except sqlite3.OperationalError:
        c.execute(
            "SELECT sequence_number, timestamp, action_type as action, entity_id as run_id, "
            "current_log_hash as entry_hash "
            "FROM audit_log ORDER BY sequence_number ASC LIMIT ? OFFSET ?",
            (limit, offset),
        )

    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    valid, msg = verify_audit_chain(DB_PATH)

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "chain_valid": valid,
        "chain_status": msg,
        "entries": rows,
    }


# ---------------------------------------------------------------------------
# Methodology (for transparency)
# ---------------------------------------------------------------------------

@app.get("/methodology", tags=["System"])
def get_methodology(client: dict = Depends(require_api_key)):
    """
    Return the detection methodology — full transparency.

    Every threshold, every base rate, every statistical method is documented.
    This is not a black box.
    """
    return {
        "version": API_VERSION,
        "statistical_methods": {
            "bootstrap": {
                "type": "BCa (bias-corrected and accelerated)",
                "default_iterations": DOJProsecutionThresholds.BOOTSTRAP_ITERATIONS,
                "confidence_level": 0.95,
                "purpose": "Robust confidence intervals for small samples",
            },
            "bayesian": {
                "framework": "Bayes theorem with DOJ-calibrated priors",
                "base_rates": BayesianFraudPrior.BASE_RATES,
                "detector_performance": BayesianFraudPrior.DETECTOR_PERFORMANCE,
                "purpose": "Adjust for base rate neglect",
            },
            "fdr_correction": {
                "method": "Benjamini-Hochberg",
                "default_alpha": 0.10,
                "purpose": "Control false discovery rate when testing many contracts",
            },
        },
        "thresholds": {
            "extreme_markup_pct": DOJProsecutionThresholds.EXTREME_MARKUP,
            "high_markup_pct": DOJProsecutionThresholds.HIGH_MARKUP,
            "elevated_markup_pct": DOJProsecutionThresholds.ELEVATED_MARKUP,
            "investigation_worthy_pct": DOJProsecutionThresholds.INVESTIGATION_WORTHY,
        },
        "tier_definitions": {
            "RED": "Prosecution-ready. 95%+ confidence, CI lower bound exceeds DOJ extreme threshold.",
            "YELLOW": "Investigation-worthy. Statistical evidence warrants further review.",
            "GREEN": "Normal. No significant evidence of fraud detected.",
            "GRAY": "Insufficient data. Fewer than 3 comparable contracts available.",
        },
        "legal_framework": [
            "31 U.S.C. 3729 — False Claims Act",
            "41 U.S.C. 8702 — Anti-Kickback Act",
            "41 U.S.C. 2102 — Procurement Integrity Act",
        ],
        "transparency_commitment": (
            "Every detection is explainable. Every threshold is traceable to DOJ prosecution "
            "precedent. Every statistical method is documented and reproducible. "
            "No black-box scores."
        ),
    }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

from fastapi import UploadFile, File

class IngestionResponse(BaseModel):
    job_id: str
    status: str
    message: str


class IngestionStatusResponse(BaseModel):
    job_id: str
    status: str
    source_filename: Optional[str]
    source_format: str
    submitted_at: str
    completed_at: Optional[str]
    total_records: int
    inserted: int
    duplicates: int
    errors: int
    scored: int
    error_details: Optional[str]


@app.post("/ingest", response_model=IngestionResponse, status_code=202, tags=["Ingestion"])
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    client: dict = Depends(require_api_key),
):
    """
    Upload a procurement document for ingestion and async scoring.

    Accepts PDF, CSV, or JSON files. Extracts structured contract data,
    inserts into the database, and scores through the detection pipeline.
    Returns a tracking ID for polling status.

    Supported formats:
    - **JSON**: Single contract object, array, or `{"contracts": [...]}`
    - **CSV**: Header row with columns matching contract fields
    - **PDF**: Best-effort text extraction (structured formats preferred)
    """
    filename = file.filename or "upload"
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    # Determine format
    content_type = file.content_type or ''
    if ext == 'json' or 'json' in content_type:
        source_format = 'json'
    elif ext == 'csv' or 'csv' in content_type:
        source_format = 'csv'
    elif ext == 'pdf' or 'pdf' in content_type:
        source_format = 'pdf'
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {ext}. Use JSON, CSV, or PDF."
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    source_hash = hashlib.sha256(content).hexdigest()

    # Create tracking job
    job_id = create_job(
        DB_PATH, filename, source_format, source_hash,
        client_name=client.get('client_name', 'anonymous'),
    )

    # Process async
    background_tasks.add_task(process_ingestion, DB_PATH, job_id, content, source_format, filename)

    logger.info("Ingestion job submitted",
                extra={"job_id": job_id, "source_file": filename, "source_format": source_format,
                       "size_bytes": len(content), "client_name_val": client.get('client_name')})

    return IngestionResponse(
        job_id=job_id,
        status="PENDING",
        message=f"File '{filename}' accepted for processing. Poll /ingest/{job_id} for status.",
    )


@app.get("/ingest/{job_id}", response_model=IngestionStatusResponse, tags=["Ingestion"])
def get_ingestion_status(job_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Check the status of an ingestion job."""
    job = get_job(DB_PATH, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job {job_id} not found")
    return IngestionStatusResponse(**job)


# ---------------------------------------------------------------------------
# Admin — Dashboard
# ---------------------------------------------------------------------------

@app.get("/admin/dashboard/health", tags=["Admin Dashboard"])
def admin_dashboard_health(client: dict = Depends(require_api_key)):
    """
    System health overview: database stats, pipeline status, audit chain integrity.
    Requires admin scope.
    """
    _require_admin(client)
    return get_system_health(DB_PATH)


@app.get("/admin/dashboard/detections", tags=["Admin Dashboard"])
def admin_dashboard_detections(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    client: dict = Depends(require_api_key),
):
    """
    Detection statistics: tier distribution, run history, top flagged vendors/agencies.
    Requires admin scope.
    """
    _require_admin(client)
    return get_detection_stats(DB_PATH, days=days)


@app.get("/admin/dashboard/api-usage", tags=["Admin Dashboard"])
def admin_dashboard_api_usage(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    client: dict = Depends(require_api_key),
):
    """
    API usage per client: request volume, top endpoints, active keys.
    Requires admin scope.
    """
    _require_admin(client)
    return get_api_usage(DB_PATH, days=days)


@app.get("/admin/dashboard/flagged", tags=["Admin Dashboard"])
def admin_dashboard_flagged(
    tier: Optional[str] = Query(None, description="Filter by tier: RED or YELLOW"),
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    client: dict = Depends(require_api_key),
):
    """
    Flagged contracts queue with investigation priority.
    RED contracts first, then YELLOW, ordered by triage priority.
    Requires admin scope.
    """
    _require_admin(client)
    return get_flagged_queue(DB_PATH, tier=tier, run_id=run_id, offset=offset, limit=limit)


# ---------------------------------------------------------------------------
# Admin — Key Management
# ---------------------------------------------------------------------------

def _require_admin(client: dict):
    """Check that client has admin scope."""
    if 'admin' not in client.get('scopes', ''):
        raise HTTPException(status_code=403, detail="Admin scope required.")


class KeyGenerateRequest(BaseModel):
    client_name: str = Field(..., min_length=1)
    rate_limit: int = Field(default=100, ge=1)
    rate_window: int = Field(default=3600, ge=60)
    scopes: str = Field(default="read,analyze")
    expires_at: Optional[str] = None


class KeyRotateRequest(BaseModel):
    key_id: str


@app.post("/admin/keys", tags=["Admin"], status_code=201)
def admin_generate_key(request: KeyGenerateRequest, client: dict = Depends(require_api_key)):
    """Generate a new API key. Requires admin scope."""
    _require_admin(client)
    result = generate_api_key(
        DB_PATH, request.client_name,
        rate_limit=request.rate_limit,
        rate_window=request.rate_window,
        scopes=request.scopes,
        expires_at=request.expires_at,
    )
    return result


@app.get("/admin/keys", tags=["Admin"])
def admin_list_keys(client: dict = Depends(require_api_key)):
    """List all API keys (no secrets). Requires admin scope."""
    _require_admin(client)
    return list_api_keys(DB_PATH)


@app.post("/admin/keys/rotate", tags=["Admin"])
def admin_rotate_key(request: KeyRotateRequest, client: dict = Depends(require_api_key)):
    """Rotate an API key. Requires admin scope."""
    _require_admin(client)
    try:
        result = rotate_api_key(DB_PATH, request.key_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@app.delete("/admin/keys/{key_id}", tags=["Admin"])
def admin_revoke_key(key_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Revoke an API key. Requires admin scope."""
    _require_admin(client)
    revoke_api_key(DB_PATH, key_id)
    return {"status": "revoked", "key_id": key_id}


@app.get("/admin/keys/{key_id}/usage", tags=["Admin"])
def admin_key_usage(key_id: str = Path(...), client: dict = Depends(require_api_key)):
    """Get usage statistics for a key. Requires admin scope."""
    _require_admin(client)
    return get_key_usage(DB_PATH, key_id)


# ---------------------------------------------------------------------------
# Web Dashboard (unauthenticated — served at /dashboard)
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"],
         include_in_schema=False)
def serve_dashboard():
    """Serve the SUNLIGHT web dashboard."""
    template_path = os.path.join(_TEMPLATE_DIR, "dashboard.html")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail="Dashboard template not found")
    with open(template_path) as f:
        return HTMLResponse(content=f.read())


@app.get("/dashboard/api/health", tags=["Dashboard"], include_in_schema=False)
def dashboard_api_health():
    """Health data for dashboard (unauthenticated)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM contracts")
    contract_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM contract_scores")
    scored_count = c.fetchone()[0]

    audit_chain_valid = True
    try:
        c.execute("""
            WITH chain AS (
                SELECT sequence_number,
                       previous_log_hash,
                       current_log_hash,
                       LAG(current_log_hash) OVER (ORDER BY sequence_number) AS expected_prev
                FROM audit_log
            )
            SELECT COUNT(*) FROM chain
            WHERE sequence_number > 1 AND previous_log_hash != expected_prev
        """)
        chain_breaks = c.fetchone()[0]
        audit_chain_valid = chain_breaks == 0
    except Exception:
        pass

    db_name = os.path.basename(DB_PATH)
    conn.close()
    return {
        "status": "operational",
        "version": API_VERSION,
        "database": db_name,
        "contract_count": contract_count,
        "scored_count": scored_count,
        "audit_chain_valid": audit_chain_valid,
    }


@app.get("/dashboard/api/triage", tags=["Dashboard"], include_in_schema=False)
def dashboard_api_triage(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Flagged contracts for dashboard (unauthenticated)."""
    return get_flagged_queue(DB_PATH, offset=offset, limit=limit)


@app.get("/dashboard/api/scores", tags=["Dashboard"], include_in_schema=False)
def dashboard_api_scores(
    limit: int = Query(500, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """All scores for dashboard donut chart (unauthenticated)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM contract_scores")
    total = c.fetchone()[0]
    c.execute(
        "SELECT score_id, contract_id, run_id, fraud_tier, confidence_score, "
        "markup_pct, bayesian_posterior, comparable_count "
        "FROM contract_scores ORDER BY triage_priority ASC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    items = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"total": total, "offset": offset, "limit": limit, "items": items}


@app.get("/dashboard/api/contracts", tags=["Dashboard"], include_in_schema=False)
def dashboard_api_contracts(limit: int = Query(1, ge=1, le=500)):
    """Contract count for dashboard (unauthenticated)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM contracts")
    total = c.fetchone()[0]
    conn.close()
    return {"total": total}


@app.get("/dashboard/api/report/{contract_id}", tags=["Dashboard"],
         include_in_schema=False)
def dashboard_api_report(contract_id: str = Path(...)):
    """Detection report for expanded row (unauthenticated)."""
    report = generate_detection_report(DB_PATH, contract_id)
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    return report


@app.post("/dashboard/api/ingest", tags=["Dashboard"], include_in_schema=False)
async def dashboard_api_ingest(request: Request, background_tasks: BackgroundTasks):
    """File ingestion from dashboard upload (unauthenticated)."""
    form = await request.form()
    upload = form.get("file")
    if not upload:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await upload.read()
    filename = upload.filename or "upload"
    file_format = "csv" if filename.lower().endswith(".csv") else "json"
    job = create_job(DB_PATH, filename, file_format, len(content))

    background_tasks.add_task(
        process_ingestion, DB_PATH, job["job_id"], content, file_format
    )
    return job


@app.get("/dashboard/api/ingest/{job_id}", tags=["Dashboard"],
         include_in_schema=False)
def dashboard_api_ingest_status(job_id: str = Path(...)):
    """Check ingestion job status from dashboard (unauthenticated)."""
    job = get_job(DB_PATH, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
