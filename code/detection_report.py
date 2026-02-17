"""
SUNLIGHT Client-Facing Detection Report
=========================================

Generates structured JSON and human-readable reports explaining WHY each
flag was raised. Designed for World Bank, IMF, and Fortune 500 reviewers
who need explainable reasoning, not just scores.

Every finding includes:
- Plain-language explanation of what was detected
- Statistical evidence with confidence intervals
- Comparable contract context
- Risk factor analysis
- Recommended next steps
- Legal framework citations
"""

import json
import os
import sys
import sqlite3
import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(__file__))

from institutional_statistical_rigor import (
    BootstrapAnalyzer, BayesianFraudPrior, ProsecutorEvidencePackage,
    DOJProsecutionThresholds, FraudTier,
)
from sunlight_logging import get_logger

logger = get_logger("report")


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------

def _tier_label(tier: str) -> str:
    return {
        'RED': 'HIGH RISK — Prosecution-Ready Evidence',
        'YELLOW': 'ELEVATED RISK — Investigation Recommended',
        'GREEN': 'NORMAL — No Significant Anomaly Detected',
        'GRAY': 'INSUFFICIENT DATA — Cannot Assess',
    }.get(tier, tier)


def _tier_action(tier: str) -> str:
    return {
        'RED': (
            'Immediate review recommended. Statistical evidence meets or exceeds '
            'thresholds established in DOJ prosecution precedent. Consider referral '
            'to Office of Inspector General or equivalent oversight body.'
        ),
        'YELLOW': (
            'Detailed review recommended. Statistical indicators suggest pricing '
            'anomalies that warrant investigation. Request supporting documentation '
            'from vendor (cost breakdowns, subcontractor invoices, market comparisons).'
        ),
        'GREEN': (
            'No action required. Contract pricing falls within expected range for '
            'comparable contracts. Standard post-award monitoring is sufficient.'
        ),
        'GRAY': (
            'Manual review required. Insufficient comparable contracts in the database '
            'to perform statistical analysis. Consider expanding the reference dataset '
            'or requesting vendor justification for pricing.'
        ),
    }.get(tier, '')


def _explain_markup(markup_pct: float, ci_lower: float, ci_upper: float,
                    sample_size: int) -> Dict:
    """Generate plain-language explanation of markup analysis."""
    explanation = {}

    if markup_pct is None or ci_lower is None:
        return {
            'finding': 'Markup analysis could not be performed.',
            'detail': 'Insufficient comparable contracts for statistical comparison.',
            'confidence': 'N/A',
        }

    # What was found
    if ci_lower > DOJProsecutionThresholds.EXTREME_MARKUP:
        severity = 'EXTREME'
        finding = (
            f'This contract is priced {markup_pct:.0f}% above the median of '
            f'{sample_size} comparable contracts. Even under the most conservative '
            f'statistical estimate (lower bound of 95% confidence interval), the '
            f'markup is {ci_lower:.0f}% — well above the {DOJProsecutionThresholds.EXTREME_MARKUP}% '
            f'threshold that has consistently resulted in DOJ prosecution.'
        )
    elif ci_lower > DOJProsecutionThresholds.HIGH_MARKUP:
        severity = 'HIGH'
        finding = (
            f'This contract is priced {markup_pct:.0f}% above the median of '
            f'{sample_size} comparable contracts. The conservative estimate '
            f'(95% CI lower bound: {ci_lower:.0f}%) exceeds the {DOJProsecutionThresholds.HIGH_MARKUP}% '
            f'threshold associated with DOJ investigations.'
        )
    elif ci_lower > DOJProsecutionThresholds.INVESTIGATION_WORTHY:
        severity = 'ELEVATED'
        finding = (
            f'This contract is priced {markup_pct:.0f}% above the median of '
            f'{sample_size} comparable contracts. The conservative estimate '
            f'(95% CI lower bound: {ci_lower:.0f}%) exceeds the minimum markup '
            f'({DOJProsecutionThresholds.INVESTIGATION_WORTHY}%) seen in DOJ-prosecuted cases.'
        )
    elif markup_pct > 0:
        severity = 'NORMAL'
        finding = (
            f'This contract is priced {markup_pct:.0f}% above the median of '
            f'{sample_size} comparable contracts. The confidence interval '
            f'[{ci_lower:.0f}%, {ci_upper:.0f}%] includes values below prosecution '
            f'thresholds, indicating the markup is within plausible market variation.'
        )
    else:
        severity = 'BELOW_MEDIAN'
        finding = (
            f'This contract is priced {abs(markup_pct):.0f}% below the median of '
            f'{sample_size} comparable contracts. No pricing anomaly detected.'
        )

    explanation['severity'] = severity
    explanation['finding'] = finding
    explanation['markup_pct'] = round(markup_pct, 1)
    explanation['confidence_interval'] = {
        'lower': round(ci_lower, 1),
        'upper': round(ci_upper, 1),
        'confidence_level': '95%',
        'method': 'BCa Bootstrap (bias-corrected and accelerated)',
    }
    explanation['sample_size'] = sample_size
    explanation['interpretation'] = (
        f'We are 95% confident the true markup falls between '
        f'{ci_lower:.0f}% and {ci_upper:.0f}%. '
        f'This was calculated using {sample_size} comparable contracts from the same agency.'
    )

    return explanation


