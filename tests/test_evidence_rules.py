"""
Tests for SUNLIGHT Side 5 — Evidence Rule Engine.

Covers spec tests 12-27: each of the 16 rules fires under its designed
condition and does NOT fire otherwise.

The non-firing half of each pair is the half that matters. A rule that fires
correctly but also fires on clean claims is a false-positive generator, and
in Side 5 a false positive is a structural finding against a country office.

Beyond the 16 pairs, three groups of tests exist because of what Side 5 is:

    Queryability guards — every Layer 2 rule must refuse to fire when the
    evidence it wants does not exist in the jurisdiction. Absence of an
    unreachable source is a limit on SUNLIGHT, not a fact about the claim.
    These are the poor-country guards at rule level.

    Layer 5 isolation — coverage rules must stay on the coverage layer, which
    has no path to a CONTRADICTED verdict.

    Determinism — no rule may read the wall clock. A finding that changes as
    time passes cannot be audited.
"""

import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_graph import EvidenceGraphBuilder
from evidence_rules import (
    COVERAGE_RULE_IDS,
    EvidenceRuleEngine,
    assert_layer_five_is_isolated,
    build_evidence_rules,
)
from evidence_schema import (
    CONTRADICTION_CAPABLE_LAYERS,
    CorroborationDossier,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceRuleLayer,
    EvidenceStatus,
    ExpectedEvidence,
    OutcomeClaim,
    OutcomeType,
    Provenance,
    SourceIndependence,
)


AWARD = date(2024, 1, 15)
COMPLETION = date(2025, 3, 1)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def prov(source_id="src", name="A Source"):
    """Valid provenance, so EVD-SRC-002 does not fire incidentally."""
    return Provenance(
        source_id=source_id,
        source_name=name,
        retrieval_timestamp=datetime(2025, 4, 1, tzinfo=timezone.utc),
        content_hash="a" * 64,
        hash_algorithm="sha256",
    )


def claim(outcome_type=OutcomeType.FACILITY_CONSTRUCTION, magnitude=200.0,
          completion=COMPLETION, award=AWARD):
    return OutcomeClaim(
        claim_id="CLAIM-001",
        contract_id="CONTRACT-001",
        outcome_type=outcome_type,
        claim_description="200-bed hospital operational",
        claimed_completion_date=completion,
        claimed_magnitude=magnitude,
        claimed_magnitude_unit="beds",
        site_latitude=9.0765,
        site_longitude=7.3986,
        country_code="ng",
        award_date=award,
    )


def art(aid, cls, status=EvidenceStatus.OBSERVED, party=None, observed_date=None,
        magnitude=None, integrity=None, provenance="default", desc=None):
    return EvidenceArtifact(
        artifact_id=aid,
        evidence_class=cls,
        claim_id="CLAIM-001",
        description=desc or f"artifact {aid}",
        status=status,
        observed_date=observed_date,
        observed_magnitude=magnitude,
        integrity_verified=integrity,
        provenance=prov() if provenance == "default" else provenance,
        source_party_id=party,
    )


def src(pid, name=None, ptype="government_agency", linked=None, contract_party=False,
        randomly_assigned=None, selected_by=None):
    return SourceIndependence(
        party_id=pid,
        party_name=name or f"Party {pid}",
        party_type=ptype,
        linked_parties=linked or [],
        is_contract_party=contract_party,
        randomly_assigned=randomly_assigned,
        selected_by=selected_by,
    )


def exp(eid, cls, required=True, queryable=True, by_month=None):
    return ExpectedEvidence(
        expectation_id=eid,
        evidence_class=cls,
        description=f"expected {eid}",
        required=required,
        queryable_in_jurisdiction=queryable,
        expected_by_month=by_month,
    )


def dossier(expectations=None, artifacts=None, sources=None, **claim_kwargs):
    """Build a dossier and populate its derived counts via the graph builder."""
    d = CorroborationDossier(
        claim=claim(**claim_kwargs),
        expected_evidence=expectations or [],
        artifacts=artifacts or [],
        source_registry=sources or [],
    )
    EvidenceGraphBuilder().build_graph(d)
    return d


