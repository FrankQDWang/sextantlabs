# 12. Observability, Security, and Operations

Sextant stores sensitive creative material. Production readiness requires auditability without leaking manuscripts into logs.

## Request Trace

Every user-visible operation must carry:

```text
request_id
project_id
actor_id
action_request_id when present
source_delta_id when present
draft_candidate_id when present
skill_run_id when present
job_id when present
```

## Audit Events

Must audit:

```text
action request submitted
draft candidate generated
agent review finding generated
candidate accepted/rejected/overridden
source delta created
source span extracted
memory writeback completed
conflict policy decision
canon promotion
review item created/resolved/dismissed/superseded
prompt version used
LLM structured output validation failure
provider retry/terminal failure
```

Audit events store refs and hashes, not full manuscript text.

## Logging Rules

Allowed in normal logs:

```text
ids
counts
durations
status
error code
hashes
object store refs
short bounded text preview only when explicitly safe
```

Forbidden in normal logs:

```text
full manuscript text
full prompt input
full LLM raw output
provider credentials
object store signed URLs
private author notes
```

Full prompt snapshots and raw outputs go to controlled object store with refs.

Runtime provider factories accept materialized OpenAI API keys from
`SEXTANT_OPENAI_API_KEY` or `OPENAI_API_KEY`, a real AWS Secrets Manager
reference, a GCP Secret Manager reference, or a HashiCorp Vault reference in
`SEXTANT_LLM_API_KEY_SECRET_REF`:

```text
aws-secretsmanager://<region>/<secret-id>?json_key=<field>
gcp-secretmanager://<project-id>/<secret-id>?version=<version>
vault://<host>/<secret-path>?field=<field>
```

The AWS path is implemented in infra with boto3, reads `SecretString` or
`SecretBinary`, rejects empty values, and never exposes credentials outside the
provider adapter boundary. The GCP path is implemented in infra with
`google-cloud-secret-manager`, uses application-default credentials or the
runtime service account configured for the deployment, reads
`projects/<project-id>/secrets/<secret-id>/versions/<version>`, defaults version
to `latest`, rejects empty values, and keeps credentials inside the provider
adapter boundary. The Vault path calls the HTTPS Vault API at
`/v1/<secret-path>`, sends `SEXTANT_VAULT_TOKEN`, supports KV-v2
`data.data.<field>` payloads, rejects empty values, and keeps credentials inside
the provider adapter boundary. The older `secret://...` form is only a
deployment materialization placeholder; provider startup still fails for it
unless the deployment has already materialized the key into
`SEXTANT_OPENAI_API_KEY` or `OPENAI_API_KEY`.

Runtime also rejects malformed secret refs that do not use the documented
`secret://` deployment materialization contract or the
`aws-secretsmanager://`, `gcp-secretmanager://`, or `vault://` production
secret-manager contracts.

Implemented API request logging uses `safe_log_event` and records only method,
route template, status, duration, request id, project id, and actor id. The
middleware does not read or serialize request bodies, so manuscript text,
prompt input, accepted text, and author notes cannot enter request logs through
the instrumentation path. Runtime enables request log emission only when
`SEXTANT_API_REQUEST_LOGS=1`; metrics counters are always created in-process.

Implemented API trace context support accepts a W3C `traceparent` header on
`/api/*` requests, preserves a valid upstream trace id, generates a fresh API
span id, and returns safe `traceparent` and `X-Trace-Id` response headers. If
the inbound trace header is missing or malformed, the API starts a fresh trace
context and does not echo the invalid payload. Safe request logs include only
the normalized trace id and span id, not the raw header or request body.

The FastAPI runtime exposes `GET /health` for process liveness. It is public,
outside the `/api/*` auth middleware, and returns only bounded deployment
metadata: `status`, `service`, `api_version`, `release_environment`, and
`deployment_version`. It must not expose database URLs, object-store refs,
session-provider URLs, credentials, manuscript text, prompt material, author
notes, provider output, queue payloads, or readiness claims for PostgreSQL,
object storage, workers, review, graph projection, or browser acceptance.

Production configuration validation requires `SEXTANT_OBSERVABILITY_EXPORTER`
to be declared as `none` or `otlp`. When `otlp` is selected,
`SEXTANT_OTLP_ENDPOINT` is required and must be HTTPS. This validates the
deployment interface without pretending an external collector, scraper,
dashboard, or alert route exists in the local repository.

