"""
Process Indicators — procedural red flag detector.

Analyzes the procurement *process* (not just the contract price):
  - Time between announcement and deadline (too short = red flag)
  - Number of bidders over time trend
  - Amendment frequency post-award
  - Whether technical specs appear tailored to a specific vendor (keyword fingerprinting)
"""

import re
import math
import sqlite3
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ProcessRedFlag:
    """A single procedural red flag."""

    indicator: str
    severity: str  # "low", "medium", "high", "critical"
    score: float  # 0-100
    description: str
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProcessAnalysis:
    """Complete process analysis for a contract or procurement."""

    contract_id: str
    red_flags: list = field(default_factory=list)
    composite_score: float = 0.0  # 0-100, higher = more suspicious
    flag_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Indicator 1: Compressed timeline
# ---------------------------------------------------------------------------

MINIMUM_REASONABLE_DAYS = {
    "goods": 15,
    "services": 21,
    "works": 30,
    "consulting": 30,
    "default": 21,
}


def check_compressed_timeline(
    announcement_date: Optional[str],
    deadline_date: Optional[str],
    procurement_type: str = "default",
) -> Optional[ProcessRedFlag]:
    """Flag procurements with unreasonably short bidding windows.

    International best practice (WTO GPA): 40 days minimum for open tenders.
    Reduced timelines may indicate an attempt to limit competition.
    """
    if not announcement_date or not deadline_date:
        return None

    try:
        announce = datetime.fromisoformat(announcement_date)
        deadline = datetime.fromisoformat(deadline_date)
    except (ValueError, TypeError):
        return None

    days = (deadline - announce).days
    if days < 0:
        return ProcessRedFlag(
            indicator="invalid_timeline",
            severity="critical",
            score=100.0,
            description=f"Deadline ({deadline_date}) is before announcement ({announcement_date})",
            evidence={"days": days},
        )

    min_days = MINIMUM_REASONABLE_DAYS.get(procurement_type, MINIMUM_REASONABLE_DAYS["default"])
    if days >= min_days:
        return None

    # Score: 0 at min_days, 100 at 0 days
    score = max(0, (1 - days / min_days)) * 100
    severity = "critical" if days <= 3 else "high" if days <= 7 else "medium"

    return ProcessRedFlag(
        indicator="compressed_timeline",
        severity=severity,
        score=round(score, 1),
        description=(
            f"Only {days} day(s) between announcement and deadline "
            f"(minimum recommended: {min_days} for {procurement_type})"
        ),
        evidence={
            "days": days,
            "minimum_recommended": min_days,
            "procurement_type": procurement_type,
        },
    )


# ---------------------------------------------------------------------------
# Indicator 2: Declining bidder count trend
# ---------------------------------------------------------------------------

