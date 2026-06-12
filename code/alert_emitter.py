"""
SUNLIGHT Intelligence Alert System — Emission Mechanisms
==========================================================

How alerts leave SUNLIGHT. The pipeline produces intelligence;
these emitters route it to consuming institutions.

Emitter types:
    WebhookEmitter — HTTPS POST to configured endpoint with HMAC signature
    FileEmitter    — JSON-lines file for batch processing environments
    LogEmitter     — Structured logging output for development/testing

Design constraints:
    - Emitter failures NEVER propagate to the pipeline
    - Every emission is wrapped in try/except
    - The pipeline produces identical results whether alerts succeed or fail
    - HMAC-SHA256 signature on every webhook for payload integrity

Authors: Rimwaya Ouedraogo, Hugo Villalba
License: Proprietary — SUNLIGHT Infrastructure
Version: 1.0.0
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from alerts import AlertPriority, IntelligenceAlert, TriageBrief


# ═══════════════════════════════════════════════════════════
# SECTION 1: EMISSION RESULT
# ═══════════════════════════════════════════════════════════


@dataclass
class EmissionResult:
    """Result of attempting to emit an alert or triage brief."""
    success: bool
    emitter_type: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    payload_id: str = ""
    retry_count: int = 0
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════
# SECTION 2: ALERT CONFIGURATION
# ═══════════════════════════════════════════════════════════


@dataclass
class AlertConfiguration:
    """
    Per-deployment alert configuration.

    Loaded from environment or config dict at startup.
    NOT modifiable at runtime via API — configuration changes
    require a deployment update. Security decision: alert routing
    should not be modifiable by anyone with API access.
    """
    enabled: bool = False
    emitters: List[Any] = field(default_factory=list)  # List[AlertEmitter]

    # Threshold configuration
    min_verdict: str = "YELLOW"
    min_confidence: float = 0.50
    min_dimensions: int = 1

    # Delivery alerts
    delivery_alerts_enabled: bool = True

    # Batch behavior
    batch_mode: str = "brief"  # "brief" or "individual"

    # Rate limiting
    max_alerts_per_hour: int = 100
    cooldown_seconds: int = 5

    def meets_threshold(
        self,
        verdict: str,
        confidence: float,
        dimensions_fired: int,
    ) -> bool:
        """Check if a verdict meets the configured alert threshold."""
        v = verdict.lower() if verdict else ""

        # GREEN never alerts
        if v == "green":
            return False

        # Verdict ordering: red > yellow > green
        verdict_rank = {"red": 2, "yellow": 1, "green": 0}
        min_rank = verdict_rank.get(self.min_verdict.lower(), 1)
        if verdict_rank.get(v, 0) < min_rank:
            return False

        if confidence < self.min_confidence:
            return False

        if dimensions_fired < self.min_dimensions:
            return False

        return True

    def to_safe_dict(self) -> Dict[str, Any]:
        """
        Return configuration as dict for API exposure.
        Does NOT expose webhook URLs or shared secrets.
        """
        return {
            "enabled": self.enabled,
            "min_verdict": self.min_verdict,
            "min_confidence": self.min_confidence,
            "min_dimensions": self.min_dimensions,
            "delivery_alerts_enabled": self.delivery_alerts_enabled,
            "batch_mode": self.batch_mode,
            "max_alerts_per_hour": self.max_alerts_per_hour,
            "cooldown_seconds": self.cooldown_seconds,
            "emitter_count": len(self.emitters),
            "emitter_types": [type(e).__name__ for e in self.emitters],
        }


# ═══════════════════════════════════════════════════════════
# SECTION 3: RATE LIMITER
# ═══════════════════════════════════════════════════════════


class RateLimiter:
    """
    Token-bucket rate limiter for alert emission.

    Enforces max_per_hour globally and cooldown_seconds per contract.
    """

    def __init__(self, max_per_hour: int = 100, cooldown_seconds: int = 5):
        self.max_per_hour = max_per_hour
        self.cooldown_seconds = cooldown_seconds
        self._hour_window: List[float] = []
        self._last_emit: Dict[str, float] = {}

    def allow(self, contract_id: str = "") -> bool:
        """Check if emission is allowed under rate limits."""
        now = time.monotonic()

        # Per-contract cooldown
        if contract_id and contract_id in self._last_emit:
            if now - self._last_emit[contract_id] < self.cooldown_seconds:
                return False

        # Global hourly limit
        cutoff = now - 3600
        self._hour_window = [t for t in self._hour_window if t > cutoff]
        if len(self._hour_window) >= self.max_per_hour:
            return False

        return True

    def record(self, contract_id: str = ""):
        """Record an emission for rate tracking."""
        now = time.monotonic()
        self._hour_window.append(now)
        if contract_id:
            self._last_emit[contract_id] = now

    def reset(self):
        """Reset all rate limiting state. For testing."""
        self._hour_window.clear()
        self._last_emit.clear()


# ═══════════════════════════════════════════════════════════
# SECTION 4: SERIALIZATION
# ═══════════════════════════════════════════════════════════


def _serialize_payload(payload: Union[IntelligenceAlert, TriageBrief]) -> str:
    """
    Serialize an alert or triage brief to JSON string.

    Handles datetime, Enum, and nested dataclass serialization.
    """
    def _default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, '__dataclass_fields__'):
            return asdict(obj)
        return str(obj)

    if hasattr(payload, '__dataclass_fields__'):
        data = asdict(payload)
    else:
        data = payload

    return json.dumps(data, default=_default, sort_keys=True)


def _compute_hmac(body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for payload integrity."""
    return hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _get_payload_id(payload: Union[IntelligenceAlert, TriageBrief]) -> str:
    """Extract the payload identifier."""
    if isinstance(payload, IntelligenceAlert):
        return payload.alert_id
    if isinstance(payload, TriageBrief):
        return payload.brief_id
    return str(uuid.uuid4())


