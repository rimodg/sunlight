"""
SUNLIGHT Webhook Delivery System
==================================

Signed webhook payloads with HMAC, replay protection, retries,
and delivery logging visible in admin UI.

Signature scheme: HMAC-SHA256(webhook_secret, timestamp + "." + payload)
Header: X-Sunlight-Signature: t=<unix_ts>,v1=<hex_signature>
Replay protection: reject events older than 5 minutes

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import json
import uuid
import time
import hmac
import hashlib
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Callable
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("webhooks")

REPLAY_TOLERANCE_SEC = 300  # 5 minutes
MAX_DELIVERY_ATTEMPTS = 5
BACKOFF_BASE = 2.0  # seconds
BACKOFF_MAX = 300.0

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

WEBHOOKS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id     TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    event_id        TEXT NOT NULL UNIQUE,
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    webhook_url     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',
    attempt         INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,
    last_status_code INTEGER,
    last_error      TEXT,
    next_retry_at   TEXT,
    created_at      TEXT NOT NULL,
    delivered_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_webhook_tenant ON webhook_deliveries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_webhook_status ON webhook_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_webhook_event ON webhook_deliveries(event_id);
"""


def init_webhooks_schema(db_path: str):
    """Create webhook delivery tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(WEBHOOKS_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Webhooks schema initialized")


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def sign_payload(secret: str, timestamp: int, payload: str) -> str:
    """
    Create HMAC-SHA256 signature.
    Signature = HMAC(secret, f"{timestamp}.{payload}")
    """
    msg = f"{timestamp}.{payload}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return sig


def build_signature_header(secret: str, payload: str) -> tuple:
    """
    Build the signature header value and timestamp.
    Returns: (header_value, timestamp)
    """
    ts = int(time.time())
    sig = sign_payload(secret, ts, payload)
    header = f"t={ts},v1={sig}"
    return header, ts


def verify_signature(
    secret: str, header: str, payload: str,
    tolerance_sec: int = REPLAY_TOLERANCE_SEC,
) -> bool:
    """
    Verify webhook signature and check replay protection.
    Returns True if valid and within tolerance window.
    """
    try:
        parts = {}
        for element in header.split(","):
            key, value = element.split("=", 1)
            parts[key] = value

        ts = int(parts["t"])
        expected_sig = parts["v1"]
    except (KeyError, ValueError):
        return False

    # Replay protection
    now = int(time.time())
    if abs(now - ts) > tolerance_sec:
        logger.warning("Webhook replay rejected",
                       extra={"timestamp": ts, "now": now,
                              "age_sec": abs(now - ts)})
        return False

    # Signature check
    computed = sign_payload(secret, ts, payload)
    return hmac.compare_digest(computed, expected_sig)


# ---------------------------------------------------------------------------
# Event creation
# ---------------------------------------------------------------------------

def create_webhook_event(
    db_path: str,
    tenant_id: str,
    event_type: str,
    data: Dict,
    webhook_url: str,
) -> Dict:
    """
    Create a webhook event for delivery.
    event_id provides idempotency — duplicate events are skipped.
    """
    event_id = f"evt_{uuid.uuid4().hex[:20]}"
    delivery_id = f"del_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
        "timestamp": now,
        "data": data,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """INSERT INTO webhook_deliveries
               (delivery_id, tenant_id, event_id, event_type,
                payload_json, webhook_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (delivery_id, tenant_id, event_id, event_type,
             payload_json, webhook_url, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Duplicate event_id — idempotent
        conn.close()
        logger.info("Duplicate webhook event skipped",
                    extra={"event_id": event_id})
        return {"event_id": event_id, "status": "duplicate"}
    conn.close()

    logger.info("Webhook event created",
                extra={"event_id": event_id, "event_type": event_type,
                       "tenant_id": tenant_id})

    return {
        "delivery_id": delivery_id,
        "event_id": event_id,
        "event_type": event_type,
        "status": "PENDING",
    }


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def deliver_webhook(
    db_path: str, delivery_id: str, webhook_secret: str,
) -> bool:
    """
    Attempt to deliver a webhook. Returns True if successful.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM webhook_deliveries WHERE delivery_id = ?",
        (delivery_id,),
    ).fetchone()
    conn.close()

    if not row:
        logger.error("Delivery not found", extra={"delivery_id": delivery_id})
        return False

    delivery = dict(row)
    url = delivery["webhook_url"]
    payload = delivery["payload_json"]

    # Sign the payload
    sig_header, _ = build_signature_header(webhook_secret, payload)

    # Attempt delivery
    try:
        req = Request(
            url,
            data=payload.encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Sunlight-Signature": sig_header,
                "X-Sunlight-Event": delivery["event_type"],
                "X-Sunlight-Event-Id": delivery["event_id"],
                "User-Agent": "SUNLIGHT-Webhooks/2.0",
            },
            method="POST",
        )

        with urlopen(req, timeout=30) as resp:
            status_code = resp.status

        success = 200 <= status_code < 300
        _update_delivery(db_path, delivery_id, success, status_code)
        return success

    except HTTPError as e:
        _update_delivery(db_path, delivery_id, False, e.code, str(e))
        return False
    except (URLError, OSError) as e:
        _update_delivery(db_path, delivery_id, False, error=str(e))
        return False


def _update_delivery(
    db_path: str, delivery_id: str, success: bool,
    status_code: Optional[int] = None, error: Optional[str] = None,
):
    """Update delivery record after attempt."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)

    if success:
        conn.execute(
            """UPDATE webhook_deliveries
               SET status = 'DELIVERED', attempt = attempt + 1,
                   last_status_code = ?, delivered_at = ?
               WHERE delivery_id = ?""",
            (status_code, now, delivery_id),
        )
    else:
        # Check attempts
        row = conn.execute(
            "SELECT attempt, max_attempts FROM webhook_deliveries WHERE delivery_id = ?",
            (delivery_id,),
        ).fetchone()

        new_attempt = (row[0] if row else 0) + 1
        max_att = row[1] if row else MAX_DELIVERY_ATTEMPTS

        if new_attempt >= max_att:
            new_status = "FAILED"
        else:
            new_status = "PENDING"
            delay = min(BACKOFF_BASE * (2 ** new_attempt), BACKOFF_MAX)
            retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            conn.execute(
                "UPDATE webhook_deliveries SET next_retry_at = ? WHERE delivery_id = ?",
                (retry_at, delivery_id),
            )

        conn.execute(
            """UPDATE webhook_deliveries
               SET status = ?, attempt = ?,
                   last_status_code = ?, last_error = ?
               WHERE delivery_id = ?""",
            (new_status, new_attempt, status_code, error, delivery_id),
        )

    conn.commit()
    conn.close()

    logger.info("Webhook delivery attempt",
                extra={"delivery_id": delivery_id, "success": success,
                       "status_code": status_code})


# ---------------------------------------------------------------------------
# Delivery worker
# ---------------------------------------------------------------------------

class WebhookWorker:
    """Background worker that processes pending webhook deliveries."""

    def __init__(self, db_path: str, poll_interval: float = 5.0):
        self.db_path = db_path
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Webhook worker started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)

    def _loop(self):
        while self._running:
            try:
                self.process_pending()
            except Exception as e:
                logger.error("Webhook worker error", extra={"error": str(e)})
            time.sleep(self.poll_interval)

    def process_pending(self) -> int:
        """Process all pending deliveries. Returns count processed."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()

        rows = conn.execute(
            """SELECT d.delivery_id, t.webhook_secret
               FROM webhook_deliveries d
               JOIN tenants t ON d.tenant_id = t.tenant_id
               WHERE d.status = 'PENDING'
               AND (d.next_retry_at IS NULL OR d.next_retry_at <= ?)
               AND d.attempt < d.max_attempts
               ORDER BY d.created_at ASC LIMIT 50""",
            (now,),
        ).fetchall()
        conn.close()

        count = 0
        for row in rows:
            deliver_webhook(self.db_path, row["delivery_id"], row["webhook_secret"])
            count += 1

        return count


# ---------------------------------------------------------------------------
# Delivery logs (for admin UI)
# ---------------------------------------------------------------------------

def get_delivery_logs(
    db_path: str, tenant_id: str, limit: int = 50,
) -> List[Dict]:
    """Get webhook delivery logs for a tenant."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT delivery_id, tenant_id, event_id, event_type, status,
                  attempt, max_attempts, last_status_code, last_error,
                  created_at, delivered_at
           FROM webhook_deliveries
           WHERE tenant_id = ?
           ORDER BY created_at DESC LIMIT ?""",
        (tenant_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_webhook_metrics(db_path: str) -> Dict:
    """Webhook delivery health metrics."""
    conn = sqlite3.connect(db_path)
    status_counts = {}
    for row in conn.execute(
        "SELECT status, COUNT(*) as cnt FROM webhook_deliveries GROUP BY status"
    ).fetchall():
        status_counts[row[0]] = row[1]

    failed = conn.execute(
        "SELECT COUNT(*) FROM webhook_deliveries WHERE status = 'FAILED'"
    ).fetchone()[0]
    conn.close()

    return {
        "pending": status_counts.get("PENDING", 0),
        "delivered": status_counts.get("DELIVERED", 0),
        "failed": failed,
        "total": sum(status_counts.values()),
    }
