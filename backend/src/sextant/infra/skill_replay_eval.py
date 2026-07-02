from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from sextant.infra.db.models import AuditEvent, JobRecord, SkillRun
from sextant.infra.worker import TerminalJobError

MAX_REPORTED_MISMATCH_PATHS = 20


class SkillReplayEvalHandler:
    def __call__(self, session: Session, job: JobRecord) -> None:
        skill_run = _skill_run_from_payload(session, job)
        expected_structured_output = _payload_dict(job, "expected_structured_output")
        expected_validation_result = _optional_payload_dict(job, "expected_validation_result")

        structured_output_paths = _mismatch_paths(
            expected_structured_output,
            skill_run.structured_output,
        )
        validation_result_paths = (
            _mismatch_paths(expected_validation_result, skill_run.validation_result)
            if expected_validation_result is not None
            else []
        )

        if structured_output_paths or validation_result_paths:
            reason = (
                "structured_output_mismatch"
                if structured_output_paths
                else "validation_result_mismatch"
            )
            _audit_replay_eval(
                session,
                job,
                skill_run,
                status="fail",
                reason=reason,
                structured_output_paths=structured_output_paths,
                validation_result_paths=validation_result_paths,
                compared_validation_result=expected_validation_result is not None,
                case_id=_optional_payload_text(job, "case_id"),
                expected_structured_output=expected_structured_output,
                expected_validation_result=expected_validation_result,
            )
            raise TerminalJobError(f"skill replay eval {reason.replace('_', ' ')}")

        _audit_replay_eval(
            session,
            job,
            skill_run,
            status="pass",
            reason=None,
            structured_output_paths=[],
            validation_result_paths=[],
            compared_validation_result=expected_validation_result is not None,
            case_id=_optional_payload_text(job, "case_id"),
            expected_structured_output=expected_structured_output,
            expected_validation_result=expected_validation_result,
        )


def _skill_run_from_payload(session: Session, job: JobRecord) -> SkillRun:
    value = job.payload.get("skill_run_id")
    try:
        skill_run_id = UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise TerminalJobError("job payload requires skill_run_id") from exc

    skill_run = session.get(SkillRun, skill_run_id)
    if skill_run is None or skill_run.project_id != job.project_id:
        raise TerminalJobError("SkillRun was not found for replay eval.")
    return skill_run


def _payload_dict(job: JobRecord, key: str) -> dict[str, Any]:
    value = job.payload.get(key)
    if not isinstance(value, dict):
        raise TerminalJobError(f"job payload requires {key}")
    return cast(dict[str, Any], value)


def _optional_payload_dict(job: JobRecord, key: str) -> dict[str, Any] | None:
    value = job.payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TerminalJobError(f"job payload requires {key}")
    return cast(dict[str, Any], value)


def _optional_payload_text(job: JobRecord, key: str) -> str | None:
    value = job.payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TerminalJobError(f"job payload has invalid {key}")
    return value.strip()


def _audit_replay_eval(
    session: Session,
    job: JobRecord,
    skill_run: SkillRun,
    *,
    status: str,
    reason: str | None,
    structured_output_paths: list[str],
    validation_result_paths: list[str],
    compared_validation_result: bool,
    case_id: str | None,
    expected_structured_output: dict[str, Any],
    expected_validation_result: dict[str, Any] | None,
) -> None:
    decision: dict[str, object] = {
        "status": status,
        "skill_run_id": str(skill_run.id),
        "skill_name": skill_run.skill_name,
        "skill_version": skill_run.skill_version,
        "prompt_version": skill_run.prompt_version,
        "input_schema_version": skill_run.input_schema_version,
        "output_schema_version": skill_run.output_schema_version,
        "input_hash": skill_run.input_hash,
        "skill_run_status": skill_run.status,
        "expected_structured_output_hash": _json_hash(expected_structured_output),
        "actual_structured_output_hash": _json_hash(skill_run.structured_output),
        "compared_validation_result": compared_validation_result,
    }
    if case_id is not None:
        decision["case_id"] = case_id
    if reason is not None:
        decision["reason"] = reason
    if structured_output_paths:
        decision["mismatch_paths"] = structured_output_paths
    if compared_validation_result:
        decision["expected_validation_result_hash"] = _json_hash(expected_validation_result or {})
        decision["actual_validation_result_hash"] = _json_hash(skill_run.validation_result)
        if validation_result_paths:
            decision["validation_result_mismatch_paths"] = validation_result_paths

    session.add(
        AuditEvent(
            id=uuid4(),
            project_id=job.project_id,
            request_id=f"job:{job.id}",
            actor_id=None,
            event_type="skill.replay_eval",
            subject_ref={"type": "skill_run", "id": str(skill_run.id)},
            decision=decision,
        )
    )
    session.flush()


def _json_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _mismatch_paths(expected: object, actual: object) -> list[str]:
    paths: list[str] = []
    _collect_mismatch_paths(expected, actual, "$", paths)
    return paths


def _collect_mismatch_paths(
    expected: object,
    actual: object,
    path: str,
    paths: list[str],
) -> None:
    if len(paths) >= MAX_REPORTED_MISMATCH_PATHS:
        return
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        expected_mapping = cast(Mapping[object, object], expected)
        actual_mapping = cast(Mapping[object, object], actual)
        keys = sorted(set(expected_mapping.keys()) | set(actual_mapping.keys()), key=str)
        for key in keys:
            if len(paths) >= MAX_REPORTED_MISMATCH_PATHS:
                return
            child_path = f"{path}.{key}" if path != "$" else str(key)
            if key not in expected_mapping or key not in actual_mapping:
                paths.append(child_path)
                continue
            _collect_mismatch_paths(
                expected_mapping[key],
                actual_mapping[key],
                child_path,
                paths,
            )
        return
    if _is_sequence(expected) and _is_sequence(actual):
        expected_sequence = cast(Sequence[object], expected)
        actual_sequence = cast(Sequence[object], actual)
        max_length = max(len(expected_sequence), len(actual_sequence))
        for index in range(max_length):
            if len(paths) >= MAX_REPORTED_MISMATCH_PATHS:
                return
            child_path = f"{path}[{index}]"
            if index >= len(expected_sequence) or index >= len(actual_sequence):
                paths.append(child_path)
                continue
            _collect_mismatch_paths(
                expected_sequence[index],
                actual_sequence[index],
                child_path,
                paths,
            )
        return
    if expected != actual:
        paths.append(path)


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)
