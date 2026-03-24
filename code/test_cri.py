"""
Test suite for SUNLIGHT CRI indicators and OCDS field extractor.

Tests cover:
- Each indicator individually with edge cases
- OCDS extraction from realistic release data
- Composite CRI computation
- Bayesian likelihood combination
- GRAY handling (missing data → indeterminate, not clean)

Run: python -m pytest test_cri.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
from ocds_field_extractor import extract_release, ExtractedRelease
from cri_indicators import (
    single_bidding,
    tender_period_risk,
    procedure_type_risk,
    decision_period_risk,
    amendment_risk,
    detect_split_purchases,
    buyer_concentration,
    compute_cri,
    combined_likelihood_ratio,
    analyze_release,
    IndicatorResult,
)


# ===========================================================================
# SINGLE BIDDING
# ===========================================================================

class TestSingleBidding:
    def test_single_bid_flagged(self):
        r = single_bidding(number_of_tenderers=1, procurement_method="open")
        assert r.flag == 1
        assert r.likelihood_ratio == 3.0

    def test_multiple_bids_clean(self):
        r = single_bidding(number_of_tenderers=5, procurement_method="open")
        assert r.flag == 0
        assert r.likelihood_ratio < 1.0

    def test_two_bids_clean_but_elevated(self):
        r = single_bidding(number_of_tenderers=2, procurement_method="open")
        assert r.flag == 0
        assert r.likelihood_ratio > 1.0

    def test_missing_data_gray(self):
        r = single_bidding(number_of_tenderers=None)
        assert r.flag is None
        assert r.is_indeterminate

    def test_direct_award_not_flagged(self):
        """Single bid on direct award is expected, not suspicious."""
        r = single_bidding(number_of_tenderers=1, procurement_method="direct")
        assert r.flag == 0

    def test_fallback_to_bid_count(self):
        """Use bid_count when numberOfTenderers missing."""
        r = single_bidding(number_of_tenderers=None, bid_count=1, procurement_method="open")
        assert r.flag == 1

    def test_tier_label(self):
        r = single_bidding(number_of_tenderers=1, procurement_method="open")
        assert r.tier_label == "RED"
        r2 = single_bidding(number_of_tenderers=5)
        assert r2.tier_label == "GREEN"
        r3 = single_bidding(number_of_tenderers=None)
        assert r3.tier_label == "GRAY"


# ===========================================================================
# TENDER PERIOD
# ===========================================================================

class TestTenderPeriod:
    def test_very_short_flagged(self):
        r = tender_period_risk(tender_period_days=3.0)
        assert r.flag == 1
        assert r.likelihood_ratio == 4.0

    def test_short_flagged(self):
        r = tender_period_risk(tender_period_days=10.0)
        assert r.flag == 1
        assert r.likelihood_ratio == 2.0

    def test_adequate_clean(self):
        r = tender_period_risk(tender_period_days=30.0)
        assert r.flag == 0

    def test_missing_gray(self):
        r = tender_period_risk(tender_period_days=None)
        assert r.flag is None

    def test_negative_period(self):
        """Negative period = data error or backdating."""
        r = tender_period_risk(tender_period_days=-2.0)
        assert r.flag == 1
        assert r.likelihood_ratio == 5.0

    def test_custom_jurisdiction_minimum(self):
        # 20 days is fine with default 15, but not with 25
        r = tender_period_risk(tender_period_days=20.0, jurisdiction_minimum=25.0)
        assert r.flag == 1


# ===========================================================================
# PROCEDURE TYPE
# ===========================================================================

class TestProcedureType:
    def test_direct_flagged(self):
        r = procedure_type_risk(procurement_method="direct")
        assert r.flag == 1
        assert r.likelihood_ratio == 2.5

    def test_limited_flagged(self):
        r = procedure_type_risk(procurement_method="limited")
        assert r.flag == 1

    def test_open_clean(self):
        r = procedure_type_risk(procurement_method="open")
        assert r.flag == 0
        assert r.likelihood_ratio < 1.0

    def test_selective_clean_but_noted(self):
        r = procedure_type_risk(procurement_method="selective")
        assert r.flag == 0
        assert r.likelihood_ratio > 1.0

    def test_missing_gray(self):
        r = procedure_type_risk(procurement_method=None)
        assert r.flag is None

    def test_unknown_method_gray(self):
        r = procedure_type_risk(procurement_method="framework_agreement_xyz")
        assert r.flag is None

    def test_case_insensitive(self):
        r = procedure_type_risk(procurement_method="Direct")
        assert r.flag == 1


# ===========================================================================
# DECISION PERIOD
# ===========================================================================

class TestDecisionPeriod:
    def test_normal_clean(self):
        r = decision_period_risk(decision_period_days=30.0)
        assert r.flag == 0

    def test_same_day_flagged(self):
        r = decision_period_risk(decision_period_days=0.5)
        assert r.flag == 1
        assert r.likelihood_ratio == 3.0

    def test_negative_flagged(self):
        """Award before deadline = impossible."""
        r = decision_period_risk(decision_period_days=-5.0)
        assert r.flag == 1
        assert r.likelihood_ratio == 4.0

    def test_very_long_flagged(self):
        r = decision_period_risk(decision_period_days=200.0)
        assert r.flag == 1

    def test_missing_gray(self):
        r = decision_period_risk(decision_period_days=None)
        assert r.flag is None


# ===========================================================================
# AMENDMENTS
# ===========================================================================

class TestAmendments:
    def test_no_amendments_clean(self):
        r = amendment_risk(amendment_count=0)
        assert r.flag == 0

    def test_value_increase_flagged(self):
        r = amendment_risk(amendment_count=1, original_value=100000, final_value=150000)
        assert r.flag == 1
        assert r.data["value_change_pct"] == pytest.approx(0.50)

    def test_moderate_increase_clean(self):
        r = amendment_risk(amendment_count=1, original_value=100000, final_value=110000)
        assert r.flag == 0

    def test_many_amendments_flagged(self):
        r = amendment_risk(amendment_count=5)
        assert r.flag == 1

    def test_no_values_with_amendments(self):
        r = amendment_risk(amendment_count=1, original_value=None, final_value=None)
        assert r.flag == 0  # Can't determine value change, count not suspicious


# ===========================================================================
# SPLIT PURCHASES
# ===========================================================================

class TestSplitPurchases:
    def test_cluster_detected(self):
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        contracts = [
            {"buyer_id": "BUYER1", "value": 9800, "date": base_date + timedelta(days=i)}
            for i in range(5)
        ]
        results = detect_split_purchases(contracts, threshold=10000)
        assert len(results) == 1
        assert results[0].flag == 1

    def test_no_cluster_below_min(self):
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        contracts = [
            {"buyer_id": "BUYER1", "value": 9800, "date": base_date + timedelta(days=i)}
            for i in range(2)  # Only 2, below min_cluster_size=3
        ]
        results = detect_split_purchases(contracts, threshold=10000)
        assert len(results) == 0

    def test_spread_out_no_cluster(self):
        """Contracts too far apart in time."""
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        contracts = [
            {"buyer_id": "BUYER1", "value": 9800, "date": base_date + timedelta(days=i * 60)}
            for i in range(5)
        ]
        results = detect_split_purchases(contracts, threshold=10000, time_window_days=30)
        assert len(results) == 0

    def test_values_not_near_threshold(self):
        base_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        contracts = [
            {"buyer_id": "BUYER1", "value": 5000, "date": base_date + timedelta(days=i)}
            for i in range(5)
        ]
        results = detect_split_purchases(contracts, threshold=10000)
        assert len(results) == 0


# ===========================================================================
# BUYER CONCENTRATION
# ===========================================================================

class TestBuyerConcentration:
    def test_high_concentration_flagged(self):
        r = buyer_concentration(
            buyer_id="GOV_AGENCY_1",
            supplier_contracts={"SupplierA": 800000, "SupplierB": 100000, "SupplierC": 100000}
        )
        assert r.flag == 1
        assert r.data["top_share"] == pytest.approx(0.80)

    def test_diversified_clean(self):
        r = buyer_concentration(
            buyer_id="GOV_AGENCY_1",
            supplier_contracts={"A": 250, "B": 250, "C": 250, "D": 250}
        )
        assert r.flag == 0

    def test_single_supplier_flagged(self):
        r = buyer_concentration(
            buyer_id="GOV_AGENCY_1",
            supplier_contracts={"OnlySupplier": 500000}
        )
        assert r.flag == 1

    def test_empty_suppliers_gray(self):
        r = buyer_concentration(buyer_id="GOV", supplier_contracts={})
        assert r.flag is None

    def test_hhi_computed(self):
        r = buyer_concentration(
            buyer_id="GOV",
            supplier_contracts={"A": 500, "B": 500}
        )
        assert r.data["hhi"] == pytest.approx(0.50)


# ===========================================================================
# COMPOSITE CRI
# ===========================================================================

class TestCompositeCRI:
    def test_all_flagged_red(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=2.0, explanation="flagged"),
            IndicatorResult("b", flag=1, likelihood_ratio=2.0, explanation="flagged"),
            IndicatorResult("c", flag=1, likelihood_ratio=2.0, explanation="flagged"),
        ]
        cri = compute_cri(results)
        assert cri.cri_score == pytest.approx(1.0)
        assert cri.tier == "RED"

    def test_none_flagged_green(self):
        results = [
            IndicatorResult("a", flag=0, likelihood_ratio=0.8, explanation="clean"),
            IndicatorResult("b", flag=0, likelihood_ratio=0.8, explanation="clean"),
            IndicatorResult("c", flag=0, likelihood_ratio=0.8, explanation="clean"),
        ]
        cri = compute_cri(results)
        assert cri.cri_score == pytest.approx(0.0)
        assert cri.tier == "GREEN"

    def test_mixed_yellow(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=2.0, explanation="flagged"),
            IndicatorResult("b", flag=0, likelihood_ratio=0.8, explanation="clean"),
            IndicatorResult("c", flag=0, likelihood_ratio=0.8, explanation="clean"),
        ]
        cri = compute_cri(results)
        assert cri.cri_score == pytest.approx(1 / 3)
        assert cri.tier == "YELLOW"

    def test_insufficient_data_gray(self):
        results = [
            IndicatorResult("a", flag=None, likelihood_ratio=1.0, explanation="no data"),
            IndicatorResult("b", flag=None, likelihood_ratio=1.0, explanation="no data"),
            IndicatorResult("c", flag=1, likelihood_ratio=2.0, explanation="flagged"),
        ]
        cri = compute_cri(results, min_indicators=3)
        assert cri.cri_score is None
        assert cri.tier == "GRAY"

    def test_skips_gray_in_average(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=2.0, explanation="flagged"),
            IndicatorResult("b", flag=0, likelihood_ratio=0.8, explanation="clean"),
            IndicatorResult("c", flag=None, likelihood_ratio=1.0, explanation="no data"),
            IndicatorResult("d", flag=0, likelihood_ratio=0.8, explanation="clean"),
        ]
        cri = compute_cri(results)
        # Only 3 available (a, b, d), 1 flagged
        assert cri.cri_score == pytest.approx(1 / 3)
        assert cri.n_indicators_available == 3

    def test_summary_string(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=2.0, explanation="f"),
            IndicatorResult("b", flag=0, likelihood_ratio=0.8, explanation="c"),
            IndicatorResult("c", flag=0, likelihood_ratio=0.8, explanation="c"),
        ]
        cri = compute_cri(results)
        assert "YELLOW" in cri.summary
        assert "1/3" in cri.summary


# ===========================================================================
# COMBINED LIKELIHOOD
# ===========================================================================

class TestCombinedLikelihood:
    def test_multiplication(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=3.0, explanation=""),
            IndicatorResult("b", flag=1, likelihood_ratio=2.0, explanation=""),
        ]
        assert combined_likelihood_ratio(results) == pytest.approx(6.0)

    def test_skips_none(self):
        results = [
            IndicatorResult("a", flag=1, likelihood_ratio=3.0, explanation=""),
            IndicatorResult("b", flag=None, likelihood_ratio=1.0, explanation=""),
        ]
        assert combined_likelihood_ratio(results) == pytest.approx(3.0)

    def test_clean_reduces(self):
        results = [
            IndicatorResult("a", flag=0, likelihood_ratio=0.7, explanation=""),
            IndicatorResult("b", flag=0, likelihood_ratio=0.8, explanation=""),
        ]
        assert combined_likelihood_ratio(results) == pytest.approx(0.56)


# ===========================================================================
# OCDS FIELD EXTRACTOR
# ===========================================================================

class TestOCDSExtractor:
    def _make_release(self, **overrides):
        """Create a minimal OCDS release with optional overrides."""
        release = {
            "ocid": "ocds-abc-001",
            "id": "release-001",
            "date": "2024-01-15T10:00:00Z",
            "buyer": {"id": "GOV-001", "name": "Ministry of Health"},
            "tender": {
                "procurementMethod": "open",
                "numberOfTenderers": 3,
                "tenderPeriod": {
                    "startDate": "2024-01-01T00:00:00Z",
                    "endDate": "2024-01-30T00:00:00Z",
                },
                "items": [
                    {"classification": {"scheme": "CPV", "id": "33000000"}}
                ],
            },
            "awards": [
                {
                    "status": "active",
                    "date": "2024-02-15T00:00:00Z",
                    "value": {"amount": 50000, "currency": "GBP"},
                    "suppliers": [{"id": "SUPPLIER-001", "name": "MedCorp"}],
                }
            ],
            "contracts": [
                {
                    "value": {"amount": 55000, "currency": "GBP"},
                    "amendments": [],
                }
            ],
        }
        # Deep merge overrides
        for key, val in overrides.items():
            release[key] = val
        return release

    def test_basic_extraction(self):
        release = self._make_release()
        ex = extract_release(release)
        assert ex.ocid == "ocds-abc-001"
        assert ex.buyer_id == "GOV-001"
        assert ex.procurement_method == "open"
        assert ex.number_of_tenderers == 3
        assert ex.tender_period_days == pytest.approx(29.0)
        assert ex.award_value == 50000
        assert ex.award_currency == "GBP"

    def test_missing_tender_period(self):
        release = self._make_release(
            tender={"procurementMethod": "open", "numberOfTenderers": 1}
        )
        ex = extract_release(release)
        assert ex.tender_period_days is None
        assert "tender_period_days" in ex.fields_missing

    def test_missing_number_of_tenderers_fallback_to_bids(self):
        release = self._make_release(
            tender={"procurementMethod": "open"},
            bids={"details": [
                {"tenderers": [{"id": "A"}]},
                {"tenderers": [{"id": "B"}]},
            ]}
        )
        # Remove numberOfTenderers from tender
        release["tender"].pop("numberOfTenderers", None)
        ex = extract_release(release)
        assert ex.number_of_tenderers == 2
        assert ex.bid_count == 2

    def test_decision_period_computed(self):
        release = self._make_release()
        ex = extract_release(release)
        # Award: Feb 15, Tender end: Jan 30 → 16 days
        assert ex.decision_period_days == pytest.approx(16.0)

    def test_amendments_extracted(self):
        release = self._make_release(
            contracts=[{
                "value": {"amount": 75000, "currency": "GBP"},
                "amendments": [
                    {"date": "2024-03-01", "description": "Scope increase"},
                    {"date": "2024-04-01", "description": "Further increase"},
                ],
            }]
        )
        ex = extract_release(release)
        assert ex.amendment_count == 2
        assert ex.contract_value == 75000
        # original_value = award value, final_value = contract value
        assert ex.original_value == 50000
        assert ex.final_value == 75000

    def test_buyer_from_parties_fallback(self):
        release = {
            "ocid": "ocds-xyz-001",
            "id": "r-001",
            "parties": [
                {"id": "BUYER-FROM-PARTIES", "name": "Customs Agency", "roles": ["buyer"]},
                {"id": "SUPPLIER-001", "name": "WidgetCo", "roles": ["supplier"]},
            ],
            "tender": {},
            "awards": [],
        }
        ex = extract_release(release)
        assert ex.buyer_id == "BUYER-FROM-PARTIES"

    def test_item_classification(self):
        release = self._make_release()
        ex = extract_release(release)
        assert ex.main_classification == "CPV:33000000"

    def test_fields_tracking(self):
        release = self._make_release()
        ex = extract_release(release)
        assert "number_of_tenderers" in ex.fields_present
        assert "procurement_method" in ex.fields_present
        assert "tender_period_days" in ex.fields_present


# ===========================================================================
# END-TO-END: analyze_release
# ===========================================================================

class TestAnalyzeRelease:
    def test_clean_release(self):
        ex = ExtractedRelease(
            ocid="test-001",
            release_id="r1",
            procurement_method="open",
            number_of_tenderers=5,
            tender_period_days=30.0,
            decision_period_days=14.0,
            amendment_count=0,
        )
        cri = analyze_release(ex, price_flag=0, price_lr=0.8)
        assert cri.tier in ("GREEN", "YELLOW")  # Depends on exact scoring
        assert cri.n_indicators_flagged == 0

    def test_suspicious_release(self):
        ex = ExtractedRelease(
            ocid="test-002",
            release_id="r2",
            procurement_method="direct",
            number_of_tenderers=1,
            tender_period_days=3.0,
            decision_period_days=0.5,
            amendment_count=4,
            original_value=100000,
            final_value=200000,
        )
        cri = analyze_release(ex, price_flag=1, price_lr=3.0)
        assert cri.tier == "RED"
        assert cri.n_indicators_flagged >= 3

    def test_sparse_data_gray(self):
        ex = ExtractedRelease(
            ocid="test-003",
            release_id="r3",
            procurement_method=None,
            number_of_tenderers=None,
            tender_period_days=None,
            decision_period_days=None,
            amendment_count=0,
        )
        cri = analyze_release(ex)
        # Most indicators will be GRAY, CRI should be GRAY too
        assert cri.tier == "GRAY"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
