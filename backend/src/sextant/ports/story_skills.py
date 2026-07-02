from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import cast
from uuid import UUID

from sextant.contracts.event_aggregation import (
    EventAggregationAdjudicationRequest,
    EventAggregationAdjudicationResult,
)
from sextant.contracts.memory_extraction import MemoryExtractionResult
from sextant.contracts.pov_detection import PovDetectionRequest, PovDetectionResult
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.ports.event_aggregation import EventAggregationAdjudicationProvider
from sextant.ports.memory_extraction import MemoryExtractionProvider
from sextant.ports.pov_detection import PovDetectionProvider
from sextant.ports.story_draft import StoryDraftProvider

STORY_SKILL_VERSION = "story-skill.v1"
VALID_POV_MODES = frozenset(("first_person", "third_limited", "omniscient", "multiple", "unknown"))
VALID_EVENT_DECISIONS = frozenset(
    ("same_event", "related_but_distinct", "conflict_version", "uncertain")
)
VALID_MEMORY_RISK_LEVELS = frozenset(("low", "medium", "high"))
VALID_THREAD_UPDATE_TYPES = frozenset(("opens", "keeps_open", "narrows", "pays_off", "closes"))
VALID_AGENT_RISK_LEVELS = frozenset(("low", "medium", "high"))
VALID_AGENT_REVIEW_TYPES = frozenset(
    (
        "canon_conflict",
        "continuity_risk",
        "pov_violation",
        "style_drift",
        "safety",
        "spoiler_risk",
        "alias_conflict",
    )
)

WRITING_ACTION_SKILL_PLAN = [
    "build-writing-context-pack",
    "character-agency-pass",
    "storytelling-control",
    "next-page-agent",
    "agent-review",
]


@dataclass(frozen=True, slots=True)
class StorySkillDefinition:
    name: str
    version: str
    trigger: str
    input_schema_version: str
    output_schema_version: str
    model_judgment_allowed: bool
    review_policy: str
    writeback_policy: str
    golden_cases: tuple[str, ...]
    failure_cases: tuple[str, ...]
    provider_prompt_ref: str | None = None


@dataclass(frozen=True, slots=True)
class StorySkillRunResult:
    skill_name: str
    skill_version: str
    provider_skill_name: str
    provider_skill_version: str
    prompt_version: str
    input_schema_version: str
    output_schema_version: str
    structured_output: dict[str, object]
    validation_result: dict[str, object]
    raw_result: object


@dataclass(frozen=True, slots=True)
class StorySkillRuntimeContext:
    project_id: UUID
    request_id: str
    story_draft_provider: StoryDraftProvider | None = None
    pov_detection_provider: PovDetectionProvider | None = None
    event_aggregation_provider: EventAggregationAdjudicationProvider | None = None
    memory_extraction_provider: MemoryExtractionProvider | None = None


class StorySkillValidationError(RuntimeError):
    def __init__(
        self,
        *,
        skill_name: str,
        validation_result: dict[str, object],
        structured_output: dict[str, object],
        raw_result: object | None = None,
    ) -> None:
        self.skill_name = skill_name
        self.validation_result = validation_result
        self.structured_output = structured_output
        self.raw_result = raw_result
        message = str(validation_result.get("message") or "Story skill validation failed.")
        super().__init__(message)


class StorySkillRegistry:
    def __init__(self, definitions: list[StorySkillDefinition]) -> None:
        self._definitions = {
            (definition.name, definition.version): definition for definition in definitions
        }

    def get(self, skill_name: str, skill_version: str) -> StorySkillDefinition:
        try:
            return self._definitions[(skill_name, skill_version)]
        except KeyError as exc:
            raise KeyError(f"Unknown story skill {skill_name}@{skill_version}") from exc

    def definitions(self) -> list[StorySkillDefinition]:
        return sorted(self._definitions.values(), key=lambda definition: definition.name)


def resolve_story_skill_plan(
    *,
    action_type: str | None = None,
    job_type: str | None = None,
) -> list[str]:
    if job_type is not None:
        return list(_JOB_TYPE_TO_SKILL_PLAN.get(job_type, []))
    if action_type is not None:
        return list(_ACTION_TYPE_TO_SKILL_PLAN.get(action_type, []))
    return []


