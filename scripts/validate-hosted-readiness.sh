#!/usr/bin/env bash
set -euo pipefail

allow_blocked=0
if [[ "${1:-}" == "--allow-blocked" ]]; then
  allow_blocked=1
  shift
fi

if (( $# > 0 )); then
  echo "Usage: bash scripts/validate-hosted-readiness.sh [--allow-blocked]" >&2
  exit 2
fi

missing=()
invalid=()

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
}

require_https_url() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" && "$value" != https://* ]]; then
    invalid+=("$name must be an HTTPS URL.")
    return
  fi
  if [[ -n "$value" ]] && ! validate_hosted_https_value "$name" "$value"; then
    invalid+=("$name must be a hosted HTTPS URL, not localhost, .local, loopback, link-local, or unspecified.")
  fi
}

validate_hosted_https_value() {
  local name="$1"
  local value="$2"
  HOSTED_URL_NAME="$name" HOSTED_URL_VALUE="$value" python3 - <<'PY'
import ipaddress
import os
from urllib.parse import urlparse

name = os.environ["HOSTED_URL_NAME"]
value = os.environ["HOSTED_URL_VALUE"]
parsed = urlparse(value)
host = (parsed.hostname or "").strip().rstrip(".").lower()
if not host:
    raise SystemExit(1)
if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
    raise SystemExit(1)
try:
    address = ipaddress.ip_address(host)
except ValueError:
    raise SystemExit(0)
if address.is_loopback or address.is_link_local or address.is_unspecified:
    raise SystemExit(1)
PY
}

reject_local_https_ref() {
  local name="$1"
  local value="$2"
  if [[ -n "$value" && "$value" == https://* ]] && ! validate_hosted_https_value "$name" "$value"; then
    invalid+=("$name HTTPS refs must not use localhost, .local, loopback, link-local, or unspecified hosts.")
  fi
}

reject_secret_bearing_ref_parts() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    return
  fi
  if ! HOSTED_REF_VALUE="$value" python3 - <<'PY'
import os
from urllib.parse import urlparse

parsed = urlparse(os.environ["HOSTED_REF_VALUE"])
if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
    raise SystemExit(1)
PY
  then
    invalid+=("$name must not include URL userinfo, params, query strings, or fragments.")
  fi
}

require_s3_uri() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" && "$value" != s3://* ]]; then
    invalid+=("$name must be an s3:// URI.")
  fi
}

require_postgres_url() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "$value" && "$value" != postgresql* ]]; then
    invalid+=("$name must be a PostgreSQL URL.")
  fi
}

require_managed_postgres_instance() {
  local value="${SEXTANT_MANAGED_POSTGRES_INSTANCE:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  case "$value" in
    rds://?*|cloudsql://?*|azure-postgres://?*|neon://?*|supabase://?*|crunchy-postgres://?*) ;;
    *)
      invalid+=("SEXTANT_MANAGED_POSTGRES_INSTANCE must be rds://, cloudsql://, azure-postgres://, neon://, supabase://, or crunchy-postgres:// with a non-empty target.")
      ;;
  esac
}

require_object_store_iam_proof_ref() {
  local value="${SEXTANT_OBJECT_STORE_IAM_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_OBJECT_STORE_IAM_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_OBJECT_STORE_IAM_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|aws-iam://?*|gcp-iam://?*|azure-rbac://?*|cloudflare-r2://?*) ;;
    *)
      invalid+=("SEXTANT_OBJECT_STORE_IAM_PROOF_REF must be runbook://, https://, aws-iam://, gcp-iam://, azure-rbac://, or cloudflare-r2:// with a non-empty target.")
      ;;
  esac
}

require_object_store_read_write_proof_ref() {
  local value="${SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|s3://?*|gs://?*|azure-blob://?*) ;;
    *)
      invalid+=("SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF must be runbook://, https://, ci-artifact://, s3://, gs://, or azure-blob:// with a non-empty target.")
      ;;
  esac
}

require_backup_restore_proof_ref() {
  local value="${SEXTANT_BACKUP_RESTORE_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_BACKUP_RESTORE_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_BACKUP_RESTORE_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*) ;;
    *)
      invalid+=("SEXTANT_BACKUP_RESTORE_PROOF_REF must be runbook://, https://, or ci-artifact:// with a non-empty target.")
      ;;
  esac
}

require_rollback_runbook_ref() {
  local value="${SEXTANT_ROLLBACK_RUNBOOK_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_ROLLBACK_RUNBOOK_REF "$value"
  reject_local_https_ref SEXTANT_ROLLBACK_RUNBOOK_REF "$value"
  case "$value" in
    runbook://?*|https://?*) ;;
    *)
      invalid+=("SEXTANT_ROLLBACK_RUNBOOK_REF must be runbook:// or https:// with a non-empty target.")
      ;;
  esac
}

