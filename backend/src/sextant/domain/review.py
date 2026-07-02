from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from sextant.domain.common import DomainInvariantError, InvalidStateTransition


class ReviewType(StrEnum):
    ALIAS_CONFLICT = "alias_conflict"
    EVENT_MERGE_CONFLICT = "event_merge_conflict"
    STATE_CONFLICT = "state_conflict"
    OBJECT_STATE_CONFLICT = "object_state_conflict"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    POV_CONFLICT = "pov_conflict"
    TIMELINE_CONFLICT = "timeline_conflict"
    RELATIONSHIP_CONFLICT = "relationship_conflict"
    CANON_CONFLICT = "canon_conflict"
    VERSION_CONFLICT = "version_conflict"
    SOURCE_SCOPE_CONFLICT = "source_scope_conflict"
    CONTINUITY_WARNING = "continuity_warning"


REVIEW_TYPE_VALUES = tuple(review_type.value for review_type in ReviewType)


class ReviewStatus(StrEnum):
    OPEN = "open"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


REVIEW_RESOLUTIONS = {
    "accept",
    "reject",
    "split",
    "merge",
    "mark_intentional",
    "supersede",
    "needs_memory_update",
    "fixed_by_text_edit",
    "accepted_as_change",
}

AGENT_RISK_LEVELS = ("low", "medium", "high")
AGENT_RISK_TYPES = (
    "pov_risk",
    "knowledge_risk",
    "canon_risk",
    "unresolved_risk",
    "continuity_risk",
    "forbidden_knowledge_leak",
    "non_pov_mind_reading",
    "target_range_risk",
    "character_risk",
    "agency_break_risk",
    "control_risk",
    "cast_reuse_risk",
    "cast_creation_risk",
    "cast_focus_risk",
    "cast_complexity_risk",
    "cast_policy_violation",
    "style_risk",
    "exposition_risk",
    "dramatization_risk",
    "inner_state_overload",
    "telling_over_action",
    "subtext_missing",
    "choice_missing",
    "scene_mode_risk",
    "sequel_mode_risk",
    "mode_mixing_risk",
    "no_turn_risk",
    "prose_contract_violation",
    "inner_state_budget_violation",
)


@dataclass(slots=True)
class ReviewItem:
    id: UUID
    project_id: UUID
    review_type: ReviewType
    severity: str
    summary: str
    new_evidence_span_ids: list[UUID]
    existing_evidence_span_ids: list[UUID]
    status: ReviewStatus = ReviewStatus.OPEN
    resolution: str | None = None
    side_effects: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        project_id: UUID,
        review_type: ReviewType,
        severity: str,
        summary: str,
        new_evidence_span_ids: list[UUID],
        existing_evidence_span_ids: list[UUID],
    ) -> ReviewItem:
        if severity not in {"low", "medium", "high"}:
            raise DomainInvariantError("ReviewItem severity must be low, medium, or high.")
        if not summary.strip():
            raise DomainInvariantError("ReviewItem requires a summary.")
        if not new_evidence_span_ids:
            raise DomainInvariantError("ReviewItem requires new SourceSpan evidence.")
        return cls(
            id=uuid4(),
            project_id=project_id,
            review_type=review_type,
            severity=severity,
            summary=summary,
            new_evidence_span_ids=new_evidence_span_ids,
            existing_evidence_span_ids=existing_evidence_span_ids,
        )

    def dismiss(self) -> None:
        if self.status is not ReviewStatus.OPEN:
            raise InvalidStateTransition("Only open ReviewItems can be dismissed.")
        self.status = ReviewStatus.DISMISSED

    def reopen(self) -> None:
        if self.status is not ReviewStatus.DISMISSED:
            raise InvalidStateTransition("Only dismissed ReviewItems can be reopened.")
        self.status = ReviewStatus.OPEN

    def resolve(self, resolution: str) -> None:
        if self.status is not ReviewStatus.OPEN:
            raise InvalidStateTransition("Only open ReviewItems can be resolved.")
        if resolution not in REVIEW_RESOLUTIONS:
            raise DomainInvariantError("ReviewItem resolution is not whitelisted.")
        self.resolution = resolution
        self.status = (
            ReviewStatus.SUPERSEDED if resolution == "supersede" else ReviewStatus.RESOLVED
        )
