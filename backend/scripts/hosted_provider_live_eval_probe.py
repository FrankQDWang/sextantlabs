from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sextant.common.observability import MetricsRegistry
from sextant.contracts.event_aggregation import EventAggregationAdjudicationRequest
from sextant.contracts.pov_detection import PovDetectionMention, PovDetectionRequest
from sextant.contracts.story_draft import StoryDraftRequest
from sextant.contracts.use_cases import WritingContextPackOutput
from sextant.infra.embedding_provider import embedding_provider_from_env
from sextant.infra.event_aggregation_provider import event_aggregation_provider_from_env
from sextant.infra.memory_extraction_provider import memory_extraction_provider_from_env
from sextant.infra.pov_detection_provider import pov_detection_provider_from_env
from sextant.infra.story_draft_provider import story_draft_provider_from_env


class ConfigError(RuntimeError):
    pass


class ProviderLiveEvalError(RuntimeError):
    pass


REQUIRED_SKILLS = {
    "story_draft",
    "memory_extraction",
    "pov_detection",
    "event_aggregation",
    "embedding",
}
LOCAL_PROVIDER_VALUES = {"local", "local-deterministic"}
SUPPORTED_SECRET_REF_PREFIXES = (
    "aws-secretsmanager://",
    "gcp-secretmanager://",
    "supabase-vault://",
    "vault://",
)


@dataclass(frozen=True)
class ProviderLiveEvalConfig:
    sample_set: str
    story_provider: str
    story_model: str
    memory_provider: str
    memory_model: str
    pov_provider: str
    pov_model: str
    event_provider: str
    event_model: str
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    credential_source: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ProviderLiveEvalConfig:
        release_environment = env.get("SEXTANT_RELEASE_ENVIRONMENT", "").strip()
        if release_environment != "production":
            raise ConfigError(
                "SEXTANT_RELEASE_ENVIRONMENT=production is required for hosted "
                "provider live eval proof."
            )
        story_provider = _openai_provider(env, "SEXTANT_LLM_PROVIDER")
        story_model = _required(env, "SEXTANT_LLM_MODEL")
        return cls(
            sample_set=env.get(
                "SEXTANT_PROVIDER_LIVE_EVAL_SAMPLE_SET",
                "hosted-provider-live-eval.v1",
            ).strip()
            or "hosted-provider-live-eval.v1",
            story_provider=story_provider,
            story_model=story_model,
            memory_provider=_openai_provider(
                env,
                "SEXTANT_MEMORY_LLM_PROVIDER",
                fallback_name="SEXTANT_LLM_PROVIDER",
            ),
            memory_model=_model_from_env(
                env,
                "SEXTANT_MEMORY_LLM_MODEL",
                fallback_name="SEXTANT_LLM_MODEL",
            ),
            pov_provider=_openai_provider(
                env,
                "SEXTANT_POV_LLM_PROVIDER",
                fallback_name="SEXTANT_LLM_PROVIDER",
            ),
            pov_model=_model_from_env(
                env,
                "SEXTANT_POV_LLM_MODEL",
                fallback_name="SEXTANT_LLM_MODEL",
            ),
            event_provider=_openai_provider(
                env,
                "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER",
                fallback_name="SEXTANT_LLM_PROVIDER",
            ),
            event_model=_model_from_env(
                env,
                "SEXTANT_EVENT_AGGREGATION_LLM_MODEL",
                fallback_name="SEXTANT_LLM_MODEL",
            ),
            embedding_provider=_openai_provider(env, "SEXTANT_EMBEDDING_PROVIDER"),
            embedding_model=_required(env, "SEXTANT_EMBEDDING_MODEL"),
            embedding_dimensions=_positive_int(
                env.get("SEXTANT_EMBEDDING_DIMENSIONS", ""),
                "SEXTANT_EMBEDDING_DIMENSIONS",
            ),
            credential_source=_credential_source(env),
        )


@dataclass(frozen=True)
class ProviderEvalOutcome:
    skill: str
    provider: str
    model: str
    status: str
    output_shape: dict[str, object]
    output_fingerprint: str


