from __future__ import annotations

from sextant.contracts.memory_extraction import (
    ExtractedFact,
    ExtractedThreadUpdate,
    MemoryExtractionResult,
)


class LocalMemoryExtractionProvider:
    skill_name = "local_memory_extraction"
    skill_version = "local-v1"
    prompt_version = "deterministic-local-v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        facts: list[ExtractedFact] = []
        thread_updates: list[ExtractedThreadUpdate] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("FACT:"):
                parts = [part.strip() for part in stripped.removeprefix("FACT:").split("|")]
                if len(parts) != 4:
                    continue
                subject, predicate, obj, risk_level = parts
                facts.append(
                    ExtractedFact(
                        subject_ref=_parse_ref(subject),
                        predicate=predicate,
                        object_ref=_parse_ref(obj),
                        risk_level=risk_level,
                    )
                )
            elif stripped.startswith("THREAD:"):
                parts = [part.strip() for part in stripped.removeprefix("THREAD:").split("|")]
                if len(parts) != 5:
                    continue
                target, update_type, thread_id, description, risk_level = parts
                thread_updates.append(
                    ExtractedThreadUpdate(
                        target_ref=_parse_ref(target),
                        update_type=update_type,
                        thread_id=thread_id or None,
                        description=description,
                        risk_level=risk_level,
                    )
                )
        return MemoryExtractionResult(facts=facts, thread_updates=thread_updates)


def _parse_ref(value: str) -> dict[str, str]:
    if ":" not in value:
        return {"type": "literal", "id": value}
    ref_type, ref_id = value.split(":", maxsplit=1)
    return {"type": ref_type, "id": ref_id}
