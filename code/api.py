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

import os
import subprocess
import time
from datetime import date, datetime, timezone
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
from global_parameters import MJPIS_DRAFT_V0, list_global_parameters, get_global_parameters
from evg import gate as evg_gate
from tca_rules import TCAGraphRuleEngineAdapter
from tca_analyzer import TCAStructureEngineAdapter
from calibration_store import EmpiricalCalibrationStore, BatchObservation
from input_adapters import build_default_registry
from sunlight_logging import get_logger

# SUNLIGHT Side 2 imports
from delivery_schema import (
    DeliveryDossier,
    DeliveryVerdict,
    DeliveryDimension,
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
)
from delivery_analyzer import DeliveryAnalyzer
from alerts import (
    AlertPriority,
    IntelligenceAlert,
    RuleCitation,
    TriageBrief,
    assemble_summary,
    assemble_recommended_action,
    assemble_triage_brief,
    compute_priority,
)
from alert_emitter import AlertConfiguration, LogEmitter
from alert_integration import AlertAssembler, AlertIntegration

# SUNLIGHT Side 4 imports
from recovery_ledger import RecoveryLedger, RecoveryRecord, RecoveryStatus, InvalidTransitionError
from cpd_allocation import (
    compute_gap_weighted_allocation,
    load_cpd_profile,
    load_cpd_profile_from_dict,
    CountryProgrammeProfile,
)
from redirection import RedirectionRecord, RedirectionRegistry
from impact_report import assemble_impact_report

logger = get_logger("api")


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
    input_format: Optional[str] = Field(
        default=None,
        description=(
            "Optional explicit input format specifier. When provided, SUNLIGHT "
            "uses the named adapter to convert the payload to canonical OCDS shape. "
            "When None (default), automatic routing detects the format by shape. "
            "Supported formats: 'ocds_release', 'undp_quantum', 'undp_compass'. "
            "Quantum and Compass adapters are placeholders pending schema integration."
        )
    )


class BatchAnalyzeRequest(BaseModel):
    """Batch contract analysis request."""
    contracts: List[ContractInput] = Field(..., description="List of contracts to analyze")
    profile: str = Field("us_federal", description="Jurisdiction profile for all contracts")
    capacity_budget: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Optional analyst investigation capacity for this batch. When "
            "provided, SUNLIGHT will recommend at most capacity_budget contracts "
            "for investigation, selected as the highest-risk contracts in the "
            "batch that also clear the statistical precision floor. When None, "
            "no capacity ceiling is applied and all contracts clearing the "
            "statistical floor are recommended. Must be a non-negative integer."
        ),
    )
    input_format: Optional[str] = Field(
        default=None,
        description=(
            "Optional explicit input format specifier. When provided, SUNLIGHT "
            "uses the named adapter to convert all payloads to canonical OCDS shape. "
            "When None (default), automatic routing detects the format by shape. "
            "Supported formats: 'ocds_release', 'undp_quantum', 'undp_compass'. "
            "Quantum and Compass adapters are placeholders pending schema integration."
        )
    )


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════


def _band_cutoffs_from_env():
    """Band cutoffs for this deployment.

    Read from the environment so an institution sets its own lines without a
    code change or a redeploy of the image. Invalid values fall back to the
    documented defaults with a warning rather than failing the request —
    a misconfigured cutoff must not take the analysis endpoint down.
    """
    from structural_scoring import DEFAULT_CUTOFFS, BandCutoffs

    raw_green = os.environ.get("SUNLIGHT_BAND_GREEN_BELOW")
    raw_red = os.environ.get("SUNLIGHT_BAND_RED_AT_OR_ABOVE")
    if raw_green is None and raw_red is None:
        return DEFAULT_CUTOFFS

    try:
        cutoffs = BandCutoffs(
            green_below=float(raw_green) if raw_green is not None
            else DEFAULT_CUTOFFS.green_below,
            red_at_or_above=float(raw_red) if raw_red is not None
            else DEFAULT_CUTOFFS.red_at_or_above,
        )
    except (TypeError, ValueError):
        logger.warning("Invalid band cutoff environment values; using defaults")
        return DEFAULT_CUTOFFS

    problems = cutoffs.validate()
    if problems:
        logger.warning(f"Band cutoffs rejected ({'; '.join(problems)}); using defaults")
        return DEFAULT_CUTOFFS
    return cutoffs


def _build_structural_scoring(
    structure,
    dossier=None,
    profile_name: str = "",
    isolation: bool = False,
) -> Optional[Dict[str, Any]]:
    """Three-tier scoring over already-attributed findings.

    Determinacy is derived from the SAME feature extraction the rules use
    (tca_rules._extract), so what the output calls assessable cannot drift
    from what the rules actually read. Deriving it independently would be a
    second source of truth about the same question.

    Never raises into the response path. This is an output layer, and a
    failure to re-express findings must not take down an analysis that
    otherwise succeeded — the verdict does not depend on it.
    """
    if structure is None:
        return None
    try:
        from structural_scoring import corpus_stamp, score_findings

        findings = [c.model_dump() for c in (structure.contradictions or [])]

        features = None
        if dossier is not None:
            try:
                from tca_rules import _extract
                features = _extract(dossier)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Feature extraction for determinacy failed: {e}")

        comparables = list(getattr(dossier, "comparables", None) or []) if dossier else []
        profile_obj = None
        try:
            profile_obj = get_profile(profile_name) if profile_name else None
        except ValueError:
            profile_obj = None

        stamp = corpus_stamp(
            comparable_count=len(comparables),
            comparable_ids=[str(x) for x in comparables],
            profile_name=profile_name,
            profile_version=getattr(profile_obj, "global_params_version", ""),
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

        return score_findings(
            findings,
            cutoffs=_band_cutoffs_from_env(),
            features=features,
            stamp=stamp,
            isolation=isolation,
        )
    except Exception as e:  # noqa: BLE001 — logged, never surfaced as a 500
        logger.error(f"Structural scoring failed (analysis unaffected): {e}")
        return None


_RULE_REGISTRY_CACHE: Optional[Dict[str, Any]] = None


def _rule_registry() -> Dict[str, Any]:
    """rule_id -> Rule, built once. Lazy, mirroring tca_analyzer's deferred import.

    Imported inside the function because tca_rules pulls in the jurisdiction
    layer; tca_analyzer defers it for the same reason.
    """
    global _RULE_REGISTRY_CACHE
    if _RULE_REGISTRY_CACHE is None:
        try:
            from tca_rules import RULES
            _RULE_REGISTRY_CACHE = {r.rule_id: r for r in RULES}
        except ImportError:
            logger.error("Failed to import RULES from tca_rules for finding attribution")
            _RULE_REGISTRY_CACHE = {}
    return _RULE_REGISTRY_CACHE


def _build_contradiction(finding: dict, severity: str) -> "Contradiction":
    """Attribute one engine finding to its rule.

    The engine writes `rule`; this reads `rule` and falls back to `rule_id`
    so a future engine change to the canonical name cannot silently
    re-break attribution.

    `evidence` (the citation, as the engine names it) is looked up from the
    registry when the finding does not carry it, so a citation is present
    even if the engine's inline copy is ever dropped.
    """
    rule_id = finding.get("rule") or finding.get("rule_id") or ""
    rule = _rule_registry().get(rule_id)

    citation = finding.get("evidence") or (getattr(rule, "evidence", "") if rule else "")
    observed = finding.get("description", "")

    return Contradiction(
        rule_id=rule_id,
        rule_name=getattr(rule, "name", "") if rule else "",
        layer=getattr(rule, "layer", "") if rule else "",
        severity=severity,
        description=observed,
        evidence=observed,
        legal_citation=citation,
        legal_citations=[citation] if citation else [],
    )


class Contradiction(BaseModel):
    """One structural finding, fully attributed to the rule that produced it.

    Field semantics, corrected. The engine emits findings keyed `rule`,
    `description` (the observed fact) and `evidence` (the legal citation).
    This model previously read `rule_id`, which the engine never writes, so
    every response carried an empty rule id, an "unknown" severity and an
    empty citation list — the system's "every flag traces to a rule, every
    rule traces to a legal citation" property was not observable through the
    API at all.

    `evidence` now carries the OBSERVED FACT and `legal_citation` the
    statutory basis, which is how Sides 2, 3 and 5 have always named these
    two things. Side 1 was the outlier. `description` is unchanged.
    """
    rule_id: str = Field(..., description="Rule that produced this finding, e.g. PROC-001")
    rule_name: str = Field("", description="Human-readable rule name from the registry")
    layer: str = Field("", description="TCA rule layer: procurement, entity, financial, temporal, network")
    severity: str = Field(..., description="high (contradiction) or medium (unproven dependency)")
    description: str = Field(..., description="What was found, in the analyst's terms")
    evidence: str = Field(..., description="The observed fact supporting this finding")
    legal_citation: str = Field("", description="Statutory/regulatory basis for this rule")
    legal_citations: List[str] = Field(default_factory=list, description="Citations as a list")


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


class EVGDimensionResult(BaseModel):
    """Result of evaluating a single EVG dimension."""
    dimension: str = Field(..., description="Dimension name (cri_markup, cri_bribery_channel, tca_typologies)")
    fired: bool = Field(..., description="Whether this dimension exceeded its threshold")
    observed_value: Optional[float] = Field(None, description="Observed value for this dimension")
    threshold: Optional[float] = Field(None, description="MJPIS-derived threshold for this dimension")
    detail: str = Field(..., description="Human-readable explanation of the evaluation")


class EVGGateOutcome(BaseModel):
    """Full EVG gate outcome with per-dimension traceability."""
    verdict: str = Field(..., description="Evidence verdict: green, yellow, or red")
    dimensions_fired: int = Field(..., description="Number of dimensions that exceeded their threshold")
    dimension_results: List[EVGDimensionResult] = Field(
        ..., description="Per-dimension evaluation results"
    )
    global_params_version: str = Field(..., description="Global parameters version used for thresholds")
    methodology_note: str = Field("", description="Methodology description")


class AnalyzeResponse(BaseModel):
    """Full analysis result for a single contract."""
    ocid: str
    stage: str = Field(..., description="Final pipeline stage reached")
    profile_used: str
    structure: Optional[StructuralFindings] = None
    gate_verdict: Optional[str] = Field(
        None,
        description="EVG evidence verdict: green, yellow, or red"
    )
    gate_outcome: Optional[EVGGateOutcome] = Field(
        None,
        description=(
            "Full EVG gate outcome with per-dimension traceability. "
            "Contains the verdict, count of dimensions fired, and detailed "
            "per-dimension results showing observed values versus MJPIS thresholds."
        ),
    )
    structural_scoring: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Three-tier structural scoring: a composite 0-1 score, the four "
            "sub-scores it averages, the interpretation band under the "
            "institution's configured cutoffs, and every finding's "
            "correspondence to the Fazekas CRI seven-flag index. Additive — "
            "an output layer over findings the engines already produced, "
            "consulted by no verdict. Always present, whether or not any "
            "band cutoff is crossed."
        ),
    )
    errors: List[str] = Field(default_factory=list)
    processing_time_ms: float
    recommended_for_investigation: bool = Field(
        default=False,
        description=(
            "True when this contract clears both the statistical threshold "
            "(structural verdict at or above CONCERN) and the capacity-calibrated "
            "threshold for the batch it was analyzed in. For single-contract "
            "analysis via POST /analyze, this field reflects only the statistical "
            "threshold since no batch capacity context exists."
        ),
    )


