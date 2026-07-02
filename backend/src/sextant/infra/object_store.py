from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse

from sextant.infra.runtime_config import validate_object_store_uri_for_release


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def get_object(self, **kwargs: object) -> dict[str, Any]: ...


class LocalObjectStore:
    scheme = "object"
    authority = "local"

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put_text(self, name: str, text: str) -> str:
        path = self._resolve_name(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return f"object://local/{quote(path.relative_to(self._root).as_posix())}"

    def get_text(self, ref: str) -> str:
        parsed = urlparse(ref)
        if parsed.scheme != self.scheme or parsed.netloc != self.authority:
            raise ValueError(f"Unsupported object ref: {ref}")
        path = self._resolve_name(unquote(parsed.path.lstrip("/")))
        return path.read_text(encoding="utf-8")

    def _resolve_name(self, name: str) -> Path:
        candidate = (self._root / name.lstrip("/")).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("Object name escapes the object store root.")
        return candidate


class S3ObjectStore:
    scheme = "s3"

    def __init__(self, *, bucket: str, prefix: str = "", client: S3Client | None = None) -> None:
        if not bucket:
            raise ValueError("S3 object store bucket is required.")
        self._bucket = bucket
        self._prefix = _clean_prefix(prefix)
        self._client = client or _create_s3_client()

    @classmethod
    def from_uri(cls, uri: str, *, client: S3Client | None = None) -> S3ObjectStore:
        parsed = urlparse(uri)
        if parsed.scheme != cls.scheme or not parsed.netloc:
            raise ValueError(f"Unsupported S3 object store URI: {uri}")
        return cls(bucket=parsed.netloc, prefix=unquote(parsed.path.lstrip("/")), client=client)

    def put_text(self, name: str, text: str) -> str:
        key = self._key_for_name(name)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=text.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return f"s3://{self._bucket}/{quote(key, safe='/')}"

    def get_text(self, ref: str) -> str:
        key = self._key_from_ref(ref)
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        payload = body.read()
        if not isinstance(payload, bytes):
            raise ValueError("S3 object body did not return bytes.")
        return payload.decode("utf-8")

    def _key_for_name(self, name: str) -> str:
        clean_name = _clean_name(name)
        if not self._prefix:
            return clean_name
        return f"{self._prefix}/{clean_name}"

    def _key_from_ref(self, ref: str) -> str:
        parsed = urlparse(ref)
        if parsed.scheme != self.scheme or parsed.netloc != self._bucket:
            raise ValueError(f"Unsupported object ref: {ref}")
        key = unquote(parsed.path.lstrip("/"))
        if not _key_is_under_prefix(key, self._prefix):
            raise ValueError(f"Unsupported object ref: {ref}")
        return key


def object_store_from_uri(uri: str | None, *, s3_client: S3Client | None = None):
    value = validate_object_store_uri_for_release(uri or "./.sextant/objects")
    if value.startswith("s3://"):
        return S3ObjectStore.from_uri(value, client=s3_client)
    return LocalObjectStore(Path(value))


def _create_s3_client() -> S3Client:
    import boto3
    from botocore.config import Config

    kwargs: dict[str, object] = {
        "config": Config(
            connect_timeout=_positive_float_env("SEXTANT_S3_CONNECT_TIMEOUT_SECONDS", 10.0),
            read_timeout=_positive_float_env("SEXTANT_S3_READ_TIMEOUT_SECONDS", 30.0),
            retries={
                "max_attempts": _positive_int_env("SEXTANT_S3_MAX_ATTEMPTS", 3),
                "mode": "standard",
            },
        )
    }
    if region := os.environ.get("SEXTANT_AWS_REGION") or os.environ.get("AWS_REGION"):
        kwargs["region_name"] = region
    if endpoint_url := os.environ.get("SEXTANT_S3_ENDPOINT_URL"):
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive number.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive number.")
    return value


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _clean_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    return _clean_name(prefix)


def _clean_name(name: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(name.lstrip("/")).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("Object name escapes the object store root.")
        parts.append(part)
    if not parts:
        raise ValueError("Object name is required.")
    return "/".join(parts)


def _key_is_under_prefix(key: str, prefix: str) -> bool:
    if not prefix:
        return True
    return key == prefix or key.startswith(f"{prefix}/")
