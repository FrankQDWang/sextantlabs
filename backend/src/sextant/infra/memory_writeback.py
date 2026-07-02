from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.contracts.memory_extraction import (
    ExtractedFact,
    ExtractedThreadUpdate,
    MemoryExtractionResult,
)
from sextant.domain.fact_schema import validate_fact_against_story_schema
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
    SkillRun,
    SourceDeltaRecord,
    SourceSpan,
    SourceVersion,
)
from sextant.infra.fact_dedup import (
    evidence_log_exists,
    find_matching_fact,
    merge_unique_text,
    refs_equivalent,
)
from sextant.infra.graph_projection import rebuild_graph_projection
from sextant.infra.source_normalization import ensure_processed_view, source_version_text
from sextant.infra.story_schema import load_effective_story_schema
from sextant.infra.story_skill_registry import (
    STORY_SKILL_VERSION,
    StorySkillRuntimeContext,
    StorySkillValidationError,
    run_skill,
)
from sextant.infra.worker import ProviderRetryableJobError, TerminalJobError
from sextant.ports.memory_extraction import MemoryExtractionProvider
from sextant.ports.object_store import ObjectStore

VALID_MEMORY_RISK_LEVELS = frozenset(("low", "medium", "high"))
VALID_THREAD_UPDATE_TYPES = frozenset(("opens", "keeps_open", "narrows", "pays_off", "closes"))
ACTIVE_THREAD_UPDATE_TYPES = frozenset(("opens", "keeps_open", "narrows"))
EXCLUSIVE_STATE_PREDICATES = frozenset(("located_in", "owns"))


