from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sextant.application.errors import ApplicationError
from sextant.application.use_cases import (
    AcceptCandidate,
    ConfirmMemoryWritebackDecision,
    ListProjectMembers,
    OperateCandidate,
    OperateReviewItem,
    RevokeProjectMember,
    SubmitActionRequest,
    UpsertProjectMember,
)
from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    CandidateOperationInput,
    CreateSourceInput,
    ListProjectMembersInput,
    MemoryWritebackDecisionInput,
    ReviewItemOperationInput,
    RevokeProjectMemberInput,
    SubmitActionRequestInput,
    UpsertProjectMemberInput,
)
from sextant.infra.db.models import (
    AgentActionRequestRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AuditEvent,
    Base,
    ContextPackReadinessRecord,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
    IdempotencyRecord,
    JobRecord,
    MemoryPage,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SourceDeltaRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
    StoryChapter,
    StoryEventCandidate,
    StoryMention,
    StoryScene,
)
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


def uow_factory(session: Session):
    return lambda: SqlAlchemyUnitOfWork(session)


def test_create_source_inserts_version_before_delta_reference(session: Session) -> None:
    project = Project(id=uuid4(), name="Insert Ordering")
    actor_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=actor_id,
            role="owner",
            status="active",
        )
    )
    session.add(project)
    session.commit()
    insert_order: list[str] = []

    @event.listens_for(session.get_bind(), "before_cursor_execute")
    def _record_insert_order(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("insert into source_versions"):
            insert_order.append("source_versions")
        if normalized.startswith("insert into source_deltas"):
            insert_order.append("source_deltas")

    SqlAlchemyUnitOfWork(session).create_source(
        CreateSourceInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-create-source-order",
            idempotency_key="idem-create-source-order",
            title="Imported chapter",
            source_type="draft_manuscript",
            source_scope="user_draft",
            ownership_status="owned",
            text="abstract source text",
        ),
        raw_text_ref="s3://bucket/source.txt",
        raw_hash="hash-source-order",
    )

    assert insert_order[:2] == ["source_versions", "source_deltas"]


def seed_source(session: Session) -> tuple[Project, RawSource, SourceVersion, UUID]:
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
    session.add_all([project, membership, raw_source, version])
    session.commit()
    return project, raw_source, version, actor_id


def seed_span_for_source(
    session: Session,
    *,
    raw_source: RawSource,
    version: SourceVersion,
    text: str,
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
        end_offset=len(text),
        raw_start_offset=0,
        raw_end_offset=len(text),
        text_preview=text,
        narration_layer="narrator",
    )
    session.add_all([view, span])
    session.flush()
    return span


def test_project_member_management_upserts_lists_and_revokes_members(
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    editor_id = uuid4()

    upsert_output = UpsertProjectMember(uow_factory(session)).execute(
        UpsertProjectMemberInput(
            project_id=project.id,
            actor_id=owner_id,
            request_id="req-member-upsert",
            idempotency_key="idem-member-upsert",
            member_actor_id=editor_id,
            role="editor",
        )
    )

    assert upsert_output.status == "active"
    assert upsert_output.member.actor_id == editor_id
    assert upsert_output.member.role == "editor"

    members = ListProjectMembers(uow_factory(session)).execute(
        ListProjectMembersInput(project_id=project.id, actor_id=owner_id)
    )

    assert [(member.actor_id, member.role, member.status) for member in members.items] == [
        (owner_id, "owner", "active"),
        (editor_id, "editor", "active"),
    ]

    RevokeProjectMember(uow_factory(session)).execute(
        RevokeProjectMemberInput(
            project_id=project.id,
            actor_id=owner_id,
            request_id="req-member-revoke",
            idempotency_key="idem-member-revoke",
            member_actor_id=editor_id,
        )
    )

    with pytest.raises(ApplicationError, match="Project is not accessible"):
        ListProjectMembers(uow_factory(session)).execute(
            ListProjectMembersInput(project_id=project.id, actor_id=editor_id)
        )

    audit_types = [event.event_type for event in session.query(AuditEvent).all()]
    assert audit_types == ["project_member.upserted", "project_member.revoked"]


def test_project_member_management_rejects_viewer_write_and_last_owner_revoke(
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    viewer_id = uuid4()
    target_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=viewer_id,
            role="viewer",
            status="active",
        )
    )
    session.commit()

    with pytest.raises(ApplicationError, match="Project member writes require owner or editor"):
        UpsertProjectMember(uow_factory(session)).execute(
            UpsertProjectMemberInput(
                project_id=project.id,
                actor_id=viewer_id,
                request_id="req-viewer-member-upsert",
                idempotency_key="idem-viewer-member-upsert",
                member_actor_id=target_id,
                role="viewer",
            )
        )

    with pytest.raises(ApplicationError, match="last active owner"):
        RevokeProjectMember(uow_factory(session)).execute(
            RevokeProjectMemberInput(
                project_id=project.id,
                actor_id=owner_id,
                request_id="req-last-owner-revoke",
                idempotency_key="idem-last-owner-revoke",
                member_actor_id=owner_id,
            )
        )


def test_submit_action_request_rejects_writing_action_without_target(
    session: Session,
) -> None:
    project, _, _, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    with pytest.raises(ApplicationError) as error:
        use_case.execute(
            SubmitActionRequestInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-1",
                idempotency_key="idem-1",
                trigger="natural_language",
                action_type="rewrite_span",
                target=None,
                constraints={},
                expected_output="draft_candidate",
                actor_intent="把这一段写得更紧一点",
            )
        )

    assert error.value.code == "missing_target"


def test_submit_action_request_rejects_unsupported_action_type(session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    with pytest.raises(ApplicationError) as error:
        use_case.execute(
            SubmitActionRequestInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-unsupported-action",
                idempotency_key="idem-unsupported-action",
                trigger="selection",
                action_type="invent_canon_fact",
                target={
                    "kind": "selected_text",
                    "source_id": str(raw_source.id),
                    "source_version_id": str(version.id),
                    "range": {"start": 10, "end": 32},
                },
                constraints={},
                expected_output="draft_candidate",
                actor_intent="直接把这个设定写进 canon",
                source_id=raw_source.id,
                source_version_id=version.id,
            )
        )

    assert error.value.code == "unsupported_action_type"
    assert session.query(AgentActionRequestRecord).count() == 0


def test_submit_action_request_rejects_expected_output_mismatch(session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    with pytest.raises(ApplicationError) as error:
        use_case.execute(
            SubmitActionRequestInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-output-mismatch",
                idempotency_key="idem-output-mismatch",
                trigger="selection",
                action_type="rewrite_span",
                target={
                    "kind": "selected_text",
                    "source_id": str(raw_source.id),
                    "source_version_id": str(version.id),
                    "range": {"start": 10, "end": 32},
                },
                constraints={},
                expected_output="memory_answer",
                actor_intent="把这一段写得更紧一点",
                source_id=raw_source.id,
                source_version_id=version.id,
            )
        )

    assert error.value.code == "expected_output_mismatch"
    assert session.query(AgentActionRequestRecord).count() == 0


def test_submit_action_request_accepts_memory_answer_without_target(session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-ask-memory",
            idempotency_key="idem-ask-memory",
            trigger="natural_language",
            action_type="ask_memory",
            target=None,
            constraints={"subject_ref": {"type": "character", "id": "mira"}},
            expected_output="memory_answer",
            actor_intent="米拉知道钥匙是谁给的吗？",
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.action_type == "ask_memory"
    assert stored.expected_output == "memory_answer"
    assert stored.actor_intent == "米拉知道钥匙是谁给的吗？"
    assert stored.target is None
    assert session.query(FactAssertionRecord).count() == 0
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )


def test_submit_action_request_accepts_check_risk_with_selected_target(session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-check-risk",
            idempotency_key="idem-check-risk",
            trigger="selection",
            action_type="check_risk",
            target={
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 10, "end": 32},
            },
            constraints={},
            expected_output="risk_findings",
            actor_intent="这段有没有 POV 穿帮？",
            source_id=raw_source.id,
            source_version_id=version.id,
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.action_type == "check_risk"
    assert stored.expected_output == "risk_findings"
    assert stored.target["range"] == {"start": 10, "end": 32}
    assert session.query(FactAssertionRecord).count() == 0


def test_submit_action_request_accepts_suggest_next_direction(session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-suggest-direction",
            idempotency_key="idem-suggest-direction",
            trigger="natural_language",
            action_type="suggest_next_direction",
            target={
                "kind": "cursor_position",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 32, "end": 32},
            },
            constraints={"length": "short"},
            expected_output="beat_candidates",
            actor_intent="下面可以发生什么？",
            source_id=raw_source.id,
            source_version_id=version.id,
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.action_type == "suggest_next_direction"
    assert stored.expected_output == "beat_candidates"
    assert session.query(FactAssertionRecord).count() == 0