class BatchAnalyzeResponse(BaseModel):
    """Batch analysis results with aggregate statistics."""
    results: List[AnalyzeResponse]
    total_processed: int
    total_errors: int
    verdict_distribution: Dict[str, int]
    threshold_metadata: dict = Field(
        default_factory=dict,
        description=(
            "Metadata describing the thresholds applied to this batch. "
            "Contains: statistical_threshold (float, the minimum risk score "
            "for investigation recommendation), capacity_budget (Optional[int], "
            "the requested capacity or None), capacity_threshold (Optional[float], "
            "the computed risk score quantile corresponding to capacity or None "
            "if no capacity specified), binding_threshold (float, the actual "
            "threshold applied, equal to max(statistical, capacity)), "
            "recommended_count (int, the number of contracts recommended for "
            "investigation in this batch)."
        ),
    )


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


class CalibrationStateResponse(BaseModel):
    """Empirical calibration state response."""
    profile_name: str
    total_contracts_analyzed: int
    verdict_counts: Dict[str, int]
    rule_fire_counts: Dict[str, int]
    mean_risk_score: Optional[float]
    variance_risk_score: Optional[float]
    risk_score_min: Optional[float]
    risk_score_max: Optional[float]
    first_observation_utc: Optional[str]
    last_observation_utc: Optional[str]
    schema_version: str


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
# EMPIRICAL CALIBRATION STORE
# ═══════════════════════════════════════════════════════════════════════════


# Module-level calibration store instance (shared across all requests)
calibration_store = EmpiricalCalibrationStore(base_dir="calibration")


# ═══════════════════════════════════════════════════════════════════════════
# INPUT FORMAT ADAPTER REGISTRY
# ═══════════════════════════════════════════════════════════════════════════


# Module-level adapter registry instance (shared across all requests)
_input_registry = build_default_registry()


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


# Default statistical threshold for recommending a contract for investigation.
# A risk score of 2.0 corresponds to the CONCERN verdict floor (verdict_rank=2.0,
# confidence=0.0). Contracts below this threshold are not flagged regardless of
# capacity pressure, because the statistical precision floor cannot be violated
# by operational shortage of analyst capacity.
DEFAULT_STATISTICAL_THRESHOLD: float = 2.0


def compute_risk_score(verdict: str, confidence: float) -> float:
    """
    Compute a scalar risk score for ranking contracts within a batch.

    The score combines the structural verdict (primary) with confidence
    (secondary tiebreaker). Higher scores indicate higher integrity risk.

    Verdict contributes the integer part of the score:
        critical    = 4.0
        compromised = 3.0
        concern     = 2.0
        sound       = 1.0
        unknown     = 0.0

    Confidence contributes up to 1.0 as a tiebreaker within verdicts,
    so the final score falls in approximately [0.0, 5.0].
    """
    verdict_ranks = {
        "critical": 4.0,
        "compromised": 3.0,
        "concern": 2.0,
        "sound": 1.0,
        "unknown": 0.0,
    }
    return verdict_ranks.get(verdict.lower(), 0.0) + max(0.0, min(1.0, confidence))


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

    # Convert contradictions to Contradiction models.
    #
    # SEVERITY IS DERIVED, and derived from the graph rather than invented.
    # The registry carries no severity field, so rather than author per-rule
    # weights the API has no basis for, severity reports the finding CLASS:
    # a contradiction is a REMOVES edge (the structure actively conflicts) and
    # an unproven dependency is a SEEKS edge (a required relationship is not
    # evidenced). Those are engine facts, not editorial judgement.
    contradictions = [
        _build_contradiction(c, "high") for c in dossier.structure.contradictions
    ]

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

    The EVG (Evidence Verification Gate) runs after the pipeline produces
    the dossier — it is called separately in the endpoint handlers, not
    as a pipeline engine, because it consumes GlobalParameters directly.
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

    # Route payload through input adapter
    try:
        if request.input_format:
            # Explicit adapter selection by format name
            adapter = _input_registry.get(request.input_format)
        else:
            # Automatic adapter routing by payload shape
            adapter = _input_registry.route(raw_ocds)

        canonical_ocds = adapter.to_canonical_ocds(raw_ocds)
    except (ValueError, KeyError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Input format adapter error: {str(e)}"
        )

    # Create pipeline and process
    pipeline = create_analysis_pipeline(profile)
    t0 = time.perf_counter()

    try:
        # Ingest contract as dossier
        dossier = pipeline.ingest(canonical_ocds, mode=ExecutionMode.BATCH)

        # Process through pipeline
        dossier = pipeline.process(dossier)

        processing_time_ms = (time.perf_counter() - t0) * 1000

        # Convert structure to findings model
        structure = structural_result_to_findings(dossier)

        # Run EVG gate against MJPIS thresholds
        global_params = get_global_parameters(profile.global_params_version)
        evg_outcome = evg_gate(dossier.price, dossier.structure, global_params)
        gate_verdict = evg_outcome.verdict.value
        gate_outcome = EVGGateOutcome(
            verdict=evg_outcome.verdict.value,
            dimensions_fired=evg_outcome.dimensions_fired,
            dimension_results=[
                EVGDimensionResult(
                    dimension=dr.dimension.value,
                    fired=dr.fired,
                    observed_value=dr.observed_value,
                    threshold=dr.threshold,
                    detail=dr.detail,
                )
                for dr in evg_outcome.dimension_results
            ],
            global_params_version=evg_outcome.global_params_version,
            methodology_note=evg_outcome.methodology_note,
        )

        # Extract errors
        errors = [e.get("error", str(e)) for e in dossier.errors]

        # Check if pipeline reached structural stage
        if dossier.structure is None and not errors:
            errors.append(f"Pipeline did not reach structural analysis stage (stopped at {dossier.stage.value})")

        # Compute risk score and determine recommendation (statistical threshold only)
        recommended = False
        if structure:
            risk_score = compute_risk_score(structure.verdict, structure.confidence)
            recommended = risk_score >= DEFAULT_STATISTICAL_THRESHOLD

        return AnalyzeResponse(
            ocid=dossier.ocid,
            stage=dossier.stage.value,
            profile_used=request.profile,
            structure=structure,
            gate_verdict=gate_verdict,
            gate_outcome=gate_outcome,
            # isolation=True: POST /analyze is a single contract with no
            # comparison set, and the output must announce that rather than
            # let a consumer assume corpus context it never had.
            structural_scoring=_build_structural_scoring(
                structure, dossier=dossier, profile_name=request.profile,
                isolation=not bool(getattr(dossier, "comparables", None))),
            errors=errors,
            processing_time_ms=processing_time_ms,
            recommended_for_investigation=recommended,
        )

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Contract analysis failed: {str(e)}"
        )


