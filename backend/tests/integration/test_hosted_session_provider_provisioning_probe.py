from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_session_provider_provisioning_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "hosted_session_provider_provisioning_probe", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_DEPLOYMENT_VERSION": "2026.06.19+deploy",
        "SEXTANT_SESSION_ISSUER": "https://auth.sextant.example/",
        "SEXTANT_SESSION_JWKS_URL": "https://auth.sextant.example/.well-known/jwks.json",
        "SEXTANT_SESSION_PROVIDER_ADMIN_URL": "https://auth.sextant.example/admin",
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": (
            "ci-artifact://prod/session-provider/2026-06-19"
        ),
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL": (
            "https://ci.sextant.example/artifacts/session-provider-2026-06-19.json"
        ),
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_TIMEOUT_SECONDS": "3",
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_MIN_CLIENTS": "1",
    }
    env.update(overrides)
    return env


def _passing_artifact() -> dict[str, object]:
    return {
        "deployment_version": "2026.06.19+deploy",
        "provider": "auth0",
        "issuer": "https://auth.sextant.example/",
        "jwks_url": "https://auth.sextant.example/.well-known/jwks.json",
        "admin_url": "https://auth.sextant.example/admin",
        "status": "provisioned",
        "client_count": 2,
        "tenant_id": "tenant-private-123",
        "client_ids": ["client-private-1", "client-private-2"],
        "notes": "private provisioning report",
    }


def test_session_provider_provisioning_config_rejects_local_or_missing_artifact() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.SessionProviderProvisioningConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_SESSION_PROVIDER_PROVISIONING"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF="session-ok")
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(
                SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=(
                    "https://localhost/session-provider"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(
                SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=(
                    "auth0://prod/sextant/session-provider?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(SEXTANT_SESSION_PROVIDER_ADMIN_URL="https://127.0.0.1/admin")
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL="")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.SessionProviderProvisioningConfig.from_env(
            _probe_env(
                SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL=(
                    "https://ci.sextant.example/artifacts/session-provider.json?token=secret"
                )
            )
        )

    config = probe.SessionProviderProvisioningConfig.from_env(_probe_env())
    assert config.deployment_version == "2026.06.19+deploy"
    assert config.issuer_host == "auth.sextant.example"
    assert config.proof_ref_scheme == "ci-artifact"
    assert config.artifact_url_host == "ci.sextant.example"

    https_config = probe.SessionProviderProvisioningConfig.from_env(
        _probe_env(
            SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=(
                "https://ci.sextant.example/artifacts/session-provider-2026-06-19.json"
            ),
            SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"


def test_session_provider_provisioning_fetches_artifact_and_redacts_private_details() -> None:
    probe = _load_probe_module()
    config = probe.SessionProviderProvisioningConfig.from_env(
        _probe_env(SEXTANT_SESSION_PROVIDER_PROVISIONING_BEARER_TOKEN="secret-provider-token")
    )
    artifact = _passing_artifact()

    evidence = probe.run_session_provider_provisioning_probe(
        config, artifact_fetcher=lambda _config: artifact
    )
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["provider"] == "auth0"
    assert evidence["issuer_host"] == "auth.sextant.example"
    assert evidence["provisioning_status"] == "provisioned"
    assert evidence["client_count"] == 2
    assert evidence["proof_ref_scheme"] == "ci-artifact"
    assert "secret-provider-token" not in rendered
    assert "tenant-private-123" not in rendered
    assert "client-private-1" not in rendered
    assert "client-private-2" not in rendered
    assert "private provisioning report" not in rendered
    assert config.raw_proof_ref not in rendered


def test_session_provider_provisioning_accepts_supabase_provider_artifact() -> None:
    probe = _load_probe_module()
    config = probe.SessionProviderProvisioningConfig.from_env(
        _probe_env(
            SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=("supabase://ientixxmbdeoqdmkublx/auth")
        )
    )
    artifact = {**_passing_artifact(), "provider": "supabase"}

    evidence = probe.run_session_provider_provisioning_probe(
        config, artifact_fetcher=lambda _config: artifact
    )

    assert evidence["status"] == "pass"
    assert evidence["provider"] == "supabase"
    assert evidence["proof_ref_scheme"] == "supabase"


def test_session_provider_provisioning_fails_when_artifact_does_not_match_config() -> None:
    probe = _load_probe_module()
    config = probe.SessionProviderProvisioningConfig.from_env(_probe_env())

    with pytest.raises(probe.SessionProviderProvisioningError, match="deployment version"):
        probe.run_session_provider_provisioning_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "deployment_version": "2026.06.18+old",
            },
        )

    with pytest.raises(probe.SessionProviderProvisioningError, match="issuer"):
        probe.run_session_provider_provisioning_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "issuer": "https://other-auth.sextant.example/",
            },
        )

    with pytest.raises(probe.SessionProviderProvisioningError, match="JWKS"):
        probe.run_session_provider_provisioning_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "jwks_url": "https://other-auth.sextant.example/jwks.json",
            },
        )

    with pytest.raises(probe.SessionProviderProvisioningError, match="not provisioned"):
        probe.run_session_provider_provisioning_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "status": "pending"},
        )

    with pytest.raises(probe.SessionProviderProvisioningError, match="client"):
        probe.run_session_provider_provisioning_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "client_count": 0},
        )


def test_session_provider_provisioning_check_config_cli() -> None:
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
        env=_probe_env(
            SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL=(
                "https://127.0.0.1/session-provider"
            )
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-session-provider-provisioning-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
