from __future__ import annotations

import os

from sextant.common.observability import MetricsRegistry
from sextant.infra.embedding_openai import OpenAIEmbeddingProvider
from sextant.infra.openai_compat import openai_base_url_from_env
from sextant.infra.provider_runtime import reject_local_provider_in_production
from sextant.infra.provider_secrets import openai_api_key_from_env
from sextant.ports.embedding import EmbeddingClient
from sextant.skills.local_embedding import LocalEmbeddingProvider


def embedding_provider_from_env(metrics: MetricsRegistry | None = None) -> EmbeddingClient:
    provider = os.environ.get("SEXTANT_EMBEDDING_PROVIDER", "local").strip().lower()
    reject_local_provider_in_production("SEXTANT_EMBEDDING_PROVIDER", provider)
    if provider in {"local", "local-deterministic"}:
        return LocalEmbeddingProvider()
    if provider == "openai":
        api_key = openai_api_key_from_env("OpenAI embedding")
        model = os.environ.get("SEXTANT_EMBEDDING_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "SEXTANT_EMBEDDING_MODEL is required for SEXTANT_EMBEDDING_PROVIDER=openai."
            )
        dimensions = _embedding_dimensions_from_env()
        return OpenAIEmbeddingProvider(
            model=model,
            dimensions=dimensions,
            api_key=api_key,
            base_url=openai_base_url_from_env(),
            metrics=metrics,
        )
    raise RuntimeError(f"Unsupported SEXTANT_EMBEDDING_PROVIDER: {provider}")


def _embedding_dimensions_from_env() -> int:
    value = os.environ.get("SEXTANT_EMBEDDING_DIMENSIONS", "1536").strip()
    try:
        dimensions = int(value)
    except ValueError as exc:
        raise RuntimeError("SEXTANT_EMBEDDING_DIMENSIONS must be a positive integer.") from exc
    if dimensions <= 0:
        raise RuntimeError("SEXTANT_EMBEDDING_DIMENSIONS must be a positive integer.")
    return dimensions
