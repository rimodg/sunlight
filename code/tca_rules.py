"""
SUNLIGHT TCA Rule Engine
=========================

Deterministic structural graph construction.
Same contract + same rules = same graph = same TCA score.
On any machine. With any LLM. Without any LLM. Forever.

Architecture:
    - The LLM DISCOVERS patterns (research role)
    - The Rule Engine CODIFIES them (execution role)
    - TCA CALCULATES structural integrity (analysis role)
    These three roles are architecturally separated.

Each rule is:
    CONDITION → GRAPH OPERATION → EVIDENCE CITATION
    - Deterministic: same data always triggers the same rule
    - Citeable: every rule has a legal/academic evidence base
    - Auditable: the rule set is version-controlled and publishable
    - Testable: each rule can be unit tested against known cases

Evidence model: ENRICHMENT LAYERS within a single graph.
    Layer 0: Procurement flow (buyer → award → process → oversight)
    Layer 1: Entity patterns (ownership, shared addresses, shells)
    Layer 2: Financial patterns (price vs peers, markup, award inflation)
    Layer 3: Temporal patterns (fiscal pressure, vendor trajectory)
    Layer 4: Network patterns (concentration, geographic mismatch)

Each layer ADDS nodes and edges to ONE graph. Empty layers add nothing.
Contradictions COMPOUND in one score instead of DILUTING across dimensions.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
Rule Set Version: RS-2026-03-001
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# SECTION 1: RULE DEFINITION
# ═══════════════════════════════════════════════════════════

@dataclass
class Rule:
    """
    A single structural detection rule.

    Each rule is a deterministic mapping from contract data
    to graph operations. When the condition fires, nodes and
    edges are added to the procurement graph.
    """
    rule_id: str                    # Unique identifier (e.g., "PROC-001")
    layer: str                      # Which enrichment layer ("procurement", "entity", etc.)
    name: str                       # Human-readable name
    description: str                # What this rule detects
    evidence: str                   # Legal/academic citation
    condition: Callable             # Function(dossier_fields) → bool
    nodes: Callable                 # Function(dossier_fields) → list of node dicts
    edges: Callable                 # Function(dossier_fields) → list of edge dicts


@dataclass
class RuleResult:
    """What happened when a rule was evaluated."""
    rule_id: str
    fired: bool
    nodes_added: int = 0
    edges_added: int = 0


@dataclass
class GraphBuildReport:
    """Complete audit trail of how a graph was constructed."""
    total_rules_evaluated: int
    rules_fired: int
    rules_skipped: int
    nodes_total: int
    edges_total: int
    layers_active: List[str]
    results: List[RuleResult]
    rule_set_version: str = "RS-2026-03-001"


# ═══════════════════════════════════════════════════════════
# SECTION 2: HELPER — Extract fields safely from dossier
# ═══════════════════════════════════════════════════════════

def _extract(dossier) -> Dict:
    """
    Extract all relevant fields from a ContractDossier into
    a flat dict that rules can evaluate against.
    """
    parties = dossier.raw_ocds.get("parties", [])
    tender = dossier.raw_ocds.get("tender", {})
    awards = dossier.raw_ocds.get("awards", [{}])
    award = awards[0] if awards else {}

    suppliers = [p for p in parties
                 if "supplier" in str(p.get("roles", [])).lower()
                 or "tenderer" in str(p.get("roles", [])).lower()]
    buyers = [p for p in parties
              if "buyer" in str(p.get("roles", [])).lower()]

    # Supplier addresses
    supplier_addresses = []
    for s in suppliers:
        addr = s.get("address", {})
        street = addr.get("streetAddress", "")
        if street:
            supplier_addresses.append(street.strip().lower())

    # Supplier IDs
    supplier_ids = [s.get("id", s.get("name", "")) for s in suppliers]

    # Award date parsing
    award_month = None
    award_day = None
    award_date_str = dossier.award_date or award.get("date", "")
    if award_date_str:
        try:
            dt = datetime.fromisoformat(award_date_str.replace("Z", "+00:00"))
            award_month = dt.month
            award_day = dt.day
        except (ValueError, TypeError):
            pass

    # Supplier countries
    supplier_countries = []
    for s in suppliers:
        addr = s.get("address", {})
        c = addr.get("countryName", "")
        if c:
            supplier_countries.append(c.strip().lower())

    # Review body
    has_review_body = any(
        "review" in str(p.get("roles", [])).lower()
        or "oversight" in str(p.get("roles", [])).lower()
        for p in parties
    )

    return {
        "procurement_method": dossier.procurement_method,
        "tender_value": dossier.tender_value,
        "award_value": dossier.award_value,
        "currency": dossier.currency,
        "number_of_tenderers": dossier.number_of_tenderers,
        "buyer_name": dossier.buyer_name,
        "supplier_name": dossier.supplier_name,
        "suppliers": suppliers,
        "supplier_count": len(suppliers),
        "supplier_ids": supplier_ids,
        "supplier_addresses": supplier_addresses,
        "supplier_countries": supplier_countries,
        "country_code": dossier.country_code.lower() if dossier.country_code else "",
        "award_month": award_month,
        "award_day": award_day,
        "has_review_body": has_review_body,
        "sector": dossier.sector,
        "award_date": award_date_str,
        "parties": parties,
        "tender": tender,
        "award": award,
    }


# ═══════════════════════════════════════════════════════════
# SECTION 3: CURRENCY-AWARE THRESHOLDS
# ═══════════════════════════════════════════════════════════

COMPETITIVE_THRESHOLDS = {
    "USD": 100_000, "EUR": 90_000, "GBP": 80_000,
    "PYG": 750_000_000, "COP": 400_000_000, "MXN": 1_700_000,
    "UAH": 4_000_000, "XOF": 60_000_000, "NGN": 100_000_000,
    "KES": 10_000_000, "ZAR": 1_500_000, "BRL": 500_000,
    "INR": 8_000_000, "BDT": 10_000_000,
}

def _threshold(currency: str) -> float:
    return COMPETITIVE_THRESHOLDS.get(currency, 100_000)


# ═══════════════════════════════════════════════════════════
# SECTION 4: THE RULES
# Organized by enrichment layer. Each rule is grounded in
# a specific legal case, institutional policy, or academic paper.
# ═══════════════════════════════════════════════════════════

RULES: List[Rule] = []

# ─────────────────────────────────────────
# LAYER 0: PROCUREMENT FLOW
# Base topology: how the procurement process ran
# ─────────────────────────────────────────

RULES.append(Rule(
    rule_id="PROC-001",
    layer="procurement",
    name="Direct award above competitive threshold",
    description="Contract awarded without competition above the value threshold requiring competitive process",
    evidence="UNCAC Art. 9(1); UNDP POPP Procurement Methods Policy; FAR Part 6",
    condition=lambda f: (
        f["procurement_method"] in ("direct", "limited", "sole_source")
        and f["tender_value"] > _threshold(f["currency"])
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "process", "type": "REMOVES", "weight": 0.9,
        "rule": "PROC-001",
        "description": f"Direct award of {f['currency']} {f['tender_value']:,.0f} exceeds competitive threshold ({f['currency']} {_threshold(f['currency']):,.0f})"
    }],
))

RULES.append(Rule(
    rule_id="PROC-002",
    layer="procurement",
    name="Single bidder in competitive tender",
    description="Only one entity submitted a bid in a process designed for competition",
    evidence="Fazekas single-bidding indicator; UNDP Anti-Corruption Compass Indicator 1",
    condition=lambda f: (
        f["number_of_tenderers"] is not None
        and f["number_of_tenderers"] <= 1
        and f["procurement_method"] in ("open", "selective", "competitive")
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "process", "type": "REMOVES", "weight": 1.0,
        "rule": "PROC-002",
        "description": f"Single bidder ({f['number_of_tenderers']}) in nominally competitive tender"
    }],
))

RULES.append(Rule(
    rule_id="PROC-003",
    layer="procurement",
    name="No oversight body identified",
    description="No review body or oversight entity found in OCDS parties",
    evidence="UNCAC Art. 9(1)(d); UNDP POPP Procurement Oversight policy",
    condition=lambda f: not f["has_review_body"],
    nodes=lambda f: [{"id": "oversight", "label": "Oversight (Absent)"}],
    edges=lambda f: [{
        "source": "award", "target": "oversight", "type": "SEEKS", "weight": 0.4,
        "rule": "PROC-003",
        "description": "No review body identified in procurement record"
    }],
))

RULES.append(Rule(
    rule_id="PROC-004",
    layer="procurement",
    name="Oversight body present",
    description="A review body or oversight entity is documented in the procurement record",
    evidence="UNCAC Art. 9(1)(d); UNDP POPP Procurement Oversight policy",
    condition=lambda f: f["has_review_body"],
    nodes=lambda f: [{"id": "oversight", "label": "Oversight Body"}],
    edges=lambda f: [{
        "source": "oversight", "target": "award", "type": "VERIFIES", "weight": 0.8,
        "rule": "PROC-004",
        "description": "Review body documented in procurement record"
    }],
))

RULES.append(Rule(
    rule_id="PROC-005",
    layer="procurement",
    name="Low bidder count in competitive tender",
    description="Fewer than 3 bidders in a process designed for open competition",
    evidence="OECD Competition Assessment Toolkit; World Bank Procurement Framework",
    condition=lambda f: (
        f["number_of_tenderers"] is not None
        and 1 < f["number_of_tenderers"] < 3
        and f["procurement_method"] in ("open", "selective", "competitive")
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "process", "type": "BOUNDS", "weight": 0.6,
        "rule": "PROC-005",
        "description": f"Only {f['number_of_tenderers']} bidders in competitive tender (minimum 3 expected)"
    }],
))


# ─────────────────────────────────────────
# LAYER 1: ENTITY ENRICHMENT
# Ownership, independence, and shell indicators
# ─────────────────────────────────────────

RULES.append(Rule(
    rule_id="ENT-001",
    layer="entity",
    name="Multiple bidders share registered address",
    description="Two or more bidding entities registered at the same street address",
    evidence="DOJ US v. Marquez (Maryland 2024): two companies at 7100 Columbia Gateway Dr submitted coordinated bids",
    condition=lambda f: (
        len(f["supplier_addresses"]) >= 2
        and len(f["supplier_addresses"]) != len(set(f["supplier_addresses"]))
    ),
    nodes=lambda f: [{"id": "fabricated_competition", "label": "Bidder Independence"}],
    edges=lambda f: [{
        "source": "shared_address", "target": "fabricated_competition",
        "type": "REMOVES", "weight": 0.95,
        "rule": "ENT-001",
        "description": "Multiple bidders share registered address — fabricated competition indicator"
    }, {
        "source": "shared_address", "target": "fabricated_competition",
        "type": "REMOVES", "weight": 0.0,  # placeholder for node
        "rule": "ENT-001",
    }] if False else [{
        "source": "ent_shared_addr", "target": "competition",
        "type": "REMOVES", "weight": 0.95,
        "rule": "ENT-001",
        "description": "Multiple bidders share registered address — fabricated competition indicator"
    }],
))

RULES.append(Rule(
    rule_id="ENT-002",
    layer="entity",
    name="Duplicate entity identifiers among bidders",
    description="Two or more bidding entities share the same ID or name",
    evidence="DOJ US v. Marquez: Marquez IT Co 1 and Marquez IT Co 2 owned by same individual",
    condition=lambda f: (
        len(f["supplier_ids"]) >= 2
        and len(f["supplier_ids"]) != len(set(f["supplier_ids"]))
    ),
    nodes=lambda f: [{"id": "ent_duplicate", "label": "Entity Duplication Detected"}],
    edges=lambda f: [{
        "source": "ent_duplicate", "target": "competition",
        "type": "REMOVES", "weight": 1.0,
        "rule": "ENT-002",
        "description": "Duplicate entity identifiers among bidders — same entity bidding twice"
    }],
))

RULES.append(Rule(
    rule_id="ENT-003",
    layer="entity",
    name="Single supplier dominance",
    description="Only one supplier entity in a contract that had multiple bidders",
    evidence="OECD Guidelines on Corporate Governance; World Bank debarment case patterns",
    condition=lambda f: (
        f["supplier_count"] == 1
        and f["number_of_tenderers"] is not None
        and f["number_of_tenderers"] >= 3
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "supplier_0",
        "type": "EXPRESSES", "weight": 0.8,
        "rule": "ENT-003",
        "description": f"Single supplier won against {f['number_of_tenderers']} bidders — normal competitive outcome"
    }],
))


# ─────────────────────────────────────────
# LAYER 2: FINANCIAL ENRICHMENT
# Price patterns, markup, award inflation
# ─────────────────────────────────────────

RULES.append(Rule(
    rule_id="FIN-001",
    layer="financial",
    name="Award significantly exceeds tender value",
    description="Award amount exceeds tender estimate by more than 15%",
    evidence="World Bank Procurement Framework; UNDP POPP Contract Modifications policy",
    condition=lambda f: (
        f["tender_value"] > 0
        and f["award_value"] > 0
        and f["award_value"] / f["tender_value"] > 1.15
    ),
    nodes=lambda f: [{"id": "price_inflation", "label": "Post-Tender Price Inflation"}],
    edges=lambda f: [{
        "source": "price_inflation", "target": "budget",
        "type": "REMOVES", "weight": 0.8,
        "rule": "FIN-001",
        "description": f"Award ({f['currency']} {f['award_value']:,.0f}) exceeds tender ({f['currency']} {f['tender_value']:,.0f}) by {((f['award_value']/f['tender_value'])-1)*100:.1f}%"
    }],
))

RULES.append(Rule(
    rule_id="FIN-002",
    layer="financial",
    name="Award matches tender exactly",
    description="Award amount equals tender estimate to the dollar — possible pre-determination",
    evidence="DOJ bid rigging prosecution patterns; Fazekas price analysis methodology",
    condition=lambda f: (
        f["tender_value"] > 0
        and f["award_value"] > 0
        and f["tender_value"] == f["award_value"]
        and f["number_of_tenderers"] is not None
        and f["number_of_tenderers"] >= 2
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "budget",
        "type": "BOUNDS", "weight": 0.6,
        "rule": "FIN-002",
        "description": f"Award exactly matches tender value ({f['currency']} {f['tender_value']:,.0f}) with {f['number_of_tenderers']} bidders — possible pre-determination"
    }],
))

RULES.append(Rule(
    rule_id="FIN-003",
    layer="financial",
    name="Award closely matches tender (within 5%)",
    description="Award value is within 5% of tender estimate — normal competitive outcome",
    evidence="Standard procurement practice; OECD value-for-money benchmarks",
    condition=lambda f: (
        f["tender_value"] > 0
        and f["award_value"] > 0
        and f["tender_value"] != f["award_value"]
        and 0.95 <= f["award_value"] / f["tender_value"] <= 1.05
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "budget",
        "type": "VERIFIES", "weight": 0.7,
        "rule": "FIN-003",
        "description": "Award within 5% of tender value — normal competitive pricing"
    }],
))


# ─────────────────────────────────────────
# LAYER 3: TEMPORAL ENRICHMENT
# Fiscal pressure, timing patterns
# ─────────────────────────────────────────

RULES.append(Rule(
    rule_id="TIME-001",
    layer="temporal",
    name="Award in final 2 weeks of fiscal period",
    description="Contract awarded in the last 15 days of a common fiscal year-end month",
    evidence="Fazekas fiscal pressure research; OECD public procurement timing analysis; Senegal case (award 8 days before fiscal close)",
    condition=lambda f: (
        f["award_month"] is not None
        and f["award_day"] is not None
        and (
            (f["award_month"] == 12 and f["award_day"] >= 15)
            or (f["award_month"] == 6 and f["award_day"] >= 15)
            or (f["award_month"] == 3 and f["award_day"] >= 25)
            or (f["award_month"] == 9 and f["award_day"] >= 25)
        )
    ),
    nodes=lambda f: [{"id": "fiscal_pressure", "label": "Fiscal Year-End Pressure"}],
    edges=lambda f: [{
        "source": "fiscal_pressure", "target": "award",
        "type": "REMOVES", "weight": 0.7,
        "rule": "TIME-001",
        "description": f"Award in final 2 weeks of fiscal period (month {f['award_month']}, day {f['award_day']})"
    }],
))

RULES.append(Rule(
    rule_id="TIME-002",
    layer="temporal",
    name="Award in final quarter of fiscal period",
    description="Contract awarded in the last quarter of a fiscal year — moderate pressure indicator",
    evidence="OECD procurement timing studies; budget cycle analysis",
    condition=lambda f: (
        f["award_month"] is not None
        and f["award_month"] in (10, 11, 12, 4, 5, 6)
        and not (  # Don't double-count with TIME-001
            f["award_day"] is not None
            and (
                (f["award_month"] == 12 and f["award_day"] >= 15)
                or (f["award_month"] == 6 and f["award_day"] >= 15)
            )
        )
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "budget",
        "type": "BOUNDS", "weight": 0.5,
        "rule": "TIME-002",
        "description": f"Award in final quarter of fiscal period (month {f['award_month']})"
    }],
))

RULES.append(Rule(
    rule_id="TIME-003",
    layer="temporal",
    name="Award timing shows no fiscal pressure",
    description="Contract awarded outside fiscal pressure periods",
    evidence="Baseline: absence of timing anomaly is a positive structural signal",
    condition=lambda f: (
        f["award_month"] is not None
        and f["award_month"] in (1, 2, 7, 8)
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "award", "target": "budget",
        "type": "VERIFIES", "weight": 0.5,
        "rule": "TIME-003",
        "description": "Award timing shows no fiscal year-end pressure"
    }],
))


# ─────────────────────────────────────────
# LAYER 4: NETWORK / GEOGRAPHIC ENRICHMENT
# Geographic mismatch, concentration
# ─────────────────────────────────────────

RULES.append(Rule(
    rule_id="GEO-001",
    layer="network",
    name="Supplier jurisdiction mismatch",
    description="Supplier registered in a different country than the contract location with no local presence",
    evidence="FATF risk indicators; World Bank debarment for cross-jurisdictional fraud",
    condition=lambda f: (
        f["country_code"]
        and f["supplier_countries"]
        and any(
            sc != f["country_code"] and sc != "unknown"
            for sc in f["supplier_countries"]
        )
    ),
    nodes=lambda f: [{"id": "geo_mismatch", "label": "Geographic Mismatch"}],
    edges=lambda f: [{
        "source": "geo_mismatch", "target": "supplier_0",
        "type": "REMOVES", "weight": 0.7,
        "rule": "GEO-001",
        "description": f"Supplier in {f['supplier_countries'][0]} but contract in {f['country_code']} — geographic mismatch"
    }],
))

RULES.append(Rule(
    rule_id="GEO-002",
    layer="network",
    name="Supplier jurisdiction matches contract",
    description="Supplier registered in the same country as contract execution",
    evidence="Positive structural signal: local presence verified",
    condition=lambda f: (
        f["country_code"]
        and f["supplier_countries"]
        and all(
            sc == f["country_code"]
            for sc in f["supplier_countries"]
            if sc and sc != "unknown"
        )
        and any(sc and sc != "unknown" for sc in f["supplier_countries"])
    ),
    nodes=lambda f: [],
    edges=lambda f: [{
        "source": "supplier_0", "target": "award",
        "type": "VERIFIES", "weight": 0.5,
        "rule": "GEO-002",
        "description": "Supplier jurisdiction matches contract location"
    }],
))


# ═══════════════════════════════════════════════════════════
# SECTION 5: THE RULE ENGINE
# Evaluates all rules against a contract, builds one enriched graph
# ═══════════════════════════════════════════════════════════

class TCAGraphRuleEngine:
    """
    Deterministic, auditable, universal graph construction.

    Evaluates every rule against the contract data.
    Rules that fire add nodes and edges to ONE graph.
    Rules that don't fire add nothing.
    The graph is the sum of all structural evidence.

    Implements GraphEngine Protocol from sunlight_core.py.
    """

    def __init__(self, rules: Optional[List[Rule]] = None):
        self.rules = rules or RULES
        self.last_report: Optional[GraphBuildReport] = None

    def build_graph(self, dossier) -> Any:
        """
        Build an enriched TCA graph from deterministic rules.
        Implements GraphEngine Protocol.
        """
        f = _extract(dossier)

        # Base graph — always present
        nodes = [
            {"id": "buyer", "label": f["buyer_name"] or "Buyer"},
            {"id": "award", "label": "Award Decision"},
            {"id": "process", "label": f["procurement_method"] or "Process"},
            {"id": "budget", "label": f"Budget ({f['currency']} {f['tender_value']:,.0f})"},
            {"id": "competition", "label": "Competitive Process"},
        ]
        edges = [
            {"source": "buyer", "target": "award", "type": "EXPRESSES", "weight": 1.0,
             "rule": "BASE", "description": "Buyer initiates award decision"},
            {"source": "process", "target": "award", "type": "BOUNDS", "weight": 0.8,
             "rule": "BASE", "description": "Procurement method constrains award"},
            {"source": "budget", "target": "award", "type": "BOUNDS", "weight": 0.9,
             "rule": "BASE", "description": "Budget constrains award value"},
            {"source": "competition", "target": "award", "type": "BOUNDS", "weight": 0.7,
             "rule": "BASE", "description": "Competition constrains award quality"},
        ]

        # Add supplier nodes
        for i, s in enumerate(f["suppliers"]):
            sid = f"supplier_{i}"
            nodes.append({"id": sid, "label": s.get("name", f"Supplier {i}")})
            edges.append({
                "source": "award", "target": sid, "type": "EXPRESSES", "weight": 0.9,
                "rule": "BASE", "description": f"Award to {s.get('name', 'supplier')}"
            })

        # Also add shared_address node if we'll need it
        addrs = f["supplier_addresses"]
        if len(addrs) >= 2 and len(addrs) != len(set(addrs)):
            nodes.append({"id": "ent_shared_addr", "label": "Shared Address Detected"})

        # Evaluate all rules
        results = []
        layers_active = set()

        for rule in self.rules:
            try:
                fired = rule.condition(f)
            except Exception:
                fired = False

            if fired:
                try:
                    new_nodes = rule.nodes(f)
                    new_edges = rule.edges(f)
                except Exception:
                    new_nodes = []
                    new_edges = []

                # Add nodes (avoid duplicates by id)
                existing_ids = {n["id"] for n in nodes}
                for n in new_nodes:
                    if n["id"] not in existing_ids:
                        nodes.append(n)
                        existing_ids.add(n["id"])

                # Add edges
                edges.extend(new_edges)
                layers_active.add(rule.layer)

                results.append(RuleResult(
                    rule_id=rule.rule_id,
                    fired=True,
                    nodes_added=len(new_nodes),
                    edges_added=len(new_edges),
                ))
            else:
                results.append(RuleResult(rule_id=rule.rule_id, fired=False))

        # Build audit report
        self.last_report = GraphBuildReport(
            total_rules_evaluated=len(self.rules),
            rules_fired=sum(1 for r in results if r.fired),
            rules_skipped=sum(1 for r in results if not r.fired),
            nodes_total=len(nodes),
            edges_total=len(edges),
            layers_active=sorted(layers_active),
            results=results,
        )

        graph = {
            "name": f"{dossier.ocid} — {dossier.buyer_name}",
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "rule_set_version": "RS-2026-03-001",
                "rules_fired": self.last_report.rules_fired,
                "layers_active": self.last_report.layers_active,
                "deterministic": True,
            }
        }

        dossier.graph = graph
        return dossier

    def audit(self) -> str:
        """Print which rules fired and why."""
        if not self.last_report:
            return "No graph built yet."

        r = self.last_report
        lines = [
            "═" * 60,
            "TCA RULE ENGINE — AUDIT REPORT",
            f"Rule Set: {r.rule_set_version}",
            "═" * 60,
            f"Rules evaluated:  {r.total_rules_evaluated}",
            f"Rules fired:      {r.rules_fired}",
            f"Rules skipped:    {r.rules_skipped}",
            f"Nodes in graph:   {r.nodes_total}",
            f"Edges in graph:   {r.edges_total}",
            f"Layers active:    {', '.join(r.layers_active) or 'base only'}",
            "",
            "RULES FIRED:",
        ]
        for result in r.results:
            if result.fired:
                rule = next((r for r in self.rules if r.rule_id == result.rule_id), None)
                if rule:
                    lines.append(f"  [{rule.rule_id}] {rule.name}")
                    lines.append(f"    Evidence: {rule.evidence}")
                    lines.append(f"    +{result.nodes_added} nodes, +{result.edges_added} edges")

        lines.append("")
        lines.append("RULES NOT FIRED:")
        for result in r.results:
            if not result.fired:
                rule = next((r for r in self.rules if r.rule_id == result.rule_id), None)
                if rule:
                    lines.append(f"  [{rule.rule_id}] {rule.name} — condition not met")

        lines.append("═" * 60)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# SECTION 6: ADAPTER — Protocol interface for sunlight_core.py
# ═══════════════════════════════════════════════════════════

class TCAGraphRuleEngineAdapter:
    """
    Implements GraphEngine Protocol from sunlight_core.py.
    Drop-in replacement for OCDSGraphAdapter.

    Usage:
        from tca_rules import TCAGraphRuleEngineAdapter
        pipeline = SunlightPipeline(grapher=TCAGraphRuleEngineAdapter())
    """
    def __init__(self):
        self.engine = TCAGraphRuleEngine()

    def build_graph(self, dossier):
        return self.engine.build_graph(dossier)


# ═══════════════════════════════════════════════════════════
# SECTION 7: DEMO
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Minimal ContractDossier mock for standalone testing
    class MockDossier:
        def __init__(self, raw, **kwargs):
            self.raw_ocds = raw
            self.ocid = raw.get("ocid", "")
            self.graph = None
            for k, v in kwargs.items():
                setattr(self, k, v)

    engine = TCAGraphRuleEngine()

    # ── Case 1: Senegal ──
    senegal = MockDossier(
        raw={
            "ocid": "ocds-SN-ARMP-2025-0847",
            "parties": [
                {"name": "Agence Routière du Sénégal", "roles": ["buyer"]},
                {"name": "SGT SA", "id": "SN-SGT-001", "roles": ["supplier"]},
            ],
            "tender": {"procurementMethod": "direct", "numberOfTenderers": 1},
            "awards": [{"date": "2025-06-22", "value": {"amount": 2450000}}],
        },
        buyer_name="Agence Routière du Sénégal",
        supplier_name="SGT SA",
        procurement_method="direct",
        tender_value=2_450_000,
        award_value=2_450_000,
        currency="USD",
        number_of_tenderers=1,
        award_date="2025-06-22",
        country_code="SN",
        sector="works",
    )

    engine.build_graph(senegal)
    print("═" * 60)
    print("CASE 1: SENEGAL")
    print("═" * 60)
    removes = [e for e in senegal.graph["edges"] if e["type"] == "REMOVES"]
    seeks = [e for e in senegal.graph["edges"] if e["type"] == "SEEKS"]
    verifies = [e for e in senegal.graph["edges"] if e["type"] == "VERIFIES"]
    print(f"Nodes: {len(senegal.graph['nodes'])}")
    print(f"Edges: {len(senegal.graph['edges'])}")
    print(f"REMOVES: {len(removes)}, SEEKS: {len(seeks)}, VERIFIES: {len(verifies)}")
    for e in removes:
        print(f"  ✗ {e.get('description', '')}")
    print(f"Layers: {senegal.graph['metadata']['layers_active']}")
    print()
    print(engine.audit())
    print()

    # ── Case 2: Marquez ──
    marquez = MockDossier(
        raw={
            "ocid": "ocds-US-DOD-IT-2024-MARQUEZ",
            "parties": [
                {"name": "Department of Defense", "roles": ["buyer"],
                 "address": {"countryName": "US"}},
                {"name": "Marquez IT Co 1", "id": "US-MARQUEZ-001", "roles": ["supplier", "tenderer"],
                 "address": {"countryName": "US", "streetAddress": "7100 Columbia Gateway Dr"}},
                {"name": "Marquez IT Co 2", "id": "US-MARQUEZ-002", "roles": ["tenderer"],
                 "address": {"countryName": "US", "streetAddress": "7100 Columbia Gateway Dr"}},
                {"name": "Reefe Corp", "id": "US-REEFE-001", "roles": ["tenderer"],
                 "address": {"countryName": "US", "streetAddress": "1900 Reston Metro Plz"}},
            ],
            "tender": {"procurementMethod": "open", "numberOfTenderers": 3},
            "awards": [{"date": "2024-12-18", "value": {"amount": 6800000}}],
        },
        buyer_name="Department of Defense",
        supplier_name="Marquez IT Co 1",
        procurement_method="open",
        tender_value=5_200_000,
        award_value=6_800_000,
        currency="USD",
        number_of_tenderers=3,
        award_date="2024-12-18",
        country_code="us",
        sector="goods",
    )

    engine.build_graph(marquez)
    print("═" * 60)
    print("CASE 2: MARQUEZ")
    print("═" * 60)
    removes = [e for e in marquez.graph["edges"] if e["type"] == "REMOVES"]
    seeks = [e for e in marquez.graph["edges"] if e["type"] == "SEEKS"]
    verifies = [e for e in marquez.graph["edges"] if e["type"] == "VERIFIES"]
    print(f"Nodes: {len(marquez.graph['nodes'])}")
    print(f"Edges: {len(marquez.graph['edges'])}")
    print(f"REMOVES: {len(removes)}, SEEKS: {len(seeks)}, VERIFIES: {len(verifies)}")
    for e in removes:
        print(f"  ✗ {e.get('description', '')}")
    for e in verifies:
        print(f"  ✓ {e.get('description', '')}")
    print(f"Layers: {marquez.graph['metadata']['layers_active']}")
    print()
    print(engine.audit())
