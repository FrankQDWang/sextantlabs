# 08. API Contracts

The API layer exposes structured actions, candidates, memory answers, review operations, and status views. It does not expose a raw database editing UI.

## API Rules

1. All write endpoints require project ownership.
2. All writes accept an idempotency key.
3. API routes do not commit DB transactions directly.
4. API routes call application use cases.
5. OpenAPI is generated in CI and the frontend client is generated from it.

## Common Envelope

Request headers:

```text
Authorization: Bearer <token>   # production jwt-jwks mode
X-Actor-Id                      # local header-dev mode / generated client actor identity
X-Request-Id
Idempotency-Key
```

In production `jwt-jwks` mode, the backend derives the authenticated actor from
the verified JWT subject and rewrites the internal actor header before
authorization checks. `X-Actor-Id` alone is accepted only in local `header-dev`
mode.

Error shape:

```json
{
  "error": {
    "code": "stale_source_version",
    "message": "Target source version has changed.",
    "details": {}
  }
}
```

Typed error status mapping:

```text
400 unsupported_action_type
400 expected_output_mismatch
400 missing_target
400 invalid_target_range
400 schema_validation_failed
401 authentication_required
403 permission_denied
404 not_found
409 idempotency_conflict
409 invalid_state_transition
409 stale_source_version
409 source_version_already_current
409 candidate_not_offerable
409 blocked_without_override
409 policy_blocked_promotion
502 llm_output_invalid
```

## Project and Source APIs

```text
GET    /api/projects/{project_id}
GET    /api/projects/{project_id}/members
PUT    /api/projects/{project_id}/members/{member_actor_id}
POST   /api/projects/{project_id}/members/{member_actor_id}/revoke
GET    /api/projects/{project_id}/invitations
POST   /api/projects/{project_id}/invitations
POST   /api/projects/{project_id}/invitations/{invitation_id}/external-proof
POST   /api/projects/{project_id}/sources
GET    /api/projects/{project_id}/sources/{source_id}
GET    /api/projects/{project_id}/sources/{source_id}/versions
GET    /api/projects/{project_id}/sources/{source_id}/versions/{version_id}
GET    /api/projects/{project_id}/sources/{source_id}/versions/{base_version_id}/diff/{compare_version_id}
POST   /api/projects/{project_id}/source-deltas
GET    /api/projects/{project_id}/source-deltas
GET    /api/projects/{project_id}/source-deltas/{source_delta_id}
```

`GET /projects/{project_id}` returns project metadata for active project
members only:

```text
id
name
actor_role
created_at
```

It is read-only. It must not create idempotency records, audit events, evidence,
memory, canon, review, graph, or provider side effects.

`GET /projects/{project_id}/members` returns durable ProjectMembership rows for
active project members:

```text
id
project_id
actor_id
role
status
created_at
```

`PUT /members/{member_actor_id}` creates, reactivates, or updates a member role
with idempotency and audit. `POST /members/{member_actor_id}/revoke` marks the
membership revoked with idempotency and audit. Both write routes require an
active owner/editor actor; only owners can grant or revoke owner membership;
the final active owner cannot be demoted or revoked. These endpoints mutate
only ProjectMembership, IdempotencyRecord, and AuditEvent rows. They must not
create SourceDelta, SourceSpan, EvidenceLogEntry, MemoryPage, ReviewItem,
FactAssertion, CanonPromotion, GraphProjection, provider, worker, or object-store
side effects.

