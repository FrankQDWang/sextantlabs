from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sextant.infra.source_delta_search import reindex_source_delta_search


class ConfigError(RuntimeError):
    pass


LOCAL_DATABASE_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


@dataclass(frozen=True)
class DatabaseUrl:
    raw: str
    scheme: str
    host: str
    sanitized: str


@dataclass(frozen=True)
class ReindexProbeConfig:
    database_url: DatabaseUrl
    object_store_root: str
    batch_size: int
    rebuild_all: bool = False

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        *,
        batch_size: int = 100,
        rebuild_all: bool = False,
    ) -> ReindexProbeConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "SourceDelta reindex proof."
            )
        if batch_size < 1:
            raise ConfigError("--batch-size must be a positive integer.")

        database_url = _database_url_from_env(env)
        object_store_root = env.get("SEXTANT_OBJECT_STORE_ROOT", "").strip()
        if not object_store_root:
            raise ConfigError("SEXTANT_OBJECT_STORE_ROOT is required.")
        if not object_store_root.startswith("s3://"):
            raise ConfigError("SEXTANT_OBJECT_STORE_ROOT must be an s3:// URI.")

        return cls(
            database_url=database_url,
            object_store_root=object_store_root,
            batch_size=batch_size,
            rebuild_all=rebuild_all,
        )


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


def build_reindex_evidence(config: ReindexProbeConfig, *, reindexed_rows: int) -> dict[str, object]:
    return {
        "status": "pass",
        "database_host": config.database_url.host,
        "database_scheme": config.database_url.scheme,
        "database_url": config.database_url.sanitized,
        "object_store_root": config.object_store_root,
        "batch_size": config.batch_size,
        "rebuild_all": config.rebuild_all,
        "reindexed_rows": reindexed_rows,
    }


def run_reindex(config: ReindexProbeConfig) -> dict[str, object]:
    count = reindex_source_delta_search(
        database_url=config.database_url.raw,
        object_store_root=config.object_store_root,
        batch_size=config.batch_size,
        rebuild_all=config.rebuild_all,
    )
    return build_reindex_evidence(config, reindexed_rows=count)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run SourceDelta submitted-text search reindex against hosted "
            "production PostgreSQL and S3 object storage, then emit JSON proof evidence."
        )
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--all", action="store_true", help="Rebuild rows that already have text.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted production configuration without connecting to DB or object storage.",
    )
    args = parser.parse_args()

    try:
        config = ReindexProbeConfig.from_env(
            os.environ,
            batch_size=args.batch_size,
            rebuild_all=args.all,
        )
        if args.check_config:
            print("hosted-source-delta-reindex-config-ok")
            return 0
        print(json.dumps(run_reindex(config), sort_keys=True))
        return 0
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
