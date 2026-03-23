"""
SUNLIGHT — Topological Contradiction Analysis Engine (TCA)
Core structural diagnostic engine — general purpose, substrate-agnostic.

Theory: Every designed system has a topology — nodes connected by typed
relationships. Structural contradictions in that topology compound and
predict failure. TCA maps any system as a typed directed graph, detects
contradictions, feedback traps, dead ends, and single points of failure,
and prescribes minimum structural fixes.

Procurement fraud is the first application. The engine works on anything:
governance systems, development finance, institutional reform, business
models, supply chains, health infrastructure.

Seven Edge Types:
    MIRRORS   — A reflects/parallels B. Structural analogy.
    INHERITS  — A derives from/depends on B. Couldn't exist without B.
    BOUNDS    — A constrains/limits/controls B. Power structure.
    EXPRESSES — A produces/causes/creates B. Direct causal output.
    VERIFIES  — A proves/grounds B with evidence. Evidence that B is real.
    REMOVES   — A contradicts/destroys/undermines B. Structural conflict.
    SEEKS     — A wants B but hasn't proven it. Aspiration. Unverified.

Version: 4.0.0
Author: Rimwaya Ouedraogo & Hugo Villalba
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── CONSTANTS ────────────────────────────────────────────────────────────────

EDGE_TYPES = frozenset({
    "MIRRORS", "INHERITS", "BOUNDS", "EXPRESSES",
    "VERIFIES", "REMOVES", "SEEKS",
})

# Confidence penalties
PENALTY_REMOVES = 0.08
PENALTY_SEEKS = 0.04
PENALTY_FEEDBACK_TRAP = 0.06
PENALTY_DEAD_END = 0.03
PENALTY_STAR_TOPOLOGY = 0.05
BONUS_VERIFIES = 0.02
BONUS_VERIFIES_CAP = 0.15

# Thresholds
STAR_BETWEENNESS_THRESHOLD = 0.4
CASCADE_TOP_N = 5


# ── DATA CLASSES ─────────────────────────────────────────────────────────────

@dataclass
class TCANode:
    """A node in a TCA graph."""
    id: str
    label: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TCAEdge:
    """A typed directed edge in a TCA graph."""
    source: str
    target: str
    edge_type: str
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.edge_type not in EDGE_TYPES:
            raise ValueError(
                f"Invalid edge type '{self.edge_type}'. "
                f"Must be one of: {', '.join(sorted(EDGE_TYPES))}"
            )


@dataclass
class TCAGraph:
    """A typed directed graph for structural analysis."""
    name: str
    nodes: List[TCANode]
    edges: List[TCAEdge]
    mode: str = "standard"  # "standard" or "physics"

    def node_ids(self) -> Set[str]:
        return {n.id for n in self.nodes}

    def node_label(self, node_id: str) -> str:
        for n in self.nodes:
            if n.id == node_id:
                return n.label
        return node_id

    def edges_by_type(self, edge_type: str) -> List[TCAEdge]:
        return [e for e in self.edges if e.edge_type == edge_type]

    def adjacency(self) -> Dict[str, List[Tuple[str, str]]]:
        """Returns {source: [(target, edge_type), ...]}"""
        adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for e in self.edges:
            adj[e.source].append((e.target, e.edge_type))
        return adj

    def reverse_adjacency(self) -> Dict[str, List[Tuple[str, str]]]:
        """Returns {target: [(source, edge_type), ...]}"""
        rev: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for e in self.edges:
            rev[e.target].append((e.source, e.edge_type))
        return rev

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [{"id": n.id, "label": n.label, "metadata": n.metadata} for n in self.nodes],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.edge_type,
                 "weight": e.weight, "metadata": e.metadata}
                for e in self.edges
            ],
            "mode": self.mode,
        }


@dataclass
class TCAResult:
    """Complete TCA analysis result."""
    graph_name: str
    confidence: float
    contradictions: List[Dict[str, Any]]
    feedback_traps: List[List[str]]
    dead_ends: List[str]
    star_topologies: List[Dict[str, Any]]
    unproven_assumptions: List[Dict[str, Any]]
    load_bearing_nodes: List[Dict[str, Any]]
    edge_type_distribution: Dict[str, int]
    grounding_ratio: float
    n_nodes: int
    n_edges: int
    cascade_results: Optional[Dict[str, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_name": self.graph_name,
            "confidence": round(self.confidence, 4),
            "contradictions": self.contradictions,
            "n_contradictions": len(self.contradictions),
            "feedback_traps": self.feedback_traps,
            "n_feedback_traps": len(self.feedback_traps),
            "dead_ends": self.dead_ends,
            "n_dead_ends": len(self.dead_ends),
            "star_topologies": self.star_topologies,
            "unproven_assumptions": self.unproven_assumptions,
            "n_unproven": len(self.unproven_assumptions),
            "load_bearing_nodes": self.load_bearing_nodes,
            "edge_type_distribution": self.edge_type_distribution,
            "grounding_ratio": round(self.grounding_ratio, 4),
            "n_nodes": self.n_nodes,
            "n_edges": self.n_edges,
            "cascade_results": self.cascade_results,
        }


# ── GRAPH CONSTRUCTION ───────────────────────────────────────────────────────

def build_graph(
    name: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    mode: str = "standard",
) -> TCAGraph:
    """Build a TCAGraph from raw node/edge dicts."""
    tca_nodes = [
        TCANode(
            id=n["id"],
            label=n.get("label", n["id"]),
            metadata=n.get("metadata", {}),
        )
        for n in nodes
    ]
    tca_edges = [
        TCAEdge(
            source=e["source"],
            target=e["target"],
            edge_type=e.get("type", e.get("edge_type", "SEEKS")),
            weight=e.get("weight", 1.0),
            metadata=e.get("metadata", {}),
        )
        for e in edges
    ]
    return TCAGraph(name=name, nodes=tca_nodes, edges=tca_edges, mode=mode)


# ── BETWEENNESS CENTRALITY ───────────────────────────────────────────────────

def betweenness_centrality(graph: TCAGraph) -> Dict[str, float]:
    """
    Compute betweenness centrality for all nodes.
    Standard Brandes algorithm adapted for directed graphs.
    """
    node_ids = list(graph.node_ids())
    centrality: Dict[str, float] = {n: 0.0 for n in node_ids}
    adj = graph.adjacency()

    for s in node_ids:
        # BFS from s
        stack: List[str] = []
        pred: Dict[str, List[str]] = {n: [] for n in node_ids}
        sigma: Dict[str, int] = {n: 0 for n in node_ids}
        sigma[s] = 1
        dist: Dict[str, int] = {n: -1 for n in node_ids}
        dist[s] = 0
        queue: deque = deque([s])

        while queue:
            v = queue.popleft()
            stack.append(v)
            for w, _ in adj.get(v, []):
                if w not in dist or dist[w] < 0:
                    # First visit
                    if dist.get(w, -1) < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                if dist.get(w, -1) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        # Accumulation
        delta: Dict[str, float] = {n: 0.0 for n in node_ids}
        while stack:
            w = stack.pop()
            for v in pred[w]:
                if sigma[w] > 0:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                centrality[w] += delta[w]

    # Normalize
    n = len(node_ids)
    if n > 2:
        norm = 1.0 / ((n - 1) * (n - 2))
        for k in centrality:
            centrality[k] *= norm

    return centrality


# ── CYCLE DETECTION ──────────────────────────────────────────────────────────

def detect_cycles(
    graph: TCAGraph,
    edge_types: Optional[List[str]] = None,
) -> List[List[str]]:
    """
    DFS-based cycle detection, optionally filtered by edge type.
    Returns list of cycles (each cycle is a list of node IDs).
    """
    if edge_types is None:
        edge_types = ["EXPRESSES", "INHERITS"]

    # Build filtered adjacency
    adj: Dict[str, List[str]] = defaultdict(list)
    for e in graph.edges:
        if e.edge_type in edge_types:
            adj[e.source].append(e.target)

    visited: Set[str] = set()
    on_stack: Set[str] = set()
    cycles: List[List[str]] = []
    path: List[str] = []

    def dfs(node: str):
        visited.add(node)
        on_stack.add(node)
        path.append(node)

        for neighbor in adj.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in on_stack:
                # Found cycle
                idx = path.index(neighbor)
                cycle = path[idx:] + [neighbor]
                # Deduplicate
                if cycle not in cycles:
                    cycles.append(cycle)

        path.pop()
        on_stack.discard(node)

    for node_id in graph.node_ids():
        if node_id not in visited:
            dfs(node_id)

    return cycles


# ── CORE ANALYSIS ────────────────────────────────────────────────────────────

def analyze(graph: TCAGraph, run_cascade: bool = True) -> TCAResult:
    """
    Run full TCA structural analysis on a graph.

    Returns TCAResult with confidence, contradictions, feedback traps,
    dead ends, star topologies, unproven assumptions, load-bearing nodes,
    edge type distribution, grounding ratio, and cascade results.
    """
    is_physics = graph.mode == "physics"

    # ── Edge type distribution ──
    dist: Dict[str, int] = {t: 0 for t in sorted(EDGE_TYPES)}
    for e in graph.edges:
        dist[e.edge_type] = dist.get(e.edge_type, 0) + 1

    # ── Contradictions (REMOVES edges) ──
    contradictions: List[Dict[str, Any]] = []
    for e in graph.edges_by_type("REMOVES"):
        contradictions.append({
            "from_id": e.source,
            "from_label": graph.node_label(e.source),
            "to_id": e.target,
            "to_label": graph.node_label(e.target),
            "weight": e.weight,
            "description": (
                f"{graph.node_label(e.source)} contradicts/undermines "
                f"{graph.node_label(e.target)}"
            ),
        })

    # ── Feedback traps (cycles in EXPRESSES/INHERITS) ──
    if is_physics:
        # In physics mode, cycles are self-consistency (not penalized)
        cycle_types = ["EXPRESSES", "INHERITS", "SEEKS"]
    else:
        cycle_types = ["EXPRESSES", "INHERITS", "SEEKS"]
    feedback_traps = detect_cycles(graph, cycle_types)

    # ── Dead ends ──
    adj = graph.adjacency()
    rev = graph.reverse_adjacency()
    dead_ends: List[str] = []
    for n in graph.nodes:
        out_edges = adj.get(n.id, [])
        in_edges = rev.get(n.id, [])
        # Isolated nodes
        if not out_edges and not in_edges:
            dead_ends.append(n.id)
        # Leaf nodes with only SEEKS outgoing
        elif out_edges and all(t == "SEEKS" for _, t in out_edges) and not in_edges:
            dead_ends.append(n.id)

    # ── Star topologies (betweenness > threshold) ──
    bc = betweenness_centrality(graph)
    star_topologies: List[Dict[str, Any]] = []
    for node_id, score in bc.items():
        if score > STAR_BETWEENNESS_THRESHOLD:
            star_topologies.append({
                "node_id": node_id,
                "label": graph.node_label(node_id),
                "betweenness": round(score, 4),
                "description": (
                    f"{graph.node_label(node_id)} is a single point of failure "
                    f"(betweenness {score:.4f} > {STAR_BETWEENNESS_THRESHOLD})"
                ),
            })

    # ── Unproven assumptions (SEEKS edges) ──
    unproven: List[Dict[str, Any]] = []
    for e in graph.edges_by_type("SEEKS"):
        unproven.append({
            "from_id": e.source,
            "from_label": graph.node_label(e.source),
            "to_id": e.target,
            "to_label": graph.node_label(e.target),
            "description": (
                f"{graph.node_label(e.source)} \u2192 {graph.node_label(e.target)} "
                f"is assumed, not proven"
            ),
        })

    # ── Load-bearing nodes (top N by betweenness) ──
    sorted_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)
    load_bearing: List[Dict[str, Any]] = [
        {
            "node_id": nid,
            "label": graph.node_label(nid),
            "betweenness": round(score, 4),
        }
        for nid, score in sorted_bc[:CASCADE_TOP_N]
        if score > 0
    ]

    # ── Grounding ratio ──
    n_verifies = dist.get("VERIFIES", 0)
    n_seeks = dist.get("SEEKS", 0)
    grounding_ratio = (
        n_verifies / (n_verifies + n_seeks) if (n_verifies + n_seeks) > 0 else 0.0
    )

    # ── Confidence score ──
    confidence = 1.0

    # Penalties
    if not is_physics:
        confidence -= len(contradictions) * PENALTY_REMOVES
        confidence -= len(feedback_traps) * PENALTY_FEEDBACK_TRAP
    else:
        # Physics mode: contradictions are boundaries (less penalty)
        confidence -= len(contradictions) * (PENALTY_REMOVES * 0.5)
        # Cycles rewarded in physics mode
        confidence += len(feedback_traps) * 0.02

    confidence -= len(unproven) * PENALTY_SEEKS
    confidence -= len(dead_ends) * PENALTY_DEAD_END
    confidence -= len(star_topologies) * PENALTY_STAR_TOPOLOGY

    # Bonus for verification
    bonus = min(n_verifies * BONUS_VERIFIES, BONUS_VERIFIES_CAP)
    confidence += bonus

    # Floor
    confidence = max(0.0, min(1.0, confidence))

    # ── Cascade analysis ──
    cascade_results: Optional[Dict[str, float]] = None
    if run_cascade and load_bearing:
        cascade_results = cascade_analysis(graph, [lb["node_id"] for lb in load_bearing])

    result = TCAResult(
        graph_name=graph.name,
        confidence=confidence,
        contradictions=contradictions,
        feedback_traps=feedback_traps,
        dead_ends=dead_ends,
        star_topologies=star_topologies,
        unproven_assumptions=unproven,
        load_bearing_nodes=load_bearing,
        edge_type_distribution=dist,
        grounding_ratio=grounding_ratio,
        n_nodes=len(graph.nodes),
        n_edges=len(graph.edges),
        cascade_results=cascade_results,
    )

    logger.info(
        "TCA analysis: graph=%s confidence=%.4f contradictions=%d traps=%d "
        "dead_ends=%d unproven=%d grounding=%.4f",
        graph.name, confidence, len(contradictions), len(feedback_traps),
        len(dead_ends), len(unproven), grounding_ratio,
    )

    return result


# ── CASCADE ANALYSIS ─────────────────────────────────────────────────────────

def cascade_analysis(
    graph: TCAGraph,
    node_ids: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Remove each node, recompute confidence.
    Returns {node_id: confidence_delta} — negative means system degrades.
    """
    baseline = _quick_confidence(graph)
    results: Dict[str, float] = {}

    if node_ids is None:
        bc = betweenness_centrality(graph)
        sorted_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)
        node_ids = [nid for nid, _ in sorted_bc[:CASCADE_TOP_N]]

    for nid in node_ids:
        # Create graph without this node
        reduced_nodes = [n for n in graph.nodes if n.id != nid]
        reduced_edges = [
            e for e in graph.edges
            if e.source != nid and e.target != nid
        ]
        reduced = TCAGraph(
            name=f"{graph.name}_minus_{nid}",
            nodes=reduced_nodes,
            edges=reduced_edges,
            mode=graph.mode,
        )
        reduced_conf = _quick_confidence(reduced)
        results[nid] = round(reduced_conf - baseline, 4)

    return results


