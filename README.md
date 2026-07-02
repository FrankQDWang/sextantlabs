# Sextant Labs

Sextant is an external long-term memory and writing agent system for fiction authors. Its goal is not to take over authorship, but to provide traceable, correctable, POV-aware story memory and local continuation assistance while the author writes.

## Current Repository

The repository is organized into source contracts and implementation surfaces:

- `GOAL.md`: macro goal for the Sextant Memory system.
- `AGENT_GOAL.md`: macro goal for the writing agent.
- `goals/`: Memory, Agent, and Storytelling Control domain design.
- `experience/`: product experience contracts.
- `implementation/`: production engineering specifications.
- `PLAN.md`: complete production implementation plan.
- `AGENTS.md`: operating manual for Codex / AI coding agents.
- `docs/`: progress, gaps, readiness review, and implementation decisions.
- `backend/`: Python modular monolith implementation surface.
- `web/`: Vite + React writing workbench prototype and production client surface.

The earlier documentation and web prototype work has been merged to `main`. The next implementation goal must not treat the prototype as the final scope.

## Current Architecture Correction

The repository now contains the local thin-harness + rich-skills architecture required by the source contracts, including the Story Skill runtime and resolver surfaces that earlier documentation identified as missing.

Implemented infrastructure now includes provider ports/adapters, prompt files, prompt hash locking, first-class `StorySkillRegistry` metadata, `run_skill(...)` runtime, Resolver planning, `SkillRun` persistence, replay-diff evaluation, real-corpus chapter/slice boundary eval assets, RRF keyword+embedding fusion, sliding-window context organization, worker handlers, and the broader source/evidence/review/memory/graph implementation.

Current hosted readiness, deployment-alignment, acceptance-matrix, browser-only hosted UI evidence, and final verification results are recorded in `docs/progress-log.md`. For this checkpoint, the final verification command set passed after the latest status-document edits.

Local prose cue/regex inference in the source pipeline is not a valid completion path and must not be reintroduced.

## Agent Entry Point

For any long-horizon implementation run, read in this order:

1. `AGENTS.md`
2. `PLAN.md`
3. `GOAL.md`
4. `AGENT_GOAL.md`
5. every Markdown file under `goals/`
6. every Markdown file under `experience/`
7. every Markdown file under `implementation/`
8. `docs/`
9. `web/README.md`

`PLAN.md` requires complete source coverage. It must not be used to shrink the work to a local-only or mock-only flow.

Only the LLM/provider boundary may use deterministic local output. Persistence, API, workers, review, graph projection, auth, observability, deployment gates, and user-facing acceptance must use real implementations.

## Implementation Direction

The target is a complete production implementation:

```text
source material
  -> source normalization
  -> SourceDelta / SourceSpan
  -> evidence-backed memory writeback
  -> review and canon promotion policy
  -> MemoryPage / GraphProjection
  -> WritingContextPack
  -> Story Skill / Agent candidate
  -> author acceptance
  -> new source delta
```

The web workbench visual direction should be preserved, but its behavior must become real product behavior backed by domain state, persistence, API contracts, worker jobs, provider interfaces, review policy, and tests.

## Frontend Runbook

```bash
pnpm --dir web install
pnpm --dir web dev
```

Backend-backed local workbench runtime:

```bash
pnpm --dir web install
set -a; source .env; set +a  # optional: load configured provider settings
bash scripts/dev-workbench.sh
```

`scripts/dev-workbench.sh` runs Alembic, seeds a backend workbench project,
validates the DB worker handler catalog, starts the DB worker loop, starts
FastAPI, and starts Vite in API mode with generated `VITE_SEXTANT_*`
configuration. By default it uses local SQLite/object storage under
`.sextant/dev-workbench`; set `SEXTANT_DATABASE_URL` and
`SEXTANT_OBJECT_STORE_ROOT` to run the same UI session against PostgreSQL or
another configured object-store path. Use `--prepare-only` to validate
migrations, seed data, worker health, and Vite API-mode environment without
starting long-running processes. The seed emits current scene and POV character
IDs so Ask Memory, Scene Card, and story-action requests use the same persisted
scene context in API mode.
For Bailian/DashScope model runs, copy `.env.example` to `.env`, fill only
`SEXTANT_OPENAI_API_KEY`, and keep `SEXTANT_OPENAI_BASE_URL` pointed at the
OpenAI-compatible endpoint. The runtime still validates provider output before
memory, canon, review, graph, or accepted-text side effects.

