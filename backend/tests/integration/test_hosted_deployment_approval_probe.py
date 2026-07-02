from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_deployment_approval_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_deployment_approval_probe", SCRIPT_PATH)
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
        "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF": ("change-request://prod/sextant/2026-06-19"),
        "SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL": (
            "https://change.sextant.example/prod/sextant/2026-06-19.json"
        ),
        "SEXTANT_DEPLOYMENT_APPROVAL_TIMEOUT_SECONDS": "3",
        "SEXTANT_DEPLOYMENT_APPROVAL_MIN_APPROVERS": "1",
    }
    env.update(overrides)
    return env


def test_hosted_deployment_approval_config_rejects_non_production_local_or_missing_artifact() -> (
    None
):
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.DeploymentApprovalConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_DEPLOYMENT_VERSION"):
        probe.DeploymentApprovalConfig.from_env(_probe_env(SEXTANT_DEPLOYMENT_VERSION=""))

    with pytest.raises(probe.ConfigError, match="auditable"):
        probe.DeploymentApprovalConfig.from_env(
            _probe_env(SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF="approval-ok")
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.DeploymentApprovalConfig.from_env(
            _probe_env(SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF="https://localhost/approval")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.DeploymentApprovalConfig.from_env(
            _probe_env(
                SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF=(
                    "change-request://prod/sextant/2026-06-19?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.DeploymentApprovalConfig.from_env(
            _probe_env(SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL="")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.DeploymentApprovalConfig.from_env(
            _probe_env(
                SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL=(
                    "https://change.sextant.example/prod/sextant/2026-06-19.json?token=secret"
                )
            )
        )

    config = probe.DeploymentApprovalConfig.from_env(_probe_env())

    assert config.deployment_version == "2026.06.19+deploy"
    assert config.proof_ref_scheme == "change-request"
    assert config.artifact_url == "https://change.sextant.example/prod/sextant/2026-06-19.json"
    assert config.artifact_url_host == "change.sextant.example"

    https_config = probe.DeploymentApprovalConfig.from_env(
        _probe_env(
            SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF=(
                "https://change.sextant.example/prod/sextant/2026-06-19.json"
            ),
            SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"


def test_hosted_deployment_approval_fetches_artifact_and_redacts_evidence() -> None:
    probe = _load_probe_module()
    config = probe.DeploymentApprovalConfig.from_env(
        _probe_env(SEXTANT_DEPLOYMENT_APPROVAL_BEARER_TOKEN="secret-approval-token")
    )
    artifact = {
        "deployment_version": "2026.06.19+deploy",
        "status": "approved",
        "approvers": ["release-manager@example.com", "security@example.com"],
        "notes": "approved with private manuscript incident context",
    }

    def fetcher(_config: object) -> dict[str, object]:
        return artifact

    evidence = probe.run_deployment_approval_probe(config, artifact_fetcher=fetcher)
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["approval_status"] == "approved"
    assert evidence["approver_count"] == 2
    assert evidence["artifact_url_host"] == "change.sextant.example"
    assert evidence["proof_ref_scheme"] == "change-request"
    assert "secret-approval-token" not in rendered
    assert "release-manager@example.com" not in rendered
    assert "security@example.com" not in rendered
    assert "private manuscript" not in rendered
    assert config.raw_proof_ref not in rendered


def test_hosted_deployment_approval_fails_on_wrong_version_or_unapproved_status() -> None:
    probe = _load_probe_module()
    config = probe.DeploymentApprovalConfig.from_env(_probe_env())

    with pytest.raises(probe.DeploymentApprovalError, match="deployment version"):
        probe.run_deployment_approval_probe(
            config,
            artifact_fetcher=lambda _config: {
                "deployment_version": "2026.06.18+old",
                "status": "approved",
                "approvers": ["release-manager@example.com"],
            },
        )

    with pytest.raises(probe.DeploymentApprovalError, match="approved"):
        probe.run_deployment_approval_probe(
            config,
            artifact_fetcher=lambda _config: {
                "deployment_version": "2026.06.19+deploy",
                "status": "pending",
                "approvers": ["release-manager@example.com"],
            },
        )

    with pytest.raises(probe.DeploymentApprovalError, match="approver"):
        probe.run_deployment_approval_probe(
            config,
            artifact_fetcher=lambda _config: {
                "deployment_version": "2026.06.19+deploy",
                "status": "approved",
                "approvers": [],
            },
        )


def test_hosted_deployment_approval_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL="https://127.0.0.1/approval"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-deployment-approval-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
