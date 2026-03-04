"""
SUNLIGHT Live Monitor — automated poll → ingest → score → flag → notify pipeline.

Polls OCDS-compliant procurement APIs on a configurable schedule, ingests new
contracts through the detection engine, triggers post-flag intelligence on
flagged results, and pushes webhook notifications.

Includes 10 preset data sources and supports daemon or single-pass mode.

Features:
  - Source management: add / pause / resume / remove
  - Watermark tracking: cursor-based pagination, picks up where it left off
  - Duplicate detection: SHA-256 hash of raw contract data
  - Auto-pause after 5 consecutive errors per source
  - Health endpoint: per-source status, last run, error counts
  - Ingestion audit log: immutable record of every run

Author: SUNLIGHT Team | v2.0.0
"""

import os
import sys
import json
import time
import uuid
import sqlite3
import hashlib
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

sys.path.insert(0, os.path.dirname(__file__))
from sunlight_logging import get_logger

logger = get_logger("live_monitor")

DB_PATH = os.environ.get(
    "SUNLIGHT_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "sunlight.db"),
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

MONITOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS data_sources (
    source_id           TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    base_url            TEXT NOT NULL,
    source_type         TEXT NOT NULL DEFAULT 'ocds',
    country_code        TEXT DEFAULT '',
    poll_interval_sec   INTEGER NOT NULL DEFAULT 3600,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'error', 'removed')),
    watermark           TEXT DEFAULT '',
    last_poll_at        TEXT,
    last_success_at     TEXT,
    consecutive_errors  INTEGER NOT NULL DEFAULT 0,
    total_contracts     INTEGER NOT NULL DEFAULT 0,
    total_flags         INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT DEFAULT '',
    config_json         TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_log (
    log_id              TEXT PRIMARY KEY,
    source_id           TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'failed')),
    contracts_fetched   INTEGER NOT NULL DEFAULT 0,
    contracts_new       INTEGER NOT NULL DEFAULT 0,
    contracts_duplicate INTEGER NOT NULL DEFAULT 0,
    contracts_scored    INTEGER NOT NULL DEFAULT 0,
    flags_generated     INTEGER NOT NULL DEFAULT 0,
    watermark_before    TEXT DEFAULT '',
    watermark_after     TEXT DEFAULT '',
    error_message       TEXT DEFAULT '',
    details_json        TEXT DEFAULT '{}'
);
"""

MAX_CONSECUTIVE_ERRORS = 5

# ---------------------------------------------------------------------------
# 10 preset OCDS data sources
# ---------------------------------------------------------------------------

KNOWN_SOURCES = {
    "senegal": {
        "source_id": "ocds-senegal",
        "name": "Senegal OCDS (ARMP)",
        "base_url": "https://api.ocds.sn/api/releases.json",
        "country_code": "SN",
        "poll_interval_sec": 3600,
    },
    "colombia": {
        "source_id": "ocds-colombia",
        "name": "Colombia OCDS (SECOP II)",
        "base_url": "https://api.colombiacompra.gov.co/releases.json",
        "country_code": "CO",
        "poll_interval_sec": 1800,
    },
    "paraguay": {
        "source_id": "ocds-paraguay",
        "name": "Paraguay OCDS (DNCP)",
        "base_url": "https://contrataciones.gov.py/datos/api/v3/doc/releases.json",
        "country_code": "PY",
        "poll_interval_sec": 3600,
    },
    "uk": {
        "source_id": "ocds-uk",
        "name": "UK Contracts Finder (OCDS)",
        "base_url": "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search",
        "country_code": "GB",
        "poll_interval_sec": 1800,
    },
    "nigeria": {
        "source_id": "ocds-nigeria",
        "name": "Nigeria OCDS (NOCOPO)",
        "base_url": "https://nocopo.bpp.gov.ng/api/ocds/releases.json",
        "country_code": "NG",
        "poll_interval_sec": 7200,
    },
    "mexico": {
        "source_id": "ocds-mexico",
        "name": "Mexico OCDS (CompraNet)",
        "base_url": "https://api.datos.gob.mx/v2/contratacionesabiertas",
        "country_code": "MX",
        "poll_interval_sec": 3600,
    },
    "uganda": {
        "source_id": "ocds-uganda",
        "name": "Uganda OCDS (PPDA/GPPD)",
        "base_url": "https://gpp.ppda.go.ug/api/ocds/releases.json",
        "country_code": "UG",
        "poll_interval_sec": 7200,
    },
    "ivory_coast": {
        "source_id": "ocds-ivory-coast",
        "name": "Côte d'Ivoire OCDS (ANRMP)",
        "base_url": "https://opendata.anrmp.ci/api/ocds/releases.json",
        "country_code": "CI",
        "poll_interval_sec": 7200,
    },
    "moldova": {
        "source_id": "ocds-moldova",
        "name": "Moldova OCDS (MTender)",
        "base_url": "https://public.api.openprocurement.org/api/2.5/tenders",
        "country_code": "MD",
        "poll_interval_sec": 3600,
    },
    "indonesia": {
        "source_id": "ocds-indonesia",
        "name": "Indonesia OCDS (LKPP/INAPROC)",
        "base_url": "https://isb-api.lkpp.go.id/api/ocds/releases.json",
        "country_code": "ID",
        "poll_interval_sec": 3600,
    },
}


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

def init_monitor_schema(db_path: str = DB_PATH):
    """Create the data_sources and ingestion_log tables if they don't exist."""
    conn = sqlite3.connect(db_path)
    conn.executescript(MONITOR_SCHEMA_SQL)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Source management
