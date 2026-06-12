"""
Tests for SUNLIGHT Side 2 delivery verification schema.

Covers:
    - DeliveryDossier construction, defaults, advance/fail state machine
    - Computed properties (delayed_milestones, budget_variance_pct, staffing_gap_ratio, etc.)
    - All four input record types (Milestone, ResourceRecord, OutcomeRecord, FinancialRecord)
    - All enum values for DeliveryStage, DeliveryVerdict, DeliveryDimension, DeliveryRuleLayer
    - Result dataclasses (DeliveryRuleResult, DeliveryGraphResult, DeliveryRulesResult,
      DeliveryDimensionResult, DeliveryGateOutcome)
    - Edge cases: empty inputs, zero denominators, boundary values
"""

import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from delivery_schema import (
    # Enums
    DeliveryStage,
    DeliveryVerdict,
    DeliveryDimension,
    DeliveryRuleLayer,
    # Input records
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
    # Result dataclasses
    DeliveryRuleResult,
    DeliveryGraphResult,
    DeliveryRulesResult,
    DeliveryDimensionResult,
    DeliveryGateOutcome,
    # The atom
    DeliveryDossier,
)


# ═══════════════════════════════════════════════════════════
# ENUM TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryStage:
    def test_all_stages_exist(self):
        stages = {s.value for s in DeliveryStage}
        assert "delivery_ingested" in stages
        assert "delivery_graphed" in stages
        assert "delivery_rules_evaluated" in stages
        assert "delivery_gated" in stages
        assert "delivery_complete" in stages
        assert "delivery_failed" in stages

    def test_stage_count(self):
        assert len(DeliveryStage) == 6


class TestDeliveryVerdict:
    def test_all_verdicts_exist(self):
        assert DeliveryVerdict.GREEN.value == "green"
        assert DeliveryVerdict.YELLOW.value == "yellow"
        assert DeliveryVerdict.RED.value == "red"

    def test_verdict_count(self):
        assert len(DeliveryVerdict) == 3


class TestDeliveryDimension:
    def test_all_dimensions_exist(self):
        dims = {d.value for d in DeliveryDimension}
        assert "milestone_compliance" in dims
        assert "resource_verification" in dims
        assert "outcome_verification" in dims
        assert "financial_reconciliation" in dims

    def test_dimension_count(self):
        assert len(DeliveryDimension) == 4


class TestDeliveryRuleLayer:
    def test_all_layers_exist(self):
        layers = {l.value for l in DeliveryRuleLayer}
        assert "milestone" in layers
        assert "resource" in layers
        assert "outcome" in layers
        assert "financial" in layers

    def test_layer_count(self):
        assert len(DeliveryRuleLayer) == 4


# ═══════════════════════════════════════════════════════════
# INPUT RECORD TESTS
# ═══════════════════════════════════════════════════════════


class TestMilestone:
    def test_construction_minimal(self):
        m = Milestone(milestone_id="M1", description="Phase 1 delivery")
        assert m.milestone_id == "M1"
        assert m.description == "Phase 1 delivery"
        assert m.delay_days == 0
        assert m.status == ""
        assert m.planned_date is None
        assert m.actual_date is None

    def test_construction_full(self):
        m = Milestone(
            milestone_id="M2",
            description="Final inspection",
            planned_date="2025-06-01",
            actual_date="2025-07-15",
            status="delayed",
            delay_days=44,
            deliverables_due=3,
            deliverables_accepted=1,
        )
        assert m.delay_days == 44
        assert m.deliverables_due == 3
        assert m.deliverables_accepted == 1
        assert m.status == "delayed"


class TestResourceRecord:
    def test_construction_defaults(self):
        r = ResourceRecord(resource_id="R1", role="engineer")
        assert r.planned_fte == 0.0
        assert r.actual_fte == 0.0
        assert r.qualification_verified is False

    def test_construction_full(self):
        r = ResourceRecord(
            resource_id="R2",
            role="project_manager",
            planned_fte=1.0,
            actual_fte=0.5,
            qualification_required="PMP",
            qualification_verified=True,
            period_start="2025-01-01",
            period_end="2025-12-31",
        )
        assert r.actual_fte == 0.5
        assert r.qualification_verified is True


