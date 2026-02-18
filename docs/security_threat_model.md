# SUNLIGHT Security Threat Model

**Date:** 2026-02-18
**Framework:** OWASP Top 10 (2021) + API Security Top 10 (2023)
**Scope:** All API endpoints, data storage, authentication, input processing

---

## 1. Threat Surface Summary

| Component | Exposure | Controls |
|---|---|---|
| REST API (FastAPI) | Internet-facing | API key auth, rate limiting, input validation, CORS |
| SQLite Database | Local file | No network exposure, parameterized queries |
| File Ingestion | Accepts uploads | Format validation, 50MB size limit, sandboxed parsing |
| Admin Endpoints | API-gated | Admin scope required, separate key management |

---

## 2. OWASP Top 10 Mapping

### A01:2021 — Broken Access Control

| Control | Status | Evidence |
|---|---|---|
| API key required on all endpoints | Implemented | `auth.py:require_api_key_dynamic()` — middleware dependency on every route |
| Scope-based access (read/analyze/admin) | Implemented | `api.py:_require_admin()` checks scope string |
| Admin endpoints protected | Implemented | All `/admin/*` routes check for `admin` scope |
| Key revocation | Implemented | `DELETE /admin/keys/{id}` immediately invalidates |
| Auth bypass for dev only | Implemented | `SUNLIGHT_AUTH_ENABLED=false` env var, disabled in production |

**Residual risk:** Scope model is coarse (3 scopes). No per-resource ACL. Acceptable for current deployment model.

### A02:2021 — Cryptographic Failures

| Control | Status | Evidence |
|---|---|---|
| API keys hashed (SHA-256) | Implemented | `auth.py` — plaintext never stored, only hash |
| Key format: `sk_sunlight_<64 hex>` | Implemented | Sufficient entropy (256 bits) |
| Audit chain hash integrity | Implemented | SHA-256 hash chain, verified on health check |
| No hardcoded credentials | Verified | `.env` for secrets, `.env` in `.gitignore` |

**Residual risk:** SHA-256 for key hashing (not bcrypt/argon2). Acceptable because keys are high-entropy random, not user-chosen passwords.

### A03:2021 — Injection

| Vector | Status | Evidence |
|---|---|---|
| SQL injection — API endpoints | No known vectors | All API queries use `?` parameterized placeholders. Manual review of `api.py`, `dashboard.py`, `auth.py`, `ingestion.py` |
| SQL injection — `update_job()` | Fixed | `_ALLOWED_JOB_COLUMNS` frozenset allowlist validates column names before SQL construction (`ingestion.py`) |
| SQL injection — internal scripts | Low risk | `dashboard.py:get_system_health()` uses hardcoded table names in f-strings. `institutional_pipeline.py` uses hardcoded column names. No user input reaches these paths |
| Command injection | N/A | No shell execution in application code |
| XSS | N/A | API returns JSON only, no HTML rendering |

**Automated test evidence:** `tests/test_api.py` exercises all endpoints with various inputs. No SQL injection test failures.

**Manual review checklist:**

- [x] `api.py`: All 24 endpoints use `?` placeholders for user-supplied values
- [x] `dashboard.py`: f-string SQL uses hardcoded table/column names only
- [x] `ingestion.py`: `update_job()` has column allowlist; `insert_contracts()` uses parameterized inserts
- [x] `auth.py`: Key lookup uses `?` placeholder for hashed key comparison
- [x] `institutional_pipeline.py`: `_load_contracts()`, `_persist_scores()` use `?` placeholders
- [x] `detection_report.py`: All queries use `?` placeholders

**Conclusion:** No known injection paths found in automated tests + manual review. This is documented evidence, not a guarantee — new code must maintain parameterized query discipline.

### A04:2021 — Insecure Design

| Control | Status |
|---|---|
| Statistical methods documented and reproducible | Yes — `DOJProsecutionThresholds`, deterministic seeds |
| Every detection is explainable | Yes — reasoning array, legal citations |
| No black-box scoring | Yes — all thresholds traceable to DOJ precedent |
| Audit trail is tamper-evident | Yes — SHA-256 hash chain |

### A05:2021 — Security Misconfiguration

| Control | Status | Evidence |
|---|---|---|
| CORS configurable | Implemented | `SUNLIGHT_CORS_ORIGINS` env var; defaults to `*` (dev only) |
| Debug mode off in production | Default | FastAPI debug disabled by default |
| Default credentials documented | Yes | `.env.example` warns to change `changeme` password |
| Unnecessary endpoints disabled | N/A | All endpoints serve a documented purpose |

