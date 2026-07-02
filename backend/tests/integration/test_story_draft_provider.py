from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.contracts.story_draft import StoryDraftRequest
from sextant.contracts.use_cases import WritingContextPackOutput
from sextant.infra.story_draft_openai import OpenAIStoryDraftOutput, OpenAIStoryDraftProvider
from sextant.infra.story_draft_provider import story_draft_provider_from_env
from sextant.skills.local_story_draft import LocalStoryDraftProvider


class _FakeResponses:
    def __init__(
        self,
        parsed: OpenAIStoryDraftOutput,
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
        parsed: OpenAIStoryDraftOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.responses = _FakeResponses(parsed, usage)


class _FakeChatCompletions:
    def __init__(
        self,
        parsed: OpenAIStoryDraftOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.parsed = parsed
        self.usage = usage
        self.kwargs: dict[str, object] = {}

    def parse(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.parsed))],
            usage=self.usage,
        )


class _FakeChat:
    def __init__(
        self,
        parsed: OpenAIStoryDraftOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.completions = _FakeChatCompletions(parsed, usage)


class _FakeChatOpenAIClient:
    def __init__(
        self,
        parsed: OpenAIStoryDraftOutput,
        usage: SimpleNamespace | None = None,
    ) -> None:
        self.chat = _FakeChat(parsed, usage)


def test_openai_story_draft_provider_parses_structured_response() -> None:
    parsed = OpenAIStoryDraftOutput(
        text="米拉停在门口。",
        finish_reason="complete",
        mode="rewrite_span",
        prose_contract_id="contract-1",
        review_cues=[
            {
                "risk_level": "medium",
                "risk_type": "pov_risk",
                "summary": "这里可能越过视角。",
                "can_offer_to_author": True,
                "maps_to_review_type_if_accepted": "pov_conflict",
            }
        ],
    )
    client = _FakeOpenAIClient(parsed)
    provider = OpenAIStoryDraftProvider(model="gpt-5", client=client)

    result = provider.draft(_story_request())

    assert result.text == "米拉停在门口。"
    assert result.finish_reason == "complete"
    assert result.structured_output["text"] == "米拉停在门口。"
    assert result.structured_output["mode"] == "rewrite_span"
    assert result.structured_output["prose_contract_id"] == "contract-1"
    assert result.review_cues[0]["risk_type"] == "pov_risk"
    assert client.responses.kwargs["model"] == "gpt-5"
    assert client.responses.kwargs["text_format"] is OpenAIStoryDraftOutput
    messages = client.responses.kwargs["input"]
    assert isinstance(messages, list)
    assert "current_text_window" in messages[1]["content"]


def test_openai_story_draft_provider_can_use_chat_compatible_structured_response() -> None:
    parsed = OpenAIStoryDraftOutput(
        text="米拉停在门口。",
        finish_reason="complete",
        mode="rewrite_span",
        prose_contract_id="contract-1",
        review_cues=[],
    )
    client = _FakeChatOpenAIClient(parsed)
    provider = OpenAIStoryDraftProvider(
        model="deepseek-v4-pro",
        client=client,
        api_style="chat",
        extra_body={"reasoning_effort": "high"},
    )

    result = provider.draft(_story_request())

    assert result.text == "米拉停在门口。"
    kwargs = client.chat.completions.kwargs
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["response_format"] is OpenAIStoryDraftOutput
    assert kwargs["extra_body"] == {"reasoning_effort": "high"}
    messages = kwargs["messages"]
    assert isinstance(messages, list)
    assert "current_text_window" in messages[1]["content"]


def test_openai_story_draft_provider_records_usage_and_cost_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = OpenAIStoryDraftOutput(
        text="米拉停在门口。",
        finish_reason="complete",
        mode="rewrite_span",
        prose_contract_id="contract-1",
        review_cues=[],
    )
    client = _FakeOpenAIClient(
        parsed,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500, total_tokens=1500),
    )
    metrics = MetricsRegistry()
    monkeypatch.setenv("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS", "200")
    monkeypatch.setenv("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS", "800")
    provider = OpenAIStoryDraftProvider(model="gpt-5", client=client, metrics=metrics)

    provider.draft(_story_request())

    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_story_draft",token_type="input"} 1000'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="gpt-5",provider="openai",'
        'skill="openai_story_draft",token_type="output"} 500'
    ) in rendered
    assert (
        'sextant_provider_cost_microusd_total{model="gpt-5",provider="openai",'
        'skill="openai_story_draft"} 600'
    ) in rendered
    assert "米拉停在门口" not in rendered


def test_story_draft_provider_factory_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEXTANT_LLM_PROVIDER", raising=False)

    provider = story_draft_provider_from_env()

    assert isinstance(provider, LocalStoryDraftProvider)


def test_story_draft_provider_factory_rejects_local_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "local")

    with pytest.raises(RuntimeError, match="SEXTANT_LLM_PROVIDER"):
        story_draft_provider_from_env()


def test_story_draft_provider_factory_requires_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_LLM_MODEL", "gpt-5")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OpenAI story draft provider requires"):
        story_draft_provider_from_env()


def test_story_draft_provider_factory_reports_secret_ref_materialization_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_LLM_MODEL", "gpt-5")
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "secret://prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SEXTANT_LLM_API_KEY_SECRET_REF"):
        story_draft_provider_from_env()


def test_story_draft_provider_factory_rejects_malformed_secret_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SEXTANT_LLM_MODEL", "gpt-5")
    monkeypatch.setenv("SEXTANT_LLM_API_KEY_SECRET_REF", "prod/openai-api-key")
    monkeypatch.delenv("SEXTANT_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="secret://"):
        story_draft_provider_from_env()


def _story_request() -> StoryDraftRequest:
    context_pack = WritingContextPackOutput(
        context_pack_id=uuid4(),
        schema_version="writing-context-pack.v1",
        current_position={"mode": "rewrite_span"},
        canonical_context={"facts": []},
        pov_constraint={"forbidden_knowledge": []},
        active_characters=[],
        character_agency_state={"status": "not_computed"},
        recent_events=[],
        character_knowledge=[],
        object_location_state=[],
        open_threads=[],
        risk_context={"facts": []},
        style_memory={"samples": []},
        evidence_refs=[],
    )
    return StoryDraftRequest(
        actor_intent="改写这里",
        current_text_window="米拉停在门口。",
        context_pack=context_pack,
        prose_rendering_contract={
            "mode": "rewrite_span",
            "contract_id": "contract-1",
        },
    )
