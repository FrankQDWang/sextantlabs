from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from sextant.infra.db.models import MemoryPage, RawSource, SemanticEmbeddingRecord, SourceSpan
from sextant.ports.embedding import EmbeddingClient

SEMANTIC_RECALL_MIN_SCORE = 0.32
SEMANTIC_RECALL_LIMIT = 8


@dataclass(frozen=True, slots=True)
class SemanticRecallResult:
    ref_keys: set[str]
    source_span_ids: set[str]
    style_sample_source_span_ids: set[str]
    matches: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class SemanticSourceSpanRefreshBatch:
    refreshed: int
    source_span_ids: list[UUID]
    has_more: bool
    last_source_span_id: UUID | None


@dataclass(frozen=True, slots=True)
class SemanticMemoryPageRefreshBatch:
    refreshed: int
    memory_page_ids: list[UUID]
    has_more: bool
    last_memory_page_id: UUID | None


def refresh_project_semantic_embeddings(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
) -> dict[str, int]:
    return {
        "memory_page": refresh_memory_page_semantic_embeddings(
            session,
            project_id=project_id,
            embedding_client=embedding_client,
        ),
        "source_span": refresh_source_span_semantic_embeddings(
            session,
            project_id=project_id,
            embedding_client=embedding_client,
        ),
        "style_sample": refresh_style_sample_semantic_embeddings(
            session,
            project_id=project_id,
            embedding_client=embedding_client,
        ),
    }


def refresh_memory_page_semantic_embeddings(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
) -> int:
    return _refresh_memory_page_embeddings(
        session,
        project_id=project_id,
        pages=_project_memory_pages(session, project_id),
        embedding_client=embedding_client,
    )


def refresh_memory_page_semantic_embedding_batch(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
    limit: int,
    after_memory_page_id: UUID | None = None,
) -> SemanticMemoryPageRefreshBatch:
    pages = _project_memory_pages(
        session,
        project_id,
        after_memory_page_id=after_memory_page_id,
        limit=limit + 1,
    )
    batch = pages[:limit]
    refreshed = _refresh_memory_page_embeddings(
        session,
        project_id=project_id,
        pages=batch,
        embedding_client=embedding_client,
    )
    last_memory_page_id = batch[-1].id if batch else after_memory_page_id
    return SemanticMemoryPageRefreshBatch(
        refreshed=refreshed,
        memory_page_ids=[page.id for page in batch],
        has_more=len(pages) > limit,
        last_memory_page_id=last_memory_page_id,
    )


def _refresh_memory_page_embeddings(
    session: Session,
    *,
    project_id: UUID,
    pages: list[MemoryPage],
    embedding_client: EmbeddingClient,
) -> int:
    payloads = [
        (page, _memory_page_embedding_text(page))
        for page in pages
        if _ref_semantic_keys(cast(dict[str, object], page.target_ref))
    ]
    if not payloads:
        return 0

    vectors = embedding_client.embed_texts([text for _page, text in payloads])
    if len(vectors) != len(payloads):
        raise RuntimeError("Embedding provider returned a mismatched vector count.")

    refreshed = 0
    for (page, embedding_text), vector in zip(payloads, vectors, strict=True):
        normalized = _validated_vector(vector, embedding_client.dimensions)
        text_hash = _semantic_text_hash(embedding_text)
        _upsert_semantic_embedding(
            session,
            project_id=project_id,
            target_type="memory_page",
            target_id=page.id,
            target_ref=page.target_ref,
            text_hash=text_hash,
            embedding_client=embedding_client,
            vector=normalized,
            evidence_refs=_valid_page_source_span_refs(session, project_id, page),
        )
        refreshed += 1
    session.flush()
    return refreshed


def refresh_source_span_semantic_embeddings(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
) -> int:
    spans = _project_source_spans(session, project_id)
    payloads = [(span, _source_span_embedding_text(span)) for span in spans]
    return _refresh_source_span_target_embeddings(
        session,
        project_id=project_id,
        target_type="source_span",
        payloads=payloads,
        embedding_client=embedding_client,
    )


