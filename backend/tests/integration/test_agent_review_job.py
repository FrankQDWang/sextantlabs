from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sextant.infra.agent_review import AgentReviewHandler
from sextant.infra.db.models import (
    AgentActionRequestRecord,
    AgentDraftCandidateRecord,
    AgentReviewFindingRecord,
    AgentStorytellingControlRecord,
    AuditEvent,
    Base,
    JobRecord,
    Project,
    RawSource,
    ReviewItemRecord,
    SourceDeltaRecord,
    SourceVersion,
)
from sextant.infra.object_store import LocalObjectStore
from sextant.infra.worker import DbWorker
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


def test_agent_review_job_blocks_high_risk_candidate_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="这段把未确认线索写成已经坐实，越过了当前证据。",
    )
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "blocked"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "canon_risk"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is False
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "blocked"


def test_agent_review_job_blocks_hard_no_contract_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="凯斯特偷走了灯图。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-hard-no",
                "hard_no": ["不要直接写“凯斯特偷走了灯图”"],
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "blocked"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "prose_contract_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-hard-no"
    assert finding.storytelling_refs["hard_no"] == "不要直接写“凯斯特偷走了灯图”"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is False
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "blocked"


def test_agent_review_job_flags_no_turn_contract_risk_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉害怕。她知道自己不能再失败。念头一层层绕回原处。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-no-turn",
                "passage_mode": "scene",
                "required_turn": "Mira chooses action instead of exposition",
                "ending_shape": "decision",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "no_turn_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-no-turn"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_scene_without_goal_or_opposition(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉打开空地图盒，转身走向窗边。雨声压住门外的脚步。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-scene-structure",
                "passage_mode": "scene",
                "scene_goal": "Mira must recover the hidden map.",
                "opposition": "Orrin blocks the archive door.",
                "required_turn": "Mira meets resistance before the page turns.",
                "ending_shape": "setback",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "scene_mode_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-scene-structure"
    assert finding.storytelling_refs["passage_mode"] == "scene"
    assert finding.storytelling_refs["missing_elements"] == ["scene_goal", "opposition"]
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_mixed_without_reaction_or_decision(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉为了确认灯图，推开门走向档案柜。门锁挡住去路，雨声贴着窗缝。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-mixed-structure",
                "passage_mode": "mixed",
                "scene_goal": "Mira must test the locked archive.",
                "opposition": "The lock blocks the archive cabinet.",
                "reaction": "Mira registers the pressure before acting again.",
                "decision": "Mira chooses one reversible next step.",
                "required_turn": "Mira makes a small action and small choice.",
                "ending_shape": "pressure_then_choice",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "mode_mixing_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-mixed-structure"
    assert finding.storytelling_refs["passage_mode"] == "mixed"
    assert finding.storytelling_refs["missing_elements"] == ["reaction", "decision"]
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_sequel_without_dilemma_or_decision(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉看见空地图盒，低声说出自己还在害怕。雨声压住门外的脚步。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-sequel-structure",
                "passage_mode": "sequel",
                "reaction": "Mira absorbs the cost of the exposed map.",
                "dilemma": "Whether to trust Orrin or hide the clue.",
                "decision": "Choose the next step before the page ends.",
                "required_turn": "Mira makes a decision from the dilemma.",
                "ending_shape": "decision",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "sequel_mode_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-sequel-structure"
    assert finding.storytelling_refs["passage_mode"] == "sequel"
    assert finding.storytelling_refs["missing_elements"] == ["dilemma", "decision"]
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_new_character_policy_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="一个陌生人从转角出现，挡住米拉去路。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-cast-policy",
                "passage_mode": "scene",
                "new_character_policy": "no_new_character",
                "allowed_cast": [{"type": "character", "id": "mira", "name": "米拉"}],
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "cast_policy_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-cast-policy"
    assert finding.storytelling_refs["new_character_policy"] == "no_new_character"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_generic_scene_role_intro_without_fixture_marker(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="一名临时检票员从暗门后走出，挡住米拉去路。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-cast-policy-generic-role",
                "passage_mode": "scene",
                "new_character_policy": "no_new_character",
                "allowed_cast": [{"type": "character", "id": "mira", "name": "米拉"}],
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "cast_policy_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-cast-policy-generic-role"
    assert finding.storytelling_refs["matched_text"] == "一名临时检票员"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_blocks_target_range_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉停在门口，伸手推开锁孔旁的铜片。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-target-range",
                "target_position": {
                    "range": {"start": 4, "end": 8},
                },
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "blocked"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "target_range_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-target-range"
    assert finding.storytelling_refs["contract_range"] == {"start": 4, "end": 8}
    assert finding.storytelling_refs["attempted_range"] == {"start": 0, "end": 12}
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is False
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "blocked"


def test_agent_review_job_blocks_non_pov_mind_reading_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="凯斯特心想米拉已经输掉了这一局。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-pov",
                "pov_character": "米拉",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "blocked"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "high"
    assert finding.risk_type == "non_pov_mind_reading"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-pov"
    assert finding.storytelling_refs["pov_character"] == "米拉"
    assert finding.storytelling_refs["matched_character"] == "凯斯特"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is False
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "blocked"


def test_agent_review_job_flags_inner_state_budget_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉停在门口。米拉害怕。米拉知道自己不能失败。米拉觉得门后有答案。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-inner-state",
                "pov_character": "米拉",
                "inner_state_budget": {"max_direct_sentences": 1},
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "inner_state_budget_violation"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-inner-state"
    assert finding.storytelling_refs["direct_inner_state_count"] == 3
    assert finding.storytelling_refs["max_direct_sentences"] == 1
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_inner_state_overload_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉停在门口。米拉害怕。米拉知道自己不能失败。米拉觉得门后有答案。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-inner-state-overload",
                "pov_character": "米拉",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "inner_state_overload"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-inner-state-overload"
    assert finding.storytelling_refs["direct_inner_state_count"] == 3
    assert finding.storytelling_refs["overload_threshold"] == 3
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_direct_thought_when_dramatic_plan_disallows_it(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉停在门口，伸手推开锁孔旁的铜片。米拉觉得门后有答案。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-dramatic-channels",
                "pov_character": "米拉",
                "inner_state_budget": {"max_direct_sentences": 2},
                "dramatic_behavior_plan": {
                    "allowed_channels": [
                        "action",
                        "dialogue",
                        "object",
                        "silence",
                        "choice",
                    ],
                    "avoid_direct_telling": ["米拉觉得门后有答案"],
                },
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "telling_over_action"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-dramatic-channels"
    assert finding.storytelling_refs["allowed_channels"] == [
        "action",
        "dialogue",
        "object",
        "silence",
        "choice",
    ]
    assert finding.storytelling_refs["matched_text"] == "米拉觉得门后有答案"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_missing_dramatic_choice_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉停在门口，伸手推开锁孔旁的铜片。空地图盒压在她掌心。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-dramatic-choice",
                "pov_character": "米拉",
                "dramatic_behavior_plan": {
                    "allowed_channels": ["action", "object", "choice"],
                    "render_as_choice": ["米拉拒绝等待，决定独自进档案室。"],
                },
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "choice_missing"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-dramatic-choice"
    assert finding.storytelling_refs["required_choice"] == ["米拉拒绝等待，决定独自进档案室。"]
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_exposition_without_scene_behavior(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text=("米拉说明自己不能失败。她解释空地图盒意味着背叛。因此局势更加危险。"),
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-exposition",
                "passage_mode": "scene",
                "show_not_tell_targets": [
                    "Mira's fear should appear through action and object detail."
                ],
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "exposition_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-exposition"
    assert finding.storytelling_refs["show_not_tell_targets"] == [
        "Mira's fear should appear through action and object detail."
    ]
    assert finding.storytelling_refs["exposition_sentence_count"] == 3
    assert finding.storytelling_refs["observable_behavior_signal_count"] == 0
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_dialogue_without_required_subtext(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="“因为空地图盒说明凯斯特有问题，所以我们必须立刻怀疑他。”米拉说道。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-subtext",
                "dramatic_behavior_plan": {
                    "allowed_channels": ["dialogue", "object", "action"],
                    "render_as_dialogue": ["Mira asks an oblique question."],
                    "subtext": ["Mira tests Kestrel without stating the accusation."],
                },
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "subtext_missing"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-subtext"
    assert finding.storytelling_refs["subtext_targets"] == [
        "Mira tests Kestrel without stating the accusation."
    ]
    assert finding.storytelling_refs["matched_dialogue"] == (
        "因为空地图盒说明凯斯特有问题，所以我们必须立刻怀疑他。"
    )
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_undramatized_plan_without_visible_behavior(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="雨声压住屋顶。档案室仍旧昏暗。灯图的传闻悬在门外。",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-dramatization",
                "dramatic_behavior_plan": {
                    "allowed_channels": ["action", "dialogue", "object", "silence"],
                    "render_as_action": [
                        "Mira touches the empty map case instead of explaining pressure."
                    ],
                    "render_as_object": ["The empty map case carries the pressure."],
                },
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "dramatization_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-dramatization"
    assert finding.storytelling_refs["dramatization_targets"] == [
        "Mira touches the empty map case instead of explaining pressure.",
        "The empty map case carries the pressure.",
    ]
    assert finding.storytelling_refs["observable_behavior_signal_count"] == 0
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_story_overreach_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text=(
            "十二个月后，岑予再也没有回到荒港。旧案的真相终于揭晓，"
            "整个王国改写了誓约，他决定余生守口如瓶。"
        ),
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-control-risk",
                "passage_mode": "scene",
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "control_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-control-risk"
    expected_categories = {
        "time_jump",
        "irreversible_outcome",
        "thread_resolution",
        "scope_expansion",
        "author_level_decision",
    }
    assert set(finding.storytelling_refs["matched_categories"]) >= expected_categories
    assert finding.storytelling_refs["scope_contract"] == {
        "mode": None,
        "passage_mode": "scene",
        "target_kind": None,
    }
    evidence_terms = finding.storytelling_refs["evidence_terms"]
    assert set(evidence_terms) >= expected_categories
    assert all(isinstance(evidence_terms[category], list) for category in expected_categories)
    assert all(evidence_terms[category] for category in expected_categories)
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_does_not_flag_local_next_beat_as_control_risk(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text=(
            "米拉必须进入档案室，但门后的脚步声阻止她。"
            "她伸手推开锁孔旁的铜片，低声问道：“谁在里面？”"
        ),
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-local-next-beat",
                "passage_mode": "scene",
                "target_position": {"kind": "selected_text"},
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    assert session.query(AgentReviewFindingRecord).count() == 0
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 0
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_flags_style_language_violation_without_formal_review(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="Mira opened the western archive door and explained why the map frightened her.",
    )
    session.add(
        AgentStorytellingControlRecord(
            id=uuid4(),
            project_id=candidate.project_id,
            action_request_id=candidate.action_request_id,
            draft_candidate_id=candidate.id,
            control_type="prose_rendering_contract",
            schema_version="prose-rendering-contract.v1",
            payload={
                "contract_id": "contract-style",
                "style_constraints": {"language": "zh"},
            },
        )
    )
    session.commit()
    job = _seed_review_job(session, candidate)

    processed = DbWorker(
        session,
        {"run_agent_review": AgentReviewHandler(object_store)},
    ).run_once(worker_id="worker-agent-review")

    assert processed is True
    assert session.get(JobRecord, job.id).status == "succeeded"
    refreshed = session.get(AgentDraftCandidateRecord, candidate.id)
    assert refreshed.status == "offered_to_author"
    finding = session.query(AgentReviewFindingRecord).one()
    assert finding.draft_candidate_id == candidate.id
    assert finding.risk_level == "medium"
    assert finding.risk_type == "style_risk"
    assert finding.storytelling_refs["source"] == "prose_contract_review"
    assert finding.storytelling_refs["contract_id"] == "contract-style"
    assert finding.storytelling_refs["expected_language"] == "zh"
    assert finding.draft_local_only is True
    assert finding.can_offer_to_author is True
    assert session.query(ReviewItemRecord).count() == 0
    assert session.query(SourceDeltaRecord).count() == 0
    audit = session.query(AuditEvent).filter_by(event_type="agent.review_completed").one()
    assert audit.decision["finding_count"] == 1
    assert audit.decision["candidate_status"] == "offered_to_author"


def test_agent_review_job_offers_safe_generated_candidate_idempotently(
    session: Session,
    object_store: LocalObjectStore,
) -> None:
    candidate = _seed_candidate(
        session,
        object_store,
        text="米拉把灯图收进斗篷内侧，继续询问钥匙的来处。",
    )
    first_job = _seed_review_job(session, candidate, suffix="one")
    second_job = _seed_review_job(session, candidate, suffix="two")

    worker = DbWorker(session, {"run_agent_review": AgentReviewHandler(object_store)})
    assert worker.run_once(worker_id="worker-agent-review") is True
    assert worker.run_once(worker_id="worker-agent-review") is True

    assert session.get(JobRecord, first_job.id).status == "succeeded"
    assert session.get(JobRecord, second_job.id).status == "succeeded"
    assert session.get(AgentDraftCandidateRecord, candidate.id).status == "offered_to_author"
    assert session.query(AgentReviewFindingRecord).count() == 0
    audits = session.query(AuditEvent).filter_by(event_type="agent.review_completed").all()
    assert [audit.decision["finding_count"] for audit in audits] == [0, 0]


def _seed_candidate(
    session: Session,
    object_store: LocalObjectStore,
    *,
    text: str,
) -> AgentDraftCandidateRecord:
    project = Project(id=uuid4(), name="Harbor Nine")
    raw_source = RawSource(
        id=uuid4(),
        project_id=project.id,
        source_type="draft_manuscript",
        source_scope="user_draft",
        title="Chapter 3",
        ownership_status="owned",
        raw_text_ref=object_store.put_text(f"raw/{project.id}.txt", "Mira paused."),
    )
    version = SourceVersion(
        id=uuid4(),
        source_id=raw_source.id,
        version_label="v1",
        raw_hash=f"hash-{project.id}",
        raw_text_ref=raw_source.raw_text_ref,
    )
    action_request = AgentActionRequestRecord(
        id=uuid4(),
        project_id=project.id,
        source_id=raw_source.id,
        source_version_id=version.id,
        actor_intent="续写当前段落。",
        trigger="toolbar",
        action_type="draft_next_passage",
        target={
            "kind": "selected_text",
            "source_id": str(raw_source.id),
            "source_version_id": str(version.id),
            "range": {"start": 0, "end": 12},
        },
        constraints={},
        expected_output="draft_candidate",
        status="succeeded",
        created_by=uuid4(),
    )
    candidate = AgentDraftCandidateRecord(
        id=uuid4(),
        project_id=project.id,
        action_request_id=action_request.id,
        mode="draft_next_passage",
        candidate_text_ref=object_store.put_text(f"drafts/{project.id}.txt", text),
        context_pack_id=None,
        selected_beat_id=None,
        target_source_id=raw_source.id,
        target_version_id=version.id,
        target_scene_id=None,
        affected_range={"start": 0, "end": 12},
        base_hash=version.raw_hash,
        memory_refs=[],
        evidence_refs=[],
        status="generated",
    )
    session.add_all([project, raw_source, version, action_request, candidate])
    session.commit()
    return candidate


def _seed_review_job(
    session: Session,
    candidate: AgentDraftCandidateRecord,
    *,
    suffix: str = "one",
) -> JobRecord:
    job = JobRecord(
        id=uuid4(),
        project_id=candidate.project_id,
        job_type="run_agent_review",
        status="queued",
        idempotency_key=f"run-agent-review:{candidate.id}:{suffix}",
        payload={
            "step": "run_agent_review",
            "pipeline_version": "pipeline-v1",
            "draft_candidate_id": str(candidate.id),
            "review_policy_version": "agent-review-rules-v1",
        },
    )
    session.add(job)
    session.commit()
    return job