class MemoryWritebackHandler:
    def __init__(
        self,
        object_store: ObjectStore,
        extraction_provider: MemoryExtractionProvider,
    ) -> None:
        self._object_store = object_store
        self._extraction_provider = extraction_provider

    def __call__(self, session: Session, job: JobRecord) -> None:
        source_delta_id = UUID(str(job.payload["source_delta_id"]))
        delta = session.get(SourceDeltaRecord, source_delta_id)
        if delta is None:
            raise ValueError("SourceDelta was not found for memory writeback.")
        if delta.status == "memory_writeback_completed":
            return
        version_id = delta.new_version_id or delta.previous_version_id
        if version_id is None:
            raise ValueError("SourceDelta requires previous_version_id for writeback.")

        version = session.get(SourceVersion, version_id)
        if version is None:
            raise ValueError("SourceVersion was not found for memory writeback.")

        text = self._object_store.get_text(delta.submitted_text_ref)
        if not text:
            raise ValueError("SourceDelta submitted text is empty.")
        try:
            skill_result = run_skill(
                "derive-facts",
                STORY_SKILL_VERSION,
                text,
                StorySkillRuntimeContext(
                    project_id=delta.project_id,
                    request_id=f"memory-writeback:{delta.id}",
                    memory_extraction_provider=self._extraction_provider,
                ),
            )
            extraction = cast(MemoryExtractionResult, skill_result.raw_result)
        except StorySkillValidationError as exc:
            _record_skill_run(
                session,
                self._object_store,
                delta=delta,
                provider=self._extraction_provider,
                text=text,
                structured_output=exc.structured_output,
                validation_result=exc.validation_result,
                status="failed_terminal",
            )
            error_code = exc.validation_result.get("error_code", "llm_output_invalid")
            message = exc.validation_result.get("message", "Memory extraction validation failed.")
            raise TerminalJobError(f"{error_code}: {message}") from exc
        except RuntimeError as exc:
            raise ProviderRetryableJobError(str(exc)) from exc

        story_schema = load_effective_story_schema(session, delta.project_id)
        try:
            facts = _validated_facts(extraction, story_schema)
            thread_updates = _validated_thread_updates(extraction)
        except _InvalidMemoryExtractionOutput as exc:
            _record_skill_run(
                session,
                self._object_store,
                delta=delta,
                provider=self._extraction_provider,
                text=text,
                structured_output=skill_result.structured_output,
                validation_result={
                    "status": "invalid",
                    "error_code": "llm_output_invalid",
                    "message": str(exc),
                },
                status="failed_terminal",
            )
            raise TerminalJobError(f"llm_output_invalid: {exc}") from exc

        version_text = source_version_text(session, self._object_store, version)
        normalized = ensure_processed_view(
            session,
            self._object_store,
            version=version,
            text=version_text,
            cleaning_profile=f"{delta.source_type}_profile_v1",
        )
        view = normalized.view
        _audit(session, delta, "source.normalized", {"view_id": str(view.id)})
        span_start = min(delta.range_start, len(version_text))
        span_end = min(span_start + len(text), len(version_text))

        span = SourceSpan(
            id=uuid4(),
            source_id=delta.source_id,
            version_id=version.id,
            view_id=view.id,
            chapter_id=None,
            scene_id=None,
            start_offset=span_start,
            end_offset=span_end,
            raw_start_offset=span_start,
            raw_end_offset=span_end,
            text_preview=text[:500],
            speaker_entity_id=None,
            narration_layer="narrator",
        )
        session.add(span)
        session.flush()
        _audit(session, delta, "source.span_extracted", {"source_span_id": str(span.id)})

        structured_output = {
            "facts": [asdict(fact) for fact in facts],
            "thread_updates": [asdict(update) for update in thread_updates],
        }
        _record_skill_run(
            session,
            self._object_store,
            delta=delta,
            provider=self._extraction_provider,
            text=text,
            structured_output=structured_output,
            validation_result={"status": "valid"},
            status="succeeded",
        )

        derived_fact_ids: list[UUID] = []
        canon_fact_ids: list[UUID] = []
        affected_memory_page_ids: list[UUID] = []
        affected_review_item_ids: list[UUID] = []
        for extracted_fact in facts:
            fact = find_matching_fact(
                session,
                project_id=delta.project_id,
                subject_ref=extracted_fact.subject_ref,
                predicate=extracted_fact.predicate,
                object_ref=extracted_fact.object_ref,
            )
            fact_created = fact is None
            evidence_added = False
            if fact is None:
                fact = FactAssertionRecord(
                    id=uuid4(),
                    project_id=delta.project_id,
                    subject_ref=extracted_fact.subject_ref,
                    predicate=extracted_fact.predicate,
                    object_ref=extracted_fact.object_ref,
                    fact_status="proposed",
                    evidence_span_ids=[str(span.id)],
                    confidence=0.95 if extracted_fact.risk_level == "low" else 0.6,
                    source_scope=delta.source_scope,
                )
                session.add(fact)
                session.flush()
                evidence_added = True
            else:
                evidence_added = _merge_fact_evidence_for_project(
                    session,
                    fact,
                    [str(span.id)],
                    delta.project_id,
                )
            derived_fact_ids.append(fact.id)
            if not evidence_log_exists(
                session,
                fact_id=fact.id,
                source_span_ids=[str(span.id)],
            ):
                session.add(
                    EvidenceLogEntry(
                        id=uuid4(),
                        project_id=delta.project_id,
                        log_type="fact_derived" if fact_created else "fact_evidence_added",
                        target_ref={"type": "fact_assertion", "id": str(fact.id)},
                        fact_id=fact.id,
                        event_id=None,
                        source_span_ids=[str(span.id)],
                        log_status="written",
                    )
                )
            _audit(session, delta, "memory.evidence_logged", {"fact_id": str(fact.id)})

            if fact.fact_status == "canon":
                _upsert_memory_page(session, delta, fact)
                if evidence_added:
                    canon_fact_ids.append(fact.id)
                _audit(
                    session,
                    delta,
                    "memory.conflict_policy",
                    {"fact_id": str(fact.id), "decision": "merge_existing_canon"},
                )
            else:
                conflict = _find_conflicting_canon_fact(session, fact)
                if conflict is not None:
                    fact.fact_status = "disputed"
                    review = _create_review_item(
                        session,
                        delta,
                        fact,
                        span.id,
                        extracted_fact.risk_level,
                        conflict=conflict,
                    )
                    affected_review_item_ids.append(review.id)
                    _audit(
                        session,
                        delta,
                        "memory.conflict_policy",
                        {
                            "fact_id": str(fact.id),
                            "conflicting_fact_id": str(conflict.id),
                            "decision": "review_required",
                        },
                    )
                elif (
                    extracted_fact.risk_level == "low" and delta.source_scope != "model_suggestion"
                ):
                    fact.promotion_decision_id = fact.promotion_decision_id or uuid4()
                    fact.fact_status = "canon"
                    canon_fact_ids.append(fact.id)
                    _upsert_memory_page(session, delta, fact)
                    _audit(
                        session,
                        delta,
                        "memory.conflict_policy",
                        {"fact_id": str(fact.id), "decision": "promote_canon"},
                    )
                else:
                    fact.fact_status = "disputed"
                    review = _create_review_item(
                        session,
                        delta,
                        fact,
                        span.id,
                        extracted_fact.risk_level,
                    )
                    affected_review_item_ids.append(review.id)
                    _audit(
                        session,
                        delta,
                        "memory.conflict_policy",
                        {"fact_id": str(fact.id), "decision": "review_required"},
                    )

        for thread_update in thread_updates:
            if thread_update.risk_level != "low":
                evidence = _create_thread_update_review_evidence(
                    session,
                    delta=delta,
                    span_id=span.id,
                    update=thread_update,
                )
                review = _create_thread_update_review_item(
                    session,
                    delta=delta,
                    span_id=span.id,
                    evidence_log_id=evidence.id,
                    update=thread_update,
                )
                affected_review_item_ids.append(review.id)
                _audit(
                    session,
                    delta,
                    "memory.thread_update_review_required",
                    {
                        "review_item_id": str(review.id),
                        "thread_id": _thread_id_for_update(thread_update),
                        "risk_level": thread_update.risk_level,
                    },
                )
                continue
            page, thread_id = _upsert_thread_memory_page(
                session,
                delta=delta,
                span_id=span.id,
                update=thread_update,
            )
            affected_memory_page_ids.append(page.id)
            if not _thread_update_evidence_log_exists(
                session,
                page_id=page.id,
                thread_id=thread_id,
                source_span_ids=[str(span.id)],
            ):
                session.add(
                    EvidenceLogEntry(
                        id=uuid4(),
                        project_id=delta.project_id,
                        log_type="thread_update",
                        target_ref={
                            "type": "memory_page_thread",
                            "id": thread_id,
                            "memory_page_id": str(page.id),
                        },
                        fact_id=None,
                        event_id=None,
                        source_span_ids=[str(span.id)],
                        log_status="written",
                    )
                )
            _audit(
                session,
                delta,
                "memory.thread_update_logged",
                {
                    "memory_page_id": str(page.id),
                    "thread_id": thread_id,
                    "update_type": thread_update.update_type,
                },
            )

        if canon_fact_ids:
            result = rebuild_graph_projection(session, project_id=delta.project_id)
            _audit(
                session,
                delta,
                "memory.graph_rebuilt",
                {"run_id": str(result.run_id), "created_edge_count": result.created_edge_count},
            )

        if facts or thread_updates:
            readiness_affected_refs: list[dict[str, object]] = [
                {"type": "source_delta", "id": str(delta.id)}
            ]
            readiness_affected_refs.extend(
                {"type": "fact_assertion", "id": str(fact_id)} for fact_id in derived_fact_ids
            )
            readiness_affected_refs.extend(
                {"type": "memory_page", "id": str(page_id)}
                for page_id in _unique_uuids(affected_memory_page_ids)
            )
            readiness_affected_refs.extend(
                {"type": "review_item", "id": str(review_id)}
                for review_id in _unique_uuids(affected_review_item_ids)
            )
            readiness = mark_context_pack_readiness(
                session,
                project_id=delta.project_id,
                source_span_id=span.id,
                source_delta_id=delta.id,
                affected_refs=readiness_affected_refs,
            )
            _audit(
                session,
                delta,
                "context_pack.readiness_marked",
                {"readiness_id": str(readiness.id), "source_span_id": str(span.id)},
            )

        delta.status = "memory_writeback_completed"
        _audit(
            session,
            delta,
            "memory_writeback.completed",
            {
                "source_delta_id": str(delta.id),
                "fact_count": len(facts),
                "thread_update_count": len(thread_updates),
            },
        )
        session.flush()


