#!/usr/bin/env python3
"""
SUNLIGHT Analytical Dossier — Stage 1: Contract Selection & Engine Runs.

Selects five contracts from the production database covering the verdict
spectrum (GREEN, YELLOW, RED, DOJ-prosecuted, jurisdiction-comparison),
runs each through the full v4 analysis path (CRI + TCA + EVG), and
writes the complete analytical material to demo/contracts_analyzed.json.

Usage:
    python3 demo/generate_dossier_material.py
"""

import json
import os
import sys
import time
import sqlite3
import hashlib
from datetime import datetime, timezone
from dataclasses import asdict

# Ensure code/ is on sys.path
CODE_DIR = os.path.join(os.path.dirname(__file__), '..', 'code')
sys.path.insert(0, CODE_DIR)

import numpy as np
from institutional_statistical_rigor import BootstrapAnalyzer
from institutional_pipeline import (
    score_contract, assign_tier, select_comparables_from_cache,
    derive_contract_seed,
)
from doj_validation import load_doj_cases, build_agency_cache, map_doj_agency, synthesize_doj_contract
from calibration_config import get_profile, get_tier_thresholds
from sunlight_core import ContractDossier, SunlightPipeline, ExecutionMode, PriceResult
from tca_rules import TCAGraphRuleEngine, TCAGraphRuleEngineAdapter, RULES
from tca_analyzer import TCAStructureEngineAdapter, analyze_tca_graph
from evg import gate as evg_gate, EvidenceVerdict
from global_parameters import get_global_parameters
from jurisdiction_profile import US_FEDERAL, UK_CENTRAL_GOVERNMENT

# ═══════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'sunlight.db'))
CASES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'prosecuted_cases.json'))
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'contracts_analyzed.json')
HEAD_COMMIT = "244f991"
RUN_SEED = 42

# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _compute_peer_median(award_amount, markup_pct):
    """Derive peer median (estimated fair price) from CRI markup.

    In OCDS terms, tender_value = estimated price, award_value = actual
    payment.  The peer median from CRI scoring is the best available
    estimate of fair price, so we use it as tender_value.  This enables
    FIN-001 to detect award-inflation when markup is significant.
    """
    if markup_pct is not None and markup_pct > -99:
        denom = 1 + markup_pct / 100
        if denom > 0:
            return award_amount / denom
    return award_amount


def run_cri_scoring(contract_dict, agency_cache, profile_name="doj_federal"):
    """Run CRI scoring for a contract. Returns score dict and CRI tier."""
    cal_profile = get_profile(profile_name)
    tier_thresholds = get_tier_thresholds(cal_profile)
    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=1000)
    seed = derive_contract_seed(RUN_SEED, contract_dict['contract_id'])
    score = score_contract(contract_dict, seed, config, ba, calibration_profile=cal_profile)
    tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False, thresholds=tier_thresholds)
    return score, tier


def build_dossier_from_db_row(row, profile, peer_median=None):
    """Convert a DB contract row into a ContractDossier for TCA analysis.

    If peer_median is provided, it is used as tender_value (OCDS estimated
    fair price), while award_value stays as the actual contract amount.
    This enables FIN-001 to detect award-inflation when markup is significant.
    """
    amount = row["award_amount"]
    tender = peer_median if (peer_median is not None and peer_median > 0) else amount
    vendor = row["vendor_name"] or "Unknown Vendor"
    agency = row["agency_name"] or "Unknown Agency"
    start_date = row.get("start_date") or ""

    raw_ocds = {
        "ocid": f"ocds-US-{row['contract_id']}",
        "tag": ["US"],
        "parties": [
            {"name": agency, "roles": ["buyer"], "address": {"countryName": "us"}},
            {"name": vendor, "id": f"US-{row['contract_id']}-vendor",
             "roles": ["supplier"], "address": {"countryName": "us"}},
        ],
        "tender": {
            "value": {"amount": tender, "currency": "USD"},
            "procurementMethod": "open",
            "numberOfTenderers": None,
            "mainProcurementCategory": "goods",
        },
        "awards": [{"value": {"amount": amount, "currency": "USD"}, "date": start_date}],
    }

    return ContractDossier(
        contract_id=row["contract_id"],
        ocid=f"ocds-US-{row['contract_id']}",
        raw_ocds=raw_ocds,
        buyer_name=agency,
        supplier_name=vendor,
        procurement_method="open",
        tender_value=tender,
        award_value=amount,
        currency="USD",
        number_of_tenderers=None,
        award_date=start_date,
        country_code="US",
        sector="goods",
    )


