from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sextant.api.app import create_app
from sextant.application.errors import ApplicationError
from sextant.application.use_cases import RunActionRequest
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.contracts.use_cases import (
    BeatCandidateDraft,
    PersistActionRequestBeatCandidatesInput,
    RunActionRequestInput,
)
from sextant.infra.db.models import (
    AgentActionRequestRecord,
    AgentBeatCandidateRecord,
    AgentContextPackRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    AuditEvent,
    Base,
    FactAssertionRecord,
    IdempotencyRecord,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SkillRun,
    SourceDeltaRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryChapter,
    StoryScene,
)
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.skills.local_story_draft import LocalStoryDraftProvider
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


def uow_factory(session: Session):
    return lambda: SqlAlchemyUnitOfWork(session)


def seed_source_span(
    session: Session,
    *,
    raw_source: RawSource,
    version: SourceVersion,
    text_preview: str,
    slug: str,
) -> SourceSpan:
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref=f"object://processed/{slug}.md",
        raw_offset_map_ref=f"object://processed/{slug}.offsets.json",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=len(text_preview),
        raw_start_offset=0,
        raw_end_offset=len(text_preview),
        text_preview=text_preview,
        narration_layer="narrator",
    )
    session.add_all([view, span])
    session.flush()
    return span


def _assert_failed_skill_run_attempts(
    session: Session,
    *,
    message: str,
    structured_text: str | None = None,
) -> None:
    skill_runs = sorted(
        session.query(SkillRun).all(),
        key=lambda run: run.validation_result["attempt"],
    )
    assert len(skill_runs) == 2
    for expected_attempt, skill_run in enumerate(skill_runs, start=1):
        assert skill_run.status == "failed_terminal"
        if structured_text is not None:
            assert skill_run.structured_output["text"] == structured_text
        assert skill_run.validation_result == {
            "status": "invalid",
            "error_code": "llm_output_invalid",
            "message": message,
            "attempt": expected_attempt,
            "max_attempts": 2,
            "will_retry": expected_attempt < 2,
        }


def seed_action_request(
    session: Session,
    *,
    constraints: dict[str, object] | None = None,
) -> tuple[Project, UUID, RawSource, SourceVersion, AgentActionRequestRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
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
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="让米拉继续推进这一页，但不要泄露奥林的身份。",
        trigger="toolbar",
        action_type="draft_next_passage",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 12, "end": 38},
        },
        constraints=constraints or {},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all([project, membership, raw_source, version, action_request])
    session.commit()
    return project, actor_id, raw_source, version, action_request


def seed_memory_answer_action_request(
    session: Session,
) -> tuple[Project, UUID, AgentActionRequestRecord]:
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
        actor_intent="米拉知道钥匙是谁给的吗？",
        trigger="natural_language",
        action_type="ask_memory",
        target=None,
        constraints={"subject_ref": {"type": "character", "id": "mira"}},
        expected_output="memory_answer",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all([project, membership, action_request])
    session.commit()
    return project, actor_id, action_request


def seed_check_risk_action_request(
    session: Session,
) -> tuple[Project, UUID, RawSource, SourceVersion, AgentActionRequestRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
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
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="这段有没有 POV 穿帮？",
        trigger="selection",
        action_type="check_risk",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 12, "end": 38},
        },
        constraints={},
        expected_output="risk_findings",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all([project, membership, raw_source, version, action_request])
    session.commit()
    return project, actor_id, raw_source, version, action_request


def seed_suggest_next_direction_action_request(
    session: Session,
) -> tuple[Project, UUID, RawSource, SourceVersion, AgentActionRequestRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
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
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="下面可以发生什么？",
        trigger="natural_language",
        action_type="suggest_next_direction",
        target={
            "kind": "cursor_position",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 38, "end": 38},
        },
        constraints={"length": "short"},
        expected_output="beat_candidates",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all([project, membership, raw_source, version, action_request])
    session.commit()
    return project, actor_id, raw_source, version, action_request