Frontend verification:

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
pnpm --dir web test
pnpm --dir web test:e2e
```

The Playwright e2e command starts a migrated local FastAPI app, DB worker loop, and Vite app in backend API mode. It is not a demo-only smoke.

## Backend Runbook

Use the local Homebrew Python to avoid macOS code-signing failures from uv-managed CPython on this machine:

```bash
uv run --python /opt/homebrew/bin/python3 pytest backend/tests
uv run --python /opt/homebrew/bin/python3 ruff check backend/src backend/tests backend/migrations backend/scripts
uv run --python /opt/homebrew/bin/python3 ty check backend/src
uv run --python /opt/homebrew/bin/python3 tach check
uv run --python /opt/homebrew/bin/python3 semgrep --config .semgrep/sextant.yml backend/src --error --quiet
uv run --python /opt/homebrew/bin/python3 alembic upgrade head
uv run --python /opt/homebrew/bin/python3 python backend/scripts/generate_api_artifacts.py
uv run --python /opt/homebrew/bin/python3 python backend/scripts/production_smoke.py
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_external_smoke.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_worker_capacity_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_object_store_iam_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_object_store_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_secret_manager_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_session_provider_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_session_provider_provisioning_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_invitation_delivery_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_token_issuer_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_postgres_readiness_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_source_delta_reindex_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_pgvector_recall_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_provider_live_eval_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_deployment_approval_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_clean_context_acceptance_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/hosted_rollback_drill_probe.py --check-config
uv run --python /opt/homebrew/bin/python3 python backend/scripts/worker_healthcheck.py
uv run --python /opt/homebrew/bin/python3 python backend/scripts/reindex_source_delta_search.py
bash scripts/postgres-smoke.sh
bash scripts/pgvector-smoke.sh
bash scripts/source-delta-reindex-smoke.sh
```

The default Alembic URL targets PostgreSQL. For local SQLite migration checks, pass `SEXTANT_DATABASE_URL`, as the backend test suite does.
Run the SourceDelta search reindex command after deploying the search-index
migration to backfill existing rows from object storage; new SourceDelta writes
populate the search index transactionally.
When `SEXTANT_RELEASE_ENVIRONMENT=production`, the reindex command rejects
missing or local DB/object-store configuration and requires PostgreSQL plus
`s3://` object storage.
S3-compatible object-store reads use bounded client settings:
`SEXTANT_S3_CONNECT_TIMEOUT_SECONDS` defaults to `10`,
`SEXTANT_S3_READ_TIMEOUT_SECONDS` defaults to `30`, and
`SEXTANT_S3_MAX_ATTEMPTS` defaults to `3`. Keep these explicit in hosted
maintenance runs so R2/S3 connectivity failures return an actionable error
instead of hanging a reindex, worker, or restore process.
`backend/scripts/production_smoke.py` is a local production-path smoke check;
it refuses `SEXTANT_RELEASE_ENVIRONMENT=production` and does not replace
hosted external smoke.
The FastAPI runtime exposes `GET /health` as an unauthenticated liveness
endpoint for load balancers and external smoke targeting. It returns only
`status`, `service`, `api_version`, `release_environment`, and
`deployment_version`; it does not include database URLs, object-store refs,
JWKS URLs, credentials, manuscript text, or worker/readiness claims. Treat it
as process liveness only, not as evidence that persistence, workers,
observability, or the full evidence path have passed.
`backend/scripts/hosted_external_smoke.py` is the hosted API smoke runner. It
requires a hosted HTTPS API base URL, a pre-provisioned smoke project id, and a
real bearer token. It creates a source through the deployed API, waits for the
hosted worker job, reads the MemoryWritebackPreview, asks an evidence-backed
MemoryAnswer, and emits JSON evidence. `--check-config` validates URL/token/
project configuration without network requests. The runner rejects localhost
and local-address smoke URLs, and it does not create or fake the hosted
external-smoke proof ref.
`backend/scripts/hosted_worker_capacity_probe.py` is the hosted worker-capacity
probe. It reads a hosted worker Prometheus metrics endpoint, requires
successful worker job metrics, enforces a configurable average queue-age
threshold, and emits JSON evidence for capacity-proof archival. `--check-config`
validates the hosted metrics URL and thresholds without network requests. The
probe rejects localhost and local-address metrics URLs and does not create or
fake `SEXTANT_WORKER_CAPACITY_PROOF_REF`.
`backend/scripts/hosted_object_store_probe.py` is the hosted object-store
read/write proof runner. It requires production mode and an `s3://`
`SEXTANT_OBJECT_STORE_ROOT`, rejects local S3-compatible endpoints, writes and
reads a proof object through the production object-store adapter, and emits
JSON evidence with the object ref, byte count, and payload hash. The proof
payload itself is not printed. `--check-config` validates production S3
configuration without writing or reading objects. The runner does not create
or fake `SEXTANT_OBJECT_STORE_READ_WRITE_PROOF_REF`.
`backend/scripts/hosted_object_store_iam_probe.py` is the hosted object-store
IAM proof runner. It requires production mode, deployment version,
`SEXTANT_OBJECT_STORE_ROOT`, an auditable `SEXTANT_OBJECT_STORE_IAM_PROOF_REF`,
and a hosted JSON artifact URL when the proof ref is not itself `https://`. It
fetches the hosted artifact, verifies deployment version, provider, object-store
root, attached/ready status, minimum policy statement count, and minimum runtime
principal count, and emits sanitized JSON evidence with hashes, status,
provider, and counts only. It does not print policy documents, principal ids,
account ids, bearer tokens, raw proof refs, or create/fake
`SEXTANT_OBJECT_STORE_IAM_PROOF_REF`. Cloudflare R2 IAM proof refs use
`cloudflare-r2://<bucket>/<principal>` and are validated through a sanitized
hosted artifact such as `https://app.sextantlabs.net/readiness/object-store-iam.json`.
`backend/scripts/hosted_secret_manager_probe.py` is the hosted secret-manager
access proof runner. It requires production mode and a
`SEXTANT_SECRET_MANAGER_REF` using `aws-secretsmanager://`,
`gcp-secretmanager://`, `vault://`, or `supabase-vault://`, rejects local Vault
targets, reads the secret through the production secret resolver, and emits
redacted JSON evidence with the ref scheme, ref fingerprint, and byte count. It
never prints the secret value or full secret ref. Supabase Vault refs are shaped
as `supabase-vault://<project-ref>/<secret-name>` and are read through
`SEXTANT_SUPABASE_VAULT_DATABASE_URL` or `SEXTANT_DATABASE_URL`. `--check-config`
validates the hosted secret manager ref without reading the secret. The runner
does not create or fake `SEXTANT_SECRET_MANAGER_ACCESS_PROOF_REF`.
`backend/scripts/hosted_session_provider_probe.py` is the hosted
session-provider readiness runner. It requires production mode, hosted
`SEXTANT_SESSION_ISSUER`, hosted `SEXTANT_SESSION_JWKS_URL`, hosted
`SEXTANT_SESSION_PROVIDER_ADMIN_URL`, session-provider provisioning evidence,
an invitation delivery provider ref, invitation delivery proof ref, and token
issuer proof ref. The full
runner fetches the hosted JWKS and admin surfaces, requires at least one JWKS
signing key, and emits sanitized JSON evidence with hosts, response hashes,
key counts, and proof-ref fingerprints only. It does not print bearer tokens,
JWK material, admin response bodies, or raw proof refs, and it does not send
invitations, mint tokens, or create/fake hosted session-provider proof.
`backend/scripts/hosted_session_provider_provisioning_probe.py` is the hosted
session-provider provisioning proof runner. It requires production mode,
deployment version, hosted session issuer, hosted JWKS URL, hosted session
provider admin URL, an auditable session-provider provisioning proof ref, and a
hosted JSON artifact URL when the proof ref is not itself `https://`. It
accepts `supabase://` proof refs for Supabase Auth deployments. It
fetches the hosted artifact, verifies deployment version, provider, issuer,
JWKS URL, admin URL, provisioned/ready status, and minimum client count, and
emits sanitized JSON evidence with hosts, hashes, status, provider, client
count, and proof-ref scheme only. It does not print tenant ids, client ids,
bearer tokens, private notes, raw proof refs, or create/fake
`SEXTANT_SESSION_PROVIDER_PROVISIONING_PROOF_REF`.
`backend/scripts/hosted_invitation_delivery_probe.py` is the hosted
invitation-delivery proof runner. It requires production mode, deployment
version, an external delivery provider URI, an auditable invitation-delivery
proof ref, and a hosted JSON artifact URL when the proof ref is not itself
`https://`. It fetches the hosted artifact, verifies deployment version,
provider match, sent/delivered status, and minimum message count, and emits
sanitized JSON evidence with hashes, status, provider scheme, host, and message
count only. It does not print recipient addresses, message bodies, provider
batch ids, bearer tokens, raw proof refs, or create/fake
`SEXTANT_INVITATION_DELIVERY_PROOF_REF`. For current production smoke
readiness, Supabase Auth admin invite evidence uses `supabase-auth://`
invitation delivery refs and a hosted artifact under
`https://app.sextantlabs.net/readiness/invitation-delivery.json`. Invitation
provider, target, issuer, delivery-proof, and token-proof refs used by the API must be durable
identifiers only; refs with URL userinfo, params, query strings, or fragments
are rejected before DB/audit/API persistence so signed URLs or embedded tokens
cannot become project-visible evidence refs.
`backend/scripts/hosted_token_issuer_probe.py` is the hosted token-issuer proof
runner. It requires production mode, deployment version, hosted session issuer,
session audience, an auditable token-issuer proof ref, and a hosted JSON
artifact URL when the proof ref is not itself `https://`. It fetches the hosted
artifact, verifies deployment version, issuer, audience, issued/success status,
and minimum token count, and accepts `supabase://` proof refs for Supabase Auth
deployments. It emits sanitized JSON evidence with hashes, status,
issuer host, and token/subject counts only. It does not print token material,
subject identities, bearer tokens, raw proof refs, or create/fake
`SEXTANT_TOKEN_ISSUER_PROOF_REF`.
`backend/scripts/hosted_postgres_readiness_probe.py` is the hosted managed
PostgreSQL readiness runner. It requires
`SEXTANT_RELEASE_ENVIRONMENT=production`, a hosted PostgreSQL
`SEXTANT_DATABASE_URL`, and `SEXTANT_MANAGED_POSTGRES_INSTANCE` using a
managed-provider ref such as `rds://`, `cloudsql://`, `azure-postgres://`,
`neon://`, `supabase://`, or `crunchy-postgres://`. The full runner connects
to the hosted database, verifies the current Alembic head, and checks minimum
SourceDelta, SourceSpan, MemoryPage, and SourceSpan -> RawSource resolution
row counts. It emits sanitized JSON evidence with the database host, sanitized
URL, managed-instance scheme/fingerprint, migration version, and row counts.
It does not print database passwords or the raw managed-instance ref, and it
does not create or fake hosted managed PostgreSQL proof.
`backend/scripts/hosted_source_delta_reindex_probe.py` is the hosted
SourceDelta search reindex proof runner. It requires
`SEXTANT_RELEASE_ENVIRONMENT=production`, a hosted PostgreSQL database URL,
and `s3://` object storage, runs the production reindex path, and emits
sanitized JSON evidence for archival behind
`SEXTANT_SOURCE_DELTA_SEARCH_REINDEX_PROOF_REF`. Use `--all` when the proof
needs to show a full rebuild of already-indexed rows. `--check-config`
validates the hosted production configuration without connecting to the
database or object store. The runner rejects local database hosts and does not
create or fake the proof ref.
`backend/scripts/hosted_pgvector_recall_probe.py` is the hosted pgvector recall
proof runner. It requires `SEXTANT_RELEASE_ENVIRONMENT=production`, a hosted
PostgreSQL database URL, `SEXTANT_VECTOR_INDEX_PROVIDER=pgvector`, a configured
embedding provider/model/dimensions, and
`SEXTANT_PGVECTOR_RECALL_PROJECT_ID`. It verifies the `vector` extension,
`semantic_embeddings.embedding_vector`, the HNSW index, persisted vector rows,
and a pgvector nearest-neighbor self-recall query, then emits sanitized JSON
evidence with hashed project/embedding identifiers. `--check-config` validates
the hosted production configuration without connecting to the database. The
runner rejects local database hosts and does not create or fake
`SEXTANT_PGVECTOR_RECALL_PROOF_REF`.
`backend/scripts/hosted_provider_live_eval_probe.py` is the hosted live provider
eval proof runner. It requires `SEXTANT_RELEASE_ENVIRONMENT=production`,
OpenAI-backed StoryDraft, Memory Extraction, POV Detection, Event Aggregation,
and Embedding providers, selected models, embedding dimensions, and a
materialized OpenAI credential or supported AWS/GCP/Vault/Supabase Vault secret
ref. It calls the production provider factories, exercises each provider with a bounded
non-private sample, and emits sanitized JSON evidence with output shapes and
fingerprints only. It does not print prompts, provider raw output, manuscript
text, API keys, or secret refs, and it does not create or fake
`SEXTANT_PROVIDER_LIVE_EVAL_PROOF_REF`.
`backend/scripts/hosted_observability_pipeline_probe.py` is the hosted
observability pipeline proof runner. It requires
`SEXTANT_RELEASE_ENVIRONMENT=production`, hosted metrics, traces, and
alert/dashboard HTTPS URLs, and optional bearer-token access. It fetches the
hosted surfaces, requires configured Prometheus metric names, optionally checks
trace/dashboard response markers, and emits sanitized JSON evidence with byte
counts and SHA-256 body fingerprints only. It does not print response bodies,
tokens, dashboard content, or create/fake
`SEXTANT_OBSERVABILITY_PIPELINE_PROOF_REF`. The self-hosted default surfaces
are the API `/metrics`, `/observability/traces`, and `/observability/alerts`
endpoints; trace samples contain path templates, status, duration, and hashed
trace/span identifiers only.
`backend/scripts/hosted_deployment_approval_probe.py` is the hosted deployment
approval proof runner. It requires production mode, deployment version, an
auditable deployment approval/change-control proof ref, and a hosted JSON
approval artifact URL when the proof ref is not itself `https://`. It fetches
the hosted artifact, verifies deployment version, approved status, and approver
count, and emits sanitized JSON evidence with hashes, status, version, host,
and approver count only. It does not print approval bodies, approver identities,
bearer tokens, raw proof refs, or create/fake
`SEXTANT_DEPLOYMENT_APPROVAL_PROOF_REF`.
`backend/scripts/hosted_clean_context_acceptance_probe.py` is the hosted
clean-context UI acceptance proof runner. It requires production mode, hosted
deployment URL, deployment version, an auditable clean-context acceptance proof
ref, and a hosted JSON acceptance artifact URL when the proof ref is not itself
`https://`. It fetches the hosted artifact, verifies deployment/version
matching, pass status, browser/computer-use reviewer mode, no source/docs
inspection, final built UI usage, empty failure list, required workflow checks,
and minimum walkthrough steps, then emits sanitized JSON evidence with hashes,
hosts, counts, status, and reviewer mode only. It does not print step text,
report notes, bearer tokens, raw proof refs, or create/fake
`SEXTANT_CLEAN_CONTEXT_UI_ACCEPTANCE_PROOF_REF`; it validates an external
acceptance artifact and does not replace the final browser/computer-use
walkthrough.
The PostgreSQL smoke command requires Docker or Podman. It starts a real
`postgres:16` container, runs Alembic against PostgreSQL, runs the production
smoke path, runs the worker healthcheck against the same PostgreSQL database,
performs `pg_dump`, restores into a second database, and verifies restored
SourceDelta and MemoryPage rows plus restored SourceSpan -> RawSource /
SourceVersion resolution. The production smoke path covers candidate
generation, draft-local check-risk review, partial candidate acceptance, worker
memory writeback, preview evidence, graph projection, and an evidence-backed
MemoryAnswer query.
`backend/scripts/hosted_backup_restore_probe.py` is the hosted backup/restore
proof runner. It requires `SEXTANT_RELEASE_ENVIRONMENT=production`, hosted
primary and scratch restore PostgreSQL URLs, `SEXTANT_BACKUP_TARGET=s3://...`,
and hosted S3 access. It runs `pg_dump` for the configured application schema
set, defaulting to `public`, and includes required application extensions,
defaulting to `vector:public,pg_trgm:public`. It uploads the dump to the backup
target, downloads it back, restores it with `psql` into the scratch database,
and verifies restored SourceDelta rows, MemoryPage rows, and SourceSpan ->
RawSource resolution. It emits sanitized JSON evidence with backup object ref,
byte count, SHA-256 hash, and restored row counts only; it does not print dump
contents, database passwords, or create/fake `SEXTANT_BACKUP_RESTORE_PROOF_REF`.
`backend/scripts/hosted_rollback_drill_probe.py` is the hosted rollback drill
proof runner. It requires production mode, a hosted rollback status URL, the
current deployment version, a distinct target rollback version, an auditable
rollback runbook ref, and a real deployment rollback command. It fetches the
hosted status URL before rollback, executes the rollback command without a
shell, polls until the hosted status reports the target version and expected
health, and emits sanitized JSON evidence with hashes, versions, host, and exit
code only. It does not print command output, bearer tokens, status response
bodies, raw runbook refs, or create/fake `SEXTANT_ROLLBACK_EXECUTION_PROOF_REF`.
The pgvector smoke command requires Docker or Podman and the
`pgvector/pgvector:pg17` image. It runs Alembic against a real pgvector-enabled
PostgreSQL database, refreshes persisted semantic embeddings, creates the
dimension-specific HNSW expression index
`ix_semantic_embeddings_embedding_vector_hnsw`, verifies `<=>` ranking through
the runtime semantic recall path, and checks that MemoryAnswer can answer an
existing SourceSpan-backed open-thread query through pgvector recall.
The SourceDelta reindex smoke command requires Docker or Podman. It starts a
real PostgreSQL container, runs Alembic, seeds a SourceDelta whose submitted
text lives in object storage, executes the production reindex CLI, and verifies
the rebuilt `submitted_text_search` value in PostgreSQL.
The worker healthcheck validates database connectivity, production job-handler
coverage against the documented job catalog, queue counts, and stale running-job
signals. It exits non-zero on missing handlers, unexpected handlers, DB errors,
or invalid runtime provider/object-store configuration.

