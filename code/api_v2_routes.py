"""
SUNLIGHT API v2 Routes — post-flag intelligence endpoints.

New endpoints:
  - POST /v2/analyze — submit a contract or batch for analysis
  - GET  /v2/results/{job_id} — poll for results
  - GET  /v2/vendor/{vendor_id}/profile — vendor intelligence report
  - GET  /v2/case/{contract_id}/package — full evidence package
  - POST /v2/triage — submit flagged contracts, get prioritized list back

All endpoints use async, include Pydantic models, and require Bearer token auth.
"""

import os
import sys
import uuid
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("api_v2_routes")

router = APIRouter(prefix="/v2", tags=["v2-intelligence"])

DB_PATH = os.environ.get(
    "SUNLIGHT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "sunlight.db"),
)

# ---------------------------------------------------------------------------
# Auth — Bearer token
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_bearer_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """Validate Bearer token. Falls back to anonymous if auth disabled."""
    auth_enabled = os.environ.get("SUNLIGHT_AUTH_ENABLED", "true").lower() != "false"
    if not auth_enabled:
        return {"key_id": "anonymous", "client_name": "anonymous", "scopes": "read,analyze,admin"}

    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Bearer token. Include Authorization: Bearer <token> header.",
        )

    # Look up token in auth database
    token = credentials.credentials
    try:
        import hashlib
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1", (token_hash,))
        row = c.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid or revoked token.")

        return {
            "key_id": row["key_id"],
            "client_name": row["client_name"],
            "scopes": row["scopes"],
        }
    except HTTPException:
        raise
    except Exception:
        # If auth tables don't exist yet, allow anonymous in dev
        return {"key_id": "anonymous", "client_name": "anonymous", "scopes": "read,analyze,admin"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ContractSubmission(BaseModel):
    """A single contract to analyze."""
    contract_id: str = Field(..., description="Unique contract identifier")
    award_amount: float = Field(..., gt=0, description="Contract value in USD")
    vendor_name: str = Field(..., min_length=1, description="Contractor name")
    agency_name: str = Field(..., min_length=1, description="Awarding agency")
    description: str = Field("", description="Contract description")
    start_date: Optional[str] = Field(None, description="Contract start date (ISO)")


class AnalyzeRequest(BaseModel):
    """Request body for POST /v2/analyze."""
    contracts: List[ContractSubmission] = Field(..., min_length=1, max_length=1000)
    calibration_profile: str = Field("doj_federal", description="Calibration profile name")
    run_seed: int = Field(42, description="Random seed for reproducibility")


class AnalyzeResponse(BaseModel):
    """Response for POST /v2/analyze."""
    job_id: str
    status: str = "queued"
    contract_count: int
    message: str


class JobResult(BaseModel):
    """Response for GET /v2/results/{job_id}."""
    job_id: str
    status: str
    progress_pct: float = 0.0
    progress_msg: str = ""
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict] = None


class VendorProfileResponse(BaseModel):
    """Response for GET /v2/vendor/{vendor_id}/profile."""
    vendor_name: str
    contract_count: int = 0
    total_awards: float = 0.0
    average_value: float = 0.0
    sole_source_rate: float = 0.0
    concentration_score: float = 0.0
    risk_score: float = 0.0
    risk_factors: List[str] = []
    red_count: int = 0
    yellow_count: int = 0
    top_agency: str = ""
    top_agency_pct: float = 0.0


class CasePackageResponse(BaseModel):
    """Response for GET /v2/case/{contract_id}/package."""
    contract_id: str
    generated_at: str
    fraud_tier: str = ""
    confidence_score: float = 0.0
    triage_priority: int = 0
    contract_metadata: dict = {}
    signals: list = []
    peer_stats: dict = {}
    vendor_summary: dict = {}
    markup_analysis: dict = {}
    recommendation: str = ""
    markdown: str = ""


class TriageContract(BaseModel):
    """A single contract in a triage request."""
    contract_id: str
    vendor_name: str = ""
    agency_name: str = ""
    award_amount: float = 0.0
    fraud_tier: str = "YELLOW"
    confidence_score: float = 0.0
    bayesian_posterior: float = 0.0
    comparable_count: int = 0
    markup_ci_lower: Optional[float] = None
    fdr_adjusted_pvalue: Optional[float] = None
    bootstrap_percentile: Optional[float] = None
    description: str = ""
    start_date: Optional[str] = None


class TriageRequest(BaseModel):
    """Request body for POST /v2/triage."""
    contracts: List[TriageContract] = Field(..., min_length=1, max_length=5000)


class TriageItemResponse(BaseModel):
    """A single prioritized item in triage results."""
    rank: int
    contract_id: str
    vendor_name: str = ""
    agency_name: str = ""
    award_amount: float = 0.0
    fraud_tier: str = ""
    priority_score: float = 0.0
    expected_fraud_value: float = 0.0
    data_completeness: float = 0.0
    complexity_estimate: str = ""
    recommended_action: str = ""


class TriageResponse(BaseModel):
    """Response for POST /v2/triage."""
    count: int
    items: List[TriageItemResponse]


# ---------------------------------------------------------------------------
# Helper: get DB connection
# ---------------------------------------------------------------------------