def _quick_confidence(graph: TCAGraph) -> float:
    """Fast confidence calculation without full analysis."""
    is_physics = graph.mode == "physics"
    confidence = 1.0

    n_removes = sum(1 for e in graph.edges if e.edge_type == "REMOVES")
    n_seeks = sum(1 for e in graph.edges if e.edge_type == "SEEKS")
    n_verifies = sum(1 for e in graph.edges if e.edge_type == "VERIFIES")

    traps = detect_cycles(graph, ["EXPRESSES", "INHERITS", "SEEKS"])

    # Dead ends
    adj = graph.adjacency()
    rev = graph.reverse_adjacency()
    n_dead = 0
    for n in graph.nodes:
        out_e = adj.get(n.id, [])
        in_e = rev.get(n.id, [])
        if not out_e and not in_e:
            n_dead += 1
        elif out_e and all(t == "SEEKS" for _, t in out_e) and not in_e:
            n_dead += 1

    # Stars
    bc = betweenness_centrality(graph)
    n_stars = sum(1 for s in bc.values() if s > STAR_BETWEENNESS_THRESHOLD)

    if not is_physics:
        confidence -= n_removes * PENALTY_REMOVES
        confidence -= len(traps) * PENALTY_FEEDBACK_TRAP
    else:
        confidence -= n_removes * (PENALTY_REMOVES * 0.5)
        confidence += len(traps) * 0.02

    confidence -= n_seeks * PENALTY_SEEKS
    confidence -= n_dead * PENALTY_DEAD_END
    confidence -= n_stars * PENALTY_STAR_TOPOLOGY
    confidence += min(n_verifies * BONUS_VERIFIES, BONUS_VERIFIES_CAP)

    return max(0.0, min(1.0, confidence))


