#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SEXTANT_REINDEX_SMOKE_PYTHON:-/opt/homebrew/bin/python3}"
RUNTIME="${SEXTANT_CONTAINER_RUNTIME:-}"
POSTGRES_IMAGE="${SEXTANT_REINDEX_POSTGRES_IMAGE:-postgres:16}"
POSTGRES_PORT="${SEXTANT_REINDEX_POSTGRES_PORT:-55434}"
POSTGRES_USER="${SEXTANT_REINDEX_POSTGRES_USER:-sextant}"
POSTGRES_PASSWORD="${SEXTANT_REINDEX_POSTGRES_PASSWORD:-sextant-reindex-smoke}"
POSTGRES_DB="${SEXTANT_REINDEX_POSTGRES_DB:-sextant}"
STATE_DIR="${SEXTANT_REINDEX_SMOKE_STATE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/sextant-reindex-smoke.XXXXXX")}"
CONTAINER_NAME="${SEXTANT_REINDEX_CONTAINER_NAME:-sextant-reindex-smoke-$$}"
OBJECT_STORE_ROOT="$STATE_DIR/objects"
DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"

cleanup() {
  if [[ -n "${RUNTIME:-}" ]]; then
    "$RUNTIME" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  if [[ -z "${SEXTANT_REINDEX_SMOKE_STATE_DIR:-}" ]]; then
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
    echo "SourceDelta reindex smoke requires docker or podman." >&2
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
  echo "SourceDelta reindex Postgres did not become ready." >&2
  exit 1
fi

cd "$ROOT"
export SEXTANT_DATABASE_URL="$DATABASE_URL"
export SEXTANT_OBJECT_STORE_ROOT="$OBJECT_STORE_ROOT"
export SEXTANT_AUTH_MODE="header-dev"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$STATE_DIR/uv-cache}"
export PYTHONPATH="${PYTHONPATH:-backend/src}"

uv run --python "$PYTHON_BIN" alembic upgrade head

SEED_OUTPUT="$(
  uv run --python "$PYTHON_BIN" python - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sextant.infra.db.models import Project, RawSource, SourceDeltaRecord, SourceVersion
from sextant.infra.object_store import LocalObjectStore

database_url = os.environ["SEXTANT_DATABASE_URL"]
object_store_root = Path(os.environ["SEXTANT_OBJECT_STORE_ROOT"])
engine = create_engine(database_url)
object_store = LocalObjectStore(object_store_root)
text_ref = object_store.put_text(
    "source-deltas/reindex-smoke.txt",
    "Mira keeps the Lantern Map inside the archive.",
)
project_id = uuid4()
source_id = uuid4()
version_id = uuid4()
delta_id = uuid4()

with Session(engine) as session:
    session.add(Project(id=project_id, name="SourceDelta Reindex Smoke"))
    session.add(
        RawSource(
            id=source_id,
            project_id=project_id,
            source_type="draft_manuscript",
            source_scope="user_draft",
            title="Chapter 1",
            ownership_status="owned",
            raw_text_ref=text_ref,
        )
    )
    session.commit()
    session.add(
        SourceVersion(
            id=version_id,
            source_id=source_id,
            version_label="v1",
            raw_hash="reindex-smoke-v1",
            raw_text_ref=text_ref,
        )
    )
    session.commit()
    session.add(
        SourceDeltaRecord(
            id=delta_id,
            project_id=project_id,
            source_id=source_id,
            previous_version_id=version_id,
            new_version_id=None,
            accepted_fragment_id=None,
            delta_kind="insert",
            range_start=0,
            range_end=0,
            base_hash="reindex-smoke-v1",
            submitted_text_ref=text_ref,
            submitted_text_search="",
            source_type="draft_manuscript",
            source_scope="user_draft",
            provenance={},
            status="memory_writeback_queued",
        )
    )
    session.commit()

print(json.dumps({"delta_id": str(delta_id), "text_ref": text_ref}, sort_keys=True))
PY
)"

uv run --python "$PYTHON_BIN" python backend/scripts/reindex_source_delta_search.py \
  --database-url "$DATABASE_URL" \
  --object-store-root "$OBJECT_STORE_ROOT" \
  --batch-size 1 >/tmp/sextant-source-delta-reindex-smoke-cli.out

uv run --python "$PYTHON_BIN" python - "$SEED_OUTPUT" <<'PY'
from __future__ import annotations

import json
import os
import sys
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sextant.infra.db.models import SourceDeltaRecord

seed = json.loads(sys.argv[1])
engine = create_engine(os.environ["SEXTANT_DATABASE_URL"])
with Session(engine) as session:
    delta = session.get(SourceDeltaRecord, UUID(seed["delta_id"]))
    if delta is None:
        raise SystemExit("Seeded SourceDelta was not found after reindex.")
    expected = "mira keeps the lantern map inside the archive."
    if delta.submitted_text_search != expected:
        raise SystemExit(
            "SourceDelta search text was not rebuilt from object storage: "
            f"{delta.submitted_text_search!r}"
        )
    print(
        json.dumps(
            {
                "status": "pass",
                "database": "postgres",
                "reindexed_rows": 1,
                "submitted_text_search": delta.submitted_text_search,
                "text_ref": seed["text_ref"],
            },
            sort_keys=True,
        )
    )
PY
