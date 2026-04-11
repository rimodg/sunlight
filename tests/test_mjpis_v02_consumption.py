"""
Tests for MJPIS v0.2 derivation and FIN-001 consumption path.
==============================================================

These tests lock in the sub-task 2.3.7 minimum-viable increment:
the first real multi-jurisdiction engine consumption of a corpus-
derived parameter.

Two assertions matter:

1. `derive_mjpis_parameters()` returns a GlobalParameters instance
   whose `markup_floor_ratio` is populated from the corpus (not the
   hardcoded default), whose `derivation_metadata` carries a methodology
   version string of "mjpis_v0.2", and whose contributing-case list
   includes at least one DOJ markup-based case (DynCorp 2005 is the
   empirical floor in the seed corpus).

2. FIN-001, built against a JurisdictionProfile that references
   `mjpis_draft_v0`, emits an edge description that includes the
   MJPIS provenance trail (methodology version + contributing case
   ID) when Check B trips — i.e. when the award/tender ratio crosses
   the empirical markup floor. Under `us_federal_v0` (default DOJ
   profile), this provenance path is silent because
   `derivation_metadata` is empty, so the rule emits the legacy
   description byte-identically.

Run with:  pytest tests/test_mjpis_v02_consumption.py -v
"""

from dataclasses import replace

import pytest

from mjpis_derivation import get_derived_mjpis
from global_parameters import US_FEDERAL_V0, MJPIS_DRAFT_V0
from jurisdiction_profile import US_FEDERAL
from tca_rules import build_rules


class TestMjpisV02Derivation:
    """The derivation function produces a real per-dimension provenance trail."""

    def test_derivation_produces_provenance(self):
        """`derive_mjpis_parameters` populates markup_floor_ratio and metadata.

        After Phase B session 2 case 2 (Tesco 2017) landed in the corpus,
        the UK SFO per-jurisdiction floor (0.501 = Tesco's overstatement
        ratio) undercuts the US DOJ per-jurisdiction floor (0.75 = DynCorp
        2005), so the intersection floor tightens to 0.501. Both DynCorp
        and Tesco appear in `contributing_cases` as per-jurisdiction floor
        setters (audit trail records every jurisdiction's floor setter).
        """
        gp = get_derived_mjpis()

        # markup_floor_ratio is set from the intersection. After Tesco 2017
        # landed in the corpus, the UK SFO floor (0.501) undercuts the US
        # DOJ floor (0.75), so the intersection tightens to 0.501.
        assert gp.markup_floor_ratio == 0.501, (
            f"Expected markup_floor_ratio=0.501 (Tesco 2017 UK SFO floor), "
            f"got {gp.markup_floor_ratio}"
        )

        # derivation_metadata is non-empty and carries methodology version
        assert gp.derivation_metadata, (
            "Expected derivation_metadata to be populated with provenance trail, "
            "got empty dict"
        )
        assert gp.derivation_metadata.get("methodology_version") == "mjpis_v0.2", (
            f"Expected methodology_version='mjpis_v0.2', got "
            f"{gp.derivation_metadata.get('methodology_version')!r}"
        )

        # Provenance structure: per-jurisdiction floors, intersection, contributing cases
        floor_info = gp.derivation_metadata.get("markup_floor_derivation", {})
        assert "per_jurisdiction" in floor_info
        assert "intersection_floor" in floor_info
        assert "contributing_cases" in floor_info

        # Both US DOJ and UK SFO set per-jurisdiction floors (DynCorp 2005
        # at 0.75 and Tesco 2017 at 0.501 respectively).
        assert "US_DOJ" in floor_info["per_jurisdiction"]
        assert "UK_SFO" in floor_info["per_jurisdiction"]
        assert floor_info["per_jurisdiction"]["US_DOJ"] == 0.75
        assert floor_info["per_jurisdiction"]["UK_SFO"] == 0.501
        assert floor_info["intersection_floor"] == 0.501

        # Both DynCorp 2005 and Tesco 2017 are contributing cases (one
        # per-jurisdiction floor setter each).
        contributing_case_ids = {c["case_id"] for c in floor_info["contributing_cases"]}
        assert "US_v_DynCorp_2005" in contributing_case_ids, (
            f"Expected DynCorp 2005 among contributing_cases, got {contributing_case_ids}"
        )
        assert "UK_SFO_Tesco_2017" in contributing_case_ids, (
            f"Expected Tesco 2017 among contributing_cases, got {contributing_case_ids}"
        )

        # corpus_version + jurisdictions_considered are captured
        assert "corpus_version" in gp.derivation_metadata
        assert "jurisdictions_considered" in gp.derivation_metadata
        assert "US_DOJ" in gp.derivation_metadata["jurisdictions_considered"]
        assert "UK_SFO" in gp.derivation_metadata["jurisdictions_considered"]


