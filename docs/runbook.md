# SUNLIGHT Operations Runbook

## Alert: High Error Rate (5xx > 1%)

**Severity:** Critical

1. Check API logs: `docker logs sunlight-api --tail 100 | grep ERROR`
2. Check health endpoint: `curl http://localhost:8000/health`
3. Check DB connectivity: `psql -h $POSTGRES_HOST -U sunlight -c "SELECT 1"`
4. If DB is down: check RDS console / `pg_isready`
5. If API is OOM: scale ECS task memory or restart
6. Rollback if recent deploy: `terraform apply -var-file=prod.tfvars` with previous image

## Alert: P95 Latency Breach (>2000ms)

**Severity:** Warning

1. Check which endpoints are slow: `GET /api/v2/metrics` → find high p95 entries
2. Common causes:
   - Large batch scan running → check `GET /api/v2/queue/health`
   - DB slow queries → check PostgreSQL `pg_stat_statements`
   - Cold start after deploy → wait 2 minutes
3. If DB: add connection pooling or check index usage
4. If compute: scale ECS tasks horizontally

## Alert: Queue Backlog (oldest job >300s)

**Severity:** Warning

1. Check queue: `GET /api/v2/queue/health`
2. Check if worker is running: look for `Worker started` in logs
3. If worker crashed: restart API container (worker runs as background thread)
4. If jobs are failing: check `GET /api/v2/dlq` for error messages
5. If overloaded: increase `max_concurrency` in tenant settings

## Alert: DLQ Growth (>10 items)

**Severity:** Critical

1. Check DLQ: `GET /api/v2/dlq`
2. Review error messages — common causes:
   - DB constraint violations (data quality)
   - Pipeline timeout (large dataset)
   - Configuration errors
3. Fix root cause, then retry: manually resubmit jobs
4. Clear DLQ entries after resolution

## Alert: Webhook Delivery Failures (>5%)

**Severity:** Warning

1. Check webhook logs: `GET /api/v2/webhooks/deliveries`
2. Common causes:
   - Client endpoint down (check `last_status_code`)
   - DNS resolution failure
   - Client returning non-2xx
   - TLS certificate issues
3. Contact tenant if their endpoint is consistently failing
4. Webhook retries automatically with exponential backoff (max 5 attempts)

## General Troubleshooting

### Restart API
```bash
# Local
docker compose restart api

# AWS ECS
aws ecs update-service --cluster sunlight-prod-cluster \
  --service sunlight-prod-api --force-new-deployment
```

### Check Database
```bash
psql -h $POSTGRES_HOST -U sunlight sunlight
> SELECT COUNT(*) FROM contracts;
> SELECT tier, COUNT(*) FROM contract_scores GROUP BY tier;
> SELECT status, COUNT(*) FROM scan_jobs GROUP BY status;
```

### View Recent Audit Log
```bash
psql -h $POSTGRES_HOST -U sunlight sunlight
> SELECT action, timestamp, details FROM audit_log ORDER BY sequence_number DESC LIMIT 20;
```

### Force Re-run Evaluation
```bash
cd code && python evaluation.py --ci --bootstrap 500 --clean 100
```