`POST /projects/{project_id}/invitations` records an auditable invitation intent
for an actor id and requested project role. It requires owner/editor access;
only owners may invite owners. It validates production-shaped external
delivery-provider refs such as `ses://`, `sendgrid://`, `postmark://`,
`mailgun://`, `smtp-tls://`, or `supabase-auth://`, and token issuer refs such
as `auth0://`, `okta://`, `clerk://`, or `supabase://`. These refs must not
contain URL userinfo, params, query strings, or fragments, because they are durable DB/audit/API references
and must never carry credentials or bearer material. It returns a durable
`ProjectInvitation` row with `status=pending_external_delivery`,
`delivery_status=not_sent`, and `token_status=not_issued`. This endpoint
records intent only: it does not send email, mint a token, create
ProjectMembership, or create SourceDelta, SourceSpan, EvidenceLogEntry,
MemoryPage, ReviewItem, FactAssertion, CanonPromotion, GraphProjection,
provider, worker, or object-store side effects. Hosted delivery execution and
token issuance require external proof refs before they can count as complete.

`GET /projects/{project_id}/invitations` returns durable `ProjectInvitation`
rows for active project members. It is read-only and must not create
idempotency records, audit events, ProjectMembership, SourceDelta, SourceSpan,
EvidenceLogEntry, MemoryPage, ReviewItem, FactAssertion, CanonPromotion,
GraphProjection, provider, worker, or object-store side effects.

`POST /projects/{project_id}/invitations/{invitation_id}/external-proof`
records the auditable result of an external invitation-delivery/token-issuer
system after that system has run outside Sextant. It requires owner/editor
access, idempotency, a pending same-project `ProjectInvitation`, and
production-shaped proof refs such as hosted delivery-provider refs,
non-local `https://` refs, or `ci-artifact://` refs. Local/mock refs and
localhost proof URLs are rejected. Proof refs must also omit URL userinfo,
params, query strings, and fragments so signed URLs, tokens, or private
delivery details cannot be stored in ProjectInvitation, audit, idempotency, or
API read models. It updates only the `ProjectInvitation` delivery/token status
plus `IdempotencyRecord` and `AuditEvent`; it does not send email, mint a
token, create ProjectMembership, or create SourceDelta, SourceSpan,
EvidenceLogEntry, MemoryPage, ReviewItem, FactAssertion, CanonPromotion,
GraphProjection, provider, worker, or object-store side effects.

`GET /sources/{source_id}` returns the same durable source summary shape as the
source list endpoint for a single source, including archive state, latest
version metadata, and version count. It must reject cross-project source ids as
`not_found` after project membership succeeds, and must not create idempotency
records, audit events, evidence, memory, canon, review, graph, or provider side
effects.

`POST /source-deltas` accepts author text, import material, note, outline, or accepted candidate provenance.

It returns:

```text
source_delta_id
new_version_id
memory_writeback_job_id
```

`POST /sources` creates the initial `RawSource`, `SourceVersion`,
`SourceDelta`, and memory-writeback job for imported material. Its response
includes:

```text
source_id
version_id
source_delta_id
memory_writeback_job_id
raw_hash
```

`POST /sources/{source_id}/versions/{version_id}/restore` restores an older
SourceVersion as a new replace SourceDelta. The response includes:

```text
source_id
restored_from_version_id
source_delta_id
new_version_id
memory_writeback_job_id
```

The restored SourceVersion supersedes the latest version. It must not mutate the
historical SourceVersion row or bypass SourceDelta/writeback.

`GET /sources/{source_id}/versions/{base_version_id}/diff/{compare_version_id}`
returns a read-only SourceVersion line diff:

```text
source_id
base_version_id
compare_version_id
base_version_label
compare_version_label
base_raw_hash
compare_raw_hash
summary.insertions/deletions/changed
hunks[].lines[].kind/old_line/new_line/text
```

The endpoint reads durable SourceVersion text from object storage and must not
create SourceDelta, Job, MemoryPage, ReviewItem, or GraphProjection side
effects.

`POST /sources/{source_id}/versions/{version_id}/source-deltas` rejects stale
previous versions with `stale_source_version` when `version_id` is no longer
the latest SourceVersion for the source. The error details include
`previous_version_id` and `latest_version_id`, and the request must not create
SourceDelta, Job, MemoryPage, ReviewItem, or GraphProjection side effects.

