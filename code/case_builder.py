"""
Case Builder — evidence package generator for flagged contracts.

For a flagged contract, compiles:
  - Contract metadata
  - All triggered signal scores with explanations
  - Peer group statistics (mean, std, confidence intervals)
  - Vendor history summary
  - Export to structured JSON + human-readable markdown summary
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SignalScore:
    """A single fraud signal with its score and explanation."""

    signal_name: str
    score: float  # 0-100
    weight: float  # how much it contributes to overall
    explanation: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PeerStats:
    """Statistics for the peer group (comparables) used in scoring."""

    peer_count: int = 0
    mean_amount: float = 0.0
    std_amount: float = 0.0
    median_amount: float = 0.0
    ci_lower: float = 0.0
    ci_upper: float = 0.0
    agency: str = ""
    selection_criteria: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CasePackage:
    """Complete evidence package for a flagged contract."""

    contract_id: str
    generated_at: str = ""
    contract_metadata: dict = field(default_factory=dict)
    fraud_tier: str = ""
    confidence_score: float = 0.0
    triage_priority: int = 0
    signals: list = field(default_factory=list)
    peer_stats: PeerStats = field(default_factory=PeerStats)
    vendor_summary: dict = field(default_factory=dict)
    markup_analysis: dict = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_markdown(self) -> str:
        return _render_markdown(self)


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------

def _extract_signals(score_row: dict) -> list:
    """Extract individual fraud signals from a contract score row."""
    signals = []

    # 1. Markup anomaly
    markup = score_row.get("markup_pct", 0)
    ci_lower = score_row.get("markup_ci_lower", 0)
    ci_upper = score_row.get("markup_ci_upper", 0)
    if markup and markup > 0:
        severity = min(markup / 5, 100)  # 500% markup = 100
        signals.append(
            SignalScore(
                signal_name="Price Markup Anomaly",
                score=round(severity, 1),
                weight=0.30,
                explanation=(
                    f"Contract priced {markup:.1f}% above peer group median "
                    f"(95% CI: {ci_lower:.1f}% - {ci_upper:.1f}%)"
                ),
                evidence={"markup_pct": markup, "ci_lower": ci_lower, "ci_upper": ci_upper},
            )
        )

    # 2. Bootstrap percentile
    pctl = score_row.get("bootstrap_percentile", 0)
    if pctl and pctl > 50:
        signals.append(
            SignalScore(
                signal_name="Bootstrap Percentile",
                score=round(pctl, 1),
                weight=0.20,
                explanation=(
                    f"Contract at {pctl:.1f}th percentile of bootstrap distribution "
                    f"— {'extreme' if pctl > 95 else 'elevated'} outlier"
                ),
                evidence={"percentile": pctl},
            )
        )

    # 3. Bayesian posterior
    posterior = score_row.get("bayesian_posterior", 0)
    if posterior and posterior > 0.1:
        signals.append(
            SignalScore(
                signal_name="Bayesian Fraud Posterior",
                score=round(posterior * 100, 1),
                weight=0.25,
                explanation=(
                    f"Posterior probability of fraud: {posterior:.1%} "
                    f"(prior: {score_row.get('bayesian_prior', 'N/A')})"
                ),
                evidence={
                    "posterior": posterior,
                    "prior": score_row.get("bayesian_prior"),
                    "likelihood_ratio": score_row.get("bayesian_likelihood_ratio"),
                },
            )
        )

    # 4. Z-score
    zscore = score_row.get("raw_zscore", 0)
    if zscore and abs(zscore) > 2:
        signals.append(
            SignalScore(
                signal_name="Statistical Z-Score",
                score=round(min(abs(zscore) * 20, 100), 1),
                weight=0.15,
                explanation=(
                    f"Raw z-score: {zscore:.2f} "
                    f"({'highly' if abs(zscore) > 3 else 'moderately'} anomalous)"
                ),
                evidence={"raw_zscore": zscore, "log_zscore": score_row.get("log_zscore")},
            )
        )

    # 5. FDR survival
    survives = score_row.get("survives_fdr", False)
    fdr_pval = score_row.get("fdr_adjusted_pvalue")
    if survives:
        signals.append(
            SignalScore(
                signal_name="FDR Significance",
                score=90.0,
                weight=0.10,
                explanation=(
                    f"Survives Benjamini-Hochberg FDR correction "
                    f"(adjusted p-value: {fdr_pval:.4f})"
                    if fdr_pval is not None
                    else "Survives FDR correction"
                ),
                evidence={"survives_fdr": True, "fdr_adjusted_pvalue": fdr_pval},
            )
        )

    return signals


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_markdown(pkg: CasePackage) -> str:
    """Render a case package as a human-readable markdown report."""
    lines = []
    lines.append(f"# Case Package: {pkg.contract_id}")
    lines.append(f"**Generated:** {pkg.generated_at}")
    lines.append(f"**Tier:** {pkg.fraud_tier} | **Confidence:** {pkg.confidence_score:.0f} | **Priority:** {pkg.triage_priority}")
    lines.append("")

    # Contract metadata
    lines.append("## Contract Details")
    meta = pkg.contract_metadata
    lines.append(f"| Field | Value |")
    lines.append(f"|---|---|")
    for key in ("vendor_name", "agency_name", "award_amount", "description", "start_date"):
        val = meta.get(key, "N/A")
        if key == "award_amount" and isinstance(val, (int, float)):
            val = f"${val:,.2f}"
        lines.append(f"| {key.replace('_', ' ').title()} | {val} |")
    lines.append("")

    # Signals
    lines.append("## Triggered Signals")
    lines.append("")
    if pkg.signals:
        for s in sorted(pkg.signals, key=lambda x: x.get("score", 0) if isinstance(x, dict) else x.score, reverse=True):
            if isinstance(s, dict):
                lines.append(f"### {s['signal_name']} (Score: {s['score']})")
                lines.append(f"- **Weight:** {s['weight']:.0%}")
                lines.append(f"- {s['explanation']}")
            else:
                lines.append(f"### {s.signal_name} (Score: {s.score})")
                lines.append(f"- **Weight:** {s.weight:.0%}")
                lines.append(f"- {s.explanation}")
            lines.append("")
    else:
        lines.append("No signals triggered.")
        lines.append("")

    # Peer stats
    lines.append("## Peer Group Statistics")
    ps = pkg.peer_stats if isinstance(pkg.peer_stats, dict) else pkg.peer_stats.to_dict()
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Peer Count | {ps.get('peer_count', 0)} |")
    lines.append(f"| Mean Amount | ${ps.get('mean_amount', 0):,.2f} |")
    lines.append(f"| Std Dev | ${ps.get('std_amount', 0):,.2f} |")
    lines.append(f"| Median | ${ps.get('median_amount', 0):,.2f} |")
    lines.append(f"| 95% CI | ${ps.get('ci_lower', 0):,.2f} — ${ps.get('ci_upper', 0):,.2f} |")
    lines.append(f"| Agency | {ps.get('agency', 'N/A')} |")
    lines.append("")

    # Vendor summary
    if pkg.vendor_summary:
        lines.append("## Vendor Summary")
        vs = pkg.vendor_summary
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        for k, v in vs.items():
            lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")

    # Markup analysis
    if pkg.markup_analysis:
        lines.append("## Markup Analysis")
        ma = pkg.markup_analysis
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        for k, v in ma.items():
            if isinstance(v, float):
                lines.append(f"| {k.replace('_', ' ').title()} | {v:.2f} |")
            else:
                lines.append(f"| {k.replace('_', ' ').title()} | {v} |")
        lines.append("")

    # Recommendation
    if pkg.recommendation:
        lines.append("## Recommendation")
        lines.append(f"{pkg.recommendation}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by SUNLIGHT Case Builder*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Package builder
# ---------------------------------------------------------------------------

def build_case_package(
    db_path: str,
    contract_id: str,
    run_id: Optional[str] = None,
    vendor_profile: Optional[dict] = None,
) -> CasePackage:
    """Build a complete evidence package for a flagged contract.

    Args:
        db_path: Path to SQLite database.
        contract_id: The contract to package.
        run_id: Analysis run ID. If None, uses latest completed run.
        vendor_profile: Pre-built vendor profile dict. If None, builds a minimal summary.

    Returns:
        CasePackage with all evidence compiled.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    pkg = CasePackage(
        contract_id=contract_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # --- Contract metadata ---
    c.execute("SELECT * FROM contracts WHERE contract_id = ?", (contract_id,))
    contract_row = c.fetchone()
    if contract_row:
        pkg.contract_metadata = dict(contract_row)

    # --- Score data ---
    if run_id is None:
        c.execute(
            "SELECT run_id FROM analysis_runs WHERE status = 'COMPLETED' ORDER BY completed_at DESC LIMIT 1"
        )
        run_row = c.fetchone()
        if run_row:
            run_id = run_row["run_id"]

    score_data = {}
    if run_id:
        c.execute(
            "SELECT * FROM contract_scores WHERE contract_id = ? AND run_id = ?",
            (contract_id, run_id),
        )
        score_row = c.fetchone()
        if score_row:
            score_data = dict(score_row)
            pkg.fraud_tier = score_data.get("fraud_tier", "")
            pkg.confidence_score = score_data.get("confidence_score", 0)
            pkg.triage_priority = score_data.get("triage_priority", 0)

    # --- Signals ---
    if score_data:
        pkg.signals = [s.to_dict() for s in _extract_signals(score_data)]
        pkg.markup_analysis = {
            "markup_pct": score_data.get("markup_pct"),
            "markup_ci_lower": score_data.get("markup_ci_lower"),
            "markup_ci_upper": score_data.get("markup_ci_upper"),
            "raw_zscore": score_data.get("raw_zscore"),
            "log_zscore": score_data.get("log_zscore"),
            "bootstrap_percentile": score_data.get("bootstrap_percentile"),
            "bayesian_posterior": score_data.get("bayesian_posterior"),
            "raw_pvalue": score_data.get("raw_pvalue"),
            "fdr_adjusted_pvalue": score_data.get("fdr_adjusted_pvalue"),
            "survives_fdr": score_data.get("survives_fdr"),
        }

    # --- Peer group stats ---
    vendor_name = pkg.contract_metadata.get("vendor_name")
    agency_name = pkg.contract_metadata.get("agency_name")
    award_amount = pkg.contract_metadata.get("award_amount", 0)

    if agency_name:
        c.execute(
            """
            SELECT award_amount FROM contracts
            WHERE agency_name = ? AND contract_id != ?
            """,
            (agency_name, contract_id),
        )
        peer_amounts = [r["award_amount"] for r in c.fetchall() if r["award_amount"]]
        if peer_amounts:
            import numpy as np

            arr = np.array(peer_amounts, dtype=float)
            pkg.peer_stats = PeerStats(
                peer_count=len(peer_amounts),
                mean_amount=float(np.mean(arr)),
                std_amount=float(np.std(arr)),
                median_amount=float(np.median(arr)),
                ci_lower=float(np.percentile(arr, 2.5)),
                ci_upper=float(np.percentile(arr, 97.5)),
                agency=agency_name,
                selection_criteria=f"Same agency ({agency_name})",
            )

    # --- Vendor summary ---
    if vendor_profile:
        pkg.vendor_summary = vendor_profile
    elif vendor_name:
        c.execute(
            """
            SELECT COUNT(*) as cnt,
                   COALESCE(SUM(award_amount), 0) as total,
                   COALESCE(AVG(award_amount), 0) as avg_val
            FROM contracts WHERE vendor_name = ?
            """,
            (vendor_name,),
        )
        vs = c.fetchone()
        pkg.vendor_summary = {
            "vendor_name": vendor_name,
            "contract_count": vs["cnt"],
            "total_awards": vs["total"],
            "average_value": round(vs["avg_val"], 2),
        }

    # --- Recommendation ---
    tier = pkg.fraud_tier
    if tier == "RED":
        pkg.recommendation = (
            "**IMMEDIATE REVIEW RECOMMENDED.** This contract exhibits strong statistical "
            "indicators of price anomaly. Recommend detailed invoice audit, vendor cost "
            "analysis, and comparison against independent cost estimates."
        )
    elif tier == "YELLOW":
        pkg.recommendation = (
            "**ELEVATED RISK — REVIEW WARRANTED.** This contract shows moderate statistical "
            "anomalies. Recommend desk review of pricing justification and comparison against "
            "recent peer contracts."
        )
    else:
        pkg.recommendation = (
            "No immediate action required. Contract scoring is within normal parameters."
        )

    conn.close()
    return pkg


def export_case_package(pkg: CasePackage, json_path: str, md_path: Optional[str] = None):
    """Export a case package to JSON and optionally markdown files."""
    with open(json_path, "w") as f:
        f.write(pkg.to_json())

    if md_path:
        with open(md_path, "w") as f:
            f.write(pkg.to_markdown())