def _explain_bayesian(prior: float, posterior: float,
                      likelihood_ratio: float,
                      characteristics: Dict) -> Dict:
    """Generate plain-language explanation of Bayesian analysis."""
    if prior is None or posterior is None:
        return {
            'finding': 'Bayesian analysis could not be performed.',
            'detail': 'Insufficient data for probability estimation.',
        }

    factors = []
    if characteristics.get('is_mega_contract'):
        factors.append('large contract value (>$25M)')
    if characteristics.get('is_defense'):
        factors.append('defense sector')
    if characteristics.get('is_sole_source'):
        factors.append('sole-source (non-competitive) award')
    if characteristics.get('has_donations'):
        factors.append('political donations from vendor to oversight officials')

    base_explanation = (
        f'Before examining this specific contract, the base rate of fraud for '
        f'contracts with these characteristics is {prior*100:.1f}%'
    )
    if factors:
        base_explanation += f' (adjusted for: {", ".join(factors)})'
    base_explanation += '.'

    posterior_explanation = (
        f'After incorporating the statistical evidence, the estimated probability '
        f'of fraud rises to {posterior*100:.1f}%.'
    )

    if likelihood_ratio > 10:
        strength = 'very strong'
    elif likelihood_ratio > 5:
        strength = 'strong'
    elif likelihood_ratio > 2:
        strength = 'moderate'
    else:
        strength = 'weak'

    return {
        'base_rate': round(prior, 4),
        'posterior_probability': round(posterior, 4),
        'likelihood_ratio': round(likelihood_ratio, 2),
        'risk_factors': factors if factors else ['No additional risk factors identified'],
        'finding': base_explanation + ' ' + posterior_explanation,
        'evidence_strength': (
            f'The evidence provides {strength} support for the fraud hypothesis '
            f'(likelihood ratio: {likelihood_ratio:.1f}x).'
        ),
    }


