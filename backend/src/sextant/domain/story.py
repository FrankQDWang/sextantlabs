from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from sextant.domain.common import DomainInvariantError, InvalidStateTransition


class AliasStatus(StrEnum):
    AUTO_ACCEPTED = "auto_accepted"
    PROPOSED = "proposed"
    LOW_CONFIDENCE = "low_confidence"
    USER_CONFIRMED = "user_confirmed"
    USER_CORRECTED = "user_corrected"
    REJECTED = "rejected"


class AliasScope(StrEnum):
    GLOBAL = "global"
    CHAPTER_LOCAL = "chapter_local"
    SCENE_LOCAL = "scene_local"
    CHARACTER_SPECIFIC = "character_specific"
    DISGUISE_ARC = "disguise_arc"


@dataclass(slots=True)
class AliasRecord:
    id: UUID
    project_id: UUID
    alias_text: str
    alias_type: str
    scope: AliasScope
    evidence_span_ids: list[UUID]
    confidence: float
    status: AliasStatus
    entity_id: UUID | None = None
    audit_signal_id: UUID | None = None

    @classmethod
    def from_mention(
        cls,
        *,
        project_id: UUID,
        alias_text: str,
        alias_type: str,
        scope: AliasScope,
        evidence_span_ids: list[UUID],
        confidence: float,
        entity_id: UUID | None = None,
    ) -> AliasRecord:
        _require_story_text(alias_text, "AliasRecord requires alias text.")
        _require_story_text(alias_type, "AliasRecord requires alias type.")
        _require_evidence(evidence_span_ids, "AliasRecord requires SourceSpan evidence.")
        _require_confidence(confidence)

        if confidence >= 0.85 and entity_id is not None:
            status = AliasStatus.AUTO_ACCEPTED
        elif confidence >= 0.45:
            status = AliasStatus.PROPOSED
        else:
            status = AliasStatus.LOW_CONFIDENCE

        return cls(
            id=uuid4(),
            project_id=project_id,
            alias_text=alias_text.strip(),
            alias_type=alias_type.strip(),
            scope=scope,
            evidence_span_ids=evidence_span_ids,
            confidence=confidence,
            status=status,
            entity_id=entity_id,
        )

    @property
    def affects_graph(self) -> bool:
        return self.status in {
            AliasStatus.AUTO_ACCEPTED,
            AliasStatus.USER_CONFIRMED,
            AliasStatus.USER_CORRECTED,
        }

    def confirm(self, *, entity_id: UUID) -> None:
        if self.status is AliasStatus.REJECTED:
            raise InvalidStateTransition("Rejected aliases cannot be confirmed.")
        self.entity_id = entity_id
        self.status = AliasStatus.USER_CONFIRMED

    def correct(self, *, entity_id: UUID, audit_signal_id: UUID | None) -> None:
        if audit_signal_id is None:
            raise DomainInvariantError("Alias user correction requires an audit signal.")
        if self.status is AliasStatus.REJECTED:
            raise InvalidStateTransition("Rejected aliases cannot be corrected.")
        self.entity_id = entity_id
        self.audit_signal_id = audit_signal_id
        self.status = AliasStatus.USER_CORRECTED

    def reject(self) -> None:
        self.status = AliasStatus.REJECTED

    def expand_scene_local_to_global(self, *, author_decision_id: UUID | None) -> None:
        if self.scope is not AliasScope.SCENE_LOCAL:
            raise InvalidStateTransition("Only scene-local aliases can use scene-local expansion.")
        if author_decision_id is None:
            raise InvalidStateTransition(
                "Scene-local aliases require explicit author global scope."
            )
        self.audit_signal_id = author_decision_id
        self.scope = AliasScope.GLOBAL


class EventCandidateStatus(StrEnum):
    NEW = "new"
    MERGED = "merged"
    RELATED = "related"
    CONFLICT_VERSION = "conflict_version"
    REJECTED = "rejected"


