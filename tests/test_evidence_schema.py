"""
Tests for SUNLIGHT Side 5 — Evidence Corroboration Schema.

Covers:
    Enumerations:
        - Six evidence classes, and EVIDENCE_CLASS_COUNT tracks them
        - Four corroboration verdicts — UNVERIFIED is distinct from CONTRADICTED
        - Five rule layers, and COVERAGE excluded from contradiction-capable set

    corroboration_capacity:
        - Computed as queryable / total
        - Zero denominator handled without ZeroDivisionError
        - Clamped to [0, 1] so a malformed count cannot manufacture capacity

    Artifact and expectation semantics:
        - corroborates is true only for OBSERVED
        - contradicts is true only for CONTRADICTORY, never for ABSENT/UNQUERYABLE
        - absence_is_meaningful requires both required and queryable

    Source independence:
        - A contract party cannot independently corroborate its own delivery

The architectural guard tested here is the one the whole side rests on:
absence of reachable evidence must not be convertible into a negative
finding. Several assertions below exist to fail loudly if that ever changes.
"""

import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_schema import (
    CONTRADICTION_CAPABLE_LAYERS,
    EVIDENCE_CLASS_COUNT,
    CorroborationDossier,
    CorroborationVerdict,
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


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def claim():
    """A 200-bed hospital claimed operational — the canonical Side 5 example."""
    return OutcomeClaim(
        claim_id="CLAIM-001",
        contract_id="CONTRACT-001",
        outcome_type=OutcomeType.FACILITY_CONSTRUCTION,
        claim_description="200-bed hospital operational",
        claimed_completion_date=date(2025, 3, 1),
        claimed_magnitude=200.0,
        claimed_magnitude_unit="beds",
        site_latitude=9.0765,
        site_longitude=7.3986,
        country_code="ng",
        award_date=date(2024, 1, 1),
    )


def _artifact(status, evidence_class=EvidenceClass.INSTITUTIONAL, aid="ART-1"):
    return EvidenceArtifact(
        artifact_id=aid,
        evidence_class=evidence_class,
        claim_id="CLAIM-001",
        description="test artifact",
        status=status,
    )


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# ═══════════════════════════════════════════════════════════


class TestEvidenceClass:

    def test_six_classes_exist(self):
        assert len(EvidenceClass) == 6

    def test_class_count_constant_tracks_the_enum(self):
        """EVIDENCE_CLASS_COUNT is the capacity denominator. It must not drift."""
        assert EVIDENCE_CLASS_COUNT == len(EvidenceClass)

    def test_all_six_named(self):
        values = {c.value for c in EvidenceClass}
        assert values == {
            "institutional",
            "third_party_admin",
            "geospatial",
            "field_verification",
            "beneficiary_side",
            "adversarial_open",
        }


class TestCorroborationVerdict:

    def test_four_verdicts_exist(self):
        """Four, not three. The fourth is the poor-country guard."""
        assert len(CorroborationVerdict) == 4

    def test_unverified_is_not_contradicted(self):
        """The single most important distinction in Side 5."""
        assert CorroborationVerdict.UNVERIFIED != CorroborationVerdict.CONTRADICTED
        assert CorroborationVerdict.UNVERIFIED.value == "unverified"
        assert CorroborationVerdict.CONTRADICTED.value == "contradicted"


class TestOutcomeType:

    def test_seven_outcome_types(self):
        assert len(OutcomeType) == 7

    def test_cash_transfer_distinct_from_construction(self):
        """Different outcome types expect different evidence. Conflating them
        would manufacture false absences — no permit exists for a cash grant."""
        assert OutcomeType.CASH_TRANSFER != OutcomeType.FACILITY_CONSTRUCTION


class TestEvidenceStatus:

    def test_absent_and_unqueryable_are_distinct(self):
        """ABSENT means asked and not found. UNQUERYABLE means could not ask.
        Merging them is the failure mode this architecture exists to prevent."""
        assert EvidenceStatus.ABSENT != EvidenceStatus.UNQUERYABLE

    def test_five_statuses(self):
        assert len(EvidenceStatus) == 5


class TestRuleLayers:

    def test_five_layers(self):
        assert len(EvidenceRuleLayer) == 5

    def test_coverage_layer_cannot_contribute_to_contradiction(self):
        """THE ARCHITECTURAL GUARD.

        Layer 5 measures how much of the evidence space was reachable. It must
        never be able to push a verdict to CONTRADICTED, because that would
        convert thin national infrastructure into a finding against the
        country. Enforced by construction: COVERAGE is not in the set.
        """
        assert EvidenceRuleLayer.COVERAGE.value not in CONTRADICTION_CAPABLE_LAYERS

    def test_the_other_four_layers_are_contradiction_capable(self):
        for layer in (
            EvidenceRuleLayer.CORROBORATION,
            EvidenceRuleLayer.ABSENCE,
            EvidenceRuleLayer.CONTRADICTION,
            EvidenceRuleLayer.SOURCE,
        ):
            assert layer.value in CONTRADICTION_CAPABLE_LAYERS

    def test_contradiction_capable_set_has_exactly_four_members(self):
        """If a fifth ever appears, someone has wired COVERAGE in. Fail loudly."""
        assert len(CONTRADICTION_CAPABLE_LAYERS) == 4


# ═══════════════════════════════════════════════════════════
# SECTION 2: CORROBORATION CAPACITY  (spec tests 6 and 7)
# ═══════════════════════════════════════════════════════════


class TestCorroborationCapacity:

    def test_capacity_computed_correctly(self, claim):
        """Spec test 6."""
        d = CorroborationDossier(claim=claim, classes_queryable=3, classes_total=6)
        assert d.corroboration_capacity == 0.5

    def test_full_capacity(self, claim):
        d = CorroborationDossier(claim=claim, classes_queryable=6, classes_total=6)
        assert d.corroboration_capacity == 1.0

    def test_zero_denominator_handled(self, claim):
        """Spec test 7 — no ZeroDivisionError, returns 0.0."""
        d = CorroborationDossier(claim=claim, classes_queryable=0, classes_total=0)
        assert d.corroboration_capacity == 0.0

    def test_negative_denominator_handled(self, claim):
        """Malformed input must not raise, and must not yield usable capacity."""
        d = CorroborationDossier(claim=claim, classes_queryable=3, classes_total=-1)
        assert d.corroboration_capacity == 0.0

    def test_capacity_clamped_to_one(self, claim):
        """A miscount must not manufacture capacity above 1.0 — capacity above
        the profile floor is what unlocks an adverse verdict."""
        d = CorroborationDossier(claim=claim, classes_queryable=99, classes_total=6)
        assert d.corroboration_capacity == 1.0

    def test_zero_queryable_is_zero_capacity(self, claim):
        d = CorroborationDossier(claim=claim, classes_queryable=0, classes_total=6)
        assert d.corroboration_capacity == 0.0

    def test_default_total_is_the_class_count(self, claim):
        d = CorroborationDossier(claim=claim)
        assert d.classes_total == EVIDENCE_CLASS_COUNT


# ═══════════════════════════════════════════════════════════
# SECTION 3: ARTIFACT SEMANTICS
# ═══════════════════════════════════════════════════════════


class TestArtifactSemantics:

    def test_observed_corroborates(self):
        assert _artifact(EvidenceStatus.OBSERVED).corroborates is True

    def test_contradictory_contradicts(self):
        assert _artifact(EvidenceStatus.CONTRADICTORY).contradicts is True

    @pytest.mark.parametrize("status", [
        EvidenceStatus.ABSENT,
        EvidenceStatus.UNQUERYABLE,
        EvidenceStatus.STALE,
        EvidenceStatus.CONTRADICTORY,
    ])
    def test_only_observed_corroborates(self, status):
        assert _artifact(status).corroborates is False

    @pytest.mark.parametrize("status", [
        EvidenceStatus.ABSENT,
        EvidenceStatus.UNQUERYABLE,
        EvidenceStatus.OBSERVED,
        EvidenceStatus.STALE,
    ])
    def test_absence_never_contradicts_at_artifact_level(self, status):
        """Absence is handled by the Layer 2 rules, which check queryability
        first. Nothing converts a missing record into a contradiction here."""
        assert _artifact(status).contradicts is False

    def test_stale_does_not_corroborate(self):
        """Stale evidence shows the claim held outside the window of interest."""
        assert _artifact(EvidenceStatus.STALE).corroborates is False


# ═══════════════════════════════════════════════════════════
# SECTION 4: EXPECTED EVIDENCE
# ═══════════════════════════════════════════════════════════


class TestExpectedEvidence:

    def _expectation(self, required=True, queryable=True):
        return ExpectedEvidence(
            expectation_id="EXP-1",
            evidence_class=EvidenceClass.THIRD_PARTY_ADMIN,
            description="municipal construction permit",
            required=required,
            queryable_in_jurisdiction=queryable,
        )

    def test_required_and_queryable_absence_is_meaningful(self):
        assert self._expectation(True, True).absence_is_meaningful is True

    def test_unqueryable_absence_is_never_meaningful(self):
        """The poor-country guard at the expectation level: a source that does
        not exist locally cannot produce a finding by failing to answer."""
        assert self._expectation(True, False).absence_is_meaningful is False

    def test_optional_absence_is_not_meaningful(self):
        assert self._expectation(False, True).absence_is_meaningful is False

    def test_defaults_are_required_and_queryable(self):
        e = ExpectedEvidence(
            expectation_id="EXP-2",
            evidence_class=EvidenceClass.GEOSPATIAL,
            description="satellite change detection",
        )
        assert e.required is True
        assert e.queryable_in_jurisdiction is True


# ═══════════════════════════════════════════════════════════
# SECTION 5: SOURCE INDEPENDENCE
# ═══════════════════════════════════════════════════════════


class TestSourceIndependence:

    def test_contract_party_cannot_corroborate_independently(self):
        s = SourceIndependence(
            party_id="P1",
            party_name="Implementing Partner Ltd",
            party_type="implementing_partner",
            is_contract_party=True,
        )
        assert s.can_corroborate_independently is False

    def test_non_contract_party_can_corroborate(self):
        s = SourceIndependence(
            party_id="P2",
            party_name="State Nursing Council",
            party_type="government_agency",
        )
        assert s.can_corroborate_independently is True

    def test_linked_parties_defaults_empty(self):
        s = SourceIndependence(party_id="P3", party_name="X", party_type="civil_society")
        assert s.linked_parties == []


# ═══════════════════════════════════════════════════════════
# SECTION 6: THE DOSSIER
# ═══════════════════════════════════════════════════════════


class TestCorroborationDossier:

    def test_claim_is_required(self):
        """A dossier with nothing to corroborate should not be constructible."""
        with pytest.raises(TypeError):
            CorroborationDossier()

    def test_dossier_id_autogenerated_and_unique(self, claim):
        a = CorroborationDossier(claim=claim)
        b = CorroborationDossier(claim=claim)
        assert a.dossier_id and b.dossier_id
        assert a.dossier_id != b.dossier_id

    def test_verdict_starts_none(self, claim):
        """No verdict until the gate has actually run. Absence of a verdict is
        not a clean bill of health."""
        assert CorroborationDossier(claim=claim).verdict is None

    def test_classes_present(self, claim):
        d = CorroborationDossier(claim=claim, artifacts=[
            _artifact(EvidenceStatus.OBSERVED, EvidenceClass.INSTITUTIONAL, "A1"),
            _artifact(EvidenceStatus.OBSERVED, EvidenceClass.GEOSPATIAL, "A2"),
            _artifact(EvidenceStatus.ABSENT, EvidenceClass.GEOSPATIAL, "A3"),
        ])
        assert d.classes_present == {
            EvidenceClass.INSTITUTIONAL,
            EvidenceClass.GEOSPATIAL,
        }

    def test_artifacts_in_class(self, claim):
        d = CorroborationDossier(claim=claim, artifacts=[
            _artifact(EvidenceStatus.OBSERVED, EvidenceClass.GEOSPATIAL, "A1"),
            _artifact(EvidenceStatus.ABSENT, EvidenceClass.GEOSPATIAL, "A2"),
            _artifact(EvidenceStatus.OBSERVED, EvidenceClass.INSTITUTIONAL, "A3"),
        ])
        found = d.artifacts_in_class(EvidenceClass.GEOSPATIAL)
        assert [a.artifact_id for a in found] == ["A1", "A2"]

    def test_source_lookup(self, claim):
        s = SourceIndependence(party_id="P1", party_name="Ministry", party_type="government_agency")
        d = CorroborationDossier(claim=claim, source_registry=[s])
        assert d.source("P1") is s
        assert d.source("NOPE") is None

    def test_disclaimer_is_structural_not_accusatory(self, claim):
        """Findings are structural, never accusatory. The disclaimer that ships
        with every dossier must say so in those terms."""
        text = CorroborationDossier(claim=claim).disclaimer.lower()
        assert "not an allegation" in text
        assert "does not assert" in text

    def test_dossier_does_not_carry_side_1_to_4_state(self, claim):
        """Purely additive: Side 5 reads other sides through the claim's link
        fields and holds no writable handle on their objects."""
        d = CorroborationDossier(claim=claim)
        for forbidden in ("delivery_dossier", "recovery_record", "contract_dossier"):
            assert not hasattr(d, forbidden)


class TestOutcomeClaim:

    def test_site_coordinates_detected(self, claim):
        assert claim.has_site_coordinates is True

    def test_missing_site_coordinates(self):
        c = OutcomeClaim(
            claim_id="C2",
            contract_id="K2",
            outcome_type=OutcomeType.CASH_TRANSFER,
            claim_description="30,000 households receiving transfers",
        )
        assert c.has_site_coordinates is False

    def test_partial_coordinates_are_not_coordinates(self):
        """Latitude alone locates nothing."""
        c = OutcomeClaim(
            claim_id="C3",
            contract_id="K3",
            outcome_type=OutcomeType.FACILITY_CONSTRUCTION,
            claim_description="clinic",
            site_latitude=9.0,
        )
        assert c.has_site_coordinates is False

    def test_links_to_other_sides_default_none(self, claim):
        assert claim.source_dossier_id is None
        assert claim.source_recovery_id is None


class TestProvenanceGeotagFlag:

    def _prov(self, lat=None, lon=None):
        return Provenance(
            source_id="S1",
            source_name="Monitor",
            retrieval_timestamp=datetime.now(timezone.utc),
            content_hash="deadbeef",
            capture_latitude=lat,
            capture_longitude=lon,
        )

    def test_has_geotag_true_with_both(self):
        assert self._prov(9.0, 7.0).has_geotag is True

    def test_has_geotag_false_with_neither(self):
        assert self._prov().has_geotag is False

    @pytest.mark.parametrize("lat,lon", [(9.0, None), (None, 7.0)])
    def test_has_geotag_false_with_one(self, lat, lon):
        assert self._prov(lat, lon).has_geotag is False

    def test_zero_coordinates_still_count_as_a_geotag(self):
        """Null Island is a real coordinate. `if not lat` would drop it, and a
        truthiness bug here would silently discard evidence."""
        assert self._prov(0.0, 0.0).has_geotag is True