### A06:2021 — Vulnerable Components

| Finding | Severity | Status |
|---|---|---|
| pip 25.2: CVE-2025-8869, CVE-2026-1703 | Medium | Build tool only, not runtime. Update recommended |
| fastapi, uvicorn, numpy, pydantic, httpx | None | Zero known CVEs as of 2026-02-18 |

**Evidence:** `pip-audit` run on 2026-02-18. Full results in `reports/security_audit.md`.

### A07:2021 — Identification and Authentication Failures

| Control | Status |
|---|---|
| API key authentication on all endpoints | Implemented |
| Rate limiting (sliding window, per-key) | Implemented |
| Key rotation without downtime | Implemented |
| Usage tracking per request | Implemented |
| No default keys shipped | Verified |

### A08:2021 — Software and Data Integrity Failures

| Control | Status | Evidence |
|---|---|---|
| Cryptographic audit trail | Implemented | Hash chain verified on every `/health` call |
| Dataset hash per analysis run | Implemented | `compute_dataset_hash()` in pipeline |
| Config hash per analysis run | Implemented | `compute_config_hash()` in pipeline |
| Code commit hash recorded per run | Implemented | `_code_hash()` in pipeline |
| Rulepack version recorded per score | Implemented | `governance.py:RULEPACK_REGISTRY` |

### A09:2021 — Security Logging and Monitoring

| Control | Status |
|---|---|
| Structured JSON logging | Implemented (`sunlight_logging.py`) |
| Per-request API key usage tracking | Implemented |
| Audit log for all scoring operations | Implemented |
| Rate limit violation logging | Implemented |

**Recommendation:** Add IP address and user agent logging for security monitoring (post-launch).

### A10:2021 — Server-Side Request Forgery (SSRF)

| Status | Evidence |
|---|---|
| No SSRF vectors | Application does not make outbound HTTP requests based on user input |

---

## 3. API Security Top 10 (2023) Mapping

| Risk | Status |
|---|---|
| API1: Broken Object Level Auth | API key scopes; no per-object ACL (acceptable for current model) |
| API2: Broken Authentication | SHA-256 hashed keys, rate limiting, key rotation |
| API3: Broken Object Property Level Auth | Pydantic models enforce allowed fields |
| API4: Unrestricted Resource Consumption | 50MB request limit, rate limiting per key, pagination limits |
| API5: Broken Function Level Auth | Admin scope check on all admin endpoints |
| API6: Unrestricted Access to Sensitive Business Flows | Rate limiting; batch analysis requires explicit invocation |
| API7: Server Side Request Forgery | No outbound requests from user input |
| API8: Security Misconfiguration | CORS configurable, no debug mode, no default keys |
| API9: Improper Inventory Management | All endpoints documented in OpenAPI spec |
| API10: Unsafe Consumption of APIs | No third-party API consumption |

---

## 4. Input Validation Summary

| Field | Validation | Source |
|---|---|---|
| `contract_id` | max_length=100 | Pydantic `ContractIn` |
| `award_amount` | gt=0, le=1e15 | Pydantic `ContractIn` |
| `vendor_name` | max_length=500 | Pydantic `ContractIn` |
| `agency_name` | max_length=500 | Pydantic `ContractIn` |
| `description` | max_length=10000 | Pydantic `ContractIn` |
| `start_date` | max_length=30 | Pydantic `ContractIn` |
| `n_bootstrap` | ge=100, le=50000 | Pydantic `BatchRequest` |
| `fdr_alpha` | gt=0, lt=1 | Pydantic `BatchRequest` |
| `limit` (pagination) | ge=1, le=500 | Query parameter |
| `offset` (pagination) | ge=0 | Query parameter |
| File uploads | 50MB max, format validated | Middleware + ingestion |

---

## 5. Residual Risks

| Risk | Severity | Mitigation Plan |
|---|---|---|
| No HTTPS enforcement in application layer | Medium | Deploy behind nginx/Caddy with TLS (pre-launch) |
| CORS defaults to `*` in development | Low | Set `SUNLIGHT_CORS_ORIGINS` for production domains |
| No IP-based rate limiting | Low | Add WAF rules post-launch |
| Key expiration tracked but not auto-enforced | Low | Implement expiration check in auth middleware |
| No MFA for admin access | Low | API key model doesn't support MFA; consider OAuth2 for admin portal |

---

*This threat model should be reviewed whenever new endpoints, authentication methods, or data flows are added.*
