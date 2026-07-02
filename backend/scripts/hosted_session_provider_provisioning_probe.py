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

PROVISIONING_PROOF_SCHEMES = {
    "runbook",
    "https",
    "ci-artifact",
    "auth0",
    "cognito",
    "okta",
    "clerk",
    "supabase",
}
SESSION_PROVIDER_SCHEMES = {"auth0", "cognito", "okta", "clerk", "supabase"}


class ConfigError(RuntimeError):
    pass


class SessionProviderProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class SessionProviderProvisioningConfig:
    deployment_version: str
    issuer: str
    issuer_host: str
    jwks_url: str
    admin_url: str
    raw_proof_ref: str
    proof_ref_scheme: str
    artifact_url: str
    artifact_url_host: str
    bearer_token: str | None
    timeout_seconds: float
    expected_statuses: tuple[str, ...]
    min_clients: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SessionProviderProvisioningConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "session-provider provisioning proof."
            )
        raw_proof_ref = _required(env, "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF")
        proof_ref_scheme = _validate_ref_scheme(
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF",
            raw_proof_ref,
            PROVISIONING_PROOF_SCHEMES,
        )
        artifact_url = _artifact_url(env, raw_proof_ref, proof_ref_scheme)
        issuer = _required(env, "SEXTANT_SESSION_ISSUER")
        return cls(
            deployment_version=_required(env, "SEXTANT_DEPLOYMENT_VERSION"),
            issuer=issuer,
            issuer_host=_validate_hosted_https_url("SEXTANT_SESSION_ISSUER", issuer),
            jwks_url=_hosted_https_url_value(env, "SEXTANT_SESSION_JWKS_URL"),
            admin_url=_hosted_https_url_value(env, "SEXTANT_SESSION_PROVIDER_ADMIN_URL"),
            raw_proof_ref=raw_proof_ref,
            proof_ref_scheme=proof_ref_scheme,
            artifact_url=artifact_url,
            artifact_url_host=_validate_hosted_https_url(
                "SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL",
                artifact_url,
            ),
            bearer_token=_optional(
                env,
                "SEXTANT_SESSION_PROVIDER_PROVISIONING_BEARER_TOKEN",
            ),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_SESSION_PROVIDER_PROVISIONING_TIMEOUT_SECONDS", "10"),
                "SEXTANT_SESSION_PROVIDER_PROVISIONING_TIMEOUT_SECONDS",
            ),
            expected_statuses=_expected_statuses(
                env.get(
                    "SEXTANT_SESSION_PROVIDER_PROVISIONING_EXPECT_STATUSES",
                    "provisioned,ready,success",
                )
            ),
            min_clients=_positive_int(
                env.get("SEXTANT_SESSION_PROVIDER_PROVISIONING_MIN_CLIENTS", "1"),
                "SEXTANT_SESSION_PROVIDER_PROVISIONING_MIN_CLIENTS",
            ),
        )


