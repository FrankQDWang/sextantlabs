from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sextant.contracts.event_aggregation import (
    EventAggregationAdjudicationRequest,
    EventAggregationAdjudicationResult,
)
from sextant.contracts.pov_detection import (
    PovDetectionMention,
    PovDetectionRequest,
    PovDetectionResult,
)
from sextant.domain.fact_schema import validate_fact_against_story_schema
from sextant.domain.story import AliasRecord, AliasScope
from sextant.domain.story_schema import EffectiveStorySchema
from sextant.infra.context_readiness import mark_context_pack_readiness
from sextant.infra.db.models import (
    AuditEvent,
    EvidenceLogEntry,
    FactAssertionRecord,
    JobRecord,
    MemoryPage,
    RawSource,
    ReviewItemRecord,
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
from sextant.infra.fact_dedup import (
    evidence_log_exists,
    find_matching_fact,
    refs_equivalent,
)
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.story_schema import load_effective_story_schema
from sextant.infra.story_skill_registry import (
    STORY_SKILL_VERSION,
    StorySkillRuntimeContext,
    StorySkillValidationError,
    run_skill,
)
from sextant.infra.worker import TerminalJobError
from sextant.ports.event_aggregation import EventAggregationAdjudicationProvider
from sextant.ports.object_store import ObjectStore
from sextant.ports.pov_detection import PovDetectionProvider

STRUCTURED_FACT_DIRECTIVE_PATTERN = re.compile(
    r"^\s*FACT:\s*[^|\n]+\|[^|\n]+\|[^|\n]+", re.IGNORECASE
)
CHINESE_KNOWLEDGE_INTERPOSED_MARKERS = (
    "已经",
    "曾经",
    "早已",
    "继续",
    "正在",
    "仍然",
    "于是",
    "然后",
    "后来",
    "随后",
    "接着",
    "同时",
    "突然",
    "终于",
    "最终",
    "刚刚",
    "当即",
)
CHINESE_KNOWLEDGE_LEADING_DISCOURSE_MARKERS = (
    "这时",
    "此时",
    "那时",
    "随后",
    "接着",
    "然后",
    "后来",
    "于是",
    "同时",
    "突然",
    "终于",
    "最终",
    "刚刚",
    "当即",
    "之后",
    "过后",
    "稍后",
    "片刻后",
    "不久后",
)
EXPLICIT_POV_HINT_PATTERN = re.compile(
    r"^\s*(?:POV|视角|观点)\s*[:：]\s*"
    r"(?P<character>[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2}|"
    r"[\u4e00-\u9fff·]{2,8})\s*$",
    re.IGNORECASE,
)
EXPLICIT_LOCATION_HINT_PATTERN = re.compile(
    r"^\s*(?:Location|地点|场景地点)\s*[:：]\s*"
    r"(?P<location>[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,3}|"
    r"[\u4e00-\u9fffA-Za-z0-9·]{2,16})\s*$",
    re.IGNORECASE,
)
SCENE_FIELD_METADATA_PATTERN = re.compile(
    r"^\s*(?:Time|Story Time|时间|Tone|Emotional Tone|情绪|基调|"
    r"Function|Scene Function|场景功能|功能)\s*[:：].+$",
    re.IGNORECASE,
)
ENGLISH_SPEAKER_PRONOUNS = {"he", "she"}
CHINESE_SPEAKER_PRONOUNS = {"他", "她"}
CHINESE_INVALID_MENTION_VALUES = {
    "为了",
    *CHINESE_KNOWLEDGE_INTERPOSED_MARKERS,
    "当前",
    "眼前",
}
CHINESE_INVALID_MENTION_PREFIXES = (
    "的",
    "了",
    "着",
    "过",
    "已",
    "已经",
    "在",
    "把",
    "将",
    "被",
    "似乎",
    "没有",
    "并未",
    "并不",
    "并没",
    "尚未",
    "未能",
    "无法",
    "不能",
    "未",
)
CHINESE_INVALID_MENTION_SUFFIXES = CHINESE_KNOWLEDGE_INTERPOSED_MARKERS
CHINESE_PRONOUN_MENTION_PREFIXES = (
    "他",
    "她",
    "它",
    "我",
    "你",
    "咱",
    "这",
    "那",
)
ENGLISH_DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"\b(?P<speaker>[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2})\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)"
    r"\s*[,，:：]\s*[\"“‘]"
)
ENGLISH_POST_QUOTE_DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"[\"“‘][^\"”’]{1,240}[\"”’]\s*,?\s*"
    r"(?P<speaker>[A-Z][A-Za-z0-9'-]*(?:\s+[A-Z][A-Za-z0-9'-]*){0,2})\s+"
    r"(?i:said|says|asked|asks|whispered|replied|answered|shouted|warned|called|murmured)\b"
)
CHINESE_DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"(?P<speaker>[\u4e00-\u9fff·]{2,8}?|[他她])\s*"
    r"(?:低声说|回答|喊道|警告|提醒|说|问)\s*[,，:：]\s*[\"“‘]"
)
CHINESE_POST_QUOTE_DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"[\"“‘][^\"”’]{1,160}[\"”’]\s*[,，]?\s*"
    r"(?P<speaker>[\u4e00-\u9fff·]{2,8}?|[他她])\s*"
    r"(?:低声说|回答|喊道|警告|提醒|说|问)\s*[。！？!?]?"
)
PIPELINE_VERSION = "pipeline-v1"
ALIAS_RESOLVER_VERSION = "alias-resolver-v1"
EVENT_EXTRACTOR_VERSION = "event-extractor-v1"
EVENT_AGGREGATOR_VERSION = "event-aggregator-v1"
FACT_DERIVATION_VERSION = "fact-derivation-v1"
CONFLICT_POLICY_VERSION = "conflict-policy-v1"
POV_MODES = {"first_person", "third_limited", "omniscient", "multiple", "unknown"}
EXCLUSIVE_STATE_PREDICATES = {"located_in", "owns"}
AGENCY_PROFILE_FACT_PREDICATES = {
    "core_desire",
    "immediate_want",
    "fear_or_wound",
    "moral_boundary",
    "secret",
    "contradiction",
    "relationship_stance",
    "voice_fingerprint",
    "agency_rule",
    "change_pressure",
}
REVIEW_REQUIRED_SOURCE_SCOPES = {
    "model_suggestion",
    "reference_only",
    "discarded_draft",
    "experimental",
    "outline_plan",
}
AUTHOR_BACKED_CANON_SOURCE_SCOPES = {
    "user_draft",
    "user_published",
    "author_note",
}
AUTHOR_REPLACEABLE_LOW_AUTHORITY_SCOPES = set(REVIEW_REQUIRED_SOURCE_SCOPES)
CANONICAL_MENTION_ENTITY_TYPES = {
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
}


@dataclass(frozen=True, slots=True)
class MentionCandidate:
    text: str
    mention_type: str
    confidence: float
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class EventExtractionCandidate:
    event_type: str
    participants: list[dict[str, object]]
    objects: list[dict[str, object]]
    location_entity_id: UUID | None
    state_change: dict[str, object]
    confidence: float


class ExtractMentionsHandler:
    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        text = _span_text(session, self._object_store, span)
        story_text = _story_text_for_extraction(text)
        if _is_structured_memory_directive_text(story_text):
            _audit(
                session,
                job,
                "story.mentions_extracted",
                {
                    "source_span_id": str(span.id),
                    "created_count": 0,
                    "skipped": "memory_fact_directive",
                },
            )
            _enqueue_next_span_job(
                session,
                job,
                span,
                job_type="resolve_aliases",
                version_key="resolver_version",
                version=ALIAS_RESOLVER_VERSION,
            )
            session.flush()
            return
        created = 0
        seen_candidates: set[str] = set()
        for candidate in _scene_metadata_mention_candidates(text):
            if candidate.text in seen_candidates:
                continue
            seen_candidates.add(candidate.text)
            if _mention_exists(session, span.id, candidate.text):
                continue
            context_start = max(candidate.start_offset - 80, 0)
            context_end = min(candidate.end_offset + 80, len(story_text))
            session.add(
                StoryMention(
                    id=uuid4(),
                    span_id=span.id,
                    raw_text=candidate.text,
                    mention_type=candidate.mention_type,
                    local_context=story_text[context_start:context_end],
                    resolved_entity_id=None,
                    resolution_status="unresolved",
                    confidence=candidate.confidence,
                )
            )
            created += 1
        _audit(
            session,
            job,
            "story.mentions_extracted",
            {"source_span_id": str(span.id), "created_count": created},
        )
        _enqueue_next_span_job(
            session,
            job,
            span,
            job_type="resolve_aliases",
            version_key="resolver_version",
            version=ALIAS_RESOLVER_VERSION,
        )
        session.flush()


class ResolveAliasesHandler:
    def __init__(
        self,
        pov_detection_provider: PovDetectionProvider | None = None,
        object_store: ObjectStore | None = None,
    ) -> None:
        self._pov_detection_provider = pov_detection_provider
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        mentions = list(
            session.scalars(
                select(StoryMention)
                .where(StoryMention.span_id == span.id)
                .order_by(StoryMention.created_at, StoryMention.id)
            )
        )
        created = 0
        review_count = 0
        story_schema = load_effective_story_schema(session, job.project_id)
        for mention in mentions:
            existing_alias = _alias_for_text(session, job.project_id, mention.raw_text)
            entity = _canonical_entity_for_mention(
                session,
                project_id=job.project_id,
                mention=mention,
                span=span,
                story_schema=story_schema,
                entity_id=existing_alias.entity_id if existing_alias is not None else None,
            )
            mention.resolved_entity_id = entity.id
            if existing_alias is not None:
                if existing_alias.entity_id is None:
                    existing_alias.entity_id = entity.id
                span_ref = str(span.id)
                merged_span_ids = _source_span_ids_for_project(
                    session,
                    _merge_unique(
                        [str(span_id) for span_id in existing_alias.evidence_span_ids],
                        [span_ref],
                    ),
                    job.project_id,
                )
                if merged_span_ids != existing_alias.evidence_span_ids:
                    existing_alias.evidence_span_ids = merged_span_ids
                if _maybe_create_alias_conflict_review_item(
                    session,
                    project_id=job.project_id,
                    span=span,
                    mention=mention,
                    alias=existing_alias,
                    entity=entity,
                ):
                    mention.resolution_status = "alias_review_pending"
                    review_count += 1
                else:
                    mention.resolution_status = "alias_recorded"
                continue
            alias = AliasRecord.from_mention(
                project_id=job.project_id,
                alias_text=mention.raw_text,
                alias_type=_alias_type(mention),
                scope=_alias_scope(mention),
                evidence_span_ids=[span.id],
                confidence=mention.confidence,
                entity_id=entity.id,
            )
            alias_record = StoryAliasRecord(
                id=alias.id,
                project_id=job.project_id,
                alias_text=alias.alias_text,
                entity_id=alias.entity_id,
                alias_type=alias.alias_type,
                status=alias.status.value,
                scope=alias.scope.value,
                evidence_span_ids=[str(evidence_id) for evidence_id in alias.evidence_span_ids],
                confidence=alias.confidence,
            )
            session.add(alias_record)
            if _maybe_create_alias_conflict_review_item(
                session,
                project_id=job.project_id,
                span=span,
                mention=mention,
                alias=alias_record,
                entity=entity,
            ):
                mention.resolution_status = "alias_review_pending"
                review_count += 1
            else:
                mention.resolution_status = "alias_recorded"
            created += 1
        speaker_text = (
            _span_text(session, self._object_store, span)
            if self._object_store is not None
            else span.text_preview
        )
        pov_result = _apply_scene_pov_hint(session, span, mentions)
        pov_source = "rule_hint" if pov_result else None
        if pov_result is None:
            pov_result = _apply_scene_pov_model_judgment(
                session,
                span,
                mentions,
                self._pov_detection_provider,
            )
            pov_source = "model_assisted" if pov_result else None
        pov_mode = pov_result[1] if pov_result else None
        location_entity_id = _apply_scene_location(session, span, mentions)
        speaker_entity_id = _apply_span_speaker(
            session,
            span,
            mentions=mentions,
            text=speaker_text,
        )
        _audit(
            session,
            job,
            "story.aliases_resolved",
            {
                "source_span_id": str(span.id),
                "created_count": created,
                "review_count": review_count,
                "pov_character_id": str(pov_result[0])
                if pov_result and pov_result[0] is not None
                else None,
                "pov_mode": pov_mode,
                "pov_source": pov_source,
                "location_entity_id": str(location_entity_id) if location_entity_id else None,
                "speaker_entity_id": str(speaker_entity_id) if speaker_entity_id else None,
                "narration_layer": span.narration_layer,
            },
        )
        _enqueue_next_span_job(
            session,
            job,
            span,
            job_type="extract_events",
            version_key="extractor_version",
            version=EVENT_EXTRACTOR_VERSION,
        )
        session.flush()


