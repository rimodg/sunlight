"""
Tests for SUNLIGHT Side 2 delivery Evidence Verification Gate.

Covers:
    - GREEN verdict (0 dimensions fired)
    - YELLOW verdict (1 dimension fired)
    - RED verdict (2+ dimensions fired)
    - All 4 dimensions evaluated independently
    - Per-dimension traceability (observed_value, threshold, detail)
    - None rules_result handling
    - min_rules_per_dimension parameter variations
    - Boundary conditions (exactly at threshold, one below, one above)
    - Methodology note content
    - Integration: full rules_result through gate
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from delivery_schema import (
    DeliveryDimension,
    DeliveryDimensionResult,
    DeliveryGateOutcome,
    DeliveryRuleResult,
    DeliveryRulesResult,
    DeliveryVerdict,
)
from delivery_evg import (
    delivery_gate,
    DEFAULT_MIN_RULES_PER_DIMENSION,
    DIMENSION_LAYER_MAP,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _make_rules_result(
    milestone_fired: int = 0,
    resource_fired: int = 0,
    outcome_fired: int = 0,
    financial_fired: int = 0,
) -> DeliveryRulesResult:
    """Build a DeliveryRulesResult with specified fired counts per layer."""
    rule_results = []
    layer_summary = {}

    for layer, count, ids in [
        ("milestone", milestone_fired, ["DEL-MILE-001", "DEL-MILE-002", "DEL-MILE-003"]),
        ("resource", resource_fired, ["DEL-RES-001", "DEL-RES-002", "DEL-RES-003"]),
        ("outcome", outcome_fired, ["DEL-OUT-001", "DEL-OUT-002", "DEL-OUT-003"]),
        ("financial", financial_fired, ["DEL-FIN-001", "DEL-FIN-002", "DEL-FIN-003"]),
    ]:
        for i, rule_id in enumerate(ids):
            fired = i < count
            rule_results.append(DeliveryRuleResult(
                rule_id=rule_id,
                layer=layer,
                fired=fired,
                evidence=f"Test evidence for {rule_id}" if fired else "",
                confidence=0.8 if fired else 0.0,
            ))
        if count > 0:
            layer_summary[layer] = count

    return DeliveryRulesResult(
        rules_evaluated=12,
        rules_fired=milestone_fired + resource_fired + outcome_fired + financial_fired,
        rule_results=rule_results,
        layer_summary=layer_summary,
    )


def _dim_result(outcome: DeliveryGateOutcome, dim: DeliveryDimension) -> DeliveryDimensionResult:
    """Extract a specific dimension result from a gate outcome."""
    return next(d for d in outcome.dimension_results if d.dimension == dim)


# ═══════════════════════════════════════════════════════════
# VERDICT TIER TESTS
# ═══════════════════════════════════════════════════════════


class TestGreenVerdict:
    def test_no_rules_fired(self):
        rr = _make_rules_result()
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.GREEN
        assert outcome.dimensions_fired == 0

    def test_one_rule_per_layer_still_green(self):
        """1 rule per layer < threshold of 2 → no dimensions fire → GREEN."""
        rr = _make_rules_result(
            milestone_fired=1,
            resource_fired=1,
            outcome_fired=1,
            financial_fired=1,
        )
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.GREEN
        assert outcome.dimensions_fired == 0

    def test_none_rules_result(self):
        outcome = delivery_gate(None)
        assert outcome.verdict == DeliveryVerdict.GREEN
        assert outcome.dimensions_fired == 0


class TestYellowVerdict:
    def test_one_dimension_fires(self):
        rr = _make_rules_result(milestone_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.YELLOW
        assert outcome.dimensions_fired == 1

    def test_milestone_dimension_only(self):
        rr = _make_rules_result(milestone_fired=3)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.YELLOW
        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.fired is True

    def test_resource_dimension_only(self):
        rr = _make_rules_result(resource_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.YELLOW
        resource = _dim_result(outcome, DeliveryDimension.RESOURCE_VERIFICATION)
        assert resource.fired is True

    def test_outcome_dimension_only(self):
        rr = _make_rules_result(outcome_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.YELLOW
        out = _dim_result(outcome, DeliveryDimension.OUTCOME_VERIFICATION)
        assert out.fired is True

    def test_financial_dimension_only(self):
        rr = _make_rules_result(financial_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.YELLOW
        fin = _dim_result(outcome, DeliveryDimension.FINANCIAL_RECONCILIATION)
        assert fin.fired is True


class TestRedVerdict:
    def test_two_dimensions_fire(self):
        rr = _make_rules_result(milestone_fired=2, financial_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 2

    def test_three_dimensions_fire(self):
        rr = _make_rules_result(milestone_fired=2, resource_fired=3, outcome_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 3

    def test_all_four_dimensions_fire(self):
        rr = _make_rules_result(
            milestone_fired=3,
            resource_fired=3,
            outcome_fired=3,
            financial_fired=3,
        )
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 4


# ═══════════════════════════════════════════════════════════
# DIMENSION TRACEABILITY TESTS
# ═══════════════════════════════════════════════════════════


class TestDimensionTraceability:
    def test_all_four_dimensions_always_present(self):
        rr = _make_rules_result()
        outcome = delivery_gate(rr)
        assert len(outcome.dimension_results) == 4
        dims = {d.dimension for d in outcome.dimension_results}
        assert dims == {
            DeliveryDimension.MILESTONE_COMPLIANCE,
            DeliveryDimension.RESOURCE_VERIFICATION,
            DeliveryDimension.OUTCOME_VERIFICATION,
            DeliveryDimension.FINANCIAL_RECONCILIATION,
        }

    def test_observed_value_reflects_fired_count(self):
        rr = _make_rules_result(milestone_fired=2, financial_fired=1)
        outcome = delivery_gate(rr)

        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.observed_value == 2.0
        assert milestone.fired is True

        financial = _dim_result(outcome, DeliveryDimension.FINANCIAL_RECONCILIATION)
        assert financial.observed_value == 1.0
        assert financial.fired is False

    def test_threshold_reflects_parameter(self):
        rr = _make_rules_result()
        outcome = delivery_gate(rr, min_rules_per_dimension=3)

        for d in outcome.dimension_results:
            assert d.threshold == 3.0

    def test_detail_string_populated_when_fired(self):
        rr = _make_rules_result(outcome_fired=2)
        outcome = delivery_gate(rr)
        out = _dim_result(outcome, DeliveryDimension.OUTCOME_VERIFICATION)
        assert out.fired is True
        assert "2 rules fired" in out.detail
        assert "outcome" in out.detail

    def test_detail_string_populated_when_not_fired(self):
        rr = _make_rules_result(outcome_fired=1)
        outcome = delivery_gate(rr)
        out = _dim_result(outcome, DeliveryDimension.OUTCOME_VERIFICATION)
        assert out.fired is False
        assert "1 rules fired" in out.detail

    def test_none_input_produces_no_observed_value(self):
        outcome = delivery_gate(None)
        for d in outcome.dimension_results:
            assert d.observed_value is None
            assert d.detail == "No delivery rule data available"


# ═══════════════════════════════════════════════════════════
# BOUNDARY CONDITION TESTS
# ═══════════════════════════════════════════════════════════


class TestBoundaryConditions:
    def test_exactly_at_threshold_fires(self):
        """Exactly 2 rules fired = threshold of 2 → fires."""
        rr = _make_rules_result(milestone_fired=2)
        outcome = delivery_gate(rr, min_rules_per_dimension=2)
        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.fired is True

    def test_one_below_threshold_does_not_fire(self):
        rr = _make_rules_result(milestone_fired=1)
        outcome = delivery_gate(rr, min_rules_per_dimension=2)
        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.fired is False

    def test_one_above_threshold_fires(self):
        rr = _make_rules_result(milestone_fired=3)
        outcome = delivery_gate(rr, min_rules_per_dimension=2)
        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.fired is True

    def test_threshold_of_1_makes_yellow_easier(self):
        """With threshold=1, a single rule firing trips the dimension."""
        rr = _make_rules_result(milestone_fired=1)
        outcome = delivery_gate(rr, min_rules_per_dimension=1)
        assert outcome.verdict == DeliveryVerdict.YELLOW

    def test_threshold_of_3_makes_red_harder(self):
        """With threshold=3, need all 3 rules per layer to trip dimension."""
        rr = _make_rules_result(milestone_fired=2, financial_fired=2)
        outcome = delivery_gate(rr, min_rules_per_dimension=3)
        # Both at 2 < 3, so no dimensions fire
        assert outcome.verdict == DeliveryVerdict.GREEN

    def test_exactly_two_dims_is_red_not_yellow(self):
        """Verify RED boundary: exactly 2 dimensions = RED."""
        rr = _make_rules_result(milestone_fired=2, resource_fired=2)
        outcome = delivery_gate(rr)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 2


# ═══════════════════════════════════════════════════════════
# MIN_RULES_PER_DIMENSION PARAMETER TESTS
# ═══════════════════════════════════════════════════════════


class TestMinRulesParameter:
    def test_default_is_2(self):
        assert DEFAULT_MIN_RULES_PER_DIMENSION == 2

    def test_threshold_1(self):
        rr = _make_rules_result(milestone_fired=1, resource_fired=1)
        outcome = delivery_gate(rr, min_rules_per_dimension=1)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 2

    def test_threshold_3(self):
        rr = _make_rules_result(
            milestone_fired=3,
            resource_fired=3,
            outcome_fired=2,
            financial_fired=1,
        )
        outcome = delivery_gate(rr, min_rules_per_dimension=3)
        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 2  # only milestone + resource at 3


# ═══════════════════════════════════════════════════════════
# METHODOLOGY NOTE TESTS
# ═══════════════════════════════════════════════════════════


class TestMethodologyNote:
    def test_note_populated(self):
        rr = _make_rules_result()
        outcome = delivery_gate(rr)
        assert "Delivery EVG v1.0" in outcome.methodology_note
        assert "GREEN=0" in outcome.methodology_note
        assert "RED=2+" in outcome.methodology_note

    def test_note_includes_threshold(self):
        outcome = delivery_gate(None, min_rules_per_dimension=3)
        assert "3 rules per layer" in outcome.methodology_note


# ═══════════════════════════════════════════════════════════
# DIMENSION-LAYER MAPPING TESTS
# ═══════════════════════════════════════════════════════════


class TestDimensionLayerMap:
    def test_all_four_dimensions_mapped(self):
        assert len(DIMENSION_LAYER_MAP) == 4
        assert DeliveryDimension.MILESTONE_COMPLIANCE in DIMENSION_LAYER_MAP
        assert DeliveryDimension.RESOURCE_VERIFICATION in DIMENSION_LAYER_MAP
        assert DeliveryDimension.OUTCOME_VERIFICATION in DIMENSION_LAYER_MAP
        assert DeliveryDimension.FINANCIAL_RECONCILIATION in DIMENSION_LAYER_MAP

    def test_milestone_maps_to_milestone_layer(self):
        assert DIMENSION_LAYER_MAP[DeliveryDimension.MILESTONE_COMPLIANCE] == "milestone"

    def test_resource_maps_to_resource_layer(self):
        assert DIMENSION_LAYER_MAP[DeliveryDimension.RESOURCE_VERIFICATION] == "resource"

    def test_outcome_maps_to_outcome_layer(self):
        assert DIMENSION_LAYER_MAP[DeliveryDimension.OUTCOME_VERIFICATION] == "outcome"

    def test_financial_maps_to_financial_layer(self):
        assert DIMENSION_LAYER_MAP[DeliveryDimension.FINANCIAL_RECONCILIATION] == "financial"


# ═══════════════════════════════════════════════════════════
# INTEGRATION TEST
# ═══════════════════════════════════════════════════════════


class TestDeliveryEVGIntegration:
    """Full integration: realistic rules_result through delivery gate."""

    def test_problematic_delivery_produces_red(self):
        """A delivery with problems across all 4 layers should be RED."""
        rr = _make_rules_result(
            milestone_fired=3,
            resource_fired=3,
            outcome_fired=3,
            financial_fired=3,
        )
        outcome = delivery_gate(rr)

        assert outcome.verdict == DeliveryVerdict.RED
        assert outcome.dimensions_fired == 4
        assert len(outcome.dimension_results) == 4

        # All dimensions fired
        for d in outcome.dimension_results:
            assert d.fired is True
            assert d.observed_value == 3.0
            assert d.threshold == 2.0
            assert "3 rules fired" in d.detail

    def test_clean_delivery_produces_green(self):
        """A delivery with no problems should be GREEN."""
        rr = _make_rules_result()
        outcome = delivery_gate(rr)

        assert outcome.verdict == DeliveryVerdict.GREEN
        assert outcome.dimensions_fired == 0

        for d in outcome.dimension_results:
            assert d.fired is False
            assert d.observed_value == 0.0

    def test_partial_problems_produce_yellow(self):
        """Problems in only one layer should be YELLOW."""
        rr = _make_rules_result(financial_fired=2)
        outcome = delivery_gate(rr)

        assert outcome.verdict == DeliveryVerdict.YELLOW
        assert outcome.dimensions_fired == 1

        fin = _dim_result(outcome, DeliveryDimension.FINANCIAL_RECONCILIATION)
        assert fin.fired is True
        assert fin.observed_value == 2.0

        # Other dimensions should not fire
        milestone = _dim_result(outcome, DeliveryDimension.MILESTONE_COMPLIANCE)
        assert milestone.fired is False
