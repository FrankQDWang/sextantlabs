from __future__ import annotations

from uuid import uuid4

import pytest
from sextant.domain.agent import (
    AgentReviewFinding,
    AgentRiskLevel,
    AgentRiskType,
    DraftCandidate,
    DraftCandidateStatus,
)
from sextant.domain.common import DomainInvariantError, InvalidStateTransition
from sextant.domain.manuscript import AcceptedFragment
from sextant.domain.memory import FactAssertion, FactStatus
from sextant.domain.review import ReviewItem, ReviewStatus, ReviewType
from sextant.domain.source import SourceDeltaKind, create_source_delta_from_acceptance
from sextant.domain.story import (
    AliasRecord,
    AliasScope,
    AliasStatus,
    CanonicalEvent,
    CanonicalEventStatus,
    EventCandidate,
    EventCandidateStatus,
)


def test_draft_candidate_requires_author_acceptance_before_source_delta() -> None:
    candidate = DraftCandidate.generated(
        project_id=uuid4(),
        action_request_id=uuid4(),
        target_source_id=uuid4(),
        target_version_id=uuid4(),
        affected_range=(10, 20),
        base_hash="hash-before-generation",
        candidate_text_ref="object://candidate-text",
        mode="rewrite_current_page",
    )
    candidate.mark_reviewed([])
    candidate.offer_to_author()

    with pytest.raises(InvalidStateTransition):
        create_source_delta_from_acceptance(
            candidate=candidate,
            accepted_fragment=None,
            current_base_hash="hash-before-generation",
            delta_kind=SourceDeltaKind.REPLACE,
        )

    accepted = AcceptedFragment.create(
        candidate_id=candidate.id,
        accepted_text_ref="object://accepted-text",
        accepted_text_hash="accepted-hash",
        accept_mode="partial",
        target_source_id=candidate.target_source_id,
        target_version_id=candidate.target_version_id,
        insert_or_replace_range=(12, 18),
        source_scope="user_draft",
        author_edited=True,
    )
    candidate.accept(accepted)

    source_delta = create_source_delta_from_acceptance(
        candidate=candidate,
        accepted_fragment=accepted,
        current_base_hash="hash-before-generation",
        delta_kind=SourceDeltaKind.REPLACE,
    )

    assert source_delta.accepted_fragment_id == accepted.id
    assert source_delta.status == "submitted"
    assert candidate.status is DraftCandidateStatus.CONVERTED_TO_SOURCE_DELTA


def test_stale_base_hash_blocks_replace_source_delta() -> None:
    candidate = DraftCandidate.generated(
        project_id=uuid4(),
        action_request_id=uuid4(),
        target_source_id=uuid4(),
        target_version_id=uuid4(),
        affected_range=(0, 5),
        base_hash="old-hash",
        candidate_text_ref="object://candidate-text",
        mode="rewrite_current_page",
    )
    candidate.mark_reviewed([])
    candidate.offer_to_author()
    accepted = AcceptedFragment.create(
        candidate_id=candidate.id,
        accepted_text_ref="object://accepted-text",
        accepted_text_hash="accepted-hash",
        accept_mode="partial",
        target_source_id=candidate.target_source_id,
        target_version_id=candidate.target_version_id,
        insert_or_replace_range=(0, 5),
        source_scope="user_draft",
        author_edited=False,
    )
    candidate.accept(accepted)

    with pytest.raises(DomainInvariantError, match="stale base"):
        create_source_delta_from_acceptance(
            candidate=candidate,
            accepted_fragment=accepted,
            current_base_hash="new-hash",
            delta_kind=SourceDeltaKind.REPLACE,
        )


