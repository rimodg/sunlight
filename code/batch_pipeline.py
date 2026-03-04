"""
SUNLIGHT Batch Analysis Pipeline

Processes a full OCDS dataset through the complete CRI indicator suite:
1. Extract fields from all releases
2. Run per-contract indicators (single bidding, tender period, procedure, decision, amendments)
3. Compute buyer-level indicators (concentration, split purchases)
4. Merge per-contract and buyer-level results
5. Compute composite CRI per contract
6. Produce ranked, scored output with country risk profile

This is the "infrastructure" layer — OCDS in, scored intelligence out.

Usage:
    pipeline = BatchPipeline(jurisdiction_config={...})
    results = pipeline.analyze(releases)
    results.export_csv("output.csv")
    print(results.country_profile)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional
from datetime import datetime, timezone
import json
import csv
import math
import logging

from ocds_field_extractor import extract_release, extract_releases, ExtractedRelease
from cri_indicators import (
    single_bidding,
    tender_period_risk,
    procedure_type_risk,
    decision_period_risk,
    amendment_risk,
    detect_split_purchases,
    buyer_concentration,
    compute_cri,
    combined_likelihood_ratio,
    IndicatorResult,
    CRIResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jurisdiction configuration
# ---------------------------------------------------------------------------

@dataclass
class JurisdictionConfig:
    """Configurable thresholds per jurisdiction."""
    country_code: str = "XX"
    country_name: str = "Unknown"
    currency: str = "USD"
    # Tender period minimum (days)
    tender_period_minimum: float = 15.0
    # Procurement threshold for split purchase detection
    procurement_threshold: float = 10000.0
    # Buyer concentration threshold
    concentration_threshold: float = 0.40
    # CRI tier thresholds
    cri_red_threshold: float = 0.50
    cri_yellow_threshold: float = 0.25
    # Minimum indicators for valid CRI
    min_indicators: int = 3


# Pre-built configs for common jurisdictions
JURISDICTION_CONFIGS = {
    "GB": JurisdictionConfig(
        country_code="GB", country_name="United Kingdom", currency="GBP",
        tender_period_minimum=10.0, procurement_threshold=12000.0,
    ),
    "SN": JurisdictionConfig(
        country_code="SN", country_name="Senegal", currency="XOF",
        tender_period_minimum=15.0, procurement_threshold=5000000.0,  # ~5M XOF
    ),
    "CO": JurisdictionConfig(
        country_code="CO", country_name="Colombia", currency="COP",
        tender_period_minimum=10.0, procurement_threshold=50000000.0,  # ~50M COP
    ),
    "PY": JurisdictionConfig(
        country_code="PY", country_name="Paraguay", currency="PYG",
        tender_period_minimum=15.0, procurement_threshold=50000000.0,
    ),
    "UA": JurisdictionConfig(
        country_code="UA", country_name="Ukraine", currency="UAH",
        tender_period_minimum=15.0, procurement_threshold=50000.0,
    ),
    "EC": JurisdictionConfig(
        country_code="EC", country_name="Ecuador", currency="USD",
        tender_period_minimum=7.0, procurement_threshold=7105.43,
    ),
    "DO": JurisdictionConfig(
        country_code="DO", country_name="Dominican Republic", currency="DOP",
        tender_period_minimum=10.0, procurement_threshold=500000.0,
    ),
    "MX": JurisdictionConfig(
        country_code="MX", country_name="Mexico", currency="MXN",
        tender_period_minimum=15.0, procurement_threshold=300000.0,
    ),
}


# ---------------------------------------------------------------------------
# Per-contract scored result
# ---------------------------------------------------------------------------

@dataclass
class ContractScore:
    """Scored result for a single contract."""
    ocid: str
    release_id: str
    buyer_id: Optional[str]
    buyer_name: Optional[str]
    supplier_id: Optional[str]
    supplier_name: Optional[str]
    award_value: Optional[float]
    currency: Optional[str]
    procurement_method: Optional[str]
    # CRI results
    cri_score: Optional[float]
    cri_tier: str
    n_indicators_available: int
    n_indicators_flagged: int
    # Individual indicator flags
    single_bidding_flag: Optional[int]
    tender_period_flag: Optional[int]
    procedure_type_flag: Optional[int]
    decision_period_flag: Optional[int]
    amendment_flag: Optional[int]
    buyer_concentration_flag: Optional[int]
    # Combined Bayesian evidence
    combined_lr: float
    # Raw data for investigation
    number_of_tenderers: Optional[int]
    tender_period_days: Optional[float]
    decision_period_days: Optional[float]
    amendment_count: int
    # Indicator explanations
    explanations: list[str]
    # Item classification
    main_classification: Optional[str]
    # Data coverage
    fields_present: int
    fields_missing: int

    def to_dict(self) -> dict:
        return {
            "ocid": self.ocid,
            "buyer_id": self.buyer_id,
            "buyer_name": self.buyer_name,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier_name,
            "award_value": self.award_value,
            "currency": self.currency,
            "procurement_method": self.procurement_method,
            "cri_score": self.cri_score,
            "cri_tier": self.cri_tier,
            "n_indicators_flagged": self.n_indicators_flagged,
            "n_indicators_available": self.n_indicators_available,
            "single_bidding": self.single_bidding_flag,
            "tender_period": self.tender_period_flag,
            "procedure_type": self.procedure_type_flag,
            "decision_period": self.decision_period_flag,
            "amendment": self.amendment_flag,
            "buyer_concentration": self.buyer_concentration_flag,
            "combined_lr": self.combined_lr,
            "number_of_tenderers": self.number_of_tenderers,
            "tender_period_days": self.tender_period_days,
            "decision_period_days": self.decision_period_days,
            "amendment_count": self.amendment_count,
            "main_classification": self.main_classification,
        }


# ---------------------------------------------------------------------------
# Country risk profile
# ---------------------------------------------------------------------------

@dataclass
class CountryProfile:
    """Aggregate risk statistics for a jurisdiction."""
    country_code: str
    country_name: str
    total_contracts: int
    total_value: float
    currency: str
    # CRI distribution
    mean_cri: Optional[float]
    median_cri: Optional[float]
    cri_std: Optional[float]
    # Tier counts
    red_count: int
    yellow_count: int
    green_count: int
    gray_count: int
    # Indicator prevalence (% of contracts with data where indicator fires)
    single_bidding_rate: Optional[float]
    non_competitive_rate: Optional[float]
    short_tender_rate: Optional[float]
    amendment_rate: Optional[float]
    # Data quality
    avg_indicators_available: float
    # Top risk buyers
    top_risk_buyers: list[dict]
    # Top risk contracts
    top_risk_contracts: list[dict]

    def summary(self) -> str:
        lines = [
            f"═══ COUNTRY RISK PROFILE: {self.country_name} ({self.country_code}) ═══",
            f"Total contracts analyzed: {self.total_contracts}",
            f"Total value: {self.total_value:,.0f} {self.currency}",
            "",
            f"CRI Distribution:",
        ]
        if self.mean_cri is not None:
            lines.append(f"  Mean:   {self.mean_cri:.3f}")
            lines.append(f"  Median: {self.median_cri:.3f}")
            lines.append(f"  Std:    {self.cri_std:.3f}")
        lines += [
            "",
            f"Tier Classification:",
            f"  RED:    {self.red_count} ({self.red_count/self.total_contracts:.1%})",
            f"  YELLOW: {self.yellow_count} ({self.yellow_count/self.total_contracts:.1%})",
            f"  GREEN:  {self.green_count} ({self.green_count/self.total_contracts:.1%})",
            f"  GRAY:   {self.gray_count} ({self.gray_count/self.total_contracts:.1%})",
            "",
            f"Indicator Prevalence:",
        ]
        if self.single_bidding_rate is not None:
            lines.append(f"  Single bidding rate: {self.single_bidding_rate:.1%}")
        if self.non_competitive_rate is not None:
            lines.append(f"  Non-competitive procedure rate: {self.non_competitive_rate:.1%}")
        if self.short_tender_rate is not None:
            lines.append(f"  Short tender period rate: {self.short_tender_rate:.1%}")
        if self.amendment_rate is not None:
            lines.append(f"  Amendment flag rate: {self.amendment_rate:.1%}")
        lines += [
            "",
            f"Data Quality: avg {self.avg_indicators_available:.1f} indicators available per contract",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Batch Pipeline
# ---------------------------------------------------------------------------

class BatchPipeline:
    """
    The full SUNLIGHT analysis pipeline.

    OCDS releases in → scored, tiered, explained contract scores out.
    """

    def __init__(self, config: Optional[JurisdictionConfig] = None):
        self.config = config or JurisdictionConfig()
        self.extracted: list[ExtractedRelease] = []
        self.scores: list[ContractScore] = []
        self.profile: Optional[CountryProfile] = None

    def analyze(self, releases: list[dict]) -> "BatchPipeline":
        """Run complete analysis on OCDS releases."""
        logger.info(f"Analyzing {len(releases)} releases for {self.config.country_name}")

        # Step 1: Extract
        all_extracted = extract_releases(releases)
        logger.info(f"Extracted {len(all_extracted)} releases")

        # Step 1b: Deduplicate by OCID — keep latest release per contracting process
        ocid_map = {}
        for ex in all_extracted:
            key = ex.ocid or ex.release_id
            existing = ocid_map.get(key)
            if existing is None:
                ocid_map[key] = ex
            elif len(ex.fields_present) > len(existing.fields_present):
                ocid_map[key] = ex
            elif len(ex.fields_present) == len(existing.fields_present):
                if ex.release_date and existing.release_date and ex.release_date > existing.release_date:
                    ocid_map[key] = ex
        self.extracted = list(ocid_map.values())
        logger.info(f"Deduplicated to {len(self.extracted)} unique contracting processes")

        # Step 2: Compute buyer-level metrics
        buyer_supplier_values, buyer_contract_counts = self._aggregate_buyer_suppliers()
        buyer_concentration_results = {}
        min_buyer_contracts = 5
        for buyer_id, supplier_vals in buyer_supplier_values.items():
            if buyer_contract_counts.get(buyer_id, 0) < min_buyer_contracts:
                buyer_concentration_results[buyer_id] = IndicatorResult(
                    indicator_name="buyer_concentration",
                    flag=None,
                    likelihood_ratio=1.0,
                    explanation=f"Buyer {buyer_id} has only {buyer_contract_counts.get(buyer_id, 0)} contracts — need {min_buyer_contracts} for concentration analysis",
                    data={"buyer_id": buyer_id}
                )
            else:
                buyer_concentration_results[buyer_id] = buyer_concentration(
                    buyer_id=buyer_id,
                    supplier_contracts=supplier_vals,
                    concentration_threshold=self.config.concentration_threshold,
                )

        # Step 3: Score each contract
        self.scores = []
        for ex in self.extracted:
            score = self._score_contract(ex, buyer_concentration_results)
            self.scores.append(score)

        # Step 4: Compute country profile
        self.profile = self._compute_profile()

        logger.info(f"Analysis complete. {len(self.scores)} contracts scored.")
        return self

    def _aggregate_buyer_suppliers(self):
        """Aggregate {buyer_id: {supplier_id: total_value}} and {buyer_id: contract_count}."""
        values = defaultdict(lambda: defaultdict(float))
        counts = defaultdict(int)
        for ex in self.extracted:
            if ex.buyer_id and ex.award_supplier_id:
                value = ex.award_value or ex.contract_value or 0
                values[ex.buyer_id][ex.award_supplier_id] += value
                counts[ex.buyer_id] += 1
        return values, counts

    def _score_contract(
        self,
        ex: ExtractedRelease,
        buyer_conc: dict[str, IndicatorResult],
    ) -> ContractScore:
        """Run all indicators on a single extracted release."""
        indicator_results = []

        # Per-contract indicators
        sb = single_bidding(
            number_of_tenderers=ex.number_of_tenderers,
            procurement_method=ex.procurement_method,
            bid_count=ex.bid_count,
        )
        indicator_results.append(sb)

        tp = tender_period_risk(
            tender_period_days=ex.tender_period_days,
            procurement_method=ex.procurement_method,
            jurisdiction_minimum=self.config.tender_period_minimum,
        )
        indicator_results.append(tp)

        pt = procedure_type_risk(
            procurement_method=ex.procurement_method,
            procurement_method_details=ex.procurement_method_details,
        )
        indicator_results.append(pt)

        dp = decision_period_risk(
            decision_period_days=ex.decision_period_days,
        )
        indicator_results.append(dp)

        am = amendment_risk(
            amendment_count=ex.amendment_count,
            original_value=ex.original_value,
            final_value=ex.final_value,
        )
        indicator_results.append(am)

        # Buyer-level indicator
        bc = buyer_conc.get(ex.buyer_id)
        if bc:
            indicator_results.append(bc)

        # Composite CRI
        cri = compute_cri(
            indicator_results,
            red_threshold=self.config.cri_red_threshold,
            yellow_threshold=self.config.cri_yellow_threshold,
            min_indicators=self.config.min_indicators,
        )

        # Combined Bayesian evidence
        lr = combined_likelihood_ratio(indicator_results)

        # Explanations for flagged indicators
        explanations = [r.explanation for r in indicator_results if r.flag == 1]

        return ContractScore(
            ocid=ex.ocid,
            release_id=ex.release_id,
            buyer_id=ex.buyer_id,
            buyer_name=ex.buyer_name,
            supplier_id=ex.award_supplier_id,
            supplier_name=ex.award_supplier_name,
            award_value=ex.award_value,
            currency=ex.award_currency,
            procurement_method=ex.procurement_method,
            cri_score=cri.cri_score,
            cri_tier=cri.tier,
            n_indicators_available=cri.n_indicators_available,
            n_indicators_flagged=cri.n_indicators_flagged,
            single_bidding_flag=sb.flag,
            tender_period_flag=tp.flag,
            procedure_type_flag=pt.flag,
            decision_period_flag=dp.flag,
            amendment_flag=am.flag,
            buyer_concentration_flag=bc.flag if bc else None,
            combined_lr=lr,
            number_of_tenderers=ex.number_of_tenderers,
            tender_period_days=ex.tender_period_days,
            decision_period_days=ex.decision_period_days,
            amendment_count=ex.amendment_count,
            explanations=explanations,
            main_classification=ex.main_classification,
            fields_present=len(ex.fields_present),
            fields_missing=len(ex.fields_missing),
        )

    def _compute_profile(self) -> CountryProfile:
        """Compute aggregate country risk profile from scored contracts."""
        total = len(self.scores)
        total_value = sum(s.award_value or 0 for s in self.scores)

        # CRI distribution
        cri_scores = [s.cri_score for s in self.scores if s.cri_score is not None]
        if cri_scores:
            mean_cri = sum(cri_scores) / len(cri_scores)
            sorted_cri = sorted(cri_scores)
            mid = len(sorted_cri) // 2
            median_cri = sorted_cri[mid] if len(sorted_cri) % 2 else (sorted_cri[mid - 1] + sorted_cri[mid]) / 2
            variance = sum((c - mean_cri) ** 2 for c in cri_scores) / len(cri_scores)
            cri_std = math.sqrt(variance)
        else:
            mean_cri = median_cri = cri_std = None

        # Tier counts
        red = sum(1 for s in self.scores if s.cri_tier == "RED")
        yellow = sum(1 for s in self.scores if s.cri_tier == "YELLOW")
        green = sum(1 for s in self.scores if s.cri_tier == "GREEN")
        gray = sum(1 for s in self.scores if s.cri_tier == "GRAY")

        # Indicator prevalence
        def rate(flag_attr):
            with_data = [(getattr(s, flag_attr)) for s in self.scores if getattr(s, flag_attr) is not None]
            if not with_data:
                return None
            return sum(1 for f in with_data if f == 1) / len(with_data)

        # Top risk buyers
        buyer_scores = defaultdict(list)
        for s in self.scores:
            if s.buyer_id and s.cri_score is not None:
                buyer_scores[s.buyer_id].append(s.cri_score)
        top_buyers = []
        for bid, scores_list in buyer_scores.items():
            avg = sum(scores_list) / len(scores_list)
            top_buyers.append({"buyer_id": bid, "avg_cri": avg, "n_contracts": len(scores_list)})
        top_buyers.sort(key=lambda x: x["avg_cri"], reverse=True)

        # Top risk contracts
        ranked = sorted(self.scores, key=lambda x: x.cri_score or 0, reverse=True)
        top_contracts = [
            {"ocid": s.ocid, "cri": s.cri_score, "tier": s.cri_tier, "value": s.award_value,
             "buyer": s.buyer_id, "supplier": s.supplier_id}
            for s in ranked[:20]
        ]

        # Avg indicators available
        avg_avail = sum(s.n_indicators_available for s in self.scores) / total if total else 0

        return CountryProfile(
            country_code=self.config.country_code,
            country_name=self.config.country_name,
            total_contracts=total,
            total_value=total_value,
            currency=self.config.currency,
            mean_cri=mean_cri,
            median_cri=median_cri,
            cri_std=cri_std,
            red_count=red,
            yellow_count=yellow,
            green_count=green,
            gray_count=gray,
            single_bidding_rate=rate("single_bidding_flag"),
            non_competitive_rate=rate("procedure_type_flag"),
            short_tender_rate=rate("tender_period_flag"),
            amendment_rate=rate("amendment_flag"),
            avg_indicators_available=avg_avail,
            top_risk_buyers=top_buyers[:10],
            top_risk_contracts=top_contracts,
        )

    # --- Export methods ---

    def export_csv(self, filepath: str):
        """Export scored contracts to CSV."""
        if not self.scores:
            logger.warning("No scores to export")
            return

        fieldnames = [
            "ocid", "cri_tier", "cri_score", "n_indicators_flagged", "n_indicators_available",
            "combined_lr", "award_value", "currency", "buyer_id", "buyer_name",
            "supplier_id", "supplier_name", "procurement_method",
            "single_bidding", "tender_period", "procedure_type",
            "decision_period", "amendment", "buyer_concentration",
            "number_of_tenderers", "tender_period_days", "decision_period_days",
            "amendment_count", "main_classification", "explanations",
        ]

        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for s in sorted(self.scores, key=lambda x: x.cri_score or 0, reverse=True):
                writer.writerow({
                    "ocid": s.ocid,
                    "cri_tier": s.cri_tier,
                    "cri_score": f"{s.cri_score:.3f}" if s.cri_score is not None else "",
                    "n_indicators_flagged": s.n_indicators_flagged,
                    "n_indicators_available": s.n_indicators_available,
                    "combined_lr": f"{s.combined_lr:.2f}",
                    "award_value": s.award_value,
                    "currency": s.currency,
                    "buyer_id": s.buyer_id,
                    "buyer_name": s.buyer_name,
                    "supplier_id": s.supplier_id,
                    "supplier_name": s.supplier_name,
                    "procurement_method": s.procurement_method,
                    "single_bidding": s.single_bidding_flag,
                    "tender_period": s.tender_period_flag,
                    "procedure_type": s.procedure_type_flag,
                    "decision_period": s.decision_period_flag,
                    "amendment": s.amendment_flag,
                    "buyer_concentration": s.buyer_concentration_flag,
                    "number_of_tenderers": s.number_of_tenderers,
                    "tender_period_days": f"{s.tender_period_days:.1f}" if s.tender_period_days else "",
                    "decision_period_days": f"{s.decision_period_days:.1f}" if s.decision_period_days else "",
                    "amendment_count": s.amendment_count,
                    "main_classification": s.main_classification,
                    "explanations": " | ".join(s.explanations),
                })

    def export_json(self, filepath: str):
        """Export complete results to JSON."""
        output = {
            "metadata": {
                "country": self.config.country_name,
                "country_code": self.config.country_code,
                "analysis_date": datetime.now(timezone.utc).isoformat(),
                "total_contracts": len(self.scores),
                "configuration": {
                    "tender_period_minimum": self.config.tender_period_minimum,
                    "procurement_threshold": self.config.procurement_threshold,
                    "concentration_threshold": self.config.concentration_threshold,
                }
            },
            "profile": {
                "mean_cri": self.profile.mean_cri if self.profile else None,
                "median_cri": self.profile.median_cri if self.profile else None,
                "tier_distribution": {
                    "RED": self.profile.red_count if self.profile else 0,
                    "YELLOW": self.profile.yellow_count if self.profile else 0,
                    "GREEN": self.profile.green_count if self.profile else 0,
                    "GRAY": self.profile.gray_count if self.profile else 0,
                },
                "indicator_rates": {
                    "single_bidding": self.profile.single_bidding_rate if self.profile else None,
                    "non_competitive": self.profile.non_competitive_rate if self.profile else None,
                    "short_tender": self.profile.short_tender_rate if self.profile else None,
                    "amendment": self.profile.amendment_rate if self.profile else None,
                },
                "top_risk_buyers": self.profile.top_risk_buyers[:5] if self.profile else [],
                "top_risk_contracts": self.profile.top_risk_contracts[:10] if self.profile else [],
            },
            "contracts": [s.to_dict() for s in self.scores],
        }
        with open(filepath, "w") as f:
            json.dump(output, f, indent=2, default=str)
