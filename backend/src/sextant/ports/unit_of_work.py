from __future__ import annotations

from typing import Protocol, Self
from uuid import UUID

from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    AcceptCandidateOutput,
    ActionRequestSnapshot,
    ArchiveSourceInput,
    ArchiveSourceOutput,
    BuildWritingContextPackInput,
    CandidateDetailSnapshot,
    CandidateOperationInput,
    CandidateOperationOutput,
    CandidateSnapshot,
    ContextPackDetailInput,
    CreateProjectInvitationInput,
    CreateSourceDeltaInput,
    CreateSourceDeltaOutput,
    CreateSourceInput,
    CreateSourceOutput,
    CreateSourceVersionInput,
    CreateSourceVersionOutput,
    CreateStorySchemaGenrePackInput,
    DeprecateStorySchemaGenrePackInput,
    GetProjectInput,
    GetProjectStorySchemaInput,
    GetSourceInput,
    GetSourceVersionInput,
    IdempotencySnapshot,
    JobDetailInput,
    JobDetailOutput,
    JobOperationInput,
    ListCanonicalEntitiesInput,
    ListCanonicalEntitiesOutput,
    ListContextPackReadinessInput,
    ListContextPackReadinessOutput,
    ListContextPacksInput,
    ListContextPacksOutput,
    ListGraphProjectionEdgesInput,
    ListGraphProjectionEdgesOutput,
    ListMemoryPagesInput,
    ListMemoryPagesOutput,
    ListProjectInvitationsInput,
    ListProjectInvitationsOutput,
    ListProjectMembersInput,
    ListProjectMembersOutput,
    ListReviewItemsInput,
    ListReviewItemsOutput,
    ListSourceDeltasInput,
    ListSourcesInput,
    ListSourcesOutput,
    ListSourceVersionsInput,
    ListSourceVersionsOutput,
    ListStoryScenesInput,
    ListStoryScenesOutput,
    ListStorySchemaPacksInput,
    ListStorySchemaPacksOutput,
    MemoryAnswerInput,
    MemoryAnswerOutput,
    MemoryPageDetailInput,
    MemoryPageDetailOutput,
    MemoryPageThreadOperationInput,
    MemoryPageThreadOperationOutput,
    MemoryWritebackDecisionInput,
    MemoryWritebackDecisionOutput,
    MemoryWritebackPreviewInput,
    MemoryWritebackPreviewOutput,
    PersistActionRequestBeatCandidatesInput,
    PersistActionRequestRiskFindingsInput,
    PersistActionRequestRunInput,
    PersistFailedSkillRunInput,
    ProjectDetailOutput,
    ProjectInvitationSnapshot,
    ProjectMemberOperationOutput,
    ProjectMemberSnapshot,
    ProjectStorySchemaOutput,
    RecordProjectInvitationExternalProofInput,
    ReviewItemDetailInput,
    ReviewItemDetailOutput,
    ReviewItemOperationInput,
    ReviewItemOperationOutput,
    ReviewItemSnapshot,
    RevokeProjectMemberInput,
    RunActionRequestOutput,
    SelectProjectStorySchemaGenreInput,
    SourceDeltaDetailInput,
    SourceDeltaSnapshot,
    SourceSummaryOutput,
    SourceVersionSnapshot,
    StorySchemaPackOutput,
    SubmitActionRequestInput,
    SubmitActionRequestOutput,
    UpsertProjectMemberInput,
    UpsertProjectStorySchemaOverrideInput,
    WritingContextPackOutput,
)