def refresh_style_sample_semantic_embeddings(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
) -> int:
    spans = _project_source_spans(session, project_id)
    payloads = [(span, _style_sample_embedding_text(span)) for span in spans]
    return _refresh_source_span_target_embeddings(
        session,
        project_id=project_id,
        target_type="style_sample",
        payloads=payloads,
        embedding_client=embedding_client,
    )


def refresh_source_span_semantic_embedding_batch(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
    limit: int,
    after_source_span_id: UUID | None = None,
) -> SemanticSourceSpanRefreshBatch:
    return _refresh_source_span_target_embedding_batch(
        session,
        project_id=project_id,
        target_type="source_span",
        embedding_client=embedding_client,
        limit=limit,
        after_source_span_id=after_source_span_id,
    )


def refresh_style_sample_semantic_embedding_batch(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
    limit: int,
    after_source_span_id: UUID | None = None,
) -> SemanticSourceSpanRefreshBatch:
    return _refresh_source_span_target_embedding_batch(
        session,
        project_id=project_id,
        target_type="style_sample",
        embedding_client=embedding_client,
        limit=limit,
        after_source_span_id=after_source_span_id,
    )


def semantic_ref_keys_for_text(
    session: Session,
    *,
    project_id: UUID,
    text: str,
    embedding_client: EmbeddingClient,
    min_score: float = SEMANTIC_RECALL_MIN_SCORE,
    limit: int = SEMANTIC_RECALL_LIMIT,
) -> SemanticRecallResult:
    if not text.strip():
        return SemanticRecallResult(
            ref_keys=set(),
            source_span_ids=set(),
            style_sample_source_span_ids=set(),
            matches=[],
        )
    query_vectors = embedding_client.embed_texts([text])
    if len(query_vectors) != 1:
        raise RuntimeError("Embedding provider returned a mismatched query vector count.")
    query_vector = _validated_vector(query_vectors[0], embedding_client.dimensions)
    ranked, ranker = _rank_semantic_embedding_records(
        session,
        project_id=project_id,
        embedding_client=embedding_client,
        query_vector=query_vector,
        min_score=min_score,
        limit=limit,
    )

    ref_keys: set[str] = set()
    source_span_ids: set[str] = set()
    style_sample_source_span_ids: set[str] = set()
    matches: list[dict[str, object]] = []
    for score, record in ranked:
        keys = _ref_semantic_keys(cast(dict[str, object], record.target_ref))
        ref_keys.update(keys)
        if record.target_type == "source_span":
            source_span_ids.add(str(record.target_id))
        elif record.target_type == "style_sample":
            style_sample_source_span_ids.add(str(record.target_id))
        matches.append(
            {
                "target_type": record.target_type,
                "target_id": str(record.target_id),
                "ref_keys": sorted(keys),
                "score": round(score, 6),
                "ranker": ranker,
            }
        )
    return SemanticRecallResult(
        ref_keys=ref_keys,
        source_span_ids=source_span_ids,
        style_sample_source_span_ids=style_sample_source_span_ids,
        matches=matches,
    )


def _refresh_source_span_target_embeddings(
    session: Session,
    *,
    project_id: UUID,
    target_type: str,
    payloads: list[tuple[SourceSpan, str]],
    embedding_client: EmbeddingClient,
) -> int:
    if not payloads:
        return 0

    vectors = embedding_client.embed_texts([text for _span, text in payloads])
    if len(vectors) != len(payloads):
        raise RuntimeError("Embedding provider returned a mismatched vector count.")

    refreshed = 0
    for (span, embedding_text), vector in zip(payloads, vectors, strict=True):
        _upsert_semantic_embedding(
            session,
            project_id=project_id,
            target_type=target_type,
            target_id=span.id,
            target_ref=_source_span_target_ref(span, target_type),
            text_hash=_semantic_text_hash(embedding_text),
            embedding_client=embedding_client,
            vector=_validated_vector(vector, embedding_client.dimensions),
            evidence_refs=[{"type": "source_span", "id": str(span.id)}],
        )
        refreshed += 1
    session.flush()
    return refreshed


