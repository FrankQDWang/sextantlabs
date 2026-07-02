from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from sextant.infra.db.models import (
    AuditEvent,
    FactAssertionRecord,
    JobRecord,
    MemoryPage,
    RawSource,
    ReviewItemRecord,
    SourceSpan,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
)
from sextant.infra.fact_dedup import refs_equivalent
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.worker import TerminalJobError

APPEARANCE_PREDICATES = {"appears_in", "present_at"}
RELATIONSHIP_PREDICATES = {
    "ally_of",
    "enemy_of",
    "family_of",
    "member_of",
    "related_to",
}
STATE_PREDICATES = {"located_in", "owns"}
EVENT_LOG_STATUSES = ("canon", "external_canon", "author_note")
AGENCY_PROFILE_SCALAR_PREDICATES = {
    "core_desire",
    "immediate_want",
    "fear_or_wound",
    "moral_boundary",
    "secret",
    "contradiction",
    "voice_fingerprint",
    "agency_rule",
    "change_pressure",
}
AGENCY_PROFILE_LIST_PREDICATES = {"relationship_stance"}


class MemoryPageRewriteHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        memory_page_id = _payload_uuid(job, "memory_page_id")
        page = session.get(MemoryPage, memory_page_id)
        if page is None or page.project_id != job.project_id:
            raise TerminalJobError("memory page not found for rewrite job")

        candidate_facts = [
            fact
            for fact in session.query(FactAssertionRecord)
            .filter_by(project_id=job.project_id, fact_status="canon")
            .all()
            if _fact_references_page(fact, page)
        ]
        fact_evidence_span_ids = _fact_evidence_span_id_map(
            session,
            job.project_id,
            candidate_facts,
        )
        facts = [fact for fact in candidate_facts if fact_evidence_span_ids.get(str(fact.id))]
        preserved_open_threads = _preserved_author_open_threads(page)
        state_facts = _state_facts(facts, page, fact_evidence_span_ids)
        agency_profile = _agency_profile(session, facts, page)
        event_current_canon, direct_event_source_events = _event_current_canon(session, page)
        page.current_canon = {
            "facts": [_fact_entry(fact, fact_evidence_span_ids) for fact in facts]
        }
        page.current_canon.update(event_current_canon)
        if state_facts:
            page.current_canon["state_facts"] = state_facts
        if agency_profile:
            page.current_canon["agency_profile"] = agency_profile
        location_events = _location_events(session, page)
        page.appearance_log = _appearance_log(facts, fact_evidence_span_ids)
        event_log, event_source_events = _event_log(
            session,
            facts,
            location_events,
            fact_evidence_span_ids,
        )
        page.event_log = event_log
        page.relationships = _relationships(facts, page, fact_evidence_span_ids)
        page.open_threads = _merge_open_threads(
            _open_threads(session, page, facts),
            preserved_open_threads,
        )
        page.source_refs = _unique_refs(
            page.source_refs
            + [
                {"type": "source_span", "id": span_id}
                for fact in facts
                for span_id in fact_evidence_span_ids[str(fact.id)]
            ]
            + [{"type": "fact_assertion", "id": str(fact.id)} for fact in facts]
            + _event_source_refs(
                session,
                page.project_id,
                event_source_events + direct_event_source_events,
            )
        )
        page.canon_status = "rebuilt"

        projection = rebuild_graph_projection(session, project_id=job.project_id)
        session.add(
            AuditEvent(
                id=uuid4(),
                project_id=job.project_id,
                request_id=f"job:{job.id}",
                actor_id=None,
                event_type="memory_page.rebuilt",
                subject_ref={"type": "memory_page", "id": str(page.id)},
                decision={
                    "canon_fact_count": len(facts),
                    "appearance_log_count": len(page.appearance_log),
                    "event_log_count": len(page.event_log),
                    "event_current_canon_count": len(direct_event_source_events),
                    "location_event_count": len(location_events),
                    "relationship_count": len(page.relationships),
                    "state_fact_count": len(state_facts),
                    "agency_profile_field_count": _agency_profile_field_count(agency_profile),
                    "open_thread_count": len(page.open_threads),
                    "graph_projection_run_id": str(projection.run_id),
                    "graph_edge_count": projection.created_edge_count,
                },
            )
        )


def _payload_uuid(job: JobRecord, key: str) -> UUID:
    value = job.payload.get(key)
    if not isinstance(value, str):
        raise TerminalJobError(f"{key} is required for memory page rewrite")
    try:
        return UUID(value)
    except ValueError as exc:
        raise TerminalJobError(f"{key} must be a UUID") from exc


def _fact_entry(
    fact: FactAssertionRecord,
    fact_evidence_span_ids: dict[str, list[str]],
) -> dict[str, object]:
    return {
        "fact_id": str(fact.id),
        "subject_ref": fact.subject_ref,
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "evidence_span_ids": fact_evidence_span_ids[str(fact.id)],
    }


