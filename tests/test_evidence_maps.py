"""
Tests for SUNLIGHT Side 5 — Country Evidence Maps and Profile Extension.

Covers the jurisdiction-awareness layer: the profile fields, the JSON
loader, the shipped ng.json and ua.json maps, and — most importantly — that
a jurisdiction's declared reachability actually governs what can be found
there.

The load-bearing test is test_ukraine_missing_monitor_is_not_a_finding.
Ukraine's map declares field verification unreachable because monitor site
access is security-constrained. A genuine facility in a contested oblast
cannot produce a monitor visit, so the absence of one must produce no
finding at all. That is the whole purpose of per-jurisdiction maps, and it
is verified end-to-end through the real pipeline rather than asserted.
"""

import json
import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evidence_maps import (
    STATUS_ILLUSTRATIVE,
    STATUS_VALIDATED,
    CountryEvidenceProfile,
    available_evidence_maps,
    load_evidence_map,
    parse_evidence_map,
)
from evidence_pipeline import EvidencePipeline, resolve_expected_evidence
from evidence_schema import (
    CorroborationVerdict,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceStatus,
    OutcomeClaim,
    OutcomeType,
    Provenance,
    SourceIndependence,
)
from jurisdiction_profile import (
    _EVIDENCE_CLASS_VALUES,
    FRANCE_PNF,
    UK_CENTRAL_GOVERNMENT,
    US_FEDERAL,
    WB_INT,
    JurisdictionProfile,
)


MAP_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'evidence_maps')
ALL_PROFILES = [US_FEDERAL, UK_CENTRAL_GOVERNMENT, WB_INT, FRANCE_PNF]


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def prov():
    return Provenance("s", "S", datetime(2025, 4, 1, tzinfo=timezone.utc), "a" * 64)


def art(aid, cls, status=EvidenceStatus.OBSERVED, party=None, observed_date=None):
    return EvidenceArtifact(
        artifact_id=aid, evidence_class=cls, claim_id="C1",
        description=f"artifact {aid}", status=status,
        observed_date=observed_date, provenance=prov(), source_party_id=party,
    )


def src(pid, contract_party=False):
    return SourceIndependence(pid, pid, "government_agency",
                              is_contract_party=contract_party)


def claim(country="ng", outcome=OutcomeType.FACILITY_CONSTRUCTION):
    return OutcomeClaim(
        claim_id="C1", contract_id="K1", outcome_type=outcome,
        claim_description="200-bed hospital operational",
        claimed_completion_date=date(2025, 3, 1),
        claimed_magnitude=200.0, claimed_magnitude_unit="beds",
        country_code=country, award_date=date(2024, 1, 15),
    )


# ═══════════════════════════════════════════════════════════
# SECTION 1: PROFILE EXTENSION
# ═══════════════════════════════════════════════════════════


class TestProfileExtension:

    def test_evidence_fields_exist_with_conservative_defaults(self):
        p = JurisdictionProfile(name="test")
        assert p.min_independent_classes == 3
        assert p.min_queryable_classes == 3
        assert p.min_corroboration_capacity == 0.5
        assert p.timeline_tolerance_days == 90
        assert p.magnitude_tolerance == 0.20
        assert p.beneficiary_tolerance == 0.25
        assert p.field_verification_window_months == 6
        assert p.evidence_freshness_months == 18
        assert p.geotag_tolerance_meters == 250.0

    def test_collection_fields_default_empty(self):
        p = JurisdictionProfile(name="test")
        assert p.queryable_classes == []
        assert p.expected_evidence_maps == {}
        assert p.evidence_legal_citations == {}

    def test_defaults_are_not_shared_between_instances(self):
        """Classic dataclass trap. A shared mutable default would let one
        jurisdiction's evidence map leak into every other."""
        a = JurisdictionProfile(name="a")
        b = JurisdictionProfile(name="b")
        a.queryable_classes.append("geospatial")
        assert b.queryable_classes == []

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_shipped_profiles_still_validate(self, profile):
        """Purely additive: the four existing profiles gain the fields and
        must not gain warnings."""
        evidence_warnings = [
            w for w in profile.validate()
            if any(k in w for k in ("corroboration", "queryable_classes",
                                    "min_independent_classes"))
        ]
        assert evidence_warnings == []

    @pytest.mark.parametrize("profile", ALL_PROFILES)
    def test_shipped_profiles_declare_no_reachability(self, profile):
        """Empty means UNKNOWN, not NONE. These are procurement jurisdictions
        with no evidence landscape declared; reachability is then derived from
        what the sources actually returned, rather than declaring the country
        unverifiable."""
        assert profile.queryable_classes == []

    def test_profile_class_values_match_the_enum(self):
        """jurisdiction_profile deliberately does NOT import evidence_schema —
        that would invert the dependency and make Side 5 unremovable. The cost
        is that the two lists can drift, so this test is the seam that fails
        if they ever do."""
        assert _EVIDENCE_CLASS_VALUES == {c.value for c in EvidenceClass}


