from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sextant.infra.object_store import object_store_from_uri


class ConfigError(RuntimeError):
    pass


class ProbeError(RuntimeError):
    pass


class TextObjectStore(Protocol):
    def put_text(self, name: str, text: str) -> str: ...

    def get_text(self, ref: str) -> str: ...


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
DEFAULT_PROBE_PREFIX = "hosted-readiness/object-store"


@dataclass(frozen=True)
class ObjectStoreProbeConfig:
    object_store_root: str
    probe_prefix: str
    s3_endpoint_url: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ObjectStoreProbeConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "object-store read/write proof."
            )
        object_store_root = env.get("SEXTANT_OBJECT_STORE_ROOT", "").strip()
        if not object_store_root:
            raise ConfigError("SEXTANT_OBJECT_STORE_ROOT is required.")
        if not object_store_root.startswith("s3://"):
            raise ConfigError("SEXTANT_OBJECT_STORE_ROOT must be an s3:// URI.")

        s3_endpoint_url = env.get("SEXTANT_S3_ENDPOINT_URL", "").strip() or None
        if s3_endpoint_url is not None:
            _validate_hosted_https_url("SEXTANT_S3_ENDPOINT_URL", s3_endpoint_url)

        return cls(
            object_store_root=object_store_root,
            probe_prefix=_validate_probe_prefix(
                env.get("SEXTANT_OBJECT_STORE_PROBE_PREFIX", DEFAULT_PROBE_PREFIX)
            ),
            s3_endpoint_url=s3_endpoint_url,
        )


def _validate_probe_prefix(value: str) -> str:
    prefix = value.strip().strip("/")
    if not prefix:
        raise ConfigError("SEXTANT_OBJECT_STORE_PROBE_PREFIX probe prefix is required.")
    parts: list[str] = []
    for part in PurePosixPath(prefix).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ConfigError("SEXTANT_OBJECT_STORE_PROBE_PREFIX probe prefix must not escape.")
        parts.append(part)
    if not parts:
        raise ConfigError("SEXTANT_OBJECT_STORE_PROBE_PREFIX probe prefix is required.")
    return "/".join(parts)


def _validate_hosted_https_url(name: str, value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or not parsed.hostname:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    host = parsed.hostname.strip().lower()
    if host in LOCAL_HOSTS or host.endswith(".local"):
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_unspecified:
        raise ConfigError(f"{name} must be a hosted HTTPS URL.")


def run_object_store_probe(
    config: ObjectStoreProbeConfig,
    *,
    object_store: TextObjectStore | None = None,
    probe_id: UUID | None = None,
) -> dict[str, object]:
    resolved_probe_id = probe_id or uuid4()
    store = object_store or object_store_from_uri(config.object_store_root)
    payload = (
        "sextant hosted object-store read/write probe\n"
        f"id={resolved_probe_id}\n"
        f"root={config.object_store_root}\n"
    )
    object_name = f"{config.probe_prefix}/{resolved_probe_id}.txt"
    ref = store.put_text(object_name, payload)
    read_back = store.get_text(ref)
    if read_back != payload:
        raise ProbeError("Object-store read/write probe read-back payload mismatch.")
    encoded = payload.encode("utf-8")
    return {
        "status": "pass",
        "object_store_root": config.object_store_root,
        "proof_object_ref": ref,
        "probe_prefix": config.probe_prefix,
        "byte_count": len(encoded),
        "payload_sha256": hashlib.sha256(encoded).hexdigest(),
        "s3_endpoint_host": urlparse(config.s3_endpoint_url).hostname
        if config.s3_endpoint_url
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write and read a hosted S3 object through Sextant's production "
            "object-store adapter, then emit JSON proof evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted object-store configuration without writing or reading objects.",
    )
    args = parser.parse_args()

    try:
        config = ObjectStoreProbeConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-object-store-config-ok")
            return 0
        print(json.dumps(run_object_store_probe(config), sort_keys=True))
        return 0
    except (ConfigError, ProbeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