class _InvalidMemoryExtractionOutput(ValueError):
    pass


def _validated_facts(
    extraction: MemoryExtractionResult,
    story_schema: EffectiveStorySchema,
) -> list[ExtractedFact]:
    if not isinstance(extraction, MemoryExtractionResult):
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned an invalid result object."
        )
    facts = extraction.facts
    if not isinstance(facts, list):
        raise _InvalidMemoryExtractionOutput("Memory extraction provider returned invalid facts.")
    for fact in facts:
        _validate_fact(fact, story_schema)
    return facts


def _validate_fact(fact: object, story_schema: EffectiveStorySchema) -> None:
    if not isinstance(fact, ExtractedFact):
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid fact object."
        )
    _validate_ref(fact.subject_ref, "subject_ref")
    _validate_ref(fact.object_ref, "object_ref")
    if not isinstance(fact.predicate, str) or not fact.predicate.strip():
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid predicate."
        )
    if fact.risk_level not in VALID_MEMORY_RISK_LEVELS:
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid fact risk_level."
        )
    schema_rejection = validate_fact_against_story_schema(
        story_schema,
        predicate=fact.predicate,
        subject_ref=dict(fact.subject_ref),
        object_ref=dict(fact.object_ref),
    )
    if schema_rejection is not None:
        raise _InvalidMemoryExtractionOutput(
            f"Memory extraction provider returned schema-invalid fact: {schema_rejection.skipped}."
        )


