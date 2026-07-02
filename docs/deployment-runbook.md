# Deployment Runbook

This runbook records the production deployment interface. It is not evidence that hosted deployment has happened in this local thread.

## Required Production Configuration

`scripts/validate-production-config.sh` requires:

- `SEXTANT_DATABASE_URL` as a PostgreSQL URL;
- `SEXTANT_OBJECT_STORE_ROOT` as an `s3://bucket/prefix` URI;
- `SEXTANT_CORS_ORIGINS`;
- `SEXTANT_AUTH_MODE`;
- `SEXTANT_SESSION_ISSUER`;
- `SEXTANT_SESSION_AUDIENCE`;
- `SEXTANT_SESSION_JWKS_URL`;
- `SEXTANT_ADMIN_ACTOR_IDS` as one or more comma-separated UUIDs;
- `SEXTANT_LLM_PROVIDER`;
- `SEXTANT_LLM_MODEL`;
- `SEXTANT_EMBEDDING_PROVIDER`;
- `SEXTANT_EMBEDDING_MODEL`;
- `SEXTANT_EMBEDDING_DIMENSIONS` as a positive integer;
- `SEXTANT_VECTOR_INDEX_PROVIDER=pgvector`;
- `OPENAI_API_KEY`, `SEXTANT_OPENAI_API_KEY`, or
  `SEXTANT_LLM_API_KEY_SECRET_REF`;
- `SEXTANT_BACKUP_TARGET` as an `s3://bucket/prefix` URI;
- `SEXTANT_RELEASE_ENVIRONMENT`;
- `SEXTANT_OBSERVABILITY_EXPORTER` as `none` or `otlp`.

`SEXTANT_AUTH_MODE=header-dev` is rejected for production.
Local filesystem object storage is rejected for production. Runtime API and
worker processes use the S3 object-store adapter when
`SEXTANT_OBJECT_STORE_ROOT` starts with `s3://`.
The implemented production StoryDraft, POV detection, Memory Extraction, and
Event Aggregation providers are OpenAI-backed. `SEXTANT_POV_LLM_PROVIDER`,
`SEXTANT_MEMORY_LLM_PROVIDER`, and `SEXTANT_EVENT_AGGREGATION_LLM_PROVIDER` may
be omitted to inherit `SEXTANT_LLM_PROVIDER`; if any is set in production,
validation requires `openai`. `SEXTANT_POV_LLM_MODEL`,
`SEXTANT_MEMORY_LLM_MODEL`, and `SEXTANT_EVENT_AGGREGATION_LLM_MODEL` may be
omitted to inherit `SEXTANT_LLM_MODEL`. Production validation rejects
unsupported provider names and requires a materialized OpenAI API key or a
supported provider-key secret reference. Runtime provider factories can read
AWS Secrets Manager refs shaped as
`aws-secretsmanager://<region>/<secret-id>?json_key=<field>`, GCP Secret Manager
refs shaped as `gcp-secretmanager://<project-id>/<secret-id>?version=<version>`
with version defaulting to `latest`, and HashiCorp Vault refs shaped as
`vault://<host>/<secret-path>?field=<field>` with `SEXTANT_VAULT_TOKEN`.
Existing-stack Supabase Vault refs are shaped as
`supabase-vault://<project-ref>/<secret-name>` and are read through
`SEXTANT_SUPABASE_VAULT_DATABASE_URL` or `SEXTANT_DATABASE_URL`. The
older `secret://...` form remains only a deployment materialization placeholder:
if it is present but neither `SEXTANT_OPENAI_API_KEY` nor `OPENAI_API_KEY` has
been materialized, the API or worker startup path fails with an explicit
secret-materialization blocker. Production config validation accepts
`secret://`, `aws-secretsmanager://`, `gcp-secretmanager://`, `vault://`, and
`supabase-vault://` refs, and rejects malformed refs before deployment.
OpenAI-compatible hosted providers can override the SDK endpoint with
`SEXTANT_OPENAI_BASE_URL`. For Alibaba Bailian / DashScope compatible mode, use
`https://dashscope.aliyuncs.com/compatible-mode/v1` and
`SEXTANT_OPENAI_API_STYLE=chat`, because Bailian's compatibility surface is
the OpenAI Chat Completions path. Runtime providers also accept scoped
`SEXTANT_*_REASONING_EFFORT` and `SEXTANT_*_ENABLE_THINKING` variables, which
are passed as provider-specific `extra_body` fields and still flow through the
same structured-output validation before any persistence side effect.
The implemented production embedding provider is OpenAI-backed. Production
validation rejects local deterministic embeddings and requires an explicit
embedding model plus dimensions. The local deterministic embedding provider is
only a provider-boundary substitute for development, tests, and evals. Bailian
OpenAI-compatible embeddings can use `SEXTANT_EMBEDDING_MODEL=text-embedding-v4`
with explicit `SEXTANT_EMBEDDING_DIMENSIONS`; `1024` is the local configuration
default for this repository's Bailian `.env`, while hosted pgvector deployments
may choose a larger supported dimension when storage and index cost allow.