class ExtractEventsHandler:
    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        if _event_candidate_exists_for_span(session, job.project_id, span.id):
            _audit(
                session,
                job,
                "story.events_extracted",
                {"source_span_id": str(span.id), "created_count": 0},
            )
            _enqueue_next_span_job(
                session,
                job,
                span,
                job_type="aggregate_events",
                version_key="aggregator_version",
                version=EVENT_AGGREGATOR_VERSION,
            )
            session.flush()
            return

        _audit(
            session,
            job,
            "story.events_extracted",
            {
                "source_span_id": str(span.id),
                "created_count": 0,
            },
        )
        _enqueue_next_span_job(
            session,
            job,
            span,
            job_type="aggregate_events",
            version_key="aggregator_version",
            version=EVENT_AGGREGATOR_VERSION,
        )
        session.flush()


class AggregateEventsHandler:
    def __init__(
        self,
        event_adjudication_provider: EventAggregationAdjudicationProvider | None = None,
    ) -> None:
        self._event_adjudication_provider = event_adjudication_provider

    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        candidates = [
            candidate
            for candidate in session.scalars(
                select(StoryEventCandidate)
                .where(StoryEventCandidate.project_id == job.project_id)
                .order_by(StoryEventCandidate.created_at, StoryEventCandidate.id)
            )
            if str(span.id) in candidate.evidence_span_ids
        ]
        created = 0
        merged = 0
        for candidate in candidates:
            decision = _canonical_event_decision_for_candidate(
                session,
                job,
                candidate,
                self._event_adjudication_provider,
            )
            canonical = decision.event if decision.merge else None
            dispute_existing_event = (
                decision.provider_decision == "conflict_version"
                and decision.policy_reason == "source_scope_conflict"
                and decision.dispute_existing_event
                and decision.event is not None
            )
            candidate_span_ids = _source_span_ids_for_project(
                session,
                [str(span_id) for span_id in candidate.evidence_span_ids],
                job.project_id,
            )
            if not candidate_span_ids:
                raise TerminalJobError("CanonicalEvent aggregation requires SourceSpan evidence.")
            if canonical is None:
                canonical = StoryCanonicalEvent(
                    id=uuid4(),
                    project_id=job.project_id,
                    event_type=candidate.event_type,
                    title=_event_title(candidate.summary),
                    event_status=(
                        "disputed"
                        if decision.provider_decision == "conflict_version"
                        and not dispute_existing_event
                        else "proposed"
                    ),
                    primary_scene_id=candidate.scene_id,
                    event_candidate_ids=[str(candidate.id)],
                    participants=candidate.participants,
                    objects=candidate.objects,
                    location_entity_id=candidate.location_entity_id,
                    story_time=None,
                    summary=candidate.summary,
                    cause_summary=_candidate_cause_summary(candidate),
                    consequence_summary=None,
                    evidence_span_ids=candidate_span_ids,
                )
                session.add(canonical)
                created += 1
            elif str(candidate.id) not in canonical.event_candidate_ids:
                canonical.event_candidate_ids = canonical.event_candidate_ids + [str(candidate.id)]
                existing_span_ids = _source_span_ids_for_project(
                    session,
                    [str(span_id) for span_id in canonical.evidence_span_ids],
                    job.project_id,
                )
                canonical.evidence_span_ids = _merge_unique(
                    existing_span_ids,
                    candidate_span_ids,
                )
                if canonical.cause_summary is None:
                    canonical.cause_summary = _candidate_cause_summary(candidate)
                merged += 1
            if decision.provider_decision == "conflict_version" and decision.event is not None:
                if dispute_existing_event:
                    decision.event.event_status = "disputed"
                    existing_event = canonical
                    disputed_event = decision.event
                else:
                    existing_event = decision.event
                    disputed_event = canonical
                _create_event_merge_conflict_review_item(
                    session,
                    existing_event=existing_event,
                    disputed_event=disputed_event,
                    policy_reason=decision.policy_reason,
                )
            if decision.provider_result is not None and decision.event is not None:
                _audit_event_adjudication(session, job, decision, candidate, canonical)
            if candidate.aggregation_status == "new":
                candidate.aggregation_status = _candidate_aggregation_status(decision)
        _audit(
            session,
            job,
            "story.events_aggregated",
            {
                "source_span_id": str(span.id),
                "created_count": created,
                "merged_count": merged,
            },
        )
        _enqueue_next_span_job(
            session,
            job,
            span,
            job_type="derive_facts",
            version_key="derivation_version",
            version=FACT_DERIVATION_VERSION,
        )
        session.flush()


class DeriveFactsHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        source_scope = _source_scope_for_span(session, span)
        story_schema = load_effective_story_schema(session, job.project_id)
        created = 0
        canonical_events = [
            event
            for event in session.scalars(
                select(StoryCanonicalEvent)
                .where(StoryCanonicalEvent.project_id == job.project_id)
                .where(StoryCanonicalEvent.event_status != "disputed")
                .order_by(StoryCanonicalEvent.created_at, StoryCanonicalEvent.id)
            )
            if str(span.id) in event.evidence_span_ids
        ]
        for event in canonical_events:
            event_ref: dict[str, object] = {
                "type": "event",
                "id": str(event.id),
                "label": event.title,
            }
            for participant in event.participants:
                created += _ensure_fact(
                    session,
                    job,
                    story_schema,
                    subject_ref=participant,
                    predicate="present_at",
                    object_ref=event_ref,
                    evidence_span_ids=event.evidence_span_ids,
                    source_scope=source_scope,
                    event_id=event.id,
                )
            for obj in event.objects:
                created += _ensure_fact(
                    session,
                    job,
                    story_schema,
                    subject_ref=event_ref,
                    predicate="involves_object",
                    object_ref=obj,
                    evidence_span_ids=event.evidence_span_ids,
                    source_scope=source_scope,
                    event_id=event.id,
                )
            owner_ref = _transfer_owner_ref(event)
            if owner_ref is not None:
                for obj in event.objects:
                    created += _ensure_fact(
                        session,
                        job,
                        story_schema,
                        subject_ref=owner_ref,
                        predicate="owns",
                        object_ref=obj,
                        evidence_span_ids=event.evidence_span_ids,
                        source_scope=source_scope,
                        event_id=event.id,
                    )
            location_ref = _location_ref_for_span(session, span)
            if location_ref is not None:
                created += _ensure_fact(
                    session,
                    job,
                    story_schema,
                    subject_ref=event_ref,
                    predicate="occurred_at",
                    object_ref=location_ref,
                    evidence_span_ids=event.evidence_span_ids,
                    source_scope=source_scope,
                    event_id=event.id,
                )
                if event.event_type == "travel":
                    for participant in event.participants:
                        created += _ensure_fact(
                            session,
                            job,
                            story_schema,
                            subject_ref=participant,
                            predicate="located_in",
                            object_ref=location_ref,
                            evidence_span_ids=event.evidence_span_ids,
                            source_scope=source_scope,
                            event_id=event.id,
                            valid_from_scene_id=span.scene_id,
                        )
        _audit(
            session,
            job,
            "story.facts_derived",
            {
                "source_span_id": str(span.id),
                "created_count": created,
            },
        )
        _enqueue_next_span_job(
            session,
            job,
            span,
            job_type="run_conflict_policy",
            version_key="policy_version",
            version=CONFLICT_POLICY_VERSION,
        )
        session.flush()


class RunConflictPolicyHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        span = _span_from_payload(session, job)
        facts = [
            fact
            for fact in session.scalars(
                select(FactAssertionRecord)
                .where(FactAssertionRecord.project_id == job.project_id)
                .where(FactAssertionRecord.fact_status == "proposed")
                .order_by(FactAssertionRecord.created_at, FactAssertionRecord.id)
            )
            if str(span.id) in fact.evidence_span_ids
        ]
        promoted = 0
        disputed = 0
        changed_fact_ids: list[UUID] = []
        for fact in facts:
            conflict = _find_conflicting_canon_fact(session, fact)
            source_scope_conflict = _find_source_scope_conflicting_fact(session, fact)
            if _author_fact_replaces_low_authority_duplicate(fact, source_scope_conflict):
                assert source_scope_conflict is not None
                source_scope_conflict.fact_status = "outdated"
                fact.fact_status = "canon"
                fact.promotion_decision_id = uuid4()
                page = _upsert_memory_page(session, job.project_id, fact)
                _queue_agency_profile_rewrite_if_needed(session, job, span, fact, page)
                superseded_review_ids = _supersede_low_authority_scope_reviews(
                    session,
                    replaced_fact=source_scope_conflict,
                    replacement_fact=fact,
                    replacement_span_id=span.id,
                )
                promoted += 1
                changed_fact_ids.extend([source_scope_conflict.id, fact.id])
                _audit(
                    session,
                    job,
                    "memory.conflict_policy",
                    {
                        "fact_id": str(fact.id),
                        "previous_fact_id": str(source_scope_conflict.id),
                        "decision": "promote_author_source_over_low_authority_duplicate",
                        "superseded_review_item_ids": [
                            str(review_id) for review_id in superseded_review_ids
                        ],
                    },
                )
                continue
            if _fact_source_scope_requires_review(fact, source_scope_conflict):
                fact.fact_status = "disputed"
                _create_review_item(session, fact, span.id, source_scope_conflict or conflict)
                disputed += 1
                changed_fact_ids.append(fact.id)
                _audit(
                    session,
                    job,
                    "memory.conflict_policy",
                    {
                        "fact_id": str(fact.id),
                        "decision": "review_required",
                        "policy_reason": "source_scope_conflict",
                    },
                )
                continue

            if conflict is not None and _is_temporal_state_progression(session, fact, conflict):
                conflict.fact_status = "outdated"
                fact.fact_status = "canon"
                fact.promotion_decision_id = uuid4()
                page = _upsert_memory_page(session, job.project_id, fact)
                _queue_agency_profile_rewrite_if_needed(session, job, span, fact, page)
                promoted += 1
                changed_fact_ids.extend([conflict.id, fact.id])
                _audit(
                    session,
                    job,
                    "memory.conflict_policy",
                    {
                        "fact_id": str(fact.id),
                        "previous_fact_id": str(conflict.id),
                        "decision": "supersede_outdated_state",
                    },
                )
                continue

            if conflict is not None:
                fact.fact_status = "disputed"
                _create_review_item(session, fact, span.id, conflict)
                disputed += 1
                changed_fact_ids.append(fact.id)
                _audit(
                    session,
                    job,
                    "memory.conflict_policy",
                    {"fact_id": str(fact.id), "decision": "review_required"},
                )
                continue

            fact.fact_status = "canon"
            fact.promotion_decision_id = uuid4()
            page = _upsert_memory_page(session, job.project_id, fact)
            _queue_agency_profile_rewrite_if_needed(session, job, span, fact, page)
            promoted += 1
            changed_fact_ids.append(fact.id)
            _audit(
                session,
                job,
                "memory.conflict_policy",
                {"fact_id": str(fact.id), "decision": "promote_canon"},
            )

        if changed_fact_ids:
            result = rebuild_graph_projection(session, project_id=job.project_id)
            _audit(
                session,
                job,
                "memory.graph_rebuilt",
                {
                    "run_id": str(result.run_id),
                    "created_edge_count": result.created_edge_count,
                },
            )
        _audit(
            session,
            job,
            "story.conflict_policy_completed",
            {
                "source_span_id": str(span.id),
                "promoted_count": promoted,
                "disputed_count": disputed,
            },
        )
        if changed_fact_ids:
            readiness_affected_refs: list[dict[str, object]] = [
                {"type": "fact_assertion", "id": str(fact_id)} for fact_id in changed_fact_ids
            ]
            readiness = mark_context_pack_readiness(
                session,
                project_id=job.project_id,
                source_span_id=span.id,
                affected_refs=readiness_affected_refs,
            )
            _audit(
                session,
                job,
                "context_pack.readiness_marked",
                {"readiness_id": str(readiness.id), "source_span_id": str(span.id)},
            )
        session.flush()