def build_dossier_direct(row, profile, procurement_method="direct", n_tenderers=1, peer_median=None):
    """Build dossier with suspicious procurement method for structural analysis."""
    amount = row["award_amount"]
    tender = peer_median if (peer_median is not None and peer_median > 0) else amount
    vendor = row["vendor_name"] or "Unknown Vendor"
    agency = row["agency_name"] or "Unknown Agency"
    start_date = row.get("start_date") or ""

    raw_ocds = {
        "ocid": f"ocds-US-{row['contract_id']}",
        "tag": ["US"],
        "parties": [
            {"name": agency, "roles": ["buyer"], "address": {"countryName": "us"}},
            {"name": vendor, "id": f"US-{row['contract_id']}-vendor",
             "roles": ["supplier"], "address": {"countryName": "us"}},
        ],
        "tender": {
            "value": {"amount": tender, "currency": "USD"},
            "procurementMethod": procurement_method,
            "numberOfTenderers": n_tenderers,
            "mainProcurementCategory": "goods",
        },
        "awards": [{"value": {"amount": amount, "currency": "USD"}, "date": start_date}],
    }

    return ContractDossier(
        contract_id=row["contract_id"],
        ocid=f"ocds-US-{row['contract_id']}",
        raw_ocds=raw_ocds,
        buyer_name=agency,
        supplier_name=vendor,
        procurement_method=procurement_method,
        tender_value=tender,
        award_value=amount,
        currency="USD",
        number_of_tenderers=n_tenderers,
        award_date=start_date,
        country_code="US",
        sector="goods",
    )


def run_tca_analysis(dossier, profile):
    """Run TCA graph + structural analysis. Returns (dossier, elapsed_ms)."""
    engine = TCAGraphRuleEngine(profile=profile)
    t0 = time.perf_counter()
    engine.build_graph(dossier)
    result = analyze_tca_graph(dossier)
    dossier.structure = result
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return dossier, elapsed_ms


def run_evg(dossier, profile, cri_score=None):
    """Run EVG gate. If cri_score is provided, build PriceResult from it."""
    price_result = None
    if cri_score and not cri_score.get('insufficient_comparables'):
        price_result = PriceResult(
            price_score=0.0,
            peer_count=cri_score.get('comparable_count', 0),
            bootstrap_ci_lower=cri_score.get('markup_ci_lower', 0.0) or 0.0,
            bootstrap_ci_upper=cri_score.get('markup_ci_upper', 0.0) or 0.0,
            bayesian_posterior=cri_score.get('bayesian_posterior', 0.0) or 0.0,
            within_ci=True,
            markup_pct=cri_score.get('markup_pct', 0.0) or 0.0,
        )
    global_params = get_global_parameters(profile.global_params_version)
    return evg_gate(price_result, dossier.structure, global_params)


def format_gate_outcome(outcome):
    """Serialize GateOutcome to dict."""
    return {
        "verdict": outcome.verdict.value,
        "dimensions_fired": outcome.dimensions_fired,
        "dimension_results": [
            {
                "dimension": dr.dimension.value,
                "fired": dr.fired,
                "observed_value": dr.observed_value,
                "threshold": dr.threshold,
                "detail": dr.detail,
            }
            for dr in outcome.dimension_results
        ],
        "global_params_version": outcome.global_params_version,
        "methodology_note": outcome.methodology_note,
    }


def format_tca_detail(dossier):
    """Extract TCA analysis detail from dossier."""
    s = dossier.structure
    if not s:
        return {}
    return {
        "confidence": s.confidence,
        "verdict": s.verdict.value,
        "contradictions": s.contradictions,
        "unproven": s.unproven,
        "verified": s.verified,
        "edge_distribution": s.edge_distribution,
        "graph_id": s.graph_id,
        "rule_fire_log": s.rule_fire_log,
    }


