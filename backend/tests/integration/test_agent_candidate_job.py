from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult
from sextant.infra.agent_candidate import AgentCandidateHandler
from sextant.infra.db.models import (
    AgentActionRequestRecord,
    AgentContextPackRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    Base,
    FactAssertionRecord,
    JobRecord,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SkillRun,
    SourceDeltaRecord,
    SourceVersion,
)
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.worker import DbWorker
from sextant.skills.local_story_draft import LocalStoryDraftProvider
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


@pytest.fixture
def object_store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


def _assert_failed_skill_run_attempts(
    session: Session,
    *,
    message: str,
    structured_text: str | None = None,
) -> None:
    skill_runs = sorted(
        session.query(SkillRun).all(),
        key=lambda run: run.validation_result["attempt"],
    )
    assert len(skill_runs) == 2
    for expected_attempt, skill_run in enumerate(skill_runs, start=1):
        assert skill_run.status == "failed_terminal"
        if structured_text is not None:
            assert skill_run.structured_output["text"] == structured_text
        assert skill_run.validation_result == {
            "status": "invalid",
            "error_code": "llm_output_invalid",
            "message": message,
            "attempt": expected_attempt,
            "max_attempts": 2,
            "will_retry": expected_attempt < 2,
        }


def test_agent_candidate_job_creates_draft_candidate_without_memory_side_effects(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, LocalStoryDraftProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    assert session.get(AgentActionRequestRecord, action_request.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    assert candidate.action_request_id == action_request.id
    assert candidate.status == "offered_to_author"
    assert candidate.affected_range == {"start": 12, "end": 38}
    assert candidate.base_hash == "hash-v1"
    assert "米拉" in object_store.get_text(candidate.candidate_text_ref)
    assert session.query(AgentContextPackRecord).count() == 1
    controls = {
        control.control_type: control.payload
        for control in session.query(AgentStorytellingControlRecord).all()
    }
    assert {
        "role_slot",
        "character_casting_decision",
        "scene_sequel_mode",
        "dramatic_behavior_plan",
        "prose_rendering_contract",
    } <= set(controls)
    serialized_controls = json.dumps(controls, ensure_ascii=False, sort_keys=True)
    assert "local-pressure" not in serialized_controls
    assert "locked archive room" not in serialized_controls
    assert "Mira chooses action instead of exposition" not in serialized_controls
    role_slot = controls["role_slot"]
    casting_decision = controls["character_casting_decision"]
    assert casting_decision["decision"] == "avoid_character"
    assert casting_decision["target_entity_ref"] is None
    assert casting_decision["new_character_seed_id"] is None
    assert casting_decision["role_slot_id"] == role_slot["role_slot_id"]
    assert str(casting_decision["decision_id"]).startswith(f"{role_slot['function']}-casting-")
    assert role_slot["scene_need"]
    scene_sequel = controls["scene_sequel_mode"]
    assert scene_sequel["passage_mode"] == "scene"
    assert scene_sequel["current_pressure"]
    assert scene_sequel["required_turn"]
    prose_contract = controls["prose_rendering_contract"]
    assert prose_contract["role_slots"] == [role_slot]
    assert prose_contract["character_casting_decisions"] == [casting_decision]
    assert prose_contract["scene_sequel_mode"] == scene_sequel
    assert prose_contract["opposition"] == scene_sequel["opposition"]
    assert session.query(SkillRun).filter_by(skill_name="local_story_draft").count() == 1
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_ignores_forced_risk_constraint_from_action_request(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={"force_risk_fact_in_draft": True},
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, LocalStoryDraftProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    controls = {
        control.control_type: control.payload
        for control in session.query(AgentStorytellingControlRecord).all()
    }
    assert candidate.status == "offered_to_author"
    assert "force_risk_fact_in_draft" not in controls["prose_rendering_contract"]
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_blocks_hard_no_contract_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={"hard_no": ["不要直接写“凯斯特偷走了灯图”"]},
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, ContractViolatingProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "blocked"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "prose_contract_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["hard_no"] == "不要直接写“凯斯特偷走了灯图”"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is False
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_no_turn_contract_risk_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, NoTurnProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "no_turn_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_new_character_policy_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, NewCharacterProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "cast_policy_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["new_character_policy"] == "avoid"
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_generic_scene_role_intro_without_fixture_marker(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, GenericSceneRoleProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "cast_policy_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["matched_text"] == "一名临时检票员"
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_blocks_target_range_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, RangeViolatingProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "blocked"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "target_range_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_range"] == {"start": 12, "end": 38}
    assert finding.storytelling_refs["attempted_range"] == {"start": 0, "end": 120}
    assert finding.can_offer_to_author is False
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_blocks_non_pov_mind_reading_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={"pov_character": "米拉"},
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, NonPovMindProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "blocked"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "non_pov_mind_reading"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["pov_character"] == "米拉"
    assert finding.storytelling_refs["matched_character"] == "凯斯特"
    assert finding.can_offer_to_author is False
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_inner_state_budget_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={
            "pov_character": "米拉",
            "inner_state_budget": {"max_direct_sentences": 1},
        },
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, InnerStateProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "inner_state_budget_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["direct_inner_state_count"] == 3
    assert finding.storytelling_refs["max_direct_sentences"] == 1
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_inner_state_overload_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={
            "pov_character": "米拉",
            "inner_state_budget": {"max_direct_sentences": 4},
        },
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, InnerStateProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "inner_state_overload"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["direct_inner_state_count"] == 3
    assert finding.storytelling_refs["overload_threshold"] == 3
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_style_language_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, EnglishStyleProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "style_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["expected_language"] == "zh"
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_exposition_without_scene_behavior(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={
            "show_not_tell_targets": [
                "Mira's fear should appear through action and object detail."
            ],
        },
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, ExpositionProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "exposition_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["show_not_tell_targets"] == [
        "Mira's fear should appear through action and object detail."
    ]
    assert finding.storytelling_refs["exposition_sentence_count"] == 3
    assert finding.storytelling_refs["observable_behavior_signal_count"] == 0
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_dialogue_without_required_subtext(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={
            "subtext_targets": ["Mira tests Kestrel without stating the accusation."],
        },
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, SubtextMissingProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "subtext_missing"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["subtext_targets"] == [
        "Mira tests Kestrel without stating the accusation."
    ]
    assert finding.storytelling_refs["matched_dialogue"] == (
        "因为空地图盒说明凯斯特有问题，所以我们必须立刻怀疑他。"
    )
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_undramatized_plan_without_visible_behavior(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(
        session,
        object_store,
        constraints={
            "render_as_action": ["Mira touches the empty map case instead of explaining pressure."],
            "render_as_object": ["The empty map case carries the pressure."],
        },
    )
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, UndramatizedProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "dramatization_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["dramatization_targets"] == [
        "Mira touches the empty map case instead of explaining pressure.",
        "The empty map case carries the pressure.",
    ]
    assert finding.storytelling_refs["observable_behavior_signal_count"] == 0
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_flags_story_overreach_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, OverreachProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    finding = session.query(AgentReviewFindingRecord).one()
    assert candidate.status == "offered_to_author"
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "control_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    expected_categories = {
        "time_jump",
        "irreversible_outcome",
        "thread_resolution",
        "scope_expansion",
        "author_level_decision",
    }
    assert set(finding.storytelling_refs["matched_categories"]) >= expected_categories
    evidence_terms = finding.storytelling_refs["evidence_terms"]
    assert set(evidence_terms) >= expected_categories
    assert all(isinstance(evidence_terms[category], list) for category in expected_categories)
    assert all(evidence_terms[category] for category in expected_categories)
    assert finding.can_offer_to_author is True
    assert finding.draft_local_only is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_blank_provider_output_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, BlankStoryProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error == "llm_output_invalid: Story draft provider returned empty text."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned empty text.",
        structured_text="   ",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_retries_invalid_provider_output_before_persisting_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)
    provider = InvalidThenValidStoryProvider()

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, provider)},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    assert provider.call_count == 2
    assert session.get(JobRecord, job.id).status == "succeeded"
    candidate = session.query(AgentDraftCandidateRecord).one()
    assert candidate.status == "offered_to_author"
    assert "米拉" in object_store.get_text(candidate.candidate_text_ref)
    skill_runs = session.query(SkillRun).all()
    assert len(skill_runs) == 2
    failed_skill_run = next(run for run in skill_runs if run.status == "failed_terminal")
    succeeded_skill_run = next(run for run in skill_runs if run.status == "succeeded")
    assert failed_skill_run.validation_result == {
        "status": "invalid",
        "error_code": "llm_output_invalid",
        "message": "Story draft provider returned empty text.",
        "attempt": 1,
        "max_attempts": 2,
        "will_retry": True,
    }
    assert succeeded_skill_run.validation_result == {"status": "valid"}
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_mismatched_provider_text_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, MismatchedTextProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error
        == "llm_output_invalid: Story draft provider text does not match structured output text."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider text does not match structured output text.",
        structured_text="凯斯特改写了这一段。",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_malformed_review_cue_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, MalformedReviewCueProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error
        == "llm_output_invalid: Story draft provider returned invalid review cue."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned invalid review cue.",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_unknown_review_cue_level_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {"run_agent_candidate": AgentCandidateHandler(object_store, UnknownReviewLevelProvider())},
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error
        == "llm_output_invalid: Story draft provider returned invalid review cue."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned invalid review cue.",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_unknown_review_cue_mapping_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {
            "run_agent_candidate": AgentCandidateHandler(
                object_store, UnknownReviewMappingProvider()
            )
        },
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error
        == "llm_output_invalid: Story draft provider returned invalid review cue."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned invalid review cue.",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


