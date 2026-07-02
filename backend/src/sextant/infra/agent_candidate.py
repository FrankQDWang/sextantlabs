from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from sextant.application.errors import ApplicationError
from sextant.application.use_cases import RunActionRequest
from sextant.contracts.use_cases import RunActionRequestInput
from sextant.infra.db.models import JobRecord
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.infra.worker import ProviderRetryableJobError, TerminalJobError
from sextant.ports.object_store import ObjectStore
from sextant.ports.story_draft import StoryDraftProvider


class AgentCandidateHandler:
    def __init__(
        self,
        object_store: ObjectStore,
        story_draft_provider: StoryDraftProvider,
    ) -> None:
        self._object_store = object_store
        self._story_draft_provider = story_draft_provider

    def __call__(self, session: Session, job: JobRecord) -> None:
        prompt_version = _payload_text(job, "prompt_version")
        if prompt_version != self._story_draft_provider.skill_version:
            raise TerminalJobError(
                "job prompt_version does not match configured story draft provider"
            )
        _payload_text(job, "input_hash")

        try:
            RunActionRequest(
                lambda: SqlAlchemyUnitOfWork(session),
                self._object_store,
                self._story_draft_provider,
            ).execute(
                RunActionRequestInput(
                    project_id=job.project_id,
                    actor_id=_payload_uuid(job, "actor_id"),
                    request_id=_payload_text(job, "request_id", default=f"job:{job.id}"),
                    idempotency_key=_payload_text(
                        job,
                        "idempotency_key",
                        default=job.idempotency_key,
                    ),
                    action_request_id=_payload_uuid(job, "action_request_id"),
                    current_text_window=_payload_text(
                        job,
                        "current_text_window",
                        default="",
                    ),
                )
            )
        except ApplicationError as exc:
            raise TerminalJobError(f"{exc.code}: {exc.message}") from exc
        except RuntimeError as exc:
            raise ProviderRetryableJobError(str(exc)) from exc


def _payload_uuid(job: JobRecord, key: str) -> UUID:
    value = job.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError(f"job payload requires {key}") from exc


def _payload_text(job: JobRecord, key: str, *, default: str | None = None) -> str:
    value = job.payload.get(key)
    if value is None and default is not None:
        value = default
    if not isinstance(value, str):
        raise TerminalJobError(f"job payload requires {key}")
    if key != "current_text_window" and not value.strip():
        raise TerminalJobError(f"job payload requires {key}")
    return value.strip() if key != "current_text_window" else value