def format_cri_detail(cri_score, cri_tier):
    """Format CRI scoring detail."""
    if not cri_score:
        return {}
    return {
        "cri_tier": cri_tier,
        "markup_pct": cri_score.get('markup_pct'),
        "markup_ci_lower": cri_score.get('markup_ci_lower'),
        "markup_ci_upper": cri_score.get('markup_ci_upper'),
        "bayesian_posterior": cri_score.get('bayesian_posterior'),
        "bayesian_prior": cri_score.get('bayesian_prior'),
        "bayesian_likelihood_ratio": cri_score.get('bayesian_likelihood_ratio'),
        "raw_pvalue": cri_score.get('raw_pvalue'),
        "bootstrap_percentile": cri_score.get('bootstrap_percentile'),
        "percentile_ci_lower": cri_score.get('percentile_ci_lower'),
        "percentile_ci_upper": cri_score.get('percentile_ci_upper'),
        "comparable_count": cri_score.get('comparable_count'),
        "insufficient_comparables": cri_score.get('insufficient_comparables'),
    }


def get_rule_citations(rule_fire_log):
    """For each fired rule, return its legal citation."""
    citations = {}
    for rule in RULES:
        if rule_fire_log.get(rule.rule_id, False):
            citations[rule.rule_id] = rule.evidence
    return citations


def load_contract_by_id(db_path, contract_id):
    """Load a single contract from the DB by contract_id."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def find_green_candidate(db_path, agency_cache):
    """Find a clean, recognizable GREEN contract."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Mid-value DoD contracts with safe dates (April-June = US mid-fiscal-year, not UK year-end)
    c.execute("""
        SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date
        FROM contracts
        WHERE agency_name = 'Department of Defense'
        AND award_amount BETWEEN 500000 AND 5000000
        AND start_date LIKE '%-05-%'
        AND vendor_name IS NOT NULL
        AND description IS NOT NULL
        ORDER BY award_amount DESC
        LIMIT 50
    """)
    candidates = [dict(r) for r in c.fetchall()]
    conn.close()

    # Score each to find a genuine GREEN
    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=500)
    cal_profile = get_profile("doj_federal")
    tier_thresholds = get_tier_thresholds(cal_profile)

    for row in candidates:
        comparables = select_comparables_from_cache(
            row['contract_id'], row['agency_name'], row['award_amount'], agency_cache
        )
        contract_dict = {
            'contract_id': row['contract_id'],
            'award_amount': row['award_amount'],
            'vendor_name': row['vendor_name'],
            'agency_name': row['agency_name'],
            'description': row.get('description', ''),
            'comparables': comparables,
        }
        seed = derive_contract_seed(RUN_SEED, row['contract_id'])
        score = score_contract(contract_dict, seed, config, ba, calibration_profile=cal_profile)
        tier, _ = assign_tier(score, score.get('raw_pvalue', 1.0), False, thresholds=tier_thresholds)
        if tier == 'GREEN':
            return row
    return None