## Metrics

Minimum production metrics:

```text
action request latency
candidate generation latency
LLM validation failure rate
skill retry count
memory writeback duration
review item creation rate
canon promotion blocked rate
job queue age
worker failure rate
provider cost
API error rate by code
```

Implemented in-process counters exported at `GET /metrics` in Prometheus text
format:

```text
sextant_api_requests_total{method,path,status}
sextant_api_errors_total{method,path,status}
sextant_application_errors_total{code,path,status}
sextant_action_request_latency_ms_count{action_type,trigger,status}
sextant_action_request_latency_ms_sum{action_type,trigger,status}
sextant_action_request_run_latency_ms_count{output_type,status}
sextant_action_request_run_latency_ms_sum{output_type,status}
sextant_candidate_acceptance_latency_ms_count{accept_mode,status}
sextant_candidate_acceptance_latency_ms_sum{accept_mode,status}
sextant_context_pack_build_latency_ms_count{mode,status}
sextant_context_pack_build_latency_ms_sum{mode,status}
sextant_memory_writeback_decision_latency_ms_count{decision,item_type,status}
sextant_memory_writeback_decision_latency_ms_sum{decision,item_type,status}
sextant_llm_validation_failures_total{surface}
sextant_canon_promotion_blocked_total{reason}
sextant_worker_jobs_total{job_type,status}
sextant_job_queue_age_seconds_count{job_type}
sextant_job_queue_age_seconds_sum{job_type}
sextant_provider_tokens_total{provider,model,skill,token_type}
sextant_provider_cost_microusd_total{provider,model,skill}
```

These metrics use route templates, enum/status values, and ids only; manuscript
text, prompt input, author notes, and provider raw output are not legal metric
labels. The API exposes these metrics at `GET /metrics`; the standalone worker
process exposes its own Prometheus endpoint when `SEXTANT_WORKER_METRICS_PORT`
is set. OpenAI provider adapters record provider token usage from the Responses
API usage object and estimate micro-USD cost only from configured per-1K-token
rates:

```text
SEXTANT_OPENAI_INPUT_MICRO_USD_PER_1K_TOKENS
SEXTANT_OPENAI_OUTPUT_MICRO_USD_PER_1K_TOKENS
```

Provider metrics are emitted from the same API or worker process registry that
owns the provider call. They use provider/model/skill/token-type labels only
and never include prompt input, manuscript text, accepted text, or raw model
output. Hosted scraping, external trace backend/export configuration, alert
rules, and dashboards remain production operations work.

## Security Boundaries

Data classes:

| Data | Sensitivity | Storage |
|---|---|---|
| manuscript text | high | object store + source refs |
| author notes | high | object store/source refs |
| prompt input snapshot | high | controlled object store |
| LLM raw output | high | controlled object store |
| structured extracted facts | medium/high | Postgres |
| audit event refs | medium | Postgres |
| generated client code | low | repo |

## Auth and Authorization

First stage:

```text
user owns project
project owns sources
project owns memory objects
project owns review items
```

Rules:

1. Every project-scoped query filters by project_id.
2. API rejects cross-project refs.
3. Worker validates project refs before processing.
4. Object store refs are not public URLs.
5. Production does not allow mock auth.
6. Local development may use `SEXTANT_AUTH_MODE=header-dev` with `X-Actor-Id`;
   production must use `SEXTANT_AUTH_MODE=jwt-jwks` and validate
   `Authorization: Bearer <token>` against issuer, audience, an HTTPS JWKS,
   and required JWT claims including `exp`.
7. The verified JWT subject becomes the authenticated actor for membership
   checks; client-supplied `X-Actor-Id` cannot override it in production mode.
8. Runtime configuration must declare auth mode explicitly; missing auth mode
   must not silently fall back to header-based development auth.
9. Project invitation delivery provider refs, delivery target refs, token
   issuer refs, delivery proof refs, and token proof refs must be durable
   identifiers only. They must not carry URL userinfo, params, query strings,
   or fragments, because those values are stored in ProjectInvitation rows,
   idempotency payloads, audit decisions, and authorized API read models.
   Hosted artifact access must use separate bearer-token configuration or
   provider credentials, never embedded proof-ref credentials.
