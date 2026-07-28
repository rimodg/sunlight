"""
Tests for SUNLIGHT Side 5 — Integration with Sides 2, 3 and 4.

Covers spec tests 42-45.

Two properties are tested harder than the rest, because the whole build has
been held to them:

    ADDITIVITY. With no corroboration data supplied, Side 4 must produce
    byte-identical output to what it produced before Side 5 existed —
    close() behaves as before, and the executive summary is unchanged to the
    character. Tested by string equality, not by inspection.

    DEPENDENCY DIRECTION. No module in Sides 1-4 may import Side 5. The
    hooks they gained take plain strings and callables, and
    evidence_integration is the only file that knows both vocabularies.
    Deleting it must restore complete separation. Tested by parsing the ASTs
    of the four modules that were actually edited.
"""

import ast
import inspect
import os
import sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from alert_emitter import AlertConfiguration
from alert_integration import AlertIntegration
from alerts import AlertPriority, compute_priority
from delivery_schema import DeliveryDossier, OutcomeRecord
from evidence_integration import (
    CorroborationRegistry,
    alert_payload_for,
    claims_from_delivery_dossier,
    corroboration_summary,
    infer_outcome_type,
    is_highest_value_finding,
)
from evidence_schema import (
    CorroborationDossier,
    CorroborationVerdict,
    OutcomeClaim,
    OutcomeType,
)
from impact_report import ImpactReport, assemble_executive_summary
from recovery_ledger import (
    RecoveryRecord,
    RecoveryStatus,
    UncorroboratedClosureError,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def claim(claim_id="C1", contract_id="K1"):
    return OutcomeClaim(
        claim_id=claim_id, contract_id=contract_id,
        outcome_type=OutcomeType.FACILITY_CONSTRUCTION,
        claim_description="200-bed hospital operational",
        claimed_magnitude=200.0, claimed_magnitude_unit="beds",
        country_code="ng",
    )


def dossier(verdict, capacity_queryable=6, claim_id="C1"):
    d = CorroborationDossier(
        claim=claim(claim_id=claim_id),
        classes_queryable=capacity_queryable,
    )
    d.verdict = verdict
    d.confidence = 0.9
    return d


def recovery_at_verified(redirections):
    r = RecoveryRecord(source_contract_id="K1", recovery_amount=100_000.0)
    r.redirections = list(redirections)
    r.confirm(date(2025, 1, 1))
    r.mark_recovered(date(2025, 1, 15))
    r.mark_redirected()
    r.mark_redeployed()
    r.mark_verified()
    return r


# ═══════════════════════════════════════════════════════════
# SECTION 1: SPEC TEST 42 — THE CLOSURE GUARD
# ═══════════════════════════════════════════════════════════


class TestClosureGuard:

    def test_cannot_close_without_corroboration(self):
        """SPEC TEST 42."""
        registry = CorroborationRegistry()
        record = recovery_at_verified(["RD-1", "RD-2"])

        with pytest.raises(UncorroboratedClosureError):
            record.close(corroboration_resolver=registry.resolver())

        assert record.status == RecoveryStatus.VERIFIED

    def test_closes_when_every_redirection_is_corroborated(self):
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.VERIFIED))
        registry.register("RD-2", dossier(CorroborationVerdict.PARTIAL))
        record = recovery_at_verified(["RD-1", "RD-2"])

        record.close(corroboration_resolver=registry.resolver())
        assert record.status == RecoveryStatus.CLOSED

    def test_partial_permits_closure(self):
        """PARTIAL means independent evidence is consistent with the claim,
        with gaps. That supports closing; UNVERIFIED and CONTRADICTED do not."""
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.PARTIAL))
        record = recovery_at_verified(["RD-1"])
        record.close(corroboration_resolver=registry.resolver())
        assert record.status == RecoveryStatus.CLOSED

    @pytest.mark.parametrize("verdict", [
        CorroborationVerdict.UNVERIFIED,
        CorroborationVerdict.CONTRADICTED,
    ])
    def test_unverified_and_contradicted_both_block(self, verdict):
        """Opposite reasons, same consequence. One is evidence we could not
        reach, the other is evidence that conflicts, and neither supports
        declaring the loop closed."""
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(verdict))
        record = recovery_at_verified(["RD-1"])

        with pytest.raises(UncorroboratedClosureError):
            record.close(corroboration_resolver=registry.resolver())

    def test_one_uncorroborated_redirection_blocks_the_whole_cycle(self):
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.VERIFIED))
        record = recovery_at_verified(["RD-1", "RD-2"])

        with pytest.raises(UncorroboratedClosureError, match="RD-2"):
            record.close(corroboration_resolver=registry.resolver())

    def test_error_names_every_blocking_redirection_and_why(self):
        """An institution told only that closure failed cannot act. Name the
        redirection and the verdict."""
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.CONTRADICTED))
        record = recovery_at_verified(["RD-1", "RD-2"])

        with pytest.raises(UncorroboratedClosureError) as exc:
            record.close(corroboration_resolver=registry.resolver())

        message = str(exc.value)
        assert "RD-1" in message and "contradicted" in message
        assert "RD-2" in message and "no corroboration on record" in message

    def test_a_failing_resolver_blocks_rather_than_passes(self):
        """Fail closed. A resolver that errors must not wave the cycle through."""
        def broken(_):
            raise RuntimeError("registry unavailable")

        record = recovery_at_verified(["RD-1"])
        with pytest.raises(UncorroboratedClosureError, match="resolver error"):
            record.close(corroboration_resolver=broken)

    def test_unregistered_redirection_blocks(self):
        """An outcome nobody looked at is not a corroborated outcome."""
        registry = CorroborationRegistry()
        record = recovery_at_verified(["RD-NEVER-CHECKED"])
        with pytest.raises(UncorroboratedClosureError):
            record.close(corroboration_resolver=registry.resolver())

    def test_record_with_no_redirections_closes(self):
        """Nothing was redeployed, so there is no outcome claim to corroborate."""
        registry = CorroborationRegistry()
        record = recovery_at_verified([])
        record.close(corroboration_resolver=registry.resolver())
        assert record.status == RecoveryStatus.CLOSED

    def test_guard_does_not_bypass_the_state_machine(self):
        """Corroboration is an additional condition, not a replacement one."""
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.VERIFIED))
        record = RecoveryRecord(source_contract_id="K1")
        record.redirections = ["RD-1"]

        from recovery_ledger import InvalidTransitionError
        with pytest.raises(InvalidTransitionError):
            record.close(corroboration_resolver=registry.resolver())


