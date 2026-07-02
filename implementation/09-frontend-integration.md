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
5. Reject must use the backend operation response status; UI must not hardcode
   a rejected state that conflicts with the durable `archived` terminal state.

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
Alias-conflict reviews must load CanonicalEntity options from the backend
entity list API; the UI may keep a manual target ID field as a production
fallback, but it must not fabricate entity candidates in local state.

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
ContextPackReadiness pending/stale/synced status
compact GraphProjection relationship inspector inside the memory side panel
SourceSpan-backed MemoryPage open-thread回收/关闭 controls inside the memory side panel
compact Project Member list/upsert/revoke controls inside the project side panel
compact Project Invitation list/intent/proof controls inside the project side panel
compact Project Story Schema override editor inside the project side panel
compact Genre Pack selector inside the project side panel
```

Avoid exposing raw graph node tables, relation tables, or database-like editors as the default experience.
The relationship inspector is read-only and must show edge status and evidence
refs from the generated client; it must not let frontend state assert canon or
write GraphProjection.
The MemoryPage open-thread controls must call the generated backend
open-thread operation client, keep Chinese display labels separate from stored
summary text, and must not claim memory/canon/graph changes beyond the
backend-returned MemoryPage detail and stale readiness state.
The Project Story Schema override editor is a generated-client API surface for
versioned project schema configuration. It must submit through the backend
`PUT /story-schema/project-override` path and must not claim memory, canon,
graph, review, or SourceDelta side effects.
The Genre Pack selector must list active backend Genre Packs and submit through
`PUT /story-schema/genre-pack`; it must not use static frontend options or
write evidence-chain state.
The Project Member controls must read and write through generated backend
project-member APIs. They may update ProjectMembership rows, idempotency
records, and audit events only; they must not claim source, evidence, memory,
canon, graph, review, worker, or provider side effects.
The Project Invitation controls must read persisted backend ProjectInvitation
rows and submit invitation intent/proof refs through generated backend APIs.
They may update ProjectInvitation rows, idempotency records, and audit events
only; they must not create membership, send invitations, mint tokens, or claim
source, evidence, memory, canon, graph, review, worker, provider, or
object-store side effects.
Global Genre Pack provisioning/deprecation is an admin API surface. The
writing workbench should keep exposing only active-pack selection unless a
future product contract requires a dedicated admin tool; do not turn the
project panel into a raw schema-pack table editor.

## Frontend Tests

Required:

1. Vitest tests for ActionRequest payload builders.
2. Vitest tests for candidate accept disabled/override behavior.
3. Playwright journey: select text -> rewrite -> accept partial -> writeback preview -> review item appears.
4. Playwright stale-base journey.
5. Typecheck against generated client.

Current implementation coverage:

- `web/tests/workbench-api.test.ts` covers ActionRequest payloads including configured scene/POV context propagation, backend-built ContextPack current scene/POV payloads, candidate accept payloads, candidate reject returning the backend archived status, high-risk accept blocking, and stale SourceVersion error messaging.
- `web/tests/candidate-drawer.test.tsx` covers stale SourceVersion recovery UI and disables accepting an old candidate.
- `web/tests/editor.test.tsx` covers selected-text range calculation when the
  browser selection range uses paragraph element containers. `web/e2e/workbench.spec.ts`
  verifies selected-text rewrite through the running backend-backed UI:
  structured ActionRequest detail, Candidate detail reload, optional risk
  override, stale-source refresh/retry, author acceptance, and persisted
  SourceDelta evidence.
- `web/e2e/workbench.spec.ts` covers Project Panel ProjectInvitation controls
  through the running backend-backed UI: invitation intent creation, refresh
  persistence, external proof recording, and API readback of recorded
  sent/issued proof state without creating membership or hosted delivery/token
  execution.
- `web/tests/review-badge.test.tsx` covers selecting a formal ReviewItem
  resolution, authored note, replacement SourceDelta ref, split/merge resolve
  requirements, supersede replacement evidence type selection for ReviewItem
  refs, alias-conflict CanonicalEntity correction, optional disguise-arc
  scene-boundary correction with backend-provided scene option labels,
  explicit same-name disguise-arc bulk boundary application, and side-effect
  display.
  `web/tests/workbench-api.test.ts` verifies the
  selected resolution, replacement refs, and source/version-filtered scene
  options are sent to/read from the backend endpoints.
  `web/e2e/workbench.spec.ts` verifies alias-conflict correction through the
  running backend-backed UI, including CanonicalEntity options, backend scene
  option selection, explicit same-name disguise-arc bulk boundary submission,
  authored note submission, and alias-boundary/alias/memory/graph side-effect
  display plus review-detail API persistence evidence.
- `web/tests/project-panel.test.tsx` covers opening, comparing, and restoring older SourceVersions from project history plus project-member list/upsert/revoke controls. `web/tests/editor.test.tsx` and `web/tests/workbench-api.test.ts` cover controlled source editing, draft diff preview, rejected-draft merge assistance, and minimal SourceDelta payload creation. `web/e2e/workbench.spec.ts` verifies SourceVersion diff, switching v2 -> v1 -> v2, restore-to-v3, source-edit draft diff preview, source-edit-to-v4, and stale source-edit rejection/refresh/reapply through the running UI.
- `web/tests/project-panel.test.tsx` and `web/tests/workbench-api.test.ts`
  cover the Project Story Schema override panel, Genre Pack selector, and
  generated API adapter. `web/e2e/workbench.spec.ts` verifies a running
  API-mode user can select a real Genre Pack and save a Project Override
  through the project side panel.
- `web/tests/memory-writeback.test.tsx` covers MemoryWritebackPreview decisions and authored correction details for non-fact preview items so ReviewItem and other evidence-chain items are not hidden behind fact-only UI.
- `web/tests/memory-page-panel.test.tsx` and `web/tests/workbench-api.test.ts`
  cover the read-only GraphProjection relationship inspector and generated
  client adapter. `web/e2e/workbench.spec.ts` verifies the running API-mode UI
  can inspect persisted GraphProjection edges and filter disputed edges through
  the memory side panel.
- `web/tests/scene-card.test.tsx` and `web/e2e/workbench.spec.ts` cover
  backend-derived ContextPack readiness status in the Scene Card, including
  pending/stale visibility and synced state after an author-requested
  ContextPack build consumes matching readiness. The Scene Card also renders
  populated recent-event, object/location-state, character-agency, and
  style-sample sections from backend WritingContextPack data; e2e covers a real
  SourceSpan style sample from the seeded ContextPack.
- `web/e2e/workbench.spec.ts` covers backend-backed accept/writeback correction with replacement SourceDelta ref, review, and a stale-base journey where a candidate generated against an older SourceVersion is rejected before any writeback UI opens.

## Acceptance

Frontend integration is complete when:

1. No hand-written duplicate backend domain DTO exists.
2. Accept action includes base_hash and target range.
3. High-risk candidate cannot be accepted without explicit override.
4. MemoryWritebackPreview is non-blocking for low/medium risk.
5. Formal ReviewItem and AgentReviewFinding are visually and logically distinct.