# ---------------------------------------------------------------------------

def add_source(
    db_path: str,
    source_id: str,
    name: str,
    base_url: str,
    country_code: str = "",
    poll_interval_sec: int = 3600,
    config: Optional[dict] = None,
) -> dict:
    """Add a new data source for monitoring."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """INSERT INTO data_sources
               (source_id, name, base_url, country_code, poll_interval_sec,
                status, config_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (source_id, name, base_url, country_code, poll_interval_sec,
             json.dumps(config or {}), now, now),
        )
        conn.commit()
        return get_source(db_path, source_id)
    finally:
        conn.close()


def add_known_source(db_path: str, key: str) -> dict:
    """Add one of the 10 preset OCDS data sources by key.

    Valid keys: senegal, colombia, paraguay, uk, nigeria, mexico,
    uganda, ivory_coast, moldova, indonesia
    """
    if key not in KNOWN_SOURCES:
        raise ValueError(
            f"Unknown source key '{key}'. Valid keys: {', '.join(sorted(KNOWN_SOURCES))}"
        )
    src = KNOWN_SOURCES[key]
    return add_source(
        db_path=db_path,
        source_id=src["source_id"],
        name=src["name"],
        base_url=src["base_url"],
        country_code=src["country_code"],
        poll_interval_sec=src["poll_interval_sec"],
    )


def get_source(db_path: str, source_id: str) -> Optional[dict]:
    """Get a single data source by ID."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM data_sources WHERE source_id = ?", (source_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_sources(db_path: str, include_removed: bool = False) -> list:
    """List all data sources."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if include_removed:
        rows = conn.execute("SELECT * FROM data_sources ORDER BY created_at").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM data_sources WHERE status != 'removed' ORDER BY created_at"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pause_source(db_path: str, source_id: str) -> dict:
    """Pause a data source (stops polling)."""
    return _update_source_status(db_path, source_id, "paused")


