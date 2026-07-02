from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from sextant.infra.object_store import S3ObjectStore

SCRIPT_PATH = Path("backend/scripts/hosted_object_store_probe.py")


class _Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _RecordingS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, **kwargs: object) -> None:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        body = kwargs["Body"]
        assert isinstance(body, bytes)
        self.objects[(bucket, key)] = body

    def get_object(self, **kwargs: object) -> dict[str, object]:
        bucket = str(kwargs["Bucket"])
        key = str(kwargs["Key"])
        return {"Body": _Body(self.objects[(bucket, key)])}


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_object_store_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_OBJECT_STORE_ROOT": "s3://sextant-prod/objects",
        "SEXTANT_OBJECT_STORE_PROBE_PREFIX": "hosted-readiness/object-store",
    }
    env.update(overrides)
    return env


def test_hosted_object_store_config_rejects_non_production_or_local_runtime() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.ObjectStoreProbeConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_OBJECT_STORE_ROOT"):
        probe.ObjectStoreProbeConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_ROOT=""))

    with pytest.raises(probe.ConfigError, match="s3://"):
        probe.ObjectStoreProbeConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_ROOT="./objects"))

    with pytest.raises(probe.ConfigError, match="hosted HTTPS URL"):
        probe.ObjectStoreProbeConfig.from_env(
            _probe_env(SEXTANT_S3_ENDPOINT_URL="http://127.0.0.1:9000")
        )

    with pytest.raises(probe.ConfigError, match="probe prefix"):
        probe.ObjectStoreProbeConfig.from_env(_probe_env(SEXTANT_OBJECT_STORE_PROBE_PREFIX="../x"))

    config = probe.ObjectStoreProbeConfig.from_env(
        _probe_env(SEXTANT_S3_ENDPOINT_URL="https://s3.us-east-1.amazonaws.com")
    )

    assert config.object_store_root == "s3://sextant-prod/objects"
    assert config.probe_prefix == "hosted-readiness/object-store"
    assert config.s3_endpoint_url == "https://s3.us-east-1.amazonaws.com"


def test_hosted_object_store_probe_round_trips_without_exposing_payload() -> None:
    probe = _load_probe_module()
    config = probe.ObjectStoreProbeConfig.from_env(_probe_env())
    client = _RecordingS3Client()
    store = S3ObjectStore(bucket="sextant-prod", prefix="objects", client=client)

    evidence = probe.run_object_store_probe(
        config,
        object_store=store,
        probe_id=UUID("00000000-0000-4000-8000-0000000000aa"),
    )
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["object_store_root"] == "s3://sextant-prod/objects"
    assert evidence["proof_object_ref"] == (
        "s3://sextant-prod/objects/hosted-readiness/object-store/"
        "00000000-0000-4000-8000-0000000000aa.txt"
    )
    assert evidence["byte_count"] > 0
    assert evidence["payload_sha256"]
    assert "hosted object-store read/write probe" not in encoded


def test_hosted_object_store_check_config_cli() -> None:
    valid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    invalid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(SEXTANT_S3_ENDPOINT_URL="https://localhost:9000"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-object-store-config-ok"
    assert invalid.returncode == 1
    assert "hosted HTTPS URL" in invalid.stderr
