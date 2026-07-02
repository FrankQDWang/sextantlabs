from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Annotated, Literal, TypeAlias, Union, cast

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from sextant.common.observability import MetricsRegistry
from sextant.contracts.memory_extraction import (
    ExtractedFact,
    ExtractedThreadUpdate,
    MemoryExtractionResult,
)
from sextant.domain.story_schema import (
    ANY_SCHEMA_ENTITY,
    BASE_ENTITY_TYPES,
    BASE_RELATION_ROLE_RULES,
    BASE_RELATIONS,
)
from sextant.infra.openai_compat import (
    OpenAIApiStyle,
    create_openai_client,
    parse_openai_structured,
)
from sextant.infra.prompt_registry import PromptDefinition, load_prompt
from sextant.infra.provider_usage import record_openai_usage_metrics


class OpenAIEntityRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str = Field(min_length=1)
    id: str = Field(min_length=1)

    @field_validator("type", "id")
    @classmethod
    def validate_required_ref_field(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("entity refs require non-empty type and id")
        return stripped


class OpenAILiteralRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["literal"]
    value: str = Field(min_length=1)
    id: str | None = None

    @field_validator("value")
    @classmethod
    def validate_required_literal_value(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("literal refs require a non-empty value")
        return stripped


class OpenAIMemoryFactBase(BaseModel):
    risk_level: Literal["low", "medium", "high"]

    @field_validator("predicate", check_fields=False)
    @classmethod
    def validate_predicate(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("predicate is required")
        return stripped


def _literal_type(values: tuple[str, ...]) -> object:
    return Literal.__getitem__(values)


def _union_type(types: tuple[object, ...]) -> object:
    if len(types) == 1:
        return types[0]
    return Union[types]  # noqa: UP007 - Dynamic tuple union for Pydantic model generation.


def _pascal_identifier(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_") if part)


def _expanded_ref_types(allowed_types: frozenset[str]) -> tuple[str, ...]:
    expanded = set(allowed_types)
    if ANY_SCHEMA_ENTITY in expanded:
        expanded.remove(ANY_SCHEMA_ENTITY)
        expanded.update(BASE_ENTITY_TYPES)
    return tuple(sorted(expanded))


def _ref_type_for_role(relation: str, role: str, allowed_types: frozenset[str]) -> object:
    expanded_types = _expanded_ref_types(allowed_types)
    id_ref_types = tuple(ref_type for ref_type in expanded_types if ref_type != "literal")
    variants: list[object] = []
    suffix = f"{_pascal_identifier(relation)}{role.capitalize()}"

    if id_ref_types:
        variants.append(
            create_model(
                f"OpenAI{suffix}EntityRef",
                __base__=OpenAIEntityRef,
                __module__=__name__,
                type=(_literal_type(id_ref_types), Field(...)),
            )
        )
    if "literal" in expanded_types:
        variants.append(
            create_model(
                f"OpenAI{suffix}LiteralRef",
                __base__=OpenAILiteralRef,
                __module__=__name__,
                type=(_literal_type(("literal",)), Field(...)),
            )
        )
    return _union_type(tuple(variants)) if variants else OpenAIEntityRef


def _fact_model_for_relation(relation: str) -> type[BaseModel]:
    role_rule = BASE_RELATION_ROLE_RULES.get(relation)
    if role_rule is None:
        subject_ref_type: object = OpenAIEntityRef
        object_ref_type: object = OpenAIEntityRef
    else:
        subject_ref_type = _ref_type_for_role(relation, "subject", role_rule[0])
        object_ref_type = _ref_type_for_role(relation, "object", role_rule[1])
    model = create_model(
        f"OpenAIMemoryFact{_pascal_identifier(relation)}",
        __base__=OpenAIMemoryFactBase,
        __module__=__name__,
        subject_ref=(subject_ref_type, Field(...)),
        predicate=(_literal_type((relation,)), Field(...)),
        object_ref=(object_ref_type, Field(...)),
    )
    return cast(type[BaseModel], model)


_OPENAI_MEMORY_FACT_MODELS = tuple(
    _fact_model_for_relation(relation) for relation in BASE_RELATIONS
)

OpenAIMemoryFact: TypeAlias = Annotated[  # noqa: UP040 - Pydantic resolves this runtime alias.
    _union_type(_OPENAI_MEMORY_FACT_MODELS),  # ty: ignore[invalid-type-form]
    Field(discriminator="predicate"),
]


class OpenAIMemoryThreadUpdate(BaseModel):
    target_ref: OpenAIEntityRef
    update_type: Literal["opens", "keeps_open", "narrows", "pays_off", "closes"]
    thread_id: str | None = None
    description: str = Field(min_length=1)
    risk_level: Literal["low", "medium", "high"]

    @field_validator("thread_id")
    @classmethod
    def validate_thread_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("thread description is required")
        return stripped


class OpenAIMemoryExtractionOutput(BaseModel):
    facts: list[OpenAIMemoryFact] = Field(default_factory=list)
    thread_updates: list[OpenAIMemoryThreadUpdate] = Field(default_factory=list)


class OpenAIMemoryExtractionProvider:
    skill_name = "openai_memory_extraction"
    prompt_version = "openai-memory-extraction.v1"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        api_style: OpenAIApiStyle = "responses",
        extra_body: Mapping[str, object] | None = None,
        client: object | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("OpenAI memory extraction model is required.")
        self._model = model
        self._api_style = api_style
        self._extra_body = dict(extra_body or {})
        self.skill_version = f"openai-memory-extraction.{model}"
        self._prompt = load_prompt(self.skill_name, self.prompt_version)
        self._client = client or create_openai_client(api_key, base_url=base_url)
        self._metrics = metrics

    def extract(self, text: str) -> MemoryExtractionResult:
        response, parsed = parse_openai_structured(
            self._client,
            api_style=self._api_style,
            model=self._model,
            messages=_messages(text, self._prompt),
            text_format=OpenAIMemoryExtractionOutput,
            extra_body=self._extra_body,
        )
        record_openai_usage_metrics(
            self._metrics,
            model=self._model,
            skill=self.skill_name,
            usage=getattr(response, "usage", None),
        )
        if not isinstance(parsed, OpenAIMemoryExtractionOutput):
            raise RuntimeError(
                "OpenAI memory extraction response did not match the expected schema."
            )
        return MemoryExtractionResult(
            facts=[
                ExtractedFact(
                    subject_ref=_ref_dict(fact.subject_ref),
                    predicate=fact.predicate,
                    object_ref=_ref_dict(fact.object_ref),
                    risk_level=fact.risk_level,
                )
                for fact in parsed.facts
            ],
            thread_updates=[
                ExtractedThreadUpdate(
                    target_ref=_ref_dict(update.target_ref),
                    update_type=update.update_type,
                    thread_id=update.thread_id,
                    description=update.description,
                    risk_level=update.risk_level,
                )
                for update in parsed.thread_updates
            ],
        )


def _messages(text: str, prompt: PromptDefinition) -> list[dict[str, str]]:
    payload = {"text": text}
    return [
        {
            "role": "system",
            "content": prompt.body,
        },
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]


def _ref_dict(ref: BaseModel) -> dict[str, str]:
    return {
        str(key): str(value).strip()
        for key, value in ref.model_dump(exclude_none=True).items()
        if str(value).strip()
    }
