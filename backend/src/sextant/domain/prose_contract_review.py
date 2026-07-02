from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class ProseContractFinding:
    risk_level: str
    risk_type: str
    summary: str
    storytelling_refs: dict[str, object]
    suggested_revision: str
    can_offer_to_author: bool
    maps_to_review_type_if_accepted: str | None


DIRECTIVE_PREFIXES = (
    "不要直接写",
    "不要写",
    "不得写",
    "不能写",
    "禁止写",
    "do not write",
    "don't write",
    "no ",
)

TURN_SIGNAL_PHRASES = (
    "决定",
    "选择",
    "问道",
    "询问",
    "说出",
    "说道",
    "开口",
    "回答",
    "伸手",
    "推开",
    "拉开",
    "拿起",
    "拿走",
    "收进",
    "放回",
    "走向",
    "停在",
    "转身",
    "看见",
    "听见",
    "敲门",
    "打开",
    "关上",
    "出现",
    "挡住",
    "阻止",
    "递给",
    "藏起",
    "退后",
    "逼近",
    "离开",
    "进入",
    "意识到",
    "发现",
    "纠正",
    "拒绝",
    "承认",
    "decided",
    "chose",
    "asked",
    "said",
    "opened",
    "closed",
    "took",
    "moved",
    "stepped",
    "turned",
    "pushed",
    "pulled",
    "found",
    "refused",
    "noticed",
)

SEQUEL_DILEMMA_SIGNAL_PHRASES = (
    "是否",
    "要不要",
    "还是",
    "两难",
    "困境",
    "选择",
    "代价",
    "whether",
    "or",
    "dilemma",
    "choice",
    "cost",
)

SEQUEL_DECISION_SIGNAL_PHRASES = (
    "决定",
    "选择",
    "下定决心",
    "转而",
    "于是",
    "下一步",
    "要去",
    "要做",
    "decided",
    "decides",
    "choose",
    "chooses",
    "chose",
    "next step",
)

SCENE_GOAL_SIGNAL_PHRASES = (
    "目标",
    "想要",
    "要去",
    "要做",
    "必须",
    "试图",
    "打算",
    "需要",
    "为了",
    "goal",
    "wants",
    "wanted",
    "must",
    "needs",
    "tries",
    "try to",
    "intends",
    "in order to",
)

SCENE_OPPOSITION_SIGNAL_PHRASES = (
    "阻止",
    "挡住",
    "拦住",
    "阻力",
    "反对",
    "拒绝",
    "威胁",
    "逼近",
    "追上",
    "拦下",
    "不能",
    "不让",
    "但是",
    "却",
    "opposition",
    "blocks",
    "blocked",
    "refuses",
    "threatens",
    "resists",
    "but",
    "cannot",
)

MIXED_ACTION_SIGNAL_PHRASES = (
    "伸手",
    "推开",
    "拉开",
    "拿起",
    "走向",
    "转身",
    "打开",
    "关上",
    "停在",
    "试探",
    "递给",
    "退后",
    "stepped",
    "turned",
    "pushed",
    "pulled",
    "opened",
    "moved",
)

MIXED_REACTION_SIGNAL_PHRASES = (
    "反应",
    "停了一下",
    "停住",
    "沉默",
    "吸气",
    "低声",
    "皱眉",
    "迟疑",
    "意识到",
    "害怕",
    "担心",
    "压住",
    "reaction",
    "reacts",
    "hesitates",
    "pauses",
    "breathes",
    "registers",
    "realizes",
)

NEW_CHARACTER_DISALLOW_POLICIES = {
    "avoid",
    "no_new_character",
    "no_new",
    "none",
    "disallow",
    "deny",
}

NEW_CHARACTER_MARKERS = (
    "一个陌生人",
    "一名陌生人",
    "陌生人",
    "新角色",
    "新来的人",
    "stranger",
    "new character",
    "unknown man",
    "unknown woman",
)
CHINESE_NEW_CHARACTER_INTRO_PATTERN = re.compile(
    r"(?P<match>"
    r"(?:一个|一名|一位|某个|这名|那名|新来的)"
    r"[\u4e00-\u9fff·]{1,12}"
    r"(?:员|者|师|官|客|手|卫|兵|徒|人|童|夫|娘|士|仆|侍|警|探|工)"
    r")"
    r"(?=(?:从|在|向|对|把|将|被|走|出现|挡住|开口|低声|问|说|递|推|拉|站|停|看|听|进入|离开))"
)

CHINESE_MIND_READING_PATTERN = re.compile(
    r"(?P<name>[\u4e00-\u9fffA-Za-z·]{2,16})(?:心想|心里想|内心|暗想|觉得|知道|害怕)"
)
ENGLISH_MIND_READING_PATTERN = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z][A-Za-z'\-]{0,30})\s+"
    r"(?:thought|felt|knew|feared|wondered|believed)\b"
)

DIRECT_INTERIORITY_CUES = (
    "心想",
    "心里想",
    "内心",
    "暗想",
    "觉得",
    "知道",
    "害怕",
    "担心",
    "恐惧",
    "thought",
    "felt",
    "knew",
    "feared",
    "wondered",
    "believed",
)