def _get_payload_type(payload: Union[IntelligenceAlert, TriageBrief]) -> str:
    """Determine payload type string."""
    if isinstance(payload, IntelligenceAlert):
        return "alert"
    if isinstance(payload, TriageBrief):
        return "triage_brief"
    return "unknown"


def _get_highest_priority(
    payload: Union[IntelligenceAlert, TriageBrief],
) -> str:
    """Extract the highest priority level from the payload."""
    if isinstance(payload, IntelligenceAlert):
        return payload.priority.value if payload.priority else "advisory"
    if isinstance(payload, TriageBrief):
        for level in ("critical", "high", "elevated", "advisory"):
            if payload.alerts_by_priority.get(level, 0) > 0:
                return level
    return "advisory"


# ═══════════════════════════════════════════════════════════
# SECTION 5: EMITTER BASE CLASS
# ═══════════════════════════════════════════════════════════


class AlertEmitter(ABC):
    """
    Base class for alert emission.

    SUNLIGHT produces alerts. The consuming institution routes them.
    Each emitter subclass implements a specific transport mechanism.
    """

    @abstractmethod
    def emit(
        self, payload: Union[IntelligenceAlert, TriageBrief]
    ) -> EmissionResult:
        """
        Emit a payload (alert or triage brief).

        Args:
            payload: IntelligenceAlert or TriageBrief.

        Returns:
            EmissionResult with success/failure status.
        """
        pass


# ═══════════════════════════════════════════════════════════
# SECTION 6: WEBHOOK EMITTER
# ═══════════════════════════════════════════════════════════


class WebhookEmitter(AlertEmitter):
    """
    HTTPS POST to configured endpoint with HMAC-SHA256 signature.

    Headers:
        Content-Type: application/json
        X-Sunlight-Alert-Id: {alert_id or brief_id}
        X-Sunlight-Priority: {highest priority}
        X-Sunlight-Signature: HMAC-SHA256({body}, {shared_secret})
        X-Sunlight-Timestamp: {ISO 8601}
        X-Sunlight-Payload-Type: "alert" or "triage_brief"
    """

    def __init__(
        self,
        webhook_url: str,
        shared_secret: str,
        timeout_seconds: int = 30,
        retry_count: int = 3,
        http_post: Optional[Callable] = None,
    ):
        self.webhook_url = webhook_url
        self.shared_secret = shared_secret
        self.timeout_seconds = timeout_seconds
        self.retry_count = retry_count
        # Injectable HTTP POST for testing (avoids real HTTP in tests)
        self._http_post = http_post

    def emit(
        self, payload: Union[IntelligenceAlert, TriageBrief]
    ) -> EmissionResult:
        """POST payload to webhook URL with HMAC signature and retry."""
        body = _serialize_payload(payload)
        signature = _compute_hmac(body, self.shared_secret)
        payload_id = _get_payload_id(payload)
        payload_type = _get_payload_type(payload)
        priority = _get_highest_priority(payload)
        timestamp = datetime.now(timezone.utc).isoformat()

        headers = {
            "Content-Type": "application/json",
            "X-Sunlight-Alert-Id": payload_id,
            "X-Sunlight-Priority": priority,
            "X-Sunlight-Signature": signature,
            "X-Sunlight-Timestamp": timestamp,
            "X-Sunlight-Payload-Type": payload_type,
        }

        last_error = None
        for attempt in range(self.retry_count):
            try:
                if self._http_post:
                    # Use injected function (for testing)
                    response = self._http_post(
                        self.webhook_url, headers=headers, body=body,
                        timeout=self.timeout_seconds,
                    )
                    if response.get("status_code", 200) >= 400:
                        raise Exception(
                            f"HTTP {response.get('status_code', 500)}"
                        )
                else:
                    # Production path: use urllib (no external dependencies)
                    import urllib.request
                    req = urllib.request.Request(
                        self.webhook_url,
                        data=body.encode("utf-8"),
                        headers=headers,
                        method="POST",
                    )
                    with urllib.request.urlopen(
                        req, timeout=self.timeout_seconds
                    ) as resp:
                        if resp.status >= 400:
                            raise Exception(f"HTTP {resp.status}")

                return EmissionResult(
                    success=True,
                    emitter_type="WebhookEmitter",
                    payload_id=payload_id,
                    retry_count=attempt,
                )

            except Exception as e:
                last_error = str(e)
                if attempt < self.retry_count - 1:
                    # Exponential backoff: 1s, 2s, 4s...
                    time.sleep(min(2 ** attempt, 10))

        return EmissionResult(
            success=False,
            emitter_type="WebhookEmitter",
            payload_id=payload_id,
            retry_count=self.retry_count,
            error=last_error,
        )


