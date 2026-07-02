from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from sextant.common.observability import MetricsRegistry
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.infra.openai_compat import (
    OpenAIApiStyle,
    create_openai_client,
    parse_openai_structured,
)
from sextant.infra.prompt_registry import PromptDefinition, load_prompt
from sextant.infra.provider_usage import record_openai_usage_metrics


class OpenAIReviewCue(BaseModel):
    risk_level: Literal["low", "medium", "high"]
    risk_type: str
    summary: str
    can_offer_to_author: bool
    maps_to_review_type_if_accepted: str | None = None


class OpenAIStoryDraftOutput(BaseModel):
    text: str
    finish_reason: str = Field(description="complete, length, blocked, or error")
    mode: str
    prose_contract_id: str
    review_cues: list[OpenAIReviewCue]


class OpenAIStoryDraftProvider:
    skill_name = "openai_story_draft"
    prompt_version = "openai-story-draft.v1"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        api_style: OpenAIApiStyle = "responses",
        extra_body: Mapping[str, object] | None = None,
        client: object | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("OpenAI story draft model is required.")
        self._model = model
        self._api_style = api_style
        self._extra_body = dict(extra_body or {})
        self.skill_version = f"openai-story-draft.{model}"
        self._prompt = load_prompt(self.skill_name, self.prompt_version)
        self._client = client or create_openai_client(api_key, base_url=base_url)
        self._metrics = metrics

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        response, parsed = parse_openai_structured(
            self._client,
            api_style=self._api_style,
            model=self._model,
            messages=_messages(request, self._prompt),
            text_format=OpenAIStoryDraftOutput,
            extra_body=self._extra_body,
        )
        record_openai_usage_metrics(
            self._metrics,
            model=self._model,
            skill=self.skill_name,
            usage=getattr(response, "usage", None),
        )
        if not isinstance(parsed, OpenAIStoryDraftOutput):
            raise RuntimeError("OpenAI story draft response did not match the expected schema.")
        structured_output = parsed.model_dump()
        return StoryDraftResult(
            text=parsed.text,
            finish_reason=parsed.finish_reason,
            structured_output=structured_output,
            review_cues=[cue.model_dump(exclude_none=True) for cue in parsed.review_cues],
        )


def _messages(request: StoryDraftRequest, prompt: PromptDefinition) -> list[dict[str, str]]:
    payload: dict[str, Any] = {
        "actor_intent": request.actor_intent,
        "current_text_window": request.current_text_window,
        "context_pack": {
            "schema_version": request.context_pack.schema_version,
            "current_position": request.context_pack.current_position,
            "canonical_context": request.context_pack.canonical_context,
            "pov_constraint": request.context_pack.pov_constraint,
            "risk_context": request.context_pack.risk_context,
            "open_threads": request.context_pack.open_threads,
            "evidence_refs": request.context_pack.evidence_refs,
        },
        "prose_rendering_contract": request.prose_rendering_contract,
    }
    return [
        {
            "role": "system",
            "content": prompt.body,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]
