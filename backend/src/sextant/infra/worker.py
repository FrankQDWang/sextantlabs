from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from sextant.common.observability import MetricsRegistry
from sextant.infra.db.models import JOB_TYPES, AuditEvent, JobRecord

JobHandler = Callable[[Session, JobRecord], None]
PIPELINE_JOB_TYPES = frozenset(JOB_TYPES)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    initial_delay: timedelta
    max_backoff: timedelta


class RetryableJobError(Exception):
    failure_class = "infrastructure"

    def __init__(self, message: str, *, failure_class: str | None = None) -> None:
        super().__init__(message)
        self.failure_class = failure_class or self.failure_class


class InfrastructureRetryableJobError(RetryableJobError):
    failure_class = "infrastructure"


class ProviderRetryableJobError(RetryableJobError):
    failure_class = "provider"


class TerminalJobError(Exception):
    pass


class DbWorker:
    def __init__(
        self,
        session: Session,
        handlers: dict[str, JobHandler],
        *,
        now: Callable[[], datetime] | None = None,
        max_backoff: timedelta = timedelta(minutes=5),
        retry_policies: dict[str, RetryPolicy] | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        self._session = session
        self._handlers = handlers
        self._now = now or (lambda: datetime.now(UTC))
        self._metrics = metrics
        self._retry_policies = retry_policies or {
            "infrastructure": RetryPolicy(
                max_attempts=5,
                initial_delay=timedelta(seconds=30),
                max_backoff=max_backoff,
            ),
            "provider": RetryPolicy(
                max_attempts=3,
                initial_delay=timedelta(seconds=60),
                max_backoff=max_backoff,
            ),
        }

    def run_once(self, *, worker_id: str) -> bool:
        now = self._now()
        job = lease_next_job(self._session, worker_id=worker_id, now=now)
        if job is None:
            return False
        self._record_queue_age(job, now)

        handler = self._handlers.get(job.job_type)
        if handler is None:
            self._mark_terminal(job, f"no handler registered for {job.job_type}")
            self._record_job_outcome(job)
            return True

        payload_error = validate_job_payload(job)
        if payload_error is not None:
            self._mark_terminal(job, payload_error)
            self._record_job_outcome(job)
            return True

        try:
            handler(self._session, job)
        except RetryableJobError as exc:
            self._mark_retryable(job, exc)
            self._record_job_outcome(job)
        except TerminalJobError as exc:
            self._mark_terminal(job, str(exc))
            self._record_job_outcome(job)
        else:
            self._session.refresh(job)
            if job.status == "cancelled":
                job.run_after = None
                job.locked_by = None
                job.locked_at = None
                job.last_error = None
                self._audit(
                    job,
                    "job.cancelled_acknowledged",
                    {"job_type": job.job_type, "worker_id": worker_id},
                )
                self._session.commit()
                self._record_job_outcome(job)
                return True
            job.status = "succeeded"
            job.last_error = None
            job.run_after = None
            self._audit(job, "job.succeeded", {"job_type": job.job_type})
            self._session.commit()
            self._record_job_outcome(job)
        return True

    def _mark_retryable(self, job: JobRecord, error: RetryableJobError) -> None:
        failure_class = error.failure_class
        policy = self._retry_policies.get(failure_class, self._retry_policies["infrastructure"])
        error_message = str(error)
        if job.attempt_count >= policy.max_attempts:
            self._mark_terminal(
                job,
                error_message,
                decision={
                    "job_type": job.job_type,
                    "error": error_message,
                    "failure_class": failure_class,
                    "terminal_reason": "retry_budget_exhausted",
                    "attempt_count": job.attempt_count,
                    "max_attempts": policy.max_attempts,
                },
            )
            return
        delay = min(
            policy.initial_delay * (2 ** max(job.attempt_count - 1, 0)),
            policy.max_backoff,
        )
        job.status = "failed_retryable"
        job.last_error = error_message
        next_run_after = self._now() + delay
        job.run_after = next_run_after
        self._audit(
            job,
            "job.failed_retryable",
            {
                "job_type": job.job_type,
                "error": error_message,
                "failure_class": failure_class,
                "attempt_count": job.attempt_count,
                "max_attempts": policy.max_attempts,
                "next_run_after": next_run_after.isoformat(),
            },
        )
        self._session.commit()

    def _mark_terminal(
        self, job: JobRecord, error: str, *, decision: dict[str, object] | None = None
    ) -> None:
        job.status = "failed_terminal"
        job.last_error = error
        job.run_after = None
        self._audit(
            job,
            "job.failed_terminal",
            decision or {"job_type": job.job_type, "error": error},
        )
        self._session.commit()

    def _audit(self, job: JobRecord, event_type: str, decision: dict[str, object]) -> None:
        self._session.add(
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

    def _record_queue_age(self, job: JobRecord, now: datetime) -> None:
        if self._metrics is None:
            return
        created_at = job.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        age_seconds = max((now - created_at).total_seconds(), 0)
        self._metrics.observe_seconds(
            "sextant_job_queue_age_seconds",
            age_seconds,
            labels={"job_type": job.job_type},
        )

    def _record_job_outcome(self, job: JobRecord) -> None:
        if self._metrics is None:
            return
        self._metrics.increment(
            "sextant_worker_jobs_total",
            labels={"job_type": job.job_type, "status": job.status},
        )


def lease_next_job(session: Session, *, worker_id: str, now: datetime) -> JobRecord | None:
    job = session.scalars(
        select(JobRecord)
        .where(JobRecord.status.in_(("queued", "failed_retryable")))
        .where(or_(JobRecord.run_after.is_(None), JobRecord.run_after <= now))
        .order_by(JobRecord.created_at, JobRecord.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    ).first()
    if job is None:
        return None

    job.status = "running"
    job.locked_by = worker_id
    job.locked_at = now
    job.attempt_count += 1
    job.last_error = None
    session.flush()
    return job


def release_timed_out_jobs(
    session: Session,
    *,
    now: datetime,
    lease_timeout: timedelta,
) -> int:
    cutoff = now - lease_timeout
    jobs = list(
        session.scalars(
            select(JobRecord)
            .where(JobRecord.status == "running")
            .where(JobRecord.locked_at.is_not(None))
            .where(JobRecord.locked_at < cutoff)
        )
    )
    for job in jobs:
        job.status = "failed_retryable"
        job.last_error = "lease_timeout"
        job.run_after = now
        job.locked_by = None
        job.locked_at = None
    session.commit()
    return len(jobs)


def validate_job_payload(job: JobRecord) -> str | None:
    if job.job_type not in PIPELINE_JOB_TYPES:
        return "job_type is not a documented pipeline job"
    if not isinstance(job.payload, dict):
        return "job payload must be an object"
    if job.payload.get("step") != job.job_type:
        return "job payload step must match job_type"
    pipeline_version = job.payload.get("pipeline_version")
    if not isinstance(pipeline_version, str) or not pipeline_version.strip():
        return "job payload requires pipeline_version"
    return None
