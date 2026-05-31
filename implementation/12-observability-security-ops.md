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
