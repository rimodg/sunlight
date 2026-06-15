"""
Tests for SUNLIGHT Side 4 — Impact Reporting.

Covers:
    ImpactReport Assembly:
        - Executive summary determinism: same inputs → identical summary
        - Pillar impact aggregation from individual redirections
        - CPD gap reduction calculation
        - Beneficiary count aggregation from delivery data
        - Cycle records trace from source RED through delivery verdict
        - Empty report: no recoveries → clean report with zeros
        - Partial cycle: redirection with no delivery verdict → delivery_pending
"""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from recovery_ledger import RecoveryRecord, RecoveryStatus
from redirection import RedirectionRecord
from cpd_allocation import (
    CPDPillarTarget,
    CountryProgrammeProfile,
)
from impact_report import (
    ImpactReport,
    PillarImpact,
    CycleRecord,
    assemble_impact_report,
    assemble_executive_summary,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _make_recovery(
    contract_id="C001",
    amount=500_000,
    status=RecoveryStatus.RECOVERED,
    pillar="health",
):
    rec = RecoveryRecord(
        source_contract_id=contract_id,
        source_verdict="red",
        source_confidence=0.85,
        recovery_amount=amount,
        currency="USD",
        country_office="Nigeria",
        country_code="NG",
        original_pillar=pillar,
    )
    # Advance through state machine to desired status
    if status.value != "identified":
        rec.confirm(date(2026, 1, 15))
    if status in {RecoveryStatus.RECOVERED, RecoveryStatus.REDIRECTED,
                  RecoveryStatus.REDEPLOYED, RecoveryStatus.VERIFIED,
                  RecoveryStatus.CLOSED}:
        rec.mark_recovered(date(2026, 2, 1))
    if status in {RecoveryStatus.REDIRECTED, RecoveryStatus.REDEPLOYED,
                  RecoveryStatus.VERIFIED, RecoveryStatus.CLOSED}:
        rec.mark_redirected()
    if status in {RecoveryStatus.REDEPLOYED, RecoveryStatus.VERIFIED,
                  RecoveryStatus.CLOSED}:
        rec.mark_redeployed()
    if status in {RecoveryStatus.VERIFIED, RecoveryStatus.CLOSED}:
        rec.mark_verified()
    if status == RecoveryStatus.CLOSED:
        rec.close()
    return rec


def _make_redirection(
    recovery_id="R001",
    contract_id="NEW-001",
    pillar="health",
    sdg="SDG 3",
    value=250_000,
    proc_verdict=None,
    del_verdict=None,
    beneficiaries=None,
):
    rd = RedirectionRecord(
        recovery_id=recovery_id,
        target_contract_id=contract_id,
        target_pillar=pillar,
        target_sdg=sdg,
        target_contract_value=value,
    )
    if proc_verdict:
        rd.update_procurement_verdict(proc_verdict)
    if del_verdict:
        rd.update_delivery_verdict(del_verdict, beneficiaries_reached=beneficiaries)
    return rd


def _make_cpd():
    return CountryProgrammeProfile(
        country_office="Nigeria",
        country_code="NG",
        programme_cycle="2022-2026",
        total_programme_budget=50_000_000,
        currency="USD",
        pillars=[
            CPDPillarTarget(
                pillar="health",
                sdg_targets=["SDG 3"],
                target_percentage=0.30,
                target_amount=15_000_000,
                actual_spend=10_000_000,
                actual_percentage=0.20,
            ),
            CPDPillarTarget(
                pillar="education",
                sdg_targets=["SDG 4"],
                target_percentage=0.25,
                target_amount=12_500_000,
                actual_spend=12_000_000,
                actual_percentage=0.24,
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════
# IMPACT REPORT TESTS
# ═══════════════════════════════════════════════════════════


class TestImpactReportAssembly:
    def test_executive_summary_determinism(self):
        """Same inputs produce identical summary."""
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED)
        rd = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                               250_000, "GREEN", "GREEN", 2000)

        r1 = assemble_impact_report(
            recoveries=[rec], redirections=[rd],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
            jurisdiction_profile="us_federal",
            total_contracts_analyzed=100,
            total_flagged_red=5,
        )
        r2 = assemble_impact_report(
            recoveries=[rec], redirections=[rd],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
            jurisdiction_profile="us_federal",
            total_contracts_analyzed=100,
            total_flagged_red=5,
        )
        assert r1.executive_summary == r2.executive_summary

    def test_pillar_impact_aggregation(self):
        """Correct rollup from individual redirections."""
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED, "health")
        rd1 = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                                150_000, "GREEN", "GREEN", 1000)
        rd2 = _make_redirection(rec.recovery_id, "NEW-002", "health", "SDG 3",
                                100_000, "GREEN", None, None)

        report = assemble_impact_report(
            recoveries=[rec], redirections=[rd1, rd2],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
        )
        health_pillar = next(
            p for p in report.redirections_by_pillar if p.pillar == "health"
        )
        assert health_pillar.contracts_redeployed == 2
        assert health_pillar.amount_redirected == 250_000
        assert health_pillar.procurement_green == 2
        assert health_pillar.delivery_green == 1
        assert health_pillar.beneficiaries_reached == 1000

    def test_cpd_gap_reduction(self):
        """Gap reduction calculated correctly from CPD data."""
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED, "health")
        rd = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                               500_000, "GREEN", "GREEN", 3000)
        cpd = _make_cpd()

        report = assemble_impact_report(
            recoveries=[rec], redirections=[rd],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
            cpd=cpd,
        )
        assert report.gap_reduction_percentage > 0
        assert len(report.cpd_gaps_before) == 2
        assert len(report.cpd_gaps_after) == 2

    def test_beneficiary_aggregation(self):
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED)
        rd1 = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                                250_000, "GREEN", "GREEN", 2000)
        rd2 = _make_redirection(rec.recovery_id, "NEW-002", "education", "SDG 4",
                                250_000, "GREEN", "GREEN", 3000)

        report = assemble_impact_report(
            recoveries=[rec], redirections=[rd1, rd2],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
        )
        assert report.total_beneficiaries_reached == 5000

    def test_cycle_records_trace(self):
        """Cycle records trace from source RED to delivery verdict."""
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED)
        rd = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                               250_000, "GREEN", "GREEN", 2000)

        report = assemble_impact_report(
            recoveries=[rec], redirections=[rd],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
        )
        assert len(report.cycle_records) == 1
        cycle = report.cycle_records[0]
        assert cycle.source_contract_id == "C001"
        assert cycle.source_verdict == "red"
        assert cycle.target_contract_id == "NEW-001"
        assert cycle.procurement_verdict == "GREEN"
        assert cycle.delivery_verdict == "GREEN"
        assert cycle.beneficiaries == 2000
        assert cycle.cycle_complete is True

    def test_empty_report(self):
        """No recoveries → clean report with zeros."""
        report = assemble_impact_report(
            recoveries=[], redirections=[],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
        )
        assert report.total_recoveries == 0
        assert report.total_amount_recovered == 0
        assert report.total_redirections == 0
        assert report.total_beneficiaries_reached == 0
        assert len(report.cycle_records) == 0
        assert len(report.executive_summary) > 0

    def test_partial_cycle_delivery_pending(self):
        """Redirection with no delivery verdict → delivery_pending counted."""
        rec = _make_recovery("C001", 500_000, RecoveryStatus.RECOVERED)
        rd = _make_redirection(rec.recovery_id, "NEW-001", "health", "SDG 3",
                               250_000, "GREEN", None, None)

        report = assemble_impact_report(
            recoveries=[rec], redirections=[rd],
            country_office="Nigeria", country_code="NG",
            reporting_period_start=date(2026, 1, 1),
            reporting_period_end=date(2026, 6, 30),
        )
        assert report.redeployed_delivery_pending == 1
        assert report.redeployed_delivery_green == 0
        cycle = report.cycle_records[0]
        assert cycle.delivery_verdict is None
        assert cycle.cycle_complete is False