def run_skill(
    skill_name: str,
    skill_version: str,
    input_object: object,
    runtime_context: StorySkillRuntimeContext,
    *,
    registry: StorySkillRegistry | None = None,
) -> StorySkillRunResult:
    skill_registry = registry or default_story_skill_registry()
    definition = skill_registry.get(skill_name, skill_version)

    if skill_name == "detect-pov":
        return _run_detect_pov(definition, cast(PovDetectionRequest, input_object), runtime_context)
    if skill_name == "aggregate-events":
        return _run_aggregate_events(
            definition,
            cast(EventAggregationAdjudicationRequest, input_object),
            runtime_context,
        )
    if skill_name == "derive-facts":
        return _run_derive_facts(definition, cast(str, input_object), runtime_context)
    if skill_name == "next-page-agent":
        return _run_next_page_agent(
            definition,
            cast(StoryDraftRequest, input_object),
            runtime_context,
        )
    raise RuntimeError(f"Story skill {skill_name} is registered but has no executable runtime.")


@lru_cache(maxsize=1)
def default_story_skill_registry() -> StorySkillRegistry:
    return StorySkillRegistry(
        [
            _definition(
                "source-normalization",
                trigger="RawSource / SourceVersion import",
                input_schema_version="raw-source-input.v1",
                output_schema_version="processed-markdown-view.v1",
                review_policy="normalization anomalies remain source-local until later review.",
                writeback_policy="persist RawSource/ObjectStore and ProcessedMarkdownView only.",
                golden_cases=(
                    "backend/tests/integration/test_memory_writeback.py::test_normalize_source_job_handler_creates_current_view",
                ),
                failure_cases=(
                    "backend/tests/integration/test_runtime_app.py::test_runtime_rejects_missing_database_url",
                ),
            ),
            _definition(
                "split-structure",
                trigger="ProcessedMarkdownView ready",
                input_schema_version="processed-markdown-view.v1",
                output_schema_version="story-structure-output.v1",
                review_policy=(
                    "structure failure blocks downstream extraction rather than inventing spans."
                ),
                writeback_policy=(
                    "persist StoryChapter, StoryScene, and SourceSpan boundaries only."
                ),
                golden_cases=(
                    "backend/tests/integration/test_memory_writeback.py::test_normalize_source_rebuild_marks_previous_current_view_stale",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_create_facts_from_plain_prose",
                ),
            ),
            _definition(
                "detect-pov",
                trigger="ResolveAliases pipeline step after character mentions exist",
                input_schema_version="pov-detection-request.v1",
                output_schema_version="pov-detection-result.v1",
                model_judgment_allowed=True,
                review_policy=(
                    "unknown or mismatched POV remains uncertain rather than creating canon facts."
                ),
                writeback_policy=(
                    "may update scene POV metadata only after deterministic evidence validation."
                ),
                golden_cases=(
                    "backend/tests/integration/test_pov_detection_provider.py::test_openai_pov_detection_provider_parses_structured_response",
                    "backend/tests/golden/test_provider_golden.py::test_local_pov_detection_golden_ambiguous_scene_output",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_infer_pov_from_perspective_phrase",
                ),
                provider_prompt_ref="prompts/skills/openai_pov_detection/openai-pov-detection.v1.md",
            ),
            _definition(
                "extract-mentions",
                trigger="SourceSpan ready for entity extraction",
                input_schema_version="source-span.v1",
                output_schema_version="mention-list.v1",
                review_policy="ambiguous mention resolution stays reviewable and local.",
                writeback_policy=(
                    "persist StoryMention only; do not create CanonicalEntity from mention "
                    "text alone."
                ),
                golden_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_keeps_alias_resolution_structured",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_create_character_knowledge_from_plain_prose",
                ),
            ),
            _definition(
                "resolve-alias",
                trigger="mentions exist for a SourceSpan",
                input_schema_version="mention-resolution-input.v1",
                output_schema_version="alias-resolution-output.v1",
                review_policy=(
                    "conflicting alias matches create ReviewItem instead of silent merge."
                ),
                writeback_policy=(
                    "persist AliasRecord and scene metadata only after evidence-backed checks."
                ),
                golden_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_alias_conflict_review_round_trip",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_promote_alias_guess_to_canon",
                ),
            ),
            _definition(
                "extract-events",
                trigger="alias resolution completed for a SourceSpan",
                input_schema_version="source-span-event-input.v1",
                output_schema_version="event-candidate-list.v1",
                review_policy=(
                    "event candidates remain provisional until aggregation and fact derivation."
                ),
                writeback_policy="persist StoryEventCandidate only.",
                golden_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_aggregate_events_and_derive_facts_preserve_structured_candidate_flow",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_infer_cross_scene_communication_from_plain_prose",
                ),
            ),
            _definition(
                "aggregate-events",
                trigger="candidate overlaps existing canonical event",
                input_schema_version="event-aggregation-adjudication-request.v1",
                output_schema_version="event-aggregation-adjudication-result.v1",
                model_judgment_allowed=True,
                review_policy=(
                    "conflict_version and uncertain results remain reviewable without silent merge."
                ),
                writeback_policy=(
                    "may merge or split CanonicalEvent only after deterministic evidence "
                    "validation."
                ),
                golden_cases=(
                    "backend/tests/integration/test_event_aggregation_provider.py::test_openai_event_aggregation_provider_parses_structured_response",
                    "backend/tests/golden/test_provider_golden.py::test_local_event_aggregation_golden_uncertain_output",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_aggregate_events_and_derive_facts_preserve_structured_candidate_flow",
                ),
                provider_prompt_ref="prompts/skills/openai_event_aggregation/openai-event-aggregation.v1.md",
            ),
            _definition(
                "derive-facts",
                trigger="accepted SourceDelta writeback or event-to-fact derivation",
                input_schema_version="memory-extraction-input-v1",
                output_schema_version="memory-extraction-output-v1",
                model_judgment_allowed=True,
                review_policy="high-risk or conflicting facts route to ReviewItem/canon gates.",
                writeback_policy=(
                    "may propose FactAssertion and thread updates only; never direct canon writes."
                ),
                golden_cases=(
                    "backend/tests/integration/test_memory_extraction_provider.py::test_openai_memory_extraction_provider_parses_structured_response",
                    "backend/tests/golden/test_provider_golden.py::test_local_memory_extraction_golden_output",
                ),
                failure_cases=(
                    "backend/tests/integration/test_memory_extraction_provider.py::test_memory_writeback_rejects_invalid_provider_output_without_fact_side_effects",
                ),
                provider_prompt_ref="prompts/skills/openai_memory_extraction/openai-memory-extraction.v1.md",
            ),
            _definition(
                "check-continuity",
                trigger="author asks to inspect continuity or risk",
                input_schema_version="continuity-check-input.v1",
                output_schema_version="review-finding-list.v1",
                review_policy="all continuity conflicts remain explicit review findings.",
                writeback_policy="no direct canon writes; findings remain risk-layer output.",
                golden_cases=(
                    "backend/tests/integration/test_agent_review_job.py::test_agent_review_job_records_findings",
                ),
                failure_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_check_risk_requires_current_text_window",
                ),
            ),
            _definition(
                "rewrite-current-canon",
                trigger="memory page needs rebuilt current canon after accepted evidence",
                input_schema_version="memory-page-rewrite-input.v1",
                output_schema_version="memory-page-rewrite-output.v1",
                review_policy="rewrites preserve evidence lineage and canon status boundaries.",
                writeback_policy="update MemoryPage.current_canon from accepted facts only.",
                golden_cases=(
                    "backend/tests/integration/test_memory_writeback.py::test_low_risk_writeback_promotes_memory_and_graph",
                ),
                failure_cases=(
                    "backend/tests/integration/test_memory_writeback.py::test_memory_writeback_rejects_invalid_ref_shape",
                ),
            ),
            _definition(
                "build-writing-context-pack",
                trigger="writing or answer request needs scoped context",
                input_schema_version="build-writing-context-pack-input.v1",
                output_schema_version="writing-context-pack.v1",
                review_policy="risk/disputed items stay in risk context with evidence refs.",
                writeback_policy="read-only snapshot; no canon or graph mutations.",
                golden_cases=(
                    "backend/tests/integration/test_memory_answer_context_pack.py::test_context_pack_ranks_facts_by_persisted_embedding_semantic_recall",
                ),
                failure_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_build_context_pack_rejects_invalid_budget",
                ),
            ),
            _definition(
                "answer-with-evidence",
                trigger="ask_memory ActionRequest",
                input_schema_version="memory-answer-input.v1",
                output_schema_version="memory-answer-output.v1",
                model_judgment_allowed=True,
                review_policy="ambiguous answers remain unknown with caveats and evidence refs.",
                writeback_policy="read-only answer surface; no canon writes.",
                golden_cases=(
                    "backend/tests/integration/test_memory_answer_context_pack.py::test_memory_answer_finds_first_appearance_from_source_mentions",
                ),
                failure_cases=(
                    "backend/tests/integration/test_memory_answer_context_pack.py::test_memory_answer_returns_unknown_without_structured_evidence_target",
                ),
            ),
            _definition(
                "character-agency-pass",
                trigger="drafting flow after context pack assembly",
                input_schema_version="character-agency-input.v1",
                output_schema_version="character-agency-output.v1",
                model_judgment_allowed=True,
                review_policy="agency constraints stay advisory until draft/review output.",
                writeback_policy="no direct memory or canon mutation.",
                golden_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_action_request_run_returns_beat_candidates",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_infer_inner_state_as_fact",
                ),
            ),
            _definition(
                "storytelling-control",
                trigger="drafting flow after context pack assembly",
                input_schema_version="storytelling-control-input.v1",
                output_schema_version="storytelling-control-output.v1",
                model_judgment_allowed=True,
                review_policy="controls constrain generation but never become canon evidence.",
                writeback_policy="no direct memory or canon mutation.",
                golden_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_action_request_run_returns_beat_candidates",
                ),
                failure_cases=(
                    "backend/tests/integration/test_source_pipeline_cleanup.py::test_source_pipeline_does_not_promote_style_signal_to_fact",
                ),
            ),
            _definition(
                "next-page-agent",
                trigger="drafting or revision ActionRequest",
                input_schema_version="story-draft-request.v1",
                output_schema_version="story-draft-result.v1",
                model_judgment_allowed=True,
                review_policy="review cues stay in agent-risk layer until formal review/writeback.",
                writeback_policy="produces DraftCandidate only; no direct memory/canon writes.",
                golden_cases=(
                    "backend/tests/integration/test_story_draft_provider.py::test_openai_story_draft_provider_parses_structured_response",
                    "backend/tests/golden/test_provider_golden.py::test_local_story_draft_golden_output_blocks_forced_risk",
                ),
                failure_cases=(
                    "backend/tests/integration/test_agent_candidate_job.py::test_agent_candidate_job_rejects_blank_provider_output_without_partial_candidate",
                    "backend/tests/integration/test_agent_candidate_job.py::test_agent_candidate_job_rejects_mismatched_contract_metadata_without_partial_candidate",
                ),
                provider_prompt_ref="prompts/skills/openai_story_draft/openai-story-draft.v1.md",
            ),
            _definition(
                "agent-review",
                trigger="draft candidate exists or user requests risk review",
                input_schema_version="agent-review-input.v1",
                output_schema_version="agent-review-output.v1",
                model_judgment_allowed=True,
                review_policy="all findings remain explicit and reviewable.",
                writeback_policy="persists AgentReviewFinding only; never canon.",
                golden_cases=(
                    "backend/tests/integration/test_agent_review_job.py::test_agent_review_job_records_findings",
                ),
                failure_cases=(
                    "backend/tests/integration/test_api_contracts.py::test_check_risk_requires_current_text_window",
                ),
            ),
        ]
    )


