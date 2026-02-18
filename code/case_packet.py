"""
SUNLIGHT Case Packet Generator
==================================

Produces investigator-ready case packets for flagged contracts.
Each packet is a self-contained evidence bundle suitable for
institutional compliance review, OIG referral, or legal proceedings.

Every explanation explicitly states: "risk indicator, not allegation."

Packet contents:
  a) Triggered typology/rule name
  b) Exact evidence fields/values
  c) Peer comparison (why this is anomalous)
  d) Linkages (vendor/name matches) with confidence
  e) Recommended next step + risk severity
  f) Analyst notes + disposition fields
"""

import json
import os
import sys
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(__file__))

from institutional_statistical_rigor import DOJProsecutionThresholds
from institutional_pipeline import verify_audit_chain
from sunlight_logging import get_logger

logger = get_logger("case_packet")

DISCLAIMER = (
    "IMPORTANT: All findings in this case packet are statistical risk indicators, "
    "not allegations of fraud. Flagged contracts require human review and investigation "
    "before any conclusions can be drawn. Statistical anomalies may have legitimate "
    "explanations including market conditions, specialized requirements, or data quality issues."
)

RULEPACK_VERSION = "2.0.0"


def _classify_typology(score: Dict, contract: Dict) -> List[Dict]:
    """Identify which detection rules triggered and why."""
    typologies = []

    markup_ci = score.get('markup_ci_lower') or 0
    markup_pct = score.get('markup_pct') or 0
    posterior = score.get('bayesian_posterior') or 0
    percentile = score.get('percentile_ci_lower') or 0

    if markup_ci > DOJProsecutionThresholds.EXTREME_MARKUP:
        typologies.append({
            'rule_id': 'PRICE-001',
            'rule_name': 'Extreme Price Inflation',
            'description': (
                f'Bootstrap 95% CI lower bound ({markup_ci:.0f}%) exceeds '
                f'DOJ extreme threshold ({DOJProsecutionThresholds.EXTREME_MARKUP}%). '
                f'This level of markup has been prosecuted under the False Claims Act.'
            ),
            'severity': 'CRITICAL',
            'threshold': f'CI lower > {DOJProsecutionThresholds.EXTREME_MARKUP}%',
            'actual_value': f'{markup_ci:.1f}%',
        })
    elif markup_ci > DOJProsecutionThresholds.HIGH_MARKUP:
        typologies.append({
            'rule_id': 'PRICE-002',
            'rule_name': 'High Price Inflation',
            'description': (
                f'Bootstrap 95% CI lower bound ({markup_ci:.0f}%) exceeds '
                f'DOJ high threshold ({DOJProsecutionThresholds.HIGH_MARKUP}%).'
            ),
            'severity': 'HIGH',
            'threshold': f'CI lower > {DOJProsecutionThresholds.HIGH_MARKUP}%',
            'actual_value': f'{markup_ci:.1f}%',
        })
    elif markup_ci > DOJProsecutionThresholds.INVESTIGATION_WORTHY:
        typologies.append({
            'rule_id': 'PRICE-003',
            'rule_name': 'Elevated Price Anomaly',
            'description': (
                f'Bootstrap 95% CI lower bound ({markup_ci:.0f}%) exceeds '
                f'minimum DOJ investigation threshold ({DOJProsecutionThresholds.INVESTIGATION_WORTHY}%).'
            ),
            'severity': 'MEDIUM',
            'threshold': f'CI lower > {DOJProsecutionThresholds.INVESTIGATION_WORTHY}%',
            'actual_value': f'{markup_ci:.1f}%',
        })

    if posterior > 0.80:
        typologies.append({
            'rule_id': 'BAYES-001',
            'rule_name': 'High Bayesian Fraud Probability',
            'description': (
                f'Bayesian posterior fraud probability ({posterior:.1%}) exceeds '
                f'80% threshold after adjusting for base rates and contract characteristics.'
            ),
            'severity': 'HIGH',
            'threshold': 'Posterior > 80%',
            'actual_value': f'{posterior:.1%}',
        })
    elif posterior > 0.50:
        typologies.append({
            'rule_id': 'BAYES-002',
            'rule_name': 'Elevated Bayesian Fraud Probability',
            'description': (
                f'Bayesian posterior fraud probability ({posterior:.1%}) exceeds '
                f'50% threshold.'
            ),
            'severity': 'MEDIUM',
            'threshold': 'Posterior > 50%',
            'actual_value': f'{posterior:.1%}',
        })

    if percentile > 95:
        typologies.append({
            'rule_id': 'OUTLIER-001',
            'rule_name': 'Extreme Percentile Outlier',
            'description': (
                f'Contract amount exceeds {percentile:.0f}th percentile of '
                f'comparable contracts. This is an extreme statistical outlier.'
            ),
            'severity': 'HIGH',
            'threshold': 'Percentile > 95th',
            'actual_value': f'{percentile:.1f}th percentile',
        })
    elif percentile > 75:
        typologies.append({
            'rule_id': 'OUTLIER-002',
            'rule_name': 'Upper Quartile Outlier',
            'description': (
                f'Contract amount exceeds {percentile:.0f}th percentile of comparable contracts.'
            ),
            'severity': 'MEDIUM',
            'threshold': 'Percentile > 75th',
            'actual_value': f'{percentile:.1f}th percentile',
        })

    return typologies


