from __future__ import annotations

from uuid import uuid4

import pytest
from sextant.contracts.event_aggregation import EventAggregationAdjudicationRequest
from sextant.contracts.memory_extraction import ExtractedFact, MemoryExtractionResult
from sextant.contracts.pov_detection import PovDetectionMention, PovDetectionRequest
from sextant.contracts.story_draft import StoryDraftRequest
from sextant.contracts.use_cases import WritingContextPackOutput
from sextant.infra.story_skill_registry import (
    StorySkillRuntimeContext,
    StorySkillValidationError,
    default_story_skill_registry,
    resolve_story_skill_plan,
    run_skill,
)
from sextant.skills.local_pov_detection import LocalPovDetectionProvider
from sextant.skills.local_story_draft import LocalStoryDraftProvider


class InvalidMemoryExtractionProvider:
    skill_name = "invalid_memory_extraction"
    skill_version = "invalid-memory-extraction.v1"
    prompt_version = "invalid-memory-extraction.v1"

    def extract(self, text: str) -> MemoryExtractionResult:
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref={"type": "character", "id": "mira"},
                    predicate="owns",
                    object_ref={"type": "object", "id": "ledger"},
                    risk_level="critical",
                )
            ]
        )


def test_story_skill_registry_covers_initial_target_set() -> None:
    registry = default_story_skill_registry()

    assert {
        "source-normalization",
        "split-structure",
        "detect-pov",
        "extract-mentions",
        "resolve-alias",
        "extract-events",
        "aggregate-events",
        "derive-facts",
        "check-continuity",
        "rewrite-current-canon",
        "build-writing-context-pack",
        "answer-with-evidence",
        "character-agency-pass",
        "storytelling-control",
        "next-page-agent",
        "agent-review",
    }.issubset({definition.name for definition in registry.definitions()})


def test_run_skill_detect_pov_returns_validated_structured_output() -> None:
    request = PovDetectionRequest(
        source_span_id=uuid4(),
        scene_id=uuid4(),
        text="Mira studies the lantern map.",
        mentions=[
            PovDetectionMention(
                raw_text="Mira",
                mention_type="character",
                canonical_entity_id="00000000-0000-4000-8000-000000000001",
            )
        ],
    )

    result = run_skill(
        "detect-pov",
        "story-skill.v1",
        request,
        StorySkillRuntimeContext(
            project_id=uuid4(),
            request_id="req-detect-pov",
            pov_detection_provider=LocalPovDetectionProvider(),
        ),
    )

    assert result.skill_name == "detect-pov"
    assert result.provider_skill_name == "local_pov_detection"
    assert result.validation_result == {"status": "valid"}
    assert result.structured_output == {
        "pov_character_name": None,
        "pov_mode": "unknown",
        "confidence": 0.0,
        "evidence_span_ids": [str(request.source_span_id)],
        "uncertainty_reason": "local_provider_no_model_judgment",
    }


def test_run_skill_next_page_agent_validates_contract_metadata() -> None:
    result = run_skill(
        "next-page-agent",
        "story-skill.v1",
        StoryDraftRequest(
            actor_intent="Continue with Mira protecting the lantern map.",
            current_text_window="Mira keeps the lantern map hidden.",
            context_pack=WritingContextPackOutput(
                context_pack_id=uuid4(),
                schema_version="writing-context-pack.v1",
                current_position={},
                canonical_context={},
                pov_constraint={},
                active_characters=[],
                character_agency_state={},
                recent_events=[],
                character_knowledge=[],
                object_location_state=[],
                open_threads=[],
                risk_context={},
                style_memory={"samples": []},
                evidence_refs=[],
            ),
            prose_rendering_contract={
                "contract_id": "contract-1",
                "mode": "draft_next_passage",
            },
        ),
        StorySkillRuntimeContext(
            project_id=uuid4(),
            request_id="req-next-page-agent",
            story_draft_provider=LocalStoryDraftProvider(),
        ),
    )

    assert result.skill_name == "next-page-agent"
    assert result.provider_skill_name == "local_story_draft"
    assert result.validation_result == {"status": "valid"}
    assert result.structured_output["prose_contract_id"] == "contract-1"
    assert result.structured_output["mode"] == "draft_next_passage"


def test_run_skill_derive_facts_rejects_invalid_provider_output() -> None:
    with pytest.raises(StorySkillValidationError) as exc_info:
        run_skill(
            "derive-facts",
            "story-skill.v1",
            "Mira takes the ledger.",
            StorySkillRuntimeContext(
                project_id=uuid4(),
                request_id="req-derive-facts",
                memory_extraction_provider=InvalidMemoryExtractionProvider(),
            ),
        )

    assert exc_info.value.skill_name == "derive-facts"
    assert exc_info.value.validation_result["status"] == "invalid"
    assert exc_info.value.validation_result["error_code"] == "llm_output_invalid"


def test_resolve_story_skill_plan_returns_ordered_writing_flow() -> None:
    plan = resolve_story_skill_plan(action_type="continue_small_passage")

    assert plan == [
        "build-writing-context-pack",
        "character-agency-pass",
        "storytelling-control",
        "next-page-agent",
        "agent-review",
    ]


def test_resolve_story_skill_plan_returns_event_aggregation_skill_for_job_step() -> None:
    plan = resolve_story_skill_plan(job_type="aggregate_events")

    assert plan == ["aggregate-events"]


def test_run_skill_aggregate_events_uses_structured_validation() -> None:
    class LocalEventProvider:
        skill_name = "local_event_aggregation"
        skill_version = "deterministic-local-event-aggregation-v1"

        def adjudicate(
            self,
            request: EventAggregationAdjudicationRequest,
        ):
            from sextant.contracts.event_aggregation import EventAggregationAdjudicationResult

            return EventAggregationAdjudicationResult(
                decision="uncertain",
                confidence=0.0,
                rationale="local_provider_no_model_judgment",
                evidence_span_ids=[
                    *request.existing_event_evidence_span_ids,
                    *request.candidate_evidence_span_ids,
                ],
            )

    request = EventAggregationAdjudicationRequest(
        existing_event_id=uuid4(),
        existing_event_type="reveal",
        existing_event_title="Lantern map moves",
        existing_event_summary="Existing summary",
        existing_event_participants=[],
        existing_event_objects=[],
        existing_event_evidence_span_ids=["span-existing"],
        existing_event_source_text="Existing event text",
        candidate_id=uuid4(),
        candidate_event_type="reveal",
        candidate_summary="Candidate summary",
        candidate_participants=[],
        candidate_objects=[],
        candidate_evidence_span_ids=["span-candidate"],
        candidate_source_text="Candidate event text",
    )

    result = run_skill(
        "aggregate-events",
        "story-skill.v1",
        request,
        StorySkillRuntimeContext(
            project_id=uuid4(),
            request_id="req-aggregate-events",
            event_aggregation_provider=LocalEventProvider(),
        ),
    )

    assert result.validation_result == {"status": "valid"}
    assert result.structured_output["decision"] == "uncertain"
