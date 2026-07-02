from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_clean_context_acceptance_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location(
        "hosted_clean_context_acceptance_probe", SCRIPT_PATH
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
        "SEXTANT_DEPLOYMENT_URL": "https://app.sextant.example",
        "SEXTANT_DEPLOYMENT_VERSION": "2026.06.19+deploy",
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF": (
            "ci-artifact://prod/sextant/clean-context-ui/2026-06-19"
        ),
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL": (
            "https://ci.sextant.example/artifacts/clean-context-ui-2026-06-19.json"
        ),
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_TIMEOUT_SECONDS": "3",
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_MIN_STEPS": "8",
    }
    env.update(overrides)
    return env


def _passing_report() -> dict[str, object]:
    return {
        "deployment_url": "https://app.sextant.example",
        "deployment_version": "2026.06.19+deploy",
        "status": "pass",
        "reviewer_mode": "browser-computer-use",
        "used_final_built_app_ui": True,
        "source_inspection": False,
        "docs_inspection": False,
        "failures": [],
        "required_checks": {
            "project_source": True,
            "source_normalization": True,
            "selected_text": True,
            "candidate_request": True,
            "evidence_risk_avoided_claims": True,
            "partial_acceptance": True,
            "source_delta_span_evidence": True,
            "memory_writeback": True,
            "review_queue": True,
            "persistence_reload": True,
            "placeholder_check": True,
        },
        "steps": [
            "opened deployed app with private manuscript project",
            "loaded source and normalized view",
            "selected text",
            "requested candidate",
            "reviewed evidence and risk",
            "accepted partial text",
            "confirmed SourceDelta and SourceSpan",
            "confirmed memory writeback and review queue",
        ],
        "notes": "private manuscript title and reviewer identity stay out of evidence",
    }


def test_clean_context_acceptance_config_rejects_local_or_missing_artifact() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.CleanContextAcceptanceConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_DEPLOYMENT_URL"):
        probe.CleanContextAcceptanceConfig.from_env(_probe_env(SEXTANT_DEPLOYMENT_URL=""))

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(SEXTANT_DEPLOYMENT_URL="https://localhost:8443")
        )

    with pytest.raises(probe.ConfigError, match="auditable"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF="looks-good")
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(
                SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF=(
                    "ci-artifact://prod/sextant/clean-context-ui/2026-06-19?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="ARTIFACT_URL"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL="")
        )

    config = probe.CleanContextAcceptanceConfig.from_env(_probe_env())
    assert config.deployment_url == "https://app.sextant.example"
    assert config.deployment_version == "2026.06.19+deploy"
    assert config.proof_ref_scheme == "ci-artifact"
    assert config.artifact_url_host == "ci.sextant.example"

    https_config = probe.CleanContextAcceptanceConfig.from_env(
        _probe_env(
            SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF=(
                "https://ci.sextant.example/artifacts/clean-context-ui-2026-06-19.json"
            ),
            SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL="",
        )
    )
    assert https_config.artifact_url == https_config.raw_proof_ref
    assert https_config.proof_ref_scheme == "https"


def test_clean_context_acceptance_config_rejects_secret_bearing_artifact_urls() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(
                SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL=(
                    "https://ci.sextant.example/artifacts/clean-context-ui.json?token=secret"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="userinfo, params, query strings, or fragments"):
        probe.CleanContextAcceptanceConfig.from_env(
            _probe_env(
                SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF=(
                    "https://ci.sextant.example/artifacts/clean-context-ui.json?token=secret"
                ),
                SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL="",
            )
        )


def test_clean_context_acceptance_fetches_artifact_and_redacts_report() -> None:
    probe = _load_probe_module()
    config = probe.CleanContextAcceptanceConfig.from_env(
        _probe_env(SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_BEARER_TOKEN="secret-acceptance-token")
    )
    report = _passing_report()

    evidence = probe.run_clean_context_acceptance_probe(
        config, artifact_fetcher=lambda _config: report
    )
    rendered = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["deployment_url_host"] == "app.sextant.example"
    assert evidence["deployment_version"] == "2026.06.19+deploy"
    assert evidence["acceptance_status"] == "pass"
    assert evidence["reviewer_mode"] == "browser-computer-use"
    assert evidence["step_count"] == 8
    assert evidence["required_check_count"] == 11
    assert evidence["artifact_url_host"] == "ci.sextant.example"
    assert evidence["proof_ref_scheme"] == "ci-artifact"
    assert "secret-acceptance-token" not in rendered
    assert "private manuscript" not in rendered
    assert "reviewer identity" not in rendered
    assert config.raw_proof_ref not in rendered
    assert report["steps"][0] not in rendered


def test_clean_context_acceptance_fails_when_report_does_not_prove_browser_acceptance() -> None:
    probe = _load_probe_module()
    config = probe.CleanContextAcceptanceConfig.from_env(_probe_env())

    with pytest.raises(probe.CleanContextAcceptanceError, match="deployment URL"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_report(),
                "deployment_url": "https://other.sextant.example",
            },
        )

    with pytest.raises(probe.CleanContextAcceptanceError, match="deployment version"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_report(),
                "deployment_version": "2026.06.18+old",
            },
        )

    with pytest.raises(probe.CleanContextAcceptanceError, match="not passed"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_report(), "status": "fail"},
        )

    with pytest.raises(probe.CleanContextAcceptanceError, match="browser/computer-use"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_report(),
                "reviewer_mode": "source-code-review",
            },
        )

    with pytest.raises(probe.CleanContextAcceptanceError, match="source/docs inspection"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {**_passing_report(), "source_inspection": True},
        )

    with pytest.raises(probe.CleanContextAcceptanceError, match="failure entries"):
        probe.run_clean_context_acceptance_probe(
            config,
            artifact_fetcher=lambda _config: {
                **_passing_report(),
                "failures": ["review queue did not persist"],
            },
        )

    missing_required_check = _passing_report()
    required_checks = dict(missing_required_check["required_checks"])
    required_checks["review_queue"] = False
    missing_required_check["required_checks"] = required_checks
    with pytest.raises(probe.CleanContextAcceptanceError, match="review_queue"):
        probe.run_clean_context_acceptance_probe(
            config, artifact_fetcher=lambda _config: missing_required_check
        )

    short_report = _passing_report()
    short_report["steps"] = ["opened app"]
    with pytest.raises(probe.CleanContextAcceptanceError, match="walkthrough steps"):
        probe.run_clean_context_acceptance_probe(
            config, artifact_fetcher=lambda _config: short_report
        )


def test_clean_context_acceptance_check_config_cli() -> None:
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
            SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL="https://127.0.0.1/acceptance"
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-clean-context-acceptance-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
