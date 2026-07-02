from __future__ import annotations

import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from sextant.infra.db.models import (  # noqa: E402
    FactAssertionRecord,
    MemoryPage,
    Project,
    ProjectMembership,
    RawSource,
    ReviewItemRecord,
    SourceProcessedView,
    SourceSpan,
    SourceVersion,
    StoryAliasRecord,
    StoryCanonicalEntity,
    StoryChapter,
    StoryMention,
    StoryScene,
    StorySchemaPackRecord,
)
from sextant.infra.graph_projection import rebuild_graph_projection  # noqa: E402
from sextant.infra.object_store import LocalObjectStore  # noqa: E402

MANUSCRIPT = "\n".join(
    [
        "Mira 把空的地图筒推过桌面。黄铜的筒身在灯下泛着旧光，里面什么也没有。",
        "「你昨晚在西档案室附近。」她说，没有抬头。",
        "Kestrel 的拇指找到了外衣上的黄铜锁扣，停在那里，静止得足以算作一种回答。",
        "她把钥匙放在两人之间。钥匙是冷的，比这间屋子里任何东西都冷。",
    ]
)


def main() -> None:
    database_url = os.environ.get(
        "SEXTANT_DATABASE_URL",
        "sqlite+pysqlite:///./.sextant/local.db",
    )
    object_store = LocalObjectStore(
        Path(os.environ.get("SEXTANT_OBJECT_STORE_ROOT", "./.sextant/objects"))
    )
    engine = create_engine(database_url)

    project_id, actor_id, source_id, version_id = _seed_ids()
    chapter_id, scene_id = _seed_structure_ids()
    review_id, view_id, span_id = _seed_review_ids()
    (
        alias_review_id,
        alias_span_id,
        old_entity_id,
        target_entity_id,
        alias_id,
        mention_id,
        fact_id,
        page_id,
    ) = _seed_alias_review_ids()
    raw_text_ref = object_store.put_text("raw/harbor-nine-ch03.txt", MANUSCRIPT)
    raw_hash = sha256(MANUSCRIPT.encode("utf-8")).hexdigest()
    span_text = "钥匙是冷的"
    span_start = MANUSCRIPT.index(span_text)
    span_end = span_start + len(span_text)
    markdown_ref = object_store.put_text("processed/harbor-nine-ch03.md", MANUSCRIPT)
    offset_ref = object_store.put_text(
        "processed/harbor-nine-ch03.offsets.json",
        json.dumps({"spans": [{"processed": [0, len(MANUSCRIPT)], "raw": [0, len(MANUSCRIPT)]}]}),
    )

    with Session(engine) as session:
        mystery_pack = (
            session.query(StorySchemaPackRecord)
            .filter_by(
                project_id=None,
                pack_type="genre",
                pack_name="mystery",
                version="mystery.v1",
            )
            .one_or_none()
        )
        session.add(Project(id=project_id, name="Harbor Nine"))
        session.flush()
        session.add_all(
            [
                ProjectMembership(
                    id=uuid4(),
                    project_id=project_id,
                    actor_id=actor_id,
                    role="owner",
                    status="active",
                ),
                RawSource(
                    id=source_id,
                    project_id=project_id,
                    source_type="draft_manuscript",
                    source_scope="user_draft",
                    title="Ch.03 西档案室",
                    ownership_status="owned",
                    raw_text_ref=raw_text_ref,
                ),
            ]
        )
        if mystery_pack is None:
            session.add(
                StorySchemaPackRecord(
                    id=UUID("00000000-0000-4000-8000-000000000008")
                    if os.environ.get("SEXTANT_SEED_WORKBENCH_FIXED_IDS") == "1"
                    else uuid4(),
                    project_id=None,
                    pack_type="genre",
                    pack_name="mystery",
                    version="mystery.v1",
                    status="active",
                    entity_types=[{"name": "clue", "subtype_of": "object"}],
                    event_types=["revelation"],
                    relations=[
                        {
                            "name": "points_to",
                            "subject_types": ["clue"],
                            "object_types": ["character"],
                        }
                    ],
                    extraction_hints={},
                    risk_rules={},
                )
            )
        session.flush()
        session.add(
            SourceVersion(
                id=version_id,
                source_id=source_id,
                version_label="v1",
                raw_hash=raw_hash,
                raw_text_ref=raw_text_ref,
            )
        )
        session.flush()
        session.add(
            SourceProcessedView(
                id=view_id,
                version_id=version_id,
                cleaning_profile="draft_manuscript_profile_v1",
                markdown_ref=markdown_ref,
                raw_offset_map_ref=offset_ref,
                view_status="current",
            )
        )
        session.flush()
        session.add(
            StoryChapter(
                id=chapter_id,
                view_id=view_id,
                chapter_index=0,
                title="Ch.03 西档案室",
                start_offset=0,
                end_offset=len(MANUSCRIPT),
                summary="Mira 在西档案室用钥匙和 Kestrel 的沉默互相试探。",
            )
        )
        session.flush()
        session.add(
            StoryScene(
                id=scene_id,
                chapter_id=chapter_id,
                scene_index=0,
                location_entity_id=None,
                pov_character_id=target_entity_id,
                pov_mode="limited",
                pov_confidence=0.87,
                pov_evidence_span_ids=[str(span_id), str(alias_span_id)],
                pov_uncertainty_reason=None,
                story_time="night",
                emotional_tone="restrained tension",
                scene_summary="Mira probes Kestrel with the cold key and the empty map tube.",
                scene_function="interrogation_pressure",
                start_offset=0,
                end_offset=len(MANUSCRIPT),
            )
        )
        session.flush()
        session.add_all(
            [
                SourceSpan(
                    id=span_id,
                    source_id=source_id,
                    version_id=version_id,
                    view_id=view_id,
                    chapter_id=chapter_id,
                    scene_id=scene_id,
                    start_offset=span_start,
                    end_offset=span_end,
                    raw_start_offset=span_start,
                    raw_end_offset=span_end,
                    text_preview=span_text,
                    speaker_entity_id=None,
                    narration_layer="narrator",
                ),
                SourceSpan(
                    id=alias_span_id,
                    source_id=source_id,
                    version_id=version_id,
                    view_id=view_id,
                    chapter_id=chapter_id,
                    scene_id=scene_id,
                    start_offset=0,
                    end_offset=min(22, len(MANUSCRIPT)),
                    raw_start_offset=0,
                    raw_end_offset=min(22, len(MANUSCRIPT)),
                    text_preview="Starling 带着灯图。",
                    speaker_entity_id=None,
                    narration_layer="narrator",
                ),
                ReviewItemRecord(
                    id=review_id,
                    project_id=project_id,
                    review_type="knowledge_conflict",
                    severity="medium",
                    status="open",
                    summary="钥匙来源仍未确认，暂不能写成 Mira 已经知道。",
                    affected_refs={
                        "source_id": str(source_id),
                        "source_version_id": str(version_id),
                    },
                    new_evidence={"source_span_ids": [str(span_id)]},
                    existing_evidence={},
                    suggested_actions=[
                        {"resolution": "accepted_as_change"},
                        {"resolution": "mark_intentional"},
                    ],
                    default_action="ask_author",
                    resolution=None,
                    side_effects={},
                ),
            ]
        )
        old_ref = {
            "type": "character",
            "id": str(old_entity_id),
            "label": "Starling",
            "canonical_entity_id": str(old_entity_id),
            "slug": "starling",
        }
        session.add_all(
            [
                StoryCanonicalEntity(
                    id=old_entity_id,
                    project_id=project_id,
                    entity_type="character",
                    display_name="Starling",
                    canonical_status="provisional",
                    cast_tier="unknown",
                ),
                StoryCanonicalEntity(
                    id=target_entity_id,
                    project_id=project_id,
                    entity_type="character",
                    display_name="Mira",
                    canonical_status="provisional",
                    cast_tier="unknown",
                ),
                StoryAliasRecord(
                    id=alias_id,
                    project_id=project_id,
                    alias_text="Starling",
                    entity_id=old_entity_id,
                    alias_type="name",
                    status="proposed",
                    scope="disguise_arc",
                    evidence_span_ids=[str(alias_span_id)],
                    confidence=0.72,
                ),
                StoryMention(
                    id=mention_id,
                    span_id=alias_span_id,
                    raw_text="Starling",
                    mention_type="character",
                    local_context="Starling 带着灯图。",
                    resolved_entity_id=old_entity_id,
                    resolution_status="alias_recorded",
                    confidence=0.72,
                ),
                FactAssertionRecord(
                    id=fact_id,
                    project_id=project_id,
                    subject_ref=old_ref,
                    predicate="owns",
                    object_ref={"type": "object", "id": "lantern-map", "label": "Lantern Map"},
                    fact_status="canon",
                    evidence_span_ids=[str(alias_span_id)],
                    confidence=0.9,
                    source_scope="user_draft",
                    promotion_decision_id=uuid4(),
                ),
                MemoryPage(
                    id=page_id,
                    project_id=project_id,
                    page_type="character",
                    target_ref=old_ref,
                    title="Starling",
                    current_canon={"facts": [{"fact_id": str(fact_id), "predicate": "owns"}]},
                    appearance_log=[],
                    event_log=[],
                    relationships=[],
                    open_threads=[
                        {
                            "id": "map-origin",
                            "update_type": "opens",
                            "summary": "地图来源仍待确认。",
                            "risk_level": "low",
                            "source_span_ids": [str(alias_span_id)],
                            "status": "open",
                        }
                    ],
                    contradictions=[],
                    source_refs=[{"type": "source_span", "id": str(alias_span_id)}],
                    canon_status="current",
                    memory_depth="scene",
                ),
                ReviewItemRecord(
                    id=alias_review_id,
                    project_id=project_id,
                    review_type="alias_conflict",
                    severity="medium",
                    status="open",
                    summary="Starling 应合并为 Mira。",
                    affected_refs={
                        "alias_record_id": str(alias_id),
                        "target_entity_id": str(target_entity_id),
                        "fact_ids": [str(fact_id)],
                        "memory_page_id": str(page_id),
                        "alias_scope": "disguise_arc",
                        "valid_from_scene_id": None,
                        "valid_until_scene_id": None,
                    },
                    new_evidence={
                        "alias_text": "Starling",
                        "source_span_ids": [str(alias_span_id)],
                    },
                    existing_evidence={"alias_text": "Starling"},
                    suggested_actions=[{"resolution": "accepted_as_change"}],
                    default_action="accepted_as_change",
                    resolution=None,
                    side_effects={},
                ),
            ]
        )
        session.flush()
        rebuild_graph_projection(session, project_id=project_id)
        session.commit()

    print("Seeded Sextant workbench project:")
    print(f"VITE_SEXTANT_PROJECT_ID={project_id}")
    print(f"VITE_SEXTANT_ACTOR_ID={actor_id}")
    print(f"VITE_SEXTANT_SOURCE_ID={source_id}")
    print(f"VITE_SEXTANT_SOURCE_VERSION_ID={version_id}")
    print(f"VITE_SEXTANT_SCENE_ID={scene_id}")
    print(f"VITE_SEXTANT_POV_CHARACTER_ID={target_entity_id}")