@dataclass(slots=True)
class EventCandidate:
    id: UUID
    project_id: UUID
    event_type: str
    summary: str
    evidence_span_ids: list[UUID]
    confidence: float
    status: EventCandidateStatus
    canonical_event_id: UUID | None = None
    related_event_id: UUID | None = None
    conflict_ref: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        project_id: UUID,
        event_type: str,
        summary: str,
        evidence_span_ids: list[UUID],
        confidence: float,
    ) -> EventCandidate:
        _require_story_text(event_type, "EventCandidate requires event type.")
        _require_story_text(summary, "EventCandidate requires summary.")
        _require_evidence(evidence_span_ids, "EventCandidate requires SourceSpan evidence.")
        _require_confidence(confidence)
        return cls(
            id=uuid4(),
            project_id=project_id,
            event_type=event_type.strip(),
            summary=summary.strip(),
            evidence_span_ids=evidence_span_ids,
            confidence=confidence,
            status=EventCandidateStatus.NEW,
        )

    def merge(self, *, canonical_event_id: UUID | None) -> None:
        if self.status is not EventCandidateStatus.NEW:
            raise InvalidStateTransition("Only new EventCandidates can be merged.")
        if canonical_event_id is None:
            raise InvalidStateTransition("Merged EventCandidates must reference CanonicalEvent.")
        self.canonical_event_id = canonical_event_id
        self.status = EventCandidateStatus.MERGED

    def mark_related(self, *, related_event_id: UUID) -> None:
        if self.status is not EventCandidateStatus.NEW:
            raise InvalidStateTransition("Only new EventCandidates can be related.")
        self.related_event_id = related_event_id
        self.status = EventCandidateStatus.RELATED

    def mark_conflict_version(
        self,
        *,
        review_item_id: UUID | None,
        disputed_relation_id: UUID | None,
    ) -> None:
        if self.status is not EventCandidateStatus.NEW:
            raise InvalidStateTransition("Only new EventCandidates can be marked conflicting.")
        if review_item_id is None and disputed_relation_id is None:
            raise DomainInvariantError(
                "EventCandidate conflict_version requires ReviewItem or disputed relation."
            )
        if review_item_id is not None:
            self.conflict_ref["review_item_id"] = str(review_item_id)
        if disputed_relation_id is not None:
            self.conflict_ref["disputed_relation_id"] = str(disputed_relation_id)
        self.status = EventCandidateStatus.CONFLICT_VERSION

    def reject(self) -> None:
        if not self.evidence_span_ids:
            raise DomainInvariantError("Rejected EventCandidates must retain evidence.")
        self.status = EventCandidateStatus.REJECTED


class CanonicalEventStatus(StrEnum):
    PROPOSED = "proposed"
    CANON = "canon"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"
    EXTERNAL_CANON = "external_canon"
    AUTHOR_NOTE = "author_note"


@dataclass(slots=True)
class CanonicalEvent:
    id: UUID
    project_id: UUID
    event_type: str
    title: str
    event_candidate_ids: list[UUID]
    evidence_span_ids: list[UUID]
    status: CanonicalEventStatus
    policy_decision_id: UUID | None = None
    author_decision_id: UUID | None = None
    replacement_event_id: UUID | None = None

    @classmethod
    def proposed(
        cls,
        *,
        project_id: UUID,
        event_type: str,
        title: str,
        event_candidate_ids: list[UUID],
        evidence_span_ids: list[UUID],
    ) -> CanonicalEvent:
        _require_story_text(event_type, "CanonicalEvent requires event type.")
        _require_story_text(title, "CanonicalEvent requires title.")
        _require_evidence(event_candidate_ids, "CanonicalEvent requires EventCandidate evidence.")
        _require_evidence(evidence_span_ids, "CanonicalEvent requires SourceSpan evidence.")
        return cls(
            id=uuid4(),
            project_id=project_id,
            event_type=event_type.strip(),
            title=title.strip(),
            event_candidate_ids=event_candidate_ids,
            evidence_span_ids=evidence_span_ids,
            status=CanonicalEventStatus.PROPOSED,
        )

    def promote_to_canon(
        self,
        *,
        policy_decision_id: UUID | None,
        author_decision_id: UUID | None,
    ) -> None:
        if self.status is not CanonicalEventStatus.PROPOSED:
            raise InvalidStateTransition("Only proposed CanonicalEvents can be promoted.")
        if policy_decision_id is None and author_decision_id is None:
            raise InvalidStateTransition(
                "CanonicalEvent canon promotion requires policy or author decision."
            )
        self.policy_decision_id = policy_decision_id
        self.author_decision_id = author_decision_id
        self.status = CanonicalEventStatus.CANON

    def mark_external_canon(self, *, author_decision_id: UUID | None) -> None:
        if author_decision_id is None:
            raise InvalidStateTransition("External canon cannot override user draft implicitly.")
        self.author_decision_id = author_decision_id
        self.status = CanonicalEventStatus.EXTERNAL_CANON

    def mark_author_note(self, *, author_decision_id: UUID) -> None:
        self.author_decision_id = author_decision_id
        self.status = CanonicalEventStatus.AUTHOR_NOTE

    def dispute(self, *, review_item_id: UUID) -> None:
        self.policy_decision_id = review_item_id
        self.status = CanonicalEventStatus.DISPUTED

    def deprecate(self, *, replacement_event_id: UUID) -> None:
        if not self.evidence_span_ids:
            raise DomainInvariantError("Deprecated CanonicalEvents must retain evidence.")
        self.replacement_event_id = replacement_event_id
        self.status = CanonicalEventStatus.DEPRECATED


def _require_story_text(value: str, message: str) -> None:
    if not value.strip():
        raise DomainInvariantError(message)


def _require_evidence(values: list[UUID], message: str) -> None:
    if not values:
        raise DomainInvariantError(message)


def _require_confidence(confidence: float) -> None:
    if confidence < 0 or confidence > 1:
        raise DomainInvariantError("Story confidence must be between 0 and 1.")
