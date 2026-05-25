#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:5173}"
E2E_EMAIL="${E2E_EMAIL:-employee@gmail.com}"
E2E_PASSWORD="${E2E_PASSWORD:-test@12345}"

# Visual run defaults (headed + a bit slower so you can follow the flow)
E2E_HEADED="${E2E_HEADED:-1}"
E2E_SLOWMO="${E2E_SLOWMO:-150}"

usage() {
  cat <<'EOF'
Run all UI tests (Playwright) in a visible browser.

This script is the canonical entrypoint for UI tests. It will:
  1) start Docker compose
  2) run migrations
  3) seed demo data (idempotent)
  4) run Playwright

Env vars:
  E2E_BASE_URL   (default: http://localhost:5173)
  E2E_EMAIL      (default: employee@gmail.com)
  E2E_PASSWORD   (default: test@12345)
  E2E_HEADED     (default: 1)
  E2E_SLOWMO     (default: 150)

Args:
  --help
  --headed | --headless
  --slowmo <ms>
  --base-url <url>
  --email <email>
  --password <password>

Examples:
  make ui-test
  E2E_SLOWMO=300 make ui-test
  bash scripts/run_ui_tests.sh --headless
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help)
      usage
      exit 0
      ;;
    --headed)
      E2E_HEADED=1
      shift
      ;;
    --headless)
      E2E_HEADED=0
      shift
      ;;
    --slowmo)
      E2E_SLOWMO="${2:-}"
      shift 2
      ;;
    --base-url)
      E2E_BASE_URL="${2:-}"
      shift 2
      ;;
    --email)
      E2E_EMAIL="${2:-}"
      shift 2
      ;;
    --password)
      E2E_PASSWORD="${2:-}"
      shift 2
      ;;
    *)
      echo "[ui-tests] Unknown arg: $1" >&2
      echo "[ui-tests] Run with --help for usage." >&2
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

# Use a repo-local TMPDIR to reduce reliance on macOS /var/folders.
mkdir -p "$ROOT_DIR/.tmp/playwright-tmp"
export TMPDIR="$ROOT_DIR/.tmp/playwright-tmp"

# Quick sanity check (gives a nicer error than Chromium's ProcessSingleton message)
if ! mktemp -p "$TMPDIR" >/dev/null 2>&1; then
  echo "[ui-tests] ERROR: Unable to create temp files in TMPDIR=$TMPDIR" >&2
  echo "[ui-tests] Likely cause: disk is full. Free up space and retry." >&2
  df -h "$ROOT_DIR" || true
  exit 1
fi

echo "[ui-tests] Starting docker stack…"
docker compose up -d --build

echo "[ui-tests] Running migrations…"
docker compose exec -T backend alembic upgrade head

echo "[ui-tests] Seeding demo data (idempotent)…"
# These scripts are intentionally tolerant of already-seeded data.
# PYTHONPATH is required when running from /app/scripts.
docker compose exec -T backend env PYTHONPATH=/app python scripts/seed_admin.py || true
docker compose exec -T backend env PYTHONPATH=/app python scripts/seed_demo_users.py || true
docker compose exec -T backend env PYTHONPATH=/app python scripts/seed_tasks.py || true

echo "[ui-tests] Installing frontend deps (if needed)…"
cd "$ROOT_DIR/frontend"
if [ ! -d node_modules ]; then
  npm install
fi

echo "[ui-tests] Ensuring Playwright browser is installed…"
# Cached after first run.
npx playwright install chromium

echo "[ui-tests] Running Playwright in visible browser…"
E2E_BASE_URL="$E2E_BASE_URL" \
E2E_EMAIL="$E2E_EMAIL" \
E2E_PASSWORD="$E2E_PASSWORD" \
E2E_HEADED="$E2E_HEADED" \
E2E_SLOWMO="$E2E_SLOWMO" \
npx playwright test
