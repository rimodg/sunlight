"""
SUNLIGHT Side 2 — Delivery Analyzer
=====================================

High-level interface for delivery integrity verification.
Wraps DeliveryPipeline with convenience methods for single
and batch analysis.

This is the public API entry point for Side 2, analogous to
how the API layer uses SunlightPipeline for Side 1.

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from delivery_schema import (
    DeliveryDossier,
    DeliveryStage,
    DeliveryVerdict,
    Milestone,
    ResourceRecord,
    OutcomeRecord,
    FinancialRecord,
)
from delivery_pipeline import DeliveryPipeline
from delivery_evg import DEFAULT_MIN_RULES_PER_DIMENSION
from jurisdiction_profile import JurisdictionProfile


class DeliveryAnalyzer:
    """
    Public interface for delivery integrity verification.

    Usage:
        analyzer = DeliveryAnalyzer()
        result = analyzer.analyze(
            contract_id="N0002417C2117",
            milestones=[...],
            resources=[...],
            outcomes=[...],
            financials=[...],
        )
        print(result["verdict"])  # "green", "yellow", or "red"
    """

    def __init__(
        self,
        profile: Optional[JurisdictionProfile] = None,
        min_rules_per_dimension: int = DEFAULT_MIN_RULES_PER_DIMENSION,
    ):
        self.pipeline = DeliveryPipeline(
            profile=profile,
            min_rules_per_dimension=min_rules_per_dimension,
        )

    def analyze(
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
    ) -> Dict[str, Any]:
        """
        Analyze delivery integrity for a single contract.

        Returns:
            Dict with verdict, dimensions, rules fired, and full dossier.
        """
        dossier = self.pipeline.ingest(
            contract_id=contract_id,
            milestones=milestones,
            resources=resources,
            outcomes=outcomes,
            financials=financials,
            country_code=country_code,
            country_name=country_name,
            project_name=project_name,
            procurement_verdict=procurement_verdict,
        )
        dossier = self.pipeline.process(dossier)
        return self._format_result(dossier)

    def analyze_dossier(self, dossier: DeliveryDossier) -> Dict[str, Any]:
        """
        Analyze a pre-constructed DeliveryDossier.

        Args:
            dossier: DeliveryDossier with input records populated.

        Returns:
            Dict with verdict, dimensions, rules fired, and full dossier.
        """
        dossier = self.pipeline.process(dossier)
        return self._format_result(dossier)

    def batch_analyze(
        self,
        deliveries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple deliveries.

        Args:
            deliveries: List of dicts, each with keys matching
                        analyze() parameters.

        Returns:
            List of result dicts, one per delivery.
        """
        results = []
        for delivery in deliveries:
            result = self.analyze(**delivery)
            results.append(result)
        return results

    @property
    def stats(self) -> Dict[str, int]:
        """Pipeline statistics."""
        return self.pipeline.stats

    def _format_result(self, dossier: DeliveryDossier) -> Dict[str, Any]:
        """Format a processed dossier into a result dict."""
        result: Dict[str, Any] = {
            "delivery_id": dossier.delivery_id,
            "contract_id": dossier.contract_id,
            "stage": dossier.stage.value,
            "procurement_verdict": dossier.procurement_verdict,
        }

        if dossier.stage == DeliveryStage.FAILED:
            result["verdict"] = None
            result["errors"] = dossier.errors
            return result

        # Gate outcome
        if dossier.gate_outcome:
            result["verdict"] = dossier.gate_outcome.verdict.value
            result["dimensions_fired"] = dossier.gate_outcome.dimensions_fired
            result["dimensions"] = [
                {
                    "dimension": d.dimension.value,
                    "fired": d.fired,
                    "observed_value": d.observed_value,
                    "threshold": d.threshold,
                    "detail": d.detail,
                }
                for d in dossier.gate_outcome.dimension_results
            ]
            result["methodology_note"] = dossier.gate_outcome.methodology_note
        else:
            result["verdict"] = None

        # Rules result
        if dossier.rules_result:
            result["rules_evaluated"] = dossier.rules_result.rules_evaluated
            result["rules_fired"] = dossier.rules_result.rules_fired
            result["layer_summary"] = dossier.rules_result.layer_summary
            result["fired_rules"] = [
                {
                    "rule_id": r.rule_id,
                    "layer": r.layer,
                    "evidence": r.evidence,
                    "legal_basis": r.legal_basis,
                    "confidence": r.confidence,
                }
                for r in dossier.rules_result.rule_results
                if r.fired
            ]

        # Graph summary
        if dossier.graph:
            result["graph_summary"] = {
                "node_count": dossier.graph.node_count,
                "edge_count": dossier.graph.edge_count,
            }

        # Computed properties
        result["delivery_metrics"] = {
            "total_milestones": dossier.total_milestones,
            "delayed_milestones": dossier.delayed_milestones,
            "total_budget": dossier.total_budget,
            "total_actual_spend": dossier.total_actual_spend,
            "budget_variance_pct": round(dossier.budget_variance_pct, 2),
            "staffing_gap_ratio": round(dossier.staffing_gap_ratio, 4),
            "outcome_delivery_ratio": round(dossier.outcome_delivery_ratio, 4),
        }

        # Timing
        result["processing_ms"] = dossier.processing_ms
        result["methodology_version"] = dossier.methodology_version

        return result
