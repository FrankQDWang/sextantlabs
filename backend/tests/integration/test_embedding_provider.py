from __future__ import annotations

from types import SimpleNamespace

import pytest
from sextant.common.observability import MetricsRegistry, render_prometheus_metrics
from sextant.infra.embedding_openai import OpenAIEmbeddingProvider
from sextant.infra.embedding_provider import embedding_provider_from_env
from sextant.skills.local_embedding import LocalEmbeddingProvider


class _FakeEmbeddings:
    def __init__(self, *, usage: SimpleNamespace | None = None) -> None:
        self.usage = usage
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[0.1, 0.2, 0.3]),
                SimpleNamespace(embedding=[0.4, 0.5, 0.6]),
            ],
            usage=self.usage,
        )


class _FakeOpenAIClient:
    def __init__(self, *, usage: SimpleNamespace | None = None) -> None:
        self.embeddings = _FakeEmbeddings(usage=usage)


def test_openai_embedding_provider_records_usage_and_cost_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeOpenAIClient(
        usage=SimpleNamespace(prompt_tokens=120, total_tokens=120),
    )
    metrics = MetricsRegistry()
    monkeypatch.setenv("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS", "25")
    monkeypatch.setenv("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS", "100")
    provider = OpenAIEmbeddingProvider(
        model="text-embedding-3-small",
        dimensions=3,
        client=client,
        metrics=metrics,
    )

    vectors = provider.embed_texts(["Secret informant note.", "Harbor map fragment."])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert client.embeddings.kwargs == {
        "model": "text-embedding-3-small",
        "input": ["Secret informant note.", "Harbor map fragment."],
        "dimensions": 3,
    }
    rendered = render_prometheus_metrics(metrics.snapshot())
    assert (
        'sextant_provider_tokens_total{model="text-embedding-3-small",'
        'provider="openai",skill="openai_embedding",token_type="input"} 120'
    ) in rendered
    assert (
        'sextant_provider_tokens_total{model="text-embedding-3-small",'
        'provider="openai",skill="openai_embedding",token_type="total"} 120'
    ) in rendered
    assert (
        'sextant_provider_cost_microusd_total{model="text-embedding-3-small",'
        'provider="openai",skill="openai_embedding"} 3'
    ) in rendered
    assert "Secret informant" not in rendered
    assert "Harbor map" not in rendered


def test_embedding_provider_factory_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEXTANT_EMBEDDING_PROVIDER", raising=False)

    provider = embedding_provider_from_env()

    assert isinstance(provider, LocalEmbeddingProvider)


def test_embedding_provider_factory_rejects_local_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEXTANT_RELEASE_ENVIRONMENT", "production")
    monkeypatch.setenv("SEXTANT_EMBEDDING_PROVIDER", "local")

    with pytest.raises(RuntimeError, match="SEXTANT_EMBEDDING_PROVIDER"):
        embedding_provider_from_env()
