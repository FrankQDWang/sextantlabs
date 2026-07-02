# Source Pipeline Cleanup Design

Date: 2026-06-29

Status: draft for user review

## Purpose

Cleanly remove the invalid direction where Sextant tries to infer novel prose meaning through local word lists, regexes, and cue families inside the source pipeline.

This is not a downgrade. The goal is to delete misleading code, tests, and documentation so future Codex work starts from a clean production target:

- thin harness for deterministic infrastructure, schema, evidence, review, and canon gates;
- rich skills and provider calls for creative/language judgment;
- deterministic validators for final system state transitions;
- no local prose-word taxonomy pretending to understand fiction.

## Confirmed Problem

The current source-pipeline direction contains too much prose semantic interpretation in deterministic Python code. In particular, cue families such as "report", "statement", "message", "heard", or equivalent Chinese words were becoming a local semantic parser.

That direction is wrong for Sextant because:

- it encodes creative prose interpretation in brittle word tables;
- it invites tests written from self-created sample sentences;
- it can make memory and canon appear more complete than the evidence supports;
- it pollutes future context by documenting narrow local behavior as production progress;
- it does not match the intended thin-harness, rich-skills architecture.

The cleanup must delete this direction rather than rename it as an explicit business taxonomy.

## Current Architecture Audit

Sextant has not actually completed the intended thin-harness and rich-skills creative semantic architecture.

Current repository state has useful pieces:

- provider ports and adapters;
- prompt files under `prompts/skills/...`;
- a prompt registry that loads prompt metadata and locks prompt hashes;
- `SkillRun` persistence and replay-diff evaluation;
- worker job handlers for source, review, memory, context, graph, and agent jobs.

These pieces are not yet a real Story Skill architecture.

Missing or incomplete pieces:

- no first-class `SkillRegistry`;
- no implemented `run_skill(skill_name, skill_version, input_object, runtime_context) -> SkillRunResult` runtime contract;
- no resolver that selects a Story Skill from input type, author intent, source type, and project policy;
- no skill document registry with trigger, inputs, transform, deterministic rules, model judgment policy, review policy, writeback policy, golden cases, and failure cases as executable metadata;
- no rich-skill layer that owns creative semantic interpretation outside the source pipeline;
- no Codex subagent judge eval rubric (not production authority) for semantic evaluation;
- no real-corpus chapter/slice skill eval against the local Fanren sample;
- no systematic negative eval coverage for over-inference, unsupported memory writes, source-boundary drift, or canon pollution.

The current prompt registry is only a prompt loader/hash-lock mechanism. It must not be described as a Skill Registry.

The current effective prompt-backed skill/provider surfaces are limited to:

- `openai_story_draft`;
- `openai_pov_detection`;
- `openai_memory_extraction`;
- `openai_event_aggregation`.

Local deterministic providers exist for development/tests at the provider boundary, plus local deterministic embedding. They are not proof of rich-skill semantic quality.

Current evaluation coverage is limited:

- prompt metadata and prompt hash locking;
- local deterministic provider golden tests;
- `SkillRun` replay comparisons against stored structured output and validation result.

This does not evaluate creative semantic generalization. It does not replace real provider E2E validation, Codex subagent judge eval review (not production authority), eval rubric scoring, real-corpus chapter/slice evals, or deployed acceptance.

## Non-Negotiables

- Do not replace the removed word lists with another natural-language cue taxonomy.
- Do not degrade strict cues into looser generic buckets.
- Do not add fallback paths that still write memory, canon, facts, events, or review items from local prose regexes.
- Do not allow provider output to write directly to memory or canon.
- Do not treat local green tests as hosted readiness.
- Do not commit source corpus text or paste long source passages into docs or tests.

## Scope of This Spec/Plan Change

This spec/plan change targets goal and target documentation only.

It should clarify the future target state and remove misleading direction from the target docs. It is not itself the code/test cleanup execution pass.

The code and test cleanup must be planned and executed separately after the target documentation is corrected. That later execution pass should remove invalid source-pipeline prose inference code, delete corresponding tests, and update progress/gap/decision docs based on the cleaned codebase state.

## Delete Scope

The cleanup implementation should remove or disable all production paths that infer these domain outcomes from local prose word tables or regexes:

- character knowledge;
- fact assertions;
- canon promotions;
- event extraction;
- relation extraction;
- scene/POV semantic conclusions;
- object transfer or possession facts;
- review items created from local prose inference;
- memory writeback proposals created from local prose inference.

The cleanup should also delete the tests whose main purpose is to prove those local prose rules, especially tests built from invented Chinese example sentences where the test author controls both the sample and the expected interpretation.

Documentation cleanup must remove claims that those rules are valid production coverage, anti-overfit progress, or a completed semantic layer.

## Preserve Scope

The cleanup must preserve infrastructure that is still aligned with the production design:

- source import, normalization, source delta creation, and source versioning;
- source slicing and SourceSpan anchoring;
- EvidenceLogEntry mechanics;
- persistence, migrations, API contracts, and worker orchestration;
- provider boundaries, structured output validation, prompt registry, and failure handling;
- review queue mechanics when review items are backed by real SourceSpan evidence;
- memory page, canon policy, and graph projection mechanics when they are fed through approved evidence/review paths;
- semantic embeddings, pgvector, and recall infrastructure as retrieval support;
- context-pack construction and token-budget handling as non-authoritative selection logic;
- frontend workbench behavior that is backed by real backend state.