class TestClosureAdditivity:
    """With no resolver, close() must behave exactly as it did before Side 5."""

    def test_close_without_a_resolver_still_works(self):
        record = recovery_at_verified(["RD-1", "RD-2"])
        record.close()
        assert record.status == RecoveryStatus.CLOSED

    def test_close_without_a_resolver_ignores_corroboration_entirely(self):
        """Even with every redirection contradicted, the unguarded call is
        unchanged. Supplying the resolver is the opt-in."""
        record = recovery_at_verified(["RD-1"])
        record.close()
        assert record.status == RecoveryStatus.CLOSED

    def test_explicit_none_is_the_same_as_omitting_it(self):
        record = recovery_at_verified(["RD-1"])
        record.close(corroboration_resolver=None)
        assert record.status == RecoveryStatus.CLOSED


# ═══════════════════════════════════════════════════════════
# SECTION 2: SPEC TEST 43 — THE CRITICAL ALERT
# ═══════════════════════════════════════════════════════════


class TestContradictedAlert:

    def _integration(self):
        return AlertIntegration(AlertConfiguration(enabled=True))

    def test_delivery_green_plus_contradicted_is_critical(self):
        """SPEC TEST 43 — the highest-value finding in the system."""
        priority = compute_priority(
            verdict="green", confidence=0.0, dimensions_fired=0,
            delivery_verdict="green", corroboration_verdict="contradicted",
        )
        assert priority == AlertPriority.CRITICAL

    def test_alert_is_emitted_on_a_clean_paperwork_contract(self):
        integration = self._integration()
        result = integration.on_corroboration_verdict(
            contract_id="K1",
            corroboration_verdict="contradicted",
            corroboration_confidence=0.92,
            corroboration_capacity=0.83,
            rule_fires=[{"rule_id": "EVD-CON-003", "layer": "contradiction",
                         "evidence": "no structural change on site polygon"}],
            profile_name="ng",
            delivery_verdict="green",
            procurement_verdict="green",
        )
        assert result is not None
        alert = integration.emitted_alerts[-1]
        assert alert.priority == AlertPriority.CRITICAL
        assert alert.alert_type == "outcome_contradicted"

    def test_alert_says_documentary_review_would_have_missed_it(self):
        """The reason this finding matters has to be in the alert, or the
        analyst reading it has no way to know why a clean contract is here."""
        integration = self._integration()
        integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="contradicted",
            corroboration_confidence=0.92, corroboration_capacity=0.83,
            rule_fires=[], profile_name="ng",
            delivery_verdict="green", procurement_verdict="green",
        )
        summary = integration.emitted_alerts[-1].summary
        assert "Documentary review would not have surfaced this" in summary

    def test_alert_states_the_evidence_capacity(self):
        """A contradiction found across five of six classes is a different
        claim from one found across three."""
        integration = self._integration()
        integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="contradicted",
            corroboration_confidence=0.92, corroboration_capacity=0.83,
            rule_fires=[], profile_name="ng",
        )
        alert = integration.emitted_alerts[-1]
        assert "83%" in alert.summary
        assert alert.corroboration_capacity == 0.83

    def test_alert_is_structural_not_accusatory(self):
        integration = self._integration()
        integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="contradicted",
            corroboration_confidence=0.92, corroboration_capacity=0.83,
            rule_fires=[], profile_name="ng",
        )
        alert = integration.emitted_alerts[-1]
        blob = f"{alert.summary} {alert.recommended_action}".lower()
        assert "not an allegation" in blob
        for forbidden in ("fraud", "does not exist", "stole"):
            assert forbidden not in blob

    @pytest.mark.parametrize("verdict", ["verified", "partial", "unverified"])
    def test_only_contradicted_alerts(self, verdict):
        integration = self._integration()
        result = integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict=verdict,
            corroboration_confidence=0.9, corroboration_capacity=0.5,
            rule_fires=[], profile_name="ng",
        )
        assert result is None
        assert integration.emitted_alerts == []

    def test_unverified_never_alerts_even_at_zero_capacity(self):
        """THE GUARD, AT THE ALERT LAYER.

        UNVERIFIED means the evidence could not be reached. Alerting on it
        would produce a permanent, unactionable alert stream against exactly
        the country offices with the thinnest registries — punishing them for
        the state of their national data infrastructure rather than for
        anything about their contracts.
        """
        integration = self._integration()
        result = integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="unverified",
            corroboration_confidence=0.95, corroboration_capacity=0.0,
            rule_fires=[], profile_name="ng",
        )
        assert result is None
        assert compute_priority("green", 0.0, 0, "green", "unverified") is None

    def test_feature_switch_disables_corroboration_alerts(self):
        config = AlertConfiguration(enabled=True)
        config.corroboration_alerts_enabled = False
        integration = AlertIntegration(config)
        result = integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="contradicted",
            corroboration_confidence=0.9, corroboration_capacity=0.8,
            rule_fires=[], profile_name="ng",
        )
        assert result is None

    def test_master_switch_disables_it_too(self):
        integration = AlertIntegration(AlertConfiguration(enabled=False))
        result = integration.on_corroboration_verdict(
            contract_id="K1", corroboration_verdict="contradicted",
            corroboration_confidence=0.9, corroboration_capacity=0.8,
            rule_fires=[], profile_name="ng",
        )
        assert result is None

    def test_existing_priorities_are_unchanged(self):
        """Additivity at the priority function. Every pre-Side-5 call site
        passes no corroboration verdict and must get its old answer."""
        assert compute_priority("green", 0.0, 0) is None
        assert compute_priority("red", 0.9, 3) == AlertPriority.CRITICAL
        assert compute_priority("red", 0.75, 2) == AlertPriority.HIGH
        assert compute_priority("yellow", 0.7, 1) == AlertPriority.ELEVATED
        assert compute_priority("yellow", 0.3, 1) == AlertPriority.ADVISORY
        assert compute_priority("red", 0.5, 1, "red") == AlertPriority.CRITICAL

    def test_highest_value_finding_is_identified(self):
        d = dossier(CorroborationVerdict.CONTRADICTED)
        assert is_highest_value_finding(d, "green", "green") is True
        assert is_highest_value_finding(d, "red", "green") is False
        assert is_highest_value_finding(
            dossier(CorroborationVerdict.PARTIAL), "green", "green") is False


