from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

BASE_STORY_SCHEMA_PACK_NAME = "base-story-schema"
BASE_STORY_SCHEMA_VERSION = "base-story-schema.v1"

BASE_ENTITY_TYPES = (
    "character",
    "location",
    "faction",
    "object",
    "event",
    "scene",
    "chapter",
    "plotline",
    "lore",
    "source",
)

BASE_EVENT_TYPES = (
    "first_meeting",
    "discovery",
    "revelation",
    "knowledge_change",
    "object_transfer",
    "conflict",
    "promise",
    "betrayal",
    "death",
    "travel",
    "relationship_change",
    "foreshadowing",
    "payoff",
    "decision",
    "other",
)

AGENCY_PROFILE_RELATIONS = (
    "core_desire",
    "immediate_want",
    "fear_or_wound",
    "moral_boundary",
    "secret",
    "contradiction",
    "relationship_stance",
    "voice_fingerprint",
    "agency_rule",
    "change_pressure",
)

BASE_RELATIONS = (
    "appears_in",
    "present_at",
    "occurred_at",
    "involves_object",
    "located_in",
    "owns",
    "member_of",
    "family_of",
    "ally_of",
    "enemy_of",
    "knows",
    "does_not_know",
    "reveals",
    "causes",
    "follows",
    "foreshadows",
    "contradicts",
    "belongs_to_plotline",
    "related_to",
    *AGENCY_PROFILE_RELATIONS,
)

ANY_SCHEMA_ENTITY = "$entity"
BASE_RELATION_ROLE_RULES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "appears_in": (frozenset({ANY_SCHEMA_ENTITY}), frozenset({"scene", "chapter"})),
    "present_at": (frozenset({"character", "faction"}), frozenset({"event"})),
    "occurred_at": (frozenset({"event"}), frozenset({"location"})),
    "involves_object": (frozenset({"event"}), frozenset({"object"})),
    "located_in": (frozenset({ANY_SCHEMA_ENTITY}), frozenset({"location"})),
    "owns": (frozenset({"character", "faction"}), frozenset({"object"})),
    "member_of": (frozenset({"character"}), frozenset({"faction"})),
    "family_of": (frozenset({"character"}), frozenset({"character"})),
    "ally_of": (frozenset({"character", "faction"}), frozenset({"character", "faction"})),
    "enemy_of": (frozenset({"character", "faction"}), frozenset({"character", "faction"})),
    "knows": (
        frozenset({"character"}),
        frozenset({"event", "knowledge_claim", "lore", "secret"}),
    ),
    "does_not_know": (
        frozenset({"character"}),
        frozenset({"event", "knowledge_claim", "lore", "secret"}),
    ),
    "reveals": (
        frozenset({"event", "scene"}),
        frozenset({"event", "knowledge_claim", "lore", "secret"}),
    ),
    "causes": (frozenset({"event"}), frozenset({"event", "fact_assertion", "knowledge_claim"})),
    "follows": (frozenset({"event", "scene"}), frozenset({"event", "scene"})),
    "foreshadows": (frozenset({"scene", "event", "object"}), frozenset({"event", "plotline"})),
    "contradicts": (
        frozenset({"event", "fact_assertion", "review_item"}),
        frozenset({"event", "fact_assertion"}),
    ),
    "belongs_to_plotline": (
        frozenset({"event", "fact_assertion", "scene"}),
        frozenset({"plotline"}),
    ),
    "core_desire": (frozenset({"character"}), frozenset({"literal"})),
    "immediate_want": (frozenset({"character"}), frozenset({"literal"})),
    "fear_or_wound": (frozenset({"character"}), frozenset({"literal"})),
    "moral_boundary": (frozenset({"character"}), frozenset({"literal"})),
    "secret": (frozenset({"character"}), frozenset({"literal", "secret"})),
    "contradiction": (frozenset({"character"}), frozenset({"literal"})),
    "relationship_stance": (frozenset({"character"}), frozenset({"literal"})),
    "voice_fingerprint": (frozenset({"character"}), frozenset({"literal"})),
    "agency_rule": (frozenset({"character"}), frozenset({"literal"})),
    "change_pressure": (frozenset({"character"}), frozenset({"literal"})),
}

STORY_SCHEMA_PACK_TYPES = ("base", "genre", "project_override")
STORY_SCHEMA_PACK_STATUSES = ("active", "deprecated")
PROJECT_SCHEMA_BINDING_STATUSES = ("active", "superseded")


@dataclass(frozen=True, slots=True)
class StorySchemaPackSnapshot:
    pack_type: str
    pack_name: str
    version: str
    status: str
    entity_types: list[dict[str, Any]] = field(default_factory=list)
    event_types: list[str | dict[str, Any]] = field(default_factory=list)
    relations: list[str | dict[str, Any]] = field(default_factory=list)
    extraction_hints: dict[str, Any] = field(default_factory=dict)
    risk_rules: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EffectiveStorySchema:
    entity_types: dict[str, dict[str, Any]]
    event_types: frozenset[str]
    relations: frozenset[str]
    relation_roles: dict[str, tuple[frozenset[str], frozenset[str]]]
    extraction_hints: dict[str, Any]
    weak_entity_types: frozenset[str]
    source_pack_versions: tuple[str, ...]

    def allows_relation_for_entity_type(self, entity_type: str, relation: str) -> bool:
        if entity_type not in self.entity_types or relation not in self.relations:
            return False
        if entity_type in self.weak_entity_types:
            return relation == "related_to"
        return True


