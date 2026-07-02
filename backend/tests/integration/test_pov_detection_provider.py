from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.contracts.pov_detection import PovDetectionMention, PovDetectionRequest
from sextant.infra.pov_detection_openai import OpenAIPovDetectionOutput, OpenAIPovDetectionProvider
from sextant.infra.pov_detection_provider import pov_detection_provider_from_env
from sextant.skills.local_pov_detection import LocalPovDetectionProvider


class _FakeResponses:
    def __init__(
        self,
        parsed: OpenAIPovDetectionOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.parsed = parsed
        self.usage = usage
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed, usage=self.usage)


class _FakeOpenAIClient:
    def __init__(
        self,
        parsed: OpenAIPovDetectionOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.responses = _FakeResponses(parsed, usage)


def test_openai_pov_detection_provider_parses_structured_response() -> None:
    source_span_id = uuid4()
    scene_id = uuid4()
    parsed = OpenAIPovDetectionOutput(
        pov_character_name="Mira",
        pov_mode="third_limited",
        confidence=0.76,
        evidence_span_ids=[str(source_span_id)],
        uncertainty_reason=None,
    )
    client = _FakeOpenAIClient(parsed)
    provider = OpenAIPovDetectionProvider(model="gpt-5", client=client)

    result = provider.detect(
        PovDetectionRequest(
            source_span_id=source_span_id,
            scene_id=scene_id,
            text="Mira walked beside Orrin in silence.",
            mentions=[
                PovDetectionMention(
                    raw_text="Mira",
                    mention_type="character",
                    canonical_entity_id=str(uuid4()),
                ),
                PovDetectionMention(
                    raw_text="Orrin",
                    mention_type="character",
                    canonical_entity_id=str(uuid4()),
                ),
            ],
        )
    )

    assert result.pov_character_name == "Mira"
    assert result.pov_mode == "third_limited"
    assert result.confidence == 0.76
    assert result.evidence_span_ids == [str(source_span_id)]
    assert client.responses.kwargs["model"] == "gpt-5"
    assert client.responses.kwargs["text_format"] is OpenAIPovDetectionOutput
    messages = client.responses.kwargs["input"]
    assert isinstance(messages, list)
    payload = json.loads(messages[1]["content"])
    assert payload["source_span_id"] == str(source_span_id)
    assert payload["scene_id"] == str(scene_id)
    assert payload["mentions"][0]["raw_text"] == "Mira"
    assert "Never invent canon" in messages[0]["content"]


def test_openai_pov_detection_provider_records_usage_and_cost_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_span_id = uuid4()
    scene_id = uuid4()
    parsed = OpenAIPovDetectionOutput(
        pov_character_name="Mira",
        pov_mode="third_limited",
        confidence=0.76,
        evidence_span_ids=[str(source_span_id)],
        uncertainty_reason=None,
    )
    client = _FakeOpenAIClient(
        parsed,
        usage={"input_tokens": 40, "output_tokens": 10, "total_tokens": 50},
    )
    metrics = MetricsRegistry()
    monkeypatch.setenv("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS", "50")
    monkeypatch.setenv("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS", "200")
    provider = OpenAIPovDetectionProvider(model="gpt-5", client=client, metrics=metrics)

    provider.detect(
        PovDetectionRequest(
            source_span_id=source_span_id,
            scene_id=scene_id,
            text="Mira walked beside Orrin in silence.",
            mentions=[],
        )
    )

    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_pov_detection",token_type="input"} 40'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_pov_detection",token_type="output"} 10'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_pov_detection",token_type="total"} 50'
    ) in rendered
    assert (
        'sextant_provider_cost_microusd_total{model="gpt-5",provider="openai",'
        'skill="openai_pov_detection"} 4'
    ) in rendered
    assert "Orrin" not in rendered


def test_pov_detection_provider_factory_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEXTANT_POV_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_PROVIDER", raising=False)

    provider = pov_detection_provider_from_env()

    assert isinstance(provider, LocalPovDetectionProvider)


def test_pov_detection_provider_factory_rejects_local_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_POV_LLM_PROVIDER", "local")

    with pytest.raises(RuntimeError, match="SEXTANT_POV_LLM_PROVIDER"):
        pov_detection_provider_from_env()


def test_pov_detection_provider_factory_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_POV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_POV_LLM_MODEL", "gpt-5")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OpenAI POV detection provider requires"):
        pov_detection_provider_from_env()


def test_pov_detection_provider_factory_reports_secret_ref_materialization_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_POV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_POV_LLM_MODEL", "gpt-5")
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "secret://prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_LLM_API_KEY_SECRET_REF"):
        pov_detection_provider_from_env()


def test_pov_detection_provider_factory_requires_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_POV_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SEXTANT_POV_LLM_MODEL", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_POV_LLM_MODEL"):
        pov_detection_provider_from_env()
