from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.infra.db.models import (
    AuditEvent,
    JobRecord,
    RawSource,
    SourceProcessedView,
    SourceVersion,
)
from sextant.infra.worker import TerminalJobError
from sextant.ports.object_store import ObjectStore

PIPELINE_VERSION = "pipeline-v1"
STRUCTURE_PARSER_VERSION = "structure-parser-v1"


@dataclass(frozen=True, slots=True)
class NormalizedSourceView:
    view: SourceProcessedView
    created: bool
    replaced_view_id: UUID | None


class SourceNormalizationHandler:
    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        source_version_id = _payload_uuid(job, "source_version_id")
        cleaning_profile = _payload_text(job, "cleaning_profile")
        version = session.get(SourceVersion, source_version_id)
        if version is None:
            raise TerminalJobError("SourceVersion was not found for normalization.")
        text = source_version_text(session, self._object_store, version)
        normalized = ensure_processed_view(
            session,
            self._object_store,
            version=version,
            text=text,
            cleaning_profile=cleaning_profile,
        )
        session.add(
            AuditEvent(
                id=uuid4(),
                project_id=job.project_id,
                request_id=f"job:{job.id}",
                actor_id=None,
                event_type="source.normalized",
                subject_ref={"type": "source_version", "id": str(version.id)},
                decision={
                    "source_version_id": str(version.id),
                    "view_id": str(normalized.view.id),
                    "cleaning_profile": cleaning_profile,
                    "created": normalized.created,
                    "replaced_view_id": (
                        str(normalized.replaced_view_id)
                        if normalized.replaced_view_id is not None
                        else None
                    ),
                },
            )
        )
        _enqueue_structure_split_job(session, job, normalized.view)
        session.flush()


def ensure_processed_view(
    session: Session,
    object_store: ObjectStore,
    *,
    version: SourceVersion,
    text: str,
    cleaning_profile: str,
) -> NormalizedSourceView:
    current_view = session.scalars(
        select(SourceProcessedView)
        .where(SourceProcessedView.version_id == version.id)
        .where(SourceProcessedView.view_status == "current")
    ).first()
    if current_view is not None and current_view.cleaning_profile == cleaning_profile:
        return NormalizedSourceView(view=current_view, created=False, replaced_view_id=None)

    replaced_view_id = None
    if current_view is not None:
        current_view.view_status = "stale"
        replaced_view_id = current_view.id

    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile=cleaning_profile,
        markdown_ref=object_store.put_text(
            f"processed/{version.id}.{cleaning_profile}.md",
            text,
        ),
        raw_offset_map_ref=object_store.put_text(
            f"processed/{version.id}.{cleaning_profile}.offsets.json",
            json.dumps({"spans": [{"processed": [0, len(text)], "raw": [0, len(text)]}]}),
        ),
        view_status="current",
    )
    session.add(view)
    session.flush()
    return NormalizedSourceView(view=view, created=True, replaced_view_id=replaced_view_id)


def source_version_text(
    session: Session,
    object_store: ObjectStore,
    version: SourceVersion,
) -> str:
    text_ref = version.raw_text_ref
    if text_ref is None:
        raw_source = session.get(RawSource, version.source_id)
        if raw_source is None:
            raise TerminalJobError("RawSource was not found for normalization.")
        text_ref = raw_source.raw_text_ref
    text = object_store.get_text(text_ref)
    if not text:
        raise TerminalJobError("SourceVersion text is empty for normalization.")
    return text


def _enqueue_structure_split_job(
    session: Session,
    job: JobRecord,
    view: SourceProcessedView,
) -> None:
    idempotency_key = f"{view.id}:{STRUCTURE_PARSER_VERSION}"
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == job.project_id)
        .where(JobRecord.job_type == "split_structure")
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="split_structure",
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": "split_structure",
                "pipeline_version": PIPELINE_VERSION,
                "processed_view_id": str(view.id),
                "parser_version": STRUCTURE_PARSER_VERSION,
                "trigger": "normalize_source",
                "source_version_id": str(view.version_id),
            },
        )
    )


def _payload_uuid(job: JobRecord, key: str) -> UUID:
    value = job.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload requires {key}") from exc


def _payload_text(job: JobRecord, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TerminalJobError(f"job payload requires {key}")
    return value.strip()
