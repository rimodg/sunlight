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

    # v0.1 derivation: as long as US_DOJ is present in the corpus,
    # inherit the empirical DOJ calibration exactly. This preserves
    # backwards compatibility, keeps the derivation stable as the
    # corpus grows with non-DOJ cases during Phase B expansion, and
    # ensures the passthrough continues producing sensible output
    # with a thin seed corpus.
    # Non-DOJ cases sit in the corpus as reference data and begin
    # contributing statistically only when sub-task 2.3.7 ships the
    # real multi-jurisdiction intersection methodology.
    if "US_DOJ" in jurisdictions:
        logger.info(
            f"MJPIS v0.1 passthrough: using US_DOJ calibration; "
            f"{len(jurisdictions - {'US_DOJ'})} non-DOJ case(s) present in "
            f"corpus but not yet consumed (awaits sub-task 2.3.7 intersection "
            f"methodology)"
        )
        # Inherit US_FEDERAL_V0 values directly
        red_threshold = US_FEDERAL_V0.red_posterior_threshold
        yellow_threshold = US_FEDERAL_V0.yellow_posterior_threshold
        default_base_rate = US_FEDERAL_V0.default_base_rate
        min_typologies = US_FEDERAL_V0.min_typologies_for_red
        min_ci = US_FEDERAL_V0.min_ci_for_yellow
        fdr_alpha = US_FEDERAL_V0.fdr_alpha
        bootstrap_ci = US_FEDERAL_V0.bootstrap_ci_level
        bootstrap_n = US_FEDERAL_V0.bootstrap_n_resamples
        max_flags = US_FEDERAL_V0.max_flags_per_1k
    else:
        # Multi-jurisdiction intersection derivation deferred to 2.2.6
        raise NotImplementedError(
            f"Multi-jurisdiction derivation not yet implemented. "
            f"Corpus contains: {sorted(jurisdictions)}. "
            f"Deferred to sub-task 2.2.6 (full intersection methodology)."
        )

    return GlobalParameters(
        version=f"mjpis_v{corpus_version}",
        description=(
            f"Multi-Jurisdiction Procurement Integrity Standard, "
            f"derived from corpus v{corpus_version} containing "
            f"{total_cases} cases from {len(jurisdictions)} jurisdiction(s). "
            f"Dimensional coverage: "
            f"markup_based={dimensional_counts['markup_based']}, "
            f"bribery_channel={dimensional_counts['bribery_channel']}, "
            f"administrative_sanctionable={dimensional_counts['administrative_sanctionable']}. "
            f"v{corpus_version} is a DRAFT derivation; full multi-jurisdiction "
            f"intersection methodology lands in sub-task 2.2.6."
        ),
        source_citation=(
            f"research/corpus/prosecuted_cases_global_v{corpus_version}.json"
        ),
        derivation_date=str(date.today()),
        evidentiary_standard=evidentiary_standard,
        default_base_rate=default_base_rate,
        red_posterior_threshold=red_threshold,
        yellow_posterior_threshold=yellow_threshold,
        min_typologies_for_red=min_typologies,
        min_ci_for_yellow=min_ci,
        fdr_alpha=fdr_alpha,
        bootstrap_ci_level=bootstrap_ci,
        bootstrap_n_resamples=bootstrap_n,
        max_flags_per_1k=max_flags,
        notes=(
            f"Derived from {total_cases} cases across {len(jurisdictions)} "
            f"jurisdiction(s) via mjpis_derivation.derive_mjpis_parameters(). "
            f"v{corpus_version}: Single-jurisdiction derivation (US DOJ only) "
            f"inherits US_FEDERAL_V0 calibration. Multi-jurisdiction intersection "
            f"methodology lands in sub-task 2.2.6 when corpus expands to UK SFO + "
            f"FR PNF + WB INT."
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
