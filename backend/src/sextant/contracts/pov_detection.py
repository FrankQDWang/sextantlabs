from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PovDetectionMention:
    raw_text: str
    mention_type: str
    canonical_entity_id: str | None


@dataclass(frozen=True, slots=True)
class PovDetectionRequest:
    source_span_id: UUID
    scene_id: UUID
    text: str
    mentions: list[PovDetectionMention]


@dataclass(frozen=True, slots=True)
class PovDetectionResult:
    pov_character_name: str | None
    pov_mode: str
    confidence: float
    evidence_span_ids: list[str]
    uncertainty_reason: str | None