def default_base_story_schema_pack() -> StorySchemaPackSnapshot:
    return StorySchemaPackSnapshot(
        pack_type="base",
        pack_name=BASE_STORY_SCHEMA_PACK_NAME,
        version=BASE_STORY_SCHEMA_VERSION,
        status="active",
        entity_types=[{"name": name} for name in BASE_ENTITY_TYPES],
        event_types=list(BASE_EVENT_TYPES),
        relations=list(BASE_RELATIONS),
    )


def build_effective_story_schema(packs: list[StorySchemaPackSnapshot]) -> EffectiveStorySchema:
    entity_types: dict[str, dict[str, Any]] = {}
    event_types: set[str] = set()
    relations: set[str] = set()
    relation_roles: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    extraction_hints: dict[str, Any] = {}
    weak_entity_types: set[str] = set()
    source_pack_versions: list[str] = []
    disabled_event_types: set[str] = set()
    disabled_relations: set[str] = set()

    for pack in packs:
        if pack.status != "active":
            continue
        source_pack_versions.append(pack.version)
        for entity_definition in pack.entity_types:
            normalized = _normalize_entity_definition(entity_definition)
            entity_name = str(normalized["name"])
            entity_types[entity_name] = {**entity_types.get(entity_name, {}), **normalized}
            if entity_name not in BASE_ENTITY_TYPES and not normalized.get("subtype_of"):
                weak_entity_types.add(entity_name)
            else:
                weak_entity_types.discard(entity_name)
        event_types.update(_name_from_definition(item) for item in pack.event_types)
        for relation_definition in pack.relations:
            relation_name = _name_from_definition(relation_definition)
            relations.add(relation_name)
            relation_role = _relation_role_from_definition(relation_definition)
            if relation_role is not None:
                relation_roles[relation_name] = relation_role
            elif relation_name in BASE_RELATION_ROLE_RULES and relation_name not in relation_roles:
                relation_roles[relation_name] = BASE_RELATION_ROLE_RULES[relation_name]
        _merge_extraction_hints(extraction_hints, pack.extraction_hints)
        disabled_event_types.update(_names_from_rule(pack.risk_rules.get("disabled_event_types")))
        disabled_relations.update(_names_from_rule(pack.risk_rules.get("disabled_relations")))

    event_types.difference_update(disabled_event_types)
    relations.difference_update(disabled_relations)
    for disabled_relation in disabled_relations:
        relation_roles.pop(disabled_relation, None)

    return EffectiveStorySchema(
        entity_types=entity_types,
        event_types=frozenset(event_types),
        relations=frozenset(relations),
        relation_roles=relation_roles,
        extraction_hints=extraction_hints,
        weak_entity_types=frozenset(weak_entity_types),
        source_pack_versions=tuple(source_pack_versions),
    )


def _normalize_entity_definition(definition: dict[str, Any]) -> dict[str, Any]:
    name = _name_from_definition(definition)
    normalized = dict(definition)
    normalized["name"] = name
    if normalized.get("subtype_of") is not None:
        normalized["subtype_of"] = str(normalized["subtype_of"]).strip()
    return normalized


def _name_from_definition(definition: object) -> str:
    if isinstance(definition, Mapping):
        raw_name = cast(Mapping[str, object], definition).get("name")
    else:
        raw_name = definition
    name = str(raw_name or "").strip()
    if not name:
        raise ValueError("Story schema definitions require a non-empty name.")
    return name


def _names_from_rule(rule_value: object) -> set[str]:
    if not isinstance(rule_value, list):
        return set()
    names: set[str] = set()
    for item in rule_value:
        if isinstance(item, (str, Mapping)):
            names.add(_name_from_definition(item))
    return names


def _relation_role_from_definition(
    definition: object,
) -> tuple[frozenset[str], frozenset[str]] | None:
    if not isinstance(definition, Mapping):
        return None
    mapping = cast(Mapping[str, object], definition)
    subject_types = _names_from_rule(
        mapping.get("subject_types") or mapping.get("subject_ref_types")
    )
    object_types = _names_from_rule(mapping.get("object_types") or mapping.get("object_ref_types"))
    if not subject_types or not object_types:
        return None
    return frozenset(subject_types), frozenset(object_types)


def _merge_extraction_hints(target: dict[str, Any], hints: dict[str, Any]) -> None:
    for key, value in hints.items():
        existing = target.get(key)
        if isinstance(existing, list) and isinstance(value, list):
            target[key] = [*existing, *value]
            continue
        if isinstance(existing, dict) and isinstance(value, dict):
            target[key] = {**existing, **value}
            continue
        target[key] = value