def _validated_thread_updates(extraction: MemoryExtractionResult) -> list[ExtractedThreadUpdate]:
    thread_updates = extraction.thread_updates
    if not isinstance(thread_updates, list):
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread_updates."
        )
    for update in thread_updates:
        _validate_thread_update(update)
    return thread_updates


def _validate_thread_update(update: object) -> None:
    if not isinstance(update, ExtractedThreadUpdate):
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread update object."
        )
    _validate_ref(update.target_ref, "thread target_ref")
    if update.update_type not in VALID_THREAD_UPDATE_TYPES:
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread update_type."
        )
    if update.risk_level not in VALID_MEMORY_RISK_LEVELS:
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread risk_level."
        )
    if not isinstance(update.description, str) or not update.description.strip():
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread description."
        )
    if update.thread_id is not None and (
        not isinstance(update.thread_id, str) or not update.thread_id.strip()
    ):
        raise _InvalidMemoryExtractionOutput(
            "Memory extraction provider returned invalid thread_id."
        )


def _validate_ref(value: object, field_name: str) -> None:
    if not isinstance(value, dict):
        raise _InvalidMemoryExtractionOutput(
            f"Memory extraction provider returned invalid {field_name}."
        )
    mapping = cast(dict[object, object], value)
    if not _non_empty_text(mapping.get("type")) or not _non_empty_text(mapping.get("id")):
        raise _InvalidMemoryExtractionOutput(
            f"Memory extraction provider returned invalid {field_name}."
        )
    for key, item in mapping.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise _InvalidMemoryExtractionOutput(
                f"Memory extraction provider returned invalid {field_name}."
            )


def _non_empty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _record_skill_run(
    session: Session,
    object_store: ObjectStore,
    *,
    delta: SourceDeltaRecord,
    provider: MemoryExtractionProvider,
    text: str,
    structured_output: dict[str, Any],
    validation_result: dict[str, object],
    status: str,
) -> UUID:
    skill_run_id = uuid4()
    session.add(
        SkillRun(
            id=skill_run_id,
            project_id=delta.project_id,
            skill_name=provider.skill_name,
            skill_version=provider.skill_version,
            input_schema_version="memory-extraction-input-v1",
            output_schema_version="memory-extraction-output-v1",
            prompt_version=provider.prompt_version,
            input_hash=sha256(text.encode("utf-8")).hexdigest(),
            structured_output=structured_output,
            validation_result=validation_result,
            raw_output_ref=object_store.put_text(
                f"skill-runs/{skill_run_id}.json",
                json.dumps(structured_output, sort_keys=True),
            ),
            status=status,
            latency_ms=0,
            cost_cents=0,
        )
    )
    session.flush()
    return skill_run_id