def run_live_eval(config: ProviderLiveEvalConfig) -> dict[str, object]:
    metrics = MetricsRegistry()
    outcomes = [
        _evaluate_story_draft(story_draft_provider_from_env(metrics), config),
        _evaluate_memory_extraction(memory_extraction_provider_from_env(metrics), config),
        _evaluate_pov_detection(pov_detection_provider_from_env(metrics), config),
        _evaluate_event_aggregation(event_aggregation_provider_from_env(metrics), config),
        _evaluate_embedding(embedding_provider_from_env(metrics), config),
    ]
    return build_live_eval_evidence(config, outcomes)


def build_live_eval_evidence(
    config: ProviderLiveEvalConfig,
    evaluations: list[ProviderEvalOutcome],
) -> dict[str, object]:
    skills = {evaluation.skill for evaluation in evaluations}
    missing = REQUIRED_SKILLS - skills
    if missing:
        raise ProviderLiveEvalError(
            "Hosted provider live eval is missing provider eval skills: "
            + ", ".join(sorted(missing))
        )
    failed = [evaluation.skill for evaluation in evaluations if evaluation.status != "pass"]
    if failed:
        raise ProviderLiveEvalError(
            "Hosted provider live eval failed for: " + ", ".join(sorted(failed))
        )
    return {
        "status": "pass",
        "sample_set": config.sample_set,
        "provider": "openai",
        "credential_source": config.credential_source,
        "evaluations": [
            {
                "skill": evaluation.skill,
                "provider": evaluation.provider,
                "model": evaluation.model,
                "status": evaluation.status,
                "output_shape": evaluation.output_shape,
                "output_fingerprint": evaluation.output_fingerprint,
            }
            for evaluation in sorted(evaluations, key=lambda item: item.skill)
        ],
    }


def _evaluate_story_draft(provider: Any, config: ProviderLiveEvalConfig) -> ProviderEvalOutcome:
    try:
        result = provider.draft(_story_draft_request())
    except Exception as exc:
        raise ProviderLiveEvalError("story_draft live provider eval failed.") from exc
    text = str(getattr(result, "text", ""))
    if not text.strip():
        raise ProviderLiveEvalError("story_draft live provider eval returned empty text.")
    finish_reason = str(getattr(result, "finish_reason", ""))
    review_cues = list(getattr(result, "review_cues", []) or [])
    structured_output = getattr(result, "structured_output", {}) or {}
    if not isinstance(structured_output, dict):
        raise ProviderLiveEvalError("story_draft live provider eval returned invalid structure.")
    return ProviderEvalOutcome(
        skill="story_draft",
        provider=config.story_provider,
        model=config.story_model,
        status="pass",
        output_shape={
            "text_length": len(text),
            "finish_reason": finish_reason,
            "review_cue_count": len(review_cues),
            "structured_keys": sorted(str(key) for key in structured_output),
        },
        output_fingerprint=hash_payload(
            {
                "text": text,
                "finish_reason": finish_reason,
                "structured_output": structured_output,
                "review_cues": review_cues,
            }
        ),
    )


def _evaluate_memory_extraction(
    provider: Any,
    config: ProviderLiveEvalConfig,
) -> ProviderEvalOutcome:
    source_text = (
        "FACT: character:mira | owns | object:lantern-map | low\n"
        "THREAD: character:mira | opens | map-origin | "
        "The lantern map origin remains unresolved. | low"
    )
    try:
        result = provider.extract(source_text)
    except Exception as exc:
        raise ProviderLiveEvalError("memory_extraction live provider eval failed.") from exc
    facts = list(getattr(result, "facts", []) or [])
    thread_updates = list(getattr(result, "thread_updates", []) or [])
    return ProviderEvalOutcome(
        skill="memory_extraction",
        provider=config.memory_provider,
        model=config.memory_model,
        status="pass",
        output_shape={
            "fact_count": len(facts),
            "thread_update_count": len(thread_updates),
        },
        output_fingerprint=hash_payload(
            {
                "fact_count": len(facts),
                "thread_update_count": len(thread_updates),
                "facts": [_safe_repr(item) for item in facts],
                "thread_updates": [_safe_repr(item) for item in thread_updates],
            }
        ),
    )


