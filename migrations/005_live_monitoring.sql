-- ============================================================================
-- Migration 005: Live Monitoring Infrastructure
-- ============================================================================
-- Creates tables for automated OCDS polling, contract ingestion tracking,
-- and watermark-based cursor pagination.
--
-- Depends on: 001_schema.sql (contracts)
-- Author: SUNLIGHT Team
-- Date: 2026-03-04
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. data_sources — configured OCDS endpoints + watermark state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_sources (
    source_id           TEXT            PRIMARY KEY,
    name                TEXT            NOT NULL,
    base_url            TEXT            NOT NULL,
    source_type         TEXT            NOT NULL DEFAULT 'ocds',
    country_code        CHAR(2)         DEFAULT '',
    poll_interval_sec   INTEGER         NOT NULL DEFAULT 3600
                                        CHECK (poll_interval_sec >= 60),
    status              TEXT            NOT NULL DEFAULT 'active'
                                        CHECK (status IN ('active', 'paused', 'error', 'removed')),
    watermark           TEXT            DEFAULT '',
    last_poll_at        TIMESTAMPTZ,
    last_success_at     TIMESTAMPTZ,
    consecutive_errors  INTEGER         NOT NULL DEFAULT 0,
    total_contracts     INTEGER         NOT NULL DEFAULT 0,
    total_flags         INTEGER         NOT NULL DEFAULT 0,
    error_message       TEXT            DEFAULT '',
    config_json         JSONB           DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_data_sources_status ON data_sources (status);
CREATE INDEX idx_data_sources_country ON data_sources (country_code);
CREATE INDEX idx_data_sources_next_poll ON data_sources (last_poll_at, poll_interval_sec)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 2. ingestion_log — immutable audit trail of every ingestion run
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_log (
    log_id              TEXT            PRIMARY KEY,
    source_id           TEXT            NOT NULL REFERENCES data_sources(source_id),
    started_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              TEXT            NOT NULL DEFAULT 'running'
                                        CHECK (status IN ('running', 'completed', 'failed')),
    contracts_fetched   INTEGER         NOT NULL DEFAULT 0,
    contracts_new       INTEGER         NOT NULL DEFAULT 0,
    contracts_duplicate INTEGER         NOT NULL DEFAULT 0,
    contracts_scored    INTEGER         NOT NULL DEFAULT 0,
    flags_generated     INTEGER         NOT NULL DEFAULT 0,
    watermark_before    TEXT            DEFAULT '',
    watermark_after     TEXT            DEFAULT '',
    error_message       TEXT            DEFAULT '',
    details_json        JSONB           DEFAULT '{}'
);

CREATE INDEX idx_ingestion_log_source ON ingestion_log (source_id, started_at DESC);
CREATE INDEX idx_ingestion_log_status ON ingestion_log (status);
CREATE INDEX idx_ingestion_log_started ON ingestion_log (started_at DESC);

-- ---------------------------------------------------------------------------
-- Row-Level Security comments (apply after 004_rls.sql pattern)
-- ---------------------------------------------------------------------------
-- If multi-tenant RLS is enabled, add policies:
--
--   ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY data_sources_tenant_isolation ON data_sources
--       USING (source_id IN (
--           SELECT source_id FROM tenant_data_sources
--           WHERE tenant_id = current_setting('app.current_tenant')
--       ));
--
--   ALTER TABLE ingestion_log ENABLE ROW LEVEL SECURITY;
--   CREATE POLICY ingestion_log_tenant_isolation ON ingestion_log
--       USING (source_id IN (
--           SELECT source_id FROM tenant_data_sources
--           WHERE tenant_id = current_setting('app.current_tenant')
--       ));

-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE 'Migration 005_live_monitoring: tables created successfully.';
END $$;

COMMIT;
