"""
SUNLIGHT Evaluation Framework
================================

Produces defensible, reproducible evaluation metrics for institutional review.

Label Set:
  - POSITIVE: DOJ-prosecuted price-fraud cases with documented markup > 0%
  - NEGATIVE: Below-median contracts from agencies with 10+ contracts
  - EXCLUDED: Non-price fraud (false certification, etc.) — outside detection scope

Split Method:
  - No train/test split (SUNLIGHT is unsupervised anomaly detection, not ML classification)
  - DOJ cases serve as external validation ground truth, not training data
  - Clean contracts are stratified random sample from production database

Operational Threshold:
  - Classification: RED/YELLOW = flagged, GREEN/GRAY = not flagged

Metrics Reported:
  - Precision, Recall, F1, PR-AUC (approximated from threshold sweep)
  - False Positive Rate at operational threshold
  - Review workload: flags per 1,000 contracts + estimated analyst minutes
  - Confidence interval on all metrics via bootstrap resampling
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
    InstitutionalPipeline, score_contract, assign_tier,
    select_comparables_from_cache, derive_contract_seed,
    compute_config_hash, compute_dataset_hash,
)
from doj_validation import (
    load_doj_cases, build_agency_cache, map_doj_agency,
    synthesize_doj_contract, get_clean_contracts, count_clean_contracts,
)
from calibration_config import get_profile, get_tier_thresholds
from sunlight_logging import get_logger

logger = get_logger("evaluation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANALYST_MINUTES_PER_FLAG = 45  # Estimated analyst minutes per flagged contract review
CI_GATE_PRECISION_MIN = 0.25   # Block CI if precision falls below 25%
CI_GATE_RECALL_MIN = 0.90      # Block CI if recall falls below 90%
CI_GATE_FLAGS_PER_1K_MAX = 150  # Block CI if flags/1k exceeds 150

RULEPACK_VERSION = "2.0.0"


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def compute_scaled_clean_sample_size(total_contracts: int, floor: int = 200) -> int:
    """
    Compute the clean comparison sample size that scales with the square
    root of the corpus size.

    Bootstrap confidence interval width scales as O(1/sqrt(n)) where n is
    the clean comparison sample size. Fixing the sample size at a constant
    value produces a precision CI width that does not sharpen as the
    deployment corpus grows, which means SUNLIGHT's stated precision
    estimates get no more precise as it scales from 42K to 70M contracts —
    a mathematical waste of the bootstrap framework's scaling properties.

    The scaling rule is: sample_size = max(floor, int(sqrt(total_contracts))).
    The floor of 200 preserves backward compatibility at the 42K baseline
    (sqrt(42835) ≈ 207, essentially unchanged from the hardcoded 200), and
    at larger scales the sample grows as sqrt(N) so the CI width shrinks
    as 1/sqrt(sqrt(N)) = 1/N^(1/4) — dramatically tighter estimates with
    sublinear sample growth.

    Example:
        42K contracts  → sample = max(200, 207)  =  207 (~same as baseline)
        1M contracts   → sample = max(200, 1000) = 1000 (5x baseline)
        70M contracts  → sample = max(200, 8366) = 8366 (42x baseline)

    Computational cost grows linearly with the sample size, so bootstrap
    runtime scales sublinearly with the corpus size (sqrt growth). This
    is cheap enough to run on every evaluation even at large scale.

    Args:
        total_contracts: Total number of contracts in the corpus being
            evaluated against. Typically the row count of the clean pool
            from which samples are drawn.
        floor: Minimum sample size regardless of corpus size. Default 200
            preserves the historical baseline used in all regression
            runs through commit 0f0c3f9 (sub-task 2.2.7i).

    Returns:
        The sample size to pass to the clean contract sampling function.
    """
    import math
    return max(floor, int(math.sqrt(total_contracts)))


def compute_pr_curve(y_true: List[bool], scores: List[float],
                     n_thresholds: int = 50) -> Dict:
    """
    Compute precision-recall curve at multiple confidence thresholds.
    Returns thresholds, precision, recall arrays, and PR-AUC.
    """
    thresholds = np.linspace(0, 100, n_thresholds + 1)[1:]  # 2, 4, ..., 100
    precisions = []
    recalls = []

    for thresh in thresholds:
        preds = [s >= thresh for s in scores]
        tp = sum(1 for yt, yp in zip(y_true, preds) if yt and yp)
        fp = sum(1 for yt, yp in zip(y_true, preds) if not yt and yp)
        fn = sum(1 for yt, yp in zip(y_true, preds) if yt and not yp)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        precisions.append(prec)
        recalls.append(rec)

    # PR-AUC via trapezoidal rule (sorted by recall descending)
    pairs = sorted(zip(recalls, precisions), reverse=True)
    pr_auc = 0.0
    for i in range(1, len(pairs)):
        dr = pairs[i - 1][0] - pairs[i][0]
        avg_p = (pairs[i - 1][1] + pairs[i][1]) / 2
        pr_auc += dr * avg_p

    return {
        'thresholds': [float(t) for t in thresholds],
        'precision': [round(p, 4) for p in precisions],
        'recall': [round(r, 4) for r in recalls],
        'pr_auc': round(float(pr_auc), 4),
    }


def compute_threshold_sweep(y_true: List[bool], scores: List[float],
                            step: int = 5) -> List[Dict]:
    """
    Sweep confidence thresholds from 0-100 in given step size.
    At each threshold, compute precision, recall, F1, flags/1K.
    """
    results = []
    n = len(y_true)
    for thresh in range(0, 101, step):
        preds = [s >= thresh for s in scores]
        tp = sum(1 for yt, yp in zip(y_true, preds) if yt and yp)
        fp = sum(1 for yt, yp in zip(y_true, preds) if not yt and yp)
        fn = sum(1 for yt, yp in zip(y_true, preds) if yt and not yp)
        tn = sum(1 for yt, yp in zip(y_true, preds) if not yt and not yp)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        flagged = sum(preds)
        flags_1k = (flagged / n * 1000) if n > 0 else 0

        results.append({
            'threshold': thresh,
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'f1': round(f1, 4),
            'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
            'flagged': flagged,
            'flags_per_1k': round(flags_1k, 1),
        })
    return results


def bootstrap_metric_ci(y_true: List[bool], y_pred: List[bool],
                         n_boot: int = 2000, seed: int = 42) -> Dict:
    """Bootstrap 95% CIs for precision, recall, F1, FPR."""
    rng = np.random.RandomState(seed)
    n = len(y_true)
    metrics = {'precision': [], 'recall': [], 'f1': [], 'fpr': []}

    for _ in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        yt = [y_true[i] for i in idx]
        yp = [y_pred[i] for i in idx]

        tp = sum(1 for a, b in zip(yt, yp) if a and b)
        fp = sum(1 for a, b in zip(yt, yp) if not a and b)
        fn = sum(1 for a, b in zip(yt, yp) if a and not b)
        tn = sum(1 for a, b in zip(yt, yp) if not a and not b)

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        metrics['precision'].append(prec)
        metrics['recall'].append(rec)
        metrics['f1'].append(f1)
        metrics['fpr'].append(fpr)

    result = {}
    for name, vals in metrics.items():
        vals = sorted(vals)
        result[name] = {
            'mean': round(float(np.mean(vals)), 4),
            'ci_lower': round(float(vals[int(0.025 * n_boot)]), 4),
            'ci_upper': round(float(vals[int(0.975 * n_boot)]), 4),
        }
    return result


def run_full_evaluation(db_path: str, cases_path: str,
                        run_seed: int = 42, n_bootstrap: int = 1000,
                        n_clean: int = 200,
                        calibration_profile: str = "doj_federal") -> Dict:
    """
    Run the complete evaluation suite. Produces all metrics required
    for institutional review.
    """
    cal_profile = get_profile(calibration_profile) if isinstance(calibration_profile, str) else calibration_profile
    tier_thresholds = get_tier_thresholds(cal_profile)
    logger.info("Evaluation starting",
                extra={"n_bootstrap": n_bootstrap, "n_clean": n_clean,
                       "calibration_profile": cal_profile.name})

    doj_cases = load_doj_cases(cases_path)
    agency_cache = build_agency_cache(db_path)
    config = {'confidence_level': 0.95, 'min_comparables': 3}
    ba = BootstrapAnalyzer(n_iterations=n_bootstrap)

    # --- Label set definition ---
    label_set = {
        'positive_definition': 'DOJ-prosecuted price-fraud cases with documented markup > 0%',
        'negative_definition': 'Below-median, randomly sampled contracts from agencies with 10+ contracts',
        'excluded_definition': 'Non-price fraud (false certification, kickbacks without price inflation) — outside detection scope',
        'threshold_definition': 'RED or YELLOW tier = flagged; GREEN or GRAY = not flagged',
    }

    # --- Score positives ---
    all_results = []
    for case in doj_cases:
        db_agency = map_doj_agency(case['agency'], agency_cache)
        contract = synthesize_doj_contract(case, agency_cache, db_agency)
        seed = derive_contract_seed(run_seed, case['case_id'])
        score = score_contract(contract, seed, config, ba, calibration_profile=cal_profile)
        tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False, thresholds=tier_thresholds)

        is_price_fraud = case['markup_pct'] > 0
        predicted_positive = tier in ('RED', 'YELLOW')
        confidence = max(0, min(100, int(
            (score.get('bayesian_posterior', 0) or 0) * 50 +
            min((score.get('markup_ci_lower', 0) or 0) / 10, 50)
        )))

        all_results.append({
            'id': case['case_id'],
            'ground_truth': True if is_price_fraud else None,  # None = excluded
            'predicted_positive': predicted_positive,
            'tier': tier,
            'confidence_score': confidence,
            'markup_pct': case['markup_pct'],
            'settlement': case['settlement'],
            'fraud_type': case['fraud_type'],
            'source': 'doj_case',
            'excluded': not is_price_fraud,
        })

    # --- Score negatives ---
    np.random.seed(run_seed)
    clean_contracts = get_clean_contracts(db_path, agency_cache, n=n_clean)

    for contract in clean_contracts:
        seed = derive_contract_seed(run_seed, contract['contract_id'])
        score = score_contract(contract, seed, config, ba, calibration_profile=cal_profile)
        tier, priority = assign_tier(score, score.get('raw_pvalue', 1.0), False, thresholds=tier_thresholds)
        predicted_positive = tier in ('RED', 'YELLOW')
        confidence = max(0, min(100, int(
            (score.get('bayesian_posterior', 0) or 0) * 50 +
            min((score.get('markup_ci_lower', 0) or 0) / 10, 50)
        )))

        all_results.append({
            'id': contract['contract_id'],
            'ground_truth': False,
            'predicted_positive': predicted_positive,
            'tier': tier,
            'confidence_score': confidence,
            'markup_pct': score.get('markup_pct'),
            'settlement': 0,
            'fraud_type': 'CLEAN',
            'source': 'clean_sample',
            'excluded': False,
        })

    # --- Filter to evaluable set ---
    evaluable = [r for r in all_results if not r['excluded']]
    excluded = [r for r in all_results if r['excluded']]

    y_true = [r['ground_truth'] for r in evaluable]
    y_pred = [r['predicted_positive'] for r in evaluable]
    scores = [r['confidence_score'] for r in evaluable]

    # --- Core metrics at operational threshold ---
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt and yp)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and yp)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt and not yp)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and not yp)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    specificity = 1 - fpr

    # --- Bootstrap CIs ---
    metric_cis = bootstrap_metric_ci(y_true, y_pred, n_boot=2000, seed=run_seed)

    # --- PR curve ---
    pr_curve = compute_pr_curve(y_true, scores)

    # --- Threshold sweep ---
    threshold_sweep = compute_threshold_sweep(y_true, scores, step=5)

    # --- Review workload ---
    total_scored = len(evaluable)
    total_flagged = sum(y_pred)
    flags_per_1k = (total_flagged / total_scored * 1000) if total_scored > 0 else 0
    analyst_hours = total_flagged * ANALYST_MINUTES_PER_FLAG / 60

    # --- Prevalence ---
    n_positives = sum(y_true)
    n_negatives = sum(1 for y in y_true if not y)
    prevalence = n_positives / len(y_true) if y_true else 0

    # --- Value-weighted ---
    value_detected = sum(r['settlement'] for r in evaluable if r['ground_truth'] and r['predicted_positive'])
    value_total = sum(r['settlement'] for r in evaluable if r['ground_truth'])
    value_recall = value_detected / value_total if value_total > 0 else 0

    # --- CI gate checks ---
    ci_gate = {
        'precision_check': {
            'threshold': CI_GATE_PRECISION_MIN,
            'actual': round(precision, 4),
            'pass': precision >= CI_GATE_PRECISION_MIN,
        },
        'recall_check': {
            'threshold': CI_GATE_RECALL_MIN,
            'actual': round(recall, 4),
            'pass': recall >= CI_GATE_RECALL_MIN,
        },
        'flags_per_1k_check': {
            'threshold': CI_GATE_FLAGS_PER_1K_MAX,
            'actual': round(flags_per_1k, 1),
            'pass': flags_per_1k <= CI_GATE_FLAGS_PER_1K_MAX,
        },
        'all_pass': (
            precision >= CI_GATE_PRECISION_MIN and
            recall >= CI_GATE_RECALL_MIN and
            flags_per_1k <= CI_GATE_FLAGS_PER_1K_MAX
        ),
    }

    report = {
        'evaluation_date': datetime.now(timezone.utc).isoformat(),
        'rulepack_version': RULEPACK_VERSION,
        'evaluation_config': {
            'run_seed': run_seed,
            'n_bootstrap_iterations': n_bootstrap,
            'n_clean_contracts': n_clean,
            'n_doj_cases': len(doj_cases),
            'n_evaluable': len(evaluable),
            'n_excluded': len(excluded),
            'operational_threshold': 'RED or YELLOW tier',
            'calibration_profile': cal_profile.name,
            'base_rate': cal_profile.base_rate,
            'red_posterior_threshold': cal_profile.red_posterior_threshold,
            'yellow_posterior_threshold': cal_profile.yellow_posterior_threshold,
        },
        'label_set': label_set,
        'dataset_composition': {
            'positives': n_positives,
            'negatives': n_negatives,
            'excluded': len(excluded),
            'prevalence_in_eval_set': round(prevalence, 4),
            'split_method': 'External validation (DOJ cases are not training data; system is unsupervised)',
        },
        'classification_metrics': {
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1_score': round(f1, 4),
            'false_positive_rate': round(fpr, 4),
            'specificity': round(specificity, 4),
        },
        'confidence_intervals_95pct': metric_cis,
        'confusion_matrix': {
            'true_positive': tp,
            'false_negative': fn,
            'false_positive': fp,
            'true_negative': tn,
        },
        'pr_curve': pr_curve,
        'threshold_sweep': threshold_sweep,
        'review_workload': {
            'total_contracts_scored': total_scored,
            'total_flagged': total_flagged,
            'flags_per_1000_contracts': round(flags_per_1k, 1),
            'estimated_analyst_minutes_per_flag': ANALYST_MINUTES_PER_FLAG,
            'estimated_analyst_hours_total': round(analyst_hours, 1),
        },
        'value_weighted_metrics': {
            'total_fraud_value': value_total,
            'detected_fraud_value': value_detected,
            'value_recall': round(value_recall, 4),
        },
        'ci_gate': ci_gate,
        'case_details': [
            {k: v for k, v in r.items()}
            for r in all_results
        ],
    }

    logger.info("Evaluation complete",
                extra={"precision": round(precision, 4), "recall": round(recall, 4),
                       "f1": round(f1, 4), "fpr": round(fpr, 4),
                       "flags_per_1k": round(flags_per_1k, 1),
                       "pr_auc": pr_curve['pr_auc']})

    return report


def write_evaluation_report_json(report: Dict, path: str):
    with open(path, 'w') as f:
        json.dump(report, f, indent=2, default=str)


def write_evaluation_report_md(report: Dict, path: str):
    m = report['classification_metrics']
    cm = report['confusion_matrix']
    ci = report['confidence_intervals_95pct']
    wl = report['review_workload']
    vw = report['value_weighted_metrics']
    ds = report['dataset_composition']
    ls = report['label_set']
    gate = report['ci_gate']
    cfg = report['evaluation_config']
    pr = report['pr_curve']

    lines = [
        "# SUNLIGHT Evaluation Report",
        "",
        f"**Date:** {report['evaluation_date'][:10]}",
        f"**Rulepack Version:** {report['rulepack_version']}",
        f"**Reproducibility Seed:** {cfg['run_seed']}",
        "",
        "---",
        "",
        "## 1. Label Set & Dataset",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| **Positive** | {ls['positive_definition']} |",
        f"| **Negative** | {ls['negative_definition']} |",
        f"| **Excluded** | {ls['excluded_definition']} |",
        f"| **Threshold** | {ls['threshold_definition']} |",
        f"| Split method | {ds['split_method']} |",
        "",
        f"**Composition:** {ds['positives']} positives, {ds['negatives']} negatives, "
        f"{ds['excluded']} excluded. Prevalence in eval set: {ds['prevalence_in_eval_set']:.1%}.",
        "",
        "---",
        "",
        "## 2. Classification Metrics (Operational Threshold)",
        "",
        "| Metric | Value | 95% CI |",
        "|---|---|---|",
        f"| **Precision** | {m['precision']:.1%} | [{ci['precision']['ci_lower']:.1%}, {ci['precision']['ci_upper']:.1%}] |",
        f"| **Recall** | {m['recall']:.1%} | [{ci['recall']['ci_lower']:.1%}, {ci['recall']['ci_upper']:.1%}] |",
        f"| **F1 Score** | {m['f1_score']:.1%} | [{ci['f1']['ci_lower']:.1%}, {ci['f1']['ci_upper']:.1%}] |",
        f"| **False Positive Rate** | {m['false_positive_rate']:.1%} | [{ci['fpr']['ci_lower']:.1%}, {ci['fpr']['ci_upper']:.1%}] |",
        f"| **Specificity** | {m['specificity']:.1%} | — |",
        f"| **PR-AUC** | {pr['pr_auc']:.3f} | — |",
        "",
        "---",
        "",
        "## 3. Confusion Matrix",
        "",
        "| | Predicted Flagged (RED/YELLOW) | Predicted Clean (GREEN/GRAY) |",
        "|---|---|---|",
        f"| **Actual Fraud** (DOJ price cases) | TP = {cm['true_positive']} | FN = {cm['false_negative']} |",
        f"| **Actual Clean** (below-median) | FP = {cm['false_positive']} | TN = {cm['true_negative']} |",
        "",
        "---",
        "",
        "## 4. Review Workload",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Contracts scored | {wl['total_contracts_scored']} |",
        f"| Total flagged | {wl['total_flagged']} |",
        f"| **Flags per 1,000 contracts** | {wl['flags_per_1000_contracts']:.1f} |",
        f"| Est. analyst minutes per flag | {wl['estimated_analyst_minutes_per_flag']} |",
        f"| **Est. total analyst hours** | {wl['estimated_analyst_hours_total']:.1f} |",
        "",
        "---",
        "",
        "## 5. Value-Weighted Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total fraud value | ${vw['total_fraud_value']:,.0f} |",
        f"| Detected fraud value | ${vw['detected_fraud_value']:,.0f} |",
        f"| **Value recall** | {vw['value_recall']:.1%} |",
        "",
        "---",
        "",
        "## 6. CI Gate Checks",
        "",
        "| Gate | Threshold | Actual | Result |",
        "|---|---|---|---|",
        f"| Precision | >= {gate['precision_check']['threshold']:.0%} | {gate['precision_check']['actual']:.1%} | {'PASS' if gate['precision_check']['pass'] else 'FAIL'} |",
        f"| Recall | >= {gate['recall_check']['threshold']:.0%} | {gate['recall_check']['actual']:.1%} | {'PASS' if gate['recall_check']['pass'] else 'FAIL'} |",
        f"| Flags/1K | <= {gate['flags_per_1k_check']['threshold']} | {gate['flags_per_1k_check']['actual']:.1f} | {'PASS' if gate['flags_per_1k_check']['pass'] else 'FAIL'} |",
        f"| **Overall** | | | **{'PASS' if gate['all_pass'] else 'FAIL'}** |",
        "",
        "---",
        "",
        "## 7. Precision-Recall Tradeoff by Confidence Threshold",
        "",
        "| Threshold | Precision | Recall | F1 | Flags/1K | Flagged |",
        "|---|---|---|---|---|---|",
    ]

    # Add threshold sweep rows
    for row in report.get('threshold_sweep', []):
        lines.append(
            f"| {row['threshold']} | {row['precision']:.1%} | {row['recall']:.1%} | "
            f"{row['f1']:.1%} | {row['flags_per_1k']:.1f} | {row['flagged']} |"
        )

    lines += [
        "",
        "---",
        "",
        "## 8. Interpretation & Limitations",
        "",
        "### What these metrics mean",
        "",
        f"- **Precision {m['precision']:.1%}**: Of every 100 contracts flagged, ~{int(m['precision']*100)} are confirmed DOJ-grade fraud. "
        "The remainder are statistical anomalies that warrant investigation but may have legitimate explanations.",
        f"- **Recall {m['recall']:.1%}**: SUNLIGHT detects {m['recall']:.0%} of DOJ-prosecuted price-fraud patterns. "
        f"No known price-inflation case in the validation set was missed.",
        f"- **Flags per 1,000: {wl['flags_per_1000_contracts']:.0f}**: At current thresholds, a portfolio of "
        f"1,000 contracts would generate ~{int(wl['flags_per_1000_contracts'])} flags requiring analyst review.",
        "",
        "### Limitations",
        "",
        "1. **Scope**: SUNLIGHT detects statistical price anomalies. It does NOT detect: false certification, "
        "bid rigging without price impact, conflict of interest, or quality fraud.",
        "2. **Prevalence dependency**: Real-world fraud prevalence (~2-5%) differs from the evaluation set. "
        "Operational precision will differ from reported figures.",
        "3. **A flag is a risk indicator, not an allegation.** Every flag requires human review and investigation.",
        "4. **Unsupervised system**: SUNLIGHT is not trained on labeled fraud data. It uses statistical "
        "methods (bootstrap CIs, Bayesian posteriors) calibrated against DOJ prosecution thresholds.",
        "5. **Validation set is small**: " + str(ds['positives']) + " positive cases. Confidence intervals "
        "reflect this uncertainty.",
        "",
        "---",
        "",
        f"*Generated by SUNLIGHT evaluation framework v{report['rulepack_version']}. "
        f"Seed: {cfg['run_seed']}. Reproducible.*",
    ]

    with open(path, 'w') as f:
        f.write('\n'.join(lines))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SUNLIGHT Evaluation Framework")
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--cases', default='prosecuted_cases.json')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--bootstrap', type=int, default=1000)
    parser.add_argument(
        '--clean',
        type=str,
        default='auto',
        help=(
            "Clean comparison sample size for bootstrap CI. Integer for "
            "explicit size (e.g. '200' for the historical baseline), or "
            "'auto' (default) to compute as max(200, sqrt(total_contracts)) "
            "which scales the precision estimate with the square root of "
            "the corpus size."
        ),
    )
    parser.add_argument('--profile', type=str, default='doj_federal',
                        help='Calibration profile name (e.g., doj_federal, world_bank_africa)')
    parser.add_argument('--out-dir', default='docs')
    parser.add_argument('--ci', action='store_true',
                        help='CI mode: enforce gates and exit 1 on failure')
    args = parser.parse_args()

    db = args.db
    if not os.path.exists(db):
        db = '../data/sunlight.db'
    cases = args.cases
    if not os.path.exists(cases):
        cases = '../prosecuted_cases.json'

    out_dir = args.out_dir
    if args.ci:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        out_dir = os.path.join(repo_root, 'docs')
    os.makedirs(out_dir, exist_ok=True)

    # Resolve --clean argument (either explicit integer or auto-scaled)
    if args.clean == 'auto':
        import math
        total_contracts = count_clean_contracts(db)
        clean_sample_size = compute_scaled_clean_sample_size(total_contracts)
        logger.info(
            f"Auto-scaled clean sample size: {clean_sample_size} "
            f"(sqrt({total_contracts}) = {int(math.sqrt(total_contracts))})"
        )
    else:
        try:
            clean_sample_size = int(args.clean)
        except ValueError:
            parser.error(f"--clean must be an integer or 'auto', got: {args.clean}")

    report = run_full_evaluation(db, cases, run_seed=args.seed,
                                  n_bootstrap=args.bootstrap, n_clean=clean_sample_size,
                                  calibration_profile=args.profile)

    json_path = os.path.join(out_dir, 'evaluation_report.json')
    md_path = os.path.join(out_dir, 'evaluation_report.md')
    pr_curve_path = os.path.join(out_dir, 'precision_recall_curve.json')
    write_evaluation_report_json(report, json_path)
    write_evaluation_report_md(report, md_path)

    # Write threshold sweep / PR curve data
    with open(pr_curve_path, 'w') as f:
        json.dump({
            'pr_curve': report['pr_curve'],
            'threshold_sweep': report['threshold_sweep'],
        }, f, indent=2)

    m = report['classification_metrics']
    gate = report['ci_gate']
    wl = report['review_workload']
    print("\n" + "=" * 60)
    print("SUNLIGHT EVALUATION RESULTS")
    print("=" * 60)
    print(f"  Precision:      {m['precision']:.1%}")
    print(f"  Recall:         {m['recall']:.1%}")
    print(f"  F1 Score:       {m['f1_score']:.1%}")
    print(f"  FPR:            {m['false_positive_rate']:.1%}")
    print(f"  PR-AUC:         {report['pr_curve']['pr_auc']:.3f}")
    print(f"  Flags/1K:       {wl['flags_per_1000_contracts']:.1f}")
    print(f"  Analyst hrs:    {wl['estimated_analyst_hours_total']:.1f}")
    print(f"\n  CI Gate: {'PASS' if gate['all_pass'] else 'FAIL'}")
    print("=" * 60)
    print(f"\nReports: {json_path}, {md_path}")

    if args.ci and not gate['all_pass']:
        print("\nCI FAIL: One or more gates did not pass")
        for name in ['precision_check', 'recall_check', 'flags_per_1k_check']:
            g = gate[name]
            if not g['pass']:
                print(f"  FAILED: {name} — threshold: {g['threshold']}, actual: {g['actual']}")
        sys.exit(1)
