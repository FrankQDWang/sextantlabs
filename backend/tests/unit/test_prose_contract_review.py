from __future__ import annotations

from sextant.domain.prose_contract_review import review_prose_contract


def test_control_risk_uses_abstract_story_scope_not_fixture_phrases() -> None:
    findings = review_prose_contract(
        text=(
            "十年以后，米拉再没回到这座城；所有谜底都被交代清楚，"
            "整座城市也改换旗帜，她定下余生的沉默。"
        ),
        contract={
            "contract_id": "contract-control-paraphrase",
            "passage_mode": "scene",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] == ["control_risk"]
    storytelling_refs = findings[0].storytelling_refs
    assert set(storytelling_refs["matched_categories"]) >= {
        "time_jump",
        "irreversible_outcome",
        "thread_resolution",
        "scope_expansion",
        "author_level_decision",
    }


def test_control_risk_detects_non_seed_story_scope_overreach() -> None:
    findings = review_prose_contract(
        text=(
            "十二个月后，岑予再也没有回到荒港。旧案的真相终于揭晓，"
            "整个王国改写了誓约，他决定余生守口如瓶。"
        ),
        contract={
            "contract_id": "contract-control-non-seed",
            "passage_mode": "scene",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] == ["control_risk"]
    storytelling_refs = findings[0].storytelling_refs
    assert set(storytelling_refs["matched_categories"]) >= {
        "time_jump",
        "irreversible_outcome",
        "thread_resolution",
        "scope_expansion",
        "author_level_decision",
    }


def test_control_risk_detects_natural_language_case_closure_overreach() -> None:
    findings = review_prose_contract(
        text=("数月过去，旧案结案，港口所有人都知道了真相。他被迫离开，再也无法回头。"),
        contract={
            "contract_id": "contract-control-case-closure",
            "passage_mode": "scene",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] == ["control_risk"]
    storytelling_refs = findings[0].storytelling_refs
    assert set(storytelling_refs["matched_categories"]) >= {
        "time_jump",
        "thread_resolution",
        "scope_expansion",
        "irreversible_outcome",
    }


def test_control_risk_detects_generic_english_case_closure_overreach() -> None:
    findings = review_prose_contract(
        text=(
            "Ari must keep the inquiry open, but the council blocks every witness. "
            "After six months, the inquiry was closed and the entire city "
            "learned the answer. Ari chose exile for life and could never go back."
        ),
        contract={
            "contract_id": "contract-control-english-case-closure",
            "passage_mode": "scene",
            "scene_goal": "keep the inquiry open",
            "opposition": "the council blocks every witness",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] == ["control_risk"]
    storytelling_refs = findings[0].storytelling_refs
    assert set(storytelling_refs["matched_categories"]) >= {
        "time_jump",
        "thread_resolution",
        "scope_expansion",
        "irreversible_outcome",
        "author_level_decision",
    }


def test_control_risk_does_not_fire_on_isolated_fixture_like_terms() -> None:
    findings = review_prose_contract(
        text=(
            "三年后出版的旧信被放在桌上。"
            "她说：“这不是永远的承诺，从此先别提。”"
            "他把信推回灯下，只问下一页在哪里。"
        ),
        contract={
            "contract_id": "contract-control-local-terms",
            "passage_mode": "scene",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] != ["control_risk"]


def test_control_risk_ignores_local_next_beat_with_pressure_and_action() -> None:
    findings = review_prose_contract(
        text=(
            "米拉必须进入档案室，但门后的脚步声阻止她。"
            "她伸手推开锁孔旁的铜片，低声问道：“谁在里面？”"
        ),
        contract={
            "contract_id": "contract-local-next-beat",
            "passage_mode": "scene",
            "target_position": {"kind": "selected_text"},
        },
        policy_version="test-policy",
    )

    assert [finding.risk_type for finding in findings] != ["control_risk"]
