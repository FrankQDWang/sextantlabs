from __future__ import annotations

import ast
import json
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sextant.api.app import create_app
from sextant.common.observability import MetricsRegistry
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    ArchiveSourceInput,
    BuildWritingContextPackInput,
    CandidateOperationInput,
    CreateProjectInvitationInput,
    CreateSourceDeltaInput,
    CreateSourceInput,
    CreateSourceVersionInput,
    CreateStorySchemaGenrePackInput,
    DeprecateStorySchemaGenrePackInput,
    JobOperationInput,
    MemoryAnswerInput,
    MemoryPageThreadOperationInput,
    MemoryWritebackDecisionInput,
    RecordProjectInvitationExternalProofInput,
    RestoreSourceVersionInput,
    ReviewItemOperationInput,
    RevokeProjectMemberInput,
    RunActionRequestInput,
    SelectProjectStorySchemaGenreInput,
    SubmitActionRequestInput,
    UpsertProjectMemberInput,
    UpsertProjectStorySchemaOverrideInput,
)
from sextant.infra.db.models import (
    AcceptedFragmentRecord,
    AgentActionRequestRecord,
    AgentBeatCandidateRecord,
    AgentContextPackRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    AuditEvent,
    Base,
    CharacterKnowledge,
    ContextPackReadinessRecord,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
    GraphProjectionRun,
    IdempotencyRecord,
    JobRecord,
    MemoryPage,
    MemoryWritebackDecisionRecord,
    Project,
    ProjectInvitation,
    ProjectMembership,
    ProjectStorySchemaBinding,
    RawSource,
    ReviewItemRecord,
    SkillRun,
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
    StorySchemaPackRecord,
)
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.infra.worker import DbWorker
from sextant.infra.worker_handlers import build_worker_handlers
from sextant.skills.local_story_draft import LocalStoryDraftProvider
from sqlalchemy import create_engine
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
def client(session: Session) -> TestClient:
    return TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


@pytest.fixture
def client_with_objects(session: Session, object_store: LocalObjectStore) -> TestClient:
    return TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session), object_store=object_store))


def test_cors_allows_project_story_schema_override_put_preflight(session: Session) -> None:
    cors_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            allowed_origins=["http://127.0.0.1:5822"],
        )
    )

    response = cors_client.options(
        "/api/projects/00000000-0000-4000-8000-000000000001/story-schema/project-override",
        headers={
            "Origin": "http://127.0.0.1:5822",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": (
                "X-Actor-Id,X-Request-Id,Idempotency-Key,Content-Type"
            ),
        },
    )

    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]


def test_cors_allows_private_network_preflight_for_local_workbench(session: Session) -> None:
    cors_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            allowed_origins=["http://127.0.0.1:5832"],
        )
    )

    response = cors_client.options(
        "/api/projects/00000000-0000-4000-8000-000000000001/action-requests/"
        "00000000-0000-4000-8000-000000000002/run",
        headers={
            "Origin": "http://127.0.0.1:5832",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "X-Actor-Id,X-Request-Id,Idempotency-Key,Content-Type"
            ),
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-private-network"] == "true"


def drain_pipeline_jobs(
    session: Session,
    object_store: LocalObjectStore,
    *,
    worker_id: str,
    max_runs: int = 30,
) -> bool:
    worker = DbWorker(session, build_worker_handlers(object_store, LocalStoryDraftProvider()))
    processed_any = False
    for _ in range(max_runs):
        processed = worker.run_once(worker_id=worker_id)
        processed_any = processed_any or processed
        if not processed:
            break
    return processed_any


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


API_ERROR_CODES_WITH_ENDPOINT_CONTRACT_COVERAGE = {
    "authentication_required",
    "blocked_without_override",
    "candidate_not_offerable",
    "expected_output_mismatch",
    "idempotency_conflict",
    "invalid_state_transition",
    "invalid_target_range",
    "llm_output_invalid",
    "missing_target",
    "not_found",
    "permission_denied",
    "policy_blocked_promotion",
    "schema_validation_failed",
    "source_version_already_current",
    "stale_source_version",
    "unsupported_action_type",
}

READ_ENDPOINT_PERMISSION_MATRIX_PATHS = {
    "/api/projects/{project_id}",
    "/api/projects/{project_id}/invitations",
    "/api/projects/{project_id}/members",
    "/api/projects/{project_id}/action-requests/{action_request_id}",
    "/api/projects/{project_id}/candidates/{candidate_id}",
    "/api/projects/{project_id}/candidates/{candidate_id}/explain",
    "/api/projects/{project_id}/context-pack-readiness",
    "/api/projects/{project_id}/context-packs",
    "/api/projects/{project_id}/context-packs/{context_pack_id}",
    "/api/projects/{project_id}/entities",
    "/api/projects/{project_id}/graph/edges",
    "/api/projects/{project_id}/jobs/{job_id}",
    "/api/projects/{project_id}/memory/pages",
    "/api/projects/{project_id}/memory/pages/{memory_page_id}",
    "/api/projects/{project_id}/review-items",
    "/api/projects/{project_id}/review-items/{review_item_id}",
    "/api/projects/{project_id}/scenes",
    "/api/projects/{project_id}/source-deltas",
    "/api/projects/{project_id}/source-deltas/{source_delta_id}",
    "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview",
    "/api/projects/{project_id}/sources",
    "/api/projects/{project_id}/sources/{source_id}",
    "/api/projects/{project_id}/sources/{source_id}/versions",
    (
        "/api/projects/{project_id}/sources/{source_id}/versions/"
        "{base_version_id}/diff/{compare_version_id}"
    ),
    "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}",
    "/api/projects/{project_id}/story-schema",
    "/api/projects/{project_id}/story-schema/packs",
}


MUTATING_HTTP_METHODS = {"delete", "patch", "post", "put"}

WRITE_ENDPOINT_PERMISSION_MATRIX_ROUTES = {
    ("post", "/api/projects/{project_id}/action-requests"),
    ("post", "/api/projects/{project_id}/action-requests/{action_request_id}/run"),
    ("post", "/api/projects/{project_id}/agent/check-risk"),
    ("post", "/api/projects/{project_id}/agent/draft-next-passage"),
    ("post", "/api/projects/{project_id}/agent/rewrite-current-page"),
    ("post", "/api/projects/{project_id}/agent/suggest-next-beat"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/accept"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/explain"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/override-block"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/reject"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/revise"),
    ("post", "/api/projects/{project_id}/context-packs/build"),
    ("post", "/api/projects/{project_id}/jobs/{job_id}/cancel"),
    ("post", "/api/projects/{project_id}/jobs/{job_id}/retry"),
    ("post", "/api/projects/{project_id}/memory/answer"),
    (
        "post",
        "/api/projects/{project_id}/memory/pages/{memory_page_id}/open-threads/{thread_id}/operate",
    ),
    ("post", "/api/projects/{project_id}/invitations"),
    ("post", "/api/projects/{project_id}/invitations/{invitation_id}/external-proof"),
    ("post", "/api/projects/{project_id}/members/{member_actor_id}/revoke"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/dismiss"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/reopen"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/resolve"),
    ("post", "/api/projects/{project_id}/source-deltas"),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
        "memory-writeback-preview/decisions",
    ),
    ("post", "/api/projects/{project_id}/sources"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/archive"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore"),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
    ),
    ("post", "/api/projects/{project_id}/story-schema/genre-packs"),
    (
        "post",
        "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate",
    ),
    ("put", "/api/projects/{project_id}/story-schema/genre-pack"),
    ("put", "/api/projects/{project_id}/story-schema/project-override"),
    ("put", "/api/projects/{project_id}/members/{member_actor_id}"),
}

API_AUTHENTICATION_MATRIX_ROUTES = {
    ("get", path) for path in READ_ENDPOINT_PERMISSION_MATRIX_PATHS
} | WRITE_ENDPOINT_PERMISSION_MATRIX_ROUTES

NO_SIDE_EFFECT_COMMAND_ROUTES = {
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/explain")
}

WRITE_IDEMPOTENCY_HEADER_MATRIX_ROUTES = (
    WRITE_ENDPOINT_PERMISSION_MATRIX_ROUTES - NO_SIDE_EFFECT_COMMAND_ROUTES
)

WRITE_IDEMPOTENCY_VALUE_MATRIX_ROUTES = WRITE_IDEMPOTENCY_HEADER_MATRIX_ROUTES

WRITE_IDEMPOTENCY_CONFLICT_OPERATION_BY_ROUTE = {
    ("post", "/api/projects/{project_id}/action-requests"): "submit_action_request",
    ("post", "/api/projects/{project_id}/action-requests/{action_request_id}/run"): (
        "action_request.run"
    ),
    ("post", "/api/projects/{project_id}/agent/check-risk"): "submit_action_request",
    ("post", "/api/projects/{project_id}/agent/draft-next-passage"): "submit_action_request",
    ("post", "/api/projects/{project_id}/agent/rewrite-current-page"): "submit_action_request",
    ("post", "/api/projects/{project_id}/agent/suggest-next-beat"): "submit_action_request",
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/accept"): "accept_candidate",
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/override-block"): (
        "candidate.override_block"
    ),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/reject"): ("candidate.reject"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/revise"): ("candidate.revise"),
    ("post", "/api/projects/{project_id}/context-packs/build"): "context_pack.build",
    ("post", "/api/projects/{project_id}/jobs/{job_id}/cancel"): "job.cancel",
    ("post", "/api/projects/{project_id}/jobs/{job_id}/retry"): "job.retry",
    ("post", "/api/projects/{project_id}/memory/answer"): "memory.answer",
    (
        "post",
        "/api/projects/{project_id}/memory/pages/{memory_page_id}/open-threads/{thread_id}/operate",
    ): "memory_page.open_thread.operate",
    ("post", "/api/projects/{project_id}/invitations"): "project_invitation.create",
    ("post", "/api/projects/{project_id}/invitations/{invitation_id}/external-proof"): (
        "project_invitation.external_proof"
    ),
    ("post", "/api/projects/{project_id}/members/{member_actor_id}/revoke"): (
        "project_member.revoke"
    ),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/dismiss"): (
        "review_item.dismiss"
    ),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/reopen"): (
        "review_item.reopen"
    ),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/resolve"): (
        "review_item.resolve"
    ),
    ("post", "/api/projects/{project_id}/source-deltas"): "source_delta.create",
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
        "memory-writeback-preview/decisions",
    ): "memory_writeback_preview.decision",
    ("post", "/api/projects/{project_id}/sources"): "source.create",
    ("post", "/api/projects/{project_id}/sources/{source_id}/archive"): "source.archive",
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions"): ("source_version.create"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore"): (
        "source_version.restore"
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
    ): "source_delta.create",
    ("post", "/api/projects/{project_id}/story-schema/genre-packs"): (
        "story_schema.genre_pack.create"
    ),
    (
        "post",
        "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate",
    ): "story_schema.genre_pack.deprecate",
    ("put", "/api/projects/{project_id}/story-schema/genre-pack"): (
        "story_schema.genre_pack.select"
    ),
    ("put", "/api/projects/{project_id}/story-schema/project-override"): (
        "story_schema.project_override.upsert"
    ),
    ("put", "/api/projects/{project_id}/members/{member_actor_id}"): ("project_member.upsert"),
}

WRITE_IDEMPOTENCY_REPLAY_ROUTES = set(WRITE_IDEMPOTENCY_CONFLICT_OPERATION_BY_ROUTE)

WRITE_RESOURCE_NOT_FOUND_PARAM_BY_ROUTE = {
    ("post", "/api/projects/{project_id}/action-requests/{action_request_id}/run"): (
        "action_request_id"
    ),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/accept"): "candidate_id",
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/override-block"): (
        "candidate_id"
    ),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/reject"): "candidate_id",
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/revise"): "candidate_id",
    ("post", "/api/projects/{project_id}/jobs/{job_id}/cancel"): "job_id",
    ("post", "/api/projects/{project_id}/jobs/{job_id}/retry"): "job_id",
    ("post", "/api/projects/{project_id}/invitations/{invitation_id}/external-proof"): (
        "invitation_id"
    ),
    ("post", "/api/projects/{project_id}/members/{member_actor_id}/revoke"): ("member_actor_id"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/dismiss"): (
        "review_item_id"
    ),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/reopen"): ("review_item_id"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/resolve"): (
        "review_item_id"
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
        "memory-writeback-preview/decisions",
    ): "source_delta_id",
    ("post", "/api/projects/{project_id}/sources/{source_id}/archive"): "source_id",
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions"): "source_id",
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore"): (
        "source_id"
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
    ): "source_id",
}
WRITE_RESOURCE_NOT_FOUND_MATRIX_ROUTES = set(WRITE_RESOURCE_NOT_FOUND_PARAM_BY_ROUTE)
WRITE_RESOURCE_NOT_FOUND_EXCLUDED_ROUTES = NO_SIDE_EFFECT_COMMAND_ROUTES | {
    ("post", "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate"),
    ("put", "/api/projects/{project_id}/members/{member_actor_id}"),
}

BODY_RESOURCE_NOT_FOUND_REQUIRED_CASES = {
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/accept",
        "target_version_id",
    ),
    (
        "post",
        "/api/projects/{project_id}/review-items/{review_item_id}/resolve",
        "replacement_refs.source_delta",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas",
        "previous_version_id",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas",
        "source_id",
    ),
    (
        "post",
        (
            "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
            "memory-writeback-preview/decisions"
        ),
        "item_ref",
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions",
        "supersedes_version_id",
    ),
    (
        "put",
        "/api/projects/{project_id}/story-schema/genre-pack",
        "genre_schema_pack_id",
    ),
}
WRITE_BODY_RESOURCE_NOT_FOUND_CASES = set(BODY_RESOURCE_NOT_FOUND_REQUIRED_CASES)

WRITE_STATE_ERROR_REQUIRED_CASES = {
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_already_succeeded",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/accept",
        "candidate_accept_blocked",
        409,
        "blocked_without_override",
    ),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/accept",
        "candidate_accept_stale_base",
        409,
        "stale_source_version",
    ),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/override-block",
        "candidate_override_not_blocked",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/reject",
        "candidate_reject_archived",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/revise",
        "candidate_revise_archived",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/jobs/{job_id}/cancel",
        "job_cancel_succeeded",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/jobs/{job_id}/retry",
        "job_retry_succeeded",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/review-items/{review_item_id}/dismiss",
        "review_dismiss_dismissed",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/review-items/{review_item_id}/reopen",
        "review_reopen_open",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/review-items/{review_item_id}/resolve",
        "review_resolve_dismissed",
        409,
        "invalid_state_transition",
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore",
        "source_restore_current",
        409,
        "source_version_already_current",
    ),
}
WRITE_STATE_ERROR_CASES = set(WRITE_STATE_ERROR_REQUIRED_CASES)

SOURCE_DELTA_STALE_BASE_HASH_REQUIRED_CASES = {
    (
        "post",
        "/api/projects/{project_id}/source-deltas",
        "project_source_delta_base_hash",
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
        "nested_source_delta_base_hash",
    ),
}
SOURCE_DELTA_STALE_BASE_HASH_CASES = set(SOURCE_DELTA_STALE_BASE_HASH_REQUIRED_CASES)

WRITE_SUCCESS_SIDE_EFFECT_REQUIRED_CASES = {
    ("post", "/api/projects/{project_id}/action-requests", "action_request_submit"),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_ask_memory",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_check_risk",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_draft_next_passage",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_explain_candidate",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_revise_candidate",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_rewrite_current_page",
    ),
    (
        "post",
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        "action_request_run_suggest_next_direction",
    ),
    ("post", "/api/projects/{project_id}/agent/check-risk", "agent_wrapper_check_risk"),
    (
        "post",
        "/api/projects/{project_id}/agent/draft-next-passage",
        "agent_wrapper_draft_next_passage",
    ),
    (
        "post",
        "/api/projects/{project_id}/agent/rewrite-current-page",
        "agent_wrapper_rewrite_current_page",
    ),
    (
        "post",
        "/api/projects/{project_id}/agent/suggest-next-beat",
        "agent_wrapper_suggest_next_beat",
    ),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/accept", "candidate_accept"),
    (
        "post",
        "/api/projects/{project_id}/candidates/{candidate_id}/override-block",
        "candidate_override_block",
    ),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/reject", "candidate_reject"),
    ("post", "/api/projects/{project_id}/candidates/{candidate_id}/revise", "candidate_revise"),
    ("post", "/api/projects/{project_id}/context-packs/build", "context_pack_build"),
    ("post", "/api/projects/{project_id}/jobs/{job_id}/cancel", "job_cancel"),
    ("post", "/api/projects/{project_id}/jobs/{job_id}/retry", "job_retry"),
    ("post", "/api/projects/{project_id}/memory/answer", "memory_answer"),
    (
        "post",
        "/api/projects/{project_id}/memory/pages/{memory_page_id}/open-threads/{thread_id}/operate",
        "memory_page_thread_operate",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_evidence_log_reject",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_fact_accept",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_fact_correct",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_fact_reject",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_graph_edge_reject",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_memory_page_reject",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_review_item_accept",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_review_item_reject",
    ),
    (
        "post",
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        "memory_writeback_decision_source_span_reject",
    ),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/dismiss", "review_dismiss"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/reopen", "review_reopen"),
    ("post", "/api/projects/{project_id}/review-items/{review_item_id}/resolve", "review_resolve"),
    ("post", "/api/projects/{project_id}/source-deltas", "project_source_delta_create"),
    ("post", "/api/projects/{project_id}/sources", "source_create"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/archive", "source_archive"),
    ("post", "/api/projects/{project_id}/sources/{source_id}/versions", "source_version_create"),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore",
        "source_version_restore",
    ),
    (
        "post",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
        "nested_source_delta_create",
    ),
    ("post", "/api/projects/{project_id}/story-schema/genre-packs", "genre_pack_create"),
    (
        "post",
        "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate",
        "genre_pack_deprecate",
    ),
    ("put", "/api/projects/{project_id}/story-schema/genre-pack", "genre_pack_select"),
    ("put", "/api/projects/{project_id}/story-schema/project-override", "project_override_upsert"),
}
CANDIDATE_WRITE_SUCCESS_CASE_NAMES = {
    "candidate_accept",
    "candidate_override_block",
    "candidate_reject",
    "candidate_revise",
}
MEMORY_CONTEXT_WRITE_SUCCESS_CASE_NAMES = {
    "context_pack_build",
    "memory_answer",
}
MEMORY_PAGE_WRITE_SUCCESS_CASE_NAMES = {
    "memory_page_thread_operate",
}
ACTION_REQUEST_WRITE_SUCCESS_CASE_NAMES = {
    "action_request_submit",
    "action_request_run_ask_memory",
    "action_request_run_check_risk",
    "action_request_run_draft_next_passage",
    "action_request_run_explain_candidate",
    "action_request_run_revise_candidate",
    "action_request_run_rewrite_current_page",
    "action_request_run_suggest_next_direction",
    "agent_wrapper_check_risk",
    "agent_wrapper_draft_next_passage",
    "agent_wrapper_rewrite_current_page",
    "agent_wrapper_suggest_next_beat",
}
MEMORY_WRITEBACK_WRITE_SUCCESS_CASE_NAMES = {
    "memory_writeback_decision_evidence_log_reject",
    "memory_writeback_decision_fact_accept",
    "memory_writeback_decision_fact_correct",
    "memory_writeback_decision_fact_reject",
    "memory_writeback_decision_graph_edge_reject",
    "memory_writeback_decision_memory_page_reject",
    "memory_writeback_decision_review_item_accept",
    "memory_writeback_decision_review_item_reject",
    "memory_writeback_decision_source_span_reject",
}
WRITE_SUCCESS_SIDE_EFFECT_CASES = set(WRITE_SUCCESS_SIDE_EFFECT_REQUIRED_CASES)
JOB_REVIEW_WRITE_SUCCESS_CASE_NAMES = {
    "job_cancel",
    "job_retry",
    "review_dismiss",
    "review_reopen",
    "review_resolve",
}
SOURCE_SCHEMA_WRITE_SUCCESS_CASE_NAMES = {
    case_name
    for _method, _route_template, case_name in WRITE_SUCCESS_SIDE_EFFECT_REQUIRED_CASES
    if case_name
    not in (
        CANDIDATE_WRITE_SUCCESS_CASE_NAMES
        | JOB_REVIEW_WRITE_SUCCESS_CASE_NAMES
        | MEMORY_CONTEXT_WRITE_SUCCESS_CASE_NAMES
        | MEMORY_PAGE_WRITE_SUCCESS_CASE_NAMES
        | ACTION_REQUEST_WRITE_SUCCESS_CASE_NAMES
        | MEMORY_WRITEBACK_WRITE_SUCCESS_CASE_NAMES
    )
}

READ_RESOURCE_NOT_FOUND_MATRIX_PATHS = {
    "/api/projects/{project_id}/action-requests/{action_request_id}",
    "/api/projects/{project_id}/candidates/{candidate_id}",
    "/api/projects/{project_id}/candidates/{candidate_id}/explain",
    "/api/projects/{project_id}/context-packs/{context_pack_id}",
    "/api/projects/{project_id}/jobs/{job_id}",
    "/api/projects/{project_id}/memory/pages/{memory_page_id}",
    "/api/projects/{project_id}/review-items/{review_item_id}",
    "/api/projects/{project_id}/source-deltas/{source_delta_id}",
    "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview",
    "/api/projects/{project_id}/sources/{source_id}",
    "/api/projects/{project_id}/sources/{source_id}/versions",
    (
        "/api/projects/{project_id}/sources/{source_id}/versions/"
        "{base_version_id}/diff/{compare_version_id}"
    ),
    "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}",
}


def test_real_application_error_codes_have_api_contract_matrix_coverage() -> None:
    missing_codes = (
        _actual_api_error_codes_from_source() - API_ERROR_CODES_WITH_ENDPOINT_CONTRACT_COVERAGE
    )

    assert missing_codes == set()


def test_read_endpoint_permission_matrix_covers_every_get_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    get_routes = {
        path
        for path, methods in openapi_paths.items()
        if path.startswith("/api/") and "get" in methods
    }

    assert get_routes - READ_ENDPOINT_PERMISSION_MATRIX_PATHS == set()


def test_read_resource_not_found_matrix_covers_every_resource_get_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    resource_param_names = {
        "action_request_id",
        "base_version_id",
        "candidate_id",
        "compare_version_id",
        "context_pack_id",
        "job_id",
        "memory_page_id",
        "review_item_id",
        "source_delta_id",
        "source_id",
        "version_id",
    }
    resource_get_routes = {
        path
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        and "get" in methods
        and any(f"{{{param_name}}}" in path for param_name in resource_param_names)
    }

    assert resource_get_routes - READ_RESOURCE_NOT_FOUND_MATRIX_PATHS == set()


def test_read_resource_endpoints_return_not_found_without_persistence_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    missing_ids = {
        "project_id": project.id,
        "source_id": uuid4(),
        "version_id": uuid4(),
        "base_version_id": uuid4(),
        "compare_version_id": uuid4(),
        "source_delta_id": uuid4(),
        "memory_page_id": uuid4(),
        "review_item_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "job_id": uuid4(),
    }
    before_counts = _permission_matrix_side_effect_counts(session)

    for route_template in sorted(READ_RESOURCE_NOT_FOUND_MATRIX_PATHS):
        response = client_with_objects.get(
            _api_route_url(route_template, missing_ids),
            headers={"X-Actor-Id": str(actor_id)},
        )

        _assert_api_error_response(
            response,
            status_code=404,
            code="not_found",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_write_endpoint_permission_matrix_covers_every_mutating_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    mutating_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
    }

    assert mutating_routes - WRITE_ENDPOINT_PERMISSION_MATRIX_ROUTES == set()


def test_write_idempotency_header_matrix_covers_every_state_changing_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    state_changing_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
    } - NO_SIDE_EFFECT_COMMAND_ROUTES

    assert state_changing_routes - WRITE_IDEMPOTENCY_HEADER_MATRIX_ROUTES == set()
    for method, path in sorted(WRITE_IDEMPOTENCY_HEADER_MATRIX_ROUTES):
        required_headers = {
            parameter["name"]
            for parameter in openapi_paths[path][method].get("parameters", [])
            if parameter.get("in") == "header" and parameter.get("required") is True
        }
        assert {"X-Request-Id", "Idempotency-Key"} <= required_headers


def test_write_idempotency_value_matrix_covers_every_state_changing_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    state_changing_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
    } - NO_SIDE_EFFECT_COMMAND_ROUTES

    assert state_changing_routes - WRITE_IDEMPOTENCY_VALUE_MATRIX_ROUTES == set()


def test_write_idempotency_conflict_matrix_covers_every_state_changing_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    state_changing_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
    } - NO_SIDE_EFFECT_COMMAND_ROUTES

    assert state_changing_routes - set(WRITE_IDEMPOTENCY_CONFLICT_OPERATION_BY_ROUTE) == set()


def test_write_idempotency_replay_matrix_covers_every_state_changing_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    state_changing_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
    } - NO_SIDE_EFFECT_COMMAND_ROUTES

    assert state_changing_routes - WRITE_IDEMPOTENCY_REPLAY_ROUTES == set()


def test_write_resource_not_found_matrix_covers_every_state_changing_resource_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    resource_param_names = {
        "action_request_id",
        "candidate_id",
        "job_id",
        "invitation_id",
        "member_actor_id",
        "pack_id",
        "review_item_id",
        "source_delta_id",
        "source_id",
        "version_id",
    }
    state_changing_resource_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method in MUTATING_HTTP_METHODS
        and any(f"{{{param_name}}}" in path for param_name in resource_param_names)
    } - WRITE_RESOURCE_NOT_FOUND_EXCLUDED_ROUTES

    assert state_changing_resource_routes - WRITE_RESOURCE_NOT_FOUND_MATRIX_ROUTES == set()


def test_write_body_resource_not_found_matrix_covers_documented_body_resource_cases() -> None:
    assert set() == BODY_RESOURCE_NOT_FOUND_REQUIRED_CASES - WRITE_BODY_RESOURCE_NOT_FOUND_CASES


def test_write_state_error_matrix_covers_documented_state_transition_cases() -> None:
    assert set() == WRITE_STATE_ERROR_REQUIRED_CASES - WRITE_STATE_ERROR_CASES


def test_source_delta_stale_base_hash_matrix_covers_documented_routes() -> None:
    assert set() == (
        SOURCE_DELTA_STALE_BASE_HASH_REQUIRED_CASES - SOURCE_DELTA_STALE_BASE_HASH_CASES
    )


def test_write_success_side_effect_matrix_covers_documented_routes() -> None:
    assert set() == WRITE_SUCCESS_SIDE_EFFECT_REQUIRED_CASES - WRITE_SUCCESS_SIDE_EFFECT_CASES


def test_source_schema_write_endpoints_persist_expected_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in SOURCE_SCHEMA_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_source_schema_success_matrix_objects(session, object_store)
        success_client = TestClient(
            create_app(
                lambda: SqlAlchemyUnitOfWork(session),
                object_store=object_store,
                admin_actor_ids={UUID(str(ids["actor_id"]))},
            )
        )
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_source_schema_success_case(
            session,
            object_store,
            route_template,
            case_name,
            ids,
            payload,
        )
        before = _permission_matrix_side_effect_counts(session)
        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-source-schema-success-{index}",
                "Idempotency-Key": f"idem-source-schema-success-{index}",
            },
            json=payload,
        )

        assert response.status_code in {200, 201}, (method, route_template, response.json())
        _assert_source_schema_success_side_effects(
            session,
            object_store,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_candidate_write_endpoints_persist_expected_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in CANDIDATE_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_candidate_success_matrix_objects(session, object_store)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_candidate_success_case(session, case_name, ids, payload)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(
            create_app(lambda: SqlAlchemyUnitOfWork(session), object_store=object_store)
        )

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-candidate-success-{index}",
                "Idempotency-Key": f"idem-candidate-success-{index}",
            },
            json=payload,
        )

        assert response.status_code == 200, (method, route_template, response.json())
        _assert_candidate_success_side_effects(
            session,
            object_store,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_memory_context_write_endpoints_persist_expected_success_side_effects(
    session: Session,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in MEMORY_CONTEXT_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_memory_context_success_matrix_objects(session)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_memory_context_success_case(case_name, ids, payload)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-memory-context-success-{index}",
                "Idempotency-Key": f"idem-memory-context-success-{index}",
            },
            json=payload,
        )

        assert response.status_code == 200, (method, route_template, response.json())
        _assert_memory_context_success_side_effects(
            session,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_memory_page_write_endpoints_persist_expected_success_side_effects(
    session: Session,
) -> None:
    for index, (method, route_template, _case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in MEMORY_PAGE_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_write_permission_matrix_objects(session)
        payload = _write_endpoint_permission_payload(route_template, ids)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-memory-page-success-{index}",
                "Idempotency-Key": f"idem-memory-page-success-{index}",
            },
            json=payload,
        )

        assert response.status_code == 200, (method, route_template, response.json())
        _assert_memory_page_thread_success_side_effects(
            session,
            ids,
            response.json(),
            before,
        )


def test_memory_page_open_thread_operation_requires_source_span_evidence(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-origin",
                "update_type": "opens",
                "summary": "Who gave Mira the lantern map?",
                "risk_level": "low",
                "source_span_ids": ["not-a-source-span-id"],
                "status": "open",
            }
        ],
        contradictions=[],
        source_refs=[],
        canon_status="current",
        memory_depth="scene",
    )
    session.add(page)
    session.commit()
    before = _permission_matrix_side_effect_counts(session)

    response = client.post(
        f"/api/projects/{project.id}/memory/pages/{page.id}/open-threads/map-origin/operate",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-memory-page-thread-missing-evidence",
            "Idempotency-Key": "idem-memory-page-thread-missing-evidence",
        },
        json={
            "update_type": "closes",
            "author_note": "Close this after review.",
        },
    )

    _assert_api_error_response(
        response,
        status_code=409,
        code="invalid_state_transition",
    )
    assert _permission_matrix_side_effect_counts(session) == before


def test_action_request_write_endpoints_persist_expected_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in ACTION_REQUEST_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_action_request_success_matrix_objects(session, object_store, case_name)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_action_request_success_case(case_name, payload)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(
            create_app(
                lambda: SqlAlchemyUnitOfWork(session),
                object_store=object_store,
                story_draft_provider=LocalStoryDraftProvider(),
            )
        )

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-action-success-{index}",
                "Idempotency-Key": f"idem-action-success-{index}",
            },
            json=payload,
        )

        expected_status = 201 if case_name == "action_request_submit" else 200
        assert response.status_code == expected_status, (
            method,
            route_template,
            case_name,
            response.json(),
        )
        _assert_action_request_success_side_effects(
            session,
            object_store,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_memory_writeback_write_endpoints_persist_expected_success_side_effects(
    session: Session,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in MEMORY_WRITEBACK_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_memory_writeback_success_matrix_objects(session, case_name)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_memory_writeback_success_case(case_name, ids, payload)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-memory-writeback-success-{index}",
                "Idempotency-Key": f"idem-memory-writeback-success-{index}",
            },
            json=payload,
        )

        assert response.status_code == 200, (method, route_template, case_name, response.json())
        _assert_memory_writeback_success_side_effects(
            session,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_job_review_write_endpoints_persist_expected_success_side_effects(
    session: Session,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(
            case
            for case in WRITE_SUCCESS_SIDE_EFFECT_CASES
            if case[2] in JOB_REVIEW_WRITE_SUCCESS_CASE_NAMES
        )
    ):
        ids = _seed_job_review_success_matrix_objects(session)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_job_review_success_case(session, case_name, ids, payload)
        before = _permission_matrix_side_effect_counts(session)
        success_client = TestClient(create_app(lambda: SqlAlchemyUnitOfWork(session)))

        response = success_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-job-review-success-{index}",
                "Idempotency-Key": f"idem-job-review-success-{index}",
            },
            json=payload,
        )

        assert response.status_code == 200, (method, route_template, response.json())
        _assert_job_review_success_side_effects(
            session,
            case_name,
            ids,
            response.json(),
            before,
        )


def test_api_authentication_matrix_covers_every_api_route(
    client: TestClient,
) -> None:
    openapi_paths = client.app.openapi()["paths"]
    api_routes = {
        (method, path)
        for path, methods in openapi_paths.items()
        if path.startswith("/api/")
        for method in methods
        if method == "get" or method in MUTATING_HTTP_METHODS
    }

    assert api_routes - API_AUTHENTICATION_MATRIX_ROUTES == set()


