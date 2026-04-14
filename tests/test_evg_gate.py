"""
Tests for the Evidence Verification Gate (EVG).
================================================

10 unit tests covering the EVG gate function's three-verdict tier logic,
per-dimension threshold evaluation, boundary conditions, and null-input
handling.  Plus 1 integration test verifying EVG reads the real data shape
produced by tca_analyzer.py (closes the key-mismatch test-coverage gap).

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
from sunlight_core import ContractDossier, PriceResult, StructuralResult, StructuralVerdict
from global_parameters import GlobalParameters, get_global_parameters
from tca_rules import TCAGraphRuleEngine
from tca_analyzer import analyze_tca_graph
from jurisdiction_profile import US_FEDERAL


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


# ═══════════════════════════════════════════════════════════════════════════
# Test Suite: Integration with real TCA output shape
# ═══════════════════════════════════════════════════════════════════════════


class TestEVGIntegrationWithTCAOutput:
    """Verify EVG reads the actual data shape produced by tca_analyzer.py.

    This test constructs a ContractDossier, runs it through the real
    TCAGraphRuleEngine + analyze_tca_graph path, and feeds the resulting
    StructuralResult into the EVG gate.  It catches key-mismatch bugs
    like the "rule" vs "rule_id" incident (commit 706df82) by exercising
    the real production data flow rather than synthetic helpers.
    """

    def test_evg_reads_real_tca_contradiction_keys(self):
        """StructuralResult from real TCA pipeline has correct keys for EVG.

        Fixture: direct procurement at $500K (above $100K competitive
        threshold) with award_date 2017-09-20 (US fiscal year-end month,
        day >= 15).  Expected to fire PROC-001 and TIME-001 minimum,
        producing at least 2 REMOVES (contradiction) edges.

        Assertions:
          (a) Shape: every contradiction dict contains the "rule" key.
          (b) Count: EVG's observed_value for TCA_TYPOLOGIES matches an
              independent count of distinct rules from the same data.
        """
        # Build a dossier that reliably fires PROC-001 + TIME-001
        dossier = ContractDossier(
            contract_id="EVG-INTEGRATION-001",
            ocid="ocds-test-evg-integration-001",
            raw_ocds={
                "ocid": "ocds-test-evg-integration-001",
                "tag": ["US"],
                "parties": [
                    {"name": "Test Agency", "roles": ["buyer"],
                     "address": {"countryName": "us"}},
                    {"name": "Test Supplier", "id": "US-TEST-001",
                     "roles": ["supplier"],
                     "address": {"countryName": "us"}},
                ],
                "tender": {
                    "value": {"amount": 500_000, "currency": "USD"},
                    "procurementMethod": "direct",
                    "numberOfTenderers": 1,
                    "mainProcurementCategory": "goods",
                },
                "awards": [{"value": {"amount": 500_000, "currency": "USD"},
                            "date": "2017-09-20"}],
            },
            buyer_name="Test Agency",
            supplier_name="Test Supplier",
            procurement_method="direct",
            tender_value=500_000,
            award_value=500_000,
            currency="USD",
            number_of_tenderers=1,
            award_date="2017-09-20",
            country_code="US",
            sector="goods",
        )

        # Run real TCA pipeline under US_FEDERAL profile
        engine = TCAGraphRuleEngine(profile=US_FEDERAL)
        engine.build_graph(dossier)
        structure = analyze_tca_graph(dossier)

        # Pre-condition: at least one REMOVES edge was produced
        assert len(structure.contradictions) > 0, (
            "No REMOVES edges produced — test fixture needs adjustment"
        )

        # (a) Shape correctness: contradictions use the key that EVG reads
        for c in structure.contradictions:
            assert "rule" in c, (
                f"Contradiction missing 'rule' key. Keys present: "
                f"{sorted(c.keys())}.  EVG reads c.get('rule') — if this "
                f"key is absent, TCA_TYPOLOGIES will never fire."
            )
            assert c["rule"] != "UNKNOWN", (
                f"Contradiction has rule=UNKNOWN.  EVG counts distinct "
                f"rule IDs; UNKNOWN values collapse typology count."
            )

        # (b) Count correctness: EVG's observed value matches independent count
        gp = get_global_parameters("us_federal_v0")
        outcome = gate(None, structure, gp)  # price=None, structure only

        tca_dim = [d for d in outcome.dimension_results
                   if d.dimension == EvidenceDimension.TCA_TYPOLOGIES][0]

        # Independent count of distinct rules from contradictions
        distinct_rules = set()
        for c in structure.contradictions:
            rule_id = c.get("rule") or c.get("rule_id", "")
            if rule_id:
                distinct_rules.add(rule_id)
        expected = float(len(distinct_rules))

        assert tca_dim.observed_value == expected, (
            f"EVG observed {tca_dim.observed_value} typologies but "
            f"structure has {expected} distinct rules: {sorted(distinct_rules)}.  "
            f"Key mismatch between tca_analyzer output and EVG reader."
        )