Core verification:

```bash
bash scripts/verify-core.sh
```

Production configuration validation:

```bash
bash scripts/validate-production-config.sh
bash scripts/validate-hosted-readiness.sh --allow-blocked
```

Local development must explicitly use `SEXTANT_AUTH_MODE=header-dev`, where API
tests and seed scripts pass `X-Actor-Id`. Production configuration must use
`SEXTANT_AUTH_MODE=jwt-jwks` with `SEXTANT_SESSION_ISSUER`,
`SEXTANT_SESSION_AUDIENCE`, an HTTPS `SEXTANT_SESSION_JWKS_URL`, and
`SEXTANT_ADMIN_ACTOR_IDS` for system-level Story Schema Genre Pack provisioning;
API clients then send expiring JWTs as `Authorization: Bearer <token>`.
Production configuration must also declare `SEXTANT_OBSERVABILITY_EXPORTER` as
`none` or `otlp`; OTLP export requires an HTTPS `SEXTANT_OTLP_ENDPOINT`.
Production semantic retrieval must declare
`SEXTANT_EMBEDDING_PROVIDER=openai`, `SEXTANT_EMBEDDING_MODEL`, and positive
`SEXTANT_EMBEDDING_DIMENSIONS`, plus
`SEXTANT_VECTOR_INDEX_PROVIDER=pgvector`; local deterministic embeddings are
allowed only for development, tests, and evals at the provider boundary.
`scripts/validate-hosted-readiness.sh` is the hosted release gate. In strict
mode it fails until deployment URL, managed Postgres evidence, object-store IAM
proof, object-store read/write proof, secret manager ref, secret-manager
access proof, live provider eval proof, pgvector recall proof, session
provider, session-provider provisioning proof, invitation delivery proof,
invitation/token issuance proof artifacts, hosted metrics/traces/alerts, observability
pipeline proof, worker capacity proof, deployment approval proof,
backup/restore proof, rollback
runbook, rollback execution proof, external smoke URL, external smoke proof,
clean-context UI acceptance proof, and SourceDelta search reindex proof are
provided. Local verification
uses `--allow-blocked` to record those missing external blockers without
pretending hosted deployment has passed.
Managed Postgres evidence must identify a hosted provider such as `rds://`,
`cloudsql://`, `azure-postgres://`, `neon://`, `supabase://`, or
`crunchy-postgres://`. Object-store IAM, object-store read/write,
backup/restore, and rollback proof refs must be auditable `runbook://`,
`https://`, `ci-artifact://`, or provider-specific cloud proof URIs such as
`cloudflare-r2://`, not local/free-form placeholders. When those proof refs use `https://`, they must
follow the same hosted-host restriction as hosted service URLs. Hosted proof
and runbook refs must not carry URL userinfo, params, query strings, or
fragments; use bearer-token configuration, provider identity, or the hosted
artifact runner settings for private artifact access instead. The readiness
gate and direct hosted proof-probe configuration parsers enforce this rule.
Hosted proof artifact URLs must follow the same rule; signed-query URLs and
embedded userinfo credentials are rejected. Worker capacity proof must be an auditable
`runbook://`, `https://`,
`ci-artifact://`, `k8s://`, `ecs://`, or `cloud-run://` reference.
Use `backend/scripts/hosted_backup_restore_probe.py` with a pre-provisioned
scratch restore database to produce JSON evidence for the backup/restore proof
reference.
Use `backend/scripts/hosted_rollback_drill_probe.py` with hosted deployment
status and rollback tooling to produce JSON evidence that can be archived
behind the rollback execution proof reference.
Use `backend/scripts/hosted_object_store_probe.py` against the hosted
bucket/prefix to produce the JSON evidence that can be stored behind the
object-store read/write proof reference.
Use `backend/scripts/hosted_object_store_iam_probe.py` against the hosted
object-store IAM artifact to produce sanitized IAM/policy attachment evidence
for the object-store IAM proof reference. For Cloudflare R2, use a
`cloudflare-r2://<bucket>/<principal>` proof ref plus a hosted artifact that
records bucket, token/principal label, status, location, permission summary, and
counts without exposing token values or account ids.
Use `backend/scripts/hosted_worker_capacity_probe.py` against the hosted worker
metrics endpoint to produce JSON evidence that can be archived behind that
proof reference.
Use `backend/scripts/hosted_session_provider_probe.py` against the hosted
issuer/JWKS/admin surfaces to produce sanitized session-provider readiness
evidence. Use
`backend/scripts/hosted_session_provider_provisioning_probe.py` against the
hosted session-provider provisioning artifact to prove the tenant/client/JWKS
configuration record matches the deployment. Use
`backend/scripts/hosted_invitation_delivery_probe.py` against the hosted
invitation delivery artifact to produce sanitized delivery proof evidence. Use
`backend/scripts/hosted_token_issuer_probe.py` against the hosted token-issuer
artifact to produce sanitized issuance proof evidence.
These do not replace real external invitation delivery, token minting, or the
separate clean-context UI acceptance proof.
Use `backend/scripts/hosted_postgres_readiness_probe.py` against the managed
hosted PostgreSQL database to produce sanitized readiness evidence for the
managed Postgres deployment record. This evidence is tied to
`SEXTANT_MANAGED_POSTGRES_INSTANCE`; it is not a local database substitute and
the runner does not mint a proof ref.
Deployment approval proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `change-request://`, `github-deployment://`, or
`github-run://` reference. It proves an external release approval or deployment
record exists; local/free-form placeholders do not count. Use
`backend/scripts/hosted_deployment_approval_probe.py` against the hosted
approval/change-control artifact to produce sanitized evidence that can be
archived behind or alongside that proof ref.
Secret-manager access proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `aws-iam://`, `gcp-iam://`, or `vault-policy://` reference.
It proves the hosted runtime identity has permission to read the configured
secret manager; a syntactically valid secret ref alone is not enough. Use
`backend/scripts/hosted_secret_manager_probe.py` against the configured hosted
secret manager to produce the redacted JSON evidence that can be stored behind
that proof reference.
Live provider eval proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, or `openai-eval://` reference; local/free-form placeholders
do not count.
Use `backend/scripts/hosted_provider_live_eval_probe.py` with hosted provider
credentials to produce JSON evidence that can be archived behind that proof
reference.
Pgvector recall proof must be an auditable `runbook://`, `https://`, or
`ci-artifact://` reference that proves hosted vector extension/index and
semantic recall execution; local/free-form placeholders do not count.
Use `backend/scripts/hosted_pgvector_recall_probe.py` against the hosted
database and smoke project to produce JSON evidence that can be archived behind
that proof reference.
Observability pipeline proof must be an auditable `runbook://`, `https://`,
`ci-artifact://`, `prometheus://`, `grafana://`, or `otel://` reference that
proves hosted scraping, trace export/sampling, alert routing, and dashboard
wiring; local/free-form placeholders do not count.
Use `backend/scripts/hosted_observability_pipeline_probe.py` against the hosted
metrics/traces/alerts surfaces to produce JSON evidence that can be archived
behind that proof reference.
External smoke proof must be an auditable `runbook://`, `https://`, or
`ci-artifact://` reference that proves the hosted smoke path ran or is wired
into release automation; a URL alone is not enough, and local/free-form
placeholders do not count. Use
`backend/scripts/hosted_external_smoke.py` against the deployed API to produce
the JSON evidence that can be stored behind that proof reference.
Clean-context UI acceptance proof must be an auditable `runbook://`,
`https://`, or `ci-artifact://` reference to a browser-only walkthrough report.
It does not replace the final clean-context acceptance requirement; it prevents
hosted readiness from passing without an external acceptance artifact. Use
`backend/scripts/hosted_clean_context_acceptance_probe.py` against the hosted
acceptance artifact to validate deployment/version match, browser/computer-use
scope, required workflow checks, persistence/review/evidence confirmation, and
sanitized proof output.
SourceDelta search reindex proof must be an auditable `runbook://`, `https://`,
or `ci-artifact://` reference that proves the production reindex operation ran,
or recorded an audited no-op, after the search-index migration. Use
`backend/scripts/hosted_source_delta_reindex_probe.py` against the hosted
database/object store to produce the JSON evidence that can be stored behind
that proof reference.
Hosted HTTPS URLs for deployment, session/JWKS, metrics, traces, dashboards,
and external smoke must not point at localhost, `.local`, loopback, link-local,
or unspecified hosts.
Invitation evidence must use an external delivery-provider URI such as
`ses://`, `sendgrid://`, `postmark://`, `mailgun://`, `smtp-tls://`, or
`supabase-auth://`; token
issuer proof must use an auditable `runbook://`, `https://`, Auth0, Cognito,
Okta, Clerk, or Supabase reference. Local/mock placeholders are rejected even in
`--allow-blocked` mode.
Session-provider provisioning proof uses the same auditable `runbook://`,
`https://`, `ci-artifact://`, Auth0, Cognito, Okta, or Clerk reference shape;
`https://` refs follow the hosted-host restriction. The admin URL alone is a
target, not proof that hosted tenant/client/JWKS provisioning ran.
Hosted deployment is blocked when these required values are missing or invalid.
Current hosted evidence is tracked in `docs/progress-log.md` and validated by
`scripts/validate-hosted-readiness.sh`.

