"""
Tests for SUNLIGHT Side 4 — CPD Allocation Intelligence.

Covers:
    Gap-Weighted Allocation:
        - Clear underspending: largest gap gets largest share
        - All pillars on target: equal distribution
        - One pillar overspent: floor allocation (5%) applied
        - Pillar allocations sum to 100% after normalization
        - Output-level allocation within pillar: gap-proportional
        - Zero recovery amount produces zero allocations (no division error)
        - Single-pillar CPD: 100% allocation to that pillar
        - Rationale string traces to data

    CPD Profile Loading:
        - JSON profile loads correctly from directory
        - Missing profile returns None, not crash
        - Profile with zero total budget handled gracefully
        - In-memory dict loading
"""

import sys
import os
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from cpd_allocation import (
    CPDPillarTarget,
    CPDOutputTarget,
    CountryProgrammeProfile,
    PillarAllocation,
    AllocationRecommendation,
    compute_gap_weighted_allocation,
    load_cpd_profile,
    load_cpd_profile_from_dict,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _make_cpd(
    pillars=None,
    outputs=None,
    country_office="Nigeria",
    country_code="NG",
    programme_cycle="2022-2026",
    total_programme_budget=50_000_000,
    currency="USD",
):
    return CountryProgrammeProfile(
        country_office=country_office,
        country_code=country_code,
        programme_cycle=programme_cycle,
        total_programme_budget=total_programme_budget,
        currency=currency,
        pillars=pillars or [],
        outputs=outputs or [],
    )


def _make_pillar(
    pillar="health",
    target_pct=0.25,
    actual_pct=0.18,
    target_amount=12_500_000,
    actual_spend=9_000_000,
    sdg_targets=None,
):
    return CPDPillarTarget(
        pillar=pillar,
        sdg_targets=sdg_targets or [],
        target_percentage=target_pct,
        target_amount=target_amount,
        actual_spend=actual_spend,
        actual_percentage=actual_pct,
    )


# ═══════════════════════════════════════════════════════════
# GAP-WEIGHTED ALLOCATION TESTS
# ═══════════════════════════════════════════════════════════


class TestGapWeightedAllocation:
    def test_largest_gap_gets_largest_share(self):
        """Pillar with biggest gap gets the most recovered funds."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.30, actual_pct=0.15),   # gap +15%
            _make_pillar("education", target_pct=0.25, actual_pct=0.20),  # gap +5%
            _make_pillar("governance", target_pct=0.25, actual_pct=0.25),  # gap 0%
            _make_pillar("energy", target_pct=0.20, actual_pct=0.20),     # gap 0%
        ])
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R001")
        # Health has 15% gap, education 5%, governance and energy 0% (floor)
        health = next(pa for pa in result.pillar_allocations if pa.pillar == "health")
        education = next(pa for pa in result.pillar_allocations if pa.pillar == "education")
        assert health.allocation_percentage > education.allocation_percentage
        assert health.allocation_amount > education.allocation_amount

    def test_all_pillars_on_target_equal_distribution(self):
        """No gaps → equal distribution."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.25, actual_pct=0.25),
            _make_pillar("education", target_pct=0.25, actual_pct=0.25),
            _make_pillar("governance", target_pct=0.25, actual_pct=0.25),
            _make_pillar("energy", target_pct=0.25, actual_pct=0.25),
        ])
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R002")
        for pa in result.pillar_allocations:
            assert abs(pa.allocation_percentage - 0.25) < 0.001
            assert abs(pa.allocation_amount - 250_000) < 1

    def test_overspent_pillar_gets_floor(self):
        """Overspent pillar (negative gap) gets 5% floor allocation."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.25, actual_pct=0.40),   # overspent
            _make_pillar("education", target_pct=0.25, actual_pct=0.10),  # underspent
        ])
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R003")
        health = next(pa for pa in result.pillar_allocations if pa.pillar == "health")
        education = next(pa for pa in result.pillar_allocations if pa.pillar == "education")
        # Health gets floor, education gets the rest
        assert health.allocation_percentage < education.allocation_percentage
        # Both still sum to 100%
        total = sum(pa.allocation_percentage for pa in result.pillar_allocations)
        assert abs(total - 1.0) < 0.001

    def test_allocations_sum_to_100(self):
        """After normalization, pillar allocations sum to exactly 100%."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.30, actual_pct=0.15),
            _make_pillar("education", target_pct=0.25, actual_pct=0.20),
            _make_pillar("governance", target_pct=0.25, actual_pct=0.30),
            _make_pillar("energy", target_pct=0.20, actual_pct=0.15),
        ])
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R004")
        total_pct = sum(pa.allocation_percentage for pa in result.pillar_allocations)
        assert abs(total_pct - 1.0) < 0.001
        total_amt = sum(pa.allocation_amount for pa in result.pillar_allocations)
        assert abs(total_amt - 1_000_000) < 1

    def test_output_level_allocation(self):
        """Within a pillar, outputs are allocated proportional to their gap."""
        cpd = _make_cpd(
            pillars=[
                _make_pillar("health", target_pct=0.50, actual_pct=0.25),
            ],
            outputs=[
                CPDOutputTarget("3.1.1", "Primary clinics", "health",
                                target_amount=5_000_000, actual_spend=2_000_000),
                CPDOutputTarget("3.1.2", "Vaccine supply", "health",
                                target_amount=3_000_000, actual_spend=2_500_000),
            ],
        )
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R005")
        clinic = next(oa for oa in result.output_allocations if oa.output_id == "3.1.1")
        vaccine = next(oa for oa in result.output_allocations if oa.output_id == "3.1.2")
        # Clinic gap: 3M, Vaccine gap: 0.5M → clinic gets more
        assert clinic.allocation_amount > vaccine.allocation_amount

    def test_zero_recovery_no_division_error(self):
        """Zero recovery produces zero allocations without errors."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.50, actual_pct=0.25),
        ])
        result = compute_gap_weighted_allocation(cpd, 0, "R006")
        assert result.recovery_amount == 0
        for pa in result.pillar_allocations:
            assert pa.allocation_amount == 0

    def test_single_pillar_gets_100_percent(self):
        """Single pillar CPD → 100% allocation to that pillar."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=1.0, actual_pct=0.50),
        ])
        result = compute_gap_weighted_allocation(cpd, 500_000, "R007")
        assert len(result.pillar_allocations) == 1
        assert abs(result.pillar_allocations[0].allocation_percentage - 1.0) < 0.001
        assert abs(result.pillar_allocations[0].allocation_amount - 500_000) < 1

    def test_rationale_traces_to_data(self):
        """Rationale string contains recovery amount, top pillar, CPD reference."""
        cpd = _make_cpd(pillars=[
            _make_pillar("health", target_pct=0.30, actual_pct=0.15),
            _make_pillar("education", target_pct=0.25, actual_pct=0.20),
        ])
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R008")
        assert "1,000,000" in result.rationale
        assert "health" in result.rationale
        assert "Nigeria" in result.rationale
        assert "2022-2026" in result.rationale

    def test_methodology_is_gap_weighted(self):
        cpd = _make_cpd(pillars=[_make_pillar("health")])
        result = compute_gap_weighted_allocation(cpd, 100_000, "R009")
        assert result.methodology == "gap_weighted"

    def test_no_pillars_produces_empty_recommendation(self):
        cpd = _make_cpd(pillars=[])
        result = compute_gap_weighted_allocation(cpd, 100_000, "R010")
        assert len(result.pillar_allocations) == 0


