from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from sextant.domain.fact_schema import validate_fact_against_story_schema
from sextant.domain.story_schema import AGENCY_PROFILE_RELATIONS, EffectiveStorySchema
from sextant.infra.db.models import (
    AuditEvent,
    CharacterKnowledge,
    FactAssertionRecord,
    GraphProjectionEdge,
    GraphProjectionRun,
    JobRecord,
    RawSource,
    ReviewItemRecord,
    SourceSpan,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
)
from sextant.infra.story_schema import load_effective_story_schema

CANONICAL_EVENT_GRAPH_STATUSES = ("canon", "external_canon", "author_note")
FACT_GRAPH_EDGE_STATUSES = {
    "canon": "canon",
    "proposed": "proposed",
    "inferred": "inferred",
    "disputed": "disputed",
    "contradicted": "contradicted",
    "outdated": "outdated",
}
GRAPH_EXCLUDED_FACT_RELATIONS = frozenset(AGENCY_PROFILE_RELATIONS)


@dataclass(frozen=True, slots=True)
class GraphProjectionResult:
    run_id: UUID
    created_edge_count: int
    source_state_hash: str


@dataclass(frozen=True, slots=True)
class ProjectedGraphEdge:
    source_ref: dict[str, Any]
    subject_ref: dict[str, Any]
    relation: str
    target_ref: dict[str, Any]
    edge_status: str
    evidence_refs: list[dict[str, str]]


class GraphProjectionRebuildHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        result = rebuild_graph_projection(session, project_id=job.project_id)
        session.add(
            AuditEvent(
                id=uuid4(),
                project_id=job.project_id,
                request_id=f"job:{job.id}",
                actor_id=None,
                event_type="graph_projection.rebuilt",
                subject_ref={"type": "job_record", "id": str(job.id)},
                decision={
                    "run_id": str(result.run_id),
                    "projection_scope": job.payload.get("projection_scope", "project"),
                    "source_state_hash": result.source_state_hash,
                    "requested_source_state_hash": job.payload.get("source_state_hash"),
                    "created_edge_count": result.created_edge_count,
                },
            )
        )
        session.flush()


def rebuild_graph_projection(session: Session, *, project_id: UUID) -> GraphProjectionResult:
    story_schema = load_effective_story_schema(session, project_id)
    facts = list(
        session.scalars(
            select(FactAssertionRecord)
            .where(FactAssertionRecord.project_id == project_id)
            .where(FactAssertionRecord.fact_status.in_(tuple(FACT_GRAPH_EDGE_STATUSES)))
            .order_by(FactAssertionRecord.id)
        )
    )
    events = list(
        session.scalars(
            select(StoryCanonicalEvent)
            .where(StoryCanonicalEvent.project_id == project_id)
            .where(StoryCanonicalEvent.event_status.in_(CANONICAL_EVENT_GRAPH_STATUSES))
            .order_by(StoryCanonicalEvent.created_at, StoryCanonicalEvent.id)
        )
    )
    character_knowledge = list(
        session.scalars(
            select(CharacterKnowledge)
            .where(CharacterKnowledge.project_id == project_id)
            .where(CharacterKnowledge.status == "active")
            .order_by(CharacterKnowledge.created_at, CharacterKnowledge.id)
        )
    )
    reviews = list(
        session.scalars(
            select(ReviewItemRecord)
            .where(ReviewItemRecord.project_id == project_id)
            .where(ReviewItemRecord.status == "open")
            .order_by(ReviewItemRecord.created_at, ReviewItemRecord.id)
        )
    )
    projected_fact_edges: list[ProjectedGraphEdge] = []
    for fact in facts:
        edge = _project_fact_edge(session, fact, story_schema)
        if edge is not None:
            projected_fact_edges.append(edge)
    projected_edges = [
        *projected_fact_edges,
        *_project_canonical_event_edges(session, events, story_schema),
        *_project_character_knowledge_edges(session, character_knowledge, story_schema),
        *_project_review_contradiction_edges(session, reviews, story_schema),
    ]
    source_state_hash = _hash_projection_state(
        session,
        facts,
        events,
        character_knowledge,
        reviews,
    )
    run_id = uuid4()
    run = GraphProjectionRun(
        id=run_id,
        project_id=project_id,
        projection_scope="project",
        source_state_hash=source_state_hash,
        created_edge_count=len(projected_edges),
    )

    session.execute(delete(GraphProjectionEdge).where(GraphProjectionEdge.project_id == project_id))
    session.add(run)
    session.flush()
    for edge in projected_edges:
        session.add(
            GraphProjectionEdge(
                id=uuid4(),
                project_id=project_id,
                run_id=run_id,
                source_ref=edge.source_ref,
                subject_ref=edge.subject_ref,
                relation=edge.relation,
                target_ref=edge.target_ref,
                edge_status=edge.edge_status,
                evidence_refs=edge.evidence_refs,
            )
        )
    session.flush()
    return GraphProjectionResult(
        run_id=run_id,
        created_edge_count=len(projected_edges),
        source_state_hash=source_state_hash,
    )


