# Implementation Decisions

## 2026-06-29 - Coverage Set Includes All Goal-Start Markdown, but Source-of-Truth Order Still Governs

Decision: the 2026-06-29 implementation run treats every Markdown file present at goal intake as part of the coverage inventory, while preserving `AGENTS.md` / `PLAN.md` source-of-truth order for conflict resolution.

Rationale:

- `PLAN.md` requires the agent to enumerate the baseline source set and also include additional Markdown files that already exist when the goal starts;
- the repository contains supplemental Markdown outside the baseline list, notably `PRODUCT.md` and `prompts/skills/*.md`;
- these extra files contain useful product-direction or provider-boundary constraints, but they must not silently outrank `GOAL.md`, `AGENT_GOAL.md`, `goals/*.md`, `experience/*.md`, or `implementation/*.md`.

Consequences:

- `docs/progress-log.md` must cover every goal-start Markdown file, including `PRODUCT.md` and prompt skill docs;
- if any supplemental Markdown conflicts with higher-order source docs, the higher-order source docs win and the conflict must be logged here;
- prompt files count as provider-boundary implementation evidence, not as proof that Story Skill architecture is complete.

## 2026-06-29 - Dirty-Branch Intake Audit Runs In Place Before Further Refactors

Decision: because the current checkout is already a large dirty implementation branch, the 2026-06-29 goal intake audit runs in place first instead of creating a new worktree immediately.

Rationale:

- `git status --short --branch` shows extensive modified and untracked implementation files across docs, backend, scripts, and `web/`;
- creating a new isolated lane before auditing the live branch state would risk losing the real execution context of the active implementation work;
- the user explicitly required preserving unrelated dirty state and forbade reset/revert style cleanup.

Consequences:

- the current run must avoid destructive git commands and work with the existing dirty tree carefully;
- state documentation must be updated before further feature edits so later implementation decisions are grounded in the live branch, not stale docs;
- if a later step needs isolation, it must be done without overwriting or discarding the current branch state.

## 2026-06-29 - Hosted Readiness Rows Stay Blocked Until External Proof Exists

Decision: hosted/deployed acceptance rows are incomplete until this run either records real external proof or explicitly leaves them as exact blockers.

Rationale:

- `README.md`, `docs/deployment-runbook.md`, and `implementation/12-13` require real hosted URLs, credentials, proof refs, and clean-context acceptance evidence;
- the repository already contains config gates and hosted probe runners, so the correct local behavior is to verify those gates and record blockers rather than fake completion;
- local green tests do not satisfy deployed smoke, hosted IAM/session/secret/object-store proof, or browser/computer-use clean-context acceptance.

Consequences:

- `docs/known-gaps.md` should list only the hosted items that remain externally blocked after this run's verification;
- `docs/progress-log.md` and any final status report must distinguish local implementation completion from hosted/deployed completion;
- no local mock, placeholder proof ref, or localhost walkthrough may be counted as the final acceptance evidence for those rows.

## 2026-06-29 - Deterministic Local Acceptance Uses Explicit Structured Writeback Inputs

Decision: local deterministic end-to-end acceptance must not assume that natural-language prose creates MemoryPage or GraphProjection side effects without an explicit supported provider output.

Rationale:

- the current deterministic local memory extractor only accepts explicit structured `FACT:` / `THREAD:` directives;
- the 2026-06-29 Playwright failure showed a stale test assumption: natural-language candidate acceptance correctly created SourceDelta/SourceSpan evidence, but not facts or memory pages;
- source-of-truth docs explicitly reject reviving local prose semantic parsing just to make local tests pass.

Consequences:

- browser and Playwright local acceptance should verify prose candidate acceptance as evidence-backed writeback, not as implicit fact extraction;
- when local acceptance needs MemoryPage/GraphProjection coverage, it must introduce an explicit supported structured input path instead of expecting removed prose-parser behavior;
- no test should reintroduce the old natural-language-to-memory shortcut under a new name.

## 2026-06-29 - Dev Workbench Seed Must Be Repeatable On A Persistent State Dir

Decision: `backend/scripts/seed_workbench.py` must reuse the existing global `genre/mystery/mystery.v1` schema pack instead of blindly inserting it on every run.

Rationale:

- `scripts/dev-workbench.sh` intentionally reuses a persistent local state dir unless `SEXTANT_DEV_RESET=1` is set;
- the live clean-context acceptance attempt failed because rerunning the seed on the same SQLite DB violated the unique constraint on `story_schema_packs(pack_type, pack_name, version)`;
- a local dev workbench that cannot be restarted cleanly is not acceptable as the human/browser acceptance surface.

Consequences:

- repeated `scripts/dev-workbench.sh --prepare-only` runs on the same state dir are now regression-tested;
- the fix is intentionally narrow: it preserves a stable shared genre pack while leaving per-run project/source seeding behavior intact;
- clean-context browser acceptance can now start from the documented local workbench path without requiring manual DB cleanup.

## 2026-06-29 - Supersede Local Prose Cue Semantic Parser Direction

Decision: local prose cue/regex inference must not be treated as Sextant's semantic architecture.

Rationale:

- creative prose semantics should be proposed by rich skills/provider calls, not by source-pipeline word tables;
- deterministic code should validate schema, evidence boundaries, SourceSpan ancestry, review policy, and canon policy;
- prompt registry, provider adapters, and SkillRun replay are useful infrastructure but not SkillRegistry/Resolver;
- self-authored fixture sentences are insufficient to prove semantic generalization.

Consequences:

- target docs must reject local prose cue taxonomy expansion;
- the 2026-06-29 cleanup pass deleted source-pipeline prose inference paths and corresponding tests;
- the immediate follow-on work from this cleanup was to implement first-class Story Skill runtime surfaces, deterministic validators, real-corpus eval, and assessment-only Codex judge rubric support without giving that rubric production authority.

## 2026-06-29 - Preserve Infrastructure, Not False Completion Claims

Decision: provider ports/adapters, prompt files, prompt hash locking, `SkillRun` persistence, replay-diff evaluation, worker handlers, and source/evidence/review/memory/graph skeletons remain meaningful infrastructure.

Rationale: these pieces are aligned with the production direction when they are not used to claim completed creative semantic understanding.

Consequences:

- keep target docs explicit about what exists;
- do not preserve stale prose-cue progress entries in working-tree docs;
- once the local Story Skill/runtime work lands, only externally sourced proof items should remain open in status docs.

## 2026-06-29 - Documentation Cleanup Before Code Cleanup

Decision: target documentation must be corrected before the next code/test cleanup pass.

Rationale: future Codex goal execution reads repository docs first. Leaving stale target language in place causes agents to keep extending the wrong source-pipeline semantic parser.

Consequences:

- this plan modifies docs only;
- the next execution phase removes invalid production code and tests;
- no production code should be changed during this target-documentation cleanup.

## 2026-06-29 - Remove Local Prose Semantic Paths Instead of Renaming Them

Decision: the cleanup pass deletes local prose cue/regex semantic paths and their tests rather than keeping them as fallback, aliases, or renamed taxonomies.

Rationale:

- keeping dead or renamed prose taxonomies would keep misleading architecture in the working tree;
- ordinary narrative prose must not create or propose character knowledge, semantic facts, communication claims, POV conclusions, review items, memory writeback, canon promotion, or graph facts through local regex parsing;
- boundary tests should prove absence of these side effects, while structured candidates and explicit metadata continue through deterministic review/policy flow.

Consequences:

- `source_pipeline` keeps only explicit scene metadata extraction, alias/event/fact infrastructure, provider-boundary POV adjudication, and deterministic policy steps;
- summary-based transfer ownership and review heuristics are removed; structured ownership now requires explicit candidate roles rather than local prose cue parsing;
- the local memory extractor keeps only explicit `FACT:` / `THREAD:` parsing;
- legacy semantic suites `backend/tests/integration/test_source_pipeline_jobs.py` and `backend/tests/unit/test_source_pipeline_parsing.py` are removed and replaced by focused boundary coverage.

## 2026-07-01 - Local Story Skill Architecture Is Now First-Class

Decision: the local repo now implements the first-class Story Skill runtime surfaces that the source docs required, and status docs must stop describing them as missing.

Rationale:

- `backend/src/sextant/ports/story_skills.py` now provides the runtime core, while `backend/src/sextant/infra/story_skill_registry.py` remains as a compatibility export for existing imports and tests;
- `backend/src/sextant/infra/{memory_writeback.py,source_pipeline.py}` now execute provider-boundary skills through that runtime, and `backend/src/sextant/application/use_cases.py` records resolved skill plans while keeping deterministic story-draft validation aligned with the same contract boundary;
- `backend/tests/integration/test_story_skill_runtime.py` and the dependent integration suites prove the runtime wiring behaves as required across action requests, source processing, writeback, and candidate generation.

Consequences:

- `docs/progress-log.md`, `GOAL.md`, `README.md`, `PLAN.md`, and `implementation/06-story-skills-and-llm-harness.md` must reflect local completion for SkillRegistry/Resolver/runtime work;
- prompt registry, provider adapters, and SkillRun replay remain useful infrastructure, but they are no longer the only skill-layer evidence in the repo;
- remaining gaps for this area are now limited to external provider live proof and hosted/deployed acceptance evidence.

## 2026-07-01 - Story Skill Runtime Core Lives In The Ports Layer

Decision: the reusable Story Skill runtime core lives in `sextant.ports.story_skills`, with `sextant.infra.story_skill_registry` preserved as a compatibility export.

Rationale:

- `tach check` correctly rejected `sextant.application` importing the runtime from `sextant.infra`;
- the Story Skill runtime core is deterministic contract logic over provider ports rather than infrastructure that owns persistence or environment wiring;
- keeping a thin infra re-export avoids gratuitous churn in existing infra call sites, tests, and doc references while restoring the intended layer rules.

Consequences:

- new application-layer imports must target `sextant.ports.story_skills`, not `sextant.infra.story_skill_registry`;
- infra modules may keep using the compatibility export temporarily, but the semantic owner is now the ports-layer runtime core;
- status docs should mention the ports-layer core when describing the architecture decision.

## 2026-07-01 - Retrieval Context Uses RRF Hybrid Recall And Scene-Local Sliding Windows

Decision: retrieval context assembly now uses reciprocal-rank fusion for keyword-plus-embedding hybrid recall and scene-local sliding-window style memory selection.

