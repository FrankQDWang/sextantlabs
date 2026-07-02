from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sextant.application.use_cases import OperateReviewItem
from sextant.contracts.use_cases import ReviewItemOperationInput
from sextant.infra.db.models import (
    AgentContextPackRecord,
    AuditEvent,
    Base,
    ContextPackReadinessRecord,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
    JobRecord,
    MemoryPage,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SkillRun,
    SourceDeltaRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
    StoryChapter,
    StoryScene,
)
from sextant.infra.memory_page_rewrite import MemoryPageRewriteHandler
from sextant.infra.memory_writeback import MemoryWritebackHandler
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.source_normalization import SourceNormalizationHandler
from sextant.infra.source_structure import SOURCE_SPAN_MAX_CHARS, SourceStructureSplitHandler
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.infra.worker import DbWorker
from sextant.infra.worker_handlers import build_worker_handlers
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider
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


def uow_factory(session: Session):
    return lambda: SqlAlchemyUnitOfWork(session)


def test_normalize_source_job_handler_creates_current_view(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_text_ref = object_store.put_text("raw/normalize.txt", "Mira crossed the quay.")
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
        raw_hash="hash-v1",
        raw_text_ref=raw_text_ref,
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="normalize_source",
        status="queued",
        idempotency_key=f"{version.id}:draft_profile_v1",
        payload={
            "step": "normalize_source",
            "pipeline_version": "pipeline-v1",
            "source_version_id": str(version.id),
            "cleaning_profile": "draft_profile_v1",
        },
    )
    session.add_all([project, raw_source, version, job])
    session.commit()

    worker = DbWorker(
        session,
        {"normalize_source": SourceNormalizationHandler(object_store)},
    )
    processed = worker.run_once(worker_id="worker-normalize")

    view = session.query(SourceProcessedView).one()
    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert view.version_id == version.id
    assert view.cleaning_profile == "draft_profile_v1"
    assert view.view_status == "current"
    assert object_store.get_text(view.markdown_ref) == "Mira crossed the quay."
    audit = session.query(AuditEvent).filter_by(event_type="source.normalized").one()
    assert audit.decision["source_version_id"] == str(version.id)
    split_job = session.query(JobRecord).filter_by(job_type="split_structure").one()
    assert split_job.status == "queued"
    assert split_job.payload["processed_view_id"] == str(view.id)
    assert split_job.payload["parser_version"] == "structure-parser-v1"


def test_normalize_source_rebuild_marks_previous_current_view_stale(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_text_ref = object_store.put_text("raw/rebuild.txt", "Mira kept the lantern.")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 2",
        ownership_status="owned",
        raw_text_ref=raw_text_ref,
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
        raw_text_ref=raw_text_ref,
    )
    old_view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text("processed/old.md", "old"),
        raw_offset_map_ref=object_store.put_text("processed/old.offsets.json", "{}"),
        view_status="current",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="normalize_source",
        status="queued",
        idempotency_key=f"{version.id}:semantic_profile_v2",
        payload={
            "step": "normalize_source",
            "pipeline_version": "pipeline-v1",
            "source_version_id": str(version.id),
            "cleaning_profile": "semantic_profile_v2",
        },
    )
    session.add_all([project, raw_source, version, old_view, job])
    session.commit()

    worker = DbWorker(
        session,
        {"normalize_source": SourceNormalizationHandler(object_store)},
    )
    worker.run_once(worker_id="worker-normalize")

    views = {
        view.cleaning_profile: view
        for view in session.query(SourceProcessedView).order_by(
            SourceProcessedView.cleaning_profile
        )
    }
    assert views["draft_profile_v1"].view_status == "stale"
    assert views["semantic_profile_v2"].view_status == "current"


def test_split_structure_job_handler_creates_chapter_and_scenes(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/structure.txt", "unused"),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    markdown = "Mira entered the quay.\n\nOrrin closed the iron gate."
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text("processed/structure.md", markdown),
        raw_offset_map_ref=object_store.put_text("processed/structure.offsets.json", "{}"),
        view_status="current",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
            "chapter_title": "Chapter 3",
        },
    )
    session.add_all([project, raw_source, version, view, job])
    session.commit()

    worker = DbWorker(
        session,
        {"split_structure": SourceStructureSplitHandler(object_store)},
    )
    processed = worker.run_once(worker_id="worker-structure")

    chapter = session.query(StoryChapter).one()
    scenes = session.query(StoryScene).order_by(StoryScene.scene_index).all()
    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert chapter.view_id == view.id
    assert chapter.title == "Chapter 3"
    assert chapter.start_offset == 0
    assert chapter.end_offset == len(markdown)
    assert [(scene.start_offset, scene.end_offset) for scene in scenes] == [
        (0, len("Mira entered the quay.")),
        (markdown.index("Orrin"), len(markdown)),
    ]
    audit = session.query(AuditEvent).filter_by(event_type="source.structure_split").one()
    assert audit.decision["chapter_count"] == 1
    assert audit.decision["scene_count"] == 2


def test_split_structure_chunks_long_scene_into_multiple_source_spans(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Long Scene",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/long-scene.txt", "unused"),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    sentence = "Mira checked the archive door and marked the hinge. "
    markdown = sentence * ((SOURCE_SPAN_MAX_CHARS // len(sentence)) + 4)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text("processed/long-scene.md", markdown),
        raw_offset_map_ref=object_store.put_text("processed/long-scene.offsets.json", "{}"),
        view_status="current",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
            "chapter_title": "Long Scene",
        },
    )
    session.add_all([project, raw_source, version, view, job])
    session.commit()

    processed = DbWorker(
        session,
        {"split_structure": SourceStructureSplitHandler(object_store)},
    ).run_once(worker_id="worker-structure")

    spans = session.query(SourceSpan).order_by(SourceSpan.start_offset).all()
    extract_jobs = session.query(JobRecord).filter_by(job_type="extract_mentions").all()
    assert processed is True
    assert len(spans) > 1
    assert len(extract_jobs) == len(spans)
    assert spans[0].start_offset == 0
    assert spans[-1].end_offset == len(markdown.rstrip())
    assert all(span.end_offset - span.start_offset <= SOURCE_SPAN_MAX_CHARS for span in spans)
    assert {span.scene_id for span in spans} == {session.query(StoryScene).one().id}


