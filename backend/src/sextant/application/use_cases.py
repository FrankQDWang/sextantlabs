from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import datetime
from difflib import SequenceMatcher
from hashlib import sha256
from typing import cast
from urllib.parse import ParseResult, urlparse
from uuid import UUID

from sextant.application.errors import ApplicationError
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    AcceptCandidateOutput,
    ActionRequestSnapshot,
    AgentReviewFindingDraft,
    AgentReviewFindingSnapshot,
    ArchiveSourceInput,
    ArchiveSourceOutput,
    BeatCandidateDraft,
    BeatCandidateSnapshot,
    BuildWritingContextPackInput,
    CandidateDetailOutput,
    CandidateDetailSnapshot,
    CandidateExplanationOutput,
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
    GetActionRequestInput,
    GetCandidateInput,
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
    ListSourceDeltasOutput,
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
    RestoreSourceVersionInput,
    RestoreSourceVersionOutput,
    ReviewItemDetailInput,
    ReviewItemDetailOutput,
    ReviewItemOperationInput,
    ReviewItemOperationOutput,
    ReviewItemSnapshot,
    RevokeProjectMemberInput,
    RunActionRequestInput,
    RunActionRequestOutput,
    SelectProjectStorySchemaGenreInput,
    SourceDeltaDetailInput,
    SourceDeltaDetailOutput,
    SourceDeltaSnapshot,
    SourceDeltaSummaryOutput,
    SourceSummaryOutput,
    SourceVersionDetailOutput,
    SourceVersionDiffHunkOutput,
    SourceVersionDiffInput,
    SourceVersionDiffLineOutput,
    SourceVersionDiffOutput,
    SourceVersionDiffSummaryOutput,
    StorySchemaPackOutput,
    StorytellingControlDraft,
    SubmitActionRequestInput,
    SubmitActionRequestOutput,
    UpsertProjectMemberInput,
    UpsertProjectStorySchemaOverrideInput,
    WritingContextPackOutput,
)
from sextant.domain.agent_risk import contains_canon_risk_language
from sextant.domain.fact_schema import NON_ENTITY_FACT_REF_TYPES
from sextant.domain.prose_contract_review import review_prose_contract
from sextant.domain.review import (
    AGENT_RISK_LEVELS,
    AGENT_RISK_TYPES,
    REVIEW_RESOLUTIONS,
    REVIEW_TYPE_VALUES,
)
from sextant.domain.story_schema import (
    AGENCY_PROFILE_RELATIONS,
    ANY_SCHEMA_ENTITY,
    BASE_ENTITY_TYPES,
    EffectiveStorySchema,
    StorySchemaPackSnapshot,
    build_effective_story_schema,
    default_base_story_schema_pack,
)
from sextant.ports.object_store import ObjectStore
from sextant.ports.story_draft import StoryDraftProvider
from sextant.ports.story_skills import resolve_story_skill_plan
from sextant.ports.unit_of_work import SextantUnitOfWork

WRITING_ACTIONS = {
    "draft_next_passage",
    "rewrite_current_page",
    "rewrite_span",
    "continue_small_passage",
    "render_current_beat",
}
STORY_DRAFT_MAX_INVALID_ATTEMPTS = 2
TARGET_REQUIRED_ACTIONS = WRITING_ACTIONS | {
    "check_risk",
    "suggest_next_direction",
    "explain_candidate",
    "revise_candidate",
}
ACTION_EXPECTED_OUTPUTS = {
    "ask_memory": {"memory_answer"},
    "check_risk": {"risk_findings"},
    "suggest_next_direction": {"beat_candidates"},
    "explain_candidate": {"candidate_explanation"},
    "revise_candidate": {"draft_candidate", "draft_candidates"},
    "draft_next_passage": {"draft_candidate", "draft_candidates"},
    "rewrite_current_page": {"draft_candidate", "draft_candidates"},
    "rewrite_span": {"draft_candidate", "draft_candidates"},
    "continue_small_passage": {"draft_candidate", "draft_candidates"},
    "render_current_beat": {"draft_candidate", "draft_candidates"},
}

SOURCE_DELTA_KINDS = {"insert", "replace", "delete"}
SOURCE_DELTA_STATUSES = {
    "submitted",
    "source_version_created",
    "normalized",
    "span_extracted",
    "memory_writeback_queued",
    "memory_writeback_completed",
    "rejected_stale_base",
}
AUTHOR_CANON_SOURCE_SCOPES = {"user_draft", "user_published", "author_note"}
CONTEXT_PACK_READINESS_STATUSES = {"pending", "stale", "consumed"}
CONTEXT_PACK_READINESS_REASONS = {
    "memory_dependency_changed",
    "review_dependency_changed",
}


class SubmitActionRequest:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: SubmitActionRequestInput) -> SubmitActionRequestOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        allowed_outputs = ACTION_EXPECTED_OUTPUTS.get(input_data.action_type)
        if allowed_outputs is None:
            raise ApplicationError(
                "unsupported_action_type",
                f"Unsupported action_type: {input_data.action_type}.",
            )
        if input_data.expected_output not in allowed_outputs:
            raise ApplicationError(
                "expected_output_mismatch",
                "expected_output does not match action_type.",
            )
        if input_data.action_type in TARGET_REQUIRED_ACTIONS and input_data.target is None:
            raise ApplicationError(
                "missing_target",
                "This action requires a target source, version, and range.",
            )
        if input_data.target is not None:
            _validate_target(input_data.target)
        _validate_context_budget_constraints(input_data.constraints)
        if not input_data.actor_intent.strip():
            raise ApplicationError("schema_validation_failed", "actor_intent is required.")

        operation = "submit_action_request"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return SubmitActionRequestOutput(
                    action_request_id=_uuid_from_payload(record, "action_request_id"),
                    status=str(record.response_payload["status"]),
                )

            output = uow.create_action_request(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="action_request.submitted",
                subject_ref={"type": "agent_action_request", "id": str(output.action_request_id)},
                decision={
                    "trigger": input_data.trigger,
                    "action_type": input_data.action_type,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "action_request_id": str(output.action_request_id),
                    "status": output.status,
                },
            )
            uow.commit()
            return output


class CreateSource:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: CreateSourceInput) -> CreateSourceOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if not input_data.title.strip():
            raise ApplicationError("schema_validation_failed", "Source title is required.")
        if not input_data.text.strip():
            raise ApplicationError("schema_validation_failed", "Source text is required.")

        operation = "source.create"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return CreateSourceOutput(
                    source_id=_uuid_from_payload(record, "source_id"),
                    version_id=_uuid_from_payload(record, "version_id"),
                    source_delta_id=_uuid_from_payload(record, "source_delta_id"),
                    memory_writeback_job_id=_uuid_from_payload(record, "memory_writeback_job_id"),
                    raw_hash=str(record.response_payload["raw_hash"]),
                )

            raw_hash = sha256(input_data.text.encode("utf-8")).hexdigest()
            source_id_hint = request_hash[:12]
            raw_text_ref = self._object_store.put_text(
                f"raw/{source_id_hint}-{input_data.version_label}.txt",
                input_data.text,
            )
            output = uow.create_source(input_data, raw_text_ref, raw_hash)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="source.created",
                subject_ref={"type": "raw_source", "id": str(output.source_id)},
                decision={
                    "version_id": str(output.version_id),
                    "source_delta_id": str(output.source_delta_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                    "raw_hash": output.raw_hash,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "source_id": str(output.source_id),
                    "version_id": str(output.version_id),
                    "source_delta_id": str(output.source_delta_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                    "raw_hash": output.raw_hash,
                },
            )
            uow.commit()
            return output


class CreateSourceVersion:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: CreateSourceVersionInput) -> CreateSourceVersionOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if not input_data.version_label.strip():
            raise ApplicationError("schema_validation_failed", "Source version label is required.")
        if not input_data.text.strip():
            raise ApplicationError("schema_validation_failed", "Source version text is required.")

        operation = "source_version.create"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if not uow.source_in_project(input_data.project_id, input_data.source_id):
                raise ApplicationError("not_found", "RawSource was not found.")
            if input_data.supersedes_version_id is not None:
                superseded_hash = uow.source_version_hash(input_data.supersedes_version_id)
                if superseded_hash is None:
                    raise ApplicationError("not_found", "Superseded SourceVersion was not found.")
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return CreateSourceVersionOutput(
                    source_id=_uuid_from_payload(record, "source_id"),
                    version_id=_uuid_from_payload(record, "version_id"),
                    raw_hash=str(record.response_payload["raw_hash"]),
                    supersedes_version_id=(
                        _uuid_from_payload(record, "supersedes_version_id")
                        if record.response_payload.get("supersedes_version_id")
                        else None
                    ),
                )

            raw_hash = sha256(input_data.text.encode("utf-8")).hexdigest()
            raw_text_ref = self._object_store.put_text(
                f"raw/{input_data.source_id}-{input_data.version_label}-{request_hash[:12]}.txt",
                input_data.text,
            )
            output = uow.create_source_version(input_data, raw_text_ref, raw_hash)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="source_version.created",
                subject_ref={"type": "source_version", "id": str(output.version_id)},
                decision={
                    "source_id": str(output.source_id),
                    "supersedes_version_id": str(output.supersedes_version_id)
                    if output.supersedes_version_id
                    else None,
                    "raw_hash": output.raw_hash,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "source_id": str(output.source_id),
                    "version_id": str(output.version_id),
                    "raw_hash": output.raw_hash,
                    "supersedes_version_id": str(output.supersedes_version_id)
                    if output.supersedes_version_id
                    else None,
                },
            )
            uow.commit()
            return output


class RestoreSourceVersion:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: RestoreSourceVersionInput) -> RestoreSourceVersionOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        operation = "source_version.restore"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if not uow.source_in_project(input_data.project_id, input_data.source_id):
                raise ApplicationError("not_found", "RawSource was not found.")
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return RestoreSourceVersionOutput(
                    source_id=_uuid_from_payload(record, "source_id"),
                    restored_from_version_id=_uuid_from_payload(record, "restored_from_version_id"),
                    source_delta_id=_uuid_from_payload(record, "source_delta_id"),
                    new_version_id=_uuid_from_payload(record, "new_version_id"),
                    memory_writeback_job_id=_uuid_from_payload(record, "memory_writeback_job_id"),
                )

            target_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    version_id=input_data.version_id,
                )
            )
            if target_version is None:
                raise ApplicationError("not_found", "SourceVersion to restore was not found.")

            latest_versions = uow.list_source_versions(
                ListSourceVersionsInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    limit=1,
                )
            )
            if latest_versions is None or not latest_versions.items:
                raise ApplicationError("not_found", "Latest SourceVersion was not found.")
            latest_summary = latest_versions.items[0]
            if latest_summary.version_id == target_version.version_id:
                raise ApplicationError(
                    "source_version_already_current",
                    "SourceVersion is already the latest version.",
                )
            latest_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    version_id=latest_summary.version_id,
                )
            )
            if latest_version is None:
                raise ApplicationError("not_found", "Latest SourceVersion was not found.")

            target_text = _read_object_text(
                self._object_store,
                target_version.raw_text_ref,
                "Restored SourceVersion raw text object was not found.",
            )
            latest_text = _read_object_text(
                self._object_store,
                latest_version.raw_text_ref,
                "Latest SourceVersion raw text object was not found.",
            )
            delta_input = CreateSourceDeltaInput(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                request_id=input_data.request_id,
                idempotency_key=input_data.idempotency_key,
                source_id=input_data.source_id,
                previous_version_id=latest_version.version_id,
                delta_kind="replace",
                range_start=0,
                range_end=len(latest_text),
                base_hash=latest_version.raw_hash,
                submitted_text=target_text,
                source_type=target_version.source_type,
                source_scope=target_version.source_scope,
                provenance={
                    "restored_from_version_id": str(target_version.version_id),
                    "restore_author_note": input_data.author_note or "",
                },
            )
            submitted_text_ref = self._object_store.put_text(
                f"source-deltas/restore-{request_hash[:12]}.txt",
                target_text,
            )
            restored_text_ref = self._object_store.put_text(
                f"raw/{input_data.source_id}-restore-{request_hash[:12]}.txt",
                target_text,
            )
            delta_output = uow.create_source_delta(
                delta_input,
                submitted_text_ref,
                restored_text_ref,
                _hash_text(target_text),
                _next_version_label(latest_version.version_label),
            )
            output = RestoreSourceVersionOutput(
                source_id=input_data.source_id,
                restored_from_version_id=target_version.version_id,
                source_delta_id=delta_output.source_delta_id,
                new_version_id=delta_output.new_version_id,
                memory_writeback_job_id=delta_output.memory_writeback_job_id,
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="source_version.restored",
                subject_ref={"type": "source_version", "id": str(output.new_version_id)},
                decision={
                    "source_id": str(output.source_id),
                    "restored_from_version_id": str(output.restored_from_version_id),
                    "previous_version_id": str(latest_version.version_id),
                    "source_delta_id": str(output.source_delta_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "source_id": str(output.source_id),
                    "restored_from_version_id": str(output.restored_from_version_id),
                    "source_delta_id": str(output.source_delta_id),
                    "new_version_id": str(output.new_version_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                },
            )
            uow.commit()
            return output


class CreateSourceDelta:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: CreateSourceDeltaInput) -> CreateSourceDeltaOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_accept_range({"start": input_data.range_start, "end": input_data.range_end})
        if input_data.delta_kind not in {"insert", "replace", "delete"}:
            raise ApplicationError("schema_validation_failed", "SourceDelta kind is invalid.")
        if input_data.delta_kind != "delete" and not input_data.submitted_text.strip():
            raise ApplicationError("schema_validation_failed", "SourceDelta text is required.")

        operation = "source_delta.create"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if not uow.source_in_project(input_data.project_id, input_data.source_id):
                raise ApplicationError("not_found", "RawSource was not found.")
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return CreateSourceDeltaOutput(
                    source_delta_id=_uuid_from_payload(record, "source_delta_id"),
                    new_version_id=_uuid_from_payload(record, "new_version_id"),
                    memory_writeback_job_id=_uuid_from_payload(record, "memory_writeback_job_id"),
                )

            previous_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    version_id=input_data.previous_version_id,
                )
            )
            if previous_version is None:
                raise ApplicationError("not_found", "Previous SourceVersion was not found.")
            current_hash = previous_version.raw_hash
            if input_data.base_hash is not None and input_data.base_hash != current_hash:
                raise ApplicationError(
                    "stale_source_version",
                    "SourceDelta base hash does not match current SourceVersion.",
                    {
                        "request_base_hash": input_data.base_hash,
                        "current_hash": current_hash,
                    },
                )
            latest_versions = uow.list_source_versions(
                ListSourceVersionsInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    limit=1,
                )
            )
            latest_version = (
                latest_versions.items[0] if latest_versions and latest_versions.items else None
            )
            if latest_version is None or latest_version.version_id != previous_version.version_id:
                raise ApplicationError(
                    "stale_source_version",
                    "SourceDelta previous SourceVersion is no longer latest.",
                    {
                        "previous_version_id": str(previous_version.version_id),
                        "latest_version_id": str(latest_version.version_id)
                        if latest_version
                        else None,
                    },
                )

            submitted_text_ref = self._object_store.put_text(
                f"source-deltas/{request_hash[:12]}.txt",
                input_data.submitted_text,
            )
            previous_text = _read_object_text(
                self._object_store,
                previous_version.raw_text_ref,
                "Previous SourceVersion raw text object was not found.",
            )
            materialized_text = _apply_source_delta_text(
                previous_text=previous_text,
                submitted_text=input_data.submitted_text,
                delta_kind=input_data.delta_kind,
                range_start=input_data.range_start,
                range_end=input_data.range_end,
            )
            materialized_text_ref = self._object_store.put_text(
                f"raw/{input_data.source_id}-delta-{request_hash[:12]}.txt",
                materialized_text,
            )
            output = uow.create_source_delta(
                input_data,
                submitted_text_ref,
                materialized_text_ref,
                _hash_text(materialized_text),
                _next_version_label(previous_version.version_label),
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="source_delta.created",
                subject_ref={"type": "source_delta", "id": str(output.source_delta_id)},
                decision={
                    "new_version_id": str(output.new_version_id),
                    "job_id": str(output.memory_writeback_job_id),
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "source_delta_id": str(output.source_delta_id),
                    "new_version_id": str(output.new_version_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                },
            )
            uow.commit()
            return output


class AcceptCandidate:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: AcceptCandidateInput) -> AcceptCandidateOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_accept_range(input_data.insert_or_replace_range)
        accepted_text_ref = (input_data.accepted_text_ref or "").strip()
        accepted_text = (input_data.accepted_text or "").strip()
        if accepted_text_ref and accepted_text:
            raise ApplicationError(
                "schema_validation_failed",
                "Provide accepted_text or accepted_text_ref, not both.",
            )
        if not accepted_text_ref and not accepted_text:
            raise ApplicationError(
                "schema_validation_failed",
                "accepted_text or accepted_text_ref is required.",
            )

        operation = "accept_candidate"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return AcceptCandidateOutput(
                    accepted_fragment_id=_uuid_from_payload(record, "accepted_fragment_id"),
                    source_delta_id=_uuid_from_payload(record, "source_delta_id"),
                    new_version_id=_uuid_from_payload(record, "new_version_id"),
                    memory_writeback_job_id=_uuid_from_payload(record, "memory_writeback_job_id"),
                )

            candidate = uow.load_candidate(input_data.candidate_id)
            if candidate is None or candidate.project_id != input_data.project_id:
                raise ApplicationError("not_found", "DraftCandidate was not found.")
            _validate_candidate_acceptance(candidate, input_data)

            if input_data.target_source_id is None or input_data.target_version_id is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Candidate acceptance requires target source and version.",
                )
            target_source_id = input_data.target_source_id
            target_version_id = input_data.target_version_id

            target_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=target_source_id,
                    version_id=target_version_id,
                )
            )
            if target_version is None:
                raise ApplicationError("not_found", "Target SourceVersion was not found.")
            latest_versions = uow.list_source_versions(
                ListSourceVersionsInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=target_source_id,
                    limit=1,
                )
            )
            latest_version = (
                latest_versions.items[0] if latest_versions and latest_versions.items else None
            )
            if latest_version is None or latest_version.version_id != target_version_id:
                raise ApplicationError(
                    "stale_source_version",
                    "Target SourceVersion has been superseded.",
                    {
                        "candidate_target_version_id": str(target_version_id),
                        "latest_version_id": str(latest_version.version_id)
                        if latest_version
                        else None,
                    },
                )
            current_hash = target_version.raw_hash
            if candidate.base_hash != current_hash:
                raise ApplicationError(
                    "stale_source_version",
                    "Target source version has changed.",
                    {"candidate_base_hash": candidate.base_hash, "current_hash": current_hash},
                )

            if accepted_text:
                if self._object_store is None:
                    raise ApplicationError(
                        "schema_validation_failed",
                        "accepted_text requires a configured object store.",
                    )
                accepted_text_ref = self._object_store.put_text(
                    f"accepted/{input_data.candidate_id}-{request_hash[:12]}.txt",
                    input_data.accepted_text or "",
                )
                input_data = replace(input_data, accepted_text_ref=accepted_text_ref)

            if self._object_store is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Candidate acceptance requires a configured object store.",
                )
            previous_text = _read_object_text(
                self._object_store,
                target_version.raw_text_ref,
                "Target SourceVersion raw text object was not found.",
            )
            submitted_text = _read_object_text(
                self._object_store,
                input_data.accepted_text_ref or "",
                "AcceptedFragment text object was not found.",
            )
            input_data = replace(input_data, accepted_text=submitted_text)
            materialized_text = _apply_source_delta_text(
                previous_text=previous_text,
                submitted_text=submitted_text,
                delta_kind="replace",
                range_start=input_data.insert_or_replace_range["start"],
                range_end=input_data.insert_or_replace_range["end"],
            )
            materialized_text_ref = self._object_store.put_text(
                f"raw/{target_source_id}-accepted-{request_hash[:12]}.txt",
                materialized_text,
            )
            output = uow.persist_candidate_acceptance(
                input_data,
                materialized_text_ref,
                _hash_text(materialized_text),
                _next_version_label(target_version.version_label),
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="candidate.accepted",
                subject_ref={"type": "draft_candidate", "id": str(input_data.candidate_id)},
                decision={
                    "accept_mode": input_data.accept_mode,
                    "source_delta_id": str(output.source_delta_id),
                    "new_version_id": str(output.new_version_id),
                    "override_reason": candidate.override_reason,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "accepted_fragment_id": str(output.accepted_fragment_id),
                    "source_delta_id": str(output.source_delta_id),
                    "new_version_id": str(output.new_version_id),
                    "memory_writeback_job_id": str(output.memory_writeback_job_id),
                },
            )
            uow.commit()
            return output