def _build_peer_comparison(db_path: str, contract: Dict, score: Dict) -> Dict:
    """Build peer comparison showing why this contract is anomalous."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    agency = contract.get('agency_name', '')
    contract_id = contract.get('contract_id', '')
    amount = contract.get('award_amount', 0)

    c.execute(
        "SELECT award_amount FROM contracts "
        "WHERE agency_name = ? AND contract_id != ? AND award_amount > 0 "
        "ORDER BY award_amount",
        (agency, contract_id),
    )
    peer_amounts = [r[0] for r in c.fetchall()]
    conn.close()

    if not peer_amounts:
        return {'available': False, 'reason': 'No comparable contracts in database'}

    import numpy as np
    arr = np.array(peer_amounts)
    median = float(np.median(arr))
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0
    p25 = float(np.percentile(arr, 25))
    p75 = float(np.percentile(arr, 75))
    p95 = float(np.percentile(arr, 95))

    rank = int(np.searchsorted(np.sort(arr), amount))
    percentile = rank / len(arr) * 100 if len(arr) > 0 else 0

    return {
        'available': True,
        'agency': agency,
        'peer_count': len(peer_amounts),
        'contract_amount': amount,
        'peer_statistics': {
            'median': round(median, 2),
            'mean': round(mean, 2),
            'std_dev': round(std, 2),
            'p25': round(p25, 2),
            'p75': round(p75, 2),
            'p95': round(p95, 2),
        },
        'anomaly_assessment': {
            'percentile_rank': round(percentile, 1),
            'deviation_from_median_pct': round((amount - median) / median * 100, 1) if median > 0 else 0,
            'z_score': round((amount - mean) / std, 2) if std > 0 else 0,
        },
        'interpretation': (
            f'This contract (${amount:,.0f}) is at the {percentile:.0f}th percentile '
            f'of {len(peer_amounts)} comparable contracts in {agency}. '
            f'The peer median is ${median:,.0f}. '
            f'This is a statistical risk indicator, not an allegation.'
        ),
    }


def _find_vendor_linkages(db_path: str, vendor_name: str,
                           contract_id: str) -> Dict:
    """Find other contracts and donations linked to this vendor."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Other contracts by same vendor
    c.execute(
        "SELECT contract_id, award_amount, agency_name, description "
        "FROM contracts WHERE vendor_name = ? AND contract_id != ? "
        "ORDER BY award_amount DESC LIMIT 10",
        (vendor_name, contract_id),
    )
    other_contracts = [dict(r) for r in c.fetchall()]

    # Check for scored contracts
    flagged_contracts = []
    for oc in other_contracts:
        c.execute(
            "SELECT fraud_tier, confidence_score, markup_pct "
            "FROM contract_scores WHERE contract_id = ? "
            "ORDER BY scored_at DESC LIMIT 1",
            (oc['contract_id'],),
        )
        score_row = c.fetchone()
        if score_row and dict(score_row).get('fraud_tier') in ('RED', 'YELLOW'):
            flagged_contracts.append({
                **oc,
                'fraud_tier': dict(score_row)['fraud_tier'],
                'confidence_score': dict(score_row)['confidence_score'],
            })

    # Political donations
    c.execute(
        "SELECT recipient_name, amount, date, cycle "
        "FROM political_donations WHERE vendor_name = ? "
        "ORDER BY amount DESC",
        (vendor_name,),
    )
    donations = [dict(r) for r in c.fetchall()]
    total_donations = sum(d['amount'] for d in donations)

    conn.close()

    linkage_confidence = 'HIGH'  # Exact name match
    if len(other_contracts) == 0 and len(donations) == 0:
        linkage_confidence = 'LOW'

    return {
        'vendor_name': vendor_name,
        'match_type': 'exact_name',
        'linkage_confidence': linkage_confidence,
        'total_contracts': len(other_contracts) + 1,
        'other_contracts': other_contracts[:5],
        'flagged_contracts': flagged_contracts,
        'political_donations': {
            'count': len(donations),
            'total_amount': total_donations,
            'records': donations[:5],
        },
        'note': (
            'Vendor linkages are based on exact name matching. '
            'Variations in vendor naming may cause missed linkages. '
            'These are indicators for further investigation, not conclusions.'
        ),
    }


