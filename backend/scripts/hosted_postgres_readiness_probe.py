from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
MANAGED_POSTGRES_SCHEMES = {
    "rds",
    "cloudsql",
    "azure-postgres",
    "neon",
    "supabase",
    "crunchy-postgres",
}

CONNECTIVITY_SQL = "SELECT 1;"
CURRENT_DATABASE_SQL = "SELECT current_database();"
CURRENT_USER_SQL = "SELECT current_user;"
SERVER_VERSION_SQL = "SHOW server_version;"
ALEMBIC_VERSION_SQL = "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1;"
SOURCE_DELTA_COUNT_SQL = "SELECT count(*) FROM source_deltas;"
SOURCE_SPAN_COUNT_SQL = "SELECT count(*) FROM source_spans;"
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


class PostgresReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseUrl:
    raw: str
    scheme: str
    host: str
    sanitized: str


@dataclass(frozen=True)
class PostgresReadinessConfig:
    database_url: DatabaseUrl
    managed_instance_ref: str
    managed_instance_scheme: str
    managed_instance_fingerprint: str
    min_source_deltas: int
    min_source_spans: int
    min_memory_pages: int
    min_source_spans_with_raw: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> PostgresReadinessConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "PostgreSQL readiness proof."
            )
        database_url = _database_url_from_env(env)
        managed_ref = _required(env, "SEXTANT_MANAGED_POSTGRES_INSTANCE")
        managed_scheme = _managed_instance_scheme(managed_ref)
        return cls(
            database_url=database_url,
            managed_instance_ref=managed_ref,
            managed_instance_scheme=managed_scheme,
            managed_instance_fingerprint=hashlib.sha256(managed_ref.encode()).hexdigest(),
            min_source_deltas=_positive_int(
                env.get("SEXTANT_POSTGRES_READINESS_MIN_SOURCE_DELTAS", "1"),
                "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_DELTAS",
            ),
            min_source_spans=_positive_int(
                env.get("SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS", "1"),
                "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS",
            ),
            min_memory_pages=_positive_int(
                env.get("SEXTANT_POSTGRES_READINESS_MIN_MEMORY_PAGES", "1"),
                "SEXTANT_POSTGRES_READINESS_MIN_MEMORY_PAGES",
            ),
            min_source_spans_with_raw=_positive_int(
                env.get("SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS_WITH_RAW", "1"),
                "SEXTANT_POSTGRES_READINESS_MIN_SOURCE_SPANS_WITH_RAW",
            ),
        )


QueryRunner = Callable[[str], object]


def run_postgres_readiness_probe(
    config: PostgresReadinessConfig,
    *,
    query_runner: QueryRunner | None = None,
    expected_alembic_head: str | None = None,
) -> dict[str, object]:
    run_query = query_runner or _sqlalchemy_query_runner(config.database_url.raw)
    expected_head = expected_alembic_head or _current_alembic_head()

    _expect_int(run_query(CONNECTIVITY_SQL), "connectivity check")
    current_database = str(run_query(CURRENT_DATABASE_SQL))
    current_user = str(run_query(CURRENT_USER_SQL))
    server_version = str(run_query(SERVER_VERSION_SQL))
    alembic_version = str(run_query(ALEMBIC_VERSION_SQL))
    if alembic_version != expected_head:
        raise PostgresReadinessError(
            "Hosted PostgreSQL Alembic version does not match expected head: "
            f"{alembic_version} != {expected_head}."
        )

    source_delta_count = _expect_int(run_query(SOURCE_DELTA_COUNT_SQL), "SourceDelta count")
    source_span_count = _expect_int(run_query(SOURCE_SPAN_COUNT_SQL), "SourceSpan count")
    memory_page_count = _expect_int(run_query(MEMORY_PAGE_COUNT_SQL), "MemoryPage count")
    source_span_raw_resolution_count = _expect_int(
        run_query(SOURCE_SPAN_RAW_COUNT_SQL),
        "SourceSpan -> RawSource resolution count",
    )

    _validate_minimums(
        config,
        source_delta_count=source_delta_count,
        source_span_count=source_span_count,
        memory_page_count=memory_page_count,
        source_span_raw_resolution_count=source_span_raw_resolution_count,
    )

    return {
        "status": "pass",
        "database_host": config.database_url.host,
        "database_url": config.database_url.sanitized,
        "database_name": current_database,
        "database_user": current_user,
        "server_version": server_version,
        "alembic_version": alembic_version,
        "expected_alembic_head": expected_head,
        "managed_instance_scheme": config.managed_instance_scheme,
        "managed_instance_fingerprint": config.managed_instance_fingerprint,
        "source_delta_count": source_delta_count,
        "source_span_count": source_span_count,
        "memory_page_count": memory_page_count,
        "source_span_raw_resolution_count": source_span_raw_resolution_count,
    }


