from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ErrorEnvelope(BaseModel):
    error: dict[str, Any]


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    actor_role: str
    created_at: datetime


class ProjectMemberResponse(BaseModel):
    id: UUID
    project_id: UUID
    actor_id: UUID
    role: str
    status: str
    created_at: datetime


class ProjectMemberListResponse(BaseModel):
    items: list[ProjectMemberResponse]


class ProjectMemberUpsertBody(BaseModel):
    role: str


class ProjectMemberOperationResponse(BaseModel):
    member: ProjectMemberResponse
    status: str


class ProjectInvitationCreateBody(BaseModel):
    member_actor_id: UUID
    role: str
    delivery_provider_ref: str
    delivery_target_ref: str
    token_issuer_ref: str | None = None


class ProjectInvitationExternalProofBody(BaseModel):
    delivery_proof_ref: str
    token_proof_ref: str | None = None


class ProjectInvitationResponse(BaseModel):
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


class ProjectInvitationListResponse(BaseModel):
    items: list[ProjectInvitationResponse]


class ActionRequestCreateBody(BaseModel):
    actor_id: UUID | None = None
    trigger: str
    action_type: str
    target: dict[str, Any] | None
    constraints: dict[str, Any] = Field(default_factory=dict)
    expected_output: str
    actor_intent: str
    source_id: UUID | None = None
    source_version_id: UUID | None = None
    scene_id: UUID | None = None
    chapter_id: UUID | None = None
    pov_character_id: UUID | None = None


class ActionRequestResponse(BaseModel):
    action_request_id: UUID
    status: str


class ActionRequestDetailResponse(BaseModel):
    action_request_id: UUID
    project_id: UUID
    source_id: UUID | None
    source_version_id: UUID | None
    scene_id: UUID | None
    chapter_id: UUID | None
    pov_character_id: UUID | None
    actor_intent: str
    trigger: str
    action_type: str
    target: dict[str, Any] | None
    constraints: dict[str, Any]
    expected_output: str
    status: str
    created_by: UUID | None


class CreateSourceBody(BaseModel):
    title: str
    source_type: str
    source_scope: str
    ownership_status: str
    text: str
    version_label: str = "v1"


class CreateSourceResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    source_delta_id: UUID
    memory_writeback_job_id: UUID
    raw_hash: str


class SourceSummaryResponse(BaseModel):
    source_id: UUID
    title: str
    source_type: str
    source_scope: str
    ownership_status: str
    is_archived: bool
    archived_at: str | None
    archived_by: UUID | None
    latest_version_id: UUID | None
    latest_version_label: str | None
    latest_raw_hash: str | None
    version_count: int


class SourceListResponse(BaseModel):
    items: list[SourceSummaryResponse]


class ArchiveSourceBody(BaseModel):
    author_note: str | None = None


class ArchiveSourceResponse(BaseModel):
    source_id: UUID
    status: str
    archived_at: str
    archived_by: UUID


class CreateSourceVersionBody(BaseModel):
    text: str
    version_label: str
    supersedes_version_id: UUID | None = None


class CreateSourceVersionResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    raw_hash: str
    supersedes_version_id: UUID | None


class RestoreSourceVersionBody(BaseModel):
    author_note: str | None = None


class RestoreSourceVersionResponse(BaseModel):
    source_id: UUID
    restored_from_version_id: UUID
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


class CreateSourceDeltaBody(BaseModel):
    delta_kind: str
    range_start: int
    range_end: int
    base_hash: str | None = None
    submitted_text: str
    source_type: str
    source_scope: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class ProjectSourceDeltaBody(CreateSourceDeltaBody):
    source_id: UUID
    previous_version_id: UUID


class CreateSourceDeltaResponse(BaseModel):
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


class ActionRequestRunBody(BaseModel):
    current_text_window: str = ""


class AgentActionRunBody(BaseModel):
    actor_id: UUID | None = None
    trigger: str = "toolbar"
    target: dict[str, Any] | None
    constraints: dict[str, Any] = Field(default_factory=dict)
    actor_intent: str
    source_id: UUID | None = None
    source_version_id: UUID | None = None
    scene_id: UUID | None = None
    chapter_id: UUID | None = None
    pov_character_id: UUID | None = None
    current_text_window: str = ""


