"""
Tests for MJPIS intersection_v1 derivations (all three Phase C parameters).
===========================================================================

Twenty-four regression tests locking in the principled per-jurisdiction
extraction and intersection methodology introduced by item 20
phase two sub-tasks A (markup_floor), B (bribery_channel), and
C (administrative_sanctionable).

Run with:  pytest tests/test_mjpis_derivation_intersection.py -v
"""

import pytest

from mjpis_derivation import (
    CORPUS_PATH,
    AdministrativeSanctionableDerivation,
    BriberyChannelDerivation,
    DerivationAuditTrail,
    InsufficientCorpusError,
    JurisdictionAnchor,
    MarkupFloorDerivation,
    derive_administrative_sanctionable_threshold,
    derive_bribery_channel_ratio,
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


def _make_bc_case(case_id, jurisdiction, bribery_channel_ratio, tags=None):
    """Build a minimal synthetic bribery-channel corpus case dict."""
    return {
        "case_id": case_id,
        "jurisdiction": jurisdiction,
        "bribery_channel_ratio": bribery_channel_ratio,
        "dimensional_tags": tags or ["bribery_channel"],
    }


def _make_as_case(
    case_id, jurisdiction, debarment_duration_months,
    debarment_is_permanent=False, tags=None,
):
    """Build a minimal synthetic administrative-sanctionable corpus case dict."""
    return {
        "case_id": case_id,
        "jurisdiction": jurisdiction,
        "debarment_duration_months": debarment_duration_months,
        "debarment_is_permanent": debarment_is_permanent,
        "dimensional_tags": tags or ["administrative_sanctionable"],
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


# ═══════════════════════════════════════════════════════════
# Bribery-channel ratio tests against the real corpus
# ═══════════════════════════════════════════════════════════


class TestRealCorpusBriberyChannelDerivation:
    """Verify the intersection_v1 bribery-channel ratio against the current corpus."""

    def test_bribery_channel_value_is_0_0058(self):
        """The intersection is 0.0058 (Amec Foster Wheeler, UK_SFO anchor)."""
        cases = _load_real_cases()
        result = derive_bribery_channel_ratio(cases)
        assert result.value == 0.0058, (
            f"Expected bribery_channel_ratio=0.0058 (AmecFosterWheeler 2021), "
            f"got {result.value}"
        )

    def test_bribery_channel_contributing_jurisdictions(self):
        """Only UK_SFO and FR_PNF have qualifying bribery_channel cases."""
        cases = _load_real_cases()
        result = derive_bribery_channel_ratio(cases)
        assert set(result.contributing_jurisdictions) == {"UK_SFO", "FR_PNF"}, (
            f"Expected {{UK_SFO, FR_PNF}}, got {set(result.contributing_jurisdictions)}"
        )

    def test_bribery_channel_per_jurisdiction_anchors(self):
        """UK_SFO anchor is AmecFosterWheeler at 0.0058, FR_PNF is SocieteGenerale at 0.0246."""
        cases = _load_real_cases()
        result = derive_bribery_channel_ratio(cases)

        uk = result.per_jurisdiction_anchors["UK_SFO"]
        assert uk.case_id == "UK_SFO_AmecFosterWheeler_2021", f"UK_SFO anchor: {uk.case_id}"
        assert uk.markup_percentage == 0.0058, f"UK_SFO ratio: {uk.markup_percentage}"
        assert uk.qualifying_case_count == 4, f"UK_SFO qualifying: {uk.qualifying_case_count}"

        fr = result.per_jurisdiction_anchors["FR_PNF"]
        assert fr.case_id == "FR_PNF_SocieteGenerale_2018", f"FR_PNF anchor: {fr.case_id}"
        assert fr.markup_percentage == 0.0246, f"FR_PNF ratio: {fr.markup_percentage}"
        assert fr.qualifying_case_count == 2, f"FR_PNF qualifying: {fr.qualifying_case_count}"

    def test_us_doj_and_wb_int_not_in_bribery_channel(self):
        """US_DOJ and WB_INT have no qualifying bribery_channel cases."""
        cases = _load_real_cases()
        result = derive_bribery_channel_ratio(cases)
        assert "US_DOJ" not in result.per_jurisdiction_anchors, (
            "US_DOJ should not appear (no bribery_channel cases with ratio)"
        )
        assert "WB_INT" not in result.per_jurisdiction_anchors, (
            "WB_INT should not appear (no bribery_channel cases with ratio)"
        )

    def test_bribery_channel_methodology_version(self):
        """The derivation identifies itself as intersection_v1."""
        cases = _load_real_cases()
        result = derive_bribery_channel_ratio(cases)
        assert result.methodology_version == "intersection_v1"


# ═══════════════════════════════════════════════════════════
# Bribery-channel synthetic tests
# ═══════════════════════════════════════════════════════════


class TestSyntheticBriberyChannelDerivation:
    """Verify bribery-channel edge cases and multi-jurisdiction logic."""

    def test_three_jurisdiction_bribery_channel_intersection(self):
        """With three jurisdictions, returns the minimum anchor."""
        cases = [
            _make_bc_case("SFO_A", "UK_SFO", 0.01),
            _make_bc_case("PNF_B", "FR_PNF", 0.02),
            _make_bc_case("DOJ_C", "US_DOJ", 0.005),
        ]
        result = derive_bribery_channel_ratio(cases)
        assert result.value == 0.005, f"Expected 0.005, got {result.value}"
        assert set(result.contributing_jurisdictions) == {
            "UK_SFO", "FR_PNF", "US_DOJ"
        }

    def test_empty_corpus_raises_insufficient_corpus_error_bribery(self):
        """An empty cases list raises InsufficientCorpusError."""
        with pytest.raises(InsufficientCorpusError):
            derive_bribery_channel_ratio([])


# ═══════════════════════════════════════════════════════════
# Bribery-channel audit trail test
# ═══════════════════════════════════════════════════════════


class TestBriberyChannelAuditTrail:
    """The audit trail includes bribery_channel after derivation runs."""

    def test_audit_trail_has_bribery_channel_entry(self):
        """get_derivation_audit_trail() returns a populated bribery_channel."""
        from global_parameters import MJPIS_DRAFT_V0  # noqa: F401

        trail = get_derivation_audit_trail()
        assert isinstance(trail, DerivationAuditTrail)
        assert trail.bribery_channel is not None, (
            "Expected bribery_channel to be populated in the audit trail"
        )
        bc = trail.bribery_channel
        assert isinstance(bc, BriberyChannelDerivation)
        assert bc.value == 0.0058
        assert set(bc.contributing_jurisdictions) == {"UK_SFO", "FR_PNF"}
        assert "UK_SFO" in bc.per_jurisdiction_anchors
        assert "FR_PNF" in bc.per_jurisdiction_anchors


# ═══════════════════════════════════════════════════════════
# Administrative-sanctionable threshold tests against the real corpus
# ═══════════════════════════════════════════════════════════


class TestRealCorpusAdminSanctionableDerivation:
    """Verify intersection_v1 admin-sanctionable threshold against current corpus."""

    def test_admin_sanctionable_value_is_18(self):
        """The intersection is 18 months (Alcatel-Lucent 2015, WB_INT anchor)."""
        cases = _load_real_cases()
        result = derive_administrative_sanctionable_threshold(cases)
        assert result.value == 18, (
            f"Expected admin_sanc_threshold=18 (AlcatelLucent 2015), "
            f"got {result.value}"
        )

    def test_admin_sanctionable_contributing_jurisdictions(self):
        """Only WB_INT has qualifying administrative_sanctionable cases."""
        cases = _load_real_cases()
        result = derive_administrative_sanctionable_threshold(cases)
        assert result.contributing_jurisdictions == ["WB_INT"], (
            f"Expected ['WB_INT'], got {result.contributing_jurisdictions}"
        )

    def test_admin_sanctionable_wb_int_anchor(self):
        """WB_INT anchor is Alcatel-Lucent 2015 at 18 months."""
        cases = _load_real_cases()
        result = derive_administrative_sanctionable_threshold(cases)
        wb = result.per_jurisdiction_anchors["WB_INT"]
        assert wb.case_id == "WB_INT_AlcatelLucent_2015", f"WB_INT anchor: {wb.case_id}"
        assert int(wb.markup_percentage) == 18, f"WB_INT duration: {wb.markup_percentage}"

    def test_admin_sanctionable_excluded_permanent_count(self):
        """Excluded permanent debarment count reflects corpus state.

        The CRBC case has debarment_is_permanent=False at the case level
        (CRBC headline entity got 96 months; the E.C. de Luna permanent
        debarment is a sub-entity documented in notes). No WB_INT case
        has debarment_is_permanent=True in the current corpus, so the
        excluded count is 0.
        """
        cases = _load_real_cases()
        result = derive_administrative_sanctionable_threshold(cases)
        assert result.excluded_permanent_debarment_count == 0, (
            f"Expected 0 excluded permanent debarments, "
            f"got {result.excluded_permanent_debarment_count}"
        )

    def test_admin_sanctionable_methodology_version(self):
        """The derivation identifies itself as intersection_v1."""
        cases = _load_real_cases()
        result = derive_administrative_sanctionable_threshold(cases)
        assert result.methodology_version == "intersection_v1"


# ═══════════════════════════════════════════════════════════
# Administrative-sanctionable synthetic tests
# ═══════════════════════════════════════════════════════════


class TestSyntheticAdminSanctionableDerivation:
    """Verify admin-sanctionable edge cases and multi-jurisdiction logic."""

    def test_three_jurisdiction_admin_sanctionable_intersection(self):
        """With three jurisdictions, returns the minimum anchor."""
        cases = [
            _make_as_case("WB_A", "WB_INT", 24),
            _make_as_case("PNF_B", "FR_PNF", 36),
            _make_as_case("SFO_C", "UK_SFO", 12),
        ]
        result = derive_administrative_sanctionable_threshold(cases)
        assert result.value == 12, f"Expected 12, got {result.value}"
        assert set(result.contributing_jurisdictions) == {
            "WB_INT", "FR_PNF", "UK_SFO"
        }

    def test_empty_corpus_raises_insufficient_corpus_error_admin(self):
        """An empty cases list raises InsufficientCorpusError."""
        with pytest.raises(InsufficientCorpusError):
            derive_administrative_sanctionable_threshold([])


# ═══════════════════════════════════════════════════════════
# Administrative-sanctionable audit trail and integration tests
# ═══════════════════════════════════════════════════════════


class TestAdminSanctionableAuditTrailAndIntegration:
    """Audit trail and GlobalParameters integration for admin-sanctionable."""

    def test_audit_trail_has_all_three_entries(self):
        """get_derivation_audit_trail() returns all three Phase C derivations."""
        from global_parameters import MJPIS_DRAFT_V0  # noqa: F401

        trail = get_derivation_audit_trail()
        assert isinstance(trail, DerivationAuditTrail)
        assert trail.markup_floor is not None, "markup_floor missing"
        assert trail.bribery_channel is not None, "bribery_channel missing"
        assert trail.administrative_sanctionable is not None, (
            "administrative_sanctionable missing"
        )
        ad = trail.administrative_sanctionable
        assert isinstance(ad, AdministrativeSanctionableDerivation)
        assert ad.value == 18
        assert ad.contributing_jurisdictions == ["WB_INT"]

    def test_corpus_migration_completeness(self):
        """Every WB_INT admin_sanctionable case has duration or permanent flag."""
        cases = _load_real_cases()
        for case in cases:
            if case["jurisdiction"] != "WB_INT":
                continue
            if "administrative_sanctionable" not in case.get("dimensional_tags", []):
                continue
            has_duration = case.get("debarment_duration_months") is not None
            is_permanent = case.get("debarment_is_permanent", False)
            assert has_duration or is_permanent, (
                f"WB_INT case {case['case_id']} is administrative_sanctionable "
                f"but has neither debarment_duration_months nor "
                f"debarment_is_permanent=True — silent null in qualifying slice"
            )
