"""
Tests for SUNLIGHT three-tier structural scoring and Fazekas CRI mapping.

The scoring layer is an OUTPUT layer. Its correctness claim is not "the score
is right" — that is a modelling judgement — but that the number is fully
DECOMPOSABLE: composite from vector, vector from rules, every rule named with
its citation. An institution must be able to rebuild the composite with a
calculator, and these tests assert exactly that.

The Fazekas mapping tests pin the table itself, because its value is entirely
in being conservative. A mapping that over-claims correspondence would tell an
institution its existing index already covers a risk it does not cover, which
is worse than reporting no correspondence at all.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from fastapi.testclient import TestClient

from api import app
from structural_scoring import (
    COMPOSITE_FORMULA,
    DEFAULT_CUTOFFS,
    FAZEKAS_FLAGS,
    RELATIONSHIP_CONFIRMS,
    RELATIONSHIP_NONE,
    RELATIONSHIP_RELATED,
    RULE_FAZEKAS_MAP,
    SUBSCORE_LAYERS,
    BandCutoffs,
    compute_composite,
    compute_sub_scores,
    fazekas_mapping_for,
    flags_never_confirmed,
    score_findings,
)


@pytest.fixture
def client():
    return TestClient(app)


def finding(rule_id, layer, severity="high", name="", evidence="observed", citation="UNCAC"):
    return {"rule_id": rule_id, "rule_name": name or rule_id, "layer": layer,
            "severity": severity, "evidence": evidence, "legal_citation": citation}


# A contract shaped like the Boeing case: a very large sole-source defence
# spare-parts award to a single bidder at fiscal year end.
BOEING_LIKE = {
    "contract": {
        "ocid": "ocds-doj-boeing-2006",
        "buyer": {"name": "Department of Defense - Air Force", "id": "USAF-01"},
        "tender": {"title": "Aircraft spare parts resupply",
                   "value": {"amount": 615_000_000, "currency": "USD"},
                   "procurementMethod": "limited",
                   "procurementMethodRationale": "sole source",
                   "numberOfTenderers": 1},
        "awards": [{"id": "A1", "date": "2006-09-28",
                    "value": {"amount": 615_000_000, "currency": "USD"},
                    "suppliers": [{"name": "Boeing Company", "id": "BOEING"}]}],
        "parties": [{"id": "BOEING", "name": "Boeing Company", "roles": ["supplier"]},
                    {"id": "USAF-01", "name": "Department of Defense - Air Force",
                     "roles": ["buyer"]}],
    },
    "profile": "us_federal",
}


# ═══════════════════════════════════════════════════════════
# TIER 1 — SUB-SCORE VECTOR
# ═══════════════════════════════════════════════════════════


class TestSubScores:

    def test_four_sub_scores_always_present(self):
        subs = compute_sub_scores([])
        assert set(subs) == {"procedural_score", "financial_score",
                             "temporal_score", "network_score"}

    def test_every_sub_score_is_in_range(self):
        findings = [finding(f"PROC-00{i}", "procurement") for i in range(1, 6)]
        for s in compute_sub_scores(findings).values():
            assert 0.0 <= s.score <= 1.0

    def test_sub_score_is_weighted_share_of_its_layer(self):
        """procurement has 5 rules; one contradiction at weight 1.0 -> 0.2."""
        subs = compute_sub_scores([finding("PROC-001", "procurement")])
        assert subs["procedural_score"].score == pytest.approx(1.0 / 5)

    def test_medium_severity_contributes_half(self):
        high = compute_sub_scores([finding("PROC-001", "procurement", "high")])
        med = compute_sub_scores([finding("PROC-001", "procurement", "medium")])
        assert med["procedural_score"].score == pytest.approx(
            high["procedural_score"].score / 2)

    def test_entity_and_network_merge_into_network_score(self):
        """Five engine layers collapse to four sub-scores; entity and network
        both describe relationships between parties."""
        subs = compute_sub_scores([finding("ENT-003", "entity"),
                                   finding("GEO-001", "network")])
        assert subs["network_score"].raw_weight == 2.0
        assert subs["network_score"].denominator == 5  # 3 entity + 2 network

    def test_score_is_capped_at_one(self):
        many = [finding(f"X-{i}", "temporal") for i in range(20)]
        assert compute_sub_scores(many)["temporal_score"].score == 1.0

    def test_zero_denominator_does_not_divide_by_zero(self):
        subs = compute_sub_scores([finding("X-1", "procurement")],
                                  layer_counts={"procurement": 0})
        assert subs["procedural_score"].score == 0.0

    def test_no_findings_yields_zero_not_none(self):
        for s in compute_sub_scores([]).values():
            assert s.score == 0.0

    def test_sub_scores_are_deterministic(self):
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        a = {k: v.score for k, v in compute_sub_scores(findings).items()}
        b = {k: v.score for k, v in compute_sub_scores(findings).items()}
        assert a == b


# ═══════════════════════════════════════════════════════════
# TIER 2 — COMPOSITE
# ═══════════════════════════════════════════════════════════


class TestComposite:

    def test_composite_is_the_exact_arithmetic_mean(self):
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        subs = compute_sub_scores(findings)
        expected = sum(s.score for s in subs.values()) / 4
        assert compute_composite(subs) == pytest.approx(expected)

    def test_composite_matches_a_hand_calculation(self):
        """The property the formula is published for: an evaluator with a
        calculator must reach the same number."""
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        out = score_findings(findings)
        by_hand = (1 / 5 + 0.0 + 1 / 3 + 0.0) / 4
        assert out["composite_structural_score"] == pytest.approx(by_hand, abs=1e-6)

    def test_formula_is_published_in_the_output(self):
        out = score_findings([])
        assert out["composite_formula"] == COMPOSITE_FORMULA
        assert "mean(" in out["composite_formula"]

    def test_composite_reconstructable_from_the_vector(self):
        out = score_findings([finding("PROC-001", "procurement"),
                              finding("ENT-003", "entity")])
        vector = [v["score"] for v in out["sub_scores"].values()]
        assert out["composite_structural_score"] == pytest.approx(
            sum(vector) / len(vector), abs=1e-6)

    def test_vector_reconstructable_from_the_rules(self):
        """Decomposition integrity, one level down: each sub-score's raw weight
        must equal the sum of its own decomposition's contributions."""
        out = score_findings([finding("PROC-001", "procurement"),
                              finding("PROC-002", "procurement", "medium"),
                              finding("TIME-001", "temporal")])
        for sub in out["sub_scores"].values():
            assert sub["raw_weight"] == pytest.approx(
                sum(f["contribution"] for f in sub["decomposition"]))

    def test_every_finding_appears_in_exactly_one_sub_score(self):
        findings = [finding("PROC-001", "procurement"), finding("FIN-001", "financial"),
                    finding("TIME-001", "temporal"), finding("ENT-003", "entity")]
        out = score_findings(findings)
        placed = [f["rule_id"] for s in out["sub_scores"].values()
                  for f in s["decomposition"]]
        assert sorted(placed) == sorted(f["rule_id"] for f in findings)


