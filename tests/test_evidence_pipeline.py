"""
Tests for SUNLIGHT Side 5 — Corroboration Pipeline and Analyzer.

Covers spec tests 36-41 (scenarios) and 46 (pipeline invariance), plus the
stage contracts.

The scenario tests are the ones an institution would actually recognise:
a ghost facility, a genuine facility, a thin-infrastructure country, a
facility built at a quarter of its contracted size, a structure that
predates the contract that claims to have built it, and a monitor chosen by
the party being monitored.

Scenario 38 is the one that protects everybody else. A country where only
two evidence classes are reachable must never reach CONTRADICTED, however
little corroboration it can produce, because it cannot produce the evidence
that would confirm a TRUE claim either.
"""

import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_analyzer import EvidenceAnalyzer, summarise_capacity
from evidence_pipeline import EvidencePipeline, resolve_expected_evidence
from evidence_schema import (
    CorroborationDossier,
    CorroborationVerdict,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceStage,
    EvidenceStatus,
    ExpectedEvidence,
    OutcomeClaim,
    OutcomeType,
    Provenance,
    SourceIndependence,
)
from provenance import ProvenanceError, create_provenance


AWARD = date(2024, 1, 15)
COMPLETION = date(2025, 3, 1)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def prov(source_id="src", name="A Source"):
    return Provenance(
        source_id=source_id,
        source_name=name,
        retrieval_timestamp=datetime(2025, 4, 1, tzinfo=timezone.utc),
        content_hash="a" * 64,
        hash_algorithm="sha256",
    )


def hospital_claim(magnitude=200.0, outcome=OutcomeType.FACILITY_CONSTRUCTION):
    return OutcomeClaim(
        claim_id="CLAIM-001",
        contract_id="CONTRACT-001",
        outcome_type=outcome,
        claim_description="200-bed hospital operational",
        claimed_completion_date=COMPLETION,
        claimed_magnitude=magnitude,
        claimed_magnitude_unit="beds",
        site_latitude=9.0765,
        site_longitude=7.3986,
        country_code="ng",
        country_office="Nigeria",
        award_date=AWARD,
        source_dossier_id="DELIVERY-9",
        source_recovery_id="RECOVERY-4",
    )


def art(aid, cls, status=EvidenceStatus.OBSERVED, party=None, observed_date=None,
        magnitude=None, provenance="default", desc=None):
    return EvidenceArtifact(
        artifact_id=aid,
        evidence_class=cls,
        claim_id="CLAIM-001",
        description=desc or f"artifact {aid}",
        status=status,
        observed_date=observed_date,
        observed_magnitude=magnitude,
        provenance=prov() if provenance == "default" else provenance,
        source_party_id=party,
    )


def src(pid, name=None, ptype="government_agency", linked=None, contract_party=False,
        randomly_assigned=None, selected_by=None):
    return SourceIndependence(
        party_id=pid, party_name=name or pid, party_type=ptype,
        linked_parties=linked or [], is_contract_party=contract_party,
        randomly_assigned=randomly_assigned, selected_by=selected_by,
    )


def exp(eid, cls, queryable=True, required=True):
    return ExpectedEvidence(
        expectation_id=eid, evidence_class=cls, description=f"expected {eid}",
        required=required, queryable_in_jurisdiction=queryable,
    )


FULL_EXPECTATIONS = [
    exp("E1", EvidenceClass.INSTITUTIONAL),
    exp("E2", EvidenceClass.THIRD_PARTY_ADMIN),
    exp("E3", EvidenceClass.GEOSPATIAL),
    exp("E4", EvidenceClass.FIELD_VERIFICATION),
    exp("E5", EvidenceClass.BENEFICIARY_SIDE),
]


def run(artifacts, sources, expectations=FULL_EXPECTATIONS, claim=None):
    return EvidencePipeline().run(
        claim=claim or hospital_claim(),
        artifacts=artifacts,
        source_registry=sources,
        expected_evidence=expectations,
    )


def fired_ids(dossier):
    return [r.rule_id for r in dossier.rules_result.rule_results if r.fired]


