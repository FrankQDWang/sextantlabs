from __future__ import annotations

from pathlib import Path

import pytest
from sextant.infra.object_store import LocalObjectStore, S3ObjectStore, object_store_from_uri


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _RecordingS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> None:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[(bucket, key)] = body
        self.put_calls.append(kwargs)

    def get_object(self, **kwargs: object) -> dict[str, object]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        return {"Body": _Body(self.objects[(bucket, key)])}


def test_local_object_store_rejects_path_escape(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")

    with pytest.raises(ValueError, match="escapes"):
        store.put_text("../outside.txt", "nope")


def test_s3_object_store_round_trips_text_with_stable_refs() -> None:
    client = _RecordingS3Client()
    store = S3ObjectStore(bucket="sextant-prod", prefix="source", client=client)

    ref = store.put_text("raw/chapter 1.txt", "Mira keeps the map.")

    assert ref == "s3://sextant-prod/source/raw/chapter%201.txt"
    assert client.put_calls[0]["ContentType"] == "text/plain; charset=utf-8"
    assert store.get_text(ref) == "Mira keeps the map."


def test_s3_object_store_rejects_other_bucket_and_key_escape() -> None:
    store = S3ObjectStore(bucket="sextant-prod", prefix="source", client=_RecordingS3Client())

    with pytest.raises(ValueError, match="Unsupported object ref"):
        store.get_text("s3://other-bucket/source/raw/chapter.txt")
    with pytest.raises(ValueError, match="escapes"):
        store.put_text("../outside.txt", "nope")


def test_object_store_factory_uses_s3_for_s3_uri() -> None:
    client = _RecordingS3Client()
    store = object_store_from_uri("s3://sextant-prod/source", s3_client=client)

    ref = store.put_text("accepted/fragment.txt", "Accepted")

    assert isinstance(store, S3ObjectStore)
    assert ref == "s3://sextant-prod/source/accepted/fragment.txt"
    assert store.get_text(ref) == "Accepted"


def test_object_store_factory_rejects_local_default_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="SEXTANT_OBJECT_STORE_ROOT"):
        object_store_from_uri(None)


def test_object_store_factory_rejects_local_path_in_production(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")

    with pytest.raises(RuntimeError, match="SEXTANT_OBJECT_STORE_ROOT"):
        object_store_from_uri(str(tmp_path / "objects"))
