from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IdempotencySnapshot:
    operation: str
    idempotency_key: str
    request_hash: str
    response_payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class GetProjectInput:
    project_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProjectDetailOutput:
    id: UUID
    name: str
    actor_role: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectMemberSnapshot:
    id: UUID
    project_id: UUID
    actor_id: UUID
    role: str
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ListProjectMembersInput:
    project_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ListProjectMembersOutput:
    items: list[ProjectMemberSnapshot]


@dataclass(frozen=True, slots=True)
class ListProjectInvitationsInput:
    project_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ListProjectInvitationsOutput:
    items: list[ProjectInvitationSnapshot]


@dataclass(frozen=True, slots=True)
class UpsertProjectMemberInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    member_actor_id: UUID
    role: str


@dataclass(frozen=True, slots=True)
class RevokeProjectMemberInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    member_actor_id: UUID


@dataclass(frozen=True, slots=True)
class ProjectMemberOperationOutput:
    member: ProjectMemberSnapshot
    status: str


@dataclass(frozen=True, slots=True)
class ProjectInvitationSnapshot:
    id: UUID
    project_id: UUID
    member_actor_id: UUID
    role: str
    delivery_provider_ref: str
    delivery_target_ref: str
    token_issuer_ref: str | None
    delivery_proof_ref: str | None
    token_proof_ref: str | None
    status: str
    delivery_status: str
    token_status: str
    delivered_at: datetime | None
    token_issued_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CreateProjectInvitationInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    member_actor_id: UUID
    role: str
    delivery_provider_ref: str
    delivery_target_ref: str
    token_issuer_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RecordProjectInvitationExternalProofInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    invitation_id: UUID
    delivery_proof_ref: str
    token_proof_ref: str | None = None


@dataclass(frozen=True, slots=True)
class SubmitActionRequestInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    trigger: str
    action_type: str
    target: dict[str, object] | None
    constraints: dict[str, object]
    expected_output: str
    actor_intent: str
    source_id: UUID | None = None
    source_version_id: UUID | None = None
    scene_id: UUID | None = None
    chapter_id: UUID | None = None
    pov_character_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SubmitActionRequestOutput:
    action_request_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class GetActionRequestInput:
    project_id: UUID
    actor_id: UUID
    action_request_id: UUID


@dataclass(frozen=True, slots=True)
class ActionRequestSnapshot:
    id: UUID
    project_id: UUID
    source_id: UUID | None
    source_version_id: UUID | None
    scene_id: UUID | None
    chapter_id: UUID | None
    pov_character_id: UUID | None
    actor_intent: str
    trigger: str
    action_type: str
    target: dict[str, object] | None
    constraints: dict[str, object]
    expected_output: str
    status: str
    created_by: UUID | None


@dataclass(frozen=True, slots=True)
class AgentReviewFindingDraft:
    risk_level: str
    risk_type: str
    summary: str
    affected_text_ref: str | None
    memory_refs: dict[str, object]
    storytelling_refs: dict[str, object]
    suggested_revision: str | None
    can_offer_to_author: bool
    maps_to_review_type_if_accepted: str | None


@dataclass(frozen=True, slots=True)
class StorytellingControlDraft:
    control_type: str
    schema_version: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class BeatCandidateDraft:
    summary: str
    driver_character: str
    agency_rationale: str
    storytelling_rationale: str
    cast_decision: dict[str, object]
    tension: str
    memory_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class BeatCandidateSnapshot:
    id: UUID
    summary: str
    driver_character: str
    agency_rationale: str
    storytelling_rationale: str
    cast_decision: dict[str, object]
    tension: str
    memory_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]
    agent_review_findings: list[AgentReviewFindingSnapshot]


@dataclass(frozen=True, slots=True)
class CandidateExplanationOutput:
    candidate_id: UUID
    why_this: str
    used_memory_refs: list[dict[str, object]]
    respected_constraints: list[str]
    avoided_claims: list[str]
    risks: list[AgentReviewFindingSnapshot]


@dataclass(frozen=True, slots=True)
class PersistActionRequestRunInput:
    project_id: UUID
    actor_id: UUID
    action_request_id: UUID
    original_candidate_id: UUID | None
    mode: str
    context_pack_id: UUID
    candidate_text_ref: str
    target_source_id: UUID | None
    target_version_id: UUID | None
    target_scene_id: UUID | None
    affected_range: dict[str, int] | None
    base_hash: str | None
    memory_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]
    controls: list[StorytellingControlDraft]
    skill_name: str
    skill_version: str
    prompt_version: str
    input_hash: str
    structured_output: dict[str, object]
    findings: list[AgentReviewFindingDraft]
    candidate_status: str


