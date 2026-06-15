"""
Tests for SUNLIGHT Intelligence Alert System — Pipeline Integration.

Covers:
    AlertAssembler:
        - Procurement alert assembly with full citations
        - Delivery alert assembly
        - Combined alert (procurement RED + delivery RED)
        - GREEN verdict returns None

    AlertIntegration:
        - Disabled config returns None
        - Below threshold returns None
        - Rate limiting suppresses rapid alerts
        - on_procurement_verdict assembles and emits
        - on_delivery_verdict assembles and emits
        - on_batch_complete in brief mode emits single TriageBrief
        - on_batch_complete in individual mode emits each alert
        - Emission failure does not raise

    Pipeline Invariance:
        - Alert integration does not modify pipeline data
        - Emitter crash does not affect pipeline output

    Recovery Alerts:
        - Assembler builds recovery-type alert
        - Summary includes allocation details when provided
        - Integration emits recovery event through configured emitters
        - Disabled config returns None for recovery events
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from alerts import (
    AlertPriority,
    IntelligenceAlert,
    TriageBrief,
)
from alert_emitter import (
    AlertConfiguration,
    AlertEmitter,
    EmissionResult,
    LogEmitter,
)
from alert_integration import (
    AlertAssembler,
    AlertIntegration,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


class MockEmitter(AlertEmitter):
    """Records all emissions for test inspection."""

    def __init__(self):
        self.emissions = []

    def emit(self, payload):
        self.emissions.append(payload)
        return EmissionResult(
            success=True,
            emitter_type="MockEmitter",
            payload_id="mock",
        )


class CrashingEmitter(AlertEmitter):
    """Always raises on emit."""

    def emit(self, payload):
        raise RuntimeError("Emitter exploded")


def _procurement_rule_fires():
    return [
        {
            "rule_id": "PROC-001",
            "description": "Direct award above competitive threshold",
            "layer": "procurement",
            "confidence": 0.92,
            "legal_citations": ["FAR Part 6"],
            "evidence": "Direct award of USD 14,250,000",
        },
        {
            "rule_id": "FIN-001",
            "description": "Price deviation above peer median",
            "layer": "financial",
            "confidence": 0.87,
            "legal_citations": ["FAR Part 15.404"],
            "evidence": "Price +110.9% above median",
        },
    ]


def _delivery_rule_fires():
    return [
        {
            "rule_id": "DEL-MILE-001",
            "name": "Critical milestone delay",
            "layer": "milestone",
            "confidence": 0.85,
            "legal_basis": "UNCAC Art. 9(1)",
            "evidence": "3 milestones exceed 30-day delay tolerance",
        },
        {
            "rule_id": "DEL-FIN-001",
            "name": "Cost escalation above tolerance",
            "layer": "financial",
            "confidence": 0.80,
            "legal_basis": "UNDP Financial Regs",
            "evidence": "Budget variance 100% exceeds 25% tolerance",
        },
    ]


def _make_config(enabled=True, **kwargs):
    mock = MockEmitter()
    defaults = dict(
        enabled=enabled,
        emitters=[mock],
        min_verdict="YELLOW",
        min_confidence=0.50,
        min_dimensions=1,
        delivery_alerts_enabled=True,
        batch_mode="brief",
        max_alerts_per_hour=100,
        cooldown_seconds=0,  # No cooldown in tests
    )
    defaults.update(kwargs)
    return AlertConfiguration(**defaults), mock


# ═══════════════════════════════════════════════════════════
# ALERT ASSEMBLER TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertAssembler:
    def test_procurement_alert_has_citations(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_procurement_alert(
            contract_id="TEST-001",
            verdict="red",
            confidence=0.85,
            dimensions_fired=2,
            rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert alert is not None
        assert len(alert.rule_citations) == 2
        assert alert.rule_citations[0].rule_id == "PROC-001"
        assert alert.rule_citations[1].rule_id == "FIN-001"

    def test_procurement_alert_has_summary(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_procurement_alert(
            contract_id="TEST-001",
            verdict="red",
            confidence=0.85,
            dimensions_fired=2,
            rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert "TEST-001" in alert.summary
        assert "RED" in alert.summary

    def test_procurement_green_returns_none(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_procurement_alert(
            contract_id="TEST-001",
            verdict="green",
            confidence=0.85,
            dimensions_fired=0,
            rule_fires=[],
            profile_name="us_federal",
        )
        assert alert is None

    def test_delivery_alert_has_delivery_citations(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_delivery_alert(
            contract_id="TEST-002",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=_delivery_rule_fires(),
            profile_name="us_federal",
        )
        assert alert is not None
        assert alert.delivery_verdict == "red"
        assert len(alert.delivery_rule_citations) == 2
        assert alert.delivery_rule_citations[0].rule_id == "DEL-MILE-001"

    def test_combined_alert_type(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_delivery_alert(
            contract_id="TEST-003",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=_delivery_rule_fires(),
            profile_name="us_federal",
            procurement_verdict="red",
            procurement_confidence=0.85,
            procurement_dimensions_fired=2,
            procurement_rule_fires=_procurement_rule_fires(),
        )
        assert alert is not None
        assert alert.alert_type == "combined"
        assert alert.priority == AlertPriority.CRITICAL

    def test_delivery_only_alert_type(self):
        assembler = AlertAssembler()
        alert = assembler.assemble_delivery_alert(
            contract_id="TEST-004",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=_delivery_rule_fires(),
            profile_name="us_federal",
            procurement_verdict="green",
        )
        assert alert is not None
        assert alert.alert_type == "delivery"


# ═══════════════════════════════════════════════════════════
# ALERT INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertIntegrationProcurement:
    def test_disabled_returns_none(self):
        config, mock = _make_config(enabled=False)
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.90,
            dimensions_fired=3, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert result is None
        assert len(mock.emissions) == 0

    def test_green_verdict_no_emission(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="green", confidence=0.90,
            dimensions_fired=0, rule_fires=[],
            profile_name="us_federal",
        )
        assert result is None
        assert len(mock.emissions) == 0

    def test_below_threshold_no_emission(self):
        config, mock = _make_config(min_confidence=0.90)
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.50,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert result is None
        assert len(mock.emissions) == 0

    def test_red_verdict_emits(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert result is not None
        assert len(result) == 1
        assert result[0].success is True
        assert len(mock.emissions) == 1
        assert isinstance(mock.emissions[0], IntelligenceAlert)

    def test_emitted_alert_tracked(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert len(integration.emitted_alerts) == 1
        assert integration.emitted_alerts[0].contract_id == "C001"


class TestAlertIntegrationDelivery:
    def test_delivery_red_emits(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_delivery_verdict(
            contract_id="D001",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=_delivery_rule_fires(),
            profile_name="us_federal",
        )
        assert result is not None
        assert len(mock.emissions) == 1

    def test_delivery_disabled_no_emission(self):
        config, mock = _make_config(delivery_alerts_enabled=False)
        integration = AlertIntegration(config)
        result = integration.on_delivery_verdict(
            contract_id="D001",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=_delivery_rule_fires(),
            profile_name="us_federal",
        )
        assert result is None
        assert len(mock.emissions) == 0

    def test_delivery_green_no_emission(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_delivery_verdict(
            contract_id="D001",
            delivery_verdict="green",
            delivery_dimensions_fired=0,
            delivery_rule_fires=[],
            profile_name="us_federal",
        )
        assert result is None


class TestAlertIntegrationBatch:
    def test_brief_mode_single_emission(self):
        """Brief mode emits one TriageBrief, not N alerts."""
        config, mock = _make_config(batch_mode="brief")
        integration = AlertIntegration(config)

        alerts = []
        for i in range(5):
            a = IntelligenceAlert(
                contract_id=f"B{i}", verdict="red",
                priority=AlertPriority.HIGH, confidence=0.80,
                dimensions_fired=2,
            )
            alerts.append(a)

        result = integration.on_batch_complete(
            alerts=alerts, batch_id="BATCH-001",
            total_contracts=100, profile_name="us_federal",
        )
        assert result is not None
        # Single emission (one TriageBrief)
        assert len(mock.emissions) == 1
        assert isinstance(mock.emissions[0], TriageBrief)

    def test_individual_mode_multiple_emissions(self):
        """Individual mode emits each alert separately."""
        config, mock = _make_config(batch_mode="individual")
        integration = AlertIntegration(config)

        alerts = [
            IntelligenceAlert(
                contract_id=f"B{i}", verdict="red",
                priority=AlertPriority.HIGH, confidence=0.80,
            )
            for i in range(3)
        ]

        result = integration.on_batch_complete(
            alerts=alerts, batch_id="BATCH-002",
            total_contracts=50, profile_name="us_federal",
        )
        assert result is not None
        # 3 individual emissions
        assert len(mock.emissions) == 3

    def test_empty_batch_no_emission(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_batch_complete(
            alerts=[], batch_id="BATCH-003",
            total_contracts=50, profile_name="us_federal",
        )
        assert result is None
        assert len(mock.emissions) == 0

    def test_batch_disabled_no_emission(self):
        config, mock = _make_config(enabled=False)
        integration = AlertIntegration(config)
        alerts = [IntelligenceAlert(contract_id="B0", verdict="red")]
        result = integration.on_batch_complete(
            alerts=alerts, batch_id="BATCH-004",
            total_contracts=10, profile_name="us_federal",
        )
        assert result is None


# ═══════════════════════════════════════════════════════════
# EMISSION FAILURE ISOLATION TESTS
# ═══════════════════════════════════════════════════════════


class TestEmissionFailureIsolation:
    def test_crashing_emitter_does_not_raise(self):
        """Emitter crash produces EmissionResult with error, not exception."""
        config = AlertConfiguration(
            enabled=True,
            emitters=[CrashingEmitter()],
            min_verdict="YELLOW",
            min_confidence=0.0,
            min_dimensions=0,
            cooldown_seconds=0,
        )
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert result is not None
        assert len(result) == 1
        assert result[0].success is False
        assert "exploded" in result[0].error

    def test_mixed_emitters_partial_success(self):
        """One emitter succeeds, one crashes → both results returned."""
        mock = MockEmitter()
        config = AlertConfiguration(
            enabled=True,
            emitters=[mock, CrashingEmitter()],
            min_verdict="YELLOW",
            min_confidence=0.0,
            min_dimensions=0,
            cooldown_seconds=0,
        )
        integration = AlertIntegration(config)
        result = integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert len(result) == 2
        assert result[0].success is True  # MockEmitter
        assert result[1].success is False  # CrashingEmitter


# ═══════════════════════════════════════════════════════════
# PIPELINE INVARIANCE TESTS
# ═══════════════════════════════════════════════════════════


class TestPipelineInvariance:
    def test_rule_fires_not_modified(self):
        """Alert integration does not modify the rule_fires input."""
        rule_fires = _procurement_rule_fires()
        original = [dict(rf) for rf in rule_fires]  # deep copy

        config, mock = _make_config()
        integration = AlertIntegration(config)
        integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=rule_fires,
            profile_name="us_federal",
        )

        # rule_fires should be unchanged
        assert len(rule_fires) == len(original)
        for rf, orig in zip(rule_fires, original):
            assert rf == orig

    def test_delivery_rule_fires_not_modified(self):
        """Alert integration does not modify delivery rule_fires."""
        delivery_fires = _delivery_rule_fires()
        original = [dict(rf) for rf in delivery_fires]

        config, mock = _make_config()
        integration = AlertIntegration(config)
        integration.on_delivery_verdict(
            contract_id="D001",
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_fires=delivery_fires,
            profile_name="us_federal",
        )

        assert len(delivery_fires) == len(original)
        for rf, orig in zip(delivery_fires, original):
            assert rf == orig

    def test_reset_clears_state(self):
        config, mock = _make_config()
        integration = AlertIntegration(config)
        integration.on_procurement_verdict(
            contract_id="C001", verdict="red", confidence=0.85,
            dimensions_fired=2, rule_fires=_procurement_rule_fires(),
            profile_name="us_federal",
        )
        assert len(integration.emitted_alerts) == 1
        integration.reset()
        assert len(integration.emitted_alerts) == 0


# ═══════════════════════════════════════════════════════════
# RECOVERY ALERT TESTS
# ═══════════════════════════════════════════════════════════


class TestRecoveryAlerts:
    def test_assembler_builds_recovery_alert(self):
        """AlertAssembler produces recovery-type alert."""
        assembler = AlertAssembler()
        alert = assembler.assemble_recovery_alert(
            recovery_id="R001",
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
            source_verdict="red",
            source_confidence=0.85,
        )
        assert alert.alert_type == "recovery"
        assert alert.contract_id == "C001"
        assert alert.priority == AlertPriority.ADVISORY
        assert alert.contract_value == 500_000
        assert "500,000" in alert.summary
        assert "C001" in alert.summary
        assert "Nigeria" in alert.summary

    def test_assembler_includes_allocation_in_summary(self):
        """When allocation details provided, summary includes them."""
        assembler = AlertAssembler()
        alert = assembler.assemble_recovery_alert(
            recovery_id="R001",
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
            allocation_pillar="education",
            allocation_amount=300_000,
            target_contract_id="NEW-001",
        )
        assert "education" in alert.summary
        assert "300,000" in alert.summary
        assert "NEW-001" in alert.summary

    def test_integration_emits_recovery_event(self):
        """on_recovery_event assembles and emits through configured emitters."""
        config, mock = _make_config()
        integration = AlertIntegration(config)
        result = integration.on_recovery_event(
            recovery_id="R001",
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
            source_verdict="red",
        )
        assert result is not None
        assert len(result) == 1
        assert result[0].success is True
        assert len(mock.emissions) == 1
        assert mock.emissions[0].alert_type == "recovery"
        assert len(integration.emitted_alerts) == 1

    def test_integration_disabled_no_emission(self):
        """Disabled config returns None for recovery events."""
        config, mock = _make_config(enabled=False)
        integration = AlertIntegration(config)
        result = integration.on_recovery_event(
            recovery_id="R001",
            source_contract_id="C001",
            recovery_amount=500_000,
            currency="USD",
            country_office="Nigeria",
            country_code="NG",
            original_pillar="health",
        )
        assert result is None
        assert len(mock.emissions) == 0
