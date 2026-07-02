from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, quote, urlparse, urlsplit, urlunsplit
from uuid import UUID, uuid4

LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
DEFAULT_PROBE_PREFIX = "hosted-readiness-backup-restore"

SOURCE_DELTA_COUNT_SQL = "SELECT count(*) FROM source_deltas;"
MEMORY_PAGE_COUNT_SQL = "SELECT count(*) FROM memory_pages;"
SOURCE_SPAN_RAW_COUNT_SQL = """
SELECT count(*)
FROM source_spans restored_source_spans
JOIN source_raw_sources restored_raw_sources
  ON restored_raw_sources.id = restored_source_spans.source_id
JOIN source_versions restored_source_versions
  ON restored_source_versions.id = restored_source_spans.version_id
 AND restored_source_versions.source_id = restored_raw_sources.id
WHERE restored_source_spans.text_preview IS NOT NULL
  AND restored_raw_sources.raw_text_ref IS NOT NULL;
"""


class ConfigError(RuntimeError):
    pass


class BackupRestoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommandResult:
    stdout: str


@dataclass(frozen=True)
class DatabaseUrl:
    raw: str
    cli_url: str
    scheme: str
    host: str
    sanitized: str


@dataclass(frozen=True)
class BackupTarget:
    raw: str
    bucket: str
    prefix: str


@dataclass(frozen=True)
class RequiredExtension:
    name: str
    schema: str


@dataclass(frozen=True)
class BackupRestoreConfig:
    database_url: DatabaseUrl
    restore_database_url: DatabaseUrl
    backup_target: str
    backup_target_ref: BackupTarget
    probe_prefix: str
    timeout_seconds: float
    min_source_deltas: int
    min_memory_pages: int
    min_source_spans_with_raw: int
    s3_endpoint_url: str | None
    schemas: tuple[str, ...]
    required_extensions: tuple[RequiredExtension, ...]

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> BackupRestoreConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "backup/restore proof."
            )
        database_url = _database_url_from_env(env, "SEXTANT_DATABASE_URL")
        restore_database_url = _database_url_from_env(env, "SEXTANT_BACKUP_RESTORE_DATABASE_URL")
        if _same_database_target(database_url, restore_database_url):
            raise ConfigError(
                "SEXTANT_BACKUP_RESTORE_DATABASE_URL restore database must be a "
                "separate scratch database."
            )
        backup_target = _required(env, "SEXTANT_BACKUP_TARGET")
        backup_target_ref = _backup_target_from_uri(backup_target)
        s3_endpoint_url = env.get("SEXTANT_S3_ENDPOINT_URL", "").strip() or None
        if s3_endpoint_url is not None:
            _validate_hosted_https_url("SEXTANT_S3_ENDPOINT_URL", s3_endpoint_url)
        return cls(
            database_url=database_url,
            restore_database_url=restore_database_url,
            backup_target=backup_target,
            backup_target_ref=backup_target_ref,
            probe_prefix=_safe_prefix(
                env.get("SEXTANT_BACKUP_RESTORE_PROBE_PREFIX", DEFAULT_PROBE_PREFIX)
            ),
            timeout_seconds=_positive_float(
                env.get("SEXTANT_BACKUP_RESTORE_TIMEOUT_SECONDS", "600"),
                "SEXTANT_BACKUP_RESTORE_TIMEOUT_SECONDS",
            ),
            min_source_deltas=_positive_int(
                env.get("SEXTANT_BACKUP_RESTORE_MIN_SOURCE_DELTAS", "1"),
                "SEXTANT_BACKUP_RESTORE_MIN_SOURCE_DELTAS",
            ),
            min_memory_pages=_positive_int(
                env.get("SEXTANT_BACKUP_RESTORE_MIN_MEMORY_PAGES", "1"),
                "SEXTANT_BACKUP_RESTORE_MIN_MEMORY_PAGES",
            ),
            min_source_spans_with_raw=_positive_int(
                env.get("SEXTANT_BACKUP_RESTORE_MIN_SOURCE_SPANS_WITH_RAW", "1"),
                "SEXTANT_BACKUP_RESTORE_MIN_SOURCE_SPANS_WITH_RAW",
            ),
            s3_endpoint_url=s3_endpoint_url,
            schemas=_schemas(env.get("SEXTANT_BACKUP_RESTORE_SCHEMAS", "public")),
            required_extensions=_required_extensions(
                env.get(
                    "SEXTANT_BACKUP_RESTORE_REQUIRED_EXTENSIONS",
                    "vector:public,pg_trgm:public",
                )
            ),
        )