class TestOutcomeRecord:
    def test_construction_defaults(self):
        o = OutcomeRecord(outcome_id="O1", description="Road segment A")
        assert o.quantity_planned == 0.0
        assert o.quantity_delivered == 0.0
        assert o.quality_score is None

    def test_construction_full(self):
        o = OutcomeRecord(
            outcome_id="O2",
            description="Bridge construction",
            unit="meters",
            quantity_planned=100.0,
            quantity_delivered=75.0,
            quality_score=0.85,
            inspection_date="2025-09-01",
            inspector_id="INS-42",
            defects_noted=2,
        )
        assert o.quantity_delivered == 75.0
        assert o.defects_noted == 2


class TestFinancialRecord:
    def test_construction_defaults(self):
        f = FinancialRecord(line_item_id="F1", description="Materials")
        assert f.budgeted_amount == 0.0
        assert f.actual_amount == 0.0
        assert f.currency == "USD"

    def test_construction_full(self):
        f = FinancialRecord(
            line_item_id="F2",
            description="Labour costs",
            budgeted_amount=500000.0,
            actual_amount=650000.0,
            currency="EUR",
            variance_pct=30.0,
            amendment_count=3,
            justification="Scope expansion approved",
        )
        assert f.variance_pct == 30.0
        assert f.amendment_count == 3


# ═══════════════════════════════════════════════════════════
# RESULT DATACLASS TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryRuleResult:
    def test_construction(self):
        r = DeliveryRuleResult(
            rule_id="DEL-MILE-001",
            layer="milestone",
            fired=True,
            evidence="Deadline exceeded by 60 days",
            legal_basis="FAR 52.211-12",
            confidence=0.85,
        )
        assert r.rule_id == "DEL-MILE-001"
        assert r.fired is True
        assert r.confidence == 0.85

    def test_defaults(self):
        r = DeliveryRuleResult(rule_id="DEL-RES-001", layer="resource", fired=False)
        assert r.evidence == ""
        assert r.legal_basis == ""
        assert r.confidence == 0.0


class TestDeliveryGraphResult:
    def test_defaults(self):
        g = DeliveryGraphResult()
        assert g.node_count == 0
        assert g.edge_count == 0
        assert g.nodes == []
        assert g.edges == []

    def test_construction(self):
        g = DeliveryGraphResult(
            node_count=5,
            edge_count=8,
            nodes=[{"id": "n1"}],
            edges=[{"src": "n1", "dst": "n2"}],
        )
        assert g.node_count == 5
        assert len(g.nodes) == 1


class TestDeliveryRulesResult:
    def test_defaults(self):
        r = DeliveryRulesResult()
        assert r.rules_evaluated == 0
        assert r.rules_fired == 0
        assert r.rule_results == []

    def test_construction(self):
        rule1 = DeliveryRuleResult(rule_id="DEL-MILE-001", layer="milestone", fired=True)
        rule2 = DeliveryRuleResult(rule_id="DEL-MILE-002", layer="milestone", fired=False)
        r = DeliveryRulesResult(
            rules_evaluated=2,
            rules_fired=1,
            rule_results=[rule1, rule2],
            layer_summary={"milestone": 1},
        )
        assert r.rules_evaluated == 2
        assert r.rules_fired == 1
        assert len(r.rule_results) == 2


class TestDeliveryDimensionResult:
    def test_construction(self):
        d = DeliveryDimensionResult(
            dimension=DeliveryDimension.MILESTONE_COMPLIANCE,
            fired=True,
            observed_value=0.6,
            threshold=0.8,
            detail="60% milestone compliance < 80% threshold",
        )
        assert d.fired is True
        assert d.observed_value == 0.6

    def test_defaults(self):
        d = DeliveryDimensionResult(
            dimension=DeliveryDimension.FINANCIAL_RECONCILIATION,
            fired=False,
        )
        assert d.observed_value is None
        assert d.threshold is None
        assert d.detail == ""


