#!/usr/bin/env bash
# Build a white-label tenant app locally.
#   scripts/build-tenant.sh <tenant> <ios|android> [debug|release]
# debug   : prebuild + `expo run:<platform>` (simulator/emulator/device dev build)
# release : prebuild only; produce store binaries with EAS (see README):
#           TENANT=<tenant> eas build --platform <p> --profile production [--local]
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
echo ">> prebuild tenant=$TENANT platform=$PLATFORM"
npx expo prebuild --clean --platform "$PLATFORM"

if [[ "$MODE" == "debug" ]]; then
  npx expo run:"$PLATFORM" ${DEVICE:+--device "$DEVICE"}
else
  echo ">> native project generated. Release binaries: TENANT=$TENANT eas build --platform $PLATFORM --profile production"
fi
