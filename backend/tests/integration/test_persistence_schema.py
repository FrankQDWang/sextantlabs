from __future__ import annotations

from uuid import uuid4

import pytest
from sextant.infra.db.models import (
    AgentActionRequestRecord,
    AgentReviewFindingRecord,
    Base,
    CharacterKnowledge,
    ContextPackReadinessRecord,
    FactAssertionRecord,
    GraphProjectionEdge,
    IdempotencyRecord,
    JobRecord,
    Project,
    ProjectMembership,
    ProjectStorySchemaBinding,
    RawSource,
    ReviewItemRecord,
    SemanticEmbeddingRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
    StoryEventCandidate,
    StorySchemaPackRecord,
)
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.story_schema import load_effective_story_schema
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def create_source_version(session: Session) -> SourceVersion:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref="object://raw/chapter-3",
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    session.add_all([project, raw_source, version])
    session.commit()
    return version


def test_only_one_current_processed_view_per_source_version(session: Session) -> None:
    version = create_source_version(session)
    first_view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/one",
        raw_offset_map_ref="object://offsets/one",
        view_status="current",
    )
    second_view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v2",
        markdown_ref="object://markdown/two",
        raw_offset_map_ref="object://offsets/two",
        view_status="current",
    )

    session.add(first_view)
    session.commit()
    session.add(second_view)

    with pytest.raises(IntegrityError):
        session.commit()


