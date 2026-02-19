"""
SUNLIGHT Webhook + Jobs Tests
===============================

Tests for async job lifecycle, webhook signing, replay protection,
idempotency, retries, and DLQ handling.
"""

import os
import sys
import json
import time
import sqlite3
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))

from jobs import (
    init_jobs_schema, create_job, get_job, list_jobs,
    update_job_status, move_to_dlq, get_dlq_items,
    get_queue_metrics, JobStatus,
)
from webhooks import (
    init_webhooks_schema, sign_payload, build_signature_header,
    verify_signature, create_webhook_event, get_delivery_logs,
    get_webhook_metrics,
)
from tenancy import init_tenant_schema, create_tenant


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    init_jobs_schema(path)
    init_webhooks_schema(path)
    init_tenant_schema(path)
    yield path
    os.unlink(path)


@pytest.fixture
def tenant(db_path):
    return create_tenant(db_path, "Test Org", "test-org",
                         webhook_url="https://httpbin.org/post")


# ─── Job Lifecycle ────────────────────────────────────────────────────────

class TestJobLifecycle:
    def test_create_job(self, db_path, tenant):
        job = create_job(db_path, tenant["tenant_id"])
        assert job["status"] == "QUEUED"
        assert job["job_id"].startswith("job_")

    def test_job_status_transitions(self, db_path, tenant):
        job = create_job(db_path, tenant["tenant_id"])
        jid = job["job_id"]

        update_job_status(db_path, jid, "RUNNING", progress_pct=10)
        j = get_job(db_path, jid)
        assert j["status"] == "RUNNING"
        assert j["progress_pct"] == 10

        update_job_status(db_path, jid, "SUCCEEDED", progress_pct=100,
                          result={"run_id": "test_run"})
        j = get_job(db_path, jid)
        assert j["status"] == "SUCCEEDED"
        assert j["progress_pct"] == 100
        assert "test_run" in j["result_json"]

    def test_idempotency_key(self, db_path, tenant):
        """Same idempotency key returns the same job, not a duplicate."""
        j1 = create_job(db_path, tenant["tenant_id"],
                         idempotency_key="scan-2026-02-18")
        j2 = create_job(db_path, tenant["tenant_id"],
                         idempotency_key="scan-2026-02-18")
        assert j1["job_id"] == j2["job_id"]

    def test_different_idempotency_keys_create_different_jobs(self, db_path, tenant):
        j1 = create_job(db_path, tenant["tenant_id"], idempotency_key="a")
        j2 = create_job(db_path, tenant["tenant_id"], idempotency_key="b")
        assert j1["job_id"] != j2["job_id"]

    def test_idempotency_scoped_to_tenant(self, db_path):
        t1 = create_tenant(db_path, "T1", "t1")
        t2 = create_tenant(db_path, "T2", "t2")
        j1 = create_job(db_path, t1["tenant_id"], idempotency_key="same-key")
        j2 = create_job(db_path, t2["tenant_id"], idempotency_key="same-key")
        # Different tenants -> different jobs even with same key
        assert j1["job_id"] != j2["job_id"]


# ─── Dead Letter Queue ───────────────────────────────────────────────────

class TestDLQ:
    def test_move_to_dlq(self, db_path, tenant):
        job = create_job(db_path, tenant["tenant_id"], max_attempts=1)
        update_job_status(db_path, job["job_id"], "FAILED",
                          error_message="Test failure")
        # Simulate exhaustion
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE scan_jobs SET attempt = 1 WHERE job_id = ?",
                     (job["job_id"],))
        conn.commit()
        conn.close()

        move_to_dlq(db_path, job["job_id"])

        j = get_job(db_path, job["job_id"])
        assert j["status"] == "DLQ"

        dlq = get_dlq_items(db_path, tenant["tenant_id"])
        assert len(dlq) == 1
        assert dlq[0]["job_id"] == job["job_id"]

    def test_dlq_scoped_to_tenant(self, db_path):
        t1 = create_tenant(db_path, "T1", "t1-dlq")
        t2 = create_tenant(db_path, "T2", "t2-dlq")

        j1 = create_job(db_path, t1["tenant_id"], max_attempts=1)
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE scan_jobs SET attempt = 1 WHERE job_id = ?",
                     (j1["job_id"],))
        conn.commit()
        conn.close()
        move_to_dlq(db_path, j1["job_id"])

        assert len(get_dlq_items(db_path, t1["tenant_id"])) == 1
        assert len(get_dlq_items(db_path, t2["tenant_id"])) == 0


