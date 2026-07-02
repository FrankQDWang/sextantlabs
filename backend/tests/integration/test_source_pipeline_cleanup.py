from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sextant.contracts.pov_detection import PovDetectionRequest, PovDetectionResult
from sextant.infra.db.models import (
    AuditEvent,
    Base,
    CharacterKnowledge,
    ContextPackReadinessRecord,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
    JobRecord,
    MemoryPage,
    Project,
    RawSource,
    ReviewItemRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
    StoryEventCandidate,
    StoryMention,
    StoryScene,
)
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.source_pipeline import (
    AggregateEventsHandler,
    DeriveFactsHandler,
    ExtractEventsHandler,
    ExtractMentionsHandler,
    ResolveAliasesHandler,
    RunConflictPolicyHandler,
    _ensure_fact,
)
from sextant.infra.source_structure import SourceStructureSplitHandler
from sextant.infra.story_schema import load_effective_story_schema
from sextant.infra.worker import DbWorker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


def test_split_structure_enqueues_source_spans_and_extract_mentions_jobs(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    view = _seed_processed_view(
        session,
        object_store,
        text="Mira found the Lantern Map in Harbor Nine.\n\nOrrin closed the gate.",
    )
    job = _split_structure_job(session, view)

    processed = DbWorker(
        session,
        {"split_structure": SourceStructureSplitHandler(object_store)},
    ).run_once(worker_id="worker-structure")

    spans = session.query(SourceSpan).order_by(SourceSpan.start_offset).all()
    extract_jobs = (
        session.query(JobRecord)
        .filter_by(job_type="extract_mentions")
        .order_by(JobRecord.created_at, JobRecord.id)
        .all()
    )
    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert [span.text_preview for span in spans] == [
        "Mira found the Lantern Map in Harbor Nine.",
        "Orrin closed the gate.",
    ]
    assert {queued.payload["source_span_id"] for queued in extract_jobs} == {
        str(span.id) for span in spans
    }
    assert all(
        queued.payload["extractor_version"] == "mention-extractor-v1" for queued in extract_jobs
    )


def test_source_pipeline_keeps_ordinary_prose_out_of_semantic_state(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    view = _seed_processed_view(
        session,
        object_store,
        text="Mira handed Kestrel the Lantern Map.",
    )
    _split_structure_job(session, view)

    processed_types = _drain_worker(
        session,
        _source_pipeline_handlers(object_store),
        max_runs=12,
    )

    assert processed_types == [
        "split_structure",
        "extract_mentions",
        "resolve_aliases",
        "extract_events",
        "aggregate_events",
        "derive_facts",
        "run_conflict_policy",
    ]
    assert session.query(StoryMention).count() == 0
    assert session.query(StoryAliasRecord).count() == 0
    assert session.query(StoryCanonicalEntity).count() == 0
    assert session.query(StoryEventCandidate).count() == 0
    assert session.query(StoryCanonicalEvent).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(CharacterKnowledge).count() == 0
    assert session.query(EvidenceLogEntry).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ContextPackReadinessRecord).count() == 0


def test_source_pipeline_does_not_infer_pov_from_perspective_phrase(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    view = _seed_processed_view(
        session,
        object_store,
        text="From Mira's perspective, the Harbor Nine bells sounded wrong.",
    )
    _split_structure_job(session, view)

    _drain_worker(
        session,
        _source_pipeline_handlers(object_store),
        max_runs=12,
    )

    scene = session.query(StoryScene).one()
    span = session.query(SourceSpan).one()
    assert scene.pov_character_id is None
    assert scene.pov_evidence_span_ids == []
    assert scene.pov_uncertainty_reason is None
    assert span.speaker_entity_id is None


def test_explicit_scene_pov_hint_still_links_scene_to_canonical_character(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    view = _seed_processed_view(
        session,
        object_store,
        text="POV: Mira\nMira found the Lantern Map.",
    )
    _split_structure_job(session, view)

    _drain_worker(
        session,
        _source_pipeline_handlers(object_store),
        max_runs=12,
    )

    mira = session.query(StoryCanonicalEntity).filter_by(display_name="Mira").one()
    scene = session.query(StoryScene).one()
    span = session.query(SourceSpan).one()
    assert scene.pov_character_id == mira.id
    assert scene.pov_mode == "third_limited"
    assert scene.pov_evidence_span_ids == [str(span.id)]
    assert session.query(StoryAliasRecord).filter_by(alias_text="Mira").count() == 1
    assert session.query(StoryMention).filter_by(raw_text="Mira").count() == 1


def test_resolve_aliases_can_use_provider_for_preseeded_mentions(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    view = _seed_processed_view(
        session,
        object_store,
        text="Ari walked beside Niko in silence.",
    )
    _split_structure_job(session, view)
    DbWorker(
        session,
        {"split_structure": SourceStructureSplitHandler(object_store)},
    ).run_once(worker_id="worker-structure")

    span = session.query(SourceSpan).one()
    session.add_all(
        [
            StoryMention(
                id=uuid4(),
                span_id=span.id,
                raw_text="Ari",
                mention_type="character",
                local_context=span.text_preview,
                resolved_entity_id=None,
                resolution_status="unresolved",
                confidence=0.82,
            ),
            StoryMention(
                id=uuid4(),
                span_id=span.id,
                raw_text="Niko",
                mention_type="character",
                local_context=span.text_preview,
                resolved_entity_id=None,
                resolution_status="unresolved",
                confidence=0.82,
            ),
        ]
    )
    session.commit()

    worker = DbWorker(
        session,
        _source_pipeline_handlers(
            object_store,
            pov_detection_provider=_StaticPovDetectionProvider(pov_character_name="Ari"),
        ),
    )
    assert worker.run_once(worker_id="worker-source-pipeline") is True
    assert worker.run_once(worker_id="worker-source-pipeline") is True

    scene = session.query(StoryScene).one()
    span = session.query(SourceSpan).one()
    ari = session.query(StoryCanonicalEntity).filter_by(display_name="Ari").one()
    queued_extract_events = (
        session.query(JobRecord).filter_by(job_type="extract_events", status="queued").all()
    )
    assert scene.pov_character_id == ari.id
    assert scene.pov_mode == "third_limited"
    assert scene.pov_confidence == 0.76
    assert scene.pov_evidence_span_ids == [str(span.id)]
    assert len(queued_extract_events) == 1
    audit = (
        session.query(AuditEvent)
        .filter_by(event_type="story.aliases_resolved")
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .first()
    )
    assert audit is not None
    assert audit.decision["pov_source"] == "model_assisted"


def test_aggregate_events_and_derive_facts_preserve_structured_candidate_flow(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    span = _seed_span(
        session,
        object_store,
        text="Structured event candidate evidence.",
    )
    candidate = StoryEventCandidate(
        id=uuid4(),
        project_id=span_project_id(session, span),
        scene_id=None,
        event_type="object_transfer",
        summary="Mira handed Kestrel the Lantern Map.",
        participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel", "role": "recipient"},
        ],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        state_change={"source": "structured_candidate"},
        evidence_span_ids=[str(span.id)],
        confidence=0.84,
        aggregation_status="new",
    )
    session.add(candidate)
    session.commit()

    _run_job(session, "aggregate_events", span, AggregateEventsHandler())
    processed = DbWorker(
        session,
        {"derive_facts": DeriveFactsHandler()},
    ).run_once(worker_id="worker-derive-facts")
    assert processed is True

    canonical_event = session.query(StoryCanonicalEvent).one()
    facts = session.query(FactAssertionRecord).order_by(FactAssertionRecord.predicate).all()
    conflict_policy_jobs = (
        session.query(JobRecord).filter_by(job_type="run_conflict_policy", status="queued").all()
    )
    assert canonical_event.event_candidate_ids == [str(candidate.id)]
    assert canonical_event.evidence_span_ids == [str(span.id)]
    assert [(fact.predicate, fact.fact_status) for fact in facts] == [
        ("involves_object", "proposed"),
        ("owns", "proposed"),
        ("present_at", "proposed"),
        ("present_at", "proposed"),
    ]
    assert len(conflict_policy_jobs) == 1
    assert {tuple(entry.source_span_ids) for entry in session.query(EvidenceLogEntry).all()} == {
        (str(span.id),)
    }


def test_derive_facts_does_not_infer_transfer_owner_from_event_summary(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    span = _seed_span(
        session,
        object_store,
        text="Structured candidate without explicit recipient role.",
    )
    candidate = StoryEventCandidate(
        id=uuid4(),
        project_id=span_project_id(session, span),
        scene_id=None,
        event_type="object_transfer",
        summary="Mira handed Kestrel the Lantern Map.",
        participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        state_change={"source": "structured_candidate"},
        evidence_span_ids=[str(span.id)],
        confidence=0.84,
        aggregation_status="new",
    )
    session.add(candidate)
    session.commit()

    _run_job(session, "aggregate_events", span, AggregateEventsHandler())
    processed = DbWorker(
        session,
        {"derive_facts": DeriveFactsHandler()},
    ).run_once(worker_id="worker-derive-facts")
    assert processed is True

    facts = session.query(FactAssertionRecord).order_by(FactAssertionRecord.predicate).all()
    assert [(fact.predicate, fact.fact_status) for fact in facts] == [
        ("involves_object", "proposed"),
        ("present_at", "proposed"),
        ("present_at", "proposed"),
    ]
    assert session.query(ReviewItemRecord).count() == 0


def test_derive_facts_does_not_create_transfer_review_from_summary_pronoun(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    span = _seed_span(
        session,
        object_store,
        text="Structured candidate without explicit object resolution.",
    )
    candidate = StoryEventCandidate(
        id=uuid4(),
        project_id=span_project_id(session, span),
        scene_id=None,
        event_type="object_transfer",
        summary="Mira handed it to Kestrel.",
        participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        objects=[],
        location_entity_id=None,
        state_change={"source": "structured_candidate"},
        evidence_span_ids=[str(span.id)],
        confidence=0.84,
        aggregation_status="new",
    )
    session.add(candidate)
    session.commit()

    _run_job(session, "aggregate_events", span, AggregateEventsHandler())
    processed = DbWorker(
        session,
        {"derive_facts": DeriveFactsHandler()},
    ).run_once(worker_id="worker-derive-facts")
    assert processed is True

    facts = session.query(FactAssertionRecord).order_by(FactAssertionRecord.predicate).all()
    assert [(fact.predicate, fact.fact_status) for fact in facts] == [
        ("present_at", "proposed"),
        ("present_at", "proposed"),
    ]
    assert session.query(ReviewItemRecord).count() == 0


def test_conflict_policy_promotes_manual_fact_through_memory_and_graph_gates(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    span = _seed_span(
        session,
        object_store,
        text="Manual structured fact evidence.",
    )
    story_schema = load_effective_story_schema(session, span_project_id(session, span))
    subject_ref = {"type": "character", "id": "mira", "label": "Mira"}
    object_ref = {"type": "object", "id": "lantern-map", "label": "Lantern Map"}

    _ensure_fact(
        session,
        _span_job(session, span),
        story_schema,
        subject_ref=subject_ref,
        predicate="owns",
        object_ref=object_ref,
        evidence_span_ids=[str(span.id)],
        source_scope="user_draft",
        event_id=None,
    )
    _run_job(session, "run_conflict_policy", span, RunConflictPolicyHandler())

    fact = session.query(FactAssertionRecord).one()
    page = session.query(MemoryPage).one()
    graph_edge = session.query(GraphProjectionEdge).one()
    assert fact.fact_status == "canon"
    assert fact.evidence_span_ids == [str(span.id)]
    assert page.current_canon["facts"] == [
        {
            "fact_id": str(fact.id),
            "predicate": "owns",
            "object_ref": object_ref,
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert graph_edge.edge_status == "canon"
    assert graph_edge.evidence_refs == [{"type": "source_span", "id": str(span.id)}]


def _seed_processed_view(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
    source_type: str = "draft_manuscript",
    source_scope: str = "user_draft",
) -> SourceProcessedView:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_text_ref = object_store.put_text(f"raw/{project.id}.txt", text)
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type=source_type,
        source_scope=source_scope,
        title="Chapter 1",
        ownership_status="owned",
        raw_text_ref=raw_text_ref,
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash=f"hash-{project.id}",
        raw_text_ref=raw_text_ref,
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text(f"processed/{version.id}.md", text),
        raw_offset_map_ref=object_store.put_text(f"processed/{version.id}.offsets.json", "{}"),
        view_status="current",
    )
    session.add_all([project, raw_source, version, view])
    session.commit()
    return view


def _split_structure_job(
    session: Session,
    view: SourceProcessedView,
    *,
    chapter_title: str = "Chapter 1",
) -> JobRecord:
    version = session.get(SourceVersion, view.version_id)
    assert version is not None
    raw_source = session.get(RawSource, version.source_id)
    assert raw_source is not None
    job = JobRecord(
        id=uuid4(),
        project_id=raw_source.project_id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
            "chapter_title": chapter_title,
        },
    )
    session.add(job)
    session.commit()
    return job


def _drain_worker(
    session: Session,
    handlers: dict[str, object],
    *,
    max_runs: int = 12,
) -> list[str]:
    worker = DbWorker(session, handlers)
    processed_types: list[str] = []
    for _ in range(max_runs):
        next_job = (
            session.query(JobRecord)
            .filter_by(status="queued")
            .order_by(JobRecord.created_at, JobRecord.id)
            .first()
        )
        if next_job is None:
            break
        processed = worker.run_once(worker_id="worker-source-pipeline")
        assert processed is True
        processed_types.append(next_job.job_type)
    assert session.query(JobRecord).filter_by(status="queued").count() == 0
    return processed_types


def _seed_span(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
) -> SourceSpan:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_text_ref = object_store.put_text(f"raw/{project.id}.txt", text)
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 1",
        ownership_status="owned",
        raw_text_ref=raw_text_ref,
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash=f"hash-{project.id}",
        raw_text_ref=raw_text_ref,
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text(f"processed/{version.id}.md", text),
        raw_offset_map_ref=object_store.put_text(f"processed/{version.id}.offsets.json", "{}"),
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=None,
        scene_id=None,
        start_offset=0,
        end_offset=len(text),
        raw_start_offset=0,
        raw_end_offset=len(text),
        text_preview=text,
        speaker_entity_id=None,
        narration_layer="narrator",
    )
    session.add_all([project, raw_source, version, view])
    session.add(span)
    session.commit()
    return span


def _span_job(session: Session, span: SourceSpan) -> JobRecord:
    job = JobRecord(
        id=uuid4(),
        project_id=span_project_id(session, span),
        job_type="derive_facts",
        status="running",
        idempotency_key=f"derive_facts:{span.id}:manual",
        payload={
            "step": "derive_facts",
            "pipeline_version": "pipeline-v1",
            "source_span_id": str(span.id),
        },
    )
    session.add(job)
    session.flush()
    return job


def _run_job(
    session: Session,
    job_type: str,
    span: SourceSpan,
    handler: object,
    *,
    suffix: str = "one",
) -> JobRecord:
    job = JobRecord(
        id=uuid4(),
        project_id=span_project_id(session, span),
        job_type=job_type,
        status="queued",
        idempotency_key=f"{job_type}:{span.id}:{suffix}",
        payload={
            "step": job_type,
            "pipeline_version": "pipeline-v1",
            "source_span_id": str(span.id),
        },
    )
    session.add(job)
    session.commit()

    processed = DbWorker(session, {job_type: handler}).run_once(worker_id=f"worker-{job_type}")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    return job


def _source_pipeline_handlers(
    object_store: LocalObjectStore,
    *,
    pov_detection_provider=None,
    event_aggregation_provider=None,
) -> dict[str, object]:
    return {
        "split_structure": SourceStructureSplitHandler(object_store),
        "extract_mentions": ExtractMentionsHandler(object_store),
        "resolve_aliases": ResolveAliasesHandler(
            pov_detection_provider=pov_detection_provider,
            object_store=object_store,
        ),
        "extract_events": ExtractEventsHandler(object_store),
        "aggregate_events": AggregateEventsHandler(event_aggregation_provider),
        "derive_facts": DeriveFactsHandler(),
        "run_conflict_policy": RunConflictPolicyHandler(),
    }


def span_project_id(session: Session, span: SourceSpan) -> UUID:
    raw_source = session.get(RawSource, span.source_id)
    assert raw_source is not None
    return raw_source.project_id


class _StaticPovDetectionProvider:
    skill_name = "test_pov_detection"
    skill_version = "test-pov-detection.v1"

    def __init__(self, *, pov_character_name: str) -> None:
        self._pov_character_name = pov_character_name

    def detect(self, request: PovDetectionRequest) -> PovDetectionResult:
        return PovDetectionResult(
            pov_character_name=self._pov_character_name,
            pov_mode="third_limited",
            confidence=0.76,
            evidence_span_ids=[str(request.source_span_id)],
            uncertainty_reason=None,
        )
