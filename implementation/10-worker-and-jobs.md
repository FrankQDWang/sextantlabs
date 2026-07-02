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
refresh_semantic_index
extract_mentions
resolve_aliases
extract_events
aggregate_events
derive_facts
run_conflict_policy
rewrite_memory_page
rebuild_graph_projection
build_context_pack
run_agent_candidate
run_agent_review
run_skill_replay_eval
```

Some job types may initially be grouped into `run_memory_writeback`, but the payload must still record pipeline step and version.

The DB worker validates `payload.step == job_type` and a non-empty
`payload.pipeline_version` before calling any handler. Invalid payloads are
terminal domain failures and are audited without running handler code.

`rebuild_graph_projection` has a dedicated DB worker handler that calls the
real graph projection rebuild function, writes a `graph_projection.rebuilt`
audit event, and leaves facts as the source of truth.

`normalize_source` has a dedicated DB worker handler that reads the durable
SourceVersion/raw-source text from the object store, writes a
ProcessedMarkdownView plus raw-offset map, marks a replaced current view stale,
and audits `source.normalized`.

`split_structure` has a dedicated DB worker handler that reads the normalized
markdown object, creates a StoryChapter plus deterministic blank-line-delimited
StoryScene rows, creates bounded scene SourceSpans with raw offsets, segments
single-newline-separated explicit dialogue-attribution lines into individual
SourceSpans when every non-empty line in the scene is an attributed dialogue
line, and also segments conservative same-line English attributed dialogue
clauses, including `said: "..."` colon attribution, plus Chinese post-quote and
leading-attribution dialogue clauses when the scene text is fully covered by
two or more adjacent attributed dialogue spans separated only by whitespace or
by a comma/semicolon/em-dash English dialogue separator. Comma, semicolon, and
em-dash separators are retained on the preceding SourceSpan so source coverage
does not drop punctuation. It enqueues downstream `extract_mentions` work in
bounded batches and uses real DB-backed `split_structure` continuation jobs for
remaining SourceSpans instead of creating unbounded downstream bursts. It is
idempotent for an already split view and audits `source.structure_split`.

`build_context_pack` has a dedicated DB worker handler that invokes the real
`BuildWritingContextPack` application use case, preserving project permission,
idempotency, audit, and persisted context-pack behavior.
When a `current_scene_id` is supplied, `BuildWritingContextPack` reads the
persisted `StoryChapter` id/index/title into `current_position.chapter` and the
persisted `StoryScene` location, POV character, POV mode, story time,
emotional tone, and scene function into `current_position.scene`. If the caller
does not supply a current POV character, the use case falls back to the
scene's persisted `pov_character_id` for POV constraints and records that
effective POV on the persisted context-pack row.
The POV constraint includes conservative sensory limits for the current
scene/location and inner-access rules that allow direct interior access only to
the effective POV character unless an omniscient or multiple-POV mode is
explicitly present.
It also carries `allowed_knowledge` from active CharacterKnowledge rows for the
effective POV character and `forbidden_knowledge` for canon facts not present
in that POV knowledge set.
Active characters in the pack prefer canon SourceSpan-derived `appears_in`
facts whose object ref is the current scene; global canon character refs are
used only as a fallback when no current-scene appearance facts exist.
The pack ranks canon facts, risk facts, open reviews, recent events,
object/location state, and style samples with read-only relevance metadata.
The `character_agency_state` section also carries active CharacterKnowledge for
active characters as read-only `knowledge_state`, so the agent can reason about
known, suspected, misunderstood, false-belief, and explicit-unknown state
without creating or replacing facts.
Relevance reasons include current scene evidence, current source/version
evidence, active character, effective POV character, and current text/mode
token overlap. It also uses read-only semantic recall from AliasRecord text and
MemoryPage titles/open threads, plus persisted MemoryPage, SourceSpan, and
style-sample embeddings refreshed by the `refresh_semantic_index` worker job
when an embedding provider is configured, to boost existing evidence-backed
entries for the same canonical refs, matched fact evidence SourceSpans, or
matched style sample SourceSpans. The retrieval policy records vocabulary-only
recall as
`semantic_recall.mode=read_only_vocabulary_expansion` and persisted embedding
recall as `semantic_recall.mode=embedding_index_recall` or
`rrf_keyword_embedding_hybrid`. Ranking changes only the persisted
`AgentContextPackRecord` payload; it does not create or mutate facts, reviews,
memory pages, graph edges, SourceDeltas, or provider state.
`refresh_semantic_index` refreshes MemoryPage embeddings in bounded batches
before it starts high-cardinality SourceSpan and style-sample embeddings. When
additional MemoryPages remain, it uses DB-backed `refresh_semantic_index`
continuation jobs carrying an `after_memory_page_id` cursor and does not start
SourceSpan/style work until that phase drains. SourceSpan/style embeddings are
then refreshed in bounded paired batches; their continuations skip MemoryPage
refreshes and carry an `after_source_span_id` cursor so large manuscripts do
not require one unbounded embedding provider call.
When `constraints.context_budget.max_estimated_tokens` is supplied, the same
handler applies budget truncation after ranking, records estimated-token budget
metadata in the retrieval policy, and recalculates `evidence_refs` from the
retained snapshot entries only. The worker payload may carry `constraints`,
but budget truncation remains a ContextPack snapshot policy and cannot delete
or mutate upstream evidence, Memory, ReviewItem, FactAssertion, GraphProjection,
or SourceDelta rows.

`extract_mentions`, `resolve_aliases`, `extract_events`, `aggregate_events`,
`derive_facts`, and `run_conflict_policy` have dedicated DB worker handlers for
the current SourceSpan-scoped story pipeline. They read SourceSpan-backed text
or persisted story rows, write StoryMention, StoryAliasRecord,
StoryCanonicalEntity, StoryEventCandidate, StoryCanonicalEvent, FactAssertion,
EvidenceLogEntry, ReviewItem, MemoryPage, and GraphProjection state through the
real database, and audit each step. Alias resolution creates or reuses
provisional CanonicalEntity rows for story mentions, links StoryMention and
StoryAliasRecord to that entity, and merges repeated alias evidence across
SourceSpans without promoting the entity to canon. Conservative near-spelling
Latin alias variants such as `Mira`/`Myra` keep separate provisional entities
and create SourceSpan-backed `alias_conflict` ReviewItems with candidate and
target entity refs for author correction instead of silently merging.
SourceSpan-derived
FactAssertion, MemoryPage, GraphProjection, MemoryAnswer, and ContextPack paths
use those canonical entity ids as stable refs while retaining slug identities
for legacy grouped-writeback deduplication, user query matching, and MemoryPage
rewrite. Author `alias_conflict` ReviewItem resolution accepts correction
payloads, marks AliasRecord as `user_corrected`, repoints mentions and facts,
marks affected MemoryPages stale, queues real `rewrite_memory_page` jobs, and
rebuilds GraphProjection from facts. These handlers are production interfaces
with conservative rule-based first-pass behavior, including clear English/Chinese
actor/location/object/event cues and explicit owner-gain object-transfer facts.
Event extraction reads the project's effective Story Schema Pack. If a project
override disables an event type, the worker audits
`schema_event_type_not_allowed`, creates no EventCandidate, and continues the
pipeline without event-derived facts.
Fact derivation also reads the effective Story Schema relation whitelist before
deduplication or insert. If a project override disables a relation predicate,
the worker audits `schema_relation_not_allowed` as
`story.fact_relation_rejected` and creates no FactAssertion, EvidenceLogEntry,
CharacterKnowledge, MemoryPage, GraphProjection, or context-readiness side
effect for that attempted relation.
Schema-aware scene appearance derivation also considers project extension
entity types. Extension entities without `subtype_of` are weak nodes: attempted
strong relations such as `appears_in` are audited as
`schema_entity_relation_not_allowed` and skipped before fact or graph side
effects.
Effective relation directions are validated before write as well. Base Story
Schema roles cover built-in predicates; Genre Pack and Project Override
relations may declare structured `subject_types` and `object_types`, which are
compiled into the same role gate. For example, an `object` ref accidentally
placed in CanonicalEvent participants is audited as
`schema_relation_role_not_allowed` instead of being written as `present_at`,
and a project-defined `guards` relation can reject
`character -> guards -> event` when its schema allows only location/object
targets. Legitimate character/faction participants, event-object links, object
ownership, travel location state, and scene appearances continue through the
same evidence path.
Unknown entity ref types are rejected even earlier with
`schema_entity_type_not_allowed` unless the ref is a documented non-entity fact
target such as a `knowledge_claim`.
Malformed refs with missing `type`, missing durable `id`, or missing literal
`value` are audited as `schema_ref_shape_invalid` and skipped before
FactAssertion, EvidenceLogEntry, MemoryPage, GraphProjection, or readiness
side effects.
Schema Pack `extraction_hints.relation_patterns` can derive deterministic
custom relation facts after same-SourceSpan mentions have been resolved. A
pattern such as `{subject} is {object}'s master` creates a SourceSpan-backed
`master_of` FactAssertion only when the rendered template appears in the span
and both mentions match the configured effective schema types. The fact then
passes through `_ensure_fact`, conflict policy, MemoryPage update, and graph
projection like any other SourceSpan-derived fact. When `master_of` remains
allowed by the project effective schema, GraphProjection preserves it as a
`master_of` edge instead of collapsing it to `related_to`. English possessive
mention candidates are normalized before alias/entity creation so `Kestrel's`
resolves as the `Kestrel` entity.
Schema Pack `extraction_hints.mention_patterns` can derive deterministic
project-specific StoryMention rows before alias resolution. For example,
`Relic: {mention}` with `entity_type=artifact` records an `artifact` mention
from source prose, resolves it through the normal AliasRecord and
CanonicalEntity path, and can then participate in relation templates. The
mention and FactAssertion refs keep the project schema type, while the durable
CanonicalEntity row stores the nearest base subtype such as `object` to satisfy
the static entity-type constraint.
Schema Pack `extraction_hints.event_patterns` can derive deterministic
project-specific StoryEventCandidate rows after alias resolution. A pattern such
as `{subject} sealed the rite at {location}` with `event_type=ritual` creates a
SourceSpan-backed EventCandidate only when the rendered template appears in
source prose and referenced placeholders resolve to same-SourceSpan mentions of
the configured effective schema types. Patterns can also include `{recipient}`
with `recipient_type`; for `object_transfer` events that structured recipient
role can derive an owner fact through CanonicalEvent aggregation and normal
SourceSpan-backed fact derivation. The pattern itself does not write
FactAssertion, MemoryPage, GraphProjection, or canon directly.
English recipient-side `gave`/`handed`/`passed ... to` transfers, explicit
English ditransitive transfers such as `Mira gave Kestrel the Lantern Map`,
explicit English owner-gain subjects such as `Orrin watched as Kestrel received
the Lantern Map` or `Orrin watched as Kestrel recovered the Lantern Map`,
same-SourceSpan cross-sentence transfer cue sentences such as `Mira set the
Lantern Map on the table. Orrin watched as Kestrel received the Lantern Map.`,
schema event-pattern recipient roles such as
`{subject} bestowed the {object} upon {recipient}`, and Chinese recipient-side
`交给`/`递给` transfers, including aspect-marked `交给了`/`递给了`, active
`转交给`, and passive `地图已经被凯斯特转交给旧王` forms, plus explicit Chinese
owner-gain recovery such as `凯斯特取回灯图` derive owner facts for the named
recipient or gain subject instead of the giver or unrelated observer
participants. Chinese forbidden-knowledge transfer summaries such as
`Mira 不知道地图已经被转交给旧王` still derive the explicit recipient's owner state,
but the negated knowledge subject is not an object-transfer participant and
does not receive an event `present_at` fact. Ambiguous English
`gave`/`handed`/`passed` transfer prose without an explicit recipient does not
derive an `owns` fact from participant order; when the SourceSpan still contains
resolved participants and objects, it creates a SourceSpan-backed
`object_state_conflict` ReviewItem so author adjudication stays on the review
path instead of writing memory or graph ownership. English owner-gain prose with
an implicit beneficiary such as `Mira took the Lantern Map for Kestrel`, and
Chinese beneficiary transfer prose such as `米拉替凯斯特取回灯图`, likewise create a
SourceSpan-backed `object_state_conflict` ReviewItem and write no `owns`
FactAssertion or owner graph edge, because the beneficiary may not yet be the
current holder. Explicit owner-loss prose such as `Mira lost the Lantern Map`
likewise creates a SourceSpan-backed
`object_state_conflict` ReviewItem with `owner_lost` evidence and no `owns`
FactAssertion or owner graph edge, because the new owner state is unresolved.
Object-transfer prose with a pronoun object or a bounded Chinese omitted object
can resolve only a same-SourceSpan antecedent: when an
English `gave`/`handed`/`passed`/gain transfer cue sentence uses `it`/`them`, a
Chinese recipient-transfer cue sentence uses `它`/`它们`, or a Chinese
recipient-transfer summary such as `Kestrel 已经转交给旧王` omits the object after a
single concrete object mention in the immediately prior sentence, event
extraction binds the event object to the nearest prior object mention and records
`state_change.object_resolution` before the normal CanonicalEvent ->
FactAssertion -> EvidenceLogEntry path derives ownership. If the nearest prior
sentence contains competing concrete object antecedents, or if no concrete object
mention resolves, prose such as `Mira handed it to Kestrel`,
`Mira passed it to Kestrel`, `米拉发现了灯图和银钥匙。她把它交给凯斯特`, or
`米拉把它交给凯斯特` creates a SourceSpan-backed `object_state_conflict`
ReviewItem with unresolved-object evidence; it must not infer an object or write
ownership without author review. Conservative Chinese compound object mentions
joined by `和`/`与`/`及`/`、` are split only when every part is a recognized object
label, so coordinated objects can participate as separate antecedent candidates
without inventing unrecognized entities.
AggregateEventsHandler may merge adjacent same-source/version `object_transfer`
EventCandidates into one CanonicalEvent when their participant refs and object
refs match, for example `Mira handed Kestrel the Lantern Map.` followed by
`Kestrel received the Lantern Map from Mira.`. This is bounded EventSignature
aggregation; it still writes no facts directly and leaves CanonicalEvent ->
FactAssertion -> EvidenceLogEntry -> conflict policy to derive memory and graph
state. The same bounded rule may also merge the same event across direct
SourceVersion successors of one RawSource when the SourceSpans occupy the same
chapter/scene/span position or, for unstructured spans, the same raw start
offset. It does not merge unrelated positions, non-adjacent versions, or
cross-source evidence. Exact same event titles are likewise deterministic only
inside those same-source/version or direct-successor SourceVersion boundaries;
cross-source same-title evidence must not bypass adjudication.
For same-type CanonicalEvent/EventCandidate pairs that do not satisfy the
deterministic adjacency or direct-successor rules, including cross-source
evidence, `aggregate_events` may call the configured
`EventAggregationAdjudicationProvider`. The provider receives only existing
SourceSpan-backed event/candidate evidence and may return only `same_event`,
`related_but_distinct`, `conflict_version`, or `uncertain`.
`same_event` merges the candidate into the existing CanonicalEvent evidence
only when all compared SourceSpans have the same `source_scope`. If the provider
returns `same_event` across incompatible `source_scope` values, the worker
downgrades the application decision to `conflict_version`, records
`policy_reason="source_scope_conflict"` in the audit payload, and opens a
SourceSpan-backed `event_merge_conflict` ReviewItem before any merge can take
effect. If the existing event is still only `proposed` and comes exclusively
from review-required low-authority scopes such as `model_suggestion`, while the
current candidate comes from higher-authority material such as `user_draft`, the
worker marks the existing event disputed and keeps the higher-authority current
candidate as the proposed event so processing order cannot let model output
outrank author text.
`related_but_distinct` and `uncertain` leave the candidate as its own proposed
CanonicalEvent. `conflict_version` creates a disputed CanonicalEvent and
opens a SourceSpan-backed `event_merge_conflict` ReviewItem that compares the
new disputed event evidence with the existing event evidence. `derive_facts`
skips disputed events, so provider output cannot directly write facts, memory,
canon, graph edges, or review items; the worker is responsible for the formal
review object and graph projection. The worker validates that the provider cites
both the existing CanonicalEvent SourceSpan evidence and the current candidate
SourceSpan evidence before applying any decision.
Fact derivation also preserves `source_scope` boundaries. A FactAssertion has a
single `source_scope`, so `_ensure_fact` may merge additional SourceSpan evidence
only into a matching fact with the same scope. Matching subject/predicate/object
evidence from a different scope is stored as a separate proposed FactAssertion;
Conflict Policy then marks review-required scopes (`model_suggestion`,
`reference_only`, `discarded_draft`, `experimental`, `outline_plan`) or same-fact
cross-scope duplicates as disputed and creates a SourceSpan-backed
`source_scope_conflict` ReviewItem. This prevents low-authority evidence from
silently extending an existing canon fact. The created ReviewItem must not
suggest direct `accept`; its suggested author paths are `reject`,
`accepted_as_change`, and `fixed_by_text_edit`.
Formal resolution preserves that boundary: a model-suggestion
`source_scope_conflict` cannot be directly accepted. Author adoption must be
recorded as `accepted_as_change` or `fixed_by_text_edit` with a same-project
replacement SourceDelta whose scope is author-backed (`user_draft`,
`user_published`, or `author_note`); that replacement then goes through normal
source normalization and memory writeback. The original model-suggestion
FactAssertion remains non-canon. Author `reject` resolution marks the affected
model-suggestion FactAssertion `contradicted`, preserves SourceSpan evidence,
does not create SourceDelta, CanonPromotion, MemoryPage, provider, or canon
side effects, and rebuilds GraphProjection so the open ReviewItem reminder edge
is removed while the rejected fact remains traceable as contradicted evidence.
If the same fact appears later in higher-authority author material while a
review-required lower-authority same-fact assertion already exists
(`model_suggestion`, `reference_only`, `discarded_draft`, `experimental`, or
`outline_plan`), Conflict Policy promotes only the author-backed FactAssertion
to canon, leaves the lower-authority evidence on its own non-canon
FactAssertion, marks that lower-authority fact `outdated`, and supersedes any
open lower-authority `source_scope_conflict` ReviewItem with the author
SourceSpan as replacement evidence. This automatic authority path must not merge
lower-authority SourceSpan evidence into the author fact and must not mark
review-required lower-authority scopes as canon. Non-author-backed cross-scope
duplicates still produce a `source_scope_conflict` ReviewItem; predicate-specific
conflict types such as `object_state_conflict` remain for different object/state
claims, not same-fact source authority duplicates.
Author decisions for `event_merge_conflict` ReviewItems are handled later by
the formal `ResolveReviewItem` use case. `merge` merges event evidence and
deprecates the disputed CanonicalEvent only after replacement SourceDelta
validation. `split` records the author decision that the events are distinct,
restores the disputed CanonicalEvent to `proposed`, and uses the normal
MemoryPage/GraphProjection rebuild queues without deriving facts or canon
inside the ReviewItem operation. `reject` deprecates the disputed
CanonicalEvent, marks referenced EventCandidates `rejected`, and rebuilds
GraphProjection so the open ReviewItem reminder edge no longer appears without
deleting SourceSpan evidence or writing facts. `mark_intentional` records the
author decision and rebuilds GraphProjection so the open ReviewItem reminder
edge no longer appears, while leaving event evidence disputed and not promoting
facts or canon.
Travel events with explicit locations derive `located_in` state facts for
participants in addition to `occurred_at` event facts.
Scene-backed SourceSpans also derive deterministic `appears_in` facts from
entity mentions, and conflict policy treats accumulative relations such as
`appears_in` and `present_at` as multi-value facts while preserving exclusive
state conflict checks for `located_in` and `owns`.
Explicit scene metadata lines such as `POV: Mira`, simple character chapter
titles, diary/letter chapter titles such as `Mira's Diary`, and leading or
inline perspective phrases such as `From Mira's perspective, ...`,
`... from Mira's perspective`, and `在米拉看来...` are treated as scene POV
hints, not prose mentions. Alias resolution links the scene's
`pov_character_id` to the resolved CanonicalEntity for that mention and records
`pov_mode=third_limited` for the first-pass explicit hint path. If the explicit
POV identity is paired with first-person narration cues in the scene text, the
worker records `pov_mode=first_person` instead. When a first-person SourceSpan
gets its POV identity from structural context such as a chapter or diary/letter
title and the prose does not repeat the name as a mention, the worker may bind
only to a unique existing same-project character entity. It must not create a
new CanonicalEntity, fake alias, fact, review, memory page, or graph edge from
the structural hint. Perspective structures are stripped from prose mention
extraction so they do not create fake aliases such as `From Mira` or `Mira's`.
Self-naming first-person statements such as `My name is Mira` and `我叫萧寒`
also create normal character mentions and can bind the scene POV through the
same alias/entity path after resolution.
First-person dialogue can also bind the scene POV when the current SourceSpan
has exactly one explicit non-pronoun dialogue speaker surface that resolves to
one existing character through normal mention/alias resolution, for example
`Mira said, "I saw..."`. Multi-speaker first-person SourceSpans remain
unresolved, and this heuristic writes only `StoryScene` POV metadata. It does
not create entities, aliases, facts, reviews, memory pages, graph edges,
providers, or SourceDeltas.
Conservative inner/sensory focus heuristics can bind a third-limited scene POV
when one resolved character has at least two same-clause focus cues such as
`noticed`/`felt` and no other character has the same top score. The heuristic is
audited as `inner_sensory_focus_heuristic`, is skipped for first-person text,
and does not create facts, canon, reviews, or graph state.
If explicit rules and conservative heuristics cannot decide but the SourceSpan
has resolved character mentions, `resolve_aliases` may call the configured
`PovDetectionProvider`. The worker validates the structured POV mode,
confidence, and current SourceSpan evidence before applying it. A provider
character name must match one of the already resolved character mentions; an
unmatched name records `pov_mode=unknown`,
`pov_uncertainty_reason=model_character_not_resolved`, and does not create a
CanonicalEntity. Model-assisted POV writes are audited as `model_assisted` and
may update only `StoryScene` POV metadata.
Every rule, mode-only, heuristic, or model-assisted POV write stores
`pov_confidence`, `pov_evidence_span_ids`, and `pov_uncertainty_reason` on
`StoryScene`.
WritingContextPack includes those fields in both `current_position.scene` and
`pov_constraint`.
If first-person narration is present without an explicit or structurally
resolvable POV character, the worker records
`StoryScene.pov_mode=first_person` while leaving `pov_character_id` unset
rather than fabricating a character identity.
After alias resolution, the same SourceSpan worker links
`StoryScene.location_entity_id` to the first resolved location mention in that
scene, including locations declared in explicit metadata lines such as
`Location: Harbor Nine`. This keeps scene location downstream of real
mention/entity evidence while keeping metadata labels out of prose extraction.
The structure split handler also persists explicit non-entity scene metadata
lines such as `Time: Dusk`, `Tone: tense`, and `Function: reveal` to
`StoryScene.story_time`, `emotional_tone`, and `scene_function`; these labels
are likewise excluded from prose mention extraction.
After alias resolution has linked mentions to CanonicalEntities, the same
SourceSpan worker records explicit single-speaker dialogue evidence on the
SourceSpan: patterns such as `Mira said, "..."`, `Mira said: "..."`,
`"...," Mira said`, `米拉说：“……”`, and `“……”米拉说。` set
`SourceSpan.speaker_entity_id` to the resolved character and
`narration_layer="dialogue"`. The structure splitter now prevents common
single-newline dialogue blocks from becoming false multi-speaker SourceSpans by
splitting English and Chinese attributed dialogue lines into separate
SourceSpans before the SourceSpan worker runs, and does the same for adjacent
same-line English and Chinese attributed dialogue spans that contain no
intervening prose, including English colon attribution and conservative
English comma, semicolon, and em-dash separators between two attributed spans.
If one SourceSpan still contains multiple different explicit speakers, the
worker leaves `speaker_entity_id` unset rather than assigning the whole span to
one character.
Explicit SourceSpan statements such as `Mira knows the Harbor Code` derive a
SourceSpan-backed `knows` FactAssertion and an active CharacterKnowledge row
that points back to the fact. `suspects`, explicit false belief, and explicit
misunderstanding statements still use the Story Schema relation predicate
`knows`; their certainty is stored on the CharacterKnowledge row and on the
knowledge-claim object ref, not as ad hoc FactAssertion predicates.
`does_not_know` remains the negative Base relation predicate. English narrative
tense variants such as `Arden knew the north gate was unguarded`, `Bela did
not know the treaty was false`, and `Cato suspected the hidden ledger was
forged`, proposition recollection such as `Iris remembered that the old cipher
was broken`, plus past-tense false-belief and misunderstanding forms such as
`Dena falsely believed the beacon was lit` and `Eldon mistakenly believed the
treaty was valid`, and explicit awareness forms such as `Faye was aware that
the east gate was open`, `Galen was unaware that the west gate was trapped`,
`Hale was not aware that the treaty was forged`, and `Juno became aware that
the east gate was open`, preserve those same predicate/certainty semantics.
Object recollection such as `Iris remembered the old song` and broad perception
phrasing such as `Juno became aware of the bells` remain outside durable
CharacterKnowledge. Explicit English realization cues such as `Arden realized
that the north gate was unguarded` and `Gwen realised that the route was
unsafe`, plus understanding cues such as `Bela understood the treaty was false`
and `Hale understood that the bridge was unsafe`, plus explicit present-tense
that-clause forms such as `Kira realizes that the beacon is false`, `Lena
realises that the east road is blocked`, `Milo understands that the treaty is
void`, and `Nia noticed that the blue lantern was missing`, and `Oren saw that
the gate was open`, `Pia observed that the bridge was damaged`, `Quinn
recognized that the cipher was false`, and `Rhea recognised that the ledger was
missing`, plus confirmation cues such as `Sera confirmed that the route was
safe` and `Tobin verified that the seal was broken`, and reasoning cues such as
`Uma deduced that the vault was empty` and `Vera concluded that the signal was
false`, plus acquisition/reasoning cues such as `Wren figured out that the old
lock was trapped` and `Yara worked out that the cipher was old`, and inference
cues such as `Zane inferred that the passage was hidden` and `Ari reasoned that
the map was incomplete`, plus determination cues such as `Bea determined that
the bridge was unsafe` and `Cyra ascertained that the seal was forged`, follow
that same CharacterKnowledge path. Proof cues such as `Dax established that the
alibi was false` and `Eli proved that the vial was poisoned` also follow that
path. Explicit proposition learning such as `Faye learned that the tunnel was
flooded` also follows that path. Object-only realization, understanding,
perception, recognition, confirmation, conclusion, figuring-out, inference,
determination, establishment, or learning such as `Kira realizes the cost`,
`Arden realized the cost`, `Bela understood the treaty`, `Nia noticed the blue
lantern`, `Oren saw the blue lantern`, `Pia observed the blue lantern`, `Quinn
recognized the old emblem`, `Sera confirmed the old seal`, `Vera concluded the
meeting`, `Wren figured out the old lock`, `Zane inferred the answer`, `Bea
determined the route`, `Dax established the camp`, and `Faye learned the old
song` remain outside durable CharacterKnowledge.
Chinese statements such as `米拉知道地图被偷`,
`萧寒怀疑奥林偷走地图`,
`凯斯特误以为灯图很安全`, and `奥林不知道米拉的真实身份` follow the same
SourceSpan -> FactAssertion -> CharacterKnowledge path, as do explicit
realization/acquisition cues such as `萧寒意识到地图被偷`,
`萧寒了解到地图被偷`, `萧寒得知地图被偷`, `米拉明白暗门已经打开`, and
`凯斯特发现钥匙不见了`.
Locative discovery prose such as `米拉在九号码头发现了灯图` and bare
object-discovery prose such as `凯斯特发现钥匙` remain event and location/object
evidence rather than CharacterKnowledge. Bare object-understanding prose such
as `米拉明白暗门` likewise remains outside durable CharacterKnowledge.
Bare object-perception prose such as `萧寒看出暗门` also remains outside
durable CharacterKnowledge. Bare object-realization/acquisition prose such as
`萧寒意识到暗门`, `萧寒了解到暗门`, and `萧寒得知暗门` remain outside durable
CharacterKnowledge.
Conservative
communication statements such as
`Mira told Kestrel about the Harbor Code`, `米拉告诉萧寒地图被偷`,
`米拉对萧寒说地图被偷`, and `凯斯特向奥林透露灯图藏在港口` create knowledge only
for the resolved recipient character, not for the speaker, and use the same
SourceSpan evidence path. Passive English communication such as `Arden was told
by Bela that the north gate was unguarded`, `Cato was warned by Dena about
the hidden ledger`, and agentless forms such as `Arden was told that the north
gate was unguarded` follow the same listener-only path. This keeps
CharacterKnowledge downstream of SourceSpan evidence and FactAssertion identity
instead of treating it as a graph or provider output. Conservative
adjacent-sentence and bounded same-SourceSpan
non-adjacent hearing statements such as
`Mira said that the Harbor Code was broken. Kestrel overheard.`,
`Mira said that the Harbor Code was broken. The lamps went out. Kestrel
overheard the warning.`, `米拉说地图被偷。萧寒听见了。`, and
`米拉说地图被偷。灯灭了。萧寒听见了。` also create knowledge only for the
listener. The non-adjacent path is limited to one or two short intervening
sentences and does not count broader pronoun/coreference inference, cross-scene
transfer, or implicit knowledge as complete.
Bounded English and Chinese adjacent-scene hearing is also supported when the
current SourceSpan is a simple listener sentence such as `Kestrel overheard the
warning.` or `萧寒听见了。`, and the immediately preceding StoryScene in the same
SourceVersion ends with a named speaker claim such as `Mira said that the
Harbor Code was broken.` or `米拉说地图被偷。`. The derived FactAssertion and
EvidenceLogEntry cite both SourceSpans, while CharacterKnowledge records the
listener span and scene as the learning point. The listener must resolve through
the current SourceSpan's mention/alias path; the speaker text is supporting
SourceSpan evidence but is not written as knowledge and is not a worker-order
dependency. This does not count non-adjacent scenes, cross-source transfer,
pronoun/coreference inference, or implicit knowledge as complete.
Explicit source-attributed acquisition statements such as
`Arden learned from Bela that the north gate was unguarded`,
`Cato heard from Dena about the hidden ledger`,
`Eldon found out from Faye that the treaty was forged`, `萧寒从米拉那里得知地图被偷`,
and `奥林听米拉说灯图藏在港口` likewise create knowledge for the
listener/learner only, while the named source is extracted as SourceSpan
evidence but does not receive inferred knowledge. Explicit unattributed English
acquisition such as `Arden heard that the north gate was unguarded`,
`Bela heard about the hidden ledger`, and `Cato found out that the treaty was
forged`, explicit unattributed Chinese hearsay such as `萧寒听说地图被偷`, plus
proposition discovery such as `Dena discovered that the harbor key was missing`,
also creates knowledge for the listener/learner, but bare Chinese object-hearsay
such as `萧寒听说暗门`, plain sensory hearing such as `Arden heard the bell`, and
locative discovery such as `Dena discovered the Harbor Key at Harbor Nine`
remain event/perception or location prose rather than durable
CharacterKnowledge. When a later
`known` statement for the same character and knowledge object is ingested, prior
active `suspected`, `false_belief`, `misunderstands`, or `does_not_know`
CharacterKnowledge rows for that object are marked `superseded`; their
FactAssertions and EvidenceLogEntries remain intact.
Structured `FACT:` memory extraction directives used by grouped writeback are
skipped by scene mention extraction so they do not create false scene
appearances from machine-readable fact notation.
The grouped `run_memory_writeback` handler uses the configured
`MemoryExtractionProvider`. Local deterministic extraction is allowed only for
dev/tests/evals at the provider boundary. Production `openai` mode uses the
OpenAI structured-output memory adapter selected by
`SEXTANT_MEMORY_LLM_PROVIDER` or inherited from `SEXTANT_LLM_PROVIDER`. The
handler validates each returned fact's ref shape, predicate, risk level, and
project effective Story Schema compatibility before any normalized view,
SourceSpan, FactAssertion, ReviewItem, MemoryPage, EvidenceLogEntry, or
GraphProjection side effect. Invalid provider output records a failed-terminal
SkillRun and terminal worker failure. The shared fact schema allows documented
knowledge `secret` refs for `knows`, `does_not_know`, and `reveals`, but still
blocks invented predicates, unknown entity types, weak-extension strong
relations, malformed refs, and invalid Base relation roles.
Chinese actor mention extraction uses shortest verb-preceding name matches and
filters particle-led fragments so phrases such as `的拇指` or `米拉停` do not
enter alias, appearance, fact, MemoryPage, GraphProjection, or ContextPack
state as characters.
Explicit Character Agency Profile author-note / character-sheet field lines in
English and Chinese, such as `Mira's core desire: ...`,
`Mira's moral boundary: ...`, `米拉的核心欲望：...`, and
`米拉的道德边界：...`, derive SourceSpan-backed profile FactAssertions through
the normal mention, alias, fact derivation, conflict policy, and MemoryPage
rewrite chain. These behavior-profile facts update MemoryPage and
WritingContextPack agency state but are not projected as GraphProjection edges.
Project Story Schema `extraction_hints.agency_profile_fields` can extend the
accepted author-note / character-sheet labels without changing production code.
For example, a project override can map `执念` to `core_desire` and
`禁忌边界` to `moral_boundary`; the worker still creates the character mention,
resolves the alias, validates the allowed agency predicate, writes a
SourceSpan-backed FactAssertion/EvidenceLogEntry, and queues MemoryPage rewrite
through the same evidence path.
Richer schema-pack extraction beyond deterministic mention, event, and relation
templates, broader alias/entity split-merge policy, richer entity picker
workflows, ambiguous transfer-direction parsing beyond the narrow
recipientless-review item above, complex multi-party transfers beyond explicit
English recipient/gain-subject cue sentences, schema event-pattern recipient
roles, and Chinese `交给`/`递给`,
pronoun/coreference-heavy transfer, cross-source transfer, richer event
signatures, and advanced conflict classification remain future work.

