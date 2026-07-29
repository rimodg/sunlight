# SUNLIGHT API - Production Container Image
# Multi-stage build for minimal attack surface and reproducible deployment

# ============================================================================
# Stage 1: Builder - Install dependencies
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies if needed (currently none, but reserved for future needs)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# Stage 2: Runtime - Minimal production image
# ============================================================================
FROM python:3.11-slim

# Security: Create non-root user for running the application
RUN groupadd -r sunlight && useradd -r -g sunlight -u 1000 sunlight

# Set working directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/sunlight/.local

# Copy application code
COPY --chown=sunlight:sunlight code/ ./code/

# Copy required data files
COPY --chown=sunlight:sunlight prosecuted_cases.json ./
COPY --chown=sunlight:sunlight data/ ./data/

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
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=2.0)" || exit 1

# Run the API server
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