10. Hosted readiness proof refs, runbook refs, and the invitation delivery
    provider ref must also be durable identifiers only. They must reject URL
    userinfo, params, query strings, and fragments even when
    `--allow-blocked` is used, because blocker-recording mode cannot be allowed
    to normalize credential-bearing proof material into release evidence. The
    hosted proof runners must enforce the same rule on their direct proof-ref
    configuration before they fetch artifacts or emit sanitized evidence.
11. Hosted proof artifact URLs must also reject URL userinfo, params, query
    strings, and fragments. Private artifact fetches must use the
    probe-specific bearer token environment variable, provider IAM, or runtime
    identity rather than signed URLs that could be logged or copied into
    release records.

Hosted session-provider readiness proof can be generated with
`backend/scripts/hosted_session_provider_probe.py` against the configured
issuer, JWKS URL, and session-provider admin URL. The probe must require
production mode, hosted HTTPS issuer/JWKS/admin URLs, session-provider
provisioning evidence, invitation delivery provider/proof evidence, and token
issuer proof evidence; fetch the hosted JWKS and admin surfaces; require at least one
JWKS signing key; and emit sanitized JSON evidence with hosts, response hashes,
key counts, and proof-ref fingerprints only. It must not print bearer tokens,
JWK material, admin response bodies, raw proof refs, local auth fixtures, or
fabricate invitation delivery/token issuance readiness.

Hosted invitation delivery proof can be validated with
`backend/scripts/hosted_invitation_delivery_probe.py` against the hosted
external delivery artifact. The probe must require production mode, deployment
version, an external delivery provider URI, an auditable invitation-delivery
proof ref, and a hosted artifact URL when the proof ref is not itself HTTPS. It
must fetch the hosted JSON artifact, verify deployment version, provider match,
sent/delivered status, and minimum message count, and emit sanitized evidence
with artifact/proof hashes, status, provider scheme, host, and message count
only. It must not print recipient addresses, message bodies, provider batch
ids, bearer tokens, raw proof refs, or fabricate invitation delivery proof.

Hosted token issuer proof can be validated with
`backend/scripts/hosted_token_issuer_probe.py` against the hosted external
token issuance artifact. The probe must require production mode, deployment
version, hosted session issuer, session audience, an auditable token-issuer
proof ref, and a hosted artifact URL when the proof ref is not itself HTTPS. It
must fetch the hosted JSON artifact, verify deployment version, issuer,
audience, issued/success status, and minimum token count, and emit sanitized
evidence with hosts, hashes, counts, and status only. It must not print token
material, subject identities, bearer tokens, raw proof refs, or fabricate token
issuance readiness.

Hosted session-provider provisioning proof can be validated with
`backend/scripts/hosted_session_provider_provisioning_probe.py` against the
hosted external provisioning artifact. The probe must require production mode,
deployment version, hosted session issuer, hosted JWKS URL, hosted session
provider admin URL, an auditable session-provider provisioning proof ref, and a
hosted artifact URL when the proof ref is not itself HTTPS. It must fetch the
hosted JSON artifact, verify deployment version, provider, issuer, JWKS URL,
admin URL, provisioned/ready status, and minimum client count, and emit
sanitized evidence with hosts, hashes, status, provider, and client count only.
It must not print tenant ids, client ids, private notes, bearer tokens, raw
proof refs, or fabricate session-provider provisioning readiness.

## Secrets

Provider credentials:

1. stored in deployment secret manager,
2. read only by infra adapters,
3. never committed,
4. never exposed to domain/application/skills,
5. rotated without code change.

## Object Store

Object store contains:

```text
raw source text
processed markdown view
raw offset maps
accepted text refs
candidate text refs
prompt input snapshots
LLM raw output audit records
large eval artifacts
```

Objects must be keyed by project and content hash or id. Deletion policy must account for audit requirements.

## Backups

Production backup includes:

```text
Postgres database
object store bucket
migration version
deployment version
```

Recovery test must prove SourceSpan can still resolve to raw text after restore.

Hosted managed PostgreSQL readiness proof can be generated with
`backend/scripts/hosted_postgres_readiness_probe.py` against the production
database identified by `SEXTANT_MANAGED_POSTGRES_INSTANCE`. The probe must
require production mode, a hosted PostgreSQL URL, a managed-provider instance
ref, and positive minimum row thresholds; reject local database hosts; verify
database connectivity and the current Alembic head; check SourceDelta,
SourceSpan, MemoryPage, and SourceSpan -> RawSource resolution counts; and emit
sanitized JSON evidence with database host, sanitized URL, migration version,
managed-instance scheme/fingerprint, and row counts only. It must not print
database credentials, raw managed-instance refs, manuscript text, or fabricate
readiness proof.

