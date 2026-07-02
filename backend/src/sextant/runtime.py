from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from sextant.api.app import create_app
from sextant.common.observability import MetricsRegistry
from sextant.infra.auth import JwksJwtVerifier
from sextant.infra.embedding_provider import embedding_provider_from_env
from sextant.infra.object_store import object_store_from_uri
from sextant.infra.runtime_config import database_url_from_env, object_store_uri_from_env
from sextant.infra.story_draft_provider import story_draft_provider_from_env
from sextant.infra.uow import SqlAlchemyUnitOfWork

_SQLITE_BUSY_TIMEOUT_SECONDS = 30
_SQLITE_BUSY_TIMEOUT_MS = _SQLITE_BUSY_TIMEOUT_SECONDS * 1000


def build_app():
    database_url = database_url_from_env()
    object_store_uri = object_store_uri_from_env()
    engine = _engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    metrics = MetricsRegistry()
    embedding_provider = embedding_provider_from_env(metrics=metrics)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(
            session_factory(),
            close_on_exit=True,
            embedding_client=embedding_provider,
        )

    return create_app(
        uow_factory,
        object_store=object_store_from_uri(object_store_uri),
        story_draft_provider=story_draft_provider_from_env(metrics=metrics),
        auth_verifier=_auth_verifier(),
        admin_actor_ids=_admin_actor_ids(),
        allowed_origins=_cors_origins(),
        metrics=metrics,
        log_sink=_api_log_sink(),
        health_metadata=_health_metadata(),
    )


def _engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        sqlite_path = database_url.removeprefix("sqlite+pysqlite:///")
        if sqlite_path and sqlite_path != ":memory:":
            Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            database_url,
            connect_args={
                "check_same_thread": False,
                "timeout": _SQLITE_BUSY_TIMEOUT_SECONDS,
            },
            pool_pre_ping=True,
        )
        _configure_sqlite_engine(engine)
        return engine
    return create_engine(database_url, pool_pre_ping=True)


def _configure_sqlite_engine(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def _cors_origins() -> list[str]:
    value = os.environ.get(
        "SEXTANT_CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174",
    )
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def _auth_verifier() -> JwksJwtVerifier | None:
    auth_mode = os.environ.get("SEXTANT_AUTH_MODE", "").strip()
    if not auth_mode:
        raise RuntimeError("SEXTANT_AUTH_MODE is required. Use header-dev locally or jwt-jwks.")
    if auth_mode == "header-dev":
        return None
    if auth_mode != "jwt-jwks":
        raise RuntimeError(f"Unsupported SEXTANT_AUTH_MODE: {auth_mode}")
    return JwksJwtVerifier(
        issuer=_required_env("SEXTANT_SESSION_ISSUER"),
        audience=_required_env("SEXTANT_SESSION_AUDIENCE"),
        jwks_url=_jwks_url(),
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for SEXTANT_AUTH_MODE=jwt-jwks.")
    return value


def _admin_actor_ids() -> frozenset[UUID]:
    value = os.environ.get("SEXTANT_ADMIN_ACTOR_IDS", "").strip()
    if not value:
        return frozenset()
    try:
        return frozenset(UUID(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise RuntimeError("SEXTANT_ADMIN_ACTOR_IDS must be comma-separated UUIDs.") from exc


def _jwks_url() -> str:
    value = _required_env("SEXTANT_SESSION_JWKS_URL")
    if value.startswith("https://"):
        return value
    if os.environ.get("SEXTANT_ALLOW_INSECURE_JWKS_FOR_TESTS") == "1":
        return value
    raise RuntimeError("SEXTANT_SESSION_JWKS_URL must be an HTTPS URL.")


def _api_log_sink() -> Callable[[str], None] | None:
    if os.environ.get("SEXTANT_API_REQUEST_LOGS") != "1":
        return None
    return print


def _health_metadata() -> dict[str, str]:
    release_environment = os.environ.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
    deployment_version = os.environ.get("SEXTANT_DEPLOYMENT_VERSION", "").strip()
    return {
        "release_environment": release_environment or "development",
        "deployment_version": deployment_version or "local",
    }


app = build_app()
