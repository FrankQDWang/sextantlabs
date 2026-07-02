from __future__ import annotations

import os
from collections.abc import Mapping
from typing import cast

from sextant.common.observability import MetricsRegistry


def record_openai_usage_metrics(
    metrics: MetricsRegistry | None,
    *,
    model: str,
    skill: str,
    usage: object,
) -> None:
    if metrics is None or usage is None:
        return
    labels = {
        "provider": "openai",
        "model": model,
        "skill": skill,
    }
    input_tokens = _token_count(usage, ("input_tokens", "prompt_tokens"))
    output_tokens = _token_count(usage, ("output_tokens", "completion_tokens"))
    total_tokens = _token_count(usage, ("total_tokens",))
    if input_tokens is not None:
        metrics.increment(
            "sextant_provider_tokens_total",
            labels={**labels, "token_type": "input"},
            amount=input_tokens,
        )
    if output_tokens is not None:
        metrics.increment(
            "sextant_provider_tokens_total",
            labels={**labels, "token_type": "output"},
            amount=output_tokens,
        )
    if total_tokens is not None:
        metrics.increment(
            "sextant_provider_tokens_total",
            labels={**labels, "token_type": "total"},
            amount=total_tokens,
        )
    cost_microusd = _cost_microusd(input_tokens=input_tokens, output_tokens=output_tokens)
    if cost_microusd is not None:
        metrics.increment(
            "sextant_provider_cost_microusd_total",
            labels=labels,
            amount=cost_microusd,
        )


def _token_count(usage: object, names: tuple[str, ...]) -> float | None:
    for name in names:
        value = _usage_value(usage, name)
        if value is None:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            if value < 0:
                continue
            return float(value)
    return None


def _usage_value(usage: object, name: str) -> object:
    if isinstance(usage, Mapping):
        return cast(Mapping[str, object], usage).get(name)
    return getattr(usage, name, None)


def _cost_microusd(
    *,
    input_tokens: float | None,
    output_tokens: float | None,
) -> float | None:
    input_rate = _rate("SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS")
    output_rate = _rate("SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS")
    cost = 0.0
    observed = False
    if input_tokens is not None and input_rate is not None:
        cost += input_tokens * input_rate / 1000
        observed = True
    if output_tokens is not None and output_rate is not None:
        cost += output_tokens * output_rate / 1000
        observed = True
    if not observed:
        return None
    return cost


def _rate(name: str) -> float | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        rate = float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a numeric micro-USD rate per 1K tokens.") from exc
    if rate < 0:
        raise RuntimeError(f"{name} must be zero or greater.")
    return rate
