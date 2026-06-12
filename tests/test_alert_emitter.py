"""
Tests for SUNLIGHT Intelligence Alert System — Emission Mechanisms.

Covers:
    WebhookEmitter:
        14. Mock endpoint receives correctly formatted POST with HMAC signature
            and correct headers
        - Retry on failure
        - Payload type header correct for alert vs brief
        - Priority header reflects highest priority

    FileEmitter:
        15. Alert written to JSON-lines file, parseable, complete

    LogEmitter:
        16. Alert logged with correct severity

    AlertConfiguration:
        - meets_threshold filtering
        - Safe dict does not expose secrets
        - Validation logic

    RateLimiter:
        - Per-contract cooldown
        - Global hourly limit

    Serialization:
        - Payload serialization round-trip
        - HMAC computation determinism
"""

import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from alerts import (
    AlertPriority,
    IntelligenceAlert,
    RuleCitation,
    TriageBrief,
    assemble_summary,
    assemble_recommended_action,
)
from alert_emitter import (
    AlertConfiguration,
    AlertEmitter,
    EmissionResult,
    FileEmitter,
    LogEmitter,
    RateLimiter,
    WebhookEmitter,
    _compute_hmac,
    _get_highest_priority,
    _get_payload_id,
    _get_payload_type,
    _serialize_payload,
)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════


def _make_alert(**kwargs) -> IntelligenceAlert:
    defaults = dict(
        alert_type="procurement",
        contract_id="TEST-001",
        contract_title="Test Contract",
        vendor="TestVendor",
        agency="TestAgency",
        contract_value=1000000.0,
        currency="USD",
        award_date="2024-06-01",
        verdict="red",
        confidence=0.85,
        priority=AlertPriority.HIGH,
        jurisdiction_profile="us_federal",
        country_code="US",
        dimensions_fired=2,
        dimensions_required=2,
        typologies=["CRI_MARKUP", "TCA_PROC"],
        rule_citations=[
            RuleCitation(
                rule_id="PROC-001",
                rule_name="Test Rule",
                layer="procurement",
                confidence=0.90,
                legal_basis="FAR Part 6",
                evidence="Test evidence",
                recommendation="Review",
            ),
        ],
    )
    defaults.update(kwargs)
    alert = IntelligenceAlert(**defaults)
    alert.summary = assemble_summary(alert)
    alert.recommended_action = assemble_recommended_action(alert)
    return alert


def _make_brief(**kwargs) -> TriageBrief:
    defaults = dict(
        batch_id="BATCH-001",
        jurisdiction_profile="us_federal",
        total_contracts_analyzed=100,
        total_alerts=5,
        alerts_by_priority={"critical": 1, "high": 2, "elevated": 2, "advisory": 0},
        ranked_alerts=[],
        patterns=[],
        executive_summary="Test executive summary.",
    )
    defaults.update(kwargs)
    return TriageBrief(**defaults)


# ═══════════════════════════════════════════════════════════
# WEBHOOK EMITTER TESTS
# ═══════════════════════════════════════════════════════════


