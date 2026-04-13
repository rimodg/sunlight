"""
SUNLIGHT Jurisdiction Profile System
=====================================

Unified jurisdiction configuration for TCA + CRI engines.
Replaces all hardcoded jurisdiction-specific constants.

This module enables SUNLIGHT to deploy across UNDP's 170-country operational
context without per-deployment rule rewriting. It unifies:
- TCA structural rules (fiscal calendar, procurement thresholds, legal citations)
- CRI statistical calibration (Bayesian priors, detection thresholds)

Architecture:
    JurisdictionProfile = CalibrationProfile + Fiscal Calendar + Legal Framework

The profile is the single source of truth for:
1. When the fiscal year ends (TIME-001, TIME-002, TIME-003)
2. What procurement threshold triggers competition requirements (PROC-001)
3. Which legal citations ground rule evidence (all rules)
4. What fraud prevalence rate informs Bayesian priors (CRI scoring)
5. What evidentiary standard applies (RED/YELLOW tier thresholds)

Authors: Rimwaya Ouedraogo, Hugo Villalba
Version: 1.0.0
Schema Version: JP-2026-04-001
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
import os


@dataclass
class JurisdictionProfile:
    """
    Unified jurisdiction configuration for TCA + CRI engines.
    Replaces all hardcoded jurisdiction-specific constants.

    This profile contains THREE categories of parameters:
    1. Fiscal/Procurement Parameters (for TCA structural rules)
    2. Legal Framework (for TCA evidence citations)
    3. Statistical Calibration (for CRI detection thresholds)

    Each parameter documents:
    - What it controls
    - Example values for common jurisdictions
    - Which rules/functions consume it
    """

    # ═══════════════════════════════════════════════════════════
    # IDENTITY
    # ═══════════════════════════════════════════════════════════

    name: str
    # Profile identifier (e.g., "us_federal", "uk", "world_bank_africa")
    # Consumed by: Audit trail, logging

    description: str = ""
    # Human-readable description of this profile's jurisdiction/context

    country_code: Optional[str] = None
    # ISO 3166-1 alpha-2 code ("US", "GB", "UA", None for multi-country)
    # Consumed by: GEO-001, GEO-002 (geographic mismatch detection)


    # ═══════════════════════════════════════════════════════════════════════════
    # LOCAL PARAMETERS — Jurisdiction-Specific Configuration
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # These parameters vary by jurisdiction and are consumed by TCA structural rules.
    # They represent local legal/fiscal/procurement context:
    #   - Fiscal calendar (when the fiscal year ends, which months have pressure)
    #   - Procurement thresholds (competition requirements, currency)
    #   - Price variation tolerances (acceptable markup ranges)
    #   - Legal framework (citations, oversight bodies)
    #
    # Why "local"? Because fiscal year-end in the UK (March 31) is different from
    # the US federal government (September 30), and both are different from
    # calendar-year jurisdictions (December 31). These parameters adapt SUNLIGHT's
    # structural rules to the local operating environment.
    #
    # TCA rules (TIME-001, PROC-001, FIN-001, etc.) use these parameters to detect
    # structural anomalies relative to local norms.
    # ═══════════════════════════════════════════════════════════════════════════


    # ═══════════════════════════════════════════════════════════
    # FISCAL CALENDAR (for TCA TIME-001, TIME-002, TIME-003)
    # ═══════════════════════════════════════════════════════════

    fiscal_year_end_month: int = 12
    # Month when fiscal year ends (1-12)
    # Examples:
    #   us_federal: 9 (Sep 30)
    #   us_private/colombia/mexico/paraguay: 12 (Dec 31)
    #   uk/india/japan/canada/south_africa/nigeria/kenya: 3 (Mar 31)
    #   australia/pakistan/egypt/bangladesh: 6 (Jun 30)
    # Consumed by: TIME-001 (fiscal year-end pressure detection)

    fiscal_year_end_day: int = 31
    # Day when fiscal year ends (1-31)
    # Examples:
    #   us_federal: 30 (Sep 30)
    #   uk: 31 (Mar 31)
    #   us_private: 31 (Dec 31)
    # Consumed by: TIME-001 (final 2 weeks = day >= year_end_day - 15)

    fiscal_q4_months: List[int] = field(default_factory=lambda: [10, 11, 12])
    # Months in final fiscal quarter
    # Examples:
    #   us_federal: [7, 8, 9]
    #   us_private/colombia: [10, 11, 12]
    #   uk/india: [1, 2, 3]
    #   australia: [4, 5, 6]
    # Consumed by: TIME-002 (quarter-end pressure detection)

    fiscal_safe_months: List[int] = field(default_factory=lambda: [1, 2, 7, 8])
    # Months with no fiscal pressure (positive structural signal)
    # Examples:
    #   us_federal: [10, 11, 12, 4, 5, 6]
    #   uk: [7, 8, 9, 10]
    #   us_private: [1, 2, 7, 8]
    # Consumed by: TIME-003 (absence of timing anomaly)


    # ═══════════════════════════════════════════════════════════
    # PROCUREMENT THRESHOLDS (for TCA PROC-001)
    # ═══════════════════════════════════════════════════════════

    competitive_threshold: float = 100_000
    # Minimum contract value requiring competitive procurement
    # Examples:
    #   us_federal: 250_000 USD (FAR Part 6)
    #   uk: 214_000 GBP (Procurement Act 2023, central government)
    #   ukraine: 200_000 UAH (Prozorro threshold)
    #   world_bank: 100_000 USD (UNDP POPP default)
    # Consumed by: PROC-001 (direct award threshold violation)

    currency: str = "USD"
    # ISO 4217 currency code
    # Examples:
    #   us_federal: "USD"
    #   uk: "GBP"
    #   ukraine: "UAH"
    #   eurozone: "EUR"
    # Consumed by: PROC-001, FIN-001, FIN-002, FIN-003, CRI mega_contract logic

    mega_contract_threshold: float = 25_000_000
    # Threshold for "mega contract" Bayesian context modifier
    # Examples:
    #   us_federal: 25_000_000 USD
    #   uk: 20_000_000 GBP
    #   ukraine: 100_000_000 UAH
    #   world_bank_africa: 10_000_000 USD (lower for developing context)
    # Consumed by: CRI Bayesian context (institutional_pipeline.py:106)


    # ═══════════════════════════════════════════════════════════
    # PRICE VARIATION TOLERANCES (for TCA FIN-001, FIN-003)
    # ═══════════════════════════════════════════════════════════

    max_award_inflation_pct: float = 15.0
    # Maximum allowable award inflation above tender estimate (percentage)
    # Examples:
    #   us_federal/world_bank: 15.0%
    #   eu: 10.0% (stricter)
    # Consumed by: FIN-001 (post-tender price inflation detection)

    competitive_pricing_tolerance_pct: float = 5.0
    # Tolerance band for "competitive outcome" pricing (percentage)
    # Examples:
    #   world_bank/oecd: 5.0% (±5% = 0.95 to 1.05 ratio)
    # Consumed by: FIN-003 (award closely matches tender = competitive signal)


    # ═══════════════════════════════════════════════════════════
    # LEGAL FRAMEWORK (for TCA rule evidence citations)
    # ═══════════════════════════════════════════════════════════

    legal_citations: Dict[str, str] = field(default_factory=dict)
    # Jurisdiction-specific legal citations for evidence strings.
    # Institutional-grade profiles should populate all 11 keys below.
    # New profiles should use us_federal as the template for depth.
    #
    # --- Keys consumed by TCA rules (PROC-001, ENT-001, ENT-002) ---
    #   "procurement_law"           — primary procurement statute(s)
    #   "case_authority"            — leading case law references
    #
    # --- Keys consumed by CRI _determine_tier() evidence citations ---
    #   "false_claims_law"          — statute for false/fraudulent claims
    #   "false_records_law"         — statute for false records/material misstatement
    #   "anti_kickback_law"         — anti-corruption/kickback statute
    #   "extreme_markup_precedent"  — prosecution precedent for extreme price inflation
    #
    # --- Institutional depth keys (not yet consumed by rules) ---
    #   "foreign_bribery_law"           — foreign bribery / transnational corruption statute
    #   "audit_oversight_law"           — audit/oversight/inspector general authority
    #   "sanctions_debarment_law"       — debarment, suspension, and sanctions authority
    #   "conflict_of_interest_law"      — conflict of interest / procurement integrity statute
    #   "whistleblower_protection_law"  — whistleblower / anti-retaliation protections

    universal_citations: List[str] = field(default_factory=lambda: [
        "UNCAC Art. 9(1) — Public procurement systems based on transparency, competition and objective criteria",
        "UNCAC Art. 9(2) — Public finance management measures",
        "UNCAC Art. 12 — Private sector measures against corruption",
        "UNCAC Art. 15 — Bribery of national public officials",
        "UNCAC Art. 16 — Bribery of foreign public officials and officials of public international organizations",
        "UNCAC Art. 17 — Embezzlement, misappropriation or other diversion of property by a public official",
        "UNCAC Art. 18 — Trading in influence",
        "OECD Anti-Bribery Convention 1997 — Convention on Combating Bribery of Foreign Public Officials in International Business Transactions",
        "OECD Recommendation on Public Procurement 2015 — OECD/LEGAL/0411",
    ])
    # Universally-applicable international framework citations.
    # Ordered: procurement-specific UNCAC first, broader anti-corruption UNCAC second,
    # OECD instruments third. Order determines emission order in evidence strings.
    # Consumed by: PROC-001 evidence string (full list, no slicing)

    oversight_body_names: List[str] = field(default_factory=list)
    # Institution name strings that indicate oversight is present
    # Examples:
    #   us_federal: ["Inspector General", "GAO", "Government Accountability Office"]
    #   uk: ["National Audit Office", "NAO", "Public Accounts Committee"]
    #   world_bank: ["Integrity Vice Presidency", "INT", "Sanctions Board"]
    # Consumed by: PROC-003, PROC-004 (oversight body detection)
    # Note: Not consumed in 2.2.4a — included in schema for 2.2.4b


    # ═══════════════════════════════════════════════════════════════════════════
    # GLOBAL PARAMETERS — Statistical Calibration
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # These parameters control CRI's statistical detection machinery. While they
    # vary across profiles (DOJ vs World Bank vs SAI), they represent global
    # statistical/methodological choices, not jurisdiction-specific legal/fiscal facts.
    #
    # Key distinction from LOCAL parameters:
    #   - LOCAL: "When does the fiscal year end?" (legal/fiscal fact)
    #   - GLOBAL: "How confident must we be to flag?" (statistical/operational choice)
    #
    # Examples:
    #   - base_rate: fraud prevalence estimate (Bayesian prior)
    #   - red_posterior_threshold: minimum confidence for RED classification
    #   - bootstrap_n_resamples: statistical rigor parameter
    #
    # These parameters are consumed by the CRI statistical engines (Bayesian scoring,
    # bootstrap analysis, tier assignment) and control the detection sensitivity,
    # false positive rate, and operational workload.
    #
    # Why "global"? Because they apply uniformly across all contracts within a
    # jurisdiction, rather than varying by contract type, buyer, or procurement method.
    # They represent the statistical lens through which we view the structural
    # anomalies detected by TCA rules.
    # ═══════════════════════════════════════════════════════════════════════════


    # ═══════════════════════════════════════════════════════════
    # CRI STATISTICAL CALIBRATION (for institutional pipeline)
    # ═══════════════════════════════════════════════════════════

    global_params_version: str = "us_federal_v0"
    # Reference to global statistical parameters registry
    # Options:
    #   "us_federal_v0": Empirical DOJ calibration (sub-task 2.2.4a)
    #   "mjpis_draft_v0": Multi-jurisdiction standard (DRAFT, pending sub-task 2.2.5b)
    # Consumed by: Future migration (sub-task TBD) — currently coexists with legacy fields
    # Note: Legacy fields (base_rate, red_posterior_threshold, etc.) remain for backwards
    # compatibility during migration. Consumers will be migrated to use
    # get_global_parameters(profile.global_params_version) in future sub-tasks.

    base_rate: float = 0.03
    # Bayesian prior — estimated fraud prevalence in this context
    # Examples:
    #   us_federal: 0.03 (3%, GAO estimate)
    #   uk: 0.05 (5%, OECD estimate)
    #   world_bank_africa: 0.20 (20%, OECD developing country estimate)
    #   ukraine: 0.15 (15%, TI CPI-adjusted)
    # Consumed by: BayesianFraudPrior (institutional_pipeline.py:104-105)

    evidentiary_standard: str = "balance_of_probabilities"
    # Legal/institutional framework for detection confidence
    # Options:
    #   "beyond_reasonable_doubt" (US DOJ criminal, ~95% certainty)
    #   "clear_and_convincing" (US civil fraud, ~75% certainty)
    #   "balance_of_probabilities" (World Bank/MDB, ~51% certainty)
    #   "reasonable_suspicion" (SAI audit planning, ~30% certainty)
    # Consumed by: Documentation, audit trail

    red_posterior_threshold: float = 0.72
    # Minimum posterior probability for RED tier classification
    # Examples:
    #   us_federal: 0.72 (72%, aligned with "beyond reasonable doubt")
    #   world_bank: 0.65 (65%, "balance of probabilities")
    #   world_bank_africa: 0.60 (60%, lower due to higher base rate)
    # Consumed by: assign_tier() (institutional_pipeline.py:120)

    yellow_posterior_threshold: float = 0.38
    # Minimum posterior probability for YELLOW tier classification
    # Examples:
    #   us_federal: 0.38 (38%)
    #   world_bank: 0.35 (35%)
    #   world_bank_africa: 0.32 (32%)
    # Consumed by: assign_tier() (institutional_pipeline.py:121)

    min_typologies_for_red: int = 2
    # Minimum distinct typology triggers required for RED tier
    # Examples:
    #   us_federal/world_bank: 2
    #   sai_developing: 1 (broader net for audit planning)
    # Consumed by: assign_tier() (future — not in current institutional_pipeline.py)

    min_ci_for_yellow: int = 66
    # Minimum markup confidence interval lower bound (percentage) for YELLOW tier
    # Examples:
    #   us_federal: 66
    #   world_bank: 65
    # Consumed by: assign_tier() (institutional_pipeline.py:141)

    fdr_alpha: float = 0.05
    # False Discovery Rate control level (Benjamini-Hochberg correction)
    # Examples:
    #   us_federal/world_bank: 0.05 (5% FDR)
    #   sai_developing: 0.08 (8% FDR, broader net acceptable for audit planning)
    # Consumed by: MultipleTestingCorrection (institutional_pipeline.py:264)

    bootstrap_ci_level: float = 0.95
    # Confidence interval level for bootstrap statistical tests
    # Examples:
    #   us_federal: 0.95 (95% CI)
    # Consumed by: BootstrapAnalyzer (institutional_statistical_rigor.py)

    bootstrap_n_resamples: int = 10_000
    # Number of bootstrap resamples for statistical tests
    # Examples:
    #   us_federal: 10,000 (production standard)
    #   development: 1,000 (faster testing)
    # Consumed by: BootstrapAnalyzer (institutional_statistical_rigor.py)

    max_flags_per_1k: int = 150
    # Operational target for maximum flags per 1,000 contracts
    # Examples:
    #   us_federal: 150
    #   world_bank_africa: 250 (higher risk environment)
    #   sai_developing: 300 (audit planning context, not prosecution)
    # Consumed by: Documentation, operational capacity planning


    # ═══════════════════════════════════════════════════════════
    # METADATA
    # ═══════════════════════════════════════════════════════════

    notes: str = ""
    # Implementation notes, validation history, special considerations

    source_citations: List[str] = field(default_factory=list)
    # Academic/legal sources grounding this profile's parameters


    def validate(self) -> List[str]:
        """
        Validate profile parameters. Returns list of warnings.

        Checks:
        - Base rate is reasonable (0.01 to 0.50)
        - Evidentiary standard is recognized
        - RED threshold > YELLOW threshold
        - Fiscal calendar values are valid
        - Currency code is reasonable
        - FDR alpha is not too permissive
        """
        warnings = []

        # Base rate validation
        if not 0.01 <= self.base_rate <= 0.50:
            warnings.append(
                f"base_rate={self.base_rate} outside expected range [0.01, 0.50]. "
                f"OECD estimates 10-30% for developing countries, 2-5% for US federal."
            )

        # Evidentiary standard validation
        valid_standards = [
            "beyond_reasonable_doubt",
            "clear_and_convincing",
            "balance_of_probabilities",
            "more_likely_than_not",
            "french_cjip_admission_of_facts",
            "wb_sanctions_board_decision",
            "negotiated_resolution_agreement",
            "reasonable_suspicion",
        ]
        if self.evidentiary_standard not in valid_standards:
            warnings.append(
                f"evidentiary_standard='{self.evidentiary_standard}' not recognized. "
                f"Valid: {valid_standards}"
            )

        # Threshold ordering
        if self.red_posterior_threshold <= self.yellow_posterior_threshold:
            warnings.append(
                f"red_posterior_threshold ({self.red_posterior_threshold}) must exceed "
                f"yellow_posterior_threshold ({self.yellow_posterior_threshold})"
            )

        # Fiscal calendar validation
        if not 1 <= self.fiscal_year_end_month <= 12:
            warnings.append(f"fiscal_year_end_month={self.fiscal_year_end_month} invalid (must be 1-12)")

        if not 1 <= self.fiscal_year_end_day <= 31:
            warnings.append(f"fiscal_year_end_day={self.fiscal_year_end_day} invalid (must be 1-31)")

        for month in self.fiscal_q4_months:
            if not 1 <= month <= 12:
                warnings.append(f"fiscal_q4_months contains invalid month: {month}")

        for month in self.fiscal_safe_months:
            if not 1 <= month <= 12:
                warnings.append(f"fiscal_safe_months contains invalid month: {month}")

        # Currency validation (basic check for 3-letter code)
        if len(self.currency) != 3 or not self.currency.isupper():
            warnings.append(f"currency='{self.currency}' should be 3-letter ISO 4217 code (e.g., 'USD', 'GBP')")

        # FDR alpha validation
        if self.fdr_alpha > 0.10:
            warnings.append(
                f"fdr_alpha={self.fdr_alpha} is unusually high (>10%). "
                f"Values above 0.10 weaken false positive control."
            )

        # Bootstrap validation
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
            "country_code": self.country_code,
            "fiscal_year_end_month": self.fiscal_year_end_month,
            "fiscal_year_end_day": self.fiscal_year_end_day,
            "fiscal_q4_months": self.fiscal_q4_months,
            "fiscal_safe_months": self.fiscal_safe_months,
            "competitive_threshold": self.competitive_threshold,
            "currency": self.currency,
            "mega_contract_threshold": self.mega_contract_threshold,
            "max_award_inflation_pct": self.max_award_inflation_pct,
            "competitive_pricing_tolerance_pct": self.competitive_pricing_tolerance_pct,
            "legal_citations": self.legal_citations,
            "universal_citations": self.universal_citations,
            "oversight_body_names": self.oversight_body_names,
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
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


    @classmethod
    def from_dict(cls, d: dict) -> "JurisdictionProfile":
        """Deserialize from dictionary."""
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})


    def summary(self) -> str:
        """Human-readable summary for audit trail / detection reports."""
        lines = [
            f"Jurisdiction Profile: {self.name}",
            f"  Country: {self.country_code or 'Multi-country'}",
            f"  Currency: {self.currency}",
            f"  Fiscal year ends: Month {self.fiscal_year_end_month}, Day {self.fiscal_year_end_day}",
            f"  Competitive threshold: {self.currency} {self.competitive_threshold:,.0f}",
            f"  Base rate (fraud prior): {self.base_rate:.1%}",
            f"  Evidentiary standard: {self.evidentiary_standard}",
            f"  RED threshold: posterior ≥ {self.red_posterior_threshold:.0%}",
            f"  YELLOW threshold: posterior ≥ {self.yellow_posterior_threshold:.0%}",
            f"  FDR alpha: {self.fdr_alpha}",
        ]
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

# Profiles will be registered here as they are built
# Sub-task 2.2.4a: Only us_federal
# Sub-task 2.2.4b+: Additional jurisdictions

PROFILES: Dict[str, JurisdictionProfile] = {}


def register_profile(profile: JurisdictionProfile) -> None:
    """Register a profile in the global registry."""
    PROFILES[profile.name] = profile


def load_profile(name: str) -> JurisdictionProfile:
    """
    Load a jurisdiction profile by name.

    Args:
        name: Profile identifier (e.g., "us_federal", "uk", "world_bank_africa")

    Returns:
        JurisdictionProfile instance

    Raises:
        ValueError: If profile name not found

    Usage:
        from jurisdiction_profile import load_profile

        profile = load_profile("us_federal")
        fiscal_year_end = profile.fiscal_year_end_month
        threshold = profile.competitive_threshold
    """
    if name not in PROFILES:
        available = ", ".join(sorted(PROFILES.keys()))
        raise ValueError(
            f"Unknown jurisdiction profile '{name}'. "
            f"Available profiles: {available or '(none registered)'}"
        )
    return PROFILES[name]


def list_profiles() -> List[dict]:
    """List all available profiles with basic metadata."""
    return [
        {
            "name": p.name,
            "description": p.description,
            "country_code": p.country_code,
            "currency": p.currency,
            "base_rate": p.base_rate,
        }
        for p in PROFILES.values()
    ]


# ═══════════════════════════════════════════════════════════════════════════
# US FEDERAL PROFILE (Sub-task 2.2.4a)
# ═══════════════════════════════════════════════════════════════════════════

US_FEDERAL = JurisdictionProfile(
    # Identity
    name="us_federal",
    description=(
        "US federal government procurement. Calibrated against DOJ-prosecuted "
        "price fraud cases (9 prosecutions, 100% recall). Conservative prior "
        "based on GAO fraud prevalence estimates. Fiscal year ends September 30. "
        "Evidentiary standard: beyond reasonable doubt (criminal prosecution)."
    ),
    country_code="US",

    # Fiscal calendar (US federal government: October 1 - September 30)
    fiscal_year_end_month=9,  # September
    fiscal_year_end_day=30,
    fiscal_q4_months=[7, 8, 9],  # July, August, September
    fiscal_safe_months=[10, 11, 12, 4, 5, 6],  # Mid-year months, away from Sep 30

    # Procurement thresholds
    competitive_threshold=100_000,  # Current COMPETITIVE_THRESHOLDS["USD"] value
    currency="USD",
    mega_contract_threshold=25_000_000,  # Current institutional_pipeline.py line 106

    # Price variation tolerances
    max_award_inflation_pct=15.0,  # Current FIN-001 threshold (>1.15 = >15%)
    competitive_pricing_tolerance_pct=5.0,  # Current FIN-003 band (0.95-1.05 = ±5%)

    # Legal framework
    legal_citations={
        # --- TCA rule consumers (PROC-001, ENT-001, ENT-002) ---
        "procurement_law": (
            "Federal Acquisition Regulation (FAR) Part 6 — Competition Requirements; "
            "FAR Part 15 — Contracting by Negotiation; "
            "FAR Part 13 — Simplified Acquisition Procedures"
        ),
        "case_authority": (
            "DOJ enforcement precedent: US v. Marquez (D. Md. 2024); "
            "US v. DynCorp (D.D.C. 2005); US v. Oracle Corp. (N.D. Cal. 2011); "
            "US v. Boeing Co. (E.D. Va. 2006); US v. Lockheed Martin (D.D.C. 2008)"
        ),
        # --- CRI _determine_tier() consumers (commit 39b5d65, locked by tests) ---
        "false_claims_law": "31 U.S.C. § 3729(a)(1)(A) - Knowingly presenting false/fraudulent claim",
        "false_records_law": "31 U.S.C. § 3729(a)(1)(B) - Knowingly using false record material to claim",
        "anti_kickback_law": "Anti-Kickback Act 41 U.S.C. § 8702 - Quid pro quo indicator",
        "extreme_markup_precedent": "DOJ prosecution precedent (Oracle, Boeing, Lockheed)",
        # --- Institutional depth keys (not yet consumed by rules) ---
        "foreign_bribery_law": (
            "Foreign Corrupt Practices Act — 15 U.S.C. §§ 78dd-1, 78dd-2, 78dd-3 "
            "(anti-bribery provisions) and 15 U.S.C. § 78m(b)(2) (books and records provisions)"
        ),
        "audit_oversight_law": (
            "Inspector General Act of 1978 (5 U.S.C. App.) and "
            "31 U.S.C. § 3512 — Federal Managers' Financial Integrity Act"
        ),
        "sanctions_debarment_law": (
            "FAR Subpart 9.4 — Debarment, Suspension, and Ineligibility; "
            "Executive Order 12549; "
            "2 C.F.R. Part 180 — OMB Guidelines for Governmentwide Debarment and Suspension (Nonprocurement)"
        ),
        "conflict_of_interest_law": (
            "18 U.S.C. § 208 — Acts affecting a personal financial interest; "
            "41 U.S.C. §§ 2101-2107 — Procurement Integrity Act"
        ),
        "whistleblower_protection_law": (
            "31 U.S.C. § 3730(h) — False Claims Act anti-retaliation; "
            "41 U.S.C. § 4712 — Pilot program for enhancement of contractor protection from reprisal"
        ),
    },
    # universal_citations: uses dataclass default (full UNCAC + OECD list)
    oversight_body_names=[
        "Inspector General",
        "IG",
        "GAO",
        "Government Accountability Office",
        "Office of Inspector General",
    ],

    # CRI statistical calibration (from doj_federal in calibration_config.py)
    global_params_version="us_federal_v0",
    base_rate=0.03,
    evidentiary_standard="beyond_reasonable_doubt",
    red_posterior_threshold=0.72,
    yellow_posterior_threshold=0.38,
    min_typologies_for_red=2,
    min_ci_for_yellow=66,
    fdr_alpha=0.05,
    bootstrap_ci_level=0.95,
    bootstrap_n_resamples=10_000,
    max_flags_per_1k=150,

    # Metadata
    notes=(
        "Original SUNLIGHT calibration profile. Validated against 9 DOJ-prosecuted "
        "procurement fraud cases (100% recall, 37.5% precision, 114.8 flags/1K). "
        "Fiscal year: Oct 1 - Sep 30 (federal government). "
        "Competitive threshold: $100K (current TCA value; FAR Part 6 actual is $250K). "
        "This profile preserves exact DOJ validation baseline behavior."
    ),
    source_citations=[
        "DOJ procurement fraud prosecutions (9 cases, 100% recall)",
        "US Government Accountability Office procurement fraud estimates",
        "FAR Part 6: Competition Requirements",
        "31 USC 1501-1557: Federal fiscal year definition (Oct 1 - Sep 30)",
    ],
)

# Register us_federal profile
register_profile(US_FEDERAL)


# ═══════════════════════════════════════════════════════════════════════════
# UK CENTRAL GOVERNMENT PROFILE (Sub-task 2.2.4d)
# ═══════════════════════════════════════════════════════════════════════════

UK_CENTRAL_GOVERNMENT = JurisdictionProfile(
    # Identity
    name="uk_central_government",
    description=(
        "UK central government procurement. Fiscal year ends March 31. "
        "Governed by Procurement Act 2023 (replacing Public Contracts Regulations 2015). "
        "Evidentiary standard: beyond reasonable doubt (criminal prosecution). "
        "Base rate reflects UK's low corruption context (TI CPI rank ~20th globally)."
    ),
    country_code="GB",

    # Fiscal calendar (UK government: April 1 - March 31)
    fiscal_year_end_month=3,  # March
    fiscal_year_end_day=31,
    fiscal_q4_months=[1, 2, 3],  # January, February, March
    fiscal_safe_months=[8, 9, 10],  # August, September, October (mid-fiscal-year)

    # Procurement thresholds
    competitive_threshold=214_000,  # GBP 214,000 (PCR 2015 Schedule 1, central government)
    currency="GBP",
    mega_contract_threshold=20_000_000,  # GBP 20 million (equivalent to $25M USD)

    # Price variation tolerances
    max_award_inflation_pct=15.0,  # PCR 2015 Reg 72 allows ~10%, using 15% for consistency
    competitive_pricing_tolerance_pct=5.0,  # OECD standard (±5% = 0.95-1.05 ratio)

    # Legal framework
    legal_citations={
        # --- TCA rule consumers (PROC-001, ENT-001, ENT-002) ---
        "procurement_law": (
            "Procurement Act 2023 (effective 24 February 2025); "
            "Public Contracts Regulations 2015 (legacy regulations for pre-2025 contracts); "
            "Concession Contracts Regulations 2016; "
            "Utilities Contracts Regulations 2016"
        ),
        "case_authority": (
            "UK SFO enforcement precedent: R v Rolls-Royce (SFO DPA 2017, £497.3M); "
            "R v Airbus SE (SFO DPA 2020, £991M); "
            "R v Standard Bank (SFO DPA 2015, $32.2M); "
            "R v Tesco (SFO DPA 2017, £129M); "
            "R v Petrofac (Southwark Crown Court conviction 2021, £77M); "
            "SFO v Serco Geografix (SFO DPA 2019, £22.9M)"
        ),
        # --- CRI _determine_tier() consumers (commit 39b5d65, locked by tests) ---
        "false_claims_law": "Fraud Act 2006 s.2 - Fraud by false representation",
        "false_records_law": "Fraud Act 2006 s.3 - Fraud by failing to disclose information",
        "anti_kickback_law": "Bribery Act 2010 s.1 - Bribing another person",
        "extreme_markup_precedent": "UK SFO DPA precedent (Rolls-Royce, Airbus, Tesco)",
        # --- Institutional depth keys (not yet consumed by rules) ---
        "foreign_bribery_law": (
            "Bribery Act 2010 s.6 — Bribery of foreign public officials; "
            "Bribery Act 2010 s.7 — Failure of commercial organisations to prevent bribery; "
            "OECD Anti-Bribery Convention 1997 as implemented by Part 12 of the "
            "Anti-terrorism, Crime and Security Act 2001"
        ),
        "audit_oversight_law": (
            "National Audit Act 1983; "
            "Government Resources and Accounts Act 2000; "
            "Budget Responsibility and National Audit Act 2011 — establishing the "
            "National Audit Office (NAO) and the Comptroller and Auditor General"
        ),
        "sanctions_debarment_law": (
            "Procurement Act 2023 Part 5 — Excluded and Excludable Suppliers; "
            "Procurement Act 2023 s.57-58 — Debarment List; "
            "Cabinet Office Procurement Policy Note on Exclusion and Debarment"
        ),
        "conflict_of_interest_law": (
            "Bribery Act 2010 ss.1-2 — General bribery offences; "
            "Constitutional Reform and Governance Act 2010 — Civil Service Code; "
            "Standards in Public Life — The Seven Principles (Nolan Principles)"
        ),
        "whistleblower_protection_law": (
            "Public Interest Disclosure Act 1998; "
            "Employment Rights Act 1996 Part IVA — Protected Disclosures; "
            "Enterprise and Regulatory Reform Act 2013 s.17 — Disclosures in the public interest"
        ),
    },
    # universal_citations: uses dataclass default (full UNCAC + OECD list)
    oversight_body_names=[
        # Empty for now (matches US_FEDERAL pattern)
        # Will populate when PROC-003/PROC-004 oversight detection implemented
    ],

    # CRI statistical calibration (GLOBAL parameters — match US_FEDERAL until sub-task 2.2.6)
    global_params_version="us_federal_v0",
    base_rate=0.025,  # 2.5% (UK NAO estimate, lower than US federal 3%)
    evidentiary_standard="beyond_reasonable_doubt",  # UK criminal standard
    red_posterior_threshold=0.72,  # Same as US_FEDERAL (global parameter)
    yellow_posterior_threshold=0.38,  # Same as US_FEDERAL (global parameter)
    min_typologies_for_red=2,  # Same as US_FEDERAL (global parameter)
    min_ci_for_yellow=66,  # Same as US_FEDERAL (global parameter)
    fdr_alpha=0.05,  # Same as US_FEDERAL (global parameter)
    bootstrap_ci_level=0.95,  # Same as US_FEDERAL (global parameter)
    bootstrap_n_resamples=10_000,  # Same as US_FEDERAL (global parameter)
    max_flags_per_1k=150,  # Same as US_FEDERAL (global parameter)

    # Metadata
    notes=(
        "First non-US jurisdiction profile. Validates jurisdiction profile architecture "
        "for second major legal framework. UK fiscal year ends March 31 (not Sep 30). "
        "Competitive threshold £214,000 (not $100K USD). Governed by Procurement Act 2023 "
        "(replaced EU-derived PCR 2015 post-Brexit). Base rate 2.5% reflects UK's low-corruption "
        "context (TI CPI rank ~20th). Statistical parameters match US_FEDERAL pending "
        "multi-jurisdiction calibration (sub-task 2.2.6)."
    ),
    source_citations=[
        "UK Procurement Act 2023 (c. 54)",
        "The Public Contracts Regulations 2015 (SI 2015/102) Schedule 1",
        "HM Treasury Managing Public Money Annex 2.1",
        "Competition Act 1998 (c. 41)",
        "UK Serious Fraud Office prosecution records 2015-2025",
        "Transparency International Corruption Perceptions Index 2024",
        "OECD Public Procurement Principles",
    ],
)

# Register uk_central_government profile
register_profile(UK_CENTRAL_GOVERNMENT)


# ═══════════════════════════════════════════════════════════════════════════
# WORLD BANK INT PROFILE (Phase E item 32)
# ═══════════════════════════════════════════════════════════════════════════

WB_INT = JurisdictionProfile(
    # Identity
    name="wb_int",
    description=(
        "World Bank Group — Integrity Vice Presidency. Covers procurement under "
        "IBRD/IDA-financed investment project financing (IPF). Contract values in USD "
        "for cross-country comparability. WB fiscal year runs July 1 – June 30. "
        "Evidentiary standard: more likely than not (WB Sanctions Board "
        "civil-administrative standard, distinct from US DOJ criminal standard). "
        "Base rate 4% reflects WB's developing-country operational footprint."
    ),
    country_code="INT",  # International — WB INT operates across all WB borrower countries

    # Fiscal calendar (World Bank Group: July 1 – June 30)
    fiscal_year_end_month=6,  # June
    fiscal_year_end_day=30,
    fiscal_q4_months=[4, 5, 6],  # April, May, June
    fiscal_safe_months=[7, 8, 9, 10, 11, 12, 1, 2, 3],  # All months outside fiscal Q4

    # Procurement thresholds
    competitive_threshold=250_000,  # USD 250K ICB threshold for goods (WB Procurement Regulations)
    currency="USD",
    mega_contract_threshold=10_000_000,  # USD 10M — additional scrutiny per INT enforcement patterns

    # Price variation tolerances
    max_award_inflation_pct=15.0,  # WB Procurement Regulations standard
    competitive_pricing_tolerance_pct=20.0,  # ±20% — broader tolerance for developing-country context

    # Legal framework
    legal_citations={
        # --- TCA rule consumers (PROC-001, ENT-001, ENT-002) ---
        "procurement_law": (
            "World Bank Procurement Regulations for IPF Borrowers "
            "(July 2016, revised November 2020 and September 2023); "
            "World Bank Anti-Corruption Guidelines for IBRD and IDA Financed Projects "
            "(revised January 2011); "
            "World Bank Consultant Guidelines (revised 2014)"
        ),
        "case_authority": (
            "World Bank Sanctions Board enforcement precedent: "
            "SNC-Lavalin (2013 Padma Bridge, 10-year debarment); "
            "Alstom Hydro France (2012 Zambia, USD 9.5M restitution); "
            "Siemens AG (2009 global settlement, USD 100M anti-corruption payment); "
            "Macmillan Limited (2010 Sudan MDTF education, 6-year debarment)"
        ),
        # --- CRI _determine_tier() consumers ---
        "false_claims_law": (
            "World Bank Anti-Corruption Guidelines § 1(a)(iv) — 'Fraudulent practice' "
            "defined as any act or omission, including misrepresentation, that knowingly "
            "or recklessly misleads or attempts to mislead a party to obtain a financial "
            "or other benefit or to avoid an obligation; "
            "WB Sanctions Procedures § III.A.3"
        ),
        "false_records_law": (
            "World Bank Procurement Regulations Annex IV (IV.4) — misrepresentation in "
            "bid documents and financial statements; "
            "WB Anti-Corruption Guidelines § 1(a)(iv) — knowingly or recklessly false "
            "representation in a financial context"
        ),
        "anti_kickback_law": (
            "World Bank Anti-Corruption Guidelines § 1(a)(i) — 'Corrupt practice' "
            "defined as offering, giving, receiving, or soliciting of anything of value "
            "to influence improperly the actions of another party; "
            "WB Sanctions Procedures § III.A.1"
        ),
        "extreme_markup_precedent": (
            "World Bank Sanctions Board precedent on sanctionable misrepresentation "
            "and overcharging: SNC-Lavalin Inc. Padma Bridge (2013, 10-year debarment, "
            "longest in WB history at time of imposition); "
            "Alstom Hydro France (2012, Zambia Kariba North hydropower, misconduct "
            "under IBRD-financed project)"
        ),
        # --- Institutional depth keys ---
        "foreign_bribery_law": (
            "UNCAC Art. 16 — Bribery of foreign public officials and officials of "
            "public international organizations (Article 16 specifically covers bribery "
            "of international organization officials, which includes WB staff); "
            "OECD Anti-Bribery Convention 1997 as incorporated into WB Anti-Corruption "
            "Guidelines § 1(a)(i); "
            "World Bank Staff Rule 03.01 — Standards of Professional Conduct"
        ),
        "audit_oversight_law": (
            "World Bank Integrity Vice Presidency (INT) mandate under President's "
            "Memorandum; WB Internal Audit Vice Presidency (IAD); "
            "Independent Evaluation Group (IEG) charter; "
            "WB Sanctions System consisting of the Office of Suspension and Debarment "
            "(OSD) and the WB Group Sanctions Board (SB)"
        ),
        "sanctions_debarment_law": (
            "World Bank Sanctions Procedures (2011, revised 2016); "
            "World Bank Group Sanctioning Guidelines; "
            "Agreement for Mutual Enforcement of Debarment Decisions among the African "
            "Development Bank, Asian Development Bank, European Bank for Reconstruction "
            "and Development, Inter-American Development Bank, and World Bank Group "
            "(9 April 2010); "
            "WB Integrity Compliance Officer (ICO) Terms of Reference"
        ),
        "conflict_of_interest_law": (
            "WB Staff Rule 03.01 — Standards of Professional Conduct; "
            "WB Staff Rule 03.02 — Conflicts of Interest; "
            "WB Procurement Regulations § 3.16 — Conflict of Interest "
            "(borrowers' procurement staff); "
            "WB Code of Conduct for Bank Group Staff"
        ),
        "whistleblower_protection_law": (
            "WB Staff Rule 08.02 — Whistleblower Protection for Bank Staff; "
            "WB INT Reporting Mechanism (integrity complaints line); "
            "WB Ethics Helpline — protected disclosure framework"
        ),
    },
    # universal_citations: uses dataclass default (full UNCAC + OECD list)
    oversight_body_names=[
        "Integrity Vice Presidency",
        "INT",
        "Sanctions Board",
        "Office of Suspension and Debarment",
        "OSD",
        "Independent Evaluation Group",
        "IEG",
    ],

    # CRI statistical calibration (GLOBAL parameters — referencing mjpis_draft_v0)
    global_params_version="mjpis_draft_v0",
    base_rate=0.04,  # 4% — higher than US/UK given WB developing-country footprint
    evidentiary_standard="more_likely_than_not",  # WB Sanctions Board civil-administrative standard
    red_posterior_threshold=0.72,  # mjpis_draft_v0 value (pending WB-specific calibration)
    yellow_posterior_threshold=0.38,  # mjpis_draft_v0 value (pending WB-specific calibration)
    min_typologies_for_red=2,  # mjpis_draft_v0 value
    min_ci_for_yellow=66,  # mjpis_draft_v0 value
    fdr_alpha=0.05,  # mjpis_draft_v0 value
    bootstrap_ci_level=0.95,  # mjpis_draft_v0 value
    bootstrap_n_resamples=10_000,  # Production standard
    max_flags_per_1k=150,  # mjpis_draft_v0 value

    # Metadata
    notes=(
        "Third jurisdiction profile. Covers World Bank Group IPF procurement under "
        "INT oversight. WB INT uses the MJPIS living standard (mjpis_draft_v0) rather "
        "than a WB-specific isolated calibration, consistent with WB INT's role as one "
        "of the four MJPIS intersection jurisdictions. Base rate 4% derived from INT's "
        "historical sanctions rate across WB borrower countries. Evidentiary standard "
        "'more_likely_than_not' is the WB Sanctions Board's civil-administrative standard "
        "(functionally equivalent to 'balance of probabilities' but institutionally distinct). "
        "Statistical thresholds match mjpis_draft_v0 pending WB-specific calibration in "
        "future sub-task."
    ),
    source_citations=[
        "World Bank Procurement Regulations for IPF Borrowers (July 2016, rev. Nov 2020, Sep 2023)",
        "World Bank Anti-Corruption Guidelines for IBRD/IDA Financed Projects (rev. Jan 2011)",
        "World Bank Sanctions Procedures (2011, rev. 2016)",
        "World Bank Group Sanctioning Guidelines",
        "Agreement for Mutual Enforcement of Debarment Decisions (9 April 2010)",
        "World Bank INT Annual Reports 2013-2023",
        "World Bank Sanctions Board decisions: SNC-Lavalin, Alstom, Siemens, Macmillan",
    ],
)

# Register wb_int profile
register_profile(WB_INT)


# ═══════════════════════════════════════════════════════════════════════════
# FRANCE PNF PROFILE (Phase E item 33)
# ═══════════════════════════════════════════════════════════════════════════

FRANCE_PNF = JurisdictionProfile(
    # Identity
    name="france_pnf",
    description=(
        "France — Parquet National Financier. Covers procurement under French public "
        "contract law (Code de la commande publique) and EU procurement directives as "
        "transposed into French law. EUR currency, calendar-year fiscal alignment. "
        "Evidentiary standard: french_cjip_admission_of_facts (corporate admission of "
        "facts and acceptance of penal characterization under Article 41-1-2 CPP). "
        "Base rate 2.5% reflects France's mature prosecution context (TI CPI parity "
        "with UK). Loi Sapin II (2016) provides the overarching anti-corruption framework."
    ),
    country_code="FR",

    # Fiscal calendar (French public bodies: January 1 – December 31)
    fiscal_year_end_month=12,  # December
    fiscal_year_end_day=31,
    fiscal_q4_months=[10, 11, 12],  # October, November, December
    fiscal_safe_months=[1, 2, 3, 4, 5, 6, 7, 8, 9],  # All months outside fiscal Q4

    # Procurement thresholds
    competitive_threshold=143_000,  # EUR 143K — formalized-procedure threshold (Code de la commande publique, EU Directive 2014/24/EU)
    currency="EUR",
    mega_contract_threshold=5_350_000,  # EUR 5.35M — EU Directive works threshold for maximum procedural scrutiny

    # Price variation tolerances
    max_award_inflation_pct=15.0,  # EU/French standard
    competitive_pricing_tolerance_pct=20.0,  # ±20% — same default as UK and WB_INT pending MJPIS calibration

    # Legal framework
    legal_citations={
        # --- TCA rule consumers (PROC-001, ENT-001, ENT-002) ---
        "procurement_law": (
            "Code de la commande publique (Ordonnance n° 2018-1074 du 26 novembre 2018, "
            "consolidated 2024); "
            "Directive 2014/24/UE relative à la passation des marchés publics "
            "(transposed into French law); "
            "Directive 2014/25/UE (utilities sector); "
            "Loi n° 2016-1691 du 9 décembre 2016 relative à la transparence, à la lutte "
            "contre la corruption et à la modernisation de la vie économique (Sapin II)"
        ),
        "case_authority": (
            "Parquet National Financier enforcement precedent: "
            "Airbus SE (CJIP 2020, EUR 2.083B global resolution with DOJ/SFO); "
            "Bolloré (CJIP 2021, EUR 12M Togo ports); "
            "Société Générale (CJIP 2018, EUR 250.15M Libya sovereign wealth fund); "
            "Egis Avia (CJIP 2019, EUR 2.6M Algeria airport terminal); "
            "Bouygues Bâtiment Sud Est / Linkcity Sud Est (CJIP 2023, EUR 7.964M "
            "Centre Hospitalier Annecy Genevois procurement favoritism); "
            "Airbus SE (CJIP 2022, EUR 15.856M Libya/Kazakhstan/IPA follow-on)"
        ),
        # --- CRI _determine_tier() consumers ---
        "false_claims_law": (
            "Code pénal Art. 441-1 — Faux (forgery and use of false documents); "
            "Code pénal Art. 441-6 — Fourniture frauduleuse de document "
            "(fraudulent provision of documents); "
            "Code pénal Art. 313-1 — Escroquerie (fraud)"
        ),
        "false_records_law": (
            "Code pénal Art. 441-1 — Faux et usage de faux (forgery and use of forgery); "
            "Code pénal Art. 441-2 — Faux en écriture publique (forgery in public records); "
            "Code de commerce L. 242-6 — Présentation de comptes annuels ne donnant pas "
            "une image fidèle (presenting accounts that do not give a true and fair view)"
        ),
        "anti_kickback_law": (
            "Code pénal Art. 433-1 — Corruption active d'agent public "
            "(active bribery of French public officials); "
            "Code pénal Art. 432-11 — Corruption passive et trafic d'influence par "
            "personne exerçant une fonction publique (passive bribery and trading in "
            "influence by public officials); "
            "Code pénal Art. 433-2 — Trafic d'influence par particuliers "
            "(trading in influence by private persons)"
        ),
        "extreme_markup_precedent": (
            "PNF CJIP precedent on extreme overcharging and disgorgement: "
            "Airbus SE 2020 (EUR 2.083B, largest French anti-bribery settlement); "
            "Société Générale 2018 (EUR 250.15M, USD 90M in bribes over USD 3.66B "
            "of investments, channel ratio 2.46%); "
            "Bolloré 2021 (EUR 12M, Togo ports concession); "
            "Egis Avia 2019 (EUR 2.6M, disgorgement calculated as margin plus "
            "intermediary commissions)"
        ),
        # --- Institutional depth keys ---
        "foreign_bribery_law": (
            "Code pénal Art. 435-3 — Corruption active d'agent public étranger "
            "(active bribery of foreign public officials); "
            "Code pénal Art. 435-4 — Corruption passive d'agent public étranger; "
            "Loi Sapin II (Loi n° 2016-1691 du 9 décembre 2016) — French transposition "
            "of OECD Anti-Bribery Convention 1997; "
            "Convention des Nations Unies contre la corruption (UNCAC) — ratified by "
            "France 11 July 2005"
        ),
        "audit_oversight_law": (
            "Cour des comptes (French Court of Accounts) — constitutional audit "
            "institution under Articles 47-2 and L. 111-1 Code des juridictions "
            "financières; "
            "Chambres régionales des comptes (Regional Courts of Accounts); "
            "Haute Autorité pour la transparence de la vie publique (HATVP); "
            "Agence française anticorruption (AFA) — established by Loi Sapin II, "
            "Articles 1-5"
        ),
        "sanctions_debarment_law": (
            "Code de la commande publique L. 2141-1 à L. 2141-11 — Exclusions "
            "obligatoires et facultatives (mandatory and optional exclusions from "
            "public contracts); "
            "Directive 2014/24/UE Art. 57 — Grounds for exclusion; "
            "Code pénal Art. 131-39 — Peines applicables aux personnes morales incluant "
            "l'exclusion des marchés publics (penalties applicable to legal persons "
            "including exclusion from public contracts)"
        ),
        "conflict_of_interest_law": (
            "Code pénal Art. 432-12 — Prise illégale d'intérêts (unlawful taking of "
            "interests by public officials); "
            "Code pénal Art. 432-13 — Pantouflage (illegal post-public-service private "
            "employment restrictions); "
            "Loi n° 2013-907 du 11 octobre 2013 relative à la transparence de la vie "
            "publique — Déontologie et déclarations d'intérêts; "
            "Charte de déontologie des agents publics"
        ),
        "whistleblower_protection_law": (
            "Loi n° 2016-1691 du 9 décembre 2016 (Sapin II) Chapitre II Articles 6-16 "
            "— Protection des lanceurs d'alerte (whistleblower protection); "
            "Loi n° 2022-401 du 21 mars 2022 améliorant la protection des lanceurs "
            "d'alerte (transposition of EU Directive 2019/1937); "
            "Défenseur des droits — autorité compétente pour les signalements"
        ),
    },
    # universal_citations: uses dataclass default (full UNCAC + OECD list)
    oversight_body_names=[
        "Agence française anticorruption",
        "AFA",
        "Cour des comptes",
        "Haute Autorité pour la transparence de la vie publique",
        "HATVP",
        "Parquet National Financier",
        "PNF",
    ],

    # CRI statistical calibration (GLOBAL parameters — referencing mjpis_draft_v0)
    global_params_version="mjpis_draft_v0",
    base_rate=0.025,  # 2.5% — France/UK TI CPI parity
    evidentiary_standard="french_cjip_admission_of_facts",  # PNF CJIP standard under Art. 41-1-2 CPP
    red_posterior_threshold=0.72,  # mjpis_draft_v0 value (pending FR-specific calibration)
    yellow_posterior_threshold=0.38,  # mjpis_draft_v0 value (pending FR-specific calibration)
    min_typologies_for_red=2,  # mjpis_draft_v0 value
    min_ci_for_yellow=66,  # mjpis_draft_v0 value
    fdr_alpha=0.05,  # mjpis_draft_v0 value
    bootstrap_ci_level=0.95,  # mjpis_draft_v0 value
    bootstrap_n_resamples=10_000,  # Production standard
    max_flags_per_1k=150,  # mjpis_draft_v0 value

    # Metadata
    notes=(
        "Fourth jurisdiction profile — completes MJPIS operational coverage. Covers "
        "French public procurement under Code de la commande publique and EU directives. "
        "Loi Sapin II (2016) is the overarching anti-corruption framework. PNF's CJIP "
        "standard ('french_cjip_admission_of_facts') requires corporate admission of facts "
        "and acceptance of penal characterization under Article 41-1-2 CPP — distinct from "
        "US plea, UK DPA, and WB administrative standards. Base rate 2.5% reflects France's "
        "mature prosecution context (TI CPI ~21st globally, parity with UK). Statistical "
        "thresholds match mjpis_draft_v0 pending FR-specific calibration."
    ),
    source_citations=[
        "Code de la commande publique (Ordonnance n° 2018-1074 du 26 novembre 2018)",
        "Directive 2014/24/UE du 26 février 2014 — Passation des marchés publics",
        "Loi n° 2016-1691 du 9 décembre 2016 (Sapin II)",
        "Code pénal — Livre IV, Titre III (Des atteintes à l'autorité de l'État)",
        "Parquet National Financier CJIP records 2017-2023",
        "Agence française anticorruption annual reports",
        "Transparency International Corruption Perceptions Index 2024",
    ],
)

# Register france_pnf profile
register_profile(FRANCE_PNF)


# ═══════════════════════════════════════════════════════════════════════════
# IMPORT-TIME SANITY CHECK: Global parameters registry consistency
# ═══════════════════════════════════════════════════════════════════════════

# Verify that the global parameters registry values match the legacy profile fields
# This import-time assertion guarantees consistency during the migration period
# If registry and legacy fields drift, the module fails to load (correct failure mode)

from global_parameters import get_global_parameters

_US_FEDERAL_GLOBAL = get_global_parameters(US_FEDERAL.global_params_version)
assert _US_FEDERAL_GLOBAL.red_posterior_threshold == US_FEDERAL.red_posterior_threshold, \
    f"us_federal_v0 red_posterior_threshold mismatch: registry={_US_FEDERAL_GLOBAL.red_posterior_threshold}, profile={US_FEDERAL.red_posterior_threshold}"
assert _US_FEDERAL_GLOBAL.yellow_posterior_threshold == US_FEDERAL.yellow_posterior_threshold, \
    f"us_federal_v0 yellow_posterior_threshold mismatch: registry={_US_FEDERAL_GLOBAL.yellow_posterior_threshold}, profile={US_FEDERAL.yellow_posterior_threshold}"
assert _US_FEDERAL_GLOBAL.fdr_alpha == US_FEDERAL.fdr_alpha, \
    f"us_federal_v0 fdr_alpha mismatch: registry={_US_FEDERAL_GLOBAL.fdr_alpha}, profile={US_FEDERAL.fdr_alpha}"
assert _US_FEDERAL_GLOBAL.bootstrap_n_resamples == US_FEDERAL.bootstrap_n_resamples, \
    f"us_federal_v0 bootstrap_n_resamples mismatch: registry={_US_FEDERAL_GLOBAL.bootstrap_n_resamples}, profile={US_FEDERAL.bootstrap_n_resamples}"

_UK_CENTRAL_GLOBAL = get_global_parameters(UK_CENTRAL_GOVERNMENT.global_params_version)
assert _UK_CENTRAL_GLOBAL.red_posterior_threshold == UK_CENTRAL_GOVERNMENT.red_posterior_threshold, \
    f"UK profile red_posterior_threshold mismatch: registry={_UK_CENTRAL_GLOBAL.red_posterior_threshold}, profile={UK_CENTRAL_GOVERNMENT.red_posterior_threshold}"
assert _UK_CENTRAL_GLOBAL.yellow_posterior_threshold == UK_CENTRAL_GOVERNMENT.yellow_posterior_threshold, \
    f"UK profile yellow_posterior_threshold mismatch: registry={_UK_CENTRAL_GLOBAL.yellow_posterior_threshold}, profile={UK_CENTRAL_GOVERNMENT.yellow_posterior_threshold}"

_WB_INT_GLOBAL = get_global_parameters(WB_INT.global_params_version)
assert _WB_INT_GLOBAL.red_posterior_threshold == WB_INT.red_posterior_threshold, \
    f"WB_INT red_posterior_threshold mismatch: registry={_WB_INT_GLOBAL.red_posterior_threshold}, profile={WB_INT.red_posterior_threshold}"
assert _WB_INT_GLOBAL.yellow_posterior_threshold == WB_INT.yellow_posterior_threshold, \
    f"WB_INT yellow_posterior_threshold mismatch: registry={_WB_INT_GLOBAL.yellow_posterior_threshold}, profile={WB_INT.yellow_posterior_threshold}"
assert _WB_INT_GLOBAL.fdr_alpha == WB_INT.fdr_alpha, \
    f"WB_INT fdr_alpha mismatch: registry={_WB_INT_GLOBAL.fdr_alpha}, profile={WB_INT.fdr_alpha}"
assert _WB_INT_GLOBAL.bootstrap_n_resamples == WB_INT.bootstrap_n_resamples, \
    f"WB_INT bootstrap_n_resamples mismatch: registry={_WB_INT_GLOBAL.bootstrap_n_resamples}, profile={WB_INT.bootstrap_n_resamples}"

_FRANCE_PNF_GLOBAL = get_global_parameters(FRANCE_PNF.global_params_version)
assert _FRANCE_PNF_GLOBAL.red_posterior_threshold == FRANCE_PNF.red_posterior_threshold, \
    f"FRANCE_PNF red_posterior_threshold mismatch: registry={_FRANCE_PNF_GLOBAL.red_posterior_threshold}, profile={FRANCE_PNF.red_posterior_threshold}"
assert _FRANCE_PNF_GLOBAL.yellow_posterior_threshold == FRANCE_PNF.yellow_posterior_threshold, \
    f"FRANCE_PNF yellow_posterior_threshold mismatch: registry={_FRANCE_PNF_GLOBAL.yellow_posterior_threshold}, profile={FRANCE_PNF.yellow_posterior_threshold}"
assert _FRANCE_PNF_GLOBAL.fdr_alpha == FRANCE_PNF.fdr_alpha, \
    f"FRANCE_PNF fdr_alpha mismatch: registry={_FRANCE_PNF_GLOBAL.fdr_alpha}, profile={FRANCE_PNF.fdr_alpha}"
assert _FRANCE_PNF_GLOBAL.bootstrap_n_resamples == FRANCE_PNF.bootstrap_n_resamples, \
    f"FRANCE_PNF bootstrap_n_resamples mismatch: registry={_FRANCE_PNF_GLOBAL.bootstrap_n_resamples}, profile={FRANCE_PNF.bootstrap_n_resamples}"


# ═══════════════════════════════════════════════════════════════════════════
# CLI: Print profile summary
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 72)
    print("SUNLIGHT Jurisdiction Profiles")
    print("=" * 72)
    for profile in PROFILES.values():
        print()
        print(profile.summary())
        warnings = profile.validate()
        if warnings:
            print()
            for w in warnings:
                print(f"  ⚠ WARNING: {w}")
    print()
    print("=" * 72)
    print(f"Total profiles registered: {len(PROFILES)}")
    print(f"Available profiles: {', '.join(sorted(PROFILES.keys()))}")