@dataclass(frozen=True, slots=True)
class PersistFailedSkillRunInput:
    project_id: UUID
    skill_name: str
    skill_version: str
    input_schema_version: str
    output_schema_version: str
    prompt_version: str
    input_hash: str
    structured_output: dict[str, object]
    validation_result: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistActionRequestBeatCandidatesInput:
    project_id: UUID
    actor_id: UUID
    action_request_id: UUID
    context_pack_id: UUID
    target_source_id: UUID | None
    target_version_id: UUID | None
    target_scene_id: UUID | None
    affected_range: dict[str, int] | None
    base_hash: str | None
    controls: list[StorytellingControlDraft]
    beat_candidates: list[BeatCandidateDraft]


@dataclass(frozen=True, slots=True)
class PersistActionRequestRiskFindingsInput:
    project_id: UUID
    actor_id: UUID
    action_request_id: UUID
    findings: list[AgentReviewFindingDraft]


@dataclass(frozen=True, slots=True)
class RunActionRequestInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    action_request_id: UUID
    current_text_window: str


@dataclass(frozen=True, slots=True)
class RunActionRequestOutput:
    action_request_id: UUID
    status: str
    output_type: str
    context_pack_id: UUID | None
    draft_candidate_ids: list[UUID]
    risk_finding_ids: list[UUID]
    beat_candidate_ids: list[UUID]
    memory_answer: MemoryAnswerOutput | None = None
    risk_findings: list[AgentReviewFindingSnapshot] | None = None
    beat_candidates: list[BeatCandidateSnapshot] | None = None
    candidate_explanation: CandidateExplanationOutput | None = None


@dataclass(frozen=True, slots=True)
class AgentReviewFindingSnapshot:
    id: UUID
    risk_level: str
    risk_type: str
    summary: str
    memory_refs: dict[str, object]
    storytelling_refs: dict[str, object]
    suggested_revision: str | None
    can_offer_to_author: bool
    maps_to_review_type_if_accepted: str | None
    draft_local_only: bool


@dataclass(frozen=True, slots=True)
class CandidateDetailSnapshot:
    id: UUID
    project_id: UUID
    action_request_id: UUID
    mode: str
    candidate_text_ref: str
    context_pack_id: UUID | None
    target_source_id: UUID | None
    target_version_id: UUID | None
    target_scene_id: UUID | None
    affected_range: dict[str, int] | None
    base_hash: str | None
    memory_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]
    status: str
    override_reason: str | None
    agent_review_findings: list[AgentReviewFindingSnapshot]


@dataclass(frozen=True, slots=True)
class GetCandidateInput:
    project_id: UUID
    actor_id: UUID
    candidate_id: UUID


@dataclass(frozen=True, slots=True)
class CandidateDetailOutput:
    id: UUID
    action_request_id: UUID
    mode: str
    text: str
    status: str
    context_pack_id: UUID | None
    target_source_id: UUID | None
    target_version_id: UUID | None
    target_scene_id: UUID | None
    affected_range: dict[str, int] | None
    base_hash: str | None
    memory_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]
    override_reason: str | None
    agent_review_findings: list[AgentReviewFindingSnapshot]


@dataclass(frozen=True, slots=True)
class CandidateOperationInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    candidate_id: UUID
    operation: str
    author_note: str | None = None
    override_reason: str | None = None
    revised_text_ref: str | None = None
    revised_text: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateOperationOutput:
    candidate_id: UUID
    status: str
    replacement_candidate_id: UUID | None = None
    override_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SourceVersionSnapshot:
    project_id: UUID
    source_id: UUID
    version_id: UUID
    title: str
    source_type: str
    source_scope: str
    raw_text_ref: str
    version_label: str
    raw_hash: str


@dataclass(frozen=True, slots=True)
class GetSourceVersionInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID
    version_id: UUID


@dataclass(frozen=True, slots=True)
class SourceVersionDetailOutput:
    source_id: UUID
    version_id: UUID
    title: str
    source_type: str
    source_scope: str
    version_label: str
    raw_hash: str
    text: str