def _structured_output(extraction: object) -> dict[str, Any]:
    facts = getattr(extraction, "facts", None)
    thread_updates = getattr(extraction, "thread_updates", None)
    output: dict[str, Any] = {}
    if not isinstance(facts, list):
        output["facts"] = facts
    else:
        output["facts"] = [_structured_item_output(fact) for fact in facts]
    if not isinstance(thread_updates, list):
        output["thread_updates"] = thread_updates
    else:
        output["thread_updates"] = [_structured_item_output(update) for update in thread_updates]
    return output


def _structured_item_output(item: object) -> object:
    if isinstance(item, ExtractedFact | ExtractedThreadUpdate):
        return asdict(item)
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    return repr(item)


def _create_review_item(
    session: Session,
    delta: SourceDeltaRecord,
    fact: FactAssertionRecord,
    span_id: UUID,
    risk_level: str,
    *,
    conflict: FactAssertionRecord | None = None,
) -> ReviewItemRecord:
    existing = _review_for_fact(session, fact.id)
    if existing is not None:
        existing_source_span_ids = _source_span_ids_for_project(
            session,
            [str(item) for item in existing.new_evidence.get("source_span_ids", [])],
            delta.project_id,
        )
        existing.new_evidence = {
            **existing.new_evidence,
            "source_span_ids": merge_unique_text(
                existing_source_span_ids,
                [str(span_id)],
            ),
        }
        if conflict is not None:
            existing.existing_evidence = _conflict_existing_evidence(
                session,
                conflict=conflict,
                project_id=delta.project_id,
            )
        return existing
    review_type = _review_type_for_fact(fact)
    severity = "medium" if risk_level == "medium" else "high"
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type=review_type,
        severity=severity,
        status="open",
        summary=f"{fact.predicate} requires author review before canon promotion.",
        affected_refs={"fact_id": str(fact.id)},
        new_evidence={"source_span_ids": [str(span_id)]},
        existing_evidence=(
            _conflict_existing_evidence(session, conflict=conflict, project_id=delta.project_id)
            if conflict is not None
            else {}
        ),
        suggested_actions=[
            {"resolution": "accept"},
            {"resolution": "reject"},
            {"resolution": "mark_intentional"},
        ],
        default_action="review",
    )
    session.add(review)
    return review


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


def _review_type_for_fact(fact: FactAssertionRecord) -> str:
    if fact.predicate in EXCLUSIVE_STATE_PREDICATES:
        return "object_state_conflict"
    if fact.predicate == "knows":
        return "knowledge_conflict"
    return "canon_conflict"


def _conflict_existing_evidence(
    session: Session,
    *,
    conflict: FactAssertionRecord,
    project_id: UUID,
) -> dict[str, object]:
    return {
        "fact_id": str(conflict.id),
        "source_span_ids": _source_span_ids_for_project(
            session,
            [str(item) for item in conflict.evidence_span_ids],
            project_id,
        ),
    }


def _source_span_ids_for_project(
    session: Session,
    span_ids: list[str],
    project_id: UUID,
) -> list[str]:
    filtered: list[str] = []
    for span_id in span_ids:
        try:
            span_uuid = UUID(span_id)
        except ValueError:
            continue
        span = session.get(SourceSpan, span_uuid)
        if span is None:
            continue
        raw_source = session.get(RawSource, span.source_id)
        if raw_source is None or raw_source.project_id != project_id:
            continue
        filtered.append(str(span.id))
    return list(dict.fromkeys(filtered))


def _merge_fact_evidence_for_project(
    session: Session,
    fact: FactAssertionRecord,
    evidence_span_ids: list[str],
    project_id: UUID,
) -> bool:
    existing_ids = _source_span_ids_for_project(
        session,
        [str(item) for item in fact.evidence_span_ids],
        project_id,
    )
    added_ids = _source_span_ids_for_project(session, evidence_span_ids, project_id)
    merged = merge_unique_text(existing_ids, added_ids)
    if merged == fact.evidence_span_ids:
        return False
    fact.evidence_span_ids = merged
    return True