`POST /source-deltas` and
`POST /sources/{source_id}/versions/{version_id}/source-deltas` also reject a
submitted `base_hash` that does not match the current `previous_version_id`
SourceVersion hash with `stale_source_version`. The error details include
`request_base_hash` and `current_hash`, and the request must not create
SourceDelta, Job, MemoryPage, ReviewItem, GraphProjection, idempotency, audit,
or object-store side effects.

`GET /source-deltas` returns newest-first SourceDelta summaries from the
database-backed read model. It accepts `source_id`, `source_version_id`,
`status`, `delta_kind`, `accepted_only`, `query`, `limit`, and opaque `cursor`
parameters. Text `query` uses the persisted `submitted_text_search` column and
production trigram index; the response includes `next_cursor` when another page
is available. Returned rows still read `submitted_text_ref` through object
storage for the visible preview.

## ActionRequest API

```text
POST /api/projects/{project_id}/action-requests
GET  /api/projects/{project_id}/action-requests/{action_request_id}
POST /api/projects/{project_id}/action-requests/{action_request_id}/run
```

`ActionRequest` DTO fields:

```text
source_id
source_version_id
scene_id
chapter_id
pov_character_id
actor_intent
trigger
action_type
target
constraints
expected_output
```

`GET /action-requests/{action_request_id}` returns the persisted structured
request for active project members, including the fields above plus
`action_request_id`, `project_id`, `status`, and `created_by`. It must reject
cross-project ActionRequest ids as `not_found` after project membership
succeeds, and must not create idempotency records, audit events, candidates,
SourceDeltas, evidence, memory, canon, review, graph, provider, worker, or
frontend-only side effects.

`run` returns one of:

```text
memory_answer
risk_findings
beat_candidates
draft_candidates
candidate_explanation
job_status
```

Long-running actions can return `job_status`.

Current ActionRequest write routes have API success side-effect matrix coverage.
The matrix covers `POST /action-requests`, all implemented direct
`POST /action-requests/{action_request_id}/run` output modes
(`ask_memory`, `check_risk`, `suggest_next_direction`,
`draft_next_passage`, `rewrite_current_page`, `explain_candidate`, and
`revise_candidate`), plus `/agent/check-risk`, `/agent/draft-next-passage`,
`/agent/rewrite-current-page`, and `/agent/suggest-next-beat` wrappers. Submit
creates exactly one ActionRequest, one idempotency record, and one audit event.
Direct runs record exactly one run idempotency record and one audit event plus
their output-specific persisted draft-local artifacts: MemoryAnswer writes no
answer row, risk checks write only AgentReviewFinding rows, beat suggestions
write one AgentContextPack plus StorytellingControls and BeatCandidates,
candidate-producing runs write one AgentContextPack plus StorytellingControls,
SkillRun, and DraftCandidate, explanations write no new candidate rows, and
candidate revision writes one replacement DraftCandidate while marking the
original revised. The `/agent/*` wrappers preserve the same output contracts
while adding the submit-side ActionRequest, idempotency, and audit side
effects. None of these ActionRequest success paths writes SourceDelta,
AcceptedFragment, MemoryPage, ReviewItem, FactAssertion, CanonPromotion,
GraphProjection, schema, or worker side effects.

## Candidate API

```text
GET  /api/projects/{project_id}/candidates/{candidate_id}
POST /api/projects/{project_id}/candidates/{candidate_id}/explain
POST /api/projects/{project_id}/candidates/{candidate_id}/revise
POST /api/projects/{project_id}/candidates/{candidate_id}/accept
POST /api/projects/{project_id}/candidates/{candidate_id}/reject
POST /api/projects/{project_id}/candidates/{candidate_id}/override-block
```

Accept input:

```json
{
  "accepted_text_ref": "object://...",
  "accept_mode": "partial",
  "target_source_id": "...",
  "target_version_id": "...",
  "insert_or_replace_range": {"start": 100, "end": 120},
  "source_scope": "user_draft",
  "author_edited": true
}
```

Accept output:

```text
accepted_fragment_id
source_delta_id
memory_writeback_job_id
```

