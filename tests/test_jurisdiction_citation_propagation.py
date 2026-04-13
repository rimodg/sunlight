"""
Tests for CRI legal citation propagation and universal_citations coverage.

- Tests 1-3 (commit 39b5d65): _determine_tier() emits jurisdiction-appropriate
  legal citations from the active profile's legal_citations dict.
- Tests 4-6 (this commit): PROC-001 evidence string contains the full UNCAC +
  OECD universal_citations list and NOT the removed institution-specific items.

Run: pytest tests/test_jurisdiction_citation_propagation.py -v
"""

import pytest
import numpy as np

from institutional_statistical_rigor import (
    ProsecutorEvidencePackage,
    BootstrapResult,
    BayesianResult,
    DOJProsecutionThresholds,
    FraudTier,
)
from jurisdiction_profile import US_FEDERAL, UK_CENTRAL_GOVERNMENT
from tca_rules import build_rules


# ---------------------------------------------------------------------------
# Helpers — build synthetic bootstrap / bayesian results for _determine_tier()
# ---------------------------------------------------------------------------

def _make_bootstrap(ci_lower: float, is_significant: bool = True) -> BootstrapResult:
    """Create a BootstrapResult with controlled ci_lower."""
    return BootstrapResult(
        point_estimate=ci_lower * 1.2,
        ci_lower=ci_lower,
        ci_upper=ci_lower * 1.5,
        ci_width=ci_lower * 0.3,
        confidence_level=0.95,
        n_iterations=1000,
        sample_size=10,
        p_value=0.001 if is_significant else 0.5,
        is_significant=is_significant,
        interpretation="test",
    )


def _make_bayesian(posterior: float = 0.5) -> BayesianResult:
    """Create a BayesianResult with controlled posterior."""
    return BayesianResult(
        prior_probability=0.03,
        likelihood_ratio=2.0,
        posterior_probability=posterior,
        base_rate_source="test",
        sensitivity=0.9,
        specificity=0.95,
        interpretation="test",
    )


# ---------------------------------------------------------------------------
# Test 1: US profile emits US statutes
# ---------------------------------------------------------------------------

class TestUSProfileCitations:
    """When ProsecutorEvidencePackage is constructed with US_FEDERAL legal_citations,
    _determine_tier() must emit US-specific statutes."""

    def test_extreme_markup_emits_us_false_claims_act(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db, legal_citations=US_FEDERAL.legal_citations)
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.EXTREME_MARKUP + 50)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(markup, percentile, bayesian, {})

        assert tier == FraudTier.RED
        assert any("31 U.S.C. § 3729(a)(1)(A)" in c for c in citations), \
            f"Expected US False Claims Act citation, got: {citations}"
        assert any("31 U.S.C. § 3729(a)(1)(B)" in c for c in citations), \
            f"Expected US false records citation, got: {citations}"
        assert any("Oracle, Boeing, Lockheed" in c for c in citations), \
            f"Expected DOJ precedent citation, got: {citations}"

    def test_donations_emit_us_anti_kickback(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db, legal_citations=US_FEDERAL.legal_citations)
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.ELEVATED_MARKUP + 10)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(
            markup, percentile, bayesian, {"has_donations": True}
        )

        assert any("41 U.S.C. § 8702" in c for c in citations), \
            f"Expected US Anti-Kickback Act citation, got: {citations}"


# ---------------------------------------------------------------------------
# Test 2: UK profile emits UK statutes and NOT US statutes
# ---------------------------------------------------------------------------

class TestUKProfileCitations:
    """When ProsecutorEvidencePackage is constructed with UK_CENTRAL_GOVERNMENT
    legal_citations, _determine_tier() must emit UK-specific statutes and must
    NOT emit any US statute references."""

    def test_extreme_markup_emits_uk_fraud_act(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db, legal_citations=UK_CENTRAL_GOVERNMENT.legal_citations)
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.EXTREME_MARKUP + 50)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(markup, percentile, bayesian, {})

        assert tier == FraudTier.RED
        assert any("Fraud Act 2006" in c for c in citations), \
            f"Expected UK Fraud Act citation, got: {citations}"
        assert any("Rolls-Royce, Airbus, Tesco" in c for c in citations), \
            f"Expected UK SFO DPA precedent, got: {citations}"
        # Must NOT contain US-specific references
        for c in citations:
            assert "U.S.C." not in c, f"UK profile must not emit US statute, got: {c}"
            assert "DOJ prosecution precedent" not in c, f"UK profile must not reference DOJ, got: {c}"

    def test_donations_emit_uk_bribery_act(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db, legal_citations=UK_CENTRAL_GOVERNMENT.legal_citations)
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.ELEVATED_MARKUP + 10)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(
            markup, percentile, bayesian, {"has_donations": True}
        )

        assert any("Bribery Act 2010" in c for c in citations), \
            f"Expected UK Bribery Act citation, got: {citations}"
        for c in citations:
            assert "Anti-Kickback Act" not in c, f"UK profile must not emit US AKA, got: {c}"


