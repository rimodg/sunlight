"""
Tests for credibility hardening: data normalization, case packets,
evaluation framework, and messy input resilience.
"""
import sys
import os
import json
import sqlite3
import tempfile
import hashlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from data_normalization import (
    normalize_vendor_name, normalize_contract_id, normalize_date,
    normalize_amount, normalize_record, should_downgrade_severity,
)
from case_packet import (
    generate_case_packet, render_case_packet_md, _classify_typology,
    DISCLAIMER,
)
from evaluation import (
    compute_pr_curve, bootstrap_metric_ci,
    CI_GATE_PRECISION_MIN, CI_GATE_RECALL_MIN, CI_GATE_FLAGS_PER_1K_MAX,
)
from governance import RULEPACK_REGISTRY, compute_rulepack_hash


# =========================================================================
# Data Normalization Tests
# =========================================================================

class TestVendorNormalization:
    def test_clean_name(self):
        name, conf = normalize_vendor_name("Acme Defense Systems")
        assert conf >= 70
        assert name  # Non-empty

    def test_strips_llc(self):
        name, _ = normalize_vendor_name("Acme Defense LLC")
        assert 'LLC' not in name

    def test_strips_inc(self):
        name, _ = normalize_vendor_name("Boeing Inc.")
        assert 'INC' not in name
        assert 'BOEING' in name

    def test_strips_corporation(self):
        name, _ = normalize_vendor_name("Oracle Corporation")
        assert 'CORPORATION' not in name

    def test_extra_whitespace(self):
        name, conf = normalize_vendor_name("  Raytheon   Technologies  ")
        assert '  ' not in name
        assert conf <= 90

    def test_empty_string(self):
        name, conf = normalize_vendor_name("")
        assert name == ''
        assert conf == 0

    def test_none_like(self):
        name, conf = normalize_vendor_name("   ")
        assert name == ''
        assert conf == 0

    def test_very_short_name(self):
        name, conf = normalize_vendor_name("AB")
        assert conf <= 30

    def test_preserves_core_name(self):
        name, _ = normalize_vendor_name("Lockheed Martin Corporation")
        assert 'LOCKHEED' in name
        assert 'MARTIN' in name


class TestContractIdNormalization:
    def test_clean_id(self):
        cid, conf = normalize_contract_id("DOD-2026-001")
        assert conf >= 80
        assert cid

    def test_whitespace_trimming(self):
        cid, conf = normalize_contract_id("  DOD-001  ")
        assert cid == "DOD-001"

    def test_empty_id(self):
        cid, conf = normalize_contract_id("")
        assert conf == 0

    def test_special_characters(self):
        cid, conf = normalize_contract_id("DOD@#2026")
        assert conf <= 50
        # Should still produce something
        assert cid

    def test_spaces_to_dashes(self):
        cid, _ = normalize_contract_id("DOD 2026 001")
        assert ' ' not in cid


class TestDateNormalization:
    def test_iso_format(self):
        dt, conf = normalize_date("2026-01-15")
        assert dt == "2026-01-15"
        assert conf == 100

    def test_us_format(self):
        dt, conf = normalize_date("01/15/2026")
        assert dt == "2026-01-15"
        assert conf == 90

    def test_long_month(self):
        dt, conf = normalize_date("January 15, 2026")
        assert dt is not None
        assert '2026' in dt

    def test_empty(self):
        dt, conf = normalize_date("")
        assert dt is None
        assert conf == 0

    def test_garbage(self):
        dt, conf = normalize_date("not a date")
        assert dt is None
        assert conf == 0

    def test_compact(self):
        dt, conf = normalize_date("20260115")
        assert dt is not None


class TestAmountNormalization:
    def test_integer(self):
        amt, conf, curr = normalize_amount(5000000)
        assert amt == 5000000
        assert conf == 100

    def test_float(self):
        amt, conf, _ = normalize_amount(5000000.50)
        assert amt == 5000000.50

    def test_string_with_dollar(self):
        amt, conf, curr = normalize_amount("$5,000,000")
        assert amt == 5000000
        assert curr == 'USD'

    def test_millions_suffix(self):
        amt, conf, _ = normalize_amount("5M")
        assert amt == 5000000
        assert conf == 70

    def test_thousands_suffix(self):
        amt, conf, _ = normalize_amount("500K")
        assert amt == 500000

    def test_euro_symbol(self):
        amt, conf, curr = normalize_amount("\u20ac1000000")
        assert curr == 'EUR'

    def test_empty(self):
        amt, conf, _ = normalize_amount("")
        assert amt is None
        assert conf == 0

    def test_none(self):
        amt, conf, _ = normalize_amount(None)
        assert amt is None
        assert conf == 0

    def test_garbage(self):
        amt, conf, _ = normalize_amount("not a number")
        assert conf == 0

    def test_parentheses_negative(self):
        amt, conf, _ = normalize_amount("($500,000)")
        assert amt == -500000