def test_split_structure_backpressures_extract_mention_scheduling_for_large_import(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Long Import Story")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="pdf_book",
        source_scope="reference_only",
        title="Collected Notes",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/large-import.txt", "unused"),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    sentence = "Observer logged the corridor pressure and catalogued the signal. "
    markdown = sentence * ((SOURCE_SPAN_MAX_CHARS // len(sentence)) * 5)
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="pdf_book_profile_v1",
        markdown_ref=object_store.put_text("processed/large-import.md", markdown),
        raw_offset_map_ref=object_store.put_text("processed/large-import.offsets.json", "{}"),
        view_status="current",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
            "chapter_title": "Collected Notes",
            "extract_batch_size": 2,
        },
    )
    session.add_all([project, raw_source, version, view, job])
    session.commit()

    worker = DbWorker(
        session,
        {
            "split_structure": SourceStructureSplitHandler(object_store),
            "extract_mentions": lambda _session, _job: None,
        },
    )
    assert worker.run_once(worker_id="worker-structure") is True

    spans = session.query(SourceSpan).order_by(SourceSpan.start_offset).all()
    extract_jobs = session.query(JobRecord).filter_by(job_type="extract_mentions").all()
    continuation_jobs = [
        record
        for record in session.query(JobRecord).filter_by(job_type="split_structure").all()
        if record.id != job.id
    ]

    assert len(spans) > 2
    assert len(extract_jobs) == 2
    assert len(continuation_jobs) == 1
    assert continuation_jobs[0].payload["trigger"] == "split_structure_backpressure"
    assert continuation_jobs[0].payload["extract_batch_size"] == 2

    for _ in range(20):
        if not worker.run_once(worker_id="worker-structure"):
            break

    final_extract_jobs = session.query(JobRecord).filter_by(job_type="extract_mentions").all()
    assert len(final_extract_jobs) == len(spans)
    assert all(job.status == "succeeded" for job in final_extract_jobs)
    assert (
        session.query(JobRecord)
        .filter(JobRecord.status.in_(("queued", "failed_retryable", "running")))
        .count()
        == 0
    )


def test_split_structure_job_handler_is_idempotent_for_existing_view(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 4",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/structure-idempotent.txt", "unused"),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    markdown = "First scene.\n\nSecond scene."
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref=object_store.put_text("processed/structure-idempotent.md", markdown),
        raw_offset_map_ref=object_store.put_text(
            "processed/structure-idempotent.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    first_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1:first",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
        },
    )
    second_job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="split_structure",
        status="queued",
        idempotency_key=f"{view.id}:parser-v1:second",
        payload={
            "step": "split_structure",
            "pipeline_version": "pipeline-v1",
            "processed_view_id": str(view.id),
            "parser_version": "parser-v1",
        },
    )
    session.add_all([project, raw_source, version, view, first_job, second_job])
    session.commit()

    worker = DbWorker(session, build_worker_handlers(object_store, LocalStoryDraftProvider()))
    processed_count = 0
    for _ in range(20):
        if not worker.run_once(worker_id="worker-structure"):
            break
        processed_count += 1

    assert processed_count >= 2
    assert session.query(StoryChapter).count() == 1
    assert session.query(StoryScene).count() == 2
    audits = session.query(AuditEvent).filter_by(event_type="source.structure_split").all()
    assert [audit.decision["created"] for audit in audits] == [True, False]


def seed_delta(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
    source_scope: str = "user_draft",
) -> tuple[SourceDeltaRecord, JobRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope=source_scope,
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/chapter-3.txt", text),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        delta_kind="replace",
        range_start=0,
        range_end=len(text),
        base_hash=version.raw_hash,
        submitted_text_ref=object_store.put_text("accepted/delta.txt", text),
        source_type="draft_manuscript",
        source_scope=source_scope,
        provenance={"author_edited": True},
        status="memory_writeback_queued",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="running",
        idempotency_key=f"{delta.id}:pipeline-v1",
        payload={
            "step": "run_memory_writeback",
            "pipeline_version": "pipeline-v1",
            "source_delta_id": str(delta.id),
        },
    )
    session.add_all([project, raw_source, version, delta, job])
    session.commit()
    return delta, job


def test_low_risk_writeback_promotes_memory_and_graph(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    handler = MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())

    handler(session, job)

    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_completed"
    assert session.query(SourceProcessedView).count() == 1
    assert session.query(SourceSpan).count() == 1
    assert session.query(EvidenceLogEntry).count() == 1

    fact = session.query(FactAssertionRecord).one()
    assert fact.fact_status == "canon"
    assert fact.promotion_decision_id is not None

    page = session.query(MemoryPage).one()
    assert page.current_canon["facts"][0]["predicate"] == "owns"
    assert session.query(GraphProjectionEdge).one().edge_status == "canon"
    assert session.query(SkillRun).filter_by(skill_name="local_memory_extraction").count() == 1
    assert session.query(AuditEvent).filter_by(event_type="memory_writeback.completed").count() == 1
    readiness = session.query(ContextPackReadinessRecord).one()
    span = session.query(SourceSpan).one()
    assert readiness.status == "pending"
    assert readiness.reason == "memory_dependency_changed"
    assert readiness.source_span_id == span.id
    assert readiness.source_delta_id == delta.id
    assert readiness.evidence_refs == [{"type": "source_span", "id": str(span.id)}]
    assert session.query(AgentContextPackRecord).count() == 0
    assert session.query(JobRecord).filter_by(job_type="build_context_pack").count() == 0


def test_thread_update_writeback_adds_source_backed_memory_page_open_thread(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | opens | map-origin | "
            "The lantern map origin remains unresolved. | low"
        ),
    )

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    span = session.query(SourceSpan).one()
    page = session.query(MemoryPage).one()
    evidence = session.query(EvidenceLogEntry).one()
    readiness = session.query(ContextPackReadinessRecord).one()
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_completed"
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert page.target_ref == {"type": "character", "id": "mira"}
    assert page.current_canon == {"facts": []}
    assert page.open_threads == [
        {
            "id": "map-origin",
            "update_type": "opens",
            "summary": "The lantern map origin remains unresolved.",
            "risk_level": "low",
            "source_delta_id": str(delta.id),
            "source_span_ids": [str(span.id)],
            "status": "open",
        }
    ]
    assert {"type": "source_delta", "id": str(delta.id)} in page.source_refs
    assert {"type": "source_span", "id": str(span.id)} in page.source_refs
    assert evidence.log_type == "thread_update"
    assert evidence.target_ref == {
        "type": "memory_page_thread",
        "id": "map-origin",
        "memory_page_id": str(page.id),
    }
    assert evidence.fact_id is None
    assert evidence.event_id is None
    assert evidence.source_span_ids == [str(span.id)]
    assert readiness.status == "pending"
    assert readiness.source_span_id == span.id
    assert {"type": "memory_page", "id": str(page.id)} in readiness.affected_refs
    skill_run = session.query(SkillRun).filter_by(skill_name="local_memory_extraction").one()
    assert skill_run.structured_output["thread_updates"] == [
        {
            "target_ref": {"type": "character", "id": "mira"},
            "update_type": "opens",
            "thread_id": "map-origin",
            "description": "The lantern map origin remains unresolved.",
            "risk_level": "low",
        }
    ]


