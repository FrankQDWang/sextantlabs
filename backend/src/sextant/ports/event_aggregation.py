from __future__ import annotations

from typing import Protocol

from sextant.contracts.event_aggregation import (
    EventAggregationAdjudicationRequest,
    EventAggregationAdjudicationResult,
)


class EventAggregationAdjudicationProvider(Protocol):
    skill_name: str
    skill_version: str

    def adjudicate(
        self,
        request: EventAggregationAdjudicationRequest,
    ) -> EventAggregationAdjudicationResult: ...