def test_api_endpoints_require_actor_identity_without_persistence_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(sorted(API_AUTHENTICATION_MATRIX_ROUTES)):
        url = _api_route_url(route_template, ids)
        headers = {
            "X-Request-Id": f"req-missing-actor-{index}",
            "Idempotency-Key": f"idem-missing-actor-{index}",
        }
        payload = None
        if method in MUTATING_HTTP_METHODS:
            payload = _write_endpoint_permission_payload(route_template, ids)
        request_kwargs = {"headers": headers}
        if payload is not None:
            request_kwargs["json"] = payload

        response = client_with_objects.request(method.upper(), url, **request_kwargs)

        assert response.status_code == 401, (method, route_template, response.json())
        _assert_api_error_response(
            response,
            status_code=401,
            code="authentication_required",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_api_validation_errors_use_common_envelope_without_persistence_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    invalid_actor_response = client_with_objects.get(
        f"/api/projects/{project.id}",
        headers={"X-Actor-Id": "not-a-uuid"},
    )
    invalid_body_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-invalid-body-envelope",
            "Idempotency-Key": "idem-invalid-body-envelope",
        },
        json={
            "title": "Invalid Import",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "ownership_status": "owned",
        },
    )

    _assert_api_error_response(
        invalid_actor_response,
        status_code=400,
        code="schema_validation_failed",
    )
    _assert_api_error_response(
        invalid_body_response,
        status_code=400,
        code="schema_validation_failed",
    )
    assert "input" not in str(invalid_body_response.json()["error"]["details"])
    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_write_endpoints_reject_non_members_without_persistence_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    outsider_id = uuid4()
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(
        sorted(WRITE_ENDPOINT_PERMISSION_MATRIX_ROUTES)
    ):
        url = _api_route_url(route_template, ids)
        headers = {
            "X-Actor-Id": str(outsider_id),
            "X-Request-Id": f"req-non-member-write-{index}",
            "Idempotency-Key": f"idem-non-member-write-{index}",
        }
        payload = _write_endpoint_permission_payload(route_template, ids)
        request_kwargs = {"headers": headers}
        if payload is not None:
            request_kwargs["json"] = payload

        response = client_with_objects.request(method.upper(), url, **request_kwargs)

        assert response.status_code == 403, (method, route_template, response.json())
        _assert_api_error_response(
            response,
            status_code=403,
            code="permission_denied",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_endpoints_require_idempotency_headers_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(
        sorted(WRITE_IDEMPOTENCY_HEADER_MATRIX_ROUTES)
    ):
        url = _api_route_url(route_template, ids)
        payload = _write_endpoint_permission_payload(route_template, ids)

        for header_case, headers in {
            "missing_request_id": {
                "X-Actor-Id": str(ids["actor_id"]),
                "Idempotency-Key": f"idem-missing-request-id-{index}",
            },
            "missing_idempotency_key": {
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-missing-idempotency-key-{index}",
            },
        }.items():
            request_kwargs = {"headers": headers}
            if payload is not None:
                request_kwargs["json"] = payload

            response = client_with_objects.request(method.upper(), url, **request_kwargs)

            assert response.status_code == 400, (
                header_case,
                method,
                route_template,
                response.json(),
            )
            _assert_api_error_response(
                response,
                status_code=400,
                code="schema_validation_failed",
            )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_endpoints_reject_blank_idempotency_key_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(sorted(WRITE_IDEMPOTENCY_VALUE_MATRIX_ROUTES)):
        url = _api_route_url(route_template, ids)
        headers = {
            "X-Actor-Id": str(ids["actor_id"]),
            "X-Request-Id": f"req-blank-idempotency-key-{index}",
            "Idempotency-Key": "",
        }
        payload = _write_endpoint_permission_payload(route_template, ids)
        request_kwargs = {"headers": headers}
        if payload is not None:
            request_kwargs["json"] = payload

        response = client_with_objects.request(method.upper(), url, **request_kwargs)

        assert response.status_code == 400, (method, route_template, response.json())
        _assert_api_error_response(
            response,
            status_code=400,
            code="schema_validation_failed",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_endpoints_reject_idempotency_conflicts_without_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    _seed_idempotency_conflict_records(session, ids)
    conflict_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            admin_actor_ids={ids["actor_id"]},
        )
    )
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(
        sorted(WRITE_IDEMPOTENCY_CONFLICT_OPERATION_BY_ROUTE)
    ):
        url = _api_route_url(route_template, ids)
        headers = {
            "X-Actor-Id": str(ids["actor_id"]),
            "X-Request-Id": f"req-idempotency-conflict-{index}",
            "Idempotency-Key": _idempotency_conflict_key(index),
        }
        payload = _write_endpoint_permission_payload(route_template, ids)
        request_kwargs = {"headers": headers}
        if payload is not None:
            request_kwargs["json"] = payload

        response = conflict_client.request(method.upper(), url, **request_kwargs)

        assert response.status_code == 409, (method, route_template, response.json())
        _assert_api_error_response(
            response,
            status_code=409,
            code="idempotency_conflict",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_endpoints_replay_matching_idempotency_records_without_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    for index, (method, route_template) in enumerate(sorted(WRITE_IDEMPOTENCY_REPLAY_ROUTES)):
        ids = _seed_write_permission_matrix_objects(session)
        idempotency_key = _idempotency_replay_key(index)
        request_id = f"req-idempotency-replay-{index}"
        payload = _write_endpoint_permission_payload(route_template, ids)
        expected_response = _seed_idempotency_replay_records(
            session,
            route_template,
            ids,
            request_id=request_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        replay_client = TestClient(
            create_app(
                lambda: SqlAlchemyUnitOfWork(session),
                object_store=object_store,
                admin_actor_ids={UUID(str(ids["actor_id"]))},
            )
        )
        before_counts = _permission_matrix_side_effect_counts(session)
        request_kwargs = {
            "headers": {
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": request_id,
                "Idempotency-Key": idempotency_key,
            }
        }
        if payload is not None:
            request_kwargs["json"] = payload

        response = replay_client.request(
            method.upper(),
            _api_route_url(route_template, ids),
            **request_kwargs,
        )

        assert response.status_code in {200, 201}, (method, route_template, response.json())
        _assert_json_contains(response.json(), expected_response)
        assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_resource_endpoints_return_not_found_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template) in enumerate(
        sorted(WRITE_RESOURCE_NOT_FOUND_MATRIX_ROUTES)
    ):
        missing_ids = dict(ids)
        missing_param = WRITE_RESOURCE_NOT_FOUND_PARAM_BY_ROUTE[(method, route_template)]
        missing_ids[missing_param] = uuid4()
        payload = _write_endpoint_permission_payload(route_template, missing_ids)
        request_kwargs = {
            "headers": {
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-write-not-found-{index}",
                "Idempotency-Key": f"idem-write-not-found-{index}",
            }
        }
        if payload is not None:
            request_kwargs["json"] = payload

        response = client_with_objects.request(
            method.upper(),
            _api_route_url(route_template, missing_ids),
            **request_kwargs,
        )

        assert response.status_code == 404, (method, route_template, response.json())
        _assert_api_error_response(
            response,
            status_code=404,
            code="not_found",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_body_resource_endpoints_return_not_found_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    ids = _seed_write_permission_matrix_objects(session)
    before_counts = _permission_matrix_side_effect_counts(session)

    for index, (method, route_template, body_case) in enumerate(
        sorted(WRITE_BODY_RESOURCE_NOT_FOUND_CASES)
    ):
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _body_resource_not_found_payload(session, ids, payload, body_case)
        response = client_with_objects.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-write-body-not-found-{index}",
                "Idempotency-Key": f"idem-write-body-not-found-{index}",
            },
            json=payload,
        )

        assert response.status_code == 404, (method, route_template, body_case, response.json())
        _assert_api_error_response(
            response,
            status_code=404,
            code="not_found",
        )

    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_state_changing_endpoints_return_route_state_errors_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    for index, (
        method,
        route_template,
        case_name,
        expected_status,
        expected_code,
    ) in enumerate(sorted(WRITE_STATE_ERROR_CASES)):
        ids = _seed_write_permission_matrix_objects(session)
        payload = _write_endpoint_permission_payload(route_template, ids)
        payload = _prepare_write_state_error_case(session, ids, payload, case_name)
        before = _write_state_error_side_effect_snapshot(session, ids)
        request_kwargs = {
            "headers": {
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-write-state-error-{index}",
                "Idempotency-Key": f"idem-write-state-error-{index}",
            }
        }
        if payload is not None:
            request_kwargs["json"] = payload

        response = client_with_objects.request(
            method.upper(),
            _api_route_url(route_template, ids),
            **request_kwargs,
        )

        assert response.status_code == expected_status, (
            method,
            route_template,
            case_name,
            response.json(),
        )
        _assert_api_error_response(
            response,
            status_code=expected_status,
            code=expected_code,
        )
        assert _write_state_error_side_effect_snapshot(session, ids) == before


def test_source_delta_stale_base_hash_endpoints_reject_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    for index, (method, route_template, case_name) in enumerate(
        sorted(SOURCE_DELTA_STALE_BASE_HASH_CASES)
    ):
        ids = _seed_write_permission_matrix_objects(session)
        payload = _write_endpoint_permission_payload(route_template, ids)
        assert payload is not None
        stale_hash = f"stale-base-hash-{case_name}"
        payload = {**payload, "base_hash": stale_hash}
        before_counts = _permission_matrix_side_effect_counts(session)

        response = client_with_objects.request(
            method.upper(),
            _api_route_url(route_template, ids),
            headers={
                "X-Actor-Id": str(ids["actor_id"]),
                "X-Request-Id": f"req-source-delta-stale-base-{index}",
                "Idempotency-Key": f"idem-source-delta-stale-base-{index}",
            },
            json=payload,
        )

        _assert_api_error_response(
            response,
            status_code=409,
            code="stale_source_version",
        )
        details = response.json()["error"]["details"]
        assert details["request_base_hash"] == stale_hash
        assert details["current_hash"] == ids["raw_hash"]
        assert _permission_matrix_side_effect_counts(session) == before_counts


def test_read_endpoints_reject_non_members_without_write_side_effects(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    outsider_id = uuid4()
    ids = {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "source_delta_id": uuid4(),
        "memory_page_id": uuid4(),
        "review_item_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "job_id": uuid4(),
    }

    for route_template in sorted(READ_ENDPOINT_PERMISSION_MATRIX_PATHS):
        url = _api_route_url(route_template, ids)
        response = client_with_objects.get(
            url,
            headers={"X-Actor-Id": str(outsider_id)},
        )
        _assert_api_error_response(
            response,
            status_code=403,
            code="permission_denied",
        )

    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0


def _api_route_url(route_template: str, ids: dict[str, UUID | str]) -> str:
    url = route_template
    for key, value in ids.items():
        url = url.replace(f"{{{key}}}", str(value))
    return url


def _seed_write_permission_matrix_objects(session: Session) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    action_request_id = uuid4()
    candidate_id = uuid4()
    source_delta_id = uuid4()
    review_item_id = uuid4()
    job_id = uuid4()
    pack_id = uuid4()
    member_actor_id = uuid4()
    invitation_id = uuid4()
    memory_page_id = uuid4()
    thread_id = "map-origin"
    thread_view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="matrix_open_thread_profile_v1",
        markdown_ref="object://processed/matrix-open-thread.md",
        raw_offset_map_ref="object://processed/matrix-open-thread.offsets.json",
        view_status="current",
    )
    thread_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=thread_view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=42,
        raw_start_offset=0,
        raw_end_offset=42,
        text_preview="Mira asks where the lantern map came from.",
        narration_layer="narrator",
    )

    action_request = AgentActionRequestRecord(
        id=action_request_id,
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="改写这里",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 8},
        },
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    candidate = AgentDraftCandidateRecord(
        id=candidate_id,
        project_id=project.id,
        action_request_id=action_request_id,
        mode="rewrite_span",
        candidate_text_ref="object://candidate/non-member-matrix",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 8},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    source_delta = SourceDeltaRecord(
        id=source_delta_id,
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        delta_kind="replace",
        range_start=0,
        range_end=8,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/non-member-matrix",
        submitted_text_search="米拉推开门。",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "write-permission-matrix"},
        status="memory_writeback_completed",
    )
    review_item = ReviewItemRecord(
        id=review_item_id,
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    job = JobRecord(
        id=job_id,
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="non-member-write-matrix-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(source_delta_id),
        },
    )
    genre_pack = StorySchemaPackRecord(
        id=pack_id,
        project_id=None,
        pack_type="genre",
        pack_name=f"non-member-matrix-{pack_id}",
        version="v1",
        status="active",
        entity_types=[],
        event_types=[],
        relations=[],
        extraction_hints={},
        risk_rules={},
    )
    memory_page = MemoryPage(
        id=memory_page_id,
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": thread_id,
                "update_type": "opens",
                "summary": "Who gave Mira the lantern map?",
                "risk_level": "low",
                "source_delta_id": str(source_delta_id),
                "source_span_ids": [str(thread_span.id)],
                "status": "open",
            }
        ],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(source_delta_id)},
            {"type": "source_span", "id": str(thread_span.id)},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all(
        [
            action_request,
            candidate,
            source_delta,
            review_item,
            job,
            genre_pack,
            thread_view,
            thread_span,
            memory_page,
        ]
    )
    session.commit()
    return {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": action_request_id,
        "candidate_id": candidate_id,
        "context_pack_id": uuid4(),
        "memory_page_id": memory_page_id,
        "thread_id": thread_id,
        "source_delta_id": source_delta_id,
        "review_item_id": review_item_id,
        "job_id": job_id,
        "pack_id": pack_id,
        "member_actor_id": member_actor_id,
        "invitation_id": invitation_id,
        "raw_hash": version.raw_hash,
        "actor_id": actor_id,
    }


def _seed_source_schema_success_matrix_objects(
    session: Session,
    object_store: LocalObjectStore,
) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    base_text = "米拉停在门口等待。"
    base_ref = object_store.put_text(f"raw/source-schema-success-{version.id}.txt", base_text)
    base_hash = sha256(base_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = base_ref
    version.raw_text_ref = base_ref
    version.raw_hash = base_hash
    version.version_label = "v1"
    version.created_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

    pack_id = uuid4()
    session.add(
        StorySchemaPackRecord(
            id=pack_id,
            project_id=None,
            pack_type="genre",
            pack_name=f"success-matrix-genre-{pack_id}",
            version="v1",
            status="active",
            entity_types=[],
            event_types=[],
            relations=[],
            extraction_hints={},
            risk_rules={},
        )
    )
    session.commit()
    return {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "memory_page_id": uuid4(),
        "source_delta_id": uuid4(),
        "review_item_id": uuid4(),
        "job_id": uuid4(),
        "pack_id": pack_id,
        "raw_hash": base_hash,
        "actor_id": actor_id,
    }


def _prepare_source_schema_success_case(
    session: Session,
    object_store: LocalObjectStore,
    route_template: str,
    case_name: str,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    if case_name == "source_version_restore":
        source_id = UUID(str(ids["source_id"]))
        version_id = UUID(str(ids["version_id"]))
        latest_text = "米拉已经推开门。"
        latest_ref = object_store.put_text(
            f"raw/source-schema-success-restore-latest-{version_id}.txt",
            latest_text,
        )
        latest_version = SourceVersion(
            id=uuid4(),
            source_id=source_id,
            version_label="v2",
            raw_hash=sha256(latest_text.encode("utf-8")).hexdigest(),
            raw_text_ref=latest_ref,
            supersedes_version_id=version_id,
        )
        latest_version.created_at = datetime(2026, 1, 1, 9, 1, tzinfo=UTC)
        session.add(latest_version)
        session.commit()
        return payload

    if case_name == "genre_pack_create":
        assert payload is not None
        return {
            **payload,
            "pack_name": f"success-matrix-created-{ids['project_id']}",
        }

    if route_template == "/api/projects/{project_id}/story-schema/project-override":
        assert payload is not None
        return {
            **payload,
            "pack_name": f"project-overrides-{ids['project_id']}",
        }

    return payload


def _assert_source_schema_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    assert after["idempotency_records"] == before["idempotency_records"] + 1
    assert after["audit_events"] == before["audit_events"] + 1

    if case_name == "source_create":
        source = session.get(RawSource, UUID(str(body["source_id"])))
        version = session.get(SourceVersion, UUID(str(body["version_id"])))
        delta = session.get(SourceDeltaRecord, UUID(str(body["source_delta_id"])))
        job = session.get(JobRecord, UUID(str(body["memory_writeback_job_id"])))
        assert source is not None
        assert version is not None
        assert delta is not None
        assert job is not None
        assert object_store.get_text(version.raw_text_ref or "") == "米拉停在门口。"
        assert delta.new_version_id == version.id
        assert delta.status == "memory_writeback_queued"
        assert after["source_raw_sources"] == before["source_raw_sources"] + 1
        assert after["source_versions"] == before["source_versions"] + 1
        assert after["source_deltas"] == before["source_deltas"] + 1
        assert after["job_records"] == before["job_records"] + 2
        return

    if case_name == "source_archive":
        source = session.get(RawSource, UUID(str(ids["source_id"])))
        assert source is not None
        assert source.archived_at is not None
        assert source.archived_by == UUID(str(ids["actor_id"]))
        assert body["status"] == "archived"
        assert after["source_raw_sources"] == before["source_raw_sources"]
        assert after["source_versions"] == before["source_versions"]
        return

    if case_name == "source_version_create":
        version = session.get(SourceVersion, UUID(str(body["version_id"])))
        assert version is not None
        assert version.supersedes_version_id == UUID(str(ids["version_id"]))
        assert object_store.get_text(version.raw_text_ref or "") == "米拉停在门口。"
        assert after["source_versions"] == before["source_versions"] + 1
        assert after["source_deltas"] == before["source_deltas"]
        assert after["job_records"] == before["job_records"]
        return

    if case_name == "source_version_restore":
        restored_version = session.get(SourceVersion, UUID(str(body["new_version_id"])))
        delta = session.get(SourceDeltaRecord, UUID(str(body["source_delta_id"])))
        job = session.get(JobRecord, UUID(str(body["memory_writeback_job_id"])))
        assert restored_version is not None
        assert delta is not None
        assert job is not None
        assert body["restored_from_version_id"] == str(ids["version_id"])
        assert delta.new_version_id == restored_version.id
        assert delta.status == "memory_writeback_queued"
        assert object_store.get_text(restored_version.raw_text_ref or "") == "米拉停在门口等待。"
        assert after["source_versions"] == before["source_versions"] + 1
        assert after["source_deltas"] == before["source_deltas"] + 1
        assert after["job_records"] == before["job_records"] + 2
        return

    if case_name in {"project_source_delta_create", "nested_source_delta_create"}:
        new_version = session.get(SourceVersion, UUID(str(body["new_version_id"])))
        delta = session.get(SourceDeltaRecord, UUID(str(body["source_delta_id"])))
        job = session.get(JobRecord, UUID(str(body["memory_writeback_job_id"])))
        assert new_version is not None
        assert delta is not None
        assert job is not None
        assert delta.previous_version_id == UUID(str(ids["version_id"]))
        assert delta.new_version_id == new_version.id
        assert delta.status == "memory_writeback_queued"
        assert object_store.get_text(delta.submitted_text_ref) == "米拉推开门。"
        assert after["source_versions"] == before["source_versions"] + 1
        assert after["source_deltas"] == before["source_deltas"] + 1
        assert after["job_records"] == before["job_records"] + 2
        return

    if case_name == "genre_pack_create":
        pack = session.get(StorySchemaPackRecord, UUID(str(body["id"])))
        assert pack is not None
        assert pack.pack_type == "genre"
        assert pack.status == "active"
        assert after["story_schema_packs"] == before["story_schema_packs"] + 1
        assert after["project_story_schema_bindings"] == before["project_story_schema_bindings"]
        return

    if case_name == "genre_pack_deprecate":
        pack = session.get(StorySchemaPackRecord, UUID(str(ids["pack_id"])))
        assert pack is not None
        assert pack.status == "deprecated"
        assert body["status"] == "deprecated"
        assert after["story_schema_packs"] == before["story_schema_packs"]
        assert after["project_story_schema_bindings"] == before["project_story_schema_bindings"]
        return

    if case_name == "genre_pack_select":
        binding = (
            session.query(ProjectStorySchemaBinding)
            .filter_by(project_id=UUID(str(ids["project_id"])), status="active")
            .one()
        )
        assert binding.genre_schema_pack_id == UUID(str(ids["pack_id"]))
        assert body["genre_schema_pack_id"] == str(ids["pack_id"])
        assert after["project_story_schema_bindings"] == before["project_story_schema_bindings"] + 1
        assert after["story_schema_packs"] in {
            before["story_schema_packs"],
            before["story_schema_packs"] + 1,
        }
        return

    if case_name == "project_override_upsert":
        binding = (
            session.query(ProjectStorySchemaBinding)
            .filter_by(project_id=UUID(str(ids["project_id"])), status="active")
            .one()
        )
        assert binding.project_override_pack_id == UUID(str(body["project_override_pack_id"]))
        override_pack = session.get(StorySchemaPackRecord, binding.project_override_pack_id)
        assert override_pack is not None
        assert override_pack.project_id == UUID(str(ids["project_id"]))
        assert override_pack.pack_type == "project_override"
        assert after["project_story_schema_bindings"] == before["project_story_schema_bindings"] + 1
        assert after["story_schema_packs"] in {
            before["story_schema_packs"] + 1,
            before["story_schema_packs"] + 2,
        }
        return

    raise AssertionError(f"Missing success side-effect assertions for {case_name}")


def _seed_candidate_success_matrix_objects(
    session: Session,
    object_store: LocalObjectStore,
) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "旧事实占位文本。后续保留。"
    raw_text_ref = object_store.put_text(
        f"raw/candidate-success-{version.id}.txt",
        original_text,
    )
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    version.version_label = "v1"

    action_request_id = uuid4()
    candidate_id = uuid4()
    action_request = AgentActionRequestRecord(
        id=action_request_id,
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续这一段",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 8},
        },
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    candidate = AgentDraftCandidateRecord(
        id=candidate_id,
        project_id=project.id,
        action_request_id=action_request_id,
        mode="rewrite_span",
        candidate_text_ref=object_store.put_text(
            f"candidates/candidate-success-{candidate_id}.txt",
            "候选句。",
        ),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 8},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()
    return {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": action_request_id,
        "candidate_id": candidate_id,
        "context_pack_id": uuid4(),
        "memory_page_id": uuid4(),
        "source_delta_id": uuid4(),
        "review_item_id": uuid4(),
        "job_id": uuid4(),
        "pack_id": uuid4(),
        "raw_hash": raw_hash,
        "actor_id": actor_id,
    }


def test_candidate_detail_filters_invalid_source_span_refs(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="The narrator anchors a candidate in verified context.",
        slug="candidate-detail-valid-source-ref",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Another project has a separate candidate context.",
        slug="candidate-detail-cross-project-source-ref",
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="Revise the selected passage.",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 12},
        },
        constraints={},
        expected_output="draft_candidate",
        status="succeeded",
        created_by=actor_id,
    )
    candidate_id = uuid4()
    candidate_text_ref = object_store.put_text(
        f"candidates/candidate-detail-filter-{candidate_id}.txt",
        "The revised candidate keeps the unresolved context open.",
    )
    candidate = AgentDraftCandidateRecord(
        id=candidate_id,
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_span",
        candidate_text_ref=candidate_text_ref,
        context_pack_id=uuid4(),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        target_scene_id=None,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        evidence_refs=[
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        status="offered_to_author",
    )
    finding = AgentReviewFindingRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        draft_candidate_id=candidate.id,
        risk_level="medium",
        risk_type="control_risk",
        summary="Candidate should stay within the requested local scope.",
        affected_text_ref=candidate_text_ref,
        memory_refs={
            "source_span_ids": [
                str(valid_span.id),
                str(cross_project_span.id),
                "not-a-source-span-id",
            ],
            "candidate_memory_refs": [
                {"type": "source_span", "id": str(valid_span.id)},
                {"type": "source_span", "id": str(cross_project_span.id)},
                {"type": "source_span", "id": "not-a-source-span-id"},
            ],
            "note": "kept",
        },
        storytelling_refs={
            "control": "keep_thread_open",
            "source_span_ids": [
                str(valid_span.id),
                str(cross_project_span.id),
                "not-a-source-span-id",
            ],
            "matched_categories": ["scope_expansion"],
        },
        suggested_revision="Keep the next candidate local.",
        can_offer_to_author=True,
        maps_to_review_type_if_accepted="canon_conflict",
        draft_local_only=True,
    )
    session.add_all([action_request, candidate, finding])
    session.commit()
    client = TestClient(
        create_app(lambda: SqlAlchemyUnitOfWork(session), object_store=object_store)
    )

    response = client.get(
        f"/api/projects/{project.id}/candidates/{candidate.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    expected_refs = [{"type": "source_span", "id": str(valid_span.id)}]
    assert body["memory_refs"] == expected_refs
    assert body["evidence_refs"] == expected_refs
    assert body["agent_review_findings"][0]["memory_refs"] == {
        "source_span_ids": [str(valid_span.id)],
        "candidate_memory_refs": expected_refs,
        "note": "kept",
    }
    assert body["agent_review_findings"][0]["storytelling_refs"] == {
        "control": "keep_thread_open",
        "source_span_ids": [str(valid_span.id)],
        "matched_categories": ["scope_expansion"],
    }
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)