class TestDeliveryGateOutcome:
    def test_green(self):
        g = DeliveryGateOutcome(
            verdict=DeliveryVerdict.GREEN,
            dimensions_fired=0,
        )
        assert g.verdict == DeliveryVerdict.GREEN
        assert g.dimension_results == []

    def test_red(self):
        dims = [
            DeliveryDimensionResult(
                dimension=DeliveryDimension.MILESTONE_COMPLIANCE,
                fired=True,
            ),
            DeliveryDimensionResult(
                dimension=DeliveryDimension.FINANCIAL_RECONCILIATION,
                fired=True,
            ),
        ]
        g = DeliveryGateOutcome(
            verdict=DeliveryVerdict.RED,
            dimensions_fired=2,
            dimension_results=dims,
        )
        assert g.dimensions_fired == 2


# ═══════════════════════════════════════════════════════════
# DELIVERY DOSSIER TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryDossierConstruction:
    def test_default_construction(self):
        d = DeliveryDossier()
        # Identity defaults
        assert len(d.delivery_id) == 36  # UUID format
        assert d.contract_id == ""
        assert d.country_code == ""
        # Stage defaults
        assert d.stage == DeliveryStage.INGESTED
        # Collections empty
        assert d.milestones == []
        assert d.resources == []
        assert d.outcomes == []
        assert d.financials == []
        # Engine results None
        assert d.graph is None
        assert d.rules_result is None
        assert d.gate_outcome is None
        # Provenance
        assert "Side 2" in d.methodology_version
        assert d.disclaimer != ""

    def test_construction_with_contract_link(self):
        d = DeliveryDossier(
            contract_id="CONTRACT-123",
            country_code="BF",
            country_name="Burkina Faso",
            project_name="Road Rehabilitation Phase II",
            procurement_verdict="YELLOW",
        )
        assert d.contract_id == "CONTRACT-123"
        assert d.country_code == "BF"
        assert d.procurement_verdict == "YELLOW"

    def test_unique_delivery_ids(self):
        d1 = DeliveryDossier()
        d2 = DeliveryDossier()
        assert d1.delivery_id != d2.delivery_id

    def test_created_at_populated(self):
        d = DeliveryDossier()
        assert d.created_at != ""
        assert "T" in d.created_at  # ISO format check


class TestDeliveryDossierStateMachine:
    def test_advance(self):
        d = DeliveryDossier()
        assert d.stage == DeliveryStage.INGESTED

        d.advance(DeliveryStage.GRAPHED, duration_ms=50.0)
        assert d.stage == DeliveryStage.GRAPHED
        assert d.updated_at != ""
        assert d.processing_ms["delivery_graphed"] == 50.0

    def test_advance_all_stages(self):
        d = DeliveryDossier()
        stages = [
            DeliveryStage.GRAPHED,
            DeliveryStage.RULES_EVALUATED,
            DeliveryStage.GATED,
            DeliveryStage.COMPLETE,
        ]
        for stage in stages:
            d.advance(stage, duration_ms=10.0)
            assert d.stage == stage
        assert len(d.processing_ms) == 4

    def test_advance_zero_duration_not_recorded(self):
        d = DeliveryDossier()
        d.advance(DeliveryStage.GRAPHED, duration_ms=0)
        assert "delivery_graphed" not in d.processing_ms

    def test_fail(self):
        d = DeliveryDossier()
        d.fail(DeliveryStage.RULES_EVALUATED, "Rule engine timeout")
        assert d.stage == DeliveryStage.FAILED
        assert len(d.errors) == 1
        assert d.errors[0]["stage"] == "delivery_rules_evaluated"
        assert d.errors[0]["error"] == "Rule engine timeout"
        assert "at" in d.errors[0]

    def test_multiple_failures(self):
        d = DeliveryDossier()
        d.fail(DeliveryStage.GRAPHED, "Graph construction error")
        d.fail(DeliveryStage.RULES_EVALUATED, "Rule engine error")
        assert len(d.errors) == 2