def seed_explain_candidate_action_request(
    session: Session,
) -> tuple[Project, UUID, AgentActionRequestRecord, AgentDraftCandidateRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
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
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/explain-candidate.md",
        raw_offset_map_ref="object://processed/explain-candidate.offsets.json",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="候选解释引用的真实上下文。",
        narration_layer="narrator",
    )
    original_action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="把这段写得更克制",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 6},
        },
        constraints={"keep_thread_open": True},
        expected_output="draft_candidate",
        status="succeeded",
        created_by=actor_id,
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=original_action_request.id,
        mode="rewrite_span",
        candidate_text_ref="object://candidate/explain",
        context_pack_id=uuid4(),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        target_scene_id=None,
        affected_range={"start": 0, "end": 6},
        base_hash="base-hash",
        memory_refs=[{"type": "source_span", "id": str(span.id)}],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
        status="offered_to_author",
    )
    finding = AgentReviewFindingRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=original_action_request.id,
        draft_candidate_id=candidate.id,
        risk_level="medium",
        risk_type="canon_risk",
        summary="候选避开了未确认钥匙来源。",
        affected_text_ref="object://candidate/explain",
        memory_refs={"source_span_id": str(span.id)},
        storytelling_refs={"control": "keep_thread_open"},
        suggested_revision="继续保持悬念开放。",
        can_offer_to_author=True,
        maps_to_review_type_if_accepted="canon_conflict",
        draft_local_only=True,
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        actor_intent="为什么这个候选合理？",
        trigger="candidate_action",
        action_type="explain_candidate",
        target={"kind": "candidate", "candidate_id": str(candidate.id)},
        constraints={},
        expected_output="candidate_explanation",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all(
        [
            project,
            membership,
            raw_source,
            version,
            view,
            span,
            original_action_request,
            candidate,
            finding,
            action_request,
        ]
    )
    session.commit()
    return project, actor_id, action_request, candidate