class TestProfileValidation:

    def test_capacity_floor_of_zero_is_warned(self):
        """Disabling the floor makes adverse verdicts available in
        jurisdictions where nothing is reachable."""
        p = JurisdictionProfile(name="x", min_corroboration_capacity=0.0)
        assert any("capacity floor" in w for w in p.validate())

    def test_capacity_outside_range_is_warned(self):
        p = JurisdictionProfile(name="x", min_corroboration_capacity=1.5)
        assert any("outside [0.0, 1.0]" in w for w in p.validate())

    def test_unreachable_verified_threshold_is_warned(self):
        p = JurisdictionProfile(name="x", min_independent_classes=9)
        assert any("VERIFIED would be unreachable" in w for w in p.validate())

    def test_impossible_queryable_minimum_is_warned(self):
        p = JurisdictionProfile(name="x", min_queryable_classes=9)
        assert any("fire on every claim" in w for w in p.validate())

    def test_unrecognised_class_is_warned(self):
        p = JurisdictionProfile(name="x", queryable_classes=["satellite"])
        assert any("unrecognised" in w for w in p.validate())

    def test_valid_evidence_config_produces_no_evidence_warnings(self):
        p = JurisdictionProfile(
            name="x",
            queryable_classes=["geospatial", "institutional"],
            min_corroboration_capacity=0.5,
        )
        assert not any("queryable_classes" in w for w in p.validate())


# ═══════════════════════════════════════════════════════════
# SECTION 2: THE LOADER
# ═══════════════════════════════════════════════════════════


class TestLoader:

    def test_both_maps_ship(self):
        assert available_evidence_maps(MAP_DIR) == ["ng", "ua"]

    def test_filenames_follow_the_cpd_convention(self):
        """ISO-2 lowercase, matching data/cpd_profiles/ exactly. The same
        country codes flow through both, and a second convention would
        guarantee mismatches."""
        cpd_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cpd_profiles')
        cpd_codes = sorted(
            os.path.splitext(f)[0] for f in os.listdir(cpd_dir) if f.endswith('.json'))
        assert available_evidence_maps(MAP_DIR) == cpd_codes

    def test_load_is_case_insensitive(self):
        assert load_evidence_map("NG", MAP_DIR).country_code == "ng"

    def test_missing_country_returns_none_not_an_error(self):
        """None means SUNLIGHT has no declared expectations here. Stage 14
        then resolves none, no absence rule can fire, and the analysis
        reports what the evidence shows without inventing a standard the
        country never agreed to."""
        assert load_evidence_map("zz", MAP_DIR) is None

    def test_missing_directory_lists_nothing(self):
        assert available_evidence_maps("/nonexistent/path") == []

    def test_parameters_override_defaults(self):
        p = parse_evidence_map({
            "country_code": "xx",
            "parameters": {"magnitude_tolerance": 0.05},
        })
        assert p.magnitude_tolerance == 0.05

    def test_unknown_parameter_keys_are_ignored(self):
        """A stray key in a country map must not crash analysis for that
        country."""
        p = parse_evidence_map({
            "country_code": "xx",
            "parameters": {"not_a_real_parameter": 1},
        })
        assert not hasattr(p, "not_a_real_parameter")

    def test_empty_document_parses(self):
        p = parse_evidence_map({})
        assert p.country_code == ""
        assert p.expectations_for("facility_construction") == []


