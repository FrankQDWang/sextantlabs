# 06. Story Skills and LLM Harness

Story Skills are deterministic, auditable processing protocols. LLM calls are adapters behind ports, not domain truth.

## Current Implementation Status

As of 2026-07-01, Sextant has completed the local Story Skill architecture required by the repository contracts.

Implemented pieces:

- provider ports and adapters for StoryDraft, POV Detection, Memory Extraction, Event Aggregation, and Embedding;
- prompt files under `prompts/skills/...`;
- prompt metadata/hash locking through `prompt_registry.py`;
- first-class `StorySkillRegistry` metadata for the production skill set;
- implemented `run_skill(skill_name, skill_version, input_object, runtime_context) -> SkillRunResult`;
- Resolver planning for ActionRequest flows and worker job steps;
- executable skill document registry metadata with trigger/input/output/review/writeback/eval fields;
- Codex subagent judge eval rubric (eval only; not production authority);
- real-corpus chapter/slice boundary eval using the ignored local Fanren sample without committing source text;
- RRF keyword+embedding fusion for context retrieval;
- sliding-window automatic source/context organization for style memory and scene-local context;
- `SkillRun` persistence and replay-diff evaluation;
- worker job handlers for source, memory, review, context, graph, and agent work.

Prompt registry is still not Skill Registry, and provider adapters are still not production authority. Remaining non-local completion is hosted: live provider proof refs, deployed smoke, clean-context UI acceptance, and other externally evidenced release gates.

## Target Skill Registry

First production set:

```text
source-normalization
split-structure
detect-pov
extract-mentions
resolve-alias
extract-events
aggregate-events
derive-facts
check-continuity
rewrite-current-canon
build-writing-context-pack
answer-with-evidence
character-agency-pass
storytelling-control
next-page-agent
agent-review
```

The legacy `build-next-page-context` label maps to `build-writing-context-pack` for compatibility only; it is not a new skill name.

## Skill Document Contract

Each skill must have:

```text
name
version
trigger
inputs
input_schema_version
transform
deterministic_rules
model_judgment_allowed
outputs
output_schema_version
review_policy
writeback_policy
prompt_version
golden_cases
failure_cases
```

No skill may be merged without at least one golden case.

## Runtime Contract

Skill callable signature:

```text
run_skill(skill_name, skill_version, input_object, runtime_context) -> SkillRunResult
```

`runtime_context` may expose:

```text
project_id
request_id
clock
id_generator
repository ports
llm_client port
embedding_client port
audit sink
object store port
```

It must not expose concrete DB session, provider SDK, or environment secrets.

## Structured Output

All model-assisted skills must return structured output before validation.

Pipeline:

```text
raw output
  -> parse
  -> schema validation
  -> domain validation
  -> evidence binding check
  -> policy classification
  -> proposed output
```

The structured output boundary must not be implemented as a local prose cue parser. Natural-language cues may appear in provider prompts or eval examples, but production validators may only check structured schema, enum membership, SourceSpan ancestry, evidence boundaries, review policy, and writeback/canon policy.

If schema validation fails, the skill may retry with bounded retry policy. Invalid output must not be partially applied.

Implemented model-assisted POV detection uses the same boundary. The
`PovDetectionProvider` returns `pov_character_name`, `pov_mode`, `confidence`,
`evidence_span_ids`, and `uncertainty_reason` as structured output. Application
validation requires a whitelisted POV mode, confidence in `0..1`, and evidence
that includes the current `SourceSpan`. The provider may suggest only names
from resolved character mentions supplied in the request; if the returned name
does not match a resolved mention, the worker records an unknown POV judgment
with uncertainty instead of creating a CanonicalEntity. POV provider output may
write only `StoryScene` POV metadata after alias resolution and must not create
facts, memory, reviews, canon, graph projections, or SourceDeltas.

Implemented grouped memory writeback uses the same provider boundary. The
`MemoryExtractionProvider` returns only structured proposed facts with
`subject_ref`, `predicate`, `object_ref`, and a whitelisted `risk_level`.
The worker validates the `MemoryExtractionResult`, ref shape, predicate, and
risk level before any FactAssertion, EvidenceLogEntry, ReviewItem, MemoryPage,
or GraphProjection side effect. Invalid provider output is recorded as a
failed-terminal `SkillRun` and terminal worker failure. The production OpenAI
adapter has no authority to create canon, memory pages, review items, graph
state, or SourceDeltas; it only returns the structured schema consumed by the
writeback policy.

## Prompt Versioning

Prompt files live under:

```text
prompts/skills/<skill-name>/<version>.md
```

Prompt metadata:

```yaml
skill_name: extract-events
skill_version: 1
prompt_version: 1
input_schema_version: 1
output_schema_version: 1
model_constraints:
  structured_output: true
  evidence_required: true
```

Prompt changes require:

1. version bump,
2. updated golden expected output,
3. audit of changed failure cases,
4. CI golden test run.

The current implementation stores OpenAI StoryDraft, POV Detection, Memory
Extraction, and Event Aggregation prompts under `prompts/skills/...`. Each file
has front matter for skill name/version, prompt version, input/output schema
versions, model constraints, golden cases, and failure cases. The OpenAI
provider adapters load their system prompt body through the prompt registry
rather than embedding it in code. `backend/tests/contract/test_prompt_registry.py`
locks prompt hashes under `evals/expected/prompts`, so prompt text or metadata
changes fail the quick gate until the expected prompt lock and referenced
golden/failure cases are updated.

## LLM Trust Boundary

Allowed:

```text
model proposes EventCandidate
model proposes FactAssertion with evidence spans
model flags AgentReviewFinding
model ranks possible alias matches
model drafts candidate prose
```

Forbidden:

```text
model writes MemoryPage.current_canon
model sets FactAssertion.fact_status = canon
model creates GraphProjection canon edge
model resolves ReviewItem without user/policy action
model treats its previous output as evidence
```

The implemented Semgrep provider-boundary guardrail fails provider classes that
directly construct ORM artifacts for facts, review, memory pages, SourceDeltas,
SourceSpans, EvidenceLogEntries, GraphProjection runs/edges, aliases, canonical
entities, or canonical events. Provider adapters may return only structured
outputs for application/worker validation.

## Skill-Specific Boundaries

### `source-normalization`

Input: RawSource or SourceVersion.
Output: ProcessedMarkdownView, raw offset map, cleaning profile.

Rules:

1. Preserve raw text in object store.
2. Never delete semantic content silently.
3. OCR uncertainty is marked, not corrected as fact.

### `split-structure`

Output: Chapter, Scene, SourceSpan candidates.

Rules:

1. Scene is primary extraction unit.
2. SourceSpan must map to raw offsets.
3. Structure failure can block downstream extraction, but not raw source save.

### `extract-mentions`

Output: Mention list.

Rules:

1. Mention is not CanonicalEntity.
2. unresolved mention is valid output.
3. mention_type must obey Story Schema Pack.

### `resolve-alias`

Output: AliasRecord updates and possible ReviewItem proposals.

Rules:

1. Low confidence alias cannot strong merge.
2. Scene-local alias stays local unless evidence supports wider scope.
3. Conflicting alias produces ReviewItem, not silent merge.

### `extract-events` and `aggregate-events`

Rules:

1. EventCandidate first, CanonicalEvent second.
2. Ambiguous event match uses `related` or `conflict_version`, not forced merge.
3. Event aggregation cannot directly promote facts to canon.

### `derive-facts`

Rules:

1. FactAssertion requires SourceSpan or CanonicalEvent evidence.
2. Derived fact remains proposed/inferred until gate.
3. `source_scope` is carried into policy.

### `check-continuity`

Rules:

1. Finds risk; does not block ingest.
2. Emits ReviewItem candidates through review policy.
3. Must distinguish intentional ambiguity from contradiction when evidence supports it.

### `rewrite-current-canon`

Rules:

1. Only consumes facts already accepted by promotion policy.
2. Must preserve source_refs.
3. Cannot erase contradictions without review resolution.

### `next-page-agent`

Rules:

1. Produces BeatCandidate or DraftCandidate.
2. Must consume ProseRenderingContract for prose output.
3. Must not write SourceDelta.

### `agent-review`

Rules:

1. Produces AgentReviewFinding.
2. Uses `goals/26` risk_type whitelist.
3. Cannot create ReviewItem.

## Golden Tests

Golden fixture shape:

```text
evals/datasets/<skill>/<case>.input.json
evals/expected/<skill>/<case>.expected.json
```

Each golden case must include:

1. input object,
2. expected structured output,
3. expected evidence refs,
4. expected non-promotion behavior,
5. expected review finding if risk exists.

## Replay Tests

LLM replay tests run against stored structured outputs, not live provider calls.

Quick-gate replay tests use stored structured outputs. Production readiness still requires real provider E2E validation against fixed source slices, deterministic schema/evidence checks, and Codex subagent judge review with a structured eval rubric; the judge is not production authority. Provider output variability is acceptable only when the invariant checks and eval rubric reject unsupported claims, source-boundary drift, over-inference, missing evidence, and direct memory/canon writes.

## Audit Record

Each skill run records:

```text
request_id
skill_name
skill_version
prompt_version
model/provider
input_hash
structured_output
raw_output_ref
validation_result
retry_count
latency/cost
```

Audit record is not Memory evidence.

## Acceptance

Skill implementation is complete when:

1. Input and output schemas are versioned.
2. Golden tests cover success and one failure/risk case.
3. Skill cannot import infra directly.
4. Invalid structured output cannot write domain state.
5. Prompt changes fail CI unless golden expected output is updated.