require_rollback_execution_proof_ref() {
  local value="${SEXTANT_ROLLBACK_EXECUTION_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_ROLLBACK_EXECUTION_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_ROLLBACK_EXECUTION_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|github-run://?*|k8s://?*|ecs://?*|cloud-run://?*) ;;
    *)
      invalid+=("SEXTANT_ROLLBACK_EXECUTION_PROOF_REF must be runbook://, https://, ci-artifact://, github-run://, k8s://, ecs://, or cloud-run:// with a non-empty target.")
      ;;
  esac
}

require_deployment_approval_proof_ref() {
  local value="${SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|change-request://?*|github-deployment://?*|github-run://?*) ;;
    *)
      invalid+=("SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF must be runbook://, https://, ci-artifact://, change-request://, github-deployment://, or github-run:// with a non-empty target.")
      ;;
  esac
}

require_worker_capacity_proof_ref() {
  local value="${SEXTANT_WORKER_CAPACITY_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_WORKER_CAPACITY_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_WORKER_CAPACITY_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|k8s://?*|ecs://?*|cloud-run://?*) ;;
    *)
      invalid+=("SEXTANT_WORKER_CAPACITY_PROOF_REF must be runbook://, https://, ci-artifact://, k8s://, ecs://, or cloud-run:// with a non-empty target.")
      ;;
  esac
}

require_provider_live_eval_proof_ref() {
  local value="${SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|openai-eval://?*) ;;
    *)
      invalid+=("SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF must be runbook://, https://, ci-artifact://, or openai-eval:// with a non-empty target.")
      ;;
  esac
}

require_pgvector_recall_proof_ref() {
  local value="${SEXTANT_PGVECTOR_RECALL_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_PGVECTOR_RECALL_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_PGVECTOR_RECALL_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*) ;;
    *)
      invalid+=("SEXTANT_PGVECTOR_RECALL_PROOF_REF must be runbook://, https://, or ci-artifact:// with a non-empty target.")
      ;;
  esac
}

require_observability_pipeline_proof_ref() {
  local value="${SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|prometheus://?*|grafana://?*|otel://?*) ;;
    *)
      invalid+=("SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF must be runbook://, https://, ci-artifact://, prometheus://, grafana://, or otel:// with a non-empty target.")
      ;;
  esac
}

require_external_smoke_proof_ref() {
  local value="${SEXTANT_EXTERNAL_SMOKE_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_EXTERNAL_SMOKE_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_EXTERNAL_SMOKE_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*) ;;
    *)
      invalid+=("SEXTANT_EXTERNAL_SMOKE_PROOF_REF must be runbook://, https://, or ci-artifact:// with a non-empty target.")
      ;;
  esac
}

require_clean_context_ui_acceptance_proof_ref() {
  local value="${SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*) ;;
    *)
      invalid+=("SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF must be runbook://, https://, or ci-artifact:// with a non-empty target.")
      ;;
  esac
}

require_source_delta_search_reindex_proof_ref() {
  local value="${SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*) ;;
    *)
      invalid+=("SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF must be runbook://, https://, or ci-artifact:// with a non-empty target.")
      ;;
  esac
}

require_invitation_delivery_provider() {
  local value="${SEXTANT_INVITATION_DELIVERY_PROVIDER:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_INVITATION_DELIVERY_PROVIDER "$value"
  case "$value" in
    ses://?*|sendgrid://?*|postmark://?*|mailgun://?*|smtp-tls://?*|supabase-auth://?*) ;;
    *)
      invalid+=("SEXTANT_INVITATION_DELIVERY_PROVIDER must be ses://, sendgrid://, postmark://, mailgun://, smtp-tls://, or supabase-auth:// with a provider-specific target.")
      ;;
  esac
}

require_invitation_delivery_proof_ref() {
  local value="${SEXTANT_INVITATION_DELIVERY_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_INVITATION_DELIVERY_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_INVITATION_DELIVERY_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|ses://?*|sendgrid://?*|postmark://?*|mailgun://?*|smtp-tls://?*|supabase-auth://?*) ;;
    *)
      invalid+=("SEXTANT_INVITATION_DELIVERY_PROOF_REF must be runbook://, https://, ci-artifact://, ses://, sendgrid://, postmark://, mailgun://, smtp-tls://, or supabase-auth:// with a non-empty target.")
      ;;
  esac
}

require_token_issuer_proof_ref() {
  local value="${SEXTANT_TOKEN_ISSUER_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_TOKEN_ISSUER_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_TOKEN_ISSUER_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|auth0://?*|cognito://?*|okta://?*|clerk://?*|supabase://?*) ;;
    *)
      invalid+=("SEXTANT_TOKEN_ISSUER_PROOF_REF must be runbook://, https://, ci-artifact://, auth0://, cognito://, okta://, clerk://, or supabase:// with a non-empty target.")
      ;;
  esac
}

