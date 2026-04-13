"""
Tests for MJPIS intersection_v1 markup floor derivation.
=========================================================

Eight regression tests locking in the principled per-jurisdiction
extraction and intersection methodology introduced by item 20
phase two sub-task A.

Run with:  pytest tests/test_mjpis_derivation_intersection.py -v
"""

import pytest

from mjpis_derivation import (
    CORPUS_PATH,
    DerivationAuditTrail,
    InsufficientCorpusError,
    JurisdictionAnchor,
    MarkupFloorDerivation,
    derive_markup_floor_ratio,
    get_derivation_audit_trail,
    load_corpus,
)


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════


def _load_real_cases():
    """Load the current corpus cases list."""
    corpus = load_corpus(CORPUS_PATH)
    return corpus["cases"]


def _make_case(case_id, jurisdiction, markup_percentage, tags=None):
    """Build a minimal synthetic corpus case dict."""
    return {
        "case_id": case_id,
        "jurisdiction": jurisdiction,
        "markup_percentage": markup_percentage,
        "dimensional_tags": tags or ["markup_based"],
    }


# ═══════════════════════════════════════════════════════════
# Tests against the real corpus
# ═══════════════════════════════════════════════════════════


class TestRealCorpusDerivation:
    """Verify the intersection_v1 methodology against the current corpus."""

    def test_markup_floor_value_is_0_501(self):
        """The methodology produces 0.501, same as the v0.1 passthrough."""
        cases = _load_real_cases()
        result = derive_markup_floor_ratio(cases)
        assert result.value == 0.501, (
            f"Expected markup_floor_ratio=0.501 (Tesco 2017), got {result.value}"
        )

    def test_contributing_jurisdictions_are_us_doj_and_uk_sfo(self):
        """Only US_DOJ and UK_SFO have markup_based qualifying cases."""
        cases = _load_real_cases()
        result = derive_markup_floor_ratio(cases)
        assert set(result.contributing_jurisdictions) == {"US_DOJ", "UK_SFO"}, (
            f"Expected {{US_DOJ, UK_SFO}}, got {set(result.contributing_jurisdictions)}"
        )

    def test_per_jurisdiction_anchors_correct(self):
        """US_DOJ anchor is DynCorp at 0.75, UK_SFO anchor is Tesco at 0.501."""
        cases = _load_real_cases()
        result = derive_markup_floor_ratio(cases)

        us = result.per_jurisdiction_anchors["US_DOJ"]
        assert us.case_id == "US_v_DynCorp_2005", f"US_DOJ anchor: {us.case_id}"
        assert us.markup_percentage == 0.75, f"US_DOJ markup: {us.markup_percentage}"

        uk = result.per_jurisdiction_anchors["UK_SFO"]
        assert uk.case_id == "UK_SFO_Tesco_2017", f"UK_SFO anchor: {uk.case_id}"
        assert uk.markup_percentage == 0.501, f"UK_SFO markup: {uk.markup_percentage}"

    def test_fr_pnf_and_wb_int_not_in_contributing(self):
        """FR_PNF and WB_INT have no markup_based qualifying cases yet."""
        cases = _load_real_cases()
        result = derive_markup_floor_ratio(cases)
        assert "FR_PNF" not in result.per_jurisdiction_anchors, (
            "FR_PNF should not appear (no markup_based cases)"
        )
        assert "WB_INT" not in result.per_jurisdiction_anchors, (
            "WB_INT should not appear (no markup_based cases)"
        )

    def test_methodology_version_is_intersection_v1(self):
        """The derivation identifies itself as intersection_v1."""
        cases = _load_real_cases()
        result = derive_markup_floor_ratio(cases)
        assert result.methodology_version == "intersection_v1"


# ═══════════════════════════════════════════════════════════
# Synthetic tests
# ═══════════════════════════════════════════════════════════


class TestSyntheticCorpusDerivation:
    """Verify edge cases and multi-jurisdiction intersection logic."""

    def test_three_jurisdiction_intersection(self):
        """With three jurisdictions, the function returns the minimum anchor."""
        cases = [
            _make_case("DOJ_A", "US_DOJ", 60.0),   # 0.6
            _make_case("SFO_B", "UK_SFO", 50.0),    # 0.5
            _make_case("PNF_C", "FR_PNF", 40.0),    # 0.4
        ]
        result = derive_markup_floor_ratio(cases)
        assert result.value == 0.4, f"Expected 0.4, got {result.value}"
        assert set(result.contributing_jurisdictions) == {
            "US_DOJ", "UK_SFO", "FR_PNF"
        }

    def test_empty_corpus_raises_insufficient_corpus_error(self):
        """An empty cases list raises InsufficientCorpusError."""
        with pytest.raises(InsufficientCorpusError):
            derive_markup_floor_ratio([])


# ═══════════════════════════════════════════════════════════
# Audit trail test
# ═══════════════════════════════════════════════════════════


class TestDerivationAuditTrail:
    """The audit trail is populated after derivation runs."""

    def test_audit_trail_has_markup_floor_entry(self):
        """get_derivation_audit_trail() returns a populated markup_floor."""
        # The audit trail is populated at import time when
        # global_parameters.py calls get_derived_mjpis(). Force it
        # to run by importing the module.
        from global_parameters import MJPIS_DRAFT_V0  # noqa: F401

        trail = get_derivation_audit_trail()
        assert isinstance(trail, DerivationAuditTrail)
        assert trail.markup_floor is not None, (
            "Expected markup_floor to be populated in the audit trail"
        )
        mf = trail.markup_floor
        assert isinstance(mf, MarkupFloorDerivation)
        assert mf.value == 0.501
        assert set(mf.contributing_jurisdictions) == {"US_DOJ", "UK_SFO"}
        assert "US_DOJ" in mf.per_jurisdiction_anchors
        assert "UK_SFO" in mf.per_jurisdiction_anchors
