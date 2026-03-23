"""
Tests for the TCA structural analysis engine and procurement graph builder.
"""

import pytest
from code.tca import (
    TCAEdge, TCAGraph, TCANode, TCAResult,
    analyze, betweenness_centrality, build_graph, cascade_analysis,
    detect_cycles, solve, structural_delta, EDGE_TYPES,
)
from code.tca_procurement import (
    build_procurement_graph, classify_procurement, run_tca,
)


# ── TCA ENGINE TESTS ─────────────────────────────────────────────────────────

class TestEdgeTypes:
    def test_all_seven_types_valid(self):
        assert len(EDGE_TYPES) == 7
        for t in ["MIRRORS", "INHERITS", "BOUNDS", "EXPRESSES", "VERIFIES", "REMOVES", "SEEKS"]:
            assert t in EDGE_TYPES

    def test_invalid_edge_type_raises(self):
        with pytest.raises(ValueError):
            TCAEdge(source="a", target="b", edge_type="INVALID")

    def test_valid_edge_types_accepted(self):
        for t in EDGE_TYPES:
            edge = TCAEdge(source="a", target="b", edge_type=t)
            assert edge.edge_type == t


class TestBuildGraph:
    def test_build_from_dicts(self):
        g = build_graph(
            "test",
            [{"id": "a", "label": "Node A"}, {"id": "b", "label": "Node B"}],
            [{"source": "a", "target": "b", "type": "EXPRESSES"}],
        )
        assert g.name == "test"
        assert len(g.nodes) == 2
        assert len(g.edges) == 1
        assert g.edges[0].edge_type == "EXPRESSES"


class TestAnalyze:
    def test_clean_graph_high_confidence(self):
        """Graph with only VERIFIES and EXPRESSES should score high."""
        g = build_graph("clean", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ], [
            {"source": "a", "target": "b", "type": "EXPRESSES"},
            {"source": "b", "target": "c", "type": "VERIFIES"},
            {"source": "a", "target": "c", "type": "VERIFIES"},
        ])
        result = analyze(g, run_cascade=False)
        assert result.confidence > 0.8
        assert len(result.contradictions) == 0

    def test_contradictions_lower_confidence(self):
        """Graph with REMOVES edges should score lower."""
        g = build_graph("broken", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "REMOVES"},
        ])
        result = analyze(g, run_cascade=False)
        assert result.confidence < 0.95
        assert len(result.contradictions) == 1

    def test_many_seeks_lowers_confidence(self):
        """Graph with many SEEKS edges (unproven) should score low."""
        nodes = [{"id": f"n{i}", "label": f"N{i}"} for i in range(6)]
        edges = [{"source": f"n{i}", "target": f"n{i+1}", "type": "SEEKS"} for i in range(5)]
        g = build_graph("hopeful", nodes, edges)
        result = analyze(g, run_cascade=False)
        assert result.confidence < 0.85
        assert len(result.unproven_assumptions) == 5

    def test_grounding_ratio(self):
        """Grounding ratio = VERIFIES / (VERIFIES + SEEKS)."""
        g = build_graph("mixed", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"}, {"id": "d", "label": "D"},
        ], [
            {"source": "a", "target": "b", "type": "VERIFIES"},
            {"source": "c", "target": "d", "type": "SEEKS"},
        ])
        result = analyze(g, run_cascade=False)
        assert result.grounding_ratio == pytest.approx(0.5, abs=0.01)

    def test_edge_type_distribution(self):
        g = build_graph("dist", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "EXPRESSES"},
            {"source": "b", "target": "a", "type": "REMOVES"},
        ])
        result = analyze(g, run_cascade=False)
        assert result.edge_type_distribution["EXPRESSES"] == 1
        assert result.edge_type_distribution["REMOVES"] == 1
        assert result.edge_type_distribution["SEEKS"] == 0

    def test_result_to_dict(self):
        g = build_graph("test", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "EXPRESSES"},
        ])
        result = analyze(g, run_cascade=False)
        d = result.to_dict()
        assert "confidence" in d
        assert "contradictions" in d
        assert "grounding_ratio" in d
        assert "n_nodes" in d


class TestCycleDetection:
    def test_finds_simple_cycle(self):
        g = build_graph("cycle", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ], [
            {"source": "a", "target": "b", "type": "EXPRESSES"},
            {"source": "b", "target": "c", "type": "EXPRESSES"},
            {"source": "c", "target": "a", "type": "EXPRESSES"},
        ])
        cycles = detect_cycles(g, ["EXPRESSES"])
        assert len(cycles) >= 1

    def test_no_cycle_in_dag(self):
        g = build_graph("dag", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ], [
            {"source": "a", "target": "b", "type": "EXPRESSES"},
            {"source": "b", "target": "c", "type": "EXPRESSES"},
        ])
        cycles = detect_cycles(g, ["EXPRESSES"])
        assert len(cycles) == 0


class TestBetweennessCentrality:
    def test_hub_has_highest_centrality(self):
        """Star topology: center node should have highest betweenness."""
        g = build_graph("star", [
            {"id": "hub", "label": "Hub"},
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"}, {"id": "d", "label": "D"},
        ], [
            {"source": "a", "target": "hub", "type": "EXPRESSES"},
            {"source": "b", "target": "hub", "type": "EXPRESSES"},
            {"source": "hub", "target": "c", "type": "EXPRESSES"},
            {"source": "hub", "target": "d", "type": "EXPRESSES"},
        ])
        bc = betweenness_centrality(g)
        assert bc["hub"] >= bc.get("a", 0)
        assert bc["hub"] >= bc.get("b", 0)