def fired(d, rule_id, profile=None):
    """Did this specific rule fire against this dossier?"""
    result = EvidenceRuleEngine(profile=profile).evaluate(d)
    match = next(r for r in result.rule_results if r.rule_id == rule_id)
    return match.fired


def result_for(d, rule_id, profile=None):
    result = EvidenceRuleEngine(profile=profile).evaluate(d)
    return next(r for r in result.rule_results if r.rule_id == rule_id)


def three_independent_corroborations():
    """A clean evidence base: three unrelated outside parties corroborating."""
    return (
        [
            art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY"),
            art("A2", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                observed_date=date(2025, 2, 1)),
            art("A3", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                magnitude=200.0),
        ],
        [src("UTILITY"), src("IMAGERY", ptype="commercial_provider"), src("HEALTH_MIS")],
    )


# ═══════════════════════════════════════════════════════════
# SECTION 1: RULE SET SHAPE
# ═══════════════════════════════════════════════════════════


class TestRuleSet:

    def test_sixteen_rules(self):
        assert len(build_evidence_rules(None)) == 16

    def test_layer_distribution(self):
        rules = build_evidence_rules(None)
        counts = {}
        for r in rules:
            counts[r.layer] = counts.get(r.layer, 0) + 1
        assert counts == {
            EvidenceRuleLayer.CORROBORATION.value: 3,
            EvidenceRuleLayer.ABSENCE.value: 4,
            EvidenceRuleLayer.CONTRADICTION.value: 4,
            EvidenceRuleLayer.SOURCE.value: 3,
            EvidenceRuleLayer.COVERAGE.value: 2,
        }

    def test_rule_ids_unique(self):
        ids = [r.rule_id for r in build_evidence_rules(None)]
        assert len(ids) == len(set(ids))

    def test_every_rule_has_a_legal_basis(self):
        assert all(r.evidence_template.strip() for r in build_evidence_rules(None))

    def test_every_rule_has_a_recommendation(self):
        """A finding that does not say what would resolve it is not actionable."""
        assert all(r.recommendation.strip() for r in build_evidence_rules(None))

    def test_engine_evaluates_all_sixteen(self):
        assert EvidenceRuleEngine().evaluate(dossier()).rules_evaluated == 16

    def test_profile_parameterises_thresholds(self):
        """Closure pattern: thresholds bind from the profile at build time."""
        class Strict:
            min_independent_classes = 5

        artifacts, sources = three_independent_corroborations()
        d = dossier(artifacts=artifacts, sources=sources)
        assert fired(d, "EVD-CORR-001") is False
        assert fired(d, "EVD-CORR-001", profile=Strict()) is True

    def test_a_throwing_rule_degrades_to_not_fired(self):
        """Conservative direction: firing is what produces a finding."""
        engine = EvidenceRuleEngine()

        def explode(_):
            raise RuntimeError("boom")

        engine.rules[0].condition = explode
        result = engine.evaluate(dossier())
        assert result.rule_results[0].fired is False


# ═══════════════════════════════════════════════════════════
# SECTION 2: LAYER 1 — CORROBORATION SUFFICIENCY (spec 12-14)
# ═══════════════════════════════════════════════════════════


