from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.contracts.memory_extraction import ExtractedFact, MemoryExtractionResult
from sextant.domain.story_schema import (
    BASE_RELATION_ROLE_RULES,
    BASE_RELATIONS,
    default_base_story_schema_pack,
)
from sextant.infra.db.models import (
    Base,
    EvidenceLogEntry,
    FactAssertionRecord,
    GraphProjectionEdge,
    JobRecord,
    MemoryPage,
    Project,
    ProjectStorySchemaBinding,
    RawSource,
    ReviewItemRecord,
    SkillRun,
    SourceDeltaRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StorySchemaPackRecord,
)
from sextant.infra.memory_extraction_openai import (
    OpenAIMemoryExtractionOutput,
    OpenAIMemoryExtractionProvider,
)
from sextant.infra.memory_extraction_provider import memory_extraction_provider_from_env
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.worker import DbWorker
from sextant.infra.worker_handlers import build_worker_handlers
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _FakeResponses:
    def __init__(
        self,
        parsed: OpenAIMemoryExtractionOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.parsed = parsed
        self.usage = usage
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed, usage=self.usage)


class _FakeOpenAIClient:
    def __init__(
        self,
        parsed: OpenAIMemoryExtractionOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.responses = _FakeResponses(parsed, usage)


class _CustomMemoryProvider:
    skill_name = "custom_memory_extraction"
    skill_version = "custom-memory-v1"
    prompt_version = "custom-prompt-v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref={"type": "character", "id": "mira"},
                    predicate="owns",
                    object_ref={"type": "object", "id": "lantern-map"},
                    risk_level="low",
                )
            ]
        )


class _InvalidRiskMemoryProvider:
    skill_name = "invalid_memory_extraction"
    skill_version = "invalid-memory-v1"
    prompt_version = "invalid-prompt-v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref={"type": "character", "id": "mira"},
                    predicate="owns",
                    object_ref={"type": "object", "id": "lantern-map"},
                    risk_level="certain",
                )
            ]
        )


class _InvalidPredicateMemoryProvider:
    skill_name = "invalid_predicate_memory_extraction"
    skill_version = "invalid-predicate-memory-v1"
    prompt_version = "invalid-predicate-prompt-v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref={"type": "character", "id": "mira"},
                    predicate="participates_in",
                    object_ref={"type": "event", "id": "map-theft"},
                    risk_level="low",
                )
            ]
        )


class _InvalidCustomRelationRoleMemoryProvider:
    skill_name = "invalid_custom_relation_memory_extraction"
    skill_version = "invalid-custom-relation-memory-v1"
    prompt_version = "invalid-custom-relation-prompt-v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref={"type": "character", "id": "mira"},
                    predicate="guards",
                    object_ref={"type": "event", "id": "map-theft"},
                    risk_level="low",
                )
            ]
        )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


def test_openai_memory_extraction_provider_parses_structured_response() -> None:
    parsed = OpenAIMemoryExtractionOutput(
        facts=[
            {
                "subject_ref": {"type": "character", "id": "mira", "label": "Mira"},
                "predicate": "owns",
                "object_ref": {"type": "object", "id": "lantern-map"},
                "risk_level": "low",
            }
        ],
        thread_updates=[
            {
                "target_ref": {"type": "character", "id": "mira"},
                "update_type": "opens",
                "thread_id": "map-origin",
                "description": "The lantern map origin remains unresolved.",
                "risk_level": "low",
            }
        ],
    )
    client = _FakeOpenAIClient(parsed)
    provider = OpenAIMemoryExtractionProvider(model="gpt-5", client=client)

    result = provider.extract("Mira takes the Lantern Map from the quay.")

    assert result.facts[0].subject_ref == {
        "type": "character",
        "id": "mira",
        "label": "Mira",
    }
    assert result.facts[0].predicate == "owns"
    assert result.facts[0].object_ref == {"type": "object", "id": "lantern-map"}
    assert result.facts[0].risk_level == "low"
    assert result.thread_updates[0].target_ref == {"type": "character", "id": "mira"}
    assert result.thread_updates[0].update_type == "opens"
    assert result.thread_updates[0].thread_id == "map-origin"
    assert result.thread_updates[0].description == "The lantern map origin remains unresolved."
    assert result.thread_updates[0].risk_level == "low"
    assert client.responses.kwargs["model"] == "gpt-5"
    assert client.responses.kwargs["text_format"] is OpenAIMemoryExtractionOutput
    messages = client.responses.kwargs["input"]
    assert isinstance(messages, list)
    assert "no authority to create canon" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["text"] == "Mira takes the Lantern Map from the quay."