def test_source_span_range_checks_are_enforced(session: Session) -> None:
    version = create_source_version(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    session.add(view)
    session.commit()

    bad_span = SourceSpan(
        id=uuid4(),
        source_id=version.source_id,
        version_id=version.id,
        view_id=view.id,
        start_offset=10,
        end_offset=5,
        raw_start_offset=30,
        raw_end_offset=20,
        text_preview="bad",
        narration_layer="narrator",
    )
    session.add(bad_span)

    with pytest.raises(IntegrityError):
        session.commit()


def test_context_pack_readiness_schema_checks_are_enforced(session: Session) -> None:
    version = create_source_version(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=version.source_id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=12,
        raw_start_offset=0,
        raw_end_offset=12,
        text_preview="Mira moved.",
        narration_layer="narrator",
    )
    session.add_all([view, span])
    session.commit()

    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    first = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        source_span_id=span.id,
        source_delta_id=None,
        status="pending",
        reason="memory_dependency_changed",
        affected_refs=[],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    session.add(first)
    session.commit()

    duplicate = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=first.project_id,
        source_span_id=span.id,
        source_delta_id=None,
        status="pending",
        reason="memory_dependency_changed",
        affected_refs=[],
        evidence_refs=[],
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_status = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=first.project_id,
        source_span_id=span.id,
        source_delta_id=None,
        status="ready",
        reason="memory_dependency_changed",
        affected_refs=[],
        evidence_refs=[],
    )
    session.add(bad_status)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_reason = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=first.project_id,
        source_span_id=span.id,
        source_delta_id=None,
        status="pending",
        reason="unknown_change",
        affected_refs=[],
        evidence_refs=[],
    )
    session.add(bad_reason)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_character_knowledge_schema_checks_are_enforced(session: Session) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=version.source_id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=12,
        raw_start_offset=0,
        raw_end_offset=12,
        text_preview="Mira knows.",
        narration_layer="narrator",
    )
    session.add_all([view, span])
    session.commit()

    valid = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=uuid4(),
        knows_ref={"type": "fact_assertion", "id": str(uuid4())},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add(valid)
    session.commit()

    bad_certainty = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=uuid4(),
        knows_ref={"type": "fact_assertion", "id": str(uuid4())},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="omniscient",
        hidden_from=[],
        status="active",
    )
    session.add(bad_certainty)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_status = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=uuid4(),
        knows_ref={"type": "fact_assertion", "id": str(uuid4())},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="hidden",
    )
    session.add(bad_status)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_semantic_embedding_schema_checks_are_enforced(session: Session) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    target_id = uuid4()
    valid = SemanticEmbeddingRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        target_type="memory_page",
        target_id=target_id,
        target_ref={"type": "character", "id": str(target_id), "label": "Mira"},
        text_hash="hash-one",
        provider="local_deterministic",
        model_name="local-semantic-hash-v1",
        dimensions=2,
        vector=[1.0, 0.0],
        evidence_refs=[],
    )
    session.add(valid)
    session.commit()

    duplicate = SemanticEmbeddingRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        target_type="memory_page",
        target_id=target_id,
        target_ref={"type": "character", "id": str(target_id), "label": "Mira"},
        text_hash="hash-two",
        provider="local_deterministic",
        model_name="local-semantic-hash-v1",
        dimensions=2,
        vector=[0.0, 1.0],
        evidence_refs=[],
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_target_type = SemanticEmbeddingRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        target_type="draft_candidate",
        target_id=uuid4(),
        target_ref={"type": "candidate", "id": str(uuid4())},
        text_hash="hash-three",
        provider="local_deterministic",
        model_name="local-semantic-hash-v1",
        dimensions=2,
        vector=[1.0, 0.0],
        evidence_refs=[],
    )
    session.add(bad_target_type)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_dimensions = SemanticEmbeddingRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        target_type="memory_page",
        target_id=uuid4(),
        target_ref={"type": "character", "id": str(uuid4())},
        text_hash="hash-four",
        provider="local_deterministic",
        model_name="local-semantic-hash-v1",
        dimensions=0,
        vector=[],
        evidence_refs=[],
    )
    session.add(bad_dimensions)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_story_schema_pack_constraints_and_active_binding(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    base_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="base",
        pack_name="base-story-schema",
        version="base.v1",
        status="active",
        entity_types=[{"name": "character"}, {"name": "object"}],
        event_types=["knowledge_change"],
        relations=["owns", "related_to"],
        extraction_hints={},
        risk_rules={},
    )
    override_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=project.id,
        pack_type="project_override",
        pack_name="harbor-nine-overrides",
        version="project.v1",
        status="active",
        entity_types=[{"name": "star_scar", "subtype_of": "object"}],
        event_types=[],
        relations=[],
        extraction_hints={},
        risk_rules={},
    )
    binding = ProjectStorySchemaBinding(
        id=uuid4(),
        project_id=project.id,
        base_schema_pack_id=base_pack.id,
        genre_schema_pack_id=None,
        project_override_pack_id=override_pack.id,
        status="active",
        created_by=uuid4(),
    )

    session.add_all([project, base_pack, override_pack, binding])
    session.commit()

    duplicate_active = ProjectStorySchemaBinding(
        id=uuid4(),
        project_id=project.id,
        base_schema_pack_id=base_pack.id,
        genre_schema_pack_id=None,
        project_override_pack_id=None,
        status="active",
        created_by=uuid4(),
    )
    session.add(duplicate_active)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_project_override = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="project_override",
        pack_name="bad-override",
        version="project.v1",
        status="active",
        entity_types=[],
        event_types=[],
        relations=[],
        extraction_hints={},
        risk_rules={},
    )
    session.add(bad_project_override)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_base_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=project.id,
        pack_type="base",
        pack_name="bad-base",
        version="base.v2",
        status="active",
        entity_types=[],
        event_types=[],
        relations=[],
        extraction_hints={},
        risk_rules={},
    )
    session.add(bad_base_pack)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    bad_binding_status = ProjectStorySchemaBinding(
        id=uuid4(),
        project_id=uuid4(),
        base_schema_pack_id=base_pack.id,
        genre_schema_pack_id=None,
        project_override_pack_id=None,
        status="current",
        created_by=None,
    )
    session.add(bad_binding_status)
    with pytest.raises(IntegrityError):
        session.commit()


def test_effective_story_schema_loads_project_binding(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    base_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="base",
        pack_name="base-story-schema",
        version="base.v1",
        status="active",
        entity_types=[{"name": "character"}, {"name": "object"}],
        event_types=["knowledge_change"],
        relations=["owns", "related_to"],
        extraction_hints={},
        risk_rules={},
    )
    genre_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="genre",
        pack_name="mystery",
        version="mystery.v1",
        status="active",
        entity_types=[{"name": "clue", "subtype_of": "object"}],
        event_types=["deduction"],
        relations=["points_to"],
        extraction_hints={},
        risk_rules={},
    )
    binding = ProjectStorySchemaBinding(
        id=uuid4(),
        project_id=project.id,
        base_schema_pack_id=base_pack.id,
        genre_schema_pack_id=genre_pack.id,
        project_override_pack_id=None,
        status="active",
        created_by=None,
    )
    session.add_all([project, base_pack, genre_pack, binding])
    session.commit()

    schema = load_effective_story_schema(session, project.id)

    assert "clue" in schema.entity_types
    assert "deduction" in schema.event_types
    assert schema.allows_relation_for_entity_type("clue", "points_to")
    assert schema.allows_relation_for_entity_type("character", "owns")


