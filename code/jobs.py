"""
SUNLIGHT Async Job System
===========================

Job-based scanning with background execution, retries, idempotency,
and dead-letter queue handling.

Job lifecycle: QUEUED -> RUNNING -> SUCCEEDED | FAILED -> (DLQ if exhausted)

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import json
import uuid
import time
import hashlib
import sqlite3
import threading
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Callable
from collections import defaultdict
from enum import Enum

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("jobs")

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

JOBS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_jobs (
    job_id          TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    idempotency_key TEXT,
    status          TEXT NOT NULL DEFAULT 'QUEUED',
    job_type        TEXT NOT NULL DEFAULT 'batch_scan',
    input_json      TEXT NOT NULL DEFAULT '{}',
    result_json     TEXT,
    progress_pct    INTEGER NOT NULL DEFAULT 0,
    progress_msg    TEXT,
    attempt         INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    error_message   TEXT,
    error_trace     TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    completed_at    TEXT,
    next_retry_at   TEXT,
    worker_id       TEXT,
    UNIQUE(tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON scan_jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON scan_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON scan_jobs(created_at);

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    dlq_id      TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL,
    tenant_id   TEXT NOT NULL,
    job_type    TEXT NOT NULL,
    input_json  TEXT NOT NULL,
    error_message TEXT,
    error_trace TEXT,
    attempts    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    original_created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dlq_tenant ON dead_letter_queue(tenant_id);
"""


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DLQ = "DLQ"
    CANCELLED = "CANCELLED"


def init_jobs_schema(db_path: str):
    """Create job tables."""
    conn = sqlite3.connect(db_path)
    conn.executescript(JOBS_SCHEMA_SQL)
    conn.commit()
    conn.close()
    logger.info("Jobs schema initialized")


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

