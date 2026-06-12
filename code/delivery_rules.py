"""
SUNLIGHT Side 2 — Delivery Rule Engine
========================================

Deterministic delivery integrity verification.
Same delivery data + same rules = same result. Forever.

Architecture:
    Mirrors tca_rules.py exactly:
    - build_delivery_rules(profile) → List[DeliveryRule]
    - Closure pattern: rules close over profile at construction time
    - Each rule: CONDITION → EVIDENCE → RESULT
    - 12 rules across 4 enrichment layers

Rule Layers:
    Layer 0: Milestone Compliance (DEL-MILE-001/002/003)
        Schedule adherence — were milestones hit on time?
    Layer 1: Resource Verification (DEL-RES-001/002/003)
        Staffing integrity — were promised resources actually deployed?
    Layer 2: Outcome Verification (DEL-OUT-001/002/003)
        Deliverable integrity — was what was promised actually delivered?
    Layer 3: Financial Reconciliation (DEL-FIN-001/002/003)
        Cost integrity — does actual spend match the budget?

Each rule is:
    CONDITION → RESULT → EVIDENCE CITATION
    - Deterministic: same delivery data always triggers the same rule
    - Citeable: every rule has a legal/regulatory evidence base
    - Auditable: the rule set is version-controlled
    - Testable: each rule can be unit tested in isolation

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
Rule Set Version: DRS-2026-06-001
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from delivery_schema import (
    DeliveryDossier,
    DeliveryRuleResult,
    DeliveryRulesResult,
    DeliveryRuleLayer,
)
from jurisdiction_profile import JurisdictionProfile


# ═══════════════════════════════════════════════════════════
# SECTION 1: DELIVERY RULE DEFINITION
# ═══════════════════════════════════════════════════════════


@dataclass
class DeliveryRule:
    """
    A single delivery integrity rule.

    Each rule is a deterministic mapping from delivery data
    to a finding. When the condition fires, a DeliveryRuleResult
    is produced with evidence and legal basis.

    Mirrors tca_rules.Rule but operates on DeliveryDossier
    instead of ContractDossier.
    """
    rule_id: str                        # e.g. "DEL-MILE-001"
    layer: str                          # "milestone", "resource", "outcome", "financial"
    name: str                           # Human-readable name
    description: str                    # What this rule detects
    evidence_template: str              # Legal/regulatory citation template
    condition: Callable[[DeliveryDossier], bool]
    build_evidence: Callable[[DeliveryDossier], str]
    confidence: Callable[[DeliveryDossier], float]


# ═══════════════════════════════════════════════════════════
# SECTION 2: THRESHOLD DEFAULTS
# Used when jurisdiction profile does not supply delivery-
# specific parameters. Values are conservative (institutional
# credibility floor).
# ═══════════════════════════════════════════════════════════

# Milestone layer
DEFAULT_DELAY_TOLERANCE_DAYS = 30
DEFAULT_MILESTONE_FAILURE_RATIO = 0.5       # >50% milestones delayed = concern

# Resource layer
DEFAULT_STAFFING_GAP_TOLERANCE = 0.75       # <75% of planned FTE = concern
DEFAULT_QUALIFICATION_FAILURE_RATIO = 0.5   # >50% unverified qualifications = concern

# Outcome layer
DEFAULT_OUTCOME_SHORTFALL_THRESHOLD = 0.80  # <80% delivered vs planned = concern
DEFAULT_DEFECT_RATE_THRESHOLD = 0.20        # >20% of outcomes have defects = concern

# Financial layer
DEFAULT_COST_ESCALATION_TOLERANCE = 0.25    # >25% over budget = concern
DEFAULT_AMENDMENT_THRESHOLD = 3             # >3 amendments on a single line = concern
DEFAULT_BUDGET_CONCENTRATION_RATIO = 0.70   # >70% of variance in single line = concern


def _get_delivery_param(profile: JurisdictionProfile, param: str, default):
    """
    Safely retrieve a delivery-specific parameter from a jurisdiction profile.

    Delivery parameters are added to JurisdictionProfile in Side 2 Step 5.
    Until then, this function returns the default value. This allows
    delivery_rules.py to be tested and used before the profile schema
    is extended.
    """
    return getattr(profile, param, default)


# ═══════════════════════════════════════════════════════════
# SECTION 3: RULE BUILDER — Closure pattern
# ═══════════════════════════════════════════════════════════


def build_delivery_rules(profile: JurisdictionProfile) -> List[DeliveryRule]:
    """
    Build all 12 delivery rules with jurisdiction-specific parameters.

    Uses the same closure pattern as tca_rules.build_rules(profile):
    rules' lambdas close over the profile, binding jurisdiction
    parameters at construction time.

    Args:
        profile: JurisdictionProfile containing jurisdiction-specific constants.
                 Delivery-specific fields (delivery_delay_tolerance_days, etc.)
                 are read via _get_delivery_param with conservative defaults.

    Returns:
        List of 12 DeliveryRule objects.
    """
    rules: List[DeliveryRule] = []

    # Resolve delivery thresholds from profile (with defaults for pre-extension profiles)
    delay_tolerance = _get_delivery_param(
        profile, "delivery_delay_tolerance_days", DEFAULT_DELAY_TOLERANCE_DAYS
    )
    staffing_gap_tolerance = _get_delivery_param(
        profile, "staffing_gap_tolerance_ratio", DEFAULT_STAFFING_GAP_TOLERANCE
    )
    outcome_shortfall = _get_delivery_param(
        profile, "outcome_shortfall_threshold", DEFAULT_OUTCOME_SHORTFALL_THRESHOLD
    )
    cost_escalation = _get_delivery_param(
        profile, "cost_escalation_tolerance", DEFAULT_COST_ESCALATION_TOLERANCE
    )

    # Legal citations for delivery rules
    delivery_citations = _get_delivery_param(
        profile, "delivery_legal_citations", {}
    )
    contract_admin_cite = delivery_citations.get(
        "contract_administration",
        "UNCAC Art. 9(1) — Procurement systems based on transparency; "
        "UNDP POPP Contract and Asset Management"
    )
    financial_mgmt_cite = delivery_citations.get(
        "financial_management",
        "UNCAC Art. 9(2) — Public finance management measures; "
        "UNDP Financial Regulations and Rules"
    )
    quality_assurance_cite = delivery_citations.get(
        "quality_assurance",
        "UNDP Programme and Operations Policies and Procedures — Quality Assurance; "
        "OECD DAC Quality Standards for Development Evaluation"
    )

    # ─────────────────────────────────────────
    # LAYER 0: MILESTONE COMPLIANCE
    # ─────────────────────────────────────────

    rules.append(DeliveryRule(
        rule_id="DEL-MILE-001",
        layer="milestone",
        name="Critical milestone delay",
        description=(
            "One or more milestones exceed the jurisdiction-specific "
            "delay tolerance threshold"
        ),
        evidence_template=contract_admin_cite,
        condition=lambda d: any(
            m.delay_days > delay_tolerance
            for m in d.milestones
        ),
        build_evidence=lambda d: (
            f"{sum(1 for m in d.milestones if m.delay_days > delay_tolerance)} "
            f"milestone(s) exceed {delay_tolerance}-day delay tolerance; "
            f"worst delay: {max((m.delay_days for m in d.milestones), default=0)} days"
        ),
        confidence=lambda d: min(
            0.95,
            0.5 + 0.1 * sum(1 for m in d.milestones if m.delay_days > delay_tolerance)
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-MILE-002",
        layer="milestone",
        name="Majority milestones delayed",
        description=(
            "More than half of all milestones show delay, indicating "
            "systemic schedule failure"
        ),
        evidence_template=contract_admin_cite,
        condition=lambda d: (
            len(d.milestones) >= 2
            and d.delayed_milestones / len(d.milestones) > DEFAULT_MILESTONE_FAILURE_RATIO
        ),
        build_evidence=lambda d: (
            f"{d.delayed_milestones} of {d.total_milestones} milestones delayed "
            f"({d.delayed_milestones / d.total_milestones * 100:.0f}% > "
            f"{DEFAULT_MILESTONE_FAILURE_RATIO * 100:.0f}% threshold)"
        ),
        confidence=lambda d: min(
            0.90,
            0.4 + 0.15 * (d.delayed_milestones / max(d.total_milestones, 1))
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-MILE-003",
        layer="milestone",
        name="Deliverable acceptance gap",
        description=(
            "Milestones show accepted deliverables significantly below "
            "what was due, indicating partial or rejected delivery"
        ),
        evidence_template=contract_admin_cite,
        condition=lambda d: (
            len(d.milestones) > 0
            and sum(m.deliverables_due for m in d.milestones) > 0
            and (
                sum(m.deliverables_accepted for m in d.milestones)
                / sum(m.deliverables_due for m in d.milestones)
            ) < outcome_shortfall
        ),
        build_evidence=lambda d: (
            f"Deliverables accepted: {sum(m.deliverables_accepted for m in d.milestones)} "
            f"of {sum(m.deliverables_due for m in d.milestones)} due "
            f"({sum(m.deliverables_accepted for m in d.milestones) / sum(m.deliverables_due for m in d.milestones) * 100:.0f}% "
            f"< {outcome_shortfall * 100:.0f}% threshold)"
        ),
        confidence=lambda d: 0.75,
    ))

    # ─────────────────────────────────────────
    # LAYER 1: RESOURCE VERIFICATION
    # ─────────────────────────────────────────

    rules.append(DeliveryRule(
        rule_id="DEL-RES-001",
        layer="resource",
        name="Staffing gap below tolerance",
        description=(
            "Actual FTE deployment falls below the jurisdiction-specific "
            "staffing gap tolerance"
        ),
        evidence_template=contract_admin_cite,
        condition=lambda d: (
            len(d.resources) > 0
            and sum(r.planned_fte for r in d.resources) > 0
            and d.staffing_gap_ratio < staffing_gap_tolerance
        ),
        build_evidence=lambda d: (
            f"Staffing ratio {d.staffing_gap_ratio:.2f} "
            f"< {staffing_gap_tolerance:.2f} tolerance; "
            f"planned {sum(r.planned_fte for r in d.resources):.1f} FTE, "
            f"actual {sum(r.actual_fte for r in d.resources):.1f} FTE"
        ),
        confidence=lambda d: min(
            0.90,
            0.5 + 0.3 * (1 - d.staffing_gap_ratio)
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-RES-002",
        layer="resource",
        name="Qualification verification failure",
        description=(
            "More than half of resources with required qualifications "
            "have not been verified"
        ),
        evidence_template=quality_assurance_cite,
        condition=lambda d: (
            len(d.resources) > 0
            and sum(1 for r in d.resources if r.qualification_required) > 0
            and (
                sum(1 for r in d.resources if r.qualification_required and not r.qualification_verified)
                / sum(1 for r in d.resources if r.qualification_required)
            ) > DEFAULT_QUALIFICATION_FAILURE_RATIO
        ),
        build_evidence=lambda d: (
            f"{sum(1 for r in d.resources if r.qualification_required and not r.qualification_verified)} "
            f"of {sum(1 for r in d.resources if r.qualification_required)} "
            f"required qualifications unverified"
        ),
        confidence=lambda d: 0.80,
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-RES-003",
        layer="resource",
        name="Zero actual staffing on planned role",
        description=(
            "One or more roles with planned FTE have zero actual deployment"
        ),
        evidence_template=contract_admin_cite,
        condition=lambda d: any(
            r.planned_fte > 0 and r.actual_fte == 0
            for r in d.resources
        ),
        build_evidence=lambda d: (
            f"{sum(1 for r in d.resources if r.planned_fte > 0 and r.actual_fte == 0)} "
            f"role(s) with planned FTE have zero actual deployment: "
            + ", ".join(
                r.role for r in d.resources
                if r.planned_fte > 0 and r.actual_fte == 0
            )
        ),
        confidence=lambda d: 0.85,
    ))

    # ─────────────────────────────────────────
    # LAYER 2: OUTCOME VERIFICATION
    # ─────────────────────────────────────────

    rules.append(DeliveryRule(
        rule_id="DEL-OUT-001",
        layer="outcome",
        name="Outcome delivery shortfall",
        description=(
            "Overall quantity delivered falls below the jurisdiction-specific "
            "outcome shortfall threshold"
        ),
        evidence_template=quality_assurance_cite,
        condition=lambda d: (
            len(d.outcomes) > 0
            and sum(o.quantity_planned for o in d.outcomes) > 0
            and d.outcome_delivery_ratio < outcome_shortfall
        ),
        build_evidence=lambda d: (
            f"Delivery ratio {d.outcome_delivery_ratio:.2f} "
            f"< {outcome_shortfall:.2f} threshold; "
            f"planned {sum(o.quantity_planned for o in d.outcomes):.0f}, "
            f"delivered {sum(o.quantity_delivered for o in d.outcomes):.0f}"
        ),
        confidence=lambda d: min(
            0.90,
            0.5 + 0.3 * (1 - d.outcome_delivery_ratio)
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-OUT-002",
        layer="outcome",
        name="Excessive defect rate",
        description=(
            "More than the acceptable proportion of outcomes have defects noted"
        ),
        evidence_template=quality_assurance_cite,
        condition=lambda d: (
            len(d.outcomes) > 0
            and (
                sum(1 for o in d.outcomes if o.defects_noted > 0)
                / len(d.outcomes)
            ) > DEFAULT_DEFECT_RATE_THRESHOLD
        ),
        build_evidence=lambda d: (
            f"{sum(1 for o in d.outcomes if o.defects_noted > 0)} "
            f"of {len(d.outcomes)} outcomes have defects "
            f"({sum(1 for o in d.outcomes if o.defects_noted > 0) / len(d.outcomes) * 100:.0f}% "
            f"> {DEFAULT_DEFECT_RATE_THRESHOLD * 100:.0f}% threshold); "
            f"total defects: {sum(o.defects_noted for o in d.outcomes)}"
        ),
        confidence=lambda d: min(
            0.85,
            0.4 + 0.15 * (sum(o.defects_noted for o in d.outcomes) / max(len(d.outcomes), 1))
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-OUT-003",
        layer="outcome",
        name="Quality score below threshold",
        description=(
            "Average quality score across assessed outcomes falls below "
            "the shortfall threshold"
        ),
        evidence_template=quality_assurance_cite,
        condition=lambda d: (
            len(d.outcomes) > 0
            and any(o.quality_score is not None for o in d.outcomes)
            and (
                sum(o.quality_score for o in d.outcomes if o.quality_score is not None)
                / sum(1 for o in d.outcomes if o.quality_score is not None)
            ) < outcome_shortfall
        ),
        build_evidence=lambda d: (
            f"Average quality score "
            f"{sum(o.quality_score for o in d.outcomes if o.quality_score is not None) / sum(1 for o in d.outcomes if o.quality_score is not None):.2f} "
            f"< {outcome_shortfall:.2f} threshold"
        ),
        confidence=lambda d: 0.70,
    ))

    # ─────────────────────────────────────────
    # LAYER 3: FINANCIAL RECONCILIATION
    # ─────────────────────────────────────────

    rules.append(DeliveryRule(
        rule_id="DEL-FIN-001",
        layer="financial",
        name="Cost escalation above tolerance",
        description=(
            "Overall budget variance exceeds the jurisdiction-specific "
            "cost escalation tolerance"
        ),
        evidence_template=financial_mgmt_cite,
        condition=lambda d: (
            d.total_budget > 0
            and d.budget_variance_pct / 100 > cost_escalation
        ),
        build_evidence=lambda d: (
            f"Budget variance {d.budget_variance_pct:.1f}% "
            f"exceeds {cost_escalation * 100:.0f}% tolerance; "
            f"budgeted {d.total_budget:,.0f}, actual {d.total_actual_spend:,.0f}"
        ),
        confidence=lambda d: min(
            0.90,
            0.5 + 0.3 * (d.budget_variance_pct / 100 - cost_escalation)
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-FIN-002",
        layer="financial",
        name="Excessive contract amendments",
        description=(
            "One or more financial line items have more amendments than "
            "the institutional threshold, indicating scope creep or manipulation"
        ),
        evidence_template=financial_mgmt_cite,
        condition=lambda d: any(
            f.amendment_count > DEFAULT_AMENDMENT_THRESHOLD
            for f in d.financials
        ),
        build_evidence=lambda d: (
            f"{sum(1 for f in d.financials if f.amendment_count > DEFAULT_AMENDMENT_THRESHOLD)} "
            f"line item(s) exceed {DEFAULT_AMENDMENT_THRESHOLD}-amendment threshold; "
            f"worst: {max((f.amendment_count for f in d.financials), default=0)} amendments"
        ),
        confidence=lambda d: min(
            0.85,
            0.5 + 0.1 * max(
                (f.amendment_count - DEFAULT_AMENDMENT_THRESHOLD for f in d.financials),
                default=0
            )
        ),
    ))

    rules.append(DeliveryRule(
        rule_id="DEL-FIN-003",
        layer="financial",
        name="Budget variance concentration",
        description=(
            "More than the acceptable ratio of total budget variance is "
            "concentrated in a single line item, indicating targeted manipulation"
        ),
        evidence_template=financial_mgmt_cite,
        condition=lambda d: (
            len(d.financials) >= 2
            and d.total_budget > 0
            and d.total_actual_spend > d.total_budget
            and (
                max(
                    (f.actual_amount - f.budgeted_amount for f in d.financials),
                    default=0
                )
                / (d.total_actual_spend - d.total_budget)
            ) > DEFAULT_BUDGET_CONCENTRATION_RATIO
        ),
        build_evidence=lambda d: (
            f"Largest single-line variance: "
            f"{max((f.actual_amount - f.budgeted_amount for f in d.financials), default=0):,.0f} "
            f"of total overrun {d.total_actual_spend - d.total_budget:,.0f} "
            f"({max((f.actual_amount - f.budgeted_amount for f in d.financials), default=0) / (d.total_actual_spend - d.total_budget) * 100:.0f}% "
            f"> {DEFAULT_BUDGET_CONCENTRATION_RATIO * 100:.0f}% threshold)"
        ),
        confidence=lambda d: 0.75,
    ))

    return rules


# ═══════════════════════════════════════════════════════════
# SECTION 4: DELIVERY RULE ENGINE
# Evaluates all 12 rules against a delivery dossier.
# ═══════════════════════════════════════════════════════════


class DeliveryRuleEngine:
    """
    Deterministic delivery integrity rule evaluation.

    Evaluates every delivery rule against the dossier.
    Rules that fire produce DeliveryRuleResult entries.
    The aggregate DeliveryRulesResult tracks per-layer summaries.
    """

    def __init__(self, profile: Optional[JurisdictionProfile] = None):
        from jurisdiction_profile import US_FEDERAL
        self.profile = profile or US_FEDERAL
        self.rules = build_delivery_rules(self.profile)

    def evaluate(self, dossier: DeliveryDossier) -> DeliveryRulesResult:
        """
        Evaluate all delivery rules against a dossier.

        Returns:
            DeliveryRulesResult with per-rule results and layer summary.
        """
        rule_results: List[DeliveryRuleResult] = []
        layer_summary: dict = {}

        for rule in self.rules:
            try:
                fired = rule.condition(dossier)
            except Exception:
                fired = False

            if fired:
                try:
                    evidence = rule.build_evidence(dossier)
                except Exception:
                    evidence = f"{rule.name} — evidence generation failed"
                try:
                    conf = rule.confidence(dossier)
                except Exception:
                    conf = 0.5

                rule_results.append(DeliveryRuleResult(
                    rule_id=rule.rule_id,
                    layer=rule.layer,
                    fired=True,
                    evidence=evidence,
                    legal_basis=rule.evidence_template,
                    confidence=conf,
                    detail=rule.description,
                ))
                layer_summary[rule.layer] = layer_summary.get(rule.layer, 0) + 1
            else:
                rule_results.append(DeliveryRuleResult(
                    rule_id=rule.rule_id,
                    layer=rule.layer,
                    fired=False,
                    detail=rule.description,
                ))

        return DeliveryRulesResult(
            rules_evaluated=len(self.rules),
            rules_fired=sum(1 for r in rule_results if r.fired),
            rule_results=rule_results,
            layer_summary=layer_summary,
        )
