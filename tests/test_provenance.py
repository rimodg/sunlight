"""
Tests for SUNLIGHT Side 5 — Provenance and Chain of Custody.

Covers spec tests 1-5 plus the surrounding contract:

    Hashing (spec 1, 2):
        - compute_hash is deterministic and matches hashlib
        - Tampered content fails verification
        - Weak algorithms (md5, sha1) are refused, not silently accepted
        - Non-bytes content is refused with a clear message

    Ingestion gate (spec 3):
        - Artifact without provenance is rejected
        - Blank source_id, source_name, content_hash rejected
        - Missing retrieval_timestamp rejected
        - Unsupported algorithm rejected
        - Absence records still require provenance — of the query

    Geotag (spec 4, 5):
        - Capture location within tolerance passes
        - Capture location outside tolerance fails (photo of the wrong building)
        - Missing geotag is distinguishable from a wrong geotag, which is the
          difference between an absence and a contradiction

    Haversine:
        - Zero distance, known reference distance, symmetry, antimeridian
"""

import hashlib
import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_schema import (
    EvidenceArtifact,
    EvidenceClass,
    EvidenceStatus,
    OutcomeClaim,
    OutcomeType,
    Provenance,
)
from provenance import (
    DEFAULT_HASH_ALGORITHM,
    SUPPORTED_HASH_ALGORITHMS,
    ProvenanceError,
    compute_hash,
    create_provenance,
    geotag_distance_meters,
    haversine_meters,
    is_ingestible,
    records_negative_result,
    rejection_reason,
    validate_for_ingestion,
    validate_geotag,
    verify_artifact_integrity,
)


CONTENT = b"municipal construction permit no. 44182, issued 2024-06-11"
TAMPERED = b"municipal construction permit no. 44182, issued 2023-01-02"

# Abuja and Lagos, roughly. Used as a "definitely a different site" pair.
ABUJA = (9.0765, 7.3986)
LAGOS = (6.5244, 3.3792)


# ═══════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def claim():
    return OutcomeClaim(
        claim_id="CLAIM-001",
        contract_id="CONTRACT-001",
        outcome_type=OutcomeType.FACILITY_CONSTRUCTION,
        claim_description="200-bed hospital operational",
        site_latitude=ABUJA[0],
        site_longitude=ABUJA[1],
        country_code="ng",
    )


@pytest.fixture
def good_provenance():
    return create_provenance(
        source_id="ng-fct-permits",
        source_name="FCT Development Control Department",
        content=CONTENT,
        source_url="https://example.invalid/permits/44182",
    )


def _artifact(provenance, status=EvidenceStatus.OBSERVED, aid="ART-1"):
    return EvidenceArtifact(
        artifact_id=aid,
        evidence_class=EvidenceClass.THIRD_PARTY_ADMIN,
        claim_id="CLAIM-001",
        description="municipal construction permit",
        status=status,
        observed_date=date(2024, 6, 11),
        provenance=provenance,
    )


# ═══════════════════════════════════════════════════════════
# SECTION 1: HASHING  (spec tests 1 and 2)
# ═══════════════════════════════════════════════════════════


class TestComputeHash:

    def test_matches_hashlib(self):
        """Spec test 1 — the digest is the real thing, not our own scheme."""
        assert compute_hash(CONTENT) == hashlib.sha256(CONTENT).hexdigest()

    def test_deterministic(self):
        assert compute_hash(CONTENT) == compute_hash(CONTENT)

    def test_different_content_different_hash(self):
        assert compute_hash(CONTENT) != compute_hash(TAMPERED)

    def test_default_algorithm_is_sha256(self):
        assert DEFAULT_HASH_ALGORITHM == "sha256"

    @pytest.mark.parametrize("algorithm", sorted(SUPPORTED_HASH_ALGORITHMS))
    def test_every_supported_algorithm_works(self, algorithm):
        digest = compute_hash(CONTENT, algorithm=algorithm)
        assert digest == hashlib.new(algorithm, CONTENT).hexdigest()

    @pytest.mark.parametrize("weak", ["md5", "sha1"])
    def test_collision_capable_algorithms_refused(self, weak):
        """A collision-capable digest cannot support a tamper-detection claim
        in front of an auditor. Refuse loudly rather than accept quietly."""
        assert weak not in SUPPORTED_HASH_ALGORITHMS
        with pytest.raises(ProvenanceError, match="Unsupported hash algorithm"):
            compute_hash(CONTENT, algorithm=weak)

    def test_unknown_algorithm_refused(self):
        with pytest.raises(ProvenanceError):
            compute_hash(CONTENT, algorithm="not-a-real-digest")

    def test_str_content_refused(self):
        """Encoding must be explicit and part of the record."""
        with pytest.raises(ProvenanceError, match="must be bytes"):
            compute_hash("a string", algorithm="sha256")

    def test_empty_content_hashes(self):
        """A negative result hashes its empty response body — that digest is
        what makes 'we asked and got nothing' re-verifiable."""
        assert compute_hash(b"") == hashlib.sha256(b"").hexdigest()