def _project_fact_edge(
    session: Session,
    fact: FactAssertionRecord,
    story_schema: EffectiveStorySchema,
) -> ProjectedGraphEdge | None:
    if fact.predicate in GRAPH_EXCLUDED_FACT_RELATIONS:
        return None
    evidence_refs = _same_project_evidence_refs(session, fact.evidence_span_ids, fact.project_id)
    if not evidence_refs:
        return None
    relation = fact.predicate if fact.predicate in story_schema.relations else "related_to"
    return ProjectedGraphEdge(
        source_ref={"type": "fact_assertion", "id": str(fact.id)},
        subject_ref=fact.subject_ref,
        relation=relation,
        target_ref=fact.object_ref,
        edge_status=FACT_GRAPH_EDGE_STATUSES[fact.fact_status],
        evidence_refs=evidence_refs,
    )


def _project_canonical_event_edges(
    session: Session,
    events: list[StoryCanonicalEvent],
    story_schema: EffectiveStorySchema,
) -> list[ProjectedGraphEdge]:
    edges: list[ProjectedGraphEdge] = []
    for event in events:
        event_ref = _event_ref(event)
        for participant in event.participants:
            edge = _project_event_edge(
                session,
                event,
                story_schema,
                subject_ref=dict(participant),
                relation="present_at",
                target_ref=event_ref,
            )
            if edge is not None:
                edges.append(edge)
        location_ref = _location_ref(session, event)
        if location_ref is not None:
            edge = _project_event_edge(
                session,
                event,
                story_schema,
                subject_ref=event_ref,
                relation="occurred_at",
                target_ref=location_ref,
            )
            if edge is not None:
                edges.append(edge)
        for obj in event.objects:
            edge = _project_event_edge(
                session,
                event,
                story_schema,
                subject_ref=event_ref,
                relation="involves_object",
                target_ref=dict(obj),
            )
            if edge is not None:
                edges.append(edge)
    return edges


def _project_event_edge(
    session: Session,
    event: StoryCanonicalEvent,
    story_schema: EffectiveStorySchema,
    *,
    subject_ref: dict[str, Any],
    relation: str,
    target_ref: dict[str, Any],
) -> ProjectedGraphEdge | None:
    evidence_refs = _same_project_evidence_refs(session, event.evidence_span_ids, event.project_id)
    if not evidence_refs:
        return None
    rejection = validate_fact_against_story_schema(
        story_schema,
        predicate=relation,
        subject_ref=subject_ref,
        object_ref=target_ref,
    )
    if rejection is not None:
        return None
    return ProjectedGraphEdge(
        source_ref={"type": "canonical_event", "id": str(event.id)},
        subject_ref=subject_ref,
        relation=relation,
        target_ref=target_ref,
        edge_status="canon",
        evidence_refs=evidence_refs,
    )


def _project_character_knowledge_edges(
    session: Session,
    knowledge_rows: list[CharacterKnowledge],
    story_schema: EffectiveStorySchema,
) -> list[ProjectedGraphEdge]:
    edges: list[ProjectedGraphEdge] = []
    for knowledge in knowledge_rows:
        edge = _project_character_knowledge_edge(session, knowledge, story_schema)
        if edge is not None:
            edges.append(edge)
    return edges


