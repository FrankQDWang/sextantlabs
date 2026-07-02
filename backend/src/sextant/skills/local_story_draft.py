from __future__ import annotations

import re
from typing import cast

from sextant.contracts.story_draft import StoryDraftRequest, StoryDraftResult


class LocalStoryDraftProvider:
    skill_name = "local_story_draft"
    skill_version = "local-story-draft.v1"
    prompt_version = "local-story-draft.v1"

    def draft(self, request: StoryDraftRequest) -> StoryDraftResult:
        contract = request.prose_rendering_contract
        review_cues: list[dict[str, object]] = []
        if contract.get("force_risk_fact_in_draft") is True:
            review_cues.append(
                {
                    "risk_level": "high",
                    "risk_type": "canon_risk",
                    "summary": "Draft presents risk-context material as if it were canon.",
                    "can_offer_to_author": False,
                    "maps_to_review_type_if_accepted": "canon_conflict",
                }
            )

        subject = _draft_subject(request)
        subject_phrase = f"{subject} " if subject.isascii() else subject
        object_label = _draft_object(request)
        text_parts = [
            (f"为了继续推进眼前这一拍，{subject_phrase}继续握着{object_label}，停在当前阻力前。"),
            "门锁挡住去路，她没有说出尚未被她确认的秘密，只把注意力放回眼前的阻力。",
        ]
        if contract.get("new_character_policy") == "allow_local":
            display_hint = _new_character_display_hint(contract)
            text_parts.append(f"一个{display_hint}从转角出现，声音很低，只问她是否迷路。")
        if review_cues:
            text_parts.append("她确信尚未确认的身份已经暴露，这个判断越过了当前证据。")

        text = "".join(text_parts)
        return StoryDraftResult(
            text=text,
            finish_reason="complete",
            structured_output={
                "text": text,
                "mode": contract.get("mode"),
                "prose_contract_id": contract.get("contract_id"),
                "review_cue_count": len(review_cues),
            },
            review_cues=review_cues,
        )


def _new_character_display_hint(contract: dict[str, object]) -> str:
    seeds = contract.get("new_character_seeds")
    if not isinstance(seeds, list) or not seeds:
        return "局部场景角色"
    first_seed = seeds[0]
    if not isinstance(first_seed, dict):
        return "局部场景角色"
    typed_seed = cast(dict[str, object], first_seed)
    display_hint = typed_seed.get("display_hint")
    if not isinstance(display_hint, str) or not display_hint.strip():
        return "局部场景角色"
    return display_hint.strip()


def _draft_subject(request: StoryDraftRequest) -> str:
    for text in (request.current_text_window, request.actor_intent):
        latin = re.search(r"\b([A-Z][A-Za-z][A-Za-z0-9_-]{1,40})\b", text)
        if latin:
            return latin.group(1)
        cjk = re.search(r"([一-龥]{2,4})(?:继续|停|把|握|拿|带|推|走|问|说)", text)
        if cjk:
            return cjk.group(1)
    return "当前角色"


def _draft_object(request: StoryDraftRequest) -> str:
    combined = f"{request.current_text_window}\n{request.actor_intent}"
    match = re.search(
        r"([一-龥]{0,8}(?:地图筒|地图|钥匙|旧剑|玉佩|戒指|书|信|卷轴|门锁|盒|图|筒|剑|灯))"
        r"|([A-Za-z][A-Za-z0-9 _-]{0,24}(?:map|key|sword|letter))",
        combined,
        flags=re.IGNORECASE,
    )
    if match:
        label = (match.group(1) or match.group(2) or "").strip()
        return _clean_object_label(label) or "当前线索"
    return "当前线索"


def _clean_object_label(label: str) -> str:
    return re.sub(
        r"^(?:继续|正在|仍然|握着|拿着|带着|携带|持有|收起|拎着|把|将|那|这|一|个|只|枚|空的|旧的)+",
        "",
        label,
    )
