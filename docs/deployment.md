# SUNLIGHT Deployment Guide

## Quick Start

### Local (Docker Compose)
```bash
./infra/deploy.sh local
```
This starts PostgreSQL + the API. Available at http://localhost:8000.

### AWS Demo
```bash
./infra/deploy.sh demo
```
Provisions: VPC, ECS Fargate, RDS PostgreSQL, ALB. See `infra/aws/main.tf`.

### AWS Production
```bash
./infra/deploy.sh prod
```
Multi-AZ RDS, 2 ECS tasks, HTTPS with ACM certificate, 90-day log retention.

## Architecture

```
Client -> ALB (HTTPS) -> ECS Fargate (API) -> RDS PostgreSQL
                              |
                         Background Workers
                         (Scan + Webhooks)
```

## Environment Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SUNLIGHT_DB_PATH` | `data/sunlight.db` | SQLite path (dev only) |
| `SUNLIGHT_AUTH_ENABLED` | `true` | Enable API key auth |
| `SUNLIGHT_LOG_LEVEL` | `INFO` | Log level |
| `POSTGRES_HOST` | `localhost` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `sunlight` | Database name |
| `POSTGRES_USER` | `sunlight` | Database user |
| `POSTGRES_PASSWORD` | - | Database password (use SSM in prod) |
| `ENVIRONMENT` | `demo` | demo/staging/prod |

## Database Migration

SQLite (dev) -> PostgreSQL (prod):
```bash
python migrations/002_data_migration.py \
  --sqlite data/sunlight.db \
  --pg "postgresql://sunlight:password@host:5432/sunlight"
```

Verify: `psql -f migrations/003_verify.sql`

## Health Checks

- `GET /health` — API health + DB status
- ECS health check: every 30s, 3 retries
- ALB target group: /health, 2 healthy / 5 unhealthy threshold

## Monitoring

See [observability.md](observability.md) and [runbook.md](runbook.md).

## Security

See [security.md](security.md) and [security_threat_model.md](security_threat_model.md).

## Related Docs

- [API Reference](api.md)
- [Async & Webhooks](async_webhooks.md)
- [Multi-Tenancy](multi_tenancy.md)
- [Onboarding](onboarding.md)
- [Demo Script](demo_script.md)
