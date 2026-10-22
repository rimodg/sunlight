# SUNLIGHT API - Production Container Image
# Multi-stage build for minimal attack surface and reproducible deployment

# Build the same-origin evidence workspace.
FROM node:24-slim AS workspace
WORKDIR /workspace/sunlight-dashboard
COPY sunlight-dashboard/package.json sunlight-dashboard/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --strict-ssl=true
COPY sunlight-dashboard/ ./
COPY static/ /workspace/static/
RUN npm run build -- --base=/watch/

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies if needed (currently none, but reserved for future needs)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim
ARG SUNLIGHT_BUILD_REVISION=unversioned
LABEL org.opencontainers.image.source="https://github.com/rimodg/sunlight" \
      org.opencontainers.image.revision=$SUNLIGHT_BUILD_REVISION

# Security: Create non-root user for running the application
RUN groupadd -r sunlight && useradd -r -g sunlight -u 1000 sunlight

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/sunlight/.local

# Copy application code
COPY --chown=sunlight:sunlight code/ ./code/

# Ship calibration inputs, not the ignored evaluation-only prosecution fixture.
COPY --chown=sunlight:sunlight research/corpus/ ./research/corpus/
COPY --chown=sunlight:sunlight data/ ./data/
COPY --from=workspace --chown=sunlight:sunlight /workspace/sunlight-dashboard/dist/ ./sunlight-dashboard/dist/

# Create calibration directory with correct ownership for runtime state
RUN mkdir -p /app/calibration && chown -R sunlight:sunlight /app/calibration

# Environment variables with secure defaults
ENV PATH=/home/sunlight/.local/bin:$PATH \
    PYTHONPATH=/app/code \
    PYTHONUNBUFFERED=1 \
    SUNLIGHT_LOG_LEVEL=INFO \
    SUNLIGHT_CALIBRATION_DIR=/app/calibration

# Security: Switch to non-root user
USER sunlight

# Expose API port
EXPOSE 8000

# Health check configuration - uses the /health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://localhost:8000/health', timeout=2.0); r.raise_for_status(); assert r.json()['status']=='ok'" || exit 1

# Run the API server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
