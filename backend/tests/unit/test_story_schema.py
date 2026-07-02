from __future__ import annotations

from sextant.domain.story_schema import (
    StorySchemaPackSnapshot,
    build_effective_story_schema,
    default_base_story_schema_pack,
)


def test_default_base_story_schema_contains_documented_whitelists() -> None:
    schema = build_effective_story_schema([default_base_story_schema_pack()])

    assert "character" in schema.entity_types
    assert "location" in schema.entity_types
    assert "knowledge_change" in schema.event_types
    assert "present_at" in schema.relations
    assert "participates_in" not in schema.relations
    assert schema.allows_relation_for_entity_type("character", "present_at")
    assert not schema.allows_relation_for_entity_type("character", "participates_in")


def test_genre_extensions_require_subtype_to_inherit_specific_relations() -> None:
    genre = StorySchemaPackSnapshot(
        pack_type="genre",
        pack_name="mystery",
        version="mystery.v1",
        status="active",
        entity_types=[
            {"name": "clue", "subtype_of": "object", "display_name": "Clue"},
            {"name": "omen", "display_name": "Omen"},
        ],
        event_types=["deduction"],
        relations=["points_to"],
    )

    schema = build_effective_story_schema([default_base_story_schema_pack(), genre])

    assert schema.entity_types["clue"]["subtype_of"] == "object"
    assert schema.allows_relation_for_entity_type("clue", "points_to")
    assert schema.allows_relation_for_entity_type("omen", "related_to")
    assert not schema.allows_relation_for_entity_type("omen", "points_to")
    assert "deduction" in schema.event_types


def test_project_override_extends_without_removing_base_schema() -> None:
    override = StorySchemaPackSnapshot(
        pack_type="project_override",
        pack_name="harbor-nine-overrides",
        version="project.v1",
        status="active",
        entity_types=[
            {
                "name": "star_scar",
                "subtype_of": "object",
                "display_name": "星痕",
                "aliases": ["星痕", "旧星痕"],
            }
        ],
        event_types=[],
        relations=[],
    )

    schema = build_effective_story_schema([default_base_story_schema_pack(), override])

    assert "source" in schema.entity_types
    assert "star_scar" in schema.entity_types
    assert schema.entity_types["star_scar"]["subtype_of"] == "object"
    assert schema.allows_relation_for_entity_type("star_scar", "owns")


def test_project_override_relation_roles_are_effective_schema_metadata() -> None:
    override = StorySchemaPackSnapshot(
        pack_type="project_override",
        pack_name="harbor-nine-overrides",
        version="project.v1",
        status="active",
        relations=[
            {
                "name": "guards",
                "subject_types": ["character", "faction"],
                "object_types": ["location", "object"],
            }
        ],
    )

    schema = build_effective_story_schema([default_base_story_schema_pack(), override])

    assert "guards" in schema.relations
    assert schema.relation_roles["guards"] == (
        frozenset({"character", "faction"}),
        frozenset({"location", "object"}),
    )


def test_disabled_relation_removes_effective_relation_role() -> None:
    override = StorySchemaPackSnapshot(
        pack_type="project_override",
        pack_name="harbor-nine-overrides",
        version="project.v1",
        status="active",
        relations=[
            {
                "name": "guards",
                "subject_types": ["character"],
                "object_types": ["location"],
            }
        ],
        risk_rules={"disabled_relations": ["guards"]},
    )

    schema = build_effective_story_schema([default_base_story_schema_pack(), override])

    assert "guards" not in schema.relations
    assert "guards" not in schema.relation_roles


def test_project_override_can_disable_event_types() -> None:
    override = StorySchemaPackSnapshot(
        pack_type="project_override",
        pack_name="harbor-nine-overrides",
        version="project.v1",
        status="active",
        risk_rules={"disabled_event_types": ["object_transfer"]},
    )

    schema = build_effective_story_schema([default_base_story_schema_pack(), override])

    assert "discovery" in schema.event_types
    assert "object_transfer" not in schema.event_types
