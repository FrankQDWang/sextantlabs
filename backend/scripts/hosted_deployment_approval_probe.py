from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_PROOF_SCHEMES = {
    "runbook",
    "https",
    "ci-artifact",
    "change-request",
    "github-deployment",
    "github-run",
}


class ConfigError(RuntimeError):
    pass


class DeploymentApprovalError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeploymentApprovalConfig:
    deployment_version: str
    raw_proof_ref: str
    proof_ref_scheme: str
    artifact_url: str
    artifact_url_host: str
    bearer_token: str | None
    timeout_seconds: float
    version_field: str
    status_field: str
    approvers_field: str
    expected_statuses: tuple[str, ...]
    min_approvers: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> DeploymentApprovalConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "deployment approval proof."
            )
        deployment_version = _required(env, "SEXTANT_DEPLOYMENT_VERSION")
        raw_proof_ref = _required(env, "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF")
        proof_ref_scheme = _validate_proof_ref(raw_proof_ref)
        artifact_url = _artifact_url(env, raw_proof_ref, proof_ref_scheme)
        artifact_url_host = _validate_hosted_https_url(
            "SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL", artifact_url
        )
        return cls(
            deployment_version=deployment_version,
            raw_proof_ref=raw_proof_ref,
            proof_ref_scheme=proof_ref_scheme,
            artifact_url=artifact_url,
            artifact_url_host=artifact_url_host,
            bearer_token=_optional(env, "SEXTANT_DEPLOYMENT_APPROVAL_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_DEPLOYMENT_APPROVAL_TIMEOUT_SECONDS", "10"),
                "SEXTANT_DEPLOYMENT_APPROVAL_TIMEOUT_SECONDS",
            ),
            version_field=env.get(
                "SEXTANT_DEPLOYMENT_APPROVAL_VERSION_FIELD", "deployment_version"
            ).strip()
            or "deployment_version",
            status_field=env.get("SEXTANT_DEPLOYMENT_APPROVAL_STATUS_FIELD", "status").strip()
            or "status",
            approvers_field=env.get(
                "SEXTANT_DEPLOYMENT_APPROVAL_APPROVERS_FIELD", "approvers"
            ).strip()
            or "approvers",
            expected_statuses=_expected_statuses(
                env.get("SEXTANT_DEPLOYMENT_APPROVAL_EXPECT_STATUSES", "approved,success,ready")
            ),
            min_approvers=_positive_int(
                env.get("SEXTANT_DEPLOYMENT_APPROVAL_MIN_APPROVERS", "1"),
                "SEXTANT_DEPLOYMENT_APPROVAL_MIN_APPROVERS",
            ),
        )


ArtifactFetcher = Callable[[DeploymentApprovalConfig], dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe hosted Sextant deployment approval/change-control evidence."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted deployment approval probe configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = DeploymentApprovalConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-deployment-approval-config-ok")
        return
    try:
        result = run_deployment_approval_probe(config)
    except (DeploymentApprovalError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_deployment_approval_probe(
    config: DeploymentApprovalConfig,
    *,
    artifact_fetcher: ArtifactFetcher | None = None,
) -> dict[str, object]:
    fetcher = artifact_fetcher or fetch_approval_artifact
    artifact = fetcher(config)
    deployment_version = _field_text(artifact, config.version_field)
    if deployment_version != config.deployment_version:
        raise DeploymentApprovalError(
            "Deployment approval artifact reported deployment version "
            f"{deployment_version!r}; expected {config.deployment_version!r}."
        )
    approval_status = _field_text(artifact, config.status_field).lower()
    if approval_status not in config.expected_statuses:
        raise DeploymentApprovalError(
            "Deployment approval artifact is not approved: "
            f"{approval_status!r} not in {config.expected_statuses!r}."
        )
    approver_count = _approver_count(artifact, config.approvers_field)
    if approver_count < config.min_approvers:
        raise DeploymentApprovalError(
            "Deployment approval artifact has "
            f"{approver_count} approver(s); expected at least {config.min_approvers}."
        )
    return {
        "status": "pass",
        "deployment_version": deployment_version,
        "approval_status": approval_status,
        "approver_count": approver_count,
        "artifact_url_host": config.artifact_url_host,
        "artifact_url_path_sha256": _sha256(urlparse(config.artifact_url).path or "/"),
        "artifact_sha256": _artifact_hash(artifact),
        "proof_ref_scheme": config.proof_ref_scheme,
        "proof_ref_sha256": _sha256(config.raw_proof_ref),
        "version_field": config.version_field,
        "status_field": config.status_field,
        "approvers_field": config.approvers_field,
    }


def fetch_approval_artifact(config: DeploymentApprovalConfig) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.artifact_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Deployment approval probe failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("Deployment approval probe could not reach artifact URL.") from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Deployment approval artifact did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Deployment approval artifact must be a JSON object.")
    return payload


def _artifact_url(env: Mapping[str, str], raw_proof_ref: str, proof_ref_scheme: str) -> str:
    configured = env.get("SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL", "").strip()
    if proof_ref_scheme == "https":
        return configured or raw_proof_ref
    if not configured:
        raise ConfigError(
            "SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL is required when "
            "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF is not an HTTPS artifact URL."
        )
    return configured


def _validate_proof_ref(value: str) -> str:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_PROOF_SCHEMES or not (parsed.netloc or parsed.path.lstrip("/")):
        raise ConfigError(
            "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF must be an auditable "
            "runbook://, https://, ci-artifact://, change-request://, "
            "github-deployment://, or github-run:// reference."
        )
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF must not include URL "
            "userinfo, params, query strings, or fragments."
        )
    if scheme == "https":
        _validate_hosted_https_url("SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF", value)
    return scheme


def _field_text(payload: Mapping[str, object], field_path: str) -> str:
    value: object = payload
    for part in field_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise DeploymentApprovalError(
                f"Deployment approval artifact field {field_path!r} is missing."
            )
        value = value[part]
    if not isinstance(value, str) or not value.strip():
        raise DeploymentApprovalError(
            f"Deployment approval artifact field {field_path!r} must be text."
        )
    return value.strip()


def _approver_count(payload: Mapping[str, object], field_path: str) -> int:
    value: object = payload
    for part in field_path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise DeploymentApprovalError(
                f"Deployment approval artifact field {field_path!r} is missing."
            )
        value = value[part]
    if isinstance(value, list):
        return len([item for item in value if isinstance(item, str) and item.strip()])
    if isinstance(value, int):
        return value
    raise DeploymentApprovalError(
        f"Deployment approval artifact field {field_path!r} must be a list or integer."
    )


def _expected_statuses(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not statuses:
        raise ConfigError("SEXTANT_DEPLOYMENT_APPROVAL_EXPECT_STATUSES must not be empty.")
    return statuses


def _validate_hosted_https_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            f"{name} must not include URL userinfo, params, query strings, or fragments."
        )
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")
    return host


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted deployment approval proof.")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


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


def _artifact_hash(payload: Mapping[str, object]) -> str:
    return _sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
