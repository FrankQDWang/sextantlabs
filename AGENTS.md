# AGENTS.md

This file is the operating manual for Codex / AI coding agents working in this repository. It defines how to read context, implement the system, verify work, and stop.

It does not replace the product and engineering source documents. Repository files are the source of truth.

## 1. Current Repository State

Sextant is moving from design documents and a web workbench prototype toward complete production implementation.

The repository now contains:

- `goals/`: Memory, Agent, and Storytelling Control domain design.
- `experience/`: product experience contracts for writing sessions, candidates, memory writeback, review, and conversational entry.
- `implementation/`: production engineering specifications.
- `web/`: Vite + React writing workbench prototype that must be preserved visually while it becomes a real production client.
- `PLAN.md`: complete production implementation plan.

Important rule: do not treat the existing workbench prototype or any historical local-only planning text as the implementation scope. The target is the full production system described by the documentation.

## 2. Source-of-Truth Order

When documents conflict, resolve in this order and record the decision:

1. `GOAL.md`
2. `AGENT_GOAL.md`
3. `goals/*.md`
4. `experience/*.md`
5. `implementation/*.md`
6. `PLAN.md`
7. `web/` and future implementation code
8. `docs/progress-log.md`, `docs/known-gaps.md`, `docs/implementation-decisions.md`

`PLAN.md` is not allowed to reduce scope below the source documents. Its purpose is to force complete source coverage and production acceptance.

## 3. Repo Layout

```text
GOAL.md             # Sextant Memory macro goal
AGENT_GOAL.md       # Sextant Agent macro goal
goals/              # Memory / Agent / Storytelling Control domain design
experience/         # Product experience contracts
implementation/     # Production engineering specifications
PLAN.md             # Complete production implementation plan
AGENTS.md           # Agent operating manual
docs/               # Readiness review, progress, gaps, decisions
web/                # Frontend workbench prototype and future production client
```

## 4. Required Context Before Coding

Before implementation work starts, the agent must:

1. read `AGENTS.md`;
2. read `PLAN.md`;
3. enumerate every Markdown file under the repository source directories;
4. read all source Markdown files listed in `PLAN.md`;
5. create or update a source coverage section in `docs/progress-log.md`;
6. record conflicts or scope decisions in `docs/implementation-decisions.md`.

Do not rely on only a subset of `goals/` or `implementation/`. Do not silently collapse multiple source requirements into a vague summary.

## 5. Working Directory and Package Manager

Frontend working directory:

```bash
cd web
```

Frontend package manager:

```bash
pnpm
```

If Corepack is not enabled locally:

```bash
corepack enable
```

## 6. Common Commands

Documentation check:

```bash
git diff --check -- AGENTS.md PLAN.md README.md docs experience goals implementation web
rg -n "TODO|TBD|[ \t]+$" AGENTS.md PLAN.md README.md docs experience goals implementation web || true
```

Frontend install and run:

```bash
pnpm --dir web install
pnpm --dir web dev
```

Frontend verification:

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
pnpm --dir web test
pnpm --dir web test:e2e
```

If backend, worker, migration, API generation, or security commands are added, document them in README and require them in final verification.

## 7. Implementation Rules

- Implement the complete production system described by the source documents.
- Do not create placeholder features that look complete.
- Do not use frontend-only state to pretend domain behavior exists.
- Do not let provider output directly write memory or canon.
- Do not mark external integrations complete unless production configuration, validation, and failure behavior exist.
- Only the LLM/provider boundary may use a deterministic local substitute.
- Do not mock or fake any non-LLM subsystem for completion or acceptance.
- If non-LLM credentials or hosted infrastructure are missing, implement the production interface and validation path, then record the exact blocker. Do not replace it with a local mock or adapter and mark it complete.
- Preserve current web workbench visual direction unless a documented product contract requires a targeted UI change.
- Update `docs/progress-log.md` after each checkpoint.
- Update `docs/known-gaps.md` only for real non-blocking gaps or exact external blockers.
- Update `docs/implementation-decisions.md` for architecture, schema, dependency, provider, persistence, security, or testing decisions.

## 8. Frontend Constraints

The current `web/` workbench visual direction is an asset. Do not broadly redesign:

- layout density;
- type hierarchy;
- quiet writing-workbench character;
- Candidate Drawer, Memory Writeback, Scene Card visual language;
- Chinese copy style.

Allowed frontend changes:

- connect UI to real domain/API state;
- add production client behavior;
- add stable test selectors;
- add accessibility and responsive fixes;
- remove, disable, or implement unfinished actions;
- fix lint, typecheck, build, and test issues.

## 9. Domain Boundary

The implementation must preserve the full evidence chain:

```text
DraftCandidate
  -> AcceptedFragment
  -> SourceDelta
  -> SourceSpan
  -> EvidenceLogEntry
  -> MemoryWritebackPreview
  -> ProposedMemory / ReviewItem
  -> MemoryPage / CanonPromotion
  -> GraphProjection
```

Forbidden:

```text
DraftCandidate -> MemoryPage
DraftCandidate -> Current Canon
AgentReviewFinding -> ReviewItem without SourceSpan
model output -> CanonFact without evidence and review policy
GraphProjection -> FactAssertion
```

## 10. Dependency Policy

- Production dependencies require a reason and an entry in `docs/implementation-decisions.md`.
- Test dependencies are allowed when they support required acceptance coverage.
- Do not commit real secrets, API keys, user-private text, or production credentials.
- Local adapters are allowed for tests; they must not be represented as final production integrations.

## 11. Definition of Done

A production implementation goal is complete only when:

- every source Markdown file has a coverage record;
- every source requirement is implemented or blocked with exact evidence;
- source documents, code, tests, and README agree;
- `implementation/13-acceptance-matrix.md` acceptance is satisfied;
- frontend, backend, worker, migration, API, security, and smoke verification commands pass;
- clean-context human UI acceptance passes through browser/computer-use only;
- `docs/progress-log.md`, `docs/known-gaps.md`, and `docs/implementation-decisions.md` are current.

## 12. Recommended Goal Prompt

```text
/goal Implement the complete production-ready Sextant system described by the repository documentation.

Read AGENTS.md first. Then read PLAN.md and enumerate every Markdown file under GOAL.md, AGENT_GOAL.md, goals/, experience/, implementation/, docs/, README.md, and web/README.md.

Before coding, create a source coverage section in docs/progress-log.md listing every source Markdown file and the implementation obligations derived from it. Do not omit, collapse, or simplify requirements silently.

Build the complete production implementation, not a demo. No placeholder features, no fake UI-only success states, no hardcoded product flow pretending to be real behavior, and no mock-only final implementation.

Preserve the current web workbench visual direction. Do not redesign the UI unless a documented product contract requires a targeted change.

Only the LLM/provider boundary may use a deterministic local substitute. Do not mock or fake any other subsystem for completion or acceptance. If non-LLM credentials, hosted infrastructure, or third-party access are unavailable, implement the production interface, configuration contract, and validation path, then record the exact blocker in docs/known-gaps.md. Do not mark that feature complete.

Use subagents where helpful for source coverage, architecture review, backend/domain review, frontend UI preservation review, security review, and clean-context human acceptance.

Final clean-context acceptance must use only the running UI through browser/computer-use. The reviewer must not inspect source code or docs. They must verify the complete user-facing workflow and report exact pass/fail evidence.

Stop only when every source document requirement is implemented or explicitly blocked with evidence, all production acceptance criteria pass, and code, tests, and docs are aligned.
```
