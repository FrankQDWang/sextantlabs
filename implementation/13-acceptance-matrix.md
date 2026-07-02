# 13. Acceptance Matrix

This document defines what "complete enough for production implementation" means. It is not a task plan; it is the matrix future PRs are judged against.

## Global Definition of Done

Every implementation PR must satisfy:

1. Source docs identified.
2. Domain boundary preserved.
3. Tests added at the right level.
4. CI commands documented and passing.
5. No undocumented enum or schema change.
6. No source-of-truth shortcut.
7. Audit/logging behavior acceptable.

## Core Flow Acceptance

### ActionRequest

Must prove:

```text
natural language / selected text / toolbar action
  -> structured ActionRequest
```

Tests:

```text
contract test for each trigger
missing target rejects writing action
actor_intent is not fact
```

### Candidate Lifecycle

Must prove:

```text
DraftCandidate cannot enter Memory before author accept
blocked candidate needs override
stale base cannot create replace SourceDelta
rejected candidate archives without SourceDelta, review, memory, canon, or graph side effects
```

Tests:

```text
domain state transition tests
application AcceptCandidate tests
candidate reject API side-effect test
frontend stale-base Playwright test
```

### SourceDelta and SourceSpan

Must prove:

```text
SourceDelta creates SourceVersion
ProcessedMarkdownView preserves raw offset map
SourceSpan maps to RawSource
```

Tests:

```text
unit range validation
integration source normalization
restore smoke SourceSpan -> RawSource
public API liveness endpoint returns sanitized deployment metadata without auth or secret/config leakage
hosted PostgreSQL readiness probe verifies managed instance shape, Alembic head, and evidence-chain row counts without local database substitutes
hosted external smoke creates source through deployed API and verifies SourceSpan-backed writeback evidence
hosted worker capacity probe verifies successful worker metrics and bounded queue age without local worker substitutes
hosted object-store IAM probe verifies external IAM/policy attachment evidence and emits sanitized hash/count evidence without local IAM substitutes
hosted object-store probe writes and reads through production S3 adapter and emits sanitized hash evidence without local object-store substitutes
hosted secret-manager probe reads through production AWS/GCP/Vault secret resolver and emits redacted evidence without local secret substitutes
hosted SourceDelta reindex probe runs production reindex path against hosted PostgreSQL/S3 and emits sanitized evidence without local substitutes
hosted pgvector recall probe verifies hosted vector extension/index/vector rows and self-nearest semantic recall without local database substitutes
hosted provider live eval probe exercises production OpenAI StoryDraft, Memory Extraction, POV Detection, Event Aggregation, and Embedding providers without deterministic local provider substitutes
hosted observability pipeline probe fetches hosted metrics/traces/alert surfaces and emits sanitized evidence without local observability substitutes
hosted deployment approval probe fetches hosted approval/change-control evidence and emits sanitized proof without local approval substitutes
hosted clean-context acceptance probe fetches hosted browser/computer-use walkthrough evidence and emits sanitized proof without local acceptance substitutes
hosted backup/restore probe runs pg_dump, S3 backup-target upload/download, scratch restore, and restored evidence-chain counts without local database substitutes
hosted rollback drill probe executes deployment rollback tooling and verifies the hosted status URL reaches the target version without local proof substitutes
```

### Memory Writeback

Must prove:

```text
SourceDelta -> EvidenceLogEntry -> ConflictPolicyGate -> CanonPromotion or ReviewItem
```

Tests:

```text
low risk promotes
medium risk creates ReviewItem
high risk blocks promotion only
author rejects extraction stores correction signal
```

### MemoryPage Author Operations

Must prove:

```text
author can operate an existing SourceSpan-backed open thread
operation updates only the MemoryPage thread state
operation records audit and idempotency
operation marks dependent ContextPack readiness stale
operation cannot write SourceDelta, FactAssertion, ReviewItem, CanonPromotion, GraphProjection, provider output, or worker jobs
```

Tests:

```text
API side-effect matrix for MemoryPage open-thread operation
idempotency conflict/replay matrix for the route
invalid thread without SourceSpan evidence rejects without side effects
workbench MemoryPage panel operates a real backend thread and reflects the returned detail
```

### Review

Must prove:

```text
AgentReviewFinding != ReviewItem
ReviewItem lifecycle follows whitelist
resolution side effects mark MemoryPage/GraphProjection stale
```

Tests:

```text
agent finding cannot be formal review pre-acceptance
review resolve/dismiss/reopen/supersede state tests
source_scope_conflict reject marks model-suggestion fact contradicted and rebuilds graph
later author-backed duplicate promotes over review-required lower-authority
same-fact review without merging lower-authority evidence into canon
```

### GraphProjection

Must prove:

```text
GraphProjection is rebuildable
GraphProjection cannot write FactAssertion
```

Tests:

```text
delete projection and rebuild
semgrep or unit guard for graph-to-fact write
read-only graph edge API returns evidence refs and cannot write facts
workbench memory panel inspects graph edges through the generated client
```

### Project Story Schema

Must prove:

```text
project override is versioned and idempotent
system admin can provision and deprecate unused global Genre Packs
non-admin actors cannot provision or deprecate global Genre Packs
in-use Genre Packs cannot be deprecated
genre pack selection is idempotent and preserves project overrides
effective schema validation runs before persistence
schema writes cannot create evidence, memory, canon, review, graph, or provider side effects
browser UI can save project override through generated API client
browser UI can select an active backend Genre Pack through generated API client
browser UI can read project invitations and record invitation intent/proof refs through generated API client without claiming hosted delivery/token execution
```

Tests:

```text
project story schema API validates/version/replays writes
project story schema API admin-provisions/deprecates Genre Packs
project story schema API lists/selects/clears active Genre Packs
CORS preflight allows PUT schema writes
workbench project panel saves Project Override JSON through generated client
workbench project panel selects Genre Pack through generated client
workbench project panel lists ProjectInvitation rows and records intent/proof refs through generated client
```

## Documentation and Skill Architecture Correction

| Acceptance target | Requirement | Verification |
|---|---|---|
| target documentation correction | GOAL/AGENT_GOAL/goals/implementation/PLAN/README docs explicitly reject local prose cue/regex semantic inference and distinguish prompt registry from SkillRegistry | `rg` verification plus doc diff review |
| real SkillRegistry target | target docs require first-class SkillRegistry, Resolver, `run_skill(...)`, executable skill document registry, deterministic validators, and rich-skill/provider candidate generation | doc review plus runtime verification in `backend/src/sextant/ports/story_skills.py`, compatibility export in `backend/src/sextant/infra/story_skill_registry.py`, production use in `backend/src/sextant/infra/{memory_writeback.py,source_pipeline.py}`, skill-plan audit in `backend/src/sextant/application/use_cases.py`, and `backend/tests/integration/test_story_skill_runtime.py` |
| skill semantic eval target | target docs require fixed source slices, real provider candidate generation, deterministic invariants, and Codex subagent judge eval rubric (not production authority) instead of exact-output LLM assertions | doc review plus `backend/scripts/real_corpus_memory_boundary_eval.py`, `backend/src/sextant/infra/real_corpus_skill_eval.py`, `evals/datasets/real_corpus_memory_boundary/{fanren-chapter-slices.v1.json,codex-subagent-judge-rubric.v1.json}`, and `backend/tests/integration/test_real_corpus_skill_eval.py` |

## Agent Acceptance

### WritingContextPack

Must prove:

```text
canon/risk/POV/style sections are separated
risk context cannot be used as fact without finding
token budget truncation keeps highest-relevance/risk context and only changes the snapshot
```

Tests:

```text
contract test for disputed fact in risk section
agent review flags proposed fact as canon
context pack budget integration/API contract tests
```

### Storytelling Control

Must prove:

```text
RoleSlot and casting decisions are control objects only
NewCharacterSeed does not create Memory until accepted text enters SourceDelta
SceneSequelMode and DramaticBehaviorPlan feed ProseRenderingContract
```

Tests:

```text
new character seed not in CanonicalEntity before accept
non-POV mind reading creates finding
no-turn prose creates finding
scene without goal/opposition creates scene_mode_risk
mixed without action/reaction/decision creates mode_mixing_risk
sequel without dilemma/decision creates sequel_mode_risk
direct thought disallowed by DramaticBehaviorPlan creates telling_over_action
paragraph with repeated direct inner state creates inner_state_overload
required dramatic choice without visible choice creates choice_missing
show-not-tell target without scene behavior creates exposition_risk
subtext target with explanatory dialogue creates subtext_missing
dramatic rendering target without visible behavior creates dramatization_risk
major story overreach creates control_risk
```

### ProseRenderingContract

Must prove:

```text
hard_no constraints are enforceable
target_position protects editor range
new_character_policy is checked
```

Tests:

```text
contract hard_no violation -> high risk
target range violation -> target_range_risk
new major character without confirmation -> cast_creation_risk
```

## Persistence Acceptance

Must prove:

1. Alembic upgrade works from empty DB.
2. Current ProcessedMarkdownView uniqueness enforced.
3. SourceSpan range checks enforced.
4. ReviewItem and AgentReviewFinding enum checks enforced.
5. Fact canon promotion path cannot be bypassed.

## API Acceptance

Must prove:

1. OpenAPI generated.
2. Frontend client generated.
3. Each write endpoint has idempotency behavior.
4. Error code mapping is deterministic.
5. API routes do not import infra adapters.

## Frontend Acceptance

Must prove:

1. Editor can create ActionRequest from selected text.
2. Candidate accept sends base_hash and target range.
3. Partial accept works.
4. High-risk candidate requires explicit override.
5. ReviewItem and AgentReviewFinding are not conflated.

## CI Acceptance

Must prove:

1. `tach check` catches illegal imports.
2. `semgrep` catches at least one direct canon write pattern.
3. Prompt/golden drift fails.
4. Generated OpenAPI client drift fails.
5. Migration upgrade runs.
6. Hosted session-provider, session-provider provisioning,
   invitation-delivery, and token-issuer readiness probes verify JWKS/admin
   surfaces plus provisioning, delivery, and issuance proof artifacts without
   mock auth, fake provider provisioning, fake invitation delivery, or fake
   token issuance.
7. Project invitation provider refs and external delivery/token proof refs
   reject URL userinfo, params, query strings, and fragments before DB, audit,
   idempotency, or API read models can persist credential-bearing refs.
8. Hosted readiness proof refs, runbook refs, and invitation delivery provider
   refs reject URL userinfo, params, query strings, and fragments even in
   blocker-recording mode, without echoing embedded secret material.
9. Hosted proof artifact URLs reject URL userinfo, params, query strings, and
   fragments, and private artifact access uses bearer/provider configuration
   instead of signed URLs.
10. Direct hosted proof-probe configuration rejects credential-bearing proof
    refs before fetching artifacts or emitting sanitized proof output.

## Production Smoke Acceptance

A release candidate must pass:

```text
create project
import source
normalize source
extract span
ask evidence-backed question
generate candidate
review candidate
accept partial text
create source delta
run memory writeback
observe low-risk memory or review item
rebuild graph projection
```

## Non-Acceptance Examples

Not acceptable:

```text
single endpoint "chat" that writes text and memory
model output directly updates MemoryPage.current_canon
frontend stores its own FactAssertion type
review item without source span
GraphProjection used as fact source
prompt change without golden case
green build with tach disabled
```