@dataclass(frozen=True, slots=True)
class SourceVersionDiffInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID
    base_version_id: UUID
    compare_version_id: UUID


@dataclass(frozen=True, slots=True)
class SourceVersionDiffLineOutput:
    kind: str
    old_line: int | None
    new_line: int | None
    text: str


@dataclass(frozen=True, slots=True)
class SourceVersionDiffHunkOutput:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[SourceVersionDiffLineOutput]


@dataclass(frozen=True, slots=True)
class SourceVersionDiffSummaryOutput:
    insertions: int
    deletions: int
    changed: bool


@dataclass(frozen=True, slots=True)
class SourceVersionDiffOutput:
    source_id: UUID
    base_version_id: UUID
    compare_version_id: UUID
    base_version_label: str
    compare_version_label: str
    base_raw_hash: str
    compare_raw_hash: str
    summary: SourceVersionDiffSummaryOutput
    hunks: list[SourceVersionDiffHunkOutput]


@dataclass(frozen=True, slots=True)
class ListSourceVersionsInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID
    limit: int = 20


@dataclass(frozen=True, slots=True)
class SourceVersionSummaryOutput:
    source_id: UUID
    version_id: UUID
    version_label: str
    raw_hash: str
    raw_text_ref: str
    supersedes_version_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ListSourceVersionsOutput:
    items: list[SourceVersionSummaryOutput]


@dataclass(frozen=True, slots=True)
class SourceSummaryOutput:
    source_id: UUID
    title: str
    source_type: str
    source_scope: str
    ownership_status: str
    is_archived: bool
    archived_at: datetime | None
    archived_by: UUID | None
    latest_version_id: UUID | None
    latest_version_label: str | None
    latest_raw_hash: str | None
    version_count: int


@dataclass(frozen=True, slots=True)
class ListSourcesInput:
    project_id: UUID
    actor_id: UUID
    query: str = ""
    limit: int = 20
    include_archived: bool = False


@dataclass(frozen=True, slots=True)
class GetSourceInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID


@dataclass(frozen=True, slots=True)
class ListSourcesOutput:
    items: list[SourceSummaryOutput]


@dataclass(frozen=True, slots=True)
class ArchiveSourceInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    source_id: UUID
    author_note: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveSourceOutput:
    source_id: UUID
    status: str
    archived_at: datetime
    archived_by: UUID


@dataclass(frozen=True, slots=True)
class CreateSourceInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    title: str
    source_type: str
    source_scope: str
    ownership_status: str
    text: str
    version_label: str = "v1"


@dataclass(frozen=True, slots=True)
class CreateSourceOutput:
    source_id: UUID
    version_id: UUID
    source_delta_id: UUID
    memory_writeback_job_id: UUID
    raw_hash: str


@dataclass(frozen=True, slots=True)
class CreateSourceVersionInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    source_id: UUID
    text: str
    version_label: str
    supersedes_version_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CreateSourceVersionOutput:
    source_id: UUID
    version_id: UUID
    raw_hash: str
    supersedes_version_id: UUID | None


@dataclass(frozen=True, slots=True)
class RestoreSourceVersionInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    source_id: UUID
    version_id: UUID
    author_note: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreSourceVersionOutput:
    source_id: UUID
    restored_from_version_id: UUID
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


@dataclass(frozen=True, slots=True)
class CreateSourceDeltaInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    source_id: UUID
    previous_version_id: UUID
    delta_kind: str
    range_start: int
    range_end: int
    base_hash: str | None
    submitted_text: str
    source_type: str
    source_scope: str
    provenance: dict[str, object]


@dataclass(frozen=True, slots=True)
class CreateSourceDeltaOutput:
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


@dataclass(frozen=True, slots=True)
class AcceptCandidateInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    candidate_id: UUID
    accepted_text_ref: str | None
    accept_mode: str
    target_source_id: UUID
    target_version_id: UUID
    insert_or_replace_range: dict[str, int]
    source_type: str
    source_scope: str
    author_edited: bool
    accepted_text: str | None = None
    base_hash: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptCandidateOutput:
    accepted_fragment_id: UUID
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    id: UUID
    project_id: UUID
    status: str
    target_source_id: UUID | None
    target_version_id: UUID | None
    affected_range: dict[str, int] | None
    base_hash: str | None
    override_reason: str | None


