from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sextant.infra.db.models import Base, Project, ProjectMembership
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def test_runtime_sqlite_engine_enables_wal_and_busy_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEXTANT_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'runtime-app.db'}")
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "header-dev")
    from sextant.runtime import _engine

    engine = _engine(f"sqlite+pysqlite:///{tmp_path / 'runtime-wal.db'}")

    with engine.connect() as connection:
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert busy_timeout >= 30_000
    assert journal_mode == "wal"


def test_runtime_app_assembles_real_uow_object_store_and_provider(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'runtime.db'}"
    object_root = tmp_path / "objects"
    project_id = uuid4()
    actor_id = uuid4()

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Project(id=project_id, name="Runtime Smoke"),
                ProjectMembership(
                    id=uuid4(),
                    project_id=project_id,
                    actor_id=actor_id,
                    role="owner",
                    status="active",
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("SEXTANT_DATABASE_URL", database_url)
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(object_root))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "header-dev")
    from sextant.runtime import build_app

    client = TestClient(build_app())

    response = client.post(
        f"/api/projects/{project_id}/memory/answer",
        headers={
            "X-Actor-Id": str(actor_id),
            "X-Request-Id": "req-runtime-answer",
            "Idempotency-Key": "idem-runtime-answer",
        },
        json={"question": "现在有什么证据？"},
    )

    assert response.status_code == 200
    assert response.json()["answer_type"] == "unknown"


def test_runtime_app_uses_jwks_auth_mode(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'runtime-jwks.db'}"
    object_root = tmp_path / "objects"
    project_id = uuid4()
    actor_id = uuid4()
    issuer = "https://auth.example.test/"
    audience = "sextant-api"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "runtime-key", "alg": "RS256", "use": "sig"})
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    token = jwt.encode(
        {"sub": str(actor_id), "iss": issuer, "aud": audience, "exp": expires_at},
        private_key,
        algorithm="RS256",
        headers={"kid": "runtime-key"},
    )

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Project(id=project_id, name="Runtime JWT Smoke"),
                ProjectMembership(
                    id=uuid4(),
                    project_id=project_id,
                    actor_id=actor_id,
                    role="viewer",
                    status="active",
                ),
            ]
        )
        session.commit()

    monkeypatch.setenv("SEXTANT_DATABASE_URL", database_url)
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(object_root))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "jwt-jwks")
    monkeypatch.setenv("SEXTANT_SESSION_ISSUER", issuer)
    monkeypatch.setenv("SEXTANT_SESSION_AUDIENCE", audience)
    monkeypatch.setenv("SEXTANT_SESSION_JWKS_URL", jwks_path.as_uri())
    monkeypatch.setenv("SEXTANT_ALLOW_INSECURE_JWKS_FOR_TESTS", "1")
    from sextant.runtime import build_app

    client = TestClient(build_app())

    rejected = client.get(
        f"/api/projects/{project_id}/sources",
        headers={"X-Actor-Id": str(actor_id)},
    )
    accepted = client.get(
        f"/api/projects/{project_id}/sources",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["items"] == []


def test_runtime_app_exposes_public_sanitized_health_endpoint(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'runtime-health.db'}"
    object_root = tmp_path / "objects"
    monkeypatch.setenv("SEXTANT_DATABASE_URL", database_url)
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(object_root))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "jwt-jwks")
    monkeypatch.setenv("SEXTANT_SESSION_ISSUER", "https://auth.example.test/")
    monkeypatch.setenv("SEXTANT_SESSION_AUDIENCE", "sextant-api")
    monkeypatch.setenv("SEXTANT_SESSION_JWKS_URL", "https://auth.example.test/jwks.json")
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "staging")
    monkeypatch.setenv("SEXTANT_DEPLOYMENT_VERSION", "2026.06.20-health")
    from sextant.runtime import build_app

    client = TestClient(build_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "sextant-api",
        "api_version": "0.1.0",
        "release_environment": "staging",
        "deployment_version": "2026.06.20-health",
    }
    serialized = response.text
    assert database_url not in serialized
    assert str(object_root) not in serialized
    assert "jwks.json" not in serialized
    assert "auth.example.test" not in serialized


def test_runtime_app_requires_explicit_auth_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SEXTANT_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'runtime.db'}")
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.delenv("SEXTANT_AUTH_MODE", raising=False)
    from sextant.runtime import build_app

    try:
        build_app()
    except RuntimeError as exc:
        assert "SEXTANT_AUTH_MODE is required" in str(exc)
    else:
        raise AssertionError("build_app should require explicit auth mode")


def test_runtime_app_rejects_database_default_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = _runtime_module_loaded_for_dev_import(tmp_path, monkeypatch)
    _set_production_provider_env(monkeypatch)
    monkeypatch.delenv("SEXTANT_DATABASE_URL", raising=False)
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "objects"))

    with pytest.raises(RuntimeError, match="SEXTANT_DATABASE_URL"):
        runtime.build_app()


def test_runtime_app_rejects_local_object_store_in_production(
    tmp_path,
    monkeypatch,
) -> None:
    runtime = _runtime_module_loaded_for_dev_import(tmp_path, monkeypatch)
    _set_production_provider_env(monkeypatch)
    monkeypatch.setenv(
        "SEXTANT_DATABASE_URL",
        "postgresql+psycopg://sextant:sextant@example.invalid:5432/sextant",
    )
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "objects"))

    with pytest.raises(RuntimeError, match="SEXTANT_OBJECT_STORE_ROOT"):
        runtime.build_app()


def test_runtime_app_rejects_insecure_jwks_url_without_test_escape_hatch(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SEXTANT_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'runtime.db'}")
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "jwt-jwks")
    monkeypatch.setenv("SEXTANT_SESSION_ISSUER", "https://auth.example.test/")
    monkeypatch.setenv("SEXTANT_SESSION_AUDIENCE", "sextant-api")
    monkeypatch.setenv("SEXTANT_SESSION_JWKS_URL", "http://auth.example.test/jwks.json")
    monkeypatch.delenv("SEXTANT_ALLOW_INSECURE_JWKS_FOR_TESTS", raising=False)
    from sextant.runtime import build_app

    try:
        build_app()
    except RuntimeError as exc:
        assert "HTTPS URL" in str(exc)
    else:
        raise AssertionError("build_app should reject insecure JWKS URLs")


def _runtime_module_loaded_for_dev_import(tmp_path, monkeypatch):
    monkeypatch.delenv("SEXTANT_RELEASE_ENVIRONMENT", raising=False)
    monkeypatch.setenv("SEXTANT_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'import.db'}")
    monkeypatch.setenv("SEXTANT_OBJECT_STORE_ROOT", str(tmp_path / "import-objects"))
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "header-dev")
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "local")
    monkeypatch.setenv("SEXTANT_EMBEDDING_PROVIDER", "local")
    return importlib.import_module("sextant.runtime")


def _set_production_provider_env(monkeypatch) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_AUTH_MODE", "jwt-jwks")
    monkeypatch.setenv("SEXTANT_SESSION_ISSUER", "https://auth.example.test/")
    monkeypatch.setenv("SEXTANT_SESSION_AUDIENCE", "sextant-api")
    monkeypatch.setenv("SEXTANT_SESSION_JWKS_URL", "https://auth.example.test/jwks.json")
    monkeypatch.setenv("SEXTANT_ADMIN_ACTOR_IDS", "00000000-0000-4000-8000-0000000000aa")
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_LLM_MODEL", "gpt-5")
    monkeypatch.setenv("SEXTANT_EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("SEXTANT_EMBEDDING_DIMENSIONS", "1536")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