def _is_structured_memory_directive_text(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(STRUCTURED_FACT_DIRECTIVE_PATTERN.match(line) for line in lines)


def _story_text_for_extraction(text: str) -> str:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or _is_scene_metadata_line(line):
            index += 1
            continue
        break
    if index >= len(lines):
        return ""
    if index == 0:
        return text
    return "\n".join(lines[index:]).lstrip()


def _scene_metadata_mention_candidates(text: str) -> list[MentionCandidate]:
    candidates: list[MentionCandidate] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            offset += len(line)
            continue
        pov_match = EXPLICIT_POV_HINT_PATTERN.match(stripped)
        if pov_match is not None:
            character = pov_match.group("character").strip()
            candidates.append(
                MentionCandidate(
                    text=character,
                    mention_type="character",
                    confidence=0.86,
                    start_offset=offset + line.find(character),
                    end_offset=offset + line.find(character) + len(character),
                )
            )
            offset += len(line)
            continue
        location_match = EXPLICIT_LOCATION_HINT_PATTERN.match(stripped)
        if location_match is not None:
            location = location_match.group("location").strip()
            candidates.append(
                MentionCandidate(
                    text=location,
                    mention_type="location",
                    confidence=0.86,
                    start_offset=offset + line.find(location),
                    end_offset=offset + line.find(location) + len(location),
                )
            )
            offset += len(line)
            continue
        if SCENE_FIELD_METADATA_PATTERN.match(stripped):
            offset += len(line)
            continue
        break
    return candidates


def _is_chinese_locative_compound_subject(value: str) -> bool:
    return bool(re.search(r"(?:在|于)[\u4e00-\u9fff·]{2,}$", value))


def _explicit_pov_hint(text: str) -> tuple[str, str] | None:
    for line in text.splitlines()[:3]:
        if not line.strip():
            continue
        match = EXPLICIT_POV_HINT_PATTERN.match(line)
        if match is None:
            continue
        character = match.group("character").strip()
        if not character:
            return None
        return character, "third_limited"
    return None


def _is_scene_metadata_line(line: str) -> bool:
    stripped = line.strip()
    return bool(
        EXPLICIT_POV_HINT_PATTERN.match(stripped)
        or EXPLICIT_LOCATION_HINT_PATTERN.match(stripped)
        or SCENE_FIELD_METADATA_PATTERN.match(stripped)
    )


def _apply_scene_pov_hint(
    session: Session,
    span: SourceSpan,
    mentions: list[StoryMention],
) -> tuple[UUID, str] | None:
    if span.scene_id is None:
        return None
    hint = _pov_hint_for_span(session, span)
    if hint is None:
        return None
    character_name, pov_mode = hint
    normalized = character_name.casefold()
    mention = next(
        (
            item
            for item in mentions
            if item.mention_type == "character"
            and item.raw_text.casefold() == normalized
            and item.resolved_entity_id is not None
        ),
        None,
    )
    if mention is None or mention.resolved_entity_id is None:
        entity = _existing_pov_character_entity(session, span, character_name)
        if entity is None:
            return None
        scene = session.get(StoryScene, span.scene_id)
        if scene is None:
            return None
        scene.pov_character_id = entity.id
        scene.pov_mode = pov_mode
        scene.pov_confidence = 0.82
        scene.pov_evidence_span_ids = [str(span.id)]
        scene.pov_uncertainty_reason = None
        return entity.id, pov_mode
    scene = session.get(StoryScene, span.scene_id)
    if scene is None:
        return None
    scene.pov_character_id = mention.resolved_entity_id
    scene.pov_mode = pov_mode
    scene.pov_confidence = 0.9
    scene.pov_evidence_span_ids = [str(span.id)]
    scene.pov_uncertainty_reason = None
    return mention.resolved_entity_id, pov_mode


def _existing_pov_character_entity(
    session: Session,
    span: SourceSpan,
    character_name: str,
) -> StoryCanonicalEntity | None:
    raw_source = session.get(RawSource, span.source_id)
    if raw_source is None:
        return None
    normalized = character_name.casefold()
    matches = [
        entity
        for entity in session.scalars(
            select(StoryCanonicalEntity)
            .where(StoryCanonicalEntity.project_id == raw_source.project_id)
            .where(StoryCanonicalEntity.entity_type == "character")
            .where(StoryCanonicalEntity.canonical_status.in_(("canon", "draft", "provisional")))
            .order_by(StoryCanonicalEntity.created_at, StoryCanonicalEntity.id)
        )
        if entity.display_name.casefold() == normalized
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _apply_scene_pov_model_judgment(
    session: Session,
    span: SourceSpan,
    mentions: list[StoryMention],
    provider: PovDetectionProvider | None,
) -> tuple[UUID | None, str] | None:
    if provider is None or span.scene_id is None:
        return None
    resolved_character_mentions = [
        mention
        for mention in mentions
        if mention.mention_type == "character" and mention.resolved_entity_id is not None
    ]
    if not resolved_character_mentions:
        return None
    raw_source = session.get(RawSource, span.source_id)
    if raw_source is None:
        return None
    request = PovDetectionRequest(
        source_span_id=span.id,
        scene_id=span.scene_id,
        text=_story_text_for_extraction(span.text_preview),
        mentions=[
            PovDetectionMention(
                raw_text=mention.raw_text,
                mention_type=mention.mention_type,
                canonical_entity_id=str(mention.resolved_entity_id)
                if mention.resolved_entity_id
                else None,
            )
            for mention in resolved_character_mentions
        ],
    )
    try:
        skill_result = run_skill(
            "detect-pov",
            STORY_SKILL_VERSION,
            request,
            StorySkillRuntimeContext(
                project_id=raw_source.project_id,
                request_id=f"detect-pov:{span.id}",
                pov_detection_provider=provider,
            ),
        )
    except StorySkillValidationError as exc:
        raise TerminalJobError(str(exc)) from exc
    result = cast(PovDetectionResult, skill_result.raw_result)
    _validate_pov_detection_result(result_mode=result.pov_mode, confidence=result.confidence)
    evidence_span_ids = _validated_pov_evidence_span_ids(result.evidence_span_ids, span.id)
    scene = session.get(StoryScene, span.scene_id)
    if scene is None or scene.pov_character_id is not None:
        return None
    if result.pov_character_name is None:
        scene.pov_mode = result.pov_mode
        scene.pov_confidence = result.confidence
        scene.pov_evidence_span_ids = evidence_span_ids
        scene.pov_uncertainty_reason = result.uncertainty_reason or "model_assisted_no_character"
        return None, result.pov_mode
    normalized = result.pov_character_name.casefold()
    mention = next(
        (
            item
            for item in resolved_character_mentions
            if item.raw_text.casefold() == normalized and item.resolved_entity_id is not None
        ),
        None,
    )
    if mention is None or mention.resolved_entity_id is None:
        scene.pov_mode = "unknown"
        scene.pov_confidence = result.confidence
        scene.pov_evidence_span_ids = evidence_span_ids
        scene.pov_uncertainty_reason = "model_character_not_resolved"
        return None, "unknown"
    scene.pov_character_id = mention.resolved_entity_id
    scene.pov_mode = result.pov_mode
    scene.pov_confidence = result.confidence
    scene.pov_evidence_span_ids = evidence_span_ids
    scene.pov_uncertainty_reason = result.uncertainty_reason
    return mention.resolved_entity_id, result.pov_mode


def _validate_pov_detection_result(*, result_mode: str, confidence: float) -> None:
    if result_mode not in POV_MODES:
        raise TerminalJobError(f"POV detection provider returned invalid pov_mode: {result_mode}")
    if confidence < 0 or confidence > 1:
        raise TerminalJobError("POV detection provider returned confidence outside 0..1.")


def _validated_pov_evidence_span_ids(evidence_span_ids: list[str], span_id: UUID) -> list[str]:
    span_ref = str(span_id)
    if span_ref not in evidence_span_ids:
        raise TerminalJobError(
            "POV detection provider returned no evidence for current SourceSpan."
        )
    if set(evidence_span_ids) != {span_ref}:
        raise TerminalJobError(
            "POV detection provider cited SourceSpan evidence outside the POV detection request."
        )
    return [span_ref]


def _apply_scene_location(
    session: Session,
    span: SourceSpan,
    mentions: list[StoryMention],
) -> UUID | None:
    if span.scene_id is None:
        return None
    location = next(
        (
            item
            for item in mentions
            if item.mention_type == "location" and item.resolved_entity_id is not None
        ),
        None,
    )
    if location is None or location.resolved_entity_id is None:
        return None
    scene = session.get(StoryScene, span.scene_id)
    if scene is None:
        return None
    scene.location_entity_id = location.resolved_entity_id
    return location.resolved_entity_id


def _apply_span_speaker(
    session: Session,
    span: SourceSpan,
    *,
    mentions: list[StoryMention],
    text: str,
) -> UUID | None:
    speaker_surfaces = _explicit_dialogue_speaker_surfaces(text)
    if not speaker_surfaces:
        return span.speaker_entity_id
    if all(_is_speaker_pronoun(surface) for surface in speaker_surfaces):
        speaker_id = _single_prior_dialogue_speaker(session, span)
        if speaker_id is None:
            return span.speaker_entity_id
        span.speaker_entity_id = speaker_id
        span.narration_layer = "dialogue"
        _apply_speaker_to_following_pronoun_dialogue_spans(session, span, speaker_id)
        return speaker_id
    speaker_id = _unique_resolved_explicit_dialogue_speaker_id(mentions, text)
    if speaker_id is None:
        return span.speaker_entity_id
    span.speaker_entity_id = speaker_id
    span.narration_layer = "dialogue"
    _apply_speaker_to_following_pronoun_dialogue_spans(session, span, speaker_id)
    return speaker_id


def _unique_resolved_explicit_dialogue_speaker_id(
    mentions: list[StoryMention],
    text: str,
) -> UUID | None:
    speaker_surfaces = _explicit_dialogue_speaker_surfaces(text)
    if not speaker_surfaces or any(_is_speaker_pronoun(surface) for surface in speaker_surfaces):
        return None
    resolved_by_surface: dict[str, set[UUID]] = {}
    for mention in mentions:
        if mention.mention_type != "character" or mention.resolved_entity_id is None:
            continue
        resolved_by_surface.setdefault(_speaker_key(mention.raw_text), set()).add(
            mention.resolved_entity_id
        )
    speaker_ids: set[UUID] = set()
    for surface in speaker_surfaces:
        speaker_ids.update(resolved_by_surface.get(_speaker_key(surface), set()))
    if len(speaker_ids) != 1:
        return None
    return next(iter(speaker_ids))


def _explicit_dialogue_speaker_surfaces(text: str) -> list[str]:
    surfaces: list[str] = []
    for pattern in (
        ENGLISH_DIALOGUE_SPEAKER_PATTERN,
        ENGLISH_POST_QUOTE_DIALOGUE_SPEAKER_PATTERN,
        CHINESE_DIALOGUE_SPEAKER_PATTERN,
        CHINESE_POST_QUOTE_DIALOGUE_SPEAKER_PATTERN,
    ):
        for match in pattern.finditer(text):
            surface = match.group("speaker").strip()
            if surface:
                surfaces.append(surface)
    return surfaces


def _speaker_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _is_speaker_pronoun(value: str) -> bool:
    stripped = value.strip()
    return (
        stripped in CHINESE_SPEAKER_PRONOUNS or _speaker_key(stripped) in ENGLISH_SPEAKER_PRONOUNS
    )


def _single_prior_dialogue_speaker(session: Session, span: SourceSpan) -> UUID | None:
    prior_spans = list(
        session.scalars(
            select(SourceSpan)
            .where(SourceSpan.view_id == span.view_id)
            .where(SourceSpan.start_offset < span.start_offset)
            .order_by(SourceSpan.start_offset.desc(), SourceSpan.id.desc())
        )
    )
    if not prior_spans:
        return None
    nearest = prior_spans[0]
    if nearest.narration_layer != "dialogue" or nearest.speaker_entity_id is None:
        return None
    speaker_ids = _contiguous_prior_dialogue_speaker_ids(prior_spans)
    if speaker_ids is None:
        return None
    if len(speaker_ids) != 1:
        return None
    return nearest.speaker_entity_id


def _contiguous_prior_dialogue_speaker_ids(prior_spans: list[SourceSpan]) -> set[UUID] | None:
    speaker_ids: set[UUID] = set()
    for prior_span in prior_spans:
        if prior_span.narration_layer != "dialogue":
            if _explicit_dialogue_speaker_surfaces(prior_span.text_preview):
                return None
            break
        if prior_span.speaker_entity_id is not None:
            speaker_ids.add(prior_span.speaker_entity_id)
    return speaker_ids


def _apply_speaker_to_following_pronoun_dialogue_spans(
    session: Session,
    span: SourceSpan,
    speaker_id: UUID,
) -> None:
    prior_spans = list(
        session.scalars(
            select(SourceSpan)
            .where(SourceSpan.view_id == span.view_id)
            .where(SourceSpan.start_offset < span.start_offset)
            .order_by(SourceSpan.start_offset.desc(), SourceSpan.id.desc())
        )
    )
    dialogue_run_speaker_ids = _contiguous_prior_dialogue_speaker_ids(prior_spans)
    if dialogue_run_speaker_ids is None:
        return
    dialogue_run_speaker_ids.add(speaker_id)
    if dialogue_run_speaker_ids != {speaker_id}:
        return
    following_spans = list(
        session.scalars(
            select(SourceSpan)
            .where(SourceSpan.view_id == span.view_id)
            .where(SourceSpan.start_offset > span.start_offset)
            .order_by(SourceSpan.start_offset, SourceSpan.id)
        )
    )
    for following_span in following_spans:
        if following_span.speaker_entity_id is not None:
            if following_span.speaker_entity_id != speaker_id:
                return
            continue
        surfaces = _explicit_dialogue_speaker_surfaces(following_span.text_preview)
        if not surfaces or not all(_is_speaker_pronoun(surface) for surface in surfaces):
            return
        following_span.speaker_entity_id = speaker_id
        following_span.narration_layer = "dialogue"


def _pov_hint_for_span(session: Session, span: SourceSpan) -> tuple[str, str] | None:
    explicit_hint = _explicit_pov_hint(span.text_preview)
    if explicit_hint is None:
        return None
    return explicit_hint[0], "third_limited"


def _has_chinese_leading_discourse_prefix(value: str) -> bool:
    for marker in CHINESE_KNOWLEDGE_LEADING_DISCOURSE_MARKERS:
        if not value.startswith(marker):
            continue
        remainder = value[len(marker) :].strip()
        if len(remainder) >= 2 and _contains_cjk(remainder):
            return True
    return False


def _is_invalid_chinese_mention(value: str) -> bool:
    return _contains_cjk(value) and (
        value in CHINESE_INVALID_MENTION_VALUES
        or _has_chinese_leading_discourse_prefix(value)
        or value.startswith(CHINESE_INVALID_MENTION_PREFIXES)
        or value.endswith(CHINESE_INVALID_MENTION_SUFFIXES)
        or value.startswith(CHINESE_PRONOUN_MENTION_PREFIXES)
    )


def _span_from_payload(session: Session, job: JobRecord) -> SourceSpan:
    value = job.payload.get("source_span_id")
    try:
        span_id = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError("job payload requires source_span_id") from exc
    span = session.get(SourceSpan, span_id)
    if span is None:
        raise TerminalJobError("SourceSpan was not found for source pipeline job.")
    raw_source = session.get(RawSource, span.source_id)
    if raw_source is None or raw_source.project_id != job.project_id:
        raise TerminalJobError("SourceSpan does not belong to the job project.")
    return span


def _span_text(session: Session, object_store: ObjectStore, span: SourceSpan) -> str:
    view = session.get(SourceProcessedView, span.view_id)
    if view is None:
        raise TerminalJobError("ProcessedMarkdownView was not found for SourceSpan.")
    markdown = object_store.get_text(view.markdown_ref)
    if span.end_offset <= len(markdown):
        text = markdown[span.start_offset : span.end_offset]
    else:
        text = span.text_preview
    if not text.strip():
        raise TerminalJobError("SourceSpan text is empty for source pipeline job.")
    return text


def _source_scope_for_span(session: Session, span: SourceSpan) -> str:
    raw_source = session.get(RawSource, span.source_id)
    if raw_source is None:
        raise TerminalJobError("RawSource was not found for SourceSpan.")
    return raw_source.source_scope


def _enqueue_next_span_job(
    session: Session,
    current_job: JobRecord,
    span: SourceSpan,
    *,
    job_type: str,
    version_key: str,
    version: str,
) -> None:
    idempotency_key = f"{span.id}:{version}"
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == current_job.project_id)
        .where(JobRecord.job_type == job_type)
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=current_job.project_id,
            job_type=job_type,
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": job_type,
                "pipeline_version": PIPELINE_VERSION,
                "source_span_id": str(span.id),
                version_key: version,
                "trigger": current_job.job_type,
            },
        )
    )


def _mention_exists(session: Session, span_id: UUID, raw_text: str) -> bool:
    return (
        session.scalars(
            select(StoryMention)
            .where(StoryMention.span_id == span_id)
            .where(StoryMention.raw_text == raw_text)
        ).first()
        is not None
    )


def _alias_exists(session: Session, project_id: UUID, alias_text: str, span_id: UUID) -> bool:
    return any(
        str(span_id) in alias.evidence_span_ids
        for alias in session.scalars(
            select(StoryAliasRecord)
            .where(StoryAliasRecord.project_id == project_id)
            .where(StoryAliasRecord.alias_text == alias_text)
        )
    )


def _alias_for_text(
    session: Session,
    project_id: UUID,
    alias_text: str,
) -> StoryAliasRecord | None:
    normalized_alias = alias_text.strip().lower()
    return session.scalars(
        select(StoryAliasRecord)
        .where(StoryAliasRecord.project_id == project_id)
        .where(func.lower(StoryAliasRecord.alias_text) == normalized_alias)
        .order_by(StoryAliasRecord.created_at, StoryAliasRecord.id)
    ).first()


