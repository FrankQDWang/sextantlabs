from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence


class LocalEmbeddingProvider:
    provider_name = "local_deterministic"
    model_name = "local-semantic-hash-v1"
    dimensions = 32

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [_normalized_vector(text, self.dimensions) for text in texts]


TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

LOCAL_SEMANTIC_EQUIVALENTS: dict[str, str] = {
    "clandestine": "secret",
    "covert": "secret",
    "hidden": "secret",
    "unnamed": "secret",
    "contact": "informant",
    "source": "informant",
    "spy": "informant",
}

LOCAL_EMBEDDING_STOPWORDS = {
    "appearance_log",
    "canonical_entity_id",
    "character",
    "contradictions",
    "current_canon",
    "draft_next_passage",
    "event_log",
    "id",
    "label",
    "memory_page",
    "open_threads",
    "relationships",
    "target_ref",
    "title",
    "type",
}


def _normalized_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0 for _ in range(dimensions)]
    for token in _semantic_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def _semantic_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_PATTERN.findall(text.casefold()):
        if raw_token in LOCAL_EMBEDDING_STOPWORDS:
            continue
        if "_" in raw_token or any(character.isdigit() for character in raw_token):
            continue
        token = LOCAL_SEMANTIC_EQUIVALENTS.get(raw_token, raw_token)
        tokens.append(token)
    return tokens