class TestCreateProvenance:

    def test_hashes_content(self, good_provenance):
        assert good_provenance.content_hash == hashlib.sha256(CONTENT).hexdigest()

    def test_records_source(self, good_provenance):
        assert good_provenance.source_id == "ng-fct-permits"
        assert good_provenance.source_name == "FCT Development Control Department"

    def test_retrieval_timestamp_is_timezone_aware(self, good_provenance):
        assert good_provenance.retrieval_timestamp.tzinfo is not None

    def test_explicit_retrieval_timestamp_preserved(self):
        """Back-filled evidence records when it was retrieved, not when it was
        loaded into SUNLIGHT."""
        when = datetime(2024, 6, 12, 9, 30, tzinfo=timezone.utc)
        p = create_provenance("s", "S", CONTENT, retrieval_timestamp=when)
        assert p.retrieval_timestamp == when

    def test_blank_source_id_refused(self):
        with pytest.raises(ProvenanceError, match="source_id"):
            create_provenance("   ", "Some Source", CONTENT)

    def test_blank_source_name_refused(self):
        with pytest.raises(ProvenanceError, match="source_name"):
            create_provenance("s1", "", CONTENT)

    def test_geotag_fields_carried(self):
        p = create_provenance(
            "monitor-7", "Independent Monitor 7", CONTENT,
            capture_lat=ABUJA[0], capture_lon=ABUJA[1],
            capture_timestamp=datetime(2025, 4, 2, tzinfo=timezone.utc),
        )
        assert p.has_geotag is True
        assert p.capture_timestamp.year == 2025


class TestIntegrityVerification:

    def test_intact_content_verifies(self, good_provenance):
        assert good_provenance.verify_hash(CONTENT) is True

    def test_tampered_content_fails(self, good_provenance):
        """Spec test 2 — modification after ingestion is detectable."""
        assert good_provenance.verify_hash(TAMPERED) is False

    def test_single_byte_change_fails(self, good_provenance):
        assert good_provenance.verify_hash(CONTENT + b" ") is False

    def test_artifact_integrity_intact(self, good_provenance):
        assert verify_artifact_integrity(_artifact(good_provenance), CONTENT) is True

    def test_artifact_integrity_tampered(self, good_provenance):
        assert verify_artifact_integrity(_artifact(good_provenance), TAMPERED) is False

    def test_artifact_without_provenance_fails_integrity(self):
        """Returns False rather than raising: an integrity failure is a finding
        for EVD-SRC-002 to report, not an exception to unwind the pipeline."""
        assert verify_artifact_integrity(_artifact(None), CONTENT) is False

    def test_corrupt_algorithm_fails_closed(self):
        """A provenance record with a nonsense algorithm must fail verification,
        not raise and not pass."""
        p = Provenance(
            source_id="s", source_name="S",
            retrieval_timestamp=datetime.now(timezone.utc),
            content_hash="whatever", hash_algorithm="not-a-digest",
        )
        assert p.verify_hash(CONTENT) is False

    def test_empty_recorded_hash_does_not_match_empty_recompute(self):
        """Guard against a blank-vs-blank comparison passing by accident."""
        p = Provenance(
            source_id="s", source_name="S",
            retrieval_timestamp=datetime.now(timezone.utc),
            content_hash="",
        )
        assert p.verify_hash(b"") is False


# ═══════════════════════════════════════════════════════════
# SECTION 2: THE INGESTION GATE  (spec test 3)
# ═══════════════════════════════════════════════════════════


