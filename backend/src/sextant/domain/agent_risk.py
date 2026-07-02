from __future__ import annotations

EXPLICIT_CANON_RISK_TERMS = (
    "risk-context",
    "forbidden knowledge",
)

CANON_RISK_CONFIRMATION_TERMS = (
    "already exposed",
    "confirmed",
    "settled",
    "revealed",
    "exposed",
    "已经",
    "已",
    "已确认",
    "已经确认",
    "确信",
    "坐实",
    "暴露",
    "揭开",
)

CANON_RISK_BOUNDARY_TERMS = (
    "current evidence",
    "evidence boundary",
    "unconfirmed",
    "forbidden",
    "unsupported",
    "未确认",
    "不能确认",
    "无法确认",
    "当前证据",
    "证据边界",
    "越过",
    "越界",
)


def contains_canon_risk_language(text: str) -> bool:
    lowered = text.casefold()
    if any(term in lowered for term in EXPLICIT_CANON_RISK_TERMS):
        return True
    return _contains_any(lowered, CANON_RISK_CONFIRMATION_TERMS) and _contains_any(
        lowered,
        CANON_RISK_BOUNDARY_TERMS,
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term.casefold() in text for term in terms)
