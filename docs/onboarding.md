# SUNLIGHT Onboarding Guide

**Target:** New tenant from zero to first scan results in under 10 minutes.

## Step 1: Create Tenant (1 min)

```bash
curl -X POST $BASE_URL/api/v2/tenants \
  -H "Content-Type: application/json" \
  -d '{"name": "Your Organization", "slug": "your-org", "tier": "standard"}'
```

Save the returned `tenant_id` and `webhook_secret`.

## Step 2: Set Webhook URL (30 sec)

```bash
curl -X PATCH $BASE_URL/api/v2/tenants/$TENANT_ID/webhook \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://your-server.com/sunlight-hook"}'
```

## Step 3: Create API Key (30 sec)

```bash
curl -X POST $BASE_URL/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{"client_name": "your-org-admin", "scopes": "read,analyze,admin"}'
```

Save the returned API key — it's shown once.

## Step 4: Create Users (1 min)

```bash
curl -X POST $BASE_URL/api/v2/tenants/$TENANT_ID/users \
  -H "X-API-Key: $API_KEY" \
  -d '{"email": "analyst@your-org.com", "role": "analyst"}'
```

Roles: `viewer` (read-only), `analyst` (read + scan + export), `admin` (full access).

## Step 5: Ingest Data (2 min)

### Option A: CSV Upload
```bash
curl -X POST $BASE_URL/ingest \
  -H "X-API-Key: $API_KEY" \
  -F "file=@contracts.csv" \
  -F "format=csv"
```

Required CSV columns: `contract_id`, `award_amount`, `vendor_name`, `agency_name`
Optional: `description`, `start_date`

### Option B: JSON API
```bash
curl -X POST $BASE_URL/contracts \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "contract_id": "DOD-2024-001",
    "award_amount": 5000000,
    "vendor_name": "ACME Corp",
    "agency_name": "Department of Defense",
    "description": "IT support services"
  }'
```

### Data Quality Report
After ingestion, check quality:
```bash
curl $BASE_URL/ingest/$JOB_ID
```
Reports: missing fields, normalization confidence, records that will be GRAY (insufficient comparables).

## Step 6: Run First Scan (3 min)

```bash
curl -X POST $BASE_URL/api/v2/scan \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"idempotency_key": "first-scan"}'
```

Poll for progress:
```bash
curl $BASE_URL/api/v2/jobs/$JOB_ID -H "X-API-Key: $API_KEY"
```

## Step 7: View Results (2 min)

### Risk Inbox
```bash
curl $BASE_URL/api/v2/risk-inbox -H "X-API-Key: $API_KEY"
```

### Case Packet
```bash
curl $BASE_URL/reports/evidence/$CONTRACT_ID -H "X-API-Key: $API_KEY"
```

### Portfolio View
```bash
curl $BASE_URL/api/v2/portfolio -H "X-API-Key: $API_KEY"
```

## Onboarding Checklist

```bash
curl $BASE_URL/api/v2/onboarding/status -H "X-API-Key: $API_KEY"
```

Returns:
```json
{
  "steps": {
    "tenant_created": true,
    "data_ingested": true,
    "first_scan_complete": true,
    "risk_inbox_available": true
  },
  "complete": true,
  "next_step": "done"
}
```

## Seeded Sandbox

The demo tenant (`ten_demo`) comes pre-loaded with:
- 100 sample contracts across 5 agencies
- Pre-run scan with RED/YELLOW/GREEN results
- Sample case packets ready to view
- Guided tour flag in settings

Access: Use API key for demo tenant, or visit `$BASE_URL/dashboard`.