DIRECT_INTERIORITY_CHANNELS = (
    "thought",
    "direct_thought",
    "direct_interiority",
    "brief_direct_interiority",
)

DEFAULT_INNER_STATE_OVERLOAD_THRESHOLD = 3

CHOICE_SIGNAL_PHRASES = (
    "决定",
    "选择",
    "拒绝",
    "承担",
    "隐瞒",
    "交出",
    "留下",
    "离开",
    "独自",
    "转而",
    "下一步",
    "要去",
    "要做",
    "decided",
    "decides",
    "choose",
    "chooses",
    "chose",
    "refused",
    "refuses",
    "accepts",
    "commits",
    "next step",
)

EXPOSITION_SIGNAL_PHRASES = (
    "说明",
    "解释",
    "意味着",
    "因为",
    "因此",
    "所以",
    "这让",
    "这说明",
    "原因",
    "represent",
    "represents",
    "mean",
    "means",
    "meant",
    "explained",
    "explains",
    "because",
    "therefore",
)

OBSERVABLE_BEHAVIOR_SIGNAL_PHRASES = MIXED_ACTION_SIGNAL_PHRASES + (
    "说道",
    "问道",
    "回答",
    "低声",
    "开口",
    "沉默",
    "停顿",
    "停住",
    "避开",
    "握紧",
    "抓住",
    "看见",
    "听见",
    "手心汗",
    "空气发冷",
    "said",
    "asked",
    "answered",
    "whispered",
    "paused",
    "silent",
    "gripped",
    "held",
    "saw",
    "heard",
)

DIALOGUE_EXPLANATION_SIGNAL_PHRASES = EXPOSITION_SIGNAL_PHRASES + (
    "显然",
    "证明",
    "必须",
    "立刻",
    "obviously",
    "proves",
    "must",
)

SUBTEXT_INDIRECTION_SIGNAL_PHRASES = (
    "试探",
    "故意",
    "反问",
    "停顿",
    "沉默",
    "避开",
    "不回答",
    "只说",
    "转移话题",
    "换了个说法",
    "？",
    "?",
    "tests",
    "oblique",
    "deflect",
    "deflects",
    "pauses",
    "silent",
    "does not answer",
    "doesn't answer",
)

CONTROL_OVERREACH_CATEGORY_PATTERNS = {
    "time_jump": (
        re.compile(
            r"(?:[一二三四五六七八九十百千万两几数半0-9]+年|"
            r"[一二三四五六七八九十百千万两几数半0-9]+个?月|"
            r"[一二三四五六七八九十百千万两几数半0-9]+周|"
            r"数年|数月|数周|多年|几个月|几周)(?:后|以后|之后)"
            r"(?=[，,。；;\s]|$)"
        ),
        re.compile(
            r"(?:[一二三四五六七八九十百千万两几数半0-9]+年|"
            r"[一二三四五六七八九十百千万两几数半0-9]+个?月|"
            r"[一二三四五六七八九十百千万两几数半0-9]+周|"
            r"数年|数月|数周|多年|几个月|几周)(?:过去|过去了|流逝)"
            r"(?=[，,。；;\s]|$)"
        ),
        re.compile(r"\b(?:years?|months?|weeks?)\s+(?:later|afterward)\b", re.I),
        re.compile(
            r"\bafter\s+(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"several|many|few|\d+)\s+(?:years?|months?|weeks?)\b",
            re.I,
        ),
    ),
    "irreversible_outcome": (
        re.compile(r"再(?:也)?(?:没|没有|不)(?:回|返回|回到|回头)"),
        re.compile(r"(?:再也)?(?:无法|不能)(?:回头|回去|返回|回到)"),
        re.compile(r"(?:无法挽回|不可挽回|一去不返|余生|终身)"),
        re.compile(
            r"\b(?:irreversible|never again|never returned|for the rest of)\b",
            re.I,
        ),
        re.compile(r"\bcould\s+never\s+(?:go|come|turn|get)\s+back\b", re.I),
    ),
    "thread_resolution": (
        re.compile(
            r"(?:所有|全部|一切)?(?:谜底|谜题|真相|悬案).{0,8}"
            r"(?:交代|解开|揭开|揭晓|落定)"
        ),
        re.compile(r"(?:案子|案件|旧案|调查|审判|线索).{0,8}(?:结案|结束|尘埃落定|有了定论)"),
        re.compile(r"(?:真凶|身份|秘密).{0,8}(?:揭开|公开|揭晓)"),
        re.compile(r"\b(?:all questions were answered|mystery was solved|truth came out)\b", re.I),
        re.compile(
            r"\b(?:case|inquiry|investigation|trial|matter)\s+"
            r"(?:was\s+)?(?:closed|ended|resolved|settled)\b",
            re.I,
        ),
    ),
    "scope_expansion": (
        re.compile(r"(?:全城|整座城市|整个城市|整个王国|整个世界|所有人|天下)"),
        re.compile(r"(?:街巷|城邦|王国|世界).{0,12}(?:改变|改写|动摇|知晓)"),
        re.compile(r"\b(?:(?:whole|entire) (?:city|kingdom|world|village)|everyone)\b", re.I),
    ),
    "author_level_decision": (
        re.compile(r"(?:余生|终身|命运|结局)"),
        re.compile(r"(?:定下|决定|选定).{0,12}(?:余生|命运|结局|道路|沉默|去留)"),
        re.compile(
            r"\b(?:destiny|final fate|for the rest of her life|for the rest of his life)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:chose|chooses|decided)\s+(?:exile|silence|departure)\s+for\s+life\b", re.I
        ),
    ),
}