def _prepare_candidate_success_case(
    session: Session,
    case_name: str,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    candidate = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
    assert candidate is not None

    if case_name == "candidate_override_block":
        candidate.status = "blocked"

    session.commit()
    return payload


def _assert_candidate_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    expected_counts = dict(before)
    expected_counts["audit_events"] += 1
    expected_counts["idempotency_records"] += 1

    candidate = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
    assert candidate is not None

    if case_name == "candidate_accept":
        expected_counts["source_accepted_fragments"] += 1
        expected_counts["source_deltas"] += 1
        expected_counts["source_versions"] += 1
        expected_counts["job_records"] += 2
        assert after == expected_counts

        accepted_fragment = session.get(
            AcceptedFragmentRecord,
            UUID(str(body["accepted_fragment_id"])),
        )
        delta = session.get(SourceDeltaRecord, UUID(str(body["source_delta_id"])))
        new_version = session.get(SourceVersion, UUID(str(body["new_version_id"])))
        job = session.get(JobRecord, UUID(str(body["memory_writeback_job_id"])))
        assert accepted_fragment is not None
        assert delta is not None
        assert new_version is not None
        assert job is not None
        assert candidate.status == "converted_to_source_delta"
        assert candidate.author_action == "accept"
        assert candidate.accepted_text_ref == accepted_fragment.accepted_text_ref
        assert object_store.get_text(accepted_fragment.accepted_text_ref) == "米拉推开门。"
        assert delta.accepted_fragment_id == accepted_fragment.id
        assert delta.previous_version_id == UUID(str(ids["version_id"]))
        assert delta.new_version_id == new_version.id
        assert delta.status == "memory_writeback_queued"
        assert object_store.get_text(delta.submitted_text_ref) == "米拉推开门。"
        assert new_version.supersedes_version_id == UUID(str(ids["version_id"]))
        assert object_store.get_text(new_version.raw_text_ref or "") == "米拉推开门。后续保留。"
        assert job.status == "queued"
        return

    if case_name == "candidate_revise":
        expected_counts["agent_draft_candidates"] += 1
        assert after == expected_counts
        replacement_id = UUID(str(body["replacement_candidate_id"]))
        replacement = session.get(AgentDraftCandidateRecord, replacement_id)
        assert replacement is not None
        assert candidate.status == "revised"
        assert candidate.author_action == "revise"
        assert replacement.status == "offered_to_author"
        assert replacement.action_request_id == candidate.action_request_id
        assert replacement.target_source_id == candidate.target_source_id
        assert replacement.target_version_id == candidate.target_version_id
        assert object_store.get_text(replacement.candidate_text_ref) == "米拉轻轻推开门。"
        return

    assert after == expected_counts

    if case_name == "candidate_reject":
        assert body["status"] == "archived"
        assert candidate.status == "archived"
        assert candidate.author_action == "reject"
        assert candidate.accepted_text_ref is None
        return

    if case_name == "candidate_override_block":
        assert body["status"] == "offered_to_author"
        assert body["override_reason"] == "author accepts the explicit risk"
        assert candidate.status == "offered_to_author"
        assert candidate.author_action == "override_block"
        assert candidate.override_reason == "author accepts the explicit risk"
        assert candidate.accepted_text_ref is None
        return

    raise AssertionError(f"Missing candidate success side-effect assertions for {case_name}")


def _seed_memory_context_success_matrix_objects(session: Session) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="success_matrix_profile_v1",
        markdown_ref="object://processed/memory-context-success.md",
        raw_offset_map_ref="object://processed/memory-context-success.offsets.json",
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
        text_preview="Mira owns the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([view, span, fact])
    session.commit()
    return {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "memory_page_id": uuid4(),
        "source_delta_id": uuid4(),
        "review_item_id": uuid4(),
        "job_id": uuid4(),
        "pack_id": uuid4(),
        "raw_hash": version.raw_hash,
        "actor_id": actor_id,
        "source_span_id": span.id,
        "fact_id": fact.id,
    }


def _prepare_memory_context_success_case(
    case_name: str,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    assert payload is not None
    if case_name == "memory_answer":
        return {
            **payload,
            "subject_ref": {"type": "character", "id": "mira", "name": "Mira"},
            "predicate": "owns",
        }
    if case_name == "context_pack_build":
        return payload
    raise AssertionError(f"Missing memory/context success setup case: {case_name}")


def _assert_memory_context_success_side_effects(
    session: Session,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    expected_counts = dict(before)
    expected_counts["audit_events"] += 1
    expected_counts["idempotency_records"] += 1

    if case_name == "memory_answer":
        assert after == expected_counts
        assert body["answer_type"] == "canon"
        assert body["confidence"] == 0.93
        assert body["source_span_refs"] == [
            {"type": "source_span", "id": str(ids["source_span_id"])}
        ]
        assert body["affected_entities"] == [
            {"type": "character", "id": "mira", "name": "Mira"},
            {"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        ]
        assert body["caveats"] == []
        assert body["related_review_items"] == []
        assert body["safe_to_use_in_current_pov"] is True
        assert "owns" in body["answer"]
        return

    if case_name == "context_pack_build":
        expected_counts["agent_context_packs"] += 1
        assert after == expected_counts
        context_pack = session.get(AgentContextPackRecord, UUID(str(body["context_pack_id"])))
        assert context_pack is not None
        assert body["schema_version"] == "writing-context-pack.v1"
        assert body["canonical_context"]["facts"][0]["fact_id"] == str(ids["fact_id"])
        assert body["canonical_context"]["facts"][0]["evidence_span_ids"] == [
            str(ids["source_span_id"])
        ]
        assert {"type": "source_span", "id": str(ids["source_span_id"])} in body["evidence_refs"]
        assert context_pack.current_source_id == UUID(str(ids["source_id"]))
        assert context_pack.current_version_id == UUID(str(ids["version_id"]))
        assert context_pack.payload["canonical_context"]["facts"][0]["fact_id"] == str(
            ids["fact_id"]
        )
        assert context_pack.evidence_refs == body["evidence_refs"]
        return

    raise AssertionError(f"Missing memory/context success side-effect assertions for {case_name}")


def _seed_action_request_success_matrix_objects(
    session: Session,
    object_store: LocalObjectStore,
    case_name: str,
) -> dict[str, UUID | str]:
    ids = _seed_memory_context_success_matrix_objects(session)
    if case_name == "action_request_submit" or case_name.startswith("agent_wrapper_"):
        return ids

    action_request_id = UUID(str(ids["action_request_id"]))
    source_id = UUID(str(ids["source_id"]))
    version_id = UUID(str(ids["version_id"]))
    project_id = UUID(str(ids["project_id"]))
    actor_id = UUID(str(ids["actor_id"]))

    if case_name == "action_request_run_explain_candidate":
        candidate_id = uuid4()
        original_action_request = _action_success_request_record(
            project_id=project_id,
            actor_id=actor_id,
            action_type="rewrite_span",
            expected_output="draft_candidate",
            target=_selected_text_target(ids),
            status="succeeded",
            source_id=source_id,
            source_version_id=version_id,
            actor_intent="把这段写得更克制。",
        )
        candidate_text_ref = object_store.put_text(
            f"candidates/action-success-explain-{candidate_id}.txt",
            "米拉停在门口，没有说出钥匙的来源。",
        )
        candidate = AgentDraftCandidateRecord(
            id=candidate_id,
            project_id=project_id,
            action_request_id=original_action_request.id,
            mode="rewrite_span",
            candidate_text_ref=candidate_text_ref,
            context_pack_id=uuid4(),
            target_source_id=source_id,
            target_version_id=version_id,
            target_scene_id=None,
            affected_range={"start": 0, "end": 8},
            base_hash=str(ids["raw_hash"]),
            memory_refs=[{"type": "source_span", "id": str(ids["source_span_id"])}],
            evidence_refs=[{"type": "source_span", "id": str(ids["source_span_id"])}],
            status="offered_to_author",
        )
        finding = AgentReviewFindingRecord(
            id=uuid4(),
            project_id=project_id,
            action_request_id=original_action_request.id,
            draft_candidate_id=candidate_id,
            risk_level="medium",
            risk_type="canon_risk",
            summary="候选避开了未确认钥匙来源。",
            affected_text_ref=candidate_text_ref,
            memory_refs={"source_span_id": str(ids["source_span_id"])},
            storytelling_refs={"control": "keep_thread_open"},
            suggested_revision="继续保持悬念开放。",
            can_offer_to_author=True,
            maps_to_review_type_if_accepted="canon_conflict",
            draft_local_only=True,
        )
        action_request = _action_success_request_record(
            project_id=project_id,
            actor_id=actor_id,
            action_type="explain_candidate",
            expected_output="candidate_explanation",
            target={"kind": "candidate", "candidate_id": str(candidate_id)},
            action_request_id=action_request_id,
            actor_intent="为什么这个候选合理？",
        )
        session.add_all([original_action_request, candidate, finding, action_request])
        session.commit()
        return {**ids, "candidate_id": candidate_id}

    if case_name == "action_request_run_revise_candidate":
        candidate_id = uuid4()
        original_action_request = _action_success_request_record(
            project_id=project_id,
            actor_id=actor_id,
            action_type="rewrite_span",
            expected_output="draft_candidate",
            target=_selected_text_target(ids),
            status="succeeded",
            source_id=source_id,
            source_version_id=version_id,
            actor_intent="继续这一段。",
        )
        candidate_text_ref = object_store.put_text(
            f"candidates/action-success-revise-{candidate_id}.txt",
            "米拉几乎说出钥匙的来源，又把话咽回去。",
        )
        candidate = AgentDraftCandidateRecord(
            id=candidate_id,
            project_id=project_id,
            action_request_id=original_action_request.id,
            mode="rewrite_span",
            candidate_text_ref=candidate_text_ref,
            context_pack_id=None,
            target_source_id=source_id,
            target_version_id=version_id,
            target_scene_id=None,
            affected_range={"start": 0, "end": 8},
            base_hash=str(ids["raw_hash"]),
            memory_refs=[{"type": "source_span", "id": str(ids["source_span_id"])}],
            evidence_refs=[{"type": "source_span", "id": str(ids["source_span_id"])}],
            status="offered_to_author",
        )
        action_request = _action_success_request_record(
            project_id=project_id,
            actor_id=actor_id,
            action_type="revise_candidate",
            expected_output="draft_candidate",
            target={"kind": "candidate", "candidate_id": str(candidate_id)},
            action_request_id=action_request_id,
            source_id=source_id,
            source_version_id=version_id,
            actor_intent="别关闭钥匙来源这个悬念。",
            constraints={"keep_thread_open": True},
        )
        session.add_all([original_action_request, candidate, action_request])
        session.commit()
        return {**ids, "candidate_id": candidate_id}

    action_type, expected_output, target, constraints, actor_intent = _action_run_success_spec(
        case_name, ids
    )
    session.add(
        _action_success_request_record(
            project_id=project_id,
            actor_id=actor_id,
            action_type=action_type,
            expected_output=expected_output,
            target=target,
            action_request_id=action_request_id,
            source_id=source_id if action_type != "ask_memory" else None,
            source_version_id=version_id if action_type != "ask_memory" else None,
            constraints=constraints,
            actor_intent=actor_intent,
        )
    )
    session.commit()
    return ids


def _action_success_request_record(
    *,
    project_id: UUID,
    actor_id: UUID,
    action_type: str,
    expected_output: str,
    target: dict[str, object] | None,
    action_request_id: UUID | None = None,
    source_id: UUID | None = None,
    source_version_id: UUID | None = None,
    status: str = "submitted",
    constraints: dict[str, object] | None = None,
    actor_intent: str = "继续这一段。",
) -> AgentActionRequestRecord:
    return AgentActionRequestRecord(
        id=action_request_id or uuid4(),
        project_id=project_id,
        source_id=source_id,
        source_version_id=source_version_id,
        scene_id=None,
        chapter_id=None,
        pov_character_id=None,
        actor_intent=actor_intent,
        trigger="selection",
        action_type=action_type,
        target=target,
        constraints=constraints or {},
        expected_output=expected_output,
        status=status,
        created_by=actor_id,
    )


def _action_run_success_spec(
    case_name: str, ids: dict[str, UUID | str]
) -> tuple[str, str, dict[str, object] | None, dict[str, object], str]:
    if case_name == "action_request_run_ask_memory":
        return (
            "ask_memory",
            "memory_answer",
            None,
            {
                "subject_ref": {"type": "character", "id": "mira", "name": "Mira"},
                "predicate": "owns",
            },
            "米拉拥有什么？",
        )
    if case_name == "action_request_run_check_risk":
        return (
            "check_risk",
            "risk_findings",
            _selected_text_target(ids),
            {},
            "这段有没有 POV 穿帮？",
        )
    if case_name == "action_request_run_suggest_next_direction":
        return (
            "suggest_next_direction",
            "beat_candidates",
            _cursor_target(ids),
            {"length": "short"},
            "下面可以发生什么？",
        )
    if case_name == "action_request_run_draft_next_passage":
        return (
            "draft_next_passage",
            "draft_candidate",
            _selected_text_target(ids),
            {},
            "让米拉继续推进这一页，但不要泄露奥林的身份。",
        )
    if case_name == "action_request_run_rewrite_current_page":
        return (
            "rewrite_current_page",
            "draft_candidate",
            _selected_text_target(ids),
            {"tone": "克制"},
            "重写这一页，保留钥匙来源悬念。",
        )
    raise AssertionError(f"Missing ActionRequest run success setup case: {case_name}")


def _selected_text_target(ids: dict[str, UUID | str]) -> dict[str, object]:
    return {
        "kind": "selected_text",
        "source_id": str(ids["source_id"]),
        "source_version_id": str(ids["version_id"]),
        "range": {"start": 0, "end": 8},
    }


def _cursor_target(ids: dict[str, UUID | str]) -> dict[str, object]:
    return {
        "kind": "cursor_position",
        "source_id": str(ids["source_id"]),
        "source_version_id": str(ids["version_id"]),
        "range": {"start": 8, "end": 8},
    }


def _prepare_action_request_success_case(
    case_name: str,
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    assert payload is not None
    if case_name in {"action_request_run_ask_memory", "action_request_run_explain_candidate"}:
        return {**payload, "current_text_window": ""}
    if case_name in {"action_request_run_check_risk", "agent_wrapper_check_risk"}:
        return {
            **payload,
            "actor_intent": "检查这一段是否把风险上下文写成事实。",
            "current_text_window": "这句写成 risk-context 已经坐实了秘密。",
        }
    if case_name == "action_request_run_revise_candidate":
        return {**payload, "current_text_window": "作者要求保留钥匙来源悬念。"}
    if case_name == "agent_wrapper_suggest_next_beat":
        return {
            **payload,
            "actor_intent": "下一拍可以发生什么？",
            "current_text_window": "米拉停在西档案室门口。",
        }
    return {**payload, "current_text_window": "米拉停在西档案室门口。"}


def _assert_action_request_success_side_effects(
    session: Session,
    object_store: LocalObjectStore,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    expected_counts = dict(before)
    expected_counts["audit_events"] += 1
    expected_counts["idempotency_records"] += 1

    if case_name == "action_request_submit":
        expected_counts["agent_action_requests"] += 1
        assert after == expected_counts
        action_request = session.get(AgentActionRequestRecord, UUID(str(body["action_request_id"])))
        assert action_request is not None
        assert body["status"] == "submitted"
        assert action_request.status == "submitted"
        assert action_request.action_type == "rewrite_span"
        assert action_request.expected_output == "draft_candidate"
        return

    if case_name.startswith("agent_wrapper_"):
        expected_counts["agent_action_requests"] += 1
        expected_counts["audit_events"] += 1
        expected_counts["idempotency_records"] += 1

    if case_name in {
        "action_request_run_draft_next_passage",
        "action_request_run_rewrite_current_page",
        "action_request_run_revise_candidate",
        "agent_wrapper_draft_next_passage",
        "agent_wrapper_rewrite_current_page",
    }:
        expected_counts["agent_context_packs"] += 1
        expected_counts["agent_storytelling_controls"] += 5
        expected_counts["agent_draft_candidates"] += 1
        expected_counts["skill_runs"] += 1
    elif case_name in {
        "action_request_run_suggest_next_direction",
        "agent_wrapper_suggest_next_beat",
    }:
        expected_counts["agent_context_packs"] += 1
        expected_counts["agent_storytelling_controls"] += 5
        expected_counts["agent_beat_candidates"] += 1
    elif case_name in {"action_request_run_check_risk", "agent_wrapper_check_risk"}:
        expected_counts["agent_review_findings"] += 1

    assert after == expected_counts

    action_request = session.get(AgentActionRequestRecord, UUID(str(body["action_request_id"])))
    assert action_request is not None
    assert body["status"] == "succeeded"
    assert action_request.status == "succeeded"

    if case_name == "action_request_run_ask_memory":
        assert body["output_type"] == "memory_answer"
        assert body["memory_answer"]["answer_type"] == "canon"
        assert body["memory_answer"]["confidence"] == 0.93
        assert body["memory_answer"]["source_span_refs"] == [
            {"type": "source_span", "id": str(ids["source_span_id"])}
        ]
        assert body["memory_answer"]["affected_entities"] == [
            {"type": "character", "id": "mira", "name": "Mira"},
            {"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        ]
        assert body["memory_answer"]["caveats"] == []
        assert body["draft_candidate_ids"] == []
        assert body["risk_finding_ids"] == []
        assert body["beat_candidate_ids"] == []
        return

    if case_name in {"action_request_run_check_risk", "agent_wrapper_check_risk"}:
        assert body["output_type"] == "risk_findings"
        assert len(body["risk_finding_ids"]) == 1
        finding = session.get(AgentReviewFindingRecord, UUID(str(body["risk_finding_ids"][0])))
        assert finding is not None
        assert finding.action_request_id == action_request.id
        assert finding.draft_candidate_id is None
        assert finding.draft_local_only is True
        assert body["draft_candidate_ids"] == []
        assert body["beat_candidate_ids"] == []
        return

    if case_name in {
        "action_request_run_suggest_next_direction",
        "agent_wrapper_suggest_next_beat",
    }:
        assert body["output_type"] == "beat_candidates"
        assert body["context_pack_id"] is not None
        assert len(body["beat_candidate_ids"]) == 1
        beat = session.get(AgentBeatCandidateRecord, UUID(str(body["beat_candidate_ids"][0])))
        assert beat is not None
        assert beat.action_request_id == action_request.id
        assert body["draft_candidate_ids"] == []
        assert body["risk_finding_ids"] == []
        return

    if case_name == "action_request_run_explain_candidate":
        assert body["output_type"] == "candidate_explanation"
        assert body["candidate_explanation"]["candidate_id"] == str(ids["candidate_id"])
        assert body["draft_candidate_ids"] == []
        assert body["risk_finding_ids"] == []
        assert body["beat_candidate_ids"] == []
        return

    if case_name in {
        "action_request_run_draft_next_passage",
        "action_request_run_rewrite_current_page",
        "action_request_run_revise_candidate",
        "agent_wrapper_draft_next_passage",
        "agent_wrapper_rewrite_current_page",
    }:
        assert body["output_type"] == "draft_candidates"
        assert body["context_pack_id"] is not None
        assert len(body["draft_candidate_ids"]) == 1
        candidate = session.get(
            AgentDraftCandidateRecord, UUID(str(body["draft_candidate_ids"][0]))
        )
        assert candidate is not None
        assert candidate.action_request_id == action_request.id
        assert object_store.get_text(candidate.candidate_text_ref)
        assert body["risk_finding_ids"] == []
        assert body["beat_candidate_ids"] == []
        if case_name == "action_request_run_revise_candidate":
            original = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
            assert original is not None
            assert original.status == "revised"
            assert original.author_action == "revise"
        return

    raise AssertionError(f"Missing ActionRequest success side-effect assertions for {case_name}")


def _seed_memory_writeback_success_matrix_objects(
    session: Session,
    case_name: str,
) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref=f"object://source-deltas/{case_name}.txt",
        submitted_text_search="Mira owns the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "success-matrix"},
        status="memory_writeback_completed",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile=f"{case_name}_profile_v1",
        markdown_ref=f"object://processed/{case_name}.md",
        raw_offset_map_ref=f"object://processed/{case_name}.offsets.json",
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
        end_offset=27,
        raw_start_offset=0,
        raw_end_offset=27,
        text_preview="Mira owns the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="disputed" if case_name == "memory_writeback_decision_fact_accept" else "canon",
        promotion_decision_id=None
        if case_name == "memory_writeback_decision_fact_accept"
        else uuid4(),
        evidence_span_ids=[str(span.id)],
        confidence=0.8,
        source_scope="user_draft",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="canon_conflict"
        if case_name == "memory_writeback_decision_fact_accept"
        else "knowledge_conflict",
        severity="medium",
        status="open",
        summary="Lantern-map ownership needs author review.",
        affected_refs={"fact_id": str(fact.id)}
        if case_name == "memory_writeback_decision_fact_accept"
        else {},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}, {"resolution": "reject"}],
        default_action="ask_author",
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
                    "predicate": fact.predicate,
                    "object_ref": fact.object_ref,
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(source_delta.id)},
            {"type": "source_span", "id": str(span.id)},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash=f"{case_name}-hash",
        created_edge_count=1,
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(fact.id)},
        subject_ref=fact.subject_ref,
        relation="owns",
        target_ref=fact.object_ref,
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id=f"req-{case_name}-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )

    records: list[object] = [source_delta, view, span, fact, review_item, evidence, audit]
    if case_name != "memory_writeback_decision_fact_accept":
        records.extend([page, run, edge])
    session.add_all(records)
    session.commit()
    ids = {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "memory_page_id": page.id,
        "source_delta_id": source_delta.id,
        "review_item_id": review_item.id,
        "job_id": uuid4(),
        "pack_id": uuid4(),
        "raw_hash": version.raw_hash,
        "actor_id": actor_id,
        "source_span_id": span.id,
        "fact_id": fact.id,
        "evidence_log_entry_id": evidence.id,
        "graph_edge_id": edge.id,
    }
    return ids


def _prepare_memory_writeback_success_case(
    case_name: str,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
) -> dict[str, object]:
    assert payload is not None
    item_ref_by_case = {
        "memory_writeback_decision_evidence_log_reject": {
            "type": "evidence_log_entry",
            "id": str(ids["evidence_log_entry_id"]),
        },
        "memory_writeback_decision_fact_accept": {
            "type": "fact_assertion",
            "id": str(ids["fact_id"]),
        },
        "memory_writeback_decision_fact_correct": {
            "type": "fact_assertion",
            "id": str(ids["fact_id"]),
        },
        "memory_writeback_decision_fact_reject": {
            "type": "fact_assertion",
            "id": str(ids["fact_id"]),
        },
        "memory_writeback_decision_graph_edge_reject": {
            "type": "graph_edge",
            "id": str(ids["graph_edge_id"]),
        },
        "memory_writeback_decision_memory_page_reject": {
            "type": "memory_page",
            "id": str(ids["memory_page_id"]),
        },
        "memory_writeback_decision_review_item_accept": {
            "type": "review_item",
            "id": str(ids["review_item_id"]),
        },
        "memory_writeback_decision_review_item_reject": {
            "type": "review_item",
            "id": str(ids["review_item_id"]),
        },
        "memory_writeback_decision_source_span_reject": {
            "type": "source_span",
            "id": str(ids["source_span_id"]),
        },
    }
    if case_name not in item_ref_by_case:
        raise AssertionError(f"Missing MemoryWriteback success setup case: {case_name}")

    decision = "accept" if case_name.endswith("_accept") else "reject"
    next_payload = {
        **payload,
        "item_ref": item_ref_by_case[case_name],
        "decision": decision,
        "author_note": "作者确认这条回写预览的处理方式。",
    }
    if case_name == "memory_writeback_decision_fact_correct":
        next_payload["decision"] = "correct"
        next_payload["correction"] = {"predicate": "carries"}
        next_payload["replacement_refs"] = [
            {"type": "source_delta", "id": str(ids["source_delta_id"])}
        ]
    return next_payload


def _assert_memory_writeback_success_side_effects(
    session: Session,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    expected_counts = dict(before)
    expected_counts["audit_events"] += 1
    expected_counts["idempotency_records"] += 1
    expected_counts["memory_writeback_decisions"] += 1

    if case_name == "memory_writeback_decision_fact_accept":
        expected_counts["memory_pages"] += 1
        expected_counts["memory_graph_projection_runs"] += 1
        expected_counts["memory_graph_projection_edges"] += 1
        expected_counts["context_pack_readiness"] += 1
    elif case_name == "memory_writeback_decision_review_item_accept":
        pass
    elif case_name == "memory_writeback_decision_review_item_reject":
        expected_counts["context_pack_readiness"] += 1
    else:
        expected_counts["job_records"] += 1
        expected_counts["context_pack_readiness"] += 1

    assert after == expected_counts
    assert body["status"] == "recorded"
    assert body["source_delta_id"] == str(ids["source_delta_id"])
    decision = session.get(MemoryWritebackDecisionRecord, UUID(str(body["decision_id"])))
    assert decision is not None
    assert decision.source_delta_id == UUID(str(ids["source_delta_id"]))
    assert decision.item_ref == body["item_ref"]

    side_effects = body["side_effects"]

    if case_name == "memory_writeback_decision_fact_accept":
        fact = session.get(FactAssertionRecord, UUID(str(ids["fact_id"])))
        review = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
        assert fact is not None
        assert review is not None
        assert fact.fact_status == "canon"
        assert fact.promotion_decision_id is not None
        assert review.status == "resolved"
        assert review.resolution == "accept"
        assert side_effects["fact_assertion_status"] == "canon"
        assert side_effects["memory_pages"] == "updated"
        assert side_effects["memory_pages_updated"] == 1
        assert side_effects["graph_projection"] == "rebuilt"
        assert side_effects["graph_edges_created"] == 1
        assert side_effects["review_items_resolved"] == 1
        _assert_writeback_readiness_marked(session, ids, side_effects)
        return

    if case_name == "memory_writeback_decision_review_item_accept":
        review = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
        assert review is not None
        assert review.status == "open"
        assert side_effects["policy_action"] == "review_item_retained"
        assert side_effects["memory_pages"] == "unchanged"
        assert side_effects["graph_projection"] == "unchanged"
        return

    if case_name == "memory_writeback_decision_review_item_reject":
        review = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
        assert review is not None
        assert review.status == "dismissed"
        assert review.resolved_by == UUID(str(ids["actor_id"]))
        assert side_effects["policy_action"] == "review_item_dismissed"
        assert side_effects["memory_pages"] == "unchanged"
        assert side_effects["graph_projection"] == "unchanged"
        _assert_writeback_readiness_marked(session, ids, side_effects)
        return

    if case_name == "memory_writeback_decision_memory_page_reject":
        page = session.get(MemoryPage, UUID(str(ids["memory_page_id"])))
        assert page is not None
        assert page.canon_status == "stale"
        assert side_effects["memory_pages"] == "marked_stale"
        assert side_effects["memory_pages_marked_stale"] == 1
        _assert_rewrite_job(session, side_effects, ids)
        _assert_writeback_readiness_marked(session, ids, side_effects)
        return

    fact = session.get(FactAssertionRecord, UUID(str(ids["fact_id"])))
    page = session.get(MemoryPage, UUID(str(ids["memory_page_id"])))
    edge = session.get(GraphProjectionEdge, UUID(str(ids["graph_edge_id"])))
    assert fact is not None
    assert page is not None
    assert edge is not None
    assert fact.fact_status == "disputed"
    assert page.canon_status == "stale"
    assert edge.edge_status == "disputed"
    assert side_effects["fact_assertions_marked_disputed"] == 1
    assert side_effects["memory_pages"] == "marked_stale"
    assert side_effects["memory_pages_marked_stale"] == 1
    assert side_effects["graph_edges_marked_disputed"] == 1
    _assert_rewrite_job(session, side_effects, ids)
    _assert_writeback_readiness_marked(session, ids, side_effects)

    if case_name == "memory_writeback_decision_source_span_reject":
        evidence = session.get(EvidenceLogEntry, UUID(str(ids["evidence_log_entry_id"])))
        assert evidence is not None
        assert evidence.log_status == "disputed"
        assert side_effects["source_span_status"] == "retained"
        assert side_effects["evidence_log_entries_marked_disputed"] == 1
    elif case_name == "memory_writeback_decision_evidence_log_reject":
        evidence = session.get(EvidenceLogEntry, UUID(str(ids["evidence_log_entry_id"])))
        assert evidence is not None
        assert evidence.log_status == "disputed"
        assert side_effects["evidence_log_status"] == "disputed"
        assert side_effects["evidence_log_entries_marked_disputed"] == 1
    elif case_name == "memory_writeback_decision_graph_edge_reject":
        assert side_effects["graph_edge_status"] == "disputed"
    elif case_name == "memory_writeback_decision_fact_correct":
        assert side_effects["fact_assertion_status"] == "disputed"
        assert decision.correction == {"predicate": "carries"}
        assert decision.replacement_refs == [
            {"type": "source_delta", "id": str(ids["source_delta_id"])}
        ]
    elif case_name == "memory_writeback_decision_fact_reject":
        assert side_effects["fact_assertion_status"] == "disputed"
    else:
        raise AssertionError(f"Missing MemoryWriteback success assertions for {case_name}")


def _assert_rewrite_job(
    session: Session,
    side_effects: dict[str, object],
    ids: dict[str, UUID | str],
) -> None:
    rewrite_job_ids = side_effects["memory_page_rewrite_job_ids"]
    assert isinstance(rewrite_job_ids, list)
    assert len(rewrite_job_ids) == 1
    rewrite_job = session.get(JobRecord, UUID(str(rewrite_job_ids[0])))
    assert rewrite_job is not None
    assert rewrite_job.job_type == "rewrite_memory_page"
    assert rewrite_job.status == "queued"
    assert rewrite_job.payload["source_delta_id"] == str(ids["source_delta_id"])


def _assert_writeback_readiness_marked(
    session: Session,
    ids: dict[str, UUID | str],
    side_effects: dict[str, object],
) -> None:
    assert side_effects["context_pack_readiness"] == "marked_stale"
    assert side_effects["context_pack_readiness_marked"] == 1
    readiness = (
        session.query(ContextPackReadinessRecord)
        .filter_by(
            project_id=UUID(str(ids["project_id"])),
            source_span_id=UUID(str(ids["source_span_id"])),
            reason="review_dependency_changed",
        )
        .one()
    )
    assert readiness.status == "stale"
    assert readiness.source_delta_id == UUID(str(ids["source_delta_id"]))
    assert readiness.evidence_refs == [{"type": "source_span", "id": str(ids["source_span_id"])}]


def _seed_job_review_success_matrix_objects(session: Session) -> dict[str, UUID | str]:
    project, raw_source, version, actor_id = seed_source(session)
    source_delta_id = uuid4()
    review_item_id = uuid4()
    job_id = uuid4()
    source_delta = SourceDeltaRecord(
        id=source_delta_id,
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=8,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/job-review-success-matrix",
        submitted_text_search="米拉推开门。",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "job-review-success-matrix"},
        status="memory_writeback_completed",
    )
    job = JobRecord(
        id=job_id,
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key=f"job-review-success-{job_id}",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(source_delta_id),
        },
    )
    review_item = ReviewItemRecord(
        id=review_item_id,
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={},
        new_evidence={"source_span_ids": []},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="ask_author",
    )
    session.add_all([source_delta, job, review_item])
    session.commit()
    return {
        "project_id": project.id,
        "source_id": raw_source.id,
        "version_id": version.id,
        "base_version_id": version.id,
        "compare_version_id": uuid4(),
        "action_request_id": uuid4(),
        "candidate_id": uuid4(),
        "context_pack_id": uuid4(),
        "memory_page_id": uuid4(),
        "source_delta_id": source_delta_id,
        "review_item_id": review_item_id,
        "job_id": job_id,
        "pack_id": uuid4(),
        "raw_hash": version.raw_hash,
        "actor_id": actor_id,
    }


def _prepare_job_review_success_case(
    session: Session,
    case_name: str,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
) -> dict[str, object] | None:
    job = session.get(JobRecord, UUID(str(ids["job_id"])))
    review_item = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
    assert job is not None
    assert review_item is not None

    if case_name == "job_retry":
        job.status = "failed_retryable"
        job.attempt_count = 2
        job.run_after = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)
        job.locked_by = "worker-old"
        job.locked_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        job.last_error = "provider timeout"
    elif case_name == "review_reopen":
        review_item.status = "dismissed"
        review_item.resolution = "accepted_as_change"
        review_item.resolved_by = UUID(str(ids["actor_id"]))
        review_item.resolved_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
        review_item.side_effects = {"author_note": "previous dismissal"}

    session.commit()
    return payload


def _assert_job_review_success_side_effects(
    session: Session,
    case_name: str,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    after = _permission_matrix_side_effect_counts(session)
    expected_counts = dict(before)
    expected_counts["audit_events"] += 1
    expected_counts["idempotency_records"] += 1
    assert after == expected_counts

    job = session.get(JobRecord, UUID(str(ids["job_id"])))
    review_item = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
    assert job is not None
    assert review_item is not None

    if case_name == "job_cancel":
        assert body["status"] == "cancelled"
        assert job.status == "cancelled"
        assert job.run_after is None
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.last_error is None
        return

    if case_name == "job_retry":
        assert body["status"] == "queued"
        assert job.status == "queued"
        assert job.attempt_count == 2
        assert job.run_after is None
        assert job.locked_by is None
        assert job.locked_at is None
        assert job.last_error is None
        return

    if case_name == "review_dismiss":
        assert body["status"] == "dismissed"
        assert review_item.status == "dismissed"
        assert review_item.resolution is None
        assert review_item.resolved_by == UUID(str(ids["actor_id"]))
        assert review_item.resolved_at is not None
        assert review_item.side_effects["promotion"] == "none"
        assert review_item.side_effects["memory_pages"] == "unchanged"
        assert review_item.side_effects["graph_projection"] == "unchanged"
        assert review_item.side_effects["author_note"] == "dismiss test"
        return

    if case_name == "review_reopen":
        assert body["status"] == "open"
        assert review_item.status == "open"
        assert review_item.resolution is None
        assert review_item.resolved_by is None
        assert review_item.resolved_at is None
        assert review_item.side_effects["review_queue"] == "open"
        assert review_item.side_effects["memory_pages"] == "unchanged"
        assert review_item.side_effects["graph_projection"] == "unchanged"
        assert review_item.side_effects["author_note"] == "reopen test"
        return

    if case_name == "review_resolve":
        assert body["status"] == "resolved"
        assert body["resolution"] == "accepted_as_change"
        assert review_item.status == "resolved"
        assert review_item.resolution == "accepted_as_change"
        assert review_item.resolved_by == UUID(str(ids["actor_id"]))
        assert review_item.resolved_at is not None
        assert review_item.side_effects["memory_pages"] == "unchanged"
        assert review_item.side_effects["memory_pages_marked_stale"] == 0
        assert review_item.side_effects["graph_projection"] == "unchanged"
        assert review_item.side_effects["graph_edges_marked_stale"] == 0
        assert review_item.side_effects["replacement_refs"] == [
            {"type": "source_delta", "id": str(ids["source_delta_id"])}
        ]
        assert review_item.side_effects["author_note"] == "resolved by source edit"
        return

    raise AssertionError(f"Missing job/review success side-effect assertions for {case_name}")


def _seed_idempotency_conflict_records(
    session: Session,
    ids: dict[str, UUID | str],
) -> None:
    actor_id = UUID(str(ids["actor_id"]))
    project_id = UUID(str(ids["project_id"]))
    records = [
        IdempotencyRecord(
            id=uuid4(),
            project_id=project_id,
            actor_id=actor_id,
            operation=operation,
            idempotency_key=_idempotency_conflict_key(index),
            request_hash=f"different-request-hash-{index}",
            response_payload={"status": "seeded_conflict"},
        )
        for index, (_route, operation) in enumerate(
            sorted(WRITE_IDEMPOTENCY_CONFLICT_OPERATION_BY_ROUTE.items())
        )
    ]
    session.add_all(records)
    session.commit()


def _idempotency_conflict_key(index: int) -> str:
    return f"idem-conflict-matrix-{index}"


def _idempotency_replay_key(index: int) -> str:
    return f"idem-replay-matrix-{index}"


def _seed_idempotency_replay_records(
    session: Session,
    route_template: str,
    ids: dict[str, UUID | str],
    *,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, object] | None,
) -> dict[str, object]:
    records, expected_response = _idempotency_replay_records(
        route_template,
        ids,
        request_id=request_id,
        idempotency_key=idempotency_key,
        payload=payload or {},
    )
    session.add_all(
        [
            IdempotencyRecord(
                id=uuid4(),
                project_id=UUID(str(ids["project_id"])),
                actor_id=UUID(str(ids["actor_id"])),
                operation=operation,
                idempotency_key=idempotency_key,
                request_hash=_idempotency_request_hash(input_data),
                response_payload=response_payload,
            )
            for operation, input_data, response_payload in records
        ]
    )
    session.commit()
    return expected_response


def _idempotency_replay_records(
    route_template: str,
    ids: dict[str, UUID | str],
    *,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, object],
) -> tuple[list[tuple[str, object, dict[str, object]]], dict[str, object]]:
    project_id = UUID(str(ids["project_id"]))
    actor_id = UUID(str(ids["actor_id"]))
    source_id = UUID(str(ids["source_id"]))
    version_id = UUID(str(ids["version_id"]))
    action_request_id = UUID(str(ids["action_request_id"]))
    candidate_id = UUID(str(ids["candidate_id"]))
    source_delta_id = UUID(str(ids["source_delta_id"]))
    review_item_id = UUID(str(ids["review_item_id"]))
    job_id = UUID(str(ids["job_id"]))
    pack_id = UUID(str(ids["pack_id"]))
    memory_page_id = UUID(str(ids["memory_page_id"]))
    thread_id = str(ids["thread_id"])
    member_actor_id = UUID(str(ids["member_actor_id"]))
    invitation_id = UUID(str(ids["invitation_id"]))

    if route_template == "/api/projects/{project_id}/action-requests":
        output_id = uuid4()
        return [
            (
                "submit_action_request",
                _submit_action_input(project_id, actor_id, request_id, idempotency_key, payload),
                {"action_request_id": str(output_id), "status": "submitted"},
            )
        ], {"action_request_id": str(output_id), "status": "submitted"}

    if route_template == "/api/projects/{project_id}/action-requests/{action_request_id}/run":
        run_payload = _action_run_payload(action_request_id, output_type="draft_candidates")
        return [
            (
                "action_request.run",
                RunActionRequestInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=action_request_id,
                    current_text_window=str(payload["current_text_window"]),
                ),
                run_payload,
            )
        ], {
            "action_request_id": str(action_request_id),
            "status": "succeeded",
            "output_type": "draft_candidates",
        }

    agent_route_specs = {
        "/api/projects/{project_id}/agent/check-risk": ("check_risk", "risk_findings"),
        "/api/projects/{project_id}/agent/draft-next-passage": (
            "draft_next_passage",
            "draft_candidates",
        ),
        "/api/projects/{project_id}/agent/rewrite-current-page": (
            "rewrite_current_page",
            "draft_candidates",
        ),
        "/api/projects/{project_id}/agent/suggest-next-beat": (
            "suggest_next_direction",
            "beat_candidates",
        ),
    }
    if route_template in agent_route_specs:
        action_type, output_type = agent_route_specs[route_template]
        submitted_id = uuid4()
        return [
            (
                "submit_action_request",
                _submit_agent_action_input(
                    project_id,
                    actor_id,
                    request_id,
                    idempotency_key,
                    payload,
                    action_type=action_type,
                    expected_output=output_type,
                ),
                {"action_request_id": str(submitted_id), "status": "submitted"},
            ),
            (
                "action_request.run",
                RunActionRequestInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=submitted_id,
                    current_text_window=str(payload["current_text_window"]),
                ),
                _action_run_payload(submitted_id, output_type=output_type),
            ),
        ], {
            "action_request_id": str(submitted_id),
            "status": "succeeded",
            "output_type": output_type,
        }

    if route_template == "/api/projects/{project_id}/candidates/{candidate_id}/accept":
        accepted_fragment_id = uuid4()
        new_delta_id = uuid4()
        new_version_id = uuid4()
        job_output_id = uuid4()
        return [
            (
                "accept_candidate",
                AcceptCandidateInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    candidate_id=candidate_id,
                    accepted_text_ref=None,
                    accepted_text=str(payload["accepted_text"]),
                    accept_mode=str(payload["accept_mode"]),
                    target_source_id=UUID(str(payload["target_source_id"])),
                    target_version_id=UUID(str(payload["target_version_id"])),
                    insert_or_replace_range=dict(payload["insert_or_replace_range"]),
                    source_type=str(payload["source_type"]),
                    source_scope=str(payload["source_scope"]),
                    author_edited=bool(payload["author_edited"]),
                    base_hash=str(payload["base_hash"]),
                ),
                {
                    "accepted_fragment_id": str(accepted_fragment_id),
                    "source_delta_id": str(new_delta_id),
                    "new_version_id": str(new_version_id),
                    "memory_writeback_job_id": str(job_output_id),
                },
            )
        ], {
            "accepted_fragment_id": str(accepted_fragment_id),
            "source_delta_id": str(new_delta_id),
        }

    if route_template == "/api/projects/{project_id}/members/{member_actor_id}":
        membership_id = uuid4()
        member_payload = {
            "id": str(membership_id),
            "project_id": str(project_id),
            "actor_id": str(member_actor_id),
            "role": str(payload["role"]),
            "status": "active",
            "created_at": "2026-01-01T09:00:00+00:00",
        }
        return [
            (
                "project_member.upsert",
                UpsertProjectMemberInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    member_actor_id=member_actor_id,
                    role=str(payload["role"]),
                ),
                {"member": member_payload, "status": "active"},
            )
        ], {"status": "active"}

    if route_template == "/api/projects/{project_id}/members/{member_actor_id}/revoke":
        membership_id = uuid4()
        member_payload = {
            "id": str(membership_id),
            "project_id": str(project_id),
            "actor_id": str(member_actor_id),
            "role": "viewer",
            "status": "revoked",
            "created_at": "2026-01-01T09:00:00+00:00",
        }
        return [
            (
                "project_member.revoke",
                RevokeProjectMemberInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    member_actor_id=member_actor_id,
                ),
                {"member": member_payload, "status": "revoked"},
            )
        ], {"status": "revoked"}

    if route_template == "/api/projects/{project_id}/invitations":
        invitation_id = uuid4()
        invitation_payload = {
            "id": str(invitation_id),
            "project_id": str(project_id),
            "member_actor_id": str(payload["member_actor_id"]),
            "role": str(payload["role"]),
            "delivery_provider_ref": str(payload["delivery_provider_ref"]),
            "delivery_target_ref": str(payload["delivery_target_ref"]),
            "token_issuer_ref": payload.get("token_issuer_ref"),
            "status": "pending_external_delivery",
            "delivery_status": "not_sent",
            "token_status": "not_issued",
            "created_at": "2026-01-01T09:00:00+00:00",
        }
        return [
            (
                "project_invitation.create",
                CreateProjectInvitationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    member_actor_id=UUID(str(payload["member_actor_id"])),
                    role=str(payload["role"]),
                    delivery_provider_ref=str(payload["delivery_provider_ref"]),
                    delivery_target_ref=str(payload["delivery_target_ref"]),
                    token_issuer_ref=(
                        str(payload["token_issuer_ref"])
                        if payload.get("token_issuer_ref")
                        else None
                    ),
                ),
                invitation_payload,
            )
        ], {"status": "pending_external_delivery"}

    if route_template == "/api/projects/{project_id}/invitations/{invitation_id}/external-proof":
        invitation_payload = {
            "id": str(invitation_id),
            "project_id": str(project_id),
            "member_actor_id": str(ids["member_actor_id"]),
            "role": "viewer",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/matrix-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
            "delivery_proof_ref": str(payload["delivery_proof_ref"]),
            "token_proof_ref": payload.get("token_proof_ref"),
            "status": "external_delivery_recorded",
            "delivery_status": "sent",
            "token_status": "issued",
            "delivered_at": "2026-01-01T09:00:00+00:00",
            "token_issued_at": "2026-01-01T09:00:00+00:00",
            "created_at": "2026-01-01T08:00:00+00:00",
        }
        return [
            (
                "project_invitation.external_proof",
                RecordProjectInvitationExternalProofInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    invitation_id=invitation_id,
                    delivery_proof_ref=str(payload["delivery_proof_ref"]),
                    token_proof_ref=(
                        str(payload["token_proof_ref"]) if payload.get("token_proof_ref") else None
                    ),
                ),
                invitation_payload,
            )
        ], {"status": "external_delivery_recorded"}

    if route_template == "/api/projects/{project_id}/candidates/{candidate_id}/override-block":
        return [
            (
                "candidate.override_block",
                CandidateOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    candidate_id=candidate_id,
                    operation="override_block",
                    override_reason=str(payload["override_reason"]),
                ),
                {
                    "candidate_id": str(candidate_id),
                    "status": "offered_to_author",
                    "replacement_candidate_id": None,
                    "override_reason": str(payload["override_reason"]),
                },
            )
        ], {"candidate_id": str(candidate_id), "status": "offered_to_author"}

    if route_template == "/api/projects/{project_id}/candidates/{candidate_id}/reject":
        return [
            (
                "candidate.reject",
                CandidateOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    candidate_id=candidate_id,
                    operation="reject",
                    author_note=str(payload["author_note"]),
                ),
                {
                    "candidate_id": str(candidate_id),
                    "status": "archived",
                    "replacement_candidate_id": None,
                    "override_reason": None,
                },
            )
        ], {"candidate_id": str(candidate_id), "status": "archived"}

    if route_template == "/api/projects/{project_id}/candidates/{candidate_id}/revise":
        replacement_id = uuid4()
        return [
            (
                "candidate.revise",
                CandidateOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    candidate_id=candidate_id,
                    operation="revise",
                    author_note=str(payload["author_note"]),
                    revised_text=str(payload["revised_text"]),
                ),
                {
                    "candidate_id": str(candidate_id),
                    "status": "revised",
                    "replacement_candidate_id": str(replacement_id),
                    "override_reason": None,
                },
            )
        ], {
            "candidate_id": str(candidate_id),
            "status": "revised",
            "replacement_candidate_id": str(replacement_id),
        }

    if route_template == "/api/projects/{project_id}/context-packs/build":
        context_pack_id = uuid4()
        return [
            (
                "context_pack.build",
                BuildWritingContextPackInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=None,
                    current_source_id=UUID(str(payload["current_source_id"])),
                    current_version_id=UUID(str(payload["current_version_id"])),
                    current_scene_id=None,
                    current_pov_character_id=None,
                    mode=str(payload["mode"]),
                    current_text_window=str(payload["current_text_window"]),
                    constraints={},
                ),
                _context_pack_payload(context_pack_id),
            )
        ], {"context_pack_id": str(context_pack_id)}

    if route_template == "/api/projects/{project_id}/jobs/{job_id}/cancel":
        return [
            (
                "job.cancel",
                JobOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    job_id=job_id,
                    operation="cancel",
                    author_note=str(payload["author_note"]),
                ),
                _job_detail_payload(job_id, status="cancelled"),
            )
        ], {"id": str(job_id), "status": "cancelled"}

    if route_template == "/api/projects/{project_id}/jobs/{job_id}/retry":
        return [
            (
                "job.retry",
                JobOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    job_id=job_id,
                    operation="retry",
                    author_note=str(payload["author_note"]),
                ),
                _job_detail_payload(job_id, status="queued"),
            )
        ], {"id": str(job_id), "status": "queued"}

    if route_template == "/api/projects/{project_id}/memory/answer":
        answer_payload = {
            "question": str(payload["question"]),
            "answer": "No durable memory answer was needed for replay.",
            "answer_type": "unknown",
            "confidence": 0.0,
            "source_span_refs": [],
            "affected_entities": [],
            "caveats": ["replay-seeded"],
            "unknowns": ["replay-seeded"],
            "related_review_items": [],
            "safe_to_use_in_current_pov": True,
        }
        return [
            (
                "memory.answer",
                MemoryAnswerInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    question=str(payload["question"]),
                ),
                answer_payload,
            )
        ], {"question": str(payload["question"]), "answer_type": "unknown"}

    if (
        route_template == "/api/projects/{project_id}/memory/pages/{memory_page_id}/"
        "open-threads/{thread_id}/operate"
    ):
        update_type = str(payload["update_type"])
        status = "closed" if update_type == "closes" else "resolved"
        source_span_id = str(uuid4())
        thread_payload = {
            "id": thread_id,
            "update_type": update_type,
            "summary": str(payload["summary"]),
            "risk_level": "low",
            "source_delta_id": str(source_delta_id),
            "source_span_ids": [source_span_id],
            "status": status,
            "author_note": str(payload["author_note"]),
        }
        memory_page_payload = {
            "id": str(memory_page_id),
            "page_type": "character",
            "target_ref": {"type": "character", "id": "mira"},
            "title": "Mira",
            "current_canon": {"facts": []},
            "appearance_log": [],
            "event_log": [],
            "relationships": [],
            "knowledge_state": [],
            "open_threads": [thread_payload],
            "contradictions": [],
            "source_refs": [{"type": "source_span", "id": source_span_id}],
            "canon_status": "current",
            "memory_depth": "scene",
        }
        response_payload = {
            "memory_page_id": str(memory_page_id),
            "thread_id": thread_id,
            "status": status,
            "update_type": update_type,
            "memory_page": memory_page_payload,
            "side_effects": {
                "memory_pages": "thread_update_applied",
                "graph_projection": "unchanged",
                "policy_action": "memory_page_thread_author_updated",
            },
        }
        return [
            (
                "memory_page.open_thread.operate",
                MemoryPageThreadOperationInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    memory_page_id=memory_page_id,
                    thread_id=thread_id,
                    update_type=update_type,
                    author_note=str(payload["author_note"]),
                    summary=str(payload["summary"]),
                ),
                response_payload,
            )
        ], {
            "memory_page_id": str(memory_page_id),
            "thread_id": thread_id,
            "status": status,
            "update_type": update_type,
        }

    if route_template == "/api/projects/{project_id}/review-items/{review_item_id}/dismiss":
        return _review_replay_record(
            project_id,
            actor_id,
            request_id,
            idempotency_key,
            review_item_id,
            operation="dismiss",
            author_note=str(payload["author_note"]),
            status="dismissed",
        )

    if route_template == "/api/projects/{project_id}/review-items/{review_item_id}/reopen":
        return _review_replay_record(
            project_id,
            actor_id,
            request_id,
            idempotency_key,
            review_item_id,
            operation="reopen",
            author_note=str(payload["author_note"]),
            status="open",
        )

    if route_template == "/api/projects/{project_id}/review-items/{review_item_id}/resolve":
        return _review_replay_record(
            project_id,
            actor_id,
            request_id,
            idempotency_key,
            review_item_id,
            operation="resolve",
            author_note=str(payload["author_note"]),
            status="resolved",
            resolution=str(payload["resolution"]),
            replacement_refs=list(payload["replacement_refs"]),
        )

    source_delta_routes = {
        "/api/projects/{project_id}/source-deltas",
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
    }
    if route_template in source_delta_routes:
        new_delta_id = uuid4()
        new_version_id = uuid4()
        job_output_id = uuid4()
        return [
            (
                "source_delta.create",
                CreateSourceDeltaInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_id=source_id,
                    previous_version_id=version_id,
                    delta_kind=str(payload["delta_kind"]),
                    range_start=int(payload["range_start"]),
                    range_end=int(payload["range_end"]),
                    base_hash=str(payload["base_hash"]),
                    submitted_text=str(payload["submitted_text"]),
                    source_type=str(payload["source_type"]),
                    source_scope=str(payload["source_scope"]),
                    provenance=dict(payload["provenance"]),
                ),
                {
                    "source_delta_id": str(new_delta_id),
                    "new_version_id": str(new_version_id),
                    "memory_writeback_job_id": str(job_output_id),
                },
            )
        ], {"source_delta_id": str(new_delta_id), "new_version_id": str(new_version_id)}

    if (
        route_template == "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
        "memory-writeback-preview/decisions"
    ):
        decision_id = uuid4()
        return [
            (
                "memory_writeback_preview.decision",
                MemoryWritebackDecisionInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_delta_id=source_delta_id,
                    item_ref=dict(payload["item_ref"]),
                    decision=str(payload["decision"]),
                    author_note=str(payload["author_note"]),
                    correction={},
                    replacement_refs=[],
                ),
                {
                    "decision_id": str(decision_id),
                    "source_delta_id": str(source_delta_id),
                    "item_ref": dict(payload["item_ref"]),
                    "decision": str(payload["decision"]),
                    "status": "rejected",
                    "side_effects": {},
                },
            )
        ], {"decision_id": str(decision_id), "source_delta_id": str(source_delta_id)}

    if route_template == "/api/projects/{project_id}/sources":
        new_source_id = uuid4()
        new_version_id = uuid4()
        new_delta_id = uuid4()
        job_output_id = uuid4()
        raw_hash = sha256(str(payload["text"]).encode("utf-8")).hexdigest()
        return [
            (
                "source.create",
                CreateSourceInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    title=str(payload["title"]),
                    source_type=str(payload["source_type"]),
                    source_scope=str(payload["source_scope"]),
                    ownership_status=str(payload["ownership_status"]),
                    text=str(payload["text"]),
                    version_label=str(payload["version_label"]),
                ),
                {
                    "source_id": str(new_source_id),
                    "version_id": str(new_version_id),
                    "source_delta_id": str(new_delta_id),
                    "memory_writeback_job_id": str(job_output_id),
                    "raw_hash": raw_hash,
                },
            )
        ], {"source_id": str(new_source_id), "version_id": str(new_version_id)}

    if route_template == "/api/projects/{project_id}/sources/{source_id}/archive":
        archived_at = datetime(2026, 6, 11, 12, 0, tzinfo=UTC).isoformat()
        return [
            (
                "source.archive",
                ArchiveSourceInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_id=source_id,
                    author_note=str(payload["author_note"]),
                ),
                {
                    "source_id": str(source_id),
                    "status": "archived",
                    "archived_at": archived_at,
                    "archived_by": str(actor_id),
                },
            )
        ], {"source_id": str(source_id), "status": "archived"}

    if route_template == "/api/projects/{project_id}/sources/{source_id}/versions":
        new_version_id = uuid4()
        raw_hash = sha256(str(payload["text"]).encode("utf-8")).hexdigest()
        return [
            (
                "source_version.create",
                CreateSourceVersionInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_id=source_id,
                    text=str(payload["text"]),
                    version_label=str(payload["version_label"]),
                    supersedes_version_id=UUID(str(payload["supersedes_version_id"])),
                ),
                {
                    "source_id": str(source_id),
                    "version_id": str(new_version_id),
                    "raw_hash": raw_hash,
                    "supersedes_version_id": str(payload["supersedes_version_id"]),
                },
            )
        ], {"source_id": str(source_id), "version_id": str(new_version_id)}

    if (
        route_template
        == "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore"
    ):
        new_delta_id = uuid4()
        new_version_id = uuid4()
        job_output_id = uuid4()
        return [
            (
                "source_version.restore",
                RestoreSourceVersionInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_id=source_id,
                    version_id=version_id,
                    author_note=str(payload["author_note"]),
                ),
                {
                    "source_id": str(source_id),
                    "restored_from_version_id": str(version_id),
                    "source_delta_id": str(new_delta_id),
                    "new_version_id": str(new_version_id),
                    "memory_writeback_job_id": str(job_output_id),
                },
            )
        ], {"source_id": str(source_id), "new_version_id": str(new_version_id)}

    if route_template == "/api/projects/{project_id}/story-schema/genre-packs":
        new_pack_id = uuid4()
        pack_payload = _story_schema_pack_payload(
            new_pack_id,
            project_id=project_id,
            pack_name=str(payload["pack_name"]),
            version=str(payload["version"]),
        )
        return [
            (
                "story_schema.genre_pack.create",
                CreateStorySchemaGenrePackInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    pack_name=str(payload["pack_name"]),
                    version=str(payload["version"]),
                    entity_types=list(payload["entity_types"]),
                    event_types=list(payload["event_types"]),
                    relations=list(payload["relations"]),
                    extraction_hints={},
                    risk_rules={},
                ),
                pack_payload,
            )
        ], {"id": str(new_pack_id), "status": "active"}

    if route_template == "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate":
        pack_payload = _story_schema_pack_payload(
            pack_id,
            project_id=None,
            pack_name="Deprecated Mystery",
            version="v1",
            status="deprecated",
        )
        return [
            (
                "story_schema.genre_pack.deprecate",
                DeprecateStorySchemaGenrePackInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    story_schema_pack_id=pack_id,
                ),
                pack_payload,
            )
        ], {"id": str(pack_id), "status": "deprecated"}

    if route_template == "/api/projects/{project_id}/story-schema/genre-pack":
        schema_payload = _project_schema_payload(
            project_id,
            genre_schema_pack_id=UUID(str(payload["genre_schema_pack_id"])),
        )
        return [
            (
                "story_schema.genre_pack.select",
                SelectProjectStorySchemaGenreInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    genre_schema_pack_id=UUID(str(payload["genre_schema_pack_id"])),
                ),
                schema_payload,
            )
        ], {
            "project_id": str(project_id),
            "genre_schema_pack_id": str(payload["genre_schema_pack_id"]),
        }

    if route_template == "/api/projects/{project_id}/story-schema/project-override":
        override_pack_id = uuid4()
        schema_payload = _project_schema_payload(
            project_id,
            project_override_pack_id=override_pack_id,
        )
        return [
            (
                "story_schema.project_override.upsert",
                UpsertProjectStorySchemaOverrideInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    pack_name="project-overrides",
                    entity_types=list(payload["entity_types"]),
                    event_types=list(payload["event_types"]),
                    relations=list(payload["relations"]),
                    extraction_hints={},
                    risk_rules={},
                ),
                schema_payload,
            )
        ], {"project_id": str(project_id), "project_override_pack_id": str(override_pack_id)}

    raise AssertionError(f"Missing idempotency replay seed for {route_template}")


