FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
RUN python -m playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend backend
COPY data data
COPY references/*.xlsx references/
COPY scripts scripts

ENV PORT=8080
ENV PLAYWRIGHT_BROWSER_CHANNEL=""
CMD exec gunicorn --bind :${PORT} --workers 1 --threads 8 --timeout 0 backend.wsgi:app