Accept failure examples:

```text
blocked_without_override
stale_source_version
invalid_target_range
candidate_not_offerable
```

`stale_source_version` is returned when the candidate target version/base hash
does not match the accept request or when the target SourceVersion has already
been superseded. Superseded-version responses include
`candidate_target_version_id` and `latest_version_id` in `error.details`.

Reject output:

```text
candidate_id
status=archived
author_action=reject
```

`POST /candidates/{candidate_id}/reject` is an authenticated, idempotent author
operation. It records the rejection action and stores the candidate in terminal
`archived` state, but it must not create AcceptedFragment, SourceDelta,
SourceSpan, EvidenceLogEntry, ReviewItem, FactAssertion, MemoryPage,
CanonPromotion, GraphProjection, provider, or worker side effects.

Current Candidate write routes have API success side-effect matrix coverage.
The matrix runs candidate accept, reject, override-block, and revise through
FastAPI, application use cases, SQLAlchemy persistence, and local object
storage. Accept must be the only candidate operation that creates
AcceptedFragment, SourceDelta, a new SourceVersion, and writeback pipeline jobs;
reject and override-block must only update the original DraftCandidate; revise
must only archive the original attempt into `revised` state and create a new
offered DraftCandidate. All successful Candidate writes record exactly one
idempotency row and one audit event, and none may directly write MemoryPage,
ReviewItem, FactAssertion, CanonPromotion, GraphProjection, schema, or provider
state.

`POST /candidates/{candidate_id}/explain` returns the candidate detail and
evidence/risk refs needed for the author-facing "查看依据" surface. It is
read-only despite the command-style method: it must not run providers, create an
ActionRequest, create CandidateExplanation rows, mutate candidate state, or
write SourceDelta, Memory, Canon, ReviewItem, GraphProjection, audit, worker,
or idempotency records. `GET /candidates/{candidate_id}/explain` remains a
compatibility read alias for existing clients, but generated clients should use
the documented POST route.

## Project Story Schema API

```text
GET /api/projects/{project_id}/story-schema/packs
GET /api/projects/{project_id}/story-schema
POST /api/projects/{project_id}/story-schema/genre-packs
POST /api/projects/{project_id}/story-schema/genre-packs/{pack_id}/deprecate
PUT /api/projects/{project_id}/story-schema/genre-pack
PUT /api/projects/{project_id}/story-schema/project-override
```

`GET /story-schema/packs` returns active StorySchemaPack records visible to
the project. `pack_type=genre` lists global active Genre Packs that can be
selected for the project.

`POST /story-schema/genre-packs` is a system-admin, authenticated,
idempotent write that provisions a global active `genre` StorySchemaPack after
the same effective-schema relation/ref and extraction-hint validation used by
Project Overrides. Admin actors are configured by `SEXTANT_ADMIN_ACTOR_IDS`;
project membership alone is not enough for global provisioning.

`POST /story-schema/genre-packs/{pack_id}/deprecate` is a system-admin,
authenticated, idempotent write that marks an unused global Genre Pack
`deprecated`. The write is rejected while any active project binding still
references the pack, so an existing project's effective schema cannot be
silently changed by global deprecation.

`GET /story-schema` returns the active project binding ids, the current
Genre Pack and Project Override pack when they exist, and the effective Base +
Genre + Project Override schema used by extraction, validation, and
GraphProjection.

`PUT /story-schema/genre-pack` is an authenticated, idempotent project write
that selects or clears an active global Genre Pack by id. It creates a new
active ProjectStorySchemaBinding, supersedes the previous binding, preserves
the current Project Override pack ref, and returns the new effective schema.
Missing, deprecated, project-scoped, or non-genre pack ids return `not_found`
before binding changes. Malformed request bodies still use
`schema_validation_failed`.

