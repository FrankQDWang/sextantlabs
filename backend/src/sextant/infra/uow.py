from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import String, and_, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session

from sextant.contracts.use_cases import (
    AcceptCandidateInput,
    AcceptCandidateOutput,
    ActionRequestSnapshot,
    AgentReviewFindingDraft,
    AgentReviewFindingSnapshot,
    ArchiveSourceInput,
    ArchiveSourceOutput,
    BeatCandidateSnapshot,
    BuildWritingContextPackInput,
    CandidateDetailSnapshot,
    CandidateOperationInput,
    CandidateOperationOutput,
    CandidateSnapshot,
    CanonicalEntitySummaryOutput,
    ContextPackDetailInput,
    ContextPackReadinessSummaryOutput,
    ContextPackSummaryOutput,
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
    GraphProjectionEdgeSummaryOutput,
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
    MemoryPageSummaryOutput,
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
    SourceVersionSummaryOutput,
    StorySceneSummaryOutput,
    StorySchemaPackOutput,
    SubmitActionRequestInput,
    SubmitActionRequestOutput,
    UpsertProjectMemberInput,
    UpsertProjectStorySchemaOverrideInput,
    WritingContextPackOutput,
)
from sextant.domain.story_schema import (
    EffectiveStorySchema,
    StorySchemaPackSnapshot,
    build_effective_story_schema,
    default_base_story_schema_pack,
)
from sextant.infra.context_readiness import mark_context_pack_readiness
from sextant.infra.db.models import (
    AcceptedFragmentRecord,
    AgentActionRequestRecord,
    AgentBeatCandidateRecord,
    AgentContextPackRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    AuditEvent,
    CharacterKnowledge,
    ContextPackReadinessRecord,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
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
from sextant.infra.fact_dedup import refs_equivalent
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.retrieval_fusion import reciprocal_rank_fusion
from sextant.infra.semantic_search import SemanticRecallResult, semantic_ref_keys_for_text
from sextant.infra.source_delta_search import source_delta_search_text
from sextant.ports.embedding import EmbeddingClient

CONTEXT_RETRIEVAL_POLICY: dict[str, object] = {
    "version": "context-relevance-v1",
    "sort": "score_desc_then_recency",
    "sections": [
        "canonical_context",
        "risk_context",
        "recent_events",
        "object_location_state",
        "style_memory",
    ],
}
SEMANTIC_RRF_SCORE_SCALE = 1000
STYLE_MEMORY_WINDOW_SIZE = 3

MEMORY_ANSWER_QUERY_STOPWORDS = {
    "about",
    "after",
    "and",
    "are",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "the",
    "their",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

MEMORY_ANSWER_KNOWLEDGE_GENERIC_TERMS = {
    "know",
    "knows",
    "known",
    "learn",
    "learned",
    "realize",
    "realized",
    "secret",
    "secrets",
    "知道",
    "得知",
    "秘密",
}

MEMORY_ANSWER_NOT_KNOW_TERMS = {
    "not",
    "unknown",
    "unaware",
    "不知道",
    "不知",
}

MEMORY_ANSWER_SUSPECT_TERMS = {
    "suspect",
    "suspects",
    "suspected",
    "怀疑",
}

MEMORY_ANSWER_MISUNDERSTAND_TERMS = {
    "false",
    "belief",
    "believes",
    "misunderstand",
    "misunderstands",
    "mistaken",
    "误会",
    "误解",
    "误以为",
}

MEMORY_ANSWER_KNOWLEDGE_INVENTORY_TERMS = {
    "what",
    "which",
    "list",
    "secrets",
    "secret",
    "哪些",
    "什么",
}

AGENCY_PROFILE_SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("core_desire", "core_desire"),
    ("immediate_want", "immediate_want"),
    ("fear_or_wound", "fear_or_wound"),
    ("moral_boundary", "moral_boundary"),
    ("secret", "secret"),
    ("contradiction", "contradiction"),
    ("voice_fingerprint", "voice_fingerprint"),
    ("agency_rule", "agency_rule"),
    ("change_pressure", "pressure"),
)

AGENCY_PROFILE_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("relationship_stance", "relationship_stance"),
)

MEMORY_ANSWER_EVENT_AFTER_TERMS = {
    "after",
    "later",
    "then",
    "之后",
    "后来",
    "接着",
}

MEMORY_ANSWER_EVENT_OVERLAP_TERMS = {
    "during",
    "meanwhile",
    "simultaneous",
    "simultaneously",
    "while",
    "同时",
    "期间",
}

MEMORY_ANSWER_EVENT_QUERY_TERMS = {
    "happen",
    "happening",
    "happened",
    "event",
    "events",
    "occurred",
    "发生",
    "事件",
    "后来",
}

MEMORY_ANSWER_SCOPED_ALIAS_CONTEXT_CAVEAT = "scene_local_alias_context"
MEMORY_ANSWER_LOCAL_ALIAS_SCOPES = {
    "scene_local",
    "chapter_local",
    "character_specific",
    "disguise_arc",
}

MEMORY_ANSWER_RELATIONSHIP_QUERY_TERMS = {
    "alliance",
    "ally",
    "allies",
    "enemy",
    "enemies",
    "hostile",
    "relationship",
    "relation",
    "related",
    "rival",
    "rivals",
    "why",
    "ally_of",
    "enemy_of",
    "family_of",
    "related_to",
    "关系",
    "敌对",
    "敌人",
    "盟友",
    "同盟",
    "亲属",
    "为什么",
}

MEMORY_ANSWER_RELATIONSHIP_TIMELINE_TERMS = {
    "change",
    "changed",
    "changing",
    "evolve",
    "evolved",
    "evolution",
    "history",
    "timeline",
    "变化",
    "改变",
    "演变",
    "发展",
    "时间线",
}

MEMORY_ANSWER_RELATIONSHIP_PATH_TERMS = {
    "connect",
    "connected",
    "connection",
    "link",
    "linked",
    "path",
    "through",
    "关联",
    "联系",
    "连接",
    "路径",
    "通过",
    "认识",
    "相识",
}

MEMORY_ANSWER_RELATIONSHIP_PATH_MAX_EDGES = 6

MEMORY_ANSWER_RELATIONSHIP_PREDICATE_TERMS: dict[str, set[str]] = {
    "enemy_of": {
        "betray",
        "betrayal",
        "betrayed",
        "betrays",
        "distrust",
        "distrusts",
        "enemy",
        "enemies",
        "enemy_of",
        "frame",
        "framed",
        "frames",
        "hostile",
        "oppose",
        "opposed",
        "opposes",
        "rival",
        "rivals",
        "不信任",
        "敌人",
        "敌对",
        "背叛",
        "陷害",
    },
    "ally_of": {
        "alliance",
        "allies",
        "ally",
        "ally_of",
        "help",
        "helps",
        "protect",
        "protected",
        "protects",
        "support",
        "supports",
        "trust",
        "trusted",
        "trusting",
        "trusts",
        "保护",
        "信任",
        "同盟",
        "盟友",
    },
    "family_of": {"family", "kin", "relative", "family_of", "亲属", "家人"},
    "related_to": {"relationship", "relation", "related", "related_to", "关系"},
}

MEMORY_ANSWER_RELATIONSHIP_NEGATED_TRUST_PHRASES = (
    "lose trust",
    "loses trust",
    "lost trust",
    "no longer trust",
    "no longer trusts",
    "stop trusting",
    "stopped trusting",
    "stops trusting",
    "不再信任",
    "失去信任",
)

MEMORY_ANSWER_RELATIONSHIP_PREDICATES = frozenset(MEMORY_ANSWER_RELATIONSHIP_PREDICATE_TERMS)

MEMORY_ANSWER_CONTINUITY_QUERY_TERMS = {
    "canon",
    "conflict",
    "conflicts",
    "contradict",
    "contradiction",
    "contradictions",
    "continuity",
    "inconsistent",
    "inconsistency",
    "risk",
    "risks",
    "矛盾",
    "冲突",
    "连续性",
    "穿帮",
    "前文",
    "设定",
}

MEMORY_ANSWER_CONTINUITY_FOCUS_STOPWORDS = MEMORY_ANSWER_CONTINUITY_QUERY_TERMS | {
    "chapter",
    "earlier",
    "previous",
    "this",
    "本章",
    "这章",
    "这一章",
}

MEMORY_ANSWER_CONTINUITY_REVIEW_TYPES = frozenset(
    {
        "canon_conflict",
        "continuity_warning",
        "knowledge_conflict",
        "object_state_conflict",
        "pov_conflict",
        "relationship_conflict",
        "source_scope_conflict",
        "state_conflict",
        "timeline_conflict",
        "version_conflict",
    }
)

MEMORY_ANSWER_OPEN_THREAD_QUERY_TERMS = {
    "dangling",
    "mystery",
    "open",
    "question",
    "questions",
    "remain",
    "remaining",
    "thread",
    "threads",
    "unresolved",
    "伏笔",
    "悬念",
    "线索",
    "未解",
    "未解决",
    "问题",
}

MEMORY_ANSWER_OPEN_THREAD_FOCUS_STOPWORDS = MEMORY_ANSWER_OPEN_THREAD_QUERY_TERMS | {
    "list",
    "show",
    "still",
    "哪些",
    "什么",
    "还有",
}

MEMORY_ANSWER_FIRST_APPEARANCE_FIRST_TERMS = {
    "first",
    "earliest",
    "initial",
    "introduced",
    "第一次",
    "首次",
    "最早",
    "初次",
}

MEMORY_ANSWER_FIRST_APPEARANCE_APPEAR_TERMS = {
    "appear",
    "appears",
    "appeared",
    "appearance",
    "seen",
    "shown",
    "introduced",
    "出现",
    "登场",
    "亮相",
}

MEMORY_ANSWER_PREDICATE_TERMS: dict[str, set[str]] = {
    "owns": {
        "carry",
        "carries",
        "has",
        "have",
        "hold",
        "holds",
        "own",
        "owns",
        "possess",
        "possesses",
        "持有",
        "拥有",
        "拿着",
    },
    "knows": {
        "know",
        "knows",
        "learned",
        "realized",
        "suspect",
        "suspects",
        "知道",
        "得知",
        "意识到",
        "怀疑",
    },
    "located_in": {
        "at",
        "located",
        "where",
        "位置",
        "哪里",
        "在",
    },
    "appears_in": {
        "appear",
        "appears",
        "seen",
        "出现",
        "登场",
    },
}


class SqlAlchemyUnitOfWork:
    def __init__(
        self,
        session: Session,
        *,
        close_on_exit: bool = False,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._session = session
        self._close_on_exit = close_on_exit
        self._embedding_client = embedding_client

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        if exc_type is not None:
            self.rollback()
        if self._close_on_exit:
            self._session.close()

    def project_accessible(self, project_id: UUID, actor_id: UUID) -> bool:
        if self._session.get(Project, project_id) is None:
            return False
        membership = (
            self._session.query(ProjectMembership)
            .filter_by(project_id=project_id, actor_id=actor_id, status="active")
            .one_or_none()
        )
        return membership is not None and membership.role in {"owner", "editor"}

    def project_readable(self, project_id: UUID, actor_id: UUID) -> bool:
        if self._session.get(Project, project_id) is None:
            return False
        membership = (
            self._session.query(ProjectMembership)
            .filter_by(project_id=project_id, actor_id=actor_id, status="active")
            .one_or_none()
        )
        return membership is not None and membership.role in {"owner", "editor", "viewer"}

    def get_project(self, input_data: GetProjectInput) -> ProjectDetailOutput | None:
        row = (
            self._session.query(Project, ProjectMembership)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .filter(Project.id == input_data.project_id)
            .filter(ProjectMembership.actor_id == input_data.actor_id)
            .filter(ProjectMembership.status == "active")
            .one_or_none()
        )
        if row is None:
            return None
        project, membership = row
        if membership.role not in {"owner", "editor", "viewer"}:
            return None
        return ProjectDetailOutput(
            id=project.id,
            name=project.name,
            actor_role=membership.role,
            created_at=project.created_at,
        )

    def project_actor_role(self, project_id: UUID, actor_id: UUID) -> str | None:
        membership = (
            self._session.query(ProjectMembership)
            .filter_by(project_id=project_id, actor_id=actor_id, status="active")
            .one_or_none()
        )
        if membership is None:
            return None
        return membership.role

    def list_project_members(self, input_data: ListProjectMembersInput) -> ListProjectMembersOutput:
        memberships = (
            self._session.query(ProjectMembership)
            .filter(ProjectMembership.project_id == input_data.project_id)
            .all()
        )
        role_order = {"owner": 0, "editor": 1, "viewer": 2}
        memberships = sorted(
            memberships,
            key=lambda membership: (
                0 if membership.status == "active" else 1,
                role_order.get(membership.role, 99),
                membership.created_at,
                str(membership.actor_id),
            ),
        )
        return ListProjectMembersOutput(
            items=[_project_member_snapshot(membership) for membership in memberships]
        )

    def list_project_invitations(
        self, input_data: ListProjectInvitationsInput
    ) -> ListProjectInvitationsOutput:
        invitations = (
            self._session.query(ProjectInvitation)
            .filter(ProjectInvitation.project_id == input_data.project_id)
            .order_by(ProjectInvitation.created_at.desc(), ProjectInvitation.id.asc())
            .all()
        )
        return ListProjectInvitationsOutput(
            items=[_project_invitation_snapshot(invitation) for invitation in invitations]
        )

    def active_project_owner_count(self, project_id: UUID) -> int:
        return int(
            self._session.query(func.count(ProjectMembership.id))
            .filter_by(project_id=project_id, role="owner", status="active")
            .scalar()
            or 0
        )

    def upsert_project_member(
        self, input_data: UpsertProjectMemberInput
    ) -> ProjectMemberOperationOutput:
        membership = (
            self._session.query(ProjectMembership)
            .filter_by(project_id=input_data.project_id, actor_id=input_data.member_actor_id)
            .one_or_none()
        )
        if membership is None:
            membership = ProjectMembership(
                id=uuid4(),
                project_id=input_data.project_id,
                actor_id=input_data.member_actor_id,
                role=input_data.role,
                status="active",
            )
            self._session.add(membership)
        else:
            membership.role = input_data.role
            membership.status = "active"
        self._session.flush()
        self._session.refresh(membership)
        return ProjectMemberOperationOutput(
            member=_project_member_snapshot(membership),
            status=membership.status,
        )

    def revoke_project_member(
        self, input_data: RevokeProjectMemberInput
    ) -> ProjectMemberSnapshot | None:
        membership = (
            self._session.query(ProjectMembership)
            .filter_by(project_id=input_data.project_id, actor_id=input_data.member_actor_id)
            .one_or_none()
        )
        if membership is None:
            return None
        membership.status = "revoked"
        self._session.flush()
        self._session.refresh(membership)
        return _project_member_snapshot(membership)

    def create_project_invitation(
        self, input_data: CreateProjectInvitationInput
    ) -> ProjectInvitationSnapshot:
        invitation = ProjectInvitation(
            id=uuid4(),
            project_id=input_data.project_id,
            member_actor_id=input_data.member_actor_id,
            role=input_data.role,
            delivery_provider_ref=input_data.delivery_provider_ref,
            delivery_target_ref=input_data.delivery_target_ref,
            token_issuer_ref=input_data.token_issuer_ref,
            status="pending_external_delivery",
            delivery_status="not_sent",
            token_status="not_issued",
        )
        self._session.add(invitation)
        self._session.flush()
        self._session.refresh(invitation)
        return _project_invitation_snapshot(invitation)

    def get_project_invitation(
        self, project_id: UUID, invitation_id: UUID
    ) -> ProjectInvitationSnapshot | None:
        invitation = self._session.get(ProjectInvitation, invitation_id)
        if invitation is None or invitation.project_id != project_id:
            return None
        return _project_invitation_snapshot(invitation)

    def record_project_invitation_external_proof(
        self, input_data: RecordProjectInvitationExternalProofInput
    ) -> ProjectInvitationSnapshot | None:
        invitation = self._session.get(ProjectInvitation, input_data.invitation_id)
        if invitation is None or invitation.project_id != input_data.project_id:
            return None
        now = datetime.now(UTC)
        invitation.status = "external_delivery_recorded"
        invitation.delivery_status = "sent"
        invitation.delivery_proof_ref = input_data.delivery_proof_ref
        invitation.delivered_at = now
        if invitation.token_issuer_ref is not None and input_data.token_proof_ref is not None:
            invitation.token_status = "issued"
            invitation.token_proof_ref = input_data.token_proof_ref
            invitation.token_issued_at = now
        self._session.flush()
        self._session.refresh(invitation)
        return _project_invitation_snapshot(invitation)

    def load_idempotency_record(
        self, project_id: UUID, actor_id: UUID, operation: str, idempotency_key: str
    ) -> IdempotencySnapshot | None:
        record = (
            self._session.query(IdempotencyRecord)
            .filter_by(
                project_id=project_id,
                actor_id=actor_id,
                operation=operation,
                idempotency_key=idempotency_key,
            )
            .one_or_none()
        )
        if record is None:
            return None
        return IdempotencySnapshot(
            operation=record.operation,
            idempotency_key=record.idempotency_key,
            request_hash=record.request_hash,
            response_payload=record.response_payload,
        )

    def store_idempotency_record(
        self,
        *,
        project_id: UUID,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
        request_hash: str,
        response_payload: dict[str, object],
    ) -> None:
        self._session.add(
            IdempotencyRecord(
                id=uuid4(),
                project_id=project_id,
                actor_id=actor_id,
                operation=operation,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_payload=response_payload,
            )
        )

    def create_action_request(
        self, input_data: SubmitActionRequestInput
    ) -> SubmitActionRequestOutput:
        action_request = AgentActionRequestRecord(
            id=uuid4(),
            project_id=input_data.project_id,
            source_id=input_data.source_id,
            source_version_id=input_data.source_version_id,
            scene_id=input_data.scene_id,
            chapter_id=input_data.chapter_id,
            pov_character_id=input_data.pov_character_id,
            actor_intent=input_data.actor_intent,
            trigger=input_data.trigger,
            action_type=input_data.action_type,
            target=input_data.target,
            constraints=input_data.constraints,
            expected_output=input_data.expected_output,
            status="submitted",
            created_by=input_data.actor_id,
        )
        self._session.add(action_request)
        self._session.flush()
        return SubmitActionRequestOutput(
            action_request_id=action_request.id,
            status=action_request.status,
        )

    def load_action_request(self, action_request_id: UUID) -> ActionRequestSnapshot | None:
        action_request = self._session.get(AgentActionRequestRecord, action_request_id)
        if action_request is None:
            return None
        return ActionRequestSnapshot(
            id=action_request.id,
            project_id=action_request.project_id,
            source_id=action_request.source_id,
            source_version_id=action_request.source_version_id,
            scene_id=action_request.scene_id,
            chapter_id=action_request.chapter_id,
            pov_character_id=action_request.pov_character_id,
            actor_intent=action_request.actor_intent,
            trigger=action_request.trigger,
            action_type=action_request.action_type,
            target=action_request.target,
            constraints=action_request.constraints,
            expected_output=action_request.expected_output,
            status=action_request.status,
            created_by=action_request.created_by,
        )

    def update_action_request_status(self, action_request_id: UUID, status: str) -> str | None:
        action_request = self._session.get(AgentActionRequestRecord, action_request_id)
        if action_request is None:
            return None
        action_request.status = status
        self._session.flush()
        return action_request.status

    def persist_failed_skill_run(self, input_data: PersistFailedSkillRunInput) -> None:
        self._session.add(
            SkillRun(
                id=uuid4(),
                project_id=input_data.project_id,
                skill_name=input_data.skill_name,
                skill_version=input_data.skill_version,
                input_schema_version=input_data.input_schema_version,
                output_schema_version=input_data.output_schema_version,
                prompt_version=input_data.prompt_version,
                input_hash=input_data.input_hash,
                structured_output=input_data.structured_output,
                validation_result=input_data.validation_result,
                status="failed_terminal",
            )
        )
        self._session.flush()

    def persist_action_request_run(
        self, input_data: PersistActionRequestRunInput
    ) -> RunActionRequestOutput:
        action_request = self._session.get(AgentActionRequestRecord, input_data.action_request_id)
        if action_request is None:
            raise RuntimeError("action request must be loaded before persisting run")

        if input_data.original_candidate_id is not None:
            original_candidate = self._session.get(
                AgentDraftCandidateRecord, input_data.original_candidate_id
            )
            if original_candidate is None or original_candidate.project_id != input_data.project_id:
                raise RuntimeError("original candidate must be loaded before persisting revision")
            original_candidate.status = "revised"
            original_candidate.author_action = "revise"

        skill_run_id = uuid4()
        self._session.add(
            SkillRun(
                id=skill_run_id,
                project_id=input_data.project_id,
                skill_name=input_data.skill_name,
                skill_version=input_data.skill_version,
                input_schema_version="story-draft-request.v1",
                output_schema_version="story-draft-result.v1",
                prompt_version=input_data.prompt_version,
                input_hash=input_data.input_hash,
                structured_output=input_data.structured_output,
                validation_result={"status": "valid"},
                status="succeeded",
            )
        )

        candidate_id = uuid4()
        candidate = AgentDraftCandidateRecord(
            id=candidate_id,
            project_id=input_data.project_id,
            action_request_id=input_data.action_request_id,
            mode=input_data.mode,
            candidate_text_ref=input_data.candidate_text_ref,
            context_pack_id=input_data.context_pack_id,
            target_source_id=input_data.target_source_id,
            target_version_id=input_data.target_version_id,
            target_scene_id=input_data.target_scene_id,
            affected_range=input_data.affected_range,
            base_hash=input_data.base_hash,
            memory_refs=input_data.memory_refs,
            evidence_refs=input_data.evidence_refs,
            status=input_data.candidate_status,
        )
        self._session.add(candidate)

        for control in input_data.controls:
            self._session.add(
                AgentStorytellingControlRecord(
                    id=uuid4(),
                    project_id=input_data.project_id,
                    action_request_id=input_data.action_request_id,
                    draft_candidate_id=candidate_id,
                    control_type=control.control_type,
                    schema_version=control.schema_version,
                    payload=control.payload,
                )
            )

        finding_ids: list[UUID] = []
        for finding in input_data.findings:
            finding_id = uuid4()
            finding_ids.append(finding_id)
            self._session.add(
                _agent_review_finding_record(finding_id, candidate_id, finding, input_data)
            )

        action_request.status = "succeeded"
        self._session.flush()
        return RunActionRequestOutput(
            action_request_id=input_data.action_request_id,
            status=action_request.status,
            output_type="draft_candidates",
            context_pack_id=input_data.context_pack_id,
            draft_candidate_ids=[candidate_id],
            risk_finding_ids=finding_ids,
            beat_candidate_ids=[],
        )

    def persist_action_request_beat_candidates(
        self, input_data: PersistActionRequestBeatCandidatesInput
    ) -> RunActionRequestOutput:
        action_request = self._session.get(AgentActionRequestRecord, input_data.action_request_id)
        if action_request is None:
            raise RuntimeError("action request must be loaded before persisting beat candidates")

        for control in input_data.controls:
            self._session.add(
                AgentStorytellingControlRecord(
                    id=uuid4(),
                    project_id=input_data.project_id,
                    action_request_id=input_data.action_request_id,
                    draft_candidate_id=None,
                    control_type=control.control_type,
                    schema_version=control.schema_version,
                    payload=control.payload,
                )
            )

        records: list[AgentBeatCandidateRecord] = []
        for beat in input_data.beat_candidates:
            record = AgentBeatCandidateRecord(
                id=uuid4(),
                project_id=input_data.project_id,
                action_request_id=input_data.action_request_id,
                context_pack_id=input_data.context_pack_id,
                target_source_id=input_data.target_source_id,
                target_version_id=input_data.target_version_id,
                target_scene_id=input_data.target_scene_id,
                affected_range=input_data.affected_range,
                base_hash=input_data.base_hash,
                summary=beat.summary,
                driver_character=beat.driver_character,
                agency_rationale=beat.agency_rationale,
                storytelling_rationale=beat.storytelling_rationale,
                cast_decision=beat.cast_decision,
                tension=beat.tension,
                memory_refs=beat.memory_refs,
                evidence_refs=beat.evidence_refs,
                status="suggested",
            )
            records.append(record)
            self._session.add(record)

        action_request.status = "succeeded"
        self._session.flush()
        return RunActionRequestOutput(
            action_request_id=input_data.action_request_id,
            status=action_request.status,
            output_type="beat_candidates",
            context_pack_id=input_data.context_pack_id,
            draft_candidate_ids=[],
            risk_finding_ids=[],
            beat_candidate_ids=[record.id for record in records],
            beat_candidates=[
                _beat_candidate_snapshot(self._session, input_data.project_id, record)
                for record in records
            ],
        )

    def persist_action_request_risk_findings(
        self, input_data: PersistActionRequestRiskFindingsInput
    ) -> RunActionRequestOutput:
        action_request = self._session.get(AgentActionRequestRecord, input_data.action_request_id)
        if action_request is None:
            raise RuntimeError("action request must be loaded before persisting risk findings")

        records: list[AgentReviewFindingRecord] = []
        for finding in input_data.findings:
            finding_id = uuid4()
            record = AgentReviewFindingRecord(
                id=finding_id,
                project_id=input_data.project_id,
                action_request_id=input_data.action_request_id,
                draft_candidate_id=None,
                risk_level=finding.risk_level,
                risk_type=finding.risk_type,
                summary=finding.summary,
                affected_text_ref=finding.affected_text_ref,
                memory_refs=finding.memory_refs,
                storytelling_refs=finding.storytelling_refs,
                suggested_revision=finding.suggested_revision,
                can_offer_to_author=finding.can_offer_to_author,
                maps_to_review_type_if_accepted=finding.maps_to_review_type_if_accepted,
                draft_local_only=True,
            )
            records.append(record)
            self._session.add(record)

        action_request.status = "succeeded"
        self._session.flush()
        return RunActionRequestOutput(
            action_request_id=input_data.action_request_id,
            status=action_request.status,
            output_type="risk_findings",
            context_pack_id=None,
            draft_candidate_ids=[],
            risk_finding_ids=[record.id for record in records],
            beat_candidate_ids=[],
            risk_findings=[
                _agent_review_finding_snapshot(self._session, input_data.project_id, record)
                for record in records
            ],
        )

    def load_candidate(self, candidate_id: UUID) -> CandidateSnapshot | None:
        candidate = self._session.get(AgentDraftCandidateRecord, candidate_id)
        if candidate is None:
            return None
        return CandidateSnapshot(
            id=candidate.id,
            project_id=candidate.project_id,
            status=candidate.status,
            target_source_id=candidate.target_source_id,
            target_version_id=candidate.target_version_id,
            affected_range=candidate.affected_range,
            base_hash=candidate.base_hash,
            override_reason=candidate.override_reason,
        )

    def load_candidate_detail(self, candidate_id: UUID) -> CandidateDetailSnapshot | None:
        candidate = self._session.get(AgentDraftCandidateRecord, candidate_id)
        if candidate is None:
            return None
        findings = (
            self._session.query(AgentReviewFindingRecord)
            .filter_by(draft_candidate_id=candidate_id)
            .all()
        )
        return CandidateDetailSnapshot(
            id=candidate.id,
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            mode=candidate.mode,
            candidate_text_ref=candidate.candidate_text_ref,
            context_pack_id=candidate.context_pack_id,
            target_source_id=candidate.target_source_id,
            target_version_id=candidate.target_version_id,
            target_scene_id=candidate.target_scene_id,
            affected_range=candidate.affected_range,
            base_hash=candidate.base_hash,
            memory_refs=_sanitized_agent_memory_refs(
                self._session, candidate.project_id, candidate.memory_refs
            ),
            evidence_refs=_valid_source_span_refs(
                self._session, candidate.project_id, candidate.evidence_refs
            ),
            status=candidate.status,
            override_reason=candidate.override_reason,
            agent_review_findings=[
                _agent_review_finding_snapshot(self._session, candidate.project_id, finding)
                for finding in findings
            ],
        )

    def persist_candidate_operation(
        self, input_data: CandidateOperationInput
    ) -> CandidateOperationOutput:
        candidate = self._session.get(AgentDraftCandidateRecord, input_data.candidate_id)
        if candidate is None:
            raise RuntimeError("candidate must be loaded before persisting operation")

        replacement_candidate_id: UUID | None = None
        if input_data.operation == "reject":
            candidate.status = "archived"
            candidate.author_action = "reject"
        elif input_data.operation == "override_block":
            candidate.override_reason = input_data.override_reason
            candidate.status = "offered_to_author"
            candidate.author_action = "override_block"
        elif input_data.operation == "revise":
            if input_data.revised_text_ref is None:
                raise RuntimeError("revised text must be stored before persisting revision")
            candidate.status = "revised"
            candidate.author_action = "revise"
            replacement_candidate_id = uuid4()
            self._session.add(
                AgentDraftCandidateRecord(
                    id=replacement_candidate_id,
                    project_id=candidate.project_id,
                    action_request_id=candidate.action_request_id,
                    mode=candidate.mode,
                    candidate_text_ref=input_data.revised_text_ref,
                    context_pack_id=candidate.context_pack_id,
                    selected_beat_id=candidate.selected_beat_id,
                    target_source_id=candidate.target_source_id,
                    target_version_id=candidate.target_version_id,
                    target_scene_id=candidate.target_scene_id,
                    affected_range=candidate.affected_range,
                    base_hash=candidate.base_hash,
                    memory_refs=candidate.memory_refs,
                    evidence_refs=candidate.evidence_refs,
                    status="offered_to_author",
                )
            )
        else:
            raise RuntimeError("unsupported candidate operation")

        self._session.flush()
        return CandidateOperationOutput(
            candidate_id=candidate.id,
            status=candidate.status,
            replacement_candidate_id=replacement_candidate_id,
            override_reason=candidate.override_reason,
        )

    def load_source_version(
        self, input_data: GetSourceVersionInput
    ) -> SourceVersionSnapshot | None:
        version = self._session.get(SourceVersion, input_data.version_id)
        if version is None or version.source_id != input_data.source_id:
            return None
        raw_source = self._session.get(RawSource, input_data.source_id)
        if raw_source is None or raw_source.project_id != input_data.project_id:
            return None
        return SourceVersionSnapshot(
            project_id=raw_source.project_id,
            source_id=raw_source.id,
            version_id=version.id,
            title=raw_source.title,
            source_type=raw_source.source_type,
            source_scope=raw_source.source_scope,
            raw_text_ref=version.raw_text_ref or raw_source.raw_text_ref,
            version_label=version.version_label,
            raw_hash=version.raw_hash,
        )

    def list_source_versions(
        self, input_data: ListSourceVersionsInput
    ) -> ListSourceVersionsOutput | None:
        raw_source = self._session.get(RawSource, input_data.source_id)
        if raw_source is None or raw_source.project_id != input_data.project_id:
            return None
        versions = (
            self._session.query(SourceVersion)
            .filter_by(source_id=input_data.source_id)
            .order_by(SourceVersion.created_at.desc(), SourceVersion.id.desc())
            .all()
        )
        versions = _sort_source_versions_by_chain(versions)
        versions = versions[: input_data.limit]
        return ListSourceVersionsOutput(
            items=[
                SourceVersionSummaryOutput(
                    source_id=raw_source.id,
                    version_id=version.id,
                    version_label=version.version_label,
                    raw_hash=version.raw_hash,
                    raw_text_ref=version.raw_text_ref or raw_source.raw_text_ref,
                    supersedes_version_id=version.supersedes_version_id,
                    created_at=version.created_at,
                )
                for version in versions
            ]
        )

    def list_sources(self, input_data: ListSourcesInput) -> ListSourcesOutput:
        source_query = self._session.query(RawSource).filter(
            RawSource.project_id == input_data.project_id
        )
        if not input_data.include_archived:
            source_query = source_query.filter(RawSource.archived_at.is_(None))
        sources = source_query.order_by(RawSource.created_at.desc()).all()
        query = input_data.query.casefold()
        if query:
            sources = [
                source
                for source in sources
                if query in source.title.casefold()
                or query in source.source_type.casefold()
                or query in source.source_scope.casefold()
            ]
        sources = sources[: input_data.limit]
        if not sources:
            return ListSourcesOutput(items=[])

        source_ids = [source.id for source in sources]
        versions = (
            self._session.query(SourceVersion)
            .filter(SourceVersion.source_id.in_(source_ids))
            .order_by(SourceVersion.created_at.desc())
            .all()
        )
        versions_by_source: dict[UUID, list[SourceVersion]] = {
            source_id: [] for source_id in source_ids
        }
        for version in versions:
            versions_by_source[version.source_id].append(version)

        return ListSourcesOutput(
            items=[_source_summary(source, versions_by_source[source.id]) for source in sources]
        )

    def get_source(self, input_data: GetSourceInput) -> SourceSummaryOutput | None:
        source = (
            self._session.query(RawSource)
            .filter_by(id=input_data.source_id, project_id=input_data.project_id)
            .one_or_none()
        )
        if source is None:
            return None
        versions = (
            self._session.query(SourceVersion)
            .filter_by(source_id=source.id)
            .order_by(SourceVersion.created_at.desc())
            .all()
        )
        return _source_summary(source, versions)

    def archive_source(self, input_data: ArchiveSourceInput) -> ArchiveSourceOutput | None:
        source = self._session.get(RawSource, input_data.source_id)
        if source is None or source.project_id != input_data.project_id:
            return None
        archived_at = source.archived_at
        if archived_at is None:
            archived_at = datetime.now(UTC)
            source.archived_at = archived_at
            source.archived_by = input_data.actor_id
        archived_by = source.archived_by or input_data.actor_id
        if source.archived_by is None:
            source.archived_by = archived_by
        self._session.flush()
        return ArchiveSourceOutput(
            source_id=source.id,
            status="archived",
            archived_at=archived_at,
            archived_by=archived_by,
        )

    def create_source(
        self, input_data: CreateSourceInput, raw_text_ref: str, raw_hash: str
    ) -> CreateSourceOutput:
        source_id = uuid4()
        version_id = uuid4()
        source_delta_id = uuid4()
        self._session.add(
            RawSource(
                id=source_id,
                project_id=input_data.project_id,
                source_type=input_data.source_type,
                source_scope=input_data.source_scope,
                title=input_data.title,
                ownership_status=input_data.ownership_status,
                raw_text_ref=raw_text_ref,
                created_by=input_data.actor_id,
            )
        )
        self._session.add(
            SourceVersion(
                id=version_id,
                source_id=source_id,
                version_label=input_data.version_label,
                raw_hash=raw_hash,
                raw_text_ref=raw_text_ref,
            )
        )
        self._session.flush()
        self._session.add(
            SourceDeltaRecord(
                id=source_delta_id,
                project_id=input_data.project_id,
                source_id=source_id,
                previous_version_id=None,
                new_version_id=version_id,
                accepted_fragment_id=None,
                delta_kind="insert",
                range_start=0,
                range_end=0,
                base_hash=None,
                submitted_text_ref=raw_text_ref,
                submitted_text_search=source_delta_search_text(input_data.text),
                source_type=input_data.source_type,
                source_scope=input_data.source_scope,
                provenance={
                    "created_by_api": True,
                    "imported_source": True,
                    "source_create_idempotency_key": input_data.idempotency_key,
                },
                status="memory_writeback_queued",
            )
        )
        job_id = _enqueue_source_delta_pipeline_jobs(
            self._session,
            project_id=input_data.project_id,
            source_delta_id=source_delta_id,
            source_version_id=version_id,
            source_type=input_data.source_type,
            trigger="source_import",
        )
        self._session.flush()
        return CreateSourceOutput(
            source_id=source_id,
            version_id=version_id,
            source_delta_id=source_delta_id,
            memory_writeback_job_id=job_id,
            raw_hash=raw_hash,
        )

    def create_source_version(
        self, input_data: CreateSourceVersionInput, raw_text_ref: str, raw_hash: str
    ) -> CreateSourceVersionOutput:
        source = self._session.get(RawSource, input_data.source_id)
        if source is None or source.project_id != input_data.project_id:
            raise RuntimeError("source must exist before creating SourceVersion")
        if input_data.supersedes_version_id is not None:
            superseded = self._session.get(SourceVersion, input_data.supersedes_version_id)
            if superseded is None or superseded.source_id != input_data.source_id:
                raise RuntimeError("superseded SourceVersion must belong to the source")
        version_id = uuid4()
        self._session.add(
            SourceVersion(
                id=version_id,
                source_id=input_data.source_id,
                version_label=input_data.version_label,
                raw_hash=raw_hash,
                raw_text_ref=raw_text_ref,
                supersedes_version_id=input_data.supersedes_version_id,
            )
        )
        self._session.flush()
        return CreateSourceVersionOutput(
            source_id=input_data.source_id,
            version_id=version_id,
            raw_hash=raw_hash,
            supersedes_version_id=input_data.supersedes_version_id,
        )

    def create_source_delta(
        self,
        input_data: CreateSourceDeltaInput,
        submitted_text_ref: str,
        materialized_text_ref: str,
        materialized_hash: str,
        materialized_version_label: str,
    ) -> CreateSourceDeltaOutput:
        source_delta_id = uuid4()
        new_version_id = uuid4()
        self._session.add(
            SourceVersion(
                id=new_version_id,
                source_id=input_data.source_id,
                version_label=materialized_version_label,
                raw_hash=materialized_hash,
                raw_text_ref=materialized_text_ref,
                supersedes_version_id=input_data.previous_version_id,
            )
        )
        self._session.flush()
        self._session.add(
            SourceDeltaRecord(
                id=source_delta_id,
                project_id=input_data.project_id,
                source_id=input_data.source_id,
                previous_version_id=input_data.previous_version_id,
                new_version_id=new_version_id,
                accepted_fragment_id=None,
                delta_kind=input_data.delta_kind,
                range_start=input_data.range_start,
                range_end=input_data.range_end,
                base_hash=input_data.base_hash,
                submitted_text_ref=submitted_text_ref,
                submitted_text_search=source_delta_search_text(input_data.submitted_text),
                source_type=input_data.source_type,
                source_scope=input_data.source_scope,
                provenance={
                    **input_data.provenance,
                    "created_by_api": True,
                },
                status="memory_writeback_queued",
            )
        )
        job_id = _enqueue_source_delta_pipeline_jobs(
            self._session,
            project_id=input_data.project_id,
            source_delta_id=source_delta_id,
            source_version_id=new_version_id,
            source_type=input_data.source_type,
            trigger="source_delta",
        )
        self._session.flush()
        return CreateSourceDeltaOutput(
            source_delta_id=source_delta_id,
            new_version_id=new_version_id,
            memory_writeback_job_id=job_id,
        )

    def source_version_hash(self, version_id: UUID) -> str | None:
        version = self._session.get(SourceVersion, version_id)
        if version is None:
            return None
        return version.raw_hash

    def source_in_project(self, project_id: UUID, source_id: UUID) -> bool:
        source = self._session.get(RawSource, source_id)
        return source is not None and source.project_id == project_id

    def persist_candidate_acceptance(
        self,
        input_data: AcceptCandidateInput,
        materialized_text_ref: str,
        materialized_hash: str,
        materialized_version_label: str,
    ) -> AcceptCandidateOutput:
        candidate = self._session.get(AgentDraftCandidateRecord, input_data.candidate_id)
        if candidate is None:
            raise RuntimeError("candidate must be loaded before persisting acceptance")
        if input_data.accepted_text_ref is None:
            raise RuntimeError("accepted text must be stored before persisting acceptance")

        accepted_fragment_id = uuid4()
        source_delta_id = uuid4()
        new_version_id = uuid4()
        memory_writeback_job_id = uuid4()
        selected_range = input_data.insert_or_replace_range
        if input_data.target_source_id is None or input_data.target_version_id is None:
            raise RuntimeError("candidate acceptance requires target source and version")
        target_source_id = input_data.target_source_id
        target_version_id = input_data.target_version_id
        source_version = SourceVersion(
            id=new_version_id,
            source_id=target_source_id,
            version_label=materialized_version_label,
            raw_hash=materialized_hash,
            raw_text_ref=materialized_text_ref,
            supersedes_version_id=target_version_id,
        )
        accepted_fragment = AcceptedFragmentRecord(
            id=accepted_fragment_id,
            project_id=input_data.project_id,
            candidate_id=input_data.candidate_id,
            target_source_id=target_source_id,
            target_version_id=target_version_id,
            accepted_text_ref=input_data.accepted_text_ref,
            range_start=selected_range["start"],
            range_end=selected_range["end"],
            source_type=input_data.source_type,
            source_scope=input_data.source_scope,
            author_edited=input_data.author_edited,
            accepted_by=input_data.actor_id,
        )
        provenance: dict[str, object] = {
            "generated_by_agent": True,
            "draft_candidate_id": str(input_data.candidate_id),
            "author_edited": input_data.author_edited,
            "accept_mode": input_data.accept_mode,
        }
        if candidate.override_reason:
            provenance["override_reason"] = candidate.override_reason
        source_delta = SourceDeltaRecord(
            id=source_delta_id,
            project_id=input_data.project_id,
            source_id=target_source_id,
            previous_version_id=target_version_id,
            new_version_id=new_version_id,
            accepted_fragment_id=accepted_fragment_id,
            delta_kind="replace",
            range_start=selected_range["start"],
            range_end=selected_range["end"],
            base_hash=candidate.base_hash,
            submitted_text_ref=input_data.accepted_text_ref,
            submitted_text_search=source_delta_search_text(input_data.accepted_text or ""),
            source_type=input_data.source_type,
            source_scope=input_data.source_scope,
            provenance=provenance,
            status="memory_writeback_queued",
        )
        memory_writeback_job_id = _enqueue_source_delta_pipeline_jobs(
            self._session,
            project_id=input_data.project_id,
            source_delta_id=source_delta_id,
            source_version_id=new_version_id,
            source_type=input_data.source_type,
            trigger="candidate_acceptance",
            memory_writeback_job_id=memory_writeback_job_id,
        )
        candidate.status = "converted_to_source_delta"
        candidate.author_action = (
            "accept_partial" if input_data.accept_mode == "partial" else "accept"
        )
        candidate.accepted_text_ref = input_data.accepted_text_ref
        self._session.add_all([source_version, accepted_fragment])
        self._session.flush()
        self._session.add(source_delta)
        self._session.flush()
        return AcceptCandidateOutput(
            accepted_fragment_id=accepted_fragment_id,
            source_delta_id=source_delta_id,
            new_version_id=new_version_id,
            memory_writeback_job_id=memory_writeback_job_id,
        )

    def load_review_item(self, review_item_id: UUID) -> ReviewItemSnapshot | None:
        review_item = self._session.get(ReviewItemRecord, review_item_id)
        if review_item is None:
            return None
        return ReviewItemSnapshot(
            id=review_item.id,
            project_id=review_item.project_id,
            review_type=review_item.review_type,
            affected_refs=review_item.affected_refs,
            new_evidence=review_item.new_evidence,
            status=review_item.status,
            resolution=review_item.resolution,
            side_effects=review_item.side_effects,
        )

    def alias_correction_target_exists(
        self,
        project_id: UUID,
        alias_record_id: UUID,
        target_entity_id: UUID,
        boundary_scene_refs: dict[str, UUID | None] | None = None,
    ) -> bool:
        alias = self._session.get(StoryAliasRecord, alias_record_id)
        target_entity = self._session.get(StoryCanonicalEntity, target_entity_id)
        if (
            alias is None
            or target_entity is None
            or alias.project_id != project_id
            or target_entity.project_id != project_id
        ):
            return False
        return self._alias_correction_boundary_refs_valid(
            project_id,
            alias,
            boundary_scene_refs or {},
        )

    def _alias_correction_boundary_refs_valid(
        self,
        project_id: UUID,
        alias: StoryAliasRecord,
        boundary_scene_refs: dict[str, UUID | None],
    ) -> bool:
        if not boundary_scene_refs:
            return True

        valid_from_scene_id = alias.valid_from_scene_id
        valid_until_scene_id = alias.valid_until_scene_id
        if "valid_from_scene_id" in boundary_scene_refs:
            valid_from_scene_id = boundary_scene_refs["valid_from_scene_id"]
        if "valid_until_scene_id" in boundary_scene_refs:
            valid_until_scene_id = boundary_scene_refs["valid_until_scene_id"]

        start_key = _memory_answer_alias_boundary_scene_key(
            self._session,
            project_id,
            valid_from_scene_id,
        )
        end_key = _memory_answer_alias_boundary_scene_key(
            self._session,
            project_id,
            valid_until_scene_id,
        )
        if valid_from_scene_id is not None and start_key is None:
            return False
        if valid_until_scene_id is not None and end_key is None:
            return False
        return not (start_key is not None and end_key is not None and start_key > end_key)

    def source_deltas_exist(self, project_id: UUID, source_delta_ids: list[UUID]) -> bool:
        expected_ids = set(source_delta_ids)
        if not expected_ids:
            return True
        existing_ids = set(
            self._session.scalars(
                select(SourceDeltaRecord.id)
                .where(SourceDeltaRecord.project_id == project_id)
                .where(SourceDeltaRecord.id.in_(expected_ids))
            ).all()
        )
        return existing_ids == expected_ids

    def source_deltas_have_source_scopes(
        self,
        project_id: UUID,
        source_delta_ids: list[UUID],
        allowed_source_scopes: set[str],
    ) -> bool:
        expected_ids = set(source_delta_ids)
        if not expected_ids:
            return True
        scoped_ids = set(
            self._session.scalars(
                select(SourceDeltaRecord.id)
                .where(SourceDeltaRecord.project_id == project_id)
                .where(SourceDeltaRecord.id.in_(expected_ids))
                .where(SourceDeltaRecord.source_scope.in_(allowed_source_scopes))
            ).all()
        )
        return scoped_ids == expected_ids

    def review_replacement_refs_exist(
        self, project_id: UUID, refs_by_type: dict[str, list[UUID]]
    ) -> bool:
        source_delta_ids = refs_by_type.get("source_delta", [])
        if source_delta_ids and not self.source_deltas_exist(project_id, source_delta_ids):
            return False

        review_item_ids = refs_by_type.get("review_item", [])
        if review_item_ids:
            expected_review_ids = set(review_item_ids)
            existing_review_ids = set(
                self._session.scalars(
                    select(ReviewItemRecord.id)
                    .where(ReviewItemRecord.project_id == project_id)
                    .where(ReviewItemRecord.id.in_(expected_review_ids))
                ).all()
            )
            if existing_review_ids != expected_review_ids:
                return False

        source_span_ids = refs_by_type.get("source_span", [])
        if source_span_ids:
            expected_span_ids = set(source_span_ids)
            existing_span_ids = set(
                self._session.scalars(
                    select(SourceSpan.id)
                    .join(RawSource, SourceSpan.source_id == RawSource.id)
                    .where(RawSource.project_id == project_id)
                    .where(SourceSpan.id.in_(expected_span_ids))
                ).all()
            )
            if existing_span_ids != expected_span_ids:
                return False

        return True

    def get_job_detail(self, input_data: JobDetailInput) -> JobDetailOutput | None:
        job = self._session.get(JobRecord, input_data.job_id)
        if job is None or job.project_id != input_data.project_id:
            return None
        return _job_detail(job)

    def operate_job(self, input_data: JobOperationInput) -> JobDetailOutput | None:
        job = self._session.get(JobRecord, input_data.job_id)
        if job is None or job.project_id != input_data.project_id:
            return None
        if input_data.operation == "cancel":
            job.status = "cancelled"
            job.run_after = None
            job.locked_by = None
            job.locked_at = None
            job.last_error = None
        elif input_data.operation == "retry":
            job.status = "queued"
            job.run_after = None
            job.locked_by = None
            job.locked_at = None
            job.last_error = None
        else:
            raise RuntimeError(f"Unsupported job operation: {input_data.operation}")
        self._session.flush()
        return _job_detail(job)

    def list_source_deltas(self, input_data: ListSourceDeltasInput) -> list[SourceDeltaSnapshot]:
        query = self._session.query(SourceDeltaRecord).filter_by(project_id=input_data.project_id)
        if input_data.source_id is not None:
            query = query.filter_by(source_id=input_data.source_id)
        if input_data.source_version_id is not None:
            query = query.filter(
                or_(
                    SourceDeltaRecord.previous_version_id == input_data.source_version_id,
                    SourceDeltaRecord.new_version_id == input_data.source_version_id,
                )
            )
        if input_data.status is not None:
            query = query.filter_by(status=input_data.status)
        if input_data.delta_kind is not None:
            query = query.filter_by(delta_kind=input_data.delta_kind)
        if input_data.accepted_only:
            query = query.filter(SourceDeltaRecord.accepted_fragment_id.is_not(None))
        search_query = source_delta_search_text(input_data.query or "")
        if search_query:
            query = query.filter(
                func.lower(SourceDeltaRecord.submitted_text_search).like(
                    f"%{_escape_like(search_query)}%",
                    escape="\\",
                )
            )
        if input_data.after_created_at is not None and input_data.after_id is not None:
            query = query.filter(
                or_(
                    SourceDeltaRecord.created_at < input_data.after_created_at,
                    and_(
                        SourceDeltaRecord.created_at == input_data.after_created_at,
                        SourceDeltaRecord.id < input_data.after_id,
                    ),
                )
            )
        limit = max(1, min(input_data.limit + 1, 101))
        deltas = query.order_by(
            SourceDeltaRecord.created_at.desc(), SourceDeltaRecord.id.desc()
        ).limit(limit)
        return [_source_delta_snapshot(self._session, delta) for delta in deltas]

    def get_source_delta_detail(
        self, input_data: SourceDeltaDetailInput
    ) -> SourceDeltaSnapshot | None:
        delta = self._session.get(SourceDeltaRecord, input_data.source_delta_id)
        if delta is None or delta.project_id != input_data.project_id:
            return None
        return _source_delta_snapshot(self._session, delta)

    def list_review_items(self, input_data: ListReviewItemsInput) -> ListReviewItemsOutput:
        query = self._session.query(ReviewItemRecord).filter_by(project_id=input_data.project_id)
        if input_data.status is not None:
            query = query.filter_by(status=input_data.status)
        items = query.order_by(ReviewItemRecord.created_at, ReviewItemRecord.id).all()
        return ListReviewItemsOutput(
            items=[
                detail
                for item in items
                if (detail := _review_detail(self._session, item)) is not None
            ]
        )

    def get_review_item_detail(
        self, input_data: ReviewItemDetailInput
    ) -> ReviewItemDetailOutput | None:
        review_item = self._session.get(ReviewItemRecord, input_data.review_item_id)
        if review_item is None or review_item.project_id != input_data.project_id:
            return None
        return _review_detail(self._session, review_item)

    def list_canonical_entities(
        self, input_data: ListCanonicalEntitiesInput
    ) -> ListCanonicalEntitiesOutput:
        query = self._session.query(StoryCanonicalEntity).filter_by(
            project_id=input_data.project_id
        )
        if input_data.entity_type is not None:
            query = query.filter_by(entity_type=input_data.entity_type)
        if input_data.query is not None and input_data.query.strip():
            pattern = f"%{_escape_like(input_data.query.strip().casefold())}%"
            alias_entity_ids = (
                select(StoryAliasRecord.entity_id)
                .where(StoryAliasRecord.project_id == input_data.project_id)
                .where(StoryAliasRecord.entity_id.is_not(None))
                .where(func.lower(StoryAliasRecord.alias_text).like(pattern, escape="\\"))
            )
            query = query.filter(
                or_(
                    func.lower(StoryCanonicalEntity.display_name).like(pattern, escape="\\"),
                    StoryCanonicalEntity.id.in_(alias_entity_ids),
                )
            )
        limit = max(1, min(input_data.limit, 50))
        entities = (
            query.order_by(StoryCanonicalEntity.display_name, StoryCanonicalEntity.id)
            .limit(limit)
            .all()
        )
        return ListCanonicalEntitiesOutput(
            items=[_canonical_entity_summary(entity) for entity in entities]
        )

    def list_story_scenes(self, input_data: ListStoryScenesInput) -> ListStoryScenesOutput:
        query = (
            self._session.query(
                StoryScene,
                StoryChapter,
                SourceProcessedView,
                SourceVersion,
                RawSource,
            )
            .join(StoryChapter, StoryScene.chapter_id == StoryChapter.id)
            .join(SourceProcessedView, StoryChapter.view_id == SourceProcessedView.id)
            .join(SourceVersion, SourceProcessedView.version_id == SourceVersion.id)
            .join(RawSource, SourceVersion.source_id == RawSource.id)
            .filter(RawSource.project_id == input_data.project_id)
        )
        if input_data.source_id is not None:
            query = query.filter(RawSource.id == input_data.source_id)
        if input_data.version_id is not None:
            query = query.filter(SourceVersion.id == input_data.version_id)
        limit = max(1, min(input_data.limit, 200))
        rows = (
            query.order_by(
                StoryChapter.chapter_index,
                StoryScene.scene_index,
                StoryScene.start_offset,
                StoryScene.id,
            )
            .limit(limit)
            .all()
        )
        return ListStoryScenesOutput(
            items=[
                _story_scene_summary(scene, chapter, version, source)
                for scene, chapter, _view, version, source in rows
            ]
        )

    def get_project_story_schema(
        self, input_data: GetProjectStorySchemaInput
    ) -> ProjectStorySchemaOutput:
        return _project_story_schema_output(self._session, input_data.project_id)

    def list_story_schema_packs(
        self, input_data: ListStorySchemaPacksInput
    ) -> ListStorySchemaPacksOutput:
        query = self._session.query(StorySchemaPackRecord).filter(
            StorySchemaPackRecord.status == "active"
        )
        if input_data.pack_type is None:
            query = query.filter(StorySchemaPackRecord.project_id.is_(None))
        elif input_data.pack_type == "project_override":
            query = query.filter(
                StorySchemaPackRecord.project_id == input_data.project_id,
                StorySchemaPackRecord.pack_type == input_data.pack_type,
            )
        else:
            query = query.filter(
                StorySchemaPackRecord.project_id.is_(None),
                StorySchemaPackRecord.pack_type == input_data.pack_type,
            )
        packs = query.order_by(
            StorySchemaPackRecord.pack_type,
            StorySchemaPackRecord.pack_name,
            StorySchemaPackRecord.version,
        ).all()
        return ListStorySchemaPacksOutput(items=[_story_schema_pack_output(pack) for pack in packs])

    def create_story_schema_genre_pack(
        self, input_data: CreateStorySchemaGenrePackInput
    ) -> StorySchemaPackOutput | None:
        if self._session.get(Project, input_data.project_id) is None:
            return None
        existing = (
            self._session.query(StorySchemaPackRecord)
            .filter_by(
                project_id=None,
                pack_type="genre",
                pack_name=input_data.pack_name.strip(),
                version=input_data.version.strip(),
            )
            .one_or_none()
        )
        if existing is not None:
            return None
        pack = StorySchemaPackRecord(
            id=uuid4(),
            project_id=None,
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
        self._session.add(pack)
        self._session.flush()
        return _story_schema_pack_output(pack)

    def deprecate_story_schema_genre_pack(
        self, input_data: DeprecateStorySchemaGenrePackInput
    ) -> StorySchemaPackOutput | None:
        if self._session.get(Project, input_data.project_id) is None:
            return None
        pack = self._session.get(StorySchemaPackRecord, input_data.story_schema_pack_id)
        if pack is None or pack.project_id is not None or pack.pack_type != "genre":
            return None
        in_use = (
            self._session.query(ProjectStorySchemaBinding)
            .filter_by(genre_schema_pack_id=pack.id, status="active")
            .first()
            is not None
        )
        if in_use:
            return None
        if pack.status != "deprecated":
            pack.status = "deprecated"
            self._session.flush()
        return _story_schema_pack_output(pack)

    def select_project_story_schema_genre(
        self, input_data: SelectProjectStorySchemaGenreInput
    ) -> ProjectStorySchemaOutput | None:
        active_binding = _active_project_story_schema_binding(self._session, input_data.project_id)
        if active_binding is None and input_data.genre_schema_pack_id is None:
            return _project_story_schema_output(self._session, input_data.project_id)
        if (
            active_binding is not None
            and active_binding.genre_schema_pack_id == input_data.genre_schema_pack_id
        ):
            return _project_story_schema_output(self._session, input_data.project_id)

        genre_pack = None
        if input_data.genre_schema_pack_id is not None:
            genre_pack = self._session.get(StorySchemaPackRecord, input_data.genre_schema_pack_id)
            if (
                genre_pack is None
                or genre_pack.project_id is not None
                or genre_pack.pack_type != "genre"
                or genre_pack.status != "active"
            ):
                return None

        base_pack = _get_or_create_base_story_schema_pack(self._session)
        for binding in (
            self._session.query(ProjectStorySchemaBinding)
            .filter_by(project_id=input_data.project_id, status="active")
            .all()
        ):
            binding.status = "superseded"
        self._session.flush()

        binding = ProjectStorySchemaBinding(
            id=uuid4(),
            project_id=input_data.project_id,
            base_schema_pack_id=base_pack.id,
            genre_schema_pack_id=genre_pack.id if genre_pack is not None else None,
            project_override_pack_id=active_binding.project_override_pack_id
            if active_binding is not None
            else None,
            status="active",
            created_by=input_data.actor_id,
        )
        self._session.add(binding)
        self._session.flush()
        return _project_story_schema_output(self._session, input_data.project_id)

    def upsert_project_story_schema_override(
        self, input_data: UpsertProjectStorySchemaOverrideInput
    ) -> ProjectStorySchemaOutput:
        active_binding = _active_project_story_schema_binding(self._session, input_data.project_id)
        base_pack = _get_or_create_base_story_schema_pack(self._session)
        for binding in (
            self._session.query(ProjectStorySchemaBinding)
            .filter_by(project_id=input_data.project_id, status="active")
            .all()
        ):
            binding.status = "superseded"
        self._session.flush()

        override_pack = StorySchemaPackRecord(
            id=uuid4(),
            project_id=input_data.project_id,
            pack_type="project_override",
            pack_name=input_data.pack_name.strip(),
            version=f"project-override.{uuid4()}",
            status="active",
            entity_types=input_data.entity_types,
            event_types=input_data.event_types,
            relations=input_data.relations,
            extraction_hints=input_data.extraction_hints,
            risk_rules=input_data.risk_rules,
        )
        binding = ProjectStorySchemaBinding(
            id=uuid4(),
            project_id=input_data.project_id,
            base_schema_pack_id=base_pack.id,
            genre_schema_pack_id=active_binding.genre_schema_pack_id
            if active_binding is not None
            else None,
            project_override_pack_id=override_pack.id,
            status="active",
            created_by=input_data.actor_id,
        )
        self._session.add_all([override_pack, binding])
        self._session.flush()
        return _project_story_schema_output(self._session, input_data.project_id)

    def list_memory_pages(self, input_data: ListMemoryPagesInput) -> ListMemoryPagesOutput:
        query = self._session.query(MemoryPage).filter_by(project_id=input_data.project_id)
        if input_data.page_type is not None:
            query = query.filter_by(page_type=input_data.page_type)
        if input_data.canon_status is not None:
            query = query.filter_by(canon_status=input_data.canon_status)
        pages = (
            query.order_by(MemoryPage.title, MemoryPage.id)
            .limit(max(1, min(input_data.limit, 100)))
            .all()
        )
        return ListMemoryPagesOutput(
            items=[_memory_page_summary(self._session, page) for page in pages]
        )

    def get_memory_page_detail(
        self, input_data: MemoryPageDetailInput
    ) -> MemoryPageDetailOutput | None:
        page = self._session.get(MemoryPage, input_data.memory_page_id)
        if page is None or page.project_id != input_data.project_id:
            return None
        return _memory_page_detail(self._session, page)

    def persist_memory_page_thread_operation(
        self, input_data: MemoryPageThreadOperationInput
    ) -> MemoryPageThreadOperationOutput:
        page = self._session.get(MemoryPage, input_data.memory_page_id)
        if page is None or page.project_id != input_data.project_id:
            raise RuntimeError("MemoryPage was not found.")

        thread_id = input_data.thread_id.strip()
        threads = [dict(thread) for thread in page.open_threads]
        target_index = next(
            (
                index
                for index, thread in enumerate(threads)
                if str(thread.get("id") or "").strip() == thread_id
            ),
            None,
        )
        if target_index is None:
            raise RuntimeError("MemoryPage open thread was not found.")

        current_thread = dict(threads[target_index])
        raw_source_span_ids = current_thread.get("source_span_ids", [])
        source_span_values = raw_source_span_ids if isinstance(raw_source_span_ids, list) else []
        valid_span_ids = [
            str(span_id)
            for span_id in _source_span_ids_to_uuids(
                self._session,
                input_data.project_id,
                {str(span_id) for span_id in source_span_values},
            )
        ]
        if not valid_span_ids:
            raise RuntimeError("MemoryPage open thread has no valid SourceSpan evidence.")

        status = _thread_update_review_status(input_data.update_type)
        updated_thread = {
            **current_thread,
            "id": thread_id,
            "update_type": input_data.update_type,
            "status": status,
            "source_span_ids": valid_span_ids,
            "author_note": input_data.author_note.strip(),
            "updated_by": str(input_data.actor_id),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if input_data.summary is not None:
            updated_thread["summary"] = input_data.summary.strip()

        threads[target_index] = updated_thread
        page.open_threads = threads
        page.source_refs = _sanitized_memory_page_source_refs(
            self._session,
            input_data.project_id,
            list(page.source_refs)
            + [{"type": "source_span", "id": span_id} for span_id in valid_span_ids],
        )
        evidence = _ensure_thread_update_applied_evidence(
            self._session,
            project_id=input_data.project_id,
            page_id=page.id,
            thread_id=thread_id,
            source_span_ids=valid_span_ids,
        )
        readiness_records = [
            mark_context_pack_readiness(
                self._session,
                project_id=input_data.project_id,
                source_span_id=span_id,
                affected_refs=[
                    {"type": "memory_page", "id": str(page.id)},
                    {
                        "type": "memory_page_thread",
                        "id": thread_id,
                        "memory_page_id": str(page.id),
                    },
                    {"type": "evidence_log_entry", "id": str(evidence.id)},
                ],
                reason="review_dependency_changed",
                status="stale",
            )
            for span_id in _source_span_ids_to_uuids(
                self._session,
                input_data.project_id,
                set(valid_span_ids),
            )
        ]
        self._session.flush()

        side_effects: dict[str, object] = {
            "memory_pages": "thread_update_applied",
            "memory_page_ids": [str(page.id)],
            "thread_update_id": thread_id,
            "source_span_ids": valid_span_ids,
            "evidence_log_entry_ids": [str(evidence.id)],
            "context_pack_readiness": "marked_stale",
            "context_pack_readiness_marked": len(readiness_records),
            "context_pack_readiness_ids": [str(record.id) for record in readiness_records],
            "graph_projection": "unchanged",
            "policy_action": "memory_page_thread_author_updated",
        }
        return MemoryPageThreadOperationOutput(
            memory_page_id=page.id,
            thread_id=thread_id,
            status=status,
            update_type=input_data.update_type,
            memory_page=_memory_page_detail(self._session, page),
            side_effects=side_effects,
        )

    def list_graph_projection_edges(
        self, input_data: ListGraphProjectionEdgesInput
    ) -> ListGraphProjectionEdgesOutput:
        query = self._session.query(GraphProjectionEdge).filter_by(project_id=input_data.project_id)
        if input_data.relation is not None:
            query = query.filter_by(relation=input_data.relation)
        if input_data.edge_status is not None:
            query = query.filter_by(edge_status=input_data.edge_status)
        search_query = (input_data.query or "").strip().casefold()
        if search_query:
            pattern = f"%{_escape_like(search_query)}%"
            query = query.filter(
                or_(
                    func.lower(GraphProjectionEdge.relation).like(pattern, escape="\\"),
                    func.lower(GraphProjectionEdge.edge_status).like(pattern, escape="\\"),
                    func.lower(sql_cast(GraphProjectionEdge.source_ref, String)).like(
                        pattern, escape="\\"
                    ),
                    func.lower(sql_cast(GraphProjectionEdge.subject_ref, String)).like(
                        pattern, escape="\\"
                    ),
                    func.lower(sql_cast(GraphProjectionEdge.target_ref, String)).like(
                        pattern, escape="\\"
                    ),
                    func.lower(sql_cast(GraphProjectionEdge.evidence_refs, String)).like(
                        pattern, escape="\\"
                    ),
                )
            )
        edges = (
            query.order_by(GraphProjectionEdge.created_at.desc(), GraphProjectionEdge.id.desc())
            .limit(max(1, min(input_data.limit, 100)))
            .all()
        )
        summaries: list[GraphProjectionEdgeSummaryOutput] = []
        for edge in edges:
            summary = _graph_projection_edge_summary(
                self._session,
                input_data.project_id,
                edge,
            )
            if summary is not None:
                summaries.append(summary)
        return ListGraphProjectionEdgesOutput(items=summaries)

    def memory_writeback_preview(
        self, input_data: MemoryWritebackPreviewInput
    ) -> MemoryWritebackPreviewOutput | None:
        delta = self._session.get(SourceDeltaRecord, input_data.source_delta_id)
        if delta is None or delta.project_id != input_data.project_id:
            return None

        job = _job_for_source_delta(
            self._session, project_id=input_data.project_id, source_delta_id=delta.id
        )
        source_span_ids = _source_span_ids_for_delta(
            self._session, project_id=input_data.project_id, source_delta_id=delta.id
        )
        spans = _spans_for_ids(self._session, source_span_ids)
        evidence_entries = _evidence_entries_for_spans(
            self._session, project_id=input_data.project_id, span_ids=source_span_ids
        )
        fact_assertions = _facts_for_spans(
            self._session, project_id=input_data.project_id, span_ids=source_span_ids
        )
        review_items = _reviews_for_spans(
            self._session, project_id=input_data.project_id, span_ids=source_span_ids
        )
        memory_pages = _memory_pages_for_delta(
            self._session, project_id=input_data.project_id, source_delta_id=delta.id
        )
        graph_edges = _graph_edges_for_spans(
            self._session, project_id=input_data.project_id, span_ids=source_span_ids
        )

        return MemoryWritebackPreviewOutput(
            source_delta_id=delta.id,
            source_delta_status=delta.status,
            source_delta={
                "source_id": str(delta.source_id),
                "previous_version_id": str(delta.previous_version_id)
                if delta.previous_version_id
                else None,
                "new_version_id": str(delta.new_version_id) if delta.new_version_id else None,
                "accepted_fragment_id": str(delta.accepted_fragment_id)
                if delta.accepted_fragment_id
                else None,
                "delta_kind": delta.delta_kind,
                "range": {"start": delta.range_start, "end": delta.range_end},
                "base_hash": delta.base_hash,
                "source_type": delta.source_type,
                "source_scope": delta.source_scope,
                "provenance": delta.provenance,
            },
            job=_job_detail(job) if job is not None else None,
            source_spans=[_source_span_entry(span) for span in spans],
            evidence_log_entries=[_evidence_entry(entry) for entry in evidence_entries],
            fact_assertions=[_fact_entry(fact) for fact in fact_assertions],
            review_items=[
                detail
                for review in review_items
                if (detail := _review_detail(self._session, review)) is not None
            ],
            memory_pages=[_memory_page_entry(self._session, page) for page in memory_pages],
            graph_edges=[
                entry
                for edge in graph_edges
                if (
                    entry := _graph_edge_entry(
                        self._session,
                        input_data.project_id,
                        edge,
                    )
                )
                is not None
            ],
        )

    def persist_memory_writeback_decision(
        self, input_data: MemoryWritebackDecisionInput
    ) -> MemoryWritebackDecisionOutput:
        decision_id = uuid4()
        side_effects = self._apply_memory_writeback_decision_side_effects(input_data)
        self._mark_memory_writeback_context_readiness(
            input_data,
            decision_id=decision_id,
            side_effects=side_effects,
        )
        record = MemoryWritebackDecisionRecord(
            id=decision_id,
            project_id=input_data.project_id,
            source_delta_id=input_data.source_delta_id,
            item_ref=input_data.item_ref,
            decision=input_data.decision,
            correction=input_data.correction or {},
            replacement_refs=input_data.replacement_refs or [],
            author_note=input_data.author_note,
            side_effects=side_effects,
            decided_by=input_data.actor_id,
        )
        self._session.add(record)
        self._session.flush()
        return MemoryWritebackDecisionOutput(
            decision_id=decision_id,
            source_delta_id=input_data.source_delta_id,
            item_ref=input_data.item_ref,
            decision=input_data.decision,
            status="recorded",
            side_effects=side_effects,
        )

    def _apply_memory_writeback_decision_side_effects(
        self, input_data: MemoryWritebackDecisionInput
    ) -> dict[str, object]:
        side_effects: dict[str, object] = {
            "memory_pages": "unchanged_pending_rewrite",
            "memory_pages_marked_stale": 0,
            "memory_page_rewrite_job_ids": [],
            "graph_edges_marked_disputed": 0,
            "replacement_refs": input_data.replacement_refs or [],
        }
        if input_data.item_ref.get("type") == "review_item":
            return self._apply_review_item_preview_decision(input_data, side_effects)
        if input_data.item_ref.get("type") == "source_span":
            return self._apply_source_span_preview_decision(input_data, side_effects)
        if input_data.item_ref.get("type") == "evidence_log_entry":
            return self._apply_evidence_log_preview_decision(input_data, side_effects)
        if input_data.item_ref.get("type") == "memory_page":
            return self._apply_memory_page_preview_decision(input_data, side_effects)
        if input_data.item_ref.get("type") == "graph_edge":
            return self._apply_graph_edge_preview_decision(input_data, side_effects)
        if input_data.item_ref.get("type") != "fact_assertion":
            return side_effects

        fact_id = input_data.item_ref.get("id")
        if fact_id is None:
            return side_effects
        fact = self._session.get(FactAssertionRecord, UUID(str(fact_id)))
        if fact is None or fact.project_id != input_data.project_id:
            return side_effects
        if input_data.decision == "accept":
            return self._apply_fact_accept_decision(input_data, fact, side_effects)

        return self._apply_fact_dispute_decision(input_data, [fact], side_effects)

    def _mark_memory_writeback_context_readiness(
        self,
        input_data: MemoryWritebackDecisionInput,
        *,
        decision_id: UUID,
        side_effects: dict[str, object],
    ) -> None:
        if not _memory_writeback_decision_changes_context(input_data, side_effects):
            return
        source_span_ids = _source_span_ids_for_writeback_decision(
            self._session,
            project_id=input_data.project_id,
            item_ref=input_data.item_ref,
            side_effects=side_effects,
        )
        if not source_span_ids:
            return

        affected_refs = _unique_refs(
            [
                {"type": "memory_writeback_decision", "id": str(decision_id)},
                {"type": "source_delta", "id": str(input_data.source_delta_id)},
                input_data.item_ref,
            ]
            + _side_effect_affected_refs(side_effects)
            + (input_data.replacement_refs or [])
        )
        records = [
            mark_context_pack_readiness(
                self._session,
                project_id=input_data.project_id,
                source_span_id=span_id,
                source_delta_id=input_data.source_delta_id,
                affected_refs=affected_refs,
                reason="review_dependency_changed",
                status="stale",
            )
            for span_id in source_span_ids
        ]
        side_effects["context_pack_readiness"] = "marked_stale"
        side_effects["context_pack_readiness_marked"] = len(records)
        side_effects["context_pack_readiness_ids"] = [str(record.id) for record in records]

    def _apply_fact_dispute_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        facts: list[FactAssertionRecord],
        side_effects: dict[str, object],
        *,
        evidence_span_ids: set[str] | None = None,
    ) -> dict[str, object]:
        fact_ids = {fact.id for fact in facts if fact.project_id == input_data.project_id}
        for fact in facts:
            if fact.id in fact_ids:
                fact.fact_status = "disputed"
        if len(fact_ids) == 1 and input_data.item_ref.get("type") == "fact_assertion":
            side_effects["fact_assertion_status"] = "disputed"
        side_effects["fact_assertions_marked_disputed"] = len(fact_ids)
        marked_pages = 0
        marked_page_ids: list[str] = []
        rewrite_job_ids: list[str] = []
        contradiction_source_span_ids = _fact_dispute_source_span_ids(
            self._session,
            input_data.project_id,
            facts,
            evidence_span_ids,
        )
        memory_pages = (
            self._session.query(MemoryPage).filter_by(project_id=input_data.project_id).all()
        )
        for page in memory_pages:
            facts = page.current_canon.get("facts", [])
            page_fact_ids = {
                str(entry.get("fact_id")) for entry in facts if isinstance(entry, dict)
            }
            if not page_fact_ids.intersection(str(fact_id) for fact_id in fact_ids):
                continue
            page.canon_status = "stale"
            contradiction_entry: dict[str, object] = {
                "type": "memory_writeback_decision",
                "source_delta_id": str(input_data.source_delta_id),
                "item_ref": input_data.item_ref,
                "decision": input_data.decision,
                "correction": input_data.correction or {},
                "replacement_refs": input_data.replacement_refs or [],
                "author_note": input_data.author_note,
                "requires": "new_source_delta_or_memory_rewrite",
            }
            if contradiction_source_span_ids:
                contradiction_entry["source_span_ids"] = contradiction_source_span_ids
            page.contradictions = list(page.contradictions) + [contradiction_entry]
            job = self._queue_memory_page_rewrite_job(input_data, page)
            rewrite_job_ids.append(str(job.id))
            marked_pages += 1
            marked_page_ids.append(str(page.id))
        if marked_pages:
            side_effects["memory_pages"] = "marked_stale"
            side_effects["memory_pages_marked_stale"] = marked_pages
            side_effects["memory_page_ids"] = marked_page_ids
            side_effects["memory_page_rewrite_job_ids"] = rewrite_job_ids

        graph_edges = (
            self._session.query(GraphProjectionEdge)
            .filter_by(project_id=input_data.project_id)
            .all()
        )
        marked = 0
        marked_edge_ids: list[str] = []
        evidence_span_ids = set(contradiction_source_span_ids)
        for edge in graph_edges:
            edge_fact_match = edge.source_ref.get(
                "type"
            ) == "fact_assertion" and edge.source_ref.get("id") in {
                str(fact_id) for fact_id in fact_ids
            }
            edge_span_ids = {
                str(ref.get("id"))
                for ref in edge.evidence_refs
                if ref.get("type") == "source_span" and ref.get("id") is not None
            }
            if edge_fact_match or edge_span_ids.intersection(evidence_span_ids):
                edge.edge_status = "disputed"
                marked += 1
                marked_edge_ids.append(str(edge.id))
        side_effects["graph_edges_marked_disputed"] = marked
        if marked_edge_ids:
            side_effects["graph_edge_ids"] = marked_edge_ids
        return side_effects

    def _apply_source_span_preview_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        side_effects["source_span_status"] = "retained"
        span_id = input_data.item_ref.get("id")
        if span_id is None:
            return side_effects
        span = self._session.get(SourceSpan, UUID(str(span_id)))
        if span is None or not _source_span_belongs_to_project(
            self._session, span, input_data.project_id
        ):
            return side_effects
        if input_data.decision == "accept":
            side_effects["evidence_log_entries_marked_disputed"] = 0
            side_effects["fact_assertions_marked_disputed"] = 0
            return side_effects

        span_id_text = str(span.id)
        evidence_entries = _evidence_entries_for_spans(
            self._session, project_id=input_data.project_id, span_ids=[span_id_text]
        )
        for entry in evidence_entries:
            entry.log_status = "disputed"
        side_effects["evidence_log_entries_marked_disputed"] = len(evidence_entries)

        facts = _facts_for_spans(
            self._session, project_id=input_data.project_id, span_ids=[span_id_text]
        )
        return self._apply_fact_dispute_decision(
            input_data,
            facts,
            side_effects,
            evidence_span_ids={span_id_text},
        )

    def _apply_evidence_log_preview_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        evidence_id = input_data.item_ref.get("id")
        if evidence_id is None:
            return side_effects
        entry = self._session.get(EvidenceLogEntry, UUID(str(evidence_id)))
        if entry is None or entry.project_id != input_data.project_id:
            return side_effects
        if input_data.decision == "accept":
            side_effects["evidence_log_status"] = entry.log_status
            side_effects["fact_assertions_marked_disputed"] = 0
            return side_effects

        entry.log_status = "disputed"
        side_effects["evidence_log_status"] = "disputed"
        side_effects["evidence_log_entries_marked_disputed"] = 1
        facts: list[FactAssertionRecord] = []
        if entry.fact_id is not None:
            fact = self._session.get(FactAssertionRecord, entry.fact_id)
            if fact is not None:
                facts.append(fact)
        if not facts:
            facts = _facts_for_spans(
                self._session,
                project_id=input_data.project_id,
                span_ids=[str(item) for item in entry.source_span_ids],
            )
        return self._apply_fact_dispute_decision(
            input_data,
            facts,
            side_effects,
            evidence_span_ids={str(item) for item in entry.source_span_ids},
        )

    def _apply_memory_page_preview_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        side_effects["graph_projection"] = "unchanged"
        page_id = input_data.item_ref.get("id")
        if page_id is None:
            return side_effects
        page = self._session.get(MemoryPage, UUID(str(page_id)))
        if page is None or page.project_id != input_data.project_id:
            return side_effects
        if input_data.decision == "accept":
            side_effects["memory_pages"] = page.canon_status
            side_effects["memory_pages_marked_stale"] = 0
            return side_effects

        page.canon_status = "stale"
        if _is_memory_page_open_thread_correction(input_data):
            page.source_refs = _sanitized_memory_page_source_refs(
                self._session,
                input_data.project_id,
                page.source_refs,
            )
            thread = _memory_page_open_thread_decision_entry(
                self._session,
                page,
                input_data,
            )
            raw_thread_source_span_ids = thread.get("source_span_ids", [])
            thread_source_span_values = (
                raw_thread_source_span_ids if isinstance(raw_thread_source_span_ids, list) else []
            )
            thread_source_span_ids = [
                str(span_id) for span_id in thread_source_span_values if span_id is not None
            ]
            if thread_source_span_ids:
                page.source_refs = _unique_refs(
                    list(page.source_refs)
                    + [{"type": "source_span", "id": span_id} for span_id in thread_source_span_ids]
                )
                side_effects["source_span_ids"] = thread_source_span_ids
            if thread not in page.open_threads:
                page.open_threads = list(page.open_threads) + [thread]
                side_effects["memory_page_open_threads_added"] = 1
            else:
                side_effects["memory_page_open_threads_added"] = 0
            side_effects["policy_action"] = "memory_page_open_thread_recorded"
        else:
            page.contradictions = list(page.contradictions) + [
                {
                    "type": "memory_writeback_decision",
                    "source_delta_id": str(input_data.source_delta_id),
                    "item_ref": input_data.item_ref,
                    "decision": input_data.decision,
                    "correction": input_data.correction or {},
                    "replacement_refs": input_data.replacement_refs or [],
                    "author_note": input_data.author_note,
                    "requires": "memory_page_rewrite",
                }
            ]
            side_effects["policy_action"] = "memory_page_contradiction_recorded"
        job = self._queue_memory_page_rewrite_job(input_data, page)
        side_effects["memory_pages"] = "marked_stale"
        side_effects["memory_pages_marked_stale"] = 1
        side_effects["memory_page_ids"] = [str(page.id)]
        side_effects["memory_page_rewrite_job_ids"] = [str(job.id)]
        return side_effects

    def _apply_graph_edge_preview_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        edge_id = input_data.item_ref.get("id")
        if edge_id is None:
            return side_effects
        edge = self._session.get(GraphProjectionEdge, UUID(str(edge_id)))
        if edge is None or edge.project_id != input_data.project_id:
            return side_effects
        if input_data.decision == "accept":
            side_effects["graph_edge_status"] = edge.edge_status
            side_effects["graph_edges_marked_disputed"] = 0
            side_effects["fact_assertions_marked_disputed"] = 0
            return side_effects

        edge.edge_status = "disputed"
        side_effects["graph_edge_status"] = "disputed"
        facts: list[FactAssertionRecord] = []
        if edge.source_ref.get("type") == "fact_assertion" and edge.source_ref.get("id"):
            fact = self._session.get(FactAssertionRecord, UUID(str(edge.source_ref["id"])))
            if fact is not None:
                facts.append(fact)
        evidence_span_ids = {
            str(ref.get("id"))
            for ref in edge.evidence_refs
            if ref.get("type") == "source_span" and ref.get("id") is not None
        }
        return self._apply_fact_dispute_decision(
            input_data,
            facts,
            side_effects,
            evidence_span_ids=evidence_span_ids,
        )

    def _queue_memory_page_rewrite_job(
        self,
        input_data: MemoryWritebackDecisionInput,
        page: MemoryPage,
    ) -> JobRecord:
        decision_ref = f"{input_data.item_ref.get('type')}:{input_data.item_ref.get('id')}"
        rewrite_key = (
            f"memory-page:{page.id}:rewrite-after:{input_data.source_delta_id}:{decision_ref}"
        )
        job = (
            self._session.query(JobRecord)
            .filter_by(
                project_id=input_data.project_id,
                job_type="rewrite_memory_page",
                idempotency_key=rewrite_key,
            )
            .one_or_none()
        )
        if job is None:
            job = JobRecord(
                id=uuid4(),
                project_id=input_data.project_id,
                job_type="rewrite_memory_page",
                status="queued",
                idempotency_key=rewrite_key,
                payload={
                    "step": "rewrite_memory_page",
                    "pipeline_version": "pipeline-v1",
                    "memory_page_id": str(page.id),
                    "source_delta_id": str(input_data.source_delta_id),
                    "decision_item_ref": input_data.item_ref,
                    "reason": "memory_writeback_decision",
                },
                run_after=datetime.now(UTC) + timedelta(seconds=60),
            )
        self._session.add(job)
        return job

    def _apply_fact_accept_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        fact: FactAssertionRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        if fact.fact_status != "canon":
            fact.fact_status = "canon"
        if fact.promotion_decision_id is None:
            fact.promotion_decision_id = uuid4()
        side_effects["fact_assertion_status"] = "canon"

        updated_page_ids = _upsert_fact_memory_page(
            self._session,
            project_id=input_data.project_id,
            source_delta_id=input_data.source_delta_id,
            fact=fact,
        )
        side_effects["memory_pages"] = "updated" if updated_page_ids else "unchanged"
        side_effects["memory_pages_updated"] = len(updated_page_ids)
        side_effects["memory_page_ids"] = updated_page_ids

        result = rebuild_graph_projection(self._session, project_id=input_data.project_id)
        side_effects["graph_projection"] = "rebuilt"
        side_effects["graph_projection_run_id"] = str(result.run_id)
        side_effects["graph_edges_created"] = result.created_edge_count

        resolved_review_ids = _resolve_fact_review_items(
            self._session,
            project_id=input_data.project_id,
            actor_id=input_data.actor_id,
            fact=fact,
            author_note=input_data.author_note,
            replacement_refs=input_data.replacement_refs or [],
        )
        side_effects["review_items_resolved"] = len(resolved_review_ids)
        side_effects["review_item_ids"] = resolved_review_ids
        return side_effects

    def _apply_review_item_preview_decision(
        self,
        input_data: MemoryWritebackDecisionInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        side_effects["memory_pages"] = "unchanged"
        side_effects["graph_projection"] = "unchanged"
        review_id = input_data.item_ref.get("id")
        if review_id is None:
            return side_effects
        review = self._session.get(ReviewItemRecord, UUID(str(review_id)))
        if review is None or review.project_id != input_data.project_id:
            return side_effects

        policy_action = "review_item_retained"
        if input_data.decision == "reject" and review.status == "open":
            review.status = "dismissed"
            review.resolution = None
            review.resolved_by = input_data.actor_id
            review.resolved_at = datetime.now(UTC)
            policy_action = "review_item_dismissed"
        elif input_data.decision == "correct":
            policy_action = "review_item_correction_recorded"

        review.side_effects = {
            **dict(review.side_effects or {}),
            "policy_action": policy_action,
            "memory_writeback_decision": input_data.decision,
            "author_note": input_data.author_note,
            "correction": input_data.correction or {},
            "replacement_refs": input_data.replacement_refs or [],
        }
        side_effects["review_item_id"] = str(review.id)
        side_effects["review_item_status"] = review.status
        side_effects["policy_action"] = policy_action
        return side_effects

    def persist_review_item_operation(
        self, input_data: ReviewItemOperationInput
    ) -> ReviewItemOperationOutput:
        review_item = self._session.get(ReviewItemRecord, input_data.review_item_id)
        if review_item is None:
            raise RuntimeError("review item must be loaded before persisting operation")

        side_effects = dict(input_data.side_effects or {})
        if input_data.operation == "resolve":
            review_item.status = (
                "superseded" if input_data.resolution == "supersede" else "resolved"
            )
            review_item.resolution = input_data.resolution
            review_item.resolved_by = input_data.actor_id
            review_item.resolved_at = datetime.now(UTC)
            side_effects = self._apply_review_resolution_side_effects(
                review_item,
                input_data,
                side_effects,
            )
            _persist_review_replacement_evidence(review_item, input_data)
        elif input_data.operation == "dismiss":
            review_item.status = "dismissed"
            review_item.resolution = None
            review_item.resolved_by = input_data.actor_id
            review_item.resolved_at = datetime.now(UTC)
        elif input_data.operation == "reopen":
            review_item.status = "open"
            review_item.resolution = None
            review_item.resolved_by = None
            review_item.resolved_at = None
        else:
            raise RuntimeError("unsupported review operation")

        self._mark_review_item_context_readiness(review_item, input_data, side_effects)
        review_item.side_effects = {
            **side_effects,
            "author_note": input_data.author_note,
        }
        self._session.flush()
        return ReviewItemOperationOutput(
            review_item_id=review_item.id,
            status=review_item.status,
            resolution=review_item.resolution,
            side_effects=review_item.side_effects,
        )

    def _apply_review_resolution_side_effects(
        self,
        review_item: ReviewItemRecord,
        input_data: ReviewItemOperationInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        if _is_proposed_thread_update_review(review_item):
            return self._apply_proposed_thread_update_review_resolution(
                review_item,
                input_data,
                side_effects,
            )

        if review_item.review_type == "alias_conflict" and input_data.correction:
            return self._apply_alias_review_correction(review_item, input_data, side_effects)

        if review_item.review_type == "event_merge_conflict":
            if input_data.resolution == "merge":
                side_effects = self._apply_event_merge_conflict_resolution(
                    review_item,
                    side_effects,
                )
            elif input_data.resolution == "split":
                side_effects = self._apply_event_merge_conflict_split_resolution(
                    review_item,
                    side_effects,
                )
            elif input_data.resolution == "reject":
                return self._apply_event_merge_conflict_reject_resolution(
                    review_item,
                    side_effects,
                )
            elif input_data.resolution == "mark_intentional":
                return self._apply_event_merge_conflict_intentional_resolution(
                    review_item,
                    side_effects,
                )

        if review_item.review_type == "source_scope_conflict" and input_data.resolution == "reject":
            return self._apply_source_scope_conflict_reject_resolution(
                review_item,
                side_effects,
            )

        if (
            side_effects.get("memory_pages") != "mark_stale"
            and side_effects.get("graph_projection") != "mark_stale"
        ):
            return side_effects

        fact_ids = _uuid_values(review_item.affected_refs, "fact_id", "fact_ids")
        memory_page_ids = _uuid_values(
            review_item.affected_refs,
            "memory_page_id",
            "memory_page_ids",
        )
        source_span_ids = _validated_review_source_span_ids(self._session, review_item)
        replacement_refs = input_data.replacement_refs or []
        queue_split_merge_rebuild = (
            side_effects.get("policy_action") == "split_merge_rebuild_required"
        )

        marked_page_ids: list[str] = []
        affected_page_ids: list[str] = []
        rewrite_job_ids: list[str] = []
        pages = self._session.query(MemoryPage).filter_by(project_id=review_item.project_id).all()
        for page in pages:
            if not _review_matches_memory_page(page, fact_ids, memory_page_ids, source_span_ids):
                continue
            affected_page_ids.append(str(page.id))
            if page.canon_status != "stale":
                page.canon_status = "stale"
                marked_page_ids.append(str(page.id))
            if not _has_review_contradiction(page, review_item.id):
                page.contradictions = list(page.contradictions) + [
                    {
                        "type": "review_item_resolution",
                        "review_item_id": str(review_item.id),
                        "resolution": input_data.resolution,
                        "author_note": input_data.author_note,
                        "replacement_refs": replacement_refs,
                        "fact_ids": [str(fact_id) for fact_id in fact_ids],
                        "source_span_ids": sorted(source_span_ids),
                        "requires": "new_source_delta_or_memory_rewrite",
                    }
                ]
            if queue_split_merge_rebuild:
                job = self._queue_review_memory_page_rewrite_job(
                    review_item,
                    page,
                    reason="review_item_split_merge_resolution",
                )
                rewrite_job_ids.append(str(job.id))

        marked_edge_ids: list[str] = []
        edges = (
            self._session.query(GraphProjectionEdge)
            .filter_by(project_id=review_item.project_id)
            .all()
        )
        for edge in edges:
            if not _review_matches_graph_edge(edge, fact_ids, source_span_ids):
                continue
            if edge.edge_status != "outdated":
                edge.edge_status = "outdated"
                marked_edge_ids.append(str(edge.id))

        if side_effects.get("memory_pages") == "mark_stale":
            if queue_split_merge_rebuild and affected_page_ids:
                side_effects["memory_pages"] = "stale_rewrite_queued"
            else:
                side_effects["memory_pages"] = "marked_stale" if marked_page_ids else "unchanged"
            side_effects["memory_pages_marked_stale"] = len(marked_page_ids)
            side_effects["memory_page_ids"] = affected_page_ids
            if queue_split_merge_rebuild:
                side_effects["memory_page_rewrite_job_ids"] = rewrite_job_ids
        if side_effects.get("graph_projection") == "mark_stale":
            if queue_split_merge_rebuild:
                graph_job = self._queue_review_graph_projection_rebuild_job(
                    review_item,
                    input_data,
                )
                side_effects["graph_projection"] = (
                    "outdated_rebuild_queued" if marked_edge_ids else "rebuild_queued"
                )
                side_effects["graph_projection_rebuild_job_id"] = str(graph_job.id)
            else:
                side_effects["graph_projection"] = (
                    "marked_stale" if marked_edge_ids else "unchanged"
                )
            side_effects["graph_edges_marked_stale"] = len(marked_edge_ids)
            side_effects["graph_edge_ids"] = marked_edge_ids
        return side_effects

    def _apply_source_scope_conflict_reject_resolution(
        self,
        review_item: ReviewItemRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        fact_ids = _uuid_values(review_item.affected_refs, "fact_id", "fact_ids")
        if not fact_ids:
            raise RuntimeError("source_scope_conflict ReviewItem has no affected fact ref.")

        facts = (
            self._session.query(FactAssertionRecord)
            .filter_by(project_id=review_item.project_id)
            .where(FactAssertionRecord.id.in_(fact_ids))
            .order_by(FactAssertionRecord.created_at, FactAssertionRecord.id)
            .all()
        )
        if len(facts) != len(fact_ids):
            raise RuntimeError("source_scope_conflict ReviewItem fact refs were not found.")

        retired_fact_ids: list[str] = []
        for fact in facts:
            if fact.fact_status != "contradicted":
                fact.fact_status = "contradicted"
            retired_fact_ids.append(str(fact.id))

        marked_page_ids: list[str] = []
        rewrite_job_ids: list[str] = []
        pages = self._session.query(MemoryPage).filter_by(project_id=review_item.project_id).all()
        for page in pages:
            if not _memory_page_fact_ids(page).intersection(retired_fact_ids):
                continue
            if page.canon_status != "stale":
                page.canon_status = "stale"
            if not _has_review_contradiction(page, review_item.id):
                page.contradictions = list(page.contradictions) + [
                    {
                        "type": "review_item_resolution",
                        "review_item_id": str(review_item.id),
                        "resolution": "reject",
                        "fact_ids": retired_fact_ids,
                        "requires": "memory_rewrite_from_remaining_canon",
                    }
                ]
            rewrite_job = self._queue_review_memory_page_rewrite_job(
                review_item,
                page,
                reason="source_scope_conflict_reject",
            )
            marked_page_ids.append(str(page.id))
            rewrite_job_ids.append(str(rewrite_job.id))

        projection = rebuild_graph_projection(self._session, project_id=review_item.project_id)
        side_effects.update(
            {
                "fact_reject": "source_scope_conflict_rejected",
                "fact_assertion_status": "contradicted",
                "fact_assertions_retired": len(retired_fact_ids),
                "fact_assertion_ids_retired": retired_fact_ids,
                "memory_pages": "stale_rewrite_queued" if marked_page_ids else "unchanged",
                "memory_pages_marked_stale": len(marked_page_ids),
                "memory_page_ids": marked_page_ids,
                "memory_page_rewrite_job_ids": rewrite_job_ids,
                "graph_projection": "rebuilt",
                "graph_projection_run_id": str(projection.run_id),
                "graph_edges_created": projection.created_edge_count,
            }
        )
        return side_effects

    def _apply_event_merge_conflict_resolution(
        self,
        review_item: ReviewItemRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        disputed_event, existing_event = self._event_merge_conflict_events(review_item)

        previous_candidate_ids = set(existing_event.event_candidate_ids)
        existing_span_ids = _valid_source_span_id_strings(
            self._session,
            review_item.project_id,
            existing_event.evidence_span_ids,
        )
        disputed_span_ids = _valid_source_span_id_strings(
            self._session,
            review_item.project_id,
            disputed_event.evidence_span_ids,
        )
        previous_span_ids = set(existing_span_ids)
        existing_event.event_candidate_ids = _merge_text_values(
            existing_event.event_candidate_ids,
            list(disputed_event.event_candidate_ids),
        )
        existing_event.evidence_span_ids = _merge_text_values(
            existing_span_ids,
            disputed_span_ids,
        )
        existing_event.participants = _merge_dict_values(
            existing_event.participants,
            disputed_event.participants,
        )
        existing_event.objects = _merge_dict_values(
            existing_event.objects,
            disputed_event.objects,
        )
        if existing_event.primary_scene_id is None and disputed_event.primary_scene_id is not None:
            existing_event.primary_scene_id = disputed_event.primary_scene_id
        if (
            existing_event.location_entity_id is None
            and disputed_event.location_entity_id is not None
        ):
            existing_event.location_entity_id = disputed_event.location_entity_id
        if existing_event.story_time is None and disputed_event.story_time:
            existing_event.story_time = disputed_event.story_time
        if not existing_event.cause_summary and disputed_event.cause_summary:
            existing_event.cause_summary = disputed_event.cause_summary
        if not existing_event.consequence_summary and disputed_event.consequence_summary:
            existing_event.consequence_summary = disputed_event.consequence_summary
        disputed_event.event_status = "deprecated"
        now = datetime.now(UTC)
        existing_event.updated_at = now
        disputed_event.updated_at = now

        side_effects.update(
            {
                "event_merge": "applied",
                "merged_event_id": str(existing_event.id),
                "deprecated_event_id": str(disputed_event.id),
                "event_candidate_ids_merged": len(
                    set(existing_event.event_candidate_ids) - previous_candidate_ids
                ),
                "source_span_ids_merged": len(
                    set(existing_event.evidence_span_ids) - previous_span_ids
                ),
            }
        )
        return side_effects

    def _apply_event_merge_conflict_split_resolution(
        self,
        review_item: ReviewItemRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        disputed_event, existing_event = self._event_merge_conflict_events(review_item)
        if disputed_event.event_status == "disputed":
            disputed_event.event_status = "proposed"
            disputed_event.updated_at = datetime.now(UTC)
        side_effects.update(
            {
                "event_split": "confirmed_distinct",
                "distinct_event_id": str(disputed_event.id),
                "existing_event_id": str(existing_event.id),
                "distinct_event_status": disputed_event.event_status,
            }
        )
        return side_effects

    def _apply_event_merge_conflict_reject_resolution(
        self,
        review_item: ReviewItemRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        disputed_event, existing_event = self._event_merge_conflict_events(review_item)
        rejected_candidate_ids: list[str] = []
        candidate_ids = _uuid_values(
            {"event_candidate_ids": disputed_event.event_candidate_ids},
            "event_candidate_id",
            "event_candidate_ids",
        )
        if candidate_ids:
            candidates = self._session.scalars(
                select(StoryEventCandidate)
                .where(StoryEventCandidate.project_id == review_item.project_id)
                .where(StoryEventCandidate.id.in_(candidate_ids))
                .order_by(StoryEventCandidate.created_at, StoryEventCandidate.id)
            ).all()
            for candidate in candidates:
                if candidate.aggregation_status != "rejected":
                    candidate.aggregation_status = "rejected"
                rejected_candidate_ids.append(str(candidate.id))

        if disputed_event.event_status != "deprecated":
            disputed_event.event_status = "deprecated"
            disputed_event.updated_at = datetime.now(UTC)

        projection = rebuild_graph_projection(self._session, project_id=review_item.project_id)
        side_effects.update(
            {
                "event_reject": "deprecated_conflict_version",
                "deprecated_event_id": str(disputed_event.id),
                "existing_event_id": str(existing_event.id),
                "event_candidates_rejected": len(rejected_candidate_ids),
                "event_candidate_ids_rejected": rejected_candidate_ids,
                "memory_pages": "unchanged",
                "graph_projection": "rebuilt",
                "graph_projection_run_id": str(projection.run_id),
                "graph_edges_created": projection.created_edge_count,
            }
        )
        return side_effects

    def _apply_event_merge_conflict_intentional_resolution(
        self,
        review_item: ReviewItemRecord,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        disputed_event, existing_event = self._event_merge_conflict_events(review_item)
        projection = rebuild_graph_projection(self._session, project_id=review_item.project_id)
        side_effects.update(
            {
                "event_intentional_conflict": "recorded",
                "event_id": str(disputed_event.id),
                "existing_event_id": str(existing_event.id),
                "memory_pages": "unchanged",
                "graph_projection": "rebuilt",
                "graph_projection_run_id": str(projection.run_id),
                "graph_edges_created": projection.created_edge_count,
            }
        )
        return side_effects

    def _event_merge_conflict_events(
        self,
        review_item: ReviewItemRecord,
    ) -> tuple[StoryCanonicalEvent, StoryCanonicalEvent]:
        affected_refs = dict(review_item.affected_refs or {})
        event_ref = affected_refs.get("event_id")
        existing_event_ref = affected_refs.get("existing_event_id")
        try:
            event_id = UUID(str(event_ref))
            existing_event_id = UUID(str(existing_event_ref))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Event merge ReviewItem has invalid affected event refs.") from exc

        if event_id == existing_event_id:
            raise RuntimeError("Event merge ReviewItem cannot compare an event with itself.")

        disputed_event = self._session.get(StoryCanonicalEvent, event_id)
        existing_event = self._session.get(StoryCanonicalEvent, existing_event_id)
        if (
            disputed_event is None
            or existing_event is None
            or disputed_event.project_id != review_item.project_id
            or existing_event.project_id != review_item.project_id
        ):
            raise RuntimeError("Event merge ReviewItem events were not found in the project.")
        if disputed_event.event_type != existing_event.event_type:
            raise RuntimeError("Event merge ReviewItem events must share an event type.")
        return disputed_event, existing_event

    def _apply_proposed_thread_update_review_resolution(
        self,
        review_item: ReviewItemRecord,
        input_data: ReviewItemOperationInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        affected_refs = dict(review_item.affected_refs or {})
        thread_id = str(affected_refs.get("id") or "").strip()
        target_ref = affected_refs.get("target_ref")
        update_type = str(affected_refs.get("update_type") or "").strip()
        side_effects["graph_projection"] = "unchanged"
        if thread_id:
            side_effects["thread_update_id"] = thread_id

        if input_data.resolution == "reject":
            side_effects["memory_pages"] = "unchanged"
            side_effects["policy_action"] = "thread_update_rejected"
            return side_effects
        if input_data.resolution == "needs_memory_update":
            side_effects["memory_pages"] = "awaiting_author_memory_update"
            side_effects["policy_action"] = "thread_update_needs_author_memory_update"
            return side_effects
        if input_data.resolution not in {"accept", "accepted_as_change"}:
            side_effects["memory_pages"] = "unchanged"
            side_effects["policy_action"] = "thread_update_left_unapplied"
            return side_effects

        if (
            not thread_id
            or not isinstance(target_ref, dict)
            or not isinstance(target_ref.get("type"), str)
            or not isinstance(target_ref.get("id"), str)
            or update_type not in REVIEW_THREAD_UPDATE_TYPES
        ):
            raise RuntimeError("Proposed thread update ReviewItem has invalid affected_refs.")

        span_ids = _review_context_source_span_ids(self._session, review_item)
        if not span_ids:
            raise RuntimeError("Proposed thread update ReviewItem has no SourceSpan evidence.")

        spans = [self._session.get(SourceSpan, span_id) for span_id in span_ids]
        source_spans = [span for span in spans if span is not None]
        source_deltas = [
            _source_delta_for_thread_update_span(
                self._session,
                project_id=review_item.project_id,
                span=span,
            )
            for span in source_spans
        ]
        if not source_deltas or any(delta is None for delta in source_deltas):
            raise RuntimeError("Proposed thread update ReviewItem has no SourceDelta evidence.")

        source_delta_ids = [str(delta.id) for delta in source_deltas if delta is not None]
        source_span_ids = [str(span.id) for span in source_spans]
        page = _find_memory_page_for_target_ref(
            self._session,
            project_id=review_item.project_id,
            target_ref=target_ref,
        )
        source_refs = _unique_refs(
            [{"type": "source_delta", "id": delta_id} for delta_id in source_delta_ids]
            + [{"type": "source_span", "id": span_id} for span_id in source_span_ids]
        )
        if page is None:
            page = MemoryPage(
                id=uuid4(),
                project_id=review_item.project_id,
                page_type=str(target_ref["type"]),
                target_ref=dict(target_ref),
                title=str(target_ref["id"]),
                current_canon={"facts": []},
                appearance_log=[],
                event_log=[],
                relationships=[],
                open_threads=[],
                contradictions=[],
                source_refs=source_refs,
                canon_status="current",
                memory_depth="scene",
            )
            self._session.add(page)
            self._session.flush()
        else:
            page.source_refs = _unique_refs(list(page.source_refs) + source_refs)

        thread_entry: dict[str, object] = {
            "id": thread_id,
            "update_type": update_type,
            "summary": review_item.summary.strip(),
            "risk_level": review_item.severity,
            "source_delta_id": source_delta_ids[0],
            "source_span_ids": source_span_ids,
            "status": _thread_update_review_status(update_type),
        }
        page.open_threads = _apply_thread_entry(
            self._session,
            page.open_threads,
            thread_entry,
            project_id=review_item.project_id,
        )
        evidence = _ensure_thread_update_applied_evidence(
            self._session,
            project_id=review_item.project_id,
            page_id=page.id,
            thread_id=thread_id,
            source_span_ids=source_span_ids,
        )
        self._session.flush()

        side_effects["memory_pages"] = "thread_update_applied"
        side_effects["memory_page_ids"] = [str(page.id)]
        side_effects["evidence_log_entry_ids"] = [str(evidence.id)]
        side_effects["source_span_ids"] = source_span_ids
        side_effects["source_delta_ids"] = source_delta_ids
        side_effects["policy_action"] = "thread_update_accepted"
        return side_effects

    def _apply_alias_review_correction(
        self,
        review_item: ReviewItemRecord,
        input_data: ReviewItemOperationInput,
        side_effects: dict[str, object],
    ) -> dict[str, object]:
        correction = input_data.correction or {}
        alias_id = UUID(
            str(
                correction.get("alias_record_id")
                or review_item.affected_refs.get("alias_record_id")
            )
        )
        target_entity_id = UUID(
            str(
                correction.get("target_entity_id")
                or review_item.affected_refs.get("target_entity_id")
            )
        )
        alias = self._session.get(StoryAliasRecord, alias_id)
        target_entity = self._session.get(StoryCanonicalEntity, target_entity_id)
        if (
            alias is None
            or target_entity is None
            or alias.project_id != review_item.project_id
            or target_entity.project_id != review_item.project_id
        ):
            raise RuntimeError("Alias correction target was not found in the review project.")

        old_entity_id = alias.entity_id
        old_entity = (
            self._session.get(StoryCanonicalEntity, old_entity_id)
            if old_entity_id is not None
            else None
        )
        old_ref = _alias_entity_ref(alias, old_entity)
        target_ref = _canonical_entity_ref(target_entity)
        old_valid_from_scene_id = alias.valid_from_scene_id
        old_valid_until_scene_id = alias.valid_until_scene_id
        boundary_scene_refs = _alias_boundary_scene_refs_from_correction(correction)
        alias.entity_id = target_entity.id
        alias.status = "user_corrected"
        boundary_aliases = self._alias_boundary_correction_targets(
            alias,
            target_entity,
            correction,
            boundary_scene_refs,
        )
        for boundary_alias in boundary_aliases:
            boundary_alias.status = "user_corrected"
            if "valid_from_scene_id" in boundary_scene_refs:
                boundary_alias.valid_from_scene_id = boundary_scene_refs["valid_from_scene_id"]
            if "valid_until_scene_id" in boundary_scene_refs:
                boundary_alias.valid_until_scene_id = boundary_scene_refs["valid_until_scene_id"]

        mentions_updated = 0
        alias_span_ids = {str(span_id) for span_id in alias.evidence_span_ids}
        mentions = self._session.query(StoryMention).all()
        for mention in mentions:
            if str(mention.span_id) not in alias_span_ids:
                continue
            if mention.raw_text.casefold() != alias.alias_text.casefold():
                continue
            if mention.resolved_entity_id != target_entity.id:
                mention.resolved_entity_id = target_entity.id
                mentions_updated += 1
            mention.resolution_status = "user_corrected"

        updated_fact_ids: set[UUID] = set()
        facts = self._session.query(FactAssertionRecord).filter_by(
            project_id=review_item.project_id
        )
        for fact in facts:
            changed = False
            if refs_equivalent(fact.subject_ref, old_ref):
                fact.subject_ref = dict(target_ref)
                changed = True
            if refs_equivalent(fact.object_ref, old_ref):
                fact.object_ref = dict(target_ref)
                changed = True
            if changed:
                updated_fact_ids.add(fact.id)

        marked_page_ids: list[str] = []
        rewrite_job_ids: list[str] = []
        pages = self._session.query(MemoryPage).filter_by(project_id=review_item.project_id).all()
        for page in pages:
            page_fact_ids = {
                UUID(str(entry.get("fact_id")))
                for entry in page.current_canon.get("facts", [])
                if isinstance(entry, dict) and entry.get("fact_id")
            }
            target_matches = refs_equivalent(page.target_ref, old_ref)
            fact_matches = bool(page_fact_ids.intersection(updated_fact_ids))
            if not target_matches and not fact_matches:
                continue
            if target_matches:
                page.target_ref = dict(target_ref)
                page.title = target_entity.display_name
            page.canon_status = "stale"
            if not _has_review_contradiction(page, review_item.id):
                page.contradictions = list(page.contradictions) + [
                    {
                        "type": "review_item_resolution",
                        "review_item_id": str(review_item.id),
                        "resolution": input_data.resolution,
                        "author_note": input_data.author_note,
                        "correction": correction,
                        "fact_ids": [str(fact_id) for fact_id in sorted(updated_fact_ids, key=str)],
                        "requires": "memory_page_rewrite",
                    }
                ]
            job = self._queue_review_memory_page_rewrite_job(review_item, page)
            marked_page_ids.append(str(page.id))
            rewrite_job_ids.append(str(job.id))

        projection = rebuild_graph_projection(self._session, project_id=review_item.project_id)
        side_effects.update(
            {
                "alias_correction": "applied",
                "alias_record_id": str(alias.id),
                "old_entity_id": str(old_entity_id) if old_entity_id is not None else None,
                "target_entity_id": str(target_entity.id),
                "mentions_updated": mentions_updated,
                "fact_assertions_updated": len(updated_fact_ids),
                "fact_ids": [str(fact_id) for fact_id in sorted(updated_fact_ids, key=str)],
                "memory_pages": "marked_stale" if marked_page_ids else "unchanged",
                "memory_pages_marked_stale": len(marked_page_ids),
                "memory_page_ids": marked_page_ids,
                "memory_page_rewrite_job_ids": rewrite_job_ids,
                "graph_projection": "rebuilt",
                "graph_projection_run_id": str(projection.run_id),
                "graph_edges_created": projection.created_edge_count,
            }
        )
        if boundary_scene_refs:
            side_effects.update(
                {
                    "alias_boundary_correction": "applied",
                    "alias_boundary_records_updated": len(boundary_aliases),
                    "alias_boundary_record_ids": [
                        str(boundary_alias.id)
                        for boundary_alias in sorted(
                            boundary_aliases,
                            key=lambda item: str(item.id),
                        )
                    ],
                    "previous_valid_from_scene_id": (
                        str(old_valid_from_scene_id)
                        if old_valid_from_scene_id is not None
                        else None
                    ),
                    "previous_valid_until_scene_id": (
                        str(old_valid_until_scene_id)
                        if old_valid_until_scene_id is not None
                        else None
                    ),
                    "valid_from_scene_id": (
                        str(alias.valid_from_scene_id)
                        if alias.valid_from_scene_id is not None
                        else None
                    ),
                    "valid_until_scene_id": (
                        str(alias.valid_until_scene_id)
                        if alias.valid_until_scene_id is not None
                        else None
                    ),
                }
            )
        return side_effects

    def _alias_boundary_correction_targets(
        self,
        alias: StoryAliasRecord,
        target_entity: StoryCanonicalEntity,
        correction: dict[str, object],
        boundary_scene_refs: dict[str, UUID | None],
    ) -> list[StoryAliasRecord]:
        if (
            not boundary_scene_refs
            or correction.get("apply_to_matching_aliases") is not True
            or alias.scope != "disguise_arc"
        ):
            return [alias]

        normalized_alias = alias.alias_text.casefold()
        aliases = (
            self._session.query(StoryAliasRecord)
            .filter(StoryAliasRecord.project_id == alias.project_id)
            .filter(func.lower(StoryAliasRecord.alias_text) == normalized_alias)
            .filter(StoryAliasRecord.entity_id == target_entity.id)
            .filter(StoryAliasRecord.scope == alias.scope)
            .order_by(StoryAliasRecord.created_at, StoryAliasRecord.id)
            .all()
        )
        targets = {row.id: row for row in aliases}
        targets[alias.id] = alias
        return list(targets.values())

    def _queue_review_memory_page_rewrite_job(
        self,
        review_item: ReviewItemRecord,
        page: MemoryPage,
        *,
        reason: str = "review_item_alias_correction",
    ) -> JobRecord:
        rewrite_key = f"memory-page:{page.id}:rewrite-after-review:{review_item.id}"
        job = (
            self._session.query(JobRecord)
            .filter_by(
                project_id=review_item.project_id,
                job_type="rewrite_memory_page",
                idempotency_key=rewrite_key,
            )
            .one_or_none()
        )
        if job is None:
            job = JobRecord(
                id=uuid4(),
                project_id=review_item.project_id,
                job_type="rewrite_memory_page",
                status="queued",
                idempotency_key=rewrite_key,
                payload={
                    "step": "rewrite_memory_page",
                    "pipeline_version": "pipeline-v1",
                    "memory_page_id": str(page.id),
                    "review_item_id": str(review_item.id),
                    "reason": reason,
                },
                run_after=datetime.now(UTC) + timedelta(seconds=60),
            )
        self._session.add(job)
        return job

    def _queue_review_graph_projection_rebuild_job(
        self,
        review_item: ReviewItemRecord,
        input_data: ReviewItemOperationInput,
    ) -> JobRecord:
        rebuild_key = (
            f"graph-projection:{review_item.project_id}:rebuild-after-review:{review_item.id}"
        )
        job = (
            self._session.query(JobRecord)
            .filter_by(
                project_id=review_item.project_id,
                job_type="rebuild_graph_projection",
                idempotency_key=rebuild_key,
            )
            .one_or_none()
        )
        if job is None:
            job = JobRecord(
                id=uuid4(),
                project_id=review_item.project_id,
                job_type="rebuild_graph_projection",
                status="queued",
                idempotency_key=rebuild_key,
                payload={
                    "step": "rebuild_graph_projection",
                    "pipeline_version": "pipeline-v1",
                    "review_item_id": str(review_item.id),
                    "resolution": input_data.resolution,
                    "replacement_refs": input_data.replacement_refs or [],
                    "reason": "review_item_split_merge_resolution",
                },
                run_after=datetime.now(UTC) + timedelta(seconds=60),
            )
        self._session.add(job)
        return job

    def _mark_review_item_context_readiness(
        self,
        review_item: ReviewItemRecord,
        input_data: ReviewItemOperationInput,
        side_effects: dict[str, object],
    ) -> None:
        source_span_ids = _review_context_source_span_ids(self._session, review_item)
        if not source_span_ids:
            return

        affected_refs = _unique_refs(
            [{"type": "review_item", "id": str(review_item.id)}]
            + _side_effect_affected_refs(side_effects)
            + (input_data.replacement_refs or [])
        )
        records = [
            mark_context_pack_readiness(
                self._session,
                project_id=review_item.project_id,
                source_span_id=span_id,
                affected_refs=affected_refs,
                reason="review_dependency_changed",
                status="stale",
            )
            for span_id in source_span_ids
        ]
        side_effects["context_pack_readiness"] = "marked_stale"
        side_effects["context_pack_readiness_marked"] = len(records)
        side_effects["context_pack_readiness_ids"] = [str(record.id) for record in records]

    def answer_memory(self, input_data: MemoryAnswerInput) -> MemoryAnswerOutput:
        input_data = _memory_answer_input_with_effective_pov(self._session, input_data)
        continuity_reviews = _memory_answer_continuity_reviews(
            self._session,
            input_data,
        )
        if continuity_reviews is not None:
            if not continuity_reviews:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )
            span_ids = _continuity_review_span_ids(continuity_reviews)
            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_continuity_review_answer(continuity_reviews),
                answer_type="conflict",
                confidence=_continuity_review_confidence(continuity_reviews),
                source_span_refs=[{"type": "source_span", "id": span_id} for span_id in span_ids],
                affected_entities=_continuity_review_affected_entities(continuity_reviews),
                caveats=_continuity_review_caveats(continuity_reviews),
                unknowns=[],
                related_review_items=[review.id for review in continuity_reviews],
                safe_to_use_in_current_pov=False,
            )

        event_overlap = _memory_answer_event_overlap(
            self._session,
            input_data,
        )
        if event_overlap is not None:
            anchor_event, overlapping_events = event_overlap
            if anchor_event is None:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )
            if not overlapping_events:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            span_ids = _event_answer_span_ids(
                self._session,
                input_data.project_id,
                anchor_event,
                overlapping_events,
            )
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            caveats = ["event_overlap_from_scene_or_story_time"]
            if related_review_items:
                caveats.append("open_review_item")
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_event_answer_confidence(overlapping_events),
                    source_span_refs=source_span_refs,
                    affected_entities=_event_answer_affected_entities(overlapping_events),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_event_overlap_answer(anchor_event, overlapping_events),
                answer_type="canon",
                confidence=_event_answer_confidence(overlapping_events),
                source_span_refs=source_span_refs,
                affected_entities=_event_answer_affected_entities(overlapping_events),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=True,
            )

        event_timeline = _memory_answer_event_timeline(
            self._session,
            input_data,
        )
        if event_timeline is not None:
            anchor_event, later_events = event_timeline
            if anchor_event is None:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )
            if not later_events:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            span_ids = _event_answer_span_ids(
                self._session,
                input_data.project_id,
                anchor_event,
                later_events,
            )
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            caveats = ["timeline_order_from_scene_position"]
            if related_review_items:
                caveats.append("open_review_item")
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_event_answer_confidence(later_events),
                    source_span_refs=source_span_refs,
                    affected_entities=_event_answer_affected_entities(later_events),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_event_timeline_answer(anchor_event, later_events),
                answer_type="canon",
                confidence=_event_answer_confidence(later_events),
                source_span_refs=source_span_refs,
                affected_entities=_event_answer_affected_entities(later_events),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=True,
            )

        knowledge_matches = _memory_answer_character_knowledge_matches(
            self._session,
            input_data,
        )
        if knowledge_matches is not None:
            if not knowledge_matches:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            facts = [fact for _knowledge, fact in knowledge_matches]
            span_ids = _character_knowledge_span_ids(
                self._session,
                input_data.project_id,
                knowledge_matches,
            )
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            risk_facts = [fact for fact in facts if fact.fact_status != "canon"]
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            safe_to_use = _character_knowledge_safe_for_pov(
                knowledge_matches,
                input_data.current_pov_character_id,
            )
            caveats = _memory_answer_character_knowledge_caveats(
                knowledge_matches,
                has_non_canon_evidence=bool(risk_facts),
                has_open_review_items=bool(related_review_items),
                safe_to_use_in_current_pov=safe_to_use,
            )
            if risk_facts or related_review_items:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_memory_answer_confidence(facts),
                    source_span_refs=source_span_refs,
                    affected_entities=_memory_answer_knowledge_affected_entities(knowledge_matches),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer="; ".join(
                    _format_character_knowledge_answer(knowledge, fact)
                    for knowledge, fact in knowledge_matches
                ),
                answer_type="canon",
                confidence=_memory_answer_confidence(facts),
                source_span_refs=source_span_refs,
                affected_entities=_memory_answer_knowledge_affected_entities(knowledge_matches),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=safe_to_use,
            )

        relationship_path_result = _memory_answer_relationship_path(
            self._session,
            input_data,
        )
        if relationship_path_result is not None:
            relationship_path, relationship_path_node_keys = relationship_path_result
            if not relationship_path:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            span_ids = _fact_source_span_ids(
                self._session,
                input_data.project_id,
                relationship_path,
            )
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            risk_facts = [fact for fact in relationship_path if fact.fact_status != "canon"]
            safe_to_use = self._facts_safe_for_pov(
                relationship_path,
                input_data.current_pov_character_id,
            )
            caveats = _relationship_path_caveats(
                has_non_canon_evidence=bool(risk_facts),
                has_open_review_items=bool(related_review_items),
                safe_to_use_in_current_pov=safe_to_use,
            )
            if risk_facts or related_review_items:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_memory_answer_confidence(relationship_path),
                    source_span_refs=source_span_refs,
                    affected_entities=_relationship_path_affected_entities(
                        relationship_path,
                        relationship_path_node_keys,
                    ),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_relationship_path_answer(
                    relationship_path,
                    relationship_path_node_keys,
                ),
                answer_type="canon",
                confidence=_memory_answer_confidence(relationship_path),
                source_span_refs=source_span_refs,
                affected_entities=_relationship_path_affected_entities(
                    relationship_path,
                    relationship_path_node_keys,
                ),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=safe_to_use,
            )

        relationship_timeline = _memory_answer_relationship_timeline(
            self._session,
            input_data,
        )
        if relationship_timeline is not None:
            if not relationship_timeline:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            relationship_facts = [fact for fact, _span, _chapter, _scene in relationship_timeline]
            span_ids = _relationship_timeline_span_ids(relationship_timeline)
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            risk_facts = [
                fact
                for fact in relationship_facts
                if fact.fact_status not in {"canon", "outdated", "user_note"}
            ]
            safe_to_use = self._facts_safe_for_pov(
                relationship_facts,
                input_data.current_pov_character_id,
            )
            caveats = _relationship_timeline_caveats(
                has_non_canon_evidence=bool(risk_facts),
                has_open_review_items=bool(related_review_items),
                safe_to_use_in_current_pov=safe_to_use,
            )
            if risk_facts or related_review_items:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_memory_answer_confidence(relationship_facts),
                    source_span_refs=source_span_refs,
                    affected_entities=_memory_answer_affected_entities(relationship_facts),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_relationship_timeline_answer(relationship_timeline),
                answer_type="canon",
                confidence=_memory_answer_confidence(relationship_facts),
                source_span_refs=source_span_refs,
                affected_entities=_memory_answer_affected_entities(relationship_facts),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=safe_to_use,
            )

        relationship_explanation = _memory_answer_relationship_explanation(
            self._session,
            input_data,
        )
        if relationship_explanation is not None:
            relationship_facts, supporting_events = relationship_explanation
            if not relationship_facts:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            span_ids = _relationship_answer_span_ids(
                self._session,
                input_data.project_id,
                relationship_facts,
                supporting_events,
            )
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            canonical_facts = [fact for fact in relationship_facts if fact.fact_status == "canon"]
            risk_facts = [fact for fact in relationship_facts if fact.fact_status != "canon"]
            safe_to_use = self._facts_safe_for_pov(
                canonical_facts,
                input_data.current_pov_character_id,
            )
            caveats = _relationship_answer_caveats(
                supporting_events=supporting_events,
                has_non_canon_evidence=bool(risk_facts),
                has_open_review_items=bool(related_review_items),
                safe_to_use_in_current_pov=safe_to_use,
            )
            if risk_facts or related_review_items:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_memory_answer_confidence(relationship_facts),
                    source_span_refs=source_span_refs,
                    affected_entities=_memory_answer_affected_entities(relationship_facts),
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_relationship_answer(canonical_facts, supporting_events),
                answer_type="canon",
                confidence=_memory_answer_confidence(canonical_facts),
                source_span_refs=source_span_refs,
                affected_entities=_memory_answer_affected_entities(canonical_facts),
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=safe_to_use,
            )

        open_thread_entries = _memory_answer_open_thread_entries(
            self._session,
            input_data,
            embedding_client=self._embedding_client,
        )
        if open_thread_entries is not None:
            if not open_thread_entries:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            span_ids = _open_thread_answer_span_ids(open_thread_entries)
            related_review_items = _unique_uuid_sequence(
                _open_thread_entry_review_ids(
                    self._session,
                    input_data.project_id,
                    open_thread_entries,
                )
                + self._open_review_ids_for_spans(input_data.project_id, span_ids)
            )
            source_span_refs: list[dict[str, object]] = [
                {"type": "source_span", "id": span_id} for span_id in span_ids
            ]
            caveats = _open_thread_answer_caveats(has_open_review_items=bool(related_review_items))
            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_open_thread_answer(open_thread_entries),
                answer_type="open_thread",
                confidence=_open_thread_answer_confidence(
                    self._session,
                    input_data.project_id,
                    open_thread_entries,
                    related_review_items=related_review_items,
                ),
                source_span_refs=source_span_refs,
                affected_entities=_open_thread_answer_affected_entities(open_thread_entries),
                caveats=caveats,
                unknowns=[],
                related_review_items=related_review_items,
                safe_to_use_in_current_pov=not related_review_items,
            )

        ambiguous_entity_match = _memory_answer_ambiguous_entity_match(
            self._session,
            input_data,
        )
        if ambiguous_entity_match is not None:
            surface, entities, span_ids = ambiguous_entity_match
            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_ambiguous_entity_answer(surface, entities),
                answer_type="unknown",
                confidence=0.0,
                source_span_refs=[{"type": "source_span", "id": span_id} for span_id in span_ids],
                affected_entities=[
                    _memory_answer_entity_ref(entity)
                    for entity in sorted(
                        entities,
                        key=lambda item: (item.display_name, str(item.id)),
                    )
                ],
                caveats=["ambiguous_entity_match"],
                unknowns=["ambiguous_entity_match"],
                related_review_items=[],
                safe_to_use_in_current_pov=False,
            )

        first_appearance = _memory_answer_first_appearance(self._session, input_data)
        if first_appearance is not None:
            if not first_appearance:
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="No SourceSpan-backed memory evidence matches this question.",
                    answer_type="unknown",
                    confidence=0.0,
                    source_span_refs=[],
                    affected_entities=[],
                    caveats=["no_matching_evidence"],
                    unknowns=["no_matching_evidence"],
                    related_review_items=[],
                    safe_to_use_in_current_pov=False,
                )

            mention, span, entity, chapter, scene = first_appearance[0]
            span_ids = [str(span.id)]
            related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
            caveats = ["source_mention_lookup"]
            if related_review_items:
                caveats.append("open_review_item")
                return MemoryAnswerOutput(
                    question=input_data.question,
                    answer="Evidence exists, but it is disputed or tied to open review.",
                    answer_type="conflict",
                    confidence=_bounded_confidence(mention.confidence),
                    source_span_refs=[{"type": "source_span", "id": str(span.id)}],
                    affected_entities=[_first_appearance_entity_ref(entity)],
                    caveats=caveats,
                    unknowns=[],
                    related_review_items=related_review_items,
                    safe_to_use_in_current_pov=False,
                )

            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_first_appearance_answer(mention, span, entity, chapter, scene),
                answer_type="canon",
                confidence=_bounded_confidence(mention.confidence),
                source_span_refs=[{"type": "source_span", "id": str(span.id)}],
                affected_entities=[_first_appearance_entity_ref(entity)],
                caveats=caveats,
                unknowns=[],
                related_review_items=[],
                safe_to_use_in_current_pov=True,
            )

        inferred_facts: list[FactAssertionRecord] | None = None
        if input_data.subject_ref is None and input_data.predicate is None:
            inferred_facts = _infer_memory_answer_facts(
                self._session,
                input_data,
                embedding_client=self._embedding_client,
            )
        if (
            input_data.subject_ref is None
            and input_data.predicate is None
            and inferred_facts is None
        ):
            return MemoryAnswerOutput(
                question=input_data.question,
                answer="No structured evidence target was provided.",
                answer_type="unknown",
                confidence=0.0,
                source_span_refs=[],
                affected_entities=[],
                caveats=["structured_subject_or_predicate_required"],
                unknowns=["structured_subject_or_predicate_required"],
                related_review_items=[],
                safe_to_use_in_current_pov=False,
            )

        facts = (
            inferred_facts
            if inferred_facts is not None
            else self._matching_facts(
                input_data.project_id, input_data.subject_ref, input_data.predicate
            )
        )
        facts = _facts_with_same_project_source_spans(
            self._session,
            input_data.project_id,
            facts,
        )
        if not facts:
            return MemoryAnswerOutput(
                question=input_data.question,
                answer="No SourceSpan-backed memory evidence matches this question.",
                answer_type="unknown",
                confidence=0.0,
                source_span_refs=[],
                affected_entities=[],
                caveats=["no_matching_evidence"],
                unknowns=["no_matching_evidence"],
                related_review_items=[],
                safe_to_use_in_current_pov=False,
            )

        clarification_refs = _memory_answer_semantic_fact_clarification_refs(
            self._session,
            input_data,
            facts,
            embedding_client=self._embedding_client,
        )
        if clarification_refs:
            span_ids = _fact_source_span_ids(self._session, input_data.project_id, facts)
            return MemoryAnswerOutput(
                question=input_data.question,
                answer=_format_semantic_fact_clarification_answer(clarification_refs),
                answer_type="unknown",
                confidence=0.0,
                source_span_refs=[{"type": "source_span", "id": span_id} for span_id in span_ids],
                affected_entities=clarification_refs,
                caveats=["semantic_clarification_needed"],
                unknowns=["semantic_clarification_needed"],
                related_review_items=self._open_review_ids_for_spans(
                    input_data.project_id,
                    span_ids,
                ),
                safe_to_use_in_current_pov=False,
            )

        span_ids = _fact_source_span_ids(self._session, input_data.project_id, facts)
        related_review_items = self._open_review_ids_for_spans(input_data.project_id, span_ids)
        canonical_facts = [fact for fact in facts if fact.fact_status == "canon"]
        risk_facts = [fact for fact in facts if fact.fact_status != "canon"]
        source_span_refs: list[dict[str, object]] = [
            {"type": "source_span", "id": span_id} for span_id in span_ids
        ]
        safe_to_use = self._facts_safe_for_pov(canonical_facts, input_data.current_pov_character_id)

        if risk_facts or related_review_items:
            caveats = _memory_answer_caveats(
                has_non_canon_evidence=bool(risk_facts),
                has_open_review_items=bool(related_review_items),
                safe_to_use_in_current_pov=False,
            ) + _memory_answer_scoped_alias_context_caveats(
                self._session,
                input_data,
                facts,
            )
            return MemoryAnswerOutput(
                question=input_data.question,
                answer="Evidence exists, but it is disputed or tied to open review.",
                answer_type="conflict",
                confidence=_memory_answer_confidence_with_evidence_caps(
                    self._session,
                    input_data,
                    facts,
                    embedding_client=self._embedding_client,
                ),
                source_span_refs=source_span_refs,
                affected_entities=_memory_answer_affected_entities(facts),
                caveats=caveats,
                unknowns=[],
                related_review_items=related_review_items,
                safe_to_use_in_current_pov=False,
            )

        caveats = _memory_answer_caveats(
            has_non_canon_evidence=False,
            has_open_review_items=False,
            safe_to_use_in_current_pov=safe_to_use,
        ) + _memory_answer_scoped_alias_context_caveats(
            self._session,
            input_data,
            canonical_facts,
        )
        return MemoryAnswerOutput(
            question=input_data.question,
            answer="; ".join(_format_fact(fact) for fact in canonical_facts),
            answer_type="canon",
            confidence=_memory_answer_confidence_with_evidence_caps(
                self._session,
                input_data,
                canonical_facts,
                embedding_client=self._embedding_client,
            ),
            source_span_refs=source_span_refs,
            affected_entities=_memory_answer_affected_entities(canonical_facts),
            caveats=caveats,
            unknowns=[],
            related_review_items=[],
            safe_to_use_in_current_pov=safe_to_use,
        )

    def build_writing_context_pack(
        self, input_data: BuildWritingContextPackInput
    ) -> WritingContextPackOutput:
        facts = (
            self._session.query(FactAssertionRecord)
            .filter_by(project_id=input_data.project_id)
            .all()
        )
        fact_span_ids_by_id = _fact_source_span_id_map(
            self._session,
            input_data.project_id,
            facts,
        )
        facts = [fact for fact in facts if fact_span_ids_by_id.get(str(fact.id))]
        canonical_facts = [fact for fact in facts if fact.fact_status == "canon"]
        risk_facts = [fact for fact in facts if fact.fact_status != "canon"]
        open_reviews = (
            self._session.query(ReviewItemRecord)
            .filter_by(project_id=input_data.project_id, status="open")
            .all()
        )
        review_span_ids_by_id = _review_source_span_id_map(
            self._session,
            input_data.project_id,
            open_reviews,
        )
        open_reviews = [
            review for review in open_reviews if review_span_ids_by_id.get(str(review.id))
        ]
        scene_context = _scene_context(self._session, input_data.current_scene_id)
        chapter_context = _chapter_context_for_scene(self._session, input_data.current_scene_id)
        current_pov_character_id = input_data.current_pov_character_id
        if current_pov_character_id is None and scene_context is not None:
            scene_pov_id = scene_context.get("pov_character_id")
            if isinstance(scene_pov_id, str):
                current_pov_character_id = UUID(scene_pov_id)
        pov_knowledge = self._pov_knowledge(input_data.project_id, current_pov_character_id)
        allowed_knowledge = [_character_knowledge_entry(item) for item in pov_knowledge]
        known_fact_ids = {
            str(item.knows_ref.get("id"))
            for item in pov_knowledge
            if item.knows_ref.get("type") == "fact_assertion"
        }
        recent_events = _recent_event_entries(self._session, input_data.project_id)
        object_location_state = _object_location_state(self._session, input_data.project_id)
        style_memory = _style_memory(self._session, input_data)
        memory_pages = (
            self._session.query(MemoryPage).filter_by(project_id=input_data.project_id).all()
        )
        semantic_recall = _semantic_recall_context(
            self._session,
            project_id=input_data.project_id,
            input_data=input_data,
            memory_pages=memory_pages,
            embedding_client=self._embedding_client,
        )
        active_characters = _active_characters(
            canonical_facts, current_scene_id=input_data.current_scene_id
        )
        source_spans_by_id = _source_spans_by_id(
            self._session,
            input_data.project_id,
            [
                span_id
                for fact in canonical_facts + risk_facts
                for span_id in fact_span_ids_by_id.get(str(fact.id), [])
            ]
            + [
                str(ref["id"])
                for ref in _event_evidence_refs(recent_events)
                + _edge_evidence_refs(object_location_state)
                + _style_evidence_refs(style_memory)
                if ref.get("id") is not None
            ]
            + [
                span_id
                for review in open_reviews
                for span_id in review_span_ids_by_id.get(str(review.id), [])
            ],
        )
        relevance_scope = _context_relevance_scope(
            input_data=input_data,
            current_pov_character_id=current_pov_character_id,
            active_characters=active_characters,
            source_spans_by_id=source_spans_by_id,
            semantic_recall=semantic_recall,
        )
        canonical_fact_entries = _ranked_fact_entries(
            canonical_facts,
            relevance_scope,
            fact_span_ids_by_id=fact_span_ids_by_id,
        )
        risk_fact_entries = _ranked_fact_entries(
            risk_facts,
            relevance_scope,
            fact_span_ids_by_id=fact_span_ids_by_id,
        )
        forbidden_knowledge = [
            _fact_entry_with_relevance(
                fact,
                relevance_scope,
                fact_span_ids_by_id=fact_span_ids_by_id,
            )
            for fact in canonical_facts
            if current_pov_character_id is not None and str(fact.id) not in known_fact_ids
        ]
        recent_events = _ranked_event_entries(recent_events, relevance_scope)
        object_location_state = _ranked_edge_entries(object_location_state, relevance_scope)
        style_memory = _ranked_style_memory(style_memory, relevance_scope)
        review_entries = _ranked_review_entries(
            open_reviews,
            relevance_scope,
            review_span_ids_by_id=review_span_ids_by_id,
        )
        open_threads = _open_threads(self._session, input_data.project_id, memory_pages)
        budget_metadata = _apply_context_budget(
            input_data=input_data,
            canonical_fact_entries=canonical_fact_entries,
            risk_fact_entries=risk_fact_entries,
            forbidden_knowledge=forbidden_knowledge,
            recent_events=recent_events,
            object_location_state=object_location_state,
            style_memory=style_memory,
            review_entries=review_entries,
            open_threads=open_threads,
        )
        retrieval_policy = _context_retrieval_policy(budget_metadata, semantic_recall)
        style_memory["retrieval_policy"] = dict(retrieval_policy)
        evidence_refs = _context_pack_evidence_refs(
            canonical_fact_entries=canonical_fact_entries,
            risk_fact_entries=risk_fact_entries,
            forbidden_knowledge=forbidden_knowledge,
            recent_events=recent_events,
            object_location_state=object_location_state,
            style_memory=style_memory,
            review_entries=review_entries,
        )
        character_agency_state = _character_agency_state(
            session=self._session,
            project_id=input_data.project_id,
            active_characters=active_characters,
            canonical_facts=canonical_facts,
            recent_events=recent_events,
            object_location_state=object_location_state,
            open_reviews=open_reviews,
            memory_pages=memory_pages,
            fact_span_ids_by_id=fact_span_ids_by_id,
        )
        pov_mode = scene_context.get("pov_mode") if scene_context else None
        output = WritingContextPackOutput(
            context_pack_id=uuid4(),
            schema_version="writing-context-pack.v1",
            current_position={
                "source_id": str(input_data.current_source_id)
                if input_data.current_source_id
                else None,
                "version_id": str(input_data.current_version_id)
                if input_data.current_version_id
                else None,
                "scene_id": str(input_data.current_scene_id)
                if input_data.current_scene_id
                else None,
                "mode": input_data.mode,
                "current_text_window": input_data.current_text_window,
                "chapter": chapter_context,
                "scene": scene_context,
            },
            canonical_context={
                "facts": canonical_fact_entries,
                "retrieval_policy": dict(retrieval_policy),
            },
            pov_constraint={
                "pov_character_id": str(current_pov_character_id)
                if current_pov_character_id
                else None,
                "pov_mode": pov_mode,
                "pov_confidence": scene_context.get("pov_confidence") if scene_context else None,
                "pov_evidence_span_ids": scene_context.get("pov_evidence_span_ids")
                if scene_context
                else [],
                "pov_uncertainty_reason": scene_context.get("pov_uncertainty_reason")
                if scene_context
                else None,
                "sensory_limits": _pov_sensory_limits(scene_context),
                "inner_access": _pov_inner_access(current_pov_character_id, pov_mode),
                "allowed_knowledge": allowed_knowledge,
                "forbidden_knowledge": forbidden_knowledge,
            },
            active_characters=active_characters,
            character_agency_state=character_agency_state,
            recent_events=recent_events,
            character_knowledge=allowed_knowledge,
            object_location_state=object_location_state,
            open_threads=open_threads,
            risk_context={
                "facts": risk_fact_entries,
                "review_items": review_entries,
                "retrieval_policy": dict(retrieval_policy),
            },
            style_memory=style_memory,
            evidence_refs=evidence_refs,
        )
        self._session.add(
            AgentContextPackRecord(
                id=output.context_pack_id,
                project_id=input_data.project_id,
                action_request_id=input_data.action_request_id,
                current_source_id=input_data.current_source_id,
                current_version_id=input_data.current_version_id,
                current_scene_id=input_data.current_scene_id,
                current_pov_character_id=current_pov_character_id,
                mode=input_data.mode,
                schema_version=output.schema_version,
                payload={
                    "current_position": output.current_position,
                    "canonical_context": output.canonical_context,
                    "pov_constraint": output.pov_constraint,
                    "active_characters": output.active_characters,
                    "character_agency_state": output.character_agency_state,
                    "recent_events": output.recent_events,
                    "character_knowledge": output.character_knowledge,
                    "object_location_state": output.object_location_state,
                    "open_threads": output.open_threads,
                    "risk_context": output.risk_context,
                    "style_memory": output.style_memory,
                },
                evidence_refs=output.evidence_refs,
                created_by=input_data.actor_id,
            )
        )
        self._session.flush()
        return output

    def consume_context_pack_readiness(
        self,
        *,
        project_id: UUID,
        context_pack_id: UUID,
        evidence_refs: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        source_span_ids = _source_span_ids_from_refs(evidence_refs)
        if not source_span_ids:
            return []
        records = (
            self._session.query(ContextPackReadinessRecord)
            .filter(ContextPackReadinessRecord.project_id == project_id)
            .filter(ContextPackReadinessRecord.status.in_(("pending", "stale")))
            .filter(ContextPackReadinessRecord.source_span_id.in_(source_span_ids))
            .order_by(ContextPackReadinessRecord.id)
            .all()
        )
        for record in records:
            record.status = "consumed"
            record.affected_refs = _unique_refs(
                list(record.affected_refs)
                + [{"type": "agent_context_pack", "id": str(context_pack_id)}]
            )
        self._session.flush()
        return [
            {
                "id": str(record.id),
                "source_span_id": str(record.source_span_id),
            }
            for record in records
        ]

    def get_writing_context_pack(
        self, input_data: ContextPackDetailInput
    ) -> WritingContextPackOutput | None:
        record = self._session.get(AgentContextPackRecord, input_data.context_pack_id)
        if record is None or record.project_id != input_data.project_id:
            return None
        return _context_pack_output(record)

    def list_writing_context_packs(
        self, input_data: ListContextPacksInput
    ) -> ListContextPacksOutput:
        limit = max(1, min(input_data.limit, 100))
        records = (
            self._session.query(AgentContextPackRecord)
            .filter_by(project_id=input_data.project_id)
            .order_by(AgentContextPackRecord.created_at.desc(), AgentContextPackRecord.id)
            .limit(limit)
            .all()
        )
        return ListContextPacksOutput(
            items=[
                ContextPackSummaryOutput(
                    context_pack_id=record.id,
                    schema_version=record.schema_version,
                    mode=record.mode,
                    current_position=dict(record.payload.get("current_position", {})),
                    evidence_refs=list(record.evidence_refs),
                )
                for record in records
            ]
        )

    def list_context_pack_readiness(
        self, input_data: ListContextPackReadinessInput
    ) -> ListContextPackReadinessOutput:
        limit = max(1, min(input_data.limit, 100))
        query = self._session.query(ContextPackReadinessRecord).filter_by(
            project_id=input_data.project_id
        )
        if input_data.status is not None:
            query = query.filter(ContextPackReadinessRecord.status == input_data.status)
        if input_data.reason is not None:
            query = query.filter(ContextPackReadinessRecord.reason == input_data.reason)
        if input_data.source_delta_id is not None:
            query = query.filter(
                ContextPackReadinessRecord.source_delta_id == input_data.source_delta_id
            )
        records = (
            query.order_by(
                ContextPackReadinessRecord.updated_at.desc(),
                ContextPackReadinessRecord.id,
            )
            .limit(limit)
            .all()
        )
        return ListContextPackReadinessOutput(
            items=[
                ContextPackReadinessSummaryOutput(
                    id=record.id,
                    source_span_id=record.source_span_id,
                    source_delta_id=record.source_delta_id,
                    status=record.status,
                    reason=record.reason,
                    affected_refs=list(record.affected_refs),
                    evidence_refs=list(record.evidence_refs),
                )
                for record in records
            ]
        )

    def _matching_facts(
        self,
        project_id: UUID,
        subject_ref: dict[str, object] | None,
        predicate: str | None,
    ) -> list[FactAssertionRecord]:
        facts = self._session.query(FactAssertionRecord).filter_by(project_id=project_id).all()
        if subject_ref is not None:
            facts = [fact for fact in facts if refs_equivalent(fact.subject_ref, subject_ref)]
        if predicate is not None:
            facts = [fact for fact in facts if fact.predicate == predicate]
        return facts

    def _open_review_ids_for_spans(self, project_id: UUID, span_ids: list[str]) -> list[UUID]:
        if not span_ids:
            return []
        span_id_set = set(span_ids)
        reviews = (
            self._session.query(ReviewItemRecord)
            .filter_by(project_id=project_id, status="open")
            .all()
        )
        return [
            review.id
            for review in reviews
            if span_id_set.intersection(
                str(item) for item in review.new_evidence.get("source_span_ids", [])
            )
        ]

    def _facts_safe_for_pov(
        self, facts: list[FactAssertionRecord], pov_character_id: UUID | None
    ) -> bool:
        if not facts:
            return False
        if pov_character_id is None:
            return True
        known_fact_ids = {
            str(item.knows_ref.get("id"))
            for item in self._session.query(CharacterKnowledge)
            .filter_by(character_id=pov_character_id, status="active")
            .all()
            if item.knows_ref.get("type") == "fact_assertion"
        }
        return all(str(fact.id) in known_fact_ids for fact in facts)

    def _pov_knowledge(
        self, project_id: UUID, pov_character_id: UUID | None
    ) -> list[CharacterKnowledge]:
        if pov_character_id is None:
            return []
        return (
            self._session.query(CharacterKnowledge)
            .filter_by(
                project_id=project_id,
                character_id=pov_character_id,
                status="active",
            )
            .all()
        )

    def record_audit(
        self,
        *,
        project_id: UUID,
        request_id: str,
        actor_id: UUID,
        event_type: str,
        subject_ref: dict[str, object],
        decision: dict[str, object],
    ) -> None:
        self._session.add(
            AuditEvent(
                id=uuid4(),
                project_id=project_id,
                request_id=request_id,
                actor_id=actor_id,
                event_type=event_type,
                subject_ref=subject_ref,
                decision=decision,
            )
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _project_member_snapshot(membership: ProjectMembership) -> ProjectMemberSnapshot:
    return ProjectMemberSnapshot(
        id=membership.id,
        project_id=membership.project_id,
        actor_id=membership.actor_id,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
    )


def _project_invitation_snapshot(invitation: ProjectInvitation) -> ProjectInvitationSnapshot:
    return ProjectInvitationSnapshot(
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


def _sort_source_versions_by_chain(versions: list[SourceVersion]) -> list[SourceVersion]:
    version_by_id = {version.id: version for version in versions}
    depth_cache: dict[UUID, int] = {}

    def version_depth(version: SourceVersion) -> int:
        if version.id in depth_cache:
            return depth_cache[version.id]
        if version.supersedes_version_id and version.supersedes_version_id in version_by_id:
            depth = version_depth(version_by_id[version.supersedes_version_id]) + 1
        else:
            depth = 0
        depth_cache[version.id] = depth
        return depth

    return sorted(
        versions,
        key=lambda version: (version_depth(version), version.created_at, str(version.id)),
        reverse=True,
    )


def _source_summary(source: RawSource, versions: list[SourceVersion]) -> SourceSummaryOutput:
    versions = _sort_source_versions_by_chain(versions)
    latest = versions[0] if versions else None
    return SourceSummaryOutput(
        source_id=source.id,
        title=source.title,
        source_type=source.source_type,
        source_scope=source.source_scope,
        ownership_status=source.ownership_status,
        is_archived=source.archived_at is not None,
        archived_at=source.archived_at,
        archived_by=source.archived_by,
        latest_version_id=latest.id if latest is not None else None,
        latest_version_label=latest.version_label if latest is not None else None,
        latest_raw_hash=latest.raw_hash if latest is not None else None,
        version_count=len(versions),
    )


def _fact_span_ids(facts: list[FactAssertionRecord]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for fact in facts:
        for span_id in fact.evidence_span_ids:
            span_id = str(span_id)
            if span_id not in seen:
                seen.add(span_id)
                result.append(span_id)
    return result


def _facts_with_same_project_source_spans(
    session: Session,
    project_id: UUID,
    facts: list[FactAssertionRecord],
) -> list[FactAssertionRecord]:
    return [
        fact
        for fact in facts
        if _valid_source_span_id_strings(session, project_id, fact.evidence_span_ids)
    ]


def _fact_source_span_ids(
    session: Session,
    project_id: UUID,
    facts: list[FactAssertionRecord],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for fact in facts:
        for span_id in _valid_source_span_id_strings(session, project_id, fact.evidence_span_ids):
            if span_id in seen:
                continue
            seen.add(span_id)
            result.append(span_id)
    return result


def _format_fact(fact: FactAssertionRecord) -> str:
    return f"{_ref_label(fact.subject_ref)} {fact.predicate} {_ref_label(fact.object_ref)}"


def _memory_answer_confidence(facts: list[FactAssertionRecord]) -> float:
    if not facts:
        return 0.0
    return float(min(fact.confidence for fact in facts))


def _memory_answer_confidence_with_scoped_alias_cap(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
) -> float:
    confidence = _memory_answer_confidence(facts)
    alias_cap = _memory_answer_scoped_alias_confidence_cap(session, input_data, facts)
    if alias_cap is None:
        return confidence
    return min(confidence, alias_cap)


def _memory_answer_confidence_with_evidence_caps(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
    *,
    embedding_client: EmbeddingClient | None,
) -> float:
    confidence = _memory_answer_confidence_with_scoped_alias_cap(session, input_data, facts)
    semantic_cap = _memory_answer_semantic_fact_confidence_cap(
        session,
        input_data,
        facts,
        embedding_client=embedding_client,
    )
    if semantic_cap is None:
        return confidence
    return min(confidence, semantic_cap)


def _memory_answer_semantic_fact_confidence_cap(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
    *,
    embedding_client: EmbeddingClient | None,
) -> float | None:
    if (
        embedding_client is None
        or input_data.subject_ref is not None
        or input_data.predicate is not None
        or not facts
    ):
        return None

    semantic_recall = _memory_answer_semantic_recall_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        embedding_client=embedding_client,
    )
    if semantic_recall is None:
        return None

    span_scores = _memory_answer_semantic_source_span_scores(semantic_recall)
    if not span_scores:
        return None

    fact_scores: list[float] = []
    for fact in facts:
        fact_span_scores = [
            span_scores[span_id]
            for span_id in _valid_source_span_id_strings(
                session,
                input_data.project_id,
                fact.evidence_span_ids,
            )
            if span_id in span_scores
        ]
        if not fact_span_scores:
            return None
        fact_scores.append(max(fact_span_scores))

    return min(fact_scores) if fact_scores else None


def _memory_answer_affected_entities(
    facts: list[FactAssertionRecord],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for fact in facts:
        for ref in (fact.subject_ref, fact.object_ref):
            copied = dict(ref)
            key = json.dumps(copied, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(copied)
    return result


def _memory_answer_knowledge_affected_entities(
    matches: list[tuple[CharacterKnowledge, FactAssertionRecord]],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for _knowledge, fact in matches:
        for ref in (fact.subject_ref, fact.object_ref):
            copied = dict(ref)
            key = json.dumps(copied, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(copied)
    return result


def _character_knowledge_span_ids(
    session: Session,
    project_id: UUID,
    matches: list[tuple[CharacterKnowledge, FactAssertionRecord]],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for knowledge, fact in matches:
        span_ids = [
            *_valid_source_span_id_strings(session, project_id, fact.evidence_span_ids),
            *_valid_source_span_id_strings(session, project_id, [knowledge.evidence_span_id]),
        ]
        for span_id in span_ids:
            if span_id not in seen:
                seen.add(span_id)
                result.append(span_id)
    return result


def _character_knowledge_safe_for_pov(
    matches: list[tuple[CharacterKnowledge, FactAssertionRecord]],
    pov_character_id: UUID | None,
) -> bool:
    if not matches:
        return False
    if pov_character_id is None:
        return True
    return all(knowledge.character_id == pov_character_id for knowledge, _fact in matches)


def _memory_answer_caveats(
    *,
    has_non_canon_evidence: bool,
    has_open_review_items: bool,
    safe_to_use_in_current_pov: bool,
) -> list[str]:
    caveats: list[str] = []
    if has_non_canon_evidence:
        caveats.append("non_canon_evidence")
    if has_open_review_items:
        caveats.append("open_review_item")
    if not safe_to_use_in_current_pov and not caveats:
        caveats.append("not_safe_for_current_pov")
    return caveats


def _memory_answer_character_knowledge_caveats(
    matches: list[tuple[CharacterKnowledge, FactAssertionRecord]],
    *,
    has_non_canon_evidence: bool,
    has_open_review_items: bool,
    safe_to_use_in_current_pov: bool,
) -> list[str]:
    caveats = _memory_answer_caveats(
        has_non_canon_evidence=has_non_canon_evidence,
        has_open_review_items=has_open_review_items,
        safe_to_use_in_current_pov=safe_to_use_in_current_pov,
    )
    certainties = {knowledge.certainty for knowledge, _fact in matches}
    for certainty, caveat in (
        ("suspected", "suspected_knowledge"),
        ("false_belief", "false_belief_knowledge"),
        ("misunderstands", "misunderstood_knowledge"),
        ("does_not_know", "explicit_unknown_knowledge"),
    ):
        if certainty in certainties and caveat not in caveats:
            caveats.append(caveat)
    return caveats


def _format_character_knowledge_answer(
    knowledge: CharacterKnowledge,
    fact: FactAssertionRecord,
) -> str:
    subject = _ref_label(fact.subject_ref)
    target = _ref_label(fact.object_ref)
    if knowledge.certainty == "does_not_know":
        return f"{subject} does not know {target} ({knowledge.certainty})"
    if knowledge.certainty in {"misunderstands", "false_belief"}:
        return f"{subject} misunderstands {target} ({knowledge.certainty})"
    if knowledge.certainty == "suspected":
        return f"{subject} suspects {target} ({knowledge.certainty})"
    return f"{subject} knows {target} ({knowledge.certainty})"


def _ref_label(ref: dict[str, object]) -> str:
    if "label" in ref:
        return str(ref["label"])
    if "name" in ref:
        return str(ref["name"])
    if "id" in ref:
        return str(ref["id"])
    return str(ref)


def _canonical_entity_ref(entity: StoryCanonicalEntity) -> dict[str, object]:
    return {
        "type": entity.entity_type,
        "id": str(entity.id),
        "label": entity.display_name,
        "canonical_entity_id": str(entity.id),
        "slug": _slug(entity.display_name),
    }


def _alias_entity_ref(
    alias: StoryAliasRecord,
    entity: StoryCanonicalEntity | None,
) -> dict[str, object]:
    ref_id = str(entity.id) if entity is not None else _slug(alias.alias_text)
    ref: dict[str, object] = {
        "type": entity.entity_type if entity is not None else _entity_type_for_alias(alias),
        "id": ref_id,
        "label": entity.display_name if entity is not None else alias.alias_text,
        "slug": _slug(alias.alias_text),
    }
    if entity is not None:
        ref["canonical_entity_id"] = str(entity.id)
    return ref


def _entity_type_for_alias(alias: StoryAliasRecord) -> str:
    if alias.alias_type in {
        "character",
        "location",
        "faction",
        "object",
        "event",
        "scene",
        "chapter",
        "plotline",
        "lore",
        "source",
        "other",
    }:
        return alias.alias_type
    return "character"


def _slug(value: str) -> str:
    slug = re.sub(r"[^\w]+", "-", value.casefold()).replace("_", "-").strip("-")
    return slug or "unknown"


def _fact_source_span_id_map(
    session: Session,
    project_id: UUID,
    facts: list[FactAssertionRecord],
) -> dict[str, list[str]]:
    return {
        str(fact.id): _valid_source_span_id_strings(session, project_id, fact.evidence_span_ids)
        for fact in facts
    }


def _fact_entry(
    fact: FactAssertionRecord,
    *,
    evidence_span_ids: list[str] | None = None,
) -> dict[str, object]:
    return {
        "fact_id": str(fact.id),
        "subject_ref": fact.subject_ref,
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "fact_status": fact.fact_status,
        "confidence": fact.confidence,
        "evidence_span_ids": list(evidence_span_ids)
        if evidence_span_ids is not None
        else [str(span_id) for span_id in fact.evidence_span_ids],
    }


def _fact_entry_with_relevance(
    fact: FactAssertionRecord,
    scope: dict[str, Any],
    *,
    fact_span_ids_by_id: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    entry = _fact_entry(
        fact,
        evidence_span_ids=fact_span_ids_by_id.get(str(fact.id))
        if fact_span_ids_by_id is not None
        else None,
    )
    entry["relevance"] = _fact_relevance(fact, scope)
    return entry


def _ranked_fact_entries(
    facts: list[FactAssertionRecord],
    scope: dict[str, Any],
    *,
    fact_span_ids_by_id: dict[str, list[str]] | None = None,
) -> list[dict[str, object]]:
    ranked = [
        _fact_entry_with_relevance(
            fact,
            scope,
            fact_span_ids_by_id=fact_span_ids_by_id,
        )
        for fact in facts
    ]
    ranked.sort(
        key=lambda entry: (
            -_entry_relevance_score(entry),
            str(entry["fact_id"]),
        )
    )
    return ranked


def _fact_relevance(fact: FactAssertionRecord, scope: dict[str, Any]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    current_scene_id = cast(str | None, scope.get("current_scene_id"))
    if current_scene_id and (
        _fact_has_evidence_in_scene(fact, current_scene_id, scope)
        or str(fact.valid_from_scene_id) == current_scene_id
        or _ref_matches_id(fact.object_ref, current_scene_id)
        or _ref_matches_id(fact.subject_ref, current_scene_id)
    ):
        score += 70
        reasons.append("current_scene_evidence")
    if _fact_has_evidence_in_source(fact, scope):
        score += 10
        reasons.append("current_source_evidence")
    if _fact_has_evidence_in_version(fact, scope):
        score += 15
        reasons.append("current_version_evidence")
    if _fact_references_any(fact, cast(list[dict[str, object]], scope["active_characters"])):
        score += 40
        reasons.append("active_character")
    current_pov_character_id = cast(str | None, scope.get("current_pov_character_id"))
    if current_pov_character_id and (
        _ref_matches_id(fact.subject_ref, current_pov_character_id)
        or _ref_matches_id(fact.object_ref, current_pov_character_id)
    ):
        score += 20
        reasons.append("pov_character")
    query_overlap = _payload_query_overlap(
        {
            "subject_ref": fact.subject_ref,
            "predicate": fact.predicate,
            "object_ref": fact.object_ref,
        },
        scope,
    )
    if query_overlap:
        score += min(45, query_overlap * 15)
        reasons.append("intent_match")
    if _fact_matches_semantic_recall(fact, scope):
        score += _semantic_fact_relevance_points(fact, scope)
        reasons.append("semantic_recall")
    return {"score": score, "reasons": reasons or ["background_context"]}


def _entry_relevance_score(entry: dict[str, object]) -> int:
    relevance = cast(dict[str, object], entry.get("relevance", {}))
    score = relevance.get("score", 0)
    if isinstance(score, int):
        return score
    if isinstance(score, float):
        return int(score)
    return 0


def _scene_context(session: Session, scene_id: UUID | None) -> dict[str, object | None] | None:
    if scene_id is None:
        return None
    scene = session.get(StoryScene, scene_id)
    if scene is None:
        return None
    return {
        "scene_id": str(scene.id),
        "location_entity_id": str(scene.location_entity_id) if scene.location_entity_id else None,
        "pov_character_id": str(scene.pov_character_id) if scene.pov_character_id else None,
        "pov_mode": scene.pov_mode,
        "pov_confidence": scene.pov_confidence,
        "pov_evidence_span_ids": scene.pov_evidence_span_ids,
        "pov_uncertainty_reason": scene.pov_uncertainty_reason,
        "story_time": scene.story_time,
        "emotional_tone": scene.emotional_tone,
        "scene_function": scene.scene_function,
    }


def _chapter_context_for_scene(session: Session, scene_id: UUID | None) -> dict[str, object] | None:
    if scene_id is None:
        return None
    scene = session.get(StoryScene, scene_id)
    if scene is None:
        return None
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return None
    return {
        "chapter_id": str(chapter.id),
        "chapter_index": chapter.chapter_index,
        "title": chapter.title,
    }


def _pov_sensory_limits(scene_context: dict[str, object | None] | None) -> dict[str, object]:
    if scene_context is None:
        return {"scope": "unknown", "scene_id": None, "location_entity_id": None}
    return {
        "scope": "current_scene",
        "scene_id": scene_context.get("scene_id"),
        "location_entity_id": scene_context.get("location_entity_id"),
    }


def _pov_inner_access(
    current_pov_character_id: UUID | None, pov_mode: object | None
) -> dict[str, object]:
    if str(pov_mode) == "omniscient":
        return {"allowed_character_ids": ["*"], "non_pov_inner_state": "allowed_by_pov_mode"}
    if current_pov_character_id is None:
        return {"allowed_character_ids": [], "non_pov_inner_state": "forbidden"}
    non_pov_rule = "requires_explicit_transition" if str(pov_mode) == "multiple" else "forbidden"
    return {
        "allowed_character_ids": [str(current_pov_character_id)],
        "non_pov_inner_state": non_pov_rule,
    }


def _unique_refs(refs: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for ref in refs:
        key = (str(ref.get("type")), str(ref.get("id")))
        if key not in seen:
            seen.add(key)
            result.append(dict(ref))
    return result


REVIEW_THREAD_UPDATE_TYPES = frozenset(("opens", "keeps_open", "narrows", "pays_off", "closes"))
REVIEW_ACTIVE_THREAD_UPDATE_TYPES = frozenset(("opens", "keeps_open", "narrows"))


def _is_proposed_thread_update_review(review_item: ReviewItemRecord) -> bool:
    return (
        review_item.review_type == "continuity_warning"
        and review_item.affected_refs.get("type") == "proposed_thread_update"
    )


def _find_memory_page_for_target_ref(
    session: Session,
    *,
    project_id: UUID,
    target_ref: dict[str, object],
) -> MemoryPage | None:
    page_type = str(target_ref.get("type"))
    pages = (
        session.query(MemoryPage)
        .filter_by(project_id=project_id)
        .where(MemoryPage.page_type == page_type)
        .all()
    )
    for page in pages:
        if refs_equivalent(page.target_ref, target_ref):
            return page
    return None


def _source_delta_for_thread_update_span(
    session: Session,
    *,
    project_id: UUID,
    span: SourceSpan,
) -> SourceDeltaRecord | None:
    span_id = str(span.id)
    audits = (
        session.query(AuditEvent)
        .filter_by(project_id=project_id, event_type="source.span_extracted")
        .all()
    )
    for audit in audits:
        if str(audit.decision.get("source_span_id")) != span_id:
            continue
        subject_ref = audit.subject_ref
        if subject_ref.get("type") != "source_delta" or subject_ref.get("id") is None:
            continue
        try:
            delta_id = UUID(str(subject_ref["id"]))
        except ValueError:
            continue
        delta = session.get(SourceDeltaRecord, delta_id)
        if delta is not None and delta.project_id == project_id:
            return delta

    return (
        session.query(SourceDeltaRecord)
        .filter_by(project_id=project_id, source_id=span.source_id)
        .filter(
            or_(
                SourceDeltaRecord.previous_version_id == span.version_id,
                SourceDeltaRecord.new_version_id == span.version_id,
            )
        )
        .order_by(SourceDeltaRecord.created_at.desc(), SourceDeltaRecord.id.desc())
        .first()
    )


def _apply_thread_entry(
    session: Session,
    open_threads: list[dict[str, object]],
    thread_entry: dict[str, object],
    *,
    project_id: UUID,
) -> list[dict[str, object]]:
    threads = [dict(thread) for thread in open_threads]
    new_span_ids = thread_entry.get("source_span_ids", [])
    new_span_id_values = (
        [str(item) for item in new_span_ids] if isinstance(new_span_ids, list) else []
    )
    for index, thread in enumerate(threads):
        if thread.get("id") != thread_entry["id"]:
            continue
        previous_span_ids = thread.get("source_span_ids", [])
        previous_span_id_values = set()
        if isinstance(previous_span_ids, list):
            previous_span_id_values = {str(item) for item in previous_span_ids}
        valid_previous_span_ids = [
            str(span_id)
            for span_id in _source_span_ids_to_uuids(
                session,
                project_id,
                previous_span_id_values,
            )
        ]
        merged_span_ids = _merge_text_values(
            valid_previous_span_ids,
            new_span_id_values,
        )
        threads[index] = {**thread, **thread_entry, "source_span_ids": merged_span_ids}
        return threads
    return threads + [thread_entry]


def _thread_update_review_status(update_type: str) -> str:
    if update_type in REVIEW_ACTIVE_THREAD_UPDATE_TYPES:
        return "open"
    if update_type == "pays_off":
        return "resolved"
    return "closed"


def _ensure_thread_update_applied_evidence(
    session: Session,
    *,
    project_id: UUID,
    page_id: UUID,
    thread_id: str,
    source_span_ids: list[str],
) -> EvidenceLogEntry:
    target_ref = {
        "type": "memory_page_thread",
        "id": thread_id,
        "memory_page_id": str(page_id),
    }
    source_span_id_set = set(source_span_ids)
    for entry in session.query(EvidenceLogEntry).filter_by(
        project_id=project_id,
        log_type="thread_update",
    ):
        if entry.target_ref == target_ref and source_span_id_set.issubset(
            set(entry.source_span_ids)
        ):
            return entry

    evidence = EvidenceLogEntry(
        id=uuid4(),
        project_id=project_id,
        log_type="thread_update",
        target_ref=target_ref,
        fact_id=None,
        event_id=None,
        source_span_ids=source_span_ids,
        log_status="written",
    )
    session.add(evidence)
    session.flush()
    return evidence


def _persist_review_replacement_evidence(
    review_item: ReviewItemRecord,
    input_data: ReviewItemOperationInput,
) -> None:
    replacement_refs = _unique_refs(input_data.replacement_refs or [])
    if not replacement_refs:
        return

    affected_refs = dict(review_item.affected_refs or {})
    for ref_type, affected_key in (
        ("source_delta", "replacement_source_delta_ids"),
        ("review_item", "replacement_review_item_ids"),
        ("source_span", "replacement_source_span_ids"),
    ):
        replacement_ids = [
            str(ref["id"])
            for ref in replacement_refs
            if ref.get("type") == ref_type and ref.get("id") is not None
        ]
        if not replacement_ids:
            continue
        affected_refs[affected_key] = _merge_text_values(
            affected_refs.get(affected_key),
            replacement_ids,
        )
    review_item.affected_refs = affected_refs

    new_evidence = dict(review_item.new_evidence or {})
    new_evidence["resolution_replacement_refs"] = replacement_refs
    review_item.new_evidence = new_evidence


def _merge_text_values(existing: object, additions: list[str]) -> list[str]:
    values: list[str] = []
    existing_values = existing if isinstance(existing, list) else []
    for value in existing_values:
        values.append(str(value))
    for value in additions:
        if value not in values:
            values.append(value)
    return values


def _merge_dict_values(
    existing: list[dict[str, Any]],
    additions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    values = [dict(value) for value in existing if isinstance(value, dict)]
    seen = {json.dumps(value, sort_keys=True) for value in values}
    for addition in additions:
        if not isinstance(addition, dict):
            continue
        candidate = dict(addition)
        key = json.dumps(candidate, sort_keys=True)
        if key in seen:
            continue
        values.append(candidate)
        seen.add(key)
    return values


def _source_span_ids_from_refs(refs: list[dict[str, object]]) -> list[UUID]:
    ids: list[UUID] = []
    seen: set[UUID] = set()
    for ref in refs:
        if ref.get("type") != "source_span" or ref.get("id") is None:
            continue
        try:
            span_id = UUID(str(ref["id"]))
        except ValueError:
            continue
        if span_id not in seen:
            seen.add(span_id)
            ids.append(span_id)
    return ids


def _memory_writeback_decision_changes_context(
    input_data: MemoryWritebackDecisionInput, side_effects: dict[str, object]
) -> bool:
    if input_data.item_ref.get("type") == "review_item" and side_effects.get("policy_action") in {
        "review_item_dismissed",
        "review_item_correction_recorded",
    }:
        return True
    if side_effects.get("fact_assertion_status") in {"canon", "disputed"}:
        return True
    if side_effects.get("memory_pages") in {"marked_stale", "updated"}:
        return True
    if side_effects.get("graph_projection") in {"rebuilt", "marked_stale"}:
        return True
    return any(
        _side_effect_count(side_effects, key) > 0
        for key in (
            "memory_pages_marked_stale",
            "memory_pages_updated",
            "graph_edges_marked_disputed",
            "graph_edges_marked_stale",
            "review_items_resolved",
        )
    )


def _side_effect_count(side_effects: dict[str, object], key: str) -> int:
    value = side_effects.get(key)
    return value if isinstance(value, int) else 0


def _source_span_ids_for_writeback_decision(
    session: Session,
    *,
    project_id: UUID,
    item_ref: dict[str, object],
    side_effects: dict[str, object],
) -> list[UUID]:
    span_ids = _source_span_ids_for_item_ref(session, project_id, item_ref)
    for page_id in _side_effect_text_values(side_effects, "memory_page_ids"):
        try:
            page = session.get(MemoryPage, UUID(page_id))
        except ValueError:
            continue
        if page is not None and page.project_id == project_id:
            span_ids.update(_memory_page_context_source_span_ids(session, page))
    for edge_id in _side_effect_text_values(side_effects, "graph_edge_ids"):
        try:
            edge = session.get(GraphProjectionEdge, UUID(edge_id))
        except ValueError:
            continue
        if edge is not None and edge.project_id == project_id:
            span_ids.update(_graph_edge_source_span_ids(session, edge))
    for review_id in _side_effect_text_values(side_effects, "review_item_ids"):
        try:
            review = session.get(ReviewItemRecord, UUID(review_id))
        except ValueError:
            continue
        if review is not None and review.project_id == project_id:
            span_ids.update(
                str(span_id) for span_id in _review_context_source_span_ids(session, review)
            )
    return _source_span_ids_to_uuids(session, project_id, span_ids)


def _source_span_ids_for_item_ref(
    session: Session, project_id: UUID, item_ref: dict[str, object]
) -> set[str]:
    ref_type = item_ref.get("type")
    ref_id = item_ref.get("id")
    if ref_id is None:
        return set()
    try:
        entity_id = UUID(str(ref_id))
    except ValueError:
        return set()

    if ref_type == "source_span":
        span = session.get(SourceSpan, entity_id)
        if span is not None and _source_span_belongs_to_project(session, span, project_id):
            return {str(span.id)}
        return set()
    if ref_type == "fact_assertion":
        fact = session.get(FactAssertionRecord, entity_id)
        if fact is not None and fact.project_id == project_id:
            return {str(span_id) for span_id in fact.evidence_span_ids}
        return set()
    if ref_type == "evidence_log_entry":
        entry = session.get(EvidenceLogEntry, entity_id)
        if entry is not None and entry.project_id == project_id:
            return {str(span_id) for span_id in entry.source_span_ids}
        return set()
    if ref_type == "memory_page":
        page = session.get(MemoryPage, entity_id)
        if page is not None and page.project_id == project_id:
            return _memory_page_context_source_span_ids(session, page)
        return set()
    if ref_type == "graph_edge":
        edge = session.get(GraphProjectionEdge, entity_id)
        if edge is not None and edge.project_id == project_id:
            return _graph_edge_source_span_ids(session, edge)
        return set()
    if ref_type == "review_item":
        review = session.get(ReviewItemRecord, entity_id)
        if review is not None and review.project_id == project_id:
            return {str(span_id) for span_id in _review_context_source_span_ids(session, review)}
    return set()


def _source_span_ids_to_uuids(session: Session, project_id: UUID, span_ids: set[str]) -> list[UUID]:
    parsed: list[UUID] = []
    seen: set[UUID] = set()
    for span_id in sorted(span_ids):
        try:
            span_uuid = UUID(str(span_id))
        except ValueError:
            continue
        if span_uuid in seen:
            continue
        span = session.get(SourceSpan, span_uuid)
        if span is None or not _source_span_belongs_to_project(session, span, project_id):
            continue
        seen.add(span_uuid)
        parsed.append(span_uuid)
    return parsed


def _fact_dispute_source_span_ids(
    session: Session,
    project_id: UUID,
    facts: list[FactAssertionRecord],
    evidence_span_ids: set[str] | None,
) -> list[str]:
    raw_span_ids = {str(span_id) for span_id in evidence_span_ids or set() if span_id is not None}
    if not raw_span_ids:
        for fact in facts:
            if fact.project_id != project_id:
                continue
            raw_span_ids.update(str(span_id) for span_id in fact.evidence_span_ids)
    return [
        str(span_id) for span_id in _source_span_ids_to_uuids(session, project_id, raw_span_ids)
    ]


def _sanitized_memory_page_source_refs(
    session: Session,
    project_id: UUID,
    source_refs: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    valid_span_ids = set(
        _valid_source_span_id_strings(
            session,
            project_id,
            (
                ref.get("id")
                for ref in source_refs
                if ref.get("type") == "source_span" and ref.get("id") is not None
            ),
        )
    )
    result: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for ref in source_refs:
        ref_type = ref.get("type")
        raw_id = ref.get("id")
        ref_id = _uuid_or_none(raw_id)
        if ref_id is None:
            continue
        if ref_type == "source_delta":
            source_delta = session.get(SourceDeltaRecord, ref_id)
            if source_delta is None or source_delta.project_id != project_id:
                continue
        elif ref_type == "source_span":
            if str(ref_id) not in valid_span_ids:
                continue
        else:
            continue
        key = (str(ref_type), str(ref_id))
        if key in seen:
            continue
        seen.add(key)
        result.append({"type": str(ref_type), "id": str(ref_id)})
    return result


def _side_effect_affected_refs(side_effects: dict[str, object]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    refs.extend(_side_effect_id_refs(side_effects, "memory_page_ids", "memory_page"))
    refs.extend(_side_effect_id_refs(side_effects, "graph_edge_ids", "graph_edge"))
    refs.extend(_side_effect_id_refs(side_effects, "review_item_ids", "review_item"))
    refs.extend(_side_effect_id_refs(side_effects, "memory_page_rewrite_job_ids", "job"))
    refs.extend(
        _side_effect_id_refs(
            side_effects,
            "fact_assertion_ids_retired",
            "fact_assertion",
        )
    )
    if run_id := side_effects.get("graph_projection_run_id"):
        refs.append({"type": "graph_projection_run", "id": str(run_id)})
    return refs


def _side_effect_id_refs(
    side_effects: dict[str, object], key: str, ref_type: str
) -> list[dict[str, object]]:
    return [
        {"type": ref_type, "id": value} for value in _side_effect_text_values(side_effects, key)
    ]


def _side_effect_text_values(side_effects: dict[str, object], key: str) -> list[str]:
    value = side_effects.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, str):
        return [value]
    return []


def _memory_page_context_source_span_ids(session: Session, page: MemoryPage) -> set[str]:
    span_ids = set(_memory_page_source_span_ids(page))
    facts = page.current_canon.get("facts", [])
    if isinstance(facts, list):
        for entry in facts:
            if not isinstance(entry, dict):
                continue
            evidence_ids = entry.get("evidence_span_ids", [])
            if isinstance(evidence_ids, list):
                span_ids.update(str(span_id) for span_id in evidence_ids)
            fact_id = entry.get("fact_id")
            if fact_id is None:
                continue
            try:
                fact = session.get(FactAssertionRecord, UUID(str(fact_id)))
            except ValueError:
                continue
            if fact is not None and fact.project_id == page.project_id:
                span_ids.update(str(span_id) for span_id in fact.evidence_span_ids)
    return span_ids


def _graph_edge_source_span_ids(session: Session, edge: GraphProjectionEdge) -> set[str]:
    span_ids = {
        str(ref.get("id"))
        for ref in edge.evidence_refs
        if ref.get("type") == "source_span" and ref.get("id") is not None
    }
    if edge.source_ref.get("type") == "fact_assertion" and edge.source_ref.get("id"):
        try:
            fact = session.get(FactAssertionRecord, UUID(str(edge.source_ref["id"])))
        except ValueError:
            fact = None
        if fact is not None and fact.project_id == edge.project_id:
            span_ids.update(str(span_id) for span_id in fact.evidence_span_ids)
    return span_ids


def _review_context_source_span_ids(session: Session, review_item: ReviewItemRecord) -> list[UUID]:
    span_ids = set(_review_source_span_ids(review_item))
    for fact_id in _uuid_values(review_item.affected_refs, "fact_id", "fact_ids"):
        fact = session.get(FactAssertionRecord, fact_id)
        if fact is not None and fact.project_id == review_item.project_id:
            span_ids.update(str(span_id) for span_id in fact.evidence_span_ids)
    for page_id in _uuid_values(review_item.affected_refs, "memory_page_id", "memory_page_ids"):
        page = session.get(MemoryPage, page_id)
        if page is not None and page.project_id == review_item.project_id:
            span_ids.update(_memory_page_context_source_span_ids(session, page))
    return _source_span_ids_to_uuids(session, review_item.project_id, span_ids)


def _review_source_span_id_map(
    session: Session,
    project_id: UUID,
    reviews: list[ReviewItemRecord],
) -> dict[str, list[str]]:
    span_ids_by_review_id: dict[str, list[str]] = {}
    for review in reviews:
        if review.project_id != project_id:
            continue
        span_ids = [str(span_id) for span_id in _review_context_source_span_ids(session, review)]
        if span_ids:
            span_ids_by_review_id[str(review.id)] = span_ids
    return span_ids_by_review_id


def _active_characters(
    facts: list[FactAssertionRecord], *, current_scene_id: UUID | None = None
) -> list[dict[str, object]]:
    if current_scene_id is not None:
        scene_id = str(current_scene_id)
        scene_refs = [
            fact.subject_ref
            for fact in facts
            if fact.predicate == "appears_in"
            and fact.object_ref.get("type") == "scene"
            and str(fact.object_ref.get("id")) == scene_id
            and fact.subject_ref.get("type") == "character"
        ]
        if scene_refs:
            return _unique_refs(scene_refs)

    refs: list[dict[str, object]] = []
    for fact in facts:
        for ref in (fact.subject_ref, fact.object_ref):
            if ref.get("type") == "character":
                refs.append(ref)
    return _unique_refs(refs)


def _character_agency_state(
    *,
    session: Session,
    project_id: UUID,
    active_characters: list[dict[str, object]],
    canonical_facts: list[FactAssertionRecord],
    recent_events: list[dict[str, object]],
    object_location_state: list[dict[str, object]],
    open_reviews: list[ReviewItemRecord],
    memory_pages: list[MemoryPage],
    fact_span_ids_by_id: dict[str, list[str]],
) -> dict[str, object]:
    if not active_characters:
        return {"status": "not_computed", "source": "memory"}

    knowledge_by_character_id = _active_character_knowledge(
        session,
        project_id=project_id,
        active_characters=active_characters,
    )
    characters: list[dict[str, object]] = []
    for character_ref in active_characters[:6]:
        character_id = _uuid_or_none(character_ref.get("id"))
        knowledge_state = (
            knowledge_by_character_id.get(character_id, []) if character_id is not None else []
        )
        canon_facts = [
            _agency_fact_entry(fact, fact_span_ids_by_id)
            for fact in canonical_facts
            if _fact_references_character(fact, character_ref)
        ]
        recent_event_pressures = [
            _agency_event_entry(event)
            for event in recent_events
            if _event_references_character(event, character_ref)
        ]
        object_state = [
            _agency_object_state_entry(edge)
            for edge in object_location_state
            if _same_ref(cast(dict[str, object], edge["subject_ref"]), character_ref)
        ]
        open_threads = [
            thread
            for page in memory_pages
            if _same_ref(page.target_ref, character_ref)
            for thread in _context_pack_open_threads_for_page(session, project_id, page)
        ]
        risk_notes = [
            _agency_risk_entry(review)
            for review in open_reviews
            if _review_references_character(review, character_ref)
        ]
        natural_next_action = _natural_next_action(risk_notes)
        character_state: dict[str, object] = {
            "character_ref": character_ref,
            "canon_facts": canon_facts,
            "recent_event_pressures": recent_event_pressures,
            "object_state": object_state,
            "knowledge_state": [
                _character_knowledge_entry(knowledge) for knowledge in knowledge_state
            ],
            "open_threads": open_threads,
            "risk_notes": risk_notes,
            "natural_next_action": natural_next_action,
        }
        agency_profile = _agency_profile_for_character(
            session=session,
            project_id=project_id,
            memory_pages=memory_pages,
            character_ref=character_ref,
        )
        if agency_profile:
            character_state.update(agency_profile)
            agency_pass = _agency_pass_from_profile(
                agency_profile,
                natural_next_action=natural_next_action,
            )
            if agency_pass:
                character_state["agency_pass"] = agency_pass
        characters.append(character_state)
    return {"status": "computed", "source": "memory", "characters": characters}


def _agency_profile_for_character(
    *,
    session: Session,
    project_id: UUID,
    memory_pages: list[MemoryPage],
    character_ref: dict[str, object],
) -> dict[str, object]:
    page = next(
        (
            memory_page
            for memory_page in memory_pages
            if memory_page.page_type == "character"
            and _same_ref(memory_page.target_ref, character_ref)
        ),
        None,
    )
    if page is None or page.canon_status not in {"current", "rebuilt"}:
        return {}

    current_canon = page.current_canon if isinstance(page.current_canon, dict) else {}
    raw_profile = current_canon.get("agency_profile")
    if not isinstance(raw_profile, dict):
        return {}

    fallback_span_ids = _valid_source_span_id_strings(
        session,
        project_id,
        _memory_page_source_span_ids(page),
    )
    profile: dict[str, object] = {}
    for source_key, output_key in AGENCY_PROFILE_SCALAR_FIELDS:
        entry = _agency_profile_scalar_entry(
            session=session,
            project_id=project_id,
            raw_value=raw_profile.get(source_key),
            fallback_span_ids=fallback_span_ids,
        )
        if entry is not None:
            profile[output_key] = entry
    for source_key, output_key in AGENCY_PROFILE_LIST_FIELDS:
        entries = _agency_profile_list_entries(
            session=session,
            project_id=project_id,
            raw_value=raw_profile.get(source_key),
            fallback_span_ids=fallback_span_ids,
        )
        if entries:
            profile[output_key] = entries
    return profile


def _agency_profile_scalar_entry(
    *,
    session: Session,
    project_id: UUID,
    raw_value: object,
    fallback_span_ids: list[str],
) -> dict[str, object] | None:
    if raw_value is None:
        return None
    entry = _agency_profile_entry(
        session=session,
        project_id=project_id,
        raw_value=raw_value,
        fallback_span_ids=fallback_span_ids,
    )
    return entry if entry and isinstance(entry.get("value"), str) else None


def _agency_profile_list_entries(
    *,
    session: Session,
    project_id: UUID,
    raw_value: object,
    fallback_span_ids: list[str],
) -> list[dict[str, object]]:
    raw_items = raw_value if isinstance(raw_value, list) else [raw_value]
    entries: list[dict[str, object]] = []
    for raw_item in raw_items:
        entry = _agency_profile_entry(
            session=session,
            project_id=project_id,
            raw_value=raw_item,
            fallback_span_ids=fallback_span_ids,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def _agency_profile_entry(
    *,
    session: Session,
    project_id: UUID,
    raw_value: object,
    fallback_span_ids: list[str],
) -> dict[str, object] | None:
    if isinstance(raw_value, str):
        value = raw_value.strip()
        raw_span_ids: Iterable[object] = fallback_span_ids
        has_explicit_span_ids = False
        target_ref: object = None
    elif isinstance(raw_value, dict):
        raw_entry = cast(dict[str, object], raw_value)
        value = _agency_profile_text(raw_entry)
        source_ids = raw_entry.get("source_span_ids", raw_entry.get("evidence_span_ids", []))
        raw_span_ids = source_ids if isinstance(source_ids, list) else []
        has_explicit_span_ids = bool(raw_span_ids)
        target_ref = raw_entry.get("target_ref")
    else:
        return None
    if not value:
        return None
    span_ids = _valid_source_span_id_strings(session, project_id, raw_span_ids)
    if not span_ids and not has_explicit_span_ids:
        span_ids = _valid_source_span_id_strings(session, project_id, fallback_span_ids)
    if not span_ids:
        return None
    entry: dict[str, object] = {"value": value, "source_span_ids": span_ids}
    if isinstance(target_ref, dict):
        entry["target_ref"] = target_ref
    return entry


def _agency_profile_text(raw_value: dict[str, object]) -> str:
    for key in ("value", "summary", "text", "description"):
        value = raw_value.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _agency_pass_from_profile(
    profile: dict[str, object],
    *,
    natural_next_action: str,
) -> dict[str, object] | None:
    source_span_ids = _agency_profile_source_span_ids(profile)
    if not source_span_ids:
        return None
    agency_rule = _agency_profile_entry_value(profile.get("agency_rule"))
    pressure = _agency_profile_entry_value(profile.get("pressure"))
    moral_boundary = _agency_profile_entry_value(profile.get("moral_boundary"))
    core_desire = _agency_profile_entry_value(profile.get("core_desire"))
    relationship_stance = _agency_profile_first_list_value(profile.get("relationship_stance"))
    return {
        "natural_action": natural_next_action,
        "likely_dialogue_move": agency_rule or natural_next_action,
        "hidden_pressure": pressure or "",
        "forbidden_action": moral_boundary or "",
        "agency_rationale": core_desire or "",
        "conflict_opportunity": relationship_stance or pressure or "",
        "source_span_ids": source_span_ids,
    }


def _agency_profile_entry_value(entry: object) -> str:
    if isinstance(entry, dict):
        value = cast(dict[str, object], entry).get("value")
        if isinstance(value, str):
            return value
    return ""


def _agency_profile_first_list_value(entry: object) -> str:
    if not isinstance(entry, list):
        return ""
    for item in entry:
        value = _agency_profile_entry_value(item)
        if value:
            return value
    return ""


def _agency_profile_source_span_ids(profile: dict[str, object]) -> list[str]:
    span_ids: list[str] = []
    for entry in profile.values():
        if isinstance(entry, list):
            for item in entry:
                if isinstance(item, dict):
                    span_ids.extend(
                        _agency_profile_entry_source_span_ids(cast(dict[str, object], item))
                    )
        elif isinstance(entry, dict):
            span_ids.extend(_agency_profile_entry_source_span_ids(cast(dict[str, object], entry)))
    return _unique_str_sequence(span_ids)


def _agency_profile_entry_source_span_ids(entry: dict[str, object]) -> list[str]:
    source_span_ids = entry.get("source_span_ids", [])
    if not isinstance(source_span_ids, list):
        return []
    return [str(span_id) for span_id in source_span_ids if span_id is not None]


def _active_character_knowledge(
    session: Session,
    *,
    project_id: UUID,
    active_characters: list[dict[str, object]],
) -> dict[UUID, list[CharacterKnowledge]]:
    character_ids = [
        character_id
        for character_id in (_uuid_or_none(ref.get("id")) for ref in active_characters[:6])
        if character_id is not None
    ]
    if not character_ids:
        return {}
    rows = (
        session.query(CharacterKnowledge)
        .filter(CharacterKnowledge.project_id == project_id)
        .filter(CharacterKnowledge.status == "active")
        .filter(CharacterKnowledge.character_id.in_(character_ids))
        .order_by(CharacterKnowledge.created_at, CharacterKnowledge.id)
        .all()
    )
    by_character_id: dict[UUID, list[CharacterKnowledge]] = {}
    for row in rows:
        by_character_id.setdefault(row.character_id, []).append(row)
    return by_character_id


def _agency_fact_entry(
    fact: FactAssertionRecord,
    fact_span_ids_by_id: dict[str, list[str]],
) -> dict[str, object]:
    return {
        "fact_id": str(fact.id),
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "evidence_span_ids": list(fact_span_ids_by_id.get(str(fact.id), [])),
    }


def _agency_event_entry(event: dict[str, object]) -> dict[str, object]:
    return {
        "event_id": str(event["event_id"]),
        "summary": str(event["summary"]),
        "consequence_summary": event["consequence_summary"],
    }


def _agency_object_state_entry(edge: dict[str, object]) -> dict[str, object]:
    return {
        "relation": str(edge["relation"]),
        "target_ref": cast(dict[str, object], edge["target_ref"]),
        "edge_status": str(edge["edge_status"]),
    }


def _agency_risk_entry(review: ReviewItemRecord) -> dict[str, object]:
    return {
        "review_item_id": str(review.id),
        "review_type": review.review_type,
        "summary": review.summary,
    }


def _natural_next_action(risk_notes: list[dict[str, object]]) -> str:
    if risk_notes:
        return "依据已确认事实行动，同时保留开放风险"
    return "依据已确认事实行动"


def _fact_references_character(fact: FactAssertionRecord, character_ref: dict[str, object]) -> bool:
    return _same_ref(fact.subject_ref, character_ref) or _same_ref(fact.object_ref, character_ref)


def _event_references_character(event: dict[str, object], character_ref: dict[str, object]) -> bool:
    participants = cast(list[dict[str, object]], event["participants"])
    return any(_same_ref(participant, character_ref) for participant in participants)


def _review_references_character(
    review: ReviewItemRecord, character_ref: dict[str, object]
) -> bool:
    character_id = str(character_ref.get("id", ""))
    character_label = str(character_ref.get("name") or character_ref.get("label") or "")
    payload = json.dumps(
        {
            "affected_refs": review.affected_refs,
            "new_evidence": review.new_evidence,
            "existing_evidence": review.existing_evidence,
            "summary": review.summary,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).casefold()
    return bool(
        character_id
        and character_id.casefold() in payload
        or character_label
        and character_label.casefold() in payload
    )


def _same_ref(first: dict[str, object], second: dict[str, object]) -> bool:
    return refs_equivalent(first, second)


def _character_knowledge_entry(item: CharacterKnowledge) -> dict[str, object]:
    return {
        "character_id": str(item.character_id),
        "knows_ref": item.knows_ref,
        "learned_in_scene_id": None
        if item.learned_in_scene_id is None
        else str(item.learned_in_scene_id),
        "evidence_span_id": str(item.evidence_span_id),
        "certainty": item.certainty,
        "hidden_from": item.hidden_from,
        "status": item.status,
    }


def _review_entry(
    review: ReviewItemRecord,
    *,
    review_span_ids_by_id: dict[str, list[str]],
) -> dict[str, object]:
    entry: dict[str, object] = {
        "review_item_id": str(review.id),
        "review_type": review.review_type,
        "severity": review.severity,
        "summary": review.summary,
        "new_evidence": _review_evidence_entry(
            review.new_evidence,
            review_span_ids_by_id.get(str(review.id), []),
        ),
        "evidence_span_ids": list(review_span_ids_by_id.get(str(review.id), [])),
    }
    existing_evidence = _review_evidence_entry(
        review.existing_evidence,
        review_span_ids_by_id.get(str(review.id), []),
    )
    if existing_evidence:
        entry["existing_evidence"] = existing_evidence
    return entry


def _ranked_review_entries(
    reviews: list[ReviewItemRecord],
    scope: dict[str, Any],
    *,
    review_span_ids_by_id: dict[str, list[str]],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for review in reviews:
        entry = _review_entry(review, review_span_ids_by_id=review_span_ids_by_id)
        entry["relevance"] = _review_relevance(
            review,
            scope,
            review_span_ids=review_span_ids_by_id.get(str(review.id), []),
        )
        entries.append(entry)
    entries.sort(
        key=lambda entry: (
            -_entry_relevance_score(entry),
            str(entry["review_item_id"]),
        )
    )
    return entries


def _review_relevance(
    review: ReviewItemRecord,
    scope: dict[str, Any],
    *,
    review_span_ids: list[str],
) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    span_ids = set(review_span_ids)
    if _span_ids_have_scene(span_ids, scope):
        score += 70
        reasons.append("current_scene_evidence")
    if _span_ids_have_source(span_ids, scope):
        score += 10
        reasons.append("current_source_evidence")
    if _span_ids_have_version(span_ids, scope):
        score += 15
        reasons.append("current_version_evidence")
    active_characters = cast(list[dict[str, object]], scope["active_characters"])
    if any(_review_references_character(review, ref) for ref in active_characters):
        score += 40
        reasons.append("active_character")
    current_pov_character_id = cast(str | None, scope.get("current_pov_character_id"))
    if (
        current_pov_character_id
        and current_pov_character_id.casefold()
        in json.dumps(
            {
                "affected_refs": review.affected_refs,
                "new_evidence": _review_evidence_entry(review.new_evidence, review_span_ids),
                "summary": review.summary,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).casefold()
    ):
        score += 20
        reasons.append("pov_character")
    query_overlap = _payload_query_overlap(
        {
            "summary": review.summary,
            "affected_refs": review.affected_refs,
            "new_evidence": _review_evidence_entry(review.new_evidence, review_span_ids),
        },
        scope,
    )
    if query_overlap:
        score += min(45, query_overlap * 15)
        reasons.append("intent_match")
    return {"score": score, "reasons": reasons or ["background_context"]}


def _review_evidence_entry(
    evidence: dict[str, object],
    valid_review_span_ids: list[str],
) -> dict[str, object]:
    entry = dict(evidence)
    if "source_span_ids" in entry:
        source_span_ids = entry.get("source_span_ids")
        if isinstance(source_span_ids, list):
            valid_set = set(valid_review_span_ids)
            valid_ids = [str(span_id) for span_id in source_span_ids if str(span_id) in valid_set]
            if valid_ids:
                entry["source_span_ids"] = valid_ids
            else:
                entry.pop("source_span_ids", None)
    return entry


def _open_threads(
    session: Session,
    project_id: UUID,
    memory_pages: list[MemoryPage],
) -> list[dict[str, object]]:
    threads: list[dict[str, object]] = []
    for page in memory_pages:
        threads.extend(_context_pack_open_threads_for_page(session, project_id, page))
    return threads


def _context_pack_open_threads_for_page(
    session: Session,
    project_id: UUID,
    page: MemoryPage,
) -> list[dict[str, object]]:
    threads: list[dict[str, object]] = []
    for thread in page.open_threads:
        if not isinstance(thread, dict):
            continue
        span_ids = thread.get("source_span_ids")
        if isinstance(span_ids, list):
            valid_span_ids = _valid_source_span_id_strings(session, project_id, span_ids)
        else:
            valid_span_ids = []
        if not valid_span_ids:
            valid_span_ids = _valid_source_span_id_strings(
                session,
                project_id,
                _memory_page_source_span_ids(page),
            )
        if not valid_span_ids:
            continue
        entry = dict(thread)
        entry["source_span_ids"] = valid_span_ids
        threads.append(entry)
    return threads


def _event_evidence_refs(events: list[dict[str, object]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for event in events:
        for span_id in cast(list[str], event["evidence_span_ids"]):
            refs.append({"type": "source_span", "id": span_id})
    return refs


def _ranked_event_entries(
    events: list[dict[str, object]],
    scope: dict[str, Any],
) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for event in events:
        entry = dict(event)
        entry["relevance"] = _event_relevance(entry, scope)
        ranked.append(entry)
    ranked.sort(
        key=lambda entry: (
            -_entry_relevance_score(entry),
            str(entry["event_id"]),
        )
    )
    return ranked


def _event_relevance(event: dict[str, object], scope: dict[str, Any]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    span_ids = cast(list[str], event.get("evidence_span_ids", []))
    if _span_ids_have_scene(span_ids, scope):
        score += 70
        reasons.append("current_scene_evidence")
    if _span_ids_have_source(span_ids, scope):
        score += 10
        reasons.append("current_source_evidence")
    if _span_ids_have_version(span_ids, scope):
        score += 15
        reasons.append("current_version_evidence")
    active_characters = cast(list[dict[str, object]], scope["active_characters"])
    participants = cast(list[dict[str, object]], event.get("participants", []))
    if any(
        _same_ref(participant, active)
        for participant in participants
        for active in active_characters
    ):
        score += 40
        reasons.append("active_character")
    current_pov_character_id = cast(str | None, scope.get("current_pov_character_id"))
    if current_pov_character_id and any(
        _ref_matches_id(participant, current_pov_character_id) for participant in participants
    ):
        score += 20
        reasons.append("pov_character")
    query_overlap = _payload_query_overlap(event, scope)
    if query_overlap:
        score += min(45, query_overlap * 15)
        reasons.append("intent_match")
    return {"score": score, "reasons": reasons or ["background_context"]}


def _edge_evidence_refs(edges: list[dict[str, object]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for edge in edges:
        for ref in cast(list[dict[str, object]], edge["evidence_refs"]):
            if ref.get("type") == "source_span":
                refs.append(ref)
    return refs


def _ranked_edge_entries(
    edges: list[dict[str, object]],
    scope: dict[str, Any],
) -> list[dict[str, object]]:
    ranked: list[dict[str, object]] = []
    for edge in edges:
        entry = dict(edge)
        entry["relevance"] = _edge_relevance(entry, scope)
        ranked.append(entry)
    ranked.sort(
        key=lambda entry: (
            -_entry_relevance_score(entry),
            str(entry["edge_id"]),
        )
    )
    return ranked


def _edge_relevance(edge: dict[str, object], scope: dict[str, Any]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    span_ids = [
        str(ref.get("id"))
        for ref in cast(list[dict[str, object]], edge.get("evidence_refs", []))
        if ref.get("type") == "source_span" and ref.get("id") is not None
    ]
    if _span_ids_have_scene(span_ids, scope):
        score += 70
        reasons.append("current_scene_evidence")
    if _span_ids_have_source(span_ids, scope):
        score += 10
        reasons.append("current_source_evidence")
    if _span_ids_have_version(span_ids, scope):
        score += 15
        reasons.append("current_version_evidence")
    active_characters = cast(list[dict[str, object]], scope["active_characters"])
    subject_ref = cast(dict[str, object], edge["subject_ref"])
    target_ref = cast(dict[str, object], edge["target_ref"])
    if any(
        _same_ref(subject_ref, active) or _same_ref(target_ref, active)
        for active in active_characters
    ):
        score += 40
        reasons.append("active_character")
    current_pov_character_id = cast(str | None, scope.get("current_pov_character_id"))
    if current_pov_character_id and (
        _ref_matches_id(subject_ref, current_pov_character_id)
        or _ref_matches_id(target_ref, current_pov_character_id)
    ):
        score += 20
        reasons.append("pov_character")
    query_overlap = _payload_query_overlap(edge, scope)
    if query_overlap:
        score += min(45, query_overlap * 15)
        reasons.append("intent_match")
    return {"score": score, "reasons": reasons or ["background_context"]}


def _style_evidence_refs(style_memory: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"type": "source_span", "id": str(sample["source_span_id"])}
        for sample in cast(list[dict[str, object]], style_memory["samples"])
    ]


def _fact_entry_evidence_refs(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for entry in entries:
        for span_id in cast(list[str], entry.get("evidence_span_ids", [])):
            refs.append({"type": "source_span", "id": str(span_id)})
    return refs


def _review_entry_evidence_refs(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = [
        {"type": "review_item", "id": str(entry["review_item_id"])} for entry in entries
    ]
    for entry in entries:
        for span_id in cast(list[str], entry.get("evidence_span_ids", [])):
            refs.append({"type": "source_span", "id": str(span_id)})
    return refs


def _context_pack_evidence_refs(
    *,
    canonical_fact_entries: list[dict[str, object]],
    risk_fact_entries: list[dict[str, object]],
    forbidden_knowledge: list[dict[str, object]],
    recent_events: list[dict[str, object]],
    object_location_state: list[dict[str, object]],
    style_memory: dict[str, object],
    review_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    return _unique_refs(
        _fact_entry_evidence_refs(canonical_fact_entries)
        + _fact_entry_evidence_refs(risk_fact_entries)
        + _fact_entry_evidence_refs(forbidden_knowledge)
        + _review_entry_evidence_refs(review_entries)
        + _event_evidence_refs(recent_events)
        + _edge_evidence_refs(object_location_state)
        + _style_evidence_refs(style_memory)
    )


def _ranked_style_memory(
    style_memory: dict[str, object],
    scope: dict[str, Any],
) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    for sample in cast(list[dict[str, object]], style_memory["samples"]):
        entry = dict(sample)
        entry["relevance"] = _style_sample_relevance(entry, scope)
        samples.append(entry)
    samples.sort(
        key=lambda entry: (
            -_entry_relevance_score(entry),
            str(entry["source_span_id"]),
        )
    )
    ranked = dict(style_memory)
    ranked["samples"] = samples
    ranked["retrieval_policy"] = dict(CONTEXT_RETRIEVAL_POLICY)
    return ranked


def _context_retrieval_policy(
    budget_metadata: dict[str, object] | None,
    semantic_recall: dict[str, object] | None = None,
) -> dict[str, object]:
    policy = dict(CONTEXT_RETRIEVAL_POLICY)
    if semantic_recall is not None and (
        semantic_recall.get("ref_keys")
        or semantic_recall.get("source_span_ids")
        or semantic_recall.get("style_sample_source_span_ids")
    ):
        sources = cast(set[str], semantic_recall["sources"])
        semantic_policy: dict[str, object] = {
            "sources": [
                source
                for source in ("alias_records", "memory_pages", "semantic_embedding_index")
                if source in sources
            ],
            "mode": "read_only_vocabulary_expansion",
        }
        embedding = semantic_recall.get("embedding")
        if isinstance(embedding, dict) and "semantic_embedding_index" in sources:
            semantic_policy["mode"] = (
                "rrf_keyword_embedding_hybrid"
                if {"alias_records", "memory_pages"}.intersection(sources)
                else "embedding_index_recall"
            )
            semantic_policy["embedding"] = embedding
        policy["semantic_recall"] = semantic_policy
    if budget_metadata is not None:
        policy["budget"] = budget_metadata
    return policy


def _apply_context_budget(
    *,
    input_data: BuildWritingContextPackInput,
    canonical_fact_entries: list[dict[str, object]],
    risk_fact_entries: list[dict[str, object]],
    forbidden_knowledge: list[dict[str, object]],
    recent_events: list[dict[str, object]],
    object_location_state: list[dict[str, object]],
    style_memory: dict[str, object],
    review_entries: list[dict[str, object]],
    open_threads: list[dict[str, object]],
) -> dict[str, object] | None:
    max_estimated_tokens = _context_budget_max_tokens(input_data)
    if max_estimated_tokens is None:
        return None

    style_samples = cast(list[dict[str, object]], style_memory["samples"])
    sections: dict[str, list[dict[str, object]]] = {
        "canonical_fact_entries": canonical_fact_entries,
        "risk_fact_entries": risk_fact_entries,
        "forbidden_knowledge": forbidden_knowledge,
        "recent_events": recent_events,
        "object_location_state": object_location_state,
        "style_samples": style_samples,
        "review_entries": review_entries,
        "open_threads": open_threads,
    }
    selected: dict[str, set[int]] = {name: set() for name in sections}
    estimated_tokens = 0
    total_estimated_tokens = sum(
        _estimated_context_tokens(item) for entries in sections.values() for item in entries
    )

    for section_name in ("risk_fact_entries", "review_entries"):
        if sections[section_name]:
            cost = _estimated_context_tokens(sections[section_name][0])
            if estimated_tokens + cost <= max_estimated_tokens:
                selected[section_name].add(0)
                estimated_tokens += cost

    candidates: list[tuple[int, str, str, int, int]] = []
    for section_name, entries in sections.items():
        for index, item in enumerate(entries):
            if index in selected[section_name]:
                continue
            score = _entry_relevance_score(item) + _budget_section_priority(section_name)
            candidates.append(
                (
                    score,
                    _budget_item_identity(item),
                    section_name,
                    index,
                    _estimated_context_tokens(item),
                )
            )
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))

    for _score, _identity, section_name, index, cost in candidates:
        if estimated_tokens + cost > max_estimated_tokens:
            continue
        selected[section_name].add(index)
        estimated_tokens += cost

    for section_name, entries in sections.items():
        kept = [item for index, item in enumerate(entries) if index in selected[section_name]]
        entries[:] = kept

    return {
        "max_estimated_tokens": max_estimated_tokens,
        "estimated_tokens": estimated_tokens,
        "truncated": total_estimated_tokens > estimated_tokens,
    }


def _context_budget_max_tokens(input_data: BuildWritingContextPackInput) -> int | None:
    constraints = input_data.constraints or {}
    budget = constraints.get("context_budget")
    if not isinstance(budget, dict):
        return None
    budget_map = cast(dict[str, object], budget)
    value = budget_map.get("max_estimated_tokens")
    if value is None:
        value = budget_map.get("max_tokens")
    if isinstance(value, int) and value > 0:
        return value
    return None


def _estimated_context_tokens(item: dict[str, object]) -> int:
    rendered = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return max(1, (len(rendered) + 3) // 4)


def _budget_section_priority(section_name: str) -> int:
    return {
        "review_entries": 60,
        "risk_fact_entries": 50,
        "forbidden_knowledge": 45,
        "canonical_fact_entries": 20,
        "recent_events": 15,
        "object_location_state": 15,
        "open_threads": 10,
        "style_samples": 0,
    }.get(section_name, 0)


def _budget_item_identity(item: dict[str, object]) -> str:
    for key in (
        "fact_id",
        "review_item_id",
        "event_id",
        "edge_id",
        "source_span_id",
        "id",
    ):
        value = item.get(key)
        if value is not None:
            return str(value)
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def _style_sample_relevance(sample: dict[str, object], scope: dict[str, Any]) -> dict[str, object]:
    score = 0
    reasons: list[str] = []
    span_id = str(sample["source_span_id"])
    if _span_ids_have_scene([span_id], scope):
        score += 70
        reasons.append("current_scene_evidence")
    if _span_ids_have_source([span_id], scope):
        score += 10
        reasons.append("current_source_evidence")
    if _span_ids_have_version([span_id], scope):
        score += 15
        reasons.append("current_version_evidence")
    query_overlap = _payload_query_overlap(sample, scope)
    if query_overlap:
        score += min(45, query_overlap * 15)
        reasons.append("intent_match")
    if _span_matches_semantic_recall(span_id, scope, include_style_samples=True):
        score += _semantic_span_relevance_points(
            span_id,
            scope,
            include_style_samples=True,
        )
        reasons.append("semantic_recall")
    return {"score": score, "reasons": reasons or ["recent_style_sample"]}


def _recent_event_entries(session: Session, project_id: UUID) -> list[dict[str, object]]:
    events = (
        session.query(StoryCanonicalEvent)
        .filter_by(project_id=project_id)
        .filter(StoryCanonicalEvent.event_status.in_(("canon", "external_canon", "author_note")))
        .order_by(StoryCanonicalEvent.created_at.desc(), StoryCanonicalEvent.id.desc())
        .limit(10)
        .all()
    )
    entries: list[dict[str, object]] = []
    for event in events:
        evidence_span_ids = _valid_source_span_id_strings(
            session,
            project_id,
            event.evidence_span_ids,
        )
        if not evidence_span_ids:
            continue
        entries.append(
            {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "title": event.title,
                "event_status": event.event_status,
                "story_time": event.story_time,
                "summary": event.summary,
                "consequence_summary": event.consequence_summary,
                "participants": event.participants,
                "objects": event.objects,
                "evidence_span_ids": evidence_span_ids,
            }
        )
    return entries


def _object_location_state(session: Session, project_id: UUID) -> list[dict[str, object]]:
    edges = (
        session.query(GraphProjectionEdge)
        .filter_by(project_id=project_id)
        .filter(GraphProjectionEdge.relation.in_(("owns", "located_in", "involves_object")))
        .filter(GraphProjectionEdge.edge_status.in_(("canon", "inferred", "proposed")))
        .order_by(GraphProjectionEdge.created_at.desc(), GraphProjectionEdge.id.desc())
        .limit(20)
        .all()
    )
    edge_entries: list[dict[str, object]] = []
    for edge in edges:
        evidence_refs = _valid_source_span_refs(
            session,
            project_id,
            edge.evidence_refs,
        )
        if not evidence_refs:
            continue
        edge_entries.append(
            {
                "edge_id": str(edge.id),
                "relation": edge.relation,
                "subject_ref": edge.subject_ref,
                "target_ref": edge.target_ref,
                "edge_status": edge.edge_status,
                "evidence_refs": evidence_refs,
            }
        )
    return edge_entries + _memory_page_state_entries(
        session,
        project_id=project_id,
        existing_entries=edge_entries,
    )


def _memory_page_state_entries(
    session: Session,
    *,
    project_id: UUID,
    existing_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    seen = {_object_location_state_key(entry) for entry in existing_entries}
    entries: list[dict[str, object]] = []
    pages = (
        session.query(MemoryPage)
        .filter_by(project_id=project_id)
        .filter(MemoryPage.canon_status.in_(("current", "rebuilt")))
        .order_by(MemoryPage.updated_at.desc(), MemoryPage.id.desc())
        .limit(20)
        .all()
    )
    for page in pages:
        current_canon = page.current_canon
        state_facts = current_canon.get("state_facts") if isinstance(current_canon, dict) else None
        if not isinstance(state_facts, list):
            continue
        for state_fact in state_facts:
            if not isinstance(state_fact, dict):
                continue
            entry = _memory_page_state_entry(
                session,
                project_id,
                page,
                cast(dict[str, object], state_fact),
            )
            if entry is None:
                continue
            key = _object_location_state_key(entry)
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    return entries


def _memory_page_state_entry(
    session: Session,
    project_id: UUID,
    page: MemoryPage,
    state_fact: dict[str, object],
) -> dict[str, object] | None:
    predicate = state_fact.get("predicate")
    state_type = state_fact.get("state_type")
    fact_id = state_fact.get("fact_id")
    subject_ref = state_fact.get("subject_ref")
    object_ref = state_fact.get("object_ref")
    evidence_span_ids = state_fact.get("evidence_span_ids")
    if (
        not isinstance(predicate, str)
        or predicate not in {"owns", "located_in", "involves_object"}
        or not isinstance(state_type, str)
        or not isinstance(fact_id, str)
        or not isinstance(subject_ref, dict)
        or not isinstance(object_ref, dict)
        or not isinstance(evidence_span_ids, list)
        or not evidence_span_ids
    ):
        return None
    span_ids = _valid_source_span_id_strings(session, project_id, evidence_span_ids)
    if not span_ids:
        return None
    return {
        "edge_id": f"memory_page_state:{page.id}:{fact_id}:{state_type}",
        "source": "memory_page_state",
        "memory_page_id": str(page.id),
        "fact_id": fact_id,
        "state_type": state_type,
        "relation": predicate,
        "subject_ref": cast(dict[str, object], subject_ref),
        "target_ref": cast(dict[str, object], object_ref),
        "edge_status": "canon",
        "evidence_refs": [{"type": "source_span", "id": span_id} for span_id in span_ids],
    }


def _valid_source_span_refs(
    session: Session,
    project_id: UUID,
    evidence_refs: object,
) -> list[dict[str, object]]:
    if not isinstance(evidence_refs, list):
        return []
    span_ref_ids: list[object] = []
    for ref in evidence_refs:
        if not isinstance(ref, Mapping):
            continue
        ref_map = cast(Mapping[str, object], ref)
        if ref_map.get("type") == "source_span":
            span_ref_ids.append(ref_map.get("id"))
    span_ids = _valid_source_span_id_strings(
        session,
        project_id,
        span_ref_ids,
    )
    return [{"type": "source_span", "id": span_id} for span_id in span_ids]


def _sanitized_agent_memory_refs(
    session: Session,
    project_id: UUID,
    memory_refs: object,
) -> list[dict[str, object]]:
    sanitized = _sanitized_agent_ref_payload(session, project_id, memory_refs)
    if not isinstance(sanitized, list):
        return []
    refs: list[dict[str, object]] = []
    for ref in sanitized:
        if isinstance(ref, dict):
            refs.append(cast(dict[str, object], ref))
    return refs


def _sanitized_agent_ref_payload(
    session: Session,
    project_id: UUID,
    payload: object,
) -> object | None:
    if isinstance(payload, Mapping):
        payload_map = cast(Mapping[str, object], payload)
        if isinstance(payload_map.get("type"), str):
            return _sanitized_typed_agent_ref(session, project_id, payload_map)
        result: dict[str, object] = {}
        for raw_key, raw_value in payload_map.items():
            key = str(raw_key)
            if key == "source_span_id":
                span_ids = _valid_source_span_id_strings(session, project_id, [raw_value])
                if span_ids:
                    result[key] = span_ids[0]
                continue
            if key in {"source_span_ids", "evidence_span_ids"}:
                span_values = raw_value if isinstance(raw_value, list) else []
                span_ids = _valid_source_span_id_strings(session, project_id, span_values)
                if span_ids:
                    result[key] = span_ids
                continue
            if key.endswith("_refs") and isinstance(raw_value, list):
                refs = _sanitized_agent_memory_refs(session, project_id, raw_value)
                if refs:
                    result[key] = refs
                continue
            sanitized_value = _sanitized_agent_ref_payload(session, project_id, raw_value)
            if sanitized_value is not None:
                result[key] = sanitized_value
        return result

    if isinstance(payload, list):
        if any(
            isinstance(item, Mapping)
            and isinstance(cast(Mapping[str, object], item).get("type"), str)
            for item in payload
        ):
            refs: list[dict[str, object]] = []
            for item in payload:
                if not isinstance(item, Mapping):
                    continue
                ref = _sanitized_typed_agent_ref(
                    session,
                    project_id,
                    cast(Mapping[str, object], item),
                )
                if ref is not None:
                    refs.append(ref)
            return refs
        values: list[object] = []
        for item in payload:
            sanitized_item = _sanitized_agent_ref_payload(session, project_id, item)
            if sanitized_item is not None:
                values.append(sanitized_item)
        return values

    return payload


def _sanitized_typed_agent_ref(
    session: Session,
    project_id: UUID,
    ref: Mapping[str, object],
) -> dict[str, object] | None:
    ref_type = ref.get("type")
    if not isinstance(ref_type, str):
        return None
    ref_id = _valid_agent_ref_id(session, project_id, ref_type, ref.get("id"))
    if ref_id is None:
        return None

    result: dict[str, object] = {"type": ref_type, "id": str(ref_id)}
    for raw_key, raw_value in ref.items():
        key = str(raw_key)
        if key in {"type", "id"}:
            continue
        sanitized_value = _sanitized_agent_ref_payload(session, project_id, raw_value)
        if sanitized_value is not None:
            result[key] = sanitized_value
    return result


def _valid_agent_ref_id(
    session: Session,
    project_id: UUID,
    ref_type: str,
    raw_ref_id: object,
) -> UUID | None:
    ref_id = _uuid_or_none(raw_ref_id)
    if ref_id is None:
        return None

    if ref_type == "source_span":
        span = session.get(SourceSpan, ref_id)
        if span is not None and _source_span_belongs_to_project(session, span, project_id):
            return span.id
        return None

    if ref_type == "memory_page":
        page = session.get(MemoryPage, ref_id)
        if page is None or page.project_id != project_id:
            return None
        span_ids = _valid_source_span_id_strings(
            session, project_id, _memory_page_context_source_span_ids(session, page)
        )
        return page.id if span_ids else None

    if ref_type == "fact_assertion":
        fact = session.get(FactAssertionRecord, ref_id)
        if fact is None or fact.project_id != project_id:
            return None
        span_ids = _valid_source_span_id_strings(session, project_id, fact.evidence_span_ids)
        return fact.id if span_ids else None

    if ref_type in {"canonical_event", "story_canonical_event"}:
        event = session.get(StoryCanonicalEvent, ref_id)
        if event is None or event.project_id != project_id:
            return None
        span_ids = _valid_source_span_id_strings(session, project_id, event.evidence_span_ids)
        return event.id if span_ids else None

    if ref_type in {"graph_projection_edge", "graph_edge"}:
        edge = session.get(GraphProjectionEdge, ref_id)
        if edge is None or edge.project_id != project_id:
            return None
        span_ids = _valid_source_span_id_strings(
            session, project_id, _graph_edge_source_span_ids(session, edge)
        )
        return edge.id if span_ids else None

    if ref_type == "review_item":
        review = session.get(ReviewItemRecord, ref_id)
        if review is None or review.project_id != project_id:
            return None
        return review.id if _review_context_source_span_ids(session, review) else None

    if ref_type == "source_delta":
        delta = session.get(SourceDeltaRecord, ref_id)
        if delta is None or delta.project_id != project_id:
            return None
        span_ids = _source_span_ids_for_delta(
            session, project_id=project_id, source_delta_id=delta.id
        )
        return delta.id if span_ids else None

    return None


def _object_location_state_key(entry: dict[str, object]) -> tuple[str, str, str]:
    return (
        str(entry.get("relation") or ""),
        _ref_key(cast(dict[str, object], entry.get("subject_ref") or {})),
        _ref_key(cast(dict[str, object], entry.get("target_ref") or {})),
    )


def _ref_key(ref: dict[str, object]) -> str:
    return f"{ref.get('type')}:{ref.get('id') or ref.get('value') or ref.get('label') or ''}"


def _style_memory(session: Session, input_data: BuildWritingContextPackInput) -> dict[str, object]:
    source_ids = [
        source_id
        for (source_id,) in session.query(RawSource.id)
        .filter_by(project_id=input_data.project_id)
        .all()
    ]
    if not source_ids:
        return {"samples": []}
    query = session.query(SourceSpan).filter(SourceSpan.source_id.in_(source_ids))
    if input_data.current_version_id is not None:
        query = query.filter_by(version_id=input_data.current_version_id)
    elif input_data.current_source_id is not None:
        query = query.filter_by(source_id=input_data.current_source_id)
    spans = query.order_by(SourceSpan.start_offset, SourceSpan.id).all()
    spans = _style_memory_sliding_window(session, input_data, spans)
    return {
        "samples": [
            {
                "source_span_id": str(span.id),
                "text_preview": span.text_preview,
                "narration_layer": span.narration_layer,
            }
            for span in spans[:STYLE_MEMORY_WINDOW_SIZE]
        ]
    }


def _style_memory_sliding_window(
    session: Session,
    input_data: BuildWritingContextPackInput,
    spans: list[SourceSpan],
) -> list[SourceSpan]:
    if not spans:
        return []
    if input_data.current_scene_id is not None:
        scene_indices = [
            index
            for index, span in enumerate(spans)
            if span.scene_id == input_data.current_scene_id
        ]
        if scene_indices:
            return _windowed_spans(
                spans,
                scene_indices,
                query_tokens=_context_query_tokens(input_data),
            )
    anchor_index = _style_memory_query_anchor_index(spans, _context_query_tokens(input_data))
    if anchor_index is not None:
        return _windowed_spans(
            spans,
            [anchor_index],
            query_tokens=_context_query_tokens(input_data),
        )
    return list(reversed(spans[-STYLE_MEMORY_WINDOW_SIZE:]))


def _style_memory_query_anchor_index(
    spans: list[SourceSpan],
    query_tokens: set[str],
) -> int | None:
    if not query_tokens:
        return None
    best_index: int | None = None
    best_overlap = 0
    for index, span in enumerate(spans):
        overlap = len(query_tokens & _search_tokens(span.text_preview))
        if overlap > best_overlap:
            best_index = index
            best_overlap = overlap
    return best_index


def _windowed_spans(
    spans: list[SourceSpan],
    anchor_indices: list[int],
    *,
    query_tokens: set[str],
) -> list[SourceSpan]:
    ordered: list[SourceSpan] = []
    seen: set[UUID] = set()

    anchor_entries = [spans[index] for index in anchor_indices if 0 <= index < len(spans)]
    anchor_entries.sort(
        key=lambda span: (
            -len(query_tokens & _search_tokens(span.text_preview)),
            span.start_offset,
            str(span.id),
        )
    )
    for span in anchor_entries:
        if span.id not in seen:
            ordered.append(span)
            seen.add(span.id)
            if len(ordered) >= STYLE_MEMORY_WINDOW_SIZE:
                return ordered

    left = min(anchor_indices) - 1
    right = max(anchor_indices) + 1
    while len(ordered) < STYLE_MEMORY_WINDOW_SIZE and (left >= 0 or right < len(spans)):
        if left >= 0:
            span = spans[left]
            if span.id not in seen:
                ordered.append(span)
                seen.add(span.id)
                if len(ordered) >= STYLE_MEMORY_WINDOW_SIZE:
                    break
            left -= 1
        if right < len(spans):
            span = spans[right]
            if span.id not in seen:
                ordered.append(span)
                seen.add(span.id)
            right += 1
    return ordered


def _source_spans_by_id(
    session: Session,
    project_id: UUID,
    span_ids: list[str],
) -> dict[str, SourceSpan]:
    uuid_span_ids: list[UUID] = []
    for span_id in dict.fromkeys(span_ids):
        try:
            uuid_span_ids.append(UUID(str(span_id)))
        except ValueError:
            continue
    if not uuid_span_ids:
        return {}
    source_ids = [
        source_id
        for (source_id,) in session.query(RawSource.id).filter_by(project_id=project_id).all()
    ]
    if not source_ids:
        return {}
    spans = (
        session.query(SourceSpan)
        .filter(SourceSpan.id.in_(uuid_span_ids))
        .filter(SourceSpan.source_id.in_(source_ids))
        .all()
    )
    return {str(span.id): span for span in spans}


def _context_relevance_scope(
    *,
    input_data: BuildWritingContextPackInput,
    current_pov_character_id: UUID | None,
    active_characters: list[dict[str, object]],
    source_spans_by_id: dict[str, SourceSpan],
    semantic_recall: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "current_scene_id": str(input_data.current_scene_id)
        if input_data.current_scene_id
        else None,
        "current_source_id": str(input_data.current_source_id)
        if input_data.current_source_id
        else None,
        "current_version_id": str(input_data.current_version_id)
        if input_data.current_version_id
        else None,
        "current_pov_character_id": str(current_pov_character_id)
        if current_pov_character_id
        else None,
        "active_characters": active_characters,
        "query_tokens": _context_query_tokens(input_data),
        "source_spans_by_id": source_spans_by_id,
        "semantic_recall": semantic_recall
        or {
            "ref_keys": set(),
            "source_span_ids": set(),
            "style_sample_source_span_ids": set(),
            "sources": set(),
        },
    }


def _semantic_recall_context(
    session: Session,
    *,
    project_id: UUID,
    input_data: BuildWritingContextPackInput,
    memory_pages: list[MemoryPage],
    embedding_client: EmbeddingClient | None = None,
) -> dict[str, object]:
    query_tokens = _context_query_tokens(input_data)
    query_text = f"{input_data.mode} {input_data.current_text_window}"
    if not query_tokens and not query_text.strip():
        return {"ref_keys": set(), "sources": set()}

    ref_keys: set[str] = set()
    sources: set[str] = set()
    alias_rankings: list[str] = []
    memory_page_rankings: list[str] = []

    aliases = session.query(StoryAliasRecord).filter_by(project_id=project_id).all()
    alias_matches: list[tuple[int, float, str]] = []
    for alias in aliases:
        if alias.entity_id is None:
            continue
        overlap = len(query_tokens & _search_tokens(alias.alias_text))
        if overlap:
            ref_key = str(alias.entity_id).casefold()
            ref_keys.add(ref_key)
            sources.add("alias_records")
            alias_matches.append((overlap, alias.confidence, ref_key))
    alias_matches.sort(key=lambda item: (-item[0], -item[1], item[2]))
    alias_rankings = [ref_key for _overlap, _confidence, ref_key in alias_matches]

    memory_page_matches: list[tuple[int, str]] = []
    for page in memory_pages:
        page_payload = {
            "title": page.title,
            "target_ref": page.target_ref,
            "open_threads": page.open_threads,
            "current_canon": page.current_canon,
            "relationships": page.relationships,
            "contradictions": page.contradictions,
        }
        overlap = len(query_tokens & _search_tokens(page_payload))
        page_ref_keys = sorted(_ref_semantic_keys(page.target_ref))
        if overlap and page_ref_keys:
            ref_keys.update(page_ref_keys)
            sources.add("memory_pages")
            for ref_key in page_ref_keys:
                memory_page_matches.append((overlap, ref_key))
    memory_page_matches.sort(key=lambda item: (-item[0], item[1]))
    memory_page_rankings = [ref_key for _overlap, ref_key in memory_page_matches]

    embedding: dict[str, object] | None = None
    source_span_ids: set[str] = set()
    style_sample_source_span_ids: set[str] = set()
    embedding_ref_rankings: list[str] = []
    embedding_source_span_rankings: list[str] = []
    embedding_style_sample_rankings: list[str] = []
    if embedding_client is not None and query_text.strip():
        semantic_matches = semantic_ref_keys_for_text(
            session,
            project_id=project_id,
            text=query_text,
            embedding_client=embedding_client,
        )
        if semantic_matches.ref_keys:
            ref_keys.update(semantic_matches.ref_keys)
            sources.add("semantic_embedding_index")
        for match in semantic_matches.matches:
            match_ref_keys = match.get("ref_keys")
            if isinstance(match_ref_keys, list):
                embedding_ref_rankings.extend(
                    str(ref_key).casefold() for ref_key in match_ref_keys if str(ref_key).strip()
                )
            target_type = match.get("target_type")
            target_id = match.get("target_id")
            if target_type == "source_span" and target_id is not None:
                embedding_source_span_rankings.append(str(target_id))
            if target_type == "style_sample" and target_id is not None:
                embedding_style_sample_rankings.append(str(target_id))
        source_span_ids = semantic_matches.source_span_ids
        style_sample_source_span_ids = semantic_matches.style_sample_source_span_ids
        if source_span_ids or style_sample_source_span_ids:
            sources.add("semantic_embedding_index")
        if semantic_matches.matches:
            embedding = {
                "provider": embedding_client.provider_name,
                "model": embedding_client.model_name,
                "matches": len(semantic_matches.matches),
            }

    context: dict[str, object] = {"ref_keys": ref_keys, "sources": sources}
    if alias_rankings or memory_page_rankings or embedding_ref_rankings:
        context["ref_key_scores"] = reciprocal_rank_fusion(
            [
                ranking
                for ranking in (
                    alias_rankings,
                    memory_page_rankings,
                    embedding_ref_rankings,
                )
                if ranking
            ]
        )
    if embedding_source_span_rankings:
        context["source_span_scores"] = reciprocal_rank_fusion([embedding_source_span_rankings])
    if embedding_style_sample_rankings:
        context["style_sample_source_span_scores"] = reciprocal_rank_fusion(
            [embedding_style_sample_rankings]
        )
    if embedding is not None:
        context["embedding"] = embedding
        context["source_span_ids"] = source_span_ids
        context["style_sample_source_span_ids"] = style_sample_source_span_ids
    return context


def _context_query_tokens(input_data: BuildWritingContextPackInput) -> set[str]:
    payload = f"{input_data.mode} {input_data.current_text_window}"
    return _search_tokens(payload)


def _memory_answer_open_thread_entries(
    session: Session,
    input_data: MemoryAnswerInput,
    *,
    embedding_client: EmbeddingClient | None = None,
) -> list[tuple[MemoryPage, list[dict[str, object]], list[str]]] | None:
    if not _memory_answer_is_open_thread_query(input_data.question):
        return None

    semantic_recall = _memory_answer_semantic_recall_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        embedding_client=embedding_client,
    )
    pages = (
        session.query(MemoryPage)
        .filter_by(project_id=input_data.project_id, canon_status="current")
        .order_by(MemoryPage.title.asc(), MemoryPage.id.asc())
        .all()
    )
    focus_tokens = _memory_answer_open_thread_focus_tokens(input_data.question)
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]] = []
    for page in pages:
        ranking_focus_tokens = focus_tokens
        threads = [
            dict(thread)
            for thread in page.open_threads
            if isinstance(thread, dict)
            and _open_thread_is_active(thread)
            and _open_thread_text(thread)
        ]
        if not threads:
            continue

        if focus_tokens:
            target_payload = {"title": page.title, "target_ref": page.target_ref}
            semantic_page_match = _memory_answer_page_matches_semantic_recall(
                page,
                semantic_recall,
            )
            semantic_thread_matches = _open_threads_matching_semantic_recall(
                session,
                project_id=input_data.project_id,
                page=page,
                threads=threads,
                semantic_recall=semantic_recall,
            )
            target_matches = (
                _text_matches_query(target_payload, focus_tokens, input_data.question)
                or semantic_page_match
            )
            thread_focus_tokens = focus_tokens - _meaningful_search_tokens(target_payload)
            if thread_focus_tokens:
                ranking_focus_tokens = thread_focus_tokens
                matching_threads = [
                    thread
                    for thread in threads
                    if _text_matches_query(thread, thread_focus_tokens, input_data.question)
                ]
                if matching_threads:
                    threads = matching_threads
                elif semantic_thread_matches:
                    threads = semantic_thread_matches
                    ranking_focus_tokens = set()
                elif semantic_page_match:
                    ranking_focus_tokens = set()
                else:
                    continue
            elif not target_matches:
                matching_threads = [
                    thread
                    for thread in threads
                    if _text_matches_query(thread, focus_tokens, input_data.question)
                ]
                if matching_threads:
                    threads = matching_threads
                elif semantic_thread_matches:
                    threads = semantic_thread_matches
                    ranking_focus_tokens = set()
                else:
                    threads = []
            else:
                ranking_focus_tokens = set()
            if not target_matches and not threads:
                continue

        threads = _rank_open_threads(
            session,
            project_id=input_data.project_id,
            threads=threads,
            focus_tokens=ranking_focus_tokens,
        )
        threads = threads[:5]
        span_ids = _open_thread_entry_span_ids(
            session,
            project_id=input_data.project_id,
            page=page,
            threads=threads,
        )
        if not span_ids:
            continue
        entries.append((page, threads, span_ids))
    return entries[:5]


def _memory_answer_semantic_recall_for_question(
    session: Session,
    *,
    project_id: UUID,
    question: str,
    embedding_client: EmbeddingClient | None,
) -> SemanticRecallResult | None:
    if embedding_client is None or not question.strip():
        return None
    semantic_recall = semantic_ref_keys_for_text(
        session,
        project_id=project_id,
        text=question,
        embedding_client=embedding_client,
    )
    if not semantic_recall.ref_keys and not semantic_recall.source_span_ids:
        return None
    return semantic_recall


def _memory_answer_page_matches_semantic_recall(
    page: MemoryPage,
    semantic_recall: SemanticRecallResult | None,
) -> bool:
    if semantic_recall is None:
        return False
    return bool(semantic_recall.ref_keys.intersection(_ref_semantic_keys(page.target_ref)))


def _open_threads_matching_semantic_recall(
    session: Session,
    *,
    project_id: UUID,
    page: MemoryPage,
    threads: list[dict[str, object]],
    semantic_recall: SemanticRecallResult | None,
) -> list[dict[str, object]]:
    if semantic_recall is None or not semantic_recall.source_span_ids:
        return []

    semantic_source_span_ids = semantic_recall.source_span_ids
    page_span_ids = set(
        _valid_source_span_id_strings(
            session,
            project_id,
            _memory_page_source_span_ids(page),
        )
    )
    matching_threads: list[dict[str, object]] = []
    for thread in threads:
        raw_thread_span_ids = thread.get("source_span_ids")
        if isinstance(raw_thread_span_ids, list):
            thread_span_ids = set(
                _valid_source_span_id_strings(
                    session,
                    project_id,
                    raw_thread_span_ids,
                )
            )
            if thread_span_ids and semantic_source_span_ids.intersection(thread_span_ids):
                matching_threads.append(thread)
            continue
        if page_span_ids and semantic_source_span_ids.intersection(page_span_ids):
            matching_threads.append(thread)
    return matching_threads


def _rank_open_threads(
    session: Session,
    *,
    project_id: UUID,
    threads: list[dict[str, object]],
    focus_tokens: set[str],
) -> list[dict[str, object]]:
    review_cache: dict[UUID, ReviewItemRecord | None] = {}
    indexed_threads = list(enumerate(threads))
    indexed_threads.sort(
        key=lambda item: _open_thread_rank_key(
            session,
            project_id=project_id,
            thread=item[1],
            focus_tokens=focus_tokens,
            original_index=item[0],
            review_cache=review_cache,
        )
    )
    return [thread for _index, thread in indexed_threads]


def _open_thread_rank_key(
    session: Session,
    *,
    project_id: UUID,
    thread: dict[str, object],
    focus_tokens: set[str],
    original_index: int,
    review_cache: dict[UUID, ReviewItemRecord | None],
) -> tuple[int, int, int, int, int]:
    review = _open_thread_review_record(
        session,
        project_id=project_id,
        thread=thread,
        review_cache=review_cache,
    )
    severity = review.severity if review is not None else str(thread.get("severity", ""))
    return (
        -len(focus_tokens.intersection(_meaningful_search_tokens(thread))),
        0 if review is not None else 1,
        _continuity_severity_rank(severity),
        -_open_thread_source_span_count(session, project_id, thread),
        original_index,
    )


def _open_thread_review_record(
    session: Session,
    *,
    project_id: UUID,
    thread: dict[str, object],
    review_cache: dict[UUID, ReviewItemRecord | None],
) -> ReviewItemRecord | None:
    review_id = _uuid_or_none(thread.get("review_item_id"))
    if review_id is None:
        return None
    if review_id not in review_cache:
        review = session.get(ReviewItemRecord, review_id)
        if review is not None and review.project_id == project_id and review.status == "open":
            review_cache[review_id] = review
        else:
            review_cache[review_id] = None
    return review_cache[review_id]


def _open_thread_source_span_count(
    session: Session,
    project_id: UUID,
    thread: dict[str, object],
) -> int:
    span_ids = thread.get("source_span_ids")
    if isinstance(span_ids, list):
        return len(_valid_source_span_id_strings(session, project_id, span_ids))
    return 0


def _open_thread_entry_span_ids(
    session: Session,
    *,
    project_id: UUID,
    page: MemoryPage,
    threads: list[dict[str, object]],
) -> list[str]:
    thread_span_ids: list[str] = []
    for thread in threads:
        span_ids = thread.get("source_span_ids")
        if not isinstance(span_ids, list):
            return _valid_source_span_id_strings(
                session,
                project_id,
                _memory_page_source_span_ids(page),
            )
        valid_span_ids = _valid_source_span_id_strings(session, project_id, span_ids)
        if not valid_span_ids:
            return _valid_source_span_id_strings(
                session,
                project_id,
                _memory_page_source_span_ids(page),
            )
        thread_span_ids.extend(valid_span_ids)
    return _unique_str_sequence(thread_span_ids)


def _valid_source_span_id_strings(
    session: Session,
    project_id: UUID,
    span_ids: Iterable[object],
) -> list[str]:
    result: list[str] = []
    seen: set[UUID] = set()
    for raw_span_id in span_ids:
        span_id = _uuid_or_none(raw_span_id)
        if span_id is None or span_id in seen:
            continue
        span = session.get(SourceSpan, span_id)
        if span is None or not _source_span_belongs_to_project(session, span, project_id):
            continue
        seen.add(span_id)
        result.append(str(span_id))
    return result


def _memory_answer_is_open_thread_query(question: str) -> bool:
    tokens = _search_tokens(question)
    if tokens.intersection(MEMORY_ANSWER_OPEN_THREAD_QUERY_TERMS):
        return True
    lowered = question.casefold()
    return any(
        term in lowered for term in ("伏笔", "悬念", "线索", "未解", "未解决", "open thread")
    )


def _memory_answer_open_thread_focus_tokens(question: str) -> set[str]:
    focus_tokens = _meaningful_search_tokens(question)
    focus_tokens -= MEMORY_ANSWER_OPEN_THREAD_FOCUS_STOPWORDS
    return focus_tokens


def _open_thread_answer_span_ids(
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for _page, _threads, span_ids in entries:
        for span_id in span_ids:
            if span_id not in seen:
                seen.add(span_id)
                result.append(span_id)
    return result


def _open_thread_entry_review_ids(
    session: Session,
    project_id: UUID,
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]],
) -> list[UUID]:
    review_ids: list[UUID] = []
    for _page, threads, _span_ids in entries:
        for thread in threads:
            review_id = _uuid_or_none(thread.get("review_item_id"))
            if review_id is None:
                continue
            review = session.get(ReviewItemRecord, review_id)
            if review is not None and review.project_id == project_id and review.status == "open":
                review_ids.append(review.id)
    return _unique_uuid_sequence(review_ids)


def _unique_uuid_sequence(values: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    result: list[UUID] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _open_thread_answer_affected_entities(
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]],
) -> list[dict[str, object]]:
    return _unique_refs([dict(page.target_ref) for page, _threads, _span_ids in entries])


def _open_thread_answer_caveats(*, has_open_review_items: bool) -> list[str]:
    caveats = ["memory_page_open_thread"]
    if has_open_review_items:
        caveats.append("open_review_item")
    return caveats


def _open_thread_answer_confidence(
    session: Session,
    project_id: UUID,
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]],
    *,
    related_review_items: list[UUID],
) -> float:
    if not entries:
        return 0.0
    if not related_review_items:
        return 0.8

    severities = _open_review_item_severities(session, project_id, related_review_items)
    if "high" in severities:
        return 0.5
    if "medium" in severities:
        return 0.6
    if "low" in severities:
        return 0.7
    return 0.6


def _open_review_item_severities(
    session: Session,
    project_id: UUID,
    review_ids: list[UUID],
) -> set[str]:
    severities: set[str] = set()
    for review_id in review_ids:
        review = session.get(ReviewItemRecord, review_id)
        if review is not None and review.project_id == project_id and review.status == "open":
            severities.add(review.severity)
    return severities


def _format_open_thread_answer(
    entries: list[tuple[MemoryPage, list[dict[str, object]], list[str]]],
) -> str:
    page_segments: list[str] = []
    for page, threads, _span_ids in entries:
        thread_texts = [_open_thread_text(thread) for thread in threads]
        page_segments.append(f"{_ref_label(page.target_ref)}: {'; '.join(thread_texts)}")
    return "Open threads: " + " | ".join(page_segments)


def _open_thread_text(thread: dict[str, object]) -> str:
    for key in ("summary", "thread", "question", "description", "title"):
        value = thread.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(thread, ensure_ascii=False, sort_keys=True)


def _open_thread_is_active(thread: dict[str, object]) -> bool:
    for key in ("status", "thread_status", "state"):
        value = thread.get(key)
        if value is not None:
            return str(value).casefold() not in {
                "closed",
                "done",
                "dismissed",
                "obsolete",
                "resolved",
                "superseded",
            }
    return True


def _memory_answer_continuity_reviews(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[ReviewItemRecord] | None:
    if not _memory_answer_is_continuity_query(input_data.question):
        return None

    reviews = (
        session.query(ReviewItemRecord)
        .filter_by(project_id=input_data.project_id, status="open")
        .filter(ReviewItemRecord.review_type.in_(MEMORY_ANSWER_CONTINUITY_REVIEW_TYPES))
        .order_by(ReviewItemRecord.created_at.desc(), ReviewItemRecord.id.desc())
        .all()
    )
    focus_tokens = _meaningful_search_tokens(input_data.question)
    focus_tokens -= MEMORY_ANSWER_CONTINUITY_FOCUS_STOPWORDS
    if focus_tokens:
        focused = [
            review
            for review in reviews
            if _text_matches_query(
                _continuity_review_search_payload(review), focus_tokens, input_data.question
            )
        ]
        if focused:
            reviews = focused
    reviews.sort(
        key=lambda review: (
            _continuity_severity_rank(review.severity),
            str(review.id),
        )
    )
    return reviews[:5]


def _memory_answer_is_continuity_query(question: str) -> bool:
    tokens = _search_tokens(question)
    return bool(tokens.intersection(MEMORY_ANSWER_CONTINUITY_QUERY_TERMS))


def _continuity_review_search_payload(review: ReviewItemRecord) -> dict[str, object]:
    return {
        "review_type": review.review_type,
        "severity": review.severity,
        "summary": review.summary,
        "affected_refs": review.affected_refs,
        "new_evidence": review.new_evidence,
        "existing_evidence": review.existing_evidence,
    }


def _continuity_review_span_ids(reviews: list[ReviewItemRecord]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for review in reviews:
        for evidence in (review.new_evidence, review.existing_evidence):
            for span_id in evidence.get("source_span_ids", []):
                span_id = str(span_id)
                if span_id not in seen:
                    seen.add(span_id)
                    result.append(span_id)
    return result


def _continuity_review_affected_entities(
    reviews: list[ReviewItemRecord],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for review in reviews:
        refs = review.affected_refs.get("refs")
        if isinstance(refs, list):
            for ref in refs:
                if isinstance(ref, dict):
                    _append_unique_payload(result, seen, ref)
        if review.affected_refs.get("type") is not None:
            _append_unique_payload(result, seen, review.affected_refs)
        for key, value in review.affected_refs.items():
            if key == "refs" or isinstance(value, dict):
                continue
            ref_type = key.removesuffix("_ids").removesuffix("_id")
            if isinstance(value, list):
                for item in value:
                    _append_unique_payload(result, seen, {"type": ref_type, "id": str(item)})
            elif value is not None:
                _append_unique_payload(result, seen, {"type": ref_type, "id": str(value)})
    return result


def _append_unique_payload(
    result: list[dict[str, object]],
    seen: set[str],
    payload: dict[str, object],
) -> None:
    copied = dict(payload)
    key = json.dumps(copied, sort_keys=True, default=str)
    if key in seen:
        return
    seen.add(key)
    result.append(copied)


def _continuity_review_caveats(reviews: list[ReviewItemRecord]) -> list[str]:
    caveats = ["open_review_item", "continuity_review_item"]
    severities = {review.severity for review in reviews}
    if "high" in severities:
        caveats.append("high_severity_review")
    elif "medium" in severities:
        caveats.append("medium_severity_review")
    elif "low" in severities:
        caveats.append("low_severity_review")
    if len(reviews) > 1:
        caveats.append("multiple_continuity_reviews")
    return caveats


def _continuity_review_confidence(reviews: list[ReviewItemRecord]) -> float:
    if not reviews:
        return 0.0
    return max(
        {
            "high": 0.9,
            "medium": 0.75,
            "low": 0.6,
        }.get(review.severity, 0.5)
        for review in reviews
    )


def _continuity_severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def _format_continuity_review_answer(reviews: list[ReviewItemRecord]) -> str:
    return "Open continuity risks: " + "; ".join(
        f"[{review.severity} {review.review_type}] {review.summary}" for review in reviews
    )


def _memory_answer_event_timeline(
    session: Session,
    input_data: MemoryAnswerInput,
) -> tuple[StoryCanonicalEvent | None, list[StoryCanonicalEvent]] | None:
    if not _memory_answer_is_after_event_query(input_data.question):
        return None

    events = (
        session.query(StoryCanonicalEvent)
        .filter_by(project_id=input_data.project_id)
        .filter(StoryCanonicalEvent.event_status.in_(("canon", "external_canon", "author_note")))
        .all()
    )
    events = _events_with_same_project_source_spans(session, input_data.project_id, events)
    if not events:
        return None, []

    anchor_event = _best_matching_event(input_data.question, events)
    if anchor_event is None:
        return None, []
    anchor_key = _event_scene_sort_key(session, anchor_event)
    if anchor_key is None:
        return anchor_event, []

    later_events = [
        event
        for event in events
        if event.id != anchor_event.id
        and (event_key := _event_scene_sort_key(session, event)) is not None
        and event_key > anchor_key
    ]
    later_events.sort(
        key=lambda event: (
            _event_scene_sort_key(session, event) or (999999, 999999, 999999, str(event.id)),
            str(event.id),
        )
    )
    return anchor_event, later_events[:5]


def _memory_answer_event_overlap(
    session: Session,
    input_data: MemoryAnswerInput,
) -> tuple[StoryCanonicalEvent | None, list[StoryCanonicalEvent]] | None:
    if not _memory_answer_is_event_overlap_query(input_data.question):
        return None

    events = (
        session.query(StoryCanonicalEvent)
        .filter_by(project_id=input_data.project_id)
        .filter(StoryCanonicalEvent.event_status.in_(("canon", "external_canon", "author_note")))
        .all()
    )
    events = _events_with_same_project_source_spans(session, input_data.project_id, events)
    if not events:
        return None, []

    anchor_event = _best_matching_event(
        input_data.question,
        events,
        ignored_terms=MEMORY_ANSWER_EVENT_OVERLAP_TERMS,
    )
    if anchor_event is None:
        return None, []

    overlapping_events = [
        event
        for event in events
        if event.id != anchor_event.id and _events_overlap(anchor_event, event)
    ]
    overlapping_events.sort(
        key=lambda event: (
            _event_scene_sort_key(session, event) or (999999, 999999, 999999, str(event.id)),
            str(event.id),
        )
    )
    return anchor_event, overlapping_events[:5]


def _memory_answer_is_after_event_query(question: str) -> bool:
    tokens = _search_tokens(question)
    return bool(tokens.intersection(MEMORY_ANSWER_EVENT_AFTER_TERMS)) and bool(
        tokens.intersection(MEMORY_ANSWER_EVENT_QUERY_TERMS)
        or "发生" in question
        or "happen" in question.casefold()
    )


def _memory_answer_is_event_overlap_query(question: str) -> bool:
    tokens = _search_tokens(question)
    lowered = question.casefold()
    return bool(tokens.intersection(MEMORY_ANSWER_EVENT_OVERLAP_TERMS)) and bool(
        tokens.intersection(MEMORY_ANSWER_EVENT_QUERY_TERMS)
        or "same time" in lowered
        or "happen" in lowered
        or "发生" in question
    )


def _best_matching_event(
    question: str,
    events: list[StoryCanonicalEvent],
    *,
    ignored_terms: set[str] | None = None,
) -> StoryCanonicalEvent | None:
    query_tokens = _meaningful_search_tokens(question)
    query_tokens -= MEMORY_ANSWER_EVENT_AFTER_TERMS
    query_tokens -= MEMORY_ANSWER_EVENT_OVERLAP_TERMS
    query_tokens -= MEMORY_ANSWER_EVENT_QUERY_TERMS
    if ignored_terms:
        query_tokens -= ignored_terms
    if not query_tokens:
        return None

    scored: list[tuple[int, StoryCanonicalEvent]] = []
    for event in events:
        score = _event_query_overlap(event, query_tokens)
        if score > 0:
            scored.append((score, event))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], str(item[1].id)))
    return scored[0][1]


def _event_query_overlap(event: StoryCanonicalEvent, query_tokens: set[str]) -> int:
    title_tokens = _search_tokens(event.title)
    summary_tokens = _search_tokens(event.summary)
    object_tokens = _search_tokens(event.objects)
    participant_tokens = _search_tokens(event.participants)
    return (
        len(query_tokens & title_tokens) * 4
        + len(query_tokens & object_tokens) * 3
        + len(query_tokens & summary_tokens) * 2
        + len(query_tokens & participant_tokens)
    )


def _events_overlap(
    anchor_event: StoryCanonicalEvent, candidate_event: StoryCanonicalEvent
) -> bool:
    if (
        anchor_event.primary_scene_id is not None
        and candidate_event.primary_scene_id is not None
        and anchor_event.primary_scene_id == candidate_event.primary_scene_id
    ):
        return True
    anchor_time = _normalized_story_time(anchor_event.story_time)
    candidate_time = _normalized_story_time(candidate_event.story_time)
    if not anchor_time or not candidate_time:
        return False
    if anchor_time == candidate_time:
        return True

    anchor_window = _story_time_window(anchor_time)
    candidate_window = _story_time_window(candidate_time)
    if anchor_window is None or candidate_window is None:
        return False
    anchor_prefix, anchor_start, anchor_end = anchor_window
    candidate_prefix, candidate_start, candidate_end = candidate_window
    return (
        anchor_prefix == candidate_prefix
        and anchor_start <= candidate_end
        and candidate_start <= anchor_end
    )


def _normalized_story_time(story_time: str | None) -> str:
    return re.sub(r"\s+", " ", story_time.strip().casefold()) if story_time else ""


StoryTimeWindow = tuple[str, float, float]


def _story_time_window(normalized_story_time: str) -> StoryTimeWindow | None:
    range_match = re.fullmatch(
        r"(?P<prefix>.+?)\s+(?P<start>\d+(?:\.\d+)?)\s*(?:-|to|through)\s*"
        r"(?P<end>\d+(?:\.\d+)?)",
        normalized_story_time,
    )
    if range_match:
        start = float(range_match.group("start"))
        end = float(range_match.group("end"))
        return range_match.group("prefix").strip(), min(start, end), max(start, end)

    point_match = re.fullmatch(
        r"(?P<prefix>.+?)\s+(?P<point>\d+(?:\.\d+)?)",
        normalized_story_time,
    )
    if point_match:
        point = float(point_match.group("point"))
        return point_match.group("prefix").strip(), point, point
    return None


def _event_scene_sort_key(
    session: Session,
    event: StoryCanonicalEvent,
) -> tuple[int, int, int, str] | None:
    if event.primary_scene_id is None:
        return None
    scene = session.get(StoryScene, event.primary_scene_id)
    if scene is None:
        return None
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return None
    return (chapter.chapter_index, scene.scene_index, scene.start_offset, str(scene.id))


def _events_with_same_project_source_spans(
    session: Session,
    project_id: UUID,
    events: list[StoryCanonicalEvent],
) -> list[StoryCanonicalEvent]:
    return [
        event
        for event in events
        if _valid_source_span_id_strings(session, project_id, event.evidence_span_ids)
    ]


def _event_answer_span_ids(
    session: Session,
    project_id: UUID,
    anchor_event: StoryCanonicalEvent,
    later_events: list[StoryCanonicalEvent],
) -> list[str]:
    return _event_source_span_ids(session, project_id, [anchor_event, *later_events])


def _event_source_span_ids(
    session: Session,
    project_id: UUID,
    events: list[StoryCanonicalEvent],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for event in events:
        for span_id in _valid_source_span_id_strings(session, project_id, event.evidence_span_ids):
            if span_id not in seen:
                seen.add(span_id)
                result.append(span_id)
    return result


def _event_answer_affected_entities(
    events: list[StoryCanonicalEvent],
) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for event in events:
        for ref in [*event.participants, *event.objects]:
            copied = dict(ref)
            key = json.dumps(copied, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            result.append(copied)
    return result


def _event_answer_confidence(events: list[StoryCanonicalEvent]) -> float:
    if not events:
        return 0.0
    if any(event.event_status == "author_note" for event in events):
        return 0.95
    if any(event.event_status == "external_canon" for event in events):
        return 0.92
    return 0.9


def _format_event_timeline_answer(
    anchor_event: StoryCanonicalEvent,
    later_events: list[StoryCanonicalEvent],
) -> str:
    prefix = f"After {anchor_event.title}: "
    return prefix + "; ".join(_format_event_answer(event) for event in later_events)


def _format_event_overlap_answer(
    anchor_event: StoryCanonicalEvent,
    overlapping_events: list[StoryCanonicalEvent],
) -> str:
    prefix = f"During {anchor_event.title}: "
    return prefix + "; ".join(_format_event_answer(event) for event in overlapping_events)


def _format_event_answer(event: StoryCanonicalEvent) -> str:
    answer = f"{event.title} - {event.summary}"
    if event.consequence_summary:
        answer = f"{answer} Consequence: {event.consequence_summary}"
    return answer


RelationshipPath = tuple[list[FactAssertionRecord], list[str]]


def _memory_answer_relationship_path(
    session: Session,
    input_data: MemoryAnswerInput,
) -> RelationshipPath | None:
    if input_data.subject_ref is not None or input_data.predicate is not None:
        return None
    if not _memory_answer_is_relationship_path_query(input_data.question):
        return None
    if _memory_answer_ambiguous_entity_match(session, input_data) is not None:
        return None

    target_entity_ids = _memory_answer_explicit_or_alias_entity_ids_in_question_order(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    if len(target_entity_ids) != 2:
        return [], []

    relationship_facts = [
        fact
        for fact in session.query(FactAssertionRecord).filter_by(project_id=input_data.project_id)
        if fact.predicate in MEMORY_ANSWER_RELATIONSHIP_PREDICATES
        and _valid_source_span_id_strings(session, input_data.project_id, fact.evidence_span_ids)
    ]
    question_tokens = _search_tokens(input_data.question)
    for start_id, end_id in _relationship_path_target_pairs(target_entity_ids):
        path = _find_relationship_path(
            relationship_facts,
            start_id,
            end_id,
            max_edges=MEMORY_ANSWER_RELATIONSHIP_PATH_MAX_EDGES,
            question_tokens=question_tokens,
        )
        if path[0]:
            return path
    return [], []


def _memory_answer_is_relationship_path_query(question: str) -> bool:
    tokens = _search_tokens(question)
    return bool(tokens.intersection(MEMORY_ANSWER_RELATIONSHIP_PATH_TERMS)) or (
        _question_contains_cjk_term(question, MEMORY_ANSWER_RELATIONSHIP_PATH_TERMS)
    )


def _relationship_path_target_pairs(target_entity_ids: list[UUID]) -> list[tuple[str, str]]:
    ids = [str(entity_id).casefold() for entity_id in target_entity_ids]
    if len(ids) != 2:
        return []
    first, second = ids
    return [(first, second), (second, first)]


def _find_relationship_path(
    relationship_facts: list[FactAssertionRecord],
    start_id: str,
    end_id: str,
    *,
    max_edges: int,
    question_tokens: set[str],
) -> RelationshipPath:
    queue: list[tuple[str, list[FactAssertionRecord], list[str], set[str]]] = [
        (start_id, [], [start_id], {start_id})
    ]
    candidates: list[RelationshipPath] = []
    while queue:
        current_key, path, node_keys, visited_keys = queue.pop(0)
        if len(path) >= max_edges:
            continue
        path_fact_ids = {fact.id for fact in path}
        for fact in relationship_facts:
            if fact.id in path_fact_ids:
                continue
            left_keys, right_keys = _relationship_fact_endpoint_keys(fact)
            neighbor_keys: set[str] | None = None
            if current_key in left_keys:
                neighbor_keys = right_keys
            elif current_key in right_keys:
                neighbor_keys = left_keys
            if not neighbor_keys:
                continue
            next_path = [*path, fact]
            if end_id in neighbor_keys:
                candidates.append((next_path, [*node_keys, end_id]))
                continue
            for neighbor_key in sorted(neighbor_keys):
                if neighbor_key in visited_keys:
                    continue
                queue.append(
                    (
                        neighbor_key,
                        next_path,
                        [*node_keys, neighbor_key],
                        {*visited_keys, neighbor_key},
                    )
                )
    if candidates:
        candidates.sort(
            key=lambda candidate: _relationship_path_rank_key(
                candidate[0],
                question_tokens=question_tokens,
            )
        )
        return candidates[0]
    return [], []


def _relationship_path_rank_key(
    path: list[FactAssertionRecord],
    *,
    question_tokens: set[str],
) -> tuple[int, int, int, float, float, int, tuple[str, ...]]:
    return (
        -_relationship_path_predicate_match_count(path, question_tokens),
        _relationship_path_non_canon_count(path),
        -_relationship_path_min_status_rank(path),
        -_memory_answer_confidence(path),
        -_relationship_path_average_confidence(path),
        len(path),
        tuple(str(fact.id) for fact in path),
    )


def _relationship_path_predicate_match_count(
    path: list[FactAssertionRecord],
    question_tokens: set[str],
) -> int:
    return sum(
        1
        for fact in path
        if question_tokens.intersection(
            MEMORY_ANSWER_RELATIONSHIP_PREDICATE_TERMS.get(fact.predicate, set())
        )
    )


def _relationship_path_non_canon_count(path: list[FactAssertionRecord]) -> int:
    return sum(1 for fact in path if fact.fact_status != "canon")


def _relationship_path_min_status_rank(path: list[FactAssertionRecord]) -> int:
    if not path:
        return 0
    return min(_relationship_fact_status_rank(fact.fact_status) for fact in path)


def _relationship_fact_status_rank(status: str) -> int:
    if status == "canon":
        return 4
    if status in {"external_canon", "author_note"}:
        return 3
    if status == "proposed":
        return 2
    if status in {"disputed", "blocked"}:
        return 1
    return 0


def _relationship_path_average_confidence(path: list[FactAssertionRecord]) -> float:
    if not path:
        return 0.0
    return sum(float(fact.confidence) for fact in path) / len(path)


def _relationship_fact_endpoint_keys(
    fact: FactAssertionRecord,
) -> tuple[set[str], set[str]]:
    return _ref_semantic_keys(fact.subject_ref), _ref_semantic_keys(fact.object_ref)


def _relationship_path_caveats(
    *,
    has_non_canon_evidence: bool,
    has_open_review_items: bool,
    safe_to_use_in_current_pov: bool,
) -> list[str]:
    caveats = ["relationship_path_from_fact_evidence"]
    if has_non_canon_evidence:
        caveats.append("non_canon_evidence")
    if has_open_review_items:
        caveats.append("open_review_item")
    if not safe_to_use_in_current_pov:
        caveats.append("not_safe_for_current_pov")
    return caveats


def _format_relationship_path_answer(
    path: list[FactAssertionRecord],
    node_keys: list[str],
) -> str:
    if len(node_keys) != len(path) + 1:
        return "Relationship path: " + "; ".join(_format_fact(fact) for fact in path)

    segments: list[str] = []
    for index, fact in enumerate(path):
        from_ref = _relationship_fact_ref_for_node_key(fact, node_keys[index])
        to_ref = _relationship_fact_ref_for_node_key(fact, node_keys[index + 1])
        if from_ref is None or to_ref is None:
            segments.append(_format_fact(fact))
            continue
        segments.append(f"{_ref_label(from_ref)} {fact.predicate} {_ref_label(to_ref)}")
    return "Relationship path: " + "; ".join(segments)


def _relationship_path_affected_entities(
    path: list[FactAssertionRecord],
    node_keys: list[str],
) -> list[dict[str, object]]:
    if len(node_keys) != len(path) + 1:
        return _memory_answer_affected_entities(path)

    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for node_key in node_keys:
        ref = _relationship_path_ref_for_node_key(path, node_key)
        if ref is None:
            continue
        copied = dict(ref)
        key = json.dumps(copied, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(copied)
    return result


def _relationship_path_ref_for_node_key(
    path: list[FactAssertionRecord],
    node_key: str,
) -> dict[str, object] | None:
    for fact in path:
        ref = _relationship_fact_ref_for_node_key(fact, node_key)
        if ref is not None:
            return ref
    return None


def _relationship_fact_ref_for_node_key(
    fact: FactAssertionRecord,
    node_key: str,
) -> dict[str, object] | None:
    normalized_node_key = node_key.casefold()
    for ref in (fact.subject_ref, fact.object_ref):
        if normalized_node_key in _ref_semantic_keys(ref):
            return ref
    return None


RelationshipTimelineEntry = tuple[
    FactAssertionRecord,
    SourceSpan,
    StoryChapter | None,
    StoryScene | None,
]


def _memory_answer_relationship_timeline(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[RelationshipTimelineEntry] | None:
    if input_data.subject_ref is not None or input_data.predicate is not None:
        return None
    if not _memory_answer_is_relationship_timeline_query(input_data.question):
        return None

    facts = session.query(FactAssertionRecord).filter_by(project_id=input_data.project_id).all()
    if not facts:
        return []

    ref_keys = _memory_answer_ref_keys(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        facts=facts,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    relationship_facts = [
        fact
        for fact in facts
        if fact.predicate in MEMORY_ANSWER_RELATIONSHIP_PREDICATES
        and _relationship_fact_matches_refs(fact, ref_keys)
    ]
    entries_with_keys: list[tuple[tuple[int, int, int, int, str], RelationshipTimelineEntry]] = []
    for fact in relationship_facts:
        timeline_context = _relationship_timeline_context(session, input_data.project_id, fact)
        if timeline_context is None:
            continue
        sort_key, entry = timeline_context
        entries_with_keys.append((sort_key, entry))
    entries_with_keys.sort(key=lambda item: (item[0], str(item[1][0].id)))
    entries = [entry for _sort_key, entry in entries_with_keys]
    if len(entries) < 2:
        return []
    return entries[:8]


def _memory_answer_is_relationship_timeline_query(question: str) -> bool:
    if not _memory_answer_is_relationship_query(question):
        return False
    tokens = _search_tokens(question)
    return (
        bool(tokens.intersection(MEMORY_ANSWER_RELATIONSHIP_TIMELINE_TERMS))
        or _question_contains_cjk_term(question, MEMORY_ANSWER_RELATIONSHIP_TIMELINE_TERMS)
        or ("over" in tokens and "time" in tokens)
    )


def _relationship_timeline_context(
    session: Session,
    project_id: UUID,
    fact: FactAssertionRecord,
) -> tuple[tuple[int, int, int, int, str], RelationshipTimelineEntry] | None:
    span = _first_same_project_source_span(session, project_id, fact.evidence_span_ids)
    if span is None:
        return None

    scene_id = fact.valid_from_scene_id or span.scene_id
    scene = session.get(StoryScene, scene_id) if scene_id is not None else None
    chapter_id = scene.chapter_id if scene is not None else span.chapter_id
    chapter = session.get(StoryChapter, chapter_id) if chapter_id is not None else None
    if chapter is None or scene is None:
        return None
    sort_key = (
        chapter.chapter_index,
        scene.scene_index,
        span.start_offset,
        span.raw_start_offset,
        str(fact.id),
    )
    return sort_key, (fact, span, chapter, scene)


def _first_same_project_source_span(
    session: Session,
    project_id: UUID,
    span_ids: list[str],
) -> SourceSpan | None:
    for span_id in span_ids:
        span_uuid = _uuid_or_none(span_id)
        if span_uuid is None:
            continue
        span = session.get(SourceSpan, span_uuid)
        if span is not None and _source_span_belongs_to_project(session, span, project_id):
            return span
    return None


def _relationship_timeline_span_ids(entries: list[RelationshipTimelineEntry]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for _fact, span, _chapter, _scene in entries:
        span_id = str(span.id)
        if span_id not in seen:
            seen.add(span_id)
            result.append(span_id)
    return result


def _relationship_timeline_caveats(
    *,
    has_non_canon_evidence: bool,
    has_open_review_items: bool,
    safe_to_use_in_current_pov: bool,
) -> list[str]:
    caveats = ["relationship_timeline_from_scene_position"]
    if has_non_canon_evidence:
        caveats.append("non_canon_evidence")
    if has_open_review_items:
        caveats.append("open_review_item")
    if not safe_to_use_in_current_pov:
        caveats.append("not_safe_for_current_pov")
    return caveats


def _format_relationship_timeline_answer(entries: list[RelationshipTimelineEntry]) -> str:
    rendered = [
        (
            f"{_relationship_timeline_location_label(chapter, scene)}: "
            f"{_format_fact(fact)} ({fact.fact_status})"
            f"{_relationship_timeline_preview_suffix(span)}"
        )
        for fact, span, chapter, scene in entries
    ]
    return "Relationship timeline: " + "; ".join(rendered)


def _relationship_timeline_location_label(
    chapter: StoryChapter | None,
    scene: StoryScene | None,
) -> str:
    if chapter is not None and scene is not None:
        return f"Chapter {chapter.chapter_index + 1} / Scene {scene.scene_index + 1}"
    if chapter is not None:
        return f"Chapter {chapter.chapter_index + 1}"
    if scene is not None:
        return f"Scene {scene.scene_index + 1}"
    return "unsorted source evidence"


def _relationship_timeline_preview_suffix(span: SourceSpan) -> str:
    preview = span.text_preview.strip()
    return f" - {preview}" if preview else ""


def _memory_answer_relationship_explanation(
    session: Session,
    input_data: MemoryAnswerInput,
) -> tuple[list[FactAssertionRecord], list[StoryCanonicalEvent]] | None:
    if input_data.subject_ref is not None or input_data.predicate is not None:
        return None
    if not _memory_answer_is_relationship_query(input_data.question):
        return None

    facts = session.query(FactAssertionRecord).filter_by(project_id=input_data.project_id).all()
    if not facts:
        return [], []

    predicate = _infer_memory_answer_relationship_predicate(input_data.question)
    ref_keys = _memory_answer_ref_keys(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        facts=facts,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    relationship_facts = [
        fact
        for fact in facts
        if fact.predicate in MEMORY_ANSWER_RELATIONSHIP_PREDICATES
        and (predicate is None or fact.predicate == predicate)
        and _relationship_fact_matches_refs(fact, ref_keys)
    ]
    relationship_facts = _facts_with_same_project_source_spans(
        session,
        input_data.project_id,
        relationship_facts,
    )
    relationship_facts.sort(
        key=lambda fact: (
            0 if fact.fact_status == "canon" else 1,
            -fact.confidence,
            str(fact.id),
        )
    )
    supporting_events = _relationship_supporting_events(
        session,
        project_id=input_data.project_id,
        relationship_facts=relationship_facts,
        ref_keys=ref_keys,
    )
    return relationship_facts[:5], supporting_events


def _memory_answer_is_relationship_query(question: str) -> bool:
    tokens = _search_tokens(question)
    if tokens.intersection(MEMORY_ANSWER_RELATIONSHIP_QUERY_TERMS) or _question_contains_cjk_term(
        question, MEMORY_ANSWER_RELATIONSHIP_QUERY_TERMS
    ):
        return True
    if _memory_answer_has_negated_trust_paraphrase(question):
        return True
    return any(
        predicate in tokens
        or tokens.intersection(terms)
        or _question_contains_cjk_term(question, terms)
        for predicate, terms in MEMORY_ANSWER_RELATIONSHIP_PREDICATE_TERMS.items()
    )


def _infer_memory_answer_relationship_predicate(question: str) -> str | None:
    if _memory_answer_has_negated_trust_paraphrase(question):
        return "enemy_of"
    tokens = _search_tokens(question)
    for predicate, terms in MEMORY_ANSWER_RELATIONSHIP_PREDICATE_TERMS.items():
        if (
            predicate in tokens
            or tokens.intersection(terms)
            or _question_contains_cjk_term(question, terms)
        ):
            return predicate
    return None


def _memory_answer_has_negated_trust_paraphrase(question: str) -> bool:
    lowered = question.casefold()
    return any(phrase in lowered for phrase in MEMORY_ANSWER_RELATIONSHIP_NEGATED_TRUST_PHRASES)


def _question_contains_cjk_term(question: str, terms: set[str]) -> bool:
    lowered = question.casefold()
    return any(_has_cjk(term) and term in lowered for term in terms)


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def _relationship_fact_matches_refs(
    fact: FactAssertionRecord,
    ref_keys: set[str],
) -> bool:
    if not ref_keys:
        return True
    subject_match = bool(ref_keys.intersection(_ref_semantic_keys(fact.subject_ref)))
    object_match = bool(ref_keys.intersection(_ref_semantic_keys(fact.object_ref)))
    if len(ref_keys) >= 2:
        return subject_match and object_match
    return subject_match or object_match


def _relationship_supporting_events(
    session: Session,
    *,
    project_id: UUID,
    relationship_facts: list[FactAssertionRecord],
    ref_keys: set[str],
) -> list[StoryCanonicalEvent]:
    if not relationship_facts:
        return []
    relationship_keys = set(ref_keys)
    for fact in relationship_facts:
        relationship_keys.update(_ref_semantic_keys(fact.subject_ref))
        relationship_keys.update(_ref_semantic_keys(fact.object_ref))
    events = (
        session.query(StoryCanonicalEvent)
        .filter_by(project_id=project_id)
        .filter(StoryCanonicalEvent.event_status.in_(("canon", "external_canon", "author_note")))
        .all()
    )
    events = _events_with_same_project_source_spans(session, project_id, events)
    scored: list[tuple[int, StoryCanonicalEvent]] = []
    for event in events:
        event_keys = _event_ref_keys(event)
        overlap = len(relationship_keys.intersection(event_keys))
        if len(relationship_keys) >= 2 and overlap < 2:
            continue
        if overlap == 0:
            continue
        scored.append((overlap, event))
    scored.sort(key=lambda item: (-item[0], str(item[1].id)))
    return [event for _score, event in scored[:3]]


def _event_ref_keys(event: StoryCanonicalEvent) -> set[str]:
    keys: set[str] = set()
    for ref in [*event.participants, *event.objects]:
        keys.update(_ref_semantic_keys(ref))
    return keys


def _relationship_answer_span_ids(
    session: Session,
    project_id: UUID,
    relationship_facts: list[FactAssertionRecord],
    supporting_events: list[StoryCanonicalEvent],
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for span_id in _fact_source_span_ids(session, project_id, relationship_facts):
        if span_id not in seen:
            seen.add(span_id)
            result.append(span_id)
    for span_id in _event_source_span_ids(session, project_id, supporting_events):
        if span_id not in seen:
            seen.add(span_id)
            result.append(span_id)
    return result


def _relationship_answer_caveats(
    *,
    supporting_events: list[StoryCanonicalEvent],
    has_non_canon_evidence: bool,
    has_open_review_items: bool,
    safe_to_use_in_current_pov: bool,
) -> list[str]:
    caveats: list[str] = []
    if supporting_events:
        caveats.append("relationship_explained_by_canonical_event")
    else:
        caveats.append("relationship_fact_without_event_explanation")
    if has_non_canon_evidence:
        caveats.append("non_canon_evidence")
    if has_open_review_items:
        caveats.append("open_review_item")
    if not safe_to_use_in_current_pov:
        caveats.append("not_safe_for_current_pov")
    return caveats


def _format_relationship_answer(
    relationship_facts: list[FactAssertionRecord],
    supporting_events: list[StoryCanonicalEvent],
) -> str:
    fact_answer = "; ".join(_format_fact(fact) for fact in relationship_facts)
    if not supporting_events:
        return fact_answer
    event_answer = "; ".join(_format_event_answer(event) for event in supporting_events)
    return f"{fact_answer} because {event_answer}"


def _memory_answer_character_knowledge_matches(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[tuple[CharacterKnowledge, FactAssertionRecord]] | None:
    certainties = _memory_answer_knowledge_certainties(input_data)
    if certainties is None:
        return None

    character_ids = _memory_answer_character_ids(session, input_data)
    if not character_ids:
        return None

    knowledge_rows = (
        session.query(CharacterKnowledge)
        .filter(CharacterKnowledge.project_id == input_data.project_id)
        .filter(CharacterKnowledge.status == "active")
        .filter(CharacterKnowledge.character_id.in_(character_ids))
        .order_by(CharacterKnowledge.created_at, CharacterKnowledge.id)
        .all()
    )
    matches: list[tuple[CharacterKnowledge, FactAssertionRecord]] = []
    for knowledge in knowledge_rows:
        if knowledge.certainty not in certainties:
            continue
        fact = _knowledge_fact(session, input_data.project_id, knowledge)
        if fact is None:
            continue
        if not _knowledge_fact_matches_certainties(fact, certainties):
            continue
        if not _valid_source_span_id_strings(
            session,
            input_data.project_id,
            [knowledge.evidence_span_id],
        ):
            continue
        if not _valid_source_span_id_strings(
            session,
            input_data.project_id,
            fact.evidence_span_ids,
        ):
            continue
        matches.append((knowledge, fact))

    focus_tokens = _memory_answer_knowledge_focus_tokens(session, input_data, character_ids)
    if focus_tokens:
        narrowed = [
            (knowledge, fact)
            for knowledge, fact in matches
            if _text_matches_query(fact.object_ref, focus_tokens, input_data.question)
        ]
        if narrowed or not _memory_answer_is_knowledge_inventory(input_data.question):
            matches = narrowed
    matches.sort(
        key=lambda item: (
            _knowledge_certainty_sort_rank(item[0].certainty),
            _ref_label(item[1].object_ref).casefold(),
            str(item[1].id),
        )
    )
    return matches


def _memory_answer_knowledge_certainties(input_data: MemoryAnswerInput) -> set[str] | None:
    question = input_data.question.casefold()
    tokens = _search_tokens(question)
    predicate = input_data.predicate
    if (
        predicate == "does_not_know"
        or "does not know" in question
        or "doesn't know" in question
        or any(term in question for term in ("不知道", "不知"))
    ):
        return {"does_not_know"}
    if tokens.intersection(MEMORY_ANSWER_NOT_KNOW_TERMS) and tokens.intersection(
        MEMORY_ANSWER_KNOWLEDGE_GENERIC_TERMS
    ):
        return {"does_not_know"}
    if tokens.intersection(MEMORY_ANSWER_MISUNDERSTAND_TERMS) or "误以为" in question:
        return {"misunderstands", "false_belief"}
    if tokens.intersection(MEMORY_ANSWER_SUSPECT_TERMS):
        return {"suspected"}
    if (
        predicate == "knows"
        or tokens.intersection(MEMORY_ANSWER_KNOWLEDGE_GENERIC_TERMS)
        or any(term in question for term in ("知道", "得知", "秘密"))
    ):
        return {"known", "suspected", "false_belief", "misunderstands"}
    return None


def _memory_answer_character_ids(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[UUID]:
    ids: list[UUID] = []
    if input_data.subject_ref is not None:
        for key in ("canonical_entity_id", "id"):
            value = input_data.subject_ref.get(key)
            parsed = _uuid_or_none(value)
            if parsed is not None:
                entity = session.get(StoryCanonicalEntity, parsed)
                if entity is None or (
                    entity.project_id == input_data.project_id and entity.entity_type == "character"
                ):
                    ids.append(parsed)
                break

    query_tokens = _meaningful_search_tokens(input_data.question)
    if query_tokens:
        for entity in (
            session.query(StoryCanonicalEntity)
            .filter_by(project_id=input_data.project_id, entity_type="character")
            .all()
        ):
            if _text_matches_query(entity.display_name, query_tokens, input_data.question):
                ids.append(entity.id)
        for alias in session.query(StoryAliasRecord).filter_by(project_id=input_data.project_id):
            if alias.entity_id is None:
                continue
            entity = session.get(StoryCanonicalEntity, alias.entity_id)
            if entity is None or entity.entity_type != "character":
                continue
            if _text_matches_query(alias.alias_text, query_tokens, input_data.question):
                ids.append(alias.entity_id)

    seen: set[UUID] = set()
    result: list[UUID] = []
    for character_id in ids:
        if character_id not in seen:
            seen.add(character_id)
            result.append(character_id)
    return result


def _memory_answer_knowledge_focus_tokens(
    session: Session,
    input_data: MemoryAnswerInput,
    character_ids: list[UUID],
) -> set[str]:
    focus_tokens = _meaningful_search_tokens(input_data.question)
    focus_tokens -= MEMORY_ANSWER_KNOWLEDGE_GENERIC_TERMS
    focus_tokens -= MEMORY_ANSWER_NOT_KNOW_TERMS
    focus_tokens -= MEMORY_ANSWER_SUSPECT_TERMS
    focus_tokens -= MEMORY_ANSWER_MISUNDERSTAND_TERMS
    focus_tokens -= MEMORY_ANSWER_KNOWLEDGE_INVENTORY_TERMS
    for character_id in character_ids:
        entity = session.get(StoryCanonicalEntity, character_id)
        if entity is not None:
            focus_tokens -= _search_tokens(entity.display_name)
        for alias in (
            session.query(StoryAliasRecord)
            .filter_by(project_id=input_data.project_id, entity_id=character_id)
            .all()
        ):
            focus_tokens -= _search_tokens(alias.alias_text)
    return focus_tokens


def _memory_answer_is_knowledge_inventory(question: str) -> bool:
    tokens = _search_tokens(question)
    lowered = question.casefold()
    if any(term in lowered for term in ("什么", "哪些")) and any(
        term in lowered for term in ("知道", "不知", "秘密")
    ):
        return True
    return bool(tokens.intersection(MEMORY_ANSWER_KNOWLEDGE_INVENTORY_TERMS))


def _knowledge_fact(
    session: Session,
    project_id: UUID,
    knowledge: CharacterKnowledge,
) -> FactAssertionRecord | None:
    if knowledge.knows_ref.get("type") != "fact_assertion":
        return None
    fact_id = _uuid_or_none(knowledge.knows_ref.get("id"))
    if fact_id is None:
        return None
    fact = session.get(FactAssertionRecord, fact_id)
    if fact is None or fact.project_id != project_id:
        return None
    return fact


def _knowledge_fact_matches_certainties(
    fact: FactAssertionRecord,
    certainties: set[str],
) -> bool:
    if certainties == {"does_not_know"}:
        return fact.predicate == "does_not_know"
    return fact.predicate == "knows"


def _knowledge_certainty_sort_rank(certainty: str) -> int:
    return {
        "known": 0,
        "suspected": 1,
        "misunderstands": 2,
        "false_belief": 3,
        "does_not_know": 4,
    }.get(certainty, 9)


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


FirstAppearance = tuple[
    StoryMention,
    SourceSpan,
    StoryCanonicalEntity,
    StoryChapter | None,
    StoryScene | None,
]

AmbiguousEntityMatch = tuple[str, list[StoryCanonicalEntity], list[str]]


def _memory_answer_ambiguous_entity_match(
    session: Session,
    input_data: MemoryAnswerInput,
) -> AmbiguousEntityMatch | None:
    query_tokens = _meaningful_search_tokens(input_data.question)
    if not query_tokens:
        return None

    explicit_entity_ids = _memory_answer_explicit_entity_ids(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
    )
    surfaces: dict[str, dict[str, object]] = {}
    for entity in session.query(StoryCanonicalEntity).filter_by(project_id=input_data.project_id):
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        if not _text_matches_query(entity.display_name, query_tokens, input_data.question):
            description_surface = _entity_description_query_surface(
                entity,
                query_tokens,
                input_data.question.casefold(),
            )
            if description_surface is None:
                continue
            _record_ambiguous_entity_surface(
                surfaces,
                surface=description_surface,
                entity=entity,
                span_ids=[],
            )
        else:
            _record_ambiguous_entity_surface(
                surfaces,
                surface=entity.display_name,
                entity=entity,
                span_ids=[],
            )

    for alias in session.query(StoryAliasRecord).filter_by(project_id=input_data.project_id):
        if alias.entity_id is None or alias.status == "rejected":
            continue
        if not _text_matches_query(alias.alias_text, query_tokens, input_data.question):
            continue
        entity = session.get(StoryCanonicalEntity, alias.entity_id)
        if entity is None or entity.project_id != input_data.project_id:
            continue
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        _record_ambiguous_entity_surface(
            surfaces,
            surface=alias.alias_text,
            entity=entity,
            span_ids=alias.evidence_span_ids,
        )

    for surface_info in surfaces.values():
        entities_by_id = cast(dict[UUID, StoryCanonicalEntity], surface_info["entities_by_id"])
        if len(entities_by_id) < 2:
            continue
        if explicit_entity_ids:
            explicitly_named_ids = [
                entity_id for entity_id in entities_by_id if entity_id in explicit_entity_ids
            ]
            if len(explicitly_named_ids) == 1:
                continue
            if len(explicitly_named_ids) > 1:
                entities_by_id = {
                    entity_id: entities_by_id[entity_id] for entity_id in explicitly_named_ids
                }
        else:
            scoped_entity_ids = _memory_answer_scoped_alias_context_entity_ids(
                session,
                project_id=input_data.project_id,
                surface=str(surface_info["surface"]),
                question=input_data.question,
                current_scene_id=input_data.current_scene_id,
                current_pov_character_id=input_data.current_pov_character_id,
            )
            if len(scoped_entity_ids) == 1:
                continue
        entities = sorted(
            entities_by_id.values(),
            key=lambda item: (item.display_name, str(item.id)),
        )
        span_ids = _unique_str_sequence(cast(list[str], surface_info["span_ids"]))
        return str(surface_info["surface"]), entities, span_ids
    return None


def _record_ambiguous_entity_surface(
    surfaces: dict[str, dict[str, object]],
    *,
    surface: str,
    entity: StoryCanonicalEntity,
    span_ids: list[str],
) -> None:
    key = surface.strip().casefold()
    if not key:
        return
    surface_info = surfaces.setdefault(
        key,
        {"surface": surface.strip(), "entities_by_id": {}, "span_ids": []},
    )
    entities_by_id = cast(dict[UUID, StoryCanonicalEntity], surface_info["entities_by_id"])
    entities_by_id[entity.id] = entity
    surface_info["span_ids"] = cast(list[str], surface_info["span_ids"]) + span_ids


def _memory_answer_explicit_entity_ids(
    session: Session,
    *,
    project_id: UUID,
    question: str,
) -> set[UUID]:
    query_tokens = _meaningful_search_tokens(question)
    if not query_tokens:
        return set()
    return {
        entity.id
        for entity in session.query(StoryCanonicalEntity).filter_by(project_id=project_id).all()
        if entity.canonical_status not in {"discarded", "contradicted"}
        and _text_matches_query(entity.display_name, query_tokens, question)
    }


def _memory_answer_explicit_entity_ids_in_question_order(
    session: Session,
    *,
    project_id: UUID,
    question: str,
) -> list[UUID]:
    query_tokens = _meaningful_search_tokens(question)
    if not query_tokens:
        return []

    question_text = question.casefold()
    matches: list[tuple[int, str, UUID]] = []
    for entity in session.query(StoryCanonicalEntity).filter_by(project_id=project_id).all():
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        if not _text_matches_query(entity.display_name, query_tokens, question):
            continue
        display_name = entity.display_name.strip()
        index = question_text.find(display_name.casefold()) if display_name else -1
        matches.append((index if index >= 0 else 1_000_000, display_name, entity.id))

    seen: set[UUID] = set()
    result: list[UUID] = []
    for _index, _display_name, entity_id in sorted(
        matches, key=lambda item: (item[0], item[1], str(item[2]))
    ):
        if entity_id in seen:
            continue
        seen.add(entity_id)
        result.append(entity_id)
    return result


def _memory_answer_explicit_or_alias_entity_ids_in_question_order(
    session: Session,
    *,
    project_id: UUID,
    question: str,
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> list[UUID]:
    query_tokens = _meaningful_search_tokens(question)
    if not query_tokens:
        return []

    question_text = question.casefold()
    matches: list[tuple[int, str, UUID]] = []
    explicit_entity_ids: set[UUID] = set()
    for entity in session.query(StoryCanonicalEntity).filter_by(project_id=project_id).all():
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        if _text_matches_query(entity.display_name, query_tokens, question):
            explicit_entity_ids.add(entity.id)
            _append_memory_answer_entity_match(
                matches,
                question_text=question_text,
                surface=entity.display_name,
                entity_id=entity.id,
            )
        _append_memory_answer_entity_description_match(
            matches,
            question_text=question_text,
            entity=entity,
            query_tokens=query_tokens,
        )

    aliases_by_surface: dict[str, list[tuple[StoryAliasRecord, StoryCanonicalEntity]]] = {}
    for alias in session.query(StoryAliasRecord).filter_by(project_id=project_id).all():
        if alias.entity_id is None or alias.status == "rejected":
            continue
        if not _text_matches_query(alias.alias_text, query_tokens, question):
            continue
        entity = session.get(StoryCanonicalEntity, alias.entity_id)
        if entity is None or entity.project_id != project_id:
            continue
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        aliases_by_surface.setdefault(alias.alias_text.strip().casefold(), []).append(
            (alias, entity)
        )

    for alias_rows in aliases_by_surface.values():
        entity_ids = {entity.id for _alias, entity in alias_rows}
        if len(entity_ids) > 1:
            explicitly_named_alias_ids = entity_ids.intersection(explicit_entity_ids)
            if len(explicitly_named_alias_ids) == 1:
                entity_ids = explicitly_named_alias_ids
            else:
                scoped_entity_ids = _memory_answer_scoped_alias_context_entity_ids_from_rows(
                    session,
                    project_id=project_id,
                    alias_rows=alias_rows,
                    question=question,
                    current_scene_id=current_scene_id,
                    current_pov_character_id=current_pov_character_id,
                )
                if len(scoped_entity_ids) != 1:
                    continue
                entity_ids = scoped_entity_ids
        for alias, entity in alias_rows:
            if entity.id not in entity_ids:
                continue
            _append_memory_answer_entity_match(
                matches,
                question_text=question_text,
                surface=alias.alias_text,
                entity_id=entity.id,
            )

    seen: set[UUID] = set()
    result: list[UUID] = []
    for _index, _surface, entity_id in sorted(
        matches, key=lambda item: (item[0], item[1], str(item[2]))
    ):
        if entity_id in seen:
            continue
        seen.add(entity_id)
        result.append(entity_id)
    return result


def _append_memory_answer_entity_match(
    matches: list[tuple[int, str, UUID]],
    *,
    question_text: str,
    surface: str,
    entity_id: UUID,
) -> None:
    normalized_surface = surface.strip()
    index = question_text.find(normalized_surface.casefold()) if normalized_surface else -1
    matches.append((index if index >= 0 else 1_000_000, normalized_surface, entity_id))


def _append_memory_answer_entity_description_match(
    matches: list[tuple[int, str, UUID]],
    *,
    question_text: str,
    entity: StoryCanonicalEntity,
    query_tokens: set[str],
) -> None:
    surface = _entity_description_query_surface(entity, query_tokens, question_text)
    if surface is None:
        return
    surface_tokens = surface.split()
    positions = [
        question_text.find(token) for token in surface_tokens if question_text.find(token) >= 0
    ]
    index = min(positions) if positions else 1_000_000
    matches.append((index, surface, entity.id))


def _format_ambiguous_entity_answer(
    surface: str,
    entities: list[StoryCanonicalEntity],
) -> str:
    candidates = ", ".join(entity.display_name for entity in entities)
    return f"Ambiguous entity match for `{surface}`: {candidates}."


def _memory_answer_entity_ref(entity: StoryCanonicalEntity) -> dict[str, object]:
    return {"type": entity.entity_type, "id": str(entity.id), "label": entity.display_name}


def _unique_str_sequence(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _memory_answer_first_appearance(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[FirstAppearance] | None:
    if not _memory_answer_is_first_appearance_query(input_data.question):
        return None

    target_entity_ids = _memory_answer_first_appearance_target_entity_ids(session, input_data)
    if not target_entity_ids:
        return []

    rows = cast(
        list[tuple[StoryMention, SourceSpan, StoryCanonicalEntity]],
        (
            session.query(StoryMention, SourceSpan, StoryCanonicalEntity)
            .join(SourceSpan, StoryMention.span_id == SourceSpan.id)
            .join(RawSource, SourceSpan.source_id == RawSource.id)
            .join(
                StoryCanonicalEntity,
                StoryMention.resolved_entity_id == StoryCanonicalEntity.id,
            )
            .filter(RawSource.project_id == input_data.project_id)
            .filter(StoryCanonicalEntity.project_id == input_data.project_id)
            .filter(StoryCanonicalEntity.canonical_status.notin_(("discarded", "contradicted")))
            .filter(StoryMention.resolved_entity_id.in_(target_entity_ids))
            .all()
        ),
    )
    if not rows:
        return []

    chapter_ids = {span.chapter_id for _mention, span, _entity in rows if span.chapter_id}
    scene_ids = {span.scene_id for _mention, span, _entity in rows if span.scene_id}
    chapters: dict[UUID, StoryChapter] = (
        {
            chapter.id: chapter
            for chapter in session.query(StoryChapter).filter(StoryChapter.id.in_(chapter_ids))
        }
        if chapter_ids
        else {}
    )
    scenes: dict[UUID, StoryScene] = (
        {
            scene.id: scene
            for scene in session.query(StoryScene).filter(StoryScene.id.in_(scene_ids))
        }
        if scene_ids
        else {}
    )
    appearances: list[FirstAppearance] = []
    for mention, span, entity in rows:
        chapter = chapters.get(span.chapter_id) if span.chapter_id is not None else None
        scene = scenes.get(span.scene_id) if span.scene_id is not None else None
        appearances.append((mention, span, entity, chapter, scene))
    appearances.sort(key=_first_appearance_sort_key)
    return appearances


def _memory_answer_is_first_appearance_query(question: str) -> bool:
    lowered = question.casefold()
    tokens = _search_tokens(question)
    has_first = bool(tokens.intersection(MEMORY_ANSWER_FIRST_APPEARANCE_FIRST_TERMS)) or any(
        term in lowered for term in MEMORY_ANSWER_FIRST_APPEARANCE_FIRST_TERMS
    )
    has_appearance = bool(tokens.intersection(MEMORY_ANSWER_FIRST_APPEARANCE_APPEAR_TERMS)) or any(
        term in lowered for term in MEMORY_ANSWER_FIRST_APPEARANCE_APPEAR_TERMS
    )
    return has_first and has_appearance


def _memory_answer_first_appearance_target_entity_ids(
    session: Session,
    input_data: MemoryAnswerInput,
) -> list[UUID]:
    query_tokens = _meaningful_search_tokens(input_data.question)
    question = input_data.question.casefold()
    target_ids: list[UUID] = []
    for entity in session.query(StoryCanonicalEntity).filter_by(project_id=input_data.project_id):
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        if _text_matches_query(entity.display_name, query_tokens, question):
            target_ids.append(entity.id)

    for alias in session.query(StoryAliasRecord).filter_by(project_id=input_data.project_id):
        if alias.entity_id is None or alias.status in {"rejected"}:
            continue
        if _text_matches_query(alias.alias_text, query_tokens, question):
            target_ids.append(alias.entity_id)

    if not target_ids:
        matching_mentions: list[UUID] = []
        for entity_id, raw_text in (
            session.query(StoryMention.resolved_entity_id)
            .add_columns(StoryMention.raw_text)
            .join(SourceSpan, StoryMention.span_id == SourceSpan.id)
            .join(RawSource, SourceSpan.source_id == RawSource.id)
            .filter(RawSource.project_id == input_data.project_id)
            .filter(StoryMention.resolved_entity_id.isnot(None))
            .distinct()
        ):
            if entity_id is not None and _text_matches_query(raw_text, query_tokens, question):
                matching_mentions.append(entity_id)
        target_ids.extend(matching_mentions)

    return _unique_uuid_sequence(target_ids)


def _first_appearance_sort_key(appearance: FirstAppearance) -> tuple[int, int, int, int, str]:
    mention, span, _entity, chapter, scene = appearance
    chapter_index = chapter.chapter_index if chapter is not None else 1_000_000
    scene_index = scene.scene_index if scene is not None else 1_000_000
    return (chapter_index, scene_index, span.start_offset, span.raw_start_offset, str(mention.id))


def _first_appearance_entity_ref(entity: StoryCanonicalEntity) -> dict[str, object]:
    return _memory_answer_entity_ref(entity)


def _format_first_appearance_answer(
    mention: StoryMention,
    span: SourceSpan,
    entity: StoryCanonicalEntity,
    chapter: StoryChapter | None,
    scene: StoryScene | None,
) -> str:
    location = _first_appearance_location_label(span, chapter, scene)
    preview = span.text_preview.strip()
    if preview:
        return f"{entity.display_name} first appears in {location}: {preview}"
    return f"{entity.display_name} first appears in {location} as `{mention.raw_text}`."


def _first_appearance_location_label(
    span: SourceSpan,
    chapter: StoryChapter | None,
    scene: StoryScene | None,
) -> str:
    if chapter is not None and scene is not None:
        return f"Chapter {chapter.chapter_index + 1} / Scene {scene.scene_index + 1}"
    if chapter is not None:
        return f"Chapter {chapter.chapter_index + 1}"
    if scene is not None:
        return f"Scene {scene.scene_index + 1}"
    return f"source offsets {span.start_offset}-{span.end_offset}"


def _bounded_confidence(value: object) -> float:
    try:
        confidence = float(cast(Any, value))
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _memory_answer_input_with_effective_pov(
    session: Session, input_data: MemoryAnswerInput
) -> MemoryAnswerInput:
    if input_data.current_pov_character_id is not None or input_data.current_scene_id is None:
        return input_data

    scene = session.get(StoryScene, input_data.current_scene_id)
    if (
        scene is None
        or scene.pov_character_id is None
        or not _story_scene_belongs_to_project(session, scene, input_data.project_id)
    ):
        return input_data

    pov_character = session.get(StoryCanonicalEntity, scene.pov_character_id)
    if (
        pov_character is None
        or pov_character.project_id != input_data.project_id
        or pov_character.entity_type != "character"
        or pov_character.canonical_status in {"discarded", "contradicted"}
    ):
        return input_data

    return replace(input_data, current_pov_character_id=scene.pov_character_id)


def _infer_memory_answer_facts(
    session: Session,
    input_data: MemoryAnswerInput,
    *,
    embedding_client: EmbeddingClient | None = None,
) -> list[FactAssertionRecord] | None:
    facts = session.query(FactAssertionRecord).filter_by(project_id=input_data.project_id).all()
    if not facts:
        return None

    predicate = _infer_memory_answer_predicate(input_data.question)
    ref_keys = _memory_answer_ref_keys(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        facts=facts,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    semantic_recall = _memory_answer_semantic_recall_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        embedding_client=embedding_client,
    )
    semantic_source_span_ids: set[str] = set()
    if semantic_recall is not None:
        semantic_source_span_ids = _memory_answer_primary_semantic_source_span_ids(semantic_recall)
        if not semantic_source_span_ids:
            ref_keys.update(semantic_recall.ref_keys)

    if predicate is None and not ref_keys and not semantic_source_span_ids:
        return None

    inferred = facts
    if predicate is not None:
        inferred = [fact for fact in inferred if fact.predicate == predicate]
    if ref_keys or semantic_source_span_ids:
        inferred = [
            fact
            for fact in inferred
            if (
                semantic_source_span_ids
                and semantic_source_span_ids.intersection(
                    str(span_id) for span_id in fact.evidence_span_ids
                )
            )
            or (
                ref_keys.intersection(_ref_semantic_keys(fact.subject_ref))
                or ref_keys.intersection(_ref_semantic_keys(fact.object_ref))
            )
        ]
    return inferred


def _memory_answer_primary_semantic_source_span_ids(
    semantic_recall: SemanticRecallResult,
) -> set[str]:
    source_matches = list(_memory_answer_semantic_source_span_scores(semantic_recall).items())
    if not source_matches:
        return set()

    best_score = max(score for _span_id, score in source_matches)
    cutoff = best_score * 0.9
    return {span_id for span_id, score in source_matches if score >= cutoff}


def _memory_answer_semantic_source_span_scores(
    semantic_recall: SemanticRecallResult,
) -> dict[str, float]:
    span_scores: dict[str, float] = {}
    for match in semantic_recall.matches:
        if match.get("target_type") != "source_span":
            continue
        score = match.get("score")
        target_id = match.get("target_id")
        if not isinstance(score, (int, float)) or target_id is None:
            continue
        span_id = str(target_id)
        span_scores[span_id] = max(float(score), span_scores.get(span_id, 0.0))
    return span_scores


def _memory_answer_semantic_fact_clarification_refs(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
    *,
    embedding_client: EmbeddingClient | None,
) -> list[dict[str, object]]:
    if input_data.subject_ref is not None or input_data.predicate is not None:
        return []
    if _infer_memory_answer_predicate(input_data.question) is not None:
        return []

    semantic_recall = _memory_answer_semantic_recall_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        embedding_client=embedding_client,
    )
    if semantic_recall is None:
        return []

    semantic_source_span_ids = _memory_answer_primary_semantic_source_span_ids(semantic_recall)
    if not semantic_source_span_ids:
        return []

    semantic_facts = [
        fact
        for fact in facts
        if semantic_source_span_ids.intersection(str(span_id) for span_id in fact.evidence_span_ids)
    ]
    return _unique_fact_subject_refs(semantic_facts) if len(semantic_facts) > 1 else []


def _unique_fact_subject_refs(facts: list[FactAssertionRecord]) -> list[dict[str, object]]:
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for fact in facts:
        copied = dict(fact.subject_ref)
        key = json.dumps(copied, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(copied)
    return result if len(result) > 1 else []


def _format_semantic_fact_clarification_answer(
    subject_refs: list[dict[str, object]],
) -> str:
    candidates = ", ".join(_ref_label(ref) for ref in subject_refs)
    return (
        "Multiple SourceSpan-backed memory targets match this question: "
        f"{candidates}. Name one target or ask a narrower question."
    )


def _infer_memory_answer_predicate(question: str) -> str | None:
    tokens = _search_tokens(question)
    for predicate, terms in MEMORY_ANSWER_PREDICATE_TERMS.items():
        if tokens.intersection(terms):
            return predicate
    for predicate in MEMORY_ANSWER_PREDICATE_TERMS:
        if predicate in tokens:
            return predicate
    return None


def _memory_answer_ref_keys(
    session: Session,
    *,
    project_id: UUID,
    question: str,
    facts: list[FactAssertionRecord],
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> set[str]:
    query_tokens = _meaningful_search_tokens(question)
    if not query_tokens:
        return set()

    explicit_entity_ids = _memory_answer_explicit_entity_ids(
        session,
        project_id=project_id,
        question=question,
    )
    ref_keys: set[str] = set()
    for entity in session.query(StoryCanonicalEntity).filter_by(project_id=project_id).all():
        if _text_matches_query(entity.display_name, query_tokens, question):
            ref_keys.add(str(entity.id).casefold())
        if _entity_description_matches_query(entity, query_tokens):
            ref_keys.add(str(entity.id).casefold())

    aliases_by_surface: dict[str, list[tuple[StoryAliasRecord, StoryCanonicalEntity]]] = {}
    for alias in session.query(StoryAliasRecord).filter_by(project_id=project_id).all():
        if alias.entity_id is None or alias.status == "rejected":
            continue
        if not _text_matches_query(alias.alias_text, query_tokens, question):
            continue
        entity = session.get(StoryCanonicalEntity, alias.entity_id)
        if entity is None or entity.project_id != project_id:
            continue
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        aliases_by_surface.setdefault(alias.alias_text.strip().casefold(), []).append(
            (alias, entity)
        )

    for alias_rows in aliases_by_surface.values():
        entity_ids = {entity.id for _alias, entity in alias_rows}
        if explicit_entity_ids:
            entity_ids = entity_ids.intersection(explicit_entity_ids)
        elif len(entity_ids) > 1:
            scoped_entity_ids = _memory_answer_scoped_alias_context_entity_ids_from_rows(
                session,
                project_id=project_id,
                alias_rows=alias_rows,
                question=question,
                current_scene_id=current_scene_id,
                current_pov_character_id=current_pov_character_id,
            )
            if len(scoped_entity_ids) == 1:
                entity_ids = scoped_entity_ids
            else:
                continue
        for entity_id in entity_ids:
            ref_keys.add(str(entity_id).casefold())

    for page in session.query(MemoryPage).filter_by(project_id=project_id).all():
        page_payload = {
            "title": page.title,
            "target_ref": page.target_ref,
            "open_threads": page.open_threads,
            "current_canon": page.current_canon,
            "relationships": page.relationships,
            "contradictions": page.contradictions,
        }
        if _text_matches_query(page_payload, query_tokens, question):
            ref_keys.update(_ref_semantic_keys(page.target_ref))

    for fact in facts:
        for ref in (fact.subject_ref, fact.object_ref):
            if _text_matches_query(ref, query_tokens, question):
                ref_keys.update(_ref_semantic_keys(ref))
    return ref_keys


def _memory_answer_scoped_alias_context_entity_ids(
    session: Session,
    *,
    project_id: UUID,
    surface: str,
    question: str,
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> set[UUID]:
    alias_rows: list[tuple[StoryAliasRecord, StoryCanonicalEntity]] = []
    for alias in session.query(StoryAliasRecord).filter_by(project_id=project_id).all():
        if alias.entity_id is None or alias.status == "rejected":
            continue
        if alias.alias_text.strip().casefold() != surface.strip().casefold():
            continue
        entity = session.get(StoryCanonicalEntity, alias.entity_id)
        if entity is None or entity.project_id != project_id:
            continue
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        alias_rows.append((alias, entity))
    return _memory_answer_scoped_alias_context_entity_ids_from_rows(
        session,
        project_id=project_id,
        alias_rows=alias_rows,
        question=question,
        current_scene_id=current_scene_id,
        current_pov_character_id=current_pov_character_id,
    )


def _memory_answer_scoped_alias_context_entity_ids_from_rows(
    session: Session,
    *,
    project_id: UUID,
    alias_rows: list[tuple[StoryAliasRecord, StoryCanonicalEntity]],
    question: str,
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> set[UUID]:
    query_tokens = _meaningful_search_tokens(question)
    if not query_tokens:
        return set()

    scored: list[tuple[int, UUID]] = []
    for alias, entity in alias_rows:
        score = _memory_answer_scoped_alias_context_score(
            session,
            project_id=project_id,
            alias=alias,
            query_tokens=query_tokens,
            current_scene_id=current_scene_id,
            current_pov_character_id=current_pov_character_id,
        )
        if score > 0:
            scored.append((score, entity.id))
    if not scored:
        return set()

    best_score = max(score for score, _entity_id in scored)
    best_entity_ids = {entity_id for score, entity_id in scored if score == best_score}
    return best_entity_ids if len(best_entity_ids) == 1 else set()


def _memory_answer_scoped_alias_context_score(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    query_tokens: set[str],
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> int:
    if alias.scope not in MEMORY_ANSWER_LOCAL_ALIAS_SCOPES:
        return 0

    score = 0
    if current_scene_id is not None:
        score += _memory_answer_alias_scene_context_overlap(
            session,
            project_id=project_id,
            alias=alias,
            current_scene_id=current_scene_id,
        )
    if alias.scope == "character_specific" and current_pov_character_id is not None:
        score += _memory_answer_alias_pov_context_overlap(
            session,
            project_id=project_id,
            alias=alias,
            current_pov_character_id=current_pov_character_id,
        )
    focus_tokens = query_tokens - _search_tokens(alias.alias_text)
    if focus_tokens:
        score += _memory_answer_alias_evidence_context_overlap(
            session,
            project_id=project_id,
            alias=alias,
            focus_tokens=focus_tokens,
        )
    return score


def _memory_answer_alias_evidence_context_overlap(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    focus_tokens: set[str],
) -> int:
    overlap = 0
    for span_id in alias.evidence_span_ids:
        parsed_span_id = _uuid_or_none(span_id)
        if parsed_span_id is None:
            continue
        span = session.get(SourceSpan, parsed_span_id)
        if span is None:
            continue
        source = session.get(RawSource, span.source_id)
        if source is None or source.project_id != project_id:
            continue
        payload: dict[str, object] = {
            "text_preview": span.text_preview,
            "narration_layer": span.narration_layer,
        }
        if span.chapter_id is not None:
            chapter = session.get(StoryChapter, span.chapter_id)
            if chapter is not None:
                payload["chapter"] = {
                    "title": chapter.title,
                    "summary": chapter.summary,
                    "chapter_index": chapter.chapter_index,
                }
        if span.scene_id is not None:
            scene = session.get(StoryScene, span.scene_id)
            if scene is not None:
                payload["scene"] = {
                    "scene_index": scene.scene_index,
                    "story_time": scene.story_time,
                    "emotional_tone": scene.emotional_tone,
                    "scene_function": scene.scene_function,
                }
        overlap += len(_meaningful_search_tokens(payload).intersection(focus_tokens))
    return overlap


def _memory_answer_alias_scene_context_overlap(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    current_scene_id: UUID,
) -> int:
    current_scene = session.get(StoryScene, current_scene_id)
    if current_scene is None or not _story_scene_belongs_to_project(
        session, current_scene, project_id
    ):
        return 0
    current_scene_key = _story_scene_position_key(session, current_scene)
    boundary_score = _memory_answer_disguise_arc_boundary_score(
        session,
        project_id=project_id,
        alias=alias,
        current_scene_key=current_scene_key,
    )
    if boundary_score is not None:
        return boundary_score

    overlap = 0
    disguise_arc_keys: list[tuple[int, int, int, str]] = []
    for span_id in alias.evidence_span_ids:
        parsed_span_id = _uuid_or_none(span_id)
        if parsed_span_id is None:
            continue
        span = session.get(SourceSpan, parsed_span_id)
        if span is None:
            continue
        source = session.get(RawSource, span.source_id)
        if source is None or source.project_id != project_id:
            continue
        if alias.scope == "scene_local" and span.scene_id == current_scene.id:
            overlap += 4
            continue
        if alias.scope == "chapter_local":
            span_chapter_id = span.chapter_id
            if span_chapter_id is None and span.scene_id is not None:
                span_scene = session.get(StoryScene, span.scene_id)
                span_chapter_id = span_scene.chapter_id if span_scene is not None else None
            if span_chapter_id is not None and span_chapter_id == current_scene.chapter_id:
                overlap += 2
            continue
        if alias.scope != "disguise_arc" or span.scene_id is None:
            continue
        span_scene = session.get(StoryScene, span.scene_id)
        if span_scene is None:
            continue
        span_scene_key = _story_scene_position_key(session, span_scene)
        if span_scene_key is None:
            continue
        disguise_arc_keys.append(span_scene_key)
        if span.scene_id == current_scene.id:
            overlap += 4
    if alias.scope == "disguise_arc" and current_scene_key is not None:
        distinct_arc_keys = sorted(set(disguise_arc_keys))
        if (
            len(distinct_arc_keys) >= 2
            and distinct_arc_keys[0] <= current_scene_key <= distinct_arc_keys[-1]
        ):
            overlap += 3
    return overlap


def _memory_answer_disguise_arc_boundary_score(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    current_scene_key: tuple[int, int, int, str] | None,
) -> int | None:
    if alias.scope != "disguise_arc":
        return None
    if alias.valid_from_scene_id is None and alias.valid_until_scene_id is None:
        return None
    if current_scene_key is None:
        return 0

    start_key = _memory_answer_alias_boundary_scene_key(
        session, project_id, alias.valid_from_scene_id
    )
    end_key = _memory_answer_alias_boundary_scene_key(
        session, project_id, alias.valid_until_scene_id
    )
    if alias.valid_from_scene_id is not None and start_key is None:
        return 0
    if alias.valid_until_scene_id is not None and end_key is None:
        return 0
    if start_key is not None and end_key is not None and start_key > end_key:
        return 0
    if start_key is not None and current_scene_key < start_key:
        return 0
    if end_key is not None and current_scene_key > end_key:
        return 0
    return 5


def _memory_answer_alias_boundary_scene_key(
    session: Session,
    project_id: UUID,
    scene_id: UUID | None,
) -> tuple[int, int, int, str] | None:
    if scene_id is None:
        return None
    scene = session.get(StoryScene, scene_id)
    if scene is None or not _story_scene_belongs_to_project(session, scene, project_id):
        return None
    return _story_scene_position_key(session, scene)


def _story_scene_belongs_to_project(session: Session, scene: StoryScene, project_id: UUID) -> bool:
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return False
    view = session.get(SourceProcessedView, chapter.view_id)
    if view is None:
        return False
    version = session.get(SourceVersion, view.version_id)
    if version is None:
        return False
    source = session.get(RawSource, version.source_id)
    return source is not None and source.project_id == project_id


def _story_scene_position_key(
    session: Session, scene: StoryScene
) -> tuple[int, int, int, str] | None:
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return None
    return (chapter.chapter_index, scene.scene_index, scene.start_offset, str(scene.id))


def _memory_answer_alias_pov_context_overlap(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    current_pov_character_id: UUID,
) -> int:
    overlap = 0
    for span_id in alias.evidence_span_ids:
        parsed_span_id = _uuid_or_none(span_id)
        if parsed_span_id is None:
            continue
        span = session.get(SourceSpan, parsed_span_id)
        if span is None or span.scene_id is None:
            continue
        source = session.get(RawSource, span.source_id)
        if source is None or source.project_id != project_id:
            continue
        if span.speaker_entity_id == current_pov_character_id:
            overlap += 1
            continue
        scene = session.get(StoryScene, span.scene_id)
        if scene is not None and scene.pov_character_id == current_pov_character_id:
            overlap += 1
    return overlap


def _memory_answer_scoped_alias_context_caveats(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
) -> list[str]:
    if not facts:
        return []
    matched_entity_ids = _memory_answer_scoped_alias_context_entity_ids_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    if not matched_entity_ids:
        return []
    for fact in facts:
        for ref in (fact.subject_ref, fact.object_ref):
            ref_ids = _ref_semantic_keys(ref)
            if any(str(entity_id).casefold() in ref_ids for entity_id in matched_entity_ids):
                return [MEMORY_ANSWER_SCOPED_ALIAS_CONTEXT_CAVEAT]
    return []


def _memory_answer_scoped_alias_confidence_cap(
    session: Session,
    input_data: MemoryAnswerInput,
    facts: list[FactAssertionRecord],
) -> float | None:
    if not facts:
        return None

    matched_entity_ids = _memory_answer_scoped_alias_context_entity_ids_for_question(
        session,
        project_id=input_data.project_id,
        question=input_data.question,
        current_scene_id=input_data.current_scene_id,
        current_pov_character_id=input_data.current_pov_character_id,
    )
    if not matched_entity_ids:
        return None

    fact_ref_keys = {
        key
        for fact in facts
        for ref in (fact.subject_ref, fact.object_ref)
        for key in _ref_semantic_keys(ref)
    }
    matched_entity_ids = {
        entity_id for entity_id in matched_entity_ids if str(entity_id).casefold() in fact_ref_keys
    }
    if not matched_entity_ids:
        return None

    query_tokens = _meaningful_search_tokens(input_data.question)
    confidence_by_entity_id: dict[UUID, float] = {}
    for alias in session.query(StoryAliasRecord).filter_by(project_id=input_data.project_id).all():
        if (
            alias.entity_id is None
            or alias.status == "rejected"
            or alias.entity_id not in matched_entity_ids
            or not _text_matches_query(alias.alias_text, query_tokens, input_data.question)
        ):
            continue
        score = _memory_answer_scoped_alias_context_score(
            session,
            project_id=input_data.project_id,
            alias=alias,
            query_tokens=query_tokens,
            current_scene_id=input_data.current_scene_id,
            current_pov_character_id=input_data.current_pov_character_id,
        )
        if score <= 0:
            continue
        confidence = _bounded_confidence(alias.confidence)
        current_confidence = confidence_by_entity_id.get(alias.entity_id)
        confidence_by_entity_id[alias.entity_id] = (
            confidence if current_confidence is None else max(current_confidence, confidence)
        )

    if not confidence_by_entity_id:
        return None
    return min(confidence_by_entity_id.values())


def _memory_answer_scoped_alias_context_entity_ids_for_question(
    session: Session,
    *,
    project_id: UUID,
    question: str,
    current_scene_id: UUID | None,
    current_pov_character_id: UUID | None,
) -> set[UUID]:
    query_tokens = _meaningful_search_tokens(question)
    aliases_by_surface: dict[str, list[tuple[StoryAliasRecord, StoryCanonicalEntity]]] = {}
    for alias in session.query(StoryAliasRecord).filter_by(project_id=project_id).all():
        if alias.entity_id is None or alias.status == "rejected":
            continue
        if not _text_matches_query(alias.alias_text, query_tokens, question):
            continue
        entity = session.get(StoryCanonicalEntity, alias.entity_id)
        if entity is None or entity.project_id != project_id:
            continue
        if entity.canonical_status in {"discarded", "contradicted"}:
            continue
        aliases_by_surface.setdefault(alias.alias_text.strip().casefold(), []).append(
            (alias, entity)
        )

    matched: set[UUID] = set()
    for alias_rows in aliases_by_surface.values():
        if len({entity.id for _alias, entity in alias_rows}) < 2:
            continue
        scoped_entity_ids = _memory_answer_scoped_alias_context_entity_ids_from_rows(
            session,
            project_id=project_id,
            alias_rows=alias_rows,
            question=question,
            current_scene_id=current_scene_id,
            current_pov_character_id=current_pov_character_id,
        )
        if len(scoped_entity_ids) == 1:
            matched.update(scoped_entity_ids)
    return matched


def _entity_description_matches_query(
    entity: StoryCanonicalEntity,
    query_tokens: set[str],
) -> bool:
    return bool(_entity_description_query_overlap(entity, query_tokens))


def _entity_description_query_surface(
    entity: StoryCanonicalEntity,
    query_tokens: set[str],
    question_text: str,
) -> str | None:
    overlap = _entity_description_query_overlap(entity, query_tokens)
    if not overlap:
        return None
    return " ".join(
        sorted(
            overlap,
            key=lambda token: (
                question_text.find(token) if question_text.find(token) >= 0 else 1_000_000,
                token,
            ),
        )
    )


def _entity_description_query_overlap(
    entity: StoryCanonicalEntity,
    query_tokens: set[str],
) -> set[str]:
    if not query_tokens or not entity.description:
        return set()
    overlap = _meaningful_search_tokens(entity.description).intersection(query_tokens)
    if len(overlap) < 2:
        return set()
    return overlap


def _text_matches_query(
    value: object,
    query_tokens: set[str],
    question: str,
) -> bool:
    if not query_tokens:
        return False
    value_tokens = _meaningful_search_tokens(value)
    if value_tokens.intersection(query_tokens):
        return True
    if isinstance(value, str):
        value_text = value.strip().casefold()
        return bool(value_text) and value_text in question.casefold()
    return False


def _search_tokens(value: object) -> set[str]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).casefold()
    tokens = {token for token in re.findall(r"[a-z0-9][a-z0-9'-]{2,}", text)}
    tokens.update(token for token in re.findall(r"[\u4e00-\u9fff·]{2,}", text))
    return tokens


def _meaningful_search_tokens(value: object) -> set[str]:
    return {token for token in _search_tokens(value) if token not in MEMORY_ANSWER_QUERY_STOPWORDS}


def _payload_matches_query(payload: object, scope: dict[str, Any]) -> bool:
    return _payload_query_overlap(payload, scope) > 0


def _payload_query_overlap(payload: object, scope: dict[str, Any]) -> int:
    query_tokens = cast(set[str], scope["query_tokens"])
    if not query_tokens:
        return 0
    payload_tokens = _search_tokens(payload)
    return len(query_tokens & payload_tokens)


def _fact_matches_semantic_recall(
    fact: FactAssertionRecord,
    scope: dict[str, Any],
) -> bool:
    semantic_recall = cast(dict[str, object], scope.get("semantic_recall", {}))
    ref_keys = cast(set[str], semantic_recall.get("ref_keys", set()))
    source_span_ids = cast(set[str], semantic_recall.get("source_span_ids", set()))
    return bool(
        ref_keys.intersection(_ref_semantic_keys(fact.subject_ref))
        or ref_keys.intersection(_ref_semantic_keys(fact.object_ref))
        or source_span_ids.intersection(str(span_id) for span_id in fact.evidence_span_ids)
    )


def _semantic_fact_relevance_points(
    fact: FactAssertionRecord,
    scope: dict[str, Any],
) -> int:
    semantic_recall = cast(dict[str, object], scope.get("semantic_recall", {}))
    ref_key_scores = cast(dict[str, float], semantic_recall.get("ref_key_scores", {}))
    source_span_scores = cast(dict[str, float], semantic_recall.get("source_span_scores", {}))
    best_score = 0.0
    for ref_key in _ref_semantic_keys(fact.subject_ref) | _ref_semantic_keys(fact.object_ref):
        best_score = max(best_score, float(ref_key_scores.get(ref_key, 0.0)))
    for span_id in fact.evidence_span_ids:
        best_score = max(best_score, float(source_span_scores.get(str(span_id), 0.0)))
    return _semantic_recall_points(best_score)


def _semantic_span_relevance_points(
    span_id: str,
    scope: dict[str, Any],
    *,
    include_style_samples: bool = False,
) -> int:
    semantic_recall = cast(dict[str, object], scope.get("semantic_recall", {}))
    source_span_scores = cast(dict[str, float], semantic_recall.get("source_span_scores", {}))
    style_sample_scores = cast(
        dict[str, float],
        semantic_recall.get("style_sample_source_span_scores", {}),
    )
    best_score = float(source_span_scores.get(span_id, 0.0))
    if include_style_samples:
        best_score = max(best_score, float(style_sample_scores.get(span_id, 0.0)))
    return _semantic_recall_points(best_score)


def _semantic_recall_points(score: float) -> int:
    if score <= 0:
        return 35
    return min(35, max(1, int(round(score * SEMANTIC_RRF_SCORE_SCALE))))


def _span_matches_semantic_recall(
    span_id: str,
    scope: dict[str, Any],
    *,
    include_style_samples: bool = False,
) -> bool:
    semantic_recall = cast(dict[str, object], scope.get("semantic_recall", {}))
    source_span_ids = cast(set[str], semantic_recall.get("source_span_ids", set()))
    if span_id in source_span_ids:
        return True
    if not include_style_samples:
        return False
    style_sample_source_span_ids = cast(
        set[str],
        semantic_recall.get("style_sample_source_span_ids", set()),
    )
    return span_id in style_sample_source_span_ids


def _ref_semantic_keys(ref: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for key in ("id", "canonical_entity_id"):
        value = ref.get(key)
        if value is not None:
            keys.add(str(value).casefold())
    return keys


def _fact_has_evidence_in_scene(
    fact: FactAssertionRecord,
    scene_id: str,
    scope: dict[str, Any],
) -> bool:
    return any(
        span.scene_id is not None and str(span.scene_id) == scene_id
        for span in _evidence_spans(fact.evidence_span_ids, scope)
    )


def _fact_has_evidence_in_source(fact: FactAssertionRecord, scope: dict[str, Any]) -> bool:
    return _span_ids_have_source([str(span_id) for span_id in fact.evidence_span_ids], scope)


def _fact_has_evidence_in_version(fact: FactAssertionRecord, scope: dict[str, Any]) -> bool:
    return _span_ids_have_version([str(span_id) for span_id in fact.evidence_span_ids], scope)


def _evidence_spans(span_ids: list[str], scope: dict[str, Any]) -> list[SourceSpan]:
    source_spans_by_id = cast(dict[str, SourceSpan], scope["source_spans_by_id"])
    return [
        source_spans_by_id[str(span_id)]
        for span_id in span_ids
        if str(span_id) in source_spans_by_id
    ]


def _span_ids_have_scene(span_ids: list[str] | set[str], scope: dict[str, Any]) -> bool:
    current_scene_id = cast(str | None, scope.get("current_scene_id"))
    if current_scene_id is None:
        return False
    return any(
        span.scene_id is not None and str(span.scene_id) == current_scene_id
        for span in _evidence_spans([str(span_id) for span_id in span_ids], scope)
    )


def _span_ids_have_source(span_ids: list[str] | set[str], scope: dict[str, Any]) -> bool:
    current_source_id = cast(str | None, scope.get("current_source_id"))
    if current_source_id is None:
        return False
    return any(
        str(span.source_id) == current_source_id
        for span in _evidence_spans([str(span_id) for span_id in span_ids], scope)
    )


def _span_ids_have_version(span_ids: list[str] | set[str], scope: dict[str, Any]) -> bool:
    current_version_id = cast(str | None, scope.get("current_version_id"))
    if current_version_id is None:
        return False
    return any(
        str(span.version_id) == current_version_id
        for span in _evidence_spans([str(span_id) for span_id in span_ids], scope)
    )


def _fact_references_any(
    fact: FactAssertionRecord,
    refs: list[dict[str, object]],
) -> bool:
    return any(
        _same_ref(fact.subject_ref, ref)
        or _same_ref(fact.object_ref, ref)
        or _ref_matches_id(fact.subject_ref, str(ref.get("id")))
        or _ref_matches_id(fact.object_ref, str(ref.get("id")))
        for ref in refs
    )


def _ref_matches_id(ref: dict[str, object], expected_id: str) -> bool:
    candidates = {
        str(ref.get("id", "")),
        str(ref.get("canonical_entity_id", "")),
        str(ref.get("scene_id", "")),
        str(ref.get("source_span_id", "")),
    }
    return expected_id in candidates


def _job_detail(job: JobRecord) -> JobDetailOutput:
    return JobDetailOutput(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        attempt_count=job.attempt_count,
        run_after=job.run_after,
        locked_by=job.locked_by,
        locked_at=job.locked_at,
        last_error=job.last_error,
        payload=job.payload,
    )


def _review_detail(session: Session, review: ReviewItemRecord) -> ReviewItemDetailOutput | None:
    source_span_ids = [str(span_id) for span_id in _review_context_source_span_ids(session, review)]
    if not source_span_ids:
        return None
    return ReviewItemDetailOutput(
        id=review.id,
        review_type=review.review_type,
        severity=review.severity,
        status=review.status,
        summary=review.summary,
        affected_refs=review.affected_refs,
        new_evidence=_review_evidence_entry(review.new_evidence, source_span_ids),
        existing_evidence=_review_evidence_entry(review.existing_evidence, source_span_ids),
        suggested_actions=review.suggested_actions,
        default_action=review.default_action,
        resolution=review.resolution,
        side_effects=review.side_effects,
    )


def _canonical_entity_summary(entity: StoryCanonicalEntity) -> CanonicalEntitySummaryOutput:
    return CanonicalEntitySummaryOutput(
        id=entity.id,
        entity_type=entity.entity_type,
        display_name=entity.display_name,
        canonical_status=entity.canonical_status,
        cast_tier=entity.cast_tier,
        first_seen_scene_id=entity.first_seen_scene_id,
    )


def _story_scene_summary(
    scene: StoryScene,
    chapter: StoryChapter,
    version: SourceVersion,
    source: RawSource,
) -> StorySceneSummaryOutput:
    return StorySceneSummaryOutput(
        id=scene.id,
        source_id=source.id,
        version_id=version.id,
        chapter_id=chapter.id,
        chapter_index=chapter.chapter_index,
        chapter_title=chapter.title,
        scene_index=scene.scene_index,
        position_label=f"Chapter {chapter.chapter_index + 1} / Scene {scene.scene_index + 1}",
        story_time=scene.story_time,
        scene_summary=scene.scene_summary,
        pov_character_id=scene.pov_character_id,
        pov_mode=scene.pov_mode,
    )


def _active_project_story_schema_binding(
    session: Session, project_id: UUID
) -> ProjectStorySchemaBinding | None:
    return session.scalars(
        select(ProjectStorySchemaBinding)
        .where(ProjectStorySchemaBinding.project_id == project_id)
        .where(ProjectStorySchemaBinding.status == "active")
        .order_by(ProjectStorySchemaBinding.created_at.desc(), ProjectStorySchemaBinding.id.desc())
    ).first()


def _get_or_create_base_story_schema_pack(session: Session) -> StorySchemaPackRecord:
    snapshot = default_base_story_schema_pack()
    existing = session.scalars(
        select(StorySchemaPackRecord)
        .where(StorySchemaPackRecord.project_id.is_(None))
        .where(StorySchemaPackRecord.pack_type == snapshot.pack_type)
        .where(StorySchemaPackRecord.pack_name == snapshot.pack_name)
        .where(StorySchemaPackRecord.version == snapshot.version)
    ).first()
    if existing is not None:
        return existing
    record = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type=snapshot.pack_type,
        pack_name=snapshot.pack_name,
        version=snapshot.version,
        status=snapshot.status,
        entity_types=snapshot.entity_types,
        event_types=snapshot.event_types,
        relations=snapshot.relations,
        extraction_hints=snapshot.extraction_hints,
        risk_rules=snapshot.risk_rules,
    )
    session.add(record)
    session.flush()
    return record


def _project_story_schema_output(session: Session, project_id: UUID) -> ProjectStorySchemaOutput:
    binding = _active_project_story_schema_binding(session, project_id)
    if binding is None:
        effective_schema = build_effective_story_schema([default_base_story_schema_pack()])
        return ProjectStorySchemaOutput(
            project_id=project_id,
            binding_id=None,
            base_schema_pack_id=None,
            genre_schema_pack_id=None,
            genre_schema_pack=None,
            project_override_pack_id=None,
            project_override_pack=None,
            effective_schema=_effective_story_schema_payload(effective_schema),
        )

    pack_ids = [
        pack_id
        for pack_id in (
            binding.base_schema_pack_id,
            binding.genre_schema_pack_id,
            binding.project_override_pack_id,
        )
        if pack_id is not None
    ]
    packs_by_id = {
        pack.id: pack
        for pack in session.scalars(
            select(StorySchemaPackRecord).where(StorySchemaPackRecord.id.in_(pack_ids))
        )
    }
    snapshots: list[StorySchemaPackSnapshot] = []
    base_pack = packs_by_id.get(binding.base_schema_pack_id)
    snapshots.append(
        _story_schema_pack_snapshot(base_pack)
        if base_pack is not None
        else default_base_story_schema_pack()
    )
    genre_pack = None
    if binding.genre_schema_pack_id is not None:
        genre_pack = packs_by_id.get(binding.genre_schema_pack_id)
        if genre_pack is not None:
            snapshots.append(_story_schema_pack_snapshot(genre_pack))
    project_override_pack = None
    if binding.project_override_pack_id is not None:
        project_override_pack = packs_by_id.get(binding.project_override_pack_id)
        if project_override_pack is not None:
            snapshots.append(_story_schema_pack_snapshot(project_override_pack))

    return ProjectStorySchemaOutput(
        project_id=project_id,
        binding_id=binding.id,
        base_schema_pack_id=binding.base_schema_pack_id,
        genre_schema_pack_id=binding.genre_schema_pack_id,
        genre_schema_pack=_story_schema_pack_output(genre_pack) if genre_pack is not None else None,
        project_override_pack_id=binding.project_override_pack_id,
        project_override_pack=_story_schema_pack_output(project_override_pack)
        if project_override_pack is not None
        else None,
        effective_schema=_effective_story_schema_payload(build_effective_story_schema(snapshots)),
    )


def _story_schema_pack_snapshot(record: StorySchemaPackRecord) -> StorySchemaPackSnapshot:
    return StorySchemaPackSnapshot(
        pack_type=record.pack_type,
        pack_name=record.pack_name,
        version=record.version,
        status=record.status,
        entity_types=record.entity_types,
        event_types=record.event_types,
        relations=record.relations,
        extraction_hints=record.extraction_hints,
        risk_rules=record.risk_rules,
    )


def _story_schema_pack_output(record: StorySchemaPackRecord) -> StorySchemaPackOutput:
    return StorySchemaPackOutput(
        id=record.id,
        project_id=record.project_id,
        pack_type=record.pack_type,
        pack_name=record.pack_name,
        version=record.version,
        status=record.status,
        entity_types=record.entity_types,
        event_types=record.event_types,
        relations=record.relations,
        extraction_hints=record.extraction_hints,
        risk_rules=record.risk_rules,
    )


def _effective_story_schema_payload(schema: EffectiveStorySchema) -> dict[str, object]:
    return {
        "entity_types": sorted(schema.entity_types.values(), key=lambda item: str(item["name"])),
        "event_types": sorted(schema.event_types),
        "relations": sorted(schema.relations),
        "relation_roles": [
            {
                "relation": relation,
                "subject_types": sorted(subject_types),
                "object_types": sorted(object_types),
            }
            for relation, (subject_types, object_types) in sorted(schema.relation_roles.items())
        ],
        "weak_entity_types": sorted(schema.weak_entity_types),
        "source_pack_versions": list(schema.source_pack_versions),
        "extraction_hints": schema.extraction_hints,
    }


def _job_for_source_delta(
    session: Session, *, project_id: UUID, source_delta_id: UUID
) -> JobRecord | None:
    jobs = (
        session.query(JobRecord)
        .filter_by(project_id=project_id, job_type="run_memory_writeback")
        .order_by(JobRecord.created_at.desc(), JobRecord.id.desc())
        .all()
    )
    for job in jobs:
        if str(job.payload.get("source_delta_id")) == str(source_delta_id):
            return job
    return None


def _enqueue_source_delta_pipeline_jobs(
    session: Session,
    *,
    project_id: UUID,
    source_delta_id: UUID,
    source_version_id: UUID,
    source_type: str,
    trigger: str,
    memory_writeback_job_id: UUID | None = None,
) -> UUID:
    pipeline_version = "pipeline-v1"
    cleaning_profile = f"{source_type}_profile_v1"
    normalize_key = f"{source_version_id}:{cleaning_profile}:{pipeline_version}"
    if (
        session.query(JobRecord)
        .filter_by(
            project_id=project_id,
            job_type="normalize_source",
            idempotency_key=normalize_key,
        )
        .first()
        is None
    ):
        session.add(
            JobRecord(
                id=uuid4(),
                project_id=project_id,
                job_type="normalize_source",
                status="queued",
                idempotency_key=normalize_key,
                payload={
                    "source_version_id": str(source_version_id),
                    "cleaning_profile": cleaning_profile,
                    "pipeline_version": pipeline_version,
                    "step": "normalize_source",
                    "trigger": trigger,
                    "source_delta_id": str(source_delta_id),
                },
            )
        )

    writeback_id = memory_writeback_job_id or uuid4()
    session.add(
        JobRecord(
            id=writeback_id,
            project_id=project_id,
            job_type="run_memory_writeback",
            status="queued",
            idempotency_key=f"{source_delta_id}:memory_writeback:{pipeline_version}",
            payload={
                "source_delta_id": str(source_delta_id),
                "pipeline_version": pipeline_version,
                "step": "run_memory_writeback",
                "trigger": trigger,
            },
        )
    )
    return writeback_id


def _source_delta_snapshot(session: Session, delta: SourceDeltaRecord) -> SourceDeltaSnapshot:
    return SourceDeltaSnapshot(
        id=delta.id,
        project_id=delta.project_id,
        source_id=delta.source_id,
        previous_version_id=delta.previous_version_id,
        new_version_id=delta.new_version_id,
        accepted_fragment_id=delta.accepted_fragment_id,
        delta_kind=delta.delta_kind,
        status=delta.status,
        range_start=delta.range_start,
        range_end=delta.range_end,
        base_hash=delta.base_hash,
        source_type=delta.source_type,
        source_scope=delta.source_scope,
        provenance=delta.provenance,
        submitted_text_ref=delta.submitted_text_ref,
        created_at=delta.created_at,
        job=_job_detail(job)
        if (
            job := _job_for_source_delta(
                session, project_id=delta.project_id, source_delta_id=delta.id
            )
        )
        else None,
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _context_pack_output(record: AgentContextPackRecord) -> WritingContextPackOutput:
    payload = record.payload
    return WritingContextPackOutput(
        context_pack_id=record.id,
        schema_version=record.schema_version,
        current_position=dict(payload.get("current_position", {})),
        canonical_context=dict(payload.get("canonical_context", {})),
        pov_constraint=dict(payload.get("pov_constraint", {})),
        active_characters=list(payload.get("active_characters", [])),
        character_agency_state=dict(payload.get("character_agency_state", {})),
        recent_events=list(payload.get("recent_events", [])),
        character_knowledge=list(payload.get("character_knowledge", [])),
        object_location_state=list(payload.get("object_location_state", [])),
        open_threads=list(payload.get("open_threads", [])),
        risk_context=dict(payload.get("risk_context", {})),
        style_memory=dict(payload.get("style_memory", {})),
        evidence_refs=list(record.evidence_refs),
    )


def _source_span_ids_for_delta(
    session: Session, *, project_id: UUID, source_delta_id: UUID
) -> list[str]:
    audits = (
        session.query(AuditEvent)
        .filter_by(
            project_id=project_id,
            event_type="source.span_extracted",
        )
        .all()
    )
    return [
        str(audit.decision["source_span_id"])
        for audit in audits
        if audit.subject_ref == {"type": "source_delta", "id": str(source_delta_id)}
        and "source_span_id" in audit.decision
    ]


def _spans_for_ids(session: Session, span_ids: list[str]) -> list[SourceSpan]:
    if not span_ids:
        return []
    parsed_ids = [UUID(span_id) for span_id in span_ids]
    return session.query(SourceSpan).filter(SourceSpan.id.in_(parsed_ids)).all()


def _source_span_belongs_to_project(session: Session, span: SourceSpan, project_id: UUID) -> bool:
    source = session.get(RawSource, span.source_id)
    return source is not None and source.project_id == project_id


def _evidence_entries_for_spans(
    session: Session, *, project_id: UUID, span_ids: list[str]
) -> list[EvidenceLogEntry]:
    if not span_ids:
        return []
    span_id_set = set(span_ids)
    entries = session.query(EvidenceLogEntry).filter_by(project_id=project_id).all()
    return [
        entry
        for entry in entries
        if span_id_set.intersection(str(item) for item in entry.source_span_ids)
    ]


def _facts_for_spans(
    session: Session, *, project_id: UUID, span_ids: list[str]
) -> list[FactAssertionRecord]:
    if not span_ids:
        return []
    span_id_set = set(span_ids)
    facts = session.query(FactAssertionRecord).filter_by(project_id=project_id).all()
    return [
        fact
        for fact in facts
        if span_id_set.intersection(str(item) for item in fact.evidence_span_ids)
    ]


def _reviews_for_spans(
    session: Session, *, project_id: UUID, span_ids: list[str]
) -> list[ReviewItemRecord]:
    if not span_ids:
        return []
    span_id_set = set(span_ids)
    reviews = session.query(ReviewItemRecord).filter_by(project_id=project_id).all()
    return [
        review
        for review in reviews
        if span_id_set.intersection(
            str(item) for item in review.new_evidence.get("source_span_ids", [])
        )
    ]


def _upsert_fact_memory_page(
    session: Session,
    *,
    project_id: UUID,
    source_delta_id: UUID,
    fact: FactAssertionRecord,
) -> list[str]:
    evidence_span_ids = _valid_source_span_id_strings(
        session,
        project_id,
        [str(item) for item in fact.evidence_span_ids],
    )
    if evidence_span_ids != fact.evidence_span_ids:
        fact.evidence_span_ids = evidence_span_ids
    fact_entry = {
        "fact_id": str(fact.id),
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "evidence_span_ids": evidence_span_ids,
    }
    source_refs = _unique_refs(
        [{"type": "source_delta", "id": str(source_delta_id)}]
        + [{"type": "source_span", "id": span_id} for span_id in evidence_span_ids]
    )
    pages = session.query(MemoryPage).filter_by(project_id=project_id).all()
    for page in pages:
        if page.target_ref != fact.subject_ref:
            continue
        changed = False
        facts = list(page.current_canon.get("facts", []))
        replaced = False
        for index, entry in enumerate(facts):
            if str(entry.get("fact_id")) != str(fact.id):
                continue
            if entry != fact_entry:
                facts[index] = fact_entry
                page.current_canon = {"facts": facts}
                changed = True
            replaced = True
            break
        if not replaced:
            facts.append(fact_entry)
            page.current_canon = {"facts": facts}
            changed = True
        updated_source_refs = _unique_refs(
            _sanitized_memory_page_source_refs(session, project_id, page.source_refs) + source_refs
        )
        if updated_source_refs != page.source_refs:
            page.source_refs = updated_source_refs
            changed = True
        return [str(page.id)] if changed else []

    page_id = uuid4()
    session.add(
        MemoryPage(
            id=page_id,
            project_id=project_id,
            page_type=str(fact.subject_ref.get("type", "entity")),
            target_ref=fact.subject_ref,
            title=_ref_label(fact.subject_ref),
            current_canon={"facts": [fact_entry]},
            appearance_log=[],
            event_log=[],
            relationships=[],
            open_threads=[],
            contradictions=[],
            source_refs=source_refs,
            canon_status="current",
            memory_depth="scene",
        )
    )
    return [str(page_id)]


def _resolve_fact_review_items(
    session: Session,
    *,
    project_id: UUID,
    actor_id: UUID,
    fact: FactAssertionRecord,
    author_note: str | None,
    replacement_refs: list[dict[str, object]],
) -> list[str]:
    resolved_ids: list[str] = []
    reviews = session.query(ReviewItemRecord).filter_by(project_id=project_id, status="open").all()
    for review in reviews:
        if not _review_matches_fact(review, fact.id):
            continue
        review.status = "resolved"
        review.resolution = "accept"
        review.resolved_by = actor_id
        review.resolved_at = datetime.now(UTC)
        review.side_effects = {
            **dict(review.side_effects or {}),
            "policy_action": "fact_accept_promoted_canon",
            "fact_id": str(fact.id),
            "author_note": author_note,
            "replacement_refs": replacement_refs,
        }
        resolved_ids.append(str(review.id))
    return resolved_ids


def _review_matches_fact(review: ReviewItemRecord, fact_id: UUID) -> bool:
    refs = review.affected_refs
    fact_id_text = str(fact_id)
    if str(refs.get("fact_id")) == fact_id_text:
        return True
    return fact_id_text in {str(item) for item in refs.get("fact_ids", [])}


def _memory_pages_for_delta(
    session: Session, *, project_id: UUID, source_delta_id: UUID
) -> list[MemoryPage]:
    pages = session.query(MemoryPage).filter_by(project_id=project_id).all()
    return [
        page
        for page in pages
        if {"type": "source_delta", "id": str(source_delta_id)} in page.source_refs
    ]


def _graph_edges_for_spans(
    session: Session, *, project_id: UUID, span_ids: list[str]
) -> list[GraphProjectionEdge]:
    if not span_ids:
        return []
    span_id_set = set(span_ids)
    edges = session.query(GraphProjectionEdge).filter_by(project_id=project_id).all()
    return [
        edge
        for edge in edges
        if span_id_set.intersection(
            str(ref.get("id")) for ref in edge.evidence_refs if ref.get("type") == "source_span"
        )
    ]


def _alias_boundary_scene_refs_from_correction(
    correction: dict[str, object],
) -> dict[str, UUID | None]:
    refs: dict[str, UUID | None] = {}
    for key in ("valid_from_scene_id", "valid_until_scene_id"):
        if key not in correction:
            continue
        value = correction[key]
        refs[key] = None if value is None else UUID(str(value))
    return refs


def _uuid_values(refs: dict[str, object], single_key: str, list_key: str) -> set[UUID]:
    values: list[object] = []
    single_value = refs.get(single_key)
    if single_value is not None:
        values.append(single_value)
    list_value = refs.get(list_key)
    if isinstance(list_value, list):
        values.extend(list_value)

    parsed: set[UUID] = set()
    for value in values:
        try:
            parsed.add(UUID(str(value)))
        except ValueError:
            continue
    return parsed


def _review_source_span_ids(review_item: ReviewItemRecord) -> set[str]:
    span_ids: set[str] = set()
    for evidence in (review_item.new_evidence, review_item.existing_evidence):
        values = evidence.get("source_span_ids", [])
        if isinstance(values, list):
            span_ids.update(str(value) for value in values)
    return span_ids


def _validated_review_source_span_ids(
    session: Session,
    review_item: ReviewItemRecord,
) -> set[str]:
    return {
        str(span_id)
        for span_id in _source_span_ids_to_uuids(
            session,
            review_item.project_id,
            _review_source_span_ids(review_item),
        )
    }


def _review_matches_memory_page(
    page: MemoryPage,
    fact_ids: set[UUID],
    memory_page_ids: set[UUID],
    source_span_ids: set[str],
) -> bool:
    if page.id in memory_page_ids:
        return True
    if _memory_page_fact_ids(page).intersection(str(fact_id) for fact_id in fact_ids):
        return True
    return bool(_memory_page_source_span_ids(page).intersection(source_span_ids))


def _memory_page_fact_ids(page: MemoryPage) -> set[str]:
    facts = page.current_canon.get("facts", [])
    if not isinstance(facts, list):
        return set()
    return {
        str(entry.get("fact_id"))
        for entry in facts
        if isinstance(entry, dict) and entry.get("fact_id") is not None
    }


def _memory_page_source_span_ids(page: MemoryPage) -> set[str]:
    return {
        str(ref.get("id"))
        for ref in page.source_refs
        if ref.get("type") == "source_span" and ref.get("id") is not None
    }


def _is_memory_page_open_thread_correction(input_data: MemoryWritebackDecisionInput) -> bool:
    correction = input_data.correction or {}
    return (
        input_data.decision == "correct"
        and correction.get("action") == "needs_memory_update"
        and correction.get("target_section") == "open_threads"
    )


def _memory_page_open_thread_decision_entry(
    session: Session,
    page: MemoryPage,
    input_data: MemoryWritebackDecisionInput,
) -> dict[str, object]:
    correction = input_data.correction or {}
    raw_source_span_ids = _memory_page_context_source_span_ids(session, page).union(
        _source_span_ids_for_delta(
            session,
            project_id=page.project_id,
            source_delta_id=input_data.source_delta_id,
        )
    )
    source_span_ids = [
        str(span_id)
        for span_id in _source_span_ids_to_uuids(session, page.project_id, raw_source_span_ids)
    ]
    description = (
        correction.get("description")
        or correction.get("open_thread")
        or input_data.author_note
        or "Memory page needs an author-reviewed open-thread update."
    )
    return {
        "type": "memory_writeback_decision",
        "thread_type": "needs_memory_update",
        "source_delta_id": str(input_data.source_delta_id),
        "item_ref": input_data.item_ref,
        "decision": input_data.decision,
        "target_section": "open_threads",
        "description": str(description),
        "author_note": input_data.author_note,
        "source_span_ids": source_span_ids,
        "status": "open",
        "requires": "memory_page_rewrite",
    }


def _has_review_contradiction(page: MemoryPage, review_item_id: UUID) -> bool:
    return any(
        entry.get("type") == "review_item_resolution"
        and entry.get("review_item_id") == str(review_item_id)
        for entry in page.contradictions
        if isinstance(entry, dict)
    )


def _review_matches_graph_edge(
    edge: GraphProjectionEdge,
    fact_ids: set[UUID],
    source_span_ids: set[str],
) -> bool:
    if edge.source_ref.get("type") == "fact_assertion" and edge.source_ref.get("id") in {
        str(fact_id) for fact_id in fact_ids
    }:
        return True
    edge_span_ids = {
        str(ref.get("id"))
        for ref in edge.evidence_refs
        if ref.get("type") == "source_span" and ref.get("id") is not None
    }
    return bool(edge_span_ids.intersection(source_span_ids))


def _source_span_entry(span: SourceSpan) -> dict[str, object]:
    return {
        "id": str(span.id),
        "source_id": str(span.source_id),
        "version_id": str(span.version_id),
        "view_id": str(span.view_id),
        "chapter_id": str(span.chapter_id) if span.chapter_id else None,
        "scene_id": str(span.scene_id) if span.scene_id else None,
        "start_offset": span.start_offset,
        "end_offset": span.end_offset,
        "raw_start_offset": span.raw_start_offset,
        "raw_end_offset": span.raw_end_offset,
        "text_preview": span.text_preview,
        "speaker_entity_id": str(span.speaker_entity_id) if span.speaker_entity_id else None,
        "narration_layer": span.narration_layer,
    }


def _evidence_entry(entry: EvidenceLogEntry) -> dict[str, object]:
    return {
        "id": str(entry.id),
        "log_type": entry.log_type,
        "target_ref": entry.target_ref,
        "fact_id": str(entry.fact_id) if entry.fact_id else None,
        "event_id": str(entry.event_id) if entry.event_id else None,
        "source_span_ids": [str(item) for item in entry.source_span_ids],
        "log_status": entry.log_status,
    }


def _memory_page_entry(session: Session, page: MemoryPage) -> dict[str, object]:
    return {
        "id": str(page.id),
        "page_type": page.page_type,
        "target_ref": page.target_ref,
        "title": page.title,
        "current_canon": page.current_canon,
        "open_threads": page.open_threads,
        "contradictions": page.contradictions,
        "source_refs": _sanitized_memory_page_source_refs(
            session,
            page.project_id,
            page.source_refs,
        ),
        "canon_status": page.canon_status,
        "memory_depth": page.memory_depth,
    }


def _memory_page_summary(session: Session, page: MemoryPage) -> MemoryPageSummaryOutput:
    return MemoryPageSummaryOutput(
        id=page.id,
        page_type=page.page_type,
        target_ref=page.target_ref,
        title=page.title,
        canon_status=page.canon_status,
        memory_depth=page.memory_depth,
        source_refs=_sanitized_memory_page_source_refs(
            session,
            page.project_id,
            page.source_refs,
        ),
        open_thread_count=len(page.open_threads),
        contradiction_count=len(page.contradictions),
    )


def _memory_page_detail(session: Session, page: MemoryPage) -> MemoryPageDetailOutput:
    return MemoryPageDetailOutput(
        id=page.id,
        page_type=page.page_type,
        target_ref=page.target_ref,
        title=page.title,
        current_canon=page.current_canon,
        appearance_log=page.appearance_log,
        event_log=page.event_log,
        relationships=page.relationships,
        knowledge_state=_memory_page_knowledge_state(session, page),
        open_threads=page.open_threads,
        contradictions=page.contradictions,
        source_refs=_sanitized_memory_page_source_refs(
            session,
            page.project_id,
            page.source_refs,
        ),
        canon_status=page.canon_status,
        memory_depth=page.memory_depth,
    )


def _memory_page_knowledge_state(session: Session, page: MemoryPage) -> list[dict[str, object]]:
    if page.page_type != "character":
        return []
    character_ids = _memory_page_character_ids(session, page)
    if not character_ids:
        return []
    rows = (
        session.query(CharacterKnowledge)
        .filter(CharacterKnowledge.project_id == page.project_id)
        .filter(CharacterKnowledge.status == "active")
        .filter(CharacterKnowledge.character_id.in_(character_ids))
        .order_by(CharacterKnowledge.created_at, CharacterKnowledge.id)
        .all()
    )
    valid_span_ids = set(
        _valid_source_span_id_strings(
            session,
            page.project_id,
            (row.evidence_span_id for row in rows),
        )
    )
    return [
        _character_knowledge_entry(row)
        for row in rows
        if str(row.evidence_span_id) in valid_span_ids
    ]


def _memory_page_character_ids(session: Session, page: MemoryPage) -> list[UUID]:
    parsed_ids: list[UUID] = []
    for key in ("canonical_entity_id", "entity_id", "id"):
        parsed = _uuid_or_none(page.target_ref.get(key))
        if parsed is not None:
            parsed_ids.append(parsed)

    labels = {
        value.strip()
        for value in (
            page.target_ref.get("label"),
            page.target_ref.get("display_name"),
            page.title,
        )
        if isinstance(value, str) and value.strip()
    }
    for label in sorted(labels):
        matching_entities = (
            session.query(StoryCanonicalEntity)
            .filter_by(
                project_id=page.project_id,
                entity_type="character",
                display_name=label,
            )
            .order_by(StoryCanonicalEntity.id)
            .limit(2)
            .all()
        )
        if len(matching_entities) == 1:
            parsed_ids.append(matching_entities[0].id)

    seen: set[UUID] = set()
    result: list[UUID] = []
    for character_id in parsed_ids:
        if character_id in seen:
            continue
        seen.add(character_id)
        result.append(character_id)
    return result


def _graph_projection_edge_summary(
    session: Session,
    project_id: UUID,
    edge: GraphProjectionEdge,
) -> GraphProjectionEdgeSummaryOutput | None:
    evidence_refs = _valid_source_span_refs(session, project_id, edge.evidence_refs)
    if not evidence_refs:
        return None
    return GraphProjectionEdgeSummaryOutput(
        id=edge.id,
        run_id=edge.run_id,
        source_ref=edge.source_ref,
        subject_ref=edge.subject_ref,
        relation=edge.relation,
        target_ref=edge.target_ref,
        edge_status=edge.edge_status,
        evidence_refs=evidence_refs,
        created_at=edge.created_at,
    )


def _graph_edge_entry(
    session: Session,
    project_id: UUID,
    edge: GraphProjectionEdge,
) -> dict[str, object] | None:
    evidence_refs = _valid_source_span_refs(session, project_id, edge.evidence_refs)
    if not evidence_refs:
        return None
    return {
        "id": str(edge.id),
        "run_id": str(edge.run_id),
        "source_ref": edge.source_ref,
        "subject_ref": edge.subject_ref,
        "relation": edge.relation,
        "target_ref": edge.target_ref,
        "edge_status": edge.edge_status,
        "evidence_refs": evidence_refs,
    }


def _agent_review_finding_record(
    finding_id: UUID,
    candidate_id: UUID,
    finding: AgentReviewFindingDraft,
    input_data: PersistActionRequestRunInput,
) -> AgentReviewFindingRecord:
    return AgentReviewFindingRecord(
        id=finding_id,
        project_id=input_data.project_id,
        action_request_id=input_data.action_request_id,
        draft_candidate_id=candidate_id,
        risk_level=finding.risk_level,
        risk_type=finding.risk_type,
        summary=finding.summary,
        affected_text_ref=finding.affected_text_ref,
        memory_refs=finding.memory_refs,
        storytelling_refs=finding.storytelling_refs,
        suggested_revision=finding.suggested_revision,
        can_offer_to_author=finding.can_offer_to_author,
        maps_to_review_type_if_accepted=finding.maps_to_review_type_if_accepted,
        draft_local_only=True,
    )


def _beat_candidate_snapshot(
    session: Session,
    project_id: UUID,
    beat: AgentBeatCandidateRecord,
) -> BeatCandidateSnapshot:
    return BeatCandidateSnapshot(
        id=beat.id,
        summary=beat.summary,
        driver_character=beat.driver_character,
        agency_rationale=beat.agency_rationale,
        storytelling_rationale=beat.storytelling_rationale,
        cast_decision=beat.cast_decision,
        tension=beat.tension,
        memory_refs=_sanitized_agent_memory_refs(session, project_id, beat.memory_refs),
        evidence_refs=_valid_source_span_refs(session, project_id, beat.evidence_refs),
        agent_review_findings=[],
    )


def _agent_review_finding_snapshot(
    session: Session,
    project_id: UUID,
    finding: AgentReviewFindingRecord,
) -> AgentReviewFindingSnapshot:
    return AgentReviewFindingSnapshot(
        id=finding.id,
        risk_level=finding.risk_level,
        risk_type=finding.risk_type,
        summary=finding.summary,
        memory_refs=cast(
            dict[str, object],
            _sanitized_agent_ref_payload(session, project_id, finding.memory_refs) or {},
        ),
        storytelling_refs=cast(
            dict[str, object],
            _sanitized_agent_ref_payload(session, project_id, finding.storytelling_refs) or {},
        ),
        suggested_revision=finding.suggested_revision,
        can_offer_to_author=finding.can_offer_to_author,
        maps_to_review_type_if_accepted=finding.maps_to_review_type_if_accepted,
        draft_local_only=finding.draft_local_only,
    )
