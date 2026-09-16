FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/s3-storage/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/s3-storage/app /app/app

RUN mkdir -p /data/adaptive-lms-content

EXPOSE 9000 9001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