def _refresh_source_span_target_embedding_batch(
    session: Session,
    *,
    project_id: UUID,
    target_type: str,
    embedding_client: EmbeddingClient,
    limit: int,
    after_source_span_id: UUID | None,
) -> SemanticSourceSpanRefreshBatch:
    spans = _project_source_spans(
        session,
        project_id,
        after_source_span_id=after_source_span_id,
        limit=limit + 1,
    )
    batch = spans[:limit]
    refreshed = _refresh_source_span_target_embeddings(
        session,
        project_id=project_id,
        target_type=target_type,
        payloads=[
            (
                span,
                _source_span_embedding_text(span)
                if target_type == "source_span"
                else _style_sample_embedding_text(span),
            )
            for span in batch
        ],
        embedding_client=embedding_client,
    )
    last_source_span_id = batch[-1].id if batch else after_source_span_id
    return SemanticSourceSpanRefreshBatch(
        refreshed=refreshed,
        source_span_ids=[span.id for span in batch],
        has_more=len(spans) > limit,
        last_source_span_id=last_source_span_id,
    )


def _upsert_semantic_embedding(
    session: Session,
    *,
    project_id: UUID,
    target_type: str,
    target_id: UUID,
    target_ref: dict[str, object],
    text_hash: str,
    embedding_client: EmbeddingClient,
    vector: list[float],
    evidence_refs: list[dict[str, object]],
) -> None:
    existing = (
        session.query(SemanticEmbeddingRecord)
        .filter_by(
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            provider=embedding_client.provider_name,
            model_name=embedding_client.model_name,
        )
        .one_or_none()
    )
    if existing is None:
        record = SemanticEmbeddingRecord(
            id=uuid4(),
            project_id=project_id,
            target_type=target_type,
            target_id=target_id,
            target_ref=target_ref,
            text_hash=text_hash,
            provider=embedding_client.provider_name,
            model_name=embedding_client.model_name,
            dimensions=embedding_client.dimensions,
            vector=vector,
            evidence_refs=evidence_refs,
        )
        session.add(record)
        session.flush()
        _sync_pgvector_embedding(session, record_id=record.id, vector=vector)
        return

    existing.target_ref = target_ref
    existing.text_hash = text_hash
    existing.dimensions = embedding_client.dimensions
    existing.vector = vector
    existing.evidence_refs = evidence_refs
    session.flush()
    _sync_pgvector_embedding(session, record_id=existing.id, vector=vector)


def _rank_semantic_embedding_records(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
    query_vector: list[float],
    min_score: float,
    limit: int,
) -> tuple[list[tuple[float, SemanticEmbeddingRecord]], str]:
    pgvector_ranked = _pgvector_ranked_embedding_records(
        session,
        project_id=project_id,
        embedding_client=embedding_client,
        query_vector=query_vector,
        min_score=min_score,
        limit=limit,
    )
    if pgvector_ranked is not None:
        return pgvector_ranked, "pgvector"

    records = (
        session.query(SemanticEmbeddingRecord)
        .filter_by(
            project_id=project_id,
            provider=embedding_client.provider_name,
            model_name=embedding_client.model_name,
            dimensions=embedding_client.dimensions,
        )
        .all()
    )
    ranked: list[tuple[float, SemanticEmbeddingRecord]] = []
    for record in records:
        score = _cosine_similarity(
            query_vector, _validated_vector(record.vector, record.dimensions)
        )
        if score >= min_score:
            ranked.append((score, record))
    ranked.sort(key=lambda item: (-item[0], item[1].target_type, str(item[1].target_id)))
    return ranked[:limit], "json"