def review_prose_contract(
    *,
    text: str,
    contract: dict[str, object] | None,
    policy_version: str,
    structured_output: dict[str, object] | None = None,
    candidate_range: dict[str, int] | None = None,
) -> list[ProseContractFinding]:
    if contract is None or not text.strip():
        return []

    forbidden_match = _forbidden_knowledge_match(text, contract)
    if forbidden_match is not None:
        return [
            ProseContractFinding(
                risk_level="high",
                risk_type="forbidden_knowledge_leak",
                summary="Draft leaks knowledge the ProseRenderingContract marks as forbidden.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "forbidden_knowledge": forbidden_match,
                },
                suggested_revision=(
                    "Remove the forbidden knowledge or keep it outside the current POV."
                ),
                can_offer_to_author=False,
                maps_to_review_type_if_accepted="knowledge_conflict",
            )
        ]

    target_range_match = _target_range_match(contract, structured_output, candidate_range)
    if target_range_match is not None:
        contract_range, attempted_range = target_range_match
        return [
            ProseContractFinding(
                risk_level="high",
                risk_type="target_range_risk",
                summary="Draft attempts to modify text outside the ProseRenderingContract range.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "contract_range": contract_range,
                    "attempted_range": attempted_range,
                },
                suggested_revision="Regenerate or revise the candidate inside the selected range.",
                can_offer_to_author=False,
                maps_to_review_type_if_accepted="version_conflict",
            )
        ]

    mind_reading_match = _non_pov_mind_reading_match(text, contract)
    if mind_reading_match is not None:
        return [
            ProseContractFinding(
                risk_level="high",
                risk_type="non_pov_mind_reading",
                summary="Draft directly states non-POV character interiority.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "pov_character": mind_reading_match["pov_character"],
                    "matched_character": mind_reading_match["matched_character"],
                    "matched_text": mind_reading_match["matched_text"],
                },
                suggested_revision=(
                    "Rewrite the non-POV interiority as observable action, dialogue, or silence."
                ),
                can_offer_to_author=False,
                maps_to_review_type_if_accepted="pov_conflict",
            )
        ]

    inner_state_budget_match = _inner_state_budget_match(text, contract)
    if inner_state_budget_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="inner_state_budget_violation",
                summary="Draft exceeds the direct inner-state budget in the contract.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "direct_inner_state_count": inner_state_budget_match[
                        "direct_inner_state_count"
                    ],
                    "max_direct_sentences": inner_state_budget_match["max_direct_sentences"],
                },
                suggested_revision=(
                    "Convert excess inner-state explanation into action, dialogue, or choice."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    inner_state_overload_match = _inner_state_overload_match(text, contract)
    if inner_state_overload_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="inner_state_overload",
                summary="Draft packs too many direct inner-state statements into one paragraph.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "direct_inner_state_count": inner_state_overload_match[
                        "direct_inner_state_count"
                    ],
                    "overload_threshold": inner_state_overload_match["overload_threshold"],
                    "paragraph_index": inner_state_overload_match["paragraph_index"],
                },
                suggested_revision=(
                    "Convert the repeated inner-state statements into action, silence, "
                    "object pressure, dialogue, or a concrete choice."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    dramatic_behavior_match = _dramatic_behavior_match(text, contract)
    if dramatic_behavior_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="telling_over_action",
                summary="Draft directly tells inner state that the dramatic plan disallows.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "allowed_channels": dramatic_behavior_match["allowed_channels"],
                    "matched_text": dramatic_behavior_match["matched_text"],
                    "avoid_direct_telling": dramatic_behavior_match["avoid_direct_telling"],
                },
                suggested_revision=(
                    "Render the inner state through action, dialogue, object, silence, or choice."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    dramatic_choice_match = _dramatic_choice_match(text, contract)
    if dramatic_choice_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="choice_missing",
                summary="Draft does not show the choice required by the dramatic plan.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "required_choice": dramatic_choice_match["required_choice"],
                },
                suggested_revision=("Make the character's choice visible in action or dialogue."),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    style_language_match = _style_language_match(text, contract)
    if style_language_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="style_risk",
                summary="Draft language does not match the ProseRenderingContract style.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "expected_language": style_language_match["expected_language"],
                    "latin_letter_count": style_language_match["latin_letter_count"],
                    "cjk_character_count": style_language_match["cjk_character_count"],
                },
                suggested_revision="Rewrite the draft in the contract language and tone.",
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    hard_no_match = _hard_no_match(text, contract)
    if hard_no_match is not None:
        rule, matched_text = hard_no_match
        return [
            ProseContractFinding(
                risk_level="high",
                risk_type="prose_contract_violation",
                summary="Draft violates a hard_no rule in the ProseRenderingContract.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "hard_no": rule,
                    "matched_text": matched_text,
                },
                suggested_revision="Rewrite the passage so the prohibited claim or form is absent.",
                can_offer_to_author=False,
                maps_to_review_type_if_accepted=None,
            )
        ]

    cast_policy_match = _cast_policy_match(text, contract)
    if cast_policy_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="cast_policy_violation",
                summary="Draft appears to introduce a new character outside the contract policy.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "new_character_policy": _optional_text(contract.get("new_character_policy")),
                    "matched_text": cast_policy_match,
                },
                suggested_revision=(
                    "Reuse the allowed cast or ask the author before introducing a new role."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    exposition_match = _exposition_match(text, contract)
    if exposition_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="exposition_risk",
                summary="Draft explains inner state without enough scene behavior.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "show_not_tell_targets": exposition_match["show_not_tell_targets"],
                    "exposition_sentence_count": exposition_match["exposition_sentence_count"],
                    "observable_behavior_signal_count": exposition_match[
                        "observable_behavior_signal_count"
                    ],
                },
                suggested_revision=(
                    "Convert the explanation into observable action, dialogue, silence, "
                    "object detail, or sensory detail."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    subtext_match = _subtext_match(text, contract)
    if subtext_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="subtext_missing",
                summary="Draft dialogue states information directly instead of carrying subtext.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "subtext_targets": subtext_match["subtext_targets"],
                    "matched_dialogue": subtext_match["matched_dialogue"],
                },
                suggested_revision=(
                    "Rewrite the line as an oblique question, deflection, pause, "
                    "or pressure-bearing exchange."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    dramatization_match = _dramatization_match(text, contract)
    if dramatization_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="dramatization_risk",
                summary="Draft does not render the dramatic plan as visible behavior.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "dramatization_targets": dramatization_match["dramatization_targets"],
                    "observable_behavior_signal_count": dramatization_match[
                        "observable_behavior_signal_count"
                    ],
                },
                suggested_revision=(
                    "Add visible action, dialogue, object pressure, silence, or a concrete choice."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    control_match = _control_overreach_match(text, contract)
    if control_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="control_risk",
                summary="Draft advances too far and decides major story direction for the author.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "matched_categories": control_match["matched_categories"],
                    "evidence_terms": control_match["evidence_terms"],
                    "scope_contract": control_match["scope_contract"],
                },
                suggested_revision=(
                    "Keep the candidate to the next local beat and leave large outcomes "
                    "or time jumps for explicit author direction."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    sequel_mode_match = _sequel_mode_structure_match(text, contract)
    if sequel_mode_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="sequel_mode_risk",
                summary="Sequel-mode draft lacks a detectable dilemma or decision.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "passage_mode": "sequel",
                    "missing_elements": sequel_mode_match,
                    "expected_dilemma": _optional_text(contract.get("dilemma")),
                    "expected_decision": _optional_text(contract.get("decision")),
                },
                suggested_revision=(
                    "Make the reaction turn into a dilemma and visible decision before ending."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    if _requires_turn(contract) and not _has_turn_signal(text):
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="no_turn_risk",
                summary="Draft does not show a detectable turn, choice, action, or hook.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "required_turn": _optional_text(contract.get("required_turn")),
                    "ending_shape": _optional_text(contract.get("ending_shape")),
                },
                suggested_revision=(
                    "Add a visible action, choice, obstacle, or hook that changes the page state."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    mixed_mode_match = _mixed_mode_structure_match(text, contract)
    if mixed_mode_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="mode_mixing_risk",
                summary="Mixed-mode draft lacks a detectable action, reaction, or decision.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "passage_mode": "mixed",
                    "missing_elements": mixed_mode_match,
                    "expected_scene_goal": _optional_text(contract.get("scene_goal")),
                    "expected_reaction": _optional_text(contract.get("reaction")),
                    "expected_decision": _optional_text(contract.get("decision")),
                },
                suggested_revision=(
                    "Keep the mixed passage to a small action, short reaction, and small choice."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]

    scene_mode_match = _scene_mode_structure_match(text, contract)
    if scene_mode_match is not None:
        return [
            ProseContractFinding(
                risk_level="medium",
                risk_type="scene_mode_risk",
                summary="Scene-mode draft lacks a detectable goal or opposition.",
                storytelling_refs={
                    "source": "prose_contract_review",
                    "review_policy_version": policy_version,
                    "contract_id": _contract_id(contract),
                    "passage_mode": "scene",
                    "missing_elements": scene_mode_match,
                    "expected_scene_goal": _optional_text(contract.get("scene_goal")),
                    "expected_opposition": _optional_text(contract.get("opposition")),
                },
                suggested_revision=(
                    "Make the scene goal and opposing force visible before ending."
                ),
                can_offer_to_author=True,
                maps_to_review_type_if_accepted=None,
            )
        ]
    return []


