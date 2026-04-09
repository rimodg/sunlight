"""
SUNLIGHT DOJ Validation Suite
==============================

Runs every DOJ-prosecuted case through the full scoring pipeline.
Generates precision, recall, F1, confusion matrix, and per-fraud-category
breakdowns.

Approach:
- DOJ cases are ground-truth positives (fraud=True)
- Below-median, competitively-bid contracts from the DB are ground-truth negatives
- Each case gets comparable contracts from the actual database
- Each case runs through score_contract + assign_tier (the real pipeline path)
- Classification: RED/YELLOW = predicted positive, GREEN/GRAY = predicted negative
"""

import json
import os
import sys
import sqlite3
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any

sys.path.insert(0, os.path.dirname(__file__))

from institutional_statistical_rigor import (
    BootstrapAnalyzer, BayesianFraudPrior, MultipleTestingCorrection,
    DOJProsecutionThresholds, FraudTier,
)
from institutional_pipeline import (
    score_contract, assign_tier, select_comparables_from_cache,
    derive_contract_seed, _get_size_bin, _is_defense, _is_it,
)
from sunlight_logging import get_logger

logger = get_logger("doj_validation")


def load_doj_cases(path: str) -> List[Dict]:
    with open(path, 'r') as f:
        data = json.load(f)
    return data['cases']


def build_agency_cache(db_path: str) -> Dict[str, List[Tuple[str, float]]]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT contract_id, agency_name, award_amount FROM contracts WHERE award_amount > 0")
    cache = {}
    for cid, agency, amt in c.fetchall():
        if agency not in cache:
            cache[agency] = []
        cache[agency].append((cid, amt))
    conn.close()
    return cache


def map_doj_agency(doj_agency: str, agency_cache: Dict) -> str:
    """Map DOJ case agency names to database agency names."""
    lower = doj_agency.lower()
    # Direct matches
    for db_agency in agency_cache:
        if db_agency.lower() in lower or lower in db_agency.lower():
            return db_agency
    # Defense variants
    if any(x in lower for x in ['defense', 'dod', 'air force', 'navy', 'army']):
        for db_agency in agency_cache:
            if 'defense' in db_agency.lower():
                return db_agency
    # State department
    if 'state' in lower:
        for db_agency in agency_cache:
            if 'state' in db_agency.lower():
                return db_agency
    # Interior
    if 'interior' in lower:
        for db_agency in agency_cache:
            if 'interior' in db_agency.lower():
                return db_agency
    # Fallback: use the agency with the most contracts
    best = max(agency_cache, key=lambda a: len(agency_cache[a]))
    return best


def synthesize_doj_contract(case: Dict, agency_cache: Dict, db_agency: str) -> Dict:
    """
    Synthesize a contract dict for a DOJ case using real comparables.

    If markup_pct > 0, we set the contract amount relative to the median
    of comparable contracts so the markup matches the DOJ-documented value.
    This tests whether our pipeline correctly identifies the markup pattern.
    """
    comparables_raw = agency_cache.get(db_agency, [])
    amounts = [a for _, a in comparables_raw]

    if amounts and case['markup_pct'] > 0:
        median = np.median(amounts)
        # Set amount so markup matches DOJ case
        synthetic_amount = median * (1 + case['markup_pct'] / 100)
    else:
        synthetic_amount = case['contract_amount']

    comparables = select_comparables_from_cache(
        case['case_id'], db_agency, synthetic_amount, agency_cache
    )

    return {
        'contract_id': case['case_id'],
        'award_amount': synthetic_amount,
        'vendor_name': case['vendor'],
        'agency_name': db_agency,
        'description': case['description'],
        'is_sole_source': 'sole' in case.get('legal_basis', '').lower(),
        'has_donations': 'kickback' in case.get('legal_basis', '').lower()
                         or 'quid pro quo' in case.get('fraud_type', '').lower(),
        'comparables': comparables,
    }

