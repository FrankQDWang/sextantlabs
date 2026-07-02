# PLAN: Sextant Complete Production Implementation

This file is the execution plan for implementing the full Sextant system described by the repository documentation.

It is intentionally not a reduced demo plan. It must not be used to narrow the work to a local-only slice, a visual prototype, or a mock-only flow. The implementation target is code, tests, and documentation that align with the complete product and engineering contracts in this repository.

## 1. Objective

Build Sextant as a production-ready writing memory and agent system for fiction authors.

The completed system must support the full evidence-preserving path:

```text
source material
  -> normalized source views
  -> SourceDelta
  -> SourceSpan
  -> EvidenceLogEntry
  -> Memory writeback
  -> ReviewItem / CanonPromotion
  -> MemoryPage
  -> GraphProjection
  -> WritingContextPack
  -> Story Skill / Agent candidate
  -> author acceptance
  -> new SourceDelta
```

The web workbench remains the user-facing surface, but the implementation is not limited to frontend state. The system must include the domain model, persistence, backend API, worker pipeline, provider interfaces, review and audit behavior, verification, and production readiness gates described in `goals/`, `experience/`, and `implementation/`.

## 2. Scope Authority

Source-of-truth order:

1. `GOAL.md`
2. `AGENT_GOAL.md`
3. `goals/*.md`
4. `experience/*.md`
5. `implementation/*.md`
6. `AGENTS.md`
7. this file
8. `docs/*.md`
9. implementation code

Rules:

- Do not use this file, or any older reduced-scope language, to reduce scope.
- Do not silently omit, merge away, or simplify requirements from source documents.
- If two source documents conflict, stop and record the conflict in `docs/implementation-decisions.md` with exact file references.
- Only the LLM/provider boundary may use a deterministic local substitute for development, tests, and evals.
- No other subsystem may be mocked or faked for completion: persistence, API, worker jobs, review, graph projection, auth, observability, and deployment gates must use real implementations in verification.
- If a non-LLM external dependency cannot be completed locally because credentials, hosted infrastructure, or third-party access is missing, implement the production interface and validation path, record the exact blocker, and leave the feature incomplete. Do not replace it with a local mock or adapter and mark it complete.

## 3. Required Source Coverage

Before coding, the implementing agent must enumerate every Markdown source file and create a source coverage section in `docs/progress-log.md`.

Coverage records must state, for each source file:

- concrete implementation obligations;
- code paths or tests that satisfy those obligations;
- deferred items, only when blocked by external evidence or explicitly out of product scope;
- corresponding entries in `docs/known-gaps.md` or `docs/implementation-decisions.md` when applicable.

Current baseline source files that must be covered:

```text
GOAL.md
AGENT_GOAL.md
AGENTS.md
README.md
PLAN.md
docs/goal-readiness-review.md
docs/implementation-decisions.md
docs/known-gaps.md
docs/progress-log.md
experience/00-product-principles.md
experience/01-writing-session-loop.md
experience/02-action-request-contract.md
experience/03-candidate-lifecycle.md
experience/04-memory-writeback-contract.md
experience/05-review-and-risk-contract.md
experience/06-conversational-entry-contract.md
experience/README.md
goals/00-design-principles.md
goals/01-data-flow.md
goals/02-core-data-structures.md
goals/03-source-evidence.md
goals/04-scenes-pov.md
goals/05-mentions-aliases.md
goals/06-entities-events-facts.md
goals/07-memory-pages.md
goals/08-graph-projection.md
goals/09-retrieval-context-pack.md
goals/10-continuity-check.md
goals/11-non-goals.md
goals/12-inspirations.md
goals/13-skills-and-resolver.md
goals/14-story-schema-packs.md
goals/15-event-aggregation.md
goals/16-source-normalization.md
goals/17-incremental-memory-writeback.md
goals/18-conflict-policy.md
goals/19-story-auto-link.md
goals/20-agent-overview.md
goals/21-writing-context-pack.md
goals/22-character-agency-profile.md
goals/23-next-page-agent.md
goals/24-draft-candidate-lifecycle.md
goals/25-agent-memory-writeback.md
goals/26-agent-review-policy.md
goals/27-storytelling-control-layer.md
goals/28-role-need-and-cast-expansion.md
goals/29-new-character-policy.md
goals/30-dramatization-layer.md
goals/31-inner-state-rendering.md
goals/32-scene-sequel-mode.md
goals/33-prose-rendering-contract.md
implementation/00-overview.md
implementation/01-source-of-truth-map.md
implementation/02-module-boundaries.md
implementation/03-persistence-schema.md
implementation/04-domain-state-machines.md
implementation/05-application-use-cases.md
implementation/06-story-skills-and-llm-harness.md
implementation/07-agent-and-storytelling-control.md
implementation/08-api-contracts.md
implementation/09-frontend-integration.md
implementation/10-worker-and-jobs.md
implementation/11-ci-cd-and-ai-guardrails.md
implementation/12-observability-security-ops.md
implementation/13-acceptance-matrix.md
implementation/14-implementation-pr-stack.md
implementation/README.md
web/README.md
```