def seed_revise_candidate_action_request(
    session: Session,
    object_store: LocalObjectStore,
) -> tuple[Project, UUID, AgentActionRequestRecord, AgentDraftCandidateRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
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
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/revise-candidate.md",
        raw_offset_map_ref="object://processed/revise-candidate.offsets.json",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="候选修订引用的真实上下文。",
        narration_layer="narrator",
    )
    original_action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="selection",
        action_type="rewrite_span",
        target={"kind": "selected_text", "range": {"start": 0, "end": 6}},
        constraints={},
        expected_output="draft_candidate",
        status="succeeded",
        created_by=actor_id,
    )
    candidate_text_ref = object_store.put_text(
        "candidates/original-revision-source.txt",
        "米拉几乎说出钥匙的来源，又把话咽回去。",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=original_action_request.id,
        mode="rewrite_span",
        candidate_text_ref=candidate_text_ref,
        context_pack_id=None,
        target_source_id=raw_source.id,
        target_version_id=version.id,
        target_scene_id=None,
        affected_range={"start": 0, "end": 6},
        base_hash="hash-v1",
        memory_refs=[{"type": "source_span", "id": str(span.id)}],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
        status="offered_to_author",
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="别关闭钥匙来源这个悬念。",
        trigger="candidate_action",
        action_type="revise_candidate",
        target={"kind": "candidate", "candidate_id": str(candidate.id)},
        constraints={"keep_thread_open": True},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all(
        [
            project,
            membership,
            raw_source,
            version,
            view,
            span,
            original_action_request,
            candidate,
            action_request,
        ]
    )
    session.commit()
    return project, actor_id, action_request, candidate


def run_use_case(
    session: Session,
    object_store: LocalObjectStore,
    action_request: AgentActionRequestRecord,
    actor_id: UUID,
    *,
    idempotency_key: str = "idem-run-action",
    current_text_window: str = "米拉停在西档案室门口。",
):
    return RunActionRequest(
        uow_factory(session),
        object_store,
        LocalStoryDraftProvider(),
    ).execute(
        RunActionRequestInput(
            project_id=action_request.project_id,
            actor_id=actor_id,
            request_id=f"req-{idempotency_key}",
            idempotency_key=idempotency_key,
            action_request_id=action_request.id,
            current_text_window=current_text_window,
        )
    )


def test_run_action_request_creates_draft_local_candidate_without_memory_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(session)

    output = run_use_case(session, object_store, action_request, actor_id)

    assert output.status == "succeeded"
    assert len(output.draft_candidate_ids) == 1
    candidate = session.get(AgentDraftCandidateRecord, output.draft_candidate_ids[0])
    assert candidate is not None
    assert candidate.status == "offered_to_author"
    assert candidate.context_pack_id == output.context_pack_id
    assert candidate.affected_range == {"start": 12, "end": 38}
    assert candidate.base_hash == "hash-v1"
    assert "米拉" in object_store.get_text(candidate.candidate_text_ref)
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(AgentStorytellingControlRecord).count() >= 4
    assert session.query(SkillRun).filter_by(skill_name="local_story_draft").count() == 1
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_storytelling_controls_derive_mode_pressure_and_role_from_current_context(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(
        session,
        constraints={
            "new_character_policy": "allow_local",
            "hard_no": ["不要揭露奥林的真实身份"],
        },
    )

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-derived-storytelling-controls",
        current_text_window="米拉意识到地图已经暴露。她停下来，必须决定是否回头。",
    )

    assert output.status == "succeeded"
    controls = {
        control.control_type: control.payload
        for control in session.query(AgentStorytellingControlRecord).all()
    }
    serialized_controls = json.dumps(controls, ensure_ascii=False, sort_keys=True)
    assert "locked archive room" not in serialized_controls
    assert "local-pressure" not in serialized_controls
    assert "Mira chooses action instead of exposition" not in serialized_controls

    scene_sequel = controls["scene_sequel_mode"]
    assert scene_sequel["passage_mode"] == "sequel"
    assert scene_sequel["mode_rationale"]
    assert "地图已经暴露" in scene_sequel["current_pressure"]
    assert scene_sequel["reaction"]
    assert scene_sequel["dilemma"]
    assert scene_sequel["decision"]
    assert scene_sequel["new_goal"]

    role_slot = controls["role_slot"]
    assert role_slot["role_slot_id"] != "local-pressure"
    assert role_slot["scene_need"] == scene_sequel["current_pressure"]
    assert role_slot["function"] == controls["new_character_seed"]["role_function"]
    assert controls["new_character_seed"]["scope"] == "scene_local"

    prose_contract = controls["prose_rendering_contract"]
    assert prose_contract["passage_mode"] == "sequel"
    assert prose_contract["opposition"] == scene_sequel["opposition"]
    assert prose_contract["required_turn"] == scene_sequel["required_turn"]
    assert prose_contract["ending_shape"] == scene_sequel["ending_shape"]
    assert prose_contract["role_slots"] == [role_slot]
    assert prose_contract["character_casting_decisions"] == [controls["character_casting_decision"]]

    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(StoryCanonicalEntity).count() == 0


def test_storytelling_role_function_does_not_treat_seed_location_as_gatekeeper(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(
        session,
        constraints={"new_character_policy": "allow_local"},
    )

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-seed-location-not-gatekeeper",
        current_text_window="雨声压住屋顶。档案室仍旧昏暗。纸页被风吹动。",
    )

    assert output.status == "succeeded"
    controls = {
        control.control_type: control.payload
        for control in session.query(AgentStorytellingControlRecord).all()
    }
    assert controls["role_slot"]["function"] == "pressure_source"
    assert controls["new_character_seed"]["role_function"] == "pressure_source"
    assert controls["new_character_seed"]["display_hint"] == "局部施压者"
    assert "档案室仍旧昏暗" in controls["role_slot"]["scene_need"]


def test_run_ask_memory_action_request_returns_answer_without_candidate_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, action_request = seed_memory_answer_action_request(session)

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-ask-memory",
    )

    assert output.output_type == "memory_answer"
    assert output.status == "succeeded"
    assert output.context_pack_id is None
    assert output.draft_candidate_ids == []
    assert output.risk_finding_ids == []
    assert output.memory_answer is not None
    assert output.memory_answer.answer_type == "unknown"
    assert output.memory_answer.question == "米拉知道钥匙是谁给的吗？"
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(AgentStorytellingControlRecord).count() == 0
    assert session.query(SkillRun).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1


