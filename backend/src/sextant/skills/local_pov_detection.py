from __future__ import annotations

from sextant.contracts.pov_detection import PovDetectionRequest, PovDetectionResult


class LocalPovDetectionProvider:
    skill_name = "local_pov_detection"
    skill_version = "deterministic-local-pov-v1"

    def detect(self, request: PovDetectionRequest) -> PovDetectionResult:
        return PovDetectionResult(
            pov_character_name=None,
            pov_mode="unknown",
            confidence=0.0,
            evidence_span_ids=[str(request.source_span_id)],
            uncertainty_reason="local_provider_no_model_judgment",
        )