def check_bidder_trend(
    bidder_counts: list,
    min_history: int = 3,
) -> Optional[ProcessRedFlag]:
    """Flag agencies/categories with declining bidder counts over time.

    A downward trend in the number of bidders may indicate market manipulation
    or barriers to entry.

    Args:
        bidder_counts: List of (period, count) tuples in chronological order,
                       e.g. [("2023-Q1", 8), ("2023-Q2", 6), ("2024-Q1", 3)].
        min_history: Minimum data points required.
    """
    if len(bidder_counts) < min_history:
        return None

    counts = [c[1] for c in bidder_counts]
    n = len(counts)

    # Linear regression slope
    x_mean = (n - 1) / 2
    y_mean = sum(counts) / n
    numerator = sum((i - x_mean) * (counts[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return None

    slope = numerator / denominator

    # Only flag declining trends
    if slope >= 0:
        return None

    # Severity based on decline rate
    decline_pct = abs(slope) / max(y_mean, 1) * 100
    if decline_pct < 10:
        return None

    severity = "high" if decline_pct > 30 else "medium"
    score = min(decline_pct * 2, 100)

    return ProcessRedFlag(
        indicator="declining_bidders",
        severity=severity,
        score=round(score, 1),
        description=(
            f"Bidder count declining at {decline_pct:.0f}% per period "
            f"(from {counts[0]} to {counts[-1]} over {n} periods)"
        ),
        evidence={
            "slope": round(slope, 3),
            "decline_pct": round(decline_pct, 1),
            "first_count": counts[0],
            "last_count": counts[-1],
            "periods": n,
        },
    )


# ---------------------------------------------------------------------------
# Indicator 3: Post-award amendment frequency
# ---------------------------------------------------------------------------

def check_amendment_frequency(
    original_amount: float,
    amendments: list,
    threshold_count: int = 3,
    threshold_value_pct: float = 25.0,
) -> Optional[ProcessRedFlag]:
    """Flag contracts with excessive post-award modifications.

    Frequent or large amendments may indicate:
      - Low-ball bid followed by change orders
      - Scope creep enabling price escalation
      - Collusion between contractor and contracting officer

    Args:
        original_amount: Original contract value.
        amendments: List of dicts with {"amount_change": float, "date": str, "description": str}.
        threshold_count: Number of amendments that triggers concern.
        threshold_value_pct: Cumulative value change (%) that triggers concern.
    """
    if not amendments:
        return None

    total_change = sum(a.get("amount_change", 0) for a in amendments)
    if original_amount <= 0:
        return None

    change_pct = (total_change / original_amount) * 100
    count = len(amendments)

    flags = []
    if count >= threshold_count:
        flags.append(f"{count} amendments (threshold: {threshold_count})")
    if abs(change_pct) >= threshold_value_pct:
        flags.append(f"{change_pct:+.1f}% value change (threshold: {threshold_value_pct}%)")

    if not flags:
        return None

    severity = "high" if (count >= threshold_count * 2 or abs(change_pct) >= 50) else "medium"
    score = min(
        (count / threshold_count * 30) + (abs(change_pct) / threshold_value_pct * 30),
        100,
    )

    return ProcessRedFlag(
        indicator="excessive_amendments",
        severity=severity,
        score=round(score, 1),
        description=f"Post-award modification concerns: {'; '.join(flags)}",
        evidence={
            "amendment_count": count,
            "total_change": total_change,
            "change_pct": round(change_pct, 1),
            "original_amount": original_amount,
        },
    )


# ---------------------------------------------------------------------------
# Indicator 4: Tailored specifications (keyword fingerprinting)
# ---------------------------------------------------------------------------

# Patterns that suggest specs were written for a specific vendor
TAILORING_PATTERNS = [
    (r"\b[A-Z][a-z]+(?:Corp|Inc|LLC|Ltd|GmbH|SA)\b", "company_name_in_spec"),
    (r"\bmodel\s+[A-Z0-9]{3,}\b", "specific_model_number"),
    (r"\bpart\s*(?:number|no\.?|#)\s*[A-Z0-9\-]{5,}\b", "specific_part_number"),
    (r"\bpatent(?:ed)?\s*(?:number|no\.?|#)?\s*\d+", "patent_reference"),
    (r"\bproprietary\b", "proprietary_requirement"),
    (r"\bsole\s*source\b", "sole_source_language"),
    (r"\bonly\s+(?:available|manufactured|produced)\s+by\b", "exclusivity_language"),
    (r"\bcompatible\s+(?:only\s+)?with\s+[A-Z]", "compatibility_restriction"),
]


def check_tailored_specs(
    specification_text: str,
    vendor_name: Optional[str] = None,
) -> Optional[ProcessRedFlag]:
    """Detect whether technical specifications appear tailored to a specific vendor.

    Uses keyword fingerprinting to identify language patterns that restrict
    competition to a particular supplier.

    Args:
        specification_text: The technical specification or SOW text.
        vendor_name: If provided, also checks for the vendor's name in the spec.
    """
    if not specification_text or len(specification_text) < 20:
        return None

    text = specification_text
    matches = []

    for pattern, indicator_type in TAILORING_PATTERNS:
        found = re.findall(pattern, text, re.IGNORECASE)
        if found:
            matches.append({
                "type": indicator_type,
                "matches": found[:5],  # limit to first 5
                "count": len(found),
            })

    # Check for vendor name in spec
    if vendor_name and len(vendor_name) > 3:
        vendor_pattern = re.escape(vendor_name)
        vendor_matches = re.findall(vendor_pattern, text, re.IGNORECASE)
        if vendor_matches:
            matches.append({
                "type": "vendor_name_in_spec",
                "matches": vendor_matches[:3],
                "count": len(vendor_matches),
            })

    if not matches:
        return None

    total_indicators = sum(m["count"] for m in matches)
    unique_types = len(matches)
    score = min(unique_types * 20 + total_indicators * 5, 100)
    severity = "high" if score > 60 else "medium" if score > 30 else "low"

    return ProcessRedFlag(
        indicator="tailored_specifications",
        severity=severity,
        score=round(score, 1),
        description=(
            f"Specification contains {unique_types} type(s) of restrictive language "
            f"({total_indicators} total instances)"
        ),
        evidence={
            "indicator_types": [m["type"] for m in matches],
            "total_instances": total_indicators,
            "details": matches,
        },
    )


# ---------------------------------------------------------------------------
# Composite analysis
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}


def analyze_process(
    contract_id: str,
    announcement_date: Optional[str] = None,
    deadline_date: Optional[str] = None,
    procurement_type: str = "default",
    bidder_counts: Optional[list] = None,
    original_amount: float = 0,
    amendments: Optional[list] = None,
    specification_text: str = "",
    vendor_name: Optional[str] = None,
) -> ProcessAnalysis:
    """Run all process indicator checks and return composite analysis.

    Returns:
        ProcessAnalysis with all detected red flags and composite score.
    """
    analysis = ProcessAnalysis(contract_id=contract_id)

    # Run each indicator
    timeline_flag = check_compressed_timeline(
        announcement_date, deadline_date, procurement_type
    )
    if timeline_flag:
        analysis.red_flags.append(timeline_flag.to_dict())

    if bidder_counts:
        bidder_flag = check_bidder_trend(bidder_counts)
        if bidder_flag:
            analysis.red_flags.append(bidder_flag.to_dict())

    if amendments:
        amendment_flag = check_amendment_frequency(original_amount, amendments)
        if amendment_flag:
            analysis.red_flags.append(amendment_flag.to_dict())

    if specification_text:
        spec_flag = check_tailored_specs(specification_text, vendor_name)
        if spec_flag:
            analysis.red_flags.append(spec_flag.to_dict())

    # Composite score
    analysis.flag_count = len(analysis.red_flags)
    if analysis.red_flags:
        weighted_sum = sum(
            f["score"] * SEVERITY_WEIGHTS.get(f["severity"], 0.5)
            for f in analysis.red_flags
        )
        max_possible = analysis.flag_count * 100
        analysis.composite_score = round(
            min(weighted_sum / max(max_possible, 1) * 100, 100), 1
        )

    return analysis