def _submit_action_input(
    project_id: UUID,
    actor_id: UUID,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, object],
) -> SubmitActionRequestInput:
    return SubmitActionRequestInput(
        project_id=project_id,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        trigger=str(payload["trigger"]),
        action_type=str(payload["action_type"]),
        target=payload["target"],
        constraints=dict(payload["constraints"]),
        expected_output=str(payload["expected_output"]),
        actor_intent=str(payload["actor_intent"]),
        source_id=UUID(str(payload["source_id"])),
        source_version_id=UUID(str(payload["source_version_id"])),
    )


def _submit_agent_action_input(
    project_id: UUID,
    actor_id: UUID,
    request_id: str,
    idempotency_key: str,
    payload: dict[str, object],
    *,
    action_type: str,
    expected_output: str,
) -> SubmitActionRequestInput:
    return SubmitActionRequestInput(
        project_id=project_id,
        actor_id=actor_id,
        request_id=request_id,
        idempotency_key=idempotency_key,
        trigger="toolbar",
        action_type=action_type,
        target=payload["target"],
        constraints={},
        expected_output=expected_output,
        actor_intent=str(payload["actor_intent"]),
        source_id=UUID(str(payload["source_id"])),
        source_version_id=UUID(str(payload["source_version_id"])),
    )


def _review_replay_record(
    project_id: UUID,
    actor_id: UUID,
    request_id: str,
    idempotency_key: str,
    review_item_id: UUID,
    *,
    operation: str,
    author_note: str,
    status: str,
    resolution: str | None = None,
    replacement_refs: list[object] | None = None,
) -> tuple[list[tuple[str, object, dict[str, object]]], dict[str, object]]:
    response_payload = {
        "review_item_id": str(review_item_id),
        "status": status,
        "resolution": resolution,
        "side_effects": {},
    }
    return [
        (
            f"review_item.{operation}",
            ReviewItemOperationInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                review_item_id=review_item_id,
                operation=operation,
                resolution=resolution,
                author_note=author_note,
                replacement_refs=replacement_refs,
                correction={} if operation == "resolve" else None,
            ),
            response_payload,
        )
    ], {"review_item_id": str(review_item_id), "status": status}


def _action_run_payload(action_request_id: UUID, *, output_type: str) -> dict[str, object]:
    return {
        "action_request_id": str(action_request_id),
        "status": "succeeded",
        "output_type": output_type,
        "context_pack_id": str(uuid4())
        if output_type in {"draft_candidates", "beat_candidates"}
        else None,
        "draft_candidate_ids": [str(uuid4())] if output_type == "draft_candidates" else [],
        "risk_finding_ids": [str(uuid4())] if output_type == "risk_findings" else [],
        "beat_candidate_ids": [str(uuid4())] if output_type == "beat_candidates" else [],
    }


def _context_pack_payload(context_pack_id: UUID) -> dict[str, object]:
    return {
        "context_pack_id": str(context_pack_id),
        "schema_version": "writing-context-pack-v1",
        "current_position": {},
        "canonical_context": {},
        "pov_constraint": {},
        "active_characters": [],
        "character_agency_state": {},
        "recent_events": [],
        "character_knowledge": [],
        "object_location_state": [],
        "open_threads": [],
        "risk_context": {},
        "style_memory": {},
        "evidence_refs": [],
    }


def _job_detail_payload(job_id: UUID, *, status: str) -> dict[str, object]:
    return {
        "id": str(job_id),
        "job_type": "run_memory_writeback",
        "status": status,
        "attempt_count": 0,
        "run_after": None,
        "locked_by": None,
        "locked_at": None,
        "last_error": None,
        "payload": {"step": "run_memory_writeback"},
    }


def _story_schema_pack_payload(
    pack_id: UUID,
    *,
    project_id: UUID | None,
    pack_name: str,
    version: str,
    status: str = "active",
) -> dict[str, object]:
    return {
        "id": str(pack_id),
        "project_id": str(project_id) if project_id else None,
        "pack_type": "genre",
        "pack_name": pack_name,
        "version": version,
        "status": status,
        "entity_types": [],
        "event_types": [],
        "relations": [],
        "extraction_hints": {},
        "risk_rules": {},
    }


def _project_schema_payload(
    project_id: UUID,
    *,
    genre_schema_pack_id: UUID | None = None,
    project_override_pack_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "project_id": str(project_id),
        "binding_id": str(uuid4()),
        "base_schema_pack_id": None,
        "genre_schema_pack_id": str(genre_schema_pack_id) if genre_schema_pack_id else None,
        "genre_schema_pack": None,
        "project_override_pack_id": str(project_override_pack_id)
        if project_override_pack_id
        else None,
        "project_override_pack": None,
        "effective_schema": {"source_pack_versions": []},
    }


def _idempotency_request_hash(input_data: object) -> str:
    payload = _jsonable_dataclass(asdict(input_data))
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _jsonable_dataclass(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable_dataclass(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_jsonable_dataclass(nested) for nested in value]
    return value


def _assert_json_contains(actual: dict[str, object], expected_subset: dict[str, object]) -> None:
    for key, expected_value in expected_subset.items():
        assert actual.get(key) == expected_value, (key, expected_value, actual)


def _write_endpoint_permission_payload(
    route_template: str,
    ids: dict[str, UUID | str],
) -> dict[str, object] | None:
    source_id = str(ids["source_id"])
    version_id = str(ids["version_id"])
    raw_hash = str(ids["raw_hash"])
    action_target = {
        "kind": "selected_text",
        "source_id": source_id,
        "source_version_id": version_id,
        "range": {"start": 0, "end": 8},
    }
    action_body = {
        "source_id": source_id,
        "source_version_id": version_id,
        "trigger": "selection",
        "action_type": "rewrite_span",
        "target": action_target,
        "constraints": {},
        "expected_output": "draft_candidate",
        "actor_intent": "改写这里",
    }
    agent_body = {
        "source_id": source_id,
        "source_version_id": version_id,
        "target": action_target,
        "actor_intent": "继续这一段",
        "current_text_window": "米拉停在门口。",
    }
    source_delta_body = {
        "delta_kind": "replace",
        "range_start": 0,
        "range_end": 8,
        "base_hash": raw_hash,
        "submitted_text": "米拉推开门。",
        "source_type": "draft_manuscript",
        "source_scope": "user_draft",
        "provenance": {"source": "write-permission-matrix"},
    }

    payloads: dict[str, dict[str, object] | None] = {
        "/api/projects/{project_id}/action-requests": action_body,
        "/api/projects/{project_id}/action-requests/{action_request_id}/run": {
            "current_text_window": "米拉停在门口。"
        },
        "/api/projects/{project_id}/agent/check-risk": agent_body,
        "/api/projects/{project_id}/agent/draft-next-passage": agent_body,
        "/api/projects/{project_id}/agent/rewrite-current-page": agent_body,
        "/api/projects/{project_id}/agent/suggest-next-beat": agent_body,
        "/api/projects/{project_id}/candidates/{candidate_id}/accept": {
            "accept_mode": "replace",
            "target_source_id": source_id,
            "target_version_id": version_id,
            "insert_or_replace_range": {"start": 0, "end": 8},
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": False,
            "base_hash": raw_hash,
            "accepted_text": "米拉推开门。",
        },
        "/api/projects/{project_id}/candidates/{candidate_id}/explain": None,
        "/api/projects/{project_id}/candidates/{candidate_id}/override-block": {
            "override_reason": "author accepts the explicit risk"
        },
        "/api/projects/{project_id}/candidates/{candidate_id}/reject": {
            "author_note": "reject this candidate"
        },
        "/api/projects/{project_id}/candidates/{candidate_id}/revise": {
            "author_note": "try a quieter version",
            "revised_text": "米拉轻轻推开门。",
        },
        "/api/projects/{project_id}/context-packs/build": {
            "current_source_id": source_id,
            "current_version_id": version_id,
            "mode": "rewrite_span",
            "current_text_window": "米拉停在门口。",
        },
        "/api/projects/{project_id}/jobs/{job_id}/cancel": {"author_note": "cancel test"},
        "/api/projects/{project_id}/jobs/{job_id}/retry": {"author_note": "retry test"},
        "/api/projects/{project_id}/memory/answer": {"question": "米拉知道什么？"},
        (
            "/api/projects/{project_id}/memory/pages/{memory_page_id}/"
            "open-threads/{thread_id}/operate"
        ): {
            "update_type": "pays_off",
            "summary": "The map origin has been paid off by the archive reveal.",
            "author_note": "Mark this thread as paid off after reviewing the cited scene.",
        },
        "/api/projects/{project_id}/invitations": {
            "member_actor_id": str(uuid4()),
            "role": "viewer",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/matrix-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
        },
        "/api/projects/{project_id}/invitations/{invitation_id}/external-proof": {
            "delivery_proof_ref": "ses://sextant-prod/messages/matrix-delivery",
            "token_proof_ref": "auth0://sextant-prod/tickets/matrix-token",
        },
        "/api/projects/{project_id}/members/{member_actor_id}": {"role": "viewer"},
        "/api/projects/{project_id}/members/{member_actor_id}/revoke": None,
        "/api/projects/{project_id}/review-items/{review_item_id}/dismiss": {
            "author_note": "dismiss test"
        },
        "/api/projects/{project_id}/review-items/{review_item_id}/reopen": {
            "author_note": "reopen test"
        },
        "/api/projects/{project_id}/review-items/{review_item_id}/resolve": {
            "resolution": "accepted_as_change",
            "author_note": "resolved by source edit",
            "replacement_refs": [{"type": "source_delta", "id": str(ids["source_delta_id"])}],
        },
        "/api/projects/{project_id}/source-deltas": {
            **source_delta_body,
            "source_id": source_id,
            "previous_version_id": version_id,
        },
        (
            "/api/projects/{project_id}/source-deltas/{source_delta_id}/"
            "memory-writeback-preview/decisions"
        ): {
            "item_ref": {"type": "source_span", "id": str(uuid4())},
            "decision": "reject",
            "author_note": "not canon",
        },
        "/api/projects/{project_id}/sources": {
            "title": "Viewer Import",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "ownership_status": "owned",
            "text": "米拉停在门口。",
            "version_label": "v1",
        },
        "/api/projects/{project_id}/sources/{source_id}/archive": {"author_note": "archive test"},
        "/api/projects/{project_id}/sources/{source_id}/versions": {
            "text": "米拉停在门口。",
            "version_label": "v2",
            "supersedes_version_id": version_id,
        },
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore": {
            "author_note": "restore test"
        },
        (
            "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas"
        ): source_delta_body,
        "/api/projects/{project_id}/story-schema/genre-packs": {
            "pack_name": "Mystery",
            "version": "v1",
            "entity_types": [],
            "event_types": [],
            "relations": [],
        },
        "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate": None,
        "/api/projects/{project_id}/story-schema/genre-pack": {
            "genre_schema_pack_id": str(ids["pack_id"])
        },
        "/api/projects/{project_id}/story-schema/project-override": {
            "entity_types": [],
            "event_types": [],
            "relations": [],
        },
    }
    return payloads[route_template]


def _assert_memory_page_thread_success_side_effects(
    session: Session,
    ids: dict[str, UUID | str],
    body: dict[str, object],
    before: dict[str, int],
) -> None:
    page = session.get(MemoryPage, UUID(str(ids["memory_page_id"])))
    assert page is not None
    assert session.query(AuditEvent).count() == before["audit_events"] + 1
    assert session.query(IdempotencyRecord).count() == before["idempotency_records"] + 1
    assert session.query(ContextPackReadinessRecord).count() == (
        before["context_pack_readiness"] + 1
    )
    assert session.query(EvidenceLogEntry).count() == before["memory_evidence_log_entries"] + 1
    unchanged_tables = {
        "source_accepted_fragments",
        "agent_action_requests",
        "agent_beat_candidates",
        "agent_context_packs",
        "agent_draft_candidates",
        "agent_review_findings",
        "agent_storytelling_controls",
        "story_fact_assertions",
        "memory_graph_projection_edges",
        "memory_graph_projection_runs",
        "job_records",
        "memory_writeback_decisions",
        "review_items",
        "skill_runs",
        "source_deltas",
    }
    after = _permission_matrix_side_effect_counts(session)
    for key in unchanged_tables:
        assert after[key] == before[key], key
    thread = page.open_threads[0]
    assert thread["id"] == ids["thread_id"]
    assert thread["update_type"] == "pays_off"
    assert thread["status"] == "resolved"
    assert thread["summary"] == "The map origin has been paid off by the archive reveal."
    assert thread["author_note"] == "Mark this thread as paid off after reviewing the cited scene."
    assert body["side_effects"]["memory_pages"] == "thread_update_applied"
    assert body["memory_page"]["id"] == str(ids["memory_page_id"])


def _body_resource_not_found_payload(
    session: Session,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
    body_case: str,
) -> dict[str, object]:
    assert payload is not None
    missing_id = str(uuid4())
    next_payload = dict(payload)
    if body_case in {
        "genre_schema_pack_id",
        "previous_version_id",
        "source_id",
        "supersedes_version_id",
        "target_version_id",
    }:
        next_payload[body_case] = missing_id
        if body_case == "target_version_id":
            candidate = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
            assert candidate is not None
            candidate.target_version_id = UUID(missing_id)
            session.commit()
        return next_payload
    if body_case == "item_ref":
        next_payload["item_ref"] = {"type": "source_span", "id": missing_id}
        return next_payload
    if body_case == "replacement_refs.source_delta":
        next_payload["resolution"] = "fixed_by_text_edit"
        next_payload["author_note"] = "resolved by a source edit"
        next_payload["replacement_refs"] = [{"type": "source_delta", "id": missing_id}]
        return next_payload
    raise AssertionError(f"Missing body resource not-found payload case: {body_case}")


def _prepare_write_state_error_case(
    session: Session,
    ids: dict[str, UUID | str],
    payload: dict[str, object] | None,
    case_name: str,
) -> dict[str, object] | None:
    next_payload = dict(payload) if payload is not None else None
    action_request = session.get(AgentActionRequestRecord, UUID(str(ids["action_request_id"])))
    candidate = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
    job = session.get(JobRecord, UUID(str(ids["job_id"])))
    review_item = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
    version = session.get(SourceVersion, UUID(str(ids["version_id"])))
    assert action_request is not None
    assert candidate is not None
    assert job is not None
    assert review_item is not None
    assert version is not None

    if case_name == "action_request_already_succeeded":
        action_request.status = "succeeded"
    elif case_name == "candidate_accept_blocked":
        candidate.status = "blocked"
    elif case_name == "candidate_accept_stale_base":
        version.raw_hash = "hash-newer-than-candidate"
    elif case_name == "candidate_override_not_blocked":
        candidate.status = "offered_to_author"
    elif case_name in {"candidate_reject_archived", "candidate_revise_archived"}:
        candidate.status = "archived"
    elif case_name in {"job_cancel_succeeded", "job_retry_succeeded"}:
        job.status = "succeeded"
    elif case_name in {"review_dismiss_dismissed", "review_resolve_dismissed"}:
        review_item.status = "dismissed"
    elif case_name == "review_reopen_open":
        review_item.status = "open"
    elif case_name == "source_restore_current":
        pass
    else:
        raise AssertionError(f"Missing state-error setup case: {case_name}")

    session.commit()
    return next_payload


def _write_state_error_side_effect_snapshot(
    session: Session,
    ids: dict[str, UUID | str],
) -> dict[str, object]:
    action_request = session.get(AgentActionRequestRecord, UUID(str(ids["action_request_id"])))
    candidate = session.get(AgentDraftCandidateRecord, UUID(str(ids["candidate_id"])))
    job = session.get(JobRecord, UUID(str(ids["job_id"])))
    review_item = session.get(ReviewItemRecord, UUID(str(ids["review_item_id"])))
    version = session.get(SourceVersion, UUID(str(ids["version_id"])))
    assert action_request is not None
    assert candidate is not None
    assert job is not None
    assert review_item is not None
    assert version is not None
    return {
        "counts": _permission_matrix_side_effect_counts(session),
        "action_request_status": action_request.status,
        "candidate_status": candidate.status,
        "candidate_author_action": candidate.author_action,
        "candidate_accepted_text_ref": candidate.accepted_text_ref,
        "candidate_override_reason": candidate.override_reason,
        "job_status": job.status,
        "job_attempt_count": job.attempt_count,
        "review_item_status": review_item.status,
        "review_item_resolution": review_item.resolution,
        "review_item_side_effects": review_item.side_effects,
        "version_raw_hash": version.raw_hash,
    }