# ═══════════════════════════════════════════════════════════
# COMPUTED PROPERTY TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryDossierProperties:
    def test_total_milestones(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A"),
            Milestone(milestone_id="M2", description="B"),
            Milestone(milestone_id="M3", description="C"),
        ])
        assert d.total_milestones == 3

    def test_total_milestones_empty(self):
        d = DeliveryDossier()
        assert d.total_milestones == 0

    def test_delayed_milestones(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=0),
            Milestone(milestone_id="M2", description="B", delay_days=30),
            Milestone(milestone_id="M3", description="C", delay_days=15),
        ])
        assert d.delayed_milestones == 2

    def test_delayed_milestones_none_delayed(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=0),
        ])
        assert d.delayed_milestones == 0

    def test_total_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A", budgeted_amount=100000),
            FinancialRecord(line_item_id="F2", description="B", budgeted_amount=200000),
        ])
        assert d.total_budget == 300000

    def test_total_budget_empty(self):
        d = DeliveryDossier()
        assert d.total_budget == 0.0

    def test_total_actual_spend(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A", actual_amount=120000),
            FinancialRecord(line_item_id="F2", description="B", actual_amount=250000),
        ])
        assert d.total_actual_spend == 370000

    def test_budget_variance_pct_over_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=130000),
        ])
        assert d.budget_variance_pct == pytest.approx(30.0)

    def test_budget_variance_pct_under_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=90000),
        ])
        assert d.budget_variance_pct == pytest.approx(-10.0)

    def test_budget_variance_pct_zero_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=0, actual_amount=50000),
        ])
        assert d.budget_variance_pct == 0.0

    def test_staffing_gap_ratio_fully_staffed(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng", planned_fte=2.0, actual_fte=2.0),
        ])
        assert d.staffing_gap_ratio == pytest.approx(1.0)

    def test_staffing_gap_ratio_understaffed(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng", planned_fte=4.0, actual_fte=2.0),
        ])
        assert d.staffing_gap_ratio == pytest.approx(0.5)

    def test_staffing_gap_ratio_no_plan(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng", planned_fte=0.0, actual_fte=2.0),
        ])
        # No staffing plan = no gap measurable
        assert d.staffing_gap_ratio == 1.0

    def test_staffing_gap_ratio_empty(self):
        d = DeliveryDossier()
        assert d.staffing_gap_ratio == 1.0

    def test_outcome_delivery_ratio_full(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=100, quantity_delivered=100),
        ])
        assert d.outcome_delivery_ratio == pytest.approx(1.0)

    def test_outcome_delivery_ratio_partial(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=100, quantity_delivered=60),
            OutcomeRecord(outcome_id="O2", description="B",
                          quantity_planned=200, quantity_delivered=180),
        ])
        # total planned=300, total delivered=240 → ratio=0.8
        assert d.outcome_delivery_ratio == pytest.approx(0.8)

    def test_outcome_delivery_ratio_nothing_planned(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=0, quantity_delivered=0),
        ])
        assert d.outcome_delivery_ratio == 1.0

    def test_outcome_delivery_ratio_empty(self):
        d = DeliveryDossier()
        assert d.outcome_delivery_ratio == 1.0


# ═══════════════════════════════════════════════════════════
# INTEGRATION: FULLY POPULATED DOSSIER
# ═══════════════════════════════════════════════════════════


