#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required for the full stack." >&2
  echo "Use the SQLite host instructions in README.md when Docker is unavailable." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from safe local defaults; add OPENAI_API_KEY only for live AI analysis."
fi

echo "Warning: CodeReason is an unauthenticated local single-user MVP; keep ports 3000 and 8000 on loopback." >&2

docker compose build sandbox
docker compose up --build --remove-orphans
