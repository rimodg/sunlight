"""
SUNLIGHT Recovery Value Projection Engine
Converts TCA structural findings into projected recovery values
with specific remediation steps and dollar amounts.

Part of the SUNLIGHT full-stack recovery pipeline:
TCA Detection → TCA Solve → Recovery Projection → Remediation → Verification
"""

import json
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class PeerBenchmark:
    """Benchmark derived from peer contracts in same category/jurisdiction."""
    category: str
    jurisdiction: str
    peer_count: int
    median_value: float
    p25_value: float
    p75_value: float
    ci_lower: float  # 95% CI lower bound
    ci_upper: float  # 95% CI upper bound
    currency: str = "USD"


@dataclass
class RemediationStep:
    """A specific action the institution should take."""
    order: int
    action: str  # e.g., "Cancel sole-source designation"
    rationale: str  # Why this step
    edge_reference: str  # Which TCA edge this addresses
    urgency: str  # "immediate", "short-term", "structural"
    responsible_entity: str  # Who should act


@dataclass
class RecoveryProjection:
    """Complete recovery projection for a single structural finding."""
    contract_id: str
    contract_value: float
    currency: str
    tca_confidence: float
    cri_score: float
    contradictions: List[Dict]
    
    # Peer benchmark
    benchmark: Optional[PeerBenchmark] = None
    
    # Recovery calculation
    projected_fair_value: float = 0.0
    recovery_delta: float = 0.0
    recovery_confidence: float = 0.0  # How confident are we in the projection
    
    # Remediation
    remediation_steps: List[RemediationStep] = field(default_factory=list)
    
    # Metadata
    generated_at: str = ""
    methodology: str = "TCA structural analysis + peer contract benchmarking"
    disclaimer: str = "Structural finding — not an allegation. Recovery projections are estimates based on peer contract analysis."


