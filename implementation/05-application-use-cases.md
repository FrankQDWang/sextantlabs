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
| `CreateSource` | author imports a source | RawSource + SourceVersion + SourceDelta + writeback job |
| `CreateSourceDelta` | text changed or material imported | SourceDelta + SourceVersion job |
| `RestoreSourceVersion` | author restores a prior source version | SourceDelta + new SourceVersion + writeback job |
| `ListSourceVersions` | author audits source history | SourceVersion summaries |
| `GetSourceVersionDiff` | author compares source versions | read-only line diff |
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
expected_output_mismatch
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
constraints.context_budget.max_estimated_tokens (optional positive integer)
```

Reads:

```text
MemoryPage
CanonicalEvent
FactAssertion
ReviewItem
CharacterKnowledge
GraphProjection
StoryChapter
StoryScene
SourceSpan
StoryAliasRecord
Style samples
```

Rules:

1. Canon facts go to canonical context only when their serialized
   `evidence_span_ids` include at least one existing same-project SourceSpan.
   Canon fact entries cite only those same-project SourceSpans.
2. proposed/disputed/blocked facts go to risk context only when their
   serialized `evidence_span_ids` include at least one existing same-project
   SourceSpan. Risk fact entries cite only those same-project SourceSpans.
3. Recent events go to `recent_events` only when their serialized
   `evidence_span_ids` include at least one existing same-project SourceSpan.
   Recent-event entries cite only those same-project SourceSpans.
4. Object/location state entries from GraphProjectionEdge `evidence_refs` and
   MemoryPage `current_canon.state_facts[].evidence_span_ids` go to
   `object_location_state` only when they include at least one existing
   same-project SourceSpan. Object/location entries cite only those
   same-project SourceSpans.
5. Style samples go to `style_memory.samples` only when the SourceSpan resolves
   through a RawSource in the same project, including when a caller supplies a
   `current_source_id` or `current_version_id`.
6. Open ReviewItems go to `risk_context.review_items` only when direct
   evidence, affected facts, or affected MemoryPages resolve to at least one
   existing same-project SourceSpan. Review entries cite only those
   same-project SourceSpans and sanitize model-visible `source_span_ids`.
7. MemoryPage open threads go to `open_threads` and character-agency
   `open_threads` only when thread-level SourceSpan ids or MemoryPage
   source refs resolve to at least one existing same-project SourceSpan.
8. allowed and forbidden knowledge are derived for current POV.
9. POV constraint includes conservative sensory limits and inner-access rules
   derived from effective POV and persisted scene position.
10. Active characters prefer canon `appears_in` facts for the current scene and
   fall back to canon character refs only when no current-scene appearance facts
   exist.
11. Canon, risk, recent-event, object/location, and style-sample entries carry
   read-only relevance metadata and are sorted by current scene evidence,
   current source/version evidence, active character, effective POV character,
   current text/mode token overlap, and read-only semantic recall from matching
   AliasRecord and MemoryPage vocabulary.
12. When an optional context token budget is supplied, the use case truncates
   the persisted snapshot after relevance ranking, preserves high-priority risk
   entries when budget allows, records budget metadata in retrieval policy, and
   recalculates `evidence_refs` from retained items only.
13. Invalid context budget shape or non-positive budget values fail before
   AgentContextPack, idempotency, or audit side effects.
14. AliasRecord and MemoryPage vocabulary may affect retrieval ranking only; it
   cannot create facts, canon, ReviewItems, MemoryPages, GraphProjection, or
   SourceDelta state.
15. Style Memory is auxiliary, not fact source.

Output:

```text
WritingContextPack(schema_version, current_position, canonical_context, pov_constraint, active_characters, character_agency_state, recent_events, risk_context, style_memory, evidence_refs)
```

## `AnswerWithEvidence`

Rules:

1. Answer must cite SourceSpan refs that resolve to existing SourceSpan rows in
   the same project. Generic FactAssertion answers ignore facts whose serialized
   `evidence_span_ids` contain no valid same-project SourceSpan refs.
2. If `subject_ref`/`predicate` is not supplied, the use case may infer a
   simple evidence target from existing FactAssertion refs, CanonicalEntity
   display names, AliasRecord text, and MemoryPage vocabulary.
3. If one matched display name, alias surface, or description-derived endpoint
   surface points to multiple CanonicalEntities, the use case returns
   `answer_type='unknown'` with an `ambiguous_entity_match` caveat, affected
   candidate refs, and any alias SourceSpan refs instead of combining facts
   across candidates.
4. If the same question also explicitly names exactly one candidate
   CanonicalEntity display name, alias expansion is narrowed to that entity for
   this read-only answer instead of treating the alias as globally resolved or
   combining facts from other candidates. If no explicit candidate name is
   present, an ambiguous local AliasRecord surface may narrow only when exactly
   one scene/chapter/character/disguise-scoped alias has SourceSpan-backed
   evidence context matching the question, when exactly one `scene_local` alias
   has evidence in `current_scene_id`, when exactly one `chapter_local` alias
   has evidence in the chapter containing `current_scene_id`, when exactly one
   `disguise_arc` alias has explicit `valid_from_scene_id` /
   `valid_until_scene_id` boundaries containing `current_scene_id` or, if no
   explicit boundaries exist, sortable evidence scene spans whose inclusive
   window contains `current_scene_id`, or when exactly one `character_specific`
   alias has SourceSpan evidence in a StoryScene whose persisted
   `pov_character_id` matches `current_pov_character_id` or whose SourceSpan
   `speaker_entity_id` matches `current_pov_character_id`; if
   `current_pov_character_id` is omitted and `current_scene_id` points to a
   same-project StoryScene with persisted `pov_character_id`, the use case may
   use that persisted scene POV as the effective current POV for this read-only
   answer, without overriding an explicitly supplied POV; the answer carries
   `scene_local_alias_context` and still cannot promote the alias globally or
   write canon. When an answer depends on this scoped alias
   narrowing, its confidence cannot exceed the selected AliasRecord confidence.
5. First-appearance source lookup questions may answer from resolved
   StoryMention rows only after following them to SourceSpan and sortable
   StoryChapter/StoryScene positions. The answer cites the first SourceSpan,
   returns the affected CanonicalEntity ref, and carries a
   `source_mention_lookup` caveat without creating canon facts or graph state.
6. Character-knowledge inventory questions answer from active
   CharacterKnowledge rows only after following `knows_ref` to
   FactAssertions whose serialized `evidence_span_ids` include at least one
   existing same-project SourceSpan. The CharacterKnowledge row's own
   `evidence_span_id` must also resolve to an existing same-project SourceSpan.
   The answer cites only same-project SourceSpans while preserving `known`,
   `suspected`, `misunderstands`, `false_belief`, and `does_not_know`
   certainty as caveats.
   Chinese inventory questions such as `Mira 现在知道哪些秘密？` and
   `Mira 不知道什么？` must route to this CharacterKnowledge path rather than
   falling through to a generic FactAssertion answer.
7. After/timeline event questions may answer from canon, external-canon, or
   author-note CanonicalEvents only when the anchor event and later events have
   sortable StoryChapter/StoryScene positions and at least one evidence ref that
   resolves to an existing same-project SourceSpan. The answer cites only
   same-project SourceSpans for both the anchor event and returned later events
   and carries a scene-order caveat.
8. During/while event questions may answer from canon, external-canon, or
   author-note CanonicalEvents only when the anchor event and returned events
   share a persisted StoryScene, normalized `story_time`, or an explicit
   same-prefix numeric `story_time` point/range overlap such as
   `storm hour 1-3` overlapping `storm hour 2`, and at least one evidence ref
   resolves to an existing same-project SourceSpan. The answer cites only
   same-project SourceSpans for both the anchor event and overlapping events,
   carries an overlap caveat, and cannot infer overlap from GraphProjection,
   provider output, or unstored timeline assumptions.
9. Relationship questions may answer from SourceSpan-backed relationship
   FactAssertions and may include supporting canon/external-canon/author-note
   CanonicalEvents as the explanation. GraphProjection can inform retrieval but
   cannot be the only source for the answer. Predicate inference may use
   deterministic paraphrase cues such as betrayal, distrust, stopped trust,
   support, protection, trust, or Chinese cues such as `敌对`, but it still must
   answer only from existing relationship FactAssertions with at least one
   evidence ref that resolves to an existing same-project SourceSpan; supporting
   events are included only when their evidence refs also resolve to
   same-project SourceSpans, and the answer cites only those same-project
   SourceSpans. Chinese relationship questions such as
   `Kestrel 和 Mira 为什么敌对？` must route to this relationship explanation path
   rather than a generic FactAssertion answer. Endpoint matching may use
   persisted CanonicalEntity descriptions when at least two meaningful question
   tokens overlap the description; this is read-only and cannot create aliases
   or canonical entities.
10. Relationship path questions may answer from a bounded multi-hop path across
   SourceSpan-backed relationship FactAssertions when the question names both
   endpoint CanonicalEntities, unambiguous AliasRecords, or unambiguous
   description-derived endpoints. If a matched alias or description-derived
   endpoint points to multiple entities and the question does not explicitly
   name one candidate display name, return `ambiguous_entity_match` rather than
   guessing a path. When multiple paths are available, rank them
   deterministically by query-predicate term match, canon status, confidence,
   path length, and stable ids rather than database insertion order. The answer
   can use only relationship FactAssertions with at least one evidence ref that
   resolves to an existing same-project SourceSpan, cites only same-project
   SourceSpans for the selected path, preserves the question's endpoint order,
   including when the author asks for the stored facts in reverse endpoint
   order, carries a
   relationship-path caveat, and does not treat GraphProjection as fact evidence
   or write GraphProjection state. Chinese relationship path questions such as
   `Kestrel 和 Orrin 通过谁联系？`, `Kestrel 和 Orrin 是怎么认识的？`,
   or `Kestrel 和 Orrin 如何相识？` must route to this bounded path rather
   than returning a generic relationship fact list.
11. Relationship evolution questions may answer from SourceSpan-backed
   relationship FactAssertions with sortable StoryChapter/StoryScene positions
   only when each returned fact has at least one evidence ref that resolves to
   an existing same-project SourceSpan. The answer orders historical/current
   relationship facts by scene position, includes each fact status, cites only
   the ordered same-project SourceSpans, and carries a relationship timeline
   caveat without treating GraphProjection as fact evidence. Chinese
   relationship evolution questions such as `Kestrel 和 Mira 的关系如何变化？`
   must route to this timeline path rather than returning unknown or a generic
   relationship fact.
12. Continuity-check questions may answer from existing open ReviewItems only
   when those ReviewItems carry new/existing SourceSpan evidence. The answer
   returns `answer_type='conflict'`, related ReviewItem ids, affected refs, and
   severity caveats; it does not run a new continuity scan.
13. Open-thread questions may answer from current MemoryPages only when the
   matched open thread or its MemoryPage has same-project SourceSpan refs that
   resolve to existing rows. When every selected thread has its own valid
   `source_span_ids`, the answer cites only those selected thread SourceSpans;
   otherwise it falls back to valid MemoryPage SourceSpan refs. The answer
   returns `answer_type='open_thread'`, affected MemoryPage targets, and a
   `memory_page_open_thread` caveat without treating unresolved threads as
   canon facts. If a matching open thread is backed by an
   open ReviewItem, the answer remains `open_thread` but includes related
   ReviewItem ids, an
   `open_review_item` caveat, severity-calibrated lower confidence, and
   `safe_to_use_in_current_pov=false`. Closed, resolved, dismissed, obsolete,
   or superseded thread entries are not returned as open-thread answers. When
   a question names both a MemoryPage target and a specific unresolved subject,
   target tokens select the page and remaining focus tokens filter the returned
   thread entries. Returned thread entries are ranked by remaining thread-focus
   token overlap, open ReviewItem backing, review severity, thread-local
   SourceSpan evidence count, and original order. If a real persisted
   `semantic_embeddings` index is available through the injected embedding
   provider, open-thread questions may use read-only MemoryPage target and
   SourceSpan semantic matches to select existing same-project SourceSpan-backed
   thread entries without creating facts, canon, review items, memory pages,
   graph edges, SourceDeltas, provider state, or frontend-only state.
14. If no evidence exists, return `answer_type='unknown'`.
15. If evidence conflicts, return `answer_type='conflict'` and related ReviewItem ids.
16. Natural-language target inference is read-only. It cannot create facts,
   aliases, canon, ReviewItems, MemoryPages, GraphProjection, SourceDeltas, or
   provider calls. When no lexical subject/predicate target is available and a
   persisted `semantic_embeddings` index is available through the injected
   embedding provider, generic FactAssertion answers may use the highest-scored
   same-project SourceSpan semantic evidence bucket to select existing
   SourceSpan-backed facts. Semantic fact answers must cap returned confidence
   by the SourceSpan semantic match score, and semantic target refs are used
   only when the recall result has no SourceSpan evidence match. If an
   underspecified question
   semantically matches multiple candidate fact subjects, return
   `answer_type='unknown'` with `semantic_clarification_needed`, cite the
   candidate SourceSpans, and list the candidate subject refs instead of
   concatenating the possible targets into canon text.
17. Every response carries `confidence`, `affected_entities`, and `caveats` so
   the author can distinguish confirmed answers from unknown, disputed, open
   review, or POV-unsafe answers without trusting a naked text string.
18. Never answer from GraphProjection alone.

Output:

```text
MemoryAnswer(question, answer, answer_type, confidence, source_span_refs, affected_entities, caveats, unknowns, related_review_items, safe_to_use_in_current_pov)
```

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
5. SourceDelta enqueues source normalization and memory writeback jobs.

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
stale_source_version
invalid_target_range
```