def _contract_id(contract: dict[str, object]) -> str | None:
    value = contract.get("contract_id")
    return str(value) if value is not None else None


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _forbidden_knowledge_match(text: str, contract: dict[str, object]) -> object | None:
    value = contract.get("forbidden_knowledge", [])
    if not isinstance(value, list):
        return None
    for item in value:
        for phrase in _forbidden_phrases(item):
            if _contains_phrase(text, phrase):
                return item
    return None


def _forbidden_phrases(item: object) -> list[str]:
    if isinstance(item, str):
        return [item]
    if not isinstance(item, dict):
        return []
    typed_item = cast(dict[str, object], item)
    phrases: list[str] = []
    for key in ("text", "summary", "label", "name", "title"):
        value = typed_item.get(key)
        if isinstance(value, str):
            phrases.append(value)
    for ref_key in ("subject_ref", "object_ref"):
        ref = typed_item.get(ref_key)
        if isinstance(ref, dict):
            phrases.extend(_ref_phrases(cast(dict[Any, Any], ref)))
    return phrases


def _ref_phrases(ref: dict[Any, Any]) -> list[str]:
    phrases: list[str] = []
    for key in ("text", "display_name", "name", "title", "label", "id"):
        value = ref.get(key)
        if isinstance(value, str):
            phrases.append(value.replace("_", " "))
    return phrases


