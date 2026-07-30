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
    STATUS_INDETERMINATE,
    assess_context,
    assess_determinacy,
    corpus_stamp,
    strip_volatile,
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
        """Exact to the published precision. The by-hand procedure is fully
        specified in composite_formula: add the published sub-scores, divide by
        the count, round to 6 decimals. Rounding happens once at computation so
        the published sub-scores reconstruct the published composite exactly —
        without that, an evaluator adding the numbers lands 2.5e-7 off."""
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        subs = compute_sub_scores(findings)
        expected = round(sum(s.score for s in subs.values()) / 4, 6)
        assert compute_composite(subs) == expected

    def test_composite_matches_a_hand_calculation(self):
        """The property the formula is published for: an evaluator with a
        calculator must reach the same number."""
        findings = [finding("PROC-001", "procurement"), finding("TIME-001", "temporal")]
        out = score_findings(findings)
        by_hand = round((round(1 / 5, 6) + 0.0 + round(1 / 3, 6) + 0.0) / 4, 6)
        assert out["composite_structural_score"] == by_hand

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

    def test_no_rule_confirms_f7_because_none_measures_concentration(self):
        """CORRECTED MAPPING. ENT-003 was mapped to F7 as CONFIRMS on the
        strength of its name, "Single supplier dominance". The rule itself
        detects a single winner among three or more bidders and its own
        description calls that a "normal competitive outcome"; it emits an
        EXPRESSES edge and cannot even reach the scoring layer.

        Claiming it confirms F7 would have told an institution SUNLIGHT
        structurally verifies market concentration when no rule in the engine
        measures concentration at all.
        """
        m = fazekas_mapping_for("ENT-003")
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE
        assert "normal" in m.note.lower()
        confirmed = {f for mm in RULE_FAZEKAS_MAP.values()
                     if mm.relationship == RELATIONSHIP_CONFIRMS for f in mm.flags}
        assert "F7" not in confirmed

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

        F7 has no rule either, after the ENT-003 correction: nothing in the
        engine measures spending or market concentration.

        F6 is different. Two temporal rules map to it, but only as RELATED —
        F6 measures the decision interval while SUNLIGHT measures
        fiscal-calendar clustering. Deliberately not upgraded to a
        confirmation, per the conservative mapping discipline.
        """
        never = flags_never_confirmed()
        assert set(never) == {"F2", "F4", "F5", "F6", "F7"}

        unmapped = {f for f in FAZEKAS_FLAGS
                    if not any(f in m.flags for m in RULE_FAZEKAS_MAP.values())}
        assert unmapped == {"F2", "F4", "F5", "F7"}

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

    def test_the_composite_is_the_mean_of_its_determinate_vector(self, client):
        """Indeterminate axes are excluded from the mean, not entered as zero."""
        s = self._scoring(client)
        determinate = [v["score"] for v in s["sub_scores"].values()
                       if v["determinate"] and v["score"] is not None]
        assert s["composite_structural_score"] == pytest.approx(
            sum(determinate) / len(determinate), abs=1e-6)

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
        """Byte-identical under the canonical form. computed_at is provenance
        (when the score ran), not corpus state, and is the single declared
        volatile field."""
        assert strip_volatile(self._scoring(client)) == strip_volatile(self._scoring(client))

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
        determinate = [v["score"] for v in s["sub_scores"].values()
                       if v["determinate"] and v["score"] is not None]
        assert s["composite_structural_score"] == pytest.approx(
            sum(determinate) / len(determinate), abs=1e-6)

    def test_every_finding_is_fully_attributed(self, client):
        for f in self._scoring(client)["findings"]:
            assert f["rule_id"] and f["rule_name"] and f["legal_citation"]
            assert f["fazekas_mapping"]["relationship"] in ("confirms", "related", "none")

    def test_it_is_deterministic(self, client):
        assert strip_volatile(self._scoring(client)) == strip_volatile(self._scoring(client))


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


# ═══════════════════════════════════════════════════════════
# PHASE 1A — ISOLATION-ZERO vs COMPARED-ZERO
# ═══════════════════════════════════════════════════════════


class TestDeterminacy:
    """An axis with no basis for assessment must never render as 0.0.

    "Assessed against context and found clean" and "no basis to look" are
    epistemically opposite. Displaying them identically is the most
    misleading thing this output layer could do, and it is what it did
    before this change.
    """

    RICH = {"procurement_method": "open", "number_of_tenderers": 3,
            "has_review_body": True, "tender_value": 100.0, "award_value": 120.0,
            "award_month": 9, "award_day": 29,
            "supplier_addresses": ["a", "a"], "supplier_ids": ["x", "y"],
            "supplier_countries": ["US"], "country_code": "US"}

    BARE = {"procurement_method": "", "number_of_tenderers": None,
            "has_review_body": None, "tender_value": 0, "award_value": 0,
            "award_month": None, "award_day": None,
            "supplier_addresses": [], "supplier_ids": [], "supplier_countries": [],
            "country_code": ""}

    def test_rich_contract_is_determinate_on_all_axes(self):
        d = assess_determinacy(self.RICH)
        assert all(v["determinate"] for v in d.values())

    def test_bare_contract_is_indeterminate_on_all_axes(self):
        d = assess_determinacy(self.BARE)
        assert not any(v["determinate"] for v in d.values())

    def test_no_features_means_indeterminate_not_determinate(self):
        """The honest default. A caller who told us nothing about the contract
        gave us no basis to assess it; defaulting to determinate would
        manufacture confidence."""
        d = assess_determinacy(None)
        assert not any(v["determinate"] for v in d.values())

    def test_single_supplier_no_addresses_is_indeterminate_on_network(self):
        """THE FALSE CLEAN-ZERO, caught. One supplier with no addresses and no
        countries has NOTHING for ENT-001/ENT-002/GEO-001 to evaluate. Before
        this fix it reported network_score 0.0 with sufficient context."""
        f = dict(self.RICH, supplier_addresses=[], supplier_ids=["only-one"],
                 supplier_countries=[], country_code="")
        assert assess_determinacy(f)["network_score"]["determinate"] is False

    def test_one_value_alone_cannot_assess_financial(self):
        """FIN-001 compares tender against award. One value compares to nothing."""
        f = dict(self.RICH, tender_value=100.0, award_value=0)
        assert assess_determinacy(f)["financial_score"]["determinate"] is False

    def test_indeterminate_score_is_none_never_zero(self):
        subs = compute_sub_scores([], determinacy=assess_determinacy(self.BARE))
        for name, s in subs.items():
            assert s.score is None, f"{name} rendered {s.score} instead of None"
            assert s.determinate is False

    def test_indeterminate_axis_says_so_in_words(self):
        out = score_findings([], features=self.BARE)
        for sub in out["sub_scores"].values():
            assert sub["score"] is None
            assert sub["status"] == STATUS_INDETERMINATE
            assert sub["requires_for_assessment"]
            assert sub["rules_on_axis"]

    def test_a_fired_rule_proves_its_axis_determinate(self):
        """Evidence outranks the availability check. An axis cannot be
        indeterminate while carrying a finding — the rule fired, so its
        inputs were plainly present."""
        subs = compute_sub_scores([finding("PROC-001", "procurement")],
                                  determinacy=assess_determinacy(self.BARE))
        assert subs["procedural_score"].determinate is True
        assert subs["procedural_score"].score is not None

    def test_determinate_zero_and_indeterminate_are_distinguishable(self):
        """The whole point: a consumer must be able to tell them apart."""
        clean = score_findings([], features=self.RICH)
        unknown = score_findings([], features=self.BARE)
        clean_fin = clean["sub_scores"]["financial_score"]
        unknown_fin = unknown["sub_scores"]["financial_score"]
        assert clean_fin["score"] == 0.0 and clean_fin["determinate"] is True
        assert unknown_fin["score"] is None and unknown_fin["determinate"] is False
        assert clean_fin["status"] != unknown_fin["status"]


class TestCompositeOverDeterminateAxes:

    def test_indeterminate_axes_are_excluded_not_zeroed(self):
        """A contract determinate only on procedural, scoring 0.2 there, must
        report 0.2 — not 0.05 from averaging three phantom zeros."""
        f = dict(TestDeterminacy.BARE, procurement_method="limited")
        out = score_findings([finding("PROC-001", "procurement")], features=f)
        assert out["composite_structural_score"] == pytest.approx(0.2)

    def test_composite_is_mean_over_determinate_only(self):
        out = score_findings([finding("PROC-001", "procurement"),
                              finding("TIME-001", "temporal")],
                             features=TestDeterminacy.RICH)
        det = [v["score"] for v in out["sub_scores"].values()
               if v["determinate"] and v["score"] is not None]
        assert out["composite_structural_score"] == round(sum(det) / len(det), 6)

    def test_no_determinate_axis_yields_no_composite(self):
        """None, not 0.0. A zero here would be a fabricated clean bill."""
        out = score_findings([], features=TestDeterminacy.BARE)
        assert out["composite_structural_score"] is None
        assert out["interpretation_band"] is None
        assert "no axis was determinate" in out["band_qualification"]

    def test_composite_names_the_axes_it_used(self):
        out = score_findings([], features=TestDeterminacy.RICH)
        assert set(out["composite_computed_over"]) == set(out["sub_scores"])


class TestSingleAxisGuard:
    """A score from one axis is not the same epistemic object as one from four,
    and the output must say so rather than let a consumer assume otherwise."""

    def test_single_determinate_axis_is_flagged_low_context(self):
        f = dict(TestDeterminacy.BARE, procurement_method="limited")
        out = score_findings([finding("PROC-001", "procurement")], features=f)
        ctx = out["assessment_context"]
        assert ctx["axes_populated"] == 1
        assert ctx["low_context"] is True
        assert ctx["context_level"] == "single-axis"
        assert "LOW CONTEXT" in ctx["note"]
        assert "not a whole-contract assessment" in ctx["note"]

    def test_band_carries_the_low_context_qualification(self):
        f = dict(TestDeterminacy.BARE, procurement_method="limited")
        out = score_findings([finding("PROC-001", "procurement")], features=f)
        assert "LOW CONTEXT" in out["band_qualification"]

    def test_full_context_is_not_flagged_low(self):
        out = score_findings([], features=TestDeterminacy.RICH)
        ctx = out["assessment_context"]
        assert ctx["context_level"] == "full"
        assert ctx["low_context"] is False

    def test_reduced_context_is_named_but_not_low(self):
        f = dict(TestDeterminacy.RICH, supplier_addresses=[], supplier_ids=["one"],
                 supplier_countries=[], country_code="")
        ctx = score_findings([], features=f)["assessment_context"]
        assert ctx["context_level"] == "reduced"
        assert ctx["low_context"] is False
        assert ctx["axes_populated"] == 3

    def test_context_lists_both_sides(self):
        f = dict(TestDeterminacy.RICH, supplier_addresses=[], supplier_ids=["one"],
                 supplier_countries=[], country_code="")
        ctx = score_findings([], features=f)["assessment_context"]
        assert "network_score" in ctx["axes_indeterminate"]
        assert "network_score" not in ctx["axes_determinate"]
        assert len(ctx["axes_determinate"]) + len(ctx["axes_indeterminate"]) == 4


class TestIsolationAnnouncement:

    def test_single_contract_analyze_declares_isolation(self, client):
        s = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        assert s["isolation_assessment"] is True
        assert "isolation" in s["assessment_mode"]
        assert "SINGLE-CONTRACT (ISOLATION) ASSESSMENT" in s["isolation_note"]

    def test_isolation_note_corrects_the_comparables_misconception(self, client):
        """The four structural axes do not use comparables; the CRI price axis
        does. Stating it prevents a reader inferring the wrong reason for an
        indeterminate axis."""
        s = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        assert "do not use corpus comparables" in s["isolation_note"]

    def test_non_isolation_carries_no_isolation_note(self):
        out = score_findings([], features=TestDeterminacy.RICH, isolation=False)
        assert out["isolation_assessment"] is False
        assert out["isolation_note"] is None


# ═══════════════════════════════════════════════════════════
# PHASE 1B — CORPUS-STATE STAMPING
# ═══════════════════════════════════════════════════════════


class TestCorpusStamp:

    def test_stamp_is_present_on_every_result(self, client):
        s = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        st = s["corpus_stamp"]
        for k in ("comparison_set_size", "corpus_fingerprint",
                  "jurisdiction_profile", "jurisdiction_profile_version",
                  "computed_at"):
            assert k in st

    def test_fingerprint_is_stable_under_reordering(self):
        a = corpus_stamp(3, ["c", "a", "b"])
        b = corpus_stamp(3, ["a", "b", "c"])
        assert a["corpus_fingerprint"] == b["corpus_fingerprint"]

    def test_fingerprint_changes_when_membership_changes(self):
        """The property that makes drift attributable rather than mysterious."""
        a = corpus_stamp(3, ["a", "b", "c"])
        b = corpus_stamp(4, ["a", "b", "c", "d"])
        assert a["corpus_fingerprint"] != b["corpus_fingerprint"]

    def test_empty_comparison_set_yields_null_not_a_digest(self):
        """So "no corpus" cannot be confused with "a corpus that happened to
        hash to that value"."""
        assert corpus_stamp(0, [])["corpus_fingerprint"] is None

    def test_profile_version_is_recorded(self, client):
        st = client.post("/analyze", json=BOEING_LIKE).json()[
            "structural_scoring"]["corpus_stamp"]
        assert st["jurisdiction_profile"] == "us_federal"
        assert st["jurisdiction_profile_version"]

    def test_volatile_field_is_declared(self):
        assert corpus_stamp(0, [])["volatile_fields"] == ["computed_at"]

    def test_determinism_holds_under_the_canonical_form(self, client):
        """Same contract + same corpus state + same profile -> byte-identical."""
        a = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        b = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        assert strip_volatile(a) == strip_volatile(b)

    def test_only_computed_at_differs_between_runs(self, client):
        a = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        b = client.post("/analyze", json=BOEING_LIKE).json()["structural_scoring"]
        diff = {k for k in a["corpus_stamp"]
                if a["corpus_stamp"][k] != b["corpus_stamp"][k]}
        assert diff <= {"computed_at"}