# ═══════════════════════════════════════════════════════════
# SECTION 3: THE SHIPPED MAPS
# ═══════════════════════════════════════════════════════════


class TestShippedMaps:

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_map_is_valid_json_and_loads(self, code):
        assert load_evidence_map(code, MAP_DIR) is not None

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_map_is_marked_illustrative(self, code):
        """These encode a plausible evidence landscape, not a validated one.
        Nothing downstream may mistake them for country-office ground truth."""
        p = load_evidence_map(code, MAP_DIR)
        assert p.status == STATUS_ILLUSTRATIVE
        assert p.is_validated() is False

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_map_says_so_in_its_own_source_note(self, code):
        p = load_evidence_map(code, MAP_DIR)
        assert "ILLUSTRATIVE" in p.source_note

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_validate_flags_the_unvalidated_status(self, code):
        p = load_evidence_map(code, MAP_DIR)
        assert any("not been validated" in w for w in p.validate())

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_required_outcome_types_are_seeded(self, code):
        p = load_evidence_map(code, MAP_DIR)
        for outcome in ("facility_construction", "infrastructure_linear",
                        "service_delivery"):
            assert p.expectations_for(outcome), f"{code}: {outcome} missing"

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_every_expectation_names_a_real_evidence_class(self, code):
        p = load_evidence_map(code, MAP_DIR)
        valid = {c.value for c in EvidenceClass}
        for outcome, entries in p.expected_evidence_maps.items():
            for entry in entries:
                assert entry["evidence_class"] in valid, f"{code}/{outcome}"

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_every_expectation_has_a_stable_id_and_description(self, code):
        p = load_evidence_map(code, MAP_DIR)
        seen = set()
        for entries in p.expected_evidence_maps.values():
            for entry in entries:
                assert entry["expectation_id"] not in seen
                seen.add(entry["expectation_id"])
                assert entry["description"].strip()

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_expected_by_month_is_present_everywhere(self, code):
        """EVD-CON-001 anchors on this. Without it there is no timeline
        window, and the rule silently cannot fire."""
        p = load_evidence_map(code, MAP_DIR)
        for entries in p.expected_evidence_maps.values():
            for entry in entries:
                assert entry.get("expected_by_month") is not None

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_declared_classes_are_consistent_with_expectations(self, code):
        """An expectation marked queryable in a class the jurisdiction does
        not list as reachable would be a contradiction inside the map."""
        p = load_evidence_map(code, MAP_DIR)
        for entries in p.expected_evidence_maps.values():
            for entry in entries:
                if entry.get("queryable_in_jurisdiction", True):
                    assert entry["evidence_class"] in p.queryable_classes

    @pytest.mark.parametrize("code", ["ng", "ua"])
    def test_capacity_clears_the_floor(self, code):
        """Both shipped maps must permit an adverse conclusion; otherwise the
        maps would be untestable against any contradiction scenario."""
        p = load_evidence_map(code, MAP_DIR)
        assert p.capacity_ceiling() >= p.min_corroboration_capacity

    def test_the_two_maps_genuinely_differ(self):
        """Jurisdiction-awareness is only real if jurisdictions differ. If
        both maps were identical, the whole mechanism would be decoration."""
        ng = load_evidence_map("ng", MAP_DIR)
        ua = load_evidence_map("ua", MAP_DIR)
        assert set(ng.queryable_classes) != set(ua.queryable_classes)

    def test_ukraine_declares_field_verification_unreachable(self):
        """Monitor site access is security-constrained. No verification
        system can wish that away, and pretending otherwise would penalise
        every project in a contested oblast."""
        ua = load_evidence_map("ua", MAP_DIR)
        assert "field_verification" not in ua.queryable_classes
        assert ua.capacity_ceiling() == pytest.approx(5 / 6)

    def test_nigeria_declares_all_six_reachable(self):
        ng = load_evidence_map("ng", MAP_DIR)
        assert ng.capacity_ceiling() == 1.0

    def test_maps_are_pretty_printed_for_review(self):
        """Country offices have to read and correct these. A single-line JSON
        blob is not reviewable, and an unreviewable map will not get corrected."""
        for code in ("ng", "ua"):
            with open(os.path.join(MAP_DIR, f"{code}.json"), encoding="utf-8") as f:
                assert len(f.readlines()) > 20


