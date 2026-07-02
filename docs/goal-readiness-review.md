# Codex Goal Readiness Review

This review records whether the repository is ready to claim completion for the long-horizon Codex Goal that implements the complete Sextant production system.

## 1. Overall Judgment

The repository now has local implementation evidence, hosted proof evidence,
current deployment/source alignment, and hosted clean-context UI acceptance
recorded for the current source documents. The final verification command set
was re-run after the latest status-document edits and passed; no current
source-document completion blocker is recorded.

It is not acceptable to treat local green tests, local browser acceptance,
deterministic local providers, or localhost smoke as substitutes for hosted
proof. The source documents require real production configuration, hosted
data-plane evidence, live provider proof refs, deployed smoke, and
clean-context UI acceptance evidence; those evidence classes are now recorded in
`docs/progress-log.md` for the current checkpoint.

## 2. What Is Ready

### 2.1 Product Direction

`GOAL.md` defines Sextant as an external long-term memory system for fiction authors. It emphasizes traceable evidence, correctable memory, story-aware retrieval, and canon/risk separation.

### 2.2 Agent Direction

`AGENT_GOAL.md` defines the writing agent as a memory-backed writing copilot, not an autopilot. The author remains in control.

### 2.3 Domain Source Material

`goals/` contains the Memory, Agent, and Storytelling Control design. All files under `goals/` must be read and covered.

### 2.4 Product Experience Contracts

`experience/` defines the user-facing contracts for writing sessions, action requests, candidate lifecycle, memory writeback, review/risk, and conversational entry.

### 2.5 Engineering Specifications

`implementation/` defines production engineering boundaries, persistence, API contracts, workers, CI/CD, observability, security, and acceptance criteria.

### 2.6 Web Prototype

`web/` provides a useful visual and interaction starting point. Its visual direction should be preserved, but its current demo data and component state are not production implementation.

## 3. Current Residual Work

The local implementation surface passed the 2026-07-02 core verification
checkpoint recorded in `docs/progress-log.md`. Hosted readiness also has
recorded evidence for managed PostgreSQL/pgvector, R2 object storage and IAM,
Supabase Vault runtime secrets, Supabase Auth session/token/invitation paths,
self-hosted observability, deployment approval, external smoke, backup/restore,
rollback, SourceDelta reindex, worker capacity, provider live eval, and
deployed clean-context UI acceptance.

Current residual work is release-discipline work:

- keep `docs/known-gaps.md`, `TODOs.md`, and this review aligned with the
  latest evidence;
- treat direct VPS SSH and Custom SMTP as operational follow-ups unless a
  source document makes them current acceptance gates.

## 4. Required Goal Start Procedure

Before coding, the implementation goal must:

1. read `AGENTS.md`;
2. read `PLAN.md`;
3. enumerate every source Markdown file;
4. read every file listed in `PLAN.md`;
5. create a source coverage table in `docs/progress-log.md`;
6. record any contradictions in `docs/implementation-decisions.md`.

## 5. Recommended Goal Prompt

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

## 6. Readiness Status

```text
Ready to continue production implementation: yes, with source coverage already recorded
Ready to claim local implementation checkpoint: yes, per docs/progress-log.md
Ready to claim hosted-readiness checkpoint: yes, when local production secrets are sourced and the gate returns hosted-readiness-config-ok
Ready to claim full product completion: yes for this checkpoint, with the current status documents and verification evidence
```
