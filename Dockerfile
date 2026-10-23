FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RF_DESIGN_DATA_DIR=/tmp/rf-data \
    RF_DESIGN_RESOURCE_DIR=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-web.txt backend/requirements-web.txt
RUN pip install --no-cache-dir -r backend/requirements-web.txt

COPY backend backend
COPY data data
COPY references references
COPY scripts scripts

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 8 --timeout 300 backend.web:app"]