require_session_provider_provisioning_proof_ref() {
  local value="${SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|auth0://?*|cognito://?*|okta://?*|clerk://?*|supabase://?*) ;;
    *)
      invalid+=("SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF must be runbook://, https://, ci-artifact://, auth0://, cognito://, okta://, clerk://, or supabase:// with a non-empty target.")
      ;;
  esac
}

require_secret_manager_ref() {
  local value="${SEXTANT_SECRET_MANAGER_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  case "$value" in
    aws-secretsmanager://*)
      if ! SECRET_REF_VALUE="$value" python3 - <<'PY'
import os
from urllib.parse import parse_qs, unquote, urlparse

parsed = urlparse(os.environ["SECRET_REF_VALUE"])
json_key = parse_qs(parsed.query).get("json_key", [None])[0]
if parsed.scheme != "aws-secretsmanager":
    raise SystemExit(1)
if not parsed.netloc.strip() or not unquote(parsed.path.lstrip("/")).strip():
    raise SystemExit(1)
if json_key is not None and not json_key.strip():
    raise SystemExit(1)
PY
      then
        invalid+=("SEXTANT_SECRET_MANAGER_REF aws-secretsmanager:// refs must include region and secret id.")
      fi
      ;;
    gcp-secretmanager://*)
      if ! SECRET_REF_VALUE="$value" python3 - <<'PY'
import os
from urllib.parse import parse_qs, unquote, urlparse

parsed = urlparse(os.environ["SECRET_REF_VALUE"])
version = parse_qs(parsed.query, keep_blank_values=True).get("version", ["latest"])[0]
secret_parts = [
    unquote(part).strip() for part in parsed.path.split("/") if unquote(part).strip()
]
if parsed.scheme != "gcp-secretmanager":
    raise SystemExit(1)
if not parsed.netloc.strip() or len(secret_parts) != 1:
    raise SystemExit(1)
if version is None or not version.strip():
    raise SystemExit(1)
PY
      then
        invalid+=("SEXTANT_SECRET_MANAGER_REF gcp-secretmanager:// refs must include project id, secret id, and optional non-empty version.")
      fi
      ;;
    vault://*)
      if ! SECRET_REF_VALUE="$value" python3 - <<'PY'
import os
from urllib.parse import parse_qs, unquote, urlparse

parsed = urlparse(os.environ["SECRET_REF_VALUE"])
field = parse_qs(parsed.query).get("field", [None])[0]
if parsed.scheme != "vault":
    raise SystemExit(1)
if not parsed.netloc.strip() or not unquote(parsed.path.lstrip("/")).strip():
    raise SystemExit(1)
if field is None or not field.strip():
    raise SystemExit(1)
PY
      then
        invalid+=("SEXTANT_SECRET_MANAGER_REF vault:// refs must include host, secret path, and field.")
      fi
      ;;
    supabase-vault://*)
      if ! SECRET_REF_VALUE="$value" python3 - <<'PY'
import os
from urllib.parse import unquote, urlparse

parsed = urlparse(os.environ["SECRET_REF_VALUE"])
if parsed.scheme != "supabase-vault":
    raise SystemExit(1)
if parsed.username or parsed.password or parsed.params or parsed.query or parsed.fragment:
    raise SystemExit(1)
if not parsed.netloc.strip() or not unquote(parsed.path.lstrip("/")).strip():
    raise SystemExit(1)
PY
      then
        invalid+=("SEXTANT_SECRET_MANAGER_REF supabase-vault:// refs must include project ref and secret name without URL userinfo, params, query strings, or fragments.")
      fi
      ;;
    *) invalid+=("SEXTANT_SECRET_MANAGER_REF must be aws-secretsmanager://, gcp-secretmanager://, vault://, or supabase-vault://.") ;;
  esac
}

require_secret_manager_access_proof_ref() {
  local value="${SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  reject_secret_bearing_ref_parts SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF "$value"
  reject_local_https_ref SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF "$value"
  case "$value" in
    runbook://?*|https://?*|ci-artifact://?*|aws-iam://?*|gcp-iam://?*|vault-policy://?*) ;;
    *)
      invalid+=("SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF must be runbook://, https://, ci-artifact://, aws-iam://, gcp-iam://, or vault-policy:// with a non-empty target.")
      ;;
  esac
}

