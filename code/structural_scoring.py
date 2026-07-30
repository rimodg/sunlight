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

# Decimal places for every published score. Rounding happens once, at
# computation, so the composite is the exact mean of the published
# sub-scores and an evaluator with a calculator reaches the same number.
SCORE_PRECISION = 6

COMPOSITE_FORMULA = (
    "round(mean(determinate sub-scores), 6) — indeterminate axes are excluded "
    "from the mean, never counted as zero"
)

# ═══════════════════════════════════════════════════════════
# DETERMINACY — WHICH AXES HAD A BASIS FOR ASSESSMENT
#
# A sub-score of 0.0 and an axis that could not be assessed are epistemically
# opposite, and displaying them identically is the single most misleading
# thing this output layer could do. "Compared against context and found
# clean" is a finding. "No basis to look" is not a finding at all.
#
# CRITICAL DISTINCTION, established by reading every rule condition: the four
# structural sub-scores do NOT use corpus comparables. The word "comparable"
# does not appear in tca_rules.py. Every contradiction-capable condition reads
# intra-contract fields — procurement method, bidder count, the contract's own
# tender-vs-award values, its own party list, its own award date.
#
# Comparables belong to the CRI price engine (institutional_pipeline), which
# is a DIFFERENT axis and is not one of these four. So determinacy here is
# INPUT AVAILABILITY, not peer availability: an axis is determinate when the
# fields its rules read are actually present on the contract.
#
# Each axis lists the feature keys its contradiction-capable rules read. Any
# one of them present makes the axis assessable, because a rule that can fire
# has something to fire on.
# ═══════════════════════════════════════════════════════════

STATUS_DETERMINATE = "RELATIONALLY-DERIVED WITH SUFFICIENT CONTEXT"
STATUS_INDETERMINATE = "INDETERMINATE (insufficient context)"

CONTEXT_FULL = "full"
CONTEXT_REDUCED = "reduced"
CONTEXT_SINGLE_AXIS = "single-axis"
CONTEXT_NONE = "none"

# Determinacy is per-axis and mirrors what that axis's rules genuinely
# require, not mere key presence. A generic "any field non-empty" test is too
# permissive and produces exactly the false clean-zero this section exists to
# prevent: a contract with one supplier and no addresses has NOTHING for the
# entity rules to evaluate, yet carries a non-empty country_code.
#
# Each entry names the requirement in the rules' own terms and the rules that
# depend on it, so the check can be audited against the registry by eye.
AXIS_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "procedural_score": {
        "rules": ("PROC-001", "PROC-002", "PROC-003"),
        "requires": "oversight flag, or procurement method, or bidder count",
        # PROC-003 evaluates `not has_review_body`, so oversight is assessable
        # from any contract at all. This axis is therefore effectively always
        # determinate — which is correct, not a loophole: whether a
        # procurement record names a review body is always a fact about it.
        "check": lambda f: (
            f.get("has_review_body") is not None
            or bool(f.get("procurement_method"))
            or f.get("number_of_tenderers") is not None
        ),
    },
    "financial_score": {
        "rules": ("FIN-001",),
        "requires": "both tender_value and award_value present and non-zero",
        # FIN-001 compares the two. One value alone compares to nothing.
        "check": lambda f: (f.get("tender_value") or 0) > 0
                           and (f.get("award_value") or 0) > 0,
    },
    "temporal_score": {
        "rules": ("TIME-001",),
        "requires": "an award date (month and day)",
        "check": lambda f: (f.get("award_month") is not None
                            and f.get("award_day") is not None),
    },
    "network_score": {
        "rules": ("ENT-001", "ENT-002", "GEO-001"),
        "requires": ("two or more supplier addresses, or two or more supplier "
                     "identifiers, or both a contract country and supplier "
                     "countries"),
        # Every network rule needs a RELATIONSHIP — a pair to compare. One
        # supplier with no address and no country is not a clean network, it
        # is an unassessable one.
        "check": lambda f: (
            len(f.get("supplier_addresses") or []) >= 2
            or len(f.get("supplier_ids") or []) >= 2
            or (bool(f.get("country_code")) and bool(f.get("supplier_countries")))
        ),
    },
}