class TestRecordNormalization:
    def test_complete_record(self):
        record = {
            'contract_id': 'DOD-2026-001',
            'vendor_name': 'Acme Defense LLC',
            'agency_name': 'Department of Defense',
            'award_amount': '$5,000,000',
            'description': 'IT systems upgrade',
            'start_date': '2026-01-15',
        }
        norm, confs = normalize_record(record)
        assert norm['contract_id']
        assert norm['vendor_name']
        assert norm['award_amount'] == 5000000
        assert confs['overall'] > 50

    def test_messy_record(self):
        record = {
            'contract_id': '  weird id @#$ ',
            'vendor_name': '  "ACME"  inc.  ',
            'agency_name': 'dod',
            'award_amount': '5M',
            'description': '',
            'start_date': 'not-a-date',
        }
        norm, confs = normalize_record(record)
        assert norm['contract_id']  # Cleaned up
        assert confs['contract_id'] <= 50  # Low confidence
        assert confs['start_date'] == 0

    def test_missing_fields(self):
        record = {'contract_id': 'X'}
        norm, confs = normalize_record(record)
        assert confs['vendor_name'] == 0
        assert confs['award_amount'] == 0
        assert confs['overall'] < 30

    def test_currency_formats(self):
        record = {
            'contract_id': 'TEST-001',
            'vendor_name': 'Test Corp',
            'agency_name': 'DOD',
            'award_amount': '\u00a31,500,000',
        }
        norm, confs = normalize_record(record)
        assert norm['award_amount'] == 1500000
        assert norm['currency'] == 'GBP'


class TestSeverityDowngrade:
    def test_low_confidence_downgrades_to_gray(self):
        tier, reason = should_downgrade_severity({'overall': 20}, 'RED')
        assert tier == 'GRAY'
        assert 'insufficient data' in reason.lower()

    def test_moderate_confidence_downgrades_red(self):
        tier, reason = should_downgrade_severity({'overall': 40}, 'RED')
        assert tier == 'YELLOW'
        assert reason  # Has explanation

    def test_high_confidence_no_downgrade(self):
        tier, reason = should_downgrade_severity({'overall': 90}, 'RED')
        assert tier == 'RED'
        assert reason == ''

    def test_green_stays_green(self):
        tier, reason = should_downgrade_severity({'overall': 40}, 'GREEN')
        assert tier == 'GREEN'


# =========================================================================
# Case Packet Tests
# =========================================================================

