from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sextant.domain.common import DomainInvariantError


@dataclass(frozen=True, slots=True)
class AcceptedFragment:
    id: UUID
    candidate_id: UUID
    accepted_text_ref: str
    accepted_text_hash: str
    accept_mode: str
    target_source_id: UUID
    target_version_id: UUID
    insert_or_replace_range: tuple[int, int]
    source_scope: str
    author_edited: bool

    @classmethod
    def create(
        cls,
        *,
        candidate_id: UUID,
        accepted_text_ref: str,
        accepted_text_hash: str,
        accept_mode: str,
        target_source_id: UUID,
        target_version_id: UUID,
        insert_or_replace_range: tuple[int, int],
        source_scope: str,
        author_edited: bool,
    ) -> AcceptedFragment:
        start, end = insert_or_replace_range
        if start < 0 or end < start:
            raise DomainInvariantError("AcceptedFragment target range is invalid.")
        if accept_mode not in {"partial", "full"}:
            raise DomainInvariantError("AcceptedFragment accept_mode must be partial or full.")
        author_accepted_scopes = {"user_draft", "user_published", "author_note", "outline_plan"}
        if source_scope not in author_accepted_scopes:
            raise DomainInvariantError("AcceptedFragment source_scope is not author-accepted.")
        if not accepted_text_ref or not accepted_text_hash:
            raise DomainInvariantError(
                "AcceptedFragment requires accepted text reference and hash."
            )
        return cls(
            id=uuid4(),
            candidate_id=candidate_id,
            accepted_text_ref=accepted_text_ref,
            accepted_text_hash=accepted_text_hash,
            accept_mode=accept_mode,
            target_source_id=target_source_id,
            target_version_id=target_version_id,
            insert_or_replace_range=insert_or_replace_range,
            source_scope=source_scope,
            author_edited=author_edited,
        )