`stale_source_version` covers both candidate/base-hash mismatch and a target
SourceVersion that has been superseded by a newer source version. It must fail
before any AcceptedFragment, SourceDelta, SourceVersion, job, MemoryPage, or
GraphProjection side effect is created.

## `CreateSource`

This use case handles first import of source material into a project.

Rules:

1. It preserves the original text as `RawSource`.
2. It creates the initial `SourceVersion`.
3. It creates an insert `SourceDelta` with no previous version and the initial
   version as `new_version_id`.
4. It enqueues source normalization for the new `SourceVersion` and memory
   writeback for that `SourceDelta`.
5. It returns the SourceDelta and memory-writeback job ids so clients can show
   evidence-backed import/writeback status.

## `CreateSourceDelta`

This use case handles author-typed text, imported material, accepted candidate text, notes, and outlines.

Rules:

1. `source_type` controls normalization profile.
2. `source_scope` controls canon promotion weight.
3. SourceDelta creates a new superseding SourceVersion only when the requested
   previous SourceVersion is still latest for that source.
4. Stale previous SourceVersion writes fail before SourceDelta, Job, Memory, or
   GraphProjection side effects are created.
5. Source normalization and memory writeback are queued for the resulting
   SourceDelta; normalization queues structure split for the current processed
   source view.