def _hard_no_match(text: str, contract: dict[str, object]) -> tuple[str, str] | None:
    value = contract.get("hard_no", [])
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, str):
            continue
        for phrase in _hard_no_phrases(item):
            if _contains_phrase(text, phrase):
                return item, phrase
    return None


def _target_range_match(
    contract: dict[str, object],
    structured_output: dict[str, object] | None,
    candidate_range: dict[str, int] | None,
) -> tuple[dict[str, int], dict[str, int]] | None:
    contract_range = _contract_range(contract)
    if contract_range is None:
        return None
    attempted_range = _attempted_range(structured_output, candidate_range)
    if attempted_range is None:
        return None
    if (
        attempted_range["start"] < contract_range["start"]
        or attempted_range["end"] > contract_range["end"]
    ):
        return contract_range, attempted_range
    return None


def _non_pov_mind_reading_match(text: str, contract: dict[str, object]) -> dict[str, str] | None:
    pov_character = _pov_character_name(contract)
    if pov_character is None:
        return None
    for pattern in (CHINESE_MIND_READING_PATTERN, ENGLISH_MIND_READING_PATTERN):
        for match in pattern.finditer(text):
            matched_character = match.group("name")
            if not _same_character_name(matched_character, pov_character):
                return {
                    "pov_character": pov_character,
                    "matched_character": matched_character,
                    "matched_text": match.group(0),
                }
    return None


def _inner_state_budget_match(text: str, contract: dict[str, object]) -> dict[str, int] | None:
    max_direct_sentences = _max_direct_inner_state_sentences(contract)
    if max_direct_sentences is None:
        return None
    direct_count = sum(1 for sentence in _sentences(text) if _contains_direct_interiority(sentence))
    if direct_count > max_direct_sentences:
        return {
            "direct_inner_state_count": direct_count,
            "max_direct_sentences": max_direct_sentences,
        }
    return None


def _inner_state_overload_match(text: str, contract: dict[str, object]) -> dict[str, int] | None:
    threshold = _inner_state_overload_threshold(contract)
    for index, paragraph in enumerate(_paragraphs(text), start=1):
        direct_count = sum(
            1 for sentence in _sentences(paragraph) if _contains_direct_interiority(sentence)
        )
        if direct_count >= threshold:
            return {
                "direct_inner_state_count": direct_count,
                "overload_threshold": threshold,
                "paragraph_index": index,
            }
    return None


def _dramatic_behavior_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    plan = contract.get("dramatic_behavior_plan")
    if not isinstance(plan, dict):
        return None
    typed_plan = cast(dict[str, object], plan)
    allowed_channels = _allowed_channels(typed_plan)
    if not allowed_channels or _direct_interiority_allowed(allowed_channels):
        return None
    matched_text = _first_direct_interiority_sentence(text)
    if matched_text is None:
        return None
    return {
        "allowed_channels": allowed_channels,
        "matched_text": matched_text,
        "avoid_direct_telling": _avoid_direct_telling_rules(typed_plan),
    }


def _dramatic_choice_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    plan = contract.get("dramatic_behavior_plan")
    if not isinstance(plan, dict):
        return None
    required_choice = _required_choice(cast(dict[str, object], plan))
    if not required_choice or _has_any_signal(text, CHOICE_SIGNAL_PHRASES):
        return None
    return {"required_choice": required_choice}


