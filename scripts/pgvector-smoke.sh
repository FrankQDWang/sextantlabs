#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${SEXTANT_PGVECTOR_SMOKE_PYTHON:-/opt/homebrew/bin/python3}"
RUNTIME="${SEXTANT_CONTAINER_RUNTIME:-}"
PGVECTOR_IMAGE="${SEXTANT_PGVECTOR_IMAGE:-pgvector/pgvector:pg17}"
POSTGRES_PORT="${SEXTANT_PGVECTOR_POSTGRES_PORT:-55433}"
POSTGRES_USER="${SEXTANT_PGVECTOR_POSTGRES_USER:-sextant}"
POSTGRES_PASSWORD="${SEXTANT_PGVECTOR_POSTGRES_PASSWORD:-sextant-pgvector-smoke}"
POSTGRES_DB="${SEXTANT_PGVECTOR_POSTGRES_DB:-sextant}"
STATE_DIR="${SEXTANT_PGVECTOR_SMOKE_STATE_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/sextant-pgvector-smoke.XXXXXX")}"
CONTAINER_NAME="${SEXTANT_PGVECTOR_CONTAINER_NAME:-sextant-pgvector-smoke-$$}"
OBJECT_STORE_ROOT="$STATE_DIR/objects"

cleanup() {
  if [[ -n "${RUNTIME:-}" ]]; then
    "$RUNTIME" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  if [[ -z "${SEXTANT_PGVECTOR_SMOKE_STATE_DIR:-}" ]]; then
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
    echo "pgvector smoke requires docker or podman." >&2
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
  "$PGVECTOR_IMAGE" >/dev/null

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
  echo "pgvector Postgres did not become ready." >&2
  exit 1
fi

"$RUNTIME" exec "$CONTAINER_NAME" psql \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null

cd "$ROOT"
export SEXTANT_DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$POSTGRES_PORT/$POSTGRES_DB"
export SEXTANT_OBJECT_STORE_ROOT="$OBJECT_STORE_ROOT"
export SEXTANT_AUTH_MODE="header-dev"
export SEXTANT_LLM_PROVIDER="${SEXTANT_LLM_PROVIDER:-local}"
export SEXTANT_EMBEDDING_PROVIDER="${SEXTANT_EMBEDDING_PROVIDER:-local}"
export SEXTANT_VECTOR_INDEX_PROVIDER="${SEXTANT_VECTOR_INDEX_PROVIDER:-pgvector}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$STATE_DIR/uv-cache}"
export PYTHONPATH="${PYTHONPATH:-backend/src}"

uv run --python "$PYTHON_BIN" alembic upgrade head

uv run --python "$PYTHON_BIN" python - <<'PY'
from __future__ import annotations

import json
import os
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from sextant.application.use_cases import AnswerWithEvidence
from sextant.contracts.use_cases import MemoryAnswerInput
from sextant.infra.db.models import (
    MemoryPage,
    Project,
    ProjectMembership,
    RawSource,
    SemanticEmbeddingRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
)
from sextant.infra.semantic_search import (
    refresh_project_semantic_embeddings,
    semantic_ref_keys_for_text,
)
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.skills.local_embedding import LocalEmbeddingProvider

database_url = os.environ["SEXTANT_DATABASE_URL"]
engine = create_engine(database_url)
embedding_provider = LocalEmbeddingProvider()

with Session(engine) as session:
    project = Project(id=uuid4(), name="Pgvector Smoke")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
    source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 1",
        ownership_status="owned",
        raw_text_ref="object://raw/pgvector-smoke",
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=source.id,
        version_label="v1",
        raw_hash="pgvector-smoke-v1",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/pgvector-smoke",
        raw_offset_map_ref="object://offsets/pgvector-smoke",
        view_status="current",
    )
    relevant_span = SourceSpan(
        id=uuid4(),
        source_id=source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=64,
        raw_start_offset=0,
        raw_end_offset=64,
        text_preview="Secret informant secret informant must remain unnamed.",
        narration_layer="narrator",
    )
    unrelated_span = SourceSpan(
        id=uuid4(),
        source_id=source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=80,
        end_offset=130,
        raw_start_offset=80,
        raw_end_offset=130,
        text_preview="Inventory ledger count rests near quay.",
        narration_layer="narrator",
    )
    mira_id = UUID("00000000-0000-4000-8000-0000000000aa")
    mira_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira_id),
            "label": "Mira",
            "canonical_entity_id": str(mira_id),
        },
        title="Mira dossier",
        current_canon={"role_note": "Secret informant secret informant must remain unnamed."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "informant-thread",
                "summary": "Secret informant secret informant must remain unnamed.",
                "source_span_ids": [str(relevant_span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(relevant_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="object",
        target_ref={"type": "object", "id": "ledger-count", "label": "Ledger Count"},
        title="Ledger Count",
        current_canon={"state": "Inventory ledger count rests near quay."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "inventory-thread",
                "summary": "Inventory ledger count rests near quay.",
                "source_span_ids": [str(unrelated_span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(unrelated_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([project, membership, source])
    session.commit()
    session.add(version)
    session.commit()
    session.add(view)
    session.commit()
    session.add_all([relevant_span, unrelated_span])
    session.commit()
    session.add_all([mira_page, unrelated_page])
    session.commit()

    refreshed = refresh_project_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    session.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_semantic_embeddings_embedding_vector_hnsw
            ON semantic_embeddings
            USING hnsw ((embedding_vector::vector(32)) vector_cosine_ops)
            WHERE dimensions = 32 AND embedding_vector IS NOT NULL
            """
        )
    )
    session.commit()
    session.info.pop("sextant_pgvector_semantic_index_ready", None)

    vector_rows = session.execute(
        text("SELECT count(*) FROM semantic_embeddings WHERE embedding_vector IS NOT NULL")
    ).scalar_one()
    hnsw_index = session.execute(
        text(
            """
            SELECT count(*)
            FROM pg_indexes
            WHERE tablename = 'semantic_embeddings'
              AND indexname = 'ix_semantic_embeddings_embedding_vector_hnsw'
            """
        )
    ).scalar_one()
    ranked_probe = session.execute(
        text(
            """
            SELECT id
            FROM semantic_embeddings
            WHERE embedding_vector IS NOT NULL
            ORDER BY embedding_vector::vector(32) <=> CAST(:query_vector AS vector(32))
            LIMIT 1
            """
        ),
        {"query_vector": "[1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]"},
    ).first()
    if vector_rows < 1 or hnsw_index != 1 or ranked_probe is None:
        raise SystemExit("pgvector semantic index was not materialized.")

    recall = semantic_ref_keys_for_text(
        session,
        project_id=project.id,
        text="open thread clandestine contact",
        embedding_client=embedding_provider,
    )
    if not recall.matches or recall.matches[0].get("ranker") != "pgvector":
        raise SystemExit("semantic_ref_keys_for_text did not use pgvector ranking.")

    answer = AnswerWithEvidence(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-pgvector-semantic-recall",
            idempotency_key="idem-pgvector-semantic-recall",
            question="open thread clandestine contact",
        )
    )
    if answer.answer_type != "open_thread" or str(relevant_span.id) not in {
        str(ref.get("id")) for ref in answer.source_span_refs
    }:
        raise SystemExit("MemoryAnswer did not use pgvector-backed semantic recall.")
    if "Inventory ledger count" in answer.answer:
        raise SystemExit("pgvector semantic recall returned the unrelated open thread.")

    total_embeddings = session.query(SemanticEmbeddingRecord).count()
    print(
        json.dumps(
            {
                "status": "pass",
                "pgvector_semantic_recall": True,
                "refreshed": refreshed,
                "embedding_rows": total_embeddings,
                "embedding_vector_rows": vector_rows,
                "hnsw_index": "ix_semantic_embeddings_embedding_vector_hnsw",
                "ranker": recall.matches[0]["ranker"],
                "answer_type": answer.answer_type,
                "source_span_refs": len(answer.source_span_refs),
            },
            sort_keys=True,
        )
    )
PY
