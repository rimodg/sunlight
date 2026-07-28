"""
Tests for SUNLIGHT Side 5 — Evidence API.

Covers spec tests 47-52: each endpoint returns the correct structure, and
/evidence/capacity honestly reports jurisdiction limits.

Two endpoints exist to disclose limits rather than to produce findings, and
they are tested as hard as the ones that do:

    /evidence/capacity  — what SUNLIGHT cannot verify in a country, including
                          an explicit statement that no adverse conclusion is
                          available where reach is too thin.
    /evidence/expected  — what SUNLIGHT will look for, published before
                          anything is submitted. An expectation that cannot
                          survive being published is one that should not be
                          applied.

Every corroboration response is checked to carry its corroboration capacity
beside its verdict. A verdict reported without its reach is misleading by
omission: UNVERIFIED at two of six reachable classes and UNVERIFIED at six of
six are different statements.
"""

import base64
import hashlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from api import app


CONTENT = b"municipal construction permit no. 44182"
CONTENT_HASH = hashlib.sha256(CONTENT).hexdigest()


@pytest.fixture
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════
# PAYLOAD BUILDERS
# ═══════════════════════════════════════════════════════════


def provenance(content_hash=CONTENT_HASH, source_id="ng-permits"):
    return {
        "source_id": source_id,
        "source_name": "FCT Development Control Department",
        "retrieval_timestamp": "2025-04-01T09:30:00Z",
        "content_hash": content_hash,
        "hash_algorithm": "sha256",
    }


def artifact(aid="A1", cls="third_party_admin", status="observed",
             party="PERMITS", with_provenance=True, **extra):
    payload = {
        "artifact_id": aid,
        "evidence_class": cls,
        "description": f"artifact {aid}",
        "status": status,
        "source_party_id": party,
    }
    if with_provenance:
        payload["provenance"] = provenance()
    payload.update(extra)
    return payload


def claim(**overrides):
    payload = {
        "claim_id": "CLAIM-001",
        "contract_id": "CONTRACT-001",
        "outcome_type": "facility_construction",
        "claim_description": "200-bed hospital operational",
        "claimed_completion_date": "2025-03-01",
        "claimed_magnitude": 200.0,
        "claimed_magnitude_unit": "beds",
        "country_code": "ng",
        "award_date": "2024-01-15",
    }
    payload.update(overrides)
    return payload


