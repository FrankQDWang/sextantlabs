from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from sextant.common.observability import MetricsRegistry
from sextant.contracts.event_aggregation import (
    EventAggregationAdjudicationRequest,
    EventAggregationAdjudicationResult,
)
from sextant.infra.openai_compat import (
    OpenAIApiStyle,
    create_openai_client,
    parse_openai_structured,
)
from sextant.infra.prompt_registry import PromptDefinition, load_prompt
from sextant.infra.provider_usage import record_openai_usage_metrics


class OpenAIEventAggregationOutput(BaseModel):
    decision: Literal["same_event", "related_but_distinct", "conflict_version", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence_span_ids: list[str]


class OpenAIEventAggregationProvider:
    skill_name = "openai_event_aggregation"
    prompt_version = "openai-event-aggregation.v1"

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
            raise ValueError("OpenAI event aggregation model is required.")
        self._model = model
        self._api_style = api_style
        self._extra_body = dict(extra_body or {})
        self.skill_version = f"openai-event-aggregation.{model}"
        self._prompt = load_prompt(self.skill_name, self.prompt_version)
        self._client = client or create_openai_client(api_key, base_url=base_url)
        self._metrics = metrics

    def adjudicate(
        self,
        request: EventAggregationAdjudicationRequest,
    ) -> EventAggregationAdjudicationResult:
        response, parsed = parse_openai_structured(
            self._client,
            api_style=self._api_style,
            model=self._model,
            messages=_messages(request, self._prompt),
            text_format=OpenAIEventAggregationOutput,
            extra_body=self._extra_body,
        )
        record_openai_usage_metrics(
            self._metrics,
            model=self._model,
            skill=self.skill_name,
            usage=getattr(response, "usage", None),
        )
        if not isinstance(parsed, OpenAIEventAggregationOutput):
            raise RuntimeError(
                "OpenAI event aggregation response did not match the expected schema."
            )
        return EventAggregationAdjudicationResult(
            decision=parsed.decision,
            confidence=parsed.confidence,
            rationale=parsed.rationale,
            evidence_span_ids=parsed.evidence_span_ids,
        )


def _messages(
    request: EventAggregationAdjudicationRequest,
    prompt: PromptDefinition,
) -> list[dict[str, str]]:
    payload: dict[str, Any] = {
        "existing_event_id": str(request.existing_event_id),
        "existing_event_type": request.existing_event_type,
        "existing_event_title": request.existing_event_title,
        "existing_event_summary": request.existing_event_summary,
        "existing_event_participants": request.existing_event_participants,
        "existing_event_objects": request.existing_event_objects,
        "existing_event_evidence_span_ids": request.existing_event_evidence_span_ids,
        "existing_event_source_text": request.existing_event_source_text,
        "candidate_id": str(request.candidate_id),
        "candidate_event_type": request.candidate_event_type,
        "candidate_summary": request.candidate_summary,
        "candidate_participants": request.candidate_participants,
        "candidate_objects": request.candidate_objects,
        "candidate_evidence_span_ids": request.candidate_evidence_span_ids,
        "candidate_source_text": request.candidate_source_text,
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
