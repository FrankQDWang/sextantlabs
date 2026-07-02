from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingClient(Protocol):
    provider_name: str
    model_name: str
    dimensions: int

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...