Hosted live provider eval is separate from prompt/golden replay tests:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_provider_live_eval_probe.py
```

It requires `SEXTANT_RELEASE_ENVIRONMENT=production`, OpenAI-backed
StoryDraft, Memory Extraction, POV Detection, Event Aggregation, and Embedding
providers, selected models, embedding dimensions, and a materialized OpenAI
credential or supported AWS/GCP/Vault secret ref. `--check-config` validates
that production/provider/credential shape without calling providers. The full
command exercises the production provider factories with bounded non-private
samples and emits sanitized JSON evidence with output shapes and fingerprints
only. It does not print prompts, provider raw output, manuscript text, API keys,
or secret refs, and operators must archive its output behind
`SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF`.

OpenAI provider token usage is exported as process metrics when OpenAI returns
a usage object. Optional cost estimates require deployment-provided rates:

```bash
SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS=200
SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS=800
```

Rates are micro-USD per 1K tokens. If omitted, token metrics still export and
cost metrics are not emitted. If set, the API process records StoryDraft
provider metrics through its `/metrics` endpoint, and the worker process records
StoryDraft, POV detection, Memory Extraction, and Event Aggregation provider
metrics through the worker `/metrics` endpoint when enabled.
`scripts/validate-production-config.sh`
rejects non-numeric or negative rate values before deployment.

Production observability export must be explicit:

```bash
SEXTANT_OBSERVABILITY_EXPORTER=none
# or
SEXTANT_OBSERVABILITY_EXPORTER=otlp
SEXTANT_OTLP_ENDPOINT=https://otel.example.com/v1/traces
```

`none` is acceptable for local structural validation only; it does not satisfy
hosted observability acceptance. If `otlp` is selected, production validation
requires `SEXTANT_OTLP_ENDPOINT` to be an HTTPS URL. The API already propagates
W3C `traceparent` ids through response headers and safe logs, but hosted trace
collection, sampling, dashboards, and alert routing remain deployment
infrastructure.

Production auth mode is:

```bash
SEXTANT_AUTH_MODE=jwt-jwks
```

The API validates `Authorization: Bearer <token>` against an HTTPS
`SEXTANT_SESSION_JWKS_URL`, `SEXTANT_SESSION_ISSUER`, and
`SEXTANT_SESSION_AUDIENCE`. JWTs must include `exp`, `iss`, `aud`, and `sub`.
The `sub` claim must be a UUID and must match a durable project membership row
before project-scoped data is returned. `X-Actor-Id` is local `header-dev`
compatibility only and cannot override the verified JWT subject in production
mode.

The hosted session-provider readiness runner is separate from local auth tests:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_SESSION_ISSUER=https://auth.example.com/ \
SEXTANT_SESSION_AUDIENCE=sextant-api \
SEXTANT_SESSION_JWKS_URL=https://auth.example.com/.well-known/jwks.json \
SEXTANT_SESSION_PROVIDER_ADMIN_URL=https://auth.example.com/admin \
SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=auth0://prod/sextant/session-provider \
SEXTANT_INVITATION_DELIVERY_PROVIDER=ses://prod/invitations \
SEXTANT_INVITATION_DELIVERY_PROOF_REF=ci-artifact://prod/invitations/2026-06-19 \
SEXTANT_TOKEN_ISSUER_PROOF_REF=ci-artifact://prod/token-issuer/2026-06-19 \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_session_provider_probe.py
```

`--check-config` validates hosted URL and proof-ref shape without network
requests. The full command fetches the hosted JWKS and admin surfaces, verifies
JWKS key presence, emits sanitized JSON evidence with hosts, response hashes,
key counts, and proof-ref fingerprints, and must be archived with the
session-provider deployment record. It does not send invitations, mint tokens,
print bearer tokens, print JWK material, or fabricate readiness proof.

Global Story Schema Genre Pack provisioning is restricted to actors listed in
`SEXTANT_ADMIN_ACTOR_IDS`. Project owners and editors can select active Genre
Packs for their project, but they cannot create or deprecate global Genre Pack
records unless their verified actor id is also in the admin list.

## Local Validation

```bash
bash scripts/verify-core.sh
```

