"""
SUNLIGHT Side 4 — CPD Allocation Intelligence
================================================

Country Programme Document allocation logic. Reads the institution's own
stated priorities, compares to actual spending, computes gap-weighted
allocation recommendations for recovered funds.

The allocation logic is not SUNLIGHT's opinion. It reads the institution's
own published Country Programme Documents (CPDs), compares stated allocation
targets to actual spending, identifies the gaps, and recommends allocation
of recovered funds proportional to those gaps.

Every allocation remains a recommendation, not a directive.

CPD profiles are loaded from JSON files in data/cpd_profiles/ — one file
per country office. This allows the institution's own data team to update
profiles without code changes.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: CPD DATA STRUCTURES
# ═══════════════════════════════════════════════════════════


@dataclass
class CPDPillarTarget:
    """One pillar's allocation from the Country Programme Document."""
    pillar: str
    sdg_targets: List[str] = field(default_factory=list)
    target_percentage: float = 0.0
    target_amount: float = 0.0
    actual_spend: float = 0.0
    actual_percentage: float = 0.0

    @property
    def gap_percentage(self) -> float:
        """Positive = underspent, negative = overspent."""
        return self.target_percentage - self.actual_percentage

    @property
    def gap_amount(self) -> float:
        """Absolute gap in currency."""
        return self.target_amount - self.actual_spend


@dataclass
class CPDOutputTarget:
    """Specific output within a pillar from the CPD."""
    output_id: str
    output_description: str
    pillar: str
    target_amount: float = 0.0
    actual_spend: float = 0.0
    actual_delivery: Optional[str] = None
    delivery_verdict: Optional[str] = None

    @property
    def gap_amount(self) -> float:
        return self.target_amount - self.actual_spend


@dataclass
class CountryProgrammeProfile:
    """Full CPD allocation profile for one country office."""
    country_office: str
    country_code: str
    programme_cycle: str
    total_programme_budget: float
    currency: str
    pillars: List[CPDPillarTarget] = field(default_factory=list)
    outputs: List[CPDOutputTarget] = field(default_factory=list)
    last_updated: Optional[str] = None
    source_document: Optional[str] = None

    def get_pillar(self, pillar_name: str) -> Optional[CPDPillarTarget]:
        for p in self.pillars:
            if p.pillar == pillar_name:
                return p
        return None

    def get_outputs_for_pillar(self, pillar_name: str) -> List[CPDOutputTarget]:
        return [o for o in self.outputs if o.pillar == pillar_name]


# ═══════════════════════════════════════════════════════════
# SECTION 2: ALLOCATION DATA STRUCTURES
# ═══════════════════════════════════════════════════════════


@dataclass
class PillarAllocation:
    """How much of the recovery goes to each pillar."""
    pillar: str
    sdg_targets: List[str] = field(default_factory=list)
    cpd_target_percentage: float = 0.0
    actual_percentage: float = 0.0
    gap_percentage: float = 0.0
    allocation_percentage: float = 0.0
    allocation_amount: float = 0.0
    rationale: str = ""


@dataclass
class OutputAllocation:
    """Within a pillar, which specific output gets the funds."""
    output_id: str
    output_description: str
    pillar: str
    cpd_target_amount: float = 0.0
    actual_spend: float = 0.0
    gap_amount: float = 0.0
    allocation_amount: float = 0.0
    rationale: str = ""


@dataclass
class AllocationRecommendation:
    """Gap-weighted allocation recommendation for recovered funds."""
    recovery_id: str
    country_office: str
    recovery_amount: float
    currency: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    pillar_allocations: List[PillarAllocation] = field(default_factory=list)
    output_allocations: List[OutputAllocation] = field(default_factory=list)
    methodology: str = "gap_weighted"
    rationale: str = ""


# ═══════════════════════════════════════════════════════════
# SECTION 3: GAP-WEIGHTED ALLOCATION
# ═══════════════════════════════════════════════════════════


