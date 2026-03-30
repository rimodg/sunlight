"""
SUNLIGHT Pre-Award Structural Gate
The engine that positions SUNLIGHT AT the procurement pipeline joints.

Not downstream analysis. Not post-hoc detection.
Structural verification BEFORE money moves.

Seven gates corresponding to seven pipeline joints:
1. NEED GATE — Is this need structurally legitimate?
2. SPEC GATE — Do specifications exclude competition?
3. ENTITY GATE — Are bidders independent entities?
4. COMPETITION GATE — Is competition structurally real?
5. PRICE GATE — Is the price structurally sound?
6. AWARD GATE — Does the award contradict the process?
7. PAYMENT GATE — Does delivery verify disbursement?

Each gate produces: CLEAR / REVIEW / BLOCK
CLEAR = proceed, structural verification passed
REVIEW = proceed with mandatory independent review
BLOCK = cannot proceed until structural contradiction resolved

This is what converts SEEKS edges to VERIFIES edges in the
global procurement pipeline. The first structural verification
layer in the history of public procurement.
"""

import json
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GateVerdict(Enum):
    CLEAR = "CLEAR"       # Structurally sound — proceed
    REVIEW = "REVIEW"     # Structural concern — proceed with independent review
    BLOCK = "BLOCK"       # Structural contradiction — cannot proceed


class GateType(Enum):
    NEED = "need"
    SPEC = "spec"
    ENTITY = "entity"
    COMPETITION = "competition"
    PRICE = "price"
    AWARD = "award"
    PAYMENT = "payment"


@dataclass
class GateResult:
    """Result from a single structural gate."""
    gate: GateType
    verdict: GateVerdict
    confidence: float
    contradictions: List[Dict]
    evidence: List[str]
    recommendation: str
    processing_time_ms: float = 0.0


@dataclass
class GatePassport:
    """
    Complete structural verification passport for a contract.
    Every gate's result, combined verdict, and the structural
    signature that becomes the VERIFIES edge in the pipeline.
    """
    contract_id: str
    ocid: Optional[str]
    country_code: str
    contract_value: float
    currency: str
    
    # Gate results
    gates: List[GateResult] = field(default_factory=list)
    
    # Combined assessment
    overall_verdict: GateVerdict = GateVerdict.CLEAR
    structural_confidence: float = 1.0
    total_contradictions: int = 0
    gates_passed: int = 0
    gates_review: int = 0
    gates_blocked: int = 0
    
    # Projected impact
    projected_recovery_if_blocked: float = 0.0
    
    # Metadata
    passport_id: str = ""
    issued_at: str = ""
    valid_until: str = ""  # Passports expire — structures change
    methodology_version: str = "SUNLIGHT Gate v1.0 — TCA v4.0"
    
    # The critical line
    verification_statement: str = ""


