# SUNLIGHT API Integration Guide

**Version:** 1.0.0
**Base URL:** `https://api.sunlight.example.com` (production)
**Interactive Docs:** `/docs` (Swagger UI) | `/redoc` (ReDoc)
**OpenAPI Spec:** `/openapi.json`

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Quick Start](#2-quick-start)
3. [Submitting Contracts](#3-submitting-contracts)
4. [Running Analysis](#4-running-analysis)
5. [Reading Detection Reports](#5-reading-detection-reports)
6. [File Ingestion (Bulk Upload)](#6-file-ingestion-bulk-upload)
7. [Triage Queue](#7-triage-queue)
8. [Webhook Setup for Async Results](#8-webhook-setup-for-async-results)
9. [Admin Dashboard](#9-admin-dashboard)
10. [Error Handling](#10-error-handling)
11. [Rate Limits](#11-rate-limits)
12. [Methodology Transparency](#12-methodology-transparency)

---

## 1. Authentication

All API requests require an API key passed in the `X-API-Key` header.

```bash
curl -H "X-API-Key: sk_sunlight_YOUR_KEY_HERE" \
     https://api.sunlight.example.com/health
```

### Getting an API Key

Contact your SUNLIGHT administrator, or if you have admin access:

```bash
curl -X POST https://api.sunlight.example.com/admin/keys \
     -H "X-API-Key: sk_sunlight_ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"client_name": "my-app", "rate_limit": 100, "scopes": "read,analyze"}'
```

Response:
```json
{
  "key_id": "key_a1b2c3d4...",
  "api_key": "sk_sunlight_...",
  "client_name": "my-app",
  "rate_limit": 100,
  "scopes": "read,analyze"
}
```

**Save the `api_key` immediately** — it is only shown once.

### Scopes

| Scope | Permissions |
|---|---|
| `read` | List contracts, scores, runs, reports |
| `analyze` | Submit contracts, run single/batch analysis |
| `admin` | Key management, dashboard, all operations |

### Key Rotation

Rotate keys periodically without downtime:

```bash
curl -X POST https://api.sunlight.example.com/admin/keys/rotate \
     -H "X-API-Key: sk_sunlight_ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"key_id": "key_a1b2c3d4..."}'
```

The old key is immediately revoked and a new key is returned.

---

## 2. Quick Start

### Check System Health

```bash
curl -H "X-API-Key: $API_KEY" https://api.sunlight.example.com/health
```

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "sunlight.db",
  "contract_count": 42593,
  "scored_count": 56556,
  "audit_chain_valid": true
}
```

### Analyze a Single Contract

```bash
curl -X POST https://api.sunlight.example.com/analyze \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "contract_id": "MY-CONTRACT-001",
       "award_amount": 15000000,
       "vendor_name": "Acme Defense Corp",
       "agency_name": "DEPARTMENT OF DEFENSE",
       "description": "Logistics support services"
     }'
```

```json
{
  "contract_id": "MY-CONTRACT-001",
  "fraud_tier": "YELLOW",
  "confidence_score": 72,
  "markup_pct": 185.3,
  "markup_ci_lower": 170.2,
  "markup_ci_upper": 195.8,
  "bayesian_posterior": 0.6222,
  "comparable_count": 847,
  "reasoning": [
    "Contract amount exceeds 95th percentile of comparable contracts",
    "Bootstrap CI lower bound (170.2%) exceeds investigation threshold (75%)",
    "Bayesian posterior probability: 62.2%"
  ],
  "legal_citations": [
    "31 U.S.C. 3729 — False Claims Act"
  ],
  "methodology_version": "1.0.0"
}
```

---

## 3. Submitting Contracts

### Single Contract

```bash
curl -X POST https://api.sunlight.example.com/contracts \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "contract_id": "CONTRACT-2026-001",
       "award_amount": 5000000,
       "vendor_name": "Example Corp",
       "agency_name": "DEPARTMENT OF ENERGY",
       "description": "IT infrastructure upgrade",
       "start_date": "2026-01-15"
     }'
```

### List Contracts

```bash
# Paginated list
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/contracts?limit=20&offset=0"

# Filter by agency
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/contracts?agency=DEFENSE&min_amount=1000000"

# Filter by vendor
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/contracts?vendor=Boeing"
```

---

## 4. Running Analysis

### Single Contract Analysis

Returns immediate results with full statistical evidence:

```bash
curl -X POST https://api.sunlight.example.com/analyze \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "contract_id": "CONTRACT-2026-001",
       "award_amount": 25000000,
       "vendor_name": "Defense Systems Inc",
       "agency_name": "DEPARTMENT OF DEFENSE",
       "is_sole_source": true,
       "has_political_donations": false
     }'
```

### Batch Analysis

Scores all contracts in the database through the full pipeline (two-pass: scoring + FDR correction):

```bash
curl -X POST https://api.sunlight.example.com/analyze/batch \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "run_seed": 42,
       "n_bootstrap": 1000,
       "fdr_alpha": 0.10,
       "limit": 1000
     }'
```

Response:
```json
{
  "run_id": "run_20260218_...",
  "run_seed": 42,
  "config_hash": "abc123...",
  "dataset_hash": "def456...",
  "n_contracts": 1000,
  "n_scored": 998,
  "n_errors": 2,
  "tier_counts": {"RED": 45, "YELLOW": 312, "GREEN": 640, "GRAY": 1},
  "pass1_time": 123.4
}
```

### Query Scores

```bash
# All scores from a run
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/scores?run_id=run_20260218_...&tier=RED"

# Scores for a specific contract
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/scores/CONTRACT-2026-001"
```

---

## 5. Reading Detection Reports

### JSON Format (Machine-Readable)

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/reports/detection/CONTRACT-2026-001?format=json"
```

Returns a structured report with:
- **Assessment:** Risk level, tier, confidence score
- **Evidence:** Markup analysis, bootstrap CIs, Bayesian posteriors
- **Context:** Agency statistics, comparable contracts
- **Explanation:** Plain-language reasoning for every finding
- **Recommendations:** Specific next steps per risk level
- **Methodology:** Statistical methods used, transparency section

### Markdown Format (Human-Readable)

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/reports/detection/CONTRACT-2026-001?format=markdown"
```

Returns a formatted markdown document suitable for:
- World Bank reviewers
- Institutional compliance teams
- Legal proceedings documentation
- Board presentations

### Evidence Package (Court-Grade)

Full prosecutor-grade statistical evidence:

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/reports/evidence/CONTRACT-2026-001"
```

Includes raw z-scores, bootstrap distributions, Bayesian computations, FDR-adjusted p-values, and legal citations.

---

## 6. File Ingestion (Bulk Upload)

Upload procurement documents for automatic extraction and scoring.

### JSON File

```bash
curl -X POST https://api.sunlight.example.com/ingest \
     -H "X-API-Key: $API_KEY" \
     -F "file=@contracts.json"
```

Supported JSON formats:
```json
// Single contract
{"contract_id": "...", "award_amount": 1000000, "vendor_name": "...", "agency_name": "..."}

// Array
[{"contract_id": "...", ...}, {"contract_id": "...", ...}]

// Wrapped
{"contracts": [{"contract_id": "...", ...}]}
```

### CSV File

```bash
curl -X POST https://api.sunlight.example.com/ingest \
     -H "X-API-Key: $API_KEY" \
     -F "file=@contracts.csv"
```

Expected header row (flexible column names accepted):
```
contract_id,award_amount,vendor_name,agency_name,description
```

### PDF File (Best-Effort)

```bash
curl -X POST https://api.sunlight.example.com/ingest \
     -H "X-API-Key: $API_KEY" \
     -F "file=@procurement_document.pdf"
```

PDF extraction is best-effort. Use JSON or CSV for reliable ingestion.

### Check Ingestion Status

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/ingest/ingest_20260218_123456_abc123"
```

```json
{
  "job_id": "ingest_20260218_123456_abc123",
  "status": "COMPLETED",
  "source_format": "csv",
  "total_records": 150,
  "inserted": 148,
  "duplicates": 2,
  "errors": 0,
  "scored": 148
}
```

---

## 7. Triage Queue

The triage queue shows flagged contracts ordered by investigation priority (RED first, then YELLOW):

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/reports/triage?limit=20"
```

Each item includes the fraud tier, confidence score, markup percentage, vendor name, agency, and award amount — everything needed to prioritize investigations.

---

## 8. Webhook Setup for Async Results

For batch analysis and file ingestion, results are processed asynchronously. Use polling or webhook patterns:

### Polling Pattern

```python
import time
import httpx

# Submit ingestion
resp = httpx.post(f"{BASE_URL}/ingest",
    headers={"X-API-Key": API_KEY},
    files={"file": open("contracts.csv", "rb")})
job_id = resp.json()["job_id"]

# Poll until complete
while True:
    status = httpx.get(f"{BASE_URL}/ingest/{job_id}",
        headers={"X-API-Key": API_KEY}).json()
    if status["status"] in ("COMPLETED", "FAILED"):
        break
    time.sleep(5)

print(f"Inserted: {status['inserted']}, Scored: {status['scored']}")
```

### Webhook Pattern (Recommended for Production)

Configure a callback URL when submitting jobs. SUNLIGHT will POST results to your endpoint when processing completes:

```python
# In your webhook receiver (Flask/FastAPI/Express):
@app.post("/webhook/sunlight")
async def handle_sunlight_webhook(payload: dict):
    job_id = payload["job_id"]
    status = payload["status"]
    if status == "COMPLETED":
        # Fetch detailed results
        results = httpx.get(f"{SUNLIGHT_URL}/ingest/{job_id}",
            headers={"X-API-Key": API_KEY}).json()
        process_results(results)
```

*Note: Webhook delivery requires configuring the callback URL in your SUNLIGHT instance settings.*

---

## 9. Admin Dashboard

Requires `admin` scope.

### System Health

```bash
curl -H "X-API-Key: $ADMIN_KEY" \
     "https://api.sunlight.example.com/admin/dashboard/health"
```

Returns database stats, pipeline status, audit chain integrity, ingestion job history.

### Detection Statistics

```bash
curl -H "X-API-Key: $ADMIN_KEY" \
     "https://api.sunlight.example.com/admin/dashboard/detections"
```

Returns tier distribution, run history, top flagged vendors/agencies, markup distribution.

### API Usage

```bash
curl -H "X-API-Key: $ADMIN_KEY" \
     "https://api.sunlight.example.com/admin/dashboard/api-usage"
```

Returns per-client request volume, top endpoints, active keys.

### Flagged Contracts Queue

```bash
# All flagged contracts
curl -H "X-API-Key: $ADMIN_KEY" \
     "https://api.sunlight.example.com/admin/dashboard/flagged"

# Only RED-tier contracts
curl -H "X-API-Key: $ADMIN_KEY" \
     "https://api.sunlight.example.com/admin/dashboard/flagged?tier=RED"
```

---

## 10. Error Handling

All errors return JSON with `detail`:

| Status Code | Meaning |
|---|---|
| 400 | Invalid request (bad format, missing fields) |
| 401 | Missing or invalid API key |
| 403 | Insufficient scope (e.g., non-admin accessing admin endpoints) |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate contract ID) |
| 413 | Request body too large (max 50 MB) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Database unavailable |

```json
{
  "detail": "Contract MY-CONTRACT-001 already exists"
}
```

---

## 11. Rate Limits

Each API key has a configurable rate limit (default: 100 requests per hour). When exceeded:

```json
{
  "detail": "Rate limit exceeded. Try again in 42 seconds."
}
```

Contact your administrator to adjust rate limits for production workloads.

---

## 12. Methodology Transparency

SUNLIGHT is not a black box. Every detection is explainable:

```bash
curl -H "X-API-Key: $API_KEY" \
     "https://api.sunlight.example.com/methodology"
```

Returns:
- **Statistical methods:** BCa Bootstrap, Bayesian analysis, Benjamini-Hochberg FDR
- **Thresholds:** DOJ prosecution precedent (Extreme >300%, High >200%, Elevated >150%, Investigation-Worthy >75%)
- **Tier definitions:** RED (prosecution-ready), YELLOW (investigation-worthy), GREEN (normal), GRAY (insufficient data)
- **Legal framework:** False Claims Act, Anti-Kickback Act, Procurement Integrity Act
- **Base rates:** DOJ-calibrated fraud prevalence rates

Every scoring decision includes human-readable reasoning and legal citations.
