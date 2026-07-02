from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sextant.application.use_cases import AnswerWithEvidence, BuildWritingContextPack
from sextant.contracts.use_cases import BuildWritingContextPackInput, MemoryAnswerInput
from sextant.infra.context_pack_job import BuildContextPackHandler
from sextant.infra.db.models import (
    AgentContextPackRecord,
    AuditEvent,
    Base,
    CharacterKnowledge,
    ContextPackReadinessRecord,
    FactAssertionRecord,
    GraphProjectionEdge,
    GraphProjectionRun,
    IdempotencyRecord,
    JobRecord,
    MemoryPage,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SemanticEmbeddingRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryCanonicalEvent,
    StoryChapter,
    StoryMention,
    StoryScene,
)
from sextant.infra.semantic_index_job import SemanticIndexRefreshHandler
from sextant.infra.semantic_search import (
    refresh_memory_page_semantic_embeddings,
    refresh_project_semantic_embeddings,
)
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sextant.infra.worker import DbWorker
from sextant.skills.local_embedding import LocalEmbeddingProvider
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def uow_factory(session: Session):
    return lambda: SqlAlchemyUnitOfWork(session)


class FixedLowScoreEmbeddingProvider:
    provider_name = "test_low_score"
    model_name = "fixed-low-score-v1"
    dimensions = 2

    def embed_texts(self, texts):
        return [[1.0, 0.0] for _text in texts]


class CountingLocalEmbeddingProvider(LocalEmbeddingProvider):
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def embed_texts(self, texts):
        self.batch_sizes.append(len(texts))
        return super().embed_texts(texts)


def seed_evidence(
    session: Session,
) -> tuple[Project, UUID, RawSource, SourceVersion, SourceSpan]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref="object://raw/chapter-3",
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    view = SourceProcessedView(
        id=uuid4(),
        version_id=version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/current",
        raw_offset_map_ref="object://offsets/current",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=0,
        end_offset=24,
        raw_start_offset=0,
        raw_end_offset=24,
        text_preview="Mira took the lantern map.",
        narration_layer="narrator",
    )
    session.add_all([project, membership, raw_source, version, view, span])
    session.commit()
    return project, actor_id, raw_source, version, span


def seed_cross_project_span(session: Session, *, text_preview: str) -> SourceSpan:
    other_project = Project(id=uuid4(), name="Other Story")
    other_source = RawSource(
        id=uuid4(),
        project_id=other_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/other-chapter",
    )
    other_version = SourceVersion(
        id=uuid4(),
        source_id=other_source.id,
        version_label="v1",
        raw_hash="other-hash-v1",
    )
    other_view = SourceProcessedView(
        id=uuid4(),
        version_id=other_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/other",
        raw_offset_map_ref="object://offsets/other",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=other_source.id,
        version_id=other_version.id,
        view_id=other_view.id,
        start_offset=0,
        end_offset=len(text_preview),
        raw_start_offset=0,
        raw_end_offset=len(text_preview),
        text_preview=text_preview,
        narration_layer="narrator",
    )
    session.add_all([other_project, other_source, other_version, other_view, cross_project_span])
    return cross_project_span