class GetCandidate:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: GetCandidateInput) -> CandidateDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            candidate = uow.load_candidate_detail(input_data.candidate_id)
            if candidate is None or candidate.project_id != input_data.project_id:
                raise ApplicationError("not_found", "DraftCandidate was not found.")
            try:
                text = self._object_store.get_text(candidate.candidate_text_ref)
            except (FileNotFoundError, ValueError) as exc:
                raise ApplicationError(
                    "not_found",
                    "DraftCandidate text object was not found.",
                    {"candidate_text_ref": candidate.candidate_text_ref},
                ) from exc
            return CandidateDetailOutput(
                id=candidate.id,
                action_request_id=candidate.action_request_id,
                mode=candidate.mode,
                text=text,
                status=candidate.status,
                context_pack_id=candidate.context_pack_id,
                target_source_id=candidate.target_source_id,
                target_version_id=candidate.target_version_id,
                target_scene_id=candidate.target_scene_id,
                affected_range=candidate.affected_range,
                base_hash=candidate.base_hash,
                memory_refs=candidate.memory_refs,
                evidence_refs=candidate.evidence_refs,
                override_reason=candidate.override_reason,
                agent_review_findings=candidate.agent_review_findings,
            )


class OperateCandidate:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: CandidateOperationInput) -> CandidateOperationOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if input_data.operation not in {"reject", "override_block", "revise"}:
            raise ApplicationError("schema_validation_failed", "Unsupported candidate operation.")
        if (
            input_data.operation == "override_block"
            and not (input_data.override_reason or "").strip()
        ):
            raise ApplicationError(
                "schema_validation_failed",
                "Blocked candidate override requires a reason.",
            )
        if input_data.operation == "revise":
            revised_text = (input_data.revised_text or "").strip()
            revised_text_ref = (input_data.revised_text_ref or "").strip()
            if revised_text and revised_text_ref:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Provide revised_text or revised_text_ref, not both.",
                )
            if not revised_text and not revised_text_ref:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Candidate revise requires revised text.",
                )

        operation = f"candidate.{input_data.operation}"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return CandidateOperationOutput(
                    candidate_id=_uuid_from_payload(record, "candidate_id"),
                    status=str(record.response_payload["status"]),
                    replacement_candidate_id=(
                        _uuid_from_payload(record, "replacement_candidate_id")
                        if record.response_payload.get("replacement_candidate_id")
                        else None
                    ),
                    override_reason=cast(
                        str | None, record.response_payload.get("override_reason")
                    ),
                )

            candidate = uow.load_candidate(input_data.candidate_id)
            if candidate is None or candidate.project_id != input_data.project_id:
                raise ApplicationError("not_found", "DraftCandidate was not found.")
            _validate_candidate_operation(candidate, input_data)

            if input_data.operation == "revise" and input_data.revised_text:
                if self._object_store is None:
                    raise ApplicationError(
                        "schema_validation_failed",
                        "revised_text requires a configured object store.",
                    )
                revised_text_ref = self._object_store.put_text(
                    f"candidates/{input_data.candidate_id}-revision-{request_hash[:12]}.txt",
                    input_data.revised_text,
                )
                input_data = replace(input_data, revised_text_ref=revised_text_ref)

            output = uow.persist_candidate_operation(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type=operation,
                subject_ref={"type": "draft_candidate", "id": str(input_data.candidate_id)},
                decision={
                    "status": output.status,
                    "replacement_candidate_id": str(output.replacement_candidate_id)
                    if output.replacement_candidate_id
                    else None,
                    "author_note": input_data.author_note,
                    "override_reason": output.override_reason,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "candidate_id": str(output.candidate_id),
                    "status": output.status,
                    "replacement_candidate_id": str(output.replacement_candidate_id)
                    if output.replacement_candidate_id
                    else None,
                    "override_reason": output.override_reason,
                },
            )
            uow.commit()
            return output


class GetProject:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: GetProjectInput) -> ProjectDetailOutput:
        with self._uow_factory() as uow:
            output = uow.get_project(input_data)
            if output is None:
                raise ApplicationError("permission_denied", "Project is not accessible.")
            return output


class ListProjectMembers:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListProjectMembersInput) -> ListProjectMembersOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_project_members(input_data)


class ListProjectInvitations:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListProjectInvitationsInput) -> ListProjectInvitationsOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_project_invitations(input_data)


class UpsertProjectMember:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: UpsertProjectMemberInput) -> ProjectMemberOperationOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_project_member_role(input_data.role)
        operation = "project_member.upsert"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            actor_role = _require_project_member_writer(
                uow, input_data.project_id, input_data.actor_id
            )
            target_role = uow.project_actor_role(input_data.project_id, input_data.member_actor_id)
            if input_data.role == "owner" and actor_role != "owner":
                raise ApplicationError(
                    "permission_denied",
                    "Only project owners can grant owner membership.",
                )
            if target_role == "owner" and input_data.role != "owner":
                if actor_role != "owner":
                    raise ApplicationError(
                        "permission_denied",
                        "Only project owners can change owner membership.",
                    )
                if uow.active_project_owner_count(input_data.project_id) <= 1:
                    raise ApplicationError(
                        "invalid_state_transition",
                        "Cannot remove the last active owner from a project.",
                    )
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return ProjectMemberOperationOutput(
                    member=_project_member_from_payload(record.response_payload["member"]),
                    status=str(record.response_payload["status"]),
                )

            output = uow.upsert_project_member(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="project_member.upserted",
                subject_ref={"type": "project_member", "id": str(output.member.id)},
                decision={
                    "member_actor_id": str(input_data.member_actor_id),
                    "role": output.member.role,
                    "status": output.status,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=_project_member_operation_payload(output),
            )
            uow.commit()
            return output


class RevokeProjectMember:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: RevokeProjectMemberInput) -> ProjectMemberOperationOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        operation = "project_member.revoke"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            actor_role = _require_project_member_writer(
                uow, input_data.project_id, input_data.actor_id
            )
            target_role = uow.project_actor_role(input_data.project_id, input_data.member_actor_id)
            if target_role == "owner":
                if actor_role != "owner":
                    raise ApplicationError(
                        "permission_denied",
                        "Only project owners can revoke owner membership.",
                    )
                if uow.active_project_owner_count(input_data.project_id) <= 1:
                    raise ApplicationError(
                        "invalid_state_transition",
                        "Cannot revoke the last active owner from a project.",
                    )
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return ProjectMemberOperationOutput(
                    member=_project_member_from_payload(record.response_payload["member"]),
                    status=str(record.response_payload["status"]),
                )

            member = uow.revoke_project_member(input_data)
            if member is None:
                raise ApplicationError("not_found", "Project member was not found.")
            output = ProjectMemberOperationOutput(member=member, status=member.status)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="project_member.revoked",
                subject_ref={"type": "project_member", "id": str(member.id)},
                decision={
                    "member_actor_id": str(input_data.member_actor_id),
                    "role": member.role,
                    "status": member.status,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=_project_member_operation_payload(output),
            )
            uow.commit()
            return output


class CreateProjectInvitation:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: CreateProjectInvitationInput) -> ProjectInvitationSnapshot:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_project_member_role(input_data.role)
        _validate_invitation_refs(input_data)
        operation = "project_invitation.create"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            actor_role = _require_project_member_writer(
                uow, input_data.project_id, input_data.actor_id
            )
            if input_data.role == "owner" and actor_role != "owner":
                raise ApplicationError(
                    "permission_denied",
                    "Only project owners can invite owner membership.",
                )
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _project_invitation_from_payload(record.response_payload)

            invitation = uow.create_project_invitation(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="project_invitation.created",
                subject_ref={"type": "project_invitation", "id": str(invitation.id)},
                decision={
                    "member_actor_id": str(invitation.member_actor_id),
                    "role": invitation.role,
                    "status": invitation.status,
                    "delivery_status": invitation.delivery_status,
                    "token_status": invitation.token_status,
                    "delivery_provider_ref": invitation.delivery_provider_ref,
                    "token_issuer_ref": invitation.token_issuer_ref,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=_project_invitation_payload(invitation),
            )
            uow.commit()
            return invitation


class RecordProjectInvitationExternalProof:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(
        self, input_data: RecordProjectInvitationExternalProofInput
    ) -> ProjectInvitationSnapshot:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_invitation_external_proof_refs(input_data)
        operation = "project_invitation.external_proof"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _require_project_member_writer(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _project_invitation_from_payload(record.response_payload)

            existing = uow.get_project_invitation(input_data.project_id, input_data.invitation_id)
            if existing is None:
                raise ApplicationError("not_found", "Project invitation was not found.")
            if existing.status != "pending_external_delivery":
                raise ApplicationError(
                    "invalid_state_transition",
                    "Project invitation external proof has already been recorded.",
                )
            if input_data.token_proof_ref is not None and existing.token_issuer_ref is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Token proof ref requires an invitation token issuer ref.",
                )

            invitation = uow.record_project_invitation_external_proof(input_data)
            if invitation is None:
                raise ApplicationError("not_found", "Project invitation was not found.")
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="project_invitation.external_proof_recorded",
                subject_ref={"type": "project_invitation", "id": str(invitation.id)},
                decision={
                    "member_actor_id": str(invitation.member_actor_id),
                    "role": invitation.role,
                    "status": invitation.status,
                    "delivery_status": invitation.delivery_status,
                    "token_status": invitation.token_status,
                    "delivery_proof_ref": invitation.delivery_proof_ref,
                    "token_proof_ref": invitation.token_proof_ref,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=_project_invitation_payload(invitation),
            )
            uow.commit()
            return invitation


class GetActionRequest:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: GetActionRequestInput) -> ActionRequestSnapshot:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            action_request = uow.load_action_request(input_data.action_request_id)
            if action_request is None or action_request.project_id != input_data.project_id:
                raise ApplicationError("not_found", "ActionRequest was not found.")
            return action_request


class GetSource:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: GetSourceInput) -> SourceSummaryOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.get_source(input_data)
            if output is None:
                raise ApplicationError("not_found", "Source was not found.")
            return output


class GetSourceVersion:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: GetSourceVersionInput) -> SourceVersionDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            source_version = uow.load_source_version(input_data)
            if source_version is None:
                raise ApplicationError("not_found", "SourceVersion was not found.")
            try:
                text = self._object_store.get_text(source_version.raw_text_ref)
            except (FileNotFoundError, ValueError) as exc:
                raise ApplicationError(
                    "not_found",
                    "SourceVersion raw text object was not found.",
                    {"raw_text_ref": source_version.raw_text_ref},
                ) from exc
            return SourceVersionDetailOutput(
                source_id=source_version.source_id,
                version_id=source_version.version_id,
                title=source_version.title,
                source_type=source_version.source_type,
                source_scope=source_version.source_scope,
                version_label=source_version.version_label,
                raw_hash=source_version.raw_hash,
                text=text,
            )


class GetSourceVersionDiff:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: SourceVersionDiffInput) -> SourceVersionDiffOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            base_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    version_id=input_data.base_version_id,
                )
            )
            compare_version = uow.load_source_version(
                GetSourceVersionInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_id=input_data.source_id,
                    version_id=input_data.compare_version_id,
                )
            )
            if base_version is None or compare_version is None:
                raise ApplicationError("not_found", "SourceVersion was not found.")
            base_text = _read_object_text(
                self._object_store,
                base_version.raw_text_ref,
                "Base SourceVersion raw text object was not found.",
            )
            compare_text = _read_object_text(
                self._object_store,
                compare_version.raw_text_ref,
                "Compare SourceVersion raw text object was not found.",
            )
            hunks, summary = _source_version_line_diff(base_text, compare_text)
            return SourceVersionDiffOutput(
                source_id=input_data.source_id,
                base_version_id=base_version.version_id,
                compare_version_id=compare_version.version_id,
                base_version_label=base_version.version_label,
                compare_version_label=compare_version.version_label,
                base_raw_hash=base_version.raw_hash,
                compare_raw_hash=compare_version.raw_hash,
                summary=summary,
                hunks=hunks,
            )


class ListSourceVersions:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListSourceVersionsInput) -> ListSourceVersionsOutput:
        normalized = replace(input_data, limit=max(1, min(input_data.limit, 100)))
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, normalized.project_id, normalized.actor_id)
            output = uow.list_source_versions(normalized)
            if output is None:
                raise ApplicationError("not_found", "RawSource was not found.")
            return output


class ListSources:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListSourcesInput) -> ListSourcesOutput:
        normalized = replace(
            input_data,
            query=input_data.query.strip(),
            limit=max(1, min(input_data.limit, 100)),
        )
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, normalized.project_id, normalized.actor_id)
            return uow.list_sources(normalized)


class ArchiveSource:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ArchiveSourceInput) -> ArchiveSourceOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        operation = "source.archive"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return ArchiveSourceOutput(
                    source_id=_uuid_from_payload(record, "source_id"),
                    status=str(record.response_payload["status"]),
                    archived_at=datetime.fromisoformat(str(record.response_payload["archived_at"])),
                    archived_by=_uuid_from_payload(record, "archived_by"),
                )

            output = uow.archive_source(input_data)
            if output is None:
                raise ApplicationError("not_found", "RawSource was not found.")
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="source.archived",
                subject_ref={"type": "source", "id": str(output.source_id)},
                decision={
                    "idempotency_key": input_data.idempotency_key,
                    "author_note": input_data.author_note,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "source_id": str(output.source_id),
                    "status": output.status,
                    "archived_at": output.archived_at.isoformat(),
                    "archived_by": str(output.archived_by),
                },
            )
            uow.commit()
            return output


class GetJobDetail:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: JobDetailInput) -> JobDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.get_job_detail(input_data)
            if output is None:
                raise ApplicationError("not_found", "Job was not found.")
            return output


class OperateJob:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: JobOperationInput) -> JobDetailOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if input_data.operation not in {"cancel", "retry"}:
            raise ApplicationError("schema_validation_failed", "Unsupported job operation.")
        idempotency_operation = f"job.{input_data.operation}"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(
                uow, input_data, idempotency_operation, request_hash
            ):
                return _job_detail_from_payload(record.response_payload)

            current = uow.get_job_detail(
                JobDetailInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    job_id=input_data.job_id,
                )
            )
            if current is None:
                raise ApplicationError("not_found", "Job was not found.")
            _validate_job_operation(current, input_data.operation)
            output = uow.operate_job(input_data)
            if output is None:
                raise ApplicationError("not_found", "Job was not found.")
            event_type = (
                "job.cancelled" if input_data.operation == "cancel" else "job.retry_requested"
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type=event_type,
                subject_ref={"type": "job_record", "id": str(input_data.job_id)},
                decision={
                    "operation": input_data.operation,
                    "previous_status": current.status,
                    "job_type": current.job_type,
                    "author_note": input_data.author_note,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=idempotency_operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class ListSourceDeltas:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: ListSourceDeltasInput) -> ListSourceDeltasOutput:
        if input_data.status is not None and input_data.status not in SOURCE_DELTA_STATUSES:
            raise ApplicationError("schema_validation_failed", "SourceDelta status is invalid.")
        if input_data.delta_kind is not None and input_data.delta_kind not in SOURCE_DELTA_KINDS:
            raise ApplicationError("schema_validation_failed", "SourceDelta kind is invalid.")
        if input_data.limit < 1 or input_data.limit > 100:
            raise ApplicationError("schema_validation_failed", "SourceDelta limit must be 1-100.")
        after_created_at: datetime | None = None
        after_id: UUID | None = None
        if input_data.cursor is not None:
            after_created_at, after_id = _decode_source_delta_cursor(input_data.cursor)
        fetch_input = replace(
            input_data,
            after_created_at=after_created_at,
            after_id=after_id,
        )
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            snapshots = uow.list_source_deltas(fetch_input)
            page_snapshots = snapshots[: input_data.limit]
            summaries = []
            for snapshot in page_snapshots:
                submitted_text = self._read_delta_text(snapshot)
                summaries.append(_source_delta_summary(snapshot, submitted_text))
            next_cursor = (
                _encode_source_delta_cursor(page_snapshots[-1])
                if len(snapshots) > input_data.limit and page_snapshots
                else None
            )
            return ListSourceDeltasOutput(items=summaries, next_cursor=next_cursor)

    def _read_delta_text(self, snapshot: SourceDeltaSnapshot) -> str:
        try:
            return self._object_store.get_text(snapshot.submitted_text_ref)
        except (FileNotFoundError, ValueError) as exc:
            raise ApplicationError(
                "not_found",
                "SourceDelta submitted text object was not found.",
                {"submitted_text_ref": snapshot.submitted_text_ref},
            ) from exc


class GetSourceDeltaDetail:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store

    def execute(self, input_data: SourceDeltaDetailInput) -> SourceDeltaDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            snapshot = uow.get_source_delta_detail(input_data)
            if snapshot is None:
                raise ApplicationError("not_found", "SourceDelta was not found.")
            try:
                submitted_text = self._object_store.get_text(snapshot.submitted_text_ref)
            except (FileNotFoundError, ValueError) as exc:
                raise ApplicationError(
                    "not_found",
                    "SourceDelta submitted text object was not found.",
                    {"submitted_text_ref": snapshot.submitted_text_ref},
                ) from exc
            return _source_delta_detail(snapshot, submitted_text)


class ListReviewItems:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListReviewItemsInput) -> ListReviewItemsOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_review_items(input_data)