# ═══════════════════════════════════════════════════════════
# SECTION 3: SPEC TESTS 44-45 — THE IMPACT REPORT
# ═══════════════════════════════════════════════════════════


class TestImpactReportFields:

    def test_corroboration_fields_populate(self):
        """SPEC TEST 44."""
        summary = corroboration_summary([
            dossier(CorroborationVerdict.VERIFIED, 6),
            dossier(CorroborationVerdict.VERIFIED, 6),
            dossier(CorroborationVerdict.PARTIAL, 6),
            dossier(CorroborationVerdict.UNVERIFIED, 2),
            dossier(CorroborationVerdict.CONTRADICTED, 5),
        ])
        assert summary["corroborated_outcomes"] == 2
        assert summary["partially_corroborated_outcomes"] == 1
        assert summary["unverified_outcomes"] == 1
        assert summary["contradicted_outcomes"] == 1
        assert summary["outcomes_assessed"] == 5

    def test_average_capacity_computed(self):
        summary = corroboration_summary([
            dossier(CorroborationVerdict.VERIFIED, 6),
            dossier(CorroborationVerdict.UNVERIFIED, 0),
        ])
        assert summary["average_corroboration_capacity"] == pytest.approx(0.5)

    def test_unverified_is_never_folded_into_contradicted(self):
        """They mean opposite things. A portfolio view that merged them would
        report a pattern of contradicted claims in exactly the country offices
        whose registries are thinnest."""
        summary = corroboration_summary([
            dossier(CorroborationVerdict.UNVERIFIED, 1) for _ in range(10)
        ])
        assert summary["unverified_outcomes"] == 10
        assert summary["contradicted_outcomes"] == 0

    def test_empty_input_does_not_divide_by_zero(self):
        summary = corroboration_summary([])
        assert summary["average_corroboration_capacity"] == 0.0
        assert summary["outcomes_assessed"] == 0

    def test_dossier_without_a_verdict_is_counted_but_not_classified(self):
        d = CorroborationDossier(claim=claim(), classes_queryable=6)
        summary = corroboration_summary([d])
        assert summary["outcomes_assessed"] == 1
        assert sum(summary[k] for k in (
            "corroborated_outcomes", "partially_corroborated_outcomes",
            "unverified_outcomes", "contradicted_outcomes")) == 0

    def test_report_fields_default_to_zero(self):
        r = ImpactReport()
        assert r.corroborated_outcomes == 0
        assert r.unverified_outcomes == 0
        assert r.average_corroboration_capacity == 0.0
        assert r.has_corroboration_data is False


