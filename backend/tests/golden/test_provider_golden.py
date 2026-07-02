from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sextant.contracts.event_aggregation import EventAggregationAdjudicationRequest
from sextant.contracts.pov_detection import PovDetectionMention, PovDetectionRequest
from sextant.contracts.story_draft import StoryDraftRequest
from sextant.contracts.use_cases import WritingContextPackOutput
from sextant.skills.local_event_aggregation import LocalEventAggregationProvider
from sextant.skills.local_memory_extractor import LocalMemoryExtractionProvider
from sextant.skills.local_pov_detection import LocalPovDetectionProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_local_memory_extraction_golden_output() -> None:
    provider = LocalMemoryExtractionProvider()

    result = provider.extract(
        "\n".join(
            [
                "FACT: character:mira | owns | object:lantern-map | low",
                (
                    "THREAD: character:mira | opens | map-origin | "
                    "The lantern map origin remains unresolved. | low"
                ),
            ]
        )
    )

    assert result.facts[0].subject_ref == {"type": "character", "id": "mira"}
    assert result.facts[0].predicate == "owns"
    assert result.facts[0].object_ref == {"type": "object", "id": "lantern-map"}
    assert result.facts[0].risk_level == "low"
    assert result.thread_updates[0].target_ref == {"type": "character", "id": "mira"}
    assert result.thread_updates[0].update_type == "opens"
    assert result.thread_updates[0].thread_id == "map-origin"
    assert result.thread_updates[0].description == "The lantern map origin remains unresolved."
    assert result.thread_updates[0].risk_level == "low"


def test_local_memory_extraction_does_not_infer_seed_story_fact_from_prose() -> None:
    provider = LocalMemoryExtractionProvider()

    result = provider.extract("米拉停在西档案室门口，指尖压着灯图的折痕。")

    assert result.facts == []
    assert result.thread_updates == []


def test_local_memory_extraction_does_not_infer_observable_ownership_from_prose() -> None:
    provider = LocalMemoryExtractionProvider()

    result = provider.extract("Nova 继续握着继续握着旧剑，停在门口。")

    assert result.facts == []
    assert result.thread_updates == []


def test_local_story_draft_golden_output_blocks_forced_risk() -> None:
    provider = LocalStoryDraftProvider()
    context_pack = WritingContextPackOutput(
        context_pack_id=uuid4(),
        schema_version="writing-context-pack.v1",
        current_position={"mode": "rewrite_span"},
        canonical_context={"facts": []},
        pov_constraint={"forbidden_knowledge": []},
        active_characters=[],
        character_agency_state={"status": "not_computed"},
        recent_events=[],
        character_knowledge=[],
        object_location_state=[],
        open_threads=[],
        risk_context={"facts": [{"fact_status": "disputed"}]},
        style_memory={"samples": []},
        evidence_refs=[],
    )

    result = provider.draft(
        StoryDraftRequest(
            actor_intent="改写得更克制",
            current_text_window="米拉停在门口。",
            context_pack=context_pack,
            prose_rendering_contract={
                "mode": "rewrite_span",
                "contract_id": str(uuid4()),
                "new_character_policy": "avoid",
                "force_risk_fact_in_draft": True,
            },
        )
    )

    assert result.text.startswith("为了继续推进眼前这一拍")
    assert "继续握着继续握着" not in result.text
    assert "为了继续校准灯图" not in result.text
    assert "米拉停在西档案室门口，指尖压着灯图的折痕" not in result.text
    assert "奥林" not in result.text
    assert "挡住去路" in result.text
    assert result.review_cues == [
        {
            "risk_level": "high",
            "risk_type": "canon_risk",
            "summary": "Draft presents risk-context material as if it were canon.",
            "can_offer_to_author": False,
            "maps_to_review_type_if_accepted": "canon_conflict",
        }
    ]


def test_local_pov_detection_golden_ambiguous_scene_output() -> None:
    input_payload = cast(
        dict[str, object],
        _read_json("evals/datasets/local_pov_detection/ambiguous_scene.input.json"),
    )
    expected = cast(
        dict[str, object],
        _read_json("evals/expected/local_pov_detection/ambiguous_scene.expected.json"),
    )
    provider = LocalPovDetectionProvider()
    mentions = [
        PovDetectionMention(
            raw_text=str(mention["raw_text"]),
            mention_type=str(mention["mention_type"]),
            canonical_entity_id=cast(str | None, mention.get("canonical_entity_id")),
        )
        for mention in cast(list[dict[str, object]], input_payload["mentions"])
    ]

    result = provider.detect(
        PovDetectionRequest(
            source_span_id=UUID(str(input_payload["source_span_id"])),
            scene_id=UUID(str(input_payload["scene_id"])),
            text=str(input_payload["text"]),
            mentions=mentions,
        )
    )

    assert {
        "pov_character_name": result.pov_character_name,
        "pov_mode": result.pov_mode,
        "confidence": result.confidence,
        "evidence_span_ids": result.evidence_span_ids,
        "uncertainty_reason": result.uncertainty_reason,
    } == {
        key: expected[key]
        for key in (
            "pov_character_name",
            "pov_mode",
            "confidence",
            "evidence_span_ids",
            "uncertainty_reason",
        )
    }
    assert expected["evidence_refs"] == input_payload["expected_evidence_refs"]
    assert expected["non_promotion"] == input_payload["expected_non_promotion"]


def test_local_event_aggregation_golden_uncertain_output() -> None:
    existing_span_id = uuid4()
    candidate_span_id = uuid4()
    provider = LocalEventAggregationProvider()

    result = provider.adjudicate(
        EventAggregationAdjudicationRequest(
            existing_event_id=uuid4(),
            existing_event_type="object_transfer",
            existing_event_title="Mira handed Kestrel the Lantern Map",
            existing_event_summary="Mira handed Kestrel the Lantern Map.",
            existing_event_participants=[
                {"type": "character", "id": "mira", "label": "Mira"},
                {"type": "character", "id": "kestrel", "label": "Kestrel"},
            ],
            existing_event_objects=[
                {"type": "object", "id": "lantern-map", "label": "Lantern Map"}
            ],
            existing_event_evidence_span_ids=[str(existing_span_id)],
            existing_event_source_text="Mira handed Kestrel the Lantern Map.",
            candidate_id=uuid4(),
            candidate_event_type="object_transfer",
            candidate_summary="Kestrel received the Lantern Map from Mira.",
            candidate_participants=[
                {"type": "character", "id": "kestrel", "label": "Kestrel"},
                {"type": "character", "id": "mira", "label": "Mira"},
            ],
            candidate_objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
            candidate_evidence_span_ids=[str(candidate_span_id)],
            candidate_source_text="Kestrel received the Lantern Map from Mira.",
        )
    )

    assert result.decision == "uncertain"
    assert result.confidence == 0.0
    assert result.rationale == "local_provider_no_model_judgment"
    assert result.evidence_span_ids == [str(existing_span_id), str(candidate_span_id)]


def _read_json(path: str) -> object:
    return json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
