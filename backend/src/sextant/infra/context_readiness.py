from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.infra.db.models import ContextPackReadinessRecord


def mark_context_pack_readiness(
    session: Session,
    *,
    project_id: UUID,
    source_span_id: UUID,
    source_delta_id: UUID | None = None,
    affected_refs: list[dict[str, object]] | None = None,
    reason: str = "memory_dependency_changed",
    status: str = "pending",
) -> ContextPackReadinessRecord:
    evidence_refs = [{"type": "source_span", "id": str(source_span_id)}]
    record = session.scalars(
        select(ContextPackReadinessRecord)
        .where(ContextPackReadinessRecord.project_id == project_id)
        .where(ContextPackReadinessRecord.source_span_id == source_span_id)
        .where(ContextPackReadinessRecord.reason == reason)
    ).first()
    if record is None:
        record = ContextPackReadinessRecord(
            id=uuid4(),
            project_id=project_id,
            source_span_id=source_span_id,
            source_delta_id=source_delta_id,
            status=status,
            reason=reason,
            affected_refs=affected_refs or [],
            evidence_refs=evidence_refs,
        )
        session.add(record)
        session.flush()
        return record

    record.status = status
    if source_delta_id is not None:
        record.source_delta_id = source_delta_id
    if affected_refs:
        record.affected_refs = _unique_refs(list(record.affected_refs) + affected_refs)
    record.evidence_refs = evidence_refs
    session.flush()
    return record


def _unique_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for ref in refs:
        key = (str(ref.get("type")), str(ref.get("id")))
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return result