`PUT /story-schema/project-override` is an authenticated, idempotent project
write. It versions a new `project_override` StorySchemaPack, supersedes the
previous active project binding, preserves the active Base and Genre pack
refs, and returns the new effective schema. The application validates the
merged schema before writing: names must be present, custom relation
subject/object role refs must be in the effective schema or documented
non-entity fact refs, `extraction_hints.relation_patterns` must point to
allowed relations and entity types, and
`extraction_hints.mention_patterns` must point to allowed entity types with a
`{mention}` template placeholder. `extraction_hints.event_patterns` must point
to allowed event types and entity types, use only `{subject}`, `{object}`, and
`{location}` placeholders, and include `{subject}`.
`extraction_hints.agency_profile_fields` may map project-defined labels to
allowed Character Agency Profile predicates such as `core_desire` and
`moral_boundary`; entries must have a valid `predicate` and non-empty string
`labels`.

Schema configuration endpoints must not create SourceDelta, SourceSpan,
EvidenceLogEntry, FactAssertion, ReviewItem, MemoryPage, CanonPromotion,
GraphProjection, or provider side effects. Browser clients call project schema
writes with `PUT`, so CORS configuration must include `PUT` in addition to
existing read/write methods.

Current Source and Project Story Schema write routes have API success
side-effect matrix coverage. The matrix runs each documented source/schema
write through FastAPI, application use cases, SQLAlchemy persistence, and local
object storage; it requires the expected durable row changes, exactly one
idempotency record, exactly one audit event, and no memory/canon/review/graph
side effects for schema-only writes.

Current Job and ReviewItem operation routes also have API success side-effect
matrix coverage. The matrix runs job cancel/retry and ReviewItem
dismiss/reopen/resolve through FastAPI, application use cases, and SQLAlchemy
persistence; each success path must record exactly one idempotency row and one
audit event, update only the target Job or ReviewItem row, and avoid creating
SourceDelta, MemoryPage, FactAssertion, GraphProjection, worker, schema, or
provider side effects.

## Memory API

```text
GET  /api/projects/{project_id}/memory/pages
GET  /api/projects/{project_id}/memory/pages/{memory_page_id}
GET  /api/projects/{project_id}/graph/edges
POST /api/projects/{project_id}/memory/answer
POST /api/projects/{project_id}/memory/pages/{memory_page_id}/open-threads/{thread_id}/operate
GET  /api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview
POST /api/projects/{project_id}/source-deltas/{source_delta_id}/memory-writeback-preview/decisions
```

Memory page response must include source refs or related evidence refs for canon sections.
The MemoryPage endpoints are read-only. They expose `current_canon`, logs,
open threads, contradictions, status, depth, and `source_refs`; they do not
rewrite MemoryPage text, promote canon, or bypass SourceSpan-backed writeback.

MemoryPage open-thread operations are author actions over an existing
SourceSpan-backed thread entry. The route accepts `update_type`, optional
summary, and an author note, is idempotent, audits the actor, returns the
updated MemoryPage detail, and marks dependent ContextPack readiness stale.
It must not create SourceDelta, FactAssertion, ReviewItem, CanonPromotion,
GraphProjection edges, provider output, worker jobs, or frontend-only state.

`GET /graph/edges` is a read-only GraphProjection inspector endpoint. It
accepts `q`, `relation`, `edge_status`, and `limit`, returns projected
source/subject/relation/target/status/evidence refs, and must not rebuild the
graph, create FactAssertions, promote canon, or write MemoryPage/ReviewItem
state. It is a derived read model over already persisted evidence-backed
FactAssertions and confirmed CanonicalEvents.

Memory answer response:

```text
question
answer
answer_type
source_span_refs
unknowns
related_review_items
safe_to_use_in_current_pov
```

Current MemoryAnswer write routes have API success side-effect matrix coverage.
The matrix runs `POST /memory/answer` through FastAPI, application use cases,
SQLAlchemy, and SourceSpan-backed FactAssertion evidence. A successful answer
records exactly one idempotency row and one audit event, returns evidence refs
for matching canon/conflict answers, and must not persist a fake answer object
or create SourceDelta, MemoryPage, ReviewItem, FactAssertion, CanonPromotion,
GraphProjection, worker, schema, or provider side effects.