def test_memory_answer_returns_unknown_without_structured_evidence_target(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, _span = seed_evidence(session)

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-unknown",
            idempotency_key="idem-answer-unknown",
            question="米拉知道钥匙是谁给的吗？",
        )
    )

    assert output.answer_type == "unknown"
    assert output.source_span_refs == []
    assert output.unknowns == ["structured_subject_or_predicate_required"]
    assert output.confidence == 0.0
    assert output.affected_entities == []
    assert output.caveats == ["structured_subject_or_predicate_required"]
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_finds_first_appearance_from_source_mentions(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=120,
        summary=None,
    )
    first_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=50,
    )
    later_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=51,
        end_offset=100,
    )
    first_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=first_scene.id,
        start_offset=8,
        end_offset=36,
        raw_start_offset=8,
        raw_end_offset=36,
        text_preview="Mira stepped onto the quay.",
        narration_layer="narrator",
    )
    later_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=later_scene.id,
        start_offset=72,
        end_offset=102,
        raw_start_offset=72,
        raw_end_offset=102,
        text_preview="Mira found the hidden ledger.",
        narration_layer="narrator",
    )
    first_mention = StoryMention(
        id=uuid4(),
        span_id=first_span.id,
        raw_text="Mira",
        mention_type="character",
        local_context="Mira stepped onto the quay.",
        resolved_entity_id=mira.id,
        resolution_status="auto_accepted",
        confidence=0.93,
    )
    later_mention = StoryMention(
        id=uuid4(),
        span_id=later_span.id,
        raw_text="Mira",
        mention_type="character",
        local_context="Mira found the hidden ledger.",
        resolved_entity_id=mira.id,
        resolution_status="auto_accepted",
        confidence=0.91,
    )
    session.add_all(
        [
            mira,
            chapter,
            first_scene,
            later_scene,
            first_span,
            later_span,
            first_mention,
            later_mention,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-first-appearance",
            idempotency_key="idem-answer-first-appearance",
            question="Where does Mira first appear?",
        )
    )

    assert output.answer_type == "canon"
    assert output.source_span_refs == [{"type": "source_span", "id": str(first_span.id)}]
    assert output.affected_entities == [{"type": "character", "id": str(mira.id), "label": "Mira"}]
    assert output.caveats == ["source_mention_lookup"]
    assert output.confidence == 0.93
    assert "Mira first appears in Chapter 1 / Scene 1" in output.answer
    assert "Mira stepped onto the quay." in output.answer
    assert "hidden ledger" not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_finds_first_appearance_from_raw_mention_text(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    masked_man = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Silver Masked Man",
        canonical_status="provisional",
        cast_tier="recurring",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=1,
        title="Fog Market",
        start_offset=0,
        end_offset=80,
        summary=None,
    )
    scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=20,
        end_offset=70,
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=scene.id,
        start_offset=24,
        end_offset=56,
        raw_start_offset=24,
        raw_end_offset=56,
        text_preview="银面人第一次站在雾市门口。",
        narration_layer="narrator",
    )
    mention = StoryMention(
        id=uuid4(),
        span_id=span.id,
        raw_text="银面人",
        mention_type="character",
        local_context="银面人第一次站在雾市门口。",
        resolved_entity_id=masked_man.id,
        resolution_status="auto_accepted",
        confidence=0.87,
    )
    session.add_all([masked_man, chapter, scene, span, mention])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-first-appearance-raw-mention",
            idempotency_key="idem-answer-first-appearance-raw-mention",
            question="银面人第一次出现在哪？",
        )
    )

    assert output.answer_type == "canon"
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [
        {"type": "character", "id": str(masked_man.id), "label": "Silver Masked Man"}
    ]
    assert output.caveats == ["source_mention_lookup"]
    assert output.confidence == 0.87
    assert "Silver Masked Man first appears in Chapter 2 / Scene 3" in output.answer
    assert "银面人第一次站在雾市门口。" in output.answer
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_lists_source_backed_open_threads_from_memory_pages(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-thread",
                "summary": "Kestrel still has the Lantern Map.",
                "source_span_ids": [str(span.id)],
            },
            {
                "id": "buyer-thread",
                "thread": "The buyer behind the map remains unknown.",
                "source_span_ids": [str(span.id)],
            },
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    orrin_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "orrin", "label": "Orrin"},
        title="Orrin",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[{"id": "debt-thread", "summary": "Orrin still owes the harbor guard."}],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([mira_page, orrin_page])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread",
            idempotency_key="idem-answer-open-thread",
            question="What open threads remain for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [{"type": "character", "id": "mira", "label": "Mira"}]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Kestrel still has the Lantern Map." in output.answer
    assert "The buyer behind the map remains unknown." in output.answer
    assert "Orrin still owes the harbor guard." not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_open_threads_use_persisted_embedding_recall(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    relevant_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=48,
        end_offset=96,
        raw_start_offset=48,
        raw_end_offset=96,
        text_preview="Secret informant secret informant must remain unnamed.",
        narration_layer="narrator",
    )
    unrelated_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=120,
        end_offset=160,
        raw_start_offset=120,
        raw_end_offset=160,
        text_preview="Inventory ledger count rests near quay.",
        narration_layer="narrator",
    )
    mira_id = uuid4()
    mira_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira_id),
            "label": "Mira",
            "canonical_entity_id": str(mira_id),
        },
        title="Mira dossier",
        current_canon={"role_note": "Secret informant secret informant must remain unnamed."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "informant-thread",
                "summary": "Secret informant secret informant must remain unnamed.",
                "source_span_ids": [str(relevant_span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(relevant_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="object",
        target_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
        title="Lantern Map",
        current_canon={"state": "Inventory ledger count rests near quay."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "inventory-thread",
                "summary": "Inventory ledger count rests near quay.",
                "source_span_ids": [str(unrelated_span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(unrelated_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([relevant_span, unrelated_span, mira_page, unrelated_page])
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refreshed = refresh_project_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    assert refreshed == {
        "memory_page": 2,
        "source_span": 3,
        "style_sample": 3,
    }
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="memory_page").count() == 2

    output = AnswerWithEvidence(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-embedding-recall",
            idempotency_key="idem-answer-open-thread-embedding-recall",
            question="open thread clandestine contact",
        )
    )

    assert output.answer_type == "open_thread"
    assert output.source_span_refs == [{"type": "source_span", "id": str(relevant_span.id)}]
    assert output.affected_entities == [
        {
            "type": "character",
            "id": str(mira_id),
            "label": "Mira",
            "canonical_entity_id": str(mira_id),
        }
    ]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Secret informant secret informant must remain unnamed." in output.answer
    assert "Inventory ledger count rests near quay." not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_facts_use_persisted_embedding_recall(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    relevant_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=48,
        end_offset=96,
        raw_start_offset=48,
        raw_end_offset=96,
        text_preview="Secret informant secret informant carries the black ledger.",
        narration_layer="narrator",
    )
    unrelated_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=120,
        end_offset=168,
        raw_start_offset=120,
        raw_end_offset=168,
        text_preview="Harbor quartermaster locks the signal knife away.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira dossier",
        current_canon={"role_note": "Secret informant secret informant carries the black ledger."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(relevant_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin Vale",
            "canonical_entity_id": str(orrin.id),
        },
        title="Orrin dossier",
        current_canon={"role_note": "Harbor quartermaster locks the signal knife away."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(unrelated_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "black-ledger", "label": "black ledger"},
        fact_status="canon",
        evidence_span_ids=[str(relevant_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unrelated_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin Vale",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "signal-knife", "label": "signal knife"},
        fact_status="canon",
        evidence_span_ids=[str(unrelated_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            relevant_span,
            unrelated_span,
            mira,
            orrin,
            mira_page,
            unrelated_page,
            mira_fact,
            unrelated_fact,
        ]
    )
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refreshed = refresh_project_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    assert refreshed == {
        "memory_page": 2,
        "source_span": 3,
        "style_sample": 3,
    }

    output = AnswerWithEvidence(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-fact-embedding-recall",
            idempotency_key="idem-answer-fact-embedding-recall",
            question="What is remembered about the clandestine contact?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns black ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(relevant_span.id)}]
    assert output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Orrin" not in output.answer
    assert "signal knife" not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_semantic_fact_recall_caps_confidence_by_match_score(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=48,
        end_offset=96,
        raw_start_offset=48,
        raw_end_offset=96,
        text_preview="Distant archive rumor marks the sealed ledger.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "object", "id": "sealed-ledger", "label": "sealed ledger"},
        predicate="located_in",
        object_ref={"type": "location", "id": "distant-archive", "label": "distant archive"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    embedding_provider = FixedLowScoreEmbeddingProvider()
    embedding = SemanticEmbeddingRecord(
        id=uuid4(),
        project_id=project.id,
        target_type="source_span",
        target_id=span.id,
        target_ref={"type": "source_span", "id": str(span.id)},
        text_hash="fixed-low-score-span",
        provider=embedding_provider.provider_name,
        model_name=embedding_provider.model_name,
        dimensions=embedding_provider.dimensions,
        vector=[0.5, 0.8660254037844386],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    session.add_all([span, fact, embedding])
    session.commit()

    output = AnswerWithEvidence(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-semantic-fact-confidence-cap",
            idempotency_key="idem-answer-semantic-fact-confidence-cap",
            question="What is remembered about the faraway rumor?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "sealed ledger located_in distant archive"
    assert output.confidence == 0.5
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [fact.subject_ref, fact.object_ref]
    assert output.caveats == []
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_semantic_fact_recall_asks_for_clarification_on_multiple_targets(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=48,
        end_offset=96,
        raw_start_offset=48,
        raw_end_offset=96,
        text_preview="Secret informant secret informant carries the black ledger.",
        narration_layer="narrator",
    )
    myra_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=120,
        end_offset=168,
        raw_start_offset=120,
        raw_end_offset=168,
        text_preview="Secret informant secret informant keeps the brass compass.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "black-ledger", "label": "black ledger"},
        fact_status="canon",
        evidence_span_ids=[str(mira_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "brass-compass", "label": "brass compass"},
        fact_status="canon",
        evidence_span_ids=[str(myra_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira_span, myra_span, mira, myra, mira_fact, myra_fact])
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refresh_project_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    output = AnswerWithEvidence(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-semantic-fact-clarification",
            idempotency_key="idem-answer-semantic-fact-clarification",
            question="What is remembered about the clandestine contact?",
        )
    )

    assert output.answer_type == "unknown"
    assert output.caveats == ["semantic_clarification_needed"]
    assert output.unknowns == ["semantic_clarification_needed"]
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(mira_span.id)},
        {"type": "source_span", "id": str(myra_span.id)},
    ]
    assert output.affected_entities == [mira_fact.subject_ref, myra_fact.subject_ref]
    assert output.safe_to_use_in_current_pov is False
    assert "Mira Vale" in output.answer
    assert "Myra Vail" in output.answer
    assert "black ledger" not in output.answer
    assert "brass compass" not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_open_threads_surface_related_review_items(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="medium",
        status="open",
        summary="Mira's map knowledge needs follow-up.",
        affected_refs={"type": "character", "id": "mira", "label": "Mira"},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "review_item_id": str(review.id),
                "review_type": "continuity_warning",
                "severity": "medium",
                "summary": "Mira's map knowledge needs follow-up.",
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([review, page])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-review",
            idempotency_key="idem-answer-open-thread-review",
            question="What unresolved threads remain for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.related_review_items == [review.id]
    assert output.caveats == ["memory_page_open_thread", "open_review_item"]
    assert output.confidence == 0.6
    assert output.safe_to_use_in_current_pov is False
    assert "Mira's map knowledge needs follow-up." in output.answer
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_open_threads_calibrate_confidence_by_review_severity(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="high",
        status="open",
        summary="Mira's map knowledge contradicts the accepted scene.",
        affected_refs={"type": "character", "id": "mira", "label": "Mira"},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "review_item_id": str(review.id),
                "review_type": "continuity_warning",
                "severity": "high",
                "summary": "Mira's map knowledge contradicts the accepted scene.",
                "source_span_ids": [str(span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([review, page])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-severity-confidence",
            idempotency_key="idem-answer-open-thread-severity-confidence",
            question="What unresolved threads remain for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert output.related_review_items == [review.id]
    assert output.caveats == ["memory_page_open_thread", "open_review_item"]
    assert output.confidence == 0.5
    assert output.safe_to_use_in_current_pov is False
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_open_threads_rank_review_backed_items_first(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="high",
        status="open",
        summary="Mira's map knowledge contradicts the last scene.",
        affected_refs={"type": "character", "id": "mira", "label": "Mira"},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "ordinary-map-thread",
                "status": "open",
                "summary": "Mira still needs to hide the lantern map.",
            },
            {
                "id": "review-map-thread",
                "review_item_id": str(review.id),
                "review_type": "continuity_warning",
                "severity": "high",
                "summary": "Mira's map knowledge contradicts the last scene.",
            },
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([review, page])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-ranked-review",
            idempotency_key="idem-answer-open-thread-ranked-review",
            question="What unresolved threads remain for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert output.related_review_items == [review.id]
    assert output.caveats == ["memory_page_open_thread", "open_review_item"]
    assert output.confidence == 0.5
    assert output.safe_to_use_in_current_pov is False
    assert output.answer.index("map knowledge contradicts") < output.answer.index(
        "needs to hide the lantern map"
    )
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [{"type": "character", "id": "mira", "label": "Mira"}]
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(AuditEvent).filter_by(event_type="memory.answer").count() == 1


def test_memory_answer_open_threads_ignore_closed_threads(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "resolved-map-thread",
                "status": "resolved",
                "summary": "The buyer behind the map has been revealed.",
            },
            {
                "id": "closed-harbor-thread",
                "thread_status": "closed",
                "summary": "The harbor guard debt has been paid.",
            },
            {
                "id": "active-compass-thread",
                "status": "open",
                "summary": "Mira still has not found the second compass.",
            },
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add(page)
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-closed",
            idempotency_key="idem-answer-open-thread-closed",
            question="What open threads remain for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert "Mira still has not found the second compass." in output.answer
    assert "buyer behind the map has been revealed" not in output.answer
    assert "harbor guard debt has been paid" not in output.answer
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert output.related_review_items == []
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_open_threads_filter_thread_focus_after_target_match(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-thread",
                "status": "open",
                "summary": "Mira still needs to hide the lantern map.",
            },
            {
                "id": "compass-thread",
                "status": "open",
                "summary": "Mira still has not found the second compass.",
            },
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add(page)
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-thread-focus",
            idempotency_key="idem-answer-open-thread-thread-focus",
            question="What open threads remain about the compass for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert "Mira still has not found the second compass." in output.answer
    assert "lantern map" not in output.answer
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [{"type": "character", "id": "mira", "label": "Mira"}]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_open_threads_cite_only_matching_thread_source_spans(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, map_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    compass_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=78,
        raw_start_offset=30,
        raw_end_offset=78,
        text_preview="Mira still has not found the second compass.",
        narration_layer="narrator",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-thread",
                "status": "open",
                "summary": "Mira still needs to hide the lantern map.",
                "source_span_ids": [str(map_span.id)],
            },
            {
                "id": "compass-thread",
                "status": "open",
                "summary": "Mira still has not found the second compass.",
                "source_span_ids": [str(compass_span.id)],
            },
        ],
        contradictions=[],
        source_refs=[
            {"type": "source_span", "id": str(map_span.id)},
            {"type": "source_span", "id": str(compass_span.id)},
        ],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([compass_span, page])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-thread-span",
            idempotency_key="idem-answer-open-thread-thread-span",
            question="What open threads remain about the compass for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert "Mira still has not found the second compass." in output.answer
    assert "lantern map" not in output.answer
    assert output.source_span_refs == [{"type": "source_span", "id": str(compass_span.id)}]
    assert output.affected_entities == [{"type": "character", "id": "mira", "label": "Mira"}]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_open_threads_ignore_missing_thread_source_spans(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, page_span = seed_evidence(session)
    missing_span_id = uuid4()
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "label": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "compass-thread",
                "status": "open",
                "summary": "Mira still has not found the second compass.",
                "source_span_ids": [str(missing_span_id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(page_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add(page)
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-open-thread-missing-thread-span",
            idempotency_key="idem-answer-open-thread-missing-thread-span",
            question="What open threads remain about the compass for Mira?",
        )
    )

    assert output.answer_type == "open_thread"
    assert "Mira still has not found the second compass." in output.answer
    assert output.source_span_refs == [{"type": "source_span", "id": str(page_span.id)}]
    assert {"type": "source_span", "id": str(missing_span_id)} not in output.source_span_refs
    assert output.affected_entities == [{"type": "character", "id": "mira", "label": "Mira"}]
    assert output.caveats == ["memory_page_open_thread"]
    assert output.confidence == 0.8
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_infers_target_from_question_alias_and_predicate(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="the informant",
        entity_id=mira.id,
        alias_type="title",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(span.id)],
        confidence=0.79,
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, alias, fact])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-natural-language",
            idempotency_key="idem-answer-natural-language",
            question="What does the informant own?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira owns ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.91
    assert output.affected_entities == [fact.subject_ref, fact.object_ref]
    assert output.caveats == []
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(StoryAliasRecord).count() == 1
    assert session.query(StoryCanonicalEntity).count() == 1
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_unknown_for_ambiguous_alias_target(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    aliases = [
        StoryAliasRecord(
            id=uuid4(),
            project_id=project.id,
            alias_text="Starling",
            entity_id=mira.id,
            alias_type="codename",
            status="proposed",
            scope="global",
            evidence_span_ids=[str(span.id)],
            confidence=0.72,
        ),
        StoryAliasRecord(
            id=uuid4(),
            project_id=project.id,
            alias_text="Starling",
            entity_id=myra.id,
            alias_type="codename",
            status="proposed",
            scope="global",
            evidence_span_ids=[str(span.id)],
            confidence=0.68,
        ),
    ]
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, myra, *aliases, mira_fact, myra_fact])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-ambiguous-alias",
            idempotency_key="idem-answer-ambiguous-alias",
            question="What does Starling own?",
        )
    )

    assert output.answer_type == "unknown"
    assert output.answer == "Ambiguous entity match for `Starling`: Mira Vale, Myra Vail."
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [
        {"type": "character", "id": str(mira.id), "label": "Mira Vale"},
        {"type": "character", "id": str(myra.id), "label": "Myra Vail"},
    ]
    assert output.caveats == ["ambiguous_entity_match"]
    assert output.unknowns == ["ambiguous_entity_match"]
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is False
    assert output.confidence == 0.0
    assert "ledger" not in output.answer
    assert "knife" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_narrows_scene_local_alias_from_alias_evidence_context(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    observatory_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=80,
    )
    archive_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=81,
        end_offset=170,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = observatory_scene.id
    observatory_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=observatory_scene.id,
        start_offset=10,
        end_offset=55,
        raw_start_offset=10,
        raw_end_offset=55,
        text_preview="In the observatory, Starling hides the prism ledger.",
        narration_layer="narrator",
    )
    archive_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=archive_scene.id,
        start_offset=90,
        end_offset=140,
        raw_start_offset=90,
        raw_end_offset=140,
        text_preview="In the archive, Starling palms the brass knife.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=mira.id,
        alias_type="codename",
        status="proposed",
        scope="scene_local",
        evidence_span_ids=[str(observatory_alias_span.id)],
        confidence=0.73,
    )
    myra_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=myra.id,
        alias_type="codename",
        status="proposed",
        scope="scene_local",
        evidence_span_ids=[str(archive_alias_span.id)],
        confidence=0.71,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(observatory_alias_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(archive_alias_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            chapter,
            observatory_scene,
            archive_scene,
            observatory_alias_span,
            archive_alias_span,
            mira,
            myra,
            mira_alias,
            myra_alias,
            mira_fact,
            myra_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-scene-local-alias",
            idempotency_key="idem-answer-scene-local-alias",
            question="What does Starling own in the observatory scene?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns ledger"
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(observatory_alias_span.id)}
    ]
    assert output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.73
    assert "knife" not in output.answer

    scene_output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-scene-local-alias-current-scene",
            idempotency_key="idem-answer-scene-local-alias-current-scene",
            question="What does Starling own?",
            current_scene_id=observatory_scene.id,
        )
    )

    assert scene_output.answer_type == "canon"
    assert scene_output.answer == "Mira Vale owns ledger"
    assert scene_output.source_span_refs == [
        {"type": "source_span", "id": str(observatory_alias_span.id)}
    ]
    assert scene_output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert scene_output.caveats == ["scene_local_alias_context"]
    assert scene_output.unknowns == []
    assert scene_output.related_review_items == []
    assert scene_output.safe_to_use_in_current_pov is True
    assert scene_output.confidence == 0.73
    assert "knife" not in scene_output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_chapter_local_alias_from_current_scene_chapter(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    harbor_chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    citadel_chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=1,
        title="Citadel",
        start_offset=181,
        end_offset=360,
        summary=None,
    )
    current_scene = StoryScene(
        id=uuid4(),
        chapter_id=harbor_chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=90,
        end_offset=170,
    )
    harbor_alias_scene = StoryScene(
        id=uuid4(),
        chapter_id=harbor_chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=80,
    )
    citadel_alias_scene = StoryScene(
        id=uuid4(),
        chapter_id=citadel_chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=181,
        end_offset=260,
    )
    harbor_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=harbor_chapter.id,
        scene_id=harbor_alias_scene.id,
        start_offset=10,
        end_offset=55,
        raw_start_offset=10,
        raw_end_offset=55,
        text_preview="Across the harbor chapter, Starling means Mira Vale.",
        narration_layer="narrator",
    )
    citadel_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=citadel_chapter.id,
        scene_id=citadel_alias_scene.id,
        start_offset=190,
        end_offset=235,
        raw_start_offset=190,
        raw_end_offset=235,
        text_preview="Across the citadel chapter, Starling means Myra Vail.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=mira.id,
        alias_type="codename",
        status="proposed",
        scope="chapter_local",
        evidence_span_ids=[str(harbor_alias_span.id)],
        confidence=0.76,
    )
    myra_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=myra.id,
        alias_type="codename",
        status="proposed",
        scope="chapter_local",
        evidence_span_ids=[str(citadel_alias_span.id)],
        confidence=0.7,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(harbor_alias_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(citadel_alias_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            harbor_chapter,
            citadel_chapter,
            current_scene,
            harbor_alias_scene,
            citadel_alias_scene,
            harbor_alias_span,
            citadel_alias_span,
            mira,
            myra,
            mira_alias,
            myra_alias,
            mira_fact,
            myra_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-chapter-local-alias-current-scene",
            idempotency_key="idem-answer-chapter-local-alias-current-scene",
            question="What does Starling own?",
            current_scene_id=current_scene.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(harbor_alias_span.id)}]
    assert output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.76
    assert "knife" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_disguise_arc_alias_from_current_scene_window(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    harbor_chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=300,
        summary=None,
    )
    citadel_chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=1,
        title="Citadel",
        start_offset=301,
        end_offset=620,
        summary=None,
    )
    harbor_start_scene = StoryScene(
        id=uuid4(),
        chapter_id=harbor_chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=80,
    )
    harbor_middle_scene = StoryScene(
        id=uuid4(),
        chapter_id=harbor_chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=81,
        end_offset=170,
    )
    harbor_end_scene = StoryScene(
        id=uuid4(),
        chapter_id=harbor_chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=171,
        end_offset=260,
    )
    citadel_start_scene = StoryScene(
        id=uuid4(),
        chapter_id=citadel_chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=301,
        end_offset=390,
    )
    citadel_end_scene = StoryScene(
        id=uuid4(),
        chapter_id=citadel_chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=391,
        end_offset=500,
    )
    mira_arc_start_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=harbor_chapter.id,
        scene_id=harbor_start_scene.id,
        start_offset=10,
        end_offset=55,
        raw_start_offset=10,
        raw_end_offset=55,
        text_preview="Mira begins using the Vesper disguise at the harbor gate.",
        narration_layer="narrator",
    )
    mira_arc_end_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=harbor_chapter.id,
        scene_id=harbor_end_scene.id,
        start_offset=180,
        end_offset=230,
        raw_start_offset=180,
        raw_end_offset=230,
        text_preview="Mira drops the Vesper disguise after the harbor exchange.",
        narration_layer="narrator",
    )
    myra_arc_start_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=citadel_chapter.id,
        scene_id=citadel_start_scene.id,
        start_offset=320,
        end_offset=365,
        raw_start_offset=320,
        raw_end_offset=365,
        text_preview="Myra later takes the Vesper disguise in the citadel.",
        narration_layer="narrator",
    )
    myra_arc_end_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=citadel_chapter.id,
        scene_id=citadel_end_scene.id,
        start_offset=400,
        end_offset=455,
        raw_start_offset=400,
        raw_end_offset=455,
        text_preview="Myra abandons the Vesper disguise before the citadel bell.",
        narration_layer="narrator",
    )
    middle_fact_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=harbor_chapter.id,
        scene_id=harbor_middle_scene.id,
        start_offset=100,
        end_offset=140,
        raw_start_offset=100,
        raw_end_offset=140,
        text_preview="As Vesper, Mira carries the ledger through the market.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=mira.id,
        alias_type="disguise",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(mira_arc_start_span.id), str(mira_arc_end_span.id)],
        confidence=0.77,
    )
    myra_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=myra.id,
        alias_type="disguise",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(myra_arc_start_span.id), str(myra_arc_end_span.id)],
        confidence=0.72,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(middle_fact_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(myra_arc_start_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            harbor_chapter,
            citadel_chapter,
            harbor_start_scene,
            harbor_middle_scene,
            harbor_end_scene,
            citadel_start_scene,
            citadel_end_scene,
            mira_arc_start_span,
            mira_arc_end_span,
            myra_arc_start_span,
            myra_arc_end_span,
            middle_fact_span,
            mira,
            myra,
            mira_alias,
            myra_alias,
            mira_fact,
            myra_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-disguise-arc-alias-current-scene",
            idempotency_key="idem-answer-disguise-arc-alias-current-scene",
            question="What does Vesper own?",
            current_scene_id=harbor_middle_scene.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(middle_fact_span.id)}]
    assert output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.77
    assert "knife" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_disguise_arc_alias_from_author_scene_boundaries(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=420,
        summary=None,
    )
    arc_start_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=90,
    )
    arc_middle_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=91,
        end_offset=190,
    )
    arc_end_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=191,
        end_offset=280,
    )
    other_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=3,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=281,
        end_offset=390,
    )
    mira_boundary_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=arc_start_scene.id,
        start_offset=15,
        end_offset=55,
        raw_start_offset=15,
        raw_end_offset=55,
        text_preview="Mira starts the Vesper disguise.",
        narration_layer="narrator",
    )
    myra_boundary_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=other_scene.id,
        start_offset=300,
        end_offset=345,
        raw_start_offset=300,
        raw_end_offset=345,
        text_preview="Myra uses Vesper outside this arc.",
        narration_layer="narrator",
    )
    mira_fact_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=arc_middle_scene.id,
        start_offset=120,
        end_offset=150,
        raw_start_offset=120,
        raw_end_offset=150,
        text_preview="Vesper carries the ledger in the market.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=mira.id,
        alias_type="disguise",
        status="proposed",
        scope="disguise_arc",
        valid_from_scene_id=arc_start_scene.id,
        valid_until_scene_id=arc_end_scene.id,
        evidence_span_ids=[str(mira_boundary_span.id)],
        confidence=0.81,
    )
    myra_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Vesper",
        entity_id=myra.id,
        alias_type="disguise",
        status="proposed",
        scope="disguise_arc",
        evidence_span_ids=[str(myra_boundary_span.id)],
        confidence=0.82,
    )
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(mira_fact_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(myra_boundary_span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            chapter,
            arc_start_scene,
            arc_middle_scene,
            arc_end_scene,
            other_scene,
            mira_boundary_span,
            myra_boundary_span,
            mira_fact_span,
            mira,
            myra,
            mira_alias,
            myra_alias,
            mira_fact,
            myra_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-disguise-arc-alias-boundary",
            idempotency_key="idem-answer-disguise-arc-alias-boundary",
            question="What does Vesper own?",
            current_scene_id=arc_middle_scene.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(mira_fact_span.id)}]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.confidence == 0.81
    assert "knife" not in output.answer
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_character_specific_alias_from_current_pov(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ana = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ana Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    cal = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Cal Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Private Names",
        start_offset=0,
        end_offset=220,
        summary=None,
    )
    mira_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=mira.id,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=100,
    )
    ana_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=ana.id,
        pov_mode="third_limited",
        start_offset=101,
        end_offset=210,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = mira_scene.id
    mira_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=mira_scene.id,
        start_offset=20,
        end_offset=70,
        raw_start_offset=20,
        raw_end_offset=70,
        text_preview="From Mira's viewpoint, brother means Orrin Vale.",
        narration_layer="narrator",
    )
    ana_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=ana_scene.id,
        start_offset=120,
        end_offset=170,
        raw_start_offset=120,
        raw_end_offset=170,
        text_preview="From Ana's viewpoint, brother means Cal Reed.",
        narration_layer="narrator",
    )
    orrin_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=orrin.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.74,
    )
    cal_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=cal.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.72,
    )
    orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin Vale",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "silver-compass", "label": "silver compass"},
        fact_status="canon",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cal_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(cal.id),
            "label": "Cal Reed",
            "canonical_entity_id": str(cal.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "amber-seal", "label": "amber seal"},
        fact_status="canon",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "fact_assertion", "id": str(orrin_fact.id)},
        evidence_span_id=mira_alias_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all(
        [
            mira,
            ana,
            orrin,
            cal,
            chapter,
            mira_scene,
            ana_scene,
            mira_alias_span,
            ana_alias_span,
            orrin_alias,
            cal_alias,
            orrin_fact,
            cal_fact,
            mira_knowledge,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-character-specific-alias",
            idempotency_key="idem-answer-character-specific-alias",
            question="What does brother own?",
            current_pov_character_id=mira.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Orrin Vale owns silver compass"
    assert output.source_span_refs == [{"type": "source_span", "id": str(mira_alias_span.id)}]
    assert output.affected_entities == [orrin_fact.subject_ref, orrin_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.74
    assert "amber seal" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_character_specific_alias_from_current_scene_persisted_pov(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ana = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ana Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    cal = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Cal Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Private Names",
        start_offset=0,
        end_offset=220,
        summary=None,
    )
    mira_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=mira.id,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=100,
    )
    ana_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=ana.id,
        pov_mode="third_limited",
        start_offset=101,
        end_offset=210,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = mira_scene.id
    mira_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=mira_scene.id,
        start_offset=20,
        end_offset=70,
        raw_start_offset=20,
        raw_end_offset=70,
        text_preview="From Mira's viewpoint, brother means Orrin Vale.",
        narration_layer="narrator",
    )
    ana_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=ana_scene.id,
        start_offset=120,
        end_offset=170,
        raw_start_offset=120,
        raw_end_offset=170,
        text_preview="From Ana's viewpoint, brother means Cal Reed.",
        narration_layer="narrator",
    )
    orrin_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=orrin.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.74,
    )
    cal_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=cal.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.72,
    )
    orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin Vale",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "silver-compass", "label": "silver compass"},
        fact_status="canon",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cal_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(cal.id),
            "label": "Cal Reed",
            "canonical_entity_id": str(cal.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "amber-seal", "label": "amber seal"},
        fact_status="canon",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "fact_assertion", "id": str(orrin_fact.id)},
        evidence_span_id=mira_alias_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all(
        [
            mira,
            ana,
            orrin,
            cal,
            chapter,
            mira_scene,
            ana_scene,
            mira_alias_span,
            ana_alias_span,
            orrin_alias,
            cal_alias,
            orrin_fact,
            cal_fact,
            mira_knowledge,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-character-specific-scene-pov-alias",
            idempotency_key="idem-answer-character-specific-scene-pov-alias",
            question="What does brother own?",
            current_scene_id=mira_scene.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Orrin Vale owns silver compass"
    assert output.source_span_refs == [{"type": "source_span", "id": str(mira_alias_span.id)}]
    assert output.affected_entities == [orrin_fact.subject_ref, orrin_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.74
    assert "amber seal" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_narrows_character_specific_alias_from_speaker_span_without_scene_pov(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ana = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ana Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    cal = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Cal Reed",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Private Names",
        start_offset=0,
        end_offset=220,
        summary=None,
    )
    mira_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=100,
    )
    ana_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=101,
        end_offset=210,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = mira_scene.id
    mira_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=mira_scene.id,
        start_offset=20,
        end_offset=70,
        raw_start_offset=20,
        raw_end_offset=70,
        text_preview='Mira says, "Brother means Orrin Vale."',
        speaker_entity_id=mira.id,
        narration_layer="dialogue",
    )
    ana_alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=ana_scene.id,
        start_offset=120,
        end_offset=170,
        raw_start_offset=120,
        raw_end_offset=170,
        text_preview='Ana says, "Brother means Cal Reed."',
        speaker_entity_id=ana.id,
        narration_layer="dialogue",
    )
    orrin_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=orrin.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.74,
    )
    cal_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="brother",
        entity_id=cal.id,
        alias_type="kinship",
        status="proposed",
        scope="character_specific",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.72,
    )
    orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin Vale",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "silver-compass", "label": "silver compass"},
        fact_status="canon",
        evidence_span_ids=[str(mira_alias_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cal_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(cal.id),
            "label": "Cal Reed",
            "canonical_entity_id": str(cal.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "amber-seal", "label": "amber seal"},
        fact_status="canon",
        evidence_span_ids=[str(ana_alias_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "fact_assertion", "id": str(orrin_fact.id)},
        evidence_span_id=mira_alias_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all(
        [
            mira,
            ana,
            orrin,
            cal,
            chapter,
            mira_scene,
            ana_scene,
            mira_alias_span,
            ana_alias_span,
            orrin_alias,
            cal_alias,
            orrin_fact,
            cal_fact,
            mira_knowledge,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-character-specific-speaker-alias",
            idempotency_key="idem-answer-character-specific-speaker-alias",
            question="What does brother own?",
            current_pov_character_id=mira.id,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Orrin Vale owns silver compass"
    assert output.source_span_refs == [{"type": "source_span", "id": str(mira_alias_span.id)}]
    assert output.affected_entities == [orrin_fact.subject_ref, orrin_fact.object_ref]
    assert output.caveats == ["scene_local_alias_context"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.74
    assert "amber seal" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_disambiguates_alias_when_question_names_candidate_entity(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira Vale",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    myra = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Myra Vail",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    aliases = [
        StoryAliasRecord(
            id=uuid4(),
            project_id=project.id,
            alias_text="Starling",
            entity_id=mira.id,
            alias_type="codename",
            status="proposed",
            scope="global",
            evidence_span_ids=[str(span.id)],
            confidence=0.72,
        ),
        StoryAliasRecord(
            id=uuid4(),
            project_id=project.id,
            alias_text="Starling",
            entity_id=myra.id,
            alias_type="codename",
            status="proposed",
            scope="global",
            evidence_span_ids=[str(span.id)],
            confidence=0.68,
        ),
    ]
    mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira Vale",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    myra_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(myra.id),
            "label": "Myra Vail",
            "canonical_entity_id": str(myra.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "knife", "label": "knife"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.89,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, myra, *aliases, mira_fact, myra_fact])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-explicit-entity-alias",
            idempotency_key="idem-answer-explicit-entity-alias",
            question="What does Starling, Mira Vale, own?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira Vale owns ledger"
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [mira_fact.subject_ref, mira_fact.object_ref]
    assert output.caveats == []
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.91
    assert "knife" not in output.answer
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryAliasRecord).count() == 2
    assert session.query(GraphProjectionEdge).count() == 0


@pytest.mark.parametrize(
    ("question", "request_id", "idempotency_key"),
    [
        (
            "What secrets does Mira know?",
            "req-answer-character-knowledge",
            "idem-answer-character-knowledge",
        ),
        (
            "Mira 现在知道哪些秘密？",
            "req-answer-character-knowledge-cn",
            "idem-answer-character-knowledge-cn",
        ),
    ],
)
def test_memory_answer_lists_character_knowledge_states_with_certainty(
    session: Session,
    question: str,
    request_id: str,
    idempotency_key: str,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    known_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    misunderstood_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=known_fact.subject_ref,
        predicate="knows",
        object_ref={
            "type": "knowledge_claim",
            "id": "orrin-betrayal",
            "label": "Orrin betrayed her",
            "certainty": "misunderstands",
        },
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.74,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unknown_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=known_fact.subject_ref,
        predicate="does_not_know",
        object_ref={
            "type": "secret",
            "id": "kestrel-moved-map",
            "label": "Kestrel moved the map",
        },
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.82,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    knowledge_rows = [
        CharacterKnowledge(
            id=uuid4(),
            project_id=project.id,
            character_id=mira.id,
            knows_ref={"type": "fact_assertion", "id": str(known_fact.id)},
            evidence_span_id=span.id,
            certainty="known",
            hidden_from=[],
            status="active",
        ),
        CharacterKnowledge(
            id=uuid4(),
            project_id=project.id,
            character_id=mira.id,
            knows_ref={"type": "fact_assertion", "id": str(misunderstood_fact.id)},
            evidence_span_id=span.id,
            certainty="misunderstands",
            hidden_from=[],
            status="active",
        ),
        CharacterKnowledge(
            id=uuid4(),
            project_id=project.id,
            character_id=mira.id,
            knows_ref={"type": "fact_assertion", "id": str(unknown_fact.id)},
            evidence_span_id=span.id,
            certainty="does_not_know",
            hidden_from=[],
            status="active",
        ),
    ]
    session.add_all([mira, known_fact, misunderstood_fact, unknown_fact, *knowledge_rows])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            question=question,
        )
    )

    assert output.answer_type == "canon"
    assert "Harbor Code (known)" in output.answer
    assert "Orrin betrayed her (misunderstands)" in output.answer
    assert "Kestrel moved the map" not in output.answer
    assert output.confidence == 0.74
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.affected_entities == [
        known_fact.subject_ref,
        known_fact.object_ref,
        misunderstood_fact.object_ref,
    ]
    assert output.caveats == ["misunderstood_knowledge"]
    assert output.safe_to_use_in_current_pov is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_character_knowledge_ignores_cross_project_fact_evidence(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, knowledge_span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Mira learned the harbor cipher in another project.",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    cross_project_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor-cipher", "label": "Harbor Cipher"},
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "fact_assertion", "id": str(cross_project_fact.id)},
        evidence_span_id=knowledge_span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all([mira, cross_project_fact, knowledge])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-character-knowledge-cross-project-evidence",
            idempotency_key="idem-answer-character-knowledge-cross-project-evidence",
            question="What secrets does Mira know?",
        )
    )

    assert output.answer_type == "unknown"
    assert output.answer == "No SourceSpan-backed memory evidence matches this question."
    assert output.source_span_refs == []
    assert output.affected_entities == []
    assert output.caveats == ["no_matching_evidence"]
    assert output.related_review_items == []
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


@pytest.mark.parametrize(
    ("question", "request_id", "idempotency_key"),
    [
        (
            "What does Mira not know?",
            "req-answer-character-unknowns",
            "idem-answer-character-unknowns",
        ),
        (
            "Mira 不知道什么？",
            "req-answer-character-unknowns-cn",
            "idem-answer-character-unknowns-cn",
        ),
    ],
)
def test_memory_answer_lists_explicit_character_unknowns(
    session: Session,
    question: str,
    request_id: str,
    idempotency_key: str,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    unknown_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="does_not_know",
        object_ref={
            "type": "secret",
            "id": "kestrel-moved-map",
            "label": "Kestrel moved the map",
        },
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.82,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira.id,
        knows_ref={"type": "fact_assertion", "id": str(unknown_fact.id)},
        evidence_span_id=span.id,
        certainty="does_not_know",
        hidden_from=[],
        status="active",
    )
    session.add_all([mira, unknown_fact, knowledge])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            question=question,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Mira does not know Kestrel moved the map (does_not_know)"
    assert output.confidence == 0.82
    assert output.affected_entities == [unknown_fact.subject_ref, unknown_fact.object_ref]
    assert output.caveats == ["explicit_unknown_knowledge"]


def test_memory_answer_uses_canonical_event_timeline_for_after_questions(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=100,
        summary=None,
    )
    theft_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=40,
    )
    aftermath_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=41,
        end_offset=90,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = theft_scene.id
    aftermath_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=aftermath_scene.id,
        start_offset=41,
        end_offset=80,
        raw_start_offset=41,
        raw_end_offset=80,
        text_preview="Mira hid in the archive after the theft.",
        narration_layer="narrator",
    )
    anchor_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Lantern Map is stolen",
        event_status="canon",
        primary_scene_id=theft_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel steals the Lantern Map from the quay.",
        consequence_summary="Mira loses the map.",
        evidence_span_ids=[str(seed_span.id)],
    )
    later_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="decision",
        title="Mira hides in the archive",
        event_status="canon",
        primary_scene_id=aftermath_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira", "label": "Mira"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3-after-theft",
        summary="Mira hides in the archive after the map is stolen.",
        consequence_summary="She keeps searching without the map.",
        evidence_span_ids=[str(aftermath_span.id)],
    )
    session.add_all(
        [
            chapter,
            theft_scene,
            aftermath_scene,
            aftermath_span,
            anchor_event,
            later_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-event-after",
            idempotency_key="idem-answer-event-after",
            question="What happened after the Lantern Map was stolen?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "After Lantern Map is stolen: Mira hides in the archive - "
        "Mira hides in the archive after the map is stolen. Consequence: "
        "She keeps searching without the map."
    )
    assert output.confidence == 0.9
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(aftermath_span.id)},
    ]
    assert output.affected_entities == [
        {"type": "character", "id": "mira", "label": "Mira"},
        {"type": "object", "id": "lantern-map", "label": "Lantern Map"},
    ]
    assert output.caveats == ["timeline_order_from_scene_position"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_answer_event_timeline_ignores_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="A different story says Orrin burns the map after the theft.",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    theft_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=40,
    )
    invalid_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=41,
        end_offset=90,
    )
    valid_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=91,
        end_offset=160,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = theft_scene.id
    valid_later_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=valid_scene.id,
        start_offset=100,
        end_offset=145,
        raw_start_offset=100,
        raw_end_offset=145,
        text_preview="Mira hides in the archive after the map is stolen.",
        narration_layer="narrator",
    )
    anchor_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Lantern Map is stolen",
        event_status="canon",
        primary_scene_id=theft_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel steals the Lantern Map from the quay.",
        consequence_summary="Mira loses the map.",
        evidence_span_ids=[str(seed_span.id)],
    )
    invalid_later_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="discovery",
        title="Orrin burns the map",
        event_status="canon",
        primary_scene_id=invalid_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "orrin", "label": "Orrin"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3-false-aftermath",
        summary="Orrin burns the Lantern Map after the theft.",
        consequence_summary=None,
        evidence_span_ids=[str(cross_project_span.id)],
    )
    valid_later_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="decision",
        title="Mira hides in the archive",
        event_status="canon",
        primary_scene_id=valid_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira", "label": "Mira"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3-after-theft",
        summary="Mira hides in the archive after the map is stolen.",
        consequence_summary=None,
        evidence_span_ids=[str(valid_later_span.id)],
    )
    session.add_all(
        [
            chapter,
            theft_scene,
            invalid_scene,
            valid_scene,
            valid_later_span,
            anchor_event,
            invalid_later_event,
            valid_later_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-event-after-cross-project-span",
            idempotency_key="idem-answer-event-after-cross-project-span",
            question="What happened after the Lantern Map was stolen?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "After Lantern Map is stolen: Mira hides in the archive - "
        "Mira hides in the archive after the map is stolen."
    )
    assert "Orrin burns the map" not in output.answer
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(valid_later_span.id)},
    ]
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.source_span_refs
    assert output.affected_entities == [
        {"type": "character", "id": "mira", "label": "Mira"},
        {"type": "object", "id": "lantern-map", "label": "Lantern Map"},
    ]
    assert output.caveats == ["timeline_order_from_scene_position"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_uses_scene_overlap_for_during_event_questions(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=150,
        summary=None,
    )
    quay_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="storm hour",
        start_offset=0,
        end_offset=70,
    )
    next_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="after storm",
        start_offset=71,
        end_offset=140,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = quay_scene.id
    chant_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=quay_scene.id,
        start_offset=30,
        end_offset=60,
        raw_start_offset=30,
        raw_end_offset=60,
        text_preview="Orrin chants under the same storm bell.",
        narration_layer="narrator",
    )
    later_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=next_scene.id,
        start_offset=80,
        end_offset=120,
        raw_start_offset=80,
        raw_end_offset=120,
        text_preview="Mira leaves after the storm ends.",
        narration_layer="narrator",
    )
    anchor_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Lantern Map is stolen",
        event_status="canon",
        primary_scene_id=quay_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="storm hour",
        summary="Kestrel steals the Lantern Map during the storm bell.",
        consequence_summary="Mira loses the map.",
        evidence_span_ids=[str(seed_span.id)],
    )
    overlapping_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="revelation",
        title="Orrin starts the storm chant",
        event_status="canon",
        primary_scene_id=quay_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "orrin", "label": "Orrin"}],
        objects=[],
        location_entity_id=None,
        story_time="storm hour",
        summary="Orrin chants under the same storm bell while the map is stolen.",
        consequence_summary=None,
        evidence_span_ids=[str(chant_span.id)],
    )
    later_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="travel",
        title="Mira leaves the quay",
        event_status="canon",
        primary_scene_id=next_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira", "label": "Mira"}],
        objects=[],
        location_entity_id=None,
        story_time="after storm",
        summary="Mira leaves after the storm ends.",
        consequence_summary=None,
        evidence_span_ids=[str(later_span.id)],
    )
    session.add_all(
        [
            chapter,
            quay_scene,
            next_scene,
            chant_span,
            later_span,
            anchor_event,
            overlapping_event,
            later_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-event-overlap",
            idempotency_key="idem-answer-event-overlap",
            question="What was happening while the Lantern Map was stolen?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "During Lantern Map is stolen: Orrin starts the storm chant - "
        "Orrin chants under the same storm bell while the map is stolen."
    )
    assert output.confidence == 0.9
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(chant_span.id)},
    ]
    assert output.affected_entities == [{"type": "character", "id": "orrin", "label": "Orrin"}]
    assert output.caveats == ["event_overlap_from_scene_or_story_time"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_event_overlap_ignores_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="A different story says Selene lights a false beacon during the theft.",
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    quay_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="storm hour",
        start_offset=0,
        end_offset=100,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = quay_scene.id
    chant_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=quay_scene.id,
        start_offset=40,
        end_offset=80,
        raw_start_offset=40,
        raw_end_offset=80,
        text_preview="Orrin chants under the same storm bell.",
        narration_layer="narrator",
    )
    anchor_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Lantern Map is stolen",
        event_status="canon",
        primary_scene_id=quay_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="storm hour",
        summary="Kestrel steals the Lantern Map during the storm bell.",
        consequence_summary="Mira loses the map.",
        evidence_span_ids=[str(seed_span.id)],
    )
    invalid_overlapping_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="foreshadowing",
        title="Selene lights a false beacon",
        event_status="canon",
        primary_scene_id=quay_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "selene", "label": "Selene"}],
        objects=[],
        location_entity_id=None,
        story_time="storm hour",
        summary="Selene lights a false beacon while the map is stolen.",
        consequence_summary=None,
        evidence_span_ids=[str(cross_project_span.id)],
    )
    valid_overlapping_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="revelation",
        title="Orrin starts the storm chant",
        event_status="canon",
        primary_scene_id=quay_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "orrin", "label": "Orrin"}],
        objects=[],
        location_entity_id=None,
        story_time="storm hour",
        summary="Orrin chants under the same storm bell while the map is stolen.",
        consequence_summary=None,
        evidence_span_ids=[str(chant_span.id)],
    )
    session.add_all(
        [
            chapter,
            quay_scene,
            chant_span,
            anchor_event,
            invalid_overlapping_event,
            valid_overlapping_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-event-overlap-cross-project-span",
            idempotency_key="idem-answer-event-overlap-cross-project-span",
            question="What was happening while the Lantern Map was stolen?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "During Lantern Map is stolen: Orrin starts the storm chant - "
        "Orrin chants under the same storm bell while the map is stolen."
    )
    assert "Selene lights a false beacon" not in output.answer
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(chant_span.id)},
    ]
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.source_span_refs
    assert output.affected_entities == [{"type": "character", "id": "orrin", "label": "Orrin"}]
    assert output.caveats == ["event_overlap_from_scene_or_story_time"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_uses_story_time_ranges_for_during_event_questions(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=240,
        summary=None,
    )
    theft_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="storm hour 1-3",
        start_offset=0,
        end_offset=70,
    )
    ritual_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="storm hour 2",
        start_offset=71,
        end_offset=150,
    )
    aftermath_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        story_time="storm hour 4",
        start_offset=151,
        end_offset=230,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = theft_scene.id
    ritual_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=ritual_scene.id,
        start_offset=90,
        end_offset=130,
        raw_start_offset=90,
        raw_end_offset=130,
        text_preview="Orrin seals the tide gate during the second storm hour.",
        narration_layer="narrator",
    )
    aftermath_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=aftermath_scene.id,
        start_offset=170,
        end_offset=215,
        raw_start_offset=170,
        raw_end_offset=215,
        text_preview="Mira reaches the quay after the storm window closes.",
        narration_layer="narrator",
    )
    anchor_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Lantern Map is stolen",
        event_status="canon",
        primary_scene_id=theft_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "kestrel", "label": "Kestrel"}],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="storm hour 1-3",
        summary="Kestrel steals the Lantern Map during storm hours one through three.",
        consequence_summary="Mira loses the map.",
        evidence_span_ids=[str(seed_span.id)],
    )
    overlapping_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="revelation",
        title="Orrin seals the tide gate",
        event_status="canon",
        primary_scene_id=ritual_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "orrin", "label": "Orrin"}],
        objects=[],
        location_entity_id=None,
        story_time="storm hour 2",
        summary="Orrin seals the tide gate during the second storm hour.",
        consequence_summary=None,
        evidence_span_ids=[str(ritual_span.id)],
    )
    later_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="travel",
        title="Mira reaches the quay",
        event_status="canon",
        primary_scene_id=aftermath_scene.id,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira", "label": "Mira"}],
        objects=[],
        location_entity_id=None,
        story_time="storm hour 4",
        summary="Mira reaches the quay after the storm window closes.",
        consequence_summary=None,
        evidence_span_ids=[str(aftermath_span.id)],
    )
    session.add_all(
        [
            chapter,
            theft_scene,
            ritual_scene,
            aftermath_scene,
            ritual_span,
            aftermath_span,
            anchor_event,
            overlapping_event,
            later_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-event-range-overlap",
            idempotency_key="idem-answer-event-range-overlap",
            question="What was happening while the Lantern Map was stolen?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "During Lantern Map is stolen: Orrin seals the tide gate - "
        "Orrin seals the tide gate during the second storm hour."
    )
    assert output.confidence == 0.9
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(ritual_span.id)},
    ]
    assert output.affected_entities == [{"type": "character", "id": "orrin", "label": "Orrin"}]
    assert output.caveats == ["event_overlap_from_scene_or_story_time"]
    assert output.related_review_items == []
    assert "Mira reaches the quay" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


