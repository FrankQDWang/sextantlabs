from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path("backend/scripts/hosted_provider_live_eval_probe.py")


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("hosted_provider_live_eval_probe", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _probe_env(**overrides: str) -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_LLM_PROVIDER": "openai",
        "SEXTANT_LLM_MODEL": "gpt-4.1-mini",
        "SEXTANT_MEMORY_LLM_PROVIDER": "openai",
        "SEXTANT_POV_LLM_PROVIDER": "openai",
        "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER": "openai",
        "SEXTANT_EMBEDDING_PROVIDER": "openai",
        "SEXTANT_EMBEDDING_MODEL": "text-embedding-3-small",
        "SEXTANT_EMBEDDING_DIMENSIONS": "8",
        "SEXTANT_LLM_API_KEY_SECRET_REF": (
            "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY"
        ),
    }
    env.update(overrides)
    return env


def test_hosted_provider_live_eval_config_rejects_non_production_or_local_providers() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_RELEASE_ENVIRONMENT=production"):
        probe.ProviderLiveEvalConfig.from_env({})

    with pytest.raises(probe.ConfigError, match="SEXTANT_LLM_PROVIDER"):
        probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_LLM_PROVIDER="local"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_MEMORY_LLM_PROVIDER"):
        probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_MEMORY_LLM_PROVIDER="local"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_EMBEDDING_PROVIDER"):
        probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_EMBEDDING_PROVIDER="local"))

    with pytest.raises(probe.ConfigError, match="SEXTANT_EMBEDDING_DIMENSIONS"):
        probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_EMBEDDING_DIMENSIONS="0"))

    with pytest.raises(probe.ConfigError, match="provider credential"):
        probe.ProviderLiveEvalConfig.from_env(
            _probe_env(SEXTANT_LLM_API_KEY_SECRET_REF="", SEXTANT_OPENAI_API_KEY="")
        )

    with pytest.raises(probe.ConfigError, match="materialized"):
        probe.ProviderLiveEvalConfig.from_env(
            _probe_env(SEXTANT_LLM_API_KEY_SECRET_REF="secret://openai")
        )

    config = probe.ProviderLiveEvalConfig.from_env(_probe_env())

    assert config.sample_set == "hosted-provider-live-eval.v1"
    assert config.story_model == "gpt-4.1-mini"
    assert config.memory_model == "gpt-4.1-mini"
    assert config.pov_model == "gpt-4.1-mini"
    assert config.event_model == "gpt-4.1-mini"
    assert config.embedding_model == "text-embedding-3-small"
    assert config.embedding_dimensions == 8

    supabase_vault_config = probe.ProviderLiveEvalConfig.from_env(
        _probe_env(
            SEXTANT_LLM_API_KEY_SECRET_REF=(
                "supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key"
            )
        )
    )

    assert supabase_vault_config.credential_source == "supabase-vault"


def test_hosted_provider_live_eval_requires_vault_token_for_vault_secret_ref() -> None:
    probe = _load_probe_module()

    with pytest.raises(probe.ConfigError, match="SEXTANT_VAULT_TOKEN"):
        probe.ProviderLiveEvalConfig.from_env(
            _probe_env(
                SEXTANT_LLM_API_KEY_SECRET_REF=(
                    "vault://vault.example.com/secret/data/sextant/openai?field=OPENAI_API_KEY"
                ),
                SEXTANT_VAULT_TOKEN="",
            )
        )


