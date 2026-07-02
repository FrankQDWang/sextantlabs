from __future__ import annotations

import os

from sextant.common.observability import MetricsRegistry
from sextant.infra.openai_compat import (
    openai_api_style_from_env,
    openai_base_url_from_env,
    openai_extra_body_from_env,
)
from sextant.infra.provider_runtime import reject_local_provider_in_production
from sextant.infra.provider_secrets import openai_api_key_from_env
from sextant.infra.story_draft_openai import OpenAIStoryDraftProvider
from sextant.ports.story_draft import StoryDraftProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider


def story_draft_provider_from_env(metrics: MetricsRegistry | None = None) -> StoryDraftProvider:
    provider = os.environ.get("SEXTANT_LLM_PROVIDER", "local").strip().lower()
    reject_local_provider_in_production("SEXTANT_LLM_PROVIDER", provider)
    if provider in {"local", "local-deterministic"}:
        return LocalStoryDraftProvider()
    if provider == "openai":
        api_key = openai_api_key_from_env("OpenAI story draft")
        model = os.environ.get("SEXTANT_LLM_MODEL", "").strip()
        if not model:
            raise RuntimeError("SEXTANT_LLM_MODEL is required for SEXTANT_LLM_PROVIDER=openai.")
        return OpenAIStoryDraftProvider(
            model=model,
            api_key=api_key,
            base_url=openai_base_url_from_env(),
            api_style=openai_api_style_from_env(),
            extra_body=openai_extra_body_from_env("SEXTANT_LLM"),
            metrics=metrics,
        )
    raise RuntimeError(f"Unsupported SEXTANT_LLM_PROVIDER: {provider}")
