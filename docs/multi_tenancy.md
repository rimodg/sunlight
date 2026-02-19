# SUNLIGHT Multi-Tenancy

## Architecture

Strict tenant isolation at two layers:

1. **Application layer**: Middleware extracts `tenant_id` from API key, injects into every DB query via `scoped_query()`. Defense-in-depth — even if RLS is misconfigured, app layer enforces isolation.

2. **Database layer (PostgreSQL)**: Row-Level Security (RLS) policies on all tenant-scoped tables. Session variable `app.tenant_id` set per request. Queries physically cannot return cross-tenant rows.

## Data Model

Every tenant-scoped table includes `tenant_id TEXT NOT NULL`:

| Table | Scoped | Description |
|-------|--------|-------------|
| `tenants` | — | Tenant registry |
| `tenant_users` | ✅ | Users per tenant |
| `contracts` | ✅ | Procurement contracts |
| `contract_scores` | ✅ | Analysis results |
| `analysis_runs` | ✅ | Pipeline runs |
| `scan_jobs` | ✅ | Async scan jobs |
| `webhook_deliveries` | ✅ | Webhook delivery logs |
| `audit_log` | ✅ | Immutable audit trail |
| `dead_letter_queue` | ✅ | Failed jobs |

## Tenant Lifecycle

```
POST /api/v2/tenants          → Create tenant
POST /api/v2/tenants/{id}/users → Add users
PATCH /api/v2/tenants/{id}     → Update settings
PATCH /api/v2/tenants/{id}/webhook → Set webhook URL
```

## Rate Limits & Quotas

| Setting | Default | Configurable |
|---------|---------|--------------|
| `rate_limit_rpm` | 60 | Yes |
| `max_concurrency` | 5 | Yes |
| `max_contracts` | 100,000 | Yes |

## Enforcement Tests

Located in `tests/test_tenancy.py`:

- `test_jobs_isolated_between_tenants` — Tenant A's jobs invisible to Tenant B
- `test_job_get_with_wrong_tenant_returns_none` — Cross-tenant job access returns null
- `test_webhook_logs_isolated` — Webhook logs scoped per tenant
- `test_contracts_cross_tenant_read_fails` — Contract data isolated
- `test_scores_cross_tenant_read_fails` — Score data isolated
- `test_all_tenant_tables_have_tenant_id` — Regression: schema audit

## PostgreSQL RLS

Applied via `migrations/004_rls.sql`:
```sql
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_contracts ON contracts
    USING (tenant_id = current_setting('app.tenant_id', true));
```

Every API request sets the session variable before any query:
```sql
SET app.tenant_id = 'ten_abc123';
```