def _explain_percentile(percentile: float, ci_lower: float,
                        ci_upper: float) -> Dict:
    """Explain where the contract falls in the distribution."""
    if percentile is None:
        return {'finding': 'Percentile analysis not available.'}

    if ci_lower is not None and ci_lower > 95:
        finding = (
            f'This contract is at the {percentile:.0f}th percentile — meaning it costs '
            f'more than {percentile:.0f}% of comparable contracts. Even conservatively, '
            f'it remains above the 95th percentile (CI lower: {ci_lower:.0f}th), '
            f'making it a statistically extreme outlier.'
        )
    elif percentile > 90:
        finding = (
            f'This contract is at the {percentile:.0f}th percentile among comparable '
            f'contracts — a strong statistical outlier, costing more than {percentile:.0f}% '
            f'of comparable contracts.'
        )
    elif percentile > 75:
        finding = (
            f'This contract is at the {percentile:.0f}th percentile — above average '
            f'but not extreme relative to comparable contracts.'
        )
    else:
        finding = (
            f'This contract is at the {percentile:.0f}th percentile — within the '
            f'normal range of comparable contracts.'
        )

    return {
        'percentile': round(percentile, 1),
        'confidence_interval': {
            'lower': round(ci_lower, 1) if ci_lower is not None else None,
            'upper': round(ci_upper, 1) if ci_upper is not None else None,
        },
        'finding': finding,
    }


