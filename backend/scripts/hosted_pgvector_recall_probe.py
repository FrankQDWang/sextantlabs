from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class ConfigError(RuntimeError):
    pass


class PgvectorProbeError(RuntimeError):
    pass


LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
HNSW_INDEX_NAME = "ix_semantic_embeddings_embedding_vector_hnsw"


@dataclass(frozen=True)
class DatabaseUrl:
    raw: str
    scheme: str
    host: str
    sanitized: str


@dataclass(frozen=True)
class PgvectorRecallConfig:
    database_url: DatabaseUrl
    project_id: UUID
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    recall_limit: int
    max_self_distance: float

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> PgvectorRecallConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "pgvector recall proof."
            )
        vector_index_provider = _required(env, "SEXTANT_VECTOR_INDEX_PROVIDER")
        if vector_index_provider != "pgvector":
            raise ConfigError("SEXTANT_VECTOR_INDEX_PROVIDER must be pgvector.")
        return cls(
            database_url=_database_url_from_env(env),
            project_id=_uuid_from_env(env, "SEXTANT_PGVECTOR_RECALL_PROJECT_ID"),
            embedding_provider=_required(env, "SEXTANT_EMBEDDING_PROVIDER"),
            embedding_model=_required(env, "SEXTANT_EMBEDDING_MODEL"),
            embedding_dimensions=_positive_int(
                env.get("SEXTANT_EMBEDDING_DIMENSIONS", ""),
                "SEXTANT_EMBEDDING_DIMENSIONS",
            ),
            recall_limit=_positive_int(
                env.get("SEXTANT_PGVECTOR_RECALL_LIMIT", "5"),
                "SEXTANT_PGVECTOR_RECALL_LIMIT",
            ),
            max_self_distance=_non_negative_float(
                env.get("SEXTANT_PGVECTOR_RECALL_MAX_SELF_DISTANCE", "0.000001"),
                "SEXTANT_PGVECTOR_RECALL_MAX_SELF_DISTANCE",
            ),
        )


@dataclass(frozen=True)
class PgvectorProbeChecks:
    vector_extension: bool
    embedding_vector_column: bool
    hnsw_index: bool
    vector_rows: int
    probe_embedding_id: str
    nearest_embedding_id: str
    nearest_target_type: str
    nearest_distance: float


def run_pgvector_probe(config: PgvectorRecallConfig) -> dict[str, object]:
    engine = create_engine(config.database_url.raw, pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            checks = fetch_pgvector_checks(connection, config)
    finally:
        engine.dispose()
    return build_pgvector_evidence(config, checks)


def fetch_pgvector_checks(
    connection: Connection,
    config: PgvectorRecallConfig,
) -> PgvectorProbeChecks:
    vector_extension = bool(
        connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar()
    )
    embedding_vector_column = bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM information_schema.columns
                  WHERE table_schema = current_schema()
                    AND table_name = 'semantic_embeddings'
                    AND column_name = 'embedding_vector'
                )
                """
            )
        ).scalar()
    )
    hnsw_index = bool(
        connection.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM pg_indexes
                  WHERE schemaname = current_schema()
                    AND tablename = 'semantic_embeddings'
                    AND indexname = :index_name
                )
                """
            ),
            {"index_name": HNSW_INDEX_NAME},
        ).scalar()
    )
    params = _semantic_params(config)
    vector_rows = int(
        connection.execute(
            text(
                """
                SELECT count(*)
                FROM semantic_embeddings
                WHERE project_id = CAST(:project_id AS uuid)
                  AND provider = :provider
                  AND model_name = :model_name
                  AND dimensions = :dimensions
                  AND embedding_vector IS NOT NULL
                """
            ),
            params,
        ).scalar_one()
    )
    if not vector_extension or not embedding_vector_column or not hnsw_index or vector_rows < 1:
        return PgvectorProbeChecks(
            vector_extension=vector_extension,
            embedding_vector_column=embedding_vector_column,
            hnsw_index=hnsw_index,
            vector_rows=vector_rows,
            probe_embedding_id="",
            nearest_embedding_id="",
            nearest_target_type="",
            nearest_distance=float("inf"),
        )

    vector_type = _pgvector_type_name(config.embedding_dimensions)
    nearest = (
        connection.execute(
            text(
                f"""
                WITH probe AS (
                  SELECT id, embedding_vector::{vector_type} AS query_vector
                  FROM semantic_embeddings
                  WHERE project_id = CAST(:project_id AS uuid)
                    AND provider = :provider
                    AND model_name = :model_name
                    AND dimensions = :dimensions
                    AND embedding_vector IS NOT NULL
                  ORDER BY updated_at DESC, id
                  LIMIT 1
                )
                SELECT
                  probe.id::text AS probe_embedding_id,
                  e.id::text AS nearest_embedding_id,
                  e.target_type AS nearest_target_type,
                  (
                    e.embedding_vector::{vector_type} <=> probe.query_vector
                  ) AS nearest_distance
                FROM probe
                JOIN semantic_embeddings e
                  ON e.project_id = CAST(:project_id AS uuid)
                 AND e.provider = :provider
                 AND e.model_name = :model_name
                 AND e.dimensions = :dimensions
                 AND e.embedding_vector IS NOT NULL
                ORDER BY (
                  e.embedding_vector::{vector_type} <=> probe.query_vector
                ),
                e.target_type,
                e.target_id::text
                LIMIT :recall_limit
                """
            ),
            {**params, "recall_limit": config.recall_limit},
        )
        .mappings()
        .first()
    )
    if nearest is None:
        return PgvectorProbeChecks(
            vector_extension=vector_extension,
            embedding_vector_column=embedding_vector_column,
            hnsw_index=hnsw_index,
            vector_rows=vector_rows,
            probe_embedding_id="",
            nearest_embedding_id="",
            nearest_target_type="",
            nearest_distance=float("inf"),
        )
    return PgvectorProbeChecks(
        vector_extension=vector_extension,
        embedding_vector_column=embedding_vector_column,
        hnsw_index=hnsw_index,
        vector_rows=vector_rows,
        probe_embedding_id=str(nearest["probe_embedding_id"]),
        nearest_embedding_id=str(nearest["nearest_embedding_id"]),
        nearest_target_type=str(nearest["nearest_target_type"]),
        nearest_distance=float(nearest["nearest_distance"]),
    )