def _project_character_knowledge_edge(
    session: Session,
    knowledge: CharacterKnowledge,
    story_schema: EffectiveStorySchema,
) -> ProjectedGraphEdge | None:
    if not _source_span_belongs_to_project(
        session, knowledge.evidence_span_id, knowledge.project_id
    ):
        return None
    target_ref = dict(knowledge.knows_ref)
    if target_ref.get("type") == "fact_assertion":
        return None
    relation = "does_not_know" if knowledge.certainty == "does_not_know" else "knows"
    subject_ref = _character_knowledge_subject_ref(session, knowledge)
    rejection = validate_fact_against_story_schema(
        story_schema,
        predicate=relation,
        subject_ref=subject_ref,
        object_ref=target_ref,
    )
    if rejection is not None:
        return None
    return ProjectedGraphEdge(
        source_ref={"type": "character_knowledge", "id": str(knowledge.id)},
        subject_ref=subject_ref,
        relation=relation,
        target_ref=target_ref,
        edge_status="canon",
        evidence_refs=_evidence_refs([str(knowledge.evidence_span_id)]),
    )


def _source_span_belongs_to_project(session: Session, span_id: UUID, project_id: UUID) -> bool:
    span = session.get(SourceSpan, span_id)
    if span is None:
        return False
    raw_source = session.get(RawSource, span.source_id)
    return raw_source is not None and raw_source.project_id == project_id


def _character_knowledge_subject_ref(
    session: Session, knowledge: CharacterKnowledge
) -> dict[str, Any]:
    entity = session.get(StoryCanonicalEntity, knowledge.character_id)
    if entity is None or entity.project_id != knowledge.project_id:
        return {"type": "character", "id": str(knowledge.character_id)}
    return {
        "type": entity.entity_type,
        "id": str(entity.id),
        "label": entity.display_name,
        "canonical_entity_id": str(entity.id),
    }


def _project_review_contradiction_edges(
    session: Session,
    reviews: list[ReviewItemRecord],
    story_schema: EffectiveStorySchema,
) -> list[ProjectedGraphEdge]:
    edges: list[ProjectedGraphEdge] = []
    for review in reviews:
        evidence_refs = _review_evidence_refs(session, review)
        if not evidence_refs:
            continue
        target_ref = _review_contradiction_target_ref(session, review)
        if target_ref is None:
            continue
        subject_ref = _review_item_ref(review)
        rejection = validate_fact_against_story_schema(
            story_schema,
            predicate="contradicts",
            subject_ref=subject_ref,
            object_ref=target_ref,
        )
        if rejection is not None:
            continue
        edges.append(
            ProjectedGraphEdge(
                source_ref={"type": "review_item", "id": str(review.id)},
                subject_ref=subject_ref,
                relation="contradicts",
                target_ref=target_ref,
                edge_status="disputed",
                evidence_refs=evidence_refs,
            )
        )
    return edges


def _review_contradiction_target_ref(
    session: Session, review: ReviewItemRecord
) -> dict[str, Any] | None:
    fact_id = _uuid_from_payload(review.existing_evidence, "fact_id")
    if fact_id is not None:
        fact = session.get(FactAssertionRecord, fact_id)
        if fact is not None and fact.project_id == review.project_id:
            return {
                "type": "fact_assertion",
                "id": str(fact.id),
                "predicate": fact.predicate,
            }

    event_id = _uuid_from_payload(review.existing_evidence, "event_id")
    if event_id is not None:
        event = session.get(StoryCanonicalEvent, event_id)
        if event is not None and event.project_id == review.project_id:
            return _event_ref(event)

    return None


def _review_item_ref(review: ReviewItemRecord) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "type": "review_item",
        "id": str(review.id),
        "review_type": review.review_type,
        "severity": review.severity,
        "status": review.status,
    }
    if fact_id := review.affected_refs.get("fact_id"):
        ref["affected_fact_id"] = str(fact_id)
    if event_id := review.affected_refs.get("event_id"):
        ref["affected_event_id"] = str(event_id)
    return ref


def _review_evidence_refs(session: Session, review: ReviewItemRecord) -> list[dict[str, str]]:
    span_ids: list[str] = []
    for evidence in (review.new_evidence, review.existing_evidence):
        values = evidence.get("source_span_ids", [])
        if not isinstance(values, list):
            continue
        for value in values:
            span_id = str(value)
            if span_id not in span_ids:
                span_ids.append(span_id)
    return _same_project_evidence_refs(session, span_ids, review.project_id)


