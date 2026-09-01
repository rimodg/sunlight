"""
Reprogramming feasibility assessor. Reads delegation thresholds authored
in the jurisdiction profile and returns whether a proposed redirection
falls within country-office delegated authority or requires HQ approval.

Constitutional rules of this module, enforced by tests:
1. Never modifies allocation. Feasibility is reported, never used to
   filter, downrank, or re-order redirections.
2. Deterministic and total: same inputs plus same profile yield the same
   assessment; every degenerate input yields a stated reason, never a
   raise.
3. UNASSESSABLE is not "not feasible". A profile lacking delegation data
   returns UNASSESSABLE with the specific missing field named. Absence
   of data is never rendered as "requires HQ".
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class FeasibilityVerdict(Enum):
    DELEGATED_AUTHORITY = "delegated_authority"
    HQ_APPROVAL_REQUIRED = "hq_approval_required"
    UNASSESSABLE = "unassessable"


@dataclass
class FeasibilityAssessment:
    verdict: FeasibilityVerdict
    rationale: str
    threshold_applied_usd: Optional[float] = None
    process_months_min: Optional[int] = None
    process_months_max: Optional[int] = None
    profile_source: Optional[str] = None


def _get_feasibility_param(profile: Any, name: str, default: Any = None) -> Any:
    """Same conservative pattern as _get_absence_param and
    _get_evidence_param: a profile lacking the field returns default,
    never raises."""
    return getattr(profile, name, default)


def assess_feasibility(redirection, profile, source_recovery_pillar: Optional[str] = None) -> FeasibilityAssessment:
    """Pure function: reads the profile's delegation thresholds and the
    redirection's amount and pillar, returns a verdict with rationale."""
    threshold = _get_feasibility_param(profile, 'delegated_authority_threshold_usd')
    pillar_delegated = _get_feasibility_param(profile, 'pillar_reallocation_delegated', False)
    cross_pillar_hq = _get_feasibility_param(profile, 'cross_pillar_requires_hq', True)
    months_min = _get_feasibility_param(profile, 'hq_approval_process_months_min')
    months_max = _get_feasibility_param(profile, 'hq_approval_process_months_max')
    profile_code = getattr(profile, 'jurisdiction_code', None) or getattr(profile, 'country_code', None)

    if threshold is None:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.UNASSESSABLE,
            rationale=("profile does not state delegated_authority_threshold_usd; "
                       "feasibility cannot be assessed without an authored threshold"),
            profile_source=profile_code,
        )

    amount = redirection.target_contract_value
    currency = redirection.currency
    is_cross_pillar = (source_recovery_pillar is not None
                       and redirection.target_pillar != source_recovery_pillar)

    if currency != 'USD':
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.UNASSESSABLE,
            rationale=(f"redirection currency is {currency}; delegation threshold is "
                       f"authored in USD, no FX conversion is performed at this layer "
                       f"to keep the assessment deterministic and free of stale rates"),
            threshold_applied_usd=threshold,
            profile_source=profile_code,
        )

    if is_cross_pillar and cross_pillar_hq:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.HQ_APPROVAL_REQUIRED,
            rationale=(f"redirection crosses pillars (source {source_recovery_pillar} -> "
                       f"target {redirection.target_pillar}); profile states cross-pillar "
                       f"reallocation requires HQ approval"),
            threshold_applied_usd=threshold,
            process_months_min=months_min,
            process_months_max=months_max,
            profile_source=profile_code,
        )

    if amount > threshold:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.HQ_APPROVAL_REQUIRED,
            rationale=(f"target contract value {amount:,.0f} USD exceeds delegated "
                       f"authority threshold {threshold:,.0f} USD"),
            threshold_applied_usd=threshold,
            process_months_min=months_min,
            process_months_max=months_max,
            profile_source=profile_code,
        )

    if not pillar_delegated and not is_cross_pillar:
        return FeasibilityAssessment(
            verdict=FeasibilityVerdict.HQ_APPROVAL_REQUIRED,
            rationale=("profile states pillar reallocation is not delegated to the "
                       "country office even within the target pillar"),
            threshold_applied_usd=threshold,
            process_months_min=months_min,
            process_months_max=months_max,
            profile_source=profile_code,
        )

    return FeasibilityAssessment(
        verdict=FeasibilityVerdict.DELEGATED_AUTHORITY,
        rationale=(f"target contract value {amount:,.0f} USD within delegated "
                   f"threshold {threshold:,.0f} USD, and reallocation is within "
                   f"delegated pillar authority"),
        threshold_applied_usd=threshold,
        profile_source=profile_code,
    )
