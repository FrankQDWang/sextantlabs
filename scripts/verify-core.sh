#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${SEXTANT_VERIFY_PYTHON:-/opt/homebrew/bin/python3}"
VERIFY_TMP="${SEXTANT_VERIFY_TMP:-${TMPDIR:-/tmp}}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$VERIFY_TMP/sextantlabs-uv-cache}"

git diff --check -- AGENTS.md PLAN.md README.md PRODUCT.md docs experience goals implementation web backend scripts pyproject.toml tach.toml alembic.ini
uv sync --locked
SEMGREP_TMP="${SEXTANT_SEMGREP_TMP:-$VERIFY_TMP/sextantlabs-semgrep}"
mkdir -p "$SEMGREP_TMP/config"
SEMGREP_CA_BUNDLE="$(uv run --python "$PYTHON_BIN" python -c 'import certifi; print(certifi.where())')"
export SSL_CERT_FILE="${SSL_CERT_FILE:-$SEMGREP_CA_BUNDLE}"
export REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-$SEMGREP_CA_BUNDLE}"
export CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-$SEMGREP_CA_BUNDLE}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$SEMGREP_TMP/config}"
export SEMGREP_LOG_FILE="${SEMGREP_LOG_FILE:-$SEMGREP_TMP/semgrep.log}"
export SEMGREP_SETTINGS_FILE="${SEMGREP_SETTINGS_FILE:-$SEMGREP_TMP/settings.yaml}"
export SEMGREP_VERSION_CACHE_PATH="${SEMGREP_VERSION_CACHE_PATH:-$SEMGREP_TMP/version-cache}"
uv run --python "$PYTHON_BIN" ruff format --check backend/src backend/tests backend/migrations backend/scripts
uv run --python "$PYTHON_BIN" ruff check backend/src backend/tests backend/migrations backend/scripts
uv run --python "$PYTHON_BIN" ty check backend/src
uv run --python "$PYTHON_BIN" tach check
uv run --python "$PYTHON_BIN" pytest backend/tests
uv run --python "$PYTHON_BIN" python -c "import os,tempfile,pathlib; from alembic.config import Config; from alembic import command; fd,path=tempfile.mkstemp(prefix='sextant-alembic-', suffix='.db'); os.close(fd); os.environ['SEXTANT_DATABASE_URL']='sqlite+pysqlite:///'+path; command.upgrade(Config('alembic.ini'),'head'); pathlib.Path(path).unlink(missing_ok=True)"
uv run --python "$PYTHON_BIN" semgrep --config .semgrep/sextant.yml backend/src --error --quiet --metrics=off --disable-version-check
uv run --python "$PYTHON_BIN" python backend/scripts/production_smoke.py
bash scripts/validate-hosted-readiness.sh --allow-blocked
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
pnpm --dir web test
export SEXTANT_E2E_API_PORT="${SEXTANT_E2E_API_PORT:-8121}"
export SEXTANT_E2E_WEB_PORT="${SEXTANT_E2E_WEB_PORT:-5821}"
export SEXTANT_E2E_STATE_DIR="${SEXTANT_E2E_STATE_DIR:-$VERIFY_TMP/sextantlabs-e2e}"
pnpm --dir web test:e2e