class TestCorroborationSufficiency:

    def test_corr_001_fires_on_insufficient_independence(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-CORR-001") is True

    def test_corr_001_silent_with_three_independent_sources(self):
        artifacts, sources = three_independent_corroborations()
        assert fired(dossier(artifacts=artifacts, sources=sources), "EVD-CORR-001") is False

    def test_corr_002_fires_on_single_source(self):
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="P1"),
                art("A2", EvidenceClass.ADVERSARIAL_OPEN, party="P1"),
            ],
            sources=[src("P1", "One Ministry")],
        )
        assert fired(d, "EVD-CORR-002") is True

    def test_corr_002_fires_when_two_names_are_one_source(self):
        """Linked parties are a single source however they are presented."""
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="PRIME"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="SUB"),
            ],
            sources=[src("PRIME", linked=["SUB"]), src("SUB")],
        )
        assert fired(d, "EVD-CORR-002") is True

    def test_corr_002_silent_with_independent_sources(self):
        artifacts, sources = three_independent_corroborations()
        assert fired(dossier(artifacts=artifacts, sources=sources), "EVD-CORR-002") is False

    def test_corr_002_silent_with_no_evidence(self):
        """No evidence at all is not a single-source problem — it is a
        coverage problem, and EVD-COV-001 owns it."""
        assert fired(dossier(), "EVD-CORR-002") is False

    def test_corr_003_fires_when_only_provider_side_evidence(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.ADVERSARIAL_OPEN, party="PRESS"),
            ],
            sources=[src("IP", contract_party=True), src("PRESS", ptype="civil_society")],
        )
        assert fired(d, "EVD-CORR-003") is True

    def test_corr_003_silent_when_third_party_evidence_present(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY")],
            sources=[src("UTILITY")],
        )
        assert fired(d, "EVD-CORR-003") is False

    def test_corr_003_silent_when_no_non_provider_class_is_reachable(self):
        """THE POOR-COUNTRY GUARD AT LAYER 1.

        Without this, the rule fires on every claim in every country that has
        no third-party registries, no monitor roster and no beneficiary-side
        systems — a finding generated purely by the absence of infrastructure.
        """
        d = dossier(
            expectations=[
                exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, queryable=False),
                exp("E2", EvidenceClass.FIELD_VERIFICATION, queryable=False),
                exp("E3", EvidenceClass.BENEFICIARY_SIDE, queryable=False),
            ],
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="IP")],
            sources=[src("IP", contract_party=True)],
        )
        assert fired(d, "EVD-CORR-003") is False


# ═══════════════════════════════════════════════════════════
# SECTION 3: LAYER 2 — EXPECTED ABSENCE (spec 15-18)
# ═══════════════════════════════════════════════════════════


