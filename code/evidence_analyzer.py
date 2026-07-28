"""
SUNLIGHT Side 5 — Evidence Corroboration Analyzer
====================================================

Orchestrates the Side 5 pipeline and formats results for the API,
analogous to delivery_analyzer.py for Side 2.

What the output says, and what it refuses to say:
    A corroboration result reports which evidence classes were queried, what
    each returned, which contradicted the claim, and how much of the evidence
    space was reachable in this jurisdiction at all. Every element traces to
    a source, a hash and a timestamp.

    It does not say a facility does not exist. SUNLIGHT cannot inspect
    anything, and no software can. It says that independent evidence is
    structurally inconsistent with the claim as recorded — a finding with a
    documented evidence chain, not an accusation.

    Every formatted result therefore carries its corroboration capacity
    alongside its verdict. UNVERIFIED at two of six reachable classes means
    something entirely different from UNVERIFIED at six of six, and a report
    that states one without the other is misleading by omission.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evidence_pipeline import EvidencePipeline
from evidence_schema import (
    EVIDENCE_CLASS_COUNT,
    CorroborationDossier,
    CorroborationVerdict,
    EvidenceArtifact,
    EvidenceStage,
    ExpectedEvidence,
    OutcomeClaim,
    SourceIndependence,
)


class EvidenceAnalyzer:
    """Runs corroboration analysis and formats the result.

    Mirrors DeliveryAnalyzer: analyze() takes raw inputs, analyze_dossier()
    takes a prepared dossier, batch_analyze() handles many, and stats()
    reports what has been seen.
    """

    def __init__(self, profile=None, profile_name: str = ""):
        self.pipeline = EvidencePipeline(profile=profile)
        self.profile = self.pipeline.profile
        self.profile_name = profile_name or getattr(self.profile, "name", "")
        self._analyzed = 0
        self._verdict_counts: Dict[str, int] = {
            v.value: 0 for v in CorroborationVerdict
        }

    # ── Entry points ─────────────────────────────────────

    def analyze(
        self,
        claim: OutcomeClaim,
        artifacts: Optional[List[EvidenceArtifact]] = None,
        source_registry: Optional[List[SourceIndependence]] = None,
        expected_evidence: Optional[List[ExpectedEvidence]] = None,
        strict: bool = False,
    ) -> Dict[str, Any]:
        """Corroborate a single claim. Stages 13-16."""
        dossier = self.pipeline.run(
            claim=claim,
            artifacts=artifacts,
            source_registry=source_registry,
            expected_evidence=expected_evidence,
            strict=strict,
        )
        return self._format(dossier)

    def analyze_dossier(self, dossier: CorroborationDossier) -> Dict[str, Any]:
        """Corroborate a prepared dossier. Stages 14-16."""
        return self._format(self.pipeline.process(dossier))

    def batch_analyze(self, requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Corroborate many claims and aggregate.

        The aggregate reports UNVERIFIED as its own count, never folded in
        with CONTRADICTED. A country office whose registries are thin will
        accumulate UNVERIFIED results, and a summary that merged the two
        would read as a pattern of contradicted claims — manufacturing at
        portfolio level exactly the injustice the verdict model prevents at
        claim level.
        """
        results = [self.analyze(**req) for req in requests]

        distribution: Dict[str, int] = {v.value: 0 for v in CorroborationVerdict}
        capacity_total = 0.0
        for r in results:
            distribution[r["verdict"]] = distribution.get(r["verdict"], 0) + 1
            capacity_total += r["corroboration_capacity"]

        count = len(results) or 1
        return {
            "results": results,
            "total": len(results),
            "verdict_distribution": distribution,
            "average_corroboration_capacity": round(capacity_total / count, 4),
            "profile": self.profile_name,
        }

    def stats(self) -> Dict[str, Any]:
        return {
            "claims_analyzed": self._analyzed,
            "verdict_distribution": dict(self._verdict_counts),
            "profile": self.profile_name,
        }

    # ── Formatting ───────────────────────────────────────

    def _format(self, dossier: CorroborationDossier) -> Dict[str, Any]:
        self._analyzed += 1
        verdict = dossier.verdict.value if dossier.verdict else None
        if verdict in self._verdict_counts:
            self._verdict_counts[verdict] += 1

        outcome = dossier.gate_outcome

        return {
            "dossier_id": dossier.dossier_id,
            "claim_id": dossier.claim.claim_id,
            "contract_id": dossier.claim.contract_id,
            "outcome_type": dossier.claim.outcome_type.value,
            "country_code": dossier.claim.country_code,
            "country_office": dossier.claim.country_office,

            "verdict": verdict,
            "confidence": dossier.confidence,

            # Capacity travels with the verdict, always. A Side 5 verdict is
            # not interpretable without knowing how far we could see.
            "corroboration_capacity": round(dossier.corroboration_capacity, 4),
            "classes_queryable": dossier.classes_queryable,
            "classes_total": dossier.classes_total,
            "independent_classes_corroborating": dossier.independent_classes_corroborating,

            "dimensions_fired": outcome.dimensions_fired if outcome else 0,
            "dimension_results": [
                {
                    "dimension": d.dimension.value,
                    "fired": d.fired,
                    "observed_value": d.observed_value,
                    "threshold": d.threshold,
                    "detail": d.detail,
                }
                for d in (outcome.dimension_results if outcome else [])
            ],

            "contradictions": dossier.contradictions,
            "coverage_findings": outcome.coverage_findings if outcome else [],

            "rules_evaluated": (
                dossier.rules_result.rules_evaluated if dossier.rules_result else 0),
            "rules_fired": (
                dossier.rules_result.rules_fired if dossier.rules_result else 0),
            "rule_fires": [
                {
                    "rule_id": r.rule_id,
                    "layer": r.layer,
                    "evidence": r.evidence,
                    "legal_basis": r.legal_basis,
                    "confidence": r.confidence,
                    "recommendation": r.recommendation,
                }
                for r in (dossier.rules_result.rule_results if dossier.rules_result else [])
                if r.fired
            ],

            "artifacts_admitted": len(dossier.artifacts),
            "artifacts_rejected": len(dossier.rejected_artifacts),
            "rejections": [
                {
                    "artifact_id": e.get("artifact_id"),
                    "reason": e.get("reason") or e.get("error"),
                }
                for e in dossier.errors
                if e.get("stage") == EvidenceStage.INGESTED.value
            ],

            "graph": {
                "node_count": dossier.graph.node_count if dossier.graph else 0,
                "edge_count": dossier.graph.edge_count if dossier.graph else 0,
            },

            "stage": dossier.stage.value,
            "errors": dossier.errors,
            "processing_ms": dossier.processing_ms,
            "methodology_note": outcome.methodology_note if outcome else "",
            "methodology_version": dossier.methodology_version,
            "disclaimer": dossier.disclaimer,
            "profile": self.profile_name,
        }


