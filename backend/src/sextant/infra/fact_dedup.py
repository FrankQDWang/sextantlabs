from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.infra.db.models import EvidenceLogEntry, FactAssertionRecord


def find_matching_fact(
    session: Session,
    *,
    project_id: UUID,
    subject_ref: Mapping[str, object],
    predicate: str,
    object_ref: Mapping[str, object],
) -> FactAssertionRecord | None:
    facts = session.scalars(
        select(FactAssertionRecord)
        .where(FactAssertionRecord.project_id == project_id)
        .where(FactAssertionRecord.predicate == predicate)
    )
    for fact in facts:
        if refs_equivalent(fact.subject_ref, subject_ref) and refs_equivalent(
            fact.object_ref,
            object_ref,
        ):
            return fact
    return None


def refs_equivalent(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return bool(_ref_identities(left).intersection(_ref_identities(right)))


def merge_fact_evidence(fact: FactAssertionRecord, evidence_span_ids: list[str]) -> bool:
    merged = merge_unique_text(fact.evidence_span_ids, evidence_span_ids)
    if merged == fact.evidence_span_ids:
        return False
    fact.evidence_span_ids = merged
    return True


def merge_unique_text(existing: list[str], additional: list[str]) -> list[str]:
    result = list(existing)
    seen = set(result)
    for value in additional:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def evidence_log_exists(
    session: Session,
    *,
    fact_id: UUID,
    source_span_ids: list[str],
) -> bool:
    span_set = set(source_span_ids)
    for entry in session.scalars(
        select(EvidenceLogEntry).where(EvidenceLogEntry.fact_id == fact_id)
    ):
        if span_set.issubset(set(entry.source_span_ids)):
            return True
    return False


def _ref_identities(ref: Mapping[str, object]) -> set[tuple[str, str]]:
    ref_type = ref.get("type")
    ref_id = ref.get("id")
    identities: set[tuple[str, str]] = set()
    if ref_type is not None and ref_id is not None:
        if ref_type == "knowledge_claim" and ref.get("certainty") is not None:
            identities.add((str(ref_type), f"{ref_id}:certainty:{ref['certainty']}"))
            return identities
        identities.add((str(ref_type), str(ref_id)))
    slug = ref.get("slug")
    if ref_type is not None and slug is not None:
        identities.add((str(ref_type), str(slug)))
    if identities:
        return identities
    return {("json", json.dumps(dict(ref), ensure_ascii=False, sort_keys=True))}