def test_submit_action_request_accepts_explain_candidate_target(session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    candidate_id = uuid4()
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-explain-candidate",
            idempotency_key="idem-explain-candidate",
            trigger="candidate_action",
            action_type="explain_candidate",
            target={"kind": "candidate", "candidate_id": str(candidate_id)},
            constraints={},
            expected_output="candidate_explanation",
            actor_intent="为什么这个候选合理？",
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.action_type == "explain_candidate"
    assert stored.expected_output == "candidate_explanation"
    assert stored.target["candidate_id"] == str(candidate_id)
    assert session.query(FactAssertionRecord).count() == 0


def test_submit_action_request_accepts_revise_candidate_target(session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    candidate_id = uuid4()
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-revise-candidate",
            idempotency_key="idem-revise-candidate",
            trigger="candidate_action",
            action_type="revise_candidate",
            target={"kind": "candidate", "candidate_id": str(candidate_id)},
            constraints={"keep_thread_open": True},
            expected_output="draft_candidate",
            actor_intent="别关闭钥匙来源这个悬念。",
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.action_type == "revise_candidate"
    assert stored.expected_output == "draft_candidate"
    assert stored.target["candidate_id"] == str(candidate_id)
    assert session.query(FactAssertionRecord).count() == 0


def test_submit_action_request_persists_intent_without_creating_facts(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    output = use_case.execute(
        SubmitActionRequestInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-2",
            idempotency_key="idem-2",
            trigger="selection",
            action_type="rewrite_span",
            target={
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 10, "end": 32},
            },
            constraints={"tone": "克制"},
            expected_output="draft_candidate",
            actor_intent="让米拉更犹豫",
            source_id=raw_source.id,
            source_version_id=version.id,
        )
    )

    stored = session.get(AgentActionRequestRecord, output.action_request_id)
    assert stored is not None
    assert stored.status == "submitted"
    assert stored.actor_intent == "让米拉更犹豫"
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="action_request.submitted").count() == 1
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )


def test_submit_action_request_replays_matching_idempotency_key(session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))
    input_data = SubmitActionRequestInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-2-replay",
        idempotency_key="idem-2-replay",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 10, "end": 32},
        },
        constraints={"tone": "克制"},
        expected_output="draft_candidate",
        actor_intent="让米拉更犹豫",
        source_id=raw_source.id,
        source_version_id=version.id,
    )

    first = use_case.execute(input_data)
    second = use_case.execute(input_data)

    assert second == first
    assert session.query(AgentActionRequestRecord).count() == 1
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )


def test_submit_action_request_rejects_idempotency_payload_change(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))
    base = SubmitActionRequestInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-2-conflict",
        idempotency_key="idem-2-conflict",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 10, "end": 32},
        },
        constraints={"tone": "克制"},
        expected_output="draft_candidate",
        actor_intent="让米拉更犹豫",
        source_id=raw_source.id,
        source_version_id=version.id,
    )

    use_case.execute(base)
    with pytest.raises(ApplicationError) as error:
        use_case.execute(replace(base, actor_intent="同一个 key 不能换 payload"))

    assert error.value.code == "idempotency_conflict"


def test_submit_action_request_rejects_actor_without_membership(session: Session) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    use_case = SubmitActionRequest(uow_factory(session))

    with pytest.raises(ApplicationError) as error:
        use_case.execute(
            SubmitActionRequestInput(
                project_id=project.id,
                actor_id=uuid4(),
                request_id="req-permission",
                idempotency_key="idem-permission",
                trigger="selection",
                action_type="rewrite_span",
                target={
                    "kind": "selected_text",
                    "source_id": str(raw_source.id),
                    "source_version_id": str(version.id),
                    "range": {"start": 10, "end": 32},
                },
                constraints={},
                expected_output="draft_candidate",
                actor_intent="改写",
                source_id=raw_source.id,
                source_version_id=version.id,
            )
        )

    assert error.value.code == "permission_denied"


def test_accept_candidate_creates_source_delta_job_and_audit(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "米拉把钥匙放在桌上。\nKestrel 没有解释来源。"
    raw_text_ref = object_store.put_text("raw/chapter-3.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 3, "end": 9}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/one",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        target_scene_id=None,
        affected_range={"start": 3, "end": 9},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()
    accepted_text_ref = object_store.put_text("accepted/one.txt", "钥匙停在两人之间。")

    output = AcceptCandidate(uow_factory(session), object_store).execute(
        AcceptCandidateInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-accept-1",
            idempotency_key="idem-accept-1",
            candidate_id=candidate.id,
            accepted_text_ref=accepted_text_ref,
            accept_mode="partial",
            target_source_id=raw_source.id,
            target_version_id=version.id,
            insert_or_replace_range={"start": 3, "end": 9},
            source_type="draft_manuscript",
            source_scope="user_draft",
            author_edited=True,
        )
    )

    stored_candidate = session.get(AgentDraftCandidateRecord, candidate.id)
    assert stored_candidate.status == "converted_to_source_delta"
    assert stored_candidate.author_action == "accept_partial"
    assert stored_candidate.accepted_text_ref == accepted_text_ref

    delta = session.get(SourceDeltaRecord, output.source_delta_id)
    assert delta is not None
    assert delta.accepted_fragment_id == output.accepted_fragment_id
    assert delta.status == "memory_writeback_queued"
    assert delta.provenance["draft_candidate_id"] == str(candidate.id)
    assert delta.new_version_id == output.new_version_id

    new_version = session.get(SourceVersion, output.new_version_id)
    assert new_version is not None
    assert new_version.source_id == raw_source.id
    assert new_version.supersedes_version_id == version.id
    assert new_version.version_label == "v2"
    assert object_store.get_text(new_version.raw_text_ref) == (
        original_text[:3] + "钥匙停在两人之间。" + original_text[9:]
    )

    job = session.get(JobRecord, output.memory_writeback_job_id)
    assert job is not None
    assert job.status == "queued"
    assert job.job_type == "run_memory_writeback"
    normalize_job = session.query(JobRecord).filter_by(job_type="normalize_source").one()
    assert normalize_job.status == "queued"
    assert normalize_job.payload["source_version_id"] == str(output.new_version_id)
    assert normalize_job.payload["cleaning_profile"] == "draft_manuscript_profile_v1"
    assert session.query(AuditEvent).filter_by(event_type="candidate.accepted").count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="accept_candidate").count() == 1


def test_accept_overridden_blocked_candidate_preserves_override_provenance(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "米拉没有打开门。"
    raw_text_ref = object_store.put_text("raw/blocked-override.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="有意打破 POV",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 2, "end": 8}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref=object_store.put_text(
            "candidates/blocked-override.txt", "米拉知道门后有人。"
        ),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 2, "end": 8},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="blocked",
    )
    finding = AgentReviewFindingRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        draft_candidate_id=candidate.id,
        risk_level="high",
        risk_type="forbidden_knowledge_leak",
        summary="候选泄露当前 POV 不应知道的信息。",
        affected_text_ref=candidate.candidate_text_ref,
        memory_refs={},
        storytelling_refs={"source": "test"},
        suggested_revision="保持未知。",
        can_offer_to_author=False,
        maps_to_review_type_if_accepted="knowledge_conflict",
        draft_local_only=True,
    )
    session.add_all([action_request, candidate, finding])
    session.commit()
    accepted_text_ref = object_store.put_text("accepted/blocked-override.txt", "米拉知道门后有人。")
    accept_input = AcceptCandidateInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-accept-blocked-override",
        idempotency_key="idem-accept-blocked-override",
        candidate_id=candidate.id,
        accepted_text_ref=accepted_text_ref,
        accept_mode="partial",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        insert_or_replace_range={"start": 2, "end": 8},
        source_type="draft_manuscript",
        source_scope="user_draft",
        author_edited=False,
    )

    with pytest.raises(ApplicationError) as blocked_error:
        AcceptCandidate(uow_factory(session), object_store).execute(accept_input)

    assert blocked_error.value.code == "blocked_without_override"
    assert session.query(SourceDeltaRecord).count() == 0
    override = OperateCandidate(uow_factory(session), object_store).execute(
        CandidateOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-override-before-accept",
            idempotency_key="idem-override-before-accept",
            candidate_id=candidate.id,
            operation="override_block",
            override_reason="作者确认这是有意的不可靠叙述实验。",
        )
    )

    assert override.status == "offered_to_author"
    output = AcceptCandidate(uow_factory(session), object_store).execute(accept_input)

    stored_candidate = session.get(AgentDraftCandidateRecord, candidate.id)
    assert stored_candidate.status == "converted_to_source_delta"
    assert stored_candidate.override_reason == "作者确认这是有意的不可靠叙述实验。"
    assert session.query(AgentReviewFindingRecord).filter_by(draft_candidate_id=candidate.id).one()
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    delta = session.get(SourceDeltaRecord, output.source_delta_id)
    assert delta is not None
    assert delta.status == "memory_writeback_queued"
    assert delta.provenance["override_reason"] == "作者确认这是有意的不可靠叙述实验。"
    assert delta.provenance["draft_candidate_id"] == str(candidate.id)
    job = session.get(JobRecord, output.memory_writeback_job_id)
    assert job is not None
    assert job.job_type == "run_memory_writeback"


def test_accept_candidate_replays_matching_idempotency_key(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "米拉把旧句子留在纸上。"
    raw_text_ref = object_store.put_text("raw/replay.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 3, "end": 6}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/replay",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 3, "end": 6},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()
    accepted_text_ref = object_store.put_text("accepted/replay.txt", "新句子")
    input_data = AcceptCandidateInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-accept-replay",
        idempotency_key="idem-accept-replay",
        candidate_id=candidate.id,
        accepted_text_ref=accepted_text_ref,
        accept_mode="partial",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        insert_or_replace_range={"start": 3, "end": 6},
        source_type="draft_manuscript",
        source_scope="user_draft",
        author_edited=True,
    )

    first = AcceptCandidate(uow_factory(session), object_store).execute(input_data)
    second = AcceptCandidate(uow_factory(session), object_store).execute(input_data)

    assert second == first
    assert session.query(SourceDeltaRecord).count() == 1
    assert session.query(SourceVersion).count() == 2
    assert session.query(JobRecord).count() == 2
    assert {
        job.job_type for job in session.query(JobRecord).order_by(JobRecord.job_type).all()
    } == {"normalize_source", "run_memory_writeback"}


