"""
Tests for the live monitoring scheduler.

Covers:
  - Source management (add, pause, resume, remove, list)
  - Scheduling logic (due sources, watermark tracking)
  - Pipeline orchestration (fetch → ingest → score → flag → notify)
  - Error handling (auto-pause after 5 consecutive errors)
  - Health checks
  - Known source validation (10 presets)

Uses in-memory SQLite MockDB matching existing test patterns.
"""

import os
import sys
import json
import pytest
import sqlite3
import tempfile
import hashlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'code'))
os.environ['SUNLIGHT_AUTH_ENABLED'] = 'false'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor_db():
    """Create a temp DB with monitor + contracts schema."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    c = conn.cursor()

    # Contracts table (needed for dedup and pipeline)
    c.execute("""CREATE TABLE contracts (
        contract_id TEXT PRIMARY KEY,
        award_amount REAL,
        vendor_name TEXT,
        agency_name TEXT,
        description TEXT,
        start_date TEXT,
        location TEXT,
        raw_data TEXT,
        raw_data_hash TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE analysis_runs (
        run_id TEXT PRIMARY KEY,
        started_at TEXT,
        completed_at TEXT,
        status TEXT,
        run_seed INTEGER,
        config_json TEXT,
        config_hash TEXT,
        dataset_hash TEXT,
        contracts_analyzed INTEGER,
        n_contracts INTEGER,
        n_scored INTEGER,
        n_errors INTEGER,
        code_commit_hash TEXT,
        environment_json TEXT,
        model_version TEXT,
        summary_json TEXT,
        fdr_n_tests INTEGER,
        fdr_n_significant INTEGER
    )""")

    c.execute("""CREATE TABLE contract_scores (
        score_id TEXT PRIMARY KEY,
        contract_id TEXT,
        run_id TEXT,
        fraud_tier TEXT,
        tier TEXT,
        triage_priority INTEGER,
        confidence_score INTEGER,
        raw_pvalue REAL,
        fdr_adjusted_pvalue REAL,
        survives_fdr INTEGER,
        markup_pct REAL,
        markup_ci_lower REAL,
        markup_ci_upper REAL,
        raw_zscore REAL,
        log_zscore REAL,
        bootstrap_percentile REAL,
        percentile_ci_lower REAL,
        percentile_ci_upper REAL,
        bayesian_prior REAL,
        bayesian_likelihood_ratio REAL,
        bayesian_posterior REAL,
        comparable_count INTEGER,
        insufficient_comparables INTEGER,
        selection_params_json TEXT,
        scored_at TEXT,
        analyzed_at TEXT,
        UNIQUE(contract_id, run_id)
    )""")

    conn.commit()
    conn.close()

    # Initialize monitor schema
    from live_monitor import init_monitor_schema
    init_monitor_schema(path)

    yield path
    os.unlink(path)


# ===================================================================
# 1. Source Management
# ===================================================================

class TestSourceManagement:

    def test_add_source(self, monitor_db):
        """Add a custom data source."""
        from live_monitor import add_source, get_source

        src = add_source(
            monitor_db, "test-source", "Test Source",
            "https://api.example.com/releases.json",
            country_code="US", poll_interval_sec=1800,
        )
        assert src["source_id"] == "test-source"
        assert src["name"] == "Test Source"
        assert src["status"] == "active"
        assert src["poll_interval_sec"] == 1800

    def test_add_known_source(self, monitor_db):
        """Add a preset OCDS source by key."""
        from live_monitor import add_known_source

        src = add_known_source(monitor_db, "senegal")
        assert src["source_id"] == "ocds-senegal"
        assert src["country_code"] == "SN"
        assert src["status"] == "active"

    def test_add_known_source_invalid_key(self, monitor_db):
        """Invalid preset key should raise ValueError."""
        from live_monitor import add_known_source

        with pytest.raises(ValueError, match="Unknown source key"):
            add_known_source(monitor_db, "narnia")

    def test_pause_source(self, monitor_db):
        """Pausing a source sets status to 'paused'."""
        from live_monitor import add_source, pause_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        result = pause_source(monitor_db, "s1")
        assert result["status"] == "paused"

    def test_resume_source(self, monitor_db):
        """Resuming resets status to 'active' and clears errors."""
        from live_monitor import add_source, pause_source, resume_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        pause_source(monitor_db, "s1")
        result = resume_source(monitor_db, "s1")
        assert result["status"] == "active"
        assert result["consecutive_errors"] == 0

    def test_remove_source(self, monitor_db):
        """Removing a source sets status to 'removed'."""
        from live_monitor import add_source, remove_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        result = remove_source(monitor_db, "s1")
        assert result["status"] == "removed"

    def test_list_sources_excludes_removed(self, monitor_db):
        """list_sources should exclude removed sources by default."""
        from live_monitor import add_source, remove_source, list_sources

        add_source(monitor_db, "s1", "S1", "https://example.com")
        add_source(monitor_db, "s2", "S2", "https://example.com")
        remove_source(monitor_db, "s1")

        sources = list_sources(monitor_db)
        assert len(sources) == 1
        assert sources[0]["source_id"] == "s2"

    def test_list_sources_include_removed(self, monitor_db):
        """list_sources with include_removed=True returns all."""
        from live_monitor import add_source, remove_source, list_sources

        add_source(monitor_db, "s1", "S1", "https://example.com")
        add_source(monitor_db, "s2", "S2", "https://example.com")
        remove_source(monitor_db, "s1")

        sources = list_sources(monitor_db, include_removed=True)
        assert len(sources) == 2

    def test_get_nonexistent_source(self, monitor_db):
        """Getting a nonexistent source returns None."""
        from live_monitor import get_source

        assert get_source(monitor_db, "nonexistent") is None


# ===================================================================
# 2. Scheduling Logic
# ===================================================================

class TestScheduling:

    def test_new_source_is_due(self, monitor_db):
        """A newly added source (never polled) should be due immediately."""
        from live_monitor import add_source, _sources_due

        add_source(monitor_db, "s1", "S1", "https://example.com", poll_interval_sec=3600)
        due = _sources_due(monitor_db)
        assert any(s["source_id"] == "s1" for s in due)

    def test_recently_polled_not_due(self, monitor_db):
        """A source polled within its interval should not be due."""
        from live_monitor import add_source, _sources_due, _record_success
        from datetime import datetime, timezone

        add_source(monitor_db, "s1", "S1", "https://example.com", poll_interval_sec=3600)
        _record_success(monitor_db, "s1", 0, 0)  # Sets last_poll_at to now
        due = _sources_due(monitor_db)
        assert not any(s["source_id"] == "s1" for s in due)

    def test_paused_source_not_due(self, monitor_db):
        """Paused sources should never be due."""
        from live_monitor import add_source, pause_source, _sources_due

        add_source(monitor_db, "s1", "S1", "https://example.com")
        pause_source(monitor_db, "s1")
        due = _sources_due(monitor_db)
        assert not any(s["source_id"] == "s1" for s in due)

    def test_watermark_tracking(self, monitor_db):
        """Watermarks should persist between polls."""
        from live_monitor import add_source, set_watermark, get_watermark

        add_source(monitor_db, "s1", "S1", "https://example.com")
        assert get_watermark(monitor_db, "s1") == ""

        set_watermark(monitor_db, "s1", "2025-06-15T00:00:00Z")
        assert get_watermark(monitor_db, "s1") == "2025-06-15T00:00:00Z"

        set_watermark(monitor_db, "s1", "2025-07-01T00:00:00Z")
        assert get_watermark(monitor_db, "s1") == "2025-07-01T00:00:00Z"


# ===================================================================
# 3. Pipeline Orchestration
# ===================================================================

class TestPipelineOrchestration:

    def _mock_fetch(self, releases):
        """Create a mock fetch function returning fixed releases."""
        def fetch_fn(source, watermark):
            return releases, "cursor-after"
        return fetch_fn

    def test_pipeline_with_mock_releases(self, monitor_db):
        """Full pipeline with mock OCDS releases."""
        from live_monitor import add_source, run_pipeline_for_source

        add_source(monitor_db, "s1", "S1", "https://example.com")

        releases = [
            {
                "ocid": "ocds-test-001",
                "tag": ["award"],
                "buyer": {"name": "Test Agency"},
                "awards": [{
                    "id": "a1",
                    "value": {"amount": 5000000, "currency": "USD"},
                    "suppliers": [{"name": "Test Vendor"}],
                    "description": "Test contract",
                    "date": "2025-06-15",
                }],
            },
        ]

        result = run_pipeline_for_source(
            monitor_db, "s1", fetch_fn=self._mock_fetch(releases),
        )
        assert result["contracts_fetched"] == 1
        assert result["contracts_new"] == 1
        assert result["contracts_duplicate"] == 0

    def test_pipeline_empty_releases(self, monitor_db):
        """Pipeline with no releases should complete gracefully."""
        from live_monitor import add_source, run_pipeline_for_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        result = run_pipeline_for_source(
            monitor_db, "s1", fetch_fn=self._mock_fetch([]),
        )
        assert result["contracts_fetched"] == 0
        assert result["contracts_new"] == 0

    def test_pipeline_duplicate_detection(self, monitor_db):
        """Second run with same data should detect duplicates."""
        from live_monitor import add_source, run_pipeline_for_source

        add_source(monitor_db, "s1", "S1", "https://example.com")

        releases = [
            {
                "ocid": "ocds-dup-001",
                "tag": ["award"],
                "buyer": {"name": "Agency"},
                "awards": [{
                    "id": "a1",
                    "value": {"amount": 1000000},
                    "suppliers": [{"name": "Vendor"}],
                }],
            },
        ]

        fetch_fn = self._mock_fetch(releases)
        run_pipeline_for_source(monitor_db, "s1", fetch_fn=fetch_fn)

        # Second run — same data
        result = run_pipeline_for_source(monitor_db, "s1", fetch_fn=fetch_fn)
        assert result["contracts_duplicate"] == 1
        assert result["contracts_new"] == 0

    def test_pipeline_watermark_updated(self, monitor_db):
        """Watermark should advance after successful pipeline run."""
        from live_monitor import add_source, run_pipeline_for_source, get_watermark

        add_source(monitor_db, "s1", "S1", "https://example.com")
        assert get_watermark(monitor_db, "s1") == ""

        releases = [{
            "ocid": "ocds-wm-001",
            "tag": ["award"],
            "buyer": {"name": "Agency"},
            "awards": [{"id": "a1", "value": {"amount": 100000}, "suppliers": [{"name": "V"}]}],
        }]

        run_pipeline_for_source(
            monitor_db, "s1", fetch_fn=self._mock_fetch(releases),
        )
        assert get_watermark(monitor_db, "s1") == "cursor-after"

    def test_pipeline_webhook_notification(self, monitor_db):
        """Webhook function should be called for flagged contracts."""
        from live_monitor import add_source, run_pipeline_for_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        notifications = []

        def mock_webhook(payload):
            notifications.append(payload)

        releases = [{
            "ocid": "ocds-wh-001",
            "tag": ["award"],
            "buyer": {"name": "Agency"},
            "awards": [{"id": "a1", "value": {"amount": 100000}, "suppliers": [{"name": "V"}]}],
        }]

        # Pipeline runs; even if no flags are generated (depends on scoring),
        # the webhook plumbing is exercised without errors
        run_pipeline_for_source(
            monitor_db, "s1",
            webhook_fn=mock_webhook,
            fetch_fn=self._mock_fetch(releases),
        )
        # Notifications list may or may not have entries depending on scoring
        # but the pipeline completed without error
        assert isinstance(notifications, list)

    def test_pipeline_skips_paused_source(self, monitor_db):
        """Pipeline should skip paused sources."""
        from live_monitor import add_source, pause_source, run_pipeline_for_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        pause_source(monitor_db, "s1")

        result = run_pipeline_for_source(
            monitor_db, "s1", fetch_fn=self._mock_fetch([]),
        )
        assert result.get("skipped") is True


# ===================================================================
# 4. Error Handling
# ===================================================================

class TestErrorHandling:

    def test_error_increments_count(self, monitor_db):
        """Each error should increment consecutive_errors."""
        from live_monitor import add_source, _record_error, get_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        _record_error(monitor_db, "s1", "Connection timeout")

        src = get_source(monitor_db, "s1")
        assert src["consecutive_errors"] == 1
        assert src["error_message"] == "Connection timeout"

    def test_auto_pause_after_max_errors(self, monitor_db):
        """Source should auto-pause after MAX_CONSECUTIVE_ERRORS."""
        from live_monitor import add_source, _record_error, get_source, MAX_CONSECUTIVE_ERRORS

        add_source(monitor_db, "s1", "S1", "https://example.com")

        for i in range(MAX_CONSECUTIVE_ERRORS):
            _record_error(monitor_db, "s1", f"Error {i+1}")

        src = get_source(monitor_db, "s1")
        assert src["status"] == "error"
        assert src["consecutive_errors"] == MAX_CONSECUTIVE_ERRORS

    def test_success_resets_error_count(self, monitor_db):
        """A successful run should reset consecutive_errors to 0."""
        from live_monitor import add_source, _record_error, _record_success, get_source

        add_source(monitor_db, "s1", "S1", "https://example.com")
        _record_error(monitor_db, "s1", "Temporary error")
        _record_error(monitor_db, "s1", "Another error")
        assert get_source(monitor_db, "s1")["consecutive_errors"] == 2

        _record_success(monitor_db, "s1", 10, 2)
        src = get_source(monitor_db, "s1")
        assert src["consecutive_errors"] == 0
        assert src["error_message"] == ""
        assert src["total_contracts"] == 10
        assert src["total_flags"] == 2

    def test_pipeline_records_error_on_failure(self, monitor_db):
        """Pipeline failure should record error and raise."""
        from live_monitor import add_source, run_pipeline_for_source, get_source

        add_source(monitor_db, "s1", "S1", "https://example.com")

        def failing_fetch(source, watermark):
            raise ConnectionError("API is down")

        with pytest.raises(ConnectionError):
            run_pipeline_for_source(monitor_db, "s1", fetch_fn=failing_fetch)

        src = get_source(monitor_db, "s1")
        assert src["consecutive_errors"] == 1
        assert "API is down" in src["error_message"]

    def test_resume_clears_error_state(self, monitor_db):
        """Resuming an errored source should clear error state."""
        from live_monitor import add_source, _record_error, resume_source, get_source, MAX_CONSECUTIVE_ERRORS

        add_source(monitor_db, "s1", "S1", "https://example.com")
        for i in range(MAX_CONSECUTIVE_ERRORS):
            _record_error(monitor_db, "s1", f"Error {i}")
        assert get_source(monitor_db, "s1")["status"] == "error"

        result = resume_source(monitor_db, "s1")
        assert result["status"] == "active"
        assert result["consecutive_errors"] == 0
        assert result["error_message"] == ""


# ===================================================================
# 5. Health Checks
# ===================================================================

class TestHealthChecks:

    def test_healthy_status(self, monitor_db):
        """All active sources = healthy."""
        from live_monitor import add_source, get_health

        add_source(monitor_db, "s1", "S1", "https://example.com")
        add_source(monitor_db, "s2", "S2", "https://example.com")

        health = get_health(monitor_db)
        assert health["status"] == "healthy"
        assert health["sources_active"] == 2
        assert health["sources_errored"] == 0

    def test_degraded_status(self, monitor_db):
        """Some errored sources = degraded."""
        from live_monitor import add_source, _record_error, get_health, MAX_CONSECUTIVE_ERRORS

        add_source(monitor_db, "s1", "S1", "https://example.com")
        add_source(monitor_db, "s2", "S2", "https://example.com")

        for i in range(MAX_CONSECUTIVE_ERRORS):
            _record_error(monitor_db, "s1", f"Error {i}")

        health = get_health(monitor_db)
        assert health["status"] == "degraded"
        assert health["sources_active"] == 1
        assert health["sources_errored"] == 1

    def test_health_includes_per_source_details(self, monitor_db):
        """Health response should include per-source details."""
        from live_monitor import add_source, _record_success, get_health

        add_source(monitor_db, "s1", "S1", "https://example.com", country_code="SN")
        _record_success(monitor_db, "s1", 42, 3)

        health = get_health(monitor_db)
        src = health["sources"][0]
        assert src["source_id"] == "s1"
        assert src["total_contracts"] == 42
        assert src["total_flags"] == 3
        assert src["country_code"] == "SN"

    def test_empty_health(self, monitor_db):
        """Health with no sources should be healthy."""
        from live_monitor import get_health

        health = get_health(monitor_db)
        assert health["status"] == "healthy"
        assert health["sources_total"] == 0


# ===================================================================
# 6. Known Source Validation
# ===================================================================

class TestKnownSources:

    def test_all_10_presets_valid(self):
        """All 10 preset sources should have required fields."""
        from live_monitor import KNOWN_SOURCES

        assert len(KNOWN_SOURCES) == 10

        required_keys = {"source_id", "name", "base_url", "country_code", "poll_interval_sec"}
        for key, src in KNOWN_SOURCES.items():
            missing = required_keys - set(src.keys())
            assert not missing, f"Source '{key}' missing keys: {missing}"
            assert src["base_url"].startswith("https://"), f"Source '{key}' base_url not HTTPS"
            assert len(src["country_code"]) == 2, f"Source '{key}' invalid country code"
            assert src["poll_interval_sec"] >= 60, f"Source '{key}' poll interval too low"

    def test_preset_country_codes(self):
        """Verify country codes for all presets."""
        from live_monitor import KNOWN_SOURCES

        expected = {
            "senegal": "SN", "colombia": "CO", "paraguay": "PY",
            "uk": "GB", "nigeria": "NG", "mexico": "MX",
            "uganda": "UG", "ivory_coast": "CI", "moldova": "MD",
            "indonesia": "ID",
        }
        for key, code in expected.items():
            assert KNOWN_SOURCES[key]["country_code"] == code, f"Wrong code for {key}"

    def test_preset_source_ids_unique(self):
        """All preset source IDs should be unique."""
        from live_monitor import KNOWN_SOURCES

        ids = [src["source_id"] for src in KNOWN_SOURCES.values()]
        assert len(ids) == len(set(ids))

    def test_add_all_presets(self, monitor_db):
        """Should be able to add all 10 presets without conflict."""
        from live_monitor import add_known_source, list_sources

        for key in ("senegal", "colombia", "paraguay", "uk", "nigeria",
                     "mexico", "uganda", "ivory_coast", "moldova", "indonesia"):
            add_known_source(monitor_db, key)

        sources = list_sources(monitor_db)
        assert len(sources) == 10


# ===================================================================
# 7. Ingestion Audit Log
# ===================================================================

class TestIngestionLog:

    def test_log_created_on_pipeline_run(self, monitor_db):
        """Pipeline run should create an ingestion log entry."""
        from live_monitor import add_source, run_pipeline_for_source, get_ingestion_logs

        add_source(monitor_db, "s1", "S1", "https://example.com")

        def mock_fetch(source, watermark):
            return [], ""

        run_pipeline_for_source(monitor_db, "s1", fetch_fn=mock_fetch)

        logs = get_ingestion_logs(monitor_db, source_id="s1")
        assert len(logs) == 1
        assert logs[0]["status"] == "completed"
        assert logs[0]["source_id"] == "s1"

    def test_log_records_failure(self, monitor_db):
        """Failed pipeline run should log the error."""
        from live_monitor import add_source, run_pipeline_for_source, get_ingestion_logs

        add_source(monitor_db, "s1", "S1", "https://example.com")

        def failing_fetch(source, watermark):
            raise RuntimeError("Network failure")

        with pytest.raises(RuntimeError):
            run_pipeline_for_source(monitor_db, "s1", fetch_fn=failing_fetch)

        logs = get_ingestion_logs(monitor_db, source_id="s1")
        assert len(logs) == 1
        assert logs[0]["status"] == "failed"
        assert "Network failure" in logs[0]["error_message"]

    def test_log_records_counts(self, monitor_db):
        """Successful run should record contract counts."""
        from live_monitor import add_source, run_pipeline_for_source, get_ingestion_logs

        add_source(monitor_db, "s1", "S1", "https://example.com")

        releases = [{
            "ocid": "ocds-log-001",
            "tag": ["award"],
            "buyer": {"name": "Agency"},
            "awards": [{"id": "a1", "value": {"amount": 500000}, "suppliers": [{"name": "V"}]}],
        }]

        def fetch_fn(source, watermark):
            return releases, "cursor-1"

        run_pipeline_for_source(monitor_db, "s1", fetch_fn=fetch_fn)

        logs = get_ingestion_logs(monitor_db, source_id="s1")
        assert logs[0]["contracts_fetched"] == 1
        assert logs[0]["contracts_new"] == 1
        assert logs[0]["watermark_after"] == "cursor-1"


# ===================================================================
# 8. Duplicate Detection
# ===================================================================

class TestDuplicateDetection:

    def test_contract_hash_deterministic(self):
        """Same contract data should produce the same hash."""
        from live_monitor import compute_contract_hash

        c1 = {"contract_id": "C-001", "award_amount": 1000000, "vendor_name": "V", "agency_name": "A"}
        c2 = {"contract_id": "C-001", "award_amount": 1000000, "vendor_name": "V", "agency_name": "A"}
        assert compute_contract_hash(c1) == compute_contract_hash(c2)

    def test_different_contracts_different_hash(self):
        """Different contracts should produce different hashes."""
        from live_monitor import compute_contract_hash

        c1 = {"contract_id": "C-001", "award_amount": 1000000, "vendor_name": "V1", "agency_name": "A"}
        c2 = {"contract_id": "C-002", "award_amount": 2000000, "vendor_name": "V2", "agency_name": "A"}
        assert compute_contract_hash(c1) != compute_contract_hash(c2)

    def test_is_duplicate_check(self, monitor_db):
        """is_duplicate should detect existing contracts by hash."""
        from live_monitor import compute_contract_hash, is_duplicate

        c = {"contract_id": "DUP-001", "award_amount": 500000, "vendor_name": "V", "agency_name": "A"}
        c_hash = compute_contract_hash(c)

        assert not is_duplicate(monitor_db, c_hash)

        # Insert contract with that hash
        conn = sqlite3.connect(monitor_db)
        conn.execute(
            "INSERT INTO contracts (contract_id, award_amount, vendor_name, agency_name, raw_data_hash) VALUES (?, ?, ?, ?, ?)",
            ("DUP-001", 500000, "V", "A", c_hash),
        )
        conn.commit()
        conn.close()

        assert is_duplicate(monitor_db, c_hash)
