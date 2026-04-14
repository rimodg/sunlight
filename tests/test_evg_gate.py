"""
Tests for the Evidence Verification Gate (EVG).
================================================

10 regression tests covering the EVG gate function's three-verdict tier
logic, per-dimension threshold evaluation, boundary conditions, and
null-input handling.

Run with:  pytest tests/test_evg_gate.py -v
"""

import os
import sys

import pytest

# Ensure code/ is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from evg import (
    EvidenceDimension,
    EvidenceVerdict,
    GateOutcome,
    DimensionResult,
    gate,
)
from sunlight_core import PriceResult, StructuralResult, StructuralVerdict
from global_parameters import GlobalParameters


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_global_params(**overrides) -> GlobalParameters:
    """Create a GlobalParameters instance with test defaults."""
    defaults = dict(
        version="test_v0",
        markup_floor_ratio=0.50,           # 50% markup floor
        bribery_channel_ratio=0.01,        # 1% bribery-channel floor
        min_typologies_for_red=2,          # Need 2 distinct typologies
        # Fields below are required by the dataclass but not consumed by EVG
        evidentiary_standard="test",
        default_base_rate=0.03,
        red_posterior_threshold=0.72,
        yellow_posterior_threshold=0.38,
        min_ci_for_yellow=66,
        fdr_alpha=0.05,
        bootstrap_ci_level=0.95,
        bootstrap_n_resamples=1_000,
        max_flags_per_1k=150,
    )
    defaults.update(overrides)
    return GlobalParameters(**defaults)


def _make_price(markup_pct: float = 0.0) -> PriceResult:
    """Create a PriceResult with a given markup percentage."""
    return PriceResult(
        price_score=0.5,
        peer_count=10,
        bootstrap_ci_lower=0,
        bootstrap_ci_upper=100,
        bayesian_posterior=0.5,
        within_ci=True,
        markup_pct=markup_pct,
    )


def _make_structure(rule_ids: list[str] | None = None) -> StructuralResult:
    """Create a StructuralResult with contradictions tagged by rule_id."""
    contradictions = []
    if rule_ids:
        for rid in rule_ids:
            contradictions.append({
                "rule": rid,
                "severity": "high",
                "description": f"Finding from {rid}",
                "evidence": "test evidence",
                "legal_citations": [],
            })
    return StructuralResult(
        confidence=0.4,
        verdict=StructuralVerdict.COMPROMISED,
        contradictions=contradictions,
        feedback_traps=[],
        unproven=[],
        verified=[],
        edge_distribution={},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite: Three-verdict tier logic
# ═══════════════════════════════════════════════════════════════════════════


class TestEVGVerdictTiers:
    """Tests covering the GREEN / YELLOW / RED verdict assignment."""

    def test_green_no_dimensions_fire(self):
        """Clean contract: low markup, no typologies → GREEN."""
        gp = _make_global_params(markup_floor_ratio=0.50, min_typologies_for_red=2)
        price = _make_price(markup_pct=10.0)  # 10% = 0.10 ratio < 0.50
        structure = _make_structure(rule_ids=[])

        outcome = gate(price, structure, gp)

        assert outcome.verdict == EvidenceVerdict.GREEN
        assert outcome.dimensions_fired == 0

    def test_yellow_only_markup_fires(self):
        """High markup, insufficient typologies → YELLOW (1 dim)."""
        gp = _make_global_params(markup_floor_ratio=0.50, min_typologies_for_red=2)
        price = _make_price(markup_pct=60.0)  # 60% = 0.60 ratio >= 0.50
        structure = _make_structure(rule_ids=["FIN-001"])  # Only 1 typology < 2

        outcome = gate(price, structure, gp)

        assert outcome.verdict == EvidenceVerdict.YELLOW
        assert outcome.dimensions_fired == 1
        # Verify CRI_MARKUP fired
        markup_dim = [d for d in outcome.dimension_results
                      if d.dimension == EvidenceDimension.CRI_MARKUP][0]
        assert markup_dim.fired is True

    def test_yellow_only_typologies_fire(self):
        """Low markup, multiple typologies → YELLOW (1 dim)."""
        gp = _make_global_params(markup_floor_ratio=0.50, min_typologies_for_red=2)
        price = _make_price(markup_pct=10.0)  # 10% = 0.10 < 0.50
        structure = _make_structure(rule_ids=["FIN-001", "COMP-001"])  # 2 typologies >= 2

        outcome = gate(price, structure, gp)

        assert outcome.verdict == EvidenceVerdict.YELLOW
        assert outcome.dimensions_fired == 1
        # Verify TCA_TYPOLOGIES fired
        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]
        assert tca_dim.fired is True

    def test_red_markup_and_typologies_fire(self):
        """High markup + multiple typologies → RED (2 dims)."""
        gp = _make_global_params(markup_floor_ratio=0.50, min_typologies_for_red=2)
        price = _make_price(markup_pct=80.0)  # 80% = 0.80 >= 0.50
        structure = _make_structure(rule_ids=["FIN-001", "COMP-001", "PROC-001"])  # 3 >= 2

        outcome = gate(price, structure, gp)

        assert outcome.verdict == EvidenceVerdict.RED
        assert outcome.dimensions_fired == 2


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite: Boundary conditions
# ═══════════════════════════════════════════════════════════════════════════