def test_thread_update_writeback_filters_existing_open_thread_source_span_evidence(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | opens | map-origin | "
            "The lantern map origin remains unresolved. | low"
        ),
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/thread-page-existing.md",
            "Mira still has no source for the lantern map.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/thread-page-existing.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=45,
        raw_start_offset=0,
        raw_end_offset=45,
        text_preview="Mira still has no source for the lantern map.",
        narration_layer="narrator",
    )
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-open-thread.txt", "Other open thread."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-open-thread-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-open-thread.md",
            "Other open thread.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-open-thread.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=18,
        raw_start_offset=0,
        raw_end_offset=18,
        text_preview="Other open thread.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-origin",
                "update_type": "opens",
                "summary": "Earlier map-origin thread.",
                "risk_level": "low",
                "source_delta_id": str(delta.id),
                "source_span_ids": [
                    str(existing_span.id),
                    str(foreign_span.id),
                    "not-a-source-span-id",
                ],
                "status": "open",
            }
        ],
        contradictions=[],
        source_refs=[],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all(
        [
            view,
            existing_span,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            page,
        ]
    )
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    rewritten = session.get(MemoryPage, page.id)
    spans = session.query(SourceSpan).order_by(SourceSpan.created_at, SourceSpan.id).all()
    project_span_ids = {str(span.id) for span in spans if span.source_id == delta.source_id}
    assert set(rewritten.open_threads[0]["source_span_ids"]) == project_span_ids
    assert str(foreign_span.id) not in rewritten.open_threads[0]["source_span_ids"]
    assert "not-a-source-span-id" not in rewritten.open_threads[0]["source_span_ids"]
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_high_risk_thread_update_creates_review_without_memory_page_write(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | closes | map-origin | "
            "The lantern map origin is revealed as enemy bait. | high"
        ),
    )

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    span = session.query(SourceSpan).one()
    evidence = session.query(EvidenceLogEntry).one()
    review = session.query(ReviewItemRecord).one()
    readiness = session.query(ContextPackReadinessRecord).one()
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_completed"
    assert session.query(MemoryPage).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert evidence.log_type == "thread_update_review_required"
    assert evidence.target_ref == {
        "type": "proposed_thread_update",
        "id": "map-origin",
        "target_ref": {"type": "character", "id": "mira"},
    }
    assert evidence.fact_id is None
    assert evidence.event_id is None
    assert evidence.source_span_ids == [str(span.id)]
    assert review.review_type == "continuity_warning"
    assert review.severity == "high"
    assert review.status == "open"
    assert review.summary == "The lantern map origin is revealed as enemy bait."
    assert review.affected_refs == {
        "type": "proposed_thread_update",
        "id": "map-origin",
        "target_ref": {"type": "character", "id": "mira"},
        "update_type": "closes",
    }
    assert review.new_evidence == {
        "source_span_ids": [str(span.id)],
        "evidence_log_entry_ids": [str(evidence.id)],
    }
    assert review.default_action == "ask_author"
    assert readiness.status == "pending"
    assert readiness.source_span_id == span.id
    assert {"type": "review_item", "id": str(review.id)} in readiness.affected_refs


def test_thread_update_review_merge_filters_existing_source_span_evidence(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | closes | map-origin | "
            "The lantern map origin is revealed as enemy bait. | high"
        ),
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/thread-existing.md",
            "Mira keeps asking where the lantern map came from.",
        ),
        raw_offset_map_ref=object_store.put_text("processed/thread-existing.offsets.json", "{}"),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=49,
        raw_start_offset=0,
        raw_end_offset=49,
        text_preview="Mira keeps asking where the lantern map came from.",
        narration_layer="narrator",
    )
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-thread.txt", "Other thread."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-thread-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text("processed/foreign-thread.md", "Other thread."),
        raw_offset_map_ref=object_store.put_text("processed/foreign-thread.offsets.json", "{}"),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=13,
        raw_start_offset=0,
        raw_end_offset=13,
        text_preview="Other thread.",
        narration_layer="narrator",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="continuity_warning",
        severity="high",
        status="open",
        summary="The lantern map origin is revealed as enemy bait.",
        affected_refs={
            "type": "proposed_thread_update",
            "id": "map-origin",
            "target_ref": {"type": "character", "id": "mira"},
            "update_type": "closes",
        },
        new_evidence={
            "source_span_ids": [
                str(existing_span.id),
                str(foreign_span.id),
                "not-a-source-span-id",
            ],
            "evidence_log_entry_ids": [],
        },
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}],
        default_action="ask_author",
    )
    session.add_all(
        [
            view,
            existing_span,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            review,
        ]
    )
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    review = session.query(ReviewItemRecord).one()
    spans = session.query(SourceSpan).order_by(SourceSpan.created_at, SourceSpan.id).all()
    project_span_ids = {str(span.id) for span in spans if span.source_id == delta.source_id}
    assert set(review.new_evidence["source_span_ids"]) == project_span_ids
    assert str(foreign_span.id) not in review.new_evidence["source_span_ids"]
    assert "not-a-source-span-id" not in review.new_evidence["source_span_ids"]
    assert session.query(MemoryPage).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_thread_update_review_merge_filters_existing_evidence_log_entries(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | closes | map-origin | "
            "The lantern map origin is revealed as enemy bait. | high"
        ),
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/thread-evidence-log-existing.md",
            "Mira keeps asking where the lantern map came from.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/thread-evidence-log-existing.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=49,
        raw_start_offset=0,
        raw_end_offset=49,
        text_preview="Mira keeps asking where the lantern map came from.",
        narration_layer="narrator",
    )
    target_ref = {
        "type": "proposed_thread_update",
        "id": "map-origin",
        "target_ref": {"type": "character", "id": "mira"},
    }
    valid_existing_evidence = EvidenceLogEntry(
        id=uuid4(),
        project_id=delta.project_id,
        log_type="thread_update_review_required",
        target_ref=target_ref,
        fact_id=None,
        event_id=None,
        source_span_ids=[str(existing_span.id)],
        log_status="written",
    )
    same_project_wrong_target = EvidenceLogEntry(
        id=uuid4(),
        project_id=delta.project_id,
        log_type="thread_update_review_required",
        target_ref={
            "type": "proposed_thread_update",
            "id": "other-thread",
            "target_ref": {"type": "character", "id": "mira"},
        },
        fact_id=None,
        event_id=None,
        source_span_ids=[str(existing_span.id)],
        log_status="written",
    )
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-thread-evidence.txt", "Other thread."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-thread-evidence-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-thread-evidence.md",
            "Other thread.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-thread-evidence.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=13,
        raw_start_offset=0,
        raw_end_offset=13,
        text_preview="Other thread.",
        narration_layer="narrator",
    )
    foreign_evidence = EvidenceLogEntry(
        id=uuid4(),
        project_id=foreign_project.id,
        log_type="thread_update_review_required",
        target_ref=target_ref,
        fact_id=None,
        event_id=None,
        source_span_ids=[str(foreign_span.id)],
        log_status="written",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="continuity_warning",
        severity="high",
        status="open",
        summary="The lantern map origin is revealed as enemy bait.",
        affected_refs={**target_ref, "update_type": "closes"},
        new_evidence={
            "source_span_ids": [str(existing_span.id)],
            "evidence_log_entry_ids": [
                str(valid_existing_evidence.id),
                str(same_project_wrong_target.id),
                str(foreign_evidence.id),
                "not-an-evidence-log-id",
            ],
        },
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}],
        default_action="ask_author",
    )
    session.add_all(
        [
            view,
            existing_span,
            valid_existing_evidence,
            same_project_wrong_target,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            foreign_evidence,
            review,
        ]
    )
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    review = session.query(ReviewItemRecord).one()
    new_evidence = session.query(EvidenceLogEntry).filter_by(project_id=delta.project_id).all()
    new_evidence_ids = {
        str(entry.id)
        for entry in new_evidence
        if entry.id not in {valid_existing_evidence.id, same_project_wrong_target.id}
    }
    assert set(review.new_evidence["evidence_log_entry_ids"]) == {
        str(valid_existing_evidence.id),
        *new_evidence_ids,
    }
    assert str(same_project_wrong_target.id) not in review.new_evidence["evidence_log_entry_ids"]
    assert str(foreign_evidence.id) not in review.new_evidence["evidence_log_entry_ids"]
    assert "not-an-evidence-log-id" not in review.new_evidence["evidence_log_entry_ids"]
    assert session.query(MemoryPage).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_accepting_high_risk_thread_update_review_applies_memory_page_thread(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | closes | map-origin | "
            "The lantern map origin is revealed as enemy bait. | high"
        ),
    )

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    actor_id = uuid4()
    session.add(
        ProjectMembership(
            id=uuid4(),
            project_id=delta.project_id,
            actor_id=actor_id,
            role="editor",
            status="active",
        )
    )
    session.commit()

    review = session.query(ReviewItemRecord).one()
    span = session.query(SourceSpan).one()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=delta.project_id,
            actor_id=actor_id,
            request_id="request-thread-review-accept",
            idempotency_key="review-thread-accept-map-origin",
            review_item_id=review.id,
            operation="resolve",
            resolution="accept",
            author_note="Accept the payoff as written.",
        )
    )

    page = session.query(MemoryPage).one()
    applied_evidence = session.query(EvidenceLogEntry).filter_by(log_type="thread_update").one()
    readiness_records = session.query(ContextPackReadinessRecord).all()
    assert output.status == "resolved"
    assert output.resolution == "accept"
    assert output.side_effects["memory_pages"] == "thread_update_applied"
    assert output.side_effects["graph_projection"] == "unchanged"
    assert output.side_effects["memory_page_ids"] == [str(page.id)]
    assert output.side_effects["thread_update_id"] == "map-origin"
    assert session.get(ReviewItemRecord, review.id).status == "resolved"
    assert page.target_ref == {"type": "character", "id": "mira"}
    assert page.current_canon == {"facts": []}
    assert page.open_threads == [
        {
            "id": "map-origin",
            "update_type": "closes",
            "summary": "The lantern map origin is revealed as enemy bait.",
            "risk_level": "high",
            "source_delta_id": str(delta.id),
            "source_span_ids": [str(span.id)],
            "status": "closed",
        }
    ]
    assert {"type": "source_delta", "id": str(delta.id)} in page.source_refs
    assert {"type": "source_span", "id": str(span.id)} in page.source_refs
    assert applied_evidence.target_ref == {
        "type": "memory_page_thread",
        "id": "map-origin",
        "memory_page_id": str(page.id),
    }
    assert applied_evidence.fact_id is None
    assert applied_evidence.event_id is None
    assert applied_evidence.source_span_ids == [str(span.id)]
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert any(
        record.status == "stale"
        and record.reason == "review_dependency_changed"
        and {"type": "memory_page", "id": str(page.id)} in record.affected_refs
        for record in readiness_records
    )