The local production-path smoke command is included in `verify-core`:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/production_smoke.py
```

It runs migrations, FastAPI contracts, SQLAlchemy persistence, local object storage, a DB worker, memory writeback, and preview reads. It refuses `SEXTANT_RELEASE_ENVIRONMENT=production`; use hosted readiness and external smoke gates for production release validation.

The deployed API exposes a public liveness endpoint:

```text
GET /health
```

The response contains only safe process metadata: `status`, `service`,
`api_version`, `release_environment`, and `deployment_version`. Use this for
load-balancer liveness and as a hosted URL target when a gate only needs to
prove the API process is reachable. It does not check PostgreSQL, object
storage, workers, provider credentials, review queues, graph projection, or
browser acceptance; those remain covered by the hosted readiness probes and
external smoke evidence below.

The hosted API smoke runner is separate from local smoke:

```bash
SEXTANT_EXTERNAL_SMOKE_URL=https://api.example.com \
SEXTANT_EXTERNAL_SMOKE_PROJECT_ID=00000000-0000-4000-8000-000000000000 \
SEXTANT_EXTERNAL_SMOKE_BEARER_TOKEN="$JWT" \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_external_smoke.py
```

`--check-config` validates the hosted URL, project id, token presence, and
polling values without sending network requests. The full command talks only
to the deployed API over HTTPS, creates a source in the pre-provisioned smoke
project, waits for the hosted worker job, reads MemoryWritebackPreview, asks a
SourceSpan-backed MemoryAnswer, and emits JSON evidence. It rejects localhost,
`.local`, loopback, link-local, and unspecified hosts. Store the resulting
JSON in an auditable location, then set `SEXTANT_EXTERNAL_SMOKE_PROOF_REF` to
that artifact; the runner itself does not mint or fake the proof ref.

The local PostgreSQL production-database gate is separate from `verify-core`
because it requires Docker or Podman:

```bash
bash scripts/postgres-smoke.sh
```

It starts a real `postgres:16` container, waits for an actual `SELECT 1`,
runs Alembic against PostgreSQL, runs the production smoke path, creates a
`pg_dump` backup, restores it into a second database, and verifies restored
SourceDelta and MemoryPage rows plus restored SourceSpan -> RawSource /
SourceVersion resolution. The command is local infrastructure evidence; it is
not evidence that a hosted managed database, hosted backup target, or rollback
drill has run.

The hosted managed PostgreSQL readiness runner is separate from the local
container smoke:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DATABASE_URL=postgresql+psycopg://...@db.example.com/sextant \
SEXTANT_MANAGED_POSTGRES_INSTANCE=rds://prod/sextant \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_postgres_readiness_probe.py
```

`--check-config` validates production mode, hosted database host shape, managed
PostgreSQL instance ref shape, and minimum evidence-chain row thresholds
without connecting to the database. The full command connects to the hosted
database, verifies the Alembic head, checks SourceDelta, SourceSpan,
MemoryPage, and SourceSpan -> RawSource resolution counts, emits sanitized JSON
evidence, and must be archived with the managed PostgreSQL deployment record.
The runner does not print database passwords, raw managed-instance refs, or
manuscript text, and it does not mint or fake hosted proof.

The hosted backup/restore runner is separate from the local container smoke:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DATABASE_URL=postgresql+psycopg://...@db.example.com/sextant \
SEXTANT_BACKUP_RESTORE_DATABASE_URL=postgresql+psycopg://...@restore-db.example.com/sextant_restore \
SEXTANT_BACKUP_TARGET=s3://sextant-prod-backups/restore-probes \
SEXTANT_BACKUP_RESTORE_SCHEMAS=public \
SEXTANT_BACKUP_RESTORE_REQUIRED_EXTENSIONS=vector:public,pg_trgm:public \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_backup_restore_probe.py
```

`SEXTANT_BACKUP_RESTORE_DATABASE_URL` must point at a separate scratch hosted
database prepared for restore validation. `--check-config` validates
production mode, hosted PostgreSQL URL shape, hosted S3 endpoint shape, and
backup target shape without connecting to the database or object store. The
full command runs `pg_dump --clean --if-exists` for the configured application
schemas and required application extensions, uploads the dump to the configured
S3 backup target, downloads it back, restores it with `psql`, verifies
SourceDelta, MemoryPage, and SourceSpan -> RawSource counts, emits sanitized
JSON evidence, and must be archived behind `SEXTANT_BACKUP_RESTORE_PROOF_REF`;
the runner does not mint or fake that proof ref. Do not include Supabase-managed
platform schemas such as `auth` in the application restore proof.

The hosted rollback drill runner is separate from the backup/restore probe and
from the rollback runbook reference:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+current \
SEXTANT_ROLLBACK_TARGET_VERSION=2026.06.18+previous \
SEXTANT_ROLLBACK_STATUS_URL=https://deploy.example.com/sextant/status \
SEXTANT_ROLLBACK_RUNBOOK_REF=runbook://release/rollback/2026-06-19 \
SEXTANT_ROLLBACK_COMMAND='sextant-release rollback --target-version 2026.06.18+previous' \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_rollback_drill_probe.py
```

`--check-config` validates production mode, hosted status URL shape, distinct
current/target versions, rollback runbook ref shape, and rollback command shape
without executing network or rollback operations. The full command fetches the
hosted status URL before rollback, executes the rollback command without a
shell, polls until the hosted status reports the target version and expected
health, emits sanitized JSON evidence, and must be archived behind
`SEXTANT_ROLLBACK_EXECUTION_PROOF_REF`; the runner does not print command
output, bearer tokens, status response bodies, raw runbook refs, or mint/fake
that proof ref.