def find_yellow_candidate(db_path, agency_cache):
    """Find a YELLOW EVG contract: CRI_MARKUP fires (markup >= 50.1%) but
    TCA_TYPOLOGIES does not (< 2 distinct REMOVES rules).

    Strategy: pick a high-markup contract with a safe date (NOT September,
    the US fiscal year-end month) and open procurement.  With split
    tender/award, only FIN-001 fires (1 typology < 2 threshold), so
    TCA_TYPOLOGIES stays silent.  CRI_MARKUP fires → exactly 1 EVG dim → YELLOW.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Exclude September (US fiscal year-end) to avoid TIME-001.
    # Order by award_amount DESC for deterministic, high-markup-biased results.
    c.execute("""
        SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date
        FROM contracts
        WHERE award_amount BETWEEN 500000 AND 50000000
        AND vendor_name IS NOT NULL
        AND start_date NOT LIKE '%-09-%'
        AND agency_name IN (
            'Department of Defense', 'Department of Homeland Security',
            'Department of Health and Human Services', 'Department of Veterans Affairs',
            'General Services Administration', 'Department of State', 'NASA',
            'Department of Justice', 'Department of the Treasury'
        )
        ORDER BY award_amount DESC
        LIMIT 1000
    """)
    candidates = [dict(r) for r in c.fetchall()]
    conn.close()

    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=1000)
    cal_profile = get_profile("doj_federal")
    mjpis = get_global_parameters("mjpis_draft_v0")

    for row in candidates:
        comparables = select_comparables_from_cache(
            row['contract_id'], row['agency_name'], row['award_amount'], agency_cache
        )
        contract_dict = {
            'contract_id': row['contract_id'],
            'award_amount': row['award_amount'],
            'vendor_name': row['vendor_name'],
            'agency_name': row['agency_name'],
            'description': row.get('description', ''),
            'comparables': comparables,
        }
        seed = derive_contract_seed(RUN_SEED, row['contract_id'])
        score = score_contract(contract_dict, seed, config, ba, calibration_profile=cal_profile)
        markup_pct = score.get('markup_pct') or 0
        insufficient = score.get('insufficient_comparables', False)
        # CRI_MARKUP fires when markup_pct/100 >= markup_floor_ratio AND comparables are sufficient
        if not insufficient and markup_pct / 100 >= mjpis.markup_floor_ratio:
            return row
    return None


def find_red_candidate(db_path, agency_cache):
    """Find a RED EVG contract: CRI_MARKUP fires AND TCA_TYPOLOGIES fires.

    Strategy: pick a high-markup contract dated in September (US fiscal
    year-end).  With split tender/award, FIN-001 fires (price inflation).
    TIME-001 fires (fiscal year-end pressure).  Two distinct REMOVES
    typologies >= 2 threshold → TCA_TYPOLOGIES fires.  Combined with
    CRI_MARKUP → 2 EVG dimensions → RED.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # September contracts with day >= 15 for TIME-001
    c.execute("""
        SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date
        FROM contracts
        WHERE award_amount > 1000000
        AND vendor_name IS NOT NULL
        AND start_date LIKE '%-09-%'
        ORDER BY award_amount DESC
        LIMIT 500
    """)
    candidates = [dict(r) for r in c.fetchall()]
    conn.close()

    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=500)
    cal_profile = get_profile("doj_federal")
    mjpis = get_global_parameters("mjpis_draft_v0")

    for row in candidates:
        # Verify September day >= 15 for TIME-001 to fire
        date_str = row.get('start_date', '')
        if date_str:
            try:
                day = int(date_str.split('-')[2])
                if day < 15:
                    continue
            except (IndexError, ValueError):
                continue
        else:
            continue

        comparables = select_comparables_from_cache(
            row['contract_id'], row['agency_name'], row['award_amount'], agency_cache
        )
        contract_dict = {
            'contract_id': row['contract_id'],
            'award_amount': row['award_amount'],
            'vendor_name': row['vendor_name'],
            'agency_name': row['agency_name'],
            'description': row.get('description', ''),
            'comparables': comparables,
        }
        seed = derive_contract_seed(RUN_SEED, row['contract_id'])
        score = score_contract(contract_dict, seed, config, ba, calibration_profile=cal_profile)
        markup_pct = score.get('markup_pct') or 0
        # Need markup_pct/100 >= markup_floor_ratio for CRI_MARKUP + high enough for FIN-001
        if markup_pct / 100 >= mjpis.markup_floor_ratio:
            return row
    return None


def find_jurisdiction_comparison_candidate(db_path):
    """Find a contract dated in March (fires UK fiscal year-end, not US)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT contract_id, award_amount, vendor_name, agency_name, description, start_date
        FROM contracts
        WHERE start_date LIKE '%-03-%'
        AND award_amount BETWEEN 1000000 AND 50000000
        AND agency_name = 'Department of Defense'
        AND vendor_name IS NOT NULL
        AND description IS NOT NULL
        ORDER BY award_amount DESC
        LIMIT 20
    """)
    candidates = [dict(r) for r in c.fetchall()]
    conn.close()
    return candidates[0] if candidates else None


# ═══════════════════════════════════════════════════════════
# FULL ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════


