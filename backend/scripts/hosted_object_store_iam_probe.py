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

IAM_PROOF_SCHEMES = {
    "runbook",
    "https",
    "aws-iam",
    "gcp-iam",
    "azure-rbac",
    "cloudflare-r2",
}
IAM_PROVIDER_SCHEMES = {"aws-iam", "gcp-iam", "azure-rbac", "cloudflare-r2"}


class ConfigError(RuntimeError):
    pass


class ObjectStoreIamError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectStoreIamConfig:
    deployment_version: str
    object_store_root: str
    raw_proof_ref: str
    proof_ref_scheme: str
    artifact_url: str
    artifact_url_host: str
    bearer_token: str | None
    timeout_seconds: float
    expected_statuses: tuple[str, ...]
    min_policy_statements: int
    min_runtime_principals: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ObjectStoreIamConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "object-store IAM proof."
            )
        object_store_root = _required(env, "SEXTANT_OBJECT_STORE_ROOT")
        if not object_store_root.startswith("s3://"):
            raise ConfigError("SEXTANT_OBJECT_STORE_ROOT must be an s3:// URI.")
        raw_proof_ref = _required(env, "SEXTANT_OBJECT_STORE_IAM_PROOF_REF")
        proof_ref_scheme = _validate_ref_scheme(
            "SEXTANT_OBJECT_STORE_IAM_PROOF_REF",
            raw_proof_ref,
            IAM_PROOF_SCHEMES,
        )
        artifact_url = _artifact_url(env, raw_proof_ref, proof_ref_scheme)
        return cls(
            deployment_version=_required(env, "SEXTANT_DEPLOYMENT_VERSION"),
            object_store_root=object_store_root,
            raw_proof_ref=raw_proof_ref,
            proof_ref_scheme=proof_ref_scheme,
            artifact_url=artifact_url,
            artifact_url_host=_validate_hosted_https_url(
                "SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL",
                artifact_url,
            ),
            bearer_token=_optional(env, "SEXTANT_OBJECT_STORE_IAM_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_OBJECT_STORE_IAM_TIMEOUT_SECONDS", "10"),
                "SEXTANT_OBJECT_STORE_IAM_TIMEOUT_SECONDS",
            ),
            expected_statuses=_expected_statuses(
                env.get(
                    "SEXTANT_OBJECT_STORE_IAM_EXPECT_STATUSES",
                    "attached,ready,success",
                )
            ),
            min_policy_statements=_positive_int(
                env.get("SEXTANT_OBJECT_STORE_IAM_MIN_POLICY_STATEMENTS", "1"),
                "SEXTANT_OBJECT_STORE_IAM_MIN_POLICY_STATEMENTS",
            ),
            min_runtime_principals=_positive_int(
                env.get("SEXTANT_OBJECT_STORE_IAM_MIN_RUNTIME_PRINCIPALS", "1"),
                "SEXTANT_OBJECT_STORE_IAM_MIN_RUNTIME_PRINCIPALS",
            ),
        )


