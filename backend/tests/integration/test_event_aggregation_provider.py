from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.contracts.event_aggregation import EventAggregationAdjudicationRequest
from sextant.infra.event_aggregation_openai import (
    OpenAIEventAggregationOutput,
    OpenAIEventAggregationProvider,
)
from sextant.infra.event_aggregation_provider import event_aggregation_provider_from_env
from sextant.skills.local_event_aggregation import LocalEventAggregationProvider


class _FakeResponses:
    def __init__(
        self,
        parsed: OpenAIEventAggregationOutput,
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
        parsed: OpenAIEventAggregationOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.responses = _FakeResponses(parsed, usage)


def test_openai_event_aggregation_provider_parses_structured_response() -> None:
    existing_span_id = uuid4()
    candidate_span_id = uuid4()
    parsed = OpenAIEventAggregationOutput(
        decision="same_event",
        confidence=0.84,
        rationale="Both passages describe the same map transfer.",
        evidence_span_ids=[str(existing_span_id), str(candidate_span_id)],
    )
    client = _FakeOpenAIClient(parsed)
    provider = OpenAIEventAggregationProvider(model="gpt-5", client=client)

    result = provider.adjudicate(
        _event_request(
            existing_span_id=str(existing_span_id),
            candidate_span_id=str(candidate_span_id),
        )
    )

    assert result.decision == "same_event"
    assert result.confidence == 0.84
    assert result.evidence_span_ids == [str(existing_span_id), str(candidate_span_id)]
    assert client.responses.kwargs["model"] == "gpt-5"
    assert client.responses.kwargs["text_format"] is OpenAIEventAggregationOutput
    messages = client.responses.kwargs["input"]
    assert isinstance(messages, list)
    payload = json.loads(messages[1]["content"])
    assert payload["candidate_event_type"] == "object_transfer"
    assert payload["existing_event_evidence_span_ids"] == [str(existing_span_id)]
    assert "Return only one of same_event" in messages[0]["content"]


def test_openai_event_aggregation_provider_records_usage_and_cost_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_span_id = uuid4()
    candidate_span_id = uuid4()
    parsed = OpenAIEventAggregationOutput(
        decision="related_but_distinct",
        confidence=0.7,
        rationale="The same object appears, but the actions are separate.",
        evidence_span_ids=[str(existing_span_id), str(candidate_span_id)],
    )
    client = _FakeOpenAIClient(
        parsed,
        usage=SimpleNamespace(input_tokens=80, output_tokens=20, total_tokens=100),
    )
    metrics = MetricsRegistry()
    monkeypatch.setenv("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS", "50")
    monkeypatch.setenv("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS", "150")
    provider = OpenAIEventAggregationProvider(model="gpt-5", client=client, metrics=metrics)

    provider.adjudicate(
        _event_request(
            existing_span_id=str(existing_span_id),
            candidate_span_id=str(candidate_span_id),
        )
    )

    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_event_aggregation",token_type="input"} 80'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_event_aggregation",token_type="output"} 20'
    ) in rendered
    assert (
        'sextant_provider_cost_microusd_total{model="gpt-5",provider="openai",'
        'skill="openai_event_aggregation"} 7'
    ) in rendered
    assert "Lantern Map" not in rendered


def test_event_aggregation_provider_factory_defaults_to_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_PROVIDER", raising=False)

    provider = event_aggregation_provider_from_env()

    assert isinstance(provider, LocalEventAggregationProvider)


def test_event_aggregation_provider_factory_rejects_local_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER", "local")

    with pytest.raises(RuntimeError, match="SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER"):
        event_aggregation_provider_from_env()


def test_event_aggregation_provider_factory_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_EVENT_AGGREGATION_LLM_MODEL", "gpt-5")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OpenAI event aggregation provider requires"):
        event_aggregation_provider_from_env()


def test_event_aggregation_provider_factory_requires_openai_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("SEXTANT_EVENT_AGGREGATION_LLM_MODEL", raising=False)
    monkeypatch.delenv("SEXTANT_LLM_MODEL", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_EVENT_AGGREGATION_LLM_MODEL"):
        event_aggregation_provider_from_env()


def _event_request(
    *,
    existing_span_id: str,
    candidate_span_id: str,
) -> EventAggregationAdjudicationRequest:
    return EventAggregationAdjudicationRequest(
        existing_event_id=uuid4(),
        existing_event_type="object_transfer",
        existing_event_title="Mira handed Kestrel the Lantern Map",
        existing_event_summary="Mira handed Kestrel the Lantern Map.",
        existing_event_participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        existing_event_objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        existing_event_evidence_span_ids=[existing_span_id],
        existing_event_source_text="Mira handed Kestrel the Lantern Map.",
        candidate_id=uuid4(),
        candidate_event_type="object_transfer",
        candidate_summary="Kestrel received the Lantern Map from Mira.",
        candidate_participants=[
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
            {"type": "character", "id": "mira", "label": "Mira"},
        ],
        candidate_objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        candidate_evidence_span_ids=[candidate_span_id],
        candidate_source_text="Kestrel received the Lantern Map from Mira.",
    )
