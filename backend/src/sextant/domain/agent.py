from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sextant.domain.common import DomainInvariantError, InvalidStateTransition

if TYPE_CHECKING:
    from sextant.domain.manuscript import AcceptedFragment
    from sextant.domain.review import ReviewType


class DraftCandidateStatus(StrEnum):
    GENERATED = "generated"
    REVIEWED = "reviewed"
    OFFERED_TO_AUTHOR = "offered_to_author"
    ACCEPTED = "accepted"
    REVISED = "revised"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    CONVERTED_TO_SOURCE_DELTA = "converted_to_source_delta"


class AgentRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentRiskType(StrEnum):
    POV_RISK = "pov_risk"
    KNOWLEDGE_RISK = "knowledge_risk"
    CANON_RISK = "canon_risk"
    UNRESOLVED_RISK = "unresolved_risk"
    CONTINUITY_RISK = "continuity_risk"
    FORBIDDEN_KNOWLEDGE_LEAK = "forbidden_knowledge_leak"
    NON_POV_MIND_READING = "non_pov_mind_reading"
    TARGET_RANGE_RISK = "target_range_risk"
    CHARACTER_RISK = "character_risk"
    AGENCY_BREAK_RISK = "agency_break_risk"
    CONTROL_RISK = "control_risk"
    CAST_REUSE_RISK = "cast_reuse_risk"
    CAST_CREATION_RISK = "cast_creation_risk"
    CAST_FOCUS_RISK = "cast_focus_risk"
    CAST_COMPLEXITY_RISK = "cast_complexity_risk"
    CAST_POLICY_VIOLATION = "cast_policy_violation"
    STYLE_RISK = "style_risk"
    EXPOSITION_RISK = "exposition_risk"
    DRAMATIZATION_RISK = "dramatization_risk"
    INNER_STATE_OVERLOAD = "inner_state_overload"
    TELLING_OVER_ACTION = "telling_over_action"
    SUBTEXT_MISSING = "subtext_missing"
    CHOICE_MISSING = "choice_missing"
    SCENE_MODE_RISK = "scene_mode_risk"
    SEQUEL_MODE_RISK = "sequel_mode_risk"
    MODE_MIXING_RISK = "mode_mixing_risk"
    NO_TURN_RISK = "no_turn_risk"
    PROSE_CONTRACT_VIOLATION = "prose_contract_violation"
    INNER_STATE_BUDGET_VIOLATION = "inner_state_budget_violation"


@dataclass(slots=True)
class AgentReviewFinding:
    id: UUID
    draft_candidate_id: UUID
    risk_level: AgentRiskLevel
    risk_type: AgentRiskType
    summary: str
    can_offer_to_author: bool
    draft_local_only: bool
    maps_to_review_type_if_accepted: ReviewType | None = None

    @classmethod
    def create(
        cls,
        *,
        draft_candidate_id: UUID,
        risk_level: AgentRiskLevel,
        risk_type: AgentRiskType,
        summary: str,
        can_offer_to_author: bool,
        draft_local_only: bool,
        maps_to_review_type_if_accepted: ReviewType | None = None,
    ) -> AgentReviewFinding:
        if not summary.strip():
            raise DomainInvariantError("AgentReviewFinding requires a summary.")
        return cls(
            id=uuid4(),
            draft_candidate_id=draft_candidate_id,
            risk_level=risk_level,
            risk_type=risk_type,
            summary=summary,
            can_offer_to_author=can_offer_to_author,
            draft_local_only=draft_local_only,
            maps_to_review_type_if_accepted=maps_to_review_type_if_accepted,
        )