def _permission_matrix_side_effect_counts(session: Session) -> dict[str, int]:
    models = [
        AcceptedFragmentRecord,
        AgentActionRequestRecord,
        AgentBeatCandidateRecord,
        AgentContextPackRecord,
        AgentDraftCandidateRecord,
        AgentReviewFindingRecord,
        AgentStorytellingControlRecord,
        AuditEvent,
        ContextPackReadinessRecord,
        EvidenceLogEntry,
        FactAssertionRecord,
        GraphProjectionEdge,
        GraphProjectionRun,
        IdempotencyRecord,
        JobRecord,
        MemoryPage,
        MemoryWritebackDecisionRecord,
        Project,
        ProjectInvitation,
        ProjectMembership,
        ProjectStorySchemaBinding,
        RawSource,
        ReviewItemRecord,
        SkillRun,
        SourceDeltaRecord,
        SourceProcessedView,
        SourceSpan,
        SourceVersion,
        StoryAliasRecord,
        StoryCanonicalEntity,
        StoryCanonicalEvent,
        StoryEventCandidate,
        StoryMention,
        StorySchemaPackRecord,
    ]
    return {model.__tablename__: session.query(model).count() for model in models}


def _actual_api_error_codes_from_source() -> set[str]:
    backend_root = Path(__file__).resolve().parents[2]
    source_files = [
        backend_root / "src/sextant/api/app.py",
        backend_root / "src/sextant/application/use_cases.py",
    ]
    error_codes = {"authentication_required"}
    for source_file in source_files:
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "ApplicationError":
                continue
            if not node.args:
                continue
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                error_codes.add(first_arg.value)
    return error_codes


def _assert_api_error_response(
    response,
    *,
    status_code: int,
    code: str,
) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    assert isinstance(body["error"]["details"], dict)


class BlankStoryProvider:
    skill_name = "api_contract_story_draft"
    skill_version = "api-contract-story-draft.v1"

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


def test_project_detail_endpoint_returns_membership_role_without_write_side_effects(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    viewer_id = uuid4()
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

    response = client.get(
        f"/api/projects/{project.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(project.id)
    assert body["name"] == "Harbor Nine"
    assert body["actor_role"] == "viewer"
    assert body["created_at"]
    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0

    outsider_response = client.get(
        f"/api/projects/{project.id}",
        headers={"X-Actor-Id": str(uuid4())},
    )

    assert outsider_response.status_code == 403
    assert outsider_response.json()["error"]["code"] == "permission_denied"


def test_project_member_management_endpoints_upsert_list_and_revoke_members(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    editor_id = uuid4()

    list_response = client.get(
        f"/api/projects/{project.id}/members",
        headers={"X-Actor-Id": str(owner_id)},
    )

    assert list_response.status_code == 200
    assert [
        (item["actor_id"], item["role"], item["status"]) for item in list_response.json()["items"]
    ] == [(str(owner_id), "owner", "active")]

    upsert_response = client.put(
        f"/api/projects/{project.id}/members/{editor_id}",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-member-upsert",
            "Idempotency-Key": "idem-api-member-upsert",
        },
        json={"role": "editor"},
    )

    assert upsert_response.status_code == 200, upsert_response.json()
    assert upsert_response.json()["member"]["actor_id"] == str(editor_id)
    assert upsert_response.json()["member"]["role"] == "editor"
    assert upsert_response.json()["status"] == "active"

    member = (
        session.query(ProjectMembership).filter_by(project_id=project.id, actor_id=editor_id).one()
    )
    assert member.role == "editor"
    assert member.status == "active"

    revoke_response = client.post(
        f"/api/projects/{project.id}/members/{editor_id}/revoke",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-member-revoke",
            "Idempotency-Key": "idem-api-member-revoke",
        },
    )

    assert revoke_response.status_code == 200, revoke_response.json()
    assert revoke_response.json()["member"]["status"] == "revoked"
    session.refresh(member)
    assert member.status == "revoked"

    editor_project_response = client.get(
        f"/api/projects/{project.id}",
        headers={"X-Actor-Id": str(editor_id)},
    )
    _assert_api_error_response(
        editor_project_response,
        status_code=403,
        code="permission_denied",
    )

    audit_types = [event.event_type for event in session.query(AuditEvent).all()]
    assert audit_types == ["project_member.upserted", "project_member.revoked"]


def test_project_invitation_endpoint_records_external_delivery_intent_without_membership(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    before_counts = {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
    }

    response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation",
            "Idempotency-Key": "idem-api-invitation",
        },
        json={
            "member_actor_id": str(invited_actor_id),
            "role": "editor",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/frank-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["project_id"] == str(project.id)
    assert body["member_actor_id"] == str(invited_actor_id)
    assert body["role"] == "editor"
    assert body["status"] == "pending_external_delivery"
    assert body["delivery_status"] == "not_sent"
    assert body["token_status"] == "not_issued"

    invitation_row = session.get(ProjectInvitation, UUID(body["id"]))
    assert invitation_row is not None
    assert invitation_row.status == "pending_external_delivery"
    assert invitation_row.delivery_status == "not_sent"
    assert invitation_row.token_status == "not_issued"

    assert {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
    } == before_counts
    assert [event.event_type for event in session.query(AuditEvent).all()] == [
        "project_invitation.created"
    ]
    assert session.query(IdempotencyRecord).one().operation == "project_invitation.create"


@pytest.mark.parametrize(
    "payload_override",
    [
        {"delivery_provider_ref": "ses://user:secret@sextant-prod/invitations"},
        {"delivery_target_ref": "ses://sextant-prod/recipient/frank-author?token=secret"},
        {"token_issuer_ref": "auth0://sextant-prod/clients/web#secret-token"},
    ],
)
def test_project_invitation_endpoint_rejects_secret_bearing_external_refs(
    client: TestClient,
    session: Session,
    payload_override: dict[str, str],
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    before_counts = _permission_matrix_side_effect_counts(session)
    payload = {
        "member_actor_id": str(invited_actor_id),
        "role": "editor",
        "delivery_provider_ref": "ses://sextant-prod/invitations",
        "delivery_target_ref": "ses://sextant-prod/recipient/frank-author",
        "token_issuer_ref": "auth0://sextant-prod/clients/web",
        **payload_override,
    }

    response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": f"req-api-invitation-secret-ref-{len(payload_override)}",
            "Idempotency-Key": f"idem-api-invitation-secret-ref-{len(payload_override)}",
        },
        json=payload,
    )

    _assert_api_error_response(
        response,
        status_code=400,
        code="schema_validation_failed",
    )
    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_project_invitation_endpoint_accepts_supabase_auth_admin_invite_refs(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    create_response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-supabase-auth",
            "Idempotency-Key": "idem-api-invitation-supabase-auth",
        },
        json={
            "member_actor_id": str(invited_actor_id),
            "role": "viewer",
            "delivery_provider_ref": ("supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email"),
            "delivery_target_ref": ("supabase-auth://ientixxmbdeoqdmkublx/recipient/sha256-test"),
            "token_issuer_ref": "supabase://ientixxmbdeoqdmkublx/auth",
        },
    )

    assert create_response.status_code == 200, create_response.json()
    invitation_id = UUID(create_response.json()["id"])
    proof_response = client.post(
        f"/api/projects/{project.id}/invitations/{invitation_id}/external-proof",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-supabase-auth-proof",
            "Idempotency-Key": "idem-api-invitation-supabase-auth-proof",
        },
        json={
            "delivery_proof_ref": (
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/2026-07-01"
            ),
            "token_proof_ref": "supabase://ientixxmbdeoqdmkublx/auth/2026-07-01",
        },
    )

    assert proof_response.status_code == 200, proof_response.json()
    body = proof_response.json()
    assert body["status"] == "external_delivery_recorded"
    assert body["delivery_status"] == "sent"
    assert body["token_status"] == "issued"
    assert body["delivery_proof_ref"].startswith("supabase-auth://")
    assert body["token_proof_ref"].startswith("supabase://")


def test_project_invitation_external_proof_records_sent_status_without_membership(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    create_response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-proof-create",
            "Idempotency-Key": "idem-api-invitation-proof-create",
        },
        json={
            "member_actor_id": str(invited_actor_id),
            "role": "editor",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/proof-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
        },
    )
    assert create_response.status_code == 200, create_response.json()
    invitation_id = UUID(create_response.json()["id"])
    before_counts = {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
    }

    response = client.post(
        f"/api/projects/{project.id}/invitations/{invitation_id}/external-proof",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-proof",
            "Idempotency-Key": "idem-api-invitation-proof",
        },
        json={
            "delivery_proof_ref": "ses://sextant-prod/messages/proof-delivery",
            "token_proof_ref": "auth0://sextant-prod/tickets/proof-token",
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["id"] == str(invitation_id)
    assert body["status"] == "external_delivery_recorded"
    assert body["delivery_status"] == "sent"
    assert body["token_status"] == "issued"
    assert body["delivery_proof_ref"] == "ses://sextant-prod/messages/proof-delivery"
    assert body["token_proof_ref"] == "auth0://sextant-prod/tickets/proof-token"

    invitation_row = session.get(ProjectInvitation, invitation_id)
    assert invitation_row is not None
    assert invitation_row.status == "external_delivery_recorded"
    assert invitation_row.delivery_status == "sent"
    assert invitation_row.token_status == "issued"
    assert invitation_row.delivery_proof_ref == "ses://sextant-prod/messages/proof-delivery"
    assert invitation_row.token_proof_ref == "auth0://sextant-prod/tickets/proof-token"

    assert {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
    } == before_counts
    assert [event.event_type for event in session.query(AuditEvent).all()] == [
        "project_invitation.created",
        "project_invitation.external_proof_recorded",
    ]
    assert [record.operation for record in session.query(IdempotencyRecord).all()] == [
        "project_invitation.create",
        "project_invitation.external_proof",
    ]


def test_project_invitation_list_returns_persisted_external_proof_without_side_effects(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    create_response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-list-create",
            "Idempotency-Key": "idem-api-invitation-list-create",
        },
        json={
            "member_actor_id": str(invited_actor_id),
            "role": "editor",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/list-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
        },
    )
    assert create_response.status_code == 200, create_response.json()
    invitation_id = UUID(create_response.json()["id"])
    proof_response = client.post(
        f"/api/projects/{project.id}/invitations/{invitation_id}/external-proof",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-list-proof",
            "Idempotency-Key": "idem-api-invitation-list-proof",
        },
        json={
            "delivery_proof_ref": "ses://sextant-prod/messages/list-delivery",
            "token_proof_ref": "auth0://sextant-prod/tickets/list-token",
        },
    )
    assert proof_response.status_code == 200, proof_response.json()
    before_counts = {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
        "audit_events": session.query(AuditEvent).count(),
        "idempotency_records": session.query(IdempotencyRecord).count(),
    }

    response = client.get(
        f"/api/projects/{project.id}/invitations",
        headers={"X-Actor-Id": str(owner_id)},
    )

    assert response.status_code == 200, response.json()
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(invitation_id)
    assert items[0]["member_actor_id"] == str(invited_actor_id)
    assert items[0]["status"] == "external_delivery_recorded"
    assert items[0]["delivery_status"] == "sent"
    assert items[0]["token_status"] == "issued"
    assert items[0]["delivery_proof_ref"] == "ses://sextant-prod/messages/list-delivery"
    assert items[0]["token_proof_ref"] == "auth0://sextant-prod/tickets/list-token"

    assert {
        "memberships": session.query(ProjectMembership).count(),
        "source_deltas": session.query(SourceDeltaRecord).count(),
        "source_spans": session.query(SourceSpan).count(),
        "evidence_logs": session.query(EvidenceLogEntry).count(),
        "memory_pages": session.query(MemoryPage).count(),
        "review_items": session.query(ReviewItemRecord).count(),
        "graph_edges": session.query(GraphProjectionEdge).count(),
        "jobs": session.query(JobRecord).count(),
        "audit_events": session.query(AuditEvent).count(),
        "idempotency_records": session.query(IdempotencyRecord).count(),
    } == before_counts


@pytest.mark.parametrize(
    "payload",
    [
        {"delivery_proof_ref": "local://dev/invitation-delivery"},
        {"delivery_proof_ref": "https://localhost/invitation-delivery"},
        {"delivery_proof_ref": "https://ci.sextant.example/invitation?token=secret"},
        {"delivery_proof_ref": "ses://user:secret@sextant-prod/messages/proof-delivery"},
        {
            "delivery_proof_ref": "ses://sextant-prod/messages/proof-delivery",
            "token_proof_ref": "local://dev/token",
        },
        {
            "delivery_proof_ref": "ses://sextant-prod/messages/proof-delivery",
            "token_proof_ref": "https://ci.sextant.example/token#secret",
        },
    ],
)
def test_project_invitation_external_proof_rejects_local_or_fake_proof_refs(
    client: TestClient,
    session: Session,
    payload: dict[str, str],
) -> None:
    project, _raw_source, _version, owner_id = seed_source(session)
    invited_actor_id = uuid4()
    create_response = client.post(
        f"/api/projects/{project.id}/invitations",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": "req-api-invitation-local-proof-create",
            "Idempotency-Key": "idem-api-invitation-local-proof-create",
        },
        json={
            "member_actor_id": str(invited_actor_id),
            "role": "editor",
            "delivery_provider_ref": "ses://sextant-prod/invitations",
            "delivery_target_ref": "ses://sextant-prod/recipient/local-proof-author",
            "token_issuer_ref": "auth0://sextant-prod/clients/web",
        },
    )
    assert create_response.status_code == 200, create_response.json()
    invitation_id = UUID(create_response.json()["id"])
    before_counts = _permission_matrix_side_effect_counts(session)

    response = client.post(
        f"/api/projects/{project.id}/invitations/{invitation_id}/external-proof",
        headers={
            "X-Actor-Id": str(owner_id),
            "X-Request-Id": f"req-api-invitation-local-proof-{len(payload)}",
            "Idempotency-Key": f"idem-api-invitation-local-proof-{len(payload)}",
        },
        json=payload,
    )

    _assert_api_error_response(
        response,
        status_code=400,
        code="schema_validation_failed",
    )
    invitation_row = session.get(ProjectInvitation, invitation_id)
    assert invitation_row is not None
    assert invitation_row.status == "pending_external_delivery"
    assert invitation_row.delivery_status == "not_sent"
    assert invitation_row.token_status == "not_issued"
    assert invitation_row.delivery_proof_ref is None
    assert invitation_row.token_proof_ref is None
    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_source_detail_endpoint_returns_summary_without_write_side_effects(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    viewer_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=viewer_id,
            role="viewer",
            status="active",
        )
    )
    other_project = Project(id=uuid4(), name="Other Project")
    other_source = RawSource(
        id=uuid4(),
        project_id=other_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/other",
    )
    session.add_all([other_project, other_source])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == str(raw_source.id)
    assert body["title"] == "Chapter 3"
    assert body["latest_version_id"] == str(version.id)
    assert body["latest_raw_hash"] == "hash-v1"
    assert body["version_count"] == 1
    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0

    cross_project_response = client.get(
        f"/api/projects/{project.id}/sources/{other_source.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert cross_project_response.status_code == 404
    assert cross_project_response.json()["error"]["code"] == "not_found"


def test_action_request_endpoint_maps_missing_target_error(
    client: TestClient, session: Session
) -> None:
    project, _, _, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-1",
            "Idempotency-Key": "idem-api-1",
        },
        json={
            "trigger": "natural_language",
            "action_type": "rewrite_span",
            "target": None,
            "constraints": {},
            "expected_output": "draft_candidate",
            "actor_intent": "改写这里",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "missing_target"


def test_action_request_endpoint_returns_submitted_request(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-2",
            "Idempotency-Key": "idem-api-2",
        },
        json={
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "trigger": "selection",
            "action_type": "rewrite_span",
            "target": {
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 0, "end": 12},
            },
            "constraints": {"tone": "克制"},
            "expected_output": "draft_candidate",
            "actor_intent": "改写这里",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert session.get(AgentActionRequestRecord, UUID(body["action_request_id"])) is not None
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )


def test_action_request_endpoint_error_matrix_uses_structured_envelope(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    base_headers = {
        "X-Actor-Id": str(actor_id),
        "X-Request-Id": "req-api-error-matrix-base",
        "Idempotency-Key": "idem-api-error-matrix-base",
    }
    valid_payload = {
        "source_id": str(raw_source.id),
        "source_version_id": str(version.id),
        "trigger": "selection",
        "action_type": "rewrite_span",
        "target": {
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 12},
        },
        "constraints": {},
        "expected_output": "draft_candidate",
        "actor_intent": "改写这里",
    }

    unsupported_action = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-error-matrix-unsupported",
            "Idempotency-Key": "idem-api-error-matrix-unsupported",
        },
        json={**valid_payload, "action_type": "invent_canon"},
    )
    expected_output_mismatch = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-error-matrix-output",
            "Idempotency-Key": "idem-api-error-matrix-output",
        },
        json={**valid_payload, "expected_output": "memory_answer"},
    )
    invalid_range = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-error-matrix-range",
            "Idempotency-Key": "idem-api-error-matrix-range",
        },
        json={
            **valid_payload,
            "target": {
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 12, "end": 0},
            },
        },
    )
    first_submit = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers=base_headers,
        json=valid_payload,
    )
    idempotency_conflict = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers=base_headers,
        json={**valid_payload, "actor_intent": "同一个幂等键不能换请求体。"},
    )

    _assert_api_error_response(
        unsupported_action,
        status_code=400,
        code="unsupported_action_type",
    )
    _assert_api_error_response(
        expected_output_mismatch,
        status_code=400,
        code="expected_output_mismatch",
    )
    _assert_api_error_response(
        invalid_range,
        status_code=400,
        code="invalid_target_range",
    )
    assert first_submit.status_code == 201
    _assert_api_error_response(
        idempotency_conflict,
        status_code=409,
        code="idempotency_conflict",
    )
    assert session.query(AgentActionRequestRecord).count() == 1
    assert (
        session.query(IdempotencyRecord).filter_by(operation="submit_action_request").count() == 1
    )


def test_action_request_detail_endpoint_returns_structured_request_without_write_side_effects(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    viewer_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=viewer_id,
            role="viewer",
            status="active",
        )
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        scene_id=None,
        chapter_id=None,
        pov_character_id=None,
        actor_intent="改写这里",
        trigger="selection",
        action_type="rewrite_span",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 12},
        },
        constraints={"tone": "克制"},
        expected_output="draft_candidate",
        status="submitted",
        created_by=viewer_id,
    )
    other_project = Project(id=uuid4(), name="Other")
    other_source = RawSource(
        id=uuid4(),
        project_id=other_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Source",
        ownership_status="owned",
        raw_text_ref="object://raw/other",
    )
    other_action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=other_project.id,
        source_id=other_source.id,
        source_version_id=None,
        scene_id=None,
        chapter_id=None,
        pov_character_id=None,
        actor_intent="other",
        trigger="toolbar",
        action_type="ask_memory",
        target=None,
        constraints={},
        expected_output="memory_answer",
        status="submitted",
        created_by=uuid4(),
    )
    session.add_all([action_request, other_project, other_source, other_action_request])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/action-requests/{action_request.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action_request_id"] == str(action_request.id)
    assert body["project_id"] == str(project.id)
    assert body["source_id"] == str(raw_source.id)
    assert body["source_version_id"] == str(version.id)
    assert body["actor_intent"] == "改写这里"
    assert body["trigger"] == "selection"
    assert body["action_type"] == "rewrite_span"
    assert body["target"]["range"] == {"start": 0, "end": 12}
    assert body["constraints"] == {"tone": "克制"}
    assert body["expected_output"] == "draft_candidate"
    assert body["status"] == "submitted"
    assert body["created_by"] == str(viewer_id)
    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0

    cross_project_response = client.get(
        f"/api/projects/{project.id}/action-requests/{other_action_request.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )
    assert cross_project_response.status_code == 404
    assert cross_project_response.json()["error"]["code"] == "not_found"

    outsider_response = client.get(
        f"/api/projects/{project.id}/action-requests/{action_request.id}",
        headers={"X-Actor-Id": str(uuid4())},
    )
    assert outsider_response.status_code == 403
    assert outsider_response.json()["error"]["code"] == "permission_denied"


def test_action_request_run_error_matrix_maps_invalid_story_provider_output(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        scene_id=None,
        chapter_id=None,
        pov_character_id=None,
        actor_intent="继续写，但保持信息克制。",
        trigger="toolbar",
        action_type="draft_next_passage",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 12},
        },
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    session.add(action_request)
    session.commit()
    invalid_provider_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            story_draft_provider=BlankStoryProvider(),
        )
    )

    response = invalid_provider_client.post(
        f"/api/projects/{project.id}/action-requests/{action_request.id}/run",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-invalid-story-provider",
            "Idempotency-Key": "idem-api-invalid-story-provider",
        },
        json={"current_text_window": "米拉停在西档案室门口。"},
    )

    _assert_api_error_response(
        response,
        status_code=502,
        code="llm_output_invalid",
    )
    assert session.get(AgentActionRequestRecord, action_request.id).status == "submitted"
    assert session.query(SkillRun).filter_by(status="failed_terminal").count() == 2
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_action_request_endpoint_accepts_ask_memory_without_target(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-ask-memory",
            "Idempotency-Key": "idem-api-ask-memory",
        },
        json={
            "trigger": "natural_language",
            "action_type": "ask_memory",
            "target": None,
            "constraints": {"subject_ref": {"type": "character", "id": "mira"}},
            "expected_output": "memory_answer",
            "actor_intent": "米拉知道钥匙是谁给的吗？",
        },
    )

    assert response.status_code == 201
    body = response.json()
    stored = session.get(AgentActionRequestRecord, UUID(body["action_request_id"]))
    assert body["status"] == "submitted"
    assert stored is not None
    assert stored.action_type == "ask_memory"
    assert stored.expected_output == "memory_answer"
    assert stored.target is None


def test_api_request_observability_records_metrics_without_manuscript_text(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    metrics = MetricsRegistry()
    logs: list[str] = []
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            metrics=metrics,
            log_sink=logs.append,
        )
    )
    manuscript = "Mira 把钥匙放在两人之间。钥匙是冷的。"

    response = observed_client.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-observe-source",
            "Idempotency-Key": "idem-api-observe-source",
        },
        json={
            "title": "Observation Source",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": manuscript,
            "version_label": "v1",
        },
    )

    assert response.status_code == 201
    assert logs
    assert manuscript not in logs[0]
    assert '"event_type":"api.request"' in logs[0]
    counters = {
        (counter.name, tuple(sorted(counter.labels.items()))): counter.value
        for counter in metrics.snapshot()
    }
    assert (
        counters[
            (
                "sextant_api_requests_total",
                (
                    ("method", "POST"),
                    ("path", "/api/projects/{project_id}/sources"),
                    ("status", "201"),
                ),
            )
        ]
        == 1
    )


def test_api_trace_context_returns_safe_headers_and_log_fields(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    logs: list[str] = []
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            log_sink=logs.append,
        )
    )
    incoming_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    response = observed_client.get(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-trace-context",
            "traceparent": incoming_traceparent,
        },
    )

    assert response.status_code == 200
    response_traceparent = response.headers["traceparent"]
    assert response.headers["x-trace-id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert response_traceparent.startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
    assert response_traceparent.endswith("-01")
    assert "00f067aa0ba902b7" not in response_traceparent
    assert logs
    logged = json.loads(logs[0])
    assert logged["payload"]["trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert len(logged["payload"]["span_id"]) == 16
    assert incoming_traceparent not in logs[0]


def test_observability_trace_endpoint_reports_sanitized_recent_api_activity(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
        )
    )
    incoming_traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    manuscript = "Mira 把钥匙放在两人之间。钥匙是冷的。"

    response = observed_client.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-observability-trace",
            "Idempotency-Key": "idem-api-observability-trace",
            "traceparent": incoming_traceparent,
        },
        json={
            "title": "Trace Source",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": manuscript,
            "version_label": "v1",
        },
    )
    traces_response = observed_client.get("/observability/traces")

    assert response.status_code == 201
    assert traces_response.status_code == 200
    body = traces_response.json()
    rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
    assert body["status"] == "ready"
    assert body["service"] == "sextant-api"
    assert body["trace_sample_count"] == 1
    assert body["samples"][0]["method"] == "POST"
    assert body["samples"][0]["path"] == "/api/projects/{project_id}/sources"
    assert body["samples"][0]["status"] == 201
    assert body["samples"][0]["trace_id_sha256"]
    assert body["samples"][0]["span_id_sha256"]
    assert "4bf92f3577b34da6a3ce929d0e0e4736" not in rendered
    assert "00f067aa0ba902b7" not in rendered
    assert str(actor_id) not in rendered
    assert manuscript not in rendered


def test_observability_alert_endpoint_reports_metric_derived_state_without_payloads(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    metrics = MetricsRegistry()
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            metrics=metrics,
        )
    )
    manuscript = "Mira 把钥匙放在两人之间。钥匙是冷的。"

    failed = observed_client.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-observability-alert",
            "Idempotency-Key": "idem-api-observability-alert",
        },
        json={
            "title": "Alert Source",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": manuscript,
            "version_label": "",
        },
    )
    alerts_response = observed_client.get("/observability/alerts")

    assert failed.status_code == 400
    assert alerts_response.status_code == 200
    body = alerts_response.json()
    rendered = json.dumps(body, ensure_ascii=False, sort_keys=True)
    assert body["service"] == "sextant-api"
    assert body["status"] == "degraded"
    assert body["active_alert_count"] == 1
    assert body["checks"][0]["name"] == "api_error_rate"
    assert body["checks"][0]["status"] == "firing"
    assert body["checks"][0]["observed_error_count"] == 1
    assert manuscript not in rendered
    assert str(actor_id) not in rendered


def test_metrics_endpoint_exports_request_counters_without_manuscript_text(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    metrics = MetricsRegistry()
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            metrics=metrics,
        )
    )
    manuscript = "Mira 把钥匙放在两人之间。钥匙是冷的。"

    response = observed_client.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-metrics-source",
            "Idempotency-Key": "idem-api-metrics-source",
        },
        json={
            "title": "Metrics Source",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": manuscript,
            "version_label": "v1",
        },
    )
    metrics_response = observed_client.get("/metrics")

    assert response.status_code == 201
    assert metrics_response.status_code == 200
    assert "text/plain" in metrics_response.headers["content-type"]
    request_counter = (
        'sextant_api_requests_total{method="POST",'
        'path="/api/projects/{project_id}/sources",status="201"} 1'
    )
    assert request_counter in metrics_response.text
    assert manuscript not in metrics_response.text


def test_metrics_endpoint_exports_action_request_latency_and_error_code_metrics(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    metrics = MetricsRegistry()
    observed_client = TestClient(
        create_app(
            lambda: SqlAlchemyUnitOfWork(session),
            object_store=object_store,
            metrics=metrics,
        )
    )
    actor_intent = "Mira 现在知道钥匙的来源吗？"

    submitted = observed_client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-metrics-action",
            "Idempotency-Key": "idem-api-metrics-action",
        },
        json={
            "trigger": "natural_language",
            "action_type": "ask_memory",
            "target": None,
            "constraints": {"subject_ref": {"type": "character", "id": "mira"}},
            "expected_output": "memory_answer",
            "actor_intent": actor_intent,
        },
    )
    failed = observed_client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-metrics-action-error",
            "Idempotency-Key": "idem-api-metrics-action-error",
        },
        json={
            "trigger": "natural_language",
            "action_type": "unsupported_metric_probe",
            "target": None,
            "constraints": {},
            "expected_output": "memory_answer",
            "actor_intent": actor_intent,
        },
    )

    metrics_response = observed_client.get("/metrics")

    assert submitted.status_code == 201
    assert failed.status_code == 400
    assert metrics_response.status_code == 200
    assert (
        'sextant_action_request_latency_ms_count{action_type="ask_memory",'
        'status="success",trigger="natural_language"} 1'
    ) in metrics_response.text
    assert (
        'sextant_application_errors_total{code="unsupported_action_type",'
        'path="/api/projects/{project_id}/action-requests",status="400"} 1'
    ) in metrics_response.text
    assert actor_intent not in metrics_response.text


def test_create_source_and_version_endpoints_store_version_text(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)

    source_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-create",
            "Idempotency-Key": "idem-source-create",
        },
        json={
            "title": "作者笔记",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": "Mira 讨厌冷钥匙。",
            "version_label": "notes-v1",
        },
    )

    assert source_response.status_code == 201
    created = source_response.json()
    source_id = UUID(created["source_id"])
    version_id = UUID(created["version_id"])

    source_detail = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{source_id}/versions/{version_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    assert source_detail.status_code == 200
    assert source_detail.json()["text"] == "Mira 讨厌冷钥匙。"

    version_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{source_id}/versions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-version-create",
            "Idempotency-Key": "idem-source-version-create",
        },
        json={
            "text": "Mira 讨厌冷钥匙，但会拿起来。",
            "version_label": "notes-v2",
            "supersedes_version_id": str(version_id),
        },
    )

    assert version_response.status_code == 201
    next_version_id = UUID(version_response.json()["version_id"])
    next_detail = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{source_id}/versions/{next_version_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    assert next_detail.json()["text"] == "Mira 讨厌冷钥匙，但会拿起来。"
    next_version = session.get(SourceVersion, next_version_id)
    assert next_version is not None
    assert next_version.raw_text_ref is not None
    assert object_store.get_text(next_version.raw_text_ref) == "Mira 讨厌冷钥匙，但会拿起来。"

    versions_response = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{source_id}/versions",
        headers={"X-Actor-Id": str(actor_id)},
    )
    assert versions_response.status_code == 200
    versions = versions_response.json()["items"]
    assert [item["version_label"] for item in versions] == ["notes-v2", "notes-v1"]
    assert versions[0]["version_id"] == str(next_version_id)
    assert versions[0]["supersedes_version_id"] == str(version_id)
    assert versions[1]["version_id"] == str(version_id)
    assert versions[1]["supersedes_version_id"] is None


def test_restore_source_version_creates_evidence_delta_and_writeback_job(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    v1_text = "Mira hated the cold key."
    v1_ref = object_store.put_text("raw/restore-v1.txt", v1_text)
    raw_source.raw_text_ref = v1_ref
    version.raw_text_ref = v1_ref
    version.raw_hash = sha256(v1_text.encode("utf-8")).hexdigest()
    version.version_label = "v1"
    v2_text = "Mira picked up the cold key."
    v2_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-restore-v2",
            "Idempotency-Key": "idem-source-restore-v2",
        },
        json={
            "text": v2_text,
            "version_label": "v2",
            "supersedes_version_id": str(version.id),
        },
    )
    assert v2_response.status_code == 201
    v2_id = UUID(v2_response.json()["version_id"])

    restore_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/restore",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-restore-v1",
            "Idempotency-Key": "idem-source-restore-v1",
        },
        json={"author_note": "回滚到第一版。"},
    )

    assert restore_response.status_code == 201
    body = restore_response.json()
    restored_version_id = UUID(body["new_version_id"])
    assert body["restored_from_version_id"] == str(version.id)
    restored_detail = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{restored_version_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    assert restored_detail.status_code == 200
    assert restored_detail.json()["text"] == v1_text
    restored_version = session.get(SourceVersion, restored_version_id)
    assert restored_version is not None
    assert restored_version.supersedes_version_id == v2_id
    source_delta = session.get(SourceDeltaRecord, UUID(body["source_delta_id"]))
    assert source_delta is not None
    assert source_delta.previous_version_id == v2_id
    assert source_delta.new_version_id == restored_version_id
    assert source_delta.delta_kind == "replace"
    assert source_delta.range_start == 0
    assert source_delta.range_end == len(v2_text)
    assert source_delta.provenance["restored_from_version_id"] == str(version.id)
    assert session.get(JobRecord, UUID(body["memory_writeback_job_id"])).status == "queued"


def test_source_restore_error_matrix_rejects_current_version_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    version_text = "Mira remains at the current door."
    text_ref = object_store.put_text("raw/current-restore-v1.txt", version_text)
    raw_source.raw_text_ref = text_ref
    version.raw_text_ref = text_ref
    version.raw_hash = sha256(version_text.encode("utf-8")).hexdigest()
    session.commit()
    delta_count = session.query(SourceDeltaRecord).count()
    job_count = session.query(JobRecord).count()

    response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/restore",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-current-restore",
            "Idempotency-Key": "idem-api-current-restore",
        },
        json={"author_note": "当前版本不需要恢复。"},
    )

    _assert_api_error_response(
        response,
        status_code=409,
        code="source_version_already_current",
    )
    assert session.query(SourceDeltaRecord).count() == delta_count
    assert session.query(JobRecord).count() == job_count
    assert session.query(IdempotencyRecord).count() == 0


