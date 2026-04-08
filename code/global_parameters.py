"""
SUNLIGHT Global Statistical Parameters Registry
================================================

Unified statistical calibration parameters shared across jurisdictions.

Architecture:
    JurisdictionProfile = LOCAL parameters (fiscal calendar, thresholds, citations)
                        + REFERENCE to GLOBAL parameters (statistical bars)

This module provides the GLOBAL parameter registry. Profiles reference global
parameters by version string, enabling the "living standard" pattern:
    - Update the global parameter set once
    - All profiles referencing that version inherit the update
    - No per-jurisdiction recalibration required

Version Semantics:
    - "us_federal_v0": Empirical calibration from DOJ-prosecuted cases (sub-task 2.2.4a)
      - Source: 9 DOJ federal procurement fraud prosecutions
      - Evidentiary standard: beyond_reasonable_doubt (US criminal)
      - Red posterior: 0.72 (72% confidence for RED tier)
      - Yellow posterior: 0.38 (38% confidence for YELLOW tier)
      - FDR alpha: 0.05 (5% false discovery rate)
      - Bootstrap: 10,000 resamples

    - "mjpis_draft_v0": Multi-Jurisdiction Procurement Integrity Standard (DRAFT)
      - Source: PLACEHOLDER — pending multi-jurisdiction corpus assembly (sub-task 2.2.5b)
      - Will derive from unified prosecuted-case corpus across:
        * US DOJ (9 cases)
        * UK Serious Fraud Office (SFO prosecutions 2015-2025)
        * French Parquet National Financier (PNF)
        * World Bank Integrity Vice Presidency (INT)
      - Current values: Conservative placeholders (copy of us_federal_v0)
      - DO NOT USE IN PRODUCTION until derivation is complete

Future versions:
    - "mjpis_v1": First production multi-jurisdiction standard
    - "world_bank_mdb_v1": World Bank/MDB-specific calibration
    - "sai_audit_planning_v1": Supreme Audit Institution audit planning profile
    - Country-specific versions as empirical data becomes available

Usage:
    from global_parameters import get_global_parameters

    # Get global parameters by version
    global_params = get_global_parameters("us_federal_v0")

    # Use in JurisdictionProfile
    profile = JurisdictionProfile(
        name="example",
        global_params_version="us_federal_v0",
        # ... local parameters ...
    )

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
Schema Version: GP-2026-04-001
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL PARAMETERS DATACLASS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GlobalParameters:
    """
    Global statistical calibration parameters shared across jurisdictions.

    These parameters control CRI's detection machinery and apply uniformly
    across all contracts within a jurisdiction. They represent methodological
    choices about evidentiary bars, statistical rigor, and operational workload,
    not jurisdiction-specific legal/fiscal facts.

    Fields mirror the GLOBAL PARAMETERS section of JurisdictionProfile but
    are versioned and shared across multiple profiles.
    """

    # Identity
    version: str
    # Version identifier (e.g., "us_federal_v0", "mjpis_v1")
    # Used as registry key and profile reference

    description: str = ""
    # Human-readable description of what this parameter set represents

    source_citation: str = ""
    # Where these numbers came from (calibration corpus, research paper, etc.)

    derivation_date: str = ""
    # ISO date string of when these values were computed/published

    # Evidentiary Standard
    evidentiary_standard: str = "balance_of_probabilities"
    # Legal/institutional framework for detection confidence
    # Options:
    #   "beyond_reasonable_doubt" (US DOJ criminal, ~95% certainty)
    #   "clear_and_convincing" (US civil fraud, ~75% certainty)
    #   "balance_of_probabilities" (World Bank/MDB, ~51% certainty)
    #   "reasonable_suspicion" (SAI audit planning, ~30% certainty)
    #   "intersection_of_mature_legal_systems" (MJPIS target)

    # Bayesian Prior
    default_base_rate: float = 0.03
    # Default Bayesian prior — estimated fraud prevalence
    # Profiles can override with jurisdiction-specific base_rate
    # Examples:
    #   us_federal: 0.03 (3%, GAO estimate)
    #   uk: 0.025 (2.5%, TI CPI)
    #   world_bank_africa: 0.20 (20%, OECD developing country estimate)

    # Tier Assignment Thresholds
    red_posterior_threshold: float = 0.72
    # Minimum posterior probability for RED tier classification
    # Examples:
    #   us_federal: 0.72 (72%, aligned with "beyond reasonable doubt")
    #   world_bank: 0.65 (65%, "balance of probabilities")

    yellow_posterior_threshold: float = 0.38
    # Minimum posterior probability for YELLOW tier classification
    # Examples:
    #   us_federal: 0.38 (38%)
    #   world_bank: 0.35 (35%)

    min_typologies_for_red: int = 2
    # Minimum distinct typology triggers required for RED tier
    # Examples:
    #   us_federal/world_bank: 2
    #   sai_developing: 1 (broader net for audit planning)

    min_ci_for_yellow: int = 66
    # Minimum markup confidence interval lower bound (percentage) for YELLOW tier
    # Examples:
    #   us_federal: 66
    #   world_bank: 65

    # Statistical Rigor
    fdr_alpha: float = 0.05
    # False Discovery Rate control level (Benjamini-Hochberg correction)
    # Examples:
    #   us_federal/world_bank: 0.05 (5% FDR)
    #   sai_developing: 0.08 (8% FDR, broader net acceptable for audit planning)

    bootstrap_ci_level: float = 0.95
    # Confidence interval level for bootstrap statistical tests
    # Examples:
    #   us_federal: 0.95 (95% CI)

    bootstrap_n_resamples: int = 10_000
    # Number of bootstrap resamples for statistical tests
    # Examples:
    #   us_federal: 10,000 (production standard)
    #   development: 1,000 (faster testing)

    # Operational Workload
    max_flags_per_1k: int = 150
    # Operational target for maximum flags per 1,000 contracts
    # Examples:
    #   us_federal: 150
    #   world_bank_africa: 250 (higher risk environment)
    #   sai_developing: 300 (audit planning context, not prosecution)

    # Metadata
    notes: str = ""
    # Implementation notes, validation history, special considerations


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

_GLOBAL_PARAMETERS_REGISTRY: Dict[str, GlobalParameters] = {}


def register_global_parameters(params: GlobalParameters) -> None:
    """
    Register a global parameter set in the registry.

    Args:
        params: GlobalParameters instance to register

    Raises:
        ValueError: If params.version already exists in registry
    """
    if params.version in _GLOBAL_PARAMETERS_REGISTRY:
        raise ValueError(
            f"Global parameters version '{params.version}' already registered. "
            f"Existing versions: {list(_GLOBAL_PARAMETERS_REGISTRY.keys())}"
        )
    _GLOBAL_PARAMETERS_REGISTRY[params.version] = params


def get_global_parameters(version: str) -> GlobalParameters:
    """
    Load global parameters by version string.

    Args:
        version: Version identifier (e.g., "us_federal_v0", "mjpis_v1")

    Returns:
        GlobalParameters instance for the given version

    Raises:
        ValueError: If version not found in registry

    Usage:
        global_params = get_global_parameters("us_federal_v0")
        red_threshold = global_params.red_posterior_threshold
    """
    if version not in _GLOBAL_PARAMETERS_REGISTRY:
        available = ", ".join(sorted(_GLOBAL_PARAMETERS_REGISTRY.keys()))
        raise ValueError(
            f"Unknown global parameters version '{version}'. "
            f"Available versions: {available or '(none registered)'}"
        )
    return _GLOBAL_PARAMETERS_REGISTRY[version]


def list_global_parameters() -> List[dict]:
    """List all registered global parameter sets with basic metadata."""
    return [
        {
            "version": p.version,
            "description": p.description,
            "evidentiary_standard": p.evidentiary_standard,
            "source_citation": p.source_citation,
            "derivation_date": p.derivation_date,
        }
        for p in _GLOBAL_PARAMETERS_REGISTRY.values()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# US_FEDERAL_V0 — Empirical DOJ Calibration (Sub-task 2.2.4a)
# ═══════════════════════════════════════════════════════════════════════════

US_FEDERAL_V0 = GlobalParameters(
    version="us_federal_v0",
    description=(
        "US federal government empirical calibration from DOJ-prosecuted "
        "procurement fraud cases. Conservative statistical bars aligned with "
        "'beyond reasonable doubt' criminal evidentiary standard. Validated "
        "on 9 DOJ prosecutions with 100% recall, 37.5% precision."
    ),
    source_citation=(
        "doj_federal calibration profile, sub-task 2.2.4a inventory. "
        "9 DOJ-prosecuted price fraud cases (Oracle 2011, Boeing 2006, "
        "DynCorp 2005, Lockheed Martin 2012, United Technologies 2015, "
        "Northrop Grumman 2009, CACI 2010, Raytheon 2014, BAE Systems 2010). "
        "Corpus value: $941.4M fraud detected."
    ),
    derivation_date="2026-04-08",
    evidentiary_standard="beyond_reasonable_doubt",
    default_base_rate=0.03,  # 3% GAO federal procurement fraud estimate
    red_posterior_threshold=0.72,  # 72% confidence for RED tier
    yellow_posterior_threshold=0.38,  # 38% confidence for YELLOW tier
    min_typologies_for_red=2,
    min_ci_for_yellow=66,
    fdr_alpha=0.05,  # 5% false discovery rate
    bootstrap_ci_level=0.95,  # 95% confidence interval
    bootstrap_n_resamples=10_000,  # Production-grade resampling
    max_flags_per_1k=150,  # Operational workload target
    notes=(
        "Original SUNLIGHT global calibration. Preserves DOJ validation "
        "baseline (100% recall, precision 37.5% with 95% CI [17.4%, 57.7%]). "
        "Used by us_federal and uk_central_government jurisdiction profiles "
        "pending multi-jurisdiction consensus derivation."
    ),
)

# Register us_federal_v0
register_global_parameters(US_FEDERAL_V0)


# ═══════════════════════════════════════════════════════════════════════════
# MJPIS_DRAFT_V0 — Multi-Jurisdiction Procurement Integrity Standard (PLACEHOLDER)
# ═══════════════════════════════════════════════════════════════════════════

MJPIS_DRAFT_V0 = GlobalParameters(
    version="mjpis_draft_v0",
    description=(
        "Multi-Jurisdiction Procurement Integrity Standard — DRAFT placeholder. "
        "Real values will be derived from unified multi-jurisdiction prosecuted-case "
        "corpus in sub-task 2.2.5b. This is an architectural placeholder with "
        "conservative values copied from us_federal_v0. "
        "DO NOT USE IN PRODUCTION until derivation is complete."
    ),
    source_citation=(
        "Placeholder — pending multi-jurisdiction corpus assembly and statistical "
        "derivation in sub-task 2.2.5b. Target corpus: US DOJ (9 cases), UK SFO "
        "(crown prosecutions 2015-2025), French PNF (procurement cases), World Bank "
        "INT (sanctions board cases). Derivation method: intersection of mature "
        "legal systems, consensus statistical bars maximizing precision while "
        "preserving recall across jurisdictions."
    ),
    derivation_date="2026-04-08",
    evidentiary_standard="intersection_of_mature_legal_systems",
    # Placeholder values below — will be replaced by real derivation
    default_base_rate=0.03,  # PLACEHOLDER (copied from us_federal_v0)
    red_posterior_threshold=0.72,  # PLACEHOLDER (copied from us_federal_v0)
    yellow_posterior_threshold=0.38,  # PLACEHOLDER (copied from us_federal_v0)
    min_typologies_for_red=2,  # PLACEHOLDER (copied from us_federal_v0)
    min_ci_for_yellow=66,  # PLACEHOLDER (copied from us_federal_v0)
    fdr_alpha=0.05,  # PLACEHOLDER (copied from us_federal_v0)
    bootstrap_ci_level=0.95,  # PLACEHOLDER (copied from us_federal_v0)
    bootstrap_n_resamples=10_000,  # PLACEHOLDER (copied from us_federal_v0)
    max_flags_per_1k=150,  # PLACEHOLDER (copied from us_federal_v0)
    notes=(
        "DRAFT PLACEHOLDER VERSION. This is the registry slot the living standard "
        "will occupy once multi-jurisdiction research produces real values. Current "
        "values are conservative placeholders (identical to us_federal_v0) to enable "
        "architectural testing. Sub-task 2.2.5b will replace these with empirically "
        "derived consensus thresholds from the unified prosecuted-case corpus."
    ),
)

# Register mjpis_draft_v0
register_global_parameters(MJPIS_DRAFT_V0)


# ═══════════════════════════════════════════════════════════════════════════
# CLI: Print registry summary
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 72)
    print("SUNLIGHT Global Parameters Registry")
    print("=" * 72)
    for params in _GLOBAL_PARAMETERS_REGISTRY.values():
        print()
        print(f"Version: {params.version}")
        print(f"  Description: {params.description[:80]}...")
        print(f"  Evidentiary standard: {params.evidentiary_standard}")
        print(f"  RED threshold: posterior ≥ {params.red_posterior_threshold:.0%}")
        print(f"  YELLOW threshold: posterior ≥ {params.yellow_posterior_threshold:.0%}")
        print(f"  FDR alpha: {params.fdr_alpha}")
        print(f"  Bootstrap resamples: {params.bootstrap_n_resamples:,}")
    print()
    print("=" * 72)
    print(f"Total versions registered: {len(_GLOBAL_PARAMETERS_REGISTRY)}")
    print(f"Available versions: {', '.join(sorted(_GLOBAL_PARAMETERS_REGISTRY.keys()))}")
