"""
SUNLIGHT Side 5 — Evidence Rule Engine
=========================================

Deterministic corroboration analysis. 16 rules across 5 layers.
Same evidence + same profile = same result. Forever.

Architecture:
    Mirrors delivery_rules.py exactly:
    - build_evidence_rules(profile) → List[EvidenceRule]
    - Closure pattern: rules close over the profile at construction time
    - Each rule: CONDITION → EVIDENCE → RESULT
    - EvidenceRuleEngine.evaluate() wraps every lambda, so a throwing rule
      degrades to not-fired rather than killing the analysis

Rule Layers:
    Layer 1: Corroboration Sufficiency (EVD-CORR-001/002/003)
        Is there enough genuinely independent support for the claim?
    Layer 2: Expected Evidence Absence (EVD-ABS-001/002/003/004)
        Was expected evidence queried and found missing?
    Layer 3: Contradiction Detection (EVD-CON-001/002/003/004)
        Does evidence actively conflict with the claim?
    Layer 4: Source Integrity (EVD-SRC-001/002/003)
        Can the evidence chain itself be trusted?
    Layer 5: Coverage Assessment (EVD-COV-001/002)
        How much of the evidence space was reachable here?

THE LAYER 5 CONSTRAINT — read before adding or moving any rule:
    Layer 5 measures SUNLIGHT's reach, not the claim's truth. Its rules must
    never contribute to a CONTRADICTED verdict. That is enforced two ways:

      1. Structurally — evidence_evg.py maps only the first four layers to
         dimensions, and CONTRADICTION_CAPABLE_LAYERS in evidence_schema.py
         omits "coverage". A Layer 5 rule has no path to an adverse verdict.
      2. By test — assert_layer_five_is_isolated() below is called from the
         test suite and fails loudly if a coverage rule is ever given a
         contradiction-capable layer.

    The reason is not stylistic. A country with no digital land registry, no
    utility connection database and no health information system cannot
    produce the evidence that would corroborate a TRUE claim. If thin
    infrastructure could push a verdict toward CONTRADICTED, SUNLIGHT would
    systematically find against the poorest countries for being poor.

THE QUERYABILITY GUARD:
    Every Layer 2 rule checks that the evidence it wants was actually
    reachable before treating its absence as a finding. An absence is only
    meaningful when a source exists, was asked, and returned nothing —
    which is why each of these rules requires BOTH a required-and-queryable
    expectation AND a documented ABSENT artifact carrying the provenance of
    the query that came back empty.

Determinism note:
    No rule reads the wall clock. EVD-COV-002 measures staleness against the
    claim's own dates rather than against today, because a rule whose output
    changes as time passes is not reproducible, and a finding that cannot be
    reproduced cannot be audited.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
Rule Set Version: EVR-2026-07-001
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

from evidence_graph import IndependenceResolver, derive_queryable_classes
from evidence_schema import (
    CONTRADICTION_CAPABLE_LAYERS,
    CorroborationDossier,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceRuleLayer,
    EvidenceRuleResult,
    EvidenceRulesResult,
    EvidenceStatus,
    OutcomeType,
)
from provenance import is_ingestible


# ═══════════════════════════════════════════════════════════
# SECTION 1: RULE DEFINITION
# ═══════════════════════════════════════════════════════════


@dataclass
class EvidenceRule:
    """A single corroboration rule.

    Mirrors delivery_rules.DeliveryRule, with one addition: recommendation.
    A Side 5 finding tells an institution what evidence would resolve it —
    "commission an independent site verification" is actionable, "structural
    contradiction detected" is not.
    """
    rule_id: str                        # e.g. "EVD-CORR-001"
    layer: str                          # EvidenceRuleLayer value
    name: str
    description: str
    evidence_template: str              # legal/regulatory citation
    condition: Callable[[CorroborationDossier], bool]
    build_evidence: Callable[[CorroborationDossier], str]
    confidence: Callable[[CorroborationDossier], float]
    recommendation: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 2: THRESHOLD DEFAULTS
# Used when the jurisdiction profile supplies no evidence-
# specific parameters. Conservative — an institutional
# credibility floor, not a detection-maximising setting.
# ═══════════════════════════════════════════════════════════

DEFAULT_MIN_INDEPENDENT_CLASSES = 3
DEFAULT_MIN_QUERYABLE_CLASSES = 3
DEFAULT_MIN_CORROBORATION_CAPACITY = 0.5
DEFAULT_TIMELINE_TOLERANCE_DAYS = 90
DEFAULT_MAGNITUDE_TOLERANCE = 0.20
DEFAULT_BENEFICIARY_TOLERANCE = 0.25
DEFAULT_FIELD_VERIFICATION_WINDOW_MONTHS = 6
DEFAULT_EVIDENCE_FRESHNESS_MONTHS = 18
DEFAULT_GEOTAG_TOLERANCE_METERS = 250.0

# Mean days per month. Used only to turn profile month-thresholds into day
# comparisons; nothing here needs calendar precision.
DAYS_PER_MONTH = 30.44

# Outcome types that leave a physical footprint. Geospatial absence is only
# meaningful for these — a cash transfer programme builds nothing, and
# expecting satellite change detection to show one would manufacture a
# finding out of a category error.
PHYSICAL_FOOTPRINT_OUTCOMES = frozenset({
    OutcomeType.FACILITY_CONSTRUCTION,
    OutcomeType.INFRASTRUCTURE_LINEAR,
    OutcomeType.WATER_SANITATION,
})

# The three classes whose data path does not route through the implementing
# partner. A claim supported by none of these is provider-attested only.
NON_PROVIDER_CLASSES = frozenset({
    EvidenceClass.THIRD_PARTY_ADMIN,
    EvidenceClass.FIELD_VERIFICATION,
    EvidenceClass.BENEFICIARY_SIDE,
})


def _get_evidence_param(profile, param: str, default):
    """Safely read an evidence parameter from a jurisdiction profile.

    Follows the precedent set by delivery_rules._get_delivery_param: read
    through getattr with a conservative default, so the rules work against
    profiles that predate the evidence extension and against any profile-like
    object a caller supplies.
    """
    return getattr(profile, param, default)


# ═══════════════════════════════════════════════════════════
# SECTION 3: SHARED PREDICATES
# ═══════════════════════════════════════════════════════════


def _queryable_classes(dossier: CorroborationDossier) -> set:
    return derive_queryable_classes(dossier)


def _class_is_queryable(dossier: CorroborationDossier, cls: EvidenceClass) -> bool:
    """Was this evidence class reachable in this jurisdiction at all?

    The gate on every absence finding. Absence of an unreachable source is a
    limit on SUNLIGHT, not a fact about the claim.
    """
    return cls in _queryable_classes(dossier)


def _expects(dossier: CorroborationDossier, cls: EvidenceClass) -> bool:
    """Is there a required, locally-queryable expectation in this class?"""
    return any(
        exp.evidence_class == cls and exp.absence_is_meaningful
        for exp in dossier.expected_evidence
    )


def _documented_absence(dossier: CorroborationDossier, cls: EvidenceClass) -> bool:
    """Is there an ABSENT artifact in this class?

    ABSENT means a named source was queried and returned nothing, carrying
    the provenance of that query. An expectation with no artifact at all is
    NOT this: it was never asked, and never-asked is not evidence.
    """
    return any(
        a.evidence_class == cls and a.status == EvidenceStatus.ABSENT
        for a in dossier.artifacts
    )


def _meaningful_absence(dossier: CorroborationDossier, cls: EvidenceClass) -> bool:
    """The full Layer 2 predicate: expected, reachable, asked, and not found."""
    return (
        _class_is_queryable(dossier, cls)
        and _expects(dossier, cls)
        and _documented_absence(dossier, cls)
    )


def _artifacts_in(dossier: CorroborationDossier, cls: EvidenceClass) -> List[EvidenceArtifact]:
    return [a for a in dossier.artifacts if a.evidence_class == cls]


def _reference_date(dossier: CorroborationDossier) -> Optional[date]:
    """The date findings are measured against.

    Claimed completion first, award date as fallback. Never today: a rule
    that reads the wall clock produces a different answer next month, and a
    finding that cannot be reproduced cannot be audited.
    """
    return dossier.claim.claimed_completion_date or dossier.claim.award_date


def _relative_deviation(observed: float, claimed: float) -> Optional[float]:
    """|observed - claimed| / claimed, or None when claimed is zero."""
    if claimed is None or claimed == 0:
        return None
    return abs(observed - claimed) / abs(claimed)


def _magnitude_observations(
    dossier: CorroborationDossier,
    exclude: Optional[frozenset] = None,
) -> List[EvidenceArtifact]:
    """Artifacts that actually measured a magnitude.

    Only artifacts with observed_magnitude explicitly set are considered.
    Parsing observed_value would make a contradiction finding depend on
    string formatting, and a year renders as a perfectly good float.
    """
    exclude = exclude or frozenset()
    return [
        a for a in dossier.artifacts
        if a.observed_magnitude is not None
        and a.evidence_class not in exclude
        and a.status in (EvidenceStatus.OBSERVED, EvidenceStatus.CONTRADICTORY)
    ]


def _attributed(dossier: CorroborationDossier) -> List[EvidenceArtifact]:
    return [a for a in dossier.artifacts if a.source_party_id]


# ═══════════════════════════════════════════════════════════
# SECTION 4: RULE BUILDER — closure pattern
# ═══════════════════════════════════════════════════════════


def build_evidence_rules(profile) -> List[EvidenceRule]:
    """Build all 16 evidence rules with jurisdiction-specific parameters.

    Uses the same closure pattern as delivery_rules.build_delivery_rules and
    tca_rules.build_rules: the rules' lambdas close over the profile, binding
    jurisdiction parameters at construction time.
    """
    rules: List[EvidenceRule] = []

    min_independent = _get_evidence_param(
        profile, "min_independent_classes", DEFAULT_MIN_INDEPENDENT_CLASSES)
    min_queryable = _get_evidence_param(
        profile, "min_queryable_classes", DEFAULT_MIN_QUERYABLE_CLASSES)
    timeline_tolerance = _get_evidence_param(
        profile, "timeline_tolerance_days", DEFAULT_TIMELINE_TOLERANCE_DAYS)
    magnitude_tolerance = _get_evidence_param(
        profile, "magnitude_tolerance", DEFAULT_MAGNITUDE_TOLERANCE)
    beneficiary_tolerance = _get_evidence_param(
        profile, "beneficiary_tolerance", DEFAULT_BENEFICIARY_TOLERANCE)
    field_window_months = _get_evidence_param(
        profile, "field_verification_window_months",
        DEFAULT_FIELD_VERIFICATION_WINDOW_MONTHS)
    freshness_months = _get_evidence_param(
        profile, "evidence_freshness_months", DEFAULT_EVIDENCE_FRESHNESS_MONTHS)

    citations = _get_evidence_param(profile, "evidence_legal_citations", {}) or {}

    evaluation_cite = citations.get(
        "evaluation_standards",
        "UNEG Norms and Standards for Evaluation, Norm 4 (Credibility); "
        "UNDP POPP — Programme and Project Management, Monitoring and Evaluation"
    )
    verification_cite = citations.get(
        "verification",
        "OECD-DAC Evaluation Criteria — Effectiveness and Impact; "
        "UNDP POPP — Assurance and Verification of Implementing Partners"
    )
    results_cite = citations.get(
        "results_reporting",
        "UNEG Norms and Standards for Evaluation, Norm 6 (Evaluation Ethics); "
        "OECD-DAC Quality Standards for Development Evaluation — Reliability of Data"
    )
    audit_cite = citations.get(
        "audit",
        "UNCAC Art. 9(2) — Public finance management; "
        "INTOSAI ISSAI 3000 — Performance Audit Standards, Evidence Requirements"
    )
    coverage_cite = citations.get(
        "coverage_disclosure",
        "UNEG Norms and Standards for Evaluation, Norm 7 (Transparency); "
        "OECD-DAC Quality Standards — Limitations and Data Constraints Disclosure"
    )

    # ─────────────────────────────────────────
    # LAYER 1: CORROBORATION SUFFICIENCY
    # ─────────────────────────────────────────

    rules.append(EvidenceRule(
        rule_id="EVD-CORR-001",
        layer=EvidenceRuleLayer.CORROBORATION.value,
        name="Insufficient independent classes",
        description=(
            "Genuinely independent corroboration of the claim falls below the "
            "jurisdiction threshold, after linked sources are collapsed"
        ),
        evidence_template=evaluation_cite,
        condition=lambda d: d.independent_classes_corroborating < min_independent,
        build_evidence=lambda d: (
            f"{d.independent_classes_corroborating} independent corroborating "
            f"source(s) after independence collapse, against a threshold of "
            f"{min_independent}; corroboration capacity "
            f"{d.corroboration_capacity:.0%}"
        ),
        confidence=lambda d: min(
            0.90,
            0.45 + 0.15 * max(0, min_independent - d.independent_classes_corroborating)
        ),
        recommendation=(
            "Obtain corroboration from an evidence class whose data path does "
            "not route through a party to the contract."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-CORR-002",
        layer=EvidenceRuleLayer.CORROBORATION.value,
        name="Single-source claim",
        description=(
            "All submitted evidence traces to one party once linked sources "
            "are collapsed into a single independence group"
        ),
        evidence_template=evaluation_cite,
        condition=lambda d: _single_source(d),
        build_evidence=lambda d: _single_source_evidence(d),
        confidence=lambda d: 0.75 if _single_source(d) else 0.0,
        recommendation=(
            "Corroborate from a second party with no ownership, contractual "
            "or supervisory relationship to the first."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-CORR-003",
        layer=EvidenceRuleLayer.CORROBORATION.value,
        name="Provider-side evidence only",
        description=(
            "No third-party administrative, field verification or "
            "beneficiary-side evidence supports the claim, though at least "
            "one of those classes is reachable in this jurisdiction"
        ),
        evidence_template=verification_cite,
        condition=lambda d: _provider_side_only(d),
        build_evidence=lambda d: _provider_side_only_evidence(d),
        confidence=lambda d: 0.70 if _provider_side_only(d) else 0.0,
        recommendation=(
            "Query an available non-provider class — administrative registry, "
            "independent monitor, or recipient-side records."
        ),
    ))

    # ─────────────────────────────────────────
    # LAYER 2: EXPECTED EVIDENCE ABSENCE
    # Every rule here checks queryability first.
    # ─────────────────────────────────────────

    rules.append(EvidenceRule(
        rule_id="EVD-ABS-001",
        layer=EvidenceRuleLayer.ABSENCE.value,
        name="Missing administrative record",
        description=(
            "A required third-party administrative record — permit, licence, "
            "utility connection, customs entry — was queried in a jurisdiction "
            "where the registry exists, and was not found"
        ),
        evidence_template=audit_cite,
        condition=lambda d: _meaningful_absence(d, EvidenceClass.THIRD_PARTY_ADMIN),
        build_evidence=lambda d: _absence_evidence(d, EvidenceClass.THIRD_PARTY_ADMIN),
        confidence=lambda d: min(
            0.88,
            0.55 + 0.11 * _absent_count(d, EvidenceClass.THIRD_PARTY_ADMIN)
        ),
        recommendation=(
            "Request the permit or connection reference from the implementing "
            "partner and re-query the registry against it."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-ABS-002",
        layer=EvidenceRuleLayer.ABSENCE.value,
        name="Missing geospatial change",
        description=(
            "A physical works outcome was claimed, and satellite change "
            "detection over the site polygon shows no structural change "
            "across the claimed build window"
        ),
        evidence_template=verification_cite,
        condition=lambda d: (
            d.claim.outcome_type in PHYSICAL_FOOTPRINT_OUTCOMES
            and _meaningful_absence(d, EvidenceClass.GEOSPATIAL)
        ),
        build_evidence=lambda d: (
            f"{d.claim.outcome_type.value} claimed; "
            + _absence_evidence(d, EvidenceClass.GEOSPATIAL)
        ),
        confidence=lambda d: 0.85,
        recommendation=(
            "Confirm the site coordinates on record, then re-run change "
            "detection against the corrected polygon before treating this as "
            "settled — a wrong coordinate produces the same signature."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-ABS-003",
        layer=EvidenceRuleLayer.ABSENCE.value,
        name="Missing beneficiary-side signal",
        description=(
            "Recipient-side systems returned zero records where service "
            "delivery was claimed and the system is queryable locally"
        ),
        evidence_template=results_cite,
        condition=lambda d: _meaningful_absence(d, EvidenceClass.BENEFICIARY_SIDE),
        build_evidence=lambda d: _absence_evidence(d, EvidenceClass.BENEFICIARY_SIDE),
        confidence=lambda d: 0.82,
        recommendation=(
            "Verify the facility or programme identifier used in the query "
            "against the recipient-side system's own registry."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-ABS-004",
        layer=EvidenceRuleLayer.ABSENCE.value,
        name="Missing field verification",
        description=(
            "No independent monitor visit is recorded within the jurisdiction "
            "field verification window"
        ),
        evidence_template=verification_cite,
        condition=lambda d: _missing_field_verification(d, field_window_months),
        build_evidence=lambda d: _missing_field_verification_evidence(d, field_window_months),
        confidence=lambda d: 0.65,
        recommendation=(
            "Commission an independent site verification with a randomly "
            "assigned monitor."
        ),
    ))

    # ─────────────────────────────────────────
    # LAYER 3: CONTRADICTION DETECTION
    # ─────────────────────────────────────────

    rules.append(EvidenceRule(
        rule_id="EVD-CON-001",
        layer=EvidenceRuleLayer.CONTRADICTION.value,
        name="Timeline contradiction",
        description=(
            "Corroborating evidence is dated materially earlier than the "
            "claimed completion date, beyond the jurisdiction tolerance"
        ),
        evidence_template=results_cite,
        condition=lambda d: _timeline_contradiction(d, timeline_tolerance),
        build_evidence=lambda d: _timeline_contradiction_evidence(d, timeline_tolerance),
        confidence=lambda d: 0.80,
        recommendation=(
            "Reconcile the claimed completion date against the source record "
            "dates; a reporting-date error and a misstated timeline present "
            "identically here."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-CON-002",
        layer=EvidenceRuleLayer.CONTRADICTION.value,
        name="Magnitude contradiction",
        description=(
            "Observed scale differs from claimed scale beyond the "
            "jurisdiction magnitude tolerance"
        ),
        evidence_template=results_cite,
        condition=lambda d: _magnitude_contradiction(
            d, magnitude_tolerance, exclude=frozenset({EvidenceClass.BENEFICIARY_SIDE})),
        build_evidence=lambda d: _magnitude_contradiction_evidence(
            d, magnitude_tolerance, exclude=frozenset({EvidenceClass.BENEFICIARY_SIDE})),
        confidence=lambda d: _magnitude_confidence(
            d, magnitude_tolerance, frozenset({EvidenceClass.BENEFICIARY_SIDE})),
        recommendation=(
            "Reconcile the claimed figure against the observing source's "
            "measurement basis before treating the difference as material."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-CON-003",
        layer=EvidenceRuleLayer.CONTRADICTION.value,
        name="Geospatial contradiction",
        description=(
            "Imagery shows a physical state inconsistent with the claim — no "
            "structure, a different footprint, or a structure predating award"
        ),
        evidence_template=verification_cite,
        condition=lambda d: _geospatial_contradiction(d),
        build_evidence=lambda d: _geospatial_contradiction_evidence(d),
        confidence=lambda d: 0.88,
        recommendation=(
            "Obtain the imagery time-series and the award date from the "
            "contract record, and confirm the site polygon."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-CON-004",
        layer=EvidenceRuleLayer.CONTRADICTION.value,
        name="Beneficiary count contradiction",
        description=(
            "Claimed beneficiary numbers diverge from recipient-side records "
            "beyond the jurisdiction tolerance"
        ),
        evidence_template=results_cite,
        condition=lambda d: _beneficiary_contradiction(d, beneficiary_tolerance),
        build_evidence=lambda d: _beneficiary_contradiction_evidence(d, beneficiary_tolerance),
        confidence=lambda d: 0.80,
        recommendation=(
            "Compare counting bases — unique beneficiaries against service "
            "contacts is a common and legitimate source of divergence."
        ),
    ))

    # ─────────────────────────────────────────
    # LAYER 4: SOURCE INTEGRITY
    # ─────────────────────────────────────────

    rules.append(EvidenceRule(
        rule_id="EVD-SRC-001",
        layer=EvidenceRuleLayer.SOURCE.value,
        name="Independence violation",
        description=(
            "Sources presented as independent are structurally linked — "
            "shared ownership, common parent ministry, or a subcontracting "
            "relationship — and collapse into one source"
        ),
        evidence_template=evaluation_cite,
        condition=lambda d: _independence_violation(d),
        build_evidence=lambda d: _independence_violation_evidence(d),
        confidence=lambda d: 0.85,
        recommendation=(
            "Treat the linked parties as one source and seek corroboration "
            "outside that group."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-SRC-002",
        layer=EvidenceRuleLayer.SOURCE.value,
        name="Chain of custody break",
        description=(
            "An artifact lacks valid provenance, or its content hash does not "
            "match the hash recorded at ingestion"
        ),
        evidence_template=audit_cite,
        condition=lambda d: _custody_break(d),
        build_evidence=lambda d: _custody_break_evidence(d),
        confidence=lambda d: 0.90,
        recommendation=(
            "Re-retrieve the artifact from its named source and re-hash. "
            "Evidence that cannot be re-verified cannot support a finding in "
            "either direction."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-SRC-003",
        layer=EvidenceRuleLayer.SOURCE.value,
        name="Non-random monitor assignment",
        description=(
            "Field verification exists, but the monitor was selected rather "
            "than randomly assigned — or was chosen by a party to the contract"
        ),
        evidence_template=verification_cite,
        condition=lambda d: _captured_monitor(d),
        build_evidence=lambda d: _captured_monitor_evidence(d),
        confidence=lambda d: 0.78,
        recommendation=(
            "Re-verify with a monitor drawn at random from an independent "
            "roster. A selected monitor's report is provider-side evidence "
            "regardless of the monitor's own conduct."
        ),
    ))

    # ─────────────────────────────────────────
    # LAYER 5: COVERAGE ASSESSMENT
    #
    # Capacity reporting, NOT contradiction. These rules describe how much of
    # the evidence space was reachable. They must never contribute to an
    # adverse verdict — see the module docstring, and the structural
    # enforcement in evidence_evg.py.
    # ─────────────────────────────────────────

    rules.append(EvidenceRule(
        rule_id="EVD-COV-001",
        layer=EvidenceRuleLayer.COVERAGE.value,
        name="Reduced corroboration capacity",
        description=(
            "Fewer evidence classes are queryable in this jurisdiction than "
            "the profile minimum. This is a statement about SUNLIGHT's reach, "
            "not about the claim: it forces UNVERIFIED and can never produce "
            "a finding against the claimant"
        ),
        evidence_template=coverage_cite,
        condition=lambda d: d.classes_queryable < min_queryable,
        build_evidence=lambda d: (
            f"{d.classes_queryable} of {d.classes_total} evidence classes "
            f"queryable in this jurisdiction, below the minimum of "
            f"{min_queryable}; corroboration capacity "
            f"{d.corroboration_capacity:.0%}. No adverse conclusion is "
            f"available at this capacity."
        ),
        confidence=lambda d: 0.95,
        recommendation=(
            "Report this claim as unverified and disclose the capacity "
            "ceiling. Absence of reachable evidence is not evidence of absence."
        ),
    ))

    rules.append(EvidenceRule(
        rule_id="EVD-COV-002",
        layer=EvidenceRuleLayer.COVERAGE.value,
        name="Stale evidence",
        description=(
            "Every dated artifact predates the claim's own reference date by "
            "more than the jurisdiction freshness threshold. Measured against "
            "the claim rather than against today, so the finding is "
            "reproducible"
        ),
        evidence_template=coverage_cite,
        condition=lambda d: _all_evidence_stale(d, freshness_months),
        build_evidence=lambda d: _stale_evidence_detail(d, freshness_months),
        confidence=lambda d: 0.70,
        recommendation=(
            "Re-query the sources for records covering the claimed delivery "
            "period before drawing any conclusion."
        ),
    ))

    return rules


# ═══════════════════════════════════════════════════════════
# SECTION 5: CONDITION IMPLEMENTATIONS
# Kept as named functions rather than inline lambdas wherever
# the logic needs a queryability guard or more than one step,
# so the guard is visible and independently testable.
# ═══════════════════════════════════════════════════════════


def _single_source(d: CorroborationDossier) -> bool:
    attributed = _attributed(d)
    if not attributed:
        return False
    resolver = IndependenceResolver(d.source_registry)
    groups = {resolver.find(a.source_party_id) for a in attributed}
    return len(groups) == 1


def _single_source_evidence(d: CorroborationDossier) -> str:
    attributed = _attributed(d)
    resolver = IndependenceResolver(d.source_registry)
    parties = sorted({a.source_party_id for a in attributed})
    group = resolver.find(parties[0]) if parties else "(none)"
    return (
        f"{len(attributed)} artifact(s) from {len(parties)} named part(ies) "
        f"({', '.join(parties)}) collapse to a single independence group "
        f"'{group}'"
    )


def _provider_side_only(d: CorroborationDossier) -> bool:
    """Fires only when a non-provider class was actually reachable.

    Without the queryability guard this rule would fire on every claim in
    every country that has no third-party registries, no monitor roster and
    no beneficiary-side systems — punishing the absence of infrastructure.
    """
    if not d.artifacts:
        return False
    reachable = _queryable_classes(d) & NON_PROVIDER_CLASSES
    if not reachable:
        return False
    present = {
        a.evidence_class for a in d.artifacts
        if a.status in (EvidenceStatus.OBSERVED, EvidenceStatus.CONTRADICTORY)
    }
    return not (present & NON_PROVIDER_CLASSES)


def _provider_side_only_evidence(d: CorroborationDossier) -> str:
    reachable = sorted(c.value for c in (_queryable_classes(d) & NON_PROVIDER_CLASSES))
    return (
        f"No third-party administrative, field verification or "
        f"beneficiary-side evidence present, though {len(reachable)} such "
        f"class(es) are reachable here ({', '.join(reachable)})"
    )


def _absent_count(d: CorroborationDossier, cls: EvidenceClass) -> int:
    return sum(
        1 for a in d.artifacts
        if a.evidence_class == cls and a.status == EvidenceStatus.ABSENT
    )


def _absence_evidence(d: CorroborationDossier, cls: EvidenceClass) -> str:
    absent = [
        a for a in d.artifacts
        if a.evidence_class == cls and a.status == EvidenceStatus.ABSENT
    ]
    names = ", ".join(a.description for a in absent[:3])
    sources = sorted({
        a.provenance.source_name for a in absent
        if a.provenance and a.provenance.source_name
    })
    return (
        f"{len(absent)} required {cls.value} record(s) queried and not found "
        f"({names}); source(s) queried: "
        f"{', '.join(sources) if sources else 'unrecorded'}"
    )


def _missing_field_verification(d: CorroborationDossier, window_months: int) -> bool:
    if not _class_is_queryable(d, EvidenceClass.FIELD_VERIFICATION):
        return False
    if not _expects(d, EvidenceClass.FIELD_VERIFICATION):
        return False
    ref = _reference_date(d)
    if ref is None:
        # No anchor date means the window cannot be placed. Not assessable is
        # not a finding.
        return False
    window_days = window_months * DAYS_PER_MONTH
    for a in _artifacts_in(d, EvidenceClass.FIELD_VERIFICATION):
        if a.status != EvidenceStatus.OBSERVED or a.observed_date is None:
            continue
        if abs((a.observed_date - ref).days) <= window_days:
            return False
    return True


def _missing_field_verification_evidence(d: CorroborationDossier, window_months: int) -> str:
    ref = _reference_date(d)
    visits = [
        a for a in _artifacts_in(d, EvidenceClass.FIELD_VERIFICATION)
        if a.status == EvidenceStatus.OBSERVED and a.observed_date
    ]
    if not visits:
        return (
            f"No independent monitor visit recorded within {window_months} "
            f"months of {ref}"
        )
    nearest = min(visits, key=lambda a: abs((a.observed_date - ref).days))
    off = abs((nearest.observed_date - ref).days)
    return (
        f"Nearest monitor visit {nearest.observed_date} is {off} days from "
        f"{ref}, outside the {window_months}-month window"
    )


def _timeline_offenders(d: CorroborationDossier, tolerance_days: int):
    """Artifacts dated outside the window their expectation places them in.

    Anchored on ExpectedEvidence.expected_by_month, measured from the award
    date — NOT on the claimed completion date.

    Anchoring on completion was the obvious first design and it is wrong: a
    construction permit is issued long before a building is finished, so
    every genuine facility would fire this rule. What is contradictory is not
    that evidence predates completion, but that it falls outside the window
    where that KIND of evidence belongs — a permit at month 4 is expected, an
    operational certificate at month 4 on a 22-month build is not.

    Where an expectation carries no expected_by_month there is no anchor, and
    no anchor means no finding.
    """
    award = d.claim.award_date
    if award is None:
        return []

    windows = {
        exp.evidence_class: exp.expected_by_month
        for exp in d.expected_evidence
        if exp.expected_by_month is not None
    }
    if not windows:
        return []

    out = []
    for a in d.artifacts:
        if a.status not in (EvidenceStatus.OBSERVED, EvidenceStatus.CONTRADICTORY):
            continue
        if a.observed_date is None:
            continue
        expected_month = windows.get(a.evidence_class)
        if expected_month is None:
            continue
        expected_offset_days = expected_month * DAYS_PER_MONTH
        actual_offset_days = (a.observed_date - award).days
        drift = abs(actual_offset_days - expected_offset_days)
        if drift > tolerance_days:
            out.append((a, drift, expected_month))
    return out


def _timeline_contradiction(d: CorroborationDossier, tolerance_days: int) -> bool:
    return bool(_timeline_offenders(d, tolerance_days))


def _timeline_contradiction_evidence(d: CorroborationDossier, tolerance_days: int) -> str:
    offenders = _timeline_offenders(d, tolerance_days)
    worst = max(offenders, key=lambda t: t[1])
    artifact, drift, expected_month = worst
    return (
        f"{len(offenders)} artifact(s) fall outside the window their evidence "
        f"class is expected in; furthest is '{artifact.description}' dated "
        f"{artifact.observed_date}, {drift:.0f} days from the expected "
        f"month {expected_month} after award {d.claim.award_date} "
        f"(tolerance {tolerance_days} days)"
    )


def _magnitude_offenders(d: CorroborationDossier, tolerance: float, exclude: frozenset):
    claimed = d.claim.claimed_magnitude
    if claimed is None:
        return []
    out = []
    for a in _magnitude_observations(d, exclude=exclude):
        dev = _relative_deviation(a.observed_magnitude, claimed)
        if dev is not None and dev > tolerance:
            out.append((a, dev))
    return out


def _magnitude_contradiction(d: CorroborationDossier, tolerance: float,
                             exclude: frozenset) -> bool:
    return bool(_magnitude_offenders(d, tolerance, exclude))


def _magnitude_contradiction_evidence(d: CorroborationDossier, tolerance: float,
                                      exclude: frozenset) -> str:
    offenders = _magnitude_offenders(d, tolerance, exclude)
    worst = max(offenders, key=lambda t: t[1])
    unit = d.claim.claimed_magnitude_unit or "units"
    return (
        f"Claimed {d.claim.claimed_magnitude:,.0f} {unit}; observed "
        f"{worst[0].observed_magnitude:,.0f} {unit} per "
        f"'{worst[0].description}' ({worst[1]:.0%} deviation, tolerance "
        f"{tolerance:.0%})"
    )


def _magnitude_confidence(d: CorroborationDossier, tolerance: float,
                          exclude: frozenset) -> float:
    offenders = _magnitude_offenders(d, tolerance, exclude)
    if not offenders:
        return 0.0
    worst = max(dev for _, dev in offenders)
    # Confidence rises with the size of the discrepancy: a 25% shortfall on a
    # 20% tolerance is arguably a measurement-basis difference; a 75%
    # shortfall is not.
    return min(0.92, 0.60 + 0.4 * min(1.0, worst))


def _geospatial_contradiction(d: CorroborationDossier) -> bool:
    geo = _artifacts_in(d, EvidenceClass.GEOSPATIAL)
    if any(a.status == EvidenceStatus.CONTRADICTORY for a in geo):
        return True
    award = d.claim.award_date
    if award is None:
        return False
    # A structure already visible in pre-award imagery was not produced by
    # this contract.
    return any(
        a.status == EvidenceStatus.OBSERVED
        and a.observed_date is not None
        and a.observed_date < award
        for a in geo
    )


def _geospatial_contradiction_evidence(d: CorroborationDossier) -> str:
    geo = _artifacts_in(d, EvidenceClass.GEOSPATIAL)
    direct = [a for a in geo if a.status == EvidenceStatus.CONTRADICTORY]
    if direct:
        return (
            f"{len(direct)} geospatial artifact(s) inconsistent with the "
            f"claim: {'; '.join(a.description for a in direct[:3])}"
        )
    award = d.claim.award_date
    predating = [
        a for a in geo
        if a.status == EvidenceStatus.OBSERVED
        and a.observed_date is not None
        and a.observed_date < award
    ]
    earliest = min(predating, key=lambda a: a.observed_date)
    return (
        f"Structure visible in imagery dated {earliest.observed_date}, "
        f"before the contract award date {award} — the observed footprint "
        f"predates the contract claimed to have produced it"
    )


def _beneficiary_contradiction(d: CorroborationDossier, tolerance: float) -> bool:
    claimed = d.claim.claimed_magnitude
    if claimed is None:
        return False
    for a in _artifacts_in(d, EvidenceClass.BENEFICIARY_SIDE):
        if a.observed_magnitude is None:
            continue
        if a.status not in (EvidenceStatus.OBSERVED, EvidenceStatus.CONTRADICTORY):
            continue
        dev = _relative_deviation(a.observed_magnitude, claimed)
        if dev is not None and dev > tolerance:
            return True
    return False


def _beneficiary_contradiction_evidence(d: CorroborationDossier, tolerance: float) -> str:
    claimed = d.claim.claimed_magnitude
    rows = [
        (a, _relative_deviation(a.observed_magnitude, claimed))
        for a in _artifacts_in(d, EvidenceClass.BENEFICIARY_SIDE)
        if a.observed_magnitude is not None
        and a.status in (EvidenceStatus.OBSERVED, EvidenceStatus.CONTRADICTORY)
    ]
    rows = [(a, dev) for a, dev in rows if dev is not None and dev > tolerance]
    worst = max(rows, key=lambda t: t[1])
    unit = d.claim.claimed_magnitude_unit or "beneficiaries"
    return (
        f"Claimed {claimed:,.0f} {unit}; recipient-side records show "
        f"{worst[0].observed_magnitude:,.0f} per '{worst[0].description}' "
        f"({worst[1]:.0%} divergence, tolerance {tolerance:.0%})"
    )


def _independence_violation(d: CorroborationDossier) -> bool:
    """Two or more DIFFERENT named parties that resolve to the same group.

    Presenting one source under two names is the violation. A single party
    submitting two documents is EVD-CORR-002's business, not this rule's.
    """
    attributed = _attributed(d)
    if len(attributed) < 2:
        return False
    resolver = IndependenceResolver(d.source_registry)
    by_group = {}
    for a in attributed:
        by_group.setdefault(resolver.find(a.source_party_id), set()).add(a.source_party_id)
    return any(len(parties) > 1 for parties in by_group.values())


def _independence_violation_evidence(d: CorroborationDossier) -> str:
    resolver = IndependenceResolver(d.source_registry)
    by_group = {}
    for a in _attributed(d):
        by_group.setdefault(resolver.find(a.source_party_id), set()).add(a.source_party_id)
    collapsed = {g: sorted(p) for g, p in by_group.items() if len(p) > 1}
    parts = [
        f"{' + '.join(parties)} resolve to one source"
        for parties in collapsed.values()
    ]
    return (
        f"{len(collapsed)} group(s) of separately-named parties are "
        f"structurally linked: {'; '.join(parts)}"
    )


def _custody_break_artifacts(d: CorroborationDossier) -> List[EvidenceArtifact]:
    """Artifacts that cannot be vouched for, admitted or quarantined.

    Scans rejected_artifacts as well as artifacts. Stage 13 quarantines
    unsourced evidence so it cannot corroborate anything — but if this rule
    only looked at the admitted set, quarantining would make the finding
    disappear, silently converting a chain-of-custody problem into an absence
    of evidence. The artifact is refused AND reported.
    """
    out = []
    for a in list(d.artifacts) + list(d.rejected_artifacts):
        if a.integrity_verified is False:
            out.append(a)
        elif not is_ingestible(a):
            out.append(a)
    return out


def _custody_break(d: CorroborationDossier) -> bool:
    return bool(_custody_break_artifacts(d))


def _custody_break_evidence(d: CorroborationDossier) -> str:
    broken = _custody_break_artifacts(d)
    tampered = [a for a in broken if a.integrity_verified is False]
    unsourced = [a for a in broken if a.integrity_verified is not False]
    bits = []
    if tampered:
        bits.append(
            f"{len(tampered)} artifact(s) failed hash re-verification "
            f"({', '.join(a.artifact_id for a in tampered[:3])})"
        )
    if unsourced:
        bits.append(
            f"{len(unsourced)} artifact(s) lack valid provenance "
            f"({', '.join(a.artifact_id for a in unsourced[:3])})"
        )
    return "; ".join(bits)


def _captured_monitors(d: CorroborationDossier) -> List[EvidenceArtifact]:
    out = []
    for a in _artifacts_in(d, EvidenceClass.FIELD_VERIFICATION):
        if not a.source_party_id:
            continue
        src = d.source(a.source_party_id)
        if src is None:
            continue
        if src.randomly_assigned is False:
            out.append(a)
            continue
        if src.selected_by:
            chooser = d.source(src.selected_by)
            if chooser is not None and chooser.is_contract_party:
                out.append(a)
    return out


def _captured_monitor(d: CorroborationDossier) -> bool:
    return bool(_captured_monitors(d))


def _captured_monitor_evidence(d: CorroborationDossier) -> str:
    captured = _captured_monitors(d)
    details = []
    for a in captured[:3]:
        src = d.source(a.source_party_id)
        if src and src.selected_by:
            details.append(f"{src.party_name} selected by {src.selected_by}")
        elif src:
            details.append(f"{src.party_name} not randomly assigned")
    return (
        f"{len(captured)} field verification artifact(s) rest on a monitor "
        f"that was not independently assigned: {'; '.join(details)}"
    )


def _all_evidence_stale(d: CorroborationDossier, freshness_months: int) -> bool:
    """Every dated artifact predates the claim's reference date by too much.

    Anchored on the claim, never on today. A staleness rule that reads the
    wall clock returns a different answer next month, which would make the
    finding irreproducible and therefore unauditable.
    """
    ref = _reference_date(d)
    if ref is None:
        return False
    dated = [a for a in d.artifacts if a.observed_date is not None]
    if not dated:
        return False
    threshold_days = freshness_months * DAYS_PER_MONTH
    return all((ref - a.observed_date).days > threshold_days for a in dated)


def _stale_evidence_detail(d: CorroborationDossier, freshness_months: int) -> str:
    ref = _reference_date(d)
    dated = [a for a in d.artifacts if a.observed_date is not None]
    newest = max(dated, key=lambda a: a.observed_date)
    age_days = (ref - newest.observed_date).days
    return (
        f"All {len(dated)} dated artifact(s) predate the reference date "
        f"{ref} by more than {freshness_months} months; the most recent "
        f"('{newest.description}', {newest.observed_date}) is "
        f"{age_days / DAYS_PER_MONTH:.1f} months older"
    )


# ═══════════════════════════════════════════════════════════
# SECTION 6: LAYER 5 ISOLATION GUARD
# ═══════════════════════════════════════════════════════════


COVERAGE_RULE_IDS = frozenset({"EVD-COV-001", "EVD-COV-002"})


def assert_layer_five_is_isolated(rules: List[EvidenceRule]) -> None:
    """Fail loudly if a coverage rule is ever wired to a contradiction-capable layer.

    Called from the test suite. This is the code-level twin of the structural
    guarantee in evidence_evg.py: coverage rules describe how far SUNLIGHT
    could see, and must have no path to a finding against a claimant.

    Raises:
        AssertionError: with the offending rule id.
    """
    for rule in rules:
        if rule.rule_id in COVERAGE_RULE_IDS:
            if rule.layer in CONTRADICTION_CAPABLE_LAYERS:
                raise AssertionError(
                    f"{rule.rule_id} is a coverage rule but sits on layer "
                    f"'{rule.layer}', which can contribute to CONTRADICTED. "
                    f"Coverage rules must stay on "
                    f"'{EvidenceRuleLayer.COVERAGE.value}' — otherwise thin "
                    f"national infrastructure becomes a finding against the "
                    f"country."
                )
        elif rule.layer == EvidenceRuleLayer.COVERAGE.value:
            raise AssertionError(
                f"{rule.rule_id} sits on the coverage layer but is not a "
                f"declared coverage rule. It would be silently excluded from "
                f"every verdict."
            )


# ═══════════════════════════════════════════════════════════
# SECTION 7: THE ENGINE
# ═══════════════════════════════════════════════════════════


class EvidenceRuleEngine:
    """Deterministic corroboration rule evaluation.

    Mirrors DeliveryRuleEngine: evaluate every rule, record what fired, and
    contain exceptions so one malformed rule cannot take down the analysis.
    A rule that throws is recorded as not-fired — the conservative direction,
    since a rule firing is what produces a finding.
    """

    def __init__(self, profile=None):
        if profile is None:
            from jurisdiction_profile import US_FEDERAL
            profile = US_FEDERAL
        self.profile = profile
        self.rules = build_evidence_rules(self.profile)

    def evaluate(self, dossier: CorroborationDossier) -> EvidenceRulesResult:
        """Evaluate all 16 rules against a dossier."""
        rule_results: List[EvidenceRuleResult] = []
        layer_summary: dict = {}

        for rule in self.rules:
            try:
                fired = rule.condition(dossier)
            except Exception:
                fired = False

            if fired:
                try:
                    evidence = rule.build_evidence(dossier)
                except Exception:
                    evidence = f"{rule.name} — evidence generation failed"
                try:
                    conf = rule.confidence(dossier)
                except Exception:
                    conf = 0.5

                rule_results.append(EvidenceRuleResult(
                    rule_id=rule.rule_id,
                    layer=rule.layer,
                    fired=True,
                    evidence=evidence,
                    legal_basis=rule.evidence_template,
                    confidence=conf,
                    detail=rule.description,
                    recommendation=rule.recommendation,
                ))
                layer_summary[rule.layer] = layer_summary.get(rule.layer, 0) + 1
            else:
                rule_results.append(EvidenceRuleResult(
                    rule_id=rule.rule_id,
                    layer=rule.layer,
                    fired=False,
                    detail=rule.description,
                    recommendation=rule.recommendation,
                ))

        return EvidenceRulesResult(
            rules_evaluated=len(self.rules),
            rules_fired=sum(1 for r in rule_results if r.fired),
            rule_results=rule_results,
            layer_summary=layer_summary,
        )