def _definition(
    name: str,
    *,
    trigger: str,
    input_schema_version: str,
    output_schema_version: str,
    review_policy: str,
    writeback_policy: str,
    golden_cases: tuple[str, ...],
    failure_cases: tuple[str, ...],
    model_judgment_allowed: bool = False,
    provider_prompt_ref: str | None = None,
) -> StorySkillDefinition:
    return StorySkillDefinition(
        name=name,
        version=STORY_SKILL_VERSION,
        trigger=trigger,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        model_judgment_allowed=model_judgment_allowed,
        review_policy=review_policy,
        writeback_policy=writeback_policy,
        golden_cases=golden_cases,
        failure_cases=failure_cases,
        provider_prompt_ref=provider_prompt_ref,
    )


def _run_detect_pov(
    definition: StorySkillDefinition,
    request: PovDetectionRequest,
    runtime_context: StorySkillRuntimeContext,
) -> StorySkillRunResult:
    provider = runtime_context.pov_detection_provider
    if provider is None:
        raise RuntimeError("detect-pov requires a configured POV detection provider.")
    result = provider.detect(request)
    structured_output = asdict(result)
    _validate_pov_detection_result(result, request)
    return StorySkillRunResult(
        skill_name=definition.name,
        skill_version=definition.version,
        provider_skill_name=provider.skill_name,
        provider_skill_version=provider.skill_version,
        prompt_version=_provider_prompt_version(provider),
        input_schema_version=definition.input_schema_version,
        output_schema_version=definition.output_schema_version,
        structured_output=cast(dict[str, object], structured_output),
        validation_result={"status": "valid"},
        raw_result=result,
    )


