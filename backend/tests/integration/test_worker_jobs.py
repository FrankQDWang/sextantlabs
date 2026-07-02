from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.infra.db.models import (
    AuditEvent,
    Base,
    FactAssertionRecord,
    GraphProjectionEdge,
    JobRecord,
    Project,
    RawSource,
    SkillRun,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
)
from sextant.infra.graph_projection import GraphProjectionRebuildHandler
from sextant.infra.skill_replay_eval import SkillReplayEvalHandler
from sextant.infra.worker import (
    DbWorker,
    ProviderRetryableJobError,
    RetryableJobError,
    TerminalJobError,
    release_timed_out_jobs,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def seed_project(session: Session) -> Project:
    project = Project(id=uuid4(), name="Harbor Nine")
    session.add(project)
    session.commit()
    return project


def seed_job(session: Session, project: Project, job_type: str) -> JobRecord:
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type=job_type,
        status="queued",
        idempotency_key=f"{job_type}:one",
        payload={"step": job_type, "pipeline_version": "pipeline-v1"},
    )
    session.add(job)
    session.commit()
    return job


def seed_skill_run(
    session: Session,
    project: Project,
    *,
    structured_output: dict[str, object],
    validation_result: dict[str, object] | None = None,
) -> SkillRun:
    skill_run = SkillRun(
        id=uuid4(),
        project_id=project.id,
        skill_name="next-page-agent",
        skill_version="1",
        input_schema_version="story-draft-request.v1",
        output_schema_version="story-draft-result.v1",
        prompt_version="1",
        input_hash="input-hash-1",
        structured_output=structured_output,
        validation_result=validation_result or {"status": "valid"},
        status="succeeded",
    )
    session.add(skill_run)
    session.commit()
    return skill_run


def test_release_timed_out_running_job_for_retry(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "run_memory_writeback")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)
    job.status = "running"
    job.locked_by = "worker-old"
    job.locked_at = now - timedelta(minutes=20)
    session.commit()

    released = release_timed_out_jobs(
        session,
        now=now,
        lease_timeout=timedelta(minutes=5),
    )

    assert released == 1
    refreshed = session.get(JobRecord, job.id)
    assert refreshed.status == "failed_retryable"
    assert refreshed.last_error == "lease_timeout"
    assert refreshed.run_after.replace(tzinfo=UTC) == now