@pytest.mark.parametrize(
    ("question", "request_id", "idempotency_key"),
    [
        (
            "Why are Kestrel and Mira enemies?",
            "req-answer-relationship",
            "idem-answer-relationship",
        ),
        (
            "Kestrel 和 Mira 为什么敌对？",
            "req-answer-relationship-cn",
            "idem-answer-relationship-cn",
        ),
    ],
)
def test_memory_answer_explains_relationship_from_fact_and_event_evidence(
    session: Session,
    question: str,
    request_id: str,
    idempotency_key: str,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    cause_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=80,
        raw_start_offset=25,
        raw_end_offset=80,
        text_preview="Kestrel framed Mira at the council.",
        narration_layer="narrator",
    )
    relationship_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="enemy_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.87,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cause_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="betrayal",
        title="Kestrel frames Mira at the council",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
            {"type": "character", "id": str(mira.id), "label": "Mira"},
        ],
        objects=[],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel frames Mira at the council, making Mira distrust him.",
        consequence_summary="Mira refuses to ally with him.",
        evidence_span_ids=[str(cause_span.id)],
    )
    session.add_all([kestrel, mira, cause_span, relationship_fact, cause_event])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            question=question,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Kestrel enemy_of Mira because Kestrel frames Mira at the council - "
        "Kestrel frames Mira at the council, making Mira distrust him. "
        "Consequence: Mira refuses to ally with him."
    )
    assert output.confidence == 0.87
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(cause_span.id)},
    ]
    assert output.affected_entities == [relationship_fact.subject_ref, relationship_fact.object_ref]
    assert output.caveats == ["relationship_explained_by_canonical_event"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_infers_relationship_predicate_from_paraphrase(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    enemy_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=80,
        raw_start_offset=25,
        raw_end_offset=80,
        text_preview="Kestrel betrayed Mira before the harbor vote.",
        narration_layer="narrator",
    )
    ally_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.96,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    enemy_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=ally_fact.subject_ref,
        predicate="enemy_of",
        object_ref=ally_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(enemy_span.id)],
        confidence=0.77,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cause_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="betrayal",
        title="Kestrel betrays Mira before the harbor vote",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
            {"type": "character", "id": str(mira.id), "label": "Mira"},
        ],
        objects=[],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel betrays Mira before the harbor vote, ending her trust.",
        consequence_summary="Mira refuses to share the Lantern Map.",
        evidence_span_ids=[str(enemy_span.id)],
    )
    session.add_all([kestrel, mira, enemy_span, ally_fact, enemy_fact, cause_event])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-paraphrase",
            idempotency_key="idem-answer-relationship-paraphrase",
            question="Why did Mira stop trusting Kestrel?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Kestrel enemy_of Mira because Kestrel betrays Mira before the harbor vote - "
        "Kestrel betrays Mira before the harbor vote, ending her trust. "
        "Consequence: Mira refuses to share the Lantern Map."
    )
    assert output.confidence == 0.77
    assert output.source_span_refs == [{"type": "source_span", "id": str(enemy_span.id)}]
    assert output.affected_entities == [enemy_fact.subject_ref, enemy_fact.object_ref]
    assert output.caveats == ["relationship_explained_by_canonical_event"]
    assert "ally_of" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_explanation_ignores_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="A different story says Kestrel betrayed Mira twice.",
    )
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    valid_event_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=80,
        raw_start_offset=25,
        raw_end_offset=80,
        text_preview="Kestrel framed Mira at the council.",
        narration_layer="narrator",
    )
    valid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="enemy_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.87,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    invalid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=valid_fact.subject_ref,
        predicate="enemy_of",
        object_ref=valid_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    valid_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="betrayal",
        title="Kestrel frames Mira at the council",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
            {"type": "character", "id": str(mira.id), "label": "Mira"},
        ],
        objects=[],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel frames Mira at the council, making Mira distrust him.",
        consequence_summary=None,
        evidence_span_ids=[str(valid_event_span.id)],
    )
    invalid_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="betrayal",
        title="Kestrel betrays Mira twice",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
            {"type": "character", "id": str(mira.id), "label": "Mira"},
        ],
        objects=[],
        location_entity_id=None,
        story_time="chapter-3-alt",
        summary="Kestrel betrays Mira twice in a different story.",
        consequence_summary=None,
        evidence_span_ids=[str(cross_project_span.id)],
    )
    session.add_all(
        [
            kestrel,
            mira,
            valid_event_span,
            valid_fact,
            invalid_fact,
            valid_event,
            invalid_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-explanation-cross-project-span",
            idempotency_key="idem-answer-relationship-explanation-cross-project-span",
            question="Why are Kestrel and Mira enemies?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Kestrel enemy_of Mira because Kestrel frames Mira at the council - "
        "Kestrel frames Mira at the council, making Mira distrust him."
    )
    assert "betrays Mira twice" not in output.answer
    assert output.confidence == 0.87
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(valid_event_span.id)},
    ]
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.source_span_refs
    assert output.affected_entities == [valid_fact.subject_ref, valid_fact.object_ref]
    assert output.caveats == ["relationship_explained_by_canonical_event"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_matches_relationship_endpoint_from_entity_description(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description="The map thief who stole the Lantern Map.",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description="The harbor clerk who stalled Mira's petition.",
    )
    kestrel_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=80,
        raw_start_offset=25,
        raw_end_offset=80,
        text_preview="Kestrel betrayed Mira and stole the Lantern Map.",
        narration_layer="narrator",
    )
    orrin_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=81,
        end_offset=130,
        raw_start_offset=81,
        raw_end_offset=130,
        text_preview="Orrin opposed Mira at the harbor office.",
        narration_layer="narrator",
    )
    kestrel_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="enemy_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(kestrel_span.id)],
        confidence=0.77,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="enemy_of",
        object_ref=kestrel_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(orrin_span.id)],
        confidence=0.96,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    cause_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="betrayal",
        title="Kestrel steals the Lantern Map",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[
            {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
            {"type": "character", "id": str(mira.id), "label": "Mira"},
        ],
        objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Kestrel steals the Lantern Map, making Mira distrust him.",
        consequence_summary="Mira refuses to share the route.",
        evidence_span_ids=[str(kestrel_span.id)],
    )
    session.add_all(
        [
            kestrel,
            mira,
            orrin,
            kestrel_span,
            orrin_span,
            kestrel_fact,
            orrin_fact,
            cause_event,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-description-endpoint",
            idempotency_key="idem-answer-relationship-description-endpoint",
            question="Why does Mira distrust the map thief?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Kestrel enemy_of Mira because Kestrel steals the Lantern Map - "
        "Kestrel steals the Lantern Map, making Mira distrust him. "
        "Consequence: Mira refuses to share the route."
    )
    assert output.confidence == 0.77
    assert output.source_span_refs == [{"type": "source_span", "id": str(kestrel_span.id)}]
    assert output.affected_entities == [kestrel_fact.subject_ref, kestrel_fact.object_ref]
    assert output.caveats == ["relationship_explained_by_canonical_event"]
    assert "Orrin" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


@pytest.mark.parametrize(
    ("question", "request_id", "idempotency_key"),
    [
        (
            "How did Kestrel and Mira's relationship change over time?",
            "req-answer-relationship-timeline",
            "idem-answer-relationship-timeline",
        ),
        (
            "Kestrel 和 Mira 的关系如何变化？",
            "req-answer-relationship-timeline-cn",
            "idem-answer-relationship-timeline-cn",
        ),
    ],
)
def test_memory_answer_orders_relationship_evolution_from_scene_evidence(
    session: Session,
    question: str,
    request_id: str,
    idempotency_key: str,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=140,
        summary=None,
    )
    pact_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=60,
    )
    betrayal_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=61,
        end_offset=130,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = pact_scene.id
    seed_span.text_preview = "Kestrel and Mira signed a harbor pact."
    betrayal_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=betrayal_scene.id,
        start_offset=70,
        end_offset=118,
        raw_start_offset=70,
        raw_end_offset=118,
        text_preview="Kestrel betrayed Mira before the council.",
        narration_layer="narrator",
    )
    ally_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="outdated",
        valid_from_scene_id=pact_scene.id,
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.82,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    enemy_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=ally_fact.subject_ref,
        predicate="enemy_of",
        object_ref=ally_fact.object_ref,
        fact_status="canon",
        valid_from_scene_id=betrayal_scene.id,
        evidence_span_ids=[str(betrayal_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [kestrel, mira, chapter, pact_scene, betrayal_scene, betrayal_span, ally_fact, enemy_fact]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            question=question,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Relationship timeline: Chapter 1 / Scene 1: Kestrel ally_of Mira "
        "(outdated) - Kestrel and Mira signed a harbor pact.; Chapter 1 / Scene 2: "
        "Kestrel enemy_of Mira (canon) - Kestrel betrayed Mira before the council."
    )
    assert output.confidence == 0.82
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(betrayal_span.id)},
    ]
    assert output.affected_entities == [ally_fact.subject_ref, ally_fact.object_ref]
    assert output.caveats == ["relationship_timeline_from_scene_position"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_timeline_ignores_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="A different story says Kestrel and Mira were rivals first.",
    )
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=180,
        summary=None,
    )
    pact_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=55,
    )
    false_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=56,
        end_offset=95,
    )
    betrayal_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="third_limited",
        start_offset=96,
        end_offset=170,
    )
    seed_span.chapter_id = chapter.id
    seed_span.scene_id = pact_scene.id
    seed_span.text_preview = "Kestrel and Mira signed a harbor pact."
    betrayal_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=betrayal_scene.id,
        start_offset=110,
        end_offset=155,
        raw_start_offset=110,
        raw_end_offset=155,
        text_preview="Kestrel betrayed Mira before the council.",
        narration_layer="narrator",
    )
    ally_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="outdated",
        valid_from_scene_id=pact_scene.id,
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.82,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    invalid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=ally_fact.subject_ref,
        predicate="related_to",
        object_ref=ally_fact.object_ref,
        fact_status="outdated",
        valid_from_scene_id=false_scene.id,
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    enemy_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=ally_fact.subject_ref,
        predicate="enemy_of",
        object_ref=ally_fact.object_ref,
        fact_status="canon",
        valid_from_scene_id=betrayal_scene.id,
        evidence_span_ids=[str(betrayal_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            kestrel,
            mira,
            chapter,
            pact_scene,
            false_scene,
            betrayal_scene,
            betrayal_span,
            ally_fact,
            invalid_fact,
            enemy_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-timeline-cross-project-span",
            idempotency_key="idem-answer-relationship-timeline-cross-project-span",
            question="How did Kestrel and Mira's relationship change over time?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Relationship timeline: Chapter 1 / Scene 1: Kestrel ally_of Mira "
        "(outdated) - Kestrel and Mira signed a harbor pact.; Chapter 1 / Scene 3: "
        "Kestrel enemy_of Mira (canon) - Kestrel betrayed Mira before the council."
    )
    assert "related_to" not in output.answer
    assert output.confidence == 0.82
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(betrayal_span.id)},
    ]
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.source_span_refs
    assert output.affected_entities == [ally_fact.subject_ref, ally_fact.object_ref]
    assert output.caveats == ["relationship_timeline_from_scene_position"]
    assert output.related_review_items == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