def _source_refs_for_fact_writeback(
    session: Session,
    *,
    project_id: UUID,
    source_refs: list[dict[str, object]],
    source_delta_id: UUID,
    source_span_ids: list[str],
) -> list[dict[str, object]]:
    preserved_refs = [dict(ref) for ref in source_refs if ref.get("type") != "source_span"]
    existing_span_ids = [
        str(ref.get("id"))
        for ref in source_refs
        if ref.get("type") == "source_span" and ref.get("id") is not None
    ]
    valid_span_ids = _source_span_ids_for_project(
        session,
        merge_unique_text(existing_span_ids, source_span_ids),
        project_id,
    )
    return _unique_refs(
        preserved_refs
        + [{"type": "source_delta", "id": str(source_delta_id)}]
        + [{"type": "source_span", "id": span_id} for span_id in valid_span_ids]
    )


def _thread_update_review_evidence_log_entry_ids(
    session: Session,
    entry_ids: list[str],
    *,
    project_id: UUID,
    target_ref: dict[str, object],
) -> list[str]:
    filtered: list[str] = []
    for entry_id in entry_ids:
        try:
            entry_uuid = UUID(entry_id)
        except ValueError:
            continue
        entry = session.get(EvidenceLogEntry, entry_uuid)
        if entry is None:
            continue
        if entry.project_id != project_id:
            continue
        if entry.log_type != "thread_update_review_required":
            continue
        if entry.log_status != "written":
            continue
        if entry.target_ref != target_ref:
            continue
        source_span_ids = _source_span_ids_for_project(
            session,
            [str(item) for item in entry.source_span_ids],
            project_id,
        )
        if not source_span_ids:
            continue
        filtered.append(str(entry.id))
    return list(dict.fromkeys(filtered))


def _review_for_fact(session: Session, fact_id: UUID) -> ReviewItemRecord | None:
    return session.scalars(
        select(ReviewItemRecord).where(ReviewItemRecord.affected_refs == {"fact_id": str(fact_id)})
    ).first()


def _upsert_memory_page(
    session: Session,
    delta: SourceDeltaRecord,
    fact: FactAssertionRecord,
) -> None:
    target_ref = fact.subject_ref
    page = _find_memory_page(session, project_id=delta.project_id, target_ref=target_ref)
    evidence_span_ids = _source_span_ids_for_project(
        session,
        [str(item) for item in fact.evidence_span_ids],
        delta.project_id,
    )
    if evidence_span_ids != fact.evidence_span_ids:
        fact.evidence_span_ids = evidence_span_ids
    fact_entry = {
        "fact_id": str(fact.id),
        "predicate": fact.predicate,
        "object_ref": fact.object_ref,
        "evidence_span_ids": evidence_span_ids,
    }
    if page is None:
        session.add(
            MemoryPage(
                id=uuid4(),
                project_id=delta.project_id,
                page_type=target_ref["type"],
                target_ref=target_ref,
                title=target_ref["id"],
                current_canon={"facts": [fact_entry]},
                appearance_log=[],
                event_log=[],
                relationships=[],
                open_threads=[],
                contradictions=[],
                source_refs=_source_refs_for_fact_writeback(
                    session,
                    project_id=delta.project_id,
                    source_refs=[],
                    source_delta_id=delta.id,
                    source_span_ids=evidence_span_ids,
                ),
                canon_status="current",
                memory_depth="scene",
            )
        )
    else:
        facts = list(page.current_canon.get("facts", []))
        replaced = False
        for index, entry in enumerate(facts):
            if entry.get("fact_id") == str(fact.id):
                facts[index] = fact_entry
                replaced = True
                break
        if not replaced:
            facts.append(fact_entry)
        page.current_canon = {"facts": facts}
        page.source_refs = _source_refs_for_fact_writeback(
            session,
            project_id=delta.project_id,
            source_refs=list(page.source_refs),
            source_delta_id=delta.id,
            source_span_ids=evidence_span_ids,
        )