def test_accept_candidate_rejects_stale_base_without_side_effects(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    version.raw_hash = "newer-hash"
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 10, "end": 32}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/stale",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 10, "end": 32},
        base_hash="hash-v1",
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()

    with pytest.raises(ApplicationError) as error:
        AcceptCandidate(uow_factory(session)).execute(
            AcceptCandidateInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-accept-stale",
                idempotency_key="idem-accept-stale",
                candidate_id=candidate.id,
                accepted_text_ref="object://accepted/stale",
                accept_mode="partial",
                target_source_id=raw_source.id,
                target_version_id=version.id,
                insert_or_replace_range={"start": 12, "end": 30},
                source_type="draft_manuscript",
                source_scope="user_draft",
                author_edited=True,
            )
        )

    assert error.value.code == "stale_source_version"
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(JobRecord).count() == 0


def test_accept_candidate_rejects_superseded_source_version_without_side_effects(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    newer_version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v2",
        raw_hash="hash-v2",
        supersedes_version_id=version.id,
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 10, "end": 32}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/superseded",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 10, "end": 32},
        base_hash="hash-v1",
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([newer_version, action_request, candidate])
    session.commit()

    with pytest.raises(ApplicationError) as error:
        AcceptCandidate(uow_factory(session)).execute(
            AcceptCandidateInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-accept-superseded",
                idempotency_key="idem-accept-superseded",
                candidate_id=candidate.id,
                accepted_text_ref="object://accepted/superseded",
                accept_mode="partial",
                target_source_id=raw_source.id,
                target_version_id=version.id,
                insert_or_replace_range={"start": 12, "end": 30},
                source_type="draft_manuscript",
                source_scope="user_draft",
                author_edited=True,
            )
        )

    assert error.value.code == "stale_source_version"
    assert error.value.details == {
        "candidate_target_version_id": str(version.id),
        "latest_version_id": str(newer_version.id),
    }
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(JobRecord).count() == 0


def test_review_item_resolve_records_noop_side_effects_without_matches_and_audit(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=0,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/review-resolve.txt",
        submitted_text_search="作者确认这是新变化",
        source_type="author_notes",
        source_scope="author_note",
        provenance={"trigger": "review_resolution"},
        status="submitted",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={"fact_ids": []},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([replacement_delta, review_item])
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-resolve",
            idempotency_key="idem-review-resolve",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="作者确认这是新变化",
            replacement_refs=[{"type": "source_delta", "id": str(replacement_delta.id)}],
        )
    )

    stored = session.get(ReviewItemRecord, review_item.id)
    assert output.status == "resolved"
    assert output.side_effects["memory_pages"] == "unchanged"
    assert output.side_effects["memory_pages_marked_stale"] == 0
    assert output.side_effects["graph_projection"] == "unchanged"
    assert output.side_effects["graph_edges_marked_stale"] == 0
    assert stored.resolved_by == actor_id
    assert session.query(AuditEvent).filter_by(event_type="review_item.resolve").count() == 1


def test_source_scope_conflict_from_model_suggestion_requires_author_source_delta(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    user_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira owns the Lantern Map.",
        slug="source-scope-user",
    )
    model_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="model_output",
        source_scope="model_suggestion",
        title="Model suggestion",
        ownership_status="owned",
        raw_text_ref="object://raw/model-suggestion",
    )
    model_version = SourceVersion(
        id=uuid4(),
        source_id=model_source.id,
        version_label="v1",
        raw_hash="hash-model-suggestion",
    )
    session.add_all([model_source, model_version])
    session.flush()
    model_span = seed_span_for_source(
        session,
        raw_source=model_source,
        version=model_version,
        text="Mira owns the Lantern Map.",
        slug="source-scope-model",
    )
    subject_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    user_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=subject_ref,
        predicate="owns",
        object_ref=object_ref,
        fact_status="canon",
        evidence_span_ids=[str(user_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    model_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=subject_ref,
        predicate="owns",
        object_ref=object_ref,
        fact_status="disputed",
        evidence_span_ids=[str(model_span.id)],
        confidence=0.82,
        source_scope="model_suggestion",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="source_scope_conflict",
        severity="medium",
        status="open",
        summary="Model suggestion cannot overwrite author text.",
        affected_refs={"fact_id": str(model_fact.id)},
        new_evidence={
            "source_span_ids": [str(model_span.id)],
            "source_scope": "model_suggestion",
        },
        existing_evidence={
            "fact_id": str(user_fact.id),
            "source_span_ids": [str(user_span.id)],
            "source_scope": "user_draft",
        },
        suggested_actions=[
            {"resolution": "accepted_as_change"},
            {"resolution": "fixed_by_text_edit"},
            {"resolution": "reject"},
        ],
        default_action="review",
    )
    session.add_all([user_fact, model_fact, review_item])
    session.commit()

    with pytest.raises(ApplicationError) as direct_accept:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-source-scope-accept",
                idempotency_key="idem-source-scope-accept",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="accept",
                author_note="直接采用模型建议。",
            )
        )

    assert direct_accept.value.code == "schema_validation_failed"
    assert "model_suggestion" in direct_accept.value.message
    assert session.get(ReviewItemRecord, review_item.id).status == "open"
    assert session.get(FactAssertionRecord, model_fact.id).fact_status == "disputed"

    with pytest.raises(ApplicationError) as missing_delta:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-source-scope-missing-delta",
                idempotency_key="idem-source-scope-missing-delta",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="accepted_as_change",
                author_note="作者决定把它作为新设定。",
            )
        )

    assert missing_delta.value.code == "schema_validation_failed"
    assert "replacement SourceDelta" in missing_delta.value.message
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    model_replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=model_source.id,
        previous_version_id=model_version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="insert",
        range_start=0,
        range_end=0,
        base_hash=model_version.raw_hash,
        submitted_text_ref="object://delta/source-scope-model-replacement.txt",
        submitted_text_search="Mira owns the Lantern Map.",
        source_type="model_output",
        source_scope="model_suggestion",
        provenance={"trigger": "source_scope_conflict_resolution"},
        status="memory_writeback_completed",
    )
    session.add(model_replacement_delta)
    session.commit()

    with pytest.raises(ApplicationError) as model_delta:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-source-scope-model-delta",
                idempotency_key="idem-source-scope-model-delta",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="accepted_as_change",
                author_note="不能用模型 SourceDelta 当作作者确认。",
                replacement_refs=[{"type": "source_delta", "id": str(model_replacement_delta.id)}],
            )
        )

    assert model_delta.value.code == "schema_validation_failed"
    assert "author-backed SourceDelta" in model_delta.value.message
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="insert",
        range_start=0,
        range_end=0,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/source-scope-accepted-change.txt",
        submitted_text_search="Mira owns the Lantern Map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "source_scope_conflict_resolution"},
        status="memory_writeback_completed",
    )
    session.add(replacement_delta)
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-source-scope-accepted-change",
            idempotency_key="idem-source-scope-accepted-change",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="作者已用正文 SourceDelta 接纳这个变化。",
            replacement_refs=[{"type": "source_delta", "id": str(replacement_delta.id)}],
        )
    )

    stored = session.get(ReviewItemRecord, review_item.id)
    assert output.status == "resolved"
    assert output.resolution == "accepted_as_change"
    assert output.side_effects["replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    assert stored.new_evidence["resolution_replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    assert stored.affected_refs["replacement_source_delta_ids"] == [str(replacement_delta.id)]
    assert session.get(FactAssertionRecord, model_fact.id).fact_status == "disputed"


def test_source_scope_conflict_reject_retires_model_fact_and_rebuilds_graph(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    user_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira owns the Lantern Map.",
        slug="source-scope-reject-user",
    )
    model_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="model_output",
        source_scope="model_suggestion",
        title="Model suggestion",
        ownership_status="owned",
        raw_text_ref="object://raw/model-suggestion-reject",
    )
    model_version = SourceVersion(
        id=uuid4(),
        source_id=model_source.id,
        version_label="v1",
        raw_hash="hash-model-suggestion-reject",
    )
    session.add_all([model_source, model_version])
    session.flush()
    model_span = seed_span_for_source(
        session,
        raw_source=model_source,
        version=model_version,
        text="Mira owns the Lantern Map.",
        slug="source-scope-reject-model",
    )
    subject_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    user_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=subject_ref,
        predicate="owns",
        object_ref=object_ref,
        fact_status="canon",
        evidence_span_ids=[str(user_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    model_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=subject_ref,
        predicate="owns",
        object_ref=object_ref,
        fact_status="disputed",
        evidence_span_ids=[str(model_span.id)],
        confidence=0.82,
        source_scope="model_suggestion",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="source_scope_conflict",
        severity="medium",
        status="open",
        summary="Reject model-suggestion source-scope conflict.",
        affected_refs={"fact_id": str(model_fact.id)},
        new_evidence={
            "source_span_ids": [str(model_span.id)],
            "source_scope": "model_suggestion",
        },
        existing_evidence={
            "fact_id": str(user_fact.id),
            "source_span_ids": [str(user_span.id)],
            "source_scope": "user_draft",
        },
        suggested_actions=[{"resolution": "reject"}],
        default_action="review",
    )
    session.add_all([user_fact, model_fact, review_item])
    session.commit()

    rebuild_graph_projection(session, project_id=project.id)
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 1
    )

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-source-scope-reject",
            idempotency_key="idem-source-scope-reject",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="reject",
            author_note="作者拒绝模型建议，不进入当前设定。",
        )
    )

    stored_review = session.get(ReviewItemRecord, review_item.id)
    stored_model_fact = session.get(FactAssertionRecord, model_fact.id)
    assert output.status == "resolved"
    assert output.resolution == "reject"
    assert output.side_effects["fact_reject"] == "source_scope_conflict_rejected"
    assert output.side_effects["fact_assertion_status"] == "contradicted"
    assert output.side_effects["graph_projection"] == "rebuilt"
    assert stored_review.status == "resolved"
    assert stored_model_fact.fact_status == "contradicted"
    assert stored_model_fact.evidence_span_ids == [str(model_span.id)]
    assert stored_model_fact.promotion_decision_id is None
    assert session.get(FactAssertionRecord, user_fact.id).fact_status == "canon"

    graph_edges = session.query(GraphProjectionEdge).filter_by(project_id=project.id).all()
    assert all(edge.source_ref.get("id") != str(review_item.id) for edge in graph_edges)
    model_edges = [
        edge
        for edge in graph_edges
        if edge.source_ref.get("type") == "fact_assertion"
        and edge.source_ref.get("id") == str(model_fact.id)
    ]
    assert [edge.edge_status for edge in model_edges] == ["contradicted"]