def _run_aggregate_events(
    definition: StorySkillDefinition,
    request: EventAggregationAdjudicationRequest,
    runtime_context: StorySkillRuntimeContext,
) -> StorySkillRunResult:
    provider = runtime_context.event_aggregation_provider
    if provider is None:
        raise RuntimeError("aggregate-events requires a configured event aggregation provider.")
    result = provider.adjudicate(request)
    structured_output = asdict(result)
    _validate_event_aggregation_result(result, request)
    return StorySkillRunResult(
        skill_name=definition.name,
        skill_version=definition.version,
        provider_skill_name=provider.skill_name,
        provider_skill_version=provider.skill_version,
        prompt_version=_provider_prompt_version(provider),
        input_schema_version=definition.input_schema_version,
        output_schema_version=definition.output_schema_version,
        structured_output=cast(dict[str, object], structured_output),
        validation_result={"status": "valid"},
        raw_result=result,
    )


def _run_derive_facts(
    definition: StorySkillDefinition,
    text: str,
    runtime_context: StorySkillRuntimeContext,
) -> StorySkillRunResult:
    provider = runtime_context.memory_extraction_provider
    if provider is None:
        raise RuntimeError("derive-facts requires a configured memory extraction provider.")
    result = provider.extract(text)
    structured_output = cast(dict[str, object], asdict(result))
    validation_result = _memory_extraction_validation_result(result)
    if validation_result["status"] != "valid":
        raise StorySkillValidationError(
            skill_name=definition.name,
            validation_result=validation_result,
            structured_output=structured_output,
            raw_result=result,
        )
    return StorySkillRunResult(
        skill_name=definition.name,
        skill_version=definition.version,
        provider_skill_name=provider.skill_name,
        provider_skill_version=provider.skill_version,
        prompt_version=_provider_prompt_version(provider),
        input_schema_version=definition.input_schema_version,
        output_schema_version=definition.output_schema_version,
        structured_output=structured_output,
        validation_result=validation_result,
        raw_result=result,
    )


