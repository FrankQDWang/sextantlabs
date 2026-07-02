from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from time import perf_counter
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from sextant.api.schemas import (
    ActionRequestCreateBody,
    ActionRequestDetailResponse,
    ActionRequestResponse,
    ActionRequestRunBody,
    ActionRequestRunResponse,
    AgentActionRunBody,
    AgentReviewFindingResponse,
    ArchiveSourceBody,
    ArchiveSourceResponse,
    BeatCandidateResponse,
    BuildWritingContextPackBody,
    CandidateAcceptBody,
    CandidateAcceptResponse,
    CandidateDetailResponse,
    CandidateExplanationResponse,
    CandidateOperationResponse,
    CandidateOverrideBody,
    CandidateRejectBody,
    CandidateReviseBody,
    CanonicalEntityListResponse,
    CanonicalEntitySummaryResponse,
    ContextPackReadinessListResponse,
    ContextPackReadinessResponse,
    CreateSourceBody,
    CreateSourceDeltaBody,
    CreateSourceDeltaResponse,
    CreateSourceResponse,
    CreateSourceVersionBody,
    CreateSourceVersionResponse,
    GraphProjectionEdgeListResponse,
    GraphProjectionEdgeResponse,
    JobDetailResponse,
    JobOperationBody,
    MemoryAnswerBody,
    MemoryAnswerResponse,
    MemoryPageDetailResponse,
    MemoryPageListResponse,
    MemoryPageSummaryResponse,
    MemoryPageThreadOperationBody,
    MemoryPageThreadOperationResponse,
    MemoryWritebackDecisionBody,
    MemoryWritebackDecisionResponse,
    MemoryWritebackPreviewResponse,
    ProjectInvitationCreateBody,
    ProjectInvitationExternalProofBody,
    ProjectInvitationListResponse,
    ProjectInvitationResponse,
    ProjectMemberListResponse,
    ProjectMemberOperationResponse,
    ProjectMemberResponse,
    ProjectMemberUpsertBody,
    ProjectResponse,
    ProjectSourceDeltaBody,
    ProjectStorySchemaGenreBody,
    ProjectStorySchemaOverrideBody,
    ProjectStorySchemaResponse,
    RestoreSourceVersionBody,
    RestoreSourceVersionResponse,
    ReviewItemDetailResponse,
    ReviewItemListResponse,
    ReviewItemNoteBody,
    ReviewItemOperationResponse,
    ReviewItemResolveBody,
    SourceDeltaDetailResponse,
    SourceDeltaListResponse,
    SourceDeltaSummaryResponse,
    SourceListResponse,
    SourceSummaryResponse,
    SourceVersionDiffHunkResponse,
    SourceVersionDiffLineResponse,
    SourceVersionDiffResponse,
    SourceVersionDiffSummaryResponse,
    SourceVersionListResponse,
    SourceVersionResponse,
    SourceVersionSummaryResponse,
    StorySceneListResponse,
    StorySceneSummaryResponse,
    StorySchemaGenrePackBody,
    StorySchemaPackListResponse,
    StorySchemaPackResponse,
    WritingContextPackListResponse,
    WritingContextPackResponse,
    WritingContextPackSummaryResponse,
)
from sextant.application.errors import ApplicationError
from sextant.application.use_cases import (
    AcceptCandidate,
    AnswerWithEvidence,
    ArchiveSource,
    BuildWritingContextPack,
    ConfirmMemoryWritebackDecision,
    CreateProjectInvitation,
    CreateSource,
    CreateSourceDelta,
    CreateSourceVersion,
    CreateStorySchemaGenrePack,
    DeprecateStorySchemaGenrePack,
    GetActionRequest,
    GetCandidate,
    GetJobDetail,
    GetMemoryPageDetail,
    GetMemoryWritebackPreview,
    GetProject,
    GetProjectStorySchema,
    GetReviewItemDetail,
    GetSource,
    GetSourceDeltaDetail,
    GetSourceVersion,
    GetSourceVersionDiff,
    GetWritingContextPack,
    ListCanonicalEntities,
    ListContextPackReadiness,
    ListGraphProjectionEdges,
    ListMemoryPages,
    ListProjectInvitations,
    ListProjectMembers,
    ListReviewItems,
    ListSourceDeltas,
    ListSources,
    ListSourceVersions,
    ListStoryScenes,
    ListStorySchemaPacks,
    ListWritingContextPacks,
    OperateCandidate,
    OperateJob,
    OperateMemoryPageThread,
    OperateReviewItem,
    RecordProjectInvitationExternalProof,
    RestoreSourceVersion,
    RevokeProjectMember,
    RunActionRequest,
    SelectProjectStorySchemaGenre,
    SubmitActionRequest,
    UpsertProjectMember,
    UpsertProjectStorySchemaOverride,
)
from sextant.common.observability import (
    MetricsRegistry,
    ObservabilityState,
    render_prometheus_metrics,
    safe_log_event,
    trace_context_from_traceparent,
    traceparent_header,
)
from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    ArchiveSourceInput,
    BuildWritingContextPackInput,
    CandidateOperationInput,
    CanonicalEntitySummaryOutput,
    ContextPackDetailInput,
    CreateProjectInvitationInput,
    CreateSourceDeltaInput,
    CreateSourceInput,
    CreateSourceVersionInput,
    CreateStorySchemaGenrePackInput,
    DeprecateStorySchemaGenrePackInput,
    GetActionRequestInput,
    GetCandidateInput,
    GetProjectInput,
    GetProjectStorySchemaInput,
    GetSourceInput,
    GetSourceVersionInput,
    GraphProjectionEdgeSummaryOutput,
    JobDetailInput,
    JobDetailOutput,
    JobOperationInput,
    ListCanonicalEntitiesInput,
    ListContextPackReadinessInput,
    ListContextPacksInput,
    ListGraphProjectionEdgesInput,
    ListMemoryPagesInput,
    ListProjectInvitationsInput,
    ListProjectMembersInput,
    ListReviewItemsInput,
    ListSourceDeltasInput,
    ListSourcesInput,
    ListSourceVersionsInput,
    ListStoryScenesInput,
    ListStorySchemaPacksInput,
    MemoryAnswerInput,
    MemoryPageDetailInput,
    MemoryPageDetailOutput,
    MemoryPageSummaryOutput,
    MemoryPageThreadOperationInput,
    MemoryWritebackDecisionInput,
    MemoryWritebackPreviewInput,
    ProjectInvitationSnapshot,
    ProjectMemberSnapshot,
    ProjectStorySchemaOutput,
    RecordProjectInvitationExternalProofInput,
    RestoreSourceVersionInput,
    ReviewItemDetailInput,
    ReviewItemDetailOutput,
    ReviewItemOperationInput,
    RevokeProjectMemberInput,
    RunActionRequestInput,
    RunActionRequestOutput,
    SelectProjectStorySchemaGenreInput,
    SourceDeltaDetailInput,
    SourceDeltaDetailOutput,
    SourceDeltaSummaryOutput,
    SourceSummaryOutput,
    SourceVersionDiffInput,
    StorySceneSummaryOutput,
    StorySchemaPackOutput,
    SubmitActionRequestInput,
    UpsertProjectMemberInput,
    UpsertProjectStorySchemaOverrideInput,
    WritingContextPackOutput,
)
from sextant.ports.auth import AuthVerifier
from sextant.ports.object_store import ObjectStore
from sextant.ports.story_draft import StoryDraftProvider
from sextant.ports.unit_of_work import SextantUnitOfWork

API_VERSION = "0.1.0"