# ═══════════════════════════════════════════════════════════
# TIER 3 — CONFIGURABLE BANDS
# ═══════════════════════════════════════════════════════════


class TestBands:

    def test_default_cutoffs_are_the_documented_values(self):
        assert DEFAULT_CUTOFFS.green_below == 0.3
        assert DEFAULT_CUTOFFS.red_at_or_above == 0.6

    @pytest.mark.parametrize("score,band", [
        (0.0, "GREEN"), (0.29, "GREEN"), (0.3, "YELLOW"),
        (0.59, "YELLOW"), (0.6, "RED"), (1.0, "RED"),
    ])
    def test_band_boundaries(self, score, band):
        assert DEFAULT_CUTOFFS.band_for(score) == band

    def test_changing_cutoffs_changes_the_band_not_the_score(self):
        """THE POINT OF TIER 3. SUNLIGHT reports the number; the institution
        decides where the lines fall."""
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        default = score_findings(findings)
        strict = score_findings(findings, cutoffs=BandCutoffs(green_below=0.05,
                                                              red_at_or_above=0.1))
        assert default["composite_structural_score"] == strict["composite_structural_score"]
        assert default["interpretation_band"] != strict["interpretation_band"]

    def test_cutoffs_used_are_stated_in_the_output(self):
        out = score_findings([], cutoffs=BandCutoffs(green_below=0.2, red_at_or_above=0.7))
        assert out["band_cutoffs"]["green_below"] == 0.2
        assert out["band_cutoffs"]["red_at_or_above"] == 0.7

    def test_inverted_cutoffs_are_reported_as_a_problem(self):
        problems = BandCutoffs(green_below=0.8, red_at_or_above=0.2).validate()
        assert any("inverted" in p for p in problems)

    def test_out_of_range_cutoffs_are_reported(self):
        assert BandCutoffs(green_below=-1.0).validate()
        assert BandCutoffs(red_at_or_above=5.0).validate()

    def test_valid_cutoffs_produce_no_warnings(self):
        assert BandCutoffs(green_below=0.25, red_at_or_above=0.75).validate() == []


