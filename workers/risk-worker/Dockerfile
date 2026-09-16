# =============================================================================
# Risk Worker Dockerfile
# =============================================================================
FROM python:3.11-slim

WORKDIR /app

COPY workers/risk-worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared /app/shared
COPY workers/risk-worker/app /app/app

CMD ["python", "-m", "app.main"]
