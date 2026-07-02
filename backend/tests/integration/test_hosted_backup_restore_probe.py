from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_backup_restore_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_backup_restore_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_DATABASE_URL": (
            "postgresql+psycopg://sextant:secret@db.sextant.example:5432/sextant"
        ),
        "SEXTANT_BACKUP_RESTORE_DATABASE_URL": (
            "postgresql+psycopg://sextant:restore-secret@restore.sextant.example:5432/sextant_restore"
        ),
        "SEXTANT_BACKUP_TARGET": "s3://sextant-prod-backups/restore-probes",
        "SEXTANT_BACKUP_RESTORE_TIMEOUT_SECONDS": "30",
        "SEXTANT_BACKUP_RESTORE_MIN_SOURCE_DELTAS": "1",
        "SEXTANT_BACKUP_RESTORE_MIN_MEMORY_PAGES": "1",
        "SEXTANT_BACKUP_RESTORE_MIN_SOURCE_SPANS_WITH_RAW": "1",
    }
    env.update(overrides)
    return env


class _RecordingBackupStore:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}

    def upload_file(self, path: Path, object_name: str) -> str:
        payload = path.read_bytes()
        self.uploaded[object_name] = payload
        return f"s3://sextant-prod-backups/restore-probes/{object_name}"

    def download_file(self, ref: str, path: Path) -> None:
        object_name = ref.rsplit("/", 1)[-1]
        path.write_bytes(self.uploaded[object_name])


def test_hosted_backup_restore_config_rejects_non_production_or_local_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.BackupRestoreConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="hosted database host"):
        probe.BackupRestoreConfig.from_env(
            _probe_env(SEXTANT_DATABASE_URL="postgresql+psycopg://user:pass@localhost/db")
        )

    with pytest.raises(probe.ConfigError, match="restore database"):
        probe.BackupRestoreConfig.from_env(
            _probe_env(
                SEXTANT_BACKUP_RESTORE_DATABASE_URL=(
                    "postgresql+psycopg://sextant:secret@db.sextant.example:5432/sextant"
                )
            )
        )

    with pytest.raises(probe.ConfigError, match="s3://"):
        probe.BackupRestoreConfig.from_env(_probe_env(SEXTANT_BACKUP_TARGET="/tmp/backups"))

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.BackupRestoreConfig.from_env(
            _probe_env(SEXTANT_S3_ENDPOINT_URL="https://127.0.0.1:9000")
        )

    with pytest.raises(probe.ConfigError, match="positive number"):
        probe.BackupRestoreConfig.from_env(_probe_env(SEXTANT_BACKUP_RESTORE_TIMEOUT_SECONDS="0"))

    config = probe.BackupRestoreConfig.from_env(_probe_env())

    assert config.database_url.host == "db.sextant.example"
    assert config.database_url.cli_url == (
        "postgresql://sextant:secret@db.sextant.example:5432/sextant"
    )
    assert config.database_url.sanitized == (
        "postgresql+psycopg://sextant:***@db.sextant.example:5432/sextant"
    )
    assert config.restore_database_url.host == "restore.sextant.example"
    assert config.backup_target == "s3://sextant-prod-backups/restore-probes"
    assert config.timeout_seconds == 30.0


def test_hosted_backup_restore_runs_dump_upload_download_restore_and_redacts_evidence() -> None:
    probe = _load_probe_module()
    config = probe.BackupRestoreConfig.from_env(_probe_env())
    store = _RecordingBackupStore()
    dump_payload = b"-- sextant backup dump\nINSERT INTO source_deltas VALUES ('secret-text');\n"
    commands: list[tuple[str, ...]] = []

    def runner(args: tuple[str, ...], *, stdout_path: Path | None = None) -> object:
        commands.append(args)
        if args[0] == "pg_dump":
            assert stdout_path is not None
            stdout_path.write_bytes(dump_payload)
            return probe.CommandResult(stdout="")
        if args[0] == "psql" and "DROP EXTENSION" in args[-1]:
            return probe.CommandResult(stdout="")
        if args[0] == "psql" and "--file" in args:
            restore_path = Path(args[args.index("--file") + 1])
            assert restore_path.read_bytes() == dump_payload
            return probe.CommandResult(stdout="")
        if args[0] == "psql" and "source_deltas" in args[-1]:
            return probe.CommandResult(stdout="2\n")
        if args[0] == "psql" and "memory_pages" in args[-1]:
            return probe.CommandResult(stdout="3\n")
        if args[0] == "psql" and "source_spans restored_source_spans" in args[-1]:
            return probe.CommandResult(stdout="4\n")
        raise AssertionError(f"unexpected command: {args}")

    evidence = probe.run_backup_restore_probe(
        config,
        command_runner=runner,
        backup_store=store,
        probe_id=UUID("00000000-0000-4000-8000-0000000000bb"),
    )
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["backup_target"] == "s3://sextant-prod-backups/restore-probes"
    assert evidence["backup_object_ref"] == (
        "s3://sextant-prod-backups/restore-probes/"
        "hosted-readiness-backup-restore-00000000-0000-4000-8000-0000000000bb.sql"
    )
    assert evidence["backup_bytes"] == len(dump_payload)
    assert evidence["backup_sha256"] == hashlib.sha256(dump_payload).hexdigest()
    assert evidence["restored_source_deltas"] == 2
    assert evidence["restored_memory_pages"] == 3
    assert evidence["restored_source_spans_with_raw"] == 4
    assert commands[0][0] == "pg_dump"
    assert "--clean" in commands[0]
    assert "--if-exists" in commands[0]
    assert commands[0].count("--schema") == 1
    assert commands[0][commands[0].index("--schema") + 1] == "public"
    assert commands[0].count("--extension") == 2
    assert commands[0][commands[0].index("--extension") + 1] == "vector"
    assert "pg_trgm" in commands[0]
    assert any(
        command[0] == "psql" and "DROP EXTENSION" in command[-1] and "CASCADE" in command[-1]
        for command in commands
    )
    assert any(command[0] == "psql" and "--file" in command for command in commands)
    assert "secret" not in encoded
    assert "secret-text" not in encoded
    assert "restore-secret" not in encoded


def test_hosted_backup_restore_fails_when_restore_counts_do_not_prove_evidence_chain() -> None:
    probe = _load_probe_module()
    config = probe.BackupRestoreConfig.from_env(_probe_env())
    store = _RecordingBackupStore()

    def runner(args: tuple[str, ...], *, stdout_path: Path | None = None) -> object:
        if args[0] == "pg_dump":
            assert stdout_path is not None
            stdout_path.write_text("-- empty backup\n", encoding="utf-8")
        return probe.CommandResult(stdout="0\n")

    with pytest.raises(probe.BackupRestoreError, match="SourceDelta"):
        probe.run_backup_restore_probe(config, command_runner=runner, backup_store=store)


def test_hosted_backup_restore_check_config_cli() -> None:
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
        env=_probe_env(SEXTANT_BACKUP_TARGET="./backups"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-backup-restore-config-ok"
    assert invalid.returncode == 1
    assert "s3://" in invalid.stderr
