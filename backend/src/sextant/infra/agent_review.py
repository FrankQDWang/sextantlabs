from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.domain.agent_risk import contains_canon_risk_language
from sextant.domain.prose_contract_review import ProseContractFinding, review_prose_contract
from sextant.infra.db.models import (
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    AuditEvent,
    JobRecord,
)
from sextant.infra.worker import TerminalJobError
from sextant.ports.object_store import ObjectStore


class AgentReviewHandler:
    def __init__(self, object_store: ObjectStore) -> None:
        self._object_store = object_store

    def __call__(self, session: Session, job: JobRecord) -> None:
        candidate = _candidate_from_payload(session, job)
        policy_version = _payload_text(job, "review_policy_version")
        text = self._object_store.get_text(candidate.candidate_text_ref)
        if not text.strip():
            raise TerminalJobError("DraftCandidate text is empty for agent review.")

        findings = _review_findings(session, candidate, text, policy_version)
        if candidate.status in {"generated", "reviewed"}:
            if any(not finding.can_offer_to_author for finding in findings):
                candidate.status = "blocked"
            else:
                candidate.status = "offered_to_author"

        session.add(
            AuditEvent(
                id=uuid4(),
                project_id=job.project_id,
                request_id=f"job:{job.id}",
                actor_id=None,
                event_type="agent.review_completed",
                subject_ref={"type": "draft_candidate", "id": str(candidate.id)},
                decision={
                    "draft_candidate_id": str(candidate.id),
                    "review_policy_version": policy_version,
                    "finding_count": len(findings),
                    "candidate_status": candidate.status,
                },
            )
        )
        session.flush()


def _candidate_from_payload(session: Session, job: JobRecord) -> AgentDraftCandidateRecord:
    value = job.payload.get("draft_candidate_id")
    try:
        candidate_id = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError("job payload requires draft_candidate_id") from exc
    candidate = session.get(AgentDraftCandidateRecord, candidate_id)
    if candidate is None or candidate.project_id != job.project_id:
        raise TerminalJobError("DraftCandidate was not found for agent review.")
    return candidate


def _payload_text(job: JobRecord, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TerminalJobError(f"job payload requires {key}")
    return value.strip()


def _review_findings(
    session: Session,
    candidate: AgentDraftCandidateRecord,
    text: str,
    policy_version: str,
) -> list[AgentReviewFindingRecord]:
    finding_specs: list[ProseContractFinding] = []
    if _has_high_risk_phrase(text):
        finding_specs.append(
            ProseContractFinding(
                risk_level="high",
                risk_type="canon_risk",
                summary="Draft presents risk-context material as if it were canon.",
                storytelling_refs={
                    "source": "agent_review_worker",
                    "review_policy_version": policy_version,
                },
                suggested_revision="Keep the risky knowledge framed as uncertainty or omit it.",
                can_offer_to_author=False,
                maps_to_review_type_if_accepted="canon_conflict",
            )
        )
    finding_specs.extend(
        review_prose_contract(
            text=text,
            contract=_prose_rendering_contract(session, candidate),
            policy_version=policy_version,
            candidate_range=candidate.affected_range,
        )
    )
    if not finding_specs:
        return []

    findings: list[AgentReviewFindingRecord] = []
    seen_risk_types: set[str] = set()
    for finding_spec in finding_specs:
        if finding_spec.risk_type in seen_risk_types:
            continue
        seen_risk_types.add(finding_spec.risk_type)
        existing = session.scalars(
            select(AgentReviewFindingRecord)
            .where(AgentReviewFindingRecord.draft_candidate_id == candidate.id)
            .where(AgentReviewFindingRecord.risk_type == finding_spec.risk_type)
        ).first()
        if existing is not None:
            findings.append(existing)
            continue

        finding = AgentReviewFindingRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            risk_level=finding_spec.risk_level,
            risk_type=finding_spec.risk_type,
            summary=finding_spec.summary,
            affected_text_ref=candidate.candidate_text_ref,
            memory_refs={"candidate_memory_refs": candidate.memory_refs},
            storytelling_refs=finding_spec.storytelling_refs,
            suggested_revision=finding_spec.suggested_revision,
            can_offer_to_author=finding_spec.can_offer_to_author,
            maps_to_review_type_if_accepted=finding_spec.maps_to_review_type_if_accepted,
            draft_local_only=True,
        )
        session.add(finding)
        findings.append(finding)
    session.flush()
    return findings


def _prose_rendering_contract(
    session: Session, candidate: AgentDraftCandidateRecord
) -> dict[str, object] | None:
    control = session.scalars(
        select(AgentStorytellingControlRecord)
        .where(AgentStorytellingControlRecord.draft_candidate_id == candidate.id)
        .where(AgentStorytellingControlRecord.control_type == "prose_rendering_contract")
    ).first()
    if control is None:
        return None
    return control.payload


def _has_high_risk_phrase(text: str) -> bool:
    return contains_canon_risk_language(text)
