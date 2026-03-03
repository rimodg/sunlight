"""
Priority Queue — triage engine for flagged contracts.

Takes a list of flagged contracts and ranks them by:
  - Expected value of fraud (contract_value x fraud_probability)
  - Data completeness score
  - Investigation complexity estimate

Returns a prioritized list with recommended next actions.
"""

import sqlite3
import math
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TriageItem:
    """A single flagged contract with computed priority metadata."""

    contract_id: str
    vendor_name: str = ""
    agency_name: str = ""
    award_amount: float = 0.0
    fraud_tier: str = ""
    confidence_score: float = 0.0
    fraud_probability: float = 0.0
    expected_fraud_value: float = 0.0
    data_completeness: float = 0.0
    complexity_estimate: str = "medium"  # low, medium, high
    priority_score: float = 0.0
    recommended_action: str = ""
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _expected_value(amount: float, probability: float) -> float:
    """Expected fraud value = contract_value * fraud_probability."""
    return amount * probability


def _data_completeness(contract: dict, score: dict) -> float:
    """Score how complete the available data is for investigation (0-1).

    Higher = more data available = easier to investigate.
    """
    checks = [
        contract.get("vendor_name") not in (None, "", "UNKNOWN"),
        contract.get("agency_name") not in (None, "", "UNKNOWN"),
        contract.get("award_amount", 0) > 0,
        contract.get("description") not in (None, ""),
        contract.get("start_date") is not None,
        score.get("comparable_count", 0) >= 10,
        score.get("markup_ci_lower") is not None,
        score.get("bayesian_posterior") is not None,
        score.get("fdr_adjusted_pvalue") is not None,
        score.get("bootstrap_percentile") is not None,
    ]
    return sum(checks) / len(checks)


def _complexity_estimate(contract: dict, score: dict) -> str:
    """Estimate investigation complexity based on contract characteristics.

    Returns: "low", "medium", or "high"
    """
    amount = contract.get("award_amount", 0)
    comparables = score.get("comparable_count", 0)

    # High complexity: large contracts, few comparables, or defense
    if amount > 50_000_000 or comparables < 5:
        return "high"

    agency = (contract.get("agency_name") or "").upper()
    is_defense = any(
        kw in agency for kw in ("DEFENSE", "DOD", "ARMY", "NAVY", "AIR FORCE")
    )
    if is_defense and amount > 10_000_000:
        return "high"

    if amount < 1_000_000 and comparables >= 20:
        return "low"

    return "medium"


COMPLEXITY_MULTIPLIER = {"low": 1.2, "medium": 1.0, "high": 0.8}

ACTIONS = {
    "RED": {
        "high": "Escalate to senior investigator. Recommend subpoena of vendor cost records.",
        "medium": "Assign to investigator. Conduct invoice-level audit and vendor cost analysis.",
        "low": "Desk review with automated comparison against independent cost estimates.",
    },
    "YELLOW": {
        "high": "Queue for experienced analyst. Gather additional pricing data before full review.",
        "medium": "Standard desk review. Compare pricing against peer group and recent benchmarks.",
        "low": "Automated screening report. Flag for batch review in next audit cycle.",
    },
}


# ---------------------------------------------------------------------------
# Prioritization engine
# ---------------------------------------------------------------------------

def prioritize(items: list) -> list:
    """Sort triage items by priority_score descending.

    Priority = expected_fraud_value * data_completeness * complexity_multiplier

    Items with higher expected value, better data, and lower complexity
    are prioritized (higher bang-for-buck investigations).
    """
    for item in items:
        complexity_mult = COMPLEXITY_MULTIPLIER.get(item.complexity_estimate, 1.0)
        raw_score = item.expected_fraud_value * item.data_completeness * complexity_mult
        # Log-scale to prevent mega-contracts from completely dominating
        item.priority_score = round(math.log1p(raw_score) * 10, 2)

        # Assign recommended action
        tier_actions = ACTIONS.get(item.fraud_tier, ACTIONS["YELLOW"])
        item.recommended_action = tier_actions.get(
            item.complexity_estimate,
            "Standard review — assess pricing against peer group.",
        )

    items.sort(key=lambda x: x.priority_score, reverse=True)
    for i, item in enumerate(items):
        item.rank = i + 1

    return items