class TestExpectedAbsence:

    def test_abs_001_fires_on_missing_permit(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                           EvidenceStatus.ABSENT, party="PERMITS",
                           desc="municipal construction permit")],
            sources=[src("PERMITS")],
        )
        assert fired(d, "EVD-ABS-001") is True

    def test_abs_001_silent_when_record_present(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS")],
            sources=[src("PERMITS")],
        )
        assert fired(d, "EVD-ABS-001") is False

    def test_abs_001_silent_when_registry_unqueryable(self):
        """No permit registry exists here. Its silence says nothing."""
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, queryable=False)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                           EvidenceStatus.UNQUERYABLE, party="PERMITS")],
            sources=[src("PERMITS")],
        )
        assert fired(d, "EVD-ABS-001") is False

    def test_abs_001_silent_when_never_queried(self):
        """An expectation with no artifact was never asked. Never-asked is not
        an absence — absence carries the provenance of the query."""
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[],
        )
        assert fired(d, "EVD-ABS-001") is False

    def test_abs_002_fires_when_no_structure_appeared(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.GEOSPATIAL)],
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, EvidenceStatus.ABSENT,
                           party="IMAGERY", desc="change detection over site polygon")],
            sources=[src("IMAGERY", ptype="commercial_provider")],
        )
        assert fired(d, "EVD-ABS-002") is True

    def test_abs_002_silent_for_non_physical_outcomes(self):
        """A cash transfer programme builds nothing. Expecting satellite change
        detection to show a footprint is a category error, and firing on its
        absence would manufacture a finding out of one."""
        d = dossier(
            outcome_type=OutcomeType.CASH_TRANSFER,
            expectations=[exp("E1", EvidenceClass.GEOSPATIAL)],
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, EvidenceStatus.ABSENT,
                           party="IMAGERY")],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-ABS-002") is False

    def test_abs_002_silent_when_imagery_unavailable(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.GEOSPATIAL, queryable=False)],
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, EvidenceStatus.UNQUERYABLE,
                           party="IMAGERY")],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-ABS-002") is False

    def test_abs_003_fires_on_zero_beneficiary_records(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.BENEFICIARY_SIDE)],
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, EvidenceStatus.ABSENT,
                           party="HEALTH_MIS", desc="patient encounter records")],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-ABS-003") is True

    def test_abs_003_silent_when_records_present(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.BENEFICIARY_SIDE)],
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS")],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-ABS-003") is False

    def test_abs_003_silent_when_no_health_information_system_exists(self):
        """THE POOR-COUNTRY GUARD AT LAYER 2.

        A country with no national health information system cannot produce
        patient records for a hospital that genuinely exists and genuinely
        treats people.
        """
        d = dossier(
            expectations=[exp("E1", EvidenceClass.BENEFICIARY_SIDE, queryable=False)],
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE,
                           EvidenceStatus.UNQUERYABLE, party="HEALTH_MIS")],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-ABS-003") is False

    def test_abs_004_fires_when_no_monitor_visit_in_window(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.FIELD_VERIFICATION)],
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, EvidenceStatus.ABSENT,
                           party="MONITOR")],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-ABS-004") is True

    def test_abs_004_silent_when_visit_inside_window(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.FIELD_VERIFICATION)],
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                           observed_date=date(2025, 4, 1))],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-ABS-004") is False

    def test_abs_004_fires_when_visit_far_outside_window(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.FIELD_VERIFICATION)],
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                           observed_date=date(2022, 1, 1))],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-ABS-004") is True

    def test_abs_004_silent_without_an_anchor_date(self):
        """No completion or award date means the window cannot be placed.
        Not assessable is not a finding."""
        d = dossier(
            completion=None, award=None,
            expectations=[exp("E1", EvidenceClass.FIELD_VERIFICATION)],
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, EvidenceStatus.ABSENT,
                           party="MONITOR")],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-ABS-004") is False

    def test_abs_004_silent_when_no_monitor_roster_exists(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.FIELD_VERIFICATION, queryable=False)],
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION,
                           EvidenceStatus.UNQUERYABLE, party="MONITOR")],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-ABS-004") is False


# ═══════════════════════════════════════════════════════════
# SECTION 4: LAYER 3 — CONTRADICTION (spec 19-22)
# ═══════════════════════════════════════════════════════════