def test_memory_writeback_fact_accept_filters_fact_evidence_before_memory_page_promotion(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira keeps the lantern map.",
        slug="fact-accept-filter",
    )
    foreign_project = Project(id=uuid4(), name="Other Fact Accept Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/foreign-fact-accept",
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-fact-accept-hash-v1",
    )
    session.add_all([foreign_project, foreign_raw_source, foreign_version])
    session.flush()
    foreign_span = seed_span_for_source(
        session,
        raw_source=foreign_raw_source,
        version=foreign_version,
        text="Foreign fact evidence.",
        slug="foreign-fact-accept",
    )
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=27,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/fact-accept-filter.txt",
        submitted_text_search="Mira keeps the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "fact_accept_filter"},
        status="memory_writeback_completed",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="disputed",
        evidence_span_ids=[str(span.id), str(foreign_span.id), "not-a-source-span-id"],
        confidence=0.82,
        source_scope="user_draft",
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:fact-accept-filter",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([delta, fact, extraction_audit])
    session.commit()

    output = ConfirmMemoryWritebackDecision(uow_factory(session)).execute(
        MemoryWritebackDecisionInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-fact-accept-filter",
            idempotency_key="idem-fact-accept-filter",
            source_delta_id=delta.id,
            item_ref={"type": "fact_assertion", "id": str(fact.id)},
            decision="accept",
            author_note="作者确认这个设定进入当前记忆。",
        )
    )

    stored_fact = session.get(FactAssertionRecord, fact.id)
    page = session.query(MemoryPage).one()
    graph_edge = session.query(GraphProjectionEdge).one()
    assert output.side_effects["fact_assertion_status"] == "canon"
    assert stored_fact.fact_status == "canon"
    assert stored_fact.evidence_span_ids == [str(span.id)]
    assert page.current_canon["facts"] == [
        {
            "fact_id": str(fact.id),
            "predicate": "owns",
            "object_ref": fact.object_ref,
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in page.source_refs
    assert {"type": "source_span", "id": str(foreign_span.id)} not in page.source_refs
    assert {"type": "source_span", "id": "not-a-source-span-id"} not in page.source_refs
    assert graph_edge.evidence_refs == [{"type": "source_span", "id": str(span.id)}]


def test_source_span_dispute_records_valid_source_span_evidence_on_memory_page_contradiction(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira owns the lantern map.",
        slug="source-span-dispute-filter",
    )
    foreign_project = Project(id=uuid4(), name="Other SourceSpan Dispute Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Foreign Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/foreign-source-span-dispute",
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-source-span-dispute-hash-v1",
    )
    session.add_all([foreign_project, foreign_raw_source, foreign_version])
    session.flush()
    foreign_span = seed_span_for_source(
        session,
        raw_source=foreign_raw_source,
        version=foreign_version,
        text="Foreign dispute evidence.",
        slug="foreign-source-span-dispute",
    )
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=27,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/source-span-dispute-filter.txt",
        submitted_text_search="Mira owns the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "source_span_dispute_filter"},
        status="memory_writeback_completed",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id), str(foreign_span.id), "not-a-source-span-id"],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    evidence = EvidenceLogEntry(
        id=uuid4(),
        project_id=project.id,
        log_type="fact_derived",
        target_ref={"type": "fact_assertion", "id": str(fact.id)},
        fact_id=fact.id,
        event_id=None,
        source_span_ids=[str(span.id)],
        log_status="written",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref=fact.subject_ref,
        title="Mira",
        current_canon={
            "facts": [
                {
                    "fact_id": str(fact.id),
                    "predicate": "owns",
                    "object_ref": fact.object_ref,
                    "evidence_span_ids": [
                        str(span.id),
                        str(foreign_span.id),
                        "not-a-source-span-id",
                    ],
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_span", "id": str(span.id)},
            {"type": "source_span", "id": str(foreign_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:source-span-dispute-filter",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([delta, fact, evidence, page, extraction_audit])
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    session.commit()

    output = ConfirmMemoryWritebackDecision(uow_factory(session)).execute(
        MemoryWritebackDecisionInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-source-span-dispute-filter",
            idempotency_key="idem-source-span-dispute-filter",
            source_delta_id=delta.id,
            item_ref={"type": "source_span", "id": str(span.id)},
            decision="reject",
            author_note="作者确认这段证据不能支撑当前设定。",
        )
    )

    stored_page = session.get(MemoryPage, page.id)
    stored_fact = session.get(FactAssertionRecord, fact.id)
    stored_evidence = session.get(EvidenceLogEntry, evidence.id)
    graph_edge = session.query(GraphProjectionEdge).one()
    assert output.side_effects["evidence_log_entries_marked_disputed"] == 1
    assert stored_evidence.log_status == "disputed"
    assert stored_fact.fact_status == "disputed"
    assert stored_page.canon_status == "stale"
    assert stored_page.contradictions[0]["source_span_ids"] == [str(span.id)]
    assert str(foreign_span.id) not in stored_page.contradictions[0]["source_span_ids"]
    assert "not-a-source-span-id" not in stored_page.contradictions[0]["source_span_ids"]
    assert graph_edge.edge_status == "disputed"


def test_review_item_dismiss_and_reopen_follow_whitelist(session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="low",
        status="open",
        summary="Intentional timeline echo.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[],
        default_action="defer",
    )
    session.add(review_item)
    session.commit()

    dismiss_output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-dismiss",
            idempotency_key="idem-review-dismiss",
            review_item_id=review_item.id,
            operation="dismiss",
            author_note="有意为之",
        )
    )
    reopen_output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-reopen",
            idempotency_key="idem-review-reopen",
            review_item_id=review_item.id,
            operation="reopen",
        )
    )

    assert dismiss_output.status == "dismissed"
    assert dismiss_output.side_effects["promotion"] == "none"
    assert reopen_output.status == "open"


def test_review_item_supersede_resolution_enters_superseded_status(
    session: Session,
) -> None:
    project, raw_source, _version, actor_id = seed_source(session)
    replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=None,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=0,
        base_hash=None,
        submitted_text_ref="object://replacement/review-supersede.txt",
        submitted_text_search="New evidence supersedes the old review.",
        source_type="author_notes",
        source_scope="author_note",
        provenance={"trigger": "review_supersede_resolution"},
        status="submitted",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="version_conflict",
        severity="medium",
        status="open",
        summary="A newer SourceDelta supersedes this review.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "supersede"}],
        default_action="supersede",
    )
    session.add_all([replacement_delta, review_item])
    session.commit()

    with pytest.raises(ApplicationError) as missing_refs:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-supersede-missing",
                idempotency_key="idem-review-supersede-missing",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="supersede",
                author_note="缺少替代证据。",
            )
        )

    assert missing_refs.value.code == "schema_validation_failed"
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-supersede",
            idempotency_key="idem-review-supersede",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="supersede",
            author_note="新证据已经取代这个 ReviewItem。",
            replacement_refs=[{"type": "source_delta", "id": str(replacement_delta.id)}],
        )
    )

    stored = session.get(ReviewItemRecord, review_item.id)
    assert output.status == "superseded"
    assert output.resolution == "supersede"
    assert output.side_effects["replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    assert stored.status == "superseded"
    assert stored.resolution == "supersede"


def test_review_item_supersede_accepts_replacement_review_item_ref(
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    replacement_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="version_conflict",
        severity="medium",
        status="open",
        summary="Newer ReviewItem carries the current version-conflict evidence.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}],
        default_action="accept",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="version_conflict",
        severity="medium",
        status="open",
        summary="An older ReviewItem was replaced by a newer review.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "supersede"}],
        default_action="supersede",
    )
    session.add_all([replacement_review, review_item])
    session.commit()

    with pytest.raises(ApplicationError) as missing_replacement:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-supersede-review-ref-missing",
                idempotency_key="idem-review-supersede-review-ref-missing",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="supersede",
                author_note="不存在的替代 ReviewItem 不能生效。",
                replacement_refs=[{"type": "review_item", "id": str(uuid4())}],
            )
        )

    assert missing_replacement.value.code == "not_found"
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    with pytest.raises(ApplicationError) as self_replacement:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-supersede-review-ref-self",
                idempotency_key="idem-review-supersede-review-ref-self",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="supersede",
                author_note="自引用不能替代自己。",
                replacement_refs=[{"type": "review_item", "id": str(review_item.id)}],
            )
        )

    assert self_replacement.value.code == "schema_validation_failed"
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-supersede-review-ref",
            idempotency_key="idem-review-supersede-review-ref",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="supersede",
            author_note="新的 ReviewItem 已经替代这个旧风险。",
            replacement_refs=[{"type": "review_item", "id": str(replacement_review.id)}],
        )
    )

    stored = session.get(ReviewItemRecord, review_item.id)
    assert output.status == "superseded"
    assert output.side_effects["replacement_refs"] == [
        {"type": "review_item", "id": str(replacement_review.id)}
    ]
    assert stored.status == "superseded"
    assert stored.resolution == "supersede"