# ═══════════════════════════════════════════════════════════
# SECTION 1: SCENARIOS  (spec tests 36-41)
# ═══════════════════════════════════════════════════════════


class TestGhostFacility:
    """SPEC TEST 36.

    Construction claimed. Imagery obtained and shows no structural change.
    No permit, no utility connection, no staff on the professional register,
    zero patient encounters. Five classes reachable.
    """

    def _dossier(self):
        return run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP",
                    desc="implementing partner completion report"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, EvidenceStatus.ABSENT,
                    party="PERMITS", desc="municipal construction permit"),
                art("A3", EvidenceClass.THIRD_PARTY_ADMIN, EvidenceStatus.ABSENT,
                    party="UTILITY", desc="electricity connection record"),
                # Imagery ANSWERED. It shows no structure. That is a
                # contradiction, not an absence — see the pair in
                # test_evidence_evg.py.
                art("A4", EvidenceClass.GEOSPATIAL, EvidenceStatus.CONTRADICTORY,
                    party="IMAGERY",
                    desc="no structural change on site polygon, month 0 to 22"),
                art("A5", EvidenceClass.BENEFICIARY_SIDE, EvidenceStatus.ABSENT,
                    party="HEALTH_MIS", desc="patient encounter records"),
                art("A6", EvidenceClass.FIELD_VERIFICATION, EvidenceStatus.ABSENT,
                    party="MONITOR", desc="independent monitor visit"),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("PERMITS"), src("UTILITY"),
                src("IMAGERY", ptype="commercial_provider"),
                src("HEALTH_MIS"), src("MONITOR"),
            ],
        )

    def test_verdict_is_contradicted(self):
        assert self._dossier().verdict == CorroborationVerdict.CONTRADICTED

    def test_confidence_above_point_nine(self):
        assert self._dossier().confidence > 0.9

    def test_the_implementing_partner_report_does_not_corroborate(self):
        """Self-attestation is not corroboration. The only OBSERVED artifact
        is the contract party's own report, so independent corroboration is
        zero."""
        assert self._dossier().independent_classes_corroborating == 0

    def test_findings_span_multiple_evidence_classes(self):
        d = self._dossier()
        assert d.gate_outcome.dimensions_fired >= 3

    def test_output_is_structural_not_accusatory(self):
        """The finding never says the facility does not exist."""
        d = self._dossier()
        blob = " ".join(
            [d.disclaimer, d.gate_outcome.methodology_note]
            + [c["evidence"] for c in d.contradictions]
        ).lower()
        for forbidden in ("does not exist", "fraud", "fraudulent", "stole", "lied"):
            assert forbidden not in blob


class TestGenuineFacility:
    """SPEC TEST 37 — permit exists, structure appeared in window, utility
    connected, staff registered, patient records present."""

    def _dossier(self):
        return run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                    observed_date=date(2024, 5, 1), desc="construction permit"),
                art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 1, 10),
                    desc="structure appeared between month 4 and month 12"),
                art("A4", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                    observed_date=date(2025, 4, 2), magnitude=200.0,
                    desc="monitor site visit, 200 beds counted"),
                art("A5", EvidenceClass.BENEFICIARY_SIDE, party="HEALTH_MIS",
                    observed_date=date(2025, 5, 1), magnitude=200.0,
                    desc="patient encounter records"),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("PERMITS"), src("IMAGERY", ptype="commercial_provider"),
                src("MONITOR", randomly_assigned=True), src("HEALTH_MIS"),
            ],
        )

    def test_verdict_is_verified(self):
        assert self._dossier().verdict == CorroborationVerdict.VERIFIED

    def test_four_independent_corroborations(self):
        """The implementing partner's own report is excluded; the four outside
        parties are counted."""
        assert self._dossier().independent_classes_corroborating == 4

    def test_nothing_fired(self):
        assert fired_ids(self._dossier()) == []

    def test_no_contradictions_reported(self):
        assert self._dossier().contradictions == []