class TestContradictionDetection:

    def test_con_001_fires_outside_the_expected_window(self):
        """Anchored on ExpectedEvidence.expected_by_month, measured from award.

        A utility connection expected at month 12 but dated month 1.5 is
        inconsistent with the build timeline it belongs to.
        """
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, by_month=12)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY",
                           observed_date=date(2024, 3, 1),
                           desc="utility connection record")],
            sources=[src("UTILITY")],
        )
        assert fired(d, "EVD-CON-001") is True

    def test_con_001_silent_inside_the_expected_window(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, by_month=4)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                           observed_date=date(2024, 5, 1))],
            sources=[src("PERMITS")],
        )
        assert fired(d, "EVD-CON-001") is False

    def test_con_001_does_not_fire_merely_because_evidence_predates_completion(self):
        """REGRESSION.

        The first design anchored on the claimed completion date and fired on
        anything dated materially before it. That condemns every genuine
        facility: a construction permit is issued long before a building is
        finished. The scenario suite caught it — a fully corroborated
        hospital came back with a contradiction against it.

        What is contradictory is not that evidence predates completion, but
        that it falls outside the window where that KIND of evidence belongs.
        """
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, by_month=4)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                           observed_date=date(2024, 5, 1),
                           desc="construction permit, 10 months before completion")],
            sources=[src("PERMITS")],
        )
        assert fired(d, "EVD-CON-001") is False

    def test_con_001_silent_without_an_expected_window(self):
        """No anchor, no finding."""
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY",
                           observed_date=date(2019, 1, 1))],
            sources=[src("UTILITY")],
        )
        assert fired(d, "EVD-CON-001") is False

    def test_con_001_silent_without_an_award_date(self):
        d = dossier(
            award=None,
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN, by_month=12)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="UTILITY",
                           observed_date=date(2024, 3, 1))],
            sources=[src("UTILITY")],
        )
        assert fired(d, "EVD-CON-001") is False

    def test_con_002_fires_on_magnitude_shortfall(self):
        """50 beds observed against 200 claimed."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                           magnitude=50.0, desc="monitor bed count")],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-CON-002") is True

    def test_con_002_silent_within_tolerance(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                           magnitude=190.0)],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-CON-002") is False

    def test_con_002_ignores_artifacts_with_no_magnitude(self):
        """Only explicitly measured magnitudes count. Parsing observed_value
        would make the finding depend on string formatting."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR")],
            sources=[src("MONITOR")],
        )
        assert fired(d, "EVD-CON-002") is False

    def test_con_002_excludes_beneficiary_side(self):
        """CON-002 and CON-004 are disjoint, so one observation cannot fire
        two rules and push the dimension over threshold on its own."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                           magnitude=10.0)],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-CON-002") is False
        assert fired(d, "EVD-CON-004") is True

    def test_con_002_confidence_scales_with_discrepancy(self):
        small = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="M", magnitude=140.0)],
            sources=[src("M")],
        )
        large = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="M", magnitude=20.0)],
            sources=[src("M")],
        )
        assert result_for(large, "EVD-CON-002").confidence > \
               result_for(small, "EVD-CON-002").confidence

    def test_con_003_fires_on_contradictory_imagery(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, EvidenceStatus.CONTRADICTORY,
                           party="IMAGERY", desc="no structural change on site polygon")],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-CON-003") is True

    def test_con_003_fires_when_structure_predates_award(self):
        """The building was already there before the contract that claims to
        have produced it."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                           observed_date=date(2023, 5, 1),
                           desc="structure present in pre-award imagery")],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-CON-003") is True

    def test_con_003_silent_when_structure_appeared_after_award(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                           observed_date=date(2024, 9, 1))],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-CON-003") is False

    def test_con_003_silent_without_award_date(self):
        d = dossier(
            award=None,
            artifacts=[art("A1", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                           observed_date=date(2023, 5, 1))],
            sources=[src("IMAGERY")],
        )
        assert fired(d, "EVD-CON-003") is False

    def test_con_004_fires_on_beneficiary_divergence(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                           magnitude=12.0, desc="patient encounter count")],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-CON-004") is True

    def test_con_004_silent_within_tolerance(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                           magnitude=180.0)],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-CON-004") is False

    def test_con_004_silent_without_a_claimed_magnitude(self):
        d = dossier(
            magnitude=None,
            artifacts=[art("A1", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                           magnitude=12.0)],
            sources=[src("HEALTH_MIS")],
        )
        assert fired(d, "EVD-CON-004") is False


# ═══════════════════════════════════════════════════════════
# SECTION 5: LAYER 4 — SOURCE INTEGRITY (spec 23-25)
# ═══════════════════════════════════════════════════════════