def test_openai_memory_extraction_structured_schema_requires_type_id_refs() -> None:
    schema = OpenAIMemoryExtractionOutput.model_json_schema()
    thread_schema = schema["$defs"]["OpenAIMemoryThreadUpdate"]
    owns_schema = _schema_for_relation(schema, "owns")

    subject_ref_schema = _resolve_schema_ref(schema, owns_schema["properties"]["subject_ref"])
    object_ref_schema = _resolve_schema_ref(schema, owns_schema["properties"]["object_ref"])
    target_ref_schema = _resolve_schema_ref(schema, thread_schema["properties"]["target_ref"])

    for ref_schema in (subject_ref_schema, object_ref_schema, target_ref_schema):
        assert {"type", "id"}.issubset(set(ref_schema["required"]))
        type_schema = ref_schema["properties"]["type"]
        assert type_schema.get("minLength") == 1 or "enum" in type_schema or "const" in type_schema
        assert ref_schema["properties"]["id"]["minLength"] == 1


def test_openai_memory_extraction_structured_schema_limits_predicates_to_base_story_relations() -> (
    None
):
    schema = OpenAIMemoryExtractionOutput.model_json_schema()

    assert tuple(_fact_branch_relation_names(schema)) == BASE_RELATIONS


def test_openai_memory_extraction_structured_schema_limits_relation_roles() -> None:
    schema = OpenAIMemoryExtractionOutput.model_json_schema()
    owns_schema = _schema_for_relation(schema, "owns")
    subject_ref_schema = _resolve_schema_ref(schema, owns_schema["properties"]["subject_ref"])
    object_ref_schema = _resolve_schema_ref(schema, owns_schema["properties"]["object_ref"])

    assert tuple(owns_schema["properties"]["predicate"]["const"] for _ in [0]) == ("owns",)
    assert _schema_literal_values(subject_ref_schema["properties"]["type"]) == tuple(
        sorted(BASE_RELATION_ROLE_RULES["owns"][0])
    )
    assert _schema_literal_values(object_ref_schema["properties"]["type"]) == tuple(
        sorted(BASE_RELATION_ROLE_RULES["owns"][1])
    )

    with pytest.raises(ValueError):
        OpenAIMemoryExtractionOutput(
            facts=[
                {
                    "subject_ref": {"type": "character", "id": "mira"},
                    "predicate": "owns",
                    "object_ref": {"type": "event", "id": "map-theft"},
                    "risk_level": "low",
                }
            ]
        )


def test_openai_memory_extraction_provider_records_usage_and_cost_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = OpenAIMemoryExtractionOutput(
        facts=[
            {
                "subject_ref": {"type": "character", "id": "mira"},
                "predicate": "owns",
                "object_ref": {"type": "object", "id": "lantern-map"},
                "risk_level": "low",
            }
        ]
    )
    client = _FakeOpenAIClient(
        parsed,
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20),
    )
    metrics = MetricsRegistry()
    monkeypatch.setenv("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS", "100")
    monkeypatch.setenv("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS", "500")
    provider = OpenAIMemoryExtractionProvider(model="gpt-5", client=client, metrics=metrics)

    provider.extract("Mira takes the Lantern Map from the quay.")

    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_memory_extraction",token_type="input"} 12'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_memory_extraction",token_type="output"} 8'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_memory_extraction",token_type="total"} 20'
    ) in rendered
    assert (
        'sextant_provider_cost_microusd_total{model="gpt-5",provider="openai",'
        'skill="openai_memory_extraction"} 5.2'
    ) in rendered
    assert "Lantern Map" not in rendered


def _resolve_schema_ref(schema: dict[str, object], node: dict[str, object]) -> dict[str, object]:
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    prefix = "#/$defs/"
    assert ref.startswith(prefix)
    resolved = schema["$defs"][ref.removeprefix(prefix)]
    assert isinstance(resolved, dict)
    return resolved


def _schema_for_relation(schema: dict[str, object], relation: str) -> dict[str, object]:
    facts_schema = schema["properties"]["facts"]
    assert isinstance(facts_schema, dict)
    item_schema = facts_schema["items"]
    assert isinstance(item_schema, dict)
    branches = item_schema["oneOf"]
    assert isinstance(branches, list)
    for branch_ref in branches:
        assert isinstance(branch_ref, dict)
        branch_schema = _resolve_schema_ref(schema, branch_ref)
        predicate_schema = branch_schema["properties"]["predicate"]
        assert isinstance(predicate_schema, dict)
        if predicate_schema.get("const") == relation:
            return branch_schema
    raise AssertionError(f"missing schema branch for relation {relation}")


