#!/usr/bin/env bash
set -euo pipefail

# Hostinger production redeploy helper.
# Run this ON THE VPS from the repo root folder.

REPO_DIR="${REPO_DIR:-$PWD}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

# Optional switches (default off for safety in real production)
RUN_SYSTEM_SEEDS="${RUN_SYSTEM_SEEDS:-0}"   # 1 = seed core roles/admin (safe for fresh prod)
RUN_SEEDS="${RUN_SEEDS:-0}"           # 1 = run seed scripts (demo/provisioning)
RUN_SMOKE_TESTS="${RUN_SMOKE_TESTS:-0}" # 1 = run API smoke tests after deploy
RUN_READONLY_SMOKE_TESTS="${RUN_READONLY_SMOKE_TESTS:-0}" # 1 = run read-only smoke tests after deploy
RUN_CLIENT_DETAILS_SMOKE_TESTS="${RUN_CLIENT_DETAILS_SMOKE_TESTS:-0}" # 1 = run client-details write smoke test after deploy
SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://backend:8000/api/v1}"
ERP_PASSWORD="${ERP_PASSWORD:-test@12345}"

# 1 = tail backend logs at the end (interactive). 0 = exit after deploy checks.
TAIL_LOGS="${TAIL_LOGS:-1}"

# Read-only smoke test credentials (recommended for production)
SMOKE_USERNAME="${SMOKE_USERNAME:-}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-}"
SMOKE_BD_USERNAME="${SMOKE_BD_USERNAME:-}"
SMOKE_BD_PASSWORD="${SMOKE_BD_PASSWORD:-}"

cd "$REPO_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: $COMPOSE_FILE not found in $REPO_DIR" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Create it from backend/production.env.example" >&2
  exit 1
fi

echo "==> Pulling latest code"
if [[ -d .git ]]; then
  git pull --rebase
else
  echo "(skip) Not a git checkout (.git missing). Sync code via rsync/scp first."
fi

echo "==> Rebuilding & restarting production stack"
sudo docker compose -f "$COMPOSE_FILE" down
sudo docker compose -f "$COMPOSE_FILE" up -d --build

echo "==> Running DB migrations (alembic upgrade head)"
set +e
for i in {1..60}; do
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app backend alembic upgrade head >/dev/null 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    break
  fi
  sleep 2
done
set -e

if [[ $rc -ne 0 ]]; then
  echo "ERROR: Alembic migrations failed after retries" >&2
  sudo docker compose -f "$COMPOSE_FILE" logs --tail=200 backend >&2 || true
  exit 1
fi

echo "==> Waiting for API health"
set +e
for i in {1..60}; do
  # Check health from inside the backend container to avoid:
  # - HTTP->HTTPS redirects in nginx
  # - cert mismatch when curling https://localhost
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app backend \
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).read()" \
    >/dev/null 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    break
  fi
  sleep 2
done
set -e

echo "==> Showing running services"
sudo docker compose -f "$COMPOSE_FILE" ps

if [[ "$RUN_SYSTEM_SEEDS" == "1" ]]; then
  echo "==> Running system seed scripts (RUN_SYSTEM_SEEDS=1)"
  # Safe for fresh installs: create roles/permissions + ensure admin user exists.
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_admin.py
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/create_admin.py
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_hr_permissions.py
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_departments.py
fi

if [[ "$RUN_SEEDS" == "1" ]]; then
  echo "==> Running seed scripts (RUN_SEEDS=1)"
  # NOTE: seed_demo_users creates demo accounts: admin/hr/pm/employee/bd/ceo.
  # Use only on fresh installs or staging.
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_demo_users.py
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_hr_permissions.py
fi

if [[ "$RUN_SMOKE_TESTS" == "1" ]]; then
  echo "==> Running smoke tests (RUN_SMOKE_TESTS=1)"
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app backend sh -c "ERP_BASE_URL='${SMOKE_BASE_URL}' ERP_PASSWORD='${ERP_PASSWORD}' python happy_path_test.py"
fi

if [[ "$RUN_READONLY_SMOKE_TESTS" == "1" ]]; then
  echo "==> Running read-only smoke tests (RUN_READONLY_SMOKE_TESTS=1)"
  if [[ -z "${SMOKE_USERNAME}" || -z "${SMOKE_PASSWORD}" ]]; then
    echo "ERROR: Set SMOKE_USERNAME and SMOKE_PASSWORD for read-only smoke tests" >&2
    exit 2
  fi
  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app backend sh -c "ERP_BASE_URL='${SMOKE_BASE_URL}' ERP_USERNAME='${SMOKE_USERNAME}' ERP_PASSWORD='${SMOKE_PASSWORD}' python readonly_smoke_test.py"
fi

if [[ "$RUN_CLIENT_DETAILS_SMOKE_TESTS" == "1" ]]; then
  echo "==> Running client details smoke test (RUN_CLIENT_DETAILS_SMOKE_TESTS=1)"
  if [[ -z "${SMOKE_USERNAME}" || -z "${SMOKE_PASSWORD}" ]]; then
    echo "ERROR: Set SMOKE_USERNAME and SMOKE_PASSWORD for client-details smoke tests" >&2
    exit 2
  fi

  extra_env=""
  if [[ -n "${SMOKE_BD_USERNAME}" && -n "${SMOKE_BD_PASSWORD}" ]]; then
    extra_env="ERP_BD_USERNAME='${SMOKE_BD_USERNAME}' ERP_BD_PASSWORD='${SMOKE_BD_PASSWORD}'"
  fi

  sudo docker compose -f "$COMPOSE_FILE" exec -T -w /app backend sh -c "ERP_BASE_URL='${SMOKE_BASE_URL}' ERP_USERNAME='${SMOKE_USERNAME}' ERP_PASSWORD='${SMOKE_PASSWORD}' ${extra_env} python client_details_smoke_test.py"
fi

if [[ "$TAIL_LOGS" == "1" ]]; then
  echo "==> Tail backend logs (Ctrl+C to stop)"
  sudo docker compose -f "$COMPOSE_FILE" logs -f --tail=200 backend
else
  echo "==> Redeploy complete (TAIL_LOGS=0)"
fi
