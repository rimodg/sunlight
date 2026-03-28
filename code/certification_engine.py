"""
SUNLIGHT Structural Health Certification Engine
Computes country-level governance health scores from aggregated TCA analysis.
Produces certifiable structural integrity ratings for institutional clients.

Resolves UNDP Problem #8: Benchmarking Without Enforcement
Revenue Layer 3: Recurring certification revenue independent of finding new corruption.
"""

import json
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CertificationGrade(Enum):
    """Structural health grades — institutional language, not traffic lights."""
    A = "Structurally Sound"          # Confidence >= 0.75
    B = "Minor Structural Concerns"   # 0.60 <= confidence < 0.75
    C = "Elevated Structural Risk"    # 0.45 <= confidence < 0.60
    D = "Critical Structural Failure" # 0.30 <= confidence < 0.45
    F = "Systemic Structural Collapse"# confidence < 0.30


@dataclass
class SectorAnalysis:
    """TCA analysis of a specific procurement sector within a country."""
    sector: str  # e.g., "construction", "health", "education"
    contracts_analyzed: int
    avg_tca_confidence: float
    avg_cri_score: float
    total_contradictions: int
    total_seeks: int
    total_verifies: int
    grounding_ratio: float
    dominant_contradiction_type: str
    projected_recovery_value: float
    currency: str = "USD"


@dataclass  
class CountryCertification:
    """Complete structural health certification for a country."""
    country_code: str
    country_name: str
    certification_period: str  # e.g., "2025-Q4"
    
    # Aggregate scores
    overall_confidence: float
    grade: CertificationGrade
    
    # Component scores
    structural_integrity: float   # TCA average across all contracts
    pricing_integrity: float      # CRI average
    entity_integrity: float       # EVG pass rate
    oversight_coverage: float     # % of contracts with VERIFIES edges to oversight
    
    # Statistics
    contracts_analyzed: int
    total_contradictions: int
    total_recovery_projected: float
    currency: str
    
    # Sector breakdown
    sectors: List[SectorAnalysis] = field(default_factory=list)
    
    # Trend
    previous_confidence: Optional[float] = None
    trend: str = "NEW"  # "IMPROVING", "STABLE", "DECLINING", "NEW"
    
    # Methodology
    methodology_version: str = "TCA v4.0 + CRI v2.3 + EVG v1.0"
    generated_at: str = ""
    disclaimer: str = "Structural certification based on automated topological analysis of published procurement data. Findings are structural indicators — not allegations."
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)


