# SUNLIGHT Docker Deployment

Quick reference for containerized deployment of the SUNLIGHT API.

## Quick Start

```bash
# Build and start the API
docker-compose up -d

# Verify it's running
curl http://localhost:8000/health

# View logs
docker-compose logs -f api

# Stop the service
docker-compose down
```

## Image Details

**Base:** `python:3.11-slim`
**Architecture:** Multi-stage build (builder + runtime)
**User:** Non-root (`sunlight:sunlight`, UID 1000)
**Port:** 8000
**Health check:** `GET /health` every 30s

## Security Features

- ✅ Multi-stage build minimizes final image size
- ✅ Runs as non-root user (`sunlight:1000`)
- ✅ Read-only root filesystem with explicit writable mount for calibration data
- ✅ Dropped all capabilities except `NET_BIND_SERVICE`
- ✅ No shell in production image (slim base)
- ✅ Pinned Python dependencies
- ✅ Health check for container orchestration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SUNLIGHT_PORT` | `8000` | Host port mapping |
| `SUNLIGHT_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `SUNLIGHT_CALIBRATION_DIR` | `/app/calibration` | Empirical calibration store path |
| `SUNLIGHT_AUTH_ENABLED` | `false` | Enable authentication (future) |

## Volume Mounts

**Calibration data** (`calibration_data` volume):
- Persists empirical calibration state across container restarts
- Mounted at `/app/calibration` with read-write access
- Accumulates per-profile operational statistics
- Survives `docker-compose down` but is removed with `docker-compose down -v`

## Testing the Deployment

```bash
# Automated validation script
./scripts/test_docker_deployment.sh

# Manual verification
curl http://localhost:8000/health
curl http://localhost:8000/version
curl http://localhost:8000/profiles

# Single contract analysis
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d @examples/single_contract.json

# Batch analysis with capacity threshold
curl -X POST http://localhost:8000/batch \
  -H "Content-Type: application/json" \
  -d @examples/batch_contracts.json
```

## Production Deployment

### Building for Production

```bash
# Build with explicit tag
docker build -t sunlight-api:1.0.0 .

# Tag for registry
docker tag sunlight-api:1.0.0 your-registry/sunlight-api:1.0.0

# Push to registry
docker push your-registry/sunlight-api:1.0.0
```

### Running in Production

**Option 1: Docker Compose (recommended for single-host)**
```bash
# Production mode with specific version
SUNLIGHT_PORT=8000 docker-compose up -d

# Production mode with environment file
docker-compose --env-file .env.production up -d
```

**Option 2: Standalone Docker**
```bash
docker run -d \
  --name sunlight-api \
  --user 1000:1000 \
  -p 8000:8000 \
  -e SUNLIGHT_LOG_LEVEL=INFO \
  -v sunlight_calibration:/app/calibration \
  --read-only \
  --tmpfs /tmp:size=10M \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \
  --restart unless-stopped \
  sunlight-api:1.0.0
```

**Option 3: Kubernetes (see full stack in docker-compose.full.yml)**
```yaml
# See infra/k8s/ for Kubernetes manifests (future work)
```

## Troubleshooting

### Container exits immediately
```bash
# Check logs
docker-compose logs api

# Common causes:
# - Missing prosecuted_cases.json file
# - Missing data/sunlight.db file
# - Python import errors (check module dependencies)
```

### Health check failing
```bash
# Check if API is responding
docker-compose exec api curl http://localhost:8000/health

# Check container logs
docker-compose logs api

# Verify port is not already in use
lsof -i :8000
```

### Permission denied on calibration directory
```bash
# The Dockerfile creates /app/calibration with correct ownership
# If volume mount fails, check:
docker-compose exec api ls -la /app/calibration
docker-compose exec api whoami  # Should be 'sunlight'
```

## Full Stack Deployment

For the complete SUNLIGHT stack including PostgreSQL, Prometheus, and Grafana:
```bash
docker-compose -f docker-compose.full.yml up -d
```

See `docker-compose.full.yml` for configuration details.

## Development vs Production

**Development** (local testing):
- Use `docker-compose up` for easy iteration
- Mount local code directory as volume for live reload (not currently configured)
- Set `SUNLIGHT_LOG_LEVEL=DEBUG`

**Production** (institutional deployment):
- Use tagged image from registry
- Set `SUNLIGHT_LOG_LEVEL=INFO` or `WARNING`
- Enable proper monitoring and alerting
- Use secrets management for any future auth tokens
- Set resource limits (CPU/memory) in production orchestration
- Configure log aggregation (future work)

## Next Steps

- See `docs/INTEGRATION.md` for comprehensive deployment guide (future sub-task 2.2.7f)
- See `docker-compose.full.yml` for database and monitoring stack
- See `scripts/test_docker_deployment.sh` for automated validation