def compute_gap_weighted_allocation(
    cpd: CountryProgrammeProfile,
    recovery_amount: float,
    recovery_id: str,
) -> AllocationRecommendation:
    """
    Allocate recovered funds proportional to each pillar's gap
    between CPD target and actual spending.

    Pillars furthest below target get the largest share.
    Pillars at or above target get minimum allocation (floor of 5%
    to ensure every pillar receives some recovery benefit).

    Within each pillar, funds are further allocated to specific
    outputs proportional to their gap from CPD output targets.

    Args:
        cpd: Country Programme Profile with pillar targets and actuals.
        recovery_amount: Amount recovered to allocate.
        recovery_id: Links to the RecoveryRecord.

    Returns:
        AllocationRecommendation with per-pillar and per-output allocations.
    """
    if not cpd.pillars:
        return AllocationRecommendation(
            recovery_id=recovery_id,
            country_office=cpd.country_office,
            recovery_amount=recovery_amount,
            currency=cpd.currency,
            rationale="No pillars defined in CPD profile.",
        )

    if recovery_amount == 0:
        return AllocationRecommendation(
            recovery_id=recovery_id,
            country_office=cpd.country_office,
            recovery_amount=0,
            currency=cpd.currency,
            pillar_allocations=[
                PillarAllocation(
                    pillar=p.pillar,
                    sdg_targets=p.sdg_targets,
                    cpd_target_percentage=p.target_percentage,
                    actual_percentage=p.actual_percentage,
                    gap_percentage=p.gap_percentage,
                    allocation_percentage=0.0,
                    allocation_amount=0.0,
                    rationale="Zero recovery amount",
                )
                for p in cpd.pillars
            ],
            rationale="Zero recovery amount — no allocation computed.",
        )

    # Step 1: Compute gaps for all pillars
    pillar_gaps = []
    for p in cpd.pillars:
        gap = max(p.gap_percentage, 0)  # only positive gaps (underspent)
        pillar_gaps.append((p, gap))

    total_positive_gap = sum(g for _, g in pillar_gaps)

    # Step 2: Compute raw allocation percentages proportional to gaps
    pillar_allocations = []
    for pillar, gap in pillar_gaps:
        if total_positive_gap > 0:
            raw_pct = gap / total_positive_gap
        else:
            # No gaps — distribute equally
            raw_pct = 1.0 / len(cpd.pillars)

        # Floor: every pillar gets at least 5% of recovery
        alloc_pct = max(raw_pct, 0.05)

        pillar_allocations.append(PillarAllocation(
            pillar=pillar.pillar,
            sdg_targets=pillar.sdg_targets,
            cpd_target_percentage=pillar.target_percentage,
            actual_percentage=pillar.actual_percentage,
            gap_percentage=pillar.gap_percentage,
            allocation_percentage=alloc_pct,
            allocation_amount=recovery_amount * alloc_pct,
            rationale=f"Gap: {pillar.gap_percentage:+.1%} from CPD target",
        ))

    # Step 3: Normalize so allocations sum to 100%
    total_alloc = sum(pa.allocation_percentage for pa in pillar_allocations)
    if total_alloc > 0:
        for pa in pillar_allocations:
            pa.allocation_percentage /= total_alloc
            pa.allocation_amount = recovery_amount * pa.allocation_percentage

    # Step 4: Sort by allocation descending (largest gap first)
    pillar_allocations.sort(
        key=lambda pa: pa.allocation_percentage, reverse=True
    )

    # Step 5: Within each pillar, allocate to specific outputs by gap
    output_allocations = []
    for pa in pillar_allocations:
        pillar_outputs = cpd.get_outputs_for_pillar(pa.pillar)
        if not pillar_outputs:
            continue

        output_gaps = [(o, max(o.gap_amount, 0)) for o in pillar_outputs]
        total_output_gap = sum(g for _, g in output_gaps)

        for output, ogap in output_gaps:
            if total_output_gap > 0:
                output_pct = ogap / total_output_gap
            else:
                output_pct = 1.0 / len(pillar_outputs)

            output_allocations.append(OutputAllocation(
                output_id=output.output_id,
                output_description=output.output_description,
                pillar=pa.pillar,
                cpd_target_amount=output.target_amount,
                actual_spend=output.actual_spend,
                gap_amount=output.gap_amount,
                allocation_amount=pa.allocation_amount * output_pct,
                rationale=f"Output gap: {output.gap_amount:,.0f} {cpd.currency}",
            ))

    # Step 6: Assemble rationale
    top_pillar = pillar_allocations[0]
    rationale = (
        f"Recovery of {recovery_amount:,.0f} {cpd.currency} allocated across "
        f"{len(pillar_allocations)} development pillars using gap-weighted methodology. "
        f"Largest allocation ({top_pillar.allocation_percentage:.1%}) to "
        f"{top_pillar.pillar} (gap: {top_pillar.gap_percentage:+.1%} from CPD target). "
        f"Allocation grounded in {cpd.country_office} Country Programme Document "
        f"({cpd.programme_cycle})."
    )

    return AllocationRecommendation(
        recovery_id=recovery_id,
        country_office=cpd.country_office,
        recovery_amount=recovery_amount,
        currency=cpd.currency,
        pillar_allocations=pillar_allocations,
        output_allocations=output_allocations,
        methodology="gap_weighted",
        rationale=rationale,
    )


