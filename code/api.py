"""
SUNLIGHT HTTP API Layer
========================

Exposes SUNLIGHT's structural procurement integrity analysis as a REST API.

This module transforms SUNLIGHT from a Python library into a service that
external systems can call via HTTP to analyze contracts and receive structural
findings. It is designed for integration into institutional pipelines (UNDP,
World Bank, regional development banks, national audit offices) and exposes
five endpoints:

- POST /analyze — Single contract analysis with jurisdiction calibration
- POST /batch — Batch contract analysis (up to 1000 contracts)
- GET /health — Service health and readiness check
- GET /version — Deployment metadata and MJPIS version
- GET /profiles — List available jurisdiction profiles

The API auto-generates OpenAPI documentation at /docs and /openapi.json —
these are the institutional integration artifacts that UNDP developers will
reference when integrating SUNLIGHT into their procurement pipelines.

AUTHENTICATION AND AUTHORIZATION:
This module deliberately does NOT implement authentication or authorization.
The API is designed for localhost/private-network deployment only. Production
deployments MUST add an authentication/authorization layer (OAuth2, API keys,
mTLS, or institutional SSO) at the reverse proxy or gateway level BEFORE any
public exposure. Without that layer, this API is NOT production-ready.

Example deployment architecture:
    Internet → Institutional Gateway (auth + rate limiting)
           → SUNLIGHT API (localhost:8765)
           → SUNLIGHT pipeline

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 0.1.0
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# SUNLIGHT core imports
from sunlight_core import (
    ContractDossier,
    SunlightPipeline,
    PipelineStage,
    StructuralVerdict,
    GateVerdict,
    ExecutionMode,
)
from jurisdiction_profile import US_FEDERAL, UK_CENTRAL_GOVERNMENT, JurisdictionProfile
from global_parameters import MJPIS_DRAFT_V0, list_global_parameters
from tca_rules import TCAGraphRuleEngineAdapter
from tca_analyzer import TCAStructureEngineAdapter


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════


class ContractInput(BaseModel):
    """
    Flexible JSON representation of a contract.

    Accepts canonical OCDS release package shape. The structure is deliberately
    flexible to accommodate different OCDS publisher formats while maintaining
    the core required fields for structural analysis.
    """
    ocid: str = Field(..., description="OCDS contract identifier (required)")
    buyer: Optional[Dict[str, Any]] = Field(None, description="Buyer information")
    tender: Optional[Dict[str, Any]] = Field(None, description="Tender details including value, currency, method")
    awards: Optional[List[Dict[str, Any]]] = Field(None, description="Award information")
    parties: Optional[List[Dict[str, Any]]] = Field(None, description="All involved parties")
    planning: Optional[Dict[str, Any]] = Field(None, description="Planning phase data")
    contracts: Optional[List[Dict[str, Any]]] = Field(None, description="Contract phase data")
    language: str = Field("en", description="Language code")


class AnalyzeRequest(BaseModel):
    """Single contract analysis request."""
    contract: ContractInput = Field(..., description="Contract to analyze")
    profile: str = Field(
        "us_federal",
        description="Jurisdiction profile name (e.g., 'us_federal', 'uk_central_government')"
    )
    include_graph: bool = Field(
        False,
        description="Include full TCA structural graph in response (for debugging)"
    )


class BatchAnalyzeRequest(BaseModel):
    """Batch contract analysis request."""
    contracts: List[ContractInput] = Field(..., description="List of contracts to analyze")
    profile: str = Field("us_federal", description="Jurisdiction profile for all contracts")


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════


class Contradiction(BaseModel):
    """One structural contradiction finding."""
    rule_id: str
    severity: str
    description: str
    evidence: str
    legal_citations: List[str]


class StructuralFindings(BaseModel):
    """Structural analysis portion of result."""
    confidence: float = Field(..., description="Structural confidence (0-1)")
    verdict: str = Field(..., description="SOUND, CONCERN, COMPROMISED, or CRITICAL")
    contradictions: List[Contradiction] = Field(
        default_factory=list,
        description="REMOVES edges (structural contradictions)"
    )
    feedback_traps: List[str] = Field(
        default_factory=list,
        description="Self-reinforcing loops detected"
    )


class AnalyzeResponse(BaseModel):
    """Full analysis result for a single contract."""
    ocid: str
    stage: str = Field(..., description="Final pipeline stage reached")
    profile_used: str
    structure: Optional[StructuralFindings] = None
    gate_verdict: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    processing_time_ms: float


class BatchAnalyzeResponse(BaseModel):
    """Batch analysis results with aggregate statistics."""
    results: List[AnalyzeResponse]
    total_processed: int
    total_errors: int
    verdict_distribution: Dict[str, int]


class HealthResponse(BaseModel):
    """Service health check response."""
    status: str
    version: str
    profiles_available: int
    timestamp: str


class VersionResponse(BaseModel):
    """Deployment metadata response."""
    sunlight_version: str
    mjpis_version: str
    profiles: List[str]
    api_version: str = "v1"


class ProfileListResponse(BaseModel):
    """Jurisdiction profile listing response."""
    profiles: List[Dict[str, Any]]


# ═══════════════════════════════════════════════════════════════════════════
# FASTAPI APP INSTANCE
# ═══════════════════════════════════════════════════════════════════════════


app = FastAPI(
    title="SUNLIGHT — Procurement Integrity Analysis API",
    description=(
        "REST API for SUNLIGHT's structural procurement integrity analysis engine. "
        "Exposes multi-jurisdiction contract analysis with topological contradiction "
        "detection (TCA), statistical risk indicators (CRI), and evidence verification "
        "gates (EVG). Designed for integration into institutional procurement pipelines "
        "(UNDP, World Bank, regional development banks, national audit offices). "
        "Returns explainable, tiered risk assessments with full legal citations and "
        "investigation-ready evidence packages."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════


# Registry of available jurisdiction profiles
_PROFILE_REGISTRY: Dict[str, JurisdictionProfile] = {
    "us_federal": US_FEDERAL,
    "uk_central_government": UK_CENTRAL_GOVERNMENT,
}


def get_profile(profile_name: str) -> JurisdictionProfile:
    """Load jurisdiction profile by name."""
    if profile_name not in _PROFILE_REGISTRY:
        available = ", ".join(sorted(_PROFILE_REGISTRY.keys()))
        raise ValueError(
            f"Profile '{profile_name}' not found. Available: {available}"
        )
    return _PROFILE_REGISTRY[profile_name]


def list_profiles() -> List[str]:
    """List all registered profile names."""
    return sorted(_PROFILE_REGISTRY.keys())


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════


def ocds_to_dict(contract: ContractInput) -> Dict:
    """Convert ContractInput Pydantic model to dict for pipeline ingestion."""
    return {
        "ocid": contract.ocid,
        "buyer": contract.buyer or {},
        "tender": contract.tender or {},
        "awards": contract.awards or [],
        "parties": contract.parties or [],
        "planning": contract.planning or {},
        "contracts": contract.contracts or [],
        "language": contract.language,
    }


def structural_result_to_findings(dossier: ContractDossier) -> Optional[StructuralFindings]:
    """Convert ContractDossier.structure to StructuralFindings Pydantic model."""
    if dossier.structure is None:
        return None

    # Convert contradictions to Contradiction models
    contradictions = []
    for c in dossier.structure.contradictions:
        contradictions.append(Contradiction(
            rule_id=c.get("rule_id", ""),
            severity=c.get("severity", "unknown"),
            description=c.get("description", ""),
            evidence=c.get("evidence", ""),
            legal_citations=c.get("legal_citations", []),
        ))

    # Convert feedback traps to string descriptions
    feedback_traps = [str(trap) for trap in dossier.structure.feedback_traps]

    return StructuralFindings(
        confidence=dossier.structure.confidence,
        verdict=dossier.structure.verdict.value,  # Convert enum to string
        contradictions=contradictions,
        feedback_traps=feedback_traps,
    )


def create_analysis_pipeline(profile: JurisdictionProfile) -> SunlightPipeline:
    """
    Construct a SUNLIGHT v4 pipeline with TCA engines wired for the
    specified jurisdiction profile.

    The grapher is instantiated with the profile so that jurisdiction-
    specific rule calibration (fiscal calendar, competitive thresholds,
    legal citations) flows into the structural analysis. The structure
    engine is jurisdiction-agnostic and uses the rule output from the
    grapher.

    Gate engine (EVG) wiring is deferred to a future sub-task — the
    response returns gate_verdict=None until EVG is integrated.
    """
    return SunlightPipeline(
        grapher=TCAGraphRuleEngineAdapter(profile=profile),
        structure=TCAStructureEngineAdapter(),
    )


def get_git_commit() -> str:
    """Get current git commit hash if available."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


