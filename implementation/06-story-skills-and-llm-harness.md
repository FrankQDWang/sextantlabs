# 06. Story Skills and LLM Harness

Story Skills are deterministic, auditable processing protocols. LLM calls are adapters behind ports, not domain truth.

## Skill Registry

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

The old `build-next-page-context` name maps to `build-writing-context-pack`.

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

If schema validation fails, the skill may retry with bounded retry policy. Invalid output must not be partially applied.

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

Live provider tests are optional and never required for PR quick gate.

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