def _recommend_actions(tier: str, typologies: List[Dict],
                        linkages: Dict) -> Dict:
    """Generate recommended next steps based on findings."""
    severity = tier
    has_donations = linkages.get('political_donations', {}).get('count', 0) > 0
    has_other_flags = len(linkages.get('flagged_contracts', [])) > 0

    if tier == 'RED':
        action = 'Immediate detailed review recommended'
        next_steps = [
            'Request complete cost/pricing data from vendor (FAR 15.403)',
            'Compare line-item pricing against GSA schedule or commercial equivalents',
            'Review contract modification history for unexplained cost growth',
            'Check vendor debarment/suspension status (SAM.gov)',
        ]
        if has_donations:
            next_steps.append('Review political donation records for potential conflict of interest')
        if has_other_flags:
            next_steps.append('Investigate pattern across other flagged contracts from this vendor')
        next_steps.append('If evidence supports, consider referral to OIG or contracting officer')
    elif tier == 'YELLOW':
        action = 'Detailed review recommended'
        next_steps = [
            'Request supporting documentation (cost breakdowns, subcontractor quotes)',
            'Verify market conditions at time of award',
            'Review sole-source justification if applicable',
            'Compare against recent re-competitions or follow-on contracts',
        ]
        if has_donations:
            next_steps.append('Note political donation records for completeness')
        if has_other_flags:
            next_steps.append('Review vendor portfolio for pricing patterns')
    else:
        action = 'Standard monitoring'
        next_steps = ['No additional action required at this time']
        severity = 'LOW'

    return {
        'risk_severity': severity,
        'recommended_action': action,
        'next_steps': next_steps,
        'escalation_path': (
            'OIG Hotline or Contracting Officer for RED-tier findings; '
            'Contracting Officer for YELLOW-tier findings'
        ),
    }