`run_agent_candidate` has a dedicated DB worker handler that invokes the real
`RunActionRequest` application use case with the configured StoryDraftProvider.
It validates the job prompt version against the provider skill version, requires
the documented input hash payload, persists WritingContextPack,
StorytellingControl, SkillRun, DraftCandidate, and draft-local
AgentReviewFinding rows through the application boundary, and must not create
SourceDelta, ReviewItem, FactAssertion, MemoryPage, GraphProjection, or canon
before author acceptance.

`run_agent_review` has a dedicated DB worker handler that reads the durable
DraftCandidate text from object storage, writes draft-local
AgentReviewFinding rows, updates candidate offer/block status, and audits the
review. It must not create ReviewItem, SourceDelta, MemoryPage, FactAssertion,
or canon before author acceptance.

`run_skill_replay_eval` has a dedicated DB worker handler that compares a
stored `SkillRun.structured_output` and optional `validation_result` against
expected replay payloads. It does not call live providers, does not create
Memory/Canon/Graph state, and audits pass/fail with structured mismatch paths
and hashes only, not full manuscript or candidate text. Mismatches are terminal
domain failures.

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
| extract_mentions | source_span_id + extractor_version |
| resolve_aliases | source_span_id + resolver_version |
| extract_events | source_span_id + extractor_version |
| aggregate_events | source_span_id + aggregator_version |
| derive_facts | source_span_id + derivation_version |
| run_conflict_policy | source_span_id + policy_version |
| run_memory_writeback | source_delta_id + pipeline_version |
| refresh_semantic_index | project_id + provider + model_name + index_scope_hash |
| rewrite_memory_page | memory_page_id + source_delta_id + decision_item_ref |
| rebuild_graph_projection | project_id + projection_scope + source_state_hash |
| build_context_pack | action_request_id + context_scope_hash |
| run_agent_candidate | action_request_id + prompt_version + input_hash |
| run_agent_review | draft_candidate_id + review_policy_version |
| run_skill_replay_eval | skill_run_id + case_id + expected_output_hash |