Rationale:

- `backend/src/sextant/infra/semantic_search.py` now preserves semantic ref keys so downstream policy can reason over the same evidence targets as embedding recall;
- `backend/src/sextant/infra/retrieval_fusion.py` and `backend/src/sextant/infra/uow.py` combine keyword and embedding rankings through deterministic reciprocal-rank fusion instead of treating embedding expansion as a one-way bonus;
- focused tests in `backend/tests/integration/test_memory_answer_context_pack.py` prove both the `rrf_keyword_embedding_hybrid` policy label and the scene-local sliding-window selection behavior.

Consequences:

- source-of-truth rows for `goals/09-retrieval-context-pack.md` and `implementation/10-worker-and-jobs.md` should now cite the local hybrid retrieval implementation rather than listing RRF/sliding-window as open work;
- future retrieval tuning should preserve evidence boundaries and policy determinism instead of reintroducing heuristic prose parsing;
- hosted pgvector and provider-live proof remain separate external evidence requirements.

## 2026-07-01 - Real-Corpus Boundary Eval Uses Ignored Sample Paths Plus Deterministic Invariants

Decision: real-corpus eval is implemented as a local runnable harness that references ignored corpus paths, fixed slice coordinates, deterministic invariants, and an assessment-only Codex judge rubric.

Rationale:

- `backend/src/sextant/infra/real_corpus_skill_eval.py` loads a spec file that forbids embedding corpus text in the committed dataset and resolves the actual corpus through repo-local ignored paths;
- `backend/scripts/real_corpus_memory_boundary_eval.py` runs the boundary harness end to end and emits structured results for each slice;
- the Fanren dataset and rubric files capture fixed slice coordinates and assessment dimensions without granting Codex judge output production authority.

Consequences:

- `implementation/13-acceptance-matrix.md` should verify the skill semantic eval target against the real harness, dataset, and rubric rather than leaving it as a future plan;
- future local eval additions must keep copyright text out of git and must test boundary invariants rather than exact-output prose;
- real provider live eval across hosted credentials remains an external proof requirement.

## 2026-07-01 - Alembic Env Escapes Percent-Encoded Database URLs

Decision: `backend/migrations/env.py` escapes percent signs before writing `SEXTANT_DATABASE_URL` into Alembic's ConfigParser-backed `sqlalchemy.url` option.

Rationale:

- hosted database passwords can require URL encoding, which introduces `%xx` sequences in otherwise valid SQLAlchemy URLs;
- ConfigParser rejects unescaped `%` when `config.set_main_option(...)` is used, causing production migrations to fail before any database connection is opened;
- the deployment path should accept ordinary percent-encoded PostgreSQL URLs rather than requiring manual password rotation to avoid `%`.

Consequences:

- Alembic receives the original decoded URL value after ConfigParser interpolation while remaining compatible with SQLite and local migration tests;
- `backend/tests/integration/test_migrations.py::test_alembic_env_accepts_percent_encoded_database_url` covers the regression observed during Supabase deployment;
- future migration environment changes must avoid logging or rendering full database URLs.

## 2026-07-01 - Cloudflare R2 Uses A New WNAM Bucket Name

Decision: production object storage uses `sextant-prod-wnam-objects` instead of reusing the earlier `sextant-prod-objects` bucket name.

Rationale:

- Cloudflare's R2 data-location documentation says `WNAM` is the Western North America location hint and that location hints are honored only the first time a bucket name is created;
- deleting and recreating `sextant-prod-objects` preserved the original APAC location, so changing production locality required a new bucket name;
- no production data had been written to the APAC bucket, so deleting it and switching secrets to the WNAM bucket avoided migration complexity and removed a deployment footgun.

Consequences:

- deployment environments must set `SEXTANT_R2_BUCKET=sextant-prod-wnam-objects` and should not recreate or depend on `sextant-prod-objects`;
- local production secrets now include `SEXTANT_R2_LOCATION_HINT=WNAM` as a human-readable deployment note, while S3 clients continue to use the standard R2 endpoint and `SEXTANT_AWS_REGION=auto`;
- hosted readiness evidence should cite the WNAM bucket settings page verification and the live object-store probe rather than the earlier APAC probe.

## 2026-07-01 - OpenAI Memory Extraction Predicate Is Schema-Bound

Decision: OpenAI memory extraction `facts[].predicate` is constrained by the Pydantic structured-output schema to the base story-schema relation enum.

Rationale:

- hosted smoke failed at `run_memory_writeback` because the provider returned a relation that the deterministic story-schema validator rejected as `schema_relation_not_allowed`;
- loosening writeback validation would violate the source-of-truth requirement that provider output cannot directly write memory/canon and must pass deterministic schema, evidence, review, and canon gates;
- constraining the provider schema and prompt keeps natural-language interpretation at the provider boundary while preserving deterministic downstream validation.

Consequences:

- `backend/src/sextant/infra/memory_extraction_openai.py` now imports `BASE_RELATIONS` and exposes `OpenAIMemoryRelation = Literal[*BASE_RELATIONS]`;
- `prompts/skills/openai_memory_extraction/openai-memory-extraction.v1.md` explicitly lists the allowed relation names and instructs the provider to omit unsupported claims;
- `backend/tests/integration/test_memory_extraction_provider.py::test_openai_memory_extraction_structured_schema_limits_predicates_to_base_story_relations` covers the schema invariant without relying on a seed-story fixture sentence;
- hosted external smoke and provider live eval must be rerun after any future relation-schema change.

