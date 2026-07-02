from __future__ import annotations

import base64
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen


class SecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str) -> dict[str, object]: ...  # noqa: N803


class GcpSecretManagerClient(Protocol):
    def access_secret_version(self, *, request: dict[str, str]) -> object: ...


class SecretResolver(Protocol):
    def read_secret(self, ref: str) -> str: ...


VaultJsonLoader = Callable[[str, dict[str, str]], dict[str, object]]
SupabaseVaultSecretLoader = Callable[[str, str], str]


@dataclass(frozen=True)
class AwsSecretsManagerSecretResolver:
    client_factory: Callable[[str], SecretsManagerClient] | None = None

    def read_secret(self, ref: str) -> str:
        parsed = _parse_aws_secrets_manager_ref(ref)
        client_factory = self.client_factory or _default_aws_secrets_client
        response = client_factory(parsed.region).get_secret_value(SecretId=parsed.secret_id)
        secret_value = _secret_value_from_response(response)
        if parsed.json_key is not None:
            secret_value = _json_secret_field(secret_value, parsed.json_key, ref)
        return _non_empty_secret_value(secret_value, ref)


@dataclass(frozen=True)
class VaultSecretResolver:
    token: str | None = None
    json_loader: VaultJsonLoader | None = None

    def read_secret(self, ref: str) -> str:
        parsed = _parse_vault_ref(ref)
        token = (self.token or os.environ.get("SEXTANT_VAULT_TOKEN", "")).strip()
        if not token:
            raise RuntimeError(
                "Vault secret refs require SEXTANT_VAULT_TOKEN before provider startup."
            )
        loader = self.json_loader or _load_vault_json
        payload = loader(parsed.url, {"X-Vault-Token": token})
        return _non_empty_secret_value(_vault_secret_field(payload, parsed.field, ref), ref)


@dataclass(frozen=True)
class SupabaseVaultSecretResolver:
    database_url: str | None = None
    secret_loader: SupabaseVaultSecretLoader | None = None

    def read_secret(self, ref: str) -> str:
        parsed = _parse_supabase_vault_ref(ref)
        database_url = (
            self.database_url
            or os.environ.get("SEXTANT_SUPABASE_VAULT_DATABASE_URL", "")
            or os.environ.get("SEXTANT_DATABASE_URL", "")
        ).strip()
        if not database_url:
            raise RuntimeError(
                "supabase-vault:// refs require SEXTANT_SUPABASE_VAULT_DATABASE_URL "
                "or SEXTANT_DATABASE_URL."
            )
        loader = self.secret_loader or _load_supabase_vault_secret
        return _non_empty_secret_value(loader(database_url, parsed.secret_name), ref)


@dataclass(frozen=True)
class GcpSecretManagerSecretResolver:
    client_factory: Callable[[], GcpSecretManagerClient] | None = None

    def read_secret(self, ref: str) -> str:
        parsed = _parse_gcp_secret_manager_ref(ref)
        client_factory = self.client_factory or _default_gcp_secret_manager_client
        response = client_factory().access_secret_version(request={"name": parsed.resource_name})
        return _non_empty_secret_value(_gcp_secret_payload(response, ref), ref)


@dataclass(frozen=True)
class _AwsSecretRef:
    region: str
    secret_id: str
    json_key: str | None = None


@dataclass(frozen=True)
class _VaultSecretRef:
    url: str
    field: str


@dataclass(frozen=True)
class _SupabaseVaultSecretRef:
    project_ref: str
    secret_name: str


@dataclass(frozen=True)
class _GcpSecretRef:
    resource_name: str


