"""
SUNLIGHT Side 5 — Integration with Sides 2, 3 and 4
======================================================

The single seam where the evidence engine meets the rest of SUNLIGHT.

WHY THIS MODULE EXISTS AT ALL.
    Integration usually means each side reaching into the others. Done that
    way here, Sides 2, 3 and 4 would import Side 5, and Side 5 would stop
    being removable — which would break the one guarantee the whole build
    has been held to: with the evidence engine absent, Sides 1-4 produce
    identical output.

    So the dependency all points inward to this file. Nothing in Sides 1-4
    imports Side 5. The hooks they gained take plain strings and callables:
    RecoveryRecord.close() takes a resolver it never introspects,
    assemble_impact_report() takes a dict, compute_priority() takes a verdict
    string. This module is the only place that knows both vocabularies, and
    deleting it restores complete separation without touching anything else.

WHAT IT PROVIDES.
    claims_from_delivery_dossier() — Side 2 outcomes become Side 5 claims.
    CorroborationRegistry          — holds verdicts, hands out the resolver
                                     that Side 4's close() guard consumes.
    corroboration_summary()        — the aggregate ImpactReport carries.
    alert_payload_for()            — the arguments Side 3's hook expects.

THE FINDING THIS EXISTS TO SURFACE.
    Delivery GREEN plus corroboration CONTRADICTED. Sides 1 and 2 read
    documents produced by parties with an interest in the answer, so a clean
    procurement and delivery record is precisely what a competently executed
    false claim looks like. Every earlier gate is structurally unable to see
    it. Independent evidence is the only thing that can.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional

from evidence_schema import (
    CorroborationDossier,
    CorroborationVerdict,
    OutcomeClaim,
    OutcomeType,
)


# ═══════════════════════════════════════════════════════════
# SECTION 1: SIDE 2 — DELIVERY OUTCOMES BECOME CLAIMS
# ═══════════════════════════════════════════════════════════

# Delivery outcome units mapped to the Side 5 outcome type that determines
# which expected-evidence map applies. Unit strings are matched as
# substrings, lowercased.
#
# Where nothing matches, the outcome becomes SERVICE_DELIVERY rather than
# FACILITY_CONSTRUCTION. That default is chosen deliberately: guessing
# "facility" would invite an expected-evidence map to demand construction
# permits and satellite change detection for a training programme, and every
# one of those absences would be a manufactured finding.
_UNIT_TO_OUTCOME_TYPE = {
    "km": OutcomeType.INFRASTRUCTURE_LINEAR,
    "kilometre": OutcomeType.INFRASTRUCTURE_LINEAR,
    "kilometer": OutcomeType.INFRASTRUCTURE_LINEAR,
    "road": OutcomeType.INFRASTRUCTURE_LINEAR,
    "pipeline": OutcomeType.INFRASTRUCTURE_LINEAR,
    "transmission": OutcomeType.INFRASTRUCTURE_LINEAR,
    "bed": OutcomeType.FACILITY_CONSTRUCTION,
    "facility": OutcomeType.FACILITY_CONSTRUCTION,
    "clinic": OutcomeType.FACILITY_CONSTRUCTION,
    "hospital": OutcomeType.FACILITY_CONSTRUCTION,
    "school": OutcomeType.FACILITY_CONSTRUCTION,
    "classroom": OutcomeType.FACILITY_CONSTRUCTION,
    "borehole": OutcomeType.WATER_SANITATION,
    "latrine": OutcomeType.WATER_SANITATION,
    "water": OutcomeType.WATER_SANITATION,
    "sanitation": OutcomeType.WATER_SANITATION,
    "unit": OutcomeType.EQUIPMENT_SUPPLY,
    "equipment": OutcomeType.EQUIPMENT_SUPPLY,
    "kit": OutcomeType.EQUIPMENT_SUPPLY,
    "grant": OutcomeType.CASH_TRANSFER,
    "transfer": OutcomeType.CASH_TRANSFER,
    "household": OutcomeType.CASH_TRANSFER,
    "training": OutcomeType.CAPACITY_BUILDING,
    "workshop": OutcomeType.CAPACITY_BUILDING,
}

DEFAULT_OUTCOME_TYPE = OutcomeType.SERVICE_DELIVERY


def infer_outcome_type(unit: str = "", description: str = "") -> OutcomeType:
    """Map a delivery outcome's unit and description to a Side 5 outcome type.

    Deterministic and deliberately conservative. Unmatched outcomes become
    SERVICE_DELIVERY, whose expected-evidence maps ask for the least
    physically specific corroboration — so a wrong guess produces weaker
    expectations rather than fabricated absences.
    """
    haystack = f"{unit} {description}".lower()
    for token, outcome_type in _UNIT_TO_OUTCOME_TYPE.items():
        if token in haystack:
            return outcome_type
    return DEFAULT_OUTCOME_TYPE


def claims_from_delivery_dossier(
    delivery_dossier,
    site_latitude: Optional[float] = None,
    site_longitude: Optional[float] = None,
    award_date: Optional[date] = None,
    country_office: str = "",
) -> List[OutcomeClaim]:
    """Turn a Side 2 DeliveryDossier's outcomes into Side 5 claims.

    Duck-typed on purpose: the parameter is read, never imported. This module
    can therefore hold the only knowledge of both vocabularies without making
    Side 2 depend on Side 5.

    Reads and does not write. The delivery dossier is unchanged, and the
    claims carry its id so the link is traceable in the other direction
    without a handle on the object.

    Only outcomes with something claimed are converted. An outcome with
    nothing planned or delivered has no assertion to corroborate.
    """
    claims: List[OutcomeClaim] = []

    for outcome in getattr(delivery_dossier, "outcomes", []) or []:
        planned = getattr(outcome, "quantity_planned", 0.0) or 0.0
        delivered = getattr(outcome, "quantity_delivered", 0.0) or 0.0
        if planned <= 0 and delivered <= 0:
            continue

        unit = getattr(outcome, "unit", "") or ""
        description = getattr(outcome, "description", "") or ""

        inspection = getattr(outcome, "inspection_date", None)
        completion = _as_date(inspection)

        claims.append(OutcomeClaim(
            claim_id=f"{getattr(delivery_dossier, 'delivery_id', 'delivery')}:"
                     f"{getattr(outcome, 'outcome_id', len(claims))}",
            contract_id=getattr(delivery_dossier, "contract_id", ""),
            outcome_type=infer_outcome_type(unit, description),
            claim_description=description,
            claimed_completion_date=completion,
            # The claim under test is what was REPORTED delivered. Corroborating
            # the planned figure would test the contract, not the report.
            claimed_magnitude=delivered or planned,
            claimed_magnitude_unit=unit,
            site_latitude=site_latitude,
            site_longitude=site_longitude,
            country_code=getattr(delivery_dossier, "country_code", "") or "",
            country_office=country_office,
            award_date=award_date,
            source_dossier_id=getattr(delivery_dossier, "delivery_id", None),
        ))

    return claims


def _as_date(value) -> Optional[date]:
    """Parse a delivery record's ISO date string, or pass a date through."""
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════
# SECTION 2: SIDE 4 — THE CLOSURE GUARD
# ═══════════════════════════════════════════════════════════