# ---------------------------------------------------------------------------
# Test 3: Minimal/empty profile gets fallback, NOT US statutes
# ---------------------------------------------------------------------------

class TestFallbackCitations:
    """When ProsecutorEvidencePackage is constructed with no legal_citations
    (the default), _determine_tier() must emit generic fallback citations
    and NOT US-specific statute numbers."""

    def test_extreme_markup_emits_generic_fallback(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db)  # no legal_citations
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.EXTREME_MARKUP + 50)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(markup, percentile, bayesian, {})

        assert tier == FraudTier.RED
        # Must contain generic fallback language
        assert any("False claims" in c or "fraudulent misrepresentation" in c for c in citations), \
            f"Expected generic false claims fallback, got: {citations}"
        assert any("False records" in c or "material misstatement" in c for c in citations), \
            f"Expected generic false records fallback, got: {citations}"
        # Must NOT contain US-specific statute references
        for c in citations:
            assert "U.S.C." not in c, f"Default profile must not emit US statute, got: {c}"
            assert "Anti-Kickback Act" not in c, f"Default profile must not emit US AKA, got: {c}"

    def test_donations_emit_generic_anti_corruption(self, temp_db):
        pkg = ProsecutorEvidencePackage(temp_db)  # no legal_citations
        markup = _make_bootstrap(ci_lower=DOJProsecutionThresholds.ELEVATED_MARKUP + 10)
        percentile = _make_bootstrap(ci_lower=50, is_significant=False)
        bayesian = _make_bayesian(posterior=0.5)

        tier, conf, citations = pkg._determine_tier(
            markup, percentile, bayesian, {"has_donations": True}
        )

        assert any("Anti-corruption" in c or "quid pro quo" in c for c in citations), \
            f"Expected generic anti-corruption fallback, got: {citations}"
        for c in citations:
            assert "§ 8702" not in c, f"Default profile must not emit US AKA section, got: {c}"


# ---------------------------------------------------------------------------
# Helper — extract PROC-001 evidence string from a built rule set
# ---------------------------------------------------------------------------

def _get_proc_001_evidence(profile):
    """Build rules for a profile and return the PROC-001 evidence string."""
    rules = build_rules(profile)
    proc_001 = [r for r in rules if r.rule_id == "PROC-001"]
    assert len(proc_001) == 1, f"Expected exactly one PROC-001 rule, got {len(proc_001)}"
    return proc_001[0].evidence


# ---------------------------------------------------------------------------
# Test 4: PROC-001 under us_federal emits full UNCAC + OECD set
# ---------------------------------------------------------------------------