class S3BackupStore:
    def __init__(self, target: BackupTarget, *, endpoint_url: str | None = None) -> None:
        self._target = target
        self._client = _create_s3_client(endpoint_url)

    def upload_file(self, path: Path, object_name: str) -> str:
        key = _target_key(self._target.prefix, object_name)
        self._client.upload_file(str(path), self._target.bucket, key)
        return f"s3://{self._target.bucket}/{quote(key, safe='/')}"

    def download_file(self, ref: str, path: Path) -> None:
        parsed = urlparse(ref)
        if parsed.scheme != "s3" or parsed.netloc != self._target.bucket:
            raise BackupRestoreError("Backup object ref is outside configured backup target.")
        key = parsed.path.lstrip("/")
        if self._target.prefix and not (
            key == self._target.prefix or key.startswith(f"{self._target.prefix}/")
        ):
            raise BackupRestoreError("Backup object ref is outside configured backup target.")
        self._client.download_file(self._target.bucket, key, str(path))


CommandRunner = Callable[[tuple[str, ...]], CommandResult]


def run_backup_restore_probe(
    config: BackupRestoreConfig,
    *,
    command_runner: Callable[[tuple[str, ...]], CommandResult] | None = None,
    backup_store: object | None = None,
    probe_id: UUID | None = None,
) -> dict[str, object]:
    resolved_probe_id = probe_id or uuid4()
    object_name = f"{config.probe_prefix}-{resolved_probe_id}.sql"
    runner = command_runner or _subprocess_runner(config)
    store = backup_store or S3BackupStore(
        config.backup_target_ref, endpoint_url=config.s3_endpoint_url
    )

    with tempfile.TemporaryDirectory(prefix="sextant-hosted-backup-restore-") as temp_dir:
        temp_path = Path(temp_dir)
        dump_path = temp_path / "backup.sql"
        downloaded_path = temp_path / "downloaded-backup.sql"

        runner(_pg_dump_command(config), stdout_path=dump_path)  # type: ignore[misc]
        backup_bytes = dump_path.read_bytes()
        backup_object_ref = store.upload_file(dump_path, object_name)
        store.download_file(backup_object_ref, downloaded_path)
        downloaded_bytes = downloaded_path.read_bytes()
        if downloaded_bytes != backup_bytes:
            raise BackupRestoreError("Downloaded backup payload does not match uploaded dump.")

        if config.required_extensions:
            runner(_psql_prepare_restore_command(config))
        runner(_psql_restore_command(config, downloaded_path))  # type: ignore[misc]
        restored_source_deltas = _run_count(runner, config, SOURCE_DELTA_COUNT_SQL)
        restored_memory_pages = _run_count(runner, config, MEMORY_PAGE_COUNT_SQL)
        restored_source_spans_with_raw = _run_count(runner, config, SOURCE_SPAN_RAW_COUNT_SQL)

    _validate_minimums(
        config,
        restored_source_deltas=restored_source_deltas,
        restored_memory_pages=restored_memory_pages,
        restored_source_spans_with_raw=restored_source_spans_with_raw,
    )

    return {
        "status": "pass",
        "database_host": config.database_url.host,
        "database_url": config.database_url.sanitized,
        "restore_database_host": config.restore_database_url.host,
        "restore_database_url": config.restore_database_url.sanitized,
        "backup_target": config.backup_target,
        "backup_object_ref": backup_object_ref,
        "backup_bytes": len(backup_bytes),
        "backup_sha256": hashlib.sha256(backup_bytes).hexdigest(),
        "restored_source_deltas": restored_source_deltas,
        "restored_memory_pages": restored_memory_pages,
        "restored_source_spans_with_raw": restored_source_spans_with_raw,
        "s3_endpoint_host": urlparse(config.s3_endpoint_url).hostname
        if config.s3_endpoint_url
        else None,
    }