class TestIngestionGate:

    def test_valid_artifact_admitted(self, good_provenance):
        validate_for_ingestion(_artifact(good_provenance))   # does not raise
        assert is_ingestible(_artifact(good_provenance)) is True
        assert rejection_reason(_artifact(good_provenance)) is None

    def test_artifact_without_provenance_rejected(self):
        """Spec test 3 — rejected at ingestion, not silently accepted."""
        with pytest.raises(ProvenanceError, match="no provenance"):
            validate_for_ingestion(_artifact(None))

    def test_rejection_names_the_artifact(self):
        """A rejected batch must be reportable precisely, not as a count."""
        with pytest.raises(ProvenanceError) as exc:
            validate_for_ingestion(_artifact(None, aid="ART-99"))
        assert "ART-99" in str(exc.value)
        assert exc.value.artifact_id == "ART-99"

    def test_is_ingestible_false_without_provenance(self):
        assert is_ingestible(_artifact(None)) is False

    def test_rejection_reason_explains(self):
        reason = rejection_reason(_artifact(None))
        assert reason is not None
        assert "provenance" in reason.lower()

    def _prov(self, **overrides):
        base = dict(
            source_id="s1",
            source_name="Source One",
            retrieval_timestamp=datetime.now(timezone.utc),
            content_hash="abc123",
        )
        base.update(overrides)
        return Provenance(**base)

    def test_blank_source_id_rejected(self):
        with pytest.raises(ProvenanceError, match="source_id"):
            validate_for_ingestion(_artifact(self._prov(source_id="  ")))

    def test_blank_source_name_rejected(self):
        with pytest.raises(ProvenanceError, match="source_name"):
            validate_for_ingestion(_artifact(self._prov(source_name="")))

    def test_blank_content_hash_rejected(self):
        with pytest.raises(ProvenanceError, match="content_hash"):
            validate_for_ingestion(_artifact(self._prov(content_hash="")))

    def test_missing_retrieval_timestamp_rejected(self):
        with pytest.raises(ProvenanceError, match="retrieval_timestamp"):
            validate_for_ingestion(_artifact(self._prov(retrieval_timestamp=None)))

    def test_string_retrieval_timestamp_rejected(self):
        """An ISO string is not a point in time until it is parsed."""
        with pytest.raises(ProvenanceError, match="retrieval_timestamp"):
            validate_for_ingestion(_artifact(self._prov(retrieval_timestamp="2024-06-11")))

    def test_unsupported_algorithm_rejected(self):
        with pytest.raises(ProvenanceError, match="unsupported hash algorithm"):
            validate_for_ingestion(_artifact(self._prov(hash_algorithm="md5")))

    @pytest.mark.parametrize("status", [EvidenceStatus.ABSENT, EvidenceStatus.UNQUERYABLE])
    def test_absence_records_still_require_provenance(self, status):
        """The negative-result principle.

        An absence with no record of who was asked and when is an assumption,
        not evidence. Since absence is what drives Layer 2 findings, accepting
        unsourced absences would let anyone manufacture a contradiction by
        submitting empty records.
        """
        with pytest.raises(ProvenanceError):
            validate_for_ingestion(_artifact(None, status=status))

    @pytest.mark.parametrize("status", [EvidenceStatus.ABSENT, EvidenceStatus.UNQUERYABLE])
    def test_absence_with_query_provenance_admitted(self, good_provenance, status):
        """Properly sourced absence IS admissible — that is the whole point."""
        validate_for_ingestion(_artifact(good_provenance, status=status))

    @pytest.mark.parametrize("status,expected", [
        (EvidenceStatus.ABSENT, True),
        (EvidenceStatus.UNQUERYABLE, True),
        (EvidenceStatus.OBSERVED, False),
        (EvidenceStatus.CONTRADICTORY, False),
        (EvidenceStatus.STALE, False),
    ])
    def test_records_negative_result(self, good_provenance, status, expected):
        assert records_negative_result(_artifact(good_provenance, status=status)) is expected


# ═══════════════════════════════════════════════════════════
# SECTION 3: HAVERSINE
# ═══════════════════════════════════════════════════════════


class TestHaversine:

    def test_zero_distance(self):
        assert haversine_meters(*ABUJA, *ABUJA) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_abuja_to_lagos(self):
        """Roughly 525 km great-circle. Generous bound — this checks the formula
        is right, not that the cities moved."""
        d = haversine_meters(*ABUJA, *LAGOS)
        assert 500_000 < d < 550_000

    def test_symmetric(self):
        assert haversine_meters(*ABUJA, *LAGOS) == pytest.approx(
            haversine_meters(*LAGOS, *ABUJA)
        )

    def test_one_degree_latitude_is_about_111km(self):
        d = haversine_meters(0.0, 0.0, 1.0, 0.0)
        assert 110_000 < d < 112_000

    def test_short_distance_precision(self):
        """250 m is the default geotag tolerance, so the formula has to be
        trustworthy at that scale, not just at continental scale."""
        # ~0.001 degrees latitude ≈ 111 m
        d = haversine_meters(9.0000, 7.0000, 9.0010, 7.0000)
        assert 108 < d < 114

    def test_antimeridian_does_not_blow_up(self):
        """Two points either side of the date line are close, not 40,000 km apart."""
        d = haversine_meters(0.0, 179.999, 0.0, -179.999)
        assert d < 1000