def test_review_item_supersede_accepts_replacement_source_span_ref(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-supersede-span.md",
        raw_offset_map_ref="object://processed/review-supersede-span.offsets.json",
        view_status="current",
    )
    replacement_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=31,
        raw_start_offset=0,
        raw_end_offset=31,
        text_preview="New evidence replaces this risk.",
        narration_layer="narrator",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="version_conflict",
        severity="medium",
        status="open",
        summary="New evidence supersedes this review.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "supersede"}],
        default_action="supersede",
    )
    session.add_all([view, replacement_span, review_item])
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-supersede-span-ref",
            idempotency_key="idem-review-supersede-span-ref",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="supersede",
            author_note="新的 SourceSpan 证据已经取代这个 ReviewItem。",
            replacement_refs=[{"type": "source_span", "id": str(replacement_span.id)}],
        )
    )

    stored = session.get(ReviewItemRecord, review_item.id)
    assert output.status == "superseded"
    assert output.side_effects["replacement_refs"] == [
        {"type": "source_span", "id": str(replacement_span.id)}
    ]
    assert stored.status == "superseded"
    assert stored.resolution == "supersede"


def test_review_item_rejects_invalid_resolution(session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)

    with pytest.raises(ApplicationError) as error:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-invalid",
                idempotency_key="idem-review-invalid",
                review_item_id=uuid4(),
                operation="resolve",
                resolution="ship_it",
            )
        )

    assert error.value.code == "schema_validation_failed"


def test_review_item_split_merge_resolution_requires_note_and_replacement_delta(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-merge.md",
        raw_offset_map_ref="object://processed/review-merge.offsets.json",
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
        end_offset=28,
        raw_start_offset=0,
        raw_end_offset=28,
        text_preview="Mira carried the lantern map.",
        narration_layer="narrator",
    )
    character_ref = {"type": "character", "id": "mira", "label": "Mira"}
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=character_ref,
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref=character_ref,
        title="Mira",
        current_canon={"facts": [{"fact_id": str(fact.id), "predicate": "owns"}]},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    existing_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira carries the lantern map",
        event_status="proposed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[character_ref],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="ch001",
        summary="Mira carries the lantern map.",
        cause_summary=None,
        consequence_summary="Mira keeps the map.",
        evidence_span_ids=[str(span.id)],
    )
    disputed_candidate_id = uuid4()
    disputed_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=29,
        end_offset=57,
        raw_start_offset=29,
        raw_end_offset=57,
        text_preview="The same transfer is clarified.",
        narration_layer="narrator",
    )
    _foreign_project, foreign_raw_source, foreign_version, _foreign_actor_id = seed_source(session)
    foreign_span = seed_span_for_source(
        session,
        raw_source=foreign_raw_source,
        version=foreign_version,
        text="Foreign event merge evidence from another project.",
        slug="foreign-event-merge",
    )
    existing_event.evidence_span_ids = [
        str(span.id),
        str(foreign_span.id),
        "not-a-source-span-id",
    ]
    disputed_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Clarified lantern map transfer",
        event_status="disputed",
        primary_scene_id=None,
        event_candidate_ids=[str(disputed_candidate_id)],
        participants=[character_ref],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="ch001",
        summary="The map transfer is clarified.",
        cause_summary="The author resolved this as the same event.",
        consequence_summary=None,
        evidence_span_ids=[
            str(disputed_span.id),
            str(foreign_span.id),
            "not-a-source-span-id",
        ],
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="event_merge_conflict",
        severity="medium",
        status="open",
        summary="Two events may need merging.",
        affected_refs={
            "event_id": str(disputed_event.id),
            "existing_event_id": str(existing_event.id),
            "event_type": "object_transfer",
            "fact_ids": [str(fact.id)],
            "memory_page_id": str(page.id),
        },
        new_evidence={
            "event_id": str(disputed_event.id),
            "source_span_ids": [str(disputed_span.id)],
            "summary": disputed_event.summary,
        },
        existing_evidence={
            "event_id": str(existing_event.id),
            "source_span_ids": [str(span.id)],
            "summary": existing_event.summary,
        },
        suggested_actions=[{"resolution": "merge"}],
        default_action="merge",
    )
    session.add_all(
        [
            view,
            span,
            disputed_span,
            fact,
            page,
            existing_event,
            disputed_event,
            review_item,
        ]
    )
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    session.commit()

    with pytest.raises(ApplicationError) as error:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-merge-missing-ref",
                idempotency_key="idem-review-merge-missing-ref",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="merge",
                author_note="合并为一次事件。",
                replacement_refs=[],
            )
        )

    assert error.value.code == "schema_validation_failed"
    assert "replacement SourceDelta" in error.value.message

    with pytest.raises(ApplicationError) as error:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-merge-missing-delta",
                idempotency_key="idem-review-merge-missing-delta",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="merge",
                author_note="合并为一次事件。",
                replacement_refs=[{"type": "source_delta", "id": str(uuid4())}],
            )
        )

    assert error.value.code == "not_found"
    assert "Replacement SourceDelta" in error.value.message
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=28,
        base_hash="hash-v1",
        submitted_text_ref="object://delta/review-merge.txt",
        submitted_text_search="merged event correction",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "review_merge_resolution"},
        status="memory_writeback_completed",
    )
    session.add(replacement_delta)
    session.commit()

    original_existing_candidate_ids = list(existing_event.event_candidate_ids)
    original_disputed_candidate_ids = list(disputed_event.event_candidate_ids)
    original_existing_span_ids = [str(span.id)]
    original_disputed_span_ids = [str(disputed_span.id)]
    original_disputed_cause_summary = disputed_event.cause_summary
    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-merge-valid",
            idempotency_key="idem-review-merge-valid",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="merge",
            author_note="合并为一次事件。",
            replacement_refs=[{"type": "source_delta", "id": str(replacement_delta.id)}],
        )
    )

    assert output.status == "resolved"
    assert output.side_effects["policy_action"] == "split_merge_rebuild_required"
    assert output.side_effects["replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    assert output.side_effects["memory_pages"] == "stale_rewrite_queued"
    assert output.side_effects["memory_pages_marked_stale"] == 1
    assert output.side_effects["graph_projection"] == "outdated_rebuild_queued"
    assert output.side_effects["graph_edges_marked_stale"] == 2
    assert output.side_effects["graph_projection_rebuild_job_id"]
    assert output.side_effects["memory_page_rewrite_job_ids"]
    assert output.side_effects["event_merge"] == "applied"
    assert output.side_effects["merged_event_id"] == str(existing_event.id)
    assert output.side_effects["deprecated_event_id"] == str(disputed_event.id)
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review is not None
    assert stored_review.affected_refs["event_id"] == str(disputed_event.id)
    assert stored_review.affected_refs["existing_event_id"] == str(existing_event.id)
    assert stored_review.affected_refs["fact_ids"] == [str(fact.id)]
    assert stored_review.affected_refs["replacement_source_delta_ids"] == [
        str(replacement_delta.id)
    ]
    assert stored_review.new_evidence["resolution_replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    stored_existing_event = session.get(StoryCanonicalEvent, existing_event.id)
    assert stored_existing_event is not None
    assert stored_existing_event.event_status == "proposed"
    assert stored_existing_event.event_candidate_ids == [
        *original_existing_candidate_ids,
        *original_disputed_candidate_ids,
    ]
    assert stored_existing_event.evidence_span_ids == [
        *original_existing_span_ids,
        *original_disputed_span_ids,
    ]
    assert str(foreign_span.id) not in stored_existing_event.evidence_span_ids
    assert "not-a-source-span-id" not in stored_existing_event.evidence_span_ids
    assert stored_existing_event.cause_summary == original_disputed_cause_summary
    stored_disputed_event = session.get(StoryCanonicalEvent, disputed_event.id)
    assert stored_disputed_event is not None
    assert stored_disputed_event.event_status == "deprecated"
    assert session.get(MemoryPage, page.id).canon_status == "stale"
    assert {
        edge.edge_status
        for edge in session.query(GraphProjectionEdge).filter_by(project_id=project.id).all()
    } == {"outdated"}
    assert session.query(JobRecord).filter_by(job_type="rewrite_memory_page").count() == 1
    assert session.query(JobRecord).filter_by(job_type="rebuild_graph_projection").count() == 1


def test_event_merge_conflict_split_confirms_distinct_event_and_rebuilds_dependents(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-event-split.md",
        raw_offset_map_ref="object://processed/review-event-split.offsets.json",
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=27,
        raw_start_offset=0,
        raw_end_offset=27,
        text_preview="Mira hid the lantern map.",
        narration_layer="narrator",
    )
    disputed_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=28,
        end_offset=58,
        raw_start_offset=28,
        raw_end_offset=58,
        text_preview="Kestrel moved a copied map later.",
        narration_layer="narrator",
    )
    character_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=character_ref,
        predicate="owns",
        object_ref=object_ref,
        fact_status="canon",
        evidence_span_ids=[str(existing_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref=character_ref,
        title="Mira",
        current_canon={"facts": [{"fact_id": str(fact.id), "predicate": "owns"}]},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(existing_span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    existing_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira hides the lantern map",
        event_status="proposed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[character_ref],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch001",
        summary="Mira hides the lantern map.",
        cause_summary=None,
        consequence_summary=None,
        evidence_span_ids=[str(existing_span.id)],
    )
    disputed_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Kestrel moves a copied map",
        event_status="disputed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch002",
        summary="Kestrel later moves a copied map.",
        cause_summary="The author confirmed this is a later distinct action.",
        consequence_summary=None,
        evidence_span_ids=[str(disputed_span.id)],
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="event_merge_conflict",
        severity="medium",
        status="open",
        summary="Two map-transfer events may be distinct.",
        affected_refs={
            "event_id": str(disputed_event.id),
            "existing_event_id": str(existing_event.id),
            "event_type": "object_transfer",
            "fact_ids": [str(fact.id)],
            "memory_page_id": str(page.id),
        },
        new_evidence={
            "event_id": str(disputed_event.id),
            "source_span_ids": [str(disputed_span.id)],
            "summary": disputed_event.summary,
        },
        existing_evidence={
            "event_id": str(existing_event.id),
            "source_span_ids": [str(existing_span.id)],
            "summary": existing_event.summary,
        },
        suggested_actions=[{"resolution": "split"}],
        default_action="review",
    )
    replacement_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=28,
        range_end=58,
        base_hash="hash-v1",
        submitted_text_ref="object://delta/review-event-split.txt",
        submitted_text_search="distinct later map action",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "review_split_resolution"},
        status="memory_writeback_completed",
    )
    session.add_all(
        [
            view,
            existing_span,
            disputed_span,
            fact,
            page,
            existing_event,
            disputed_event,
            review_item,
            replacement_delta,
        ]
    )
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    session.commit()

    original_existing_candidate_ids = list(existing_event.event_candidate_ids)
    original_disputed_candidate_ids = list(disputed_event.event_candidate_ids)
    original_existing_span_ids = list(existing_event.evidence_span_ids)
    original_disputed_span_ids = list(disputed_event.evidence_span_ids)

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-event-split",
            idempotency_key="idem-review-event-split",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="split",
            author_note="这不是同一事件，保留为后续独立动作。",
            replacement_refs=[{"type": "source_delta", "id": str(replacement_delta.id)}],
        )
    )

    assert output.status == "resolved"
    assert output.side_effects["policy_action"] == "split_merge_rebuild_required"
    assert output.side_effects["event_split"] == "confirmed_distinct"
    assert output.side_effects["distinct_event_id"] == str(disputed_event.id)
    assert output.side_effects["existing_event_id"] == str(existing_event.id)
    assert output.side_effects["memory_pages"] == "stale_rewrite_queued"
    assert output.side_effects["graph_projection"] == "outdated_rebuild_queued"
    assert output.side_effects["graph_edges_marked_stale"] == 2

    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review is not None
    assert stored_review.resolution == "split"
    assert stored_review.affected_refs["replacement_source_delta_ids"] == [
        str(replacement_delta.id)
    ]
    assert stored_review.new_evidence["resolution_replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]

    stored_existing_event = session.get(StoryCanonicalEvent, existing_event.id)
    assert stored_existing_event is not None
    assert stored_existing_event.event_status == "proposed"
    assert stored_existing_event.event_candidate_ids == original_existing_candidate_ids
    assert stored_existing_event.evidence_span_ids == original_existing_span_ids

    stored_disputed_event = session.get(StoryCanonicalEvent, disputed_event.id)
    assert stored_disputed_event is not None
    assert stored_disputed_event.event_status == "proposed"
    assert stored_disputed_event.event_candidate_ids == original_disputed_candidate_ids
    assert stored_disputed_event.evidence_span_ids == original_disputed_span_ids
    assert session.get(MemoryPage, page.id).canon_status == "stale"
    assert session.query(JobRecord).filter_by(job_type="rewrite_memory_page").count() == 1
    assert session.query(JobRecord).filter_by(job_type="rebuild_graph_projection").count() == 1


def test_event_merge_conflict_mark_intentional_removes_graph_reminder(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-event-intentional.md",
        raw_offset_map_ref="object://processed/review-event-intentional.offsets.json",
        view_status="current",
    )
    existing_span = SourceSpan(
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
        text_preview="Mira kept the lantern map.",
        narration_layer="narrator",
    )
    disputed_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=25,
        end_offset=54,
        raw_start_offset=25,
        raw_end_offset=54,
        text_preview="The narrator hints Kestrel has it.",
        narration_layer="narrator",
    )
    participant_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    existing_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira keeps the lantern map",
        event_status="proposed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[participant_ref],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch001",
        summary="Mira keeps the lantern map.",
        cause_summary=None,
        consequence_summary=None,
        evidence_span_ids=[str(existing_span.id)],
    )
    disputed_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Kestrel may have the lantern map",
        event_status="disputed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[participant_ref],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch001",
        summary="The narrator intentionally hints at a conflicting holder.",
        cause_summary=None,
        consequence_summary=None,
        evidence_span_ids=[str(disputed_span.id)],
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="event_merge_conflict",
        severity="medium",
        status="open",
        summary="The map holder conflict may be intentional misdirection.",
        affected_refs={
            "event_id": str(disputed_event.id),
            "existing_event_id": str(existing_event.id),
            "event_type": "object_transfer",
        },
        new_evidence={
            "event_id": str(disputed_event.id),
            "source_span_ids": [str(disputed_span.id)],
            "summary": disputed_event.summary,
        },
        existing_evidence={
            "event_id": str(existing_event.id),
            "source_span_ids": [str(existing_span.id)],
            "summary": existing_event.summary,
        },
        suggested_actions=[{"resolution": "mark_intentional"}],
        default_action="review",
    )
    session.add_all(
        [
            view,
            existing_span,
            disputed_span,
            existing_event,
            disputed_event,
            review_item,
        ]
    )
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 1
    )
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-event-intentional",
            idempotency_key="idem-review-event-intentional",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="mark_intentional",
            author_note="这是有意误导，不需要继续作为错误提醒。",
        )
    )

    assert output.status == "resolved"
    assert output.side_effects["event_intentional_conflict"] == "recorded"
    assert output.side_effects["graph_projection"] == "rebuilt"
    assert output.side_effects["graph_edges_created"] == 0
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review is not None
    assert stored_review.resolution == "mark_intentional"
    assert stored_review.side_effects["event_id"] == str(disputed_event.id)
    assert session.get(StoryCanonicalEvent, disputed_event.id).event_status == "disputed"
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 0
    )


