-- ============================================================================
-- Migration 004: Post-Flag Intelligence Layer
-- ============================================================================
-- Adds tables for vendor profiling, case evidence packaging, investigation
-- triage queue, and vendor network analysis.
--
-- Depends on: 001_schema.sql (contracts, contract_scores, analysis_runs)
-- Author: SUNLIGHT Team
-- Date: 2026-03-03
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. vendor_profiles — cached vendor risk assessments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_profiles (
    vendor_id           TEXT            PRIMARY KEY,
    risk_score          NUMERIC(5,1)    NOT NULL DEFAULT 0 CHECK (risk_score >= 0 AND risk_score <= 100),
    contract_count      INTEGER         NOT NULL DEFAULT 0,
    total_awards        NUMERIC(18,2)   NOT NULL DEFAULT 0,
    average_value       NUMERIC(18,2)   NOT NULL DEFAULT 0,
    sole_source_rate    NUMERIC(5,4)    NOT NULL DEFAULT 0 CHECK (sole_source_rate >= 0 AND sole_source_rate <= 1),
    concentration_score NUMERIC(5,4)    NOT NULL DEFAULT 0 CHECK (concentration_score >= 0 AND concentration_score <= 1),
    top_agency          TEXT            DEFAULT '',
    top_agency_pct      NUMERIC(5,4)    DEFAULT 0,
    red_count           INTEGER         NOT NULL DEFAULT 0,
    yellow_count        INTEGER         NOT NULL DEFAULT 0,
    risk_factors        JSONB           DEFAULT '[]',
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vendor_profiles_risk ON vendor_profiles (risk_score DESC);
CREATE INDEX idx_vendor_profiles_updated ON vendor_profiles (updated_at);


-- ---------------------------------------------------------------------------
-- 2. case_packages — generated evidence packages for flagged contracts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS case_packages (
    id                  SERIAL          PRIMARY KEY,
    contract_id         TEXT            NOT NULL REFERENCES contracts(contract_id),
    run_id              TEXT            REFERENCES analysis_runs(run_id),
    generated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    fraud_tier          TEXT            CHECK (fraud_tier IN ('RED', 'YELLOW', 'GREEN', 'GRAY')),
    confidence_score    NUMERIC(5,1)    DEFAULT 0,
    signals_json        JSONB           NOT NULL DEFAULT '[]',
    peer_stats_json     JSONB           NOT NULL DEFAULT '{}',
    vendor_summary_json JSONB           DEFAULT '{}',
    markup_analysis_json JSONB          DEFAULT '{}',
    markdown_summary    TEXT            DEFAULT '',
    recommendation      TEXT            DEFAULT '',
    exported_at         TIMESTAMPTZ
);

CREATE INDEX idx_case_packages_contract ON case_packages (contract_id);
CREATE INDEX idx_case_packages_tier ON case_packages (fraud_tier);
CREATE INDEX idx_case_packages_generated ON case_packages (generated_at DESC);


-- ---------------------------------------------------------------------------
-- 3. investigation_queue — prioritized triage queue
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investigation_queue (
    id                  SERIAL          PRIMARY KEY,
    contract_id         TEXT            NOT NULL REFERENCES contracts(contract_id),
    run_id              TEXT            REFERENCES analysis_runs(run_id),
    priority_score      NUMERIC(10,2)   NOT NULL DEFAULT 0,
    expected_fraud_value NUMERIC(18,2)  DEFAULT 0,
    data_completeness   NUMERIC(5,4)    DEFAULT 0,
    complexity_estimate TEXT            CHECK (complexity_estimate IN ('low', 'medium', 'high')) DEFAULT 'medium',
    recommended_action  TEXT            DEFAULT '',
    assigned_to         TEXT,
    status              TEXT            NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending', 'assigned', 'in_review', 'completed', 'dismissed')),
    notes               TEXT            DEFAULT '',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_investigation_queue_priority ON investigation_queue (priority_score DESC);
CREATE INDEX idx_investigation_queue_status ON investigation_queue (status);
CREATE INDEX idx_investigation_queue_contract ON investigation_queue (contract_id);
CREATE INDEX idx_investigation_queue_assigned ON investigation_queue (assigned_to) WHERE assigned_to IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 4. vendor_network_edges — collusion detection graph edges
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_network_edges (
    id                  SERIAL          PRIMARY KEY,
    vendor_a            TEXT            NOT NULL,
    vendor_b            TEXT            NOT NULL,
    edge_type           TEXT            NOT NULL CHECK (edge_type IN ('shared_agency', 'bid_rotation', 'temporal_cluster')),
    confidence_score    NUMERIC(5,4)    NOT NULL DEFAULT 0 CHECK (confidence_score >= 0 AND confidence_score <= 1),
    evidence_json       JSONB           DEFAULT '{}',
    detected_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (vendor_a, vendor_b, edge_type)
);

CREATE INDEX idx_vendor_network_vendor_a ON vendor_network_edges (vendor_a);
CREATE INDEX idx_vendor_network_vendor_b ON vendor_network_edges (vendor_b);
CREATE INDEX idx_vendor_network_type ON vendor_network_edges (edge_type);
CREATE INDEX idx_vendor_network_confidence ON vendor_network_edges (confidence_score DESC);


-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE 'Migration 004_post_flag_intelligence: all tables created successfully.';
END $$;

COMMIT;