def _maybe_create_alias_conflict_review_item(
    session: Session,
    *,
    project_id: UUID,
    span: SourceSpan,
    mention: StoryMention,
    alias: StoryAliasRecord,
    entity: StoryCanonicalEntity,
) -> bool:
    conflicting_alias = _near_alias_conflict(
        session,
        project_id=project_id,
        alias=alias,
        entity=entity,
    )
    if conflicting_alias is None:
        return False
    if conflicting_alias.entity_id is None:
        return False
    conflicting_entity = session.get(StoryCanonicalEntity, conflicting_alias.entity_id)
    if conflicting_entity is None or conflicting_entity.project_id != project_id:
        return False
    if conflicting_entity.entity_type != entity.entity_type:
        return False
    new_source_span_ids = _source_span_ids_for_project(session, [str(span.id)], project_id)
    if not new_source_span_ids:
        return False
    existing_source_span_ids = _source_span_ids_for_project(
        session,
        [str(item) for item in conflicting_alias.evidence_span_ids],
        project_id,
    )
    if _alias_conflict_review_exists(
        session,
        project_id=project_id,
        alias_record_id=alias.id,
        conflicting_alias_record_id=conflicting_alias.id,
    ):
        return True

    session.add(
        ReviewItemRecord(
            id=uuid4(),
            project_id=project_id,
            review_type="alias_conflict",
            severity="medium",
            status="open",
            summary=(
                f"Alias '{alias.alias_text}' may be a spelling variant of "
                f"'{conflicting_alias.alias_text}' and needs author confirmation."
            ),
            affected_refs={
                "alias_record_id": str(alias.id),
                "candidate_entity_id": str(entity.id),
                "conflicting_alias_record_id": str(conflicting_alias.id),
                "target_entity_id": str(conflicting_entity.id),
            },
            new_evidence={
                "source_span_ids": new_source_span_ids,
                "mention_id": str(mention.id),
                "alias_text": alias.alias_text,
                "candidate_entity_id": str(entity.id),
            },
            existing_evidence={
                "source_span_ids": existing_source_span_ids,
                "alias_text": conflicting_alias.alias_text,
                "entity_id": str(conflicting_entity.id),
            },
            suggested_actions=[
                {"resolution": "merge", "target_entity_id": str(conflicting_entity.id)},
                {"resolution": "accept", "target_entity_id": str(entity.id)},
                {"resolution": "reject"},
            ],
            default_action="review",
        )
    )
    return True


def _near_alias_conflict(
    session: Session,
    *,
    project_id: UUID,
    alias: StoryAliasRecord,
    entity: StoryCanonicalEntity,
) -> StoryAliasRecord | None:
    if alias.entity_id is None or alias.status in {"rejected", "user_confirmed", "user_corrected"}:
        return None
    alias_key = _latin_alias_key(alias.alias_text)
    if alias_key is None:
        return None

    for existing in session.scalars(
        select(StoryAliasRecord)
        .where(StoryAliasRecord.project_id == project_id)
        .where(StoryAliasRecord.id != alias.id)
        .order_by(StoryAliasRecord.created_at, StoryAliasRecord.id)
    ):
        if existing.entity_id is None or existing.entity_id == entity.id:
            continue
        if existing.status == "rejected" or existing.alias_type != alias.alias_type:
            continue
        existing_key = _latin_alias_key(existing.alias_text)
        if existing_key is None or not _edit_distance_at_most_one(alias_key, existing_key):
            continue
        existing_entity = session.get(StoryCanonicalEntity, existing.entity_id)
        if existing_entity is None or existing_entity.entity_type != entity.entity_type:
            continue
        return existing
    return None


def _alias_conflict_review_exists(
    session: Session,
    *,
    project_id: UUID,
    alias_record_id: UUID,
    conflicting_alias_record_id: UUID,
) -> bool:
    for review in session.scalars(
        select(ReviewItemRecord)
        .where(ReviewItemRecord.project_id == project_id)
        .where(ReviewItemRecord.review_type == "alias_conflict")
    ):
        affected_refs = review.affected_refs
        if affected_refs.get("alias_record_id") != str(alias_record_id):
            continue
        if affected_refs.get("conflicting_alias_record_id") != str(conflicting_alias_record_id):
            continue
        return True
    return False


def _latin_alias_key(value: str) -> str | None:
    key = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if len(key) < 4 or len(key) > 40:
        return None
    if not re.fullmatch(r"[a-z0-9]+", key):
        return None
    return key


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return False
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right, strict=True)) <= 1

    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    index_short = 0
    index_long = 0
    edits = 0
    while index_short < len(shorter) and index_long < len(longer):
        if shorter[index_short] == longer[index_long]:
            index_short += 1
            index_long += 1
            continue
        edits += 1
        if edits > 1:
            return False
        index_long += 1
    return True


def _canonical_entity_for_mention(
    session: Session,
    *,
    project_id: UUID,
    mention: StoryMention,
    span: SourceSpan,
    story_schema: EffectiveStorySchema,
    entity_id: UUID | None,
) -> StoryCanonicalEntity:
    if entity_id is not None:
        entity = session.get(StoryCanonicalEntity, entity_id)
        if entity is not None and entity.project_id == project_id:
            _record_first_seen_scene(session, entity, span)
            return entity

    entity_type = _entity_type_for_mention(mention, story_schema)
    display_name = mention.raw_text.strip()
    normalized_name = display_name.lower()
    existing = session.scalars(
        select(StoryCanonicalEntity)
        .where(StoryCanonicalEntity.project_id == project_id)
        .where(StoryCanonicalEntity.entity_type == entity_type)
        .where(func.lower(StoryCanonicalEntity.display_name) == normalized_name)
        .order_by(StoryCanonicalEntity.created_at, StoryCanonicalEntity.id)
    ).first()
    if existing is not None:
        _record_first_seen_scene(session, existing, span)
        return existing

    entity = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project_id,
        entity_type=entity_type,
        display_name=display_name,
        canonical_status="provisional",
        cast_tier="unknown" if entity_type == "character" else None,
        first_seen_scene_id=span.scene_id,
        description=None,
    )
    session.add(entity)
    session.flush()
    return entity


def _record_first_seen_scene(
    session: Session,
    entity: StoryCanonicalEntity,
    span: SourceSpan,
) -> None:
    if span.scene_id is None:
        return
    if entity.first_seen_scene_id is None:
        entity.first_seen_scene_id = span.scene_id
        return
    current_scene = session.get(StoryScene, entity.first_seen_scene_id)
    candidate_scene = session.get(StoryScene, span.scene_id)
    if current_scene is None or candidate_scene is None:
        return
    if candidate_scene.start_offset < current_scene.start_offset:
        entity.first_seen_scene_id = span.scene_id


def _entity_type_for_mention(
    mention: StoryMention,
    story_schema: EffectiveStorySchema,
) -> str:
    if mention.mention_type in CANONICAL_MENTION_ENTITY_TYPES:
        return mention.mention_type
    entity_definition = story_schema.entity_types.get(mention.mention_type)
    if entity_definition is not None:
        subtype = entity_definition.get("subtype_of")
        if isinstance(subtype, str) and subtype in CANONICAL_MENTION_ENTITY_TYPES:
            return subtype
    return "other"


def _event_candidate_exists_for_span(session: Session, project_id: UUID, span_id: UUID) -> bool:
    return any(
        str(span_id) in candidate.evidence_span_ids
        for candidate in session.scalars(
            select(StoryEventCandidate).where(StoryEventCandidate.project_id == project_id)
        )
    )


@dataclass(frozen=True, slots=True)
class EventAggregationDecisionResult:
    event: StoryCanonicalEvent | None
    merge: bool
    provider_decision: str | None = None
    provider_result: EventAggregationAdjudicationResult | None = None
    provider_request: EventAggregationAdjudicationRequest | None = None
    provider_original_decision: str | None = None
    policy_reason: str | None = None
    dispute_existing_event: bool = False


def _canonical_event_decision_for_candidate(
    session: Session,
    job: JobRecord,
    candidate: StoryEventCandidate,
    provider: EventAggregationAdjudicationProvider | None,
) -> EventAggregationDecisionResult:
    for event in session.scalars(
        select(StoryCanonicalEvent).where(StoryCanonicalEvent.project_id == job.project_id)
    ):
        if str(candidate.id) in event.event_candidate_ids:
            return EventAggregationDecisionResult(event=event, merge=True)
        if _event_title_matches_candidate(session, event, candidate):
            return EventAggregationDecisionResult(event=event, merge=True)
        if _event_signature_matches_candidate(session, event, candidate):
            return EventAggregationDecisionResult(event=event, merge=True)
        provider_decision = _event_provider_decision_for_candidate(
            session,
            job,
            event,
            candidate,
            provider,
        )
        if provider_decision is not None:
            return provider_decision
    return EventAggregationDecisionResult(event=None, merge=False)


def _event_title_matches_candidate(
    session: Session,
    event: StoryCanonicalEvent,
    candidate: StoryEventCandidate,
) -> bool:
    return (
        event.event_type == candidate.event_type
        and event.title == _event_title(candidate.summary)
        and _event_spans_are_same_source_neighbors(session, event, candidate)
    )


def _event_provider_decision_for_candidate(
    session: Session,
    job: JobRecord,
    event: StoryCanonicalEvent,
    candidate: StoryEventCandidate,
    provider: EventAggregationAdjudicationProvider | None,
) -> EventAggregationDecisionResult | None:
    if provider is None:
        return None
    if event.event_type != candidate.event_type:
        return None
    request = _event_adjudication_request(session, event, candidate)
    if request is None:
        return None
    try:
        skill_result = run_skill(
            "aggregate-events",
            STORY_SKILL_VERSION,
            request,
            StorySkillRuntimeContext(
                project_id=event.project_id,
                request_id=f"aggregate-events:{candidate.id}",
                event_aggregation_provider=provider,
            ),
        )
    except TerminalJobError:
        raise
    except StorySkillValidationError as exc:
        raise TerminalJobError(str(exc)) from exc
    except Exception as exc:
        raise TerminalJobError(str(exc)) from exc
    result = cast(EventAggregationAdjudicationResult, skill_result.raw_result)
    _validate_event_adjudication_result(result, request)
    if result.decision == "same_event":
        event_scopes = _source_scopes_for_span_ids(session, event.evidence_span_ids)
        candidate_scopes = _source_scopes_for_span_ids(session, candidate.evidence_span_ids)
        if not _event_source_scopes_allow_merge(event_scopes, candidate_scopes):
            return EventAggregationDecisionResult(
                event=event,
                merge=False,
                provider_decision="conflict_version",
                provider_result=_source_scope_conflict_adjudication_result(
                    result,
                    event_scopes=event_scopes,
                    candidate_scopes=candidate_scopes,
                ),
                provider_request=request,
                provider_original_decision=result.decision,
                policy_reason="source_scope_conflict",
                dispute_existing_event=_source_scope_conflict_should_dispute_existing_event(
                    event,
                    event_scopes=event_scopes,
                    candidate_scopes=candidate_scopes,
                ),
            )
        return EventAggregationDecisionResult(
            event=event,
            merge=True,
            provider_decision=result.decision,
            provider_result=result,
            provider_request=request,
        )
    if result.decision == "conflict_version":
        return EventAggregationDecisionResult(
            event=event,
            merge=False,
            provider_decision=result.decision,
            provider_result=result,
            provider_request=request,
        )
    return EventAggregationDecisionResult(
        event=None,
        merge=False,
        provider_decision=result.decision,
        provider_result=result,
        provider_request=request,
    )


def _source_scopes_for_span_ids(session: Session, span_ids: list[str]) -> set[str]:
    return {_source_scope_for_span(session, span) for span in _spans_from_ids(session, span_ids)}


def _event_source_scopes_allow_merge(
    event_scopes: set[str],
    candidate_scopes: set[str],
) -> bool:
    return (
        bool(event_scopes) and bool(candidate_scopes) and len(event_scopes | candidate_scopes) == 1
    )


