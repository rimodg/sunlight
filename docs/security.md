# SUNLIGHT Security Baseline

**Version:** 2.0.0 | **Classification:** Confidential | **Last Updated:** February 2026

## 1. Authentication (AuthN)

### API Key Model
- Keys prefixed `sk_sunlight_` for safe log correlation (prefix never secret)
- 256-bit random generation via `secrets.token_hex(32)`
- Stored as SHA-256 hash — raw key never persisted, shown once at creation
- Constant-time comparison via `hmac.compare_digest` to prevent timing attacks
- Key rotation: new key generated, old key has 72-hour grace period, then revoked
- Expiration: configurable per key, enforced at auth middleware

### Key Lifecycle
```
generate → active → rotated (grace period) → revoked
                 → expired (TTL reached) → revoked
```

## 2. Authorization (AuthZ)

### RBAC Model

| Permission | Viewer | Analyst | Admin |
|------------|--------|---------|-------|
| Read scores, reports, dashboard | ✅ | ✅ | ✅ |
| Read audit logs | ✅ | ✅ | ✅ |
| Submit contracts | ❌ | ✅ | ✅ |
| Run scans | ❌ | ✅ | ✅ |
| Export case packets | ❌ | ✅ | ✅ |
| Set disposition | ❌ | ✅ | ✅ |
| Manage users & keys | ❌ | ❌ | ✅ |
| Manage tenants | ❌ | ❌ | ✅ |
| Manage webhooks | ❌ | ❌ | ✅ |
| Access DLQ | ❌ | ❌ | ✅ |

Enforced by `rbac.py` middleware. Every endpoint checks role before execution.

## 3. Data Isolation (Multi-Tenant)

### Dual-Layer Enforcement

**Layer 1 — Application:** Middleware extracts `tenant_id` from API key, injects into every database query via `scoped_query()`. No query can execute without tenant scope.

**Layer 2 — Database (PostgreSQL):** Row-Level Security (RLS) with `FORCE ROW LEVEL SECURITY`. Application role has no `BYPASSRLS` privilege. Even if application layer has a bug, database physically prevents cross-tenant reads.

```sql
ALTER TABLE contracts ENABLE ROW LEVEL SECURITY;
ALTER TABLE contracts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON contracts
    USING (tenant_id = current_setting('app.tenant_id', true));
```

### Isolation Tests
- Cross-tenant read attempts return empty results (not 403, to prevent enumeration)
- Automated regression tests in `tests/test_tenancy.py`
- Every tenant-scoped table audited for `tenant_id` column presence

## 4. Secrets Management

### Policy: Zero Secrets in Repository
- No `.env` files committed (`.gitignore` enforced)
- No hardcoded credentials in source code
- CI pipeline scans for secret patterns

### Secret Storage
| Secret | Storage | Rotation |
|--------|---------|----------|
| Database password | AWS SSM Parameter Store (SecureString) | 90 days |
| API keys | SHA-256 hash in DB, raw shown once | Per client policy |
| Webhook secrets | Per-tenant in DB, `whsec_` prefix | On tenant request |
| TLS certificates | ACM (auto-renewed) | Automatic |

### Rotation Procedure
1. Generate new credential
2. Update SSM parameter / DB record
3. Grace period for old credential (72h for API keys)
4. Revoke old credential
5. Audit log entry for rotation event

## 5. HTTP Security Headers

Applied to every response via `security_headers_middleware`:

| Header | Value | Purpose |
|--------|-------|---------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Force HTTPS |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `X-XSS-Protection` | `1; mode=block` | XSS filter |
| `Cache-Control` | `no-store` | Prevent caching of sensitive data |
| `X-Request-Id` | `{uuid}` | Request tracing |

## 6. CORS Policy

- Explicit origin allowlist (never `*` in production)
- Credentials supported for authenticated API calls
- Preflight responses cached for 1 hour
- Configurable per environment

## 7. Rate Limiting

### Per-Tenant Sliding Window
- Default: 60 requests/minute per tenant
- Configurable per tenant tier:
  - Demo: 60 RPM
  - Standard: 120 RPM
  - Enterprise: 600 RPM
- Separate stricter limits for auth/key-generation endpoints
- 429 response with `Retry-After` header

## 8. Audit Logging

### Immutable Append-Only Design
- INSERT + SELECT only — no UPDATE or DELETE on audit_log
- SHA-256 hash chain: each entry includes hash of previous entry
- Chain integrity verified on every pipeline run and nightly via cron
- Tampering detection: broken chain = immediate alert

### Required Fields on Every Entry
- `tenant_id` — which tenant
- `rulepack_version` — which detection rules were active
- `timestamp` — UTC ISO-8601
- `action` — what happened
- `entity_id` — what was affected
- `entry_hash` — cryptographic integrity

### Audited Actions
Login, API key creation/rotation/revocation, contract upload, scan submission, score view, case packet export, disposition change, tenant settings change, webhook configuration change, user creation/deactivation.

## 9. Encryption

### At Rest
- RDS: AES-256 encryption enabled (`storage_encrypted = true`)
- EBS volumes: encrypted by default
- S3 (if used): SSE-S3 or SSE-KMS
- SSM parameters: SecureString with KMS

### In Transit
- TLS 1.3 enforced on ALB (`ELBSecurityPolicy-TLS13-1-2-2021-06`)
- Database connections use SSL (`sslmode=require`)
- Internal service communication: TLS required

## 10. Incident Response

### Severity Levels
| Level | Description | Response SLA |
|-------|-------------|-------------|
| P0 | Data breach, cross-tenant leak | 15 min |
| P1 | Service down, auth bypass | 30 min |
| P2 | Degraded performance, partial outage | 2 hours |
| P3 | Minor issue, no data impact | 24 hours |

### Procedure
1. **Detect** — Alerts fire or user reports
2. **Triage** — Classify severity, assign owner
3. **Contain** — Isolate affected tenant/service, revoke compromised credentials
4. **Eradicate** — Fix root cause, deploy patch
5. **Recover** — Restore service, verify data integrity
6. **Post-Incident** — Write post-mortem, update runbook, implement preventive measures

## 11. Compliance Mapping

| Control | SOC 2 | ISO 27001 | Notes |
|---------|-------|-----------|-------|
| API key auth | CC6.1 | A.9.4.2 | SHA-256, rotation |
| RBAC | CC6.3 | A.9.2.3 | Three roles, least privilege |
| RLS isolation | CC6.1 | A.13.1.3 | DB-level enforcement |
| Audit logging | CC7.2 | A.12.4.1 | Immutable, hash-chained |
| Encryption at rest | CC6.7 | A.10.1.1 | AES-256 |
| Encryption in transit | CC6.7 | A.13.1.1 | TLS 1.3 |
| Secrets management | CC6.1 | A.10.1.2 | SSM, no repo secrets |
| Incident response | CC7.3 | A.16.1.1 | Documented, tested |
