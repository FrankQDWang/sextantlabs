from __future__ import annotations

from typing import Protocol
from uuid import UUID


class AuthVerifier(Protocol):
    def actor_id_for_authorization(self, authorization: str | None) -> UUID | None: ...
