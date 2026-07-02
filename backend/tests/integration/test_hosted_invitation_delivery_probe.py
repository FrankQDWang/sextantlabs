from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_invitation_delivery_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_invitation_delivery_probe", SCRIPT_PATH)
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
        "SEXTANT_INVITATION_DELIVERY_PROVIDER": "ses://prod/invitations",
        "SEXTANT_INVITATION_DELIVERY_PROOF_REF": "ci-artifact://prod/invitations/2026-06-19",
        "SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL": (
            "https://ci.sextant.example/artifacts/invitation-delivery-2026-06-19.json"
        ),
        "SEXTANT_INVITATION_DELIVERY_TIMEOUT_SECONDS": "3",
        "SEXTANT_INVITATION_DELIVERY_MIN_MESSAGES": "1",
    }
    env.update(overrides)
    return env


def _passing_artifact() -> dict[str, object]:
    return {
        "deployment_version": "2026.06.19+deploy",
        "provider": "ses://prod/invitations",
        "status": "sent",
        "message_count": 3,
        "recipient_count": 3,
        "external_batch_id": "ses-batch-private-123",
        "recipients": ["author@example.com", "reviewer@example.com"],
        "notes": "private invitation copy and token details",
    }


def test_invitation_delivery_config_rejects_non_production_local_or_missing_artifact() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.InvitationDeliveryConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_INVITATION_DELIVERY_PROVIDER"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_PROVIDER="local://mail")
        )

    with pytest.raises(probe.ConfigError, match="SEXTANT_INVITATION_DELIVERY_PROOF_REF"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_PROOF_REF="delivery-ok")
        )

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_PROOF_REF="https://localhost/delivery")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(
                SEXTANT_INVITATION_DELIVERY_PROOF_REF=(
                    "ci-artifact://prod/invitations/2026-06-19?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL="")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.InvitationDeliveryConfig.from_env(
            _probe_env(
                SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL=(
                    "https://ci.sextant.example/artifacts/invitation-delivery.json?token=secret"
                )
            )
        )

    config = probe.InvitationDeliveryConfig.from_env(_probe_env())
    assert config.deployment_version == "2026.06.19+deploy"
    assert config.provider_scheme == "ses"
    assert config.proof_ref_scheme == "ci-artifact"
    assert config.artifact_url_host == "ci.sextant.example"

    https_config = probe.InvitationDeliveryConfig.from_env(
        _probe_env(
            SEXTANT_INVITATION_DELIVERY_PROOF_REF=(
                "https://ci.sextant.example/artifacts/invitation-delivery-2026-06-19.json"
            ),
            SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"


def test_invitation_delivery_accepts_supabase_auth_admin_invite_refs() -> None:
    probe = _load_probe_module()
    config = probe.InvitationDeliveryConfig.from_env(
        _probe_env(
            SEXTANT_INVITATION_DELIVERY_PROVIDER=(
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email"
            ),
            SEXTANT_INVITATION_DELIVERY_PROOF_REF=(
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/2026-07-01"
            ),
            SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL=(
                "https://app.sextant.example/readiness/invitation-delivery.json"
            ),
        )
    )
    artifact = {
        **_passing_artifact(),
        "provider": "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email",
        "message_count": 1,
    }

    evidence = probe.run_invitation_delivery_probe(
        config, artifact_fetcher=lambda _config: artifact
    )

    assert config.provider_scheme == "supabase-auth"
    assert config.proof_ref_scheme == "supabase-auth"
    assert evidence["status"] == "pass"
    assert evidence["provider_scheme"] == "supabase-auth"
    assert evidence["proof_ref_scheme"] == "supabase-auth"


def test_invitation_delivery_fetches_artifact_and_redacts_delivery_details() -> None:
    probe = _load_probe_module()
    config = probe.InvitationDeliveryConfig.from_env(
        _probe_env(SEXTANT_INVITATION_DELIVERY_BEARER_TOKEN="secret-delivery-token")
    )
    artifact = _passing_artifact()

    evidence = probe.run_invitation_delivery_probe(
        config, artifact_fetcher=lambda _config: artifact
    )
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["delivery_status"] == "sent"
    assert evidence["message_count"] == 3
    assert evidence["provider_scheme"] == "ses"
    assert evidence["artifact_url_host"] == "ci.sextant.example"
    assert evidence["proof_ref_scheme"] == "ci-artifact"
    assert "secret-delivery-token" not in rendered
    assert "author@example.com" not in rendered
    assert "reviewer@example.com" not in rendered
    assert "private invitation copy" not in rendered
    assert "ses-batch-private-123" not in rendered
    assert config.raw_proof_ref not in rendered


def test_invitation_delivery_fails_when_artifact_does_not_prove_delivery() -> None:
    probe = _load_probe_module()
    config = probe.InvitationDeliveryConfig.from_env(_probe_env())

    with pytest.raises(probe.InvitationDeliveryError, match="deployment version"):
        probe.run_invitation_delivery_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_artifact(),
                "deployment_version": "2026.06.18+old",
            },
        )

    with pytest.raises(probe.InvitationDeliveryError, match="provider"):
        probe.run_invitation_delivery_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "provider": "sendgrid://prod"},
        )

    with pytest.raises(probe.InvitationDeliveryError, match="not sent"):
        probe.run_invitation_delivery_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "status": "pending"},
        )

    with pytest.raises(probe.InvitationDeliveryError, match="message"):
        probe.run_invitation_delivery_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_artifact(), "message_count": 0},
        )


def test_invitation_delivery_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL="https://127.0.0.1/delivery"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-invitation-delivery-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
