"""
SUNLIGHT Evidence Verification Gate (EVG)
==========================================

Multi-dimensional hard-evidence gate that combines CRI statistical indicators
and TCA structural findings against MJPIS-derived thresholds to produce a
tiered evidence verdict.

Dimensions:
    CRI_MARKUP — Price markup ratio above MJPIS empirical floor
    CRI_BRIBERY_CHANNEL — Bribery-channel ratio above MJPIS floor (future)
    TCA_TYPOLOGIES — Distinct structural typology triggers above threshold

Verdicts:
    GREEN — No dimension above threshold
    YELLOW — At least one dimension above threshold
    RED — At least two dimensions above threshold simultaneously

The administrative_sanctionable_threshold_months parameter does NOT gate at
per-contract level. It is reserved for case-packet output (post-gate
aggregation) and is not evaluated as an EVG dimension.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from sunlight_core import PriceResult, StructuralResult
from global_parameters import GlobalParameters


# ═══════════════════════════════════════════════════════════════════════════
# ENUMERATIONS
# ═══════════════════════════════════════════════════════════════════════════


class EvidenceVerdict(Enum):
    """EVG evidence gate verdict."""
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class EvidenceDimension(Enum):
    """Dimensions evaluated by the EVG gate."""
    CRI_MARKUP = "cri_markup"
    CRI_BRIBERY_CHANNEL = "cri_bribery_channel"
    TCA_TYPOLOGIES = "tca_typologies"


# ═══════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class DimensionResult:
    """Result of evaluating a single EVG dimension."""
    dimension: EvidenceDimension
    fired: bool
    observed_value: Optional[float]
    threshold: Optional[float]
    detail: str


@dataclass
class GateOutcome:
    """Full EVG gate outcome with per-dimension traceability."""
    verdict: EvidenceVerdict
    dimensions_fired: int
    dimension_results: List[DimensionResult]
    global_params_version: str
    methodology_note: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# GATE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════


def gate(
    price: Optional[PriceResult],
    structure: Optional[StructuralResult],
    global_params: GlobalParameters,
) -> GateOutcome:
    """
    Evaluate the Evidence Verification Gate.

    Combines CRI price analysis and TCA structural analysis outputs against
    MJPIS-calibrated thresholds to produce a tiered evidence verdict.

    Args:
        price: CRI price analysis result (PriceResult from dossier pipeline).
               May be None if price stage was not reached.
        structure: TCA structural analysis result (StructuralResult from
                   dossier pipeline). May be None if structure stage was
                   not reached.
        global_params: MJPIS-calibrated thresholds (GlobalParameters instance
                       for the active jurisdiction profile).

    Returns:
        GateOutcome with verdict (GREEN/YELLOW/RED) and per-dimension detail.
    """
    dimension_results: List[DimensionResult] = []

    # ── CRI_MARKUP dimension ──
    markup_fired = False
    markup_observed: Optional[float] = None
    markup_threshold = global_params.markup_floor_ratio
    markup_detail = "No price data available"

    if price is not None and price.markup_pct is not None:
        # markup_pct is a percentage (e.g. 75.0 for 75%); convert to ratio
        markup_ratio = price.markup_pct / 100.0
        markup_observed = markup_ratio
        if markup_ratio >= markup_threshold:
            markup_fired = True
            markup_detail = (
                f"Markup ratio {markup_ratio:.4f} >= "
                f"MJPIS floor {markup_threshold:.4f}"
            )
        else:
            markup_detail = (
                f"Markup ratio {markup_ratio:.4f} < "
                f"MJPIS floor {markup_threshold:.4f}"
            )

    dimension_results.append(DimensionResult(
        dimension=EvidenceDimension.CRI_MARKUP,
        fired=markup_fired,
        observed_value=markup_observed,
        threshold=markup_threshold,
        detail=markup_detail,
    ))

    # ── CRI_BRIBERY_CHANNEL dimension ──
    # Not yet consumable — no bribery-channel data flows through the dossier
    # pipeline. When the bribery-channel consumer module is built, this
    # dimension will check the observed bribery-channel ratio against
    # global_params.bribery_channel_ratio.
    bc_fired = False
    bc_observed: Optional[float] = None
    bc_threshold = global_params.bribery_channel_ratio
    bc_detail = "Bribery-channel data not yet available in pipeline"

    dimension_results.append(DimensionResult(
        dimension=EvidenceDimension.CRI_BRIBERY_CHANNEL,
        fired=bc_fired,
        observed_value=bc_observed,
        threshold=bc_threshold,
        detail=bc_detail,
    ))

    # ── TCA_TYPOLOGIES dimension ──
    tca_fired = False
    tca_observed: Optional[float] = None
    tca_threshold = float(global_params.min_typologies_for_red)
    tca_detail = "No structural data available"

    if structure is not None:
        # Count distinct rule_ids in structural contradictions.
        # Each distinct rule_id represents a different typology trigger.
        rule_ids = set()
        for c in structure.contradictions:
            # tca_analyzer.py produces key "rule"; accept both for robustness
            rule_id = c.get("rule") or c.get("rule_id", "")
            if rule_id:
                rule_ids.add(rule_id)
        distinct_typologies = len(rule_ids)
        tca_observed = float(distinct_typologies)

        if distinct_typologies >= global_params.min_typologies_for_red:
            tca_fired = True
            tca_detail = (
                f"{distinct_typologies} distinct typologies >= "
                f"threshold {global_params.min_typologies_for_red}"
            )
        else:
            tca_detail = (
                f"{distinct_typologies} distinct typologies < "
                f"threshold {global_params.min_typologies_for_red}"
            )

    dimension_results.append(DimensionResult(
        dimension=EvidenceDimension.TCA_TYPOLOGIES,
        fired=tca_fired,
        observed_value=tca_observed,
        threshold=tca_threshold,
        detail=tca_detail,
    ))

    # ── Verdict ──
    dimensions_fired = sum(1 for d in dimension_results if d.fired)

    if dimensions_fired >= 2:
        verdict = EvidenceVerdict.RED
    elif dimensions_fired >= 1:
        verdict = EvidenceVerdict.YELLOW
    else:
        verdict = EvidenceVerdict.GREEN

    return GateOutcome(
        verdict=verdict,
        dimensions_fired=dimensions_fired,
        dimension_results=dimension_results,
        global_params_version=global_params.version,
        methodology_note=(
            "EVG v1.0: GREEN=0 dims fired, YELLOW=1 dim, RED=2+ dims. "
            f"Thresholds from {global_params.version}."
        ),
    )
