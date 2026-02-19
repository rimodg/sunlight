# SUNLIGHT Observability

## Stack

**Prometheus + Grafana (OSS)**. Self-hosted or managed (Grafana Cloud).

## Metrics Endpoint

`GET /api/v2/metrics` — Prometheus text exposition format.

### Metrics Collected

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | counter | Request count by method, endpoint, status |
| `http_request_duration_ms` | histogram | Latency p50/p95/p99 by endpoint |
| `http_requests_errors_total` | counter | 5xx error count |
| `rate_limit_hits_total` | counter | Rate limit rejections |
| `auth_failures_total` | counter | 401/403 responses |
| `jobs_queued` | gauge | Jobs waiting to be processed |
| `jobs_running` | gauge | Jobs currently executing |
| `jobs_dlq_size` | gauge | Dead-letter queue size |
| `jobs_oldest_queued_age_sec` | gauge | Age of oldest queued job |
| `webhooks_pending` | gauge | Webhook deliveries awaiting send |
| `webhooks_failed` | gauge | Failed webhook deliveries |

### Queue Health

`GET /api/v2/queue/health` — JSON queue metrics:
```json
{
  "queued": 3,
  "running": 1,
  "succeeded": 142,
  "failed": 2,
  "dlq": 0,
  "oldest_queued_age_sec": 12.4,
  "total_jobs": 148
}
```

## Structured Logging

All logs are JSON with these fields:
- `timestamp`, `level`, `logger`, `message`
- `request_id` — unique per HTTP request
- `tenant_id` — current tenant (if authenticated)
- `job_id` — for job-related operations
- `contract_id` — for contract-related operations

Error logs include `error` + `traceback` but **no PII**.

## Prometheus Configuration

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'sunlight'
    scrape_interval: 15s
    metrics_path: '/api/v2/metrics'
    static_targets:
      - targets: ['sunlight-api:8000']
```

## Grafana Dashboards

Import `infra/grafana/sunlight-dashboard.json` or create:

1. **API Health**: request rate, error rate, p95 latency
2. **Queue Health**: depth, age, success/fail rate, DLQ
3. **Webhook Delivery**: pending, delivered, failed
4. **Tenant Activity**: requests per tenant, scan frequency

## Alerts (SLO-based)

| Alert | Condition | Severity |
|-------|-----------|----------|
| High Error Rate | 5xx rate > 1% for 5 min | critical |
| P95 Latency Breach | p95 > 2000ms for 5 min | warning |
| Queue Backlog | oldest job > 300s | warning |
| DLQ Growth | DLQ size > 10 | critical |
| Webhook Failures | failure rate > 5% for 1 hour | warning |

See [runbook.md](runbook.md) for response procedures.
