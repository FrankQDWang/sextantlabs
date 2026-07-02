from __future__ import annotations

from typing import Protocol

from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult


class StoryDraftProvider(Protocol):
    skill_name: str
    skill_version: str

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult: ...