def create_job(
    db_path: str,
    tenant_id: str,
    job_type: str = "batch_scan",
    input_data: Optional[Dict] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 3,
) -> Dict:
    """
    Submit a new job. If idempotency_key matches existing job for tenant,
    returns the existing job instead of creating a duplicate.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Idempotency check
    if idempotency_key:
        existing = conn.execute(
            "SELECT * FROM scan_jobs WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        ).fetchone()
        if existing:
            conn.close()
            logger.info("Idempotent job returned",
                        extra={"job_id": existing["job_id"],
                               "idempotency_key": idempotency_key})
            return dict(existing)

    job_id = f"job_{uuid.uuid4().hex[:16]}"
    input_json = json.dumps(input_data or {})

    conn.execute(
        """INSERT INTO scan_jobs
           (job_id, tenant_id, idempotency_key, status, job_type,
            input_json, max_attempts, created_at)
           VALUES (?, ?, ?, 'QUEUED', ?, ?, ?, ?)""",
        (job_id, tenant_id, idempotency_key, job_type, input_json,
         max_attempts, now),
    )
    conn.commit()
    conn.close()

    logger.info("Job created",
                extra={"job_id": job_id, "tenant_id": tenant_id,
                       "job_type": job_type})

    return {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "status": "QUEUED",
        "job_type": job_type,
        "progress_pct": 0,
        "created_at": now,
    }


def get_job(db_path: str, job_id: str, tenant_id: Optional[str] = None) -> Optional[Dict]:
    """Get job by ID, optionally scoped to tenant."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if tenant_id:
        row = conn.execute(
            "SELECT * FROM scan_jobs WHERE job_id = ? AND tenant_id = ?",
            (job_id, tenant_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM scan_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_jobs(
    db_path: str, tenant_id: str, status: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> List[Dict]:
    """List jobs for a tenant."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM scan_jobs WHERE tenant_id = ?"
    params: list = [tenant_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_job_status(
    db_path: str, job_id: str, status: str,
    progress_pct: Optional[int] = None,
    progress_msg: Optional[str] = None,
    result: Optional[Dict] = None,
    error_message: Optional[str] = None,
    error_trace: Optional[str] = None,
    worker_id: Optional[str] = None,
):
    """Update job status and optional fields."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)

    sets = ["status = ?"]
    vals: list = [status]

    if progress_pct is not None:
        sets.append("progress_pct = ?")
        vals.append(progress_pct)
    if progress_msg is not None:
        sets.append("progress_msg = ?")
        vals.append(progress_msg)
    if result is not None:
        sets.append("result_json = ?")
        vals.append(json.dumps(result))
    if error_message is not None:
        sets.append("error_message = ?")
        vals.append(error_message)
    if error_trace is not None:
        sets.append("error_trace = ?")
        vals.append(error_trace)
    if worker_id is not None:
        sets.append("worker_id = ?")
        vals.append(worker_id)

    if status == "RUNNING":
        sets.append("started_at = ?")
        vals.append(now)
    elif status in ("SUCCEEDED", "FAILED", "DLQ"):
        sets.append("completed_at = ?")
        vals.append(now)

    vals.append(job_id)
    conn.execute(f"UPDATE scan_jobs SET {', '.join(sets)} WHERE job_id = ?", vals)
    conn.commit()
    conn.close()

    logger.info("Job status updated",
                extra={"job_id": job_id, "status": status,
                       "progress_pct": progress_pct})


def move_to_dlq(db_path: str, job_id: str):
    """Move exhausted job to dead-letter queue."""
    job = get_job(db_path, job_id)
    if not job:
        return

    dlq_id = f"dlq_{uuid.uuid4().hex[:16]}"
    now = datetime.now(timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO dead_letter_queue
           (dlq_id, job_id, tenant_id, job_type, input_json,
            error_message, error_trace, attempts, created_at, original_created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (dlq_id, job_id, job["tenant_id"], job["job_type"],
         job["input_json"], job.get("error_message"),
         job.get("error_trace"), job["attempt"],
         now, job["created_at"]),
    )
    conn.execute(
        "UPDATE scan_jobs SET status = 'DLQ' WHERE job_id = ?", (job_id,)
    )
    conn.commit()
    conn.close()

    logger.warning("Job moved to DLQ",
                   extra={"job_id": job_id, "dlq_id": dlq_id,
                          "attempts": job["attempt"]})


def get_dlq_items(db_path: str, tenant_id: Optional[str] = None) -> List[Dict]:
    """List dead-letter queue items."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if tenant_id:
        rows = conn.execute(
            "SELECT * FROM dead_letter_queue WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM dead_letter_queue ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class ScanWorker:
    """
    Background worker that processes scan jobs from the queue.
    Supports retries with exponential backoff.

    Usage:
        worker = ScanWorker(db_path, pipeline_fn)
        worker.start()  # Starts background thread
        worker.stop()   # Graceful shutdown
    """

    def __init__(
        self,
        db_path: str,
        pipeline_fn: Callable,
        worker_id: Optional[str] = None,
        poll_interval: float = 2.0,
        backoff_base: float = 5.0,
        backoff_max: float = 300.0,
    ):
        self.db_path = db_path
        self.pipeline_fn = pipeline_fn
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.poll_interval = poll_interval
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the worker in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Worker started", extra={"worker_id": self.worker_id})

    def stop(self):
        """Stop the worker gracefully."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=30)
        logger.info("Worker stopped", extra={"worker_id": self.worker_id})

    def _loop(self):
        """Main polling loop."""
        while self._running:
            try:
                job = self._claim_next_job()
                if job:
                    self._execute(job)
                else:
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error("Worker loop error",
                             extra={"worker_id": self.worker_id,
                                    "error": str(e)})
                time.sleep(self.poll_interval)

    def _claim_next_job(self) -> Optional[Dict]:
        """Atomically claim the next QUEUED job."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        now = datetime.now(timezone.utc).isoformat()

        # Get next eligible job (QUEUED, or FAILED with retry time passed)
        row = conn.execute(
            """SELECT * FROM scan_jobs
               WHERE status IN ('QUEUED', 'FAILED')
               AND (next_retry_at IS NULL OR next_retry_at <= ?)
               AND attempt < max_attempts
               ORDER BY created_at ASC LIMIT 1""",
            (now,),
        ).fetchone()

        if not row:
            conn.close()
            return None

        job = dict(row)
        # Claim it
        conn.execute(
            """UPDATE scan_jobs
               SET status = 'RUNNING', worker_id = ?,
                   started_at = ?, attempt = attempt + 1
               WHERE job_id = ? AND status IN ('QUEUED', 'FAILED')""",
            (self.worker_id, now, job["job_id"]),
        )
        conn.commit()
        conn.close()

        logger.info("Job claimed",
                     extra={"job_id": job["job_id"],
                            "worker_id": self.worker_id,
                            "attempt": job["attempt"] + 1})
        return job

    def _execute(self, job: Dict):
        """Execute a single job with error handling."""
        job_id = job["job_id"]
        try:
            input_data = json.loads(job.get("input_json", "{}"))

            # Progress callback
            def on_progress(pct: int, msg: str = ""):
                update_job_status(self.db_path, job_id, "RUNNING",
                                  progress_pct=pct, progress_msg=msg)

            # Execute the pipeline
            result = self.pipeline_fn(
                db_path=self.db_path,
                tenant_id=job["tenant_id"],
                input_data=input_data,
                progress_callback=on_progress,
            )

            update_job_status(
                self.db_path, job_id, "SUCCEEDED",
                progress_pct=100,
                progress_msg="Scan complete",
                result=result,
            )

            logger.info("Job succeeded",
                        extra={"job_id": job_id, "tenant_id": job["tenant_id"]})

        except Exception as e:
            attempt = job["attempt"] + 1
            max_attempts = job["max_attempts"]

            logger.error("Job failed",
                         extra={"job_id": job_id, "attempt": attempt,
                                "max_attempts": max_attempts, "error": str(e)})

            if attempt >= max_attempts:
                # Exhausted retries -> DLQ
                update_job_status(
                    self.db_path, job_id, "FAILED",
                    error_message=str(e),
                    error_trace=traceback.format_exc(),
                )
                move_to_dlq(self.db_path, job_id)
            else:
                # Schedule retry with exponential backoff
                delay = min(
                    self.backoff_base * (2 ** (attempt - 1)),
                    self.backoff_max,
                )
                retry_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat()

                update_job_status(
                    self.db_path, job_id, "FAILED",
                    error_message=str(e),
                    error_trace=traceback.format_exc(),
                )
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    "UPDATE scan_jobs SET next_retry_at = ? WHERE job_id = ?",
                    (retry_at, job_id),
                )
                conn.commit()
                conn.close()

    def process_one(self) -> bool:
        """Process a single job synchronously. Returns True if a job was processed."""
        job = self._claim_next_job()
        if job:
            self._execute(job)
            return True
        return False


# ---------------------------------------------------------------------------
# Pipeline function adapter
# ---------------------------------------------------------------------------

def run_scan_pipeline(
    db_path: str,
    tenant_id: str,
    input_data: Dict,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Execute SUNLIGHT scan pipeline for a tenant's data.
    This is the function the worker calls.
    """
    from institutional_pipeline import InstitutionalPipeline

    limit = input_data.get("limit")
    seed = input_data.get("seed", 42)
    config = input_data.get("config", {})

    if progress_callback:
        progress_callback(5, "Loading contracts")

    pipeline = InstitutionalPipeline(db_path)

    if progress_callback:
        progress_callback(10, "Starting analysis")

    result = pipeline.run(run_seed=seed, config=config, limit=limit, verbose=False)

    if progress_callback:
        progress_callback(100, "Complete")

    return {
        "run_id": result["run_id"],
        "n_scored": result["n_scored"],
        "tier_counts": result["tier_counts"],
        "elapsed_sec": result.get("pass1_time", 0),
    }


# ---------------------------------------------------------------------------
# Queue metrics (for observability)
# ---------------------------------------------------------------------------

def get_queue_metrics(db_path: str) -> Dict:
    """Get job queue health metrics."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    status_counts = {}
    for row in conn.execute(
        "SELECT status, COUNT(*) as cnt FROM scan_jobs GROUP BY status"
    ).fetchall():
        status_counts[row["status"]] = row["cnt"]

    # Oldest queued job age
    oldest = conn.execute(
        "SELECT MIN(created_at) as oldest FROM scan_jobs WHERE status = 'QUEUED'"
    ).fetchone()
    oldest_age_sec = 0
    if oldest and oldest["oldest"]:
        created = datetime.fromisoformat(oldest["oldest"])
        oldest_age_sec = (datetime.now(timezone.utc) - created).total_seconds()

    # DLQ size
    dlq_size = conn.execute(
        "SELECT COUNT(*) as cnt FROM dead_letter_queue"
    ).fetchone()["cnt"]

    conn.close()

    return {
        "queued": status_counts.get("QUEUED", 0),
        "running": status_counts.get("RUNNING", 0),
        "succeeded": status_counts.get("SUCCEEDED", 0),
        "failed": status_counts.get("FAILED", 0),
        "dlq": dlq_size,
        "oldest_queued_age_sec": round(oldest_age_sec, 1),
        "total_jobs": sum(status_counts.values()),
    }


# ---------------------------------------------------------------------------
# CLI entrypoint: python -m jobs --worker
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import signal

    parser = argparse.ArgumentParser(description="SUNLIGHT Job Worker")
    parser.add_argument("--worker", action="store_true", help="Run as background worker")
    parser.add_argument("--db", default=None, help="Database path")
    parser.add_argument("--poll", type=float, default=2.0, help="Poll interval (seconds)")
    args = parser.parse_args()

    if not args.worker:
        parser.print_help()
        sys.exit(0)

    db_path = args.db or os.environ.get(
        "SUNLIGHT_DB_PATH",
        os.path.join(os.path.dirname(__file__), "..", "data", "sunlight.db"),
    )

    logger.info("Starting webhook worker", extra={"db_path": db_path})

    init_jobs_schema(db_path)

    worker = ScanWorker(
        db_path=db_path,
        pipeline_fn=run_scan_pipeline,
        poll_interval=args.poll,
    )

    # Graceful shutdown on SIGTERM/SIGINT
    def shutdown(sig, frame):
        logger.info("Shutting down worker")
        worker.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    worker.start()

    # Keep main thread alive
    import threading
    stop_event = threading.Event()
    stop_event.wait()