@pytest.fixture
def scored_db():
    """Create a temp DB with scored contracts for case packet testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    c = conn.cursor()

    c.execute("""CREATE TABLE contracts (
        contract_id TEXT PRIMARY KEY, award_amount REAL,
        vendor_name TEXT, agency_name TEXT, description TEXT,
        start_date TEXT, location TEXT, raw_data TEXT, raw_data_hash TEXT
    )""")
    c.execute("""CREATE TABLE contract_scores (
        score_id TEXT PRIMARY KEY, contract_id TEXT, run_id TEXT,
        fraud_tier TEXT, tier TEXT, triage_priority INTEGER,
        confidence_score INTEGER, raw_pvalue REAL, fdr_adjusted_pvalue REAL,
        survives_fdr INTEGER, markup_pct REAL, markup_ci_lower REAL,
        markup_ci_upper REAL, raw_zscore REAL, log_zscore REAL,
        bootstrap_percentile REAL, percentile_ci_lower REAL,
        percentile_ci_upper REAL, bayesian_prior REAL,
        bayesian_likelihood_ratio REAL, bayesian_posterior REAL,
        comparable_count INTEGER, insufficient_comparables INTEGER,
        selection_params_json TEXT, scored_at TEXT, analyzed_at TEXT,
        UNIQUE(contract_id, run_id)
    )""")
    c.execute("""CREATE TABLE political_donations (
        vendor_name TEXT, recipient_name TEXT, amount REAL,
        date TEXT, cycle TEXT, source TEXT
    )""")

    # Insert test contracts
    for cid, amt, vendor in [
        ('FLAG-001', 35000000, 'SUSPECT_CORP'),
        ('CLEAN-001', 5000000, 'NORMAL_CORP'),
        ('CLEAN-002', 6000000, 'SUSPECT_CORP'),
    ]:
        h = hashlib.sha256(f"{cid}:{amt}".encode()).hexdigest()
        c.execute("INSERT INTO contracts VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, amt, vendor, 'Department of Defense', 'Test', '2026-01-01', None, None, h))

    # Insert score for flagged contract
    c.execute(
        "INSERT INTO contract_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ('s1', 'FLAG-001', 'run_test', 'RED', 'RED', 10, 85, 0.001, 0.005, 1,
         350.0, 310.0, 390.0, 4.5, 3.8, 98.0, 95.0, 100.0,
         0.03, 15.0, 0.82, 15, 0, '{}',
         '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z'))

    # Political donation
    c.execute("INSERT INTO political_donations VALUES (?,?,?,?,?,?)",
              ('SUSPECT_CORP', 'Senate Committee', 250000, '2024-06-01', '2024', 'TEST'))

    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


class TestCasePacket:
    def test_generates_packet(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert 'error' not in packet
        assert packet['contract']['contract_id'] == 'FLAG-001'
        assert packet['assessment']['fraud_tier'] == 'RED'

    def test_includes_disclaimer(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert 'risk indicator' in packet['disclaimer'].lower()
        assert 'not allegation' in packet['disclaimer'].lower()

    def test_has_typologies(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert len(packet['triggered_typologies']) > 0
        assert packet['triggered_typologies'][0]['rule_id']
        assert packet['triggered_typologies'][0]['severity']

    def test_has_peer_comparison(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['peer_comparison']['available']
        assert 'risk indicator' in packet['peer_comparison']['interpretation'].lower()

    def test_has_vendor_linkages(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['vendor_linkages']['vendor_name'] == 'SUSPECT_CORP'
        assert packet['vendor_linkages']['political_donations']['count'] > 0

    def test_has_recommendations(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['recommendations']['risk_severity'] == 'RED'
        assert len(packet['recommendations']['next_steps']) > 0

    def test_has_disposition_fields(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['disposition']['status'] == 'PENDING_REVIEW'
        assert 'TRUE_POSITIVE' in str(packet['disposition']['disposition_options'])
        assert 'FALSE_POSITIVE' in str(packet['disposition']['disposition_options'])

    def test_has_snapshot_id(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['data_snapshot_id']
        assert len(packet['data_snapshot_id']) == 16

    def test_has_rulepack_version(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        assert packet['rulepack_version']

    def test_markdown_render(self, scored_db):
        packet = generate_case_packet(scored_db, 'FLAG-001')
        md = render_case_packet_md(packet)
        assert 'Case Packet' in md
        assert 'risk indicators, not allegations' in md
        assert 'FLAG-001' in md
        assert 'PENDING_REVIEW' in md

    def test_not_found(self, scored_db):
        packet = generate_case_packet(scored_db, 'NONEXISTENT')
        assert 'error' in packet


class TestTypologyClassification:
    def test_extreme_markup(self):
        score = {'markup_ci_lower': 350, 'bayesian_posterior': 0.9, 'percentile_ci_lower': 98}
        types = _classify_typology(score, {})
        rule_ids = [t['rule_id'] for t in types]
        assert 'PRICE-001' in rule_ids

    def test_no_typologies_for_green(self):
        score = {'markup_ci_lower': 10, 'bayesian_posterior': 0.1, 'percentile_ci_lower': 30}
        types = _classify_typology(score, {})
        assert len(types) == 0


# =========================================================================
# Evaluation Framework Tests
# =========================================================================

class TestPRCurve:
    def test_perfect_separation(self):
        y_true = [True, True, True, False, False, False]
        scores = [90, 85, 80, 20, 15, 10]
        pr = compute_pr_curve(y_true, scores)
        assert pr['pr_auc'] > 0.9

    def test_random_scores(self):
        y_true = [True, False, True, False]
        scores = [50, 50, 50, 50]
        pr = compute_pr_curve(y_true, scores)
        assert 'precision' in pr
        assert 'recall' in pr

    def test_returns_thresholds(self):
        y_true = [True, False]
        scores = [80, 20]
        pr = compute_pr_curve(y_true, scores)
        assert len(pr['thresholds']) > 0


class TestBootstrapCI:
    def test_produces_cis(self):
        y_true = [True] * 5 + [False] * 5
        y_pred = [True] * 4 + [False] + [True] + [False] * 4
        cis = bootstrap_metric_ci(y_true, y_pred, n_boot=500)
        assert 'precision' in cis
        assert 'recall' in cis
        assert cis['precision']['ci_lower'] <= cis['precision']['ci_upper']


class TestCIGateConstants:
    def test_thresholds_reasonable(self):
        assert 0 < CI_GATE_PRECISION_MIN < 1
        assert 0 < CI_GATE_RECALL_MIN < 1
        assert CI_GATE_FLAGS_PER_1K_MAX > 0


# =========================================================================
# Governance Tests
# =========================================================================

class TestRulepackVersioning:
    def test_registry_has_current_version(self):
        assert '2.0.0' in RULEPACK_REGISTRY

    def test_rulepack_hash_deterministic(self):
        h1 = compute_rulepack_hash('2.0.0')
        h2 = compute_rulepack_hash('2.0.0')
        assert h1 == h2

    def test_rulepack_hash_varies(self):
        h1 = compute_rulepack_hash('2.0.0')
        h2 = compute_rulepack_hash('1.0.0')
        assert h1 != h2

    def test_rulepack_has_required_fields(self):
        rp = RULEPACK_REGISTRY['2.0.0']
        assert 'rules' in rp
        assert 'thresholds' in rp
        assert 'version' in rp
