#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SEXTANT_POSTGRES_SMOKE_PYTHON:-/opt/homebrew/bin/python3}"
RUNTIME="${SEXTANT_CONTAINER_RUNTIME:-}"
POSTGRES_IMAGE="${SEXTANT_POSTGRES_IMAGE:-postgres:16}"
POSTGRES_PORT="${SEXTANT_POSTGRES_PORT:-55432}"
POSTGRES_USER="${SEXTANT_POSTGRES_USER:-sextant}"
POSTGRES_PASSWORD="${SEXTANT_POSTGRES_PASSWORD:-sextant-smoke}"
POSTGRES_DB="${SEXTANT_POSTGRES_DB:-sextant}"
RESTORE_DB="${SEXTANT_POSTGRES_RESTORE_DB:-sextant_restore}"
STATE_DIR="${SEXTANT_POSTGRES_SMOKE_STATE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/sextant-postgres-smoke.XXXXXX")}"
CONTAINER_NAME="${SEXTANT_POSTGRES_CONTAINER_NAME:-sextant-postgres-smoke-$$}"
BACKUP_FILE="$STATE_DIR/sextant-backup.sql"
OBJECT_STORE_ROOT="$STATE_DIR/objects"
DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"

cleanup() {
  if [[ -n "${RUNTIME:-}" ]]; then
    "$RUNTIME" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  if [[ -z "${SEXTANT_POSTGRES_SMOKE_STATE_DIR:-}" ]]; then
    rm -rf "$STATE_DIR"
  fi
}
trap cleanup EXIT

if [[ -z "$RUNTIME" ]]; then
  if command -v docker >/dev/null 2>&1; then
    RUNTIME="docker"
  elif command -v podman >/dev/null 2>&1; then
    RUNTIME="podman"
  else
    echo "Postgres smoke requires docker or podman." >&2
    exit 1
  fi
fi

mkdir -p "$STATE_DIR" "$OBJECT_STORE_ROOT"

"$RUNTIME" run \
  --detach \
  --name "$CONTAINER_NAME" \
  --publish "127.0.0.1:$POSTGRES_PORT:5432" \
  --env "POSTGRES_USER=$POSTGRES_USER" \
  --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
  --env "POSTGRES_DB=$POSTGRES_DB" \
  "$POSTGRES_IMAGE" >/dev/null

POSTGRES_READY=0
for _ in $(seq 1 60); do
  if "$RUNTIME" exec "$CONTAINER_NAME" psql \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 \
    -At \
    -c "SELECT 1;" 2>/dev/null | grep -qx "1"; then
    POSTGRES_READY=1
    break
  fi
  sleep 1
done

if [[ "$POSTGRES_READY" != "1" ]]; then
  echo "Postgres did not become ready." >&2
  exit 1
fi

cd "$ROOT"
export SEXTANT_DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"
export SEXTANT_OBJECT_STORE_ROOT="$OBJECT_STORE_ROOT"
export SEXTANT_SMOKE_DATABASE_URL="$DATABASE_URL"
export SEXTANT_SMOKE_OBJECT_STORE_ROOT="$OBJECT_STORE_ROOT"
export SEXTANT_AUTH_MODE="header-dev"
export SEXTANT_LLM_PROVIDER="${SEXTANT_LLM_PROVIDER:-local}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$STATE_DIR/uv-cache}"

uv run --python "$PYTHON_BIN" alembic upgrade head
uv run --python "$PYTHON_BIN" python backend/scripts/production_smoke.py
uv run --python "$PYTHON_BIN" python backend/scripts/worker_healthcheck.py

"$RUNTIME" exec "$CONTAINER_NAME" pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-owner \
  --no-privileges \
  > "$BACKUP_FILE"

"$RUNTIME" exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres \
  -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS $RESTORE_DB WITH (FORCE);"
"$RUNTIME" exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d postgres \
  -v ON_ERROR_STOP=1 \
  -c "CREATE DATABASE $RESTORE_DB;"
"$RUNTIME" exec -i "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" \
  -v ON_ERROR_STOP=1 \
  < "$BACKUP_FILE" >/dev/null

RESTORED_SOURCE_DELTAS="$(
  "$RUNTIME" exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" \
    -At \
    -c "SELECT count(*) FROM source_deltas;"
)"
RESTORED_MEMORY_PAGES="$(
  "$RUNTIME" exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" \
    -At \
    -c "SELECT count(*) FROM memory_pages;"
)"
RESTORED_SOURCE_SPANS_WITH_RAW="$(
  "$RUNTIME" exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" \
    -At \
    -c "
      SELECT count(*)
      FROM source_spans restored_source_spans
      JOIN source_raw_sources restored_raw_sources
        ON restored_raw_sources.id = restored_source_spans.source_id
      JOIN source_versions restored_source_versions
        ON restored_source_versions.id = restored_source_spans.version_id
       AND restored_source_versions.source_id = restored_raw_sources.id
      WHERE restored_source_spans.text_preview IS NOT NULL
        AND restored_raw_sources.raw_text_ref IS NOT NULL;
    "
)"

if [[ "$RESTORED_SOURCE_DELTAS" -lt 1 || "$RESTORED_MEMORY_PAGES" -lt 1 ]]; then
  echo "Postgres restore smoke failed: expected restored SourceDelta and MemoryPage rows." >&2
  exit 1
fi

if [[ "$RESTORED_SOURCE_SPANS_WITH_RAW" -lt 1 ]]; then
  echo "Postgres restore smoke failed: expected restored SourceSpan -> RawSource resolution." >&2
  exit 1
fi

printf '{"status":"pass","database":"postgres","backup":"%s","restored_source_deltas":%s,"restored_memory_pages":%s,"restored_source_spans_with_raw":%s}\n' \
  "$BACKUP_FILE" \
  "$RESTORED_SOURCE_DELTAS" \
  "$RESTORED_MEMORY_PAGES" \
  "$RESTORED_SOURCE_SPANS_WITH_RAW"
