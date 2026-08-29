"""
SUNLIGHT Side 4 — Impact Reporting
=====================================

Assembles full-cycle reports from recovery data. This is what goes
on the Administrator's desk at donor meetings: how much was caught,
where it was redirected, whether the redirected contracts delivered,
and how CPD alignment improved.

Every word in every report traces to a data point. Executive summaries
are deterministic templates. No AI text generation. No interpretation.
No opinion.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from recovery_ledger import RecoveryRecord, RecoveryStatus
from redirection import RedirectionRecord
from cpd_allocation import CountryProgrammeProfile


# ═══════════════════════════════════════════════════════════
# SECTION 1: DATA STRUCTURES
# ═══════════════════════════════════════════════════════════


@dataclass
class CycleRecord:
    """One complete catch-redirect-verify cycle for traceability."""
    source_contract_id: str
    source_verdict: str
    source_amount: float
    target_contract_id: str
    target_pillar: str
    target_sdg: str
    target_output: Optional[str]
    procurement_verdict: str
    delivery_verdict: Optional[str]
    beneficiaries: Optional[int]
    cycle_complete: bool


@dataclass
class PillarImpact:
    """Impact within one development pillar."""
    pillar: str
    sdg_targets: List[str] = field(default_factory=list)
    amount_recovered: float = 0.0
    amount_redirected: float = 0.0
    contracts_redeployed: int = 0
    procurement_green: int = 0
    delivery_green: int = 0
    beneficiaries_reached: int = 0
    cpd_gap_before: float = 0.0
    cpd_gap_after: float = 0.0
    outputs_advanced: List[dict] = field(default_factory=list)


@dataclass
class ImpactReport:
    """
    Full-cycle report for a country office or reporting period.

    This is the institutional output — what goes on the Administrator's
    desk at donor meetings.
    """
    # Identity
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    country_office: str = ""
    country_code: str = ""
    reporting_period_start: Optional[date] = None
    reporting_period_end: Optional[date] = None
    jurisdiction_profile: str = ""

    # Side 1 aggregate
    total_contracts_analyzed: int = 0
    total_flagged_red: int = 0
    total_flagged_yellow: int = 0
    total_cleared_green: int = 0

    # Recovery aggregate
    total_recoveries: int = 0
    total_amount_recovered: float = 0.0
    currency: str = "USD"

    # Redirection aggregate
    total_redirections: int = 0
    total_amount_redirected: float = 0.0
    redirections_by_pillar: List[PillarImpact] = field(default_factory=list)
    redirections_by_sdg: Dict[str, float] = field(default_factory=dict)

    # Delivery aggregate on redeployed contracts
    redeployed_contracts_total: int = 0
    redeployed_procurement_green: int = 0
    redeployed_delivery_green: int = 0
    redeployed_delivery_pending: int = 0
    total_beneficiaries_reached: int = 0

    # Evidence corroboration (Side 5).
    #
    # Every field defaults to zero, so a report assembled without
    # corroboration data is byte-identical to one produced before Side 5
    # existed. Populated, they qualify every outcome claim in this report.
    #
    # unverified_outcomes is reported SEPARATELY from contradicted_outcomes
    # and must never be added to it. They mean opposite things: one is
    # evidence we could not reach, the other is evidence that conflicts.
    # A country office with thin registries accumulates the first, and
    # merging the two would read as a pattern of contradicted claims in
    # exactly the offices least able to answer the charge.
    corroborated_outcomes: int = 0
    partially_corroborated_outcomes: int = 0
    unverified_outcomes: int = 0
    contradicted_outcomes: int = 0
    average_corroboration_capacity: float = 0.0

    # Absence Ledger (additive). Populated only when absence data is
    # supplied; None keeps reports byte-identical to pre-absence output.
    absence: Optional[dict] = None

    @property
    def has_absence_data(self) -> bool:
        """Whether this report carries confirmed Absence Ledger data.

        Gates the absence clause in the executive summary. With no absence
        data, or none confirmed, the summary is byte-identical to one
        produced before the Absence Ledger existed.
        """
        return bool(self.absence) and self.absence.get("confirmed_diversions", 0) > 0

    # CPD alignment
    cpd_gaps_before: List[dict] = field(default_factory=list)
    cpd_gaps_after: List[dict] = field(default_factory=list)
    gap_reduction_percentage: float = 0.0

    @property
    def has_corroboration_data(self) -> bool:
        """Whether any outcome in this report carries a corroboration verdict.

        Gates the corroboration clause in the executive summary. With no
        Side 5 data the summary is unchanged, which is what keeps the
        addition non-breaking for existing reports.
        """
        return (
            self.corroborated_outcomes
            + self.partially_corroborated_outcomes
            + self.unverified_outcomes
            + self.contradicted_outcomes
        ) > 0

    @property
    def outcomes_with_verdicts(self) -> int:
        return (
            self.corroborated_outcomes
            + self.partially_corroborated_outcomes
            + self.unverified_outcomes
            + self.contradicted_outcomes
        )

    # Narrative
    executive_summary: str = ""

    # Full cycle proof chain
    cycle_records: List[CycleRecord] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# SECTION 2: REPORT ASSEMBLY
# ═══════════════════════════════════════════════════════════


def assemble_impact_report(
    recoveries: List[RecoveryRecord],
    redirections: List[RedirectionRecord],
    country_office: str,
    country_code: str,
    reporting_period_start: date,
    reporting_period_end: date,
    jurisdiction_profile: str = "",
    currency: str = "USD",
    total_contracts_analyzed: int = 0,
    total_flagged_red: int = 0,
    total_flagged_yellow: int = 0,
    total_cleared_green: int = 0,
    cpd: Optional[CountryProgrammeProfile] = None,
    corroboration: Optional[dict] = None,
) -> ImpactReport:
    """
    Assemble a full-cycle impact report from recovery and redirection data.

    Args:
        recoveries: Recovery records for the reporting period.
        redirections: Redirection records linked to those recoveries.
        country_office: Country office identifier.
        country_code: ISO 3166-1 alpha-2 code.
        reporting_period_start: Start of reporting period.
        reporting_period_end: End of reporting period.
        jurisdiction_profile: Jurisdiction profile name.
        currency: ISO 4217 currency code.
        total_contracts_analyzed: Total contracts analyzed in period.
        total_flagged_red: Total RED flags in period.
        total_flagged_yellow: Total YELLOW flags in period.
        total_cleared_green: Total GREEN contracts in period.
        cpd: Optional CPD profile for gap reduction calculation.
        corroboration: Optional Side 5 summary, as produced by
            evidence_integration.corroboration_summary(). Recognised keys:
            corroborated_outcomes, partially_corroborated_outcomes,
            unverified_outcomes, contradicted_outcomes,
            average_corroboration_capacity.

            Passed as a plain dict rather than typed objects so that this
            module — Side 4 — needs no import of Side 5. If it is omitted,
            the report is identical in every field to one produced before
            the evidence engine existed.

    Returns:
        ImpactReport with all aggregates and executive summary.
    """
    # Recovery aggregates
    recoverable_statuses = {
        RecoveryStatus.RECOVERED,
        RecoveryStatus.REDIRECTED,
        RecoveryStatus.REDEPLOYED,
        RecoveryStatus.VERIFIED,
        RecoveryStatus.CLOSED,
    }
    recovered_records = [
        r for r in recoveries if r.status in recoverable_statuses
    ]
    total_amount_recovered = sum(r.recovery_amount for r in recovered_records)

    # Redirection aggregates
    total_amount_redirected = sum(r.target_contract_value for r in redirections)

    # Build redirection_map: recovery_id → [RedirectionRecord]
    redirection_map: Dict[str, List[RedirectionRecord]] = {}
    for rd in redirections:
        redirection_map.setdefault(rd.recovery_id, []).append(rd)

    # Pillar impact aggregation
    pillar_data: Dict[str, PillarImpact] = {}
    sdg_data: Dict[str, float] = {}

    for rd in redirections:
        pillar = rd.target_pillar
        if pillar not in pillar_data:
            pillar_data[pillar] = PillarImpact(pillar=pillar)
        pi = pillar_data[pillar]

        pi.amount_redirected += rd.target_contract_value
        pi.contracts_redeployed += 1

        if rd.procurement_verdict and rd.procurement_verdict.upper() == "GREEN":
            pi.procurement_green += 1
        if rd.delivery_verdict and rd.delivery_verdict.upper() == "GREEN":
            pi.delivery_green += 1
        if rd.beneficiaries_reached:
            pi.beneficiaries_reached += rd.beneficiaries_reached

        if rd.target_sdg:
            sdg_data[rd.target_sdg] = sdg_data.get(rd.target_sdg, 0) + rd.target_contract_value
            if rd.target_sdg not in pi.sdg_targets:
                pi.sdg_targets.append(rd.target_sdg)

    # Recovery amounts by pillar (from original_pillar of recovery records)
    for rec in recovered_records:
        pillar = rec.original_pillar
        if pillar and pillar in pillar_data:
            pillar_data[pillar].amount_recovered += rec.recovery_amount

    # Delivery aggregate on redeployed contracts
    redeployed_total = len(redirections)
    redeployed_procurement_green = sum(
        1 for rd in redirections
        if rd.procurement_verdict and rd.procurement_verdict.upper() == "GREEN"
    )
    redeployed_delivery_green = sum(
        1 for rd in redirections
        if rd.delivery_verdict and rd.delivery_verdict.upper() == "GREEN"
    )
    redeployed_delivery_pending = sum(
        1 for rd in redirections if rd.delivery_verdict is None
    )
    total_beneficiaries = sum(
        rd.beneficiaries_reached or 0 for rd in redirections
    )

    # Cycle records
    cycle_records = []
    for rec in recoveries:
        rds = redirection_map.get(rec.recovery_id, [])
        for rd in rds:
            cycle_records.append(CycleRecord(
                source_contract_id=rec.source_contract_id,
                source_verdict=rec.source_verdict,
                source_amount=rec.recovery_amount,
                target_contract_id=rd.target_contract_id,
                target_pillar=rd.target_pillar,
                target_sdg=rd.target_sdg,
                target_output=rd.target_output,
                procurement_verdict=rd.procurement_verdict or "pending",
                delivery_verdict=rd.delivery_verdict,
                beneficiaries=rd.beneficiaries_reached,
                cycle_complete=rd.full_cycle_complete,
            ))

    # CPD gap reduction
    cpd_gaps_before = []
    cpd_gaps_after = []
    gap_reduction = 0.0

    if cpd:
        for p in cpd.pillars:
            cpd_gaps_before.append({
                "pillar": p.pillar,
                "gap_percentage": p.gap_percentage,
            })
            # After redirection: add redirected amount to actual spend
            redirected_to_pillar = sum(
                rd.target_contract_value for rd in redirections
                if rd.target_pillar == p.pillar
            )
            new_actual = p.actual_spend + redirected_to_pillar
            new_actual_pct = (
                new_actual / cpd.total_programme_budget
                if cpd.total_programme_budget > 0 else 0
            )
            new_gap = p.target_percentage - new_actual_pct
            cpd_gaps_after.append({
                "pillar": p.pillar,
                "gap_percentage": new_gap,
            })

        # Gap reduction: average reduction in absolute gap
        if cpd_gaps_before:
            total_gap_before = sum(
                abs(g["gap_percentage"]) for g in cpd_gaps_before
            )
            total_gap_after = sum(
                abs(g["gap_percentage"]) for g in cpd_gaps_after
            )
            if total_gap_before > 0:
                gap_reduction = (
                    (total_gap_before - total_gap_after)
                    / total_gap_before * 100
                )

    report = ImpactReport(
        country_office=country_office,
        country_code=country_code,
        reporting_period_start=reporting_period_start,
        reporting_period_end=reporting_period_end,
        jurisdiction_profile=jurisdiction_profile,
        total_contracts_analyzed=total_contracts_analyzed,
        total_flagged_red=total_flagged_red,
        total_flagged_yellow=total_flagged_yellow,
        total_cleared_green=total_cleared_green,
        total_recoveries=len(recovered_records),
        total_amount_recovered=total_amount_recovered,
        currency=currency,
        total_redirections=len(redirections),
        total_amount_redirected=total_amount_redirected,
        redirections_by_pillar=list(pillar_data.values()),
        redirections_by_sdg=sdg_data,
        redeployed_contracts_total=redeployed_total,
        redeployed_procurement_green=redeployed_procurement_green,
        redeployed_delivery_green=redeployed_delivery_green,
        redeployed_delivery_pending=redeployed_delivery_pending,
        total_beneficiaries_reached=total_beneficiaries,
        cpd_gaps_before=cpd_gaps_before,
        cpd_gaps_after=cpd_gaps_after,
        gap_reduction_percentage=gap_reduction,
        cycle_records=cycle_records,
    )

    if corroboration:
        report.corroborated_outcomes = int(
            corroboration.get("corroborated_outcomes", 0))
        report.partially_corroborated_outcomes = int(
            corroboration.get("partially_corroborated_outcomes", 0))
        report.unverified_outcomes = int(
            corroboration.get("unverified_outcomes", 0))
        report.contradicted_outcomes = int(
            corroboration.get("contradicted_outcomes", 0))
        report.average_corroboration_capacity = float(
            corroboration.get("average_corroboration_capacity", 0.0))

    report.executive_summary = assemble_executive_summary(report)
    return report


# ═══════════════════════════════════════════════════════════
# SECTION 3: EXECUTIVE SUMMARY
# ═══════════════════════════════════════════════════════════


def assemble_executive_summary(report: ImpactReport) -> str:
    """
    Build a deterministic executive summary from report data.

    Every word traces to a data point. No interpretation.
    No adjectives. No opinion.

    Args:
        report: ImpactReport with all fields populated.

    Returns:
        Deterministic executive summary string.
    """
    verified_cycles = sum(1 for c in report.cycle_records if c.cycle_complete)
    clean_cycles = sum(
        1 for c in report.cycle_records
        if c.cycle_complete
        and c.procurement_verdict.upper() == "GREEN"
        and c.delivery_verdict
        and c.delivery_verdict.upper() == "GREEN"
    )

    top_pillar = (
        max(report.redirections_by_pillar, key=lambda p: p.amount_redirected)
        if report.redirections_by_pillar else None
    )

    period_str = ""
    if report.reporting_period_start and report.reporting_period_end:
        period_str = (
            f"{report.reporting_period_start} to {report.reporting_period_end}"
        )

    summary = (
        f"{report.country_office} ({period_str}): "
        f"{report.total_contracts_analyzed} contracts "
        f"analyzed under {report.jurisdiction_profile} profile. "
        f"{report.total_flagged_red} structural integrity failures identified. "
        f"{report.total_amount_recovered:,.0f} {report.currency} recovered and "
        f"redirected across {len(report.redirections_by_pillar)} development pillars. "
    )

    if top_pillar:
        summary += (
            f"Largest redirection: {top_pillar.amount_redirected:,.0f} "
            f"{report.currency} to {top_pillar.pillar} "
            f"({', '.join(top_pillar.sdg_targets)}). "
        )

    summary += (
        f"{report.redeployed_contracts_total} redeployed contracts verified: "
        f"{report.redeployed_procurement_green} procurement clean, "
        f"{report.redeployed_delivery_green} delivery confirmed. "
    )

    # Beneficiary counts are stated with their corroboration status, never
    # bare — but only when corroboration data exists. With no Side 5 data
    # the sentence is exactly what it was before the evidence engine
    # existed, which is what keeps this addition non-breaking.
    if report.has_corroboration_data:
        summary += _corroboration_clause(report)
    else:
        summary += f"{report.total_beneficiaries_reached:,} beneficiaries reached. "

    summary += (
        f"CPD alignment improved by {report.gap_reduction_percentage:.1f} "
        f"percentage points across the programme cycle."
    )

    # Absence Ledger clause (additive). Rendered only when confirmed
    # absence data exists, so the no-absence summary is byte-identical
    # to pre-ledger output, mirroring the corroboration precedent.
    if report.has_absence_data:
        summary += _absence_clause(report)

    return summary


def _corroboration_clause(report: ImpactReport) -> str:
    """State beneficiary reach alongside what independent evidence supports.

    A bare beneficiary number invites the reader to treat it as established
    fact. It is a claimed figure, and the honest presentation says how much
    of it independent evidence actually reaches.

    UNVERIFIED is reported in its own words — "could not be verified from
    available sources" — and never folded into the contradicted count. In a
    country whose registries are thin, most outcomes will land there, and
    that is a statement about the available evidence rather than about the
    programme or the people running it. The clause names the average
    corroboration capacity for the same reason: the reader needs to know how
    far SUNLIGHT could see before weighing what it found.
    """
    parts = [
        f"{report.total_beneficiaries_reached:,} beneficiaries reported across "
        f"{report.outcomes_with_verdicts} outcome claims, of which "
        f"{report.corroborated_outcomes} corroborated by independent evidence, "
        f"{report.partially_corroborated_outcomes} partially corroborated, "
        f"{report.unverified_outcomes} could not be verified from available "
        f"sources, and {report.contradicted_outcomes} structurally contradicted "
        f"by independent evidence. "
    ]

    parts.append(
        f"Average corroboration capacity {report.average_corroboration_capacity:.0%} "
        f"of the six evidence classes. "
    )

    if report.unverified_outcomes:
        parts.append(
            "Unverified outcomes reflect the evidence reachable in this "
            "jurisdiction and are not adverse findings. "
        )

    return "".join(parts)


def _absence_clause(report: ImpactReport) -> str:
    """State what confirmed diversions left unfunded, in the CPD's own terms.

    Sums only CPD-stated beneficiary figures and names the count of affected
    outputs stating no figure, so the number is never mistaken for a total.
    Every figure traces to the absence roll_up, which traces to the CPD.
    """
    a = report.absence or {}
    n = a.get("confirmed_diversions", 0)
    amt = a.get("total_diverted_confirmed", 0.0)
    m = a.get("stated_planned_beneficiaries_total", 0)
    k = a.get("outputs_without_stated_beneficiaries", 0)
    return (
        f"Confirmed diversions: {n}, totalling {amt:,.0f} {report.currency}, "
        f"left CPD-planned capacity unfunded for a combined {m:,} stated "
        f"planned beneficiaries ({k} affected outputs state no figure). "
    )