class TestThinInfrastructureCountry:
    """SPEC TEST 38 — THE GUARD SCENARIO.

    Only institutional and geospatial sources exist in this country. Both
    are consistent with the claim. There is very little corroboration, and
    that must never become a finding against the country: a jurisdiction with
    two reachable classes cannot produce the evidence that would confirm a
    true claim either.
    """

    def _dossier(self):
        return run(
            expectations=[
                exp("E1", EvidenceClass.INSTITUTIONAL),
                exp("E2", EvidenceClass.GEOSPATIAL),
                exp("E3", EvidenceClass.THIRD_PARTY_ADMIN, queryable=False),
                exp("E4", EvidenceClass.FIELD_VERIFICATION, queryable=False),
                exp("E5", EvidenceClass.BENEFICIARY_SIDE, queryable=False),
            ],
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 1, 10)),
                art("A3", EvidenceClass.THIRD_PARTY_ADMIN,
                    EvidenceStatus.UNQUERYABLE, party="PERMITS"),
                art("A4", EvidenceClass.FIELD_VERIFICATION,
                    EvidenceStatus.UNQUERYABLE, party="MONITOR"),
                art("A5", EvidenceClass.BENEFICIARY_SIDE,
                    EvidenceStatus.UNQUERYABLE, party="HEALTH_MIS"),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("IMAGERY", ptype="commercial_provider"),
                src("PERMITS"), src("MONITOR"), src("HEALTH_MIS"),
            ],
        )

    def test_never_contradicted(self):
        """The assertion this whole architecture exists to guarantee."""
        assert self._dossier().verdict != CorroborationVerdict.CONTRADICTED

    def test_verdict_is_unverified_or_partial(self):
        assert self._dossier().verdict in (
            CorroborationVerdict.UNVERIFIED, CorroborationVerdict.PARTIAL)

    def test_capacity_is_reported_honestly(self):
        d = self._dossier()
        assert d.classes_queryable == 2
        assert d.corroboration_capacity == pytest.approx(2 / 6)

    def test_unqueryable_classes_do_not_produce_absence_findings(self):
        """No Layer 2 rule may fire on a source that does not exist here."""
        fired = fired_ids(self._dossier())
        assert not any(r.startswith("EVD-ABS-") for r in fired)

    def test_provider_side_rule_does_not_fire_either(self):
        """EVD-CORR-003 would otherwise punish the country for having no
        non-provider registries at all."""
        assert "EVD-CORR-003" not in fired_ids(self._dossier())


class TestMagnitudeFraud:
    """SPEC TEST 39 — the facility exists, at 50 beds against 200 claimed."""

    def _dossier(self):
        return run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP",
                    desc="partner report claiming 200 beds"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                    observed_date=date(2024, 5, 1)),
                art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 1, 10)),
                # The sources that answered CONTRADICT rather than corroborate,
                # which is why independent corroboration of the claim as made
                # also collapses.
                art("A4", EvidenceClass.FIELD_VERIFICATION,
                    EvidenceStatus.CONTRADICTORY, party="MONITOR",
                    observed_date=date(2025, 4, 2), magnitude=50.0,
                    desc="monitor counted 50 beds"),
                art("A5", EvidenceClass.BENEFICIARY_SIDE,
                    EvidenceStatus.CONTRADICTORY, party="HEALTH_MIS",
                    observed_date=date(2025, 5, 1), magnitude=48.0,
                    desc="patient volumes consistent with 48 beds"),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("PERMITS"), src("IMAGERY", ptype="commercial_provider"),
                src("MONITOR", randomly_assigned=True), src("HEALTH_MIS"),
            ],
        )

    def test_evd_con_002_fires(self):
        assert "EVD-CON-002" in fired_ids(self._dossier())

    def test_verdict_is_contradicted(self):
        assert self._dossier().verdict == CorroborationVerdict.CONTRADICTED

    def test_the_contradiction_names_both_figures(self):
        d = self._dossier()
        evidence = next(
            c["evidence"] for c in d.contradictions if c["rule_id"] == "EVD-CON-002")
        assert "200" in evidence and "50" in evidence