def _subprocess_runner(
    config: BackupRestoreConfig,
) -> Callable[[tuple[str, ...]], CommandResult]:
    def run(args: tuple[str, ...], *, stdout_path: Path | None = None) -> CommandResult:
        stdout_target = subprocess.PIPE
        opened_stdout = None
        text = True
        if stdout_path is not None:
            opened_stdout = stdout_path.open("wb")
            stdout_target = opened_stdout
            text = False
        try:
            completed = subprocess.run(
                args,
                stdout=stdout_target,
                stderr=subprocess.PIPE,
                check=False,
                timeout=config.timeout_seconds,
                text=text,
            )
        finally:
            if opened_stdout is not None:
                opened_stdout.close()
        if completed.returncode != 0:
            raise BackupRestoreError(
                f"Hosted backup/restore command {args[0]} failed with exit "
                f"code {completed.returncode}."
            )
        stdout = completed.stdout if isinstance(completed.stdout, str) else ""
        return CommandResult(stdout=stdout)

    return run


def _pg_dump_command(config: BackupRestoreConfig) -> tuple[str, ...]:
    command = [
        "pg_dump",
        "--dbname",
        config.database_url.cli_url,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
    ]
    for schema in config.schemas:
        command.extend(("--schema", schema))
    for extension in config.required_extensions:
        command.extend(("--extension", extension.name))
    return tuple(command)


def _psql_restore_command(config: BackupRestoreConfig, backup_path: Path) -> tuple[str, ...]:
    return (
        "psql",
        "--dbname",
        config.restore_database_url.cli_url,
        "-v",
        "ON_ERROR_STOP=1",
        "--file",
        str(backup_path),
    )


def _psql_prepare_restore_command(config: BackupRestoreConfig) -> tuple[str, ...]:
    statements = [
        f"DROP EXTENSION IF EXISTS {_quote_identifier(extension.name)} CASCADE;"
        for extension in config.required_extensions
    ]
    return (
        "psql",
        "--dbname",
        config.restore_database_url.cli_url,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "\n".join(statements),
    )


def _psql_count_command(config: BackupRestoreConfig, sql: str) -> tuple[str, ...]:
    return (
        "psql",
        "--dbname",
        config.restore_database_url.cli_url,
        "-v",
        "ON_ERROR_STOP=1",
        "-At",
        "-c",
        sql,
    )


def _run_count(
    runner: Callable[[tuple[str, ...]], CommandResult],
    config: BackupRestoreConfig,
    sql: str,
) -> int:
    result = runner(_psql_count_command(config, sql))
    raw_value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    try:
        return int(raw_value)
    except ValueError as exc:
        raise BackupRestoreError("Hosted restore count query returned non-integer output.") from exc


def _validate_minimums(
    config: BackupRestoreConfig,
    *,
    restored_source_deltas: int,
    restored_memory_pages: int,
    restored_source_spans_with_raw: int,
) -> None:
    if restored_source_deltas < config.min_source_deltas:
        raise BackupRestoreError(
            "Hosted restore did not prove restored SourceDelta rows: "
            f"{restored_source_deltas} < {config.min_source_deltas}."
        )
    if restored_memory_pages < config.min_memory_pages:
        raise BackupRestoreError(
            "Hosted restore did not prove restored MemoryPage rows: "
            f"{restored_memory_pages} < {config.min_memory_pages}."
        )
    if restored_source_spans_with_raw < config.min_source_spans_with_raw:
        raise BackupRestoreError(
            "Hosted restore did not prove SourceSpan -> RawSource resolution: "
            f"{restored_source_spans_with_raw} < {config.min_source_spans_with_raw}."
        )


def _database_url_from_env(env: Mapping[str, str], name: str) -> DatabaseUrl:
    value = _required(env, name)
    parsed = urlsplit(value)
    if not parsed.scheme.startswith("postgresql"):
        raise ConfigError(f"{name} must be a PostgreSQL URL.")
    if not parsed.hostname:
        raise ConfigError(f"{name} must include a database host.")
    hostname = parsed.hostname.strip()
    _validate_hosted_database_host(name, hostname)
    return DatabaseUrl(
        raw=value,
        cli_url=_postgres_cli_url(parsed),
        scheme=parsed.scheme,
        host=hostname,
        sanitized=_sanitize_url(parsed),
    )


