from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON as SA_JSON,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid

from sextant.domain.review import AGENT_RISK_LEVELS, AGENT_RISK_TYPES, REVIEW_TYPE_VALUES
from sextant.domain.story_schema import (
    BASE_ENTITY_TYPES,
    BASE_RELATIONS,
    PROJECT_SCHEMA_BINDING_STATUSES,
    STORY_SCHEMA_PACK_STATUSES,
    STORY_SCHEMA_PACK_TYPES,
)

JSON = SA_JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def sql_values(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


PROJECT_MEMBERSHIP_ROLES = ("owner", "editor", "viewer")
PROJECT_MEMBERSHIP_STATUSES = ("active", "revoked")
PROJECT_INVITATION_STATUSES = (
    "pending_external_delivery",
    "external_delivery_recorded",
    "cancelled",
)
PROJECT_INVITATION_DELIVERY_STATUSES = ("not_sent", "sent", "failed")
PROJECT_INVITATION_TOKEN_STATUSES = ("not_issued", "issued", "failed")


class ProjectMembership(Base, TimestampMixin):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "actor_id", name="uq_project_memberships_actor"),
        CheckConstraint(
            f"role in ({sql_values(PROJECT_MEMBERSHIP_ROLES)})",
            name="ck_project_memberships_role",
        ),
        CheckConstraint(
            f"status in ({sql_values(PROJECT_MEMBERSHIP_STATUSES)})",
            name="ck_project_memberships_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class ProjectInvitation(Base, TimestampMixin):
    __tablename__ = "project_invitations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "member_actor_id",
            "status",
            name="uq_project_invitations_active_actor",
        ),
        CheckConstraint(
            f"role in ({sql_values(PROJECT_MEMBERSHIP_ROLES)})",
            name="ck_project_invitations_role",
        ),
        CheckConstraint(
            f"status in ({sql_values(PROJECT_INVITATION_STATUSES)})",
            name="ck_project_invitations_status",
        ),
        CheckConstraint(
            f"delivery_status in ({sql_values(PROJECT_INVITATION_DELIVERY_STATUSES)})",
            name="ck_project_invitations_delivery_status",
        ),
        CheckConstraint(
            f"token_status in ({sql_values(PROJECT_INVITATION_TOKEN_STATUSES)})",
            name="ck_project_invitations_token_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    member_actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    delivery_provider_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    delivery_target_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    token_issuer_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    delivery_proof_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    token_proof_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(40), nullable=False)
    token_status: Mapped[str] = mapped_column(String(40), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class StorySchemaPackRecord(Base, TimestampMixin):
    __tablename__ = "story_schema_packs"
    __table_args__ = (
        Index(
            "uq_story_schema_packs_global_version",
            "pack_type",
            "pack_name",
            "version",
            unique=True,
            sqlite_where=text("project_id is null"),
            postgresql_where=text("project_id is null"),
        ),
        Index(
            "uq_story_schema_packs_project_version",
            "project_id",
            "pack_type",
            "pack_name",
            "version",
            unique=True,
            sqlite_where=text("project_id is not null"),
            postgresql_where=text("project_id is not null"),
        ),
        CheckConstraint(
            f"pack_type in ({sql_values(STORY_SCHEMA_PACK_TYPES)})",
            name="ck_story_schema_packs_type",
        ),
        CheckConstraint(
            f"status in ({sql_values(STORY_SCHEMA_PACK_STATUSES)})",
            name="ck_story_schema_packs_status",
        ),
        CheckConstraint(
            "((pack_type = 'project_override' and project_id is not null) or "
            "(pack_type in ('base', 'genre') and project_id is null))",
            name="ck_story_schema_packs_project_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True
    )
    pack_type: Mapped[str] = mapped_column(String(40), nullable=False)
    pack_name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_types: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    event_types: Mapped[list[dict[str, Any] | str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    relations: Mapped[list[dict[str, Any] | str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    extraction_hints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    risk_rules: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectStorySchemaBinding(Base, TimestampMixin):
    __tablename__ = "project_story_schema_bindings"
    __table_args__ = (
        Index(
            "uq_project_story_schema_bindings_active",
            "project_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint(
            f"status in ({sql_values(PROJECT_SCHEMA_BINDING_STATUSES)})",
            name="ck_project_story_schema_bindings_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    base_schema_pack_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_schema_packs.id"), nullable=False, index=True
    )
    genre_schema_pack_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_schema_packs.id"), nullable=True, index=True
    )
    project_override_pack_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_schema_packs.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IdempotencyRecord(Base, TimestampMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="uq_idempotency_records_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


SOURCE_TYPES = (
    "draft_manuscript",
    "canon_source",
    "web_serial",
    "pdf_book",
    "ocr_text",
    "author_notes",
    "outline",
    "character_sheet",
    "worldbuilding",
    "model_output",
    "other",
)
SOURCE_SCOPES = (
    "user_draft",
    "user_published",
    "external_canon",
    "author_note",
    "outline_plan",
    "reference_only",
    "discarded_draft",
    "experimental",
    "model_suggestion",
)
OWNERSHIP_STATUSES = ("owned", "authorized", "user_provided", "unknown")
VIEW_STATUSES = ("current", "stale", "rebuilt", "deprecated")
CONTEXT_PACK_READINESS_STATUSES = ("pending", "stale", "consumed")
CONTEXT_PACK_READINESS_REASONS = (
    "memory_dependency_changed",
    "review_dependency_changed",
)
SOURCE_DELTA_KINDS = ("insert", "replace", "delete")
SOURCE_DELTA_STATUSES = (
    "submitted",
    "source_version_created",
    "normalized",
    "span_extracted",
    "memory_writeback_queued",
    "memory_writeback_completed",
    "rejected_stale_base",
)
NARRATION_LAYERS = ("narrator", "dialogue", "inner_thought", "author_note")
SEVERITIES = ("low", "medium", "high")
REVIEW_TYPES = REVIEW_TYPE_VALUES
REVIEW_STATUSES = ("open", "dismissed", "resolved", "superseded")
REVIEW_RESOLUTIONS = (
    "accept",
    "reject",
    "split",
    "merge",
    "mark_intentional",
    "supersede",
    "needs_memory_update",
    "fixed_by_text_edit",
    "accepted_as_change",
)
FACT_STATUSES = (
    "proposed",
    "inferred",
    "canon",
    "disputed",
    "contradicted",
    "outdated",
    "user_note",
)
GRAPH_EDGE_STATUSES = (
    "canon",
    "proposed",
    "inferred",
    "disputed",
    "contradicted",
    "outdated",
    "discarded",
)
ALIAS_STATUSES = (
    "auto_accepted",
    "proposed",
    "low_confidence",
    "rejected",
    "user_confirmed",
    "user_corrected",
)
EVENT_CANDIDATE_STATUSES = (
    "new",
    "merged",
    "related",
    "conflict_version",
    "rejected",
)
CANONICAL_EVENT_STATUSES = (
    "proposed",
    "canon",
    "disputed",
    "deprecated",
    "external_canon",
    "author_note",
)
CANONICAL_ENTITY_TYPES = (
    *BASE_ENTITY_TYPES,
    "other",
)
CANONICAL_ENTITY_STATUSES = (
    "canon",
    "draft",
    "provisional",
    "discarded",
    "contradicted",
)
CAST_TIERS = (
    "local_extra",
    "minor_supporting",
    "recurring",
    "major",
    "unknown",
)
MEMORY_WRITEBACK_DECISIONS = ("accept", "reject", "correct")
CANONICAL_RELATIONS = BASE_RELATIONS
ACTION_REQUEST_STATUSES = ("submitted", "running", "succeeded", "failed", "cancelled")
BEAT_CANDIDATE_STATUSES = ("suggested", "selected", "dismissed", "archived")
DRAFT_CANDIDATE_STATUSES = (
    "generated",
    "reviewed",
    "offered_to_author",
    "accepted",
    "revised",
    "rejected",
    "blocked",
    "archived",
    "converted_to_source_delta",
)
STORYTELLING_CONTROL_TYPES = (
    "role_slot",
    "character_casting_decision",
    "new_character_seed",
    "scene_sequel_mode",
    "dramatic_behavior_plan",
    "prose_rendering_contract",
)
JOB_TYPES = (
    "normalize_source",
    "split_structure",
    "run_memory_writeback",
    "refresh_semantic_index",
    "extract_mentions",
    "resolve_aliases",
    "extract_events",
    "aggregate_events",
    "derive_facts",
    "run_conflict_policy",
    "rewrite_memory_page",
    "rebuild_graph_projection",
    "build_context_pack",
    "run_agent_candidate",
    "run_agent_review",
    "run_skill_replay_eval",
)
JOB_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed_retryable",
    "failed_terminal",
    "cancelled",
)


class RawSource(Base, TimestampMixin):
    __tablename__ = "source_raw_sources"
    __table_args__ = (
        CheckConstraint(
            f"source_type in ({sql_values(SOURCE_TYPES)})",
            name="ck_source_raw_sources_source_type",
        ),
        CheckConstraint(
            f"source_scope in ({sql_values(SOURCE_SCOPES)})",
            name="ck_source_raw_sources_source_scope",
        ),
        CheckConstraint(
            f"ownership_status in ({sql_values(OWNERSHIP_STATUSES)})",
            name="ck_source_raw_sources_ownership_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    ownership_status: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_text_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class SourceVersion(Base, TimestampMixin):
    __tablename__ = "source_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=False, index=True
    )
    version_label: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_text_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True
    )


class SourceProcessedView(Base, TimestampMixin):
    __tablename__ = "source_processed_views"
    __table_args__ = (
        CheckConstraint(
            f"view_status in ({sql_values(VIEW_STATUSES)})",
            name="ck_source_processed_views_status",
        ),
        Index(
            "uq_source_processed_views_current_version",
            "version_id",
            unique=True,
            sqlite_where=text("view_status = 'current'"),
            postgresql_where=text("view_status = 'current'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=False, index=True
    )
    cleaning_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    markdown_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_offset_map_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    view_status: Mapped[str] = mapped_column(String(40), nullable=False)


class SourceSpan(Base, TimestampMixin):
    __tablename__ = "source_spans"
    __table_args__ = (
        CheckConstraint("start_offset >= 0", name="ck_source_spans_start_non_negative"),
        CheckConstraint("end_offset > start_offset", name="ck_source_spans_range"),
        CheckConstraint("raw_start_offset >= 0", name="ck_source_spans_raw_start_non_negative"),
        CheckConstraint("raw_end_offset > raw_start_offset", name="ck_source_spans_raw_range"),
        CheckConstraint(
            f"narration_layer in ({sql_values(NARRATION_LAYERS)})",
            name="ck_source_spans_narration_layer",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=False, index=True
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=False, index=True
    )
    view_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_processed_views.id"), nullable=False, index=True
    )
    chapter_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    raw_start_offset: Mapped[int] = mapped_column(nullable=False)
    raw_end_offset: Mapped[int] = mapped_column(nullable=False)
    text_preview: Mapped[str] = mapped_column(String(500), nullable=False)
    speaker_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    narration_layer: Mapped[str] = mapped_column(String(40), nullable=False)


class AcceptedFragmentRecord(Base, TimestampMixin):
    __tablename__ = "source_accepted_fragments"
    __table_args__ = (
        CheckConstraint("range_start >= 0", name="ck_source_accepted_fragments_start"),
        CheckConstraint("range_end >= range_start", name="ck_source_accepted_fragments_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    candidate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    target_source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=False, index=True
    )
    target_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=False, index=True
    )
    accepted_text_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    range_start: Mapped[int] = mapped_column(nullable=False)
    range_end: Mapped[int] = mapped_column(nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    author_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class SourceDeltaRecord(Base, TimestampMixin):
    __tablename__ = "source_deltas"
    __table_args__ = (
        Index("ix_source_deltas_project_created_id", "project_id", "created_at", "id"),
        Index("ix_source_deltas_project_status_created", "project_id", "status", "created_at"),
        Index(
            "ix_source_deltas_search_trgm",
            "submitted_text_search",
            postgresql_using="gin",
            postgresql_ops={"submitted_text_search": "gin_trgm_ops"},
        ),
        CheckConstraint(
            f"delta_kind in ({sql_values(SOURCE_DELTA_KINDS)})",
            name="ck_source_deltas_kind",
        ),
        CheckConstraint(
            f"status in ({sql_values(SOURCE_DELTA_STATUSES)})",
            name="ck_source_deltas_status",
        ),
        CheckConstraint("range_start >= 0", name="ck_source_deltas_start"),
        CheckConstraint("range_end >= range_start", name="ck_source_deltas_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=False, index=True
    )
    previous_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True, index=True
    )
    new_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True, index=True
    )
    accepted_fragment_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_accepted_fragments.id"), nullable=True, index=True
    )
    delta_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    range_start: Mapped[int] = mapped_column(nullable=False)
    range_end: Mapped[int] = mapped_column(nullable=False)
    base_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitted_text_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    submitted_text_search: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)


class MemoryWritebackDecisionRecord(Base, TimestampMixin):
    __tablename__ = "memory_writeback_decisions"
    __table_args__ = (
        CheckConstraint(
            f"decision in ({sql_values(MEMORY_WRITEBACK_DECISIONS)})",
            name="ck_memory_writeback_decisions_decision",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_delta_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_deltas.id"), nullable=False, index=True
    )
    item_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    correction: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    replacement_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    author_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    side_effects: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    decided_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class StoryChapter(Base, TimestampMixin):
    __tablename__ = "story_chapters"
    __table_args__ = (
        UniqueConstraint("view_id", "chapter_index", name="uq_story_chapters_view_index"),
        CheckConstraint("chapter_index >= 0", name="ck_story_chapters_index"),
        CheckConstraint("end_offset > start_offset", name="ck_story_chapters_range"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    view_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_processed_views.id"), nullable=False, index=True
    )
    chapter_index: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class StoryScene(Base):
    __tablename__ = "story_scenes"
    __table_args__ = (
        UniqueConstraint("chapter_id", "scene_index", name="uq_story_scenes_chapter_index"),
        CheckConstraint("scene_index >= 0", name="ck_story_scenes_index"),
        CheckConstraint("end_offset > start_offset", name="ck_story_scenes_range"),
        CheckConstraint(
            "pov_confidence is null or (pov_confidence >= 0 and pov_confidence <= 1)",
            name="ck_story_scenes_pov_confidence_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    chapter_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_chapters.id"), nullable=False, index=True
    )
    scene_index: Mapped[int] = mapped_column(nullable=False)
    location_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    pov_character_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    pov_mode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pov_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    pov_evidence_span_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    pov_uncertainty_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    story_time: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emotional_tone: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scene_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    scene_function: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_offset: Mapped[int] = mapped_column(nullable=False)
    end_offset: Mapped[int] = mapped_column(nullable=False)


class StoryMention(Base, TimestampMixin):
    __tablename__ = "story_mentions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_spans.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(String(500), nullable=False)
    mention_type: Mapped[str] = mapped_column(String(80), nullable=False)
    local_context: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    resolved_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class StoryAliasRecord(Base, TimestampMixin):
    __tablename__ = "story_alias_records"
    __table_args__ = (
        CheckConstraint(
            f"status in ({sql_values(ALIAS_STATUSES)})",
            name="ck_story_alias_records_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    alias_text: Mapped[str] = mapped_column(String(500), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    alias_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
    scope: Mapped[str] = mapped_column(String(80), nullable=False)
    valid_from_scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    valid_until_scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    evidence_span_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class StoryCanonicalEntity(Base, TimestampMixin):
    __tablename__ = "story_canonical_entities"
    __table_args__ = (
        CheckConstraint(
            f"entity_type in ({sql_values(CANONICAL_ENTITY_TYPES)})",
            name="ck_story_canonical_entities_type",
        ),
        CheckConstraint(
            f"canonical_status in ({sql_values(CANONICAL_ENTITY_STATUSES)})",
            name="ck_story_canonical_entities_status",
        ),
        CheckConstraint(
            f"cast_tier is null or cast_tier in ({sql_values(CAST_TIERS)})",
            name="ck_story_canonical_entities_cast_tier",
        ),
        CheckConstraint(
            "entity_type = 'character' or cast_tier is null",
            name="ck_story_canonical_entities_cast_tier_character_only",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical_status: Mapped[str] = mapped_column(String(80), nullable=False)
    cast_tier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    first_seen_scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StoryEventCandidate(Base, TimestampMixin):
    __tablename__ = "story_event_candidates"
    __table_args__ = (
        CheckConstraint(
            f"aggregation_status in ({sql_values(EVENT_CANDIDATE_STATUSES)})",
            name="ck_story_event_candidates_aggregation_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    objects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    location_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    state_change: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_span_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    aggregation_status: Mapped[str] = mapped_column(String(80), nullable=False)


class StoryCanonicalEvent(Base, TimestampMixin):
    __tablename__ = "story_canonical_events"
    __table_args__ = (
        CheckConstraint(
            f"event_status in ({sql_values(CANONICAL_EVENT_STATUSES)})",
            name="ck_story_canonical_events_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    event_status: Mapped[str] = mapped_column(String(80), nullable=False)
    primary_scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    event_candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    participants: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    objects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    location_entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    story_time: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    cause_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    consequence_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    evidence_span_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FactAssertionRecord(Base, TimestampMixin):
    __tablename__ = "story_fact_assertions"
    __table_args__ = (
        CheckConstraint(
            f"fact_status in ({sql_values(FACT_STATUSES)})",
            name="ck_story_fact_assertions_status",
        ),
        CheckConstraint(
            "fact_status != 'canon' or promotion_decision_id is not null",
            name="ck_story_fact_assertions_canon_requires_promotion",
        ),
        CheckConstraint(
            "not (source_scope = 'model_suggestion' and fact_status = 'canon')",
            name="ck_story_fact_assertions_model_suggestion_not_canon",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    subject_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    predicate: Mapped[str] = mapped_column(String(120), nullable=False)
    object_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fact_status: Mapped[str] = mapped_column(String(40), nullable=False)
    valid_from_scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    valid_until_scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    evidence_span_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_scope: Mapped[str] = mapped_column(String(40), nullable=False)
    promotion_decision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EvidenceLogEntry(Base, TimestampMixin):
    __tablename__ = "memory_evidence_log_entries"
    __table_args__ = (
        CheckConstraint(
            "source_span_ids is not null",
            name="ck_memory_evidence_log_entries_source_spans",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    log_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    fact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_fact_assertions.id"), nullable=True
    )
    event_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_canonical_events.id"), nullable=True
    )
    source_span_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    log_status: Mapped[str] = mapped_column(String(80), nullable=False)


CHARACTER_KNOWLEDGE_CERTAINTIES = (
    "known",
    "suspected",
    "false_belief",
    "misunderstands",
    "does_not_know",
)
CHARACTER_KNOWLEDGE_STATUSES = ("active", "superseded")


class CharacterKnowledge(Base, TimestampMixin):
    __tablename__ = "memory_character_knowledge"
    __table_args__ = (
        CheckConstraint(
            f"certainty in ({sql_values(CHARACTER_KNOWLEDGE_CERTAINTIES)})",
            name="ck_memory_character_knowledge_certainty",
        ),
        CheckConstraint(
            f"status in ({sql_values(CHARACTER_KNOWLEDGE_STATUSES)})",
            name="ck_memory_character_knowledge_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    character_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    knows_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    learned_in_scene_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    evidence_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_spans.id"), nullable=False
    )
    certainty: Mapped[str] = mapped_column(String(80), nullable=False)
    hidden_from: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)


class MemoryPage(Base):
    __tablename__ = "memory_pages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    page_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    current_canon: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    appearance_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    event_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    relationships: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    open_threads: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    contradictions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    canon_status: Mapped[str] = mapped_column(String(80), nullable=False)
    memory_depth: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


SEMANTIC_EMBEDDING_TARGET_TYPES = (
    "memory_page",
    "source_span",
    "style_sample",
)


class SemanticEmbeddingRecord(Base):
    __tablename__ = "semantic_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "target_type",
            "target_id",
            "provider",
            "model_name",
            name="uq_semantic_embeddings_target_model",
        ),
        CheckConstraint(
            f"target_type in ({sql_values(SEMANTIC_EMBEDDING_TARGET_TYPES)})",
            name="ck_semantic_embeddings_target_type",
        ),
        CheckConstraint("dimensions > 0", name="ck_semantic_embeddings_dimensions_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    target_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GraphProjectionRun(Base, TimestampMixin):
    __tablename__ = "memory_graph_projection_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    projection_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    source_state_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_edge_count: Mapped[int] = mapped_column(Integer, nullable=False)


class GraphProjectionEdge(Base, TimestampMixin):
    __tablename__ = "memory_graph_projection_edges"
    __table_args__ = (
        CheckConstraint(
            f"edge_status in ({sql_values(GRAPH_EDGE_STATUSES)})",
            name="ck_memory_graph_projection_edges_status",
        ),
        UniqueConstraint(
            "project_id",
            "source_ref",
            "subject_ref",
            "relation",
            "target_ref",
            name="uq_memory_graph_projection_edges_identity",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memory_graph_projection_runs.id"), nullable=False
    )
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    subject_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    relation: Mapped[str] = mapped_column(String(100), nullable=False)
    target_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    edge_status: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)


class ReviewItemRecord(Base, TimestampMixin):
    __tablename__ = "review_items"
    __table_args__ = (
        CheckConstraint(
            f"review_type in ({sql_values(REVIEW_TYPES)})",
            name="ck_review_items_review_type",
        ),
        CheckConstraint(
            f"severity in ({sql_values(SEVERITIES)})",
            name="ck_review_items_severity",
        ),
        CheckConstraint(
            f"status in ({sql_values(REVIEW_STATUSES)})",
            name="ck_review_items_status",
        ),
        CheckConstraint(
            f"resolution is null or resolution in ({sql_values(REVIEW_RESOLUTIONS)})",
            name="ck_review_items_resolution",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    review_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    affected_refs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    new_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    existing_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    suggested_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    default_action: Mapped[str] = mapped_column(String(100), nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    side_effects: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentActionRequestRecord(Base, TimestampMixin):
    __tablename__ = "agent_action_requests"
    __table_args__ = (
        CheckConstraint(
            f"status in ({sql_values(ACTION_REQUEST_STATUSES)})",
            name="ck_agent_action_requests_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=True
    )
    source_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True
    )
    scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    chapter_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_chapters.id"), nullable=True
    )
    pov_character_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor_intent: Mapped[str] = mapped_column(String(4000), nullable=False)
    trigger: Mapped[str] = mapped_column(String(80), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expected_output: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class AgentContextPackRecord(Base, TimestampMixin):
    __tablename__ = "agent_context_packs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    action_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_action_requests.id"), nullable=True, index=True
    )
    current_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=True
    )
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True
    )
    current_scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    current_pov_character_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    mode: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class ContextPackReadinessRecord(Base, TimestampMixin):
    __tablename__ = "context_pack_readiness"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_span_id",
            "reason",
            name="uq_context_pack_readiness_span_reason",
        ),
        CheckConstraint(
            f"status in ({sql_values(CONTEXT_PACK_READINESS_STATUSES)})",
            name="ck_context_pack_readiness_status",
        ),
        CheckConstraint(
            f"reason in ({sql_values(CONTEXT_PACK_READINESS_REASONS)})",
            name="ck_context_pack_readiness_reason",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    source_span_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_spans.id"), nullable=False, index=True
    )
    source_delta_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_deltas.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    affected_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentDraftCandidateRecord(Base, TimestampMixin):
    __tablename__ = "agent_draft_candidates"
    __table_args__ = (
        CheckConstraint(
            f"status in ({sql_values(DRAFT_CANDIDATE_STATUSES)})",
            name="ck_agent_draft_candidates_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    action_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_action_requests.id"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_text_ref: Mapped[str] = mapped_column(String(1000), nullable=False)
    context_pack_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    selected_beat_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    target_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=True
    )
    target_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True
    )
    target_scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    affected_range: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    memory_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    author_action: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accepted_text_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentBeatCandidateRecord(Base, TimestampMixin):
    __tablename__ = "agent_beat_candidates"
    __table_args__ = (
        CheckConstraint(
            f"status in ({sql_values(BEAT_CANDIDATE_STATUSES)})",
            name="ck_agent_beat_candidates_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    action_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_action_requests.id"), nullable=False, index=True
    )
    context_pack_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    target_source_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_raw_sources.id"), nullable=True
    )
    target_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("source_versions.id"), nullable=True
    )
    target_scene_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("story_scenes.id"), nullable=True
    )
    affected_range: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    driver_character: Mapped[str] = mapped_column(String(400), nullable=False)
    agency_rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    storytelling_rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    cast_decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    tension: Mapped[str] = mapped_column(String(1000), nullable=False)
    memory_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentReviewFindingRecord(Base, TimestampMixin):
    __tablename__ = "agent_review_findings"
    __table_args__ = (
        CheckConstraint(
            f"risk_level in ({sql_values(AGENT_RISK_LEVELS)})",
            name="ck_agent_review_findings_level",
        ),
        CheckConstraint(
            f"risk_type in ({sql_values(AGENT_RISK_TYPES)})",
            name="ck_agent_review_findings_type",
        ),
        CheckConstraint(
            "maps_to_review_type_if_accepted is null or "
            f"maps_to_review_type_if_accepted in ({sql_values(REVIEW_TYPES)})",
            name="ck_agent_review_findings_review_mapping",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    action_request_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_action_requests.id"), nullable=False, index=True
    )
    draft_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    affected_text_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    memory_refs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    storytelling_refs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    suggested_revision: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    can_offer_to_author: Mapped[bool] = mapped_column(Boolean, nullable=False)
    maps_to_review_type_if_accepted: Mapped[str | None] = mapped_column(String(80), nullable=True)
    draft_local_only: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AgentStorytellingControlRecord(Base, TimestampMixin):
    __tablename__ = "agent_storytelling_controls"
    __table_args__ = (
        CheckConstraint(
            f"control_type in ({sql_values(STORYTELLING_CONTROL_TYPES)})",
            name="ck_agent_storytelling_controls_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    action_request_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_action_requests.id"), nullable=True
    )
    draft_candidate_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_draft_candidates.id"), nullable=True
    )
    control_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SkillRun(Base, TimestampMixin):
    __tablename__ = "skill_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('started', 'succeeded', 'failed_retryable', 'failed_terminal')",
            name="ck_skill_runs_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_output_ref: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_cents: Mapped[float | None] = mapped_column(Float, nullable=True)


class JobRecord(Base, TimestampMixin):
    __tablename__ = "job_records"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "job_type", "idempotency_key", name="uq_job_records_idempotency"
        ),
        CheckConstraint(
            f"status in ({sql_values(JOB_STATUSES)})",
            name="ck_job_records_status",
        ),
        CheckConstraint(
            f"job_type in ({sql_values(JOB_TYPES)})",
            name="ck_job_records_job_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base, TimestampMixin):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