def test_run_ask_memory_action_request_passes_scene_context_to_alias_narrowing(
    session: Session, object_store: LocalObjectStore
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
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    observatory_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=80,
    )
    archive_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=81,
        end_offset=170,
    )
    observatory_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=observatory_scene.id,
        start_offset=10,
        end_offset=55,
        raw_start_offset=10,
        raw_end_offset=55,
        text_preview="In the observatory, Starling hides the prism ledger.",
        narration_layer="narrator",
    )
    archive_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=archive_scene.id,
        start_offset=90,
        end_offset=140,
        raw_start_offset=90,
        raw_end_offset=140,
        text_preview="In the archive, Starling palms the brass knife.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=mira.id,
        alias_type="codename",
        status="proposed",
        scope="scene_local",
        evidence_span_ids=[str(observatory_alias_span.id)],
        confidence=0.73,
    )
    myra_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=myra.id,
        alias_type="codename",
        status="proposed",
        scope="scene_local",
        evidence_span_ids=[str(archive_alias_span.id)],
        confidence=0.71,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(observatory_alias_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(archive_alias_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        scene_id=observatory_scene.id,
        actor_intent="What does Starling own?",
        trigger="natural_language",
        action_type="ask_memory",
        target=None,
        constraints={},
        expected_output="memory_answer",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all(
        [
            project,
            membership,
            raw_source,
            version,
            view,
            chapter,
            observatory_scene,
            archive_scene,
            observatory_alias_span,
            archive_alias_span,
            mira,
            myra,
            mira_alias,
            myra_alias,
            mira_fact,
            myra_fact,
            action_request,
        ]
    )
    session.commit()

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-ask-memory-scene-alias",
        current_text_window="",
    )

    assert output.output_type == "memory_answer"
    assert output.status == "succeeded"
    assert output.context_pack_id is None
    assert output.draft_candidate_ids == []
    assert output.risk_finding_ids == []
    assert output.memory_answer is not None
    assert output.memory_answer.answer_type == "canon"
    assert output.memory_answer.answer == "Mira Vale owns ledger"
    assert output.memory_answer.source_span_refs == [
        {"type": "source_span", "id": str(observatory_alias_span.id)}
    ]
    assert output.memory_answer.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.memory_answer.caveats == ["scene_local_alias_context"]
    assert output.memory_answer.confidence == 0.73
    assert output.memory_answer.safe_to_use_in_current_pov is True
    assert "knife" not in output.memory_answer.answer
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(AgentStorytellingControlRecord).count() == 0
    assert session.query(SkillRun).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1


def test_run_check_risk_action_request_returns_findings_without_candidate_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_check_risk_action_request(
        session
    )

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-check-risk",
        current_text_window="这句写成 risk-context 已经坐实了秘密。",
    )

    assert output.output_type == "risk_findings"
    assert output.status == "succeeded"
    assert output.context_pack_id is None
    assert output.draft_candidate_ids == []
    assert len(output.risk_finding_ids) == 1
    assert output.risk_findings is not None
    assert output.risk_findings[0].risk_type == "canon_risk"
    finding = session.get(AgentReviewFindingRecord, output.risk_finding_ids[0])
    assert finding is not None
    assert finding.action_request_id == action_request.id
    assert finding.draft_candidate_id is None
    assert finding.draft_local_only is True
    assert "risk-context" in object_store.get_text(finding.affected_text_ref)
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(AgentStorytellingControlRecord).count() == 0
    assert session.query(SkillRun).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1


def test_run_suggest_next_direction_returns_persisted_beat_candidates_without_text_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = (
        seed_suggest_next_direction_action_request(session)
    )

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-suggest-next",
        current_text_window="米拉停在西档案室门口。",
    )

    assert output.output_type == "beat_candidates"
    assert output.status == "succeeded"
    assert output.context_pack_id is not None
    assert output.draft_candidate_ids == []
    assert output.risk_finding_ids == []
    assert output.beat_candidate_ids
    assert output.beat_candidates is not None
    assert output.beat_candidates[0].summary
    assert output.beat_candidates[0].driver_character
    assert output.beat_candidates[0].memory_refs == output.beat_candidates[0].evidence_refs
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(AgentStorytellingControlRecord).count() >= 4
    assert session.query(SkillRun).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    beat_count = session.execute(text("select count(*) from agent_beat_candidates")).scalar_one()
    assert beat_count == 1
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1