class TestTimelineFraud:
    """SPEC TEST 40 — the structure in imagery predates the contract award."""

    def _dossier(self):
        return run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.GEOSPATIAL, EvidenceStatus.CONTRADICTORY,
                    party="IMAGERY", observed_date=date(2023, 5, 1),
                    desc="structure present in imagery predating award"),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("IMAGERY", ptype="commercial_provider"),
            ],
        )

    def test_evd_con_003_fires(self):
        assert "EVD-CON-003" in fired_ids(self._dossier())

    def test_verdict_is_contradicted(self):
        assert self._dossier().verdict == CorroborationVerdict.CONTRADICTED

    def test_observed_predating_imagery_also_caught(self):
        """Defence in depth: even when ingestion classified the imagery as a
        plain observation, a structure visible before the award date is still
        inconsistent with the claim that this contract produced it."""
        d = run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.GEOSPATIAL, EvidenceStatus.OBSERVED,
                    party="IMAGERY", observed_date=date(2023, 5, 1)),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("IMAGERY", ptype="commercial_provider"),
            ],
        )
        assert "EVD-CON-003" in fired_ids(d)


class TestCapturedMonitor:
    """SPEC TEST 41 — field verification exists, but the implementing partner
    chose the monitor."""

    def _dossier(self):
        return run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                    observed_date=date(2024, 5, 1)),
                art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 1, 10)),
                art("A4", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                    observed_date=date(2025, 4, 2)),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("PERMITS"), src("IMAGERY", ptype="commercial_provider"),
                src("MONITOR", "Selected Monitor", selected_by="IP"),
            ],
        )

    def test_evd_src_003_fires(self):
        assert "EVD-SRC-003" in fired_ids(self._dossier())

    def test_not_escalated_to_contradicted_on_its_own(self):
        """A captured monitor undermines the evidence base; it is not itself
        evidence that the claim is false."""
        assert self._dossier().verdict != CorroborationVerdict.CONTRADICTED

    def test_a_randomly_assigned_monitor_does_not_fire_it(self):
        d = run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                    observed_date=date(2024, 5, 1)),
                art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 1, 10)),
                art("A4", EvidenceClass.FIELD_VERIFICATION, party="MONITOR",
                    observed_date=date(2025, 4, 2)),
            ],
            sources=[
                src("IP", "Implementing Partner", "implementing_partner",
                    contract_party=True),
                src("PERMITS"), src("IMAGERY", ptype="commercial_provider"),
                src("MONITOR", randomly_assigned=True),
            ],
        )
        assert "EVD-SRC-003" not in fired_ids(d)


# ═══════════════════════════════════════════════════════════
# SECTION 2: STAGE 13 — INGESTION
# ═══════════════════════════════════════════════════════════


class TestStage13Ingestion:

    def test_valid_artifacts_admitted(self):
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
        )
        assert len(d.artifacts) == 1
        assert d.rejected_artifacts == []
        assert d.stage == EvidenceStage.INGESTED

    def test_artifact_without_provenance_is_refused(self):
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1",
                           provenance=None)],
        )
        assert d.artifacts == []
        assert len(d.rejected_artifacts) == 1

    def test_refusal_is_quarantine_not_deletion(self):
        """The artifact must not corroborate anything, and must still be
        visible to whoever submitted it."""
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[art("A7", EvidenceClass.INSTITUTIONAL, party="P1",
                           provenance=None)],
        )
        assert d.rejected_artifacts[0].artifact_id == "A7"
        assert any("A7" in str(e.get("artifact_id")) for e in d.errors)

    def test_rejection_reason_is_specific(self):
        """'3 artifacts rejected' is not actionable. Name the defect."""
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1",
                           provenance=None)],
        )
        assert "provenance" in d.errors[0]["error"].lower()

    def test_quarantined_artifact_still_produces_a_custody_finding(self):
        """THE POINT OF QUARANTINE.

        If refusal removed the artifact from view, a broken chain of custody
        would silently present as an absence of evidence — a different and
        much weaker finding.
        """
        d = run(
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP", provenance=None),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS"),
            ],
            sources=[src("IP", contract_party=True), src("PERMITS")],
        )
        assert "EVD-SRC-002" in fired_ids(d)

    def test_quarantined_artifact_cannot_corroborate(self):
        d = EvidencePipeline().run(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="P1",
                           provenance=None)],
            source_registry=[src("P1")],
        )
        assert d.independent_classes_corroborating == 0

    def test_strict_mode_raises(self):
        with pytest.raises(ProvenanceError):
            EvidencePipeline().ingest(
                claim=hospital_claim(),
                artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, provenance=None)],
                strict=True,
            )

    def test_mixed_batch_admits_the_good_and_refuses_the_bad(self):
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[
                art("GOOD", EvidenceClass.INSTITUTIONAL, party="P1"),
                art("BAD", EvidenceClass.GEOSPATIAL, party="P2", provenance=None),
            ],
        )
        assert [a.artifact_id for a in d.artifacts] == ["GOOD"]
        assert [a.artifact_id for a in d.rejected_artifacts] == ["BAD"]

    def test_real_provenance_round_trips(self):
        content = b"permit no. 44182"
        p = create_provenance("ng-permits", "FCT Development Control", content)
        d = EvidencePipeline().ingest(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.THIRD_PARTY_ADMIN, party="P1",
                           provenance=p)],
        )
        assert len(d.artifacts) == 1
        assert d.artifacts[0].provenance.verify_hash(content) is True