class TestWebhookEmitter:
    def test_webhook_posts_with_correct_headers(self):
        """Mock endpoint receives POST with HMAC signature and headers."""
        captured = {}

        def mock_post(url, headers, body, timeout):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = body
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="test-secret",
            http_post=mock_post,
        )
        alert = _make_alert()
        result = emitter.emit(alert)

        assert result.success is True
        assert result.emitter_type == "WebhookEmitter"
        assert captured["url"] == "https://example.com/webhook"

        # Verify headers
        h = captured["headers"]
        assert h["Content-Type"] == "application/json"
        assert h["X-Sunlight-Alert-Id"] == alert.alert_id
        assert h["X-Sunlight-Priority"] == "high"
        assert h["X-Sunlight-Payload-Type"] == "alert"
        assert "X-Sunlight-Signature" in h
        assert "X-Sunlight-Timestamp" in h

    def test_webhook_hmac_signature_valid(self):
        """HMAC signature matches body + secret."""
        captured = {}

        def mock_post(url, headers, body, timeout):
            captured["headers"] = headers
            captured["body"] = body
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="my-secret",
            http_post=mock_post,
        )
        emitter.emit(_make_alert())

        expected_sig = _compute_hmac(captured["body"], "my-secret")
        assert captured["headers"]["X-Sunlight-Signature"] == expected_sig

    def test_webhook_retry_on_failure(self):
        """Webhook retries on HTTP error."""
        call_count = {"n": 0}

        def mock_post(url, headers, body, timeout):
            call_count["n"] += 1
            if call_count["n"] < 3:
                return {"status_code": 500}
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            retry_count=3,
            http_post=mock_post,
        )
        result = emitter.emit(_make_alert())
        assert result.success is True
        assert call_count["n"] == 3

    def test_webhook_all_retries_fail(self):
        """All retries fail → EmissionResult.success is False."""
        def mock_post(url, headers, body, timeout):
            return {"status_code": 500}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            retry_count=2,
            http_post=mock_post,
        )
        result = emitter.emit(_make_alert())
        assert result.success is False
        assert result.error is not None

    def test_webhook_brief_payload_type(self):
        """TriageBrief sends X-Sunlight-Payload-Type: triage_brief."""
        captured = {}

        def mock_post(url, headers, body, timeout):
            captured["headers"] = headers
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            http_post=mock_post,
        )
        brief = _make_brief()
        emitter.emit(brief)

        assert captured["headers"]["X-Sunlight-Payload-Type"] == "triage_brief"

    def test_webhook_critical_priority_header(self):
        """CRITICAL alert sets X-Sunlight-Priority: critical."""
        captured = {}

        def mock_post(url, headers, body, timeout):
            captured["headers"] = headers
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            http_post=mock_post,
        )
        alert = _make_alert(priority=AlertPriority.CRITICAL)
        emitter.emit(alert)

        assert captured["headers"]["X-Sunlight-Priority"] == "critical"

    def test_webhook_brief_priority_from_highest(self):
        """TriageBrief priority header reflects highest priority in brief."""
        captured = {}

        def mock_post(url, headers, body, timeout):
            captured["headers"] = headers
            return {"status_code": 200}

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            http_post=mock_post,
        )
        brief = _make_brief(
            alerts_by_priority={"critical": 1, "high": 3, "elevated": 2, "advisory": 0},
        )
        emitter.emit(brief)

        assert captured["headers"]["X-Sunlight-Priority"] == "critical"


# ═══════════════════════════════════════════════════════════
# FILE EMITTER TESTS
# ═══════════════════════════════════════════════════════════