def build_triage_queue(
    db_path: str,
    run_id: Optional[str] = None,
    tiers: Optional[list] = None,
) -> list:
    """Build a prioritized triage queue from the database.

    Args:
        db_path: Path to SQLite database.
        run_id: Analysis run ID. If None, uses latest completed run.
        tiers: Which tiers to include. Default: ["RED", "YELLOW"].

    Returns:
        List of TriageItem sorted by priority_score descending.
    """
    if tiers is None:
        tiers = ["RED", "YELLOW"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if run_id is None:
        c.execute(
            "SELECT run_id FROM analysis_runs WHERE status = 'COMPLETED' ORDER BY completed_at DESC LIMIT 1"
        )
        run_row = c.fetchone()
        if not run_row:
            conn.close()
            return []
        run_id = run_row["run_id"]

    placeholders = ",".join("?" for _ in tiers)
    c.execute(
        f"""
        SELECT cs.*, ct.vendor_name, ct.agency_name, ct.award_amount,
               ct.description, ct.start_date
        FROM contract_scores cs
        JOIN contracts ct ON cs.contract_id = ct.contract_id
        WHERE cs.run_id = ? AND cs.fraud_tier IN ({placeholders})
        ORDER BY cs.triage_priority ASC
        """,
        [run_id] + tiers,
    )

    items = []
    for row in c.fetchall():
        row_dict = dict(row)
        contract = {
            "vendor_name": row_dict.get("vendor_name"),
            "agency_name": row_dict.get("agency_name"),
            "award_amount": row_dict.get("award_amount", 0),
            "description": row_dict.get("description"),
            "start_date": row_dict.get("start_date"),
        }

        posterior = row_dict.get("bayesian_posterior", 0) or 0
        amount = row_dict.get("award_amount", 0) or 0

        item = TriageItem(
            contract_id=row_dict["contract_id"],
            vendor_name=row_dict.get("vendor_name", ""),
            agency_name=row_dict.get("agency_name", ""),
            award_amount=amount,
            fraud_tier=row_dict.get("fraud_tier", ""),
            confidence_score=row_dict.get("confidence_score", 0) or 0,
            fraud_probability=posterior,
            expected_fraud_value=_expected_value(amount, posterior),
            data_completeness=_data_completeness(contract, row_dict),
            complexity_estimate=_complexity_estimate(contract, row_dict),
        )
        items.append(item)

    conn.close()
    return prioritize(items)


def triage_from_list(flagged_contracts: list) -> list:
    """Prioritize a pre-built list of flagged contract dicts.

    Each dict should have:
        contract_id, vendor_name, agency_name, award_amount,
        fraud_tier, confidence_score, bayesian_posterior,
        comparable_count, markup_ci_lower, description, start_date

    Returns:
        List of TriageItem sorted by priority.
    """
    items = []
    for fc in flagged_contracts:
        posterior = fc.get("bayesian_posterior", 0) or 0
        amount = fc.get("award_amount", 0) or 0
        score_fields = {
            "comparable_count": fc.get("comparable_count", 0),
            "markup_ci_lower": fc.get("markup_ci_lower"),
            "bayesian_posterior": posterior,
            "fdr_adjusted_pvalue": fc.get("fdr_adjusted_pvalue"),
            "bootstrap_percentile": fc.get("bootstrap_percentile"),
        }

        item = TriageItem(
            contract_id=fc["contract_id"],
            vendor_name=fc.get("vendor_name", ""),
            agency_name=fc.get("agency_name", ""),
            award_amount=amount,
            fraud_tier=fc.get("fraud_tier", ""),
            confidence_score=fc.get("confidence_score", 0) or 0,
            fraud_probability=posterior,
            expected_fraud_value=_expected_value(amount, posterior),
            data_completeness=_data_completeness(fc, score_fields),
            complexity_estimate=_complexity_estimate(fc, score_fields),
        )
        items.append(item)

    return prioritize(items)