def resume_source(db_path: str, source_id: str) -> dict:
    """Resume a paused or errored source."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """UPDATE data_sources
           SET status = 'active', consecutive_errors = 0, error_message = '', updated_at = ?
           WHERE source_id = ?""",
        (now, source_id),
    )
    conn.commit()
    conn.close()
    return get_source(db_path, source_id)


def remove_source(db_path: str, source_id: str) -> dict:
    """Soft-remove a data source."""
    return _update_source_status(db_path, source_id, "removed")


def _update_source_status(db_path: str, source_id: str, status: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE data_sources SET status = ?, updated_at = ? WHERE source_id = ?",
        (status, now, source_id),
    )
    conn.commit()
    conn.close()
    return get_source(db_path, source_id)


# ---------------------------------------------------------------------------
# Watermark / cursor tracking
# ---------------------------------------------------------------------------

def get_watermark(db_path: str, source_id: str) -> str:
    """Get the current watermark (pagination cursor) for a source."""
    src = get_source(db_path, source_id)
    return src.get("watermark", "") if src else ""


def set_watermark(db_path: str, source_id: str, watermark: str):
    """Update the watermark after a successful fetch."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE data_sources SET watermark = ?, updated_at = ? WHERE source_id = ?",
        (watermark, now, source_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def compute_contract_hash(contract: dict) -> str:
    """SHA-256 of normalized contract data for dedup."""
    key_fields = {
        "contract_id": contract.get("contract_id", ""),
        "award_amount": str(contract.get("award_amount", "")),
        "vendor_name": contract.get("vendor_name", ""),
        "agency_name": contract.get("agency_name", ""),
    }
    raw = json.dumps(key_fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def is_duplicate(db_path: str, contract_hash: str) -> bool:
    """Check if a contract with this hash already exists."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT 1 FROM contracts WHERE raw_data_hash = ? LIMIT 1", (contract_hash,)
    ).fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# Ingestion audit log
# ---------------------------------------------------------------------------

def _start_ingestion_log(db_path: str, source_id: str, watermark_before: str) -> str:
    """Create an ingestion log entry at the start of a run."""
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO ingestion_log
           (log_id, source_id, started_at, status, watermark_before)
           VALUES (?, ?, ?, 'running', ?)""",
        (log_id, source_id, now, watermark_before),
    )
    conn.commit()
    conn.close()
    return log_id


def _complete_ingestion_log(
    db_path: str,
    log_id: str,
    status: str,
    contracts_fetched: int = 0,
    contracts_new: int = 0,
    contracts_duplicate: int = 0,
    contracts_scored: int = 0,
    flags_generated: int = 0,
    watermark_after: str = "",
    error_message: str = "",
):
    """Finalize an ingestion log entry."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """UPDATE ingestion_log
           SET completed_at = ?, status = ?,
               contracts_fetched = ?, contracts_new = ?, contracts_duplicate = ?,
               contracts_scored = ?, flags_generated = ?,
               watermark_after = ?, error_message = ?
           WHERE log_id = ?""",
        (now, status, contracts_fetched, contracts_new, contracts_duplicate,
         contracts_scored, flags_generated, watermark_after, error_message, log_id),
    )
    conn.commit()
    conn.close()


def get_ingestion_logs(db_path: str, source_id: Optional[str] = None, limit: int = 50) -> list:
    """Get recent ingestion log entries."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if source_id:
        rows = conn.execute(
            "SELECT * FROM ingestion_log WHERE source_id = ? ORDER BY started_at DESC LIMIT ?",
            (source_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ingestion_log ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Error tracking + auto-pause
# ---------------------------------------------------------------------------

def _record_error(db_path: str, source_id: str, error_msg: str):
    """Increment consecutive error count; auto-pause after MAX_CONSECUTIVE_ERRORS."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """UPDATE data_sources
           SET consecutive_errors = consecutive_errors + 1,
               error_message = ?, last_poll_at = ?, updated_at = ?
           WHERE source_id = ?""",
        (error_msg, now, now, source_id),
    )
    conn.commit()

    # Check if we should auto-pause
    row = conn.execute(
        "SELECT consecutive_errors FROM data_sources WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    if row and row[0] >= MAX_CONSECUTIVE_ERRORS:
        conn.execute(
            "UPDATE data_sources SET status = 'error', updated_at = ? WHERE source_id = ?",
            (now, source_id),
        )
        conn.commit()
        logger.warning(
            f"Source {source_id} auto-paused after {MAX_CONSECUTIVE_ERRORS} consecutive errors"
        )
    conn.close()


def _record_success(db_path: str, source_id: str, new_contracts: int, new_flags: int):
    """Reset error count and update success metrics."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        """UPDATE data_sources
           SET consecutive_errors = 0, error_message = '',
               last_poll_at = ?, last_success_at = ?,
               total_contracts = total_contracts + ?,
               total_flags = total_flags + ?,
               updated_at = ?
           WHERE source_id = ?""",
        (now, now, new_contracts, new_flags, now, source_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Pipeline: fetch → ingest → score → flag → notify
# ---------------------------------------------------------------------------

def _fetch_releases(source: dict, watermark: str) -> tuple:
    """Fetch OCDS releases from a source, starting after watermark.

    Returns (releases_list, next_watermark).
    """
    from external_data import RESTConnector, RateLimitConfig

    connector = RESTConnector(
        base_url=source["base_url"],
        rate_config=RateLimitConfig(requests_per_second=2.0, retry_max=3, timeout=30.0),
    )

    params = {}
    if watermark:
        params["since"] = watermark
        params["cursor"] = watermark

    try:
        result = connector.get("", params=params)
        releases = result.get("releases", [])
        # Extract next watermark from response
        next_cursor = (
            result.get("links", {}).get("next", "")
            or result.get("next", "")
            or result.get("offset", "")
        )
        if not next_cursor and releases:
            # Use latest release date as watermark
            for r in reversed(releases):
                dt = r.get("date") or r.get("publishedDate")
                if dt:
                    next_cursor = dt
                    break
        return releases, next_cursor or watermark
    finally:
        connector.close()


def _ingest_contracts(db_path: str, contracts: list) -> tuple:
    """Insert new contracts into the database, skipping duplicates.

    Returns (new_count, duplicate_count).
    """
    new_count = 0
    dup_count = 0
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()

    for c in contracts:
        c_hash = compute_contract_hash(c)
        existing = conn.execute(
            "SELECT 1 FROM contracts WHERE raw_data_hash = ? OR contract_id = ? LIMIT 1",
            (c_hash, c.get("contract_id", "")),
        ).fetchone()

        if existing:
            dup_count += 1
            continue

        conn.execute(
            """INSERT OR IGNORE INTO contracts
               (contract_id, award_amount, vendor_name, agency_name, description,
                start_date, raw_data_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                c.get("contract_id", str(uuid.uuid4())),
                c.get("award_amount", 0),
                c.get("vendor_name", ""),
                c.get("agency_name", ""),
                c.get("description", ""),
                c.get("start_date"),
                c_hash,
            ),
        )
        new_count += 1

    conn.commit()
    conn.close()
    return new_count, dup_count


def _score_contracts(db_path: str, contract_ids: list, calibration_profile: str = "doj_federal") -> list:
    """Score a batch of contracts through the detection engine.

    Returns list of dicts with contract_id, fraud_tier, confidence_score.
    """
    if not contract_ids:
        return []

    try:
        from institutional_pipeline import InstitutionalPipeline
        pipeline = InstitutionalPipeline(db_path)
        results = pipeline.run(
            calibration_profile=calibration_profile,
            limit=len(contract_ids),
            verbose=False,
        )
        return results.get("scored", []) if isinstance(results, dict) else []
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return []


def _trigger_post_flag(db_path: str, flagged_contracts: list):
    """Run post-flag intelligence on flagged contracts."""
    if not flagged_contracts:
        return

    try:
        from case_builder import build_case_package
        from vendor_intelligence import build_vendor_profile

        for fc in flagged_contracts:
            cid = fc.get("contract_id")
            if not cid:
                continue
            build_case_package(db_path, cid)
    except Exception as e:
        logger.error(f"Post-flag intelligence error: {e}")


def _send_notifications(
    db_path: str,
    source_id: str,
    flagged_contracts: list,
    webhook_fn: Optional[Callable] = None,
):
    """Push webhook notifications for newly flagged contracts."""
    if not flagged_contracts:
        return

    if webhook_fn:
        for fc in flagged_contracts:
            try:
                webhook_fn({
                    "event": "contract.flagged",
                    "source_id": source_id,
                    "contract_id": fc.get("contract_id"),
                    "fraud_tier": fc.get("fraud_tier"),
                    "confidence_score": fc.get("confidence_score"),
                })
            except Exception as e:
                logger.error(f"Webhook notification error: {e}")


def run_pipeline_for_source(
    db_path: str,
    source_id: str,
    webhook_fn: Optional[Callable] = None,
    fetch_fn: Optional[Callable] = None,
) -> dict:
    """Execute the full pipeline for a single data source.

    Pipeline steps:
      1. Fetch OCDS releases (with cursor pagination)
      2. Transform via OCDS adapter
      3. Ingest new contracts (dedup)
      4. Score through detection engine
      5. Trigger post-flag intelligence on RED/YELLOW
      6. Push webhook notifications
      7. Update watermark

    Args:
        db_path: Database path.
        source_id: The data source to process.
        webhook_fn: Optional callback for webhook delivery.
        fetch_fn: Optional override for release fetching (for testing).

    Returns:
        Summary dict with counts.
    """
    source = get_source(db_path, source_id)
    if not source:
        raise ValueError(f"Source not found: {source_id}")
    if source["status"] not in ("active",):
        return {"skipped": True, "reason": f"Source status is '{source['status']}'"}

    watermark = source.get("watermark", "")
    log_id = _start_ingestion_log(db_path, source_id, watermark)

    try:
        # Step 1: Fetch
        if fetch_fn:
            releases, new_watermark = fetch_fn(source, watermark)
        else:
            releases, new_watermark = _fetch_releases(source, watermark)

        if not releases:
            _complete_ingestion_log(db_path, log_id, "completed", watermark_after=watermark)
            _record_success(db_path, source_id, 0, 0)
            return {"contracts_fetched": 0, "contracts_new": 0, "flags": 0}

        # Step 2: Transform via OCDS adapter
        from ocds_adapter import transform_releases
        contracts = transform_releases(releases, validate=True)
        contract_dicts = [c.to_dict() for c in contracts]

        # Step 3: Ingest (dedup)
        new_count, dup_count = _ingest_contracts(db_path, contract_dicts)

        # Step 4: Score
        new_ids = [c["contract_id"] for c in contract_dicts[:new_count]]
        scored = _score_contracts(db_path, new_ids)

        # Step 5: Identify flags
        flagged = [s for s in scored if s.get("fraud_tier") in ("RED", "YELLOW")]

        # Step 6: Post-flag intelligence
        _trigger_post_flag(db_path, flagged)

        # Step 7: Webhook notifications
        _send_notifications(db_path, source_id, flagged, webhook_fn)

        # Step 8: Update watermark
        set_watermark(db_path, source_id, new_watermark)

        # Record success
        _record_success(db_path, source_id, new_count, len(flagged))
        _complete_ingestion_log(
            db_path, log_id, "completed",
            contracts_fetched=len(contract_dicts),
            contracts_new=new_count,
            contracts_duplicate=dup_count,
            contracts_scored=len(scored),
            flags_generated=len(flagged),
            watermark_after=new_watermark,
        )

        summary = {
            "contracts_fetched": len(contract_dicts),
            "contracts_new": new_count,
            "contracts_duplicate": dup_count,
            "contracts_scored": len(scored),
            "flags": len(flagged),
            "watermark": new_watermark,
        }
        logger.info(f"Source {source_id}: {summary}")
        return summary

    except Exception as e:
        error_msg = str(e)
        _record_error(db_path, source_id, error_msg)
        _complete_ingestion_log(db_path, log_id, "failed", error_message=error_msg)
        logger.error(f"Pipeline error for {source_id}: {error_msg}")
        raise


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

def get_health(db_path: str) -> dict:
    """Get overall monitoring health status.

    Returns per-source status, last run times, error counts.
    """
    sources = list_sources(db_path)
    source_health = []
    for s in sources:
        source_health.append({
            "source_id": s["source_id"],
            "name": s["name"],
            "status": s["status"],
            "country_code": s["country_code"],
            "last_poll_at": s.get("last_poll_at"),
            "last_success_at": s.get("last_success_at"),
            "consecutive_errors": s["consecutive_errors"],
            "total_contracts": s["total_contracts"],
            "total_flags": s["total_flags"],
            "error_message": s.get("error_message", ""),
        })

    active = sum(1 for s in source_health if s["status"] == "active")
    errored = sum(1 for s in source_health if s["status"] == "error")
    paused = sum(1 for s in source_health if s["status"] == "paused")

    return {
        "status": "healthy" if errored == 0 else "degraded" if active > 0 else "unhealthy",
        "sources_active": active,
        "sources_paused": paused,
        "sources_errored": errored,
        "sources_total": len(source_health),
        "sources": source_health,
    }


# ---------------------------------------------------------------------------
# Scheduler: daemon + single-pass modes
# ---------------------------------------------------------------------------

def _sources_due(db_path: str) -> list:
    """Find active sources whose poll interval has elapsed."""
    sources = list_sources(db_path)
    now = datetime.now(timezone.utc)
    due = []
    for s in sources:
        if s["status"] != "active":
            continue
        last_poll = s.get("last_poll_at")
        if not last_poll:
            due.append(s)
            continue
        try:
            last_dt = datetime.fromisoformat(last_poll)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            interval = timedelta(seconds=s.get("poll_interval_sec", 3600))
            if now >= last_dt + interval:
                due.append(s)
        except (ValueError, TypeError):
            due.append(s)
    return due


def run_single_pass(
    db_path: str = DB_PATH,
    webhook_fn: Optional[Callable] = None,
    fetch_fn: Optional[Callable] = None,
) -> dict:
    """Run a single polling pass across all due sources.

    Returns summary of results per source.
    """
    init_monitor_schema(db_path)
    due_sources = _sources_due(db_path)

    results = {}
    for source in due_sources:
        sid = source["source_id"]
        try:
            results[sid] = run_pipeline_for_source(db_path, sid, webhook_fn, fetch_fn)
        except Exception as e:
            results[sid] = {"error": str(e)}

    return results


class MonitorDaemon:
    """Background daemon that polls sources on their configured intervals."""

    def __init__(
        self,
        db_path: str = DB_PATH,
        webhook_fn: Optional[Callable] = None,
        fetch_fn: Optional[Callable] = None,
        tick_interval: int = 60,
    ):
        self.db_path = db_path
        self.webhook_fn = webhook_fn
        self.fetch_fn = fetch_fn
        self.tick_interval = tick_interval
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Start the daemon in a background thread."""
        init_monitor_schema(self.db_path)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Monitor daemon started")

    def stop(self):
        """Signal the daemon to stop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Monitor daemon stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                run_single_pass(self.db_path, self.webhook_fn, self.fetch_fn)
            except Exception as e:
                logger.error(f"Daemon tick error: {e}")
            self._stop_event.wait(self.tick_interval)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SUNLIGHT Live Monitor")
    sub = parser.add_subparsers(dest="command")

    # Single pass
    sub.add_parser("run", help="Run a single polling pass")

    # Daemon mode
    daemon_p = sub.add_parser("daemon", help="Run as daemon")
    daemon_p.add_argument("--tick", type=int, default=60, help="Tick interval (seconds)")

    # Source management
    add_p = sub.add_parser("add-source", help="Add a preset source")
    add_p.add_argument("key", choices=sorted(KNOWN_SOURCES.keys()))

    sub.add_parser("list-sources", help="List all sources")

    pause_p = sub.add_parser("pause", help="Pause a source")
    pause_p.add_argument("source_id")

    resume_p = sub.add_parser("resume", help="Resume a source")
    resume_p.add_argument("source_id")

    remove_p = sub.add_parser("remove", help="Remove a source")
    remove_p.add_argument("source_id")

    sub.add_parser("health", help="Show health status")

    args = parser.parse_args()

    if args.command == "run":
        results = run_single_pass()
        print(json.dumps(results, indent=2))
    elif args.command == "daemon":
        daemon = MonitorDaemon(tick_interval=args.tick)
        daemon.start()
        try:
            while daemon.running:
                time.sleep(1)
        except KeyboardInterrupt:
            daemon.stop()
    elif args.command == "add-source":
        src = add_known_source(DB_PATH, args.key)
        print(f"Added: {src['name']} ({src['source_id']})")
    elif args.command == "list-sources":
        for s in list_sources(DB_PATH):
            print(f"  [{s['status']:>7}] {s['source_id']}: {s['name']}")
    elif args.command == "pause":
        pause_source(DB_PATH, args.source_id)
        print(f"Paused: {args.source_id}")
    elif args.command == "resume":
        resume_source(DB_PATH, args.source_id)
        print(f"Resumed: {args.source_id}")
    elif args.command == "remove":
        remove_source(DB_PATH, args.source_id)
        print(f"Removed: {args.source_id}")
    elif args.command == "health":
        health = get_health(DB_PATH)
        print(json.dumps(health, indent=2))
    else:
        parser.print_help()