def openai_api_key_from_env(
    provider_label: str,
    *,
    secret_resolver: SecretResolver | None = None,
) -> str:
    secret_ref = os.environ.get("SEXTANT_LLM_API_KEY_SECRET_REF", "").strip()
    if secret_ref and not _is_supported_secret_ref(secret_ref):
        raise RuntimeError(
            f"{provider_label} provider requires SEXTANT_LLM_API_KEY_SECRET_REF to be a "
            "secret://, aws-secretsmanager://, gcp-secretmanager://, vault://, "
            "or supabase-vault:// reference when it is configured."
        )
    api_key = os.environ.get("SEXTANT_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key
    if secret_ref:
        if secret_ref.startswith("aws-secretsmanager://"):
            resolver = secret_resolver or AwsSecretsManagerSecretResolver()
            return resolver.read_secret(secret_ref)
        if secret_ref.startswith("gcp-secretmanager://"):
            resolver = secret_resolver or GcpSecretManagerSecretResolver()
            return resolver.read_secret(secret_ref)
        if secret_ref.startswith("vault://"):
            resolver = secret_resolver or VaultSecretResolver()
            return resolver.read_secret(secret_ref)
        if secret_ref.startswith("supabase-vault://"):
            resolver = secret_resolver or SupabaseVaultSecretResolver()
            return resolver.read_secret(secret_ref)
        raise RuntimeError(
            f"{provider_label} provider found SEXTANT_LLM_API_KEY_SECRET_REF={secret_ref!r}, "
            "Deployment must materialize that secret into SEXTANT_OPENAI_API_KEY or "
            "OPENAI_API_KEY before starting the API or worker."
        )
    raise RuntimeError(
        f"{provider_label} provider requires SEXTANT_OPENAI_API_KEY or OPENAI_API_KEY."
    )


def _is_supported_secret_ref(ref: str) -> bool:
    return (
        ref.startswith("secret://")
        or ref.startswith("aws-secretsmanager://")
        or ref.startswith("gcp-secretmanager://")
        or ref.startswith("vault://")
        or ref.startswith("supabase-vault://")
    )


def _parse_aws_secrets_manager_ref(ref: str) -> _AwsSecretRef:
    parsed = urlparse(ref)
    if parsed.scheme != "aws-secretsmanager":
        raise RuntimeError("AWS secret refs must use aws-secretsmanager://.")
    region = parsed.netloc.strip()
    secret_id = unquote(parsed.path.lstrip("/")).strip()
    json_key = parse_qs(parsed.query).get("json_key", [None])[0]
    if json_key is not None:
        json_key = json_key.strip() or None
    if not region or not secret_id:
        raise RuntimeError(
            "aws-secretsmanager:// refs must include a region host and secret id path."
        )
    return _AwsSecretRef(region=region, secret_id=secret_id, json_key=json_key)


def _secret_value_from_response(response: dict[str, object]) -> str:
    secret_string = response.get("SecretString")
    if isinstance(secret_string, str):
        return secret_string
    secret_binary = response.get("SecretBinary")
    if isinstance(secret_binary, bytes):
        return base64.b64decode(secret_binary).decode("utf-8")
    if isinstance(secret_binary, str):
        return base64.b64decode(secret_binary).decode("utf-8")
    raise RuntimeError("AWS Secrets Manager response did not contain SecretString or SecretBinary.")


def _parse_vault_ref(ref: str) -> _VaultSecretRef:
    parsed = urlparse(ref)
    if parsed.scheme != "vault":
        raise RuntimeError("Vault secret refs must use vault://.")
    host = parsed.netloc.strip()
    path = unquote(parsed.path.lstrip("/")).strip()
    field = parse_qs(parsed.query).get("field", [None])[0]
    if field is not None:
        field = field.strip() or None
    if not host or not path or not field:
        raise RuntimeError("vault:// refs must include host, secret path, and field query.")
    return _VaultSecretRef(url=f"https://{host}/v1/{path}", field=field)


def _parse_supabase_vault_ref(ref: str) -> _SupabaseVaultSecretRef:
    parsed = urlparse(ref)
    if parsed.scheme != "supabase-vault":
        raise RuntimeError("Supabase Vault secret refs must use supabase-vault://.")
    project_ref = parsed.netloc.strip()
    secret_name = unquote(parsed.path.lstrip("/")).strip()
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError(
            "supabase-vault:// refs must not include URL userinfo, params, query strings, "
            "or fragments."
        )
    if not project_ref or not secret_name:
        raise RuntimeError("supabase-vault:// refs must include project ref and secret name.")
    return _SupabaseVaultSecretRef(project_ref=project_ref, secret_name=secret_name)


def _parse_gcp_secret_manager_ref(ref: str) -> _GcpSecretRef:
    parsed = urlparse(ref)
    if parsed.scheme != "gcp-secretmanager":
        raise RuntimeError("GCP Secret Manager refs must use gcp-secretmanager://.")
    project_id = parsed.netloc.strip()
    secret_parts = [
        unquote(part).strip() for part in parsed.path.split("/") if unquote(part).strip()
    ]
    version = parse_qs(parsed.query, keep_blank_values=True).get("version", ["latest"])[0]
    if version is not None:
        version = version.strip() or None
    if not project_id or len(secret_parts) != 1 or not version:
        raise RuntimeError(
            "gcp-secretmanager:// refs must include project id, secret id, "
            "and optional non-empty version query."
        )
    secret_id = secret_parts[0]
    return _GcpSecretRef(
        resource_name=f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    )


def _load_vault_json(url: str, headers: dict[str, str]) -> dict[str, object]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=10) as response:  # noqa: S310 - production HTTPS Vault URL.
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Vault response was not a JSON object.")
    return payload


