from __future__ import annotations

from dataclasses import dataclass

from sextant.domain.story_schema import ANY_SCHEMA_ENTITY, EffectiveStorySchema

NON_ENTITY_FACT_REF_TYPES = frozenset(
    {
        "fact_assertion",
        "knowledge_claim",
        "literal",
        "review_item",
        "secret",
    }
)


@dataclass(frozen=True, slots=True)
class FactSchemaRejection:
    skipped: str
    details: dict[str, object]


def validate_fact_against_story_schema(
    story_schema: EffectiveStorySchema,
    *,
    predicate: str,
    subject_ref: dict[str, object],
    object_ref: dict[str, object],
) -> FactSchemaRejection | None:
    if predicate not in story_schema.relations:
        return FactSchemaRejection("schema_relation_not_allowed", {})

    ref_shape_rejection = _ref_shape_rejection(subject_ref=subject_ref, object_ref=object_ref)
    if ref_shape_rejection is not None:
        return FactSchemaRejection("schema_ref_shape_invalid", ref_shape_rejection)

    unknown_ref_rejection = _unknown_ref_type_rejection(
        story_schema,
        subject_ref=subject_ref,
        object_ref=object_ref,
    )
    if unknown_ref_rejection is not None:
        return FactSchemaRejection("schema_entity_type_not_allowed", unknown_ref_rejection)

    entity_relation_rejection = _entity_relation_rejection(
        story_schema,
        predicate=predicate,
        subject_ref=subject_ref,
        object_ref=object_ref,
    )
    if entity_relation_rejection is not None:
        return FactSchemaRejection(
            "schema_entity_relation_not_allowed",
            entity_relation_rejection,
        )

    role_rejection = _relation_role_rejection(
        story_schema,
        predicate=predicate,
        subject_ref=subject_ref,
        object_ref=object_ref,
    )
    if role_rejection is not None:
        return FactSchemaRejection("schema_relation_role_not_allowed", role_rejection)

    return None


def _ref_shape_rejection(
    *,
    subject_ref: dict[str, object],
    object_ref: dict[str, object],
) -> dict[str, object] | None:
    for ref_role, ref in (("subject", subject_ref), ("object", object_ref)):
        ref_type = ref.get("type")
        missing_fields: list[str] = []
        if not isinstance(ref_type, str) or not ref_type.strip():
            missing_fields.append("type")
        if ref_type == "literal":
            if "value" not in ref:
                missing_fields.append("value")
        else:
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id.strip():
                missing_fields.append("id")
        if missing_fields:
            return {
                "ref_role": ref_role,
                "ref_type": str(ref_type or ""),
                "missing_fields": missing_fields,
            }
    return None


def _unknown_ref_type_rejection(
    story_schema: EffectiveStorySchema,
    *,
    subject_ref: dict[str, object],
    object_ref: dict[str, object],
) -> dict[str, object] | None:
    for ref_role, ref in (("subject", subject_ref), ("object", object_ref)):
        ref_type = str(ref.get("type") or "")
        if ref_type in story_schema.entity_types or ref_type in NON_ENTITY_FACT_REF_TYPES:
            continue
        return {"ref_role": ref_role, "ref_type": ref_type}
    return None


def _entity_relation_rejection(
    story_schema: EffectiveStorySchema,
    *,
    predicate: str,
    subject_ref: dict[str, object],
    object_ref: dict[str, object],
) -> dict[str, object] | None:
    for ref_role, ref in (("subject", subject_ref), ("object", object_ref)):
        ref_type = str(ref.get("type") or "")
        if ref_type not in story_schema.entity_types:
            continue
        if story_schema.allows_relation_for_entity_type(ref_type, predicate):
            continue
        return {"ref_role": ref_role, "ref_type": ref_type}
    return None


def _relation_role_rejection(
    story_schema: EffectiveStorySchema,
    *,
    predicate: str,
    subject_ref: dict[str, object],
    object_ref: dict[str, object],
) -> dict[str, object] | None:
    rule = story_schema.relation_roles.get(predicate)
    if rule is None:
        return None
    subject_types, object_types = rule
    for ref_role, ref, allowed_types in (
        ("subject", subject_ref, subject_types),
        ("object", object_ref, object_types),
    ):
        ref_type = str(ref.get("type") or "")
        if _ref_type_matches_relation_role(story_schema, ref_type, allowed_types):
            continue
        return {
            "ref_role": ref_role,
            "ref_type": ref_type,
            "allowed_ref_types": sorted(allowed_types),
        }
    return None


def _ref_type_matches_relation_role(
    story_schema: EffectiveStorySchema,
    ref_type: str,
    allowed_types: frozenset[str],
) -> bool:
    if ref_type in allowed_types:
        return True
    if ANY_SCHEMA_ENTITY in allowed_types and ref_type in story_schema.entity_types:
        return True
    entity_definition = story_schema.entity_types.get(ref_type)
    if entity_definition is None:
        return False
    subtype = entity_definition.get("subtype_of")
    return isinstance(subtype, str) and subtype in allowed_types
