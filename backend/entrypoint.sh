#!/usr/bin/env sh
set -eu

# Optional: wait for DB if needed (simple TCP check)
if [ -n "${DB_HOST:-}" ] && [ -n "${DB_PORT:-}" ]; then
  echo "Waiting for DB at ${DB_HOST}:${DB_PORT}..."
  for i in $(seq 1 60); do
    nc -z "${DB_HOST}" "${DB_PORT}" >/dev/null 2>&1 && break
    sleep 1
  done
fi

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
# Use gunicorn with uvicorn workers for production.
# WEB_CONCURRENCY defaults to 2 if not set.
exec gunicorn \
  -k uvicorn.workers.UvicornWorker \
  -w "${WEB_CONCURRENCY:-2}" \
  -b 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile - \
  --timeout "${GUNICORN_TIMEOUT:-60}" \
  app.main:app