@app.post("/batch", response_model=BatchAnalyzeResponse)
async def batch_analyze(request: BatchAnalyzeRequest):
    """
    Analyze multiple contracts in batch with jurisdiction calibration and
    capacity-calibrated thresholds.

    Maximum batch size: 1000 contracts. Returns individual analysis results
    plus aggregate statistics (verdict distribution, total errors, threshold
    metadata).

    When capacity_budget is provided, the batch response includes at most
    capacity_budget contracts recommended for investigation, selected as the
    highest-risk contracts that also clear the statistical precision floor.
    """
    # Enforce batch size limit
    if len(request.contracts) > 1000:
        raise HTTPException(
            status_code=413,
            detail=f"Batch size {len(request.contracts)} exceeds maximum of 1000 contracts"
        )

    # Validate capacity_budget (defense in depth - Pydantic should already validate)
    if request.capacity_budget is not None and request.capacity_budget < 0:
        raise HTTPException(
            status_code=400,
            detail=f"capacity_budget must be non-negative, got {request.capacity_budget}"
        )

    # Validate profile exists
    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # FIRST PASS: Analyze all contracts
    results = []
    total_errors = 0
    verdict_counts: Dict[str, int] = {}

    # Create pipeline once for the entire batch (all contracts share the same profile)
    pipeline = create_analysis_pipeline(profile)
    global_params = get_global_parameters(profile.global_params_version)

    for contract in request.contracts:
        raw_ocds = ocds_to_dict(contract)
        t0 = time.perf_counter()

        try:
            # Route payload through input adapter
            try:
                if request.input_format:
                    adapter = _input_registry.get(request.input_format)
                else:
                    adapter = _input_registry.route(raw_ocds)
                canonical_ocds = adapter.to_canonical_ocds(raw_ocds)
            except (ValueError, KeyError) as e:
                raise Exception(f"Input format adapter error: {str(e)}")

            dossier = pipeline.ingest(canonical_ocds, mode=ExecutionMode.BATCH)
            dossier = pipeline.process(dossier)

            processing_time_ms = (time.perf_counter() - t0) * 1000

            structure = structural_result_to_findings(dossier)

            # Run EVG gate against MJPIS thresholds
            evg_outcome = evg_gate(dossier.price, dossier.structure, global_params)
            gate_verdict = evg_outcome.verdict.value
            gate_outcome = EVGGateOutcome(
                verdict=evg_outcome.verdict.value,
                dimensions_fired=evg_outcome.dimensions_fired,
                dimension_results=[
                    EVGDimensionResult(
                        dimension=dr.dimension.value,
                        fired=dr.fired,
                        observed_value=dr.observed_value,
                        threshold=dr.threshold,
                        detail=dr.detail,
                    )
                    for dr in evg_outcome.dimension_results
                ],
                global_params_version=evg_outcome.global_params_version,
                methodology_note=evg_outcome.methodology_note,
            )

            errors = [e.get("error", str(e)) for e in dossier.errors]

            # Check if pipeline reached structural stage
            if dossier.structure is None and not errors:
                errors.append(f"Pipeline did not reach structural analysis stage (stopped at {dossier.stage.value})")

            if errors:
                total_errors += 1

            # Count verdicts for distribution
            if structure:
                verdict_counts[structure.verdict] = verdict_counts.get(structure.verdict, 0) + 1

            # Add result with placeholder recommended_for_investigation=False
            # (will update in second pass after capacity threshold computation)
            results.append(AnalyzeResponse(
                ocid=dossier.ocid,
                stage=dossier.stage.value,
                profile_used=request.profile,
                structure=structure,
                gate_verdict=gate_verdict,
                gate_outcome=gate_outcome,
                # Populated on the batch path too. The same response model
                # returning a scored result from /analyze and a null from
                # /batch would make the field's meaning depend on which
                # endpoint a consumer happened to call.
                structural_scoring=_build_structural_scoring(
                    structure, dossier=dossier, profile_name=request.profile,
                    isolation=not bool(getattr(dossier, "comparables", None))),
                errors=errors,
                processing_time_ms=processing_time_ms,
                recommended_for_investigation=False,  # Placeholder
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
                recommended_for_investigation=False,
            ))

    # CAPACITY THRESHOLD COMPUTATION
    # Compute risk scores for all contracts
    risk_scores = []
    for r in results:
        if r.structure:
            risk_scores.append(compute_risk_score(r.structure.verdict, r.structure.confidence))
        else:
            risk_scores.append(0.0)  # Failed contracts get minimum score

    # Determine capacity threshold
    capacity_threshold = None
    if request.capacity_budget is None or request.capacity_budget >= len(results):
        # No capacity ceiling: capacity threshold is effectively -inf
        capacity_threshold_value = float('-inf')
    elif request.capacity_budget == 0:
        # Zero capacity: capacity threshold is +inf (nothing recommended)
        capacity_threshold_value = float('inf')
    else:
        # Compute the C-th highest risk score (where C = capacity_budget)
        sorted_scores = sorted(risk_scores, reverse=True)
        capacity_threshold_value = sorted_scores[request.capacity_budget - 1]
        capacity_threshold = capacity_threshold_value  # For metadata reporting

    # Binding threshold is max of statistical and capacity thresholds
    binding_threshold = max(DEFAULT_STATISTICAL_THRESHOLD, capacity_threshold_value)

    # SECOND PASS: Set recommended_for_investigation from the binding threshold.
    #
    # Assigns rather than promotes. The first pass flags against the statistical
    # threshold alone; when a capacity budget raises the binding threshold above
    # it, contracts between the two thresholds must be UNflagged. The previous
    # form only ever set True, so those stayed flagged from the first pass and
    # the capacity ceiling silently did nothing to them — an investigator with
    # capacity for 2 could still be handed everything above the statistical bar.
    #
    # Isolated from the DOJ scoring path: recommended_for_investigation exists
    # only in this module, and neither doj_validation.py nor evaluation.py
    # references it, the /batch endpoint, or capacity_budget. Verdicts,
    # confidence and gate outcomes are untouched by this block.
    recommended_count = 0
    for i, result in enumerate(results):
        recommended = risk_scores[i] >= binding_threshold
        result.recommended_for_investigation = recommended
        if recommended:
            recommended_count += 1

    # Populate threshold metadata
    threshold_metadata = {
        "statistical_threshold": DEFAULT_STATISTICAL_THRESHOLD,
        "capacity_budget": request.capacity_budget,
        "capacity_threshold": capacity_threshold,  # None if no budget, else the quantile
        "binding_threshold": binding_threshold,
        "recommended_count": recommended_count,
    }

    # Update empirical calibration store with observations from this batch
    # (phase one: observation only, not yet consumed in detection path)
    try:
        observations = []
        for i, result in enumerate(results):
            if result.structure:  # Only observe contracts that reached structural analysis
                observations.append(BatchObservation(
                    verdict=result.structure.verdict,
                    confidence=result.structure.confidence,
                    risk_score=risk_scores[i],
                    fired_rule_ids=[c.rule_id for c in result.structure.contradictions],
                ))
        if observations:
            calibration_store.update_from_batch(request.profile, observations)
    except Exception as e:
        # Swallow storage failures — the batch analysis result is the primary
        # product, and the calibration layer is observational metadata. Log
        # the failure so operators can see if the store is broken.
        logger.warning(
            f"Empirical calibration store update failed for profile {request.profile}: {e}",
            exc_info=True
        )

    return BatchAnalyzeResponse(
        results=results,
        total_processed=len(request.contracts),
        total_errors=total_errors,
        verdict_distribution=verdict_counts,
        threshold_metadata=threshold_metadata,
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
        # Service is running but degraded. Log the cause — a health endpoint that
        # reports "degraded" and discards the reason cannot be diagnosed from outside.
        logger.warning(f"Health check degraded: {e}")
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


@app.get("/calibration/{profile_name}", response_model=CalibrationStateResponse)
async def get_calibration_state(profile_name: str):
    """
    Return the current empirical calibration state for a jurisdiction
    profile. The state accumulates observations from every batch analysis
    that has used this profile, providing a live running view of what
    normal looks like in this jurisdiction.

    Returns fresh zero-initialized state if no observations have been
    recorded yet (not a 404) — absence means 'no observations yet', not
    'profile does not exist'. For the latter, clients should check
    GET /profiles.
    """
    state = calibration_store.load(profile_name)
    return CalibrationStateResponse(
        profile_name=state.profile_name,
        total_contracts_analyzed=state.total_contracts_analyzed,
        verdict_counts=state.verdict_counts,
        rule_fire_counts=state.rule_fire_counts,
        mean_risk_score=state.mean_risk_score(),
        variance_risk_score=state.variance_risk_score(),
        risk_score_min=state.risk_score_min,
        risk_score_max=state.risk_score_max,
        first_observation_utc=state.first_observation_utc,
        last_observation_utc=state.last_observation_utc,
        schema_version=state.schema_version,
    )


@app.get("/input-formats")
async def list_input_formats():
    """
    List all registered input format adapters.

    Returns the format names that can be passed to the input_format field
    in POST /analyze and POST /batch requests. Each format name corresponds
    to an adapter that converts source-format payloads to canonical OCDS
    release dict shape.

    Note: 'undp_quantum' and 'undp_compass' are placeholder adapters that
    raise NotImplementedError until the UNDP institutional schemas are
    integrated during Phase B onboarding work.
    """
    formats = _input_registry.list_formats()
    return {
        "available_formats": formats,
        "description": (
            "Input format adapters convert heterogeneous procurement data "
            "formats into canonical OCDS release shape for SUNLIGHT ingestion. "
            "Use the 'input_format' field in analyze/batch requests to select "
            "an adapter explicitly, or omit it for automatic format detection."
        )
    }


# ═══════════════════════════════════════════════════════════════════════════
# SIDE 2: DELIVERY VERIFICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


# ── Pydantic models for delivery endpoints ──

class MilestoneInput(BaseModel):
    """A contractual milestone with planned vs. actual dates."""
    milestone_id: str = Field(..., description="Unique milestone identifier")
    description: str = Field(..., description="Milestone description")
    planned_date: Optional[str] = Field(None, description="Planned completion date (ISO 8601)")
    actual_date: Optional[str] = Field(None, description="Actual completion date (ISO 8601)")
    status: str = Field("", description="Status: completed, delayed, cancelled, pending")
    delay_days: int = Field(0, description="Days of delay (actual - planned)")
    deliverables_due: int = Field(0, description="Number of deliverables expected")
    deliverables_accepted: int = Field(0, description="Number of deliverables accepted")


class ResourceInput(BaseModel):
    """A staffing or resource input record."""
    resource_id: str = Field(..., description="Unique resource identifier")
    role: str = Field(..., description="Role (e.g., project_manager, engineer)")
    planned_fte: float = Field(0.0, description="Planned full-time equivalent")
    actual_fte: float = Field(0.0, description="Actual FTE deployed")
    qualification_required: str = Field("", description="Required qualification")
    qualification_verified: bool = Field(False, description="Whether qualification was verified")
    period_start: Optional[str] = Field(None, description="Assignment start (ISO 8601)")
    period_end: Optional[str] = Field(None, description="Assignment end (ISO 8601)")


class OutcomeInput(BaseModel):
    """A deliverable or output record."""
    outcome_id: str = Field(..., description="Unique outcome identifier")
    description: str = Field(..., description="Deliverable description")
    unit: str = Field("", description="Unit of measure (e.g., km_road, units)")
    quantity_planned: float = Field(0.0, description="Planned quantity")
    quantity_delivered: float = Field(0.0, description="Delivered quantity")
    quality_score: Optional[float] = Field(None, description="Quality score 0.0-1.0")
    inspection_date: Optional[str] = Field(None, description="Inspection date (ISO 8601)")
    inspector_id: str = Field("", description="Inspector identifier")
    defects_noted: int = Field(0, description="Number of defects found")


class FinancialInput(BaseModel):
    """A financial reconciliation line item."""
    line_item_id: str = Field(..., description="Unique line item identifier")
    description: str = Field(..., description="Line item description")
    budgeted_amount: float = Field(0.0, description="Budgeted amount")
    actual_amount: float = Field(0.0, description="Actual amount spent")
    currency: str = Field("USD", description="ISO 4217 currency code")
    variance_pct: float = Field(0.0, description="Variance percentage")
    amendment_count: int = Field(0, description="Number of contract amendments")
    justification: str = Field("", description="Justification for variance")


class DeliveryAnalyzeRequest(BaseModel):
    """Single delivery analysis request."""
    contract_id: str = Field(..., description="Links to Side 1 ContractDossier")
    milestones: List[MilestoneInput] = Field(default_factory=list, description="Milestone records")
    resources: List[ResourceInput] = Field(default_factory=list, description="Resource records")
    outcomes: List[OutcomeInput] = Field(default_factory=list, description="Outcome records")
    financials: List[FinancialInput] = Field(default_factory=list, description="Financial records")
    country_code: str = Field("", description="ISO 3166-1 alpha-2 code")
    country_name: str = Field("", description="Full country name")
    project_name: str = Field("", description="Project identifier")
    procurement_verdict: str = Field("", description="Side 1 EVG verdict (GREEN/YELLOW/RED)")
    profile: str = Field("us_federal", description="Jurisdiction profile name")


class DeliveryBatchRequest(BaseModel):
    """Batch delivery analysis request."""
    deliveries: List[DeliveryAnalyzeRequest] = Field(..., description="Deliveries to analyze")
    profile: str = Field("us_federal", description="Jurisdiction profile for all deliveries")


class DeliveryDimensionResponse(BaseModel):
    """Result of evaluating a single delivery EVG dimension."""
    dimension: str = Field(..., description="Dimension name")
    fired: bool = Field(..., description="Whether this dimension exceeded threshold")
    observed_value: Optional[float] = Field(None, description="Observed value")
    threshold: Optional[float] = Field(None, description="Threshold applied")
    detail: str = Field("", description="Human-readable explanation")


class DeliveryFiredRule(BaseModel):
    """A delivery rule that fired."""
    rule_id: str = Field(..., description="Rule identifier (e.g., DEL-MILE-001)")
    layer: str = Field(..., description="Rule layer (milestone, resource, outcome, financial)")
    evidence: str = Field(..., description="Evidence string")
    legal_basis: str = Field("", description="Legal citation")
    confidence: float = Field(0.0, description="Confidence score")


class DeliveryAnalyzeResponse(BaseModel):
    """Full delivery analysis result."""
    delivery_id: str
    contract_id: str
    verdict: Optional[str] = Field(None, description="Delivery EVG verdict: green, yellow, red")
    stage: str
    dimensions_fired: int = 0
    dimensions: List[DeliveryDimensionResponse] = Field(default_factory=list)
    rules_evaluated: int = 0
    rules_fired: int = 0
    fired_rules: List[DeliveryFiredRule] = Field(default_factory=list)
    layer_summary: Dict[str, int] = Field(default_factory=dict)
    graph_summary: Optional[Dict[str, int]] = None
    delivery_metrics: Dict[str, Any] = Field(default_factory=dict)
    processing_ms: Dict[str, float] = Field(default_factory=dict)
    procurement_verdict: str = ""
    methodology_note: str = ""
    methodology_version: str = ""
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    profile_used: str = ""


class DeliveryBatchResponse(BaseModel):
    """Batch delivery analysis results."""
    results: List[DeliveryAnalyzeResponse]
    total_processed: int
    total_errors: int
    verdict_distribution: Dict[str, int]


class DeliveryPillarSummaryResponse(BaseModel):
    """Summary of delivery analysis capacity."""
    total_analyzed: int
    verdict_distribution: Dict[str, int]
    profiles_available: List[str]
    methodology_version: str


# ── Module-level delivery analyzer (lazy init per profile) ──
_delivery_analyzers: Dict[str, DeliveryAnalyzer] = {}


def _get_delivery_analyzer(profile_name: str) -> DeliveryAnalyzer:
    """Get or create a DeliveryAnalyzer for the given profile."""
    if profile_name not in _delivery_analyzers:
        profile = get_profile(profile_name)
        _delivery_analyzers[profile_name] = DeliveryAnalyzer(profile=profile)
    return _delivery_analyzers[profile_name]


def _convert_delivery_request(req: DeliveryAnalyzeRequest) -> Dict[str, Any]:
    """Convert a DeliveryAnalyzeRequest to kwargs for DeliveryAnalyzer.analyze()."""
    return dict(
        contract_id=req.contract_id,
        milestones=[
            Milestone(
                milestone_id=m.milestone_id,
                description=m.description,
                planned_date=m.planned_date,
                actual_date=m.actual_date,
                status=m.status,
                delay_days=m.delay_days,
                deliverables_due=m.deliverables_due,
                deliverables_accepted=m.deliverables_accepted,
            )
            for m in req.milestones
        ],
        resources=[
            ResourceRecord(
                resource_id=r.resource_id,
                role=r.role,
                planned_fte=r.planned_fte,
                actual_fte=r.actual_fte,
                qualification_required=r.qualification_required,
                qualification_verified=r.qualification_verified,
                period_start=r.period_start,
                period_end=r.period_end,
            )
            for r in req.resources
        ],
        outcomes=[
            OutcomeRecord(
                outcome_id=o.outcome_id,
                description=o.description,
                unit=o.unit,
                quantity_planned=o.quantity_planned,
                quantity_delivered=o.quantity_delivered,
                quality_score=o.quality_score,
                inspection_date=o.inspection_date,
                inspector_id=o.inspector_id,
                defects_noted=o.defects_noted,
            )
            for o in req.outcomes
        ],
        financials=[
            FinancialRecord(
                line_item_id=f.line_item_id,
                description=f.description,
                budgeted_amount=f.budgeted_amount,
                actual_amount=f.actual_amount,
                currency=f.currency,
                variance_pct=f.variance_pct,
                amendment_count=f.amendment_count,
                justification=f.justification,
            )
            for f in req.financials
        ],
        country_code=req.country_code,
        country_name=req.country_name,
        project_name=req.project_name,
        procurement_verdict=req.procurement_verdict,
    )


def _format_delivery_response(result: Dict[str, Any], profile_name: str) -> DeliveryAnalyzeResponse:
    """Convert analyzer result dict to DeliveryAnalyzeResponse."""
    return DeliveryAnalyzeResponse(
        delivery_id=result.get("delivery_id", ""),
        contract_id=result.get("contract_id", ""),
        verdict=result.get("verdict"),
        stage=result.get("stage", ""),
        dimensions_fired=result.get("dimensions_fired", 0),
        dimensions=[
            DeliveryDimensionResponse(**d)
            for d in result.get("dimensions", [])
        ],
        rules_evaluated=result.get("rules_evaluated", 0),
        rules_fired=result.get("rules_fired", 0),
        fired_rules=[
            DeliveryFiredRule(**r)
            for r in result.get("fired_rules", [])
        ],
        layer_summary=result.get("layer_summary", {}),
        graph_summary=result.get("graph_summary"),
        delivery_metrics=result.get("delivery_metrics", {}),
        processing_ms=result.get("processing_ms", {}),
        procurement_verdict=result.get("procurement_verdict", ""),
        methodology_note=result.get("methodology_note", ""),
        methodology_version=result.get("methodology_version", ""),
        errors=result.get("errors", []),
        profile_used=profile_name,
    )


# ── Delivery endpoints ──

@app.post("/delivery/analyze", response_model=DeliveryAnalyzeResponse)
async def analyze_delivery(request: DeliveryAnalyzeRequest):
    """
    Analyze delivery integrity for a single contract.

    Runs the Side 2 delivery verification pipeline (graph construction,
    12-rule evaluation across 4 layers, delivery EVG gating) and returns
    a tiered delivery integrity verdict with per-dimension traceability.
    """
    try:
        profile_name = request.profile
        # Validation guard: raises ValueError for an unknown profile, which becomes a
        # 400 below. The profile OBJECT is not needed — _get_delivery_analyzer takes the
        # name — so the return value is deliberately discarded rather than bound.
        get_profile(profile_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        analyzer = _get_delivery_analyzer(profile_name)
        kwargs = _convert_delivery_request(request)
        result = analyzer.analyze(**kwargs)
        return _format_delivery_response(result, profile_name)
    except Exception as e:
        logger.error(f"Delivery analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delivery analysis failed: {str(e)}")


@app.post("/delivery/batch", response_model=DeliveryBatchResponse)
async def batch_analyze_deliveries(request: DeliveryBatchRequest):
    """
    Analyze delivery integrity for a batch of contracts.

    Runs the Side 2 delivery verification pipeline for each delivery
    and returns aggregate results with verdict distribution.
    """
    try:
        profile_name = request.profile
        # Validation guard: raises ValueError for an unknown profile, which becomes a
        # 400 below. The profile OBJECT is not needed — _get_delivery_analyzer takes the
        # name — so the return value is deliberately discarded rather than bound.
        get_profile(profile_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if len(request.deliveries) > 1000:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(request.deliveries)} exceeds maximum of 1000"
        )

    analyzer = _get_delivery_analyzer(profile_name)
    results = []
    errors = 0
    verdict_dist: Dict[str, int] = {"green": 0, "yellow": 0, "red": 0}

    for delivery_req in request.deliveries:
        try:
            kwargs = _convert_delivery_request(delivery_req)
            result = analyzer.analyze(**kwargs)
            response = _format_delivery_response(result, profile_name)
            results.append(response)
            verdict = result.get("verdict")
            if verdict in verdict_dist:
                verdict_dist[verdict] += 1
        except Exception as e:
            errors += 1
            logger.error(f"Delivery batch item failed: {e}")
            results.append(DeliveryAnalyzeResponse(
                delivery_id="",
                contract_id=delivery_req.contract_id,
                verdict=None,
                stage="delivery_failed",
                errors=[{"error": str(e)}],
                profile_used=profile_name,
            ))

    return DeliveryBatchResponse(
        results=results,
        total_processed=len(request.deliveries),
        total_errors=errors,
        verdict_distribution=verdict_dist,
    )


@app.get("/delivery/pillar-summary", response_model=DeliveryPillarSummaryResponse)
async def delivery_pillar_summary():
    """
    Summary of Side 2 delivery verification capacity.

    Returns the total number of deliveries analyzed across all profiles,
    aggregate verdict distribution, and available profiles.
    """
    total = 0
    verdict_dist: Dict[str, int] = {"green": 0, "yellow": 0, "red": 0}

    for name, analyzer in _delivery_analyzers.items():
        stats = analyzer.stats
        total += stats.get("completed", 0)
        for v in ("green", "yellow", "red"):
            verdict_dist[v] += stats.get(v, 0)

    return DeliveryPillarSummaryResponse(
        total_analyzed=total,
        verdict_distribution=verdict_dist,
        profiles_available=list_profiles(),
        methodology_version="SUNLIGHT Side 2 v1.0 | Delivery EVG v1.0",
    )


# ═══════════════════════════════════════════════════════════════════════════
# SIDE 3: INTELLIGENCE ALERT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


# ── Pydantic models for alert endpoints ──

class AlertConfigResponse(BaseModel):
    """Alert configuration (safe subset, no secrets)."""
    enabled: bool
    min_verdict: str
    min_confidence: float
    min_dimensions: int
    delivery_alerts_enabled: bool
    batch_mode: str
    max_alerts_per_hour: int
    cooldown_seconds: int
    emitter_count: int
    emitter_types: List[str]


class AlertTestResponse(BaseModel):
    """Result of firing a test alert."""
    success: bool
    emissions: List[Dict[str, Any]]


class RuleCitationInput(BaseModel):
    """Rule citation for triage request."""
    rule_id: str
    rule_name: str = ""
    layer: str = ""
    confidence: float = 0.0
    legal_basis: str = ""
    evidence: str = ""
    recommendation: str = ""


class AlertInput(BaseModel):
    """Alert input for triage request."""
    contract_id: str
    verdict: str = "red"
    confidence: float = 0.0
    priority: str = "high"
    dimensions_fired: int = 0
    vendor: str = ""
    contract_value: float = 0.0
    currency: str = "USD"
    award_date: str = ""
    jurisdiction_profile: str = ""
    typologies: List[str] = Field(default_factory=list)
    rule_citations: List[RuleCitationInput] = Field(default_factory=list)
    delivery_verdict: Optional[str] = None
    delivery_dimensions_fired: Optional[int] = None
    delivery_rule_citations: Optional[List[RuleCitationInput]] = None


class TriageRequest(BaseModel):
    """Request to generate a triage brief from alerts."""
    alerts: List[AlertInput]
    batch_id: Optional[str] = None
    total_contracts: int = 0
    jurisdiction_profile: str = "us_federal"
    country_office: Optional[str] = None


class AlertPatternResponse(BaseModel):
    """Cross-contract pattern."""
    pattern_type: str
    description: str
    severity: str
    affected_contracts: List[str]


class TriageBriefResponse(BaseModel):
    """Triage brief response."""
    brief_id: str
    batch_id: Optional[str]
    jurisdiction_profile: str
    total_contracts_analyzed: int
    total_alerts: int
    alerts_by_priority: Dict[str, int]
    alerts_by_dimension: Dict[str, int]
    patterns: List[AlertPatternResponse]
    executive_summary: str


# ── Module-level alert configuration ──
# Loaded once at startup. NOT modifiable via API.
# In production, configure via environment variables or config file.
_alert_config = AlertConfiguration(
    enabled=False,  # Disabled by default; enable in deployment config
    emitters=[LogEmitter()],  # Default: log emitter only
)
_alert_integration = AlertIntegration(_alert_config)


# ── Alert endpoints ──

@app.get("/alerts/config", response_model=AlertConfigResponse)
async def get_alert_config():
    """
    Return current alert configuration.

    Does NOT expose webhook URLs or shared secrets.
    Configuration is set at deployment time; not modifiable via API.
    """
    safe = _alert_config.to_safe_dict()
    return AlertConfigResponse(**safe)


@app.post("/alerts/test", response_model=AlertTestResponse)
async def test_alert():
    """
    Fire a test alert through all configured emitters.

    Uses synthetic finding data. Useful for integration teams to verify
    webhook receiver configuration.
    """
    assembler = AlertAssembler()
    alert = assembler.assemble_procurement_alert(
        contract_id="TEST-SYNTHETIC-001",
        verdict="yellow",
        confidence=0.65,
        dimensions_fired=1,
        rule_fires=[{
            "rule_id": "TEST-001",
            "description": "Synthetic test rule",
            "layer": "test",
            "confidence": 0.65,
            "legal_citations": ["Test citation"],
            "evidence": "Synthetic test evidence",
        }],
        profile_name="test",
        contract_title="Synthetic Test Contract",
        vendor="Test Vendor",
        agency="Test Agency",
        contract_value=100000.0,
    )

    if alert is None:
        return AlertTestResponse(success=False, emissions=[])

    emissions = []
    for emitter in _alert_config.emitters:
        try:
            result = emitter.emit(alert)
            emissions.append({
                "emitter_type": result.emitter_type,
                "success": result.success,
                "error": result.error,
            })
        except Exception as e:
            emissions.append({
                "emitter_type": type(emitter).__name__,
                "success": False,
                "error": str(e),
            })

    all_success = all(e["success"] for e in emissions) if emissions else False
    return AlertTestResponse(success=all_success, emissions=emissions)


@app.post("/alerts/triage", response_model=TriageBriefResponse)
async def generate_triage(request: TriageRequest):
    """
    Generate a TriageBrief from a list of alerts.

    Takes pre-computed alerts and returns a structured triage brief
    with ranking, cross-contract pattern detection, and executive summary.
    Can be called independently of batch processing.
    """
    # Convert AlertInput to IntelligenceAlert
    intel_alerts = []
    for ai in request.alerts:
        priority_map = {
            "critical": AlertPriority.CRITICAL,
            "high": AlertPriority.HIGH,
            "elevated": AlertPriority.ELEVATED,
            "advisory": AlertPriority.ADVISORY,
        }
        priority = priority_map.get(ai.priority.lower(), AlertPriority.HIGH)

        citations = [
            RuleCitation(
                rule_id=rc.rule_id,
                rule_name=rc.rule_name,
                layer=rc.layer,
                confidence=rc.confidence,
                legal_basis=rc.legal_basis,
                evidence=rc.evidence,
                recommendation=rc.recommendation,
            )
            for rc in ai.rule_citations
        ]

        delivery_citations = None
        if ai.delivery_rule_citations:
            delivery_citations = [
                RuleCitation(
                    rule_id=rc.rule_id,
                    rule_name=rc.rule_name,
                    layer=rc.layer,
                    confidence=rc.confidence,
                    legal_basis=rc.legal_basis,
                    evidence=rc.evidence,
                    recommendation=rc.recommendation,
                )
                for rc in ai.delivery_rule_citations
            ]

        alert = IntelligenceAlert(
            contract_id=ai.contract_id,
            verdict=ai.verdict,
            confidence=ai.confidence,
            priority=priority,
            dimensions_fired=ai.dimensions_fired,
            vendor=ai.vendor,
            contract_value=ai.contract_value,
            currency=ai.currency,
            award_date=ai.award_date,
            jurisdiction_profile=ai.jurisdiction_profile,
            typologies=ai.typologies,
            rule_citations=citations,
            delivery_verdict=ai.delivery_verdict,
            delivery_dimensions_fired=ai.delivery_dimensions_fired,
            delivery_rule_citations=delivery_citations,
        )
        alert.summary = assemble_summary(alert)
        alert.recommended_action = assemble_recommended_action(alert)
        intel_alerts.append(alert)

    brief = assemble_triage_brief(
        alerts=intel_alerts,
        batch_id=request.batch_id,
        total_contracts=request.total_contracts,
        jurisdiction_profile=request.jurisdiction_profile,
        country_office=request.country_office,
    )

    return TriageBriefResponse(
        brief_id=brief.brief_id,
        batch_id=brief.batch_id,
        jurisdiction_profile=brief.jurisdiction_profile,
        total_contracts_analyzed=brief.total_contracts_analyzed,
        total_alerts=brief.total_alerts,
        alerts_by_priority=brief.alerts_by_priority,
        alerts_by_dimension=brief.alerts_by_dimension,
        patterns=[
            AlertPatternResponse(
                pattern_type=p.pattern_type,
                description=p.description,
                severity=p.severity,
                affected_contracts=p.affected_contracts,
            )
            for p in brief.patterns
        ],
        executive_summary=brief.executive_summary,
    )


# ═══════════════════════════════════════════════════════════════════════════
# SIDE 4: RECOVERY INTELLIGENCE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


# ── Pydantic models for recovery endpoints ──

class RecoveryRecordRequest(BaseModel):
    """Create a recovery record."""
    source_contract_id: str
    recovery_amount: float
    currency: str = "USD"
    country_office: str
    country_code: str
    original_pillar: str
    source_verdict: str = "red"
    source_confidence: float = 0.0
    source_rule_fires: List[str] = Field(default_factory=list)
    original_sdg: Optional[str] = None
    notes: Optional[str] = None


class RecoveryConfirmRequest(BaseModel):
    """Confirm a recovery."""
    recovery_id: str
    confirmation_date: str  # ISO 8601 date string


class RecoveryAllocateRequest(BaseModel):
    """Request gap-weighted allocation for a recovery."""
    recovery_id: str
    cpd_profile: Dict[str, Any]  # CountryProgrammeProfile as dict


class RecoveryRedirectRequest(BaseModel):
    """Redirect recovered funds to a new contract."""
    recovery_id: str
    target_contract_id: str
    target_pillar: str
    target_sdg: str
    target_output: Optional[str] = None
    target_contract_value: float
    target_contract_title: str = ""
    currency: str = "USD"


class ImpactReportRequest(BaseModel):
    """Query parameters for impact report."""
    country_office: str
    period_start: str  # ISO 8601 date
    period_end: str    # ISO 8601 date
    jurisdiction_profile: str = ""
    total_contracts_analyzed: int = 0
    total_flagged_red: int = 0
    total_flagged_yellow: int = 0
    total_cleared_green: int = 0


# ── Module-level recovery registries ──
_recovery_ledger = RecoveryLedger()
_redirection_registry = RedirectionRegistry()


# ── Recovery endpoints ──

@app.post("/recovery/record")
async def create_recovery_record(request: RecoveryRecordRequest):
    """
    Create a recovery record when Side 1 flags a contract and the
    institution confirms action. Returns a RecoveryRecord at IDENTIFIED status.
    """
    record = _recovery_ledger.create(
        source_contract_id=request.source_contract_id,
        recovery_amount=request.recovery_amount,
        currency=request.currency,
        country_office=request.country_office,
        country_code=request.country_code,
        original_pillar=request.original_pillar,
        source_verdict=request.source_verdict,
        source_confidence=request.source_confidence,
        source_rule_fires=request.source_rule_fires,
        original_sdg=request.original_sdg,
        notes=request.notes,
    )
    return {
        "recovery_id": record.recovery_id,
        "source_contract_id": record.source_contract_id,
        "status": record.status.value,
        "recovery_amount": record.recovery_amount,
        "currency": record.currency,
        "country_office": record.country_office,
        "country_code": record.country_code,
        "original_pillar": record.original_pillar,
    }


@app.post("/recovery/confirm")
async def confirm_recovery(request: RecoveryConfirmRequest):
    """
    Confirm a recovery — institution confirms contract cancellation/modification.
    """
    record = _recovery_ledger.get(request.recovery_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery {request.recovery_id} not found")

    try:
        from datetime import date as date_type
        conf_date = date_type.fromisoformat(request.confirmation_date)
        record.confirm(conf_date)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 (YYYY-MM-DD).")

    return {
        "recovery_id": record.recovery_id,
        "status": record.status.value,
        "confirmation_date": str(record.confirmation_date),
    }


@app.post("/recovery/allocate")
async def allocate_recovery(request: RecoveryAllocateRequest):
    """
    Compute gap-weighted allocation for recovered funds.

    Reads the institution's own CPD and recommends where recovered
    funds should go, proportional to gaps between stated targets and
    actual spending.
    """
    record = _recovery_ledger.get(request.recovery_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery {request.recovery_id} not found")

    cpd = load_cpd_profile_from_dict(request.cpd_profile)
    recommendation = compute_gap_weighted_allocation(
        cpd=cpd,
        recovery_amount=record.recovery_amount,
        recovery_id=record.recovery_id,
    )

    return {
        "recovery_id": recommendation.recovery_id,
        "country_office": recommendation.country_office,
        "recovery_amount": recommendation.recovery_amount,
        "currency": recommendation.currency,
        "methodology": recommendation.methodology,
        "rationale": recommendation.rationale,
        "pillar_allocations": [
            {
                "pillar": pa.pillar,
                "sdg_targets": pa.sdg_targets,
                "cpd_target_percentage": pa.cpd_target_percentage,
                "actual_percentage": pa.actual_percentage,
                "gap_percentage": pa.gap_percentage,
                "allocation_percentage": pa.allocation_percentage,
                "allocation_amount": pa.allocation_amount,
                "rationale": pa.rationale,
            }
            for pa in recommendation.pillar_allocations
        ],
        "output_allocations": [
            {
                "output_id": oa.output_id,
                "output_description": oa.output_description,
                "pillar": oa.pillar,
                "allocation_amount": oa.allocation_amount,
                "rationale": oa.rationale,
            }
            for oa in recommendation.output_allocations
        ],
    }


@app.post("/recovery/redirect")
async def redirect_recovery(request: RecoveryRedirectRequest):
    """
    Link recovered funds to a specific new contract.

    That new contract automatically enters Side 1 and Side 2
    verification queues.
    """
    record = _recovery_ledger.get(request.recovery_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery {request.recovery_id} not found")

    redirection = _redirection_registry.create(
        recovery_id=request.recovery_id,
        target_contract_id=request.target_contract_id,
        target_pillar=request.target_pillar,
        target_sdg=request.target_sdg,
        target_output=request.target_output,
        target_contract_value=request.target_contract_value,
        target_contract_title=request.target_contract_title,
        currency=request.currency,
    )
    record.redirections.append(redirection.redirection_id)

    return {
        "redirection_id": redirection.redirection_id,
        "recovery_id": redirection.recovery_id,
        "target_contract_id": redirection.target_contract_id,
        "target_pillar": redirection.target_pillar,
        "target_sdg": redirection.target_sdg,
        "target_contract_value": redirection.target_contract_value,
        "allocation_source": redirection.allocation_source,
    }


@app.get("/recovery/status/{recovery_id}")
async def get_recovery_status(recovery_id: str):
    """
    Full recovery lifecycle status including all linked redirections,
    their procurement verdicts, and their delivery verdicts.
    """
    record = _recovery_ledger.get(recovery_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Recovery {recovery_id} not found")

    redirections = _redirection_registry.list_by_recovery(recovery_id)

    return {
        "recovery_id": record.recovery_id,
        "source_contract_id": record.source_contract_id,
        "source_verdict": record.source_verdict,
        "status": record.status.value,
        "recovery_amount": record.recovery_amount,
        "currency": record.currency,
        "country_office": record.country_office,
        "original_pillar": record.original_pillar,
        "identification_date": str(record.identification_date) if record.identification_date else None,
        "confirmation_date": str(record.confirmation_date) if record.confirmation_date else None,
        "recovery_date": str(record.recovery_date) if record.recovery_date else None,
        "redirections": [
            {
                "redirection_id": rd.redirection_id,
                "target_contract_id": rd.target_contract_id,
                "target_pillar": rd.target_pillar,
                "target_sdg": rd.target_sdg,
                "target_contract_value": rd.target_contract_value,
                "procurement_verdict": rd.procurement_verdict,
                "delivery_verdict": rd.delivery_verdict,
                "beneficiaries_reached": rd.beneficiaries_reached,
                "full_cycle_complete": rd.full_cycle_complete,
            }
            for rd in redirections
        ],
    }


@app.get("/recovery/impact")
async def get_recovery_impact(
    country_office: str,
    period_start: str,
    period_end: str,
    jurisdiction_profile: str = "",
):
    """
    Impact report for a country office and period.

    This is the endpoint that produces what goes on the Administrator's
    desk at donor meetings.
    """
    from datetime import date as date_type
    try:
        start = date_type.fromisoformat(period_start)
        end = date_type.fromisoformat(period_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 (YYYY-MM-DD).")

    recoveries = _recovery_ledger.list_by_country(country_office)
    all_redirections = []
    for rec in recoveries:
        all_redirections.extend(
            _redirection_registry.list_by_recovery(rec.recovery_id)
        )

    report = assemble_impact_report(
        recoveries=recoveries,
        redirections=all_redirections,
        country_office=country_office,
        country_code=recoveries[0].country_code if recoveries else "",
        reporting_period_start=start,
        reporting_period_end=end,
        jurisdiction_profile=jurisdiction_profile,
    )

    return {
        "report_id": report.report_id,
        "country_office": report.country_office,
        "reporting_period": f"{start} to {end}",
        "total_recoveries": report.total_recoveries,
        "total_amount_recovered": report.total_amount_recovered,
        "currency": report.currency,
        "total_redirections": report.total_redirections,
        "total_amount_redirected": report.total_amount_redirected,
        "redeployed_contracts_total": report.redeployed_contracts_total,
        "redeployed_procurement_green": report.redeployed_procurement_green,
        "redeployed_delivery_green": report.redeployed_delivery_green,
        "redeployed_delivery_pending": report.redeployed_delivery_pending,
        "total_beneficiaries_reached": report.total_beneficiaries_reached,
        "gap_reduction_percentage": report.gap_reduction_percentage,
        "executive_summary": report.executive_summary,
        "cycle_records": [
            {
                "source_contract_id": c.source_contract_id,
                "source_verdict": c.source_verdict,
                "target_contract_id": c.target_contract_id,
                "target_pillar": c.target_pillar,
                "procurement_verdict": c.procurement_verdict,
                "delivery_verdict": c.delivery_verdict,
                "beneficiaries": c.beneficiaries,
                "cycle_complete": c.cycle_complete,
            }
            for c in report.cycle_records
        ],
    }


@app.get("/recovery/cycle/{source_contract_id}")
async def get_recovery_cycle(source_contract_id: str):
    """
    Complete cycle trace for one flagged contract — from RED flag
    through recovery, allocation, redirection, new procurement verdict,
    delivery verdict, beneficiaries reached.
    """
    record = _recovery_ledger.get_by_contract(source_contract_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No recovery record for contract {source_contract_id}"
        )

    redirections = _redirection_registry.list_by_recovery(record.recovery_id)

    return {
        "source_contract_id": record.source_contract_id,
        "source_verdict": record.source_verdict,
        "source_confidence": record.source_confidence,
        "recovery_id": record.recovery_id,
        "recovery_amount": record.recovery_amount,
        "currency": record.currency,
        "status": record.status.value,
        "country_office": record.country_office,
        "original_pillar": record.original_pillar,
        "redirections": [
            {
                "redirection_id": rd.redirection_id,
                "target_contract_id": rd.target_contract_id,
                "target_pillar": rd.target_pillar,
                "target_sdg": rd.target_sdg,
                "target_output": rd.target_output,
                "target_contract_value": rd.target_contract_value,
                "procurement_verdict": rd.procurement_verdict,
                "delivery_verdict": rd.delivery_verdict,
                "delivery_milestones_met": rd.delivery_milestones_met,
                "delivery_milestones_total": rd.delivery_milestones_total,
                "beneficiaries_reached": rd.beneficiaries_reached,
                "full_cycle_complete": rd.full_cycle_complete,
                "full_cycle_clean": rd.full_cycle_clean,
            }
            for rd in redirections
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# SIDE 5 — EVIDENCE CORROBORATION
#
# Six endpoints. Two of them exist to disclose limits rather than to produce
# findings: /evidence/capacity says what SUNLIGHT cannot verify in a given
# country, and /evidence/expected says what it will look for, before anything
# is submitted. An institution is entitled to both in advance.
#
# What the responses never say: that a facility does not exist. SUNLIGHT
# cannot inspect anything. Every corroboration response carries its
# corroboration capacity beside its verdict, because UNVERIFIED at two of six
# reachable evidence classes means something entirely different from
# UNVERIFIED at six of six, and a verdict reported without its reach is
# misleading by omission.
# ═══════════════════════════════════════════════════════════════════════════

from collections import OrderedDict as _OrderedDict

from evidence_analyzer import EvidenceAnalyzer, summarise_capacity
from evidence_maps import load_evidence_map
from evidence_schema import (
    CorroborationDossier as _CorroborationDossier,
    EvidenceArtifact as _EvidenceArtifact,
    EvidenceClass as _EvidenceClass,
    EvidenceStatus as _EvidenceStatus,
    OutcomeClaim as _OutcomeClaim,
    OutcomeType as _OutcomeType,
    Provenance as _Provenance,
    SourceIndependence as _SourceIndependence,
)
from provenance import (
    SUPPORTED_HASH_ALGORITHMS as _SUPPORTED_HASH_ALGORITHMS,
    compute_hash as _compute_hash,
)


# ── Analyzer cache, keyed on the profile actually used ──

_evidence_analyzers: Dict[str, EvidenceAnalyzer] = {}


def _get_evidence_analyzer(profile_name: str, country_code: str = "") -> EvidenceAnalyzer:
    """Get or create an EvidenceAnalyzer.

    A country's evidence map takes precedence over the jurisdiction profile
    when one exists, because Side 5's thresholds and — more importantly — its
    reachable evidence classes are properties of the country, not of the
    procurement regime.
    """
    key = f"{profile_name}:{country_code.lower()}"
    if key not in _evidence_analyzers:
        profile = None
        label = profile_name
        if country_code:
            profile = load_evidence_map(country_code)
            if profile is not None:
                label = f"{profile_name}+{country_code.lower()}"
        if profile is None:
            profile = get_profile(profile_name)
        _evidence_analyzers[key] = EvidenceAnalyzer(
            profile=profile, profile_name=label)
    return _evidence_analyzers[key]


# ── Dossier store ──
#
# Bounded and in-process. This is a cache so that /evidence/dossier/{id} can
# return the analysis just performed; it is NOT a database, and it does not
# survive a restart. Unbounded growth in a long-running API is a defect, so
# the oldest entries are evicted past the cap and the response says plainly
# that retention is ephemeral.
#
# It stores dossiers, which hold provenance — source, digest, timestamp — and
# never artifact CONTENT. Evidence bytes are hashed at ingestion and
# discarded, so a compromised store leaks no underlying documents.

_EVIDENCE_DOSSIER_CACHE_MAX = 500
_evidence_dossiers: "_OrderedDict[str, _CorroborationDossier]" = _OrderedDict()


def _remember_dossier(dossier: _CorroborationDossier) -> None:
    _evidence_dossiers[dossier.dossier_id] = dossier
    _evidence_dossiers.move_to_end(dossier.dossier_id)
    while len(_evidence_dossiers) > _EVIDENCE_DOSSIER_CACHE_MAX:
        _evidence_dossiers.popitem(last=False)


# ── Request / response models ──


class ProvenanceInput(BaseModel):
    source_id: str = Field(..., description="Canonical identifier for the source system or organisation")
    source_name: str = Field(..., description="Human-readable source name")
    retrieval_timestamp: str = Field(..., description="When the source was queried (ISO 8601)")
    content_hash: str = Field(..., description="Digest of the artifact, or of the empty response for a documented absence")
    source_url: Optional[str] = Field(None, description="Where the artifact was retrieved from")
    capture_timestamp: Optional[str] = Field(None, description="When a photograph was taken (ISO 8601)")
    capture_latitude: Optional[float] = Field(None, description="Photograph capture latitude")
    capture_longitude: Optional[float] = Field(None, description="Photograph capture longitude")
    hash_algorithm: str = Field("sha256", description="Digest algorithm; md5 and sha1 are refused")


class EvidenceArtifactInput(BaseModel):
    artifact_id: str = Field(..., description="Unique artifact identifier")
    evidence_class: str = Field(..., description="One of the six evidence classes")
    description: str = Field(..., description="What this artifact is")
    status: str = Field(..., description="observed, absent, contradictory, unqueryable, or stale")
    observed_value: Optional[str] = Field(None, description="Free-text observed value")
    observed_date: Optional[str] = Field(None, description="Date the evidence refers to (ISO 8601)")
    observed_magnitude: Optional[float] = Field(None, description="Measured magnitude, where this artifact measures one")
    source_party_id: Optional[str] = Field(None, description="Party that produced this artifact")
    integrity_verified: Optional[bool] = Field(None, description="Result of re-verifying the hash; null means not checked")
    notes: Optional[str] = Field(None, description="Additional notes")
    provenance: Optional[ProvenanceInput] = Field(None, description="Chain of custody; artifacts without it are refused at ingestion")


class SourceInput(BaseModel):
    party_id: str = Field(..., description="Unique party identifier")
    party_name: str = Field(..., description="Party name")
    party_type: str = Field("", description="implementing_partner, government_agency, commercial_provider, civil_society, etc.")
    linked_parties: List[str] = Field(default_factory=list, description="Parties this one is NOT independent of")
    is_contract_party: bool = Field(False, description="Party to the contract under verification")
    randomly_assigned: Optional[bool] = Field(None, description="Field monitors only: randomly assigned from an independent pool")
    selected_by: Optional[str] = Field(None, description="Field monitors only: party that chose this monitor")


class OutcomeClaimInput(BaseModel):
    claim_id: str = Field(..., description="Unique claim identifier")
    contract_id: str = Field(..., description="Contract this outcome was claimed under")
    outcome_type: str = Field(..., description="Determines which expected-evidence map applies")
    claim_description: str = Field(..., description="What was claimed, e.g. '200-bed hospital operational'")
    claimed_completion_date: Optional[str] = Field(None, description="Claimed completion date (ISO 8601)")
    claimed_magnitude: Optional[float] = Field(None, description="Claimed scale, e.g. 200")
    claimed_magnitude_unit: Optional[str] = Field(None, description="Unit of the claimed scale, e.g. 'beds'")
    site_latitude: Optional[float] = Field(None, description="Site latitude")
    site_longitude: Optional[float] = Field(None, description="Site longitude")
    country_code: Optional[str] = Field(None, description="ISO 3166-1 alpha-2 code")
    country_office: Optional[str] = Field(None, description="Country office")
    award_date: Optional[str] = Field(None, description="Contract award date, anchoring expected-evidence windows")
    source_dossier_id: Optional[str] = Field(None, description="Originating Side 2 delivery dossier")
    source_recovery_id: Optional[str] = Field(None, description="Originating Side 4 recovery record")


class ExpectedEvidenceInput(BaseModel):
    expectation_id: str = Field(..., description="Unique expectation identifier")
    evidence_class: str = Field(..., description="Evidence class expected")
    description: str = Field(..., description="What should exist if the claim is true")
    required: bool = Field(True, description="Whether absence is a candidate finding")
    expected_by_month: Optional[int] = Field(None, description="Months after award when this is expected")
    queryable_in_jurisdiction: bool = Field(True, description="False where the source does not exist locally")


class EvidenceAnalyzeRequest(BaseModel):
    claim: OutcomeClaimInput = Field(..., description="The outcome claim to corroborate")
    artifacts: List[EvidenceArtifactInput] = Field(default_factory=list, description="Submitted evidence, including documented absences")
    source_registry: List[SourceInput] = Field(default_factory=list, description="Parties, with linkage and contract status")
    expected_evidence: Optional[List[ExpectedEvidenceInput]] = Field(None, description="Explicit expectations; when omitted the jurisdiction map is used")
    profile: str = Field("us_federal", description="Jurisdiction profile name")
    country_code: Optional[str] = Field(None, description="Overrides the profile with that country's evidence map when one exists")


class EvidenceBatchRequest(BaseModel):
    claims: List[EvidenceAnalyzeRequest] = Field(..., description="Up to 1000 corroboration requests")
    profile: str = Field("us_federal", description="Default jurisdiction profile")


class VerifyIntegrityRequest(BaseModel):
    artifact_id: str = Field(..., description="Artifact to verify")
    dossier_id: Optional[str] = Field(None, description="Dossier holding the artifact; searched across the cache when omitted")
    content_base64: Optional[str] = Field(None, description="Artifact content, base64-encoded. Preferred: binary-safe")
    content: Optional[str] = Field(None, description="Artifact content as UTF-8 text. Convenience for text artifacts")


# ── Conversion helpers ──


def _parse_enum(enum_cls, value: str, field_name: str):
    try:
        return enum_cls(value)
    except ValueError:
        valid = ", ".join(sorted(m.value for m in enum_cls))
        raise HTTPException(
            status_code=400,
            detail=f"Unknown {field_name} '{value}'. Valid values: {valid}",
        )


def _parse_date(value: Optional[str], field_name: str):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} '{value}' is not an ISO 8601 date",
        )


def _parse_datetime(value: str, field_name: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} '{value}' is not an ISO 8601 timestamp",
        )


def _build_claim(data: OutcomeClaimInput) -> _OutcomeClaim:
    return _OutcomeClaim(
        claim_id=data.claim_id,
        contract_id=data.contract_id,
        outcome_type=_parse_enum(_OutcomeType, data.outcome_type, "outcome_type"),
        claim_description=data.claim_description,
        claimed_completion_date=_parse_date(data.claimed_completion_date, "claimed_completion_date"),
        claimed_magnitude=data.claimed_magnitude,
        claimed_magnitude_unit=data.claimed_magnitude_unit,
        site_latitude=data.site_latitude,
        site_longitude=data.site_longitude,
        country_code=data.country_code,
        country_office=data.country_office,
        award_date=_parse_date(data.award_date, "award_date"),
        source_dossier_id=data.source_dossier_id,
        source_recovery_id=data.source_recovery_id,
    )


def _build_artifacts(items: List[EvidenceArtifactInput], claim_id: str) -> List[_EvidenceArtifact]:
    out = []
    for item in items:
        provenance = None
        if item.provenance is not None:
            p = item.provenance
            provenance = _Provenance(
                source_id=p.source_id,
                source_name=p.source_name,
                retrieval_timestamp=_parse_datetime(p.retrieval_timestamp, "retrieval_timestamp"),
                content_hash=p.content_hash,
                source_url=p.source_url,
                capture_timestamp=(
                    _parse_datetime(p.capture_timestamp, "capture_timestamp")
                    if p.capture_timestamp else None),
                capture_latitude=p.capture_latitude,
                capture_longitude=p.capture_longitude,
                hash_algorithm=p.hash_algorithm,
            )
        out.append(_EvidenceArtifact(
            artifact_id=item.artifact_id,
            evidence_class=_parse_enum(_EvidenceClass, item.evidence_class, "evidence_class"),
            claim_id=claim_id,
            description=item.description,
            status=_parse_enum(_EvidenceStatus, item.status, "status"),
            observed_value=item.observed_value,
            observed_date=_parse_date(item.observed_date, "observed_date"),
            observed_magnitude=item.observed_magnitude,
            provenance=provenance,
            source_party_id=item.source_party_id,
            integrity_verified=item.integrity_verified,
            notes=item.notes,
        ))
    return out


def _build_sources(items: List[SourceInput]) -> List[_SourceIndependence]:
    return [
        _SourceIndependence(
            party_id=s.party_id,
            party_name=s.party_name,
            party_type=s.party_type,
            linked_parties=list(s.linked_parties),
            is_contract_party=s.is_contract_party,
            randomly_assigned=s.randomly_assigned,
            selected_by=s.selected_by,
        )
        for s in items
    ]


def _build_expectations(items: Optional[List[ExpectedEvidenceInput]]):
    if items is None:
        return None
    from evidence_schema import ExpectedEvidence as _ExpectedEvidence
    return [
        _ExpectedEvidence(
            expectation_id=e.expectation_id,
            evidence_class=_parse_enum(_EvidenceClass, e.evidence_class, "evidence_class"),
            description=e.description,
            required=e.required,
            expected_by_month=e.expected_by_month,
            queryable_in_jurisdiction=e.queryable_in_jurisdiction,
        )
        for e in items
    ]


def _run_corroboration(request: EvidenceAnalyzeRequest) -> dict:
    """Analyse one claim and cache the dossier for later retrieval."""
    analyzer = _get_evidence_analyzer(request.profile, request.country_code or "")

    claim = _build_claim(request.claim)
    dossier = analyzer.pipeline.run(
        claim=claim,
        artifacts=_build_artifacts(request.artifacts, claim.claim_id),
        source_registry=_build_sources(request.source_registry),
        expected_evidence=_build_expectations(request.expected_evidence),
    )
    _remember_dossier(dossier)
    return analyzer._format(dossier)


# ── Endpoints ──


@app.post("/evidence/analyze")
async def analyze_evidence(request: EvidenceAnalyzeRequest):
    """
    Corroborate a claimed outcome against independent evidence.

    Runs Side 5 stages 13-16: provenance-validated ingestion, expected-evidence
    resolution, corroboration graph construction with source-independence
    collapse, 16-rule evaluation, and the four-verdict evidence gate.

    Returns the verdict alongside the corroboration capacity it was reached
    at. The two are not separable: UNVERIFIED at two of six reachable
    evidence classes is a statement about this jurisdiction's data sources,
    while UNVERIFIED at six of six is a statement about this claim.

    A CONTRADICTED verdict states that independent evidence is inconsistent
    with the claim as recorded. It does not assert what did or did not
    physically occur.
    """
    try:
        get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        return _run_corroboration(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Evidence analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evidence analysis failed: {str(e)}")


@app.post("/evidence/batch")
async def batch_analyze_evidence(request: EvidenceBatchRequest):
    """
    Corroborate a batch of claims. Maximum 1000.

    The aggregate reports UNVERIFIED as its own count and never merges it
    with CONTRADICTED. They mean opposite things — evidence that could not be
    reached against evidence that conflicts — and a portfolio summary that
    combined them would show a pattern of contradicted claims in exactly the
    country offices whose registries are thinnest.
    """
    if len(request.claims) > 1000:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(request.claims)} exceeds maximum of 1000",
        )

    results = []
    errors = []
    distribution: Dict[str, int] = {
        "verified": 0, "partial": 0, "unverified": 0, "contradicted": 0}
    capacity_total = 0.0

    for i, item in enumerate(request.claims):
        try:
            result = _run_corroboration(item)
        except HTTPException as e:
            errors.append({"index": i, "claim_id": item.claim.claim_id,
                           "error": e.detail})
            continue
        except Exception as e:
            logger.error(f"Batch corroboration failed at index {i}: {e}")
            errors.append({"index": i, "claim_id": item.claim.claim_id,
                           "error": str(e)})
            continue

        results.append(result)
        verdict = result.get("verdict")
        if verdict in distribution:
            distribution[verdict] += 1
        capacity_total += result.get("corroboration_capacity", 0.0)

    analysed = len(results)
    return {
        "results": results,
        "errors": errors,
        "total_submitted": len(request.claims),
        "total_analyzed": analysed,
        "total_failed": len(errors),
        "verdict_distribution": distribution,
        "average_corroboration_capacity": (
            round(capacity_total / analysed, 4) if analysed else 0.0),
        "profile": request.profile,
        "note": (
            "unverified is reported separately from contradicted and must not "
            "be added to it. Unverified means the evidence could not be "
            "reached in that jurisdiction; it is not an adverse finding."
        ),
    }


@app.get("/evidence/expected/{outcome_type}")
async def get_expected_evidence(outcome_type: str, country_code: str = ""):
    """
    What SUNLIGHT will look for, for this outcome type in this country.

    Published deliberately and in advance. An institution is entitled to see
    the expectations before submitting anything, rather than discovering them
    in a finding — and an expectation that cannot survive being published is
    one that should not be applied.

    Expectations marked queryable_in_jurisdiction=false name sources that do
    not exist in this country. Their absence can never produce a finding.
    """
    parsed = _parse_enum(_OutcomeType, outcome_type, "outcome_type")

    country_profile = load_evidence_map(country_code) if country_code else None
    if country_code and country_profile is None:
        return {
            "outcome_type": parsed.value,
            "country_code": country_code.lower(),
            "expectations": [],
            "map_available": False,
            "note": (
                "No evidence map is declared for this country. SUNLIGHT "
                "resolves no expectations here, so no absence finding can be "
                "produced; analysis reports only what the submitted evidence "
                "shows."
            ),
        }

    expectations = (
        country_profile.expectations_for(parsed.value) if country_profile else [])

    return {
        "outcome_type": parsed.value,
        "country_code": (country_code or "").lower(),
        "country_office": country_profile.country_office if country_profile else "",
        "map_status": country_profile.status if country_profile else "none",
        "map_validated": country_profile.is_validated() if country_profile else False,
        "queryable_classes": (
            sorted(country_profile.valid_queryable_classes()) if country_profile else []),
        "expectations": expectations,
        "expectation_count": len(expectations),
        "map_available": country_profile is not None,
        "outcome_types_covered": (
            country_profile.outcome_types_covered() if country_profile else []),
    }


@app.get("/evidence/capacity/{country_code}")
async def get_evidence_capacity(country_code: str):
    """
    What SUNLIGHT can and cannot verify in this jurisdiction.

    Honest disclosure of the capability ceiling, and a feature rather than a
    caveat. Where fewer evidence classes are reachable than the profile
    minimum, no adverse conclusion is available and every verdict in that
    country will be UNVERIFIED — which an institution should know before it
    submits, not after.

    Corroboration capacity is a property of the country's available data
    sources. It says nothing about any project or claim within it.
    """
    profile = load_evidence_map(country_code)
    summary = summarise_capacity(country_code.lower(), profile=profile)
    summary["map_available"] = profile is not None
    summary["map_status"] = profile.status if profile else "none"
    summary["map_validated"] = profile.is_validated() if profile else False
    if profile is None:
        summary["note"] = (
            "No evidence map is declared for this country, so no evidence "
            "class is declared reachable. Reachability is then derived from "
            "what submitted sources actually return. " + summary["note"]
        )
    return summary


@app.get("/evidence/dossier/{dossier_id}")
async def get_evidence_dossier(dossier_id: str):
    """
    Full corroboration dossier: graph, artifacts, and provenance chain.

    Retention is EPHEMERAL. This is an in-process cache holding the most
    recent analyses so a result can be inspected after the fact; it is not a
    database and does not survive a restart. The response says so, so that no
    institution builds an audit trail on it.

    The dossier carries provenance — source, digest, timestamp — and never
    artifact content. Evidence bytes are hashed at ingestion and discarded.
    """
    dossier = _evidence_dossiers.get(dossier_id)
    if dossier is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dossier {dossier_id} is not in the analysis cache. Retention "
                f"is ephemeral and bounded to the {_EVIDENCE_DOSSIER_CACHE_MAX} "
                f"most recent analyses; re-run the analysis to regenerate it."
            ),
        )

    def _artifact_view(a, refused: bool):
        p = a.provenance
        return {
            "artifact_id": a.artifact_id,
            "evidence_class": a.evidence_class.value,
            "description": a.description,
            "status": a.status.value,
            "observed_value": a.observed_value,
            "observed_date": a.observed_date.isoformat() if a.observed_date else None,
            "observed_magnitude": a.observed_magnitude,
            "source_party_id": a.source_party_id,
            "integrity_verified": a.integrity_verified,
            "admitted": not refused,
            "provenance": None if p is None else {
                "source_id": p.source_id,
                "source_name": p.source_name,
                "source_url": p.source_url,
                "retrieval_timestamp": (
                    p.retrieval_timestamp.isoformat()
                    if hasattr(p.retrieval_timestamp, "isoformat")
                    else str(p.retrieval_timestamp)),
                "content_hash": p.content_hash,
                "hash_algorithm": p.hash_algorithm,
                "has_geotag": p.has_geotag,
                "capture_latitude": p.capture_latitude,
                "capture_longitude": p.capture_longitude,
            },
        }

    outcome = dossier.gate_outcome
    return {
        "dossier_id": dossier.dossier_id,
        "claim": {
            "claim_id": dossier.claim.claim_id,
            "contract_id": dossier.claim.contract_id,
            "outcome_type": dossier.claim.outcome_type.value,
            "claim_description": dossier.claim.claim_description,
            "claimed_magnitude": dossier.claim.claimed_magnitude,
            "claimed_magnitude_unit": dossier.claim.claimed_magnitude_unit,
            "country_code": dossier.claim.country_code,
            "source_dossier_id": dossier.claim.source_dossier_id,
            "source_recovery_id": dossier.claim.source_recovery_id,
        },
        "verdict": dossier.verdict.value if dossier.verdict else None,
        "confidence": dossier.confidence,
        "corroboration_capacity": round(dossier.corroboration_capacity, 4),
        "classes_queryable": dossier.classes_queryable,
        "classes_total": dossier.classes_total,
        "independent_classes_corroborating": dossier.independent_classes_corroborating,
        "expected_evidence": [
            {
                "expectation_id": e.expectation_id,
                "evidence_class": e.evidence_class.value,
                "description": e.description,
                "required": e.required,
                "expected_by_month": e.expected_by_month,
                "queryable_in_jurisdiction": e.queryable_in_jurisdiction,
                "absence_is_meaningful": e.absence_is_meaningful,
            }
            for e in dossier.expected_evidence
        ],
        "artifacts": (
            [_artifact_view(a, False) for a in dossier.artifacts]
            + [_artifact_view(a, True) for a in dossier.rejected_artifacts]
        ),
        "source_registry": [
            {
                "party_id": s.party_id,
                "party_name": s.party_name,
                "party_type": s.party_type,
                "linked_parties": s.linked_parties,
                "is_contract_party": s.is_contract_party,
                "randomly_assigned": s.randomly_assigned,
                "selected_by": s.selected_by,
            }
            for s in dossier.source_registry
        ],
        "graph": {
            "node_count": dossier.graph.node_count if dossier.graph else 0,
            "edge_count": dossier.graph.edge_count if dossier.graph else 0,
            "nodes": dossier.graph.nodes if dossier.graph else [],
            "edges": dossier.graph.edges if dossier.graph else [],
        },
        "contradictions": dossier.contradictions,
        "coverage_findings": outcome.coverage_findings if outcome else [],
        "rules_fired": [
            {
                "rule_id": r.rule_id,
                "layer": r.layer,
                "evidence": r.evidence,
                "legal_basis": r.legal_basis,
                "confidence": r.confidence,
                "recommendation": r.recommendation,
            }
            for r in (dossier.rules_result.rule_results if dossier.rules_result else [])
            if r.fired
        ],
        "stage": dossier.stage.value,
        "errors": dossier.errors,
        "methodology_note": outcome.methodology_note if outcome else "",
        "methodology_version": dossier.methodology_version,
        "disclaimer": dossier.disclaimer,
        "retention": (
            f"Ephemeral. In-process cache of the {_EVIDENCE_DOSSIER_CACHE_MAX} "
            f"most recent analyses; not a database, and not durable across a "
            f"restart. Provenance is retained; artifact content is not stored."
        ),
    }


@app.post("/evidence/verify-integrity")
async def verify_evidence_integrity(request: VerifyIntegrityRequest):
    """
    Re-verify an artifact's content hash. Detects post-ingestion tampering.

    Supply content_base64 (binary-safe, preferred) or content as UTF-8 text.
    Exactly one is required: the encoding has to be explicit, because a
    digest computed over differently-encoded bytes is a different digest, and
    an ambiguous mismatch here would be indistinguishable from tampering.

    A mismatch is reported, never raised. Integrity failure is a finding for
    EVD-SRC-002 to carry, not an error to unwind.
    """
    if bool(request.content_base64) == bool(request.content):
        raise HTTPException(
            status_code=400,
            detail=(
                "Supply exactly one of content_base64 or content. The encoding "
                "must be explicit — a digest over differently-encoded bytes is "
                "a different digest."
            ),
        )

    if request.content_base64:
        import base64
        try:
            content = base64.b64decode(request.content_base64, validate=True)
        except Exception:
            raise HTTPException(
                status_code=400, detail="content_base64 is not valid base64")
    else:
        content = request.content.encode("utf-8")

    candidates = (
        [_evidence_dossiers[request.dossier_id]]
        if request.dossier_id and request.dossier_id in _evidence_dossiers
        else list(_evidence_dossiers.values())
    )
    if request.dossier_id and request.dossier_id not in _evidence_dossiers:
        raise HTTPException(
            status_code=404,
            detail=f"Dossier {request.dossier_id} is not in the analysis cache",
        )

    artifact = None
    holder = None
    for dossier in reversed(candidates):
        for candidate in list(dossier.artifacts) + list(dossier.rejected_artifacts):
            if candidate.artifact_id == request.artifact_id:
                artifact, holder = candidate, dossier
                break
        if artifact is not None:
            break

    if artifact is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Artifact {request.artifact_id} is not in the analysis cache. "
                f"Retention is ephemeral; re-run the analysis to regenerate it."
            ),
        )

    if artifact.provenance is None:
        return {
            "artifact_id": artifact.artifact_id,
            "dossier_id": holder.dossier_id,
            "verified": False,
            "reason": "artifact has no provenance and cannot be verified",
            "recorded_hash": None,
            "computed_hash": None,
            "finding": "EVD-SRC-002",
        }

    algorithm = artifact.provenance.hash_algorithm
    if algorithm not in _SUPPORTED_HASH_ALGORITHMS:
        return {
            "artifact_id": artifact.artifact_id,
            "dossier_id": holder.dossier_id,
            "verified": False,
            "reason": f"unsupported hash algorithm '{algorithm}'",
            "recorded_hash": artifact.provenance.content_hash,
            "computed_hash": None,
            "finding": "EVD-SRC-002",
        }

    computed = _compute_hash(content, algorithm=algorithm)
    verified = artifact.provenance.verify_hash(content)

    return {
        "artifact_id": artifact.artifact_id,
        "dossier_id": holder.dossier_id,
        "verified": verified,
        "reason": (
            "content matches the hash recorded at ingestion" if verified
            else "content does not match the hash recorded at ingestion — "
                 "the artifact was modified after ingestion, or different "
                 "content was submitted"
        ),
        "recorded_hash": artifact.provenance.content_hash,
        "computed_hash": computed,
        "hash_algorithm": algorithm,
        "source_id": artifact.provenance.source_id,
        "source_name": artifact.provenance.source_name,
        "finding": None if verified else "EVD-SRC-002",
    }


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
