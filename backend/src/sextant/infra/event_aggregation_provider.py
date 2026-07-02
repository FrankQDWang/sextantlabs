from __future__ import annotations

import os

from sextant.common.observability import MetricsRegistry
from sextant.infra.event_aggregation_openai import OpenAIEventAggregationProvider
from sextant.infra.openai_compat import (
    openai_api_style_from_env,
    openai_base_url_from_env,
    openai_extra_body_from_env,
)
from sextant.infra.provider_runtime import reject_local_provider_in_production
from sextant.infra.provider_secrets import openai_api_key_from_env
from sextant.ports.event_aggregation import EventAggregationAdjudicationProvider
from sextant.skills.local_event_aggregation import LocalEventAggregationProvider


def event_aggregation_provider_from_env(
    metrics: MetricsRegistry | None = None,
) -> EventAggregationAdjudicationProvider:
    provider = (
        os.environ.get(
            "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER",
            os.environ.get("SEXTANT_LLM_PROVIDER", "local"),
        )
        .strip()
        .lower()
    )
    reject_local_provider_in_production("SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER", provider)
    if provider in {"local", "local-deterministic"}:
        return LocalEventAggregationProvider()
    if provider == "openai":
        api_key = openai_api_key_from_env("OpenAI event aggregation")
        model = (
            os.environ.get("SEXTANT_EVENT_AGGREGATION_LLM_MODEL")
            or os.environ.get("SEXTANT_LLM_MODEL")
            or ""
        ).strip()
        if not model:
            raise RuntimeError(
                "SEXTANT_EVENT_AGGREGATION_LLM_MODEL or SEXTANT_LLM_MODEL is required "
                "for SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER=openai."
            )
        return OpenAIEventAggregationProvider(
            model=model,
            api_key=api_key,
            base_url=openai_base_url_from_env(),
            api_style=openai_api_style_from_env(),
            extra_body=openai_extra_body_from_env(
                "SEXTANT_EVENT_AGGREGATION_LLM",
                fallback_prefix="SEXTANT_LLM",
            ),
            metrics=metrics,
        )
    raise RuntimeError(f"Unsupported SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER: {provider}")
