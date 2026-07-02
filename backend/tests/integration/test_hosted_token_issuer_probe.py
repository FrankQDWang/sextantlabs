from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_token_issuer_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_token_issuer_probe", SCRIPT_PATH)
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
        "SEXTANT_SESSION_AUDIENCE": "sextant-api",
        "SEXTANT_TOKEN_ISSUER_PROOF_REF": "ci-artifact://prod/token-issuer/2026-06-19",
        "SEXTANT_TOKEN_ISSUER_ARTIFACT_URL": (
            "https://ci.sextant.example/artifacts/token-issuer-2026-06-19.json"
        ),
        "SEXTANT_TOKEN_ISSUER_TIMEOUT_SECONDS": "3",
        "SEXTANT_TOKEN_ISSUER_MIN_TOKENS": "1",
    }
    env.update(overrides)
    return env


def _passing_artifact() -> dict[str, object]:
    return {
        "deployment_version": "2026.06.19+deploy",
        "issuer": "https://auth.sextant.example/",
        "audience": "sextant-api",
        "status": "issued",
        "token_count": 2,
        "subject_count": 2,
        "subjects": ["author@example.com", "editor@example.com"],
        "sample_token": "eyJ.private.jwt.material",
        "external_batch_id": "auth0-private-batch-123",
        "notes": "private token issuance report",
    }


def test_token_issuer_config_rejects_non_production_local_or_missing_artifact() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.TokenIssuerConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_TOKEN_ISSUER_PROOF_REF"):
        probe.TokenIssuerConfig.from_env(_probe_env(SEXTANT_TOKEN_ISSUER_PROOF_REF="token-ok"))

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.TokenIssuerConfig.from_env(
            _probe_env(SEXTANT_TOKEN_ISSUER_PROOF_REF="https://localhost/token")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.TokenIssuerConfig.from_env(
            _probe_env(
                SEXTANT_TOKEN_ISSUER_PROOF_REF=(
                    "ci-artifact://prod/token-issuer/2026-06-19?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.TokenIssuerConfig.from_env(
            _probe_env(SEXTANT_SESSION_ISSUER="https://127.0.0.1/issuer")
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.TokenIssuerConfig.from_env(_probe_env(SEXTANT_TOKEN_ISSUER_ARTIFACT_URL=""))

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.TokenIssuerConfig.from_env(
            _probe_env(
                SEXTANT_TOKEN_ISSUER_ARTIFACT_URL=(
                    "https://ci.sextant.example/artifacts/token-issuer.json?token=secret"
                )
            )
        )

    config = probe.TokenIssuerConfig.from_env(_probe_env())
    assert config.deployment_version == "2026.06.19+deploy"
    assert config.issuer_host == "auth.sextant.example"
    assert config.proof_ref_scheme == "ci-artifact"
    assert config.artifact_url_host == "ci.sextant.example"

    https_config = probe.TokenIssuerConfig.from_env(
        _probe_env(
            SEXTANT_TOKEN_ISSUER_PROOF_REF=(
                "https://ci.sextant.example/artifacts/token-issuer-2026-06-19.json"
            ),
            SEXTANT_TOKEN_ISSUER_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"

    supabase_config = probe.TokenIssuerConfig.from_env(
        _probe_env(SEXTANT_TOKEN_ISSUER_PROOF_REF="supabase://ientixxmbdeoqdmkublx/auth")
    )
    assert supabase_config.proof_ref_scheme == "supabase"


def test_token_issuer_fetches_artifact_and_redacts_token_material() -> None:
    probe = _load_probe_module()
    config = probe.TokenIssuerConfig.from_env(
        _probe_env(SEXTANT_TOKEN_ISSUER_BEARER_TOKEN="secret-token-artifact-bearer")
    )
    artifact = _passing_artifact()

    evidence = probe.run_token_issuer_probe(config, artifact_fetcher=lambda _config: artifact)
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["issuer_host"] == "auth.sextant.example"
    assert evidence["issuance_status"] == "issued"
    assert evidence["token_count"] == 2
    assert evidence["subject_count"] == 2
    assert evidence["proof_ref_scheme"] == "ci-artifact"
    assert "secret-token-artifact-bearer" not in rendered
    assert "author@example.com" not in rendered
    assert "editor@example.com" not in rendered
    assert "eyJ.private.jwt.material" not in rendered
    assert "auth0-private-batch-123" not in rendered
    assert "private token issuance report" not in rendered
    assert config.raw_proof_ref not in rendered


def test_token_issuer_fails_when_artifact_does_not_prove_issuance() -> None:
    probe = _load_probe_module()
    config = probe.TokenIssuerConfig.from_env(_probe_env())

    with pytest.raises(probe.TokenIssuerError, match="deployment version"):
        probe.run_token_issuer_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "deployment_version": "2026.06.18+old",
            },
        )

    with pytest.raises(probe.TokenIssuerError, match="issuer"):
        probe.run_token_issuer_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "issuer": "https://other-auth.sextant.example/",
            },
        )

    with pytest.raises(probe.TokenIssuerError, match="audience"):
        probe.run_token_issuer_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "audience": "other-api"},
        )

    with pytest.raises(probe.TokenIssuerError, match="not issued"):
        probe.run_token_issuer_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "status": "pending"},
        )

    with pytest.raises(probe.TokenIssuerError, match="token"):
        probe.run_token_issuer_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "token_count": 0},
        )


def test_token_issuer_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_TOKEN_ISSUER_ARTIFACT_URL="https://127.0.0.1/token"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-token-issuer-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