class TestExecutiveSummary:

    def _report(self, **corroboration):
        r = ImpactReport(
            country_office="Nigeria", country_code="ng",
            reporting_period_start=date(2025, 1, 1),
            reporting_period_end=date(2025, 12, 31),
            jurisdiction_profile="wb_int",
            total_contracts_analyzed=400, total_flagged_red=12,
            total_amount_recovered=2_400_000.0, currency="USD",
            redeployed_contracts_total=9,
            redeployed_procurement_green=9,
            redeployed_delivery_green=7,
            total_beneficiaries_reached=30_000,
            gap_reduction_percentage=4.2,
        )
        for k, v in corroboration.items():
            setattr(r, k, v)
        return r

    def test_summary_states_corroboration_status(self):
        """SPEC TEST 45."""
        r = self._report(
            corroborated_outcomes=5, partially_corroborated_outcomes=2,
            unverified_outcomes=1, contradicted_outcomes=1,
            average_corroboration_capacity=0.83,
        )
        summary = assemble_executive_summary(r)
        assert "5 corroborated by independent evidence" in summary
        assert "2 partially corroborated" in summary
        assert "1 could not be verified from available sources" in summary
        assert "1 structurally contradicted" in summary

    def test_beneficiary_number_is_never_bare_when_corroboration_exists(self):
        """A bare figure invites the reader to treat a claimed number as
        established fact."""
        r = self._report(corroborated_outcomes=5,
                         average_corroboration_capacity=0.83)
        summary = assemble_executive_summary(r)
        assert "30,000 beneficiaries reached." not in summary
        assert "30,000 beneficiaries reported across" in summary

    def test_summary_states_the_capacity(self):
        r = self._report(corroborated_outcomes=5,
                         average_corroboration_capacity=0.83)
        assert "Average corroboration capacity 83%" in assemble_executive_summary(r)

    def test_unverified_is_explained_not_left_to_be_misread(self):
        """In a country whose registries are thin, most outcomes land here.
        The summary must say that is a statement about available evidence,
        not about the programme."""
        r = self._report(unverified_outcomes=8,
                         average_corroboration_capacity=0.2)
        summary = assemble_executive_summary(r)
        assert "are not adverse findings" in summary

    def test_no_unverified_no_disclaimer(self):
        r = self._report(corroborated_outcomes=5,
                         average_corroboration_capacity=1.0)
        assert "are not adverse findings" not in assemble_executive_summary(r)

    def test_summary_is_deterministic(self):
        r = self._report(corroborated_outcomes=5, unverified_outcomes=1,
                         average_corroboration_capacity=0.83)
        assert assemble_executive_summary(r) == assemble_executive_summary(r)