# ═══════════════════════════════════════════════════════════
# SECTION 7: FILE EMITTER
# ═══════════════════════════════════════════════════════════


class FileEmitter(AlertEmitter):
    """
    Writes alerts to JSON-lines file for batch processing.

    Each line is a complete JSON object (one alert or brief per line).
    For environments without webhook capability.
    """

    def __init__(self, output_path: str):
        self.output_path = output_path

    def emit(
        self, payload: Union[IntelligenceAlert, TriageBrief]
    ) -> EmissionResult:
        """Append serialized payload as a JSON line."""
        payload_id = _get_payload_id(payload)
        try:
            body = _serialize_payload(payload)
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            with open(self.output_path, "a") as f:
                f.write(body + "\n")

            return EmissionResult(
                success=True,
                emitter_type="FileEmitter",
                payload_id=payload_id,
            )
        except Exception as e:
            return EmissionResult(
                success=False,
                emitter_type="FileEmitter",
                payload_id=payload_id,
                error=str(e),
            )


# ═══════════════════════════════════════════════════════════
# SECTION 8: LOG EMITTER
# ═══════════════════════════════════════════════════════════


class LogEmitter(AlertEmitter):
    """
    Structured logging output for development and testing.

    Maps alert priority to log severity:
        CRITICAL → logging.CRITICAL
        HIGH     → logging.ERROR
        ELEVATED → logging.WARNING
        ADVISORY → logging.INFO
    """

    _PRIORITY_LOG_LEVEL = {
        "critical": logging.CRITICAL,
        "high": logging.ERROR,
        "elevated": logging.WARNING,
        "advisory": logging.INFO,
    }

    def __init__(self, logger_name: str = "sunlight.alerts"):
        self.logger = logging.getLogger(logger_name)

    def emit(
        self, payload: Union[IntelligenceAlert, TriageBrief]
    ) -> EmissionResult:
        """Log the alert at the appropriate severity level."""
        payload_id = _get_payload_id(payload)
        try:
            priority = _get_highest_priority(payload)
            level = self._PRIORITY_LOG_LEVEL.get(priority, logging.INFO)

            if isinstance(payload, IntelligenceAlert):
                self.logger.log(
                    level,
                    "Intelligence alert: %s | contract=%s | verdict=%s | "
                    "priority=%s | confidence=%.0f%% | dims=%d",
                    payload_id,
                    payload.contract_id,
                    payload.verdict,
                    priority,
                    payload.confidence * 100,
                    payload.dimensions_fired,
                )
            elif isinstance(payload, TriageBrief):
                self.logger.log(
                    level,
                    "Triage brief: %s | batch=%s | alerts=%d | "
                    "priority=%s | patterns=%d",
                    payload_id,
                    payload.batch_id or "none",
                    payload.total_alerts,
                    priority,
                    len(payload.patterns),
                )

            return EmissionResult(
                success=True,
                emitter_type="LogEmitter",
                payload_id=payload_id,
            )
        except Exception as e:
            return EmissionResult(
                success=False,
                emitter_type="LogEmitter",
                payload_id=payload_id,
                error=str(e),
            )
