from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from sextant.application.use_cases import BuildWritingContextPack
from sextant.contracts.use_cases import BuildWritingContextPackInput
from sextant.infra.db.models import JobRecord
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.infra.worker import TerminalJobError


class BuildContextPackHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        BuildWritingContextPack(lambda: SqlAlchemyUnitOfWork(session)).execute(
            BuildWritingContextPackInput(
                project_id=job.project_id,
                actor_id=_payload_uuid(job, "actor_id"),
                request_id=_payload_text(job, "request_id", default=f"job:{job.id}"),
                idempotency_key=_payload_text(
                    job,
                    "idempotency_key",
                    default=job.idempotency_key,
                ),
                action_request_id=_optional_payload_uuid(job, "action_request_id"),
                current_source_id=_optional_payload_uuid(job, "current_source_id"),
                current_version_id=_optional_payload_uuid(job, "current_version_id"),
                current_scene_id=_optional_payload_uuid(job, "current_scene_id"),
                current_pov_character_id=_optional_payload_uuid(
                    job,
                    "current_pov_character_id",
                ),
                mode=_payload_text(job, "mode"),
                current_text_window=_payload_text(job, "current_text_window", default=""),
                constraints=_payload_record(job, "constraints", default={}),
            )
        )


def _payload_uuid(job: JobRecord, key: str) -> UUID:
    value = job.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload requires {key}") from exc


def _optional_payload_uuid(job: JobRecord, key: str) -> UUID | None:
    value = job.payload.get(key)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload has invalid {key}") from exc


def _payload_text(job: JobRecord, key: str, *, default: str | None = None) -> str:
    value = job.payload.get(key)
    if value is None and default is not None:
        value = default
    if not isinstance(value, str):
        raise TerminalJobError(f"job payload requires {key}")
    if key != "current_text_window" and not value.strip():
        raise TerminalJobError(f"job payload requires {key}")
    return value.strip() if key != "current_text_window" else value


def _payload_record(
    job: JobRecord,
    key: str,
    *,
    default: dict[str, object] | None = None,
) -> dict[str, object]:
    value = job.payload.get(key)
    if value is None and default is not None:
        value = default
    if not isinstance(value, dict):
        raise TerminalJobError(f"job payload requires object {key}")
    return value
