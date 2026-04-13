"""
MJPIS Derivation Function
=========================

Reads the multi-jurisdiction prosecuted cases corpus and produces a
GlobalParameters instance for the Multi-Jurisdiction Procurement
Integrity Standard (MJPIS).

The derivation methodology:

1. DIMENSIONAL ANALYSIS — cases are categorized into three dimensions
   based on the prosecution pattern they represent:
     - markup_based: cases anchored on documented price inflation above
       fair market value (primary US DOJ pattern, DynCorp 2005 at 75%
       markup as the empirical floor)
     - bribery_channel: cases anchored on documented payments through
       bribery intermediaries or commission structures (primary UK SFO
       and French PNF pattern)
     - administrative_sanctionable: cases anchored on "more likely
       than not" evidentiary standard for administrative debarment
       (primary World Bank INT pattern)

2. STATISTICAL DERIVATION — for each dimension present in the corpus,
   compute dimension-specific threshold values. If multiple dimensions
   are present, compute the intersection (stricter of each pair) rather
   than the average.

3. EVIDENTIARY STANDARD — set to "intersection_of_mature_legal_systems"
   when the corpus contains cases from more than one jurisdiction,
   otherwise inherit the dominant jurisdiction's standard.

v0.2 derivation:

  markup_floor_ratio is derived via the intersection_v1 methodology:
    - Group corpus cases by jurisdiction.
    - For each jurisdiction, filter to cases where markup_percentage is
      documented (non-null) AND dimensional_tags contains "markup_based".
    - For each jurisdiction with at least one qualifying case, compute
      the jurisdiction's anchor as the MINIMUM markup_percentage across
      that jurisdiction's qualifying cases.
    - The MJPIS markup_floor_ratio is the MINIMUM across per-jurisdiction
      anchors — the strictest jurisdiction's strictest case.
    - If only one jurisdiction has qualifying cases, the MJPIS value
      equals that jurisdiction's anchor (degrades cleanly to single-
      jurisdiction calibration when corpus is thin).
    - The function returns both the computed value AND a derivation log
      showing which jurisdictions contributed, which case was each
      jurisdiction's anchor, and what each anchor value was.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 2.0.0
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# Dataclasses for structured derivation results
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class JurisdictionAnchor:
    """One jurisdiction's anchor case for a per-parameter derivation.

    Used by both markup_floor and bribery_channel derivations.
    The `markup_percentage` field carries the anchor ratio regardless
    of which parameter it anchors (markup ratio or bribery-channel ratio).
    """

    jurisdiction: str
    case_id: str
    markup_percentage: float  # ratio (e.g. 0.501, 0.0058)
    qualifying_case_count: int


@dataclass(frozen=True)
class MarkupFloorDerivation:
    """Result of the intersection_v1 markup floor derivation."""

    value: float  # the MJPIS markup_floor_ratio
    contributing_jurisdictions: List[str]
    per_jurisdiction_anchors: Dict[str, JurisdictionAnchor]
    methodology_version: str = "intersection_v1"


@dataclass(frozen=True)
class BriberyChannelDerivation:
    """Result of the intersection_v1 bribery-channel ratio derivation."""

    value: float  # the MJPIS bribery_channel_ratio
    contributing_jurisdictions: List[str]
    per_jurisdiction_anchors: Dict[str, JurisdictionAnchor]
    methodology_version: str = "intersection_v1"


@dataclass(frozen=True)
class DerivationAuditTrail:
    """Full per-parameter derivation log for institutional audit."""

    markup_floor: Optional[MarkupFloorDerivation] = None
    bribery_channel: Optional[BriberyChannelDerivation] = None
    # Future sub-task C will add:
    # administrative_sanctionable: Optional[AdminSanctionableDerivation] = None


class InsufficientCorpusError(Exception):
    """Raised when the corpus lacks qualifying cases for a derivation."""


# ═══════════════════════════════════════════════════════════
# Module-level state for the audit trail
# ═══════════════════════════════════════════════════════════

_audit_trail: Optional[DerivationAuditTrail] = None


# ═══════════════════════════════════════════════════════════
# Corpus loading
# ═══════════════════════════════════════════════════════════


def load_corpus(corpus_path: Path) -> Dict:
    """
    Load the corpus JSON from disk.

    Args:
        corpus_path: Path to the corpus JSON file

    Returns:
        Corpus dictionary with metadata and cases

    Raises:
        FileNotFoundError: If corpus file doesn't exist
        json.JSONDecodeError: If corpus file is malformed
    """
    with open(corpus_path, 'r') as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════════
# Per-parameter derivation functions
# ═══════════════════════════════════════════════════════════


def derive_markup_floor_ratio(cases: List[Dict]) -> MarkupFloorDerivation:
    """
    Derive the MJPIS markup_floor_ratio via intersection_v1 methodology.

    Groups corpus cases by jurisdiction, filters to qualifying cases
    (markup_percentage documented + markup_based dimensional tag),
    computes per-jurisdiction anchors (minimum markup in each
    jurisdiction), and returns the intersection (minimum across
    jurisdictions).

    Args:
        cases: List of corpus case dicts (the "cases" array from the
               corpus JSON, not the full corpus dict).

    Returns:
        MarkupFloorDerivation with value, contributing jurisdictions,
        per-jurisdiction anchors, and methodology version.

    Raises:
        InsufficientCorpusError: If no jurisdiction has qualifying
            markup_based cases with documented markup_percentage, or
            if the cases list is empty.
    """
    if not cases:
        raise InsufficientCorpusError(
            "Cannot derive markup_floor_ratio from an empty corpus. "
            "At least one case with markup_based tag and documented "
            "markup_percentage is required."
        )

    # Group qualifying cases by jurisdiction
    markup_cases_by_jurisdiction: Dict[str, List[Dict]] = {}
    for case in cases:
        if "markup_based" not in case.get("dimensional_tags", []):
            continue
        markup_pct = case.get("markup_percentage")
        if markup_pct is None:
            continue
        ratio = float(markup_pct) / 100.0
        j = case["jurisdiction"]
        markup_cases_by_jurisdiction.setdefault(j, []).append({
            "case_id": case["case_id"],
            "markup_ratio": ratio,
        })

    if not markup_cases_by_jurisdiction:
        raise InsufficientCorpusError(
            "No jurisdiction in the corpus has qualifying markup_based "
            "cases with documented markup_percentage. Cannot derive "
            "markup_floor_ratio."
        )

    # Per-jurisdiction anchors: minimum markup in each jurisdiction
    per_jurisdiction_anchors: Dict[str, JurisdictionAnchor] = {}
    for j, j_cases in markup_cases_by_jurisdiction.items():
        min_case = min(j_cases, key=lambda c: c["markup_ratio"])
        per_jurisdiction_anchors[j] = JurisdictionAnchor(
            jurisdiction=j,
            case_id=min_case["case_id"],
            markup_percentage=min_case["markup_ratio"],
            qualifying_case_count=len(j_cases),
        )

    # Intersection: minimum across per-jurisdiction anchors
    intersection_value = min(
        a.markup_percentage for a in per_jurisdiction_anchors.values()
    )
    contributing_jurisdictions = sorted(per_jurisdiction_anchors.keys())

    return MarkupFloorDerivation(
        value=intersection_value,
        contributing_jurisdictions=contributing_jurisdictions,
        per_jurisdiction_anchors=per_jurisdiction_anchors,
        methodology_version="intersection_v1",
    )


def derive_bribery_channel_ratio(cases: List[Dict]) -> BriberyChannelDerivation:
    """
    Derive the MJPIS bribery_channel_ratio via intersection_v1 methodology.

    Groups corpus cases by jurisdiction, filters to qualifying cases
    (bribery_channel dimensional tag + bribery_channel_ratio documented),
    computes per-jurisdiction anchors (minimum ratio in each jurisdiction),
    and returns the intersection (minimum across jurisdictions).

    Args:
        cases: List of corpus case dicts.

    Returns:
        BriberyChannelDerivation with value, contributing jurisdictions,
        per-jurisdiction anchors, and methodology version.

    Raises:
        InsufficientCorpusError: If no jurisdiction has qualifying cases.
    """
    if not cases:
        raise InsufficientCorpusError(
            "Cannot derive bribery_channel_ratio from an empty corpus."
        )

    # Group qualifying cases by jurisdiction
    bc_cases_by_jurisdiction: Dict[str, List[Dict]] = {}
    for case in cases:
        if "bribery_channel" not in case.get("dimensional_tags", []):
            continue
        ratio = case.get("bribery_channel_ratio")
        if ratio is None:
            continue
        j = case["jurisdiction"]
        bc_cases_by_jurisdiction.setdefault(j, []).append({
            "case_id": case["case_id"],
            "ratio": float(ratio),
        })

    if not bc_cases_by_jurisdiction:
        raise InsufficientCorpusError(
            "No jurisdiction in the corpus has qualifying bribery_channel "
            "cases with documented bribery_channel_ratio."
        )

    # Per-jurisdiction anchors: minimum ratio in each jurisdiction
    per_jurisdiction_anchors: Dict[str, JurisdictionAnchor] = {}
    for j, j_cases in bc_cases_by_jurisdiction.items():
        min_case = min(j_cases, key=lambda c: c["ratio"])
        per_jurisdiction_anchors[j] = JurisdictionAnchor(
            jurisdiction=j,
            case_id=min_case["case_id"],
            markup_percentage=min_case["ratio"],
            qualifying_case_count=len(j_cases),
        )

    # Intersection: minimum across per-jurisdiction anchors
    intersection_value = min(
        a.markup_percentage for a in per_jurisdiction_anchors.values()
    )
    contributing_jurisdictions = sorted(per_jurisdiction_anchors.keys())

    return BriberyChannelDerivation(
        value=intersection_value,
        contributing_jurisdictions=contributing_jurisdictions,
        per_jurisdiction_anchors=per_jurisdiction_anchors,
        methodology_version="intersection_v1",
    )


# ═══════════════════════════════════════════════════════════
# Main derivation orchestrator
# ═══════════════════════════════════════════════════════════


def derive_mjpis_parameters(corpus: Dict) -> "GlobalParameters":
    """
    Derive a GlobalParameters instance from the prosecuted cases corpus.

    Calls per-parameter derivation functions (currently markup_floor_ratio
    via intersection_v1) and assembles the result into a GlobalParameters
    instance. Parameters without their own derivation function yet inherit
    from US_FEDERAL_V0.

    Args:
        corpus: Corpus dictionary loaded from JSON

    Returns:
        GlobalParameters instance with derived threshold values
    """
    global _audit_trail

    # Late import to avoid circular dependency with global_parameters.py
    from global_parameters import GlobalParameters, US_FEDERAL_V0

    # Extract jurisdiction metadata
    jurisdictions: Set[str] = set(case["jurisdiction"] for case in corpus["cases"])
    total_cases = len(corpus["cases"])
    corpus_version = corpus["corpus_version"]

    # Dimensional analysis
    dimensional_counts = {
        "markup_based": 0,
        "bribery_channel": 0,
        "administrative_sanctionable": 0,
    }
    for case in corpus["cases"]:
        for tag in case.get("dimensional_tags", []):
            if tag in dimensional_counts:
                dimensional_counts[tag] += 1

    # Determine evidentiary standard
    if len(jurisdictions) > 1:
        evidentiary_standard = "intersection_of_mature_legal_systems"
    elif "US_DOJ" in jurisdictions:
        evidentiary_standard = "beyond_reasonable_doubt"
    elif "WB_INT" in jurisdictions:
        evidentiary_standard = "more_likely_than_not"
    elif "UK_SFO" in jurisdictions:
        evidentiary_standard = "beyond_reasonable_doubt"
    elif "FR_PNF" in jurisdictions:
        evidentiary_standard = "beyond_reasonable_doubt"
    else:
        evidentiary_standard = "beyond_reasonable_doubt"

    # ── Markup floor derivation (intersection_v1) ──────────────
    #
    # Call the standalone derivation function. If it raises
    # InsufficientCorpusError (no qualifying markup_based cases),
    # fall back to the US_FEDERAL_V0 default (DynCorp 2005
    # empirical floor at 0.75).
    markup_floor_derivation: Optional[MarkupFloorDerivation] = None
    try:
        markup_floor_derivation = derive_markup_floor_ratio(corpus["cases"])
        intersection_floor = markup_floor_derivation.value
    except InsufficientCorpusError:
        intersection_floor = US_FEDERAL_V0.markup_floor_ratio

    # ── Bribery-channel ratio derivation (intersection_v1) ────
    #
    # Same methodology as markup floor but over bribery_channel cases.
    # If no qualifying cases exist, the parameter stays None (no rule
    # consumes it yet, so there is no fallback needed).
    bribery_channel_derivation: Optional[BriberyChannelDerivation] = None
    bribery_channel_value: Optional[float] = None
    try:
        bribery_channel_derivation = derive_bribery_channel_ratio(corpus["cases"])
        bribery_channel_value = bribery_channel_derivation.value
    except InsufficientCorpusError:
        pass  # stays None

    # Store the audit trail at module level
    _audit_trail = DerivationAuditTrail(
        markup_floor=markup_floor_derivation,
        bribery_channel=bribery_channel_derivation,
    )

    # ── Provenance trail for derivation_metadata on GlobalParameters ──
    #
    # Backward-compatible dict format consumed by existing tests and
    # FIN-001's evidence string builder.
    if markup_floor_derivation is not None:
        per_jurisdiction_floors = {
            j: anchor.markup_percentage
            for j, anchor in markup_floor_derivation.per_jurisdiction_anchors.items()
        }
        contributing_cases = [
            {
                "case_id": anchor.case_id,
                "jurisdiction": anchor.jurisdiction,
                "markup_ratio": anchor.markup_percentage,
            }
            for anchor in markup_floor_derivation.per_jurisdiction_anchors.values()
        ]
    else:
        per_jurisdiction_floors = {}
        contributing_cases = []

    # Bribery-channel provenance
    if bribery_channel_derivation is not None:
        bc_per_jurisdiction = {
            j: anchor.markup_percentage
            for j, anchor in bribery_channel_derivation.per_jurisdiction_anchors.items()
        }
        bc_contributing_cases = [
            {
                "case_id": anchor.case_id,
                "jurisdiction": anchor.jurisdiction,
                "bribery_channel_ratio": anchor.markup_percentage,
            }
            for anchor in bribery_channel_derivation.per_jurisdiction_anchors.values()
        ]
    else:
        bc_per_jurisdiction = {}
        bc_contributing_cases = []

    derivation_metadata = {
        "methodology_version": "mjpis_v0.2",
        "markup_floor_derivation": {
            "methodology": "intersection_v1",
            "per_jurisdiction": per_jurisdiction_floors,
            "intersection_floor": intersection_floor,
            "contributing_cases": contributing_cases,
        },
        "bribery_channel_derivation": {
            "methodology": "intersection_v1",
            "per_jurisdiction": bc_per_jurisdiction,
            "intersection_floor": bribery_channel_value,
            "contributing_cases": bc_contributing_cases,
        },
        "corpus_version": corpus_version,
        "jurisdictions_considered": sorted(jurisdictions),
    }

    # Log the derivation outcome
    non_doj_case_count = sum(
        1 for c in corpus["cases"] if c["jurisdiction"] != "US_DOJ"
    )
    n_contributing = len(per_jurisdiction_floors)
    n_bc_contributing = len(bc_per_jurisdiction)
    bc_value_str = f"{bribery_channel_value:.4f}" if bribery_channel_value is not None else "None"
    logger.info(
        f"MJPIS v0.2 derivation: markup_floor_ratio={intersection_floor:.4f} "
        f"(intersection_v1 across {n_contributing} jurisdiction(s) "
        f"with markup-based cases); "
        f"bribery_channel_ratio={bc_value_str} "
        f"(intersection_v1 across {n_bc_contributing} jurisdiction(s) "
        f"with bribery-channel cases); "
        f"{non_doj_case_count} non-DOJ case(s) present in corpus"
    )

    # Construct derived GlobalParameters via dataclasses.replace so ALL
    # statistical fields from US_FEDERAL_V0 are preserved by default, and
    # only the MJPIS-specific fields are overridden.
    return replace(
        US_FEDERAL_V0,
        version=f"mjpis_v{corpus_version}",
        description=(
            f"Multi-Jurisdiction Procurement Integrity Standard, "
            f"derived from corpus v{corpus_version} containing "
            f"{total_cases} cases from {len(jurisdictions)} jurisdiction(s). "
            f"Dimensional coverage: "
            f"markup_based={dimensional_counts['markup_based']}, "
            f"bribery_channel={dimensional_counts['bribery_channel']}, "
            f"administrative_sanctionable={dimensional_counts['administrative_sanctionable']}. "
            f"mjpis_v0.2 derives markup_floor_ratio and bribery_channel_ratio "
            f"empirically via cross-jurisdictional intersection (intersection_v1); "
            f"remaining statistical bars inherit US_FEDERAL_V0 until their own "
            f"consumers and derivations land."
        ),
        source_citation=(
            f"research/corpus/prosecuted_cases_global_v{corpus_version}.json"
        ),
        derivation_date=str(date.today()),
        evidentiary_standard=evidentiary_standard,
        markup_floor_ratio=intersection_floor,
        bribery_channel_ratio=bribery_channel_value,
        derivation_metadata=derivation_metadata,
        notes=(
            f"Derived from {total_cases} cases across {len(jurisdictions)} "
            f"jurisdiction(s) via mjpis_derivation.derive_mjpis_parameters(). "
            f"markup_floor_ratio derived via intersection_v1 across "
            f"{n_contributing} jurisdiction(s) with markup-based "
            f"cases. Contributing case(s): "
            f"{', '.join(c['case_id'] for c in contributing_cases) or '(none)'}. "
            f"bribery_channel_ratio derived via intersection_v1 across "
            f"{n_bc_contributing} jurisdiction(s) with bribery-channel "
            f"cases. Contributing case(s): "
            f"{', '.join(c['case_id'] for c in bc_contributing_cases) or '(none)'}. "
            f"Remaining statistical bars (posterior thresholds, FDR, bootstrap) "
            f"inherit US_FEDERAL_V0 pending their own derivation layers."
        ),
    )


# ═══════════════════════════════════════════════════════════
# Audit trail accessor
# ═══════════════════════════════════════════════════════════


def get_derivation_audit_trail() -> DerivationAuditTrail:
    """
    Return the full per-parameter derivation log.

    The audit trail is populated when derive_mjpis_parameters() runs
    (typically at import time via global_parameters.py). Each parameter
    that has a derivation function gets a typed entry in the trail.

    Returns:
        DerivationAuditTrail with markup_floor as the first populated
        entry. Future sub-tasks will add bribery_channel and
        administrative_sanctionable entries.
    """
    if _audit_trail is None:
        return DerivationAuditTrail()
    return _audit_trail


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════


# Path to the seed corpus
# Use __file__ to locate the corpus relative to this module
CORPUS_PATH = Path(__file__).parent.parent / "research" / "corpus" / "prosecuted_cases_global_v0.1.json"


def get_derived_mjpis() -> "GlobalParameters":
    """
    Load the corpus and derive MJPIS parameters in one call.

    This is the public API for obtaining the derived MJPIS GlobalParameters.
    Called by global_parameters.py at import time to populate MJPIS_DRAFT_V0.

    Returns:
        GlobalParameters instance derived from the current corpus

    Raises:
        FileNotFoundError: If corpus file doesn't exist
        json.JSONDecodeError: If corpus file is malformed

    Example:
        >>> from mjpis_derivation import get_derived_mjpis
        >>> mjpis_params = get_derived_mjpis()
        >>> mjpis_params.markup_floor_ratio
        0.501
    """
    corpus = load_corpus(CORPUS_PATH)
    return derive_mjpis_parameters(corpus)


# ═══════════════════════════════════════════════════════════
# CLI: Print derivation summary
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 72)
    print("MJPIS Derivation Function")
    print("=" * 72)

    try:
        corpus = load_corpus(CORPUS_PATH)
        print(f"\nCorpus loaded: {CORPUS_PATH}")
        print(f"  Version: {corpus['corpus_version']}")
        print(f"  Total cases: {corpus['total_cases']}")
        print(f"  Jurisdictions: {', '.join(corpus['jurisdictions_included'])}")

        print("\nDeriving MJPIS parameters...")
        mjpis = derive_mjpis_parameters(corpus)

        print(f"\nDerived GlobalParameters:")
        print(f"  Version: {mjpis.version}")
        print(f"  Evidentiary standard: {mjpis.evidentiary_standard}")
        print(f"  Markup floor ratio: {mjpis.markup_floor_ratio}")
        print(f"  RED threshold: posterior >= {mjpis.red_posterior_threshold:.0%}")
        print(f"  YELLOW threshold: posterior >= {mjpis.yellow_posterior_threshold:.0%}")
        print(f"  FDR alpha: {mjpis.fdr_alpha}")
        print(f"  Bootstrap resamples: {mjpis.bootstrap_n_resamples:,}")

        trail = get_derivation_audit_trail()
        if trail.markup_floor is not None:
            mf = trail.markup_floor
            print(f"\nMarkup floor derivation ({mf.methodology_version}):")
            print(f"  Value: {mf.value}")
            print(f"  Contributing jurisdictions: {mf.contributing_jurisdictions}")
            for j, anchor in mf.per_jurisdiction_anchors.items():
                print(f"    {j}: {anchor.case_id} at {anchor.markup_percentage} "
                      f"({anchor.qualifying_case_count} qualifying case(s))")

        if trail.bribery_channel is not None:
            bc = trail.bribery_channel
            print(f"\nBribery-channel ratio derivation ({bc.methodology_version}):")
            print(f"  Value: {bc.value}")
            print(f"  Contributing jurisdictions: {bc.contributing_jurisdictions}")
            for j, anchor in bc.per_jurisdiction_anchors.items():
                print(f"    {j}: {anchor.case_id} at {anchor.markup_percentage} "
                      f"({anchor.qualifying_case_count} qualifying case(s))")

        print("\n" + "=" * 72)
        print("Derivation successful")

    except FileNotFoundError as e:
        print(f"\n  Corpus file not found: {e}")
    except InsufficientCorpusError as e:
        print(f"\n  Insufficient corpus: {e}")
    except Exception as e:
        print(f"\n  Derivation failed: {e}")
        import traceback
        traceback.print_exc()