## 2026-07-01 - Pgvector HNSW Index Uses Configured Embedding Dimensions

Decision: production pgvector HNSW indexing uses a fixed-dimension expression index based on `SEXTANT_EMBEDDING_DIMENSIONS`.

Rationale:

- Supabase accepted the `embedding_vector` column but rejected a generic HNSW index with `column does not have dimensions`;
- the hosted recall probe queries `embedding_vector::vector(N)`, so the index must use the same configured dimension and a partial predicate matching `dimensions = N`;
- hardcoding a sample or deployment-specific dimension in tests would be brittle, while reading the configured production dimension keeps the migration aligned with the deployed embedding provider.

Consequences:

- migration `7c8d9e0f1a2b_add_pgvector_semantic_index.py` creates the HNSW index only when `SEXTANT_EMBEDDING_DIMENSIONS` is configured;
- migration `af1b2c3d4e5f_ensure_pgvector_hnsw_index.py` backfills the same index for databases that had already reached the previous head before the missing-index fix;
- Supabase production was upgraded to `af1b2c3d4e5f`, creating `ix_semantic_embeddings_embedding_vector_hnsw` over `embedding_vector::vector(1024)` with `dimensions = 1024`;
- future embedding-dimension changes require a deliberate index migration or reindex plan rather than silently reusing the old partial index.

## 2026-07-01 - Hosted Vite Frontend Uses Runtime Supabase Auth

Decision: hosted static Vite deployments must not set `VITE_SEXTANT_BEARER_TOKEN`; they use public Supabase Auth runtime config and browser login to obtain a per-user JWT.

Rationale:

- Vite environment variables are embedded into the static frontend bundle, so a production bearer token in `VITE_SEXTANT_BEARER_TOKEN` would expose credential material to every browser;
- the backend is already configured for Supabase JWT/JWKS verification, so the production frontend should obtain tokens from the same session-provider boundary instead of baking a smoke token into the build;
- keeping token acquisition in a dedicated runtime auth gate lets the workbench stay disconnected until authenticated and avoids unauthenticated API requests that would produce misleading UI-only success or noisy 401 failures.

Consequences:

- `web/lib/workbench-api.ts` now has explicit `readWorkbenchAuthConfig`, `signInWorkbenchWithPassword`, and local session storage helpers for runtime Supabase Auth;
- `web/components/workbench/index.tsx` shows a production login gate when API context and Supabase Auth public config are present but no runtime token exists;
- hosted Vercel environment configuration must set `VITE_SEXTANT_SUPABASE_URL` and `VITE_SEXTANT_SUPABASE_PUBLISHABLE_KEY`, leave `VITE_SEXTANT_BEARER_TOKEN` blank, and rely on browser login during clean-context acceptance;
- this closes the frontend token-issuance implementation gap, but does not by itself satisfy Vercel deployment, CORS, session-provider proof refs, or clean-context UI acceptance.

## 2026-07-01 - OpenAI Memory Extraction Relation Roles Are Schema-Bound

Decision: OpenAI memory extraction structured output now uses relation-specific fact branches so each allowed predicate also constrains the permitted subject and object ref roles.

Rationale:

- hosted UI acceptance exposed a real `run_memory_writeback` terminal failure where the provider returned an allowed predicate with an invalid role pairing, rejected downstream as `schema_relation_role_not_allowed`;
- relaxing deterministic writeback validation would violate the evidence/review/canon gate rules and would let provider output shape memory directly;
- role constraints belong at the provider structured-output boundary so the provider proposes only schema-shaped candidates and the deterministic validator remains the final gate.

Consequences:

- `backend/src/sextant/infra/memory_extraction_openai.py` dynamically builds one discriminated Pydantic fact model per base relation using `BASE_RELATION_ROLE_RULES`;
- `OpenAILiteralRef` exists only for relations whose schema permits literal or relation-specific non-entity targets;
- `prompts/skills/openai_memory_extraction/openai-memory-extraction.v1.md` now lists relation-role constraints and instructs the provider to omit mismatched facts instead of forcing invalid ref types;
- `backend/tests/integration/test_memory_extraction_provider.py::test_openai_memory_extraction_structured_schema_limits_relation_roles` asserts the abstract role invariant for `owns` without relying on fixture-specific prose;
- VPS verification confirmed `REMOTE_FACT_BRANCHES=29`, `REMOTE_OWNS_OBJECT_TYPE=object`, and prompt hash `f14d85ff23d79f119eb55dae6385bb7614deed2c60242af5f56b3a839fc6e74a`.

## 2026-07-01 - New Vercel Project Replaces Stale `sextant-v3-web`

Decision: production frontend deployment uses a new Vercel project named `sextant-web`; the stale `sextant-v3-web` project was deleted instead of reused.

Rationale:

- the existing project name represented an earlier manual Sextant attempt and could hide old environment variables, domains, or deployment history;
- a fresh project gives a clearer deployment identity for hosted-readiness proof and avoids accidentally preserving a bundled-token build configuration;
- the static Vite frontend can be deployed safely only when public runtime auth config is present and `VITE_SEXTANT_BEARER_TOKEN` is blank.