def test_source_version_diff_endpoint_returns_real_line_changes_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    v1_text = "第一行\n第二行\n第三行"
    v1_ref = object_store.put_text("raw/diff-v1.txt", v1_text)
    raw_source.raw_text_ref = v1_ref
    version.raw_text_ref = v1_ref
    version.raw_hash = sha256(v1_text.encode("utf-8")).hexdigest()
    version.version_label = "v1"
    v2_text = "第一行\n第二行改\n第三行\n新增行"
    v2_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-diff-v2",
            "Idempotency-Key": "idem-source-diff-v2",
        },
        json={
            "text": v2_text,
            "version_label": "v2",
            "supersedes_version_id": str(version.id),
        },
    )
    assert v2_response.status_code == 201
    v2_id = UUID(v2_response.json()["version_id"])
    source_delta_count = session.query(SourceDeltaRecord).count()
    job_count = session.query(JobRecord).count()

    diff_response = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/diff/{v2_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert diff_response.status_code == 200
    body = diff_response.json()
    assert body["source_id"] == str(raw_source.id)
    assert body["base_version_id"] == str(version.id)
    assert body["compare_version_id"] == str(v2_id)
    assert body["base_version_label"] == "v1"
    assert body["compare_version_label"] == "v2"
    assert body["summary"] == {"insertions": 2, "deletions": 1, "changed": True}
    lines = [line for hunk in body["hunks"] for line in hunk["lines"]]
    assert {"kind": "delete", "old_line": 2, "new_line": None, "text": "第二行"} in lines
    assert {"kind": "insert", "old_line": None, "new_line": 2, "text": "第二行改"} in lines
    assert {"kind": "insert", "old_line": None, "new_line": 4, "text": "新增行"} in lines
    assert session.query(SourceDeltaRecord).count() == source_delta_count
    assert session.query(JobRecord).count() == job_count


def test_create_source_delta_endpoint_queues_real_writeback(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "旧正文需要替换，后面保留。"
    raw_text_ref = object_store.put_text("raw/source-delta-create.txt", original_text)
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref

    response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-delta-create",
            "Idempotency-Key": "idem-source-delta-create",
        },
        json={
            "delta_kind": "replace",
            "range_start": 0,
            "range_end": 7,
            "base_hash": "hash-v1",
            "submitted_text": "FACT: character:mira | owns | object:lantern-map | low",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"surface": "api"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    delta = session.get(SourceDeltaRecord, UUID(body["source_delta_id"]))
    assert delta is not None
    assert delta.accepted_fragment_id is None
    assert delta.status == "memory_writeback_queued"
    assert object_store.get_text(delta.submitted_text_ref).startswith("FACT:")
    assert delta.new_version_id == UUID(body["new_version_id"])
    new_version = session.get(SourceVersion, delta.new_version_id)
    assert new_version is not None
    assert new_version.supersedes_version_id == version.id
    assert object_store.get_text(new_version.raw_text_ref).startswith("FACT:")


def test_create_source_delta_endpoint_rejects_superseded_previous_version_without_side_effects(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_text_ref = object_store.put_text(
        "raw/source-delta-stale-create-v1.txt",
        "Mira opened the archive.",
    )
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    session.commit()

    concurrent_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-source-edit-concurrent",
            "Idempotency-Key": "idem-api-source-edit-concurrent",
        },
        json={
            "text": "Mira opened the archive.\nA concurrent line exists.",
            "version_label": "v2",
            "supersedes_version_id": str(version.id),
        },
    )
    assert concurrent_response.status_code == 201
    latest_version_id = concurrent_response.json()["version_id"]
    delta_count = session.query(SourceDeltaRecord).count()
    job_count = session.query(JobRecord).count()

    stale_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-source-edit-stale",
            "Idempotency-Key": "idem-api-source-edit-stale",
        },
        json={
            "delta_kind": "insert",
            "range_start": 0,
            "range_end": 0,
            "base_hash": version.raw_hash,
            "submitted_text": "Stale edit.",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"surface": "api"},
        },
    )

    assert stale_response.status_code == 409
    body = stale_response.json()
    assert body["error"]["code"] == "stale_source_version"
    assert body["error"]["details"]["previous_version_id"] == str(version.id)
    assert body["error"]["details"]["latest_version_id"] == latest_version_id
    assert session.query(SourceDeltaRecord).count() == delta_count
    assert session.query(JobRecord).count() == job_count


def test_project_source_delta_endpoint_queues_writeback_and_rejects_stale_version(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_text_ref = object_store.put_text(
        "raw/project-source-delta-create-v1.txt",
        "Mira opened the archive.",
    )
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    session.commit()

    response = client_with_objects.post(
        f"/api/projects/{project.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-project-source-delta-create",
            "Idempotency-Key": "idem-project-source-delta-create",
        },
        json={
            "source_id": str(raw_source.id),
            "previous_version_id": str(version.id),
            "delta_kind": "insert",
            "range_start": len("Mira opened the archive."),
            "range_end": len("Mira opened the archive."),
            "base_hash": version.raw_hash,
            "submitted_text": "\nMira told Kestrel about the Harbor Code.",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"surface": "project-source-delta-api"},
        },
    )

    assert response.status_code == 201
    body = response.json()
    delta = session.get(SourceDeltaRecord, UUID(body["source_delta_id"]))
    assert delta is not None
    assert delta.source_id == raw_source.id
    assert delta.previous_version_id == version.id
    assert delta.status == "memory_writeback_queued"
    assert object_store.get_text(delta.submitted_text_ref).startswith("\nMira told")
    new_version = session.get(SourceVersion, UUID(body["new_version_id"]))
    assert new_version is not None
    assert new_version.supersedes_version_id == version.id
    assert object_store.get_text(new_version.raw_text_ref).endswith("Harbor Code.")
    assert session.get(JobRecord, UUID(body["memory_writeback_job_id"])) is not None

    delta_count = session.query(SourceDeltaRecord).count()
    job_count = session.query(JobRecord).count()
    stale_response = client_with_objects.post(
        f"/api/projects/{project.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-project-source-delta-stale",
            "Idempotency-Key": "idem-project-source-delta-stale",
        },
        json={
            "source_id": str(raw_source.id),
            "previous_version_id": str(version.id),
            "delta_kind": "insert",
            "range_start": 0,
            "range_end": 0,
            "base_hash": version.raw_hash,
            "submitted_text": "Stale project-level edit.",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"surface": "project-source-delta-api"},
        },
    )

    assert stale_response.status_code == 409
    stale_body = stale_response.json()
    assert stale_body["error"]["code"] == "stale_source_version"
    assert stale_body["error"]["details"]["previous_version_id"] == str(version.id)
    assert stale_body["error"]["details"]["latest_version_id"] == body["new_version_id"]
    assert session.query(SourceDeltaRecord).count() == delta_count
    assert session.query(JobRecord).count() == job_count


def test_candidate_accept_endpoint_maps_stale_base(client: TestClient, session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    version.raw_hash = "newer-hash"
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 0, "end": 12}},
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
        affected_range={"start": 0, "end": 12},
        base_hash="hash-v1",
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/candidates/{candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-3",
            "Idempotency-Key": "idem-api-3",
        },
        json={
            "accepted_text_ref": "object://accepted/stale",
            "accept_mode": "partial",
            "target_source_id": str(raw_source.id),
            "target_version_id": str(version.id),
            "insert_or_replace_range": {"start": 0, "end": 12},
            "base_hash": "hash-v1",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "stale_source_version"


def test_candidate_accept_error_matrix_rejects_invalid_offerability_without_side_effects(
    client: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    other_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Target",
        ownership_status="owned",
        raw_text_ref="object://raw/other-target",
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 0, "end": 12}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    blocked_candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/blocked",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="blocked",
    )
    archived_candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/archived",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="archived",
    )
    offered_candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref="object://candidate/offered",
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all(
        [other_source, action_request, blocked_candidate, archived_candidate, offered_candidate]
    )
    session.commit()

    def accept_payload(
        candidate: AgentDraftCandidateRecord, *, target_source_id: UUID
    ) -> dict[str, object]:
        return {
            "accepted_text_ref": "object://accepted/error-matrix",
            "accept_mode": "partial",
            "target_source_id": str(target_source_id),
            "target_version_id": str(version.id),
            "insert_or_replace_range": {"start": 0, "end": 12},
            "base_hash": version.raw_hash,
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": True,
        }

    blocked_response = client.post(
        f"/api/projects/{project.id}/candidates/{blocked_candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-candidate-blocked",
            "Idempotency-Key": "idem-api-candidate-blocked",
        },
        json=accept_payload(blocked_candidate, target_source_id=raw_source.id),
    )
    archived_response = client.post(
        f"/api/projects/{project.id}/candidates/{archived_candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-candidate-archived",
            "Idempotency-Key": "idem-api-candidate-archived",
        },
        json=accept_payload(archived_candidate, target_source_id=raw_source.id),
    )
    target_mismatch_response = client.post(
        f"/api/projects/{project.id}/candidates/{offered_candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-candidate-target-mismatch",
            "Idempotency-Key": "idem-api-candidate-target-mismatch",
        },
        json=accept_payload(offered_candidate, target_source_id=other_source.id),
    )
    invalid_override_response = client.post(
        f"/api/projects/{project.id}/candidates/{offered_candidate.id}/override-block",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-candidate-invalid-override",
            "Idempotency-Key": "idem-api-candidate-invalid-override",
        },
        json={"override_reason": "不是 blocked 的候选不能越过。"},
    )

    _assert_api_error_response(
        blocked_response,
        status_code=409,
        code="blocked_without_override",
    )
    _assert_api_error_response(
        archived_response,
        status_code=409,
        code="candidate_not_offerable",
    )
    _assert_api_error_response(
        target_mismatch_response,
        status_code=400,
        code="invalid_target_range",
    )
    _assert_api_error_response(
        invalid_override_response,
        status_code=409,
        code="invalid_state_transition",
    )
    assert session.query(AcceptedFragmentRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(JobRecord).count() == 0
    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0


def test_candidate_operation_endpoints_do_not_create_memory(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "旧正文第一句。\n第二句保留。"
    raw_text_ref = object_store.put_text("raw/accept-text-source.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 0, "end": 6}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    blocked_candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref=object_store.put_text("candidates/blocked.txt", "候选句。"),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="blocked",
    )
    offered_candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref=object_store.put_text("candidates/offered.txt", "旧候选。"),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, blocked_candidate, offered_candidate])
    session.commit()

    override = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{blocked_candidate.id}/override-block",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-candidate-override",
            "Idempotency-Key": "idem-candidate-override",
        },
        json={"override_reason": "作者确认这是有意越界。"},
    )
    explained = client_with_objects.get(
        f"/api/projects/{project.id}/candidates/{blocked_candidate.id}/explain",
        headers={"X-Actor-Id": str(actor_id)},
    )
    post_explained = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{blocked_candidate.id}/explain",
        headers={"X-Actor-Id": str(actor_id)},
    )
    revise = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{offered_candidate.id}/revise",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-candidate-revise",
            "Idempotency-Key": "idem-candidate-revise",
        },
        json={"revised_text": "新候选。", "author_note": "改弱一点。"},
    )
    reject = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{blocked_candidate.id}/reject",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-candidate-reject",
            "Idempotency-Key": "idem-candidate-reject",
        },
        json={"author_note": "不用这个方向。"},
    )

    assert override.status_code == 200
    assert override.json()["status"] == "offered_to_author"
    assert override.json()["override_reason"] == "作者确认这是有意越界。"
    assert explained.status_code == 200
    assert explained.json()["override_reason"] == "作者确认这是有意越界。"
    assert post_explained.status_code == 200
    assert post_explained.json()["override_reason"] == "作者确认这是有意越界。"
    assert revise.status_code == 200
    replacement_id = UUID(revise.json()["replacement_candidate_id"])
    replacement = session.get(AgentDraftCandidateRecord, replacement_id)
    assert replacement is not None
    assert replacement.status == "offered_to_author"
    assert object_store.get_text(replacement.candidate_text_ref) == "新候选。"
    assert reject.status_code == 200
    assert reject.json()["status"] == "archived"
    assert session.get(AgentDraftCandidateRecord, blocked_candidate.id).author_action == "reject"
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(AcceptedFragmentRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_source_list_endpoint_supports_search(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    note = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="author_notes",
        source_scope="author_note",
        title="角色备忘",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/notes.txt", "Mira 不确定钥匙来源。"),
        created_by=actor_id,
    )
    note_version = SourceVersion(
        id=uuid4(),
        source_id=note.id,
        version_label="v1",
        raw_hash="hash-note",
        raw_text_ref=note.raw_text_ref,
    )
    session.add_all([note, note_version])
    session.commit()

    all_sources = client_with_objects.get(
        f"/api/projects/{project.id}/sources",
        headers={"X-Actor-Id": str(actor_id)},
    )
    searched = client_with_objects.get(
        f"/api/projects/{project.id}/sources?query=角色",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert all_sources.status_code == 200
    assert len(all_sources.json()["items"]) == 2
    assert searched.status_code == 200
    assert searched.json()["items"][0]["source_id"] == str(note.id)
    assert searched.json()["items"][0]["latest_version_id"] == str(note_version.id)
    assert searched.json()["items"][0]["version_count"] == 1
    assert any(item["latest_version_id"] == str(version.id) for item in all_sources.json()["items"])


def test_source_summary_reports_chain_latest_when_versions_share_timestamp(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    shared_created_at = datetime(2026, 1, 1, 9, 1, tzinfo=UTC)
    second_text = "Mira opened the west archive door."
    third_text = "Mira opened the west archive door and marked the empty map tube."
    second_version = SourceVersion(
        id=UUID("10000000-0000-4000-8000-000000000002"),
        source_id=raw_source.id,
        version_label="v2",
        raw_hash=sha256(second_text.encode("utf-8")).hexdigest(),
        raw_text_ref=object_store.put_text("raw/source-chain-same-second-v2.txt", second_text),
        supersedes_version_id=version.id,
    )
    third_version = SourceVersion(
        id=UUID("00000000-0000-4000-8000-000000000003"),
        source_id=raw_source.id,
        version_label="v3",
        raw_hash=sha256(third_text.encode("utf-8")).hexdigest(),
        raw_text_ref=object_store.put_text("raw/source-chain-same-second-v3.txt", third_text),
        supersedes_version_id=second_version.id,
    )
    second_version.created_at = shared_created_at
    third_version.created_at = shared_created_at
    session.add_all([second_version, third_version])
    session.commit()

    list_response = client_with_objects.get(
        f"/api/projects/{project.id}/sources",
        headers={"X-Actor-Id": str(actor_id)},
    )
    detail_response = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert list_response.status_code == 200
    listed_source = next(
        item for item in list_response.json()["items"] if item["source_id"] == str(raw_source.id)
    )
    assert listed_source["latest_version_id"] == str(third_version.id)
    assert listed_source["latest_version_label"] == "v3"
    assert listed_source["latest_raw_hash"] == third_version.raw_hash
    assert listed_source["version_count"] == 3
    assert detail_response.status_code == 200
    assert detail_response.json()["latest_version_id"] == str(third_version.id)


def test_source_create_endpoint_queues_imported_source_delta_writeback(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)

    response = client_with_objects.post(
        f"/api/projects/{project.id}/sources",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-import-writeback",
            "Idempotency-Key": "idem-source-import-writeback",
        },
        json={
            "title": "角色备忘",
            "source_type": "author_notes",
            "source_scope": "author_note",
            "ownership_status": "owned",
            "text": "FACT: character:mira | owns | object:lantern-map | low",
            "version_label": "v1",
        },
    )

    assert response.status_code == 201
    body = response.json()
    source_delta_id = UUID(body["source_delta_id"])
    job_id = UUID(body["memory_writeback_job_id"])
    delta = session.get(SourceDeltaRecord, source_delta_id)
    assert delta is not None
    assert delta.source_id == UUID(body["source_id"])
    assert delta.previous_version_id is None
    assert delta.new_version_id == UUID(body["version_id"])
    assert object_store.get_text(delta.submitted_text_ref) == (
        "FACT: character:mira | owns | object:lantern-map | low"
    )
    job = session.get(JobRecord, job_id)
    assert job is not None
    assert job.status == "queued"
    assert job.payload["source_delta_id"] == str(source_delta_id)

    assert drain_pipeline_jobs(
        session,
        object_store,
        worker_id="source-import-worker",
    )
    assert session.get(SourceDeltaRecord, source_delta_id).status == "memory_writeback_completed"
    spans = session.query(SourceSpan).filter_by(source_id=UUID(body["source_id"])).all()
    assert any(
        span.text_preview == "FACT: character:mira | owns | object:lantern-map | low"
        and span.scene_id is None
        for span in spans
    )
    assert any(span.scene_id is not None for span in spans)
    assert session.query(FactAssertionRecord).filter_by(project_id=project.id).count() == 1


def test_source_archive_endpoint_preserves_evidence_and_hides_default_list(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_source.raw_text_ref = object_store.put_text("raw/chapter-3.txt", "第一段。")
    version.raw_text_ref = raw_source.raw_text_ref
    session.commit()

    response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/archive",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-source-archive",
            "Idempotency-Key": "idem-source-archive",
        },
        json={"author_note": "作者不再在当前项目列表中使用。"},
    )
    default_list = client_with_objects.get(
        f"/api/projects/{project.id}/sources",
        headers={"X-Actor-Id": str(actor_id)},
    )
    archived_list = client_with_objects.get(
        f"/api/projects/{project.id}/sources?include_archived=true",
        headers={"X-Actor-Id": str(actor_id)},
    )
    source_detail = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == str(raw_source.id)
    assert body["status"] == "archived"
    assert body["archived_by"] == str(actor_id)
    assert body["archived_at"]
    assert default_list.json()["items"] == []
    assert archived_list.json()["items"][0]["source_id"] == str(raw_source.id)
    assert archived_list.json()["items"][0]["is_archived"] is True
    assert source_detail.status_code == 200
    assert source_detail.json()["text"] == "第一段。"
    assert session.get(RawSource, raw_source.id).archived_at is not None


def test_candidate_accept_endpoint_stores_browser_text_before_source_delta(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "旧事实占位文本。"
    raw_text_ref = object_store.put_text("raw/preview-accept-source.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 0, "end": 4}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_current_page",
        candidate_text_ref=object_store.put_text("candidates/accept-text.txt", "候选句。"),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 6},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()

    response = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-accept-text",
            "Idempotency-Key": "idem-api-accept-text",
        },
        json={
            "accepted_text": "候选句。",
            "accept_mode": "partial",
            "target_source_id": str(raw_source.id),
            "target_version_id": str(version.id),
            "insert_or_replace_range": {"start": 0, "end": 6},
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": True,
        },
    )

    assert response.status_code == 200
    source_delta_id = UUID(response.json()["source_delta_id"])
    delta = session.get(SourceDeltaRecord, source_delta_id)
    assert delta is not None
    assert object_store.get_text(delta.submitted_text_ref) == "候选句。"
    assert delta.new_version_id == UUID(response.json()["new_version_id"])
    new_version = session.get(SourceVersion, delta.new_version_id)
    assert new_version is not None
    assert object_store.get_text(new_version.raw_text_ref) == "候选句。" + original_text[6:]


def test_source_version_endpoint_returns_real_source_text(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_source.raw_text_ref = object_store.put_text("raw/chapter-3.txt", "第一段。\n第二段。")
    version.raw_hash = "hash-source-text"
    session.commit()

    response = client_with_objects.get(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "第一段。\n第二段。"
    assert body["raw_hash"] == "hash-source-text"


def test_memory_writeback_preview_endpoint_reports_evidence_chain(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    original_text = "旧事实占位文本。"
    raw_text_ref = object_store.put_text("raw/preview-accept-source.txt", original_text)
    raw_hash = sha256(original_text.encode("utf-8")).hexdigest()
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    version.raw_hash = raw_hash
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="继续",
        trigger="toolbar",
        action_type="rewrite_span",
        target={"range": {"start": 0, "end": 4}},
        constraints={},
        expected_output="draft_candidate",
        status="submitted",
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="rewrite_span",
        candidate_text_ref=object_store.put_text("candidates/fact.txt", "候选句。"),
        target_source_id=raw_source.id,
        target_version_id=version.id,
        affected_range={"start": 0, "end": 4},
        base_hash=raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="offered_to_author",
    )
    session.add_all([action_request, candidate])
    session.commit()

    accept_response = client_with_objects.post(
        f"/api/projects/{project.id}/candidates/{candidate.id}/accept",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-accept",
            "Idempotency-Key": "idem-api-preview-accept",
        },
        json={
            "accepted_text": "FACT: character:mira | owns | object:lantern-map | low",
            "accept_mode": "partial",
            "target_source_id": str(raw_source.id),
            "target_version_id": str(version.id),
            "insert_or_replace_range": {"start": 0, "end": 4},
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "author_edited": True,
        },
    )
    assert accept_response.status_code == 200
    source_delta_id = UUID(accept_response.json()["source_delta_id"])
    job_id = UUID(accept_response.json()["memory_writeback_job_id"])

    assert drain_pipeline_jobs(
        session,
        object_store,
        worker_id="preview-test-worker",
    )

    response = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta_id}/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_delta_status"] == "memory_writeback_completed"
    assert body["job"]["id"] == str(job_id)
    assert body["job"]["status"] == "succeeded"
    assert len(body["source_spans"]) == 1
    assert len(body["evidence_log_entries"]) == 1
    assert body["fact_assertions"][0]["fact_status"] == "canon"
    assert len(body["memory_pages"]) == 1
    assert len(body["graph_edges"]) == 1
    assert (
        session.query(SourceSpan)
        .filter_by(text_preview="FACT: character:mira | owns | object:lantern-map | low")
        .count()
        == 1
    )
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(MemoryPage).count() == 1


def test_memory_page_list_and_detail_endpoints_return_evidence_refs(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    source_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira appears with the lantern map.",
        slug="memory-page-evidence-ref",
    )
    source_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=34,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/memory-page-evidence-ref",
        submitted_text_search="Mira appears with the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    current_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={"facts": [{"predicate": "owns", "object": "lantern-map"}]},
        appearance_log=[{"source_span_id": str(source_span.id), "summary": "Mira appears."}],
        event_log=[],
        relationships=[],
        open_threads=[{"id": "thread-1", "summary": "Who gave Mira the map?"}],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(source_delta.id)},
            {"type": "source_span", "id": str(source_span.id)},
        ],
        canon_status="current",
        memory_depth="standard",
    )
    stale_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="location",
        target_ref={"type": "location", "id": "west-archive"},
        title="West Archive",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[{"source_delta_id": str(source_delta.id), "decision": "correct"}],
        source_refs=[{"type": "source_delta", "id": str(source_delta.id)}],
        canon_status="stale",
        memory_depth="light",
    )
    session.add_all([source_delta, current_page, stale_page])
    session.commit()

    list_response = client.get(
        f"/api/projects/{project.id}/memory/pages?canon_status=current&limit=10",
        headers={"X-Actor-Id": str(actor_id)},
    )
    detail_response = client.get(
        f"/api/projects/{project.id}/memory/pages/{current_page.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    forbidden_response = client.get(
        f"/api/projects/{project.id}/memory/pages",
        headers={"X-Actor-Id": str(uuid4())},
    )

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert [item["id"] for item in list_body["items"]] == [str(current_page.id)]
    assert list_body["items"][0]["title"] == "Mira"
    assert list_body["items"][0]["source_refs"] == current_page.source_refs
    assert list_body["items"][0]["open_thread_count"] == 1
    assert list_body["items"][0]["contradiction_count"] == 0

    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["current_canon"]["facts"][0]["predicate"] == "owns"
    assert detail_body["appearance_log"][0]["source_span_id"] == str(source_span.id)
    assert detail_body["open_threads"][0]["id"] == "thread-1"
    assert detail_body["source_refs"] == current_page.source_refs

    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error"]["code"] == "permission_denied"


def test_memory_page_list_and_detail_filter_invalid_source_refs(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira records the tide key.",
        slug="memory-page-valid-source-ref",
    )
    valid_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=24,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/memory-page-valid-source-ref",
        submitted_text_search="Mira records the tide key.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="An unrelated project records another key.",
        slug="memory-page-cross-project-source-ref",
    )
    cross_project_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=other_project.id,
        source_id=other_source.id,
        previous_version_id=other_version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=40,
        base_hash=other_version.raw_hash,
        submitted_text_ref="object://delta/memory-page-cross-project-source-ref",
        submitted_text_search="An unrelated project records another key.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(valid_delta.id)},
            {"type": "source_delta", "id": str(cross_project_delta.id)},
            {"type": "source_delta", "id": "not-a-source-delta-id"},
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([valid_delta, cross_project_delta, page])
    session.commit()

    list_response = client.get(
        f"/api/projects/{project.id}/memory/pages?canon_status=current&limit=10",
        headers={"X-Actor-Id": str(actor_id)},
    )
    detail_response = client.get(
        f"/api/projects/{project.id}/memory/pages/{page.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    expected_refs = [
        {"type": "source_delta", "id": str(valid_delta.id)},
        {"type": "source_span", "id": str(valid_span.id)},
    ]
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()["items"][0]["source_refs"] == expected_refs
    assert detail_response.json()["source_refs"] == expected_refs
    assert str(cross_project_delta.id) not in json.dumps(detail_response.json(), sort_keys=True)
    assert str(cross_project_span.id) not in json.dumps(detail_response.json(), sort_keys=True)


def test_memory_writeback_preview_filters_embedded_memory_page_source_refs(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira keeps a verified archive note.",
        slug="preview-valid-memory-page-source-ref",
    )
    source_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=36,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/preview-valid-memory-page-source-ref",
        submitted_text_search="Mira keeps a verified archive note.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="An unrelated project keeps a separate note.",
        slug="preview-cross-project-memory-page-source-ref",
    )
    cross_project_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=other_project.id,
        source_id=other_source.id,
        previous_version_id=other_version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=41,
        base_hash=other_version.raw_hash,
        submitted_text_ref="object://delta/preview-cross-project-memory-page-source-ref",
        submitted_text_search="An unrelated project keeps a separate note.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_delta", "id": str(source_delta.id)},
            {"type": "source_delta", "id": str(cross_project_delta.id)},
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
        ],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([source_delta, cross_project_delta, page])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["memory_pages"][0]["source_refs"] == [
        {"type": "source_delta", "id": str(source_delta.id)},
        {"type": "source_span", "id": str(valid_span.id)},
    ]
    assert str(cross_project_delta.id) not in json.dumps(body, sort_keys=True)
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)


def test_memory_page_detail_exposes_character_knowledge_state(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/chapter-3.md",
        raw_offset_map_ref="object://processed/chapter-3.offsets.json",
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
        end_offset=19,
        raw_start_offset=0,
        raw_end_offset=19,
        text_preview="Mira knows the code.",
        speaker_entity_id=None,
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    active_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    superseded_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "old-map", "label": "Old Map"},
        evidence_span_id=span.id,
        certainty="suspected",
        hidden_from=[],
        status="superseded",
    )
    session.add_all([view, span, mira, page, active_knowledge, superseded_knowledge])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/memory/pages/{page.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_state"] == [
        {
            "character_id": str(mira.id),
            "knows_ref": {"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
            "learned_in_scene_id": None,
            "evidence_span_id": str(span.id),
            "certainty": "known",
            "hidden_from": [],
            "status": "active",
        }
    ]
    assert body["current_canon"] == {"facts": []}


def test_memory_page_detail_ignores_character_knowledge_with_cross_project_evidence(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira knows the harbor code.",
        slug="mira-valid-knowledge",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Mira learns an unrelated cross-project secret.",
        slug="mira-cross-project-knowledge",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(valid_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    valid_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        evidence_span_id=valid_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    cross_project_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "secret", "id": "other-secret", "label": "Other Secret"},
        evidence_span_id=cross_project_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all([mira, page, valid_knowledge, cross_project_knowledge])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/memory/pages/{page.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["knowledge_state"] == [
        {
            "character_id": str(mira.id),
            "knows_ref": {"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
            "learned_in_scene_id": None,
            "evidence_span_id": str(valid_span.id),
            "certainty": "known",
            "hidden_from": [],
            "status": "active",
        }
    ]
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)
    assert other_project.id != project.id


def test_graph_projection_edge_list_endpoint_is_read_only_and_filterable(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    owns_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira owns the lantern map.",
        slug="graph-list-owns",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="memory_graph",
        source_state_hash="graph-state-v1",
        created_edge_count=2,
        created_at=datetime.now(UTC),
    )
    canon_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": "fact-owns"},
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(owns_span.id)}],
        created_at=datetime.now(UTC),
    )
    disputed_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": "fact-location"},
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        relation="located_in",
        target_ref={"type": "location", "id": "west-archive", "label": "West Archive"},
        edge_status="disputed",
        evidence_refs=[{"type": "source_span", "id": str(owns_span.id)}],
        created_at=datetime.now(UTC),
    )
    session.add_all([run, canon_edge, disputed_edge])
    session.commit()

    facts_before = session.query(FactAssertionRecord).count()
    response = client.get(
        f"/api/projects/{project.id}/graph/edges?q=archive&edge_status=disputed&limit=10",
        headers={"X-Actor-Id": str(actor_id)},
    )
    forbidden_response = client.get(
        f"/api/projects/{project.id}/graph/edges",
        headers={"X-Actor-Id": str(uuid4())},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(disputed_edge.id)]
    assert body["items"][0]["relation"] == "located_in"
    assert body["items"][0]["edge_status"] == "disputed"
    assert body["items"][0]["subject_ref"]["label"] == "Mira"
    assert body["items"][0]["target_ref"]["label"] == "West Archive"
    assert body["items"][0]["evidence_refs"] == disputed_edge.evidence_refs
    assert session.query(FactAssertionRecord).count() == facts_before

    assert forbidden_response.status_code == 403
    assert forbidden_response.json()["error"]["code"] == "permission_denied"


def test_graph_projection_edge_list_filters_invalid_evidence_refs(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira stores the lantern map in the archive.",
        slug="graph-valid-evidence-ref",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Another project stores another map.",
        slug="graph-cross-project-evidence-ref",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="memory_graph",
        source_state_hash="graph-state-filter",
        created_edge_count=2,
        created_at=datetime.now(UTC),
    )
    mixed_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": "fact-owns"},
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        edge_status="canon",
        evidence_refs=[
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        created_at=datetime.now(UTC),
    )
    invalid_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": "fact-invalid"},
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        relation="knows",
        target_ref={"type": "secret", "id": "invalid", "label": "Invalid"},
        edge_status="canon",
        evidence_refs=[
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        created_at=datetime.now(UTC),
    )
    session.add_all([run, mixed_edge, invalid_edge])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/graph/edges?limit=10",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(mixed_edge.id)]
    assert body["items"][0]["evidence_refs"] == [{"type": "source_span", "id": str(valid_span.id)}]
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)


def test_memory_writeback_preview_filters_embedded_graph_edge_evidence_refs(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira stores the lantern map in the archive.",
        slug="preview-graph-valid-evidence-ref",
    )
    source_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=43,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/preview-graph-valid-evidence-ref",
        submitted_text_search="Mira stores the lantern map in the archive.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Another project stores another map.",
        slug="preview-graph-cross-project-evidence-ref",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="memory_graph",
        source_state_hash="graph-state-preview-filter",
        created_edge_count=1,
        created_at=datetime.now(UTC),
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": "fact-owns"},
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        edge_status="canon",
        evidence_refs=[
            {"type": "source_span", "id": str(valid_span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        created_at=datetime.now(UTC),
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:preview-graph-filter",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(valid_span.id)},
    )
    session.add_all([source_delta, run, edge, extraction_audit])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graph_edges"][0]["evidence_refs"] == [
        {"type": "source_span", "id": str(valid_span.id)}
    ]
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)


def test_source_delta_list_and_detail_endpoints_return_submitted_text(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_text_ref = object_store.put_text("raw/delta-read-source.txt", "原始正文。")
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref

    create_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-delta-read",
            "Idempotency-Key": "idem-api-delta-read",
        },
        json={
            "delta_kind": "insert",
            "range_start": 0,
            "range_end": 0,
            "base_hash": "hash-v1",
            "submitted_text": "FACT: character:mira | owns | object:lantern-map | low",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"source": "api-test"},
        },
    )
    assert create_response.status_code == 201
    source_delta_id = UUID(create_response.json()["source_delta_id"])

    list_response = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas",
        headers={"X-Actor-Id": str(actor_id)},
    )
    detail_response = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["items"][0]["id"] == str(source_delta_id)
    assert list_body["items"][0]["submitted_text_preview"].startswith("FACT: character:mira")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["id"] == str(source_delta_id)
    assert detail_body["submitted_text"] == "FACT: character:mira | owns | object:lantern-map | low"
    assert detail_body["job"]["id"] == create_response.json()["memory_writeback_job_id"]


def test_context_pack_readiness_list_endpoint_returns_backend_state(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
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
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=18,
        raw_start_offset=0,
        raw_end_offset=18,
        text_preview="米拉把灯图收进袖中。",
        narration_layer="narrator",
    )
    readiness = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=project.id,
        source_span_id=span.id,
        source_delta_id=None,
        status="pending",
        reason="memory_dependency_changed",
        affected_refs=[{"type": "fact_assertion", "id": "fact-1"}],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    session.add_all([view, span, readiness])
    session.commit()

    response = client_with_objects.get(
        f"/api/projects/{project.id}/context-pack-readiness?status=pending",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "id": str(readiness.id),
            "source_span_id": str(span.id),
            "source_delta_id": None,
            "status": "pending",
            "reason": "memory_dependency_changed",
            "affected_refs": [{"type": "fact_assertion", "id": "fact-1"}],
            "evidence_refs": [{"type": "source_span", "id": str(span.id)}],
        }
    ]