class ListCanonicalEntities:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListCanonicalEntitiesInput) -> ListCanonicalEntitiesOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_canonical_entities(input_data)


class ListStoryScenes:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListStoryScenesInput) -> ListStoryScenesOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_story_scenes(input_data)


class GetProjectStorySchema:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: GetProjectStorySchemaInput) -> ProjectStorySchemaOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.get_project_story_schema(input_data)


class ListStorySchemaPacks:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListStorySchemaPacksInput) -> ListStorySchemaPacksOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_story_schema_packs(input_data)


class CreateStorySchemaGenrePack:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        admin_actor_ids: frozenset[UUID],
    ) -> None:
        self._uow_factory = uow_factory
        self._admin_actor_ids = admin_actor_ids

    def execute(self, input_data: CreateStorySchemaGenrePackInput) -> StorySchemaPackOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _ensure_system_admin(self._admin_actor_ids, input_data.actor_id)
        _validate_story_schema_genre_pack(input_data)

        operation = "story_schema.genre_pack.create"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _story_schema_pack_from_payload(record.response_payload)

            output = uow.create_story_schema_genre_pack(input_data)
            if output is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Genre Story Schema Pack could not be provisioned.",
                )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="story_schema.genre_pack.created",
                subject_ref={"type": "story_schema_pack", "id": str(output.id)},
                decision={
                    "pack_name": output.pack_name,
                    "version": output.version,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class DeprecateStorySchemaGenrePack:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        admin_actor_ids: frozenset[UUID],
    ) -> None:
        self._uow_factory = uow_factory
        self._admin_actor_ids = admin_actor_ids

    def execute(self, input_data: DeprecateStorySchemaGenrePackInput) -> StorySchemaPackOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _ensure_system_admin(self._admin_actor_ids, input_data.actor_id)

        operation = "story_schema.genre_pack.deprecate"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _story_schema_pack_from_payload(record.response_payload)

            output = uow.deprecate_story_schema_genre_pack(input_data)
            if output is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Genre Story Schema Pack was not found or is still used by an active project.",
                )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="story_schema.genre_pack.deprecated",
                subject_ref={"type": "story_schema_pack", "id": str(output.id)},
                decision={
                    "pack_name": output.pack_name,
                    "version": output.version,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class SelectProjectStorySchemaGenre:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: SelectProjectStorySchemaGenreInput) -> ProjectStorySchemaOutput:
        _validate_idempotency_key(input_data.idempotency_key)

        operation = "story_schema.genre_pack.select"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _project_story_schema_from_payload(record.response_payload)

            output = uow.select_project_story_schema_genre(input_data)
            if output is None:
                raise ApplicationError(
                    "not_found",
                    "Genre Story Schema Pack was not found or is not active.",
                )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="story_schema.genre_pack.selected",
                subject_ref={"type": "project", "id": str(input_data.project_id)},
                decision={
                    "genre_schema_pack_id": str(input_data.genre_schema_pack_id)
                    if input_data.genre_schema_pack_id
                    else None,
                    "binding_id": str(output.binding_id) if output.binding_id else None,
                    "source_pack_versions": output.effective_schema.get("source_pack_versions", []),
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class UpsertProjectStorySchemaOverride:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(
        self, input_data: UpsertProjectStorySchemaOverrideInput
    ) -> ProjectStorySchemaOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        _validate_story_schema_override(input_data)

        operation = "story_schema.project_override.upsert"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _project_story_schema_from_payload(record.response_payload)

            output = uow.upsert_project_story_schema_override(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="story_schema.project_override.upserted",
                subject_ref={"type": "project", "id": str(input_data.project_id)},
                decision={
                    "pack_name": input_data.pack_name,
                    "project_override_pack_id": str(output.project_override_pack_id)
                    if output.project_override_pack_id
                    else None,
                    "binding_id": str(output.binding_id) if output.binding_id else None,
                    "source_pack_versions": output.effective_schema.get("source_pack_versions", []),
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class GetReviewItemDetail:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ReviewItemDetailInput) -> ReviewItemDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.get_review_item_detail(input_data)
            if output is None:
                raise ApplicationError("not_found", "ReviewItem was not found.")
            return output


class ListMemoryPages:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListMemoryPagesInput) -> ListMemoryPagesOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_memory_pages(input_data)


class GetMemoryPageDetail:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: MemoryPageDetailInput) -> MemoryPageDetailOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.get_memory_page_detail(input_data)
            if output is None:
                raise ApplicationError("not_found", "MemoryPage was not found.")
            return output


class OperateMemoryPageThread:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        input_data: MemoryPageThreadOperationInput,
    ) -> MemoryPageThreadOperationOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        update_type = input_data.update_type.strip()
        if update_type not in {"keeps_open", "narrows", "pays_off", "closes"}:
            raise ApplicationError(
                "schema_validation_failed",
                "MemoryPage open-thread update_type is not whitelisted.",
            )
        if not input_data.thread_id.strip():
            raise ApplicationError(
                "schema_validation_failed",
                "MemoryPage open-thread id is required.",
            )
        if not input_data.author_note.strip():
            raise ApplicationError(
                "schema_validation_failed",
                "Author note is required for MemoryPage open-thread operations.",
            )
        if input_data.summary is not None and not input_data.summary.strip():
            raise ApplicationError(
                "schema_validation_failed",
                "MemoryPage open-thread summary cannot be blank.",
            )

        operation = "memory_page.open_thread.operate"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _memory_page_thread_operation_from_payload(record.response_payload)

            existing = uow.get_memory_page_detail(
                MemoryPageDetailInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    memory_page_id=input_data.memory_page_id,
                )
            )
            if existing is None:
                raise ApplicationError("not_found", "MemoryPage was not found.")
            if not _memory_page_detail_contains_thread(existing, input_data.thread_id):
                raise ApplicationError(
                    "not_found",
                    "MemoryPage open thread was not found.",
                )

            try:
                output = uow.persist_memory_page_thread_operation(input_data)
            except RuntimeError as exc:
                if "SourceSpan evidence" in str(exc):
                    raise ApplicationError(
                        "invalid_state_transition",
                        "MemoryPage open thread cannot be updated without valid "
                        "SourceSpan evidence.",
                    ) from exc
                raise
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type=operation,
                subject_ref={
                    "type": "memory_page_thread",
                    "id": input_data.thread_id,
                    "memory_page_id": str(input_data.memory_page_id),
                },
                decision={
                    "update_type": output.update_type,
                    "status": output.status,
                    "author_note": input_data.author_note,
                    "summary": input_data.summary,
                    "side_effects": output.side_effects,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class ListGraphProjectionEdges:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListGraphProjectionEdgesInput) -> ListGraphProjectionEdgesOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_graph_projection_edges(input_data)


class GetMemoryWritebackPreview:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: MemoryWritebackPreviewInput) -> MemoryWritebackPreviewOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.memory_writeback_preview(input_data)
            if output is None:
                raise ApplicationError("not_found", "SourceDelta was not found.")
            return output


class ConfirmMemoryWritebackDecision:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: MemoryWritebackDecisionInput) -> MemoryWritebackDecisionOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if input_data.decision not in {"accept", "reject", "correct"}:
            raise ApplicationError(
                "schema_validation_failed",
                "Memory writeback decision is not whitelisted.",
            )
        if input_data.decision == "correct" and not input_data.correction:
            raise ApplicationError(
                "schema_validation_failed",
                "Correction payload is required for correct decisions.",
            )
        if not _valid_item_ref(input_data.item_ref):
            raise ApplicationError(
                "schema_validation_failed",
                "Memory writeback decision item_ref must include type and id.",
            )

        operation = "memory_writeback_preview.decision"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _memory_writeback_decision_from_payload(record.response_payload)

            preview = uow.memory_writeback_preview(
                MemoryWritebackPreviewInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    source_delta_id=input_data.source_delta_id,
                )
            )
            if preview is None:
                raise ApplicationError("not_found", "SourceDelta was not found.")
            if not _preview_contains_item(preview, input_data.item_ref):
                raise ApplicationError(
                    "not_found",
                    "Memory writeback preview item was not found for this SourceDelta.",
                )
            if blocking_review := _preview_policy_blocking_fact_promotion(
                preview,
                input_data,
            ):
                raise ApplicationError(
                    "policy_blocked_promotion",
                    "High-risk ReviewItem blocks canon promotion for this fact.",
                    {
                        "fact_id": str(input_data.item_ref["id"]),
                        "review_item_id": str(blocking_review.id),
                        "review_type": blocking_review.review_type,
                        "severity": blocking_review.severity,
                    },
                )

            output = uow.persist_memory_writeback_decision(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="memory_writeback_preview.decision",
                subject_ref={"type": "source_delta", "id": str(input_data.source_delta_id)},
                decision={
                    "item_ref": input_data.item_ref,
                    "decision": input_data.decision,
                    "author_note": input_data.author_note,
                    "correction": input_data.correction or {},
                    "replacement_refs": input_data.replacement_refs or [],
                    "side_effects": output.side_effects,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class OperateReviewItem:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ReviewItemOperationInput) -> ReviewItemOperationOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        operation = input_data.operation
        if operation not in {"resolve", "dismiss", "reopen"}:
            raise ApplicationError("schema_validation_failed", "Unsupported review operation.")
        if operation == "resolve":
            if input_data.resolution is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Review resolution is required.",
                )
            if input_data.resolution not in REVIEW_RESOLUTIONS:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Review resolution is not whitelisted.",
                )
            _validate_review_resolution_payload(input_data)

        idempotency_operation = f"review_item.{operation}"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(
                uow, input_data, idempotency_operation, request_hash
            ):
                return ReviewItemOperationOutput(
                    review_item_id=_uuid_from_payload(record, "review_item_id"),
                    status=str(record.response_payload["status"]),
                    resolution=cast(str | None, record.response_payload.get("resolution")),
                    side_effects=cast(dict[str, object], record.response_payload["side_effects"]),
                )

            review_item = uow.load_review_item(input_data.review_item_id)
            if review_item is None or review_item.project_id != input_data.project_id:
                raise ApplicationError("not_found", "ReviewItem was not found.")
            _validate_review_transition(review_item, input_data)
            _validate_review_correction_payload(review_item, input_data)
            _validate_source_scope_conflict_resolution_payload(review_item, input_data)
            if _review_requires_replacement_source_delta(
                input_data
            ) or _source_scope_conflict_requires_replacement_source_delta(
                review_item,
                input_data,
            ):
                replacement_source_delta_ids = _review_replacement_source_delta_ids(
                    input_data,
                )
                if not uow.source_deltas_exist(
                    input_data.project_id,
                    replacement_source_delta_ids,
                ):
                    raise ApplicationError(
                        "not_found",
                        "Replacement SourceDelta refs must point to existing "
                        "SourceDelta rows in the review project.",
                    )
                if _source_scope_conflict_requires_author_source_delta(
                    review_item,
                    input_data,
                ) and not uow.source_deltas_have_source_scopes(
                    input_data.project_id,
                    replacement_source_delta_ids,
                    AUTHOR_CANON_SOURCE_SCOPES,
                ):
                    raise ApplicationError(
                        "schema_validation_failed",
                        "source_scope_conflict ReviewItems from model_suggestion require "
                        "author-backed SourceDelta refs.",
                    )
            if _review_requires_replacement_refs(input_data):
                replacement_refs_by_type = _review_replacement_ref_ids(input_data)
                if not uow.review_replacement_refs_exist(
                    input_data.project_id,
                    replacement_refs_by_type,
                ):
                    raise ApplicationError(
                        "not_found",
                        "Replacement refs must point to existing SourceDelta, "
                        "ReviewItem, or SourceSpan rows in the review project.",
                    )
            elif input_data.replacement_refs:
                replacement_refs_by_type = _review_replacement_ref_ids(input_data)
                if not replacement_refs_by_type or not uow.review_replacement_refs_exist(
                    input_data.project_id,
                    replacement_refs_by_type,
                ):
                    raise ApplicationError(
                        "not_found",
                        "Replacement refs must point to existing SourceDelta, "
                        "ReviewItem, or SourceSpan rows in the review project.",
                    )
            if input_data.correction:
                alias_record_id, target_entity_id = _review_alias_correction_ids(
                    review_item,
                    input_data,
                )
                boundary_scene_refs = _review_alias_boundary_scene_refs(input_data)
                if not uow.alias_correction_target_exists(
                    input_data.project_id,
                    alias_record_id,
                    target_entity_id,
                    boundary_scene_refs,
                ):
                    raise ApplicationError(
                        "not_found",
                        "Alias correction target or boundary scene was not found in "
                        "the review project, or boundary order is invalid.",
                    )

            side_effects = _review_side_effects(input_data)
            output = uow.persist_review_item_operation(
                replace(input_data, side_effects=side_effects)
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type=f"review_item.{operation}",
                subject_ref={"type": "review_item", "id": str(input_data.review_item_id)},
                decision={
                    "resolution": input_data.resolution,
                    "author_note": input_data.author_note,
                    "replacement_refs": input_data.replacement_refs or [],
                    "correction": input_data.correction or {},
                    "side_effects": output.side_effects,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=idempotency_operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload={
                    "review_item_id": str(output.review_item_id),
                    "status": output.status,
                    "resolution": output.resolution,
                    "side_effects": output.side_effects,
                },
            )
            uow.commit()
            return output


class AnswerWithEvidence:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: MemoryAnswerInput) -> MemoryAnswerOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if not input_data.question.strip():
            raise ApplicationError("schema_validation_failed", "Memory question is required.")

        operation = "memory.answer"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _memory_answer_from_payload(record.response_payload)

            output = uow.answer_memory(input_data)
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="memory.answer",
                subject_ref={"type": "memory_answer", "question": input_data.question},
                decision={
                    "answer_type": output.answer_type,
                    "confidence": output.confidence,
                    "source_span_refs": output.source_span_refs,
                    "affected_entities": output.affected_entities,
                    "caveats": output.caveats,
                    "related_review_items": [str(item) for item in output.related_review_items],
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class BuildWritingContextPack:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: BuildWritingContextPackInput) -> WritingContextPackOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        if not input_data.mode.strip():
            raise ApplicationError("schema_validation_failed", "Context pack mode is required.")
        _validate_context_budget_constraints(input_data.constraints or {})

        operation = "context_pack.build"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _context_pack_from_payload(record.response_payload)

            output = uow.build_writing_context_pack(input_data)
            consumed_readiness = uow.consume_context_pack_readiness(
                project_id=input_data.project_id,
                context_pack_id=output.context_pack_id,
                evidence_refs=output.evidence_refs,
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="context_pack.built",
                subject_ref={"type": "agent_context_pack", "id": str(output.context_pack_id)},
                decision={
                    "mode": input_data.mode,
                    "evidence_refs": output.evidence_refs,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            if consumed_readiness:
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="context_pack.readiness_consumed",
                    subject_ref={
                        "type": "agent_context_pack",
                        "id": str(output.context_pack_id),
                    },
                    decision={
                        "readiness_ids": [str(item["id"]) for item in consumed_readiness],
                        "source_span_ids": [
                            str(item["source_span_id"]) for item in consumed_readiness
                        ],
                    },
                )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


class GetWritingContextPack:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ContextPackDetailInput) -> WritingContextPackOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            output = uow.get_writing_context_pack(input_data)
            if output is None:
                raise ApplicationError("not_found", "WritingContextPack was not found.")
            return output


class ListWritingContextPacks:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListContextPacksInput) -> ListContextPacksOutput:
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_writing_context_packs(input_data)