class CorroborationRegistry:
    """Holds corroboration verdicts and hands out the resolver Side 4 consumes.

    RecoveryRecord.close(corroboration_resolver=...) takes a callable mapping
    a redirection id to a verdict string. It never introspects it, which is
    what lets Side 4 enforce the guarantee without importing Side 5.

    Supplying that resolver is the opt-in: without one, close() behaves
    exactly as it did before the evidence engine existed.
    """

    def __init__(self):
        self._by_redirection: Dict[str, CorroborationDossier] = {}

    def register(self, redirection_id: str, dossier: CorroborationDossier) -> None:
        """Attach a corroboration dossier to a redirection."""
        self._by_redirection[redirection_id] = dossier

    def get(self, redirection_id: str) -> Optional[CorroborationDossier]:
        return self._by_redirection.get(redirection_id)

    def verdict_for(self, redirection_id: str) -> Optional[str]:
        """The verdict as a lowercase string, or None when nothing is registered.

        None is the honest answer for an unregistered redirection and blocks
        closure. Returning a permissive default would let a cycle close on an
        outcome nobody ever looked at, which is the precise failure the guard
        exists to prevent.
        """
        dossier = self._by_redirection.get(redirection_id)
        if dossier is None or dossier.verdict is None:
            return None
        return dossier.verdict.value

    def resolver(self) -> Callable[[str], Optional[str]]:
        """The callable to pass to RecoveryRecord.close()."""
        return self.verdict_for

    def dossiers(self) -> List[CorroborationDossier]:
        return list(self._by_redirection.values())

    def __len__(self) -> int:
        return len(self._by_redirection)