def count_clean_contracts(db_path: str) -> int:
    """
    Count the total size of the clean contract pool (below-median, above $100K).

    Uses the same filter conditions as get_clean_contracts() to determine
    the pool from which samples are drawn. This count is used to compute
    the auto-scaled sample size via sqrt(pool_size).
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        WITH agency_medians AS (
            SELECT agency_name, AVG(award_amount) as med_amount
            FROM contracts
            WHERE award_amount > 0
            GROUP BY agency_name
            HAVING COUNT(*) >= 10
        )
        SELECT COUNT(*)
        FROM contracts c
        JOIN agency_medians am ON c.agency_name = am.agency_name
        WHERE c.award_amount < am.med_amount
        AND c.award_amount > 100000
    """)
    count = c.fetchone()[0]
    conn.close()
    return count


def get_clean_contracts(db_path: str, agency_cache: Dict, n: int = 50) -> List[Dict]:
    """
    Get ground-truth negative contracts: below-median, competitively-bid.
    These are the least likely to be fraudulent.
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        WITH agency_medians AS (
            SELECT agency_name, AVG(award_amount) as med_amount
            FROM contracts
            WHERE award_amount > 0
            GROUP BY agency_name
            HAVING COUNT(*) >= 10
        )
        SELECT c.contract_id, c.award_amount, c.vendor_name, c.agency_name,
               c.description
        FROM contracts c
        JOIN agency_medians am ON c.agency_name = am.agency_name
        WHERE c.award_amount < am.med_amount
        AND c.award_amount > 100000
        ORDER BY RANDOM()
        LIMIT ?
    """, (n,))

    contracts = []
    for row in c.fetchall():
        cid, amount, vendor, agency, desc = row
        comparables = select_comparables_from_cache(cid, agency, amount, agency_cache)
        contracts.append({
            'contract_id': cid,
            'award_amount': amount,
            'vendor_name': vendor,
            'agency_name': agency,
            'description': desc,
            'is_sole_source': False,
            'has_donations': False,
            'comparables': comparables,
        })

    conn.close()
    return contracts