If additional Markdown files exist when the goal starts, include them too.

## 4. Non-Negotiable Product Boundaries

The implementation must preserve these boundaries:

- The author remains in control. The agent proposes; the author accepts.
- `DraftCandidate` is not manuscript text.
- `DraftCandidate` cannot become memory or canon before author acceptance.
- Accepted text must create a `SourceDelta`.
- Memory evidence must trace through `SourceSpan`.
- Risk and disputed information cannot be promoted to canon without the conflict policy and review path.
- `AgentReviewFinding` and `ReviewItem` are different objects.
- `GraphProjection` is rebuildable and cannot write canonical facts.
- Storytelling control objects guide generation; they do not create memory before accepted text exists.
- POV, known/unknown information, role needs, new character policy, and prose rendering constraints must be enforceable.

Forbidden shortcuts:

```text
single chat endpoint writes text and memory
candidate accepted directly into canon
frontend-only memory state
review item without source span
graph projection as fact source
provider output treated as truth
hardcoded UI state pretending to be domain behavior
placeholder feature marked complete
```

## 5. Required System Areas

### 5.1 Domain Model

Implement the production domain objects and state machines described in `goals/`, `experience/`, and `implementation/`, including at least:

- project, source, raw source, source version, normalized source view;
- source delta and source span;
- entity, mention, alias, event, fact assertion, evidence log entry;
- memory page, proposed memory, canon promotion, conflict policy;
- graph projection and rebuild state;
- action request, writing context pack, draft candidate, accepted fragment;
- story skill request/result, role slot, role need, casting decision, new character seed;
- scene/sequel mode, dramatic behavior plan, prose rendering contract;
- agent review finding and review item.

State transitions must be explicit and tested. Invalid transitions must fail deterministically.

### 5.2 Persistence

Implement production persistence according to `implementation/03-persistence-schema.md`.

Requirements:

- relational schema with migrations;
- enum and check constraints for lifecycle objects;
- source span range validation;
- uniqueness rules for current processed source views;
- idempotency keys for write operations;
- backup and rollback notes before production migration;
- no direct bypass around canon promotion or review gates.

Local development may use a local database. It must not replace production persistence with `localStorage` as the final product behavior.

### 5.3 Backend API

Implement backend application use cases and API contracts from `implementation/05-application-use-cases.md` and `implementation/08-api-contracts.md`.

Requirements:

- typed request/response contracts;
- deterministic error mapping;
- generated or verifiable OpenAPI contract;
- idempotent write endpoints;
- route layer separated from domain and infra adapters;
- frontend client kept in sync with the API contract.

### 5.4 Worker Pipeline

Implement the background pipeline from `implementation/10-worker-and-jobs.md`.

Requirements:

- source normalization jobs;
- extraction and memory writeback jobs;
- conflict policy evaluation;
- graph projection rebuilds;
- retry and idempotency behavior;
- observable job state and failure handling.

### 5.5 Provider and Story Skill Harness

Implement provider interfaces and the Story Skill / resolver harness from `goals/13-*`, `goals/20-*`, and `implementation/06-*`.

Requirements:

- production provider abstraction;
- LLM-only deterministic local adapter for development, tests, and evals;
- prompt/input contracts with golden cases;
- provider output validation;
- no direct promotion of provider claims to memory or canon.

### 5.6 Agent and Storytelling Control

Implement the agent behavior described in `AGENT_GOAL.md` and `goals/20-33`.

Requirements:

- context pack sections for canon, risk, POV, style, role needs, and open threads;
- candidate lifecycle with stale base protection;
- role need and casting decision control objects;
- new character policy checks;
- dramatization and inner-state constraints;
- scene/sequel mode;
- prose rendering contract;
- review findings for violations.

### 5.7 Frontend Workbench

Preserve the current `web/` visual direction while making it a real production client.

Requirements:

- do not redesign the UI unless required by a documented contract;
- editor creates structured `ActionRequest` from selected text or conversational entry;
- candidate drawer renders real candidate lifecycle data;
- partial accept sends base hash and target range;
- accepted text creates the backend/domain evidence chain;
- memory writeback preview and review queue reflect persisted backend state;
- high-risk candidate paths require explicit user action;
- unfinished or lower-priority placeholders must be removed, disabled, or implemented.

### 5.8 Security, Observability, and Operations

Implement the production gates from `implementation/11-ci-cd-and-ai-guardrails.md` and `implementation/12-observability-security-ops.md`.

Requirements:

- CI checks for lint, type, test, migrations, API drift, and architecture boundaries;
- security checks for direct canon writes, illegal imports, and secret handling;
- audit logs for sensitive state changes;
- structured logs, metrics, and traces for core flows;
- deployment, migration, smoke test, and rollback documentation.