def test_persist_beat_candidates_filters_invalid_source_span_refs(session: Session) -> None:
    project, actor_id, raw_source, version, action_request = (
        seed_suggest_next_direction_action_request(session)
    )
    valid_span = seed_source_span(
        session,
        raw_source=raw_source,
        version=version,
        text_preview="The next beat is anchored in verified local context.",
        slug="beat-candidate-valid-source-ref",
    )
    _other_project, _other_actor_id, other_source, other_version, _other_request = (
        seed_suggest_next_direction_action_request(session)
    )
    cross_project_span = seed_source_span(
        session,
        raw_source=other_source,
        version=other_version,
        text_preview="Another project anchors a different beat.",
        slug="beat-candidate-cross-project-source-ref",
    )
    raw_refs = [
        {"type": "source_span", "id": str(valid_span.id)},
        {"type": "source_span", "id": str(cross_project_span.id)},
        {"type": "source_span", "id": "not-a-source-span-id"},
    ]

    with SqlAlchemyUnitOfWork(session) as uow:
        output = uow.persist_action_request_beat_candidates(
            PersistActionRequestBeatCandidatesInput(
                project_id=project.id,
                actor_id=actor_id,
                action_request_id=action_request.id,
                context_pack_id=uuid4(),
                target_source_id=raw_source.id,
                target_version_id=version.id,
                target_scene_id=None,
                affected_range={"start": 0, "end": 12},
                base_hash=version.raw_hash,
                controls=[],
                beat_candidates=[
                    BeatCandidateDraft(
                        summary="Stay with the current unresolved choice.",
                        driver_character="current protagonist",
                        agency_rationale="The character still chooses the next action.",
                        storytelling_rationale="The beat keeps the thread open.",
                        cast_decision={"policy": "reuse_current_cast"},
                        tension="The decision remains unresolved.",
                        memory_refs=raw_refs,
                        evidence_refs=raw_refs,
                    )
                ],
            )
        )
        uow.commit()

    assert output.beat_candidates is not None
    expected_refs = [{"type": "source_span", "id": str(valid_span.id)}]
    assert output.beat_candidates[0].memory_refs == expected_refs
    assert output.beat_candidates[0].evidence_refs == expected_refs
    assert str(cross_project_span.id) not in json.dumps(
        {
            "memory_refs": output.beat_candidates[0].memory_refs,
            "evidence_refs": output.beat_candidates[0].evidence_refs,
        },
        sort_keys=True,
    )
    stored_beat = session.get(AgentBeatCandidateRecord, output.beat_candidate_ids[0])
    assert stored_beat is not None
    assert stored_beat.memory_refs == raw_refs
    assert stored_beat.evidence_refs == raw_refs


def test_run_explain_candidate_returns_explanation_without_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, action_request, candidate = seed_explain_candidate_action_request(session)

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-explain-candidate",
        current_text_window="",
    )
    replayed = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-explain-candidate",
        current_text_window="",
    )

    assert output.output_type == "candidate_explanation"
    assert replayed == output
    assert output.status == "succeeded"
    assert output.draft_candidate_ids == []
    assert output.risk_finding_ids == []
    assert output.beat_candidate_ids == []
    assert output.candidate_explanation is not None
    assert output.candidate_explanation.candidate_id == candidate.id
    assert output.candidate_explanation.used_memory_refs == candidate.memory_refs
    assert output.candidate_explanation.risks[0].risk_type == "canon_risk"
    assert "未确认" in output.candidate_explanation.avoided_claims[0]
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 1
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(AgentStorytellingControlRecord).count() == 0
    assert session.query(SkillRun).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="action_request.run").count() == 1


