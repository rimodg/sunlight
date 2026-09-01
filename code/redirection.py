"""
SUNLIGHT Side 4 — Redirection Records
========================================

Links recovered funds to new contracts and tracks the full
redirection lifecycle. When recovered funds are redirected to
a new contract, that new contract automatically enters Side 1
and Side 2 verification queues.

A RedirectionRecord links a RecoveryRecord to a specific new
contract funded by recovered money. Multiple redirections can
stem from a single recovery (funds split across contracts).

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: REDIRECTION RECORD
# ═══════════════════════════════════════════════════════════


@dataclass
class RedirectionRecord:
    """
    Links a recovery to a specific new contract funded by recovered money.

    The target contract enters Side 1 and Side 2 verification automatically.
    When verdicts are produced, they are recorded back on this record to
    complete the cycle traceability.
    """
    # Identity
    redirection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recovery_id: str = ""

    # Target contract
    target_sdg: str = ""
    target_pillar: str = ""
    target_output: Optional[str] = None
    target_contract_id: str = ""
    target_contract_title: str = ""
    target_contract_value: float = 0.0
    currency: str = "USD"
    redirection_date: Optional[date] = None
    allocation_source: str = "gap_weighted"

    # Side 1 results on the new contract
    procurement_verdict: Optional[str] = None
    procurement_confidence: Optional[float] = None

    # Side 2 results on the new contract
    delivery_verdict: Optional[str] = None
    delivery_confidence: Optional[float] = None
    delivery_milestones_met: Optional[int] = None
    delivery_milestones_total: Optional[int] = None
    beneficiaries_reached: Optional[int] = None

    # Reprogramming feasibility (additive, Phase 4). None means the
    # assessment has not been run; the assessor is optional and the
    # feasibility field is honest reporting, never a downrank.
    feasibility_verdict: Optional[str] = None
    feasibility_rationale: Optional[str] = None
    feasibility_threshold_usd: Optional[float] = None
    feasibility_months_min: Optional[int] = None
    feasibility_months_max: Optional[int] = None

    # Metadata
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def full_cycle_complete(self) -> bool:
        """True when both procurement and delivery verdicts exist."""
        return (
            self.procurement_verdict is not None
            and self.delivery_verdict is not None
        )

    @property
    def full_cycle_clean(self) -> bool:
        """True when procurement GREEN and delivery GREEN."""
        if not self.full_cycle_complete:
            return False
        return (
            self.procurement_verdict.upper() == "GREEN"
            and self.delivery_verdict.upper() == "GREEN"
        )

    def update_procurement_verdict(
        self, verdict: str, confidence: float = 0.0
    ) -> None:
        """Record Side 1 verdict on the target contract."""
        self.procurement_verdict = verdict
        self.procurement_confidence = confidence

    def update_delivery_verdict(
        self,
        verdict: str,
        confidence: float = 0.0,
        milestones_met: Optional[int] = None,
        milestones_total: Optional[int] = None,
        beneficiaries_reached: Optional[int] = None,
    ) -> None:
        """Record Side 2 verdict on the target contract."""
        self.delivery_verdict = verdict
        self.delivery_confidence = confidence
        self.delivery_milestones_met = milestones_met
        self.delivery_milestones_total = milestones_total
        self.beneficiaries_reached = beneficiaries_reached


# ═══════════════════════════════════════════════════════════
# SECTION 2: REDIRECTION REGISTRY
# ═══════════════════════════════════════════════════════════


class RedirectionRegistry:
    """
    In-memory registry of redirection records.

    Provides lookup by redirection_id, recovery_id, and
    target_contract_id.
    """

    def __init__(self):
        self._records: dict[str, RedirectionRecord] = {}
        self._by_recovery: dict[str, List[str]] = {}  # recovery_id → [redirection_ids]
        self._by_contract: dict[str, str] = {}  # target_contract_id → redirection_id

    def create(
        self,
        recovery_id: str,
        target_contract_id: str,
        target_pillar: str,
        target_sdg: str,
        target_contract_value: float,
        currency: str = "USD",
        target_output: Optional[str] = None,
        target_contract_title: str = "",
        allocation_source: str = "gap_weighted",
    ) -> RedirectionRecord:
        """Create a new redirection record."""
        record = RedirectionRecord(
            recovery_id=recovery_id,
            target_sdg=target_sdg,
            target_pillar=target_pillar,
            target_output=target_output,
            target_contract_id=target_contract_id,
            target_contract_title=target_contract_title,
            target_contract_value=target_contract_value,
            currency=currency,
            redirection_date=date.today(),
            allocation_source=allocation_source,
        )
        self._records[record.redirection_id] = record
        self._by_recovery.setdefault(recovery_id, []).append(record.redirection_id)
        self._by_contract[target_contract_id] = record.redirection_id
        return record

    def get(self, redirection_id: str) -> Optional[RedirectionRecord]:
        """Get a redirection record by ID."""
        return self._records.get(redirection_id)

    def get_by_contract(self, contract_id: str) -> Optional[RedirectionRecord]:
        """Get a redirection record by target contract ID."""
        rid = self._by_contract.get(contract_id)
        if rid:
            return self._records.get(rid)
        return None

    def list_by_recovery(self, recovery_id: str) -> List[RedirectionRecord]:
        """List all redirections from a single recovery."""
        rids = self._by_recovery.get(recovery_id, [])
        return [self._records[rid] for rid in rids if rid in self._records]

    def list_all(self) -> List[RedirectionRecord]:
        """List all redirection records."""
        return list(self._records.values())

    def reset(self) -> None:
        """Clear all records. For testing."""
        self._records.clear()
        self._by_recovery.clear()
        self._by_contract.clear()