def test_agent_candidate_job_rejects_mismatched_contract_metadata_without_partial_candidate(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    actor_id, action_request = _seed_action_request(session, object_store)
    job = _seed_candidate_job(session, action_request, actor_id)

    processed = DbWorker(
        session,
        {
            "run_agent_candidate": AgentCandidateHandler(
                object_store, MismatchedContractMetadataProvider()
            )
        },
    ).run_once(worker_id="worker-agent-candidate")

    assert processed is True
    refreshed_job = session.get(JobRecord, job.id)
    assert refreshed_job.status == "failed_terminal"
    assert (
        refreshed_job.last_error
        == "llm_output_invalid: Story draft provider returned mismatched contract metadata."
    )
    _assert_failed_skill_run_attempts(
        session,
        message="Story draft provider returned mismatched contract metadata.",
    )
    assert session.query(AgentDraftCandidateRecord).count() == 0
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    assert session.query(FactAssertionRecord).count() == 0


class ContractViolatingProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "凯斯特偷走了灯图。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class NoTurnProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉站在原地。空气沉沉。旧墙没有变化。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class NewCharacterProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "一个陌生人从转角出现，挡住米拉去路。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class GenericSceneRoleProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "一名临时检票员从暗门后走出，挡住米拉去路。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class RangeViolatingProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉停在门口，伸手推开锁孔旁的铜片。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
                "affected_range": {"start": 0, "end": 120},
            },
            review_cues=[],
        )


class NonPovMindProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "凯斯特心想米拉已经输掉了这一局。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class InnerStateProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉停在门口。米拉害怕。米拉知道自己不能失败。米拉觉得门后有答案。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class EnglishStyleProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "Mira opened the western archive door and explained why the map frightened her."
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class ExpositionProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉说明自己不能失败。她解释空地图盒意味着背叛。因此局势更加危险。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class SubtextMissingProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "“因为空地图盒说明凯斯特有问题，所以我们必须立刻怀疑他。”米拉说道。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class UndramatizedProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "雨声压住屋顶。档案室仍旧昏暗。灯图的传闻悬在门外。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class OverreachProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = (
            "十二个月后，岑予再也没有回到荒港。旧案的真相终于揭晓，"
            "整个王国改写了誓约，他决定余生守口如瓶。"
        )
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class BlankStoryProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        return StoryDraftResult(
            text="   ",
            finish_reason="complete",
            structured_output={
                "text": "   ",
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class InvalidThenValidStoryProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def __init__(self) -> None:
        self.call_count = 0
        self._valid_provider = LocalStoryDraftProvider()

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        self.call_count += 1
        if self.call_count == 1:
            return StoryDraftResult(
                text="   ",
                finish_reason="complete",
                structured_output={
                    "text": "   ",
                    "mode": request.prose_rendering_contract.get("mode"),
                    "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
                },
                review_cues=[],
            )
        return self._valid_provider.draft(request)


class MismatchedTextProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        return StoryDraftResult(
            text="米拉推开西档案室的门。",
            finish_reason="complete",
            structured_output={
                "text": "凯斯特改写了这一段。",
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[],
        )


class MalformedReviewCueProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉推开西档案室的门。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[
                {
                    "risk_type": "canon_risk",
                    "summary": "缺少 risk_level。",
                    "can_offer_to_author": False,
                }
            ],
        )


class UnknownReviewLevelProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉推开西档案室的门。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[
                {
                    "risk_level": "critical",
                    "risk_type": "canon_risk",
                    "summary": "非法风险等级。",
                    "can_offer_to_author": False,
                }
            ],
        )


class UnknownReviewMappingProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉推开西档案室的门。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": request.prose_rendering_contract.get("contract_id"),
            },
            review_cues=[
                {
                    "risk_level": "high",
                    "risk_type": "canon_risk",
                    "summary": "非法 ReviewItem 映射。",
                    "can_offer_to_author": False,
                    "maps_to_review_type_if_accepted": "made_up_conflict",
                }
            ],
        )


class MismatchedContractMetadataProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        text = "米拉推开西档案室的门。"
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": request.prose_rendering_contract.get("mode"),
                "prose_contract_id": "wrong-contract",
            },
            review_cues=[],
        )


def _seed_action_request(
    session: Session,
    object_store: LocalObjectStore,
    *,
    constraints: dict[str, object] | None = None,
) -> tuple[UUID, AgentActionRequestRecord]:
    project = Project(id=uuid4(), name="Harbor Nine")
    actor_id = uuid4()
    membership = ProjectMembership(
        id=uuid4(),
        project_id=project.id,
        actor_id=actor_id,
        role="owner",
        status="active",
    )
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref=object_store.put_text(f"raw/{project.id}.txt", "米拉停在西档案室门口。"),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash="hash-v1",
        raw_text_ref=raw_source.raw_text_ref,
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="让米拉继续推进这一页，但不要泄露奥林的身份。",
        trigger="toolbar",
        action_type="draft_next_passage",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 12, "end": 38},
        },
        constraints=constraints or {},
        expected_output="draft_candidate",
        status="submitted",
        created_by=actor_id,
    )
    session.add_all([project, membership, raw_source, version, action_request])
    session.commit()
    return actor_id, action_request


def _seed_candidate_job(
    session: Session,
    action_request: AgentActionRequestRecord,
    actor_id: UUID,
) -> JobRecord:
    job = JobRecord(
        id=uuid4(),
        project_id=action_request.project_id,
        job_type="run_agent_candidate",
        status="queued",
        idempotency_key=f"run-agent-candidate:{action_request.id}:local-story-draft.v1",
        payload={
            "step": "run_agent_candidate",
            "pipeline_version": "pipeline-v1",
            "action_request_id": str(action_request.id),
            "actor_id": str(actor_id),
            "current_text_window": "米拉停在西档案室门口。",
            "prompt_version": "local-story-draft.v1",
            "input_hash": f"input:{action_request.id}",
        },
    )
    session.add(job)
    session.commit()
    return job