def test_event_merge_conflict_reject_deprecates_disputed_event_and_rebuilds_graph(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-event-reject.md",
        raw_offset_map_ref="object://processed/review-event-reject.offsets.json",
        view_status="current",
    )
    existing_span = SourceSpan(
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
        text_preview="Mira kept the lantern map.",
        narration_layer="narrator",
    )
    disputed_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=25,
        end_offset=56,
        raw_start_offset=25,
        raw_end_offset=56,
        text_preview="A mistaken note says the map vanished.",
        narration_layer="narrator",
    )
    participant_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    existing_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira keeps the lantern map",
        event_status="proposed",
        primary_scene_id=None,
        event_candidate_ids=[str(uuid4())],
        participants=[participant_ref],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch001",
        summary="Mira keeps the lantern map.",
        cause_summary=None,
        consequence_summary=None,
        evidence_span_ids=[str(existing_span.id)],
    )
    disputed_candidate = StoryEventCandidate(
        id=uuid4(),
        project_id=project.id,
        scene_id=None,
        event_type="object_transfer",
        summary="A mistaken note says the map vanished.",
        participants=[participant_ref],
        objects=[object_ref],
        location_entity_id=None,
        state_change={},
        evidence_span_ids=[str(disputed_span.id)],
        confidence=0.7,
        aggregation_status="conflict_version",
    )
    disputed_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mistaken vanished-map event",
        event_status="disputed",
        primary_scene_id=None,
        event_candidate_ids=[str(disputed_candidate.id)],
        participants=[participant_ref],
        objects=[object_ref],
        location_entity_id=None,
        story_time="ch001",
        summary="A mistaken note says the map vanished.",
        cause_summary=None,
        consequence_summary=None,
        evidence_span_ids=[str(disputed_span.id)],
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="event_merge_conflict",
        severity="medium",
        status="open",
        summary="The vanished-map conflict version should be rejected.",
        affected_refs={
            "event_id": str(disputed_event.id),
            "existing_event_id": str(existing_event.id),
            "event_type": "object_transfer",
        },
        new_evidence={
            "event_id": str(disputed_event.id),
            "source_span_ids": [str(disputed_span.id)],
            "summary": disputed_event.summary,
        },
        existing_evidence={
            "event_id": str(existing_event.id),
            "source_span_ids": [str(existing_span.id)],
            "summary": existing_event.summary,
        },
        suggested_actions=[{"resolution": "reject"}],
        default_action="review",
    )
    session.add_all(
        [
            view,
            existing_span,
            disputed_span,
            existing_event,
            disputed_candidate,
            disputed_event,
            review_item,
        ]
    )
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 1
    )
    session.commit()

    with pytest.raises(ApplicationError) as missing_ref:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-event-reject-missing-ref",
                idempotency_key="idem-review-event-reject-missing-ref",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="reject",
                author_note="这是错误抽取，不进入事件线。",
                replacement_refs=[{"type": "source_delta", "id": str(uuid4())}],
            )
        )

    assert missing_ref.value.code == "not_found"
    assert "Replacement refs" in missing_ref.value.message
    assert session.get(ReviewItemRecord, review_item.id).status == "open"
    assert session.get(StoryCanonicalEvent, disputed_event.id).event_status == "disputed"
    assert (
        session.get(StoryEventCandidate, disputed_candidate.id).aggregation_status
        == "conflict_version"
    )
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 1
    )

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-event-reject",
            idempotency_key="idem-review-event-reject",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="reject",
            author_note="这是错误抽取，不进入事件线。",
        )
    )

    assert output.status == "resolved"
    assert output.side_effects["event_reject"] == "deprecated_conflict_version"
    assert output.side_effects["deprecated_event_id"] == str(disputed_event.id)
    assert output.side_effects["existing_event_id"] == str(existing_event.id)
    assert output.side_effects["event_candidates_rejected"] == 1
    assert output.side_effects["event_candidate_ids_rejected"] == [str(disputed_candidate.id)]
    assert output.side_effects["memory_pages"] == "unchanged"
    assert output.side_effects["graph_projection"] == "rebuilt"
    assert output.side_effects["graph_edges_created"] == 0

    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review is not None
    assert stored_review.resolution == "reject"
    assert stored_review.side_effects["event_reject"] == "deprecated_conflict_version"
    assert session.get(StoryCanonicalEvent, existing_event.id).event_status == "proposed"
    assert session.get(StoryCanonicalEvent, disputed_event.id).event_status == "deprecated"
    assert session.get(StoryEventCandidate, disputed_candidate.id).aggregation_status == "rejected"
    assert (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project.id)
        .filter(GraphProjectionEdge.source_ref["type"].as_string() == "review_item")
        .count()
        == 0
    )


