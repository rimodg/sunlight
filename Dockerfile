FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY code/ ./code/
COPY static/ ./static/ 2>/dev/null || true

WORKDIR /app/code

EXPOSE 8000

CMD ["uvicorn", "cri_api:app", "--host", "0.0.0.0", "--port", "8000"]