class TestMapValidation:

    def test_expectation_outside_declared_reachability_is_warned(self):
        p = parse_evidence_map({
            "country_code": "xx",
            "queryable_classes": ["institutional"],
            "expected_evidence_maps": {
                "facility_construction": [
                    {"expectation_id": "X1", "evidence_class": "geospatial",
                     "description": "imagery"},
                ]
            },
        })
        assert any("does not list as queryable" in w for w in p.validate())

    def test_unknown_class_in_expectations_is_warned(self):
        p = parse_evidence_map({
            "country_code": "xx",
            "expected_evidence_maps": {
                "facility_construction": [
                    {"expectation_id": "X1", "evidence_class": "telepathy",
                     "description": "vibes"},
                ]
            },
        })
        assert any("unrecognised evidence_class" in w for w in p.validate())

    def test_validated_map_produces_no_status_warning(self):
        p = CountryEvidenceProfile(country_code="xx", status=STATUS_VALIDATED)
        assert not any("not been validated" in w for w in p.validate())

    def test_invalid_classes_are_dropped_from_capacity(self):
        p = CountryEvidenceProfile(
            country_code="xx",
            queryable_classes=["geospatial", "telepathy"],
        )
        assert p.valid_queryable_classes() == ["geospatial"]
        assert p.capacity_ceiling() == pytest.approx(1 / 6)


# ═══════════════════════════════════════════════════════════
# SECTION 4: THE MAPS DRIVING REAL ANALYSIS
# ═══════════════════════════════════════════════════════════