# ═══════════════════════════════════════════════════════════
# FAZEKAS CRI MAPPING
# ═══════════════════════════════════════════════════════════


class TestFazekasMapping:

    def test_seven_flags_defined(self):
        assert len(FAZEKAS_FLAGS) == 7
        assert set(FAZEKAS_FLAGS) == {"F1", "F2", "F3", "F4", "F5", "F6", "F7"}

    def test_missing_competitive_process_confirms_f1_and_f3(self):
        """The spec's headline mapping."""
        m = fazekas_mapping_for("PROC-001")
        assert set(m.flags) == {"F1", "F3"}
        assert m.relationship == RELATIONSHIP_CONFIRMS
        assert "CONFIRMS" in m.note

    def test_single_bidding_confirms_f1(self):
        m = fazekas_mapping_for("PROC-002")
        assert m.flags == ("F1",)
        assert m.relationship == RELATIONSHIP_CONFIRMS

    def test_concentration_confirms_f7(self):
        m = fazekas_mapping_for("ENT-003")
        assert m.flags == ("F7",)
        assert m.relationship == RELATIONSHIP_CONFIRMS

    def test_fiscal_clustering_is_related_to_f6_not_identical(self):
        """Do not overclaim. F6 measures the decision interval; TIME-001
        measures fiscal-calendar clustering."""
        m = fazekas_mapping_for("TIME-001")
        assert m.flags == ("F6",)
        assert m.relationship == RELATIONSHIP_RELATED
        assert m.relationship != RELATIONSHIP_CONFIRMS
        assert "not identical" in m.note

    def test_oversight_finding_has_no_cri_counterpart(self):
        m = fazekas_mapping_for("PROC-003")
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE
        assert "NO corresponding CRI indicator" in m.note

    @pytest.mark.parametrize("rule_id", ["ENT-001", "ENT-002", "FIN-001", "GEO-001"])
    def test_structural_only_findings_map_to_nothing(self, rule_id):
        """These are the risks an indicator-based index cannot see."""
        m = fazekas_mapping_for(rule_id)
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE

    @pytest.mark.parametrize("rule_id", ["DEL-MILE-001", "EVD-CON-003", "REC-001"])
    def test_other_sides_are_beyond_the_paradigm(self, rule_id):
        """Side 2 delivery, Side 5 evidence and Side 4 recovery findings have
        no CRI counterpart by construction: the index describes a procurement
        event, these describe what happened afterwards."""
        m = fazekas_mapping_for(rule_id)
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE
        assert "beyond the indicator paradigm" in m.note

    def test_unknown_rule_maps_to_nothing_rather_than_guessing(self):
        """A wrong confirmation tells an institution its index covers a risk
        it does not cover. Silence is the safe failure."""
        m = fazekas_mapping_for("TOTALLY-UNKNOWN-999")
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE

    def test_empty_rule_id_maps_to_nothing(self):
        assert fazekas_mapping_for("").flags == ()

    def test_every_mapped_flag_is_a_real_flag(self):
        for m in RULE_FAZEKAS_MAP.values():
            for f in m.flags:
                assert f in FAZEKAS_FLAGS

    def test_relationship_is_always_one_of_three(self):
        for m in RULE_FAZEKAS_MAP.values():
            assert m.relationship in (RELATIONSHIP_CONFIRMS, RELATIONSHIP_RELATED,
                                      RELATIONSHIP_NONE)

    def test_mapping_with_no_flags_is_never_labelled_confirms(self):
        """A confirmation with nothing to confirm would be incoherent."""
        for rule_id, m in RULE_FAZEKAS_MAP.items():
            if not m.flags:
                assert m.relationship == RELATIONSHIP_NONE, rule_id

    def test_flags_never_confirmed_are_disclosed(self):
        """Four of the seven flags are never CONFIRMED, and for two different
        reasons — a distinction that matters to an institution reading this.

        F2, F4 and F5 concern publication and evaluation-criteria attributes
        the structural engine does not model at all: no rule touches them.

        F6 is different. Two temporal rules map to it, but only as RELATED —
        F6 measures the decision interval while SUNLIGHT measures
        fiscal-calendar clustering. Deliberately not upgraded to a
        confirmation, per the conservative mapping discipline.
        """
        never = flags_never_confirmed()
        assert set(never) == {"F2", "F4", "F5", "F6"}

        unmapped = {f for f in FAZEKAS_FLAGS
                    if not any(f in m.flags for m in RULE_FAZEKAS_MAP.values())}
        assert unmapped == {"F2", "F4", "F5"}

        related_only = set(never) - unmapped
        assert related_only == {"F6"}
        assert all(fazekas_mapping_for(r).relationship == RELATIONSHIP_RELATED
                   for r in ("TIME-001", "TIME-002"))

    def test_output_lists_confirmed_flags_and_blind_findings(self):
        out = score_findings([finding("PROC-001", "procurement"),
                              finding("GEO-001", "network")])
        assert [f["flag"] for f in out["cri_confirmed_flags"]] == ["F1", "F3"]
        assert [b["rule_id"] for b in out["cri_blind_findings"]] == ["GEO-001"]

    def test_every_finding_declares_a_mapping(self):
        """No finding may be silent about its CRI correspondence."""
        out = score_findings([finding("PROC-001", "procurement"),
                              finding("FIN-001", "financial"),
                              finding("TIME-001", "temporal")])
        for f in out["findings"]:
            assert "fazekas_mapping" in f
            assert f["fazekas_mapping"]["relationship"] in ("confirms", "related", "none")


