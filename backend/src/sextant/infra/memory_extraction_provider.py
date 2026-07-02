from __future__ import annotations

import os

from sextant.common.observability import MetricsRegistry
from sextant.infra.memory_extraction_openai import OpenAIMemoryExtractionProvider
from sextant.infra.openai_compat import (
    openai_api_style_from_env,
    openai_base_url_from_env,
    openai_extra_body_from_env,
)
from sextant.infra.provider_runtime import reject_local_provider_in_production
from sextant.infra.provider_secrets import openai_api_key_from_env
from sextant.ports.memory_extraction import MemoryExtractionProvider
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider


def memory_extraction_provider_from_env(
    metrics: MetricsRegistry | None = None,
) -> MemoryExtractionProvider:
    provider = (
        os.environ.get(
            "SEXTANT_MEMORY_LLM_PROVIDER",
            os.environ.get("SEXTANT_LLM_PROVIDER", "local"),
        )
        .strip()
        .lower()
    )
    reject_local_provider_in_production("SEXTANT_MEMORY_LLM_PROVIDER", provider)
    if provider in {"local", "local-deterministic"}:
        return LocalMemoryExtractionProvider()
    if provider == "openai":
        api_key = openai_api_key_from_env("OpenAI memory extraction")
        model = (
            os.environ.get("SEXTANT_MEMORY_LLM_MODEL") or os.environ.get("SEXTANT_LLM_MODEL") or ""
        ).strip()
        if not model:
            raise RuntimeError(
                "SEXTANT_MEMORY_LLM_MODEL or SEXTANT_LLM_MODEL is required for "
                "SEXTANT_MEMORY_LLM_PROVIDER=openai."
            )
        return OpenAIMemoryExtractionProvider(
            model=model,
            api_key=api_key,
            base_url=openai_base_url_from_env(),
            api_style=openai_api_style_from_env(),
            extra_body=openai_extra_body_from_env(
                "SEXTANT_MEMORY_LLM",
                fallback_prefix="SEXTANT_LLM",
            ),
            metrics=metrics,
        )
    raise RuntimeError(f"Unsupported SEXTANT_MEMORY_LLM_PROVIDER: {provider}")