for name in \
  SEXTANT_DATABASE_URL \
  SEXTANT_OBJECT_STORE_ROOT \
  SEXTANT_BACKUP_TARGET \
  SEXTANT_CORS_ORIGINS \
  SEXTANT_AUTH_MODE \
  SEXTANT_SESSION_ISSUER \
  SEXTANT_SESSION_AUDIENCE \
  SEXTANT_SESSION_JWKS_URL \
  SEXTANT_ADMIN_ACTOR_IDS \
  SEXTANT_LLM_PROVIDER \
  SEXTANT_LLM_MODEL \
  SEXTANT_EMBEDDING_PROVIDER \
  SEXTANT_EMBEDDING_MODEL \
  SEXTANT_EMBEDDING_DIMENSIONS \
  SEXTANT_VECTOR_INDEX_PROVIDER \
  SEXTANT_RELEASE_ENVIRONMENT \
  SEXTANT_OBSERVABILITY_EXPORTER \
  SEXTANT_DEPLOYMENT_URL \
  SEXTANT_DEPLOYMENT_VERSION \
  SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF \
  SEXTANT_MANAGED_POSTGRES_INSTANCE \
  SEXTANT_OBJECT_STORE_IAM_PROOF_REF \
  SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF \
  SEXTANT_SECRET_MANAGER_REF \
  SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF \
  SEXTANT_SESSION_PROVIDER_ADMIN_URL \
  SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF \
  SEXTANT_INVITATION_DELIVERY_PROVIDER \
  SEXTANT_INVITATION_DELIVERY_PROOF_REF \
  SEXTANT_TOKEN_ISSUER_PROOF_REF \
  SEXTANT_HOSTED_METRICS_URL \
  SEXTANT_HOSTED_TRACES_URL \
  SEXTANT_ALERTING_DASHBOARD_URL \
  SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF \
  SEXTANT_WORKER_CAPACITY_PROOF_REF \
  SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF \
  SEXTANT_PGVECTOR_RECALL_PROOF_REF \
  SEXTANT_BACKUP_RESTORE_PROOF_REF \
  SEXTANT_ROLLBACK_RUNBOOK_REF \
  SEXTANT_ROLLBACK_EXECUTION_PROOF_REF \
  SEXTANT_EXTERNAL_SMOKE_URL \
  SEXTANT_EXTERNAL_SMOKE_PROOF_REF \
  SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF \
  SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF
do
  require_env "$name"
done

require_postgres_url SEXTANT_DATABASE_URL
require_s3_uri SEXTANT_OBJECT_STORE_ROOT
require_s3_uri SEXTANT_BACKUP_TARGET
require_https_url SEXTANT_SESSION_ISSUER
require_https_url SEXTANT_SESSION_JWKS_URL
require_https_url SEXTANT_DEPLOYMENT_URL
require_https_url SEXTANT_SESSION_PROVIDER_ADMIN_URL
require_https_url SEXTANT_HOSTED_METRICS_URL
require_https_url SEXTANT_HOSTED_TRACES_URL
require_https_url SEXTANT_ALERTING_DASHBOARD_URL
require_https_url SEXTANT_EXTERNAL_SMOKE_URL
require_secret_manager_ref
require_managed_postgres_instance
require_object_store_iam_proof_ref
require_object_store_read_write_proof_ref
require_deployment_approval_proof_ref
require_secret_manager_access_proof_ref
require_invitation_delivery_provider
require_invitation_delivery_proof_ref
require_token_issuer_proof_ref
require_session_provider_provisioning_proof_ref
require_worker_capacity_proof_ref
require_provider_live_eval_proof_ref
require_pgvector_recall_proof_ref
require_observability_pipeline_proof_ref
require_backup_restore_proof_ref
require_rollback_runbook_ref
require_rollback_execution_proof_ref
require_external_smoke_proof_ref
require_clean_context_ui_acceptance_proof_ref
require_source_delta_search_reindex_proof_ref

if (( ${#invalid[@]} > 0 )); then
  printf 'Invalid hosted readiness configuration:\n' >&2
  printf '  - %s\n' "${invalid[@]}" >&2
  exit 1
fi

if (( ${#missing[@]} > 0 )); then
  if (( allow_blocked == 1 )); then
    printf 'hosted-readiness-blocked\n'
    printf 'missing:\n'
    printf '  - %s\n' "${missing[@]}"
    exit 0
  fi
  printf 'Hosted readiness blockers:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

bash scripts/validate-production-config.sh >/dev/null

if [[ "${SEXTANT_RUN_EXTERNAL_SMOKE:-0}" == "1" ]]; then
  smoke_body="$(
    curl -fsS --max-time "${SEXTANT_EXTERNAL_SMOKE_TIMEOUT_SECONDS:-10}" \
      "$SEXTANT_EXTERNAL_SMOKE_URL"
  )"
  if [[ -n "${SEXTANT_EXTERNAL_SMOKE_EXPECT:-}" && "$smoke_body" != *"${SEXTANT_EXTERNAL_SMOKE_EXPECT}"* ]]; then
    echo "External smoke response did not contain SEXTANT_EXTERNAL_SMOKE_EXPECT." >&2
    exit 1
  fi
  echo "hosted-readiness-smoke-ok"
  exit 0
fi

echo "hosted-readiness-config-ok"
