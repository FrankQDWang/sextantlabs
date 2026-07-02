from __future__ import annotations

from typing import Protocol

from sextant.contracts.pov_detection import PovDetectionRequest, PovDetectionResult


class PovDetectionProvider(Protocol):
    skill_name: str
    skill_version: str

    def detect(self, request: PovDetectionRequest) -> PovDetectionResult: ...