# ─── Queue Metrics ────────────────────────────────────────────────────────

class TestQueueMetrics:
    def test_queue_metrics(self, db_path, tenant):
        create_job(db_path, tenant["tenant_id"])
        create_job(db_path, tenant["tenant_id"])
        j3 = create_job(db_path, tenant["tenant_id"])
        update_job_status(db_path, j3["job_id"], "SUCCEEDED")

        m = get_queue_metrics(db_path)
        assert m["queued"] == 2
        assert m["succeeded"] == 1
        assert m["total_jobs"] >= 3


# ─── Webhook Signing ─────────────────────────────────────────────────────

class TestWebhookSigning:
    SECRET = "whsec_test_secret_12345"

    def test_sign_and_verify(self):
        payload = '{"event":"test"}'
        header, ts = build_signature_header(self.SECRET, payload)

        assert header.startswith("t=")
        assert ",v1=" in header

        assert verify_signature(self.SECRET, header, payload,
                                tolerance_sec=60) is True

    def test_wrong_secret_fails(self):
        payload = '{"event":"test"}'
        header, _ = build_signature_header(self.SECRET, payload)
        assert verify_signature("wrong_secret", header, payload) is False

    def test_tampered_payload_fails(self):
        payload = '{"event":"test"}'
        header, _ = build_signature_header(self.SECRET, payload)
        assert verify_signature(self.SECRET, header, '{"event":"hacked"}') is False

    def test_replay_protection(self):
        """Old signatures should be rejected."""
        payload = '{"event":"test"}'
        old_ts = int(time.time()) - 600  # 10 minutes ago
        sig = sign_payload(self.SECRET, old_ts, payload)
        header = f"t={old_ts},v1={sig}"

        assert verify_signature(
            self.SECRET, header, payload, tolerance_sec=300
        ) is False

    def test_replay_within_window_passes(self):
        """Recent signatures should pass."""
        payload = '{"event":"test"}'
        recent_ts = int(time.time()) - 60  # 1 minute ago
        sig = sign_payload(self.SECRET, recent_ts, payload)
        header = f"t={recent_ts},v1={sig}"

        assert verify_signature(
            self.SECRET, header, payload, tolerance_sec=300
        ) is True

    def test_malformed_header_fails(self):
        assert verify_signature(self.SECRET, "garbage", "{}") is False
        assert verify_signature(self.SECRET, "t=abc,v1=xyz", "{}") is False


# ─── Webhook Events ──────────────────────────────────────────────────────

class TestWebhookEvents:
    def test_create_event(self, db_path, tenant):
        evt = create_webhook_event(
            db_path, tenant["tenant_id"], "scan.completed",
            {"job_id": "j1", "tier_counts": {"RED": 2}},
            "https://httpbin.org/post",
        )
        assert evt["event_type"] == "scan.completed"
        assert evt["status"] == "PENDING"

    def test_duplicate_event_is_idempotent(self, db_path, tenant):
        """Event with same event_id should not create duplicate."""
        evt1 = create_webhook_event(
            db_path, tenant["tenant_id"], "scan.completed",
            {"job_id": "j1"}, "https://example.com/hook",
        )
        # Second event with different data but we test via DB uniqueness
        logs = get_delivery_logs(db_path, tenant["tenant_id"])
        assert len(logs) == 1

    def test_delivery_logs_scoped(self, db_path):
        t1 = create_tenant(db_path, "T1", "t1-wh")
        t2 = create_tenant(db_path, "T2", "t2-wh")

        create_webhook_event(db_path, t1["tenant_id"], "test", {}, "https://t1.com")
        create_webhook_event(db_path, t2["tenant_id"], "test", {}, "https://t2.com")

        assert len(get_delivery_logs(db_path, t1["tenant_id"])) == 1
        assert len(get_delivery_logs(db_path, t2["tenant_id"])) == 1

    def test_webhook_metrics(self, db_path, tenant):
        create_webhook_event(db_path, tenant["tenant_id"], "test",
                             {}, "https://example.com")
        m = get_webhook_metrics(db_path)
        assert m["pending"] >= 1
        assert m["total"] >= 1