def _fact_branch_relation_names(schema: dict[str, object]) -> list[str]:
    facts_schema = schema["properties"]["facts"]
    assert isinstance(facts_schema, dict)
    item_schema = facts_schema["items"]
    assert isinstance(item_schema, dict)
    branches = item_schema["oneOf"]
    assert isinstance(branches, list)
    names: list[str] = []
    for branch_ref in branches:
        assert isinstance(branch_ref, dict)
        branch_schema = _resolve_schema_ref(schema, branch_ref)
        predicate_schema = branch_schema["properties"]["predicate"]
        assert isinstance(predicate_schema, dict)
        const = predicate_schema.get("const")
        assert isinstance(const, str)
        names.append(const)
    return names


def _schema_literal_values(node: object) -> tuple[str, ...]:
    assert isinstance(node, dict)
    if "enum" in node:
        enum = node["enum"]
        assert isinstance(enum, list)
        return tuple(str(value) for value in enum)
    const = node.get("const")
    assert isinstance(const, str)
    return (const,)


def test_memory_extraction_provider_factory_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEXTANT_MEMORY_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_PROVIDER", raising=False)

    provider = memory_extraction_provider_from_env()

    assert isinstance(provider, LocalMemoryExtractionProvider)


def test_memory_extraction_provider_factory_rejects_local_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_PROVIDER", "local")

    with pytest.raises(RuntimeError, match="SEXTANT_MEMORY_LLM_PROVIDER"):
        memory_extraction_provider_from_env()


def test_memory_extraction_provider_factory_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_MODEL", "gpt-5")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OpenAI memory extraction provider requires"):
        memory_extraction_provider_from_env()


def test_memory_extraction_provider_factory_reports_secret_ref_materialization_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_MODEL", "gpt-5")
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "secret://prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_LLM_API_KEY_SECRET_REF"):
        memory_extraction_provider_from_env()


def test_memory_extraction_provider_factory_requires_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SEXTANT_MEMORY_LLM_MODEL", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_MEMORY_LLM_MODEL"):
        memory_extraction_provider_from_env()