## Documentation Check

```bash
git diff --check -- AGENTS.md PLAN.md README.md PRODUCT.md docs experience goals implementation web backend pyproject.toml tach.toml alembic.ini
```

## Current Gaps

The current repository contains strong source documentation, a web workbench,
and an initial backend spine with project-membership authorization, JWT/JWKS
bearer-token verification for production mode, project metadata reads,
DB-backed project member list/upsert/revoke APIs, DB-backed project invitation
intent/list records plus external delivery/token proof recording that still
does not send invitations or mint tokens itself,
ActionRequest detail reads, idempotent write replay, local and S3 object-store
adapters, source import/versioning/archive/restore/diff and source detail
reads, SourceDelta APIs, DB-indexed cursor pagination/search for SourceDelta
history with a production reindex command, candidate lifecycle operation APIs with
latest-SourceVersion stale-base protection, source/job/review/writeback read
APIs, MemoryPage list/detail read APIs, DB-backed job cancel/retry controls
with running-job cancellation acknowledgement, worker retry budgets for provider
and infrastructure failures, production job-type constraints and payload
step/version validation, dedicated SourceVersion normalization, source
structure split, SourceDelta ingress scheduling for normalization/split,
scene SourceSpan pipeline chaining, and memory writeback, English/Chinese
mention extraction, alias resolution with provisional CanonicalEntity linking,
canonical entity refs for SourceSpan-derived facts/graph/context, conservative
near-spelling alias-conflict ReviewItems, canonical entity list/search API,
source/version-filtered scene list API for author-facing boundary selectors,
author alias-correction review operations with graph rebuild, MemoryPage
rewrite jobs, and same-project disguise-arc scene-boundary correction, explicit
scene POV metadata/title/diary/perspective binding,
self-named first-person POV binding, unidentified first-person POV mode
detected explicit-speaker first-person POV binding, unidentified first-person
POV mode detection, conservative inner/sensory focus POV binding, persistent POV
confidence/evidence fields, model-assisted POV detection provider boundary,
scene location binding, event
extraction, explicit scene time/tone/function metadata parsing, event
aggregation, event relation fact derivation, explicit SourceSpan
character-knowledge fact derivation including Chinese explicit
knowledge-state statements plus false-belief and misunderstanding statements,
scene mention
`appears_in` fact derivation, explicit object-transfer owner fact
derivation, non-exclusive relation-aware conflict policy, structured `FACT:`
directive isolation from scene mention extraction, English recipient-side
transfer owner derivation, travel
`located_in` state fact derivation, Chinese particle/trailing-verb mention
filtering, effective-schema mention/event/relation extraction templates for
project-specific mention refs, custom event candidates, and custom relation
facts, relation-aware MemoryPage section rewrite, GraphProjection rebuild,
WritingContextPack build with derived
character agency state and persisted StoryChapter/StoryScene position/POV
metadata fallback plus scene-scoped active characters from canon `appears_in`
facts, POV allowed/forbidden knowledge, and POV sensory/inner-access
constraints, relevance-ranked canon/risk/event/object/style context sections,
AliasRecord/MemoryPage read-only semantic recall for WritingContextPack
ranking, estimated-token budgeted WritingContextPack snapshots,
data-derived Storytelling Control records for role slots, casting,
scene/sequel mode, dramatic behavior, scene-local new-character seeds, and
ProseRenderingContract, Agent candidate generation, and draft-local
AgentReview job handling,
DB-backed SkillRun replay eval worker handling with hash-only audit,
ProseRenderingContract hard_no/forbidden-knowledge/target-range/non-POV/
inner-state-budget/style/no-turn/cast-policy draft review, StoryDraftResult
non-empty text/structured-text/finish-reason plus text-consistency validation
contract-metadata validation, and review-cue schema/enum/mapping validation
before DraftCandidate persistence with bounded invalid-output retry and failed
SkillRun audit for rejected provider output, request metrics/safe-log middleware
with Prometheus text export for API errors, core ActionRequest/Candidate/
ContextPack/MemoryWriteback latencies, LLM validation failures, canon-promotion
blocks, OpenAI provider token/cost metrics, sanitized `/observability/traces`
and `/observability/alerts` endpoints, and worker job outcome/queue-age metrics
through an optional worker `/metrics` endpoint,
AliasRecord/EventCandidate/CanonicalEvent state
gates and database status constraints, MemoryWritebackPreview decision
persistence with authored correction forms and replacement refs, fact accept
promotion, ReviewItem preview retention/dismissal side effects,
SourceSpan/EvidenceLog preview dispute propagation, MemoryPage/GraphProjection
preview side-effect handling, ContextPackReadiness persistence, consumption,
read API, Scene Card status UI, and author review/writeback stale readiness
marking, SourceSpan-backed MemoryPage open-thread author operations, fact/review deduplication across grouped
writeback and source-pipeline paths, fact plus non-fact preview UI actions, formal
ReviewItem operations with direct stale propagation and split/merge
replacement SourceDelta validation, durable replacement evidence retention,
and queued memory-page/graph rebuild side effects, evidence-backed MemoryAnswer and
WritingContextPack APIs with current scene/POV context, scene/chapter-local and
explicit-boundary/evidence-window disguise-arc alias narrowing,
event/object/style aggregation, ActionRequest
ask_memory-to-MemoryAnswer, check_risk-to-AgentReviewFinding,
suggest_next_direction-to-BeatCandidate, explain_candidate-to-CandidateExplanation,
revise_candidate-to-DraftCandidate runs, dedicated `/agent/*` wrapper APIs,
draft-local
ActionRequest-to-DraftCandidate generation with hard_no contract violation
blocking plus target-range, non-POV, inner-state-budget, style, no-turn, and
cast-policy risk surfacing, production OpenAI StoryDraft provider wiring,
production OpenAI POV detection provider wiring, production OpenAI Memory
Extraction provider wiring and worker-side output validation, production
OpenAI Event Aggregation provider wiring and worker-side evidence validation,
generated API artifacts, emitted API error-code matrix coverage,
worker/writeback/replay-eval tests, provider golden tests, versioned prompt
registry and prompt lock tests, local production
smoke with candidate review and evidence-backed MemoryAnswer coverage, a
PostgreSQL container smoke plus backup/restore gate, CI/security workflow
definitions, and guardrail checks.