# ═══════════════════════════════════════════════════════════
# THE BOEING DEMO CASE
# ═══════════════════════════════════════════════════════════


class TestBoeingDemoCase:
    """US v Boeing (2006), DOJ-prosecuted, $615M, 450% markup on spare parts.

    The demonstration case. It has to render the pitch: a real prosecuted
    contract producing a decomposed score, confirming flags the institution's
    own index already carries, AND surfacing at least one risk that index
    cannot see.
    """

    def _scoring(self, client):
        return client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]

    def test_it_analyses(self, client):
        assert client.post("/analyze", json=BOEING_LIKE).status_code == 200

    def test_scoring_is_present_regardless_of_band(self, client):
        """The resolution of the old single-contract limitation: the response
        is complete whether or not a verdict 'fires'."""
        s = self._scoring(client)
        assert s is not None
        assert "composite_structural_score" in s
        assert 0.0 <= s["composite_structural_score"] <= 1.0

    def test_procedural_risk_is_detected(self, client):
        s = self._scoring(client)
        assert s["sub_scores"]["procedural_score"]["score"] > 0.0

    def test_it_confirms_cri_flags_the_institution_already_trusts(self, client):
        s = self._scoring(client)
        confirmed = {f["flag"] for f in s["cri_confirmed_flags"]}
        assert {"F1", "F3"} <= confirmed

    def test_the_composite_is_the_mean_of_its_vector(self, client):
        s = self._scoring(client)
        vector = [v["score"] for v in s["sub_scores"].values()]
        assert s["composite_structural_score"] == pytest.approx(
            sum(vector) / len(vector), abs=1e-6)

    def test_every_finding_names_its_rule_and_citation(self, client):
        """The pitch depends on this: a score an institution can trace to a
        statute, not a number from a black box."""
        s = self._scoring(client)
        assert s["findings"]
        for f in s["findings"]:
            assert f["rule_id"]
            assert f["rule_name"]
            assert f["legal_citation"]
            assert f["contribution"] > 0

    def test_it_is_deterministic(self, client):
        a = self._scoring(client)
        b = self._scoring(client)
        assert a == b

    def test_boeing_scores_low_structurally_and_that_is_correct(self, client):
        """THE SCOPE BOUNDARY, pinned so nobody mistakes it for a defect.

        Boeing was a PRICE fraud: 450% markup on parts with known commercial
        prices. The structural composite averages the four TCA layers and does
        not include the CRI statistical/price dimension at all — so a contract
        whose fraud lived entirely in price scores low structurally, and
        should. What catches Boeing is the CRI markup signal, reported
        separately in gate_outcome.

        The demonstration case for STRUCTURAL scoring is a structurally
        contradictory contract (see TestMultiLayerDemoCase), not this one.
        Presenting Boeing as the structural-scoring demo would misrepresent
        what the number measures.
        """
        s = self._scoring(client)
        assert s["composite_structural_score"] < 0.3
        assert s["sub_scores"]["financial_score"]["score"] == 0.0
        # The structural findings it DOES have are real and attributed.
        assert {f["rule_id"] for f in s["findings"]} == {"PROC-001", "TIME-001"}