class TestFin001ConsumesMjpisProvenance:
    """FIN-001 emits MJPIS provenance under mjpis_draft_v0, legacy under DOJ."""

    def test_fin001_evidence_includes_provenance_under_mjpis_path(self):
        """Under an MJPIS-referencing profile, Check B tripping yields provenance."""
        # Build an MJPIS-referencing profile by swapping the global_params_version
        # on US_FEDERAL. All other jurisdictional locals (legal citations, fiscal
        # calendar, max_award_inflation_pct) are preserved.
        mjpis_profile = replace(US_FEDERAL, global_params_version="mjpis_draft_v0")

        rules = build_rules(mjpis_profile)
        fin001 = next(r for r in rules if r.rule_id == "FIN-001")

        # Synthesize a contract whose award/tender ratio is 2.0 (100% markup).
        # Under US_FEDERAL, this trips Check A (>15%) AND Check B (>75%).
        feature = {
            "tender_value": 100_000,
            "award_value": 200_000,
            "currency": "USD",
        }

        assert fin001.condition(feature) is True

        edges = fin001.edges(feature)
        assert len(edges) == 1
        description = edges[0]["description"]

        # Provenance branch fires because Check B tripped AND derivation_metadata
        # on mjpis_draft_v0 is populated
        assert "mjpis_v0.2" in description, (
            f"Expected methodology version 'mjpis_v0.2' in description, got:\n{description}"
        )
        assert "US_v_DynCorp_2005" in description, (
            f"Expected contributing case 'US_v_DynCorp_2005' in description, got:\n{description}"
        )
        assert "MJPIS empirical markup floor" in description

    def test_fin001_evidence_is_legacy_under_doj_path(self):
        """Under US_FEDERAL (us_federal_v0), the provenance branch stays silent."""
        rules = build_rules(US_FEDERAL)
        fin001 = next(r for r in rules if r.rule_id == "FIN-001")

        # Same high-ratio contract: ratio 2.0 trips both Check A and Check B,
        # but derivation_metadata on us_federal_v0 is empty, so the provenance
        # branch does NOT fire and the legacy description is emitted byte-identically.
        feature = {
            "tender_value": 100_000,
            "award_value": 200_000,
            "currency": "USD",
        }

        assert fin001.condition(feature) is True

        description = fin001.edges(feature)[0]["description"]

        # Legacy branch: no MJPIS provenance strings
        assert "mjpis_v0.2" not in description
        assert "MJPIS empirical markup floor" not in description
        assert "US_v_DynCorp_2005" not in description

        # Legacy description is byte-identical to the pre-2.3.7 output
        expected_legacy = (
            "Award (USD 200,000) exceeds tender (USD 100,000) by 100.0%"
        )
        assert description == expected_legacy, (
            f"Legacy description drift detected.\n"
            f"  expected: {expected_legacy!r}\n"
            f"  got:      {description!r}"
        )

    def test_mjpis_draft_v0_has_populated_metadata(self):
        """MJPIS_DRAFT_V0 registered at import time carries the provenance trail.

        After Tesco 2017 landed, the MJPIS draft floor tightens to 0.501.
        """
        assert MJPIS_DRAFT_V0.markup_floor_ratio == 0.501
        assert MJPIS_DRAFT_V0.derivation_metadata.get("methodology_version") == "mjpis_v0.2"

    def test_us_federal_v0_has_empty_metadata(self):
        """US_FEDERAL_V0 stays empty of derivation metadata (hardcoded calibration)."""
        assert US_FEDERAL_V0.markup_floor_ratio == 0.75  # dataclass default
        assert US_FEDERAL_V0.derivation_metadata == {}