@dataclass(slots=True)
class DraftCandidate:
    id: UUID
    project_id: UUID
    action_request_id: UUID
    target_source_id: UUID
    target_version_id: UUID
    affected_range: tuple[int, int]
    base_hash: str
    candidate_text_ref: str
    mode: str
    status: DraftCandidateStatus
    review_findings: list[AgentReviewFinding] = field(default_factory=list)
    accepted_fragment_id: UUID | None = None
    override_reason: str | None = None

    @classmethod
    def generated(
        cls,
        *,
        project_id: UUID,
        action_request_id: UUID,
        target_source_id: UUID,
        target_version_id: UUID,
        affected_range: tuple[int, int],
        base_hash: str,
        candidate_text_ref: str,
        mode: str,
    ) -> DraftCandidate:
        start, end = affected_range
        if start < 0 or end < start:
            raise DomainInvariantError("affected_range must be a valid non-negative range.")
        if not base_hash:
            raise DomainInvariantError("DraftCandidate requires a base_hash.")
        return cls(
            id=uuid4(),
            project_id=project_id,
            action_request_id=action_request_id,
            target_source_id=target_source_id,
            target_version_id=target_version_id,
            affected_range=affected_range,
            base_hash=base_hash,
            candidate_text_ref=candidate_text_ref,
            mode=mode,
            status=DraftCandidateStatus.GENERATED,
        )

    def mark_reviewed(self, findings: list[AgentReviewFinding]) -> None:
        if self.status is not DraftCandidateStatus.GENERATED:
            raise InvalidStateTransition("Only generated candidates can be reviewed.")
        self.review_findings = findings
        self.status = DraftCandidateStatus.REVIEWED

    def block(self) -> None:
        if self.status is not DraftCandidateStatus.REVIEWED:
            raise InvalidStateTransition("Only reviewed candidates can be blocked.")
        if not any(f.risk_level is AgentRiskLevel.HIGH for f in self.review_findings):
            raise DomainInvariantError("Blocked candidates require a high-risk finding.")
        self.status = DraftCandidateStatus.BLOCKED

    def override_block(self, reason: str) -> None:
        if self.status is not DraftCandidateStatus.BLOCKED:
            raise InvalidStateTransition("Only blocked candidates can be overridden.")
        if not reason.strip():
            raise DomainInvariantError("Blocked candidate override requires a reason.")
        self.override_reason = reason

    def offer_to_author(self) -> None:
        if self.status is DraftCandidateStatus.REVIEWED:
            if any(
                f.risk_level is AgentRiskLevel.HIGH and not f.can_offer_to_author
                for f in self.review_findings
            ):
                raise InvalidStateTransition("High-risk candidate must be blocked or revised.")
            self.status = DraftCandidateStatus.OFFERED_TO_AUTHOR
            return
        if self.status is DraftCandidateStatus.BLOCKED and self.override_reason:
            self.status = DraftCandidateStatus.OFFERED_TO_AUTHOR
            return
        raise InvalidStateTransition("Candidate is not offerable to the author.")

    def accept(self, accepted_fragment: AcceptedFragment) -> None:
        if self.status is not DraftCandidateStatus.OFFERED_TO_AUTHOR:
            raise InvalidStateTransition("Only offered candidates can be accepted.")
        if accepted_fragment.candidate_id != self.id:
            raise DomainInvariantError("AcceptedFragment must refer to this candidate.")
        self.accepted_fragment_id = accepted_fragment.id
        self.status = DraftCandidateStatus.ACCEPTED

    def reject(self) -> None:
        if self.status is not DraftCandidateStatus.OFFERED_TO_AUTHOR:
            raise InvalidStateTransition("Only offered candidates can be rejected.")
        self.status = DraftCandidateStatus.REJECTED

    def archive(self) -> None:
        if self.status is not DraftCandidateStatus.REJECTED:
            raise InvalidStateTransition("Only rejected candidates can be archived.")
        self.status = DraftCandidateStatus.ARCHIVED

    def mark_converted_to_source_delta(self) -> None:
        if self.status is not DraftCandidateStatus.ACCEPTED:
            raise InvalidStateTransition("Only accepted candidates can become SourceDelta.")
        if self.accepted_fragment_id is None:
            raise DomainInvariantError("Accepted candidate needs an AcceptedFragment.")
        self.status = DraftCandidateStatus.CONVERTED_TO_SOURCE_DELTA