If the same key exists and succeeded, return existing result.

`rewrite_memory_page` rebuilds the stale page from canon FactAssertions that
reference the page target as either `subject_ref` or `object_ref`, plus derived
review/event state. It rewrites `current_canon`, `appearance_log`, `event_log`,
`relationships`, `open_threads`, and `source_refs`, then refreshes
GraphProjection from canon facts and confirmed CanonicalEvent structures. It
must not delete SourceSpan evidence, promote facts, or use GraphProjection as
input truth.

`rebuild_graph_projection` projects FactAssertions with graph-projectable
statuses (`canon`, `proposed`, `inferred`, `disputed`, `contradicted`,
`outdated`) plus confirmed CanonicalEvent participant/location/object
structure, plus active direct CharacterKnowledge refs for `secret`, `event`,
`lore`, and `knowledge_claim` targets. FactAssertion status maps directly to
GraphProjection `edge_status` so risk/dispute edges remain queryable without
becoming canon. CanonicalEvent and CharacterKnowledge auto-link use the same
effective Story Schema validation as facts, so invalid relation, ref-shape, or
role combinations are skipped instead of becoming graph edges. Fact-backed
CharacterKnowledge rows are skipped because their `knows` / `does_not_know`
FactAssertions already supply the graph edge. The rebuild `source_state_hash`
includes FactAssertion, CanonicalEvent, and active CharacterKnowledge inputs.

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