def test_job_idempotency_key_is_unique_per_project_and_type(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    first_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="source-delta-1:pipeline-v1",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": "source-delta-1",
        },
    )
    duplicate_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="source-delta-1:pipeline-v1",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": "source-delta-1",
        },
    )

    session.add(project)
    session.add(first_job)
    session.commit()
    session.add(duplicate_job)

    with pytest.raises(IntegrityError):
        session.commit()


def test_job_type_enum_check_is_enforced(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    valid_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="extract_mentions",
        status="queued",
        idempotency_key="extract-mentions:one",
        payload={"pipeline_version": "pipeline-v1", "step": "extract_mentions"},
    )
    invalid_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="provider_call",
        status="queued",
        idempotency_key="provider-call:one",
        payload={"step": "provider_call"},
    )

    session.add_all([project, valid_job])
    session.commit()

    session.add(invalid_job)
    with pytest.raises(IntegrityError):
        session.commit()


def test_project_membership_is_unique_per_actor_and_project(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    first_membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
    duplicate_membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="editor",
        status="active",
    )

    session.add_all([project, first_membership])
    session.commit()
    session.add(duplicate_membership)

    with pytest.raises(IntegrityError):
        session.commit()


def test_write_idempotency_key_is_unique_per_actor_operation_and_project(
    session: Session,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    first_record = IdempotencyRecord(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        operation="accept_candidate",
        idempotency_key="idem-accept",
        request_hash="hash-1",
        response_payload={"source_delta_id": str(uuid4())},
    )
    duplicate_record = IdempotencyRecord(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        operation="accept_candidate",
        idempotency_key="idem-accept",
        request_hash="hash-1",
        response_payload={"source_delta_id": str(uuid4())},
    )

    session.add_all([project, first_record])
    session.commit()
    session.add(duplicate_record)

    with pytest.raises(IntegrityError):
        session.commit()


def test_review_item_and_agent_finding_enum_checks_are_enforced(session: Session) -> None:
    version = create_source_version(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=version.source_id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=12,
        raw_start_offset=0,
        raw_end_offset=12,
        text_preview="Mira stopped.",
        narration_layer="narrator",
    )
    session.add_all([view, span])
    session.commit()

    invalid_review = ReviewItemRecord(
        id=uuid4(),
        project_id=session.get(RawSource, version.source_id).project_id,
        review_type="made_up_conflict",
        severity="high",
        status="open",
        summary="invalid enum",
        affected_refs={},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="review",
    )
    session.add(invalid_review)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    invalid_finding = AgentReviewFindingRecord(
        id=uuid4(),
        project_id=session.get(RawSource, version.source_id).project_id,
        draft_candidate_id=uuid4(),
        risk_level="urgent",
        risk_type="pov_risk",
        summary="invalid level",
        affected_text_ref="object://candidate/span",
        memory_refs={},
        storytelling_refs={},
        can_offer_to_author=False,
        draft_local_only=True,
    )
    session.add(invalid_finding)

    with pytest.raises(IntegrityError):
        session.commit()


def test_agent_review_finding_can_attach_to_action_request_without_candidate(
    session: Session,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        actor_intent="这段有没有 POV 穿帮？",
        trigger="selection",
        action_type="check_risk",
        target={"kind": "selected_text", "range": {"start": 0, "end": 12}},
        constraints={},
        expected_output="risk_findings",
        status="submitted",
        created_by=actor_id,
    )
    finding = AgentReviewFindingRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        draft_candidate_id=None,
        risk_level="high",
        risk_type="pov_risk",
        summary="Selected text leaks forbidden knowledge.",
        affected_text_ref="object://risk/text",
        memory_refs={},
        storytelling_refs={"source": "check_risk"},
        can_offer_to_author=False,
        draft_local_only=True,
    )

    session.add_all([project, membership, action_request, finding])
    session.commit()

    stored = (
        session.query(AgentReviewFindingRecord).filter_by(action_request_id=action_request.id).one()
    )
    assert stored.draft_candidate_id is None