Hosted object-store IAM proof can be validated with
`backend/scripts/hosted_object_store_iam_probe.py` against the hosted external
IAM/policy artifact. The probe must require production mode, deployment
version, `s3://` object-store root, an auditable object-store IAM proof ref,
and a hosted artifact URL when the proof ref is not itself HTTPS. It must
fetch the hosted JSON artifact, verify deployment version, provider,
object-store root, attached/ready status, minimum policy statement count, and
minimum runtime principal count, and emit sanitized evidence with hosts,
hashes, status, provider, and counts only. It must not print policy documents,
principal ids, account ids, bearer tokens, raw proof refs, or fabricate
object-store IAM readiness.

Hosted backup/restore proof can be generated with
`backend/scripts/hosted_backup_restore_probe.py` against production PostgreSQL,
a separate scratch restore PostgreSQL database, and the configured S3 backup
target. The probe must require production mode, hosted database hosts,
`SEXTANT_BACKUP_TARGET=s3://...`, and hosted S3 endpoint shape; run `pg_dump`;
upload and download the dump through the backup target; restore with `psql`;
verify restored SourceDelta rows, MemoryPage rows, and SourceSpan -> RawSource
resolution; and emit sanitized JSON evidence with backup object ref, byte
count, SHA-256 dump hash, and restored row counts only. It must not print dump
contents, database credentials, local backup paths, or fabricate readiness
proof.

Hosted deployment approval proof can be validated with
`backend/scripts/hosted_deployment_approval_probe.py` against the hosted
approval/change-control artifact. The probe must require production mode,
deployment version, an auditable deployment approval proof ref, and a hosted
artifact URL when the proof ref is not itself HTTPS. It must fetch the hosted
JSON artifact, verify deployment version, approved status, and minimum approver
count, and emit sanitized JSON evidence with artifact/proof hashes, status,
version, host, and approver count only. It must not print approval bodies,
approver identities, bearer tokens, raw proof refs, or fabricate readiness
proof.

Hosted clean-context UI acceptance proof can be validated with
`backend/scripts/hosted_clean_context_acceptance_probe.py` against the hosted
browser/computer-use acceptance artifact. The probe must require production
mode, hosted deployment URL, deployment version, an auditable clean-context
acceptance proof ref, and a hosted artifact URL when the proof ref is not
itself HTTPS. It must fetch the hosted JSON artifact, verify deployment URL and
version, pass status, browser/computer-use reviewer mode, final built UI usage,
no source/docs inspection, empty failure list, required workflow checks, and a
minimum walkthrough step count. It must emit sanitized evidence with hosts,
hashes, counts, status, and reviewer mode only. It must not print step text,
report notes, bearer tokens, raw proof refs, or fabricate readiness proof; it
validates an external artifact and does not replace the final clean-context UI
walkthrough.

Hosted rollback drill proof can be generated with
`backend/scripts/hosted_rollback_drill_probe.py` against hosted deployment
status and deployment rollback tooling. The probe must require production mode,
a hosted rollback status URL, the current deployment version, a distinct target
rollback version, an auditable rollback runbook ref, and a rollback command that
references the target version. It must fetch hosted status before rollback,
execute the rollback command without a shell, poll until hosted status reports
the target version and expected health, and emit sanitized JSON evidence with
host, versions, hashes, poll count, and command exit code only. It must not
print command output, bearer tokens, hosted status bodies, raw runbook refs, or
fabricate `SEXTANT_ROLLBACK_EXECUTION_PROOF_REF`.

## Deployment Units

First stage:

```text
backend API container
worker container
Postgres
object store
Redis optional
static web hosting
```

No Kubernetes-only assumption in first stage.

## Smoke Tests

Staging/production smoke:

1. Create project.
2. Save source text.
3. Build SourceSpan.
4. Ask evidence-backed question.
5. Generate DraftCandidate with mocked or test provider.
6. Accept candidate into SourceDelta.
7. Confirm MemoryWritebackPreview or ReviewItem appears.

Hosted external smoke uses `backend/scripts/hosted_external_smoke.py` against a
pre-provisioned project in the deployed API. It must authenticate with a real
bearer token, create source material through the API, wait for hosted worker
writeback, read MemoryWritebackPreview evidence, and ask a SourceSpan-backed
MemoryAnswer. The command emits JSON evidence for an auditable external-smoke
proof ref and must reject local/loopback smoke URLs. It does not replace live
provider eval proof or clean-context browser acceptance.

