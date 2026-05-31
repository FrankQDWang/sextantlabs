# 14. Implementation PR Stack

This document defines a safe PR stack for full production implementation. It is not a sprint commitment. Each PR should be reviewable and testable on its own.

## Stack Shape

```text
base tooling
  -> domain contracts
    -> persistence
      -> repositories and ports
        -> application use cases
          -> story skills and harness
            -> API contracts
              -> frontend integration
                -> worker pipeline
                  -> observability/security
                    -> production release gate
```

## PR 1: Backend Tooling Skeleton

Deliver:

```text
backend/pyproject.toml
backend/src/sextant package skeleton
ruff
ty
tach
pytest
basic CI
```

Acceptance:

```text
ruff, ty, tach, pytest pass
illegal import fixture fails tach
```

## PR 2: Domain Core Contracts

Deliver:

```text
SourceDelta
RawSource
SourceVersion
ProcessedMarkdownView
SourceSpan
ActionRequest
DraftCandidate
AcceptedFragment
ReviewItem
AgentReviewFinding
```

Acceptance:

```text
state transition tests
SourceSpan range validation
candidate cannot convert without accepted text
```

## PR 3: Story Schema and Memory Domain

Deliver:

```text
Mention
AliasRecord
CanonicalEntity
EventCandidate
CanonicalEvent
FactAssertion
EvidenceLogEntry
CharacterKnowledge
MemoryPage
GraphProjection
Story Schema Pack value objects
```

Acceptance:

```text
enum whitelist tests
fact promotion guard tests
graph projection not source-of-truth test
```

## PR 4: Persistence and Migrations

Deliver:

```text
SQLAlchemy models
Alembic migrations
repository ports and infra implementations
object store refs
```

Acceptance:

```text
alembic upgrade
repository contract tests
current view unique index test
```

## PR 5: Application Use Cases

Deliver:

```text
SubmitActionRequest
AcceptCandidate
CreateSourceDelta
RunMemoryWriteback shell
ResolveReviewItem
AnswerWithEvidence shell
```

Acceptance:

```text
idempotency tests
stale base tests
review resolution tests
```

## PR 6: Skill Harness and Golden Test Framework

Deliver:

```text
skill registry
skill run record
prompt metadata format
structured output validation
golden fixture runner
```

Acceptance:

```text
invalid LLM output cannot apply
prompt change without golden update fails
skill cannot import infra directly
```

## PR 7: Memory Extraction Skills

Deliver:

```text
source-normalization
split-structure
extract-mentions
resolve-alias
extract-events
aggregate-events
derive-facts
check-continuity
```

Acceptance:

```text
golden tests for each skill
SourceDelta -> ReviewItem integration
low risk promotion test
```

## PR 8: Agent and Storytelling Control

Deliver:

```text
WritingContextPack
CharacterAgencyPass
RoleSlot
CharacterCastingDecision
NewCharacterSeed
SceneSequelMode
DramaticBehaviorPlan
ProseRenderingContract
NextPageAgent
AgentReview
```

Acceptance:

```text
candidate generation never writes Memory
ProseRenderingContract hard_no creates finding
NewCharacterSeed accepted path goes through SourceDelta
```

## PR 9: API and OpenAPI

Deliver:

```text
FastAPI app
OpenAPI generation
ActionRequest endpoints
Candidate endpoints
Memory answer endpoints
Review endpoints
Job status endpoints
```

Acceptance:

```text
API contract tests
generated client check
idempotency headers
```

## PR 10: Frontend Workbench Integration

Deliver:

```text
generated client usage
editor target/base hash plumbing
candidate drawer
memory answer panel
writeback preview
review panel
ask/command palette
```

Acceptance:

```text
Playwright writing loop
partial accept
stale base handling
high-risk override flow
```

## PR 11: Worker Pipeline

Deliver:

```text
job_records
worker lease/retry
memory writeback pipeline
graph projection rebuild
skill replay jobs
```

Acceptance:

```text
worker lease timeout test
duplicate job idempotency test
terminal failure audit test
```

## PR 12: Observability and Security

Deliver:

```text
audit events
structured logging
metrics
secret scanning
object store access boundaries
cross-project auth checks
```

Acceptance:

```text
logs do not contain full manuscript
audit explains canon promotion
cross-project refs rejected
```

## PR 13: CI/CD and Release Gate

Deliver:

```text
full GitHub Actions gates
migration checks
golden/replay checks
Playwright path gate
staging smoke script
PR template
CODEOWNERS
```

Acceptance:

```text
all gates pass
staging smoke passes
release checklist documented
```

## Stack Rules

1. Each PR must be independently reviewable.
2. Each PR must reference source docs from `goals/`, `experience/`, and `implementation/`.
3. Do not batch unrelated layers.
4. Do not build frontend against hand-written fake backend schema after OpenAPI exists.
5. Do not add live provider dependency to quick CI.
6. Do not merge a PR that weakens guardrails to pass tests.

## When to Add ADR

Create `docs/adr/*.md` if a PR changes:

```text
database-as-source-of-truth decision
modular monolith decision
LLM provider abstraction
worker architecture
canon promotion policy
review enum whitelist
deployment topology
```

ADR records a decision; it does not replace `implementation/` specs.