def _source_scope_conflict_should_dispute_existing_event(
    event: StoryCanonicalEvent,
    *,
    event_scopes: set[str],
    candidate_scopes: set[str],
) -> bool:
    return (
        event.event_status == "proposed"
        and bool(event_scopes)
        and bool(candidate_scopes)
        and event_scopes.issubset(REVIEW_REQUIRED_SOURCE_SCOPES)
        and not candidate_scopes.issubset(REVIEW_REQUIRED_SOURCE_SCOPES)
    )


def _source_scope_conflict_adjudication_result(
    result: EventAggregationAdjudicationResult,
    *,
    event_scopes: set[str],
    candidate_scopes: set[str],
) -> EventAggregationAdjudicationResult:
    existing = ", ".join(sorted(event_scopes)) or "unknown"
    candidate = ", ".join(sorted(candidate_scopes)) or "unknown"
    return EventAggregationAdjudicationResult(
        decision="conflict_version",
        confidence=result.confidence,
        rationale=(
            "Provider same_event blocked by source_scope_conflict: "
            f"existing scopes {existing}; candidate scopes {candidate}. "
            f"Provider rationale: {result.rationale}"
        ),
        evidence_span_ids=list(result.evidence_span_ids),
    )


def _event_adjudication_request(
    session: Session,
    event: StoryCanonicalEvent,
    candidate: StoryEventCandidate,
) -> EventAggregationAdjudicationRequest | None:
    event_text = _source_text_for_span_ids(session, event.evidence_span_ids)
    candidate_text = _source_text_for_span_ids(session, candidate.evidence_span_ids)
    if event_text is None or candidate_text is None:
        return None
    return EventAggregationAdjudicationRequest(
        existing_event_id=event.id,
        existing_event_type=event.event_type,
        existing_event_title=event.title,
        existing_event_summary=event.summary,
        existing_event_participants=event.participants,
        existing_event_objects=event.objects,
        existing_event_evidence_span_ids=list(event.evidence_span_ids),
        existing_event_source_text=event_text,
        candidate_id=candidate.id,
        candidate_event_type=candidate.event_type,
        candidate_summary=candidate.summary,
        candidate_participants=candidate.participants,
        candidate_objects=candidate.objects,
        candidate_evidence_span_ids=list(candidate.evidence_span_ids),
        candidate_source_text=candidate_text,
    )


def _source_text_for_span_ids(session: Session, span_ids: list[str]) -> str | None:
    spans = _spans_from_ids(session, span_ids)
    if not spans:
        return None
    return "\n\n".join(span.text_preview for span in spans)


def _validate_event_adjudication_result(
    result: EventAggregationAdjudicationResult,
    request: EventAggregationAdjudicationRequest,
) -> None:
    if result.decision not in {
        "same_event",
        "related_but_distinct",
        "conflict_version",
        "uncertain",
    }:
        raise TerminalJobError("Event aggregation provider returned invalid decision.")
    if not 0 <= result.confidence <= 1:
        raise TerminalJobError("Event aggregation provider returned confidence outside 0..1.")
    if not isinstance(result.rationale, str) or not result.rationale.strip():
        raise TerminalJobError("Event aggregation provider returned empty rationale.")
    evidence_span_ids = set(result.evidence_span_ids)
    if not evidence_span_ids:
        raise TerminalJobError("Event aggregation provider returned no evidence_span_ids.")
    allowed_span_ids = set(request.existing_event_evidence_span_ids) | set(
        request.candidate_evidence_span_ids
    )
    if not evidence_span_ids.issubset(allowed_span_ids):
        raise TerminalJobError(
            "Event aggregation provider cited SourceSpan evidence outside the adjudication request."
        )
    if not set(request.existing_event_evidence_span_ids).issubset(evidence_span_ids):
        raise TerminalJobError(
            "Event aggregation provider must cite existing CanonicalEvent SourceSpan evidence."
        )
    if not set(request.candidate_evidence_span_ids).issubset(evidence_span_ids):
        raise TerminalJobError(
            "Event aggregation provider must cite current candidate SourceSpan evidence."
        )


def _audit_event_adjudication(
    session: Session,
    job: JobRecord,
    decision: EventAggregationDecisionResult,
    candidate: StoryEventCandidate,
    canonical: StoryCanonicalEvent,
) -> None:
    result = decision.provider_result
    request = decision.provider_request
    if result is None or request is None:
        return
    audit_payload: dict[str, object] = {
        "candidate_id": str(candidate.id),
        "existing_event_id": str(decision.event.id) if decision.event is not None else None,
        "canonical_event_id": str(canonical.id),
        "decision": result.decision,
        "confidence": result.confidence,
        "evidence_span_ids": result.evidence_span_ids,
        "provider_compared_span_ids": _merge_unique(
            request.existing_event_evidence_span_ids,
            request.candidate_evidence_span_ids,
        ),
    }
    if decision.provider_original_decision is not None:
        audit_payload["provider_original_decision"] = decision.provider_original_decision
    if decision.policy_reason is not None:
        audit_payload["policy_reason"] = decision.policy_reason
    _audit(
        session,
        job,
        "story.event_adjudicated",
        audit_payload,
    )


def _candidate_aggregation_status(decision: EventAggregationDecisionResult) -> str:
    if decision.provider_decision == "related_but_distinct":
        return "related"
    if decision.provider_decision == "conflict_version":
        return "conflict_version"
    return "merged"


def _create_event_merge_conflict_review_item(
    session: Session,
    *,
    existing_event: StoryCanonicalEvent,
    disputed_event: StoryCanonicalEvent,
    policy_reason: str | None = None,
) -> None:
    new_source_span_ids = _event_review_source_span_ids(session, disputed_event)
    if not new_source_span_ids:
        return
    existing_source_span_ids = _event_review_source_span_ids(session, existing_event)
    affected_refs = {
        "event_id": str(disputed_event.id),
        "existing_event_id": str(existing_event.id),
        "event_type": disputed_event.event_type,
    }
    if (
        session.scalars(
            select(ReviewItemRecord)
            .where(ReviewItemRecord.project_id == disputed_event.project_id)
            .where(ReviewItemRecord.affected_refs == affected_refs)
        ).first()
        is not None
    ):
        return
    summary = "Event aggregation conflict needs author review before events are merged."
    if policy_reason == "source_scope_conflict":
        summary = "Event source scope conflict needs author review before events are merged."
    session.add(
        ReviewItemRecord(
            id=uuid4(),
            project_id=disputed_event.project_id,
            review_type="event_merge_conflict",
            severity="medium",
            status="open",
            summary=summary,
            affected_refs=affected_refs,
            new_evidence={
                "event_id": str(disputed_event.id),
                "source_span_ids": new_source_span_ids,
                "summary": disputed_event.summary,
            },
            existing_evidence={
                "event_id": str(existing_event.id),
                "source_span_ids": existing_source_span_ids,
                "summary": existing_event.summary,
            },
            suggested_actions=[
                {"resolution": "merge"},
                {"resolution": "split"},
                {"resolution": "mark_intentional"},
                {"resolution": "reject"},
            ],
            default_action="review",
        )
    )


def _event_signature_matches_candidate(
    session: Session,
    event: StoryCanonicalEvent,
    candidate: StoryEventCandidate,
) -> bool:
    if event.event_type != candidate.event_type:
        return False
    if event.event_type != "object_transfer":
        return False
    if not _event_spans_are_same_source_neighbors(session, event, candidate):
        return False
    return _same_ref_set(event.objects, candidate.objects) and _same_ref_set(
        event.participants,
        candidate.participants,
    )


def _event_spans_are_same_source_neighbors(
    session: Session,
    event: StoryCanonicalEvent,
    candidate: StoryEventCandidate,
) -> bool:
    event_spans = _spans_from_ids(session, event.evidence_span_ids)
    candidate_spans = _spans_from_ids(session, candidate.evidence_span_ids)
    return any(
        _source_spans_are_neighbors(session, event_span, candidate_span)
        for event_span in event_spans
        for candidate_span in candidate_spans
    )


def _spans_from_ids(session: Session, span_ids: list[str]) -> list[SourceSpan]:
    spans: list[SourceSpan] = []
    for span_id in span_ids:
        try:
            span_uuid = UUID(span_id)
        except ValueError:
            continue
        span = session.get(SourceSpan, span_uuid)
        if span is not None:
            spans.append(span)
    return spans


def _source_span_ids_for_project(
    session: Session,
    span_ids: list[str],
    project_id: UUID,
) -> list[str]:
    filtered: list[str] = []
    for span in _spans_from_ids(session, span_ids):
        raw_source = session.get(RawSource, span.source_id)
        if raw_source is None or raw_source.project_id != project_id:
            continue
        filtered.append(str(span.id))
    return list(dict.fromkeys(filtered))


def _event_review_source_span_ids(session: Session, event: StoryCanonicalEvent) -> list[str]:
    return _source_span_ids_for_project(session, event.evidence_span_ids, event.project_id)


def _source_spans_are_neighbors(
    session: Session,
    first: SourceSpan,
    second: SourceSpan,
) -> bool:
    if first.id == second.id:
        return True
    if first.source_id != second.source_id:
        return False
    if first.version_id != second.version_id:
        return _source_spans_are_adjacent_version_counterparts(session, first, second)
    return _source_spans_are_same_version_neighbors(session, first, second)


def _source_spans_are_same_version_neighbors(
    session: Session,
    first: SourceSpan,
    second: SourceSpan,
) -> bool:
    lower, upper = sorted((first, second), key=lambda span: span.start_offset)
    intervening = session.scalars(
        select(SourceSpan)
        .where(SourceSpan.source_id == lower.source_id)
        .where(SourceSpan.version_id == lower.version_id)
        .where(SourceSpan.start_offset > lower.start_offset)
        .where(SourceSpan.start_offset < upper.start_offset)
        .order_by(SourceSpan.start_offset)
    ).first()
    return intervening is None


def _source_spans_are_adjacent_version_counterparts(
    session: Session,
    first: SourceSpan,
    second: SourceSpan,
) -> bool:
    first_version = session.get(SourceVersion, first.version_id)
    second_version = session.get(SourceVersion, second.version_id)
    if first_version is None or second_version is None:
        return False
    if first_version.source_id != second_version.source_id:
        return False
    if not (
        first_version.supersedes_version_id == second_version.id
        or second_version.supersedes_version_id == first_version.id
    ):
        return False
    return _source_spans_have_matching_structure(session, first, second)


def _source_spans_have_matching_structure(
    session: Session,
    first: SourceSpan,
    second: SourceSpan,
) -> bool:
    first_key = _source_span_structure_key(session, first)
    second_key = _source_span_structure_key(session, second)
    if first_key is not None and second_key is not None:
        return first_key == second_key
    if first_key is not None or second_key is not None:
        return False
    return first.raw_start_offset == second.raw_start_offset


def _source_span_structure_key(
    session: Session,
    span: SourceSpan,
) -> tuple[int, str, int, int] | None:
    if span.scene_id is None:
        return None
    scene = session.get(StoryScene, span.scene_id)
    if scene is None:
        return None
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return None
    span_index = _source_span_index_within_scene(session, span)
    return (
        chapter.chapter_index,
        chapter.title.strip().casefold(),
        scene.scene_index,
        span_index,
    )