class CertificationEngine:
    """
    Produces country-level structural health certifications.
    
    Pipeline:
    1. Aggregate TCA results across all contracts in a country
    2. Compute sector-level breakdowns
    3. Calculate composite integrity scores
    4. Assign grade
    5. Generate recommendations from structural patterns
    6. Compare with previous period for trend
    """
    
    GRADE_THRESHOLDS = [
        (0.75, CertificationGrade.A),
        (0.60, CertificationGrade.B),
        (0.45, CertificationGrade.C),
        (0.30, CertificationGrade.D),
        (0.00, CertificationGrade.F),
    ]
    
    SECTOR_CATEGORIES = {
        "construction": ["road", "bridge", "building", "infrastructure", "construction", "works"],
        "health": ["medical", "pharmaceutical", "health", "hospital", "vaccine", "drug"],
        "education": ["school", "education", "textbook", "university", "training"],
        "technology": ["IT", "software", "technology", "digital", "computer", "systems"],
        "defense": ["military", "defense", "security", "weapon", "army", "navy"],
        "energy": ["energy", "power", "electricity", "solar", "fuel", "oil"],
        "water": ["water", "sanitation", "sewage", "treatment", "irrigation"],
        "transport": ["transport", "vehicle", "fleet", "aviation", "railway"],
    }
    
    def __init__(self):
        self.previous_certifications: Dict[str, CountryCertification] = {}
    
    def classify_sector(self, contract_description: str) -> str:
        """Classify a contract into a sector based on description keywords."""
        desc_lower = contract_description.lower()
        for sector, keywords in self.SECTOR_CATEGORIES.items():
            if any(kw in desc_lower for kw in keywords):
                return sector
        return "general"
    
    def assign_grade(self, confidence: float) -> CertificationGrade:
        """Assign certification grade from confidence score."""
        for threshold, grade in self.GRADE_THRESHOLDS:
            if confidence >= threshold:
                return grade
        return CertificationGrade.F
    
    def compute_trend(self, country_code: str, current_confidence: float) -> Tuple[str, Optional[float]]:
        """Compare with previous certification period."""
        prev = self.previous_certifications.get(country_code)
        if not prev:
            return "NEW", None
        
        delta = current_confidence - prev.overall_confidence
        if delta > 0.05:
            return "IMPROVING", prev.overall_confidence
        elif delta < -0.05:
            return "DECLINING", prev.overall_confidence
        else:
            return "STABLE", prev.overall_confidence
    
    def generate_recommendations(
        self,
        confidence: float,
        contradictions_by_type: Dict[str, int],
        oversight_coverage: float,
        grounding_ratio: float
    ) -> List[str]:
        """Generate specific structural recommendations."""
        recs = []
        
        if oversight_coverage < 0.5:
            recs.append(
                f"CRITICAL: Only {oversight_coverage:.0%} of contracts have verified oversight. "
                f"Implement mandatory independent review for contracts above threshold."
            )
        
        if grounding_ratio < 0.3:
            recs.append(
                f"WARNING: Grounding ratio {grounding_ratio:.2f} — {(1-grounding_ratio):.0%} of governance claims are unverified. "
                f"Strengthen verification requirements across the procurement cycle."
            )
        
        # Contradiction-specific recommendations
        if contradictions_by_type.get("sole_source", 0) > 5:
            recs.append(
                f"PATTERN: {contradictions_by_type['sole_source']} sole-source contradictions detected. "
                f"Review direct award authorization procedures and enforce competitive thresholds."
            )
        
        if contradictions_by_type.get("vendor_capture", 0) > 3:
            recs.append(
                f"PATTERN: {contradictions_by_type['vendor_capture']} vendor capture indicators. "
                f"Implement vendor rotation policy with maximum 30% single-vendor concentration per agency."
            )
        
        if contradictions_by_type.get("fiscal_timing", 0) > 5:
            recs.append(
                f"PATTERN: {contradictions_by_type['fiscal_timing']} fiscal year-end timing findings. "
                f"Implement enhanced review procedures for awards in final 30 days of fiscal period."
            )
        
        if contradictions_by_type.get("entity_fabrication", 0) > 0:
            recs.append(
                f"CRITICAL: {contradictions_by_type['entity_fabrication']} fabricated competition findings. "
                f"Mandatory entity verification against corporate registries for all competitive tenders."
            )
        
        if confidence >= 0.75 and not recs:
            recs.append("Structural integrity meets certification standards. Continue monitoring.")
        
        return recs
    
    def certify_country(
        self,
        country_code: str,
        country_name: str,
        period: str,
        contract_analyses: List[Dict],
        currency: str = "USD"
    ) -> CountryCertification:
        """
        Produce a complete country certification from aggregated contract analyses.
        
        Args:
            country_code: ISO country code
            country_name: Full country name
            period: Certification period (e.g., "2025-Q4")
            contract_analyses: List of individual contract TCA results, each containing:
                - contract_id, tca_confidence, cri_score, evg_status
                - contradictions (list), description, value, sector
            currency: Default currency for reporting
        """
        if not contract_analyses:
            raise ValueError("Cannot certify with zero contract analyses")
        
        n = len(contract_analyses)
        
        # Aggregate scores
        tca_scores = [c.get("tca_confidence", 0.5) for c in contract_analyses]
        cri_scores = [c.get("cri_score", 0.5) for c in contract_analyses]
        evg_statuses = [c.get("evg_status", "INDEPENDENT") for c in contract_analyses]
        
        structural_integrity = sum(tca_scores) / n
        pricing_integrity = 1.0 - (sum(cri_scores) / n)  # Higher CRI = more anomalous = lower integrity
        entity_integrity = sum(1 for s in evg_statuses if s == "INDEPENDENT") / n
        
        # Oversight coverage: % of contracts where oversight VERIFIES the award
        oversight_present = sum(
            1 for c in contract_analyses
            if any(e.get("type") == "VERIFIES" and "oversight" in str(e.get("source", "")).lower()
                   for e in c.get("edges", []))
        )
        oversight_coverage = oversight_present / n
        
        # Composite confidence (weighted)
        overall_confidence = (
            structural_integrity * 0.40 +
            pricing_integrity * 0.20 +
            entity_integrity * 0.20 +
            oversight_coverage * 0.20
        )
        
        # Total contradictions
        all_contradictions = []
        for c in contract_analyses:
            all_contradictions.extend(c.get("contradictions", []))
        total_contradictions = len(all_contradictions)
        
        # Contradictions by type
        contradiction_types = {}
        for cont in all_contradictions:
            c_type = cont.get("type_classified", "other")
            contradiction_types[c_type] = contradiction_types.get(c_type, 0) + 1
        
        # Total seeks (unverified assumptions)
        total_seeks = sum(
            sum(1 for e in c.get("edges", []) if e.get("type") == "SEEKS")
            for c in contract_analyses
        )
        total_verifies = sum(
            sum(1 for e in c.get("edges", []) if e.get("type") == "VERIFIES")
            for c in contract_analyses
        )
        grounding_ratio = total_verifies / (total_verifies + total_seeks) if (total_verifies + total_seeks) > 0 else 0
        
        # Sector breakdown
        sector_contracts: Dict[str, List[Dict]] = {}
        for c in contract_analyses:
            sector = self.classify_sector(c.get("description", ""))
            if sector not in sector_contracts:
                sector_contracts[sector] = []
            sector_contracts[sector].append(c)
        
        sectors = []
        for sector, contracts in sector_contracts.items():
            sn = len(contracts)
            s_tca = sum(c.get("tca_confidence", 0.5) for c in contracts) / sn
            s_cri = sum(c.get("cri_score", 0.5) for c in contracts) / sn
            s_contradictions = sum(len(c.get("contradictions", [])) for c in contracts)
            s_seeks = sum(sum(1 for e in c.get("edges", []) if e.get("type") == "SEEKS") for c in contracts)
            s_verifies = sum(sum(1 for e in c.get("edges", []) if e.get("type") == "VERIFIES") for c in contracts)
            s_gr = s_verifies / (s_verifies + s_seeks) if (s_verifies + s_seeks) > 0 else 0
            s_recovery = sum(c.get("projected_recovery", 0) for c in contracts)
            
            # Dominant contradiction type
            s_types = {}
            for c in contracts:
                for cont in c.get("contradictions", []):
                    ct = cont.get("type_classified", "other")
                    s_types[ct] = s_types.get(ct, 0) + 1
            dominant = max(s_types, key=s_types.get) if s_types else "none"
            
            sectors.append(SectorAnalysis(
                sector=sector,
                contracts_analyzed=sn,
                avg_tca_confidence=round(s_tca, 4),
                avg_cri_score=round(s_cri, 4),
                total_contradictions=s_contradictions,
                total_seeks=s_seeks,
                total_verifies=s_verifies,
                grounding_ratio=round(s_gr, 4),
                dominant_contradiction_type=dominant,
                projected_recovery_value=round(s_recovery, 2),
                currency=currency,
            ))
        
        # Sort sectors by structural risk (lowest confidence first)
        sectors.sort(key=lambda s: s.avg_tca_confidence)
        
        # Trend
        trend, prev_conf = self.compute_trend(country_code, overall_confidence)
        
        # Grade
        grade = self.assign_grade(overall_confidence)
        
        # Recommendations
        recommendations = self.generate_recommendations(
            overall_confidence, contradiction_types, oversight_coverage, grounding_ratio
        )
        
        # Total projected recovery
        total_recovery = sum(c.get("projected_recovery", 0) for c in contract_analyses)
        
        cert = CountryCertification(
            country_code=country_code,
            country_name=country_name,
            certification_period=period,
            overall_confidence=round(overall_confidence, 4),
            grade=grade,
            structural_integrity=round(structural_integrity, 4),
            pricing_integrity=round(pricing_integrity, 4),
            entity_integrity=round(entity_integrity, 4),
            oversight_coverage=round(oversight_coverage, 4),
            contracts_analyzed=n,
            total_contradictions=total_contradictions,
            total_recovery_projected=round(total_recovery, 2),
            currency=currency,
            sectors=sectors,
            previous_confidence=prev_conf,
            trend=trend,
            generated_at=datetime.utcnow().isoformat() + "Z",
            recommendations=recommendations,
        )
        
        # Store for future trend comparison
        self.previous_certifications[country_code] = cert
        
        return cert
    
    def format_certification_report(self, cert: CountryCertification) -> str:
        """Format human-readable certification report."""
        lines = []
        lines.append("═" * 70)
        lines.append("SUNLIGHT STRUCTURAL HEALTH CERTIFICATION")
        lines.append("═" * 70)
        lines.append(f"Country: {cert.country_name} ({cert.country_code})")
        lines.append(f"Period: {cert.certification_period}")
        lines.append(f"Generated: {cert.generated_at}")
        lines.append(f"Methodology: {cert.methodology_version}")
        lines.append("")
        
        lines.append(f"OVERALL GRADE: {cert.grade.name} — {cert.grade.value}")
        lines.append(f"Structural Confidence: {cert.overall_confidence:.2%}")
        trend_arrow = {"IMPROVING": "↑", "DECLINING": "↓", "STABLE": "→", "NEW": "●"}
        lines.append(f"Trend: {trend_arrow.get(cert.trend, '?')} {cert.trend}" + 
                     (f" (from {cert.previous_confidence:.2%})" if cert.previous_confidence else ""))
        lines.append("")
        
        lines.append("COMPONENT SCORES:")
        lines.append(f"  Structural Integrity (TCA):  {cert.structural_integrity:.2%}")
        lines.append(f"  Pricing Integrity (CRI):     {cert.pricing_integrity:.2%}")
        lines.append(f"  Entity Integrity (EVG):      {cert.entity_integrity:.2%}")
        lines.append(f"  Oversight Coverage:          {cert.oversight_coverage:.2%}")
        lines.append("")
        
        lines.append(f"STATISTICS:")
        lines.append(f"  Contracts Analyzed:          {cert.contracts_analyzed:,}")
        lines.append(f"  Total Contradictions:        {cert.total_contradictions:,}")
        lines.append(f"  Projected Recovery:          {cert.currency} {cert.total_recovery_projected:,.2f}")
        lines.append("")
        
        if cert.sectors:
            lines.append("SECTOR BREAKDOWN:")
            for s in cert.sectors:
                risk = "🔴" if s.avg_tca_confidence < 0.4 else "🟡" if s.avg_tca_confidence < 0.6 else "🟢"
                lines.append(f"  {risk} {s.sector.upper()} — {s.contracts_analyzed} contracts — "
                           f"TCA {s.avg_tca_confidence:.2f} — {s.total_contradictions} contradictions — "
                           f"Recovery: {s.currency} {s.projected_recovery_value:,.0f}")
            lines.append("")
        
        if cert.recommendations:
            lines.append("RECOMMENDATIONS:")
            for i, rec in enumerate(cert.recommendations, 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")
        
        lines.append(cert.disclaimer)
        lines.append("═" * 70)
        return "\n".join(lines)


# ═══ DEMO ═══
if __name__ == "__main__":
    engine = CertificationEngine()
    
    # Simulate Senegal certification with sample contract analyses
    contracts = [
        {
            "contract_id": "SN-ARMP-2025-0847",
            "description": "Road Infrastructure Rehabilitation — Thiès",
            "tca_confidence": 0.28,
            "cri_score": 0.42,
            "evg_status": "INDEPENDENT",
            "contradictions": [
                {"type_classified": "sole_source", "description": "Sole-source vs competition"},
                {"type_classified": "vendor_capture", "description": "78% vendor concentration"},
                {"type_classified": "fiscal_timing", "description": "Year-end timing"},
            ],
            "edges": [{"type": "SEEKS", "source": "oversight"}],
            "value": 2450000,
            "projected_recovery": 585000,
        },
        {
            "contract_id": "SN-ARMP-2025-1456",
            "description": "Agricultural Equipment — SAED",
            "tca_confidence": 0.83,
            "cri_score": 0.14,
            "evg_status": "INDEPENDENT",
            "contradictions": [],
            "edges": [{"type": "VERIFIES", "source": "oversight"}],
            "value": 230000,
            "projected_recovery": 0,
        },
        {
            "contract_id": "SN-ARMP-2025-1102",
            "description": "Hospital Equipment — Dakar",
            "tca_confidence": 0.45,
            "cri_score": 0.38,
            "evg_status": "INDEPENDENT",
            "contradictions": [
                {"type_classified": "sole_source", "description": "Direct award on health equipment"},
            ],
            "edges": [{"type": "SEEKS", "source": "oversight"}],
            "value": 890000,
            "projected_recovery": 133500,
        },
    ]
    
    cert = engine.certify_country("SN", "Senegal", "2025-Q4", contracts)
    print(engine.format_certification_report(cert))