class TestEVGBoundaryConditions:
    """Tests covering threshold boundary behavior."""

    def test_markup_just_below_threshold(self):
        """Markup ratio 0.4999 with floor 0.50 → does NOT fire."""
        gp = _make_global_params(markup_floor_ratio=0.50)
        price = _make_price(markup_pct=49.99)  # 0.4999 < 0.50
        structure = _make_structure(rule_ids=[])

        outcome = gate(price, structure, gp)

        markup_dim = [d for d in outcome.dimension_results
                      if d.dimension == EvidenceDimension.CRI_MARKUP][0]
        assert markup_dim.fired is False
        assert outcome.verdict == EvidenceVerdict.GREEN

    def test_markup_exactly_at_threshold(self):
        """Markup ratio exactly 0.50 with floor 0.50 → fires (>=)."""
        gp = _make_global_params(markup_floor_ratio=0.50)
        price = _make_price(markup_pct=50.0)  # 0.50 >= 0.50
        structure = _make_structure(rule_ids=[])

        outcome = gate(price, structure, gp)

        markup_dim = [d for d in outcome.dimension_results
                      if d.dimension == EvidenceDimension.CRI_MARKUP][0]
        assert markup_dim.fired is True
        assert outcome.verdict == EvidenceVerdict.YELLOW

    def test_single_typology_below_threshold_of_two(self):
        """1 typology when threshold=2 → does NOT fire."""
        gp = _make_global_params(min_typologies_for_red=2)
        price = _make_price(markup_pct=0.0)
        structure = _make_structure(rule_ids=["FIN-001"])

        outcome = gate(price, structure, gp)

        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]
        assert tca_dim.fired is False
        assert tca_dim.observed_value == 1.0

    def test_two_typologies_at_threshold_of_two(self):
        """2 typologies when threshold=2 → fires (>=)."""
        gp = _make_global_params(min_typologies_for_red=2)
        price = _make_price(markup_pct=0.0)
        structure = _make_structure(rule_ids=["FIN-001", "COMP-001"])

        outcome = gate(price, structure, gp)

        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]
        assert tca_dim.fired is True
        assert tca_dim.observed_value == 2.0


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite: Null/missing input handling
# ═══════════════════════════════════════════════════════════════════════════


class TestEVGNullInputs:
    """Tests covering None price and None structure inputs."""

    def test_null_price_does_not_fire_markup(self):
        """price=None → CRI_MARKUP does not fire, TCA still evaluates."""
        gp = _make_global_params(min_typologies_for_red=2)
        structure = _make_structure(rule_ids=["FIN-001", "COMP-001"])  # 2 typologies

        outcome = gate(None, structure, gp)

        markup_dim = [d for d in outcome.dimension_results
                      if d.dimension == EvidenceDimension.CRI_MARKUP][0]
        assert markup_dim.fired is False
        assert markup_dim.observed_value is None
        # TCA should still fire
        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]
        assert tca_dim.fired is True
        assert outcome.verdict == EvidenceVerdict.YELLOW

    def test_null_structure_does_not_fire_typologies(self):
        """structure=None → TCA_TYPOLOGIES does not fire, CRI still evaluates."""
        gp = _make_global_params(markup_floor_ratio=0.50)
        price = _make_price(markup_pct=60.0)  # fires

        outcome = gate(price, None, gp)

        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]
        assert tca_dim.fired is False
        assert tca_dim.observed_value is None
        # CRI should still fire
        markup_dim = [d for d in outcome.dimension_results
                      if d.dimension == EvidenceDimension.CRI_MARKUP][0]
        assert markup_dim.fired is True
        assert outcome.verdict == EvidenceVerdict.YELLOW