# ═══════════════════════════════════════════════════════════
# FAZEKAS AS A LIVE OUTPUT FIELD ON EVERY SIDE
# ═══════════════════════════════════════════════════════════


class TestFazekasFieldOnEverySide:
    """The mapping ships as queryable output, not only as methodology prose.

    An institution reading ANY finding — procurement, delivery, corroboration —
    is entitled to the same answer: does my existing CRI index already cover
    this, or is this something it cannot see? The second case is the valuable
    one, and it must be stated explicitly rather than left as a null.
    """

    FLAGGED = {
        "ocid": "faz-side-1",
        "tender": {"value": {"amount": 48_500_000, "currency": "USD"},
                   "procurementMethod": "limited", "numberOfTenderers": 1},
        "awards": [{"id": "A", "date": "2024-09-29",
                    "value": {"amount": 48_500_000, "currency": "USD"},
                    "suppliers": [{"name": "V", "id": "V1"}]}],
    }

    def _shape_ok(self, fm):
        assert fm is not None, "fazekas_mapping absent"
        for k in ("flags", "flag_names", "relationship", "note"):
            assert k in fm, f"{k} missing"
        assert fm["relationship"] in ("confirms", "related", "none")
        assert fm["note"].strip()
        # A confirmation with nothing to confirm would be incoherent.
        if not fm["flags"]:
            assert fm["relationship"] == "none"

    def test_side1_analyze_findings_carry_the_field(self, client):
        d = client.post("/analyze", json={"contract": self.FLAGGED}).json()
        findings = d["structure"]["contradictions"]
        assert findings
        for f in findings:
            self._shape_ok(f["fazekas_mapping"])

    def test_side1_batch_findings_carry_the_field(self, client):
        """Parity: the field must not depend on which endpoint was called."""
        b = client.post("/batch", json={"contracts": [self.FLAGGED]}).json()
        findings = b["results"][0]["structure"]["contradictions"]
        assert findings
        for f in findings:
            self._shape_ok(f["fazekas_mapping"])

    def test_side1_confirms_the_expected_flags(self, client):
        d = client.post("/analyze", json={"contract": self.FLAGGED}).json()
        by_rule = {f["rule_id"]: f["fazekas_mapping"]
                   for f in d["structure"]["contradictions"]}
        assert set(by_rule["PROC-001"]["flags"]) == {"F1", "F3"}
        assert by_rule["PROC-001"]["relationship"] == "confirms"
        assert by_rule["TIME-001"]["flags"] == ["F6"]
        assert by_rule["TIME-001"]["relationship"] == "related"

    def test_side2_delivery_findings_map_to_none(self, client):
        """By construction: the index describes a procurement event, delivery
        findings describe what happened after it."""
        r = client.post("/delivery/analyze", json={
            "contract_id": "faz-del-1",
            "milestones": [{"milestone_id": "M1", "description": "phase 1",
                            "planned_date": "2025-01-01", "actual_date": "2025-06-01",
                            "status": "completed", "delay_days": 150}]}).json()
        fired = r.get("fired_rules") or []
        assert fired
        for f in fired:
            fm = f["fazekas_mapping"]
            self._shape_ok(fm)
            assert fm["flags"] == []
            assert fm["relationship"] == "none"
            assert "beyond the indicator paradigm" in fm["note"]

    def test_side5_evidence_findings_map_to_none(self, client):
        r = client.post("/evidence/analyze", json={
            "claim": {"claim_id": "C1", "contract_id": "K1",
                      "outcome_type": "facility_construction",
                      "claim_description": "clinic operational"},
            "artifacts": [], "source_registry": [], "profile": "us_federal"}).json()
        fires = r.get("rule_fires") or []
        assert fires
        for f in fires:
            fm = f["fazekas_mapping"]
            self._shape_ok(fm)
            assert fm["flags"] == []
            assert fm["relationship"] == "none"
            assert "beyond the indicator paradigm" in fm["note"]

    def test_the_exact_mapping_table(self):
        """The whole table, pinned. Its value is entirely in being
        conservative, so a change here must be deliberate."""
        expected = {
            "PROC-001": (("F1", "F3"), "confirms"),
            "PROC-002": (("F1",), "confirms"),
            "PROC-003": ((), "none"),
            "PROC-004": ((), "none"),
            "PROC-005": (("F1",), "related"),
            "ENT-001": ((), "none"),
            "ENT-002": ((), "none"),
            "ENT-003": ((), "none"),
            "FIN-001": ((), "none"),
            "FIN-002": ((), "none"),
            "FIN-003": ((), "none"),
            "TIME-001": (("F6",), "related"),
            "TIME-002": (("F6",), "related"),
            "TIME-003": ((), "none"),
            "GEO-001": ((), "none"),
            "GEO-002": ((), "none"),
        }
        for rule_id, (flags, rel) in expected.items():
            m = fazekas_mapping_for(rule_id)
            assert m.flags == flags, f"{rule_id} flags {m.flags} != {flags}"
            assert m.relationship == rel, f"{rule_id} rel {m.relationship} != {rel}"

    def test_only_two_flags_are_ever_confirmed(self):
        """F1 and F3. Anything more is overclaiming; a due-diligence team will
        check this against the rules."""
        confirmed = {f for m in RULE_FAZEKAS_MAP.values()
                     if m.relationship == RELATIONSHIP_CONFIRMS for f in m.flags}
        assert confirmed == {"F1", "F3"}

    def test_side4_recovery_rule_ids_map_to_none(self):
        """Side 4 has no rule engine of its own, but any REC- prefixed
        identifier must route to 'beyond the paradigm' rather than fall
        through to a default."""
        m = fazekas_mapping_for("REC-001")
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE
        assert "beyond the indicator paradigm" in m.note

    def test_a_missing_capability_style_finding_maps_to_none(self):
        """No rule measures capability. PROC-003 (no oversight body) is the
        nearest structural analogue and maps to nothing, as specified."""
        m = fazekas_mapping_for("PROC-003")
        assert m.flags == ()
        assert m.relationship == RELATIONSHIP_NONE
        assert "NO corresponding CRI indicator" in m.note