def _fact_references_page(fact: FactAssertionRecord, page: MemoryPage) -> bool:
    return refs_equivalent(fact.subject_ref, page.target_ref) or refs_equivalent(
        fact.object_ref, page.target_ref
    )


def _appearance_log(
    facts: list[FactAssertionRecord],
    fact_evidence_span_ids: dict[str, list[str]],
) -> list[dict[str, object]]:
    return [
        {
            "fact_id": str(fact.id),
            "predicate": fact.predicate,
            "target_ref": fact.object_ref,
            "evidence_span_ids": fact_evidence_span_ids[str(fact.id)],
        }
        for fact in facts
        if fact.predicate in APPEARANCE_PREDICATES
    ]


def _event_log(
    session: Session,
    facts: list[FactAssertionRecord],
    location_events: list[StoryCanonicalEvent],
    fact_evidence_span_ids: dict[str, list[str]],
) -> tuple[list[dict[str, object]], list[StoryCanonicalEvent]]:
    entries: list[dict[str, object]] = []
    source_events: list[StoryCanonicalEvent] = []
    seen_entries: set[str] = set()
    seen_source_events: set[str] = set()
    for fact in facts:
        event_ref = _event_ref_for_fact(fact)
        if event_ref is None:
            continue
        event_id = event_ref.get("id")
        if not isinstance(event_id, str) or event_id in seen_entries:
            continue
        seen_entries.add(event_id)
        event = _canonical_event(session, event_id)
        if event is None:
            entries.append(
                {
                    "event_id": event_id,
                    "title": event_ref.get("label") or event_id,
                    "event_type": event_ref.get("type", "event"),
                    "summary": None,
                    "evidence_span_ids": fact_evidence_span_ids[str(fact.id)],
                }
            )
            continue
        event_span_ids = _event_evidence_span_ids(session, event.project_id, event)
        if not event_span_ids:
            continue
        entries.append(_event_entry(event, event_span_ids))
        _append_event_source_event(source_events, seen_source_events, event)
    for event in location_events:
        event_id = str(event.id)
        if event_id in seen_entries:
            continue
        seen_entries.add(event_id)
        event_span_ids = _event_evidence_span_ids(session, event.project_id, event)
        if not event_span_ids:
            continue
        entries.append(_event_entry(event, event_span_ids))
        _append_event_source_event(source_events, seen_source_events, event)
    return entries, source_events


def _append_event_source_event(
    source_events: list[StoryCanonicalEvent],
    seen_source_events: set[str],
    event: StoryCanonicalEvent,
) -> None:
    event_id = str(event.id)
    if event_id in seen_source_events:
        return
    seen_source_events.add(event_id)
    source_events.append(event)


def _event_entry(event: StoryCanonicalEvent, evidence_span_ids: list[str]) -> dict[str, object]:
    return {
        "event_id": str(event.id),
        "title": event.title,
        "event_type": event.event_type,
        "summary": event.summary,
        "story_time": event.story_time,
        "evidence_span_ids": evidence_span_ids,
    }


def _event_current_canon(
    session: Session,
    page: MemoryPage,
) -> tuple[dict[str, object], list[StoryCanonicalEvent]]:
    event = _event_page_event(session, page)
    if event is None:
        return {}, []
    event_span_ids = _event_evidence_span_ids(session, page.project_id, event)
    if not event_span_ids:
        return {}, []

    current_canon: dict[str, object] = {
        "event_summary": _event_entry(event, event_span_ids),
        "participants": event.participants,
        "objects": event.objects,
    }
    location_ref = _event_location_ref(session, event)
    if location_ref is not None:
        current_canon["location"] = location_ref
    if event.cause_summary:
        current_canon["cause"] = {
            "summary": event.cause_summary,
            "evidence_span_ids": event_span_ids,
        }
    if event.consequence_summary:
        current_canon["consequences"] = [
            {
                "summary": event.consequence_summary,
                "evidence_span_ids": event_span_ids,
            }
        ]
    return current_canon, [event]


def _event_page_event(session: Session, page: MemoryPage) -> StoryCanonicalEvent | None:
    if page.target_ref.get("type") != "event":
        return None
    event_id = page.target_ref.get("id")
    if not isinstance(event_id, str):
        return None
    event = _canonical_event(session, event_id)
    if (
        event is None
        or event.project_id != page.project_id
        or event.event_status not in EVENT_LOG_STATUSES
    ):
        return None
    return event