ArtifactFetcher = Callable[[SessionProviderProvisioningConfig], dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe hosted Sextant session-provider provisioning evidence."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help=(
            "Validate hosted session-provider provisioning configuration without network requests."
        ),
    )
    args = parser.parse_args()
    try:
        config = SessionProviderProvisioningConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-session-provider-provisioning-config-ok")
        return
    try:
        result = run_session_provider_provisioning_probe(config)
    except (SessionProviderProvisioningError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_session_provider_provisioning_probe(
    config: SessionProviderProvisioningConfig,
    *,
    artifact_fetcher: ArtifactFetcher | None = None,
) -> dict[str, object]:
    fetcher = artifact_fetcher or fetch_provisioning_artifact
    artifact = fetcher(config)
    deployment_version = _field_text(artifact, "deployment_version")
    if deployment_version != config.deployment_version:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact reported deployment version "
            f"{deployment_version!r}; expected {config.deployment_version!r}."
        )
    provider = _field_text(artifact, "provider").lower()
    if provider not in SESSION_PROVIDER_SCHEMES:
        raise SessionProviderProvisioningError(
            f"Session-provider provisioning artifact provider {provider!r} is not supported."
        )
    if config.proof_ref_scheme in SESSION_PROVIDER_SCHEMES and provider != config.proof_ref_scheme:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact provider "
            f"{provider!r}; expected {config.proof_ref_scheme!r}."
        )
    issuer = _field_text(artifact, "issuer")
    if issuer != config.issuer:
        raise SessionProviderProvisioningError(
            f"Session-provider provisioning artifact issuer {issuer!r}; expected {config.issuer!r}."
        )
    jwks_url = _field_text(artifact, "jwks_url")
    if jwks_url != config.jwks_url:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact JWKS URL "
            f"{jwks_url!r}; expected {config.jwks_url!r}."
        )
    admin_url = _field_text(artifact, "admin_url")
    if admin_url != config.admin_url:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact admin URL "
            f"{admin_url!r}; expected {config.admin_url!r}."
        )
    provisioning_status = _field_text(artifact, "status").lower()
    if provisioning_status not in config.expected_statuses:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact is not provisioned: "
            f"{provisioning_status!r} not in {config.expected_statuses!r}."
        )
    client_count = _positive_artifact_int(artifact, "client_count")
    if client_count < config.min_clients:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact has "
            f"{client_count} client(s); expected at least {config.min_clients}."
        )
    return {
        "status": "pass",
        "deployment_version": deployment_version,
        "provider": provider,
        "issuer_host": config.issuer_host,
        "jwks_host": _host(config.jwks_url),
        "admin_host": _host(config.admin_url),
        "provisioning_status": provisioning_status,
        "client_count": client_count,
        "artifact_url_host": config.artifact_url_host,
        "artifact_url_path_sha256": _sha256(urlparse(config.artifact_url).path or "/"),
        "artifact_sha256": _artifact_hash(artifact),
        "proof_ref_scheme": config.proof_ref_scheme,
        "proof_ref_sha256": _sha256(config.raw_proof_ref),
    }


def fetch_provisioning_artifact(
    config: SessionProviderProvisioningConfig,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.artifact_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(
            f"Session-provider provisioning probe failed with HTTP {exc.code}."
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            "Session-provider provisioning probe could not reach artifact URL."
        ) from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Session-provider provisioning artifact did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Session-provider provisioning artifact must be a JSON object.")
    return payload


def _artifact_url(env: Mapping[str, str], raw_proof_ref: str, proof_ref_scheme: str) -> str:
    configured = env.get("SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL", "").strip()
    if proof_ref_scheme == "https":
        return configured or raw_proof_ref
    if not configured:
        raise ConfigError(
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL is required when "
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF is not an HTTPS artifact URL."
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
        raise SessionProviderProvisioningError(
            f"Session-provider provisioning artifact field {field_name!r} must be text."
        )
    return value.strip()


def _positive_artifact_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or value < 0:
        raise SessionProviderProvisioningError(
            "Session-provider provisioning artifact field "
            f"{field_name!r} must be a non-negative integer."
        )
    return value


def _expected_statuses(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not statuses:
        raise ConfigError(
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_EXPECT_STATUSES must not be empty."
        )
    return statuses


def _hosted_https_url_value(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    _validate_hosted_https_url(name, value)
    return value


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


def _host(value: str) -> str:
    return (urlparse(value).hostname or "").strip().rstrip(".").lower()


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted session-provider provisioning proof.")
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
        "issuer_sha256": _sha256(str(payload.get("issuer", ""))),
        "jwks_url_sha256": _sha256(str(payload.get("jwks_url", ""))),
        "admin_url_sha256": _sha256(str(payload.get("admin_url", ""))),
        "status": payload.get("status"),
        "client_count": payload.get("client_count"),
    }
    encoded = json.dumps(safe_shape, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