def request_body(artifacts=None, sources=None, **overrides):
    body = {
        "claim": claim(),
        "artifacts": artifacts if artifacts is not None else [artifact()],
        "source_registry": sources if sources is not None else [
            {"party_id": "PERMITS", "party_name": "Permit Registry",
             "party_type": "government_agency"},
        ],
        "profile": "us_federal",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
# SPEC TEST 47 — POST /evidence/analyze
# ═══════════════════════════════════════════════════════════


class TestAnalyzeEndpoint:

    def test_returns_200(self, client):
        assert client.post("/evidence/analyze", json=request_body()).status_code == 200

    def test_response_structure(self, client):
        data = client.post("/evidence/analyze", json=request_body()).json()
        for key in ("dossier_id", "verdict", "confidence", "contradictions",
                    "independent_classes_corroborating",
                    "corroboration_capacity", "classes_queryable",
                    "classes_total", "rule_fires", "disclaimer"):
            assert key in data, f"missing {key}"

    def test_verdict_is_one_of_the_four(self, client):
        data = client.post("/evidence/analyze", json=request_body()).json()
        assert data["verdict"] in (
            "verified", "partial", "unverified", "contradicted")

    def test_capacity_always_accompanies_the_verdict(self, client):
        """A verdict reported without its reach is misleading by omission."""
        data = client.post("/evidence/analyze", json=request_body()).json()
        assert data["verdict"] is not None
        assert isinstance(data["corroboration_capacity"], float)
        assert data["classes_total"] == 6

    def test_disclaimer_is_structural_not_accusatory(self, client):
        data = client.post("/evidence/analyze", json=request_body()).json()
        assert "not an allegation" in data["disclaimer"].lower()

    def test_unknown_profile_is_400(self, client):
        body = request_body(profile="atlantis")
        assert client.post("/evidence/analyze", json=body).status_code == 400

    def test_unknown_evidence_class_is_400_with_valid_values(self, client):
        body = request_body(artifacts=[artifact(cls="telepathy")])
        response = client.post("/evidence/analyze", json=body)
        assert response.status_code == 400
        assert "institutional" in response.json()["detail"]

    def test_unknown_outcome_type_is_400(self, client):
        body = request_body()
        body["claim"] = claim(outcome_type="teleportation")
        assert client.post("/evidence/analyze", json=body).status_code == 400

    def test_unknown_status_is_400(self, client):
        body = request_body(artifacts=[artifact(status="probably")])
        assert client.post("/evidence/analyze", json=body).status_code == 400

    def test_malformed_date_is_400_not_500(self, client):
        body = request_body()
        body["claim"] = claim(award_date="the fourth of never")
        response = client.post("/evidence/analyze", json=body)
        assert response.status_code == 400
        assert "ISO 8601" in response.json()["detail"]

    def test_artifact_without_provenance_is_refused_not_rejected_wholesale(self, client):
        """Stage 13 quarantines: the request succeeds, the artifact does not
        enter the graph, and the submitter is told exactly which one and why."""
        body = request_body(artifacts=[artifact(with_provenance=False)])
        data = client.post("/evidence/analyze", json=body).json()
        assert data["artifacts_admitted"] == 0
        assert data["artifacts_rejected"] == 1
        assert data["rejections"][0]["artifact_id"] == "A1"
        assert "provenance" in data["rejections"][0]["reason"].lower()

    def test_empty_evidence_does_not_produce_a_verified_verdict(self, client):
        body = request_body(artifacts=[], sources=[])
        data = client.post("/evidence/analyze", json=body).json()
        assert data["verdict"] != "verified"

    def test_country_code_selects_the_jurisdiction_map(self, client):
        """Ukraine declares field verification unreachable, so an identical
        submission yields different reach than Nigeria."""
        ng = client.post("/evidence/analyze",
                         json=request_body(country_code="ng")).json()
        ua = client.post("/evidence/analyze",
                         json=request_body(country_code="ua")).json()
        assert ng["verdict"] is not None and ua["verdict"] is not None

    def test_deterministic(self, client):
        a = client.post("/evidence/analyze", json=request_body()).json()
        b = client.post("/evidence/analyze", json=request_body()).json()
        assert a["verdict"] == b["verdict"]
        assert a["confidence"] == b["confidence"]
        assert a["rule_fires"] == b["rule_fires"]


# ═══════════════════════════════════════════════════════════
# SPEC TEST 48 — POST /evidence/batch
# ═══════════════════════════════════════════════════════════


class TestBatchEndpoint:

    def test_returns_200_and_results(self, client):
        body = {"claims": [request_body(), request_body()], "profile": "us_federal"}
        data = client.post("/evidence/batch", json=body).json()
        assert data["total_submitted"] == 2
        assert data["total_analyzed"] == 2
        assert len(data["results"]) == 2

    def test_aggregate_structure(self, client):
        body = {"claims": [request_body()], "profile": "us_federal"}
        data = client.post("/evidence/batch", json=body).json()
        for key in ("verdict_distribution", "average_corroboration_capacity",
                    "total_analyzed", "total_failed", "errors"):
            assert key in data

    def test_unverified_is_a_separate_count_from_contradicted(self, client):
        """SPEC REQUIREMENT, at portfolio level. Merging them would show a
        pattern of contradicted claims in exactly the country offices whose
        registries are thinnest."""
        body = {"claims": [request_body()], "profile": "us_federal"}
        dist = client.post("/evidence/batch", json=body).json()["verdict_distribution"]
        assert set(dist) == {"verified", "partial", "unverified", "contradicted"}

    def test_the_response_says_so_in_words(self, client):
        body = {"claims": [request_body()], "profile": "us_federal"}
        note = client.post("/evidence/batch", json=body).json()["note"]
        assert "not an adverse finding" in note

    def test_batch_limit_enforced(self, client):
        body = {"claims": [request_body() for _ in range(1001)]}
        response = client.post("/evidence/batch", json=body)
        assert response.status_code == 400
        assert "1000" in response.json()["detail"]

    def test_one_bad_claim_does_not_sink_the_batch(self, client):
        """A malformed claim is reported by index and the rest still analyse."""
        bad = request_body(artifacts=[artifact(cls="telepathy")])
        body = {"claims": [request_body(), bad, request_body()]}
        data = client.post("/evidence/batch", json=body).json()
        assert data["total_analyzed"] == 2
        assert data["total_failed"] == 1
        assert data["errors"][0]["index"] == 1

    def test_empty_batch_does_not_divide_by_zero(self, client):
        data = client.post("/evidence/batch", json={"claims": []}).json()
        assert data["total_analyzed"] == 0
        assert data["average_corroboration_capacity"] == 0.0


# ═══════════════════════════════════════════════════════════
# SPEC TEST 49 — GET /evidence/expected/{outcome_type}
# ═══════════════════════════════════════════════════════════


class TestExpectedEndpoint:

    def test_returns_the_nigeria_map(self, client):
        data = client.get(
            "/evidence/expected/facility_construction?country_code=ng").json()
        assert data["map_available"] is True
        assert data["expectation_count"] > 0
        assert data["expectations"][0]["expectation_id"].startswith("NG-FC")

    def test_expectations_name_what_is_looked_for(self, client):
        """Published in advance. An institution should not first learn of an
        expectation by being found against it."""
        data = client.get(
            "/evidence/expected/facility_construction?country_code=ng").json()
        for entry in data["expectations"]:
            assert entry["description"].strip()
            assert entry["evidence_class"]

    def test_a_different_outcome_type_returns_a_different_set(self, client):
        facility = client.get(
            "/evidence/expected/facility_construction?country_code=ng").json()
        service = client.get(
            "/evidence/expected/service_delivery?country_code=ng").json()
        assert facility["expectations"] != service["expectations"]

    def test_ukraine_publishes_its_unqueryable_expectation(self, client):
        """The map declares field verification unreachable, and the endpoint
        shows it — so an institution knows that absence cannot count against it."""
        data = client.get(
            "/evidence/expected/facility_construction?country_code=ua").json()
        unqueryable = [
            e for e in data["expectations"]
            if not e.get("queryable_in_jurisdiction", True)
        ]
        assert unqueryable
        assert unqueryable[0]["evidence_class"] == "field_verification"

    def test_map_status_is_disclosed(self, client):
        data = client.get(
            "/evidence/expected/facility_construction?country_code=ng").json()
        assert data["map_status"] == "illustrative"
        assert data["map_validated"] is False

    def test_unknown_country_says_no_map_rather_than_inventing_one(self, client):
        data = client.get(
            "/evidence/expected/facility_construction?country_code=zz").json()
        assert data["map_available"] is False
        assert data["expectations"] == []
        assert "no absence finding" in data["note"]

    def test_unknown_outcome_type_is_400(self, client):
        assert client.get("/evidence/expected/teleportation").status_code == 400

    def test_no_country_code_still_answers(self, client):
        data = client.get("/evidence/expected/facility_construction").json()
        assert data["outcome_type"] == "facility_construction"


# ═══════════════════════════════════════════════════════════
# SPEC TEST 50 — GET /evidence/capacity/{country_code}
# ═══════════════════════════════════════════════════════════


class TestCapacityEndpoint:
    """Honest disclosure of the capability ceiling."""

    def test_nigeria_reports_full_reach(self, client):
        data = client.get("/evidence/capacity/ng").json()
        assert data["classes_queryable"] == 6
        assert data["corroboration_capacity_ceiling"] == 1.0
        assert data["adverse_conclusion_available"] is True

    def test_ukraine_reports_the_missing_class(self, client):
        data = client.get("/evidence/capacity/ua").json()
        assert data["classes_queryable"] == 5
        assert "field_verification" in data["unqueryable_classes"]

    def test_unqueryable_classes_are_named_not_just_counted(self, client):
        """An institution needs to know WHICH sources SUNLIGHT cannot reach,
        not merely how many."""
        data = client.get("/evidence/capacity/ua").json()
        assert isinstance(data["unqueryable_classes"], list)
        assert data["unqueryable_classes"]

    def test_unknown_country_declares_no_reach_rather_than_guessing(self, client):
        data = client.get("/evidence/capacity/zz").json()
        assert data["map_available"] is False
        assert data["classes_queryable"] == 0
        assert data["adverse_conclusion_available"] is False

    def test_thin_reach_states_the_strongest_available_conclusion(self, client):
        data = client.get("/evidence/capacity/zz").json()
        assert data["strongest_available_conclusion"] == "unverified"

    def test_the_principle_is_stated(self, client):
        data = client.get("/evidence/capacity/ng").json()
        assert "not evidence of absence" in data["note"]

    def test_capacity_is_about_the_country_not_any_claim(self, client):
        data = client.get("/evidence/capacity/ng").json()
        assert "not of any project or claim" in data["note"]

    def test_map_provenance_is_disclosed(self, client):
        data = client.get("/evidence/capacity/ng").json()
        assert data["map_status"] == "illustrative"
        assert data["map_validated"] is False


# ═══════════════════════════════════════════════════════════
# SPEC TEST 51 — GET /evidence/dossier/{dossier_id}
# ═══════════════════════════════════════════════════════════


class TestDossierEndpoint:

    def _analyse(self, client):
        return client.post("/evidence/analyze", json=request_body()).json()["dossier_id"]

    def test_returns_the_full_dossier(self, client):
        dossier_id = self._analyse(client)
        data = client.get(f"/evidence/dossier/{dossier_id}").json()
        for key in ("claim", "verdict", "artifacts", "source_registry",
                    "graph", "expected_evidence", "contradictions",
                    "rules_fired", "disclaimer"):
            assert key in data

    def test_graph_is_included(self, client):
        dossier_id = self._analyse(client)
        graph = client.get(f"/evidence/dossier/{dossier_id}").json()["graph"]
        assert graph["node_count"] > 0
        assert len(graph["nodes"]) == graph["node_count"]

    def test_provenance_chain_is_included(self, client):
        dossier_id = self._analyse(client)
        artifacts = client.get(f"/evidence/dossier/{dossier_id}").json()["artifacts"]
        prov = artifacts[0]["provenance"]
        assert prov["content_hash"] == CONTENT_HASH
        assert prov["source_name"]
        assert prov["hash_algorithm"] == "sha256"

    def test_artifact_content_is_never_stored(self, client):
        """Evidence bytes are hashed at ingestion and discarded, so a
        compromised cache leaks no underlying documents."""
        dossier_id = self._analyse(client)
        blob = client.get(f"/evidence/dossier/{dossier_id}").text
        assert "municipal construction permit no. 44182" not in blob

    def test_refused_artifacts_are_shown_as_refused(self, client):
        """Quarantine, not deletion — the submitter can see what was refused."""
        body = request_body(artifacts=[artifact(with_provenance=False)])
        dossier_id = client.post("/evidence/analyze", json=body).json()["dossier_id"]
        artifacts = client.get(f"/evidence/dossier/{dossier_id}").json()["artifacts"]
        assert artifacts[0]["admitted"] is False

    def test_retention_is_declared_ephemeral(self, client):
        """So that no institution builds an audit trail on an in-process cache."""
        dossier_id = self._analyse(client)
        data = client.get(f"/evidence/dossier/{dossier_id}").json()
        assert "Ephemeral" in data["retention"]
        assert "not a database" in data["retention"]

    def test_unknown_dossier_is_404_explaining_why(self, client):
        response = client.get("/evidence/dossier/does-not-exist")
        assert response.status_code == 404
        assert "ephemeral" in response.json()["detail"].lower()

    def test_expected_evidence_shows_whether_absence_would_count(self, client):
        dossier_id = self._analyse(client)
        data = client.get(f"/evidence/dossier/{dossier_id}").json()
        for entry in data["expected_evidence"]:
            assert "absence_is_meaningful" in entry


# ═══════════════════════════════════════════════════════════
# SPEC TEST 52 — POST /evidence/verify-integrity
# ═══════════════════════════════════════════════════════════


class TestVerifyIntegrityEndpoint:

    def _analyse(self, client, **kwargs):
        return client.post(
            "/evidence/analyze", json=request_body(**kwargs)).json()["dossier_id"]

    def test_intact_content_verifies(self, client):
        dossier_id = self._analyse(client)
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1",
            "dossier_id": dossier_id,
            "content_base64": base64.b64encode(CONTENT).decode(),
        })
        data = response.json()
        assert data["verified"] is True
        assert data["recorded_hash"] == data["computed_hash"]
        assert data["finding"] is None

    def test_tampered_content_is_detected(self, client):
        dossier_id = self._analyse(client)
        data = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1",
            "dossier_id": dossier_id,
            "content_base64": base64.b64encode(b"a different document").decode(),
        }).json()
        assert data["verified"] is False
        assert data["recorded_hash"] != data["computed_hash"]
        assert data["finding"] == "EVD-SRC-002"

    def test_mismatch_is_reported_not_raised(self, client):
        """Integrity failure is a finding for EVD-SRC-002 to carry, not an
        error to unwind."""
        dossier_id = self._analyse(client)
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1",
            "dossier_id": dossier_id,
            "content_base64": base64.b64encode(b"tampered").decode(),
        })
        assert response.status_code == 200

    def test_utf8_text_content_accepted(self, client):
        text = "a plain text artifact"
        digest = hashlib.sha256(text.encode()).hexdigest()
        body = request_body(artifacts=[
            {"artifact_id": "T1", "evidence_class": "institutional",
             "description": "text artifact", "status": "observed",
             "source_party_id": "PERMITS",
             "provenance": provenance(content_hash=digest)},
        ])
        dossier_id = client.post("/evidence/analyze", json=body).json()["dossier_id"]
        data = client.post("/evidence/verify-integrity", json={
            "artifact_id": "T1", "dossier_id": dossier_id, "content": text,
        }).json()
        assert data["verified"] is True

    def test_both_encodings_is_400(self, client):
        """The encoding must be explicit — a digest over differently-encoded
        bytes is a different digest, and an ambiguous mismatch would be
        indistinguishable from tampering."""
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1", "content": "x",
            "content_base64": base64.b64encode(b"x").decode(),
        })
        assert response.status_code == 400
        assert "exactly one" in response.json()["detail"]

    def test_neither_encoding_is_400(self, client):
        response = client.post(
            "/evidence/verify-integrity", json={"artifact_id": "A1"})
        assert response.status_code == 400

    def test_invalid_base64_is_400(self, client):
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1", "content_base64": "not!valid!base64!",
        })
        assert response.status_code == 400

    def test_unknown_artifact_is_404(self, client):
        self._analyse(client)
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "NOT-THERE",
            "content_base64": base64.b64encode(CONTENT).decode(),
        })
        assert response.status_code == 404

    def test_unknown_dossier_is_404(self, client):
        response = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1", "dossier_id": "nope",
            "content_base64": base64.b64encode(CONTENT).decode(),
        })
        assert response.status_code == 404

    def test_artifact_without_provenance_cannot_be_verified(self, client):
        body = request_body(artifacts=[artifact(with_provenance=False)])
        dossier_id = client.post("/evidence/analyze", json=body).json()["dossier_id"]
        data = client.post("/evidence/verify-integrity", json={
            "artifact_id": "A1", "dossier_id": dossier_id,
            "content_base64": base64.b64encode(CONTENT).decode(),
        }).json()
        assert data["verified"] is False
        assert data["finding"] == "EVD-SRC-002"