def _exposition_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    show_not_tell_targets = _show_not_tell_targets(contract)
    if not show_not_tell_targets:
        return None

    exposition_sentence_count = sum(
        1 for sentence in _sentences(text) if _has_any_signal(sentence, EXPOSITION_SIGNAL_PHRASES)
    )
    observable_behavior_signal_count = _signal_count(
        text,
        OBSERVABLE_BEHAVIOR_SIGNAL_PHRASES,
    )
    if exposition_sentence_count < 2 or observable_behavior_signal_count > 0:
        return None
    return {
        "show_not_tell_targets": show_not_tell_targets,
        "exposition_sentence_count": exposition_sentence_count,
        "observable_behavior_signal_count": observable_behavior_signal_count,
    }


def _subtext_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    subtext_targets = _subtext_targets(contract)
    if not subtext_targets:
        return None

    for dialogue in _dialogue_fragments(text):
        if _has_any_signal(dialogue, DIALOGUE_EXPLANATION_SIGNAL_PHRASES) and not _has_any_signal(
            dialogue,
            SUBTEXT_INDIRECTION_SIGNAL_PHRASES,
        ):
            return {
                "subtext_targets": subtext_targets,
                "matched_dialogue": dialogue,
            }
    return None


def _dramatization_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    dramatization_targets = _dramatization_targets(contract)
    if not dramatization_targets:
        return None

    observable_behavior_signal_count = _signal_count(
        text,
        OBSERVABLE_BEHAVIOR_SIGNAL_PHRASES + CHOICE_SIGNAL_PHRASES,
    )
    if observable_behavior_signal_count > 0 or _dialogue_fragments(text):
        return None
    return {
        "dramatization_targets": dramatization_targets,
        "observable_behavior_signal_count": observable_behavior_signal_count,
    }


def _control_overreach_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    scope_contract = _control_scope_contract(contract)
    if not _is_local_scope_contract(scope_contract):
        return None

    evidence_terms = _control_overreach_evidence_terms(text)

    matched_categories = list(evidence_terms.keys())
    if len(matched_categories) < 2:
        return None
    return {
        "matched_categories": matched_categories,
        "evidence_terms": evidence_terms,
        "scope_contract": scope_contract,
    }


def _control_overreach_evidence_terms(text: str) -> dict[str, list[str]]:
    evidence_terms: dict[str, list[str]] = {}
    for category, patterns in CONTROL_OVERREACH_CATEGORY_PATTERNS.items():
        matches: list[str] = []
        for pattern in patterns:
            matches.extend(match.group(0) for match in pattern.finditer(text))
        deduped_matches = list(dict.fromkeys(match for match in matches if match.strip()))
        if deduped_matches:
            evidence_terms[category] = deduped_matches
    return evidence_terms


def _control_scope_contract(contract: dict[str, object]) -> dict[str, str | None]:
    target_position = contract.get("target_position")
    target_kind = None
    if isinstance(target_position, dict):
        raw_target_kind = cast(dict[str, object], target_position).get("kind")
        if isinstance(raw_target_kind, str) and raw_target_kind.strip():
            target_kind = raw_target_kind.strip()

    mode = contract.get("mode")
    passage_mode = contract.get("passage_mode")
    return {
        "mode": mode.strip() if isinstance(mode, str) and mode.strip() else None,
        "passage_mode": (
            passage_mode.strip() if isinstance(passage_mode, str) and passage_mode.strip() else None
        ),
        "target_kind": target_kind,
    }


def _is_local_scope_contract(scope_contract: dict[str, str | None]) -> bool:
    return (
        scope_contract["passage_mode"] in {"scene", "mixed", "sequel"}
        or scope_contract["target_kind"] in {"selected_text", "range"}
        or scope_contract["mode"] in {"draft_next_passage", "revise_candidate", "rewrite_selection"}
    )


def _style_language_match(text: str, contract: dict[str, object]) -> dict[str, object] | None:
    expected_language = _expected_language(contract)
    if expected_language not in {"zh", "zh-cn", "chinese"}:
        return None
    latin_letter_count = len(re.findall(r"[A-Za-z]", text))
    cjk_character_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    if latin_letter_count >= 24 and latin_letter_count > max(cjk_character_count * 2, 12):
        return {
            "expected_language": expected_language,
            "latin_letter_count": latin_letter_count,
            "cjk_character_count": cjk_character_count,
        }
    return None


def _expected_language(contract: dict[str, object]) -> str | None:
    style_constraints = contract.get("style_constraints")
    if not isinstance(style_constraints, dict):
        return None
    value = cast(dict[str, object], style_constraints).get("language")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold()


def _max_direct_inner_state_sentences(contract: dict[str, object]) -> int | None:
    budget = contract.get("inner_state_budget")
    if not isinstance(budget, dict):
        return None
    typed_budget = cast(dict[str, object], budget)
    value = typed_budget.get("max_direct_sentences")
    if isinstance(value, int) and value >= 0:
        return value
    value = typed_budget.get("max_direct_inner_sentences")
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _inner_state_overload_threshold(contract: dict[str, object]) -> int:
    for key in ("inner_state_overload_threshold", "max_direct_sentences_per_paragraph"):
        value = contract.get(key)
        if isinstance(value, int) and value > 0:
            return value

    budget = contract.get("inner_state_budget")
    if isinstance(budget, dict):
        typed_budget = cast(dict[str, object], budget)
        for key in ("overload_threshold", "max_direct_sentences_per_paragraph"):
            value = typed_budget.get(key)
            if isinstance(value, int) and value > 0:
                return value

    return DEFAULT_INNER_STATE_OVERLOAD_THRESHOLD


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？.!?]+", text) if part.strip()]


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?:\r?\n){2,}", text) if part.strip()]