class TestMultiLayerDemoCase:
    """The case that actually renders the pitch.

    A structurally contradictory contract: sole-source above threshold, award
    exceeding tender, fiscal year-end, bidders sharing an address, duplicate
    bidder identifiers. It exercises all four layers and — the point —
    produces findings an indicator-based index cannot see.
    """

    PAYLOAD = {
        "contract": {
            "ocid": "ocds-multilayer-demo-001",
            "buyer": {"name": "Ministry of Infrastructure", "id": "MOI-01"},
            "tender": {"title": "Road rehabilitation",
                       "value": {"amount": 10_000_000, "currency": "USD"},
                       "procurementMethod": "limited", "numberOfTenderers": 1},
            "awards": [{"id": "A1", "date": "2024-09-30",
                        "value": {"amount": 18_000_000, "currency": "USD"},
                        "suppliers": [{"name": "Alpha Ltd", "id": "V-1"}]}],
            "parties": [
                {"id": "V-1", "name": "Alpha Ltd", "roles": ["supplier", "tenderer"],
                 "address": {"countryName": "Seychelles", "streetAddress": "1 Same St"}},
                {"id": "V-2", "name": "Beta Ltd", "roles": ["tenderer"],
                 "address": {"countryName": "Seychelles", "streetAddress": "1 Same St"}},
                {"id": "V-1", "name": "Alpha Ltd Duplicate", "roles": ["tenderer"]},
                {"id": "MOI-01", "name": "Ministry of Infrastructure", "roles": ["buyer"]},
            ],
        },
        "profile": "us_federal",
    }

    def _scoring(self, client):
        return client.post("/analyze", json=self.PAYLOAD).json()["structural_scoring"]

    def test_all_four_layers_carry_signal(self, client):
        for name, sub in self._scoring(client)["sub_scores"].items():
            assert sub["score"] > 0.0, f"{name} silent"

    def test_it_confirms_flags_the_institution_already_has(self, client):
        confirmed = {f["flag"] for f in self._scoring(client)["cri_confirmed_flags"]}
        assert {"F1", "F3"} <= confirmed

    def test_it_surfaces_risks_the_cri_index_cannot_see(self, client):
        """THE PITCH. Findings with no corresponding Fazekas flag are risks an
        indicator-based method is architecturally unable to produce."""
        blind = self._scoring(client)["cri_blind_findings"]
        assert len(blind) >= 3
        ids = {b["rule_id"] for b in blind}
        assert {"FIN-001", "ENT-001", "ENT-002"} <= ids
        for b in blind:
            assert "NO corresponding CRI indicator" in b["note"]

    def test_composite_is_the_mean_and_reconstructable(self, client):
        s = self._scoring(client)
        vector = [v["score"] for v in s["sub_scores"].values()]
        assert s["composite_structural_score"] == pytest.approx(
            sum(vector) / len(vector), abs=1e-6)

    def test_every_finding_is_fully_attributed(self, client):
        for f in self._scoring(client)["findings"]:
            assert f["rule_id"] and f["rule_name"] and f["legal_citation"]
            assert f["fazekas_mapping"]["relationship"] in ("confirms", "related", "none")

    def test_it_is_deterministic(self, client):
        assert self._scoring(client) == self._scoring(client)


