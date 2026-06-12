"""
Tests for SUNLIGHT Side 2 delivery graph construction.

Covers:
    - Base graph structure (contract, schedule, budget, delivery_outcome nodes)
    - Base graph edges (EXPRESSES, BOUNDS)
    - Milestone node generation (on-time → VERIFIES, delayed → SEEKS)
    - Resource node generation (fully staffed → VERIFIES, understaffed → SEEKS)
    - Outcome node generation (fully delivered → VERIFIES)
    - Financial node generation (within budget → VERIFIES)
    - Rule-fired edges (REMOVES edges from fired delivery rules)
    - DeliveryGraphBuildReport audit trail
    - DeliveryGraphResult written to dossier.graph
    - DeliveryRulesResult written to dossier.rules_result
    - Edge cases: empty dossier, single record, no rules fire
    - Integration: full dossier through graph builder
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from delivery_schema import (
    DeliveryDossier,
    DeliveryGraphResult,
    DeliveryRulesResult,
    DeliveryStage,
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
)
from delivery_graph import (
    DeliveryGraphBuilder,
    DeliveryGraphBuildReport,
    FIRED_RULE_EDGE_TYPE,
    _rule_edge_endpoints,
)


# ═══════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════


def _node_ids(graph_result: DeliveryGraphResult) -> set:
    return {n["id"] for n in graph_result.nodes}


def _edges_by_type(graph_result: DeliveryGraphResult, edge_type: str) -> list:
    return [e for e in graph_result.edges if e["type"] == edge_type]


def _edges_by_rule(graph_result: DeliveryGraphResult, rule_id: str) -> list:
    return [e for e in graph_result.edges if e.get("rule") == rule_id]


# ═══════════════════════════════════════════════════════════
# BASE GRAPH TESTS
# ═══════════════════════════════════════════════════════════


class TestBaseGraph:
    def test_empty_dossier_has_base_nodes(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "contract" in ids
        assert "schedule" in ids
        assert "budget" in ids
        assert "delivery_outcome" in ids

    def test_empty_dossier_has_base_edges(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        base_edges = [e for e in d.graph.edges if e.get("rule") == "BASE"]
        assert len(base_edges) >= 4

        # Check edge types present
        types = {e["type"] for e in base_edges}
        assert "EXPRESSES" in types
        assert "BOUNDS" in types

    def test_contract_id_in_node_label(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(contract_id="TEST-123")
        builder.build_graph(d)

        contract_node = next(n for n in d.graph.nodes if n["id"] == "contract")
        assert "TEST-123" in contract_node["label"]

    def test_budget_in_node_label(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=1000000),
        ])
        builder.build_graph(d)

        budget_node = next(n for n in d.graph.nodes if n["id"] == "budget")
        assert "1,000,000" in budget_node["label"]


# ═══════════════════════════════════════════════════════════
# MILESTONE NODE TESTS
# ═══════════════════════════════════════════════════════════


class TestMilestoneNodes:
    def test_milestone_node_created(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="Phase 1"),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "milestone_M1" in ids

    def test_on_time_milestone_adds_verifies_edge(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="Phase 1",
                      delay_days=0, status="completed"),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        m1_verifies = [e for e in verifies
                       if e["source"] == "milestone_M1" and e["target"] == "schedule"]
        assert len(m1_verifies) == 1

    def test_delayed_milestone_adds_seeks_edge(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="Phase 1",
                      delay_days=15, status="delayed"),
        ])
        builder.build_graph(d)

        seeks = _edges_by_type(d.graph, "SEEKS")
        m1_seeks = [e for e in seeks
                    if e["source"] == "milestone_M1" and e["target"] == "schedule"]
        assert len(m1_seeks) == 1
        assert "15 days" in m1_seeks[0]["description"]

    def test_multiple_milestones(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A"),
            Milestone(milestone_id="M2", description="B"),
            Milestone(milestone_id="M3", description="C"),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "milestone_M1" in ids
        assert "milestone_M2" in ids
        assert "milestone_M3" in ids


# ═══════════════════════════════════════════════════════════
# RESOURCE NODE TESTS
# ═══════════════════════════════════════════════════════════


class TestResourceNodes:
    def test_resource_node_created(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="engineer",
                           planned_fte=2.0, actual_fte=2.0),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "resource_R1" in ids

    def test_fully_staffed_adds_verifies_edge(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="engineer",
                           planned_fte=2.0, actual_fte=2.0),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        r1_verifies = [e for e in verifies
                       if e["source"] == "resource_R1"
                       and e["target"] == "delivery_outcome"]
        assert len(r1_verifies) == 1

    def test_understaffed_adds_seeks_edge(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="engineer",
                           planned_fte=4.0, actual_fte=1.5),
        ])
        builder.build_graph(d)

        seeks = _edges_by_type(d.graph, "SEEKS")
        r1_seeks = [e for e in seeks
                    if e["source"] == "resource_R1"
                    and e["target"] == "delivery_outcome"]
        assert len(r1_seeks) == 1

    def test_zero_actual_no_seeks_edge(self):
        """Zero actual FTE means no SEEKS edge (role is absent, not understaffed)."""
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(resources=[
            ResourceRecord(resource_id="R1", role="inspector",
                           planned_fte=2.0, actual_fte=0),
        ])
        builder.build_graph(d)

        seeks = _edges_by_type(d.graph, "SEEKS")
        r1_seeks = [e for e in seeks if e["source"] == "resource_R1"]
        # actual_fte == 0 does NOT satisfy actual_fte > 0 condition
        assert len(r1_seeks) == 0


# ═══════════════════════════════════════════════════════════
# OUTCOME NODE TESTS
# ═══════════════════════════════════════════════════════════


class TestOutcomeNodes:
    def test_outcome_node_created(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="Road segment"),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "outcome_O1" in ids

    def test_fully_delivered_adds_verifies(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="Road segment",
                          quantity_planned=100, quantity_delivered=100),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        o1_verifies = [e for e in verifies
                       if e["source"] == "outcome_O1"
                       and e["target"] == "delivery_outcome"]
        assert len(o1_verifies) == 1

    def test_partial_delivery_no_verifies(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(outcomes=[
            OutcomeRecord(outcome_id="O1", description="Road segment",
                          quantity_planned=100, quantity_delivered=50),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        o1_verifies = [e for e in verifies
                       if e["source"] == "outcome_O1"]
        assert len(o1_verifies) == 0


# ═══════════════════════════════════════════════════════════
# FINANCIAL NODE TESTS
# ═══════════════════════════════════════════════════════════


class TestFinancialNodes:
    def test_financial_node_created(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="Materials",
                            budgeted_amount=100000, actual_amount=90000),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "financial_F1" in ids

    def test_within_budget_adds_verifies(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="Materials",
                            budgeted_amount=100000, actual_amount=90000),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        f1_verifies = [e for e in verifies
                       if e["source"] == "financial_F1"
                       and e["target"] == "budget"]
        assert len(f1_verifies) == 1

    def test_over_budget_no_verifies(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="Materials",
                            budgeted_amount=100000, actual_amount=150000),
        ])
        builder.build_graph(d)

        verifies = _edges_by_type(d.graph, "VERIFIES")
        f1_verifies = [e for e in verifies
                       if e["source"] == "financial_F1"]
        assert len(f1_verifies) == 0


# ═══════════════════════════════════════════════════════════
# RULE-FIRED EDGE TESTS
# ═══════════════════════════════════════════════════════════


class TestRuleFiredEdges:
    def test_fired_rule_adds_removes_edge(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=60),
        ])
        builder.build_graph(d)

        removes = _edges_by_type(d.graph, FIRED_RULE_EDGE_TYPE)
        mile_001 = [e for e in removes if e.get("rule") == "DEL-MILE-001"]
        assert len(mile_001) >= 1

    def test_fired_rule_edge_targets_correct_structural_element(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=60),
        ])
        builder.build_graph(d)

        removes = _edges_by_type(d.graph, FIRED_RULE_EDGE_TYPE)
        mile_001 = [e for e in removes if e.get("rule") == "DEL-MILE-001"]
        assert mile_001[0]["target"] == "schedule"

    def test_financial_rule_targets_budget(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(financials=[
            FinancialRecord(line_item_id="F1", description="A",
                            budgeted_amount=100000, actual_amount=130000),
        ])
        builder.build_graph(d)

        removes = _edges_by_type(d.graph, FIRED_RULE_EDGE_TYPE)
        fin_001 = [e for e in removes if e.get("rule") == "DEL-FIN-001"]
        assert len(fin_001) >= 1
        assert fin_001[0]["target"] == "budget"

    def test_no_rules_fire_no_removes_edges(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A",
                      delay_days=0, status="completed"),
        ])
        builder.build_graph(d)

        removes = _edges_by_type(d.graph, FIRED_RULE_EDGE_TYPE)
        assert len(removes) == 0

    def test_finding_node_created_for_fired_rule(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=60),
        ])
        builder.build_graph(d)

        ids = _node_ids(d.graph)
        assert "finding_del_mile_001" in ids


# ═══════════════════════════════════════════════════════════
# AUDIT REPORT TESTS
# ═══════════════════════════════════════════════════════════


class TestDeliveryGraphBuildReport:
    def test_report_populated(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        report = builder.last_report
        assert report is not None
        assert report.total_rules_evaluated == 12
        assert report.rules_fired == 0
        assert report.rules_skipped == 12
        assert report.nodes_total >= 4  # base nodes
        assert report.edges_total >= 4  # base edges

    def test_report_rules_fired_count(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A", delay_days=60),
        ])
        builder.build_graph(d)

        report = builder.last_report
        assert report.rules_fired >= 1

    def test_report_layers_active(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(
            milestones=[
                Milestone(milestone_id="M1", description="A", delay_days=60),
            ],
            financials=[
                FinancialRecord(line_item_id="F1", description="A",
                                budgeted_amount=100000, actual_amount=150000),
            ],
        )
        builder.build_graph(d)

        report = builder.last_report
        assert "milestone" in report.layers_active
        assert "financial" in report.layers_active

    def test_report_rule_fire_log(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        report = builder.last_report
        assert "DEL-MILE-001" in report.rule_fire_log
        assert "DEL-FIN-003" in report.rule_fire_log
        assert len(report.rule_fire_log) == 12


# ═══════════════════════════════════════════════════════════
# DOSSIER OUTPUT TESTS
# ═══════════════════════════════════════════════════════════


class TestDossierOutput:
    def test_graph_written_to_dossier(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        assert d.graph is not None
        assert isinstance(d.graph, DeliveryGraphResult)
        assert d.graph.node_count >= 4
        assert d.graph.edge_count >= 4

    def test_rules_result_written_to_dossier(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        assert d.rules_result is not None
        assert isinstance(d.rules_result, DeliveryRulesResult)
        assert d.rules_result.rules_evaluated == 12

    def test_node_count_matches(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(milestones=[
            Milestone(milestone_id="M1", description="A"),
        ])
        builder.build_graph(d)

        assert d.graph.node_count == len(d.graph.nodes)

    def test_edge_count_matches(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier()
        builder.build_graph(d)

        assert d.graph.edge_count == len(d.graph.edges)

    def test_no_duplicate_node_ids(self):
        builder = DeliveryGraphBuilder()
        d = DeliveryDossier(
            milestones=[
                Milestone(milestone_id="M1", description="A", delay_days=60),
                Milestone(milestone_id="M2", description="B", delay_days=0, status="completed"),
            ],
            resources=[
                ResourceRecord(resource_id="R1", role="eng", planned_fte=2.0, actual_fte=2.0),
            ],
            outcomes=[
                OutcomeRecord(outcome_id="O1", description="X",
                              quantity_planned=100, quantity_delivered=100),
            ],
            financials=[
                FinancialRecord(line_item_id="F1", description="Y",
                                budgeted_amount=100000, actual_amount=90000),
            ],
        )
        builder.build_graph(d)

        ids = [n["id"] for n in d.graph.nodes]
        assert len(ids) == len(set(ids)), f"Duplicate node IDs: {[x for x in ids if ids.count(x) > 1]}"


# ═══════════════════════════════════════════════════════════
# RULE EDGE ENDPOINT MAPPING TESTS
# ═══════════════════════════════════════════════════════════


class TestRuleEdgeEndpoints:
    def test_milestone_targets_schedule(self):
        src, tgt = _rule_edge_endpoints("DEL-MILE-001", "milestone")
        assert tgt == "schedule"
        assert "del_mile_001" in src

    def test_resource_targets_delivery_outcome(self):
        src, tgt = _rule_edge_endpoints("DEL-RES-001", "resource")
        assert tgt == "delivery_outcome"

    def test_outcome_targets_delivery_outcome(self):
        src, tgt = _rule_edge_endpoints("DEL-OUT-001", "outcome")
        assert tgt == "delivery_outcome"

    def test_financial_targets_budget(self):
        src, tgt = _rule_edge_endpoints("DEL-FIN-001", "financial")
        assert tgt == "budget"

    def test_unknown_layer_defaults(self):
        src, tgt = _rule_edge_endpoints("DEL-UNK-001", "unknown")
        assert tgt == "delivery_outcome"


# ═══════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═══════════════════════════════════════════════════════════


class TestDeliveryGraphIntegration:
    """Full graph construction with a problematic delivery dossier."""

    def test_full_graph_build(self):
        dossier = DeliveryDossier(
            contract_id="N0002417C2117",
            milestones=[
                Milestone(milestone_id="M1", description="Hull inspection",
                          delay_days=45, status="delayed",
                          deliverables_due=5, deliverables_accepted=2),
                Milestone(milestone_id="M2", description="Systems check",
                          delay_days=10, status="delayed",
                          deliverables_due=3, deliverables_accepted=3),
            ],
            resources=[
                ResourceRecord(resource_id="R1", role="lead_engineer",
                               planned_fte=1.0, actual_fte=1.0,
                               qualification_required="PE", qualification_verified=True),
                ResourceRecord(resource_id="R2", role="welder",
                               planned_fte=4.0, actual_fte=1.5,
                               qualification_required="AWS", qualification_verified=False),
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

        builder = DeliveryGraphBuilder()
        builder.build_graph(dossier)

        # Graph populated
        assert dossier.graph is not None
        assert dossier.graph.node_count > 0
        assert dossier.graph.edge_count > 0

        # Rules result populated
        assert dossier.rules_result is not None
        assert dossier.rules_result.rules_evaluated == 12
        assert dossier.rules_result.rules_fired > 0

        # Base nodes present
        ids = _node_ids(dossier.graph)
        assert "contract" in ids
        assert "schedule" in ids
        assert "budget" in ids
        assert "delivery_outcome" in ids

        # Data-driven nodes present
        assert "milestone_M1" in ids
        assert "milestone_M2" in ids
        assert "resource_R1" in ids
        assert "resource_R2" in ids
        assert "resource_R3" in ids
        assert "outcome_O1" in ids
        assert "outcome_O2" in ids
        assert "financial_F1" in ids
        assert "financial_F2" in ids

        # Edge types present
        edge_types = {e["type"] for e in dossier.graph.edges}
        assert "EXPRESSES" in edge_types
        assert "BOUNDS" in edge_types
        assert "SEEKS" in edge_types      # from delayed milestones
        assert "REMOVES" in edge_types    # from fired rules

        # Report consistent
        report = builder.last_report
        assert report.nodes_total == dossier.graph.node_count
        assert report.edges_total == dossier.graph.edge_count
        assert report.total_rules_evaluated == 12
        assert len(report.rule_fire_log) == 12

        # All 4 layers should be active
        assert set(report.layers_active) == {"milestone", "resource", "outcome", "financial"}