def test_blocked_candidate_requires_explicit_override_before_offer() -> None:
    candidate = DraftCandidate.generated(
        project_id=uuid4(),
        action_request_id=uuid4(),
        target_source_id=uuid4(),
        target_version_id=uuid4(),
        affected_range=(0, 0),
        base_hash="hash",
        candidate_text_ref="object://candidate-text",
        mode="draft_next_passage",
    )
    finding = AgentReviewFinding.create(
        draft_candidate_id=candidate.id,
        risk_level=AgentRiskLevel.HIGH,
        risk_type=AgentRiskType.FORBIDDEN_KNOWLEDGE_LEAK,
        summary="Candidate leaks information the POV character cannot know.",
        can_offer_to_author=False,
        draft_local_only=False,
        maps_to_review_type_if_accepted=ReviewType.KNOWLEDGE_CONFLICT,
    )

    candidate.mark_reviewed([finding])
    candidate.block()

    with pytest.raises(InvalidStateTransition):
        candidate.offer_to_author()

    candidate.override_block("Intentional unreliable narrator experiment.")
    candidate.offer_to_author()

    assert candidate.override_reason == "Intentional unreliable narrator experiment."
    assert candidate.status is DraftCandidateStatus.OFFERED_TO_AUTHOR


def test_rejected_draft_candidate_archives_without_memory_state() -> None:
    candidate = DraftCandidate.generated(
        project_id=uuid4(),
        action_request_id=uuid4(),
        target_source_id=uuid4(),
        target_version_id=uuid4(),
        affected_range=(0, 0),
        base_hash="hash",
        candidate_text_ref="object://candidate-text",
        mode="draft_next_passage",
    )
    candidate.mark_reviewed([])
    candidate.offer_to_author()

    with pytest.raises(InvalidStateTransition):
        candidate.archive()

    candidate.reject()
    assert candidate.status is DraftCandidateStatus.REJECTED

    candidate.archive()
    assert candidate.status is DraftCandidateStatus.ARCHIVED


def test_agent_review_finding_cannot_be_formal_review_item() -> None:
    finding = AgentReviewFinding.create(
        draft_candidate_id=uuid4(),
        risk_level=AgentRiskLevel.MEDIUM,
        risk_type=AgentRiskType.CANON_RISK,
        summary="The candidate may contradict current canon.",
        can_offer_to_author=True,
        draft_local_only=False,
        maps_to_review_type_if_accepted=ReviewType.CANON_CONFLICT,
    )

    assert not isinstance(finding, ReviewItem)

    with pytest.raises(DomainInvariantError):
        ReviewItem.create(
            project_id=uuid4(),
            review_type=ReviewType.CANON_CONFLICT,
            severity="medium",
            summary=finding.summary,
            new_evidence_span_ids=[],
            existing_evidence_span_ids=[],
        )


def test_fact_assertion_requires_promotion_decision_to_become_canon() -> None:
    fact = FactAssertion.proposed(
        project_id=uuid4(),
        subject_ref={"kind": "entity", "id": str(uuid4())},
        predicate="owns",
        object_ref={"kind": "entity", "id": str(uuid4())},
        evidence_span_ids=[uuid4()],
        source_scope="user_draft",
    )

    with pytest.raises(InvalidStateTransition):
        fact.mark_canon_without_policy()

    fact.promote_to_canon(policy_decision_id=uuid4())

    assert fact.status is FactStatus.CANON


def test_review_item_lifecycle_uses_formal_statuses() -> None:
    review = ReviewItem.create(
        project_id=uuid4(),
        review_type=ReviewType.POV_CONFLICT,
        severity="high",
        summary="The accepted text exposes non-POV knowledge.",
        new_evidence_span_ids=[uuid4()],
        existing_evidence_span_ids=[uuid4()],
    )

    review.dismiss()
    assert review.status is ReviewStatus.DISMISSED

    review.reopen()
    review.resolve("mark_intentional")
    assert review.status is ReviewStatus.RESOLVED

    with pytest.raises(InvalidStateTransition):
        review.dismiss()


