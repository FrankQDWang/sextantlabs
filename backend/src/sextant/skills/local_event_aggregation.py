from __future__ import annotations

from sextant.contracts.event_aggregation import (
    EventAggregationAdjudicationRequest,
    EventAggregationAdjudicationResult,
)


class LocalEventAggregationProvider:
    skill_name = "local_event_aggregation"
    skill_version = "deterministic-local-event-aggregation-v1"

    def adjudicate(
        self,
        request: EventAggregationAdjudicationRequest,
    ) -> EventAggregationAdjudicationResult:
        return EventAggregationAdjudicationResult(
            decision="uncertain",
            confidence=0.0,
            rationale="local_provider_no_model_judgment",
            evidence_span_ids=[
                *request.existing_event_evidence_span_ids,
                *request.candidate_evidence_span_ids,
            ],
        )
