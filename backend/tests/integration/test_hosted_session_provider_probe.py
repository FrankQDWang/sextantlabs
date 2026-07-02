from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_session_provider_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_session_provider_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_SESSION_ISSUER": "https://auth.sextant.example/",
        "SEXTANT_SESSION_AUDIENCE": "sextant-api",
        "SEXTANT_SESSION_JWKS_URL": "https://auth.sextant.example/.well-known/jwks.json",
        "SEXTANT_SESSION_PROVIDER_ADMIN_URL": "https://auth.sextant.example/admin",
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": (
            "auth0://prod/sextant/session-provider"
        ),
        "SEXTANT_INVITATION_DELIVERY_PROVIDER": "ses://prod/invitations",
        "SEXTANT_INVITATION_DELIVERY_PROOF_REF": "ci-artifact://prod/invitations/2026-06-19",
        "SEXTANT_TOKEN_ISSUER_PROOF_REF": "runbook://auth/token-issuer",
        "SEXTANT_SESSION_PROVIDER_PROBE_TIMEOUT_SECONDS": "3",
        "SEXTANT_SESSION_PROVIDER_ADMIN_BEARER_TOKEN": "admin-secret-token",
    }
    env.update(overrides)
    return env


def test_hosted_session_provider_config_rejects_non_production_local_or_invalid_refs() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT"):
        probe.SessionProviderProbeConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_SESSION_ISSUER"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_SESSION_ISSUER="https://localhost/issuer")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_SESSION_PROVIDER_ADMIN_URL"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_SESSION_PROVIDER_ADMIN_URL="https://127.0.0.1/admin")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_SESSION_PROVIDER_PROVISIONING"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF="session-ok")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(
                SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=(
                    "auth0://prod/sextant/session-provider?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_INVITATION_DELIVERY_PROVIDER"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_PROVIDER="local://mail")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_INVITATION_DELIVERY_PROOF_REF"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_PROOF_REF="https://localhost/mail-proof")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(
                SEXTANT_INVITATION_DELIVERY_PROOF_REF=(
                    "ci-artifact://prod/invitations/2026-06-19?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_TOKEN_ISSUER_PROOF_REF"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_TOKEN_ISSUER_PROOF_REF="https://localhost/token")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.SessionProviderProbeConfig.from_env(
            _probe_env(SEXTANT_TOKEN_ISSUER_PROOF_REF="runbook://auth/token-issuer?token=secret")
        )

    config = probe.SessionProviderProbeConfig.from_env(_probe_env())

    assert config.issuer == "https://auth.sextant.example/"
    assert config.audience == "sextant-api"
    assert config.provisioning_proof_scheme == "auth0"
    assert config.invitation_delivery_scheme == "ses"
    assert config.invitation_delivery_proof_scheme == "ci-artifact"
    assert config.token_issuer_proof_scheme == "runbook"
    assert config.admin_bearer_token == "admin-secret-token"


def test_hosted_session_provider_accepts_supabase_auth_invitation_delivery_refs() -> None:
    probe = _load_probe_module()

    config = probe.SessionProviderProbeConfig.from_env(
        _probe_env(
            SEXTANT_INVITATION_DELIVERY_PROVIDER=(
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email"
            ),
            SEXTANT_INVITATION_DELIVERY_PROOF_REF=(
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/2026-07-01"
            ),
        )
    )

    assert config.invitation_delivery_scheme == "supabase-auth"
    assert config.invitation_delivery_proof_scheme == "supabase-auth"


def test_hosted_session_provider_probe_fetches_jwks_and_admin_without_exposing_refs() -> None:
    probe = _load_probe_module()
    config = probe.SessionProviderProbeConfig.from_env(_probe_env())
    jwks_body = json.dumps(
        {
            "keys": [
                {
                    "kid": "kid-secret-1",
                    "kty": "RSA",
                    "use": "sig",
                    "n": "raw-modulus-secret",
                    "e": "AQAB",
                },
                {
                    "kid": "kid-secret-2",
                    "kty": "EC",
                    "use": "sig",
                    "crv": "P-256",
                    "x": "raw-x-secret",
                    "y": "raw-y-secret",
                },
            ]
        }
    ).encode()
    admin_body = b'{"tenant":"sextant","status":"ready","secret":"raw-admin-body"}'
    requested: list[tuple[str, str | None]] = []

    def fetcher(url: str, probe_config: object) -> object:
        requested.append((url, probe_config.admin_bearer_token))
        if url == config.jwks_url:
            return probe.EndpointResponse(status_code=200, body=jwks_body)
        if url == config.admin_url:
            return probe.EndpointResponse(status_code=200, body=admin_body)
        raise AssertionError(f"unexpected url {url}")

    evidence = probe.run_session_provider_probe(config, fetcher=fetcher)
    rendered = json.dumps(evidence, sort_keys=True)

    assert requested == [
        (config.jwks_url, "admin-secret-token"),
        (config.admin_url, "admin-secret-token"),
    ]
    assert evidence["status"] == "pass"
    assert evidence["issuer_host"] == "auth.sextant.example"
    assert evidence["jwks_key_count"] == 2
    assert evidence["jwks_kids_sha256"] == hashlib.sha256(b"kid-secret-1\nkid-secret-2").hexdigest()
    assert evidence["admin_status_code"] == 200
    assert evidence["admin_body_sha256"] == hashlib.sha256(admin_body).hexdigest()
    assert evidence["provisioning_proof_scheme"] == "auth0"
    assert evidence["invitation_delivery_scheme"] == "ses"
    assert evidence["invitation_delivery_proof_scheme"] == "ci-artifact"
    assert evidence["token_issuer_proof_scheme"] == "runbook"
    assert "admin-secret-token" not in rendered
    assert "raw-modulus-secret" not in rendered
    assert "raw-admin-body" not in rendered
    assert "auth0://prod/sextant/session-provider" not in rendered
    assert "ci-artifact://prod/invitations/2026-06-19" not in rendered
    assert "runbook://auth/token-issuer" not in rendered


def test_hosted_session_provider_probe_fails_on_missing_jwks_or_admin_evidence() -> None:
    probe = _load_probe_module()
    config = probe.SessionProviderProbeConfig.from_env(_probe_env())

    def missing_keys_fetcher(url: str, _config: object) -> object:
        if url == config.jwks_url:
            return probe.EndpointResponse(status_code=200, body=b'{"keys":[]}')
        return probe.EndpointResponse(status_code=200, body=b"admin ok")

    with pytest.raises(probe.SessionProviderProbeError, match="JWKS"):
        probe.run_session_provider_probe(config, fetcher=missing_keys_fetcher)

    def empty_admin_fetcher(url: str, _config: object) -> object:
        if url == config.jwks_url:
            return probe.EndpointResponse(
                status_code=200, body=b'{"keys":[{"kid":"k","kty":"RSA"}]}'
            )
        return probe.EndpointResponse(status_code=204, body=b"")

    with pytest.raises(probe.SessionProviderProbeError, match="admin"):
        probe.run_session_provider_probe(config, fetcher=empty_admin_fetcher)


def test_hosted_session_provider_check_config_cli() -> None:
    valid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    invalid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(SEXTANT_SESSION_JWKS_URL="https://localhost/.well-known/jwks.json"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-session-provider-config-ok"
    assert invalid.returncode == 1
    assert "SEXTANT_SESSION_JWKS_URL" in invalid.stderr
