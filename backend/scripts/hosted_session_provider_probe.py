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

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
SESSION_PROVISIONING_PROOF_SCHEMES = {
    "runbook",
    "https",
    "ci-artifact",
    "auth0",
    "cognito",
    "okta",
    "clerk",
    "supabase",
}
INVITATION_DELIVERY_SCHEMES = {
    "ses",
    "sendgrid",
    "postmark",
    "mailgun",
    "smtp-tls",
    "supabase-auth",
}
INVITATION_DELIVERY_PROOF_SCHEMES = {
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
TOKEN_ISSUER_PROOF_SCHEMES = {
    "runbook",
    "https",
    "ci-artifact",
    "auth0",
    "cognito",
    "okta",
    "clerk",
    "supabase",
}


class ConfigError(RuntimeError):
    pass


class SessionProviderProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EndpointResponse:
    status_code: int
    body: bytes


@dataclass(frozen=True)
class SessionProviderProbeConfig:
    issuer: str
    audience: str
    jwks_url: str
    admin_url: str
    provisioning_proof_ref: str
    provisioning_proof_scheme: str
    invitation_delivery_provider: str
    invitation_delivery_scheme: str
    invitation_delivery_proof_ref: str
    invitation_delivery_proof_scheme: str
    token_issuer_proof_ref: str
    token_issuer_proof_scheme: str
    timeout_seconds: float
    admin_bearer_token: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SessionProviderProbeConfig:
        release_environment = _required(env, "SEXTANT_RELEASE_ENVIRONMENT")
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "session-provider readiness proof."
            )

        issuer = _required(env, "SEXTANT_SESSION_ISSUER")
        jwks_url = _required(env, "SEXTANT_SESSION_JWKS_URL")
        admin_url = _required(env, "SEXTANT_SESSION_PROVIDER_ADMIN_URL")
        _validate_hosted_https_url("SEXTANT_SESSION_ISSUER", issuer)
        _validate_hosted_https_url("SEXTANT_SESSION_JWKS_URL", jwks_url)
        _validate_hosted_https_url("SEXTANT_SESSION_PROVIDER_ADMIN_URL", admin_url)

        provisioning_ref = _required(env, "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF")
        invitation_provider = _required(env, "SEXTANT_INVITATION_DELIVERY_PROVIDER")
        invitation_delivery_ref = _required(env, "SEXTANT_INVITATION_DELIVERY_PROOF_REF")
        token_issuer_ref = _required(env, "SEXTANT_TOKEN_ISSUER_PROOF_REF")

        return cls(
            issuer=issuer,
            audience=_required(env, "SEXTANT_SESSION_AUDIENCE"),
            jwks_url=jwks_url,
            admin_url=admin_url,
            provisioning_proof_ref=provisioning_ref,
            provisioning_proof_scheme=_validate_ref_scheme(
                "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF",
                provisioning_ref,
                SESSION_PROVISIONING_PROOF_SCHEMES,
            ),
            invitation_delivery_provider=invitation_provider,
            invitation_delivery_scheme=_validate_ref_scheme(
                "SEXTANT_INVITATION_DELIVERY_PROVIDER",
                invitation_provider,
                INVITATION_DELIVERY_SCHEMES,
            ),
            invitation_delivery_proof_ref=invitation_delivery_ref,
            invitation_delivery_proof_scheme=_validate_ref_scheme(
                "SEXTANT_INVITATION_DELIVERY_PROOF_REF",
                invitation_delivery_ref,
                INVITATION_DELIVERY_PROOF_SCHEMES,
            ),
            token_issuer_proof_ref=token_issuer_ref,
            token_issuer_proof_scheme=_validate_ref_scheme(
                "SEXTANT_TOKEN_ISSUER_PROOF_REF",
                token_issuer_ref,
                TOKEN_ISSUER_PROOF_SCHEMES,
            ),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_SESSION_PROVIDER_PROBE_TIMEOUT_SECONDS", "10"),
                "SEXTANT_SESSION_PROVIDER_PROBE_TIMEOUT_SECONDS",
            ),
            admin_bearer_token=_optional(env, "SEXTANT_SESSION_PROVIDER_ADMIN_BEARER_TOKEN"),
        )


Fetcher = Callable[[str, SessionProviderProbeConfig], EndpointResponse]


