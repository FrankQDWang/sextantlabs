from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sextant.infra.provider_secrets import (
    AwsSecretsManagerSecretResolver,
    GcpSecretManagerSecretResolver,
    SupabaseVaultSecretResolver,
    VaultSecretResolver,
)


class ConfigError(RuntimeError):
    pass


class SecretReadError(RuntimeError):
    pass


class SecretResolver(Protocol):
    def read_secret(self, ref: str) -> str: ...


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
SUPPORTED_SECRET_SCHEMES = {
    "aws-secretsmanager",
    "gcp-secretmanager",
    "supabase-vault",
    "vault",
}


@dataclass(frozen=True)
class SecretManagerProbeConfig:
    secret_ref: str
    secret_ref_scheme: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SecretManagerProbeConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "secret-manager access proof."
            )
        secret_ref = env.get("SEXTANT_SECRET_MANAGER_REF", "").strip()
        if not secret_ref:
            raise ConfigError("SEXTANT_SECRET_MANAGER_REF is required.")
        scheme = _validate_secret_ref(secret_ref)
        return cls(secret_ref=secret_ref, secret_ref_scheme=scheme)


def _validate_secret_ref(secret_ref: str) -> str:
    parsed = urlparse(secret_ref)
    if parsed.scheme not in SUPPORTED_SECRET_SCHEMES:
        raise ConfigError(
            "SEXTANT_SECRET_MANAGER_REF must be aws-secretsmanager://, "
            "gcp-secretmanager://, vault://, or supabase-vault://."
        )
    if parsed.scheme == "aws-secretsmanager":
        _validate_aws_ref(parsed)
    elif parsed.scheme == "gcp-secretmanager":
        _validate_gcp_ref(parsed)
    elif parsed.scheme == "vault":
        _validate_vault_ref(parsed)
    elif parsed.scheme == "supabase-vault":
        _validate_supabase_vault_ref(parsed)
    return parsed.scheme


def _validate_aws_ref(parsed) -> None:
    json_key = parse_qs(parsed.query).get("json_key", [None])[0]
    secret_id = unquote(parsed.path.lstrip("/")).strip()
    if not parsed.netloc.strip() or not secret_id:
        raise ConfigError("aws-secretsmanager:// refs must include region and secret id.")
    if json_key is not None and not json_key.strip():
        raise ConfigError("aws-secretsmanager:// json_key must be non-empty when provided.")


def _validate_gcp_ref(parsed) -> None:
    version = parse_qs(parsed.query, keep_blank_values=True).get("version", ["latest"])[0]
    secret_parts = [
        unquote(part).strip() for part in parsed.path.split("/") if unquote(part).strip()
    ]
    if not parsed.netloc.strip() or len(secret_parts) != 1:
        raise ConfigError("gcp-secretmanager:// refs must include project id and secret id.")
    if version is None or not version.strip():
        raise ConfigError("gcp-secretmanager:// version must be non-empty when provided.")


def _validate_vault_ref(parsed) -> None:
    field = parse_qs(parsed.query).get("field", [None])[0]
    if not parsed.netloc.strip() or not unquote(parsed.path.lstrip("/")).strip():
        raise ConfigError("vault:// refs must include host and secret path.")
    if field is None or not field.strip():
        raise ConfigError("vault:// refs must include a non-empty field query.")
    _validate_hosted_hostname("vault:// host", parsed.hostname or "")


def _validate_supabase_vault_ref(parsed) -> None:
    if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError(
            "supabase-vault:// refs must not include URL userinfo, params, query strings, "
            "or fragments."
        )
    if not parsed.netloc.strip() or not unquote(parsed.path.lstrip("/")).strip():
        raise ConfigError("supabase-vault:// refs must include project ref and secret name.")


def _validate_hosted_hostname(name: str, hostname: str) -> None:
    host = hostname.strip().lower()
    if not host or host in LOCAL_HOSTS or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS target.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS target.")


def resolver_for_secret_ref(secret_ref: str) -> SecretResolver:
    if secret_ref.startswith("aws-secretsmanager://"):
        return AwsSecretsManagerSecretResolver()
    if secret_ref.startswith("gcp-secretmanager://"):
        return GcpSecretManagerSecretResolver()
    if secret_ref.startswith("vault://"):
        return VaultSecretResolver()
    if secret_ref.startswith("supabase-vault://"):
        return SupabaseVaultSecretResolver()
    raise ConfigError(
        "SEXTANT_SECRET_MANAGER_REF must be aws-secretsmanager://, "
        "gcp-secretmanager://, vault://, or supabase-vault://."
    )


def run_secret_manager_probe(
    config: SecretManagerProbeConfig,
    *,
    resolver: SecretResolver | None = None,
) -> dict[str, object]:
    selected_resolver = resolver or resolver_for_secret_ref(config.secret_ref)
    try:
        secret_value = selected_resolver.read_secret(config.secret_ref)
    except RuntimeError as exc:
        raise SecretReadError(str(exc)) from exc
    secret_bytes = secret_value.encode("utf-8")
    if not secret_bytes:
        raise SecretReadError("SEXTANT_SECRET_MANAGER_REF resolved to an empty secret.")
    return {
        "status": "pass",
        "secret_ref_scheme": config.secret_ref_scheme,
        "secret_value_status": "resolved_non_empty",
    }


def render_secret_manager_probe_cli_evidence() -> str:
    return json.dumps(
        {
            "secret_manager_access": "verified",
            "status": "pass",
        },
        sort_keys=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read the configured hosted secret-manager ref through Sextant's "
            "production secret resolvers, then emit redacted JSON proof evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted secret-manager configuration without reading the secret.",
    )
    args = parser.parse_args()

    try:
        config = SecretManagerProbeConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-secret-manager-config-ok")
            return 0
        run_secret_manager_probe(config)
        print(render_secret_manager_probe_cli_evidence())
        return 0
    except (ConfigError, SecretReadError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