class ListContextPackReadiness:
    def __init__(self, uow_factory: Callable[[], SextantUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def execute(self, input_data: ListContextPackReadinessInput) -> ListContextPackReadinessOutput:
        if (
            input_data.status is not None
            and input_data.status not in CONTEXT_PACK_READINESS_STATUSES
        ):
            raise ApplicationError(
                "schema_validation_failed",
                "Unsupported ContextPackReadiness status.",
            )
        if (
            input_data.reason is not None
            and input_data.reason not in CONTEXT_PACK_READINESS_REASONS
        ):
            raise ApplicationError(
                "schema_validation_failed",
                "Unsupported ContextPackReadiness reason.",
            )
        with self._uow_factory() as uow:
            _ensure_project_readable(uow, input_data.project_id, input_data.actor_id)
            return uow.list_context_pack_readiness(input_data)


class RunActionRequest:
    def __init__(
        self,
        uow_factory: Callable[[], SextantUnitOfWork],
        object_store: ObjectStore | None,
        story_draft_provider: StoryDraftProvider | None,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_store = object_store
        self._story_draft_provider = story_draft_provider

    def execute(self, input_data: RunActionRequestInput) -> RunActionRequestOutput:
        _validate_idempotency_key(input_data.idempotency_key)
        operation = "action_request.run"
        request_hash = _input_hash(input_data)
        with self._uow_factory() as uow:
            _ensure_project(uow, input_data.project_id, input_data.actor_id)
            if record := _load_idempotency_record(uow, input_data, operation, request_hash):
                return _action_request_run_from_payload(record.response_payload)

            action_request = uow.load_action_request(input_data.action_request_id)
            if action_request is None or action_request.project_id != input_data.project_id:
                raise ApplicationError("not_found", "ActionRequest was not found.")
            if action_request.status not in {"submitted", "running"}:
                raise ApplicationError(
                    "invalid_state_transition",
                    "Only submitted ActionRequests can be run.",
                )
            resolved_skill_plan = resolve_story_skill_plan(action_type=action_request.action_type)
            if action_request.action_type == "ask_memory":
                memory_answer = uow.answer_memory(
                    _memory_answer_input_from_action_request(input_data, action_request)
                )
                status = uow.update_action_request_status(input_data.action_request_id, "succeeded")
                if status is None:
                    raise ApplicationError("not_found", "ActionRequest was not found.")
                output = RunActionRequestOutput(
                    action_request_id=input_data.action_request_id,
                    status=status,
                    output_type="memory_answer",
                    context_pack_id=None,
                    draft_candidate_ids=[],
                    risk_finding_ids=[],
                    beat_candidate_ids=[],
                    memory_answer=memory_answer,
                )
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="action_request.run",
                    subject_ref={
                        "type": "agent_action_request",
                        "id": str(input_data.action_request_id),
                    },
                    decision={
                        "output_type": output.output_type,
                        "answer_type": memory_answer.answer_type,
                        "confidence": memory_answer.confidence,
                        "source_span_refs": memory_answer.source_span_refs,
                        "affected_entities": memory_answer.affected_entities,
                        "caveats": memory_answer.caveats,
                        "related_review_items": [
                            str(item) for item in memory_answer.related_review_items
                        ],
                        "resolved_skill_plan": resolved_skill_plan,
                        "idempotency_key": input_data.idempotency_key,
                    },
                )
                uow.store_idempotency_record(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    operation=operation,
                    idempotency_key=input_data.idempotency_key,
                    request_hash=request_hash,
                    response_payload=cast(dict[str, object], _jsonable(asdict(output))),
                )
                uow.commit()
                return output
            if action_request.action_type == "check_risk":
                if self._object_store is None:
                    raise ApplicationError(
                        "schema_validation_failed",
                        "check_risk ActionRequest run requires object storage.",
                    )
                findings = _risk_findings_from_action_request(
                    input_data, action_request, self._object_store
                )
                output = uow.persist_action_request_risk_findings(
                    PersistActionRequestRiskFindingsInput(
                        project_id=input_data.project_id,
                        actor_id=input_data.actor_id,
                        action_request_id=input_data.action_request_id,
                        findings=findings,
                    )
                )
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="action_request.run",
                    subject_ref={
                        "type": "agent_action_request",
                        "id": str(input_data.action_request_id),
                    },
                    decision={
                        "output_type": output.output_type,
                        "risk_finding_ids": [
                            str(finding_id) for finding_id in output.risk_finding_ids
                        ],
                        "resolved_skill_plan": resolved_skill_plan,
                        "idempotency_key": input_data.idempotency_key,
                    },
                )
                uow.store_idempotency_record(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    operation=operation,
                    idempotency_key=input_data.idempotency_key,
                    request_hash=request_hash,
                    response_payload=cast(dict[str, object], _jsonable(asdict(output))),
                )
                uow.commit()
                return output
            if action_request.action_type == "suggest_next_direction":
                context_pack = uow.build_writing_context_pack(
                    _context_input_from_action_request(input_data, action_request)
                )
                controls = _storytelling_controls(action_request, context_pack)
                output = uow.persist_action_request_beat_candidates(
                    PersistActionRequestBeatCandidatesInput(
                        project_id=input_data.project_id,
                        actor_id=input_data.actor_id,
                        action_request_id=input_data.action_request_id,
                        context_pack_id=context_pack.context_pack_id,
                        target_source_id=action_request.source_id,
                        target_version_id=action_request.source_version_id,
                        target_scene_id=action_request.scene_id,
                        affected_range=_target_range(action_request.target),
                        base_hash=uow.source_version_hash(action_request.source_version_id)
                        if action_request.source_version_id
                        else None,
                        controls=controls,
                        beat_candidates=_beat_candidates_from_action_request(
                            input_data,
                            action_request,
                            context_pack,
                            controls,
                        ),
                    )
                )
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="action_request.run",
                    subject_ref={
                        "type": "agent_action_request",
                        "id": str(input_data.action_request_id),
                    },
                    decision={
                        "output_type": output.output_type,
                        "context_pack_id": str(output.context_pack_id),
                        "beat_candidate_ids": [
                            str(beat_id) for beat_id in output.beat_candidate_ids
                        ],
                        "resolved_skill_plan": resolved_skill_plan,
                        "idempotency_key": input_data.idempotency_key,
                    },
                )
                uow.store_idempotency_record(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    operation=operation,
                    idempotency_key=input_data.idempotency_key,
                    request_hash=request_hash,
                    response_payload=cast(dict[str, object], _jsonable(asdict(output))),
                )
                uow.commit()
                return output
            if action_request.action_type == "explain_candidate":
                candidate_id = _candidate_id_from_target(action_request.target)
                candidate = uow.load_candidate_detail(candidate_id)
                if candidate is None or candidate.project_id != input_data.project_id:
                    raise ApplicationError("not_found", "DraftCandidate was not found.")
                explanation = _candidate_explanation_from_candidate(candidate)
                status = uow.update_action_request_status(input_data.action_request_id, "succeeded")
                if status is None:
                    raise ApplicationError("not_found", "ActionRequest was not found.")
                output = RunActionRequestOutput(
                    action_request_id=input_data.action_request_id,
                    status=status,
                    output_type="candidate_explanation",
                    context_pack_id=None,
                    draft_candidate_ids=[],
                    risk_finding_ids=[],
                    beat_candidate_ids=[],
                    candidate_explanation=explanation,
                )
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="action_request.run",
                    subject_ref={
                        "type": "agent_action_request",
                        "id": str(input_data.action_request_id),
                    },
                    decision={
                        "output_type": output.output_type,
                        "candidate_id": str(candidate_id),
                        "used_memory_ref_count": len(explanation.used_memory_refs),
                        "risk_count": len(explanation.risks),
                        "resolved_skill_plan": resolved_skill_plan,
                        "idempotency_key": input_data.idempotency_key,
                    },
                )
                uow.store_idempotency_record(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    operation=operation,
                    idempotency_key=input_data.idempotency_key,
                    request_hash=request_hash,
                    response_payload=cast(dict[str, object], _jsonable(asdict(output))),
                )
                uow.commit()
                return output
            if action_request.action_type == "revise_candidate":
                if self._object_store is None or self._story_draft_provider is None:
                    raise ApplicationError(
                        "schema_validation_failed",
                        "Candidate revision requires object store and story provider.",
                    )
                candidate_id = _candidate_id_from_target(action_request.target)
                candidate = uow.load_candidate_detail(candidate_id)
                if candidate is None or candidate.project_id != input_data.project_id:
                    raise ApplicationError("not_found", "DraftCandidate was not found.")
                try:
                    original_text = self._object_store.get_text(candidate.candidate_text_ref)
                except (FileNotFoundError, ValueError) as exc:
                    raise ApplicationError(
                        "not_found",
                        "DraftCandidate text object was not found.",
                        {"candidate_text_ref": candidate.candidate_text_ref},
                    ) from exc
                context_pack = _context_pack_for_candidate_revision(
                    uow, input_data, action_request, candidate
                )
                controls = _storytelling_controls(action_request, context_pack)
                prose_contract = next(
                    control.payload
                    for control in controls
                    if control.control_type == "prose_rendering_contract"
                )
                story_request = StoryDraftRequest(
                    actor_intent=action_request.actor_intent,
                    current_text_window=_revision_text_window(
                        original_text, input_data.current_text_window
                    ),
                    context_pack=context_pack,
                    prose_rendering_contract=prose_contract,
                )
                story_result = _draft_valid_story_result(
                    uow,
                    input_data,
                    story_request,
                    self._story_draft_provider,
                )
                candidate_text_ref = self._object_store.put_text(
                    f"candidates/{input_data.action_request_id}-revision.txt",
                    story_result.text,
                )
                findings = _agent_review_findings(
                    story_result.review_cues,
                    candidate_text_ref,
                    candidate_text=story_result.text,
                    prose_contract=prose_contract,
                    structured_output=story_result.structured_output,
                )
                candidate_status = (
                    "blocked"
                    if any(finding.risk_level == "high" for finding in findings)
                    else "offered_to_author"
                )
                output = uow.persist_action_request_run(
                    PersistActionRequestRunInput(
                        project_id=input_data.project_id,
                        actor_id=input_data.actor_id,
                        action_request_id=input_data.action_request_id,
                        original_candidate_id=candidate.id,
                        mode=action_request.action_type,
                        context_pack_id=context_pack.context_pack_id,
                        candidate_text_ref=candidate_text_ref,
                        target_source_id=candidate.target_source_id,
                        target_version_id=candidate.target_version_id,
                        target_scene_id=candidate.target_scene_id,
                        affected_range=candidate.affected_range,
                        base_hash=candidate.base_hash,
                        memory_refs=candidate.memory_refs,
                        evidence_refs=candidate.evidence_refs or context_pack.evidence_refs,
                        controls=controls,
                        skill_name=self._story_draft_provider.skill_name,
                        skill_version=self._story_draft_provider.skill_version,
                        prompt_version=_story_draft_prompt_version(self._story_draft_provider),
                        input_hash=_dataclass_hash(story_request),
                        structured_output=story_result.structured_output,
                        findings=findings,
                        candidate_status=candidate_status,
                    )
                )
                uow.record_audit(
                    project_id=input_data.project_id,
                    request_id=input_data.request_id,
                    actor_id=input_data.actor_id,
                    event_type="action_request.run",
                    subject_ref={
                        "type": "agent_action_request",
                        "id": str(input_data.action_request_id),
                    },
                    decision={
                        "output_type": output.output_type,
                        "original_candidate_id": str(candidate.id),
                        "draft_candidate_ids": [
                            str(candidate_id) for candidate_id in output.draft_candidate_ids
                        ],
                        "risk_finding_ids": [
                            str(finding_id) for finding_id in output.risk_finding_ids
                        ],
                        "resolved_skill_plan": resolved_skill_plan,
                        "idempotency_key": input_data.idempotency_key,
                    },
                )
                uow.store_idempotency_record(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    operation=operation,
                    idempotency_key=input_data.idempotency_key,
                    request_hash=request_hash,
                    response_payload=cast(dict[str, object], _jsonable(asdict(output))),
                )
                uow.commit()
                return output
            if action_request.action_type not in WRITING_ACTIONS:
                raise ApplicationError(
                    "schema_validation_failed",
                    "ActionRequest does not have an implemented run output.",
                )
            if self._object_store is None or self._story_draft_provider is None:
                raise ApplicationError(
                    "schema_validation_failed",
                    "Draft ActionRequest run requires object store and story provider.",
                )

            context_pack = uow.build_writing_context_pack(
                _context_input_from_action_request(input_data, action_request)
            )
            controls = _storytelling_controls(action_request, context_pack)
            prose_contract = next(
                control.payload
                for control in controls
                if control.control_type == "prose_rendering_contract"
            )
            story_request = StoryDraftRequest(
                actor_intent=action_request.actor_intent,
                current_text_window=input_data.current_text_window,
                context_pack=context_pack,
                prose_rendering_contract=prose_contract,
            )
            story_result = _draft_valid_story_result(
                uow,
                input_data,
                story_request,
                self._story_draft_provider,
            )
            candidate_text_ref = self._object_store.put_text(
                f"candidates/{input_data.action_request_id}.txt",
                story_result.text,
            )
            findings = _agent_review_findings(
                story_result.review_cues,
                candidate_text_ref,
                candidate_text=story_result.text,
                prose_contract=prose_contract,
                structured_output=story_result.structured_output,
            )
            candidate_status = (
                "blocked"
                if any(finding.risk_level == "high" for finding in findings)
                else "offered_to_author"
            )
            output = uow.persist_action_request_run(
                PersistActionRequestRunInput(
                    project_id=input_data.project_id,
                    actor_id=input_data.actor_id,
                    action_request_id=input_data.action_request_id,
                    original_candidate_id=None,
                    mode=action_request.action_type,
                    context_pack_id=context_pack.context_pack_id,
                    candidate_text_ref=candidate_text_ref,
                    target_source_id=action_request.source_id,
                    target_version_id=action_request.source_version_id,
                    target_scene_id=action_request.scene_id,
                    affected_range=_target_range(action_request.target),
                    base_hash=uow.source_version_hash(action_request.source_version_id)
                    if action_request.source_version_id
                    else None,
                    memory_refs=[],
                    evidence_refs=context_pack.evidence_refs,
                    controls=controls,
                    skill_name=self._story_draft_provider.skill_name,
                    skill_version=self._story_draft_provider.skill_version,
                    prompt_version=_story_draft_prompt_version(self._story_draft_provider),
                    input_hash=_dataclass_hash(story_request),
                    structured_output=story_result.structured_output,
                    findings=findings,
                    candidate_status=candidate_status,
                )
            )
            uow.record_audit(
                project_id=input_data.project_id,
                request_id=input_data.request_id,
                actor_id=input_data.actor_id,
                event_type="action_request.run",
                subject_ref={
                    "type": "agent_action_request",
                    "id": str(input_data.action_request_id),
                },
                decision={
                    "context_pack_id": str(output.context_pack_id),
                    "draft_candidate_ids": [
                        str(candidate_id) for candidate_id in output.draft_candidate_ids
                    ],
                    "risk_finding_ids": [str(finding_id) for finding_id in output.risk_finding_ids],
                    "resolved_skill_plan": resolved_skill_plan,
                    "idempotency_key": input_data.idempotency_key,
                },
            )
            uow.store_idempotency_record(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                operation=operation,
                idempotency_key=input_data.idempotency_key,
                request_hash=request_hash,
                response_payload=cast(dict[str, object], _jsonable(asdict(output))),
            )
            uow.commit()
            return output


def _ensure_project(uow: SextantUnitOfWork, project_id: UUID, actor_id: UUID) -> None:
    if not uow.project_accessible(project_id, actor_id):
        raise ApplicationError("permission_denied", "Project is not accessible.")


def _ensure_project_readable(uow: SextantUnitOfWork, project_id: UUID, actor_id: UUID) -> None:
    if not uow.project_readable(project_id, actor_id):
        raise ApplicationError("permission_denied", "Project is not accessible.")


def _validate_project_member_role(role: str) -> None:
    if role not in {"owner", "editor", "viewer"}:
        raise ApplicationError("schema_validation_failed", "Project member role is invalid.")


def _validate_invitation_refs(input_data: CreateProjectInvitationInput) -> None:
    if not _has_allowed_ref_scheme(
        input_data.delivery_provider_ref,
        {"ses", "sendgrid", "postmark", "mailgun", "smtp-tls", "supabase-auth"},
    ):
        raise ApplicationError(
            "schema_validation_failed",
            "Invitation delivery provider ref must use a hosted delivery provider scheme.",
        )
    if not _has_allowed_ref_scheme(
        input_data.delivery_target_ref,
        {"ses", "sendgrid", "postmark", "mailgun", "smtp-tls", "supabase-auth"},
    ):
        raise ApplicationError(
            "schema_validation_failed",
            "Invitation delivery target ref must use a hosted delivery provider scheme.",
        )
    if input_data.token_issuer_ref and not _has_allowed_ref_scheme(
        input_data.token_issuer_ref,
        {"auth0", "okta", "clerk", "supabase"},
    ):
        raise ApplicationError(
            "schema_validation_failed",
            "Invitation token issuer ref must use a hosted session-provider scheme.",
        )


def _validate_invitation_external_proof_refs(
    input_data: RecordProjectInvitationExternalProofInput,
) -> None:
    if not _has_allowed_external_ref_scheme(
        input_data.delivery_proof_ref,
        {
            "ses",
            "sendgrid",
            "postmark",
            "mailgun",
            "smtp-tls",
            "supabase-auth",
            "https",
            "ci-artifact",
        },
    ):
        raise ApplicationError(
            "schema_validation_failed",
            "Invitation delivery proof ref must be a production external proof ref.",
        )
    if input_data.token_proof_ref and not _has_allowed_external_ref_scheme(
        input_data.token_proof_ref,
        {"auth0", "okta", "clerk", "supabase", "https", "ci-artifact"},
    ):
        raise ApplicationError(
            "schema_validation_failed",
            "Invitation token proof ref must be a production external proof ref.",
        )


def _has_allowed_ref_scheme(value: str, allowed_schemes: set[str]) -> bool:
    parsed = urlparse(value)
    return bool(
        parsed.scheme
        and parsed.netloc
        and parsed.scheme in allowed_schemes
        and _has_no_secret_bearing_ref_parts(parsed)
    )


def _has_allowed_external_ref_scheme(value: str, allowed_schemes: set[str]) -> bool:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc or parsed.scheme not in allowed_schemes:
        return False
    if not _has_no_secret_bearing_ref_parts(parsed):
        return False
    return not (parsed.scheme == "https" and _is_local_ref_host(parsed.hostname or ""))


def _has_no_secret_bearing_ref_parts(parsed: ParseResult) -> bool:
    return not (
        parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment
    )


def _is_local_ref_host(hostname: str) -> bool:
    normalized = hostname.strip().casefold()
    return (
        normalized in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
        or normalized.endswith(".local")
        or normalized.startswith("127.")
        or normalized.startswith("169.254.")
    )


def _require_project_member_writer(uow: SextantUnitOfWork, project_id: UUID, actor_id: UUID) -> str:
    role = uow.project_actor_role(project_id, actor_id)
    if role not in {"owner", "editor"}:
        raise ApplicationError(
            "permission_denied",
            "Project member writes require owner or editor access.",
        )
    return role


def _ensure_system_admin(admin_actor_ids: frozenset[UUID], actor_id: UUID) -> None:
    if actor_id not in admin_actor_ids:
        raise ApplicationError("permission_denied", "System admin access is required.")


def _read_object_text(object_store: ObjectStore, ref: str, message: str) -> str:
    try:
        return object_store.get_text(ref)
    except (FileNotFoundError, ValueError) as exc:
        raise ApplicationError("not_found", message, {"object_ref": ref}) from exc


def _apply_source_delta_text(
    *,
    previous_text: str,
    submitted_text: str,
    delta_kind: str,
    range_start: int,
    range_end: int,
) -> str:
    if range_start > len(previous_text) or range_end > len(previous_text):
        raise ApplicationError(
            "invalid_target_range",
            "SourceDelta range exceeds SourceVersion text length.",
            {
                "range_start": range_start,
                "range_end": range_end,
                "text_length": len(previous_text),
            },
        )
    if delta_kind == "insert" and range_start != range_end:
        raise ApplicationError(
            "invalid_target_range",
            "Insert SourceDelta requires a collapsed range.",
            {"range_start": range_start, "range_end": range_end},
        )
    if delta_kind == "delete":
        return previous_text[:range_start] + previous_text[range_end:]
    return previous_text[:range_start] + submitted_text + previous_text[range_end:]