class TestSourceIntegrity:

    def test_src_001_fires_when_two_names_are_one_source(self):
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="PRIME"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="SUB"),
            ],
            sources=[src("PRIME", linked=["SUB"]), src("SUB")],
        )
        assert fired(d, "EVD-SRC-001") is True

    def test_src_001_silent_for_genuinely_independent_sources(self):
        artifacts, sources = three_independent_corroborations()
        assert fired(dossier(artifacts=artifacts, sources=sources), "EVD-SRC-001") is False

    def test_src_001_silent_for_one_party_submitting_twice(self):
        """That is EVD-CORR-002's finding. This rule is about a single source
        presented under two names."""
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="P1"),
                art("A2", EvidenceClass.ADVERSARIAL_OPEN, party="P1"),
            ],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-SRC-001") is False

    def test_src_002_fires_on_missing_provenance(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1", provenance=None)],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-SRC-002") is True

    def test_src_002_fires_on_failed_hash_reverification(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1", integrity=False)],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-SRC-002") is True

    def test_src_002_silent_on_intact_evidence(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1", integrity=True)],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-SRC-002") is False

    def test_src_002_silent_when_integrity_merely_unchecked(self):
        """None is not False. 'Not re-verified' is not 'found tampered'."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1", integrity=None)],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-SRC-002") is False

    def test_src_003_fires_on_monitor_not_randomly_assigned(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR")],
            sources=[src("MONITOR", randomly_assigned=False)],
        )
        assert fired(d, "EVD-SRC-003") is True

    def test_src_003_fires_when_monitor_chosen_by_the_implementing_partner(self):
        """A monitor selected by the party being monitored is provider-side
        evidence, whatever the monitor's own conduct."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR")],
            sources=[
                src("MONITOR", selected_by="IP"),
                src("IP", ptype="implementing_partner", contract_party=True),
            ],
        )
        assert fired(d, "EVD-SRC-003") is True

    def test_src_003_silent_for_randomly_assigned_monitor(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR")],
            sources=[src("MONITOR", randomly_assigned=True)],
        )
        assert fired(d, "EVD-SRC-003") is False

    def test_src_003_silent_when_selector_is_not_a_contract_party(self):
        """An oversight body assigning a monitor is not capture."""
        d = dossier(
            artifacts=[art("A1", EvidenceClass.FIELD_VERIFICATION, party="MONITOR")],
            sources=[
                src("MONITOR", selected_by="AUDIT_OFFICE"),
                src("AUDIT_OFFICE", ptype="government_agency"),
            ],
        )
        assert fired(d, "EVD-SRC-003") is False


# ═══════════════════════════════════════════════════════════
# SECTION 6: LAYER 5 — COVERAGE (spec 26-27)
# ═══════════════════════════════════════════════════════════


class TestCoverageAssessment:

    def test_cov_001_fires_on_thin_evidence_space(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.INSTITUTIONAL)],
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            sources=[src("P1")],
        )
        assert d.classes_queryable == 1
        assert fired(d, "EVD-COV-001") is True

    def test_cov_001_silent_with_adequate_coverage(self):
        artifacts, sources = three_independent_corroborations()
        d = dossier(artifacts=artifacts, sources=sources)
        assert d.classes_queryable == 3
        assert fired(d, "EVD-COV-001") is False

    def test_cov_002_fires_when_all_evidence_predates_the_window(self):
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="P1",
                    observed_date=date(2021, 1, 1)),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="P2",
                    observed_date=date(2021, 6, 1)),
            ],
            sources=[src("P1"), src("P2")],
        )
        assert fired(d, "EVD-COV-002") is True

    def test_cov_002_silent_when_any_evidence_is_fresh(self):
        d = dossier(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="P1",
                    observed_date=date(2021, 1, 1)),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="P2",
                    observed_date=date(2025, 2, 1)),
            ],
            sources=[src("P1"), src("P2")],
        )
        assert fired(d, "EVD-COV-002") is False

    def test_cov_002_silent_without_dated_evidence(self):
        d = dossier(
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            sources=[src("P1")],
        )
        assert fired(d, "EVD-COV-002") is False


