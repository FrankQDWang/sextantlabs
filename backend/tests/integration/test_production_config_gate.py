from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_validate_production_config_requires_admin_actor_ids() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    missing_admin = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={key: value for key, value in base_env.items() if key != "SEXTANT_ADMIN_ACTOR_IDS"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_admin = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_ADMIN_ACTOR_IDS": "not-a-uuid"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_admin = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_ADMIN_ACTOR_IDS": "00000000-0000-4000-8000-0000000000aa"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_admin.returncode == 1
    assert "SEXTANT_ADMIN_ACTOR_IDS" in missing_admin.stderr
    assert invalid_admin.returncode == 1
    assert "comma-separated UUID" in invalid_admin.stderr
    assert valid_admin.returncode == 0
    assert valid_admin.stdout.strip() == "production-config-ok"


def test_validate_production_config_rejects_invalid_openai_cost_rates() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    invalid_rate = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS": "not-a-number",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    negative_rate = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS": "-1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_rates = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS": "200",
            "SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS": "800.5",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert invalid_rate.returncode == 1
    assert "SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS" in invalid_rate.stderr
    assert negative_rate.returncode == 1
    assert "SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS" in negative_rate.stderr
    assert valid_rates.returncode == 0
    assert valid_rates.stdout.strip() == "production-config-ok"


def test_validate_production_config_rejects_invalid_secret_ref() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    invalid_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_LLM_API_KEY_SECRET_REF": "prod/openai-api-key"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )
    valid_aws_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": (
                "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_vault_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": (
                "vault://vault.example.com/secret/data/sextant/openai?field=OPENAI_API_KEY"
            ),
            "SEXTANT_VAULT_TOKEN": "vault-token",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_gcp_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": (
                "gcp-secretmanager://story-prod/openai-api-key?version=5"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_supabase_vault_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": (
                "supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_gcp_ref = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": "gcp-secretmanager://story-prod/?version=5",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_vault_token = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_LLM_API_KEY_SECRET_REF": (
                "vault://vault.example.com/secret/data/sextant/openai?field=OPENAI_API_KEY"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert invalid_ref.returncode == 1
    assert "SEXTANT_LLM_API_KEY_SECRET_REF" in invalid_ref.stderr
    assert valid_ref.returncode == 0
    assert valid_ref.stdout.strip() == "production-config-ok"
    assert valid_aws_ref.returncode == 0
    assert valid_aws_ref.stdout.strip() == "production-config-ok"
    assert valid_vault_ref.returncode == 0
    assert valid_vault_ref.stdout.strip() == "production-config-ok"
    assert valid_gcp_ref.returncode == 0
    assert valid_gcp_ref.stdout.strip() == "production-config-ok"
    assert valid_supabase_vault_ref.returncode == 0
    assert valid_supabase_vault_ref.stdout.strip() == "production-config-ok"
    assert invalid_gcp_ref.returncode == 1
    assert "gcp-secretmanager://" in invalid_gcp_ref.stderr
    assert missing_vault_token.returncode == 1
    assert "SEXTANT_VAULT_TOKEN" in missing_vault_token.stderr


def test_validate_production_config_rejects_invalid_event_aggregation_provider() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    invalid_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER": "local"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER": "openai",
            "SEXTANT_EVENT_AGGREGATION_LLM_MODEL": "gpt-5",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert invalid_provider.returncode == 1
    assert "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER" in invalid_provider.stderr
    assert valid_provider.returncode == 0
    assert valid_provider.stdout.strip() == "production-config-ok"


def test_validate_production_config_rejects_invalid_embedding_provider() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    missing_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={key: value for key, value in base_env.items() if key != "SEXTANT_EMBEDDING_PROVIDER"},
        text=True,
        capture_output=True,
        check=False,
    )
    local_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_EMBEDDING_PROVIDER": "local"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_dimensions = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_EMBEDDING_DIMENSIONS": "0"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_provider.returncode == 1
    assert "SEXTANT_EMBEDDING_PROVIDER" in missing_provider.stderr
    assert local_provider.returncode == 1
    assert "SEXTANT_EMBEDDING_PROVIDER" in local_provider.stderr
    assert invalid_dimensions.returncode == 1
    assert "SEXTANT_EMBEDDING_DIMENSIONS" in invalid_dimensions.stderr
    assert valid_provider.returncode == 0
    assert valid_provider.stdout.strip() == "production-config-ok"