def test_run_revise_candidate_returns_replacement_candidate_without_memory_side_effects(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, action_request, original_candidate = seed_revise_candidate_action_request(
        session, object_store
    )

    output = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-revise-candidate",
        current_text_window="作者要求保留钥匙来源悬念。",
    )
    replayed = run_use_case(
        session,
        object_store,
        action_request,
        actor_id,
        idempotency_key="idem-run-revise-candidate",
        current_text_window="作者要求保留钥匙来源悬念。",
    )

    assert output.output_type == "draft_candidates"
    assert replayed == output
    assert output.status == "succeeded"
    assert len(output.draft_candidate_ids) == 1
    replacement = session.get(AgentDraftCandidateRecord, output.draft_candidate_ids[0])
    assert replacement is not None
    assert replacement.action_request_id == action_request.id
    assert replacement.target_source_id == original_candidate.target_source_id
    assert replacement.target_version_id == original_candidate.target_version_id
    assert object_store.get_text(replacement.candidate_text_ref)
    stored_original = session.get(AgentDraftCandidateRecord, original_candidate.id)
    assert stored_original.status == "revised"
    assert stored_original.author_action == "revise"
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    assert session.query(AgentDraftCandidateRecord).count() == 2
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(AgentStorytellingControlRecord).count() >= 4
    assert session.query(SkillRun).count() == 1
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="action_request.run").count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="action_request.run").count() == 1