## `RestoreSourceVersion`

This use case restores a previous SourceVersion without mutating historical
rows.

Rules:

1. It reads the target historical SourceVersion text from object storage.
2. It replaces the latest SourceVersion text with that historical text by
   creating a new replace SourceDelta.
3. It creates a new SourceVersion that supersedes the latest version, even if
   its raw hash matches the restored historical version.
4. It enqueues memory writeback for the restore SourceDelta.
5. It records restore provenance with `restored_from_version_id`.

## `GetSourceVersionDiff`

This use case compares two SourceVersions for the same RawSource.

Rules:

1. It verifies project read access and that both SourceVersions belong to the
   requested source.
2. It reads both version texts from object storage.
3. It returns line-level context/insert/delete rows plus insertion/deletion
   counts.
4. It is read-only: it must not create SourceDelta, Job, Memory, ReviewItem, or
   GraphProjection side effects.

## `ListStoryScenes`

This use case returns author-facing scene options for review and alias boundary
correction controls.

Rules:

1. It requires project read access before returning rows.
2. It may filter by RawSource and SourceVersion.
3. It reads only StoryScene rows reachable through StoryChapter,
   SourceProcessedView, SourceVersion, and RawSource for the requested project.
4. It returns stable chapter/scene ordering labels plus story time, summary, and
   POV metadata for UI selection.
