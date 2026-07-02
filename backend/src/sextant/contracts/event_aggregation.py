from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

EventAggregationDecision = Literal[
    "same_event",
    "related_but_distinct",
    "conflict_version",
    "uncertain",
]


@dataclass(frozen=True, slots=True)
class EventAggregationAdjudicationRequest:
    existing_event_id: UUID
    existing_event_type: str
    existing_event_title: str
    existing_event_summary: str
    existing_event_participants: list[dict[str, object]]
    existing_event_objects: list[dict[str, object]]
    existing_event_evidence_span_ids: list[str]
    existing_event_source_text: str
    candidate_id: UUID
    candidate_event_type: str
    candidate_summary: str
    candidate_participants: list[dict[str, object]]
    candidate_objects: list[dict[str, object]]
    candidate_evidence_span_ids: list[str]
    candidate_source_text: str


@dataclass(frozen=True, slots=True)
class EventAggregationAdjudicationResult:
    decision: EventAggregationDecision
    confidence: float
    rationale: str
    evidence_span_ids: list[str]