def test_memory_writeback_memory_page_correction_records_open_thread_without_fact_or_graph_writes(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=28,
        base_hash="hash-v1",
        submitted_text_ref="object://delta/memory-page-correction.txt",
        submitted_text_search="mira keeps the map question open",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "memory_page_correction"},
        status="memory_writeback_completed",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/memory-page-correction.md",
        raw_offset_map_ref="object://processed/memory-page-correction.offsets.json",
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
        end_offset=28,
        raw_start_offset=0,
        raw_end_offset=28,
        text_preview="Mira keeps the map question open.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(delta.id)},
            {"type": "source_span", "id": str(span.id)},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:memory-page-correction",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([delta, view, span, page, extraction_audit])
    session.commit()

    input_data = MemoryWritebackDecisionInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-memory-page-correction",
        idempotency_key="idem-memory-page-correction",
        source_delta_id=delta.id,
        item_ref={"type": "memory_page", "id": str(page.id)},
        decision="correct",
        author_note="正文没错，Mira 的地图线索仍应保持开放。",
        correction={
            "action": "needs_memory_update",
            "target_section": "open_threads",
            "description": "地图来源仍是未解决线索，不能从当前页关闭。",
        },
    )
    output = ConfirmMemoryWritebackDecision(uow_factory(session)).execute(input_data)
    replay = ConfirmMemoryWritebackDecision(uow_factory(session)).execute(input_data)

    stored_page = session.get(MemoryPage, page.id)
    assert stored_page is not None
    assert output.decision_id == replay.decision_id
    assert output.side_effects["policy_action"] == "memory_page_open_thread_recorded"
    assert output.side_effects["memory_pages"] == "marked_stale"
    assert output.side_effects["memory_pages_marked_stale"] == 1
    assert output.side_effects["memory_page_ids"] == [str(page.id)]
    assert output.side_effects["memory_page_rewrite_job_ids"]
    assert output.side_effects["context_pack_readiness"] == "marked_stale"
    assert stored_page.canon_status == "stale"
    assert stored_page.contradictions == []
    assert stored_page.open_threads == [
        {
            "type": "memory_writeback_decision",
            "thread_type": "needs_memory_update",
            "source_delta_id": str(delta.id),
            "item_ref": {"type": "memory_page", "id": str(page.id)},
            "decision": "correct",
            "target_section": "open_threads",
            "description": "地图来源仍是未解决线索，不能从当前页关闭。",
            "author_note": "正文没错，Mira 的地图线索仍应保持开放。",
            "source_span_ids": [str(span.id)],
            "status": "open",
            "requires": "memory_page_rewrite",
        }
    ]
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(JobRecord).filter_by(job_type="rewrite_memory_page").count() == 1
    readiness = session.query(ContextPackReadinessRecord).one()
    assert readiness.status == "stale"
    assert readiness.reason == "review_dependency_changed"
    assert readiness.source_span_id == span.id
    assert (
        session.query(AuditEvent).filter_by(event_type="memory_writeback_preview.decision").count()
        == 1
    )


def test_memory_writeback_memory_page_correction_filters_existing_page_source_span_evidence(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=37,
        base_hash="hash-v1",
        submitted_text_ref="object://delta/memory-page-correction-filter.txt",
        submitted_text_search="subject alpha keeps the question open",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"trigger": "memory_page_correction"},
        status="memory_writeback_completed",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/memory-page-correction-filter.md",
        raw_offset_map_ref="object://processed/memory-page-correction-filter.offsets.json",
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
        end_offset=37,
        raw_start_offset=0,
        raw_end_offset=37,
        text_preview="Subject Alpha keeps the question open.",
        narration_layer="narrator",
    )
    foreign_project = Project(id=uuid4(), name="Foreign Preview Project")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Foreign Preview Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/foreign-preview.txt",
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-preview-hash-v1",
        raw_text_ref="object://raw/foreign-preview.txt",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/foreign-preview.md",
        raw_offset_map_ref="object://processed/foreign-preview.offsets.json",
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=23,
        raw_start_offset=0,
        raw_end_offset=23,
        text_preview="Foreign preview evidence.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "subject-alpha", "label": "Subject Alpha"},
        title="Subject Alpha",
        current_canon={
            "facts": [
                {
                    "fact_id": str(uuid4()),
                    "predicate": "owns",
                    "evidence_span_ids": [
                        str(span.id),
                        str(foreign_span.id),
                        "not-a-source-span-id",
                    ],
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(delta.id)},
            {"type": "source_span", "id": str(span.id)},
            {"type": "source_span", "id": str(foreign_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:memory-page-correction-filter",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all(
        [
            delta,
            view,
            span,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            page,
            extraction_audit,
        ]
    )
    session.commit()

    output = ConfirmMemoryWritebackDecision(uow_factory(session)).execute(
        MemoryWritebackDecisionInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-memory-page-correction-filter",
            idempotency_key="idem-memory-page-correction-filter",
            source_delta_id=delta.id,
            item_ref={"type": "memory_page", "id": str(page.id)},
            decision="correct",
            author_note="正文没错，线索仍应保持开放。",
            correction={
                "action": "needs_memory_update",
                "target_section": "open_threads",
                "description": "线索仍是未解决问题，不能从当前页关闭。",
            },
        )
    )

    stored_page = session.get(MemoryPage, page.id)
    assert output.side_effects["policy_action"] == "memory_page_open_thread_recorded"
    assert output.side_effects["source_span_ids"] == [str(span.id)]
    assert stored_page.open_threads[0]["source_span_ids"] == [str(span.id)]
    assert {"type": "source_span", "id": str(span.id)} in stored_page.source_refs
    assert {"type": "source_span", "id": str(foreign_span.id)} not in stored_page.source_refs
    assert {"type": "source_span", "id": "not-a-source-span-id"} not in stored_page.source_refs


def test_review_item_alias_correction_repoints_alias_mentions_facts_and_graph(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/alias-correction.md",
        raw_offset_map_ref="object://processed/alias-correction.offsets.json",
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
        end_offset=22,
        raw_start_offset=0,
        raw_end_offset=22,
        text_preview="Starling carried the map.",
        narration_layer="narrator",
    )
    old_entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Starling",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    target_entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=old_entity.id,
        alias_type="name",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(span.id)],
        confidence=0.72,
    )
    mention = StoryMention(
        id=uuid4(),
        span_id=span.id,
        raw_text="Starling",
        mention_type="character",
        local_context="Starling carried the map.",
        resolved_entity_id=old_entity.id,
        resolution_status="alias_recorded",
        confidence=0.72,
    )
    old_ref = {
        "type": "character",
        "id": str(old_entity.id),
        "label": "Starling",
        "canonical_entity_id": str(old_entity.id),
        "slug": "starling",
    }
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=old_ref,
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref=old_ref,
        title="Starling",
        current_canon={"facts": [{"fact_id": str(fact.id), "predicate": "owns"}]},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="alias_conflict",
        severity="medium",
        status="open",
        summary="Starling should resolve to Mira.",
        affected_refs={
            "alias_record_id": str(alias.id),
            "old_entity_id": str(old_entity.id),
            "target_entity_id": str(target_entity.id),
            "fact_ids": [str(fact.id)],
            "memory_page_id": str(page.id),
        },
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="accepted_as_change",
    )
    session.add_all(
        [view, span, old_entity, target_entity, alias, mention, fact, page, review_item]
    )
    session.flush()
    rebuild_graph_projection(session, project_id=project.id)
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-alias-correction",
            idempotency_key="idem-review-alias-correction",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="Starling 是 Mira 的称呼。",
            correction={
                "alias_record_id": str(alias.id),
                "target_entity_id": str(target_entity.id),
            },
        )
    )

    stored_alias = session.get(StoryAliasRecord, alias.id)
    stored_mention = session.get(StoryMention, mention.id)
    stored_fact = session.get(FactAssertionRecord, fact.id)
    stored_page = session.get(MemoryPage, page.id)
    graph_edge = session.query(GraphProjectionEdge).one()
    rewrite_job = session.get(
        JobRecord,
        UUID(str(output.side_effects["memory_page_rewrite_job_ids"][0])),
    )
    assert output.status == "resolved"
    assert output.side_effects["alias_correction"] == "applied"
    assert output.side_effects["mentions_updated"] == 1
    assert output.side_effects["fact_assertions_updated"] == 1
    assert output.side_effects["graph_projection"] == "rebuilt"
    assert stored_alias.entity_id == target_entity.id
    assert stored_alias.status == "user_corrected"
    assert stored_mention.resolved_entity_id == target_entity.id
    assert stored_mention.resolution_status == "user_corrected"
    assert stored_fact.subject_ref["id"] == str(target_entity.id)
    assert stored_fact.subject_ref["label"] == "Mira"
    assert stored_fact.subject_ref["slug"] == "mira"
    assert stored_page.target_ref["id"] == str(target_entity.id)
    assert stored_page.canon_status == "stale"
    assert graph_edge.subject_ref["id"] == str(target_entity.id)
    assert rewrite_job.job_type == "rewrite_memory_page"
    assert session.query(AuditEvent).filter_by(event_type="review_item.resolve").count() == 1


