from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from sextant.infra.db.models import JOB_STATUSES, JOB_TYPES, JobRecord
from sextant.infra.worker import JobHandler


def worker_health_report(
    session: Session,
    handlers: Mapping[str, JobHandler],
    *,
    now: Callable[[], datetime] | None = None,
    lease_timeout: timedelta = timedelta(minutes=5),
) -> dict[str, object]:
    session.execute(text("SELECT 1")).scalar_one()

    documented_job_types = set(JOB_TYPES)
    registered_job_types = set(handlers)
    missing_job_types = sorted(documented_job_types - registered_job_types)
    extra_job_types = sorted(registered_job_types - documented_job_types)
    stale_cutoff = (now or (lambda: datetime.now(UTC)))() - lease_timeout

    job_counts = dict.fromkeys(JOB_STATUSES, 0)
    for status, count in session.execute(
        select(JobRecord.status, func.count(JobRecord.id)).group_by(JobRecord.status)
    ):
        job_counts[str(status)] = int(count)

    stale_running_jobs = session.scalar(
        select(func.count(JobRecord.id))
        .where(JobRecord.status == "running")
        .where(JobRecord.locked_at.is_not(None))
        .where(JobRecord.locked_at < stale_cutoff)
    )

    return {
        "status": "pass" if not missing_job_types and not extra_job_types else "fail",
        "database": "ok",
        "documented_job_types": sorted(documented_job_types),
        "registered_job_types": sorted(registered_job_types),
        "missing_job_types": missing_job_types,
        "extra_job_types": extra_job_types,
        "job_counts": job_counts,
        "stale_running_jobs": int(stale_running_jobs or 0),
        "lease_timeout_seconds": int(lease_timeout.total_seconds()),
    }