class TestLayerFiveIsolation:
    """THE ARCHITECTURAL GUARD, at rule level.

    Coverage rules describe how far SUNLIGHT could see. If one were ever
    given a contradiction-capable layer, thin national infrastructure would
    start producing findings against the country. These tests fail loudly
    rather than let that happen quietly.
    """

    def test_coverage_rules_sit_on_the_coverage_layer(self):
        rules = {r.rule_id: r for r in build_evidence_rules(None)}
        for rid in COVERAGE_RULE_IDS:
            assert rules[rid].layer == EvidenceRuleLayer.COVERAGE.value

    def test_coverage_layer_is_not_contradiction_capable(self):
        assert EvidenceRuleLayer.COVERAGE.value not in CONTRADICTION_CAPABLE_LAYERS

    def test_isolation_guard_passes_on_the_shipped_rule_set(self):
        assert_layer_five_is_isolated(build_evidence_rules(None))

    def test_isolation_guard_catches_a_misfiled_coverage_rule(self):
        """The guard must actually catch the thing it exists to catch."""
        rules = build_evidence_rules(None)
        target = next(r for r in rules if r.rule_id == "EVD-COV-001")
        target.layer = EvidenceRuleLayer.ABSENCE.value
        with pytest.raises(AssertionError, match="EVD-COV-001"):
            assert_layer_five_is_isolated(rules)

    def test_isolation_guard_catches_a_stray_rule_on_the_coverage_layer(self):
        """A non-coverage rule parked on the coverage layer would be silently
        excluded from every verdict — a rule that can never matter."""
        rules = build_evidence_rules(None)
        target = next(r for r in rules if r.rule_id == "EVD-CON-001")
        target.layer = EvidenceRuleLayer.COVERAGE.value
        with pytest.raises(AssertionError, match="EVD-CON-001"):
            assert_layer_five_is_isolated(rules)

    def test_no_coverage_rule_reaches_a_contradiction_capable_layer(self):
        for rule in build_evidence_rules(None):
            if rule.rule_id in COVERAGE_RULE_IDS:
                assert rule.layer not in CONTRADICTION_CAPABLE_LAYERS


# ═══════════════════════════════════════════════════════════
# SECTION 7: DETERMINISM AND ADDITIVITY
# ═══════════════════════════════════════════════════════════


class TestDeterminism:

    def test_same_input_same_result(self):
        artifacts, sources = three_independent_corroborations()
        a = EvidenceRuleEngine().evaluate(dossier(artifacts=artifacts, sources=sources))
        artifacts, sources = three_independent_corroborations()
        b = EvidenceRuleEngine().evaluate(dossier(artifacts=artifacts, sources=sources))
        assert [r.rule_id for r in a.rule_results if r.fired] == \
               [r.rule_id for r in b.rule_results if r.fired]

    def test_no_rule_reads_the_wall_clock(self):
        """Determinism requirement. A staleness rule anchored on today returns
        a different answer next month, and an irreproducible finding cannot be
        audited — so EVD-COV-002 measures against the claim's own dates."""
        import ast
        import inspect
        import evidence_rules

        tree = ast.parse(inspect.getsource(evidence_rules))
        forbidden = {"today", "now", "utcnow", "time", "monotonic"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden, (
                    f"evidence_rules calls {node.func.attr}() — rule output "
                    f"must not depend on when it runs"
                )

    def test_rules_do_not_mutate_the_dossier(self):
        """Evaluation reads. Only the gate writes a verdict."""
        artifacts, sources = three_independent_corroborations()
        d = dossier(artifacts=artifacts, sources=sources)
        before = (d.verdict, d.confidence, len(d.artifacts), len(d.contradictions))
        EvidenceRuleEngine().evaluate(d)
        assert (d.verdict, d.confidence, len(d.artifacts), len(d.contradictions)) == before

    def test_layer_summary_counts_only_fired_rules(self):
        d = dossier(
            expectations=[exp("E1", EvidenceClass.THIRD_PARTY_ADMIN)],
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN,
                           EvidenceStatus.ABSENT, party="P1")],
            sources=[src("P1")],
        )
        result = EvidenceRuleEngine().evaluate(d)
        assert sum(result.layer_summary.values()) == result.rules_fired

    def test_clean_claim_fires_nothing_outside_coverage(self):
        """A well-evidenced claim in a jurisdiction with reach should produce
        no findings in the four contradiction-capable layers."""
        artifacts, sources = three_independent_corroborations()
        d = dossier(artifacts=artifacts, sources=sources)
        result = EvidenceRuleEngine().evaluate(d)
        fired_layers = {r.layer for r in result.rule_results if r.fired}
        assert fired_layers & CONTRADICTION_CAPABLE_LAYERS == set()