# ═══════════════════════════════════════════════════════════
# SECTION 4: CPD PROFILE LOADING
# ═══════════════════════════════════════════════════════════


def _parse_cpd_profile(data: dict) -> CountryProgrammeProfile:
    """Parse a CPD profile from a JSON-loaded dict."""
    pillars = []
    for p in data.get("pillars", []):
        pillars.append(CPDPillarTarget(
            pillar=p["pillar"],
            sdg_targets=p.get("sdg_targets", []),
            target_percentage=p.get("target_percentage", 0.0),
            target_amount=p.get("target_amount", 0.0),
            actual_spend=p.get("actual_spend", 0.0),
            actual_percentage=p.get("actual_percentage", 0.0),
        ))

    outputs = []
    for o in data.get("outputs", []):
        outputs.append(CPDOutputTarget(
            output_id=o["output_id"],
            output_description=o.get("output_description", ""),
            pillar=o["pillar"],
            target_amount=o.get("target_amount", 0.0),
            actual_spend=o.get("actual_spend", 0.0),
            actual_delivery=o.get("actual_delivery"),
            delivery_verdict=o.get("delivery_verdict"),
        ))

    return CountryProgrammeProfile(
        country_office=data["country_office"],
        country_code=data["country_code"],
        programme_cycle=data.get("programme_cycle", ""),
        total_programme_budget=data.get("total_programme_budget", 0.0),
        currency=data.get("currency", "USD"),
        pillars=pillars,
        outputs=outputs,
        last_updated=data.get("last_updated"),
        source_document=data.get("source_document"),
    )


def load_cpd_profile(
    country_code: str,
    cpd_dir: Optional[str] = None,
) -> Optional[CountryProgrammeProfile]:
    """
    Load a CPD profile from a JSON file.

    Looks for data/cpd_profiles/{country_code}.json relative to the
    project root, or in cpd_dir if specified.

    Args:
        country_code: ISO 3166-1 alpha-2 code (lowercase for filename).
        cpd_dir: Optional directory path. If None, uses default location.

    Returns:
        CountryProgrammeProfile or None if file not found.
    """
    if cpd_dir is None:
        # Default: data/cpd_profiles/ relative to code/ directory
        code_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(code_dir)
        cpd_dir = os.path.join(project_root, "data", "cpd_profiles")

    filename = f"{country_code.lower()}.json"
    filepath = os.path.join(cpd_dir, filename)

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _parse_cpd_profile(data)


def load_cpd_profile_from_dict(data: dict) -> CountryProgrammeProfile:
    """
    Load a CPD profile from an in-memory dict.

    Used by API endpoints when the CPD profile is provided
    in the request body rather than loaded from a file.

    Args:
        data: Dict matching CountryProgrammeProfile schema.

    Returns:
        CountryProgrammeProfile instance.
    """
    return _parse_cpd_profile(data)
