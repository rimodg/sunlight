-- =============================================================================
-- SUNLIGHT RLS Migration Rollback
-- =============================================================================
-- Reverses 004_rls.sql: drops policies, disables RLS, removes tenant_id columns.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1: Drop RLS policies
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS tenant_contracts ON contracts;
DROP POLICY IF EXISTS tenant_scores ON contract_scores;
DROP POLICY IF EXISTS tenant_runs ON analysis_runs;
DROP POLICY IF EXISTS tenant_audit ON audit_log;

DO $$ BEGIN
    EXECUTE 'DROP POLICY IF EXISTS tenant_jobs ON scan_jobs';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    EXECUTE 'DROP POLICY IF EXISTS tenant_webhooks ON webhook_deliveries';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Step 2: Disable RLS
-- ---------------------------------------------------------------------------

ALTER TABLE contracts DISABLE ROW LEVEL SECURITY;
ALTER TABLE contract_scores DISABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    ALTER TABLE scan_jobs DISABLE ROW LEVEL SECURITY;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE webhook_deliveries DISABLE ROW LEVEL SECURITY;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Step 3: Drop tenant_id indexes
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS idx_contracts_tenant;
DROP INDEX IF EXISTS idx_scores_tenant;
DROP INDEX IF EXISTS idx_runs_tenant;
DROP INDEX IF EXISTS idx_audit_tenant;
DROP INDEX IF EXISTS idx_jobs_tenant;
DROP INDEX IF EXISTS idx_webhooks_tenant;

-- ---------------------------------------------------------------------------
-- Step 4: Drop tenant_id columns
-- ---------------------------------------------------------------------------

ALTER TABLE contracts DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE contract_scores DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE analysis_runs DROP COLUMN IF EXISTS tenant_id;
ALTER TABLE audit_log DROP COLUMN IF EXISTS tenant_id;

DO $$ BEGIN
    ALTER TABLE scan_jobs DROP COLUMN IF EXISTS tenant_id;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE webhook_deliveries DROP COLUMN IF EXISTS tenant_id;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

COMMIT;