Hosted worker-capacity proof can be generated with
`backend/scripts/hosted_worker_capacity_probe.py` against the deployed worker
Prometheus endpoint. The probe must authenticate when the metrics endpoint is
protected, reject local/loopback metrics URLs, require successful worker job
metrics, enforce a bounded average queue-age threshold, and emit JSON evidence
for an auditable worker-capacity proof ref. It must not connect to local
databases, start workers, or fabricate readiness proof.

Hosted object-store read/write proof can be generated with
`backend/scripts/hosted_object_store_probe.py` against the deployed S3 bucket
and prefix. The probe must require production mode and an `s3://` object-store
root, reject local S3-compatible endpoints, write and read a proof object
through the production object-store adapter, and emit JSON evidence with the
proof object ref and payload hash while omitting manuscript/probe payload text.
It must not use local object storage or fabricate readiness proof.

Hosted secret-manager access proof can be generated with
`backend/scripts/hosted_secret_manager_probe.py` against the configured secret
manager ref. The probe must require production mode and an
`aws-secretsmanager://`, `gcp-secretmanager://`, or `vault://` ref, reject
local Vault targets, read the secret through the same production secret
resolver used by provider startup, and emit redacted JSON evidence without the
secret value or full secret ref. It must not use local secret material or
fabricate readiness proof.

Hosted SourceDelta search reindex proof can be generated with
`backend/scripts/hosted_source_delta_reindex_probe.py` after the search-index
migration is deployed. The probe must require production mode, hosted
PostgreSQL, and S3 object storage, reject local database hosts, run the same
production reindex path, and emit sanitized JSON evidence for an auditable
SourceDelta search reindex proof ref. It must not run against local
persistence, local object storage, or fabricate readiness proof.

Hosted pgvector recall proof can be generated with
`backend/scripts/hosted_pgvector_recall_probe.py` against the hosted PostgreSQL
database and smoke project. The probe must require production mode, hosted
PostgreSQL, `SEXTANT_VECTOR_INDEX_PROVIDER=pgvector`, the configured embedding
provider/model/dimensions, and a project id; reject local database hosts;
verify the `vector` extension, `semantic_embeddings.embedding_vector`, the HNSW
index, persisted vector rows, and a pgvector nearest-neighbor self-recall
query; and emit sanitized JSON evidence with hashed project and embedding ids.
It must not run against local persistence or fabricate readiness proof.

Hosted live provider eval proof can be generated with
`backend/scripts/hosted_provider_live_eval_probe.py` against production OpenAI
provider configuration. The probe must require production mode, OpenAI-backed
StoryDraft, Memory Extraction, POV Detection, Event Aggregation, and Embedding
providers, selected models, embedding dimensions, and a materialized OpenAI
credential or supported AWS/GCP/Vault secret ref; run the production provider
factories on bounded non-private samples; and emit sanitized JSON evidence with
output shapes and fingerprints only. It must not use deterministic local
providers, print prompts/raw provider output/manuscript text/secrets, or
fabricate readiness proof.

Hosted observability pipeline proof can be generated with
`backend/scripts/hosted_observability_pipeline_probe.py` against the hosted
metrics, traces, and alert/dashboard surfaces. The probe must require
production mode, hosted HTTPS endpoints, optional bearer-token access, and
configured Prometheus metric names; fetch each hosted surface; optionally check
trace/dashboard response markers; and emit sanitized JSON evidence with status
codes, byte counts, required metric names, series count, and SHA-256 response
fingerprints only. It must not print response bodies, tokens, dashboard
content, local endpoint data, or fabricate readiness proof.

## Incident Clues

High-priority alerts:

```text
canon promotion without evidence
ReviewItem created without SourceSpan
GraphProjection rebuild failure
SourceSpan raw offset map failure
LLM validation failure spike
job queue age over threshold
object store write failure
secret scan finding
```

## Acceptance

Ops/security work is complete when:

1. Normal logs contain no full manuscript text in tests.
2. Audit event can explain why a fact entered Memory.
3. Restore test proves SourceSpan -> RawSource resolution.
4. Cross-project access test fails correctly.
5. Production smoke test covers candidate acceptance and memory writeback.