## Pre-Implementation Correction Gates

### Target Documentation Correction

Before any further code cleanup or feature implementation, update the target documentation to remove the invalid local prose cue/regex semantic direction.

This historical gate was docs-only. It originally required the docs to:

- state that prompt registry is not Skill Registry;
- state that the then-current thin-harness + rich-skills architecture was incomplete until first-class runtime and resolver work landed;
- state that local prose cue/regex inference must be deleted, not expanded;
- preserve useful infrastructure as meaningful work;
- list missing work truthfully. As of 2026-07-01 the repository already includes SkillRegistry, `run_skill(...)`, Resolver, skill document registry, Codex subagent judge eval rubric (not production authority), real-corpus chapter/slice boundary eval, RRF fusion, and sliding-window organization; remaining blocked work is hosted proof, deployed smoke, clean-context UI acceptance, and other externally evidenced hosted release gates.

### Source Pipeline Semantic Cleanup

This gate was executed after the target documentation correction. The current
source pipeline no longer keeps local prose cue/regex inference paths that
create or propose character knowledge, facts, events, relations, review items,
memory writeback, canon promotion, graph facts, or POV/scene semantic
conclusions. The old tests that proved those local prose rules through invented
examples were deleted or rewritten as boundary tests.

Future work must preserve this boundary and route creative semantic
understanding through Story Skills/provider candidates plus deterministic
schema, evidence, review, and canon validation.

## 6. Checkpoints

Checkpoints are for auditability, not scope reduction. Do not stop at a partial product and call it complete.

1. Source coverage and architecture reconciliation.
2. Domain model and persistence.
3. Backend use cases and API contracts.
4. Worker pipeline and graph projection.
5. Provider harness, story skills, and agent controls.
6. Frontend production integration while preserving visual direction.
7. Security, observability, CI, and operational gates.
8. Full automated and clean-context human acceptance.

After each checkpoint, update:

- `docs/progress-log.md`;
- `docs/known-gaps.md`;
- `docs/implementation-decisions.md` when decisions or conflicts arise.

## 7. Verification

The final implementation must pass every applicable acceptance criterion in `implementation/13-acceptance-matrix.md`.

At minimum, final verification must include:

```bash
git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
pnpm --dir web test
pnpm --dir web test:e2e
```

The implementation must also add and document backend, migration, worker, API, security, and production smoke commands. Those commands must pass before completion.

Required acceptance evidence:

- source coverage table completed;
- domain transition tests;
- persistence migration tests;
- API contract tests;
- worker/job tests;
- provider harness golden tests;
- frontend integration tests;
- end-to-end production smoke;
- security and architecture boundary checks;
- clean-context UI acceptance report.

## 8. Clean-Context Human Acceptance

After automated verification passes, run a final acceptance pass with a separate clean-context reviewer using only the running UI through browser/computer-use.

That reviewer must not inspect source code or docs. They must behave like a real user and verify the user-facing workflow, including:

- project/source creation or loading;
- source normalization visibility;
- selecting manuscript text;
- requesting candidates;
- reviewing evidence, risk, and avoided claims;
- accepting partial text;
- seeing source delta and source span evidence;
- reviewing memory writeback preview;
- routing low-risk and risky items correctly;
- observing review queue behavior;
- refreshing/reopening and confirming persistence;
- validating that no placeholder feature pretends to be complete.

The reviewer must report exact pass/fail evidence.

## 9. Stop Conditions

Stop only when one of these is true:

- the complete production system is implemented, verified, documented, and accepted;
- an external blocker prevents completion, and the blocker includes exact evidence, attempted paths, affected source requirements, and the concrete input or infrastructure needed to continue.

Do not stop because a local-only path works. Do not stop because a visual flow appears complete. Do not stop because a subset of source documents has been implemented.

## GSTACK REVIEW REPORT

Stage: `fw-plan-review`
Date: 2026-05-31
Status: needs user confirmation before `fw-build`

Engineering gate result:

- Scope reduction is rejected. The plan intentionally targets complete production implementation.
- The plan must enumerate and cover every source Markdown file before coding.
- The plan now includes the hard mock boundary: only the LLM/provider boundary may use deterministic local output.
- Persistence, API, worker jobs, review, graph projection, auth, observability, deployment gates, and clean-context acceptance must use real implementations.
- If non-LLM credentials, hosted infrastructure, or third-party access are unavailable, the affected feature remains blocked. A local mock or adapter must not be used to mark it complete.

Design gate result:

- UI scope exists because the web workbench remains the production client.
- No redesign is approved by this plan review.
- Implementation must preserve the current workbench visual direction and verify the running UI through clean-context browser/computer-use acceptance.

Open decision before build:

- User must explicitly confirm moving from this reviewed plan into `fw-build`.