def _upsert_thread_memory_page(
    session: Session,
    *,
    delta: SourceDeltaRecord,
    span_id: UUID,
    update: ExtractedThreadUpdate,
) -> tuple[MemoryPage, str]:
    target_ref = dict(update.target_ref)
    page = _find_memory_page(session, project_id=delta.project_id, target_ref=target_ref)
    source_refs = _unique_refs(
        [
            {"type": "source_delta", "id": str(delta.id)},
            {"type": "source_span", "id": str(span_id)},
        ]
    )
    if page is None:
        page = MemoryPage(
            id=uuid4(),
            project_id=delta.project_id,
            page_type=target_ref["type"],
            target_ref=target_ref,
            title=target_ref["id"],
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
        session.add(page)
        session.flush()
    else:
        page.source_refs = _unique_refs(list(page.source_refs) + source_refs)

    thread_id = _thread_id_for_update(update)
    page.open_threads = _updated_open_threads(
        session,
        page.open_threads,
        update=update,
        thread_id=thread_id,
        project_id=delta.project_id,
        source_delta_id=delta.id,
        source_span_id=span_id,
    )
    session.flush()
    return page, thread_id


def _create_thread_update_review_evidence(
    session: Session,
    *,
    delta: SourceDeltaRecord,
    span_id: UUID,
    update: ExtractedThreadUpdate,
) -> EvidenceLogEntry:
    target_ref = _thread_update_review_ref(update)
    span_ids = [str(span_id)]
    for entry in session.scalars(
        select(EvidenceLogEntry).where(EvidenceLogEntry.log_type == "thread_update_review_required")
    ):
        if entry.target_ref == target_ref and set(span_ids).issubset(set(entry.source_span_ids)):
            return entry

    evidence = EvidenceLogEntry(
        id=uuid4(),
        project_id=delta.project_id,
        log_type="thread_update_review_required",
        target_ref=target_ref,
        fact_id=None,
        event_id=None,
        source_span_ids=span_ids,
        log_status="written",
    )
    session.add(evidence)
    session.flush()
    return evidence


def _create_thread_update_review_item(
    session: Session,
    *,
    delta: SourceDeltaRecord,
    span_id: UUID,
    evidence_log_id: UUID,
    update: ExtractedThreadUpdate,
) -> ReviewItemRecord:
    target_ref = _thread_update_review_ref(update)
    affected_refs = {
        **target_ref,
        "update_type": update.update_type,
    }
    existing = _review_for_thread_update(
        session,
        project_id=delta.project_id,
        affected_refs=affected_refs,
    )
    if existing is not None:
        existing_source_span_ids = _source_span_ids_for_project(
            session,
            [str(item) for item in existing.new_evidence.get("source_span_ids", [])],
            delta.project_id,
        )
        existing_evidence_log_entry_ids = _thread_update_review_evidence_log_entry_ids(
            session,
            [str(item) for item in existing.new_evidence.get("evidence_log_entry_ids", [])],
            project_id=delta.project_id,
            target_ref=target_ref,
        )
        existing.new_evidence = {
            **existing.new_evidence,
            "source_span_ids": merge_unique_text(
                existing_source_span_ids,
                [str(span_id)],
            ),
            "evidence_log_entry_ids": merge_unique_text(
                existing_evidence_log_entry_ids,
                [str(evidence_log_id)],
            ),
        }
        return existing

    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="continuity_warning",
        severity=update.risk_level,
        status="open",
        summary=update.description.strip(),
        affected_refs=affected_refs,
        new_evidence={
            "source_span_ids": [str(span_id)],
            "evidence_log_entry_ids": [str(evidence_log_id)],
        },
        existing_evidence={},
        suggested_actions=[
            {"resolution": "accept"},
            {"resolution": "reject"},
            {"resolution": "needs_memory_update"},
        ],
        default_action="ask_author",
    )
    session.add(review)
    session.flush()
    return review


def _review_for_thread_update(
    session: Session,
    *,
    project_id: UUID,
    affected_refs: dict[str, object],
) -> ReviewItemRecord | None:
    return session.scalars(
        select(ReviewItemRecord)
        .where(ReviewItemRecord.project_id == project_id)
        .where(ReviewItemRecord.affected_refs == affected_refs)
        .where(ReviewItemRecord.status == "open")
    ).first()