def _source_version_line_diff(
    base_text: str, compare_text: str
) -> tuple[list[SourceVersionDiffHunkOutput], SourceVersionDiffSummaryOutput]:
    base_lines = base_text.splitlines()
    compare_lines = compare_text.splitlines()
    matcher = SequenceMatcher(a=base_lines, b=compare_lines, autojunk=False)
    hunks: list[SourceVersionDiffHunkOutput] = []
    insertions = 0
    deletions = 0

    for group in matcher.get_grouped_opcodes(n=3):
        if not group:
            continue
        first = group[0]
        last = group[-1]
        old_start = first[1] + 1 if last[2] > first[1] else first[1]
        new_start = first[3] + 1 if last[4] > first[3] else first[3]
        hunk_lines: list[SourceVersionDiffLineOutput] = []

        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for offset, text in enumerate(base_lines[i1:i2]):
                    hunk_lines.append(
                        SourceVersionDiffLineOutput(
                            kind="context",
                            old_line=i1 + offset + 1,
                            new_line=j1 + offset + 1,
                            text=text,
                        )
                    )
            elif tag == "delete":
                deletions += i2 - i1
                for offset, text in enumerate(base_lines[i1:i2]):
                    hunk_lines.append(
                        SourceVersionDiffLineOutput(
                            kind="delete",
                            old_line=i1 + offset + 1,
                            new_line=None,
                            text=text,
                        )
                    )
            elif tag == "insert":
                insertions += j2 - j1
                for offset, text in enumerate(compare_lines[j1:j2]):
                    hunk_lines.append(
                        SourceVersionDiffLineOutput(
                            kind="insert",
                            old_line=None,
                            new_line=j1 + offset + 1,
                            text=text,
                        )
                    )
            elif tag == "replace":
                deletions += i2 - i1
                insertions += j2 - j1
                for offset, text in enumerate(base_lines[i1:i2]):
                    hunk_lines.append(
                        SourceVersionDiffLineOutput(
                            kind="delete",
                            old_line=i1 + offset + 1,
                            new_line=None,
                            text=text,
                        )
                    )
                for offset, text in enumerate(compare_lines[j1:j2]):
                    hunk_lines.append(
                        SourceVersionDiffLineOutput(
                            kind="insert",
                            old_line=None,
                            new_line=j1 + offset + 1,
                            text=text,
                        )
                    )

        hunks.append(
            SourceVersionDiffHunkOutput(
                old_start=old_start,
                old_lines=last[2] - first[1],
                new_start=new_start,
                new_lines=last[4] - first[3],
                lines=hunk_lines,
            )
        )

    return hunks, SourceVersionDiffSummaryOutput(
        insertions=insertions,
        deletions=deletions,
        changed=insertions > 0 or deletions > 0,
    )


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _encode_source_delta_cursor(snapshot: SourceDeltaSnapshot) -> str:
    payload = {
        "v": 1,
        "created_at": snapshot.created_at.isoformat(),
        "id": str(snapshot.id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return encoded.rstrip("=")


def _decode_source_delta_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        delta_id = UUID(str(payload["id"]))
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ApplicationError(
            "schema_validation_failed",
            "SourceDelta cursor is invalid.",
        ) from exc
    return created_at, delta_id


def _next_version_label(previous_label: str) -> str:
    match = re.match(r"^(.*?)(\d+)$", previous_label)
    if match is None:
        return f"{previous_label}+1"
    prefix, number = match.groups()
    return f"{prefix}{int(number) + 1}"


def _validate_idempotency_key(idempotency_key: str) -> None:
    if not idempotency_key.strip():
        raise ApplicationError("schema_validation_failed", "Idempotency-Key is required.")


def _validate_context_budget_constraints(constraints: dict[str, object]) -> None:
    budget = constraints.get("context_budget")
    if budget is None:
        return
    if not isinstance(budget, dict):
        raise ApplicationError(
            "schema_validation_failed",
            "context_budget must be an object.",
        )
    budget_map = cast(dict[str, object], budget)
    value = budget_map.get("max_estimated_tokens")
    if value is None:
        value = budget_map.get("max_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ApplicationError(
            "schema_validation_failed",
            "context_budget.max_estimated_tokens must be a positive integer.",
        )


def _validate_story_schema_genre_pack(input_data: CreateStorySchemaGenrePackInput) -> None:
    if not input_data.pack_name.strip():
        raise ApplicationError("schema_validation_failed", "Story Schema pack_name is required.")
    if not input_data.version.strip():
        raise ApplicationError("schema_validation_failed", "Story Schema version is required.")
    for entity_definition in input_data.entity_types:
        _schema_definition_name(entity_definition)
        subtype_of = entity_definition.get("subtype_of")
        if subtype_of is None:
            continue
        subtype_name = str(subtype_of).strip()
        if subtype_name not in BASE_ENTITY_TYPES:
            raise ApplicationError(
                "schema_validation_failed",
                f"Genre entity subtype_of {subtype_name or '<empty>'} is not a Base entity type.",
            )
    genre_pack = StorySchemaPackSnapshot(
        pack_type="genre",
        pack_name=input_data.pack_name.strip(),
        version=input_data.version.strip(),
        status="active",
        entity_types=input_data.entity_types,
        event_types=input_data.event_types,
        relations=input_data.relations,
        extraction_hints=input_data.extraction_hints,
        risk_rules=input_data.risk_rules,
    )
    try:
        effective_schema = build_effective_story_schema(
            [default_base_story_schema_pack(), genre_pack]
        )
    except ValueError as exc:
        raise ApplicationError("schema_validation_failed", str(exc)) from exc
    _validate_story_schema_relation_rules(
        relations=input_data.relations,
        extraction_hints=input_data.extraction_hints,
        effective_schema=effective_schema,
    )


def _validate_story_schema_override(input_data: UpsertProjectStorySchemaOverrideInput) -> None:
    if not input_data.pack_name.strip():
        raise ApplicationError("schema_validation_failed", "Story Schema pack_name is required.")
    override = StorySchemaPackSnapshot(
        pack_type="project_override",
        pack_name=input_data.pack_name.strip(),
        version="validation",
        status="active",
        entity_types=input_data.entity_types,
        event_types=input_data.event_types,
        relations=input_data.relations,
        extraction_hints=input_data.extraction_hints,
        risk_rules=input_data.risk_rules,
    )
    try:
        effective_schema = build_effective_story_schema(
            [default_base_story_schema_pack(), override]
        )
    except ValueError as exc:
        raise ApplicationError("schema_validation_failed", str(exc)) from exc
    _validate_story_schema_relation_rules(
        relations=input_data.relations,
        extraction_hints=input_data.extraction_hints,
        effective_schema=effective_schema,
    )


def _validate_story_schema_relation_rules(
    *,
    relations: list[dict[str, object] | str],
    extraction_hints: dict[str, object],
    effective_schema: EffectiveStorySchema,
) -> None:
    allowed_ref_types = (
        set(effective_schema.entity_types) | set(NON_ENTITY_FACT_REF_TYPES) | {ANY_SCHEMA_ENTITY}
    )
    for relation_definition in relations:
        if not isinstance(relation_definition, dict):
            continue
        relation_name = _schema_definition_name(relation_definition)
        for field_name in (
            "subject_types",
            "subject_ref_types",
            "object_types",
            "object_ref_types",
        ):
            for ref_type in _schema_names_from_rule(relation_definition.get(field_name)):
                if ref_type in allowed_ref_types:
                    continue
                raise ApplicationError(
                    "schema_validation_failed",
                    (
                        f"Relation {relation_name} references unknown ref type "
                        f"{ref_type} in {field_name}."
                    ),
                )

    relation_patterns = extraction_hints.get("relation_patterns")
    if relation_patterns is not None:
        if not isinstance(relation_patterns, list):
            raise ApplicationError(
                "schema_validation_failed",
                "extraction_hints.relation_patterns must be a list.",
            )
        for pattern_candidate in relation_patterns:
            if not isinstance(pattern_candidate, dict):
                raise ApplicationError(
                    "schema_validation_failed",
                    "relation_patterns entries must be objects.",
                )
            pattern = cast(dict[str, object], pattern_candidate)
            relation = str(pattern.get("relation") or "").strip()
            if relation not in effective_schema.relations:
                raise ApplicationError(
                    "schema_validation_failed",
                    f"relation_pattern relation {relation or '<empty>'} is not allowed.",
                )
            for field_name in ("subject_type", "object_type"):
                ref_type = str(pattern.get(field_name) or "").strip()
                if ref_type not in effective_schema.entity_types:
                    raise ApplicationError(
                        "schema_validation_failed",
                        f"relation_pattern {field_name} {ref_type or '<empty>'} is not allowed.",
                    )

    mention_patterns = extraction_hints.get("mention_patterns")
    if mention_patterns is not None:
        if not isinstance(mention_patterns, list):
            raise ApplicationError(
                "schema_validation_failed",
                "extraction_hints.mention_patterns must be a list.",
            )
        for pattern_candidate in mention_patterns:
            if not isinstance(pattern_candidate, dict):
                raise ApplicationError(
                    "schema_validation_failed",
                    "mention_patterns entries must be objects.",
                )
            pattern = cast(dict[str, object], pattern_candidate)
            entity_type = str(pattern.get("entity_type") or "").strip()
            if entity_type not in effective_schema.entity_types:
                raise ApplicationError(
                    "schema_validation_failed",
                    f"mention_pattern entity_type {entity_type or '<empty>'} is not allowed.",
                )
            template = str(pattern.get("template") or "")
            if "{mention}" not in template:
                raise ApplicationError(
                    "schema_validation_failed",
                    "mention_pattern template must include {mention}.",
                )
            confidence = pattern.get("confidence")
            if confidence is not None and (
                not isinstance(confidence, int | float) or not 0 < float(confidence) <= 1
            ):
                raise ApplicationError(
                    "schema_validation_failed",
                    "mention_pattern confidence must be between 0 and 1.",
                )

    agency_profile_fields = extraction_hints.get("agency_profile_fields")
    if agency_profile_fields is not None:
        if not isinstance(agency_profile_fields, list):
            raise ApplicationError(
                "schema_validation_failed",
                "extraction_hints.agency_profile_fields must be a list.",
            )
        for field_candidate in agency_profile_fields:
            if not isinstance(field_candidate, dict):
                raise ApplicationError(
                    "schema_validation_failed",
                    "agency_profile_fields entries must be objects.",
                )
            field = cast(dict[str, object], field_candidate)
            predicate = str(field.get("predicate") or "").strip()
            if predicate not in AGENCY_PROFILE_RELATIONS:
                raise ApplicationError(
                    "schema_validation_failed",
                    f"agency_profile_field predicate {predicate or '<empty>'} is not allowed.",
                )
            labels = field.get("labels")
            if not isinstance(labels, list) or not labels:
                raise ApplicationError(
                    "schema_validation_failed",
                    "agency_profile_field labels must be a non-empty list.",
                )
            for label in labels:
                if not isinstance(label, str) or not label.strip():
                    raise ApplicationError(
                        "schema_validation_failed",
                        "agency_profile_field labels must be non-empty strings.",
                    )

    event_patterns = extraction_hints.get("event_patterns")
    if event_patterns is None:
        return
    if not isinstance(event_patterns, list):
        raise ApplicationError(
            "schema_validation_failed",
            "extraction_hints.event_patterns must be a list.",
        )
    for pattern_candidate in event_patterns:
        if not isinstance(pattern_candidate, dict):
            raise ApplicationError(
                "schema_validation_failed",
                "event_patterns entries must be objects.",
            )
        pattern = cast(dict[str, object], pattern_candidate)
        event_type = str(pattern.get("event_type") or "").strip()
        if event_type not in effective_schema.event_types:
            raise ApplicationError(
                "schema_validation_failed",
                f"event_pattern event_type {event_type or '<empty>'} is not allowed.",
            )
        template = str(pattern.get("template") or "")
        placeholders = set(re.findall(r"{([a-z_]+)}", template))
        unknown_placeholders = placeholders - {"subject", "object", "location"}
        if unknown_placeholders:
            unknown = sorted(unknown_placeholders)[0]
            raise ApplicationError(
                "schema_validation_failed",
                f"event_pattern template placeholder {unknown} is not allowed.",
            )
        if "subject" not in placeholders:
            raise ApplicationError(
                "schema_validation_failed",
                "event_pattern template must include {subject}.",
            )
        subject_type = str(pattern.get("subject_type") or "").strip()
        if subject_type not in effective_schema.entity_types:
            raise ApplicationError(
                "schema_validation_failed",
                f"event_pattern subject_type {subject_type or '<empty>'} is not allowed.",
            )
        for field_name, placeholder in (("object_type", "object"), ("location_type", "location")):
            ref_type = str(pattern.get(field_name) or "").strip()
            if not ref_type and placeholder not in placeholders:
                continue
            if ref_type not in effective_schema.entity_types:
                raise ApplicationError(
                    "schema_validation_failed",
                    f"event_pattern {field_name} {ref_type or '<empty>'} is not allowed.",
                )
        confidence = pattern.get("confidence")
        if confidence is not None and (
            not isinstance(confidence, int | float) or not 0 < float(confidence) <= 1
        ):
            raise ApplicationError(
                "schema_validation_failed",
                "event_pattern confidence must be between 0 and 1.",
            )


def _schema_definition_name(definition: dict[str, object]) -> str:
    name = str(definition.get("name") or "").strip()
    if not name:
        raise ApplicationError(
            "schema_validation_failed",
            "Story Schema definitions require a non-empty name.",
        )
    return name


def _schema_names_from_rule(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    names: set[str] = set()
    for item in value:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            item_record = cast(dict[str, object], item)
            name = str(item_record.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.add(name)
    return names


def _project_story_schema_from_payload(
    payload: dict[str, object],
) -> ProjectStorySchemaOutput:
    genre_schema_pack_payload = payload.get("genre_schema_pack")
    genre_schema_pack = (
        _story_schema_pack_from_payload(cast(dict[str, object], genre_schema_pack_payload))
        if isinstance(genre_schema_pack_payload, dict)
        else None
    )
    project_override_pack_payload = payload.get("project_override_pack")
    project_override_pack = (
        _story_schema_pack_from_payload(cast(dict[str, object], project_override_pack_payload))
        if isinstance(project_override_pack_payload, dict)
        else None
    )
    return ProjectStorySchemaOutput(
        project_id=UUID(str(payload["project_id"])),
        binding_id=_payload_uuid_or_none(payload.get("binding_id")),
        base_schema_pack_id=_payload_uuid_or_none(payload.get("base_schema_pack_id")),
        genre_schema_pack_id=_payload_uuid_or_none(payload.get("genre_schema_pack_id")),
        genre_schema_pack=genre_schema_pack,
        project_override_pack_id=_payload_uuid_or_none(payload.get("project_override_pack_id")),
        project_override_pack=project_override_pack,
        effective_schema=cast(dict[str, object], payload["effective_schema"]),
    )


def _story_schema_pack_from_payload(payload: dict[str, object]) -> StorySchemaPackOutput:
    return StorySchemaPackOutput(
        id=UUID(str(payload["id"])),
        project_id=_payload_uuid_or_none(payload.get("project_id")),
        pack_type=str(payload["pack_type"]),
        pack_name=str(payload["pack_name"]),
        version=str(payload["version"]),
        status=str(payload["status"]),
        entity_types=cast(list[dict[str, object]], payload["entity_types"]),
        event_types=cast(list[dict[str, object] | str], payload["event_types"]),
        relations=cast(list[dict[str, object] | str], payload["relations"]),
        extraction_hints=cast(dict[str, object], payload["extraction_hints"]),
        risk_rules=cast(dict[str, object], payload["risk_rules"]),
    )


def _payload_uuid_or_none(value: object) -> UUID | None:
    return UUID(str(value)) if value else None


def _project_member_operation_payload(
    output: ProjectMemberOperationOutput,
) -> dict[str, object]:
    return {
        "member": cast(dict[str, object], _jsonable(asdict(output.member))),
        "status": output.status,
    }


def _project_member_from_payload(payload: object) -> ProjectMemberSnapshot:
    member = cast(dict[str, object], payload)
    return ProjectMemberSnapshot(
        id=UUID(str(member["id"])),
        project_id=UUID(str(member["project_id"])),
        actor_id=UUID(str(member["actor_id"])),
        role=str(member["role"]),
        status=str(member["status"]),
        created_at=datetime.fromisoformat(str(member["created_at"])),
    )


def _project_invitation_payload(invitation: ProjectInvitationSnapshot) -> dict[str, object]:
    return cast(dict[str, object], _jsonable(asdict(invitation)))


def _project_invitation_from_payload(payload: object) -> ProjectInvitationSnapshot:
    invitation = cast(dict[str, object], payload)
    return ProjectInvitationSnapshot(
        id=UUID(str(invitation["id"])),
        project_id=UUID(str(invitation["project_id"])),
        member_actor_id=UUID(str(invitation["member_actor_id"])),
        role=str(invitation["role"]),
        delivery_provider_ref=str(invitation["delivery_provider_ref"]),
        delivery_target_ref=str(invitation["delivery_target_ref"]),
        token_issuer_ref=(
            str(invitation["token_issuer_ref"]) if invitation.get("token_issuer_ref") else None
        ),
        delivery_proof_ref=(
            str(invitation["delivery_proof_ref"]) if invitation.get("delivery_proof_ref") else None
        ),
        token_proof_ref=(
            str(invitation["token_proof_ref"]) if invitation.get("token_proof_ref") else None
        ),
        status=str(invitation["status"]),
        delivery_status=str(invitation["delivery_status"]),
        token_status=str(invitation["token_status"]),
        delivered_at=(
            datetime.fromisoformat(str(invitation["delivered_at"]))
            if invitation.get("delivered_at")
            else None
        ),
        token_issued_at=(
            datetime.fromisoformat(str(invitation["token_issued_at"]))
            if invitation.get("token_issued_at")
            else None
        ),
        created_at=datetime.fromisoformat(str(invitation["created_at"])),
    )


def _input_hash(
    input_data: (
        SubmitActionRequestInput
        | CreateSourceInput
        | CreateSourceVersionInput
        | RestoreSourceVersionInput
        | CreateSourceDeltaInput
        | ArchiveSourceInput
        | JobOperationInput
        | CandidateOperationInput
        | AcceptCandidateInput
        | ReviewItemOperationInput
        | MemoryPageThreadOperationInput
        | MemoryWritebackDecisionInput
        | MemoryAnswerInput
        | BuildWritingContextPackInput
        | RunActionRequestInput
        | CreateStorySchemaGenrePackInput
        | DeprecateStorySchemaGenrePackInput
        | SelectProjectStorySchemaGenreInput
        | UpsertProjectStorySchemaOverrideInput
        | UpsertProjectMemberInput
        | RevokeProjectMemberInput
        | CreateProjectInvitationInput
        | RecordProjectInvitationExternalProofInput
    ),
) -> str:
    payload = _jsonable(asdict(input_data))
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _jsonable(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_jsonable(nested) for nested in value]
    return value


def _load_idempotency_record(
    uow: SextantUnitOfWork,
    input_data: (
        SubmitActionRequestInput
        | CreateSourceInput
        | CreateSourceVersionInput
        | RestoreSourceVersionInput
        | CreateSourceDeltaInput
        | ArchiveSourceInput
        | JobOperationInput
        | CandidateOperationInput
        | AcceptCandidateInput
        | ReviewItemOperationInput
        | MemoryPageThreadOperationInput
        | MemoryWritebackDecisionInput
        | MemoryAnswerInput
        | BuildWritingContextPackInput
        | RunActionRequestInput
        | CreateStorySchemaGenrePackInput
        | DeprecateStorySchemaGenrePackInput
        | SelectProjectStorySchemaGenreInput
        | UpsertProjectStorySchemaOverrideInput
        | UpsertProjectMemberInput
        | RevokeProjectMemberInput
        | CreateProjectInvitationInput
        | RecordProjectInvitationExternalProofInput
    ),
    operation: str,
    request_hash: str,
) -> IdempotencySnapshot | None:
    record = uow.load_idempotency_record(
        input_data.project_id,
        input_data.actor_id,
        operation,
        input_data.idempotency_key,
    )
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise ApplicationError(
            "idempotency_conflict",
            "Idempotency-Key was already used with a different request payload.",
        )
    return record


def _uuid_from_payload(record: IdempotencySnapshot, key: str) -> UUID:
    return UUID(str(record.response_payload[key]))


def _source_delta_summary(
    snapshot: SourceDeltaSnapshot, submitted_text: str
) -> SourceDeltaSummaryOutput:
    return SourceDeltaSummaryOutput(
        id=snapshot.id,
        source_id=snapshot.source_id,
        previous_version_id=snapshot.previous_version_id,
        new_version_id=snapshot.new_version_id,
        accepted_fragment_id=snapshot.accepted_fragment_id,
        delta_kind=snapshot.delta_kind,
        status=snapshot.status,
        range_start=snapshot.range_start,
        range_end=snapshot.range_end,
        base_hash=snapshot.base_hash,
        source_type=snapshot.source_type,
        source_scope=snapshot.source_scope,
        provenance=snapshot.provenance,
        submitted_text_ref=snapshot.submitted_text_ref,
        submitted_text_preview=submitted_text[:500],
        job=snapshot.job,
    )


def _source_delta_detail(
    snapshot: SourceDeltaSnapshot, submitted_text: str
) -> SourceDeltaDetailOutput:
    return SourceDeltaDetailOutput(
        id=snapshot.id,
        source_id=snapshot.source_id,
        previous_version_id=snapshot.previous_version_id,
        new_version_id=snapshot.new_version_id,
        accepted_fragment_id=snapshot.accepted_fragment_id,
        delta_kind=snapshot.delta_kind,
        status=snapshot.status,
        range_start=snapshot.range_start,
        range_end=snapshot.range_end,
        base_hash=snapshot.base_hash,
        source_type=snapshot.source_type,
        source_scope=snapshot.source_scope,
        provenance=snapshot.provenance,
        submitted_text_ref=snapshot.submitted_text_ref,
        submitted_text=submitted_text,
        job=snapshot.job,
    )


def _job_detail_from_payload(payload: dict[str, object]) -> JobDetailOutput:
    return JobDetailOutput(
        id=UUID(str(payload["id"])),
        job_type=str(payload["job_type"]),
        status=str(payload["status"]),
        attempt_count=int(str(payload["attempt_count"])),
        run_after=_optional_datetime(payload.get("run_after")),
        locked_by=cast(str | None, payload.get("locked_by")),
        locked_at=_optional_datetime(payload.get("locked_at")),
        last_error=cast(str | None, payload.get("last_error")),
        payload=cast(dict[str, object], payload["payload"]),
    )


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _validate_job_operation(job: JobDetailOutput, operation: str) -> None:
    if operation == "cancel" and job.status not in {
        "queued",
        "running",
        "failed_retryable",
        "cancelled",
    }:
        raise ApplicationError(
            "invalid_state_transition",
            "Only queued, running, or retryable jobs can be cancelled.",
            {"job_id": str(job.id), "status": job.status},
        )
    if operation == "retry" and job.status not in {"failed_retryable", "queued"}:
        raise ApplicationError(
            "invalid_state_transition",
            "Only retryable jobs can be requeued.",
            {"job_id": str(job.id), "status": job.status},
        )


def _memory_writeback_decision_from_payload(
    payload: dict[str, object],
) -> MemoryWritebackDecisionOutput:
    return MemoryWritebackDecisionOutput(
        decision_id=UUID(str(payload["decision_id"])),
        source_delta_id=UUID(str(payload["source_delta_id"])),
        item_ref=cast(dict[str, object], payload["item_ref"]),
        decision=str(payload["decision"]),
        status=str(payload["status"]),
        side_effects=cast(dict[str, object], payload["side_effects"]),
    )


def _memory_page_detail_from_payload(payload: dict[str, object]) -> MemoryPageDetailOutput:
    return MemoryPageDetailOutput(
        id=UUID(str(payload["id"])),
        page_type=str(payload["page_type"]),
        target_ref=cast(dict[str, object], payload["target_ref"]),
        title=str(payload["title"]),
        current_canon=cast(dict[str, object], payload["current_canon"]),
        appearance_log=cast(list[dict[str, object]], payload["appearance_log"]),
        event_log=cast(list[dict[str, object]], payload["event_log"]),
        relationships=cast(list[dict[str, object]], payload["relationships"]),
        knowledge_state=cast(list[dict[str, object]], payload["knowledge_state"]),
        open_threads=cast(list[dict[str, object]], payload["open_threads"]),
        contradictions=cast(list[dict[str, object]], payload["contradictions"]),
        source_refs=cast(list[dict[str, object]], payload["source_refs"]),
        canon_status=str(payload["canon_status"]),
        memory_depth=str(payload["memory_depth"]),
    )


def _memory_page_thread_operation_from_payload(
    payload: dict[str, object],
) -> MemoryPageThreadOperationOutput:
    return MemoryPageThreadOperationOutput(
        memory_page_id=UUID(str(payload["memory_page_id"])),
        thread_id=str(payload["thread_id"]),
        status=str(payload["status"]),
        update_type=str(payload["update_type"]),
        memory_page=_memory_page_detail_from_payload(
            cast(dict[str, object], payload["memory_page"])
        ),
        side_effects=cast(dict[str, object], payload["side_effects"]),
    )


def _memory_page_detail_contains_thread(
    detail: MemoryPageDetailOutput,
    thread_id: str,
) -> bool:
    target = thread_id.strip()
    return any(str(thread.get("id") or "").strip() == target for thread in detail.open_threads)


def _valid_item_ref(item_ref: dict[str, object]) -> bool:
    item_type = item_ref.get("type")
    item_id = item_ref.get("id")
    return isinstance(item_type, str) and bool(item_type.strip()) and item_id is not None


def _preview_contains_item(
    preview: MemoryWritebackPreviewOutput, item_ref: dict[str, object]
) -> bool:
    item_type = str(item_ref["type"])
    item_id = str(item_ref["id"])
    ids_by_type = {
        "source_span": {str(item.get("id")) for item in preview.source_spans},
        "evidence_log_entry": {str(item.get("id")) for item in preview.evidence_log_entries},
        "fact_assertion": {str(item.get("fact_id")) for item in preview.fact_assertions},
        "review_item": {str(item.id) for item in preview.review_items},
        "memory_page": {str(item.get("id")) for item in preview.memory_pages},
        "graph_edge": {str(item.get("id")) for item in preview.graph_edges},
    }
    return item_id in ids_by_type.get(item_type, set())


def _preview_policy_blocking_fact_promotion(
    preview: MemoryWritebackPreviewOutput,
    input_data: MemoryWritebackDecisionInput,
) -> ReviewItemDetailOutput | None:
    if input_data.decision != "accept" or input_data.item_ref.get("type") != "fact_assertion":
        return None
    fact_id = str(input_data.item_ref["id"])
    for review_item in preview.review_items:
        if review_item.status != "open" or review_item.severity != "high":
            continue
        affected_refs = review_item.affected_refs
        if str(affected_refs.get("fact_id")) == fact_id:
            return review_item
        fact_ids = affected_refs.get("fact_ids", [])
        if isinstance(fact_ids, list) and fact_id in {str(item) for item in fact_ids}:
            return review_item
    return None


def _memory_answer_from_payload(payload: dict[str, object]) -> MemoryAnswerOutput:
    raw_confidence = payload.get("confidence", 0.0)
    confidence = float(raw_confidence) if isinstance(raw_confidence, int | float | str) else 0.0
    return MemoryAnswerOutput(
        question=str(payload["question"]),
        answer=str(payload["answer"]),
        answer_type=str(payload["answer_type"]),
        confidence=confidence,
        source_span_refs=cast(list[dict[str, object]], payload["source_span_refs"]),
        affected_entities=cast(list[dict[str, object]], payload.get("affected_entities", [])),
        caveats=cast(list[str], payload.get("caveats", [])),
        unknowns=cast(list[str], payload["unknowns"]),
        related_review_items=[
            UUID(str(item)) for item in cast(list[object], payload["related_review_items"])
        ],
        safe_to_use_in_current_pov=bool(payload["safe_to_use_in_current_pov"]),
    )


def _context_pack_from_payload(payload: dict[str, object]) -> WritingContextPackOutput:
    return WritingContextPackOutput(
        context_pack_id=UUID(str(payload["context_pack_id"])),
        schema_version=str(payload["schema_version"]),
        current_position=cast(dict[str, object], payload["current_position"]),
        canonical_context=cast(dict[str, object], payload["canonical_context"]),
        pov_constraint=cast(dict[str, object], payload["pov_constraint"]),
        active_characters=cast(list[dict[str, object]], payload["active_characters"]),
        character_agency_state=cast(dict[str, object], payload["character_agency_state"]),
        recent_events=cast(list[dict[str, object]], payload["recent_events"]),
        character_knowledge=cast(list[dict[str, object]], payload["character_knowledge"]),
        object_location_state=cast(list[dict[str, object]], payload["object_location_state"]),
        open_threads=cast(list[dict[str, object]], payload["open_threads"]),
        risk_context=cast(dict[str, object], payload["risk_context"]),
        style_memory=cast(dict[str, object], payload["style_memory"]),
        evidence_refs=cast(list[dict[str, object]], payload["evidence_refs"]),
    )


def _action_request_run_from_payload(payload: dict[str, object]) -> RunActionRequestOutput:
    context_pack_value = payload.get("context_pack_id")
    memory_answer_payload = payload.get("memory_answer")
    risk_findings_payload = payload.get("risk_findings")
    beat_candidates_payload = payload.get("beat_candidates")
    candidate_explanation_payload = payload.get("candidate_explanation")
    return RunActionRequestOutput(
        action_request_id=UUID(str(payload["action_request_id"])),
        status=str(payload["status"]),
        output_type=str(payload.get("output_type", "draft_candidates")),
        context_pack_id=UUID(str(context_pack_value)) if context_pack_value is not None else None,
        draft_candidate_ids=[
            UUID(str(item)) for item in cast(list[object], payload["draft_candidate_ids"])
        ],
        risk_finding_ids=[
            UUID(str(item)) for item in cast(list[object], payload["risk_finding_ids"])
        ],
        beat_candidate_ids=[
            UUID(str(item)) for item in cast(list[object], payload.get("beat_candidate_ids", []))
        ],
        memory_answer=_memory_answer_from_payload(cast(dict[str, object], memory_answer_payload))
        if memory_answer_payload is not None
        else None,
        risk_findings=[
            _agent_review_finding_from_payload(cast(dict[str, object], item))
            for item in cast(list[object], risk_findings_payload)
        ]
        if risk_findings_payload is not None
        else None,
        beat_candidates=[
            _beat_candidate_from_payload(cast(dict[str, object], item))
            for item in cast(list[object], beat_candidates_payload)
        ]
        if beat_candidates_payload is not None
        else None,
        candidate_explanation=_candidate_explanation_from_payload(
            cast(dict[str, object], candidate_explanation_payload)
        )
        if candidate_explanation_payload is not None
        else None,
    )


def _candidate_explanation_from_payload(payload: dict[str, object]) -> CandidateExplanationOutput:
    risks_payload = payload.get("risks", [])
    return CandidateExplanationOutput(
        candidate_id=UUID(str(payload["candidate_id"])),
        why_this=str(payload["why_this"]),
        used_memory_refs=cast(list[dict[str, object]], payload["used_memory_refs"]),
        respected_constraints=cast(list[str], payload["respected_constraints"]),
        avoided_claims=cast(list[str], payload["avoided_claims"]),
        risks=[
            _agent_review_finding_from_payload(cast(dict[str, object], item))
            for item in cast(list[object], risks_payload)
        ],
    )


def _beat_candidate_from_payload(payload: dict[str, object]) -> BeatCandidateSnapshot:
    findings_payload = payload.get("agent_review_findings", [])
    return BeatCandidateSnapshot(
        id=UUID(str(payload["id"])),
        summary=str(payload["summary"]),
        driver_character=str(payload["driver_character"]),
        agency_rationale=str(payload["agency_rationale"]),
        storytelling_rationale=str(payload["storytelling_rationale"]),
        cast_decision=cast(dict[str, object], payload["cast_decision"]),
        tension=str(payload["tension"]),
        memory_refs=cast(list[dict[str, object]], payload["memory_refs"]),
        evidence_refs=cast(list[dict[str, object]], payload["evidence_refs"]),
        agent_review_findings=[
            _agent_review_finding_from_payload(cast(dict[str, object], item))
            for item in cast(list[object], findings_payload)
        ],
    )


def _agent_review_finding_from_payload(payload: dict[str, object]) -> AgentReviewFindingSnapshot:
    return AgentReviewFindingSnapshot(
        id=UUID(str(payload["id"])),
        risk_level=str(payload["risk_level"]),
        risk_type=str(payload["risk_type"]),
        summary=str(payload["summary"]),
        memory_refs=cast(dict[str, object], payload["memory_refs"]),
        storytelling_refs=cast(dict[str, object], payload["storytelling_refs"]),
        suggested_revision=(
            str(payload["suggested_revision"])
            if payload.get("suggested_revision") is not None
            else None
        ),
        can_offer_to_author=bool(payload["can_offer_to_author"]),
        maps_to_review_type_if_accepted=(
            str(payload["maps_to_review_type_if_accepted"])
            if payload.get("maps_to_review_type_if_accepted") is not None
            else None
        ),
        draft_local_only=bool(payload["draft_local_only"]),
    )


def _memory_answer_input_from_action_request(
    input_data: RunActionRequestInput, action_request: ActionRequestSnapshot
) -> MemoryAnswerInput:
    subject_ref = action_request.constraints.get("subject_ref")
    if subject_ref is not None and not isinstance(subject_ref, dict):
        raise ApplicationError(
            "schema_validation_failed",
            "ask_memory subject_ref must be an object.",
        )
    predicate = action_request.constraints.get("predicate")
    if predicate is not None and not isinstance(predicate, str):
        raise ApplicationError("schema_validation_failed", "ask_memory predicate must be a string.")
    return MemoryAnswerInput(
        project_id=input_data.project_id,
        actor_id=input_data.actor_id,
        request_id=input_data.request_id,
        idempotency_key=f"{input_data.idempotency_key}:memory-answer",
        question=action_request.actor_intent,
        subject_ref=cast(dict[str, object] | None, subject_ref),
        predicate=predicate,
        current_scene_id=action_request.scene_id,
        current_pov_character_id=action_request.pov_character_id,
    )


def _beat_candidates_from_action_request(
    input_data: RunActionRequestInput,
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
    controls: list[StorytellingControlDraft],
) -> list[BeatCandidateDraft]:
    current_window = input_data.current_text_window.strip()
    driver_character = _driver_character_from_context(context_pack)
    control_types = [control.control_type for control in controls]
    evidence_refs = context_pack.evidence_refs[:5]
    location_hint = "当前位置" if not current_window else current_window[:40]
    summary = f"{driver_character}在{location_hint}前停顿，选择先确认眼前阻力而不是揭开秘密。"
    return [
        BeatCandidateDraft(
            summary=summary,
            driver_character=driver_character,
            agency_rationale=(
                f"{driver_character}的下一步保持在当前可观察压力内，"
                "避免越过 POV 或把未确认信息当成事实。"
            ),
            storytelling_rationale=(
                "该方向只推进一个小冲突：先制造选择压力，再让作者决定是否进入正文。"
            ),
            cast_decision={
                "policy": "reuse_current_cast",
                "new_character": False,
                "control_types": control_types,
            },
            tension="信息被压住，角色必须在不确认秘密的情况下采取行动。",
            memory_refs=evidence_refs,
            evidence_refs=evidence_refs,
        )
    ]


def _driver_character_from_context(context_pack: WritingContextPackOutput) -> str:
    active_characters = context_pack.active_characters
    for character in active_characters:
        name = character.get("name") or character.get("id")
        if isinstance(name, str) and name.strip():
            return name.strip()
    pov_character = context_pack.pov_constraint.get("pov_character")
    if isinstance(pov_character, dict):
        pov_character_ref = cast(dict[str, object], pov_character)
        name = pov_character_ref.get("name") or pov_character_ref.get("id")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "当前 POV 角色"


def _candidate_explanation_from_candidate(
    candidate: CandidateDetailSnapshot,
) -> CandidateExplanationOutput:
    avoided_claims = [
        finding.summary
        for finding in candidate.agent_review_findings
        if finding.risk_type in {"canon_risk", "pov_risk", "control_risk"}
    ]
    if not avoided_claims:
        avoided_claims = ["候选解释不把未确认内容当成 canon 证据。"]

    respected_constraints = ["候选仍需作者采纳，不能直接进入正文或 Memory。"]
    if candidate.context_pack_id is not None:
        respected_constraints.append("候选保留了 WritingContextPack 依据。")
    if candidate.affected_range is not None:
        respected_constraints.append(
            "候选限定在目标范围 "
            f"{candidate.affected_range['start']}..{candidate.affected_range['end']}。"
        )
    if candidate.status == "blocked":
        respected_constraints.append("高风险候选保持拦截状态，解释不解除风险。")

    used_memory_refs = candidate.memory_refs or candidate.evidence_refs
    return CandidateExplanationOutput(
        candidate_id=candidate.id,
        why_this=(
            "该候选基于已持久化的候选记录、证据引用和草稿层风险检查生成解释；"
            "解释只说明依据，不把候选内容升级为事实。"
        ),
        used_memory_refs=used_memory_refs,
        respected_constraints=respected_constraints,
        avoided_claims=avoided_claims,
        risks=candidate.agent_review_findings,
    )


def _risk_findings_from_action_request(
    input_data: RunActionRequestInput,
    action_request: ActionRequestSnapshot,
    object_store: ObjectStore,
) -> list[AgentReviewFindingDraft]:
    if not input_data.current_text_window.strip():
        raise ApplicationError(
            "schema_validation_failed",
            "check_risk requires current_text_window.",
        )
    if not contains_canon_risk_language(input_data.current_text_window):
        return []
    affected_text_ref = object_store.put_text(
        f"agent-risk/{input_data.action_request_id}.txt",
        input_data.current_text_window,
    )
    return [
        AgentReviewFindingDraft(
            risk_level="high",
            risk_type="canon_risk",
            summary="Selected text presents risk-context material as if it were canon.",
            affected_text_ref=affected_text_ref,
            memory_refs={"action_request_target": action_request.target or {}},
            storytelling_refs={
                "source": "check_risk_action",
                "review_policy_version": "agent-review-policy.v1",
            },
            suggested_revision="Keep the risky knowledge framed as uncertainty or omit it.",
            can_offer_to_author=False,
            maps_to_review_type_if_accepted="canon_conflict",
        )
    ]


def _context_input_from_action_request(
    input_data: RunActionRequestInput, action_request: ActionRequestSnapshot
) -> BuildWritingContextPackInput:
    return BuildWritingContextPackInput(
        project_id=input_data.project_id,
        actor_id=input_data.actor_id,
        request_id=input_data.request_id,
        idempotency_key=f"{input_data.idempotency_key}:context",
        action_request_id=action_request.id,
        current_source_id=action_request.source_id,
        current_version_id=action_request.source_version_id,
        current_scene_id=action_request.scene_id,
        current_pov_character_id=action_request.pov_character_id,
        mode=action_request.action_type,
        current_text_window=input_data.current_text_window,
        constraints=action_request.constraints,
    )


def _context_pack_for_candidate_revision(
    uow: SextantUnitOfWork,
    input_data: RunActionRequestInput,
    action_request: ActionRequestSnapshot,
    candidate: CandidateDetailSnapshot,
) -> WritingContextPackOutput:
    if candidate.context_pack_id is not None:
        existing = uow.get_writing_context_pack(
            ContextPackDetailInput(
                project_id=input_data.project_id,
                actor_id=input_data.actor_id,
                context_pack_id=candidate.context_pack_id,
            )
        )
        if existing is not None:
            return existing

    return uow.build_writing_context_pack(
        BuildWritingContextPackInput(
            project_id=input_data.project_id,
            actor_id=input_data.actor_id,
            request_id=input_data.request_id,
            idempotency_key=f"{input_data.idempotency_key}:context",
            action_request_id=action_request.id,
            current_source_id=candidate.target_source_id or action_request.source_id,
            current_version_id=candidate.target_version_id or action_request.source_version_id,
            current_scene_id=candidate.target_scene_id or action_request.scene_id,
            current_pov_character_id=action_request.pov_character_id,
            mode=action_request.action_type,
            current_text_window=input_data.current_text_window,
            constraints=action_request.constraints,
        )
    )


def _revision_text_window(original_text: str, current_text_window: str) -> str:
    revision_note = current_text_window.strip()
    if not revision_note:
        return original_text
    return f"原候选：{original_text}\n修订要求：{revision_note}"


def _storytelling_controls(
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
) -> list[StorytellingControlDraft]:
    current_text_window = _storytelling_current_text_window(context_pack)
    control_suffix = _storytelling_control_suffix(action_request, current_text_window)
    contract_id = f"prose-contract-{control_suffix}"
    passage_mode, mode_rationale = _storytelling_passage_mode(
        action_request,
        current_text_window,
    )
    current_pressure = _storytelling_current_pressure(
        action_request,
        context_pack,
        current_text_window,
    )
    role_function = _storytelling_role_function(
        action_request,
        context_pack,
        current_text_window,
        current_pressure,
    )
    role_slot_id = f"{role_function}-{control_suffix}"
    required_traits = _storytelling_required_traits(role_function)
    role_slot_payload: dict[str, object] = {
        "role_slot_id": role_slot_id,
        "function": role_function,
        "scene_need": current_pressure,
        "required_traits": required_traits,
        "required_knowledge": "observable_current_scene_only",
        "risk_level": _storytelling_role_risk(action_request, context_pack),
        "can_use_existing_character": bool(context_pack.active_characters),
    }
    allow_local_new_character = (
        action_request.constraints.get("new_character_policy") == "allow_local"
    )
    new_character_seed_id = (
        f"{role_function}-seed-{control_suffix}" if allow_local_new_character else None
    )
    active_character = context_pack.active_characters[0] if context_pack.active_characters else None
    casting_decision_payload: dict[str, object]
    if allow_local_new_character:
        casting_decision_payload = {
            "decision_id": f"{role_function}-casting-{control_suffix}",
            "role_slot_id": role_slot_id,
            "decision": "create_new",
            "target_entity_ref": None,
            "new_character_seed_id": new_character_seed_id,
            "reason": (
                "The request permits a scene-local draft seed for this role slot; "
                "promotion still requires accepted text and memory review."
            ),
        }
    elif active_character is not None:
        casting_decision_payload = {
            "decision_id": f"{role_function}-casting-{control_suffix}",
            "role_slot_id": role_slot_id,
            "decision": "reuse_existing",
            "target_entity_ref": active_character,
            "new_character_seed_id": None,
            "reason": (
                "An active character is already present in the current context pack "
                "and can carry the needed story function."
            ),
        }
    else:
        casting_decision_payload = {
            "decision_id": f"{role_function}-casting-{control_suffix}",
            "role_slot_id": role_slot_id,
            "decision": "avoid_character",
            "target_entity_ref": None,
            "new_character_seed_id": None,
            "reason": (
                "No active character is available and the request does not permit "
                "a scene-local seed."
            ),
        }
    scene_sequel_payload = _storytelling_scene_sequel_payload(
        action_request,
        passage_mode,
        mode_rationale,
        current_pressure,
    )
    dramatic_behavior_payload = _storytelling_dramatic_behavior_payload(
        action_request,
        context_pack,
        passage_mode,
    )
    controls = [
        StorytellingControlDraft(
            control_type="role_slot",
            schema_version="role-slot.v1",
            payload=role_slot_payload,
        ),
        StorytellingControlDraft(
            control_type="character_casting_decision",
            schema_version="character-casting-decision.v1",
            payload=casting_decision_payload,
        ),
        StorytellingControlDraft(
            control_type="scene_sequel_mode",
            schema_version="scene-sequel-mode.v1",
            payload=scene_sequel_payload,
        ),
        StorytellingControlDraft(
            control_type="dramatic_behavior_plan",
            schema_version="dramatic-behavior-plan.v1",
            payload=dramatic_behavior_payload,
        ),
    ]
    new_character_seeds: list[dict[str, object]] = []
    if allow_local_new_character:
        seed_payload = _storytelling_new_character_seed_payload(
            seed_id=str(new_character_seed_id),
            role_function=role_function,
            current_pressure=current_pressure,
        )
        new_character_seeds.append(seed_payload)
        controls.append(
            StorytellingControlDraft(
                control_type="new_character_seed",
                schema_version="new-character-seed.v1",
                payload=seed_payload,
            )
        )
    hard_no = [
        "no non-POV inner mind",
        "no proposed/disputed fact as canon",
        "no forbidden knowledge leak",
        "no target range overwrite",
        "no automatic ReviewItem resolution",
    ] + _constraint_strings(action_request.constraints.get("hard_no"))
    show_not_tell_targets = _constraint_strings(
        action_request.constraints.get("show_not_tell_targets")
    )
    requested_pov_character = action_request.constraints.get("pov_character")
    pov_character = (
        requested_pov_character
        if isinstance(requested_pov_character, str) and requested_pov_character.strip()
        else str(action_request.pov_character_id)
        if action_request.pov_character_id
        else None
    )
    requested_inner_state_budget = action_request.constraints.get("inner_state_budget")
    inner_state_budget: dict[str, object] = (
        cast(dict[str, object], requested_inner_state_budget)
        if isinstance(requested_inner_state_budget, dict)
        else {"max_direct_sentences": 1, "mode": passage_mode}
    )
    controls.append(
        StorytellingControlDraft(
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": contract_id,
                "mode": action_request.action_type,
                "passage_mode": passage_mode,
                "mode_rationale": mode_rationale,
                "pov_character": pov_character,
                "target_position": action_request.target or {},
                "role_slots": [role_slot_payload],
                "character_casting_decisions": [casting_decision_payload],
                "allowed_cast": context_pack.active_characters,
                "new_character_seeds": new_character_seeds,
                "new_character_policy": action_request.constraints.get(
                    "new_character_policy", "avoid"
                ),
                "scene_goal": action_request.actor_intent,
                "current_pressure": current_pressure,
                "opposition": scene_sequel_payload["opposition"],
                "required_turn": scene_sequel_payload["required_turn"],
                "inner_state_budget": inner_state_budget,
                "forbidden_knowledge": context_pack.pov_constraint.get("forbidden_knowledge", []),
                "risk_context": context_pack.risk_context,
                "scene_sequel_mode": scene_sequel_payload,
                "dramatic_behavior_plan": dramatic_behavior_payload,
                "show_not_tell_targets": show_not_tell_targets,
                "style_constraints": {"tone": "quiet", "language": "zh"},
                "ending_shape": scene_sequel_payload["ending_shape"],
                "hard_no": hard_no,
            },
        )
    )
    return controls


STORYTELLING_SCENE_CUES = (
    "推进",
    "进入",
    "打开",
    "推开",
    "阻止",
    "追",
    "逃",
    "拿",
    "走向",
    "停在",
    "门",
    "行动",
    "enter",
    "open",
    "push",
    "stop",
    "move",
    "act",
)
STORYTELLING_SEQUEL_CUES = (
    "意识到",
    "决定",
    "选择",
    "犹豫",
    "反应",
    "后果",
    "评估",
    "是否",
    "必须",
    "decide",
    "decision",
    "reaction",
    "dilemma",
    "realize",
)
STORYTELLING_GATEKEEPER_CUES = (
    "门",
    "门锁",
    "入口",
    "门槛",
    "阻拦",
    "看守",
    "archive",
    "door",
    "gate",
)
STORYTELLING_MESSENGER_CUES = (
    "消息",
    "传话",
    "通知",
    "信",
    "纸条",
    "message",
    "note",
)
STORYTELLING_WITNESS_CUES = (
    "看见",
    "听见",
    "目击",
    "证人",
    "witness",
    "saw",
    "heard",
)
STORYTELLING_PRESSURE_CUES = (
    "秘密",
    "身份",
    "暴露",
    "泄露",
    "风险",
    "冲突",
    "未确认",
    "secret",
    "identity",
    "risk",
    "conflict",
)


def _storytelling_current_text_window(context_pack: WritingContextPackOutput) -> str:
    return _storytelling_string(context_pack.current_position.get("current_text_window"))


def _storytelling_control_suffix(
    action_request: ActionRequestSnapshot,
    current_text_window: str,
) -> str:
    seed = "\n".join(
        [
            str(action_request.id),
            action_request.action_type,
            action_request.actor_intent,
            current_text_window,
        ]
    )
    return sha256(seed.encode("utf-8")).hexdigest()[:8]


def _storytelling_passage_mode(
    action_request: ActionRequestSnapshot,
    current_text_window: str,
) -> tuple[str, str]:
    combined_text = f"{current_text_window} {action_request.actor_intent}"
    scene_score = _storytelling_cue_score(combined_text, STORYTELLING_SCENE_CUES)
    sequel_score = _storytelling_cue_score(combined_text, STORYTELLING_SEQUEL_CUES)
    if sequel_score > scene_score:
        return "sequel", "当前文本优先处理反应、评估或决定。"
    if scene_score > sequel_score:
        return "scene", "当前文本和作者意图优先指向可观察行动与阻力。"
    if scene_score and sequel_score:
        return "mixed", "当前输入同时包含外部行动压力和内部判断压力。"
    return "scene", "作者请求要求继续推进当前段落。"


def _storytelling_current_pressure(
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
    current_text_window: str,
) -> str:
    risk_review = _storytelling_first_payload_text(
        context_pack.risk_context.get("review_items"),
        ("summary", "risk_type", "review_type", "description"),
    )
    if risk_review:
        return f"风险队列要求处理：{risk_review}"
    risk_fact = _storytelling_first_payload_text(
        context_pack.risk_context.get("facts"),
        ("value", "summary", "label", "predicate", "object"),
    )
    if risk_fact:
        return f"未确认事实压力：{risk_fact}"
    open_thread = _storytelling_first_payload_text(
        context_pack.open_threads,
        ("summary", "question", "title", "thread"),
    )
    if open_thread:
        return f"未解线程继续施压：{open_thread}"
    if current_text_window:
        return f"当前文本压力：{_storytelling_excerpt(current_text_window, 80)}"
    return f"作者意图压力：{_storytelling_excerpt(action_request.actor_intent, 80)}"


def _storytelling_role_function(
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
    current_text_window: str,
    current_pressure: str,
) -> str:
    combined_text = f"{current_text_window} {action_request.actor_intent} {current_pressure}"
    if _storytelling_contains_cue(combined_text, STORYTELLING_GATEKEEPER_CUES):
        return "gatekeeper"
    if _storytelling_contains_cue(combined_text, STORYTELLING_MESSENGER_CUES):
        return "messenger"
    if _storytelling_contains_cue(combined_text, STORYTELLING_WITNESS_CUES):
        return "witness"
    if context_pack.risk_context.get("review_items") or _storytelling_contains_cue(
        combined_text,
        STORYTELLING_PRESSURE_CUES,
    ):
        return "pressure_source"
    return "complication"


def _storytelling_required_traits(role_function: str) -> list[str]:
    if role_function == "gatekeeper":
        return ["observant", "boundary-setting"]
    if role_function == "messenger":
        return ["brief", "information-bearing"]
    if role_function == "witness":
        return ["specific", "externally observable"]
    if role_function == "pressure_source":
        return ["quiet", "friction-bearing"]
    return ["concrete", "scene-local"]


def _storytelling_role_risk(
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
) -> str:
    if _constraint_strings(action_request.constraints.get("hard_no")):
        return "medium"
    if context_pack.risk_context.get("review_items") or context_pack.risk_context.get("facts"):
        return "medium"
    return "low"


def _storytelling_scene_sequel_payload(
    action_request: ActionRequestSnapshot,
    passage_mode: str,
    mode_rationale: str,
    current_pressure: str,
) -> dict[str, object]:
    opposition = _storytelling_opposition(action_request, current_pressure)
    required_turn = _storytelling_required_turn(action_request, passage_mode)
    ending_shape = _storytelling_ending_shape(passage_mode)
    payload: dict[str, object] = {
        "passage_mode": passage_mode,
        "mode_rationale": mode_rationale,
        "current_pressure": current_pressure,
        "opposition": opposition,
        "required_turn": required_turn,
        "ending_shape": ending_shape,
    }
    if passage_mode == "sequel":
        payload.update(
            {
                "reaction": f"先承认压力的即时反应：{current_pressure}",
                "dilemma": f"是否继续执行作者意图，同时不越过限制：{opposition}",
                "decision": "让 POV 角色做出一个可逆、可观察的下一步决定。",
                "new_goal": action_request.actor_intent,
            }
        )
    elif passage_mode == "mixed":
        payload.update(
            {
                "scene_goal": action_request.actor_intent,
                "tactic": "用一个可见动作承接判断压力。",
                "reaction": f"保留当前压力的情绪回声：{current_pressure}",
                "dilemma": f"行动必须避开限制：{opposition}",
                "decision": "把小动作落成下一步选择。",
                "new_goal": action_request.actor_intent,
            }
        )
    else:
        payload.update(
            {
                "scene_goal": action_request.actor_intent,
                "tactic": "让角色用可观察行动测试阻力。",
                "escalation": f"阻力来自：{opposition}",
                "setback_or_turn": required_turn,
            }
        )
    return payload


def _storytelling_dramatic_behavior_payload(
    action_request: ActionRequestSnapshot,
    context_pack: WritingContextPackOutput,
    passage_mode: str,
) -> dict[str, object]:
    driver = _driver_character_from_context(context_pack)
    allowed_channels = ["action", "dialogue", "object", "silence"]
    if passage_mode in {"sequel", "mixed"}:
        allowed_channels.append("brief_direct_interiority")
    subtext_targets = _constraint_strings(action_request.constraints.get("subtext_targets"))
    return {
        "allowed_channels": allowed_channels,
        "subtext": subtext_targets,
        "render_as_action": _constraint_strings(action_request.constraints.get("render_as_action")),
        "render_as_dialogue": _constraint_strings(
            action_request.constraints.get("render_as_dialogue")
        ),
        "render_as_silence": _constraint_strings(
            action_request.constraints.get("render_as_silence")
        ),
        "render_as_object": _constraint_strings(action_request.constraints.get("render_as_object")),
        "render_as_sensory": _constraint_strings(
            action_request.constraints.get("render_as_sensory")
        ),
        "render_as_choice": _constraint_strings(action_request.constraints.get("render_as_choice")),
        "forbidden_action": "state disputed memory as canon",
        "agency_rationale": (
            f"{driver}只能依据当前文本窗口、证据边界和作者意图行动；"
            "未接受的候选不能被写成 Memory 或 canon。"
        ),
        "actor_intent": action_request.actor_intent,
    }


def _storytelling_new_character_seed_payload(
    *,
    seed_id: str,
    role_function: str,
    current_pressure: str,
) -> dict[str, object]:
    return {
        "seed_id": seed_id,
        "role_function": role_function,
        "display_hint": _storytelling_seed_display_hint(role_function),
        "scope": "scene_local",
        "promotion_hint": "memory_ingest_after_acceptance_only",
        "knowledge_boundary": "只拥有当前场景可观察信息，不携带未证实背景事实。",
        "scene_need": current_pressure,
        "risk": "low",
    }


def _storytelling_opposition(
    action_request: ActionRequestSnapshot,
    current_pressure: str,
) -> str:
    hard_no = _constraint_strings(action_request.constraints.get("hard_no"))
    if hard_no:
        return f"限制条件：{hard_no[0]}"
    return f"证据边界与当前压力：{_storytelling_excerpt(current_pressure, 60)}"


def _storytelling_required_turn(
    action_request: ActionRequestSnapshot,
    passage_mode: str,
) -> str:
    if passage_mode == "sequel":
        return "把反应推进成一个明确但可逆的下一步决定。"
    if passage_mode == "mixed":
        return "让一个小动作同时改变外部局面和角色判断。"
    return f"让“{_storytelling_excerpt(action_request.actor_intent, 48)}”遭遇可见阻力。"


def _storytelling_ending_shape(passage_mode: str) -> str:
    if passage_mode == "sequel":
        return "decision_with_new_goal"
    if passage_mode == "mixed":
        return "pressure_then_choice"
    return "setback_or_small_turn"


def _storytelling_seed_display_hint(role_function: str) -> str:
    display_hints = {
        "gatekeeper": "局部门槛角色",
        "messenger": "局部传话人",
        "witness": "局部目击者",
        "pressure_source": "局部施压者",
        "complication": "局部阻力角色",
    }
    return display_hints.get(role_function, "局部场景角色")


def _storytelling_first_payload_text(
    value: object,
    keys: tuple[str, ...],
) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        if not isinstance(item, dict):
            continue
        typed_item = cast(dict[str, object], item)
        for key in keys:
            text = _storytelling_string(typed_item.get(key))
            if text:
                return _storytelling_excerpt(text, 80)
    return ""


def _storytelling_cue_score(text: str, cues: tuple[str, ...]) -> int:
    text_lower = text.casefold()
    return sum(1 for cue in cues if cue.casefold() in text_lower)


def _storytelling_contains_cue(text: str, cues: tuple[str, ...]) -> bool:
    return _storytelling_cue_score(text, cues) > 0


def _storytelling_excerpt(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1]}…"


def _storytelling_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _draft_valid_story_result(
    uow: SextantUnitOfWork,
    input_data: RunActionRequestInput,
    story_request: StoryDraftRequest,
    story_draft_provider: StoryDraftProvider,
) -> StoryDraftResult:
    last_validation_error: ApplicationError | None = None
    for attempt in range(1, STORY_DRAFT_MAX_INVALID_ATTEMPTS + 1):
        story_result = story_draft_provider.draft(story_request)
        validation_error = _story_draft_validation_error(story_request, story_result)
        if validation_error is not None:
            validation_error = ApplicationError(
                validation_error.code,
                validation_error.message,
            )
            last_validation_error = validation_error
            _record_failed_story_draft_result(
                uow,
                input_data,
                story_request,
                structured_output=dict(story_result.structured_output),
                story_draft_provider=story_draft_provider,
                validation_error=validation_error,
                attempt=attempt,
                max_attempts=STORY_DRAFT_MAX_INVALID_ATTEMPTS,
            )
            uow.commit()
            if attempt == STORY_DRAFT_MAX_INVALID_ATTEMPTS:
                raise validation_error
            continue
        return story_result
    if last_validation_error is None:
        raise RuntimeError("story draft provider did not produce a result")
    raise last_validation_error


def _record_failed_story_draft_result(
    uow: SextantUnitOfWork,
    input_data: RunActionRequestInput,
    story_request: StoryDraftRequest,
    *,
    structured_output: dict[str, object],
    story_draft_provider: StoryDraftProvider,
    validation_error: ApplicationError,
    attempt: int,
    max_attempts: int,
) -> None:
    uow.persist_failed_skill_run(
        PersistFailedSkillRunInput(
            project_id=input_data.project_id,
            skill_name=story_draft_provider.skill_name,
            skill_version=story_draft_provider.skill_version,
            input_schema_version="story-draft-request.v1",
            output_schema_version="story-draft-result.v1",
            prompt_version=_story_draft_prompt_version(story_draft_provider),
            input_hash=_dataclass_hash(story_request),
            structured_output=structured_output,
            validation_result={
                "status": "invalid",
                "error_code": validation_error.code,
                "message": validation_error.message,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "will_retry": attempt < max_attempts,
            },
        )
    )


def _story_draft_prompt_version(story_draft_provider: StoryDraftProvider) -> str:
    prompt_version = getattr(story_draft_provider, "prompt_version", None)
    if isinstance(prompt_version, str) and prompt_version.strip():
        return prompt_version.strip()
    return story_draft_provider.skill_version


def _story_draft_validation_error(
    story_request: StoryDraftRequest, story_result: StoryDraftResult
) -> ApplicationError | None:
    if not story_result.text.strip():
        return ApplicationError(
            "llm_output_invalid",
            "Story draft provider returned empty text.",
        )
    structured_text = story_result.structured_output.get("text")
    if not isinstance(structured_text, str) or not structured_text.strip():
        return ApplicationError(
            "llm_output_invalid",
            "Story draft provider returned structured output without text.",
        )
    if structured_text.strip() != story_result.text.strip():
        return ApplicationError(
            "llm_output_invalid",
            "Story draft provider text does not match structured output text.",
        )
    if not _story_output_contract_metadata_matches(story_request, story_result):
        return ApplicationError(
            "llm_output_invalid",
            "Story draft provider returned mismatched contract metadata.",
        )
    if not story_result.finish_reason.strip():
        return ApplicationError(
            "llm_output_invalid",
            "Story draft provider returned empty finish reason.",
        )
    for cue in story_result.review_cues:
        if not _valid_story_review_cue(cue):
            return ApplicationError(
                "llm_output_invalid",
                "Story draft provider returned invalid review cue.",
            )
    return None


def _story_output_contract_metadata_matches(
    story_request: StoryDraftRequest, story_result: StoryDraftResult
) -> bool:
    expected_contract_id = story_request.prose_rendering_contract.get("contract_id")
    expected_mode = story_request.prose_rendering_contract.get("mode")
    output_contract_id = story_result.structured_output.get("prose_contract_id")
    output_mode = story_result.structured_output.get("mode")
    return (
        isinstance(expected_contract_id, str)
        and isinstance(expected_mode, str)
        and output_contract_id == expected_contract_id
        and output_mode == expected_mode
    )


def _valid_story_review_cue(cue: dict[str, object]) -> bool:
    required_text_fields = ("risk_level", "risk_type", "summary")
    if any(
        not isinstance(cue.get(field), str) or not str(cue[field]).strip()
        for field in required_text_fields
    ):
        return False
    if cue["risk_level"] not in AGENT_RISK_LEVELS or cue["risk_type"] not in AGENT_RISK_TYPES:
        return False
    if not isinstance(cue.get("can_offer_to_author"), bool):
        return False
    review_type = cue.get("maps_to_review_type_if_accepted")
    return review_type is None or (
        isinstance(review_type, str) and review_type in REVIEW_TYPE_VALUES
    )


def _agent_review_findings(
    review_cues: list[dict[str, object]],
    candidate_text_ref: str,
    *,
    candidate_text: str | None = None,
    prose_contract: dict[str, object] | None = None,
    structured_output: dict[str, object] | None = None,
) -> list[AgentReviewFindingDraft]:
    findings: list[AgentReviewFindingDraft] = []
    for cue in review_cues:
        findings.append(
            AgentReviewFindingDraft(
                risk_level=str(cue["risk_level"]),
                risk_type=str(cue["risk_type"]),
                summary=str(cue["summary"]),
                affected_text_ref=candidate_text_ref,
                memory_refs={},
                storytelling_refs={"source": "local_agent_review"},
                suggested_revision=None,
                can_offer_to_author=bool(cue["can_offer_to_author"]),
                maps_to_review_type_if_accepted=cast(
                    str | None, cue.get("maps_to_review_type_if_accepted")
                ),
            )
        )
    if candidate_text is not None:
        for finding in review_prose_contract(
            text=candidate_text,
            contract=prose_contract,
            policy_version="agent-review-policy.v1",
            structured_output=structured_output,
        ):
            findings.append(
                AgentReviewFindingDraft(
                    risk_level=finding.risk_level,
                    risk_type=finding.risk_type,
                    summary=finding.summary,
                    affected_text_ref=candidate_text_ref,
                    memory_refs={},
                    storytelling_refs=finding.storytelling_refs,
                    suggested_revision=finding.suggested_revision,
                    can_offer_to_author=finding.can_offer_to_author,
                    maps_to_review_type_if_accepted=finding.maps_to_review_type_if_accepted,
                )
            )
    return findings


def _target_range(target: dict[str, object] | None) -> dict[str, int] | None:
    if target is None:
        return None
    selected_range = target.get("range")
    if not isinstance(selected_range, dict):
        return None
    typed_range = cast(dict[str, object], selected_range)
    start = typed_range.get("start")
    end = typed_range.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return {"start": start, "end": end}


def _constraint_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _candidate_id_from_target(target: dict[str, object] | None) -> UUID:
    if target is None or target.get("kind") != "candidate":
        raise ApplicationError(
            "missing_target",
            "Candidate action requires a candidate target.",
        )
    candidate_id = target.get("candidate_id")
    try:
        return UUID(str(candidate_id))
    except (TypeError, ValueError) as exc:
        raise ApplicationError(
            "missing_target",
            "Candidate action requires a valid candidate_id.",
        ) from exc


def _dataclass_hash(value: StoryDraftRequest) -> str:
    payload = _jsonable(asdict(value))
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_target(target: dict[str, object]) -> None:
    if target.get("kind") == "selected_text":
        selected_range = target.get("range")
        if not isinstance(selected_range, dict):
            raise ApplicationError("invalid_target_range", "Selected target requires a range.")
        _validate_accept_range(cast(dict[str, object], selected_range))
        if not target.get("source_id") or not target.get("source_version_id"):
            raise ApplicationError(
                "missing_target",
                "Selected target requires source_id and source_version_id.",
            )
    if target.get("kind") == "candidate":
        _candidate_id_from_target(target)


def _validate_accept_range(selected_range: dict[str, int] | dict[str, object]) -> None:
    start = selected_range.get("start")
    end = selected_range.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        raise ApplicationError("invalid_target_range", "Target range is invalid.")


def _validate_candidate_acceptance(
    candidate: CandidateSnapshot, input_data: AcceptCandidateInput
) -> None:
    if candidate.status == "blocked":
        raise ApplicationError("blocked_without_override", "Blocked candidate requires override.")
    if candidate.status != "offered_to_author":
        raise ApplicationError("candidate_not_offerable", "Candidate is not offerable.")
    if candidate.target_source_id != input_data.target_source_id:
        raise ApplicationError("invalid_target_range", "Candidate target source mismatch.")
    if candidate.target_version_id != input_data.target_version_id:
        raise ApplicationError("stale_source_version", "Candidate target version mismatch.")
    if input_data.base_hash is not None and candidate.base_hash != input_data.base_hash:
        raise ApplicationError(
            "stale_source_version",
            "Candidate base hash does not match the accept request.",
            {
                "candidate_base_hash": candidate.base_hash,
                "request_base_hash": input_data.base_hash,
            },
        )


def _validate_candidate_operation(
    candidate: CandidateSnapshot, input_data: CandidateOperationInput
) -> None:
    if input_data.operation == "reject" and candidate.status not in {
        "generated",
        "reviewed",
        "offered_to_author",
        "blocked",
    }:
        raise ApplicationError("invalid_state_transition", "Candidate cannot be rejected.")
    if input_data.operation == "override_block" and candidate.status != "blocked":
        raise ApplicationError(
            "invalid_state_transition",
            "Only blocked candidates can be overridden.",
        )
    if input_data.operation == "revise" and candidate.status not in {
        "generated",
        "reviewed",
        "offered_to_author",
        "blocked",
    }:
        raise ApplicationError("invalid_state_transition", "Candidate cannot be revised.")


def _validate_review_transition(
    review_item: ReviewItemSnapshot, input_data: ReviewItemOperationInput
) -> None:
    if input_data.operation == "resolve" and review_item.status != "open":
        raise ApplicationError("invalid_state_transition", "Only open ReviewItems can be resolved.")
    if input_data.operation == "dismiss" and review_item.status != "open":
        raise ApplicationError(
            "invalid_state_transition",
            "Only open ReviewItems can be dismissed.",
        )
    if input_data.operation == "reopen" and review_item.status != "dismissed":
        raise ApplicationError(
            "invalid_state_transition",
            "Only dismissed ReviewItems can be reopened.",
        )


def _validate_review_resolution_payload(input_data: ReviewItemOperationInput) -> None:
    if input_data.resolution not in {"split", "merge", "fixed_by_text_edit", "supersede"}:
        return
    author_note = (input_data.author_note or "").strip()
    replacement_refs = input_data.replacement_refs or []
    if input_data.resolution == "supersede":
        has_replacement_ref = any(
            isinstance(ref, dict)
            and ref.get("type") in {"source_delta", "review_item", "source_span"}
            and isinstance(ref.get("id"), str)
            and bool(str(ref["id"]).strip())
            for ref in replacement_refs
        )
        if author_note and has_replacement_ref:
            return
        raise ApplicationError(
            "schema_validation_failed",
            "Supersede ReviewItem resolutions require an author note and replacement "
            "SourceDelta, ReviewItem, or SourceSpan refs.",
        )

    has_source_delta_ref = any(
        isinstance(ref, dict)
        and ref.get("type") == "source_delta"
        and isinstance(ref.get("id"), str)
        and bool(str(ref["id"]).strip())
        for ref in replacement_refs
    )
    if author_note and has_source_delta_ref:
        return
    raise ApplicationError(
        "schema_validation_failed",
        "Split, merge, and fixed_by_text_edit ReviewItem resolutions require an author "
        "note and replacement SourceDelta refs.",
    )


def _validate_source_scope_conflict_resolution_payload(
    review_item: ReviewItemSnapshot,
    input_data: ReviewItemOperationInput,
) -> None:
    if (
        input_data.operation != "resolve"
        or review_item.review_type != "source_scope_conflict"
        or review_item.new_evidence.get("source_scope") != "model_suggestion"
    ):
        return
    if input_data.resolution == "accept":
        raise ApplicationError(
            "schema_validation_failed",
            "source_scope_conflict ReviewItems from model_suggestion cannot be "
            "accepted directly; use accepted_as_change or fixed_by_text_edit with "
            "replacement SourceDelta evidence.",
        )
    if input_data.resolution not in {"accepted_as_change", "fixed_by_text_edit"}:
        return
    author_note = (input_data.author_note or "").strip()
    if author_note and _review_has_source_delta_ref(input_data):
        return
    raise ApplicationError(
        "schema_validation_failed",
        "source_scope_conflict ReviewItems from model_suggestion require an "
        "author note and replacement SourceDelta refs before they can be accepted "
        "as author canon changes.",
    )


def _source_scope_conflict_requires_replacement_source_delta(
    review_item: ReviewItemSnapshot,
    input_data: ReviewItemOperationInput,
) -> bool:
    return (
        input_data.operation == "resolve"
        and input_data.resolution in {"accepted_as_change", "fixed_by_text_edit"}
        and review_item.review_type == "source_scope_conflict"
        and review_item.new_evidence.get("source_scope") == "model_suggestion"
    )


def _source_scope_conflict_requires_author_source_delta(
    review_item: ReviewItemSnapshot,
    input_data: ReviewItemOperationInput,
) -> bool:
    return _source_scope_conflict_requires_replacement_source_delta(review_item, input_data)


def _review_has_source_delta_ref(input_data: ReviewItemOperationInput) -> bool:
    return any(
        isinstance(ref, dict)
        and ref.get("type") == "source_delta"
        and isinstance(ref.get("id"), str)
        and bool(str(ref["id"]).strip())
        for ref in input_data.replacement_refs or []
    )


def _review_requires_replacement_source_delta(input_data: ReviewItemOperationInput) -> bool:
    return input_data.operation == "resolve" and input_data.resolution in {
        "split",
        "merge",
        "fixed_by_text_edit",
    }


def _review_requires_replacement_refs(input_data: ReviewItemOperationInput) -> bool:
    return input_data.operation == "resolve" and input_data.resolution == "supersede"


def _review_replacement_source_delta_ids(
    input_data: ReviewItemOperationInput,
) -> list[UUID]:
    source_delta_ids: list[UUID] = []
    for ref in input_data.replacement_refs or []:
        if not isinstance(ref, dict) or ref.get("type") != "source_delta":
            continue
        try:
            source_delta_ids.append(UUID(str(ref["id"])))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApplicationError(
                "schema_validation_failed",
                "Replacement SourceDelta refs require valid UUID ids.",
            ) from exc
    return source_delta_ids


def _review_replacement_ref_ids(
    input_data: ReviewItemOperationInput,
) -> dict[str, list[UUID]]:
    refs_by_type: dict[str, list[UUID]] = {
        "source_delta": [],
        "review_item": [],
        "source_span": [],
    }
    for ref in input_data.replacement_refs or []:
        if not isinstance(ref, dict):
            raise ApplicationError(
                "schema_validation_failed",
                "Replacement refs must use source_delta, review_item, or source_span types.",
            )
        ref_type = ref.get("type")
        if not isinstance(ref_type, str):
            raise ApplicationError(
                "schema_validation_failed",
                "Replacement refs must use source_delta, review_item, or source_span types.",
            )
        if ref_type not in refs_by_type:
            raise ApplicationError(
                "schema_validation_failed",
                "Replacement refs must use source_delta, review_item, or source_span types.",
            )
        try:
            ref_id = UUID(str(ref["id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ApplicationError(
                "schema_validation_failed",
                "Replacement refs require valid UUID ids.",
            ) from exc
        if ref_type == "review_item" and ref_id == input_data.review_item_id:
            raise ApplicationError(
                "schema_validation_failed",
                "A superseded ReviewItem cannot use itself as a replacement ref.",
            )
        refs_by_type[ref_type].append(ref_id)
    return {ref_type: ids for ref_type, ids in refs_by_type.items() if ids}


def _validate_review_correction_payload(
    review_item: ReviewItemSnapshot,
    input_data: ReviewItemOperationInput,
) -> None:
    if not input_data.correction:
        return
    if review_item.review_type != "alias_conflict":
        raise ApplicationError(
            "schema_validation_failed",
            "Review correction payloads are currently supported only for alias conflicts.",
        )
    if input_data.resolution not in {"accept", "accepted_as_change", "merge"}:
        raise ApplicationError(
            "schema_validation_failed",
            "Alias correction requires accept, accepted_as_change, or merge resolution.",
        )
    try:
        _review_alias_correction_ids(review_item, input_data)
        _review_alias_boundary_scene_refs(input_data)
    except (TypeError, ValueError) as exc:
        raise ApplicationError(
            "schema_validation_failed",
            "Alias correction requires alias_record_id, target_entity_id, and valid "
            "boundary scene UUIDs when provided.",
        ) from exc


def _review_alias_correction_ids(
    review_item: ReviewItemSnapshot,
    input_data: ReviewItemOperationInput,
) -> tuple[UUID, UUID]:
    if input_data.correction is None:
        raise TypeError("correction is required")
    alias_record_id = input_data.correction.get("alias_record_id") or review_item.affected_refs.get(
        "alias_record_id"
    )
    target_entity_id = input_data.correction.get(
        "target_entity_id"
    ) or review_item.affected_refs.get("target_entity_id")
    return UUID(str(alias_record_id)), UUID(str(target_entity_id))


def _review_alias_boundary_scene_refs(
    input_data: ReviewItemOperationInput,
) -> dict[str, UUID | None]:
    if input_data.correction is None:
        return {}
    refs: dict[str, UUID | None] = {}
    for key in ("valid_from_scene_id", "valid_until_scene_id"):
        if key not in input_data.correction:
            continue
        value = input_data.correction[key]
        if value is None:
            refs[key] = None
            continue
        text = str(value).strip()
        if not text:
            raise ValueError(f"{key} cannot be blank")
        refs[key] = UUID(text)
    return refs


def _review_side_effects(input_data: ReviewItemOperationInput) -> dict[str, object]:
    if input_data.operation == "reopen":
        return {
            "review_queue": "open",
            "memory_pages": "unchanged",
            "graph_projection": "unchanged",
        }
    if input_data.operation == "dismiss":
        return {
            "promotion": "none",
            "memory_pages": "unchanged",
            "graph_projection": "unchanged",
        }
    if input_data.resolution == "fixed_by_text_edit":
        return {
            "memory_pages": "awaiting_new_source_delta",
            "graph_projection": "unchanged_until_new_source_delta",
            "replacement_refs": input_data.replacement_refs or [],
            "policy_action": "await_replacement_source_delta",
        }
    if input_data.resolution in {"split", "merge"}:
        return {
            "memory_pages": "mark_stale",
            "graph_projection": "mark_stale",
            "replacement_refs": input_data.replacement_refs or [],
            "policy_action": "split_merge_rebuild_required",
        }
    if input_data.resolution in {"accept", "split", "merge", "supersede", "accepted_as_change"}:
        return {
            "memory_pages": "mark_stale",
            "graph_projection": "mark_stale",
            "replacement_refs": input_data.replacement_refs or [],
        }
    return {"memory_pages": "unchanged", "graph_projection": "unchanged"}
