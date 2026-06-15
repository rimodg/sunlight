"""
Tests for SUNLIGHT Side 4 — Recovery Intelligence Ledger.

Covers:
    RecoveryRecord:
        - Creation with correct initial status IDENTIFIED
        - State machine progression: IDENTIFIED → CONFIRMED → RECOVERED →
          REDIRECTED → REDEPLOYED → VERIFIED → CLOSED
        - Invalid state transitions rejected
        - Recovery linked to source contract RED verdict
        - Dates recorded on transitions
        - Updated_at set on each transition

    RecoveryLedger:
        - Create and retrieve by recovery_id
        - Retrieve by source contract_id
        - List all, list by status, list by country
        - Total recovered amount computation
        - Reset clears all state
"""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from recovery_ledger import (
    RecoveryStatus,
    RecoveryRecord,
    RecoveryLedger,
    InvalidTransitionError,
)


# ═══════════════════════════════════════════════════════════
# RECOVERY RECORD TESTS
# ═══════════════════════════════════════════════════════════


class TestRecoveryRecordCreation:
    def test_default_status_is_identified(self):
        record = RecoveryRecord(source_contract_id="C001")
        assert record.status == RecoveryStatus.IDENTIFIED

    def test_recovery_id_generated(self):
        record = RecoveryRecord(source_contract_id="C001")
        assert len(record.recovery_id) > 0

    def test_two_records_have_unique_ids(self):
        r1 = RecoveryRecord(source_contract_id="C001")
        r2 = RecoveryRecord(source_contract_id="C002")
        assert r1.recovery_id != r2.recovery_id

    def test_source_verdict_stored(self):
        record = RecoveryRecord(
            source_contract_id="C001",
            source_verdict="red",
            source_confidence=0.85,
            source_rule_fires=["PROC-001", "FIN-001"],
        )
        assert record.source_verdict == "red"
        assert record.source_confidence == 0.85
        assert record.source_rule_fires == ["PROC-001", "FIN-001"]

    def test_created_at_populated(self):
        record = RecoveryRecord(source_contract_id="C001")
        assert len(record.created_at) > 0


class TestRecoveryStateMachine:
    def test_full_lifecycle(self):
        """IDENTIFIED → CONFIRMED → RECOVERED → REDIRECTED → REDEPLOYED → VERIFIED → CLOSED."""
        record = RecoveryRecord(source_contract_id="C001")
        assert record.status == RecoveryStatus.IDENTIFIED

        record.confirm(date(2026, 1, 15))
        assert record.status == RecoveryStatus.CONFIRMED
        assert record.confirmation_date == date(2026, 1, 15)

        record.mark_recovered(date(2026, 2, 1))
        assert record.status == RecoveryStatus.RECOVERED
        assert record.recovery_date == date(2026, 2, 1)

        record.mark_redirected()
        assert record.status == RecoveryStatus.REDIRECTED

        record.mark_redeployed()
        assert record.status == RecoveryStatus.REDEPLOYED

        record.mark_verified()
        assert record.status == RecoveryStatus.VERIFIED

        record.close()
        assert record.status == RecoveryStatus.CLOSED

    def test_invalid_identified_to_verified(self):
        record = RecoveryRecord(source_contract_id="C001")
        with pytest.raises(InvalidTransitionError):
            record.mark_verified()

    def test_invalid_identified_to_recovered(self):
        record = RecoveryRecord(source_contract_id="C001")
        with pytest.raises(InvalidTransitionError):
            record.mark_recovered(date(2026, 1, 1))

    def test_invalid_identified_to_closed(self):
        record = RecoveryRecord(source_contract_id="C001")
        with pytest.raises(InvalidTransitionError):
            record.close()

    def test_invalid_confirmed_to_redirected(self):
        """Must go through RECOVERED before REDIRECTED."""
        record = RecoveryRecord(source_contract_id="C001")
        record.confirm(date(2026, 1, 15))
        with pytest.raises(InvalidTransitionError):
            record.mark_redirected()

    def test_closed_is_terminal(self):
        record = RecoveryRecord(source_contract_id="C001")
        record.confirm(date(2026, 1, 15))
        record.mark_recovered(date(2026, 2, 1))
        record.mark_redirected()
        record.mark_redeployed()
        record.mark_verified()
        record.close()
        with pytest.raises(InvalidTransitionError):
            record.confirm(date(2026, 3, 1))

    def test_updated_at_set_on_transition(self):
        record = RecoveryRecord(source_contract_id="C001")
        assert record.updated_at == ""
        record.confirm(date(2026, 1, 15))
        assert len(record.updated_at) > 0

    def test_invalid_transition_error_message(self):
        record = RecoveryRecord(source_contract_id="C001")
        with pytest.raises(InvalidTransitionError, match="identified.*verified"):
            record.mark_verified()