Memory writeback preview decisions return durable side effects. For fact-level
reject/correct decisions, the side effects include the disputed FactAssertion,
disputed GraphProjection edges, related MemoryPages marked stale, and queued
MemoryPage rewrite job ids for later rebuild. Decisions that change
fact/review/memory/graph dependencies also include
`context_pack_readiness`, `context_pack_readiness_marked`, and
`context_pack_readiness_ids` after marking matching SourceSpan readiness rows
`stale` with reason `review_dependency_changed`.

Current MemoryWriteback decision routes have API success side-effect matrix
coverage. The matrix runs `POST /source-deltas/{source_delta_id}/memory-writeback-preview/decisions`
through FastAPI, application use cases, SQLAlchemy persistence, preview
membership validation, audit, idempotency, and real side-effect application for
fact accept, fact reject, fact correct, review-item accept, review-item reject,
SourceSpan reject, EvidenceLogEntry reject, MemoryPage reject, and Graph edge
reject. The matrix proves exactly which branches create a
MemoryWritebackDecision, MemoryPage, GraphProjectionRun/Edge,
rewrite-memory-page Job, ContextPackReadiness stale marker, audit, and
idempotency rows, while forbidding SourceDelta, AcceptedFragment,
DraftCandidate, provider, schema, or worker execution side effects.

Fact-level `accept` promotes only when no open high-severity ReviewItem blocks
the same FactAssertion. If an open high-risk ReviewItem references the fact,
the backend returns `policy_blocked_promotion` before persisting the author
decision, idempotency record, audit event, MemoryPage, GraphProjection edge, or
canon promotion side effects. The error details include the blocked `fact_id`
and blocking `review_item_id`.

Decision input:

```text
item_ref
decision
author_note
correction
replacement_refs
```

Decision `item_ref.type` may be `source_span`, `evidence_log_entry`,
`fact_assertion`, `review_item`, `memory_page`, or `graph_edge`. The backend
validates that the referenced item is present in the preview for the
SourceDelta before persisting the decision. Non-fact item decisions are durable
author policy signals; they do not invent fact/canon side effects. A `correct`
decision requires a non-empty correction payload and can carry replacement
evidence refs for later rewrite/review workflows.

## Review API

```text
GET  /api/projects/{project_id}/entities
GET  /api/projects/{project_id}/scenes
GET  /api/projects/{project_id}/review-items
GET  /api/projects/{project_id}/review-items/{review_item_id}
POST /api/projects/{project_id}/review-items/{review_item_id}/resolve
POST /api/projects/{project_id}/review-items/{review_item_id}/dismiss
POST /api/projects/{project_id}/review-items/{review_item_id}/reopen
```

`GET /entities` returns real CanonicalEntity rows for author-facing review and
alias correction surfaces. It supports `q`, `entity_type`, and `limit`, searches
both CanonicalEntity display names and StoryAliasRecord alias text, and requires
project read permission.

`GET /scenes` returns read-only StoryScene option rows for author-facing review
and alias boundary correction surfaces. It supports `source_id`, `version_id`,
and `limit`, joins through SourceProcessedView -> SourceVersion -> RawSource to
enforce same-project filtering, and returns chapter/scene ordering labels,
story time/summary, and POV metadata without writing memory, canon, graph, or
review state.

Resolve input:

```text
resolution
author_note
replacement_refs
correction
```

Rules:

1. Review resolution can affect MemoryPage and GraphProjection stale state.
   Responses report actual affected row counts/ids when durable fact/span/page
   refs match, and report `unchanged` with zero counts when no durable rows
   match.
2. Review resolve, dismiss, and reopen operations that have SourceSpan-backed
   evidence mark matching ContextPackReadiness rows `stale` with reason
   `review_dependency_changed`.