@dataclass(frozen=True, slots=True)
class ReviewItemSnapshot:
    id: UUID
    project_id: UUID
    review_type: str
    affected_refs: dict[str, object]
    new_evidence: dict[str, object]
    status: str
    resolution: str | None
    side_effects: dict[str, object]


@dataclass(frozen=True, slots=True)
class JobDetailInput:
    project_id: UUID
    actor_id: UUID
    job_id: UUID


@dataclass(frozen=True, slots=True)
class JobDetailOutput:
    id: UUID
    job_type: str
    status: str
    attempt_count: int
    run_after: datetime | None
    locked_by: str | None
    locked_at: datetime | None
    last_error: str | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class JobOperationInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    job_id: UUID
    operation: str
    author_note: str | None = None


@dataclass(frozen=True, slots=True)
class ListSourceDeltasInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID | None = None
    source_version_id: UUID | None = None
    status: str | None = None
    delta_kind: str | None = None
    query: str | None = None
    cursor: str | None = None
    accepted_only: bool = False
    limit: int = 50
    after_created_at: datetime | None = None
    after_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SourceDeltaDetailInput:
    project_id: UUID
    actor_id: UUID
    source_delta_id: UUID


@dataclass(frozen=True, slots=True)
class SourceDeltaSummaryOutput:
    id: UUID
    source_id: UUID
    previous_version_id: UUID | None
    new_version_id: UUID | None
    accepted_fragment_id: UUID | None
    delta_kind: str
    status: str
    range_start: int
    range_end: int
    base_hash: str | None
    source_type: str
    source_scope: str
    provenance: dict[str, object]
    submitted_text_ref: str
    submitted_text_preview: str
    job: JobDetailOutput | None


@dataclass(frozen=True, slots=True)
class SourceDeltaDetailOutput:
    id: UUID
    source_id: UUID
    previous_version_id: UUID | None
    new_version_id: UUID | None
    accepted_fragment_id: UUID | None
    delta_kind: str
    status: str
    range_start: int
    range_end: int
    base_hash: str | None
    source_type: str
    source_scope: str
    provenance: dict[str, object]
    submitted_text_ref: str
    submitted_text: str
    job: JobDetailOutput | None


@dataclass(frozen=True, slots=True)
class ListSourceDeltasOutput:
    items: list[SourceDeltaSummaryOutput]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class SourceDeltaSnapshot:
    id: UUID
    project_id: UUID
    source_id: UUID
    previous_version_id: UUID | None
    new_version_id: UUID | None
    accepted_fragment_id: UUID | None
    delta_kind: str
    status: str
    range_start: int
    range_end: int
    base_hash: str | None
    source_type: str
    source_scope: str
    provenance: dict[str, object]
    submitted_text_ref: str
    created_at: datetime
    job: JobDetailOutput | None


@dataclass(frozen=True, slots=True)
class ReviewItemDetailOutput:
    id: UUID
    review_type: str
    severity: str
    status: str
    summary: str
    affected_refs: dict[str, object]
    new_evidence: dict[str, object]
    existing_evidence: dict[str, object]
    suggested_actions: list[dict[str, object]]
    default_action: str
    resolution: str | None
    side_effects: dict[str, object]


@dataclass(frozen=True, slots=True)
class ListReviewItemsInput:
    project_id: UUID
    actor_id: UUID
    status: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewItemDetailInput:
    project_id: UUID
    actor_id: UUID
    review_item_id: UUID


@dataclass(frozen=True, slots=True)
class ListReviewItemsOutput:
    items: list[ReviewItemDetailOutput]


@dataclass(frozen=True, slots=True)
class CanonicalEntitySummaryOutput:
    id: UUID
    entity_type: str
    display_name: str
    canonical_status: str
    cast_tier: str | None
    first_seen_scene_id: UUID | None


@dataclass(frozen=True, slots=True)
class ListCanonicalEntitiesInput:
    project_id: UUID
    actor_id: UUID
    query: str | None = None
    entity_type: str | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class ListCanonicalEntitiesOutput:
    items: list[CanonicalEntitySummaryOutput]


@dataclass(frozen=True, slots=True)
class StorySceneSummaryOutput:
    id: UUID
    source_id: UUID
    version_id: UUID
    chapter_id: UUID
    chapter_index: int
    chapter_title: str
    scene_index: int
    position_label: str
    story_time: str | None
    scene_summary: str | None
    pov_character_id: UUID | None
    pov_mode: str | None