def _evaluate_pov_detection(provider: Any, config: ProviderLiveEvalConfig) -> ProviderEvalOutcome:
    request = _pov_detection_request()
    try:
        result = provider.detect(request)
    except Exception as exc:
        raise ProviderLiveEvalError("pov_detection live provider eval failed.") from exc
    confidence = float(getattr(result, "confidence", -1))
    if confidence < 0 or confidence > 1:
        raise ProviderLiveEvalError("pov_detection live provider eval returned invalid confidence.")
    pov_mode = str(getattr(result, "pov_mode", ""))
    evidence_span_ids = list(getattr(result, "evidence_span_ids", []) or [])
    return ProviderEvalOutcome(
        skill="pov_detection",
        provider=config.pov_provider,
        model=config.pov_model,
        status="pass",
        output_shape={
            "pov_mode": pov_mode,
            "confidence": confidence,
            "evidence_span_count": len(evidence_span_ids),
            "has_uncertainty_reason": bool(getattr(result, "uncertainty_reason", None)),
        },
        output_fingerprint=hash_payload(
            {
                "pov_character_name": getattr(result, "pov_character_name", None),
                "pov_mode": pov_mode,
                "confidence": confidence,
                "evidence_span_ids": evidence_span_ids,
                "uncertainty_reason": getattr(result, "uncertainty_reason", None),
            }
        ),
    )


def _evaluate_event_aggregation(
    provider: Any,
    config: ProviderLiveEvalConfig,
) -> ProviderEvalOutcome:
    request = _event_aggregation_request()
    try:
        result = provider.adjudicate(request)
    except Exception as exc:
        raise ProviderLiveEvalError("event_aggregation live provider eval failed.") from exc
    decision = str(getattr(result, "decision", ""))
    if decision not in {"same_event", "related_but_distinct", "conflict_version", "uncertain"}:
        raise ProviderLiveEvalError(
            "event_aggregation live provider eval returned invalid decision."
        )
    confidence = float(getattr(result, "confidence", -1))
    if confidence < 0 or confidence > 1:
        raise ProviderLiveEvalError(
            "event_aggregation live provider eval returned invalid confidence."
        )
    evidence_span_ids = list(getattr(result, "evidence_span_ids", []) or [])
    return ProviderEvalOutcome(
        skill="event_aggregation",
        provider=config.event_provider,
        model=config.event_model,
        status="pass",
        output_shape={
            "decision": decision,
            "confidence": confidence,
            "evidence_span_count": len(evidence_span_ids),
        },
        output_fingerprint=hash_payload(
            {
                "decision": decision,
                "confidence": confidence,
                "rationale": getattr(result, "rationale", ""),
                "evidence_span_ids": evidence_span_ids,
            }
        ),
    )


def _evaluate_embedding(provider: Any, config: ProviderLiveEvalConfig) -> ProviderEvalOutcome:
    try:
        vectors = provider.embed_texts(["Sextant hosted provider live eval probe."])
    except Exception as exc:
        raise ProviderLiveEvalError("embedding live provider eval failed.") from exc
    if len(vectors) != 1:
        raise ProviderLiveEvalError("embedding live provider eval did not return one vector.")
    vector = vectors[0]
    if len(vector) != config.embedding_dimensions:
        raise ProviderLiveEvalError(
            "embedding live provider eval returned "
            f"{len(vector)} dimensions; expected {config.embedding_dimensions}."
        )
    return ProviderEvalOutcome(
        skill="embedding",
        provider=config.embedding_provider,
        model=config.embedding_model,
        status="pass",
        output_shape={"vector_count": len(vectors), "dimensions": len(vector)},
        output_fingerprint=hash_payload({"vector": vector}),
    )


def _story_draft_request() -> StoryDraftRequest:
    return StoryDraftRequest(
        actor_intent="Rewrite the selected sentence with restrained, local scene motion.",
        current_text_window="Mira paused at the archive door.",
        context_pack=WritingContextPackOutput(
            context_pack_id=uuid4(),
            schema_version="writing-context-pack.v1",
            current_position={"mode": "rewrite_span"},
            canonical_context={"facts": []},
            pov_constraint={"forbidden_knowledge": []},
            active_characters=[],
            character_agency_state={"status": "not_computed"},
            recent_events=[],
            character_knowledge=[],
            object_location_state=[],
            open_threads=[],
            risk_context={"facts": []},
            style_memory={"samples": []},
            evidence_refs=[],
        ),
        prose_rendering_contract={
            "mode": "rewrite_span",
            "contract_id": "hosted-provider-live-eval",
            "new_character_policy": "avoid",
            "target_position": {"start": 0, "end": 34},
        },
    )