def test_validate_production_config_requires_pgvector_index_provider() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    missing_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            key: value for key, value in base_env.items() if key != "SEXTANT_VECTOR_INDEX_PROVIDER"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_VECTOR_INDEX_PROVIDER": "json"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_provider = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_provider.returncode == 1
    assert "SEXTANT_VECTOR_INDEX_PROVIDER" in missing_provider.stderr
    assert invalid_provider.returncode == 1
    assert "SEXTANT_VECTOR_INDEX_PROVIDER" in invalid_provider.stderr
    assert valid_provider.returncode == 0
    assert valid_provider.stdout.strip() == "production-config-ok"


def test_validate_production_config_validates_observability_exporter() -> None:
    script = Path("scripts/validate-production-config.sh")
    base_env = _base_production_env()

    missing_exporter = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            key: value for key, value in base_env.items() if key != "SEXTANT_OBSERVABILITY_EXPORTER"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_exporter = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBSERVABILITY_EXPORTER": "local"},
        text=True,
        capture_output=True,
        check=False,
    )
    missing_endpoint = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBSERVABILITY_EXPORTER": "otlp"},
        text=True,
        capture_output=True,
        check=False,
    )
    insecure_endpoint = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OBSERVABILITY_EXPORTER": "otlp",
            "SEXTANT_OTLP_ENDPOINT": "http://otel.example.com/v1/traces",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_none = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )
    valid_otlp = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OBSERVABILITY_EXPORTER": "otlp",
            "SEXTANT_OTLP_ENDPOINT": "https://otel.example.com/v1/traces",
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_exporter.returncode == 1
    assert "SEXTANT_OBSERVABILITY_EXPORTER" in missing_exporter.stderr
    assert invalid_exporter.returncode == 1
    assert "SEXTANT_OBSERVABILITY_EXPORTER" in invalid_exporter.stderr
    assert missing_endpoint.returncode == 1
    assert "SEXTANT_OTLP_ENDPOINT" in missing_endpoint.stderr
    assert insecure_endpoint.returncode == 1
    assert "SEXTANT_OTLP_ENDPOINT" in insecure_endpoint.stderr
    assert valid_none.returncode == 0
    assert valid_none.stdout.strip() == "production-config-ok"
    assert valid_otlp.returncode == 0
    assert valid_otlp.stdout.strip() == "production-config-ok"