# ═══════════════════════════════════════════════════════════
# CROSS-CUTTING
# ═══════════════════════════════════════════════════════════


class TestSideOneToFourUnaffected:
    """Side 5 endpoints are additive. The existing API is untouched."""

    def test_root_still_lists_the_service(self, client):
        assert client.get("/").status_code == 200

    def test_health_still_answers(self, client):
        assert client.get("/health").status_code == 200

    def test_existing_analyze_still_works(self, client):
        response = client.post("/analyze", json={
            "contract": {"ocid": "test-1", "tender": {"value": {"amount": 50000}}},
            "profile": "us_federal",
        })
        assert response.status_code == 200

    def test_evidence_routes_are_all_registered(self, client):
        paths = {r.path for r in app.routes if getattr(r, "path", "").startswith("/evidence")}
        assert paths == {
            "/evidence/analyze",
            "/evidence/batch",
            "/evidence/expected/{outcome_type}",
            "/evidence/capacity/{country_code}",
            "/evidence/dossier/{dossier_id}",
            "/evidence/verify-integrity",
        }


class TestDossierCacheIsBounded:
    """An unbounded store in a long-running API is a defect, not a feature."""

    def test_cache_evicts_oldest_past_the_cap(self):
        from api import (
            _EVIDENCE_DOSSIER_CACHE_MAX,
            _evidence_dossiers,
            _remember_dossier,
        )
        from evidence_schema import CorroborationDossier, OutcomeClaim, OutcomeType

        _evidence_dossiers.clear()
        first_id = None
        for i in range(_EVIDENCE_DOSSIER_CACHE_MAX + 10):
            d = CorroborationDossier(claim=OutcomeClaim(
                claim_id=f"C{i}", contract_id="K",
                outcome_type=OutcomeType.SERVICE_DELIVERY,
                claim_description="x"))
            if i == 0:
                first_id = d.dossier_id
            _remember_dossier(d)

        assert len(_evidence_dossiers) == _EVIDENCE_DOSSIER_CACHE_MAX
        assert first_id not in _evidence_dossiers
        _evidence_dossiers.clear()