# ═══════════════════════════════════════════════════════════
# SECTION 3: STAGE 14 — RESOLUTION
# ═══════════════════════════════════════════════════════════


class TestStage14Resolution:

    MAP = {
        "facility_construction": [
            {"expectation_id": "NG-FC-01",
             "evidence_class": "third_party_admin",
             "description": "municipal construction permit",
             "expected_by_month": 6},
            {"expectation_id": "NG-FC-02",
             "evidence_class": "geospatial",
             "description": "satellite change detection over site polygon"},
        ],
        "cash_transfer": [
            {"expectation_id": "NG-CT-01",
             "evidence_class": "beneficiary_side",
             "description": "mobile money transaction records"},
        ],
    }

    def test_expectations_resolved_for_the_outcome_type(self):
        resolved = resolve_expected_evidence(hospital_claim(), evidence_map=self.MAP)
        assert [e.expectation_id for e in resolved] == ["NG-FC-01", "NG-FC-02"]

    def test_a_different_outcome_type_gets_a_different_map(self):
        """A road and a cash transfer leave different traces. Expecting one to
        produce the other's evidence would manufacture a false absence."""
        claim = hospital_claim(outcome=OutcomeType.CASH_TRANSFER)
        resolved = resolve_expected_evidence(claim, evidence_map=self.MAP)
        assert [e.evidence_class for e in resolved] == [EvidenceClass.BENEFICIARY_SIDE]

    def test_unmapped_outcome_type_yields_nothing(self):
        """An honest empty, not a guess. A fabricated expectation would
        produce a fabricated absence."""
        claim = hospital_claim(outcome=OutcomeType.CAPACITY_BUILDING)
        assert resolve_expected_evidence(claim, evidence_map=self.MAP) == []

    def test_jurisdiction_reachability_overrides_the_map(self):
        """A map that expects a utility registry in a country without one must
        not generate an absence finding."""
        resolved = resolve_expected_evidence(
            hospital_claim(), evidence_map=self.MAP,
            queryable_classes={EvidenceClass.GEOSPATIAL},
        )
        by_id = {e.expectation_id: e for e in resolved}
        assert by_id["NG-FC-01"].queryable_in_jurisdiction is False
        assert by_id["NG-FC-02"].queryable_in_jurisdiction is True

    def test_unknown_evidence_class_is_skipped_not_fatal(self):
        """A typo in one jurisdiction map degrades that expectation, not
        analysis of every claim in the country."""
        bad = {"facility_construction": [
            {"expectation_id": "X", "evidence_class": "not_a_real_class"},
            {"expectation_id": "Y", "evidence_class": "geospatial"},
        ]}
        resolved = resolve_expected_evidence(hospital_claim(), evidence_map=bad)
        assert [e.expectation_id for e in resolved] == ["Y"]

    def test_caller_supplied_expectations_are_preserved(self):
        """A caller who states what they expect has made a deliberate claim
        about this project. It is not silently replaced."""
        mine = [exp("MINE", EvidenceClass.ADVERSARIAL_OPEN)]
        d = EvidencePipeline().run(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            source_registry=[src("P1")],
            expected_evidence=mine,
        )
        assert [e.expectation_id for e in d.expected_evidence] == ["MINE"]

    def test_stage_marks_queryable_classes(self):
        d = run(
            expectations=[
                exp("E1", EvidenceClass.INSTITUTIONAL),
                exp("E2", EvidenceClass.GEOSPATIAL, queryable=False),
            ],
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            sources=[src("P1")],
        )
        assert d.classes_queryable == 1