def assess_determinacy(features: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per-axis determinacy from the same features the rules read.

    With no features supplied at all, every axis is INDETERMINATE. That is the
    honest default: a caller that did not tell us what the contract contains
    has given us no basis to assess anything, and defaulting to determinate
    would manufacture confidence.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for axis, spec in AXIS_REQUIREMENTS.items():
        if not features:
            out[axis] = {
                "determinate": False,
                "status": STATUS_INDETERMINATE,
                "requires": spec["requires"],
                "rules_on_axis": list(spec["rules"]),
                "reason": "no contract features supplied to the scoring layer",
            }
            continue
        try:
            determinate = bool(spec["check"](features))
        except Exception:
            determinate = False
        out[axis] = {
            "determinate": determinate,
            "status": STATUS_DETERMINATE if determinate else STATUS_INDETERMINATE,
            "requires": spec["requires"],
            "rules_on_axis": list(spec["rules"]),
            "reason": (
                f"inputs present: {spec['requires']}" if determinate else
                f"this contract carries none of: {spec['requires']} — "
                f"no rule on this axis ({', '.join(spec['rules'])}) has "
                f"anything to evaluate"
            ),
        }
    return out


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

    # ── ENT-003 maps to NOTHING, and this was wrong before ──
    #
    # Originally mapped to F7 (spending/market concentration) as CONFIRMS, on
    # the strength of its name, "Single supplier dominance". Reading the rule
    # rather than its title shows that is not what it detects:
    #
    #   condition : supplier_count == 1 and number_of_tenderers >= 3
    #   edge      : EXPRESSES  (not REMOVES/SEEKS/VERIFIES — ignored for scoring)
    #   its own description: "Single supplier won against N bidders —
    #                        normal competitive outcome"
    #
    # It marks a NORMAL competitive result: one winner among three or more
    # genuine bidders. Mapping it to a corruption-risk flag as a confirmation
    # would have told an institution SUNLIGHT structurally confirms market
    # concentration when nothing in the engine measures concentration at all.
    #
    # No output was ever wrong, because the EXPRESSES edge means this rule
    # cannot reach the scoring layer. The published mapping table would have
    # been, which is worse: the table is the artefact an institution reads.
    "ENT-003": FazekasMapping(
        (), RELATIONSHIP_NONE,
        NO_CRI_LABEL + " Despite its name, this rule marks a NORMAL "
        "competitive outcome — a single winner among three or more bidders — "
        "not concentration. No TCA rule measures spending or market "
        "concentration, so SUNLIGHT does not confirm F7."),

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
    score: Optional[float]          # None when INDETERMINATE — never 0.0
    raw_weight: float
    denominator: int
    determinate: bool = True
    status: str = STATUS_DETERMINATE
    reason: str = ""
    requires: str = ""
    rules_on_axis: List[str] = field(default_factory=list)
    findings: List[ScoredFinding] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            # None, not 0.0, when the axis had no basis for assessment. A
            # consumer that treats null as zero is making a claim the data
            # does not support, and the status field says so in words.
            "score": self.score,
            "determinate": self.determinate,
            "status": self.status,
            "reason": self.reason,
            "requires_for_assessment": self.requires,
            "rules_on_axis": self.rules_on_axis,
            "raw_weight": round(self.raw_weight, 6),
            "denominator": self.denominator,
            "formula": ("min(1.0, raw_weight / denominator)" if self.determinate
                        else "not computed — axis indeterminate"),
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
    determinacy: Optional[Dict[str, Dict[str, Any]]] = None,
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

        det = (determinacy or {}).get(name)
        # No determinacy supplied means the caller made no claim about input
        # availability. Treat the axis as determinate so behaviour matches the
        # pre-determinacy layer for callers that pass findings alone.
        is_det = True if det is None else bool(det.get("determinate"))

        # A rule that fired is itself proof its inputs were present. An axis
        # cannot be indeterminate while carrying evidence.
        if scored:
            is_det = True

        if not is_det:
            score = None
        elif denominator <= 0:
            score = 0.0
        else:
            # Rounded HERE, once, so the value used in the composite is the
            # same value published in the response. Rounding independently at
            # serialisation made the published sub-scores fail to reconstruct
            # the published composite in the 7th decimal — which quietly
            # breaks the "verify the rollup by hand" property the formula is
            # published for.
            score = round(min(1.0, raw / denominator), SCORE_PRECISION)

        out[name] = SubScore(
            name=name, score=score, raw_weight=raw, denominator=denominator,
            determinate=is_det,
            status=STATUS_DETERMINATE if is_det else STATUS_INDETERMINATE,
            reason=(det or {}).get("reason", "") if det else "",
            requires=(det or {}).get("requires", "") if det else "",
            rules_on_axis=(det or {}).get("rules_on_axis", []) if det else [],
            findings=scored,
        )

    return out


def compute_composite(sub_scores: Dict[str, SubScore]) -> Optional[float]:
    """Arithmetic mean over DETERMINATE axes only.

    Still the plainest possible rollup — a weighted composite would encode a
    claim about which kind of structural risk matters most, which is an
    institutional judgement rather than a technical finding, and would make
    the number impossible to check by hand.

    What changed: an axis with no basis for assessment is EXCLUDED from the
    mean rather than entered as zero. Entering it as zero would let the
    absence of information pull the score toward clean, which is the same
    error in the opposite direction from treating absence as guilt. An
    unassessable axis should move the score neither way; it should narrow the
    claim the score is making, and the context qualification is what carries
    that.

    Returns None when NO axis is determinate. There is no honest number to
    report in that case, and a zero would be a fabricated clean bill.
    """
    determinate = [s.score for s in sub_scores.values()
                   if s.determinate and s.score is not None]
    if not determinate:
        return None
    return round(sum(determinate) / len(determinate), SCORE_PRECISION)


def assess_context(sub_scores: Dict[str, SubScore]) -> Dict[str, Any]:
    """How much of the evidence space the composite actually rests on.

    THE GUARD. A composite over one axis is not the same epistemic object as a
    composite over four, and must never present as though it were. A
    single-axis result is explicitly qualified as low-context so no consumer
    can read it as a whole-contract assessment.
    """
    total = len(sub_scores)
    populated = [n for n, s in sub_scores.items() if s.determinate and s.score is not None]
    n = len(populated)

    if n == 0:
        level, note = CONTEXT_NONE, (
            "No axis had a basis for assessment. No composite is reported: a "
            "score here would be fabricated, not conservative.")
    elif n == 1:
        level, note = CONTEXT_SINGLE_AXIS, (
            f"LOW CONTEXT — the composite rests on ONE axis ({populated[0]}) of "
            f"{total}. This is not a whole-contract assessment and must not be "
            f"read as one. A score derived from a single axis is a different "
            f"epistemic object from one derived from four.")
    elif n < total:
        level, note = CONTEXT_REDUCED, (
            f"REDUCED CONTEXT — computed on {n} of {total} axes. The "
            f"{total - n} indeterminate axis/axes are excluded from the mean, "
            f"not counted as zero.")
    else:
        level, note = CONTEXT_FULL, (
            f"FULL CONTEXT — all {total} axes had a basis for assessment.")

    return {
        "context_level": level,
        "axes_total": total,
        "axes_populated": n,
        "axes_determinate": sorted(populated),
        "axes_indeterminate": sorted(n_ for n_, s in sub_scores.items()
                                     if not (s.determinate and s.score is not None)),
        "low_context": n <= 1,
        "note": note,
    }


# The only field in the scoring output that varies between identical runs.
#
# computed_at is provenance — WHEN the score was produced — not part of the
# corpus state the score depends on. Determinism is therefore asserted over
# everything else, exactly as the handover expected-outputs strip
# processing_time_ms. Naming it here rather than leaving callers to discover
# it means a consumer diffing two results knows which difference is meaningless.
VOLATILE_STAMP_FIELDS = ("computed_at",)


def strip_volatile(scoring: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of the scoring output with volatile provenance removed.

    The canonical form for determinism checks and for storing expected
    outputs. Same contract + same corpus state + same profile must produce a
    byte-identical result under this transform.
    """
    import copy
    out = copy.deepcopy(scoring)
    stamp = out.get("corpus_stamp")
    if isinstance(stamp, dict):
        for f in VOLATILE_STAMP_FIELDS:
            stamp.pop(f, None)
    return out


def corpus_stamp(
    comparable_count: int = 0,
    comparable_ids: Optional[List[str]] = None,
    profile_name: str = "",
    profile_version: str = "",
    computed_at: Optional[str] = None,
) -> Dict[str, Any]:
    """The corpus state a score was computed against.

    A score is only reproducible against the comparison set that produced it.
    Without this stamp, the same contract scoring differently next quarter is
    indistinguishable from drift — and "the corpus grew" and "the engine
    changed" are very different explanations to owe an institution.

    The fingerprint is a digest of the sorted comparison-set identifiers, so
    it is stable under reordering and changes when membership changes. Empty
    comparison set yields a NULL fingerprint rather than the digest of an
    empty string, so "no corpus" cannot be confused with "a corpus that
    happened to hash to that".
    """
    import hashlib

    ids = sorted(comparable_ids or [])
    if ids:
        digest = hashlib.sha256("\x1f".join(ids).encode("utf-8")).hexdigest()[:16]
    else:
        digest = None

    return {
        "comparison_set_size": comparable_count,
        "corpus_fingerprint": digest,
        "fingerprint_basis": ("sha256 of sorted comparison-set identifiers, "
                              "first 16 hex chars"),
        "jurisdiction_profile": profile_name,
        "jurisdiction_profile_version": profile_version,
        "computed_at": computed_at,
        "volatile_fields": list(VOLATILE_STAMP_FIELDS),
        "note": (
            "A score is reproducible only against the corpus state recorded "
            "here. A later score change for the same contract must be "
            "attributable to a documented change in this stamp, never left "
            "indistinguishable from drift."
        ),
    }


def score_findings(
    findings: List[Dict[str, Any]],
    cutoffs: Optional[BandCutoffs] = None,
    layer_counts: Optional[Dict[str, int]] = None,
    features: Optional[Dict[str, Any]] = None,
    stamp: Optional[Dict[str, Any]] = None,
    isolation: bool = False,
) -> Dict[str, Any]:
    """Full three-tier output for a set of attributed findings.

    `findings` are dicts carrying at least rule_id, layer and severity — the
    shape the API's Contradiction model produces after rule attribution.

    `features` is the same feature dict the rules read. Supplying it enables
    per-axis determinacy; omitting it treats all axes as determinate, which
    preserves behaviour for callers that pass findings alone.

    `isolation` marks a single-contract assessment, so the output announces
    its own context rather than leaving a consumer to infer it.
    """
    cutoffs = cutoffs or DEFAULT_CUTOFFS
    determinacy = assess_determinacy(features) if features is not None else None
    subs = compute_sub_scores(findings, layer_counts=layer_counts,
                              determinacy=determinacy)
    composite = compute_composite(subs)
    context = assess_context(subs)

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
        "composite_structural_score": None if composite is None else round(composite, 6),
        "composite_formula": COMPOSITE_FORMULA,
        "composite_computed_over": context["axes_determinate"],
        "assessment_context": context,
        "assessment_mode": "isolation (single contract)" if isolation else "corpus-contextual",
        "isolation_assessment": isolation,
        "isolation_note": (
            "SINGLE-CONTRACT (ISOLATION) ASSESSMENT. Axes whose rules require "
            "party, value or date fields absent from this contract are reported "
            "INDETERMINATE and excluded from the composite — not scored zero. "
            "Note that the four structural axes do not use corpus comparables; "
            "the CRI price axis does, and is reported separately in "
            "gate_outcome."
        ) if isolation else None,
        "corpus_stamp": stamp if stamp is not None else corpus_stamp(),
        "sub_scores": {name: s.as_dict() for name, s in subs.items()},
        "interpretation_band": (None if composite is None
                                else cutoffs.band_for(composite)),
        "band_qualification": (
            "NOT REPORTED — no axis was determinate" if composite is None
            else "LOW CONTEXT — band rests on a single axis" if context["low_context"]
            else f"computed on {context['axes_populated']} of {context['axes_total']} axes"),
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
            "verified by hand from the determinate sub-scores, each sub-score "
            "from its decomposition, and each finding from its rule. "
            "An INDETERMINATE axis reports null, never 0.0: no basis to assess "
            "is not the same as assessed and found clean, and the two must "
            "never render alike. A score is a structural risk measurement, "
            "not an allegation."
        ),
    }
