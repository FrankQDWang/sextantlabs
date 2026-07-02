from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.infra.db.models import JobRecord
from sextant.infra.semantic_search import (
    refresh_memory_page_semantic_embedding_batch,
    refresh_source_span_semantic_embedding_batch,
    refresh_style_sample_semantic_embedding_batch,
)
from sextant.infra.worker import TerminalJobError
from sextant.ports.embedding import EmbeddingClient

PIPELINE_VERSION = "pipeline-v1"
DEFAULT_MEMORY_PAGE_BATCH_SIZE = 100
MEMORY_PAGE_BATCH_SIZE_LIMIT = 1000
DEFAULT_SOURCE_SPAN_BATCH_SIZE = 100
SOURCE_SPAN_BATCH_SIZE_LIMIT = 1000


class SemanticIndexRefreshHandler:
    def __init__(self, embedding_client: EmbeddingClient) -> None:
        self._embedding_client = embedding_client

    def __call__(self, session: Session, job: JobRecord) -> None:
        memory_page_batch_size = _memory_page_batch_size(job)
        source_span_batch_size = _source_span_batch_size(job)
        after_memory_page_id = _optional_payload_uuid(job, "after_memory_page_id")
        after_source_span_id = _optional_payload_uuid(job, "after_source_span_id")
        if job.payload.get("skip_memory_pages") is not True:
            try:
                memory_result = refresh_memory_page_semantic_embedding_batch(
                    session,
                    project_id=job.project_id,
                    embedding_client=self._embedding_client,
                    limit=memory_page_batch_size,
                    after_memory_page_id=after_memory_page_id,
                )
            except RuntimeError as exc:
                raise TerminalJobError(str(exc)) from exc
            if memory_result.has_more and memory_result.last_memory_page_id is not None:
                _enqueue_semantic_index_memory_page_continuation(
                    session,
                    job=job,
                    memory_page_batch_size=memory_page_batch_size,
                    source_span_batch_size=source_span_batch_size,
                    after_memory_page_id=memory_result.last_memory_page_id,
                )
                return
        try:
            source_result = refresh_source_span_semantic_embedding_batch(
                session,
                project_id=job.project_id,
                embedding_client=self._embedding_client,
                limit=source_span_batch_size,
                after_source_span_id=after_source_span_id,
            )
            style_result = refresh_style_sample_semantic_embedding_batch(
                session,
                project_id=job.project_id,
                embedding_client=self._embedding_client,
                limit=source_span_batch_size,
                after_source_span_id=after_source_span_id,
            )
        except RuntimeError as exc:
            raise TerminalJobError(str(exc)) from exc
        if source_result.source_span_ids != style_result.source_span_ids:
            raise TerminalJobError("Semantic source/style refresh batches diverged.")
        if source_result.has_more and source_result.last_source_span_id is not None:
            _enqueue_semantic_index_continuation(
                session,
                job=job,
                batch_size=source_span_batch_size,
                after_source_span_id=source_result.last_source_span_id,
            )


def _enqueue_semantic_index_memory_page_continuation(
    session: Session,
    *,
    job: JobRecord,
    memory_page_batch_size: int,
    source_span_batch_size: int,
    after_memory_page_id: UUID,
) -> None:
    idempotency_key = (
        f"{job.project_id}:refresh_semantic_index:memory_page:"
        f"{job.payload.get('pipeline_version', PIPELINE_VERSION)}:"
        f"{after_memory_page_id}:{memory_page_batch_size}:{source_span_batch_size}"
    )
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == job.project_id)
        .where(JobRecord.job_type == "refresh_semantic_index")
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="refresh_semantic_index",
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": "refresh_semantic_index",
                "pipeline_version": job.payload.get("pipeline_version", PIPELINE_VERSION),
                "trigger": "refresh_semantic_index_memory_page_backpressure",
                "continues_job_id": str(job.id),
                "memory_page_batch_size": memory_page_batch_size,
                "source_span_batch_size": source_span_batch_size,
                "after_memory_page_id": str(after_memory_page_id),
            },
        )
    )


def _enqueue_semantic_index_continuation(
    session: Session,
    *,
    job: JobRecord,
    batch_size: int,
    after_source_span_id: UUID,
) -> None:
    idempotency_key = (
        f"{job.project_id}:refresh_semantic_index:"
        f"{job.payload.get('pipeline_version', PIPELINE_VERSION)}:"
        f"{after_source_span_id}:{batch_size}"
    )
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == job.project_id)
        .where(JobRecord.job_type == "refresh_semantic_index")
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="refresh_semantic_index",
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": "refresh_semantic_index",
                "pipeline_version": job.payload.get("pipeline_version", PIPELINE_VERSION),
                "trigger": "refresh_semantic_index_backpressure",
                "continues_job_id": str(job.id),
                "source_span_batch_size": batch_size,
                "after_source_span_id": str(after_source_span_id),
                "skip_memory_pages": True,
            },
        )
    )


def _memory_page_batch_size(job: JobRecord) -> int:
    value = job.payload.get("memory_page_batch_size")
    if value is None:
        return DEFAULT_MEMORY_PAGE_BATCH_SIZE
    if not isinstance(value, int) or isinstance(value, bool):
        raise TerminalJobError("memory_page_batch_size must be a positive integer.")
    if value <= 0 or value > MEMORY_PAGE_BATCH_SIZE_LIMIT:
        raise TerminalJobError(
            f"memory_page_batch_size must be between 1 and {MEMORY_PAGE_BATCH_SIZE_LIMIT}."
        )
    return value


def _source_span_batch_size(job: JobRecord) -> int:
    value = job.payload.get("source_span_batch_size")
    if value is None:
        return DEFAULT_SOURCE_SPAN_BATCH_SIZE
    if not isinstance(value, int) or isinstance(value, bool):
        raise TerminalJobError("source_span_batch_size must be a positive integer.")
    if value <= 0 or value > SOURCE_SPAN_BATCH_SIZE_LIMIT:
        raise TerminalJobError(
            f"source_span_batch_size must be between 1 and {SOURCE_SPAN_BATCH_SIZE_LIMIT}."
        )
    return value


def _optional_payload_uuid(job: JobRecord, key: str) -> UUID | None:
    value = job.payload.get(key)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload requires {key} to be a UUID") from exc