ArtifactFetcher = Callable[[ObjectStoreIamConfig], dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe hosted Sextant object-store IAM evidence.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted object-store IAM configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = ObjectStoreIamConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-object-store-iam-config-ok")
        return
    try:
        result = run_object_store_iam_probe(config)
    except (ObjectStoreIamError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_object_store_iam_probe(
    config: ObjectStoreIamConfig,
    *,
    artifact_fetcher: ArtifactFetcher | None = None,
) -> dict[str, object]:
    fetcher = artifact_fetcher or fetch_iam_artifact
    artifact = fetcher(config)
    deployment_version = _field_text(artifact, "deployment_version")
    if deployment_version != config.deployment_version:
        raise ObjectStoreIamError(
            "Object-store IAM artifact reported deployment version "
            f"{deployment_version!r}; expected {config.deployment_version!r}."
        )
    provider = _field_text(artifact, "provider").lower()
    if provider not in IAM_PROVIDER_SCHEMES:
        raise ObjectStoreIamError(
            f"Object-store IAM artifact provider {provider!r} is not supported."
        )
    if config.proof_ref_scheme in IAM_PROVIDER_SCHEMES and provider != config.proof_ref_scheme:
        raise ObjectStoreIamError(
            f"Object-store IAM artifact provider {provider!r}; expected "
            f"{config.proof_ref_scheme!r}."
        )
    object_store_root = _field_text(artifact, "object_store_root")
    if object_store_root != config.object_store_root:
        raise ObjectStoreIamError(
            "Object-store IAM artifact object-store root "
            f"{object_store_root!r}; expected {config.object_store_root!r}."
        )
    iam_status = _field_text(artifact, "status").lower()
    if iam_status not in config.expected_statuses:
        raise ObjectStoreIamError(
            f"Object-store IAM artifact is not ready: {iam_status!r} not in "
            f"{config.expected_statuses!r}."
        )
    policy_statement_count = _positive_artifact_int(artifact, "policy_statement_count")
    if policy_statement_count < config.min_policy_statements:
        raise ObjectStoreIamError(
            "Object-store IAM artifact has "
            f"{policy_statement_count} policy statement(s); expected at least "
            f"{config.min_policy_statements}."
        )
    runtime_principal_count = _positive_artifact_int(artifact, "runtime_principal_count")
    if runtime_principal_count < config.min_runtime_principals:
        raise ObjectStoreIamError(
            "Object-store IAM artifact has "
            f"{runtime_principal_count} runtime principal(s); expected at least "
            f"{config.min_runtime_principals}."
        )
    return {
        "status": "pass",
        "deployment_version": deployment_version,
        "provider": provider,
        "iam_status": iam_status,
        "policy_statement_count": policy_statement_count,
        "runtime_principal_count": runtime_principal_count,
        "object_store_root_scheme": urlparse(config.object_store_root).scheme,
        "object_store_root_sha256": _sha256(config.object_store_root),
        "artifact_url_host": config.artifact_url_host,
        "artifact_url_path_sha256": _sha256(urlparse(config.artifact_url).path or "/"),
        "artifact_sha256": _artifact_hash(artifact),
        "proof_ref_scheme": config.proof_ref_scheme,
        "proof_ref_sha256": _sha256(config.raw_proof_ref),
    }


def fetch_iam_artifact(config: ObjectStoreIamConfig) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.artifact_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Object-store IAM probe failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("Object-store IAM probe could not reach artifact URL.") from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Object-store IAM artifact did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Object-store IAM artifact must be a JSON object.")
    return payload


def _artifact_url(env: Mapping[str, str], raw_proof_ref: str, proof_ref_scheme: str) -> str:
    configured = env.get("SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL", "").strip()
    if proof_ref_scheme == "https":
        return configured or raw_proof_ref
    if not configured:
        raise ConfigError(
            "SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL is required when "
            "SEXTANT_OBJECT_STORE_IAM_PROOF_REF is not an HTTPS artifact URL."
        )
    return configured


def _validate_ref_scheme(name: str, value: str, allowed_schemes: set[str]) -> str:
    parsed = urlparse(value)
    scheme = parsed.scheme.lower()
    if scheme not in allowed_schemes or not (parsed.netloc or parsed.path.lstrip("/")):
        allowed = ", ".join(sorted(f"{allowed}://" for allowed in allowed_schemes))
        raise ConfigError(f"{name} must use one of: {allowed}")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            f"{name} must not include URL userinfo, params, query strings, or fragments."
        )
    if scheme == "https":
        _validate_hosted_https_url(name, value)
    return scheme


def _field_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ObjectStoreIamError(f"Object-store IAM artifact field {field_name!r} must be text.")
    return value.strip()


def _positive_artifact_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or value < 0:
        raise ObjectStoreIamError(
            f"Object-store IAM artifact field {field_name!r} must be a non-negative integer."
        )
    return value


def _expected_statuses(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not statuses:
        raise ConfigError("SEXTANT_OBJECT_STORE_IAM_EXPECT_STATUSES must not be empty.")
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
        raise ConfigError(f"{name} is required for hosted object-store IAM proof.")
    return value


def _optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name, "").strip()
    return value or None


def _positive_float(raw: str, name: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive number.")
    return value


def _positive_int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return value


def _artifact_hash(payload: Mapping[str, object]) -> str:
    safe_shape = {
        "deployment_version": payload.get("deployment_version"),
        "provider": payload.get("provider"),
        "object_store_root_sha256": _sha256(str(payload.get("object_store_root", ""))),
        "status": payload.get("status"),
        "policy_statement_count": payload.get("policy_statement_count"),
        "runtime_principal_count": payload.get("runtime_principal_count"),
    }
    encoded = json.dumps(safe_shape, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
