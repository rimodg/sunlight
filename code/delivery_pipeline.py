"""
SUNLIGHT Side 2 — Delivery Pipeline
=====================================

Orchestrates delivery integrity verification through stages 9-12.
Same delivery data + same pipeline = same result. Forever.

Architecture:
    Mirrors SunlightPipeline from sunlight_core.py:
    - Sequential stage execution with error handling
    - Each stage is bounded: reads specific inputs, writes specific outputs
    - Timing recorded per stage
    - Failure at any stage records error and marks dossier FAILED

Pipeline Stages:
    Stage  9 — Ingestion:       Raw delivery data → DeliveryDossier
    Stage 10 — Graph Build:     DeliveryDossier → delivery topology graph
    Stage 11 — Rule Evaluation: Graph + dossier → 12 delivery rules evaluated
    Stage 12 — Evidence Gating: Rule results → delivery EVG verdict

Note: Stages 10 and 11 are combined in DeliveryGraphBuilder.build_graph()
which constructs the graph AND evaluates rules in a single pass (matching
the Side 1 pattern where graph construction and rule evaluation are coupled).
The pipeline separates the EVG gate as a distinct stage.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional

from delivery_schema import (
    DeliveryDossier,
    DeliveryStage,
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
)
from delivery_graph import DeliveryGraphBuilder
from delivery_evg import delivery_gate, DEFAULT_MIN_RULES_PER_DIMENSION
from jurisdiction_profile import JurisdictionProfile


class DeliveryPipeline:
    """
    Orchestrates delivery integrity verification.

    A delivery record enters as raw input data and exits as a complete
    DeliveryDossier with graph topology, rule evaluation, and EVG verdict.

    Pipeline stages:
        INGEST → GRAPH+RULES → GATE → COMPLETE

    The pipeline is the ONLY way to produce a complete delivery dossier.
    """

    def __init__(
        self,
        profile: Optional[JurisdictionProfile] = None,
        min_rules_per_dimension: int = DEFAULT_MIN_RULES_PER_DIMENSION,
        on_complete: Optional[Callable[[DeliveryDossier], None]] = None,
        on_failure: Optional[Callable[[DeliveryDossier], None]] = None,
    ):
        from jurisdiction_profile import US_FEDERAL
        self.profile = profile or US_FEDERAL
        self.min_rules_per_dimension = min_rules_per_dimension
        self.graph_builder = DeliveryGraphBuilder(profile=self.profile)
        self.on_complete = on_complete
        self.on_failure = on_failure

        # Pipeline statistics
        self.stats: Dict[str, int] = {
            "processed": 0,
            "completed": 0,
            "failed": 0,
            "green": 0,
            "yellow": 0,
            "red": 0,
        }

    def ingest(
        self,
        contract_id: str,
        milestones: Optional[List[Milestone]] = None,
        resources: Optional[List[ResourceRecord]] = None,
        outcomes: Optional[List[OutcomeRecord]] = None,
        financials: Optional[List[FinancialRecord]] = None,
        country_code: str = "",
        country_name: str = "",
        project_name: str = "",
        procurement_verdict: str = "",
    ) -> DeliveryDossier:
        """
        Create a DeliveryDossier from raw delivery data. Entry point.

        Args:
            contract_id: Links to the ContractDossier from Side 1.
            milestones: Schedule milestone records.
            resources: Staffing/resource records.
            outcomes: Deliverable/output records.
            financials: Budget vs. actual financial records.
            country_code: ISO 3166-1 alpha-2 code.
            country_name: Full country name.
            project_name: Project identifier.
            procurement_verdict: Side 1 EVG verdict (GREEN/YELLOW/RED).

        Returns:
            DeliveryDossier at INGESTED stage.
        """
        dossier = DeliveryDossier(
            contract_id=contract_id,
            milestones=milestones or [],
            resources=resources or [],
            outcomes=outcomes or [],
            financials=financials or [],
            country_code=country_code,
            country_name=country_name,
            project_name=project_name,
            procurement_verdict=procurement_verdict,
        )
        return dossier

    def process(self, dossier: DeliveryDossier) -> DeliveryDossier:
        """
        Run the full delivery pipeline on a dossier.

        Executes stages 9-12 sequentially with error handling.
        A failure at any stage records the error and marks the
        dossier as FAILED, but does not crash the pipeline.

        Returns:
            The same dossier with all analysis stages complete
            (or marked FAILED with error detail).
        """
        self.stats["processed"] += 1

        stages = [
            (DeliveryStage.GRAPHED, self._build_graph),
            (DeliveryStage.RULES_EVALUATED, self._mark_rules_evaluated),
            (DeliveryStage.GATED, self._gate),
        ]

        for stage, handler in stages:
            try:
                t0 = time.monotonic()
                dossier = handler(dossier)
                elapsed = (time.monotonic() - t0) * 1000
                dossier.advance(stage, elapsed)
            except Exception as e:
                dossier.fail(stage, str(e))
                self.stats["failed"] += 1
                if self.on_failure:
                    self.on_failure(dossier)
                return dossier

        dossier.advance(DeliveryStage.COMPLETE)
        self.stats["completed"] += 1

        # Track verdict distribution
        if dossier.gate_outcome:
            verdict_key = dossier.gate_outcome.verdict.value
            self.stats[verdict_key] = self.stats.get(verdict_key, 0) + 1

        if self.on_complete:
            self.on_complete(dossier)

        return dossier

    def _build_graph(self, dossier: DeliveryDossier) -> DeliveryDossier:
        """
        Stage 10+11: Build delivery graph and evaluate rules.

        DeliveryGraphBuilder.build_graph() does both:
        - Constructs the delivery topology graph
        - Evaluates all 12 delivery rules
        - Writes graph and rules_result to dossier
        """
        return self.graph_builder.build_graph(dossier)

    def _mark_rules_evaluated(self, dossier: DeliveryDossier) -> DeliveryDossier:
        """
        Stage 11 marker: rules were already evaluated in _build_graph.

        This stage exists to maintain the 4-stage progression
        (INGESTED → GRAPHED → RULES_EVALUATED → GATED → COMPLETE)
        while acknowledging that graph build and rule evaluation
        are coupled in DeliveryGraphBuilder.
        """
        # Rules result already written by _build_graph
        return dossier

    def _gate(self, dossier: DeliveryDossier) -> DeliveryDossier:
        """
        Stage 12: Evaluate the delivery EVG gate.

        Consumes the rules_result from stage 11 and produces
        the delivery EVG verdict.
        """
        outcome = delivery_gate(
            dossier.rules_result,
            min_rules_per_dimension=self.min_rules_per_dimension,
        )
        dossier.gate_outcome = outcome
        return dossier