def run_session_provider_probe(
    config: SessionProviderProbeConfig,
    *,
    fetcher: Fetcher | None = None,
) -> dict[str, object]:
    fetch = fetcher or fetch_endpoint
    jwks_response = fetch(config.jwks_url, config)
    admin_response = fetch(config.admin_url, config)

    jwks = _validate_jwks_response(jwks_response)
    _validate_admin_response(admin_response)
    kid_material = "\n".join(jwks["kids"]).encode("utf-8")

    return {
        "status": "pass",
        "issuer_host": _host(config.issuer),
        "jwks_host": _host(config.jwks_url),
        "admin_host": _host(config.admin_url),
        "audience_sha256": _sha256_text(config.audience),
        "jwks_status_code": jwks_response.status_code,
        "jwks_body_sha256": hashlib.sha256(jwks_response.body).hexdigest(),
        "jwks_key_count": jwks["key_count"],
        "jwks_kids_sha256": hashlib.sha256(kid_material).hexdigest(),
        "jwks_key_types": jwks["key_types"],
        "admin_status_code": admin_response.status_code,
        "admin_body_bytes": len(admin_response.body),
        "admin_body_sha256": hashlib.sha256(admin_response.body).hexdigest(),
        "provisioning_proof_scheme": config.provisioning_proof_scheme,
        "provisioning_proof_sha256": _sha256_text(config.provisioning_proof_ref),
        "invitation_delivery_scheme": config.invitation_delivery_scheme,
        "invitation_delivery_sha256": _sha256_text(config.invitation_delivery_provider),
        "invitation_delivery_proof_scheme": config.invitation_delivery_proof_scheme,
        "invitation_delivery_proof_sha256": _sha256_text(config.invitation_delivery_proof_ref),
        "token_issuer_proof_scheme": config.token_issuer_proof_scheme,
        "token_issuer_proof_sha256": _sha256_text(config.token_issuer_proof_ref),
    }


def fetch_endpoint(url: str, config: SessionProviderProbeConfig) -> EndpointResponse:
    headers = {"Accept": "application/json, text/html;q=0.8, text/plain;q=0.5"}
    if config.admin_bearer_token is not None:
        headers["Authorization"] = f"Bearer {config.admin_bearer_token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=config.timeout_seconds) as response:
            status_code = getattr(response, "status", response.getcode())
            return EndpointResponse(status_code=int(status_code), body=response.read())
    except HTTPError as exc:
        raise RuntimeError(f"Hosted session-provider endpoint returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(
            f"Hosted session-provider endpoint request failed: {exc.reason}"
        ) from exc


def _validate_jwks_response(response: EndpointResponse) -> dict[str, object]:
    if response.status_code < 200 or response.status_code >= 300:
        raise SessionProviderProbeError(
            f"Hosted session-provider JWKS response returned HTTP {response.status_code}."
        )
    if not response.body:
        raise SessionProviderProbeError("Hosted session-provider JWKS response is empty.")
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SessionProviderProbeError(
            "Hosted session-provider JWKS response is not JSON."
        ) from exc
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list) or not keys:
        raise SessionProviderProbeError("Hosted session-provider JWKS has no signing keys.")

    kids: list[str] = []
    key_types: set[str] = set()
    for key in keys:
        if not isinstance(key, dict):
            raise SessionProviderProbeError("Hosted session-provider JWKS key is malformed.")
        kid = str(key.get("kid", "")).strip()
        kty = str(key.get("kty", "")).strip()
        if not kid or not kty:
            raise SessionProviderProbeError(
                "Hosted session-provider JWKS keys must include kid and kty."
            )
        kids.append(kid)
        key_types.add(kty)

    return {
        "key_count": len(keys),
        "kids": sorted(kids),
        "key_types": sorted(key_types),
    }


def _validate_admin_response(response: EndpointResponse) -> None:
    if response.status_code < 200 or response.status_code >= 300:
        raise SessionProviderProbeError(
            f"Hosted session-provider admin response returned HTTP {response.status_code}."
        )
    if not response.body:
        raise SessionProviderProbeError("Hosted session-provider admin response is empty.")


def _validate_hosted_https_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            f"{name} must not include URL userinfo, params, query strings, or fragments."
        )
    if host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")


def _validate_ref_scheme(name: str, value: str, allowed_schemes: set[str]) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        allowed = ", ".join(sorted(f"{scheme}://" for scheme in allowed_schemes))
        raise ConfigError(f"{name} must use one of: {allowed}")
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            f"{name} must not include URL userinfo, params, query strings, or fragments."
        )
    if parsed.scheme == "https":
        _validate_hosted_https_url(name, value)
    return parsed.scheme


def _host(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").strip().rstrip(".").lower()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted session-provider probe.")
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe hosted session-provider JWKS and admin surfaces, then emit "
            "sanitized JSON readiness evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted session-provider configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = SessionProviderProbeConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-session-provider-config-ok")
            return 0
        print(json.dumps(run_session_provider_probe(config), sort_keys=True))
        return 0
    except (ConfigError, SessionProviderProbeError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