def _source_span_index_within_scene(session: Session, span: SourceSpan) -> int:
    if span.scene_id is None:
        return 0
    spans = list(
        session.scalars(
            select(SourceSpan)
            .where(SourceSpan.view_id == span.view_id)
            .where(SourceSpan.scene_id == span.scene_id)
            .order_by(SourceSpan.start_offset, SourceSpan.id)
        )
    )
    for index, existing in enumerate(spans):
        if existing.id == span.id:
            return index
    return 0


def _same_ref_set(
    first: list[dict[str, object]],
    second: list[dict[str, object]],
) -> bool:
    if len(first) != len(second):
        return False
    return all(any(refs_equivalent(left, right) for right in second) for left in first)


def _candidate_cause_summary(candidate: StoryEventCandidate) -> str | None:
    value = candidate.state_change.get("cause_summary")
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:2000]


def _ensure_fact(
    session: Session,
    job: JobRecord,
    story_schema: EffectiveStorySchema,
    *,
    subject_ref: dict[str, object],
    predicate: str,
    object_ref: dict[str, object],
    evidence_span_ids: list[str],
    source_scope: str,
    event_id: UUID | None,
    valid_from_scene_id: UUID | None = None,
) -> int:
    project_id = job.project_id
    project_evidence_span_ids = _source_span_ids_for_project(
        session,
        [str(span_id) for span_id in evidence_span_ids],
        project_id,
    )
    if not project_evidence_span_ids:
        _audit(
            session,
            job,
            "story.fact_evidence_rejected",
            {
                "predicate": predicate,
                "subject_ref": subject_ref,
                "object_ref": object_ref,
                "source_span_ids": [],
                "reason": "no_same_project_source_span_evidence",
            },
        )
        return 0

    schema_rejection = validate_fact_against_story_schema(
        story_schema,
        predicate=predicate,
        subject_ref=subject_ref,
        object_ref=object_ref,
    )
    if schema_rejection is not None:
        _audit(
            session,
            job,
            "story.fact_relation_rejected",
            {
                "skipped": schema_rejection.skipped,
                "predicate": predicate,
                "subject_ref": subject_ref,
                "object_ref": object_ref,
                "source_span_ids": project_evidence_span_ids,
                "schema_pack_versions": list(story_schema.source_pack_versions),
                **schema_rejection.details,
            },
        )
        return 0

    existing = find_matching_fact(
        session,
        project_id=project_id,
        subject_ref=subject_ref,
        predicate=predicate,
        object_ref=object_ref,
    )
    if existing is not None:
        if existing.source_scope != source_scope:
            scoped_existing = _find_matching_fact_with_source_scope(
                session,
                project_id=project_id,
                subject_ref=subject_ref,
                predicate=predicate,
                object_ref=object_ref,
                source_scope=source_scope,
            )
            if scoped_existing is not None:
                _merge_fact_evidence_with_log(
                    session,
                    job,
                    fact=scoped_existing,
                    evidence_span_ids=project_evidence_span_ids,
                    event_id=event_id,
                )
                return 0
        else:
            _merge_fact_evidence_with_log(
                session,
                job,
                fact=existing,
                evidence_span_ids=project_evidence_span_ids,
                event_id=event_id,
            )
            return 0

    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project_id,
        subject_ref=subject_ref,
        predicate=predicate,
        object_ref=object_ref,
        fact_status="proposed",
        valid_from_scene_id=valid_from_scene_id,
        evidence_span_ids=project_evidence_span_ids,
        confidence=0.82,
        source_scope=source_scope,
    )
    session.add(fact)
    session.flush()
    session.add(
        EvidenceLogEntry(
            id=uuid4(),
            project_id=project_id,
            log_type="event_fact_derived",
            target_ref={"type": "fact_assertion", "id": str(fact.id)},
            fact_id=fact.id,
            event_id=event_id,
            source_span_ids=project_evidence_span_ids,
            log_status="written",
        )
    )
    return 1


def _merge_fact_evidence_with_log(
    session: Session,
    job: JobRecord,
    *,
    fact: FactAssertionRecord,
    evidence_span_ids: list[str],
    event_id: UUID | None,
) -> None:
    existing_span_ids = _source_span_ids_for_project(
        session,
        [str(span_id) for span_id in fact.evidence_span_ids],
        job.project_id,
    )
    new_span_ids = _source_span_ids_for_project(
        session,
        [str(span_id) for span_id in evidence_span_ids],
        job.project_id,
    )
    merged_span_ids = _merge_unique(existing_span_ids, new_span_ids)
    evidence_added = any(span_id not in existing_span_ids for span_id in new_span_ids)
    if merged_span_ids != fact.evidence_span_ids:
        fact.evidence_span_ids = merged_span_ids
    if (
        new_span_ids
        and evidence_added
        and not evidence_log_exists(
            session,
            fact_id=fact.id,
            source_span_ids=new_span_ids,
        )
    ):
        session.add(
            EvidenceLogEntry(
                id=uuid4(),
                project_id=job.project_id,
                log_type="event_fact_evidence_added",
                target_ref={"type": "fact_assertion", "id": str(fact.id)},
                fact_id=fact.id,
                event_id=event_id,
                source_span_ids=new_span_ids,
                log_status="written",
            )
        )


def _find_matching_fact_with_source_scope(
    session: Session,
    *,
    project_id: UUID,
    subject_ref: dict[str, object],
    predicate: str,
    object_ref: dict[str, object],
    source_scope: str,
) -> FactAssertionRecord | None:
    for fact in session.scalars(
        select(FactAssertionRecord)
        .where(FactAssertionRecord.project_id == project_id)
        .where(FactAssertionRecord.predicate == predicate)
        .where(FactAssertionRecord.source_scope == source_scope)
        .order_by(FactAssertionRecord.created_at, FactAssertionRecord.id)
    ):
        if refs_equivalent(fact.subject_ref, subject_ref) and refs_equivalent(
            fact.object_ref,
            object_ref,
        ):
            return fact
    return None


def _find_conflicting_canon_fact(
    session: Session,
    fact: FactAssertionRecord,
) -> FactAssertionRecord | None:
    if fact.predicate not in EXCLUSIVE_STATE_PREDICATES:
        return None
    for existing in session.scalars(
        select(FactAssertionRecord)
        .where(FactAssertionRecord.project_id == fact.project_id)
        .where(FactAssertionRecord.fact_status == "canon")
        .where(FactAssertionRecord.predicate == fact.predicate)
    ):
        if (
            existing.id != fact.id
            and refs_equivalent(existing.subject_ref, fact.subject_ref)
            and not refs_equivalent(existing.object_ref, fact.object_ref)
        ):
            return existing
    return None


def _find_source_scope_conflicting_fact(
    session: Session,
    fact: FactAssertionRecord,
) -> FactAssertionRecord | None:
    for existing in session.scalars(
        select(FactAssertionRecord)
        .where(FactAssertionRecord.project_id == fact.project_id)
        .where(FactAssertionRecord.predicate == fact.predicate)
        .where(FactAssertionRecord.id != fact.id)
        .order_by(FactAssertionRecord.created_at, FactAssertionRecord.id)
    ):
        if (
            existing.source_scope != fact.source_scope
            and refs_equivalent(existing.subject_ref, fact.subject_ref)
            and refs_equivalent(existing.object_ref, fact.object_ref)
        ):
            return existing
    return None


def _fact_source_scope_requires_review(
    fact: FactAssertionRecord,
    source_scope_conflict: FactAssertionRecord | None,
) -> bool:
    return fact.source_scope in REVIEW_REQUIRED_SOURCE_SCOPES or source_scope_conflict is not None


def _author_fact_replaces_low_authority_duplicate(
    fact: FactAssertionRecord,
    source_scope_conflict: FactAssertionRecord | None,
) -> bool:
    return (
        source_scope_conflict is not None
        and fact.source_scope in AUTHOR_BACKED_CANON_SOURCE_SCOPES
        and source_scope_conflict.source_scope in AUTHOR_REPLACEABLE_LOW_AUTHORITY_SCOPES
        and source_scope_conflict.fact_status in {"proposed", "disputed"}
        and _same_fact_assertion(fact, source_scope_conflict)
    )


def _supersede_low_authority_scope_reviews(
    session: Session,
    *,
    replaced_fact: FactAssertionRecord,
    replacement_fact: FactAssertionRecord,
    replacement_span_id: UUID,
) -> list[UUID]:
    superseded_review_ids: list[UUID] = []
    replacement_ref = {"type": "source_span", "id": str(replacement_span_id)}
    for review in session.scalars(
        select(ReviewItemRecord)
        .where(ReviewItemRecord.project_id == replaced_fact.project_id)
        .where(ReviewItemRecord.review_type == "source_scope_conflict")
        .where(ReviewItemRecord.status == "open")
        .order_by(ReviewItemRecord.created_at, ReviewItemRecord.id)
    ):
        if review.affected_refs.get("fact_id") != str(replaced_fact.id):
            continue
        review.status = "superseded"
        review.resolution = "supersede"
        review.resolved_at = datetime.now(UTC)
        review.affected_refs = {
            **review.affected_refs,
            "replacement_source_span_ids": [str(replacement_span_id)],
            "replacement_fact_id": str(replacement_fact.id),
        }
        review.new_evidence = {
            **review.new_evidence,
            "resolution_replacement_refs": [replacement_ref],
        }
        review.side_effects = {
            **review.side_effects,
            "superseded_by_fact_id": str(replacement_fact.id),
            "source_authority_resolution": _source_authority_resolution_label(replaced_fact),
        }
        superseded_review_ids.append(review.id)
    return superseded_review_ids


def _source_authority_resolution_label(replaced_fact: FactAssertionRecord) -> str:
    if replaced_fact.source_scope == "model_suggestion":
        return "author_evidence_replaced_model_suggestion"
    return f"author_evidence_replaced_lower_authority_{replaced_fact.source_scope}"


def _is_temporal_state_progression(
    session: Session,
    fact: FactAssertionRecord,
    conflict: FactAssertionRecord,
) -> bool:
    if fact.predicate not in EXCLUSIVE_STATE_PREDICATES:
        return False
    new_key = _fact_scene_sort_key(session, fact)
    existing_key = _fact_scene_sort_key(session, conflict)
    if new_key is None or existing_key is None:
        return False
    return new_key > existing_key


def _fact_scene_sort_key(
    session: Session,
    fact: FactAssertionRecord,
) -> tuple[int, int, int, str] | None:
    if fact.valid_from_scene_id is None:
        return None
    scene = session.get(StoryScene, fact.valid_from_scene_id)
    if scene is None:
        return None
    chapter = session.get(StoryChapter, scene.chapter_id)
    if chapter is None:
        return None
    return (
        chapter.chapter_index,
        scene.scene_index,
        scene.start_offset,
        str(scene.id),
    )