def _seed_ids() -> tuple[UUID, UUID, UUID, UUID]:
    if os.environ.get("SEXTANT_SEED_WORKBENCH_FIXED_IDS") == "1":
        return (
            UUID("00000000-0000-4000-8000-000000000001"),
            UUID("00000000-0000-4000-8000-000000000002"),
            UUID("00000000-0000-4000-8000-000000000003"),
            UUID("00000000-0000-4000-8000-000000000004"),
        )
    return uuid4(), uuid4(), uuid4(), uuid4()


def _seed_review_ids() -> tuple[UUID, UUID, UUID]:
    if os.environ.get("SEXTANT_SEED_WORKBENCH_FIXED_IDS") == "1":
        return (
            UUID("00000000-0000-4000-8000-000000000005"),
            UUID("00000000-0000-4000-8000-000000000006"),
            UUID("00000000-0000-4000-8000-000000000007"),
        )
    return uuid4(), uuid4(), uuid4()


def _seed_structure_ids() -> tuple[UUID, UUID]:
    if os.environ.get("SEXTANT_SEED_WORKBENCH_FIXED_IDS") == "1":
        return (
            UUID("00000000-0000-4000-8000-000000000011"),
            UUID("00000000-0000-4000-8000-000000000012"),
        )
    return uuid4(), uuid4()


def _seed_alias_review_ids() -> tuple[UUID, UUID, UUID, UUID, UUID, UUID, UUID, UUID]:
    if os.environ.get("SEXTANT_SEED_WORKBENCH_FIXED_IDS") == "1":
        return (
            UUID("00000000-0000-4000-8000-000000000009"),
            UUID("00000000-0000-4000-8000-00000000000a"),
            UUID("00000000-0000-4000-8000-00000000000b"),
            UUID("00000000-0000-4000-8000-00000000000c"),
            UUID("00000000-0000-4000-8000-00000000000d"),
            UUID("00000000-0000-4000-8000-00000000000e"),
            UUID("00000000-0000-4000-8000-00000000000f"),
            UUID("00000000-0000-4000-8000-000000000010"),
        )
    return tuple(uuid4() for _ in range(8))


if __name__ == "__main__":
    main()