def _location_events(session: Session, page: MemoryPage) -> list[StoryCanonicalEvent]:
    if page.target_ref.get("type") != "location":
        return []
    events = (
        session.query(StoryCanonicalEvent)
        .filter(StoryCanonicalEvent.project_id == page.project_id)
        .filter(StoryCanonicalEvent.event_status.in_(EVENT_LOG_STATUSES))
        .filter(StoryCanonicalEvent.location_entity_id.isnot(None))
        .order_by(StoryCanonicalEvent.created_at, StoryCanonicalEvent.id)
    )
    return [
        event
        for event in events
        if (location_ref := _event_location_ref(session, event)) is not None
        and refs_equivalent(location_ref, page.target_ref)
    ]


def _event_location_ref(
    session: Session,
    event: StoryCanonicalEvent,
) -> dict[str, object] | None:
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


def _event_source_refs(
    session: Session,
    project_id: UUID,
    events: list[StoryCanonicalEvent],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for event in events:
        evidence_span_ids = _event_evidence_span_ids(session, project_id, event)
        if not evidence_span_ids:
            continue
        refs.append({"type": "canonical_event", "id": str(event.id)})
        refs.extend({"type": "source_span", "id": span_id} for span_id in evidence_span_ids)
    return refs


def _relationships(
    facts: list[FactAssertionRecord],
    page: MemoryPage,
    fact_evidence_span_ids: dict[str, list[str]],
) -> list[dict[str, object]]:
    return [
        {
            "fact_id": str(fact.id),
            "predicate": fact.predicate,
            "target_ref": _relationship_counterparty_ref(fact, page),
            "evidence_span_ids": fact_evidence_span_ids[str(fact.id)],
        }
        for fact in facts
        if fact.predicate in RELATIONSHIP_PREDICATES
    ]


def _relationship_counterparty_ref(
    fact: FactAssertionRecord,
    page: MemoryPage,
) -> dict[str, object]:
    if refs_equivalent(fact.object_ref, page.target_ref):
        return fact.subject_ref
    return fact.object_ref


def _state_facts(
    facts: list[FactAssertionRecord],
    page: MemoryPage,
    fact_evidence_span_ids: dict[str, list[str]],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for fact in facts:
        if fact.predicate not in STATE_PREDICATES:
            continue
        state_type = _state_type(fact, page)
        if state_type is None:
            continue
        entries.append(
            {
                "fact_id": str(fact.id),
                "predicate": fact.predicate,
                "state_type": state_type,
                "subject_ref": fact.subject_ref,
                "object_ref": fact.object_ref,
                "counterparty_ref": _state_counterparty_ref(fact, page),
                "evidence_span_ids": fact_evidence_span_ids[str(fact.id)],
            }
        )
    return entries


def _state_type(fact: FactAssertionRecord, page: MemoryPage) -> str | None:
    if fact.predicate == "owns":
        if refs_equivalent(fact.object_ref, page.target_ref):
            return "object_holder"
        if refs_equivalent(fact.subject_ref, page.target_ref):
            return "held_object"
    if fact.predicate == "located_in":
        if refs_equivalent(fact.subject_ref, page.target_ref):
            return "current_location"
        if refs_equivalent(fact.object_ref, page.target_ref):
            return "contained_entity"
    return None


def _state_counterparty_ref(
    fact: FactAssertionRecord,
    page: MemoryPage,
) -> dict[str, object]:
    if refs_equivalent(fact.object_ref, page.target_ref):
        return fact.subject_ref
    return fact.object_ref


def _agency_profile(
    session: Session,
    facts: list[FactAssertionRecord],
    page: MemoryPage,
) -> dict[str, object]:
    if page.page_type != "character":
        return {}
    profile: dict[str, object] = {}
    for fact in facts:
        if not refs_equivalent(fact.subject_ref, page.target_ref):
            continue
        if fact.predicate in AGENCY_PROFILE_SCALAR_PREDICATES:
            entry = _agency_profile_fact_entry(session, page.project_id, fact)
            if entry is not None:
                profile[fact.predicate] = entry
        elif fact.predicate in AGENCY_PROFILE_LIST_PREDICATES:
            entry = _agency_profile_fact_entry(session, page.project_id, fact)
            if entry is not None:
                existing = profile.get(fact.predicate)
                if isinstance(existing, list):
                    cast(list[dict[str, object]], existing).append(entry)
                else:
                    profile[fact.predicate] = [entry]
    return profile


def _agency_profile_fact_entry(
    session: Session,
    project_id: UUID,
    fact: FactAssertionRecord,
) -> dict[str, object] | None:
    value = _agency_profile_value(fact.object_ref)
    source_span_ids = _valid_source_span_ids(session, project_id, fact.evidence_span_ids)
    if not value or not source_span_ids:
        return None
    entry: dict[str, object] = {
        "value": value,
        "fact_id": str(fact.id),
        "source_span_ids": source_span_ids,
    }
    target_ref = fact.object_ref.get("target_ref")
    if isinstance(target_ref, dict):
        entry["target_ref"] = target_ref
    return entry


def _agency_profile_value(ref: dict[str, object]) -> str:
    for key in ("value", "summary", "label", "name", "id"):
        value = ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _valid_source_span_ids(
    session: Session,
    project_id: UUID,
    span_ids: list[str],
) -> list[str]:
    valid_ids: list[str] = []
    seen: set[UUID] = set()
    for raw_span_id in span_ids:
        try:
            span_id = UUID(str(raw_span_id))
        except ValueError:
            continue
        if span_id in seen:
            continue
        span = session.get(SourceSpan, span_id)
        if span is None:
            continue
        source = session.get(RawSource, span.source_id)
        if source is None or source.project_id != project_id:
            continue
        seen.add(span_id)
        valid_ids.append(str(span_id))
    return valid_ids


def _fact_evidence_span_id_map(
    session: Session,
    project_id: UUID,
    facts: list[FactAssertionRecord],
) -> dict[str, list[str]]:
    return {
        str(fact.id): span_ids
        for fact in facts
        if (
            span_ids := _valid_source_span_ids(
                session,
                project_id,
                fact.evidence_span_ids,
            )
        )
    }


def _event_evidence_span_ids(
    session: Session,
    project_id: UUID,
    event: StoryCanonicalEvent,
) -> list[str]:
    if event.project_id != project_id:
        return []
    return _valid_source_span_ids(session, project_id, event.evidence_span_ids)


def _agency_profile_field_count(profile: dict[str, object]) -> int:
    count = 0
    for entry in profile.values():
        if isinstance(entry, list):
            count += len(entry)
        else:
            count += 1
    return count


def _open_threads(
    session: Session,
    page: MemoryPage,
    facts: list[FactAssertionRecord],
) -> list[dict[str, object]]:
    fact_ids = {str(fact.id) for fact in facts}
    threads: list[dict[str, object]] = []
    for review in (
        session.query(ReviewItemRecord)
        .filter_by(project_id=page.project_id, status="open")
        .order_by(ReviewItemRecord.created_at, ReviewItemRecord.id)
    ):
        if not _review_affects_page(review, page, fact_ids):
            continue
        threads.append(
            {
                "review_item_id": str(review.id),
                "review_type": review.review_type,
                "severity": review.severity,
                "summary": review.summary,
            }
        )
    return threads


def _preserved_author_open_threads(page: MemoryPage) -> list[dict[str, object]]:
    return [
        dict(thread)
        for thread in page.open_threads
        if isinstance(thread, dict)
        and thread.get("type") == "memory_writeback_decision"
        and thread.get("thread_type") == "needs_memory_update"
        and thread.get("status") == "open"
    ]


def _merge_open_threads(
    rebuilt_threads: list[dict[str, object]],
    preserved_threads: list[dict[str, object]],
) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict[str, object]] = []
    for thread in rebuilt_threads + preserved_threads:
        key = _open_thread_key(thread)
        if key in seen:
            continue
        seen.add(key)
        merged.append(thread)
    return merged


def _open_thread_key(thread: dict[str, object]) -> tuple[str, str, str]:
    item_ref = thread.get("item_ref")
    if isinstance(item_ref, dict):
        item_ref_dict = cast(dict[str, object], item_ref)
        subject = f"{item_ref_dict.get('type')}:{item_ref_dict.get('id')}"
    else:
        subject = str(
            thread.get("review_item_id")
            or thread.get("source_delta_id")
            or thread.get("description")
            or ""
        )
    return (
        str(thread.get("type") or thread.get("review_type") or ""),
        str(thread.get("thread_type") or thread.get("review_item_id") or ""),
        subject,
    )


def _review_affects_page(
    review: ReviewItemRecord,
    page: MemoryPage,
    fact_ids: set[str],
) -> bool:
    affected_refs = review.affected_refs
    if affected_refs.get("memory_page_id") == str(page.id):
        return True
    fact_id = affected_refs.get("fact_id")
    if isinstance(fact_id, str) and fact_id in fact_ids:
        return True
    page_ref = affected_refs.get("target_ref")
    return isinstance(page_ref, dict) and refs_equivalent(page_ref, page.target_ref)


def _event_ref_for_fact(fact: FactAssertionRecord) -> dict[str, object] | None:
    if fact.object_ref.get("type") == "event":
        return fact.object_ref
    if fact.subject_ref.get("type") == "event":
        return fact.subject_ref
    return None


def _canonical_event(session: Session, event_id: str) -> StoryCanonicalEvent | None:
    try:
        parsed_id = UUID(event_id)
    except ValueError:
        return None
    return session.get(StoryCanonicalEvent, parsed_id)


def _unique_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    output: list[dict[str, object]] = []
    for ref in refs:
        key = f"{ref.get('type')}:{ref.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        output.append(ref)
    return output