def build_pgvector_evidence(
    config: PgvectorRecallConfig,
    checks: PgvectorProbeChecks,
) -> dict[str, object]:
    _validate_checks(config, checks)
    return {
        "status": "pass",
        "database_host": config.database_url.host,
        "database_scheme": config.database_url.scheme,
        "database_url": config.database_url.sanitized,
        "project_id_hash": _hash_identifier(str(config.project_id)),
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_dimensions": config.embedding_dimensions,
        "vector_extension": checks.vector_extension,
        "embedding_vector_column": checks.embedding_vector_column,
        "hnsw_index": HNSW_INDEX_NAME,
        "vector_rows": checks.vector_rows,
        "recall_limit": config.recall_limit,
        "nearest_target_type": checks.nearest_target_type,
        "nearest_distance": checks.nearest_distance,
        "probe_embedding_id_hash": _hash_identifier(checks.probe_embedding_id),
        "nearest_embedding_id_hash": _hash_identifier(checks.nearest_embedding_id),
    }


def _validate_checks(config: PgvectorRecallConfig, checks: PgvectorProbeChecks) -> None:
    if not checks.vector_extension:
        raise PgvectorProbeError("Hosted PostgreSQL vector extension is not installed.")
    if not checks.embedding_vector_column:
        raise PgvectorProbeError("semantic_embeddings.embedding_vector column is missing.")
    if not checks.hnsw_index:
        raise PgvectorProbeError(f"Hosted pgvector HNSW index {HNSW_INDEX_NAME} is missing.")
    if checks.vector_rows < 1:
        raise PgvectorProbeError(
            "Hosted pgvector recall probe found no embedding vectors for the "
            "configured project/provider/model/dimensions."
        )
    if checks.probe_embedding_id != checks.nearest_embedding_id:
        raise PgvectorProbeError("Hosted pgvector nearest neighbor did not return the probe row.")
    if checks.nearest_distance > config.max_self_distance:
        raise PgvectorProbeError(
            "Hosted pgvector self-distance is too high: "
            f"{checks.nearest_distance:g} exceeds {config.max_self_distance:g}."
        )


def _semantic_params(config: PgvectorRecallConfig) -> dict[str, object]:
    return {
        "project_id": str(config.project_id),
        "provider": config.embedding_provider,
        "model_name": config.embedding_model,
        "dimensions": config.embedding_dimensions,
    }


def _database_url_from_env(env: Mapping[str, str]) -> DatabaseUrl:
    value = env.get("SEXTANT_DATABASE_URL", "").strip()
    if not value:
        raise ConfigError("SEXTANT_DATABASE_URL is required.")
    parsed = urlsplit(value)
    if not parsed.scheme.startswith("postgresql"):
        raise ConfigError("SEXTANT_DATABASE_URL must be a PostgreSQL URL.")
    if not parsed.hostname:
        raise ConfigError("SEXTANT_DATABASE_URL must include a database host.")
    hostname = parsed.hostname.strip()
    if hostname.lower() in LOCAL_DATABASE_HOSTS or hostname.endswith(".local"):
        raise ConfigError("SEXTANT_DATABASE_URL must point at a hosted database host.")
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
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required.")
    return value


def _uuid_from_env(env: Mapping[str, str], name: str) -> UUID:
    value = _required(env, name)
    try:
        return UUID(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a UUID.") from exc


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _non_negative_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a non-negative number.") from exc
    if parsed < 0:
        raise ConfigError(f"{name} must be a non-negative number.")
    return parsed


def _pgvector_type_name(dimensions: int) -> str:
    if dimensions <= 0:
        raise ConfigError("SEXTANT_EMBEDDING_DIMENSIONS must be a positive integer.")
    return f"vector({dimensions})"


def _hash_identifier(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe hosted PostgreSQL pgvector semantic recall for a configured "
            "Sextant project/provider/model and emit sanitized JSON proof evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted pgvector recall configuration without connecting to the database.",
    )
    args = parser.parse_args()
    try:
        config = PgvectorRecallConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-pgvector-recall-config-ok")
            return 0
        print(json.dumps(run_pgvector_probe(config), sort_keys=True))
        return 0
    except (ConfigError, PgvectorProbeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
