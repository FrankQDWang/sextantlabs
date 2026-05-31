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
X-Request-Id
Idempotency-Key
```

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

## Project and Source APIs

```text
GET    /api/projects/{project_id}
POST   /api/projects/{project_id}/sources
GET    /api/projects/{project_id}/sources/{source_id}
GET    /api/projects/{project_id}/sources/{source_id}/versions/{version_id}
POST   /api/projects/{project_id}/source-deltas
GET    /api/projects/{project_id}/source-deltas/{delta_id}
```

`POST /source-deltas` accepts author text, import material, note, outline, or accepted candidate provenance.

It returns:

```text
source_delta_id
status
memory_writeback_job_id
```

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

## Memory API

```text
GET  /api/projects/{project_id}/memory/pages
GET  /api/projects/{project_id}/memory/pages/{page_id}
POST /api/projects/{project_id}/memory/answer
GET  /api/projects/{project_id}/memory/writeback-previews/{source_delta_id}
POST /api/projects/{project_id}/memory/writeback-previews/{preview_id}/items/{item_id}/confirm
POST /api/projects/{project_id}/memory/writeback-previews/{preview_id}/items/{item_id}/reject
```

Memory page response must include source refs or related evidence refs for canon sections.

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

## Review API

```text
GET  /api/projects/{project_id}/review-items
GET  /api/projects/{project_id}/review-items/{review_id}
POST /api/projects/{project_id}/review-items/{review_id}/resolve
POST /api/projects/{project_id}/review-items/{review_id}/dismiss
POST /api/projects/{project_id}/review-items/{review_id}/reopen
```

Resolve input:

```text
resolution
author_note
replacement_refs
```

Rules:

1. Review resolution can affect MemoryPage and GraphProjection stale state.
2. Review dismissal does not promote facts.
3. Fix by text edit waits for new SourceDelta.

## Context and Agent API

```text
POST /api/projects/{project_id}/context-packs/build
GET  /api/projects/{project_id}/context-packs/{context_pack_id}
POST /api/projects/{project_id}/agent/suggest-next-beat
POST /api/projects/{project_id}/agent/draft-next-passage
POST /api/projects/{project_id}/agent/rewrite-current-page
POST /api/projects/{project_id}/agent/check-risk
```

These endpoints may be implemented as wrappers around ActionRequest. If both exist, ActionRequest remains the canonical internal entry.

## Job API

```text
GET /api/projects/{project_id}/jobs/{job_id}
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