# ═══════════════════════════════════════════════════════════
# SECTION 4: STAGES 15-16 AND PIPELINE MECHANICS
# ═══════════════════════════════════════════════════════════


class TestPipelineMechanics:

    def test_stages_advance_to_complete(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        assert d.stage == EvidenceStage.COMPLETE

    def test_every_stage_is_timed(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        for stage in (EvidenceStage.RESOLVED, EvidenceStage.GRAPHED, EvidenceStage.GATED):
            assert stage.value in d.processing_ms

    def test_graph_and_rules_both_run(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        assert d.graph is not None
        assert d.rules_result.rules_evaluated == 16

    def test_gate_writes_the_verdict(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        assert d.verdict is not None
        assert d.gate_outcome is not None
        assert d.evaluated_at is not None

    def test_a_failing_stage_is_recorded_not_swallowed(self):
        pipeline = EvidencePipeline()
        pipeline.graph_builder = None       # provoke a stage failure
        d = pipeline.ingest(claim=hospital_claim())
        d = pipeline.process(d)
        assert d.stage == EvidenceStage.FAILED
        assert d.errors

    def test_empty_dossier_does_not_read_as_verified(self):
        """No evidence at all must not present as a confirmed claim."""
        d = EvidencePipeline().run(claim=hospital_claim())
        assert d.verdict != CorroborationVerdict.VERIFIED

    def test_deterministic(self):
        a = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        b = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        assert a.verdict == b.verdict
        assert a.confidence == b.confidence
        assert fired_ids(a) == fired_ids(b)


class TestPipelineInvariance:
    """SPEC TEST 46 — Side 5 does not modify Side 1, 2, 3 or 4 output."""

    def test_claim_links_are_read_only(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        assert d.claim.source_dossier_id == "DELIVERY-9"
        assert d.claim.source_recovery_id == "RECOVERY-4"

    def test_pipeline_imports_no_other_side(self):
        """Structural, not aspirational. Side 5's modules may read the
        jurisdiction profile — Side 1's parameters — but must not import any
        Side 2, 3 or 4 engine."""
        import ast
        import inspect

        import evidence_analyzer
        import evidence_evg
        import evidence_graph
        import evidence_pipeline
        import evidence_rules
        import evidence_schema
        import provenance as provenance_mod

        forbidden_prefixes = (
            "delivery_", "recovery_", "impact_", "redirection",
            "alert", "tca_", "cri_", "evg", "api",
        )
        for module in (evidence_schema, provenance_mod, evidence_graph,
                       evidence_rules, evidence_evg, evidence_pipeline,
                       evidence_analyzer):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name.startswith("evidence_") or name == "provenance":
                        continue
                    assert not name.startswith(forbidden_prefixes), (
                        f"{module.__name__} imports {name} — Side 5 must not "
                        f"reach into another side"
                    )

    def test_side_5_holds_no_handle_on_another_side_object(self):
        d = run([art("A1", EvidenceClass.INSTITUTIONAL, party="P1")], [src("P1")])
        for forbidden in ("delivery_dossier", "recovery_record", "contract_dossier",
                          "impact_report"):
            assert not hasattr(d, forbidden)


# ═══════════════════════════════════════════════════════════
# SECTION 5: THE ANALYZER
# ═══════════════════════════════════════════════════════════


class TestAnalyzer:

    def _result(self):
        return EvidenceAnalyzer().analyze(
            claim=hospital_claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            source_registry=[src("P1")],
            expected_evidence=FULL_EXPECTATIONS,
        )

    def test_result_shape(self):
        r = self._result()
        for key in ("dossier_id", "claim_id", "verdict", "confidence",
                    "corroboration_capacity", "classes_queryable",
                    "independent_classes_corroborating", "contradictions",
                    "coverage_findings", "rule_fires", "disclaimer"):
            assert key in r

    def test_capacity_always_travels_with_the_verdict(self):
        """A verdict without its reach is misleading by omission."""
        r = self._result()
        assert r["verdict"] is not None
        assert r["corroboration_capacity"] is not None
        assert r["classes_total"] == 6

    def test_rejections_are_reported_specifically(self):
        r = EvidenceAnalyzer().analyze(
            claim=hospital_claim(),
            artifacts=[art("A9", EvidenceClass.INSTITUTIONAL, provenance=None)],
        )
        assert r["artifacts_rejected"] == 1
        assert r["rejections"][0]["artifact_id"] == "A9"
        assert r["rejections"][0]["reason"]

    def test_batch_keeps_unverified_separate_from_contradicted(self):
        """At portfolio level this matters as much as at claim level. Merging
        the two would read as a pattern of contradicted claims in exactly the
        country offices whose registries are thinnest."""
        analyzer = EvidenceAnalyzer()
        batch = analyzer.batch_analyze([
            {"claim": hospital_claim(),
             "artifacts": [art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
             "source_registry": [src("P1")]},
        ])
        dist = batch["verdict_distribution"]
        assert "unverified" in dist and "contradicted" in dist
        assert dist["unverified"] != dist["contradicted"] or dist["contradicted"] == 0

    def test_batch_reports_average_capacity(self):
        analyzer = EvidenceAnalyzer()
        batch = analyzer.batch_analyze([
            {"claim": hospital_claim(),
             "artifacts": [art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
             "source_registry": [src("P1")]},
        ])
        assert 0.0 <= batch["average_corroboration_capacity"] <= 1.0

    def test_stats_track_verdicts(self):
        analyzer = EvidenceAnalyzer()
        analyzer.analyze(claim=hospital_claim())
        assert analyzer.stats()["claims_analyzed"] == 1


class TestCapacityDisclosure:
    """GET /evidence/capacity/{country_code} — honest disclosure of the ceiling."""

    class ThinProfile:
        queryable_classes = ["institutional", "geospatial"]

    class RichProfile:
        queryable_classes = [
            "institutional", "third_party_admin", "geospatial",
            "field_verification", "beneficiary_side", "adversarial_open",
        ]

    def test_thin_jurisdiction_declares_no_adverse_conclusion_available(self):
        out = summarise_capacity("ng", profile=self.ThinProfile())
        assert out["classes_queryable"] == 2
        assert out["adverse_conclusion_available"] is False
        assert out["strongest_available_conclusion"] == "unverified"

    def test_thin_jurisdiction_names_what_is_unreachable(self):
        """An institution is entitled to know what SUNLIGHT cannot see here
        before it submits anything."""
        out = summarise_capacity("ng", profile=self.ThinProfile())
        assert "beneficiary_side" in out["unqueryable_classes"]
        assert len(out["unqueryable_classes"]) == 4

    def test_rich_jurisdiction_allows_adverse_conclusions(self):
        out = summarise_capacity("ua", profile=self.RichProfile())
        assert out["corroboration_capacity_ceiling"] == 1.0
        assert out["adverse_conclusion_available"] is True

    def test_note_states_the_principle(self):
        out = summarise_capacity("ng", profile=self.ThinProfile())
        assert "not evidence of absence" in out["note"]

    def test_unknown_profile_reports_zero_rather_than_guessing(self):
        out = summarise_capacity("zz", profile=None)
        assert out["classes_queryable"] == 0
        assert out["adverse_conclusion_available"] is False