def _load_supabase_vault_secret(database_url: str, secret_name: str) -> str:
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            secret_value = connection.execute(
                text(
                    """
                    select decrypted_secret
                    from vault.decrypted_secrets
                    where name = :secret_name
                    order by created_at desc
                    limit 1
                    """
                ),
                {"secret_name": secret_name},
            ).scalar_one_or_none()
    finally:
        engine.dispose()
    if not isinstance(secret_value, str):
        raise RuntimeError(f"supabase-vault:// secret name={secret_name!r} was not found.")
    return secret_value


def _vault_secret_field(payload: dict[str, object], field: str, ref: str) -> str:
    for candidate in (_vault_kv2_payload(payload), payload.get("data"), payload):
        if isinstance(candidate, dict):
            candidate_map = cast(dict[object, object], candidate)
            value = candidate_map.get(field)
            if isinstance(value, str):
                return value
    raise RuntimeError(f"{ref} does not contain string field={field!r}.")


def _vault_kv2_payload(payload: dict[str, object]) -> object:
    data = payload.get("data")
    if isinstance(data, dict):
        data_map = cast(dict[object, object], data)
        return data_map.get("data")
    return None


def _gcp_secret_payload(response: object, ref: str) -> str:
    payload = getattr(response, "payload", None)
    data = getattr(payload, "data", None)
    if isinstance(data, bytes):
        return data.decode("utf-8")
    if isinstance(data, str):
        return data
    raise RuntimeError(f"{ref} response did not contain GCP Secret Manager payload data.")


def _json_secret_field(secret_value: str, json_key: str, ref: str) -> str:
    try:
        payload = json.loads(secret_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{ref} requested json_key={json_key!r}, but the secret is not JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{ref} requested json_key={json_key!r}, but the secret is not a JSON object."
        )
    value = payload.get(json_key)
    if not isinstance(value, str):
        raise RuntimeError(f"{ref} does not contain string json_key={json_key!r}.")
    return value


def _non_empty_secret_value(secret_value: str, ref: str) -> str:
    value = secret_value.strip()
    if not value:
        raise RuntimeError(f"{ref} resolved to an empty secret value.")
    return value


def _default_aws_secrets_client(region: str) -> SecretsManagerClient:
    import boto3

    return boto3.client("secretsmanager", region_name=region)


def _default_gcp_secret_manager_client() -> GcpSecretManagerClient:
    from google.cloud import secretmanager

    return secretmanager.SecretManagerServiceClient()