class SextantUnitOfWork(Protocol):
    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None: ...

    def project_accessible(self, project_id: UUID, actor_id: UUID) -> bool: ...

    def project_readable(self, project_id: UUID, actor_id: UUID) -> bool: ...

    def get_project(self, input_data: GetProjectInput) -> ProjectDetailOutput | None: ...

    def project_actor_role(self, project_id: UUID, actor_id: UUID) -> str | None: ...

    def list_project_members(
        self, input_data: ListProjectMembersInput
    ) -> ListProjectMembersOutput: ...

    def list_project_invitations(
        self, input_data: ListProjectInvitationsInput
    ) -> ListProjectInvitationsOutput: ...

    def active_project_owner_count(self, project_id: UUID) -> int: ...

    def upsert_project_member(
        self, input_data: UpsertProjectMemberInput
    ) -> ProjectMemberOperationOutput: ...

    def revoke_project_member(
        self, input_data: RevokeProjectMemberInput
    ) -> ProjectMemberSnapshot | None: ...

    def create_project_invitation(
        self, input_data: CreateProjectInvitationInput
    ) -> ProjectInvitationSnapshot: ...

    def get_project_invitation(
        self, project_id: UUID, invitation_id: UUID
    ) -> ProjectInvitationSnapshot | None: ...

    def record_project_invitation_external_proof(
        self, input_data: RecordProjectInvitationExternalProofInput
    ) -> ProjectInvitationSnapshot | None: ...

    def load_idempotency_record(
        self, project_id: UUID, actor_id: UUID, operation: str, idempotency_key: str
    ) -> IdempotencySnapshot | None: ...

    def store_idempotency_record(
        self,
        *,
        project_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response_payload: dict[str, object],
    ) -> None: ...

    def create_action_request(
        self, input_data: SubmitActionRequestInput
    ) -> SubmitActionRequestOutput: ...

    def load_action_request(self, action_request_id: UUID) -> ActionRequestSnapshot | None: ...

    def update_action_request_status(self, action_request_id: UUID, status: str) -> str | None: ...

    def persist_action_request_run(
        self, input_data: PersistActionRequestRunInput
    ) -> RunActionRequestOutput: ...

    def persist_failed_skill_run(self, input_data: PersistFailedSkillRunInput) -> None: ...

    def persist_action_request_beat_candidates(
        self, input_data: PersistActionRequestBeatCandidatesInput
    ) -> RunActionRequestOutput: ...

    def persist_action_request_risk_findings(
        self, input_data: PersistActionRequestRiskFindingsInput
    ) -> RunActionRequestOutput: ...

    def load_candidate(self, candidate_id: UUID) -> CandidateSnapshot | None: ...

    def load_candidate_detail(self, candidate_id: UUID) -> CandidateDetailSnapshot | None: ...

    def persist_candidate_operation(
        self, input_data: CandidateOperationInput
    ) -> CandidateOperationOutput: ...

    def load_source_version(
        self, input_data: GetSourceVersionInput
    ) -> SourceVersionSnapshot | None: ...

    def list_source_versions(
        self, input_data: ListSourceVersionsInput
    ) -> ListSourceVersionsOutput | None: ...

    def list_sources(self, input_data: ListSourcesInput) -> ListSourcesOutput: ...

    def get_source(self, input_data: GetSourceInput) -> SourceSummaryOutput | None: ...

    def archive_source(self, input_data: ArchiveSourceInput) -> ArchiveSourceOutput | None: ...

    def create_source(
        self, input_data: CreateSourceInput, raw_text_ref: str, raw_hash: str
    ) -> CreateSourceOutput: ...

    def create_source_version(
        self, input_data: CreateSourceVersionInput, raw_text_ref: str, raw_hash: str
    ) -> CreateSourceVersionOutput: ...

    def create_source_delta(
        self,
        input_data: CreateSourceDeltaInput,
        submitted_text_ref: str,
        materialized_text_ref: str,
        materialized_hash: str,
        materialized_version_label: str,
    ) -> CreateSourceDeltaOutput: ...

    def source_version_hash(self, version_id: UUID) -> str | None: ...

    def source_in_project(self, project_id: UUID, source_id: UUID) -> bool: ...

    def persist_candidate_acceptance(
        self,
        input_data: AcceptCandidateInput,
        materialized_text_ref: str,
        materialized_hash: str,
        materialized_version_label: str,
    ) -> AcceptCandidateOutput: ...

    def load_review_item(self, review_item_id: UUID) -> ReviewItemSnapshot | None: ...

    def alias_correction_target_exists(
        self,
        project_id: UUID,
        alias_record_id: UUID,
        target_entity_id: UUID,
        boundary_scene_refs: dict[str, UUID | None] | None = None,
    ) -> bool: ...

    def source_deltas_exist(self, project_id: UUID, source_delta_ids: list[UUID]) -> bool: ...

    def source_deltas_have_source_scopes(
        self,
        project_id: UUID,
        source_delta_ids: list[UUID],
        allowed_source_scopes: set[str],
    ) -> bool: ...

    def review_replacement_refs_exist(
        self, project_id: UUID, refs_by_type: dict[str, list[UUID]]
    ) -> bool: ...

    def get_job_detail(self, input_data: JobDetailInput) -> JobDetailOutput | None: ...

    def operate_job(self, input_data: JobOperationInput) -> JobDetailOutput | None: ...

    def list_source_deltas(
        self, input_data: ListSourceDeltasInput
    ) -> list[SourceDeltaSnapshot]: ...

    def get_source_delta_detail(
        self, input_data: SourceDeltaDetailInput
    ) -> SourceDeltaSnapshot | None: ...

    def list_review_items(self, input_data: ListReviewItemsInput) -> ListReviewItemsOutput: ...

    def get_review_item_detail(
        self, input_data: ReviewItemDetailInput
    ) -> ReviewItemDetailOutput | None: ...

    def list_canonical_entities(
        self, input_data: ListCanonicalEntitiesInput
    ) -> ListCanonicalEntitiesOutput: ...

    def list_story_scenes(self, input_data: ListStoryScenesInput) -> ListStoryScenesOutput: ...

    def get_project_story_schema(
        self, input_data: GetProjectStorySchemaInput
    ) -> ProjectStorySchemaOutput: ...

    def list_story_schema_packs(
        self, input_data: ListStorySchemaPacksInput
    ) -> ListStorySchemaPacksOutput: ...

    def create_story_schema_genre_pack(
        self, input_data: CreateStorySchemaGenrePackInput
    ) -> StorySchemaPackOutput | None: ...

    def deprecate_story_schema_genre_pack(
        self, input_data: DeprecateStorySchemaGenrePackInput
    ) -> StorySchemaPackOutput | None: ...

    def select_project_story_schema_genre(
        self, input_data: SelectProjectStorySchemaGenreInput
    ) -> ProjectStorySchemaOutput | None: ...

    def upsert_project_story_schema_override(
        self, input_data: UpsertProjectStorySchemaOverrideInput
    ) -> ProjectStorySchemaOutput: ...

    def list_memory_pages(self, input_data: ListMemoryPagesInput) -> ListMemoryPagesOutput: ...

    def get_memory_page_detail(
        self, input_data: MemoryPageDetailInput
    ) -> MemoryPageDetailOutput | None: ...

    def persist_memory_page_thread_operation(
        self, input_data: MemoryPageThreadOperationInput
    ) -> MemoryPageThreadOperationOutput: ...

    def list_graph_projection_edges(
        self, input_data: ListGraphProjectionEdgesInput
    ) -> ListGraphProjectionEdgesOutput: ...

    def memory_writeback_preview(
        self, input_data: MemoryWritebackPreviewInput
    ) -> MemoryWritebackPreviewOutput | None: ...

    def persist_memory_writeback_decision(
        self, input_data: MemoryWritebackDecisionInput
    ) -> MemoryWritebackDecisionOutput: ...

    def persist_review_item_operation(
        self, input_data: ReviewItemOperationInput
    ) -> ReviewItemOperationOutput: ...

    def answer_memory(self, input_data: MemoryAnswerInput) -> MemoryAnswerOutput: ...

    def build_writing_context_pack(
        self, input_data: BuildWritingContextPackInput
    ) -> WritingContextPackOutput: ...

    def consume_context_pack_readiness(
        self,
        *,
        project_id: UUID,
        context_pack_id: UUID,
        evidence_refs: list[dict[str, object]],
    ) -> list[dict[str, object]]: ...

    def get_writing_context_pack(
        self, input_data: ContextPackDetailInput
    ) -> WritingContextPackOutput | None: ...

    def list_writing_context_packs(
        self, input_data: ListContextPacksInput
    ) -> ListContextPacksOutput: ...

    def list_context_pack_readiness(
        self, input_data: ListContextPackReadinessInput
    ) -> ListContextPackReadinessOutput: ...

    def record_audit(
        self,
        *,
        project_id: UUID,
        request_id: str,
        actor_id: UUID,
        event_type: str,
        subject_ref: dict[str, object],
        decision: dict[str, object],
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
