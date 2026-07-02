#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SEXTANT_E2E_PYTHON:-/opt/homebrew/bin/python3}"
API_PORT="${SEXTANT_E2E_API_PORT:-8011}"
WEB_PORT="${SEXTANT_E2E_WEB_PORT:-5810}"
STATE_DIR="${SEXTANT_E2E_STATE_DIR:-$ROOT/.sextant/e2e}"

cd "$ROOT"
rm -rf "$STATE_DIR"
mkdir -p "$STATE_DIR"

export PYTHONPATH="$ROOT/backend/src"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$STATE_DIR/uv-cache}"
export SEXTANT_DATABASE_URL="sqlite+pysqlite:///$STATE_DIR/e2e.db"
export SEXTANT_OBJECT_STORE_ROOT="$STATE_DIR/objects"
export SEXTANT_CORS_ORIGINS="http://127.0.0.1:$WEB_PORT"
export SEXTANT_AUTH_MODE="header-dev"
export SEXTANT_WORKER_ID="e2e-worker"
export SEXTANT_WORKER_POLL_SECONDS="0.25"

uv run --python "$PYTHON_BIN" alembic upgrade head
SEXTANT_SEED_WORKBENCH_FIXED_IDS=1 \
  uv run --python "$PYTHON_BIN" python backend/scripts/seed_workbench.py \
  > "$STATE_DIR/workbench.env"

uv run --python "$PYTHON_BIN" python backend/scripts/worker_loop.py &
WORKER_PID="$!"

cleanup() {
  kill "$WORKER_PID" 2>/dev/null || true
}
trap cleanup EXIT

uv run --python "$PYTHON_BIN" uvicorn sextant.runtime:app --host 127.0.0.1 --port "$API_PORT"
