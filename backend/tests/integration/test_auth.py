from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sextant.api.app import create_app
from sextant.infra.db.models import Base, Project, ProjectMembership
from sextant.infra.uow import SqlAlchemyUnitOfWork
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


class TokenVerifier:
    def __init__(self, actor_id: UUID) -> None:
        self.actor_id = actor_id

    def actor_id_for_authorization(self, authorization: str | None) -> UUID | None:
        if authorization == "Bearer valid-token":
            return self.actor_id
        return None


def test_production_auth_requires_bearer_token_and_ignores_header_only_actor() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    actor_id = uuid4()
    project_id = uuid4()
    with Session(engine) as session:
        session.add_all(
            [
                Project(id=project_id, name="Auth Smoke"),
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
        client = TestClient(
            create_app(
                lambda: SqlAlchemyUnitOfWork(session),
                auth_verifier=TokenVerifier(actor_id),
            )
        )

        header_only = client.get(
            f"/api/projects/{project_id}/sources",
            headers={"X-Actor-Id": str(actor_id)},
        )
    bearer = client.get(
        f"/api/projects/{project_id}/sources",
        headers={"Authorization": "Bearer valid-token"},
    )
    spoofed_header = client.get(
        f"/api/projects/{project_id}/sources",
        headers={
            "Authorization": "Bearer valid-token",
            "X-Actor-Id": str(uuid4()),
        },
    )

    assert header_only.status_code == 401
    assert header_only.json()["error"]["code"] == "authentication_required"
    assert bearer.status_code == 200
    assert bearer.json()["items"] == []
    assert spoofed_header.status_code == 200


def test_jwks_jwt_verifier_validates_signature_issuer_audience_and_subject(tmp_path) -> None:
    from sextant.infra.auth import JwksJwtVerifier

    actor_id = uuid4()
    issuer = "https://auth.example.test/"
    audience = "sextant-api"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    jwks_path = tmp_path / "jwks.json"
    jwks_path.write_text(json.dumps({"keys": [public_jwk]}), encoding="utf-8")
    expires_at = datetime.now(UTC) + timedelta(minutes=10)

    token = jwt.encode(
        {"sub": str(actor_id), "iss": issuer, "aud": audience, "exp": expires_at},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    wrong_audience = jwt.encode(
        {"sub": str(actor_id), "iss": issuer, "aud": "other-api", "exp": expires_at},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    missing_exp = jwt.encode(
        {"sub": str(actor_id), "iss": issuer, "aud": audience},
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    verifier = JwksJwtVerifier(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_path.as_uri(),
    )

    assert verifier.actor_id_for_authorization(f"Bearer {token}") == actor_id
    assert verifier.actor_id_for_authorization(f"Bearer {wrong_audience}") is None
    assert verifier.actor_id_for_authorization(f"Bearer {missing_exp}") is None
    assert verifier.actor_id_for_authorization("Bearer not-a-jwt") is None
    assert verifier.actor_id_for_authorization(None) is None