def test_accepting_high_risk_thread_update_review_filters_existing_thread_evidence(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text=(
            "THREAD: character:mira | closes | map-origin | "
            "The lantern map origin is revealed as enemy bait. | high"
        ),
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    review = session.query(ReviewItemRecord).one()
    span = session.query(SourceSpan).one()
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-review-accept.txt", "Other thread."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-review-accept-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text("processed/foreign-review-accept.md", "Other thread."),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-review-accept.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=13,
        raw_start_offset=0,
        raw_end_offset=13,
        text_preview="Other thread.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="character",
        target_ref={"type": "character", "id": "mira"},
        title="mira",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-origin",
                "update_type": "opens",
                "summary": "Earlier map-origin thread.",
                "risk_level": "low",
                "source_delta_id": str(delta.id),
                "source_span_ids": [
                    str(span.id),
                    str(foreign_span.id),
                    "not-a-source-span-id",
                ],
                "status": "open",
            }
        ],
        contradictions=[],
        source_refs=[],
        canon_status="current",
        memory_depth="scene",
    )
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=delta.project_id,
        actor_id=actor_id,
        role="editor",
        status="active",
    )
    session.add_all(
        [
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            page,
            membership,
        ]
    )
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=delta.project_id,
            actor_id=actor_id,
            request_id="request-thread-review-accept-contaminated-page",
            idempotency_key="review-thread-accept-contaminated-page",
            review_item_id=review.id,
            operation="resolve",
            resolution="accept",
            author_note="Accept the payoff as written.",
        )
    )

    rewritten = session.get(MemoryPage, page.id)
    assert output.status == "resolved"
    assert rewritten.open_threads[0]["source_span_ids"] == [str(span.id)]
    assert str(foreign_span.id) not in rewritten.open_threads[0]["source_span_ids"]
    assert "not-a-source-span-id" not in rewritten.open_threads[0]["source_span_ids"]
    assert session.query(GraphProjectionEdge).count() == 0


def test_review_resolution_side_effects_filter_review_source_span_evidence(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, _job = seed_delta(
        session,
        object_store,
        text="FACT: character:subject-alpha | knows | secret:hidden-marker | medium",
    )
    source_text = "Subject Alpha may know the secret too early."
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/review-side-effect.md",
            source_text,
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/review-side-effect.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=len(source_text),
        raw_start_offset=0,
        raw_end_offset=len(source_text),
        text_preview=source_text,
        narration_layer="narrator",
    )
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-review-side-effect.txt", "Other review."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-review-side-effect-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-review-side-effect.md",
            "Other review.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-review-side-effect.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=13,
        raw_start_offset=0,
        raw_end_offset=13,
        text_preview="Other review.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="character",
        target_ref={"type": "character", "id": "subject-alpha"},
        title="subject-alpha",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Subject Alpha may know too much.",
        affected_refs={},
        new_evidence={
            "source_span_ids": [
                str(span.id),
                str(foreign_span.id),
                "not-a-source-span-id",
            ]
        },
        existing_evidence={},
        suggested_actions=[{"resolution": "accepted_as_change"}],
        default_action="review",
    )
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=delta.project_id,
        actor_id=actor_id,
        role="editor",
        status="active",
    )
    session.add_all(
        [
            view,
            span,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            page,
            review,
            membership,
        ]
    )
    session.commit()

    output = OperateReviewItem(uow_factory(session)).execute(
        ReviewItemOperationInput(
            project_id=delta.project_id,
            actor_id=actor_id,
            request_id="request-review-side-effect-filter",
            idempotency_key="review-side-effect-filter",
            review_item_id=review.id,
            operation="resolve",
            resolution="accepted_as_change",
            author_note="作者确认这是新变化。",
        )
    )

    rewritten = session.get(MemoryPage, page.id)
    assert output.status == "resolved"
    assert output.side_effects["memory_pages"] == "marked_stale"
    assert rewritten.canon_status == "stale"
    assert rewritten.contradictions[0]["source_span_ids"] == [str(span.id)]
    assert str(foreign_span.id) not in rewritten.contradictions[0]["source_span_ids"]
    assert "not-a-source-span-id" not in rewritten.contradictions[0]["source_span_ids"]