@dataclass(frozen=True, slots=True)
class ListStoryScenesInput:
    project_id: UUID
    actor_id: UUID
    source_id: UUID | None = None
    version_id: UUID | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class ListStoryScenesOutput:
    items: list[StorySceneSummaryOutput]


@dataclass(frozen=True, slots=True)
class StorySchemaPackOutput:
    id: UUID
    project_id: UUID | None
    pack_type: str
    pack_name: str
    version: str
    status: str
    entity_types: list[dict[str, object]]
    event_types: list[dict[str, object] | str]
    relations: list[dict[str, object] | str]
    extraction_hints: dict[str, object]
    risk_rules: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProjectStorySchemaOutput:
    project_id: UUID
    binding_id: UUID | None
    base_schema_pack_id: UUID | None
    genre_schema_pack_id: UUID | None
    genre_schema_pack: StorySchemaPackOutput | None
    project_override_pack_id: UUID | None
    project_override_pack: StorySchemaPackOutput | None
    effective_schema: dict[str, object]


@dataclass(frozen=True, slots=True)
class GetProjectStorySchemaInput:
    project_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True)
class ListStorySchemaPacksInput:
    project_id: UUID
    actor_id: UUID
    pack_type: str | None = None


@dataclass(frozen=True, slots=True)
class ListStorySchemaPacksOutput:
    items: list[StorySchemaPackOutput]


@dataclass(frozen=True, slots=True)
class CreateStorySchemaGenrePackInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    pack_name: str
    version: str
    entity_types: list[dict[str, object]]
    event_types: list[dict[str, object] | str]
    relations: list[dict[str, object] | str]
    extraction_hints: dict[str, object]
    risk_rules: dict[str, object]


@dataclass(frozen=True, slots=True)
class DeprecateStorySchemaGenrePackInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    story_schema_pack_id: UUID


@dataclass(frozen=True, slots=True)
class SelectProjectStorySchemaGenreInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    genre_schema_pack_id: UUID | None


@dataclass(frozen=True, slots=True)
class UpsertProjectStorySchemaOverrideInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    pack_name: str
    entity_types: list[dict[str, object]]
    event_types: list[dict[str, object] | str]
    relations: list[dict[str, object] | str]
    extraction_hints: dict[str, object]
    risk_rules: dict[str, object]


@dataclass(frozen=True, slots=True)
class MemoryPageSummaryOutput:
    id: UUID
    page_type: str
    target_ref: dict[str, object]
    title: str
    canon_status: str
    memory_depth: str
    source_refs: list[dict[str, object]]
    open_thread_count: int
    contradiction_count: int


@dataclass(frozen=True, slots=True)
class MemoryPageDetailOutput:
    id: UUID
    page_type: str
    target_ref: dict[str, object]
    title: str
    current_canon: dict[str, object]
    appearance_log: list[dict[str, object]]
    event_log: list[dict[str, object]]
    relationships: list[dict[str, object]]
    knowledge_state: list[dict[str, object]]
    open_threads: list[dict[str, object]]
    contradictions: list[dict[str, object]]
    source_refs: list[dict[str, object]]
    canon_status: str
    memory_depth: str


@dataclass(frozen=True, slots=True)
class ListMemoryPagesInput:
    project_id: UUID
    actor_id: UUID
    page_type: str | None = None
    canon_status: str | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class MemoryPageDetailInput:
    project_id: UUID
    actor_id: UUID
    memory_page_id: UUID


@dataclass(frozen=True, slots=True)
class MemoryPageThreadOperationInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    memory_page_id: UUID
    thread_id: str
    update_type: str
    author_note: str
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryPageThreadOperationOutput:
    memory_page_id: UUID
    thread_id: str
    status: str
    update_type: str
    memory_page: MemoryPageDetailOutput
    side_effects: dict[str, object]


@dataclass(frozen=True, slots=True)
class ListMemoryPagesOutput:
    items: list[MemoryPageSummaryOutput]


@dataclass(frozen=True, slots=True)
class GraphProjectionEdgeSummaryOutput:
    id: UUID
    run_id: UUID
    source_ref: dict[str, object]
    subject_ref: dict[str, object]
    relation: str
    target_ref: dict[str, object]
    edge_status: str
    evidence_refs: list[dict[str, object]]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ListGraphProjectionEdgesInput:
    project_id: UUID
    actor_id: UUID
    query: str | None = None
    relation: str | None = None
    edge_status: str | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ListGraphProjectionEdgesOutput:
    items: list[GraphProjectionEdgeSummaryOutput]