# ── STRUCTURAL DELTA ─────────────────────────────────────────────────────────

def structural_delta(
    graph_a: TCAGraph,
    graph_b: TCAGraph,
) -> Dict[str, Any]:
    """Compare two graphs structurally."""
    result_a = analyze(graph_a, run_cascade=False)
    result_b = analyze(graph_b, run_cascade=False)

    def _entropy(dist: Dict[str, int]) -> float:
        total = sum(dist.values())
        if total == 0:
            return 0.0
        ent = 0.0
        for count in dist.values():
            if count > 0:
                p = count / total
                ent -= p * math.log2(p)
        return ent

    entropy_a = _entropy(result_a.edge_type_distribution)
    entropy_b = _entropy(result_b.edge_type_distribution)

    n_a = result_a.n_edges
    n_b = result_b.n_edges
    contra_density_a = len(result_a.contradictions) / n_a if n_a > 0 else 0
    contra_density_b = len(result_b.contradictions) / n_b if n_b > 0 else 0

    return {
        "graph_a": graph_a.name,
        "graph_b": graph_b.name,
        "confidence_a": round(result_a.confidence, 4),
        "confidence_b": round(result_b.confidence, 4),
        "confidence_delta": round(result_b.confidence - result_a.confidence, 4),
        "edge_type_entropy_a": round(entropy_a, 4),
        "edge_type_entropy_b": round(entropy_b, 4),
        "entropy_delta": round(entropy_b - entropy_a, 4),
        "contradiction_density_a": round(contra_density_a, 4),
        "contradiction_density_b": round(contra_density_b, 4),
        "grounding_ratio_a": round(result_a.grounding_ratio, 4),
        "grounding_ratio_b": round(result_b.grounding_ratio, 4),
        "grounding_delta": round(result_b.grounding_ratio - result_a.grounding_ratio, 4),
        "n_nodes_a": result_a.n_nodes,
        "n_nodes_b": result_b.n_nodes,
        "n_edges_a": result_a.n_edges,
        "n_edges_b": result_b.n_edges,
    }