@pytest.mark.parametrize(
    ("question", "request_id", "idempotency_key", "expected_answer", "expected_ref_labels"),
    [
        (
            "How is Kestrel connected to Orrin?",
            "req-answer-relationship-path",
            "idem-answer-relationship-path",
            "Relationship path: Kestrel ally_of Mira; Mira family_of Orrin",
            ["Kestrel", "Mira", "Orrin"],
        ),
        (
            "How is Orrin connected to Kestrel?",
            "req-answer-relationship-path-reversed",
            "idem-answer-relationship-path-reversed",
            "Relationship path: Orrin family_of Mira; Mira ally_of Kestrel",
            ["Orrin", "Mira", "Kestrel"],
        ),
        (
            "Kestrel 和 Orrin 通过谁联系？",
            "req-answer-relationship-path-cn",
            "idem-answer-relationship-path-cn",
            "Relationship path: Kestrel ally_of Mira; Mira family_of Orrin",
            ["Kestrel", "Mira", "Orrin"],
        ),
        (
            "Kestrel 和 Orrin 是怎么认识的？",
            "req-answer-relationship-path-cn-paraphrase",
            "idem-answer-relationship-path-cn-paraphrase",
            "Relationship path: Kestrel ally_of Mira; Mira family_of Orrin",
            ["Kestrel", "Mira", "Orrin"],
        ),
        (
            "Kestrel 和 Orrin 如何相识？",
            "req-answer-relationship-path-cn-acquainted",
            "idem-answer-relationship-path-cn-acquainted",
            "Relationship path: Kestrel ally_of Mira; Mira family_of Orrin",
            ["Kestrel", "Mira", "Orrin"],
        ),
    ],
)
def test_memory_answer_finds_two_hop_relationship_path_from_fact_evidence(
    session: Session,
    question: str,
    request_id: str,
    idempotency_key: str,
    expected_answer: str,
    expected_ref_labels: list[str],
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    seed_span.text_preview = "Kestrel and Mira kept the harbor pact."
    kinship_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Mira calls Orrin her brother.",
        narration_layer="narrator",
    )
    kestrel_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.84,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=kestrel_mira_fact.object_ref,
        predicate="family_of",
        object_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unrelated_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "dockmaster", "label": "Dockmaster"},
        predicate="ally_of",
        object_ref={"type": "character", "id": "guard", "label": "Guard"},
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [kestrel, mira, orrin, kinship_span, kestrel_mira_fact, mira_orrin_fact, unrelated_fact]
    )
    session.commit()
    refs_by_label = {
        "Kestrel": kestrel_mira_fact.subject_ref,
        "Mira": kestrel_mira_fact.object_ref,
        "Orrin": mira_orrin_fact.object_ref,
    }

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            question=question,
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == expected_answer
    assert output.confidence == 0.84
    if expected_ref_labels[0] == "Orrin":
        assert output.source_span_refs == [
            {"type": "source_span", "id": str(kinship_span.id)},
            {"type": "source_span", "id": str(seed_span.id)},
        ]
    else:
        assert output.source_span_refs == [
            {"type": "source_span", "id": str(seed_span.id)},
            {"type": "source_span", "id": str(kinship_span.id)},
        ]
    assert output.affected_entities == [refs_by_label[label] for label in expected_ref_labels]
    assert output.caveats == ["relationship_path_from_fact_evidence"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Dockmaster" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_finds_multi_hop_relationship_path_from_fact_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    seed_span.text_preview = "Kestrel and Mira kept the harbor pact."
    kinship_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Mira calls Orrin her brother.",
        narration_layer="narrator",
    )
    archive_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=75,
        end_offset=122,
        raw_start_offset=75,
        raw_end_offset=122,
        text_preview="Orrin kept Ilya's archive pass.",
        narration_layer="narrator",
    )
    kestrel_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_orrin_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=kestrel_mira_fact.object_ref,
        predicate="family_of",
        object_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.86,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    orrin_ilya_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=mira_orrin_fact.object_ref,
        predicate="related_to",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(archive_span.id)],
        confidence=0.79,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unrelated_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "dockmaster", "label": "Dockmaster"},
        predicate="ally_of",
        object_ref={"type": "character", "id": "guard", "label": "Guard"},
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            kestrel,
            mira,
            orrin,
            ilya,
            kinship_span,
            archive_span,
            kestrel_mira_fact,
            mira_orrin_fact,
            orrin_ilya_fact,
            unrelated_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-multi-hop-path",
            idempotency_key="idem-answer-relationship-multi-hop-path",
            question="How is Kestrel connected to Ilya?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == (
        "Relationship path: Kestrel ally_of Mira; Mira family_of Orrin; Orrin related_to Ilya"
    )
    assert output.confidence == 0.79
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(kinship_span.id)},
        {"type": "source_span", "id": str(archive_span.id)},
    ]
    assert output.affected_entities == [
        kestrel_mira_fact.subject_ref,
        kestrel_mira_fact.object_ref,
        mira_orrin_fact.object_ref,
        orrin_ilya_fact.object_ref,
    ]
    assert output.caveats == ["relationship_path_from_fact_evidence"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Dockmaster" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_path_ignores_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    other_project = Project(id=uuid4(), name="Other Story")
    other_source = RawSource(
        id=uuid4(),
        project_id=other_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/other-chapter",
    )
    other_version = SourceVersion(
        id=uuid4(),
        source_id=other_source.id,
        version_label="v1",
        raw_hash="other-hash-v1",
    )
    other_view = SourceProcessedView(
        id=uuid4(),
        version_id=other_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/other",
        raw_offset_map_ref="object://offsets/other",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=other_source.id,
        version_id=other_version.id,
        view_id=other_view.id,
        start_offset=0,
        end_offset=45,
        raw_start_offset=0,
        raw_end_offset=45,
        text_preview="Kestrel is directly tied to Ilya in another story.",
        narration_layer="narrator",
    )
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    seed_span.text_preview = "Kestrel and Mira kept the harbor pact."
    kinship_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Mira names Ilya as family.",
        narration_layer="narrator",
    )
    direct_cross_project_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="related_to",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    kestrel_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=direct_cross_project_fact.subject_ref,
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.84,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_ilya_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=kestrel_mira_fact.object_ref,
        predicate="family_of",
        object_ref=direct_cross_project_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            other_project,
            other_source,
            other_version,
            other_view,
            cross_project_span,
            kestrel,
            mira,
            ilya,
            kinship_span,
            direct_cross_project_fact,
            kestrel_mira_fact,
            mira_ilya_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-path-cross-project-span",
            idempotency_key="idem-answer-relationship-path-cross-project-span",
            question="How is Kestrel connected to Ilya?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Relationship path: Kestrel ally_of Mira; Mira family_of Ilya"
    assert output.confidence == 0.84
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(kinship_span.id)},
    ]
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.source_span_refs
    assert output.affected_entities == [
        kestrel_mira_fact.subject_ref,
        kestrel_mira_fact.object_ref,
        mira_ilya_fact.object_ref,
    ]
    assert output.caveats == ["relationship_path_from_fact_evidence"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_ranks_relationship_paths_by_evidence_quality(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    dockmaster = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Dockmaster",
        canonical_status="canon",
        cast_tier="minor_supporting",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    seed_span.text_preview = "Kestrel once used the dockmaster's gate."
    dockmaster_ilya_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=77,
        raw_start_offset=30,
        raw_end_offset=77,
        text_preview="The dockmaster had a distant tie to Ilya.",
        narration_layer="narrator",
    )
    ally_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=78,
        end_offset=124,
        raw_start_offset=78,
        raw_end_offset=124,
        text_preview="Kestrel trusted Mira with the harbor pact.",
        narration_layer="narrator",
    )
    family_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=125,
        end_offset=172,
        raw_start_offset=125,
        raw_end_offset=172,
        text_preview="Mira named Ilya as family in the archive.",
        narration_layer="narrator",
    )
    weak_first_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="related_to",
        object_ref={
            "type": "character",
            "id": str(dockmaster.id),
            "label": "Dockmaster",
            "canonical_entity_id": str(dockmaster.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.51,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    weak_second_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=weak_first_fact.object_ref,
        predicate="related_to",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(dockmaster_ilya_span.id)],
        confidence=0.52,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    strong_first_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=weak_first_fact.subject_ref,
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(ally_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    strong_second_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=strong_first_fact.object_ref,
        predicate="family_of",
        object_ref=weak_second_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(family_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            kestrel,
            dockmaster,
            mira,
            ilya,
            dockmaster_ilya_span,
            ally_span,
            family_span,
            weak_first_fact,
            weak_second_fact,
            strong_first_fact,
            strong_second_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-ranked-relationship-path",
            idempotency_key="idem-answer-ranked-relationship-path",
            question="How is Kestrel connected to Ilya?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Relationship path: Kestrel ally_of Mira; Mira family_of Ilya"
    assert output.confidence == 0.88
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(ally_span.id)},
        {"type": "source_span", "id": str(family_span.id)},
    ]
    assert output.affected_entities == [
        strong_first_fact.subject_ref,
        strong_first_fact.object_ref,
        strong_second_fact.object_ref,
    ]
    assert output.caveats == ["relationship_path_from_fact_evidence"]
    assert output.unknowns == []
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is True
    assert "Dockmaster" not in output.answer
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_path_resolves_unambiguous_alias_endpoint(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    seed_span.text_preview = "Kestrel and Mira kept the harbor pact."
    kinship_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Mira calls Ilya her sister.",
        narration_layer="narrator",
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=ilya.id,
        alias_type="codename",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.82,
    )
    kestrel_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.84,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_ilya_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=kestrel_mira_fact.object_ref,
        predicate="family_of",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([kestrel, mira, ilya, kinship_span, alias, kestrel_mira_fact, mira_ilya_fact])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-alias-path",
            idempotency_key="idem-answer-relationship-alias-path",
            question="How is Kestrel connected to Starling?",
        )
    )

    assert output.answer_type == "canon"
    assert output.answer == "Relationship path: Kestrel ally_of Mira; Mira family_of Ilya"
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(kinship_span.id)},
    ]
    assert output.affected_entities == [
        kestrel_mira_fact.subject_ref,
        kestrel_mira_fact.object_ref,
        mira_ilya_fact.object_ref,
    ]
    assert output.caveats == ["relationship_path_from_fact_evidence"]
    assert output.unknowns == []
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_path_stops_on_ambiguous_description_endpoint(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description="The harbor clerk who filed Mira's petition.",
    )
    orrin = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description="The harbor clerk who blocked Mira's petition.",
    )
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    kinship_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Mira calls Ilya her sister.",
        narration_layer="narrator",
    )
    kestrel_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.84,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    mira_ilya_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref=kestrel_mira_fact.object_ref,
        predicate="family_of",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(kinship_span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    orrin_mira_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="enemy_of",
        object_ref=kestrel_mira_fact.object_ref,
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.8,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [
            kestrel,
            orrin,
            mira,
            ilya,
            kinship_span,
            kestrel_mira_fact,
            mira_ilya_fact,
            orrin_mira_fact,
        ]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-ambiguous-description-path",
            idempotency_key="idem-answer-relationship-ambiguous-description-path",
            question="How is the harbor clerk connected to Ilya?",
        )
    )

    assert output.answer_type == "unknown"
    assert output.answer == "Ambiguous entity match for `harbor clerk`: Kestrel, Orrin."
    assert output.source_span_refs == []
    assert output.affected_entities == [
        {"type": "character", "id": str(kestrel.id), "label": "Kestrel"},
        {"type": "character", "id": str(orrin.id), "label": "Orrin"},
    ]
    assert output.caveats == ["ambiguous_entity_match"]
    assert output.unknowns == ["ambiguous_entity_match"]
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_relationship_path_stops_on_ambiguous_alias_endpoint(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    kestrel = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Kestrel",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    ilya = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Ilya",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    selene = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Selene",
        canonical_status="canon",
        cast_tier="major",
        first_seen_scene_id=None,
        description=None,
    )
    alias_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=30,
        end_offset=74,
        raw_start_offset=30,
        raw_end_offset=74,
        text_preview="Two people have used the Starling name.",
        narration_layer="narrator",
    )
    ilya_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=ilya.id,
        alias_type="codename",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.82,
    )
    selene_alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="Starling",
        entity_id=selene.id,
        alias_type="codename",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(alias_span.id)],
        confidence=0.76,
    )
    relationship_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(kestrel.id),
            "label": "Kestrel",
            "canonical_entity_id": str(kestrel.id),
        },
        predicate="ally_of",
        object_ref={
            "type": "character",
            "id": str(ilya.id),
            "label": "Ilya",
            "canonical_entity_id": str(ilya.id),
        },
        fact_status="canon",
        evidence_span_ids=[str(seed_span.id)],
        confidence=0.84,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [kestrel, ilya, selene, alias_span, ilya_alias, selene_alias, relationship_fact]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-relationship-ambiguous-alias-path",
            idempotency_key="idem-answer-relationship-ambiguous-alias-path",
            question="How is Kestrel connected to Starling?",
        )
    )

    assert output.answer_type == "unknown"
    assert output.answer == "Ambiguous entity match for `Starling`: Ilya, Selene."
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(seed_span.id)},
        {"type": "source_span", "id": str(alias_span.id)},
    ]
    assert output.affected_entities == [
        {"type": "character", "id": str(ilya.id), "label": "Ilya"},
        {"type": "character", "id": str(selene.id), "label": "Selene"},
    ]
    assert output.caveats == ["ambiguous_entity_match"]
    assert output.unknowns == ["ambiguous_entity_match"]
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_reports_open_continuity_reviews_with_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    new_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=90,
        raw_start_offset=25,
        raw_end_offset=90,
        text_preview="Mira studies the Lantern Map after Kestrel stole it.",
        narration_layer="narrator",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="object_state_conflict",
        severity="high",
        status="open",
        summary="Mira uses the Lantern Map after Kestrel stole it.",
        affected_refs={"refs": [{"type": "object", "id": "lantern-map", "label": "Lantern Map"}]},
        new_evidence={"source_span_ids": [str(new_span.id)]},
        existing_evidence={"source_span_ids": [str(seed_span.id)]},
        suggested_actions=[{"action": "fixed_by_text_edit"}],
        default_action="ask_author",
    )
    session.add_all([new_span, review])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-continuity",
            idempotency_key="idem-answer-continuity",
            question="Does this chapter contradict earlier continuity?",
        )
    )

    assert output.answer_type == "conflict"
    assert output.answer == (
        "Open continuity risks: [high object_state_conflict] "
        "Mira uses the Lantern Map after Kestrel stole it."
    )
    assert output.confidence == 0.9
    assert output.source_span_refs == [
        {"type": "source_span", "id": str(new_span.id)},
        {"type": "source_span", "id": str(seed_span.id)},
    ]
    assert output.affected_entities == [
        {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
    ]
    assert output.caveats == [
        "open_review_item",
        "continuity_review_item",
        "high_severity_review",
    ]
    assert output.related_review_items == [review.id]
    assert output.safe_to_use_in_current_pov is False
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_returns_canon_with_source_spans_and_pov_safety(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    pov_character_id = uuid4()
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "lantern map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=pov_character_id,
        knows_ref={"type": "fact_assertion", "id": str(fact.id)},
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all([fact, knowledge])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-canon",
            idempotency_key="idem-answer-canon",
            question="米拉拥有什么？",
            subject_ref={"type": "character", "id": "mira", "name": "Mira"},
            predicate="owns",
            current_pov_character_id=pov_character_id,
        )
    )

    assert output.answer_type == "canon"
    assert "owns" in output.answer
    assert output.source_span_refs == [{"type": "source_span", "id": str(span.id)}]
    assert output.safe_to_use_in_current_pov is True
    assert output.confidence == 0.92
    assert output.affected_entities == [fact.subject_ref, fact.object_ref]
    assert output.caveats == []


