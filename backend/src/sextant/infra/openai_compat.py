from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Literal, cast

OpenAIApiStyle = Literal["responses", "chat"]


def openai_base_url_from_env() -> str | None:
    value = os.environ.get("SEXTANT_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def openai_api_style_from_env() -> OpenAIApiStyle:
    value = os.environ.get("SEXTANT_OPENAI_API_STYLE", "responses").strip().lower()
    if value not in {"responses", "chat"}:
        raise RuntimeError("SEXTANT_OPENAI_API_STYLE must be either 'responses' or 'chat'.")
    return cast(OpenAIApiStyle, value)


def openai_extra_body_from_env(
    prefix: str,
    *,
    fallback_prefix: str | None = None,
) -> dict[str, object]:
    extra_body: dict[str, object] = {}
    reasoning_effort = _scoped_env(prefix, "REASONING_EFFORT", fallback_prefix=fallback_prefix)
    if reasoning_effort:
        extra_body["reasoning_effort"] = reasoning_effort
    enable_thinking = _scoped_env(prefix, "ENABLE_THINKING", fallback_prefix=fallback_prefix)
    if enable_thinking:
        extra_body["enable_thinking"] = _env_bool(enable_thinking, f"{prefix}_ENABLE_THINKING")
    return extra_body


def create_openai_client(api_key: str | None, *, base_url: str | None = None) -> object:
    from openai import OpenAI

    resolved_base_url = base_url or openai_base_url_from_env()
    if api_key and resolved_base_url:
        return OpenAI(api_key=api_key, base_url=resolved_base_url)
    if api_key:
        return OpenAI(api_key=api_key)
    if resolved_base_url:
        return OpenAI(base_url=resolved_base_url)
    return OpenAI()


def parse_openai_structured(
    client: object,
    *,
    api_style: OpenAIApiStyle,
    model: str,
    messages: list[dict[str, str]],
    text_format: type[object],
    extra_body: Mapping[str, object] | None = None,
) -> tuple[object, object | None]:
    if api_style == "chat":
        typed_client = cast(Any, client)
        kwargs: dict[str, object] = {
            "model": model,
            "messages": messages,
            "response_format": text_format,
        }
        if extra_body:
            kwargs["extra_body"] = dict(extra_body)
        response = typed_client.chat.completions.parse(**kwargs)
        choices = getattr(response, "choices", None)
        if not choices:
            return response, None
        message = getattr(choices[0], "message", None)
        return response, getattr(message, "parsed", None)

    typed_client = cast(Any, client)
    kwargs: dict[str, object] = {
        "model": model,
        "input": messages,
        "text_format": text_format,
    }
    if extra_body:
        kwargs["extra_body"] = dict(extra_body)
    response = typed_client.responses.parse(**kwargs)
    return response, getattr(response, "output_parsed", None)


def _scoped_env(prefix: str, suffix: str, *, fallback_prefix: str | None) -> str:
    value = os.environ.get(f"{prefix}_{suffix}", "").strip()
    if value:
        return value
    if fallback_prefix:
        return os.environ.get(f"{fallback_prefix}_{suffix}", "").strip()
    return ""


def _env_bool(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean: true or false.")
