from __future__ import annotations

from sextant.infra.openai_compat import (
    openai_base_url_from_env,
    openai_extra_body_from_env,
)


def test_openai_base_url_from_env_reads_dashscope_compatible_endpoint(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "SEXTANT_OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert openai_base_url_from_env() == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_openai_extra_body_from_env_reads_scoped_reasoning_and_thinking(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SEXTANT_LLM_REASONING_EFFORT", "high")
    monkeypatch.setenv("SEXTANT_LLM_ENABLE_THINKING", "false")
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_REASONING_EFFORT", "max")
    monkeypatch.setenv("SEXTANT_MEMORY_LLM_ENABLE_THINKING", "true")

    assert openai_extra_body_from_env("SEXTANT_LLM") == {
        "reasoning_effort": "high",
        "enable_thinking": False,
    }
    assert openai_extra_body_from_env("SEXTANT_MEMORY_LLM") == {
        "reasoning_effort": "max",
        "enable_thinking": True,
    }