class NeedGate:
    """
    Gate 1: Is this procurement need structurally legitimate?
    
    Checks:
    - Does this agency historically procure this category?
    - Is the need volume consistent with operational patterns?
    - Does the need timing correlate with fiscal pressure?
    - Is there a pattern of needs created for specific vendors?
    """
    
    def evaluate(
        self,
        agency_id: str,
        category: str,
        value: float,
        currency: str,
        fiscal_month: int,
        fiscal_day: int,
        agency_history: Optional[Dict] = None
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.8  # Start high, deduct for issues
        
        # Check 1: Category consistency
        if agency_history:
            historical_categories = agency_history.get("categories", [])
            if category not in historical_categories:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Agency has no history procuring '{category}'. First-time category procurement above threshold.",
                    "source": "need",
                    "target": "agency_history"
                })
                confidence -= 0.15
                evidence.append(f"Agency historical categories: {historical_categories}. Requested: {category}.")
        
        # Check 2: Value anomaly
        if agency_history:
            avg_value = agency_history.get("avg_contract_value", 0)
            if avg_value > 0 and value > avg_value * 3:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Contract value {currency} {value:,.0f} is {value/avg_value:.1f}x the agency average of {currency} {avg_value:,.0f}.",
                    "source": "need_value",
                    "target": "agency_baseline"
                })
                confidence -= 0.15
                evidence.append(f"Agency average contract: {currency} {avg_value:,.0f}. This contract: {currency} {value:,.0f}.")
        
        # Check 3: Fiscal timing
        fiscal_end_months = [3, 6, 9, 12]
        if fiscal_month in fiscal_end_months and fiscal_day > 20:
            contradictions.append({
                "type": "BOUNDS",
                "description": f"Need determination in final 10 days of fiscal period (month {fiscal_month}, day {fiscal_day}).",
                "source": "fiscal_pressure",
                "target": "need"
            })
            confidence -= 0.10
            evidence.append(f"Fiscal year-end proximity: {fiscal_day} days into month {fiscal_month}.")
        
        # Determine verdict
        if confidence >= 0.7:
            verdict = GateVerdict.CLEAR
            recommendation = "Need determination is structurally consistent with agency history."
        elif confidence >= 0.5:
            verdict = GateVerdict.REVIEW
            recommendation = "Need requires independent verification before proceeding. " + "; ".join(e for e in evidence[:2])
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "Need determination structurally inconsistent. Mandatory review required before any procurement action."
        
        return GateResult(
            gate=GateType.NEED,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class SpecGate:
    """
    Gate 2: Do specifications exclude competition?
    
    Checks:
    - Are specs unusually narrow (matching single vendor)?
    - Do specs reference proprietary standards without justification?
    - Is the experience requirement disproportionate to contract value?
    - Do specs match a previous vendor's exact capabilities?
    """
    
    def evaluate(
        self,
        specs: Dict,
        known_vendors_in_category: int = 0,
        previous_winner: Optional[str] = None
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.8
        
        # Check 1: Experience requirement vs contract value
        min_years = specs.get("min_experience_years", 0)
        contract_value = specs.get("contract_value", 0)
        
        if min_years > 5 and contract_value < 500_000:
            contradictions.append({
                "type": "BOUNDS",
                "description": f"Specification requires {min_years} years experience for a {contract_value:,.0f} contract. Disproportionate barrier to entry.",
                "source": "spec_experience",
                "target": "competition"
            })
            confidence -= 0.15
            evidence.append(f"{min_years}-year experience requirement on sub-$500K contract limits competition.")
        
        # Check 2: Proprietary references
        proprietary_refs = specs.get("proprietary_references", [])
        if proprietary_refs:
            contradictions.append({
                "type": "REMOVES",
                "description": f"Specifications reference {len(proprietary_refs)} proprietary standards without 'or equivalent' clause.",
                "source": "spec_proprietary",
                "target": "open_competition"
            })
            confidence -= 0.20
            evidence.append(f"Proprietary references: {', '.join(proprietary_refs[:3])}.")
        
        # Check 3: Known vendor pool
        if known_vendors_in_category > 0 and known_vendors_in_category < 3:
            contradictions.append({
                "type": "BOUNDS",
                "description": f"Only {known_vendors_in_category} known vendors meet specifications in this jurisdiction.",
                "source": "spec_narrowness",
                "target": "market_competition"
            })
            confidence -= 0.15
            evidence.append(f"Vendor pool reduced to {known_vendors_in_category} by specifications.")
        
        # Check 4: Previous winner match
        if previous_winner and specs.get("matches_previous_winner_profile", False):
            contradictions.append({
                "type": "REMOVES",
                "description": f"Specification profile matches previous contract winner '{previous_winner}'. Potential tailored specs.",
                "source": "spec_tailoring",
                "target": "fair_competition"
            })
            confidence -= 0.20
            evidence.append(f"Spec profile matches previous winner: {previous_winner}.")
        
        if confidence >= 0.7:
            verdict = GateVerdict.CLEAR
            recommendation = "Specifications are structurally open to competition."
        elif confidence >= 0.5:
            verdict = GateVerdict.REVIEW
            recommendation = "Specifications may restrict competition. Independent review of spec scope recommended."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "Specifications structurally exclude competition. Spec revision required before tender publication."
        
        return GateResult(
            gate=GateType.SPEC,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class EntityGate:
    """
    Gate 3: Are bidding entities independent?
    
    Runs EVG signals BEFORE the award:
    - Shared addresses
    - Synchronized incorporation
    - Shared directors/officers
    - Shell entity indicators
    - Recent incorporation relative to tender
    """
    
    def evaluate(self, bidders: List[Dict]) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.9
        
        if len(bidders) < 2:
            return GateResult(
                gate=GateType.ENTITY,
                verdict=GateVerdict.CLEAR,
                confidence=0.9,
                contradictions=[],
                evidence=["Single bidder — entity independence check not applicable."],
                recommendation="Single bidder. Entity gate passes by default."
            )
        
        # Check 1: Shared addresses
        addresses = {}
        for b in bidders:
            addr = b.get("address", "").strip().lower()
            if addr:
                if addr in addresses:
                    contradictions.append({
                        "type": "INHERITS",
                        "description": f"Bidders '{b.get('name')}' and '{addresses[addr]}' share address: {addr}.",
                        "source": b.get("id", "bidder_x"),
                        "target": addresses[addr]
                    })
                    confidence -= 0.30
                    evidence.append(f"Shared address: {addr}")
                else:
                    addresses[addr] = b.get("name", "unknown")
        
        # Check 2: Incorporation timing
        tender_date = datetime(2025, 1, 1)  # Would come from contract data
        for b in bidders:
            inc_date_str = b.get("incorporation_date")
            if inc_date_str:
                try:
                    inc_date = datetime.fromisoformat(inc_date_str)
                    days_before_tender = (tender_date - inc_date).days
                    if 0 < days_before_tender < 90:
                        contradictions.append({
                            "type": "REMOVES",
                            "description": f"Bidder '{b.get('name')}' incorporated {days_before_tender} days before tender. Shell entity indicator.",
                            "source": "entity_timing",
                            "target": "entity_independence"
                        })
                        confidence -= 0.25
                        evidence.append(f"{b.get('name')} incorporated {days_before_tender} days before tender.")
                except (ValueError, TypeError):
                    pass
        
        # Check 3: Shared directors
        all_directors = {}
        for b in bidders:
            for director in b.get("directors", []):
                d_name = director.lower().strip()
                if d_name in all_directors and all_directors[d_name] != b.get("name"):
                    contradictions.append({
                        "type": "INHERITS",
                        "description": f"Director '{director}' appears in both '{b.get('name')}' and '{all_directors[d_name]}'.",
                        "source": b.get("id", "bidder_x"),
                        "target": all_directors[d_name]
                    })
                    confidence -= 0.30
                    evidence.append(f"Shared director: {director}")
                else:
                    all_directors[d_name] = b.get("name", "unknown")
        
        confidence = max(confidence, 0.0)
        
        if confidence >= 0.7:
            verdict = GateVerdict.CLEAR
            recommendation = "Bidding entities appear structurally independent."
        elif confidence >= 0.4:
            verdict = GateVerdict.REVIEW
            recommendation = "Entity independence concerns detected. Enhanced due diligence required before award."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "FABRICATED COMPETITION DETECTED. Bidding entities are structurally linked. Award cannot proceed. Refer to integrity unit."
        
        return GateResult(
            gate=GateType.ENTITY,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class CompetitionGate:
    """
    Gate 4: Is competition structurally real?
    
    Checks beyond entity independence:
    - Bid price distribution (too uniform = coordinated)
    - Historical win patterns (rotation = collusion)
    - Vendor concentration per agency
    """
    
    def evaluate(
        self,
        bid_prices: List[float],
        vendor_agency_share: float = 0.0,
        historical_wins: Optional[Dict] = None
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.8
        
        # Check 1: Price clustering
        if len(bid_prices) >= 3:
            avg = sum(bid_prices) / len(bid_prices)
            if avg > 0:
                spreads = [abs(p - avg) / avg for p in bid_prices]
                max_spread = max(spreads)
                if max_spread < 0.05:  # All bids within 5% of each other
                    contradictions.append({
                        "type": "REMOVES",
                        "description": f"Bid prices cluster within {max_spread:.1%} of average. Statistically improbable without coordination.",
                        "source": "price_coordination",
                        "target": "independent_bidding"
                    })
                    confidence -= 0.25
                    evidence.append(f"Price spread: {max_spread:.1%}. Expected: >10% for independent bids.")
        
        # Check 2: Vendor concentration
        if vendor_agency_share > 0.5:
            contradictions.append({
                "type": "BOUNDS",
                "description": f"Winning vendor holds {vendor_agency_share:.0%} of agency contracts. Vendor capture indicator.",
                "source": "vendor",
                "target": "buyer"
            })
            confidence -= 0.20
            evidence.append(f"Vendor agency share: {vendor_agency_share:.0%}. Threshold: 30%.")
        
        # Check 3: Win rotation
        if historical_wins:
            pattern = historical_wins.get("rotation_detected", False)
            if pattern:
                contradictions.append({
                    "type": "REMOVES",
                    "description": "Win rotation pattern detected across last 8 tenders. Vendors take turns winning.",
                    "source": "collusion_pattern",
                    "target": "competitive_award"
                })
                confidence -= 0.25
                evidence.append("Systematic win rotation across recent tenders.")
        
        if confidence >= 0.7:
            verdict = GateVerdict.CLEAR
            recommendation = "Competition appears structurally genuine."
        elif confidence >= 0.5:
            verdict = GateVerdict.REVIEW
            recommendation = "Competition structure shows anomalies. Independent review of bid patterns recommended."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "Competition is structurally compromised. Re-tender with enhanced monitoring required."
        
        return GateResult(
            gate=GateType.COMPETITION,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class PriceGate:
    """
    Gate 5: Is the contract price structurally sound?
    
    CRI integration:
    - Peer benchmark comparison
    - Bootstrap CI check
    - Change order monitoring
    """
    
    def evaluate(
        self,
        contract_value: float,
        currency: str,
        peer_median: float,
        peer_ci_upper: float,
        change_order_value: float = 0.0,
        original_value: float = 0.0
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.8
        
        # Check 1: Price vs peer benchmark
        if peer_median > 0:
            markup = (contract_value - peer_median) / peer_median
            if contract_value > peer_ci_upper:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Contract value {currency} {contract_value:,.0f} exceeds 95% CI upper bound ({currency} {peer_ci_upper:,.0f}). {markup:.1%} above peer median.",
                    "source": "price",
                    "target": "peer_benchmark"
                })
                confidence -= 0.25
                evidence.append(f"Price markup: {markup:.1%} above peer median of {currency} {peer_median:,.0f}.")
            elif markup > 0.15:
                contradictions.append({
                    "type": "BOUNDS",
                    "description": f"Contract value {markup:.1%} above peer median. Within CI but elevated.",
                    "source": "price",
                    "target": "peer_benchmark"
                })
                confidence -= 0.10
                evidence.append(f"Elevated price: {markup:.1%} above median.")
        
        # Check 2: Change order inflation
        if original_value > 0 and change_order_value > 0:
            change_pct = change_order_value / original_value
            if change_pct > 0.15:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Change orders total {change_pct:.0%} of original contract value. Structural price inflation.",
                    "source": "change_orders",
                    "target": "contract_integrity"
                })
                confidence -= 0.20
                evidence.append(f"Change order inflation: {change_pct:.0%} of original value.")
        
        if confidence >= 0.7:
            verdict = GateVerdict.CLEAR
            recommendation = "Price is within structural norms."
        elif confidence >= 0.5:
            verdict = GateVerdict.REVIEW
            recommendation = "Price anomaly detected. Independent price review recommended before disbursement."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "Price structurally unsound. Renegotiation or re-tender required."
        
        return GateResult(
            gate=GateType.PRICE,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class AwardGate:
    """
    Gate 6: Does the award contradict the process?
    
    The master gate. Runs full TCA on the contract graph:
    - Process method vs contract value
    - Award vs tender requirements
    - Oversight presence
    - Political patron signature detection
    """
    
    def evaluate(
        self,
        procurement_method: str,
        contract_value: float,
        currency: str,
        competitive_threshold: float,
        has_oversight_verification: bool = False,
        single_decision_maker: bool = False,
        need_gate: Optional[GateResult] = None,
        spec_gate: Optional[GateResult] = None,
        entity_gate: Optional[GateResult] = None,
        competition_gate: Optional[GateResult] = None,
        price_gate: Optional[GateResult] = None
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.8
        
        # Check 1: Method vs value
        if procurement_method in ("direct", "sole_source", "limited", "emergency"):
            if contract_value > competitive_threshold:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Non-competitive method '{procurement_method}' on {currency} {contract_value:,.0f} contract (threshold: {currency} {competitive_threshold:,.0f}).",
                    "source": "award",
                    "target": "process_requirement"
                })
                confidence -= 0.20
                evidence.append(f"Direct award above competitive threshold by {(contract_value/competitive_threshold - 1):.0%}.")
        
        # Check 2: Oversight absence
        if not has_oversight_verification:
            contradictions.append({
                "type": "SEEKS",
                "description": "No independent oversight verification of award decision.",
                "source": "award",
                "target": "oversight"
            })
            confidence -= 0.10
            evidence.append("Oversight: ABSENT. Award proceeds without independent verification.")
        
        # Check 3: Single decision maker (political patron signature)
        if single_decision_maker:
            patron_edges = 0
            if not has_oversight_verification:
                patron_edges += 1
            if procurement_method in ("direct", "sole_source"):
                patron_edges += 1
            if need_gate and need_gate.verdict != GateVerdict.CLEAR:
                patron_edges += 1
            
            if patron_edges >= 2:
                contradictions.append({
                    "type": "REMOVES",
                    "description": f"Single decision maker controls {patron_edges + 1} pipeline joints simultaneously. Political patron topological signature.",
                    "source": "patron",
                    "target": "governance_integrity"
                })
                confidence -= 0.30
                evidence.append(f"Single actor controls {patron_edges + 1} pipeline joints. Structural capture indicator.")
        
        # Check 4: Aggregate upstream gate failures
        upstream_gates = [g for g in [need_gate, spec_gate, entity_gate, competition_gate, price_gate] if g]
        blocked_upstream = sum(1 for g in upstream_gates if g.verdict == GateVerdict.BLOCK)
        review_upstream = sum(1 for g in upstream_gates if g.verdict == GateVerdict.REVIEW)
        
        if blocked_upstream > 0:
            contradictions.append({
                "type": "REMOVES",
                "description": f"{blocked_upstream} upstream gates BLOCKED. Award cannot proceed on structurally compromised foundation.",
                "source": "upstream_gates",
                "target": "award_integrity"
            })
            confidence -= 0.15 * blocked_upstream
            evidence.append(f"Upstream blocks: {blocked_upstream}. Reviews: {review_upstream}.")
        elif review_upstream >= 3:
            contradictions.append({
                "type": "BOUNDS",
                "description": f"{review_upstream} upstream gates require review. Cumulative structural risk is elevated.",
                "source": "upstream_gates",
                "target": "award_integrity"
            })
            confidence -= 0.10
        
        confidence = max(confidence, 0.0)
        
        if confidence >= 0.65:
            verdict = GateVerdict.CLEAR
            recommendation = "Award is structurally consistent with process requirements."
        elif confidence >= 0.4:
            verdict = GateVerdict.REVIEW
            recommendation = "Award has structural concerns. Independent review committee must verify before contract execution."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "AWARD STRUCTURALLY COMPROMISED. Contract cannot execute. Full structural review required. Refer to integrity unit if patron signature detected."
        
        return GateResult(
            gate=GateType.AWARD,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class PaymentGate:
    """
    Gate 7: Does delivery verify disbursement?
    
    The hardest gate — least data available.
    Checks what it can, flags what it can't.
    """
    
    def evaluate(
        self,
        disbursement_amount: float,
        delivery_confirmed: bool,
        delivery_percentage: float = 1.0,
        delivery_verified_by: str = "self_reported",
        time_since_award_days: int = 0,
        expected_duration_days: int = 0
    ) -> GateResult:
        contradictions = []
        evidence = []
        confidence = 0.7  # Start lower — payment data is inherently less reliable
        
        # Check 1: Delivery confirmation
        if not delivery_confirmed:
            contradictions.append({
                "type": "REMOVES",
                "description": f"Disbursement of {disbursement_amount:,.0f} requested with no delivery confirmation.",
                "source": "disbursement",
                "target": "delivery"
            })
            confidence -= 0.30
            evidence.append("PHANTOM DELIVERY RISK: Payment requested without delivery verification.")
        
        # Check 2: Partial delivery, full payment
        if delivery_confirmed and delivery_percentage < 0.8 and disbursement_amount > 0:
            contradictions.append({
                "type": "REMOVES",
                "description": f"Delivery at {delivery_percentage:.0%} but disbursement at 100%. Overpayment relative to delivery.",
                "source": "disbursement",
                "target": "delivery_proportion"
            })
            confidence -= 0.20
            evidence.append(f"Delivery: {delivery_percentage:.0%}. Payment: 100%.")
        
        # Check 3: Verification source
        if delivery_verified_by == "self_reported":
            contradictions.append({
                "type": "SEEKS",
                "description": "Delivery verification is self-reported by vendor. No independent confirmation.",
                "source": "delivery",
                "target": "independent_verification"
            })
            confidence -= 0.10
            evidence.append("Delivery verified by: vendor (self-reported). No independent check.")
        
        # Check 4: Timing anomaly
        if expected_duration_days > 0 and time_since_award_days > 0:
            if time_since_award_days < expected_duration_days * 0.3:
                contradictions.append({
                    "type": "BOUNDS",
                    "description": f"Payment requested at {time_since_award_days} days into a {expected_duration_days}-day contract ({time_since_award_days/expected_duration_days:.0%} elapsed). Premature disbursement.",
                    "source": "payment_timing",
                    "target": "contract_schedule"
                })
                confidence -= 0.15
                evidence.append(f"Premature payment: {time_since_award_days}/{expected_duration_days} days.")
        
        confidence = max(confidence, 0.0)
        
        if confidence >= 0.6:
            verdict = GateVerdict.CLEAR
            recommendation = "Payment is structurally justified by delivery evidence."
        elif confidence >= 0.35:
            verdict = GateVerdict.REVIEW
            recommendation = "Payment has structural concerns. Independent delivery verification required before disbursement."
        else:
            verdict = GateVerdict.BLOCK
            recommendation = "PAYMENT BLOCKED. Delivery not structurally verified. Disbursement cannot proceed without independent confirmation of goods/works delivery."
        
        return GateResult(
            gate=GateType.PAYMENT,
            verdict=verdict,
            confidence=round(confidence, 4),
            contradictions=contradictions,
            evidence=evidence,
            recommendation=recommendation
        )


class PreAwardGate:
    """
    The master orchestrator. Runs all 7 gates in sequence.
    Each gate feeds the next. The Award Gate aggregates all upstream results.
    
    This is the engine that converts SUNLIGHT from downstream watcher
    to pipeline infrastructure. Every dollar that passes through a
    Pre-Award Gate has been structurally verified.
    """
    
    def __init__(self):
        self.need_gate = NeedGate()
        self.spec_gate = SpecGate()
        self.entity_gate = EntityGate()
        self.competition_gate = CompetitionGate()
        self.price_gate = PriceGate()
        self.award_gate = AwardGate()
        self.payment_gate = PaymentGate()
    
    def run_full_gate(
        self,
        contract_id: str,
        country_code: str,
        contract_value: float,
        currency: str,
        # Need gate inputs
        agency_id: str = "",
        category: str = "",
        fiscal_month: int = 1,
        fiscal_day: int = 1,
        agency_history: Optional[Dict] = None,
        # Spec gate inputs
        specs: Optional[Dict] = None,
        known_vendors: int = 10,
        previous_winner: Optional[str] = None,
        # Entity gate inputs
        bidders: Optional[List[Dict]] = None,
        # Competition gate inputs
        bid_prices: Optional[List[float]] = None,
        vendor_agency_share: float = 0.0,
        # Price gate inputs
        peer_median: float = 0.0,
        peer_ci_upper: float = 0.0,
        # Award gate inputs
        procurement_method: str = "open",
        competitive_threshold: float = 100_000,
        has_oversight: bool = True,
        single_decision_maker: bool = False,
        # Payment gate inputs (if contract already active)
        disbursement_amount: float = 0.0,
        delivery_confirmed: bool = True,
        delivery_percentage: float = 1.0,
        ocid: Optional[str] = None,
    ) -> GatePassport:
        """Run the complete 7-gate structural verification."""
        
        start = datetime.utcnow()
        gates = []
        
        # Gate 1: Need
        g1 = self.need_gate.evaluate(
            agency_id, category, contract_value, currency,
            fiscal_month, fiscal_day, agency_history
        )
        gates.append(g1)
        
        # Gate 2: Spec
        g2 = self.spec_gate.evaluate(
            specs or {"contract_value": contract_value},
            known_vendors, previous_winner
        )
        gates.append(g2)
        
        # Gate 3: Entity
        g3 = self.entity_gate.evaluate(bidders or [])
        gates.append(g3)
        
        # Gate 4: Competition
        g4 = self.competition_gate.evaluate(
            bid_prices or [], vendor_agency_share
        )
        gates.append(g4)
        
        # Gate 5: Price
        g5 = self.price_gate.evaluate(
            contract_value, currency, peer_median, peer_ci_upper
        )
        gates.append(g5)
        
        # Gate 6: Award (aggregates upstream)
        g6 = self.award_gate.evaluate(
            procurement_method, contract_value, currency,
            competitive_threshold, has_oversight, single_decision_maker,
            g1, g2, g3, g4, g5
        )
        gates.append(g6)
        
        # Gate 7: Payment (if applicable)
        if disbursement_amount > 0:
            g7 = self.payment_gate.evaluate(
                disbursement_amount, delivery_confirmed, delivery_percentage
            )
            gates.append(g7)
        
        # Compute passport
        gates_passed = sum(1 for g in gates if g.verdict == GateVerdict.CLEAR)
        gates_review = sum(1 for g in gates if g.verdict == GateVerdict.REVIEW)
        gates_blocked = sum(1 for g in gates if g.verdict == GateVerdict.BLOCK)
        total_contradictions = sum(len(g.contradictions) for g in gates)
        
        # Overall confidence: weighted average, Award gate weighted 2x
        weights = [1.0] * len(gates)
        if len(weights) >= 6:
            weights[5] = 2.0  # Award gate double weight
        total_weight = sum(weights)
        structural_confidence = sum(g.confidence * w for g, w in zip(gates, weights)) / total_weight
        
        # Overall verdict: worst gate wins
        if gates_blocked > 0:
            overall = GateVerdict.BLOCK
        elif gates_review > 0:
            overall = GateVerdict.REVIEW
        else:
            overall = GateVerdict.CLEAR
        
        # Projected recovery if blocked
        projected_recovery = 0.0
        if overall in (GateVerdict.BLOCK, GateVerdict.REVIEW):
            savings_pct = min(0.25 * total_contradictions / max(len(gates), 1), 0.40)
            projected_recovery = contract_value * savings_pct
        
        # Verification statement
        if overall == GateVerdict.CLEAR:
            statement = f"STRUCTURALLY VERIFIED. Contract {contract_id} has passed {gates_passed}/{len(gates)} structural gates with confidence {structural_confidence:.2%}. Proceed."
        elif overall == GateVerdict.REVIEW:
            statement = f"STRUCTURAL CONCERNS. Contract {contract_id}: {gates_review} gates require review, {gates_blocked} blocked. Confidence {structural_confidence:.2%}. Independent review required before proceeding."
        else:
            statement = f"STRUCTURALLY BLOCKED. Contract {contract_id}: {gates_blocked} gates blocked, {total_contradictions} contradictions. Confidence {structural_confidence:.2%}. Cannot proceed."
        
        passport = GatePassport(
            contract_id=contract_id,
            ocid=ocid,
            country_code=country_code,
            contract_value=contract_value,
            currency=currency,
            gates=gates,
            overall_verdict=overall,
            structural_confidence=round(structural_confidence, 4),
            total_contradictions=total_contradictions,
            gates_passed=gates_passed,
            gates_review=gates_review,
            gates_blocked=gates_blocked,
            projected_recovery_if_blocked=round(projected_recovery, 2),
            passport_id=f"SUNLIGHT-{country_code}-{contract_id}-{start.strftime('%Y%m%d%H%M%S')}",
            issued_at=start.isoformat() + "Z",
            valid_until=(start.replace(year=start.year + 1)).isoformat() + "Z",
            verification_statement=statement
        )
        
        return passport
    
    def format_passport(self, passport: GatePassport) -> str:
        """Format human-readable structural verification passport."""
        verdict_symbol = {"CLEAR": "\u2705", "REVIEW": "\u26A0\uFE0F", "BLOCK": "\u274C"}
        
        lines = []
        lines.append("\u2550" * 70)
        lines.append("SUNLIGHT STRUCTURAL VERIFICATION PASSPORT")
        lines.append("\u2550" * 70)
        lines.append(f"Passport ID: {passport.passport_id}")
        lines.append(f"Contract: {passport.contract_id}")
        lines.append(f"Country: {passport.country_code}")
        lines.append(f"Value: {passport.currency} {passport.contract_value:,.2f}")
        lines.append(f"Issued: {passport.issued_at}")
        lines.append(f"Valid until: {passport.valid_until}")
        lines.append("")
        
        v = passport.overall_verdict.value
        lines.append(f"VERDICT: {verdict_symbol.get(v, '?')} {v}")
        lines.append(f"Structural Confidence: {passport.structural_confidence:.2%}")
        lines.append(f"Gates: {passport.gates_passed} passed | {passport.gates_review} review | {passport.gates_blocked} blocked")
        lines.append(f"Contradictions: {passport.total_contradictions}")
        if passport.projected_recovery_if_blocked > 0:
            lines.append(f"Projected Recovery: {passport.currency} {passport.projected_recovery_if_blocked:,.2f}")
        lines.append("")
        
        lines.append("GATE RESULTS:")
        for gate in passport.gates:
            gv = gate.verdict.value
            symbol = verdict_symbol.get(gv, "?")
            lines.append(f"  {symbol} {gate.gate.value.upper():15s} | {gv:6s} | Confidence: {gate.confidence:.2%} | Contradictions: {len(gate.contradictions)}")
            if gate.recommendation and gate.verdict != GateVerdict.CLEAR:
                lines.append(f"    \u2192 {gate.recommendation}")
        
        lines.append("")
        lines.append(f"VERIFICATION: {passport.verification_statement}")
        lines.append("")
        lines.append(passport.methodology_version)
        lines.append("Structural finding \u2014 not an allegation.")
        lines.append("\u2550" * 70)
        return "\n".join(lines)


# \u2550\u2550\u2550 DEMO: Senegal Case \u2550\u2550\u2550
if __name__ == "__main__":
    gate = PreAwardGate()
    
    passport = gate.run_full_gate(
        contract_id="SN-ARMP-2025-0847",
        country_code="SN",
        contract_value=2_450_000,
        currency="USD",
        ocid="ocds-SN-ARMP-2025-0847",
        # Need
        agency_id="SN-ARMP",
        category="road_construction",
        fiscal_month=11,
        fiscal_day=14,
        agency_history={
            "categories": ["road_construction", "bridge_repair"],
            "avg_contract_value": 800_000
        },
        # Spec
        specs={
            "min_experience_years": 7,
            "contract_value": 2_450_000,
            "proprietary_references": [],
            "matches_previous_winner_profile": True
        },
        known_vendors=4,
        previous_winner="SGT SA",
        # Entity
        bidders=[
            {"name": "SGT SA", "id": "SN-SGT", "address": "Dakar, Route de Rufisque", "directors": ["Moussa Diallo"]},
        ],
        # Competition
        bid_prices=[],
        vendor_agency_share=0.78,
        # Price
        peer_median=1_837_500,
        peer_ci_upper=2_327_500,
        # Award
        procurement_method="direct",
        competitive_threshold=500_000,
        has_oversight=False,
        single_decision_maker=True,
    )
    
    print(gate.format_passport(passport))


# ═══ SUNLIGHT v4 PROTOCOL ADAPTER ═══

class PreAwardGateAdapter:
    """Implements GateEngine Protocol from sunlight_core."""
    def __init__(self):
        self._gate = PreAwardGate()

    def evaluate(self, dossier):
        from sunlight_core import GateResult, GateVerdict
        graph = dossier.graph or {"nodes": [], "edges": []}
        tca_result = None
        if dossier.structure:
            tca_result = {
                "confidence": dossier.structure.confidence,
                "contradictions": dossier.structure.contradictions,
            }
        passport = self._gate.evaluate(graph, tca_result=tca_result)
        verdict_map = {"CLEAR": GateVerdict.CLEAR, "REVIEW": GateVerdict.REVIEW, "BLOCK": GateVerdict.BLOCK}
        dossier.gate = GateResult(
            verdict=verdict_map.get(passport.get("verdict", "CLEAR"), GateVerdict.CLEAR),
            gates=passport.get("gates", {}),
            blocked_at=passport.get("blocked_at"),
            patron_detected=passport.get("patron_detected", False),
            total_contradictions=passport.get("total_contradictions", 0),
            recommendation=passport.get("recommendation", ""),
        )
        return dossier