# ═══════════════════════════════════════════════════════════
# ADDITIVITY AND API INTEGRATION
# ═══════════════════════════════════════════════════════════


class TestAdditive:

    def test_scoring_never_changes_the_verdict(self, client):
        """The layer is consulted by nothing. Verdicts, confidence and the
        gate outcome must be exactly what they were before it existed."""
        body = json.load(open(os.path.join(os.path.dirname(__file__), '..',
                                           'handover/samples/flagged_contract.json')))
        d = client.post("/analyze", json=body).json()
        assert d["gate_verdict"] == "yellow"
        assert d["structure"]["verdict"] == "compromised"
        assert d["structure"]["confidence"] == 0.55

    def test_scoring_module_reads_no_engine(self):
        """It re-expresses findings; it must not compute detection."""
        import ast
        import inspect

        import structural_scoring
        tree = ast.parse(inspect.getsource(structural_scoring))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        # tca_rules is read for the layer denominators only — no engine,
        # no pipeline, no gate.
        assert not any(m.startswith(("evg", "cri", "institutional_", "doj_",
                                     "evaluation", "tca_analyzer", "tca_procurement"))
                       for m in imported), imported

    def test_clean_contract_scores_zero_and_reports_it(self, client):
        body = json.load(open(os.path.join(os.path.dirname(__file__), '..',
                                           'handover/samples/clean_contract.json')))
        s = client.post("/analyze", json=body).json()["structural_scoring"]
        assert s["composite_structural_score"] == 0.0
        assert s["findings"] == []
        assert s["cri_confirmed_flags"] == []

    def test_response_carries_all_specified_keys(self, client):
        s = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        for key in ("composite_structural_score", "composite_formula", "sub_scores",
                    "interpretation_band", "band_cutoffs", "findings",
                    "cri_confirmed_flags", "cri_blind_findings"):
            assert key in s, f"missing {key}"

    def test_methodology_note_states_it_is_not_detection(self, client):
        s = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        assert "not participate in detection" in s["methodology_note"]
        assert "not an allegation" in s["methodology_note"]