def test_hosted_readiness_gate_records_external_blockers_without_faking_success() -> None:
    script = Path("scripts/validate-hosted-readiness.sh")
    base_env = _base_hosted_readiness_env()

    missing_strict = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={key: value for key, value in base_env.items() if key != "SEXTANT_DEPLOYMENT_URL"},
        text=True,
        capture_output=True,
        check=False,
    )
    missing_allowed = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={key: value for key, value in base_env.items() if key != "SEXTANT_DEPLOYMENT_URL"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_url_allowed = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_EXTERNAL_SMOKE_URL": "http://api.example.com/health"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_local_deployment_url = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_DEPLOYMENT_URL": "https://localhost:8443"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_loopback_metrics_url = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_HOSTED_METRICS_URL": "https://127.0.0.1/metrics"},
        text=True,
        capture_output=True,
        check=False,
    )
    missing_worker_capacity_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_WORKER_CAPACITY_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_deployment_approval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_secret_manager_access_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_provider_live_eval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_pgvector_recall_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_PGVECTOR_RECALL_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_observability_pipeline_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_external_smoke_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_EXTERNAL_SMOKE_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_clean_context_ui_acceptance_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_source_delta_search_reindex_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_object_store_read_write_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_session_provider_provisioning_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_invitation_delivery_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_INVITATION_DELIVERY_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    missing_token_issuer_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value for key, value in base_env.items() if key != "SEXTANT_TOKEN_ISSUER_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_worker_capacity_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_WORKER_CAPACITY_PROOF_REF": "worker-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_deployment_approval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF": "approval-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_secret_manager_access_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF": "secret-access-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_provider_live_eval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF": "eval-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_pgvector_recall_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_PGVECTOR_RECALL_PROOF_REF": "pgvector-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_observability_pipeline_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF": "observability-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_external_smoke_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_EXTERNAL_SMOKE_PROOF_REF": "smoke-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_clean_context_ui_acceptance_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF": "acceptance-ok",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_source_delta_search_reindex_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF": "reindex-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_object_store_read_write_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF": "object-store-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_session_provider_provisioning_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": "session-provider-ok",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_invitation_delivery_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_INVITATION_DELIVERY_PROOF_REF": "delivery-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_worker_capacity_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_WORKER_CAPACITY_PROOF_REF": "https://localhost/worker"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_deployment_approval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF": "https://localhost/deploy-approval",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_secret_manager_access_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF": "https://localhost/secret-access",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_provider_live_eval_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF": "https://localhost/provider-eval",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_pgvector_recall_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_PGVECTOR_RECALL_PROOF_REF": "https://localhost/pgvector-recall",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_observability_pipeline_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF": "https://localhost/observability",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_external_smoke_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_EXTERNAL_SMOKE_PROOF_REF": "https://localhost/external-smoke",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_clean_context_ui_acceptance_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF": ("https://localhost/clean-context-ui"),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_source_delta_search_reindex_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF": "https://localhost/reindex",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_object_store_read_write_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF": "https://localhost/object-store",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_session_provider_provisioning_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": (
                "https://localhost/session-provider"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_invitation_delivery_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_INVITATION_DELIVERY_PROOF_REF": "https://localhost/invitations",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_secret_manager = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_SECRET_MANAGER_REF": "secret://prod/openai-api-key"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_gcp_secret_manager = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_SECRET_MANAGER_REF": "gcp-secretmanager://story-prod/"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_invitation_provider = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_INVITATION_DELIVERY_PROVIDER": "local://dev/invitations"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_token_issuer_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_TOKEN_ISSUER_PROOF_REF": "mock-token-issuer"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_ci_artifact_token_issuer_proof = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_TOKEN_ISSUER_PROOF_REF": "ci-artifact://auth/token-issuer",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_supabase_auth_proof_refs = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": (
                "supabase://ientixxmbdeoqdmkublx/auth"
            ),
            "SEXTANT_TOKEN_ISSUER_PROOF_REF": "supabase://ientixxmbdeoqdmkublx/auth",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_supabase_auth_invitation_delivery_refs = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_INVITATION_DELIVERY_PROVIDER": (
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email"
            ),
            "SEXTANT_INVITATION_DELIVERY_PROOF_REF": (
                "supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/2026-07-01"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_managed_postgres = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_MANAGED_POSTGRES_INSTANCE": "local-postgres"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_object_store_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBJECT_STORE_IAM_PROOF_REF": "iam-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_cloudflare_r2_object_store_proof = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_OBJECT_STORE_IAM_PROOF_REF": (
                "cloudflare-r2://sextant-prod-wnam-objects/runtime-token"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_object_store_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_OBJECT_STORE_IAM_PROOF_REF": "https://localhost/iam"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_backup_restore_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_BACKUP_RESTORE_PROOF_REF": "backup-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_loopback_backup_restore_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_BACKUP_RESTORE_PROOF_REF": "https://127.0.0.1/backup"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_rollback_runbook = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_ROLLBACK_RUNBOOK_REF": "rollback-ok"},
        text=True,
        capture_output=True,
        check=False,
    )
    missing_rollback_execution_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            key: value
            for key, value in base_env.items()
            if key != "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF"
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_rollback_execution_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF": "rollback-executed"},
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_localhost_rollback_execution_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF": "https://localhost/rollback-exec",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    invalid_local_token_issuer_https_proof = subprocess.run(
        ["bash", str(script), "--allow-blocked"],
        cwd=Path.cwd(),
        env={**base_env, "SEXTANT_TOKEN_ISSUER_PROOF_REF": "https://localhost/token"},
        text=True,
        capture_output=True,
        check=False,
    )
    valid_gcp_secret_manager = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SECRET_MANAGER_REF": (
                "gcp-secretmanager://story-prod/openai-api-key?version=latest"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid_supabase_vault_secret_manager = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env={
            **base_env,
            "SEXTANT_SECRET_MANAGER_REF": (
                "supabase-vault://ientixxmbdeoqdmkublx/sextant_openai_api_key"
            ),
            "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF": (
                "runbook://supabase-vault/sextant-openai-api-key"
            ),
        },
        text=True,
        capture_output=True,
        check=False,
    )
    valid = subprocess.run(
        ["bash", str(script)],
        cwd=Path.cwd(),
        env=base_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert missing_strict.returncode == 1
    assert "SEXTANT_DEPLOYMENT_URL" in missing_strict.stderr
    assert missing_allowed.returncode == 0
    assert "hosted-readiness-blocked" in missing_allowed.stdout
    assert "SEXTANT_DEPLOYMENT_URL" in missing_allowed.stdout
    assert invalid_url_allowed.returncode == 1
    assert "SEXTANT_EXTERNAL_SMOKE_URL" in invalid_url_allowed.stderr
    assert invalid_local_deployment_url.returncode == 1
    assert "SEXTANT_DEPLOYMENT_URL" in invalid_local_deployment_url.stderr
    assert invalid_loopback_metrics_url.returncode == 1
    assert "SEXTANT_HOSTED_METRICS_URL" in invalid_loopback_metrics_url.stderr
    assert missing_worker_capacity_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_worker_capacity_proof.stdout
    assert "SEXTANT_WORKER_CAPACITY_PROOF_REF" in missing_worker_capacity_proof.stdout
    assert missing_deployment_approval_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_deployment_approval_proof.stdout
    assert "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF" in missing_deployment_approval_proof.stdout
    assert missing_secret_manager_access_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_secret_manager_access_proof.stdout
    assert "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF" in missing_secret_manager_access_proof.stdout
    assert missing_provider_live_eval_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_provider_live_eval_proof.stdout
    assert "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF" in missing_provider_live_eval_proof.stdout
    assert missing_pgvector_recall_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_pgvector_recall_proof.stdout
    assert "SEXTANT_PGVECTOR_RECALL_PROOF_REF" in missing_pgvector_recall_proof.stdout
    assert missing_observability_pipeline_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_observability_pipeline_proof.stdout
    assert "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF" in missing_observability_pipeline_proof.stdout
    assert missing_external_smoke_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_external_smoke_proof.stdout
    assert "SEXTANT_EXTERNAL_SMOKE_PROOF_REF" in missing_external_smoke_proof.stdout
    assert missing_clean_context_ui_acceptance_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_clean_context_ui_acceptance_proof.stdout
    assert (
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF"
        in missing_clean_context_ui_acceptance_proof.stdout
    )
    assert missing_source_delta_search_reindex_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_source_delta_search_reindex_proof.stdout
    assert (
        "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF"
        in missing_source_delta_search_reindex_proof.stdout
    )
    assert missing_object_store_read_write_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_object_store_read_write_proof.stdout
    assert (
        "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF" in missing_object_store_read_write_proof.stdout
    )
    assert missing_session_provider_provisioning_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_session_provider_provisioning_proof.stdout
    assert (
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF"
        in missing_session_provider_provisioning_proof.stdout
    )
    assert missing_invitation_delivery_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_invitation_delivery_proof.stdout
    assert "SEXTANT_INVITATION_DELIVERY_PROOF_REF" in missing_invitation_delivery_proof.stdout
    assert invalid_worker_capacity_proof.returncode == 1
    assert "SEXTANT_WORKER_CAPACITY_PROOF_REF" in invalid_worker_capacity_proof.stderr
    assert invalid_deployment_approval_proof.returncode == 1
    assert "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF" in invalid_deployment_approval_proof.stderr
    assert invalid_secret_manager_access_proof.returncode == 1
    assert "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF" in invalid_secret_manager_access_proof.stderr
    assert invalid_provider_live_eval_proof.returncode == 1
    assert "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF" in invalid_provider_live_eval_proof.stderr
    assert invalid_pgvector_recall_proof.returncode == 1
    assert "SEXTANT_PGVECTOR_RECALL_PROOF_REF" in invalid_pgvector_recall_proof.stderr
    assert invalid_observability_pipeline_proof.returncode == 1
    assert "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF" in invalid_observability_pipeline_proof.stderr
    assert invalid_external_smoke_proof.returncode == 1
    assert "SEXTANT_EXTERNAL_SMOKE_PROOF_REF" in invalid_external_smoke_proof.stderr
    assert invalid_clean_context_ui_acceptance_proof.returncode == 1
    assert (
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF"
        in invalid_clean_context_ui_acceptance_proof.stderr
    )
    assert invalid_source_delta_search_reindex_proof.returncode == 1
    assert (
        "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF"
        in invalid_source_delta_search_reindex_proof.stderr
    )
    assert invalid_object_store_read_write_proof.returncode == 1
    assert (
        "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF" in invalid_object_store_read_write_proof.stderr
    )
    assert invalid_session_provider_provisioning_proof.returncode == 1
    assert (
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF"
        in invalid_session_provider_provisioning_proof.stderr
    )
    assert invalid_invitation_delivery_proof.returncode == 1
    assert "SEXTANT_INVITATION_DELIVERY_PROOF_REF" in invalid_invitation_delivery_proof.stderr
    assert invalid_localhost_worker_capacity_proof.returncode == 1
    assert "SEXTANT_WORKER_CAPACITY_PROOF_REF" in invalid_localhost_worker_capacity_proof.stderr
    assert invalid_localhost_deployment_approval_proof.returncode == 1
    assert (
        "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF"
        in invalid_localhost_deployment_approval_proof.stderr
    )
    assert invalid_localhost_secret_manager_access_proof.returncode == 1
    assert (
        "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF"
        in invalid_localhost_secret_manager_access_proof.stderr
    )
    assert invalid_localhost_provider_live_eval_proof.returncode == 1
    assert (
        "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF" in invalid_localhost_provider_live_eval_proof.stderr
    )
    assert invalid_localhost_pgvector_recall_proof.returncode == 1
    assert "SEXTANT_PGVECTOR_RECALL_PROOF_REF" in invalid_localhost_pgvector_recall_proof.stderr
    assert invalid_localhost_observability_pipeline_proof.returncode == 1
    assert (
        "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF"
        in invalid_localhost_observability_pipeline_proof.stderr
    )
    assert invalid_localhost_external_smoke_proof.returncode == 1
    assert "SEXTANT_EXTERNAL_SMOKE_PROOF_REF" in invalid_localhost_external_smoke_proof.stderr
    assert invalid_localhost_clean_context_ui_acceptance_proof.returncode == 1
    assert (
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF"
        in invalid_localhost_clean_context_ui_acceptance_proof.stderr
    )
    assert invalid_localhost_source_delta_search_reindex_proof.returncode == 1
    assert (
        "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF"
        in invalid_localhost_source_delta_search_reindex_proof.stderr
    )
    assert invalid_localhost_object_store_read_write_proof.returncode == 1
    assert (
        "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF"
        in invalid_localhost_object_store_read_write_proof.stderr
    )
    assert invalid_localhost_session_provider_provisioning_proof.returncode == 1
    assert (
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF"
        in invalid_localhost_session_provider_provisioning_proof.stderr
    )
    assert invalid_localhost_invitation_delivery_proof.returncode == 1
    assert (
        "SEXTANT_INVITATION_DELIVERY_PROOF_REF"
        in invalid_localhost_invitation_delivery_proof.stderr
    )
    assert invalid_secret_manager.returncode == 1
    assert "SEXTANT_SECRET_MANAGER_REF" in invalid_secret_manager.stderr
    assert invalid_gcp_secret_manager.returncode == 1
    assert "gcp-secretmanager://" in invalid_gcp_secret_manager.stderr
    assert invalid_invitation_provider.returncode == 1
    assert "SEXTANT_INVITATION_DELIVERY_PROVIDER" in invalid_invitation_provider.stderr
    assert missing_token_issuer_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_token_issuer_proof.stdout
    assert "SEXTANT_TOKEN_ISSUER_PROOF_REF" in missing_token_issuer_proof.stdout
    assert invalid_token_issuer_proof.returncode == 1
    assert "SEXTANT_TOKEN_ISSUER_PROOF_REF" in invalid_token_issuer_proof.stderr
    assert invalid_managed_postgres.returncode == 1
    assert "SEXTANT_MANAGED_POSTGRES_INSTANCE" in invalid_managed_postgres.stderr
    assert invalid_object_store_proof.returncode == 1
    assert "SEXTANT_OBJECT_STORE_IAM_PROOF_REF" in invalid_object_store_proof.stderr
    assert valid_cloudflare_r2_object_store_proof.returncode == 0
    assert valid_cloudflare_r2_object_store_proof.stdout.strip() == "hosted-readiness-config-ok"
    assert invalid_localhost_object_store_proof.returncode == 1
    assert "SEXTANT_OBJECT_STORE_IAM_PROOF_REF" in invalid_localhost_object_store_proof.stderr
    assert invalid_backup_restore_proof.returncode == 1
    assert "SEXTANT_BACKUP_RESTORE_PROOF_REF" in invalid_backup_restore_proof.stderr
    assert invalid_loopback_backup_restore_proof.returncode == 1
    assert "SEXTANT_BACKUP_RESTORE_PROOF_REF" in invalid_loopback_backup_restore_proof.stderr
    assert invalid_rollback_runbook.returncode == 1
    assert "SEXTANT_ROLLBACK_RUNBOOK_REF" in invalid_rollback_runbook.stderr
    assert missing_rollback_execution_proof.returncode == 0
    assert "hosted-readiness-blocked" in missing_rollback_execution_proof.stdout
    assert "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF" in missing_rollback_execution_proof.stdout
    assert invalid_rollback_execution_proof.returncode == 1
    assert "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF" in invalid_rollback_execution_proof.stderr
    assert invalid_localhost_rollback_execution_proof.returncode == 1
    assert (
        "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF" in invalid_localhost_rollback_execution_proof.stderr
    )
    assert invalid_local_token_issuer_https_proof.returncode == 1
    assert "SEXTANT_TOKEN_ISSUER_PROOF_REF" in invalid_local_token_issuer_https_proof.stderr
    assert valid_ci_artifact_token_issuer_proof.returncode == 0
    assert valid_ci_artifact_token_issuer_proof.stdout.strip() == "hosted-readiness-config-ok"
    assert valid_supabase_auth_proof_refs.returncode == 0
    assert valid_supabase_auth_proof_refs.stdout.strip() == "hosted-readiness-config-ok"
    assert valid_supabase_auth_invitation_delivery_refs.returncode == 0
    assert (
        valid_supabase_auth_invitation_delivery_refs.stdout.strip() == "hosted-readiness-config-ok"
    )
    assert valid_gcp_secret_manager.returncode == 0
    assert valid_gcp_secret_manager.stdout.strip() == "hosted-readiness-config-ok"
    assert valid_supabase_vault_secret_manager.returncode == 0
    assert valid_supabase_vault_secret_manager.stdout.strip() == "hosted-readiness-config-ok"
    assert valid.returncode == 0
    assert valid.stdout.strip() == "hosted-readiness-config-ok"


def test_hosted_readiness_gate_rejects_secret_bearing_proof_refs() -> None:
    script = Path("scripts/validate-hosted-readiness.sh")
    base_env = _base_hosted_readiness_env()

    cases = {
        "SEXTANT_EXTERNAL_SMOKE_PROOF_REF": "https://ci.example.com/external-smoke?token=secret",
        "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF": ("github-run://user:secret@release/prod/deploy"),
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF": (
            "ci-artifact://clean-context-ui/2026-06-12#secret"
        ),
        "SEXTANT_ROLLBACK_RUNBOOK_REF": "https://ci.example.com/rollback;secret",
    }

    for env_name, secret_bearing_ref in cases.items():
        result = subprocess.run(
            ["bash", str(script), "--allow-blocked"],
            cwd=Path.cwd(),
            env={**base_env, env_name: secret_bearing_ref},
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 1
        assert env_name in result.stderr
        assert "userinfo, params, query strings, or fragments" in result.stderr
        assert "secret" not in result.stderr
        assert "secret" not in result.stdout


def _base_production_env() -> dict[str, str]:
    env = {
        **os.environ,
        "SEXTANT_DATABASE_URL": "postgresql://sextant:sextant@db.example.com:5432/sextant",
        "SEXTANT_AUTH_MODE": "jwt-jwks",
        "SEXTANT_SESSION_ISSUER": "https://auth.example.com/",
        "SEXTANT_SESSION_AUDIENCE": "sextant-api",
        "SEXTANT_SESSION_JWKS_URL": "https://auth.example.com/.well-known/jwks.json",
        "SEXTANT_ADMIN_ACTOR_IDS": "00000000-0000-4000-8000-0000000000aa",
        "SEXTANT_CORS_ORIGINS": "https://app.example.com",
        "SEXTANT_RELEASE_ENVIRONMENT": "production",
        "SEXTANT_LLM_PROVIDER": "openai",
        "SEXTANT_LLM_MODEL": "gpt-5",
        "SEXTANT_LLM_API_KEY_SECRET_REF": "secret://prod/openai-api-key",
        "SEXTANT_EMBEDDING_PROVIDER": "openai",
        "SEXTANT_EMBEDDING_MODEL": "text-embedding-3-small",
        "SEXTANT_EMBEDDING_DIMENSIONS": "1536",
        "SEXTANT_VECTOR_INDEX_PROVIDER": "pgvector",
        "SEXTANT_OBJECT_STORE_ROOT": "s3://sextant-prod-objects/source",
        "SEXTANT_BACKUP_TARGET": "s3://sextant-prod-backups",
        "SEXTANT_OBSERVABILITY_EXPORTER": "none",
    }
    env.pop("OPENAI_API_KEY", None)
    env.pop("SEXTANT_OPENAI_API_KEY", None)
    return env


def _base_hosted_readiness_env() -> dict[str, str]:
    return {
        **_base_production_env(),
        "SEXTANT_DEPLOYMENT_URL": "https://api.example.com",
        "SEXTANT_DEPLOYMENT_VERSION": "2026.06.12+abcdef",
        "SEXTANT_MANAGED_POSTGRES_INSTANCE": "rds://prod/sextant",
        "SEXTANT_OBJECT_STORE_IAM_PROOF_REF": "runbook://iam/sextant-prod-objects",
        "SEXTANT_SECRET_MANAGER_REF": (
            "aws-secretsmanager://us-east-1/prod/sextant/openai?json_key=OPENAI_API_KEY"
        ),
        "SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF": "aws-iam://prod/sextant-secret-access",
        "SEXTANT_SESSION_PROVIDER_ADMIN_URL": "https://auth.example.com/admin",
        "SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF": (
            "auth0://prod/sextant/session-provider"
        ),
        "SEXTANT_INVITATION_DELIVERY_PROVIDER": "ses://prod/invitations",
        "SEXTANT_INVITATION_DELIVERY_PROOF_REF": "ci-artifact://invitations/2026-06-12",
        "SEXTANT_TOKEN_ISSUER_PROOF_REF": "runbook://auth/token-issuer",
        "SEXTANT_HOSTED_METRICS_URL": "https://metrics.example.com/sextant",
        "SEXTANT_HOSTED_TRACES_URL": "https://traces.example.com/sextant",
        "SEXTANT_ALERTING_DASHBOARD_URL": "https://alerts.example.com/sextant",
        "SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF": "ci-artifact://observability/2026-06-12",
        "SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF": "change-request://prod/sextant/2026-06-12",
        "SEXTANT_WORKER_CAPACITY_PROOF_REF": "runbook://worker/capacity/2026-06-12",
        "SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF": "ci-artifact://provider-evals/2026-06-12",
        "SEXTANT_PGVECTOR_RECALL_PROOF_REF": "ci-artifact://pgvector-recall/2026-06-12",
        "SEXTANT_BACKUP_RESTORE_PROOF_REF": "runbook://backup/restore/2026-06-12",
        "SEXTANT_ROLLBACK_RUNBOOK_REF": "runbook://release/rollback/2026-06-12",
        "SEXTANT_ROLLBACK_EXECUTION_PROOF_REF": ("ci-artifact://rollback-drill/2026-06-12"),
        "SEXTANT_EXTERNAL_SMOKE_URL": "https://api.example.com/health",
        "SEXTANT_EXTERNAL_SMOKE_PROOF_REF": "ci-artifact://external-smoke/2026-06-12",
        "SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF": (
            "ci-artifact://clean-context-ui/2026-06-12"
        ),
        "SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF": (
            "ci-artifact://source-delta-search-reindex/2026-06-12"
        ),
        "SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF": (
            "ci-artifact://object-store-read-write/2026-06-12"
        ),
    }