def test_review_item_supersede_resolution_enters_superseded_status() -> None:
    review = ReviewItem.create(
        project_id=uuid4(),
        review_type=ReviewType.VERSION_CONFLICT,
        severity="medium",
        summary="A newer SourceDelta replaces this review.",
        new_evidence_span_ids=[uuid4()],
        existing_evidence_span_ids=[uuid4()],
    )

    review.resolve("supersede")

    assert review.status is ReviewStatus.SUPERSEDED
    assert review.resolution == "supersede"

    with pytest.raises(InvalidStateTransition):
        review.reopen()


def test_alias_record_preserves_low_confidence_and_requires_author_global_expansion() -> None:
    span_id = uuid4()
    alias = AliasRecord.from_mention(
        project_id=uuid4(),
        alias_text="那个人",
        alias_type="pronoun",
        scope=AliasScope.SCENE_LOCAL,
        evidence_span_ids=[span_id],
        confidence=0.2,
    )

    assert alias.status is AliasStatus.LOW_CONFIDENCE
    assert alias.affects_graph is False
    assert alias.evidence_span_ids == [span_id]

    with pytest.raises(InvalidStateTransition):
        alias.expand_scene_local_to_global(author_decision_id=None)

    alias.expand_scene_local_to_global(author_decision_id=uuid4())
    assert alias.scope is AliasScope.GLOBAL


def test_alias_user_correction_requires_audit_signal() -> None:
    alias = AliasRecord.from_mention(
        project_id=uuid4(),
        alias_text="银面人",
        alias_type="title",
        scope=AliasScope.GLOBAL,
        evidence_span_ids=[uuid4()],
        confidence=0.7,
    )

    with pytest.raises(DomainInvariantError):
        alias.correct(entity_id=uuid4(), audit_signal_id=None)

    audit_signal_id = uuid4()
    corrected_entity_id = uuid4()
    alias.correct(entity_id=corrected_entity_id, audit_signal_id=audit_signal_id)

    assert alias.status is AliasStatus.USER_CORRECTED
    assert alias.entity_id == corrected_entity_id
    assert alias.audit_signal_id == audit_signal_id


def test_event_candidate_merge_conflict_and_reject_preserve_evidence() -> None:
    span_id = uuid4()
    event = EventCandidate.create(
        project_id=uuid4(),
        event_type="object_transfer",
        summary="Kestrel may have taken the Lantern Map.",
        evidence_span_ids=[span_id],
        confidence=0.8,
    )

    with pytest.raises(InvalidStateTransition):
        event.merge(canonical_event_id=None)

    canonical_event_id = uuid4()
    event.merge(canonical_event_id=canonical_event_id)
    assert event.status is EventCandidateStatus.MERGED
    assert event.canonical_event_id == canonical_event_id

    conflicting = EventCandidate.create(
        project_id=event.project_id,
        event_type="object_transfer",
        summary="Mira may still have the Lantern Map.",
        evidence_span_ids=[uuid4()],
        confidence=0.6,
    )

    with pytest.raises(DomainInvariantError):
        conflicting.mark_conflict_version(review_item_id=None, disputed_relation_id=None)

    review_item_id = uuid4()
    conflicting.mark_conflict_version(review_item_id=review_item_id, disputed_relation_id=None)
    conflicting.reject()

    assert conflicting.status is EventCandidateStatus.REJECTED
    assert conflicting.conflict_ref == {"review_item_id": str(review_item_id)}
    assert conflicting.evidence_span_ids


def test_canonical_event_requires_policy_or_author_decision_for_canon() -> None:
    event = CanonicalEvent.proposed(
        project_id=uuid4(),
        event_type="revelation",
        title="Mira learns the map was stolen",
        event_candidate_ids=[uuid4()],
        evidence_span_ids=[uuid4()],
    )

    with pytest.raises(InvalidStateTransition):
        event.promote_to_canon(policy_decision_id=None, author_decision_id=None)

    event.promote_to_canon(policy_decision_id=uuid4(), author_decision_id=None)
    assert event.status is CanonicalEventStatus.CANON

    event.deprecate(replacement_event_id=uuid4())
    assert event.status is CanonicalEventStatus.DEPRECATED
    assert event.evidence_span_ids