class ActionRequestRunResponse(BaseModel):
    action_request_id: UUID
    status: str
    output_type: str
    context_pack_id: UUID | None
    draft_candidate_ids: list[UUID]
    risk_finding_ids: list[UUID]
    beat_candidate_ids: list[UUID]
    memory_answer: MemoryAnswerResponse | None = None
    risk_findings: list[AgentReviewFindingResponse] | None = None
    beat_candidates: list[BeatCandidateResponse] | None = None
    candidate_explanation: CandidateExplanationResponse | None = None


class AgentReviewFindingResponse(BaseModel):
    id: UUID
    risk_level: str
    risk_type: str
    summary: str
    memory_refs: dict[str, Any]
    storytelling_refs: dict[str, Any]
    suggested_revision: str | None
    can_offer_to_author: bool
    maps_to_review_type_if_accepted: str | None
    draft_local_only: bool


class BeatCandidateResponse(BaseModel):
    id: UUID
    summary: str
    driver_character: str
    agency_rationale: str
    storytelling_rationale: str
    cast_decision: dict[str, Any]
    tension: str
    memory_refs: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    agent_review_findings: list[AgentReviewFindingResponse]


class CandidateExplanationResponse(BaseModel):
    candidate_id: UUID
    why_this: str
    used_memory_refs: list[dict[str, Any]]
    respected_constraints: list[str]
    avoided_claims: list[str]
    risks: list[AgentReviewFindingResponse]


class CandidateOperationResponse(BaseModel):
    candidate_id: UUID
    status: str
    replacement_candidate_id: UUID | None = None
    override_reason: str | None = None


class CandidateRejectBody(BaseModel):
    actor_id: UUID | None = None
    author_note: str | None = None


class CandidateOverrideBody(BaseModel):
    actor_id: UUID | None = None
    override_reason: str


class CandidateReviseBody(BaseModel):
    actor_id: UUID | None = None
    revised_text_ref: str | None = None
    revised_text: str | None = None
    author_note: str | None = None


class CandidateDetailResponse(BaseModel):
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
    memory_refs: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    override_reason: str | None = None
    agent_review_findings: list[AgentReviewFindingResponse]


class SourceVersionResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    title: str
    source_type: str
    source_scope: str
    version_label: str
    raw_hash: str
    text: str


class SourceVersionDiffLineResponse(BaseModel):
    kind: str
    old_line: int | None
    new_line: int | None
    text: str


class SourceVersionDiffHunkResponse(BaseModel):
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[SourceVersionDiffLineResponse]


class SourceVersionDiffSummaryResponse(BaseModel):
    insertions: int
    deletions: int
    changed: bool


class SourceVersionDiffResponse(BaseModel):
    source_id: UUID
    base_version_id: UUID
    compare_version_id: UUID
    base_version_label: str
    compare_version_label: str
    base_raw_hash: str
    compare_raw_hash: str
    summary: SourceVersionDiffSummaryResponse
    hunks: list[SourceVersionDiffHunkResponse]


class SourceVersionSummaryResponse(BaseModel):
    source_id: UUID
    version_id: UUID
    version_label: str
    raw_hash: str
    raw_text_ref: str
    supersedes_version_id: UUID | None
    created_at: str


class SourceVersionListResponse(BaseModel):
    items: list[SourceVersionSummaryResponse]


class CandidateAcceptBody(BaseModel):
    actor_id: UUID | None = None
    accepted_text_ref: str | None = None
    accepted_text: str | None = None
    accept_mode: str
    target_source_id: UUID
    target_version_id: UUID
    insert_or_replace_range: dict[str, int]
    base_hash: str | None = None
    source_type: str
    source_scope: str
    author_edited: bool


class CandidateAcceptResponse(BaseModel):
    accepted_fragment_id: UUID
    source_delta_id: UUID
    new_version_id: UUID
    memory_writeback_job_id: UUID


class ReviewItemResolveBody(BaseModel):
    actor_id: UUID | None = None
    resolution: str
    author_note: str | None = None
    replacement_refs: list[dict[str, Any]] = Field(default_factory=list)
    correction: dict[str, Any] = Field(default_factory=dict)


class ReviewItemNoteBody(BaseModel):
    actor_id: UUID | None = None
    author_note: str | None = None


