"""
SUNLIGHT Calibration Configuration
===================================
Makes Bayesian priors, detection thresholds, and evidentiary standards
configurable per tenant, jurisdiction, and deployment context.

This module replaces hardcoded priors with institution-configurable
profiles that reflect real-world prevalence rates and evidentiary
standards across different procurement environments.

References:
- OECD (2020): 20-30% of public construction investment lost to corruption
- World Bank INT: "balance of probabilities" evidentiary standard
- DOJ: "beyond reasonable doubt" criminal prosecution standard
- Transparency International CPI: per-country corruption perception scores

Usage:
    from calibration_config import CalibrationProfile, get_profile, PROFILES

    # Use a preset profile
    profile = get_profile("world_bank_africa")
    prior = profile.base_rate
    red_threshold = profile.red_posterior_threshold

    # Create a custom profile for a specific tenant
    custom = CalibrationProfile(
        name="burkina_faso_health",
        base_rate=0.20,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.65,
        yellow_posterior_threshold=0.35,
    )
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import os


# ---------------------------------------------------------------------------
# Evidentiary Standards
# ---------------------------------------------------------------------------
# These map to the institutional frameworks SUNLIGHT's buyers operate under.

EVIDENTIARY_STANDARDS = {
    "beyond_reasonable_doubt": {
        "description": "US DOJ criminal prosecution standard (~95% certainty)",
        "implied_confidence": 0.95,
        "used_by": ["US Department of Justice", "US Federal Courts"],
    },
    "clear_and_convincing": {
        "description": "US civil fraud standard (~75% certainty)",
        "implied_confidence": 0.75,
        "used_by": ["US civil courts", "SEC enforcement"],
    },
    "balance_of_probabilities": {
        "description": "World Bank/MDB sanctions standard (~51% certainty)",
        "implied_confidence": 0.51,
        "used_by": [
            "World Bank Sanctions Board",
            "African Development Bank",
            "Asian Development Bank",
            "Inter-American Development Bank",
            "EBRD",
        ],
    },
    "reasonable_suspicion": {
        "description": "Threshold for initiating investigation (~30% certainty)",
        "implied_confidence": 0.30,
        "used_by": ["SAIs", "National audit offices", "Anti-corruption agencies"],
    },
}


# ---------------------------------------------------------------------------
# Calibration Profile
# ---------------------------------------------------------------------------

@dataclass
class CalibrationProfile:
    """
    Defines detection parameters for a specific deployment context.

    Attributes:
        name: Human-readable profile identifier
        description: What this profile is for
        base_rate: Bayesian prior — estimated fraud prevalence in this context.
                   This is the single most impactful parameter. A 3% prior in
                   a 25% prevalence environment systematically under-flags.
        evidentiary_standard: Which legal/institutional standard applies
        red_posterior_threshold: Minimum posterior probability for RED tier
        yellow_posterior_threshold: Minimum posterior for YELLOW tier
        min_typologies_for_red: Minimum distinct typology triggers for RED
        fdr_alpha: False Discovery Rate control level (Benjamini-Hochberg)
        bootstrap_ci_level: Confidence interval level for bootstrap tests
        bootstrap_n_resamples: Number of bootstrap resamples
        max_flags_per_1k: Target ceiling for flags per 1,000 contracts
        notes: Implementation notes for this profile
    """

    name: str
    description: str = ""
    base_rate: float = 0.03  # Default conservative US estimate

    # Evidentiary standard
    evidentiary_standard: str = "balance_of_probabilities"

    # Tier thresholds (posterior probability cutoffs)
    red_posterior_threshold: float = 0.72
    yellow_posterior_threshold: float = 0.38

    # Tier requirements
    min_typologies_for_red: int = 2  # OR 1 typology + posterior > red_threshold
    min_ci_for_yellow: int = 66  # Minimum markup CI lower bound for YELLOW tier

    # Statistical parameters
    fdr_alpha: float = 0.05
    bootstrap_ci_level: float = 0.95
    bootstrap_n_resamples: int = 10_000

    # Operational targets
    max_flags_per_1k: int = 150

    # Metadata
    notes: str = ""
    source_citations: list = field(default_factory=list)

    def validate(self) -> list:
        """Validate profile parameters. Returns list of warnings."""
        warnings = []

        if not 0.01 <= self.base_rate <= 0.50:
            warnings.append(
                f"base_rate={self.base_rate} outside expected range [0.01, 0.50]. "
                f"OECD estimates 10-30% for developing countries, 2-5% for US federal."
            )

        if self.evidentiary_standard not in EVIDENTIARY_STANDARDS:
            warnings.append(
                f"Unknown evidentiary_standard='{self.evidentiary_standard}'. "
                f"Valid options: {list(EVIDENTIARY_STANDARDS.keys())}"
            )

        if self.red_posterior_threshold <= self.yellow_posterior_threshold:
            warnings.append(
                f"red_threshold ({self.red_posterior_threshold}) must exceed "
                f"yellow_threshold ({self.yellow_posterior_threshold})"
            )

        if self.fdr_alpha > 0.10:
            warnings.append(
                f"fdr_alpha={self.fdr_alpha} is unusually high. "
                f"Values above 0.10 weaken false positive control."
            )

        if self.bootstrap_n_resamples < 1000:
            warnings.append(
                f"bootstrap_n_resamples={self.bootstrap_n_resamples} is low. "
                f"Minimum 1,000 recommended; 10,000 for production."
            )

        return warnings

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage / API responses."""
        return {
            "name": self.name,
            "description": self.description,
            "base_rate": self.base_rate,
            "evidentiary_standard": self.evidentiary_standard,
            "red_posterior_threshold": self.red_posterior_threshold,
            "yellow_posterior_threshold": self.yellow_posterior_threshold,
            "min_typologies_for_red": self.min_typologies_for_red,
            "min_ci_for_yellow": self.min_ci_for_yellow,
            "fdr_alpha": self.fdr_alpha,
            "bootstrap_ci_level": self.bootstrap_ci_level,
            "bootstrap_n_resamples": self.bootstrap_n_resamples,
            "max_flags_per_1k": self.max_flags_per_1k,
            "notes": self.notes,
            "source_citations": self.source_citations,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CalibrationProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def summary(self) -> str:
        """Human-readable summary for audit trail / detection reports."""
        std = EVIDENTIARY_STANDARDS.get(self.evidentiary_standard, {})
        return (
            f"Calibration Profile: {self.name}\n"
            f"  Base rate (prior): {self.base_rate:.1%}\n"
            f"  Evidentiary standard: {self.evidentiary_standard} "
            f"({std.get('description', 'custom')})\n"
            f"  RED threshold: posterior ≥ {self.red_posterior_threshold:.0%} "
            f"OR {self.min_typologies_for_red}+ typologies\n"
            f"  YELLOW threshold: posterior ≥ {self.yellow_posterior_threshold:.0%}\n"
            f"  FDR alpha: {self.fdr_alpha}\n"
            f"  Bootstrap: {self.bootstrap_n_resamples:,} resamples, "
            f"{self.bootstrap_ci_level:.0%} CI\n"
            f"  Target: ≤{self.max_flags_per_1k} flags/1K contracts"
        )


# ---------------------------------------------------------------------------
# Preset Profiles
# ---------------------------------------------------------------------------
# Each profile is grounded in published institutional data.
# Engineers: do NOT change these without citing new sources.

PROFILES = {

    # ── US Federal ────────────────────────────────────────────────────────
    # NOTE: This CalibrationProfile is maintained for backward compatibility.
    # The unified JurisdictionProfile "us_federal" (jurisdiction_profile.py)
    # supersedes this for new code. Both contain identical CRI parameters.
    # Migration: CalibrationProfile (CRI only) → JurisdictionProfile (CRI + TCA).
    "doj_federal": CalibrationProfile(
        name="doj_federal",
        description=(
            "US federal procurement. Conservative prior based on estimated "
            "US procurement fraud prevalence. Thresholds calibrated against "
            "10 DOJ-prosecuted price fraud cases (100% recall)."
        ),
        base_rate=0.03,
        evidentiary_standard="beyond_reasonable_doubt",
        red_posterior_threshold=0.72,
        yellow_posterior_threshold=0.38,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=150,
        notes="Original SUNLIGHT calibration profile. Validated against DOJ cases.",
        source_citations=[
            "DOJ procurement fraud prosecutions (10 cases, 100% recall)",
            "US Government Accountability Office procurement fraud estimates",
        ],
    ),

    # ── World Bank — Global ───────────────────────────────────────────────
    "world_bank_global": CalibrationProfile(
        name="world_bank_global",
        description=(
            "World Bank-financed projects worldwide. Moderate prior reflecting "
            "blended fraud prevalence across borrower countries. Thresholds "
            "aligned to WB 'balance of probabilities' standard."
        ),
        base_rate=0.10,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.65,
        yellow_posterior_threshold=0.35,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=200,
        notes=(
            "World Bank INT uses 'more likely than not' standard, lower than "
            "DOJ criminal threshold. Prior reflects blended rate across "
            "borrower countries (OECD estimates 10-30% in developing contexts)."
        ),
        source_citations=[
            "OECD (2020): 10-30% of publicly funded construction lost to corruption",
            "World Bank Sanctions Board evidentiary standard: balance of probabilities",
            "World Bank INT 'Warning Signs' framework",
        ],
    ),

    # ── World Bank — Sub-Saharan Africa ───────────────────────────────────
    "world_bank_africa": CalibrationProfile(
        name="world_bank_africa",
        description=(
            "World Bank-financed projects in Sub-Saharan Africa. Higher prior "
            "reflecting regional procurement fraud prevalence estimates. "
            "Tuned for health, infrastructure, and education sectors."
        ),
        base_rate=0.20,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.60,
        yellow_posterior_threshold=0.32,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=250,
        notes=(
            "Sub-Saharan Africa has higher estimated procurement fraud rates. "
            "OECD estimates 20-30% loss in public construction. "
            "AfDB actively sanctions firms in Senegal, Nigeria, Kenya, Ghana. "
            "Lower RED threshold reflects 'balance of probabilities' standard "
            "and higher base rate (posteriors shift upward with higher priors)."
        ),
        source_citations=[
            "OECD (2020): 20-30% estimated corruption loss in developing country procurement",
            "AfDB sanctions cases: Senegal, Nigeria, Kenya, Ghana (2020-2025)",
            "Transparency International CPI: Sub-Saharan Africa regional scores",
        ],
    ),

    # ── African Development Bank ──────────────────────────────────────────
    "afdb": CalibrationProfile(
        name="afdb",
        description=(
            "African Development Bank-financed projects. Similar to WB Africa "
            "profile but tuned for AfDB's specific sanctionable practices "
            "framework and investigation pipeline."
        ),
        base_rate=0.20,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.60,
        yellow_posterior_threshold=0.32,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=250,
        notes=(
            "AfDB uses same 5 sanctionable practices as WB (fraud, corruption, "
            "collusion, coercion, obstruction) and participates in MDB "
            "Cross-Debarment Agreement (2010)."
        ),
        source_citations=[
            "AfDB Sanctions Procedures",
            "MDB Cross-Debarment Agreement (April 9, 2010)",
            "AfDB Office of Integrity and Anti-Corruption case reports",
        ],
    ),

    # ── EU Procurement ────────────────────────────────────────────────────
    "eu_procurement": CalibrationProfile(
        name="eu_procurement",
        description=(
            "EU member state procurement under EU Public Procurement Directive. "
            "Moderate prior based on OECD/OLAF estimates. Aligned with "
            "OECD Belgium risk model methodology."
        ),
        base_rate=0.08,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.68,
        yellow_posterior_threshold=0.36,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=175,
        notes=(
            "EU procurement has better data quality (EU Directive standardization) "
            "but still significant corruption risk. OECD 2025 Belgium model "
            "uses single-bidding as proxy for corruption — similar statistical "
            "approach to SUNLIGHT. OLAF estimates vary by member state."
        ),
        source_citations=[
            "OECD (2025): Data-Driven Corruption Risk Model for Belgium",
            "EU OLAF: anti-fraud investigations in EU-funded procurement",
            "OpenTender dataset: 34 countries, 2003-2017",
        ],
    ),

    # ── National Audit Office / SAI ───────────────────────────────────────
    "sai_developing": CalibrationProfile(
        name="sai_developing",
        description=(
            "Supreme Audit Institution in a developing country. Broader net "
            "with lower thresholds — SAIs need to identify risk areas for "
            "audit planning, not just high-confidence fraud leads."
        ),
        base_rate=0.15,
        evidentiary_standard="reasonable_suspicion",
        red_posterior_threshold=0.55,
        yellow_posterior_threshold=0.28,
        min_typologies_for_red=1,
        fdr_alpha=0.08,
        max_flags_per_1k=300,
        notes=(
            "SAIs use SUNLIGHT for audit planning and risk-based sampling, "
            "not prosecution. Broader net is appropriate — they need to "
            "identify WHERE to audit, not WHERE to prosecute. Higher FDR "
            "alpha (0.08) acceptable because false positives lead to audits, "
            "not sanctions."
        ),
        source_citations=[
            "INTOSAI Journal: continuous transaction analytics for SAIs",
            "OECD: SAI digital maturity and data-driven audit planning",
        ],
    ),

    # ── IMF Fiscal Affairs ────────────────────────────────────────────────
    "imf_fiscal": CalibrationProfile(
        name="imf_fiscal",
        description=(
            "IMF Fiscal Affairs Department. Focused on systemic procurement "
            "integrity indicators at country/sector level rather than "
            "individual contract investigation."
        ),
        base_rate=0.12,
        evidentiary_standard="balance_of_probabilities",
        red_posterior_threshold=0.62,
        yellow_posterior_threshold=0.33,
        min_typologies_for_red=2,
        fdr_alpha=0.05,
        max_flags_per_1k=200,
        notes=(
            "IMF uses procurement data as fiscal governance indicator. "
            "More interested in aggregate risk patterns (agency-level, "
            "sector-level) than individual contract flags."
        ),
        source_citations=[
            "IMF Fiscal Affairs: procurement as fiscal governance indicator",
        ],
    ),
}


# ---------------------------------------------------------------------------
# Access Functions
# ---------------------------------------------------------------------------

def get_profile(name: str) -> CalibrationProfile:
    """
    Retrieve a calibration profile by name.

    Args:
        name: Profile identifier (e.g., "doj_federal", "world_bank_africa")

    Returns:
        CalibrationProfile instance

    Raises:
        KeyError: If profile name not found
    """
    if name not in PROFILES:
        available = ", ".join(sorted(PROFILES.keys()))
        raise KeyError(
            f"Unknown calibration profile '{name}'. Available: {available}"
        )
    return PROFILES[name]


def list_profiles() -> list:
    """List all available profile names with descriptions."""
    return [
        {"name": p.name, "description": p.description, "base_rate": p.base_rate}
        for p in PROFILES.values()
    ]


def create_tenant_profile(
    tenant_id: str,
    base_profile: str = "world_bank_global",
    overrides: Optional[dict] = None,
) -> CalibrationProfile:
    """
    Create a tenant-specific profile by starting from a base and applying overrides.

    Args:
        tenant_id: Tenant identifier
        base_profile: Name of the base profile to start from
        overrides: Dict of parameter overrides (e.g., {"base_rate": 0.18})

    Returns:
        New CalibrationProfile with tenant-specific settings
    """
    base = get_profile(base_profile)
    params = base.to_dict()
    params["name"] = f"tenant_{tenant_id}"
    params["description"] = f"Custom profile for tenant {tenant_id}, based on {base_profile}"

    if overrides:
        for k, v in overrides.items():
            if k in params:
                params[k] = v

    profile = CalibrationProfile.from_dict(params)
    warnings = profile.validate()
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")

    return profile


def load_profile_from_file(path: str) -> CalibrationProfile:
    """Load a calibration profile from a JSON file."""
    with open(path, "r") as f:
        data = json.load(f)
    return CalibrationProfile.from_dict(data)


def save_profile_to_file(profile: CalibrationProfile, path: str) -> None:
    """Save a calibration profile to a JSON file."""
    with open(path, "w") as f:
        f.write(profile.to_json())


# ---------------------------------------------------------------------------
# Integration Helpers
# ---------------------------------------------------------------------------
# These functions are designed to be called from institutional_pipeline.py
# to replace hardcoded values.

def get_prior_for_context(
    profile: CalibrationProfile,
) -> float:
    """
    Returns the Bayesian prior (base_rate) for use in posterior calculation.

    Drop-in replacement for hardcoded prior in institutional_pipeline.py:

    BEFORE:
        prior = 0.03  # hardcoded

    AFTER:
        from calibration_config import get_profile, get_prior_for_context
        profile = get_profile(tenant_config["calibration_profile"])
        prior = get_prior_for_context(profile)
    """
    return profile.base_rate


def get_tier_thresholds(
    profile: CalibrationProfile,
) -> dict:
    """
    Returns tier assignment thresholds for use in assign_tier().

    Drop-in replacement for hardcoded thresholds in institutional_pipeline.py:

    BEFORE:
        if posterior > 0.72 or num_typologies >= 2:
            tier = "RED"
        elif posterior > 0.38:
            tier = "YELLOW"

    AFTER:
        from calibration_config import get_profile, get_tier_thresholds
        thresholds = get_tier_thresholds(profile)
        if posterior > thresholds["red"] or num_typologies >= thresholds["min_typ_red"]:
            tier = "RED"
        elif posterior > thresholds["yellow"]:
            tier = "YELLOW"
    """
    return {
        "red": profile.red_posterior_threshold,
        "yellow": profile.yellow_posterior_threshold,
        "min_typ_red": profile.min_typologies_for_red,
        "min_ci_yellow": profile.min_ci_for_yellow,
    }


def get_fdr_params(profile: CalibrationProfile) -> dict:
    """Returns FDR correction parameters."""
    return {"alpha": profile.fdr_alpha}


def get_bootstrap_params(profile: CalibrationProfile) -> dict:
    """Returns bootstrap test parameters."""
    return {
        "ci_level": profile.bootstrap_ci_level,
        "n_resamples": profile.bootstrap_n_resamples,
    }


# ---------------------------------------------------------------------------
# Provenance String (for detection reports / audit trail)
# ---------------------------------------------------------------------------

def provenance_string(profile: CalibrationProfile) -> str:
    """
    Generate a provenance string for inclusion in detection reports.
    This appears in the case packet under "Calibration Context."

    Example output:
        "Calibration: world_bank_africa | Prior: 20.0% | Standard: balance_of_probabilities |
         RED ≥ 60% posterior OR 2+ typologies | YELLOW ≥ 32% | FDR α=0.05"
    """
    return (
        f"Calibration: {profile.name} | "
        f"Prior: {profile.base_rate:.1%} | "
        f"Standard: {profile.evidentiary_standard} | "
        f"RED ≥ {profile.red_posterior_threshold:.0%} posterior "
        f"OR {profile.min_typologies_for_red}+ typologies | "
        f"YELLOW ≥ {profile.yellow_posterior_threshold:.0%} | "
        f"FDR α={profile.fdr_alpha}"
    )


# ---------------------------------------------------------------------------
# CLI: Print all profiles
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 72)
    print("SUNLIGHT Calibration Profiles")
    print("=" * 72)
    for name, profile in PROFILES.items():
        print()
        print(profile.summary())
        warnings = profile.validate()
        if warnings:
            for w in warnings:
                print(f"  ⚠ WARNING: {w}")
    print()
    print("=" * 72)
    print(f"Total profiles: {len(PROFILES)}")
    print("Evidentiary standards supported:", list(EVIDENTIARY_STANDARDS.keys()))