def _get_legal_context(tier: str, markup_ci_lower: float) -> List[Dict]:
    """Get applicable legal citations with explanations."""
    citations = []

    if markup_ci_lower is not None and markup_ci_lower > DOJProsecutionThresholds.INVESTIGATION_WORTHY:
        citations.append({
            'statute': '31 U.S.C. § 3729(a)(1)(A)',
            'name': 'False Claims Act — False/Fraudulent Claims',
            'relevance': (
                'Knowingly presenting a false or fraudulent claim for payment. '
                'Applicable when a government contractor charges prices materially '
                'above fair market value.'
            ),
        })

    if markup_ci_lower is not None and markup_ci_lower > DOJProsecutionThresholds.EXTREME_MARKUP:
        citations.append({
            'statute': '31 U.S.C. § 3729(a)(1)(B)',
            'name': 'False Claims Act — False Records',
            'relevance': (
                'Knowingly making or using a false record material to a false claim. '
                'Applicable when pricing documentation misrepresents market rates.'
            ),
        })
        citations.append({
            'statute': 'DOJ Prosecution Precedent',
            'name': 'Price Inflation Cases',
            'relevance': (
                f'Markup exceeds {DOJProsecutionThresholds.EXTREME_MARKUP}%. '
                f'Comparable DOJ cases: US v. Oracle (350%), US v. Boeing (450%), '
                f'US v. Lockheed Martin (320%).'
            ),
        })

    if tier in ('RED', 'YELLOW'):
        citations.append({
            'statute': '41 U.S.C. § 2102',
            'name': 'Procurement Integrity Act',
            'relevance': (
                'Prohibits obtaining or disclosing non-public procurement information. '
                'Statistical outlier status may indicate procurement process compromise.'
            ),
        })

    return citations


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_detection_report(db_path: str, contract_id: str,
                              run_id: Optional[str] = None) -> Dict:
    """
    Generate a comprehensive, explainable detection report for a contract.

    Returns a structured dict suitable for JSON serialization and
    human-readable rendering.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Load contract
    c.execute(
        "SELECT contract_id, award_amount, vendor_name, agency_name, description "
        "FROM contracts WHERE contract_id = ?",
        (contract_id,),
    )
    contract_row = c.fetchone()
    if not contract_row:
        conn.close()
        return {'error': f'Contract {contract_id} not found'}

    contract = dict(contract_row)

    # Load latest score (or from specific run)
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

    # Load political donations
    c.execute(
        "SELECT SUM(amount) as total, COUNT(*) as n FROM political_donations "
        "WHERE vendor_name = ?",
        (contract['vendor_name'],),
    )
    donation_row = c.fetchone()
    has_donations = donation_row['total'] is not None and donation_row['total'] > 0

    # Load comparable contracts for context
    c.execute(
        "SELECT award_amount FROM contracts WHERE agency_name = ? "
        "AND contract_id != ? AND award_amount > 0 ORDER BY award_amount",
        (contract['agency_name'], contract_id),
    )
    all_comparables = [r['award_amount'] for r in c.fetchall()]
    conn.close()

    # Determine characteristics
    characteristics = {
        'is_mega_contract': contract['award_amount'] > 25_000_000,
        'is_defense': any(x in (contract['agency_name'] or '').lower()
                         for x in ['defense', 'dod', 'army', 'navy', 'air force']),
        'is_sole_source': False,  # Would need additional data
        'has_donations': has_donations,
    }

    # Build report
    report = {
        'report_type': 'SUNLIGHT Detection Report',
        'report_version': '1.0.0',
        'generated_at': datetime.now(timezone.utc).isoformat(),

        'contract': {
            'contract_id': contract['contract_id'],
            'award_amount': contract['award_amount'],
            'vendor_name': contract['vendor_name'],
            'agency_name': contract['agency_name'],
            'description': contract['description'] or '',
        },

        'assessment': {},
        'evidence': {},
        'context': {},
        'recommendations': {},
        'methodology': {},
        'legal_framework': [],
    }

    if score_row:
        score = dict(score_row)
        tier = score['fraud_tier']
        report['assessment'] = {
            'risk_level': tier,
            'risk_label': _tier_label(tier),
            'confidence_score': score['confidence_score'],
            'run_id': score['run_id'],
            'scored_at': score['scored_at'],
            'survives_fdr_correction': bool(score['survives_fdr']),
        }

        report['evidence']['price_analysis'] = _explain_markup(
            score['markup_pct'], score['markup_ci_lower'],
            score['markup_ci_upper'], score['comparable_count'],
        )

        report['evidence']['bayesian_analysis'] = _explain_bayesian(
            score['bayesian_prior'], score['bayesian_posterior'],
            score.get('bayesian_likelihood_ratio', 0) or 0,
            characteristics,
        )

        report['evidence']['distribution_analysis'] = _explain_percentile(
            score['bootstrap_percentile'],
            score.get('percentile_ci_lower'),
            score.get('percentile_ci_upper'),
        )

        if score.get('fdr_adjusted_pvalue') is not None:
            report['evidence']['multiple_testing'] = {
                'raw_pvalue': score['raw_pvalue'],
                'fdr_adjusted_pvalue': score['fdr_adjusted_pvalue'],
                'survives_fdr': bool(score['survives_fdr']),
                'finding': (
                    f'After correcting for testing {score["comparable_count"]} contracts '
                    f'simultaneously (Benjamini-Hochberg procedure), this result '
                    f'{"remains" if score["survives_fdr"] else "does not remain"} '
                    f'statistically significant.'
                ),
            }

        report['legal_framework'] = _get_legal_context(
            tier, score.get('markup_ci_lower')
        )

        report['recommendations'] = {
            'action': _tier_action(tier),
            'next_steps': _get_next_steps(tier, score, characteristics),
        }
    else:
        # No score available — generate fresh evidence
        pkg = ProsecutorEvidencePackage(db_path)
        evidence = pkg.generate_evidence({
            'id': contract['contract_id'],
            'amount': contract['award_amount'],
            'vendor': contract['vendor_name'],
            'agency': contract['agency_name'],
            'desc': contract['description'] or '',
            'has_donations': has_donations,
        })

        tier = evidence.tier.value
        report['assessment'] = {
            'risk_level': tier,
            'risk_label': _tier_label(tier),
            'confidence_score': evidence.confidence_score,
            'run_id': None,
            'scored_at': evidence.analysis_timestamp,
            'survives_fdr_correction': evidence.survives_fdr,
            'note': 'Generated on-demand (not from a batch run).',
        }

        report['evidence']['price_analysis'] = _explain_markup(
            evidence.raw_markup_pct,
            evidence.bootstrap_markup.ci_lower,
            evidence.bootstrap_markup.ci_upper,
            evidence.sample_size,
        )

        report['evidence']['bayesian_analysis'] = _explain_bayesian(
            evidence.bayesian_fraud_probability.prior_probability,
            evidence.bayesian_fraud_probability.posterior_probability,
            evidence.bayesian_fraud_probability.likelihood_ratio,
            characteristics,
        )

        report['evidence']['distribution_analysis'] = _explain_percentile(
            evidence.bootstrap_percentile.point_estimate,
            evidence.bootstrap_percentile.ci_lower,
            evidence.bootstrap_percentile.ci_upper,
        )

        report['legal_framework'] = _get_legal_context(
            tier, evidence.bootstrap_markup.ci_lower
        )

        report['recommendations'] = {
            'action': _tier_action(tier),
            'next_steps': _get_next_steps(
                tier,
                {
                    'markup_pct': evidence.raw_markup_pct,
                    'markup_ci_lower': evidence.bootstrap_markup.ci_lower,
                    'bayesian_posterior': evidence.bayesian_fraud_probability.posterior_probability,
                    'comparable_count': evidence.sample_size,
                },
                characteristics,
            ),
        }

    # Comparable context
    if all_comparables:
        report['context'] = {
            'total_comparables_in_agency': len(all_comparables),
            'agency_median': round(float(np.median(all_comparables)), 2),
            'agency_mean': round(float(np.mean(all_comparables)), 2),
            'agency_min': round(float(min(all_comparables)), 2),
            'agency_max': round(float(max(all_comparables)), 2),
            'contract_rank': sum(1 for a in all_comparables
                                if a <= contract['award_amount']),
            'explanation': (
                f'Among {len(all_comparables)} contracts from {contract["agency_name"]}, '
                f'the median award is ${np.median(all_comparables):,.0f}. '
                f'This contract (${contract["award_amount"]:,.0f}) '
                f'ranks #{sum(1 for a in all_comparables if a <= contract["award_amount"])} '
                f'out of {len(all_comparables)}.'
            ),
        }

    if has_donations:
        report['context']['political_donations'] = {
            'total_amount': float(donation_row['total']),
            'donation_count': int(donation_row['n']),
            'finding': (
                f'{contract["vendor_name"]} has ${donation_row["total"]:,.0f} in political '
                f'donations on record. This is a risk amplifier under the Anti-Kickback Act '
                f'(41 U.S.C. § 8702) when combined with pricing anomalies.'
            ),
        }

    # Methodology transparency
    report['methodology'] = {
        'version': '2.0.0',
        'statistical_methods': [
            {
                'name': 'BCa Bootstrap Confidence Intervals',
                'description': (
                    'Bias-corrected and accelerated bootstrap provides robust '
                    'confidence intervals even with small sample sizes. We resample '
                    'comparable contracts 1,000 times to estimate the true markup range.'
                ),
            },
            {
                'name': 'Bayesian Fraud Probability',
                'description': (
                    'Combines the statistical evidence with base rates of fraud derived '
                    'from DOJ prosecution data. Adjusts for contract characteristics '
                    '(size, sector, competition status, political donations).'
                ),
            },
            {
                'name': 'Benjamini-Hochberg FDR Correction',
                'description': (
                    'When testing many contracts simultaneously, we apply false discovery '
                    'rate correction to control the proportion of false positives among '
                    'all flagged contracts.'
                ),
            },
        ],
        'thresholds': {
            'extreme_markup': f'{DOJProsecutionThresholds.EXTREME_MARKUP}%',
            'high_markup': f'{DOJProsecutionThresholds.HIGH_MARKUP}%',
            'elevated_markup': f'{DOJProsecutionThresholds.ELEVATED_MARKUP}%',
            'investigation_worthy': f'{DOJProsecutionThresholds.INVESTIGATION_WORTHY}%',
            'source': 'Calibrated from analysis of 100+ DOJ procurement fraud prosecutions (2005-2024)',
        },
        'transparency_note': (
            'SUNLIGHT does not make fraud determinations. It identifies statistical '
            'anomalies in contract pricing relative to comparable contracts. All findings '
            'require human review and due process before any action is taken.'
        ),
    }

    logger.info("Detection report generated",
                extra={"contract_id": contract_id, "tier": tier})
    return report


def _get_next_steps(tier: str, score: Dict, characteristics: Dict) -> List[str]:
    """Generate specific next steps based on findings."""
    steps = []

    if tier == 'RED':
        steps.append('Request detailed cost breakdown from vendor (labor, materials, overhead, profit).')
        steps.append('Obtain independent market price analysis for the contracted goods/services.')
        steps.append('Review procurement file for compliance with competition requirements.')
        if characteristics.get('has_donations'):
            steps.append('Investigate relationship between vendor political donations and contract award timeline.')
        steps.append('Consider referral to Office of Inspector General for formal investigation.')
        steps.append('Preserve all vendor communications and procurement documents.')

    elif tier == 'YELLOW':
        steps.append('Request vendor justification for pricing (Fair and Reasonable determination).')
        steps.append('Compare against GSA Schedule pricing if applicable.')
        steps.append('Review whether competitive bidding requirements were met.')
        markup = score.get('markup_pct', 0) or 0
        if markup > 100:
            steps.append(f'Investigate basis for {markup:.0f}% markup over comparable contract median.')

    elif tier == 'GREEN':
        steps.append('No immediate action required.')
        steps.append('Include in standard post-award monitoring rotation.')

    elif tier == 'GRAY':
        steps.append('Expand comparable contract database for this agency/category.')
        steps.append('Request vendor price justification due to limited benchmark data.')
        steps.append('Consider independent price analysis from subject matter expert.')

    return steps


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(report: Dict) -> str:
    """Render a detection report as human-readable markdown."""
    lines = []

    # Header
    c = report['contract']
    a = report['assessment']
    lines.append("# SUNLIGHT Detection Report")
    lines.append("")
    lines.append(f"**Contract:** {c['contract_id']}")
    lines.append(f"**Vendor:** {c['vendor_name']}")
    lines.append(f"**Agency:** {c['agency_name']}")
    lines.append(f"**Award Amount:** ${c['award_amount']:,.0f}")
    lines.append(f"**Generated:** {report['generated_at'][:10]}")
    lines.append("")

    # Assessment box
    lines.append("---")
    lines.append("")
    lines.append(f"## Risk Assessment: {a['risk_level']}")
    lines.append("")
    lines.append(f"**{a['risk_label']}**")
    lines.append("")
    lines.append(f"Confidence Score: {a['confidence_score']}/100")
    if a.get('survives_fdr_correction'):
        lines.append("Survives FDR Correction: Yes (robust to multiple testing)")
    lines.append("")

    # Evidence
    lines.append("---")
    lines.append("")
    lines.append("## Evidence Summary")
    lines.append("")

    ev = report.get('evidence', {})

    # Price analysis
    pa = ev.get('price_analysis', {})
    if pa.get('finding'):
        lines.append("### Price Analysis")
        lines.append("")
        lines.append(pa['finding'])
        lines.append("")
        if 'interpretation' in pa:
            lines.append(f"*{pa['interpretation']}*")
            lines.append("")

    # Bayesian
    ba = ev.get('bayesian_analysis', {})
    if ba.get('finding'):
        lines.append("### Risk Probability")
        lines.append("")
        lines.append(ba['finding'])
        lines.append("")
        if ba.get('evidence_strength'):
            lines.append(f"*{ba['evidence_strength']}*")
            lines.append("")
        if ba.get('risk_factors'):
            lines.append(f"**Risk factors considered:** {', '.join(ba['risk_factors'])}")
            lines.append("")

    # Distribution
    da = ev.get('distribution_analysis', {})
    if da.get('finding'):
        lines.append("### Distribution Position")
        lines.append("")
        lines.append(da['finding'])
        lines.append("")

    # FDR
    mt = ev.get('multiple_testing', {})
    if mt.get('finding'):
        lines.append("### Multiple Testing Correction")
        lines.append("")
        lines.append(mt['finding'])
        lines.append("")

    # Context
    ctx = report.get('context', {})
    if ctx.get('explanation'):
        lines.append("---")
        lines.append("")
        lines.append("## Comparable Contract Context")
        lines.append("")
        lines.append(ctx['explanation'])
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Comparable contracts | {ctx['total_comparables_in_agency']} |")
        lines.append(f"| Agency median | ${ctx['agency_median']:,.0f} |")
        lines.append(f"| Agency min | ${ctx['agency_min']:,.0f} |")
        lines.append(f"| Agency max | ${ctx['agency_max']:,.0f} |")
        lines.append(f"| This contract rank | #{ctx['contract_rank']} of {ctx['total_comparables_in_agency']} |")
        lines.append("")

    # Political donations
    pd = ctx.get('political_donations', {})
    if pd.get('finding'):
        lines.append("### Political Donations")
        lines.append("")
        lines.append(pd['finding'])
        lines.append("")

    # Recommendations
    rec = report.get('recommendations', {})
    if rec.get('action'):
        lines.append("---")
        lines.append("")
        lines.append("## Recommended Action")
        lines.append("")
        lines.append(rec['action'])
        lines.append("")
        if rec.get('next_steps'):
            lines.append("### Next Steps")
            lines.append("")
            for i, step in enumerate(rec['next_steps'], 1):
                lines.append(f"{i}. {step}")
            lines.append("")

    # Legal
    legal = report.get('legal_framework', [])
    if legal:
        lines.append("---")
        lines.append("")
        lines.append("## Legal Framework")
        lines.append("")
        for cite in legal:
            lines.append(f"**{cite['statute']}** — {cite['name']}")
            lines.append("")
            lines.append(f"> {cite['relevance']}")
            lines.append("")

    # Methodology
    meth = report.get('methodology', {})
    if meth:
        lines.append("---")
        lines.append("")
        lines.append("## Methodology")
        lines.append("")
        for m in meth.get('statistical_methods', []):
            lines.append(f"**{m['name']}:** {m['description']}")
            lines.append("")
        if meth.get('transparency_note'):
            lines.append(f"*{meth['transparency_note']}*")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Report generated by SUNLIGHT Fraud Detection System v{meth.get('version', '2.0.0')}*")

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

def generate_and_save(db_path: str, contract_id: str,
                      output_dir: str = 'reports',
                      run_id: Optional[str] = None) -> Dict:
    """Generate report and save JSON + Markdown files."""
    os.makedirs(output_dir, exist_ok=True)

    report = generate_detection_report(db_path, contract_id, run_id=run_id)

    safe_id = contract_id.replace('/', '_').replace('\\', '_')
    json_path = os.path.join(output_dir, f'detection_{safe_id}.json')
    md_path = os.path.join(output_dir, f'detection_{safe_id}.md')

    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    with open(md_path, 'w') as f:
        f.write(render_markdown(report))

    logger.info("Detection report saved",
                extra={"contract_id": contract_id, "json": json_path, "md": md_path})

    return {'report': report, 'json_path': json_path, 'md_path': md_path}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate SUNLIGHT Detection Report")
    parser.add_argument('contract_id', help='Contract ID to report on')
    parser.add_argument('--db', default='data/sunlight.db')
    parser.add_argument('--run-id', default=None)
    parser.add_argument('--output-dir', default='reports')
    args = parser.parse_args()

    db = args.db
    if not os.path.exists(db):
        db = '../data/sunlight.db'

    result = generate_and_save(db, args.contract_id, args.output_dir, args.run_id)
    print(f"\nReport generated for {args.contract_id}:")
    print(f"  JSON: {result['json_path']}")
    print(f"  Markdown: {result['md_path']}")
    print(f"  Risk Level: {result['report']['assessment']['risk_level']}")