def _contains_direct_interiority(sentence: str) -> bool:
    normalized_sentence = _normalized(sentence)
    return any(_normalized(cue) in normalized_sentence for cue in DIRECT_INTERIORITY_CUES)


def _first_direct_interiority_sentence(text: str) -> str | None:
    for sentence in _sentences(text):
        if _contains_direct_interiority(sentence):
            return sentence
    return None


def _allowed_channels(plan: dict[str, object]) -> list[str]:
    value = plan.get("allowed_channels")
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _direct_interiority_allowed(allowed_channels: list[str]) -> bool:
    normalized_channels = {_normalized(channel) for channel in allowed_channels}
    return any(
        _normalized(channel) in normalized_channels for channel in DIRECT_INTERIORITY_CHANNELS
    )


def _required_choice(plan: dict[str, object]) -> list[str]:
    for key in ("render_as_choice", "required_choice", "visible_choice"):
        value = plan.get(key)
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _show_not_tell_targets(contract: dict[str, object]) -> list[str]:
    targets: list[str] = []
    for key in ("show_not_tell_targets", "dramatize_targets", "dramatization_targets"):
        targets.extend(_text_list(contract.get(key)))

    plan = contract.get("dramatic_behavior_plan")
    if isinstance(plan, dict):
        typed_plan = cast(dict[str, object], plan)
        for key in (
            "render_as_action",
            "render_as_dialogue",
            "render_as_silence",
            "render_as_object",
            "render_as_sensory",
            "visible_behavior",
            "sensory_focus",
        ):
            targets.extend(_text_list(typed_plan.get(key)))

    return targets


def _subtext_targets(contract: dict[str, object]) -> list[str]:
    targets: list[str] = []
    for key in ("subtext_targets", "subtext", "expected_subtext"):
        targets.extend(_text_list(contract.get(key)))

    plan = contract.get("dramatic_behavior_plan")
    if isinstance(plan, dict):
        typed_plan = cast(dict[str, object], plan)
        for key in ("subtext", "subtext_targets", "expected_subtext"):
            targets.extend(_text_list(typed_plan.get(key)))

    return targets


def _dramatization_targets(contract: dict[str, object]) -> list[str]:
    targets: list[str] = []
    for key in ("dramatization_targets", "dramatize_targets"):
        targets.extend(_text_list(contract.get(key)))

    plan = contract.get("dramatic_behavior_plan")
    if isinstance(plan, dict):
        typed_plan = cast(dict[str, object], plan)
        for key in (
            "render_as_action",
            "render_as_dialogue",
            "render_as_silence",
            "render_as_object",
            "render_as_sensory",
            "render_as_choice",
            "visible_behavior",
            "turn",
            "required_turn",
        ):
            targets.extend(_text_list(typed_plan.get(key)))

    return targets


def _dialogue_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    for pattern in (
        r"“([^”]+)”",
        r"「([^」]+)」",
        r"『([^』]+)』",
        r'"([^"]+)"',
    ):
        fragments.extend(match.strip() for match in re.findall(pattern, text) if match.strip())
    return fragments


def _text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _avoid_direct_telling_rules(plan: dict[str, object]) -> list[str]:
    for key in ("avoid_direct_telling", "avoid_phrases"):
        value = plan.get(key)
        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _pov_character_name(contract: dict[str, object]) -> str | None:
    value = contract.get("pov_character")
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "display_name", "label", "id"):
            ref_value = cast(dict[str, object], value).get(key)
            if isinstance(ref_value, str) and ref_value.strip():
                return ref_value.strip()
    return None


def _same_character_name(left: str, right: str) -> bool:
    return _normalized(left) == _normalized(right)


def _contract_range(contract: dict[str, object]) -> dict[str, int] | None:
    target_position = contract.get("target_position")
    if isinstance(target_position, dict):
        target_range = cast(dict[str, object], target_position).get("range")
        range_value = _range_from_object(target_range)
        if range_value is not None:
            return range_value
    return _range_from_object(contract.get("affected_range"))


def _attempted_range(
    structured_output: dict[str, object] | None,
    candidate_range: dict[str, int] | None,
) -> dict[str, int] | None:
    if structured_output is not None:
        for key in ("affected_range", "target_range", "range"):
            range_value = _range_from_object(structured_output.get(key))
            if range_value is not None:
                return range_value
    return _range_from_object(candidate_range)


def _range_from_object(value: object) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    typed_value = cast(dict[str, object], value)
    start = typed_value.get("start")
    end = typed_value.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        return None
    return {"start": start, "end": end}


