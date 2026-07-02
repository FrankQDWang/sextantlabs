from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_secret_manager_probe.py")


class _RecordingSecretResolver:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.refs: list[str] = []

    def read_secret(self, ref: str) -> str:
        self.refs.append(ref)
        return self.secret


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_secret_manager_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_SECRET_MANAGER_REF": (
            "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY"
        ),
    }
    env.update(overrides)
    return env


def test_hosted_secret_manager_config_rejects_non_production_or_local_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.SecretManagerProbeConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_SECRET_MANAGER_REF"):
        probe.SecretManagerProbeConfig.from_env(_probe_env(SEXTANT_SECRET_MANAGER_REF=""))

    with pytest.raises(probe.ConfigError, match="aws-secretsmanager"):
        probe.SecretManagerProbeConfig.from_env(
            _probe_env(SEXTANT_SECRET_MANAGER_REF="secret://prod/openai")
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS"):
        probe.SecretManagerProbeConfig.from_env(
            _probe_env(
                SEXTANT_SECRET_MANAGER_REF=(
                    "vault://localhost/secret/data/sextant/openai?field=OPENAI_API_KEY"
                )
            )
        )

    config = probe.SecretManagerProbeConfig.from_env(_probe_env())

    assert config.secret_ref_scheme == "aws-secretsmanager"
    assert config.secret_ref == (
        "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY"
    )


def test_hosted_secret_manager_probe_reads_without_exposing_secret() -> None:
    probe = _load_probe_module()
    config = probe.SecretManagerProbeConfig.from_env(_probe_env())
    resolver = _RecordingSecretResolver("sk-live-secret-value")

    evidence = probe.run_secret_manager_probe(config, resolver=resolver)
    encoded = json.dumps(evidence, sort_keys=True)

    assert resolver.refs == [config.secret_ref]
    assert evidence["status"] == "pass"
    assert evidence["secret_ref_scheme"] == "aws-secretsmanager"
    assert evidence["secret_value_status"] == "resolved_non_empty"
    assert "secret_ref_sha256" not in evidence
    assert "secret_value_byte_count" not in evidence
    assert "sk-live-secret-value" not in encoded
    assert "prod/sextant/openai" not in encoded


def test_hosted_secret_manager_probe_accepts_supabase_vault_ref_without_exposing_name() -> None:
    probe = _load_probe_module()
    config = probe.SecretManagerProbeConfig.from_env(
        _probe_env(
            SEXTANT_SECRET_MANAGER_REF=(
                "supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key"
            )
        )
    )
    resolver = _RecordingSecretResolver("sk-live-secret-value")

    evidence = probe.run_secret_manager_probe(config, resolver=resolver)
    encoded = json.dumps(evidence, sort_keys=True)

    assert resolver.refs == [config.secret_ref]
    assert evidence["status"] == "pass"
    assert evidence["secret_ref_scheme"] == "supabase-vault"
    assert evidence["secret_value_status"] == "resolved_non_empty"
    assert "secret_ref_sha256" not in evidence
    assert "secret_value_byte_count" not in evidence
    assert "sk-live-secret-value" not in encoded
    assert "sextant_openai_api_key" not in encoded


def test_hosted_secret_manager_probe_cli_evidence_is_constant_redacted() -> None:
    probe = _load_probe_module()

    evidence = json.loads(probe.render_secret_manager_probe_cli_evidence())

    assert evidence == {
        "secret_manager_access": "verified",
        "status": "pass",
    }


def test_hosted_secret_manager_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_SECRET_MANAGER_REF="vault://127.0.0.1/kv/app?field=key"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-secret-manager-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS" in invalid.stderr
