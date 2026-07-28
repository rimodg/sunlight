"""
Tests for SUNLIGHT Side 4 — Redirection Records.

Covers:
    RedirectionRecord:
        - Links recovery to new contract
        - full_cycle_complete returns True only when both verdicts exist
        - full_cycle_clean returns True only when both GREEN
        - Verdict update methods work correctly
        - Multiple redirections from single recovery

    RedirectionRegistry:
        - Create and retrieve by redirection_id
        - Retrieve by target contract_id
        - List by recovery_id
        - Reset clears all state
"""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from redirection import (
    RedirectionRecord,
    RedirectionRegistry,
)


# ═══════════════════════════════════════════════════════════
# REDIRECTION RECORD TESTS
# ═══════════════════════════════════════════════════════════


class TestRedirectionRecord:
    def test_links_recovery_to_contract(self):
        record = RedirectionRecord(
            recovery_id="R001",
            target_contract_id="NEW-001",
            target_pillar="health",
            target_sdg="SDG 3",
            target_contract_value=250_000,
        )
        assert record.recovery_id == "R001"
        assert record.target_contract_id == "NEW-001"
        assert record.target_pillar == "health"
        assert record.target_sdg == "SDG 3"

    def test_full_cycle_complete_false_initially(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        assert record.full_cycle_complete is False

    def test_full_cycle_complete_false_procurement_only(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_procurement_verdict("GREEN", 0.85)
        assert record.full_cycle_complete is False

    def test_full_cycle_complete_false_delivery_only(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_delivery_verdict("GREEN")
        assert record.full_cycle_complete is False

    def test_full_cycle_complete_true_both_verdicts(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_procurement_verdict("GREEN", 0.85)
        record.update_delivery_verdict("GREEN")
        assert record.full_cycle_complete is True

    def test_full_cycle_clean_true_both_green(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_procurement_verdict("GREEN", 0.85)
        record.update_delivery_verdict("GREEN")
        assert record.full_cycle_clean is True

    def test_full_cycle_clean_false_procurement_red(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_procurement_verdict("RED", 0.90)
        record.update_delivery_verdict("GREEN")
        assert record.full_cycle_clean is False

    def test_full_cycle_clean_false_delivery_red(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_procurement_verdict("GREEN", 0.85)
        record.update_delivery_verdict("RED")
        assert record.full_cycle_clean is False

    def test_full_cycle_clean_false_incomplete(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        assert record.full_cycle_clean is False

    def test_delivery_verdict_stores_details(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        record.update_delivery_verdict(
            "GREEN", confidence=0.90,
            milestones_met=8, milestones_total=10,
            beneficiaries_reached=5000,
        )
        assert record.delivery_verdict == "GREEN"
        assert record.delivery_milestones_met == 8
        assert record.delivery_milestones_total == 10
        assert record.beneficiaries_reached == 5000

    def test_allocation_source_default(self):
        record = RedirectionRecord(recovery_id="R001", target_contract_id="NEW-001")
        assert record.allocation_source == "gap_weighted"


# ═══════════════════════════════════════════════════════════
# REDIRECTION REGISTRY TESTS
# ═══════════════════════════════════════════════════════════


class TestRedirectionRegistry:
    def test_create_and_get(self):
        registry = RedirectionRegistry()
        record = registry.create(
            recovery_id="R001",
            target_contract_id="NEW-001",
            target_pillar="health",
            target_sdg="SDG 3",
            target_contract_value=250_000,
        )
        retrieved = registry.get(record.redirection_id)
        assert retrieved is not None
        assert retrieved.target_contract_id == "NEW-001"

    def test_get_by_contract(self):
        registry = RedirectionRegistry()
        record = registry.create(
            recovery_id="R001",
            target_contract_id="NEW-001",
            target_pillar="health",
            target_sdg="SDG 3",
            target_contract_value=250_000,
        )
        by_contract = registry.get_by_contract("NEW-001")
        assert by_contract is not None
        assert by_contract.redirection_id == record.redirection_id

    def test_multiple_redirections_from_single_recovery(self):
        """Recovered funds split across multiple new contracts."""
        registry = RedirectionRegistry()
        # Created for their side effect; the assertions read them back from the registry
        registry.create("R001", "NEW-001", "health", "SDG 3", 150_000)
        registry.create("R001", "NEW-002", "education", "SDG 4", 100_000)
        registry.create("R001", "NEW-003", "governance", "SDG 16", 50_000)
        from_recovery = registry.list_by_recovery("R001")
        assert len(from_recovery) == 3
        contract_ids = {r.target_contract_id for r in from_recovery}
        assert contract_ids == {"NEW-001", "NEW-002", "NEW-003"}

    def test_list_by_recovery_empty(self):
        registry = RedirectionRegistry()
        assert len(registry.list_by_recovery("NONEXISTENT")) == 0

    def test_reset_clears_all(self):
        registry = RedirectionRegistry()
        registry.create("R001", "NEW-001", "health", "SDG 3", 250_000)
        assert len(registry.list_all()) == 1
        registry.reset()
        assert len(registry.list_all()) == 0
        assert registry.get_by_contract("NEW-001") is None