@app.get("/")
async def root():
    """Root endpoint — points to API documentation."""
    return {
        "service": "SUNLIGHT Procurement Integrity Analysis API",
        "version": "0.1.0",
        "documentation": "/docs",
        "openapi_spec": "/openapi.json",
        "health_check": "/health",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_contract(request: AnalyzeRequest):
    """
    Analyze a single contract with jurisdiction calibration.

    Runs the full SUNLIGHT pipeline (ingestion, normalization, TCA graph
    construction, structural analysis, evidence gating) and returns tiered
    risk assessment with legal citations and investigation-ready evidence.

    The profile parameter selects the jurisdiction calibration (fiscal calendar,
    competitive thresholds, legal framework citations, evidentiary standards).
    """
    # Validate profile exists
    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Convert contract input to OCDS dict
    raw_ocds = ocds_to_dict(request.contract)

    # Create pipeline and process
    pipeline = create_analysis_pipeline(profile)
    t0 = time.perf_counter()

    try:
        # Ingest contract as dossier
        dossier = pipeline.ingest(raw_ocds, mode=ExecutionMode.BATCH)

        # Process through pipeline
        dossier = pipeline.process(dossier)

        processing_time_ms = (time.perf_counter() - t0) * 1000

        # Convert structure to findings model
        structure = structural_result_to_findings(dossier)

        # Extract gate verdict if available
        gate_verdict = None
        if dossier.gate:
            gate_verdict = dossier.gate.verdict.value

        # Extract errors
        errors = [e.get("error", str(e)) for e in dossier.errors]

        # Check if pipeline reached structural stage
        if dossier.structure is None and not errors:
            errors.append(f"Pipeline did not reach structural analysis stage (stopped at {dossier.stage.value})")

        return AnalyzeResponse(
            ocid=dossier.ocid,
            stage=dossier.stage.value,
            profile_used=request.profile,
            structure=structure,
            gate_verdict=gate_verdict,
            errors=errors,
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Contract analysis failed: {str(e)}"
        )


@app.post("/batch", response_model=BatchAnalyzeResponse)
async def batch_analyze(request: BatchAnalyzeRequest):
    """
    Analyze multiple contracts in batch with jurisdiction calibration.

    Maximum batch size: 1000 contracts. Returns individual analysis results
    plus aggregate statistics (verdict distribution, total errors).
    """
    # Enforce batch size limit
    if len(request.contracts) > 1000:
        raise HTTPException(
            status_code=413,
            detail=f"Batch size {len(request.contracts)} exceeds maximum of 1000 contracts"
        )

    # Validate profile exists
    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Process each contract
    results = []
    total_errors = 0
    verdict_counts: Dict[str, int] = {}

    # Create pipeline once for the entire batch (all contracts share the same profile)
    pipeline = create_analysis_pipeline(profile)

    for contract in request.contracts:
        raw_ocds = ocds_to_dict(contract)
        t0 = time.perf_counter()

        try:
            dossier = pipeline.ingest(raw_ocds, mode=ExecutionMode.BATCH)
            dossier = pipeline.process(dossier)

            processing_time_ms = (time.perf_counter() - t0) * 1000

            structure = structural_result_to_findings(dossier)
            gate_verdict = dossier.gate.verdict.value if dossier.gate else None
            errors = [e.get("error", str(e)) for e in dossier.errors]

            # Check if pipeline reached structural stage
            if dossier.structure is None and not errors:
                errors.append(f"Pipeline did not reach structural analysis stage (stopped at {dossier.stage.value})")

            if errors:
                total_errors += 1

            # Count verdicts for distribution
            if structure:
                verdict_counts[structure.verdict] = verdict_counts.get(structure.verdict, 0) + 1

            results.append(AnalyzeResponse(
                ocid=dossier.ocid,
                stage=dossier.stage.value,
                profile_used=request.profile,
                structure=structure,
                gate_verdict=gate_verdict,
                errors=errors,
                processing_time_ms=processing_time_ms,
            ))

        except Exception as e:
            # Record error but continue processing other contracts
            total_errors += 1
            results.append(AnalyzeResponse(
                ocid=contract.ocid,
                stage="failed",
                profile_used=request.profile,
                structure=None,
                gate_verdict=None,
                errors=[f"Processing failed: {str(e)}"],
                processing_time_ms=(time.perf_counter() - t0) * 1000,
            ))

    return BatchAnalyzeResponse(
        results=results,
        total_processed=len(request.contracts),
        total_errors=total_errors,
        verdict_distribution=verdict_counts,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """
    Service health and readiness check.

    Returns 200 OK if the service is operational. Never raises exceptions —
    degraded states are indicated via status field ("ok" or "degraded").
    """
    try:
        profiles_count = len(list_profiles())

        return HealthResponse(
            status="ok",
            version="0.1.0",
            profiles_available=profiles_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        # Service is running but degraded
        return HealthResponse(
            status="degraded",
            version="0.1.0",
            profiles_available=0,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@app.get("/version", response_model=VersionResponse)
async def version():
    """
    Deployment metadata and version information.

    Returns SUNLIGHT version, MJPIS version, git commit (if available),
    and list of registered jurisdiction profiles.
    """
    git_commit = get_git_commit()
    sunlight_version = f"4.0.0+{git_commit}"

    return VersionResponse(
        sunlight_version=sunlight_version,
        mjpis_version=MJPIS_DRAFT_V0.version,
        profiles=list_profiles(),
        api_version="v1",
    )


@app.get("/profiles", response_model=ProfileListResponse)
async def profiles():
    """
    List all available jurisdiction profiles with key metadata.

    Returns profile names, country codes, currencies, fiscal year ends,
    and descriptions for all registered jurisdiction calibrations.
    """
    profile_list = []

    for name, profile in _PROFILE_REGISTRY.items():
        profile_list.append({
            "name": name,
            "country_code": profile.country_code,
            "currency": profile.currency,
            "fiscal_year_end": f"{profile.fiscal_year_end_month}/{profile.fiscal_year_end_day}",
            "description": profile.description or f"Jurisdiction profile for {profile.country_code}",
        })

    return ProfileListResponse(profiles=profile_list)


# ═══════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════


@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "detail": str(exc.detail) if hasattr(exc, "detail") else "Resource not found",
            "documentation": "/docs",
        }
    )
