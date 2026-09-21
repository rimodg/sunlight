"""
Tests for DOJ threshold constants and the DOJ fixture's integrity.

HONESTY NOTE (2026-09-21): nothing in this file runs the detection engine.
TestDOJThresholdConstantsOnly compares each case's hand-entered markup_pct to
the DOJProsecutionThresholds constants. That proves the constants are set where
the cases sit; it does not prove the engine would flag the cases. The engine
gate is tests/test_doj_blind_e2e.py, which drives InstitutionalPipeline ->
score_contract -> assign_tier (the path the worker behind the API runs) over
synthetic contracts built from each case.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))
from institutional_statistical_rigor import DOJProsecutionThresholds, FraudTier

from tests.doj_fixture import (
    DOJ_CASES_PATH, DOJ_CASES_SHA256, DOJ_CASES_EXPECTED_COUNT, verify_doj_cases_file,
)


class TestDOJFixtureIntegrity:
    """The 10-case DOJ fixture must be present and byte-identical to the pin.

    This is the fail-closed gate: a missing or altered fixture is a FAILED
    test here, and an ERROR in every test that depends on the doj_cases
    fixture. Neither can be skipped.
    """

    def test_fixture_present_and_unaltered(self):
        raw = verify_doj_cases_file()  # pytest.fail()s with a reason if not
        assert hashlib.sha256(raw).hexdigest() == DOJ_CASES_SHA256
        assert os.path.basename(DOJ_CASES_PATH) == 'prosecuted_cases.json'

    def test_fixture_shape(self, doj_cases):
        assert len(doj_cases) == DOJ_CASES_EXPECTED_COUNT
        required = {'case_id', 'vendor', 'agency', 'markup_pct', 'settlement',
                    'contract_amount', 'fraud_type', 'legal_basis', 'description'}
        for case in doj_cases:
            missing = required - set(case)
            assert not missing, f"{case.get('case_id')} missing {missing}"

    def test_fixture_composition_is_the_claimed_nine_plus_one(self, doj_cases):
        """9 price-fraud cases (markup > 0) and 1 non-price case (markup == 0).

        These are the '9 positives, 1 excluded' of docs/evaluation_report.json.
        """
        price = [c for c in doj_cases if c['markup_pct'] > 0]
        non_price = [c for c in doj_cases if c['markup_pct'] == 0]
        assert len(price) == 9
        assert len(non_price) == 1
        assert non_price[0]['case_id'] == 'US_v_General_Dynamics_2011'


class TestDOJThresholds:
    """Verify DOJ prosecution thresholds are correctly set."""

    def test_extreme_markup(self):
        assert DOJProsecutionThresholds.EXTREME_MARKUP == 300

    def test_high_markup(self):
        assert DOJProsecutionThresholds.HIGH_MARKUP == 200

    def test_elevated_markup(self):
        assert DOJProsecutionThresholds.ELEVATED_MARKUP == 150

    def test_investigation_worthy(self):
        assert DOJProsecutionThresholds.INVESTIGATION_WORTHY == 75

    def test_threshold_ordering(self):
        """Thresholds must be strictly ordered."""
        assert (DOJProsecutionThresholds.INVESTIGATION_WORTHY <
                DOJProsecutionThresholds.ELEVATED_MARKUP <
                DOJProsecutionThresholds.HIGH_MARKUP <
                DOJProsecutionThresholds.EXTREME_MARKUP)

    def test_red_flag_confidence(self):
        assert DOJProsecutionThresholds.RED_FLAG_CONFIDENCE == 95

    def test_yellow_flag_confidence(self):
        assert DOJProsecutionThresholds.YELLOW_FLAG_CONFIDENCE == 85

    def test_bootstrap_iterations(self):
        assert DOJProsecutionThresholds.BOOTSTRAP_ITERATIONS == 10000

    def test_base_fraud_rate(self):
        assert DOJProsecutionThresholds.BASE_FRAUD_RATE == 0.02


class TestFraudTierEnum:
    """Verify fraud tier definitions."""

    def test_tier_values(self):
        assert FraudTier.RED.value == "RED"
        assert FraudTier.YELLOW.value == "YELLOW"
        assert FraudTier.GREEN.value == "GREEN"
        assert FraudTier.GRAY.value == "GRAY"

    def test_four_tiers_exist(self):
        assert len(FraudTier) == 4


class TestDOJThresholdConstantsOnly:
    """Threshold-constant tests. THESE DO NOT RUN THE ENGINE.

    Renamed 2026-09-21 from TestDOJCaseValidation. Each test compares a
    case's hand-entered markup_pct against a constant in
    DOJProsecutionThresholds. That is a statement about where the constants
    were set, not evidence that the scoring engine flags the case. The
    engine-driven equivalents live in tests/test_doj_blind_e2e.py.
    """

    def test_all_price_fraud_cases_detected(self, doj_cases):
        """Every DOJ case with a markup should exceed INVESTIGATION_WORTHY."""
        price_cases = [c for c in doj_cases if c['markup_pct'] > 0]
        for case in price_cases:
            assert case['markup_pct'] >= DOJProsecutionThresholds.INVESTIGATION_WORTHY, \
                f"Case {case['case_id']} with {case['markup_pct']}% markup below detection threshold"

    def test_extreme_cases_red_tier(self, doj_cases):
        """Cases with >300% markup should map to RED tier."""
        extreme = [c for c in doj_cases if c['markup_pct'] >= 300]
        assert len(extreme) >= 2  # Oracle (350%) and Boeing (450%)
        for case in extreme:
            assert case['markup_pct'] >= DOJProsecutionThresholds.EXTREME_MARKUP

    def test_detection_rate_above_80_percent(self, doj_cases):
        """Should detect at least 80% of DOJ price fraud cases."""
        price_cases = [c for c in doj_cases if c['markup_pct'] > 0]
        detected = [c for c in price_cases if c['markup_pct'] >= DOJProsecutionThresholds.INVESTIGATION_WORTHY]
        rate = len(detected) / len(price_cases)
        assert rate >= 0.80, f"Detection rate {rate:.0%} below 80% threshold"

    def test_total_settlement_value_coverage(self, doj_cases):
        """Should cover >90% of total settlement value for price cases."""
        price_cases = [c for c in doj_cases if c['markup_pct'] > 0]
        total_value = sum(c['settlement'] for c in price_cases)
        detected_value = sum(
            c['settlement'] for c in price_cases
            if c['markup_pct'] >= DOJProsecutionThresholds.INVESTIGATION_WORTHY
        )
        coverage = detected_value / total_value
        assert coverage >= 0.90, f"Value coverage {coverage:.0%} below 90%"

    def test_non_price_cases_acknowledged(self, doj_cases):
        """Cases with 0% markup are non-price fraud — system should not claim to detect them."""
        non_price = [c for c in doj_cases if c['markup_pct'] == 0]
        assert len(non_price) >= 1  # General Dynamics false certification
