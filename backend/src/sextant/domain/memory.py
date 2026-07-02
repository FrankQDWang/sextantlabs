from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from sextant.domain.common import DomainInvariantError, InvalidStateTransition


class FactStatus(StrEnum):
    PROPOSED = "proposed"
    INFERRED = "inferred"
    CANON = "canon"
    DISPUTED = "disputed"
    CONTRADICTED = "contradicted"
    OUTDATED = "outdated"
    USER_NOTE = "user_note"


@dataclass(slots=True)
class FactAssertion:
    id: UUID
    project_id: UUID
    subject_ref: dict[str, str]
    predicate: str
    object_ref: dict[str, str]
    evidence_span_ids: list[UUID]
    source_scope: str
    status: FactStatus
    promotion_policy_decision_id: UUID | None = None

    @classmethod
    def proposed(
        cls,
        *,
        project_id: UUID,
        subject_ref: dict[str, str],
        predicate: str,
        object_ref: dict[str, str],
        evidence_span_ids: list[UUID],
        source_scope: str,
    ) -> FactAssertion:
        if not evidence_span_ids:
            raise DomainInvariantError("FactAssertion requires SourceSpan evidence.")
        if source_scope == "model_suggestion":
            raise DomainInvariantError("Model suggestions cannot create proposed canon facts.")
        return cls(
            id=uuid4(),
            project_id=project_id,
            subject_ref=subject_ref,
            predicate=predicate,
            object_ref=object_ref,
            evidence_span_ids=evidence_span_ids,
            source_scope=source_scope,
            status=FactStatus.PROPOSED,
        )

    def mark_canon_without_policy(self) -> None:
        raise InvalidStateTransition("FactAssertion cannot become canon without policy decision.")

    def promote_to_canon(self, *, policy_decision_id: UUID) -> None:
        if self.status not in {FactStatus.PROPOSED, FactStatus.INFERRED}:
            raise InvalidStateTransition("Only proposed or inferred facts can be promoted.")
        self.promotion_policy_decision_id = policy_decision_id
        self.status = FactStatus.CANON