class ReviewItemOperationResponse(BaseModel):
    review_item_id: UUID
    status: str
    resolution: str | None
    side_effects: dict[str, Any]


class JobDetailResponse(BaseModel):
    id: UUID
    job_type: str
    status: str
    attempt_count: int
    run_after: str | None
    locked_by: str | None
    locked_at: str | None
    last_error: str | None
    payload: dict[str, Any]


class JobOperationBody(BaseModel):
    actor_id: UUID | None = None
    author_note: str | None = None


class ReviewItemDetailResponse(BaseModel):
    id: UUID
    review_type: str
    severity: str
    status: str
    summary: str
    affected_refs: dict[str, Any]
    new_evidence: dict[str, Any]
    existing_evidence: dict[str, Any]
    suggested_actions: list[dict[str, Any]]
    default_action: str
    resolution: str | None
    side_effects: dict[str, Any]


class ReviewItemListResponse(BaseModel):
    items: list[ReviewItemDetailResponse]


class CanonicalEntitySummaryResponse(BaseModel):
    id: UUID
    entity_type: str
    display_name: str
    canonical_status: str
    cast_tier: str | None
    first_seen_scene_id: UUID | None


class CanonicalEntityListResponse(BaseModel):
    items: list[CanonicalEntitySummaryResponse]


class StorySceneSummaryResponse(BaseModel):
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


class StorySceneListResponse(BaseModel):
    items: list[StorySceneSummaryResponse]


class StorySchemaPackResponse(BaseModel):
    id: UUID
    project_id: UUID | None
    pack_type: str
    pack_name: str
    version: str
    status: str
    entity_types: list[dict[str, Any]]
    event_types: list[dict[str, Any] | str]
    relations: list[dict[str, Any] | str]
    extraction_hints: dict[str, Any]
    risk_rules: dict[str, Any]


class StorySchemaPackListResponse(BaseModel):
    items: list[StorySchemaPackResponse]


class StorySchemaGenrePackBody(BaseModel):
    pack_name: str
    version: str
    entity_types: list[dict[str, Any]] = Field(default_factory=list)
    event_types: list[dict[str, Any] | str] = Field(default_factory=list)
    relations: list[dict[str, Any] | str] = Field(default_factory=list)
    extraction_hints: dict[str, Any] = Field(default_factory=dict)
    risk_rules: dict[str, Any] = Field(default_factory=dict)


class ProjectStorySchemaResponse(BaseModel):
    project_id: UUID
    binding_id: UUID | None
    base_schema_pack_id: UUID | None
    genre_schema_pack_id: UUID | None
    genre_schema_pack: StorySchemaPackResponse | None
    project_override_pack_id: UUID | None
    project_override_pack: StorySchemaPackResponse | None
    effective_schema: dict[str, Any]


class ProjectStorySchemaGenreBody(BaseModel):
    genre_schema_pack_id: UUID | None = None


class ProjectStorySchemaOverrideBody(BaseModel):
    pack_name: str = "project-overrides"
    entity_types: list[dict[str, Any]] = Field(default_factory=list)
    event_types: list[dict[str, Any] | str] = Field(default_factory=list)
    relations: list[dict[str, Any] | str] = Field(default_factory=list)
    extraction_hints: dict[str, Any] = Field(default_factory=dict)
    risk_rules: dict[str, Any] = Field(default_factory=dict)


class MemoryPageSummaryResponse(BaseModel):
    id: UUID
    page_type: str
    target_ref: dict[str, Any]
    title: str
    canon_status: str
    memory_depth: str
    source_refs: list[dict[str, Any]]
    open_thread_count: int
    contradiction_count: int


class MemoryPageListResponse(BaseModel):
    items: list[MemoryPageSummaryResponse]


class MemoryPageDetailResponse(BaseModel):
    id: UUID
    page_type: str
    target_ref: dict[str, Any]
    title: str
    current_canon: dict[str, Any]
    appearance_log: list[dict[str, Any]]
    event_log: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    knowledge_state: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    source_refs: list[dict[str, Any]]
    canon_status: str
    memory_depth: str


class MemoryPageThreadOperationBody(BaseModel):
    update_type: str
    author_note: str
    summary: str | None = None


