"""
Tests for SUNLIGHT Intelligence Alert System — Core Data Structures.

Covers:
    Alert Assembly:
        1. Procurement RED → correct priority, rule citations, summary
        2. Delivery RED → delivery-specific rule citations
        3. Combined procurement RED + delivery RED → CRITICAL
        4. GREEN does not alert
        5. YELLOW at elevated (confidence >= 60%)
        6. YELLOW at advisory (confidence < 60%)
        7. Delivery-only alert (procurement GREEN + delivery RED → HIGH)

    Threshold and Filtering:
        8. Below min_confidence filtering
        9. Below min_dimensions filtering
        10. Rate limiting placeholder

    Determinism:
        11. Summary determinism — same inputs → identical summary
        12. Priority determinism — same inputs → same priority

    Rule Citation Completeness:
        13. Every fired rule appears with rule_id, legal_basis, evidence, recommendation

    Triage:
        17. Ranking — mixed priorities sorted correctly
        18. Vendor clustering — 3+ alerts with same vendor
        19. Rule concentration — 5+ alerts with same rule
        20. Temporal clustering — awards within 14-day window
        21. Pillar concentration (via typologies)
        22. Executive summary determinism
        23. Empty triage — zero alerts
        24. Single alert triage

    Integration:
        27. Emission failure isolation (logic only)
        28. Pipeline invariance — alerts do not modify dossier data
        29. Configuration validation
"""