def test_worker_marks_retryable_failure_with_bounded_backoff(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "run_agent_candidate")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        raise RetryableJobError("provider timeout")

    worker = DbWorker(session, {"run_agent_candidate": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_retryable"
    assert refreshed.attempt_count == 1
    assert refreshed.run_after.replace(tzinfo=UTC) == now + timedelta(seconds=30)
    assert refreshed.last_error == "provider timeout"


def test_worker_exhausts_provider_retry_budget_as_terminal(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "run_agent_candidate")
    job.attempt_count = 2
    session.commit()
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        raise ProviderRetryableJobError("provider quota window did not recover")

    worker = DbWorker(session, {"run_agent_candidate": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.attempt_count == 3
    assert refreshed.run_after is None
    assert refreshed.last_error == "provider quota window did not recover"
    audit = session.query(AuditEvent).filter_by(event_type="job.failed_terminal").one()
    assert audit.decision["failure_class"] == "provider"
    assert audit.decision["terminal_reason"] == "retry_budget_exhausted"
    assert audit.decision["max_attempts"] == 3


def test_worker_marks_terminal_failure_without_retry(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "derive_facts")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        raise TerminalJobError("schema validation failed")

    worker = DbWorker(session, {"derive_facts": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.run_after is None
    assert refreshed.last_error == "schema validation failed"
    assert session.query(AuditEvent).filter_by(event_type="job.failed_terminal").count() == 1


def test_worker_rejects_job_missing_pipeline_step_before_handler(session: Session) -> None:
    project = seed_project(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="extract_mentions",
        status="queued",
        idempotency_key="extract-mentions:missing-payload",
        payload={"source_delta_id": str(uuid4())},
    )
    session.add(job)
    session.commit()
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        raise AssertionError("handler should not run for invalid pipeline payload")

    worker = DbWorker(session, {"extract_mentions": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "job payload step must match job_type"
    assert session.query(AuditEvent).filter_by(event_type="job.failed_terminal").count() == 1


def test_worker_rejects_job_missing_pipeline_version_before_handler(session: Session) -> None:
    project = seed_project(session)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="resolve_aliases",
        status="queued",
        idempotency_key="resolve-aliases:missing-version",
        payload={"step": "resolve_aliases"},
    )
    session.add(job)
    session.commit()
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        raise AssertionError("handler should not run for invalid pipeline payload")

    worker = DbWorker(session, {"resolve_aliases": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "job payload requires pipeline_version"
    assert session.query(AuditEvent).filter_by(event_type="job.failed_terminal").count() == 1


def test_worker_success_is_audited(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "rebuild_graph_projection")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, _job: JobRecord) -> None:
        return None

    worker = DbWorker(session, {"rebuild_graph_projection": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "succeeded"
    assert refreshed.locked_by == "worker-1"
    assert session.query(AuditEvent).filter_by(event_type="job.succeeded").count() == 1


def test_worker_records_job_metrics_without_payload_values(session: Session) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "rebuild_graph_projection")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)
    job.created_at = now - timedelta(seconds=9)
    job.payload = {
        "step": "rebuild_graph_projection",
        "pipeline_version": "pipeline-v1",
        "manuscript_text": "Mira 把钥匙放在两人之间。",
    }
    session.commit()
    metrics = MetricsRegistry()

    def handler(_session: Session, _job: JobRecord) -> None:
        return None

    worker = DbWorker(
        session,
        {"rebuild_graph_projection": handler},
        now=lambda: now,
        metrics=metrics,
    )
    processed = worker.run_once(worker_id="worker-metrics")

    assert processed is True
    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_worker_jobs_total{job_type="rebuild_graph_projection",status="succeeded"} 1'
    ) in rendered
    assert ('sextant_job_queue_age_seconds_sum{job_type="rebuild_graph_projection"} 9') in rendered
    assert "Mira 把钥匙放在两人之间" not in rendered


def test_worker_does_not_mark_success_after_running_job_is_cancelled(
    session: Session,
) -> None:
    project = seed_project(session)
    job = seed_job(session, project, "run_memory_writeback")
    now = datetime(2026, 5, 31, 12, tzinfo=UTC)

    def handler(_session: Session, running_job: JobRecord) -> None:
        running_job.status = "cancelled"
        running_job.run_after = None
        running_job.last_error = None
        _session.flush()

    worker = DbWorker(session, {"run_memory_writeback": handler}, now=lambda: now)
    processed = worker.run_once(worker_id="worker-1")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "cancelled"
    assert refreshed.locked_by is None
    assert refreshed.locked_at is None
    assert session.query(AuditEvent).filter_by(event_type="job.succeeded").count() == 0
    assert session.query(AuditEvent).filter_by(event_type="job.cancelled_acknowledged").count() == 1


def test_rebuild_graph_projection_job_handler_rebuilds_edges(session: Session) -> None:
    project = seed_project(session)
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref="object://raw/chapter-3",
    )
    source_version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
    )
    processed_view = SourceProcessedView(
        id=uuid4(),
        version_id=source_version.id,
        cleaning_profile="draft_profile_v1",
        markdown_ref="object://markdown/graph-worker",
        raw_offset_map_ref="object://offsets/graph-worker",
        view_status="current",
    )
    span = SourceSpan(
        id=uuid4(),
        source_id=raw_source.id,
        version_id=source_version.id,
        view_id=processed_view.id,
        start_offset=0,
        end_offset=29,
        raw_start_offset=0,
        raw_end_offset=29,
        text_preview="Mira owns the Lantern Map.",
        narration_layer="narrator",
    )
    fact = FactAssertionRecord(
        id=uuid4(),
        project_id=project.id,
        subject_ref={"type": "character", "id": "mira"},
        predicate="owns",
        object_ref={"type": "object", "id": "lantern-map"},
        fact_status="canon",
        evidence_span_ids=[str(span.id)],
        confidence=0.95,
        source_scope="user_draft",
        promotion_decision_id=uuid4(),
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="rebuild_graph_projection",
        status="queued",
        idempotency_key=f"{project.id}:project:test-source-state",
        payload={
            "step": "rebuild_graph_projection",
            "pipeline_version": "pipeline-v1",
            "projection_scope": "project",
            "source_state_hash": "test-source-state",
        },
    )
    session.add_all([raw_source, source_version, processed_view, span, fact, job])
    session.commit()

    worker = DbWorker(
        session,
        {"rebuild_graph_projection": GraphProjectionRebuildHandler()},
    )
    processed = worker.run_once(worker_id="worker-graph")

    edge = session.query(GraphProjectionEdge).one()
    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert edge.source_ref == {"type": "fact_assertion", "id": str(fact.id)}
    assert edge.evidence_refs == [{"type": "source_span", "id": fact.evidence_span_ids[0]}]
    audit = session.query(AuditEvent).filter_by(event_type="graph_projection.rebuilt").one()
    assert audit.decision["created_edge_count"] == 1


def test_skill_replay_eval_job_passes_against_stored_structured_output(
    session: Session,
) -> None:
    project = seed_project(session)
    structured_output = {
        "text": "米拉停在西档案室门口。",
        "review_cues": [],
        "finish_reason": "stop",
    }
    skill_run = seed_skill_run(session, project, structured_output=structured_output)
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_skill_replay_eval",
        status="queued",
        idempotency_key=f"replay:{skill_run.id}:case-1",
        payload={
            "step": "run_skill_replay_eval",
            "pipeline_version": "pipeline-v1",
            "case_id": "next-page-agent/case-1",
            "skill_run_id": str(skill_run.id),
            "expected_structured_output": structured_output,
            "expected_validation_result": {"status": "valid"},
        },
    )
    session.add(job)
    session.commit()

    worker = DbWorker(session, {"run_skill_replay_eval": SkillReplayEvalHandler()})
    processed = worker.run_once(worker_id="worker-replay")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "succeeded"
    audit = session.query(AuditEvent).filter_by(event_type="skill.replay_eval").one()
    assert audit.subject_ref == {"type": "skill_run", "id": str(skill_run.id)}
    assert audit.decision["status"] == "pass"
    assert audit.decision["case_id"] == "next-page-agent/case-1"
    assert audit.decision["compared_validation_result"] is True
    assert "米拉停在西档案室门口。" not in repr(audit.decision)


def test_skill_replay_eval_job_fails_terminal_on_structured_output_mismatch(
    session: Session,
) -> None:
    project = seed_project(session)
    skill_run = seed_skill_run(
        session,
        project,
        structured_output={
            "text": "米拉停在西档案室门口。",
            "review_cues": [],
            "finish_reason": "stop",
        },
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_skill_replay_eval",
        status="queued",
        idempotency_key=f"replay:{skill_run.id}:case-2",
        payload={
            "step": "run_skill_replay_eval",
            "pipeline_version": "pipeline-v1",
            "case_id": "next-page-agent/case-2",
            "skill_run_id": str(skill_run.id),
            "expected_structured_output": {
                "text": "凯斯特停在西档案室门口。",
                "review_cues": [],
                "finish_reason": "stop",
            },
        },
    )
    session.add(job)
    session.commit()

    worker = DbWorker(session, {"run_skill_replay_eval": SkillReplayEvalHandler()})
    processed = worker.run_once(worker_id="worker-replay")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "skill replay eval structured output mismatch"
    audit = session.query(AuditEvent).filter_by(event_type="skill.replay_eval").one()
    assert audit.decision["status"] == "fail"
    assert audit.decision["reason"] == "structured_output_mismatch"
    assert audit.decision["case_id"] == "next-page-agent/case-2"
    assert audit.decision["mismatch_paths"] == ["text"]
    assert "米拉停在西档案室门口。" not in repr(audit.decision)
    assert "凯斯特停在西档案室门口。" not in repr(audit.decision)
    assert session.query(AuditEvent).filter_by(event_type="job.failed_terminal").count() == 1


def test_skill_replay_eval_job_rejects_cross_project_skill_run(
    session: Session,
) -> None:
    project = seed_project(session)
    other_project = seed_project(session)
    skill_run = seed_skill_run(
        session,
        other_project,
        structured_output={
            "text": "米拉停在西档案室门口。",
            "review_cues": [],
            "finish_reason": "stop",
        },
    )
    job = JobRecord(
        id=uuid4(),
        project_id=project.id,
        job_type="run_skill_replay_eval",
        status="queued",
        idempotency_key=f"replay:{skill_run.id}:cross-project",
        payload={
            "step": "run_skill_replay_eval",
            "pipeline_version": "pipeline-v1",
            "skill_run_id": str(skill_run.id),
            "expected_structured_output": skill_run.structured_output,
        },
    )
    session.add(job)
    session.commit()

    worker = DbWorker(session, {"run_skill_replay_eval": SkillReplayEvalHandler()})
    processed = worker.run_once(worker_id="worker-replay")

    refreshed = session.get(JobRecord, job.id)
    assert processed is True
    assert refreshed.status == "failed_terminal"
    assert refreshed.last_error == "SkillRun was not found for replay eval."
    assert session.query(AuditEvent).filter_by(event_type="skill.replay_eval").count() == 0
    assert session.query(AuditEvent).filter_by(event_type="job.failed_terminal").count() == 1