def test_source_delta_list_filters_by_text_kind_and_version(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_text_ref = object_store.put_text("raw/delta-filter-source.txt", "原始正文。")
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    session.commit()

    lantern_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-delta-filter-lantern",
            "Idempotency-Key": "idem-api-delta-filter-lantern",
        },
        json={
            "delta_kind": "insert",
            "range_start": 0,
            "range_end": 0,
            "base_hash": "hash-v1",
            "submitted_text": "米拉记录灯图的新边注。",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"source": "api-test"},
        },
    )
    assert lantern_response.status_code == 201
    latest_version = session.get(SourceVersion, UUID(lantern_response.json()["new_version_id"]))
    assert latest_version is not None
    key_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{latest_version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-delta-filter-key",
            "Idempotency-Key": "idem-api-delta-filter-key",
        },
        json={
            "delta_kind": "replace",
            "range_start": 0,
            "range_end": 2,
            "base_hash": latest_version.raw_hash,
            "submitted_text": "钥匙来源仍未确认。",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"source": "api-test"},
        },
    )
    assert key_response.status_code == 201

    response = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas",
        headers={"X-Actor-Id": str(actor_id)},
        params={
            "query": "灯图",
            "delta_kind": "insert",
            "source_version_id": lantern_response.json()["new_version_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [lantern_response.json()["source_delta_id"]]
    assert body["items"][0]["submitted_text_preview"] == "米拉记录灯图的新边注。"


def test_source_delta_list_uses_indexed_search_and_cursor_pagination(
    client_with_objects: TestClient,
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    raw_text_ref = object_store.put_text("raw/delta-pagination-source.txt", "原始正文。")
    raw_source.raw_text_ref = raw_text_ref
    version.raw_text_ref = raw_text_ref
    session.commit()

    current_version_id = version.id
    current_base_hash = version.raw_hash

    def create_delta(idempotency_key: str, submitted_text: str) -> UUID:
        nonlocal current_base_hash, current_version_id
        response = client_with_objects.post(
            f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{current_version_id}/source-deltas",
            headers={
                "X-Actor-Id": str(actor_id),
                "X-Request-Id": f"req-{idempotency_key}",
                "Idempotency-Key": idempotency_key,
            },
            json={
                "delta_kind": "insert",
                "range_start": 0,
                "range_end": 0,
                "base_hash": current_base_hash,
                "submitted_text": submitted_text,
                "source_type": "draft_manuscript",
                "source_scope": "user_draft",
                "provenance": {"source": "api-test"},
            },
        )
        assert response.status_code == 201
        body = response.json()
        latest_version = session.get(SourceVersion, UUID(body["new_version_id"]))
        assert latest_version is not None
        current_version_id = latest_version.id
        current_base_hash = latest_version.raw_hash
        return UUID(body["source_delta_id"])

    older_match_id = create_delta("idem-api-delta-page-old", "旧灯图线索写入。")
    newer_match_id = create_delta("idem-api-delta-page-new", "新灯图线索写入。")
    newest_non_match_id = create_delta("idem-api-delta-page-missing", "钥匙线索写入。")

    older_match = session.get(SourceDeltaRecord, older_match_id)
    newer_match = session.get(SourceDeltaRecord, newer_match_id)
    newest_non_match = session.get(SourceDeltaRecord, newest_non_match_id)
    assert older_match is not None
    assert newer_match is not None
    assert newest_non_match is not None
    older_match.created_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    newer_match.created_at = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    newest_non_match.created_at = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    newest_non_match.submitted_text_ref = "object://local/source-deltas/missing-nonmatch.txt"
    session.commit()

    first_page = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas",
        headers={"X-Actor-Id": str(actor_id)},
        params={"query": "灯图", "limit": 1},
    )

    assert first_page.status_code == 200
    first_body = first_page.json()
    assert [item["id"] for item in first_body["items"]] == [str(newer_match_id)]
    assert first_body["next_cursor"]

    second_page = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas",
        headers={"X-Actor-Id": str(actor_id)},
        params={"query": "灯图", "limit": 1, "cursor": first_body["next_cursor"]},
    )

    assert second_page.status_code == 200
    second_body = second_page.json()
    assert [item["id"] for item in second_body["items"]] == [str(older_match_id)]
    assert second_body["next_cursor"] is None

    invalid_cursor = client_with_objects.get(
        f"/api/projects/{project.id}/source-deltas",
        headers={"X-Actor-Id": str(actor_id)},
        params={"cursor": "not-a-valid-cursor"},
    )
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json()["error"]["code"] == "schema_validation_failed"


def test_memory_writeback_preview_decision_persists_correction_signal_and_side_effects(
    client_with_objects: TestClient,
    object_store: LocalObjectStore,
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    object_store.put_text("source/chapter-3", "Mira carried the lantern map.")
    raw_source.raw_text_ref = "object://local/source/chapter-3"
    version.raw_text_ref = "object://local/source/chapter-3"
    session.commit()

    accept_response = client_with_objects.post(
        f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-decision-delta",
            "Idempotency-Key": "idem-api-preview-decision-delta",
        },
        json={
            "delta_kind": "insert",
            "range_start": 0,
            "range_end": 0,
            "base_hash": "hash-v1",
            "submitted_text": "FACT: character:mira | owns | object:lantern-map | low",
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "provenance": {"source": "api-test"},
        },
    )
    assert accept_response.status_code == 201
    source_delta_id = UUID(accept_response.json()["source_delta_id"])

    assert drain_pipeline_jobs(
        session,
        object_store,
        worker_id="decision-test-worker",
    )
    fact = session.query(FactAssertionRecord).one()
    edge = session.query(GraphProjectionEdge).one()
    page = session.query(MemoryPage).one()
    assert fact.fact_status == "canon"
    assert edge.edge_status == "canon"
    assert page.canon_status == "current"

    response = client_with_objects.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-decision",
            "Idempotency-Key": "idem-api-preview-decision",
        },
        json={
            "item_ref": {"type": "fact_assertion", "id": str(fact.id)},
            "decision": "correct",
            "author_note": "地图不是拥有关系，是临时携带。",
            "correction": {"predicate": "carries"},
            "replacement_refs": [{"type": "source_delta", "id": str(source_delta_id)}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_delta_id"] == str(source_delta_id)
    assert body["status"] == "recorded"
    assert body["side_effects"]["fact_assertion_status"] == "disputed"
    assert body["side_effects"]["graph_edges_marked_disputed"] == 1
    assert body["side_effects"]["memory_pages"] == "marked_stale"
    assert body["side_effects"]["memory_pages_marked_stale"] == 1
    rewrite_job_ids = body["side_effects"]["memory_page_rewrite_job_ids"]
    assert len(rewrite_job_ids) == 1
    rewrite_job = session.get(JobRecord, UUID(rewrite_job_ids[0]))
    assert rewrite_job is not None
    assert rewrite_job.status == "queued"
    assert rewrite_job.job_type == "rewrite_memory_page"
    assert rewrite_job.payload["memory_page_id"] == str(page.id)
    assert rewrite_job.payload["source_delta_id"] == str(source_delta_id)
    assert rewrite_job.run_after is not None
    assert session.get(FactAssertionRecord, fact.id).fact_status == "disputed"
    assert session.get(GraphProjectionEdge, edge.id).edge_status == "disputed"
    span = session.get(SourceSpan, UUID(fact.evidence_span_ids[0]))
    assert span is not None
    stale_readiness = (
        session.query(ContextPackReadinessRecord)
        .filter_by(
            project_id=project.id,
            source_span_id=span.id,
            reason="review_dependency_changed",
        )
        .one()
    )
    assert stale_readiness.status == "stale"
    assert stale_readiness.source_delta_id == source_delta_id
    assert {"type": "memory_writeback_decision", "id": body["decision_id"]} in (
        stale_readiness.affected_refs
    )
    assert {"type": "fact_assertion", "id": str(fact.id)} in stale_readiness.affected_refs
    assert stale_readiness.evidence_refs == [{"type": "source_span", "id": str(span.id)}]
    stale_page = session.get(MemoryPage, page.id)
    assert stale_page.canon_status == "stale"
    assert stale_page.contradictions[-1]["decision"] == "correct"
    assert stale_page.contradictions[-1]["item_ref"] == {
        "type": "fact_assertion",
        "id": str(fact.id),
    }
    decision = session.query(MemoryWritebackDecisionRecord).one()
    assert decision.item_ref == {"type": "fact_assertion", "id": str(fact.id)}
    assert decision.correction == {"predicate": "carries"}
    assert decision.replacement_refs == [{"type": "source_delta", "id": str(source_delta_id)}]
    audit = (
        session.query(AuditEvent).filter_by(event_type="memory_writeback_preview.decision").one()
    )
    assert audit.decision["replacement_refs"] == [
        {"type": "source_delta", "id": str(source_delta_id)}
    ]


def test_memory_writeback_preview_fact_accept_promotes_canon_and_resolves_review(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/fact-accept.md",
        raw_offset_map_ref="object://processed/fact-accept.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/fact-accept.txt",
        submitted_text_search="Mira carried the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=28,
        raw_start_offset=0,
        raw_end_offset=28,
        text_preview="Mira carried the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="disputed",
        promotion_decision_id=None,
        evidence_span_ids=[str(span.id)],
        confidence=0.6,
        source_scope="user_draft",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="canon_conflict",
        severity="medium",
        status="open",
        summary="Lantern-map ownership needs confirmation.",
        affected_refs={"fact_id": str(fact.id)},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}, {"resolution": "reject"}],
        default_action="ask_author",
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-fact-accept-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, fact, review_item, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-fact-accept",
            "Idempotency-Key": "idem-api-preview-fact-accept",
        },
        json={
            "item_ref": {"type": "fact_assertion", "id": str(fact.id)},
            "decision": "accept",
            "author_note": "作者确认这条事实进入 canon。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["fact_assertion_status"] == "canon"
    assert body["side_effects"]["memory_pages"] == "updated"
    assert body["side_effects"]["memory_pages_updated"] == 1
    assert body["side_effects"]["graph_projection"] == "rebuilt"
    assert body["side_effects"]["graph_edges_created"] == 1
    assert body["side_effects"]["review_items_resolved"] == 1
    stored_fact = session.get(FactAssertionRecord, fact.id)
    assert stored_fact.fact_status == "canon"
    assert stored_fact.promotion_decision_id is not None
    page = session.query(MemoryPage).one()
    assert page.canon_status == "current"
    assert page.current_canon["facts"][0]["fact_id"] == str(fact.id)
    assert {"type": "source_delta", "id": str(source_delta.id)} in page.source_refs
    edge = session.query(GraphProjectionEdge).one()
    assert edge.source_ref == {"type": "fact_assertion", "id": str(fact.id)}
    assert edge.edge_status == "canon"
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review.status == "resolved"
    assert stored_review.resolution == "accept"
    assert stored_review.resolved_by == actor_id


def test_memory_writeback_preview_fact_accept_blocks_high_risk_promotion_without_side_effects(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/fact-accept-high-risk.md",
        raw_offset_map_ref="object://processed/fact-accept-high-risk.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/fact-accept-high-risk.txt",
        submitted_text_search="Mira knows Orrin's true identity.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=35,
        raw_start_offset=0,
        raw_end_offset=35,
        text_preview="Mira knows Orrin's true identity.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="knows",
        object_ref={"type": "secret", "id": "orrin-identity"},
        fact_status="disputed",
        promotion_decision_id=None,
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="canon_conflict",
        severity="high",
        status="open",
        summary="Mira should not know Orrin's identity in this scene.",
        affected_refs={"fact_id": str(fact.id)},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "supersede"}, {"resolution": "reject"}],
        default_action="ask_author",
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-fact-high-risk-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, fact, review_item, audit])
    session.commit()
    before_counts = _permission_matrix_side_effect_counts(session)

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-fact-high-risk-accept",
            "Idempotency-Key": "idem-api-preview-fact-high-risk-accept",
        },
        json={
            "item_ref": {"type": "fact_assertion", "id": str(fact.id)},
            "decision": "accept",
            "author_note": "作者确认文字保留，但暂不污染 canon。",
        },
    )

    _assert_api_error_response(
        response,
        status_code=409,
        code="policy_blocked_promotion",
    )
    assert response.json()["error"]["details"]["review_item_id"] == str(review_item.id)
    assert response.json()["error"]["details"]["fact_id"] == str(fact.id)
    assert _permission_matrix_side_effect_counts(session) == before_counts
    stored_fact = session.get(FactAssertionRecord, fact.id)
    assert stored_fact.fact_status == "disputed"
    assert stored_fact.promotion_decision_id is None
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review.status == "open"
    assert stored_review.resolution is None
    assert stored_review.resolved_by is None
    assert session.query(MemoryWritebackDecisionRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_writeback_preview_decision_persists_review_item_decision(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-item.md",
        raw_offset_map_ref="object://processed/review-item.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/review-item.txt",
        submitted_text_search="钥匙来源仍未确认。",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=9,
        raw_start_offset=0,
        raw_end_offset=9,
        text_preview="钥匙来源仍未确认。",
        narration_layer="narrator",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="钥匙来源仍未确认。",
        affected_refs={},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="succeeded",
        idempotency_key=f"{source_delta.id}:memory_writeback:pipeline-v1",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(source_delta.id),
        },
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-review-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, review_item, job, audit])
    session.commit()

    preview_response = client.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )
    assert preview_response.status_code == 200
    assert preview_response.json()["review_items"][0]["id"] == str(review_item.id)

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-review-decision",
            "Idempotency-Key": "idem-api-preview-review-decision",
        },
        json={
            "item_ref": {"type": "review_item", "id": str(review_item.id)},
            "decision": "accept",
            "author_note": "作者确认此 Review 需要保留。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "recorded"
    assert body["item_ref"] == {"type": "review_item", "id": str(review_item.id)}
    assert body["side_effects"]["memory_pages"] == "unchanged"
    assert body["side_effects"]["graph_projection"] == "unchanged"
    assert body["side_effects"]["review_item_status"] == "open"
    assert body["side_effects"]["policy_action"] == "review_item_retained"
    decision = session.query(MemoryWritebackDecisionRecord).one()
    assert decision.source_delta_id == source_delta.id
    assert decision.item_ref == {"type": "review_item", "id": str(review_item.id)}
    assert decision.decision == "accept"


def test_memory_writeback_preview_review_item_reject_dismisses_review(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/review-item-reject.md",
        raw_offset_map_ref="object://processed/review-item-reject.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/review-item-reject.txt",
        submitted_text_search="Mira intentionally misleads the reader.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=39,
        raw_start_offset=0,
        raw_end_offset=39,
        text_preview="Mira intentionally misleads the reader.",
        narration_layer="narrator",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="low",
        status="open",
        summary="Possible misleading narration.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "reject"}, {"resolution": "mark_intentional"}],
        default_action="ask_author",
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-review-reject-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, review_item, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-review-reject",
            "Idempotency-Key": "idem-api-preview-review-reject",
        },
        json={
            "item_ref": {"type": "review_item", "id": str(review_item.id)},
            "decision": "reject",
            "author_note": "这是有意误导，不需要作为风险保留。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["review_item_status"] == "dismissed"
    assert body["side_effects"]["policy_action"] == "review_item_dismissed"
    assert body["side_effects"]["memory_pages"] == "unchanged"
    assert body["side_effects"]["graph_projection"] == "unchanged"
    stored_review = session.get(ReviewItemRecord, review_item.id)
    assert stored_review.status == "dismissed"
    assert stored_review.resolved_by == actor_id
    assert stored_review.resolved_at is not None
    assert stored_review.side_effects["author_note"] == "这是有意误导，不需要作为风险保留。"


def test_memory_writeback_preview_source_span_reject_disputes_derived_memory(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/span-reject.md",
        raw_offset_map_ref="object://processed/span-reject.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/span-reject.txt",
        submitted_text_search="Mira owns the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=27,
        raw_start_offset=0,
        raw_end_offset=27,
        text_preview="Mira owns the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        promotion_decision_id=uuid4(),
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
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
                    "predicate": fact.predicate,
                    "object_ref": fact.object_ref,
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_delta", "id": str(source_delta.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash="span-reject-hash",
        created_edge_count=1,
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(fact.id)},
        subject_ref=fact.subject_ref,
        relation="owns",
        target_ref=fact.object_ref,
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-source-span-reject-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, fact, evidence, page, run, edge, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-source-span-reject",
            "Idempotency-Key": "idem-api-preview-source-span-reject",
        },
        json={
            "item_ref": {"type": "source_span", "id": str(span.id)},
            "decision": "reject",
            "author_note": "这段不应作为所有权证据。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["source_span_status"] == "retained"
    assert body["side_effects"]["evidence_log_entries_marked_disputed"] == 1
    assert body["side_effects"]["fact_assertions_marked_disputed"] == 1
    assert body["side_effects"]["graph_edges_marked_disputed"] == 1
    assert body["side_effects"]["memory_pages"] == "marked_stale"
    assert body["side_effects"]["memory_pages_marked_stale"] == 1
    assert len(body["side_effects"]["memory_page_rewrite_job_ids"]) == 1
    assert session.get(SourceSpan, span.id).text_preview == "Mira owns the lantern map."
    assert session.get(EvidenceLogEntry, evidence.id).log_status == "disputed"
    assert session.get(FactAssertionRecord, fact.id).fact_status == "disputed"
    assert session.get(GraphProjectionEdge, edge.id).edge_status == "disputed"
    assert session.get(MemoryPage, page.id).canon_status == "stale"


def test_memory_writeback_preview_evidence_log_reject_disputes_derived_fact(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/evidence-reject.md",
        raw_offset_map_ref="object://processed/evidence-reject.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/evidence-reject.txt",
        submitted_text_search="Mira owns the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=27,
        raw_start_offset=0,
        raw_end_offset=27,
        text_preview="Mira owns the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        promotion_decision_id=uuid4(),
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
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
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-evidence-reject-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, fact, evidence, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-evidence-reject",
            "Idempotency-Key": "idem-api-preview-evidence-reject",
        },
        json={
            "item_ref": {"type": "evidence_log_entry", "id": str(evidence.id)},
            "decision": "reject",
            "author_note": "这条证据日志不应支撑事实。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["evidence_log_status"] == "disputed"
    assert body["side_effects"]["evidence_log_entries_marked_disputed"] == 1
    assert body["side_effects"]["fact_assertions_marked_disputed"] == 1
    assert session.get(EvidenceLogEntry, evidence.id).log_status == "disputed"
    assert session.get(FactAssertionRecord, fact.id).fact_status == "disputed"


def test_memory_writeback_preview_memory_page_reject_marks_stale_and_rewrite(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/page-reject.txt",
        submitted_text_search="Mira page update.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_delta", "id": str(source_delta.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all([source_delta, page])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-page-reject",
            "Idempotency-Key": "idem-api-preview-page-reject",
        },
        json={
            "item_ref": {"type": "memory_page", "id": str(page.id)},
            "decision": "reject",
            "author_note": "这张记忆页需要重写。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["memory_pages"] == "marked_stale"
    assert body["side_effects"]["memory_pages_marked_stale"] == 1
    assert len(body["side_effects"]["memory_page_rewrite_job_ids"]) == 1
    assert body["side_effects"]["graph_projection"] == "unchanged"
    stored_page = session.get(MemoryPage, page.id)
    assert stored_page.canon_status == "stale"
    assert stored_page.contradictions[-1]["item_ref"] == {
        "type": "memory_page",
        "id": str(page.id),
    }
    rewrite_job = session.get(
        JobRecord, UUID(body["side_effects"]["memory_page_rewrite_job_ids"][0])
    )
    assert rewrite_job.job_type == "rewrite_memory_page"
    assert rewrite_job.payload["memory_page_id"] == str(page.id)


def test_memory_writeback_preview_memory_page_open_thread_correction_uses_delta_span(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/page-open-thread.md",
        raw_offset_map_ref="object://processed/page-open-thread.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/page-open-thread.txt",
        submitted_text_search="Mira keeps the map origin unresolved.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=39,
        raw_start_offset=0,
        raw_end_offset=39,
        text_preview="Mira keeps the map origin unresolved.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_delta", "id": str(source_delta.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-page-open-thread-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, page, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-page-open-thread",
            "Idempotency-Key": "idem-api-preview-page-open-thread",
        },
        json={
            "item_ref": {"type": "memory_page", "id": str(page.id)},
            "decision": "correct",
            "author_note": "地图来源还没有解决，需要保持为线索。",
            "correction": {
                "action": "needs_memory_update",
                "target_section": "open_threads",
                "description": "地图来源仍是未解决线索，不能从当前页关闭。",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["policy_action"] == "memory_page_open_thread_recorded"
    assert body["side_effects"]["memory_page_open_threads_added"] == 1
    assert body["side_effects"]["context_pack_readiness"] == "marked_stale"
    assert body["side_effects"]["context_pack_readiness_marked"] == 1
    stored_page = session.get(MemoryPage, page.id)
    assert stored_page.open_threads == [
        {
            "type": "memory_writeback_decision",
            "thread_type": "needs_memory_update",
            "source_delta_id": str(source_delta.id),
            "item_ref": {"type": "memory_page", "id": str(page.id)},
            "decision": "correct",
            "target_section": "open_threads",
            "description": "地图来源仍是未解决线索，不能从当前页关闭。",
            "author_note": "地图来源还没有解决，需要保持为线索。",
            "source_span_ids": [str(span.id)],
            "status": "open",
            "requires": "memory_page_rewrite",
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in stored_page.source_refs
    readiness = session.query(ContextPackReadinessRecord).one()
    assert readiness.source_span_id == span.id
    assert readiness.source_delta_id == source_delta.id
    assert readiness.status == "stale"
    assert readiness.reason == "review_dependency_changed"


def test_memory_writeback_preview_graph_edge_reject_disputes_source_fact(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/edge-reject.md",
        raw_offset_map_ref="object://processed/edge-reject.offsets.json",
        view_status="current",
    )
    source_delta = SourceDeltaRecord(
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
        submitted_text_ref="object://source-deltas/edge-reject.txt",
        submitted_text_search="Mira owns the lantern map.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-test"},
        status="memory_writeback_completed",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=27,
        raw_start_offset=0,
        raw_end_offset=27,
        text_preview="Mira owns the lantern map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        promotion_decision_id=uuid4(),
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash="edge-reject-hash",
        created_edge_count=1,
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(fact.id)},
        subject_ref=fact.subject_ref,
        relation="owns",
        target_ref=fact.object_ref,
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="req-api-preview-edge-reject-span",
        actor_id=actor_id,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(span.id)},
    )
    session.add_all([view, source_delta, span, fact, run, edge, audit])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview/decisions",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-preview-edge-reject",
            "Idempotency-Key": "idem-api-preview-edge-reject",
        },
        json={
            "item_ref": {"type": "graph_edge", "id": str(edge.id)},
            "decision": "reject",
            "author_note": "这条图谱边不该成立。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["graph_edge_status"] == "disputed"
    assert body["side_effects"]["graph_edges_marked_disputed"] == 1
    assert body["side_effects"]["fact_assertions_marked_disputed"] == 1
    assert session.get(GraphProjectionEdge, edge.id).edge_status == "disputed"
    assert session.get(FactAssertionRecord, fact.id).fact_status == "disputed"


def test_job_and_review_list_read_endpoints_allow_viewer_membership(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira may know too much.",
        slug="review-list-viewer",
    )
    viewer_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=viewer_id,
            role="viewer",
            status="active",
        )
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="preview-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(uuid4()),
        },
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([job, review_item])
    session.commit()

    job_response = client.get(
        f"/api/projects/{project.id}/jobs/{job.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )
    review_response = client.get(
        f"/api/projects/{project.id}/review-items",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert job_response.status_code == 200
    assert job_response.json()["status"] == "queued"
    assert review_response.status_code == 200
    assert review_response.json()["items"][0]["id"] == str(review_item.id)


def test_review_item_list_and_detail_filter_invalid_source_span_evidence(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira hears the sealed verdict.",
        slug="review-valid-evidence-ref",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Another project has a separate verdict.",
        slug="review-cross-project-evidence-ref",
    )
    mixed_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={"character_id": "mira"},
        new_evidence={
            "source_span_ids": [
                str(valid_span.id),
                str(cross_project_span.id),
                "not-a-source-span-id",
            ],
            "note": "Needs source-backed review.",
        },
        existing_evidence={"source_span_ids": [str(cross_project_span.id), str(valid_span.id)]},
        suggested_actions=[{"action": "ask_author"}],
        default_action="ask_author",
    )
    invalid_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Unsupported stale review.",
        affected_refs={"character_id": "mira"},
        new_evidence={"source_span_ids": [str(cross_project_span.id), "not-a-source-span-id"]},
        existing_evidence={},
        suggested_actions=[{"action": "ask_author"}],
        default_action="ask_author",
    )
    session.add_all([mixed_review, invalid_review])
    session.commit()

    list_response = client.get(
        f"/api/projects/{project.id}/review-items",
        headers={"X-Actor-Id": str(actor_id)},
    )
    detail_response = client.get(
        f"/api/projects/{project.id}/review-items/{mixed_review.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    invalid_detail_response = client.get(
        f"/api/projects/{project.id}/review-items/{invalid_review.id}",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert [item["id"] for item in list_body["items"]] == [str(mixed_review.id)]
    assert list_body["items"][0]["new_evidence"] == {
        "source_span_ids": [str(valid_span.id)],
        "note": "Needs source-backed review.",
    }
    assert list_body["items"][0]["existing_evidence"] == {"source_span_ids": [str(valid_span.id)]}
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["new_evidence"]["source_span_ids"] == [str(valid_span.id)]
    assert detail_body["existing_evidence"]["source_span_ids"] == [str(valid_span.id)]
    assert invalid_detail_response.status_code == 404
    assert str(cross_project_span.id) not in json.dumps(
        {"list": list_body, "detail": detail_body}, sort_keys=True
    )


def test_memory_writeback_preview_filters_embedded_review_item_evidence(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    valid_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira hears the sealed verdict.",
        slug="preview-review-valid-evidence-ref",
    )
    source_delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        new_version_id=None,
        accepted_fragment_id=None,
        delta_kind="replace",
        range_start=0,
        range_end=31,
        base_hash=version.raw_hash,
        submitted_text_ref="object://delta/preview-review-valid-evidence-ref",
        submitted_text_search="Mira hears the sealed verdict.",
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"source": "api-contract-test"},
        status="memory_writeback_completed",
    )
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    cross_project_span = seed_span_for_source(
        session,
        raw_source=other_source,
        version=other_version,
        text="Another project has a separate verdict.",
        slug="preview-review-cross-project-evidence-ref",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={"character_id": "mira"},
        new_evidence={
            "source_span_ids": [
                str(valid_span.id),
                str(cross_project_span.id),
                "not-a-source-span-id",
            ],
        },
        existing_evidence={"source_span_ids": [str(cross_project_span.id), str(valid_span.id)]},
        suggested_actions=[{"action": "ask_author"}],
        default_action="ask_author",
    )
    extraction_audit = AuditEvent(
        id=uuid4(),
        project_id=project.id,
        request_id="job:preview-review-filter",
        actor_id=None,
        event_type="source.span_extracted",
        subject_ref={"type": "source_delta", "id": str(source_delta.id)},
        decision={"source_span_id": str(valid_span.id)},
    )
    session.add_all([source_delta, review_item, extraction_audit])
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/source-deltas/{source_delta.id}/memory-writeback-preview",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["review_items"][0]["new_evidence"] == {"source_span_ids": [str(valid_span.id)]}
    assert body["review_items"][0]["existing_evidence"] == {"source_span_ids": [str(valid_span.id)]}
    assert str(cross_project_span.id) not in json.dumps(body, sort_keys=True)


def test_list_entities_endpoint_searches_canonical_entities_and_aliases(
    client: TestClient,
    session: Session,
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    harbor = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="provisional",
        cast_tier=None,
        first_seen_scene_id=None,
        description=None,
    )
    session.add_all([mira, kestrel, harbor])
    session.add(
        StoryAliasRecord(
            id=uuid4(),
            project_id=project.id,
            alias_text="Starling",
            entity_id=mira.id,
            alias_type="name",
            status="user_confirmed",
            scope="global",
            evidence_span_ids=[str(uuid4())],
            confidence=0.95,
        )
    )
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/entities?q=star&entity_type=character&limit=5",
        headers={"X-Actor-Id": str(actor_id)},
    )
    limited_response = client.get(
        f"/api/projects/{project.id}/entities?limit=1",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": str(mira.id),
            "entity_type": "character",
            "display_name": "Mira",
            "canonical_status": "provisional",
            "cast_tier": "unknown",
            "first_seen_scene_id": None,
        }
    ]
    assert limited_response.status_code == 200
    assert len(limited_response.json()["items"]) == 1


def test_list_scenes_endpoint_returns_project_scene_options(
    client: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    other_project, other_source, other_version, _other_actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/scene-options.md",
        raw_offset_map_ref="object://processed/scene-options.offsets.json",
        view_status="current",
    )
    other_view = SourceProcessedView(
        id=uuid4(),
        version_id=other_version.id,
        cleaning_profile="default",
        markdown_ref="object://processed/other-scene-options.md",
        raw_offset_map_ref="object://processed/other-scene-options.offsets.json",
        view_status="current",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="The Harbor",
        start_offset=0,
        end_offset=200,
    )
    other_chapter = StoryChapter(
        id=uuid4(),
        view_id=other_view.id,
        chapter_index=0,
        title="Other Harbor",
        start_offset=0,
        end_offset=100,
    )
    later_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        start_offset=100,
        end_offset=200,
        story_time="Night 2",
        scene_summary="Mira reaches the archive.",
    )
    first_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        start_offset=0,
        end_offset=100,
        story_time="Night 1",
        scene_summary="Mira enters the harbor.",
    )
    other_scene = StoryScene(
        id=uuid4(),
        chapter_id=other_chapter.id,
        scene_index=0,
        start_offset=0,
        end_offset=100,
    )
    session.add_all(
        [
            other_project,
            other_source,
            other_version,
            view,
            other_view,
            chapter,
            other_chapter,
            later_scene,
            first_scene,
            other_scene,
        ]
    )
    session.commit()

    response = client.get(
        (
            f"/api/projects/{project.id}/scenes"
            f"?source_id={raw_source.id}&version_id={version.id}&limit=10"
        ),
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {
            "id": str(first_scene.id),
            "source_id": str(raw_source.id),
            "version_id": str(version.id),
            "chapter_id": str(chapter.id),
            "chapter_index": 0,
            "chapter_title": "The Harbor",
            "scene_index": 0,
            "position_label": "Chapter 1 / Scene 1",
            "story_time": "Night 1",
            "scene_summary": "Mira enters the harbor.",
            "pov_character_id": None,
            "pov_mode": None,
        },
        {
            "id": str(later_scene.id),
            "source_id": str(raw_source.id),
            "version_id": str(version.id),
            "chapter_id": str(chapter.id),
            "chapter_index": 0,
            "chapter_title": "The Harbor",
            "scene_index": 1,
            "position_label": "Chapter 1 / Scene 2",
            "story_time": "Night 2",
            "scene_summary": "Mira reaches the archive.",
            "pov_character_id": None,
            "pov_mode": None,
        },
    ]


def test_project_story_schema_override_endpoint_versions_and_validates_schema(
    client: TestClient, session: Session
) -> None:
    project, _, _, actor_id = seed_source(session)
    default_response = client.get(
        f"/api/projects/{project.id}/story-schema",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert default_response.status_code == 200
    default_body = default_response.json()
    assert default_body["binding_id"] is None
    assert "character" in [
        item["name"] for item in default_body["effective_schema"]["entity_types"]
    ]

    payload = {
        "pack_name": "harbor-nine-overrides",
        "entity_types": [{"name": "artifact", "subtype_of": "object"}],
        "event_types": ["oath"],
        "relations": [
            {
                "name": "guards",
                "subject_types": ["character"],
                "object_types": ["artifact", "location"],
            }
        ],
        "extraction_hints": {
            "relation_patterns": [
                {
                    "relation": "guards",
                    "template": "{subject} guards {object}",
                    "subject_type": "character",
                    "object_type": "artifact",
                }
            ],
            "agency_profile_fields": [
                {
                    "predicate": "core_desire",
                    "labels": ["执念"],
                }
            ],
        },
        "risk_rules": {"disabled_relations": ["owns"]},
    }
    headers = {
        "X-Actor-Id": str(actor_id),
        "X-Request-Id": "req-story-schema-upsert",
        "Idempotency-Key": "idem-story-schema-upsert",
    }
    upsert_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers=headers,
        json=payload,
    )
    replay_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers=headers,
        json=payload,
    )
    read_response = client.get(
        f"/api/projects/{project.id}/story-schema",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert upsert_response.status_code == 200
    body = upsert_response.json()
    assert body["project_override_pack"]["pack_name"] == "harbor-nine-overrides"
    assert body["project_override_pack"]["extraction_hints"]["agency_profile_fields"] == [
        {"predicate": "core_desire", "labels": ["执念"]}
    ]
    assert "artifact" in [item["name"] for item in body["effective_schema"]["entity_types"]]
    assert "guards" in body["effective_schema"]["relations"]
    assert "owns" not in body["effective_schema"]["relations"]
    guards_role = next(
        item for item in body["effective_schema"]["relation_roles"] if item["relation"] == "guards"
    )
    assert guards_role["object_types"] == ["artifact", "location"]
    assert replay_response.status_code == 200
    assert replay_response.json()["project_override_pack_id"] == body["project_override_pack_id"]
    assert session.query(StorySchemaPackRecord).filter_by(pack_type="project_override").count() == 1
    assert session.query(ProjectStorySchemaBinding).filter_by(status="active").count() == 1
    assert read_response.status_code == 200
    assert read_response.json()["binding_id"] == body["binding_id"]

    invalid_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-invalid",
            "Idempotency-Key": "idem-story-schema-invalid",
        },
        json={
            **payload,
            "relations": [
                {
                    "name": "haunts",
                    "subject_types": ["ghost"],
                    "object_types": ["location"],
                }
            ],
        },
    )
    invalid_mention_pattern_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-invalid-mention-pattern",
            "Idempotency-Key": "idem-story-schema-invalid-mention-pattern",
        },
        json={
            **payload,
            "extraction_hints": {
                "mention_patterns": [
                    {
                        "entity_type": "ghost",
                        "template": "Ghost: {mention}",
                    }
                ]
            },
        },
    )
    invalid_event_pattern_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-invalid-event-pattern",
            "Idempotency-Key": "idem-story-schema-invalid-event-pattern",
        },
        json={
            **payload,
            "extraction_hints": {
                "event_patterns": [
                    {
                        "event_type": "ghost_rite",
                        "template": "{subject} sealed the rite",
                        "subject_type": "character",
                    }
                ]
            },
        },
    )
    invalid_agency_field_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-invalid-agency-field",
            "Idempotency-Key": "idem-story-schema-invalid-agency-field",
        },
        json={
            **payload,
            "extraction_hints": {
                "agency_profile_fields": [
                    {
                        "predicate": "plot_twist",
                        "labels": ["隐藏爆点"],
                    }
                ]
            },
        },
    )
    viewer_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(uuid4()),
            "X-Request-Id": "req-story-schema-viewer",
            "Idempotency-Key": "idem-story-schema-viewer",
        },
        json=payload,
    )

    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "schema_validation_failed"
    assert invalid_mention_pattern_response.status_code == 400
    assert invalid_mention_pattern_response.json()["error"]["code"] == "schema_validation_failed"
    assert invalid_event_pattern_response.status_code == 400
    assert invalid_event_pattern_response.json()["error"]["code"] == "schema_validation_failed"
    assert invalid_agency_field_response.status_code == 400
    assert invalid_agency_field_response.json()["error"]["code"] == "schema_validation_failed"
    assert session.query(StorySchemaPackRecord).filter_by(pack_type="project_override").count() == 1
    assert viewer_response.status_code == 403
    assert viewer_response.json()["error"]["code"] == "permission_denied"