Candidate acceptance, direct SourceDelta writes, imported source creation,
in-editor source edits, and SourceVersion restore now materialize
SourceVersion/SourceDelta evidence and enqueue source normalization plus memory
writeback, while stale direct SourceDelta writes are rejected before side
effects. The workbench API
mode drives ContextPack-backed Scene Card state, Ask MemoryAnswer questions
through ActionRequest, Ask candidate generation, WritingContextPack detail
viewing, ActionRequest-backed candidate explanation and revision, review detail
with canonical resolution selection, authored review notes, replacement
SourceDelta refs, split/merge SourceDelta validation, alias-conflict
CanonicalEntity correction, backend scene option loading for disguise-arc
scene-boundary correction, explicit matching-disguise-arc bulk boundary
application,
scene-boundary side-effect inspection,
candidate reject-to-archive/override/accept, stale SourceVersion refresh/rebase recovery,
source list/search/create/archive with imported-source writeback detail,
SourceVersion history reads, version switching, SourceVersion diff inspection,
in-editor SourceDelta-backed source edit save with stale edit recovery, draft
diff preview, and rejected-draft merge assistance, restore-to-new-version,
paginated SourceDelta history/filter/detail, MemoryPage list/detail inspection,
GraphProjection relationship inspection with search/status filters,
project member list/upsert/revoke through the Project Panel,
project invitation list/intent/proof recording through the Project Panel,
admin-provisioned Project Story Schema Genre Pack listing/selection plus
override reads and versioned writes through the project panel,
writeback accept/reject/correct decisions for fact, SourceSpan,
EvidenceLog, ReviewItem, MemoryPage, and GraphProjection preview items with
correction notes/replacement refs, SourceVersion-backed refresh persistence,
ContextPackReadiness pending/synced visibility in the Scene Card, and a
backend-backed project SourceVersion/SourceDelta history panel. MemoryAnswer
can infer simple author-question targets from existing fact refs, canonical
entity names, alias text, and MemoryPage vocabulary while still citing
SourceSpan evidence, and its API/UI response includes confidence,
affected entities, caveats, related ReviewItems, and POV safety.
When one matched alias or display-name surface points to multiple canonical
entities, MemoryAnswer now returns an `ambiguous_entity_match` unknown with the
candidate entity refs instead of combining facts across possible characters.
If the same question also explicitly names exactly one candidate entity display
name, the read-only answer narrows alias expansion to that entity instead of
promoting the alias globally or pulling in other candidates' facts.
For local alias scopes, the answer can also narrow an ambiguous alias only when
exactly one scene/chapter/character/disguise-scoped AliasRecord has
SourceSpan-backed evidence context matching the question, and it surfaces that
as a caveat instead of promoting the alias globally.
For `character_specific` aliases, the same read-only narrowing can use the
current POV only when the alias evidence SourceSpan belongs to a StoryScene
whose persisted `pov_character_id` matches the request's current POV character;
the answer still cites fact evidence and preserves POV safety checks. Scoped
alias answers cap MemoryAnswer confidence at the selected AliasRecord
confidence so a proposed local alias cannot look stronger than its alias
evidence.
First-appearance source lookup questions such as "where does Mira first
appear?" can answer from resolved StoryMention rows, cite the first SourceSpan,
and return the CanonicalEntity ref without creating canon facts or graph state.
Character-knowledge MemoryAnswer questions can list what a character knows,
suspects, misunderstands, or explicitly does not know by following active
CharacterKnowledge rows back to SourceSpan-backed FactAssertions. Sortable
CanonicalEvent timeline questions such as "what happened after X?" can answer
from canon/external-canon/author-note events while citing anchor and result
SourceSpans and surfacing a scene-order caveat. During/while event questions
can return same-scene, same-story-time, or explicit same-prefix numeric
`story_time` range CanonicalEvents while citing both the anchor and overlapping
event SourceSpans. Relationship MemoryAnswer
questions such as "why are X and Y enemies?" can answer from SourceSpan-backed
relationship facts plus supporting CanonicalEvents without treating
GraphProjection alone as fact evidence, including deterministic predicate
paraphrases such as betrayal or stopped trust and endpoint paraphrases backed
by persisted entity descriptions. Relationship evolution questions such
as "how did X and Y's relationship change over time?" can order historical and
current relationship facts by StoryChapter/StoryScene evidence, cite each
SourceSpan, and keep fact statuses visible. Relationship path questions such as
"how is X connected to Y?" can answer from a bounded multi-hop path across
SourceSpan-backed relationship facts while preserving endpoint order, citing
each link, resolving unambiguous AliasRecord endpoint names, and without using
GraphProjection as fact evidence; when competing paths exist it ranks them by
predicate-term match, canon status, confidence, path length, and stable ids
instead of insertion order. Continuity-check MemoryAnswer
questions can report existing open ReviewItems with new/existing SourceSpan evidence,
severity, affected refs, and related review ids without running a new scan.
Open-thread MemoryAnswer questions can answer from SourceSpan-backed
MemoryPage `open_threads`, returning the affected MemoryPage target and an
open-thread caveat without creating canon facts or review state; open threads
that reference open ReviewItems retain `answer_type='open_thread'` while
surfacing the related review id, `open_review_item` caveat, severity-calibrated
lower confidence, and POV-unsafety. Closed, resolved, dismissed, obsolete, or superseded
MemoryPage thread entries are excluded from open-thread answers, and questions
that name both a MemoryPage target and a specific unresolved subject filter and
rank the returned thread list by remaining focus tokens, open ReviewItem backing,
severity, thread-local SourceSpan evidence, and original order.
Generic fact MemoryAnswer questions can also use persisted semantic recall when
the author vocabulary does not lexically name an entity or predicate: the answer
selects existing SourceSpan-backed FactAssertions through the highest-scoring
semantic SourceSpan evidence bucket, cites the validated SourceSpan, and does
not create facts, review items, memory pages, graph edges, SourceDeltas, or
provider state. Semantic fact answers cap their returned confidence by the
SourceSpan semantic match score, so low-similarity recall cannot report a
higher confidence than the evidence match supports.
If the same semantic path finds multiple candidate fact subjects for an
underspecified question, MemoryAnswer asks for clarification with candidate
SourceSpan refs instead of concatenating the possible targets into a canon
answer.
Conflict policy can supersede older exclusive state facts when later scene
evidence proves natural time progression.

Current hosted readiness now has evidence for managed Postgres/pgvector, R2
object store and IAM, Supabase Vault provider secret runtime, Supabase Auth
session/token issuance, Supabase Auth admin invitation delivery, self-hosted
metrics/traces/alerts, deployment approval, external smoke, backup/restore,
rollback, SourceDelta reindex, worker capacity, provider live eval, and
deployed clean-context UI acceptance. Direct SSH to the VPS remains an
operational access gap; the current deployment used KiwiVM shell plus a private
R2 artifact handoff instead.
