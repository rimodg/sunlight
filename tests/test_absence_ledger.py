"""
Increment 1: CPDOutputTarget schema growth + _get_absence_param.
Proves the growth is additive: old constructions and old JSON unchanged,
new fields round-trip, absent means None and never zero.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from cpd_allocation import (
    CPDOutputTarget,
    _parse_cpd_profile,
    load_cpd_profile,
)
from absence_ledger import _get_absence_param


def test_positional_construction_unbroken():
    """Existing tests build CPDOutputTarget positionally; growth must not break them."""
    o = CPDOutputTarget("3.1.1", "Primary clinics", "health", 1000.0, 400.0)
    assert o.output_id == "3.1.1"
    assert o.planned_capacity_description is None
    assert o.planned_beneficiaries is None
    assert o.planned_delivery_date is None
    assert o.source_document_citation is None


def test_parser_roundtrips_new_fields():
    data = {
        "country_office": "Testland",
        "country_code": "TL",
        "outputs": [{
            "output_id": "TL-H-001",
            "output_description": "Clinics",
            "pillar": "health",
            "target_amount": 5000000,
            "actual_spend": 1000000,
            "planned_capacity_description": "15 primary health clinics",
            "planned_beneficiaries": 30000,
            "planned_delivery_date": "2026-06-30",
            "source_document_citation": "CPD Testland 2023-2027, output 3.1.1",
        }],
    }
    prof = _parse_cpd_profile(data)
    o = prof.outputs[0]
    assert o.planned_capacity_description == "15 primary health clinics"
    assert o.planned_beneficiaries == 30000
    assert o.planned_delivery_date == "2026-06-30"
    assert o.source_document_citation == "CPD Testland 2023-2027, output 3.1.1"


def test_old_json_yields_none_not_zero():
    """A CPD without absence fields parses with None everywhere: not stated, not zero."""
    data = {
        "country_office": "Testland",
        "country_code": "TL",
        "outputs": [{
            "output_id": "TL-H-001",
            "output_description": "Clinics",
            "pillar": "health",
        }],
    }
    o = _parse_cpd_profile(data).outputs[0]
    assert o.planned_beneficiaries is None
    assert o.planned_beneficiaries != 0
    assert o.planned_delivery_date is None
    assert o.planned_capacity_description is None
    assert o.source_document_citation is None


def test_ng_profile_still_loads_with_none_fields():
    """Golden: the shipped illustrative profile loads; new fields read None until authored."""
    prof = load_cpd_profile("ng")
    assert prof is not None
    assert len(prof.outputs) > 0
    for o in prof.outputs:
        assert _get_absence_param(o, "planned_beneficiaries") is None


def test_get_absence_param_present_and_absent():
    o = CPDOutputTarget("X", "Y", "health", planned_beneficiaries=1200)
    assert _get_absence_param(o, "planned_beneficiaries") == 1200
    assert _get_absence_param(o, "nonexistent_field") is None
    assert _get_absence_param(o, "nonexistent_field", "fallback") == "fallback"


def test_none_default_is_none_not_falsy_zero():
    """The default for absence params is None, so absence is distinguishable from 0."""
    o = CPDOutputTarget("X", "Y", "health")
    v = _get_absence_param(o, "planned_beneficiaries")
    assert v is None and v != 0


# ── Increment 2: pure functions ──────────────────────────────────────

from datetime import date
from dataclasses import asdict

from recovery_ledger import RecoveryRecord, RecoveryStatus
from absence_ledger import (
    AbsenceFraming,
    compute_absence_record,
    absence_table,
    roll_up,
)


def _profile():
    return _parse_cpd_profile({
        "country_office": "Testland", "country_code": "TL",
        "source_document": "CPD Testland 2023-2027 (illustrative)",
        "outputs": [
            {"output_id": "TL-H-001", "output_description": "Clinics",
             "pillar": "health", "planned_capacity_description": "15 clinics",
             "planned_beneficiaries": 30000,
             "planned_delivery_date": "2026-01-31",
             "source_document_citation": "CPD Testland, output TL-H-001"},
            {"output_id": "TL-E-001", "output_description": "Schools",
             "pillar": "education"},
        ],
    })


def _recovery(status=RecoveryStatus.CONFIRMED):
    return RecoveryRecord(
        recovery_id="rec-001", source_contract_id="C-001",
        recovery_amount=4200000.0, currency="USD",
        country_office="Testland CO", country_code="TL",
        original_pillar="health", status=status,
    )


def test_determinism_byte_identical():
    a = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29))
    b = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29))
    assert asdict(a) == asdict(b)
    assert a.absence_id == "absence:rec-001:TL-H-001"


def test_as_of_changes_duration_only():
    a = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29))
    b = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 9, 29))
    da, db = asdict(a), asdict(b)
    assert da.pop("absence_duration_days") != db.pop("absence_duration_days")
    assert da.pop("as_of") != db.pop("as_of")
    assert da == db


def test_no_wall_clock_in_module():
    src = open("code/absence_ledger.py").read()
    assert "datetime.now" not in src
    assert "utcnow" not in src
    assert ".today(" not in src


def test_framing_gate_by_status():
    assert compute_absence_record(_recovery(RecoveryStatus.IDENTIFIED), _profile(),
                                  "TL-H-001", date(2026, 8, 29)).framing == AbsenceFraming.AT_RISK
    for st in (RecoveryStatus.CONFIRMED, RecoveryStatus.RECOVERED):
        assert compute_absence_record(_recovery(st), _profile(),
                                      "TL-H-001", date(2026, 8, 29)).framing == AbsenceFraming.DEPRIVED


def test_table_refuses_full_payload_when_at_risk():
    r = compute_absence_record(_recovery(RecoveryStatus.IDENTIFIED), _profile(),
                               "TL-H-001", date(2026, 8, 29))
    t = absence_table(r)
    assert t["framing"] == "at_risk"
    assert "note" in t
    assert "absence_duration_days" not in t
    assert "planned_beneficiaries" not in t
    full = absence_table(compute_absence_record(_recovery(), _profile(),
                                                "TL-H-001", date(2026, 8, 29)))
    assert full["framing"] == "deprived"
    assert full["planned_beneficiaries"] == 30000
    assert full["absence_duration_days"] == 210


def test_duration_past_and_boundary():
    r = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29))
    assert r.absence_duration_days == 210 and r.duration_reason is None
    r0 = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 1, 31))
    assert r0.absence_duration_days == 0


def test_duration_future_date_is_reasoned_none():
    r = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2025, 12, 1))
    assert r.absence_duration_days is None
    assert "not yet reached" in r.duration_reason


def test_duration_malformed_date_is_reasoned_none():
    prof = _profile()
    prof.outputs[0].planned_delivery_date = "31/01/2026"
    r = compute_absence_record(_recovery(), prof, "TL-H-001", date(2026, 8, 29))
    assert r.absence_duration_days is None
    assert "malformed" in r.duration_reason


def test_duration_unstated_date_is_reasoned_none():
    r = compute_absence_record(_recovery(), _profile(), "TL-E-001", date(2026, 8, 29))
    assert r.absence_duration_days is None
    assert "no planned delivery date stated" in r.duration_reason
    assert r.planned_beneficiaries is None and r.planned_beneficiaries != 0


def test_citation_fallback_chain():
    r = compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29))
    assert r.cpd_citation == "CPD Testland, output TL-H-001"
    r2 = compute_absence_record(_recovery(), _profile(), "TL-E-001", date(2026, 8, 29))
    assert r2.cpd_citation == "CPD Testland 2023-2027 (illustrative)"
    bare = _parse_cpd_profile({"country_office": "T", "country_code": "TL",
                               "outputs": [{"output_id": "X", "output_description": "D",
                                            "pillar": "health"}]})
    r3 = compute_absence_record(_recovery(), bare, "X", date(2026, 8, 29))
    assert "document reference not stated" in r3.cpd_citation


def test_output_not_found_and_missing_inputs_are_honest():
    r = compute_absence_record(_recovery(), _profile(), "TL-Z-999", date(2026, 8, 29))
    assert r.cpd_output_found is False and "not found" in r.notes
    assert r.planned_beneficiaries is None
    r2 = compute_absence_record(_recovery(), None, "TL-H-001", date(2026, 8, 29))
    assert r2.cpd_output_found is False and "no CPD profile" in r2.notes
    r3 = compute_absence_record(_recovery(), _profile(), None, date(2026, 8, 29))
    assert r3.cpd_output_found is False and "no CPD output id" in r3.notes


def test_zero_amount_no_crash():
    rec = _recovery()
    rec.recovery_amount = 0.0
    r = compute_absence_record(rec, _profile(), "TL-H-001", date(2026, 8, 29))
    assert r.diverted_amount == 0.0


def test_roll_up_sums_only_stated_and_reports_unstated():
    recs = [
        compute_absence_record(_recovery(), _profile(), "TL-H-001", date(2026, 8, 29)),
        compute_absence_record(RecoveryRecord(
            recovery_id="rec-002", source_contract_id="C-002",
            recovery_amount=1000000.0, currency="USD",
            country_office="Testland CO", country_code="TL",
            original_pillar="education", status=RecoveryStatus.CONFIRMED,
        ), _profile(), "TL-E-001", date(2026, 8, 29)),
        compute_absence_record(_recovery(RecoveryStatus.IDENTIFIED), _profile(),
                               "TL-H-001", date(2026, 8, 29)),
    ]
    agg = roll_up(recs)
    assert agg["confirmed_diversions"] == 2
    assert agg["at_risk_not_confirmed"] == 1
    assert agg["total_diverted_confirmed"] == 5200000.0
    assert agg["stated_planned_beneficiaries_total"] == 30000
    assert agg["outputs_with_stated_beneficiaries"] == 1
    assert agg["outputs_without_stated_beneficiaries"] == 1
    assert agg["by_pillar"]["health"]["diverted_amount"] == 4200000.0
    assert agg["by_pillar"]["education"]["outputs_affected"] == 1


def test_real_ng_profile_degrades_honestly():
    prof = load_cpd_profile("ng")
    rec = RecoveryRecord(recovery_id="rec-ng", source_contract_id="C-NG",
                         recovery_amount=2000000.0, currency="USD",
                         country_office="Nigeria", country_code="NG",
                         original_pillar="health", status=RecoveryStatus.CONFIRMED)
    r = compute_absence_record(rec, prof, "NG-H-001", date(2026, 8, 29))
    assert r.cpd_output_found is True
    assert r.planned_beneficiaries is None
    assert r.absence_duration_days is None
    assert "no planned delivery date stated" in r.duration_reason
    assert r.cpd_citation == "UNDP CPD Nigeria 2023-2027 (illustrative)"


# ── Increment 3: heart wiring, report gate, golden invariance ────────

from datetime import date as _date

from impact_report import assemble_impact_report, assemble_executive_summary


def _assembled_report():
    return assemble_impact_report(
        recoveries=[_recovery()],
        redirections=[],
        country_office="Testland CO",
        country_code="TL",
        reporting_period_start=_date(2026, 1, 1),
        reporting_period_end=_date(2026, 8, 29),
        jurisdiction_profile="us_federal",
        currency="USD",
    )


def test_golden_no_absence_summary_byte_identical():
    """The pre-ledger summary is untouched: with absence None the new code
    path never executes, and attaching absence only ever appends."""
    report = _assembled_report()
    before = report.executive_summary
    assert "Confirmed diversions:" not in before
    assert "unfunded" not in before
    report.absence = roll_up([
        compute_absence_record(_recovery(), _profile(), "TL-H-001", _date(2026, 8, 29)),
    ])
    after = assemble_executive_summary(report)
    assert after.startswith(before)
    assert "Confirmed diversions: 1" in after
    assert "30,000 stated" in after


def test_absence_gate_semantics():
    report = _assembled_report()
    assert report.has_absence_data is False
    report.absence = {}
    assert report.has_absence_data is False
    report.absence = roll_up([
        compute_absence_record(_recovery(RecoveryStatus.IDENTIFIED), _profile(),
                               "TL-H-001", _date(2026, 8, 29)),
    ])
    assert report.has_absence_data is False  # at-risk only: nothing confirmed
    report.absence = roll_up([
        compute_absence_record(_recovery(), _profile(), "TL-H-001", _date(2026, 8, 29)),
    ])
    assert report.has_absence_data is True


def test_at_risk_only_summary_unchanged():
    report = _assembled_report()
    before = report.executive_summary
    report.absence = roll_up([
        compute_absence_record(_recovery(RecoveryStatus.IDENTIFIED), _profile(),
                               "TL-H-001", _date(2026, 8, 29)),
    ])
    assert assemble_executive_summary(report) == before


def test_recovery_record_carries_absence_id():
    rec = _recovery()
    assert rec.absence_id is None
    rec.absence_id = "absence:rec-001:TL-H-001"
    assert rec.absence_id == "absence:rec-001:TL-H-001"


def test_clause_reports_unstated_count():
    report = _assembled_report()
    report.absence = roll_up([
        compute_absence_record(_recovery(), _profile(), "TL-H-001", _date(2026, 8, 29)),
        compute_absence_record(RecoveryRecord(
            recovery_id="rec-003", source_contract_id="C-003",
            recovery_amount=500000.0, currency="USD",
            country_office="Testland CO", country_code="TL",
            original_pillar="education", status=RecoveryStatus.CONFIRMED,
        ), _profile(), "TL-E-001", _date(2026, 8, 29)),
    ])
    s = assemble_executive_summary(report)
    assert "Confirmed diversions: 2" in s
    assert "4,700,000 USD" in s
    assert "(1 affected outputs state no figure)" in s