The local pgvector semantic-index gate is also separate from `verify-core`
because it requires Docker or Podman:

```bash
bash scripts/pgvector-smoke.sh
```

It starts a real `pgvector/pgvector:pg17` container, creates the `vector`
extension, runs Alembic, refreshes persisted semantic embeddings, creates the
dimension-specific HNSW expression index
`ix_semantic_embeddings_embedding_vector_hnsw`, verifies pgvector `<=>`
ranking through `semantic_ref_keys_for_text`, and confirms MemoryAnswer can
answer an existing SourceSpan-backed open-thread query through pgvector recall.
The command proves the local pgvector validation path; hosted readiness still
requires managed Postgres evidence, hosted pgvector recall proof, and external
smoke evidence.

The hosted pgvector recall runner is separate from the local container smoke:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_pgvector_recall_probe.py
```

It requires `SEXTANT_RELEASE_ENVIRONMENT=production`, a hosted PostgreSQL
`SEXTANT_DATABASE_URL`, `SEXTANT_VECTOR_INDEX_PROVIDER=pgvector`, the configured
embedding provider/model/dimensions, and
`SEXTANT_PGVECTOR_RECALL_PROJECT_ID`. `--check-config` validates those inputs
without connecting to the database. The full command verifies the hosted
`vector` extension, `semantic_embeddings.embedding_vector`, the HNSW index,
persisted vector rows for the configured project/provider/model, and a
pgvector nearest-neighbor self-recall query. It prints sanitized JSON evidence
with hashed project and embedding ids; operators must archive that output
behind `SEXTANT_PGVECTOR_RECALL_PROOF_REF`.

The API exposes aggregate request counters at:

```text
GET /metrics
GET /observability/traces
GET /observability/alerts
```

`GET /metrics` emits Prometheus text for `sextant_api_requests_total` and
`sextant_api_errors_total`, application error-code totals, core
ActionRequest/Candidate/ContextPack/MemoryWriteback latency count/sum metrics,
LLM validation failures, canon-promotion blocks, and worker job outcome/queue
age metrics when a worker is run with the shared metrics registry. OpenAI-backed
provider calls also emit `sextant_provider_tokens_total` and, when the rate
environment variables above are configured,
`sextant_provider_cost_microusd_total`. It does not include request bodies,
manuscript text, author notes, prompt input, raw provider output, or
object-store refs. `GET /observability/traces` returns recent API trace samples
with path templates, status, duration, and SHA-256 trace/span fingerprints only.
`GET /observability/alerts` returns metric-derived alert state for API errors
and worker job failures. Neither endpoint includes actor ids, request bodies,
manuscript text, raw trace ids, prompts, provider output, or secret values.

The standalone worker loop exposes the same Prometheus text format when a
metrics port is configured:

```bash
SEXTANT_WORKER_METRICS_PORT=9091
SEXTANT_WORKER_METRICS_HOST=127.0.0.1
```

When enabled, the worker serves `GET /metrics` from the worker process and
exports worker-local job outcome and queue-age observations. Hosted scraping
must still be provisioned outside this repository.

Hosted worker capacity can be probed from the deployed worker metrics endpoint:

```bash
SEXTANT_HOSTED_WORKER_METRICS_URL=https://worker-metrics.example.com/metrics \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_worker_capacity_probe.py
```

Set `SEXTANT_HOSTED_WORKER_METRICS_BEARER_TOKEN` when the metrics endpoint is
protected. The probe requires successful `sextant_worker_jobs_total` metrics,
checks average `sextant_job_queue_age_seconds` against
`SEXTANT_WORKER_CAPACITY_MAX_QUEUE_AGE_SECONDS`, rejects local/loopback
metrics URLs, and emits JSON evidence. Store that output in an auditable
location, then set `SEXTANT_WORKER_CAPACITY_PROOF_REF` to the artifact. The
probe does not mint or fake the proof ref.

Hosted readiness is checked separately from local production configuration:

```bash
bash scripts/validate-hosted-readiness.sh
```

The strict command fails until hosted deployment evidence is present:

- HTTPS deployment URL and release version;
- deployment approval or change-control proof using `runbook://`,
  `https://`, `ci-artifact://`, `change-request://`,
  `github-deployment://`, or `github-run://`;
- managed PostgreSQL instance identifier using a hosted provider ref such as
  `rds://`, `cloudsql://`, `azure-postgres://`, `neon://`,
  `supabase://`, or `crunchy-postgres://`, plus archived readiness evidence
  from `backend/scripts/hosted_postgres_readiness_probe.py`;
- S3-compatible object-store IAM proof using `runbook://`, `https://`,
  `aws-iam://`, `gcp-iam://`, `azure-rbac://`, or `cloudflare-r2://`, plus
  backup target;
- object-store read/write proof using `runbook://`, `https://`,
  `ci-artifact://`, `s3://`, `gs://`, or `azure-blob://`;