3. Review dismissal does not promote facts.
4. Fix by text edit waits for new SourceDelta.
5. Alias-conflict `correction` payloads can include `alias_record_id`,
   `target_entity_id`, and optional `valid_from_scene_id` /
   `valid_until_scene_id` fields. The API validates the alias, target entity,
   and any boundary scenes through the real use-case/UOW boundary before
   resolving the ReviewItem, rejects cross-project or invalid-order boundaries
   before persistence, and returns side-effect fields for applied alias
   boundary corrections.

## Context and Agent API

```text
GET  /api/projects/{project_id}/context-pack-readiness
POST /api/projects/{project_id}/context-packs/build
GET  /api/projects/{project_id}/context-packs/{context_pack_id}
POST /api/projects/{project_id}/agent/suggest-next-beat
POST /api/projects/{project_id}/agent/draft-next-passage
POST /api/projects/{project_id}/agent/rewrite-current-page
POST /api/projects/{project_id}/agent/check-risk
```

`POST /context-packs/build` accepts the same target/source/scene fields as the
application use case plus optional positive integer
`constraints.context_budget.max_estimated_tokens`. Invalid budget shape or
non-positive values return `schema_validation_failed` before AgentContextPack,
idempotency, audit, or downstream side effects. The response includes
retrieval-policy budget metadata when truncation is requested. Budgeting
changes only the persisted AgentContextPack snapshot and its `evidence_refs`;
it cannot write SourceDelta, MemoryPage, ReviewItem, FactAssertion,
GraphProjection, canon, or provider state.

Current ContextPack build routes have API success side-effect matrix coverage.
The matrix runs `POST /context-packs/build` through FastAPI, application use
cases, SQLAlchemy, and SourceSpan-backed evidence. A successful build persists
exactly one AgentContextPack snapshot, records exactly one idempotency row and
one audit event when no readiness rows are consumed, and must not create
SourceDelta, MemoryPage, ReviewItem, FactAssertion, CanonPromotion,
GraphProjection, worker, schema, or provider side effects.

The `/agent/*` endpoints are implemented as wrappers around
`SubmitActionRequest` plus `RunActionRequest`. ActionRequest remains the
canonical internal entry, and wrapper responses use the same
`ActionRequestRunResponse` shape as `/action-requests/{id}/run`.

`GET /context-pack-readiness` returns backend-persisted readiness rows with
`status`, `reason`, `source_span_id`, optional `source_delta_id`,
`affected_refs`, and `evidence_refs`. It accepts optional `status`, `reason`,
`source_delta_id`, and `limit` filters. It is read-only and does not build a
ContextPack. `POST /context-packs/build` consumes only matching pending/stale
readiness rows whose SourceSpan appears in the generated ContextPack
`evidence_refs`.

## Job API

```text
GET /api/projects/{project_id}/jobs/{job_id}
POST /api/projects/{project_id}/jobs/{job_id}/cancel
POST /api/projects/{project_id}/jobs/{job_id}/retry
```

Job status:

```text
queued
running
succeeded
failed_retryable
failed_terminal
cancelled
```

Rules:

1. Cancel requires a write actor and is allowed for queued, running, or retryable jobs.
2. Retry requires a write actor and is allowed for retryable jobs.
3. Cancel/retry must be idempotent and audited.
4. Already-running jobs are cooperatively cancelled by writing `cancelled` to
   the DB job row. The worker must refresh the row before marking success and
   must acknowledge cancellation instead of overwriting it.

## OpenAPI and Client Generation

Rules:

1. Backend OpenAPI is generated in CI.
2. Frontend client is generated into `web/src/generated/`.
3. CI fails if generated client is stale.
4. Frontend cannot hand-maintain backend DTOs.

## Acceptance

API implementation is complete when:

1. Contract tests cover every endpoint status code and error code.
2. Candidate accept stale-base error is tested.
3. Memory answer unknown/conflict/canon variants are tested.
4. Generated frontend client is up to date.
5. API route imports no concrete infra adapter.