def summarise_capacity(country_code: str, profile=None) -> Dict[str, Any]:
    """What SUNLIGHT can and cannot verify in a given jurisdiction.

    Backs GET /evidence/capacity/{country_code}. Honest disclosure of the
    capability ceiling is a feature: an institution is entitled to know,
    before it submits anything, which evidence classes are reachable in a
    country and therefore what the strongest available conclusion is.

    Where fewer than the profile minimum are reachable, the strongest
    available conclusion is UNVERIFIED — and saying so up front is better
    than returning it later without explanation.
    """
    from evidence_evg import DEFAULT_MIN_CORROBORATION_CAPACITY
    from evidence_rules import (
        DEFAULT_MIN_QUERYABLE_CLASSES,
        _get_evidence_param,
    )
    from evidence_schema import EvidenceClass

    raw = _get_evidence_param(profile, "queryable_classes", None)
    queryable: List[str] = []
    if raw:
        for name in raw:
            try:
                queryable.append(EvidenceClass(name).value)
            except ValueError:
                continue

    min_queryable = _get_evidence_param(
        profile, "min_queryable_classes", DEFAULT_MIN_QUERYABLE_CLASSES)
    min_capacity = _get_evidence_param(
        profile, "min_corroboration_capacity", DEFAULT_MIN_CORROBORATION_CAPACITY)

    capacity = len(queryable) / EVIDENCE_CLASS_COUNT if EVIDENCE_CLASS_COUNT else 0.0
    unreachable = [
        c.value for c in EvidenceClass if c.value not in queryable
    ]

    adverse_available = (
        len(queryable) >= min_queryable and capacity >= min_capacity
    )

    return {
        "country_code": country_code,
        "queryable_classes": sorted(queryable),
        "unqueryable_classes": sorted(unreachable),
        "classes_queryable": len(queryable),
        "classes_total": EVIDENCE_CLASS_COUNT,
        "corroboration_capacity_ceiling": round(capacity, 4),
        "min_queryable_classes": min_queryable,
        "min_corroboration_capacity": min_capacity,
        "adverse_conclusion_available": adverse_available,
        "strongest_available_conclusion": (
            CorroborationVerdict.VERIFIED.value if adverse_available
            else CorroborationVerdict.UNVERIFIED.value
        ),
        "note": (
            "Corroboration capacity is a property of the jurisdiction's "
            "available data sources, not of any project or claim within it. "
            "Where capacity is below the floor, no adverse conclusion is "
            "available and every verdict is UNVERIFIED. Absence of reachable "
            "evidence is not evidence of absence."
        ),
    }
