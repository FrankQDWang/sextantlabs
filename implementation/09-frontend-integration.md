# 09. Frontend Integration

The frontend is a writing workbench, not a database admin panel and not a chat-first app. It uses Vite + React + TypeScript and generated API clients.

## App Surfaces

First production workbench surfaces:

```text
editor pane
selection action menu
candidate drawer
memory side panel
review/risk panel
ask/command palette
writeback preview surface
status/toast surface
```

No surface owns domain truth. The backend owns all domain state.

## State Ownership

| State | Owner |
|---|---|
| Current editor buffer | frontend local + source version snapshot |
| Persisted manuscript versions | backend |
| Candidate lifecycle | backend |
| Memory pages | backend |
| ReviewItem lifecycle | backend |
| GraphProjection | backend |
| OpenAPI DTOs | backend generated client |
| UI panel open/closed state | frontend |

## Generated Client

Frontend imports API functions from:

```text
web/src/generated/
```

Rules:

1. Do not duplicate backend DTOs in frontend.
2. UI-local zod schemas are allowed only for form/view validation.
3. Generated files are protected; manual edits fail CI.

## Editor Integration

Editor must track:

```text
source_id
source_version_id
current_text_window
cursor_position
selected_range
base_hash
```

Any rewrite/accept action must send target position and base hash.

If backend returns `stale_source_version`, UI must ask the user to refresh/rebase the candidate, not silently apply text.

## ActionRequest Creation

All user actions become ActionRequest:

| UI action | ActionRequest |
|---|---|
| ask memory | `ask_memory` |
| check selected text risk | `check_risk` |
| suggest direction | `suggest_next_direction` |
| continue small passage | `continue_small_passage` |
| rewrite selected span | `rewrite_span` |
| explain candidate | `explain_candidate` |
| revise candidate | `revise_candidate` |

Natural language entry is allowed, but it must produce structured target and constraints.

## Candidate Drawer

Candidate card must show:

```text
candidate text or beat
mode
target range
risk summary
memory refs/evidence refs when available
actions: accept, partial accept, revise, explain, reject
```

Rules:

1. Accept is not default for high-risk candidate.
2. Blocked candidate requires override flow.
3. Partial accept is first-class.
4. Candidate explanation cannot be copied into Memory as evidence.

## Memory Writeback Preview

Preview surface shows what system is preparing to remember.

Risk behavior:

| Risk | UI behavior |
|---|---|
| low | small non-blocking confirmation/toast with undo/correction |
| medium | expandable card, can defer |
| high | review item, canon not promoted |

It must not block continued writing unless source structure parsing failed and downstream Memory cannot proceed.

## Review Panel

Review panel presents formal ReviewItems, not draft-local AgentReviewFinding.

Actions:

```text
accept
reject
split
merge
mark_intentional
supersede
needs_memory_update
fixed_by_text_edit
accepted_as_change
dismiss
reopen
```

UI labels can use writing language, but API values use canonical enum.

## Risk Display Split

| Object | Where shown | Behavior |
|---|---|---|
| AgentReviewFinding | candidate card, risk check result | draft-local, closes with candidate unless accepted |
| ReviewItem | review panel, memory page risk section | formal Memory risk, persists until resolved/dismissed/superseded |

UI must not show AgentReviewFinding as if it were a formal ReviewItem.

## Context Pack Display

The user does not need to see raw ContextPack by default.

Allowed display:

```text
current POV
active characters
known relevant facts
unknown/conflict warnings
open threads
```

Avoid exposing raw graph node tables, relation tables, or database-like editors as the default experience.

## Frontend Tests

Required:

1. Vitest tests for ActionRequest payload builders.
2. Vitest tests for candidate accept disabled/override behavior.
3. Playwright journey: select text -> rewrite -> accept partial -> writeback preview -> review item appears.
4. Playwright stale-base journey.
5. Typecheck against generated client.

## Acceptance

Frontend integration is complete when:

1. No hand-written duplicate backend domain DTO exists.
2. Accept action includes base_hash and target range.
3. High-risk candidate cannot be accepted without explicit override.
4. MemoryWritebackPreview is non-blocking for low/medium risk.
5. Formal ReviewItem and AgentReviewFinding are visually and logically distinct.