def test_story_alias_event_status_enum_checks_are_enforced(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    low_confidence_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="那个人",
        alias_type="pronoun",
        status="low_confidence",
        scope="scene_local",
        evidence_span_ids=[str(uuid4())],
        confidence=0.2,
    )
    invalid_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="银面人",
        alias_type="title",
        status="globally_merged",
        scope="global",
        evidence_span_ids=[str(uuid4())],
        confidence=0.8,
    )
    session.add_all([project, low_confidence_alias])
    session.commit()

    session.add(invalid_alias)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    invalid_candidate = StoryEventCandidate(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        summary="invalid status",
        participants=[],
        objects=[],
        state_change={},
        evidence_span_ids=[str(uuid4())],
        confidence=0.8,
        aggregation_status="canon",
    )
    session.add(invalid_candidate)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    invalid_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="revelation",
        title="invalid status",
        event_status="merged",
        event_candidate_ids=[str(uuid4())],
        participants=[],
        objects=[],
        summary="invalid canonical event status",
        evidence_span_ids=[str(uuid4())],
    )
    session.add(invalid_event)
    with pytest.raises(IntegrityError):
        session.commit()


def test_story_canonical_entity_schema_checks_are_enforced(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    valid_character = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="minor_supporting",
    )
    session.add_all([project, valid_character])
    session.commit()

    invalid_entity_type = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="vehicle",
        display_name="Nameless Skiff",
        canonical_status="provisional",
    )
    session.add(invalid_entity_type)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    invalid_status = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="object",
        display_name="Lantern Map",
        canonical_status="merged",
    )
    session.add(invalid_status)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()

    location_with_cast_tier = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="canon",
        cast_tier="major",
    )
    session.add(location_with_cast_tier)
    with pytest.raises(IntegrityError):
        session.commit()


def test_canon_fact_requires_promotion_decision(session: Session) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(uuid4())],
        confidence=0.9,
        source_scope="user_draft",
    )
    session.add_all([project, fact])

    with pytest.raises(IntegrityError):
        session.commit()


def test_graph_projection_can_be_deleted_and_rebuilt_from_facts(session: Session) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/fact-graph",
        raw_offset_map_ref="object://offsets/fact-graph",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Mira owns the Lantern Map.",
        narration_layer="narrator",
    )
    policy_decision_id = uuid4()
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=policy_decision_id,
    )
    session.add_all([view, span, fact])
    session.commit()

    first_run = rebuild_graph_projection(session, project_id=raw_source.project_id)
    assert first_run.created_edge_count == 1
    assert session.query(GraphProjectionEdge).count() == 1

    session.query(GraphProjectionEdge).delete()
    session.commit()

    second_run = rebuild_graph_projection(session, project_id=raw_source.project_id)
    edge = session.query(GraphProjectionEdge).one()

    assert second_run.created_edge_count == 1
    assert edge.source_ref == {"type": "fact_assertion", "id": str(fact.id)}
    assert edge.edge_status == "canon"