def test_hosted_provider_live_eval_evidence_is_sanitized_and_requires_all_skills() -> None:
    probe = _load_probe_module()
    config = probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_OPENAI_API_KEY="sk-secret"))
    evaluations = [
        probe.ProviderEvalOutcome(
            skill="story_draft",
            provider="openai",
            model="gpt-4.1-mini",
            status="pass",
            output_shape={"text_length": 42, "review_cue_count": 0},
            output_fingerprint=probe.hash_payload({"text": "Mira secret draft output"}),
        ),
        probe.ProviderEvalOutcome(
            skill="memory_extraction",
            provider="openai",
            model="gpt-4.1-mini",
            status="pass",
            output_shape={"fact_count": 1, "thread_update_count": 1},
            output_fingerprint=probe.hash_payload({"fact": "Mira owns lantern map"}),
        ),
        probe.ProviderEvalOutcome(
            skill="pov_detection",
            provider="openai",
            model="gpt-4.1-mini",
            status="pass",
            output_shape={"pov_mode": "first_person", "evidence_span_count": 1},
            output_fingerprint=probe.hash_payload({"text": "Mira"}),
        ),
        probe.ProviderEvalOutcome(
            skill="event_aggregation",
            provider="openai",
            model="gpt-4.1-mini",
            status="pass",
            output_shape={"decision": "same_event", "evidence_span_count": 2},
            output_fingerprint=probe.hash_payload({"decision": "same_event"}),
        ),
        probe.ProviderEvalOutcome(
            skill="embedding",
            provider="openai",
            model="text-embedding-3-small",
            status="pass",
            output_shape={"vector_count": 1, "dimensions": 8},
            output_fingerprint=probe.hash_payload({"vector": [0.1, 0.2, 0.3]}),
        ),
    ]

    evidence = probe.build_live_eval_evidence(config, evaluations)
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert evidence["sample_set"] == "hosted-provider-live-eval.v1"
    assert len(evidence["evaluations"]) == 5
    assert "sk-secret" not in encoded
    assert "Mira secret draft output" not in encoded
    assert "Mira owns lantern map" not in encoded
    assert all("output_fingerprint" in item for item in evidence["evaluations"])

    with pytest.raises(probe.ProviderLiveEvalError, match="missing provider eval skills"):
        probe.build_live_eval_evidence(config, evaluations[:-1])

    with pytest.raises(probe.ProviderLiveEvalError, match="failed"):
        probe.build_live_eval_evidence(
            config,
            [
                *evaluations[:-1],
                evaluations[-1].__class__(**{**evaluations[-1].__dict__, "status": "fail"}),
            ],
        )


def test_hosted_provider_live_eval_uses_provider_factories_without_exposing_raw_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe_module()
    config = probe.ProviderLiveEvalConfig.from_env(_probe_env(SEXTANT_OPENAI_API_KEY="sk-secret"))

    class StoryProvider:
        def draft(self, request):  # noqa: ANN001
            assert request.actor_intent
            return SimpleNamespace(
                text="Mira writes private provider text.",
                finish_reason="complete",
                structured_output={"mode": "rewrite_span"},
                review_cues=[],
            )

    class MemoryProvider:
        def extract(self, text: str):  # noqa: ANN001
            assert "FACT:" in text
            return SimpleNamespace(facts=[object()], thread_updates=[object()])

    class PovProvider:
        def detect(self, request):  # noqa: ANN001
            assert request.text
            return SimpleNamespace(
                pov_character_name="Mira",
                pov_mode="first_person",
                confidence=0.8,
                evidence_span_ids=[str(request.source_span_id)],
                uncertainty_reason=None,
            )

    class EventProvider:
        def adjudicate(self, request):  # noqa: ANN001
            assert request.existing_event_summary
            return SimpleNamespace(
                decision="same_event",
                confidence=0.75,
                rationale="same transfer",
                evidence_span_ids=[
                    *request.existing_event_evidence_span_ids,
                    *request.candidate_evidence_span_ids,
                ],
            )

    class EmbeddingProvider:
        provider_name = "openai"
        model_name = "text-embedding-3-small"
        dimensions = 8

        def embed_texts(self, texts):  # noqa: ANN001
            assert texts
            return [[0.1] * 8]

    monkeypatch.setattr(
        probe, "story_draft_provider_from_env", lambda metrics=None: StoryProvider()
    )
    monkeypatch.setattr(
        probe,
        "memory_extraction_provider_from_env",
        lambda metrics=None: MemoryProvider(),
    )
    monkeypatch.setattr(
        probe, "pov_detection_provider_from_env", lambda metrics=None: PovProvider()
    )
    monkeypatch.setattr(
        probe,
        "event_aggregation_provider_from_env",
        lambda metrics=None: EventProvider(),
    )
    monkeypatch.setattr(
        probe, "embedding_provider_from_env", lambda metrics=None: EmbeddingProvider()
    )

    evidence = probe.run_live_eval(config)
    encoded = json.dumps(evidence, sort_keys=True)

    assert evidence["status"] == "pass"
    assert {item["skill"] for item in evidence["evaluations"]} == probe.REQUIRED_SKILLS
    assert "Mira writes private provider text" not in encoded
    assert "sk-secret" not in encoded


def test_hosted_provider_live_eval_check_config_cli() -> None:
    valid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    invalid = subprocess.run(
        ["uv", "run", "python", str(SCRIPT_PATH), "--check-config"],
        cwd=Path.cwd(),
        env=_probe_env(SEXTANT_EMBEDDING_PROVIDER="local"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-provider-live-eval-config-ok"
    assert invalid.returncode == 1
    assert "SEXTANT_EMBEDDING_PROVIDER" in invalid.stderr