def _sqlalchemy_query_runner(database_url: str) -> QueryRunner:
    engine = create_engine(database_url)

    def run(sql: str) -> object:
        with engine.connect() as connection:
            return connection.execute(text(sql)).scalar_one()

    return run


def _current_alembic_head() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "alembic.ini"))
    return str(ScriptDirectory.from_config(config).get_current_head())


def _validate_minimums(
    config: PostgresReadinessConfig,
    *,
    source_delta_count: int,
    source_span_count: int,
    memory_page_count: int,
    source_span_raw_resolution_count: int,
) -> None:
    if source_delta_count < config.min_source_deltas:
        raise PostgresReadinessError(
            "Hosted PostgreSQL did not prove required SourceDelta rows: "
            f"{source_delta_count} < {config.min_source_deltas}."
        )
    if source_span_count < config.min_source_spans:
        raise PostgresReadinessError(
            "Hosted PostgreSQL did not prove required SourceSpan rows: "
            f"{source_span_count} < {config.min_source_spans}."
        )
    if memory_page_count < config.min_memory_pages:
        raise PostgresReadinessError(
            "Hosted PostgreSQL did not prove required MemoryPage rows: "
            f"{memory_page_count} < {config.min_memory_pages}."
        )
    if source_span_raw_resolution_count < config.min_source_spans_with_raw:
        raise PostgresReadinessError(
            "Hosted PostgreSQL did not prove SourceSpan -> RawSource resolution: "
            f"{source_span_raw_resolution_count} < {config.min_source_spans_with_raw}."
        )


def _expect_int(value: object, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PostgresReadinessError(f"Hosted PostgreSQL {label} returned non-integer.") from exc


def _database_url_from_env(env: Mapping[str, str]) -> DatabaseUrl:
    value = _required(env, "SEXTANT_DATABASE_URL")
    parsed = urlsplit(value)
    if not parsed.scheme.startswith("postgresql"):
        raise ConfigError("SEXTANT_DATABASE_URL must be a PostgreSQL URL.")
    if not parsed.hostname:
        raise ConfigError("SEXTANT_DATABASE_URL must include a database host.")
    hostname = parsed.hostname.strip()
    _validate_hosted_database_host("SEXTANT_DATABASE_URL", hostname)
    return DatabaseUrl(
        raw=value,
        scheme=parsed.scheme,
        host=hostname,
        sanitized=_sanitize_url(parsed),
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


def _managed_instance_scheme(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in MANAGED_POSTGRES_SCHEMES or not parsed.netloc:
        raise ConfigError(
            "SEXTANT_MANAGED_POSTGRES_INSTANCE must be rds://, cloudsql://, "
            "azure-postgres://, neon://, supabase://, or crunchy-postgres:// "
            "with a non-empty target."
        )
    return parsed.scheme


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required for hosted PostgreSQL readiness probe.")
    return value


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe hosted PostgreSQL connectivity, migration version, and "
            "evidence-chain row presence, then emit sanitized JSON evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted PostgreSQL readiness configuration without DB queries.",
    )
    args = parser.parse_args()
    try:
        config = PostgresReadinessConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-postgres-readiness-config-ok")
            return 0
        print(json.dumps(run_postgres_readiness_probe(config), sort_keys=True))
        return 0
    except (ConfigError, PostgresReadinessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
