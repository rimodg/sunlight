"""
SUNLIGHT Side 5 — Provenance and Chain of Custody
====================================================

Hashing, integrity verification, geotag validation, and the ingestion gate.

Why this module exists:
    A corroboration finding is only as good as the evidence chain behind it.
    "Six evidence classes queried, five returned contradictions" is a serious
    statement to put in front of an institution, and it is worth nothing
    unless every element is independently checkable: sourced, hashed,
    timestamped, and re-verifiable by someone who does not trust us.

    So Side 5 refuses evidence it cannot vouch for. Artifacts without valid
    provenance are rejected at Stage 13, not silently accepted and quietly
    counted. An audit tool that accepts unsourced evidence is producing
    opinion with extra steps.

The negative-result principle:
    Provenance is required on artifacts recording ABSENCE, not just on
    artifacts recording content. For an absence the provenance attests to the
    query — which registry was asked, when, and the digest of the empty
    response — rather than to a document.

    This is the difference between "no construction permit was found" as a
    finding and as an assumption. Side 5 only accepts the first.

Determinism:
    No ML, no scoring model, no classifier. compute_hash is a pure function
    of its bytes; haversine is a pure function of four floats. Same input,
    same output, forever.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Optional

from evidence_schema import (
    EvidenceArtifact,
    EvidenceStatus,
    OutcomeClaim,
    Provenance,
)


# ═══════════════════════════════════════════════════════════
# SECTION 1: ERRORS
# ═══════════════════════════════════════════════════════════


class ProvenanceError(Exception):
    """Raised when evidence cannot be admitted to the corroboration graph.

    Carries the artifact id where one is known, so a rejected batch can be
    reported back to the submitting institution precisely rather than as a
    generic ingestion failure.
    """

    def __init__(self, message: str, artifact_id: Optional[str] = None):
        self.artifact_id = artifact_id
        if artifact_id:
            message = f"{message} (artifact_id={artifact_id})"
        super().__init__(message)


# ═══════════════════════════════════════════════════════════
# SECTION 2: HASHING
# ═══════════════════════════════════════════════════════════

# Algorithms accepted for content hashing. Deliberately restrictive:
# md5 and sha1 are excluded because a collision-capable digest cannot
# support a tamper-detection claim in front of an auditor. Adding an
# algorithm here is a deliberate act, not an accident of configuration.
SUPPORTED_HASH_ALGORITHMS = frozenset({"sha256", "sha384", "sha512", "sha3_256", "sha3_512"})

DEFAULT_HASH_ALGORITHM = "sha256"


def compute_hash(content: bytes, algorithm: str = DEFAULT_HASH_ALGORITHM) -> str:
    """Compute the hex digest of artifact content.

    Args:
        content: raw artifact bytes. For a negative result (ABSENT or
                 UNQUERYABLE) this is the empty or literal response body
                 returned by the source that was queried.
        algorithm: digest algorithm. Must be in SUPPORTED_HASH_ALGORITHMS.

    Returns:
        Lowercase hex digest.

    Raises:
        ProvenanceError: on an unsupported algorithm or non-bytes content.
    """
    if algorithm not in SUPPORTED_HASH_ALGORITHMS:
        raise ProvenanceError(
            f"Unsupported hash algorithm '{algorithm}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_HASH_ALGORITHMS))}"
        )
    if not isinstance(content, (bytes, bytearray)):
        raise ProvenanceError(
            f"Content must be bytes to be hashed, got {type(content).__name__}. "
            "Encode text explicitly so the encoding is part of the record."
        )
    return hashlib.new(algorithm, bytes(content)).hexdigest()


def create_provenance(
    source_id: str,
    source_name: str,
    content: bytes,
    source_url: Optional[str] = None,
    capture_timestamp: Optional[datetime] = None,
    capture_lat: Optional[float] = None,
    capture_lon: Optional[float] = None,
    algorithm: str = DEFAULT_HASH_ALGORITHM,
    retrieval_timestamp: Optional[datetime] = None,
) -> Provenance:
    """Build a Provenance record, hashing the content as it goes.

    retrieval_timestamp defaults to now in UTC. It is exposed as a parameter
    so that back-filled evidence can record when it was actually retrieved
    rather than when it happened to be loaded into SUNLIGHT.

    Raises:
        ProvenanceError: if source_id or source_name is blank, or hashing fails.
    """
    if not source_id or not source_id.strip():
        raise ProvenanceError("Provenance requires a non-empty source_id")
    if not source_name or not source_name.strip():
        raise ProvenanceError("Provenance requires a non-empty source_name")

    content_hash = compute_hash(content, algorithm=algorithm)

    return Provenance(
        source_id=source_id,
        source_name=source_name,
        retrieval_timestamp=retrieval_timestamp or datetime.now(timezone.utc),
        content_hash=content_hash,
        source_url=source_url,
        capture_timestamp=capture_timestamp,
        capture_latitude=capture_lat,
        capture_longitude=capture_lon,
        hash_algorithm=algorithm,
    )


def verify_artifact_integrity(artifact: EvidenceArtifact, content: bytes) -> bool:
    """Check an artifact's recorded hash against content presented now.

    Returns False if the artifact carries no provenance, if the algorithm is
    unsupported, or if the digest does not match — that is, False means
    "this artifact cannot be vouched for", which is precisely the condition
    EVD-SRC-002 (chain of custody break) reports.

    Does not raise: integrity failure is a finding to be recorded, not an
    exception to be handled. Ingestion is where refusal happens; this is
    where re-verification happens, and a re-verification that throws would
    lose the finding.
    """
    if artifact.provenance is None:
        return False
    return artifact.provenance.verify_hash(content)


# ═══════════════════════════════════════════════════════════
# SECTION 3: GEOSPATIAL VALIDATION
# ═══════════════════════════════════════════════════════════

# Mean Earth radius in metres (IUGG). Haversine on a sphere is accurate to
# roughly 0.5% — far inside any tolerance a site-identity check would use,
# where the question is "same site or a different one", measured in hundreds
# of metres, not centimetres.
EARTH_RADIUS_M = 6_371_008.8


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in metres."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    # asin form is numerically better than atan2 for the near-zero distances
    # that dominate here — a monitor photo taken at the site it documents.
    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def geotag_distance_meters(
    provenance: Provenance,
    claim: OutcomeClaim,
) -> Optional[float]:
    """Distance from a photograph's capture point to the claimed site.

    Returns None when the distance cannot be computed — either the photograph
    carries no geotag or the claim names no site coordinates.

    Callers MUST distinguish None from a large number. "No geotag present" is
    an absence, handled by the Layer 2 rules after a queryability check.
    "Geotag four kilometres from the site" is a contradiction, handled by
    Layer 3. Treating the first as the second would manufacture findings out
    of missing camera metadata.
    """
    if not provenance.has_geotag:
        return None
    if not claim.has_site_coordinates:
        return None
    return haversine_meters(
        provenance.capture_latitude,
        provenance.capture_longitude,
        claim.site_latitude,
        claim.site_longitude,
    )


def validate_geotag(
    provenance: Provenance,
    claim: OutcomeClaim,
    tolerance_meters: float,
) -> bool:
    """Does a field-verification photograph's capture location match the claimed site?

    A photograph of the wrong building is a contradiction, and it is one of
    the few contradictions available to Side 5 that is genuinely hard to
    manufacture: the capture coordinates are written by the camera.

    Returns False both when the geotag is out of tolerance and when it cannot
    be assessed at all. Use geotag_distance_meters() and check for None when
    those two cases must be told apart — which, in the rule layer, they must.
    """
    distance = geotag_distance_meters(provenance, claim)
    if distance is None:
        return False
    return distance <= tolerance_meters


# ═══════════════════════════════════════════════════════════
# SECTION 4: THE INGESTION GATE (Stage 13)
# ═══════════════════════════════════════════════════════════

# Statuses that record a negative result. These still require provenance —
# attesting to the query rather than to content — but they are exempt from
# nothing else. See the module docstring.
NEGATIVE_RESULT_STATUSES = frozenset({
    EvidenceStatus.ABSENT,
    EvidenceStatus.UNQUERYABLE,
})


def records_negative_result(artifact: EvidenceArtifact) -> bool:
    """True when this artifact documents an absence rather than a document.

    The rule layers need this distinction constantly, because a negative
    result is only meaningful once its queryability has been established:
    ABSENT is a finding, UNQUERYABLE is a limit on SUNLIGHT's reach, and
    the two must not be summed.
    """
    return artifact.status in NEGATIVE_RESULT_STATUSES


def validate_for_ingestion(artifact: EvidenceArtifact) -> None:
    """Gate a single artifact at Stage 13. Raise if it cannot be admitted.

    Rejects, in order:
        - no provenance at all
        - blank source_id or source_name — an unattributable source
        - blank content_hash — nothing to re-verify against later
        - missing or non-datetime retrieval_timestamp
        - an unsupported hash algorithm

    Raises:
        ProvenanceError: with the artifact id attached.
    """
    aid = getattr(artifact, "artifact_id", None)

    prov = artifact.provenance
    if prov is None:
        raise ProvenanceError(
            "Artifact has no provenance and cannot enter the corroboration graph. "
            "Evidence recording an absence requires provenance of the query.",
            artifact_id=aid,
        )

    if not prov.source_id or not str(prov.source_id).strip():
        raise ProvenanceError("Provenance has no source_id", artifact_id=aid)

    if not prov.source_name or not str(prov.source_name).strip():
        raise ProvenanceError("Provenance has no source_name", artifact_id=aid)

    if not prov.content_hash or not str(prov.content_hash).strip():
        raise ProvenanceError(
            "Provenance has no content_hash — the artifact could not be "
            "re-verified after ingestion",
            artifact_id=aid,
        )

    if not isinstance(prov.retrieval_timestamp, datetime):
        raise ProvenanceError(
            "Provenance has no valid retrieval_timestamp — the evidence "
            "cannot be placed in time",
            artifact_id=aid,
        )

    if prov.hash_algorithm not in SUPPORTED_HASH_ALGORITHMS:
        raise ProvenanceError(
            f"Provenance uses unsupported hash algorithm '{prov.hash_algorithm}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_HASH_ALGORITHMS))}",
            artifact_id=aid,
        )


def is_ingestible(artifact: EvidenceArtifact) -> bool:
    """Non-raising form of validate_for_ingestion, for filtering and reporting."""
    try:
        validate_for_ingestion(artifact)
        return True
    except ProvenanceError:
        return False


def rejection_reason(artifact: EvidenceArtifact) -> Optional[str]:
    """Why an artifact would be rejected, or None if it would be admitted.

    Exists so that Stage 13 can tell a submitting institution exactly what is
    wrong with a rejected artifact instead of returning an opaque count.
    """
    try:
        validate_for_ingestion(artifact)
        return None
    except ProvenanceError as e:
        return str(e)