Consequences:

- Vercel production deployment `dpl_4QoHJ1SQWJwnJmFciuH7BCNmgcsJ` is aliased as `https://sextant-web-nine.vercel.app`;
- backend CORS includes the Vercel alias and immutable deployment URL;
- `app.sextantlabs.net` is attached to `sextant-web`, verified by Vercel as CNAME-configured, and explicitly aliased to the production deployment;
- production Vercel env now stores only public Vite configuration and intentionally omits `VITE_SEXTANT_BEARER_TOKEN`;
- reproducibility was verified by redeploying from persisted Vercel production env as deployment `dpl_pQBgcTNB7s8XoSmbk2FjvDbYJUYv`;
- hosted-readiness evidence should cite the new project/deployment and not the deleted `sextant-v3-web` project.

## 2026-07-01 - SourceDelta Reindex Uses Cursor Pagination And Bounded S3 Reads

Decision: SourceDelta search reindex uses `(created_at, id)` cursor pagination for both incremental and full rebuild modes, and S3-compatible object-store clients use explicit timeout/retry configuration.

Rationale:

- hosted `--all` reindex proof exposed that `rebuild_all=True` repeatedly selected the same first batch because there was no cursor or filter that advanced after commit;
- the first symptom looked like an R2 hang because reindex held a DB session open while repeatedly reading object-store refs, so the operational path also needed bounded S3/R2 network behavior;
- production maintenance commands must either finish or fail with actionable evidence rather than waiting indefinitely on object-store connectivity.

Consequences:

- `backend/src/sextant/infra/source_delta_search.py` now paginates through SourceDelta rows by `(created_at, id)` and terminates in `--all` mode;
- `backend/src/sextant/infra/object_store.py` creates boto3 S3 clients with `SEXTANT_S3_CONNECT_TIMEOUT_SECONDS`, `SEXTANT_S3_READ_TIMEOUT_SECONDS`, and `SEXTANT_S3_MAX_ATTEMPTS`;
- `backend/tests/integration/test_source_delta_reindex.py::test_reindex_source_delta_search_rebuild_all_advances_batches` guards against repeated-batch loops;
- `backend/tests/unit/test_object_store.py::test_create_s3_client_uses_bounded_timeouts` guards the S3 timeout/retry defaults;
- hosted proof rerun against Supabase/R2 returned `status=pass`, `rebuild_all=true`, and `reindexed_rows=5`.

## 2026-07-01 - Production Readiness Uses Existing Stack Before New Paid Services

Decision: remaining hosted-readiness work should use Supabase, Vercel, VPS, and Cloudflare first, and should not introduce AWS Secrets Manager, GCP Secret Manager, Vault, Grafana Cloud, SES, SendGrid, Postmark, Mailgun, or another paid managed service without later explicit approval.

Rationale:

- the current deployment already has Supabase, Vercel, Cloudflare, and a VPS provisioned, and the user explicitly rejected extra billing for managed secret-manager, observability, and email-provider choices at this stage;
- the current domain may change and there are no external users yet, so invitation delivery provider setup is not a truthful prerequisite for the single-author smoke deployment, but remains a final production-readiness item if the source documents require invitations;
- backup/restore and rollback drills are allowed, but must be real drills with separate scratch restore target or real Vercel rollback/alias-rollback evidence rather than synthetic proof refs.

Consequences:

- root `TODOs.md` records the production-ready TODOs that remain intentionally incomplete and must not be reported as done;
- the hosted-readiness gate may be updated only when an existing-stack mechanism has real proof, for example Supabase Vault or another restricted secret storage path, self-hosted observability endpoints, a Supabase scratch restore, or a Vercel rollback drill;
- proof refs for already-passed hosted checks may be aligned to auditable runbook/progress evidence, but managed secret, invitation delivery, observability, backup/restore, and rollback items remain incomplete until separately proven.

## 2026-07-01 - Supabase Vault Is The Existing-Stack Secret Manager Path

Decision: production secret-manager support now accepts `supabase-vault://<project-ref>/<secret-name>` refs for provider credentials and hosted secret-manager readiness proof.

Rationale:

- the user rejected new AWS/GCP/Vault paid secret-manager billing and asked whether Supabase/Vercel/VPS/Cloudflare could handle the need;
- Supabase's current Vault documentation describes Vault as a Postgres extension for encrypted secret storage with `vault.create_secret(...)` and a `vault.decrypted_secrets` view, and the production Supabase project confirmed `supabase_vault` version `0.3.1` is installed;
- keeping provider secret resolution behind a structured `supabase-vault://` ref avoids calling the current VPS env file a managed secret manager and lets provider adapters read the OpenAI key without embedding it in browser bundles or repository files.

Consequences:

- `backend/src/sextant/infra/provider_secrets.py` can read Supabase Vault secrets through `SEXTANT_SUPABASE_VAULT_DATABASE_URL` or `SEXTANT_DATABASE_URL`;
- `backend/scripts/hosted_secret_manager_probe.py`, `backend/scripts/hosted_provider_live_eval_probe.py`, `scripts/validate-production-config.sh`, and `scripts/validate-hosted-readiness.sh` now validate `supabase-vault://` refs;
- Supabase production Vault secret `sextant_openai_api_key` was created without printing the secret value, and hosted secret-manager probe emitted only scheme, ref hash, byte count, and pass status;
- hosted provider live eval passed with direct OpenAI env keys unset and `credential_source=supabase-vault`;
- final production readiness still requires deploying this code/env to the VPS API and worker, restarting services, and recording VPS-side proof that the hosted runtime reads the Supabase Vault ref.

## 2026-07-01 - Vercel Alias Rollback Drill Covers Web Frontend Rollback

Decision: the first rollback execution proof uses Vercel alias rollback for `app.sextantlabs.net`, switching the app domain from the current production deployment to the previous ready deployment and then restoring the current deployment.

Rationale:

- the frontend is hosted as a static Vercel deployment and `app.sextantlabs.net` is the production user-facing app domain, so alias rollback is the real operational rollback path for web UI regressions;
- the user explicitly approved real Vercel rollback/restore work;
- using Vercel alias movement avoids fake status refs and proves that the production domain can be redirected and restored without touching unrelated backend/VPS state.

Consequences:

- rollback target was `dpl_4QoHJ1SQWJwnJmFciuH7BCNmgcsJ` at `sextant-3l1hbh706-frankqdwang1-9171s-projects.vercel.app`;
- current deployment was restored to `dpl_pQBgcTNB7s8XoSmbk2FjvDbYJUYv` at `sextant-l4n3ki70w-frankqdwang1-9171s-projects.vercel.app`;
- `app.sextantlabs.net` returned HTTP `200` both after rollback and after restore, and final `vercel inspect app.sextantlabs.net` resolved to the restored current deployment;
- backend/VPS rollback remains separate if source acceptance later requires service-side rollback proof.

## 2026-07-01 - Supabase Auth Is The Session And Token Issuer Provider

Decision: production session-provider and token-issuer readiness proof accepts `supabase://<project-ref>/auth` refs and uses Supabase Auth evidence artifacts served from the hosted app domain.

Rationale:

- the deployed frontend already uses Supabase Auth runtime login and the backend validates Supabase JWKS-issued JWTs;
- adding Auth0, Cognito, Okta, or Clerk would duplicate an already configured provider and add operational scope;
- the user asked to use the existing Supabase/Vercel/VPS/Cloudflare stack and avoid extra paid services unless needed.

Consequences:

- `backend/scripts/hosted_session_provider_provisioning_probe.py`, `backend/scripts/hosted_token_issuer_probe.py`, `backend/scripts/hosted_session_provider_probe.py`, and `scripts/validate-hosted-readiness.sh` now accept `supabase://` proof refs where session-provider or token-issuer refs are expected;
- static evidence artifacts are deployed at `https://app.sextantlabs.net/readiness/session-provider-provisioning.json` and `https://app.sextantlabs.net/readiness/token-issuer.json`;
- the artifacts contain deployment version, issuer/JWKS/admin URL, provider/status/counts, JWKS key count/type, and subject hash evidence only, not JWTs, passwords, user emails, client secrets, or service-role keys;
- session provisioning and token issuer probes pass against the hosted artifacts; invitation delivery is covered separately by the later Supabase Auth admin invite proof decision and still must not be faked.

## 2026-07-01 - Cloudflare R2 IAM Proof Uses Sanitized Hosted Artifact

Decision: production object-store IAM readiness accepts `cloudflare-r2://<bucket>/<principal>` proof refs and validates them through a sanitized hosted artifact served from the app domain.

Rationale:

- Cloudflare R2 is the selected object store in the existing stack, and the user asked to avoid adding paid AWS/GCP/Vault-style dependencies when Supabase, Vercel, VPS, and Cloudflare can satisfy the requirement;
- R2 is S3-compatible for runtime object read/write, but IAM/token scope evidence is Cloudflare-specific and should not be forced into `aws-iam://`;
- exposing raw account ids, token values, or full policy documents in the repository or browser bundle would violate the secret/evidence boundary, so the artifact records only bucket/token names, status, permission summary, location, counts, and hashes.

Consequences:

- `backend/scripts/hosted_object_store_iam_probe.py` and `scripts/validate-hosted-readiness.sh` now accept `cloudflare-r2://` proof refs;
- the readiness artifact at `https://app.sextantlabs.net/readiness/object-store-iam.json` records bucket `sextant-prod-wnam-objects`, token `sextant-prod-r2-runtime-wnam`, WNAM location, active token status, and object read/write permission summary;
- hosted object-store IAM probe passed and the hosted-readiness gate no longer reports `SEXTANT_OBJECT_STORE_IAM_PROOF_REF` as missing;
- object-store read/write proof remains separate from IAM proof and must continue to use the hosted object-store read/write probe evidence.

## 2026-07-01 - Observability Uses Self-Hosted Runtime Surfaces

Decision: production observability will use Sextant's own API/worker metrics and API-hosted trace/alert endpoints before adding external observability vendors.

Rationale:

- the user explicitly rejected adding Grafana Cloud, Prometheus SaaS, or another external paid observability platform at this stage;
- the API already exports Prometheus metrics and W3C trace headers, so adding sanitized runtime trace samples and metric-derived alert state gives a real self-hosted proof path without faking a third-party dashboard;
- observability endpoints must not leak manuscript text, prompt input, actor ids, raw provider output, secret values, raw trace ids, or raw span ids.

