"""
SUNLIGHT Side 2 — Delivery Evidence Verification Gate (Delivery EVG)
=====================================================================

Multi-dimensional hard-evidence gate for delivery integrity verification.
Combines delivery rule evaluation results against threshold parameters
to produce a tiered delivery verdict.

Architecture:
    Mirrors evg.py exactly:
    - 4 delivery dimensions (vs Side 1's 3 procurement dimensions)
    - Same tiered verdict model: GREEN=0, YELLOW=1, RED=2+
    - Per-dimension traceability with observed value, threshold, detail
    - Deterministic: same inputs = same verdict. Forever.

Dimensions:
    MILESTONE_COMPLIANCE      — Proportion of milestones with rules fired
    RESOURCE_VERIFICATION     — Proportion of resource rules fired
    OUTCOME_VERIFICATION      — Proportion of outcome rules fired
    FINANCIAL_RECONCILIATION  — Proportion of financial rules fired

Each dimension fires when the number of rules fired in that layer
meets or exceeds the minimum threshold (default: 2 of 3 rules per layer).

Verdicts:
    GREEN  — No delivery dimension above threshold
    YELLOW — One dimension above threshold
    RED    — Two or more dimensions above threshold simultaneously

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from typing import Optional

from delivery_schema import (
    DeliveryDimension,
    DeliveryDimensionResult,
    DeliveryGateOutcome,
    DeliveryRulesResult,
    DeliveryVerdict,
)


# ═══════════════════════════════════════════════════════════
# THRESHOLD DEFAULTS
# ═══════════════════════════════════════════════════════════

# Minimum number of rules that must fire within a layer for
# that dimension to be considered "fired". With 3 rules per
# layer, 2 means convergent evidence is required — a single
# rule firing is not enough to trip a dimension.
DEFAULT_MIN_RULES_PER_DIMENSION = 2


# ═══════════════════════════════════════════════════════════
# DIMENSION → LAYER MAPPING
# ═══════════════════════════════════════════════════════════

DIMENSION_LAYER_MAP = {
    DeliveryDimension.MILESTONE_COMPLIANCE: "milestone",
    DeliveryDimension.RESOURCE_VERIFICATION: "resource",
    DeliveryDimension.OUTCOME_VERIFICATION: "outcome",
    DeliveryDimension.FINANCIAL_RECONCILIATION: "financial",
}


# ═══════════════════════════════════════════════════════════
# GATE FUNCTION
# ═══════════════════════════════════════════════════════════


def delivery_gate(
    rules_result: Optional[DeliveryRulesResult],
    min_rules_per_dimension: int = DEFAULT_MIN_RULES_PER_DIMENSION,
) -> DeliveryGateOutcome:
    """
    Evaluate the Delivery Evidence Verification Gate.

    Combines delivery rule evaluation results to produce a tiered
    delivery verdict. Each of the 4 dimensions fires when the number
    of rules fired in the corresponding layer meets or exceeds
    min_rules_per_dimension.

    Args:
        rules_result: Aggregate result from DeliveryRuleEngine.evaluate().
                      May be None if rule evaluation stage was not reached.
        min_rules_per_dimension: Minimum rules that must fire within a
                                 single layer for that dimension to fire.
                                 Default: 2 (convergent evidence required).

    Returns:
        DeliveryGateOutcome with verdict (GREEN/YELLOW/RED) and
        per-dimension traceability.
    """
    dimension_results: list[DeliveryDimensionResult] = []

    for dimension, layer in DIMENSION_LAYER_MAP.items():
        fired = False
        observed: Optional[float] = None
        threshold = float(min_rules_per_dimension)
        detail = "No delivery rule data available"

        if rules_result is not None:
            # Count rules fired in this layer
            layer_fired = sum(
                1 for rr in rules_result.rule_results
                if rr.layer == layer and rr.fired
            )
            observed = float(layer_fired)

            if layer_fired >= min_rules_per_dimension:
                fired = True
                detail = (
                    f"{layer_fired} rules fired in {layer} layer >= "
                    f"threshold {min_rules_per_dimension}"
                )
            else:
                detail = (
                    f"{layer_fired} rules fired in {layer} layer < "
                    f"threshold {min_rules_per_dimension}"
                )

        dimension_results.append(DeliveryDimensionResult(
            dimension=dimension,
            fired=fired,
            observed_value=observed,
            threshold=threshold,
            detail=detail,
        ))

    # ── Verdict ──
    dimensions_fired = sum(1 for d in dimension_results if d.fired)

    if dimensions_fired >= 2:
        verdict = DeliveryVerdict.RED
    elif dimensions_fired >= 1:
        verdict = DeliveryVerdict.YELLOW
    else:
        verdict = DeliveryVerdict.GREEN

    return DeliveryGateOutcome(
        verdict=verdict,
        dimensions_fired=dimensions_fired,
        dimension_results=dimension_results,
        methodology_note=(
            f"Delivery EVG v1.0: GREEN=0 dims fired, YELLOW=1 dim, RED=2+ dims. "
            f"Per-dimension threshold: {min_rules_per_dimension} rules per layer."
        ),
    )
