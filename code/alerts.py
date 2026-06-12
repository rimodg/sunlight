"""
SUNLIGHT Intelligence Alert System — Core Data Structures
============================================================

Intelligence alert mechanism for procurement and delivery integrity findings.
Converts pipeline verdicts into actionable, traceable intelligence alerts
with deterministic summaries and cross-contract pattern detection.

Key distinction: This is NOT a notification system. Each alert is a complete
intelligence package — contract identity, verdict, confidence, every rule
that fired with its legal basis and evidence, recommended action, and a
direct link to the full case packet.

Architecture:
    - AlertPriority: Tiered priority from pipeline verdicts
    - RuleCitation: Per-rule evidence package
    - IntelligenceAlert: Single contract intelligence alert
    - AlertPattern: Cross-contract pattern detection
    - TriageBrief: Structured batch intelligence package

    All summaries are deterministic templates. No AI text generation.
    Every word traces to a data point.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# ═══════════════════════════════════════════════════════════


class AlertPriority(Enum):
    """
    Tiered alert priority derived from pipeline verdicts.

    CRITICAL — RED verdict + high confidence + 3+ dimensions,
               OR procurement RED + delivery RED combined
    HIGH     — RED verdict + moderate confidence + 2+ dimensions,
               OR delivery-only RED
    ELEVATED — YELLOW verdict + confidence >= 60%,
               OR delivery-only YELLOW
    ADVISORY — YELLOW verdict + confidence < 60%
    """
    CRITICAL = "critical"
    HIGH = "high"
    ELEVATED = "elevated"
    ADVISORY = "advisory"


# ═══════════════════════════════════════════════════════════
# SECTION 2: DATA STRUCTURES
# ═══════════════════════════════════════════════════════════


@dataclass
class RuleCitation:
    """
    A single rule that fired, with full evidence context.

    Every field traces to a specific data point from the pipeline:
    rule_id and layer from the rule definition, evidence and confidence
    from the rule evaluation, legal_basis from the jurisdiction profile,
    recommendation from the rule's description.
    """
    rule_id: str
    rule_name: str
    layer: str
    confidence: float
    legal_basis: str
    evidence: str
    recommendation: str


@dataclass
class IntelligenceAlert:
    """
    Complete intelligence alert for a single contract.

    Not a notification. An intelligence package. The recipient reads it
    and knows: what contract, what is wrong, which rules fired, what law
    applies, how confident the finding is, what to do next, and where to
    see the full analysis.
    """
    # Identity
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    alert_type: str = ""  # "procurement", "delivery", "combined"

    # Contract reference
    contract_id: str = ""
    contract_title: str = ""
    vendor: str = ""
    agency: str = ""
    contract_value: float = 0.0
    currency: str = "USD"
    award_date: str = ""

    # Verdict
    verdict: str = ""  # "red" or "yellow" (green does not alert)
    confidence: float = 0.0
    priority: Optional[AlertPriority] = None

    # Jurisdiction
    jurisdiction_profile: str = ""
    country_code: str = ""

    # Intelligence
    dimensions_fired: int = 0
    dimensions_required: int = 2  # from EVG methodology
    typologies: List[str] = field(default_factory=list)

    # Rule citations
    rule_citations: List[RuleCitation] = field(default_factory=list)

    # Actionable
    summary: str = ""
    recommended_action: str = ""
    case_packet_url: str = ""

    # Delivery (if Side 2 data exists)
    delivery_verdict: Optional[str] = None
    delivery_dimensions_fired: Optional[int] = None
    delivery_rule_citations: Optional[List[RuleCitation]] = None


# ═══════════════════════════════════════════════════════════
# SECTION 3: PRIORITY COMPUTATION
# ═══════════════════════════════════════════════════════════


def compute_priority(
    verdict: str,
    confidence: float,
    dimensions_fired: int,
    delivery_verdict: Optional[str] = None,
) -> Optional[AlertPriority]:
    """
    Compute alert priority from pipeline verdicts.

    Returns None for GREEN verdicts (no alert generated).

    Priority tiers:
        CRITICAL — RED + confidence >= 85% + 3+ dims,
                   OR procurement RED + delivery RED
        HIGH     — RED + confidence >= 70% + 2+ dims,
                   OR delivery-only RED (procurement GREEN)
        ELEVATED — YELLOW + confidence >= 60%,
                   OR delivery-only YELLOW
        ADVISORY — YELLOW + confidence < 60%

    Args:
        verdict: Procurement EVG verdict ("green", "yellow", "red").
        confidence: Structural confidence (0.0-1.0).
        dimensions_fired: Number of EVG dimensions that fired.
        delivery_verdict: Delivery EVG verdict, if available.

    Returns:
        AlertPriority or None if no alert warranted.
    """
    v = verdict.lower() if verdict else ""
    dv = delivery_verdict.lower() if delivery_verdict else ""

    # GREEN procurement + GREEN/absent delivery → no alert
    if v == "green" and dv in ("", "green"):
        return None

    # Combined procurement RED + delivery RED → always CRITICAL
    if v == "red" and dv == "red":
        return AlertPriority.CRITICAL

    # Procurement RED
    if v == "red":
        if confidence >= 0.85 and dimensions_fired >= 3:
            return AlertPriority.CRITICAL
        if confidence >= 0.70 and dimensions_fired >= 2:
            return AlertPriority.HIGH
        return AlertPriority.ELEVATED

    # Procurement YELLOW
    if v == "yellow":
        if confidence >= 0.60:
            return AlertPriority.ELEVATED
        return AlertPriority.ADVISORY

    # Delivery-only alerts (procurement GREEN, delivery RED/YELLOW)
    if dv == "red":
        return AlertPriority.HIGH
    if dv == "yellow":
        return AlertPriority.ELEVATED

    return None


# ═══════════════════════════════════════════════════════════
# SECTION 4: SUMMARY ASSEMBLY
# ═══════════════════════════════════════════════════════════


def assemble_summary(alert: IntelligenceAlert) -> str:
    """
    Build a deterministic intelligence summary from alert data.

    Every word traces to a data point. No interpretation.
    No adjectives. No opinion.

    Template:
        "Contract {contract_id} ({contract_title}), {vendor},
         {value} {currency}, awarded {date}, assessed at {verdict}
         ({confidence}% confidence) under {profile} jurisdiction profile.
         {N} independent structural contradictions corroborate:
         {rule citations}. EVG gate confirms multi-dimensional
         corroboration: {dims_fired} dimensions fired against
         {dims_required} required. Recommended priority: {priority}."

    Args:
        alert: IntelligenceAlert with all fields populated.

    Returns:
        Deterministic summary string.
    """
    # Rule citation list
    citations = "; ".join(
        f"{rc.rule_id} ({rc.rule_name}, {rc.legal_basis}, "
        f"{rc.confidence * 100:.0f}% confidence)"
        for rc in alert.rule_citations
    )
    if not citations:
        citations = "no specific rule citations available"

    # Title portion
    title_part = alert.contract_title or alert.contract_id
    vendor_part = f", {alert.vendor}" if alert.vendor else ""
    value_part = f", {alert.contract_value:,.2f} {alert.currency}" if alert.contract_value else ""
    date_part = f", awarded {alert.award_date}" if alert.award_date else ""

    summary = (
        f"Contract {alert.contract_id} ({title_part}){vendor_part}"
        f"{value_part}{date_part}, "
        f"assessed at {alert.verdict.upper()} "
        f"({alert.confidence * 100:.0f}% confidence) "
        f"under {alert.jurisdiction_profile} jurisdiction profile. "
        f"{len(alert.rule_citations)} independent structural contradictions "
        f"corroborate: {citations}. "
        f"EVG gate confirms multi-dimensional corroboration: "
        f"{alert.dimensions_fired} dimensions fired against "
        f"{alert.dimensions_required} required. "
        f"Recommended priority: {alert.priority.value if alert.priority else 'none'}."
    )

    # Delivery appendix
    if alert.delivery_verdict and alert.delivery_verdict.lower() != "green":
        delivery_citations = ""
        if alert.delivery_rule_citations:
            delivery_citations = "; ".join(
                f"{rc.rule_id} ({rc.rule_name}, {rc.confidence * 100:.0f}% confidence)"
                for rc in alert.delivery_rule_citations
            )
        summary += (
            f" Delivery verification: {alert.delivery_verdict.upper()} "
            f"({alert.delivery_dimensions_fired or 0} delivery dimensions fired). "
        )
        if delivery_citations:
            summary += f"Delivery findings: {delivery_citations}."

    return summary


def assemble_recommended_action(alert: IntelligenceAlert) -> str:
    """
    Build a deterministic recommended action from alert priority.

    Args:
        alert: IntelligenceAlert with priority set.

    Returns:
        Recommended action string.
    """
    if alert.priority == AlertPriority.CRITICAL:
        return (
            f"Immediate review required. Contract {alert.contract_id} "
            f"shows corroborated structural contradictions across multiple "
            f"dimensions. Assign senior analyst for full case packet review."
        )
    if alert.priority == AlertPriority.HIGH:
        return (
            f"Priority review recommended. Contract {alert.contract_id} "
            f"shows structural contradictions warranting detailed examination. "
            f"Schedule case packet review within current review cycle."
        )
    if alert.priority == AlertPriority.ELEVATED:
        return (
            f"Elevated attention. Contract {alert.contract_id} "
            f"shows structural indicators warranting monitoring. "
            f"Include in next batch review cycle."
        )
    # ADVISORY
    return (
        f"Advisory note. Contract {alert.contract_id} "
        f"shows minor structural indicators. "
        f"Log for trend analysis."
    )


# ═══════════════════════════════════════════════════════════
# SECTION 5: TRIAGE AND AGGREGATION
# ═══════════════════════════════════════════════════════════


@dataclass
class AlertPattern:
    """
    Cross-contract intelligence insight detected across multiple alerts.

    Pattern types:
        vendor_clustering      — Same vendor in 3+ alerts
        temporal_clustering    — Multiple awards within 14-day window
        rule_concentration     — Same rule fires across 5+ contracts
        pillar_concentration   — 2/3+ of alerts in one development sector
        geographic_concentration — Alerts clustered in one office/region
        financial_escalation   — Progressive price deviation for same vendor
    """
    pattern_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pattern_type: str = ""
    description: str = ""
    severity: str = "MEDIUM"  # HIGH / MEDIUM / LOW
    affected_contracts: List[str] = field(default_factory=list)
    affected_rules: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TriageBrief:
    """
    Structured intelligence package for batch results.

    One brief per batch, not one alert per contract.
    30 independent red lights is noise. One brief that says
    "30 findings, 2 critical, here is the pattern, here is where
    to start" is intelligence.
    """
    brief_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    batch_id: Optional[str] = None
    jurisdiction_profile: str = ""
    country_office: Optional[str] = None

    # Aggregate statistics
    total_contracts_analyzed: int = 0
    total_alerts: int = 0
    alerts_by_priority: Dict[str, int] = field(default_factory=dict)
    alerts_by_dimension: Dict[str, int] = field(default_factory=dict)

    # Ranked alert queue — most urgent first
    ranked_alerts: List[IntelligenceAlert] = field(default_factory=list)

    # Cross-contract pattern detection
    patterns: List[AlertPattern] = field(default_factory=list)

    # Executive summary — deterministic
    executive_summary: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 6: RANKING
# ═══════════════════════════════════════════════════════════


# Priority ordering for sort (lower number = higher priority)
_PRIORITY_ORDER = {
    AlertPriority.CRITICAL: 0,
    AlertPriority.HIGH: 1,
    AlertPriority.ELEVATED: 2,
    AlertPriority.ADVISORY: 3,
}


def rank_alerts(alerts: List[IntelligenceAlert]) -> List[IntelligenceAlert]:
    """
    Rank alerts from most urgent to least.

    Sort order:
        1. Priority (CRITICAL first, ADVISORY last)
        2. Confidence descending (within same priority)
        3. Contract value descending (within same confidence)
        4. Dimensions fired descending (within same value)

    Args:
        alerts: List of IntelligenceAlert objects.

    Returns:
        New list sorted by urgency.
    """
    return sorted(
        alerts,
        key=lambda a: (
            _PRIORITY_ORDER.get(a.priority, 99),
            -a.confidence,
            -a.contract_value,
            -a.dimensions_fired,
        ),
    )


# ═══════════════════════════════════════════════════════════
# SECTION 7: PATTERN DETECTION
# ═══════════════════════════════════════════════════════════


def detect_vendor_clustering(
    alerts: List[IntelligenceAlert],
    min_count: int = 3,
) -> List[AlertPattern]:
    """
    Detect when the same vendor appears in multiple alerts.

    Args:
        alerts: List of alerts to scan.
        min_count: Minimum alerts per vendor to trigger pattern.

    Returns:
        List of AlertPattern objects for vendor clustering.
    """
    vendor_map: Dict[str, List[str]] = {}
    for a in alerts:
        if a.vendor:
            vendor_map.setdefault(a.vendor, []).append(a.contract_id)

    patterns = []
    for vendor, contracts in vendor_map.items():
        if len(contracts) >= min_count:
            patterns.append(AlertPattern(
                pattern_type="vendor_clustering",
                description=(
                    f"Vendor '{vendor}' appears in {len(contracts)} flagged "
                    f"contracts, indicating systemic vendor risk."
                ),
                severity="HIGH",
                affected_contracts=contracts,
                detail={"vendor": vendor, "count": len(contracts)},
            ))
    return patterns


def detect_rule_concentration(
    alerts: List[IntelligenceAlert],
    min_count: int = 5,
) -> List[AlertPattern]:
    """
    Detect when the same rule fires across many contracts.

    Indicates systemic procedural failure at the office level,
    not individual contract anomalies.

    Args:
        alerts: List of alerts to scan.
        min_count: Minimum contracts per rule to trigger pattern.

    Returns:
        List of AlertPattern objects for rule concentration.
    """
    rule_map: Dict[str, List[str]] = {}
    for a in alerts:
        for rc in a.rule_citations:
            rule_map.setdefault(rc.rule_id, []).append(a.contract_id)

    patterns = []
    for rule_id, contracts in rule_map.items():
        unique_contracts = list(dict.fromkeys(contracts))  # preserve order, dedupe
        if len(unique_contracts) >= min_count:
            patterns.append(AlertPattern(
                pattern_type="rule_concentration",
                description=(
                    f"Rule {rule_id} fires across {len(unique_contracts)} "
                    f"contracts, indicating systemic procedural failure."
                ),
                severity="HIGH",
                affected_contracts=unique_contracts,
                affected_rules=[rule_id],
                detail={"rule_id": rule_id, "count": len(unique_contracts)},
            ))
    return patterns


def detect_temporal_clustering(
    alerts: List[IntelligenceAlert],
    window_days: int = 14,
    min_count: int = 3,
) -> List[AlertPattern]:
    """
    Detect multiple flagged contracts awarded within a narrow window.

    Indicates budget-pressure-driven procurement.

    Args:
        alerts: List of alerts to scan.
        window_days: Maximum days between awards to form a cluster.
        min_count: Minimum alerts in window to trigger pattern.

    Returns:
        List of AlertPattern objects for temporal clustering.
    """
    # Parse award dates
    dated_alerts: List[tuple] = []
    for a in alerts:
        if a.award_date:
            try:
                dt = datetime.fromisoformat(
                    a.award_date.replace("Z", "+00:00")
                )
                dated_alerts.append((dt, a))
            except (ValueError, TypeError):
                pass

    if len(dated_alerts) < min_count:
        return []

    # Sort by date
    dated_alerts.sort(key=lambda x: x[0])

    # Sliding window
    patterns = []
    seen_clusters: set = set()

    for i in range(len(dated_alerts)):
        cluster_contracts = [dated_alerts[i][1].contract_id]
        for j in range(i + 1, len(dated_alerts)):
            delta = (dated_alerts[j][0] - dated_alerts[i][0]).days
            if delta <= window_days:
                cluster_contracts.append(dated_alerts[j][1].contract_id)
            else:
                break

        if len(cluster_contracts) >= min_count:
            # Deduplicate clusters by frozenset of contracts
            cluster_key = frozenset(cluster_contracts)
            if cluster_key not in seen_clusters:
                seen_clusters.add(cluster_key)
                start_date = dated_alerts[i][0].strftime("%Y-%m-%d")
                patterns.append(AlertPattern(
                    pattern_type="temporal_clustering",
                    description=(
                        f"{len(cluster_contracts)} flagged contracts awarded "
                        f"within {window_days}-day window starting {start_date}, "
                        f"indicating budget-pressure-driven procurement."
                    ),
                    severity="MEDIUM",
                    affected_contracts=cluster_contracts,
                    detail={
                        "window_days": window_days,
                        "start_date": start_date,
                        "count": len(cluster_contracts),
                    },
                ))
    return patterns


def detect_patterns(alerts: List[IntelligenceAlert]) -> List[AlertPattern]:
    """
    Run all pattern detectors on a list of alerts.

    Args:
        alerts: List of alerts from a batch.

    Returns:
        Combined list of all detected patterns.
    """
    patterns: List[AlertPattern] = []
    patterns.extend(detect_vendor_clustering(alerts))
    patterns.extend(detect_rule_concentration(alerts))
    patterns.extend(detect_temporal_clustering(alerts))
    return patterns


# ═══════════════════════════════════════════════════════════
# SECTION 8: TRIAGE BRIEF ASSEMBLY
# ═══════════════════════════════════════════════════════════


def assemble_triage_brief(
    alerts: List[IntelligenceAlert],
    batch_id: Optional[str] = None,
    total_contracts: int = 0,
    jurisdiction_profile: str = "",
    country_office: Optional[str] = None,
) -> TriageBrief:
    """
    Assemble a TriageBrief from a list of alerts.

    Ranks alerts, detects patterns, and builds an executive summary.

    Args:
        alerts: List of IntelligenceAlert objects.
        batch_id: Optional batch identifier.
        total_contracts: Total contracts in the batch (including non-alerting).
        jurisdiction_profile: Profile used for the batch.
        country_office: Optional country office identifier.

    Returns:
        TriageBrief with ranked alerts, patterns, and executive summary.
    """
    ranked = rank_alerts(alerts)
    patterns = detect_patterns(alerts)

    # Priority distribution
    priority_counts: Dict[str, int] = {
        "critical": 0, "high": 0, "elevated": 0, "advisory": 0,
    }
    for a in alerts:
        if a.priority:
            priority_counts[a.priority.value] = (
                priority_counts.get(a.priority.value, 0) + 1
            )

    # Dimension distribution (from typologies)
    dim_counts: Dict[str, int] = {}
    for a in alerts:
        for t in a.typologies:
            dim_counts[t] = dim_counts.get(t, 0) + 1

    # Executive summary
    executive_summary = assemble_executive_summary(
        batch_id=batch_id,
        total_contracts=total_contracts,
        total_alerts=len(alerts),
        priority_counts=priority_counts,
        patterns=patterns,
        top_alert=ranked[0] if ranked else None,
        jurisdiction_profile=jurisdiction_profile,
    )

    return TriageBrief(
        batch_id=batch_id,
        jurisdiction_profile=jurisdiction_profile,
        country_office=country_office,
        total_contracts_analyzed=total_contracts,
        total_alerts=len(alerts),
        alerts_by_priority=priority_counts,
        alerts_by_dimension=dim_counts,
        ranked_alerts=ranked,
        patterns=patterns,
        executive_summary=executive_summary,
    )


def assemble_executive_summary(
    batch_id: Optional[str],
    total_contracts: int,
    total_alerts: int,
    priority_counts: Dict[str, int],
    patterns: List[AlertPattern],
    top_alert: Optional[IntelligenceAlert],
    jurisdiction_profile: str,
) -> str:
    """
    Build a deterministic executive summary for a triage brief.

    Template:
        "Batch {batch_id}: {total_contracts} contracts analyzed under
         {profile} profile. {total_alerts} structural findings identified:
         {critical} critical, {high} high, {elevated} elevated,
         {advisory} advisory. {pattern descriptions if any}.
         Highest-priority finding: {top alert details}.
         {top alert recommended_action}."

    Args:
        All the data points needed to fill the template.

    Returns:
        Deterministic executive summary string.
    """
    batch_label = f"Batch {batch_id}" if batch_id else "Batch analysis"

    summary = (
        f"{batch_label}: {total_contracts} contracts analyzed "
        f"under {jurisdiction_profile} profile. "
        f"{total_alerts} structural findings identified: "
        f"{priority_counts.get('critical', 0)} critical, "
        f"{priority_counts.get('high', 0)} high, "
        f"{priority_counts.get('elevated', 0)} elevated, "
        f"{priority_counts.get('advisory', 0)} advisory."
    )

    if patterns:
        pattern_desc = "; ".join(p.description for p in patterns)
        summary += f" {len(patterns)} cross-contract patterns detected: {pattern_desc}."

    if top_alert:
        summary += (
            f" Highest-priority finding: {top_alert.contract_id}"
        )
        if top_alert.vendor:
            summary += f", {top_alert.vendor}"
        if top_alert.contract_value:
            summary += f", {top_alert.contract_value:,.2f} {top_alert.currency}"
        summary += (
            f", {top_alert.verdict.upper()} at "
            f"{top_alert.confidence * 100:.0f}% confidence "
            f"({top_alert.dimensions_fired} corroborating dimensions). "
            f"{top_alert.recommended_action}"
        )

    return summary
