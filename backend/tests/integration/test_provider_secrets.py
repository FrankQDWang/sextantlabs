from __future__ import annotations

import base64

import pytest
from sextant.infra.provider_secrets import (
    AwsSecretsManagerSecretResolver,
    GcpSecretManagerSecretResolver,
    SupabaseVaultSecretResolver,
    VaultSecretResolver,
    openai_api_key_from_env,
)


class _FakeSecretsManagerClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.secret_ids: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict[str, object]:  # noqa: N803
        self.secret_ids.append(SecretId)
        return self.response


class _FakeGcpSecretPayload:
    def __init__(self, data: bytes) -> None:
        self.data = data


class _FakeGcpSecretResponse:
    def __init__(self, data: bytes) -> None:
        self.payload = _FakeGcpSecretPayload(data)


class _FakeGcpSecretManagerClient:
    def __init__(self, response: _FakeGcpSecretResponse) -> None:
        self.response = response
        self.requests: list[dict[str, str]] = []

    def access_secret_version(self, *, request: dict[str, str]) -> _FakeGcpSecretResponse:
        self.requests.append(request)
        return self.response


def test_openai_api_key_from_env_reads_aws_secret_manager_json_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeSecretsManagerClient(
        {"SecretString": '{"OPENAI_API_KEY": "sk-from-aws", "other": "ignored"}'}
    )
    resolver = AwsSecretsManagerSecretResolver(client_factory=lambda region: client)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI story draft", secret_resolver=resolver)

    assert api_key == "sk-from-aws"
    assert client.secret_ids == ["prod/sextant/openai"]


def test_openai_api_key_from_env_reads_aws_secret_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeSecretsManagerClient(
        {"SecretBinary": base64.b64encode(b"sk-binary-secret").decode("ascii")}
    )
    resolver = AwsSecretsManagerSecretResolver(client_factory=lambda region: client)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "aws-secretsmanager://us-west-2/prod/sextant/openai-binary",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI memory extraction", secret_resolver=resolver)

    assert api_key == "sk-binary-secret"
    assert client.secret_ids == ["prod/sextant/openai-binary"]


def test_openai_api_key_from_env_reads_gcp_secret_manager_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeGcpSecretManagerClient(_FakeGcpSecretResponse(b"sk-from-gcp"))
    resolver = GcpSecretManagerSecretResolver(client_factory=lambda: client)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "gcp-secretmanager://story-prod/openai-api-key?version=5",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI story draft", secret_resolver=resolver)

    assert api_key == "sk-from-gcp"
    assert client.requests == [{"name": "projects/story-prod/secrets/openai-api-key/versions/5"}]


def test_openai_api_key_from_env_reads_gcp_secret_manager_latest_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeGcpSecretManagerClient(_FakeGcpSecretResponse(b"sk-from-gcp-latest"))
    resolver = GcpSecretManagerSecretResolver(client_factory=lambda: client)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "gcp-secretmanager://story-prod/openai-api-key",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI story draft", secret_resolver=resolver)

    assert api_key == "sk-from-gcp-latest"
    assert client.requests == [
        {"name": "projects/story-prod/secrets/openai-api-key/versions/latest"}
    ]


def test_openai_api_key_from_env_keeps_secret_uri_as_materialization_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "secret://prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="Deployment must materialize"):
        openai_api_key_from_env("OpenAI POV detection")


def test_openai_api_key_from_env_invalid_secret_ref_lists_supported_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as exc_info:
        openai_api_key_from_env("OpenAI story draft")

    message = str(exc_info.value)
    assert "secret://" in message
    assert "aws-secretsmanager://" in message
    assert "gcp-secretmanager://" in message
    assert "vault://" in message


def test_openai_api_key_from_env_rejects_empty_aws_json_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeSecretsManagerClient({"SecretString": '{"OPENAI_API_KEY": "   "}'})
    resolver = AwsSecretsManagerSecretResolver(client_factory=lambda region: client)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="empty secret value"):
        openai_api_key_from_env("OpenAI embedding", secret_resolver=resolver)


def test_openai_api_key_from_env_reads_vault_secret_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    def load_json(url: str, headers: dict[str, str]) -> dict[str, object]:
        requests.append((url, headers))
        return {"data": {"data": {"OPENAI_API_KEY": "sk-from-vault"}}}

    resolver = VaultSecretResolver(token="vault-token", json_loader=load_json)
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "vault://vault.example.com/secret/data/sextant/openai?field=OPENAI_API_KEY",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI story draft", secret_resolver=resolver)

    assert api_key == "sk-from-vault"
    assert requests == [
        (
            "https://vault.example.com/v1/secret/data/sextant/openai",
            {"X-Vault-Token": "vault-token"},
        )
    ]


def test_openai_api_key_from_env_reads_supabase_vault_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []

    def load_secret(database_url: str, secret_name: str) -> str:
        requests.append((database_url, secret_name))
        return "sk-from-supabase-vault"

    resolver = SupabaseVaultSecretResolver(
        database_url="postgresql://postgres.example.com/sextant",
        secret_loader=load_secret,
    )
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    api_key = openai_api_key_from_env("OpenAI story draft", secret_resolver=resolver)

    assert api_key == "sk-from-supabase-vault"
    assert requests == [
        (
            "postgresql://postgres.example.com/sextant",
            "sextant_openai_api_key",
        )
    ]


def test_openai_api_key_from_env_requires_vault_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SEXTANT_LLM_API_KEY_SECRET_REF",
        "vault://vault.example.com/secret/data/sextant/openai?field=OPENAI_API_KEY",
    )
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SEXTANT_VAULT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_VAULT_TOKEN"):
        openai_api_key_from_env("OpenAI memory extraction")