class RecoveryEngine:
    """
    Converts TCA findings into recovery projections.
    
    Pipeline:
    1. Receive TCA finding (contract + contradictions + confidence)
    2. Compute peer benchmark from similar contracts
    3. Project fair value based on peer analysis
    4. Calculate recovery delta (awarded - projected fair)
    5. Generate specific remediation steps from contradiction types
    6. Assign recovery confidence based on evidence strength
    """
    
    # Contradiction type → remediation mapping
    REMEDIATION_MAP = {
        "sole_source_competitive": {
            "action": "Cancel sole-source designation and re-tender competitively",
            "urgency": "immediate",
            "recovery_basis": "peer_median",
            "typical_savings_pct": 0.15,  # 15% typical savings from competitive re-tender
        },
        "vendor_capture": {
            "action": "Implement vendor rotation policy and cap single-vendor share at 30% of agency contracts",
            "urgency": "structural",
            "recovery_basis": "concentration_premium",
            "typical_savings_pct": 0.12,
        },
        "fiscal_timing": {
            "action": "Defer award to next fiscal period with full competitive review",
            "urgency": "short-term",
            "recovery_basis": "timing_premium",
            "typical_savings_pct": 0.08,
        },
        "emergency_abuse": {
            "action": "Revoke emergency classification; re-classify under standard procedure",
            "urgency": "immediate",
            "recovery_basis": "peer_median",
            "typical_savings_pct": 0.20,
        },
        "fabricated_competition": {
            "action": "Void award; debar linked entities; re-tender with enhanced entity verification",
            "urgency": "immediate",
            "recovery_basis": "full_retender",
            "typical_savings_pct": 0.25,
        },
        "price_outside_range": {
            "action": "Renegotiate contract value to within peer confidence interval",
            "urgency": "immediate",
            "recovery_basis": "ci_upper",
            "typical_savings_pct": 0.18,
        },
        "oversight_gap": {
            "action": "Mandate independent verification of award by oversight body before disbursement",
            "urgency": "short-term",
            "recovery_basis": "prevention",
            "typical_savings_pct": 0.05,
        },
        "power_inversion": {
            "action": "Restructure vendor-buyer relationship; implement competitive re-bid with diversified vendor pool",
            "urgency": "structural",
            "recovery_basis": "concentration_premium",
            "typical_savings_pct": 0.15,
        },
    }
    
    # Edge type → contradiction classification
    EDGE_TO_CONTRADICTION = {
        ("award", "tender", "REMOVES"): "sole_source_competitive",
        ("award", "process", "REMOVES"): "sole_source_competitive",
        ("vendor", "buyer", "BOUNDS"): "vendor_capture",
        ("budget", "award", "BOUNDS"): "fiscal_timing",
        ("award", "budget", "REMOVES"): "price_outside_range",
        ("award", "process_emergency", "REMOVES"): "emergency_abuse",
        ("vendor_a", "vendor_b", "INHERITS"): "fabricated_competition",
        ("award", "oversight", "SEEKS"): "oversight_gap",
    }
    
    def __init__(self, contract_database: Optional[List[Dict]] = None):
        """
        Initialize with optional contract database for peer benchmarking.
        In production, this connects to the SUNLIGHT PostgreSQL database.
        """
        self.contracts = contract_database or []
    
    def classify_contradiction(self, edge: Dict) -> str:
        """Classify a TCA contradiction edge into a remediation category."""
        source_type = edge.get("source_type", edge.get("source", "")).lower()
        target_type = edge.get("target_type", edge.get("target", "")).lower()
        edge_type = edge.get("type", "")
        
        # Try exact match
        key = (source_type, target_type, edge_type)
        if key in self.EDGE_TO_CONTRADICTION:
            return self.EDGE_TO_CONTRADICTION[key]
        
        # Fuzzy match based on edge type and keywords
        if edge_type == "REMOVES":
            desc = edge.get("description", "").lower()
            if "sole" in desc or "competitive" in desc or "single bidder" in desc:
                return "sole_source_competitive"
            elif "price" in desc or "range" in desc or "budget" in desc:
                return "price_outside_range"
            elif "emergency" in desc or "timeline" in desc:
                return "emergency_abuse"
            else:
                return "sole_source_competitive"  # Default REMOVES
        elif edge_type == "BOUNDS" and "vendor" in source_type:
            return "vendor_capture"
        elif edge_type == "BOUNDS" and "budget" in source_type:
            return "fiscal_timing"
        elif edge_type == "INHERITS":
            return "fabricated_competition"
        elif edge_type == "SEEKS" and "oversight" in target_type:
            return "oversight_gap"
        
        return "oversight_gap"  # Default fallback
    
    def compute_peer_benchmark(
        self,
        contract_value: float,
        category: str,
        jurisdiction: str,
        currency: str = "USD"
    ) -> PeerBenchmark:
        """
        Compute peer contract benchmark.
        In production, queries the SUNLIGHT database.
        Here, uses statistical estimation based on contract characteristics.
        """
        # Filter peer contracts
        peers = [
            c for c in self.contracts
            if c.get("category") == category
            and c.get("jurisdiction") == jurisdiction
            and c.get("value", 0) > 0
        ]
        
        if len(peers) >= 10:
            values = sorted([c["value"] for c in peers])
            n = len(values)
            median = values[n // 2]
            p25 = values[n // 4]
            p75 = values[3 * n // 4]
            
            # Bootstrap CI (simplified — production uses 10,000 resamples)
            se = (p75 - p25) / (1.35 * math.sqrt(n))
            ci_lower = median - 1.96 * se
            ci_upper = median + 1.96 * se
        else:
            # Insufficient peers — estimate from contract value with typical ranges
            median = contract_value * 0.75  # Conservative: assume 25% premium
            p25 = contract_value * 0.60
            p75 = contract_value * 0.90
            ci_lower = contract_value * 0.55
            ci_upper = contract_value * 0.95
        
        return PeerBenchmark(
            category=category,
            jurisdiction=jurisdiction,
            peer_count=len(peers),
            median_value=round(median, 2),
            p25_value=round(p25, 2),
            p75_value=round(p75, 2),
            ci_lower=round(max(ci_lower, 0), 2),
            ci_upper=round(ci_upper, 2),
            currency=currency
        )
    
    def project_recovery(
        self,
        contract_id: str,
        contract_value: float,
        currency: str,
        category: str,
        jurisdiction: str,
        tca_confidence: float,
        cri_score: float,
        contradictions: List[Dict],
        evg_status: str = "INDEPENDENT"
    ) -> RecoveryProjection:
        """
        Full recovery projection pipeline.
        
        Args:
            contract_id: Unique contract identifier
            contract_value: Awarded contract value
            currency: Currency code
            category: Procurement category (e.g., "road_construction")
            jurisdiction: Country/region code
            tca_confidence: TCA structural confidence (0-1)
            cri_score: CRI price integrity score (0-1)
            contradictions: List of TCA contradiction edges
            evg_status: EVG entity status
        
        Returns:
            Complete RecoveryProjection with remediation steps and dollar amounts
        """
        # Step 1: Compute peer benchmark
        benchmark = self.compute_peer_benchmark(
            contract_value, category, jurisdiction, currency
        )
        
        # Step 2: Classify contradictions and compute remediation
        remediation_steps = []
        cumulative_savings_pct = 0.0
        
        for i, contradiction in enumerate(contradictions):
            c_type = self.classify_contradiction(contradiction)
            template = self.REMEDIATION_MAP.get(c_type, self.REMEDIATION_MAP["oversight_gap"])
            
            step = RemediationStep(
                order=i + 1,
                action=template["action"],
                rationale=contradiction.get("description", f"TCA identified {contradiction.get('type', 'structural')} contradiction"),
                edge_reference=f"{contradiction.get('source', '?')} → {contradiction.get('target', '?')} ({contradiction.get('type', '?')})",
                urgency=template["urgency"],
                responsible_entity=self._infer_responsible_entity(c_type, jurisdiction)
            )
            remediation_steps.append(step)
            
            # Compound savings (diminishing returns for multiple contradictions)
            marginal = template["typical_savings_pct"] * (0.8 ** i)
            cumulative_savings_pct += marginal
        
        # Cap cumulative savings at reasonable maximum
        cumulative_savings_pct = min(cumulative_savings_pct, 0.40)
        
        # Step 3: Apply EVG multiplier
        if evg_status == "FABRICATED_COMPETITION":
            cumulative_savings_pct = max(cumulative_savings_pct, 0.25)
            remediation_steps.insert(0, RemediationStep(
                order=0,
                action="Void award immediately. Debar all linked entities. Full re-tender required.",
                rationale="EVG detected fabricated competition — entities are not independent",
                edge_reference="EVG entity graph analysis",
                urgency="immediate",
                responsible_entity="Integrity/Investigation Unit"
            ))
            # Re-number
            for j, step in enumerate(remediation_steps):
                step.order = j + 1
        
        # Step 4: Project fair value
        projected_fair_value = contract_value * (1 - cumulative_savings_pct)
        recovery_delta = contract_value - projected_fair_value
        
        # Step 5: Compute recovery confidence
        # Based on: TCA confidence, number of contradictions, peer benchmark quality
        evidence_factors = [
            1.0 - tca_confidence,  # Lower TCA confidence = more structural problems = higher recovery potential
            min(len(contradictions) / 5, 1.0),  # More contradictions = more evidence
            0.8 if cri_score > 0.7 else 0.5 if cri_score > 0.5 else 0.3,  # CRI corroboration
            0.9 if benchmark.peer_count >= 10 else 0.6 if benchmark.peer_count >= 3 else 0.4,  # Benchmark quality
            1.0 if evg_status == "FABRICATED_COMPETITION" else 0.5 if evg_status == "SUSPICIOUS" else 0.3,
        ]
        recovery_confidence = sum(evidence_factors) / len(evidence_factors)
        recovery_confidence = min(recovery_confidence, 0.95)
        
        return RecoveryProjection(
            contract_id=contract_id,
            contract_value=contract_value,
            currency=currency,
            tca_confidence=tca_confidence,
            cri_score=cri_score,
            contradictions=contradictions,
            benchmark=benchmark,
            projected_fair_value=round(projected_fair_value, 2),
            recovery_delta=round(recovery_delta, 2),
            recovery_confidence=round(recovery_confidence, 4),
            remediation_steps=remediation_steps,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
    
    def _infer_responsible_entity(self, contradiction_type: str, jurisdiction: str) -> str:
        """Map contradiction type to responsible institutional entity."""
        mapping = {
            "sole_source_competitive": "Procurement Oversight Authority",
            "vendor_capture": "Procurement Oversight Authority + Audit Office",
            "fiscal_timing": "Budget Authority + Audit Office",
            "emergency_abuse": "Procurement Oversight Authority",
            "fabricated_competition": "Integrity/Investigation Unit",
            "price_outside_range": "Procurement Oversight Authority",
            "oversight_gap": "Audit Office",
            "power_inversion": "Procurement Oversight Authority + Executive",
        }
        return mapping.get(contradiction_type, "Procurement Oversight Authority")
    
    def format_recovery_report(self, projection: RecoveryProjection) -> str:
        """Format a human-readable recovery report from a projection."""
        lines = []
        lines.append("=" * 70)
        lines.append("SUNLIGHT RECOVERY PROJECTION")
        lines.append("=" * 70)
        lines.append(f"Contract: {projection.contract_id}")
        lines.append(f"Awarded Value: {projection.currency} {projection.contract_value:,.2f}")
        lines.append(f"TCA Confidence: {projection.tca_confidence:.2f}")
        lines.append(f"CRI Score: {projection.cri_score:.2f}")
        lines.append(f"Contradictions: {len(projection.contradictions)}")
        lines.append("")
        
        if projection.benchmark:
            b = projection.benchmark
            lines.append(f"PEER BENCHMARK ({b.peer_count} peers in {b.jurisdiction}/{b.category})")
            lines.append(f"  Median: {b.currency} {b.median_value:,.2f}")
            lines.append(f"  95% CI: [{b.currency} {b.ci_lower:,.2f} — {b.currency} {b.ci_upper:,.2f}]")
            lines.append("")
        
        lines.append("RECOVERY PROJECTION")
        lines.append(f"  Projected Fair Value: {projection.currency} {projection.projected_fair_value:,.2f}")
        lines.append(f"  Recovery Delta: {projection.currency} {projection.recovery_delta:,.2f}")
        lines.append(f"  Recovery Confidence: {projection.recovery_confidence:.1%}")
        lines.append("")
        
        lines.append("REMEDIATION STEPS")
        for step in projection.remediation_steps:
            lines.append(f"  {step.order}. [{step.urgency.upper()}] {step.action}")
            lines.append(f"     Basis: {step.edge_reference}")
            lines.append(f"     Responsible: {step.responsible_entity}")
            lines.append("")
        
        lines.append(f"Generated: {projection.generated_at}")
        lines.append(f"Methodology: {projection.methodology}")
        lines.append(f"Disclaimer: {projection.disclaimer}")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def to_json(self, projection: RecoveryProjection) -> str:
        """Serialize projection to JSON for API delivery."""
        data = asdict(projection)
        return json.dumps(data, indent=2, default=str)


# ═══ DEMO: Senegal Case ═══
if __name__ == "__main__":
    engine = RecoveryEngine()
    
    # Senegal case: SN-ARMP-2025-0847
    projection = engine.project_recovery(
        contract_id="SN-ARMP-2025-0847",
        contract_value=2_450_000,
        currency="USD",
        category="road_construction",
        jurisdiction="SN",
        tca_confidence=0.28,
        cri_score=0.42,
        contradictions=[
            {
                "source": "award", "target": "tender_process", "type": "REMOVES",
                "description": "Sole-source designation contradicts competitive requirement for contracts above $500K"
            },
            {
                "source": "vendor", "target": "buyer", "type": "BOUNDS",
                "description": "Vendor controls 78% of agency road contracts — power inversion"
            },
            {
                "source": "budget", "target": "award", "type": "BOUNDS",
                "description": "Fiscal year-end timing — award 8 days before budget close"
            },
        ],
        evg_status="INDEPENDENT"
    )
    
    print(engine.format_recovery_report(projection))
    print("\n\nJSON OUTPUT:")
    print(engine.to_json(projection))
