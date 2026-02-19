# SUNLIGHT Async Scanning & Webhooks

## Async Scan Flow

```
POST /api/v2/scan  →  { job_id: "job_abc123", status: "QUEUED" }
                         ↓
GET /api/v2/jobs/job_abc123  →  { status: "RUNNING", progress_pct: 45 }
                         ↓
GET /api/v2/jobs/job_abc123  →  { status: "SUCCEEDED", result: {...} }
                         ↓
Webhook: POST to tenant webhook_url with signed payload
```

## Submitting a Scan

```bash
curl -X POST https://api.sunlight.dev/api/v2/scan \
  -H "X-API-Key: sk_sunlight_..." \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "scan-2026-02-18",
    "seed": 42,
    "limit": 1000,
    "config": {"n_bootstrap": 1000}
  }'
```

Response:
```json
{
  "job_id": "job_a1b2c3d4e5f67890",
  "status": "QUEUED",
  "message": "Scan queued. Poll /api/v2/jobs/{job_id} for progress."
}
```

## Polling Job Status

```bash
curl https://api.sunlight.dev/api/v2/jobs/job_a1b2c3d4e5f67890 \
  -H "X-API-Key: sk_sunlight_..."
```

Status transitions: `QUEUED → RUNNING → SUCCEEDED | FAILED → DLQ`

## Idempotency

Include `idempotency_key` to prevent duplicate scans. Same key + same tenant = same job returned.

## Retries

Failed jobs retry with exponential backoff:
- Attempt 1: immediate
- Attempt 2: 5 seconds
- Attempt 3: 10 seconds (max 3 attempts by default)

Exhausted jobs move to Dead Letter Queue (DLQ).

## Webhooks

### Registration

```bash
curl -X PATCH https://api.sunlight.dev/api/v2/tenants/{tenant_id}/webhook \
  -H "X-API-Key: sk_sunlight_..." \
  -d '{"webhook_url": "https://your-server.com/sunlight-webhook"}'
```

### Payload Format

```json
{
  "event_id": "evt_abc123def456",
  "event_type": "scan.completed",
  "tenant_id": "ten_xyz789",
  "timestamp": "2026-02-18T19:30:00Z",
  "data": {
    "job_id": "job_a1b2c3d4e5f67890",
    "run_id": "run_20260218_193000_42",
    "tier_counts": {"RED": 2, "YELLOW": 19, "GREEN": 979}
  }
}
```

### Signature Verification

Every webhook includes `X-Sunlight-Signature` header:
```
X-Sunlight-Signature: t=1708286400,v1=5257a869e7eceb...
```

Verify in your code:
```python
import hmac, hashlib, time

def verify(secret, header, payload):
    parts = dict(p.split("=", 1) for p in header.split(","))
    ts, sig = int(parts["t"]), parts["v1"]

    # Replay protection: reject if > 5 minutes old
    if abs(time.time() - ts) > 300:
        return False

    expected = hmac.new(
        secret.encode(), f"{ts}.{payload}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)
```

### Delivery Retries

Failed deliveries retry with exponential backoff (max 5 attempts).
Delivery logs visible at `GET /api/v2/webhooks/deliveries`.

### Event Types

| Event | Trigger |
|-------|---------|
| `scan.completed` | Scan job finished successfully |
| `scan.failed` | Scan job exhausted retries |
| `alert.red` | RED-tier contract detected |

### Delivery Logs

```bash
curl https://api.sunlight.dev/api/v2/webhooks/deliveries \
  -H "X-API-Key: sk_sunlight_..."
```