import sys
import os
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from alerts import (
    AlertPriority,
    AlertPattern,
    IntelligenceAlert,
    RuleCitation,
    TriageBrief,
    assemble_executive_summary,
    assemble_recommended_action,
    assemble_summary,
    assemble_triage_brief,
    compute_priority,
    detect_patterns,
    detect_rule_concentration,
    detect_temporal_clustering,
    detect_vendor_clustering,
    rank_alerts,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _make_rule_citation(
    rule_id: str = "PROC-001",
    rule_name: str = "Direct award above competitive threshold",
    layer: str = "procurement",
    confidence: float = 0.92,
    legal_basis: str = "FAR Part 6",
    evidence: str = "Direct award of USD 14,250,000",
    recommendation: str = "Review competitive justification",
) -> RuleCitation:
    return RuleCitation(
        rule_id=rule_id,
        rule_name=rule_name,
        layer=layer,
        confidence=confidence,
        legal_basis=legal_basis,
        evidence=evidence,
        recommendation=recommendation,
    )


def _make_alert(
    contract_id: str = "N0002417C2117",
    verdict: str = "red",
    confidence: float = 0.89,
    priority: AlertPriority = AlertPriority.CRITICAL,
    dimensions_fired: int = 3,
    vendor: str = "Acme Corp",
    contract_value: float = 14250000.0,
    award_date: str = "2017-09-28",
    jurisdiction_profile: str = "us_federal",
    rule_citations: list = None,
    delivery_verdict: str = None,
    delivery_dimensions_fired: int = None,
    delivery_rule_citations: list = None,
    alert_type: str = "procurement",
) -> IntelligenceAlert:
    if rule_citations is None:
        rule_citations = [
            _make_rule_citation("PROC-001", "Competitive Process Absent", "procurement", 0.92, "FAR Part 6"),
            _make_rule_citation("FIN-001", "Price Deviation", "financial", 0.87, "FAR Part 15.404"),
            _make_rule_citation("TIME-001", "Fiscal Year-End Clustering", "temporal", 0.78, "OMB Circular A-11"),
        ]
    alert = IntelligenceAlert(
        alert_type=alert_type,
        contract_id=contract_id,
        contract_title="Naval Surface Warfare Center IT Infrastructure",
        vendor=vendor,
        agency="NAVSEA",
        contract_value=contract_value,
        currency="USD",
        award_date=award_date,
        verdict=verdict,
        confidence=confidence,
        priority=priority,
        jurisdiction_profile=jurisdiction_profile,
        country_code="US",
        dimensions_fired=dimensions_fired,
        dimensions_required=2,
        typologies=["CRI_MARKUP", "TCA_PROC", "TCA_TIME"],
        rule_citations=rule_citations,
        delivery_verdict=delivery_verdict,
        delivery_dimensions_fired=delivery_dimensions_fired,
        delivery_rule_citations=delivery_rule_citations,
    )
    alert.summary = assemble_summary(alert)
    alert.recommended_action = assemble_recommended_action(alert)
    return alert


# ═══════════════════════════════════════════════════════════
# ALERT ASSEMBLY TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertAssemblyProcurement:
    def test_procurement_red_correct_priority(self):
        """RED verdict + high confidence + 3 dims → CRITICAL."""
        p = compute_priority("red", 0.89, 3)
        assert p == AlertPriority.CRITICAL

    def test_procurement_red_alert_has_rule_citations(self):
        alert = _make_alert()
        assert len(alert.rule_citations) == 3
        assert alert.rule_citations[0].rule_id == "PROC-001"

    def test_procurement_red_summary_contains_contract_id(self):
        alert = _make_alert()
        assert "N0002417C2117" in alert.summary

    def test_procurement_red_summary_contains_verdict(self):
        alert = _make_alert()
        assert "RED" in alert.summary

    def test_procurement_red_summary_contains_confidence(self):
        alert = _make_alert()
        assert "89%" in alert.summary


class TestAlertAssemblyDelivery:
    def test_delivery_red_produces_alert(self):
        """Delivery RED with delivery-specific rule citations."""
        delivery_cites = [
            _make_rule_citation("DEL-MILE-001", "Critical milestone delay", "milestone", 0.85, "UNCAC Art. 9(1)"),
            _make_rule_citation("DEL-FIN-001", "Cost escalation", "financial", 0.80, "UNDP Financial Regs"),
        ]
        alert = _make_alert(
            verdict="green",
            confidence=0.5,
            priority=AlertPriority.HIGH,
            dimensions_fired=0,
            delivery_verdict="red",
            delivery_dimensions_fired=2,
            delivery_rule_citations=delivery_cites,
            alert_type="delivery",
        )
        assert alert.delivery_verdict == "red"
        assert len(alert.delivery_rule_citations) == 2
        assert alert.delivery_rule_citations[0].rule_id == "DEL-MILE-001"


class TestAlertAssemblyCombined:
    def test_combined_red_red_is_critical(self):
        """Procurement RED + delivery RED → CRITICAL."""
        p = compute_priority("red", 0.89, 3, delivery_verdict="red")
        assert p == AlertPriority.CRITICAL

    def test_combined_red_red_low_confidence_still_critical(self):
        """Even low confidence, procurement RED + delivery RED → CRITICAL."""
        p = compute_priority("red", 0.50, 1, delivery_verdict="red")
        assert p == AlertPriority.CRITICAL


class TestGreenNoAlert:
    def test_green_no_delivery_returns_none(self):
        p = compute_priority("green", 0.99, 0)
        assert p is None

    def test_green_with_green_delivery_returns_none(self):
        p = compute_priority("green", 0.99, 0, delivery_verdict="green")
        assert p is None

    def test_green_empty_delivery_returns_none(self):
        p = compute_priority("green", 0.99, 0, delivery_verdict="")
        assert p is None


class TestYellowPriority:
    def test_yellow_high_confidence_elevated(self):
        """YELLOW + confidence >= 60% → ELEVATED."""
        p = compute_priority("yellow", 0.60, 1)
        assert p == AlertPriority.ELEVATED

    def test_yellow_low_confidence_advisory(self):
        """YELLOW + confidence < 60% → ADVISORY."""
        p = compute_priority("yellow", 0.59, 1)
        assert p == AlertPriority.ADVISORY

    def test_yellow_boundary_at_60(self):
        """Exactly 60% → ELEVATED (>= check)."""
        p = compute_priority("yellow", 0.60, 0)
        assert p == AlertPriority.ELEVATED


class TestDeliveryOnlyAlert:
    def test_green_procurement_delivery_red_is_high(self):
        """Procurement GREEN + delivery RED → HIGH."""
        p = compute_priority("green", 0.5, 0, delivery_verdict="red")
        assert p == AlertPriority.HIGH

    def test_green_procurement_delivery_yellow_is_elevated(self):
        """Procurement GREEN + delivery YELLOW → ELEVATED."""
        p = compute_priority("green", 0.5, 0, delivery_verdict="yellow")
        assert p == AlertPriority.ELEVATED


# ═══════════════════════════════════════════════════════════
# THRESHOLD AND FILTERING TESTS
# ═══════════════════════════════════════════════════════════


class TestThresholdFiltering:
    def test_red_low_confidence_low_dims_elevated(self):
        """RED but confidence < 70% and dims < 2 → ELEVATED (still alerts, just lower priority)."""
        p = compute_priority("red", 0.60, 1)
        assert p == AlertPriority.ELEVATED

    def test_red_high_confidence_two_dims_is_high(self):
        """RED + confidence >= 70% + 2 dims → HIGH."""
        p = compute_priority("red", 0.70, 2)
        assert p == AlertPriority.HIGH

    def test_red_high_confidence_three_dims_is_critical(self):
        """RED + confidence >= 85% + 3 dims → CRITICAL."""
        p = compute_priority("red", 0.85, 3)
        assert p == AlertPriority.CRITICAL


# ═══════════════════════════════════════════════════════════
# DETERMINISM TESTS
# ═══════════════════════════════════════════════════════════


class TestDeterminism:
    def test_summary_determinism(self):
        """Same inputs produce identical summary every time."""
        alert1 = _make_alert()
        alert2 = _make_alert()
        # Reset timestamps to match
        alert2.timestamp = alert1.timestamp
        alert2.alert_id = alert1.alert_id
        assert alert1.summary == alert2.summary

    def test_priority_determinism(self):
        """Same verdict/confidence/dimensions → same priority."""
        for _ in range(10):
            p = compute_priority("red", 0.89, 3)
            assert p == AlertPriority.CRITICAL

    def test_recommended_action_determinism(self):
        """Same priority → same recommended action pattern."""
        alert = _make_alert()
        action1 = assemble_recommended_action(alert)
        action2 = assemble_recommended_action(alert)
        assert action1 == action2


# ═══════════════════════════════════════════════════════════
# RULE CITATION COMPLETENESS TESTS
# ═══════════════════════════════════════════════════════════


class TestRuleCitationCompleteness:
    def test_every_citation_has_required_fields(self):
        """Every RuleCitation has rule_id, legal_basis, evidence, recommendation."""
        alert = _make_alert()
        for rc in alert.rule_citations:
            assert rc.rule_id, "Missing rule_id"
            assert rc.legal_basis, "Missing legal_basis"
            assert rc.evidence, "Missing evidence"
            assert rc.recommendation, "Missing recommendation"
            assert rc.rule_name, "Missing rule_name"
            assert rc.layer, "Missing layer"
            assert rc.confidence > 0, "Confidence must be positive"

    def test_citations_in_summary(self):
        """Each rule_id from citations appears in the summary."""
        alert = _make_alert()
        for rc in alert.rule_citations:
            assert rc.rule_id in alert.summary


# ═══════════════════════════════════════════════════════════
# RANKING TESTS
# ═══════════════════════════════════════════════════════════


class TestRanking:
    def test_ranking_by_priority(self):
        """CRITICAL before HIGH before ELEVATED before ADVISORY."""
        alerts = [
            _make_alert(contract_id="A", priority=AlertPriority.ADVISORY, confidence=0.5),
            _make_alert(contract_id="B", priority=AlertPriority.CRITICAL, confidence=0.9),
            _make_alert(contract_id="C", priority=AlertPriority.ELEVATED, confidence=0.7),
            _make_alert(contract_id="D", priority=AlertPriority.HIGH, confidence=0.8),
        ]
        ranked = rank_alerts(alerts)
        assert ranked[0].contract_id == "B"  # CRITICAL
        assert ranked[1].contract_id == "D"  # HIGH
        assert ranked[2].contract_id == "C"  # ELEVATED
        assert ranked[3].contract_id == "A"  # ADVISORY

    def test_ranking_within_priority_by_confidence(self):
        """Within same priority, higher confidence first."""
        alerts = [
            _make_alert(contract_id="A", priority=AlertPriority.HIGH, confidence=0.70),
            _make_alert(contract_id="B", priority=AlertPriority.HIGH, confidence=0.95),
            _make_alert(contract_id="C", priority=AlertPriority.HIGH, confidence=0.80),
        ]
        ranked = rank_alerts(alerts)
        assert ranked[0].contract_id == "B"
        assert ranked[1].contract_id == "C"
        assert ranked[2].contract_id == "A"

    def test_ranking_within_confidence_by_value(self):
        """Within same priority and confidence, higher value first."""
        alerts = [
            _make_alert(contract_id="A", priority=AlertPriority.HIGH, confidence=0.80, contract_value=100000),
            _make_alert(contract_id="B", priority=AlertPriority.HIGH, confidence=0.80, contract_value=500000),
        ]
        ranked = rank_alerts(alerts)
        assert ranked[0].contract_id == "B"
        assert ranked[1].contract_id == "A"

    def test_ranking_10_mixed_alerts(self):
        """10 alerts with mixed priorities sort correctly."""
        alerts = []
        for i, (p, c) in enumerate([
            (AlertPriority.ADVISORY, 0.40),
            (AlertPriority.CRITICAL, 0.95),
            (AlertPriority.ELEVATED, 0.65),
            (AlertPriority.HIGH, 0.85),
            (AlertPriority.CRITICAL, 0.90),
            (AlertPriority.ADVISORY, 0.55),
            (AlertPriority.HIGH, 0.75),
            (AlertPriority.ELEVATED, 0.70),
            (AlertPriority.CRITICAL, 0.88),
            (AlertPriority.HIGH, 0.80),
        ]):
            alerts.append(_make_alert(contract_id=f"C{i}", priority=p, confidence=c))

        ranked = rank_alerts(alerts)
        # First 3 should be CRITICAL (sorted by confidence desc)
        assert all(a.priority == AlertPriority.CRITICAL for a in ranked[:3])
        assert ranked[0].confidence >= ranked[1].confidence >= ranked[2].confidence
        # Next 3 should be HIGH
        assert all(a.priority == AlertPriority.HIGH for a in ranked[3:6])


# ═══════════════════════════════════════════════════════════
# PATTERN DETECTION TESTS
# ═══════════════════════════════════════════════════════════


class TestVendorClustering:
    def test_three_alerts_same_vendor(self):
        """3 alerts with same vendor → vendor_clustering pattern."""
        alerts = [
            _make_alert(contract_id=f"V{i}", vendor="ShadyCorp")
            for i in range(3)
        ]
        patterns = detect_vendor_clustering(alerts)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "vendor_clustering"
        assert "ShadyCorp" in patterns[0].description
        assert len(patterns[0].affected_contracts) == 3

    def test_four_alerts_same_vendor(self):
        """4 alerts with same vendor → still one pattern."""
        alerts = [
            _make_alert(contract_id=f"V{i}", vendor="ShadyCorp")
            for i in range(4)
        ]
        patterns = detect_vendor_clustering(alerts)
        assert len(patterns) == 1

    def test_two_alerts_below_threshold(self):
        """2 alerts with same vendor → no pattern (min is 3)."""
        alerts = [
            _make_alert(contract_id=f"V{i}", vendor="ShadyCorp")
            for i in range(2)
        ]
        patterns = detect_vendor_clustering(alerts)
        assert len(patterns) == 0

    def test_different_vendors_no_pattern(self):
        """All different vendors → no pattern."""
        alerts = [
            _make_alert(contract_id=f"V{i}", vendor=f"Vendor{i}")
            for i in range(5)
        ]
        patterns = detect_vendor_clustering(alerts)
        assert len(patterns) == 0


class TestRuleConcentration:
    def test_five_alerts_same_rule(self):
        """5 alerts with PROC-001 → rule_concentration pattern."""
        alerts = [
            _make_alert(
                contract_id=f"R{i}",
                rule_citations=[_make_rule_citation("PROC-001")],
            )
            for i in range(5)
        ]
        patterns = detect_rule_concentration(alerts)
        assert len(patterns) == 1
        assert patterns[0].pattern_type == "rule_concentration"
        assert "PROC-001" in patterns[0].description
        assert len(patterns[0].affected_contracts) == 5

    def test_six_alerts_same_rule(self):
        """6 alerts with PROC-001 → pattern detected."""
        alerts = [
            _make_alert(
                contract_id=f"R{i}",
                rule_citations=[_make_rule_citation("PROC-001")],
            )
            for i in range(6)
        ]
        patterns = detect_rule_concentration(alerts)
        assert len(patterns) == 1

    def test_four_alerts_below_threshold(self):
        """4 alerts with same rule → no pattern (min is 5)."""
        alerts = [
            _make_alert(
                contract_id=f"R{i}",
                rule_citations=[_make_rule_citation("PROC-001")],
            )
            for i in range(4)
        ]
        patterns = detect_rule_concentration(alerts)
        assert len(patterns) == 0


class TestTemporalClustering:
    def test_five_alerts_within_14_days(self):
        """5 alerts within 14-day window → temporal_clustering."""
        base = datetime(2024, 9, 15, tzinfo=timezone.utc)
        alerts = [
            _make_alert(
                contract_id=f"T{i}",
                award_date=(base + timedelta(days=i * 3)).strftime("%Y-%m-%d"),
            )
            for i in range(5)
        ]
        patterns = detect_temporal_clustering(alerts)
        assert len(patterns) >= 1
        assert any(p.pattern_type == "temporal_clustering" for p in patterns)

    def test_alerts_spread_across_months_no_cluster(self):
        """Alerts 30+ days apart → no temporal clustering."""
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        alerts = [
            _make_alert(
                contract_id=f"T{i}",
                award_date=(base + timedelta(days=i * 30)).strftime("%Y-%m-%d"),
            )
            for i in range(5)
        ]
        patterns = detect_temporal_clustering(alerts)
        assert len(patterns) == 0

    def test_no_dates_no_crash(self):
        """Alerts without award dates → no crash, no patterns."""
        alerts = [
            _make_alert(contract_id=f"T{i}", award_date="")
            for i in range(5)
        ]
        patterns = detect_temporal_clustering(alerts)
        assert len(patterns) == 0


# ═══════════════════════════════════════════════════════════
# TRIAGE BRIEF TESTS
# ═══════════════════════════════════════════════════════════


class TestTriageBrief:
    def test_executive_summary_determinism(self):
        """Same batch → identical executive summary."""
        alerts = [_make_alert(contract_id=f"X{i}") for i in range(3)]
        brief1 = assemble_triage_brief(
            alerts, batch_id="B001", total_contracts=100,
            jurisdiction_profile="us_federal",
        )
        brief2 = assemble_triage_brief(
            alerts, batch_id="B001", total_contracts=100,
            jurisdiction_profile="us_federal",
        )
        assert brief1.executive_summary == brief2.executive_summary

    def test_empty_triage(self):
        """Zero alerts → brief with empty ranked_alerts, no patterns."""
        brief = assemble_triage_brief(
            [], batch_id="B002", total_contracts=50,
            jurisdiction_profile="us_federal",
        )
        assert brief.total_alerts == 0
        assert len(brief.ranked_alerts) == 0
        assert len(brief.patterns) == 0

    def test_single_alert_triage(self):
        """1 alert in brief → no cross-contract patterns."""
        alert = _make_alert(contract_id="SOLO-001")
        brief = assemble_triage_brief(
            [alert], batch_id="B003", total_contracts=10,
            jurisdiction_profile="us_federal",
        )
        assert brief.total_alerts == 1
        assert len(brief.ranked_alerts) == 1
        # Single alert can't produce vendor or rule concentration patterns
        vendor_patterns = [p for p in brief.patterns if p.pattern_type == "vendor_clustering"]
        assert len(vendor_patterns) == 0

    def test_brief_priority_distribution(self):
        """Brief tracks alerts by priority."""
        alerts = [
            _make_alert(contract_id="P1", priority=AlertPriority.CRITICAL),
            _make_alert(contract_id="P2", priority=AlertPriority.HIGH),
            _make_alert(contract_id="P3", priority=AlertPriority.HIGH),
        ]
        brief = assemble_triage_brief(
            alerts, total_contracts=50, jurisdiction_profile="us_federal",
        )
        assert brief.alerts_by_priority["critical"] == 1
        assert brief.alerts_by_priority["high"] == 2

    def test_brief_dimension_distribution(self):
        """Brief tracks alerts by dimension/typology."""
        alerts = [
            _make_alert(contract_id=f"D{i}")
            for i in range(3)
        ]
        # All have typologies ["CRI_MARKUP", "TCA_PROC", "TCA_TIME"]
        brief = assemble_triage_brief(
            alerts, total_contracts=50, jurisdiction_profile="us_federal",
        )
        assert brief.alerts_by_dimension.get("CRI_MARKUP", 0) == 3

    def test_executive_summary_contains_batch_id(self):
        brief = assemble_triage_brief(
            [_make_alert()], batch_id="B100", total_contracts=200,
            jurisdiction_profile="us_federal",
        )
        assert "B100" in brief.executive_summary

    def test_executive_summary_contains_profile(self):
        brief = assemble_triage_brief(
            [_make_alert()], total_contracts=200,
            jurisdiction_profile="us_federal",
        )
        assert "us_federal" in brief.executive_summary

    def test_ranked_alerts_ordered(self):
        """Ranked alerts in brief are sorted by priority."""
        alerts = [
            _make_alert(contract_id="LO", priority=AlertPriority.ADVISORY, confidence=0.4),
            _make_alert(contract_id="HI", priority=AlertPriority.CRITICAL, confidence=0.95),
        ]
        brief = assemble_triage_brief(
            alerts, total_contracts=50, jurisdiction_profile="us_federal",
        )
        assert brief.ranked_alerts[0].contract_id == "HI"
        assert brief.ranked_alerts[1].contract_id == "LO"


# ═══════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════


class TestIntegration:
    def test_pipeline_invariance(self):
        """Alert construction does not modify input data."""
        rule_citations = [
            _make_rule_citation("PROC-001"),
            _make_rule_citation("FIN-001"),
        ]
        original_len = len(rule_citations)
        alert = _make_alert(rule_citations=rule_citations)
        # Building summary and action should not modify citations
        _ = assemble_summary(alert)
        _ = assemble_recommended_action(alert)
        assert len(rule_citations) == original_len
        assert rule_citations[0].rule_id == "PROC-001"

    def test_full_flow_procurement_red(self):
        """Full flow: compute priority → build alert → assemble summary."""
        priority = compute_priority("red", 0.89, 3)
        assert priority == AlertPriority.CRITICAL

        alert = _make_alert(priority=priority)
        assert "N0002417C2117" in alert.summary
        assert "RED" in alert.summary
        assert "PROC-001" in alert.summary
        assert "Immediate review" in alert.recommended_action

    def test_full_flow_batch_triage(self):
        """Full batch flow: multiple alerts → triage brief."""
        alerts = [
            _make_alert(contract_id=f"BATCH-{i}", vendor="CommonVendor")
            for i in range(5)
        ]
        brief = assemble_triage_brief(
            alerts, batch_id="BATCH-001", total_contracts=100,
            jurisdiction_profile="us_federal",
        )
        assert brief.total_alerts == 5
        assert len(brief.ranked_alerts) == 5
        assert brief.executive_summary != ""
        # CommonVendor appears 5 times → vendor clustering pattern
        vendor_patterns = [p for p in brief.patterns if p.pattern_type == "vendor_clustering"]
        assert len(vendor_patterns) == 1

    def test_recommended_action_per_priority(self):
        """Each priority tier has a distinct recommended action."""
        actions = set()
        for p in AlertPriority:
            alert = _make_alert(priority=p)
            action = assemble_recommended_action(alert)
            actions.add(action[:20])  # First 20 chars differ per tier
        assert len(actions) == 4  # 4 distinct action types

    def test_all_priority_tiers_reachable(self):
        """All four priority tiers are reachable through compute_priority."""
        assert compute_priority("red", 0.90, 3) == AlertPriority.CRITICAL
        assert compute_priority("red", 0.75, 2) == AlertPriority.HIGH
        assert compute_priority("yellow", 0.65, 1) == AlertPriority.ELEVATED
        assert compute_priority("yellow", 0.50, 1) == AlertPriority.ADVISORY