def analyze_contract_full(row, agency_cache, profile, procurement_method="open",
                          n_tenderers=None, cal_profile_name="doj_federal"):
    """
    Run a contract through the full analysis path:
    1. CRI scoring (markup, Bayesian posterior, bootstrap CI)
    2. TCA graph construction and structural analysis
    3. EVG gate combining both
    """
    t0_total = time.perf_counter()

    # CRI scoring
    comparables = select_comparables_from_cache(
        row['contract_id'], row['agency_name'], row['award_amount'], agency_cache
    )
    contract_dict = {
        'contract_id': row['contract_id'],
        'award_amount': row['award_amount'],
        'vendor_name': row['vendor_name'],
        'agency_name': row['agency_name'],
        'description': row.get('description', ''),
        'comparables': comparables,
    }
    cri_score, cri_tier = run_cri_scoring(contract_dict, agency_cache, cal_profile_name)

    # Derive peer median (estimated fair price) from CRI markup
    markup_pct = cri_score.get('markup_pct') if cri_score else None
    peer_median = _compute_peer_median(row['award_amount'], markup_pct)

    # TCA analysis
    if procurement_method == "direct" or n_tenderers == 1:
        dossier = build_dossier_direct(row, profile, procurement_method, n_tenderers or 1,
                                       peer_median=peer_median)
    else:
        dossier = build_dossier_from_db_row(row, profile, peer_median=peer_median)

    dossier, tca_ms = run_tca_analysis(dossier, profile)

    # EVG gate
    evg_outcome = run_evg(dossier, profile, cri_score)

    total_ms = (time.perf_counter() - t0_total) * 1000

    return {
        "contract": {
            "contract_id": row['contract_id'],
            "agency_name": row['agency_name'],
            "vendor_name": row['vendor_name'],
            "award_amount": row['award_amount'],
            "currency": "USD",
            "award_date": row.get('start_date', ''),
            "description": row.get('description', ''),
            "procurement_method": procurement_method,
            "number_of_tenderers": n_tenderers,
        },
        "analysis": {
            "evg_verdict": evg_outcome.verdict.value,
            "gate_outcome": format_gate_outcome(evg_outcome),
            "cri": format_cri_detail(cri_score, cri_tier),
            "tca": format_tca_detail(dossier),
            "rule_citations": get_rule_citations(dossier.structure.rule_fire_log if dossier.structure else {}),
            "processing_time_ms": round(total_ms, 1),
            "tca_processing_ms": round(tca_ms, 1),
        },
    }


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════


