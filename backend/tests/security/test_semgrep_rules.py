from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import certifi


def _semgrep_env(tmp_path: Path) -> dict[str, str]:
    semgrep_home = tmp_path / "semgrep"
    semgrep_home.mkdir()
    config_home = semgrep_home / "config"
    config_home.mkdir()
    ca_bundle = certifi.where()
    env = os.environ.copy()
    env.update(
        {
            "CURL_CA_BUNDLE": ca_bundle,
            "REQUESTS_CA_BUNDLE": ca_bundle,
            "SEMGREP_LOG_FILE": str(semgrep_home / "semgrep.log"),
            "SEMGREP_SETTINGS_FILE": str(semgrep_home / "settings.yaml"),
            "SEMGREP_VERSION_CACHE_PATH": str(semgrep_home / "version-cache"),
            "SSL_CERT_FILE": ca_bundle,
            "XDG_CONFIG_HOME": str(config_home),
        }
    )
    return env


def _rule_ids_for_fixture(path: str, tmp_path: Path) -> set[str]:
    result = subprocess.run(
        [
            "semgrep",
            "--config",
            ".semgrep/sextant.yml",
            path,
            "--json",
            "--quiet",
            "--metrics=off",
            "--disable-version-check",
        ],
        check=False,
        capture_output=True,
        env=_semgrep_env(tmp_path),
        text=True,
    )
    assert result.returncode == 0, (
        f"Semgrep fixture scan failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload = json.loads(result.stdout)
    return {finding["check_id"] for finding in payload["results"]}


def test_semgrep_direct_canon_write_rule_finds_fixture(tmp_path: Path) -> None:
    rule_ids = _rule_ids_for_fixture(".semgrep/fixtures/direct_canon_write.py", tmp_path)

    assert any(rule_id.endswith("sextant.no-direct-canon-fact-write") for rule_id in rule_ids)


def test_semgrep_graph_to_fact_write_rule_finds_fixture(tmp_path: Path) -> None:
    rule_ids = _rule_ids_for_fixture(".semgrep/fixtures/graph_to_fact_write.py", tmp_path)

    assert any(rule_id.endswith("sextant.no-graph-to-fact-write") for rule_id in rule_ids)


def test_semgrep_provider_to_memory_write_rule_finds_fixture(tmp_path: Path) -> None:
    rule_ids = _rule_ids_for_fixture(".semgrep/fixtures/provider_to_memory_write.py", tmp_path)

    assert any(rule_id.endswith("sextant.no-provider-to-memory-write") for rule_id in rule_ids)


def test_semgrep_provider_to_artifact_write_rule_finds_fixture(tmp_path: Path) -> None:
    rule_ids = _rule_ids_for_fixture(".semgrep/fixtures/provider_to_artifact_write.py", tmp_path)

    assert any(rule_id.endswith("sextant.no-provider-to-memory-write") for rule_id in rule_ids)
