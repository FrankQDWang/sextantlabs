from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    project_id: UUID
    bearer_token: str
    timeout_seconds: float
    poll_attempts: int
    poll_interval_seconds: float
    source_title: str
    source_text: str
    expected_answer_type: str

    @classmethod
    def from_env(cls, env: dict[str, str]) -> SmokeConfig:
        base_url = _required(env, "SEXTANT_EXTERNAL_SMOKE_URL").rstrip("/")
        _validate_hosted_https_url("SEXTANT_EXTERNAL_SMOKE_URL", base_url)
        bearer_token = _required(env, "SEXTANT_EXTERNAL_SMOKE_BEARER_TOKEN").strip()
        project_id_text = _required(env, "SEXTANT_EXTERNAL_SMOKE_PROJECT_ID")
        try:
            project_id = UUID(project_id_text)
        except ValueError as exc:
            raise ConfigError("SEXTANT_EXTERNAL_SMOKE_PROJECT_ID must be a UUID.") from exc
        return cls(
            base_url=base_url,
            project_id=project_id,
            bearer_token=bearer_token,
            timeout_seconds=_positive_float(
                env.get("SEXTANT_EXTERNAL_SMOKE_TIMEOUT_SECONDS", "10"),
                "SEXTANT_EXTERNAL_SMOKE_TIMEOUT_SECONDS",
            ),
            poll_attempts=_positive_int(
                env.get("SEXTANT_EXTERNAL_SMOKE_POLL_ATTEMPTS", "30"),
                "SEXTANT_EXTERNAL_SMOKE_POLL_ATTEMPTS",
            ),
            poll_interval_seconds=_positive_float(
                env.get("SEXTANT_EXTERNAL_SMOKE_POLL_INTERVAL_SECONDS", "2"),
                "SEXTANT_EXTERNAL_SMOKE_POLL_INTERVAL_SECONDS",
            ),
            source_title=env.get("SEXTANT_EXTERNAL_SMOKE_SOURCE_TITLE", "Hosted smoke chapter"),
            source_text=env.get("SEXTANT_EXTERNAL_SMOKE_SOURCE_TEXT", _default_source_text()),
            expected_answer_type=env.get("SEXTANT_EXTERNAL_SMOKE_EXPECT_ANSWER_TYPE", "canon"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a hosted Sextant external smoke against a real deployed API."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted smoke configuration without sending network requests.",
    )
    args = parser.parse_args()
    try:
        config = SmokeConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-external-smoke-config-ok")
        return
    result = run_smoke(config)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_smoke(config: SmokeConfig) -> dict[str, object]:
    client = HostedApiClient(config)
    project = client.request_json("GET", f"/api/projects/{config.project_id}")
    source = client.request_json(
        "POST",
        f"/api/projects/{config.project_id}/sources",
        body={
            "title": config.source_title,
            "source_type": "draft_manuscript",
            "source_scope": "user_draft",
            "ownership_status": "owned",
            "text": config.source_text,
            "version_label": "hosted-smoke",
        },
        idempotency_prefix="source-create",
    )
    source_delta_id = str(source["source_delta_id"])
    job_id = str(source["memory_writeback_job_id"])
    job = _poll_job(client, config.project_id, job_id, config)
    preview = client.request_json(
        "GET",
        f"/api/projects/{config.project_id}/source-deltas/{source_delta_id}/memory-writeback-preview",
    )
    _require_preview_evidence(preview)
    answer = client.request_json(
        "POST",
        f"/api/projects/{config.project_id}/memory/answer",
        body={
            "question": "Mira 持有什么？",
            "subject_ref": {"type": "character", "id": "mira"},
            "predicate": "owns",
        },
        idempotency_prefix="memory-answer",
    )
    if answer.get("answer_type") != config.expected_answer_type:
        raise RuntimeError(
            "Hosted smoke MemoryAnswer returned "
            f"{answer.get('answer_type')!r}, expected {config.expected_answer_type!r}."
        )
    if not answer.get("source_span_refs"):
        raise RuntimeError("Hosted smoke MemoryAnswer did not cite SourceSpan evidence.")

    return {
        "status": "pass",
        "deployment_url": config.base_url,
        "project_id": str(config.project_id),
        "project_name": project.get("name"),
        "source_id": source["source_id"],
        "version_id": source["version_id"],
        "source_delta_id": source_delta_id,
        "job_id": job_id,
        "job_status": job.get("status"),
        "source_span_count": len(preview.get("source_spans", [])),
        "evidence_log_count": len(preview.get("evidence_log_entries", [])),
        "fact_count": len(preview.get("fact_assertions", [])),
        "memory_page_count": len(preview.get("memory_pages", [])),
        "graph_edge_count": len(preview.get("graph_edges", [])),
        "memory_answer_type": answer.get("answer_type"),
        "memory_answer_source_span_count": len(answer.get("source_span_refs", [])),
    }


class HostedApiClient:
    def __init__(self, config: SmokeConfig) -> None:
        self._config = config

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        idempotency_prefix: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._config.bearer_token}",
        }
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_prefix is not None:
            request_id = f"req-hosted-smoke-{idempotency_prefix}-{uuid4()}"
            idempotency_hash = sha256(request_id.encode("utf-8")).hexdigest()[:24]
            headers["X-Request-Id"] = request_id
            headers["Idempotency-Key"] = f"idem-hosted-smoke-{idempotency_hash}"
        request = Request(
            urljoin(f"{self._config.base_url}/", path.lstrip("/")),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {path} failed with HTTP {exc.code}: {error_body}"
            ) from exc
        return json.loads(raw_body)


def _poll_job(
    client: HostedApiClient,
    project_id: UUID,
    job_id: str,
    config: SmokeConfig,
) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    for _ in range(config.poll_attempts):
        latest = client.request_json("GET", f"/api/projects/{project_id}/jobs/{job_id}")
        if latest.get("status") == "succeeded":
            return latest
        if latest.get("status") in {"failed_retryable", "failed_terminal", "cancelled"}:
            raise RuntimeError(f"Hosted smoke job ended with status {latest.get('status')}.")
        time.sleep(config.poll_interval_seconds)
    raise RuntimeError(f"Hosted smoke job did not succeed after {config.poll_attempts} polls.")


def _require_preview_evidence(preview: dict[str, Any]) -> None:
    expectations = {
        "source_spans": "SourceSpan",
        "evidence_log_entries": "EvidenceLogEntry",
        "fact_assertions": "FactAssertion",
        "memory_pages": "MemoryPage",
        "graph_edges": "GraphProjection edge",
    }
    for field, label in expectations.items():
        if not preview.get(field):
            raise RuntimeError(f"Hosted smoke preview did not include {label} evidence.")


def _required(env: dict[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted external smoke.")
    return value


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive number.")
    return parsed


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _validate_hosted_https_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")


def _default_source_text() -> str:
    return "\n".join(
        [
            "Mira opens the hosted smoke ledger.",
            "FACT: character:mira | owns | object:lantern-map | low",
        ]
    )


if __name__ == "__main__":
    main()
