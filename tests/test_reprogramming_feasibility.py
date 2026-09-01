"""
Phase 4 tests: reprogramming feasibility.

Discipline mirrors the Absence Ledger tests: determinism byte-identical,
totality (no raises on degenerate input), None-safe defaults, verdict
values stable, and the constitutional rule that feasibility never
modifies allocation is asserted structurally.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

from reprogramming_feasibility import (
    FeasibilityVerdict,
    FeasibilityAssessment,
    _get_feasibility_param,
    assess_feasibility,
)
from redirection import RedirectionRecord


@dataclass
class _StubProfile:
    """A minimal profile stand-in so tests are isolated from real profiles."""
    jurisdiction_code: str = "test_profile"
    country_code: str = "TL"
    delegated_authority_threshold_usd: Optional[float] = None
    pillar_reallocation_delegated: bool = False
    cross_pillar_requires_hq: bool = True
    hq_approval_process_months_min: Optional[int] = None
    hq_approval_process_months_max: Optional[int] = None


def _profile_undp_like():
    return _StubProfile(
        jurisdiction_code="undp_like",
        country_code="XX",
        delegated_authority_threshold_usd=250_000.0,
        pillar_reallocation_delegated=True,
        cross_pillar_requires_hq=True,
        hq_approval_process_months_min=12,
        hq_approval_process_months_max=18,
    )


def _redir(amount=100_000.0, pillar="health", currency="USD"):
    return RedirectionRecord(
        redirection_id="R-1", recovery_id="rec-1",
        target_sdg="SDG 3", target_pillar=pillar,
        target_contract_id="C-1", target_contract_title="Clinic supplies",
        target_contract_value=amount, currency=currency,
        allocation_source="gap_weighted",
    )


# ── Determinism and totality ────────────────────────────────────────

def test_determinism_byte_identical():
    a = assess_feasibility(_redir(), _profile_undp_like(), source_recovery_pillar="health")
    b = assess_feasibility(_redir(), _profile_undp_like(), source_recovery_pillar="health")
    assert asdict(a) == asdict(b)


def test_no_wall_clock():
    src = open('code/reprogramming_feasibility.py').read()
    assert 'datetime.now' not in src
    assert 'utcnow' not in src
    assert '.today(' not in src


def test_get_feasibility_param_present_and_absent():
    p = _profile_undp_like()
    assert _get_feasibility_param(p, 'delegated_authority_threshold_usd') == 250_000.0
    assert _get_feasibility_param(p, 'nonexistent') is None
    assert _get_feasibility_param(p, 'nonexistent', 'fb') == 'fb'


# ── Unassessable branches ────────────────────────────────────────

def test_unassessable_when_profile_lacks_threshold():
    p = _StubProfile()  # no threshold authored
    a = assess_feasibility(_redir(), p, source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.UNASSESSABLE
    assert 'does not state delegated_authority_threshold_usd' in a.rationale
    assert a.threshold_applied_usd is None


def test_unassessable_for_non_usd_currency():
    a = assess_feasibility(_redir(currency="EUR"), _profile_undp_like(),
                           source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.UNASSESSABLE
    assert 'EUR' in a.rationale
    assert 'deterministic' in a.rationale


# ── Delegated authority (small, in-pillar, in-threshold) ────────

def test_delegated_authority_small_in_pillar():
    a = assess_feasibility(_redir(amount=100_000.0),
                           _profile_undp_like(),
                           source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.DELEGATED_AUTHORITY
    assert a.threshold_applied_usd == 250_000.0
    assert 'within delegated' in a.rationale


# ── HQ approval branches ────────────────────────────────────────

def test_hq_required_when_over_threshold():
    a = assess_feasibility(_redir(amount=500_000.0),
                           _profile_undp_like(),
                           source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.HQ_APPROVAL_REQUIRED
    assert '500,000 USD exceeds' in a.rationale
    assert a.process_months_min == 12 and a.process_months_max == 18


def test_hq_required_when_cross_pillar():
    a = assess_feasibility(_redir(amount=50_000.0, pillar="education"),
                           _profile_undp_like(),
                           source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.HQ_APPROVAL_REQUIRED
    assert 'crosses pillars' in a.rationale
    assert 'health' in a.rationale and 'education' in a.rationale


def test_hq_required_when_pillar_not_delegated():
    p = _profile_undp_like()
    p.pillar_reallocation_delegated = False
    a = assess_feasibility(_redir(amount=100_000.0), p, source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.HQ_APPROVAL_REQUIRED
    assert 'not delegated' in a.rationale


def test_boundary_at_threshold_is_delegated():
    """Value exactly at the threshold is delegated, not HQ. Strict > only."""
    a = assess_feasibility(_redir(amount=250_000.0),
                           _profile_undp_like(),
                           source_recovery_pillar="health")
    assert a.verdict == FeasibilityVerdict.DELEGATED_AUTHORITY


# ── Constitutional guarantee: feasibility never modifies allocation ─

def test_assessment_never_modifies_redirection():
    """The assessor reads the redirection; it must not mutate it. This
    encodes the reviewer's warning about operational-convenience-over-
    truthfulness: feasibility is metadata, not an optimizer input."""
    r = _redir(amount=500_000.0)
    before = asdict(r)
    assess_feasibility(r, _profile_undp_like(), source_recovery_pillar="health")
    after = asdict(r)
    assert before == after


def test_redirection_record_defaults_none_for_new_fields():
    """The five feasibility fields default to None so any pre-existing
    construction of RedirectionRecord in tests or production code
    continues to work unchanged."""
    r = _redir()
    assert r.feasibility_verdict is None
    assert r.feasibility_rationale is None
    assert r.feasibility_threshold_usd is None
    assert r.feasibility_months_min is None
    assert r.feasibility_months_max is None
