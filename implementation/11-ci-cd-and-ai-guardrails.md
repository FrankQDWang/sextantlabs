# 11. CI/CD and AI Guardrails

CI/CD protects source-of-truth boundaries, not just formatting. AI-generated code is expected, so guardrails must be executable.

## PR Quick Gate

Backend:

```text
uv sync --locked
ruff format --check
ruff check
ty check
tach check
pytest backend/tests/unit backend/tests/contract
```

Frontend:

```text
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm build
pnpm vitest
```

Repo:

```text
check generated OpenAPI client is up to date
check no forbidden files
check no oversized prompt dumps
check no direct mutation of protected generated files
check implementation source map references valid docs
```

## Slow Gate

Triggered by path or label:

```text
Postgres integration tests
worker pipeline tests
LLM replay tests
golden tests
Playwright user journeys
Alembic migration upgrade tests
GraphProjection rebuild tests
```

## Security Gate

```text
semgrep
secret scanning
dependency review
CodeQL optional
Docker image scan optional
```

GitHub Actions default permissions must be read-only unless the job needs writes.

## Semgrep Rules

Must block:

```text
api layer imports provider SDK
api layer commits SQLAlchemy session
domain imports FastAPI, SQLAlchemy, Redis, provider SDK
skills imports infra.db or concrete provider SDK
skills sets MemoryPage.current_canon
code sets FactAssertion.fact_status = 'canon' outside promotion service
code creates ReviewItem outside review policy/factory
code maps model_suggestion to user_draft/user_published without author accept
code builds FactAssertion from GraphProjection
code writes full manuscript text to normal logs
```

## tach Rules

Minimum:

```text
domain cannot import api/infra/skills
skills cannot import infra
api cannot import infra.db or infra.llm
application cannot import concrete provider SDK
contracts cannot import repositories
```

## Protected Generated Files

Protected:

```text
web/src/generated/**
backend/src/sextant/contracts/openapi.json
```

Manual edits fail CI. Updates must run generator command.

## Prompt Guardrails

Prompt PR must include:

1. prompt version bump,
2. input/output schema version check,
3. golden expected output update,
4. failure case if changing risk or promotion behavior,
5. no raw full manuscript dumps in repo.

## PR Template Required Questions

Every PR body must answer:

```text
Does this modify source-of-truth objects?
Does this modify ActionRequest / Candidate / SourceDelta / SourceSpan / ReviewItem contract?
Does this modify AgentReviewFinding or ReviewItem enum values?
Does this add or change migrations?
Does this add or change prompts?
Does this add or update golden cases?
Does this touch Memory promotion or Conflict Policy Gate?
Does this touch Storytelling Control or ProseRenderingContract?
Does this need an ADR?
Which goals/experience/implementation docs does this implement?
```

## CODEOWNERS

Suggested ownership:

```text
/goals/                         product-domain-owner
/experience/                    product-domain-owner
/implementation/                engineering-owner product-domain-owner
/backend/src/sextant/domain/    engineering-owner product-domain-owner
/backend/src/sextant/skills/    engineering-owner product-domain-owner
/prompts/                       engineering-owner product-domain-owner
/backend/alembic/               engineering-owner
/.github/workflows/             engineering-owner
```

## AI Coding Rules

AI may:

```text
add domain model matching documented contract
add repository implementation matching port
add migration matching schema document
add API endpoint shell from OpenAPI contract
add skill skeleton with schema and golden case
fix lint/type/import boundary issues
```

AI may not:

```text
change source-of-truth order
invent new review_type or risk_type
let candidate auto-enter Memory
let model output become canon
delete evidence chain
make GraphProjection source-of-truth
change prompt output schema to free text
rewrite goals/ or implementation/ as part of coding without explicit design task
```

## Release Gate

Staging:

```text
main merge
build backend image
build worker image
build static web
run migration upgrade
run smoke tests
deploy staging
record deployment
```

Production:

```text
release tag
environment approval
backup confirmation
migration dry-run or staging-proven migration
deploy
smoke test
rollback note ready
```

## Acceptance

CI/guardrail work is complete when:

1. An intentionally illegal import fails `tach check`.
2. An intentionally direct canon write fails semgrep or unit test.
3. Generated client stale check fails when OpenAPI changes without generation.
4. Prompt change without golden update fails CI.
5. PR template contains source-doc mapping questions.
