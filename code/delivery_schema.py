"""
SUNLIGHT Side 2 — Delivery Verification Schema
=================================================

Data structures for delivery integrity verification AFTER money is spent.

Side 1 (procurement) asks: "Should this contract be awarded?"
Side 2 (delivery) asks: "Was what was promised actually delivered?"

Architecture:
    DeliveryDossier is the atom of Side 2, exactly as ContractDossier is the
    atom of Side 1. It links back to a ContractDossier by contract_id but does
    not modify the procurement dossier. Side 2 reads the procurement verdict;
    it never writes to it.

    DeliveryDossier accumulates intelligence through stages 9-12:
        Stage  9 — Ingestion (delivery records attached to contract)
        Stage 10 — Graph Construction (delivery topology built)
        Stage 11 — Rule Evaluation (12 delivery rules across 4 layers)
        Stage 12 — Evidence Gating (delivery EVG verdict)

    The four delivery rule layers:
        Milestone  — Schedule compliance (DEL-MILE-001/002/003)
        Resource   — Staffing and input verification (DEL-RES-001/002/003)
        Outcome    — Output quality and quantity (DEL-OUT-001/002/003)
        Financial  — Cost reconciliation (DEL-FIN-001/002/003)

    The four delivery EVG dimensions:
        MILESTONE_COMPLIANCE      — Schedule adherence
        RESOURCE_VERIFICATION     — Staffing and input integrity
        OUTCOME_VERIFICATION      — Deliverable quality/quantity
        FINANCIAL_RECONCILIATION  — Cost vs. budget integrity

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# ═══════════════════════════════════════════════════════════


class DeliveryStage(Enum):
    """Where a delivery dossier is in the Side 2 pipeline."""
    INGESTED = "delivery_ingested"               # Stage 9: raw delivery records received
    GRAPHED = "delivery_graphed"                  # Stage 10: delivery topology constructed
    RULES_EVALUATED = "delivery_rules_evaluated"  # Stage 11: 12 delivery rules applied
    GATED = "delivery_gated"                      # Stage 12: delivery EVG verdict issued
    COMPLETE = "delivery_complete"                # All delivery analysis finished
    FAILED = "delivery_failed"                    # Processing error


class DeliveryVerdict(Enum):
    """Delivery EVG evidence gate verdict.

    Same tiered model as Side 1 EVG:
        GREEN  — No delivery dimension above threshold
        YELLOW — One dimension above threshold
        RED    — Two or more dimensions above threshold
    """
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class DeliveryDimension(Enum):
    """Dimensions evaluated by the delivery EVG gate."""
    MILESTONE_COMPLIANCE = "milestone_compliance"
    RESOURCE_VERIFICATION = "resource_verification"
    OUTCOME_VERIFICATION = "outcome_verification"
    FINANCIAL_RECONCILIATION = "financial_reconciliation"


class DeliveryRuleLayer(Enum):
    """The four enrichment layers for delivery rules."""
    MILESTONE = "milestone"
    RESOURCE = "resource"
    OUTCOME = "outcome"
    FINANCIAL = "financial"


# ═══════════════════════════════════════════════════════════
# SECTION 2: DELIVERY RECORD INPUTS
# These represent the raw data Side 2 ingests.
# ═══════════════════════════════════════════════════════════


@dataclass
class Milestone:
    """A single contractual milestone with planned vs. actual dates."""
    milestone_id: str
    description: str
    planned_date: Optional[str] = None
    actual_date: Optional[str] = None
    status: str = ""                    # "completed", "delayed", "cancelled", "pending"
    delay_days: int = 0                 # actual - planned, 0 if on time or early
    deliverables_due: int = 0           # number of deliverables expected at this milestone
    deliverables_accepted: int = 0      # number actually accepted


@dataclass
class ResourceRecord:
    """A staffing or resource input record for the contract."""
    resource_id: str
    role: str                           # e.g. "project_manager", "engineer", "inspector"
    planned_fte: float = 0.0            # Full-time equivalent planned
    actual_fte: float = 0.0             # Full-time equivalent deployed
    qualification_required: str = ""    # Required qualification/certification
    qualification_verified: bool = False
    period_start: Optional[str] = None
    period_end: Optional[str] = None


@dataclass
class OutcomeRecord:
    """A deliverable or output record — what was promised vs. what was received."""
    outcome_id: str
    description: str
    unit: str = ""                      # e.g. "km_road", "units", "reports"
    quantity_planned: float = 0.0
    quantity_delivered: float = 0.0
    quality_score: Optional[float] = None  # 0.0-1.0 if assessed, None if not
    inspection_date: Optional[str] = None
    inspector_id: str = ""
    defects_noted: int = 0


@dataclass
class FinancialRecord:
    """Financial reconciliation data — budget vs. actual spend."""
    line_item_id: str
    description: str
    budgeted_amount: float = 0.0
    actual_amount: float = 0.0
    currency: str = "USD"
    variance_pct: float = 0.0          # (actual - budgeted) / budgeted * 100
    amendment_count: int = 0           # number of contract amendments on this line
    justification: str = ""            # justification for variance if any


# ═══════════════════════════════════════════════════════════
# SECTION 3: DELIVERY ENGINE RESULTS
# Each delivery analysis stage writes its result here.
# ═══════════════════════════════════════════════════════════


@dataclass
class DeliveryRuleResult:
    """What happened when a single delivery rule was evaluated."""
    rule_id: str                        # e.g. "DEL-MILE-001"
    layer: str                          # "milestone", "resource", "outcome", "financial"
    fired: bool
    evidence: str = ""                  # Human-readable evidence string
    legal_basis: str = ""               # Legal citation from jurisdiction profile
    confidence: float = 0.0
    detail: str = ""                    # Additional detail on why the rule fired/didn't


@dataclass
class DeliveryGraphResult:
    """Result of delivery graph construction (Stage 10)."""
    node_count: int = 0
    edge_count: int = 0
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DeliveryRulesResult:
    """Aggregate result of all 12 delivery rules (Stage 11)."""
    rules_evaluated: int = 0
    rules_fired: int = 0
    rule_results: List[DeliveryRuleResult] = field(default_factory=list)
    layer_summary: Dict[str, int] = field(default_factory=dict)  # layer → count fired


@dataclass
class DeliveryDimensionResult:
    """Result of evaluating a single delivery EVG dimension."""
    dimension: DeliveryDimension
    fired: bool
    observed_value: Optional[float] = None
    threshold: Optional[float] = None
    detail: str = ""


@dataclass
class DeliveryGateOutcome:
    """Full delivery EVG gate outcome with per-dimension traceability."""
    verdict: DeliveryVerdict
    dimensions_fired: int
    dimension_results: List[DeliveryDimensionResult] = field(default_factory=list)
    methodology_note: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 4: THE DELIVERY DOSSIER
# One object per contract delivery. Links to ContractDossier
# by contract_id. Does not modify the procurement dossier.
# ═══════════════════════════════════════════════════════════


@dataclass
class DeliveryDossier:
    """
    THE ATOM OF SIDE 2.

    One contract delivery. One dossier. Every delivery engine reads
    what it needs, writes what it produces. The delivery dossier
    accumulates intelligence as it flows through stages 9-12.

    This object is:
    - The input to every delivery engine
    - The output of every delivery engine
    - The link back to the procurement dossier (contract_id)
    - The delivery integrity record for institutional reporting
    """

    # ── Identity ──
    delivery_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    contract_id: str = ""               # Links to ContractDossier.contract_id
    country_code: str = ""
    country_name: str = ""
    project_name: str = ""

    # ── Raw Delivery Data ──
    milestones: List[Milestone] = field(default_factory=list)
    resources: List[ResourceRecord] = field(default_factory=list)
    outcomes: List[OutcomeRecord] = field(default_factory=list)
    financials: List[FinancialRecord] = field(default_factory=list)

    # ── Delivery Graph ──
    graph: Optional[DeliveryGraphResult] = None

    # ── Engine Results (each delivery stage writes its section) ──
    rules_result: Optional[DeliveryRulesResult] = None
    gate_outcome: Optional[DeliveryGateOutcome] = None

    # ── Pipeline State ──
    stage: DeliveryStage = DeliveryStage.INGESTED
    errors: List[Dict] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = ""
    processing_ms: Dict[str, float] = field(default_factory=dict)

    # ── Provenance ──
    methodology_version: str = "SUNLIGHT Side 2 v1.0 | Delivery EVG v1.0"
    disclaimer: str = "Delivery integrity finding — not an allegation"

    # ── Procurement Side Reference ──
    procurement_verdict: str = ""       # Side 1 EVG verdict (GREEN/YELLOW/RED)

    def advance(self, stage: DeliveryStage, duration_ms: float = 0):
        """Move to the next delivery pipeline stage. Records timing."""
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if duration_ms > 0:
            self.processing_ms[stage.value] = duration_ms

    def fail(self, stage: DeliveryStage, error: str):
        """Record a failure at a specific delivery stage."""
        self.stage = DeliveryStage.FAILED
        self.errors.append({
            "stage": stage.value,
            "error": error,
            "at": datetime.now(timezone.utc).isoformat()
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def total_milestones(self) -> int:
        """Total number of milestones in this delivery."""
        return len(self.milestones)

    @property
    def delayed_milestones(self) -> int:
        """Count of milestones with delay_days > 0."""
        return sum(1 for m in self.milestones if m.delay_days > 0)

    @property
    def total_budget(self) -> float:
        """Sum of all budgeted amounts across financial line items."""
        return sum(f.budgeted_amount for f in self.financials)

    @property
    def total_actual_spend(self) -> float:
        """Sum of all actual amounts across financial line items."""
        return sum(f.actual_amount for f in self.financials)

    @property
    def budget_variance_pct(self) -> float:
        """Overall budget variance as percentage. Positive = over budget."""
        if self.total_budget == 0:
            return 0.0
        return ((self.total_actual_spend - self.total_budget) / self.total_budget) * 100.0

    @property
    def staffing_gap_ratio(self) -> float:
        """Ratio of actual FTE to planned FTE across all resources. 1.0 = fully staffed."""
        planned = sum(r.planned_fte for r in self.resources)
        if planned == 0:
            return 1.0  # no staffing plan = no gap
        actual = sum(r.actual_fte for r in self.resources)
        return actual / planned

    @property
    def outcome_delivery_ratio(self) -> float:
        """Ratio of quantity delivered to quantity planned across all outcomes. 1.0 = fully delivered."""
        planned = sum(o.quantity_planned for o in self.outcomes)
        if planned == 0:
            return 1.0  # nothing planned = nothing to shortfall
        delivered = sum(o.quantity_delivered for o in self.outcomes)
        return delivered / planned