Preserved infrastructure must not silently keep the deleted prose-inference behavior alive.

## Replacement Architecture

The intended shape is:

1. The harness stores, slices, indexes, and retrieves source evidence.
2. Rich skills and provider calls propose structured candidates from bounded source spans.
3. Deterministic validators check candidate shape, enum type, evidence boundaries, source ancestry, review policy, and canon policy.
4. Valid candidates enter review or memory writeback preview, not direct canon.
5. Author acceptance and review/canon gates decide durable state.

The deterministic layer should define closed system categories such as:

- source artifact type;
- candidate type;
- evidence kind;
- review item kind;
- canon policy;
- graph projection edge kind;
- writing-context pack section kind.

It should not define a natural-language synonym table that attempts to classify fiction prose by words such as "statement", "report", "message", or their Chinese equivalents.

## Real Corpus Validation

Use the ignored local source sample:

```text
.sextant/imports/凡人修仙传_第一卷_风起天南_前30章.txt
```

Validation must be chapter/slice based. The corpus must not be committed, copied into fixtures, or pasted into docs beyond short references needed to locate local validation inputs.

The corpus validation should prove:

- source import and slicing preserve stable spans;
- candidates cite source spans precisely;
- unsupported memory/canon writes are rejected;
- negative slices do not create facts or character knowledge merely because wording resembles a cue;
- accepted candidates preserve the evidence path from source to review/writeback/canon.

## LLM Validation and Judge Strategy

Provider output is not stable enough to be tested as exact text. Real LLM validation should therefore separate candidate generation from acceptance judgment.

The proposed validation shape is:

1. A configured provider call proposes structured candidates for fixed corpus slices.
2. Deterministic checks validate schema, source span IDs, evidence ancestry, no direct memory/canon writes, and required review gates.
3. A Codex subagent acts as an eval-only LLM judge for semantic fitness against the same bounded source evidence.
4. The judge uses a fixed eval rubric and returns structured pass/fail findings, not free-form acceptance.
5. The test/eval accepts variability in wording but rejects unsupported claims, over-inference, source-boundary drift, and missing evidence.

The Codex subagent judge is an evaluation tool, not production authority. Production authority remains the deterministic evidence/review/canon gate.

## Current Known Missing Work

The cleanup should leave these as explicit remaining work, not completed claims:

- gbrain-style sliding-window automatic source/context organization is not implemented;
- RRF fusion of keyword and embedding retrieval is not implemented;
- full real-corpus chapter/slice validation is not implemented;
- real provider end-to-end validation with Codex subagent judge eval review (not production authority) is not implemented;
- hosted environment proof and deployed smoke acceptance are not implemented;
- deployed clean-context UI acceptance is not implemented.

## Meaningful Work to Keep

The following work remains meaningful if it is not dependent on the deleted prose parser:

- production persistence/API/worker/review/evidence-chain skeleton;
- provider boundary and structured provider configuration;
- local key-backed provider probes as provider smoke evidence only;
- source import and SourceSpan mechanics;
- review queue and memory/canon gate mechanics;
- graph projection as read-side projection only;
- frontend walkthrough evidence when backed by real API/workers;
- source coverage and acceptance-matrix tracking after incorrect completion claims are removed.

## Documentation Cleanup

The implementation pass should update documentation so future agents do not inherit the wrong direction.

Required doc changes:

- remove progress-log entries that describe local prose cue rules as completed semantic coverage;
- remove known-gaps language that implies word-list expansion is the next correct solution;
- update implementation decisions to record the deletion decision and the replacement architecture;
- update goal/plan docs only after the code and tests are actually cleaned, so docs describe the lower, cleaner codebase state;
- clearly separate completed infrastructure from remaining semantic validation work.

## Test Cleanup and Verification

The first implementation pass should be deletion-first:

1. Delete invalid prose-inference tests.
2. Add or keep negative tests proving ordinary prose does not create memory, canon, facts, review items, or graph facts without approved candidate/review flow.
3. Run focused backend tests for preserved source import, source span, evidence log, review, memory, graph, and API behavior.
4. Run source coverage checks and diff hygiene.
5. Run broader verification only after the cleanup compiles and focused tests pass.

No final production completion claim is allowed until hosted readiness, deployed smoke, and clean-context UI acceptance pass.

## Open Implementation Questions

These questions should be answered during the cleanup planning phase, before code edits:

- Which source-pipeline functions are pure infrastructure and which are prose-inference behavior?
- Which integration tests should be deleted versus rewritten as negative boundary tests?
- Which docs currently contain misleading completion claims tied to the deleted behavior?
- What minimum fixed corpus slices should seed the real-corpus validation harness without committing corpus text?
- What structured eval rubric (not production authority) should the Codex subagent judge use for candidate validation?

## Acceptance for This Cleanup

The cleanup is acceptable when:

- local prose word-list inference no longer writes or proposes memory, canon, facts, events, relations, or review items;
- tests no longer depend on self-invented prose samples to prove semantic understanding;
- docs no longer recommend expanding natural-language cue tables as the architecture;
- preserved infrastructure tests still pass;
- new negative tests prove deleted behavior stays deleted;
- remaining work clearly lists real corpus validation, provider E2E, Codex subagent judge eval review (not production authority), sliding-window organization, RRF retrieval fusion, hosted proof, and deployed acceptance.