5. It is read-only: it must not create SourceDelta, Job, Memory, ReviewItem,
   FactAssertion, CanonPromotion, GraphProjection, provider, or worker side
   effects.

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
4. User correction signal is stored when extraction is rejected or corrected,
   including authored correction payloads and optional replacement refs.
5. Accepting a fact-level preview item promotes the FactAssertion through an
   explicit author decision, updates the related MemoryPage, rebuilds
   GraphProjection from canon facts and confirmed CanonicalEvent structure, and
   resolves linked open ReviewItems with `accept`.
6. Correcting or rejecting a fact-level preview item marks the fact and graph
   projection disputed, marks related MemoryPage rows stale, and enqueues an
   idempotent MemoryPage rewrite job so the page can be rebuilt from remaining
   canon facts and derived appearance/event/relationship/open-thread sections
   without inventing new facts.
7. Accepting or correcting a ReviewItem preview item records the author signal
   on the ReviewItem side-effect payload without changing MemoryPage or
   GraphProjection; rejecting an open ReviewItem preview item dismisses it.
8. Rejecting or correcting a SourceSpan or EvidenceLogEntry preview item keeps
   the SourceSpan immutable, marks matching EvidenceLogEntry rows disputed, and
   marks derived FactAssertion, MemoryPage, and GraphProjection state stale or
   disputed for rewrite/rebuild.
