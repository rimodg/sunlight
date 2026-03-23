"""
SUNLIGHT — TCA Procurement Graph Builder
Maps OCDS procurement contract data into TCA typed graphs for structural analysis.

This is the bridge between raw procurement data and the general-purpose TCA engine.
It translates domain knowledge about procurement processes into typed edges that
TCA can analyze for structural contradictions.

The graph builder is the ONLY procurement-specific TCA code. The engine itself
(code/tca.py) is domain-agnostic.

Version: 4.0.0
Author: Rimwaya Ouedraogo
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from code.tca import (
    TCAEdge,
    TCAGraph,
    TCANode,
    TCAResult,
    analyze,
    build_graph,
)

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────────────

VENDOR_CONCENTRATION_THRESHOLD = 0.70
PRICE_BREAK_RATIO = 2.0
FISCAL_YEAR_END_DAYS = 15


# ── PROCUREMENT GRAPH BUILDER ────────────────────────────────────────────────

def build_procurement_graph(
    contract: Dict[str, Any],
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> TCAGraph:
    """
    Translate an OCDS contract record into a TCA typed graph.

    Node mapping:
        buyer          — the contracting authority
        vendor_{id}    — each bidder/tenderer
        award          — the award decision
        tender_process — the procurement method used
        budget         — the budget/funding source
        oversight      — regulatory oversight body

    Edge mapping encodes procurement domain knowledge as topology:
        Competitive + multiple bidders → tender_process EXPRESSES award (healthy)
        Sole-source / direct award    → buyer EXPRESSES award (skips process)
        Multiple independent vendors  → vendor_a MIRRORS vendor_b
        Vendor concentration > 70%    → vendor BOUNDS buyer (power inversion)
        Price within CI               → award VERIFIES budget
        Price outside CI              → award REMOVES budget
        End-of-fiscal-year            → budget BOUNDS award
        Oversight reviewed            → oversight VERIFIES award
        Oversight missing             → award SEEKS oversight
        EVG fabricated competition    → vendor_a INHERITS vendor_b (not independent)

    Args:
        contract: OCDS-formatted contract record
        portfolio_context: Optional prior contracts from same buyer/vendor
            Keys: vendor_share (float), buyer_contracts (list), evg (dict)

    Returns:
        TCAGraph ready for analysis
    """
    nodes: List[TCANode] = []
    edges: List[TCAEdge] = []

    # ── Extract contract fields ──
    contract_id = contract.get("id", contract.get("ocid", "unknown"))
    buyer_name = contract.get("buyer", {}).get("name", contract.get("agency_name", "Unknown Buyer"))
    buyer_id = contract.get("buyer", {}).get("id", contract.get("agency_id", "buyer"))

    procurement_method = contract.get("procurement_method",
                         contract.get("tender", {}).get("procurementMethod", "open"))

    vendors = contract.get("vendors", contract.get("tenderers",
              contract.get("competing_vendors", [])))

    award_value = contract.get("award_value",
                  contract.get("value", {}).get("amount",
                  contract.get("awards", [{}])[0].get("value", {}).get("amount") if contract.get("awards") else None))

    num_offers = contract.get("num_offers",
                 contract.get("numberOfTenderers", len(vendors)))

    # Timing
    award_date_str = contract.get("award_date",
                     contract.get("awards", [{}])[0].get("date") if contract.get("awards") else None)

    # Bootstrap CI from CRI (if available)
    bootstrap_ci = contract.get("bootstrap_ci", {})
    ci_lower = bootstrap_ci.get("lower")
    ci_upper = bootstrap_ci.get("upper")

    # Portfolio context
    portfolio = portfolio_context or {}
    vendor_share = portfolio.get("vendor_share", 0.0)
    evg_data = portfolio.get("evg", {})
    evg_class = evg_data.get("evg_class", "INDEPENDENT")

    # ── Build nodes ──
    nodes.append(TCANode(id="buyer", label=buyer_name))
    nodes.append(TCANode(id="award", label=f"Award: {contract_id}"))
    nodes.append(TCANode(id="tender_process", label=f"Process: {procurement_method}"))
    nodes.append(TCANode(id="budget", label="Budget / Expected Price"))

    # Add vendor nodes
    vendor_node_ids: List[str] = []
    for i, v in enumerate(vendors):
        vid = v.get("id", v.get("vendor_id", f"vendor_{i}"))
        vname = v.get("name", v.get("vendor_name", f"Vendor {i}"))
        node_id = f"vendor_{vid}"
        nodes.append(TCANode(id=node_id, label=vname))
        vendor_node_ids.append(node_id)

    # If no vendors listed but we have a primary vendor
    if not vendor_node_ids:
        primary_vendor = contract.get("vendor_name", contract.get("supplier", {}).get("name", "Unknown Vendor"))
        primary_vid = contract.get("vendor_id", "vendor_0")
        node_id = f"vendor_{primary_vid}"
        nodes.append(TCANode(id=node_id, label=primary_vendor))
        vendor_node_ids.append(node_id)

    # Oversight node
    has_oversight = contract.get("has_oversight", contract.get("review_body") is not None)
    nodes.append(TCANode(id="oversight", label="Oversight / Review Body"))

    # ── Build edges ──

    # 1. Procurement method → process integrity
    if procurement_method in ("open", "selective", "competitive"):
        if num_offers >= 2:
            # Healthy: competitive process produces award
            edges.append(TCAEdge(source="tender_process", target="award",
                                 edge_type="EXPRESSES", weight=1.0))
            # Buyer initiates tender properly
            edges.append(TCAEdge(source="buyer", target="tender_process",
                                 edge_type="EXPRESSES", weight=1.0))
        else:
            # Nominally competitive but only one bidder — contradiction
            edges.append(TCAEdge(source="tender_process", target="award",
                                 edge_type="EXPRESSES", weight=0.5))
            edges.append(TCAEdge(source="buyer", target="tender_process",
                                 edge_type="EXPRESSES", weight=1.0))
            # The single-bidder reality contradicts the competitive claim
            edges.append(TCAEdge(source="award", target="tender_process",
                                 edge_type="REMOVES", weight=0.8,
                                 metadata={"signal": "NO_COMPETITION",
                                           "detail": f"Only {num_offers} bidder(s) in competitive tender"}))
    elif procurement_method in ("limited", "direct", "sole-source"):
        # Sole-source: buyer directly produces award, skipping process
        edges.append(TCAEdge(source="buyer", target="award",
                             edge_type="EXPRESSES", weight=1.0))
        # Process exists but is bypassed
        edges.append(TCAEdge(source="buyer", target="tender_process",
                             edge_type="BOUNDS", weight=0.8))
        # Sole-source contradicts competitive ideal
        edges.append(TCAEdge(source="award", target="tender_process",
                             edge_type="REMOVES", weight=0.7,
                             metadata={"signal": "SOLE_SOURCE",
                                       "detail": f"Direct award, method: {procurement_method}"}))
    else:
        # Unknown method
        edges.append(TCAEdge(source="buyer", target="award",
                             edge_type="SEEKS", weight=0.5))
        edges.append(TCAEdge(source="tender_process", target="award",
                             edge_type="SEEKS", weight=0.5))

    # 2. Vendor relationships
    if len(vendor_node_ids) >= 2:
        if evg_class == "FABRICATED_COMPETITION":
            # Vendors are not independent — they derive from each other
            for i in range(len(vendor_node_ids)):
                for j in range(i + 1, len(vendor_node_ids)):
                    edges.append(TCAEdge(
                        source=vendor_node_ids[i], target=vendor_node_ids[j],
                        edge_type="INHERITS", weight=0.9,
                        metadata={"signal": "FABRICATED_COMPETITION",
                                  "detail": "EVG detected fabricated competition"}
                    ))
        elif evg_class == "SUSPICIOUS_COORDINATION":
            for i in range(len(vendor_node_ids)):
                for j in range(i + 1, len(vendor_node_ids)):
                    edges.append(TCAEdge(
                        source=vendor_node_ids[i], target=vendor_node_ids[j],
                        edge_type="SEEKS", weight=0.6,
                        metadata={"signal": "SUSPICIOUS_COORDINATION"}
                    ))
        else:
            # Independent vendors mirror each other (healthy competition)
            for i in range(len(vendor_node_ids)):
                for j in range(i + 1, len(vendor_node_ids)):
                    edges.append(TCAEdge(
                        source=vendor_node_ids[i], target=vendor_node_ids[j],
                        edge_type="MIRRORS", weight=1.0
                    ))

    # Winning vendor → award
    if vendor_node_ids:
        edges.append(TCAEdge(source=vendor_node_ids[0], target="award",
                             edge_type="EXPRESSES", weight=1.0))

    # 3. Price analysis
    if award_value is not None and ci_lower is not None and ci_upper is not None:
        if ci_lower <= award_value <= ci_upper:
            # Price within expected range — award verifies budget
            edges.append(TCAEdge(source="award", target="budget",
                                 edge_type="VERIFIES", weight=1.0,
                                 metadata={"detail": f"Price {award_value} within CI [{ci_lower}, {ci_upper}]"}))
        else:
            # Price outside CI — contradiction
            edges.append(TCAEdge(source="award", target="budget",
                                 edge_type="REMOVES", weight=0.8,
                                 metadata={"signal": "PRICE_ANOMALY",
                                           "detail": f"Price {award_value} outside CI [{ci_lower}, {ci_upper}]"}))
    else:
        # No price data to verify
        edges.append(TCAEdge(source="award", target="budget",
                             edge_type="SEEKS", weight=0.5))

    # 4. Price break analysis (if multiple bids available)
    bids = contract.get("bids", [])
    if len(bids) >= 2 and award_value:
        bid_amounts = sorted([b.get("amount", 0) for b in bids if b.get("amount")])
        if len(bid_amounts) >= 2 and bid_amounts[0] > 0:
            ratio = award_value / bid_amounts[0] if bid_amounts[0] != award_value else (
                award_value / bid_amounts[1] if len(bid_amounts) > 1 and bid_amounts[1] > 0 else 1.0
            )
            if ratio > PRICE_BREAK_RATIO:
                edges.append(TCAEdge(
                    source="award", target="tender_process",
                    edge_type="REMOVES", weight=0.7,
                    metadata={"signal": "PRICE_MIRROR_BREAK",
                              "detail": f"Award/next bid ratio: {ratio:.2f} > {PRICE_BREAK_RATIO}"}
                ))

    # 5. Vendor concentration
    if vendor_share > VENDOR_CONCENTRATION_THRESHOLD and vendor_node_ids:
        # Vendor controls buyer (power inversion)
        edges.append(TCAEdge(
            source=vendor_node_ids[0], target="buyer",
            edge_type="BOUNDS", weight=0.9,
            metadata={"signal": "VENDOR_CONCENTRATION",
                      "detail": f"Vendor share: {vendor_share:.0%} > {VENDOR_CONCENTRATION_THRESHOLD:.0%}"}
        ))

    # 6. Fiscal year-end timing
    if award_date_str:
        try:
            if isinstance(award_date_str, str):
                award_date = datetime.fromisoformat(award_date_str.replace("Z", "+00:00"))
            elif isinstance(award_date_str, datetime):
                award_date = award_date_str
            else:
                award_date = None

            if award_date:
                # Check proximity to common fiscal year ends
                month_day = (award_date.month, award_date.day)
                fiscal_ends = [(12, 31), (9, 30), (6, 30), (3, 31)]
                for fm, fd in fiscal_ends:
                    try:
                        fy_end = award_date.replace(month=fm, day=fd)
                        days_to_end = abs((fy_end - award_date).days)
                        if days_to_end <= FISCAL_YEAR_END_DAYS:
                            edges.append(TCAEdge(
                                source="budget", target="award",
                                edge_type="BOUNDS", weight=0.7,
                                metadata={"signal": "FISCAL_TRAP",
                                          "detail": f"Award {days_to_end} days from fiscal year end"}
                            ))
                            break
                    except ValueError:
                        continue
        except (ValueError, TypeError):
            pass

    # 7. Oversight
    if has_oversight:
        edges.append(TCAEdge(source="oversight", target="award",
                             edge_type="VERIFIES", weight=1.0))
    else:
        edges.append(TCAEdge(source="award", target="oversight",
                             edge_type="SEEKS", weight=0.8,
                             metadata={"signal": "NO_OVERSIGHT",
                                       "detail": "No oversight review on record"}))

    return TCAGraph(
        name=f"Procurement: {contract_id}",
        nodes=nodes,
        edges=edges,
        mode="standard",
    )


# ── CLASSIFICATION ───────────────────────────────────────────────────────────

def classify_procurement(tca_result: TCAResult) -> str:
    """
    Classify procurement contract based on TCA structural analysis.

    Returns:
        "HONEST"                 — 0 contradictions, grounding > 0.6
        "SUSPICIOUS"             — 1-2 contradictions OR grounding 0.3-0.6
        "STRUCTURALLY_FRAUDULENT" — 3+ contradictions OR grounding < 0.3
    """
    n_contradictions = len(tca_result.contradictions)
    grounding = tca_result.grounding_ratio

    if n_contradictions >= 3 or grounding < 0.3:
        return "STRUCTURALLY_FRAUDULENT"
    elif n_contradictions >= 1 or grounding < 0.6:
        return "SUSPICIOUS"
    else:
        return "HONEST"


# ── PIPELINE INTEGRATION ────────────────────────────────────────────────────

def run_tca(
    contract: Dict[str, Any],
    portfolio_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run full TCA analysis on a procurement contract.
    Drop-in replacement for the old build_contract_graph().

    Args:
        contract: OCDS-formatted contract record
        portfolio_context: Optional context (vendor_share, evg results, etc.)

    Returns:
        Dict with topology_class, confidence, contradictions, feedback_traps,
        dead_ends, unproven_assumptions, load_bearing_nodes, grounding_ratio,
        edge_type_distribution, cascade_results.
    """
    graph = build_procurement_graph(contract, portfolio_context)
    result = analyze(graph, run_cascade=True)
    topology_class = classify_procurement(result)

    return {
        "topology_class": topology_class,
        "confidence": result.confidence,
        "contradictions": result.contradictions,
        "n_contradictions": len(result.contradictions),
        "feedback_traps": result.feedback_traps,
        "dead_ends": result.dead_ends,
        "unproven_assumptions": result.unproven_assumptions,
        "load_bearing_nodes": result.load_bearing_nodes,
        "grounding_ratio": result.grounding_ratio,
        "edge_type_distribution": result.edge_type_distribution,
        "cascade_results": result.cascade_results,
        "graph": graph.to_dict(),
    }
