from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    subject_ref: dict[str, str]
    predicate: str
    object_ref: dict[str, str]
    risk_level: str


@dataclass(frozen=True, slots=True)
class ExtractedThreadUpdate:
    target_ref: dict[str, str]
    update_type: str
    thread_id: str | None
    description: str
    risk_level: str


@dataclass(frozen=True, slots=True)
class MemoryExtractionResult:
    facts: list[ExtractedFact]
    thread_updates: list[ExtractedThreadUpdate] = field(default_factory=list)
