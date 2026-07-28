"""
SUNLIGHT Side 5 — Evidence Verification Gate (Evidence EVG)
==============================================================

Multi-dimensional hard-evidence gate for outcome corroboration.
Combines rule evaluation results against profile thresholds to produce one
of FOUR verdicts.

Architecture:
    Mirrors delivery_evg.py:
    - DIMENSION_LAYER_MAP, count fired rules per layer, compare to threshold
    - Per-dimension traceability with observed value, threshold and detail
    - Deterministic: same inputs = same verdict. Forever.

    Two deliberate differences from delivery, both stated here because both
    change what the gate can conclude:

    1. FOUR verdicts, not three. VERIFIED / PARTIAL / UNVERIFIED /
       CONTRADICTED. The fourth exists so that "we could not establish this"
       is never recorded as "this is false".

    2. Convergence is required ACROSS dimensions, not within a layer.
       Delivery fires a dimension at 2 rules in one layer, on the reasoning
       that a single rule is not convergent evidence. Here a dimension fires
       at 1 rule, and convergence is enforced at the verdict instead:
       CONTRADICTED needs two or more DIMENSIONS.

       That is a stronger requirement, not a weaker one. Side 5's layers are
       different KINDS of problem — insufficient independent support, a
       documented absence, an active contradiction, a broken evidence chain.
       Requiring two different kinds is more meaningful convergence than
       requiring two rules of the same kind, and it is what lets a single
       decisive finding (imagery showing the structure predates the award)
       register as PARTIAL rather than being silently discarded.

       min_rules_per_dimension remains a profile parameter, so a jurisdiction
       can tighten it without a code change.

THE ORDER OF THE GUARDS IS THE ARCHITECTURE:
    Capacity is checked FIRST, before any finding is consulted. Below the
    profile floor, the verdict is UNVERIFIED no matter how many rules fired.
    This is what makes it structurally impossible for thin national
    infrastructure to produce a finding against a country — the code cannot
    reach a CONTRADICTED branch from a low-capacity dossier, regardless of
    what the evidence rules concluded.

    Layer 5 findings are passed in separately from dimensions and can only
    force UNVERIFIED. They have no path to CONTRADICTED, by construction
    rather than by convention.

Verdicts:
    VERIFIED     — enough independent corroboration, nothing fired
    PARTIAL      — some corroboration, gaps, or a single kind of finding
    UNVERIFIED   — insufficient reachable evidence to conclude anything
    CONTRADICTED — independent evidence actively conflicts with the claim

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from evidence_schema import (
    CONTRADICTION_CAPABLE_LAYERS,
    CorroborationVerdict,
    EvidenceDimension,
    EvidenceDimensionResult,
    EvidenceGateOutcome,
    EvidenceRuleLayer,
    EvidenceRulesResult,
)


# ═══════════════════════════════════════════════════════════
# THRESHOLD DEFAULTS
# ═══════════════════════════════════════════════════════════

# Rules that must fire within a layer for its dimension to fire. One, because
# convergence is enforced across dimensions at the verdict — see the module
# docstring. Profile-overridable.
DEFAULT_MIN_RULES_PER_DIMENSION = 1

# Corroboration capacity below which no adverse conclusion is available,
# whatever the rules found.
DEFAULT_MIN_CORROBORATION_CAPACITY = 0.5

# Independent corroborating sources required for VERIFIED.
DEFAULT_MIN_INDEPENDENT_CLASSES = 3

# Dimensions required for CONTRADICTED. Two different kinds of problem.
DEFAULT_MIN_DIMENSIONS_FOR_CONTRADICTION = 2

# Dimensions required when the finding is absence-driven rather than an
# active contradiction. Higher, because absence is weaker evidence than
# conflict: three independent kinds of problem, not two.
DEFAULT_MIN_DIMENSIONS_FOR_ABSENCE_CONTRADICTION = 3


# ═══════════════════════════════════════════════════════════
# DIMENSION → LAYER MAPPING
# ═══════════════════════════════════════════════════════════

# Four entries. COVERAGE is absent, and its absence is load-bearing: a layer
# with no dimension has no path to a verdict, which is the whole mechanism
# protecting weak-infrastructure jurisdictions. assert_coverage_has_no_dimension()
# below fails loudly if anyone adds a fifth entry.
DIMENSION_LAYER_MAP: Dict[EvidenceDimension, str] = {
    EvidenceDimension.CORROBORATION_SUFFICIENCY: EvidenceRuleLayer.CORROBORATION.value,
    EvidenceDimension.EXPECTED_ABSENCE: EvidenceRuleLayer.ABSENCE.value,
    EvidenceDimension.CONTRADICTION: EvidenceRuleLayer.CONTRADICTION.value,
    EvidenceDimension.SOURCE_INTEGRITY: EvidenceRuleLayer.SOURCE.value,
}

# The Layer 5 rule that forces UNVERIFIED on its own.
CAPACITY_RULE_ID = "EVD-COV-001"

# Layers whose fired rules are reported as contradictions of the claim.
# Corroboration-sufficiency and source-integrity findings describe the
# quality of the evidence base rather than a conflict with the claim, so
# they are reported through rules_result instead of being labelled
# contradictions they are not.
CONTRADICTION_REPORTING_LAYERS = frozenset({
    EvidenceRuleLayer.ABSENCE.value,
    EvidenceRuleLayer.CONTRADICTION.value,
})


def assert_coverage_has_no_dimension() -> None:
    """Fail loudly if the coverage layer is ever given an EVG dimension.

    Called from the test suite. If a coverage rule could fire a dimension,
    a jurisdiction with few reachable evidence classes would accumulate
    dimensions and could reach CONTRADICTED — which would mean SUNLIGHT
    finding against countries for the state of their registries.

    Raises:
        AssertionError: naming the offending dimension.
    """
    coverage = EvidenceRuleLayer.COVERAGE.value
    for dimension, layer in DIMENSION_LAYER_MAP.items():
        if layer == coverage:
            raise AssertionError(
                f"{dimension.name} maps to the coverage layer. Coverage "
                f"measures SUNLIGHT's reach, not the claim's truth; giving "
                f"it a dimension gives thin national infrastructure a path "
                f"to a finding against the country."
            )
    if len(DIMENSION_LAYER_MAP) != 4:
        raise AssertionError(
            f"Expected 4 EVG dimensions, found {len(DIMENSION_LAYER_MAP)}. "
            f"A fifth dimension most likely means the coverage layer was wired in."
        )
    mapped = set(DIMENSION_LAYER_MAP.values())
    if mapped != set(CONTRADICTION_CAPABLE_LAYERS):
        raise AssertionError(
            f"EVG dimensions map to {sorted(mapped)} but the schema declares "
            f"{sorted(CONTRADICTION_CAPABLE_LAYERS)} as contradiction-capable. "
            f"These two must agree or the guard is decorative."
        )


def _param(profile, name: str, default):
    """Read a threshold from the profile, defaulting conservatively.

    Same getattr precedent as delivery_rules._get_delivery_param.
    """
    return getattr(profile, name, default) if profile is not None else default


# ═══════════════════════════════════════════════════════════
# VERDICT ASSIGNMENT
# ═══════════════════════════════════════════════════════════


def assign_verdict(
    dimensions_fired: Set[EvidenceDimension],
    coverage_rules_fired: Set[str],
    corroboration_capacity: float,
    independent_classes: int,
    profile=None,
) -> CorroborationVerdict:
    """Assign one of the four corroboration verdicts.

    ORDER MATTERS AND IS THE POINT. The capacity guards run before any
    finding is consulted, so a low-capacity dossier cannot reach an adverse
    verdict no matter what fired. Everything else is downstream of that.

    Args:
        dimensions_fired: EVG dimensions that fired. Contains only the four
            scoring dimensions — coverage has none, by construction.
        coverage_rules_fired: rule ids from Layer 5. These can force
            UNVERIFIED and can do nothing else.
        corroboration_capacity: fraction of evidence classes reachable here.
        independent_classes: independent corroborating sources after collapse.
        profile: jurisdiction profile supplying thresholds.

    Returns:
        CorroborationVerdict.
    """
    min_capacity = _param(profile, "min_corroboration_capacity",
                          DEFAULT_MIN_CORROBORATION_CAPACITY)
    min_independent = _param(profile, "min_independent_classes",
                             DEFAULT_MIN_INDEPENDENT_CLASSES)
    min_dims_contradiction = _param(profile, "min_dimensions_for_contradiction",
                                    DEFAULT_MIN_DIMENSIONS_FOR_CONTRADICTION)
    min_dims_absence = _param(profile, "min_dimensions_for_absence_contradiction",
                              DEFAULT_MIN_DIMENSIONS_FOR_ABSENCE_CONTRADICTION)

    # ── GUARD 1: insufficient reach ──
    # Below the capacity floor we cannot conclude anything, and saying so is
    # the honest answer. A country with two reachable evidence classes cannot
    # produce the corroboration that would confirm a TRUE claim, so treating
    # its silence as evidence against the claim would be a finding generated
    # by the state of its registries.
    if corroboration_capacity < min_capacity:
        return CorroborationVerdict.UNVERIFIED

    # ── GUARD 2: capacity rule fired ──
    if CAPACITY_RULE_ID in coverage_rules_fired:
        return CorroborationVerdict.UNVERIFIED

    # ── Active contradiction, convergent across kinds of problem ──
    if (EvidenceDimension.CONTRADICTION in dimensions_fired
            and len(dimensions_fired) >= min_dims_contradiction):
        return CorroborationVerdict.CONTRADICTED

    # ── Absence-driven contradiction, held to a higher bar ──
    # Absence is weaker evidence than conflict, so it takes three independent
    # kinds of problem rather than two.
    if (EvidenceDimension.EXPECTED_ABSENCE in dimensions_fired
            and len(dimensions_fired) >= min_dims_absence):
        return CorroborationVerdict.CONTRADICTED

    # ── A single kind of finding is a gap, not a contradiction ──
    if len(dimensions_fired) >= 1:
        return CorroborationVerdict.PARTIAL

    # ── Nothing fired ──
    if independent_classes >= min_independent:
        return CorroborationVerdict.VERIFIED

    # Nothing fired, but corroboration is still thin. Unreachable through the
    # shipped rule set — EVD-CORR-001 fires on exactly this condition and
    # would have populated dimensions_fired — but retained so that a caller
    # invoking assign_verdict directly cannot fall off the end into VERIFIED.
    return CorroborationVerdict.PARTIAL


# ═══════════════════════════════════════════════════════════
# CONFIDENCE
# ═══════════════════════════════════════════════════════════


def _capacity_factor(capacity: float) -> float:
    """How much the reach of the evidence base is allowed to support a verdict.

    Ranges 0.5 at zero capacity to 1.0 at full. This is what makes "findings
    at low capacity carry wider confidence bounds" an actual property of the
    output rather than a sentence in a report.
    """
    return 0.5 + 0.5 * max(0.0, min(1.0, capacity))


def compute_confidence(
    verdict: CorroborationVerdict,
    fired_confidences: List[float],
    corroboration_capacity: float,
    independent_classes: int,
    profile=None,
) -> float:
    """Confidence in the verdict as stated — not in the claim.

    For adverse verdicts this combines the fired rules' own confidences with
    a noisy-OR, which rewards convergence from independent findings, then
    scales by reach. Two findings at 0.8 are worth more than one at 0.8,
    because they had to be wrong together.

    For UNVERIFIED the number means something different and is computed
    differently: confidence that no conclusion is available. That RISES as
    capacity falls, because the less we could see, the more certain we are
    that we cannot conclude.
    """
    min_independent = _param(profile, "min_independent_classes",
                             DEFAULT_MIN_INDEPENDENT_CLASSES)
    factor = _capacity_factor(corroboration_capacity)

    if verdict == CorroborationVerdict.UNVERIFIED:
        # Certainty about our own blindness, not about the claim.
        return round(min(0.95, 0.60 + 0.35 * (1.0 - max(0.0, min(1.0, corroboration_capacity)))), 4)

    if verdict == CorroborationVerdict.VERIFIED:
        strength = min(0.95, 0.50 + 0.12 * max(0, independent_classes))
        if independent_classes < min_independent:
            strength *= 0.8
        return round(strength * factor, 4)

    if not fired_confidences:
        return round(0.50 * factor, 4)

    # Noisy-OR over independent findings.
    product = 1.0
    for c in fired_confidences:
        product *= (1.0 - max(0.0, min(1.0, c)))
    combined = 1.0 - product

    return round(combined * factor, 4)


# ═══════════════════════════════════════════════════════════
# THE GATE
# ═══════════════════════════════════════════════════════════


def evidence_gate(
    rules_result: Optional[EvidenceRulesResult],
    corroboration_capacity: float = 0.0,
    independent_classes: int = 0,
    classes_queryable: int = 0,
    profile=None,
    min_rules_per_dimension: Optional[int] = None,
) -> EvidenceGateOutcome:
    """Evaluate the Evidence Verification Gate.

    Args:
        rules_result: aggregate from EvidenceRuleEngine.evaluate(). May be
            None when rule evaluation was not reached — in which case no
            dimension fires and the capacity guards still apply, so an
            unanalysed dossier reads as UNVERIFIED rather than as clean.
        corroboration_capacity: fraction of evidence classes reachable.
        independent_classes: independent corroborating sources after collapse.
        classes_queryable: reachable class count, for reporting.
        profile: jurisdiction profile supplying thresholds.
        min_rules_per_dimension: override for the per-layer firing threshold.

    Returns:
        EvidenceGateOutcome with verdict, per-dimension traceability, the
        contradictions found, and the capacity figures the verdict must be
        read alongside.
    """
    if min_rules_per_dimension is None:
        min_rules_per_dimension = _param(
            profile, "min_rules_per_dimension", DEFAULT_MIN_RULES_PER_DIMENSION)

    dimension_results: List[EvidenceDimensionResult] = []
    fired_dimensions: Set[EvidenceDimension] = set()

    for dimension, layer in DIMENSION_LAYER_MAP.items():
        fired = False
        observed: Optional[float] = None
        threshold = float(min_rules_per_dimension)
        detail = "No evidence rule data available"

        if rules_result is not None:
            layer_fired = sum(
                1 for rr in rules_result.rule_results
                if rr.layer == layer and rr.fired
            )
            observed = float(layer_fired)

            if layer_fired >= min_rules_per_dimension:
                fired = True
                fired_dimensions.add(dimension)
                detail = (
                    f"{layer_fired} rule(s) fired in {layer} layer >= "
                    f"threshold {min_rules_per_dimension}"
                )
            else:
                detail = (
                    f"{layer_fired} rule(s) fired in {layer} layer < "
                    f"threshold {min_rules_per_dimension}"
                )

        dimension_results.append(EvidenceDimensionResult(
            dimension=dimension,
            fired=fired,
            observed_value=observed,
            threshold=threshold,
            detail=detail,
        ))

    # ── Layer 5 findings, kept strictly separate from the dimensions ──
    coverage_layer = EvidenceRuleLayer.COVERAGE.value
    coverage_fired: Set[str] = set()
    contradictions: List[Dict] = []
    fired_confidences: List[float] = []

    if rules_result is not None:
        for rr in rules_result.rule_results:
            if not rr.fired:
                continue
            if rr.layer == coverage_layer:
                coverage_fired.add(rr.rule_id)
                continue
            fired_confidences.append(rr.confidence)
            if rr.layer in CONTRADICTION_REPORTING_LAYERS:
                contradictions.append({
                    "rule_id": rr.rule_id,
                    "layer": rr.layer,
                    "finding": rr.detail,
                    "evidence": rr.evidence,
                    "legal_basis": rr.legal_basis,
                    "confidence": rr.confidence,
                    "recommendation": rr.recommendation,
                })

    verdict = assign_verdict(
        dimensions_fired=fired_dimensions,
        coverage_rules_fired=coverage_fired,
        corroboration_capacity=corroboration_capacity,
        independent_classes=independent_classes,
        profile=profile,
    )

    confidence = compute_confidence(
        verdict=verdict,
        fired_confidences=fired_confidences,
        corroboration_capacity=corroboration_capacity,
        independent_classes=independent_classes,
        profile=profile,
    )

    return EvidenceGateOutcome(
        verdict=verdict,
        dimensions_fired=len(fired_dimensions),
        dimension_results=dimension_results,
        coverage_findings=sorted(coverage_fired),
        contradictions=contradictions,
        confidence=confidence,
        corroboration_capacity=corroboration_capacity,
        classes_queryable=classes_queryable,
        independent_classes_corroborating=independent_classes,
        methodology_note=(
            f"Evidence EVG v1.0: four verdicts. CONTRADICTED requires an "
            f"active contradiction plus at least "
            f"{_param(profile, 'min_dimensions_for_contradiction', DEFAULT_MIN_DIMENSIONS_FOR_CONTRADICTION)} "
            f"dimensions, or absence across at least "
            f"{_param(profile, 'min_dimensions_for_absence_contradiction', DEFAULT_MIN_DIMENSIONS_FOR_ABSENCE_CONTRADICTION)}. "
            f"Corroboration capacity {corroboration_capacity:.0%} "
            f"({classes_queryable} of 6 evidence classes reachable in this "
            f"jurisdiction); below "
            f"{_param(profile, 'min_corroboration_capacity', DEFAULT_MIN_CORROBORATION_CAPACITY):.0%} "
            f"no adverse conclusion is available and the verdict is UNVERIFIED. "
            f"Coverage findings never contribute to CONTRADICTED."
        ),
    )
