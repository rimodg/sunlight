"""
SUNLIGHT Side 5 — Evidence Corroboration Schema
==================================================

Data structures for corroborating claimed outcomes against independent evidence.

Side 1 (procurement) asks: "Should this contract be awarded?"
Side 2 (delivery)    asks: "Was what was promised actually delivered?"
Side 4 (recovery)    asks: "What happened to the money we saved?"
Side 5 (evidence)    asks: "Does independent evidence corroborate the claim?"

What this is, and what it is not:
    SUNLIGHT cannot physically inspect anything. It cannot prove a hospital
    exists. No software can. What it can do is make it structurally difficult
    for a false claim to survive contact with independent evidence sources.

    The output is never "this facility does not exist." The output is a
    structural finding with a documented evidence chain: which classes were
    queried, what each returned, which contradicted the claim, and how much
    of the evidence space was reachable in this jurisdiction at all.

The constraint that governs every decision in this module:
    UNVERIFIED IS NOT CONTRADICTED.

    Absence of data in a weak-infrastructure country is not evidence of
    fraud. A jurisdiction with no digital land registry, no utility
    connection database and no health information system cannot produce
    the evidence that would corroborate a true claim — and must never be
    penalised for that. CorroborationVerdict therefore has FOUR members,
    not three, and the separation between UNVERIFIED and CONTRADICTED is
    enforced architecturally rather than by convention: the coverage rules
    that measure evidence-space reachability (Layer 5) are not wired to
    any EVG dimension, so they cannot reach a CONTRADICTED branch.

Architecture:
    CorroborationDossier is the atom of Side 5, exactly as ContractDossier
    is the atom of Side 1 and DeliveryDossier the atom of Side 2. It links
    back to a DeliveryDossier or a RecoveryRecord through the claim, but
    never writes to either. Side 5 reads other sides' verdicts; it does not
    modify them. If Side 5 is absent, Sides 1-4 produce identical output.

    CorroborationDossier accumulates intelligence through stages 13-16:
        Stage 13 — Evidence ingestion (provenance validated on every artifact)
        Stage 14 — Expected-evidence resolution (per outcome type, per country)
        Stage 15 — Graph construction and rule evaluation (16 rules, 5 layers)
        Stage 16 — Evidence gating (corroboration verdict)

    The five evidence rule layers:
        Corroboration Sufficiency — EVD-CORR-001/002/003
        Expected Evidence Absence — EVD-ABS-001/002/003/004
        Contradiction Detection   — EVD-CON-001/002/003/004
        Source Integrity          — EVD-SRC-001/002/003
        Coverage Assessment       — EVD-COV-001/002   (capacity, never contradiction)

    The four evidence EVG dimensions (Layer 5 deliberately absent):
        CORROBORATION_SUFFICIENCY
        EXPECTED_ABSENCE
        CONTRADICTION
        SOURCE_INTEGRITY

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# ═══════════════════════════════════════════════════════════


class EvidenceClass(Enum):
    """The six independent evidence classes, ordered by manipulation difficulty.

    The class number is NOT a weight. Weights come from the jurisdiction
    profile, because which sources are trustworthy — and which exist at all —
    is a property of the jurisdiction, not of the class.

    1 INSTITUTIONAL      Disbursement records, procurement documents,
                         implementing partner reports, government sign-offs.
                         Low manipulation difficulty: produced by parties with
                         an incentive to report success.

    2 THIRD_PARTY_ADMIN  Construction permits, customs and import records,
                         utility connection records, professional licensing
                         registries, contractor tax filings.
                         Medium: held by institutions not party to the contract.

    3 GEOSPATIAL         Satellite imagery time-series over site coordinates,
                         change detection on the site polygon.
                         High: a physical footprint either appeared or it did not.

    4 FIELD_VERIFICATION Independent third-party monitor visits, geotagged and
                         timestamped and hashed photographs.
                         High — but ONLY when the monitor is independent and
                         randomly assigned. A monitor chosen by the implementing
                         partner is Class 1 evidence wearing Class 4 clothing,
                         which is what EVD-SRC-003 exists to catch.

    5 BENEFICIARY_SIDE   Health information system patient records, national
                         education enrolment systems, mobile-money transaction
                         records, SMS spot surveys to randomly sampled recipients.
                         High: the data path does not route through the
                         implementing partner.

    6 ADVERSARIAL_OPEN   Local journalism, civil society monitoring, community
                         complaint mechanisms, procurement protest filings.
                         Variable: absence of an expected signal is itself signal.
    """
    INSTITUTIONAL = "institutional"
    THIRD_PARTY_ADMIN = "third_party_admin"
    GEOSPATIAL = "geospatial"
    FIELD_VERIFICATION = "field_verification"
    BENEFICIARY_SIDE = "beneficiary_side"
    ADVERSARIAL_OPEN = "adversarial_open"


# Total number of evidence classes. Used as the denominator of
# corroboration capacity. Defined once so the two cannot drift apart.
EVIDENCE_CLASS_COUNT = len(EvidenceClass)


class OutcomeType(Enum):
    """What kind of thing was claimed. Determines the expected-evidence map.

    A road and a cash transfer leave completely different traces. Asking for
    a construction permit on a cash transfer programme would manufacture a
    false absence, so the expected-evidence map is keyed on this type.
    """
    FACILITY_CONSTRUCTION = "facility_construction"   # hospital, school, clinic
    INFRASTRUCTURE_LINEAR = "infrastructure_linear"   # road, pipeline, transmission
    WATER_SANITATION = "water_sanitation"
    EQUIPMENT_SUPPLY = "equipment_supply"
    SERVICE_DELIVERY = "service_delivery"             # training, healthcare provision
    CASH_TRANSFER = "cash_transfer"
    CAPACITY_BUILDING = "capacity_building"


class EvidenceStatus(Enum):
    """What happened when a single piece of evidence was sought.

    The distinction between ABSENT and UNQUERYABLE carries the entire
    intellectual honesty of Side 5:

        ABSENT      — the source exists in this jurisdiction, it was queried,
                      and the expected record was not there. This is a finding.
        UNQUERYABLE — the source does not exist in this jurisdiction, so no
                      query was possible. This is NOT a finding. It reduces
                      corroboration capacity and widens the confidence bounds
                      on whatever conclusion is eventually reached.

    Collapsing these two would make SUNLIGHT punish poor countries for having
    thin digital infrastructure. Every rule in Layer 2 must check queryability
    before treating an absence as meaningful.
    """
    OBSERVED = "observed"            # evidence found and consistent with the claim
    ABSENT = "absent"                # evidence expected, source queryable, not found
    CONTRADICTORY = "contradictory"  # evidence found and inconsistent with the claim
    UNQUERYABLE = "unqueryable"      # source unavailable in this jurisdiction
    STALE = "stale"                  # found, but older than the freshness threshold


class CorroborationVerdict(Enum):
    """The Side 5 verdict. FOUR members, and the fourth is the point.

    VERIFIED     — strong independent corroboration, no contradictions.
    PARTIAL      — some corroboration, gaps remain, no contradictions.
    UNVERIFIED   — insufficient queryable evidence to conclude anything.
                   This is an honest statement about SUNLIGHT's reach in this
                   jurisdiction. It is not a negative finding about the claim.
    CONTRADICTED — independent evidence actively contradicts the claim.

    UNVERIFIED must never be conflated with CONTRADICTED, in code, in the
    API, in reports, or in aggregate counts. A country office with thin
    registries should accumulate UNVERIFIED verdicts and suffer nothing for it.
    """
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNVERIFIED = "unverified"
    CONTRADICTED = "contradicted"


class EvidenceStage(Enum):
    """Where a corroboration dossier is in the Side 5 pipeline."""
    INGESTED = "evidence_ingested"                # Stage 13: artifacts admitted
    RESOLVED = "evidence_resolved"                # Stage 14: expectations resolved
    GRAPHED = "evidence_graphed"                  # Stage 15: graph + rules
    GATED = "evidence_gated"                      # Stage 16: verdict issued
    COMPLETE = "evidence_complete"
    FAILED = "evidence_failed"


class EvidenceDimension(Enum):
    """Dimensions evaluated by the evidence EVG gate.

    FOUR dimensions, mapped to the first four rule layers. There is
    deliberately no COVERAGE dimension: Layer 5 measures how much of the
    evidence space was reachable, which is a fact about SUNLIGHT rather than
    about the claim, and giving it a dimension would give it a path to an
    adverse verdict.
    """
    CORROBORATION_SUFFICIENCY = "corroboration_sufficiency"
    EXPECTED_ABSENCE = "expected_absence"
    CONTRADICTION = "contradiction"
    SOURCE_INTEGRITY = "source_integrity"


class EvidenceRuleLayer(Enum):
    """The five evidence rule layers.

    COVERAGE is structurally different from the other four: it measures how
    much of the evidence space was reachable, not whether the claim is true.
    It is deliberately NOT mapped to an EVG dimension. See evidence_evg.py.
    """
    CORROBORATION = "corroboration"
    ABSENCE = "absence"
    CONTRADICTION = "contradiction"
    SOURCE = "source"
    COVERAGE = "coverage"


# The layers that can contribute to a CONTRADICTED verdict. COVERAGE is
# absent from this set by design, and evidence_evg.py asserts it stays absent.
CONTRADICTION_CAPABLE_LAYERS = frozenset({
    EvidenceRuleLayer.CORROBORATION.value,
    EvidenceRuleLayer.ABSENCE.value,
    EvidenceRuleLayer.CONTRADICTION.value,
    EvidenceRuleLayer.SOURCE.value,
})


# ═══════════════════════════════════════════════════════════
# SECTION 2: PROVENANCE
# Chain of custody. Nothing enters the graph without it.
# ═══════════════════════════════════════════════════════════


@dataclass
class Provenance:
    """Chain of custody for a single evidence artifact.

    Every artifact entering the corroboration graph must carry one of these,
    including artifacts whose status is ABSENT or UNQUERYABLE. That is not a
    contradiction in terms: for a negative result the provenance attests to
    the QUERY rather than to content — which registry was asked, when, and
    the hash of the response that came back empty.

    This is what makes "absence is a positive finding" defensible rather than
    merely assertive. An absence with no record of who was asked and when is
    an assumption, not evidence, and Side 5 will not accept it.
    """
    source_id: str                      # canonical identifier for the source system/org
    source_name: str
    retrieval_timestamp: datetime
    content_hash: str                   # digest of the artifact content, or of the
                                        # empty query response for a negative result
    source_url: Optional[str] = None
    capture_timestamp: Optional[datetime] = None   # for photographs
    capture_latitude: Optional[float] = None
    capture_longitude: Optional[float] = None
    hash_algorithm: str = "sha256"

    def verify_hash(self, content: bytes) -> bool:
        """Recompute the digest and compare. Tampering after ingestion is detectable.

        Returns False rather than raising on an unrecognised algorithm, so that
        a malformed provenance record fails verification instead of crashing the
        pipeline. EVD-SRC-002 turns that False into a structural finding.
        """
        # Deferred import: provenance.py imports this module for its type
        # signatures, so importing it at module scope would cycle. This is the
        # same idiom delivery_rules.py uses for jurisdiction_profile.
        from provenance import compute_hash, ProvenanceError

        try:
            recomputed = compute_hash(content, algorithm=self.hash_algorithm)
        except ProvenanceError:
            return False
        return _constant_time_equals(recomputed, self.content_hash)

    @property
    def has_geotag(self) -> bool:
        """True when this provenance carries capture coordinates.

        Callers must check this before interpreting a geotag validation result:
        a missing geotag and a geotag 4 km from the site are entirely different
        findings, and only the second one is a contradiction.
        """
        return (
            self.capture_latitude is not None
            and self.capture_longitude is not None
        )


def _constant_time_equals(a: str, b: str) -> bool:
    """Compare two hex digests without leaking length or content through timing.

    Digest comparison is not a secret-dependent operation in the current
    threat model, but hash comparison drifting into a timing oracle is a
    classic way for an audit tool to become an attack surface later.
    """
    import hmac
    return hmac.compare_digest(a or "", b or "")


# ═══════════════════════════════════════════════════════════
# SECTION 3: EVIDENCE INPUTS
# These represent what Side 5 ingests at Stage 13 and 14.
# ═══════════════════════════════════════════════════════════


@dataclass
class EvidenceArtifact:
    """A single piece of evidence — or a single documented absence of one.

    An artifact with status ABSENT is not an empty record. It is the positive
    assertion that a named, queryable source was asked and returned nothing,
    backed by the provenance of that query.
    """
    artifact_id: str
    evidence_class: EvidenceClass
    claim_id: str                       # which claim this artifact speaks to
    description: str                    # what this artifact is
    status: EvidenceStatus
    observed_value: Optional[str] = None
    observed_date: Optional[date] = None
    provenance: Optional[Provenance] = None
    source_party_id: Optional[str] = None   # for independence analysis
    notes: Optional[str] = None

    # Magnitude as a number, when this artifact measures one — 50 observed
    # beds against 200 claimed. Deliberately separate from observed_value:
    # deriving a magnitude by parsing free text would make a contradiction
    # finding depend on string formatting, and "2024" parses as a number.
    # If it is not set here, no magnitude rule considers this artifact.
    observed_magnitude: Optional[float] = None

    # Result of re-verifying the content hash after ingestion.
    #   None  — never re-checked
    #   True  — re-checked and intact
    #   False — hash mismatch; the artifact was modified after ingestion
    # None and False are different: "not checked" is not "found sound", and
    # only False is a chain-of-custody finding.
    integrity_verified: Optional[bool] = None

    @property
    def corroborates(self) -> bool:
        """True only when this artifact actively supports the claim.

        STALE evidence does not corroborate — it is evidence that the claim
        was true at some point outside the window we care about.
        """
        return self.status == EvidenceStatus.OBSERVED

    @property
    def contradicts(self) -> bool:
        """True only when this artifact actively contradicts the claim.

        Note what is excluded: ABSENT and UNQUERYABLE. Absence is handled by
        the Layer 2 rules, which check queryability first. Nothing in Side 5
        converts a missing record into a contradiction at the artifact level.
        """
        return self.status == EvidenceStatus.CONTRADICTORY


@dataclass
class ExpectedEvidence:
    """What SHOULD exist if the claim is true.

    Defined per outcome type per jurisdiction, because the answer differs:
    a facility built in a country with a digital land registry and utility
    connection database leaves traces that the same facility in a country
    without them cannot leave. Expecting the second country to produce the
    first country's evidence is exactly the failure mode Side 5 is built
    to avoid, which is what queryable_in_jurisdiction is for.
    """
    expectation_id: str
    evidence_class: EvidenceClass
    description: str                    # e.g. "municipal construction permit"
    required: bool = True               # if True, absence is a candidate contradiction
    expected_by_month: Optional[int] = None   # relative to award date
    queryable_in_jurisdiction: bool = True    # False if this source does not exist locally

    @property
    def absence_is_meaningful(self) -> bool:
        """Whether a missing observation against this expectation is a finding.

        Absence only means something when the evidence was both required and
        actually reachable. An unqueryable expectation reduces corroboration
        capacity; it never produces a contradiction.
        """
        return self.required and self.queryable_in_jurisdiction


@dataclass
class OutcomeClaim:
    """The thing being verified.

    Originates from a Side 2 DeliveryDossier outcome or a Side 4 impact
    report claim. Side 5 reads it and never writes back to the source.
    """
    claim_id: str
    contract_id: str
    outcome_type: OutcomeType
    claim_description: str              # "200-bed hospital operational"
    claimed_completion_date: Optional[date] = None
    claimed_magnitude: Optional[float] = None      # 200 (beds), 30000 (beneficiaries)
    claimed_magnitude_unit: Optional[str] = None
    site_latitude: Optional[float] = None
    site_longitude: Optional[float] = None
    country_code: Optional[str] = None
    country_office: Optional[str] = None
    award_date: Optional[date] = None              # anchors expected_by_month offsets
    source_dossier_id: Optional[str] = None        # links to DeliveryDossier
    source_recovery_id: Optional[str] = None       # links to RecoveryRecord if from Side 4

    @property
    def has_site_coordinates(self) -> bool:
        """True when the claim names a location that imagery or a photo can be checked against."""
        return self.site_latitude is not None and self.site_longitude is not None


@dataclass
class SourceIndependence:
    """Models whether two sources are genuinely independent.

    Two documents from the same ministry are ONE source, not two. A prime
    contractor and its subcontractor are ONE source. An implementing partner
    and the monitor it selected are ONE source.

    Without this collapse, corroboration count is trivially inflatable: submit
    six reports from six departments of the same organisation and the claim
    appears to be corroborated across six classes. The graph collapses them
    to one before anything is counted.
    """
    party_id: str
    party_name: str
    party_type: str                     # "implementing_partner", "government_agency",
                                        # "commercial_provider", "civil_society", etc.
    linked_parties: List[str] = field(default_factory=list)  # party_ids NOT independent of this one
    is_contract_party: bool = False     # party to the contract being verified

    # Field-verification monitors only. A monitor is Class 4 evidence — near
    # the top of the manipulation-difficulty ranking — but ONLY when it was
    # independently and randomly assigned. A monitor chosen by the party
    # being monitored is Class 1 evidence wearing Class 4 clothing.
    #   None  — not a monitor, or assignment method unrecorded
    #   True  — randomly assigned from an independent pool
    #   False — selected, not randomised
    randomly_assigned: Optional[bool] = None
    selected_by: Optional[str] = None   # party_id that chose this monitor, if any

    @property
    def can_corroborate_independently(self) -> bool:
        """A party to the contract cannot independently corroborate its own delivery."""
        return not self.is_contract_party


# ═══════════════════════════════════════════════════════════
# SECTION 4: ENGINE RESULTS
# Each Side 5 stage writes its result here.
# ═══════════════════════════════════════════════════════════


@dataclass
class EvidenceRuleResult:
    """What happened when a single evidence rule was evaluated.

    Mirrors DeliveryRuleResult field for field, plus `layer` carrying an
    EvidenceRuleLayer value so the EVG can tell contradiction-capable
    layers from the coverage layer without a second lookup.
    """
    rule_id: str                        # e.g. "EVD-CORR-001"
    layer: str                          # EvidenceRuleLayer value
    fired: bool
    evidence: str = ""                  # human-readable evidence string
    legal_basis: str = ""               # citation from the jurisdiction profile
    confidence: float = 0.0
    detail: str = ""
    recommendation: str = ""


@dataclass
class EvidenceGraphResult:
    """Result of corroboration graph construction (Stage 15)."""
    node_count: int = 0
    edge_count: int = 0
    nodes: List[Dict] = field(default_factory=list)
    edges: List[Dict] = field(default_factory=list)


@dataclass
class EvidenceRulesResult:
    """Aggregate result of all 16 evidence rules (Stage 15)."""
    rules_evaluated: int = 0
    rules_fired: int = 0
    rule_results: List[EvidenceRuleResult] = field(default_factory=list)
    layer_summary: Dict[str, int] = field(default_factory=dict)  # layer → count fired


@dataclass
class EvidenceDimensionResult:
    """Result of evaluating a single evidence EVG dimension."""
    dimension: EvidenceDimension
    fired: bool
    observed_value: Optional[float] = None
    threshold: Optional[float] = None
    detail: str = ""


@dataclass
class EvidenceGateOutcome:
    """Full evidence EVG outcome with per-dimension traceability.

    Carries the capacity figures alongside the verdict because a Side 5
    verdict is not interpretable without them. "UNVERIFIED" means something
    entirely different at 2 of 6 classes reachable than at 6 of 6, and a
    report that states the verdict without the reach is misleading by
    omission.
    """
    verdict: CorroborationVerdict
    dimensions_fired: int
    dimension_results: List[EvidenceDimensionResult] = field(default_factory=list)
    coverage_findings: List[str] = field(default_factory=list)   # fired Layer 5 rule ids
    contradictions: List[Dict] = field(default_factory=list)
    confidence: float = 0.0
    corroboration_capacity: float = 0.0
    classes_queryable: int = 0
    independent_classes_corroborating: int = 0
    methodology_note: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 5: THE CORROBORATION DOSSIER
# One object per claim. Links to DeliveryDossier / RecoveryRecord
# through the claim. Does not modify either.
# ═══════════════════════════════════════════════════════════


@dataclass
class CorroborationDossier:
    """
    THE ATOM OF SIDE 5.

    One claimed outcome. One dossier. Every evidence engine reads what it
    needs and writes what it produces, exactly as DeliveryDossier does for
    Side 2.

    Field order note: `claim` is first and has no default, unlike the other
    dossiers in this codebase, because a corroboration dossier without a
    claim has nothing to corroborate and should not be constructible. The
    identifier keeps the house uuid4 default_factory.
    """

    # ── Identity ──
    claim: OutcomeClaim
    dossier_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # ── Expected vs observed ──
    expected_evidence: List[ExpectedEvidence] = field(default_factory=list)
    artifacts: List[EvidenceArtifact] = field(default_factory=list)
    source_registry: List[SourceIndependence] = field(default_factory=list)

    # Artifacts refused at Stage 13 for want of valid provenance. They are
    # kept, not deleted: they must not corroborate anything, and they must
    # still be visible to EVD-SRC-002 and to whoever submitted them. Silent
    # deletion would turn a chain-of-custody problem into an absence.
    rejected_artifacts: List[EvidenceArtifact] = field(default_factory=list)

    # ── Graph and rules ──
    graph: Optional[EvidenceGraphResult] = None
    rules_result: Optional[EvidenceRulesResult] = None
    gate_outcome: Optional["EvidenceGateOutcome"] = None

    # ── Pipeline state ──
    stage: EvidenceStage = EvidenceStage.INGESTED
    errors: List[Dict] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = ""
    processing_ms: Dict[str, float] = field(default_factory=dict)

    # ── Verdict ──
    verdict: Optional[CorroborationVerdict] = None
    confidence: float = 0.0
    contradictions: List[Dict] = field(default_factory=list)
    independent_classes_corroborating: int = 0
    classes_queryable: int = 0
    classes_total: int = EVIDENCE_CLASS_COUNT
    evaluated_at: Optional[datetime] = None

    # ── Provenance of the analysis itself ──
    methodology_version: str = "SUNLIGHT Side 5 v1.0 | Evidence EVG v1.0"
    disclaimer: str = (
        "Structural corroboration finding — not an allegation. "
        "A CONTRADICTED verdict states that independent evidence is "
        "inconsistent with the claim as recorded; it does not assert "
        "what did or did not physically occur."
    )

    def advance(self, stage: EvidenceStage, duration_ms: float = 0):
        """Move to the next pipeline stage. Records timing."""
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if duration_ms > 0:
            self.processing_ms[stage.value] = duration_ms

    def fail(self, stage: EvidenceStage, error: str):
        """Record a failure at a specific stage."""
        self.stage = EvidenceStage.FAILED
        self.errors.append({
            "stage": stage.value,
            "error": error,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self.updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def corroboration_capacity(self) -> float:
        """What fraction of the evidence space could even be queried here.

        Low capacity means findings carry wider confidence bounds, and below
        the profile floor it means no adverse conclusion may be drawn at all.
        This is SUNLIGHT being honest about its own reach rather than
        mistaking its blind spots for the absence of evidence.

        Returns 0.0 when classes_total is zero rather than raising, and
        clamps to [0.0, 1.0] so a malformed count cannot manufacture
        capacity that would unlock a CONTRADICTED verdict.
        """
        if self.classes_total <= 0:
            return 0.0
        raw = self.classes_queryable / self.classes_total
        return max(0.0, min(1.0, raw))

    @property
    def classes_present(self) -> set:
        """The distinct evidence classes represented among ingested artifacts."""
        return {a.evidence_class for a in self.artifacts}

    def artifacts_in_class(self, evidence_class: EvidenceClass) -> List[EvidenceArtifact]:
        """All artifacts belonging to one evidence class."""
        return [a for a in self.artifacts if a.evidence_class == evidence_class]

    def source(self, party_id: str) -> Optional[SourceIndependence]:
        """Look up a registered source by party id."""
        for s in self.source_registry:
            if s.party_id == party_id:
                return s
        return None