def _cast_policy_match(text: str, contract: dict[str, object]) -> str | None:
    policy = contract.get("new_character_policy")
    if not isinstance(policy, str):
        return None
    if policy.casefold() not in NEW_CHARACTER_DISALLOW_POLICIES:
        return None
    allowed_cast_phrases = set(_allowed_cast_phrases(contract))
    for marker in NEW_CHARACTER_MARKERS:
        if _contains_phrase(text, marker) and not _is_allowed_cast_match(
            marker,
            allowed_cast_phrases,
        ):
            return marker
    intro_match = _generic_new_character_intro_match(text)
    if intro_match is not None and not _is_allowed_cast_match(
        intro_match,
        allowed_cast_phrases,
    ):
        return intro_match
    return None


def _generic_new_character_intro_match(text: str) -> str | None:
    match = CHINESE_NEW_CHARACTER_INTRO_PATTERN.search(text)
    if match is None:
        return None
    return match.group("match")


def _is_allowed_cast_match(matched_text: str, allowed_cast_phrases: set[str]) -> bool:
    normalized_match = _normalized(matched_text)
    return any(
        allowed == normalized_match or (len(allowed) >= 4 and allowed in normalized_match)
        for allowed in allowed_cast_phrases
    )


def _allowed_cast_phrases(contract: dict[str, object]) -> list[str]:
    allowed_cast = contract.get("allowed_cast", [])
    if not isinstance(allowed_cast, list):
        return []
    phrases: list[str] = []
    for item in allowed_cast:
        if isinstance(item, str):
            phrases.append(_normalized(item))
        elif isinstance(item, dict):
            phrases.extend(_normalized(phrase) for phrase in _ref_phrases(item))
    return phrases


def _hard_no_phrases(rule: str) -> list[str]:
    phrases = [match.strip() for match in re.findall(r"[\"'“‘](.+?)[\"'”’]", rule)]
    stripped = rule.strip()
    lowered = stripped.casefold()
    for prefix in DIRECTIVE_PREFIXES:
        if lowered.startswith(prefix.casefold()):
            stripped = stripped[len(prefix) :].strip(" :：，,。.;；")
            break
    phrases.append(stripped)
    return [phrase for phrase in phrases if len(_normalized(phrase)) >= 4]


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_phrase = _normalized(phrase)
    if len(normalized_phrase) < 4:
        return False
    return normalized_phrase in _normalized(text)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _requires_turn(contract: dict[str, object]) -> bool:
    required_turn = contract.get("required_turn")
    if isinstance(required_turn, str) and required_turn.strip():
        return True
    passage_mode = contract.get("passage_mode")
    ending_shape = contract.get("ending_shape")
    return isinstance(passage_mode, str) and isinstance(ending_shape, str)


def _scene_mode_structure_match(text: str, contract: dict[str, object]) -> list[str] | None:
    passage_mode = contract.get("passage_mode")
    if not isinstance(passage_mode, str) or passage_mode.casefold() != "scene":
        return None

    missing: list[str] = []
    if not _has_any_signal(text, SCENE_GOAL_SIGNAL_PHRASES):
        missing.append("scene_goal")
    if not _has_any_signal(text, SCENE_OPPOSITION_SIGNAL_PHRASES):
        missing.append("opposition")
    return missing or None


def _mixed_mode_structure_match(text: str, contract: dict[str, object]) -> list[str] | None:
    passage_mode = contract.get("passage_mode")
    if not isinstance(passage_mode, str) or passage_mode.casefold() != "mixed":
        return None

    missing: list[str] = []
    if not _has_any_signal(text, MIXED_ACTION_SIGNAL_PHRASES):
        missing.append("action")
    if not _has_any_signal(text, MIXED_REACTION_SIGNAL_PHRASES):
        missing.append("reaction")
    if not _has_any_signal(text, SEQUEL_DECISION_SIGNAL_PHRASES):
        missing.append("decision")
    return missing or None


def _sequel_mode_structure_match(text: str, contract: dict[str, object]) -> list[str] | None:
    passage_mode = contract.get("passage_mode")
    if not isinstance(passage_mode, str) or passage_mode.casefold() != "sequel":
        return None

    missing: list[str] = []
    if not _has_any_signal(text, SEQUEL_DILEMMA_SIGNAL_PHRASES):
        missing.append("dilemma")
    if not _has_any_signal(text, SEQUEL_DECISION_SIGNAL_PHRASES):
        missing.append("decision")
    return missing or None


def _has_turn_signal(text: str) -> bool:
    return _has_any_signal(text, TURN_SIGNAL_PHRASES)


def _has_any_signal(text: str, phrases: tuple[str, ...]) -> bool:
    normalized_text = _normalized(text)
    return any(_normalized(phrase) in normalized_text for phrase in phrases)


def _signal_count(text: str, phrases: tuple[str, ...]) -> int:
    normalized_text = _normalized(text)
    return sum(1 for phrase in phrases if _normalized(phrase) in normalized_text)