- deployment secret-manager reference using a structurally valid
  `aws-secretsmanager://`, `gcp-secretmanager://`, `vault://`, or
  `supabase-vault://` ref;
- secret-manager access proof using `runbook://`, `https://`,
  `ci-artifact://`, `aws-iam://`, `gcp-iam://`, or `vault-policy://`;
- live provider eval proof using `runbook://`, `https://`,
  `ci-artifact://`, or `openai-eval://`;
- hosted pgvector recall proof using `runbook://`, `https://`, or
  `ci-artifact://`;
- session-provider admin URL, session-provider provisioning proof, invitation
  delivery provider/proof, token-issuer proof, and archived readiness evidence from
  `backend/scripts/hosted_session_provider_probe.py`;
- hosted metrics, trace, and alert/dashboard URLs;
- observability pipeline proof using `runbook://`, `https://`,
  `ci-artifact://`, `prometheus://`, `grafana://`, or `otel://`;
- hosted worker capacity proof using `runbook://`, `https://`,
  `ci-artifact://`, `k8s://`, `ecs://`, or `cloud-run://`;
- backup/restore proof using `runbook://`, `https://`, or
  `ci-artifact://`, plus rollback runbook reference using `runbook://` or
  `https://`, plus rollback execution proof using `runbook://`, `https://`,
  `ci-artifact://`, `github-run://`, `k8s://`, `ecs://`, or
  `cloud-run://`;
- HTTPS external smoke target URL and external smoke proof using
  `runbook://`, `https://`, or `ci-artifact://`.
- clean-context UI acceptance proof using `runbook://`, `https://`, or
  `ci-artifact://`.
- SourceDelta search reindex proof using `runbook://`, `https://`, or
  `ci-artifact://`.

Local verification can run the same contract in blocker-recording mode:

```bash
bash scripts/validate-hosted-readiness.sh --allow-blocked
```

`--allow-blocked` exits 0 only for missing external evidence and prints
`hosted-readiness-blocked` with the missing variables. Invalid provided values
still fail. This keeps hosted deployment blocked without introducing fake
secret managers, fake observability collectors, or fake external smoke.
Hosted HTTPS URLs for deployment, session issuer/JWKS, session-provider admin,
metrics, traces, alert dashboards, and external smoke must resolve to hosted
endpoints, not localhost aliases. The gate rejects `localhost`, `.localhost`,
`.local`, loopback, link-local, and unspecified host values. Private VPC or
enterprise DNS names are not rejected solely because they are non-public; the
gate only blocks explicitly local placeholders.
Hosted proof refs, runbook refs, and the invitation delivery provider ref must
be stable external identifiers only. They must not include URL userinfo,
params, query strings, or fragments. Private artifact access belongs in bearer
configuration, provider IAM, or the hosted probe artifact-fetch settings, not
inside persisted readiness refs. The readiness gate and direct hosted
proof-probe configuration parsers both reject credential-bearing proof refs.
Hosted proof artifact URLs follow the same rule: use the probe-specific bearer
token environment variable or hosted runtime identity rather than signed-query
URLs or embedded URL credentials.
Deployment approval proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `change-request://`, `github-deployment://`, or
`github-run://` ref. It proves a hosted release approval, deployment record,
or change-control artifact exists outside the local repository. Local, mock,
and free-form placeholders are invalid.
To validate the approval artifact shape and archive hash-only evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+deploy \
SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF=change-request://prod/sextant/2026-06-19 \
SEXTANT_DEPLOYMENT_APPROVAL_ARTIFACT_URL=https://change.example.com/prod/sextant/2026-06-19.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_deployment_approval_probe.py
```

`--check-config` validates production mode, deployment version, proof-ref
scheme, hosted artifact URL, timeout, expected statuses, and minimum approver
count without network requests. The full command fetches the hosted JSON
artifact, verifies deployment version, approved status, and approver count, and
emits sanitized JSON evidence. It does not print approval bodies, approver
identities, bearer tokens, raw proof refs, or mint/fake
`SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF`.
Secret-manager access proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `aws-iam://`, `gcp-iam://`, or `vault-policy://` ref. It
proves the hosted runtime identity can read the configured secret manager
outside the local repository. A structurally valid `SEXTANT_SECRET_MANAGER_REF`
is only a target reference; local, mock, and free-form access proof
placeholders are invalid.

To produce the secret-manager access proof artifact, run the hosted probe with
the deployed runtime identity and configured secret ref:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_secret_manager_probe.py
```

`--check-config` validates production mode and the secret-manager ref shape
without reading the secret. The full command reads the secret through the
production AWS Secrets Manager, GCP Secret Manager, Vault, or Supabase Vault
resolver, emits redacted JSON evidence with a ref fingerprint and byte count,
and must be archived behind `SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF`; the
runner never prints the secret value or mints the proof ref.
Managed PostgreSQL readiness evidence must come from the hosted managed
database identified by `SEXTANT_MANAGED_POSTGRES_INSTANCE`. Run the hosted
probe with the deployed production database URL:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DATABASE_URL=postgresql+psycopg://...@db.example.com/sextant \
SEXTANT_MANAGED_POSTGRES_INSTANCE=rds://prod/sextant \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_postgres_readiness_probe.py
```

