from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from sextant.common.observability import MetricsRegistry
from sextant.contracts.pov_detection import (
    PovDetectionMention,
    PovDetectionRequest,
    PovDetectionResult,
)
from sextant.infra.openai_compat import (
    OpenAIApiStyle,
    create_openai_client,
    parse_openai_structured,
)
from sextant.infra.prompt_registry import PromptDefinition, load_prompt
from sextant.infra.provider_usage import record_openai_usage_metrics


class OpenAIPovDetectionOutput(BaseModel):
    pov_character_name: str | None
    pov_mode: Literal["first_person", "third_limited", "omniscient", "multiple", "unknown"]
    confidence: float = Field(ge=0, le=1)
    evidence_span_ids: list[str]
    uncertainty_reason: str | None = None


class OpenAIPovDetectionProvider:
    skill_name = "openai_pov_detection"
    prompt_version = "openai-pov-detection.v1"

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
            raise ValueError("OpenAI POV detection model is required.")
        self._model = model
        self._api_style = api_style
        self._extra_body = dict(extra_body or {})
        self.skill_version = f"openai-pov-detection.{model}"
        self._prompt = load_prompt(self.skill_name, self.prompt_version)
        self._client = client or create_openai_client(api_key, base_url=base_url)
        self._metrics = metrics

    def detect(self, request: PovDetectionRequest) -> PovDetectionResult:
        response, parsed = parse_openai_structured(
            self._client,
            api_style=self._api_style,
            model=self._model,
            messages=_messages(request, self._prompt),
            text_format=OpenAIPovDetectionOutput,
            extra_body=self._extra_body,
        )
        record_openai_usage_metrics(
            self._metrics,
            model=self._model,
            skill=self.skill_name,
            usage=getattr(response, "usage", None),
        )
        if not isinstance(parsed, OpenAIPovDetectionOutput):
            raise RuntimeError("OpenAI POV detection response did not match the expected schema.")
        return PovDetectionResult(
            pov_character_name=parsed.pov_character_name,
            pov_mode=parsed.pov_mode,
            confidence=parsed.confidence,
            evidence_span_ids=parsed.evidence_span_ids,
            uncertainty_reason=parsed.uncertainty_reason,
        )


def _messages(request: PovDetectionRequest, prompt: PromptDefinition) -> list[dict[str, str]]:
    payload: dict[str, Any] = {
        "source_span_id": str(request.source_span_id),
        "scene_id": str(request.scene_id),
        "text": request.text,
        "mentions": [_mention_payload(mention) for mention in request.mentions],
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


def _mention_payload(mention: PovDetectionMention) -> dict[str, object]:
    return {
        "raw_text": mention.raw_text,
        "mention_type": mention.mention_type,
        "canonical_entity_id": mention.canonical_entity_id,
    }