def _same_project_evidence_refs(
    session: Session, span_ids: list[str], project_id: UUID
) -> list[dict[str, str]]:
    return _evidence_refs(_same_project_source_span_ids(session, span_ids, project_id))


def _same_project_source_span_ids(
    session: Session, span_ids: list[str], project_id: UUID
) -> list[str]:
    valid_span_ids: list[str] = []
    for value in span_ids:
        try:
            span_id = UUID(str(value))
        except ValueError:
            continue
        if _source_span_belongs_to_project(session, span_id, project_id):
            span_ref = str(span_id)
            if span_ref not in valid_span_ids:
                valid_span_ids.append(span_ref)
    return valid_span_ids


def _uuid_from_payload(payload: dict[str, Any], key: str) -> UUID | None:
    value = payload.get(key)
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _event_ref(event: StoryCanonicalEvent) -> dict[str, Any]:
    return {
        "type": "event",
        "id": str(event.id),
        "label": event.title,
        "event_type": event.event_type,
    }


def _location_ref(session: Session, event: StoryCanonicalEvent) -> dict[str, Any] | None:
    if event.location_entity_id is None:
        return None
    entity = session.get(StoryCanonicalEntity, event.location_entity_id)
    if entity is None or entity.project_id != event.project_id:
        return {"type": "location", "id": str(event.location_entity_id)}
    return {
        "type": entity.entity_type,
        "id": str(entity.id),
        "label": entity.display_name,
    }


def _evidence_refs(span_ids: list[str]) -> list[dict[str, str]]:
    return [{"type": "source_span", "id": span_id} for span_id in span_ids]


def _hash_projection_state(
    session: Session,
    facts: list[FactAssertionRecord],
    events: list[StoryCanonicalEvent],
    character_knowledge: list[CharacterKnowledge],
    reviews: list[ReviewItemRecord],
) -> str:
    payload = {
        "facts": [
            {
                "id": str(fact.id),
                "subject_ref": fact.subject_ref,
                "predicate": fact.predicate,
                "object_ref": fact.object_ref,
                "status": fact.fact_status,
                "evidence_span_ids": _same_project_source_span_ids(
                    session,
                    fact.evidence_span_ids,
                    fact.project_id,
                ),
            }
            for fact in facts
        ],
        "events": [
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "event_status": event.event_status,
                "participants": event.participants,
                "objects": event.objects,
                "location_entity_id": (
                    str(event.location_entity_id) if event.location_entity_id is not None else None
                ),
                "evidence_span_ids": _same_project_source_span_ids(
                    session,
                    event.evidence_span_ids,
                    event.project_id,
                ),
            }
            for event in events
        ],
        "character_knowledge": [
            {
                "id": str(knowledge.id),
                "character_id": str(knowledge.character_id),
                "knows_ref": knowledge.knows_ref,
                "evidence_span_id": (
                    str(knowledge.evidence_span_id)
                    if _source_span_belongs_to_project(
                        session,
                        knowledge.evidence_span_id,
                        knowledge.project_id,
                    )
                    else None
                ),
                "certainty": knowledge.certainty,
                "status": knowledge.status,
            }
            for knowledge in character_knowledge
        ],
        "reviews": [
            {
                "id": str(review.id),
                "review_type": review.review_type,
                "severity": review.severity,
                "status": review.status,
                "resolution": review.resolution,
                "affected_refs": review.affected_refs,
                "new_evidence": _projection_hash_review_evidence(
                    session,
                    review.new_evidence,
                    review.project_id,
                ),
                "existing_evidence": _projection_hash_review_evidence(
                    session,
                    review.existing_evidence,
                    review.project_id,
                ),
            }
            for review in reviews
        ],
    }
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _projection_hash_review_evidence(
    session: Session,
    evidence: dict[str, Any],
    project_id: UUID,
) -> dict[str, Any]:
    normalized = dict(evidence)
    values = evidence.get("source_span_ids", [])
    normalized["source_span_ids"] = (
        _same_project_source_span_ids(
            session,
            [str(value) for value in values],
            project_id,
        )
        if isinstance(values, list)
        else []
    )
    return normalized