def _run_next_page_agent(
    definition: StorySkillDefinition,
    request: StoryDraftRequest,
    runtime_context: StorySkillRuntimeContext,
) -> StorySkillRunResult:
    provider = runtime_context.story_draft_provider
    if provider is None:
        raise RuntimeError("next-page-agent requires a configured story draft provider.")
    result = provider.draft(request)
    structured_output = dict(result.structured_output)
    validation_result = _story_draft_validation_result(request, result)
    if validation_result["status"] != "valid":
        raise StorySkillValidationError(
            skill_name=definition.name,
            validation_result=validation_result,
            structured_output=structured_output,
            raw_result=result,
        )
    return StorySkillRunResult(
        skill_name=definition.name,
        skill_version=definition.version,
        provider_skill_name=provider.skill_name,
        provider_skill_version=provider.skill_version,
        prompt_version=_provider_prompt_version(provider),
        input_schema_version=definition.input_schema_version,
        output_schema_version=definition.output_schema_version,
        structured_output=structured_output,
        validation_result=validation_result,
        raw_result=result,
    )


def _provider_prompt_version(provider: object) -> str:
    prompt_version = getattr(provider, "prompt_version", None)
    if isinstance(prompt_version, str) and prompt_version.strip():
        return prompt_version.strip()
    return str(getattr(provider, "skill_version", "unknown"))