class MemoryPageThreadOperationResponse(BaseModel):
    memory_page_id: UUID
    thread_id: str
    status: str
    update_type: str
    memory_page: MemoryPageDetailResponse
    side_effects: dict[str, Any]


class GraphProjectionEdgeResponse(BaseModel):
    id: UUID
    run_id: UUID
    source_ref: dict[str, Any]
    subject_ref: dict[str, Any]
    relation: str
    target_ref: dict[str, Any]
    edge_status: str
    evidence_refs: list[dict[str, Any]]
    created_at: datetime


class GraphProjectionEdgeListResponse(BaseModel):
    items: list[GraphProjectionEdgeResponse]


class SourceDeltaSummaryResponse(BaseModel):
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
    provenance: dict[str, Any]
    submitted_text_ref: str
    submitted_text_preview: str
    job: JobDetailResponse | None


class SourceDeltaDetailResponse(BaseModel):
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
    provenance: dict[str, Any]
    submitted_text_ref: str
    submitted_text: str
    job: JobDetailResponse | None


class SourceDeltaListResponse(BaseModel):
    items: list[SourceDeltaSummaryResponse]
    next_cursor: str | None = None


class MemoryWritebackPreviewResponse(BaseModel):
    source_delta_id: UUID
    source_delta_status: str
    source_delta: dict[str, Any]
    job: JobDetailResponse | None
    source_spans: list[dict[str, Any]]
    evidence_log_entries: list[dict[str, Any]]
    fact_assertions: list[dict[str, Any]]
    review_items: list[ReviewItemDetailResponse]
    memory_pages: list[dict[str, Any]]
    graph_edges: list[dict[str, Any]]


class MemoryWritebackDecisionBody(BaseModel):
    actor_id: UUID | None = None
    item_ref: dict[str, Any]
    decision: str
    author_note: str | None = None
    correction: dict[str, Any] = Field(default_factory=dict)
    replacement_refs: list[dict[str, Any]] = Field(default_factory=list)


class MemoryWritebackDecisionResponse(BaseModel):
    decision_id: UUID
    source_delta_id: UUID
    item_ref: dict[str, Any]
    decision: str
    status: str
    side_effects: dict[str, Any]


class MemoryAnswerBody(BaseModel):
    question: str
    subject_ref: dict[str, Any] | None = None
    predicate: str | None = None
    current_scene_id: UUID | None = None
    current_pov_character_id: UUID | None = None


class MemoryAnswerResponse(BaseModel):
    question: str
    answer: str
    answer_type: str
    confidence: float
    source_span_refs: list[dict[str, Any]]
    affected_entities: list[dict[str, Any]]
    caveats: list[str]
    unknowns: list[str]
    related_review_items: list[UUID]
    safe_to_use_in_current_pov: bool


class BuildWritingContextPackBody(BaseModel):
    action_request_id: UUID | None = None
    current_source_id: UUID | None = None
    current_version_id: UUID | None = None
    current_scene_id: UUID | None = None
    current_pov_character_id: UUID | None = None
    mode: str
    current_text_window: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)


class WritingContextPackResponse(BaseModel):
    context_pack_id: UUID
    schema_version: str
    current_position: dict[str, Any]
    canonical_context: dict[str, Any]
    pov_constraint: dict[str, Any]
    active_characters: list[dict[str, Any]]
    character_agency_state: dict[str, Any]
    recent_events: list[dict[str, Any]]
    character_knowledge: list[dict[str, Any]]
    object_location_state: list[dict[str, Any]]
    open_threads: list[dict[str, Any]]
    risk_context: dict[str, Any]
    style_memory: dict[str, Any]
    evidence_refs: list[dict[str, Any]]


class WritingContextPackSummaryResponse(BaseModel):
    context_pack_id: UUID
    schema_version: str
    mode: str
    current_position: dict[str, Any]
    evidence_refs: list[dict[str, Any]]


class WritingContextPackListResponse(BaseModel):
    items: list[WritingContextPackSummaryResponse]


class ContextPackReadinessResponse(BaseModel):
    id: UUID
    source_span_id: UUID
    source_delta_id: UUID | None
    status: str
    reason: str
    affected_refs: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]


class ContextPackReadinessListResponse(BaseModel):
    items: list[ContextPackReadinessResponse]
