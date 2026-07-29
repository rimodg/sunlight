"""
SUNLIGHT — Three-Tier Structural Scoring and Fazekas CRI Mapping
==================================================================

An OUTPUT LAYER. It reads findings the detection engines already produced and
expresses them as a decomposable score. It computes no detection, changes no
threshold, and is not consulted by any verdict. Remove this module and every
existing response field is byte-identical.

WHY THREE TIERS.
    A single verdict answers "is this bad" and nothing else. An institution
    being asked to act on a finding needs to know which KIND of risk, how much
    of it, and from which rule — and needs to be able to rebuild the number by
    hand. So the output decomposes all the way down:

        Tier 3  interpretation band   <- institution's cutoffs, not ours
        Tier 2  composite score       <- mean of the four sub-scores
        Tier 1  sub-score vector      <- per-layer, from fired rules
                findings              <- rule_id, citation, contribution

    Every level is reconstructable from the level below it. The composite is
    a plain arithmetic mean, published in the response as a string so an
    evaluator can verify the rollup with a calculator.

WHY THE INSTITUTION OWNS THE BANDS.
    SUNLIGHT reports where a contract falls on a 0-1 scale. Where the lines
    sit between GREEN, YELLOW and RED is a policy question about
    investigative capacity and risk appetite, not a technical one, and an
    institution that cannot move those lines cannot own the output. Cutoffs
    are configurable and the ones actually used are stated in every response.

WHY THE FAZEKAS MAPPING EXISTS.
    Fazekas & Kocsis (2020) defines the seven-flag Corruption Risk Index that
    UNDP and GTI standardised on in 2024. Institutions already trust it. So
    every SUNLIGHT finding declares its correspondence to that index: which
    flag it confirms, or explicitly that no flag corresponds.

    The second case is the important one. A finding with no CRI counterpart
    is a risk the institution's existing index cannot see at all — not
    because the index is wrong, but because indicator-based methods measure
    observable procedural attributes, while structural analysis measures
    contradictions in the dependency topology. Naming those precisely is how
    an institution learns where its instrument is blind.

    The mapping is deliberately CONSERVATIVE. Where correspondence is partial
    it is labelled "related", never "confirms". Three of the seven flags — F2,
    F4, F5 — have no TCA rule that confirms them, and the module says so
    rather than stretching a rule to cover them.

Determinism: no ML, no stochastic weighting, no wall-clock. Same findings in,
same scores out, forever.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════
# SECTION 1: THE FOUR SUB-SCORES
# ═══════════════════════════════════════════════════════════

# Sub-score name -> the TCA rule layers that feed it.
#
# Five engine layers collapse to four sub-scores: `entity` and `network` both
# describe relationships between parties (shared addresses, duplicate
# identifiers, supplier dominance, jurisdiction mismatch) and are reported
# together as the network dimension.
SUBSCORE_LAYERS: Dict[str, tuple] = {
    "procedural_score": ("procurement",),
    "financial_score": ("financial",),
    "temporal_score": ("temporal",),
    "network_score": ("entity", "network"),
}

SUBSCORE_NAMES = tuple(SUBSCORE_LAYERS)

# Contribution weight by finding class.
#
# A contradiction is a REMOVES edge: the structure actively conflicts with
# itself. An unproven dependency is a SEEKS edge: a required relationship is
# not evidenced, which is weaker. Half-weight rather than a tuned constant —
# the engine gives no basis for a finer distinction, and inventing one would
# be editorial judgement presented as measurement.
SEVERITY_WEIGHTS: Dict[str, float] = {
    "high": 1.0,
    "medium": 0.5,
}
DEFAULT_SEVERITY_WEIGHT = 0.5

COMPOSITE_FORMULA = "mean(procedural_score, financial_score, temporal_score, network_score)"


# ═══════════════════════════════════════════════════════════
# SECTION 2: FAZEKAS CRI FLAGS
# ═══════════════════════════════════════════════════════════

FAZEKAS_FLAGS: Dict[str, str] = {
    "F1": "Single bidding",
    "F2": "No call for tender published",
    "F3": "Non-open or exceptional procedure",
    "F4": "Short advertisement period",
    "F5": "Subjective or hard-to-quantify evaluation criteria",
    "F6": "Short or anomalous decision/award period",
    "F7": "Spending or market concentration",
}

FAZEKAS_CITATION = (
    "Fazekas & Kocsis (2020), Corruption Risk Index; "
    "standardised by UNDP/GTI (2024)"
)

RELATIONSHIP_CONFIRMS = "confirms"
RELATIONSHIP_RELATED = "related"
RELATIONSHIP_NONE = "none"

NO_CRI_LABEL = (
    "NO corresponding CRI indicator — structural-only finding. "
    "Not visible to indicator-based methods."
)
BEYOND_PARADIGM_LABEL = (
    "NO corresponding CRI indicator — beyond the indicator paradigm."
)
CONFIRMS_LABEL = "CONFIRMS existing CRI indicator (structural verification)."


@dataclass(frozen=True)
class FazekasMapping:
    flags: tuple
    relationship: str
    note: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "flags": list(self.flags),
            "flag_names": [FAZEKAS_FLAGS[f] for f in self.flags],
            "relationship": self.relationship,
            "note": self.note,
        }


_NONE_STRUCTURAL = FazekasMapping((), RELATIONSHIP_NONE, NO_CRI_LABEL)
_NONE_BEYOND = FazekasMapping((), RELATIONSHIP_NONE, BEYOND_PARADIGM_LABEL)


# rule_id -> FazekasMapping. Fixed and conservative: correspondence is
# asserted only where the rule genuinely measures what the flag measures.
RULE_FAZEKAS_MAP: Dict[str, FazekasMapping] = {

    # ── Missing competitive process → F1 + F3 ──
    "PROC-001": FazekasMapping(
        ("F1", "F3"), RELATIONSHIP_CONFIRMS,
        CONFIRMS_LABEL + " A direct award above the competitive threshold is "
        "both a non-open procedure (F3) and, by construction, an award "
        "without competing bids (F1). SUNLIGHT confirms it structurally, "
        "from the award-to-process dependency rather than from a "
        "procedure-type field that can be mislabelled."),

    "PROC-002": FazekasMapping(
        ("F1",), RELATIONSHIP_CONFIRMS,
        CONFIRMS_LABEL + " Single bidding is F1 exactly."),

    # Fewer bidders than the threshold is adjacent to single bidding without
    # being it. Labelled related, not confirms.
    "PROC-005": FazekasMapping(
        ("F1",), RELATIONSHIP_RELATED,
        "RELATED to F1, not identical. F1 measures a single bid; this "
        "measures a bidder count below the competitive floor. Directionally "
        "the same risk, a different measurement."),

    # ── Oversight: no CRI counterpart ──
    "PROC-003": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " No Fazekas flag measures whether an oversight body "
        "exists in the procurement record. The index measures attributes of "
        "the tender; this measures a missing institutional dependency."),

    "PROC-004": _NONE_STRUCTURAL,

    # ── Concentration → F7 ──
    "ENT-003": FazekasMapping(
        ("F7",), RELATIONSHIP_CONFIRMS,
        CONFIRMS_LABEL + " Supplier dominance is the concentration F7 "
        "measures."),

    # ── Entity-relationship findings: structural-only ──
    "ENT-001": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " Bidders sharing a registered address is a "
        "relationship between entities. No Fazekas flag inspects entity "
        "relationships; the index would see a competitive tender."),

    "ENT-002": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " Duplicate entity identifiers among bidders is a "
        "contradiction in the party topology. An indicator-based method "
        "counts the bidders and sees competition."),

    # ── Financial: structural-only ──
    "FIN-001": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " No Fazekas flag compares the award against the "
        "tender estimate. The seven flags describe how a contract was "
        "advertised and decided, not whether its value moved."),

    "FIN-002": _NONE_STRUCTURAL,
    "FIN-003": _NONE_STRUCTURAL,

    # ── Temporal → F6, related only ──
    "TIME-001": FazekasMapping(
        ("F6",), RELATIONSHIP_RELATED,
        "RELATED to F6, not identical. F6 measures the length of the "
        "decision or award interval. This measures clustering against the "
        "fiscal calendar — a budget-exhaustion signal F6 does not capture. "
        "Reported as related so no evaluator reads it as an F6 confirmation."),

    "TIME-002": FazekasMapping(
        ("F6",), RELATIONSHIP_RELATED,
        "RELATED to F6, not identical. Final-quarter clustering is a "
        "fiscal-calendar signal, not the decision-interval anomaly F6 "
        "measures."),

    "TIME-003": _NONE_STRUCTURAL,

    # ── Jurisdiction: structural-only ──
    "GEO-001": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " Supplier jurisdiction mismatch is a dependency "
        "between the supplier and the contract's execution country. No "
        "Fazekas flag examines it."),

    "GEO-002": _NONE_STRUCTURAL,
}

# Findings originating outside Side 1 have no CRI counterpart by construction:
# the index describes a procurement event, and these describe what happened
# after it. Matched by rule_id prefix.
NON_PROCUREMENT_PREFIXES = ("DEL-", "EVD-", "REC-")


def fazekas_mapping_for(rule_id: str) -> FazekasMapping:
    """The CRI correspondence for one rule. Never guesses.

    An unknown rule maps to nothing rather than to a plausible flag. A wrong
    confirmation would tell an institution its index already covers a risk it
    does not cover, which is worse than reporting no correspondence.
    """
    if not rule_id:
        return _NONE_STRUCTURAL
    if rule_id.startswith(NON_PROCUREMENT_PREFIXES):
        return _NONE_BEYOND
    return RULE_FAZEKAS_MAP.get(rule_id, _NONE_STRUCTURAL)


def flags_never_confirmed() -> List[str]:
    """Fazekas flags no TCA rule confirms. Disclosed, not hidden.

    F2, F4 and F5 concern publication and evaluation-criteria attributes that
    the structural engine does not model. An institution should know which
    parts of its own index SUNLIGHT does not corroborate.
    """
    confirmed = set()
    for m in RULE_FAZEKAS_MAP.values():
        if m.relationship == RELATIONSHIP_CONFIRMS:
            confirmed.update(m.flags)
    return sorted(set(FAZEKAS_FLAGS) - confirmed)


# ═══════════════════════════════════════════════════════════
# SECTION 3: BAND CUTOFFS (TIER 3)
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class BandCutoffs:
    """Where the institution draws its lines.

    Defaults are documented starting points, not assertions about what is
    corrupt. An institution with three investigators and one with three
    hundred should not be forced to the same threshold.
    """
    green_below: float = 0.3
    red_at_or_above: float = 0.6
    green_label: str = "GREEN"
    yellow_label: str = "YELLOW"
    red_label: str = "RED"

    def validate(self) -> List[str]:
        warnings: List[str] = []
        if not 0.0 <= self.green_below <= 1.0:
            warnings.append(f"green_below={self.green_below} outside [0,1]")
        if not 0.0 <= self.red_at_or_above <= 1.0:
            warnings.append(f"red_at_or_above={self.red_at_or_above} outside [0,1]")
        if self.green_below > self.red_at_or_above:
            warnings.append(
                f"green_below={self.green_below} exceeds "
                f"red_at_or_above={self.red_at_or_above}; the YELLOW band is "
                f"inverted and nothing can fall in it")
        return warnings

    def band_for(self, score: float) -> str:
        if score < self.green_below:
            return self.green_label
        if score >= self.red_at_or_above:
            return self.red_label
        return self.yellow_label

    def as_dict(self) -> Dict[str, Any]:
        return {
            "green_below": self.green_below,
            "yellow_from": self.green_below,
            "yellow_below": self.red_at_or_above,
            "red_at_or_above": self.red_at_or_above,
            "note": (
                "Cutoffs are set by the deploying institution. SUNLIGHT "
                "reports where a contract falls on a 0-1 scale; where the "
                "lines sit is a policy decision about investigative capacity "
                "and risk appetite. Changing them changes the band and never "
                "the score."
            ),
        }


DEFAULT_CUTOFFS = BandCutoffs()


# ═══════════════════════════════════════════════════════════
# SECTION 4: SCORING
# ═══════════════════════════════════════════════════════════


@dataclass
class ScoredFinding:
    rule_id: str
    rule_name: str
    layer: str
    severity: str
    evidence: str
    legal_citation: str
    contribution: float
    subscore: str
    fazekas: FazekasMapping

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "layer": self.layer,
            "severity": self.severity,
            "evidence": self.evidence,
            "legal_citation": self.legal_citation,
            "contribution": round(self.contribution, 6),
            "sub_score": self.subscore,
            "fazekas_mapping": self.fazekas.as_dict(),
        }


@dataclass
class SubScore:
    name: str
    score: float
    raw_weight: float
    denominator: int
    findings: List[ScoredFinding] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 6),
            "raw_weight": round(self.raw_weight, 6),
            "denominator": self.denominator,
            "formula": "min(1.0, raw_weight / denominator)",
            "rules_fired": len(self.findings),
            "decomposition": [f.as_dict() for f in self.findings],
        }


def _layer_rule_counts() -> Dict[str, int]:
    """How many rules each engine layer contains. The sub-score denominator.

    Read from the live registry rather than hardcoded, so adding a rule
    changes the normalisation automatically instead of silently skewing it.
    """
    try:
        from tca_rules import RULES
    except ImportError:
        return {}
    counts: Dict[str, int] = {}
    for r in RULES:
        counts[r.layer] = counts.get(r.layer, 0) + 1
    return counts


def compute_sub_scores(
    findings: List[Dict[str, Any]],
    layer_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, SubScore]:
    """Four sub-scores from attributed findings.

    Each is the weighted share of its layers' rule set that fired:

        raw_weight = sum of contribution weights of fired findings
        denominator = number of rules registered in those layers
        score = min(1.0, raw_weight / denominator)

    The denominator counts every rule in the layer, including the exculpatory
    ones (an oversight body being present, an award matching its tender).
    That makes the scale conservative — a layer cannot reach 1.0 unless
    effectively all of its rules fire as contradictions — and conservative is
    the correct direction for an instrument whose output triggers
    investigations.
    """
    counts = layer_counts if layer_counts is not None else _layer_rule_counts()
    out: Dict[str, SubScore] = {}

    for name, layers in SUBSCORE_LAYERS.items():
        denominator = sum(counts.get(layer, 0) for layer in layers)
        scored: List[ScoredFinding] = []
        raw = 0.0

        for f in findings:
            if f.get("layer") not in layers:
                continue
            severity = f.get("severity", "medium")
            weight = SEVERITY_WEIGHTS.get(severity, DEFAULT_SEVERITY_WEIGHT)
            raw += weight
            rule_id = f.get("rule_id", "")
            scored.append(ScoredFinding(
                rule_id=rule_id,
                rule_name=f.get("rule_name", ""),
                layer=f.get("layer", ""),
                severity=severity,
                evidence=f.get("evidence", ""),
                legal_citation=f.get("legal_citation", ""),
                contribution=weight,
                subscore=name,
                fazekas=fazekas_mapping_for(rule_id),
            ))

        score = 0.0 if denominator <= 0 else min(1.0, raw / denominator)
        out[name] = SubScore(name=name, score=score, raw_weight=raw,
                             denominator=denominator, findings=scored)

    return out


def compute_composite(sub_scores: Dict[str, SubScore]) -> float:
    """Simple arithmetic mean of the four sub-scores.

    Deliberately the plainest possible rollup. A weighted composite would
    encode a claim about which kind of structural risk matters most, which is
    an institutional judgement rather than a technical finding, and it would
    make the number impossible to check by hand. Fazekas averages its flags
    the same way.
    """
    if not sub_scores:
        return 0.0
    return sum(s.score for s in sub_scores.values()) / len(sub_scores)


def score_findings(
    findings: List[Dict[str, Any]],
    cutoffs: Optional[BandCutoffs] = None,
    layer_counts: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Full three-tier output for a set of attributed findings.

    `findings` are dicts carrying at least rule_id, layer and severity — the
    shape the API's Contradiction model produces after rule attribution.
    """
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    subs = compute_sub_scores(findings, layer_counts=layer_counts)
    composite = compute_composite(subs)

    scored = [f for s in subs.values() for f in s.findings]

    confirmed: Dict[str, str] = {}
    blind: List[Dict[str, Any]] = []
    for f in scored:
        if f.fazekas.relationship == RELATIONSHIP_CONFIRMS:
            for flag in f.fazekas.flags:
                confirmed[flag] = FAZEKAS_FLAGS[flag]
        elif f.fazekas.relationship == RELATIONSHIP_NONE:
            blind.append({
                "rule_id": f.rule_id,
                "rule_name": f.rule_name,
                "evidence": f.evidence,
                "note": f.fazekas.note,
            })

    return {
        "composite_structural_score": round(composite, 6),
        "composite_formula": COMPOSITE_FORMULA,
        "sub_scores": {name: s.as_dict() for name, s in subs.items()},
        "interpretation_band": cutoffs.band_for(composite),
        "band_cutoffs": cutoffs.as_dict(),
        "findings": [f.as_dict() for f in scored],
        "cri_confirmed_flags": [
            {"flag": k, "name": v} for k, v in sorted(confirmed.items())
        ],
        "cri_blind_findings": blind,
        "cri_flags_never_confirmed": [
            {"flag": f, "name": FAZEKAS_FLAGS[f]} for f in flags_never_confirmed()
        ],
        "cri_reference": FAZEKAS_CITATION,
        "methodology_note": (
            "Structural scoring is an output layer. It re-expresses findings "
            "the detection engines already produced and does not participate "
            "in detection: no verdict, threshold or gate consults it. "
            "composite = " + COMPOSITE_FORMULA + ", so the rollup can be "
            "verified by hand from the four sub-scores, each sub-score from "
            "its decomposition, and each finding from its rule. "
            "A score is a structural risk measurement, not an allegation."
        ),
    }
