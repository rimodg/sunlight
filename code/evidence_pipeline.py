"""
SUNLIGHT Side 5 — Evidence Corroboration Pipeline
====================================================

Stages 13-16, extending the existing 12.

Pipeline Stages:
    Stage 13 — Ingestion:   Raw evidence → CorroborationDossier, provenance
                            validated on every artifact
    Stage 14 — Resolution:  Expected-evidence map resolved for this outcome
                            type and jurisdiction; queryability marked
    Stage 15 — Graph:       Corroboration graph built, sources collapsed,
                            16 rules evaluated
    Stage 16 — Gating:      Evidence EVG verdict issued

    Note: stages 15's graph construction and rule evaluation are run together,
    as delivery_pipeline runs stages 10 and 11 together.

STAGE 13 QUARANTINES, IT DOES NOT DELETE.
    Artifacts without valid provenance are refused — they cannot corroborate
    anything, and they do not enter the graph. But they are retained on the
    dossier in rejected_artifacts, for two reasons:

      1. EVD-SRC-002 must still see them. If quarantine removed them from
         view, a broken chain of custody would present as an absence of
         evidence, which is a different and much weaker finding. The rule
         reads both lists.
      2. The submitting institution is owed a specific answer. "3 artifacts
         rejected" is not actionable; "artifact A7 has no retrieval
         timestamp" is.

    Refusing evidence quietly would be the worst of both worlds: the analysis
    would lose the evidence AND lose the reason.

STAGE 14 AND THE CLASSIFICATION THAT MATTERS.
    Resolution marks which evidence classes are queryable in this
    jurisdiction, which is what sets corroboration capacity and therefore
    whether an adverse conclusion is available at all.

    It does NOT reclassify artifact statuses. That distinction belongs to
    whoever queried the source, and it is consequential: a registry with no
    record is ABSENT, while a source that answered and conflicts is
    CONTRADICTORY. Five silent registries are five findings of the weakest
    kind; one source that answered and disagreed outweighs them. Ingestion
    must record which of the two actually happened.

Purely additive:
    Nothing in this pipeline reads or writes Side 1, 2, 3 or 4 state. A claim
    carries the id of the delivery dossier or recovery record it came from,
    and those ids are never dereferenced here.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from evidence_evg import evidence_gate
from evidence_graph import EvidenceGraphBuilder, derive_queryable_classes
from evidence_rules import EvidenceRuleEngine, _get_evidence_param
from evidence_schema import (
    CorroborationDossier,
    EvidenceArtifact,
    EvidenceClass,
    EvidenceStage,
    ExpectedEvidence,
    OutcomeClaim,
    SourceIndependence,
)
from provenance import ProvenanceError, rejection_reason, validate_for_ingestion


# ═══════════════════════════════════════════════════════════
# SECTION 1: EXPECTED-EVIDENCE MAP RESOLUTION
# ═══════════════════════════════════════════════════════════


def _parse_expectation(raw: Dict, index: int) -> Optional[ExpectedEvidence]:
    """Turn one entry of an expected-evidence map into an ExpectedEvidence.

    Returns None for an entry naming an evidence class that does not exist,
    rather than raising: a typo in a jurisdiction map should degrade that one
    expectation, not take down analysis of every claim in the country.
    """
    raw_class = raw.get("evidence_class")
    try:
        evidence_class = EvidenceClass(raw_class)
    except ValueError:
        return None

    return ExpectedEvidence(
        expectation_id=raw.get("expectation_id") or f"EXP-{index:03d}",
        evidence_class=evidence_class,
        description=raw.get("description", ""),
        required=bool(raw.get("required", True)),
        expected_by_month=raw.get("expected_by_month"),
        queryable_in_jurisdiction=bool(raw.get("queryable_in_jurisdiction", True)),
    )


def resolve_expected_evidence(
    claim: OutcomeClaim,
    profile=None,
    evidence_map: Optional[Dict[str, List[Dict]]] = None,
    queryable_classes: Optional[Set[EvidenceClass]] = None,
) -> List[ExpectedEvidence]:
    """Resolve what should exist if this claim is true.

    The map is keyed on outcome type, because a road and a cash transfer
    leave completely different traces, and expecting one to produce the
    other's evidence would manufacture a false absence.

    Args:
        claim: the claim being corroborated.
        profile: jurisdiction profile; read for expected_evidence_maps and
            queryable_classes when those are not passed directly.
        evidence_map: outcome_type value → list of expectation dicts.
        queryable_classes: classes reachable in this jurisdiction. Any
            expectation outside this set is marked unqueryable, which keeps
            it out of every absence finding.

    Returns:
        List of ExpectedEvidence. Empty when no map covers this outcome type —
        an honest empty rather than a guess, since a fabricated expectation
        would produce a fabricated absence.
    """
    if evidence_map is None:
        evidence_map = _get_evidence_param(profile, "expected_evidence_maps", {}) or {}

    if queryable_classes is None:
        raw_queryable = _get_evidence_param(profile, "queryable_classes", None)
        if raw_queryable:
            queryable_classes = set()
            for name in raw_queryable:
                try:
                    queryable_classes.add(EvidenceClass(name))
                except ValueError:
                    continue

    entries = evidence_map.get(claim.outcome_type.value, [])

    resolved: List[ExpectedEvidence] = []
    for i, raw in enumerate(entries):
        exp = _parse_expectation(raw, i)
        if exp is None:
            continue
        # The jurisdiction's reachable-class list overrides the map's
        # optimism. A map that expects a utility registry in a country that
        # has none must not generate an absence finding.
        if queryable_classes is not None and exp.evidence_class not in queryable_classes:
            exp.queryable_in_jurisdiction = False
        resolved.append(exp)

    return resolved


# ═══════════════════════════════════════════════════════════
# SECTION 2: THE PIPELINE
# ═══════════════════════════════════════════════════════════


class EvidencePipeline:
    """Deterministic corroboration pipeline, stages 13-16.

    Mirrors DeliveryPipeline: ingest() builds the dossier, process() runs the
    remaining stages and records per-stage timing.
    """

    def __init__(self, profile=None):
        if profile is None:
            from jurisdiction_profile import US_FEDERAL
            profile = US_FEDERAL
        self.profile = profile
        self.graph_builder = EvidenceGraphBuilder(profile=profile)
        self.rule_engine = EvidenceRuleEngine(profile=profile)

    # ── Stage 13 ─────────────────────────────────────────

    def ingest(
        self,
        claim: OutcomeClaim,
        artifacts: Optional[List[EvidenceArtifact]] = None,
        source_registry: Optional[List[SourceIndependence]] = None,
        expected_evidence: Optional[List[ExpectedEvidence]] = None,
        strict: bool = False,
    ) -> CorroborationDossier:
        """Stage 13 — build a dossier, validating provenance on every artifact.

        Args:
            claim: the outcome claim being corroborated.
            artifacts: submitted evidence, including documented absences.
            source_registry: parties, with their linkage and contract status.
            expected_evidence: caller-supplied expectations. When given, they
                are kept and Stage 14 does not overwrite them.
            strict: when True, raise on the first artifact that cannot be
                admitted instead of quarantining it. Batch callers want the
                default; a caller submitting one dossier interactively may
                prefer to be stopped.

        Returns:
            CorroborationDossier at INGESTED stage, with admitted artifacts in
            .artifacts and refused ones in .rejected_artifacts.

        Raises:
            ProvenanceError: only when strict=True.
        """
        start = time.perf_counter()

        dossier = CorroborationDossier(
            claim=claim,
            expected_evidence=list(expected_evidence or []),
            source_registry=list(source_registry or []),
        )

        for artifact in (artifacts or []):
            try:
                validate_for_ingestion(artifact)
            except ProvenanceError as e:
                if strict:
                    raise
                dossier.rejected_artifacts.append(artifact)
                dossier.errors.append({
                    "stage": EvidenceStage.INGESTED.value,
                    "artifact_id": getattr(artifact, "artifact_id", None),
                    "error": str(e),
                    "reason": rejection_reason(artifact),
                })
                continue
            dossier.artifacts.append(artifact)

        dossier.advance(
            EvidenceStage.INGESTED, (time.perf_counter() - start) * 1000.0)
        return dossier

    # ── Stages 14-16 ─────────────────────────────────────

    def process(self, dossier: CorroborationDossier) -> CorroborationDossier:
        """Run stages 14 through 16 on an ingested dossier."""
        stages = (
            (EvidenceStage.RESOLVED, self._resolve),
            (EvidenceStage.GRAPHED, self._graph_and_rules),
            (EvidenceStage.GATED, self._gate),
        )

        for stage, fn in stages:
            start = time.perf_counter()
            try:
                dossier = fn(dossier)
            except Exception as e:  # noqa: BLE001 — recorded, not swallowed
                dossier.fail(stage, f"{type(e).__name__}: {e}")
                return dossier
            dossier.advance(stage, (time.perf_counter() - start) * 1000.0)

        dossier.advance(EvidenceStage.COMPLETE)
        return dossier

    def _resolve(self, dossier: CorroborationDossier) -> CorroborationDossier:
        """Stage 14 — resolve expectations and mark reachable classes.

        Caller-supplied expectations are preserved. A caller who states what
        they expect has made a deliberate claim about this project, and
        silently replacing it with the jurisdiction default would discard it.
        """
        if not dossier.expected_evidence:
            dossier.expected_evidence = resolve_expected_evidence(
                dossier.claim, profile=self.profile)

        dossier.classes_queryable = len(derive_queryable_classes(dossier))
        return dossier

    def _graph_and_rules(self, dossier: CorroborationDossier) -> CorroborationDossier:
        """Stage 15 — build the graph, collapse sources, evaluate the 16 rules."""
        dossier = self.graph_builder.build_graph(dossier)
        dossier.rules_result = self.rule_engine.evaluate(dossier)
        return dossier

    def _gate(self, dossier: CorroborationDossier) -> CorroborationDossier:
        """Stage 16 — issue the verdict and write it to the dossier."""
        outcome = evidence_gate(
            rules_result=dossier.rules_result,
            corroboration_capacity=dossier.corroboration_capacity,
            independent_classes=dossier.independent_classes_corroborating,
            classes_queryable=dossier.classes_queryable,
            profile=self.profile,
        )

        dossier.gate_outcome = outcome
        dossier.verdict = outcome.verdict
        dossier.confidence = outcome.confidence
        dossier.contradictions = outcome.contradictions
        dossier.evaluated_at = _utc_now()
        return dossier

    # ── Convenience ──────────────────────────────────────

    def run(
        self,
        claim: OutcomeClaim,
        artifacts: Optional[List[EvidenceArtifact]] = None,
        source_registry: Optional[List[SourceIndependence]] = None,
        expected_evidence: Optional[List[ExpectedEvidence]] = None,
        strict: bool = False,
    ) -> CorroborationDossier:
        """Ingest and process in one call. Stages 13-16."""
        dossier = self.ingest(
            claim=claim,
            artifacts=artifacts,
            source_registry=source_registry,
            expected_evidence=expected_evidence,
            strict=strict,
        )
        return self.process(dossier)


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