def test_review_item_alias_correction_records_author_scene_boundaries(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/disguise-boundaries.md",
        raw_offset_map_ref="object://processed/disguise-boundaries.offsets.json",
        view_status="current",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Chapter 3",
        start_offset=0,
        end_offset=240,
    )
    opening_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        start_offset=0,
        end_offset=80,
    )
    reveal_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        start_offset=160,
        end_offset=240,
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=opening_scene.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Vesper signed as Mira Vale.",
        narration_layer="narrator",
    )
    entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=entity.id,
        alias_type="disguise_name",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(span.id)],
        confidence=0.76,
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="alias_conflict",
        severity="medium",
        status="open",
        summary="Vesper is valid only during the disguise arc.",
        affected_refs={
            "alias_record_id": str(alias.id),
            "target_entity_id": str(entity.id),
        },
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="accepted_as_change",
    )
    session.add_all([view, chapter, opening_scene, reveal_scene, span, entity, alias, review_item])
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-alias-boundaries",
            idempotency_key="idem-review-alias-boundaries",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="Vesper 只在这段伪装弧内有效。",
            correction={
                "alias_record_id": str(alias.id),
                "target_entity_id": str(entity.id),
                "valid_from_scene_id": str(opening_scene.id),
                "valid_until_scene_id": str(reveal_scene.id),
            },
        )
    )

    stored_alias = session.get(StoryAliasRecord, alias.id)
    assert output.status == "resolved"
    assert output.side_effects["alias_correction"] == "applied"
    assert output.side_effects["alias_boundary_correction"] == "applied"
    assert output.side_effects["valid_from_scene_id"] == str(opening_scene.id)
    assert output.side_effects["valid_until_scene_id"] == str(reveal_scene.id)
    assert stored_alias.valid_from_scene_id == opening_scene.id
    assert stored_alias.valid_until_scene_id == reveal_scene.id
    audit = session.query(AuditEvent).filter_by(event_type="review_item.resolve").one()
    assert audit.decision["correction"]["valid_from_scene_id"] == str(opening_scene.id)
    assert audit.decision["correction"]["valid_until_scene_id"] == str(reveal_scene.id)


def test_review_item_alias_correction_bulk_applies_matching_disguise_arc_boundaries(
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/disguise-bulk-boundaries.md",
        raw_offset_map_ref="object://processed/disguise-bulk-boundaries.offsets.json",
        view_status="current",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Chapter 3",
        start_offset=0,
        end_offset=320,
    )
    opening_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        start_offset=0,
        end_offset=80,
    )
    middle_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        start_offset=80,
        end_offset=160,
    )
    reveal_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        start_offset=160,
        end_offset=240,
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=opening_scene.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Vesper signed as Mira Vale.",
        narration_layer="narrator",
    )
    second_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=middle_scene.id,
        start_offset=88,
        end_offset=128,
        raw_start_offset=88,
        raw_end_offset=128,
        text_preview="vesper crossed the archive again.",
        narration_layer="narrator",
    )
    entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    other_entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Selene",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=entity.id,
        alias_type="disguise_name",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(span.id)],
        confidence=0.76,
    )
    matching_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="vesper",
        entity_id=entity.id,
        alias_type="disguise_name",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(second_span.id)],
        confidence=0.74,
    )
    different_entity_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=other_entity.id,
        alias_type="disguise_name",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(second_span.id)],
        confidence=0.74,
    )
    global_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=entity.id,
        alias_type="name",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(second_span.id)],
        confidence=0.74,
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="alias_conflict",
        severity="medium",
        status="open",
        summary="Vesper boundaries should apply across the disguise arc.",
        affected_refs={
            "alias_record_id": str(alias.id),
            "target_entity_id": str(entity.id),
            "alias_scope": "disguise_arc",
        },
        new_evidence={"source_span_ids": [str(span.id), str(second_span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="accepted_as_change",
    )
    session.add_all(
        [
            view,
            chapter,
            opening_scene,
            middle_scene,
            reveal_scene,
            span,
            second_span,
            entity,
            other_entity,
            alias,
            matching_alias,
            different_entity_alias,
            global_alias,
            review_item,
        ]
    )
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-review-alias-bulk-boundaries",
            idempotency_key="idem-review-alias-bulk-boundaries",
            review_item_id=review_item.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="Vesper 的伪装边界应用到同一伪装弧。",
            correction={
                "alias_record_id": str(alias.id),
                "target_entity_id": str(entity.id),
                "valid_from_scene_id": str(opening_scene.id),
                "valid_until_scene_id": str(reveal_scene.id),
                "apply_to_matching_aliases": True,
            },
        )
    )

    assert output.side_effects["alias_boundary_correction"] == "applied"
    assert output.side_effects["alias_boundary_records_updated"] == 2
    assert set(output.side_effects["alias_boundary_record_ids"]) == {
        str(alias.id),
        str(matching_alias.id),
    }
    for alias_id in (alias.id, matching_alias.id):
        stored_alias = session.get(StoryAliasRecord, alias_id)
        assert stored_alias.valid_from_scene_id == opening_scene.id
        assert stored_alias.valid_until_scene_id == reveal_scene.id
        assert stored_alias.status == "user_corrected"
    for alias_id in (different_entity_alias.id, global_alias.id):
        stored_alias = session.get(StoryAliasRecord, alias_id)
        assert stored_alias.valid_from_scene_id is None
        assert stored_alias.valid_until_scene_id is None
        assert stored_alias.status == "proposed"


def test_review_item_alias_correction_rejects_boundary_scene_from_other_project(
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    other_project, other_raw_source, other_version, _other_actor_id = seed_source(session)
    other_view = SourceProcessedView(
        id=uuid4(),
        version_id=other_version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/other-project.md",
        raw_offset_map_ref="object://processed/other-project.offsets.json",
        view_status="current",
    )
    other_chapter = StoryChapter(
        id=uuid4(),
        view_id=other_view.id,
        chapter_index=0,
        title="Other Chapter",
        start_offset=0,
        end_offset=120,
    )
    other_scene = StoryScene(
        id=uuid4(),
        chapter_id=other_chapter.id,
        scene_index=0,
        start_offset=0,
        end_offset=120,
    )
    entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="provisional",
        cast_tier="unknown",
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=entity.id,
        alias_type="disguise_name",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[],
        confidence=0.76,
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="alias_conflict",
        severity="medium",
        status="open",
        summary="A disguise boundary must stay inside the review project.",
        affected_refs={
            "alias_record_id": str(alias.id),
            "target_entity_id": str(entity.id),
        },
        new_evidence={"source_span_ids": []},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="accepted_as_change",
    )
    session.add_all(
        [
            other_project,
            other_raw_source,
            other_version,
            other_view,
            other_chapter,
            other_scene,
            entity,
            alias,
            review_item,
        ]
    )
    session.commit()

    with pytest.raises(ApplicationError) as error:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-alias-cross-project-boundary",
                idempotency_key="idem-review-alias-cross-project-boundary",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="accepted_as_change",
                correction={
                    "alias_record_id": str(alias.id),
                    "target_entity_id": str(entity.id),
                    "valid_from_scene_id": str(other_scene.id),
                },
            )
        )

    assert error.value.code == "not_found"
    stored_alias = session.get(StoryAliasRecord, alias.id)
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_alias.valid_from_scene_id is None
    assert stored_alias.valid_until_scene_id is None
    assert stored_review.status == "open"


def test_review_item_alias_correction_rejects_missing_target_without_resolving(
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=None,
        alias_type="name",
        status="proposed",
        scope="global",
        evidence_span_ids=[],
        confidence=0.72,
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="alias_conflict",
        severity="medium",
        status="open",
        summary="Starling needs an entity target.",
        affected_refs={"alias_record_id": str(alias.id)},
        new_evidence={"source_span_ids": []},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="accepted_as_change",
    )
    session.add_all([alias, review_item])
    session.commit()

    with pytest.raises(ApplicationError) as error:
        OperateReviewItem(uow_factory(session)).execute(
            ReviewItemOperationInput(
                project_id=project.id,
                actor_id=actor_id,
                request_id="req-review-alias-missing-target",
                idempotency_key="idem-review-alias-missing-target",
                review_item_id=review_item.id,
                operation="resolve",
                resolution="accepted_as_change",
                correction={
                    "alias_record_id": str(alias.id),
                    "target_entity_id": str(uuid4()),
                },
            )
        )

    assert error.value.code == "not_found"
    assert session.get(ReviewItemRecord, review_item.id).status == "open"
    assert session.get(StoryAliasRecord, alias.id).status == "proposed"