# ═══════════════════════════════════════════════════════════
# CPD PROFILE LOADING TESTS
# ═══════════════════════════════════════════════════════════


class TestCPDProfileLoading:
    def test_load_from_json(self):
        """JSON profile loads correctly from directory."""
        profile_data = {
            "country_office": "TestLand",
            "country_code": "TL",
            "programme_cycle": "2022-2026",
            "total_programme_budget": 10_000_000,
            "currency": "USD",
            "pillars": [
                {
                    "pillar": "health",
                    "sdg_targets": ["SDG 3"],
                    "target_percentage": 0.50,
                    "target_amount": 5_000_000,
                    "actual_spend": 3_000_000,
                    "actual_percentage": 0.30,
                }
            ],
            "outputs": [
                {
                    "output_id": "1.1",
                    "output_description": "Test output",
                    "pillar": "health",
                    "target_amount": 2_000_000,
                    "actual_spend": 1_000_000,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "tl.json")
            with open(filepath, "w") as f:
                json.dump(profile_data, f)

            cpd = load_cpd_profile("TL", cpd_dir=tmpdir)
            assert cpd is not None
            assert cpd.country_office == "TestLand"
            assert cpd.country_code == "TL"
            assert len(cpd.pillars) == 1
            assert cpd.pillars[0].pillar == "health"
            assert len(cpd.outputs) == 1

    def test_missing_profile_returns_none(self):
        """Missing profile returns None, not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cpd = load_cpd_profile("NONEXISTENT", cpd_dir=tmpdir)
            assert cpd is None

    def test_zero_budget_profile(self):
        """Profile with zero total budget loads and computes gracefully."""
        cpd = _make_cpd(
            total_programme_budget=0,
            pillars=[
                _make_pillar("health", target_pct=0.50, actual_pct=0.00,
                             target_amount=0, actual_spend=0),
            ],
        )
        result = compute_gap_weighted_allocation(cpd, 100_000, "R011")
        assert len(result.pillar_allocations) == 1
        assert result.pillar_allocations[0].allocation_amount > 0

    def test_load_from_dict(self):
        """In-memory dict loading works correctly."""
        data = {
            "country_office": "DictLand",
            "country_code": "DL",
            "programme_cycle": "2024-2028",
            "total_programme_budget": 5_000_000,
            "currency": "EUR",
            "pillars": [
                {"pillar": "governance", "target_percentage": 0.40,
                 "target_amount": 2_000_000, "actual_spend": 1_500_000,
                 "actual_percentage": 0.30},
            ],
        }
        cpd = load_cpd_profile_from_dict(data)
        assert cpd.country_office == "DictLand"
        assert cpd.currency == "EUR"
        assert len(cpd.pillars) == 1


# ═══════════════════════════════════════════════════════════
# SEED PROFILE LOADING TESTS
# ═══════════════════════════════════════════════════════════


class TestSeedProfileLoading:
    """Load seed CPD profiles from data/cpd_profiles/ and verify structure."""

    def _cpd_dir(self):
        test_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(test_dir, "..", "data", "cpd_profiles")

    def test_nigeria_profile_loads(self):
        cpd = load_cpd_profile("ng", cpd_dir=self._cpd_dir())
        assert cpd is not None
        assert cpd.country_office == "Nigeria"
        assert cpd.country_code == "NG"
        assert cpd.total_programme_budget == 120_000_000
        assert len(cpd.pillars) == 5
        pillar_names = {p.pillar for p in cpd.pillars}
        assert "health" in pillar_names
        assert "education" in pillar_names
        assert "governance" in pillar_names

    def test_nigeria_allocation_runs(self):
        """Gap-weighted allocation runs on the Nigeria seed profile."""
        cpd = load_cpd_profile("ng", cpd_dir=self._cpd_dir())
        result = compute_gap_weighted_allocation(cpd, 1_000_000, "R-NG-001")
        assert len(result.pillar_allocations) == 5
        total = sum(pa.allocation_amount for pa in result.pillar_allocations)
        assert abs(total - 1_000_000) < 1.0

    def test_ukraine_profile_loads(self):
        cpd = load_cpd_profile("ua", cpd_dir=self._cpd_dir())
        assert cpd is not None
        assert cpd.country_office == "Ukraine"
        assert cpd.country_code == "UA"
        assert cpd.total_programme_budget == 85_000_000
        assert len(cpd.pillars) == 5
        pillar_names = {p.pillar for p in cpd.pillars}
        assert "recovery" in pillar_names
        assert "governance" in pillar_names

    def test_ukraine_allocation_runs(self):
        """Gap-weighted allocation runs on the Ukraine seed profile."""
        cpd = load_cpd_profile("ua", cpd_dir=self._cpd_dir())
        result = compute_gap_weighted_allocation(cpd, 500_000, "R-UA-001")
        assert len(result.pillar_allocations) == 5
        total = sum(pa.allocation_amount for pa in result.pillar_allocations)
        assert abs(total - 500_000) < 1.0

    def test_nonexistent_profile_returns_none(self):
        cpd = load_cpd_profile("xx", cpd_dir=self._cpd_dir())
        assert cpd is None
