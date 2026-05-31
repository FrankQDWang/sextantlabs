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
```

Tests:

```text
domain state transition tests
application AcceptCandidate tests
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
```

## Agent Acceptance

### WritingContextPack

Must prove:

```text
canon/risk/POV/style sections are separated
risk context cannot be used as fact without finding
```

Tests:

```text
contract test for disputed fact in risk section
agent review flags proposed fact as canon
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