def test_memory_answer_ignores_fact_with_only_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, _span = seed_evidence(session)
    other_project = Project(id=uuid4(), name="Other Story")
    other_source = RawSource(
        id=uuid4(),
        project_id=other_project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Other Chapter",
        ownership_status="owned",
        raw_text_ref="object://raw/other-chapter",
    )
    other_version = SourceVersion(
        id=uuid4(),
        source_id=other_source.id,
        version_label="v1",
        raw_hash="other-hash-v1",
    )
    other_view = SourceProcessedView(
        id=uuid4(),
        version_id=other_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/other",
        raw_offset_map_ref="object://offsets/other",
        view_status="current",
    )
    cross_project_span = SourceSpan(
        id=uuid4(),
        source_id=other_source.id,
        version_id=other_version.id,
        view_id=other_view.id,
        start_offset=0,
        end_offset=34,
        raw_start_offset=0,
        raw_end_offset=34,
        text_preview="Mira owns the harbor key elsewhere.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "harbor-key", "name": "harbor key"},
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all(
        [other_project, other_source, other_version, other_view, cross_project_span, fact]
    )
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-cross-project-fact-evidence",
            idempotency_key="idem-answer-cross-project-fact-evidence",
            question="What does Mira own?",
            subject_ref={"type": "character", "id": "mira", "name": "Mira"},
            predicate="owns",
        )
    )

    assert output.answer_type == "unknown"
    assert output.answer == "No SourceSpan-backed memory evidence matches this question."
    assert output.source_span_refs == []
    assert output.affected_entities == []
    assert output.caveats == ["no_matching_evidence"]
    assert output.unknowns == ["no_matching_evidence"]
    assert output.related_review_items == []
    assert output.safe_to_use_in_current_pov is False
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0


