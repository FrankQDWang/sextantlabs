from __future__ import annotations

from sextant.domain.agent_risk import contains_canon_risk_language


def test_canon_risk_language_uses_category_combination_not_fixture_sentence() -> None:
    assert contains_canon_risk_language("这段把未确认线索写成已经坐实。") is True
    assert (
        contains_canon_risk_language("The draft treats forbidden knowledge as confirmed.") is True
    )


def test_canon_risk_language_ignores_local_uncertainty_without_confirmation() -> None:
    assert contains_canon_risk_language("她仍然不能确认钥匙来源，只把问题留在桌面上。") is False