def test_run_revise_candidate_rejects_blank_provider_output_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    _project, actor_id, action_request, _original_candidate = seed_revise_candidate_action_request(
        session, object_store
    )

    with pytest.raises(ApplicationError) as error:
        RunActionRequest(
            uow_factory(session),
            object_store,
            BlankStoryProvider(),
        ).execute(
            RunActionRequestInput(
                project_id=action_request.project_id,
                actor_id=actor_id,
                request_id="req-blank-revision",
                idempotency_key="idem-blank-revision",
                action_request_id=action_request.id,
                current_text_window="米拉停在西档案室门口。",
            )
        )

    assert error.value.code == "llm_output_invalid"
    assert error.value.message == "Story draft provider returned empty text."
    assert session.get(AgentActionRequestRecord, action_request.id).status == "submitted"
    assert session.query(AgentDraftCandidateRecord).count() == 1
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned empty text.",
        structured_text="   ",
    )
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_run_revise_candidate_retries_invalid_provider_output_before_persisting_revision(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    _project, actor_id, action_request, original_candidate = seed_revise_candidate_action_request(
        session, object_store
    )
    provider = InvalidThenValidStoryProvider()

    output = RunActionRequest(
        uow_factory(session),
        object_store,
        provider,
    ).execute(
        RunActionRequestInput(
            project_id=action_request.project_id,
            actor_id=actor_id,
            request_id="req-retry-revision",
            idempotency_key="idem-retry-revision",
            action_request_id=action_request.id,
            current_text_window="米拉停在西档案室门口。",
        )
    )

    assert provider.call_count == 2
    assert output.status == "succeeded"
    assert len(output.draft_candidate_ids) == 1
    assert session.get(AgentDraftCandidateRecord, original_candidate.id).status == "revised"
    skill_runs = session.query(SkillRun).all()
    assert len(skill_runs) == 2
    failed_skill_run = next(run for run in skill_runs if run.status == "failed_terminal")
    succeeded_skill_run = next(run for run in skill_runs if run.status == "succeeded")
    assert failed_skill_run.validation_result == {
        "status": "invalid",
        "error_code": "llm_output_invalid",
        "message": "Story draft provider returned empty text.",
        "attempt": 1,
        "max_attempts": 2,
        "will_retry": True,
    }
    assert succeeded_skill_run.validation_result == {"status": "valid"}
    assert session.query(AgentDraftCandidateRecord).count() == 2
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_run_action_request_replays_idempotently_without_duplicate_candidates(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(session)

    first = run_use_case(session, object_store, action_request, actor_id)
    second = run_use_case(session, object_store, action_request, actor_id)

    assert second == first
    assert session.query(AgentDraftCandidateRecord).count() == 1
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="action_request.run").count() == 1


def test_run_action_request_ignores_forced_risk_constraint_from_action_request(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(
        session,
        constraints={"force_risk_fact_in_draft": True},
    )

    output = run_use_case(session, object_store, action_request, actor_id)

    candidate = session.get(AgentDraftCandidateRecord, output.draft_candidate_ids[0])
    controls = {
        control.control_type: control.payload
        for control in session.query(AgentStorytellingControlRecord).all()
    }
    assert candidate.status == "offered_to_author"
    assert "force_risk_fact_in_draft" not in controls["prose_rendering_contract"]
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_new_character_seed_is_control_only_until_accepted_text_enters_memory(
    session: Session, object_store: LocalObjectStore
) -> None:
    _project, actor_id, _raw_source, _version, action_request = seed_action_request(
        session,
        constraints={"new_character_policy": "allow_local"},
    )

    output = run_use_case(session, object_store, action_request, actor_id)

    assert output.status == "succeeded"
    seed_control = (
        session.query(AgentStorytellingControlRecord)
        .filter_by(control_type="new_character_seed")
        .one()
    )
    assert seed_control.payload["scope"] == "scene_local"
    assert seed_control.payload["promotion_hint"] == "memory_ingest_after_acceptance_only"
    assert session.query(StoryCanonicalEntity).count() == 0


def test_action_request_run_endpoint_returns_candidate_ids(
    session: Session, object_store: LocalObjectStore
) -> None:
    project, actor_id, _raw_source, _version, action_request = seed_action_request(session)
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-action",
            "Idempotency-Key": "idem-api-run-action",
        },
        json={"current_text_window": "米拉停在西档案室门口。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert len(body["draft_candidate_ids"]) == 1

    detail_response = client.get(
        f"/api/projects/{project.id}/candidates/{body['draft_candidate_ids'][0]}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "offered_to_author"
    assert "为了继续推进眼前这一拍" in detail["text"]
    assert "米拉" in detail["text"]
    assert detail["target_source_id"] == str(_raw_source.id)
    assert detail["target_version_id"] == str(_version.id)
    assert detail["affected_range"] == {"start": 12, "end": 38}
    assert detail["base_hash"] == "hash-v1"
    assert detail["agent_review_findings"] == []


def test_ask_memory_action_request_run_endpoint_returns_memory_answer_without_story_provider(
    session: Session,
) -> None:
    project, actor_id, action_request = seed_memory_answer_action_request(session)
    client = TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-ask-memory",
            "Idempotency-Key": "idem-api-run-ask-memory",
        },
        json={"current_text_window": ""},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == "memory_answer"
    assert body["status"] == "succeeded"
    assert body["context_pack_id"] is None
    assert body["draft_candidate_ids"] == []
    assert body["risk_finding_ids"] == []
    assert body["memory_answer"]["answer_type"] == "unknown"
    assert body["memory_answer"]["source_span_refs"] == []


def test_check_risk_action_request_run_endpoint_returns_risk_findings_without_story_provider(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, actor_id, _raw_source, _version, action_request = seed_check_risk_action_request(
        session
    )
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-check-risk",
            "Idempotency-Key": "idem-api-run-check-risk",
        },
        json={"current_text_window": "这句写成 risk-context 已经坐实了秘密。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == "risk_findings"
    assert body["status"] == "succeeded"
    assert body["context_pack_id"] is None
    assert body["draft_candidate_ids"] == []
    assert len(body["risk_finding_ids"]) == 1
    assert body["risk_findings"][0]["risk_type"] == "canon_risk"
    assert body["risk_findings"][0]["draft_local_only"] is True


def test_suggest_next_direction_run_endpoint_returns_beat_candidates(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, actor_id, _raw_source, _version, action_request = (
        seed_suggest_next_direction_action_request(session)
    )
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-suggest-next",
            "Idempotency-Key": "idem-api-run-suggest-next",
        },
        json={"current_text_window": "米拉停在西档案室门口。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == "beat_candidates"
    assert body["status"] == "succeeded"
    assert body["context_pack_id"] is not None
    assert body["draft_candidate_ids"] == []
    assert len(body["beat_candidate_ids"]) == 1
    assert body["beat_candidates"][0]["summary"]
    assert body["beat_candidates"][0]["driver_character"]


@pytest.mark.parametrize(
    ("path", "action_type", "expected_output", "output_type"),
    [
        ("suggest-next-beat", "suggest_next_direction", "beat_candidates", "beat_candidates"),
        ("draft-next-passage", "draft_next_passage", "draft_candidates", "draft_candidates"),
        ("rewrite-current-page", "rewrite_current_page", "draft_candidates", "draft_candidates"),
        ("check-risk", "check_risk", "risk_findings", "risk_findings"),
    ],
)
def test_agent_wrapper_endpoints_submit_and_run_canonical_action_request(
    session: Session,
    object_store: LocalObjectStore,
    path: str,
    action_type: str,
    expected_output: str,
    output_type: str,
) -> None:
    project, actor_id, raw_source, version, _action_request = seed_action_request(session)
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/agent/{path}",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": f"req-api-agent-wrapper-{path}",
            "Idempotency-Key": f"idem-api-agent-wrapper-{path}",
        },
        json={
            "trigger": "toolbar",
            "target": {
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 12, "end": 38},
            },
            "constraints": {"tone": "克制"},
            "actor_intent": "检查这一段。" if action_type == "check_risk" else "继续这一段。",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "current_text_window": "这句写成 risk-context 已经坐实了秘密。"
            if action_type == "check_risk"
            else "米拉停在西档案室门口。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == output_type
    stored = session.get(AgentActionRequestRecord, UUID(body["action_request_id"]))
    assert stored is not None
    assert stored.action_type == action_type
    assert stored.expected_output == expected_output
    assert stored.status == "succeeded"
    if output_type == "draft_candidates":
        assert len(body["draft_candidate_ids"]) == 1
    if output_type == "beat_candidates":
        assert len(body["beat_candidate_ids"]) == 1
    if output_type == "risk_findings":
        assert len(body["risk_finding_ids"]) == 1
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )
    assert session.query(IdempotencyRecord).filter_by(operation="action_request.run").count() == 1


def test_explain_candidate_action_request_run_endpoint_returns_candidate_explanation(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, actor_id, action_request, candidate = seed_explain_candidate_action_request(session)
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-explain-candidate",
            "Idempotency-Key": "idem-api-run-explain-candidate",
        },
        json={"current_text_window": ""},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == "candidate_explanation"
    assert body["draft_candidate_ids"] == []
    assert body["candidate_explanation"]["candidate_id"] == str(candidate.id)
    assert body["candidate_explanation"]["used_memory_refs"] == candidate.memory_refs
    assert body["candidate_explanation"]["risks"][0]["risk_type"] == "canon_risk"


def test_revise_candidate_action_request_run_endpoint_returns_replacement_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, actor_id, action_request, original_candidate = seed_revise_candidate_action_request(
        session, object_store
    )
    client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=LocalStoryDraftProvider(),
        )
    )

    response = client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-run-revise-candidate",
            "Idempotency-Key": "idem-api-run-revise-candidate",
        },
        json={"current_text_window": "作者要求保留钥匙来源悬念。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output_type"] == "draft_candidates"
    assert len(body["draft_candidate_ids"]) == 1
    replacement = session.get(AgentDraftCandidateRecord, UUID(body["draft_candidate_ids"][0]))
    assert replacement is not None
    assert replacement.action_request_id == action_request.id
    assert session.get(AgentDraftCandidateRecord, original_candidate.id).status == "revised"


class BlankStoryProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        return StoryDraftResult(
            text="   ",
            finish_reason="complete",
            structured_output={
                "text": "   ",
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class InvalidThenValidStoryProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def __init__(self) -> None:
        self.call_count = 0
        self._valid_provider = LocalStoryDraftProvider()

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        self.call_count += 1
        if self.call_count == 1:
            return StoryDraftResult(
                text="   ",
                finish_reason="complete",
                structured_output={
                    "text": "   ",
                    "mode": request.prose_rendering_contract.get("mode"),
                    "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
                },
                review_cues=[],
            )
        return self._valid_provider.draft(request)