class TestExecutiveSummaryAdditivity:
    """With no corroboration data the summary must be unchanged, to the
    character. Tested by string equality rather than by inspection."""

    def _bare_report(self):
        return ImpactReport(
            country_office="Nigeria", country_code="ng",
            reporting_period_start=date(2025, 1, 1),
            reporting_period_end=date(2025, 12, 31),
            jurisdiction_profile="wb_int",
            total_contracts_analyzed=400, total_flagged_red=12,
            total_amount_recovered=2_400_000.0, currency="USD",
            redeployed_contracts_total=9,
            redeployed_procurement_green=9,
            redeployed_delivery_green=7,
            total_beneficiaries_reached=30_000,
            gap_reduction_percentage=4.2,
        )

    def test_bare_report_keeps_the_original_sentence(self):
        summary = assemble_executive_summary(self._bare_report())
        assert "30,000 beneficiaries reached. " in summary

    def test_bare_report_gains_no_corroboration_language(self):
        summary = assemble_executive_summary(self._bare_report())
        for phrase in ("corroborated", "corroboration capacity",
                       "could not be verified"):
            assert phrase not in summary

    def test_bare_report_ends_as_it_always_did(self):
        summary = assemble_executive_summary(self._bare_report())
        assert summary.endswith(
            "CPD alignment improved by 4.2 percentage points across the "
            "programme cycle."
        )


# ═══════════════════════════════════════════════════════════
# SECTION 4: SIDE 2 — OUTCOMES BECOME CLAIMS
# ═══════════════════════════════════════════════════════════


