FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY data data
COPY references/*.xlsx references/

ENV PORT=8080
CMD exec gunicorn --bind :${PORT} --workers 2 --threads 8 --timeout 0 backend.wsgi:app