Running-job cancellation is cooperative through the database row:

```text
cancel API sets running job -> cancelled
worker refreshes job after handler returns
if status == cancelled -> clear lease fields, audit job.cancelled_acknowledged
```

The worker must not overwrite a cancelled running job with `succeeded`.

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

Implemented worker retry classes:

| failure class | default max attempts | initial delay | terminal behavior |
|---|---:|---:|---|
| infrastructure | 5 | 30s | terminal after retry budget exhaustion |
| provider | 3 | 60s | terminal after retry budget exhaustion |

Retryable handlers should raise `InfrastructureRetryableJobError` for database,
object-store, lock, and network infrastructure failures, and
`ProviderRetryableJobError` for LLM/provider timeout, quota, or rate-limit
failures. The worker records `failure_class`, `attempt_count`, `max_attempts`,
and `next_run_after` in audit for retryable failures. When the retry budget is
exhausted it marks the job `failed_terminal` with
`terminal_reason=retry_budget_exhausted`.

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

Current implementation queues `normalize_source` for new SourceVersions created
by `CreateSource`, `CreateSourceDelta`, Candidate acceptance, and restore-like
SourceDelta entrypoints. `normalize_source` queues `split_structure` for the
current `ProcessedMarkdownView`. `split_structure` creates/reuses bounded
scene SourceSpans, chunking long scenes at conservative prose boundaries before
falling back to hard limits, and queues `extract_mentions` for each span; each
SourceSpan worker queues the next step through alias resolution, event
extraction, event aggregation, fact derivation, and conflict policy.
Scene-backed mentions generate `appears_in` facts and edges through the same
FactAssertion/EvidenceLogEntry/MemoryPage/GraphProjection path, with
accumulative relations allowed to coexist across multiple scenes/events.
For exclusive state predicates such as `located_in` and `owns`, conflict policy
can automatically mark an older canon fact `outdated` and promote the new fact
only when both facts carry sortable `valid_from_scene_id` scene positions and
the new scene is later. Without that scene-order evidence, the conflict still
creates a ReviewItem instead of silently rewriting canon.
Machine-readable `FACT:` directives stay in the grouped memory writeback path
and are not treated as scene mentions. `run_memory_writeback` still owns the grouped
submitted-text SourceDelta SourceSpan/evidence/fact/review/memory/graph
writeback step. Memory writeback and conflict policy mark
`ContextPackReadiness` as pending; they do not auto-build full ContextPacks.
Author-requested ContextPack builds consume matching pending/stale readiness
rows only for SourceSpans included in the generated pack evidence. Author
writeback decisions and ReviewItem operations mark direct SourceSpan-backed
review dependency readiness `stale` when fact/review/memory/graph state changes.
Split/merge and supersede ReviewItem operations persist authored replacement
refs on the ReviewItem while worker side effects continue to rebuild stale
MemoryPage and GraphProjection read models rather than writing facts directly.
Richer semantic stale-resolution policy continues to mature. Fact/review writes now deduplicate
across grouped writeback and source-pipeline paths by `type/id` ref identity,
merging SourceSpan evidence and existing ReviewItem evidence instead of
creating duplicate FactAssertions or ReviewItems when labels or mention ids
differ.

The pipeline can execute grouped writeback steps temporarily, but each visible
job step must emit audit and structured step result.

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
