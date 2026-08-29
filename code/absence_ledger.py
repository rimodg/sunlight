"""
Absence Ledger: deterministic statement of what a confirmed diversion left
unfunded, in the institution's own CPD terms.

Constitutional rules of this module, enforced by tests:
1. Never estimate consequence. Every value is arithmetic over fields the CPD
   itself states, with the CPD cited, or it is None.
2. None means "not stated in CPD" and is never rendered as zero.
3. No wall clock. All durations compute against an explicit as_of date.
"""

from dataclasses import dataclass, asdict, field
from datetime import date
from enum import Enum
from typing import Any, List, Optional


def _get_absence_param(obj: Any, param: str, default: Any = None) -> Any:
    """
    Safely retrieve an absence-related parameter from a CPD object.

    Mirrors _get_delivery_param: absence fields are added to CPDOutputTarget
    additively, and any profile-like object lacking them still works. A
    missing attribute returns the default, which for absence semantics is
    None ("not stated in CPD"), never zero.
    """
    return getattr(obj, param, default)


class AbsenceFraming(Enum):
    """Honest language gate. Before institutional confirmation the only
    truthful claim is that planned capacity is at risk."""
    AT_RISK = "at_risk"
    DEPRIVED = "deprived"


@dataclass
class AbsenceRecord:
    """What a diversion left unfunded, in the CPD's own stated terms.
    Every populated planned_* field is paired with cpd_citation. None means
    the CPD does not state it, and is never rendered as zero."""
    absence_id: str
    recovery_id: str
    source_contract_id: str
    cpd_output_id: Optional[str]
    cpd_output_found: bool
    pillar: str
    country_office: str
    country_code: str
    diverted_amount: float
    currency: str
    framing: AbsenceFraming
    as_of: str
    output_description: Optional[str] = None
    planned_capacity_description: Optional[str] = None
    planned_beneficiaries: Optional[int] = None
    planned_delivery_date: Optional[str] = None
    cpd_citation: Optional[str] = None
    absence_duration_days: Optional[int] = None
    duration_reason: Optional[str] = None
    notes: Optional[str] = None


def _compute_duration(planned_iso: Optional[str], as_of: date):
    """(days, reason). Days only when a stated planned date is in the past
    relative to the explicit as_of. Never reads the wall clock."""
    if planned_iso is None:
        return None, "no planned delivery date stated in CPD"
    try:
        planned = date.fromisoformat(planned_iso)
    except (ValueError, TypeError):
        return None, f"planned delivery date malformed in CPD: {planned_iso!r}"
    if planned > as_of:
        return None, f"planned delivery date {planned_iso} not yet reached as of {as_of.isoformat()}"
    return (as_of - planned).days, None


def _resolve_citation(output, profile) -> str:
    """Citation fallback chain. A stated value always carries a source: the
    output's own citation, else the profile's source document, else the
    profile itself named as source with the gap disclosed."""
    c = _get_absence_param(output, "source_document_citation")
    if c:
        return c
    src = getattr(profile, "source_document", None)
    if src:
        return src
    code_ = getattr(profile, "country_code", "unknown")
    return f"CPD profile {code_} (document reference not stated)"


def compute_absence_record(recovery, cpd_profile, cpd_output_id: Optional[str], as_of: date) -> AbsenceRecord:
    """Pure function: arithmetic and field-copying over the recovery record
    and the institution's own CPD. Same inputs, same output, always. Total:
    every degenerate input yields a defined honest result, never a raise."""
    from recovery_ledger import RecoveryStatus

    framing = (AbsenceFraming.AT_RISK
               if recovery.status == RecoveryStatus.IDENTIFIED
               else AbsenceFraming.DEPRIVED)

    base = dict(
        absence_id=f"absence:{recovery.recovery_id}:{cpd_output_id or 'none'}",
        recovery_id=recovery.recovery_id,
        source_contract_id=recovery.source_contract_id,
        cpd_output_id=cpd_output_id,
        pillar=recovery.original_pillar,
        country_office=recovery.country_office,
        country_code=recovery.country_code,
        diverted_amount=recovery.recovery_amount,
        currency=recovery.currency,
        framing=framing,
        as_of=as_of.isoformat(),
    )

    if cpd_profile is None:
        return AbsenceRecord(**base, cpd_output_found=False,
                             duration_reason="no CPD profile available",
                             notes="no CPD profile available")
    if cpd_output_id is None:
        return AbsenceRecord(**base, cpd_output_found=False,
                             duration_reason="no CPD output id supplied",
                             notes="no CPD output id supplied")

    output = next((o for o in cpd_profile.outputs if o.output_id == cpd_output_id), None)
    if output is None:
        return AbsenceRecord(**base, cpd_output_found=False,
                             duration_reason=f"output {cpd_output_id} not found in CPD",
                             notes=f"output {cpd_output_id} not found in CPD")

    base["pillar"] = output.pillar or recovery.original_pillar
    planned_date = _get_absence_param(output, "planned_delivery_date")
    days, reason = _compute_duration(planned_date, as_of)
    return AbsenceRecord(
        **base,
        cpd_output_found=True,
        output_description=output.output_description,
        planned_capacity_description=_get_absence_param(output, "planned_capacity_description"),
        planned_beneficiaries=_get_absence_param(output, "planned_beneficiaries"),
        planned_delivery_date=planned_date,
        cpd_citation=_resolve_citation(output, cpd_profile),
        absence_duration_days=days,
        duration_reason=reason,
    )


def absence_table(record: AbsenceRecord) -> dict:
    """The single-case table, framing-gated. AT_RISK yields the at-risk
    payload with an explanatory note, never the deprived table."""
    if record.framing == AbsenceFraming.AT_RISK:
        return {
            "framing": AbsenceFraming.AT_RISK.value,
            "note": ("Diversion not yet institutionally confirmed. Planned "
                     "capacity is at risk; the full deprivation table becomes "
                     "available upon confirmation."),
            "recovery_id": record.recovery_id,
            "cpd_output_id": record.cpd_output_id,
            "diverted_amount": record.diverted_amount,
            "currency": record.currency,
            "planned_capacity_at_risk": record.planned_capacity_description,
            "cpd_citation": record.cpd_citation,
            "as_of": record.as_of,
        }
    d = asdict(record)
    d["framing"] = record.framing.value
    return d


def roll_up(records: List[AbsenceRecord]) -> dict:
    """Aggregation over absence records. Sums only CPD-stated beneficiary
    figures and reports the count of outputs stating none alongside, so the
    sum is never mistaken for a total."""
    deprived = [r for r in records if r.framing == AbsenceFraming.DEPRIVED]
    at_risk = [r for r in records if r.framing == AbsenceFraming.AT_RISK]
    stated = [r.planned_beneficiaries for r in deprived if r.planned_beneficiaries is not None]
    by_pillar: dict = {}
    for r in deprived:
        p = by_pillar.setdefault(r.pillar, {"diverted_amount": 0.0, "outputs_affected": 0})
        p["diverted_amount"] += r.diverted_amount
        p["outputs_affected"] += 1
    return {
        "confirmed_diversions": len(deprived),
        "at_risk_not_confirmed": len(at_risk),
        "total_diverted_confirmed": sum(r.diverted_amount for r in deprived),
        "stated_planned_beneficiaries_total": sum(stated),
        "outputs_with_stated_beneficiaries": len(stated),
        "outputs_without_stated_beneficiaries": len(deprived) - len(stated),
        "by_pillar": by_pillar,
    }