9. Rejecting or correcting a MemoryPage preview item marks the page stale and
   queues an idempotent rewrite job without changing facts or graph edges.
10. Rejecting or correcting a GraphProjection preview item marks the edge
   disputed and, when the edge is derived from a FactAssertion, disputes the
   source fact and downstream memory state through the same evidence policy.
11. GraphProjection can be rebuilt from structured objects.
12. Author writeback decisions and formal ReviewItem operations that change
    fact/review/memory/graph dependencies mark matching
    ContextPackReadiness rows `stale` with reason
    `review_dependency_changed`; they do not auto-build a new ContextPack.

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
5. `split`, `merge`, and `fixed_by_text_edit` require an author note plus at
   least one replacement `SourceDelta` ref before resolve can persist.
6. `supersede` requires an author note plus at least one same-project
   replacement `SourceDelta`, `ReviewItem`, or `SourceSpan` ref before resolve
   can persist; a ReviewItem cannot supersede itself.
7. Any supplied replacement refs must use supported `SourceDelta`,
   `ReviewItem`, or `SourceSpan` ref types and must point to existing rows in
   the same project before the operation can persist. Valid replacement refs
   are persisted on the ReviewItem as normalized
   `new_evidence.resolution_replacement_refs` and type-indexed
   `affected_refs.replacement_source_delta_ids`,
   `affected_refs.replacement_review_item_ids`, or
   `affected_refs.replacement_source_span_ids`; response `side_effects` are not
   the only audit surface.
8. Alias-conflict corrections may carry `alias_record_id`,
   `target_entity_id`, and optional `valid_from_scene_id` /
   `valid_until_scene_id` values. The alias/entity target and any boundary
   scenes must belong to the review project, and the final scene boundary order
   must be valid before the ReviewItem can resolve. Missing boundary fields keep
   the current AliasRecord boundaries; explicit null clears that side.
9. Alias boundary correction updates only AliasRecord lifetime metadata inside
   the formal ReviewItem operation. If correction payload
   `apply_to_matching_aliases=true` is explicitly supplied for a `disguise_arc`
   alias, the same boundary values are also applied to same-project AliasRecords
   with the same alias text, same target CanonicalEntity, and same
   `disguise_arc` scope. It does not cross entity or scope boundaries, and it
   does not create facts, canon, MemoryPages, GraphProjection facts,
   SourceDeltas, or provider output.
