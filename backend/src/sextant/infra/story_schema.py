from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from sextant.domain.story_schema import (
    EffectiveStorySchema,
    StorySchemaPackSnapshot,
    build_effective_story_schema,
    default_base_story_schema_pack,
)
from sextant.infra.db.models import ProjectStorySchemaBinding, StorySchemaPackRecord


def load_effective_story_schema(session: Session, project_id: UUID) -> EffectiveStorySchema:
    binding = session.scalars(
        select(ProjectStorySchemaBinding)
        .where(ProjectStorySchemaBinding.project_id == project_id)
        .where(ProjectStorySchemaBinding.status == "active")
        .order_by(ProjectStorySchemaBinding.created_at.desc(), ProjectStorySchemaBinding.id.desc())
    ).first()
    if binding is None:
        return build_effective_story_schema([default_base_story_schema_pack()])

    pack_ids = [
        binding.base_schema_pack_id,
        binding.genre_schema_pack_id,
        binding.project_override_pack_id,
    ]
    packs_by_id = {
        pack.id: pack
        for pack in session.scalars(
            select(StorySchemaPackRecord).where(StorySchemaPackRecord.id.in_(pack_ids))
        )
    }
    snapshots = [_snapshot_from_record(packs_by_id[binding.base_schema_pack_id])]
    if binding.genre_schema_pack_id is not None:
        snapshots.append(_snapshot_from_record(packs_by_id[binding.genre_schema_pack_id]))
    if binding.project_override_pack_id is not None:
        snapshots.append(_snapshot_from_record(packs_by_id[binding.project_override_pack_id]))
    return build_effective_story_schema(snapshots)


def _snapshot_from_record(record: StorySchemaPackRecord) -> StorySchemaPackSnapshot:
    return StorySchemaPackSnapshot(
        pack_type=record.pack_type,
        pack_name=record.pack_name,
        version=record.version,
        status=record.status,
        entity_types=record.entity_types,
        event_types=record.event_types,
        relations=record.relations,
        extraction_hints=record.extraction_hints,
        risk_rules=record.risk_rules,
    )
