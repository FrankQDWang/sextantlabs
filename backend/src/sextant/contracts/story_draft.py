from __future__ import annotations

from dataclasses import dataclass

from sextant.contracts.use_cases import WritingContextPackOutput


@dataclass(frozen=True, slots=True)
class StoryDraftRequest:
    actor_intent: str
    current_text_window: str
    context_pack: WritingContextPackOutput
    prose_rendering_contract: dict[str, object]


@dataclass(frozen=True, slots=True)
class StoryDraftResult:
    text: str
    finish_reason: str
    structured_output: dict[str, object]
    review_cues: list[dict[str, object]]