# ── INVERSE TCA (SOLVE) ─────────────────────────────────────────────────────

def solve(
    graph: TCAGraph,
    min_confidence: float = 0.6,
    max_contradictions: int = 0,
    max_seeks: int = 0,
) -> List[Dict[str, Any]]:
    """
    Inverse TCA — find minimum structural changes to improve confidence.

    Greedy mode: tries every possible single-edge modification and returns
    the top 5 that maximize confidence improvement.

    Returns list of prescriptions, each with:
      - action: "remove_edge" | "retype_edge" | "add_verifies"
      - details: what specifically to change
      - projected_confidence: confidence after this change
      - delta: improvement over current
    """
    baseline = analyze(graph, run_cascade=False)
    prescriptions: List[Dict[str, Any]] = []

    # Strategy 1: Remove REMOVES edges (resolve contradictions)
    for i, e in enumerate(graph.edges):
        if e.edge_type == "REMOVES":
            test_graph = deepcopy(graph)
            test_graph.edges = [edge for j, edge in enumerate(test_graph.edges) if j != i]
            result = analyze(test_graph, run_cascade=False)
            prescriptions.append({
                "action": "resolve_contradiction",
                "edge": f"{graph.node_label(e.source)} REMOVES {graph.node_label(e.target)}",
                "description": (
                    f"Resolve the contradiction between {graph.node_label(e.source)} "
                    f"and {graph.node_label(e.target)}. Either decouple them or "
                    f"align their purposes."
                ),
                "projected_confidence": round(result.confidence, 4),
                "delta": round(result.confidence - baseline.confidence, 4),
            })

    # Strategy 2: Convert SEEKS to VERIFIES (prove assumptions)
    for i, e in enumerate(graph.edges):
        if e.edge_type == "SEEKS":
            test_graph = deepcopy(graph)
            test_graph.edges[i] = TCAEdge(
                source=e.source,
                target=e.target,
                edge_type="VERIFIES",
                weight=e.weight,
                metadata=e.metadata,
            )
            result = analyze(test_graph, run_cascade=False)
            prescriptions.append({
                "action": "prove_assumption",
                "edge": f"{graph.node_label(e.source)} SEEKS {graph.node_label(e.target)}",
                "description": (
                    f"Find evidence that {graph.node_label(e.source)} actually "
                    f"verifies {graph.node_label(e.target)}. Convert from "
                    f"assumption to proven."
                ),
                "projected_confidence": round(result.confidence, 4),
                "delta": round(result.confidence - baseline.confidence, 4),
            })

    # Strategy 3: Add VERIFIES edges to ungrounded nodes
    nodes_with_verifies = set()
    for e in graph.edges:
        if e.edge_type == "VERIFIES":
            nodes_with_verifies.add(e.target)

    for n in graph.nodes:
        if n.id not in nodes_with_verifies:
            # Find a plausible verifier (node with high betweenness that isn't already connected)
            bc = betweenness_centrality(graph)
            for verifier_id, score in sorted(bc.items(), key=lambda x: x[1], reverse=True):
                if verifier_id != n.id:
                    test_graph = deepcopy(graph)
                    test_graph.edges.append(TCAEdge(
                        source=verifier_id,
                        target=n.id,
                        edge_type="VERIFIES",
                        weight=1.0,
                    ))
                    result = analyze(test_graph, run_cascade=False)
                    if result.confidence > baseline.confidence:
                        prescriptions.append({
                            "action": "add_verification",
                            "description": (
                                f"Add verification: {graph.node_label(verifier_id)} "
                                f"VERIFIES {graph.node_label(n.id)}. "
                                f"Find evidence that grounds {graph.node_label(n.id)}."
                            ),
                            "projected_confidence": round(result.confidence, 4),
                            "delta": round(result.confidence - baseline.confidence, 4),
                        })
                    break  # Only try top verifier per node

    # Sort by delta descending, return top 5
    prescriptions.sort(key=lambda p: p["delta"], reverse=True)

    # Filter by constraints
    filtered: List[Dict[str, Any]] = []
    for p in prescriptions[:10]:
        if p["projected_confidence"] >= min_confidence or p["delta"] > 0:
            filtered.append(p)
        if len(filtered) >= 5:
            break

    return filtered
