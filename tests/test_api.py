"""
Tests for the SUNLIGHT core analysis API.

REWRITTEN. The previous version of this file tested an API that was removed on
2026-04-09 by commit 3ade70e, which rewrote code/api.py and deleted 1230 lines along
with the module-level DB_PATH those tests monkeypatched. All 55 of its tests had been
erroring with the same AttributeError ever since, and the routes they exercised —
/contracts, /admin/dashboard/*, /admin/keys/*, /ingest, /runs, /audit, /methodology,
/reports/triage, /analyze/batch — exist in no module of the current codebase (checked
against api, api_v2, api_v2_routes, cri_api, tenant_profile_api).

This covers the CORE surface, which had no dedicated test file:

    GET  /                          service descriptor
    GET  /version                   version + profile inventory
    GET  /health                    liveness
    GET  /profiles                  jurisdiction profile inventory
    GET  /calibration/{profile}     live empirical calibration state
    POST /analyze                   single-contract analysis
    POST /batch                     batch analysis + threshold metadata

Covered elsewhere, deliberately not duplicated here:
    /alerts/*     tests/test_alert_api.py
    /delivery/*   tests/test_delivery_api.py
    /recovery/*   tests/test_recovery_api.py
    /input-formats and the adapter paths through /analyze
                  tests/test_input_adapters.py
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient
from api import app


@pytest.fixture
def client():
    return TestClient(app)


def contract(ocid="ocds-test-0001", tender_amount=1_000_000, award_amount=1_200_000,
             method="open"):
    """A minimal but well-formed OCDS release. `ocid` is the only field the schema
    requires; the rest is what makes the analysis meaningful rather than empty."""
    return {
        "ocid": ocid,
        "buyer": {"name": "Ministry of Health", "id": "MOH-1"},
        "tender": {
            "id": "T-1",
            "title": "Medical supplies",
            "procurementMethod": method,
            "value": {"amount": tender_amount, "currency": "USD"},
            "tenderPeriod": {"startDate": "2025-01-01T00:00:00Z",
                             "endDate": "2025-02-01T00:00:00Z"},
        },
        "awards": [{
            "id": "A-1",
            "value": {"amount": award_amount, "currency": "USD"},
            "suppliers": [{"name": "Acme Ltd", "id": "ACME"}],
            "date": "2025-02-15T00:00:00Z",
        }],
    }


# ═══════════════════════════════════════════════════════════
# SERVICE DESCRIPTOR AND VERSION
# ═══════════════════════════════════════════════════════════

class TestServiceDescriptor:

    def test_root_returns_service_identity_and_where_the_docs_are(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert "SUNLIGHT" in body["service"]
        assert body["documentation"] == "/docs"
        assert body["openapi_spec"] == "/openapi.json"

    def test_health_is_live(self, client):
        assert client.get("/health").status_code == 200

    def test_version_reports_sunlight_mjpis_and_the_profiles_it_carries(self, client):
        body = client.get("/version").json()
        assert body["sunlight_version"]
        assert body["mjpis_version"]                 # the parameter set is versioned too
        assert isinstance(body["profiles"], list) and body["profiles"]

    def test_version_profiles_match_the_profiles_endpoint(self, client):
        """Two endpoints report the profile inventory. They must not drift apart."""
        from_version = set(client.get("/version").json()["profiles"])
        from_profiles = {p["name"] for p in client.get("/profiles").json()["profiles"]}
        assert from_version == from_profiles


# ═══════════════════════════════════════════════════════════
# JURISDICTION PROFILES
# ═══════════════════════════════════════════════════════════

class TestProfiles:

    def test_profiles_are_listed_with_the_facts_a_caller_needs(self, client):
        profiles = client.get("/profiles").json()["profiles"]
        assert profiles
        for p in profiles:
            assert p["name"] and p["country_code"] and p["currency"]
            assert p["description"]                  # a profile without provenance is
                                                     # not usable as evidence

    def test_the_two_shipped_profiles_are_present(self, client):
        names = {p["name"] for p in client.get("/profiles").json()["profiles"]}
        assert {"us_federal", "uk_central_government"} <= names


# ═══════════════════════════════════════════════════════════
# SINGLE-CONTRACT ANALYSIS
# ═══════════════════════════════════════════════════════════

class TestAnalyze:

    def test_a_well_formed_contract_analyses(self, client):
        r = client.post("/analyze", json={"contract": contract()})
        assert r.status_code == 200
        body = r.json()
        assert body["ocid"] == "ocds-test-0001"
        assert body["stage"] == "complete"
        assert body["errors"] == []

    def test_the_response_carries_a_gate_verdict_from_the_known_set(self, client):
        body = client.post("/analyze", json={"contract": contract()}).json()
        assert body["gate_verdict"] in {"green", "yellow", "red"}
        assert "gate_outcome" in body

    def test_the_response_carries_the_structural_finding_and_its_confidence(self, client):
        structure = client.post("/analyze",
                                json={"contract": contract()}).json()["structure"]
        assert "verdict" in structure
        assert "confidence" in structure
        assert "contradictions" in structure         # the TCA half, not just the price half

    def test_the_profile_actually_used_is_reported_back(self, client):
        """A verdict without the profile that produced it is not auditable."""
        body = client.post("/analyze",
                           json={"contract": contract(), "profile": "us_federal"}).json()
        assert body["profile_used"] == "us_federal"

    def test_processing_time_is_reported(self, client):
        body = client.post("/analyze", json={"contract": contract()}).json()
        assert body["processing_time_ms"] >= 0

    def test_the_same_contract_analyses_identically(self, client):
        """Determinism is evidentiary here, not a nicety: the same contract must not
        produce a different verdict on a second run, or no finding could be defended."""
        a = client.post("/analyze", json={"contract": contract()}).json()
        b = client.post("/analyze", json={"contract": contract()}).json()
        assert a["gate_verdict"] == b["gate_verdict"]
        assert a["structure"]["verdict"] == b["structure"]["verdict"]
        assert a["recommended_for_investigation"] == b["recommended_for_investigation"]


class TestAnalyzeRejections:

    def test_an_unknown_profile_is_refused_rather_than_silently_defaulted(self, client):
        r = client.post("/analyze",
                        json={"contract": contract(), "profile": "atlantis_federal"})
        assert r.status_code == 404

    def test_a_contract_with_no_ocid_is_refused_by_the_schema(self, client):
        r = client.post("/analyze", json={"contract": {"buyer": {"name": "MOH"}}})
        assert r.status_code == 422                  # ocid is the one required field

    def test_an_empty_body_is_refused(self, client):
        assert client.post("/analyze", json={}).status_code == 422


# ═══════════════════════════════════════════════════════════
# BATCH ANALYSIS
# ═══════════════════════════════════════════════════════════

class TestBatch:

    def test_a_batch_processes_every_contract_it_was_given(self, client):
        contracts = [contract(f"ocds-batch-{i:03d}") for i in range(5)]
        body = client.post("/batch", json={"contracts": contracts}).json()
        assert body["total_processed"] == 5
        assert len(body["results"]) == 5

    def test_a_batch_reports_its_verdict_distribution(self, client):
        """NOTE, because it will trip up a caller: `verdict_distribution` counts the
        STRUCTURAL verdict (sound / concern / compromised / critical / unknown), NOT the
        per-result `gate_verdict` (green / yellow / red). Two different vocabularies, both
        called 'verdict', in the same response. This pins the actual behaviour so the
        mismatch is visible rather than discovered in production."""
        contracts = [contract(f"ocds-dist-{i:03d}") for i in range(3)]
        body = client.post("/batch", json={"contracts": contracts}).json()
        dist = body["verdict_distribution"]
        assert sum(dist.values()) == body["total_processed"]
        assert set(dist) <= {"sound", "concern", "compromised", "critical", "unknown"}
        # and it is NOT the gate vocabulary
        assert set(dist).isdisjoint({"green", "yellow", "red"})

    def test_a_batch_reports_the_threshold_that_bound_it(self, client):
        """Which threshold decided the flags — statistical or capacity — is part of the
        finding, not an implementation detail."""
        body = client.post("/batch",
                           json={"contracts": [contract("ocds-thr-1")]}).json()
        assert "threshold_metadata" in body

    def test_a_capacity_budget_computes_and_reports_a_binding_threshold(self, client):
        """The budget does reach the threshold arithmetic and is reported as binding."""
        contracts = [contract(f"ocds-cap-{i:03d}", award_amount=1_000_000 + i * 400_000)
                     for i in range(10)]
        meta = client.post("/batch",
                           json={"contracts": contracts,
                                 "capacity_budget": 2}).json()["threshold_metadata"]
        assert meta["capacity_budget"] == 2
        assert meta["capacity_threshold"] is not None
        assert meta["binding_threshold"] >= meta["statistical_threshold"]

    def test_the_second_pass_demotes_as_well_as_promotes(self, client):
        """The second pass ASSIGNS from the binding threshold, it does not only promote.

        Previously it set recommended_for_investigation=True and never False, so a
        contract flagged against the statistical threshold in pass one stayed flagged
        even when a capacity budget raised the binding threshold above it. The ceiling
        silently did nothing to those contracts.

        This pins the fix: whatever is reported as recommended must agree with the
        binding threshold in both directions, and never exceed recommended_count.
        """
        contracts = [contract(f"ocds-demote-{i:03d}", award_amount=1_000_000 + i * 400_000)
                     for i in range(10)]
        body = client.post("/batch",
                           json={"contracts": contracts, "capacity_budget": 1}).json()
        meta = body["threshold_metadata"]
        flagged = [r for r in body["results"] if r.get("recommended_for_investigation")]

        # The count in metadata and the flags on the results must be the same set.
        assert len(flagged) == meta["recommended_count"]
        # A raised binding threshold must not leave stale first-pass flags behind.
        assert meta["binding_threshold"] >= meta["statistical_threshold"]

    def test_zero_capacity_recommends_nothing(self, client):
        """The strongest form of the ceiling: budget 0 must flag nothing at all.

        This is the one capacity case ties cannot corrupt, because the threshold is
        +inf rather than a score drawn from the batch — so it holds today and would
        have caught a promote-only second pass immediately.
        """
        contracts = [contract(f"ocds-zero-{i:03d}", award_amount=1_000_000 + i * 400_000)
                     for i in range(5)]
        body = client.post("/batch",
                           json={"contracts": contracts, "capacity_budget": 0}).json()
        flagged = [r for r in body["results"] if r.get("recommended_for_investigation")]
        assert flagged == []
        assert body["threshold_metadata"]["recommended_count"] == 0

    @pytest.mark.xfail(
        strict=True,
        reason="KNOWN DEFECT — capacity_budget does not bind under ties. "
               "compute_risk_score is verdict_rank + confidence, and its own docstring "
               "calls confidence 'a tiebreaker within verdicts'; when confidence is also "
               "identical the tie is not broken. The C-th highest score is taken as the "
               "threshold and compared with >=, so every contract tied at that score is "
               "admitted. Measured: capacity_budget=2 over 10 contracts scoring "
               "[1.95, 2.75 x 9] yields binding_threshold=2.75 and 9 recommendations. "
               "An investigator with capacity for 2 is handed 9. "
               "The second, independent defect in this block — the promote-only second "
               "pass — IS now fixed; it assigns from the binding threshold in both "
               "directions and is pinned by "
               "test_the_second_pass_demotes_as_well_as_promotes. "
               "This tie defect remains DELIBERATELY DEFERRED, not forgotten: breaking "
               "the tie means deciding which 2 of 9 identically-scored contracts an "
               "investigator receives, and every available answer is arbitrary. Picking "
               "by original batch order would make the output depend on submission "
               "sequence; picking none would discard real signal. The honest fix is "
               "probably to report the tied group and let the institution choose, which "
               "is a product decision rather than a code change. Owner's call.")
    def test_a_capacity_budget_is_honoured_as_a_ceiling_on_flags(self, client):
        """The behaviour the feature exists to provide: never recommend more cases than
        the investigator can actually take. When this starts passing, the defect above is
        fixed and the xfail should be removed in the same commit."""
        contracts = [contract(f"ocds-cap-{i:03d}", award_amount=1_000_000 + i * 400_000)
                     for i in range(10)]
        body = client.post("/batch",
                           json={"contracts": contracts, "capacity_budget": 2}).json()
        flagged = [r for r in body["results"] if r.get("recommended_for_investigation")]
        assert len(flagged) <= 2

    def test_an_empty_batch_is_handled_without_error(self, client):
        r = client.post("/batch", json={"contracts": []})
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert r.json()["total_processed"] == 0

    def test_batch_errors_are_counted_not_hidden(self, client):
        body = client.post("/batch",
                           json={"contracts": [contract("ocds-err-1")]}).json()
        assert "total_errors" in body

    def test_batch_and_single_agree_on_the_same_contract(self, client):
        """A contract must not get one verdict alone and another in company."""
        one = client.post("/analyze",
                          json={"contract": contract("ocds-agree-1")}).json()
        many = client.post("/batch",
                           json={"contracts": [contract("ocds-agree-1")]}).json()
        assert many["results"][0]["gate_verdict"] == one["gate_verdict"]


# ═══════════════════════════════════════════════════════════
# CALIBRATION STATE
# ═══════════════════════════════════════════════════════════

class TestCalibration:

    def test_calibration_state_is_returned_for_a_known_profile(self, client):
        r = client.get("/calibration/us_federal")
        assert r.status_code == 200
        assert r.json()["profile_name"] == "us_federal"

    def test_an_unobserved_profile_returns_zeroed_state_not_404(self, client):
        """Pinning a documented design decision (code/api.py get_calibration_state):
        absence means 'no observations yet', NOT 'profile does not exist'. Callers check
        GET /profiles for existence. A future refactor that turns this into a 404 would
        be a behaviour change, and this test is where it should surface."""
        r = client.get("/calibration/never_observed_profile")
        assert r.status_code == 200
        body = r.json()
        assert body["total_contracts_analyzed"] == 0
        assert body["verdict_counts"] == {}
        assert body["mean_risk_score"] is None       # no observations -> no mean, not 0.0

    def test_analysis_accumulates_into_the_calibration_state(self, client):
        """The store is a live running view of what normal looks like, so a batch run
        must move it."""
        before = client.get("/calibration/us_federal").json()["total_contracts_analyzed"]
        client.post("/batch", json={"contracts": [contract("ocds-calib-1"),
                                                  contract("ocds-calib-2")],
                                    "profile": "us_federal"})
        after = client.get("/calibration/us_federal").json()["total_contracts_analyzed"]
        assert after > before


# ═══════════════════════════════════════════════════════════
# FINDING ATTRIBUTION
# ═══════════════════════════════════════════════════════════


class TestFindingAttribution:
    """Every finding must be able to name the rule that produced it.

    SUNLIGHT's central claim is that every flag traces to a rule and every
    rule traces to a legal citation. The engine writes findings keyed `rule`;
    the API read `rule_id`, which the engine never writes. So rule_id was ""
    on every finding in every response, severity was "unknown", and
    legal_citations was []. The claim was true internally and unobservable
    externally — and no test covered the field, which is why it survived.
    """

    HIGH_RISK = {
        "contract": {
            "ocid": "ocds-attribution-001",
            "buyer": {"name": "Defense Procurement Office", "id": "DPO-01"},
            "tender": {"title": "Emergency aircraft component resupply",
                       "value": {"amount": 48_500_000, "currency": "USD"},
                       "procurementMethod": "limited",
                       "procurementMethodRationale": "urgency",
                       "numberOfTenderers": 1},
            "awards": [{"id": "A1", "date": "2024-09-29",
                        "value": {"amount": 48_500_000, "currency": "USD"},
                        "suppliers": [{"name": "Zenith Infrastructure Ltd", "id": "V-9001"}]}],
            "parties": [{"id": "V-9001", "name": "Zenith Infrastructure Ltd",
                         "roles": ["supplier"]}],
        },
        "profile": "us_federal",
    }

    def _findings(self, client):
        d = client.post("/analyze", json=self.HIGH_RISK).json()
        return d["structure"]["contradictions"]

    def test_findings_are_produced(self, client):
        assert len(self._findings(client)) > 0

    def test_all_six_attribution_fields_are_populated(self, client):
        """The prerequisite: rule_id, rule_name, layer, legal_citation,
        evidence and severity present and non-empty on every finding."""
        for f in self._findings(client):
            for field in ("rule_id", "rule_name", "layer",
                          "legal_citation", "evidence", "severity"):
                assert field in f, f"{field} missing"
                assert str(f[field]).strip(), f"{field} empty on {f.get('rule_id')!r}"

    def test_rule_id_is_a_real_registry_rule(self, client):
        """Not merely non-empty — it must name a rule that actually exists."""
        import os
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))
        from tca_rules import RULES
        known = {r.rule_id for r in RULES}
        for f in self._findings(client):
            assert f["rule_id"] in known, f"unknown rule {f['rule_id']}"

    def test_rule_name_and_layer_match_the_registry(self, client):
        import os
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))
        from tca_rules import RULES
        by_id = {r.rule_id: r for r in RULES}
        for f in self._findings(client):
            rule = by_id[f["rule_id"]]
            assert f["rule_name"] == rule.name
            assert f["layer"] == rule.layer

    def test_evidence_is_the_observed_fact_not_the_citation(self, client):
        """The correction. `evidence` held the legal citation, which is what
        `legal_citation` is for. Sides 2, 3 and 5 always named these two
        things this way; Side 1 was the outlier."""
        for f in self._findings(client):
            assert not f["evidence"].startswith("UNCAC"), \
                "evidence is carrying a citation again"
            assert f["evidence"] == f["description"]

    def test_legal_citation_is_populated_and_listed(self, client):
        for f in self._findings(client):
            assert f["legal_citation"]
            assert f["legal_citations"] == [f["legal_citation"]]

    def test_severity_reports_the_finding_class(self, client):
        for f in self._findings(client):
            assert f["severity"] in ("high", "medium"), f["severity"]
            assert f["severity"] != "unknown"