def _pgvector_ranked_embedding_records(
    session: Session,
    *,
    project_id: UUID,
    embedding_client: EmbeddingClient,
    query_vector: list[float],
    min_score: float,
    limit: int,
) -> list[tuple[float, SemanticEmbeddingRecord]] | None:
    if not _pgvector_semantic_index_ready(session):
        return None

    vector_type = _pgvector_type_name(embedding_client.dimensions)
    rows = session.execute(
        text(
            f"""
            SELECT
              id,
              1 - (
                embedding_vector::{vector_type} <=> CAST(:query_vector AS {vector_type})
              ) AS score
            FROM semantic_embeddings
            WHERE project_id = :project_id
              AND provider = :provider
              AND model_name = :model_name
              AND dimensions = :dimensions
              AND embedding_vector IS NOT NULL
            ORDER BY embedding_vector::{vector_type} <=> CAST(:query_vector AS {vector_type}),
                     target_type,
                     target_id::text
            LIMIT :limit
            """
        ),
        {
            "project_id": project_id,
            "provider": embedding_client.provider_name,
            "model_name": embedding_client.model_name,
            "dimensions": embedding_client.dimensions,
            "query_vector": _pgvector_literal(query_vector),
            "limit": limit,
        },
    ).all()
    if not rows:
        return []

    ordered_ids = [row.id for row in rows if float(row.score) >= min_score]
    if not ordered_ids:
        return []
    records_by_id = {
        record.id: record
        for record in session.query(SemanticEmbeddingRecord)
        .filter(SemanticEmbeddingRecord.id.in_(ordered_ids))
        .all()
    }
    ranked: list[tuple[float, SemanticEmbeddingRecord]] = []
    for row in rows:
        score = float(row.score)
        if score < min_score:
            continue
        record = records_by_id.get(row.id)
        if record is not None:
            ranked.append((score, record))
    return ranked


def _sync_pgvector_embedding(
    session: Session,
    *,
    record_id: UUID,
    vector: list[float],
) -> None:
    if not _pgvector_semantic_storage_ready(session):
        return
    session.execute(
        text(
            """
            UPDATE semantic_embeddings
            SET embedding_vector = CAST(:embedding_vector AS vector)
            WHERE id = :record_id
            """
        ),
        {
            "embedding_vector": _pgvector_literal(vector),
            "record_id": record_id,
        },
    )


def _pgvector_semantic_storage_ready(session: Session) -> bool:
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return False

    cache_key = "sextant_pgvector_semantic_storage_ready"
    cached = session.info.get(cache_key)
    if isinstance(cached, bool):
        return cached

    try:
        ready = bool(
            session.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_schema = current_schema()
                        AND table_name = 'semantic_embeddings'
                        AND column_name = 'embedding_vector'
                    )
                    AND EXISTS (
                      SELECT 1
                      FROM pg_extension
                      WHERE extname = 'vector'
                    )
                    """
                )
            ).scalar()
        )
    except SQLAlchemyError:
        ready = False
    session.info[cache_key] = ready
    return ready


def _pgvector_semantic_index_ready(session: Session) -> bool:
    if not _pgvector_semantic_storage_ready(session):
        return False

    cache_key = "sextant_pgvector_semantic_index_ready"
    cached = session.info.get(cache_key)
    if isinstance(cached, bool):
        return cached

    try:
        ready = bool(
            session.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1
                      FROM information_schema.columns
                      WHERE table_schema = current_schema()
                        AND table_name = 'semantic_embeddings'
                        AND column_name = 'embedding_vector'
                    )
                    AND EXISTS (
                      SELECT 1
                      FROM pg_indexes
                      WHERE schemaname = current_schema()
                        AND tablename = 'semantic_embeddings'
                        AND indexname = 'ix_semantic_embeddings_embedding_vector_hnsw'
                    )
                    """
                )
            ).scalar()
        )
    except SQLAlchemyError:
        ready = False
    session.info[cache_key] = ready
    return ready


def _pgvector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in vector) + "]"


def _pgvector_type_name(dimensions: int) -> str:
    if dimensions <= 0:
        raise RuntimeError("Embedding dimensions must be positive for pgvector retrieval.")
    return f"vector({dimensions})"


