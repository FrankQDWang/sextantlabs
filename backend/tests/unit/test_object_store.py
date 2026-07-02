from __future__ import annotations

import sys
from types import SimpleNamespace

from sextant.infra.object_store import _create_s3_client


def test_create_s3_client_uses_bounded_timeouts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(service_name: str, **kwargs: object) -> object:
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))
    monkeypatch.delenv("SEXTANT_S3_CONNECT_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SEXTANT_S3_READ_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("SEXTANT_S3_MAX_ATTEMPTS", raising=False)

    _create_s3_client()

    assert captured["service_name"] == "s3"
    config = captured["config"]
    assert config.connect_timeout == 10
    assert config.read_timeout == 30
    assert config.retries["max_attempts"] == 3
