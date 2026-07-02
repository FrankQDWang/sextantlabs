from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, cast

from sextant.common.observability import MetricsRegistry
from sextant.infra.openai_compat import create_openai_client
from sextant.infra.provider_usage import record_openai_usage_metrics


class OpenAIEmbeddingsClient(Protocol):
    def create(self, **kwargs: object) -> object: ...


class OpenAIClient(Protocol):
    embeddings: OpenAIEmbeddingsClient


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        api_key: str | None = None,
        base_url: str | None = None,
        client: OpenAIClient | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("OpenAI embedding model is required.")
        if dimensions <= 0:
            raise ValueError("OpenAI embedding dimensions must be positive.")
        self.model_name = model
        self.dimensions = dimensions
        self._client = client or cast(
            OpenAIClient,
            create_openai_client(api_key, base_url=base_url),
        )
        self._metrics = metrics

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self.model_name,
            input=list(texts),
            dimensions=self.dimensions,
        )
        record_openai_usage_metrics(
            self._metrics,
            model=self.model_name,
            skill="openai_embedding",
            usage=getattr(response, "usage", None),
        )
        data = getattr(response, "data", None)
        if not isinstance(data, list):
            raise RuntimeError("OpenAI embedding response did not include data.")
        vectors: list[list[float]] = []
        for item in data:
            embedding = getattr(item, "embedding", None)
            if not isinstance(embedding, list):
                raise RuntimeError("OpenAI embedding response item did not include a vector.")
            vectors.append([float(value) for value in embedding])
        return vectors
