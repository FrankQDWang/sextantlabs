from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from sextant.domain.agent import DraftCandidate, DraftCandidateStatus
from sextant.domain.common import DomainInvariantError, InvalidStateTransition
from sextant.domain.manuscript import AcceptedFragment


class SourceDeltaKind(StrEnum):
    INSERT = "insert"
    REPLACE = "replace"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class SourceDelta:
    id: UUID
    source_id: UUID
    previous_version_id: UUID
    accepted_fragment_id: UUID
    changed_range: tuple[int, int]
    base_hash: str
    delta_kind: SourceDeltaKind
    submitted_text_ref: str
    status: str = "submitted"


def create_source_delta_from_acceptance(
    *,
    candidate: DraftCandidate,
    accepted_fragment: AcceptedFragment | None,
    current_base_hash: str,
    delta_kind: SourceDeltaKind,
) -> SourceDelta:
    if accepted_fragment is None:
        raise InvalidStateTransition("AcceptedFragment is required before SourceDelta creation.")
    if candidate.status is not DraftCandidateStatus.ACCEPTED:
        raise InvalidStateTransition("DraftCandidate must be accepted before SourceDelta creation.")
    if accepted_fragment.id != candidate.accepted_fragment_id:
        raise DomainInvariantError("AcceptedFragment is not linked to the candidate.")
    if delta_kind is SourceDeltaKind.REPLACE and current_base_hash != candidate.base_hash:
        raise DomainInvariantError("Cannot create replace SourceDelta from stale base hash.")

    candidate.mark_converted_to_source_delta()
    return SourceDelta(
        id=uuid4(),
        source_id=accepted_fragment.target_source_id,
        previous_version_id=accepted_fragment.target_version_id,
        accepted_fragment_id=accepted_fragment.id,
        changed_range=accepted_fragment.insert_or_replace_range,
        base_hash=candidate.base_hash,
        delta_kind=delta_kind,
        submitted_text_ref=accepted_fragment.accepted_text_ref,
    )