def test_memory_answer_reports_conflict_for_disputed_fact_with_open_review(
    session: Session,
) -> None:
    project, actor_id, _raw_source, _version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="knows",
        object_ref={"type": "secret", "id": "orrin_identity"},
        fact_status="disputed",
        evidence_span_ids=[str(span.id)],
        confidence=0.71,
        source_scope="user_draft",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Mira may know a secret too early.",
        affected_refs={"fact_ids": [str(fact.id)]},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([fact, review])
    session.commit()

    output = AnswerWithEvidence(uow_factory(session)).execute(
        MemoryAnswerInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-answer-conflict",
            idempotency_key="idem-answer-conflict",
            question="米拉知道奥林的身份吗？",
            subject_ref={"type": "character", "id": "mira"},
            predicate="knows",
        )
    )

    assert output.answer_type == "conflict"
    assert output.related_review_items == [review.id]
    assert output.safe_to_use_in_current_pov is False
    assert output.confidence == 0.71
    assert output.affected_entities == [fact.subject_ref, fact.object_ref]
    assert output.caveats == ["non_canon_evidence", "open_review_item"]


def test_context_pack_separates_canon_risk_and_pov_forbidden_knowledge(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    pov_character_id = uuid4()
    known_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    hidden_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "orrin", "name": "Orrin"},
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor_code"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    risk_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="knows",
        object_ref={"type": "secret", "id": "orrin_identity"},
        fact_status="disputed",
        evidence_span_ids=[str(span.id)],
        confidence=0.72,
        source_scope="user_draft",
    )
    knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=pov_character_id,
        knows_ref={"type": "fact_assertion", "id": str(known_fact.id)},
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="medium",
        status="open",
        summary="Disputed knowledge.",
        affected_refs={"fact_ids": [str(risk_fact.id)]},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="plotline",
        target_ref={"type": "plotline", "id": "harbor-conspiracy"},
        title="Harbor Conspiracy",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[{"thread": "Who moved the lantern map?"}],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="canon",
        memory_depth="standard",
    )
    session.add_all([known_fact, hidden_fact, risk_fact, knowledge, review, page])
    session.commit()

    input_data = BuildWritingContextPackInput(
        project_id=project.id,
        actor_id=actor_id,
        request_id="req-context-pack",
        idempotency_key="idem-context-pack",
        action_request_id=None,
        current_source_id=raw_source.id,
        current_version_id=version.id,
        current_scene_id=None,
        current_pov_character_id=pov_character_id,
        mode="draft_next_passage",
        current_text_window="米拉停在西档案室门口。",
    )
    first = BuildWritingContextPack(uow_factory(session)).execute(input_data)
    second = BuildWritingContextPack(uow_factory(session)).execute(input_data)

    assert second == first
    assert len(first.canonical_context["facts"]) == 2
    assert len(first.risk_context["facts"]) == 1
    assert first.risk_context["review_items"][0]["review_item_id"] == str(review.id)
    assert first.pov_constraint["allowed_knowledge"] == [
        {
            "character_id": str(pov_character_id),
            "knows_ref": knowledge.knows_ref,
            "learned_in_scene_id": None,
            "evidence_span_id": str(span.id),
            "certainty": "known",
            "hidden_from": [],
            "status": "active",
        }
    ]
    assert first.pov_constraint["forbidden_knowledge"][0]["fact_id"] == str(hidden_fact.id)
    assert first.open_threads == [
        {"thread": "Who moved the lantern map?", "source_span_ids": [str(span.id)]}
    ]
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(IdempotencyRecord).filter_by(operation="context_pack.build").count() == 1


def test_context_pack_ignores_facts_with_only_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Other story claims Mira owns the glass key.",
    )
    valid_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "lantern map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    invalid_canon_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "glass-key", "name": "glass key"},
        fact_status="canon",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.99,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    invalid_risk_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "orrin", "name": "Orrin"},
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor-code", "name": "harbor code"},
        fact_status="disputed",
        evidence_span_ids=[str(cross_project_span.id)],
        confidence=0.71,
        source_scope="user_draft",
    )
    session.add_all([valid_fact, invalid_canon_fact, invalid_risk_fact])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-cross-project-fact-evidence",
            idempotency_key="idem-context-pack-cross-project-fact-evidence",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira studies the lantern map.",
        )
    )

    assert [entry["fact_id"] for entry in output.canonical_context["facts"]] == [str(valid_fact.id)]
    assert output.risk_context["facts"] == []
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.evidence_refs
    assert session.query(FactAssertionRecord).count() == 3
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_ignores_events_with_only_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Other story says Mira crossed a different harbor.",
    )
    valid_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira takes the Lantern Map",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira"}],
        objects=[{"type": "object", "id": "lantern-map"}],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Mira takes the Lantern Map from the quay.",
        consequence_summary="Mira carries the map into the archive.",
        evidence_span_ids=[str(span.id)],
    )
    invalid_event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="travel",
        title="Mira crosses the glass harbor",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira"}],
        objects=[],
        location_entity_id=None,
        story_time="other-story",
        summary="Mira crosses the glass harbor in another project.",
        consequence_summary="This event should not enter the current project pack.",
        evidence_span_ids=[str(cross_project_span.id)],
    )
    session.add_all([valid_event, invalid_event])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-cross-project-event-evidence",
            idempotency_key="idem-context-pack-cross-project-event-evidence",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira studies the lantern map.",
        )
    )

    assert [entry["event_id"] for entry in output.recent_events] == [str(valid_event.id)]
    assert output.recent_events[0]["evidence_span_ids"] == [str(span.id)]
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.evidence_refs
    assert session.query(StoryCanonicalEvent).count() == 2
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_ignores_object_state_with_only_cross_project_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Other story says Mira left the glass key in another harbor.",
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash="state-hash-object-cross-project",
        created_edge_count=2,
    )
    valid_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(uuid4())},
        subject_ref={"type": "character", "id": "mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map"},
        edge_status="canon",
        evidence_refs=[
            {"type": "source_span", "id": str(span.id)},
            {"type": "source_span", "id": str(cross_project_span.id)},
            {"type": "fact_assertion", "id": str(uuid4())},
        ],
    )
    invalid_edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(uuid4())},
        subject_ref={"type": "object", "id": "glass-key"},
        relation="located_in",
        target_ref={"type": "location", "id": "other-harbor"},
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(cross_project_span.id)}],
    )
    invalid_page_fact_id = uuid4()
    memory_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="object",
        target_ref={"type": "object", "id": "glass-key", "name": "Glass Key"},
        title="Glass Key",
        current_canon={
            "state_facts": [
                {
                    "fact_id": str(invalid_page_fact_id),
                    "predicate": "located_in",
                    "state_type": "object_location",
                    "subject_ref": {"type": "object", "id": "glass-key", "name": "Glass Key"},
                    "object_ref": {
                        "type": "location",
                        "id": "other-harbor",
                        "name": "Other Harbor",
                    },
                    "evidence_span_ids": [str(cross_project_span.id)],
                }
            ]
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([run, valid_edge, invalid_edge, memory_page])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-cross-project-object-evidence",
            idempotency_key="idem-context-pack-cross-project-object-evidence",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira studies the lantern map.",
        )
    )

    assert [entry["edge_id"] for entry in output.object_location_state] == [str(valid_edge.id)]
    assert output.object_location_state[0]["evidence_refs"] == [
        {"type": "source_span", "id": str(span.id)}
    ]
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.evidence_refs
    assert session.query(GraphProjectionEdge).count() == 2
    assert session.query(MemoryPage).count() == 1
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_validates_style_review_and_open_thread_source_span_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, _version, span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Other story style sample and review evidence.",
    )
    valid_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="high",
        status="open",
        summary="Keep the lantern map hidden until Mira reaches the archive.",
        affected_refs={"character_id": "mira"},
        new_evidence={
            "source_span_ids": [str(cross_project_span.id), str(span.id)],
            "note": "mixed evidence should keep only same-project spans",
        },
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    invalid_review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="medium",
        status="open",
        summary="Other-story warning should not enter this context pack.",
        affected_refs={"character_id": "mira"},
        new_evidence={"source_span_ids": [str(cross_project_span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    valid_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "name": "Mira"},
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "map-thread",
                "status": "open",
                "summary": "Mira still needs to hide the lantern map.",
                "source_span_ids": [str(cross_project_span.id), str(span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    invalid_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="plotline",
        target_ref={"type": "plotline", "id": "other-thread"},
        title="Other Thread",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[
            {
                "id": "other-thread",
                "status": "open",
                "summary": "Other-story thread should not enter this context pack.",
                "source_span_ids": [str(cross_project_span.id)],
            }
        ],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(cross_project_span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    session.add_all([valid_review, invalid_review, valid_page, invalid_page])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-cross-project-style-review-open-thread",
            idempotency_key="idem-context-pack-cross-project-style-review-open-thread",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=cross_project_span.version_id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira keeps the lantern map hidden.",
        )
    )

    assert output.style_memory["samples"] == []
    assert [item["review_item_id"] for item in output.risk_context["review_items"]] == [
        str(valid_review.id)
    ]
    assert output.risk_context["review_items"][0]["new_evidence"]["source_span_ids"] == [
        str(span.id)
    ]
    assert output.risk_context["review_items"][0]["evidence_span_ids"] == [str(span.id)]
    assert output.open_threads == [
        {
            "id": "map-thread",
            "status": "open",
            "summary": "Mira still needs to hide the lantern map.",
            "source_span_ids": [str(span.id)],
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs
    assert {"type": "source_span", "id": str(cross_project_span.id)} not in output.evidence_refs
    assert session.query(ReviewItemRecord).count() == 2
    assert session.query(MemoryPage).count() == 2
    assert session.query(AgentContextPackRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0


def test_context_pack_ranks_canonical_facts_by_current_relevance(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Mira",
        start_offset=0,
        end_offset=24,
        summary=None,
    )
    scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=mira.id,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=24,
    )
    span.chapter_id = chapter.id
    span.scene_id = scene.id
    relevant_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": str(mira.id), "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "lantern map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    appears_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": str(mira.id), "label": "Mira"},
        predicate="appears_in",
        object_ref={"type": "scene", "id": str(scene.id), "label": "Scene 1"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=1.0,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unrelated_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "location", "id": "eastern-tower", "label": "Eastern Tower"},
        predicate="located_in",
        object_ref={"type": "location", "id": "old-city", "label": "Old City"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.88,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, chapter, scene, unrelated_fact, appears_fact, relevant_fact])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-ranking",
            idempotency_key="idem-context-pack-ranking",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=scene.id,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Continue with Mira protecting the lantern map.",
        )
    )

    facts = output.canonical_context["facts"]
    assert facts[0]["fact_id"] == str(relevant_fact.id)
    assert facts[0]["relevance"]["score"] > facts[-1]["relevance"]["score"]
    assert set(facts[0]["relevance"]["reasons"]) >= {
        "current_scene_evidence",
        "active_character",
        "pov_character",
        "intent_match",
        "current_source_evidence",
        "current_version_evidence",
    }
    assert facts[-1]["fact_id"] == str(unrelated_fact.id)
    assert output.canonical_context["retrieval_policy"] == {
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
    assert session.query(FactAssertionRecord).count() == 3
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_ranks_facts_by_alias_and_memory_semantic_recall(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000aa"),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="the informant",
        entity_id=mira.id,
        alias_type="title",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(span.id)],
        confidence=0.76,
    )
    memory_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira",
        current_canon={},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[{"id": "informant-thread", "summary": "The informant must stay unnamed."}],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_fact = FactAssertionRecord(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    alias_backed_fact = FactAssertionRecord(
        id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, orrin, alias, memory_page, unrelated_fact, alias_backed_fact])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-semantic-recall",
            idempotency_key="idem-context-pack-semantic-recall",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Let the informant stay hidden for one more beat.",
        )
    )

    facts = output.canonical_context["facts"]
    assert facts[0]["fact_id"] == str(alias_backed_fact.id)
    assert "semantic_recall" in facts[0]["relevance"]["reasons"]
    assert facts[0]["relevance"]["score"] > facts[1]["relevance"]["score"]
    assert output.canonical_context["retrieval_policy"]["semantic_recall"] == {
        "sources": ["alias_records", "memory_pages"],
        "mode": "read_only_vocabulary_expansion",
    }
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryCanonicalEntity).count() == 2
    assert session.query(StoryAliasRecord).count() == 1
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_ranks_facts_by_persisted_embedding_semantic_recall(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000aa"),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    memory_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira dossier",
        current_canon={"role_note": "Secret informant must remain unnamed."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_fact = FactAssertionRecord(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    embedding_backed_fact = FactAssertionRecord(
        id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, orrin, memory_page, unrelated_fact, embedding_backed_fact])
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refreshed = refresh_memory_page_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    assert refreshed == 1
    assert session.query(SemanticEmbeddingRecord).count() == 1

    output = BuildWritingContextPack(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-embedding-recall",
            idempotency_key="idem-context-pack-embedding-recall",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Clandestine contact waits.",
        )
    )

    facts = output.canonical_context["facts"]
    assert facts[0]["fact_id"] == str(embedding_backed_fact.id)
    assert "semantic_recall" in facts[0]["relevance"]["reasons"]
    assert facts[0]["relevance"]["score"] > facts[1]["relevance"]["score"]
    assert output.canonical_context["retrieval_policy"]["semantic_recall"] == {
        "sources": ["semantic_embedding_index"],
        "mode": "embedding_index_recall",
        "embedding": {
            "provider": "local_deterministic",
            "model": "local-semantic-hash-v1",
            "matches": 1,
        },
    }
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(StoryCanonicalEntity).count() == 2
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_uses_source_span_and_style_embedding_recall(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    relevant_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=48,
        end_offset=96,
        raw_start_offset=48,
        raw_end_offset=96,
        text_preview="Secret informant keeps the clipped sentence rhythm.",
        narration_layer="narrator",
    )
    unrelated_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=120,
        end_offset=160,
        raw_start_offset=120,
        raw_end_offset=160,
        text_preview="Lantern inventory rests on the quay.",
        narration_layer="narrator",
    )
    mira = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000aa"),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    relevant_fact = FactAssertionRecord(
        id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(relevant_span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    unrelated_fact = FactAssertionRecord(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="canon",
        evidence_span_ids=[str(unrelated_span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([relevant_span, unrelated_span, mira, orrin, relevant_fact, unrelated_fact])
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refreshed = refresh_project_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    assert refreshed == {
        "memory_page": 0,
        "source_span": 3,
        "style_sample": 3,
    }
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="source_span").count() == 3
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="style_sample").count() == 3

    output = BuildWritingContextPack(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-source-span-embedding-recall",
            idempotency_key="idem-context-pack-source-span-embedding-recall",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Clandestine contact waits in clipped sentences.",
        )
    )

    facts = output.canonical_context["facts"]
    assert facts[0]["fact_id"] == str(relevant_fact.id)
    assert "semantic_recall" in facts[0]["relevance"]["reasons"]
    assert facts[0]["relevance"]["score"] > facts[1]["relevance"]["score"]
    samples = output.style_memory["samples"]
    assert samples[0]["source_span_id"] == str(relevant_span.id)
    assert "semantic_recall" in samples[0]["relevance"]["reasons"]
    assert samples[0]["relevance"]["score"] > samples[1]["relevance"]["score"]
    assert output.canonical_context["retrieval_policy"]["semantic_recall"] == {
        "sources": ["semantic_embedding_index"],
        "mode": "embedding_index_recall",
        "embedding": {
            "provider": "local_deterministic",
            "model": "local-semantic-hash-v1",
            "matches": 2,
        },
    }
    assert session.query(FactAssertionRecord).count() == 2
    assert session.query(GraphProjectionEdge).count() == 0
    assert session.query(ReviewItemRecord).count() == 0


def test_context_pack_reports_rrf_hybrid_recall_when_keyword_and_embedding_both_apply(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    mira = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000aa"),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    orrin = StoryCanonicalEntity(
        id=UUID("00000000-0000-4000-8000-0000000000bb"),
        project_id=project.id,
        entity_type="character",
        display_name="Orrin",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    alias = StoryAliasRecord(
        id=uuid4(),
        project_id=project.id,
        alias_text="the informant",
        entity_id=mira.id,
        alias_type="title",
        status="proposed",
        scope="global",
        evidence_span_ids=[str(span.id)],
        confidence=0.76,
    )
    memory_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        title="Mira",
        current_canon={"role_note": "The informant hides the ledger."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[{"id": "informant-thread", "summary": "The informant must stay unnamed."}],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    unrelated_fact = FactAssertionRecord(
        id=UUID("00000000-0000-4000-8000-000000000001"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(orrin.id),
            "label": "Orrin",
            "canonical_entity_id": str(orrin.id),
        },
        predicate="located_in",
        object_ref={"type": "location", "id": "harbor-nine", "label": "Harbor Nine"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    relevant_fact = FactAssertionRecord(
        id=UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="owns",
        object_ref={"type": "object", "id": "ledger", "label": "ledger"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, orrin, alias, memory_page, unrelated_fact, relevant_fact])
    session.commit()

    embedding_provider = LocalEmbeddingProvider()
    refreshed = refresh_memory_page_semantic_embeddings(
        session,
        project_id=project.id,
        embedding_client=embedding_provider,
    )
    session.commit()

    assert refreshed == 1

    output = BuildWritingContextPack(
        lambda: SqlAlchemyUnitOfWork(session, embedding_client=embedding_provider)
    ).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-rrf-hybrid",
            idempotency_key="idem-context-pack-rrf-hybrid",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Let the informant hide the ledger for one more beat.",
        )
    )

    facts = output.canonical_context["facts"]
    assert facts[0]["fact_id"] == str(relevant_fact.id)
    assert "semantic_recall" in facts[0]["relevance"]["reasons"]
    assert output.canonical_context["retrieval_policy"]["semantic_recall"] == {
        "sources": ["alias_records", "memory_pages", "semantic_embedding_index"],
        "mode": "rrf_keyword_embedding_hybrid",
        "embedding": {
            "provider": "local_deterministic",
            "model": "local-semantic-hash-v1",
            "matches": 1,
        },
    }


def test_context_pack_style_memory_uses_scene_sliding_window_instead_of_latest_tail(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, _seed_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Harbor",
        start_offset=0,
        end_offset=360,
        summary=None,
    )
    first_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="unknown",
        pov_confidence=0.0,
        pov_evidence_span_ids=[],
        pov_uncertainty_reason=None,
        story_time=None,
        emotional_tone=None,
        scene_summary=None,
        scene_function=None,
        start_offset=0,
        end_offset=120,
    )
    middle_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=1,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="unknown",
        pov_confidence=0.0,
        pov_evidence_span_ids=[],
        pov_uncertainty_reason=None,
        story_time=None,
        emotional_tone=None,
        scene_summary=None,
        scene_function=None,
        start_offset=120,
        end_offset=240,
    )
    last_scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=2,
        location_entity_id=None,
        pov_character_id=None,
        pov_mode="unknown",
        pov_confidence=0.0,
        pov_evidence_span_ids=[],
        pov_uncertainty_reason=None,
        story_time=None,
        emotional_tone=None,
        scene_summary=None,
        scene_function=None,
        start_offset=240,
        end_offset=360,
    )
    first_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=first_scene.id,
        start_offset=0,
        end_offset=60,
        raw_start_offset=0,
        raw_end_offset=60,
        text_preview="The quay stays quiet before the confrontation.",
        narration_layer="narrator",
    )
    middle_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=middle_scene.id,
        start_offset=120,
        end_offset=180,
        raw_start_offset=120,
        raw_end_offset=180,
        text_preview="Mira hides the ledger while the corridor keeps narrowing.",
        narration_layer="narrator",
    )
    later_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=last_scene.id,
        start_offset=240,
        end_offset=300,
        raw_start_offset=240,
        raw_end_offset=300,
        text_preview="A separate clash breaks out after the ledger scene ends.",
        narration_layer="narrator",
    )
    latest_tail_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        chapter_id=chapter.id,
        scene_id=last_scene.id,
        start_offset=300,
        end_offset=340,
        raw_start_offset=300,
        raw_end_offset=340,
        text_preview="The final tail beat no longer belongs to Mira's hiding scene.",
        narration_layer="narrator",
    )
    session.add_all(
        [
            chapter,
            first_scene,
            middle_scene,
            last_scene,
            first_span,
            middle_span,
            later_span,
            latest_tail_span,
        ]
    )
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-sliding-window",
            idempotency_key="idem-context-pack-sliding-window",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=middle_scene.id,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira hides the ledger while the corridor keeps narrowing.",
        )
    )

    sample_ids = [sample["source_span_id"] for sample in output.style_memory["samples"]]
    assert str(middle_span.id) in sample_ids
    assert sample_ids[0] == str(middle_span.id)
    assert str(latest_tail_span.id) not in sample_ids