def create_app(
    uow_factory: Callable[[], SextantUnitOfWork],
    *,
    object_store: ObjectStore | None = None,
    story_draft_provider: StoryDraftProvider | None = None,
    auth_verifier: AuthVerifier | None = None,
    admin_actor_ids: set[UUID] | frozenset[UUID] | None = None,
    allowed_origins: list[str] | None = None,
    metrics: MetricsRegistry | None = None,
    observability_state: ObservabilityState | None = None,
    log_sink: Callable[[str], None] | None = None,
    health_metadata: Mapping[str, str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Sextant API", version=API_VERSION)
    system_admin_actor_ids = frozenset(admin_actor_ids or ())
    safe_health_metadata = dict(health_metadata or {})
    runtime_observability = observability_state or ObservabilityState()
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "X-Actor-Id",
                "X-Request-Id",
                "Idempotency-Key",
                "Content-Type",
                "traceparent",
                "tracestate",
            ],
            allow_private_network=True,
        )

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "sextant-api",
            "api_version": API_VERSION,
            "release_environment": safe_health_metadata.get(
                "release_environment",
                "development",
            ),
            "deployment_version": safe_health_metadata.get("deployment_version", "local"),
        }

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        trace_context = trace_context_from_traceparent(request.headers.get("traceparent"))
        request.scope["sextant_trace_context"] = trace_context
        started_at = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["traceparent"] = traceparent_header(trace_context)
            response.headers["X-Trace-Id"] = trace_context.trace_id
            return response
        finally:
            duration_ms = int((perf_counter() - started_at) * 1000)
            path_template = _path_template(request)
            labels = {
                "method": request.method,
                "path": path_template,
                "status": str(status_code),
            }
            if metrics is not None:
                metrics.increment("sextant_api_requests_total", labels=labels)
                if status_code >= 400:
                    metrics.increment("sextant_api_errors_total", labels=labels)
            runtime_observability.record_api_request(
                method=request.method,
                path=path_template,
                status=status_code,
                duration_ms=duration_ms,
                trace_context=trace_context,
            )
            if log_sink is not None:
                log_sink(
                    safe_log_event(
                        event_type="api.request",
                        project_id=_uuid_or_none(request.path_params.get("project_id")),
                        request_id=request.headers.get("X-Request-Id"),
                        actor_id=_uuid_or_none(request.headers.get("X-Actor-Id")),
                        payload={
                            "method": request.method,
                            "path": path_template,
                            "status": status_code,
                            "duration_ms": duration_ms,
                            "trace_id": trace_context.trace_id,
                            "span_id": trace_context.span_id,
                        },
                    )
                )

    @app.middleware("http")
    async def authenticate_request(request: Request, call_next):
        if not request.url.path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)

        if auth_verifier is None:
            if request.headers.get("X-Actor-Id") is None:
                return _authentication_required_response("X-Actor-Id header is required.")
            return await call_next(request)

        actor_id = auth_verifier.actor_id_for_authorization(request.headers.get("Authorization"))
        if actor_id is None:
            return _authentication_required_response("A valid bearer token is required.")

        request.scope["headers"] = _replace_header(
            request.scope["headers"],
            b"x-actor-id",
            str(actor_id).encode("ascii"),
        )
        return await call_next(request)

    @app.get("/metrics", include_in_schema=False)
    def export_metrics() -> PlainTextResponse:
        body = render_prometheus_metrics(metrics.snapshot()) if metrics is not None else ""
        return PlainTextResponse(
            body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/observability/traces", include_in_schema=False)
    def export_trace_samples() -> dict[str, object]:
        return runtime_observability.trace_report()

    @app.get("/observability/alerts", include_in_schema=False)
    def export_alert_state() -> dict[str, object]:
        return runtime_observability.alert_report(metrics)

    def observe_latency_ms(
        name: str,
        started_at: float,
        *,
        labels: dict[str, str],
    ) -> None:
        if metrics is None:
            return
        metrics.observe_ms(
            name,
            (perf_counter() - started_at) * 1000,
            labels=labels,
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        status_code = _status_for_error(exc.code)
        if metrics is not None:
            labels = {
                "code": exc.code,
                "path": _path_template(request),
                "status": str(status_code),
            }
            metrics.increment("sextant_application_errors_total", labels=labels)
            if exc.code == "llm_output_invalid":
                metrics.increment(
                    "sextant_llm_validation_failures_total",
                    labels={"surface": "story_draft"},
                )
            if exc.code == "policy_blocked_promotion":
                metrics.increment(
                    "sextant_canon_promotion_blocked_total",
                    labels={"reason": "high_risk_review"},
                )
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if metrics is not None:
            metrics.increment(
                "sextant_application_errors_total",
                labels={
                    "code": "schema_validation_failed",
                    "path": _path_template(request),
                    "status": "400",
                },
            )
        return _schema_validation_failed_response(exc.errors())

    @app.get(
        "/api/projects/{project_id}",
        response_model=ProjectResponse,
    )
    def get_project(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ProjectResponse:
        output = GetProject(uow_factory).execute(
            GetProjectInput(project_id=project_id, actor_id=actor_id)
        )
        return ProjectResponse(
            id=output.id,
            name=output.name,
            actor_role=output.actor_role,
            created_at=output.created_at,
        )

    @app.get(
        "/api/projects/{project_id}/members",
        response_model=ProjectMemberListResponse,
    )
    def list_project_members(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ProjectMemberListResponse:
        output = ListProjectMembers(uow_factory).execute(
            ListProjectMembersInput(project_id=project_id, actor_id=actor_id)
        )
        return ProjectMemberListResponse(
            items=[_project_member_response(member) for member in output.items]
        )

    @app.put(
        "/api/projects/{project_id}/members/{member_actor_id}",
        response_model=ProjectMemberOperationResponse,
    )
    def upsert_project_member(
        project_id: UUID,
        member_actor_id: UUID,
        body: ProjectMemberUpsertBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectMemberOperationResponse:
        output = UpsertProjectMember(uow_factory).execute(
            UpsertProjectMemberInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                member_actor_id=member_actor_id,
                role=body.role,
            )
        )
        return ProjectMemberOperationResponse(
            member=_project_member_response(output.member),
            status=output.status,
        )

    @app.post(
        "/api/projects/{project_id}/members/{member_actor_id}/revoke",
        response_model=ProjectMemberOperationResponse,
    )
    def revoke_project_member(
        project_id: UUID,
        member_actor_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectMemberOperationResponse:
        output = RevokeProjectMember(uow_factory).execute(
            RevokeProjectMemberInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                member_actor_id=member_actor_id,
            )
        )
        return ProjectMemberOperationResponse(
            member=_project_member_response(output.member),
            status=output.status,
        )

    @app.get(
        "/api/projects/{project_id}/invitations",
        response_model=ProjectInvitationListResponse,
    )
    def list_project_invitations(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ProjectInvitationListResponse:
        output = ListProjectInvitations(uow_factory).execute(
            ListProjectInvitationsInput(project_id=project_id, actor_id=actor_id)
        )
        return ProjectInvitationListResponse(
            items=[_project_invitation_response(invitation) for invitation in output.items]
        )

    @app.post(
        "/api/projects/{project_id}/invitations",
        response_model=ProjectInvitationResponse,
    )
    def create_project_invitation(
        project_id: UUID,
        body: ProjectInvitationCreateBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectInvitationResponse:
        output = CreateProjectInvitation(uow_factory).execute(
            CreateProjectInvitationInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                member_actor_id=body.member_actor_id,
                role=body.role,
                delivery_provider_ref=body.delivery_provider_ref,
                delivery_target_ref=body.delivery_target_ref,
                token_issuer_ref=body.token_issuer_ref,
            )
        )
        return _project_invitation_response(output)

    @app.post(
        "/api/projects/{project_id}/invitations/{invitation_id}/external-proof",
        response_model=ProjectInvitationResponse,
    )
    def record_project_invitation_external_proof(
        project_id: UUID,
        invitation_id: UUID,
        body: ProjectInvitationExternalProofBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectInvitationResponse:
        output = RecordProjectInvitationExternalProof(uow_factory).execute(
            RecordProjectInvitationExternalProofInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                invitation_id=invitation_id,
                delivery_proof_ref=body.delivery_proof_ref,
                token_proof_ref=body.token_proof_ref,
            )
        )
        return _project_invitation_response(output)

    @app.get(
        "/api/projects/{project_id}/sources",
        response_model=SourceListResponse,
    )
    def list_sources(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        query: str = "",
        limit: int = 20,
        include_archived: bool = False,
    ) -> SourceListResponse:
        output = ListSources(uow_factory).execute(
            ListSourcesInput(
                project_id=project_id,
                actor_id=actor_id,
                query=query,
                limit=limit,
                include_archived=include_archived,
            )
        )
        return SourceListResponse(items=[_source_summary_response(item) for item in output.items])

    @app.get(
        "/api/projects/{project_id}/sources/{source_id}",
        response_model=SourceSummaryResponse,
    )
    def get_source(
        project_id: UUID,
        source_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> SourceSummaryResponse:
        output = GetSource(uow_factory).execute(
            GetSourceInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
            )
        )
        return _source_summary_response(output)

    @app.post(
        "/api/projects/{project_id}/sources/{source_id}/archive",
        response_model=ArchiveSourceResponse,
    )
    def archive_source(
        project_id: UUID,
        source_id: UUID,
        body: ArchiveSourceBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ArchiveSourceResponse:
        output = ArchiveSource(uow_factory).execute(
            ArchiveSourceInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_id=source_id,
                author_note=body.author_note,
            )
        )
        return ArchiveSourceResponse(
            source_id=output.source_id,
            status=output.status,
            archived_at=output.archived_at.isoformat(),
            archived_by=output.archived_by,
        )

    @app.post(
        "/api/projects/{project_id}/sources",
        response_model=CreateSourceResponse,
        status_code=201,
    )
    def create_source(
        project_id: UUID,
        body: CreateSourceBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CreateSourceResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "Source creation requires configured object store.",
            )
        output = CreateSource(uow_factory, object_store).execute(
            CreateSourceInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                title=body.title,
                source_type=body.source_type,
                source_scope=body.source_scope,
                ownership_status=body.ownership_status,
                text=body.text,
                version_label=body.version_label,
            )
        )
        return CreateSourceResponse(
            source_id=output.source_id,
            version_id=output.version_id,
            source_delta_id=output.source_delta_id,
            memory_writeback_job_id=output.memory_writeback_job_id,
            raw_hash=output.raw_hash,
        )

    @app.post(
        "/api/projects/{project_id}/sources/{source_id}/versions",
        response_model=CreateSourceVersionResponse,
        status_code=201,
    )
    def create_source_version(
        project_id: UUID,
        source_id: UUID,
        body: CreateSourceVersionBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CreateSourceVersionResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "Source version creation requires configured object store.",
            )
        output = CreateSourceVersion(uow_factory, object_store).execute(
            CreateSourceVersionInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_id=source_id,
                text=body.text,
                version_label=body.version_label,
                supersedes_version_id=body.supersedes_version_id,
            )
        )
        return CreateSourceVersionResponse(
            source_id=output.source_id,
            version_id=output.version_id,
            raw_hash=output.raw_hash,
            supersedes_version_id=output.supersedes_version_id,
        )

    @app.post(
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/restore",
        response_model=RestoreSourceVersionResponse,
        status_code=201,
    )
    def restore_source_version(
        project_id: UUID,
        source_id: UUID,
        version_id: UUID,
        body: RestoreSourceVersionBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> RestoreSourceVersionResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "Source version restore requires configured object store.",
            )
        output = RestoreSourceVersion(uow_factory, object_store).execute(
            RestoreSourceVersionInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_id=source_id,
                version_id=version_id,
                author_note=body.author_note,
            )
        )
        return RestoreSourceVersionResponse(
            source_id=output.source_id,
            restored_from_version_id=output.restored_from_version_id,
            source_delta_id=output.source_delta_id,
            new_version_id=output.new_version_id,
            memory_writeback_job_id=output.memory_writeback_job_id,
        )

    @app.post(
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}/source-deltas",
        response_model=CreateSourceDeltaResponse,
        status_code=201,
    )
    def create_source_delta(
        project_id: UUID,
        source_id: UUID,
        version_id: UUID,
        body: CreateSourceDeltaBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CreateSourceDeltaResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceDelta creation requires configured object store.",
            )
        output = CreateSourceDelta(uow_factory, object_store).execute(
            CreateSourceDeltaInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_id=source_id,
                previous_version_id=version_id,
                delta_kind=body.delta_kind,
                range_start=body.range_start,
                range_end=body.range_end,
                base_hash=body.base_hash,
                submitted_text=body.submitted_text,
                source_type=body.source_type,
                source_scope=body.source_scope,
                provenance=body.provenance,
            )
        )
        return CreateSourceDeltaResponse(
            source_delta_id=output.source_delta_id,
            new_version_id=output.new_version_id,
            memory_writeback_job_id=output.memory_writeback_job_id,
        )

    @app.post(
        "/api/projects/{project_id}/source-deltas",
        response_model=CreateSourceDeltaResponse,
        status_code=201,
    )
    def create_project_source_delta(
        project_id: UUID,
        body: ProjectSourceDeltaBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CreateSourceDeltaResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceDelta creation requires configured object store.",
            )
        output = CreateSourceDelta(uow_factory, object_store).execute(
            CreateSourceDeltaInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                source_id=body.source_id,
                previous_version_id=body.previous_version_id,
                delta_kind=body.delta_kind,
                range_start=body.range_start,
                range_end=body.range_end,
                base_hash=body.base_hash,
                submitted_text=body.submitted_text,
                source_type=body.source_type,
                source_scope=body.source_scope,
                provenance=body.provenance,
            )
        )
        return CreateSourceDeltaResponse(
            source_delta_id=output.source_delta_id,
            new_version_id=output.new_version_id,
            memory_writeback_job_id=output.memory_writeback_job_id,
        )

    @app.post(
        "/api/projects/{project_id}/action-requests",
        response_model=ActionRequestResponse,
        status_code=201,
    )
    def submit_action_request(
        project_id: UUID,
        body: ActionRequestCreateBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        started_at = perf_counter()
        try:
            output = SubmitActionRequest(uow_factory).execute(
                SubmitActionRequestInput(
                    project_id=project_id,
                    actor_id=authenticated_actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    trigger=body.trigger,
                    action_type=body.action_type,
                    target=body.target,
                    constraints=body.constraints,
                    expected_output=body.expected_output,
                    actor_intent=body.actor_intent,
                    source_id=body.source_id,
                    source_version_id=body.source_version_id,
                    scene_id=body.scene_id,
                    chapter_id=body.chapter_id,
                    pov_character_id=body.pov_character_id,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_action_request_latency_ms",
                started_at,
                labels={
                    "action_type": body.action_type,
                    "status": exc.code,
                    "trigger": body.trigger,
                },
            )
            raise
        observe_latency_ms(
            "sextant_action_request_latency_ms",
            started_at,
            labels={
                "action_type": body.action_type,
                "status": "success",
                "trigger": body.trigger,
            },
        )
        return ActionRequestResponse(
            action_request_id=output.action_request_id,
            status=output.status,
        )

    @app.get(
        "/api/projects/{project_id}/action-requests/{action_request_id}",
        response_model=ActionRequestDetailResponse,
    )
    def get_action_request(
        project_id: UUID,
        action_request_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ActionRequestDetailResponse:
        output = GetActionRequest(uow_factory).execute(
            GetActionRequestInput(
                project_id=project_id,
                actor_id=actor_id,
                action_request_id=action_request_id,
            )
        )
        return ActionRequestDetailResponse(
            action_request_id=output.id,
            project_id=output.project_id,
            source_id=output.source_id,
            source_version_id=output.source_version_id,
            scene_id=output.scene_id,
            chapter_id=output.chapter_id,
            pov_character_id=output.pov_character_id,
            actor_intent=output.actor_intent,
            trigger=output.trigger,
            action_type=output.action_type,
            target=output.target,
            constraints=output.constraints,
            expected_output=output.expected_output,
            status=output.status,
            created_by=output.created_by,
        )

    @app.post(
        "/api/projects/{project_id}/action-requests/{action_request_id}/run",
        response_model=ActionRequestRunResponse,
    )
    def run_action_request(
        project_id: UUID,
        action_request_id: UUID,
        body: ActionRequestRunBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestRunResponse:
        started_at = perf_counter()
        try:
            output = RunActionRequest(
                uow_factory,
                object_store,
                story_draft_provider,
            ).execute(
                RunActionRequestInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=action_request_id,
                    current_text_window=body.current_text_window,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_action_request_run_latency_ms",
                started_at,
                labels={"output_type": "unknown", "status": exc.code},
            )
            raise
        observe_latency_ms(
            "sextant_action_request_run_latency_ms",
            started_at,
            labels={"output_type": output.output_type, "status": "success"},
        )
        return _action_request_run_response(output)

    def submit_and_run_agent_action(
        *,
        project_id: UUID,
        body: AgentActionRunBody,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
        action_type: str,
        expected_output: str,
    ) -> ActionRequestRunResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        submit_started_at = perf_counter()
        try:
            submitted = SubmitActionRequest(uow_factory).execute(
                SubmitActionRequestInput(
                    project_id=project_id,
                    actor_id=authenticated_actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    trigger=body.trigger,
                    action_type=action_type,
                    target=body.target,
                    constraints=body.constraints,
                    expected_output=expected_output,
                    actor_intent=body.actor_intent,
                    source_id=body.source_id,
                    source_version_id=body.source_version_id,
                    scene_id=body.scene_id,
                    chapter_id=body.chapter_id,
                    pov_character_id=body.pov_character_id,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_action_request_latency_ms",
                submit_started_at,
                labels={
                    "action_type": action_type,
                    "status": exc.code,
                    "trigger": body.trigger,
                },
            )
            raise
        observe_latency_ms(
            "sextant_action_request_latency_ms",
            submit_started_at,
            labels={
                "action_type": action_type,
                "status": "success",
                "trigger": body.trigger,
            },
        )

        run_started_at = perf_counter()
        try:
            output = RunActionRequest(
                uow_factory,
                object_store,
                story_draft_provider,
            ).execute(
                RunActionRequestInput(
                    project_id=project_id,
                    actor_id=authenticated_actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=submitted.action_request_id,
                    current_text_window=body.current_text_window,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_action_request_run_latency_ms",
                run_started_at,
                labels={"output_type": expected_output, "status": exc.code},
            )
            raise
        observe_latency_ms(
            "sextant_action_request_run_latency_ms",
            run_started_at,
            labels={"output_type": output.output_type, "status": "success"},
        )
        return _action_request_run_response(output)

    @app.post(
        "/api/projects/{project_id}/agent/suggest-next-beat",
        response_model=ActionRequestRunResponse,
    )
    def suggest_next_beat(
        project_id: UUID,
        body: AgentActionRunBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestRunResponse:
        return submit_and_run_agent_action(
            project_id=project_id,
            body=body,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            action_type="suggest_next_direction",
            expected_output="beat_candidates",
        )

    @app.post(
        "/api/projects/{project_id}/agent/draft-next-passage",
        response_model=ActionRequestRunResponse,
    )
    def draft_next_passage(
        project_id: UUID,
        body: AgentActionRunBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestRunResponse:
        return submit_and_run_agent_action(
            project_id=project_id,
            body=body,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            action_type="draft_next_passage",
            expected_output="draft_candidates",
        )

    @app.post(
        "/api/projects/{project_id}/agent/rewrite-current-page",
        response_model=ActionRequestRunResponse,
    )
    def rewrite_current_page(
        project_id: UUID,
        body: AgentActionRunBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestRunResponse:
        return submit_and_run_agent_action(
            project_id=project_id,
            body=body,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            action_type="rewrite_current_page",
            expected_output="draft_candidates",
        )

    @app.post(
        "/api/projects/{project_id}/agent/check-risk",
        response_model=ActionRequestRunResponse,
    )
    def check_risk(
        project_id: UUID,
        body: AgentActionRunBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ActionRequestRunResponse:
        return submit_and_run_agent_action(
            project_id=project_id,
            body=body,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            action_type="check_risk",
            expected_output="risk_findings",
        )

    @app.get(
        "/api/projects/{project_id}/sources/{source_id}/versions",
        response_model=SourceVersionListResponse,
    )
    def list_source_versions(
        project_id: UUID,
        source_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        limit: int = 20,
    ) -> SourceVersionListResponse:
        output = ListSourceVersions(uow_factory).execute(
            ListSourceVersionsInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
                limit=limit,
            )
        )
        return SourceVersionListResponse(
            items=[
                SourceVersionSummaryResponse(
                    source_id=item.source_id,
                    version_id=item.version_id,
                    version_label=item.version_label,
                    raw_hash=item.raw_hash,
                    raw_text_ref=item.raw_text_ref,
                    supersedes_version_id=item.supersedes_version_id,
                    created_at=item.created_at.isoformat(),
                )
                for item in output.items
            ]
        )

    @app.get(
        "/api/projects/{project_id}/sources/{source_id}/versions/{version_id}",
        response_model=SourceVersionResponse,
    )
    def get_source_version(
        project_id: UUID,
        source_id: UUID,
        version_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> SourceVersionResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceVersion detail requires configured object store.",
            )
        output = GetSourceVersion(uow_factory, object_store).execute(
            GetSourceVersionInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
                version_id=version_id,
            )
        )
        return SourceVersionResponse(
            source_id=output.source_id,
            version_id=output.version_id,
            title=output.title,
            source_type=output.source_type,
            source_scope=output.source_scope,
            version_label=output.version_label,
            raw_hash=output.raw_hash,
            text=output.text,
        )

    @app.get(
        "/api/projects/{project_id}/sources/{source_id}/versions/{base_version_id}/diff/{compare_version_id}",
        response_model=SourceVersionDiffResponse,
    )
    def get_source_version_diff(
        project_id: UUID,
        source_id: UUID,
        base_version_id: UUID,
        compare_version_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> SourceVersionDiffResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceVersion diff requires configured object store.",
            )
        output = GetSourceVersionDiff(uow_factory, object_store).execute(
            SourceVersionDiffInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
                base_version_id=base_version_id,
                compare_version_id=compare_version_id,
            )
        )
        return SourceVersionDiffResponse(
            source_id=output.source_id,
            base_version_id=output.base_version_id,
            compare_version_id=output.compare_version_id,
            base_version_label=output.base_version_label,
            compare_version_label=output.compare_version_label,
            base_raw_hash=output.base_raw_hash,
            compare_raw_hash=output.compare_raw_hash,
            summary=SourceVersionDiffSummaryResponse(
                insertions=output.summary.insertions,
                deletions=output.summary.deletions,
                changed=output.summary.changed,
            ),
            hunks=[
                SourceVersionDiffHunkResponse(
                    old_start=hunk.old_start,
                    old_lines=hunk.old_lines,
                    new_start=hunk.new_start,
                    new_lines=hunk.new_lines,
                    lines=[
                        SourceVersionDiffLineResponse(
                            kind=line.kind,
                            old_line=line.old_line,
                            new_line=line.new_line,
                            text=line.text,
                        )
                        for line in hunk.lines
                    ],
                )
                for hunk in output.hunks
            ],
        )

    @app.get(
        "/api/projects/{project_id}/candidates/{candidate_id}",
        response_model=CandidateDetailResponse,
    )
    def get_candidate(
        project_id: UUID,
        candidate_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> CandidateDetailResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "Candidate detail requires configured object store.",
            )
        output = GetCandidate(uow_factory, object_store).execute(
            GetCandidateInput(
                project_id=project_id,
                actor_id=actor_id,
                candidate_id=candidate_id,
            )
        )
        return CandidateDetailResponse(
            id=output.id,
            action_request_id=output.action_request_id,
            mode=output.mode,
            text=output.text,
            status=output.status,
            context_pack_id=output.context_pack_id,
            target_source_id=output.target_source_id,
            target_version_id=output.target_version_id,
            target_scene_id=output.target_scene_id,
            affected_range=output.affected_range,
            base_hash=output.base_hash,
            memory_refs=output.memory_refs,
            evidence_refs=output.evidence_refs,
            override_reason=output.override_reason,
            agent_review_findings=[
                AgentReviewFindingResponse(
                    id=finding.id,
                    risk_level=finding.risk_level,
                    risk_type=finding.risk_type,
                    summary=finding.summary,
                    memory_refs=finding.memory_refs,
                    storytelling_refs=finding.storytelling_refs,
                    suggested_revision=finding.suggested_revision,
                    can_offer_to_author=finding.can_offer_to_author,
                    maps_to_review_type_if_accepted=(finding.maps_to_review_type_if_accepted),
                    draft_local_only=finding.draft_local_only,
                )
                for finding in output.agent_review_findings
            ],
        )

    @app.get(
        "/api/projects/{project_id}/candidates/{candidate_id}/explain",
        response_model=CandidateDetailResponse,
    )
    def explain_candidate_read(
        project_id: UUID,
        candidate_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> CandidateDetailResponse:
        return get_candidate(project_id, candidate_id, actor_id)

    @app.post(
        "/api/projects/{project_id}/candidates/{candidate_id}/explain",
        response_model=CandidateDetailResponse,
    )
    def explain_candidate(
        project_id: UUID,
        candidate_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> CandidateDetailResponse:
        return get_candidate(project_id, candidate_id, actor_id)

    @app.post(
        "/api/projects/{project_id}/candidates/{candidate_id}/reject",
        response_model=CandidateOperationResponse,
    )
    def reject_candidate(
        project_id: UUID,
        candidate_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        body: CandidateRejectBody | None = None,
    ) -> CandidateOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id if body else None, actor_id)
        output = OperateCandidate(uow_factory, object_store).execute(
            CandidateOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                candidate_id=candidate_id,
                operation="reject",
                author_note=body.author_note if body else None,
            )
        )
        return CandidateOperationResponse(
            candidate_id=output.candidate_id,
            status=output.status,
            replacement_candidate_id=output.replacement_candidate_id,
            override_reason=output.override_reason,
        )

    @app.post(
        "/api/projects/{project_id}/candidates/{candidate_id}/override-block",
        response_model=CandidateOperationResponse,
    )
    def override_candidate_block(
        project_id: UUID,
        candidate_id: UUID,
        body: CandidateOverrideBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CandidateOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        output = OperateCandidate(uow_factory, object_store).execute(
            CandidateOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                candidate_id=candidate_id,
                operation="override_block",
                override_reason=body.override_reason,
            )
        )
        return CandidateOperationResponse(
            candidate_id=output.candidate_id,
            status=output.status,
            replacement_candidate_id=output.replacement_candidate_id,
            override_reason=output.override_reason,
        )

    @app.post(
        "/api/projects/{project_id}/candidates/{candidate_id}/revise",
        response_model=CandidateOperationResponse,
    )
    def revise_candidate(
        project_id: UUID,
        candidate_id: UUID,
        body: CandidateReviseBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CandidateOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        output = OperateCandidate(uow_factory, object_store).execute(
            CandidateOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                candidate_id=candidate_id,
                operation="revise",
                revised_text_ref=body.revised_text_ref,
                revised_text=body.revised_text,
                author_note=body.author_note,
            )
        )
        return CandidateOperationResponse(
            candidate_id=output.candidate_id,
            status=output.status,
            replacement_candidate_id=output.replacement_candidate_id,
            override_reason=output.override_reason,
        )

    @app.post(
        "/api/projects/{project_id}/candidates/{candidate_id}/accept",
        response_model=CandidateAcceptResponse,
    )
    def accept_candidate(
        project_id: UUID,
        candidate_id: UUID,
        body: CandidateAcceptBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> CandidateAcceptResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        started_at = perf_counter()
        try:
            output = AcceptCandidate(uow_factory, object_store).execute(
                AcceptCandidateInput(
                    project_id=project_id,
                    actor_id=authenticated_actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    candidate_id=candidate_id,
                    accepted_text_ref=body.accepted_text_ref,
                    accepted_text=body.accepted_text,
                    accept_mode=body.accept_mode,
                    target_source_id=body.target_source_id,
                    target_version_id=body.target_version_id,
                    insert_or_replace_range=body.insert_or_replace_range,
                    source_type=body.source_type,
                    source_scope=body.source_scope,
                    author_edited=body.author_edited,
                    base_hash=body.base_hash,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_candidate_acceptance_latency_ms",
                started_at,
                labels={"accept_mode": body.accept_mode, "status": exc.code},
            )
            raise
        observe_latency_ms(
            "sextant_candidate_acceptance_latency_ms",
            started_at,
            labels={"accept_mode": body.accept_mode, "status": "success"},
        )
        return CandidateAcceptResponse(
            accepted_fragment_id=output.accepted_fragment_id,
            source_delta_id=output.source_delta_id,
            new_version_id=output.new_version_id,
            memory_writeback_job_id=output.memory_writeback_job_id,
        )

    @app.get(
        "/api/projects/{project_id}/jobs/{job_id}",
        response_model=JobDetailResponse,
    )
    def get_job(
        project_id: UUID,
        job_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> JobDetailResponse:
        output = GetJobDetail(uow_factory).execute(
            JobDetailInput(project_id=project_id, actor_id=actor_id, job_id=job_id)
        )
        return _job_response(output)

    @app.post(
        "/api/projects/{project_id}/jobs/{job_id}/cancel",
        response_model=JobDetailResponse,
    )
    def cancel_job(
        project_id: UUID,
        job_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        body: JobOperationBody | None = None,
    ) -> JobDetailResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id if body else None, actor_id)
        output = OperateJob(uow_factory).execute(
            JobOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                job_id=job_id,
                operation="cancel",
                author_note=body.author_note if body else None,
            )
        )
        return _job_response(output)

    @app.post(
        "/api/projects/{project_id}/jobs/{job_id}/retry",
        response_model=JobDetailResponse,
    )
    def retry_job(
        project_id: UUID,
        job_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        body: JobOperationBody | None = None,
    ) -> JobDetailResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id if body else None, actor_id)
        output = OperateJob(uow_factory).execute(
            JobOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                job_id=job_id,
                operation="retry",
                author_note=body.author_note if body else None,
            )
        )
        return _job_response(output)

    @app.get(
        "/api/projects/{project_id}/source-deltas",
        response_model=SourceDeltaListResponse,
    )
    def list_source_deltas(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        source_id: UUID | None = None,
        source_version_id: UUID | None = None,
        status: str | None = None,
        delta_kind: str | None = None,
        query: str | None = None,
        cursor: str | None = None,
        accepted_only: bool = False,
        limit: int = 50,
    ) -> SourceDeltaListResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceDelta list requires configured object store.",
            )
        output = ListSourceDeltas(uow_factory, object_store).execute(
            ListSourceDeltasInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
                source_version_id=source_version_id,
                status=status,
                delta_kind=delta_kind,
                query=query,
                cursor=cursor,
                accepted_only=accepted_only,
                limit=limit,
            )
        )
        return SourceDeltaListResponse(
            items=[_source_delta_summary_response(item) for item in output.items],
            next_cursor=output.next_cursor,
        )

    @app.get(
        "/api/projects/{project_id}/source-deltas/{source_delta_id}",
        response_model=SourceDeltaDetailResponse,
    )
    def get_source_delta(
        project_id: UUID,
        source_delta_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> SourceDeltaDetailResponse:
        if object_store is None:
            raise ApplicationError(
                "schema_validation_failed",
                "SourceDelta detail requires configured object store.",
            )
        output = GetSourceDeltaDetail(uow_factory, object_store).execute(
            SourceDeltaDetailInput(
                project_id=project_id,
                actor_id=actor_id,
                source_delta_id=source_delta_id,
            )
        )
        return _source_delta_detail_response(output)

    @app.get(
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview",
        response_model=MemoryWritebackPreviewResponse,
    )
    def get_memory_writeback_preview(
        project_id: UUID,
        source_delta_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> MemoryWritebackPreviewResponse:
        output = GetMemoryWritebackPreview(uow_factory).execute(
            MemoryWritebackPreviewInput(
                project_id=project_id,
                actor_id=actor_id,
                source_delta_id=source_delta_id,
            )
        )
        return MemoryWritebackPreviewResponse(
            source_delta_id=output.source_delta_id,
            source_delta_status=output.source_delta_status,
            source_delta=output.source_delta,
            job=_job_response(output.job) if output.job else None,
            source_spans=output.source_spans,
            evidence_log_entries=output.evidence_log_entries,
            fact_assertions=output.fact_assertions,
            review_items=[_review_item_detail_response(item) for item in output.review_items],
            memory_pages=output.memory_pages,
            graph_edges=output.graph_edges,
        )

    @app.get(
        "/api/projects/{project_id}/memory/pages",
        response_model=MemoryPageListResponse,
    )
    def list_memory_pages(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        page_type: str | None = None,
        canon_status: str | None = None,
        limit: int = 50,
    ) -> MemoryPageListResponse:
        output = ListMemoryPages(uow_factory).execute(
            ListMemoryPagesInput(
                project_id=project_id,
                actor_id=actor_id,
                page_type=page_type,
                canon_status=canon_status,
                limit=limit,
            )
        )
        return MemoryPageListResponse(
            items=[_memory_page_summary_response(item) for item in output.items]
        )

    @app.get(
        "/api/projects/{project_id}/memory/pages/{memory_page_id}",
        response_model=MemoryPageDetailResponse,
    )
    def get_memory_page(
        project_id: UUID,
        memory_page_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> MemoryPageDetailResponse:
        output = GetMemoryPageDetail(uow_factory).execute(
            MemoryPageDetailInput(
                project_id=project_id,
                actor_id=actor_id,
                memory_page_id=memory_page_id,
            )
        )
        return _memory_page_detail_response(output)

    @app.post(
        "/api/projects/{project_id}/memory/pages/{memory_page_id}/open-threads/{thread_id}/operate",
        response_model=MemoryPageThreadOperationResponse,
    )
    def operate_memory_page_open_thread(
        project_id: UUID,
        memory_page_id: UUID,
        thread_id: str,
        body: MemoryPageThreadOperationBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> MemoryPageThreadOperationResponse:
        output = OperateMemoryPageThread(uow_factory).execute(
            MemoryPageThreadOperationInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                memory_page_id=memory_page_id,
                thread_id=thread_id,
                update_type=body.update_type,
                author_note=body.author_note,
                summary=body.summary,
            )
        )
        return MemoryPageThreadOperationResponse(
            memory_page_id=output.memory_page_id,
            thread_id=output.thread_id,
            status=output.status,
            update_type=output.update_type,
            memory_page=_memory_page_detail_response(output.memory_page),
            side_effects=output.side_effects,
        )

    @app.get(
        "/api/projects/{project_id}/graph/edges",
        response_model=GraphProjectionEdgeListResponse,
    )
    def list_graph_projection_edges(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        q: str | None = None,
        relation: str | None = None,
        edge_status: str | None = None,
        limit: int = 50,
    ) -> GraphProjectionEdgeListResponse:
        output = ListGraphProjectionEdges(uow_factory).execute(
            ListGraphProjectionEdgesInput(
                project_id=project_id,
                actor_id=actor_id,
                query=q,
                relation=relation,
                edge_status=edge_status,
                limit=limit,
            )
        )
        return GraphProjectionEdgeListResponse(
            items=[_graph_projection_edge_response(item) for item in output.items]
        )

    @app.post(
        "/api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions",
        response_model=MemoryWritebackDecisionResponse,
    )
    def decide_memory_writeback_preview(
        project_id: UUID,
        source_delta_id: UUID,
        body: MemoryWritebackDecisionBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> MemoryWritebackDecisionResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        started_at = perf_counter()
        item_type = _metric_item_type(body.item_ref)
        try:
            output = ConfirmMemoryWritebackDecision(uow_factory).execute(
                MemoryWritebackDecisionInput(
                    project_id=project_id,
                    actor_id=authenticated_actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    source_delta_id=source_delta_id,
                    item_ref=body.item_ref,
                    decision=body.decision,
                    author_note=body.author_note,
                    correction=body.correction,
                    replacement_refs=body.replacement_refs,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_memory_writeback_decision_latency_ms",
                started_at,
                labels={"decision": body.decision, "item_type": item_type, "status": exc.code},
            )
            raise
        observe_latency_ms(
            "sextant_memory_writeback_decision_latency_ms",
            started_at,
            labels={"decision": body.decision, "item_type": item_type, "status": "success"},
        )
        return MemoryWritebackDecisionResponse(
            decision_id=output.decision_id,
            source_delta_id=output.source_delta_id,
            item_ref=output.item_ref,
            decision=output.decision,
            status=output.status,
            side_effects=output.side_effects,
        )

    @app.get(
        "/api/projects/{project_id}/review-items",
        response_model=ReviewItemListResponse,
    )
    def list_review_items(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        status: str | None = None,
    ) -> ReviewItemListResponse:
        output = ListReviewItems(uow_factory).execute(
            ListReviewItemsInput(project_id=project_id, actor_id=actor_id, status=status)
        )
        return ReviewItemListResponse(
            items=[_review_item_detail_response(item) for item in output.items]
        )

    @app.get(
        "/api/projects/{project_id}/entities",
        response_model=CanonicalEntityListResponse,
    )
    def list_entities(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        q: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> CanonicalEntityListResponse:
        output = ListCanonicalEntities(uow_factory).execute(
            ListCanonicalEntitiesInput(
                project_id=project_id,
                actor_id=actor_id,
                query=q,
                entity_type=entity_type,
                limit=limit,
            )
        )
        return CanonicalEntityListResponse(
            items=[_canonical_entity_summary_response(item) for item in output.items]
        )

    @app.get(
        "/api/projects/{project_id}/scenes",
        response_model=StorySceneListResponse,
    )
    def list_scenes(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        source_id: UUID | None = None,
        version_id: UUID | None = None,
        limit: int = 100,
    ) -> StorySceneListResponse:
        output = ListStoryScenes(uow_factory).execute(
            ListStoryScenesInput(
                project_id=project_id,
                actor_id=actor_id,
                source_id=source_id,
                version_id=version_id,
                limit=limit,
            )
        )
        return StorySceneListResponse(
            items=[_story_scene_summary_response(item) for item in output.items]
        )

    @app.get(
        "/api/projects/{project_id}/story-schema/packs",
        response_model=StorySchemaPackListResponse,
    )
    def list_story_schema_packs(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        pack_type: str | None = None,
    ) -> StorySchemaPackListResponse:
        output = ListStorySchemaPacks(uow_factory).execute(
            ListStorySchemaPacksInput(
                project_id=project_id,
                actor_id=actor_id,
                pack_type=pack_type,
            )
        )
        return StorySchemaPackListResponse(
            items=[_story_schema_pack_response(item) for item in output.items]
        )

    @app.post(
        "/api/projects/{project_id}/story-schema/genre-packs",
        response_model=StorySchemaPackResponse,
    )
    def create_story_schema_genre_pack(
        project_id: UUID,
        body: StorySchemaGenrePackBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> StorySchemaPackResponse:
        output = CreateStorySchemaGenrePack(uow_factory, system_admin_actor_ids).execute(
            CreateStorySchemaGenrePackInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                pack_name=body.pack_name,
                version=body.version,
                entity_types=body.entity_types,
                event_types=body.event_types,
                relations=body.relations,
                extraction_hints=body.extraction_hints,
                risk_rules=body.risk_rules,
            )
        )
        return _story_schema_pack_response(output)

    @app.post(
        "/api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate",
        response_model=StorySchemaPackResponse,
    )
    def deprecate_story_schema_genre_pack(
        project_id: UUID,
        pack_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> StorySchemaPackResponse:
        output = DeprecateStorySchemaGenrePack(uow_factory, system_admin_actor_ids).execute(
            DeprecateStorySchemaGenrePackInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                story_schema_pack_id=pack_id,
            )
        )
        return _story_schema_pack_response(output)

    @app.get(
        "/api/projects/{project_id}/story-schema",
        response_model=ProjectStorySchemaResponse,
    )
    def get_project_story_schema(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ProjectStorySchemaResponse:
        output = GetProjectStorySchema(uow_factory).execute(
            GetProjectStorySchemaInput(project_id=project_id, actor_id=actor_id)
        )
        return _project_story_schema_response(output)

    @app.put(
        "/api/projects/{project_id}/story-schema/genre-pack",
        response_model=ProjectStorySchemaResponse,
    )
    def select_project_story_schema_genre(
        project_id: UUID,
        body: ProjectStorySchemaGenreBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectStorySchemaResponse:
        output = SelectProjectStorySchemaGenre(uow_factory).execute(
            SelectProjectStorySchemaGenreInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                genre_schema_pack_id=body.genre_schema_pack_id,
            )
        )
        return _project_story_schema_response(output)

    @app.put(
        "/api/projects/{project_id}/story-schema/project-override",
        response_model=ProjectStorySchemaResponse,
    )
    def upsert_project_story_schema_override(
        project_id: UUID,
        body: ProjectStorySchemaOverrideBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ProjectStorySchemaResponse:
        output = UpsertProjectStorySchemaOverride(uow_factory).execute(
            UpsertProjectStorySchemaOverrideInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                pack_name=body.pack_name,
                entity_types=body.entity_types,
                event_types=body.event_types,
                relations=body.relations,
                extraction_hints=body.extraction_hints,
                risk_rules=body.risk_rules,
            )
        )
        return _project_story_schema_response(output)

    @app.get(
        "/api/projects/{project_id}/review-items/{review_item_id}",
        response_model=ReviewItemDetailResponse,
    )
    def get_review_item(
        project_id: UUID,
        review_item_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> ReviewItemDetailResponse:
        output = GetReviewItemDetail(uow_factory).execute(
            ReviewItemDetailInput(
                project_id=project_id,
                actor_id=actor_id,
                review_item_id=review_item_id,
            )
        )
        return _review_item_detail_response(output)

    @app.post(
        "/api/projects/{project_id}/review-items/{review_item_id}/resolve",
        response_model=ReviewItemOperationResponse,
    )
    def resolve_review_item(
        project_id: UUID,
        review_item_id: UUID,
        body: ReviewItemResolveBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> ReviewItemOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id, actor_id)
        output = OperateReviewItem(uow_factory).execute(
            ReviewItemOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                review_item_id=review_item_id,
                operation="resolve",
                resolution=body.resolution,
                author_note=body.author_note,
                replacement_refs=body.replacement_refs,
                correction=body.correction,
            )
        )
        return ReviewItemOperationResponse(
            review_item_id=output.review_item_id,
            status=output.status,
            resolution=output.resolution,
            side_effects=output.side_effects,
        )

    @app.post(
        "/api/projects/{project_id}/review-items/{review_item_id}/dismiss",
        response_model=ReviewItemOperationResponse,
    )
    def dismiss_review_item(
        project_id: UUID,
        review_item_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        body: ReviewItemNoteBody | None = None,
    ) -> ReviewItemOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id if body else None, actor_id)
        output = OperateReviewItem(uow_factory).execute(
            ReviewItemOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                review_item_id=review_item_id,
                operation="dismiss",
                author_note=body.author_note if body else None,
            )
        )
        return ReviewItemOperationResponse(
            review_item_id=output.review_item_id,
            status=output.status,
            resolution=output.resolution,
            side_effects=output.side_effects,
        )

    @app.post(
        "/api/projects/{project_id}/review-items/{review_item_id}/reopen",
        response_model=ReviewItemOperationResponse,
    )
    def reopen_review_item(
        project_id: UUID,
        review_item_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        body: ReviewItemNoteBody | None = None,
    ) -> ReviewItemOperationResponse:
        authenticated_actor_id = _authenticated_actor_id(body.actor_id if body else None, actor_id)
        output = OperateReviewItem(uow_factory).execute(
            ReviewItemOperationInput(
                project_id=project_id,
                actor_id=authenticated_actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                review_item_id=review_item_id,
                operation="reopen",
                author_note=body.author_note if body else None,
            )
        )
        return ReviewItemOperationResponse(
            review_item_id=output.review_item_id,
            status=output.status,
            resolution=output.resolution,
            side_effects=output.side_effects,
        )

    @app.post(
        "/api/projects/{project_id}/memory/answer",
        response_model=MemoryAnswerResponse,
    )
    def answer_memory(
        project_id: UUID,
        body: MemoryAnswerBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> MemoryAnswerResponse:
        output = AnswerWithEvidence(uow_factory).execute(
            MemoryAnswerInput(
                project_id=project_id,
                actor_id=actor_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                question=body.question,
                subject_ref=body.subject_ref,
                predicate=body.predicate,
                current_scene_id=body.current_scene_id,
                current_pov_character_id=body.current_pov_character_id,
            )
        )
        return MemoryAnswerResponse(
            question=output.question,
            answer=output.answer,
            answer_type=output.answer_type,
            confidence=output.confidence,
            source_span_refs=output.source_span_refs,
            affected_entities=output.affected_entities,
            caveats=output.caveats,
            unknowns=output.unknowns,
            related_review_items=output.related_review_items,
            safe_to_use_in_current_pov=output.safe_to_use_in_current_pov,
        )

    @app.get(
        "/api/projects/{project_id}/context-packs",
        response_model=WritingContextPackListResponse,
    )
    def list_context_packs(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        limit: int = 50,
    ) -> WritingContextPackListResponse:
        output = ListWritingContextPacks(uow_factory).execute(
            ListContextPacksInput(project_id=project_id, actor_id=actor_id, limit=limit)
        )
        return WritingContextPackListResponse(
            items=[
                WritingContextPackSummaryResponse(
                    context_pack_id=item.context_pack_id,
                    schema_version=item.schema_version,
                    mode=item.mode,
                    current_position=item.current_position,
                    evidence_refs=item.evidence_refs,
                )
                for item in output.items
            ]
        )

    @app.get(
        "/api/projects/{project_id}/context-pack-readiness",
        response_model=ContextPackReadinessListResponse,
    )
    def list_context_pack_readiness(
        project_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        status: str | None = None,
        reason: str | None = None,
        source_delta_id: UUID | None = None,
        limit: int = 50,
    ) -> ContextPackReadinessListResponse:
        output = ListContextPackReadiness(uow_factory).execute(
            ListContextPackReadinessInput(
                project_id=project_id,
                actor_id=actor_id,
                status=status,
                reason=reason,
                source_delta_id=source_delta_id,
                limit=limit,
            )
        )
        return ContextPackReadinessListResponse(
            items=[
                ContextPackReadinessResponse(
                    id=item.id,
                    source_span_id=item.source_span_id,
                    source_delta_id=item.source_delta_id,
                    status=item.status,
                    reason=item.reason,
                    affected_refs=item.affected_refs,
                    evidence_refs=item.evidence_refs,
                )
                for item in output.items
            ]
        )

    @app.get(
        "/api/projects/{project_id}/context-packs/{context_pack_id}",
        response_model=WritingContextPackResponse,
    )
    def get_context_pack(
        project_id: UUID,
        context_pack_id: UUID,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
    ) -> WritingContextPackResponse:
        output = GetWritingContextPack(uow_factory).execute(
            ContextPackDetailInput(
                project_id=project_id,
                actor_id=actor_id,
                context_pack_id=context_pack_id,
            )
        )
        return _writing_context_pack_response(output)

    @app.post(
        "/api/projects/{project_id}/context-packs/build",
        response_model=WritingContextPackResponse,
    )
    def build_context_pack(
        project_id: UUID,
        body: BuildWritingContextPackBody,
        actor_id: Annotated[UUID, Header(alias="X-Actor-Id")],
        request_id: Annotated[str, Header(alias="X-Request-Id")],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> WritingContextPackResponse:
        started_at = perf_counter()
        try:
            output = BuildWritingContextPack(uow_factory).execute(
                BuildWritingContextPackInput(
                    project_id=project_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=idempotency_key,
                    action_request_id=body.action_request_id,
                    current_source_id=body.current_source_id,
                    current_version_id=body.current_version_id,
                    current_scene_id=body.current_scene_id,
                    current_pov_character_id=body.current_pov_character_id,
                    mode=body.mode,
                    current_text_window=body.current_text_window,
                    constraints=body.constraints,
                )
            )
        except ApplicationError as exc:
            observe_latency_ms(
                "sextant_context_pack_build_latency_ms",
                started_at,
                labels={"mode": body.mode, "status": exc.code},
            )
            raise
        observe_latency_ms(
            "sextant_context_pack_build_latency_ms",
            started_at,
            labels={"mode": body.mode, "status": "success"},
        )
        return _writing_context_pack_response(output)

    _install_openapi_security(app)
    return app


def _source_delta_summary_response(output: SourceDeltaSummaryOutput) -> SourceDeltaSummaryResponse:
    return SourceDeltaSummaryResponse(
        id=output.id,
        source_id=output.source_id,
        previous_version_id=output.previous_version_id,
        new_version_id=output.new_version_id,
        accepted_fragment_id=output.accepted_fragment_id,
        delta_kind=output.delta_kind,
        status=output.status,
        range_start=output.range_start,
        range_end=output.range_end,
        base_hash=output.base_hash,
        source_type=output.source_type,
        source_scope=output.source_scope,
        provenance=output.provenance,
        submitted_text_ref=output.submitted_text_ref,
        submitted_text_preview=output.submitted_text_preview,
        job=_job_response(output.job) if output.job else None,
    )


def _project_member_response(member: ProjectMemberSnapshot) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        actor_id=member.actor_id,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


def _project_invitation_response(
    invitation: ProjectInvitationSnapshot,
) -> ProjectInvitationResponse:
    return ProjectInvitationResponse(
        id=invitation.id,
        project_id=invitation.project_id,
        member_actor_id=invitation.member_actor_id,
        role=invitation.role,
        delivery_provider_ref=invitation.delivery_provider_ref,
        delivery_target_ref=invitation.delivery_target_ref,
        token_issuer_ref=invitation.token_issuer_ref,
        delivery_proof_ref=invitation.delivery_proof_ref,
        token_proof_ref=invitation.token_proof_ref,
        status=invitation.status,
        delivery_status=invitation.delivery_status,
        token_status=invitation.token_status,
        delivered_at=invitation.delivered_at,
        token_issued_at=invitation.token_issued_at,
        created_at=invitation.created_at,
    )


def _source_summary_response(output: SourceSummaryOutput) -> SourceSummaryResponse:
    return SourceSummaryResponse(
        source_id=output.source_id,
        title=output.title,
        source_type=output.source_type,
        source_scope=output.source_scope,
        ownership_status=output.ownership_status,
        is_archived=output.is_archived,
        archived_at=output.archived_at.isoformat() if output.archived_at else None,
        archived_by=output.archived_by,
        latest_version_id=output.latest_version_id,
        latest_version_label=output.latest_version_label,
        latest_raw_hash=output.latest_raw_hash,
        version_count=output.version_count,
    )


def _source_delta_detail_response(output: SourceDeltaDetailOutput) -> SourceDeltaDetailResponse:
    return SourceDeltaDetailResponse(
        id=output.id,
        source_id=output.source_id,
        previous_version_id=output.previous_version_id,
        new_version_id=output.new_version_id,
        accepted_fragment_id=output.accepted_fragment_id,
        delta_kind=output.delta_kind,
        status=output.status,
        range_start=output.range_start,
        range_end=output.range_end,
        base_hash=output.base_hash,
        source_type=output.source_type,
        source_scope=output.source_scope,
        provenance=output.provenance,
        submitted_text_ref=output.submitted_text_ref,
        submitted_text=output.submitted_text,
        job=_job_response(output.job) if output.job else None,
    )


def _job_response(output: JobDetailOutput) -> JobDetailResponse:
    return JobDetailResponse(
        id=output.id,
        job_type=output.job_type,
        status=output.status,
        attempt_count=output.attempt_count,
        run_after=output.run_after.isoformat() if output.run_after else None,
        locked_by=output.locked_by,
        locked_at=output.locked_at.isoformat() if output.locked_at else None,
        last_error=output.last_error,
        payload=output.payload,
    )


def _review_item_detail_response(
    output: ReviewItemDetailOutput,
) -> ReviewItemDetailResponse:
    return ReviewItemDetailResponse(
        id=output.id,
        review_type=output.review_type,
        severity=output.severity,
        status=output.status,
        summary=output.summary,
        affected_refs=output.affected_refs,
        new_evidence=output.new_evidence,
        existing_evidence=output.existing_evidence,
        suggested_actions=output.suggested_actions,
        default_action=output.default_action,
        resolution=output.resolution,
        side_effects=output.side_effects,
    )


def _canonical_entity_summary_response(
    output: CanonicalEntitySummaryOutput,
) -> CanonicalEntitySummaryResponse:
    return CanonicalEntitySummaryResponse(
        id=output.id,
        entity_type=output.entity_type,
        display_name=output.display_name,
        canonical_status=output.canonical_status,
        cast_tier=output.cast_tier,
        first_seen_scene_id=output.first_seen_scene_id,
    )


def _story_scene_summary_response(
    output: StorySceneSummaryOutput,
) -> StorySceneSummaryResponse:
    return StorySceneSummaryResponse(
        id=output.id,
        source_id=output.source_id,
        version_id=output.version_id,
        chapter_id=output.chapter_id,
        chapter_index=output.chapter_index,
        chapter_title=output.chapter_title,
        scene_index=output.scene_index,
        position_label=output.position_label,
        story_time=output.story_time,
        scene_summary=output.scene_summary,
        pov_character_id=output.pov_character_id,
        pov_mode=output.pov_mode,
    )


def _project_story_schema_response(
    output: ProjectStorySchemaOutput,
) -> ProjectStorySchemaResponse:
    return ProjectStorySchemaResponse(
        project_id=output.project_id,
        binding_id=output.binding_id,
        base_schema_pack_id=output.base_schema_pack_id,
        genre_schema_pack_id=output.genre_schema_pack_id,
        genre_schema_pack=_story_schema_pack_response(output.genre_schema_pack)
        if output.genre_schema_pack is not None
        else None,
        project_override_pack_id=output.project_override_pack_id,
        project_override_pack=_story_schema_pack_response(output.project_override_pack)
        if output.project_override_pack is not None
        else None,
        effective_schema=output.effective_schema,
    )


def _story_schema_pack_response(output: StorySchemaPackOutput) -> StorySchemaPackResponse:
    return StorySchemaPackResponse(
        id=output.id,
        project_id=output.project_id,
        pack_type=output.pack_type,
        pack_name=output.pack_name,
        version=output.version,
        status=output.status,
        entity_types=output.entity_types,
        event_types=output.event_types,
        relations=output.relations,
        extraction_hints=output.extraction_hints,
        risk_rules=output.risk_rules,
    )


def _memory_page_summary_response(output: MemoryPageSummaryOutput) -> MemoryPageSummaryResponse:
    return MemoryPageSummaryResponse(
        id=output.id,
        page_type=output.page_type,
        target_ref=output.target_ref,
        title=output.title,
        canon_status=output.canon_status,
        memory_depth=output.memory_depth,
        source_refs=output.source_refs,
        open_thread_count=output.open_thread_count,
        contradiction_count=output.contradiction_count,
    )


def _memory_page_detail_response(output: MemoryPageDetailOutput) -> MemoryPageDetailResponse:
    return MemoryPageDetailResponse(
        id=output.id,
        page_type=output.page_type,
        target_ref=output.target_ref,
        title=output.title,
        current_canon=output.current_canon,
        appearance_log=output.appearance_log,
        event_log=output.event_log,
        relationships=output.relationships,
        knowledge_state=output.knowledge_state,
        open_threads=output.open_threads,
        contradictions=output.contradictions,
        source_refs=output.source_refs,
        canon_status=output.canon_status,
        memory_depth=output.memory_depth,
    )


def _graph_projection_edge_response(
    output: GraphProjectionEdgeSummaryOutput,
) -> GraphProjectionEdgeResponse:
    return GraphProjectionEdgeResponse(
        id=output.id,
        run_id=output.run_id,
        source_ref=output.source_ref,
        subject_ref=output.subject_ref,
        relation=output.relation,
        target_ref=output.target_ref,
        edge_status=output.edge_status,
        evidence_refs=output.evidence_refs,
        created_at=output.created_at,
    )


def _action_request_run_response(output: RunActionRequestOutput) -> ActionRequestRunResponse:
    return ActionRequestRunResponse(
        action_request_id=output.action_request_id,
        status=output.status,
        output_type=output.output_type,
        context_pack_id=output.context_pack_id,
        draft_candidate_ids=output.draft_candidate_ids,
        risk_finding_ids=output.risk_finding_ids,
        beat_candidate_ids=output.beat_candidate_ids,
        memory_answer=MemoryAnswerResponse(
            question=output.memory_answer.question,
            answer=output.memory_answer.answer,
            answer_type=output.memory_answer.answer_type,
            confidence=output.memory_answer.confidence,
            source_span_refs=output.memory_answer.source_span_refs,
            affected_entities=output.memory_answer.affected_entities,
            caveats=output.memory_answer.caveats,
            unknowns=output.memory_answer.unknowns,
            related_review_items=output.memory_answer.related_review_items,
            safe_to_use_in_current_pov=output.memory_answer.safe_to_use_in_current_pov,
        )
        if output.memory_answer is not None
        else None,
        risk_findings=[_agent_review_finding_response(finding) for finding in output.risk_findings]
        if output.risk_findings is not None
        else None,
        beat_candidates=[
            BeatCandidateResponse(
                id=beat.id,
                summary=beat.summary,
                driver_character=beat.driver_character,
                agency_rationale=beat.agency_rationale,
                storytelling_rationale=beat.storytelling_rationale,
                cast_decision=beat.cast_decision,
                tension=beat.tension,
                memory_refs=beat.memory_refs,
                evidence_refs=beat.evidence_refs,
                agent_review_findings=[
                    _agent_review_finding_response(finding)
                    for finding in beat.agent_review_findings
                ],
            )
            for beat in output.beat_candidates
        ]
        if output.beat_candidates is not None
        else None,
        candidate_explanation=CandidateExplanationResponse(
            candidate_id=output.candidate_explanation.candidate_id,
            why_this=output.candidate_explanation.why_this,
            used_memory_refs=output.candidate_explanation.used_memory_refs,
            respected_constraints=output.candidate_explanation.respected_constraints,
            avoided_claims=output.candidate_explanation.avoided_claims,
            risks=[
                _agent_review_finding_response(finding)
                for finding in output.candidate_explanation.risks
            ],
        )
        if output.candidate_explanation is not None
        else None,
    )


def _agent_review_finding_response(finding: Any) -> AgentReviewFindingResponse:
    return AgentReviewFindingResponse(
        id=finding.id,
        risk_level=finding.risk_level,
        risk_type=finding.risk_type,
        summary=finding.summary,
        memory_refs=finding.memory_refs,
        storytelling_refs=finding.storytelling_refs,
        suggested_revision=finding.suggested_revision,
        can_offer_to_author=finding.can_offer_to_author,
        maps_to_review_type_if_accepted=finding.maps_to_review_type_if_accepted,
        draft_local_only=finding.draft_local_only,
    )


def _install_openapi_security(app: FastAPI) -> None:
    original_openapi = app.openapi

    def custom_openapi() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {})
        if not isinstance(components, dict):
            return schema
        security_schemes = components.setdefault("securitySchemes", {})
        if isinstance(security_schemes, dict):
            security_schemes["BearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        schema.setdefault("security", [{"BearerAuth": []}])
        return schema

    app.openapi = custom_openapi  # ty: ignore[invalid-assignment]


def _replace_header(
    headers: list[tuple[bytes, bytes]],
    name: bytes,
    value: bytes,
) -> list[tuple[bytes, bytes]]:
    normalized = name.lower()
    return [
        (header_name, header_value)
        for header_name, header_value in headers
        if header_name.lower() != normalized
    ] + [(normalized, value)]


def _authentication_required_response(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "authentication_required",
                "message": message,
                "details": {},
            }
        },
    )


def _schema_validation_failed_response(errors: Sequence[Any]) -> JSONResponse:
    sanitized_errors = []
    for error in errors:
        if not isinstance(error, dict):
            sanitized_errors.append(
                {"loc": [], "msg": "Invalid request.", "type": "validation_error"}
            )
            continue
        sanitized_errors.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": str(error.get("msg", "Invalid request.")),
                "type": str(error.get("type", "validation_error")),
            }
        )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "code": "schema_validation_failed",
                "message": "Request schema validation failed.",
                "details": {"errors": sanitized_errors},
            }
        },
    )


def _writing_context_pack_response(output: WritingContextPackOutput) -> WritingContextPackResponse:
    return WritingContextPackResponse(
        context_pack_id=output.context_pack_id,
        schema_version=output.schema_version,
        current_position=output.current_position,
        canonical_context=output.canonical_context,
        pov_constraint=output.pov_constraint,
        active_characters=output.active_characters,
        character_agency_state=output.character_agency_state,
        recent_events=output.recent_events,
        character_knowledge=output.character_knowledge,
        object_location_state=output.object_location_state,
        open_threads=output.open_threads,
        risk_context=output.risk_context,
        style_memory=output.style_memory,
        evidence_refs=output.evidence_refs,
    )


def _authenticated_actor_id(body_actor_id: UUID | None, actor_id: UUID) -> UUID:
    if body_actor_id is not None and body_actor_id != actor_id:
        raise ApplicationError(
            "permission_denied",
            "Request actor does not match authenticated actor.",
        )
    return actor_id


def _path_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else request.url.path


def _uuid_or_none(value: object) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _metric_item_type(value: object) -> str:
    if isinstance(value, Mapping):
        item_type = cast(Mapping[str, object], value).get("type")
        if isinstance(item_type, str) and item_type:
            return item_type
    return "unknown"


def _status_for_error(code: str) -> int:
    return {
        "permission_denied": 403,
        "not_found": 404,
        "idempotency_conflict": 409,
        "invalid_state_transition": 409,
        "stale_source_version": 409,
        "source_version_already_current": 409,
        "candidate_not_offerable": 409,
        "blocked_without_override": 409,
        "policy_blocked_promotion": 409,
        "unsupported_action_type": 400,
        "expected_output_mismatch": 400,
        "missing_target": 400,
        "invalid_target_range": 400,
        "schema_validation_failed": 400,
        "llm_output_invalid": 502,
    }.get(code, 400)
