"""
Tests for SUNLIGHT Side 2 delivery rule engine.

Covers:
    - build_delivery_rules() returns exactly 12 rules
    - All 12 rule IDs present (DEL-MILE-001/002/003, DEL-RES-001/002/003,
      DEL-OUT-001/002/003, DEL-FIN-001/002/003)
    - All 4 layers represented (milestone, resource, outcome, financial)
    - Each rule fires on crafted positive data
    - Each rule does NOT fire on crafted negative data
    - DeliveryRuleEngine.evaluate() produces correct aggregate results
    - Edge cases: empty dossier, zero denominators, boundary values
    - Integration: fully populated dossier through full rule evaluation
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from delivery_schema import (
    DeliveryDossier,
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
)
from delivery_rules import (
    DeliveryRule,
    DeliveryRuleEngine,
    build_delivery_rules,
    DEFAULT_DELAY_TOLERANCE_DAYS,
    DEFAULT_MILESTONE_FAILURE_RATIO,
    DEFAULT_STAFFING_GAP_TOLERANCE,
    DEFAULT_QUALIFICATION_FAILURE_RATIO,
    DEFAULT_OUTCOME_SHORTFALL_THRESHOLD,
    DEFAULT_DEFECT_RATE_THRESHOLD,
    DEFAULT_COST_ESCALATION_TOLERANCE,
    DEFAULT_AMENDMENT_THRESHOLD,
    DEFAULT_BUDGET_CONCENTRATION_RATIO,
)
from jurisdiction_profile import US_FEDERAL


# ═══════════════════════════════════════════════════════════
# RULE SET STRUCTURE TESTS
# ═══════════════════════════════════════════════════════════


class TestBuildDeliveryRules:
    def test_returns_12_rules(self):
        rules = build_delivery_rules(US_FEDERAL)
        assert len(rules) == 12

    def test_all_rule_ids_present(self):
        rules = build_delivery_rules(US_FEDERAL)
        ids = {r.rule_id for r in rules}
        expected = {
            "DEL-MILE-001", "DEL-MILE-002", "DEL-MILE-003",
            "DEL-RES-001", "DEL-RES-002", "DEL-RES-003",
            "DEL-OUT-001", "DEL-OUT-002", "DEL-OUT-003",
            "DEL-FIN-001", "DEL-FIN-002", "DEL-FIN-003",
        }
        assert ids == expected

    def test_all_layers_represented(self):
        rules = build_delivery_rules(US_FEDERAL)
        layers = {r.layer for r in rules}
        assert layers == {"milestone", "resource", "outcome", "financial"}

    def test_three_rules_per_layer(self):
        rules = build_delivery_rules(US_FEDERAL)
        layer_counts = {}
        for r in rules:
            layer_counts[r.layer] = layer_counts.get(r.layer, 0) + 1
        for layer, count in layer_counts.items():
            assert count == 3, f"Layer {layer} has {count} rules, expected 3"

    def test_all_rules_are_DeliveryRule(self):
        rules = build_delivery_rules(US_FEDERAL)
        for r in rules:
            assert isinstance(r, DeliveryRule)

    def test_all_rules_have_evidence_template(self):
        rules = build_delivery_rules(US_FEDERAL)
        for r in rules:
            assert r.evidence_template, f"Rule {r.rule_id} has empty evidence_template"


# ═══════════════════════════════════════════════════════════
# MILESTONE LAYER TESTS (DEL-MILE-001/002/003)
# ═══════════════════════════════════════════════════════════


class TestDelMile001:
    """Critical milestone delay."""

    def test_fires_when_delay_exceeds_tolerance(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      delay_days=DEFAULT_DELAY_TOLERANCE_DAYS + 1),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-001")
        assert rule.condition(d) is True

    def test_does_not_fire_at_tolerance(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      delay_days=DEFAULT_DELAY_TOLERANCE_DAYS),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-001")
        assert rule.condition(d) is False

    def test_does_not_fire_no_delay(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-001")
        assert rule.condition(d) is False

    def test_does_not_fire_empty(self):
        d = DeliveryDossier()
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-001")
        assert rule.condition(d) is False

    def test_evidence_string(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=45),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-001")
        evidence = rule.build_evidence(d)
        assert "45 days" in evidence


class TestDelMile002:
    """Majority milestones delayed."""

    def test_fires_when_majority_delayed(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=5),
            Milestone(milestone_id="M2", description="B", delay_days=10),
            Milestone(milestone_id="M3", description="C", delay_days=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-002")
        # 2/3 > 50%
        assert rule.condition(d) is True

    def test_does_not_fire_at_exactly_half(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=5),
            Milestone(milestone_id="M2", description="B", delay_days=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-002")
        # 1/2 = 50%, not > 50%
        assert rule.condition(d) is False

    def test_does_not_fire_single_milestone(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=5),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-002")
        # requires >= 2 milestones
        assert rule.condition(d) is False


class TestDelMile003:
    """Deliverable acceptance gap."""

    def test_fires_when_acceptance_below_threshold(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      deliverables_due=10, deliverables_accepted=5),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-003")
        # 5/10 = 0.5 < 0.8 threshold
        assert rule.condition(d) is True

    def test_does_not_fire_at_threshold(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      deliverables_due=10, deliverables_accepted=8),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-003")
        # 8/10 = 0.8, not < 0.8
        assert rule.condition(d) is False

    def test_does_not_fire_zero_due(self):
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      deliverables_due=0, deliverables_accepted=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-MILE-003")
        assert rule.condition(d) is False


# ═══════════════════════════════════════════════════════════
# RESOURCE LAYER TESTS (DEL-RES-001/002/003)
# ═══════════════════════════════════════════════════════════


class TestDelRes001:
    """Staffing gap below tolerance."""

    def test_fires_when_understaffed(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           planned_fte=4.0, actual_fte=2.0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-001")
        # 2/4 = 0.5 < 0.75 tolerance
        assert rule.condition(d) is True

    def test_does_not_fire_when_adequately_staffed(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           planned_fte=4.0, actual_fte=3.5),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-001")
        # 3.5/4 = 0.875 >= 0.75
        assert rule.condition(d) is False

    def test_does_not_fire_no_plan(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           planned_fte=0.0, actual_fte=2.0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-001")
        assert rule.condition(d) is False


class TestDelRes002:
    """Qualification verification failure."""

    def test_fires_when_majority_unverified(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           qualification_required="PE", qualification_verified=False),
            ResourceRecord(resource_id="R2", role="inspector",
                           qualification_required="CQE", qualification_verified=False),
            ResourceRecord(resource_id="R3", role="pm",
                           qualification_required="PMP", qualification_verified=True),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-002")
        # 2/3 unverified > 50%
        assert rule.condition(d) is True

    def test_does_not_fire_when_all_verified(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           qualification_required="PE", qualification_verified=True),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-002")
        assert rule.condition(d) is False

    def test_does_not_fire_no_qualifications_required(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="eng",
                           qualification_required="", qualification_verified=False),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-002")
        assert rule.condition(d) is False


class TestDelRes003:
    """Zero actual staffing on planned role."""

    def test_fires_when_zero_actual(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="inspector",
                           planned_fte=2.0, actual_fte=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-003")
        assert rule.condition(d) is True

    def test_does_not_fire_when_partially_staffed(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="inspector",
                           planned_fte=2.0, actual_fte=0.5),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-003")
        assert rule.condition(d) is False

    def test_does_not_fire_when_no_plan(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="inspector",
                           planned_fte=0, actual_fte=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-003")
        assert rule.condition(d) is False

    def test_evidence_lists_roles(self):
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="inspector",
                           planned_fte=2.0, actual_fte=0),
            ResourceRecord(resource_id="R2", role="surveyor",
                           planned_fte=1.0, actual_fte=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-RES-003")
        evidence = rule.build_evidence(d)
        assert "inspector" in evidence
        assert "surveyor" in evidence


# ═══════════════════════════════════════════════════════════
# OUTCOME LAYER TESTS (DEL-OUT-001/002/003)
# ═══════════════════════════════════════════════════════════


class TestDelOut001:
    """Outcome delivery shortfall."""

    def test_fires_below_threshold(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=100, quantity_delivered=50),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-001")
        # 50/100 = 0.5 < 0.8
        assert rule.condition(d) is True

    def test_does_not_fire_at_threshold(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=100, quantity_delivered=80),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-001")
        # 80/100 = 0.8, not < 0.8
        assert rule.condition(d) is False

    def test_does_not_fire_nothing_planned(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A",
                          quantity_planned=0, quantity_delivered=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-001")
        assert rule.condition(d) is False


class TestDelOut002:
    """Excessive defect rate."""

    def test_fires_above_threshold(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A", defects_noted=3),
            OutcomeRecord(outcome_id="O2", description="B", defects_noted=0),
            OutcomeRecord(outcome_id="O3", description="C", defects_noted=1),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-002")
        # 2/3 = 66% > 20%
        assert rule.condition(d) is True

    def test_does_not_fire_no_defects(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A", defects_noted=0),
            OutcomeRecord(outcome_id="O2", description="B", defects_noted=0),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-002")
        assert rule.condition(d) is False

    def test_does_not_fire_at_exactly_threshold(self):
        # 1/5 = 20%, not > 20%
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id=f"O{i}", description="X", defects_noted=0)
            for i in range(4)
        ] + [
            OutcomeRecord(outcome_id="O5", description="X", defects_noted=1),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-002")
        assert rule.condition(d) is False


class TestDelOut003:
    """Quality score below threshold."""

    def test_fires_low_quality(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A", quality_score=0.5),
            OutcomeRecord(outcome_id="O2", description="B", quality_score=0.6),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-003")
        # avg 0.55 < 0.8
        assert rule.condition(d) is True

    def test_does_not_fire_high_quality(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A", quality_score=0.9),
            OutcomeRecord(outcome_id="O2", description="B", quality_score=0.85),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-003")
        # avg 0.875 >= 0.8
        assert rule.condition(d) is False

    def test_does_not_fire_no_scores(self):
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="A", quality_score=None),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-OUT-003")
        assert rule.condition(d) is False


# ═══════════════════════════════════════════════════════════
# FINANCIAL LAYER TESTS (DEL-FIN-001/002/003)
# ═══════════════════════════════════════════════════════════


class TestDelFin001:
    """Cost escalation above tolerance."""

    def test_fires_over_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=130000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-001")
        # 30% > 25%
        assert rule.condition(d) is True

    def test_does_not_fire_at_tolerance(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=125000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-001")
        # 25% = tolerance, not > tolerance
        assert rule.condition(d) is False

    def test_does_not_fire_under_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=90000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-001")
        assert rule.condition(d) is False

    def test_does_not_fire_zero_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=0, actual_amount=50000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-001")
        assert rule.condition(d) is False


class TestDelFin002:
    """Excessive contract amendments."""

    def test_fires_above_threshold(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            amendment_count=DEFAULT_AMENDMENT_THRESHOLD + 1),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-002")
        assert rule.condition(d) is True

    def test_does_not_fire_at_threshold(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            amendment_count=DEFAULT_AMENDMENT_THRESHOLD),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-002")
        assert rule.condition(d) is False


class TestDelFin003:
    """Budget variance concentration."""

    def test_fires_when_concentrated(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="Materials",
                            budgeted_amount=500000, actual_amount=900000),
            FinancialRecord(line_item_id="F2", description="Labour",
                            budgeted_amount=500000, actual_amount=510000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-003")
        # total overrun = 410000; F1 overrun = 400000; 400000/410000 = 97.6% > 70%
        assert rule.condition(d) is True

    def test_does_not_fire_when_spread(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="Materials",
                            budgeted_amount=500000, actual_amount=600000),
            FinancialRecord(line_item_id="F2", description="Labour",
                            budgeted_amount=500000, actual_amount=610000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-003")
        # total overrun = 210000; F1 = 100000, F2 = 110000; max/total = 52% < 70%
        assert rule.condition(d) is False

    def test_does_not_fire_single_line(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=200000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-003")
        # requires >= 2 line items
        assert rule.condition(d) is False

    def test_does_not_fire_under_budget(self):
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=500000, actual_amount=400000),
            FinancialRecord(line_item_id="F2", description="B",
                            budgeted_amount=500000, actual_amount=450000),
        ])
        rules = build_delivery_rules(US_FEDERAL)
        rule = next(r for r in rules if r.rule_id == "DEL-FIN-003")
        assert rule.condition(d) is False


# ═══════════════════════════════════════════════════════════
# ENGINE TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryRuleEngine:
    def test_empty_dossier_no_rules_fire(self):
        engine = DeliveryRuleEngine()
        d = DeliveryDossier()
        result = engine.evaluate(d)
        assert result.rules_evaluated == 12
        assert result.rules_fired == 0
        assert len(result.rule_results) == 12
        assert all(not r.fired for r in result.rule_results)

    def test_all_rules_evaluated(self):
        engine = DeliveryRuleEngine()
        d = DeliveryDossier()
        result = engine.evaluate(d)
        ids = {r.rule_id for r in result.rule_results}
        assert len(ids) == 12

    def test_layer_summary_populated(self):
        engine = DeliveryRuleEngine()
        d = DeliveryDossier(
            milestones=[
                Milestone(milestone_id="M1", description="A", delay_days=60),
            ],
            financials=[
                FinancialRecord(line_item_id="F1", description="A",
                                budgeted_amount=100000, actual_amount=150000),
            ],
        )
        result = engine.evaluate(d)
        assert "milestone" in result.layer_summary
        assert "financial" in result.layer_summary

    def test_fired_rules_have_evidence(self):
        engine = DeliveryRuleEngine()
        d = DeliveryDossier(
            milestones=[
                Milestone(milestone_id="M1", description="A", delay_days=60),
            ],
        )
        result = engine.evaluate(d)
        fired = [r for r in result.rule_results if r.fired]
        assert len(fired) >= 1
        for r in fired:
            assert r.evidence != ""
            assert r.legal_basis != ""
            assert r.confidence > 0


# ═══════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═══════════════════════════════════════════════════════════


class TestDeliveryRuleEngineIntegration:
    """Full evaluation of a problematic delivery dossier."""

    def test_full_evaluation(self):
        dossier = DeliveryDossier(
            contract_id="N0002417C2117",
            milestones=[
                Milestone(milestone_id="M1", description="Phase 1",
                          delay_days=45, deliverables_due=5, deliverables_accepted=2),
                Milestone(milestone_id="M2", description="Phase 2",
                          delay_days=20, deliverables_due=3, deliverables_accepted=3),
                Milestone(milestone_id="M3", description="Phase 3",
                          delay_days=10, deliverables_due=2, deliverables_accepted=1),
            ],
            resources=[
                ResourceRecord(resource_id="R1", role="lead_engineer",
                               planned_fte=1.0, actual_fte=1.0,
                               qualification_required="PE", qualification_verified=True),
                ResourceRecord(resource_id="R2", role="welder",
                               planned_fte=4.0, actual_fte=1.5,
                               qualification_required="AWS-D1.1", qualification_verified=False),
                ResourceRecord(resource_id="R3", role="inspector",
                               planned_fte=2.0, actual_fte=0,
                               qualification_required="CQE", qualification_verified=False),
            ],
            outcomes=[
                OutcomeRecord(outcome_id="O1", description="Hull panels",
                              quantity_planned=20, quantity_delivered=12,
                              quality_score=0.6, defects_noted=4),
                OutcomeRecord(outcome_id="O2", description="Systems install",
                              quantity_planned=10, quantity_delivered=8,
                              quality_score=0.7, defects_noted=1),
            ],
            financials=[
                FinancialRecord(line_item_id="F1", description="Materials",
                                budgeted_amount=2000000, actual_amount=2900000,
                                amendment_count=5),
                FinancialRecord(line_item_id="F2", description="Labour",
                                budgeted_amount=1000000, actual_amount=1050000),
            ],
        )

        engine = DeliveryRuleEngine()
        result = engine.evaluate(dossier)

        # Verify all rules evaluated
        assert result.rules_evaluated == 12

        # The crafted dossier should trigger many rules:
        # DEL-MILE-001: M1 at 45 days > 30-day tolerance
        # DEL-MILE-002: 3/3 delayed > 50%
        # DEL-MILE-003: 6/10 accepted = 60% < 80%
        # DEL-RES-001: staffing ratio = 2.5/7.0 = 0.357 < 0.75
        # DEL-RES-002: 2/3 qualifications unverified > 50%
        # DEL-RES-003: inspector has planned_fte=2.0, actual=0
        # DEL-OUT-001: delivery ratio = 20/30 = 0.667 < 0.8
        # DEL-OUT-002: 2/2 outcomes have defects = 100% > 20%
        # DEL-OUT-003: avg quality = 0.65 < 0.8
        # DEL-FIN-001: variance = 30% > 25% (budgeted 3M, actual 3.95M)
        # DEL-FIN-002: F1 has 5 amendments > 3 threshold
        # DEL-FIN-003: F1 overrun 900K / total overrun 950K = 94.7% > 70%
        fired_ids = {r.rule_id for r in result.rule_results if r.fired}
        expected_fired = {
            "DEL-MILE-001", "DEL-MILE-002", "DEL-MILE-003",
            "DEL-RES-001", "DEL-RES-002", "DEL-RES-003",
            "DEL-OUT-001", "DEL-OUT-002", "DEL-OUT-003",
            "DEL-FIN-001", "DEL-FIN-002", "DEL-FIN-003",
        }
        assert fired_ids == expected_fired, (
            f"Expected all 12 rules to fire. "
            f"Missing: {expected_fired - fired_ids}, "
            f"Unexpected: {fired_ids - expected_fired}"
        )

        # All 4 layers active
        assert set(result.layer_summary.keys()) == {"milestone", "resource", "outcome", "financial"}

        # Each layer fired exactly 3 rules
        for layer, count in result.layer_summary.items():
            assert count == 3, f"Layer {layer} fired {count} rules, expected 3"

        # All fired rules have evidence and legal basis
        for r in result.rule_results:
            if r.fired:
                assert r.evidence != "", f"Rule {r.rule_id} has empty evidence"
                assert r.legal_basis != "", f"Rule {r.rule_id} has empty legal_basis"
                assert r.confidence > 0, f"Rule {r.rule_id} has zero confidence"
