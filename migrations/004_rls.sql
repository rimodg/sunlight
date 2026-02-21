-- =============================================================================
-- SUNLIGHT PostgreSQL Row-Level Security Migration
-- =============================================================================
-- Version: 1.1.0
-- Date: 2026-02-21
-- Depends on: 001_schema.sql
-- Target: PostgreSQL 16+
--
-- Adds tenant_id columns to all tenant-scoped tables and enables RLS
-- so each tenant can only see their own data via current_setting('app.tenant_id').
--
-- Rollback: migrations/004_rls_rollback.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1: Add tenant_id columns
-- ---------------------------------------------------------------------------

ALTER TABLE contracts
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';

ALTER TABLE contract_scores
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';

ALTER TABLE analysis_runs
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';

ALTER TABLE audit_log
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';

-- scan_jobs and webhook_deliveries may already have tenant_id from v2 schema
DO $$ BEGIN
    ALTER TABLE scan_jobs
        ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'scan_jobs table does not exist yet — skipping';
END $$;

DO $$ BEGIN
    ALTER TABLE webhook_deliveries
        ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'ten_demo';
EXCEPTION WHEN undefined_table THEN
    RAISE NOTICE 'webhook_deliveries table does not exist yet — skipping';
END $$;

-- ---------------------------------------------------------------------------
-- Step 2: Create indexes on tenant_id
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_contracts_tenant ON contracts (tenant_id);
CREATE INDEX IF NOT EXISTS idx_scores_tenant ON contract_scores (tenant_id);
CREATE INDEX IF NOT EXISTS idx_runs_tenant ON analysis_runs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log (tenant_id);

DO $$ BEGIN
    CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON scan_jobs (tenant_id);
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    CREATE INDEX IF NOT EXISTS idx_webhooks_tenant ON webhook_deliveries (tenant_id);
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Step 3: Enable Row-Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts FORCE ROW LEVEL SECURITY;

ALTER TABLE contract_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_scores FORCE ROW LEVEL SECURITY;

ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs FORCE ROW LEVEL SECURITY;

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    ALTER TABLE scan_jobs ENABLE ROW LEVEL SECURITY;
    ALTER TABLE scan_jobs FORCE ROW LEVEL SECURITY;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;
    ALTER TABLE webhook_deliveries FORCE ROW LEVEL SECURITY;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Step 4: Create RLS policies
-- ---------------------------------------------------------------------------
-- Policies use current_setting('app.tenant_id', true) which returns NULL
-- if the setting is not set (the 'true' param means don't error).
-- Superusers bypass RLS by default.

CREATE POLICY tenant_contracts ON contracts
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_scores ON contract_scores
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_runs ON analysis_runs
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_audit ON audit_log
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DO $$ BEGIN
    EXECUTE 'CREATE POLICY tenant_jobs ON scan_jobs
        FOR ALL
        USING (tenant_id = current_setting(''app.tenant_id'', true))
        WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))';
EXCEPTION WHEN undefined_table THEN NULL;
         WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    EXECUTE 'CREATE POLICY tenant_webhooks ON webhook_deliveries
        FOR ALL
        USING (tenant_id = current_setting(''app.tenant_id'', true))
        WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))';
EXCEPTION WHEN undefined_table THEN NULL;
         WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Step 5: Verify
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    -- Verify RLS is enabled on core tables
    ASSERT (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'contracts'),
        'RLS not forced on contracts';
    ASSERT (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'contract_scores'),
        'RLS not forced on contract_scores';
    ASSERT (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'analysis_runs'),
        'RLS not forced on analysis_runs';
    ASSERT (SELECT relforcerowsecurity FROM pg_class WHERE relname = 'audit_log'),
        'RLS not forced on audit_log';

    RAISE NOTICE 'RLS migration verified successfully';
END $$;

COMMIT;