def test_worker_handlers_use_configured_memory_extraction_provider(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = _seed_writeback_job(
        session,
        object_store,
        text="Mira takes the Lantern Map from the quay.",
    )

    processed = DbWorker(
        session,
        build_worker_handlers(
            object_store,
            LocalStoryDraftProvider(),
            memory_extraction_provider=_CustomMemoryProvider(),
        ),
    ).run_once(worker_id="worker-memory-provider")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_completed"
    assert session.query(SkillRun).one().skill_name == "custom_memory_extraction"
    assert session.query(FactAssertionRecord).one().fact_status == "canon"
    assert session.query(GraphProjectionEdge).filter_by(relation="owns").count() == 1


def test_memory_writeback_rejects_invalid_provider_output_without_fact_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = _seed_writeback_job(
        session,
        object_store,
        text="Mira takes the Lantern Map from the quay.",
    )

    processed = DbWorker(
        session,
        build_worker_handlers(
            object_store,
            LocalStoryDraftProvider(),
            memory_extraction_provider=_InvalidRiskMemoryProvider(),
        ),
    ).run_once(worker_id="worker-invalid-memory-provider")

    refreshed_job = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed_job.status == "failed_terminal"
    assert refreshed_job.last_error == (
        "llm_output_invalid: Memory extraction provider returned invalid fact risk_level."
    )
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_queued"
    failed_skill_run = session.query(SkillRun).one()
    assert failed_skill_run.skill_name == "invalid_memory_extraction"
    assert failed_skill_run.status == "failed_terminal"
    assert failed_skill_run.validation_result == {
        "status": "invalid",
        "error_code": "llm_output_invalid",
        "message": "Memory extraction provider returned invalid fact risk_level.",
    }
    assert session.query(SourceProcessedView).count() == 0
    assert session.query(SourceSpan).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(EvidenceLogEntry).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_writeback_rejects_schema_invalid_provider_fact_without_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = _seed_writeback_job(
        session,
        object_store,
        text="Mira joins the map theft.",
    )

    processed = DbWorker(
        session,
        build_worker_handlers(
            object_store,
            LocalStoryDraftProvider(),
            memory_extraction_provider=_InvalidPredicateMemoryProvider(),
        ),
    ).run_once(worker_id="worker-invalid-memory-schema")

    refreshed_job = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed_job.status == "failed_terminal"
    assert refreshed_job.last_error == (
        "llm_output_invalid: Memory extraction provider returned schema-invalid fact: "
        "schema_relation_not_allowed."
    )
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_queued"
    failed_skill_run = session.query(SkillRun).one()
    assert failed_skill_run.skill_name == "invalid_predicate_memory_extraction"
    assert failed_skill_run.status == "failed_terminal"
    assert failed_skill_run.validation_result == {
        "status": "invalid",
        "error_code": "llm_output_invalid",
        "message": (
            "Memory extraction provider returned schema-invalid fact: schema_relation_not_allowed."
        ),
    }
    assert session.query(SourceProcessedView).count() == 0
    assert session.query(SourceSpan).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(EvidenceLogEntry).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def test_memory_writeback_rejects_custom_relation_role_mismatch_without_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    delta, job = _seed_writeback_job(
        session,
        object_store,
        text="Mira guards the map theft.",
    )
    _bind_custom_relation_schema(session, delta.project_id)

    processed = DbWorker(
        session,
        build_worker_handlers(
            object_store,
            LocalStoryDraftProvider(),
            memory_extraction_provider=_InvalidCustomRelationRoleMemoryProvider(),
        ),
    ).run_once(worker_id="worker-invalid-custom-relation-schema")

    refreshed_job = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed_job.status == "failed_terminal"
    assert refreshed_job.last_error == (
        "llm_output_invalid: Memory extraction provider returned schema-invalid fact: "
        "schema_relation_role_not_allowed."
    )
    assert session.get(SourceDeltaRecord, delta.id).status == "memory_writeback_queued"
    failed_skill_run = session.query(SkillRun).one()
    assert failed_skill_run.skill_name == "invalid_custom_relation_memory_extraction"
    assert failed_skill_run.status == "failed_terminal"
    assert failed_skill_run.validation_result == {
        "status": "invalid",
        "error_code": "llm_output_invalid",
        "message": (
            "Memory extraction provider returned schema-invalid fact: "
            "schema_relation_role_not_allowed."
        ),
    }
    assert session.query(SourceProcessedView).count() == 0
    assert session.query(SourceSpan).count() == 0
    assert session.query(FactAssertionRecord).count() == 0
    assert session.query(EvidenceLogEntry).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(MemoryPage).count() == 0
    assert session.query(GraphProjectionEdge).count() == 0


def _seed_writeback_job(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
) -> tuple[SourceDeltaRecord, JobRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_text_ref = object_store.put_text("raw/memory-provider.txt", text)
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
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
    delta = SourceDeltaRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        previous_version_id=version.id,
        delta_kind="replace",
        range_start=0,
        range_end=len(text),
        base_hash=version.raw_hash,
        submitted_text_ref=object_store.put_text("accepted/memory-provider-delta.txt", text),
        source_type="draft_manuscript",
        source_scope="user_draft",
        provenance={"author_edited": True},
        status="memory_writeback_queued",
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_memory_writeback",
        status="queued",
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


def _bind_custom_relation_schema(session: Session, project_id: UUID) -> None:
    base_snapshot = default_base_story_schema_pack()
    base_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=None,
        pack_type="base",
        pack_name=base_snapshot.pack_name,
        version=f"{base_snapshot.version}-memory-provider-test",
        status="active",
        entity_types=base_snapshot.entity_types,
        event_types=base_snapshot.event_types,
        relations=base_snapshot.relations,
        extraction_hints={},
        risk_rules={},
    )
    override_pack = StorySchemaPackRecord(
        id=uuid4(),
        project_id=project_id,
        pack_type="project_override",
        pack_name="harbor-nine-custom-relations",
        version="harbor-nine-custom-relations.v1",
        status="active",
        entity_types=[],
        event_types=[],
        relations=[
            {
                "name": "guards",
                "subject_types": ["character", "faction"],
                "object_types": ["location", "object"],
            }
        ],
        extraction_hints={},
        risk_rules={},
    )
    binding = ProjectStorySchemaBinding(
        id=uuid4(),
        project_id=project_id,
        base_schema_pack_id=base_pack.id,
        genre_schema_pack_id=None,
        project_override_pack_id=override_pack.id,
        status="active",
        created_by=None,
    )
    session.add_all([base_pack, override_pack, binding])
    session.commit()
