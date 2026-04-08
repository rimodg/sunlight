"""
SUNLIGHT TCA Graph Analyzer
============================

Converts TCA graph output (from TCAGraphRuleEngine.build_graph()) into
a StructuralResult instance suitable for the SUNLIGHT evidence pipeline.

This analyzer:
- Classifies edges by type (REMOVES → contradictions, SEEKS → unproven, VERIFIES → verified)
- Looks up legal citations for each rule from the tca_rules.py Rule registry
- Computes structural confidence based on contradiction and unproven counts
- Maps confidence to a StructuralVerdict (SOUND | CONCERN | COMPROMISED | CRITICAL)

Pure function. No I/O. No mutation. Takes a ContractDossier with dossier.graph
already populated, returns a StructuralResult.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from typing import Dict, List

from sunlight_core import ContractDossier, StructuralResult, StructuralVerdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# SECTION 1: RULE EVIDENCE LOOKUP
# ═══════════════════════════════════════════════════════════

def _get_rule_evidence(rule_id: str) -> str:
    """
    Look up a rule's legal evidence citation from the tca_rules.py Rule registry.

    Args:
        rule_id: Rule identifier (e.g., "PROC-001", "FIN-001")

    Returns:
        Legal citation string from the Rule.evidence field, or a fallback
        error message if the rule cannot be found in the registry.
    """
    # Import here to avoid circular dependency at module load time
    try:
        from tca_rules import RULES
    except ImportError:
        logger.error("Failed to import RULES from tca_rules.py")
        return f"Citation lookup failed for rule {rule_id} (import error)"

    # Look up the rule by rule_id
    for rule in RULES:
        if rule.rule_id == rule_id:
            return rule.evidence

    # Rule not found in registry
    logger.warning(f"Rule {rule_id} not found in tca_rules.py RULES registry")
    return f"Citation lookup failed for rule {rule_id}"


# ═══════════════════════════════════════════════════════════
# SECTION 2: CONFIDENCE FORMULA
# ═══════════════════════════════════════════════════════════

def _compute_confidence(contradictions_count: int, unproven_count: int) -> float:
    """
    Compute structural confidence score.

    Formula (v1.0, uncalibrated):
        confidence = max(0.0, 1.0 - (0.20 × contradictions) - (0.05 × unproven))

    This gives:
        0 contradictions, 0 unproven → 1.0 (SOUND)
        1 contradiction → 0.80
        2 contradictions → 0.60
        3 contradictions → 0.40
        4 contradictions → 0.20
        5+ contradictions → 0.0

    Sub-task 2.4 will calibrate the threshold cutoffs in assign_tier() against
    this formula. The formula itself remains as-is.

    Args:
        contradictions_count: Number of REMOVES edges found
        unproven_count: Number of SEEKS edges found

    Returns:
        Confidence score in [0.0, 1.0]
    """
    return max(0.0, 1.0 - (0.20 * contradictions_count) - (0.05 * unproven_count))


def _map_verdict(confidence: float) -> StructuralVerdict:
    """
    Map confidence score to StructuralVerdict.

    Mapping:
        >= 0.80 → SOUND
        0.60 to 0.79 → CONCERN
        0.40 to 0.59 → COMPROMISED
        < 0.40 → CRITICAL

    Args:
        confidence: Score in [0.0, 1.0]

    Returns:
        StructuralVerdict enum value
    """
    if confidence >= 0.80:
        return StructuralVerdict.SOUND
    elif confidence >= 0.60:
        return StructuralVerdict.CONCERN
    elif confidence >= 0.40:
        return StructuralVerdict.COMPROMISED
    else:
        return StructuralVerdict.CRITICAL


# ═══════════════════════════════════════════════════════════
# SECTION 3: MAIN ANALYZER
# ═══════════════════════════════════════════════════════════

def analyze_tca_graph(dossier: ContractDossier) -> StructuralResult:
    """
    Analyze a TCA graph and return a StructuralResult.

    This function assumes dossier.graph has already been populated by
    TCAGraphRuleEngine.build_graph(). It does NOT call the engine itself.

    Process:
        1. Extract edges from dossier.graph
        2. Classify edges by type:
           - REMOVES → contradictions
           - SEEKS → unproven
           - VERIFIES → verified
           - Others → ignored for scoring
        3. Look up legal citations for each rule from tca_rules.py
        4. Compute confidence based on contradiction/unproven counts
        5. Map confidence to verdict
        6. Populate edge distribution
        7. Generate deterministic graph_id

    Args:
        dossier: ContractDossier with dossier.graph populated

    Returns:
        StructuralResult with confidence, verdict, contradictions list
        (with rule IDs and legal citations), unproven, verified, etc.
    """
    # Handle empty/null graph
    if not dossier.graph or not dossier.graph.get("edges"):
        return StructuralResult(
            confidence=1.0,
            verdict=StructuralVerdict.SOUND,
            contradictions=[],
            feedback_traps=[],
            unproven=[],
            verified=[],
            edge_distribution={},
            graph_id="",
        )

    edges = dossier.graph.get("edges", [])

    # Classify edges by type
    contradictions = []
    unproven = []
    verified = []

    for edge in edges:
        edge_type = edge.get("type", "UNKNOWN")

        # Build the finding dict
        finding = {
            "from": edge.get("source", ""),
            "to": edge.get("target", ""),
            "description": edge.get("description", ""),
            "rule": edge.get("rule", "UNKNOWN"),
            "evidence": _get_rule_evidence(edge.get("rule", "UNKNOWN")),
        }

        # Classify by edge type
        if edge_type == "REMOVES":
            contradictions.append(finding)
        elif edge_type == "SEEKS":
            unproven.append(finding)
        elif edge_type == "VERIFIES":
            verified.append(finding)
        # All other types are ignored for scoring (not an error)

    # Compute confidence
    confidence = _compute_confidence(len(contradictions), len(unproven))

    # Map to verdict
    verdict = _map_verdict(confidence)

    # Edge distribution (count all edge types, not just scored ones)
    edge_types = [e.get("type", "UNKNOWN") for e in edges]
    edge_distribution = dict(Counter(edge_types))

    # Generate deterministic graph_id
    # SHA-256(contract_id + rule_set_version) truncated to 12 hex chars
    metadata = dossier.graph.get("metadata", {})
    rule_set_version = metadata.get("rule_set_version", "")
    graph_seed = f"{dossier.contract_id}:{rule_set_version}"
    graph_id = hashlib.sha256(graph_seed.encode()).hexdigest()[:12]

    return StructuralResult(
        confidence=round(confidence, 4),
        verdict=verdict,
        contradictions=contradictions,
        feedback_traps=[],  # Future: detect cycles
        unproven=unproven,
        verified=verified,
        edge_distribution=edge_distribution,
        graph_id=graph_id,
    )


# ═══════════════════════════════════════════════════════════
# SECTION 4: VERIFICATION (for development/testing only)
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Verification: Run the analyzer against a Paraguay sample contract.

    This ensures the analyzer works end-to-end with real TCA graph output
    and produces StructuralResult with rule IDs and legal citations.
    """
    import sys
    sys.path.insert(0, ".")

    from tca_rules import TCAGraphRuleEngine
    from sunlight_core import ContractDossier

    # Build a sample Paraguay contract (similar to the one from ground truth)
    raw_ocds = {
        "ocid": "ocds-PY-2025-001-SAMPLE",
        "parties": [
            {"name": "Ministerio de Obras Públicas", "roles": ["buyer"]},
            {"name": "Constructora ABC SA", "id": "PY-ABC-001", "roles": ["supplier"]},
        ],
        "tender": {
            "procurementMethod": "direct",
            "numberOfTenderers": 1,
            "value": {"amount": 500000, "currency": "USD"},
        },
        "awards": [{"date": "2025-12-20", "value": {"amount": 650000, "currency": "USD"}}],
    }

    dossier = ContractDossier(
        contract_id="PY-2025-001-VERIFICATION",
        ocid="ocds-PY-2025-001-SAMPLE",
        raw_ocds=raw_ocds,
        buyer_name="Ministerio de Obras Públicas",
        supplier_name="Constructora ABC SA",
        procurement_method="direct",
        tender_value=500_000,
        award_value=650_000,
        currency="USD",
        number_of_tenderers=1,
        award_date="2025-12-20",
        country_code="PY",
        sector="works",
    )

    # Step 1: Build TCA graph using TCAGraphRuleEngine
    engine = TCAGraphRuleEngine()
    dossier = engine.build_graph(dossier)

    print("=" * 70)
    print("TCA ANALYZER VERIFICATION — Paraguay Sample")
    print("=" * 70)
    print(f"\nGraph built:")
    print(f"  Nodes: {len(dossier.graph['nodes'])}")
    print(f"  Edges: {len(dossier.graph['edges'])}")
    print(f"  Rules fired: {dossier.graph['metadata']['rules_fired']}")
    print(f"  Layers active: {dossier.graph['metadata']['layers_active']}")

    # Step 2: Analyze the graph
    result = analyze_tca_graph(dossier)

    print(f"\nStructural Analysis Result:")
    print(f"  Confidence: {result.confidence}")
    print(f"  Verdict: {result.verdict.value}")
    print(f"  Contradictions: {len(result.contradictions)}")
    print(f"  Unproven: {len(result.unproven)}")
    print(f"  Verified: {len(result.verified)}")
    print(f"  Edge distribution: {result.edge_distribution}")
    print(f"  Graph ID: {result.graph_id}")

    print(f"\n--- CONTRADICTIONS (REMOVES edges) ---")
    for i, c in enumerate(result.contradictions, 1):
        print(f"\n  [{i}] Rule: {c['rule']}")
        print(f"      From: {c['from']} → To: {c['to']}")
        print(f"      Description: {c['description']}")
        print(f"      Evidence: {c['evidence'][:100]}...")

    print(f"\n--- UNPROVEN (SEEKS edges) ---")
    for i, u in enumerate(result.unproven, 1):
        print(f"\n  [{i}] Rule: {u['rule']}")
        print(f"      From: {u['from']} → To: {u['to']}")
        print(f"      Description: {u['description']}")
        print(f"      Evidence: {u['evidence'][:100]}...")

    print(f"\n--- VERIFIED (VERIFIES edges) ---")
    if result.verified:
        for i, v in enumerate(result.verified, 1):
            print(f"\n  [{i}] Rule: {v['rule']}")
            print(f"      From: {v['from']} → To: {v['to']}")
            print(f"      Description: {v['description']}")
    else:
        print("  (None)")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

    # Validate that we have rule IDs and citations
    if result.contradictions:
        has_rule_ids = all(c.get('rule') and c['rule'] != 'UNKNOWN' for c in result.contradictions)
        has_citations = all(c.get('evidence') and not c['evidence'].startswith('Citation lookup failed')
                           for c in result.contradictions)

        print(f"\n✓ Rule IDs present: {has_rule_ids}")
        print(f"✓ Legal citations present: {has_citations}")

        if not has_rule_ids or not has_citations:
            print("\n⚠ WARNING: Integration check FAILED")
            sys.exit(1)
        else:
            print("\n✓ Integration check PASSED")


