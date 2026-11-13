#!/usr/bin/env bash
# Build a white-label tenant app locally.
#   scripts/build-tenant.sh <tenant> <ios|android> [debug|release]
# debug   : prebuild + `expo run:<platform>` (simulator/emulator/device dev build)
# release : rejects local/non-https API hosts, then TENANT=<tenant> eas build --local --platform <p> --profile production
set -euo pipefail

TENANT="${1:-}"; PLATFORM="${2:-}"; MODE="${3:-debug}"
cd "$(dirname "$0")/.."

usage() { echo "usage: $0 <tenant> <ios|android> [debug|release]" >&2; exit 2; }
[[ -n "$TENANT" && -n "$PLATFORM" ]] || usage
[[ "$PLATFORM" == "ios" || "$PLATFORM" == "android" ]] || { echo "platform must be ios or android" >&2; usage; }
[[ "$MODE" == "debug" || "$MODE" == "release" ]] || { echo "mode must be debug or release" >&2; usage; }
[[ "$TENANT" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid tenant name: $TENANT" >&2; exit 2; }

DIR="tenants/$TENANT"
for f in tenant.json icon.png splash.png; do
  [[ -f "$DIR/$f" ]] || { echo "missing $DIR/$f (available: $(ls tenants | tr '\n' ' '))" >&2; exit 1; }
done

export TENANT

if [[ "$MODE" == "debug" ]]; then
  echo ">> prebuild tenant=$TENANT platform=$PLATFORM"
  npx expo prebuild --clean --platform "$PLATFORM"
  npx expo run:"$PLATFORM" ${DEVICE:+--device "$DEVICE"}
else
  # Release: refuse local API hosts, then build with EAS on this machine (needs EAS login + signing credentials).
  node -e '
    const { apiHost, isLocalHost } = require("./tenants/validate.js");
    const t = require("./tenants/" + process.argv[1] + "/tenant.json");
    if (isLocalHost(t.apiBaseUrl)) { console.error("release build refused: apiBaseUrl host is local (" + apiHost(t.apiBaseUrl) + ")"); process.exit(1); }
    if (!/^https:/.test(t.apiBaseUrl)) { console.error("release build refused: apiBaseUrl must be https"); process.exit(1); }
  ' "$TENANT"
  echo ">> EAS release build tenant=$TENANT platform=$PLATFORM"
  npx eas-cli build --local --platform "$PLATFORM" --profile production
fi