class TestPROC001USFederalUniversalCitations:
    """PROC-001 evidence string under us_federal must contain the full
    universal_citations list including key UNCAC articles and OECD instruments."""

    def test_contains_uncac_art_9_1(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "UNCAC Art. 9(1)" in ev, f"Missing UNCAC Art. 9(1) in: {ev[:200]}"

    def test_contains_uncac_art_16(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "UNCAC Art. 16" in ev, f"Missing UNCAC Art. 16 in: {ev[:200]}"

    def test_contains_oecd_anti_bribery(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "OECD Anti-Bribery Convention 1997" in ev, \
            f"Missing OECD Anti-Bribery Convention in: {ev[:200]}"

    def test_contains_procurement_law(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "FAR" in ev and "Part 6" in ev, f"Missing FAR Part 6 in: {ev[:200]}"


# ---------------------------------------------------------------------------
# Test 5: PROC-001 under uk_central_government emits same universal set
# ---------------------------------------------------------------------------

class TestPROC001UKCentralGovUniversalCitations:
    """PROC-001 evidence string under uk_central_government must contain
    the same universal UNCAC + OECD references (they are jurisdiction-agnostic)."""

    def test_contains_uncac_art_9_1(self):
        ev = _get_proc_001_evidence(UK_CENTRAL_GOVERNMENT)
        assert "UNCAC Art. 9(1)" in ev, f"Missing UNCAC Art. 9(1) in: {ev[:200]}"

    def test_contains_uncac_art_16(self):
        ev = _get_proc_001_evidence(UK_CENTRAL_GOVERNMENT)
        assert "UNCAC Art. 16" in ev, f"Missing UNCAC Art. 16 in: {ev[:200]}"

    def test_contains_oecd_anti_bribery(self):
        ev = _get_proc_001_evidence(UK_CENTRAL_GOVERNMENT)
        assert "OECD Anti-Bribery Convention 1997" in ev, \
            f"Missing OECD Anti-Bribery Convention in: {ev[:200]}"

    def test_contains_uk_procurement_law(self):
        ev = _get_proc_001_evidence(UK_CENTRAL_GOVERNMENT)
        assert "UK Procurement Act 2023" in ev, \
            f"Missing UK Procurement Act 2023 in: {ev[:200]}"


# ---------------------------------------------------------------------------
# Test 6: PROC-001 must NOT contain removed institution-specific items
# ---------------------------------------------------------------------------

class TestPROC001RemovedItems:
    """PROC-001 evidence string must NOT contain the old institution-specific
    items that were removed from universal_citations."""

    def test_no_undp_popp(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "UNDP POPP" not in ev, \
            f"UNDP POPP should have been removed from universal_citations: {ev[:200]}"

    def test_no_oecd_public_procurement_principles(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "OECD Public Procurement Principles" not in ev, \
            f"OECD Public Procurement Principles should have been removed: {ev[:200]}"

    def test_no_world_bank_procurement_framework(self):
        ev = _get_proc_001_evidence(US_FEDERAL)
        assert "World Bank Procurement Framework" not in ev, \
            f"World Bank Procurement Framework should have been removed: {ev[:200]}"

    def test_uk_profile_also_clean(self):
        """Same removal assertions under uk_central_government."""
        ev = _get_proc_001_evidence(UK_CENTRAL_GOVERNMENT)
        assert "UNDP POPP" not in ev
        assert "OECD Public Procurement Principles" not in ev
        assert "World Bank Procurement Framework" not in ev


# ---------------------------------------------------------------------------
# Test 7: us_federal profile institutional depth — 12 legal_citations keys
# ---------------------------------------------------------------------------

_EXPECTED_US_FEDERAL_KEYS = {
    "procurement_law", "competition_law", "case_authority",
    "false_claims_law", "false_records_law", "anti_kickback_law",
    "extreme_markup_precedent",
    "foreign_bribery_law", "audit_oversight_law", "sanctions_debarment_law",
    "conflict_of_interest_law", "whistleblower_protection_law",
}


class TestUSFederalInstitutionalDepth:
    """us_federal profile must contain all 12 institutional-grade
    legal_citations keys with correct canonical citation values."""

    def test_all_12_keys_present(self):
        lc = US_FEDERAL.legal_citations
        assert set(lc.keys()) == _EXPECTED_US_FEDERAL_KEYS, \
            f"Expected 12 keys, got {len(lc)}: missing={_EXPECTED_US_FEDERAL_KEYS - set(lc.keys())}, extra={set(lc.keys()) - _EXPECTED_US_FEDERAL_KEYS}"

    def test_foreign_bribery_law_contains_fcpa(self):
        v = US_FEDERAL.legal_citations["foreign_bribery_law"]
        assert "Foreign Corrupt Practices Act" in v, f"Missing FCPA: {v}"
        assert "15 U.S.C." in v, f"Missing USC reference: {v}"

    def test_sanctions_debarment_law_contains_far_and_eo(self):
        v = US_FEDERAL.legal_citations["sanctions_debarment_law"]
        assert "FAR Subpart 9.4" in v, f"Missing FAR 9.4: {v}"
        assert "Executive Order 12549" in v, f"Missing EO 12549: {v}"

    def test_audit_oversight_law_contains_ig_act(self):
        v = US_FEDERAL.legal_citations["audit_oversight_law"]
        assert "Inspector General Act" in v, f"Missing IG Act: {v}"
        assert "31 U.S.C. § 3512" in v, f"Missing FMFIA: {v}"

    def test_case_authority_aggregates_corpus_cases(self):
        v = US_FEDERAL.legal_citations["case_authority"]
        for name in ["DynCorp", "Oracle", "Boeing", "Lockheed Martin"]:
            assert name in v, f"Missing {name} in case_authority: {v}"

    def test_procurement_law_covers_three_far_parts(self):
        v = US_FEDERAL.legal_citations["procurement_law"]
        assert "FAR Part 6" in v or "FAR) Part 6" in v, f"Missing FAR Part 6: {v}"
        assert "FAR Part 15" in v, f"Missing FAR Part 15: {v}"
        assert "FAR Part 13" in v, f"Missing FAR Part 13: {v}"