# ═══════════════════════════════════════════════════════════
# RECOVERY LEDGER TESTS
# ═══════════════════════════════════════════════════════════


class TestRecoveryLedger:
    def test_create_and_get(self):
        ledger = RecoveryLedger()
        record = ledger.create(
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
        )
        assert record.status == RecoveryStatus.IDENTIFIED
        retrieved = ledger.get(record.recovery_id)
        assert retrieved is not None
        assert retrieved.source_contract_id == "C001"

    def test_get_by_contract(self):
        ledger = RecoveryLedger()
        record = ledger.create(
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
        )
        by_contract = ledger.get_by_contract("C001")
        assert by_contract is not None
        assert by_contract.recovery_id == record.recovery_id

    def test_get_missing_returns_none(self):
        ledger = RecoveryLedger()
        assert ledger.get("nonexistent") is None
        assert ledger.get_by_contract("nonexistent") is None

    def test_list_all(self):
        ledger = RecoveryLedger()
        ledger.create("C001", 100_000, "USD", "Nigeria", "NG", "health")
        ledger.create("C002", 200_000, "USD", "Ukraine", "UA", "governance")
        assert len(ledger.list_all()) == 2

    def test_list_by_status(self):
        ledger = RecoveryLedger()
        r1 = ledger.create("C001", 100_000, "USD", "Nigeria", "NG", "health")
        ledger.create("C002", 200_000, "USD", "Ukraine", "UA", "governance")
        r1.confirm(date(2026, 1, 15))
        assert len(ledger.list_by_status(RecoveryStatus.IDENTIFIED)) == 1
        assert len(ledger.list_by_status(RecoveryStatus.CONFIRMED)) == 1

    def test_list_by_country(self):
        ledger = RecoveryLedger()
        ledger.create("C001", 100_000, "USD", "Nigeria", "NG", "health")
        ledger.create("C002", 200_000, "USD", "Nigeria", "NG", "governance")
        ledger.create("C003", 300_000, "USD", "Ukraine", "UA", "energy")
        assert len(ledger.list_by_country("Nigeria")) == 2
        assert len(ledger.list_by_country("Ukraine")) == 1

    def test_total_recovered(self):
        ledger = RecoveryLedger()
        r1 = ledger.create("C001", 100_000, "USD", "Nigeria", "NG", "health")
        r2 = ledger.create("C002", 200_000, "USD", "Ukraine", "UA", "governance")
        # Only IDENTIFIED — not yet recovered
        assert ledger.total_recovered == 0
        # Move r1 through to RECOVERED
        r1.confirm(date(2026, 1, 15))
        r1.mark_recovered(date(2026, 2, 1))
        assert ledger.total_recovered == 100_000
        # Move r2 through to RECOVERED
        r2.confirm(date(2026, 1, 20))
        r2.mark_recovered(date(2026, 2, 5))
        assert ledger.total_recovered == 300_000

    def test_reset_clears_all(self):
        ledger = RecoveryLedger()
        ledger.create("C001", 100_000, "USD", "Nigeria", "NG", "health")
        assert len(ledger.list_all()) == 1
        ledger.reset()
        assert len(ledger.list_all()) == 0
        assert ledger.get_by_contract("C001") is None
