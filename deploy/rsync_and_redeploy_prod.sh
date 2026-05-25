#!/usr/bin/env bash
set -euo pipefail

# Sync this repo to a VPS that is NOT a git checkout,
# then redeploy using docker-compose.prod.yml.
#
# Usage:
#   REMOTE_DIR=/root/erp-united-exploration ./deploy/rsync_and_redeploy_prod.sh
#
# Optional:
#   REMOTE_HOST=root@62.72.58.90 REMOTE_DIR=/root/erp-united-exploration ./deploy/rsync_and_redeploy_prod.sh
#   RUN_READONLY_SMOKE_TESTS=1 SMOKE_USERNAME='hr@x.com' SMOKE_PASSWORD='***' REMOTE_DIR=... ./deploy/rsync_and_redeploy_prod.sh

REMOTE_HOST="${REMOTE_HOST:-root@62.72.58.90}"
REMOTE_DIR="${REMOTE_DIR:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

RUN_SYSTEM_SEEDS="${RUN_SYSTEM_SEEDS:-0}"

RUN_READONLY_SMOKE_TESTS="${RUN_READONLY_SMOKE_TESTS:-0}"
RUN_CLIENT_DETAILS_SMOKE_TESTS="${RUN_CLIENT_DETAILS_SMOKE_TESTS:-0}"
SMOKE_USERNAME="${SMOKE_USERNAME:-}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-}"
SMOKE_BD_USERNAME="${SMOKE_BD_USERNAME:-}"
SMOKE_BD_PASSWORD="${SMOKE_BD_PASSWORD:-}"

escape_squotes() {
  # Escape single quotes for safe embedding in a single-quoted string.
  # shellcheck disable=SC1003
  printf "%s" "$1" | sed "s/'/'\\''/g"
}

if [[ -z "${REMOTE_DIR}" ]]; then
  echo "ERROR: Set REMOTE_DIR to the repo path on the VPS (example: /root/erp-united-exploration)" >&2
  exit 2
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "ERROR: rsync is required on your local machine" >&2
  exit 2
fi

echo "==> Syncing repo to ${REMOTE_HOST}:${REMOTE_DIR}"

# IMPORTANT: do not overwrite production secrets.
# .env lives in repo root on the VPS and should be managed on-server.
rsync -az --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude '**/.env' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'backend/__pycache__' \
  --exclude '**/__pycache__' \
  --exclude '**/.pytest_cache' \
  --exclude '**/.mypy_cache' \
  --exclude '**/.ruff_cache' \
  ./ "${REMOTE_HOST}:${REMOTE_DIR}/"

echo "==> Redeploying production stack on VPS"

remote_dir_escaped="$(escape_squotes "${REMOTE_DIR}")"
compose_file_escaped="$(escape_squotes "${COMPOSE_FILE}")"

remote_chain="cd '${remote_dir_escaped}' && test -f '${compose_file_escaped}' && chmod +x deploy/hostinger_prod_redeploy.sh"

remote_chain+=" && TAIL_LOGS=0 COMPOSE_FILE='${compose_file_escaped}'"

if [[ "${RUN_SYSTEM_SEEDS}" == "1" ]]; then
  remote_chain+=" RUN_SYSTEM_SEEDS=1"
fi

if [[ "${RUN_READONLY_SMOKE_TESTS}" == "1" ]]; then
  if [[ -z "${SMOKE_USERNAME}" || -z "${SMOKE_PASSWORD}" ]]; then
    echo "ERROR: Set SMOKE_USERNAME and SMOKE_PASSWORD when RUN_READONLY_SMOKE_TESTS=1" >&2
    exit 2
  fi
  smoke_user_escaped="$(escape_squotes "${SMOKE_USERNAME}")"
  smoke_pass_escaped="$(escape_squotes "${SMOKE_PASSWORD}")"
  remote_chain+=" RUN_READONLY_SMOKE_TESTS=1 SMOKE_USERNAME='${smoke_user_escaped}' SMOKE_PASSWORD='${smoke_pass_escaped}'"
fi

if [[ "${RUN_CLIENT_DETAILS_SMOKE_TESTS}" == "1" ]]; then
  if [[ -z "${SMOKE_USERNAME}" || -z "${SMOKE_PASSWORD}" ]]; then
    echo "ERROR: Set SMOKE_USERNAME and SMOKE_PASSWORD when RUN_CLIENT_DETAILS_SMOKE_TESTS=1" >&2
    exit 2
  fi
  smoke_user_escaped="$(escape_squotes "${SMOKE_USERNAME}")"
  smoke_pass_escaped="$(escape_squotes "${SMOKE_PASSWORD}")"
  smoke_bd_user_escaped="$(escape_squotes "${SMOKE_BD_USERNAME}")"
  smoke_bd_pass_escaped="$(escape_squotes "${SMOKE_BD_PASSWORD}")"
  remote_chain+=" RUN_CLIENT_DETAILS_SMOKE_TESTS=1 SMOKE_USERNAME='${smoke_user_escaped}' SMOKE_PASSWORD='${smoke_pass_escaped}' SMOKE_BD_USERNAME='${smoke_bd_user_escaped}' SMOKE_BD_PASSWORD='${smoke_bd_pass_escaped}'"
fi

remote_chain+=" ./deploy/hostinger_prod_redeploy.sh"

ssh "${REMOTE_HOST}" "${remote_chain}"