Consequences:

- `GET /observability/traces` exposes recent API request samples with path templates, status, duration, and SHA-256 trace/span fingerprints only;
- `GET /observability/alerts` reports metric-derived alert checks for API errors and worker job failures;
- `hosted_observability_pipeline_probe.py` is run against `https://api.sextantlabs.net/metrics`, `/observability/traces`, and `/observability/alerts`;
- the first hosted observability proof is scoped to `sextant_api_requests_total` plus API trace and alert-state endpoints because worker capacity is already proven by the separate hosted worker-capacity probe and endpoint;
- the Prometheus parser accepts route-template label values such as `path="/api/projects/{project_id}/context-pack-readiness"` so proof validation is based on metric identity rather than brittle label text parsing;
- hosted observability readiness is no longer blocked after the VPS R2 deployment and probe pass recorded in `docs/progress-log.md`.

## 2026-07-01 - VPS Deployment Uses Private R2 Artifact When SSH Is Unhealthy

Decision: when direct SSH to the VPS times out during banner exchange, use KiwiVM root shell plus a private, short-lived Cloudflare R2 deployment artifact to deploy source updates, while continuing to record SSH as an operational access gap.

Rationale:

- `nc` confirms TCP reachability to `74.211.103.250:22`, but OpenSSH times out before server banner exchange and the VPS did not observe those inbound sessions with `ss`, so the issue is outside normal password/public-key authentication;
- KiwiVM root shell remains available through the BandwagonHost control plane and is sufficient for root-run deployment scripts;
- Cloudflare R2 is already part of the approved stack, and a private presigned artifact avoids pushing dirty worktree state to GitHub or exposing code publicly;
- the deployment artifact contains backend source only and does not contain `.env` files, tokens, or production secrets.

Consequences:

- deployment scripts must verify artifact SHA-256 before extraction, back up `/opt/sextant/current/backend/src`, compile touched modules, and restart `sextant-api` and `sextant-worker`;
- presigned R2 URLs are treated as temporary secrets and must not be printed into docs, progress logs, or final status;
- direct SSH remains an operational follow-up item even though the current hosted observability and Vault runtime changes are deployed.

## 2026-07-01 - VPS Runtime Reads Provider Credentials From Supabase Vault

Decision: the hosted API and worker runtime now use `SEXTANT_LLM_API_KEY_SECRET_REF=supabase-vault://...` instead of direct `OPENAI_API_KEY` or `SEXTANT_OPENAI_API_KEY` entries in `/etc/sextant/sextant.env`.

Rationale:

- local secret-manager proof and provider live eval already showed Supabase Vault can resolve the provider key without printing it;
- the source rules prohibit claiming managed secret-manager completion while the hosted runtime still depends on direct environment key material;
- switching the VPS env closes the remaining gap between local secret-manager implementation and hosted runtime behavior.

Consequences:

- sanitized KiwiVM evidence records only direct-key count, secret-ref scheme, secret-ref hash, and service active states;
- a post-switch hosted external smoke passed through the deployed API/worker/provider path, which proves the runtime can still complete writeback work after removing direct provider env keys;
- future provider-key rotation should happen in Supabase Vault rather than editing the VPS env file with raw provider keys.

## 2026-07-01 - Supabase Auth Admin Invite Closes Invitation Delivery Readiness

Decision: use Supabase Auth admin invitations as the current production-shaped
invitation delivery provider, with `supabase-auth://<project-ref>/invite-user-by-email`
refs and a sanitized hosted delivery artifact. Do not close invitation delivery
readiness with a synthetic artifact, ProjectInvitation intent records, or the
mere existence of Supabase Auth invite APIs.

Rationale:

- the source contracts require hosted invitation delivery proof from a production-shaped external delivery provider/proof ref and explicitly forbid fake invitation delivery;
- Supabase Auth `inviteUserByEmail` / `invite_user_by_email` is a documented admin invite capability that sends an invite link to an email address, and Supabase Auth templates include an "Invite user" authentication email template;
- the user explicitly authorized sending an invite to `frankqdwang1@gmail.com`, and Chrome/Gmail search verified one matching Supabase invite result without opening the invite link or recording message content;
- the readiness gate, hosted invitation probe, hosted session-provider probe, and project invitation API now accept `supabase-auth://` invitation delivery refs while continuing to reject local/fake refs and URL userinfo/query/fragment secret material;
- Custom SMTP remains deferred because the user has no near-term commercial launch plan and does not want to add paid mail-provider billing yet.

Consequences:

- local production env now sets `SEXTANT_INVITATION_DELIVERY_PROVIDER=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email`, `SEXTANT_INVITATION_DELIVERY_PROOF_REF=supabase-auth://ientixxmbdeoqdmkublx/invite-user-by-email/20260701T100523Z`, and `SEXTANT_INVITATION_DELIVERY_ARTIFACT_URL=https://app.sextantlabs.net/readiness/invitation-delivery.json`;
- `backend/scripts/hosted_invitation_delivery_probe.py` returned `status=pass` with `provider_scheme=supabase-auth`, `proof_ref_scheme=supabase-auth`, `message_count=1`, and artifact SHA-256 `973cac01b37723cdf89f9400aafd319fc88137a297058d62b27bf847e38110de`;
- `bash scripts/validate-hosted-readiness.sh --allow-blocked` now returns `hosted-readiness-config-ok`;
- future commercial onboarding should configure Supabase Custom SMTP or another explicitly approved delivery provider, then record a new proof artifact rather than rewriting this historical smoke proof.

