#!/usr/bin/env bash
set -euo pipefail

missing=()

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
}

validate_optional_nonnegative_rate() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" ]]; then
    return
  fi
  if ! RATE_VALUE="$value" python3 - <<'PY'
import os

try:
    value = float(os.environ["RATE_VALUE"])
except ValueError:
    raise SystemExit(1)
if value < 0:
    raise SystemExit(1)
PY
  then
    echo "$name must be a numeric micro-USD rate per 1K tokens, zero or greater." >&2
    exit 1
  fi
}

validate_positive_integer() {
  local name="$1"
  local value="${!name:-}"
  if ! POSITIVE_INTEGER_VALUE="$value" python3 - <<'PY'
import os

try:
    value = int(os.environ["POSITIVE_INTEGER_VALUE"])
except ValueError:
    raise SystemExit(1)
if value <= 0:
    raise SystemExit(1)
PY
  then
    echo "$name must be a positive integer." >&2
    exit 1
  fi
}

require_env SEXTANT_DATABASE_URL
require_env SEXTANT_OBJECT_STORE_ROOT
require_env SEXTANT_CORS_ORIGINS
require_env SEXTANT_AUTH_MODE
require_env SEXTANT_SESSION_ISSUER
require_env SEXTANT_SESSION_AUDIENCE
require_env SEXTANT_SESSION_JWKS_URL
require_env SEXTANT_ADMIN_ACTOR_IDS
require_env SEXTANT_LLM_PROVIDER
require_env SEXTANT_LLM_MODEL
require_env SEXTANT_EMBEDDING_PROVIDER
require_env SEXTANT_EMBEDDING_MODEL
require_env SEXTANT_EMBEDDING_DIMENSIONS
require_env SEXTANT_VECTOR_INDEX_PROVIDER
require_env SEXTANT_BACKUP_TARGET
require_env SEXTANT_RELEASE_ENVIRONMENT
require_env SEXTANT_OBSERVABILITY_EXPORTER

