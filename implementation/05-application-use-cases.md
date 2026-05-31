# 05. Application Use Cases

Application layer owns orchestration. It decides transaction boundaries, idempotency, permission checks, repository port calls, Story Skill dispatch, worker enqueueing, and audit events.

It does not own domain truth. It calls domain policies and state machines.

## Use Case Catalog

| Use case | Trigger | Output |
|---|---|---|
| `SubmitActionRequest` | natural language, selection, toolbar, candidate, memory, review action | persisted ActionRequest |
| `BuildWritingContextPack` | author asks for continuation/rewrite/risk | WritingContextPack |
| `AnswerWithEvidence` | ask_memory | MemoryAnswer |
| `SuggestNextBeat` | suggest_next_direction | BeatCandidate list |
| `DraftNextPassage` | continue_small_passage/render_current_beat | DraftCandidate |
| `RewriteCurrentPage` | rewrite_span | DraftCandidate |
| `RunAgentReview` | candidate generated or user checks risk | AgentReviewFinding list |
| `AcceptCandidate` | author accepts candidate | AcceptedFragment + SourceDelta |
| `CreateSourceDelta` | text changed or material imported | SourceDelta + SourceVersion job |
| `RunMemoryWriteback` | SourceDelta ready | SourceSpan, extracted objects, ReviewItem, Memory updates |
| `BuildMemoryWritebackPreview` | post-writeback UI state | MemoryWritebackPreview |
| `ConfirmMemoryWritebackItem` | author corrects/accepts preview item | policy decision or correction signal |
| `ResolveReviewItem` | author handles formal review | ReviewItem state transition |
| `RebuildGraphProjection` | memory object changed | GraphProjection snapshot |

## Common Use Case Rules

Every use case must:

1. Accept a `request_id` or create one.
2. Check project ownership.
3. Validate idempotency key when external write is possible.
4. Use ports, not concrete infra.
5. Emit audit event for state-changing operations.
6. Return structured result or typed domain error.

No use case may:

1. Treat model output as canon.
2. Write GraphProjection as source-of-truth.
3. Create ReviewItem without SourceSpan or explicit user decision.
4. Let API route own transaction commit.

## `SubmitActionRequest`

Input:

```text
project_id
actor_id
trigger
action_type
target
constraints
expected_output
actor_intent
```

Rules:

1. Writing actions require `target`.
2. Natural language is stored as `actor_intent`, not canon fact.
3. `expected_output` must match `action_type`.
4. If target is selected text, source/version/range must be captured.

Output:

```text
ActionRequest(status='submitted')
```

Failure:

```text
missing_target
unsupported_action_type
permission_denied
stale_source_version
```

## `BuildWritingContextPack`

Input:

```text
project_id
action_request_id
current_source_id
current_version_id
current_scene_id
current_pov_character_id
mode
current_text_window
```

Reads:

```text
MemoryPage
CanonicalEvent
FactAssertion
ReviewItem
CharacterKnowledge
GraphProjection
SourceSpan
Style samples
```

Rules:

1. Canon facts go to canonical context.
2. proposed/disputed/blocked facts go to risk context.
3. forbidden knowledge is derived for current POV.
4. Style Memory is auxiliary, not fact source.

Output:

```text
WritingContextPack(schema_version, canonical_context, pov_constraint, active_characters, character_agency_state, recent_events, risk_context, style_memory, evidence_refs)
```

## `AnswerWithEvidence`

Rules:

1. Answer must cite SourceSpan refs.
2. If no evidence exists, return `answer_type='unknown'`.
3. If evidence conflicts, return `answer_type='conflict'` and related ReviewItem ids.
4. Never answer from GraphProjection alone.

Acceptance:

```text
Question: "Mira knows who gave the key?"
Valid output distinguishes canon answer from POV knowledge and unknowns.
```

## Candidate-producing Use Cases