def test_writeback_merges_duplicate_canon_fact_from_existing_source_pipeline(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text("processed/existing.md", "Mira took the Lantern Map."),
        raw_offset_map_ref=object_store.put_text("processed/existing.offsets.json", "{}"),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Mira took the Lantern Map.",
        narration_layer="narrator",
    )
    foreign_project = Project(id=uuid4(), name="Other Canon Merge Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-canon-merge.txt", "Other canon evidence."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-canon-merge-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-canon-merge.md",
            "Other canon evidence.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-canon-merge.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=21,
        raw_start_offset=0,
        raw_end_offset=21,
        text_preview="Other canon evidence.",
        narration_layer="narrator",
    )
    existing_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[
            str(existing_span.id),
            str(foreign_span.id),
            "not-a-source-span-id",
        ],
        confidence=0.82,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={
            "facts": [
                {
                    "fact_id": str(existing_fact.id),
                    "predicate": "owns",
                    "object_ref": existing_fact.object_ref,
                    "evidence_span_ids": [
                        str(existing_span.id),
                        str(foreign_span.id),
                        "not-a-source-span-id",
                    ],
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[
            {"type": "source_span", "id": str(existing_span.id)},
            {"type": "source_span", "id": str(foreign_span.id)},
            {"type": "source_span", "id": "not-a-source-span-id"},
        ],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all(
        [
            view,
            existing_span,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            existing_fact,
            page,
        ]
    )
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    fact = session.query(FactAssertionRecord).one()
    new_span = next(
        span
        for span in session.query(SourceSpan).order_by(SourceSpan.created_at, SourceSpan.id)
        if span.source_id == delta.source_id and span.id != existing_span.id
    )
    expected_span_ids = [str(existing_span.id), str(new_span.id)]
    assert fact.id == existing_fact.id
    assert fact.evidence_span_ids == expected_span_ids
    page = session.query(MemoryPage).one()
    assert page.current_canon["facts"] == [
        {
            "fact_id": str(existing_fact.id),
            "predicate": "owns",
            "object_ref": existing_fact.object_ref,
            "evidence_span_ids": expected_span_ids,
        }
    ]
    assert {"type": "source_span", "id": str(existing_span.id)} in page.source_refs
    assert {"type": "source_span", "id": str(new_span.id)} in page.source_refs
    assert {"type": "source_span", "id": str(foreign_span.id)} not in page.source_refs
    assert {"type": "source_span", "id": "not-a-source-span-id"} not in page.source_refs
    assert session.query(GraphProjectionEdge).filter_by(relation="owns").count() == 1


def test_low_risk_writeback_conflicting_existing_canon_fact_requires_review(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:ada | located_in | location:west-tower | low",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/ada-east-tower.md",
            "Ada entered East Tower.",
        ),
        raw_offset_map_ref=object_store.put_text("processed/ada-east-tower.offsets.json", "{}"),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=23,
        raw_start_offset=0,
        raw_end_offset=23,
        text_preview="Ada entered East Tower.",
        narration_layer="narrator",
    )
    existing_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "ada", "label": "ada"},
        predicate="located_in",
        object_ref={"type": "location", "id": "east-tower", "label": "east-tower"},
        fact_status="canon",
        evidence_span_ids=[str(existing_span.id), "not-a-source-span-id"],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([view, existing_span, existing_fact])
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    facts = {
        fact.object_ref["id"]: fact
        for fact in session.query(FactAssertionRecord).order_by(FactAssertionRecord.created_at)
    }
    assert facts["east-tower"].fact_status == "canon"
    assert facts["west-tower"].fact_status == "disputed"
    review = session.query(ReviewItemRecord).one()
    new_span = next(
        span
        for span in session.query(SourceSpan).order_by(SourceSpan.created_at, SourceSpan.id)
        if span.id != existing_span.id
    )
    assert review.review_type == "object_state_conflict"
    assert review.status == "open"
    assert review.affected_refs == {"fact_id": str(facts["west-tower"].id)}
    assert review.new_evidence["source_span_ids"] == [str(new_span.id)]
    assert review.existing_evidence == {
        "fact_id": str(existing_fact.id),
        "source_span_ids": [str(existing_span.id)],
    }
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_writeback_merges_duplicate_disputed_fact_review_evidence(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | knows | secret:orrin_identity | medium",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=delta.previous_version_id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text("processed/disputed.md", "Mira knows the secret."),
        raw_offset_map_ref=object_store.put_text("processed/disputed.offsets.json", "{}"),
        view_status="current",
    )
    existing_span = SourceSpan(
        id=uuid4(),
        source_id=delta.source_id,
        version_id=delta.previous_version_id,
        view_id=view.id,
        start_offset=0,
        end_offset=22,
        raw_start_offset=0,
        raw_end_offset=22,
        text_preview="Mira knows the secret.",
        narration_layer="narrator",
    )
    existing_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="knows",
        object_ref={"type": "secret", "id": "orrin_identity"},
        fact_status="disputed",
        evidence_span_ids=[str(existing_span.id)],
        confidence=0.6,
        source_scope="user_draft",
    )
    foreign_project = Project(id=uuid4(), name="Other Story")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-disputed.txt", "Other story."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text("processed/foreign-disputed.md", "Other story."),
        raw_offset_map_ref=object_store.put_text("processed/foreign-disputed.offsets.json", "{}"),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=12,
        raw_start_offset=0,
        raw_end_offset=12,
        text_preview="Other story.",
        narration_layer="narrator",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="knows requires author review before canon promotion.",
        affected_refs={"fact_id": str(existing_fact.id)},
        new_evidence={
            "source_span_ids": [
                str(existing_span.id),
                str(foreign_span.id),
                "not-a-source-span-id",
            ]
        },
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}],
        default_action="review",
    )
    session.add_all(
        [
            view,
            existing_span,
            existing_fact,
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            review,
        ]
    )
    session.commit()

    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)

    fact = session.query(FactAssertionRecord).one()
    review = session.query(ReviewItemRecord).one()
    spans = session.query(SourceSpan).order_by(SourceSpan.created_at, SourceSpan.id).all()
    project_span_ids = {str(span.id) for span in spans if span.source_id == delta.source_id}
    assert fact.id == existing_fact.id
    assert fact.fact_status == "disputed"
    assert set(fact.evidence_span_ids) == project_span_ids
    assert set(review.new_evidence["source_span_ids"]) == project_span_ids
    assert str(foreign_span.id) not in review.new_evidence["source_span_ids"]
    assert "not-a-source-span-id" not in review.new_evidence["source_span_ids"]


