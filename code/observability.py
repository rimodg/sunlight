"""
SUNLIGHT Observability
========================

Prometheus-compatible metrics, structured request logging,
and SLO-based alerting configuration.

Stack: Prometheus + Grafana (OSS)
Metrics exported at /metrics endpoint (Prometheus format).

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import time
import json
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, List
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("observability")

# ---------------------------------------------------------------------------
# In-process metrics collector (Prometheus-compatible)
# ---------------------------------------------------------------------------

class MetricsCollector:
    """
    Thread-safe metrics collector that exports Prometheus text format.
    Tracks counters, histograms, and gauges.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._gauges: Dict[str, float] = {}

    def inc_counter(self, name: str, labels: Dict[str, str] = None, value: float = 1.0):
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] += value

    def observe_histogram(self, name: str, value: float, labels: Dict[str, str] = None):
        key = self._key(name, labels)
        with self._lock:
            self._histograms[key].append(value)

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def _key(self, name: str, labels: Optional[Dict] = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines = []
        lines.append("# SUNLIGHT Metrics")

        with self._lock:
            # Counters
            for key, val in sorted(self._counters.items()):
                name = key.split("{")[0] if "{" in key else key
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{key} {val}")

            # Gauges
            for key, val in sorted(self._gauges.items()):
                name = key.split("{")[0] if "{" in key else key
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{key} {val}")

            # Histograms (export as summary with quantiles)
            for key, vals in sorted(self._histograms.items()):
                if not vals:
                    continue
                name = key.split("{")[0] if "{" in key else key
                sorted_vals = sorted(vals)
                n = len(sorted_vals)
                p50 = sorted_vals[int(n * 0.50)] if n > 0 else 0
                p95 = sorted_vals[int(n * 0.95)] if n > 0 else 0
                p99 = sorted_vals[int(n * 0.99)] if n > 0 else 0
                total = sum(sorted_vals)

                base = key.replace("{", "_summary{") if "{" in key else key
                lines.append(f"# TYPE {name} summary")
                if "{" in key:
                    prefix = key.split("{")[0]
                    label_part = key.split("{")[1]
                    lines.append(f'{prefix}{{quantile="0.5",{label_part} {p50}')
                    lines.append(f'{prefix}{{quantile="0.95",{label_part} {p95}')
                    lines.append(f'{prefix}{{quantile="0.99",{label_part} {p99}')
                    lines.append(f'{prefix}_count{{{label_part} {n}')
                    lines.append(f'{prefix}_sum{{{label_part} {total}')
                else:
                    lines.append(f'{key}{{quantile="0.5"}} {p50}')
                    lines.append(f'{key}{{quantile="0.95"}} {p95}')
                    lines.append(f'{key}{{quantile="0.99"}} {p99}')
                    lines.append(f'{key}_count {n}')
                    lines.append(f'{key}_sum {total}')

        return "\n".join(lines) + "\n"

    def get_summary(self) -> Dict:
        """Get human-readable metrics summary."""
        with self._lock:
            summary = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }
            for key, vals in self._histograms.items():
                if vals:
                    sorted_vals = sorted(vals)
                    n = len(sorted_vals)
                    summary[f"{key}_p50"] = sorted_vals[int(n * 0.50)]
                    summary[f"{key}_p95"] = sorted_vals[int(n * 0.95)]
                    summary[f"{key}_p99"] = sorted_vals[int(n * 0.99)]
                    summary[f"{key}_count"] = n
            return summary

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()


# Singleton
metrics = MetricsCollector()


# ---------------------------------------------------------------------------
# FastAPI middleware for request metrics
# ---------------------------------------------------------------------------

async def metrics_middleware(request, call_next):
    """
    ASGI middleware that captures per-request metrics.
    Tracks: latency, status codes, error rates by endpoint.
    """
    start = time.time()
    method = request.method
    path = request.url.path

    # Normalize path (collapse IDs)
    import re
    normalized = re.sub(r'/[a-f0-9-]{8,}', '/{id}', path)
    normalized = re.sub(r'/job_[a-f0-9]+', '/{job_id}', normalized)
    normalized = re.sub(r'/run_[a-f0-9_]+', '/{run_id}', normalized)

    labels = {"method": method, "endpoint": normalized}

    try:
        response = await call_next(request)
        status = response.status_code
    except Exception as e:
        status = 500
        metrics.inc_counter("http_requests_errors_total", labels)
        raise
    finally:
        duration_ms = (time.time() - start) * 1000

        labels_with_status = {**labels, "status": str(status)}
        metrics.inc_counter("http_requests_total", labels_with_status)
        metrics.observe_histogram("http_request_duration_ms", duration_ms, labels)

        if status >= 500:
            metrics.inc_counter("http_requests_errors_total", labels)
        if status == 429:
            metrics.inc_counter("rate_limit_hits_total", labels)
        if status == 401 or status == 403:
            metrics.inc_counter("auth_failures_total", labels)

        # Log structured request
        logger.info("request",
                    extra={"method": method, "path": path,
                           "status": status,
                           "duration_ms": round(duration_ms, 1),
                           "request_id": getattr(request.state, "request_id", None),
                           "tenant_id": getattr(request.state, "tenant_id", None)})

    return response


# ---------------------------------------------------------------------------
# Periodic gauge updater (queue health, DB stats)
# ---------------------------------------------------------------------------

def update_system_gauges(db_path: str):
    """Update gauge metrics from DB state. Call periodically."""
    try:
        from jobs import get_queue_metrics
        from webhooks import get_webhook_metrics

        qm = get_queue_metrics(db_path)
        metrics.set_gauge("jobs_queued", qm["queued"])
        metrics.set_gauge("jobs_running", qm["running"])
        metrics.set_gauge("jobs_dlq_size", qm["dlq"])
        metrics.set_gauge("jobs_oldest_queued_age_sec", qm["oldest_queued_age_sec"])

        wm = get_webhook_metrics(db_path)
        metrics.set_gauge("webhooks_pending", wm["pending"])
        metrics.set_gauge("webhooks_failed", wm["failed"])

    except Exception as e:
        logger.error("Gauge update failed", extra={"error": str(e)})


class GaugeUpdater:
    """Background thread that periodically updates gauges."""

    def __init__(self, db_path: str, interval: float = 30.0):
        self.db_path = db_path
        self.interval = interval
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            update_system_gauges(self.db_path)
            time.sleep(self.interval)


# ---------------------------------------------------------------------------
# SLO definitions (for alerting)
# ---------------------------------------------------------------------------

SLOS = {
    "api_error_rate": {
        "description": "API error rate (5xx) should be < 1%",
        "threshold": 0.01,
        "window_minutes": 5,
    },
    "api_latency_p95_ms": {
        "description": "API p95 latency should be < 2000ms",
        "threshold": 2000,
        "window_minutes": 5,
    },
    "job_queue_age_sec": {
        "description": "Oldest queued job should be < 300s",
        "threshold": 300,
    },
    "dlq_size": {
        "description": "DLQ should be < 10 items",
        "threshold": 10,
    },
    "webhook_failure_rate": {
        "description": "Webhook delivery failure rate < 5%",
        "threshold": 0.05,
        "window_minutes": 60,
    },
}