def _derive_scene_appearance_facts(
    session: Session,
    job: JobRecord,
    span: SourceSpan,
    source_scope: str,
    story_schema: EffectiveStorySchema,
) -> int:
    scene_ref = _scene_ref_for_span(span)
    if scene_ref is None:
        return 0
    created = 0
    mentions = list(
        session.scalars(
            select(StoryMention)
            .where(StoryMention.span_id == span.id)
            .order_by(StoryMention.created_at, StoryMention.id)
        )
    )
    for mention in mentions:
        if not _is_story_entity_mention(mention, story_schema):
            continue
        created += _ensure_fact(
            session,
            job,
            story_schema,
            subject_ref=_ref_for_mention(mention),
            predicate="appears_in",
            object_ref=scene_ref,
            evidence_span_ids=[str(span.id)],
            source_scope=source_scope,
            event_id=None,
            valid_from_scene_id=span.scene_id,
        )
    return created


def _create_review_item(
    session: Session,
    fact: FactAssertionRecord,
    span_id: UUID,
    conflict: FactAssertionRecord | None,
) -> None:
    if _review_exists_for_fact(session, fact.id):
        return
    new_source_span_ids = _source_span_ids_for_project(session, [str(span_id)], fact.project_id)
    if not new_source_span_ids:
        return
    review_type = _review_type_for_fact(fact, conflict)
    existing_evidence: dict[str, object] = {}
    if conflict is not None:
        existing_evidence = {
            "fact_id": str(conflict.id),
            "source_span_ids": _source_span_ids_for_project(
                session,
                [str(item) for item in conflict.evidence_span_ids],
                fact.project_id,
            ),
        }
        if conflict.source_scope != fact.source_scope:
            existing_evidence["source_scope"] = conflict.source_scope
    new_evidence: dict[str, object] = {"source_span_ids": new_source_span_ids}
    if review_type == "source_scope_conflict":
        new_evidence["source_scope"] = fact.source_scope
    session.add(
        ReviewItemRecord(
            id=uuid4(),
            project_id=fact.project_id,
            review_type=review_type,
            severity="medium",
            status="open",
            summary=f"{fact.predicate} requires author review before canon promotion.",
            affected_refs={"fact_id": str(fact.id)},
            new_evidence=new_evidence,
            existing_evidence=existing_evidence,
            suggested_actions=_suggested_actions_for_fact_review(review_type),
            default_action="review",
        )
    )


def _suggested_actions_for_fact_review(review_type: str) -> list[dict[str, str]]:
    if review_type == "source_scope_conflict":
        return [
            {"resolution": "reject"},
            {"resolution": "accepted_as_change"},
            {"resolution": "fixed_by_text_edit"},
        ]
    return [
        {"resolution": "accept"},
        {"resolution": "reject"},
        {"resolution": "accepted_as_change"},
    ]


def _review_exists_for_fact(session: Session, fact_id: UUID) -> bool:
    return (
        session.scalars(
            select(ReviewItemRecord).where(
                ReviewItemRecord.affected_refs == {"fact_id": str(fact_id)}
            )
        ).first()
        is not None
    )


def _upsert_memory_page(
    session: Session,
    project_id: UUID,
    fact: FactAssertionRecord,
) -> MemoryPage:
    evidence_span_ids = _source_span_ids_for_project(session, fact.evidence_span_ids, project_id)
    if not evidence_span_ids:
        raise TerminalJobError("Canon fact promotion requires same-project SourceSpan evidence.")
    if evidence_span_ids != fact.evidence_span_ids:
        fact.evidence_span_ids = evidence_span_ids
    page = session.scalars(
        select(MemoryPage)
        .where(MemoryPage.project_id == project_id)
        .where(MemoryPage.target_ref == fact.subject_ref)
    ).first()
    fact_entry = {
        "fact_id": str(fact.id),
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "evidence_span_ids": evidence_span_ids,
    }
    source_refs = _source_refs_for_fact_page(
        session,
        project_id,
        [],
        evidence_span_ids,
    )
    if page is None:
        page = MemoryPage(
            id=uuid4(),
            project_id=project_id,
            page_type=str(fact.subject_ref.get("type", "lore")),
            target_ref=fact.subject_ref,
            title=str(fact.subject_ref.get("label") or fact.subject_ref.get("id")),
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
        session.add(page)
        session.flush()
        return page
    facts = list(page.current_canon.get("facts", []))
    if not any(entry.get("fact_id") == str(fact.id) for entry in facts):
        facts.append(fact_entry)
    else:
        facts = [fact_entry if entry.get("fact_id") == str(fact.id) else entry for entry in facts]
    page.current_canon = {"facts": facts}
    page.source_refs = _source_refs_for_fact_page(
        session,
        project_id,
        list(page.source_refs),
        evidence_span_ids,
    )
    page.current_canon = {"facts": facts}
    session.flush()
    return page


def _source_refs_for_fact_page(
    session: Session,
    project_id: UUID,
    existing_refs: list[dict[str, object]],
    evidence_span_ids: list[str],
) -> list[dict[str, object]]:
    preserved_refs = [dict(ref) for ref in existing_refs if ref.get("type") != "source_span"]
    existing_span_ids = [
        str(ref.get("id"))
        for ref in existing_refs
        if ref.get("type") == "source_span" and ref.get("id") is not None
    ]
    span_ids = _source_span_ids_for_project(
        session,
        _merge_unique(existing_span_ids, evidence_span_ids),
        project_id,
    )
    source_refs: list[dict[str, object]] = preserved_refs + [
        cast(dict[str, object], {"type": "source_span", "id": span_id}) for span_id in span_ids
    ]
    deduped: list[dict[str, object]] = []
    for ref in source_refs:
        if not any(refs_equivalent(existing, ref) for existing in deduped):
            deduped.append(ref)
    return deduped


def _queue_agency_profile_rewrite_if_needed(
    session: Session,
    job: JobRecord,
    span: SourceSpan,
    fact: FactAssertionRecord,
    page: MemoryPage,
) -> None:
    if fact.predicate not in AGENCY_PROFILE_FACT_PREDICATES:
        return
    idempotency_key = f"memory-page:{page.id}:agency-profile:{span.id}"
    existing = session.scalars(
        select(JobRecord)
        .where(JobRecord.project_id == job.project_id)
        .where(JobRecord.job_type == "rewrite_memory_page")
        .where(JobRecord.idempotency_key == idempotency_key)
    ).first()
    if existing is not None:
        return
    session.add(
        JobRecord(
            id=uuid4(),
            project_id=job.project_id,
            job_type="rewrite_memory_page",
            status="queued",
            idempotency_key=idempotency_key,
            payload={
                "step": "rewrite_memory_page",
                "pipeline_version": PIPELINE_VERSION,
                "memory_page_id": str(page.id),
                "source_span_id": str(span.id),
                "fact_id": str(fact.id),
                "reason": "agency_profile_fact_promoted",
            },
        )
    )
    page.canon_status = "current"


def _audit(
    session: Session,
    job: JobRecord,
    event_type: str,
    decision: dict[str, object],
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            project_id=job.project_id,
            request_id=f"job:{job.id}",
            actor_id=None,
            event_type=event_type,
            subject_ref={"type": "job_record", "id": str(job.id)},
            decision=decision,
        )
    )


def _alias_type(mention: StoryMention) -> str:
    if mention.mention_type == "pronoun":
        return "pronoun"
    return "name"


def _alias_scope(mention: StoryMention) -> AliasScope:
    if mention.mention_type == "pronoun" or mention.confidence < 0.45:
        return AliasScope.SCENE_LOCAL
    return AliasScope.GLOBAL


def _is_actor(mention: StoryMention) -> bool:
    return mention.mention_type in {"character", "faction"}


def _is_story_entity_mention(
    mention: StoryMention,
    story_schema: EffectiveStorySchema,
) -> bool:
    return mention.mention_type in story_schema.entity_types


def _ref_for_mention(mention: StoryMention) -> dict[str, object]:
    slug = _slug(mention.raw_text)
    if mention.resolved_entity_id is not None:
        return {
            "type": mention.mention_type,
            "id": str(mention.resolved_entity_id),
            "label": mention.raw_text,
            "canonical_entity_id": str(mention.resolved_entity_id),
            "slug": slug,
        }
    return {
        "type": mention.mention_type,
        "id": slug,
        "label": mention.raw_text,
        "slug": slug,
        "mention_id": str(mention.id),
    }


def _scene_ref_for_span(span: SourceSpan) -> dict[str, object] | None:
    if span.scene_id is None:
        return None
    ref: dict[str, object] = {
        "type": "scene",
        "id": str(span.scene_id),
        "label": f"scene:{span.scene_id}",
    }
    if span.chapter_id is not None:
        ref["chapter_id"] = str(span.chapter_id)
    return ref


def _location_ref_for_span(session: Session, span: SourceSpan) -> dict[str, object] | None:
    location = session.scalars(
        select(StoryMention)
        .where(StoryMention.span_id == span.id)
        .where(StoryMention.mention_type == "location")
        .order_by(StoryMention.created_at, StoryMention.id)
    ).first()
    if location is None:
        return None
    return _ref_for_mention(location)


def _summary(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0][:500]


def _event_summary(text: str, cue: object) -> str:
    if not isinstance(cue, str) or not cue.strip():
        return _summary(text)
    normalized_cue = cue.casefold()
    for sentence in _sentence_fragments(text):
        if normalized_cue in sentence.casefold():
            return sentence[:500]
    return _summary(text)


def _sentence_fragments(text: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?。！？]+[.!?。！？]?", text.strip())
        if match.group(0).strip()
    ]


def _event_title(summary: str) -> str:
    return summary.rstrip(".!?。！？")[:120]


def _review_type_for_fact(
    fact: FactAssertionRecord,
    conflict: FactAssertionRecord | None = None,
) -> str:
    if fact.source_scope in REVIEW_REQUIRED_SOURCE_SCOPES or (
        conflict is not None
        and fact.source_scope != conflict.source_scope
        and _same_fact_assertion(fact, conflict)
    ):
        return "source_scope_conflict"
    if fact.predicate in {"owns", "located_in", "occurred_at", "involves_object"}:
        return "object_state_conflict"
    if fact.predicate in {
        "knows",
        "does_not_know",
        "suspects",
        "false_belief",
        "misunderstands",
    }:
        return "knowledge_conflict"
    return "canon_conflict"


def _same_fact_assertion(first: FactAssertionRecord, second: FactAssertionRecord) -> bool:
    return (
        first.predicate == second.predicate
        and refs_equivalent(first.subject_ref, second.subject_ref)
        and refs_equivalent(first.object_ref, second.object_ref)
    )


def _transfer_owner_ref(event: StoryCanonicalEvent) -> dict[str, object] | None:
    if event.event_type != "object_transfer" or not event.participants or not event.objects:
        return None
    for participant in event.participants:
        if participant.get("role") == "recipient":
            return dict(participant)
    return None


def _merge_unique(first: list[str], second: list[str]) -> list[str]:
    merged = list(first)
    for item in second:
        if item not in merged:
            merged.append(item)
    return merged


def _slug(value: str) -> str:
    slug = re.sub(r"[^\w]+", "-", value.casefold()).replace("_", "-").strip("-")
    return slug or "unknown"


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