10. `event_merge_conflict` with `resolution="merge"` must resolve through this
    same formal ReviewItem operation. After replacement SourceDelta validation,
    the disputed CanonicalEvent is merged into the existing same-project,
    same-type CanonicalEvent by appending EventCandidate ids and SourceSpan
    evidence, preserving existing summaries unless the existing event lacks
    cause/consequence detail, and marking the disputed event `deprecated`.
    This operation does not promote the merged event to canon or write facts;
    MemoryPage and GraphProjection rebuild side effects still use the normal
    stale/rebuild queue path.
11. `event_merge_conflict` with `resolution="split"` records the author's
    distinct-event decision inside the same formal ReviewItem operation. After
    replacement SourceDelta validation, the disputed CanonicalEvent is restored
    from `disputed` to `proposed` so it can remain a separate evidence-backed
    event instead of being merged. The operation does not derive facts, promote
    canon, or write MemoryPages directly; dependent MemoryPage and
    GraphProjection rebuilds still use the normal split/merge queue path.
12. `event_merge_conflict` with `resolution="reject"` records that the disputed
    conflict-version event should not enter the active event line. The disputed
    CanonicalEvent is marked `deprecated`, any referenced same-project
    StoryEventCandidate rows are marked `rejected`, and GraphProjection is
    rebuilt so the open `contradicts` reminder edge disappears. This operation
    does not require replacement SourceDelta refs, does not delete SourceSpan
    evidence, and does not promote canon, derive facts, write MemoryPages, or
    use provider output as truth.
13. `event_merge_conflict` with `resolution="mark_intentional"` records the
    author's intentional-conflict decision inside the same formal ReviewItem
    operation. The disputed CanonicalEvent remains evidence-preserving and
    disputed, but the ReviewItem is resolved and GraphProjection is rebuilt so
    the open `contradicts` reminder edge disappears. This does not promote
    canon, derive facts, write MemoryPages, or use provider output as truth.
14. Fact-backed `source_scope_conflict` ReviewItems whose new evidence comes
    from `model_suggestion` cannot be resolved with direct `accept`. If the
    author wants to adopt the suggested change, `accepted_as_change` or
    `fixed_by_text_edit` must carry an author note and a same-project
    replacement `SourceDelta` whose `source_scope` is author-backed
    (`user_draft`, `user_published`, or `author_note`). The model-suggestion
    FactAssertion stays non-canon; the replacement SourceDelta must re-enter
    the normal source/evidence/writeback pipeline before author canon changes.
    If the author rejects the model suggestion, the affected model-suggestion
    FactAssertion is marked `contradicted`, its SourceSpan evidence is
    preserved, GraphProjection is rebuilt so the open review reminder
    disappears, and any MemoryPage that directly referenced the rejected fact
    is marked stale for rewrite from remaining canon evidence.
    Source-scope conflict ReviewItems created for model suggestions must not
    advertise direct `accept` as a suggested action; suggested author paths are
    `reject`, `accepted_as_change`, and `fixed_by_text_edit`.
15. When a later author-backed SourceSpan (`user_draft`, `user_published`, or
    `author_note`) asserts the exact same subject/predicate/object as an
    existing review-required lower-authority FactAssertion (`model_suggestion`,
    `reference_only`, `discarded_draft`, `experimental`, or `outline_plan`),
    Conflict Policy may promote only the author-scoped FactAssertion to canon.
    The lower-authority FactAssertion remains separate, is marked `outdated`,
    and any open lower-authority source-scope ReviewItem is superseded with the
    author SourceSpan as replacement evidence. This path must not merge
    lower-authority evidence into the author fact and must not mark those
    lower-authority FactAssertions as canon.

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
idempotency_conflict
invalid_state_transition
missing_target
stale_source_version
source_version_already_current
invalid_source_scope
unsupported_action_type
expected_output_mismatch
candidate_not_offerable
blocked_without_override
invalid_target_range
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
