from __future__ import annotations

from typing import Protocol

from sextant.contracts.memory_extraction import MemoryExtractionResult


class MemoryExtractionProvider(Protocol):
    skill_name: str
    skill_version: str
    prompt_version: str

    def extract(self, text: str) -> MemoryExtractionResult: ...