The full command verifies hosted connectivity, the current Alembic head, and
minimum evidence-chain row counts, then emits sanitized JSON evidence with a
managed-instance fingerprint. Local database URLs, free-form managed Postgres
names, and raw credential dumps are invalid evidence.
Managed Postgres, object-store IAM, object-store read/write, worker capacity,
backup/restore, rollback runbook, and rollback execution proof values must also
use their documented hosted/provider/auditable schemes; local database names,
free-form strings, and `local://` proof placeholders are invalid even when
`--allow-blocked` is used.
If object-store IAM, object-store read/write, session-provider provisioning,
worker capacity, backup/restore, rollback runbook, rollback execution, or
token-issuer proof refs use `https://`, those URLs are also checked against the
hosted-host restriction above.
Live provider eval proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, or `openai-eval://` ref. It proves that hosted provider
credentials and selected models were exercised outside quick local CI; local,
mock, and free-form placeholders are invalid.
Run `backend/scripts/hosted_provider_live_eval_probe.py` with hosted provider
credentials to produce the sanitized JSON evidence that can be stored behind
this proof ref. The runner does not mint or fake the proof ref.
Pgvector recall proof must be an auditable `runbook://`, `https://`, or
`ci-artifact://` ref. It proves that hosted PostgreSQL has the vector
extension, `semantic_embeddings.embedding_vector`, the dimension-specific HNSW
index, and the runtime semantic recall path exercised outside local smoke;
local, mock, and free-form placeholders are invalid.
Run `backend/scripts/hosted_pgvector_recall_probe.py` against the hosted
database and smoke project to produce the JSON evidence that can be stored
behind this proof ref. The runner does not mint or fake the proof ref.
Observability pipeline proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `prometheus://`, `grafana://`, or `otel://` ref. It proves
that hosted metrics scraping, trace sampling, and alert-state inspection are
available from the deployed system; local, mock, and free-form placeholders are
invalid.
Run `backend/scripts/hosted_observability_pipeline_probe.py` against the hosted
metrics, traces, and alert/dashboard surfaces to produce the sanitized JSON
evidence that can be stored behind this proof ref:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_HOSTED_METRICS_URL=https://api.sextantlabs.net/metrics \
SEXTANT_HOSTED_TRACES_URL=https://api.sextantlabs.net/observability/traces \
SEXTANT_ALERTING_DASHBOARD_URL=https://api.sextantlabs.net/observability/alerts \
SEXTANT_OBSERVABILITY_REQUIRED_METRICS=sextant_api_requests_total \
SEXTANT_OBSERVABILITY_TRACES_EXPECT=trace_sample_count \
SEXTANT_OBSERVABILITY_ALERTS_EXPECT=active_alert_count \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_observability_pipeline_probe.py
```

`--check-config` validates production mode and hosted HTTPS endpoint shape
without network requests. The full command fetches the hosted surfaces,
requires configured metrics and optional trace/dashboard markers, emits byte
counts and SHA-256 response fingerprints only, and does not print response
bodies, tokens, dashboard content, or mint/fake
`SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`.
External smoke proof must be an auditable `runbook://`, `https://`, or
`ci-artifact://` ref. It proves that the hosted smoke path ran or is wired into
release automation outside the local repository; local, mock, and free-form
placeholders are invalid. A smoke URL by itself is only a target, not evidence
that the hosted smoke path has run.
Clean-context UI acceptance proof must be an auditable `runbook://`,
`https://`, or `ci-artifact://` ref to a browser-only walkthrough report. It
must come from outside the local source/code inspection path and is only an
evidence pointer; final acceptance still requires the separate clean-context
UI walkthrough required by `PLAN.md`.
To validate the hosted acceptance artifact shape and archive hash-only
evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_URL=https://app.example.com \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+deploy \
SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF=ci-artifact://prod/sextant/clean-context-ui/2026-06-19 \
SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_ARTIFACT_URL=https://ci.example.com/prod/sextant/clean-context-ui-2026-06-19.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_clean_context_acceptance_probe.py
```

`--check-config` validates production mode, hosted deployment/artifact URLs,
proof-ref scheme, timeout, expected statuses, and minimum step count without
network requests. The full command fetches the hosted JSON artifact, verifies
deployment/version match, pass status, browser/computer-use reviewer mode, no
source/docs inspection, final built UI usage, empty failure list, required
workflow checks, and walkthrough step count. It emits only host/hash/count/
status evidence and does not print step text, report notes, bearer tokens, raw
proof refs, or mint/fake `SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF`.
SourceDelta search reindex proof must be an auditable `runbook://`,
`https://`, or `ci-artifact://` ref. It proves the production reindex command
below ran against the hosted database/object store, or recorded an audited
no-op for a fresh deployment. Local, mock, and free-form placeholders are
invalid.
Object-store read/write proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `s3://`, `gs://`, or `azure-blob://` ref. It proves that the
hosted object-store adapter wrote, read, and validated an object through the
deployed bucket/prefix and runtime credentials. IAM proof alone is only a
permission/configuration reference; local, mock, and free-form read/write
placeholders are invalid.

