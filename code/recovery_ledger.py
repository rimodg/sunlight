"""
SUNLIGHT Side 4 — Recovery Intelligence Ledger
=================================================

Tracks what was intercepted by Side 1 and what happened to it.
The recovery lifecycle follows the same state-machine pattern as
DeliveryDossier from Side 2: status progresses through defined
stages, each transition validated.

State Machine:
    IDENTIFIED → CONFIRMED → RECOVERED → REDIRECTED → REDEPLOYED → VERIFIED → CLOSED

Critical design constraint:
    - Does NOT modify Side 1, Side 2, or Side 3 output.
    - Purely additive. If the recovery system is disabled or absent,
      all other pipelines produce identical results.
    - Every detection remains a risk indicator, not an allegation.
    - Every allocation remains a recommendation, not a directive.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: ENUMERATIONS
# ═══════════════════════════════════════════════════════════


class RecoveryStatus(Enum):
    """Recovery lifecycle status.

    State machine progression:
        IDENTIFIED  — Side 1 flagged RED, awaiting institutional action
        CONFIRMED   — Institution confirmed cancellation or modification
        RECOVERED   — Funds returned to budget pool
        REDIRECTED  — Allocation recommendation generated
        REDEPLOYED  — New contract(s) issued with recovered funds
        VERIFIED    — Side 2 confirmed delivery on redeployed contracts
        CLOSED      — Full cycle complete, impact report generated
    """
    IDENTIFIED = "identified"
    CONFIRMED = "confirmed"
    RECOVERED = "recovered"
    REDIRECTED = "redirected"
    REDEPLOYED = "redeployed"
    VERIFIED = "verified"
    CLOSED = "closed"


# Valid state transitions — each status maps to the set of statuses
# it can transition to. Any transition not in this map is rejected.
_VALID_TRANSITIONS = {
    RecoveryStatus.IDENTIFIED: {RecoveryStatus.CONFIRMED},
    RecoveryStatus.CONFIRMED: {RecoveryStatus.RECOVERED},
    RecoveryStatus.RECOVERED: {RecoveryStatus.REDIRECTED},
    RecoveryStatus.REDIRECTED: {RecoveryStatus.REDEPLOYED},
    RecoveryStatus.REDEPLOYED: {RecoveryStatus.VERIFIED},
    RecoveryStatus.VERIFIED: {RecoveryStatus.CLOSED},
    RecoveryStatus.CLOSED: set(),  # terminal state
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class UncorroboratedClosureError(Exception):
    """Raised when a cycle is closed on claims independent evidence has not supported.

    Distinct from InvalidTransitionError: the transition is legal, the
    evidence is not. Closing a recovery cycle is the moment SUNLIGHT asserts
    that recovered money produced a real outcome, and that assertion is only
    as good as the corroboration behind it.
    """
    pass


# Corroboration verdicts that permit a cycle to close.
#
# VERIFIED and PARTIAL both mean independent evidence is consistent with the
# claim. UNVERIFIED and CONTRADICTED do not, for opposite reasons — one
# because the evidence could not be reached, the other because it conflicts —
# and neither supports declaring the loop closed.
#
# Held as lowercase strings rather than imported from evidence_schema on
# purpose: Side 4 must not depend on Side 5, or Side 5 stops being removable.
CLOSURE_PERMITTING_VERDICTS = frozenset({"verified", "partial"})


# ═══════════════════════════════════════════════════════════
# SECTION 2: RECOVERY RECORD
# ═══════════════════════════════════════════════════════════


@dataclass
class RecoveryRecord:
    """
    Tracks a single recovery from RED-flagged contract through
    fund redirection, redeployment, and delivery verification.

    One RecoveryRecord per flagged contract that the institution
    acts on. Links to RedirectionRecords via redirections list.
    """
    # Identity
    recovery_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Source contract (the RED-flagged contract)
    source_contract_id: str = ""
    source_verdict: str = "red"
    source_confidence: float = 0.0
    source_rule_fires: List[str] = field(default_factory=list)

    # Recovery details
    recovery_amount: float = 0.0
    currency: str = "USD"
    country_office: str = ""
    country_code: str = ""
    original_pillar: str = ""
    original_sdg: Optional[str] = None

    # Dates
    identification_date: Optional[date] = None
    confirmation_date: Optional[date] = None
    recovery_date: Optional[date] = None

    # State
    status: RecoveryStatus = RecoveryStatus.IDENTIFIED

    # Linked redirections
    redirections: List[str] = field(default_factory=list)

    # Linked absence record (Absence Ledger growth, additive)
    absence_id: Optional[str] = None

    # Metadata
    notes: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = ""

    def _transition(self, target: RecoveryStatus) -> None:
        """Validate and execute a state transition."""
        valid = _VALID_TRANSITIONS.get(self.status, set())
        if target not in valid:
            raise InvalidTransitionError(
                f"Cannot transition from {self.status.value} to {target.value}. "
                f"Valid transitions from {self.status.value}: "
                f"{', '.join(s.value for s in valid) if valid else 'none (terminal state)'}"
            )
        self.status = target
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def confirm(self, confirmation_date: date) -> None:
        """Institution confirms the contract cancellation/modification."""
        self._transition(RecoveryStatus.CONFIRMED)
        self.confirmation_date = confirmation_date

    def mark_recovered(self, recovery_date: date) -> None:
        """Funds confirmed returned to budget pool."""
        self._transition(RecoveryStatus.RECOVERED)
        self.recovery_date = recovery_date

    def mark_redirected(self) -> None:
        """Allocation recommendation generated."""
        self._transition(RecoveryStatus.REDIRECTED)

    def mark_redeployed(self) -> None:
        """New contracts issued with recovered funds."""
        self._transition(RecoveryStatus.REDEPLOYED)

    def mark_verified(self) -> None:
        """Side 2 confirmed delivery on redeployed contracts."""
        self._transition(RecoveryStatus.VERIFIED)

    def close(self, corroboration_resolver=None) -> None:
        """Full cycle complete.

        Args:
            corroboration_resolver: optional callable taking a redirection id
                and returning that redirection's corroboration verdict as a
                string ("verified" / "partial" / "unverified" /
                "contradicted"), or None when no corroboration exists.

        Behaviour is deliberately split:

            No resolver — identical to the behaviour before Side 5 existed.
                This is what keeps Side 5 purely additive: with the evidence
                engine absent or disabled, Side 4 produces exactly the output
                it always did, and no existing caller breaks.

            Resolver supplied — every linked redirection must resolve to
                VERIFIED or PARTIAL. Supplying a resolver is how a deployment
                opts into the stronger guarantee: that the loop cannot be
                declared closed on claims independent evidence has not
                supported. This is what makes the impact report defensible.

        A record with no redirections closes either way. Nothing was
        redeployed, so there is no outcome claim to corroborate.

        Raises:
            InvalidTransitionError: if the record is not at VERIFIED.
            UncorroboratedClosureError: if a resolver is supplied and any
                redirection lacks a supporting corroboration verdict.
        """
        if corroboration_resolver is not None:
            self._require_corroboration(corroboration_resolver)
        self._transition(RecoveryStatus.CLOSED)

    def _require_corroboration(self, resolver) -> None:
        """Check every redirection has a corroboration verdict that permits closure."""
        blocking = []
        for redirection_id in self.redirections:
            try:
                verdict = resolver(redirection_id)
            except Exception as e:  # noqa: BLE001 — a failing resolver blocks, never passes
                blocking.append((redirection_id, f"resolver error: {e}"))
                continue

            if verdict is None:
                blocking.append((redirection_id, "no corroboration on record"))
                continue

            normalised = str(getattr(verdict, "value", verdict)).lower()
            if normalised not in CLOSURE_PERMITTING_VERDICTS:
                blocking.append((redirection_id, normalised))

        if blocking:
            detail = "; ".join(f"{rid}: {reason}" for rid, reason in blocking)
            raise UncorroboratedClosureError(
                f"Recovery {self.recovery_id} cannot close: "
                f"{len(blocking)} of {len(self.redirections)} redirection(s) "
                f"lack a corroboration verdict of "
                f"{' or '.join(sorted(CLOSURE_PERMITTING_VERDICTS))} — {detail}. "
                f"A cycle declared closed on uncorroborated outcomes asserts "
                f"an impact the evidence does not support."
            )


# ═══════════════════════════════════════════════════════════
# SECTION 3: RECOVERY LEDGER
# ═══════════════════════════════════════════════════════════


class RecoveryLedger:
    """
    In-memory registry of recovery records.

    Provides lookup by recovery_id and source_contract_id.
    Production deployments will back this with a database;
    the in-memory version is sufficient for API testing and
    single-session operation.
    """

    def __init__(self):
        self._records: dict[str, RecoveryRecord] = {}
        self._by_contract: dict[str, str] = {}  # contract_id → recovery_id

    def create(
        self,
        source_contract_id: str,
        recovery_amount: float,
        currency: str,
        country_office: str,
        country_code: str,
        original_pillar: str,
        source_verdict: str = "red",
        source_confidence: float = 0.0,
        source_rule_fires: Optional[List[str]] = None,
        original_sdg: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> RecoveryRecord:
        """Create a new recovery record at IDENTIFIED status."""
        record = RecoveryRecord(
            source_contract_id=source_contract_id,
            source_verdict=source_verdict,
            source_confidence=source_confidence,
            source_rule_fires=source_rule_fires or [],
            recovery_amount=recovery_amount,
            currency=currency,
            country_office=country_office,
            country_code=country_code,
            original_pillar=original_pillar,
            original_sdg=original_sdg,
            identification_date=date.today(),
            notes=notes,
        )
        self._records[record.recovery_id] = record
        self._by_contract[source_contract_id] = record.recovery_id
        return record

    def get(self, recovery_id: str) -> Optional[RecoveryRecord]:
        """Get a recovery record by ID."""
        return self._records.get(recovery_id)

    def get_by_contract(self, contract_id: str) -> Optional[RecoveryRecord]:
        """Get a recovery record by source contract ID."""
        rid = self._by_contract.get(contract_id)
        if rid:
            return self._records.get(rid)
        return None

    def list_all(self) -> List[RecoveryRecord]:
        """List all recovery records."""
        return list(self._records.values())

    def list_by_status(self, status: RecoveryStatus) -> List[RecoveryRecord]:
        """List recovery records filtered by status."""
        return [r for r in self._records.values() if r.status == status]

    def list_by_country(self, country_office: str) -> List[RecoveryRecord]:
        """List recovery records for a country office."""
        return [r for r in self._records.values() if r.country_office == country_office]

    @property
    def total_recovered(self) -> float:
        """Total amount across all records past RECOVERED status."""
        recoverable = {
            RecoveryStatus.RECOVERED,
            RecoveryStatus.REDIRECTED,
            RecoveryStatus.REDEPLOYED,
            RecoveryStatus.VERIFIED,
            RecoveryStatus.CLOSED,
        }
        return sum(
            r.recovery_amount
            for r in self._records.values()
            if r.status in recoverable
        )

    def reset(self) -> None:
        """Clear all records. For testing."""
        self._records.clear()
        self._by_contract.clear()
