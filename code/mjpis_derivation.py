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

v0.1 note: with only US DOJ cases in the seed corpus, the derivation
produces values identical to the empirical DOJ calibration. When the
corpus expands in later research phases, the same function produces
multi-jurisdiction intersection values automatically.

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import date
from typing import Dict, Set

logger = logging.getLogger(__name__)


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


def derive_mjpis_parameters(corpus: Dict) -> "GlobalParameters":
    """
    Derive a GlobalParameters instance from the prosecuted cases corpus.

    v0.1 derivation is conservative: when only one jurisdiction is
    present in the corpus, the derivation returns values matching that
    jurisdiction's calibration. When multiple jurisdictions are present,
    the derivation computes the intersection (stricter of each pair).

    Args:
        corpus: Corpus dictionary loaded from JSON

    Returns:
        GlobalParameters instance with derived threshold values

    Raises:
        NotImplementedError: If multi-jurisdiction derivation is attempted
            (deferred to sub-task 2.2.6)

    v0.1 Methodology:
        - Jurisdictions: Extract unique jurisdiction codes from cases
        - Dimensional analysis: Count cases in each dimension
        - Evidentiary standard: Determined by jurisdiction composition
        - Statistical thresholds:
            * Single jurisdiction: Inherit that jurisdiction's calibration
            * Multi-jurisdiction: Intersection derivation (deferred to 2.2.6)

    Example:
        >>> corpus = load_corpus(CORPUS_PATH)
        >>> params = derive_mjpis_parameters(corpus)
        >>> params.version
        'mjpis_v0.1'
        >>> params.red_posterior_threshold
        0.72
    """
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

    # mjpis_v0.2 derivation (sub-task 2.3.7 minimum-viable):
    # Real per-dimension derivation for the markup_based dimension. The
    # remaining statistical bars (posterior thresholds, FDR alpha, bootstrap
    # parameters) still inherit US_FEDERAL_V0 — those require cross-
    # jurisdictional recalibration that is out of scope for the minimum-
    # viable increment.
    #
    # Algorithm for markup_floor derivation:
    #   1. Partition corpus by (jurisdiction, dimensional_tag).
    #   2. For each jurisdiction with markup_based cases that have populated
    #      markup_percentage, compute the per-jurisdiction floor as the
    #      minimum markup ratio observed (strictest case that jurisdiction
    #      has prosecuted at).
    #   3. Intersection floor = minimum across per-jurisdiction floors. This
    #      is the strictest bar that ANY mature jurisdiction in the corpus
    #      has prosecuted at — the empirical evidentiary floor below which
    #      no mature legal system treats the case as prosecutable.
    #   4. Record contributing case(s) that set the intersection floor for
    #      provenance.
    #
    # When no jurisdiction has markup_based cases with populated percentages,
    # the derivation falls back to the DynCorp 2005 default (0.75).
    from dataclasses import replace

    # Step 1-2: Partition + per-jurisdiction markup floors
    markup_cases_by_jurisdiction: Dict[str, list] = {}
    for case in corpus["cases"]:
        if "markup_based" not in case.get("dimensional_tags", []):
            continue
        markup_pct = case.get("markup_percentage")
        if markup_pct is None:
            continue
        ratio = float(markup_pct) / 100.0
        j = case["jurisdiction"]
        markup_cases_by_jurisdiction.setdefault(j, []).append(
            {"case_id": case["case_id"], "markup_ratio": ratio}
        )

    per_jurisdiction_floors: Dict[str, float] = {
        j: min(c["markup_ratio"] for c in cases)
        for j, cases in markup_cases_by_jurisdiction.items()
        if cases
    }

    # Step 3: Intersection floor (min across jurisdictions)
    if per_jurisdiction_floors:
        intersection_floor = min(per_jurisdiction_floors.values())
    else:
        # No corpus cases tagged markup_based with populated percentages —
        # fall back to US_FEDERAL_V0 default (DynCorp 2005 empirical floor).
        intersection_floor = US_FEDERAL_V0.markup_floor_ratio

    # Step 4: Identify contributing case(s) that set the intersection floor
    contributing_cases = []
    _EPS = 1e-9
    for j, cases in markup_cases_by_jurisdiction.items():
        for c in cases:
            if abs(c["markup_ratio"] - intersection_floor) < _EPS:
                contributing_cases.append({
                    "case_id": c["case_id"],
                    "jurisdiction": j,
                    "markup_ratio": c["markup_ratio"],
                })

    # Provenance trail for the derived markup_floor_ratio
    derivation_metadata = {
        "methodology_version": "mjpis_v0.2",
        "markup_floor_derivation": {
            "per_jurisdiction": per_jurisdiction_floors,
            "intersection_floor": intersection_floor,
            "contributing_cases": contributing_cases,
        },
        "corpus_version": corpus_version,
        "jurisdictions_considered": sorted(jurisdictions),
    }

    # Log the derivation outcome
    non_doj_case_count = sum(
        1 for c in corpus["cases"] if c["jurisdiction"] != "US_DOJ"
    )
    logger.info(
        f"MJPIS v0.2 derivation: markup_floor_ratio={intersection_floor:.4f} "
        f"(intersection across {len(per_jurisdiction_floors)} jurisdiction(s) "
        f"with markup-based cases); "
        f"{non_doj_case_count} non-DOJ case(s) present in corpus "
        f"(non-markup dimensions await further sub-task 2.3.7 consumers)"
    )

    # Construct derived GlobalParameters via dataclasses.replace so ALL
    # statistical fields from US_FEDERAL_V0 are preserved by default, and
    # only the MJPIS-specific fields are overridden. This is the correct
    # pattern for a partial derivation: the minimum-viable increment only
    # derives markup_floor_ratio empirically; everything else inherits
    # until its own consumer rule and derivation land.
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
            f"mjpis_v0.2 derives markup_floor_ratio empirically via "
            f"cross-jurisdictional intersection; remaining statistical bars "
            f"inherit US_FEDERAL_V0 until their own consumers and derivations land."
        ),
        source_citation=(
            f"research/corpus/prosecuted_cases_global_v{corpus_version}.json"
        ),
        derivation_date=str(date.today()),
        evidentiary_standard=evidentiary_standard,
        markup_floor_ratio=intersection_floor,
        derivation_metadata=derivation_metadata,
        notes=(
            f"Derived from {total_cases} cases across {len(jurisdictions)} "
            f"jurisdiction(s) via mjpis_derivation.derive_mjpis_parameters(). "
            f"mjpis_v0.2 (sub-task 2.3.7 minimum-viable): real per-dimension "
            f"derivation for markup_floor_ratio via intersection across "
            f"{len(per_jurisdiction_floors)} jurisdiction(s) with markup-based "
            f"cases. Contributing case(s): "
            f"{', '.join(c['case_id'] for c in contributing_cases) or '(none)'}. "
            f"Remaining statistical bars (posterior thresholds, FDR, bootstrap) "
            f"inherit US_FEDERAL_V0 pending their own derivation layers."
        ),
    )


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
        NotImplementedError: If multi-jurisdiction derivation is attempted

    Example:
        >>> from mjpis_derivation import get_derived_mjpis
        >>> mjpis_params = get_derived_mjpis()
        >>> mjpis_params.version
        'mjpis_v0.1'
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
        print(f"  RED threshold: posterior ≥ {mjpis.red_posterior_threshold:.0%}")
        print(f"  YELLOW threshold: posterior ≥ {mjpis.yellow_posterior_threshold:.0%}")
        print(f"  FDR alpha: {mjpis.fdr_alpha}")
        print(f"  Bootstrap resamples: {mjpis.bootstrap_n_resamples:,}")

        print("\n" + "=" * 72)
        print("Derivation successful")

    except FileNotFoundError as e:
        print(f"\n✗ Corpus file not found: {e}")
    except NotImplementedError as e:
        print(f"\n⚠ Derivation not yet implemented: {e}")
    except Exception as e:
        print(f"\n✗ Derivation failed: {e}")
        import traceback
        traceback.print_exc()
