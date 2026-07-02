from __future__ import annotations

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = RRF_K,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        seen: set[str] = set()
        ordered = [item for item in ranking if item and item not in seen and not seen.add(item)]
        for position, item in enumerate(ordered, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return scores