To validate the hosted object-store IAM artifact shape and archive hash-only
evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+deploy \
SEXTANT_OBJECT_STORE_ROOT=s3://sextant-prod/objects \
SEXTANT_OBJECT_STORE_IAM_PROOF_REF=cloudflare-r2://sextant-prod-wnam-objects/runtime-token \
SEXTANT_OBJECT_STORE_IAM_ARTIFACT_URL=https://app.sextantlabs.net/readiness/object-store-iam.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_object_store_iam_probe.py
```

`--check-config` validates production mode, deployment version, `s3://`
object-store root, proof-ref scheme, hosted artifact URL, timeout, expected
statuses, minimum policy statement count, and minimum runtime principal count
without network requests. The full command fetches the hosted JSON artifact,
verifies deployment version, provider, object-store root, attached/ready
status, policy statement count, and runtime principal count, then emits only
host/hash/status/provider/count evidence. It does not print policy documents,
principal ids, account ids, bearer tokens, raw proof refs, or mint/fake
`SEXTANT_OBJECT_STORE_IAM_PROOF_REF`. For Cloudflare R2, the proof ref names
the bucket and runtime token/principal label, while the hosted artifact records
only sanitized status, location, permission summary, and count evidence.

To produce the object-store read/write proof artifact, run the hosted probe
against the deployed production environment:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_object_store_probe.py
```

`--check-config` validates production mode, `s3://` object-store configuration,
and hosted S3-compatible endpoint shape without writing objects. The full
command writes and reads a proof object through the production object-store
adapter, emits sanitized JSON evidence with the object ref and payload hash,
and must be archived behind `SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF`; the
runner does not mint or fake that proof ref.
Invitation delivery evidence must identify a real external delivery provider:
`ses://`, `sendgrid://`, `postmark://`, `mailgun://`, `smtp-tls://`, or
`supabase-auth://` with a provider-specific target. Invitation delivery proof
must be an auditable `runbook://`, `https://`, `ci-artifact://`, or
provider-specific
`ses://`/`sendgrid://`/`postmark://`/`mailgun://`/`smtp-tls://`/`supabase-auth://` ref with a
non-empty target. Token issuer proof must be an auditable `runbook://`,
`https://`, `ci-artifact://`, `auth0://`, `cognito://`, `okta://`, or
`clerk://`, or `supabase://` reference with a non-empty target. `local://`, `mock://`,
free-form strings, and other placeholders are invalid even when
`--allow-blocked` is used.
Do not embed credentials in these refs. The API rejects invitation provider,
target, issuer, delivery-proof, and token-proof refs that include URL userinfo,
params, query strings, or fragments, because those values are persisted in
ProjectInvitation, idempotency, audit, and authorized read-model responses.
Use hosted artifact bearer-token configuration or provider/runtime identity for
private artifact access instead of signed proof-ref URLs.

To validate the hosted invitation delivery artifact shape and archive hash-only
evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.07.01+vps.74.211.103.250 \
SEXTANT_INVITATION_DELIVERY_PROVIDER=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email \
SEXTANT_INVITATION_DELIVERY_PROOF_REF=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/20260701T100523Z \
SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL=https://app.sextantlabs.net/readiness/invitation-delivery.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_invitation_delivery_probe.py
```

`--check-config` validates production mode, deployment version, provider/proof
schemes, hosted artifact URL, timeout, expected statuses, and minimum message
count without network requests. The full command fetches the hosted JSON
artifact, verifies deployment version, provider match, sent/delivered status,
and message count, then emits only host/hash/count/status evidence. It does
not print recipients, message bodies, provider batch ids, bearer tokens, raw
proof refs, or mint/fake `SEXTANT_INVITATION_DELIVERY_PROOF_REF`.

To validate the hosted token-issuer artifact shape and archive hash-only
evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+deploy \
SEXTANT_SESSION_ISSUER=https://auth.example.com/ \
SEXTANT_SESSION_AUDIENCE=sextant-api \
SEXTANT_TOKEN_ISSUER_PROOF_REF=supabase://ientixxmbdeoqdmkublx/auth \
SEXTANT_TOKEN_ISSUER_ARTIFACT_URL=https://ci.example.com/prod/sextant/token-issuer-2026-06-19.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_token_issuer_probe.py
```