def test_memory_page_rewrite_rebuilds_from_remaining_canon_facts(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    fact = session.query(FactAssertionRecord).one()
    page = session.query(MemoryPage).one()
    fact.fact_status = "disputed"
    page.canon_status = "stale"
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add(rewrite_job)
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.current_canon == {"facts": []}
    edge = session.query(GraphProjectionEdge).one()
    assert edge.source_ref == {"type": "fact_assertion", "id": str(fact.id)}
    assert edge.edge_status == "disputed"
    assert session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").count() == 1


def test_memory_page_rewrite_rebuilds_sections_from_events_and_reviews(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    page = session.query(MemoryPage).one()
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=delta.project_id,
        event_type="discovery",
        title="Mira finds the Lantern Map",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira"}],
        objects=[{"type": "object", "id": "lantern-map"}],
        location_entity_id=None,
        story_time="Chapter 1",
        summary="Mira finds the Lantern Map in Harbor Nine.",
        consequence_summary="The map becomes available to Mira.",
        evidence_span_ids=[str(span.id)],
    )
    present_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="present_at",
        object_ref={"type": "event", "id": str(event.id)},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    relationship_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="ally_of",
        object_ref={"type": "character", "id": "orrin"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=delta.project_id,
        review_type="continuity_warning",
        severity="medium",
        status="open",
        summary="Mira's map knowledge needs follow-up.",
        affected_refs={"memory_page_id": str(page.id)},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[{"resolution": "accept"}],
        default_action="review",
    )
    page.canon_status = "stale"
    page.appearance_log = []
    page.event_log = []
    page.relationships = []
    page.open_threads = []
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:section-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add_all([event, present_fact, relationship_fact, review, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    assert rewritten.canon_status == "rebuilt"
    assert {fact["predicate"] for fact in rewritten.current_canon["facts"]} == {
        "ally_of",
        "owns",
        "present_at",
    }
    assert rewritten.appearance_log == [
        {
            "fact_id": str(present_fact.id),
            "predicate": "present_at",
            "target_ref": {"type": "event", "id": str(event.id)},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert rewritten.event_log[0]["event_id"] == str(event.id)
    assert rewritten.event_log[0]["title"] == "Mira finds the Lantern Map"
    assert {"type": "canonical_event", "id": str(event.id)} in rewritten.source_refs
    assert rewritten.relationships == [
        {
            "fact_id": str(relationship_fact.id),
            "predicate": "ally_of",
            "target_ref": {"type": "character", "id": "orrin"},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert rewritten.open_threads == [
        {
            "review_item_id": str(review.id),
            "review_type": "continuity_warning",
            "severity": "medium",
            "summary": "Mira's map knowledge needs follow-up.",
        }
    ]
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["event_log_count"] == 1
    assert audit.decision["open_thread_count"] == 1


def test_memory_page_rewrite_synthesizes_character_agency_profile_from_canon_facts(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    page = session.query(MemoryPage).one()
    profile_facts = [
        FactAssertionRecord(
            id=uuid4(),
            project_id=delta.project_id,
            subject_ref={"type": "character", "id": "mira"},
            predicate="core_desire",
            object_ref={
                "type": "literal",
                "id": "prove-agency",
                "value": "证明自己不是被命运摆布的人。",
            },
            fact_status="canon",
            evidence_span_ids=[str(span.id)],
            confidence=0.93,
            source_scope="author_note",
            promotion_decision_id=uuid4(),
        ),
        FactAssertionRecord(
            id=uuid4(),
            project_id=delta.project_id,
            subject_ref={"type": "character", "id": "mira"},
            predicate="immediate_want",
            object_ref={"type": "literal", "id": "recover-map", "value": "拿回灯图。"},
            fact_status="canon",
            evidence_span_ids=[str(span.id)],
            confidence=0.9,
            source_scope="author_note",
            promotion_decision_id=uuid4(),
        ),
        FactAssertionRecord(
            id=uuid4(),
            project_id=delta.project_id,
            subject_ref={"type": "character", "id": "mira"},
            predicate="moral_boundary",
            object_ref={
                "type": "literal",
                "id": "no-innocents",
                "value": "不会牺牲无辜者换取线索。",
            },
            fact_status="canon",
            evidence_span_ids=[str(span.id)],
            confidence=0.88,
            source_scope="author_note",
            promotion_decision_id=uuid4(),
        ),
        FactAssertionRecord(
            id=uuid4(),
            project_id=delta.project_id,
            subject_ref={"type": "character", "id": "mira"},
            predicate="relationship_stance",
            object_ref={
                "type": "literal",
                "id": "mira-kestrel-stance",
                "value": "对 Kestrel 表面合作，实际开始怀疑。",
                "target_ref": {"type": "character", "id": "kestrel", "label": "Kestrel"},
            },
            fact_status="canon",
            evidence_span_ids=[str(span.id)],
            confidence=0.86,
            source_scope="author_note",
            promotion_decision_id=uuid4(),
        ),
    ]
    page.current_canon = {"facts": []}
    page.canon_status = "stale"
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:agency-profile-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add_all([*profile_facts, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    profile = rewritten.current_canon["agency_profile"]
    assert profile["core_desire"] == {
        "value": "证明自己不是被命运摆布的人。",
        "fact_id": str(profile_facts[0].id),
        "source_span_ids": [str(span.id)],
    }
    assert profile["immediate_want"] == {
        "value": "拿回灯图。",
        "fact_id": str(profile_facts[1].id),
        "source_span_ids": [str(span.id)],
    }
    assert profile["moral_boundary"] == {
        "value": "不会牺牲无辜者换取线索。",
        "fact_id": str(profile_facts[2].id),
        "source_span_ids": [str(span.id)],
    }
    assert profile["relationship_stance"] == [
        {
            "value": "对 Kestrel 表面合作，实际开始怀疑。",
            "target_ref": {"type": "character", "id": "kestrel", "label": "Kestrel"},
            "fact_id": str(profile_facts[3].id),
            "source_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "fact_assertion", "id": str(profile_facts[0].id)} in rewritten.source_refs
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["agency_profile_field_count"] == 4


def test_memory_page_rewrite_ignores_agency_profile_facts_without_valid_source_span(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    page = session.query(MemoryPage).one()
    invalid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="core_desire",
        object_ref={"type": "literal", "id": "invalid-evidence", "value": "Do not include me."},
        fact_status="canon",
        evidence_span_ids=[str(uuid4())],
        confidence=0.93,
        source_scope="author_note",
        promotion_decision_id=uuid4(),
    )
    valid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="immediate_want",
        object_ref={"type": "literal", "id": "recover-map", "value": "拿回灯图。"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="author_note",
        promotion_decision_id=uuid4(),
    )
    page.current_canon = {"facts": []}
    page.canon_status = "stale"
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:agency-profile-evidence-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add_all([invalid_fact, valid_fact, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    profile = rewritten.current_canon["agency_profile"]
    assert "core_desire" not in profile
    assert profile["immediate_want"] == {
        "value": "拿回灯图。",
        "fact_id": str(valid_fact.id),
        "source_span_ids": [str(span.id)],
    }
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["agency_profile_field_count"] == 1


def test_memory_page_rewrite_adds_location_events_without_occurred_at_fact(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    location = StoryCanonicalEntity(
        id=uuid4(),
        project_id=delta.project_id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="canon",
        cast_tier=None,
        first_seen_scene_id=None,
        description=None,
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=delta.project_id,
        event_type="discovery",
        title="Mira finds the lantern map at Harbor Nine",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira"}],
        objects=[{"type": "object", "id": "lantern-map"}],
        location_entity_id=location.id,
        story_time="Chapter 1 / Scene 2",
        summary="Mira finds the lantern map beside the old ferry gate.",
        consequence_summary="The harbor becomes tied to the map mystery.",
        evidence_span_ids=[str(span.id)],
    )
    location_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="location",
        target_ref={
            "type": "location",
            "id": str(location.id),
            "label": "Harbor Nine",
            "canonical_entity_id": str(location.id),
        },
        title="Harbor Nine",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{location_page.id}:location-event-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(location_page.id),
        },
    )
    session.add_all([location, event, location_page, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, location_page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.current_canon == {"facts": []}
    assert rewritten.event_log == [
        {
            "event_id": str(event.id),
            "title": "Mira finds the lantern map at Harbor Nine",
            "event_type": "discovery",
            "summary": "Mira finds the lantern map beside the old ferry gate.",
            "story_time": "Chapter 1 / Scene 2",
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "canonical_event", "id": str(event.id)} in rewritten.source_refs
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["event_log_count"] == 1


def test_memory_page_rewrite_builds_event_page_from_canonical_event(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    location = StoryCanonicalEntity(
        id=uuid4(),
        project_id=delta.project_id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="canon",
        cast_tier=None,
        first_seen_scene_id=None,
        description=None,
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=delta.project_id,
        event_type="object_transfer",
        title="Lantern Map Stolen",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=location.id,
        story_time="Chapter 3 / Scene 2",
        summary="Kestrel steals the Lantern Map while Mira searches the quay.",
        cause_summary="Kestrel needs the map before the harbor gate closes.",
        consequence_summary="The Lantern Map changes hands and Mira loses her route.",
        evidence_span_ids=[str(span.id)],
    )
    event_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="event",
        target_ref={"type": "event", "id": str(event.id), "label": event.title},
        title=event.title,
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{event_page.id}:event-current-canon-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(event_page.id),
        },
    )
    session.add_all([location, event, event_page, rewrite_job])
    session.commit()
    fact_count = session.query(FactAssertionRecord).count()
    review_count = session.query(ReviewItemRecord).count()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, event_page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.current_canon == {
        "facts": [],
        "event_summary": {
            "event_id": str(event.id),
            "title": "Lantern Map Stolen",
            "event_type": "object_transfer",
            "summary": "Kestrel steals the Lantern Map while Mira searches the quay.",
            "story_time": "Chapter 3 / Scene 2",
            "evidence_span_ids": [str(span.id)],
        },
        "participants": [
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        "objects": [{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        "location": {
            "type": "location",
            "id": str(location.id),
            "label": "Harbor Nine",
        },
        "cause": {
            "summary": "Kestrel needs the map before the harbor gate closes.",
            "evidence_span_ids": [str(span.id)],
        },
        "consequences": [
            {
                "summary": "The Lantern Map changes hands and Mira loses her route.",
                "evidence_span_ids": [str(span.id)],
            }
        ],
    }
    assert {"type": "canonical_event", "id": str(event.id)} in rewritten.source_refs
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert session.query(FactAssertionRecord).count() == fact_count
    assert session.query(ReviewItemRecord).count() == review_count
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["event_current_canon_count"] == 1


def test_memory_page_rewrite_filters_event_evidence_to_same_project_source_spans(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:subject-alpha | owns | object:object-beta | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    foreign_project = Project(id=uuid4(), name="Foreign Event Rewrite Project")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Foreign Event Rewrite Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text(
            "raw/foreign-event-memory-rewrite.txt",
            "Foreign event rewrite.",
        ),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-event-memory-rewrite-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-event-memory-rewrite.md",
            "Foreign event rewrite.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-event-memory-rewrite.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=22,
        raw_start_offset=0,
        raw_end_offset=22,
        text_preview="Foreign event rewrite.",
        narration_layer="narrator",
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=delta.project_id,
        event_type="discovery",
        title="Subject Alpha finds Object Beta",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "subject-alpha"}],
        objects=[{"type": "object", "id": "object-beta"}],
        location_entity_id=None,
        story_time="Chapter 1",
        summary="Subject Alpha finds Object Beta.",
        cause_summary="Subject Alpha needed a clue.",
        consequence_summary="Object Beta changes hands.",
        evidence_span_ids=[str(span.id), str(foreign_span.id), "not-a-source-span-id"],
    )
    event_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="event",
        target_ref={"type": "event", "id": str(event.id)},
        title="Subject Alpha finds Object Beta",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{event_page.id}:event-evidence-filter-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(event_page.id),
        },
    )
    session.add_all(
        [
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            event,
            event_page,
            rewrite_job,
        ]
    )
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, event_page.id)
    assert rewritten.current_canon["event_summary"]["evidence_span_ids"] == [str(span.id)]
    assert rewritten.current_canon["cause"]["evidence_span_ids"] == [str(span.id)]
    assert rewritten.current_canon["consequences"][0]["evidence_span_ids"] == [str(span.id)]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "source_span", "id": str(foreign_span.id)} not in rewritten.source_refs
    assert {"type": "source_span", "id": "not-a-source-span-id"} not in rewritten.source_refs


def test_memory_page_rewrite_preserves_author_memory_update_open_threads(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    page = session.query(MemoryPage).one()
    span = session.query(SourceSpan).one()
    author_thread = {
        "type": "memory_writeback_decision",
        "thread_type": "needs_memory_update",
        "source_delta_id": str(delta.id),
        "item_ref": {"type": "memory_page", "id": str(page.id)},
        "decision": "correct",
        "target_section": "open_threads",
        "description": "地图来源仍是未解决线索，不能从当前页关闭。",
        "author_note": "正文没错，Mira 的地图线索仍应保持开放。",
        "source_span_ids": [str(span.id)],
        "status": "open",
        "requires": "memory_page_rewrite",
    }
    page.canon_status = "stale"
    page.open_threads = [author_thread]
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:preserve-author-open-thread-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add(rewrite_job)
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.open_threads == [author_thread]
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["open_thread_count"] == 1


def test_memory_page_rewrite_includes_facts_where_page_is_object(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    fact = session.query(FactAssertionRecord).one()
    span = session.query(SourceSpan).one()
    object_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="object",
        target_ref={"type": "object", "id": "lantern-map"},
        title="lantern-map",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{object_page.id}:object-side-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(object_page.id),
        },
    )
    session.add_all([object_page, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, object_page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.current_canon["facts"] == [
        {
            "fact_id": str(fact.id),
            "subject_ref": {"type": "character", "id": "mira"},
            "predicate": "owns",
            "object_ref": {"type": "object", "id": "lantern-map"},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "fact_assertion", "id": str(fact.id)} in rewritten.source_refs


def test_memory_page_rewrite_filters_fact_evidence_to_same_project_source_spans(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:subject-alpha | owns | object:object-beta | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    fact = session.query(FactAssertionRecord).one()
    span = session.query(SourceSpan).one()
    foreign_project = Project(id=uuid4(), name="Foreign Rewrite Project")
    foreign_raw_source = RawSource(
        id=uuid4(),
        project_id=foreign_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Foreign Rewrite Chapter",
        ownership_status="owned",
        raw_text_ref=object_store.put_text("raw/foreign-memory-rewrite.txt", "Foreign rewrite."),
    )
    foreign_version = SourceVersion(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_label="v1",
        raw_hash="foreign-memory-rewrite-hash-v1",
    )
    foreign_view = SourceProcessedView(
        id=uuid4(),
        version_id=foreign_version.id,
        cleaning_profile="draft_manuscript_profile_v1",
        markdown_ref=object_store.put_text(
            "processed/foreign-memory-rewrite.md",
            "Foreign rewrite.",
        ),
        raw_offset_map_ref=object_store.put_text(
            "processed/foreign-memory-rewrite.offsets.json",
            "{}",
        ),
        view_status="current",
    )
    foreign_span = SourceSpan(
        id=uuid4(),
        source_id=foreign_raw_source.id,
        version_id=foreign_version.id,
        view_id=foreign_view.id,
        start_offset=0,
        end_offset=16,
        raw_start_offset=0,
        raw_end_offset=16,
        text_preview="Foreign rewrite.",
        narration_layer="narrator",
    )
    fact.evidence_span_ids = [str(span.id), str(foreign_span.id), "not-a-source-span-id"]
    object_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="object",
        target_ref={"type": "object", "id": "object-beta"},
        title="object-beta",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{object_page.id}:fact-evidence-filter-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(object_page.id),
        },
    )
    session.add_all(
        [
            foreign_project,
            foreign_raw_source,
            foreign_version,
            foreign_view,
            foreign_span,
            object_page,
            rewrite_job,
        ]
    )
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, object_page.id)
    assert rewritten.current_canon["facts"][0]["evidence_span_ids"] == [str(span.id)]
    assert rewritten.current_canon["state_facts"][0]["evidence_span_ids"] == [str(span.id)]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "source_span", "id": str(foreign_span.id)} not in rewritten.source_refs
    assert {"type": "source_span", "id": "not-a-source-span-id"} not in rewritten.source_refs


def test_memory_page_rewrite_builds_object_holder_state_for_object_page(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    fact = session.query(FactAssertionRecord).one()
    span = session.query(SourceSpan).one()
    object_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="object",
        target_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        title="Lantern Map",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{object_page.id}:object-holder-state-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(object_page.id),
        },
    )
    session.add_all([object_page, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, object_page.id)
    assert rewritten.current_canon["state_facts"] == [
        {
            "fact_id": str(fact.id),
            "predicate": "owns",
            "state_type": "object_holder",
            "subject_ref": {"type": "character", "id": "mira"},
            "object_ref": {"type": "object", "id": "lantern-map"},
            "counterparty_ref": {"type": "character", "id": "mira"},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "fact_assertion", "id": str(fact.id)} in rewritten.source_refs
    audit = session.query(AuditEvent).filter_by(event_type="memory_page.rebuilt").one()
    assert audit.decision["state_fact_count"] == 1


def test_memory_page_rewrite_relationship_log_uses_counterparty_when_page_is_object(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    span = session.query(SourceSpan).one()
    relationship_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={"type": "character", "id": "mira", "label": "Mira"},
        predicate="ally_of",
        object_ref={"type": "character", "id": "orrin", "label": "Orrin"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    orrin_page = MemoryPage(
        id=uuid4(),
        project_id=delta.project_id,
        page_type="character",
        target_ref={"type": "character", "id": "orrin", "label": "Orrin"},
        title="Orrin",
        current_canon={"facts": []},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[],
        canon_status="stale",
        memory_depth="standard",
    )
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{orrin_page.id}:object-relationship-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(orrin_page.id),
        },
    )
    session.add_all([relationship_fact, orrin_page, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, orrin_page.id)
    assert rewritten.canon_status == "rebuilt"
    assert rewritten.relationships == [
        {
            "fact_id": str(relationship_fact.id),
            "predicate": "ally_of",
            "target_ref": {"type": "character", "id": "mira", "label": "Mira"},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert rewritten.current_canon["facts"] == [
        {
            "fact_id": str(relationship_fact.id),
            "subject_ref": {"type": "character", "id": "mira", "label": "Mira"},
            "predicate": "ally_of",
            "object_ref": {"type": "character", "id": "orrin", "label": "Orrin"},
            "evidence_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in rewritten.source_refs
    assert {"type": "fact_assertion", "id": str(relationship_fact.id)} in rewritten.source_refs


def test_memory_page_rewrite_matches_canonical_entity_refs_by_slug(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())(session, job)
    page = session.query(MemoryPage).one()
    span = session.query(SourceSpan).one()
    entity_id = uuid4()
    canonical_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=delta.project_id,
        subject_ref={
            "type": "character",
            "id": str(entity_id),
            "label": "Mira",
            "canonical_entity_id": str(entity_id),
            "slug": "mira",
        },
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page.canon_status = "stale"
    rewrite_job = JobRecord(
        id=uuid4(),
        project_id=delta.project_id,
        job_type="rewrite_memory_page",
        status="running",
        idempotency_key=f"memory-page:{page.id}:canonical-slug-rewrite-test",
        payload={
            "step": "rewrite_memory_page",
            "pipeline_version": "pipeline-v1",
            "memory_page_id": str(page.id),
        },
    )
    session.add_all([canonical_fact, rewrite_job])
    session.commit()

    MemoryPageRewriteHandler()(session, rewrite_job)

    rewritten = session.get(MemoryPage, page.id)
    assert rewritten.canon_status == "rebuilt"
    assert {fact["predicate"] for fact in rewritten.current_canon["facts"]} == {
        "located_in",
        "owns",
    }
    located_in_entry = next(
        fact for fact in rewritten.current_canon["facts"] if fact["predicate"] == "located_in"
    )
    assert located_in_entry["subject_ref"]["id"] == str(entity_id)
    assert located_in_entry["subject_ref"]["slug"] == "mira"
    assert session.query(GraphProjectionEdge).filter_by(
        relation="located_in", edge_status="canon"
    ).one().subject_ref["id"] == str(entity_id)


def test_medium_risk_writeback_creates_review_without_canon_promotion(
    session: Session, object_store: LocalObjectStore
) -> None:
    _delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | knows | secret:orrin_identity | medium",
    )
    handler = MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())

    handler(session, job)

    fact = session.query(FactAssertionRecord).one()
    assert fact.fact_status == "disputed"
    assert fact.promotion_decision_id is None
    review = session.query(ReviewItemRecord).one()
    assert review.review_type == "knowledge_conflict"
    assert review.status == "open"
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_duplicate_writeback_does_not_double_create_facts(
    session: Session, object_store: LocalObjectStore
) -> None:
    delta, job = seed_delta(
        session,
        object_store,
        text="FACT: character:mira | owns | object:lantern-map | low",
    )
    handler = MemoryWritebackHandler(object_store, LocalMemoryExtractionProvider())

    handler(session, job)
    job.status = "running"
    session.commit()
    handler(session, job)

    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_completed"
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(EvidenceLogEntry).count() == 1