class TestFileEmitter:
    def test_file_emitter_writes_json_line(self):
        """Alert written to JSON-lines file, parseable."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            path = f.name

        try:
            emitter = FileEmitter(output_path=path)
            alert = _make_alert()
            result = emitter.emit(alert)

            assert result.success is True
            assert result.emitter_type == "FileEmitter"

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["contract_id"] == "TEST-001"
            assert data["verdict"] == "red"
        finally:
            os.unlink(path)

    def test_file_emitter_appends(self):
        """Multiple emissions append to same file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            path = f.name

        try:
            emitter = FileEmitter(output_path=path)
            emitter.emit(_make_alert(contract_id="A"))
            emitter.emit(_make_alert(contract_id="B"))

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            assert json.loads(lines[0])["contract_id"] == "A"
            assert json.loads(lines[1])["contract_id"] == "B"
        finally:
            os.unlink(path)

    def test_file_emitter_brief(self):
        """TriageBrief written to JSON-lines file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            path = f.name

        try:
            emitter = FileEmitter(output_path=path)
            brief = _make_brief()
            result = emitter.emit(brief)

            assert result.success is True
            with open(path) as f:
                data = json.loads(f.readline())
            assert data["batch_id"] == "BATCH-001"
            assert data["total_alerts"] == 5
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════
# LOG EMITTER TESTS
# ═══════════════════════════════════════════════════════════


class TestLogEmitter:
    def test_log_emitter_logs_alert(self, caplog):
        """Alert logged with correct severity."""
        emitter = LogEmitter(logger_name="test.alerts")
        alert = _make_alert(priority=AlertPriority.CRITICAL)

        with caplog.at_level(logging.DEBUG, logger="test.alerts"):
            result = emitter.emit(alert)

        assert result.success is True
        assert result.emitter_type == "LogEmitter"
        assert "Intelligence alert" in caplog.text
        assert "TEST-001" in caplog.text

    def test_log_emitter_critical_uses_critical_level(self, caplog):
        """CRITICAL priority → logging.CRITICAL level."""
        emitter = LogEmitter(logger_name="test.alerts.crit")
        alert = _make_alert(priority=AlertPriority.CRITICAL)

        with caplog.at_level(logging.DEBUG, logger="test.alerts.crit"):
            emitter.emit(alert)

        assert any(r.levelno == logging.CRITICAL for r in caplog.records)

    def test_log_emitter_advisory_uses_info_level(self, caplog):
        """ADVISORY priority → logging.INFO level."""
        emitter = LogEmitter(logger_name="test.alerts.info")
        alert = _make_alert(priority=AlertPriority.ADVISORY)

        with caplog.at_level(logging.DEBUG, logger="test.alerts.info"):
            emitter.emit(alert)

        assert any(r.levelno == logging.INFO for r in caplog.records)

    def test_log_emitter_brief(self, caplog):
        """TriageBrief logged correctly."""
        emitter = LogEmitter(logger_name="test.alerts.brief")
        brief = _make_brief()

        with caplog.at_level(logging.DEBUG, logger="test.alerts.brief"):
            result = emitter.emit(brief)

        assert result.success is True
        assert "Triage brief" in caplog.text


# ═══════════════════════════════════════════════════════════
# ALERT CONFIGURATION TESTS
# ═══════════════════════════════════════════════════════════


class TestAlertConfiguration:
    def test_meets_threshold_green_never_alerts(self):
        config = AlertConfiguration(enabled=True)
        assert config.meets_threshold("green", 0.99, 5) is False

    def test_meets_threshold_red_above_min(self):
        config = AlertConfiguration(
            enabled=True, min_verdict="YELLOW",
            min_confidence=0.50, min_dimensions=1,
        )
        assert config.meets_threshold("red", 0.80, 2) is True

    def test_meets_threshold_below_confidence(self):
        config = AlertConfiguration(
            enabled=True, min_confidence=0.70,
        )
        assert config.meets_threshold("red", 0.60, 2) is False

    def test_meets_threshold_below_dimensions(self):
        config = AlertConfiguration(
            enabled=True, min_dimensions=2,
        )
        assert config.meets_threshold("red", 0.80, 1) is False

    def test_meets_threshold_yellow_when_min_is_red(self):
        config = AlertConfiguration(
            enabled=True, min_verdict="RED",
        )
        assert config.meets_threshold("yellow", 0.80, 2) is False

    def test_safe_dict_no_secrets(self):
        """Safe dict does not expose webhook URLs or secrets."""
        config = AlertConfiguration(
            enabled=True,
            emitters=[
                WebhookEmitter("https://secret.example.com", "super-secret"),
            ],
        )
        safe = config.to_safe_dict()
        assert "secret" not in json.dumps(safe).lower()
        assert "webhook_url" not in safe
        assert "shared_secret" not in safe
        assert safe["emitter_count"] == 1
        assert "WebhookEmitter" in safe["emitter_types"]


# ═══════════════════════════════════════════════════════════
# RATE LIMITER TESTS
# ═══════════════════════════════════════════════════════════


class TestRateLimiter:
    def test_allows_first_emission(self):
        limiter = RateLimiter(max_per_hour=100, cooldown_seconds=5)
        assert limiter.allow("C001") is True

    def test_cooldown_blocks_rapid_same_contract(self):
        limiter = RateLimiter(max_per_hour=100, cooldown_seconds=5)
        limiter.record("C001")
        assert limiter.allow("C001") is False

    def test_different_contract_not_affected_by_cooldown(self):
        limiter = RateLimiter(max_per_hour=100, cooldown_seconds=5)
        limiter.record("C001")
        assert limiter.allow("C002") is True

    def test_hourly_limit(self):
        limiter = RateLimiter(max_per_hour=3, cooldown_seconds=0)
        for i in range(3):
            assert limiter.allow(f"C{i}") is True
            limiter.record(f"C{i}")
        assert limiter.allow("C99") is False

    def test_reset_clears_state(self):
        limiter = RateLimiter(max_per_hour=1, cooldown_seconds=5)
        limiter.record("C001")
        assert limiter.allow("C001") is False
        limiter.reset()
        assert limiter.allow("C001") is True


# ═══════════════════════════════════════════════════════════
# SERIALIZATION TESTS
# ═══════════════════════════════════════════════════════════


class TestSerialization:
    def test_alert_serializes_to_valid_json(self):
        alert = _make_alert()
        body = _serialize_payload(alert)
        data = json.loads(body)
        assert data["contract_id"] == "TEST-001"
        assert data["verdict"] == "red"

    def test_brief_serializes_to_valid_json(self):
        brief = _make_brief()
        body = _serialize_payload(brief)
        data = json.loads(body)
        assert data["batch_id"] == "BATCH-001"

    def test_hmac_determinism(self):
        """Same body + secret → same HMAC."""
        sig1 = _compute_hmac("test body", "secret")
        sig2 = _compute_hmac("test body", "secret")
        assert sig1 == sig2

    def test_hmac_different_secret(self):
        """Different secret → different HMAC."""
        sig1 = _compute_hmac("test body", "secret1")
        sig2 = _compute_hmac("test body", "secret2")
        assert sig1 != sig2

    def test_payload_id_extraction(self):
        alert = _make_alert()
        assert _get_payload_id(alert) == alert.alert_id

        brief = _make_brief()
        assert _get_payload_id(brief) == brief.brief_id

    def test_payload_type_detection(self):
        assert _get_payload_type(_make_alert()) == "alert"
        assert _get_payload_type(_make_brief()) == "triage_brief"

    def test_highest_priority_from_alert(self):
        assert _get_highest_priority(
            _make_alert(priority=AlertPriority.CRITICAL)
        ) == "critical"

    def test_highest_priority_from_brief(self):
        brief = _make_brief(
            alerts_by_priority={"critical": 0, "high": 3, "elevated": 0, "advisory": 0},
        )
        assert _get_highest_priority(brief) == "high"


# ═══════════════════════════════════════════════════════════
# EMISSION FAILURE ISOLATION TESTS
# ═══════════════════════════════════════════════════════════


class TestEmissionFailureIsolation:
    def test_webhook_failure_returns_result_not_exception(self):
        """Webhook failure returns EmissionResult, never raises."""
        def mock_post(url, headers, body, timeout):
            raise ConnectionError("Network down")

        emitter = WebhookEmitter(
            webhook_url="https://example.com/webhook",
            shared_secret="secret",
            retry_count=1,
            http_post=mock_post,
        )
        result = emitter.emit(_make_alert())
        assert result.success is False
        assert "Network down" in result.error

    def test_file_emitter_bad_path_returns_result(self):
        """File emitter with bad path returns failure, not exception."""
        emitter = FileEmitter(output_path="/nonexistent/deep/path/alerts.jsonl")
        result = emitter.emit(_make_alert())
        # May succeed or fail depending on OS permissions; either way, no exception
        assert isinstance(result, EmissionResult)