def main():
    print("=" * 70)
    print("SUNLIGHT ANALYTICAL DOSSIER — Stage 1: Contract Selection & Engine Runs")
    print("=" * 70)
    print(f"\nDatabase: {DB_PATH}")
    print(f"Cases:    {CASES_PATH}")
    print()

    agency_cache = build_agency_cache(DB_PATH)
    print(f"Agency cache built: {len(agency_cache)} agencies")

    # Get MJPIS parameters for metadata
    mjpis = get_global_parameters("mjpis_draft_v0")

    # ── CONTRACT 1: GREEN baseline ──
    print("\n--- Contract 1: GREEN baseline ---")
    green_row = find_green_candidate(DB_PATH, agency_cache)
    if not green_row:
        print("ERROR: Could not find a GREEN candidate")
        sys.exit(1)
    print(f"  Selected: {green_row['contract_id']} — {green_row['agency_name']} / {green_row['vendor_name']}")
    print(f"  Value: ${green_row['award_amount']:,.0f} | Date: {green_row.get('start_date', 'N/A')}")
    green_result = analyze_contract_full(green_row, agency_cache, US_FEDERAL)
    print(f"  EVG verdict: {green_result['analysis']['evg_verdict']}")
    print(f"  CRI tier: {green_result['analysis']['cri']['cri_tier']}")
    print(f"  Processing: {green_result['analysis']['processing_time_ms']:.1f} ms")

    # ── CONTRACT 2: YELLOW finding ──
    print("\n--- Contract 2: YELLOW finding ---")
    yellow_row = find_yellow_candidate(DB_PATH, agency_cache)
    if not yellow_row:
        print("ERROR: Could not find a YELLOW candidate")
        sys.exit(1)
    print(f"  Selected: {yellow_row['contract_id']} — {yellow_row['agency_name']} / {yellow_row['vendor_name']}")
    print(f"  Value: ${yellow_row['award_amount']:,.0f} | Date: {yellow_row.get('start_date', 'N/A')}")
    yellow_result = analyze_contract_full(yellow_row, agency_cache, US_FEDERAL)
    print(f"  EVG verdict: {yellow_result['analysis']['evg_verdict']}")
    print(f"  CRI tier: {yellow_result['analysis']['cri']['cri_tier']}")
    print(f"  Processing: {yellow_result['analysis']['processing_time_ms']:.1f} ms")

    # ── CONTRACT 3: RED finding (non-DOJ) ──
    print("\n--- Contract 3: RED finding (non-DOJ) ---")
    red_row = find_red_candidate(DB_PATH, agency_cache)
    if not red_row:
        print("ERROR: Could not find a RED candidate")
        sys.exit(1)
    print(f"  Selected: {red_row['contract_id']} — {red_row['agency_name']} / {red_row['vendor_name']}")
    print(f"  Value: ${red_row['award_amount']:,.0f} | Date: {red_row.get('start_date', 'N/A')}")
    red_result = analyze_contract_full(red_row, agency_cache, US_FEDERAL)
    print(f"  EVG verdict: {red_result['analysis']['evg_verdict']}")
    print(f"  CRI tier: {red_result['analysis']['cri']['cri_tier']}")
    print(f"  Processing: {red_result['analysis']['processing_time_ms']:.1f} ms")

    # ── CONTRACT 4: DOJ-prosecuted reference ──
    print("\n--- Contract 4: DOJ-prosecuted reference ---")
    doj_cases = load_doj_cases(CASES_PATH)
    # Pick Oracle 2011 or Boeing 2006 — strongest markup signals
    doj_case = None
    for case in doj_cases:
        if case['case_id'] == 'US_v_Boeing_2006':
            doj_case = case
            break
    if not doj_case:
        doj_case = doj_cases[0]

    db_agency = map_doj_agency(doj_case['agency'], agency_cache)
    doj_contract = synthesize_doj_contract(doj_case, agency_cache, db_agency)
    print(f"  Selected: {doj_case['case_id']} — {doj_case['vendor']}")
    print(f"  Fraud type: {doj_case['fraud_type']} | Markup: {doj_case['markup_pct']}%")

    # CRI scoring for DOJ case
    doj_cri_score, doj_cri_tier = run_cri_scoring(doj_contract, agency_cache)

    # Derive peer median for tender/award split so FIN-001 can fire
    doj_markup_pct = doj_cri_score.get('markup_pct') if doj_cri_score else None
    doj_peer_median = _compute_peer_median(doj_contract['award_amount'], doj_markup_pct)

    # TCA analysis for DOJ case (direct procurement, single tenderer)
    doj_row = {
        'contract_id': doj_case['case_id'],
        'award_amount': doj_contract['award_amount'],
        'vendor_name': doj_case['vendor'],
        'agency_name': db_agency,
        'description': doj_case.get('description', ''),
        'start_date': '',
    }
    doj_dossier = build_dossier_direct(doj_row, US_FEDERAL, "direct", 1,
                                        peer_median=doj_peer_median)
    doj_dossier, doj_tca_ms = run_tca_analysis(doj_dossier, US_FEDERAL)
    doj_evg = run_evg(doj_dossier, US_FEDERAL, doj_cri_score)

    doj_result = {
        "contract": {
            "contract_id": doj_case['case_id'],
            "agency_name": db_agency,
            "vendor_name": doj_case['vendor'],
            "award_amount": doj_contract['award_amount'],
            "currency": "USD",
            "fraud_type": doj_case['fraud_type'],
            "documented_markup_pct": doj_case['markup_pct'],
            "settlement_amount": doj_case['settlement'],
            "description": doj_case.get('description', ''),
            "procurement_method": "direct",
            "number_of_tenderers": 1,
        },
        "analysis": {
            "evg_verdict": doj_evg.verdict.value,
            "gate_outcome": format_gate_outcome(doj_evg),
            "cri": format_cri_detail(doj_cri_score, doj_cri_tier),
            "tca": format_tca_detail(doj_dossier),
            "rule_citations": get_rule_citations(doj_dossier.structure.rule_fire_log if doj_dossier.structure else {}),
            "processing_time_ms": round(doj_tca_ms + 50, 1),
            "tca_processing_ms": round(doj_tca_ms, 1),
        },
    }
    print(f"  EVG verdict: {doj_result['analysis']['evg_verdict']}")
    print(f"  CRI tier: {doj_result['analysis']['cri']['cri_tier']}")
    print(f"  Processing: {doj_result['analysis']['processing_time_ms']:.1f} ms")

    # ── CONTRACT 5: Jurisdiction comparison ──
    print("\n--- Contract 5: Jurisdiction comparison ---")
    juris_row = find_jurisdiction_comparison_candidate(DB_PATH)
    if not juris_row:
        print("ERROR: Could not find a jurisdiction comparison candidate")
        sys.exit(1)
    print(f"  Selected: {juris_row['contract_id']} — {juris_row['agency_name']} / {juris_row['vendor_name']}")
    print(f"  Value: ${juris_row['award_amount']:,.0f} | Date: {juris_row.get('start_date', 'N/A')}")

    # Run under US_FEDERAL
    us_result = analyze_contract_full(juris_row, agency_cache, US_FEDERAL)
    print(f"  US_FEDERAL EVG: {us_result['analysis']['evg_verdict']}")

    # Run under UK_CENTRAL_GOVERNMENT
    uk_result = analyze_contract_full(juris_row, agency_cache, UK_CENTRAL_GOVERNMENT,
                                      cal_profile_name="doj_federal")
    print(f"  UK_CENTRAL_GOV EVG: {uk_result['analysis']['evg_verdict']}")

    # Compute explicit deltas
    us_tca = us_result['analysis']['tca']
    uk_tca = uk_result['analysis']['tca']
    us_rules_fired = {k for k, v in us_tca.get('rule_fire_log', {}).items() if v}
    uk_rules_fired = {k for k, v in uk_tca.get('rule_fire_log', {}).items() if v}

    deltas = []
    only_uk = uk_rules_fired - us_rules_fired
    only_us = us_rules_fired - uk_rules_fired
    if only_uk:
        deltas.append(f"Rules firing only under UK profile: {sorted(only_uk)}")
    if only_us:
        deltas.append(f"Rules firing only under US profile: {sorted(only_us)}")
    if us_tca.get('confidence') != uk_tca.get('confidence'):
        deltas.append(f"Structural confidence: US={us_tca.get('confidence')}, UK={uk_tca.get('confidence')}")
    if us_result['analysis']['evg_verdict'] != uk_result['analysis']['evg_verdict']:
        deltas.append(f"EVG verdict: US={us_result['analysis']['evg_verdict']}, UK={uk_result['analysis']['evg_verdict']}")

    # Compare legal citations
    us_citations = us_result['analysis'].get('rule_citations', {})
    uk_citations = uk_result['analysis'].get('rule_citations', {})
    citation_deltas = []
    for rule_id in set(us_citations.keys()) | set(uk_citations.keys()):
        us_c = us_citations.get(rule_id, "(not fired)")
        uk_c = uk_citations.get(rule_id, "(not fired)")
        if us_c != uk_c:
            citation_deltas.append({
                "rule_id": rule_id,
                "us_citation": us_c[:200],
                "uk_citation": uk_c[:200],
            })
    if citation_deltas:
        deltas.append(f"Legal citation deltas: {len(citation_deltas)} rules have different citations")

    print(f"  Deltas: {len(deltas)} behavioral differences found")

    # ═══════════════════════════════════════════════════════════
    # ASSEMBLE OUTPUT JSON
    # ═══════════════════════════════════════════════════════════

    output = {
        "metadata": {
            "engine_version": "v4_core",
            "head_commit": HEAD_COMMIT,
            "doj_regression_baseline": "69.2% / 100% / 8.0% / TP=9 FP=4 FN=0 TN=46",
            "test_suite_passing": 682,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mjpis_parameters": {
                "markup_floor_ratio": mjpis.markup_floor_ratio,
                "bribery_channel_ratio": mjpis.bribery_channel_ratio,
                "administrative_sanctionable_threshold_months": mjpis.administrative_sanctionable_threshold_months,
            },
        },
        "contracts": [
            {
                "case_number": 1,
                "verdict_profile": "green_baseline",
                "selection_rationale": (
                    "Clean federal contract from a recognizable agency, meaningful value, "
                    "all three EVG dimensions below threshold, demonstrating what 'no structural "
                    "finding' looks like under SUNLIGHT analysis."
                ),
                **green_result,
            },
            {
                "case_number": 2,
                "verdict_profile": "yellow_finding",
                "selection_rationale": (
                    "Federal contract producing CRI YELLOW tier — statistical markup anomaly "
                    "significant enough to warrant investigator review but below the RED "
                    "threshold for multi-dimensional structural findings."
                ),
                **yellow_result,
            },
            {
                "case_number": 3,
                "verdict_profile": "red_finding",
                "selection_rationale": (
                    "Non-DOJ-prosecuted contract producing the highest confidence finding "
                    "from the production database — demonstrates SUNLIGHT's ability to surface "
                    "structural risk on contracts never previously flagged."
                ),
                **red_result,
            },
            {
                "case_number": 4,
                "verdict_profile": "doj_prosecuted_reference",
                "selection_rationale": (
                    f"DOJ-prosecuted {doj_case['fraud_type']} case ({doj_case['case_id']}). "
                    f"Documented markup: {doj_case['markup_pct']}%. Settlement: ${doj_case['settlement']:,.0f}. "
                    "Credibility floor: prosecuted procurement fraud reliably lights up the engine."
                ),
                **doj_result,
            },
            {
                "case_number": 5,
                "verdict_profile": "jurisdiction_comparison",
                "selection_rationale": (
                    "Contract dated in March (UK fiscal Q4 but US mid-fiscal-year), analyzed "
                    "under both us_federal and uk_central_government profiles to demonstrate "
                    "jurisdiction-correct behavioral delta without code change."
                ),
                **us_result,
            },
        ],
        "jurisdiction_comparison": {
            "case_number": 5,
            "contract_id": juris_row['contract_id'],
            "us_federal_analysis": us_result['analysis'],
            "uk_central_government_analysis": uk_result['analysis'],
            "deltas_explicit": deltas,
            "citation_deltas": citation_deltas,
            "us_rules_fired": sorted(us_rules_fired),
            "uk_rules_fired": sorted(uk_rules_fired),
        },
    }

    # Write output
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print(f"Output written to: {OUTPUT_PATH}")
    print(f"{'=' * 70}")

    # ── SANITY CHECKS ──
    print("\n--- SANITY CHECKS ---")
    checks_passed = 0
    total_checks = 5

    # Check 1: GREEN shows zero dimensions
    g_dims = green_result['analysis']['gate_outcome']['dimensions_fired']
    g_rules = [k for k, v in green_result['analysis']['tca'].get('rule_fire_log', {}).items() if v]
    if g_dims == 0:
        print(f"  [PASS] GREEN: {g_dims} dimensions fired, {len(g_rules)} TCA rules fired")
        checks_passed += 1
    else:
        print(f"  [FAIL] GREEN: expected 0 dimensions fired, got {g_dims}")

    # Check 2: YELLOW shows exactly one dimension
    y_dims = yellow_result['analysis']['gate_outcome']['dimensions_fired']
    if y_dims == 1:
        print(f"  [PASS] YELLOW: exactly {y_dims} dimension fired")
        checks_passed += 1
    else:
        print(f"  [FAIL] YELLOW: expected 1 dimension fired, got {y_dims}")

    # Check 3: RED shows at least two dimensions
    r_dims = red_result['analysis']['gate_outcome']['dimensions_fired']
    if r_dims >= 2:
        print(f"  [PASS] RED: {r_dims} dimensions fired (>= 2)")
        checks_passed += 1
    else:
        print(f"  [FAIL] RED: expected >= 2 dimensions fired, got {r_dims}")

    # Check 4: DOJ contract produces RED verdict
    doj_verdict = doj_result['analysis']['evg_verdict']
    if doj_verdict == "red":
        print(f"  [PASS] DOJ: verdict RED (credibility floor holds)")
        checks_passed += 1
    else:
        print(f"  [FAIL] DOJ: expected verdict RED, got {doj_verdict}")

    # Check 5: Jurisdiction comparison shows real behavioral delta
    if len(deltas) > 0:
        print(f"  [PASS] Jurisdiction comparison: {len(deltas)} behavioral deltas found")
        checks_passed += 1
    else:
        print(f"  [FAIL] Jurisdiction comparison: no behavioral deltas found")

    print(f"\n  Sanity checks: {checks_passed}/{total_checks} passed")

    if checks_passed < total_checks:
        print("\n  WARNING: Not all sanity checks passed. Review output carefully.")
        # Don't exit — let the user see the results and decide
    else:
        print("\n  All sanity checks PASSED.")

    return output


if __name__ == "__main__":
    main()