def test_refresh_semantic_index_worker_persists_memory_page_embeddings(
    session: Session,
) -> None:
    project, _actor_id, _raw_source, _version, span = seed_evidence(session)
    mira_id = uuid4()
    memory_page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={
            "type": "character",
            "id": str(mira_id),
            "label": "Mira",
            "canonical_entity_id": str(mira_id),
        },
        title="Mira dossier",
        current_canon={"role_note": "Secret informant must remain unnamed."},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="standard",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="refresh_semantic_index",
        status="queued",
        idempotency_key="refresh-semantic-index:mira",
        payload={"step": "refresh_semantic_index", "pipeline_version": "pipeline-v1"},
    )
    session.add_all([memory_page, job])
    session.commit()

    processed = DbWorker(
        session,
        {"refresh_semantic_index": SemanticIndexRefreshHandler(LocalEmbeddingProvider())},
    ).run_once(worker_id="semantic-worker")

    assert processed is True
    assert job.status == "succeeded"
    assert session.query(SemanticEmbeddingRecord).count() == 3
    embedding = session.query(SemanticEmbeddingRecord).filter_by(target_type="memory_page").one()
    assert embedding.target_type == "memory_page"
    assert embedding.target_id == memory_page.id
    assert embedding.target_ref["id"] == str(mira_id)
    assert embedding.evidence_refs == [{"type": "source_span", "id": str(span.id)}]
    source_span_embedding = (
        session.query(SemanticEmbeddingRecord).filter_by(target_type="source_span").one()
    )
    style_sample_embedding = (
        session.query(SemanticEmbeddingRecord).filter_by(target_type="style_sample").one()
    )
    assert source_span_embedding.target_id == span.id
    assert style_sample_embedding.target_id == span.id


def test_refresh_semantic_index_worker_batches_memory_pages_before_source_spans(
    session: Session,
) -> None:
    project, _actor_id, _raw_source, _version, span = seed_evidence(session)
    memory_pages = [
        MemoryPage(
            id=uuid4(),
            project_id=project.id,
            page_type="character",
            target_ref={
                "type": "character",
                "id": str(uuid4()),
                "label": f"Mira dossier {index}",
                "canonical_entity_id": str(uuid4()),
            },
            title=f"Mira dossier {index}",
            current_canon={"role_note": f"Secret informant note {index}."},
            appearance_log=[],
            event_log=[],
            relationships=[],
            open_threads=[],
            contradictions=[],
            source_refs=[{"type": "source_span", "id": str(span.id)}],
            canon_status="current",
            memory_depth="standard",
        )
        for index in range(3)
    ]
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="refresh_semantic_index",
        status="queued",
        idempotency_key="refresh-semantic-index:batched-memory-pages",
        payload={
            "step": "refresh_semantic_index",
            "pipeline_version": "pipeline-v1",
            "memory_page_batch_size": 1,
            "source_span_batch_size": 10,
        },
    )
    session.add_all([*memory_pages, job])
    session.commit()

    embedding_provider = CountingLocalEmbeddingProvider()
    worker = DbWorker(
        session,
        {"refresh_semantic_index": SemanticIndexRefreshHandler(embedding_provider)},
    )

    assert worker.run_once(worker_id="semantic-worker") is True

    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="memory_page").count() == 1
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="source_span").count() == 0
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="style_sample").count() == 0
    assert embedding_provider.batch_sizes == [1]
    embedded_memory_page = (
        session.query(SemanticEmbeddingRecord).filter_by(target_type="memory_page").one()
    )
    continuation = (
        session.query(JobRecord).filter_by(job_type="refresh_semantic_index", status="queued").one()
    )
    assert continuation.payload["trigger"] == "refresh_semantic_index_memory_page_backpressure"
    assert continuation.payload["memory_page_batch_size"] == 1
    assert continuation.payload["source_span_batch_size"] == 10
    assert continuation.payload["after_memory_page_id"] == str(embedded_memory_page.target_id)
    assert "skip_memory_pages" not in continuation.payload

    for _ in range(10):
        if not worker.run_once(worker_id="semantic-worker"):
            break

    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="memory_page").count() == 3
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="source_span").count() == 1
    assert session.query(SemanticEmbeddingRecord).filter_by(target_type="style_sample").count() == 1
    assert (
        session.query(JobRecord)
        .filter(JobRecord.status.in_(("queued", "failed_retryable", "running")))
        .count()
        == 0
    )


def test_refresh_semantic_index_worker_fails_terminal_on_invalid_memory_page_cursor(
    session: Session,
) -> None:
    project, _actor_id, _raw_source, _version, _span = seed_evidence(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="refresh_semantic_index",
        status="queued",
        idempotency_key="refresh-semantic-index:bad-memory-page-cursor",
        payload={
            "step": "refresh_semantic_index",
            "pipeline_version": "pipeline-v1",
            "memory_page_batch_size": 1,
            "after_memory_page_id": str(uuid4()),
        },
    )
    session.add(job)
    session.commit()

    processed = DbWorker(
        session,
        {"refresh_semantic_index": SemanticIndexRefreshHandler(LocalEmbeddingProvider())},
    ).run_once(worker_id="semantic-worker")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "after_memory_page_id does not belong to the project."
    assert session.query(SemanticEmbeddingRecord).count() == 0


def test_refresh_semantic_index_worker_batches_source_span_embeddings(
    session: Session,
) -> None:
    project, _actor_id, raw_source, version, first_span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    second_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=25,
        end_offset=58,
        raw_start_offset=25,
        raw_end_offset=58,
        text_preview="The observatory catalogued cloud signals.",
        narration_layer="narrator",
    )
    third_span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=version.id,
        view_id=view.id,
        start_offset=59,
        end_offset=92,
        raw_start_offset=59,
        raw_end_offset=92,
        text_preview="The harbor archive stored pressure logs.",
        narration_layer="narrator",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="refresh_semantic_index",
        status="queued",
        idempotency_key="refresh-semantic-index:batched-spans",
        payload={
            "step": "refresh_semantic_index",
            "pipeline_version": "pipeline-v1",
            "source_span_batch_size": 1,
        },
    )
    session.add_all([second_span, third_span, job])
    session.commit()

    embedding_provider = CountingLocalEmbeddingProvider()
    worker = DbWorker(
        session,
        {"refresh_semantic_index": SemanticIndexRefreshHandler(embedding_provider)},
    )

    assert worker.run_once(worker_id="semantic-worker") is True

    assert session.query(SemanticEmbeddingRecord).count() == 2
    assert embedding_provider.batch_sizes == [1, 1]
    continuation = (
        session.query(JobRecord).filter_by(job_type="refresh_semantic_index", status="queued").one()
    )
    assert continuation.payload["trigger"] == "refresh_semantic_index_backpressure"
    assert continuation.payload["source_span_batch_size"] == 1
    assert continuation.payload["after_source_span_id"] == str(first_span.id)
    assert continuation.payload["skip_memory_pages"] is True

    for _ in range(10):
        if not worker.run_once(worker_id="semantic-worker"):
            break

    assert session.query(SemanticEmbeddingRecord).count() == 6
    assert (
        session.query(JobRecord)
        .filter(JobRecord.status.in_(("queued", "failed_retryable", "running")))
        .count()
        == 0
    )


def test_refresh_semantic_index_worker_fails_terminal_on_invalid_source_span_cursor(
    session: Session,
) -> None:
    project, _actor_id, _raw_source, _version, _span = seed_evidence(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="refresh_semantic_index",
        status="queued",
        idempotency_key="refresh-semantic-index:bad-cursor",
        payload={
            "step": "refresh_semantic_index",
            "pipeline_version": "pipeline-v1",
            "source_span_batch_size": 1,
            "after_source_span_id": str(uuid4()),
            "skip_memory_pages": True,
        },
    )
    session.add(job)
    session.commit()

    processed = DbWorker(
        session,
        {"refresh_semantic_index": SemanticIndexRefreshHandler(LocalEmbeddingProvider())},
    ).run_once(worker_id="semantic-worker")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "after_source_span_id does not belong to the project."
    assert session.query(SemanticEmbeddingRecord).count() == 0


def test_context_pack_token_budget_keeps_relevant_and_risk_context(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Mira",
        start_offset=0,
        end_offset=24,
        summary=None,
    )
    scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=None,
        pov_character_id=mira.id,
        pov_mode="third_limited",
        start_offset=0,
        end_offset=24,
    )
    span.chapter_id = chapter.id
    span.scene_id = scene.id
    relevant_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": str(mira.id), "label": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "label": "lantern map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    background_facts = [
        FactAssertionRecord(
            id=uuid4(),
            project_id=project.id,
            subject_ref={
                "type": "location",
                "id": f"background-{index}",
                "label": f"Tower {index}",
            },
            predicate="located_in",
            object_ref={"type": "location", "id": "old-city", "label": "Old City"},
            fact_status="canon",
            evidence_span_ids=[str(span.id)],
            confidence=0.8,
            source_scope="user_draft",
            promotion_decision_id=uuid4(),
        )
        for index in range(6)
    ]
    risk_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "kestrel", "label": "Kestrel"},
        predicate="knows",
        object_ref={"type": "secret", "id": "lantern-map-route", "label": "map route"},
        fact_status="disputed",
        evidence_span_ids=[str(span.id)],
        confidence=0.6,
        source_scope="user_draft",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="knowledge_conflict",
        severity="high",
        status="open",
        summary="Do not reveal Kestrel knows the lantern-map route.",
        affected_refs={"fact_ids": [str(risk_fact.id)]},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([mira, chapter, scene, relevant_fact, risk_fact, review, *background_facts])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-budget",
            idempotency_key="idem-context-pack-budget",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=scene.id,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Continue with Mira protecting the lantern map.",
            constraints={"context_budget": {"max_estimated_tokens": 620}},
        )
    )

    canonical_ids = {fact["fact_id"] for fact in output.canonical_context["facts"]}
    assert str(relevant_fact.id) in canonical_ids
    assert canonical_ids.isdisjoint({str(fact.id) for fact in background_facts})
    assert output.risk_context["facts"][0]["fact_id"] == str(risk_fact.id)
    assert output.risk_context["review_items"][0]["review_item_id"] == str(review.id)
    assert output.canonical_context["retrieval_policy"]["budget"] == {
        "max_estimated_tokens": 620,
        "estimated_tokens": output.canonical_context["retrieval_policy"]["budget"][
            "estimated_tokens"
        ],
        "truncated": True,
    }
    assert output.canonical_context["retrieval_policy"]["budget"]["estimated_tokens"] <= 620
    assert (
        output.risk_context["retrieval_policy"]["budget"]
        == output.canonical_context["retrieval_policy"]["budget"]
    )
    assert session.query(FactAssertionRecord).count() == 8
    assert session.query(ReviewItemRecord).count() == 1


def test_context_pack_uses_scene_metadata_and_pov_fallback(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    view = session.query(SourceProcessedView).one()
    mira = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="character",
        display_name="Mira",
        canonical_status="provisional",
        cast_tier="unknown",
        first_seen_scene_id=None,
        description=None,
    )
    harbor = StoryCanonicalEntity(
        id=uuid4(),
        project_id=project.id,
        entity_type="location",
        display_name="Harbor Nine",
        canonical_status="provisional",
        cast_tier=None,
        first_seen_scene_id=None,
        description=None,
    )
    chapter = StoryChapter(
        id=uuid4(),
        view_id=view.id,
        chapter_index=0,
        title="Mira",
        start_offset=0,
        end_offset=24,
        summary=None,
    )
    scene = StoryScene(
        id=uuid4(),
        chapter_id=chapter.id,
        scene_index=0,
        location_entity_id=harbor.id,
        pov_character_id=mira.id,
        pov_mode="first_person",
        pov_confidence=0.91,
        pov_evidence_span_ids=[str(span.id)],
        pov_uncertainty_reason=None,
        story_time="Dusk",
        emotional_tone="tense",
        scene_summary=None,
        scene_function="reveal",
        start_offset=0,
        end_offset=24,
    )
    hidden_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "orrin", "name": "Orrin"},
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor_code"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.9,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    appears_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={
            "type": "character",
            "id": str(mira.id),
            "label": "Mira",
            "canonical_entity_id": str(mira.id),
        },
        predicate="appears_in",
        object_ref={"type": "scene", "id": str(scene.id), "label": "Scene 1"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=1.0,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    session.add_all([mira, harbor, chapter, scene, hidden_fact, appears_fact])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-scene",
            idempotency_key="idem-context-pack-scene",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=scene.id,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="我把地图塞进袖口。",
        )
    )

    assert output.current_position["scene"] == {
        "scene_id": str(scene.id),
        "location_entity_id": str(harbor.id),
        "pov_character_id": str(mira.id),
        "pov_mode": "first_person",
        "pov_confidence": 0.91,
        "pov_evidence_span_ids": [str(span.id)],
        "pov_uncertainty_reason": None,
        "story_time": "Dusk",
        "emotional_tone": "tense",
        "scene_function": "reveal",
    }
    assert output.current_position["chapter"] == {
        "chapter_id": str(chapter.id),
        "chapter_index": 0,
        "title": "Mira",
    }
    assert output.pov_constraint["pov_character_id"] == str(mira.id)
    assert output.pov_constraint["pov_mode"] == "first_person"
    assert output.pov_constraint["pov_confidence"] == 0.91
    assert output.pov_constraint["pov_evidence_span_ids"] == [str(span.id)]
    assert output.pov_constraint["pov_uncertainty_reason"] is None
    assert output.pov_constraint["sensory_limits"] == {
        "scope": "current_scene",
        "scene_id": str(scene.id),
        "location_entity_id": str(harbor.id),
    }
    assert output.pov_constraint["inner_access"] == {
        "allowed_character_ids": [str(mira.id)],
        "non_pov_inner_state": "forbidden",
    }
    assert output.pov_constraint["forbidden_knowledge"][0]["fact_id"] == str(hidden_fact.id)
    assert output.active_characters == [appears_fact.subject_ref]
    context_pack = session.query(AgentContextPackRecord).one()
    assert context_pack.current_pov_character_id == mira.id