`SuggestNextBeat`, `DraftNextPassage`, and `RewriteCurrentPage` share a pipeline:

```text
ActionRequest
  -> BuildWritingContextPack
  -> CharacterAgencyPass
  -> StorytellingControlLayer
  -> ProseRenderingContract
  -> NextPageAgent
  -> RunAgentReview
  -> DraftCandidate/BeatCandidate
```

Rules:

1. Candidate-producing use cases do not write manuscript text.
2. They do not create SourceDelta.
3. They do not write Memory.
4. They persist prompt input/output audit records through `skill_runs`.
5. They attach AgentReviewFinding before author offer.

## `AcceptCandidate`

Input:

```text
candidate_id
accepted_text_ref
accept_mode
target_source_id
target_version_id
insert_or_replace_range
source_scope choice
author_edits flag
```

Rules:

1. Candidate must be `offered_to_author` or explicitly overridden from `blocked`.
2. Replace requires current target hash == candidate base_hash.
3. accepted text creates AcceptedFragment.
4. AcceptedFragment creates SourceDelta.
5. SourceDelta enqueue memory writeback job.

Transaction:

```text
candidate status update
accepted fragment insert
source delta insert
job enqueue
audit event
```

No LLM call inside this transaction.

Failure:

```text
candidate_not_offerable
blocked_without_override
stale_base_hash
invalid_target_range
```

## `CreateSourceDelta`

This use case handles author-typed text, imported material, accepted candidate text, notes, and outlines.

Rules:

1. `source_type` controls normalization profile.
2. `source_scope` controls canon promotion weight.
3. SourceDelta creates or updates RawSource/SourceVersion.
4. Normalization may be queued if large or model-assisted.

## `RunMemoryWriteback`

Pipeline:

```text
SourceDelta
  -> SourceNormalization
  -> StructureParsing
  -> SourceSpanExtraction
  -> MentionExtraction
  -> AliasResolution
  -> EventExtraction
  -> EventAggregation
  -> FactDerivation
  -> EvidenceLogWriteback
  -> ConflictPolicyGate
  -> CanonPromotion or ReviewItem
  -> MemoryPageUpdate
  -> GraphProjection stale/rebuild
  -> ContextPackReadiness
```

Rules:

1. Original source is saved before extraction.
2. Evidence/log writeback happens before canon promotion.
3. High risk blocks promotion only.
4. User correction signal is stored when extraction is rejected.
5. GraphProjection can be rebuilt from structured objects.

## `ResolveReviewItem`

Input:

```text
review_item_id
resolution
author_note
optional replacement refs
```

Rules:

1. Resolution must be in ReviewItem resolution whitelist.
2. `accept`, `split`, `merge`, `supersede`, `accepted_as_change` can mark affected memory/projection stale.
3. `dismissed` does not promote canon.
4. `fixed_by_text_edit` waits for a new SourceDelta.

## Idempotency

Idempotency keys:

| Operation | Key |
|---|---|
| submit action request | client request id |
| accept candidate | candidate id + accepted text hash + target version |
| create source delta | source id + previous version id + submitted text hash |
| memory writeback | source delta id + pipeline version |
| graph rebuild | projection target + source version |

## Typed Errors

Common application errors:

```text
permission_denied
not_found
invalid_state_transition
missing_target
stale_source_version
invalid_source_scope
policy_blocked_promotion
schema_validation_failed
llm_output_invalid
retryable_infrastructure_failure
terminal_pipeline_failure
```

API maps these to HTTP errors; domain/application code uses typed errors.

## Acceptance

Use case implementation is complete when:

1. Every use case has unit tests for happy path and invalid state.
2. At least one contract test covers ActionRequest -> DraftCandidate -> AcceptedFragment -> SourceDelta.
3. At least one integration test covers SourceDelta -> ReviewItem without blocking ingest.
4. Audit events exist for candidate acceptance, canon promotion, review resolution.
