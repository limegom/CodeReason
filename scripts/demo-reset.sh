#!/usr/bin/env sh
set -eu

MODE=${1:-fixture}
case "$MODE" in
  fixture) PROVENANCE=FIXTURE ;;
  live) PROVENANCE=LIVE ;;
  *)
    echo "Usage: $0 [fixture|live]" >&2
    exit 2
    ;;
esac

API_BASE_URL=${API_BASE_URL:-http://localhost:8000/api}

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to reset demo data." >&2
  exit 1
fi

curl --fail-with-body --silent --show-error \
  --request POST \
  --header "Content-Type: application/json" \
  --data "{\"provenance\":\"$PROVENANCE\"}" \
  "$API_BASE_URL/demo/reset"
printf '\nDemo reset mode requested: %s (the JSON response above is authoritative).\n' "$PROVENANCE"