class TestDeliveryDossierIntegration:
    """Build a fully populated delivery dossier and verify all fields survive."""

    def test_full_dossier_lifecycle(self):
        dossier = DeliveryDossier(
            contract_id="N0002417C2117",
            country_code="US",
            country_name="United States",
            project_name="Naval vessel maintenance",
            procurement_verdict="RED",
            milestones=[
                Milestone(milestone_id="M1", description="Hull inspection",
                          planned_date="2025-03-01", actual_date="2025-05-15",
                          status="delayed", delay_days=75,
                          deliverables_due=2, deliverables_accepted=1),
                Milestone(milestone_id="M2", description="Systems check",
                          planned_date="2025-06-01", actual_date="2025-06-01",
                          status="completed", delay_days=0,
                          deliverables_due=1, deliverables_accepted=1),
            ],
            resources=[
                ResourceRecord(resource_id="R1", role="lead_engineer",
                               planned_fte=1.0, actual_fte=1.0,
                               qualification_required="PE", qualification_verified=True),
                ResourceRecord(resource_id="R2", role="welder",
                               planned_fte=4.0, actual_fte=2.5,
                               qualification_required="AWS-D1.1", qualification_verified=False),
            ],
            outcomes=[
                OutcomeRecord(outcome_id="O1", description="Hull panels replaced",
                              unit="panels", quantity_planned=20, quantity_delivered=15,
                              quality_score=0.7, defects_noted=3),
            ],
            financials=[
                FinancialRecord(line_item_id="F1", description="Materials",
                                budgeted_amount=2000000, actual_amount=2800000,
                                currency="USD", variance_pct=40.0, amendment_count=2),
                FinancialRecord(line_item_id="F2", description="Labour",
                                budgeted_amount=1000000, actual_amount=1100000,
                                currency="USD", variance_pct=10.0),
            ],
        )

        # Verify identity
        assert dossier.contract_id == "N0002417C2117"
        assert dossier.procurement_verdict == "RED"

        # Verify computed properties
        assert dossier.total_milestones == 2
        assert dossier.delayed_milestones == 1
        assert dossier.total_budget == 3000000
        assert dossier.total_actual_spend == 3900000
        assert dossier.budget_variance_pct == pytest.approx(30.0)
        assert dossier.staffing_gap_ratio == pytest.approx(3.5 / 5.0)  # 0.7
        assert dossier.outcome_delivery_ratio == pytest.approx(15.0 / 20.0)  # 0.75

        # Simulate pipeline progression
        dossier.advance(DeliveryStage.GRAPHED, duration_ms=25.0)
        assert dossier.stage == DeliveryStage.GRAPHED

        # Attach graph result
        dossier.graph = DeliveryGraphResult(node_count=8, edge_count=12)

        # Simulate rules evaluation
        dossier.advance(DeliveryStage.RULES_EVALUATED, duration_ms=15.0)
        dossier.rules_result = DeliveryRulesResult(
            rules_evaluated=12,
            rules_fired=4,
            rule_results=[
                DeliveryRuleResult(rule_id="DEL-MILE-001", layer="milestone",
                                   fired=True, evidence="75-day delay on M1"),
                DeliveryRuleResult(rule_id="DEL-RES-002", layer="resource",
                                   fired=True, evidence="Staffing gap 30%"),
                DeliveryRuleResult(rule_id="DEL-OUT-001", layer="outcome",
                                   fired=True, evidence="25% shortfall"),
                DeliveryRuleResult(rule_id="DEL-FIN-001", layer="financial",
                                   fired=True, evidence="30% over budget"),
            ],
            layer_summary={"milestone": 1, "resource": 1, "outcome": 1, "financial": 1},
        )

        # Simulate gating
        dossier.advance(DeliveryStage.GATED, duration_ms=5.0)
        dossier.gate_outcome = DeliveryGateOutcome(
            verdict=DeliveryVerdict.RED,
            dimensions_fired=3,
            dimension_results=[
                DeliveryDimensionResult(
                    dimension=DeliveryDimension.MILESTONE_COMPLIANCE,
                    fired=True, observed_value=0.5, threshold=0.8),
                DeliveryDimensionResult(
                    dimension=DeliveryDimension.RESOURCE_VERIFICATION,
                    fired=True, observed_value=0.7, threshold=0.85),
                DeliveryDimensionResult(
                    dimension=DeliveryDimension.OUTCOME_VERIFICATION,
                    fired=True, observed_value=0.75, threshold=0.9),
                DeliveryDimensionResult(
                    dimension=DeliveryDimension.FINANCIAL_RECONCILIATION,
                    fired=False, observed_value=0.3, threshold=0.35),
            ],
        )

        dossier.advance(DeliveryStage.COMPLETE, duration_ms=1.0)
        assert dossier.stage == DeliveryStage.COMPLETE
        assert dossier.gate_outcome.verdict == DeliveryVerdict.RED
        assert dossier.rules_result.rules_fired == 4
        assert len(dossier.processing_ms) == 4