class TestMapsGovernAnalysis:

    def test_expectations_resolve_from_a_loaded_map(self):
        ng = load_evidence_map("ng", MAP_DIR)
        resolved = resolve_expected_evidence(claim(), profile=ng)
        assert [e.expectation_id for e in resolved][:2] == ["NG-FC-01", "NG-FC-02"]

    def test_a_different_outcome_type_resolves_a_different_set(self):
        ng = load_evidence_map("ng", MAP_DIR)
        service = resolve_expected_evidence(
            claim(outcome=OutcomeType.SERVICE_DELIVERY), profile=ng)
        assert all(e.expectation_id.startswith("NG-SD") for e in service)

    def test_unmapped_outcome_type_resolves_to_nothing(self):
        ng = load_evidence_map("ng", MAP_DIR)
        resolved = resolve_expected_evidence(
            claim(outcome=OutcomeType.CASH_TRANSFER), profile=ng)
        assert resolved == []

    def test_ukraine_marks_field_verification_unqueryable_on_resolution(self):
        ua = load_evidence_map("ua", MAP_DIR)
        resolved = resolve_expected_evidence(claim(country="ua"), profile=ua)
        field_exp = next(
            e for e in resolved if e.evidence_class == EvidenceClass.FIELD_VERIFICATION)
        assert field_exp.queryable_in_jurisdiction is False
        assert field_exp.absence_is_meaningful is False

    def test_ukraine_missing_monitor_is_not_a_finding(self):
        """THE POINT OF PER-JURISDICTION MAPS, END TO END.

        A genuine facility in a contested oblast cannot produce an
        independent monitor visit, because monitors cannot safely reach the
        site. EVD-ABS-004 must therefore stay silent — the absence of a
        monitor visit says nothing about whether the hospital was built.

        Run through the real pipeline with the real shipped map, not a
        fixture, because this is the property the maps exist to deliver.
        """
        ua = load_evidence_map("ua", MAP_DIR)
        dossier = EvidencePipeline(profile=ua).run(
            claim=claim(country="ua"),
            artifacts=[
                art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
                art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="BUILD_CONTROL",
                    observed_date=date(2024, 5, 1)),
                art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                    observed_date=date(2025, 5, 1)),
                art("A4", EvidenceClass.BENEFICIARY_SIDE, party="EHEALTH",
                    observed_date=date(2025, 11, 1)),
                art("A5", EvidenceClass.FIELD_VERIFICATION,
                    EvidenceStatus.UNQUERYABLE, party="MONITOR"),
            ],
            source_registry=[
                src("IP", contract_party=True), src("BUILD_CONTROL"),
                src("IMAGERY"), src("EHEALTH"), src("MONITOR"),
            ],
        )
        fired = [r.rule_id for r in dossier.rules_result.rule_results if r.fired]
        assert "EVD-ABS-004" not in fired
        assert dossier.verdict != CorroborationVerdict.CONTRADICTED

    def test_the_same_claim_is_read_differently_in_the_two_countries(self):
        """Jurisdiction-awareness, demonstrated rather than asserted.

        An identical evidence submission — with no monitor visit — carries a
        different corroboration capacity in Nigeria, where monitors are
        reachable, than in Ukraine, where they are not.
        """
        artifacts = [
            art("A1", EvidenceClass.INSTITUTIONAL, party="IP"),
            art("A2", EvidenceClass.THIRD_PARTY_ADMIN, party="PERMITS",
                observed_date=date(2024, 5, 1)),
            art("A3", EvidenceClass.GEOSPATIAL, party="IMAGERY",
                observed_date=date(2025, 5, 1)),
        ]
        sources = [src("IP", contract_party=True), src("PERMITS"), src("IMAGERY")]

        ng = load_evidence_map("ng", MAP_DIR)
        ua = load_evidence_map("ua", MAP_DIR)

        ng_d = EvidencePipeline(profile=ng).run(
            claim=claim(country="ng"), artifacts=list(artifacts),
            source_registry=list(sources))
        ua_d = EvidencePipeline(profile=ua).run(
            claim=claim(country="ua"), artifacts=list(artifacts),
            source_registry=list(sources))

        assert ng_d.classes_queryable != ua_d.classes_queryable

    def test_map_tolerances_reach_the_rules(self):
        """Closure parameterisation, through the loader. Ukraine sets a
        12-month freshness window against Nigeria's 18."""
        ng = load_evidence_map("ng", MAP_DIR)
        ua = load_evidence_map("ua", MAP_DIR)
        assert ng.evidence_freshness_months == 18
        assert ua.evidence_freshness_months == 12

        from evidence_rules import build_evidence_rules
        assert len(build_evidence_rules(ua)) == 16

    def test_a_country_evidence_profile_works_as_a_pipeline_profile(self):
        ng = load_evidence_map("ng", MAP_DIR)
        dossier = EvidencePipeline(profile=ng).run(
            claim=claim(),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            source_registry=[src("P1")],
        )
        assert dossier.verdict is not None
        assert dossier.rules_result.rules_evaluated == 16


class TestMapsAreAdditive:

    def test_pipeline_works_with_no_map_at_all(self):
        """A country with no evidence map must still analyse. It resolves no
        expectations, fires no absence rules, and reports what the submitted
        evidence shows."""
        dossier = EvidencePipeline().run(
            claim=claim(country="zz"),
            artifacts=[art("A1", EvidenceClass.INSTITUTIONAL, party="P1")],
            source_registry=[src("P1")],
        )
        fired = [r.rule_id for r in dossier.rules_result.rule_results if r.fired]
        assert not any(r.startswith("EVD-ABS-") for r in fired)
        assert dossier.verdict is not None

    def test_jurisdiction_profile_does_not_import_side_5(self):
        """Dependency direction. Side 1 infrastructure must not reach into
        Side 5, or Side 5 stops being removable."""
        import ast
        import inspect

        import jurisdiction_profile

        tree = ast.parse(inspect.getsource(jurisdiction_profile))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith("evidence_"), (
                    f"jurisdiction_profile imports {name}")
                assert name != "provenance", "jurisdiction_profile imports provenance"

    def test_shipped_maps_are_data_not_code(self):
        """No executable content sneaking into a data file."""
        for code in ("ng", "ua"):
            with open(os.path.join(MAP_DIR, f"{code}.json"), encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict)