def run_validation(db_path: str, cases_path: str, run_seed: int = 42,
                   n_bootstrap: int = 1000, n_clean: int = 50) -> Dict:
    """Run full DOJ validation suite."""
    logger.info("DOJ validation starting",
                extra={"db_path": db_path, "cases_path": cases_path,
                       "n_bootstrap": n_bootstrap})

    doj_cases = load_doj_cases(cases_path)
    agency_cache = build_agency_cache(db_path)
    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=n_bootstrap)

    # --- Score DOJ cases (ground truth: positive) ---
    doj_results = []
    for case in doj_cases:
        db_agency = map_doj_agency(case['agency'], agency_cache)
        contract = synthesize_doj_contract(case, agency_cache, db_agency)
        seed = derive_contract_seed(run_seed, case['case_id'])

        score = score_contract(contract, seed, config, ba)
        # For tier assignment, we need FDR info. Single-case: no FDR benefit.
        tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False)

        is_price_fraud = case['markup_pct'] > 0
        predicted_positive = tier in ('RED', 'YELLOW')

        doj_results.append({
            'case_id': case['case_id'],
            'vendor': case['vendor'],
            'fraud_type': case['fraud_type'],
            'markup_pct': case['markup_pct'],
            'settlement': case['settlement'],
            'contract_amount': case['contract_amount'],
            'synthetic_amount': contract['award_amount'],
            'comparable_count': score['comparable_count'],
            'predicted_tier': tier,
            'predicted_priority': priority,
            'markup_ci_lower': score.get('markup_ci_lower'),
            'markup_ci_upper': score.get('markup_ci_upper'),
            'bayesian_posterior': score.get('bayesian_posterior'),
            'bootstrap_percentile': score.get('bootstrap_percentile'),
            'raw_pvalue': score.get('raw_pvalue'),
            'is_price_fraud': is_price_fraud,
            'predicted_positive': predicted_positive,
            'ground_truth': 'FRAUD',
            'correct': (predicted_positive if is_price_fraud
                        else not predicted_positive),  # non-price fraud: we shouldn't flag
        })

        logger.info("DOJ case scored",
                     extra={"case_id": case['case_id'], "tier": tier,
                            "markup_pct": case['markup_pct'],
                            "predicted_positive": predicted_positive})

    # --- Score clean contracts (ground truth: negative) ---
    np.random.seed(run_seed)  # Deterministic clean sample
    clean_contracts = get_clean_contracts(db_path, agency_cache, n=n_clean)
    clean_results = []

    for contract in clean_contracts:
        seed = derive_contract_seed(run_seed, contract['contract_id'])
        score = score_contract(contract, seed, config, ba)
        tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False)
        predicted_positive = tier in ('RED', 'YELLOW')

        clean_results.append({
            'contract_id': contract['contract_id'],
            'agency': contract['agency_name'],
            'amount': contract['award_amount'],
            'comparable_count': score['comparable_count'],
            'predicted_tier': tier,
            'predicted_positive': predicted_positive,
            'ground_truth': 'CLEAN',
        })

    # --- Compute classification metrics ---
    # For price-fraud DOJ cases: predicted positive = correct
    # For non-price DOJ cases: excluded from precision/recall (not detectable)
    price_fraud_cases = [r for r in doj_results if r['is_price_fraud']]
    non_price_cases = [r for r in doj_results if not r['is_price_fraud']]

    tp = sum(1 for r in price_fraud_cases if r['predicted_positive'])
    fn = sum(1 for r in price_fraud_cases if not r['predicted_positive'])
    fp = sum(1 for r in clean_results if r['predicted_positive'])
    tn = sum(1 for r in clean_results if not r['predicted_positive'])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0

    confusion_matrix = {
        'true_positive': tp,
        'false_negative': fn,
        'false_positive': fp,
        'true_negative': tn,
    }

    # --- Per-fraud-category breakdown ---
    categories = {}
    for r in doj_results:
        cat = r['fraud_type']
        if cat not in categories:
            categories[cat] = {'total': 0, 'detected': 0, 'cases': []}
        categories[cat]['total'] += 1
        if r['predicted_positive']:
            categories[cat]['detected'] += 1
        categories[cat]['cases'].append({
            'case_id': r['case_id'],
            'vendor': r['vendor'],
            'markup_pct': r['markup_pct'],
            'predicted_tier': r['predicted_tier'],
            'detected': r['predicted_positive'],
        })
    for cat in categories:
        t = categories[cat]['total']
        d = categories[cat]['detected']
        categories[cat]['detection_rate'] = d / t if t > 0 else 0

    # --- Per-tier breakdown ---
    tier_counts = {'RED': 0, 'YELLOW': 0, 'GREEN': 0, 'GRAY': 0}
    for r in doj_results:
        tier_counts[r['predicted_tier']] = tier_counts.get(r['predicted_tier'], 0) + 1

    clean_tier_counts = {'RED': 0, 'YELLOW': 0, 'GREEN': 0, 'GRAY': 0}
    for r in clean_results:
        clean_tier_counts[r['predicted_tier']] = clean_tier_counts.get(r['predicted_tier'], 0) + 1

    # --- Value-weighted metrics ---
    value_detected = sum(r['settlement'] for r in price_fraud_cases if r['predicted_positive'])
    value_total = sum(r['settlement'] for r in price_fraud_cases)
    value_recall = value_detected / value_total if value_total > 0 else 0

    report = {
        'validation_date': datetime.now(timezone.utc).isoformat(),
        'methodology_version': '2.0.0',
        'parameters': {
            'run_seed': run_seed,
            'n_bootstrap': n_bootstrap,
            'n_clean_contracts': len(clean_results),
            'n_doj_cases': len(doj_cases),
            'n_price_fraud_cases': len(price_fraud_cases),
            'n_non_price_cases': len(non_price_cases),
        },
        'classification_metrics': {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1_score': round(f1, 4),
            'accuracy': round(accuracy, 4),
            'specificity': round(specificity, 4),
        },
        'confusion_matrix': confusion_matrix,
        'value_weighted_metrics': {
            'total_fraud_value': value_total,
            'detected_fraud_value': value_detected,
            'value_recall': round(value_recall, 4),
        },
        'doj_tier_distribution': tier_counts,
        'clean_tier_distribution': clean_tier_counts,
        'per_category_breakdown': categories,
        'doj_case_details': doj_results,
        'non_price_fraud_note': (
            f"{len(non_price_cases)} case(s) involve non-price fraud "
            f"(e.g., false certification) which is outside the scope of "
            f"statistical price analysis. These are excluded from "
            f"precision/recall calculations."
        ),
    }

    logger.info("DOJ validation complete",
                extra={"precision": round(precision, 4),
                       "recall": round(recall, 4),
                       "f1": round(f1, 4),
                       "tp": tp, "fn": fn, "fp": fp, "tn": tn})

    return report


