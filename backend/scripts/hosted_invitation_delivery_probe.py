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

DELIVERY_PROVIDER_SCHEMES = {
    "ses",
    "sendgrid",
    "postmark",
    "mailgun",
    "smtp-tls",
    "supabase-auth",
}
DELIVERY_PROOF_SCHEMES = {
    "runbook",
    "https",
    "ci-artifact",
    "ses",
    "sendgrid",
    "postmark",
    "mailgun",
    "smtp-tls",
    "supabase-auth",
}


class ConfigError(RuntimeError):
    pass


class InvitationDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class InvitationDeliveryConfig:
    deployment_version: str
    delivery_provider: str
    provider_scheme: str
    raw_proof_ref: str
    proof_ref_scheme: str
    artifact_url: str
    artifact_url_host: str
    bearer_token: str | None
    timeout_seconds: float
    expected_statuses: tuple[str, ...]
    min_messages: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> InvitationDeliveryConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "invitation delivery proof."
            )
        delivery_provider = _required(env, "SEXTANT_INVITATION_DELIVERY_PROVIDER")
        provider_scheme = _validate_ref_scheme(
            "SEXTANT_INVITATION_DELIVERY_PROVIDER",
            delivery_provider,
            DELIVERY_PROVIDER_SCHEMES,
        )
        raw_proof_ref = _required(env, "SEXTANT_INVITATION_DELIVERY_PROOF_REF")
        proof_ref_scheme = _validate_ref_scheme(
            "SEXTANT_INVITATION_DELIVERY_PROOF_REF",
            raw_proof_ref,
            DELIVERY_PROOF_SCHEMES,
        )
        artifact_url = _artifact_url(env, raw_proof_ref, proof_ref_scheme)
        artifact_url_host = _validate_hosted_https_url(
            "SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL", artifact_url
        )
        return cls(
            deployment_version=_required(env, "SEXTANT_DEPLOYMENT_VERSION"),
            delivery_provider=delivery_provider,
            provider_scheme=provider_scheme,
            raw_proof_ref=raw_proof_ref,
            proof_ref_scheme=proof_ref_scheme,
            artifact_url=artifact_url,
            artifact_url_host=artifact_url_host,
            bearer_token=_optional(env, "SEXTANT_INVITATION_DELIVERY_BEARER_TOKEN"),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_INVITATION_DELIVERY_TIMEOUT_SECONDS", "10"),
                "SEXTANT_INVITATION_DELIVERY_TIMEOUT_SECONDS",
            ),
            expected_statuses=_expected_statuses(
                env.get("SEXTANT_INVITATION_DELIVERY_EXPECT_STATUSES", "sent,delivered,success")
            ),
            min_messages=_positive_int(
                env.get("SEXTANT_INVITATION_DELIVERY_MIN_MESSAGES", "1"),
                "SEXTANT_INVITATION_DELIVERY_MIN_MESSAGES",
            ),
        )


ArtifactFetcher = Callable[[InvitationDeliveryConfig], dict[str, object]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe hosted Sextant invitation delivery evidence."
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted invitation delivery configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = InvitationDeliveryConfig.from_env(dict(os.environ))
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if args.check_config:
        print("hosted-invitation-delivery-config-ok")
        return
    try:
        result = run_invitation_delivery_probe(config)
    except (InvitationDeliveryError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def run_invitation_delivery_probe(
    config: InvitationDeliveryConfig,
    *,
    artifact_fetcher: ArtifactFetcher | None = None,
) -> dict[str, object]:
    fetcher = artifact_fetcher or fetch_delivery_artifact
    artifact = fetcher(config)
    deployment_version = _field_text(artifact, "deployment_version")
    if deployment_version != config.deployment_version:
        raise InvitationDeliveryError(
            "Invitation delivery artifact reported deployment version "
            f"{deployment_version!r}; expected {config.deployment_version!r}."
        )
    provider = _field_text(artifact, "provider")
    if provider != config.delivery_provider:
        raise InvitationDeliveryError(
            "Invitation delivery artifact reported provider "
            f"{provider!r}; expected {config.delivery_provider!r}."
        )
    delivery_status = _field_text(artifact, "status").lower()
    if delivery_status not in config.expected_statuses:
        raise InvitationDeliveryError(
            "Invitation delivery artifact is not sent: "
            f"{delivery_status!r} not in {config.expected_statuses!r}."
        )
    message_count = _positive_artifact_int(artifact, "message_count")
    if message_count < config.min_messages:
        raise InvitationDeliveryError(
            "Invitation delivery artifact has "
            f"{message_count} message(s); expected at least {config.min_messages}."
        )
    return {
        "status": "pass",
        "deployment_version": deployment_version,
        "provider_scheme": config.provider_scheme,
        "provider_sha256": _sha256(config.delivery_provider),
        "delivery_status": delivery_status,
        "message_count": message_count,
        "artifact_url_host": config.artifact_url_host,
        "artifact_url_path_sha256": _sha256(urlparse(config.artifact_url).path or "/"),
        "artifact_sha256": _artifact_hash(artifact),
        "proof_ref_scheme": config.proof_ref_scheme,
        "proof_ref_sha256": _sha256(config.raw_proof_ref),
    }


def fetch_delivery_artifact(config: InvitationDeliveryConfig) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if config.bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    request = Request(config.artifact_url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"Invitation delivery probe failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError("Invitation delivery probe could not reach artifact URL.") from exc
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invitation delivery artifact did not return JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Invitation delivery artifact must be a JSON object.")
    return payload


def _artifact_url(env: Mapping[str, str], raw_proof_ref: str, proof_ref_scheme: str) -> str:
    configured = env.get("SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL", "").strip()
    if proof_ref_scheme == "https":
        return configured or raw_proof_ref
    if not configured:
        raise ConfigError(
            "SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL is required when "
            "SEXTANT_INVITATION_DELIVERY_PROOF_REF is not an HTTPS artifact URL."
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
        raise InvitationDeliveryError(
            f"Invitation delivery artifact field {field_name!r} must be text."
        )
    return value.strip()


def _positive_artifact_int(payload: Mapping[str, object], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or value < 0:
        raise InvitationDeliveryError(
            f"Invitation delivery artifact field {field_name!r} must be a non-negative integer."
        )
    return value


def _expected_statuses(value: str) -> tuple[str, ...]:
    statuses = tuple(part.strip().lower() for part in value.split(",") if part.strip())
    if not statuses:
        raise ConfigError("SEXTANT_INVITATION_DELIVERY_EXPECT_STATUSES must not be empty.")
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
        raise ConfigError(f"{name} is required for hosted invitation delivery proof.")
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