def test_project_story_schema_genre_pack_endpoint_selects_and_preserves_overrides(
    client: TestClient, session: Session
) -> None:
    project, _, _, actor_id = seed_source(session)
    genre_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="genre",
        pack_name="mystery",
        version="mystery.v1",
        status="active",
        entity_types=[{"name": "clue", "subtype_of": "object"}],
        event_types=["revelation"],
        relations=[
            {
                "name": "points_to",
                "subject_types": ["clue"],
                "object_types": ["character"],
            }
        ],
        extraction_hints={},
        risk_rules={},
    )
    deprecated_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="genre",
        pack_name="deprecated-mystery",
        version="deprecated.v1",
        status="deprecated",
        entity_types=[],
        event_types=[],
        relations=[],
        extraction_hints={},
        risk_rules={},
    )
    session.add_all([genre_pack, deprecated_pack])
    session.commit()

    list_response = client.get(
        f"/api/projects/{project.id}/story-schema/packs?pack_type=genre",
        headers={"X-Actor-Id": str(actor_id)},
    )
    override_response = client.put(
        f"/api/projects/{project.id}/story-schema/project-override",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-genre-override",
            "Idempotency-Key": "idem-genre-override",
        },
        json={
            "pack_name": "harbor-nine-overrides",
            "relations": [
                {
                    "name": "guards",
                    "subject_types": ["character"],
                    "object_types": ["object"],
                }
            ],
        },
    )
    headers = {
        "X-Actor-Id": str(actor_id),
        "X-Request-Id": "req-story-schema-genre",
        "Idempotency-Key": "idem-story-schema-genre",
    }
    select_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers=headers,
        json={"genre_schema_pack_id": str(genre_pack.id)},
    )
    replay_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers=headers,
        json={"genre_schema_pack_id": str(genre_pack.id)},
    )
    clear_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-genre-clear",
            "Idempotency-Key": "idem-story-schema-genre-clear",
        },
        json={"genre_schema_pack_id": None},
    )
    invalid_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-story-schema-genre-invalid",
            "Idempotency-Key": "idem-story-schema-genre-invalid",
        },
        json={"genre_schema_pack_id": str(uuid4())},
    )
    viewer_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers={
            "X-Actor-Id": str(uuid4()),
            "X-Request-Id": "req-story-schema-genre-viewer",
            "Idempotency-Key": "idem-story-schema-genre-viewer",
        },
        json={"genre_schema_pack_id": str(genre_pack.id)},
    )

    assert list_response.status_code == 200
    listed_pack_names = [item["pack_name"] for item in list_response.json()["items"]]
    assert listed_pack_names == ["mystery"]
    assert override_response.status_code == 200
    override_pack_id = override_response.json()["project_override_pack_id"]
    assert select_response.status_code == 200
    selected_body = select_response.json()
    assert selected_body["genre_schema_pack_id"] == str(genre_pack.id)
    assert selected_body["genre_schema_pack"]["pack_name"] == "mystery"
    assert selected_body["project_override_pack_id"] == override_pack_id
    assert "clue" in [item["name"] for item in selected_body["effective_schema"]["entity_types"]]
    assert "points_to" in selected_body["effective_schema"]["relations"]
    assert "guards" in selected_body["effective_schema"]["relations"]
    assert replay_response.status_code == 200
    assert replay_response.json()["binding_id"] == selected_body["binding_id"]
    assert clear_response.status_code == 200
    assert clear_response.json()["genre_schema_pack_id"] is None
    assert clear_response.json()["project_override_pack_id"] == override_pack_id
    assert "points_to" not in clear_response.json()["effective_schema"]["relations"]
    assert "guards" in clear_response.json()["effective_schema"]["relations"]
    assert invalid_response.status_code == 404
    assert invalid_response.json()["error"]["code"] == "not_found"
    assert viewer_response.status_code == 403
    assert viewer_response.json()["error"]["code"] == "permission_denied"
    assert session.query(ProjectStorySchemaBinding).filter_by(status="active").count() == 1
    assert session.query(StorySchemaPackRecord).filter_by(pack_type="project_override").count() == 1


def test_project_story_schema_admin_provisions_and_deprecates_global_genre_packs(
    client: TestClient, session: Session
) -> None:
    project, _, _, actor_id = seed_source(session)
    admin_id = uuid4()
    admin_client = TestClient(
        create_app(lambda: SqlAlchemyUnitOfWork(session), admin_actor_ids={admin_id})
    )
    payload = {
        "pack_name": "procedural",
        "version": "procedural.v1",
        "entity_types": [{"name": "clue", "subtype_of": "object"}],
        "event_types": ["revelation"],
        "relations": [
            {
                "name": "points_to",
                "subject_types": ["clue"],
                "object_types": ["character"],
            }
        ],
        "extraction_hints": {
            "relation_patterns": [
                {
                    "relation": "points_to",
                    "template": "{subject} points to {object}",
                    "subject_type": "clue",
                    "object_type": "character",
                }
            ]
        },
        "risk_rules": {},
    }
    headers = {
        "X-Actor-Id": str(admin_id),
        "X-Request-Id": "req-genre-pack-create",
        "Idempotency-Key": "idem-genre-pack-create",
    }

    create_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs",
        headers=headers,
        json=payload,
    )
    replay_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs",
        headers=headers,
        json=payload,
    )
    non_admin_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-genre-pack-non-admin",
            "Idempotency-Key": "idem-genre-pack-non-admin",
        },
        json={**payload, "version": "procedural.v2"},
    )
    invalid_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs",
        headers={
            "X-Actor-Id": str(admin_id),
            "X-Request-Id": "req-genre-pack-invalid",
            "Idempotency-Key": "idem-genre-pack-invalid",
        },
        json={
            **payload,
            "pack_name": "bad-pack",
            "version": "bad-pack.v1",
            "relations": [
                {
                    "name": "haunts",
                    "subject_types": ["ghost"],
                    "object_types": ["location"],
                }
            ],
        },
    )

    assert create_response.status_code == 200
    created_body = create_response.json()
    created_pack_id = created_body["id"]
    assert created_body["project_id"] is None
    assert created_body["pack_type"] == "genre"
    assert created_body["status"] == "active"
    assert replay_response.status_code == 200
    assert replay_response.json()["id"] == created_pack_id
    assert non_admin_response.status_code == 403
    assert non_admin_response.json()["error"]["code"] == "permission_denied"
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"]["code"] == "schema_validation_failed"
    assert session.query(StorySchemaPackRecord).filter_by(pack_type="genre").count() == 1
    assert session.query(ProjectStorySchemaBinding).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(EvidenceLogEntry).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0

    list_response = client.get(
        f"/api/projects/{project.id}/story-schema/packs?pack_type=genre",
        headers={"X-Actor-Id": str(actor_id)},
    )
    deprecate_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs/{created_pack_id}/deprecate",
        headers={
            "X-Actor-Id": str(admin_id),
            "X-Request-Id": "req-genre-pack-deprecate",
            "Idempotency-Key": "idem-genre-pack-deprecate",
        },
    )
    deprecated_list_response = client.get(
        f"/api/projects/{project.id}/story-schema/packs?pack_type=genre",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert list_response.status_code == 200
    assert [item["pack_name"] for item in list_response.json()["items"]] == ["procedural"]
    assert deprecate_response.status_code == 200
    assert deprecate_response.json()["status"] == "deprecated"
    assert deprecated_list_response.status_code == 200
    assert deprecated_list_response.json()["items"] == []


def test_project_story_schema_admin_cannot_deprecate_in_use_genre_pack(
    client: TestClient, session: Session
) -> None:
    project, _, _, actor_id = seed_source(session)
    admin_id = uuid4()
    admin_client = TestClient(
        create_app(lambda: SqlAlchemyUnitOfWork(session), admin_actor_ids={admin_id})
    )
    genre_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="genre",
        pack_name="locked-mystery",
        version="locked-mystery.v1",
        status="active",
        entity_types=[{"name": "clue", "subtype_of": "object"}],
        event_types=["revelation"],
        relations=[
            {
                "name": "points_to",
                "subject_types": ["clue"],
                "object_types": ["character"],
            }
        ],
        extraction_hints={},
        risk_rules={},
    )
    session.add(genre_pack)
    session.commit()

    select_response = client.put(
        f"/api/projects/{project.id}/story-schema/genre-pack",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-lock-genre",
            "Idempotency-Key": "idem-lock-genre",
        },
        json={"genre_schema_pack_id": str(genre_pack.id)},
    )
    deprecate_response = admin_client.post(
        f"/api/projects/{project.id}/story-schema/genre-packs/{genre_pack.id}/deprecate",
        headers={
            "X-Actor-Id": str(admin_id),
            "X-Request-Id": "req-lock-genre-deprecate",
            "Idempotency-Key": "idem-lock-genre-deprecate",
        },
    )

    assert select_response.status_code == 200
    assert deprecate_response.status_code == 400
    assert deprecate_response.json()["error"]["code"] == "schema_validation_failed"
    session.refresh(genre_pack)
    assert genre_pack.status == "active"


def test_viewer_membership_cannot_call_write_endpoints(
    client_with_objects: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    viewer_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=project.id,
            actor_id=viewer_id,
            role="viewer",
            status="active",
        )
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="viewer-denied-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(uuid4()),
        },
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([job, review_item])
    session.commit()

    headers = {
        "X-Actor-Id": str(viewer_id),
        "X-Request-Id": "req-viewer-denied",
        "Idempotency-Key": "idem-viewer-denied",
    }
    requests = [
        (
            "submit_action_request",
            f"/api/projects/{project.id}/action-requests",
            {
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "trigger": "selection",
                "action_type": "rewrite_span",
                "target": {
                    "kind": "selected_text",
                    "source_id": str(raw_source.id),
                    "source_version_id": str(version.id),
                    "range": {"start": 0, "end": 12},
                },
                "constraints": {},
                "expected_output": "draft_candidate",
                "actor_intent": "改写这里",
            },
        ),
        (
            "create_source",
            f"/api/projects/{project.id}/sources",
            {
                "title": "Viewer Import",
                "source_type": "draft_manuscript",
                "source_scope": "user_draft",
                "ownership_status": "owned",
                "text": "米拉停在门口。",
                "version_label": "v1",
            },
        ),
        (
            "create_source_delta",
            f"/api/projects/{project.id}/sources/{raw_source.id}/versions/{version.id}/source-deltas",
            {
                "delta_kind": "replace",
                "range_start": 0,
                "range_end": 0,
                "base_hash": version.raw_hash,
                "submitted_text": "米拉推开门。",
                "source_type": "draft_manuscript",
                "source_scope": "user_draft",
                "provenance": {"source": "viewer-denied-test"},
            },
        ),
        (
            "create_project_source_delta",
            f"/api/projects/{project.id}/source-deltas",
            {
                "source_id": str(raw_source.id),
                "previous_version_id": str(version.id),
                "delta_kind": "replace",
                "range_start": 0,
                "range_end": 0,
                "base_hash": version.raw_hash,
                "submitted_text": "米拉推开门。",
                "source_type": "draft_manuscript",
                "source_scope": "user_draft",
                "provenance": {"source": "viewer-denied-test"},
            },
        ),
        (
            "cancel_job",
            f"/api/projects/{project.id}/jobs/{job.id}/cancel",
            {"author_note": "viewer should not cancel jobs"},
        ),
        (
            "resolve_review",
            f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
            {
                "resolution": "accepted_as_change",
                "author_note": "viewer should not resolve review",
                "replacement_refs": [{"type": "source_delta", "id": str(uuid4())}],
            },
        ),
        (
            "answer_memory",
            f"/api/projects/{project.id}/memory/answer",
            {"question": "米拉知道什么？"},
        ),
        (
            "build_context_pack",
            f"/api/projects/{project.id}/context-packs/build",
            {
                "current_source_id": str(raw_source.id),
                "current_version_id": str(version.id),
                "mode": "rewrite_span",
                "current_text_window": "米拉停在门口。",
            },
        ),
    ]

    for request_name, url, payload in requests:
        response = client_with_objects.post(url, headers=headers, json=payload)
        assert response.status_code == 403, request_name
        assert response.json()["error"]["code"] == "permission_denied"

    assert session.query(IdempotencyRecord).count() == 0
    assert session.query(AuditEvent).count() == 0


def test_job_cancel_endpoint_records_state_audit_and_idempotent_replay(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
        idempotency_key="cancel-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(uuid4()),
        },
    )
    session.add(job)
    session.commit()

    headers = {
        "X-Actor-Id": str(actor_id),
        "X-Request-Id": "req-api-job-cancel",
        "Idempotency-Key": "idem-api-job-cancel",
    }
    response = client.post(
        f"/api/projects/{project.id}/jobs/{job.id}/cancel",
        headers=headers,
        json={"author_note": "作者暂停这次回写。"},
    )
    replay = client.post(
        f"/api/projects/{project.id}/jobs/{job.id}/cancel",
        headers=headers,
        json={"author_note": "作者暂停这次回写。"},
    )

    assert response.status_code == 200
    assert replay.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert replay.json()["status"] == "cancelled"
    refreshed = session.get(JobRecord, job.id)
    assert refreshed.status == "cancelled"
    assert refreshed.run_after is None
    assert session.query(AuditEvent).filter_by(event_type="job.cancelled").count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="job.cancel").count() == 1


def test_job_cancel_endpoint_allows_running_cooperative_cancel(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="running",
        idempotency_key="cancel-running-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(uuid4()),
        },
        locked_by="worker-1",
        locked_at=datetime(2026, 6, 1, 12, tzinfo=UTC),
    )
    session.add(job)
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/jobs/{job.id}/cancel",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-job-cancel-running",
            "Idempotency-Key": "idem-api-job-cancel-running",
        },
        json={"author_note": "作者停止这次长任务。"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    refreshed = session.get(JobRecord, job.id)
    assert refreshed.status == "cancelled"
    assert refreshed.locked_by is None
    assert refreshed.locked_at is None
    audit = session.query(AuditEvent).filter_by(event_type="job.cancelled").one()
    assert audit.decision["previous_status"] == "running"


def test_job_retry_endpoint_requeues_retryable_job(client: TestClient, session: Session) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="failed_retryable",
        idempotency_key="retry-job",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(uuid4()),
        },
        attempt_count=2,
        run_after=datetime(2026, 6, 1, 12, tzinfo=UTC),
        locked_by="worker-old",
        locked_at=datetime(2026, 6, 1, 11, 55, tzinfo=UTC),
        last_error="provider timeout",
    )
    session.add(job)
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/jobs/{job.id}/retry",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-job-retry",
            "Idempotency-Key": "idem-api-job-retry",
        },
        json={"author_note": "作者要求立即重试。"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_after"] is None
    assert body["last_error"] is None
    refreshed = session.get(JobRecord, job.id)
    assert refreshed.status == "queued"
    assert refreshed.run_after is None
    assert refreshed.locked_by is None
    assert refreshed.locked_at is None
    assert refreshed.last_error is None
    assert session.query(AuditEvent).filter_by(event_type="job.retry_requested").count() == 1


def test_write_endpoint_rejects_unowned_project(client: TestClient, session: Session) -> None:
    project, raw_source, version, _actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(uuid4()),
            "X-Request-Id": "req-api-unowned",
            "Idempotency-Key": "idem-api-unowned",
        },
        json={
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "trigger": "selection",
            "action_type": "rewrite_span",
            "target": {
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 0, "end": 12},
            },
            "constraints": {},
            "expected_output": "draft_candidate",
            "actor_intent": "改写这里",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_body_actor_must_match_authenticated_actor(client: TestClient, session: Session) -> None:
    project, raw_source, version, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/action-requests",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-mismatch",
            "Idempotency-Key": "idem-api-mismatch",
        },
        json={
            "actor_id": str(uuid4()),
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "trigger": "selection",
            "action_type": "rewrite_span",
            "target": {
                "kind": "selected_text",
                "source_id": str(raw_source.id),
                "source_version_id": str(version.id),
                "range": {"start": 0, "end": 12},
            },
            "constraints": {},
            "expected_output": "draft_candidate",
            "actor_intent": "改写这里",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_review_item_resolve_endpoint(client: TestClient, session: Session) -> None:
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
        submitted_text_ref="object://replacement/api-review-resolve.txt",
        submitted_text_search="确认是新变化",
        source_type="author_notes",
        source_scope="author_note",
        provenance={"trigger": "api_review_resolution"},
        status="submitted",
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([replacement_delta, review_item])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-resolve",
            "Idempotency-Key": "idem-api-review-resolve",
        },
        json={
            "resolution": "accepted_as_change",
            "author_note": "确认是新变化",
            "replacement_refs": [{"type": "source_delta", "id": str(replacement_delta.id)}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["side_effects"]["graph_projection"] == "unchanged"
    assert body["side_effects"]["graph_edges_marked_stale"] == 0


def test_review_item_resolve_endpoint_applies_alias_correction(
    client: TestClient, session: Session
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

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-alias-correct",
            "Idempotency-Key": "idem-api-review-alias-correct",
        },
        json={
            "resolution": "accepted_as_change",
            "author_note": "Starling 是 Mira 的称呼。",
            "correction": {
                "alias_record_id": str(alias.id),
                "target_entity_id": str(target_entity.id),
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["alias_correction"] == "applied"
    assert body["side_effects"]["graph_projection"] == "rebuilt"
    assert body["side_effects"]["memory_pages"] == "marked_stale"
    assert session.get(StoryAliasRecord, alias.id).status == "user_corrected"
    assert session.get(StoryMention, mention.id).resolved_entity_id == target_entity.id
    assert session.get(FactAssertionRecord, fact.id).subject_ref["id"] == str(target_entity.id)
    assert session.query(GraphProjectionEdge).one().subject_ref["id"] == str(target_entity.id)


def test_review_item_resolve_endpoint_rejects_missing_alias_correction_target_without_side_effects(
    client: TestClient, session: Session
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
    before_counts = _permission_matrix_side_effect_counts(session)

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-alias-missing-target",
            "Idempotency-Key": "idem-api-review-alias-missing-target",
        },
        json={
            "resolution": "accepted_as_change",
            "author_note": "Starling 需要指向真实角色。",
            "correction": {
                "alias_record_id": str(alias.id),
                "target_entity_id": str(uuid4()),
            },
        },
    )

    _assert_api_error_response(response, status_code=404, code="not_found")
    assert session.get(ReviewItemRecord, review_item.id).status == "open"
    assert session.get(StoryAliasRecord, alias.id).status == "proposed"
    assert _permission_matrix_side_effect_counts(session) == before_counts


def test_review_item_resolve_endpoint_rejects_split_merge_without_replacement_delta(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="event_merge_conflict",
        severity="medium",
        status="open",
        summary="Two events may need merging.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "merge"}],
        default_action="merge",
    )
    session.add(review_item)
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-merge-missing-ref",
            "Idempotency-Key": "idem-api-review-merge-missing-ref",
        },
        json={
            "resolution": "merge",
            "author_note": "合并为一次事件。",
            "replacement_refs": [],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "schema_validation_failed"
    assert "replacement SourceDelta" in response.json()["error"]["message"]

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-merge-missing-delta",
            "Idempotency-Key": "idem-api-review-merge-missing-delta",
        },
        json={
            "resolution": "merge",
            "author_note": "合并为一次事件。",
            "replacement_refs": [{"type": "source_delta", "id": str(uuid4())}],
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "Replacement SourceDelta" in response.json()["error"]["message"]
    assert session.get(ReviewItemRecord, review_item.id).status == "open"


def test_review_item_resolve_endpoint_returns_superseded_status(
    client: TestClient, session: Session
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
        submitted_text_ref="object://replacement/api-review-supersede.txt",
        submitted_text_search="New evidence supersedes the old review.",
        source_type="author_notes",
        source_scope="author_note",
        provenance={"trigger": "api_review_supersede_resolution"},
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

    missing_refs_response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-supersede-missing",
            "Idempotency-Key": "idem-api-review-supersede-missing",
        },
        json={
            "resolution": "supersede",
            "author_note": "缺少替代证据。",
        },
    )
    assert missing_refs_response.status_code == 400
    assert missing_refs_response.json()["error"]["code"] == "schema_validation_failed"
    assert session.get(ReviewItemRecord, review_item.id).status == "open"

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-supersede",
            "Idempotency-Key": "idem-api-review-supersede",
        },
        json={
            "resolution": "supersede",
            "author_note": "新证据已经取代这个 ReviewItem。",
            "replacement_refs": [{"type": "source_delta", "id": str(replacement_delta.id)}],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "superseded"
    assert response.json()["resolution"] == "supersede"
    assert response.json()["side_effects"]["replacement_refs"] == [
        {"type": "source_delta", "id": str(replacement_delta.id)}
    ]
    assert session.get(ReviewItemRecord, review_item.id).status == "superseded"


def test_review_item_resolve_endpoint_accepts_replacement_review_item_ref(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)
    replacement_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="version_conflict",
        severity="medium",
        status="open",
        summary="Newer ReviewItem carries the current evidence.",
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
        summary="Older ReviewItem has been replaced.",
        affected_refs={},
        new_evidence={"source_span_ids": [str(uuid4())]},
        existing_evidence={},
        suggested_actions=[{"resolution": "supersede"}],
        default_action="supersede",
    )
    session.add_all([replacement_review, review_item])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-supersede-review-ref",
            "Idempotency-Key": "idem-api-review-supersede-review-ref",
        },
        json={
            "resolution": "supersede",
            "author_note": "新的 ReviewItem 已经替代这个旧风险。",
            "replacement_refs": [{"type": "review_item", "id": str(replacement_review.id)}],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "superseded"
    assert response.json()["side_effects"]["replacement_refs"] == [
        {"type": "review_item", "id": str(replacement_review.id)}
    ]
    assert session.get(ReviewItemRecord, review_item.id).status == "superseded"


def test_review_item_resolve_applies_memory_and_graph_stale_side_effects(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref="object://processed/review-side-effect.md",
        raw_offset_map_ref="object://processed/review-side-effect.offsets.json",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=12,
        raw_start_offset=0,
        raw_end_offset=12,
        text_preview="Mira owns it",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        promotion_decision_id=uuid4(),
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="Mira",
        current_canon={
            "facts": [
                {
                    "fact_id": str(fact.id),
                    "predicate": "owns",
                    "object_ref": fact.object_ref,
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash="review-side-effect-hash",
        created_edge_count=1,
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(fact.id)},
        subject_ref=fact.subject_ref,
        relation="owns",
        target_ref=fact.object_ref,
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="canon_conflict",
        severity="high",
        status="open",
        summary="Mira ownership changed.",
        affected_refs={
            "fact_id": str(fact.id),
            "memory_page_id": str(page.id),
        },
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
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
        range_start=0,
        range_end=0,
        base_hash=version.raw_hash,
        submitted_text_ref="object://replacement/api-review-side-effects.txt",
        submitted_text_search="作者确认改设定",
        source_type="author_notes",
        source_scope="author_note",
        provenance={"trigger": "api_review_resolution"},
        status="submitted",
    )
    session.add_all([view, span, fact, page, run, edge, review_item, replacement_delta])
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-review-resolve-side-effects",
            "Idempotency-Key": "idem-api-review-resolve-side-effects",
        },
        json={
            "resolution": "accepted_as_change",
            "author_note": "作者确认改设定。",
            "replacement_refs": [{"type": "source_delta", "id": str(replacement_delta.id)}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["side_effects"]["memory_pages"] == "marked_stale"
    assert body["side_effects"]["memory_pages_marked_stale"] == 1
    assert body["side_effects"]["graph_projection"] == "marked_stale"
    assert body["side_effects"]["graph_edges_marked_stale"] == 1
    stale_page = session.get(MemoryPage, page.id)
    assert stale_page.canon_status == "stale"
    assert stale_page.contradictions[-1]["review_item_id"] == str(review_item.id)
    assert session.get(GraphProjectionEdge, edge.id).edge_status == "outdated"
    stale_readiness = session.query(ContextPackReadinessRecord).one()
    assert stale_readiness.status == "stale"
    assert stale_readiness.reason == "review_dependency_changed"
    assert stale_readiness.source_span_id == span.id
    assert stale_readiness.source_delta_id is None
    assert {"type": "review_item", "id": str(review_item.id)} in stale_readiness.affected_refs
    assert {"type": "memory_page", "id": str(page.id)} in stale_readiness.affected_refs
    assert {"type": "graph_edge", "id": str(edge.id)} in stale_readiness.affected_refs
    assert stale_readiness.evidence_refs == [{"type": "source_span", "id": str(span.id)}]


def test_review_item_resolve_rejects_model_source_scope_conflict_through_api(
    client: TestClient,
    session: Session,
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    user_span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira owns the Lantern Map.",
        slug="api-source-scope-reject-user",
    )
    model_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="model_output",
        source_scope="model_suggestion",
        title="Model suggestion",
        ownership_status="owned",
        raw_text_ref="object://raw/api-model-suggestion-reject",
    )
    model_version = SourceVersion(
        id=uuid4(),
        source_id=model_source.id,
        version_label="v1",
        raw_hash="hash-api-model-suggestion-reject",
    )
    session.add_all([model_source, model_version])
    session.flush()
    model_span = seed_span_for_source(
        session,
        raw_source=model_source,
        version=model_version,
        text="Mira owns the Lantern Map.",
        slug="api-source-scope-reject-model",
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

    response = client.post(
        f"/api/projects/{project.id}/review-items/{review_item.id}/resolve",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-source-scope-reject",
            "Idempotency-Key": "idem-api-source-scope-reject",
        },
        json={
            "resolution": "reject",
            "author_note": "作者拒绝模型建议，不进入当前设定。",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution"] == "reject"
    assert body["side_effects"]["fact_reject"] == "source_scope_conflict_rejected"
    assert body["side_effects"]["fact_assertion_status"] == "contradicted"
    assert body["side_effects"]["graph_projection"] == "rebuilt"
    assert session.get(ReviewItemRecord, review_item.id).status == "resolved"
    stored_model_fact = session.get(FactAssertionRecord, model_fact.id)
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

    stale_readiness = session.query(ContextPackReadinessRecord).all()
    assert {(record.source_span_id, record.status) for record in stale_readiness} == {
        (user_span.id, "stale"),
        (model_span.id, "stale"),
    }
    assert all(record.reason == "review_dependency_changed" for record in stale_readiness)
    assert all(
        {"type": "fact_assertion", "id": str(model_fact.id)} in record.affected_refs
        for record in stale_readiness
    )


def test_review_item_detail_endpoint_allows_viewer_membership(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, _actor_id = seed_source(session)
    span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira may know too much.",
        slug="review-detail-viewer",
    )
    viewer_id = uuid4()
    review_item = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know too much.",
        affected_refs={"character_id": "mira"},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"action": "ask_author"}],
        default_action="ask_author",
    )
    session.add_all(
        [
            ProjectMembership(
                id=uuid4(),
                project_id=project.id,
                actor_id=viewer_id,
                role="viewer",
                status="active",
            ),
            review_item,
        ]
    )
    session.commit()

    response = client.get(
        f"/api/projects/{project.id}/review-items/{review_item.id}",
        headers={"X-Actor-Id": str(viewer_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(review_item.id)
    assert body["affected_refs"] == {"character_id": "mira"}


def test_memory_answer_endpoint_returns_unknown_with_evidence_contract(
    client: TestClient, session: Session
) -> None:
    project, _raw_source, _version, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/memory/answer",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-answer",
            "Idempotency-Key": "idem-api-answer",
        },
        json={"question": "米拉知道钥匙是谁给的吗？"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer_type"] == "unknown"
    assert body["confidence"] == 0.0
    assert body["source_span_refs"] == []
    assert body["affected_entities"] == []
    assert body["caveats"] == ["structured_subject_or_predicate_required"]


def test_context_pack_build_endpoint_returns_required_sections(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    span = seed_span_for_source(
        session,
        raw_source=raw_source,
        version=version,
        text="Mira carries the Lantern Map.",
        slug="context-pack-api",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add(fact)
    session.commit()

    response = client.post(
        f"/api/projects/{project.id}/context-packs/build",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-context",
            "Idempotency-Key": "idem-api-context",
        },
        json={
            "current_source_id": str(raw_source.id),
            "current_version_id": str(version.id),
            "mode": "draft_next_passage",
            "current_text_window": "米拉停在门口。",
            "constraints": {"context_budget": {"max_estimated_tokens": 180}},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "writing-context-pack.v1"
    assert "canonical_context" in body
    assert "risk_context" in body
    assert body["canonical_context"]["facts"][0]["fact_id"] == str(fact.id)
    assert body["canonical_context"]["retrieval_policy"]["budget"] == {
        "max_estimated_tokens": 180,
        "estimated_tokens": body["canonical_context"]["retrieval_policy"]["budget"][
            "estimated_tokens"
        ],
        "truncated": False,
    }
    context_pack = (
        session.query(AgentContextPackRecord).filter_by(id=UUID(body["context_pack_id"])).one()
    )
    assert (
        context_pack.payload["canonical_context"]["retrieval_policy"]["budget"][
            "max_estimated_tokens"
        ]
        == 180
    )


def test_context_pack_build_endpoint_rejects_invalid_budget_without_side_effects(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)

    response = client.post(
        f"/api/projects/{project.id}/context-packs/build",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-context-invalid-budget",
            "Idempotency-Key": "idem-api-context-invalid-budget",
        },
        json={
            "current_source_id": str(raw_source.id),
            "current_version_id": str(version.id),
            "mode": "draft_next_passage",
            "current_text_window": "米拉停在门口。",
            "constraints": {"context_budget": {"max_estimated_tokens": -1}},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "schema_validation_failed"
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(IdempotencyRecord).filter_by(operation="context_pack.build").count() == 0
    assert session.query(AuditEvent).filter_by(event_type="context_pack.built").count() == 0


def test_context_pack_detail_and_list_endpoints_return_persisted_snapshot(
    client: TestClient, session: Session
) -> None:
    project, raw_source, version, actor_id = seed_source(session)
    build_response = client.post(
        f"/api/projects/{project.id}/context-packs/build",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-api-context-read",
            "Idempotency-Key": "idem-api-context-read",
        },
        json={
            "current_source_id": str(raw_source.id),
            "current_version_id": str(version.id),
            "mode": "draft_next_passage",
            "current_text_window": "米拉停在门口。",
        },
    )
    assert build_response.status_code == 200
    context_pack_id = build_response.json()["context_pack_id"]

    detail_response = client.get(
        f"/api/projects/{project.id}/context-packs/{context_pack_id}",
        headers={"X-Actor-Id": str(actor_id)},
    )
    list_response = client.get(
        f"/api/projects/{project.id}/context-packs",
        headers={"X-Actor-Id": str(actor_id)},
    )

    assert detail_response.status_code == 200
    assert detail_response.json()["context_pack_id"] == context_pack_id
    assert detail_response.json()["current_position"]["current_text_window"] == "米拉停在门口。"
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["context_pack_id"] == context_pack_id
    assert list_response.json()["items"][0]["mode"] == "draft_next_passage"


def test_api_routes_do_not_import_infra() -> None:
    api_files = ["backend/src/sextant/api/app.py", "backend/src/sextant/api/schemas.py"]
    for path in api_files:
        with open(path, encoding="utf-8") as api_file:
            assert "sextant.infra" not in api_file.read()
