from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sextant.infra.db.models import JOB_TYPES, Base, JobRecord, Project
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.worker_handlers import build_worker_handlers
from sextant.infra.worker_health import worker_health_report
from sextant.skills.local_embedding import LocalEmbeddingProvider
from sextant.skills.local_event_aggregation import LocalEventAggregationProvider
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider
from sextant.skills.local_pov_detection import LocalPovDetectionProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _ConfiguredProvider:
    skill_name = "configured"
    skill_version = "configured.v1"
    model_name = "configured"
    provider_name = "configured"
    dimensions = 3


def test_worker_loop_registers_every_documented_job_type(tmp_path: Path) -> None:
    handlers = build_worker_handlers(
        LocalObjectStore(tmp_path / "objects"),
        LocalStoryDraftProvider(),
    )

    assert set(handlers) == set(JOB_TYPES)


def test_worker_handler_builder_rejects_implicit_local_defaults_in_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="pov_detection_provider"):
        build_worker_handlers(
            LocalObjectStore(tmp_path / "objects"),
            _ConfiguredProvider(),
        )


def test_worker_handler_builder_rejects_explicit_local_providers_in_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="story_draft_provider"):
        build_worker_handlers(
            LocalObjectStore(tmp_path / "objects"),
            LocalStoryDraftProvider(),
            LocalPovDetectionProvider(),
            event_aggregation_provider=LocalEventAggregationProvider(),
            memory_extraction_provider=LocalMemoryExtractionProvider(),
            embedding_provider=LocalEmbeddingProvider(),
        )


def test_worker_provider_extension_points_are_keyword_only() -> None:
    signature = inspect.signature(build_worker_handlers)

    assert signature.parameters["event_aggregation_provider"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["memory_extraction_provider"].kind is inspect.Parameter.KEYWORD_ONLY


def test_runtime_worker_scripts_wire_provider_ports_by_name() -> None:
    for script in (
        Path("backend/scripts/worker_loop.py"),
        Path("backend/scripts/worker_healthcheck.py"),
    ):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_worker_handlers"
        ]

        assert calls, f"{script} does not call build_worker_handlers"
        for call in calls:
            keyword_names = {keyword.arg for keyword in call.keywords}
            assert "event_aggregation_provider" in keyword_names
            assert "memory_extraction_provider" in keyword_names


def test_worker_health_report_checks_database_and_handler_coverage(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 6, 3, 12, tzinfo=UTC)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        project = Project(id=uuid4(), name="Harbor Nine")
        session.add(project)
        session.add(
            JobRecord(
                id=uuid4(),
                project_id=project.id,
                job_type="run_memory_writeback",
                status="running",
                idempotency_key="run-memory-writeback:healthcheck",
                payload={"step": "run_memory_writeback", "pipeline_version": "pipeline-v1"},
                locked_by="worker-old",
                locked_at=now - timedelta(minutes=10),
            )
        )
        session.commit()

        handlers = build_worker_handlers(
            LocalObjectStore(tmp_path / "objects"),
            LocalStoryDraftProvider(),
        )
        report = worker_health_report(session, handlers, now=lambda: now)
        missing_report = worker_health_report(session, {})

    assert report["status"] == "pass"
    assert report["database"] == "ok"
    assert report["missing_job_types"] == []
    assert report["extra_job_types"] == []
    assert set(report["registered_job_types"]) == set(JOB_TYPES)
    assert report["job_counts"]["running"] == 1
    assert report["stale_running_jobs"] == 1
    assert missing_report["status"] == "fail"
    assert missing_report["missing_job_types"] == sorted(JOB_TYPES)