class TestCascadeAnalysis:
    def test_removing_hub_degrades_more(self):
        g = build_graph("cascade", [
            {"id": "hub", "label": "Hub"},
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ], [
            {"source": "a", "target": "hub", "type": "EXPRESSES"},
            {"source": "hub", "target": "b", "type": "EXPRESSES"},
            {"source": "hub", "target": "c", "type": "VERIFIES"},
        ])
        results = cascade_analysis(g, ["hub", "a"])
        # Removing hub should cause more degradation (more negative or less positive)
        assert results["hub"] <= results["a"]


class TestSolve:
    def test_solve_returns_prescriptions(self):
        g = build_graph("broken", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
            {"id": "c", "label": "C"},
        ], [
            {"source": "a", "target": "b", "type": "REMOVES"},
            {"source": "b", "target": "c", "type": "SEEKS"},
        ])
        prescriptions = solve(g)
        assert len(prescriptions) > 0
        assert all("action" in p for p in prescriptions)
        assert all("projected_confidence" in p for p in prescriptions)

    def test_solve_improves_confidence(self):
        g = build_graph("fixable", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "REMOVES"},
        ])
        baseline = analyze(g, run_cascade=False).confidence
        prescriptions = solve(g)
        if prescriptions:
            assert prescriptions[0]["projected_confidence"] > baseline


class TestStructuralDelta:
    def test_delta_between_different_graphs(self):
        g1 = build_graph("healthy", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "VERIFIES"},
        ])
        g2 = build_graph("sick", [
            {"id": "a", "label": "A"}, {"id": "b", "label": "B"},
        ], [
            {"source": "a", "target": "b", "type": "REMOVES"},
        ])
        delta = structural_delta(g1, g2)
        assert delta["confidence_delta"] < 0  # Sick is worse
        assert delta["graph_a"] == "healthy"
        assert delta["graph_b"] == "sick"


# ── PROCUREMENT GRAPH BUILDER TESTS ──────────────────────────────────────────

class TestProcurementGraph:
    def test_builds_valid_graph_from_contract(self):
        contract = {
            "id": "TEST-001",
            "buyer": {"name": "Test Agency", "id": "agency_1"},
            "procurement_method": "open",
            "vendors": [
                {"id": "v1", "name": "Vendor A"},
                {"id": "v2", "name": "Vendor B"},
            ],
            "num_offers": 2,
            "award_value": 100000,
        }
        graph = build_procurement_graph(contract)
        assert graph.name == "Procurement: TEST-001"
        assert len(graph.nodes) >= 5  # buyer, award, process, budget, 2 vendors, oversight
        assert len(graph.edges) >= 3

    def test_sole_source_creates_removes_edge(self):
        contract = {
            "id": "TEST-002",
            "buyer": {"name": "Buyer", "id": "b1"},
            "procurement_method": "direct",
            "vendors": [{"id": "v1", "name": "Sole Vendor"}],
            "num_offers": 1,
        }
        graph = build_procurement_graph(contract)
        removes = [e for e in graph.edges if e.edge_type == "REMOVES"]
        assert len(removes) >= 1

    def test_fabricated_competition_creates_inherits(self):
        contract = {
            "id": "TEST-003",
            "buyer": {"name": "Buyer", "id": "b1"},
            "procurement_method": "open",
            "vendors": [
                {"id": "v1", "name": "Shell A"},
                {"id": "v2", "name": "Shell B"},
            ],
            "num_offers": 2,
        }
        portfolio = {"evg": {"evg_class": "FABRICATED_COMPETITION"}}
        graph = build_procurement_graph(contract, portfolio)
        inherits = [e for e in graph.edges if e.edge_type == "INHERITS"]
        assert len(inherits) >= 1


class TestClassifyProcurement:
    def test_honest(self):
        result = TCAResult(
            graph_name="test", confidence=0.9,
            contradictions=[], feedback_traps=[], dead_ends=[],
            star_topologies=[], unproven_assumptions=[],
            load_bearing_nodes=[], edge_type_distribution={},
            grounding_ratio=0.8, n_nodes=5, n_edges=6,
        )
        assert classify_procurement(result) == "HONEST"

    def test_suspicious(self):
        result = TCAResult(
            graph_name="test", confidence=0.5,
            contradictions=[{"from_id": "a", "to_id": "b"}],
            feedback_traps=[], dead_ends=[],
            star_topologies=[], unproven_assumptions=[],
            load_bearing_nodes=[], edge_type_distribution={},
            grounding_ratio=0.5, n_nodes=5, n_edges=6,
        )
        assert classify_procurement(result) == "SUSPICIOUS"

    def test_structurally_fraudulent(self):
        result = TCAResult(
            graph_name="test", confidence=0.2,
            contradictions=[{"a": 1}, {"b": 2}, {"c": 3}],
            feedback_traps=[], dead_ends=[],
            star_topologies=[], unproven_assumptions=[],
            load_bearing_nodes=[], edge_type_distribution={},
            grounding_ratio=0.1, n_nodes=5, n_edges=6,
        )
        assert classify_procurement(result) == "STRUCTURALLY_FRAUDULENT"


class TestRunTCA:
    def test_run_tca_returns_complete_result(self):
        contract = {
            "id": "TEST-004",
            "buyer": {"name": "Agency", "id": "a1"},
            "procurement_method": "open",
            "vendors": [
                {"id": "v1", "name": "V1"},
                {"id": "v2", "name": "V2"},
            ],
            "num_offers": 2,
            "award_value": 50000,
        }
        result = run_tca(contract)
        assert "topology_class" in result
        assert "confidence" in result
        assert "contradictions" in result
        assert "grounding_ratio" in result
        assert "graph" in result
        assert result["topology_class"] in ("HONEST", "SUSPICIOUS", "STRUCTURALLY_FRAUDULENT")