def _thread_update_review_ref(update: ExtractedThreadUpdate) -> dict[str, object]:
    return {
        "type": "proposed_thread_update",
        "id": _thread_id_for_update(update),
        "target_ref": dict(update.target_ref),
    }


def _updated_open_threads(
    session: Session,
    open_threads: list[dict[str, Any]],
    *,
    update: ExtractedThreadUpdate,
    thread_id: str,
    project_id: UUID,
    source_delta_id: UUID,
    source_span_id: UUID,
) -> list[dict[str, Any]]:
    threads = [dict(thread) for thread in open_threads]
    thread_entry = _thread_entry(
        update,
        thread_id=thread_id,
        source_delta_id=source_delta_id,
        source_span_id=source_span_id,
    )
    for index, thread in enumerate(threads):
        if thread.get("id") == thread_id:
            previous_span_ids = _source_span_ids_for_project(
                session,
                [str(item) for item in thread.get("source_span_ids", []) if isinstance(item, str)],
                project_id,
            )
            thread_entry["source_span_ids"] = merge_unique_text(
                previous_span_ids,
                [str(source_span_id)],
            )
            threads[index] = {**thread, **thread_entry}
            return threads
    return threads + [thread_entry]


def _thread_entry(
    update: ExtractedThreadUpdate,
    *,
    thread_id: str,
    source_delta_id: UUID,
    source_span_id: UUID,
) -> dict[str, Any]:
    return {
        "id": thread_id,
        "update_type": update.update_type,
        "summary": update.description.strip(),
        "risk_level": update.risk_level,
        "source_delta_id": str(source_delta_id),
        "source_span_ids": [str(source_span_id)],
        "status": _thread_status(update.update_type),
    }


def _thread_status(update_type: str) -> str:
    if update_type in ACTIVE_THREAD_UPDATE_TYPES:
        return "open"
    if update_type == "pays_off":
        return "resolved"
    return "closed"


def _thread_id_for_update(update: ExtractedThreadUpdate) -> str:
    if update.thread_id:
        return update.thread_id.strip()
    return _thread_id(update)


def _thread_id(update: ExtractedThreadUpdate) -> str:
    payload = {
        "description": update.description.strip(),
        "target_ref": update.target_ref,
        "update_type": update.update_type,
    }
    digest = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"thread-{digest}"


def _thread_update_evidence_log_exists(
    session: Session,
    *,
    page_id: UUID,
    thread_id: str,
    source_span_ids: list[str],
) -> bool:
    target_ref = {
        "type": "memory_page_thread",
        "id": thread_id,
        "memory_page_id": str(page_id),
    }
    span_set = set(source_span_ids)
    for entry in session.scalars(
        select(EvidenceLogEntry).where(EvidenceLogEntry.log_type == "thread_update")
    ):
        if entry.target_ref == target_ref and span_set.issubset(set(entry.source_span_ids)):
            return True
    return False


def _find_memory_page(
    session: Session,
    *,
    project_id: UUID,
    target_ref: dict[str, str],
) -> MemoryPage | None:
    pages = session.scalars(
        select(MemoryPage)
        .where(MemoryPage.project_id == project_id)
        .where(MemoryPage.page_type == target_ref["type"])
    )
    for page in pages:
        if refs_equivalent(page.target_ref, target_ref):
            return page
    return None


def _unique_refs(refs: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for ref in refs:
        key = (str(ref.get("type")), str(ref.get("id")))
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _unique_uuids(values: list[UUID]) -> list[UUID]:
    seen: set[UUID] = set()
    result: list[UUID] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _audit(
    session: Session,
    delta: SourceDeltaRecord,
    event_type: str,
    decision: dict[str, object],
) -> None:
    session.add(
        AuditEvent(
            id=uuid4(),
            project_id=delta.project_id,
            request_id=f"source_delta:{delta.id}",
            actor_id=None,
            event_type=event_type,
            subject_ref={"type": "source_delta", "id": str(delta.id)},
            decision=decision,
        )
    )