def _get_db():
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=503, detail=f"Database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_contracts(
    body: AnalyzeRequest,
    client: dict = Depends(require_bearer_token),
):
    """Submit a contract or batch for fraud analysis.

    Returns a job_id that can be polled via GET /v2/results/{job_id}.
    """
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_db()
    c = conn.cursor()

    # Insert submitted contracts
    for ct in body.contracts:
        c.execute(
            """
            INSERT OR IGNORE INTO contracts (contract_id, award_amount, vendor_name, agency_name, description, start_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ct.contract_id, ct.award_amount, ct.vendor_name, ct.agency_name,
             ct.description, ct.start_date, now),
        )

    # Create analysis run
    c.execute(
        """
        INSERT INTO analysis_runs (run_id, started_at, status, run_seed, config_json, n_contracts)
        VALUES (?, ?, 'QUEUED', ?, ?, ?)
        """,
        (job_id, now, body.run_seed,
         f'{{"calibration_profile": "{body.calibration_profile}"}}',
         len(body.contracts)),
    )
    conn.commit()
    conn.close()

    logger.info(f"Analysis job {job_id} queued: {len(body.contracts)} contracts",
                extra={"client": client["client_name"]})

    return AnalyzeResponse(
        job_id=job_id,
        status="queued",
        contract_count=len(body.contracts),
        message=f"Queued {len(body.contracts)} contract(s) for analysis. Poll GET /v2/results/{job_id} for results.",
    )


@router.get("/results/{job_id}", response_model=JobResult)
async def get_results(
    job_id: str,
    client: dict = Depends(require_bearer_token),
):
    """Poll for analysis job results."""
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (job_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    row_dict = dict(row)
    result_data = None

    if row_dict.get("status") == "COMPLETED":
        # Fetch scored contracts for this run
        c.execute(
            """
            SELECT cs.contract_id, cs.fraud_tier, cs.confidence_score,
                   cs.triage_priority, cs.markup_pct, cs.bayesian_posterior
            FROM contract_scores cs WHERE cs.run_id = ?
            ORDER BY cs.triage_priority ASC
            """,
            (job_id,),
        )
        scores = [dict(r) for r in c.fetchall()]
        summary = row_dict.get("summary_json")
        result_data = {
            "scores": scores,
            "summary": summary,
            "n_scored": row_dict.get("n_scored", 0),
            "n_errors": row_dict.get("n_errors", 0),
        }

    conn.close()

    # Map status to progress
    status = row_dict.get("status", "UNKNOWN")
    progress_map = {"QUEUED": 0, "RUNNING": 50, "COMPLETED": 100, "FAILED": 0, "ABORTED": 0}

    return JobResult(
        job_id=job_id,
        status=status,
        progress_pct=progress_map.get(status, 0),
        progress_msg=f"Job {status.lower()}",
        created_at=row_dict.get("started_at"),
        completed_at=row_dict.get("completed_at"),
        result=result_data,
    )


@router.get("/vendor/{vendor_id}/profile", response_model=VendorProfileResponse)
async def get_vendor_profile(
    vendor_id: str,
    client: dict = Depends(require_bearer_token),
):
    """Get vendor intelligence report.

    vendor_id is the vendor name (URL-encoded if necessary).
    """
    from vendor_intelligence import build_vendor_profile

    try:
        profile = build_vendor_profile(DB_PATH, vendor_id)
    except Exception as e:
        logger.error(f"Error building vendor profile for {vendor_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error building vendor profile: {e}")

    if profile.contract_count == 0:
        raise HTTPException(status_code=404, detail=f"No contracts found for vendor: {vendor_id}")

    return VendorProfileResponse(**profile.to_dict())


@router.get("/case/{contract_id}/package", response_model=CasePackageResponse)
async def get_case_package(
    contract_id: str,
    client: dict = Depends(require_bearer_token),
):
    """Get full evidence package for a flagged contract."""
    from case_builder import build_case_package

    try:
        pkg = build_case_package(DB_PATH, contract_id)
    except Exception as e:
        logger.error(f"Error building case package for {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error building case package: {e}")

    if not pkg.contract_metadata:
        raise HTTPException(status_code=404, detail=f"Contract not found: {contract_id}")

    resp = pkg.to_dict()
    resp["markdown"] = pkg.to_markdown()
    return CasePackageResponse(**resp)


@router.post("/triage", response_model=TriageResponse)
async def triage_contracts(
    body: TriageRequest,
    client: dict = Depends(require_bearer_token),
):
    """Submit flagged contracts and get a prioritized list back."""
    from priority_queue import triage_from_list

    contract_dicts = [c.model_dump() for c in body.contracts]
    prioritized = triage_from_list(contract_dicts)

    items = [
        TriageItemResponse(
            rank=item.rank,
            contract_id=item.contract_id,
            vendor_name=item.vendor_name,
            agency_name=item.agency_name,
            award_amount=item.award_amount,
            fraud_tier=item.fraud_tier,
            priority_score=item.priority_score,
            expected_fraud_value=item.expected_fraud_value,
            data_completeness=item.data_completeness,
            complexity_estimate=item.complexity_estimate,
            recommended_action=item.recommended_action,
        )
        for item in prioritized
    ]

    return TriageResponse(count=len(items), items=items)