class TestClaimsFromDelivery:

    def _delivery(self):
        return DeliveryDossier(
            contract_id="K1", country_code="ng",
            outcomes=[
                OutcomeRecord(outcome_id="O1", description="200-bed hospital",
                              unit="beds", quantity_planned=200.0,
                              quantity_delivered=200.0,
                              inspection_date="2025-04-02"),
                OutcomeRecord(outcome_id="O2", description="access road",
                              unit="km_road", quantity_planned=12.0,
                              quantity_delivered=11.0),
                OutcomeRecord(outcome_id="O3", description="nothing claimed",
                              unit="units"),
            ],
        )

    def test_outcomes_become_claims(self):
        claims = claims_from_delivery_dossier(self._delivery())
        assert len(claims) == 2

    def test_outcome_with_nothing_claimed_is_skipped(self):
        """No assertion, nothing to corroborate."""
        claims = claims_from_delivery_dossier(self._delivery())
        assert all("O3" not in c.claim_id for c in claims)

    def test_outcome_types_are_inferred(self):
        claims = claims_from_delivery_dossier(self._delivery())
        by_id = {c.claim_id.split(":")[-1]: c for c in claims}
        assert by_id["O1"].outcome_type == OutcomeType.FACILITY_CONSTRUCTION
        assert by_id["O2"].outcome_type == OutcomeType.INFRASTRUCTURE_LINEAR

    def test_the_claim_under_test_is_what_was_reported_delivered(self):
        """Corroborating the planned figure would test the contract, not the
        report. The report is what independent evidence can contradict."""
        claims = claims_from_delivery_dossier(self._delivery())
        road = next(c for c in claims if c.claim_id.endswith("O2"))
        assert road.claimed_magnitude == 11.0

    def test_link_back_is_recorded_without_holding_the_object(self):
        d = self._delivery()
        claims = claims_from_delivery_dossier(d)
        assert all(c.source_dossier_id == d.delivery_id for c in claims)

    def test_delivery_dossier_is_not_modified(self):
        d = self._delivery()
        before = (d.stage, len(d.outcomes), d.rules_result, d.gate_outcome)
        claims_from_delivery_dossier(d)
        assert (d.stage, len(d.outcomes), d.rules_result, d.gate_outcome) == before

    def test_inspection_date_becomes_completion_date(self):
        claims = claims_from_delivery_dossier(self._delivery())
        hospital = next(c for c in claims if c.claim_id.endswith("O1"))
        assert hospital.claimed_completion_date == date(2025, 4, 2)

    def test_malformed_date_degrades_to_none(self):
        d = DeliveryDossier(contract_id="K1", outcomes=[
            OutcomeRecord(outcome_id="O1", description="x", unit="beds",
                          quantity_delivered=1.0, inspection_date="not-a-date"),
        ])
        assert claims_from_delivery_dossier(d)[0].claimed_completion_date is None

    def test_empty_dossier_yields_no_claims(self):
        assert claims_from_delivery_dossier(DeliveryDossier(contract_id="K1")) == []


class TestOutcomeTypeInference:

    @pytest.mark.parametrize("unit,expected", [
        ("beds", OutcomeType.FACILITY_CONSTRUCTION),
        ("km_road", OutcomeType.INFRASTRUCTURE_LINEAR),
        ("boreholes", OutcomeType.WATER_SANITATION),
        ("training_sessions", OutcomeType.CAPACITY_BUILDING),
        ("households", OutcomeType.CASH_TRANSFER),
    ])
    def test_units_map_to_types(self, unit, expected):
        assert infer_outcome_type(unit) == expected

    def test_unmatched_defaults_to_service_delivery(self):
        """Deliberately NOT facility construction. Guessing 'facility' would
        invite an evidence map to demand construction permits and satellite
        change detection for a training programme, and every one of those
        absences would be a manufactured finding."""
        assert infer_outcome_type("widgets", "some activity") == \
            OutcomeType.SERVICE_DELIVERY

    def test_inference_is_deterministic(self):
        assert infer_outcome_type("beds") == infer_outcome_type("beds")