def _pov_detection_request() -> PovDetectionRequest:
    source_span_id = uuid4()
    return PovDetectionRequest(
        source_span_id=source_span_id,
        scene_id=uuid4(),
        text='Mira said, "I can only see the archive door."',
        mentions=[
            PovDetectionMention(
                raw_text="Mira",
                mention_type="character",
                canonical_entity_id=str(UUID("11111111-1111-4111-8111-111111111111")),
            )
        ],
    )


def _event_aggregation_request() -> EventAggregationAdjudicationRequest:
    existing_span_id = uuid4()
    candidate_span_id = uuid4()
    return EventAggregationAdjudicationRequest(
        existing_event_id=uuid4(),
        existing_event_type="object_transfer",
        existing_event_title="Mira handed Kestrel the Lantern Map",
        existing_event_summary="Mira handed Kestrel the Lantern Map.",
        existing_event_participants=[
            {"type": "character", "id": "mira", "label": "Mira"},
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
        ],
        existing_event_objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        existing_event_evidence_span_ids=[str(existing_span_id)],
        existing_event_source_text="Mira handed Kestrel the Lantern Map.",
        candidate_id=uuid4(),
        candidate_event_type="object_transfer",
        candidate_summary="Kestrel received the Lantern Map from Mira.",
        candidate_participants=[
            {"type": "character", "id": "kestrel", "label": "Kestrel"},
            {"type": "character", "id": "mira", "label": "Mira"},
        ],
        candidate_objects=[{"type": "object", "id": "lantern-map", "label": "Lantern Map"}],
        candidate_evidence_span_ids=[str(candidate_span_id)],
        candidate_source_text="Kestrel received the Lantern Map from Mira.",
    )


def hash_payload(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _safe_repr(value: object) -> str:
    return repr(value)


def _openai_provider(
    env: Mapping[str, str],
    name: str,
    *,
    fallback_name: str | None = None,
) -> str:
    value = env.get(name, "").strip().lower()
    if not value and fallback_name is not None:
        value = env.get(fallback_name, "").strip().lower()
    if not value:
        raise ConfigError(f"{name} is required.")
    if value in LOCAL_PROVIDER_VALUES:
        raise ConfigError(f"{name} must be openai for hosted provider live eval.")
    if value != "openai":
        raise ConfigError(f"{name} must be openai for hosted provider live eval.")
    return value


def _model_from_env(env: Mapping[str, str], name: str, *, fallback_name: str) -> str:
    value = env.get(name, "").strip() or env.get(fallback_name, "").strip()
    if not value:
        raise ConfigError(f"{name} or {fallback_name} is required.")
    return value


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required.")
    return value


def _positive_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _credential_source(env: Mapping[str, str]) -> str:
    if env.get("SEXTANT_OPENAI_API_KEY", "").strip() or env.get("OPENAI_API_KEY", "").strip():
        return "environment"
    secret_ref = env.get("SEXTANT_LLM_API_KEY_SECRET_REF", "").strip()
    if not secret_ref:
        raise ConfigError(
            "A hosted provider credential is required: set SEXTANT_OPENAI_API_KEY, "
            "OPENAI_API_KEY, or SEXTANT_LLM_API_KEY_SECRET_REF."
        )
    if secret_ref.startswith("secret://"):
        raise ConfigError(
            "SEXTANT_LLM_API_KEY_SECRET_REF=secret://... must be materialized before "
            "hosted provider live eval."
        )
    if not secret_ref.startswith(SUPPORTED_SECRET_REF_PREFIXES):
        raise ConfigError(
            "SEXTANT_LLM_API_KEY_SECRET_REF must use aws-secretsmanager://, "
            "gcp-secretmanager://, vault://, or supabase-vault:// for hosted "
            "provider live eval."
        )
    if secret_ref.startswith("vault://") and not env.get("SEXTANT_VAULT_TOKEN", "").strip():
        raise ConfigError("vault:// provider credentials require SEXTANT_VAULT_TOKEN.")
    return secret_ref.split("://", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run hosted live provider evals against production OpenAI provider adapters "
            "and emit sanitized JSON proof evidence."
        )
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate hosted provider live-eval configuration without provider calls.",
    )
    args = parser.parse_args()
    try:
        config = ProviderLiveEvalConfig.from_env(os.environ)
        if args.check_config:
            print("hosted-provider-live-eval-config-ok")
            return 0
        print(json.dumps(run_live_eval(config), sort_keys=True))
        return 0
    except (ConfigError, ProviderLiveEvalError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
