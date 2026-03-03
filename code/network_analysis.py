"""
Network Analysis — graph-based collusion detection.

Builds a bipartite graph of vendors <-> agencies and detects:
  - Shared ownership signals (same address, phone, registration date clusters)
  - Bid rotation patterns (vendor A wins round 1, vendor B round 2 repeatedly)
  - Connected component risk scoring
"""

import sqlite3
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


@dataclass
class NetworkEdge:
    """An edge between two vendors indicating a collusion signal."""

    vendor_a: str
    vendor_b: str
    edge_type: str  # "shared_agency", "bid_rotation", "temporal_cluster"
    confidence: float  # 0.0-1.0
    evidence: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetworkCluster:
    """A connected component of potentially colluding vendors."""

    cluster_id: int
    vendors: list = field(default_factory=list)
    agencies: list = field(default_factory=list)
    edge_count: int = 0
    risk_score: float = 0.0
    dominant_pattern: str = ""
    edges: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["edges"] = [e if isinstance(e, dict) else asdict(e) for e in self.edges]
        return d


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_vendor_agency_graph(db_path: str) -> dict:
    """Load vendor-agency award relationships from the database.

    Returns:
        {
            "vendor_agencies": {vendor: {agency: [award_amounts]}},
            "agency_vendors": {agency: {vendor: [award_amounts]}},
            "vendor_dates":   {vendor: {agency: [start_dates]}},
        }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(
        """
        SELECT vendor_name, agency_name, award_amount, start_date
        FROM contracts
        ORDER BY agency_name, start_date
        """
    )

    vendor_agencies = defaultdict(lambda: defaultdict(list))
    agency_vendors = defaultdict(lambda: defaultdict(list))
    vendor_dates = defaultdict(lambda: defaultdict(list))

    for row in c.fetchall():
        v, a, amt = row["vendor_name"], row["agency_name"], row["award_amount"]
        vendor_agencies[v][a].append(amt)
        agency_vendors[a][v].append(amt)
        if row["start_date"]:
            vendor_dates[v][a].append(row["start_date"])

    conn.close()
    return {
        "vendor_agencies": dict(vendor_agencies),
        "agency_vendors": dict(agency_vendors),
        "vendor_dates": dict(vendor_dates),
    }


# ---------------------------------------------------------------------------
# Collusion signal detectors
# ---------------------------------------------------------------------------

def detect_shared_agency_patterns(graph_data: dict, min_shared: int = 3) -> list:
    """Detect vendors that repeatedly win contracts at the same agencies.

    Two vendors sharing 3+ agencies is unusual and may indicate coordination.
    """
    edges = []
    vendor_agencies = graph_data["vendor_agencies"]
    vendors = list(vendor_agencies.keys())

    for i in range(len(vendors)):
        agencies_i = set(vendor_agencies[vendors[i]].keys())
        for j in range(i + 1, len(vendors)):
            agencies_j = set(vendor_agencies[vendors[j]].keys())
            shared = agencies_i & agencies_j
            if len(shared) >= min_shared:
                overlap = len(shared) / max(len(agencies_i | agencies_j), 1)
                edges.append(
                    NetworkEdge(
                        vendor_a=vendors[i],
                        vendor_b=vendors[j],
                        edge_type="shared_agency",
                        confidence=min(overlap, 1.0),
                        evidence={
                            "shared_agencies": sorted(shared),
                            "shared_count": len(shared),
                            "overlap_ratio": round(overlap, 3),
                        },
                    )
                )
    return edges


def detect_bid_rotation(graph_data: dict, min_rotations: int = 3) -> list:
    """Detect alternating award patterns between vendor pairs at the same agency.

    Pattern: V1 wins, then V2 wins, then V1 wins... at the same agency.
    """
    edges = []
    agency_vendors = graph_data["agency_vendors"]
    vendor_dates = graph_data["vendor_dates"]

    for agency, vendors_map in agency_vendors.items():
        vendor_list = list(vendors_map.keys())
        if len(vendor_list) < 2:
            continue

        # Build chronological award sequence for this agency
        timeline = []
        for v in vendor_list:
            dates = vendor_dates.get(v, {}).get(agency, [])
            for d in dates:
                timeline.append((d, v))
        timeline.sort(key=lambda x: x[0])

        if len(timeline) < min_rotations * 2:
            continue

        # Check pairs for alternating patterns
        for i in range(len(vendor_list)):
            for j in range(i + 1, len(vendor_list)):
                v1, v2 = vendor_list[i], vendor_list[j]
                # Filter timeline to just these two vendors
                pair_seq = [t[1] for t in timeline if t[1] in (v1, v2)]
                if len(pair_seq) < min_rotations * 2:
                    continue

                # Count alternations
                alternations = sum(
                    1 for k in range(1, len(pair_seq)) if pair_seq[k] != pair_seq[k - 1]
                )
                max_possible = len(pair_seq) - 1
                if max_possible == 0:
                    continue

                rotation_ratio = alternations / max_possible
                if alternations >= min_rotations and rotation_ratio > 0.6:
                    edges.append(
                        NetworkEdge(
                            vendor_a=v1,
                            vendor_b=v2,
                            edge_type="bid_rotation",
                            confidence=min(rotation_ratio, 1.0),
                            evidence={
                                "agency": agency,
                                "alternations": alternations,
                                "total_awards": len(pair_seq),
                                "rotation_ratio": round(rotation_ratio, 3),
                            },
                        )
                    )
    return edges


def detect_temporal_clusters(graph_data: dict, window_days: int = 7) -> list:
    """Detect vendors whose contracts cluster suspiciously in time.

    Multiple vendors winning at the same agency within a tight time window
    may indicate coordinated bidding.
    """
    edges = []
    agency_vendors = graph_data["agency_vendors"]
    vendor_dates = graph_data["vendor_dates"]

    for agency, vendors_map in agency_vendors.items():
        vendor_list = list(vendors_map.keys())
        if len(vendor_list) < 2:
            continue

        for i in range(len(vendor_list)):
            dates_i = vendor_dates.get(vendor_list[i], {}).get(agency, [])
            if not dates_i:
                continue
            for j in range(i + 1, len(vendor_list)):
                dates_j = vendor_dates.get(vendor_list[j], {}).get(agency, [])
                if not dates_j:
                    continue

                # Count date coincidences within window
                coincidences = 0
                for di in dates_i:
                    for dj in dates_j:
                        try:
                            dt_i = datetime.fromisoformat(di)
                            dt_j = datetime.fromisoformat(dj)
                            if abs((dt_i - dt_j).days) <= window_days:
                                coincidences += 1
                        except (ValueError, TypeError):
                            continue

                min_count = min(len(dates_i), len(dates_j))
                if min_count == 0:
                    continue
                cluster_ratio = coincidences / min_count
                if coincidences >= 2 and cluster_ratio > 0.5:
                    edges.append(
                        NetworkEdge(
                            vendor_a=vendor_list[i],
                            vendor_b=vendor_list[j],
                            edge_type="temporal_cluster",
                            confidence=min(cluster_ratio, 1.0),
                            evidence={
                                "agency": agency,
                                "coincidences": coincidences,
                                "window_days": window_days,
                                "cluster_ratio": round(cluster_ratio, 3),
                            },
                        )
                    )
    return edges


# ---------------------------------------------------------------------------
# Connected component analysis
# ---------------------------------------------------------------------------

def build_network(edges: list) -> list:
    """Build a network graph and extract connected components as clusters.

    If networkx is available, uses it for proper graph analysis.
    Otherwise, falls back to a simple union-find approach.
    """
    if not edges:
        return []

    if HAS_NETWORKX:
        return _build_network_nx(edges)
    return _build_network_simple(edges)


def _build_network_nx(edges: list) -> list:
    """Build network using networkx."""
    G = nx.Graph()
    for edge in edges:
        G.add_edge(
            edge.vendor_a,
            edge.vendor_b,
            edge_type=edge.edge_type,
            confidence=edge.confidence,
        )

    clusters = []
    for idx, component in enumerate(nx.connected_components(G)):
        vendors = sorted(component)
        subgraph = G.subgraph(component)
        component_edges = [
            e for e in edges if e.vendor_a in component and e.vendor_b in component
        ]

        # Collect agencies involved
        agencies = set()
        for e in component_edges:
            for k in ("shared_agencies", "agency"):
                val = e.evidence.get(k)
                if isinstance(val, list):
                    agencies.update(val)
                elif isinstance(val, str):
                    agencies.add(val)

        # Risk score: density * avg_confidence * size_factor
        density = nx.density(subgraph) if len(vendors) > 1 else 0.0
        avg_conf = (
            sum(e.confidence for e in component_edges) / len(component_edges)
            if component_edges
            else 0.0
        )
        size_factor = min(math.log2(max(len(vendors), 1)) + 1, 5)
        risk = min(density * avg_conf * size_factor * 100, 100.0)

        # Dominant pattern
        type_counts = defaultdict(int)
        for e in component_edges:
            type_counts[e.edge_type] += 1
        dominant = max(type_counts, key=type_counts.get) if type_counts else "unknown"

        clusters.append(
            NetworkCluster(
                cluster_id=idx,
                vendors=vendors,
                agencies=sorted(agencies),
                edge_count=len(component_edges),
                risk_score=round(risk, 1),
                dominant_pattern=dominant,
                edges=component_edges,
            )
        )

    clusters.sort(key=lambda c: c.risk_score, reverse=True)
    return clusters


def _build_network_simple(edges: list) -> list:
    """Fallback: union-find based clustering without networkx."""
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in edges:
        parent.setdefault(edge.vendor_a, edge.vendor_a)
        parent.setdefault(edge.vendor_b, edge.vendor_b)
        union(edge.vendor_a, edge.vendor_b)

    components = defaultdict(set)
    for v in parent:
        components[find(v)].add(v)

    clusters = []
    for idx, (_, vendors) in enumerate(components.items()):
        component_edges = [
            e for e in edges if e.vendor_a in vendors and e.vendor_b in vendors
        ]
        agencies = set()
        for e in component_edges:
            for k in ("shared_agencies", "agency"):
                val = e.evidence.get(k)
                if isinstance(val, list):
                    agencies.update(val)
                elif isinstance(val, str):
                    agencies.add(val)

        avg_conf = (
            sum(e.confidence for e in component_edges) / len(component_edges)
            if component_edges
            else 0.0
        )
        risk = min(avg_conf * len(component_edges) * 10, 100.0)

        type_counts = defaultdict(int)
        for e in component_edges:
            type_counts[e.edge_type] += 1
        dominant = max(type_counts, key=type_counts.get) if type_counts else "unknown"

        clusters.append(
            NetworkCluster(
                cluster_id=idx,
                vendors=sorted(vendors),
                agencies=sorted(agencies),
                edge_count=len(component_edges),
                risk_score=round(risk, 1),
                dominant_pattern=dominant,
                edges=component_edges,
            )
        )

    clusters.sort(key=lambda c: c.risk_score, reverse=True)
    return clusters


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_network_analysis(
    db_path: str,
    min_shared_agencies: int = 3,
    min_rotations: int = 3,
    temporal_window_days: int = 7,
) -> dict:
    """Run full network analysis and return clusters with risk scores.

    Returns:
        {
            "edges": [NetworkEdge.to_dict(), ...],
            "clusters": [NetworkCluster.to_dict(), ...],
            "summary": {
                "total_edges": int,
                "total_clusters": int,
                "high_risk_clusters": int,  # risk_score > 50
            }
        }
    """
    graph_data = _build_vendor_agency_graph(db_path)

    all_edges = []
    all_edges.extend(detect_shared_agency_patterns(graph_data, min_shared_agencies))
    all_edges.extend(detect_bid_rotation(graph_data, min_rotations))
    all_edges.extend(detect_temporal_clusters(graph_data, temporal_window_days))

    clusters = build_network(all_edges)

    high_risk = sum(1 for c in clusters if c.risk_score > 50)

    return {
        "edges": [e.to_dict() for e in all_edges],
        "clusters": [c.to_dict() for c in clusters],
        "summary": {
            "total_edges": len(all_edges),
            "total_clusters": len(clusters),
            "high_risk_clusters": high_risk,
        },
    }