def test_graph_projection_skips_fact_edges_with_cross_project_evidence(
    session: Session,
) -> None:
    project_version = create_source_version(session)
    evidence_version = create_source_version(session)
    project_source = session.get(RawSource, project_version.source_id)
    evidence_source = session.get(RawSource, evidence_version.source_id)
    assert project_source is not None
    assert evidence_source is not None
    evidence_view = SourceProcessedView(
        id=uuid4(),
        version_id=evidence_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/cross-project-fact",
        raw_offset_map_ref="object://offsets/cross-project-fact",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=evidence_source.id,
        version_id=evidence_version.id,
        view_id=evidence_view.id,
        start_offset=0,
        end_offset=26,
        raw_start_offset=0,
        raw_end_offset=26,
        text_preview="Other project owns the map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project_source.project_id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([evidence_view, cross_project_span, fact])
    session.commit()

    result = rebuild_graph_projection(session, project_id=project_source.project_id)

    assert result.created_edge_count == 0
    assert (
        session.query(GraphProjectionEdge).filter_by(project_id=project_source.project_id).count()
        == 0
    )


def test_graph_projection_state_hash_ignores_non_project_fact_evidence(
    session: Session,
) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    foreign_version = create_source_version(session)
    foreign_source = session.get(RawSource, foreign_version.source_id)
    assert foreign_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/fact-hash",
        raw_offset_map_ref="object://offsets/fact-hash",
        view_status="current",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/foreign-fact-hash",
        raw_offset_map_ref="object://offsets/foreign-fact-hash",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Mira owns the Lantern Map.",
        narration_layer="narrator",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=29,
        raw_start_offset=0,
        raw_end_offset=29,
        text_preview="Other project owns the ledger.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([view, foreign_view, span, foreign_span, fact])
    session.commit()

    first_run = rebuild_graph_projection(session, project_id=raw_source.project_id)
    fact.evidence_span_ids = [str(span.id), str(foreign_span.id), "not-a-source-span-id"]
    session.commit()
    second_run = rebuild_graph_projection(session, project_id=raw_source.project_id)
    edge = session.query(GraphProjectionEdge).one()

    assert second_run.created_edge_count == first_run.created_edge_count == 1
    assert second_run.source_state_hash == first_run.source_state_hash
    assert edge.evidence_refs == [{"type": "source_span", "id": str(span.id)}]


def test_graph_projection_rebuilds_character_knowledge_edges(session: Session) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/knowledge",
        raw_offset_map_ref="object://offsets/knowledge",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=31,
        raw_start_offset=0,
        raw_end_offset=31,
        text_preview="Mira knows the Harbor Code.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=raw_source.project_id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    active = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    active_unknown = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "orrin-identity", "label": "Orrin's identity"},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="does_not_know",
        hidden_from=[],
        status="active",
    )
    superseded = CharacterKnowledge(
        id=uuid4(),
        project_id=raw_source.project_id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "old-map", "label": "Old Map"},
        learned_in_scene_id=None,
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="superseded",
    )
    session.add_all([view, span, mira, active, active_unknown, superseded])
    session.commit()

    result = rebuild_graph_projection(session, project_id=raw_source.project_id)

    edges = session.query(GraphProjectionEdge).order_by(GraphProjectionEdge.relation).all()
    assert result.created_edge_count == 2
    assert session.query(FactAssertionRecord).count() == 0
    assert [
        (
            edge.source_ref,
            edge.subject_ref,
            edge.relation,
            edge.target_ref,
            edge.edge_status,
            edge.evidence_refs,
        )
        for edge in edges
    ] == [
        (
            {"type": "character_knowledge", "id": str(active_unknown.id)},
            {
                "type": "character",
                "id": str(mira.id),
                "label": "Mira",
                "canonical_entity_id": str(mira.id),
            },
            "does_not_know",
            {"type": "secret", "id": "orrin-identity", "label": "Orrin's identity"},
            "canon",
            [{"type": "source_span", "id": str(span.id)}],
        ),
        (
            {"type": "character_knowledge", "id": str(active.id)},
            {
                "type": "character",
                "id": str(mira.id),
                "label": "Mira",
                "canonical_entity_id": str(mira.id),
            },
            "knows",
            {"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
            "canon",
            [{"type": "source_span", "id": str(span.id)}],
        ),
    ]


def test_graph_projection_skips_character_knowledge_with_cross_project_evidence(
    session: Session,
) -> None:
    project_version = create_source_version(session)
    evidence_version = create_source_version(session)
    project_source = session.get(RawSource, project_version.source_id)
    evidence_source = session.get(RawSource, evidence_version.source_id)
    assert project_source is not None
    assert evidence_source is not None
    project_view = SourceProcessedView(
        id=uuid4(),
        version_id=project_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/project-knowledge",
        raw_offset_map_ref="object://offsets/project-knowledge",
        view_status="current",
    )
    evidence_view = SourceProcessedView(
        id=uuid4(),
        version_id=evidence_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/cross-project-knowledge",
        raw_offset_map_ref="object://offsets/cross-project-knowledge",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=evidence_source.id,
        version_id=evidence_version.id,
        view_id=evidence_view.id,
        start_offset=0,
        end_offset=31,
        raw_start_offset=0,
        raw_end_offset=31,
        text_preview="Another project knows the code.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project_source.project_id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    cross_project_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project_source.project_id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        learned_in_scene_id=None,
        evidence_span_id=cross_project_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all(
        [
            project_view,
            evidence_view,
            cross_project_span,
            mira,
            cross_project_knowledge,
        ]
    )
    session.commit()

    result = rebuild_graph_projection(session, project_id=project_source.project_id)

    assert result.created_edge_count == 0
    assert (
        session.query(GraphProjectionEdge).filter_by(project_id=project_source.project_id).count()
        == 0
    )


def test_graph_projection_projects_open_review_item_contradiction_edges(
    session: Session,
) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/contradiction",
        raw_offset_map_ref="object://offsets/contradiction",
        view_status="current",
    )
    old_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=20,
        raw_start_offset=0,
        raw_end_offset=20,
        text_preview="Mira is in Old Harbor.",
        narration_layer="narrator",
    )
    new_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=21,
        end_offset=43,
        raw_start_offset=21,
        raw_end_offset=43,
        text_preview="Mira is in Harbor Nine.",
        narration_layer="narrator",
    )
    character_ref = {"type": "character", "id": "mira", "label": "Mira"}
    old_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        subject_ref=character_ref,
        predicate="located_in",
        object_ref={"type": "location", "id": "old-harbor", "label": "Old Harbor"},
        fact_status="canon",
        evidence_span_ids=[str(old_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    new_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        subject_ref=character_ref,
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="disputed",
        evidence_span_ids=[str(new_span.id)],
        confidence=0.7,
        source_scope="user_draft",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        review_type="canon_conflict",
        severity="medium",
        status="open",
        summary="Mira cannot be in both locations.",
        affected_refs={"fact_id": str(new_fact.id)},
        new_evidence={"source_span_ids": [str(new_span.id)]},
        existing_evidence={
            "fact_id": str(old_fact.id),
            "source_span_ids": [str(old_span.id)],
        },
        suggested_actions=[{"resolution": "accept"}, {"resolution": "reject"}],
        default_action="review",
    )
    session.add_all([view, old_span, new_span, old_fact, new_fact, review])
    session.commit()

    result = rebuild_graph_projection(session, project_id=raw_source.project_id)

    contradiction = session.query(GraphProjectionEdge).filter_by(relation="contradicts").one()
    assert result.created_edge_count == 3
    assert session.query(GraphProjectionEdge).count() == 3
    assert contradiction.source_ref == {"type": "review_item", "id": str(review.id)}
    assert contradiction.subject_ref == {
        "type": "review_item",
        "id": str(review.id),
        "review_type": "canon_conflict",
        "severity": "medium",
        "status": "open",
        "affected_fact_id": str(new_fact.id),
    }
    assert contradiction.target_ref == {
        "type": "fact_assertion",
        "id": str(old_fact.id),
        "predicate": "located_in",
    }
    assert contradiction.edge_status == "disputed"
    assert contradiction.evidence_refs == [
        {"type": "source_span", "id": str(new_span.id)},
        {"type": "source_span", "id": str(old_span.id)},
    ]
    assert session.query(FactAssertionRecord).count() == 2


def test_graph_projection_skips_review_contradiction_edges_with_cross_project_evidence(
    session: Session,
) -> None:
    project_version = create_source_version(session)
    evidence_version = create_source_version(session)
    project_source = session.get(RawSource, project_version.source_id)
    evidence_source = session.get(RawSource, evidence_version.source_id)
    assert project_source is not None
    assert evidence_source is not None
    project_view = SourceProcessedView(
        id=uuid4(),
        version_id=project_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/review-project",
        raw_offset_map_ref="object://offsets/review-project",
        view_status="current",
    )
    old_span = SourceSpan(
        id=uuid4(),
        source_id=project_source.id,
        version_id=project_version.id,
        view_id=project_view.id,
        start_offset=0,
        end_offset=20,
        raw_start_offset=0,
        raw_end_offset=20,
        text_preview="Mira is in Old Harbor.",
        narration_layer="narrator",
    )
    new_span = SourceSpan(
        id=uuid4(),
        source_id=project_source.id,
        version_id=project_version.id,
        view_id=project_view.id,
        start_offset=21,
        end_offset=43,
        raw_start_offset=21,
        raw_end_offset=43,
        text_preview="Mira is in Harbor Nine.",
        narration_layer="narrator",
    )
    evidence_view = SourceProcessedView(
        id=uuid4(),
        version_id=evidence_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/review-cross-project",
        raw_offset_map_ref="object://offsets/review-cross-project",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=evidence_source.id,
        version_id=evidence_version.id,
        view_id=evidence_view.id,
        start_offset=0,
        end_offset=32,
        raw_start_offset=0,
        raw_end_offset=32,
        text_preview="Other project contradiction evidence.",
        narration_layer="narrator",
    )
    character_ref = {"type": "character", "id": "mira", "label": "Mira"}
    old_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project_source.project_id,
        subject_ref=character_ref,
        predicate="located_in",
        object_ref={"type": "location", "id": "old-harbor", "label": "Old Harbor"},
        fact_status="canon",
        evidence_span_ids=[str(old_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    new_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project_source.project_id,
        subject_ref=character_ref,
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="disputed",
        evidence_span_ids=[str(new_span.id)],
        confidence=0.7,
        source_scope="user_draft",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project_source.project_id,
        review_type="canon_conflict",
        severity="medium",
        status="open",
        summary="Mira cannot be in both locations.",
        affected_refs={"fact_id": str(new_fact.id)},
        new_evidence={"source_span_ids": [str(cross_project_span.id)]},
        existing_evidence={
            "fact_id": str(old_fact.id),
            "source_span_ids": [str(cross_project_span.id)],
        },
        suggested_actions=[{"resolution": "accept"}, {"resolution": "reject"}],
        default_action="review",
    )
    session.add_all(
        [
            project_view,
            old_span,
            new_span,
            evidence_view,
            cross_project_span,
            old_fact,
            new_fact,
            review,
        ]
    )
    session.commit()

    result = rebuild_graph_projection(session, project_id=project_source.project_id)

    review_edges = (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project_source.project_id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .all()
    )
    assert result.created_edge_count == 2
    assert review_edges == []
    assert (
        session.query(GraphProjectionEdge).filter_by(project_id=project_source.project_id).count()
        == 2
    )


def test_graph_projection_rebuilds_edges_from_canonical_event_structure(
    session: Session,
) -> None:
    version = create_source_version(session)
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/event-graph",
        raw_offset_map_ref="object://offsets/event-graph",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=51,
        raw_start_offset=0,
        raw_end_offset=51,
        text_preview="Mira and Orrin find the Lantern Map in Harbor Nine.",
        narration_layer="narrator",
    )
    location = StoryCanonicalEntity(
        id=uuid4(),
        project_id=raw_source.project_id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="canon",
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=raw_source.project_id,
        event_type="discovery",
        title="Lantern Map found",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "orrin", "label": "Orrin"},
        ],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=location.id,
        story_time="Chapter 1",
        summary="Mira and Orrin find the Lantern Map in Harbor Nine.",
        consequence_summary=None,
        evidence_span_ids=[str(span.id)],
    )
    session.add_all([view, span, location, event])
    session.commit()

    result = rebuild_graph_projection(session, project_id=raw_source.project_id)

    edges = session.query(GraphProjectionEdge).order_by(GraphProjectionEdge.relation).all()
    edge_keys = {
        (
            edge.subject_ref["type"],
            edge.subject_ref["id"],
            edge.relation,
            edge.target_ref["type"],
            edge.target_ref["id"],
        )
        for edge in edges
    }
    assert result.created_edge_count == 4
    assert len(edges) == 4
    assert edge_keys == {
        ("character", "mira", "present_at", "event", str(event.id)),
        ("character", "orrin", "present_at", "event", str(event.id)),
        ("event", str(event.id), "occurred_at", "location", str(location.id)),
        ("event", str(event.id), "involves_object", "object", "lantern-map"),
    }
    assert {edge.source_ref["type"] for edge in edges} == {"canonical_event"}
    expected_evidence_refs = [{"type": "source_span", "id": event.evidence_span_ids[0]}]
    assert all(edge.evidence_refs == expected_evidence_refs for edge in edges)
    assert all(edge.edge_status == "canon" for edge in edges)


def test_graph_projection_skips_canonical_event_edges_with_cross_project_evidence(
    session: Session,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    evidence_version = create_source_version(session)
    evidence_source = session.get(RawSource, evidence_version.source_id)
    assert evidence_source is not None
    evidence_view = SourceProcessedView(
        id=uuid4(),
        version_id=evidence_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/cross-project-event",
        raw_offset_map_ref="object://offsets/cross-project-event",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=evidence_source.id,
        version_id=evidence_version.id,
        view_id=evidence_view.id,
        start_offset=0,
        end_offset=29,
        raw_start_offset=0,
        raw_end_offset=29,
        text_preview="Other project event evidence.",
        narration_layer="narrator",
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="discovery",
        title="Lantern Map found",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira", "label": "Mira"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="Chapter 1",
        summary="Mira finds the Lantern Map.",
        consequence_summary=None,
        evidence_span_ids=[str(cross_project_span.id)],
    )
    session.add_all([project, evidence_view, cross_project_span, event])
    session.commit()

    result = rebuild_graph_projection(session, project_id=project.id)

    assert result.created_edge_count == 0
    assert session.query(GraphProjectionEdge).filter_by(project_id=project.id).count() == 0
