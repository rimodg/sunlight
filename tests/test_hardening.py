"""
SUNLIGHT hardening tests — high-volume institutional longevity.

These exist because the failure modes that matter at scale are not the ones
that matter in a demo. A wrong score is visible and arguable. A contract that
enters the system and silently vanishes is neither, and at high ingestion rate
it is the failure that destroys trust in every other number.

Covers:
    - No silent drop: every submitted contract yields a result or a recorded
      error, never nothing
    - Edge inputs produce a defined, honest result that states its own
      limitation rather than a fabricated score
    - Determinism across every engine, not only the DOJ path
    - Output consistency: the same response field means the same thing on
      every endpoint that returns it
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient

from api import app


@pytest.fixture
def client():
    return TestClient(app)


WELL_FORMED = {
    "ocid": "hard-ok-1", "buyer": {"name": "Ministry of Health", "id": "MOH"},
    "tender": {"value": {"amount": 50_000, "currency": "USD"},
               "procurementMethod": "open", "numberOfTenderers": 4},
    "awards": [{"id": "A", "value": {"amount": 50_000, "currency": "USD"},
                "suppliers": [{"name": "S", "id": "S1"}], "date": "2025-02-01"}],
}

# Schema-valid but semantically hostile. Schema-INVALID input is rejected
# wholesale by Pydantic with an exact pointer, which is loud and correct;
# these are the ones that reach the engine and could vanish quietly.
EDGE_CASES = [
    ("ocid only", {"ocid": "hard-bare-1"}),
    ("null tender", {"ocid": "hard-null-1", "tender": None}),
    ("negative amount", {"ocid": "hard-neg-1",
                         "tender": {"value": {"amount": -5000, "currency": "USD"}}}),
    ("string amount", {"ocid": "hard-str-1",
                       "tender": {"value": {"amount": "lots", "currency": "USD"}}}),
    ("astronomical amount", {"ocid": "hard-huge-1",
                             "tender": {"value": {"amount": 1e18, "currency": "USD"}}}),
    ("unicode names", {"ocid": "hard-uni-1",
                       "buyer": {"name": "Ministère 保健省 Здоров'я"}}),
    ("empty arrays", {"ocid": "hard-empty-1", "awards": [], "parties": []}),
    ("malformed date", {"ocid": "hard-date-1",
                        "awards": [{"id": "A", "date": "not-a-date"}]}),
    ("nested type error", {"ocid": "hard-deep-1",
                           "tender": {"value": {"amount": {"nested": "bad"}}}}),
]


# ═══════════════════════════════════════════════════════════
# NO SILENT DROP — the failure that matters most at volume
# ═══════════════════════════════════════════════════════════


class TestNoSilentDrop:

    def test_every_submitted_contract_is_accounted_for(self, client):
        """The load-bearing guarantee. At high ingestion rate a vanished
        contract is indistinguishable from one that was never sent, and no
        downstream count can be trusted if that is possible."""
        payload = [WELL_FORMED] + [c for _, c in EDGE_CASES]
        r = client.post("/batch", json={"contracts": payload})
        assert r.status_code == 200
        body = r.json()
        assert len(body["results"]) == len(payload)

    def test_every_result_carries_an_ocid_that_was_submitted(self, client):
        """Accounted-for means identifiable, not merely counted."""
        payload = [WELL_FORMED] + [c for _, c in EDGE_CASES]
        body = client.post("/batch", json={"contracts": payload}).json()
        submitted = {c["ocid"] for c in payload}
        returned = {r["ocid"] for r in body["results"]}
        assert returned == submitted

    def test_a_failing_contract_records_its_failure(self, client):
        """It must fail loudly in its own result, not disappear."""
        body = client.post("/batch", json={"contracts": [
            WELL_FORMED,
            {"ocid": "hard-fail-1",
             "tender": {"value": {"amount": {"nested": "bad"}}}},
        ]}).json()
        failed = [r for r in body["results"] if r["stage"] == "failed"]
        assert len(failed) == 1
        assert failed[0]["errors"]
        assert failed[0]["ocid"] == "hard-fail-1"

    def test_error_count_matches_failed_results(self, client):
        payload = [WELL_FORMED] + [c for _, c in EDGE_CASES]
        body = client.post("/batch", json={"contracts": payload}).json()
        failed = [r for r in body["results"] if r["errors"]]
        assert body["total_errors"] == len(failed)

    def test_one_bad_contract_does_not_sink_its_neighbours(self, client):
        """A single malformed record must not cost the whole batch."""
        body = client.post("/batch", json={"contracts": [
            WELL_FORMED,
            {"ocid": "hard-poison", "tender": {"value": {"amount": {"x": "y"}}}},
            dict(WELL_FORMED, ocid="hard-ok-2"),
        ]}).json()
        stages = [r["stage"] for r in body["results"]]
        assert stages.count("complete") == 2
        assert stages.count("failed") == 1

    def test_schema_invalid_input_is_rejected_loudly_not_silently(self, client):
        """A contract missing the one required field is refused with a pointer
        to the offending element. Loud whole-batch rejection is a scale
        limitation, recorded in the readiness assessment — but it is not a
        silent loss, which is what must never happen."""
        r = client.post("/batch", json={"contracts": [WELL_FORMED, {}]})
        assert r.status_code == 422
        detail = json.dumps(r.json())
        assert "ocid" in detail
        assert "contracts" in detail


# ═══════════════════════════════════════════════════════════
# EDGE INPUTS STATE THEIR OWN LIMITATION
# ═══════════════════════════════════════════════════════════


class TestEdgeHonesty:

    @pytest.mark.parametrize("label,contract", EDGE_CASES)
    def test_edge_case_never_raises_unhandled(self, client, label, contract):
        r = client.post("/analyze", json={"contract": contract})
        assert r.status_code in (200, 400), f"{label} produced {r.status_code}"

    @pytest.mark.parametrize("label,contract", EDGE_CASES)
    def test_edge_case_result_is_defined(self, client, label, contract):
        """Either a result with a stage, or a stated error. Never both empty."""
        r = client.post("/analyze", json={"contract": contract})
        if r.status_code == 200:
            body = r.json()
            assert body["stage"]
            assert body["ocid"] == contract["ocid"]
        else:
            assert r.json().get("detail")

    def test_a_minimal_contract_declares_low_context_not_a_clean_score(self, client):
        """THE 1A GUARD AT THE EDGE. A contract carrying only an ocid has
        almost nothing to assess. Before the isolation fix it returned
        composite 0.0 across four axes with no qualification, which reads as a
        clean bill of health. It must now say how little it knows."""
        body = client.post("/analyze",
                           json={"contract": {"ocid": "hard-minimal-1"}}).json()
        s = body["structural_scoring"]
        ctx = s["assessment_context"]
        assert ctx["axes_populated"] < ctx["axes_total"]
        assert ctx["low_context"] is True
        assert "LOW CONTEXT" in ctx["note"]

    def test_indeterminate_axes_are_null_on_a_minimal_contract(self, client):
        body = client.post("/analyze",
                           json={"contract": {"ocid": "hard-minimal-2"}}).json()
        subs = body["structural_scoring"]["sub_scores"]
        indeterminate = [n for n, v in subs.items() if not v["determinate"]]
        assert indeterminate
        for n in indeterminate:
            assert subs[n]["score"] is None, f"{n} rendered 0.0 instead of null"

    def test_malformed_date_makes_temporal_indeterminate_not_clean(self, client):
        """An unparseable award date is not a contract with good timing."""
        body = client.post("/analyze", json={"contract": {
            "ocid": "hard-date-2", "awards": [{"id": "A", "date": "not-a-date"}]}}).json()
        temporal = body["structural_scoring"]["sub_scores"]["temporal_score"]
        assert temporal["determinate"] is False
        assert temporal["score"] is None

    def test_unknown_jurisdiction_is_refused_not_defaulted(self, client):
        """Silently falling back to another country's law would make every
        finding in that response wrong about its own legal basis."""
        r = client.post("/analyze",
                        json={"contract": WELL_FORMED, "profile": "atlantis"})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════
# DETERMINISM ACROSS EVERY ENGINE
# ═══════════════════════════════════════════════════════════


class TestDeterminismAcrossEngines:
    """Determinism is evidentiary, not a nicety: a finding that cannot be
    reproduced cannot be defended. Asserted per engine, not only on the DOJ
    path, because each has its own state and its own chance to leak entropy.
    """

    def _twice(self, client, path, payload):
        a = client.post(path, json=payload).json()
        b = client.post(path, json=payload).json()
        return a, b

    def test_side1_analyze_is_deterministic(self, client):
        a, b = self._twice(client, "/analyze", {"contract": WELL_FORMED})
        for k in ("gate_verdict", "recommended_for_investigation"):
            assert a[k] == b[k]
        assert a["structure"] == b["structure"]
        assert a["gate_outcome"] == b["gate_outcome"]

    def test_side1_batch_is_deterministic(self, client):
        a, b = self._twice(client, "/batch", {"contracts": [WELL_FORMED]})
        assert a["verdict_distribution"] == b["verdict_distribution"]
        assert a["results"][0]["structure"] == b["results"][0]["structure"]

    def test_structural_scoring_is_deterministic(self, client):
        from structural_scoring import strip_volatile
        a, b = self._twice(client, "/analyze", {"contract": WELL_FORMED})
        assert strip_volatile(a["structural_scoring"]) == \
               strip_volatile(b["structural_scoring"])

    def test_side2_delivery_is_deterministic(self, client):
        payload = {"contract_id": "hard-del-1", "milestones": [
            {"milestone_id": "M1", "description": "phase 1",
             "planned_date": "2025-01-01", "actual_date": "2025-04-01",
             "status": "completed", "delay_days": 90}]}
        a, b = self._twice(client, "/delivery/analyze", payload)
        assert a.get("delivery_verdict") == b.get("delivery_verdict")
        assert a.get("rule_fires") == b.get("rule_fires")

    def test_side5_evidence_is_deterministic(self, client):
        payload = {
            "claim": {"claim_id": "C1", "contract_id": "K1",
                      "outcome_type": "facility_construction",
                      "claim_description": "clinic operational"},
            "artifacts": [], "source_registry": [], "profile": "us_federal"}
        a, b = self._twice(client, "/evidence/analyze", payload)
        assert a["verdict"] == b["verdict"]
        assert a["confidence"] == b["confidence"]
        assert a["rule_fires"] == b["rule_fires"]

    def test_side3_triage_is_deterministic(self, client):
        payload = {"batch_id": "hard-b1", "alerts": []}
        a = client.post("/alerts/triage", json=payload)
        b = client.post("/alerts/triage", json=payload)
        if a.status_code == 200:
            assert a.json().get("executive_summary") == b.json().get("executive_summary")

    def test_repeated_runs_do_not_accumulate_state(self, client):
        """A pure engine must not drift as it is used. Ten runs, one answer."""
        verdicts = {client.post("/analyze", json={"contract": WELL_FORMED})
                    .json()["gate_verdict"] for _ in range(10)}
        assert len(verdicts) == 1


# ═══════════════════════════════════════════════════════════
# OUTPUT CONSISTENCY ACROSS ENDPOINTS
# ═══════════════════════════════════════════════════════════


class TestOutputConsistency:

    def test_batch_and_single_agree_on_structure(self, client):
        one = client.post("/analyze", json={"contract": WELL_FORMED}).json()
        many = client.post("/batch", json={"contracts": [WELL_FORMED]}).json()
        assert many["results"][0]["structure"] == one["structure"]
        assert many["results"][0]["gate_verdict"] == one["gate_verdict"]

    def test_structural_scoring_populates_on_both_paths(self, client):
        """The same response model returning a scored result from one endpoint
        and null from another would make the field's meaning depend on which
        endpoint a consumer happened to call."""
        one = client.post("/analyze", json={"contract": WELL_FORMED}).json()
        many = client.post("/batch", json={"contracts": [WELL_FORMED]}).json()
        assert one["structural_scoring"] is not None
        assert many["results"][0]["structural_scoring"] is not None

    def test_batch_and_single_agree_on_composite(self, client):
        one = client.post("/analyze", json={"contract": WELL_FORMED}).json()
        many = client.post("/batch", json={"contracts": [WELL_FORMED]}).json()
        assert (many["results"][0]["structural_scoring"]["composite_structural_score"]
                == one["structural_scoring"]["composite_structural_score"])

    def test_attribution_is_complete_on_both_paths(self, client):
        """No empty rule_id, layer, severity or citation anywhere."""
        flagged = {"ocid": "hard-attr-1",
                   "tender": {"value": {"amount": 48_500_000, "currency": "USD"},
                              "procurementMethod": "limited", "numberOfTenderers": 1},
                   "awards": [{"id": "A", "date": "2024-09-29",
                               "value": {"amount": 48_500_000, "currency": "USD"},
                               "suppliers": [{"name": "V", "id": "V1"}]}]}
        one = client.post("/analyze", json={"contract": flagged}).json()
        many = client.post("/batch", json={"contracts": [flagged]}).json()
        for src in (one["structure"]["contradictions"],
                    many["results"][0]["structure"]["contradictions"]):
            assert src
            for f in src:
                for k in ("rule_id", "rule_name", "layer", "severity",
                          "legal_citation"):
                    assert str(f.get(k, "")).strip(), f"{k} empty"