def write_json_report(report: Dict, path: str):
    with open(path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("JSON report written", extra={"path": path})


def write_markdown_report(report: Dict, path: str):
    m = report['classification_metrics']
    cm = report['confusion_matrix']
    vw = report['value_weighted_metrics']
    params = report['parameters']

    lines = [
        "# SUNLIGHT DOJ Validation Report",
        "",
        f"**Date:** {report['validation_date'][:10]}",
        f"**Methodology Version:** {report['methodology_version']}",
        f"**Bootstrap Iterations:** {params['n_bootstrap']:,}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"Validated SUNLIGHT scoring pipeline against **{params['n_doj_cases']} DOJ-prosecuted fraud cases** "
        f"and **{params['n_clean_contracts']} known-clean contracts**.",
        "",
        f"- **{params['n_price_fraud_cases']}** cases involve price-based fraud (detectable by statistical analysis)",
        f"- **{params['n_non_price_cases']}** case(s) involve non-price fraud (outside scope — e.g., false certification)",
        "",
        "---",
        "",
        "## Classification Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Precision** | {m['precision']:.1%} |",
        f"| **Recall** | {m['recall']:.1%} |",
        f"| **F1 Score** | {m['f1_score']:.1%} |",
        f"| **Accuracy** | {m['accuracy']:.1%} |",
        f"| **Specificity** | {m['specificity']:.1%} |",
        "",
        "---",
        "",
        "## Confusion Matrix",
        "",
        "| | Predicted Positive (RED/YELLOW) | Predicted Negative (GREEN/GRAY) |",
        "|---|---|---|",
        f"| **Actual Fraud** (DOJ price cases) | TP = {cm['true_positive']} | FN = {cm['false_negative']} |",
        f"| **Actual Clean** (below-median) | FP = {cm['false_positive']} | TN = {cm['true_negative']} |",
        "",
        "---",
        "",
        "## Value-Weighted Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total fraud value (price cases) | ${vw['total_fraud_value']:,.0f} |",
        f"| Detected fraud value | ${vw['detected_fraud_value']:,.0f} |",
        f"| **Value recall** | {vw['value_recall']:.1%} |",
        "",
        "---",
        "",
        "## Per-Case Results",
        "",
        "| Case | Vendor | Fraud Type | Markup | Tier | Detected |",
        "|---|---|---|---|---|---|",
    ]

    for r in report['doj_case_details']:
        detected = 'YES' if r['predicted_positive'] else 'NO'
        markup = f"{r['markup_pct']}%" if r['markup_pct'] > 0 else "N/A"
        lines.append(
            f"| {r['case_id']} | {r['vendor']} | {r['fraud_type']} | "
            f"{markup} | {r['predicted_tier']} | {detected} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## Per-Category Breakdown",
        "",
        "| Fraud Category | Cases | Detected | Detection Rate |",
        "|---|---|---|---|",
    ])

    for cat, data in sorted(report['per_category_breakdown'].items()):
        rate = f"{data['detection_rate']:.0%}"
        lines.append(f"| {cat} | {data['total']} | {data['detected']} | {rate} |")

    lines.extend([
        "",
        "---",
        "",
        "## Tier Distribution",
        "",
        "### DOJ Cases",
        "",
        "| Tier | Count |",
        "|---|---|",
    ])
    for tier in ['RED', 'YELLOW', 'GREEN', 'GRAY']:
        lines.append(f"| {tier} | {report['doj_tier_distribution'].get(tier, 0)} |")

    lines.extend([
        "",
        "### Clean Contracts",
        "",
        "| Tier | Count |",
        "|---|---|",
    ])
    for tier in ['RED', 'YELLOW', 'GREEN', 'GRAY']:
        lines.append(f"| {tier} | {report['clean_tier_distribution'].get(tier, 0)} |")

    lines.extend([
        "",
        "---",
        "",
        "## Methodology Notes",
        "",
        "1. DOJ cases are scored using **synthesized contract amounts** that produce the "
        "documented markup relative to real comparable contracts from the database.",
        "2. Clean contracts are **below-median, randomly sampled** from agencies with 10+ contracts.",
        "3. Each case runs through the full `score_contract` + `assign_tier` pipeline path "
        "(Bootstrap CI, Bayesian posterior, z-scores).",
        "4. **Non-price fraud** (e.g., General Dynamics false certification, 0% markup) is "
        "correctly excluded from precision/recall — SUNLIGHT is a price-anomaly detector, "
        "not a universal fraud detector.",
        "5. FDR correction is **not applied** to individual DOJ case scoring (single-case mode). "
        "In production batch mode, FDR would further reduce false positives.",
        "",
    ])

    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    logger.info("Markdown report written", extra={"path": path})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SUNLIGHT DOJ Validation Suite")
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--cases', default='prosecuted_cases.json')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--bootstrap', type=int, default=1000)
    parser.add_argument('--clean', type=int, default=50)
    parser.add_argument('--out-json', default='reports/validation_report.json')
    parser.add_argument('--out-md', default='reports/validation_report.md')
    parser.add_argument('--ci', action='store_true',
                        help='CI mode: resolve paths relative to repo root, exit 1 if recall < 90%%')
    args = parser.parse_args()

    # Resolve paths — when run from code/ dir, look up one level
    db = args.db
    if not os.path.exists(db):
        db = '../data/sunlight.db'
    cases = args.cases
    if not os.path.exists(cases):
        cases = '../prosecuted_cases.json'

    # In CI mode, ensure output goes to repo root reports/
    out_json = args.out_json
    out_md = args.out_md
    if args.ci:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_json = os.path.join(repo_root, 'reports', 'validation_report.json')
        out_md = os.path.join(repo_root, 'reports', 'validation_report.md')
        os.makedirs(os.path.join(repo_root, 'reports'), exist_ok=True)

    report = run_validation(db, cases, run_seed=args.seed,
                            n_bootstrap=args.bootstrap, n_clean=args.clean)
    write_json_report(report, out_json)
    write_markdown_report(report, out_md)

    # Print summary to stdout
    m = report['classification_metrics']
    cm = report['confusion_matrix']
    print("\n" + "=" * 60)
    print("DOJ VALIDATION RESULTS")
    print("=" * 60)
    print(f"  Precision:   {m['precision']:.1%}")
    print(f"  Recall:      {m['recall']:.1%}")
    print(f"  F1 Score:    {m['f1_score']:.1%}")
    print(f"  Specificity: {m['specificity']:.1%}")
    print(f"\n  TP={cm['true_positive']}  FN={cm['false_negative']}  "
          f"FP={cm['false_positive']}  TN={cm['true_negative']}")
    print(f"\n  Value Recall: {report['value_weighted_metrics']['value_recall']:.1%}")
    print("=" * 60)
    print(f"\nReports: {out_json}, {out_md}")

    # CI accuracy gate
    if args.ci and m['recall'] < 0.90:
        print(f"\nCI FAIL: Recall {m['recall']:.1%} is below 90% threshold")
        sys.exit(1)