# ═══════════════════════════════════════════════════════════
# SECTION 3: SIDE 4 — THE IMPACT REPORT AGGREGATE
# ═══════════════════════════════════════════════════════════


def corroboration_summary(
    dossiers: Iterable[CorroborationDossier],
) -> Dict[str, Any]:
    """Aggregate corroboration verdicts for an ImpactReport.

    Returns the plain dict assemble_impact_report() accepts, so Side 4 needs
    no Side 5 import.

    unverified is counted SEPARATELY from contradicted and the two are never
    summed anywhere downstream. They mean opposite things — evidence we could
    not reach against evidence that conflicts — and a portfolio view that
    merged them would report a pattern of contradicted claims in exactly the
    country offices whose registries are thinnest.

    average_corroboration_capacity is included because the other four numbers
    cannot be read without it. Ten unverified outcomes at 20% capacity is a
    statement about the country's data infrastructure; ten at 100% is a
    statement about the evidence for those claims.
    """
    counts = {v: 0 for v in CorroborationVerdict}
    capacity_total = 0.0
    n = 0

    for dossier in dossiers:
        n += 1
        capacity_total += dossier.corroboration_capacity
        if dossier.verdict is not None:
            counts[dossier.verdict] += 1

    return {
        "corroborated_outcomes": counts[CorroborationVerdict.VERIFIED],
        "partially_corroborated_outcomes": counts[CorroborationVerdict.PARTIAL],
        "unverified_outcomes": counts[CorroborationVerdict.UNVERIFIED],
        "contradicted_outcomes": counts[CorroborationVerdict.CONTRADICTED],
        "average_corroboration_capacity": round(capacity_total / n, 4) if n else 0.0,
        "outcomes_assessed": n,
    }


# ═══════════════════════════════════════════════════════════
# SECTION 4: SIDE 3 — THE ALERT PAYLOAD
# ═══════════════════════════════════════════════════════════


def alert_payload_for(
    dossier: CorroborationDossier,
    profile_name: str = "",
    delivery_verdict: str = "green",
    procurement_verdict: str = "green",
    procurement_confidence: float = 0.0,
    procurement_dimensions_fired: int = 0,
    **extra,
) -> Dict[str, Any]:
    """Build the arguments AlertIntegration.on_corroboration_verdict() expects.

    Everything crosses as strings, floats and plain dicts, so Side 3 stays
    free of Side 5 types.
    """
    rule_fires = []
    if dossier.rules_result is not None:
        rule_fires = [
            {
                "rule_id": r.rule_id,
                "layer": r.layer,
                "description": r.detail,
                "confidence": r.confidence,
                "legal_basis": r.legal_basis,
                "evidence": r.evidence,
                "recommendation": r.recommendation,
            }
            for r in dossier.rules_result.rule_results
            if r.fired
        ]

    payload = {
        "contract_id": dossier.claim.contract_id,
        "corroboration_verdict": dossier.verdict.value if dossier.verdict else "",
        "corroboration_confidence": dossier.confidence,
        "corroboration_capacity": dossier.corroboration_capacity,
        "rule_fires": rule_fires,
        "profile_name": profile_name,
        "claim_description": dossier.claim.claim_description,
        "country_code": dossier.claim.country_code or "",
        "delivery_verdict": delivery_verdict,
        "procurement_verdict": procurement_verdict,
        "procurement_confidence": procurement_confidence,
        "procurement_dimensions_fired": procurement_dimensions_fired,
    }
    payload.update(extra)
    return payload


def is_highest_value_finding(
    dossier: CorroborationDossier,
    delivery_verdict: str = "",
    procurement_verdict: str = "",
) -> bool:
    """Clean paperwork at every stage, contradicted by independent evidence.

    The single most valuable output SUNLIGHT can produce, and the one no
    documentary review can reach: Sides 1 and 2 read records produced by
    parties with an interest in the answer, so a clean procurement and
    delivery file is exactly what a competently executed false claim
    produces.
    """
    return (
        dossier.verdict == CorroborationVerdict.CONTRADICTED
        and (delivery_verdict or "").lower() == "green"
        and (procurement_verdict or "").lower() == "green"
    )