# ═══════════════════════════════════════════════════════════
# SECTION 4: GEOTAG VALIDATION  (spec tests 4 and 5)
# ═══════════════════════════════════════════════════════════


class TestGeotagValidation:

    def _geotagged(self, lat, lon):
        return create_provenance(
            "monitor-7", "Independent Monitor 7", CONTENT,
            capture_lat=lat, capture_lon=lon,
        )

    def test_within_tolerance_passes(self, claim):
        """Spec test 4 — a photo taken at the site it documents."""
        p = self._geotagged(ABUJA[0], ABUJA[1])
        assert validate_geotag(p, claim, tolerance_meters=250.0) is True

    def test_just_inside_tolerance_passes(self, claim):
        # ~111 m north of the site
        p = self._geotagged(ABUJA[0] + 0.001, ABUJA[1])
        assert validate_geotag(p, claim, tolerance_meters=250.0) is True

    def test_outside_tolerance_fails(self, claim):
        """Spec test 5 — a photograph of the wrong building."""
        p = self._geotagged(LAGOS[0], LAGOS[1])
        assert validate_geotag(p, claim, tolerance_meters=250.0) is False

    def test_just_outside_tolerance_fails(self, claim):
        # ~555 m north of the site
        p = self._geotagged(ABUJA[0] + 0.005, ABUJA[1])
        assert validate_geotag(p, claim, tolerance_meters=250.0) is False

    def test_tolerance_is_honoured_not_hardcoded(self, claim):
        """The same photo passes at a wide tolerance and fails at a tight one —
        the threshold comes from the jurisdiction profile, not from this module."""
        p = self._geotagged(ABUJA[0] + 0.005, ABUJA[1])
        assert validate_geotag(p, claim, tolerance_meters=1000.0) is True
        assert validate_geotag(p, claim, tolerance_meters=100.0) is False


class TestGeotagAbsenceIsNotContradiction:
    """THE DISTINCTION THAT MATTERS.

    A missing geotag and a geotag four kilometres away are different findings.
    Only the second is a contradiction; the first is an absence, which Layer 2
    handles after checking queryability. geotag_distance_meters returns None
    for the unassessable case precisely so the rule layer can tell them apart,
    and these tests pin that contract before any rule depends on it.
    """

    def test_no_geotag_yields_none_distance(self, claim, good_provenance):
        assert good_provenance.has_geotag is False
        assert geotag_distance_meters(good_provenance, claim) is None

    def test_no_site_coordinates_yields_none_distance(self):
        p = create_provenance("m", "M", CONTENT, capture_lat=9.0, capture_lon=7.0)
        claim_without_site = OutcomeClaim(
            claim_id="C9",
            contract_id="K9",
            outcome_type=OutcomeType.CASH_TRANSFER,
            claim_description="cash transfers to 30,000 households",
        )
        assert geotag_distance_meters(p, claim_without_site) is None

    def test_wrong_location_yields_a_real_distance(self, claim):
        p = create_provenance("m", "M", CONTENT, capture_lat=LAGOS[0], capture_lon=LAGOS[1])
        d = geotag_distance_meters(p, claim)
        assert d is not None
        assert d > 500_000

    def test_both_cases_return_false_from_validate_geotag(self, claim, good_provenance):
        """validate_geotag alone cannot distinguish them — which is exactly why
        the rule layer must use geotag_distance_meters instead."""
        no_geotag = validate_geotag(good_provenance, claim, tolerance_meters=250.0)
        wrong_place = validate_geotag(
            create_provenance("m", "M", CONTENT, capture_lat=LAGOS[0], capture_lon=LAGOS[1]),
            claim, tolerance_meters=250.0,
        )
        assert no_geotag is False
        assert wrong_place is False
        # ...and the distances are what tell them apart:
        assert geotag_distance_meters(good_provenance, claim) is None
        assert geotag_distance_meters(
            create_provenance("m", "M", CONTENT, capture_lat=LAGOS[0], capture_lon=LAGOS[1]),
            claim,
        ) is not None
