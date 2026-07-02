# Sextant Web Workbench

This directory contains the Vite + React writing workbench prototype. Its visual direction should be preserved while the system becomes a real production client.

The current web app is not the complete product. Demo data and local interactions are available only when explicitly enabled for development; they must not be treated as final implementation.

## Run

```bash
pnpm install
pnpm dev
```

From the repository root:

```bash
pnpm --dir web install
pnpm --dir web dev
```

For a backend-backed local workbench session from the repository root:

```bash
pnpm --dir web install
bash scripts/dev-workbench.sh
```

The script runs migrations, seed data, DB worker health validation, the worker
loop, FastAPI, and Vite in API mode. It respects `SEXTANT_DATABASE_URL`,
`SEXTANT_OBJECT_STORE_ROOT`, `SEXTANT_DEV_API_PORT`, and
`SEXTANT_DEV_WEB_PORT`; use `--prepare-only` when you only need to validate the
runtime setup and generated `VITE_SEXTANT_*` environment. The generated
environment includes project, actor, source, SourceVersion, current scene, and
current POV character IDs for the seeded backend workbench project.

## Verify

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm test
pnpm test:e2e
```

From the repository root:

```bash
pnpm --dir web lint
pnpm --dir web typecheck
pnpm --dir web build
pnpm --dir web test
pnpm --dir web test:e2e
```

The `test` script runs Vitest contract/unit tests. The `test:e2e` script runs Playwright in backend API mode: it starts a migrated local FastAPI app, a DB worker loop, and the Vite app. By default it uses API port `8011` and web port `5810`; set `SEXTANT_E2E_API_PORT`, `SEXTANT_E2E_WEB_PORT`, or `SEXTANT_E2E_STATE_DIR` when those ports or the default local state directory are already in use.

Generated API client artifacts live in:

```text
web/src/generated/sextant-api.ts
```

Regenerate them from the repository root with:

```bash
uv run --python /opt/homebrew/bin/python3 python backend/scripts/generate_api_artifacts.py
```

Generated write methods require authenticated write headers:

```text
X-Actor-Id
X-Request-Id
Idempotency-Key
```

Generated read and write methods also accept an optional `bearerToken`, which
is sent as `Authorization: Bearer <token>`. In local/manual API-mode testing the
workbench can read this from `VITE_SEXTANT_BEARER_TOKEN`; leave it blank for
local `header-dev` runs. Hosted production must obtain per-user runtime tokens
from the session provider rather than baking a token into the static Vite
bundle. For the hosted Vite build, configure public Supabase Auth values
`VITE_SEXTANT_SUPABASE_URL` and `VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY`, leave
`VITE_SEXTANT_BEARER_TOKEN` blank, and let the author sign in at runtime.

The frontend must not treat body-level `actor_id` as authentication.

## Current Behavior

Without API configuration, the workbench shows a disconnected production state by default rather than seed-story data. Set `VITE_SEXTANT_ENABLE_DEMO=true` only for visual development sessions that intentionally need the fixed demo project `Harbor Nine · Ch.03 西档案室 · POV Mira`.

When `VITE_SEXTANT_API_BASE_URL`, project, actor, source, and source-version IDs are all configured, the workbench enters API mode for the current backend-backed path. `VITE_SEXTANT_SCENE_ID` and `VITE_SEXTANT_POV_CHARACTER_ID` are optional but should be set for scene-aware Ask Memory and Scene Card context. `VITE_SEXTANT_BEARER_TOKEN` is optional for local/manual development against `jwt-jwks`. When Supabase Auth runtime config is present and no bearer token is bundled, the workbench shows a login gate, exchanges the author's credentials with Supabase Auth in the browser, stores the returned runtime session locally, and then sends the resulting JWT in generated client headers:

1. load real `SourceVersion` text from the backend;
2. create a structured selected-text `ActionRequest`;
3. run it to create a draft-local `DraftCandidate`;
4. read candidate detail through the generated client;
5. accept browser text with target range and base hash; backend-mode
   Playwright covers this selected-text path through ActionRequest detail,
   Candidate detail, optional risk override, stale-source refresh/retry, and
   persisted SourceDelta evidence;
6. poll real job, MemoryWritebackPreview, and open ReviewItem state;
7. list, search, create, and archive project sources through backend APIs;
8. read SourceVersion history for the active source through backend APIs;
9. create source imports that return backend SourceDelta detail and a queued memory writeback job;
10. filter SourceDelta history by submitted text, status, kind, and SourceVersion through backend APIs;
11. list backend MemoryPages and inspect detail/source refs through the memory panel;
12. inspect backend GraphProjection edges from the memory panel with
    search/status filters, edge status, source refs, and SourceSpan evidence
    counts;
13. list/select admin-provisioned active Genre Packs and read/save versioned
    Project Story Schema overrides through the project panel and generated
    backend client;
14. list, add/update, and revoke Project Members, plus list project invitations,
    record invitation intent, and record external invitation proof refs through
    the project panel and generated backend client;
15. show a stale SourceVersion recovery path when backend rejects an old candidate base;
16. resolve formal ReviewItems with a canonical resolution selector, authored
    note, replacement SourceDelta refs, and backend side-effect inspection
    instead of a fixed frontend action; split/merge/fixed-by-text-edit
    resolutions require an authored note and replacement SourceDelta before
    submission; alias-conflict reviews load real backend CanonicalEntity
    options plus source/version-filtered backend scene options for optional
    disguise-arc scene-boundary correction instead of using frontend-only
    candidate state or raw persisted UI state; the boundary editor can
    explicitly apply the same boundaries to matching same-name disguise-arc
    AliasRecords, and Playwright covers selecting a backend scene option,
    submitting that bulk-boundary flag, and inspecting the resulting
    `alias_boundary_correction` side effects through the running UI and
    review-detail API;
17. open older SourceVersions from project history through the backend read API;
18. restore an older SourceVersion as a new backend SourceDelta/SourceVersion with a queued writeback job;
19. compare SourceVersions through the backend diff API and inspect line-level
    insert/delete/context rows in the project panel;
20. edit the current SourceVersion in the main editor and save it as a minimal
    backend SourceDelta/new SourceVersion with a queued writeback job, while
    stale source-edit saves are rejected before any writeback and can refresh
    to the latest SourceVersion, and draft edits show a compact line diff
    before save; stale rejected drafts are preserved for author merge, the
    merge action keeps the latest SourceVersion and appends draft-only lines,
    and merged text only persists if the author saves through SourceDelta;
21. record MemoryWritebackPreview accept/reject/correct decisions for fact and
    non-fact preview items through the generated backend client, including
    authored correction notes, corrected values, and replacement SourceDelta
    refs;
22. answer Ask Palette evidence questions through an `ask_memory`
    ActionRequest run and render typed MemoryAnswer evidence, confidence,
    caveat, ambiguous-target, source-mention, relationship, relationship
    timeline, relationship-path, event timeline, continuity-review, and
    open-thread metadata, plus author-facing semantic-clarification copy when
    recall finds multiple candidate evidence targets, while passing configured
    scene/POV context to the backend; API mode can also load backend
    CanonicalEntity options into compact Ask Palette controls so author-selected
    `subject_ref` / `predicate` constraints are sent explicitly through the
    `ActionRequest`;
23. explain backend DraftCandidates through an `explain_candidate`
    ActionRequest run, then reload candidate detail for the existing Candidate
    Drawer presentation;
24. check risk through a `check_risk` ActionRequest run and render typed
    AgentReviewFinding output in Candidate Drawer without enabling sentence
    acceptance or memory writeback;
25. request next story direction through a `suggest_next_direction`
    ActionRequest run and render typed BeatCandidate output in Candidate Drawer
    without enabling sentence acceptance or memory writeback;
26. save a selected candidate sentence as a revision request through a
    `revise_candidate` ActionRequest run, then load the replacement
    DraftCandidate while still requiring separate author acceptance;
27. reject a backend DraftCandidate through the generated client and render the
    returned terminal `archived` status instead of storing frontend-only state;
28. show backend `ContextPackReadiness` pending/stale/synced status in the
    Scene Card after writeback and author-requested ContextPack builds;
29. render populated WritingContextPack recent-event, object/location-state,
    character-agency, and style-sample sections in the Scene Card using the
    configured current scene/POV context while keeping the existing workbench
    density.

With `VITE_SEXTANT_ENABLE_DEMO=true` and without complete API configuration, development demo interactions remain available:

1. selecting text in the manuscript;
2. opening candidate continuation UI;
3. choosing a candidate sentence;
4. seeing a writeback-style panel;
5. using the bottom state switcher;
6. opening Ask Palette with `Cmd/Ctrl + K`.

The demo fallback is not production completion. It is opt-in only; production and ordinary local API-mode work must use backend state or show the disconnected state instead of seed-story behavior.

## Production Integration Direction

Future web work must:

- preserve the current writing-workbench visual direction;
- keep new conversational entries on structured `ActionRequest` paths rather
  than direct UI-only or candidate-only shortcuts;
- render the full candidate lifecycle from production domain/API data;
- reload new `SourceVersion` state after accepted text is persisted;
- extend source editing/history management beyond list, search, import, non-destructive archive, restore, version diff, draft diff preview, rejected-draft merge assistance, and basic full-text edit save;
- extend the real `SourceDelta`, `SourceSpan`, memory writeback, and review queue workflow beyond the current history/filter/detail surfaces;
- handle risk and review paths according to product contracts;
- remove, disable, or implement any unfinished actions;
- support clean-context human acceptance through the running UI.

## UI Constraints

Preserve:

- writing area as the main surface;
- quiet and restrained visual tone;
- dense but readable information hierarchy;
- natural Chinese writing copy;
- Candidate Drawer, Memory Writeback, and Scene Card visual language.

Do not broadly redesign the workbench to make implementation easier.

## Environment

Only the LLM/provider boundary may use deterministic local output. Production completion requires real API, persistence, worker, review, graph, observability, and configuration contracts as described by `PLAN.md` and `implementation/`.