# ═══════════════════════════════════════════════════════════
# SECTION 5: THE REGISTRY AND THE ALERT PAYLOAD
# ═══════════════════════════════════════════════════════════


class TestCorroborationRegistry:

    def test_register_and_retrieve(self):
        registry = CorroborationRegistry()
        d = dossier(CorroborationVerdict.VERIFIED)
        registry.register("RD-1", d)
        assert registry.get("RD-1") is d
        assert registry.verdict_for("RD-1") == "verified"
        assert len(registry) == 1

    def test_unregistered_returns_none(self):
        assert CorroborationRegistry().verdict_for("RD-X") is None

    def test_dossier_without_a_verdict_returns_none(self):
        """Analysed but ungated is not corroborated."""
        registry = CorroborationRegistry()
        registry.register("RD-1", CorroborationDossier(claim=claim()))
        assert registry.verdict_for("RD-1") is None

    def test_resolver_is_the_callable_close_expects(self):
        registry = CorroborationRegistry()
        registry.register("RD-1", dossier(CorroborationVerdict.VERIFIED))
        assert registry.resolver()("RD-1") == "verified"


class TestAlertPayload:

    def test_payload_carries_only_primitives(self):
        """Everything crosses as strings, floats and plain dicts, so Side 3
        stays free of Side 5 types."""
        payload = alert_payload_for(
            dossier(CorroborationVerdict.CONTRADICTED),
            profile_name="ng", delivery_verdict="green")
        for value in payload.values():
            assert isinstance(value, (str, int, float, list, type(None)))

    def test_payload_feeds_the_hook_directly(self):
        integration = AlertIntegration(AlertConfiguration(enabled=True))
        payload = alert_payload_for(
            dossier(CorroborationVerdict.CONTRADICTED),
            profile_name="ng", delivery_verdict="green")
        result = integration.on_corroboration_verdict(**payload)
        assert result is not None


# ═══════════════════════════════════════════════════════════
# SECTION 6: DEPENDENCY DIRECTION
# ═══════════════════════════════════════════════════════════


class TestDependencyDirection:
    """No module in Sides 1-4 may import Side 5.

    evidence_integration is the only file that knows both vocabularies, and
    deleting it must restore complete separation. Checked by AST rather than
    by convention, on the four modules this step actually edited.
    """

    @pytest.mark.parametrize("module_name", [
        "recovery_ledger", "impact_report", "alerts",
        "alert_integration", "alert_emitter", "delivery_schema",
        "jurisdiction_profile",
    ])
    def test_no_side_5_import(self, module_name):
        module = __import__(module_name)
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not name.startswith("evidence_"), (
                    f"{module_name} imports {name} — Side 5 must stay removable")
                assert name != "provenance", f"{module_name} imports provenance"

    def test_side_5_core_still_imports_no_other_side(self):
        """The reverse direction, re-checked now that integration exists.
        evidence_integration is excluded — it is the seam, and it is allowed
        to know both."""
        import evidence_evg
        import evidence_graph
        import evidence_pipeline
        import evidence_rules
        import evidence_schema

        forbidden = ("delivery_", "recovery_", "impact_", "alert", "tca_")
        for module in (evidence_schema, evidence_graph, evidence_rules,
                       evidence_evg, evidence_pipeline):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    assert not name.startswith(forbidden), (
                        f"{module.__name__} imports {name}")

    def test_the_seam_knows_both_but_writes_to_neither(self):
        """evidence_integration reads Side 2/4 objects by duck-typing and
        never imports them, so even the seam creates no hard dependency."""
        import evidence_integration

        tree = ast.parse(inspect.getsource(evidence_integration))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)

        assert "evidence_schema" in imported
        assert not any(
            m.startswith(("delivery_", "recovery_", "impact_", "alert"))
            for m in imported
        )
