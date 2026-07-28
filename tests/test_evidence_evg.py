"""
Tests for SUNLIGHT Side 5 — Evidence Verification Gate.

Covers spec tests 28-35, the verdict-assignment guards.

Test 30 is the one that matters most in the whole side:

    LOW capacity + absence must produce UNVERIFIED, never CONTRADICTED.

A country with no digital land registry, no utility connection database and
no health information system cannot produce the evidence that would
corroborate a TRUE claim. If thin infrastructure could push a verdict toward
CONTRADICTED, SUNLIGHT would systematically find against the poorest
countries for being poor. That failure mode is unacceptable, and the tests
below are what stop it returning quietly.

The guard is enforced by ORDER: capacity is checked before any finding is
consulted, so the code cannot reach a CONTRADICTED branch from a low-capacity
dossier whatever the rules concluded. TestPoorCountryGuard exhausts that
claim rather than sampling it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_evg import (
    CAPACITY_RULE_ID,
    DIMENSION_LAYER_MAP,
    assert_coverage_has_no_dimension,
    assign_verdict,
    compute_confidence,
    evidence_gate,
)
from evidence_schema import (
    CONTRADICTION_CAPABLE_LAYERS,
    CorroborationVerdict,
    EvidenceDimension,
    EvidenceRuleLayer,
    EvidenceRuleResult,
    EvidenceRulesResult,
)


ALL_DIMENSIONS = list(EvidenceDimension)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def rules(*specs):
    """Build an EvidenceRulesResult from (rule_id, layer, fired[, confidence])."""
    results = []
    for spec in specs:
        rule_id, layer, fired = spec[0], spec[1], spec[2]
        confidence = spec[3] if len(spec) > 3 else 0.8
        results.append(EvidenceRuleResult(
            rule_id=rule_id,
            layer=layer.value if hasattr(layer, "value") else layer,
            fired=fired,
            evidence=f"evidence for {rule_id}",
            confidence=confidence if fired else 0.0,
            detail=f"detail for {rule_id}",
        ))
    return EvidenceRulesResult(
        rules_evaluated=len(results),
        rules_fired=sum(1 for r in results if r.fired),
        rule_results=results,
        layer_summary={},
    )


CORR = EvidenceRuleLayer.CORROBORATION
ABS = EvidenceRuleLayer.ABSENCE
CON = EvidenceRuleLayer.CONTRADICTION
SRC = EvidenceRuleLayer.SOURCE
COV = EvidenceRuleLayer.COVERAGE


# ═══════════════════════════════════════════════════════════
# SECTION 1: THE POOR-COUNTRY GUARD  (spec tests 30, 31, 32, 35)
# ═══════════════════════════════════════════════════════════


class TestPoorCountryGuard:
    """THE GUARD THAT THE WHOLE SIDE RESTS ON."""

    def test_low_capacity_plus_absence_is_unverified_never_contradicted(self):
        """SPEC TEST 30.

        Absence findings across three dimensions — which at full capacity
        would be CONTRADICTED — must produce UNVERIFIED when the evidence
        space was barely reachable.
        """
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.EXPECTED_ABSENCE,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
                EvidenceDimension.SOURCE_INTEGRITY,
            },
            coverage_rules_fired={CAPACITY_RULE_ID},
            corroboration_capacity=0.17,     # 1 of 6 classes reachable
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.UNVERIFIED
        assert verdict != CorroborationVerdict.CONTRADICTED

    def test_capacity_below_floor_overrides_everything(self):
        """SPEC TEST 31 — including an active contradiction across all four
        dimensions. Reach is checked before findings, always."""
        verdict = assign_verdict(
            dimensions_fired=set(ALL_DIMENSIONS),
            coverage_rules_fired=set(),
            corroboration_capacity=0.33,
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.UNVERIFIED

    def test_capacity_rule_fired_overrides_everything(self):
        """SPEC TEST 32 — EVD-COV-001 forces UNVERIFIED even at full capacity."""
        verdict = assign_verdict(
            dimensions_fired=set(ALL_DIMENSIONS),
            coverage_rules_fired={CAPACITY_RULE_ID},
            corroboration_capacity=1.0,
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.UNVERIFIED

    def test_coverage_rules_alone_never_produce_contradicted(self):
        """SPEC TEST 35 — Layer 5 has no path to an adverse verdict."""
        verdict = assign_verdict(
            dimensions_fired=set(),
            coverage_rules_fired={"EVD-COV-001", "EVD-COV-002"},
            corroboration_capacity=1.0,
            independent_classes=5,
        )
        assert verdict != CorroborationVerdict.CONTRADICTED

    def test_stale_evidence_alone_does_not_condemn(self):
        """EVD-COV-002 without EVD-COV-001 does not force UNVERIFIED, and
        still cannot reach CONTRADICTED."""
        verdict = assign_verdict(
            dimensions_fired=set(),
            coverage_rules_fired={"EVD-COV-002"},
            corroboration_capacity=1.0,
            independent_classes=4,
        )
        assert verdict == CorroborationVerdict.VERIFIED

    @pytest.mark.parametrize("capacity", [0.0, 0.1, 0.17, 0.33, 0.49])
    def test_no_capacity_below_floor_can_reach_contradicted(self, capacity):
        """Exhaustive over every dimension combination at each low capacity.

        Not a sample — every one of the 16 subsets of the four dimensions,
        with and without the capacity rule. If ANY combination reaches
        CONTRADICTED below the floor, the guard has a hole.
        """
        from itertools import combinations

        for size in range(len(ALL_DIMENSIONS) + 1):
            for combo in combinations(ALL_DIMENSIONS, size):
                for coverage in (set(), {CAPACITY_RULE_ID}, {"EVD-COV-002"}):
                    verdict = assign_verdict(
                        dimensions_fired=set(combo),
                        coverage_rules_fired=coverage,
                        corroboration_capacity=capacity,
                        independent_classes=0,
                    )
                    assert verdict == CorroborationVerdict.UNVERIFIED, (
                        f"capacity={capacity} dims={[d.name for d in combo]} "
                        f"coverage={coverage} produced {verdict}"
                    )

    def test_thin_infrastructure_country_with_consistent_evidence(self):
        """SPEC TEST 38 (verdict half).

        Only two classes reachable, both consistent, nothing fired. The
        honest answer is that we could not establish this — not that it is
        false, and not that it is confirmed.
        """
        outcome = evidence_gate(
            rules_result=rules(("EVD-COV-001", COV, True)),
            corroboration_capacity=2 / 6,
            independent_classes=2,
            classes_queryable=2,
        )
        assert outcome.verdict == CorroborationVerdict.UNVERIFIED
        assert outcome.verdict != CorroborationVerdict.CONTRADICTED


# ═══════════════════════════════════════════════════════════
# SECTION 2: ADVERSE VERDICTS  (spec tests 28, 29)
# ═══════════════════════════════════════════════════════════


class TestContradictedVerdict:

    def test_contradiction_across_two_dimensions(self):
        """SPEC TEST 28."""
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.CONTRADICTION,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
            },
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=1,
        )
        assert verdict == CorroborationVerdict.CONTRADICTED

    def test_absence_across_three_dimensions(self):
        """SPEC TEST 29."""
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.EXPECTED_ABSENCE,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
                EvidenceDimension.SOURCE_INTEGRITY,
            },
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.CONTRADICTED

    def test_absence_across_only_two_dimensions_is_partial(self):
        """Absence is weaker evidence than conflict, so it is held to a
        higher bar: three kinds of problem, not two."""
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.EXPECTED_ABSENCE,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
            },
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=1,
        )
        assert verdict == CorroborationVerdict.PARTIAL

    def test_many_absences_in_one_layer_still_count_as_one_dimension(self):
        """A deliberate, and consequential, property of the dimension model.

        Five registries each returning "no record" is five findings but ONE
        kind of problem, so it reaches two dimensions with the corroboration
        layer and lands on PARTIAL, not CONTRADICTED.

        That is the conservative reading and it is the right one: a
        no-record result is the weakest evidence Side 5 handles, and a pile
        of weak evidence of the same kind should not convert into an adverse
        finding. What separates PARTIAL from CONTRADICTED here is whether
        any source ANSWERED and conflicted — see the pair below.
        """
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.EXPECTED_ABSENCE,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
            },
            coverage_rules_fired=set(),
            corroboration_capacity=5 / 6,
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.PARTIAL

    def test_one_answering_source_that_conflicts_reaches_contradicted(self):
        """The pair to the test above, and the distinction Side 5 turns on.

        A registry with no record is an absence. Satellite imagery that was
        obtained and shows no structure is an ANSWER, and it conflicts. The
        second is stronger evidence than the first no matter how many
        registries were silent, and only the second opens the CONTRADICTED
        path — with the same absences alongside it.
        """
        verdict = assign_verdict(
            dimensions_fired={
                EvidenceDimension.EXPECTED_ABSENCE,
                EvidenceDimension.CORROBORATION_SUFFICIENCY,
                EvidenceDimension.CONTRADICTION,
            },
            coverage_rules_fired=set(),
            corroboration_capacity=5 / 6,
            independent_classes=0,
        )
        assert verdict == CorroborationVerdict.CONTRADICTED

    def test_contradiction_alone_is_partial_not_contradicted(self):
        """One kind of problem is a gap. CONTRADICTED needs convergence
        across different kinds — that is what makes it defensible."""
        verdict = assign_verdict(
            dimensions_fired={EvidenceDimension.CONTRADICTION},
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=3,
        )
        assert verdict == CorroborationVerdict.PARTIAL


# ═══════════════════════════════════════════════════════════
# SECTION 3: CLEAN AND PARTIAL  (spec tests 33, 34)
# ═══════════════════════════════════════════════════════════


class TestCleanVerdicts:

    def test_clean_claim_with_four_independent_classes_is_verified(self):
        """SPEC TEST 33."""
        verdict = assign_verdict(
            dimensions_fired=set(),
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=4,
        )
        assert verdict == CorroborationVerdict.VERIFIED

    def test_single_dimension_with_good_capacity_is_partial(self):
        """SPEC TEST 34."""
        verdict = assign_verdict(
            dimensions_fired={EvidenceDimension.SOURCE_INTEGRITY},
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=3,
        )
        assert verdict == CorroborationVerdict.PARTIAL

    def test_nothing_fired_but_thin_corroboration_is_not_verified(self):
        """Unreachable through the rule engine — EVD-CORR-001 fires on exactly
        this condition — but retained so a direct caller cannot fall off the
        end of the function into an unearned VERIFIED."""
        verdict = assign_verdict(
            dimensions_fired=set(),
            coverage_rules_fired=set(),
            corroboration_capacity=1.0,
            independent_classes=1,
        )
        assert verdict == CorroborationVerdict.PARTIAL

    def test_exactly_at_the_independence_threshold_verifies(self):
        assert assign_verdict(set(), set(), 1.0, 3) == CorroborationVerdict.VERIFIED

    def test_exactly_at_the_capacity_floor_is_not_blocked(self):
        """The floor is a strict minimum: at exactly 0.5 the gate may proceed."""
        verdict = assign_verdict(set(), set(), 0.5, 4)
        assert verdict == CorroborationVerdict.VERIFIED


# ═══════════════════════════════════════════════════════════
# SECTION 4: STRUCTURAL ISOLATION OF LAYER 5
# ═══════════════════════════════════════════════════════════


class TestCoverageIsNotADimension:

    def test_four_dimensions(self):
        assert len(DIMENSION_LAYER_MAP) == 4

    def test_coverage_layer_has_no_dimension(self):
        assert EvidenceRuleLayer.COVERAGE.value not in DIMENSION_LAYER_MAP.values()

    def test_dimensions_match_the_contradiction_capable_layers(self):
        """The schema's declaration and the gate's mapping must agree, or the
        guard in one of them is decorative."""
        assert set(DIMENSION_LAYER_MAP.values()) == set(CONTRADICTION_CAPABLE_LAYERS)

    def test_structural_guard_passes(self):
        assert_coverage_has_no_dimension()

    def test_structural_guard_catches_a_wired_in_coverage_layer(self):
        """The guard must actually catch the thing it exists to catch."""
        original = DIMENSION_LAYER_MAP.copy()
        try:
            DIMENSION_LAYER_MAP[EvidenceDimension.EXPECTED_ABSENCE] = \
                EvidenceRuleLayer.COVERAGE.value
            with pytest.raises(AssertionError, match="EXPECTED_ABSENCE"):
                assert_coverage_has_no_dimension()
        finally:
            DIMENSION_LAYER_MAP.clear()
            DIMENSION_LAYER_MAP.update(original)

    def test_coverage_findings_reported_separately_from_dimensions(self):
        outcome = evidence_gate(
            rules_result=rules(
                ("EVD-COV-001", COV, True),
                ("EVD-COV-002", COV, True),
            ),
            corroboration_capacity=1.0,
            independent_classes=4,
            classes_queryable=6,
        )
        assert outcome.coverage_findings == ["EVD-COV-001", "EVD-COV-002"]
        assert outcome.dimensions_fired == 0

    def test_coverage_rules_are_not_reported_as_contradictions(self):
        outcome = evidence_gate(
            rules_result=rules(("EVD-COV-002", COV, True)),
            corroboration_capacity=1.0,
            independent_classes=4,
        )
        assert outcome.contradictions == []


# ═══════════════════════════════════════════════════════════
# SECTION 5: THE GATE END TO END
# ═══════════════════════════════════════════════════════════


class TestEvidenceGate:

    def test_dimension_fires_from_its_layer(self):
        outcome = evidence_gate(
            rules_result=rules(("EVD-CON-001", CON, True)),
            corroboration_capacity=1.0,
            independent_classes=3,
        )
        con = next(d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.CONTRADICTION)
        assert con.fired is True
        assert con.observed_value == 1.0

    def test_dimension_does_not_fire_from_another_layer(self):
        outcome = evidence_gate(
            rules_result=rules(("EVD-ABS-001", ABS, True)),
            corroboration_capacity=1.0,
            independent_classes=3,
        )
        con = next(d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.CONTRADICTION)
        assert con.fired is False

    def test_every_dimension_is_reported_whether_or_not_it_fired(self):
        """Per-dimension traceability, as in delivery. A dimension that did
        not fire is a stated negative, not a silence."""
        outcome = evidence_gate(rules_result=rules(), corroboration_capacity=1.0)
        assert len(outcome.dimension_results) == 4

    def test_none_rules_result_does_not_read_as_clean(self):
        """An unanalysed dossier must not present as a verified one."""
        outcome = evidence_gate(rules_result=None, corroboration_capacity=0.0)
        assert outcome.verdict == CorroborationVerdict.UNVERIFIED
        assert outcome.dimensions_fired == 0

    def test_contradictions_populated_from_absence_and_contradiction_layers(self):
        outcome = evidence_gate(
            rules_result=rules(
                ("EVD-ABS-001", ABS, True),
                ("EVD-CON-003", CON, True),
                ("EVD-CORR-001", CORR, True),
                ("EVD-SRC-002", SRC, True),
            ),
            corroboration_capacity=1.0,
            independent_classes=0,
        )
        reported = {c["rule_id"] for c in outcome.contradictions}
        assert reported == {"EVD-ABS-001", "EVD-CON-003"}

    def test_corroboration_and_source_findings_are_not_called_contradictions(self):
        """They describe the quality of the evidence base, not a conflict with
        the claim. Labelling them contradictions would overstate the finding."""
        outcome = evidence_gate(
            rules_result=rules(
                ("EVD-CORR-002", CORR, True),
                ("EVD-SRC-001", SRC, True),
            ),
            corroboration_capacity=1.0,
            independent_classes=1,
        )
        assert outcome.contradictions == []
        assert outcome.dimensions_fired == 2

    def test_contradiction_entries_carry_evidence_and_recommendation(self):
        outcome = evidence_gate(
            rules_result=rules(("EVD-ABS-002", ABS, True)),
            corroboration_capacity=1.0,
            independent_classes=3,
        )
        entry = outcome.contradictions[0]
        for key in ("rule_id", "layer", "finding", "evidence",
                    "legal_basis", "confidence", "recommendation"):
            assert key in entry

    def test_capacity_figures_travel_with_the_verdict(self):
        """A Side 5 verdict is not interpretable without its reach. UNVERIFIED
        at 2 of 6 means something different from UNVERIFIED at 6 of 6."""
        outcome = evidence_gate(
            rules_result=rules(),
            corroboration_capacity=2 / 6,
            independent_classes=1,
            classes_queryable=2,
        )
        assert outcome.classes_queryable == 2
        assert outcome.corroboration_capacity == pytest.approx(2 / 6)
        assert "2 of 6" in outcome.methodology_note

    def test_methodology_note_states_the_capacity_rule(self):
        outcome = evidence_gate(rules_result=rules(), corroboration_capacity=1.0)
        assert "never contribute to CONTRADICTED" in outcome.methodology_note

    def test_deterministic(self):
        spec = (("EVD-ABS-001", ABS, True), ("EVD-CON-001", CON, True))
        a = evidence_gate(rules(*spec), 1.0, 2, 6)
        b = evidence_gate(rules(*spec), 1.0, 2, 6)
        assert a.verdict == b.verdict
        assert a.confidence == b.confidence
        assert a.contradictions == b.contradictions


class TestProfileParameterisation:

    def test_profile_can_tighten_the_capacity_floor(self):
        class Strict:
            min_corroboration_capacity = 0.9

        assert assign_verdict(set(), set(), 0.8, 4) == CorroborationVerdict.VERIFIED
        assert assign_verdict(set(), set(), 0.8, 4, profile=Strict()) == \
            CorroborationVerdict.UNVERIFIED

    def test_profile_can_tighten_the_independence_threshold(self):
        class Strict:
            min_independent_classes = 6

        assert assign_verdict(set(), set(), 1.0, 4) == CorroborationVerdict.VERIFIED
        assert assign_verdict(set(), set(), 1.0, 4, profile=Strict()) == \
            CorroborationVerdict.PARTIAL

    def test_profile_can_require_more_dimensions_for_contradiction(self):
        class Strict:
            min_dimensions_for_contradiction = 3

        dims = {EvidenceDimension.CONTRADICTION,
                EvidenceDimension.CORROBORATION_SUFFICIENCY}
        assert assign_verdict(dims, set(), 1.0, 1) == CorroborationVerdict.CONTRADICTED
        assert assign_verdict(dims, set(), 1.0, 1, profile=Strict()) == \
            CorroborationVerdict.PARTIAL

    def test_profile_can_require_two_rules_per_dimension(self):
        """The delivery-style convergence-within-a-layer setting remains
        available to any jurisdiction that wants it."""
        class Strict:
            min_rules_per_dimension = 2

        one_rule = rules(("EVD-CON-001", CON, True))
        assert evidence_gate(one_rule, 1.0, 3).dimensions_fired == 1
        assert evidence_gate(one_rule, 1.0, 3, profile=Strict()).dimensions_fired == 0


# ═══════════════════════════════════════════════════════════
# SECTION 6: CONFIDENCE
# ═══════════════════════════════════════════════════════════


class TestConfidence:

    def test_convergent_findings_beat_a_single_finding(self):
        """Two findings at 0.8 are worth more than one, because they had to
        be wrong together."""
        one = compute_confidence(CorroborationVerdict.PARTIAL, [0.8], 1.0, 1)
        two = compute_confidence(CorroborationVerdict.CONTRADICTED, [0.8, 0.8], 1.0, 1)
        assert two > one

    def test_low_capacity_widens_the_bounds(self):
        """'Findings at low capacity carry wider confidence bounds' has to be
        a property of the output, not a sentence in a report."""
        full = compute_confidence(CorroborationVerdict.CONTRADICTED, [0.85, 0.85], 1.0, 1)
        thin = compute_confidence(CorroborationVerdict.CONTRADICTED, [0.85, 0.85], 0.5, 1)
        assert thin < full

    def test_unverified_confidence_rises_as_capacity_falls(self):
        """A different quantity: certainty that no conclusion is available.
        The less we could see, the surer we are that we cannot conclude."""
        blind = compute_confidence(CorroborationVerdict.UNVERIFIED, [], 0.0, 0)
        partial_sight = compute_confidence(CorroborationVerdict.UNVERIFIED, [], 0.49, 0)
        assert blind > partial_sight

    def test_verified_confidence_rises_with_independent_corroboration(self):
        three = compute_confidence(CorroborationVerdict.VERIFIED, [], 1.0, 3)
        five = compute_confidence(CorroborationVerdict.VERIFIED, [], 1.0, 5)
        assert five > three

    def test_ghost_facility_pattern_exceeds_point_nine(self):
        """SPEC TEST 36 (confidence half): five converging findings at high
        capacity must clear 0.9."""
        confidence = compute_confidence(
            CorroborationVerdict.CONTRADICTED,
            [0.85, 0.82, 0.75, 0.70, 0.66],
            corroboration_capacity=5 / 6,
            independent_classes=0,
        )
        assert confidence > 0.9

    @pytest.mark.parametrize("verdict", list(CorroborationVerdict))
    def test_confidence_always_in_range(self, verdict):
        for capacity in (0.0, 0.5, 1.0):
            for fired in ([], [0.5], [0.9, 0.9, 0.9]):
                c = compute_confidence(verdict, fired, capacity, 3)
                assert 0.0 <= c <= 1.0

    def test_no_findings_no_spurious_confidence(self):
        c = compute_confidence(CorroborationVerdict.PARTIAL, [], 1.0, 1)
        assert c == pytest.approx(0.5)