if (( ${#missing[@]} > 0 )); then
  printf 'Missing production configuration:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

if [[ "${SEXTANT_DATABASE_URL:-}" != postgresql* ]]; then
  echo "SEXTANT_DATABASE_URL must be a PostgreSQL URL for production." >&2
  exit 1
fi

if [[ "${SEXTANT_OBJECT_STORE_ROOT:-}" != s3://* ]]; then
  echo "SEXTANT_OBJECT_STORE_ROOT must be an s3:// URI for production." >&2
  exit 1
fi

if [[ "${SEXTANT_BACKUP_TARGET:-}" != s3://* ]]; then
  echo "SEXTANT_BACKUP_TARGET must be an s3:// URI for production." >&2
  exit 1
fi

if [[ "${SEXTANT_OBSERVABILITY_EXPORTER:-}" != "none" && "${SEXTANT_OBSERVABILITY_EXPORTER:-}" != "otlp" ]]; then
  echo "SEXTANT_OBSERVABILITY_EXPORTER must be none or otlp for production." >&2
  exit 1
fi

if [[ "${SEXTANT_OBSERVABILITY_EXPORTER:-}" == "otlp" ]]; then
  if [[ -z "${SEXTANT_OTLP_ENDPOINT:-}" ]]; then
    echo "SEXTANT_OTLP_ENDPOINT is required when SEXTANT_OBSERVABILITY_EXPORTER=otlp." >&2
    exit 1
  fi
  if [[ "${SEXTANT_OTLP_ENDPOINT:-}" != https://* ]]; then
    echo "SEXTANT_OTLP_ENDPOINT must be an HTTPS URL for production." >&2
    exit 1
  fi
fi

if [[ "${SEXTANT_LLM_PROVIDER:-}" != "openai" ]]; then
  echo "SEXTANT_LLM_PROVIDER must be openai for the implemented production provider." >&2
  exit 1
fi

if [[ "${SEXTANT_EMBEDDING_PROVIDER:-}" != "openai" ]]; then
  echo "SEXTANT_EMBEDDING_PROVIDER must be openai for production semantic retrieval." >&2
  exit 1
fi

validate_positive_integer SEXTANT_EMBEDDING_DIMENSIONS

if [[ "${SEXTANT_VECTOR_INDEX_PROVIDER:-}" != "pgvector" ]]; then
  echo "SEXTANT_VECTOR_INDEX_PROVIDER must be pgvector for production semantic retrieval." >&2
  exit 1
fi

if [[ -n "${SEXTANT_POV_LLM_PROVIDER:-}" && "${SEXTANT_POV_LLM_PROVIDER:-}" != "openai" ]]; then
  echo "SEXTANT_POV_LLM_PROVIDER must be openai when set for production." >&2
  exit 1
fi

if [[ -n "${SEXTANT_MEMORY_LLM_PROVIDER:-}" && "${SEXTANT_MEMORY_LLM_PROVIDER:-}" != "openai" ]]; then
  echo "SEXTANT_MEMORY_LLM_PROVIDER must be openai when set for production." >&2
  exit 1
fi

if [[ -n "${SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER:-}" && "${SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER:-}" != "openai" ]]; then
  echo "SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER must be openai when set for production." >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" && -z "${SEXTANT_OPENAI_API_KEY:-}" && -z "${SEXTANT_LLM_API_KEY_SECRET_REF:-}" ]]; then
  echo "OpenAI production provider requires OPENAI_API_KEY, SEXTANT_OPENAI_API_KEY, or SEXTANT_LLM_API_KEY_SECRET_REF." >&2
  exit 1
fi

if [[ -n "${SEXTANT_LLM_API_KEY_SECRET_REF:-}" ]]; then
  case "${SEXTANT_LLM_API_KEY_SECRET_REF:-}" in
    secret://*) ;;
    aws-secretsmanager://*)
      if ! SECRET_REF_VALUE="${SEXTANT_LLM_API_KEY_SECRET_REF:-}" python3 - <<'PY'
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
        echo "SEXTANT_LLM_API_KEY_SECRET_REF aws-secretsmanager:// refs must include region and secret id." >&2
        exit 1
      fi
      ;;
    gcp-secretmanager://*)
      if ! SECRET_REF_VALUE="${SEXTANT_LLM_API_KEY_SECRET_REF:-}" python3 - <<'PY'
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
        echo "SEXTANT_LLM_API_KEY_SECRET_REF gcp-secretmanager:// refs must include project id, secret id, and optional non-empty version." >&2
        exit 1
      fi
      ;;
    vault://*)
      if [[ -z "${SEXTANT_VAULT_TOKEN:-}" ]]; then
        echo "SEXTANT_VAULT_TOKEN is required when SEXTANT_LLM_API_KEY_SECRET_REF uses vault://." >&2
        exit 1
      fi
      if ! SECRET_REF_VALUE="${SEXTANT_LLM_API_KEY_SECRET_REF:-}" python3 - <<'PY'
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
        echo "SEXTANT_LLM_API_KEY_SECRET_REF vault:// refs must include host, secret path, and field." >&2
        exit 1
      fi
      ;;
    supabase-vault://*)
      if ! SECRET_REF_VALUE="${SEXTANT_LLM_API_KEY_SECRET_REF:-}" python3 - <<'PY'
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
        echo "SEXTANT_LLM_API_KEY_SECRET_REF supabase-vault:// refs must include project ref and secret name without URL userinfo, params, query strings, or fragments." >&2
        exit 1
      fi
      ;;
    *)
      echo "SEXTANT_LLM_API_KEY_SECRET_REF must be a secret://, aws-secretsmanager://, gcp-secretmanager://, vault://, or supabase-vault:// reference for production." >&2
      exit 1
      ;;
  esac
fi

validate_optional_nonnegative_rate SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS
validate_optional_nonnegative_rate SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS

if [[ "${SEXTANT_AUTH_MODE:-}" == "header-dev" ]]; then
  echo "SEXTANT_AUTH_MODE=header-dev is not allowed for production." >&2
  exit 1
fi

if [[ "${SEXTANT_AUTH_MODE:-}" != "jwt-jwks" ]]; then
  echo "SEXTANT_AUTH_MODE must be jwt-jwks for production." >&2
  exit 1
fi

if [[ "${SEXTANT_SESSION_JWKS_URL:-}" != https://* ]]; then
  echo "SEXTANT_SESSION_JWKS_URL must be an HTTPS URL for production." >&2
  exit 1
fi

if ! python3 - <<'PY'
import os
from uuid import UUID

raw = os.environ.get("SEXTANT_ADMIN_ACTOR_IDS", "")
ids = [item.strip() for item in raw.split(",") if item.strip()]
if not ids:
    raise SystemExit(1)
try:
    for item in ids:
        UUID(item)
except ValueError:
    raise SystemExit(1)
PY
then
  echo "SEXTANT_ADMIN_ACTOR_IDS must contain at least one comma-separated UUID." >&2
  exit 1
fi

echo "production-config-ok"
