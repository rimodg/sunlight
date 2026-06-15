"""
SUNLIGHT Intelligence Alert System — Pipeline Integration
============================================================

Hooks into the pipeline AFTER EVG gating. Assembles IntelligenceAlert
objects from pipeline output and emits through configured emitters.

Critical design constraint:
    - Does NOT modify pipeline output. Purely additive side-effect.
    - If the alert system fails or is disabled, the pipeline produces
      identical results. Alerts are never a dependency.
    - Every emitter call is wrapped in try/except. Alert emission
      failure NEVER propagates to the pipeline.

Usage:
    integration = AlertIntegration(config)

    # After Stage 8 (procurement EVG):
    integration.on_procurement_verdict(dossier, evg_result, profile)

    # After Stage 12 (delivery EVG):
    integration.on_delivery_verdict(delivery_dossier, delivery_evg, profile)

    # After batch processing:
    integration.on_batch_complete(alerts, batch_id, total, profile)

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from alerts import (
    AlertPriority,
    AlertPattern,
    IntelligenceAlert,
    RuleCitation,
    TriageBrief,
    assemble_recommended_action,
    assemble_summary,
    assemble_triage_brief,
    compute_priority,
)
from alert_emitter import (
    AlertConfiguration,
    EmissionResult,
    RateLimiter,
)


logger = logging.getLogger("sunlight.alerts")


# ═══════════════════════════════════════════════════════════
# SECTION 1: ALERT ASSEMBLER
# ═══════════════════════════════════════════════════════════


class AlertAssembler:
    """
    Builds IntelligenceAlert objects from pipeline output.

    Extracts rule citations, computes priority, assembles
    deterministic summary. All fields trace to pipeline data.
    """

    def assemble_procurement_alert(
        self,
        contract_id: str,
        verdict: str,
        confidence: float,
        dimensions_fired: int,
        rule_fires: List[Dict[str, Any]],
        profile_name: str,
        country_code: str = "",
        contract_title: str = "",
        vendor: str = "",
        agency: str = "",
        contract_value: float = 0.0,
        currency: str = "USD",
        award_date: str = "",
        typologies: Optional[List[str]] = None,
        case_packet_url: str = "",
    ) -> Optional[IntelligenceAlert]:
        """
        Assemble a procurement alert from pipeline output.

        Args:
            contract_id: Contract identifier.
            verdict: EVG verdict string ("green", "yellow", "red").
            confidence: Structural confidence (0.0-1.0).
            dimensions_fired: Number of EVG dimensions that fired.
            rule_fires: List of dicts from structural contradictions,
                        each with rule_id, description, evidence, etc.
            profile_name: Jurisdiction profile name.
            country_code: ISO 3166-1 alpha-2 code.
            contract_title: Human-readable title.
            vendor: Vendor/supplier name.
            agency: Buying agency name.
            contract_value: Contract value.
            currency: ISO 4217 currency code.
            award_date: Award date string.
            typologies: List of typology identifiers.
            case_packet_url: URL to full case packet.

        Returns:
            IntelligenceAlert or None if GREEN verdict.
        """
        priority = compute_priority(verdict, confidence, dimensions_fired)
        if priority is None:
            return None

        citations = self._extract_procurement_citations(rule_fires)

        alert = IntelligenceAlert(
            alert_type="procurement",
            contract_id=contract_id,
            contract_title=contract_title,
            vendor=vendor,
            agency=agency,
            contract_value=contract_value,
            currency=currency,
            award_date=award_date,
            verdict=verdict,
            confidence=confidence,
            priority=priority,
            jurisdiction_profile=profile_name,
            country_code=country_code,
            dimensions_fired=dimensions_fired,
            typologies=typologies or [],
            rule_citations=citations,
            case_packet_url=case_packet_url,
        )

        alert.summary = assemble_summary(alert)
        alert.recommended_action = assemble_recommended_action(alert)

        return alert

    def assemble_delivery_alert(
        self,
        contract_id: str,
        delivery_verdict: str,
        delivery_dimensions_fired: int,
        delivery_rule_fires: List[Dict[str, Any]],
        profile_name: str,
        country_code: str = "",
        procurement_verdict: str = "green",
        procurement_confidence: float = 0.0,
        procurement_dimensions_fired: int = 0,
        procurement_rule_fires: Optional[List[Dict[str, Any]]] = None,
        contract_title: str = "",
        vendor: str = "",
        agency: str = "",
        contract_value: float = 0.0,
        currency: str = "USD",
        award_date: str = "",
        case_packet_url: str = "",
    ) -> Optional[IntelligenceAlert]:
        """
        Assemble a delivery alert from delivery pipeline output.

        If procurement data is also provided, produces a combined alert.
        """
        priority = compute_priority(
            procurement_verdict,
            procurement_confidence,
            procurement_dimensions_fired,
            delivery_verdict=delivery_verdict,
        )
        if priority is None:
            return None

        # Determine alert type
        pv = procurement_verdict.lower() if procurement_verdict else "green"
        dv = delivery_verdict.lower() if delivery_verdict else "green"
        if pv != "green" and dv != "green":
            alert_type = "combined"
        elif dv != "green":
            alert_type = "delivery"
        else:
            alert_type = "procurement"

        procurement_citations = self._extract_procurement_citations(
            procurement_rule_fires or []
        )
        delivery_citations = self._extract_delivery_citations(
            delivery_rule_fires
        )

        alert = IntelligenceAlert(
            alert_type=alert_type,
            contract_id=contract_id,
            contract_title=contract_title,
            vendor=vendor,
            agency=agency,
            contract_value=contract_value,
            currency=currency,
            award_date=award_date,
            verdict=procurement_verdict,
            confidence=procurement_confidence,
            priority=priority,
            jurisdiction_profile=profile_name,
            country_code=country_code,
            dimensions_fired=procurement_dimensions_fired,
            rule_citations=procurement_citations,
            delivery_verdict=delivery_verdict,
            delivery_dimensions_fired=delivery_dimensions_fired,
            delivery_rule_citations=delivery_citations,
            case_packet_url=case_packet_url,
        )

        alert.summary = assemble_summary(alert)
        alert.recommended_action = assemble_recommended_action(alert)

        return alert

    def _extract_procurement_citations(
        self, rule_fires: List[Dict[str, Any]]
    ) -> List[RuleCitation]:
        """Extract RuleCitations from procurement structural contradictions."""
        citations = []
        for rf in rule_fires:
            citations.append(RuleCitation(
                rule_id=rf.get("rule_id", rf.get("rule", "")),
                rule_name=rf.get("description", rf.get("name", "")),
                layer=rf.get("layer", rf.get("severity", "")),
                confidence=rf.get("confidence", 0.0),
                legal_basis="; ".join(rf.get("legal_citations", [])) if isinstance(rf.get("legal_citations"), list) else rf.get("legal_basis", ""),
                evidence=rf.get("evidence", ""),
                recommendation=rf.get("recommendation", rf.get("description", "")),
            ))
        return citations

    def _extract_delivery_citations(
        self, rule_fires: List[Dict[str, Any]]
    ) -> List[RuleCitation]:
        """Extract RuleCitations from delivery rule results."""
        citations = []
        for rf in rule_fires:
            citations.append(RuleCitation(
                rule_id=rf.get("rule_id", ""),
                rule_name=rf.get("name", rf.get("description", "")),
                layer=rf.get("layer", ""),
                confidence=rf.get("confidence", 0.0),
                legal_basis=rf.get("legal_basis", rf.get("evidence_template", "")),
                evidence=rf.get("evidence", ""),
                recommendation=rf.get("recommendation", rf.get("description", "")),
            ))
        return citations

    def assemble_recovery_alert(
        self,
        recovery_id: str,
        source_contract_id: str,
        recovery_amount: float,
        currency: str,
        country_office: str,
        country_code: str,
        original_pillar: str,
        source_verdict: str = "red",
        source_confidence: float = 0.0,
        allocation_pillar: str = "",
        allocation_amount: float = 0.0,
        target_contract_id: str = "",
    ) -> IntelligenceAlert:
        """
        Assemble a recovery event alert.

        Recovery alerts are always ADVISORY priority — they are informational,
        tracking fund recovery and redeployment, not flagging new risks.

        Args:
            recovery_id: Recovery record identifier.
            source_contract_id: Original flagged contract.
            recovery_amount: Total recovered amount.
            currency: ISO 4217 currency code.
            country_office: Country office name.
            country_code: ISO 3166-1 alpha-2 code.
            original_pillar: Development pillar of the original contract.
            source_verdict: Original procurement verdict.
            source_confidence: Original structural confidence.
            allocation_pillar: Pillar receiving redirected funds.
            allocation_amount: Amount redirected to this pillar.
            target_contract_id: New contract receiving funds.

        Returns:
            IntelligenceAlert of type "recovery".
        """
        summary = (
            f"Recovery event: {recovery_amount:,.0f} {currency} recovered "
            f"from {source_contract_id} ({source_verdict.upper()}) in "
            f"{country_office}."
        )
        if allocation_pillar and allocation_amount > 0:
            summary += (
                f" {allocation_amount:,.0f} {currency} redirected to "
                f"{allocation_pillar}."
            )
        if target_contract_id:
            summary += f" Target contract: {target_contract_id}."

        alert = IntelligenceAlert(
            alert_type="recovery",
            contract_id=source_contract_id,
            verdict=source_verdict,
            confidence=source_confidence,
            priority=AlertPriority.ADVISORY,
            country_code=country_code,
            contract_value=recovery_amount,
            currency=currency,
            summary=summary,
            recommended_action=(
                f"Track redeployment of recovered funds from {source_contract_id}. "
                f"New contract enters Side 1 and Side 2 verification automatically."
            ),
        )
        return alert


# ═══════════════════════════════════════════════════════════
# SECTION 2: ALERT INTEGRATION
# ═══════════════════════════════════════════════════════════


class AlertIntegration:
    """
    Hooks into the pipeline after EVG gating.

    Does NOT modify pipeline output. Purely additive side-effect.
    If the alert system fails or is disabled, the pipeline produces
    identical results. Alerts are never a dependency.
    """

    def __init__(self, config: AlertConfiguration):
        self.config = config
        self.assembler = AlertAssembler()
        self._rate_limiter = RateLimiter(
            config.max_alerts_per_hour, config.cooldown_seconds
        )
        self._emitted_alerts: List[IntelligenceAlert] = []

    @property
    def emitted_alerts(self) -> List[IntelligenceAlert]:
        """Alerts emitted since last reset (for testing/inspection)."""
        return list(self._emitted_alerts)

    def on_procurement_verdict(
        self,
        contract_id: str,
        verdict: str,
        confidence: float,
        dimensions_fired: int,
        rule_fires: List[Dict[str, Any]],
        profile_name: str,
        **kwargs,
    ) -> Optional[List[EmissionResult]]:
        """
        Called after Stage 8. Assembles and emits procurement alert
        if threshold met.

        Returns None if disabled, below threshold, or rate-limited.
        Returns list of EmissionResult if emission attempted.
        """
        if not self.config.enabled:
            return None

        if not self.config.meets_threshold(verdict, confidence, dimensions_fired):
            return None

        if not self._rate_limiter.allow(contract_id):
            return None

        alert = self.assembler.assemble_procurement_alert(
            contract_id=contract_id,
            verdict=verdict,
            confidence=confidence,
            dimensions_fired=dimensions_fired,
            rule_fires=rule_fires,
            profile_name=profile_name,
            **kwargs,
        )

        if alert is None:
            return None

        self._emitted_alerts.append(alert)
        self._rate_limiter.record(contract_id)
        return self._emit(alert)

    def on_delivery_verdict(
        self,
        contract_id: str,
        delivery_verdict: str,
        delivery_dimensions_fired: int,
        delivery_rule_fires: List[Dict[str, Any]],
        profile_name: str,
        procurement_verdict: str = "green",
        procurement_confidence: float = 0.0,
        procurement_dimensions_fired: int = 0,
        procurement_rule_fires: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Optional[List[EmissionResult]]:
        """
        Called after Stage 12. Assembles and emits delivery alert
        if threshold met.
        """
        if not self.config.enabled:
            return None

        if not self.config.delivery_alerts_enabled:
            return None

        # For delivery-only alerts, check delivery verdict against threshold
        dv = delivery_verdict.lower() if delivery_verdict else "green"
        if dv == "green" and procurement_verdict.lower() == "green":
            return None

        if not self._rate_limiter.allow(contract_id):
            return None

        alert = self.assembler.assemble_delivery_alert(
            contract_id=contract_id,
            delivery_verdict=delivery_verdict,
            delivery_dimensions_fired=delivery_dimensions_fired,
            delivery_rule_fires=delivery_rule_fires,
            profile_name=profile_name,
            procurement_verdict=procurement_verdict,
            procurement_confidence=procurement_confidence,
            procurement_dimensions_fired=procurement_dimensions_fired,
            procurement_rule_fires=procurement_rule_fires,
            **kwargs,
        )

        if alert is None:
            return None

        self._emitted_alerts.append(alert)
        self._rate_limiter.record(contract_id)
        return self._emit(alert)

    def on_batch_complete(
        self,
        alerts: List[IntelligenceAlert],
        batch_id: str,
        total_contracts: int,
        profile_name: str,
        country_office: Optional[str] = None,
    ) -> Optional[Union[List[EmissionResult], List[List[EmissionResult]]]]:
        """
        Called after batch processing completes.

        In "brief" mode: assembles TriageBrief, emits single webhook.
        In "individual" mode: emits each alert separately.
        """
        if not self.config.enabled:
            return None

        if not alerts:
            return None

        if self.config.batch_mode == "brief":
            brief = assemble_triage_brief(
                alerts=alerts,
                batch_id=batch_id,
                total_contracts=total_contracts,
                jurisdiction_profile=profile_name,
                country_office=country_office,
            )
            return self._emit(brief)
        else:
            # Individual mode: emit each alert
            results = []
            for alert in alerts:
                result = self._emit(alert)
                results.append(result)
            return results

    def on_recovery_event(
        self,
        recovery_id: str,
        source_contract_id: str,
        recovery_amount: float,
        currency: str,
        country_office: str,
        country_code: str,
        original_pillar: str,
        source_verdict: str = "red",
        source_confidence: float = 0.0,
        allocation_pillar: str = "",
        allocation_amount: float = 0.0,
        target_contract_id: str = "",
    ) -> Optional[List[EmissionResult]]:
        """
        Called when recovered funds are allocated or redirected.

        Recovery alerts are informational — they track fund recovery and
        redeployment, not new risk flags. Always emitted as ADVISORY.

        Returns None if disabled. Returns list of EmissionResult if emitted.
        """
        if not self.config.enabled:
            return None

        alert = self.assembler.assemble_recovery_alert(
            recovery_id=recovery_id,
            source_contract_id=source_contract_id,
            recovery_amount=recovery_amount,
            currency=currency,
            country_office=country_office,
            country_code=country_code,
            original_pillar=original_pillar,
            source_verdict=source_verdict,
            source_confidence=source_confidence,
            allocation_pillar=allocation_pillar,
            allocation_amount=allocation_amount,
            target_contract_id=target_contract_id,
        )

        self._emitted_alerts.append(alert)
        return self._emit(alert)

    def _emit(
        self, payload: Union[IntelligenceAlert, TriageBrief]
    ) -> List[EmissionResult]:
        """
        Fire through all configured emitters.

        Every emitter call is wrapped in try/except. Alert emission
        failure NEVER crashes the pipeline.
        """
        results = []
        for emitter in self.config.emitters:
            try:
                result = emitter.emit(payload)
                results.append(result)
            except Exception as e:
                logger.warning(
                    "Alert emission failed for %s: %s",
                    type(emitter).__name__, str(e),
                )
                results.append(EmissionResult(
                    success=False,
                    emitter_type=type(emitter).__name__,
                    payload_id="error",
                    error=str(e),
                ))
        return results

    def reset(self):
        """Reset emitted alerts and rate limiter. For testing."""
        self._emitted_alerts.clear()
        self._rate_limiter.reset()