def generate_case_packet(db_path: str, contract_id: str,
                          run_id: Optional[str] = None) -> Dict:
    """
    Generate a complete, investigator-ready case packet for a contract.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Load contract
    c.execute(
        "SELECT contract_id, award_amount, vendor_name, agency_name, "
        "description, start_date "
        "FROM contracts WHERE contract_id = ?",
        (contract_id,),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        return {'error': f'Contract {contract_id} not found'}
    contract = dict(row)

    # Load score
    if run_id:
        c.execute(
            "SELECT * FROM contract_scores WHERE contract_id = ? AND run_id = ?",
            (contract_id, run_id),
        )
    else:
        c.execute(
            "SELECT * FROM contract_scores WHERE contract_id = ? "
            "ORDER BY scored_at DESC LIMIT 1",
            (contract_id,),
        )
    score_row = c.fetchone()
    conn.close()

    if not score_row:
        return {'error': f'No scores found for contract {contract_id}'}

    score = dict(score_row)
    tier = score.get('fraud_tier') or score.get('tier') or 'GREEN'

    # Build packet sections
    typologies = _classify_typology(score, contract)
    peer_comparison = _build_peer_comparison(db_path, contract, score)
    linkages = _find_vendor_linkages(db_path, contract['vendor_name'], contract_id)
    recommendations = _recommend_actions(tier, typologies, linkages)

    # Data snapshot hash
    snapshot_hash = hashlib.sha256(
        json.dumps({
            'contract': contract,
            'score': {k: v for k, v in score.items() if k != 'selection_params_json'},
        }, sort_keys=True, default=str).encode()
    ).hexdigest()

    packet = {
        'case_packet_version': '1.0.0',
        'rulepack_version': RULEPACK_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'data_snapshot_id': snapshot_hash[:16],
        'disclaimer': DISCLAIMER,

        'contract': contract,

        'assessment': {
            'fraud_tier': tier,
            'confidence_score': score.get('confidence_score', 0),
            'run_id': score.get('run_id'),
            'scored_at': score.get('scored_at'),
        },

        'triggered_typologies': typologies,

        'evidence': {
            'markup_pct': score.get('markup_pct'),
            'markup_ci_lower': score.get('markup_ci_lower'),
            'markup_ci_upper': score.get('markup_ci_upper'),
            'raw_zscore': score.get('raw_zscore'),
            'log_zscore': score.get('log_zscore'),
            'bootstrap_percentile': score.get('bootstrap_percentile'),
            'percentile_ci_lower': score.get('percentile_ci_lower'),
            'percentile_ci_upper': score.get('percentile_ci_upper'),
            'bayesian_prior': score.get('bayesian_prior'),
            'bayesian_posterior': score.get('bayesian_posterior'),
            'bayesian_likelihood_ratio': score.get('bayesian_likelihood_ratio'),
            'raw_pvalue': score.get('raw_pvalue'),
            'fdr_adjusted_pvalue': score.get('fdr_adjusted_pvalue'),
            'survives_fdr': bool(score.get('survives_fdr')),
            'comparable_count': score.get('comparable_count'),
        },

        'peer_comparison': peer_comparison,
        'vendor_linkages': linkages,
        'recommendations': recommendations,

        'disposition': {
            'status': 'PENDING_REVIEW',
            'analyst_notes': '',
            'disposition_options': [
                'TRUE_POSITIVE — Confirmed pricing anomaly, escalate',
                'FALSE_POSITIVE — Legitimate pricing, document rationale',
                'BENIGN — Anomaly explained by market conditions',
                'NEEDS_INFO — Insufficient information, request documentation',
            ],
            'reviewed_by': None,
            'reviewed_at': None,
        },
    }

    logger.info("Case packet generated",
                extra={"contract_id": contract_id, "tier": tier,
                       "n_typologies": len(typologies),
                       "snapshot_id": snapshot_hash[:16]})

    return packet


def render_case_packet_md(packet: Dict) -> str:
    """Render a case packet as markdown for human review."""
    c = packet['contract']
    a = packet['assessment']
    ev = packet['evidence']
    pc = packet['peer_comparison']
    vl = packet['vendor_linkages']
    rec = packet['recommendations']

    lines = [
        f"# Case Packet: {c['contract_id']}",
        "",
        f"> {packet['disclaimer']}",
        "",
        f"**Generated:** {packet['generated_at'][:19]}Z | "
        f"**Rulepack:** {packet['rulepack_version']} | "
        f"**Snapshot:** {packet['data_snapshot_id']}",
        "",
        "---",
        "",
        "## Contract Summary",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| Contract ID | `{c['contract_id']}` |",
        f"| Award Amount | ${c['award_amount']:,.0f} |",
        f"| Vendor | {c['vendor_name']} |",
        f"| Agency | {c['agency_name']} |",
        f"| Description | {c.get('description', '')} |",
        f"| Start Date | {c.get('start_date', '—')} |",
        "",
        "---",
        "",
        "## Risk Assessment",
        "",
        f"**Tier:** {a['fraud_tier']} | **Confidence:** {a['confidence_score']}/100 | "
        f"**Severity:** {rec['risk_severity']}",
        "",
    ]

    # Typologies
    if packet['triggered_typologies']:
        lines.extend(["## Triggered Rules", ""])
        for t in packet['triggered_typologies']:
            lines.extend([
                f"### {t['rule_id']}: {t['rule_name']} [{t['severity']}]",
                "",
                t['description'],
                "",
                f"- Threshold: {t['threshold']}",
                f"- Actual: {t['actual_value']}",
                "",
            ])

    # Evidence
    lines.extend([
        "## Statistical Evidence",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Markup vs. median | {ev['markup_pct']:.1f}% |" if ev.get('markup_pct') is not None else "| Markup | — |",
        f"| Bootstrap 95% CI | [{ev['markup_ci_lower']:.1f}%, {ev['markup_ci_upper']:.1f}%] |" if ev.get('markup_ci_lower') is not None else "| Bootstrap CI | — |",
        f"| Bayesian posterior | {ev['bayesian_posterior']:.1%} |" if ev.get('bayesian_posterior') is not None else "| Bayesian posterior | — |",
        f"| Percentile (CI lower) | {ev['percentile_ci_lower']:.1f}th |" if ev.get('percentile_ci_lower') is not None else "| Percentile | — |",
        f"| FDR-adjusted p-value | {ev['fdr_adjusted_pvalue']:.4f} |" if ev.get('fdr_adjusted_pvalue') is not None else "| FDR p-value | — |",
        f"| Survives FDR | {'Yes' if ev.get('survives_fdr') else 'No'} |",
        f"| Comparable contracts | {ev.get('comparable_count', '—')} |",
        "",
    ])

    # Peer comparison
    if pc.get('available'):
        ps = pc['peer_statistics']
        aa = pc['anomaly_assessment']
        lines.extend([
            "## Peer Comparison",
            "",
            f"{pc['interpretation']}",
            "",
            "| Peer Statistic | Value |",
            "|---|---|",
            f"| Peer count | {pc['peer_count']} |",
            f"| Peer median | ${ps['median']:,.0f} |",
            f"| Peer P75 | ${ps['p75']:,.0f} |",
            f"| Peer P95 | ${ps['p95']:,.0f} |",
            f"| This contract percentile | {aa['percentile_rank']:.0f}th |",
            f"| Deviation from median | {aa['deviation_from_median_pct']:.1f}% |",
            "",
        ])

    # Vendor linkages
    lines.extend([
        "## Vendor Linkages",
        "",
        f"**Vendor:** {vl['vendor_name']} | **Match type:** {vl['match_type']} | "
        f"**Confidence:** {vl['linkage_confidence']}",
        "",
        f"- Total contracts: {vl['total_contracts']}",
    ])
    if vl['flagged_contracts']:
        lines.append(f"- Other flagged contracts: {len(vl['flagged_contracts'])}")
        for fc in vl['flagged_contracts'][:3]:
            lines.append(f"  - `{fc['contract_id']}`: {fc['fraud_tier']} (confidence {fc['confidence_score']})")
    pd = vl.get('political_donations', {})
    if pd.get('count', 0) > 0:
        lines.append(f"- Political donations: {pd['count']} records, ${pd['total_amount']:,.0f} total")
    lines.extend(["", f"*{vl['note']}*", ""])

    # Recommendations
    lines.extend([
        "## Recommended Actions",
        "",
        f"**Action:** {rec['recommended_action']}",
        "",
    ])
    for step in rec['next_steps']:
        lines.append(f"- {step}")
    lines.extend([
        "",
        f"**Escalation path:** {rec['escalation_path']}",
        "",
    ])

    # Disposition
    lines.extend([
        "## Analyst Disposition",
        "",
        "| Field | Value |",
        "|---|---|",
        "| Status | PENDING_REVIEW |",
        "| Reviewed by | ________________ |",
        "| Date | ________________ |",
        "| Disposition | [ ] TRUE_POSITIVE [ ] FALSE_POSITIVE [ ] BENIGN [ ] NEEDS_INFO |",
        "| Notes | |",
        "",
        "---",
        "",
        f"*SUNLIGHT Case Packet v{packet['case_packet_version']} | "
        f"Rulepack {packet['rulepack_version']} | "
        f"All findings are risk indicators, not allegations.*",
    ])

    return '\n'.join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate SUNLIGHT case packet")
    parser.add_argument('contract_id', help='Contract ID to generate packet for')
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--run-id', default=None)
    parser.add_argument('--out-dir', default='reports')
    parser.add_argument('--format', choices=['json', 'markdown', 'both'], default='both')
    args = parser.parse_args()

    db = args.db
    if not os.path.exists(db):
        db = os.path.join('..', db)

    os.makedirs(args.out_dir, exist_ok=True)

    packet = generate_case_packet(db, args.contract_id, run_id=args.run_id)

    if 'error' in packet:
        print(f"ERROR: {packet['error']}")
        sys.exit(1)

    if args.format in ('json', 'both'):
        path = os.path.join(args.out_dir, f'case_packet_{args.contract_id}.json')
        with open(path, 'w') as f:
            json.dump(packet, f, indent=2, default=str)
        print(f"JSON: {path}")

    if args.format in ('markdown', 'both'):
        path = os.path.join(args.out_dir, f'case_packet_{args.contract_id}.md')
        with open(path, 'w') as f:
            f.write(render_case_packet_md(packet))
        print(f"Markdown: {path}")