## 2026-07-01 - Backup Restore Uses Supabase Scratch Project And Application Schema Dump

Decision: hosted backup/restore proof uses a separate Supabase scratch project and restores the application schema plus required extensions, not Supabase-managed platform schemas.

Rationale:

- Supabase free-tier backup guidance points to logical backups with the CLI or `pg_dump`, and the user allowed a second Supabase scratch project as long as the free quota supports it;
- Supabase scratch projects already include platform-managed schemas such as `auth`, so restoring a full cluster dump into another Supabase project creates schema collisions and is not a valid application restore proof;
- Sextant application data lives in the `public` schema and depends on `vector` and `pg_trgm` extension objects in `public`, so the restore proof must include those extensions and validate restored evidence-chain tables.

Consequences:

- scratch project `avjwnxdexbwdenipizfc` (`sextant-restore-proof-scratch`) in `us-west-1` was created with Supabase-reported project cost `$0/month`;
- `backend/scripts/hosted_backup_restore_probe.py` now defaults to `SEXTANT_BACKUP_RESTORE_SCHEMAS=public` and `SEXTANT_BACKUP_RESTORE_REQUIRED_EXTENSIONS=vector:public,pg_trgm:public`;
- the probe runs `pg_dump --clean --if-exists --schema public --extension vector --extension pg_trgm`, uploads the dump to R2, downloads it back, restores into the scratch database, and validates SourceDelta, MemoryPage, and SourceSpan -> RawSource counts;
- hosted backup/restore proof passed and `SEXTANT_BACKUP_RESTORE_PROOF_REF` is aligned to `runbook://docs/progress-log/supabase-scratch-backup-restore-proof`.

## 2026-07-02 - Dynamic OpenAI Memory Extraction Schema Keeps A Narrow Static-Check Boundary

Decision: keep the OpenAI memory extraction response schema generated from the
story schema relation registry at runtime, and use precise lint/type ignores only
at the unavoidable dynamic Pydantic type-expression boundary.

Rationale:

- the structured OpenAI memory extraction schema must track `BASE_RELATIONS`,
  relation role rules, and story-schema entity types without hardcoding fixture
  phrases or sample-specific parser behavior;
- Pydantic's discriminated union needs the runtime `typing.Union[tuple]` and
  `Annotated[..., Field(discriminator="predicate")]` shape so JSON Schema
  generation and validation continue to reject invalid predicates and invalid
  relation-role entity types;
- `ty` and ruff cannot fully infer this dynamic type expression, so converting it
  to a static-looking alias would either break runtime schema generation or hide
  the real provider contract behind weaker `object` types.

Consequences:

- `backend/src/sextant/infra/memory_extraction_openai.py` keeps the dynamic union
  helper with `noqa` only on the runtime tuple-union expression and keeps the
  Pydantic runtime alias with `noqa`/`ty: ignore` only on the generated type
  expression;
- dynamic `create_model` calls now pass the generated field named `type`
  directly so static checking can validate the overload while preserving the
  Pydantic model field name;
- `test_memory_extraction_provider.py` continues to prove schema constraints,
  predicate limits, relation-role limits, provider parsing, and metric recording;
- this decision does not introduce a prose cue parser or any seed-story-specific
  extraction rule.

## 2026-07-02 - KiwiVM Source Redeploy Uses One-Line Base64 Scripts And Safe Post-Verify

Decision: when direct SSH is unavailable, use KiwiVM advanced shell for VPS
source redeploys as a single `base64 -> /tmp script -> bash` command, then run a
second no-secret verification script. Do not treat heredoc submissions or
stdout-only KiwiVM task output as deployment proof.

Rationale:

- KiwiVM advanced shell executes one-line commands reliably, but heredoc
  submissions replayed task text and did not provide trustworthy command-output
  evidence;
- the first failed `/bin/sh` attempt rejected `set -o pipefail`, so deployment
  scripts must explicitly execute under Bash while keeping the outer KiwiVM
  command POSIX-compatible;
- the deploy artifact URL is a short-lived secret-bearing presigned URL, so it
  must not be copied into docs, README, final status, or committed files;
- a separate safe post-verify script can prove artifact/source alignment,
  compileability, service state, and production health without exposing secret
  material.

Consequences:

- `docs/progress-log.md` records only the private R2 artifact key, artifact hash,
  expected source hashes, KiwiVM `Completed` status, and hosted smoke/readiness
  outcomes;
- future KiwiVM redeploy evidence must include a no-secret post-verify gate for
  current-source hashes, `python3 -m compileall`, `sextant-api` and
  `sextant-worker` active state, and `https://api.sextantlabs.net/health`;
- direct SSH remains preferable when available because it allows richer logs and
  easier rollback inspection, but KiwiVM one-line scripts are acceptable for
  source redeploys when followed by hosted smoke and readiness checks.
