# 10. Worker and Jobs

First production implementation uses a DB-backed worker. Temporal or another workflow system can be introduced later only after the domain pipeline is stable.

## Why DB-backed Worker First

The difficult part is source-of-truth, evidence, policy, and skill boundaries, not distributed orchestration.

DB-backed worker gives:

1. simple local development,
2. idempotent retries,
3. easy audit,
4. fewer moving parts for AI-coded implementation.

## Job Table

See [03-persistence-schema.md](03-persistence-schema.md) for `job_records`.

Required fields:

```text
id
project_id
job_type
status
idempotency_key
payload
attempt_count
run_after
locked_by
locked_at
last_error
created_at
updated_at
```

## Job Types

```text
normalize_source
split_structure
run_memory_writeback
extract_mentions
resolve_aliases
extract_events
aggregate_events
derive_facts
run_conflict_policy
rewrite_memory_pages
rebuild_graph_projection
build_context_pack
run_agent_candidate
run_agent_review
run_skill_replay_eval
```

Some job types may initially be grouped into `run_memory_writeback`, but the payload must still record pipeline step and version.

## Job Status

```text
queued
running
succeeded
failed_retryable
failed_terminal
cancelled
```

Rules:

1. retryable failures set `run_after`.
2. terminal failures write audit event.
3. cancelled jobs cannot be resumed without a new job.
4. succeeded jobs are immutable except archival metadata.

## Idempotency

Every job must define its idempotency key.

| Job | Idempotency key |
|---|---|
| normalize_source | source_version_id + cleaning_profile |
| split_structure | processed_view_id + parser_version |
| run_memory_writeback | source_delta_id + pipeline_version |
| rebuild_graph_projection | project_id + projection_scope + source_state_hash |
| build_context_pack | action_request_id + context_scope_hash |
| run_agent_candidate | action_request_id + prompt_version + input_hash |
| run_agent_review | draft_candidate_id + review_policy_version |

If the same key exists and succeeded, return existing result.

## Worker Leasing

Worker loop:

```text
select queued/failed_retryable job where run_after <= now
  order by created_at
  for update skip locked
set running, locked_by, locked_at
execute handler
mark succeeded or failed
```

Lease timeout releases abandoned running jobs:

```text
running where locked_at < now - lease_timeout -> failed_retryable
```

## Retry Policy

Retryable:

```text
provider timeout
rate limit
temporary object store error
deadlock
serialization failure
```

Terminal:

```text
schema validation failed after bounded retries
invalid state transition
missing source version
invalid SourceSpan offset map
policy invariant violation
```

Do not retry terminal domain failures.

## Pipeline Ordering

Memory writeback order:

```text
normalize_source
  -> split_structure
  -> extract source spans
  -> extract mentions
  -> resolve aliases
  -> extract events
  -> aggregate events
  -> derive facts
  -> evidence log writeback
  -> conflict policy
  -> memory page rewrite
  -> graph projection rebuild/stale mark
  -> context readiness
```

The pipeline can execute as one job first, but each step must emit audit and structured step result.

## Outbox Pattern

If external side effects are needed later, use an outbox table or job record, not side effects inside transaction before commit.

Examples:

```text
send notification
publish artifact
call external eval service
```

## Long LLM Calls

LLM calls must happen outside transaction.

Pattern:

```text
transaction: load input snapshot refs and mark skill run started
call provider
transaction: validate structured output and persist result
```

If validation fails, output is stored for audit but not applied.

## Acceptance

Worker implementation is complete when:

1. Lease timeout test proves abandoned job is retryable.
2. Idempotency test proves duplicate memory writeback does not double-create facts.
3. Terminal domain failure does not retry indefinitely.
4. LLM provider timeout retries with bounded backoff.
5. Each pipeline step writes audit event or skill run record.
