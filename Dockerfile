FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY code/ ./code/
COPY data/ ./data/
COPY prosecuted_cases.json ./
COPY migrations/ ./migrations/
COPY worker.py ./

# Ensure internal imports resolve (api.py uses sys.path.insert for siblings)
ENV PYTHONPATH=/app/code \
    SUNLIGHT_DB_PATH=/app/data/sunlight.db \
    SUNLIGHT_AUTH_ENABLED=true \
    SUNLIGHT_LOG_LEVEL=INFO \
    POSTGRES_HOST=postgres \
    POSTGRES_PORT=5432 \
    POSTGRES_DB=sunlight \
    POSTGRES_USER=sunlight \
    POSTGRES_PASSWORD=changeme

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); r.raise_for_status()" || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