def _validate_pov_detection_result(
    result: PovDetectionResult,
    request: PovDetectionRequest,
) -> None:
    if result.pov_mode not in VALID_POV_MODES:
        raise StorySkillValidationError(
            skill_name="detect-pov",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": f"invalid pov_mode: {result.pov_mode}",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    if result.confidence < 0 or result.confidence > 1:
        raise StorySkillValidationError(
            skill_name="detect-pov",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "POV detection confidence must be within 0..1.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    span_ref = str(request.source_span_id)
    evidence_span_ids = {str(span_id) for span_id in result.evidence_span_ids}
    if evidence_span_ids != {span_ref}:
        raise StorySkillValidationError(
            skill_name="detect-pov",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "POV detection evidence must cite only the current SourceSpan.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )


def _validate_event_aggregation_result(
    result: EventAggregationAdjudicationResult,
    request: EventAggregationAdjudicationRequest,
) -> None:
    if result.decision not in VALID_EVENT_DECISIONS:
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "Event aggregation provider returned invalid decision.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    if not 0 <= result.confidence <= 1:
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "Event aggregation confidence must be within 0..1.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    if not isinstance(result.rationale, str) or not result.rationale.strip():
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "Event aggregation provider returned empty rationale.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    evidence_span_ids = {str(span_id) for span_id in result.evidence_span_ids}
    allowed_span_ids = set(request.existing_event_evidence_span_ids) | set(
        request.candidate_evidence_span_ids
    )
    if not evidence_span_ids or not evidence_span_ids.issubset(allowed_span_ids):
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": (
                    "Event aggregation provider cited evidence outside the adjudication request."
                ),
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    if not set(request.existing_event_evidence_span_ids).issubset(evidence_span_ids):
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "Event aggregation provider must cite existing event evidence.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )
    if not set(request.candidate_evidence_span_ids).issubset(evidence_span_ids):
        raise StorySkillValidationError(
            skill_name="aggregate-events",
            validation_result={
                "status": "invalid",
                "error_code": "llm_output_invalid",
                "message": "Event aggregation provider must cite candidate evidence.",
            },
            structured_output=cast(dict[str, object], asdict(result)),
            raw_result=result,
        )


def _memory_extraction_validation_result(
    result: MemoryExtractionResult,
) -> dict[str, object]:
    for fact in result.facts:
        if fact.risk_level not in VALID_MEMORY_RISK_LEVELS:
            return _invalid_result("Memory extraction provider returned invalid fact risk_level.")
        if not _valid_ref_shape(fact.subject_ref) or not _valid_ref_shape(fact.object_ref):
            return _invalid_result("Memory extraction provider returned invalid fact ref shape.")
        if not isinstance(fact.predicate, str) or not fact.predicate.strip():
            return _invalid_result("Memory extraction provider returned invalid predicate.")
    for update in result.thread_updates:
        if update.risk_level not in VALID_MEMORY_RISK_LEVELS:
            return _invalid_result("Memory extraction provider returned invalid thread risk_level.")
        if update.update_type not in VALID_THREAD_UPDATE_TYPES:
            return _invalid_result(
                "Memory extraction provider returned invalid thread update_type."
            )
        if not _valid_ref_shape(update.target_ref):
            return _invalid_result("Memory extraction provider returned invalid target_ref.")
        if not isinstance(update.description, str) or not update.description.strip():
            return _invalid_result("Memory extraction provider returned empty thread description.")
    return {"status": "valid"}


def _story_draft_validation_result(
    request: StoryDraftRequest,
    result: StoryDraftResult,
) -> dict[str, object]:
    if not result.text.strip():
        return _invalid_result("Story draft provider returned empty text.")
    structured_text = result.structured_output.get("text")
    if not isinstance(structured_text, str) or not structured_text.strip():
        return _invalid_result("Story draft provider returned structured output without text.")
    if structured_text.strip() != result.text.strip():
        return _invalid_result("Story draft provider text does not match structured output text.")
    expected_contract_id = request.prose_rendering_contract.get("contract_id")
    expected_mode = request.prose_rendering_contract.get("mode")
    if (
        not isinstance(expected_contract_id, str)
        or not isinstance(expected_mode, str)
        or result.structured_output.get("prose_contract_id") != expected_contract_id
        or result.structured_output.get("mode") != expected_mode
    ):
        return _invalid_result("Story draft provider returned mismatched contract metadata.")
    if not result.finish_reason.strip():
        return _invalid_result("Story draft provider returned empty finish reason.")
    for cue in result.review_cues:
        if not _valid_story_review_cue(cue):
            return _invalid_result("Story draft provider returned invalid review cue.")
    return {"status": "valid"}


def _valid_story_review_cue(cue: dict[str, object]) -> bool:
    required_text_fields = ("risk_level", "risk_type", "summary")
    if any(
        not isinstance(cue.get(field), str) or not str(cue[field]).strip()
        for field in required_text_fields
    ):
        return False
    if cue["risk_level"] not in VALID_AGENT_RISK_LEVELS:
        return False
    if not isinstance(cue.get("can_offer_to_author"), bool):
        return False
    review_type = cue.get("maps_to_review_type_if_accepted")
    return review_type is None or (
        isinstance(review_type, str) and review_type in VALID_AGENT_REVIEW_TYPES
    )


def _invalid_result(message: str) -> dict[str, object]:
    return {"status": "invalid", "error_code": "llm_output_invalid", "message": message}


def _valid_ref_shape(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    ref_value = cast(dict[str, object], value)
    ref_type = ref_value.get("type")
    ref_id = ref_value.get("id")
    return (
        isinstance(ref_type, str)
        and bool(ref_type.strip())
        and isinstance(ref_id, str)
        and bool(ref_id.strip())
    )


_ACTION_TYPE_TO_SKILL_PLAN: dict[str, tuple[str, ...]] = {
    "ask_memory": ("answer-with-evidence",),
    "check_risk": ("agent-review",),
    "suggest_next_direction": (
        "build-writing-context-pack",
        "character-agency-pass",
        "storytelling-control",
    ),
    "explain_candidate": ("agent-review",),
    "revise_candidate": tuple(WRITING_ACTION_SKILL_PLAN),
    "draft_next_passage": tuple(WRITING_ACTION_SKILL_PLAN),
    "rewrite_current_page": tuple(WRITING_ACTION_SKILL_PLAN),
    "rewrite_span": tuple(WRITING_ACTION_SKILL_PLAN),
    "continue_small_passage": tuple(WRITING_ACTION_SKILL_PLAN),
    "render_current_beat": tuple(WRITING_ACTION_SKILL_PLAN),
}

_JOB_TYPE_TO_SKILL_PLAN: dict[str, tuple[str, ...]] = {
    "normalize_source": ("source-normalization",),
    "split_structure": ("split-structure",),
    "extract_mentions": ("extract-mentions",),
    "resolve_aliases": ("resolve-alias", "detect-pov"),
    "extract_events": ("extract-events",),
    "aggregate_events": ("aggregate-events",),
    "derive_facts": ("derive-facts",),
    "run_conflict_policy": ("check-continuity",),
    "run_memory_writeback": ("derive-facts", "rewrite-current-canon"),
    "build_context_pack": ("build-writing-context-pack",),
    "run_agent_candidate": tuple(WRITING_ACTION_SKILL_PLAN),
    "run_agent_review": ("agent-review",),
}
