#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SEXTANT_DEV_PYTHON:-/opt/homebrew/bin/python3}"
API_PORT="${SEXTANT_DEV_API_PORT:-8000}"
WEB_PORT="${SEXTANT_DEV_WEB_PORT:-5800}"
STATE_DIR="${SEXTANT_DEV_STATE_DIR:-$ROOT/.sextant/dev-workbench}"
PREPARE_ONLY=0

usage() {
  cat <<'EOF'
Usage: scripts/dev-workbench.sh [--prepare-only]

Starts a real local Sextant workbench runtime:
  - Alembic migrations
  - backend seed data
  - DB worker loop
  - FastAPI
  - Vite in API mode

Environment:
  SEXTANT_DATABASE_URL       Optional DB URL. Defaults to local SQLite state.
  SEXTANT_OBJECT_STORE_ROOT  Optional object-store root. Defaults under state.
  SEXTANT_DEV_API_PORT       FastAPI port. Defaults to 8000.
  SEXTANT_DEV_WEB_PORT       Vite port. Defaults to 5800.
  SEXTANT_DEV_STATE_DIR      Local runtime state dir.
  SEXTANT_DEV_RESET=1        Reset the default local SQLite state dir first.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prepare-only)
      PREPARE_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

using_default_database_url=0
if [[ -z "${SEXTANT_DATABASE_URL:-}" ]]; then
  using_default_database_url=1
  export SEXTANT_DATABASE_URL="sqlite+pysqlite:///$STATE_DIR/workbench.db"
fi

if [[ "${SEXTANT_DEV_RESET:-0}" == "1" ]]; then
  if [[ "$using_default_database_url" == "1" ]]; then
    rm -rf "$STATE_DIR"
  else
    echo "SEXTANT_DEV_RESET ignored for external SEXTANT_DATABASE_URL" >&2
  fi
fi

mkdir -p "$STATE_DIR"

cd "$ROOT"
export PYTHONPATH="$ROOT/backend/src"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$STATE_DIR/uv-cache}"
export SEXTANT_OBJECT_STORE_ROOT="${SEXTANT_OBJECT_STORE_ROOT:-$STATE_DIR/objects}"
export SEXTANT_CORS_ORIGINS="${SEXTANT_CORS_ORIGINS:-http://127.0.0.1:$WEB_PORT}"
export SEXTANT_AUTH_MODE="${SEXTANT_AUTH_MODE:-header-dev}"
export SEXTANT_WORKER_ID="${SEXTANT_WORKER_ID:-dev-workbench-worker}"
export SEXTANT_WORKER_POLL_SECONDS="${SEXTANT_WORKER_POLL_SECONDS:-0.25}"

seed_output="$STATE_DIR/workbench.seed.out"
vite_env="$STATE_DIR/workbench.vite.env"
health_output="$STATE_DIR/worker-health.json"

uv run --python "$PYTHON_BIN" alembic upgrade head
SEXTANT_SEED_WORKBENCH_FIXED_IDS="${SEXTANT_DEV_SEED_FIXED_IDS:-0}" \
  uv run --python "$PYTHON_BIN" python backend/scripts/seed_workbench.py \
  > "$seed_output"

{
  printf 'VITE_SEXTANT_API_BASE_URL=http://127.0.0.1:%s\n' "$API_PORT"
  grep '^VITE_SEXTANT_' "$seed_output"
  if [[ -n "${VITE_SEXTANT_BEARER_TOKEN:-}" ]]; then
    printf 'VITE_SEXTANT_BEARER_TOKEN=%s\n' "$VITE_SEXTANT_BEARER_TOKEN"
  fi
} > "$vite_env"

uv run --python "$PYTHON_BIN" python backend/scripts/worker_healthcheck.py > "$health_output"
if ! grep -q '"status": "pass"' "$health_output"; then
  cat "$health_output" >&2
  exit 1
fi

echo "Sextant dev workbench prepared"
echo "database: $SEXTANT_DATABASE_URL"
echo "object store: $SEXTANT_OBJECT_STORE_ROOT"
echo "vite env: $vite_env"
echo "worker healthcheck: pass"

if [[ "$PREPARE_ONLY" == "1" ]]; then
  exit 0
fi

set -a
# shellcheck disable=SC1090
. "$vite_env"
set +a

uv run --python "$PYTHON_BIN" python backend/scripts/worker_loop.py &
worker_pid="$!"
uv run --python "$PYTHON_BIN" uvicorn sextant.runtime:app --host 127.0.0.1 --port "$API_PORT" &
api_pid="$!"

cleanup() {
  kill "$worker_pid" "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "API: http://127.0.0.1:$API_PORT"
echo "Workbench: http://127.0.0.1:$WEB_PORT"
pnpm --dir web dev --host 127.0.0.1 --port "$WEB_PORT"