@dataclass(frozen=True, slots=True)
class MemoryWritebackPreviewInput:
    project_id: UUID
    actor_id: UUID
    source_delta_id: UUID


@dataclass(frozen=True, slots=True)
class MemoryWritebackPreviewOutput:
    source_delta_id: UUID
    source_delta_status: str
    source_delta: dict[str, object]
    job: JobDetailOutput | None
    source_spans: list[dict[str, object]]
    evidence_log_entries: list[dict[str, object]]
    fact_assertions: list[dict[str, object]]
    review_items: list[ReviewItemDetailOutput]
    memory_pages: list[dict[str, object]]
    graph_edges: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ReviewItemOperationInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    review_item_id: UUID
    operation: str
    resolution: str | None = None
    author_note: str | None = None
    replacement_refs: list[dict[str, object]] | None = None
    correction: dict[str, object] | None = None
    side_effects: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ReviewItemOperationOutput:
    review_item_id: UUID
    status: str
    resolution: str | None
    side_effects: dict[str, object]


@dataclass(frozen=True, slots=True)
class MemoryWritebackDecisionInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    source_delta_id: UUID
    item_ref: dict[str, object]
    decision: str
    author_note: str | None = None
    correction: dict[str, object] | None = None
    replacement_refs: list[dict[str, object]] | None = None


@dataclass(frozen=True, slots=True)
class MemoryWritebackDecisionOutput:
    decision_id: UUID
    source_delta_id: UUID
    item_ref: dict[str, object]
    decision: str
    status: str
    side_effects: dict[str, object]


@dataclass(frozen=True, slots=True)
class MemoryAnswerInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    question: str
    subject_ref: dict[str, object] | None = None
    predicate: str | None = None
    current_scene_id: UUID | None = None
    current_pov_character_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class MemoryAnswerOutput:
    question: str
    answer: str
    answer_type: str
    confidence: float
    source_span_refs: list[dict[str, object]]
    affected_entities: list[dict[str, object]]
    caveats: list[str]
    unknowns: list[str]
    related_review_items: list[UUID]
    safe_to_use_in_current_pov: bool


@dataclass(frozen=True, slots=True)
class BuildWritingContextPackInput:
    project_id: UUID
    actor_id: UUID
    request_id: str
    idempotency_key: str
    action_request_id: UUID | None
    current_source_id: UUID | None
    current_version_id: UUID | None
    current_scene_id: UUID | None
    current_pov_character_id: UUID | None
    mode: str
    current_text_window: str
    constraints: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class WritingContextPackOutput:
    context_pack_id: UUID
    schema_version: str
    current_position: dict[str, object]
    canonical_context: dict[str, object]
    pov_constraint: dict[str, object]
    active_characters: list[dict[str, object]]
    character_agency_state: dict[str, object]
    recent_events: list[dict[str, object]]
    character_knowledge: list[dict[str, object]]
    object_location_state: list[dict[str, object]]
    open_threads: list[dict[str, object]]
    risk_context: dict[str, object]
    style_memory: dict[str, object]
    evidence_refs: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ContextPackDetailInput:
    project_id: UUID
    actor_id: UUID
    context_pack_id: UUID


@dataclass(frozen=True, slots=True)
class ListContextPacksInput:
    project_id: UUID
    actor_id: UUID
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ContextPackSummaryOutput:
    context_pack_id: UUID
    schema_version: str
    mode: str
    current_position: dict[str, object]
    evidence_refs: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ListContextPacksOutput:
    items: list[ContextPackSummaryOutput]


@dataclass(frozen=True, slots=True)
class ListContextPackReadinessInput:
    project_id: UUID
    actor_id: UUID
    status: str | None = None
    reason: str | None = None
    source_delta_id: UUID | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class ContextPackReadinessSummaryOutput:
    id: UUID
    source_span_id: UUID
    source_delta_id: UUID | None
    status: str
    reason: str
    affected_refs: list[dict[str, object]]
    evidence_refs: list[dict[str, object]]


@dataclass(frozen=True, slots=True)
class ListContextPackReadinessOutput:
    items: list[ContextPackReadinessSummaryOutput]
