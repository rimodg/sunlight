"""
SUNLIGHT Side 2 — Delivery Graph Construction
================================================

Builds a typed directed graph representing delivery topology.
Same delivery data + same rules = same graph. Forever.

Architecture:
    Mirrors TCAGraphRuleEngine.build_graph() from tca_rules.py:
    1. Construct base delivery graph (contract → milestones → outcomes → budget)
    2. Add milestone, resource, outcome, financial nodes from dossier data
    3. Evaluate delivery rules via DeliveryRuleEngine
    4. Annotate graph edges from fired rules
    5. Write DeliveryGraphResult to dossier.graph
    6. Write DeliveryRulesResult to dossier.rules_result

    Uses the same 7 TCA edge types (MIRRORS, INHERITS, BOUNDS, EXPRESSES,
    VERIFIES, REMOVES, SEEKS) applied to delivery relationships.

    The delivery graph captures:
    - Contract → Milestone schedule topology
    - Milestone → Deliverable acceptance topology
    - Resource → Role deployment topology
    - Outcome → Quality verification topology
    - Financial → Budget reconciliation topology

    Rule-fired edges add REMOVES (contradiction) or SEEKS (unverified)
    edges that compound in the structural score.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from delivery_schema import (
    DeliveryDossier,
    DeliveryGraphResult,
    DeliveryRulesResult,
    DeliveryStage,
)
from delivery_rules import DeliveryRuleEngine
from jurisdiction_profile import JurisdictionProfile


# ═══════════════════════════════════════════════════════════
# SECTION 1: GRAPH BUILD REPORT
# ═══════════════════════════════════════════════════════════


@dataclass
class DeliveryGraphBuildReport:
    """Complete audit trail of how a delivery graph was constructed."""
    total_rules_evaluated: int
    rules_fired: int
    rules_skipped: int
    nodes_total: int
    edges_total: int
    layers_active: List[str]
    rule_fire_log: Dict[str, bool] = field(default_factory=dict)
    rule_set_version: str = "DRS-2026-06-001"


# ═══════════════════════════════════════════════════════════
# SECTION 2: EDGE TYPE MAPPING
# ═══════════════════════════════════════════════════════════

# Maps delivery rule layers to the edge type emitted when a rule fires.
# Milestone/Resource/Outcome rules that fire indicate contradictions (REMOVES).
# Financial rules that fire indicate unverified claims (SEEKS or REMOVES
# depending on severity — the graph builder uses REMOVES for all fired
# rules since firing indicates a threshold breach).
FIRED_RULE_EDGE_TYPE = "REMOVES"

# Base structural edges use these types:
#   EXPRESSES — contract produces milestones, milestones produce deliverables
#   BOUNDS    — budget constrains spend, schedule constrains milestones
#   VERIFIES  — on-time milestone verifies schedule, full delivery verifies outcome


# ═══════════════════════════════════════════════════════════
# SECTION 3: DELIVERY GRAPH BUILDER
# ═══════════════════════════════════════════════════════════


class DeliveryGraphBuilder:
    """
    Deterministic delivery topology construction.

    Builds a typed directed graph from delivery dossier data,
    then enriches it with rule evaluation results.

    Mirrors TCAGraphRuleEngine from tca_rules.py but operates
    on DeliveryDossier instead of ContractDossier.
    """

    def __init__(self, profile: Optional[JurisdictionProfile] = None):
        from jurisdiction_profile import US_FEDERAL
        self.profile = profile or US_FEDERAL
        self.rule_engine = DeliveryRuleEngine(profile=self.profile)
        self.last_report: Optional[DeliveryGraphBuildReport] = None

    def build_graph(self, dossier: DeliveryDossier) -> DeliveryDossier:
        """
        Build the delivery topology graph and evaluate rules.

        Steps:
            1. Construct base graph nodes and edges from dossier data
            2. Evaluate all 12 delivery rules
            3. Add rule-fired edges to graph
            4. Write DeliveryGraphResult and DeliveryRulesResult to dossier

        Args:
            dossier: DeliveryDossier with populated input records.

        Returns:
            The same dossier with .graph and .rules_result populated.
        """
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        existing_ids: set = set()

        def _add_node(node_id: str, label: str, **metadata):
            if node_id not in existing_ids:
                node = {"id": node_id, "label": label}
                if metadata:
                    node["metadata"] = metadata
                nodes.append(node)
                existing_ids.add(node_id)

        # ── Base graph: always present ──
        _add_node("contract", f"Contract {dossier.contract_id or '(unknown)'}")
        _add_node("schedule", "Delivery Schedule")
        _add_node("budget", f"Budget ({dossier.total_budget:,.0f})")
        _add_node("delivery_outcome", "Delivery Outcome")

        edges.extend([
            {
                "source": "contract", "target": "schedule",
                "type": "EXPRESSES", "weight": 1.0,
                "rule": "BASE",
                "description": "Contract defines delivery schedule",
            },
            {
                "source": "contract", "target": "budget",
                "type": "BOUNDS", "weight": 0.9,
                "rule": "BASE",
                "description": "Contract budget constrains spend",
            },
            {
                "source": "schedule", "target": "delivery_outcome",
                "type": "BOUNDS", "weight": 0.8,
                "rule": "BASE",
                "description": "Schedule constrains delivery timeline",
            },
            {
                "source": "budget", "target": "delivery_outcome",
                "type": "BOUNDS", "weight": 0.8,
                "rule": "BASE",
                "description": "Budget constrains delivery scope",
            },
        ])

        # ── Milestone nodes ──
        for m in dossier.milestones:
            mid = f"milestone_{m.milestone_id}"
            _add_node(mid, f"Milestone: {m.description}", status=m.status)

            edges.append({
                "source": "schedule", "target": mid,
                "type": "EXPRESSES", "weight": 0.9,
                "rule": "BASE",
                "description": f"Schedule produces milestone {m.milestone_id}",
            })

            if m.delay_days == 0 and m.status == "completed":
                edges.append({
                    "source": mid, "target": "schedule",
                    "type": "VERIFIES", "weight": 0.7,
                    "rule": "BASE",
                    "description": f"Milestone {m.milestone_id} completed on time",
                })
            elif m.delay_days > 0:
                edges.append({
                    "source": mid, "target": "schedule",
                    "type": "SEEKS", "weight": 0.5,
                    "rule": "BASE",
                    "description": f"Milestone {m.milestone_id} delayed {m.delay_days} days",
                })

        # ── Resource nodes ──
        for r in dossier.resources:
            rid = f"resource_{r.resource_id}"
            _add_node(rid, f"Resource: {r.role}")

            edges.append({
                "source": "contract", "target": rid,
                "type": "EXPRESSES", "weight": 0.8,
                "rule": "BASE",
                "description": f"Contract requires {r.role}",
            })

            if r.planned_fte > 0 and r.actual_fte >= r.planned_fte:
                edges.append({
                    "source": rid, "target": "delivery_outcome",
                    "type": "VERIFIES", "weight": 0.6,
                    "rule": "BASE",
                    "description": f"{r.role} fully staffed ({r.actual_fte:.1f}/{r.planned_fte:.1f} FTE)",
                })
            elif r.planned_fte > 0 and r.actual_fte > 0:
                edges.append({
                    "source": rid, "target": "delivery_outcome",
                    "type": "SEEKS", "weight": 0.4,
                    "rule": "BASE",
                    "description": f"{r.role} understaffed ({r.actual_fte:.1f}/{r.planned_fte:.1f} FTE)",
                })

        # ── Outcome nodes ──
        for o in dossier.outcomes:
            oid = f"outcome_{o.outcome_id}"
            _add_node(oid, f"Outcome: {o.description}")

            edges.append({
                "source": "delivery_outcome", "target": oid,
                "type": "EXPRESSES", "weight": 0.9,
                "rule": "BASE",
                "description": f"Delivery produces {o.description}",
            })

            if o.quantity_planned > 0 and o.quantity_delivered >= o.quantity_planned:
                edges.append({
                    "source": oid, "target": "delivery_outcome",
                    "type": "VERIFIES", "weight": 0.7,
                    "rule": "BASE",
                    "description": f"{o.description} fully delivered",
                })

        # ── Financial nodes ──
        for f_rec in dossier.financials:
            fid = f"financial_{f_rec.line_item_id}"
            _add_node(fid, f"Line: {f_rec.description}")

            edges.append({
                "source": "budget", "target": fid,
                "type": "EXPRESSES", "weight": 0.8,
                "rule": "BASE",
                "description": f"Budget allocates to {f_rec.description}",
            })

            if f_rec.budgeted_amount > 0 and f_rec.actual_amount <= f_rec.budgeted_amount:
                edges.append({
                    "source": fid, "target": "budget",
                    "type": "VERIFIES", "weight": 0.6,
                    "rule": "BASE",
                    "description": f"{f_rec.description} within budget",
                })

        # ── Evaluate delivery rules ──
        rules_result = self.rule_engine.evaluate(dossier)

        # ── Add rule-fired edges to graph ──
        layers_active: set = set()
        for rr in rules_result.rule_results:
            if rr.fired:
                layers_active.add(rr.layer)

                # Determine source and target for the rule edge
                source_id, target_id = _rule_edge_endpoints(rr.rule_id, rr.layer)
                _add_node(source_id, f"Finding: {rr.rule_id}")

                edges.append({
                    "source": source_id,
                    "target": target_id,
                    "type": FIRED_RULE_EDGE_TYPE,
                    "weight": rr.confidence,
                    "rule": rr.rule_id,
                    "description": rr.evidence,
                })

        # ── Build audit report ──
        rule_fire_log = {rr.rule_id: rr.fired for rr in rules_result.rule_results}
        self.last_report = DeliveryGraphBuildReport(
            total_rules_evaluated=rules_result.rules_evaluated,
            rules_fired=rules_result.rules_fired,
            rules_skipped=rules_result.rules_evaluated - rules_result.rules_fired,
            nodes_total=len(nodes),
            edges_total=len(edges),
            layers_active=sorted(layers_active),
            rule_fire_log=rule_fire_log,
        )

        # ── Write results to dossier ──
        dossier.graph = DeliveryGraphResult(
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=nodes,
            edges=edges,
        )
        dossier.rules_result = rules_result

        return dossier


def _rule_edge_endpoints(rule_id: str, layer: str) -> tuple:
    """
    Map a delivery rule to its graph edge source/target.

    Each fired rule adds a REMOVES edge from a finding node
    to the structural element it contradicts.
    """
    target_map = {
        "milestone": "schedule",
        "resource": "delivery_outcome",
        "outcome": "delivery_outcome",
        "financial": "budget",
    }
    source_id = f"finding_{rule_id.lower().replace('-', '_')}"
    target_id = target_map.get(layer, "delivery_outcome")
    return source_id, target_id
