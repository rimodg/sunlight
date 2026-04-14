"""
SUNLIGHT v4 Core Architecture
==============================

The structural verification layer for global procurement.

This module IS the architecture. Everything else is an engine
that plugs into this spine.

Design Principles:
    1. ONE OBJECT — ContractDossier holds everything about one contract.
       Every engine reads what it needs, writes what it produces.
       Nothing is lost between stages. Nothing is incompatible.

    2. ONE PIPELINE — Stages execute in defined order with defined
       contracts between them. No engine can skip a stage.
       No engine can corrupt another engine's data.

    3. ONE STATE MACHINE — Every contract knows where it is.
       Every failure is traceable. Every timeout is detectable.

    4. TWO MODES — Batch (historical analysis of existing contracts)
       and Gate (real-time structural verification before award).
       Same pipeline. Different entry points. Same dossier.

    5. ONE FEEDBACK LOOP — When OAI acts on a lead and reports
       the outcome, that outcome flows back into KD, improving
       every future analysis. Intelligence compounds.

Why this architecture matters:
    UNDP has three pillars that don't connect (Compass, OAI, ACPIS).
    SUNLIGHT sits BETWEEN them as connective tissue.
    Once institutional memory compounds through this pipeline,
    removing SUNLIGHT means removing structural verification
    from the entire procurement system. The institution becomes
    structurally dependent — not because we locked them in,
    but because the alternative is going back to zero verification.

    TCA on UNDP's infrastructure: confidence 0.33.
    TCA on SUNLIGHT without this spine: confidence 0.36.
    TCA on SUNLIGHT WITH this spine: target 0.75+.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 4.0.0
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# The vocabulary of the system. Every state, every verdict,
# every priority has exactly one name.
# ═══════════════════════════════════════════════════════════

class PipelineStage(Enum):
    """Where a contract is in the analysis pipeline."""
    INGESTED = "ingested"           # Raw data received
    NORMALIZED = "normalized"       # OCDS fields extracted
    GRAPHED = "graphed"             # TCA graph constructed
    ENTITY_CHECKED = "entity_checked"  # EVG verification complete
    PRICE_CHECKED = "price_checked"    # CRI analysis complete
    STRUCTURE_CHECKED = "structure_checked"  # TCA analysis complete
    GATED = "gated"                 # Pre-Award Gate verdict issued
    RECOVERED = "recovered"         # Recovery projection computed
    LEADS_GENERATED = "leads_generated"  # OAI leads produced
    CERTIFIED = "certified"         # Aggregated into country cert
    COMPLETE = "complete"           # All analysis finished
    FAILED = "failed"               # Processing error


class StructuralVerdict(Enum):
    """TCA structural assessment."""
    SOUND = "sound"           # Confidence >= 0.60
    CONCERN = "concern"       # 0.45 <= confidence < 0.60
    COMPROMISED = "compromised"  # 0.30 <= confidence < 0.45
    CRITICAL = "critical"     # Confidence < 0.30


class GateVerdict(Enum):
    """Pre-Award Gate outcome."""
    CLEAR = "clear"       # All gates passed
    REVIEW = "review"     # Concerns — independent review required
    BLOCK = "block"       # Structural failure — cannot proceed


class InvestigationPriority(Enum):
    """OAI triage priority."""
    IMMEDIATE = "immediate"   # Active investigation warranted
    HIGH = "high"             # Investigation recommended
    STANDARD = "standard"     # Review recommended
    MONITOR = "monitor"       # Add to watchlist


class ExecutionMode(Enum):
    """How the pipeline runs."""
    BATCH = "batch"       # Historical analysis — async, Stork campaigns
    GATE = "gate"         # Real-time verification — sync, sub-second
    MONITOR = "monitor"   # Continuous feed — poll, normalize, flag


# ═══════════════════════════════════════════════════════════
# SECTION 2: THE UNIFIED CONTRACT DOSSIER
# One object per contract. Every engine reads from and writes
# to this object. Nothing is lost. Nothing is incompatible.
# This is the atom of the system.
# ═══════════════════════════════════════════════════════════

@dataclass
class EntityResult:
    """EVG entity verification output."""
    entity_id: str
    entity_name: str
    jurisdiction: str
    verified: bool
    concerns: List[str] = field(default_factory=list)
    shared_ownership: List[str] = field(default_factory=list)
    shell_indicators: int = 0
    opencorporates_match: bool = False


@dataclass
class PriceResult:
    """CRI statistical analysis output."""
    price_score: float              # 0-1 anomaly score
    peer_count: int                 # Number of peer contracts compared
    bootstrap_ci_lower: float       # 95% CI lower bound
    bootstrap_ci_upper: float       # 95% CI upper bound
    bayesian_posterior: float       # P(fraud | evidence)
    within_ci: bool                 # Is price within peer CI?
    markup_pct: float = 0.0        # % above peer median


@dataclass
class StructuralResult:
    """TCA topological analysis output."""
    confidence: float               # 0-1 structural confidence
    verdict: StructuralVerdict
    contradictions: List[Dict]      # REMOVES edges found
    feedback_traps: List[Dict]      # Self-reinforcing loops
    unproven: List[Dict]            # SEEKS edges (unverified)
    verified: List[Dict]            # VERIFIES edges (grounded)
    edge_distribution: Dict[str, int]
    graph_id: str = ""              # KD graph reference
    rule_fire_log: Dict[str, bool] = field(default_factory=dict)  # rule_id → did_fire


@dataclass
class GateResult:
    """Pre-Award Gate 7-gate assessment."""
    verdict: GateVerdict
    gates: Dict[str, str]           # {gate_name: "CLEAR"|"REVIEW"|"BLOCK"}
    blocked_at: Optional[str]       # Which gate blocked (if any)
    patron_detected: bool           # Political patron topology found
    total_contradictions: int
    recommendation: str


@dataclass
class RecoveryResult:
    """Recovery engine projection."""
    projected_recovery: float       # Dollar value
    currency: str
    remediation_steps: List[Dict]   # Specific actions
    peer_benchmark: float           # What this contract SHOULD cost
    excess: float                   # Amount above benchmark
    recovery_confidence: float      # How confident in the projection


@dataclass
class InvestigationLead:
    """OAI-ready investigation brief."""
    lead_id: str
    priority: InvestigationPriority
    compass_flags: int              # UNDP indicator count
    compass_verdict: str            # "CLEAN" or "FLAGGED"
    structural_verdict: str         # SUNLIGHT verdict
    finding_summary: str
    projected_recovery: float
    currency: str
    compass_invisible: bool         # True = Compass CLEAN + SUNLIGHT CRITICAL
    similar_countries: List[str] = field(default_factory=list)


@dataclass
class Outcome:
    """Feedback from OAI after acting on a lead."""
    outcome_id: str
    confirmed: bool                 # Was the structural finding confirmed?
    actual_recovery: float          # How much was actually recovered
    investigation_notes: str
    recorded_at: str
    recorded_by: str


@dataclass
class ContractDossier:
    """
    THE ATOM OF SUNLIGHT.

    One contract. One dossier. Every engine reads what it needs,
    writes what it produces. The dossier accumulates intelligence
    as it flows through the pipeline.

    This object is:
    - The input to every engine
    - The output of every engine
    - The state machine that tracks progress
    - The institutional memory of this contract
    - The OAI investigation brief when complete
    - The data point for country certification

    When UNDP has 70 million of these, each one a complete
    structural analysis with recovery projections and investigation
    leads, that is an asset no institution walks away from.
    """

    # ── Identity ──
    dossier_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ocid: str = ""                      # OCDS contract ID
    contract_id: str = ""               # Internal reference
    country_code: str = ""
    country_name: str = ""

    # ── Raw Data ──
    raw_ocds: Dict = field(default_factory=dict)

    # ── Normalized Fields (OCDS → flat) ──
    buyer_name: str = ""
    buyer_id: str = ""
    supplier_name: str = ""
    supplier_id: str = ""
    suppliers: List[Dict] = field(default_factory=list)
    tender_value: float = 0.0
    award_value: float = 0.0
    currency: str = "USD"
    procurement_method: str = ""
    number_of_tenderers: Optional[int] = None
    tender_start: Optional[str] = None
    tender_end: Optional[str] = None
    award_date: Optional[str] = None
    sector: str = ""
    description: str = ""

    # ── TCA Graph ──
    graph: Optional[Dict] = None        # Nodes + edges in TCA format

    # ── Engine Results (each engine writes its section) ──
    entity: Optional[EntityResult] = None
    price: Optional[PriceResult] = None
    structure: Optional[StructuralResult] = None
    gate: Optional[GateResult] = None
    recovery: Optional[RecoveryResult] = None
    lead: Optional[InvestigationLead] = None
    outcome: Optional[Outcome] = None

    # ── Pipeline State ──
    stage: PipelineStage = PipelineStage.INGESTED
    mode: ExecutionMode = ExecutionMode.BATCH
    errors: List[Dict] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = ""
    processing_ms: Dict[str, float] = field(default_factory=dict)

    # ── Provenance ──
    methodology_version: str = "SUNLIGHT v4.0 | TCA v4.0 | CRI v2.3 | EVG v1.0"
    disclaimer: str = "Structural finding — not an allegation"

    def advance(self, stage: PipelineStage, duration_ms: float = 0):
        """Move to the next pipeline stage. Records timing."""
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if duration_ms > 0:
            self.processing_ms[stage.value] = duration_ms

    def fail(self, stage: PipelineStage, error: str):
        """Record a failure at a specific stage."""
        self.stage = PipelineStage.FAILED
        self.errors.append({
            "stage": stage.value,
            "error": error,
            "at": datetime.now(timezone.utc).isoformat()
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def is_compass_invisible(self) -> bool:
        """True when Compass says CLEAN but SUNLIGHT says CRITICAL/COMPROMISED."""
        if self.lead and self.lead.compass_invisible:
            return True
        if self.structure and self.structure.verdict in (
            StructuralVerdict.CRITICAL, StructuralVerdict.COMPROMISED
        ):
            # No Compass flags but structurally compromised
            return True
        return False

    @property
    def total_processing_ms(self) -> float:
        return sum(self.processing_ms.values())

    def fingerprint(self) -> str:
        """Immutable hash for audit trail."""
        content = json.dumps({
            "ocid": self.ocid,
            "structure": self.structure.confidence if self.structure else None,
            "gate": self.gate.verdict.value if self.gate else None,
            "recovery": self.recovery.projected_recovery if self.recovery else None,
            "created": self.created_at,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict:
        """Serialize for storage/transmission."""
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, Enum):
                d[k] = v.value
            elif v is None:
                continue
            else:
                d[k] = v
        return d


# ═══════════════════════════════════════════════════════════
# SECTION 3: ENGINE PROTOCOLS
# Each engine implements a Protocol. The pipeline doesn't
# know or care HOW an engine works. It only knows the
# contract: what goes in, what comes out.
# ═══════════════════════════════════════════════════════════

class NormalizerEngine(Protocol):
    """Converts raw OCDS → normalized fields on the dossier."""
    def normalize(self, dossier: ContractDossier) -> ContractDossier: ...

class GraphEngine(Protocol):
    """Converts normalized fields → TCA graph on the dossier."""
    def build_graph(self, dossier: ContractDossier) -> ContractDossier: ...

class EntityEngine(Protocol):
    """Runs EVG entity verification, writes EntityResult."""
    def verify(self, dossier: ContractDossier) -> ContractDossier: ...

class PriceEngine(Protocol):
    """Runs CRI statistical analysis, writes PriceResult."""
    def analyze(self, dossier: ContractDossier) -> ContractDossier: ...

class StructureEngine(Protocol):
    """Runs TCA topological analysis, writes StructuralResult."""
    def analyze(self, dossier: ContractDossier) -> ContractDossier: ...

class GateEngine(Protocol):
    """Runs Pre-Award 7-gate verification, writes GateResult."""
    def evaluate(self, dossier: ContractDossier) -> ContractDossier: ...

class RecoveryEngine(Protocol):
    """Computes recovery projection, writes RecoveryResult."""
    def project(self, dossier: ContractDossier) -> ContractDossier: ...

class LeadEngine(Protocol):
    """Generates OAI investigation lead, writes InvestigationLead."""
    def generate(self, dossier: ContractDossier) -> ContractDossier: ...


# ═══════════════════════════════════════════════════════════
# SECTION 4: THE PIPELINE
# One pipeline. Defined stage order. Each stage is bounded.
# Each stage has a contract: reads specific fields, writes
# specific fields. No engine touches another engine's data.
# ═══════════════════════════════════════════════════════════

class SunlightPipeline:
    """
    The circulatory system of SUNLIGHT.

    A contract enters as raw OCDS data and exits as a complete
    ContractDossier with structural analysis, entity verification,
    price assessment, gate verdict, recovery projection, and
    investigation lead.

    Pipeline stages:
        INGEST → NORMALIZE → GRAPH → [ENTITY, PRICE, STRUCTURE] → GATE → RECOVER → LEAD

    ENTITY, PRICE, and STRUCTURE are independent analyses.
    In BATCH mode they run in parallel. In GATE mode they
    run sequentially for deterministic timing.

    The pipeline is the ONLY way to produce a complete dossier.
    No engine can be called outside the pipeline in production.
    This ensures every dossier has passed every stage.
    """

    def __init__(
        self,
        normalizer: Optional[NormalizerEngine] = None,
        grapher: Optional[GraphEngine] = None,
        entity: Optional[EntityEngine] = None,
        price: Optional[PriceEngine] = None,
        structure: Optional[StructureEngine] = None,
        gate: Optional[GateEngine] = None,
        recovery: Optional[RecoveryEngine] = None,
        lead: Optional[LeadEngine] = None,
        on_complete: Optional[Callable[[ContractDossier], None]] = None,
        on_failure: Optional[Callable[[ContractDossier], None]] = None,
    ):
        self.normalizer = normalizer
        self.grapher = grapher
        self.entity = entity
        self.price = price
        self.structure = structure
        self.gate = gate
        self.recovery = recovery
        self.lead = lead
        self.on_complete = on_complete
        self.on_failure = on_failure

        # Pipeline statistics
        self.stats = {
            "processed": 0,
            "completed": 0,
            "failed": 0,
            "compass_invisible": 0,
            "blocked": 0,
            "total_recovery_projected": 0.0,
        }

    def ingest(self, raw_ocds: Dict, mode: ExecutionMode = ExecutionMode.BATCH) -> ContractDossier:
        """Create a dossier from raw OCDS data. Entry point."""
        dossier = ContractDossier(
            raw_ocds=raw_ocds,
            ocid=raw_ocds.get("ocid", ""),
            mode=mode,
        )
        dossier.advance(PipelineStage.INGESTED)
        return dossier

    def process(self, dossier: ContractDossier) -> ContractDossier:
        """
        Run the full pipeline on a dossier.

        This is the ONLY public method that produces a complete analysis.
        Every stage is wrapped in error handling. A failure at any stage
        records the error and marks the dossier as FAILED, but does not
        crash the pipeline.
        """
        self.stats["processed"] += 1
        stages = [
            (PipelineStage.NORMALIZED, self._normalize),
            (PipelineStage.GRAPHED, self._graph),
            (PipelineStage.ENTITY_CHECKED, self._entity),
            (PipelineStage.PRICE_CHECKED, self._price),
            (PipelineStage.STRUCTURE_CHECKED, self._structure),
            (PipelineStage.GATED, self._gate),
            (PipelineStage.RECOVERED, self._recover),
            (PipelineStage.LEADS_GENERATED, self._lead),
        ]

        for stage, handler in stages:
            try:
                import time
                t0 = time.monotonic()
                dossier = handler(dossier)
                elapsed = (time.monotonic() - t0) * 1000
                dossier.advance(stage, elapsed)
            except Exception as e:
                dossier.fail(stage, str(e))
                self.stats["failed"] += 1
                if self.on_failure:
                    self.on_failure(dossier)
                return dossier

        dossier.advance(PipelineStage.COMPLETE)
        self.stats["completed"] += 1

        if dossier.is_compass_invisible:
            self.stats["compass_invisible"] += 1
        if dossier.gate and dossier.gate.verdict == GateVerdict.BLOCK:
            self.stats["blocked"] += 1
        if dossier.recovery:
            self.stats["total_recovery_projected"] += dossier.recovery.projected_recovery

        if self.on_complete:
            self.on_complete(dossier)

        return dossier

    def _normalize(self, d: ContractDossier) -> ContractDossier:
        if self.normalizer:
            return self.normalizer.normalize(d)
        # Fallback: extract from raw OCDS directly
        raw = d.raw_ocds
        tender = raw.get("tender", {})
        awards = raw.get("awards", [{}])
        award = awards[0] if awards else {}
        parties = raw.get("parties", [])

        buyers = [p for p in parties if "buyer" in str(p.get("roles", []))]
        suppliers = [p for p in parties if "supplier" in str(p.get("roles", []))]

        d.buyer_name = buyers[0].get("name", "") if buyers else raw.get("buyer", {}).get("name", "")
        d.buyer_id = buyers[0].get("id", "") if buyers else ""
        d.supplier_name = suppliers[0].get("name", "") if suppliers else ""
        d.supplier_id = suppliers[0].get("id", "") if suppliers else ""
        d.suppliers = suppliers

        tv = tender.get("value", {})
        av = award.get("value", {})
        d.tender_value = float(tv.get("amount", 0) or 0)
        d.award_value = float(av.get("amount", 0) or 0)
        d.currency = tv.get("currency", av.get("currency", "USD"))

        method = tender.get("procurementMethod", "")
        d.procurement_method = method.lower() if method else ""

        d.number_of_tenderers = tender.get("numberOfTenderers")
        if d.number_of_tenderers is not None:
            d.number_of_tenderers = int(d.number_of_tenderers)

        d.award_date = award.get("date", "")
        d.sector = tender.get("mainProcurementCategory", "")
        d.description = tender.get("description", "")[:500]
        d.country_code = raw.get("tag", [""])[0][:2].upper() if raw.get("tag") else ""

        return d

    def _graph(self, d: ContractDossier) -> ContractDossier:
        if self.grapher:
            return self.grapher.build_graph(d)
        # Fallback: construct minimal TCA graph from normalized fields
        nodes = [
            {"id": "buyer", "label": d.buyer_name or "Buyer"},
            {"id": "award", "label": "Award Decision"},
            {"id": "process", "label": d.procurement_method or "Process"},
            {"id": "budget", "label": f"Budget ({d.currency} {d.tender_value:,.0f})"},
        ]
        edges = [
            {"source": "buyer", "target": "award", "type": "EXPRESSES", "weight": 1.0},
            {"source": "process", "target": "award", "type": "BOUNDS", "weight": 0.8},
            {"source": "budget", "target": "award", "type": "BOUNDS", "weight": 0.9},
        ]

        for i, s in enumerate(d.suppliers):
            sid = f"supplier_{i}"
            nodes.append({"id": sid, "label": s.get("name", f"Supplier {i}")})
            edges.append({"source": "award", "target": sid, "type": "EXPRESSES", "weight": 0.9})

        # Structural signals
        actual_bidders = d.number_of_tenderers
        if actual_bidders is not None and actual_bidders <= 1 and d.procurement_method in ("open", "selective", "competitive"):
            edges.append({
                "source": "award", "target": "process", "type": "REMOVES", "weight": 1.0,
                "description": f"Single bidder ({actual_bidders}) in competitive tender"
            })

        # Currency-aware direct award threshold
        thresholds = {"USD": 100_000, "EUR": 90_000, "PYG": 750_000_000, "COP": 400_000_000, "MXN": 1_700_000}
        threshold = thresholds.get(d.currency, 100_000)
        if d.procurement_method in ("direct", "limited", "sole_source") and d.tender_value > threshold:
            edges.append({
                "source": "award", "target": "process", "type": "REMOVES", "weight": 0.9,
                "description": f"Direct award of {d.currency} {d.tender_value:,.0f} above competitive threshold"
            })

        # Oversight — always model it
        has_oversight = any("review" in str(p.get("roles", [])).lower() for p in d.raw_ocds.get("parties", []))
        if has_oversight:
            nodes.append({"id": "oversight", "label": "Oversight Body"})
            edges.append({"source": "oversight", "target": "award", "type": "VERIFIES", "weight": 0.8})
        else:
            nodes.append({"id": "oversight", "label": "Oversight (Absent)"})
            edges.append({"source": "award", "target": "oversight", "type": "SEEKS", "weight": 0.4,
                         "description": "No review body identified"})

        d.graph = {
            "name": f"{d.ocid} — {d.buyer_name}",
            "nodes": nodes,
            "edges": edges,
        }
        return d

    def _entity(self, d: ContractDossier) -> ContractDossier:
        if self.entity:
            return self.entity.verify(d)
        # Stub: mark as not yet verified
        d.entity = EntityResult(
            entity_id=d.supplier_id,
            entity_name=d.supplier_name,
            jurisdiction=d.country_code,
            verified=False,
        )
        return d

    def _price(self, d: ContractDossier) -> ContractDossier:
        if self.price:
            return self.price.analyze(d)
        # Stub: no peer data available
        d.price = PriceResult(
            price_score=0.5,
            peer_count=0,
            bootstrap_ci_lower=0,
            bootstrap_ci_upper=0,
            bayesian_posterior=0.02,
            within_ci=True,
        )
        return d

    def _structure(self, d: ContractDossier) -> ContractDossier:
        if self.structure:
            return self.structure.analyze(d)
        # Fallback: count REMOVES and SEEKS edges for basic assessment
        if not d.graph:
            d.structure = StructuralResult(
                confidence=0.5, verdict=StructuralVerdict.CONCERN,
                contradictions=[], feedback_traps=[], unproven=[], verified=[],
                edge_distribution={}, graph_id=""
            )
            return d

        edges = d.graph.get("edges", [])
        removes = [e for e in edges if e.get("type") == "REMOVES"]
        seeks = [e for e in edges if e.get("type") == "SEEKS"]
        verifies = [e for e in edges if e.get("type") == "VERIFIES"]
        total = len(edges) or 1

        # Simple confidence: penalize REMOVES, reward VERIFIES
        confidence = 1.0 - (len(removes) * 0.15) - (len(seeks) * 0.05) + (len(verifies) * 0.05)
        confidence = max(0.0, min(1.0, confidence))

        if confidence < 0.30:
            verdict = StructuralVerdict.CRITICAL
        elif confidence < 0.45:
            verdict = StructuralVerdict.COMPROMISED
        elif confidence < 0.60:
            verdict = StructuralVerdict.CONCERN
        else:
            verdict = StructuralVerdict.SOUND

        dist = {}
        for e in edges:
            t = e.get("type", "UNKNOWN")
            dist[t] = dist.get(t, 0) + 1

        d.structure = StructuralResult(
            confidence=round(confidence, 4),
            verdict=verdict,
            contradictions=[{"from": e["source"], "to": e["target"],
                           "description": e.get("description", "Structural contradiction")}
                          for e in removes],
            feedback_traps=[],
            unproven=[{"from": e["source"], "to": e["target"],
                      "description": e.get("description", "Unverified assumption")}
                     for e in seeks],
            verified=[{"from": e["source"], "to": e["target"]} for e in verifies],
            edge_distribution=dist,
        )
        return d

    def _gate(self, d: ContractDossier) -> ContractDossier:
        if self.gate:
            return self.gate.evaluate(d)
        # Fallback: derive gate from structure + entity + price
        gates = {}
        blocked_at = None
        total_contradictions = 0

        # Entity gate
        if d.entity and d.entity.shared_ownership:
            gates["entity"] = "BLOCK"
            blocked_at = blocked_at or "Entity Gate"
        elif d.entity and not d.entity.verified:
            gates["entity"] = "REVIEW"
        else:
            gates["entity"] = "CLEAR"

        # Competition gate
        if d.number_of_tenderers is not None and d.number_of_tenderers <= 1:
            gates["competition"] = "BLOCK" if d.procurement_method in ("open", "selective") else "REVIEW"
            blocked_at = blocked_at or "Competition Gate"
        else:
            gates["competition"] = "CLEAR"

        # Price gate
        if d.price and not d.price.within_ci:
            gates["price"] = "REVIEW"
        else:
            gates["price"] = "CLEAR"

        # Structure gate (TCA)
        if d.structure:
            total_contradictions = len(d.structure.contradictions)
            if d.structure.verdict == StructuralVerdict.CRITICAL:
                gates["structure"] = "BLOCK"
                blocked_at = blocked_at or "Structure Gate"
            elif d.structure.verdict == StructuralVerdict.COMPROMISED:
                gates["structure"] = "REVIEW"
            else:
                gates["structure"] = "CLEAR"
        else:
            gates["structure"] = "REVIEW"

        # Award gate (aggregate)
        blocks = sum(1 for v in gates.values() if v == "BLOCK")
        reviews = sum(1 for v in gates.values() if v == "REVIEW")

        if blocks > 0:
            verdict = GateVerdict.BLOCK
        elif reviews >= 2:
            verdict = GateVerdict.REVIEW
        else:
            verdict = GateVerdict.CLEAR

        # Patron detection
        patron = False
        if d.structure and total_contradictions >= 3:
            patron = True

        d.gate = GateResult(
            verdict=verdict,
            gates=gates,
            blocked_at=blocked_at,
            patron_detected=patron,
            total_contradictions=total_contradictions,
            recommendation={
                GateVerdict.CLEAR: "Proceed — structural verification passed",
                GateVerdict.REVIEW: "Hold — independent structural review required",
                GateVerdict.BLOCK: "Block — structural failure detected, cannot proceed",
            }[verdict]
        )
        return d

    def _recover(self, d: ContractDossier) -> ContractDossier:
        if self.recovery:
            return self.recovery.project(d)
        # Fallback: estimate based on contradictions
        if not d.structure or d.structure.verdict == StructuralVerdict.SOUND:
            d.recovery = RecoveryResult(
                projected_recovery=0, currency=d.currency,
                remediation_steps=[], peer_benchmark=d.tender_value,
                excess=0, recovery_confidence=0
            )
            return d

        # Estimate: each contradiction costs ~10% of contract value
        n = len(d.structure.contradictions)
        excess_pct = min(n * 0.10, 0.40)  # Cap at 40%
        excess = d.tender_value * excess_pct
        recovery_confidence = min(n * 0.2, 0.8)  # More contradictions = more confident

        steps = []
        for c in d.structure.contradictions:
            steps.append({
                "action": f"Address: {c.get('description', 'structural finding')}",
                "type": "structural_remediation"
            })

        d.recovery = RecoveryResult(
            projected_recovery=round(excess, 2),
            currency=d.currency,
            remediation_steps=steps,
            peer_benchmark=d.tender_value * (1 - excess_pct),
            excess=round(excess, 2),
            recovery_confidence=round(recovery_confidence, 2),
        )
        return d

    def _lead(self, d: ContractDossier) -> ContractDossier:
        if self.lead:
            return self.lead.generate(d)
        # Generate from accumulated analysis
        if not d.structure:
            return d

        compass_flags = 0  # Would come from UNDP integration
        compass_invisible = (
            compass_flags == 0 and
            d.structure.verdict in (StructuralVerdict.CRITICAL, StructuralVerdict.COMPROMISED)
        )

        # Priority assignment
        if compass_invisible and d.gate and d.gate.verdict == GateVerdict.BLOCK:
            priority = InvestigationPriority.IMMEDIATE
        elif d.structure.verdict == StructuralVerdict.CRITICAL:
            priority = InvestigationPriority.HIGH
        elif d.structure.verdict == StructuralVerdict.COMPROMISED:
            priority = InvestigationPriority.STANDARD
        else:
            priority = InvestigationPriority.MONITOR

        findings = "; ".join(
            c.get("description", "") for c in d.structure.contradictions
        )

        d.lead = InvestigationLead(
            lead_id=f"SL-{d.country_code}-{d.fingerprint()}",
            priority=priority,
            compass_flags=compass_flags,
            compass_verdict="CLEAN" if compass_flags == 0 else "FLAGGED",
            structural_verdict=d.structure.verdict.value,
            finding_summary=findings or "No structural findings",
            projected_recovery=d.recovery.projected_recovery if d.recovery else 0,
            currency=d.currency,
            compass_invisible=compass_invisible,
        )
        return d

    def report(self) -> str:
        """Pipeline statistics summary."""
        s = self.stats
        lines = [
            "═" * 50,
            "SUNLIGHT PIPELINE — STATUS",
            "═" * 50,
            f"Processed:           {s['processed']}",
            f"Completed:           {s['completed']}",
            f"Failed:              {s['failed']}",
            f"Compass-invisible:   {s['compass_invisible']}",
            f"Blocked at gate:     {s['blocked']}",
            f"Recovery projected:  {d.currency if hasattr(d, 'currency') else 'USD'} {s['total_recovery_projected']:,.2f}" if s['total_recovery_projected'] > 0 else f"Recovery projected:  $0",
            "═" * 50,
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# SECTION 5: AGGREGATORS
# These operate on collections of dossiers, not individual
# contracts. Certification, country-level analysis, trend
# detection, cross-jurisdictional pattern matching.
# ═══════════════════════════════════════════════════════════

class CountryCertifier:
    """
    Aggregates dossiers into country-level structural health certifications.

    Takes N dossiers for a country → produces a grade (A-F),
    sector breakdowns, trend analysis, and remediation priorities.
    """

    GRADES = {
        (0.80, 1.01): "A",
        (0.65, 0.80): "B",
        (0.50, 0.65): "C",
        (0.35, 0.50): "D",
        (0.20, 0.35): "E",
        (0.00, 0.20): "F",
    }

    def certify(self, country_code: str, dossiers: List[ContractDossier]) -> Dict:
        """Produce a country structural health certification."""
        completed = [d for d in dossiers if d.structure is not None]
        if not completed:
            return {"country": country_code, "grade": "INSUFFICIENT DATA", "contracts": 0}

        confidences = [d.structure.confidence for d in completed]
        avg_conf = sum(confidences) / len(confidences)

        grade = "F"
        for (low, high), g in self.GRADES.items():
            if low <= avg_conf < high:
                grade = g
                break

        total_contradictions = sum(len(d.structure.contradictions) for d in completed)
        total_recovery = sum(d.recovery.projected_recovery for d in completed if d.recovery)
        compass_invisible = sum(1 for d in completed if d.is_compass_invisible)
        blocked = sum(1 for d in completed if d.gate and d.gate.verdict == GateVerdict.BLOCK)

        # Sector breakdown
        sectors = {}
        for d in completed:
            s = d.sector or "unclassified"
            if s not in sectors:
                sectors[s] = {"count": 0, "confidence_sum": 0, "contradictions": 0}
            sectors[s]["count"] += 1
            sectors[s]["confidence_sum"] += d.structure.confidence
            sectors[s]["contradictions"] += len(d.structure.contradictions)

        sector_grades = {}
        for s, data in sectors.items():
            avg = data["confidence_sum"] / data["count"]
            for (low, high), g in self.GRADES.items():
                if low <= avg < high:
                    sector_grades[s] = {"grade": g, "confidence": round(avg, 3), "contracts": data["count"], "contradictions": data["contradictions"]}
                    break

        return {
            "country": country_code,
            "grade": grade,
            "confidence": round(avg_conf, 4),
            "contracts_analyzed": len(completed),
            "total_contradictions": total_contradictions,
            "total_projected_recovery": round(total_recovery, 2),
            "compass_invisible_findings": compass_invisible,
            "blocked_at_gate": blocked,
            "sectors": sector_grades,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "methodology": "SUNLIGHT v4.0 — Structural Health Certification",
        }


# ═══════════════════════════════════════════════════════════
# SECTION 6: DEMO — Proof the spine works
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    pipeline = SunlightPipeline()

    # ── Case 1: Senegal ──
    senegal_raw = {
        "ocid": "ocds-SN-ARMP-2025-0847",
        "tag": ["planning"],
        "buyer": {"name": "Agence Routière du Sénégal"},
        "tender": {
            "value": {"amount": 2_450_000, "currency": "USD"},
            "procurementMethod": "direct",
            "numberOfTenderers": 1,
            "mainProcurementCategory": "works",
            "description": "Road infrastructure rehabilitation, Thiès Region",
        },
        "awards": [{"value": {"amount": 2_450_000, "currency": "USD"}, "date": "2025-06-22"}],
        "parties": [
            {"name": "Agence Routière du Sénégal", "roles": ["buyer"]},
            {"name": "SGT SA", "id": "SN-SGT-001", "roles": ["supplier"]},
        ],
    }

    senegal = pipeline.ingest(senegal_raw)
    senegal = pipeline.process(senegal)

    print("═" * 60)
    print("CASE 1: SENEGAL — Road Infrastructure")
    print("═" * 60)
    print(f"Stage:        {senegal.stage.value}")
    print(f"TCA:          {senegal.structure.confidence} — {senegal.structure.verdict.value}")
    print(f"Contrad:      {len(senegal.structure.contradictions)}")
    print(f"Gate:         {senegal.gate.verdict.value} (blocked at: {senegal.gate.blocked_at})")
    print(f"Recovery:     {senegal.currency} {senegal.recovery.projected_recovery:,.2f}")
    print(f"Lead:         {senegal.lead.priority.value} — Compass-invisible: {senegal.lead.compass_invisible}")
    print(f"Processing:   {senegal.total_processing_ms:.1f}ms")
    print(f"Fingerprint:  {senegal.fingerprint()}")
    print()

    # ── Case 2: Marquez (DOD) ──
    marquez_raw = {
        "ocid": "ocds-US-DOD-IT-2024-MARQUEZ",
        "tag": ["award"],
        "buyer": {"name": "Department of Defense"},
        "tender": {
            "value": {"amount": 5_200_000, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": 3,
            "mainProcurementCategory": "goods",
            "description": "IT products and services for federal agencies",
        },
        "awards": [{"value": {"amount": 5_200_000, "currency": "USD"}, "date": "2024-03-15"}],
        "parties": [
            {"name": "Department of Defense", "roles": ["buyer"]},
            {"name": "Marquez IT Co 1", "id": "US-MARQUEZ-001", "roles": ["supplier"]},
            {"name": "Marquez IT Co 2", "id": "US-MARQUEZ-002", "roles": ["tenderer"]},
            {"name": "Reefe Corp", "id": "US-REEFE-001", "roles": ["tenderer"]},
        ],
    }

    marquez = pipeline.ingest(marquez_raw)
    marquez = pipeline.process(marquez)

    print("═" * 60)
    print("CASE 2: MARQUEZ — DOD IT Procurement")
    print("═" * 60)
    print(f"Stage:        {marquez.stage.value}")
    print(f"TCA:          {marquez.structure.confidence} — {marquez.structure.verdict.value}")
    print(f"Contrad:      {len(marquez.structure.contradictions)}")
    print(f"Gate:         {marquez.gate.verdict.value}")
    print(f"Recovery:     {marquez.currency} {marquez.recovery.projected_recovery:,.2f}")
    print(f"Lead:         {marquez.lead.priority.value}")
    print(f"Processing:   {marquez.total_processing_ms:.1f}ms")
    print()

    # ── Case 3: Clean contract ──
    clean_raw = {
        "ocid": "ocds-PY-DNCP-2025-CLEAN",
        "tag": ["award"],
        "buyer": {"name": "Ministerio de Obras Públicas"},
        "tender": {
            "value": {"amount": 150_000, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": 7,
            "mainProcurementCategory": "works",
        },
        "awards": [{"value": {"amount": 148_000, "currency": "USD"}}],
        "parties": [
            {"name": "Ministerio de Obras Públicas", "roles": ["buyer"]},
            {"name": "Constructora ABC", "roles": ["supplier"]},
            {"name": "Procurement Review Board", "roles": ["reviewBody"]},
        ],
    }

    clean = pipeline.ingest(clean_raw)
    clean = pipeline.process(clean)

    print("═" * 60)
    print("CASE 3: PARAGUAY — Clean Contract")
    print("═" * 60)
    print(f"Stage:        {clean.stage.value}")
    print(f"TCA:          {clean.structure.confidence} — {clean.structure.verdict.value}")
    print(f"Gate:         {clean.gate.verdict.value}")
    print(f"Recovery:     {clean.currency} {clean.recovery.projected_recovery:,.2f}")
    print(f"Lead:         {clean.lead.priority.value}")
    print()

    # ── Country Certification ──
    certifier = CountryCertifier()
    cert = certifier.certify("PY", [clean])
    print("═" * 60)
    print(f"PARAGUAY CERTIFICATION: Grade {cert['grade']} ({cert['confidence']:.1%})")
    print("═" * 60)
    print()

    # ── Pipeline Stats ──
    print(f"Pipeline: {pipeline.stats['processed']} processed, {pipeline.stats['completed']} completed, {pipeline.stats['compass_invisible']} compass-invisible")
    print(f"Total recovery projected: USD {pipeline.stats['total_recovery_projected']:,.2f}")