`--check-config` validates production mode, deployment version, hosted issuer,
audience, proof-ref scheme, hosted artifact URL, timeout, expected statuses,
and minimum token count without network requests. The full command fetches the
hosted JSON artifact, verifies deployment version, issuer, audience,
issued/success status, and token count, then emits only host/hash/count/status
evidence. It does not print token material, subject identities, bearer tokens,
raw proof refs, or mint/fake `SEXTANT_TOKEN_ISSUER_PROOF_REF`.

Session-provider provisioning proof must be an auditable `runbook://`,
`https://`, `ci-artifact://`, `auth0://`, `cognito://`, `okta://`, `clerk://`,
or `supabase://` ref. It proves the hosted tenant/client/JWKS configuration
was provisioned outside the local repository. The session-provider admin URL is
a target for operations, not provisioning evidence by itself.

To validate the hosted session-provider provisioning artifact shape and archive
hash-only evidence, run:

```bash
SEXTANT_RELEASE_ENVIRONMENT=production \
SEXTANT_DEPLOYMENT_VERSION=2026.06.19+deploy \
SEXTANT_SESSION_ISSUER=https://auth.example.com/ \
SEXTANT_SESSION_JWKS_URL=https://auth.example.com/.well-known/jwks.json \
SEXTANT_SESSION_PROVIDER_ADMIN_URL=https://auth.example.com/admin \
SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF=supabase://ientixxmbdeoqdmkublx/auth \
SEXTANT_SESSION_PROVIDER_PROVISIONING_ARTIFACT_URL=https://ci.example.com/prod/sextant/session-provider-2026-06-19.json \
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_session_provider_provisioning_probe.py
```

`--check-config` validates production mode, deployment version, hosted issuer,
hosted JWKS/admin URLs, proof-ref scheme, hosted artifact URL, timeout,
expected statuses, and minimum client count without network requests. The full
command fetches the hosted JSON artifact, verifies deployment version,
provider, issuer, JWKS URL, admin URL, provisioned/ready status, and client
count, then emits only host/hash/status/provider/client-count evidence. It
does not print tenant ids, client ids, private notes, bearer tokens, raw proof
refs, or mint/fake `SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF`.

To produce the session-provider readiness evidence artifact, run:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_session_provider_probe.py
```

The runner checks hosted issuer/JWKS/admin surfaces and proof-ref shape, emits
hash-only evidence for JWKS/admin responses and raw proof refs, and must be
archived with the session-provider provisioning record. Invitation delivery and
token minting require separate external proof artifacts; this probe does not
execute or fake those providers.

After applying migration `9f0b7c1a2d3e`, run the SourceDelta search reindex
against the same production database and object store to backfill existing
rows:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/reindex_source_delta_search.py
```

The command reads `SEXTANT_DATABASE_URL` and `SEXTANT_OBJECT_STORE_ROOT`, fails
if production configuration is missing or local, fails if an indexed
SourceDelta object is missing, and reports the updated row count.
New SourceDelta writes populate `submitted_text_search` transactionally.
S3-compatible object-store clients use bounded timeout/retry settings:
`SEXTANT_S3_CONNECT_TIMEOUT_SECONDS` defaults to `10`,
`SEXTANT_S3_READ_TIMEOUT_SECONDS` defaults to `30`, and
`SEXTANT_S3_MAX_ATTEMPTS` defaults to `3`. Keep these explicit in maintenance
commands when validating R2/S3 connectivity.
Hosted readiness requires `SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF`
because successful local command shape is not evidence that the hosted reindex
operation ran after deployment.

To produce the hosted proof artifact, run the hosted probe after the migration
with the deployed production environment:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_source_delta_reindex_probe.py
```

`--check-config` validates production mode, hosted PostgreSQL, and `s3://`
object storage without touching the database or object store. The full command
uses the same production reindex path, emits sanitized JSON evidence, and must
be archived behind `SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF`; use `--all`
when the hosted proof should demonstrate a full rebuild of rows that are
already indexed. The runner does not mint or fake that proof ref.

## Hosted Evidence Inventory

Hosted release evidence must cover:

- managed PostgreSQL;
- archived hosted PostgreSQL readiness evidence from the managed database;
- provisioned S3-compatible object storage bucket and IAM credentials;
- OpenAI API key secret materialization into the runtime environment;
- session/JWKS provider;
- secret manager and hosted access proof;
- backup target;
- hosted pgvector extension/index and semantic recall proof;
- hosted metrics scraper, dashboards, trace backend, alert routing, and
  archived observability pipeline probe proof;
- deployment environment and archived deployment approval/change-control proof;
- archived hosted session-provider JWKS/admin readiness evidence;
- external smoke target URL and proof;
- clean-context UI acceptance proof;
- SourceDelta search reindex proof;
- hosted backup/restore and rollback execution proof.

The current production env and progress log contain evidence for these hosted
gates as of the 2026-07-02 checkpoint, but this runbook is still an interface
document rather than proof by itself. A release claim must cite the current
probe output or the archived `docs/progress-log.md` evidence and must not infer
readiness from this checklist alone.