def test_context_pack_build_consumes_matching_pending_readiness(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    readiness = ContextPackReadinessRecord(
        id=uuid4(),
        project_id=project.id,
        source_span_id=span.id,
        source_delta_id=None,
        status="pending",
        reason="memory_dependency_changed",
        affected_refs=[{"type": "fact_assertion", "id": str(fact.id)}],
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    session.add_all([fact, readiness])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-readiness-consume",
            idempotency_key="idem-context-readiness-consume",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="米拉把地图收进袖中。",
        )
    )

    session.refresh(readiness)
    assert readiness.status == "consumed"
    assert session.query(ContextPackReadinessRecord).count() == 1
    audit = session.query(AuditEvent).filter_by(event_type="context_pack.readiness_consumed").one()
    assert audit.subject_ref == {"type": "agent_context_pack", "id": str(output.context_pack_id)}
    assert audit.decision["readiness_ids"] == [str(readiness.id)]
    assert audit.decision["source_span_ids"] == [str(span.id)]


def test_build_context_pack_job_handler_uses_real_use_case(session: Session) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.93,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="build_context_pack",
        status="queued",
        idempotency_key="context-pack-job:one",
        payload={
            "step": "build_context_pack",
            "pipeline_version": "pipeline-v1",
            "actor_id": str(actor_id),
            "request_id": "req-context-pack-job",
            "idempotency_key": "idem-context-pack-job",
            "action_request_id": None,
            "current_source_id": str(raw_source.id),
            "current_version_id": str(version.id),
            "current_scene_id": None,
            "current_pov_character_id": None,
            "mode": "draft_next_passage",
            "current_text_window": "米拉把地图收进袖中。",
        },
    )
    session.add_all([fact, job])
    session.commit()

    worker = DbWorker(session, {"build_context_pack": BuildContextPackHandler()})
    processed = worker.run_once(worker_id="worker-context")

    context_pack = session.query(AgentContextPackRecord).one()
    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert context_pack.current_source_id == raw_source.id
    assert context_pack.payload["canonical_context"]["facts"][0]["fact_id"] == str(fact.id)
    assert session.query(IdempotencyRecord).filter_by(operation="context_pack.build").count() == 1
    audits = {audit.event_type for audit in session.query(AuditEvent).all()}
    assert {"context_pack.built", "job.succeeded"}.issubset(audits)


def test_context_pack_includes_events_object_state_and_style_samples(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    event = StoryCanonicalEvent(
        id=uuid4(),
        project_id=project.id,
        event_type="object_transfer",
        title="Mira takes the Lantern Map",
        event_status="canon",
        primary_scene_id=None,
        event_candidate_ids=[],
        participants=[{"type": "character", "id": "mira"}],
        objects=[{"type": "object", "id": "lantern-map"}],
        location_entity_id=None,
        story_time="chapter-3",
        summary="Mira takes the Lantern Map from the quay.",
        consequence_summary="Mira carries the map into the archive.",
        evidence_span_ids=[str(span.id)],
    )
    run = GraphProjectionRun(
        id=uuid4(),
        project_id=project.id,
        projection_scope="project",
        source_state_hash="state-hash",
        created_edge_count=1,
    )
    edge = GraphProjectionEdge(
        id=uuid4(),
        project_id=project.id,
        run_id=run.id,
        source_ref={"type": "fact_assertion", "id": str(uuid4())},
        subject_ref={"type": "character", "id": "mira"},
        relation="owns",
        target_ref={"type": "object", "id": "lantern-map"},
        edge_status="canon",
        evidence_refs=[{"type": "source_span", "id": str(span.id)}],
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "name": "Mira"},
        title="Mira",
        current_canon={"facts": [{"fact_id": str(fact.id), "predicate": "owns"}]},
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[{"id": "map-thread", "summary": "Mira needs to keep the map hidden."}],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    review = ReviewItemRecord(
        id=uuid4(),
        project_id=project.id,
        review_type="continuity_warning",
        severity="medium",
        status="open",
        summary="Do not confirm Kestrel stole the map yet.",
        affected_refs={"character_id": "mira"},
        new_evidence={"source_span_ids": [str(span.id)]},
        existing_evidence={},
        suggested_actions=[],
        default_action="ask_author",
    )
    session.add_all([fact, event, run, edge, page, review])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-rich",
            idempotency_key="idem-context-pack-rich",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="米拉把地图塞进袖口。",
        )
    )

    assert output.recent_events == [
        {
            "event_id": str(event.id),
            "event_type": "object_transfer",
            "title": "Mira takes the Lantern Map",
            "event_status": "canon",
            "story_time": "chapter-3",
            "summary": "Mira takes the Lantern Map from the quay.",
            "consequence_summary": "Mira carries the map into the archive.",
            "participants": [{"type": "character", "id": "mira"}],
            "objects": [{"type": "object", "id": "lantern-map"}],
            "evidence_span_ids": [str(span.id)],
            "relevance": {
                "score": 65,
                "reasons": [
                    "current_source_evidence",
                    "current_version_evidence",
                    "active_character",
                ],
            },
        }
    ]
    assert output.object_location_state == [
        {
            "edge_id": str(edge.id),
            "relation": "owns",
            "subject_ref": {"type": "character", "id": "mira"},
            "target_ref": {"type": "object", "id": "lantern-map"},
            "edge_status": "canon",
            "evidence_refs": [{"type": "source_span", "id": str(span.id)}],
            "relevance": {
                "score": 65,
                "reasons": [
                    "current_source_evidence",
                    "current_version_evidence",
                    "active_character",
                ],
            },
        }
    ]
    assert output.style_memory == {
        "samples": [
            {
                "source_span_id": str(span.id),
                "text_preview": "Mira took the lantern map.",
                "narration_layer": "narrator",
                "relevance": {
                    "score": 25,
                    "reasons": ["current_source_evidence", "current_version_evidence"],
                },
            }
        ],
        "retrieval_policy": {
            "version": "context-relevance-v1",
            "sort": "score_desc_then_recency",
            "sections": [
                "canonical_context",
                "risk_context",
                "recent_events",
                "object_location_state",
                "style_memory",
            ],
        },
    }
    assert output.character_agency_state == {
        "status": "computed",
        "source": "memory",
        "characters": [
            {
                "character_ref": {"type": "character", "id": "mira", "name": "Mira"},
                "canon_facts": [
                    {
                        "fact_id": str(fact.id),
                        "predicate": "owns",
                        "object_ref": {
                            "type": "object",
                            "id": "lantern-map",
                            "name": "Lantern Map",
                        },
                        "evidence_span_ids": [str(span.id)],
                    }
                ],
                "recent_event_pressures": [
                    {
                        "event_id": str(event.id),
                        "summary": "Mira takes the Lantern Map from the quay.",
                        "consequence_summary": "Mira carries the map into the archive.",
                    }
                ],
                "object_state": [
                    {
                        "relation": "owns",
                        "target_ref": {"type": "object", "id": "lantern-map"},
                        "edge_status": "canon",
                    }
                ],
                "knowledge_state": [],
                "open_threads": [
                    {
                        "id": "map-thread",
                        "summary": "Mira needs to keep the map hidden.",
                        "source_span_ids": [str(span.id)],
                    }
                ],
                "risk_notes": [
                    {
                        "review_item_id": str(review.id),
                        "review_type": "continuity_warning",
                        "summary": "Do not confirm Kestrel stole the map yet.",
                    }
                ],
                "natural_next_action": "依据已确认事实行动，同时保留开放风险",
            }
        ],
    }
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs


def test_context_pack_agency_state_includes_active_character_knowledge_state(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    mira_id = uuid4()
    knowledge_fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": str(mira_id), "name": "Mira"},
        predicate="knows",
        object_ref={"type": "secret", "id": "harbor-code", "label": "Harbor Code"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.91,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    knowledge = CharacterKnowledge(
        id=uuid4(),
        project_id=project.id,
        character_id=mira_id,
        knows_ref={"type": "fact_assertion", "id": str(knowledge_fact.id)},
        evidence_span_id=span.id,
        certainty="known",
        hidden_from=[],
        status="active",
    )
    session.add_all([knowledge_fact, knowledge])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-agency-knowledge",
            idempotency_key="idem-context-pack-agency-knowledge",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="米拉握紧灯图，没有把暗号告诉任何人。",
        )
    )

    assert output.character_knowledge == []
    assert output.character_agency_state["characters"][0]["knowledge_state"] == [
        {
            "character_id": str(mira_id),
            "knows_ref": knowledge.knows_ref,
            "learned_in_scene_id": None,
            "evidence_span_id": str(span.id),
            "certainty": "known",
            "hidden_from": [],
            "status": "active",
        }
    ]
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_context_pack_agency_state_reads_source_backed_memory_page_profile(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "name": "Mira"},
        title="Mira",
        current_canon={
            "facts": [{"fact_id": str(fact.id), "predicate": "owns"}],
            "agency_profile": {
                "core_desire": {
                    "value": "证明自己不是被命运摆布的人。",
                    "source_span_ids": [str(span.id)],
                },
                "immediate_want": {
                    "value": "拿回灯图，同时不暴露她已经怀疑 Kestrel。",
                    "source_span_ids": [str(span.id)],
                },
                "fear_or_wound": {
                    "value": "害怕自己其实依赖 Orrin。",
                    "source_span_ids": [str(span.id)],
                },
                "moral_boundary": {
                    "value": "不会牺牲无辜者换取线索。",
                    "source_span_ids": [str(span.id)],
                },
                "secret": {
                    "value": "隐藏她已经怀疑 Kestrel。",
                    "source_span_ids": [str(span.id)],
                },
                "relationship_stance": {
                    "value": "对 Kestrel 表面合作，实际开始怀疑。",
                    "target_ref": {"type": "character", "id": "kestrel", "name": "Kestrel"},
                    "source_span_ids": [str(span.id)],
                },
                "voice_fingerprint": {
                    "value": "短句多，情绪压在动作里。",
                    "source_span_ids": [str(span.id)],
                },
                "agency_rule": {
                    "value": "被逼问时先反击，再转移话题。",
                    "source_span_ids": [str(span.id)],
                },
                "change_pressure": {
                    "value": "灯图易主迫使她必须立刻选择是否信任同伴。",
                    "source_span_ids": [str(span.id)],
                },
            },
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all([fact, page])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-agency-profile",
            idempotency_key="idem-context-pack-agency-profile",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="米拉握紧灯图，没有说出她怀疑 Kestrel。",
        )
    )

    character_state = output.character_agency_state["characters"][0]
    assert character_state["core_desire"] == {
        "value": "证明自己不是被命运摆布的人。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["immediate_want"] == {
        "value": "拿回灯图，同时不暴露她已经怀疑 Kestrel。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["fear_or_wound"] == {
        "value": "害怕自己其实依赖 Orrin。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["moral_boundary"] == {
        "value": "不会牺牲无辜者换取线索。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["secret"] == {
        "value": "隐藏她已经怀疑 Kestrel。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["relationship_stance"] == [
        {
            "value": "对 Kestrel 表面合作，实际开始怀疑。",
            "target_ref": {"type": "character", "id": "kestrel", "name": "Kestrel"},
            "source_span_ids": [str(span.id)],
        }
    ]
    assert character_state["voice_fingerprint"] == {
        "value": "短句多，情绪压在动作里。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["agency_rule"] == {
        "value": "被逼问时先反击，再转移话题。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["pressure"] == {
        "value": "灯图易主迫使她必须立刻选择是否信任同伴。",
        "source_span_ids": [str(span.id)],
    }
    assert character_state["agency_pass"] == {
        "natural_action": "依据已确认事实行动",
        "likely_dialogue_move": "被逼问时先反击，再转移话题。",
        "hidden_pressure": "灯图易主迫使她必须立刻选择是否信任同伴。",
        "forbidden_action": "不会牺牲无辜者换取线索。",
        "agency_rationale": "证明自己不是被命运摆布的人。",
        "conflict_opportunity": "对 Kestrel 表面合作，实际开始怀疑。",
        "source_span_ids": [str(span.id)],
    }
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_context_pack_agency_profile_rejects_cross_project_field_evidence(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    cross_project_span = seed_cross_project_span(
        session,
        text_preview="Other story evidence must not support Mira.",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.92,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="character",
        target_ref={"type": "character", "id": "mira", "name": "Mira"},
        title="Mira",
        current_canon={
            "facts": [{"fact_id": str(fact.id), "predicate": "owns"}],
            "agency_profile": {
                "core_desire": {
                    "value": "This must not be accepted from another project.",
                    "source_span_ids": [str(cross_project_span.id)],
                },
                "immediate_want": {
                    "value": "Use the local source-backed field.",
                    "source_span_ids": [str(span.id)],
                },
            },
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="current",
        memory_depth="scene",
    )
    session.add_all([fact, page])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-agency-profile-cross-project",
            idempotency_key="idem-context-pack-agency-profile-cross-project",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="Mira checks the Lantern Map.",
        )
    )

    character_state = output.character_agency_state["characters"][0]
    assert "core_desire" not in character_state
    assert character_state["immediate_want"] == {
        "value": "Use the local source-backed field.",
        "source_span_ids": [str(span.id)],
    }
    assert session.query(FactAssertionRecord).count() == 1
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_context_pack_reads_memory_page_state_facts_without_graph_edge(
    session: Session,
) -> None:
    project, actor_id, raw_source, version, span = seed_evidence(session)
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira", "name": "Mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.94,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    page = MemoryPage(
        id=uuid4(),
        project_id=project.id,
        page_type="object",
        target_ref={"type": "object", "id": "lantern-map", "name": "Lantern Map"},
        title="Lantern Map",
        current_canon={
            "facts": [{"fact_id": str(fact.id), "predicate": "owns"}],
            "state_facts": [
                {
                    "fact_id": str(fact.id),
                    "predicate": "owns",
                    "state_type": "object_holder",
                    "subject_ref": {"type": "character", "id": "mira", "name": "Mira"},
                    "object_ref": {
                        "type": "object",
                        "id": "lantern-map",
                        "name": "Lantern Map",
                    },
                    "counterparty_ref": {
                        "type": "character",
                        "id": "mira",
                        "name": "Mira",
                    },
                    "evidence_span_ids": [str(span.id)],
                }
            ],
        },
        appearance_log=[],
        event_log=[],
        relationships=[],
        open_threads=[],
        contradictions=[],
        source_refs=[{"type": "source_span", "id": str(span.id)}],
        canon_status="rebuilt",
        memory_depth="standard",
    )
    session.add_all([fact, page])
    session.commit()

    output = BuildWritingContextPack(uow_factory(session)).execute(
        BuildWritingContextPackInput(
            project_id=project.id,
            actor_id=actor_id,
            request_id="req-context-pack-memory-page-state",
            idempotency_key="idem-context-pack-memory-page-state",
            action_request_id=None,
            current_source_id=raw_source.id,
            current_version_id=version.id,
            current_scene_id=None,
            current_pov_character_id=None,
            mode="draft_next_passage",
            current_text_window="米拉检查灯笼地图。",
        )
    )

    assert session.query(GraphProjectionEdge).count() == 0
    assert output.object_location_state == [
        {
            "edge_id": f"memory_page_state:{page.id}:{fact.id}:object_holder",
            "source": "memory_page_state",
            "memory_page_id": str(page.id),
            "fact_id": str(fact.id),
            "state_type": "object_holder",
            "relation": "owns",
            "subject_ref": {"type": "character", "id": "mira", "name": "Mira"},
            "target_ref": {"type": "object", "id": "lantern-map", "name": "Lantern Map"},
            "edge_status": "canon",
            "evidence_refs": [{"type": "source_span", "id": str(span.id)}],
            "relevance": {
                "score": 65,
                "reasons": [
                    "current_source_evidence",
                    "current_version_evidence",
                    "active_character",
                ],
            },
        }
    ]
    assert {"type": "source_span", "id": str(span.id)} in output.evidence_refs
