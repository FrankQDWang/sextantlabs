from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_object_store_iam_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_object_store_iam_probe", SCRIPT_PATH)
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
        "SEXTANT_OBJECT_STORE_ROOT": "s3://sextant-prod/objects",
        "SEXTANT_OBJECT_STORE_IAM_PROOF_REF": "aws-iam://prod/sextant-object-store",
        "SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL": (
            "https://ci.sextant.example/artifacts/object-store-iam-2026-06-19.json"
        ),
        "SEXTANT_OBJECT_STORE_IAM_TIMEOUT_SECONDS": "3",
        "SEXTANT_OBJECT_STORE_IAM_MIN_POLICY_STATEMENTS": "1",
        "SEXTANT_OBJECT_STORE_IAM_MIN_RUNTIME_PRINCIPALS": "1",
    }
    env.update(overrides)
    return env


def _passing_artifact() -> dict[str, object]:
    return {
        "deployment_version": "2026.06.19+deploy",
        "provider": "aws-iam",
        "object_store_root": "s3://sextant-prod/objects",
        "status": "attached",
        "policy_statement_count": 3,
        "runtime_principal_count": 2,
        "allowed_actions": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
        "principal_arns": [
            "arn:aws:iam::123456789012:role/sextant-api-prod",
            "arn:aws:iam::123456789012:role/sextant-worker-prod",
        ],
        "policy_document": {"Statement": [{"Effect": "Allow", "Resource": "*"}]},
        "account_id": "123456789012",
        "private_notes": "operator-only IAM attachment details",
    }


def test_object_store_iam_config_rejects_local_or_missing_artifact() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.ObjectStoreIamConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="s3://"):
        probe.ObjectStoreIamConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_ROOT="./objects"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_OBJECT_STORE_IAM_PROOF_REF"):
        probe.ObjectStoreIamConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_IAM_PROOF_REF="iam-ok"))

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.ObjectStoreIamConfig.from_env(
            _probe_env(SEXTANT_OBJECT_STORE_IAM_PROOF_REF="https://localhost/iam")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.ObjectStoreIamConfig.from_env(
            _probe_env(SEXTANT_OBJECT_STORE_IAM_PROOF_REF="aws-iam://prod/iam?token=secret")
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.ObjectStoreIamConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL=""))

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.ObjectStoreIamConfig.from_env(
            _probe_env(
                SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL=(
                    "https://ci.sextant.example/artifacts/object-store-iam.json?token=secret"
                )
            )
        )

    config = probe.ObjectStoreIamConfig.from_env(_probe_env())
    assert config.deployment_version == "2026.06.19+deploy"
    assert config.object_store_root == "s3://sextant-prod/objects"
    assert config.proof_ref_scheme == "aws-iam"
    assert config.artifact_url_host == "ci.sextant.example"

    https_config = probe.ObjectStoreIamConfig.from_env(
        _probe_env(
            SEXTANT_OBJECT_STORE_IAM_PROOF_REF=(
                "https://ci.sextant.example/artifacts/object-store-iam-2026-06-19.json"
            ),
            SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"


def test_object_store_iam_fetches_artifact_and_redacts_private_details() -> None:
    probe = _load_probe_module()
    config = probe.ObjectStoreIamConfig.from_env(
        _probe_env(SEXTANT_OBJECT_STORE_IAM_BEARER_TOKEN="secret-iam-token")
    )
    artifact = _passing_artifact()

    evidence = probe.run_object_store_iam_probe(config, artifact_fetcher=lambda _config: artifact)
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["provider"] == "aws-iam"
    assert evidence["iam_status"] == "attached"
    assert evidence["policy_statement_count"] == 3
    assert evidence["runtime_principal_count"] == 2
    assert evidence["proof_ref_scheme"] == "aws-iam"
    assert "secret-iam-token" not in rendered
    assert "123456789012" not in rendered
    assert "sextant-api-prod" not in rendered
    assert "sextant-worker-prod" not in rendered
    assert "operator-only IAM attachment details" not in rendered
    assert "s3:PutObject" not in rendered
    assert config.raw_proof_ref not in rendered


def test_object_store_iam_accepts_cloudflare_r2_artifact() -> None:
    probe = _load_probe_module()
    config = probe.ObjectStoreIamConfig.from_env(
        _probe_env(
            SEXTANT_OBJECT_STORE_ROOT="s3://sextant-prod-wnam-objects/objects",
            SEXTANT_OBJECT_STORE_IAM_PROOF_REF=(
                "cloudflare-r2://sextant-prod-wnam-objects/runtime-token"
            ),
        )
    )
    artifact = {
        **_passing_artifact(),
        "provider": "cloudflare-r2",
        "object_store_root": "s3://sextant-prod-wnam-objects/objects",
        "policy_statement_count": 1,
        "runtime_principal_count": 1,
    }

    evidence = probe.run_object_store_iam_probe(config, artifact_fetcher=lambda _config: artifact)

    assert evidence["status"] == "pass"
    assert evidence["provider"] == "cloudflare-r2"
    assert evidence["proof_ref_scheme"] == "cloudflare-r2"


def test_object_store_iam_fails_when_artifact_does_not_match_config() -> None:
    probe = _load_probe_module()
    config = probe.ObjectStoreIamConfig.from_env(_probe_env())

    with pytest.raises(probe.ObjectStoreIamError, match="deployment version"):
        probe.run_object_store_iam_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "deployment_version": "2026.06.18+old",
            },
        )

    with pytest.raises(probe.ObjectStoreIamError, match="object-store root"):
        probe.run_object_store_iam_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "object_store_root": "s3://other-prod/objects",
            },
        )

    with pytest.raises(probe.ObjectStoreIamError, match="not ready"):
        probe.run_object_store_iam_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "status": "pending"},
        )

    with pytest.raises(probe.ObjectStoreIamError, match="policy"):
        probe.run_object_store_iam_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "policy_statement_count": 0,
            },
        )

    with pytest.raises(probe.ObjectStoreIamError, match="principal"):
        probe.run_object_store_iam_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "runtime_principal_count": 0,
            },
        )


def test_object_store_iam_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL="https://127.0.0.1/iam"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-object-store-iam-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