def _memory_page_embedding_text(page: MemoryPage) -> str:
    payload = {
        "title": page.title,
        "target_ref": page.target_ref,
        "current_canon": page.current_canon,
        "appearance_log": page.appearance_log,
        "event_log": page.event_log,
        "relationships": page.relationships,
        "open_threads": page.open_threads,
        "contradictions": page.contradictions,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _project_memory_pages(
    session: Session,
    project_id: UUID,
    *,
    after_memory_page_id: UUID | None = None,
    limit: int | None = None,
) -> list[MemoryPage]:
    query = (
        session.query(MemoryPage)
        .filter_by(project_id=project_id)
        .filter(MemoryPage.canon_status.in_(("current", "rebuilt")))
    )
    if after_memory_page_id is not None:
        after_page = session.get(MemoryPage, after_memory_page_id)
        if after_page is None or after_page.project_id != project_id:
            raise RuntimeError("after_memory_page_id does not belong to the project.")
        query = query.filter(MemoryPage.id > after_page.id)
    query = query.order_by(MemoryPage.id)
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def _project_source_spans(
    session: Session,
    project_id: UUID,
    *,
    after_source_span_id: UUID | None = None,
    limit: int | None = None,
) -> list[SourceSpan]:
    source_ids = [
        source_id
        for (source_id,) in session.query(RawSource.id).filter_by(project_id=project_id).all()
    ]
    if not source_ids:
        return []
    query = session.query(SourceSpan).filter(SourceSpan.source_id.in_(source_ids))
    if after_source_span_id is not None:
        after_span = session.get(SourceSpan, after_source_span_id)
        if after_span is None or after_span.source_id not in source_ids:
            raise RuntimeError("after_source_span_id does not belong to the project.")
        query = query.filter(
            or_(
                SourceSpan.source_id > after_span.source_id,
                and_(
                    SourceSpan.source_id == after_span.source_id,
                    SourceSpan.start_offset > after_span.start_offset,
                ),
                and_(
                    SourceSpan.source_id == after_span.source_id,
                    SourceSpan.start_offset == after_span.start_offset,
                    SourceSpan.id > after_span.id,
                ),
            )
        )
    query = query.order_by(SourceSpan.source_id, SourceSpan.start_offset, SourceSpan.id)
    if limit is not None:
        query = query.limit(limit)
    return list(query.all())


def _source_span_embedding_text(span: SourceSpan) -> str:
    payload = {
        "text_preview": span.text_preview,
        "narration_layer": span.narration_layer,
        "source_id": str(span.source_id),
        "version_id": str(span.version_id),
        "scene_id": str(span.scene_id) if span.scene_id else None,
        "chapter_id": str(span.chapter_id) if span.chapter_id else None,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _style_sample_embedding_text(span: SourceSpan) -> str:
    payload = {
        "style_sample": span.text_preview,
        "narration_layer": span.narration_layer,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_span_target_ref(span: SourceSpan, target_type: str) -> dict[str, object]:
    return {
        "type": target_type,
        "id": str(span.id),
        "source_span_id": str(span.id),
        "source_id": str(span.source_id),
        "version_id": str(span.version_id),
        "scene_id": str(span.scene_id) if span.scene_id else None,
        "chapter_id": str(span.chapter_id) if span.chapter_id else None,
    }


def _valid_page_source_span_refs(
    session: Session,
    project_id: UUID,
    page: MemoryPage,
) -> list[dict[str, object]]:
    span_ids: list[UUID] = []
    for ref in page.source_refs:
        if not isinstance(ref, dict) or ref.get("type") != "source_span":
            continue
        try:
            span_ids.append(UUID(str(ref.get("id"))))
        except ValueError:
            continue
    if not span_ids:
        return []
    source_ids = [
        source_id
        for (source_id,) in session.query(RawSource.id).filter_by(project_id=project_id).all()
    ]
    if not source_ids:
        return []
    rows = (
        session.query(SourceSpan.id)
        .filter(SourceSpan.id.in_(span_ids))
        .filter(SourceSpan.source_id.in_(source_ids))
        .all()
    )
    valid_ids = {str(span_id) for (span_id,) in rows}
    return [
        {"type": "source_span", "id": str(span_id)}
        for span_id in span_ids
        if str(span_id) in valid_ids
    ]


def _validated_vector(vector: object, dimensions: int) -> list[float]:
    if not isinstance(vector, list) or len(vector) != dimensions:
        raise RuntimeError("Embedding vector dimensions do not match provider metadata.")
    values: list[float] = []
    for value in vector:
        if not isinstance(value, int | float):
            raise RuntimeError("Embedding vectors must contain numeric values.")
        values.append(float(value))
    return values


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _semantic_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ref_semantic_keys(ref: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for key in ("id", "canonical_entity_id"):
        value = ref.get(key)
        if value is not None:
            keys.add(str(value).casefold())
    return keys