def _postgres_cli_url(parsed: SplitResult) -> str:
    scheme = "postgresql" if parsed.scheme.startswith("postgresql+") else parsed.scheme
    return urlunsplit((scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def _same_database_target(left: DatabaseUrl, right: DatabaseUrl) -> bool:
    left_parsed = urlsplit(left.cli_url)
    right_parsed = urlsplit(right.cli_url)
    return (
        (left_parsed.hostname or "").lower() == (right_parsed.hostname or "").lower()
        and left_parsed.port == right_parsed.port
        and left_parsed.path == right_parsed.path
    )


def _sanitize_url(parsed: SplitResult) -> str:
    host = parsed.hostname or ""
    netloc = host
    if parsed.username:
        password = ":***" if parsed.password else ""
        netloc = f"{parsed.username}{password}@{host}"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _backup_target_from_uri(value: str) -> BackupTarget:
    parsed = urlparse(value)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ConfigError("SEXTANT_BACKUP_TARGET must be an s3:// URI.")
    prefix = parsed.path.strip("/")
    return BackupTarget(raw=value, bucket=parsed.netloc, prefix=prefix)


def _schemas(value: str) -> tuple[str, ...]:
    schemas = tuple(schema.strip() for schema in value.split(",") if schema.strip())
    if not schemas:
        raise ConfigError("SEXTANT_BACKUP_RESTORE_SCHEMAS must list at least one schema.")
    for schema in schemas:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ConfigError(
                "SEXTANT_BACKUP_RESTORE_SCHEMAS must contain only PostgreSQL identifier names."
            )
    return schemas


def _required_extensions(value: str) -> tuple[RequiredExtension, ...]:
    raw_items = [item.strip() for item in value.split(",") if item.strip()]
    extensions: list[RequiredExtension] = []
    for item in raw_items:
        if ":" in item:
            name, schema = (part.strip() for part in item.split(":", 1))
        else:
            name, schema = item, "public"
        _validate_identifier("SEXTANT_BACKUP_RESTORE_REQUIRED_EXTENSIONS", name)
        _validate_identifier("SEXTANT_BACKUP_RESTORE_REQUIRED_EXTENSIONS", schema)
        extensions.append(RequiredExtension(name=name, schema=schema))
    return tuple(extensions)


def _validate_identifier(name: str, value: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ConfigError(f"{name} must contain only PostgreSQL identifier names.")


def _quote_identifier(value: str) -> str:
    _validate_identifier("PostgreSQL identifier", value)
    return f'"{value}"'


def _target_key(prefix: str, object_name: str) -> str:
    clean_name = object_name.strip("/")
    if not clean_name or ".." in clean_name.split("/"):
        raise BackupRestoreError("Backup object name is invalid.")
    if not prefix:
        return clean_name
    return f"{prefix}/{clean_name}"


def _safe_prefix(value: str) -> str:
    prefix = value.strip().strip("/")
    if not prefix or ".." in prefix.split("/"):
        raise ConfigError("SEXTANT_BACKUP_RESTORE_PROBE_PREFIX must be a safe object prefix.")
    return prefix.replace("/", "-")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted backup/restore probe.")
    return value


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive number.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive number.")
    return parsed


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _validate_hosted_database_host(name: str, host: str) -> None:
    normalized = host.rstrip(".").lower()
    if normalized in LOCAL_DATABASE_HOSTS or normalized.endswith(".local"):
        raise ConfigError(f"{name} must point at a hosted database host.")
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must point at a hosted database host.")


def _validate_hosted_https_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL, not a local address.")


def _create_s3_client(endpoint_url: str | None):
    import boto3

    kwargs: dict[str, str] = {}
    if region := os.environ.get("SEXTANT_AWS_REGION") or os.environ.get("AWS_REGION"):
        kwargs["region_name"] = region
    if endpoint_url is not None:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run hosted PostgreSQL backup/restore through pg_dump, S3, and psql, "
            "then emit sanitized JSON evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted backup/restore probe configuration without network requests.",
    )
    args = parser.parse_args()
    try:
        config = BackupRestoreConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-backup-restore-config-ok")
            return 0
        print(json.dumps(run_backup_restore_probe(config), sort_keys=True))
        return 0
    except (ConfigError, BackupRestoreError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
